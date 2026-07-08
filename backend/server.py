"""GoldFlow SMC — FastAPI backend.

Phase 1+2 MVP: settings, MetaApi connection (with degraded mode), SMC signal engine,
journal des signaux, notifications, backtest, news (Forex Factory), risk preview,
sessions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import backtest as bt_engine  # noqa: E402
import bot_loop  # noqa: E402
import news as news_engine  # noqa: E402
import sessions as sess  # noqa: E402
import store  # noqa: E402
from metaapi_client import (  # noqa: E402
    MetaApiConnectionError,
    MetaApiNotConfiguredError,
    metaapi_client,
)
from smc import analyze  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("goldflow")


app = FastAPI(title="GoldFlow SMC")
api = APIRouter(prefix="/api")


# ---------------- bootstrap ----------------

@app.on_event("startup")
async def _on_startup() -> None:
    s = await store.get_settings()
    # Use env vars as fallback when DB has no credentials (e.g. fresh deploy after reset)
    token = s.get("metaapi_token") or os.environ.get("METAAPI_TOKEN", "")
    account_id = s.get("metaapi_account_id") or os.environ.get("METAAPI_ACCOUNT_ID", "")
    if token and account_id:
        try:
            await metaapi_client.configure(token, account_id)
        except Exception as e:
            logger.warning("MetaApi configure failed: %s", e)
    # Recover orphaned backtests (running/pending from a previous process)
    try:
        from store import get_db
        db = get_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        n = await db.backtests.update_many(
            {"status": {"$in": ["running", "pending"]}},
            {"$set": {
                "status": "error",
                "error": "Backtest interrompu (redémarrage du serveur).",
                "finished_at": now_iso,
            }},
        )
        if n.modified_count:
            logger.info("Recovered %d orphan backtests as error.", n.modified_count)
    except Exception:
        logger.exception("Orphan backtest recovery failed")

    # Auto-reprise du bot après un redémarrage du serveur (déploiement Render
    # OU redémarrage spontané de la plateforme). Sans ceci, la boucle de trading
    # ne redémarre jamais alors que la base indique toujours running=true : le
    # bot affiche « en marche » mais ne trade plus, sans alerte. On relance la
    # boucle dès que l'état persisté dit qu'elle doit tourner ET que MetaApi est
    # configuré. La boucle tolère une connexion MetaApi encore indisponible (elle
    # se reconnecte toute seule au tour suivant).
    try:
        bstate = await store.get_bot_state()
        if bstate.get("running") and metaapi_client.is_configured():
            bot_loop.start(day_start_equity=float(bstate.get("day_start_equity", 0) or 0))
            logger.info("Bot en marche détecté au démarrage — boucle de trading "
                        "relancée automatiquement.")
    except Exception:
        logger.exception("Auto-reprise du bot au démarrage échouée")

    # Gardien de vivacité : relance la boucle si elle cesse de battre (morte OU
    # bloquée sur une connexion MetaApi coincée), même sans redémarrage serveur.
    try:
        bot_loop.start_watchdog()
    except Exception:
        logger.exception("Démarrage du gardien de vivacité échoué")


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    await metaapi_client.disconnect()


# ---------------- root ----------------

@api.get("/")
async def root() -> Dict[str, str]:
    return {"app": "GoldFlow SMC", "status": "ok"}


@api.get("/health")
async def health() -> Dict[str, Any]:
    s = await store.get_settings()
    state = await store.get_bot_state()
    return {
        "ok": True,
        "configured": metaapi_client.is_configured(),
        "metaapi": metaapi_client.get_status(),
        "bot": {"running": state.get("running", False), "stop_reason": state.get("stop_reason")},
        "signal_only_mode": s.get("signal_only_mode", True),
    }


# ---------------- settings ----------------

class SettingsPayload(BaseModel):
    updates: Dict[str, Any]


@api.get("/settings")
async def get_settings() -> Dict[str, Any]:
    s = await store.get_settings()
    # mask token
    if s.get("metaapi_token"):
        s["metaapi_token_masked"] = "•" * 8 + s["metaapi_token"][-4:]
    s.pop("metaapi_token", None)
    return s


@api.put("/settings")
async def put_settings(payload: SettingsPayload) -> Dict[str, Any]:
    updates = payload.updates or {}
    # Validation guardrails
    if "account_type" in updates and updates["account_type"] == "real":
        if not updates.get("real_confirmed"):
            raise HTTPException(status_code=400, detail="Le passage en compte réel nécessite real_confirmed=true.")
    # Don't store empty token (avoid wiping)
    if "metaapi_token" in updates and not updates["metaapi_token"]:
        updates.pop("metaapi_token")
    new_settings = await store.update_settings(updates)
    # Reconfigure MetaApi if creds changed
    if updates.get("metaapi_token") or updates.get("metaapi_account_id"):
        token = new_settings.get("metaapi_token") or ""
        acc = new_settings.get("metaapi_account_id") or ""
        if token and acc:
            await metaapi_client.configure(token, acc)
    # Return masked
    new_settings.pop("metaapi_token", None)
    return new_settings


# ---------------- metaapi status ----------------

@api.get("/metaapi/status")
async def metaapi_status() -> Dict[str, Any]:
    return metaapi_client.get_status()


@api.post("/metaapi/test-connection")
async def metaapi_test_connection() -> Dict[str, Any]:
    if not metaapi_client.is_configured():
        return {"ok": False, "configured": False, "error": "MetaApi non configuré."}
    try:
        info = await metaapi_client.get_account_information()
        return {"ok": True, "configured": True, "account": info}
    except MetaApiConnectionError as e:
        return {"ok": False, "configured": True, "error": str(e)}
    except Exception as e:
        return {"ok": False, "configured": True, "error": str(e)}


# ---------------- account / positions / prices ----------------

@api.get("/account")
async def get_account() -> Dict[str, Any]:
    if not metaapi_client.is_configured():
        return {"configured": False, "error": "MetaApi non configuré."}
    try:
        info = await metaapi_client.get_account_information()
        return {"configured": True, "data": info}
    except MetaApiConnectionError as e:
        return {"configured": True, "error": str(e)}


@api.get("/positions")
async def get_positions() -> Dict[str, Any]:
    if not metaapi_client.is_configured():
        return {"configured": False, "data": []}
    try:
        positions = await metaapi_client.get_positions()
        return {"configured": True, "data": positions}
    except MetaApiConnectionError as e:
        return {"configured": True, "data": [], "error": str(e)}


@api.post("/positions/{position_id}/close")
async def close_position(position_id: str) -> Dict[str, Any]:
    """Emergency close a position by ID."""
    if not metaapi_client.is_configured():
        raise HTTPException(status_code=400, detail="MetaApi non configuré.")
    try:
        result = await metaapi_client.close_position(position_id)
        return {"ok": True, "result": result}
    except MetaApiConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api.get("/price/{symbol}")
async def get_price(symbol: str) -> Dict[str, Any]:
    if not metaapi_client.is_configured():
        return {"configured": False, "error": "MetaApi non configuré."}
    try:
        p = await metaapi_client.get_symbol_price(symbol)
        return {"configured": True, "data": p}
    except MetaApiConnectionError as e:
        return {"configured": True, "error": str(e)}


@api.get("/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "M5", limit: int = 200) -> Dict[str, Any]:
    if not metaapi_client.is_configured():
        return {"configured": False, "data": []}
    try:
        candles = await metaapi_client.get_candles(symbol, timeframe, None, min(limit, 1000))
        # Convert datetime objects to ISO strings for JSON
        out = []
        for c in candles:
            t = c.get("time")
            if hasattr(t, "isoformat"):
                t = t.isoformat()
            out.append({
                "time": t,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            })
        return {"configured": True, "data": out}
    except MetaApiConnectionError as e:
        return {"configured": True, "data": [], "error": str(e)}
    except Exception as e:
        logger.exception("get_candles failed")
        return {"configured": True, "data": [], "error": f"{type(e).__name__}: {e}"}


@api.get("/symbol/spec")
async def get_symbol_spec(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """Per-symbol contract specs (point size, contract size) read live from MetaApi.
    Used by the UI to display what the backtest/lot calc will apply for a symbol."""
    if not metaapi_client.is_configured():
        return {"configured": False}
    try:
        spec = await metaapi_client.get_symbol_spec(symbol)
    except MetaApiConnectionError as e:
        return {"configured": True, "error": str(e)}
    except Exception as e:
        logger.exception("get_symbol_spec failed")
        return {"configured": True, "error": f"{type(e).__name__}: {e}"}
    return {"configured": True, "symbol": symbol, **spec}


@api.get("/symbol/spread")
async def get_symbol_spread(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """Live spread (ask − bid) from the connected broker account, used as a realistic
    default for the backtest 'spread moyen simulé'. Points = prix / tickSize du symbole."""
    if not metaapi_client.is_configured():
        return {"configured": False}
    try:
        price = await metaapi_client.get_symbol_price(symbol)
        spec = await metaapi_client.get_symbol_spec(symbol)
    except MetaApiConnectionError as e:
        return {"configured": True, "error": str(e)}
    except Exception as e:
        logger.exception("get_symbol_spread failed")
        return {"configured": True, "error": f"{type(e).__name__}: {e}"}
    bid = float(price.get("bid", 0) or 0)
    ask = float(price.get("ask", 0) or 0)
    spread_price = max(0.0, ask - bid)
    point_size = float(spec.get("point_size", 0.01)) or 0.01
    return {
        "configured": True, "symbol": symbol, "bid": bid, "ask": ask,
        "spread_price": round(spread_price, 3),
        "spread_points": round(spread_price / point_size, 1),
        "point_size": point_size,
    }


# ---------------- bot start/stop ----------------

class BotStartPayload(BaseModel):
    pass


@api.post("/bot/start")
async def bot_start() -> Dict[str, Any]:
    s = await store.get_settings()
    if not metaapi_client.is_configured():
        await store.set_bot_state({"running": False, "stop_reason": "no_metaapi"})
        await _notify("warning", "bot_stop", "Démarrage impossible",
                      "MetaApi n'est pas configuré. Ajoute ton token dans Réglages.")
        return {"running": False, "error": "MetaApi non configuré."}
    # Snapshot equity at bot start for drawdown tracking
    equity = 0.0
    try:
        info = await metaapi_client.get_account_information()
        equity = float(info.get("equity", 0))
    except Exception:
        pass
    now_iso = datetime.now(timezone.utc).isoformat()
    await store.set_bot_state({
        "running": True, "stop_reason": None,
        "last_status_change": now_iso,
        "current_day": datetime.now(timezone.utc).date().isoformat(),
        "trades_today": 0,
        "day_start_equity": equity,
        "session_start_equity": equity,
    })
    bot_loop.start(day_start_equity=equity)
    await _notify("success", "bot_stop", "Bot démarré",
                  "Mode " + ("Signal uniquement" if s.get("signal_only_mode") else "Exécution automatique") + ".")
    return {"running": True, "stop_reason": None}


@api.post("/bot/stop")
async def bot_stop() -> Dict[str, Any]:
    bot_loop.stop()
    await store.set_bot_state({
        "running": False, "stop_reason": "manual",
        "last_status_change": datetime.now(timezone.utc).isoformat(),
    })
    await _notify("info", "bot_stop", "Bot arrêté", "Arrêt manuel du bot.")
    return {"running": False, "stop_reason": "manual"}


@api.get("/bot/state")
async def bot_state() -> Dict[str, Any]:
    state = await store.get_bot_state()
    s = await store.get_settings()
    # session info
    now = datetime.now(timezone.utc)
    info = sess.is_in_session(now, s)
    rail = sess.session_rail_segments(s, now)
    # Determine effective status (6 states matching spec)
    stop_reason = state.get("stop_reason")
    if not state.get("running"):
        if stop_reason == "drawdown":
            effective = "stopped_drawdown"
        elif stop_reason == "consec_losses":
            effective = "stopped_losses"
        elif stop_reason == "manual":
            effective = "stopped_manual"
        else:
            effective = "stopped"
    else:
        # Check news pause
        try:
            news_data = await news_engine.fetch_calendar()
            in_pause = news_engine.is_in_news_pause(
                news_data.get("events", []),
                int(s.get("news_minutes_before", 30)),
                int(s.get("news_minutes_after", 30)),
            )
        except Exception:
            in_pause = False
        if s.get("news_filter_enabled") and in_pause:
            effective = "news_pause"
        elif not info["in_session"]:
            effective = "out_of_session"
        else:
            effective = "active"
    state["effective_status"] = effective
    state["session"] = info
    state["rail"] = rail
    state["signal_only_mode"] = s.get("signal_only_mode", True)
    state["trading_mode"] = s.get("trading_mode", "intraday")
    state["max_consec_losses"] = s.get("max_consec_losses", 3)
    state["max_drawdown_pct"] = s.get("max_drawdown_pct", 3.0)
    return state


@api.post("/bot/resume")
async def bot_resume() -> Dict[str, Any]:
    """Manually resume bot after an automatic stop (drawdown or consec_losses)."""
    s = await store.get_settings()
    if not metaapi_client.is_configured():
        return {"running": False, "error": "MetaApi non configuré."}
    equity = 0.0
    try:
        info = await metaapi_client.get_account_information()
        equity = float(info.get("equity", 0))
    except Exception:
        pass
    await store.set_bot_state({
        "running": True, "stop_reason": None,
        "last_status_change": datetime.now(timezone.utc).isoformat(),
        "current_day": datetime.now(timezone.utc).date().isoformat(),
        "consec_losses": 0,  # reset on manual resume
        "trades_today": 0,
        "day_start_equity": equity,
        "session_start_equity": equity,
    })
    bot_loop.start(day_start_equity=equity)
    await _notify("info", "bot_stop", "Bot repris manuellement",
                  "Compteurs de pertes et de trades remis à zéro.")
    return {"running": True, "stop_reason": None}


# ---------------- analysis / signals ----------------

@api.post("/analysis/run")
async def run_analysis(symbol: str = Body(default="XAUUSD", embed=True),
                       persist: bool = Body(default=False, embed=True),
                       timeframe: Optional[str] = Body(default=None, embed=True)) -> Dict[str, Any]:
    s = await store.get_settings()
    mode = s.get("trading_mode", "intraday")
    if timeframe:
        # Single-timeframe analysis (used by the chart): every detection — order blocks, FVG,
        # structure, swings — is computed on the SAME timeframe that is displayed, so zones stay
        # aligned with the candles. No cross-timeframe overlay (which produced oversized zones).
        htf = mtf = ltf = timeframe
    else:
        htf = s.get("intraday_htf" if mode == "intraday" else "scalping_htf", "H1")
        mtf = s.get("intraday_mtf" if mode == "intraday" else "scalping_mtf", "M15")
        ltf = s.get("intraday_ltf" if mode == "intraday" else "scalping_ltf", "M5")

    if not metaapi_client.is_configured():
        return {"configured": False, "error": "MetaApi non configuré.", "result": None}

    try:
        if timeframe:
            ltf_candles = await metaapi_client.get_candles(symbol, timeframe, None, 300)
            htf_candles = mtf_candles = ltf_candles
        else:
            htf_candles = await metaapi_client.get_candles(symbol, htf, None, 300)
            mtf_candles = await metaapi_client.get_candles(symbol, mtf, None, 300)
            ltf_candles = await metaapi_client.get_candles(symbol, ltf, None, 300)
    except MetaApiConnectionError as e:
        return {"configured": True, "error": str(e), "result": None}

    # Normalize candle times to ISO strings for JSON
    def _norm(arr):
        out = []
        for c in arr:
            t = c.get("time")
            if hasattr(t, "isoformat"):
                t = t.isoformat()
            out.append({
                "time": t, "open": float(c["open"]), "high": float(c["high"]),
                "low": float(c["low"]), "close": float(c["close"]),
            })
        return out

    htf_norm = _norm(htf_candles)
    mtf_norm = _norm(mtf_candles)
    ltf_norm = _norm(ltf_candles)
    result = analyze(htf_norm, mtf_norm, ltf_norm,
                     fractal_n=int(s.get("fractal_n", 3)),
                     min_rr=float(s.get("min_rr", 2.0)),
                     recent_window=int(s.get("recent_window", 6)),
                     require_fvg=bool(s.get("require_fvg_entry", True)),
                     require_sequence=bool(s.get("require_sweep_then_choch", True)),
                     require_unmitigated=bool(s.get("require_unmitigated_ob", True)))

    if persist:
        sig = result.get("signal")
        now = datetime.now(timezone.utc)
        session_info = sess.is_in_session(now, s)
        rec = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "timeframe": ltf,
            "side": sig["side"] if sig else "buy",
            "status": "accepted" if sig else "rejected",
            "reason": (sig["reason"] if sig else result.get("reject_reason", "Setup invalide")),
            "rr": sig["rr"] if sig else None,
            "entry": sig["entry"] if sig else None,
            "sl": sig["sl"] if sig else None,
            "tp": sig["tp"] if sig else None,
            "time": now.isoformat(),
            "session": session_info.get("session", "unknown"),
        }
        await store.add_signal(rec)

    return {
        "configured": True, "result": result, "candles_ltf": ltf_norm,
        "mode": mode, "htf": htf, "mtf": mtf, "ltf": ltf,
    }


@api.get("/analysis/at-time")
async def analysis_at_time(symbol: str = "XAUUSD", timestamp: str = "",
                            mode: str = "intraday", window: int = 200) -> Dict[str, Any]:
    """Replay SMC analysis at a specific historical timestamp.
    Returns candles ending at the timestamp + analysis result."""
    if not metaapi_client.is_configured():
        return {"configured": False, "error": "MetaApi non configuré.", "result": None, "candles_ltf": []}
    s = await store.get_settings()
    htf = s.get("intraday_htf" if mode == "intraday" else "scalping_htf", "H1")
    mtf = s.get("intraday_mtf" if mode == "intraday" else "scalping_mtf", "M15")
    ltf = s.get("intraday_ltf" if mode == "intraday" else "scalping_ltf", "M5")
    try:
        from datetime import datetime as _dt
        end_dt = _dt.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else None
        htf_candles = await metaapi_client.get_candles(symbol, htf, end_dt, min(window, 500))
        mtf_candles = await metaapi_client.get_candles(symbol, mtf, end_dt, min(window, 500))
        ltf_candles = await metaapi_client.get_candles(symbol, ltf, end_dt, min(window, 500))
    except Exception as e:
        return {"configured": True, "error": f"{type(e).__name__}: {e}", "result": None, "candles_ltf": []}

    def _norm(arr):
        out = []
        for c in arr:
            t = c.get("time")
            if hasattr(t, "isoformat"):
                t = t.isoformat()
            out.append({
                "time": t, "open": float(c["open"]), "high": float(c["high"]),
                "low": float(c["low"]), "close": float(c["close"]),
            })
        return out

    htf_norm = _norm(htf_candles)
    mtf_norm = _norm(mtf_candles)
    ltf_norm = _norm(ltf_candles)
    result = analyze(htf_norm, mtf_norm, ltf_norm,
                     fractal_n=int(s.get("fractal_n", 3)),
                     min_rr=float(s.get("min_rr", 2.0)),
                     recent_window=int(s.get("recent_window", 6)),
                     require_fvg=bool(s.get("require_fvg_entry", True)),
                     require_sequence=bool(s.get("require_sweep_then_choch", True)),
                     require_unmitigated=bool(s.get("require_unmitigated_ob", True)))
    return {
        "configured": True, "result": result, "candles_ltf": ltf_norm,
        "mode": mode, "htf": htf, "mtf": mtf, "ltf": ltf, "timestamp": timestamp,
    }


@api.get("/signals")
async def get_signals(limit: int = 50) -> List[Dict[str, Any]]:
    return await store.list_signals(limit)


@api.delete("/signals")
async def delete_signals() -> Dict[str, Any]:
    await store.clear_signals()
    return {"ok": True}


# ---------------- notifications ----------------

async def _notify(ntype: str, category: str, title: str, message: str) -> None:
    n = {
        "id": str(uuid.uuid4()),
        "type": ntype, "category": category,
        "title": title, "message": message,
        "time": datetime.now(timezone.utc).isoformat(),
        "read": False,
    }
    await store.add_notification(n)


@api.get("/notifications")
async def list_notifications(limit: int = 50) -> Dict[str, Any]:
    items = await store.list_notifications(limit)
    count = await store.unread_count()
    return {"items": items, "unread": count}


@api.post("/notifications/read-all")
async def read_all_notifications() -> Dict[str, Any]:
    await store.mark_all_read()
    return {"ok": True}


@api.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str) -> Dict[str, Any]:
    deleted = await store.delete_notification(notif_id)
    return {"ok": deleted}


# ---------------- news ----------------

@api.get("/news")
async def get_news(currency: str = "USD") -> Dict[str, Any]:
    s = await store.get_settings()
    data = await news_engine.fetch_calendar(currency=currency)
    # Compute pause status
    pause = news_engine.is_in_news_pause(
        data.get("events", []),
        int(s.get("news_minutes_before", 30)),
        int(s.get("news_minutes_after", 30)),
    )
    data["pause"] = pause
    return data


# ---------------- backtests ----------------

class BacktestPayload(BaseModel):
    symbol: str = "XAUUSD"
    start_date: str
    end_date: str
    mode: str = "intraday"
    spread_points: float = 25.0
    # Trailing stop — BACKTEST UNIQUEMENT (le bot live ne l'applique jamais). Optionnel.
    trailing_mode: Optional[str] = None  # off | breakeven | r_trail | structure
    trailing_trigger_r: Optional[float] = None
    trailing_distance_r: Optional[float] = None
    trailing_lookback: Optional[int] = None
    trailing_buffer: Optional[float] = None


BACKTEST_GLOBAL_TIMEOUT_SECONDS = 15 * 60  # 15 minutes
_running_backtests: Dict[str, asyncio.Task] = {}


async def _run_backtest_task(bt_id: str, req: Dict[str, Any]) -> None:
    """Wrapper enforcing global timeout + try/except. Stores any error in DB."""
    try:
        await asyncio.wait_for(
            _execute_backtest(bt_id, req),
            timeout=BACKTEST_GLOBAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        await _fail_backtest(bt_id, f"Timeout global ({BACKTEST_GLOBAL_TIMEOUT_SECONDS // 60} min) atteint.")
    except asyncio.CancelledError:
        await _fail_backtest(bt_id, "Backtest annulé par l'utilisateur.")
        raise
    except Exception as e:
        logger.exception("Backtest %s crashed", bt_id)
        await _fail_backtest(bt_id, f"{type(e).__name__}: {e}")
    finally:
        _running_backtests.pop(bt_id, None)


async def _fail_backtest(bt_id: str, error: str) -> None:
    bt = await store.get_backtest(bt_id)
    if not bt:
        return
    bt["status"] = "error"
    bt["error"] = error
    bt["finished_at"] = datetime.now(timezone.utc).isoformat()
    await store.save_backtest(bt)
    await _notify("error", "bot_stop", "Backtest échoué", error[:200])


async def _execute_backtest(bt_id: str, req: Dict[str, Any]) -> None:
    bt = await store.get_backtest(bt_id)
    if not bt:
        return
    s = await store.get_settings()
    bt["status"] = "running"
    bt["progress"] = 0.0
    bt["progress_label"] = "Initialisation…"
    bt["error"] = None
    await store.save_backtest(bt)

    if not metaapi_client.is_configured():
        await _fail_backtest(bt_id, "MetaApi non configuré — impossible de récupérer l'historique.")
        return

    from datetime import datetime as dt
    start_dt = dt.fromisoformat(req["start_date"]).replace(tzinfo=timezone.utc)
    end_dt = dt.fromisoformat(req["end_date"]).replace(tzinfo=timezone.utc)
    if end_dt <= start_dt:
        await _fail_backtest(bt_id, "Plage de dates invalide (fin ≤ début).")
        return

    days_span = (end_dt - start_dt).days
    if days_span > 186:
        await _fail_backtest(bt_id, f"Plage trop longue ({days_span} jours). Maximum 6 mois.")
        return

    async def on_status(label: str, pct: float) -> None:
        cur = await store.get_backtest(bt_id)
        if cur:
            cur["progress_label"] = label
            if pct > 0:
                cur["progress"] = round(pct, 1)
            await store.save_backtest(cur)

    candles = await bt_engine.download_m1_history(
        metaapi_client, req["symbol"], start_dt, end_dt, on_status=on_status,
    )
    if not candles:
        await _fail_backtest(bt_id, "Aucune bougie M1 récupérée pour la plage demandée.")
        return

    # Spécifications du symbole (taille du point + du contrat) pour un spread et
    # un P&L corrects par symbole. Lues en live via MetaApi (or=0.01/100, indices=…).
    try:
        spec = await metaapi_client.get_symbol_spec(req["symbol"])
        point_size = float(spec.get("point_size", 0.01))
        contract_size = float(spec.get("contract_size", 100.0))
    except Exception as e:
        logger.warning("get_symbol_spec(%s) échec backtest, défauts XAUUSD: %s", req["symbol"], e)
        point_size, contract_size = 0.01, 100.0

    await on_status(f"Replay SMC sur {len(candles)} bougies M1…", 0.0)

    async def on_progress(pct: float) -> None:
        cur = await store.get_backtest(bt_id)
        if cur:
            cur["progress"] = round(pct, 1)
            cur["progress_label"] = f"Replay SMC… {pct:.0f}%"
            await store.save_backtest(cur)

    result = await bt_engine.run_backtest(req, candles, on_progress=on_progress, settings=s,
                                          point_size=point_size, contract_size=contract_size)

    bt = await store.get_backtest(bt_id) or bt
    bt["status"] = "done"
    bt["progress"] = 100.0
    bt["progress_label"] = "Terminé"
    bt["trades"] = result["trades"]
    bt["metrics"] = result["metrics"]
    bt["equity_curve"] = result["equity_curve"]
    bt["finished_at"] = datetime.now(timezone.utc).isoformat()
    await store.save_backtest(bt)
    await _notify(
        "success", "bot_stop", "Backtest terminé",
        f"{result['metrics'].get('trades_count', 0)} trades · "
        f"winrate {result['metrics'].get('winrate', 0)}%",
    )


@api.post("/backtest")
async def start_backtest(payload: BacktestPayload) -> Dict[str, Any]:
    bt_id = str(uuid.uuid4())
    bt = {
        "id": bt_id, "status": "pending", "progress": 0.0, "progress_label": "En file d'attente…",
        "symbol": payload.symbol, "start_date": payload.start_date, "end_date": payload.end_date,
        "mode": payload.mode, "spread_points": payload.spread_points,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trades": [], "metrics": {}, "equity_curve": [],
    }
    await store.save_backtest(bt)
    task = asyncio.create_task(_run_backtest_task(bt_id, payload.model_dump()))
    _running_backtests[bt_id] = task
    return {"id": bt_id, "status": "pending"}


@api.delete("/backtest/{bt_id}")
async def cancel_or_delete_backtest(bt_id: str) -> Dict[str, Any]:
    """Cancel a running backtest OR delete a finished one."""
    task = _running_backtests.get(bt_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
        await _fail_backtest(bt_id, "Backtest annulé par l'utilisateur.")
        return {"id": bt_id, "cancelled": True}

    # Otherwise delete from DB
    from store import get_db
    res = await get_db().backtests.delete_one({"id": bt_id})
    return {"id": bt_id, "deleted": res.deleted_count > 0}


@api.get("/backtest/{bt_id}")
async def get_backtest(bt_id: str) -> Dict[str, Any]:
    bt = await store.get_backtest(bt_id)
    if not bt:
        raise HTTPException(status_code=404, detail="Backtest non trouvé.")
    return bt


@api.get("/backtests")
async def list_backtests() -> List[Dict[str, Any]]:
    return await store.list_backtests()


# ---------------- stats ----------------

@api.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Aggregate executed signals as basic live stats."""
    sigs = await store.list_signals(500)
    executed = [s for s in sigs if s.get("status") == "executed"]
    accepted = [s for s in sigs if s.get("status") in ("accepted", "executed")]
    return {
        "signals_total": len(sigs),
        "accepted": len(accepted),
        "executed": len(executed),
        "by_day": {},  # placeholder for later
        "by_session": {},
    }


# ---------------- mount ----------------

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
