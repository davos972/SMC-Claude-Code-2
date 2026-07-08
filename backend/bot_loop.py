"""GoldFlow SMC — Automatic trading loop.

Runs as a background asyncio task when the bot is started.
Checks every 30 seconds for a new candle close, runs SMC analysis,
enforces all protections, and places orders when conditions are met.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import news as news_engine
import sessions as sess
import store
from metaapi_client import MetaApiConnectionError, metaapi_client
from smc import analyze
from backtest import compute_trailing_sl  # logique de trailing partagée live + backtest

logger = logging.getLogger("goldflow.bot")

_bot_task: Optional[asyncio.Task] = None
_resume_task: Optional[asyncio.Task] = None  # auto-resume watcher (tracked so it can be cancelled)
_last_candle_time: Dict[str, str] = {}  # "symbol:timeframe" -> last seen ISO time
_open_positions: Dict[str, Dict] = {}   # position_id -> {equity_at_open, symbol, side}
_news_outage_active: bool = False       # True while the news calendar is unreachable
_watchdog_task: Optional[asyncio.Task] = None       # gardien de vivacité (tâche unique)
_last_heartbeat: Optional[datetime] = None          # pouls : dernier tour de boucle réussi (lecture compte OK)
_last_watchdog_notify: Optional[datetime] = None    # dernière notif du gardien (anti-spam)


def calc_lot_size(balance: float, risk_pct: float, entry: float, sl: float,
                  contract_size: float = 100.0, max_lot: float = 10.0) -> float:
    """Lot size for XAUUSD (100 oz per standard lot).
    Formula: lot = (balance * risk%) / (SL_distance * contract_size)
    Capped at `max_lot` to avoid over-leverage when the SL distance is tiny.
    """
    risk_dollars = balance * (risk_pct / 100.0)
    sl_distance = abs(entry - sl)
    if sl_distance <= 0:
        return 0.01
    lot = risk_dollars / (sl_distance * contract_size)
    return max(0.01, min(max_lot, round(lot * 100) / 100))


def _trading_day_key(now_utc: datetime, s: Dict) -> str:
    """Clé du « jour de trading » pour les resets quotidiens.

    Avec une prop firm à reset horaire (BlueGuardian : 17h00 EST), le jour bascule à
    cette heure dans le fuseau de New York. Sinon, jour calendaire UTC classique."""
    if s.get("prop_firm_enabled") and s.get("prop_daily_reset_hour_est") is not None:
        reset_h = int(s.get("prop_daily_reset_hour_est", 17))
        ny = now_utc.astimezone(sess.NEWYORK)
        d = ny.date()
        if ny.hour >= reset_h:  # après l'heure de reset → nouveau jour de trading
            d = d + timedelta(days=1)
        return d.isoformat()
    return now_utc.date().isoformat()


async def _notify(ntype: str, category: str, title: str, message: str) -> None:
    n = {
        "id": str(uuid.uuid4()),
        "type": ntype, "category": category,
        "title": title, "message": message,
        "time": datetime.now(timezone.utc).isoformat(),
        "read": False,
    }
    await store.add_notification(n)


async def auto_stop(reason: str, detail: str) -> None:
    """Stop the bot automatically with a reason."""
    stop_time = datetime.now(timezone.utc)
    await store.set_bot_state({
        "running": False,
        "stop_reason": reason,
        "last_status_change": stop_time.isoformat(),
    })
    titles = {
        "drawdown": "Bot arrêté — Drawdown max atteint",
        "consec_losses": "Bot arrêté — Pertes consécutives max",
    }
    await _notify("warning", "bot_stop", titles.get(reason, "Bot arrêté automatiquement"), detail)
    logger.info("Bot auto-stopped: %s — %s", reason, detail)
    global _resume_task
    if _resume_task and not _resume_task.done():
        _resume_task.cancel()
    _resume_task = asyncio.create_task(_auto_resume_watcher(stop_time))


async def _auto_resume_watcher(stop_time: datetime) -> None:
    """Wait for resume condition then restart the bot."""
    logger.info("Auto-resume watcher started (stopped at %s).", stop_time.isoformat())
    # Wait at least 2 minutes before checking (avoid immediate re-trigger)
    await asyncio.sleep(120)
    while True:
        await asyncio.sleep(30)
        try:
            state = await store.get_bot_state()
            # If someone manually restarted or stopped again, exit watcher
            if state.get("running") or state.get("stop_reason") is None:
                logger.info("Auto-resume watcher: manual change detected, exiting.")
                return

            s = await store.get_settings()
            resume_policy = s.get("resume_policy", "next_session")
            now = datetime.now(timezone.utc)

            should_resume = False
            if resume_policy == "next_day":
                should_resume = now.date() > stop_time.date()
            else:  # next_session (default)
                session_info = sess.is_in_session(now, s)
                should_resume = session_info.get("in_session", False)

            if not should_resume:
                continue

            # Resume: reset counters, snapshot equity, restart loop
            try:
                account_info = await metaapi_client.get_account_information()
                equity = float(account_info.get("equity", 0))
            except Exception:
                equity = 0.0

            await store.set_bot_state({
                "running": True,
                "stop_reason": None,
                "consec_losses": 0,
                "current_day": now.date().isoformat(),
                "trades_today": 0,
                "day_start_equity": equity,
                "session_start_equity": equity,
                "last_status_change": now.isoformat(),
            })
            start(equity)
            await _notify("success", "bot_resume", "Bot repris automatiquement",
                          f"Equity de référence : {equity:.2f}")
            logger.info("Bot auto-resumed (policy=%s, equity=%.2f).", resume_policy, equity)
            return
        except Exception as e:
            logger.warning("Auto-resume watcher error: %s", e)


async def _close_all_bot_positions(magic_number: int, reason: str = "news") -> None:
    """Close all open positions belonging to this bot (matching magic number)."""
    try:
        positions = await metaapi_client.get_positions()
        bot_pos = [p for p in positions if int(p.get("magic", 0)) == magic_number]
        for p in bot_pos:
            try:
                await metaapi_client.close_position(str(p.get("id", "")))
                logger.info("Closed position %s (reason: %s)", p.get("id"), reason)
            except Exception as e:
                logger.warning("Failed to close position %s: %s", p.get("id"), e)
        if bot_pos:
            await _notify("info", "close_trade", "Positions fermées automatiquement",
                          f"Motif : {reason} ({len(bot_pos)} position(s))")
    except Exception as e:
        logger.warning("_close_all_bot_positions failed: %s", e)


async def _realized_pnl(position_id: str) -> Optional[float]:
    """Real realized P&L of a closed position from the broker's deal history
    (profit + swap + commission). Returns None if the history is unavailable, so
    the caller can fall back to the (mono-symbol-only) equity-delta estimate."""
    try:
        deals = await metaapi_client.get_deals_by_position(position_id)
    except Exception as e:
        logger.warning("get_deals_by_position(%s) failed: %s", position_id, e)
        return None
    if not deals:
        return None
    total = 0.0
    for d in deals:
        total += float(d.get("profit", 0) or 0)
        total += float(d.get("swap", 0) or 0)
        total += float(d.get("commission", 0) or 0)
    return total


async def _check_closed_positions(current_equity: float, magic_number: int) -> None:
    """Detect positions closed since last check and update consecutive loss counter."""
    global _open_positions
    try:
        positions = await metaapi_client.get_positions()
        current_ids = {str(p.get("id", "")) for p in positions
                       if int(p.get("magic", 0)) == magic_number}
        closed_ids = set(_open_positions.keys()) - current_ids
        for pos_id in closed_ids:
            tracked = _open_positions.pop(pos_id, {})
            if not tracked:
                continue
            equity_at_open = tracked.get("equity_at_open", current_equity)
            symbol = tracked.get("symbol", "")
            # Prefer the broker's REAL realized P&L for this exact position. The global
            # equity delta only approximates it with a single open position at a time and
            # becomes wrong with several symbols open at once — so it's only a fallback.
            delta = await _realized_pnl(pos_id)
            if delta is None:
                delta = current_equity - equity_at_open
            be_threshold = equity_at_open * 0.001  # 0.1% = break-even

            state = await store.get_bot_state()
            consec = state.get("consec_losses", 0)

            if delta >= -be_threshold:
                # Win or break-even — break-even does NOT count as a loss
                await store.set_bot_state({"consec_losses": 0})
                label = f"Gain +${delta:.2f}" if delta > be_threshold else "Break-even"
                await _notify("success", "close_trade", f"Trade fermé {symbol}", label)
            else:
                # Loss
                consec += 1
                await store.set_bot_state({"consec_losses": consec})
                await _notify("warning", "close_trade", f"Trade fermé {symbol}",
                              f"Perte −${abs(delta):.2f} · {consec} perte(s) consécutive(s)")
    except Exception as e:
        logger.warning("_check_closed_positions failed: %s", e)


async def _apply_trailing(s: Dict, magic_number: int) -> None:
    """Trailing stop LIVE : resserre le SL des positions du bot CHEZ LE BROKER.
    Même logique que le backtest (compute_trailing_sl). Tourne à chaque tour (~30 s),
    y compris hors session (les positions restent gérées 24 h). OFF par défaut."""
    mode = s.get("trailing_mode", "off")
    if mode == "off" or not _open_positions:
        return
    params = {
        "mode": mode,
        "trigger_r": float(s.get("trailing_trigger_r", 1.0)),
        "distance_r": float(s.get("trailing_distance_r", 1.0)),
        "lookback": int(s.get("trailing_lookback", 5)),
        "buffer": float(s.get("trailing_buffer", 0.0)),
    }
    ltf = (s.get("scalping_ltf", "M1") if s.get("trading_mode") == "scalping"
           else s.get("intraday_ltf", "M5"))
    try:
        positions = await metaapi_client.get_positions()
    except MetaApiConnectionError as e:
        logger.warning("Trailing: lecture positions échouée: %s", e)
        return
    for p in positions:
        if int(p.get("magic", 0)) != magic_number:
            continue
        pid = str(p.get("id", ""))
        tr = _open_positions.get(pid)
        if not tr or tr.get("R", 0) <= 0:
            continue
        try:
            candles = await metaapi_client.get_candles(tr["symbol"], ltf, None,
                                                       max(params["lookback"] + 2, 5))
        except MetaApiConnectionError as e:
            logger.warning("Trailing: bougies %s indisponibles: %s", tr["symbol"], e)
            continue
        if not candles:
            continue
        last = candles[-1]
        recent = candles[-params["lookback"]:]
        new_sl, tr["max_fav"] = compute_trailing_sl(
            tr["side"], tr["entry"], tr["sl"], tr["R"], tr["max_fav"],
            float(last["high"]), float(last["low"]), float(last["close"]),
            [float(c["low"]) for c in recent], [float(c["high"]) for c in recent], params)
        if new_sl is None:
            continue
        try:
            await metaapi_client.modify_position(pid, new_sl, tr["tp"])
            logger.info("Trailing %s: SL %.5f -> %.5f (pos %s)", mode, tr["sl"], new_sl, pid)
            tr["sl"] = new_sl
        except MetaApiConnectionError as e:
            logger.warning("Trailing: modify_position(%s) échec: %s", pid, e)


async def _bot_trading_loop() -> None:
    """Main loop: every 30 s, check for new candle close and run analysis."""
    global _last_heartbeat
    logger.info("Trading loop started.")
    while True:
        await asyncio.sleep(30)
        try:
            state = await store.get_bot_state()
            if not state.get("running"):
                logger.info("Bot stopped — trading loop exiting.")
                break

            s = await store.get_settings()
            now = datetime.now(timezone.utc)
            symbol = s.get("active_symbol", "XAUUSD")
            mode = s.get("trading_mode", "intraday")
            htf = s.get("intraday_htf" if mode == "intraday" else "scalping_htf", "H1")
            mtf = s.get("intraday_mtf" if mode == "intraday" else "scalping_mtf", "M15")
            ltf = s.get("intraday_ltf" if mode == "intraday" else "scalping_ltf", "M5")
            magic = int(s.get("magic_number", 990077))

            # ── Account info (needed for drawdown check and lot calc) ──
            try:
                account_info = await metaapi_client.get_account_information()
                equity = float(account_info.get("equity", 0))
                balance = float(account_info.get("balance", 0))
                # Pouls du gardien : arriver ici prouve que la boucle tourne ET que MetaApi répond.
                _last_heartbeat = datetime.now(timezone.utc)
            except MetaApiConnectionError as e:
                logger.warning("Cannot get account info: %s", e)
                continue

            # ── Daily rollover: reset trades_today / day_start_equity at a new UTC day ──
            # Sans ce reset, max_trades_per_day devient un plafond cumulatif et le
            # drawdown « du jour » est calculé contre une équité périmée.
            today_str = _trading_day_key(now, s)
            if state.get("current_day") != today_str:
                # Repère journalier prop = le PLUS HAUT entre solde et équité (règle BlueGuardian).
                day_ref = max(equity, balance)
                # High watermark trailing = plus haut solde de fin de journée vu jusqu'ici.
                prop_initial = float(s.get("prop_initial_balance", balance) or balance)
                hwm = max(float(state.get("prop_hwm_balance", 0) or 0), balance, prop_initial)
                await store.set_bot_state({
                    "current_day": today_str,
                    "trades_today": 0,
                    "day_start_equity": equity,
                    "day_start_ref": day_ref,
                    "session_start_equity": equity,
                    "prop_hwm_balance": hwm,
                })
                state["current_day"] = today_str
                state["trades_today"] = 0
                state["day_start_equity"] = equity
                state["day_start_ref"] = day_ref
                state["session_start_equity"] = equity
                state["prop_hwm_balance"] = hwm
                logger.info("Nouveau jour %s — compteurs réinitialisés (equity=%.2f, ref=%.2f, hwm=%.2f).",
                            today_str, equity, day_ref, hwm)

            # ── Check for position closes (update consec_losses) ──
            await _check_closed_positions(equity, magic)
            state = await store.get_bot_state()  # reload after update

            # ── Trailing stop live : gère les positions ouvertes du bot (même hors session) ──
            await _apply_trailing(s, magic)

            # ── Session check ──
            session_info = sess.is_in_session(now, s)
            if not session_info["in_session"]:
                continue

            # ── News pause check ──
            if s.get("news_filter_enabled", True):
                global _news_outage_active
                try:
                    news_data = await news_engine.fetch_calendar()
                except Exception as e:
                    news_data = {"events": [], "error": str(e)}
                if news_data.get("error"):
                    # Conservative behaviour: we cannot verify upcoming high-impact news,
                    # so we skip new entries until the calendar is reachable again.
                    if not _news_outage_active:
                        _news_outage_active = True
                        await _notify("warning", "bot_stop", "Filtre news indisponible",
                                      "Calendrier économique inaccessible — le bot suspend les "
                                      "nouvelles entrées par sécurité jusqu'au rétablissement.")
                    logger.warning("Filtre news indisponible (%s) — pause conservatrice.",
                                   news_data.get("error"))
                    continue
                if _news_outage_active:
                    _news_outage_active = False
                    await _notify("info", "bot_stop", "Filtre news rétabli",
                                  "Le calendrier économique est de nouveau accessible.")
                in_pause = news_engine.is_in_news_pause(
                    news_data.get("events", []),
                    int(s.get("news_minutes_before", 30)),
                    int(s.get("news_minutes_after", 30)),
                )
                if in_pause:
                    if s.get("close_positions_before_news", False):
                        await _close_all_bot_positions(magic, reason="annonce news imminente")
                    continue

            # ── Drawdown / prop firm checks ──
            day_start_eq = state.get("day_start_equity") or equity
            if s.get("prop_firm_enabled"):
                prop_initial = float(s.get("prop_initial_balance", balance) or balance)
                safety = float(s.get("prop_safety_margin_pct", 20.0)) / 100.0

                # (1) GUARDIAN SHIELD — perte FLOTTANTE des positions ouvertes.
                # On ferme NOUS-MÊMES, avec marge, AVANT que la prop ne déclenche son shield
                # (chez BlueGuardian, un déclenchement = soft breach → split 50 %, et 2e = compte résilié).
                gs_pct = float(s.get("prop_guardian_shield_pct", 0.0) or 0.0)
                if gs_pct > 0:
                    try:
                        positions = await metaapi_client.get_positions()
                        floating = sum(
                            float(p.get("unrealizedProfit", p.get("profit", 0)) or 0)
                            for p in positions if int(p.get("magic", 0)) == magic)
                    except MetaApiConnectionError:
                        floating = 0.0
                    gs_limit = prop_initial * gs_pct / 100.0     # ex. 1% de 25000 = 250 $
                    gs_trigger = gs_limit * (1 - safety)         # ferme à 0,8% = 200 $
                    if floating <= -gs_trigger:
                        await _close_all_bot_positions(
                            magic,
                            reason=(f"Guardian Shield préventif : perte flottante {floating:.0f}$ "
                                    f"≥ seuil sécurité {gs_trigger:.0f}$ (limite prop {gs_limit:.0f}$)"))
                        continue  # soft : on ne stoppe pas le bot, on protège juste la position

                # (2) PERTE JOURNALIÈRE — repère = plus haut solde/équité au reset (17h EST).
                daily_room = prop_initial * float(s.get("prop_daily_dd_pct", 3.0)) / 100.0
                day_ref = float(state.get("day_start_ref") or day_start_eq or equity)
                daily_loss = day_ref - equity
                if daily_loss >= daily_room * (1 - safety):
                    await auto_stop("drawdown",
                        f"Prop : perte du jour {daily_loss:.0f}$ approche la limite "
                        f"{daily_room:.0f}$ ({s.get('prop_daily_dd_pct')}% de {prop_initial:.0f}$).")
                    break

                # (3) DRAWDOWN MAX — trailing (sur high watermark) ou statique.
                total_room = prop_initial * float(s.get("prop_total_dd_pct", 6.0)) / 100.0
                hwm = float(state.get("prop_hwm_balance") or prop_initial)
                if s.get("prop_trailing_dd"):
                    lock_at = prop_initial * (1 + float(s.get("prop_trailing_lock_profit_pct", 6.0)) / 100.0)
                    floor = prop_initial if hwm >= lock_at else (hwm - total_room)
                else:
                    floor = prop_initial - total_room
                if equity <= floor + total_room * safety:
                    await auto_stop("drawdown",
                        f"Prop : équité {equity:.0f}$ approche le drawdown max "
                        f"(plancher {floor:.0f}$, marge sécurité incluse).")
                    break
            else:
                max_dd = float(s.get("max_drawdown_pct", 3.0))
                if day_start_eq > 0:
                    dd = (day_start_eq - equity) / day_start_eq * 100
                    if dd >= max_dd:
                        await auto_stop("drawdown", f"Drawdown {dd:.1f}% ≥ limite {max_dd}%")
                        break

            # ── Consecutive losses check ──
            consec = state.get("consec_losses", 0)
            max_losses = int(s.get("max_consec_losses", 3))
            if consec >= max_losses:
                await auto_stop("consec_losses",
                    f"{consec} pertes consécutives. Reprise : {s.get('resume_policy', 'next_session')}.")
                break

            # ── Max trades per day check ──
            trades_today = state.get("trades_today", 0)
            if trades_today >= int(s.get("max_trades_per_day", 5)):
                continue

            # ── One position per symbol check ──
            try:
                positions = await metaapi_client.get_positions()
                bot_pos = [p for p in positions
                           if p.get("symbol") == symbol and int(p.get("magic", 0)) == magic]
                if bot_pos:
                    continue
            except MetaApiConnectionError:
                continue

            # ── New candle close detection ──
            try:
                ltf_raw = await metaapi_client.get_candles(symbol, ltf, None, 300)
                if not ltf_raw:
                    continue
                last_t = ltf_raw[-1].get("time")
                if hasattr(last_t, "isoformat"):
                    last_t = last_t.isoformat()
                last_t = str(last_t)
                key = f"{symbol}:{ltf}"
                if _last_candle_time.get(key) == last_t:
                    continue  # No new candle since last check
                _last_candle_time[key] = last_t
                logger.info("New %s candle at %s — running SMC analysis", ltf, last_t)
            except MetaApiConnectionError as e:
                logger.warning("Candle fetch failed: %s", e)
                continue

            # ── SMC analysis (top-down 3 niveaux) ──
            try:
                htf_raw = await metaapi_client.get_candles(symbol, htf, None, 300)
                mtf_raw = await metaapi_client.get_candles(symbol, mtf, None, 300)

                def _norm(arr):
                    out = []
                    for c in arr:
                        t = c.get("time")
                        if hasattr(t, "isoformat"):
                            t = t.isoformat()
                        out.append({"time": str(t), "open": float(c["open"]),
                                    "high": float(c["high"]), "low": float(c["low"]),
                                    "close": float(c["close"])})
                    return out

                result = analyze(_norm(htf_raw), _norm(mtf_raw), _norm(ltf_raw),
                                 fractal_n=int(s.get("fractal_n", 3)),
                                 min_rr=float(s.get("min_rr", 2.0)),
                                 recent_window=int(s.get("recent_window", 6)),
                                 require_fvg=bool(s.get("require_fvg_entry", True)),
                                 require_sequence=bool(s.get("require_sweep_then_choch", True)),
                                 require_unmitigated=bool(s.get("require_unmitigated_ob", True)))
            except Exception as e:
                logger.warning("SMC analysis failed: %s", e)
                continue

            sig = result.get("signal")
            reject_reason = result.get("reject_reason", "Setup invalide")

            # ── Persist to signal journal ──
            rec = {
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "timeframe": ltf,
                "side": sig["side"] if sig else "buy",
                # Direction du setup (biais HTF) — sert à afficher Haussier/Baissier même sur un rejet.
                "bias": result.get("bias"),
                "status": "rejected",
                "reason": sig["reason"] if sig else reject_reason,
                "rr": sig["rr"] if sig else None,
                "entry": sig["entry"] if sig else None,
                "sl": sig["sl"] if sig else None,
                "tp": sig["tp"] if sig else None,
                "time": now.isoformat(),
                "session": session_info.get("session", "unknown"),
            }

            if not sig:
                # En temps normal on ne journalise QUE les vrais quasi-setups (stade "near_miss" :
                # prix DANS la POI + bonne zone, seul le déclencheur/RR manquait). Les minutes
                # "pas de biais / pas de POI / prix mal placé" sont du bruit (la cause des
                # centaines de lignes/jour) → ignorées. Le mode DIAGNOSTIC (verbose_journal)
                # journalise AUSSI ces rejets précoces pour comprendre pourquoi des setups sont
                # écartés. Dans les deux cas, les rejets de même nature consécutifs sont regroupés.
                stage = result.get("reject_stage")
                if stage == "near_miss" or (s.get("verbose_journal", False) and stage):
                    rec["reject_stage"] = stage
                    # Clé de regroupement : stade + raison aux nombres neutralisés (ex.
                    # "RR 1.85 < min 2.0" → "RR N < min N") pour fusionner les variantes.
                    # On inclut la direction dans la clé → les rejets haussiers et baissiers de même
                    # raison forment deux groupes distincts, chacun affichant sa bonne direction.
                    rec["reason_key"] = f"{stage}|{rec.get('bias')}|" + re.sub(r"[-+]?[0-9]*\.?[0-9]+", "N", rec["reason"] or "")
                    await store.add_or_merge_signal(rec)
                continue

            # ── Signal-only mode ──
            if s.get("signal_only_mode", True):
                rec["status"] = "accepted"
                await store.add_signal(rec)
                await _notify("info", "open_trade",
                              f"Signal {sig['side'].upper()} {symbol}",
                              sig["reason"])
                continue

            # ── Execute trade ──
            try:
                risk_pct = float(s.get("risk_per_trade_pct", 1.0))
                # Sur compte prop avec Guardian Shield : on plafonne le risque par trade SOUS
                # le seuil shield (avec marge) pour qu'un SL ne puisse jamais le déclencher.
                if s.get("prop_firm_enabled"):
                    gs_pct = float(s.get("prop_guardian_shield_pct", 0.0) or 0.0)
                    if gs_pct > 0:
                        risk_cap = gs_pct * (1 - float(s.get("prop_safety_margin_pct", 20.0)) / 100.0)
                        if risk_pct > risk_cap:
                            logger.info("Risque plafonné %.2f%% → %.2f%% (Guardian Shield).",
                                        risk_pct, risk_cap)
                            risk_pct = risk_cap
                # Taille de contrat RÉELLE du symbole (100 oz pour l'or, 1 pour
                # les indices) — indispensable pour que le risque % soit correct
                # sur autre chose que XAUUSD. Lue en live via MetaApi (cache).
                try:
                    spec = await metaapi_client.get_symbol_spec(symbol)
                    contract_size = float(spec.get("contract_size", 100.0))
                except Exception as e:
                    logger.warning("get_symbol_spec(%s) échec, contrat=100 par défaut: %s", symbol, e)
                    contract_size = 100.0
                lot = calc_lot_size(balance, risk_pct,
                                    float(sig["entry"]), float(sig["sl"]),
                                    contract_size=contract_size,
                                    max_lot=float(s.get("max_lot_per_trade", 10.0)))
                order = await metaapi_client.place_order(
                    symbol=symbol, side=sig["side"], volume=lot,
                    sl=float(sig["sl"]), tp=float(sig["tp"]),
                    magic=magic, comment=str(s.get("order_comment_tag", "GFSMC")),
                )
                rec["status"] = "executed"
                await store.add_signal(rec)
                await store.set_bot_state({"trades_today": trades_today + 1})

                # Track position for win/loss detection.
                # Use the broker's real position id (matches get_positions()[].id).
                # NEVER fall back to a random UUID: it would never match a live
                # position and would be counted as an instant (false) win/loss.
                pos_id = str(order.get("positionId") or order.get("position_id") or "")
                if not pos_id:
                    # Fallback: re-fetch positions and grab the one we just opened.
                    try:
                        positions = await metaapi_client.get_positions()
                        mine = [p for p in positions
                                if p.get("symbol") == symbol and int(p.get("magic", 0)) == magic]
                        if mine:
                            pos_id = str(mine[-1].get("id", ""))
                    except Exception as e:
                        logger.warning("Re-fetch positions for tracking failed: %s", e)
                if pos_id:
                    _open_positions[pos_id] = {
                        "equity_at_open": equity,
                        "symbol": symbol,
                        "side": sig["side"],
                        # Suivi pour le trailing stop live (SL modifié chez le broker).
                        "entry": float(sig["entry"]),
                        "sl": float(sig["sl"]),
                        "tp": float(sig["tp"]),
                        "R": abs(float(sig["entry"]) - float(sig["sl"])),
                        "max_fav": float(sig["entry"]),
                    }
                else:
                    logger.error("Ordre placé sans identifiant de position exploitable — "
                                 "suivi gain/perte ignoré pour ce trade. Réponse: %s", order)
                    await _notify("warning", "open_trade", "Suivi P&L indisponible",
                                  "Ordre placé mais MetaApi n'a pas renvoyé d'identifiant de "
                                  "position : le comptage gain/perte de ce trade est ignoré.")
                await _notify("success", "open_trade",
                              f"Trade {sig['side'].upper()} {symbol}",
                              f"{lot} lot · SL {sig['sl']:.2f} · TP {sig['tp']:.2f} · RR 1:{sig['rr']:.2f}")
            except Exception as e:
                logger.error("Order placement failed: %s", e)
                rec["status"] = "rejected"
                rec["reason"] = f"Erreur placement : {e}"
                await store.add_signal(rec)
                await _notify("error", "open_trade", "Erreur placement d'ordre", str(e)[:200])

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Unexpected bot loop error: %s", e)

    logger.info("Trading loop ended.")


def start(day_start_equity: float = 0.0) -> None:
    """Start the trading loop. Call from bot_start() endpoint."""
    global _bot_task, _open_positions, _last_heartbeat
    _open_positions = {}
    _last_heartbeat = datetime.now(timezone.utc)  # période de grâce avant le 1er pouls réel
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
    _bot_task = asyncio.create_task(_bot_trading_loop())
    logger.info("Trading loop task created (day_start_equity=%.2f).", day_start_equity)


def stop() -> None:
    """Cancel the trading loop task. Call from bot_stop() endpoint."""
    global _bot_task, _resume_task
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
    _bot_task = None
    # Also cancel any pending auto-resume watcher so a manual stop stays stopped.
    if _resume_task and not _resume_task.done():
        _resume_task.cancel()


# ─────────────────────────── Gardien de vivacité ───────────────────────────
# Relance la boucle si elle cesse de « battre » — qu'elle soit morte OU vivante
# mais bloquée sur une connexion MetaApi coincée (cas vécu 2026-07-08 : boucle
# figée ~2 jours, current_day périmé, bot affiché « running » mais idle). Comble
# le trou de l'auto-reprise au démarrage (qui, elle, ne couvre que le
# redémarrage du serveur). Voir DECISIONS.md.
_WATCHDOG_INTERVAL_S = 60      # fréquence de vérification du pouls
_WATCHDOG_STALE_S = 300        # pouls périmé > 5 min = boucle figée (> reconnexion à froid ~4 min → pas de fausse alerte)
_WATCHDOG_NOTIFY_GAP_S = 900   # anti-spam : au plus 1 notif / 15 min pendant une panne prolongée


async def _watchdog_check_once(now: datetime, stale_after_s: int = _WATCHDOG_STALE_S) -> bool:
    """Un tour de vérification du gardien. Renvoie True si la boucle a été relancée.

    Ne relance QUE si le bot est censé tourner (running=true) ET que le pouls est
    périmé. Un arrêt manuel (running=false) est donc respecté."""
    global _last_watchdog_notify
    state = await store.get_bot_state()
    if not state.get("running"):
        return False
    hb = _last_heartbeat
    if hb is not None and (now - hb).total_seconds() < stale_after_s:
        return False  # pouls frais → rien à faire
    age = (now - hb).total_seconds() if hb else -1
    logger.warning("Gardien : boucle figée (pouls périmé, %.0fs) — reconnexion MetaApi + relance.", age)
    # 1. Couper la boucle figée et attendre sa fin (libère tout verrou de connexion tenu).
    old = _bot_task
    if old is not None and not old.done():
        old.cancel()
        try:
            await old
        except (asyncio.CancelledError, Exception):
            pass
    # 2. Reconnexion MetaApi à neuf.
    try:
        await metaapi_client.force_reconnect()
    except Exception:
        logger.exception("Gardien : force_reconnect a échoué (relance de la boucle quand même).")
    # 3. Relance de la boucle (réinitialise aussi le pouls → période de grâce).
    start(day_start_equity=float(state.get("day_start_equity", 0) or 0))
    if _last_watchdog_notify is None or (now - _last_watchdog_notify).total_seconds() >= _WATCHDOG_NOTIFY_GAP_S:
        _last_watchdog_notify = now
        await _notify("warning", "bot_resume", "Bot relancé automatiquement",
                      "La boucle de trading était figée : reconnexion MetaApi et relance par le gardien.")
    return True


async def _liveness_watchdog() -> None:
    logger.info("Gardien de vivacité démarré (seuil %ds, vérif toutes les %ds).",
                _WATCHDOG_STALE_S, _WATCHDOG_INTERVAL_S)
    while True:
        await asyncio.sleep(_WATCHDOG_INTERVAL_S)
        try:
            await _watchdog_check_once(datetime.now(timezone.utc))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Gardien : erreur inattendue (on continue).")


def start_watchdog() -> None:
    """Lance le gardien de vivacité (tâche unique). Appelé au démarrage du serveur."""
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        return
    _watchdog_task = asyncio.create_task(_liveness_watchdog())


def stop_watchdog() -> None:
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
    _watchdog_task = None
    _resume_task = None
