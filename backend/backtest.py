"""Backtest engine — uses the SHARED SMC module to replay strategy on historical candles."""
from __future__ import annotations

import asyncio
import bisect
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from smc import analyze
import sessions as sess

logger = logging.getLogger(__name__)


def _aggregate(candles_m1: List[Dict], minutes: int) -> List[Dict]:
    """Aggregate M1 candles into higher timeframe by grouping `minutes` consecutive bars."""
    out: List[Dict] = []
    bucket: List[Dict] = []
    for c in candles_m1:
        bucket.append(c)
        if len(bucket) >= minutes:
            out.append({
                "time": bucket[0]["time"],
                "open": bucket[0]["open"],
                "high": max(b["high"] for b in bucket),
                "low": min(b["low"] for b in bucket),
                "close": bucket[-1]["close"],
            })
            bucket = []
    return out


TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}


def _to_iso(t: Any) -> str:
    """Coerce any time representation (datetime, ISO str, brokerTime) to ISO 8601 UTC."""
    if isinstance(t, datetime):
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.isoformat()
    return str(t)


def _parse_dt(t: Any) -> Optional[datetime]:
    if isinstance(t, datetime):
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    try:
        s = str(t).replace("Z", "+00:00").replace(" ", "T", 1)
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _bt_day_key(dt: datetime, settings: Dict[str, Any]) -> str:
    """Cle du jour de trading — miroir de bot_loop._trading_day_key (reset 17h EST en prop, sinon UTC)."""
    if settings.get("prop_firm_enabled") and settings.get("prop_daily_reset_hour_est") is not None:
        reset_h = int(settings.get("prop_daily_reset_hour_est", 17))
        ny = dt.astimezone(sess.NEWYORK)
        d = ny.date()
        if ny.hour >= reset_h:
            d = d + timedelta(days=1)
        return d.isoformat()
    return dt.date().isoformat()


def _bt_calc_lot(balance: float, risk_pct: float, entry: float, sl: float,
                 contract_size: float, max_lot: float) -> float:
    """Taille de lot au risque % — miroir de bot_loop.calc_lot_size (dimensionnement et
    drawdown comparables au live)."""
    risk_dollars = balance * (risk_pct / 100.0)
    sl_distance = abs(entry - sl)
    if sl_distance <= 0:
        return 0.01
    lot = risk_dollars / (sl_distance * contract_size)
    return max(0.01, min(max_lot, round(lot * 100) / 100))


def _register_close(rm: Dict[str, Any], closed_trade: Dict[str, Any], open_trade: Dict[str, Any],
                    equity: float, max_consec: int, max_dd_pct: float,
                    cdt: Optional[datetime], sinfo: Dict[str, Any], settings: Dict[str, Any]) -> None:
    """A la fermeture d'un trade, met a jour pertes consecutives + drawdown jour et declenche
    l'arret auto comme bot_loop (break-even = +/-0.1% ne compte pas comme perte)."""
    be_threshold = open_trade.get("_equity_at_open", equity) * 0.001
    delta = closed_trade.get("pnl", 0.0)  # deja en $
    if delta >= -be_threshold:
        rm["consec"] = 0
    else:
        rm["consec"] += 1
    stop = rm["consec"] >= max_consec
    if not stop:
        dse = rm.get("day_start_equity") or equity
        dd = (dse - equity) / dse * 100 if dse > 0 else 0
        stop = dd >= max_dd_pct
    if stop:
        rm["stopped"] = True
        day_key = _bt_day_key(cdt, settings) if cdt else rm["day"]
        rm["stop_day"] = day_key
        rm["stop_session"] = f"{day_key}|{sinfo.get('session')}"


