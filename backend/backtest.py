"""Backtest engine — uses the SHARED SMC module to replay strategy on historical candles."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
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


async def run_backtest(req: Dict[str, Any], candles_m1: List[Dict],
                        on_progress=None, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Replay strategy on supplied M1 candles. Pure logic — no I/O."""
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
    spread_points = float(req.get("spread_points", 25))
    spread_price = spread_points * 0.01  # XAUUSD: 1 point ≈ 0.01

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
        htf_window = [h for h in htf_candles if h["time"] <= cur_time][-100:]
        mtf_window = [h for h in mtf_candles if h["time"] <= cur_time][-150:]
        ltf_window = ltf_candles[max(0, i - 200): i + 1]
        if len(htf_window) < 30 or len(mtf_window) < 30:
            continue

        if open_trade:
            _check_exit(open_trade, c, spread_price, trades, equity_curve)
            if open_trade.get("_closed"):
                equity = equity_curve[-1]["equity"]
                open_trade = None

        if open_trade:
            continue

        # Sessions: comme le bot live, on n'OUVRE de position que pendant Londres/NY.
        # (Les positions déjà ouvertes, elles, sont gérées 24h via SL/TP ci-dessus.)
        cdt = _parse_dt(cur_time)
        if cdt is not None and not sess.is_in_session(cdt, settings)["in_session"]:
            continue

        result = analyze(htf_window, mtf_window, ltf_window, fractal_n=fractal_n, min_rr=min_rr,
                         recent_window=recent_window, require_fvg=require_fvg,
                         require_sequence=require_sequence, require_unmitigated=require_unmitigated,
                         require_pd=require_pd)
        sig = result.get("signal")
        if sig:
            entry_price = sig["entry"] + (spread_price if sig["side"] == "buy" else -spread_price)
            open_trade = {
                "id": str(uuid.uuid4()),
                "side": sig["side"],
                "entry_time": _to_iso(c["time"]),
                "entry": entry_price,
                "sl": sig["sl"],
                "tp": sig["tp"],
                "rr": sig["rr"],
                "reason": sig["reason"],
                "exit_time": "",
                "exit_price": 0.0,
                "pnl": 0.0,
                "result": "be",
            }

    # Close any trade still open at the end of the period at the last candle's
    # close — otherwise it is silently omitted from the metrics (biasing winrate).
    if open_trade and not open_trade.get("_closed") and ltf_candles:
        last_c = ltf_candles[-1]
        side = open_trade["side"]
        exit_price = last_c["close"]
        # Spread already paid once via the worse entry fill — do not subtract again.
        pnl = (exit_price - open_trade["entry"]) if side == "buy" else (open_trade["entry"] - exit_price)
        result = "win" if pnl > 0 else ("loss" if pnl < 0 else "be")
        open_trade.update(exit_time=_to_iso(last_c["time"]), exit_price=exit_price,
                          pnl=pnl, result=result, _closed=True)
        trades.append({k: v for k, v in open_trade.items() if not k.startswith("_")})
        equity_curve.append({"time": _to_iso(last_c["time"]),
                             "equity": equity_curve[-1]["equity"] + pnl * 100})

    if on_progress:
        try:
            await on_progress(100.0)
        except Exception:
            pass

    metrics = _compute_metrics(trades, equity_curve)
    return {"trades": trades, "metrics": metrics, "equity_curve": equity_curve}


def _check_exit(trade: Dict[str, Any], c: Dict[str, Any], spread_price: float,
                trades: List[Dict[str, Any]], equity_curve: List[Dict[str, Any]]) -> None:
    """Mutate trade in place when SL/TP hit, append to trades + equity_curve."""
    side = trade["side"]
    entry = trade["entry"]
    sl, tp = trade["sl"], trade["tp"]
    hit_sl = (c["low"] <= sl) if side == "buy" else (c["high"] >= sl)
    hit_tp = (c["high"] >= tp) if side == "buy" else (c["low"] <= tp)
    if not (hit_sl or hit_tp):
        return
    if hit_sl:
        exit_price = sl
        result = "loss"
    else:
        exit_price = tp
        result = "win"
    # Spread is already paid once via the worse entry fill (entry_price adjusted at open),
    # which models the full round-trip cost — do NOT subtract it again here (double-counting).
    pnl = (exit_price - entry) if side == "buy" else (entry - exit_price)
    trade.update(exit_time=_to_iso(c["time"]), exit_price=exit_price, pnl=pnl, result=result, _closed=True)
    trades.append({k: v for k, v in trade.items() if not k.startswith("_")})
    last_eq = equity_curve[-1]["equity"] + pnl * 100
    equity_curve.append({"time": _to_iso(c["time"]), "equity": last_eq})


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