async def run_backtest(req: Dict[str, Any], candles_m1: List[Dict],
                        on_progress=None, settings: Optional[Dict[str, Any]] = None,
                        point_size: float = 0.01, contract_size: float = 100.0) -> Dict[str, Any]:
    """Replay strategy on supplied M1 candles. Pure logic — no I/O.

    point_size / contract_size : spécifications du symbole testé (défauts = XAUUSD).
    Le serveur les lit en live via MetaApi avant d'appeler cette fonction, pour
    que le spread (points → prix) et le P&L (prix → $) soient corrects par symbole.
    """
    settings = settings or {}
    mode = req.get("mode", "intraday")
    htf = settings.get("intraday_htf", "H1") if mode == "intraday" else settings.get("scalping_htf", "H1")
    mtf = settings.get("intraday_mtf", "M15") if mode == "intraday" else settings.get("scalping_mtf", "M15")
    ltf = settings.get("intraday_ltf", "M5") if mode == "intraday" else settings.get("scalping_ltf", "M1")
    min_rr = float(settings.get("min_rr", 2.0))
    fractal_n = int(settings.get("fractal_n", 3))
    recent_window = int(settings.get("recent_window", 6))
    require_fvg = bool(settings.get("require_fvg_entry", True))
    require_sequence = bool(settings.get("require_sweep_then_choch", True))
    require_unmitigated = bool(settings.get("require_unmitigated_ob", True))
    require_pd = bool(settings.get("require_premium_discount", True))
    # Trailing / break-even (expérimental, OFF par défaut = aucun changement vs baseline).
    # N'affecte QUE le backtest : le bot live n'applique jamais le trailing.
    # Priorité à la requête (réglé par run depuis l'UI Backtest), sinon settings (scripts), sinon défaut.
    def _tparam(key, default):
        v = req.get(key)
        return v if v is not None else settings.get(key, default)
    # mode: "off" | "breakeven" | "r_trail" | "structure"
    trailing = {
        "mode": str(_tparam("trailing_mode", "off")),
        "trigger_r": float(_tparam("trailing_trigger_r", 1.0)),
        "distance_r": float(_tparam("trailing_distance_r", 1.0)),
        "lookback": int(_tparam("trailing_lookback", 5)),
        "buffer": float(_tparam("trailing_buffer", 0.0)),
    }
    spread_points = float(req.get("spread_points", 25))
    spread_price = spread_points * point_size  # 1 point = tickSize du symbole

    # Risque & limites du bot live — pour que le backtest reflete le NOMBRE de trades reel
    # et un dimensionnement/drawdown comparables au live (lus depuis les Reglages).
    risk_pct = float(settings.get("risk_per_trade_pct", 1.0))
    max_lot = float(settings.get("max_lot_per_trade", 10.0))
    max_trades_per_day = int(settings.get("max_trades_per_day", 5))
    max_consec = int(settings.get("max_consec_losses", 3))
    max_dd_pct = float(settings.get("max_drawdown_pct", 3.0))
    resume_policy = settings.get("resume_policy", "next_session")

    if not candles_m1:
        return {"trades": [], "metrics": {}, "equity_curve": []}

    htf_minutes = TF_MIN.get(htf, 60)
    mtf_minutes = TF_MIN.get(mtf, 15)
    ltf_minutes = TF_MIN.get(ltf, 5)

    trades: List[Dict[str, Any]] = []
    equity = 10000.0
    equity_curve: List[Dict[str, Any]] = [{"time": _to_iso(candles_m1[0]["time"]), "equity": equity}]

    htf_candles = _aggregate(candles_m1, htf_minutes)
    mtf_candles = _aggregate(candles_m1, mtf_minutes)
    ltf_candles = _aggregate(candles_m1, ltf_minutes)

    # Tableaux de temps pré-calculés : le temps croît de façon monotone, donc
    # bisect_right donne en O(log n) le nombre de bougies HTF/MTF déjà clôturées,
    # au lieu de refiltrer toute la liste à chaque bougie LTF (O(n²) → O(n log n)).
    # Fenêtres STRICTEMENT identiques à l'ancien filtre → résultats inchangés.
    htf_times = [h["time"] for h in htf_candles]
    mtf_times = [h["time"] for h in mtf_candles]

    # Etat des limites de risque (simule l'arret jour / pertes consecutives / drawdown du live).
    rm: Dict[str, Any] = {
        "day": None, "trades_today": 0, "consec": 0, "day_start_equity": equity,
        "stopped": False, "stop_day": None, "stop_session": None,
    }

    open_trade: Optional[Dict[str, Any]] = None
    step = max(1, len(ltf_candles) // 100)

    for i in range(60, len(ltf_candles)):
        if on_progress and i % step == 0:
            try:
                await on_progress(min(99.0, i / max(1, len(ltf_candles)) * 100.0))
            except Exception:
                pass
            await asyncio.sleep(0)

        c = ltf_candles[i]
        cur_time = c["time"]
        cdt = _parse_dt(cur_time)
        sinfo = sess.is_in_session(cdt, settings) if cdt is not None else {"in_session": False, "session": None}
        hk = bisect.bisect_right(htf_times, cur_time)
        mk = bisect.bisect_right(mtf_times, cur_time)
        htf_window = htf_candles[max(0, hk - 100):hk]
        mtf_window = mtf_candles[max(0, mk - 150):mk]
        ltf_window = ltf_candles[max(0, i - 200): i + 1]
        if len(htf_window) < 30 or len(mtf_window) < 30:
            continue

        if open_trade:
            _check_exit(open_trade, c, spread_price, trades, equity_curve, contract_size)
            if open_trade.get("_closed"):
                equity = equity_curve[-1]["equity"]
                # MAJ des limites (pertes consécutives + drawdown) comme le bot live.
                _register_close(rm, trades[-1], open_trade, equity,
                                max_consec, max_dd_pct, cdt, sinfo, settings)
                open_trade = None
            elif trailing["mode"] != "off":
                # Sortie non déclenchée avec le SL courant : on resserre le SL
                # pour la bougie SUIVANTE (jamais dans la même bougie → conservateur).
                _update_trailing(open_trade, c, ltf_window, trailing)

        if open_trade:
            continue

        # Sessions: comme le bot live, on n'OUVRE de position que pendant Londres/NY.
        # (Les positions déjà ouvertes, elles, sont gérées 24h via SL/TP ci-dessus.)
        if not sinfo["in_session"]:
            continue

        # ── Limites du bot live : reset quotidien, reprise après arrêt auto, plafonds ──
        day_key = _bt_day_key(cdt, settings)
        if day_key != rm["day"]:
            rm["day"] = day_key
            rm["trades_today"] = 0
            rm["day_start_equity"] = equity
        if rm["stopped"]:
            if resume_policy == "next_day":
                resumed = day_key != rm["stop_day"]
            else:  # next_session : on reprend à la prochaine session distincte
                resumed = f"{day_key}|{sinfo['session']}" != rm["stop_session"]
            if not resumed:
                continue
            rm["stopped"] = False
            rm["consec"] = 0
            rm["trades_today"] = 0
            rm["day_start_equity"] = equity
        if rm["trades_today"] >= max_trades_per_day:
            continue

        result = analyze(htf_window, mtf_window, ltf_window, fractal_n=fractal_n, min_rr=min_rr,
                         recent_window=recent_window, require_fvg=require_fvg,
                         require_sequence=require_sequence, require_unmitigated=require_unmitigated,
                         require_pd=require_pd)
        sig = result.get("signal")
        if sig:
            entry_price = sig["entry"] + (spread_price if sig["side"] == "buy" else -spread_price)
            # Dimensionnement au risque % comme le live (et non plus 1 lot fixe).
            lot = _bt_calc_lot(equity, risk_pct, entry_price, float(sig["sl"]), contract_size, max_lot)
            open_trade = {
                "id": str(uuid.uuid4()),
                "side": sig["side"],
                "entry_time": _to_iso(c["time"]),
                "entry": entry_price,
                "sl": sig["sl"],
                "tp": sig["tp"],
                "rr": sig["rr"],
                "lot": lot,
                "reason": sig["reason"],
                "exit_time": "",
                "exit_price": 0.0,
                "pnl": 0.0,
                "result": "be",
                # Suivi pour le trailing (préfixe _ → retiré du trade exporté).
                "_R": abs(entry_price - float(sig["sl"])),  # distance de risque = 1R
                "_max_fav": entry_price,                     # meilleure excursion favorable
                "_equity_at_open": equity,
            }
            rm["trades_today"] += 1

    # Close any trade still open at the end of the period at the last candle's
    # close — otherwise it is silently omitted from the metrics (biasing winrate).
    if open_trade and not open_trade.get("_closed") and ltf_candles:
        last_c = ltf_candles[-1]
        side = open_trade["side"]
        exit_price = last_c["close"]
        # Spread already paid once via the worse entry fill — do not subtract again.
        pnl_price = (exit_price - open_trade["entry"]) if side == "buy" else (open_trade["entry"] - exit_price)
        result = "win" if pnl_price > 0 else ("loss" if pnl_price < 0 else "be")
        pnl_money = pnl_price * contract_size * open_trade.get("lot", 1.0)
        open_trade.update(exit_time=_to_iso(last_c["time"]), exit_price=exit_price,
                          pnl=pnl_money, result=result, _closed=True)
        trades.append({k: v for k, v in open_trade.items() if not k.startswith("_")})
        equity_curve.append({"time": _to_iso(last_c["time"]),
                             "equity": equity_curve[-1]["equity"] + pnl_money})

    if on_progress:
        try:
            await on_progress(100.0)
        except Exception:
            pass

    metrics = _compute_metrics(trades, equity_curve)
    return {"trades": trades, "metrics": metrics, "equity_curve": equity_curve}


def _check_exit(trade: Dict[str, Any], c: Dict[str, Any], spread_price: float,
                trades: List[Dict[str, Any]], equity_curve: List[Dict[str, Any]],
                contract_size: float = 100.0) -> None:
    """Mutate trade in place when SL/TP hit, append to trades + equity_curve."""
    side = trade["side"]
    entry = trade["entry"]
    sl, tp = trade["sl"], trade["tp"]
    hit_sl = (c["low"] <= sl) if side == "buy" else (c["high"] >= sl)
    hit_tp = (c["high"] >= tp) if side == "buy" else (c["low"] <= tp)
    if not (hit_sl or hit_tp):
        return
    exit_price = sl if hit_sl else tp
    # Spread is already paid once via the worse entry fill (entry_price adjusted at open),
    # which models the full round-trip cost — do NOT subtract it again here (double-counting).
    pnl_price = (exit_price - entry) if side == "buy" else (entry - exit_price)
    # Classer par le SIGNE du P&L (pas par le niveau touché) : avec un trailing,
    # un SL remonté au-dessus de l'entrée donne un SL touché... GAGNANT.
    eps = trade.get("_R", 0.0) * 1e-6
    result = "win" if pnl_price > eps else ("loss" if pnl_price < -eps else "be")
    # P&L en $ pondéré par la taille de lot (risque %), comme le live.
    pnl_money = pnl_price * contract_size * trade.get("lot", 1.0)
    trade.update(exit_time=_to_iso(c["time"]), exit_price=exit_price, pnl=pnl_money, result=result, _closed=True)
    trades.append({k: v for k, v in trade.items() if not k.startswith("_")})
    last_eq = equity_curve[-1]["equity"] + pnl_money
    equity_curve.append({"time": _to_iso(c["time"]), "equity": last_eq})


def compute_trailing_sl(side: str, entry: float, current_sl: float, R: float, max_fav: float,
                        cur_high: float, cur_low: float, cur_close: float,
                        recent_lows: List[float], recent_highs: List[float],
                        params: Dict[str, Any]):
    """Logique UNIQUE de trailing partagée live (bot_loop) + backtest.

    Retourne (new_sl | None, new_max_fav). new_sl n'est renvoyé que s'il RESSERRE le SL
    (jamais l'inverse) et reste du bon côté du prix courant.
    Modes :
      - breakeven : à +trigger_r, SL → entrée (±buffer) = trade « gratuit »
      - r_trail   : à partir de +trigger_r, SL verrouille (excursion − distance_r)·R
      - structure : à partir de +trigger_r, SL suit le plus bas/haut des `lookback`
                    dernières bougies (∓ buffer)
    """
    if R <= 0:
        return None, max_fav
    mode = params["mode"]
    trigger = params["trigger_r"]
    buf = params["buffer"]

    if side == "buy":
        max_fav = max(max_fav, cur_high)
        if (max_fav - entry) / R < trigger:
            return None, max_fav
        if mode == "breakeven":
            cand = entry + buf
        elif mode == "r_trail":
            cand = max_fav - params["distance_r"] * R
        elif mode == "structure":
            cand = (min(recent_lows) if recent_lows else cur_low) - buf
        else:
            return None, max_fav
        new_sl = max(current_sl, cand)
        if new_sl > current_sl and new_sl < cur_close:
            return new_sl, max_fav
        return None, max_fav
    else:  # sell
        max_fav = min(max_fav, cur_low)
        if (entry - max_fav) / R < trigger:
            return None, max_fav
        if mode == "breakeven":
            cand = entry - buf
        elif mode == "r_trail":
            cand = max_fav + params["distance_r"] * R
        elif mode == "structure":
            cand = (max(recent_highs) if recent_highs else cur_high) + buf
        else:
            return None, max_fav
        new_sl = min(current_sl, cand)
        if new_sl < current_sl and new_sl > cur_close:
            return new_sl, max_fav
        return None, max_fav


def _update_trailing(trade: Dict[str, Any], c: Dict[str, Any],
                     ltf_window: List[Dict[str, Any]], params: Dict[str, Any]) -> None:
    """Backtest : resserre trade['sl'] via la logique commune. Appelé APRÈS _check_exit,
    donc le nouveau SL ne s'applique qu'à la bougie suivante (pas de triche intra-bougie)."""
    recent = ltf_window[-params["lookback"]:] if ltf_window else []
    new_sl, trade["_max_fav"] = compute_trailing_sl(
        trade["side"], trade["entry"], trade["sl"], trade.get("_R", 0.0), trade["_max_fav"],
        c["high"], c["low"], c["close"],
        [x["low"] for x in recent], [x["high"] for x in recent], params)
    if new_sl is not None:
        trade["sl"] = new_sl


def _compute_metrics(trades: List[Dict[str, Any]], equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    total_pnl = sum(t["pnl"] for t in trades)
    win_pnl = sum(t["pnl"] for t in wins)
    loss_pnl = sum(t["pnl"] for t in losses)
    profit_factor = (win_pnl / abs(loss_pnl)) if loss_pnl != 0 else (999.0 if win_pnl > 0 else 0.0)
    winrate = (len(wins) / len(trades) * 100) if trades else 0.0
    avg_rr = (sum(t["rr"] for t in trades) / len(trades)) if trades else 0.0

    peak = equity_curve[0]["equity"] if equity_curve else 10000.0
    max_dd = 0.0
    for p in equity_curve:
        peak = max(peak, p["equity"])
        dd = (peak - p["equity"]) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    final_equity = equity_curve[-1]["equity"] if equity_curve else 10000.0
    return {
        "trades_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_rr": round(avg_rr, 2),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "final_equity": round(final_equity, 2),
    }


# ---------------- chunked M1 download ----------------

class CandleFetchTimeout(Exception):
    """Raised when a single MetaApi candle batch exceeds the per-request timeout."""


async def download_m1_history(metaapi_client, symbol: str, start_dt: datetime, end_dt: datetime,
                               on_status=None) -> List[Dict[str, Any]]:
    """Fetch M1 candles in chunks of 1000 ending at successively earlier cursors.

    Sleeps 0.5s between requests to respect MetaApi rate limits. Each chunk is
    wrapped in its own timeout to detect SDK hangs."""
    all_candles: List[Dict[str, Any]] = []
    cursor = end_dt
    chunk_size = 1000
    chunk_idx = 0
    max_chunks = 300  # 300k candles safety cap
    seen_times = set()

    while cursor > start_dt and chunk_idx < max_chunks:
        chunk_idx += 1
        if on_status:
            await on_status(f"Téléchargement bougies M1 lot {chunk_idx}…", 0.0)

        # Fetch the chunk with up to 3 attempts and exponential backoff (1s, 2s, 4s)
        # to ride out transient MetaApi rate-limits (HTTP 429) without failing the run.
        chunk = None
        for attempt in range(3):
            try:
                chunk = await asyncio.wait_for(
                    metaapi_client.get_candles(symbol, "1m", cursor, chunk_size),
                    timeout=60.0,
                )
                break
            except asyncio.TimeoutError as e:
                raise CandleFetchTimeout(
                    f"MetaApi.get_candles timeout après 60s sur le lot #{chunk_idx} "
                    f"(cursor={cursor.isoformat()})"
                ) from e
            except Exception as e:
                wait = 2 ** attempt  # 1, 2, 4 seconds
                logger.warning("download_m1_history: lot %d échec (tentative %d/3): %s",
                               chunk_idx, attempt + 1, e)
                if attempt == 2:
                    raise
                if on_status:
                    await on_status(
                        f"Limite MetaApi atteinte — nouvelle tentative lot {chunk_idx} dans {wait}s…",
                        0.0,
                    )
                await asyncio.sleep(wait)

        if not chunk:
            logger.info("download_m1_history: lot %d vide, arrêt", chunk_idx)
            break

        # Normalize and deduplicate
        new_count = 0
        oldest_dt: Optional[datetime] = None
        for c in chunk:
            t = c.get("time") or c.get("brokerTime")
            tdt = _parse_dt(t)
            if not tdt:
                continue
            if oldest_dt is None or tdt < oldest_dt:
                oldest_dt = tdt
            key = tdt.isoformat()
            if key in seen_times:
                continue
            if tdt < start_dt or tdt > end_dt:
                continue
            seen_times.add(key)
            all_candles.append({
                "time": tdt.isoformat(),
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            })
            new_count += 1

        logger.info("download_m1_history: lot %d → %d nouvelles bougies (cursor=%s)",
                    chunk_idx, new_count, cursor.isoformat())

        if oldest_dt is None or oldest_dt >= cursor:
            # No progress this iteration — bail to avoid infinite loop
            logger.warning("download_m1_history: pas de progression (cursor inchangé), arrêt")
            break

        cursor = oldest_dt
        await asyncio.sleep(0.5)  # rate-limit cushion

    all_candles.sort(key=lambda x: x["time"])
    return all_candles
