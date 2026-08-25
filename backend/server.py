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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Body, Request
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

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


# ---------------- API key protection ----------------
# L'API pilote un compte de trading RÉEL et est exposée publiquement (Render).
# Si la variable d'environnement API_KEY est définie, toute requête /api doit
# porter le header X-API-Key correspondant. Si API_KEY est absente, l'auth est
# désactivée (compatibilité : permet de déployer ce code AVANT de créer la clé).
# /api/ et /api/health restent ouverts (statut sans donnée sensible).
_API_KEY = os.environ.get("API_KEY", "").strip()
_PUBLIC_PATHS = {"/api", "/api/", "/api/health"}


@app.middleware("http")
async def _require_api_key(request: Request, call_next):
    if _API_KEY and request.url.path.startswith("/api") \
            and request.url.path not in _PUBLIC_PATHS \
            and request.method != "OPTIONS":  # laisser passer les preflights CORS
        if request.headers.get("x-api-key", "") != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Clé API manquante ou invalide."})
    return await call_next(request)


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
    # Liste blanche : seules les clés connues de DEFAULT_SETTINGS sont acceptées.
    # Sans ce filtre, n'importe quelle clé arbitraire serait injectée dans le
    # document Mongo (le frontend renvoie d'ailleurs des clés dérivées comme
    # metaapi_token_masked qu'il ne faut jamais stocker).
    from models import DEFAULT_SETTINGS
    unknown = [k for k in updates if k not in DEFAULT_SETTINGS]
    if unknown:
        logger.info("put_settings: clés ignorées (hors liste blanche): %s", unknown)
    updates = {k: v for k, v in updates.items() if k in DEFAULT_SETTINGS}
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
    # Analyse 3 niveaux : MÊMES fenêtres que le backtest et le bot live. La branche
    # mono-timeframe (graphique) garde ses 300 bougies : c'est de l'affichage de
    # zones, pas une décision de trading — les tronquer ferait disparaître les
    # zones anciennes du graphique.
    if timeframe:
        htf_in, mtf_in, ltf_in = htf_norm, mtf_norm, ltf_norm
    else:
        htf_in = htf_norm[-bt_engine.WINDOW_HTF:]
        mtf_in = mtf_norm[-bt_engine.WINDOW_MTF:]
        ltf_in = ltf_norm[-bt_engine.WINDOW_LTF:]
    result = analyze(htf_in, mtf_in, ltf_in,
                     fractal_n=int(s.get("fractal_n", 3)),
                     min_rr=float(s.get("min_rr", 2.0)),
                     recent_window=int(s.get("recent_window", 6)),
                     require_fvg=bool(s.get("require_fvg_entry", True)),
                     require_sequence=bool(s.get("require_sweep_then_choch", True)),
                     require_unmitigated=bool(s.get("require_unmitigated_ob", True)),
                     require_pd=bool(s.get("require_premium_discount", True)),
                     ob_entry_mode=str(s.get("ob_entry_mode", "close")))

    if persist:
        sig = result.get("signal")
        now = datetime.now(timezone.utc)
        session_info = sess.is_in_session(now, s)
        rec = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "timeframe": ltf,
            # Sur un rejet, la direction affichée = biais HTF du setup (pas "buy" arbitraire).
            "side": sig["side"] if sig else ("sell" if result.get("bias") == "bearish" else "buy"),
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
    # Rejeu : mêmes fenêtres d'analyse que le backtest/live ; l'affichage (candles_ltf)
    # garde toutes les bougies demandées.
    result = analyze(htf_norm[-bt_engine.WINDOW_HTF:], mtf_norm[-bt_engine.WINDOW_MTF:],
                     ltf_norm[-bt_engine.WINDOW_LTF:],
                     fractal_n=int(s.get("fractal_n", 3)),
                     min_rr=float(s.get("min_rr", 2.0)),
                     recent_window=int(s.get("recent_window", 6)),
                     require_fvg=bool(s.get("require_fvg_entry", True)),
                     require_sequence=bool(s.get("require_sweep_then_choch", True)),
                     require_unmitigated=bool(s.get("require_unmitigated_ob", True)),
                     require_pd=bool(s.get("require_premium_discount", True)),
                     ob_entry_mode=str(s.get("ob_entry_mode", "close")))
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


# ---------------- push (téléphones) ----------------

@api.post("/push/register")
async def register_push_device(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Enregistre un téléphone pour les notifications push (app mobile)."""
    token = str(payload.get("token", "")).strip()
    if not token:
        raise HTTPException(status_code=400, detail="token manquant")
    await store.upsert_push_device(token, platform=str(payload.get("platform", "android")))
    import push
    return {"ok": True, "push_configured": push.is_configured()}


@api.post("/push/test")
async def send_test_push() -> Dict[str, Any]:
    """Envoie une notification de test à tous les téléphones enregistrés."""
    import push
    if not push.is_configured():
        raise HTTPException(status_code=503, detail="Push non configuré (FIREBASE_SERVICE_ACCOUNT absent)")
    devices = await store.list_push_devices()
    if not devices:
        raise HTTPException(status_code=404, detail="Aucun téléphone enregistré")
    await push.send_to_all("Test GoldFlow SMC", "Les notifications push fonctionnent ✅", "test")
    return {"ok": True, "devices": len(devices)}


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
    # Trailing stop — paramètres du RUN de backtest (prioritaires sur les Réglages).
    # NB : le trailing existe AUSSI en live (bot_loop._apply_trailing, OFF par défaut,
    # piloté par les Réglages) — même logique partagée compute_trailing_sl.
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
    await _notify("error", "backtest", "Backtest échoué", error[:200])


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
        "success", "backtest", "Backtest terminé",
        f"{result['metrics'].get('trades_count', 0)} trades · "
        f"winrate {result['metrics'].get('winrate', 0)}%",
    )


@api.post("/backtest")
async def start_backtest(payload: BacktestPayload) -> Dict[str, Any]:
    # Un seul backtest à la fois : le replay est gourmand en CPU et partage
    # l'event loop avec la boucle de trading LIVE — plusieurs backtests en
    # parallèle affameraient le bot (pouls périmé → relances du gardien).
    if any(not t.done() for t in _running_backtests.values()):
        raise HTTPException(status_code=409,
                            detail="Un backtest est déjà en cours. Attends sa fin ou annule-le.")
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


# ---------------- journal de trading ----------------
# Le journal s'appuie sur la collection `trades` alimentee par bot_loop
# (ouverture -> cloture avec le P&L REEL du broker). Les metriques reutilisent
# _compute_metrics du backtest : une seule definition de winrate / profit factor /
# drawdown dans toute l'app.

# Libelles lisibles des reglages recopies dans chaque trade. Sert a afficher
# « reglage particulier » quand la valeur differait du defaut de l'app.
_SETTINGS_LABELS = {
    "trading_mode": "Mode",
    "risk_per_trade_pct": "Risque par trade (%)",
    "min_rr": "RR minimum",
    "max_lot_per_trade": "Lot max",
    "trailing_mode": "Trailing stop",
    "trailing_trigger_r": "Trailing — declenchement (R)",
    "trailing_distance_r": "Trailing — distance (R)",
    "trailing_lookback": "Trailing — bougies suivies",
    "require_fvg_entry": "Confluence FVG exigee",
    "require_sweep_then_choch": "Sequence sweep -> CHoCH exigee",
    "require_unmitigated_ob": "Order block non mitige exige",
    "require_premium_discount": "Premium/discount exige",
    "ob_entry_mode": "Mode d'entree sur l'OB",
    "swing_method": "Methode de detection des swings",
    "swing_confirm": "Bougies de confirmation d'un swing",
    "ob_zone": "Trace de l'order block",
    "structure_break_mode": "Cassure de structure",
    "tp_target": "Cible du TP",
    "max_ob_touches": "Fraicheur OB (touches max)",
    "require_displacement": "Displacement exige",
    "intraday_d1": "Etage journalier (intraday)",
    "scalping_d1": "Etage journalier (scalping)",
    "require_daily_bias": "Daily Bias PDH/PDL exige",
    "require_po3": "Power of 3 exige",
    "po3_wick_ratio": "Power of 3 — ratio de meche",
    "liquidity_cluster_atr": "Liquidite — tolerance de regroupement",
    "sl_mode": "Placement du SL",
    "require_inducement_swept": "Inducement pris exige",
    "require_second_choch": "Second CHoCH exige",
    "second_choch_window": "Second CHoCH — fenetre",
    "use_asia_liquidity": "Liquidite du range asiatique",
    "use_pdh_pdl_liquidity": "Liquidite PDH/PDL",
    "fractal_n": "Fractale N",
    "recent_window": "Fenetre recente",
    "max_trades_per_day": "Trades max / jour",
    "max_consec_losses": "Pertes consecutives max",
    "max_drawdown_pct": "Drawdown max (%)",
    "news_filter_enabled": "Filtre news",
    "prop_firm_enabled": "Mode prop firm",
}


def _fmt_setting(v: Any) -> str:
    if isinstance(v, bool):
        return "active" if v else "desactive"
    return str(v)


def _settings_notes(snapshot: Optional[Dict[str, Any]]) -> List[str]:
    """Reglages du trade qui DIFFERENT des valeurs par defaut de l'app."""
    from models import DEFAULT_SETTINGS
    notes: List[str] = []
    for k, v in (snapshot or {}).items():
        if k not in DEFAULT_SETTINGS or v is None:
            continue
        if v != DEFAULT_SETTINGS[k]:
            notes.append(f"{_SETTINGS_LABELS.get(k, k)} : {_fmt_setting(v)}")
    return notes


@api.get("/journal")
async def get_journal(limit: int = 500) -> Dict[str, Any]:
    """Journal de trading : trades reels + metriques globales + courbe d'evolution."""
    s = await store.get_settings()
    trades = await store.list_trades(limit)
    for t in trades:
        t["settings_notes"] = _settings_notes(t.get("settings_snapshot"))

    # Seuls les trades clotures AVEC un P&L connu entrent dans les statistiques.
    # Un trade au P&L inconnu (historique broker indisponible) reste visible dans
    # la liste mais n'est jamais compte comme un gain ni une perte.
    closed = [t for t in trades
              if t.get("status") == "closed" and isinstance(t.get("pnl"), (int, float))]
    chrono = sorted(closed, key=lambda t: t.get("close_time") or t.get("open_time") or "")
    total_pnl = sum(float(t["pnl"]) for t in chrono)

    account: Dict[str, Any] = {}
    if metaapi_client.is_configured():
        try:
            account = await metaapi_client.get_account_information() or {}
        except Exception as e:
            logger.info("Journal: solde du compte indisponible (%s)", e)

    # Capital de depart : reglage explicite, sinon deduit du solde actuel moins le
    # P&L cumule du journal. Jamais invente : sans reglage ET sans MetaApi, on
    # renvoie null et le drawdown en % n'est pas calcule (seul celui en devise l'est).
    initial = float(s.get("journal_initial_balance") or 0)
    initial_source = "setting"
    if initial <= 0:
        balance = account.get("balance")
        if balance is None:
            initial, initial_source = 0.0, "unknown"
        else:
            initial, initial_source = float(balance) - total_pnl, "auto"
            if initial <= 0:
                initial, initial_source = 0.0, "unknown"

    equity_curve: List[Dict[str, Any]] = []
    if chrono:
        equity_curve.append({"time": chrono[0].get("open_time"), "equity": round(initial, 2)})
        eq = initial
        for t in chrono:
            eq += float(t["pnl"])
            equity_curve.append({"time": t.get("close_time") or t.get("open_time"),
                                 "equity": round(eq, 2)})

    metrics: Dict[str, Any] = {}
    if chrono:
        norm = [{
            "pnl": float(t["pnl"]),
            "rr": float(t.get("planned_rr") or 0),
            "result": t.get("result") or ("win" if float(t["pnl"]) > 0 else "loss"),
        } for t in chrono]
        metrics = dict(bt_engine._compute_metrics(norm, equity_curve))
        # Drawdown en devise : toujours calculable, meme sans capital de depart connu.
        peak, max_dd_money = initial, 0.0
        for pt in equity_curve:
            peak = max(peak, pt["equity"])
            max_dd_money = max(max_dd_money, peak - pt["equity"])
        metrics["max_drawdown_money"] = round(max_dd_money, 2)
        if initial <= 0:
            metrics.pop("max_drawdown_pct", None)   # % impossible sans capital de depart
            metrics.pop("final_equity", None)
        metrics["pnl_pct"] = round(total_pnl / initial * 100, 2) if initial > 0 else None
    metrics["open_trades"] = len([t for t in trades if t.get("status") == "open"])
    metrics["unknown_pnl"] = len([t for t in trades
                                  if t.get("status") == "closed" and t.get("pnl") is None])

    return {
        "trades": trades,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "initial_balance": round(initial, 2) if initial > 0 else None,
        "initial_balance_source": initial_source,
        "currency": account.get("currency"),
    }


class JournalImportPayload(BaseModel):
    days: int = Field(default=180, ge=1, le=1000)


def _match_executed_signal(executed: List[Dict[str, Any]], symbol: str, side: str,
                           open_time: str) -> Optional[Dict[str, Any]]:
    """Retrouve le signal execute correspondant a un trade importe (meme symbole,
    meme sens, a moins de 15 min de l'ouverture) — c'est lui qui porte le RR prevu,
    le SL/TP et la session. Renvoie None si aucun ne correspond (RR affiche inconnu,
    jamais invente)."""
    t0 = _parse_iso(open_time)
    if t0 is None:
        return None
    best, best_gap = None, 900.0
    for x in executed:
        if x.get("symbol") != symbol or x.get("side") != side:
            continue
        t = _parse_iso(str(x.get("time", "")))
        if t is None:
            continue
        gap = abs((t - t0).total_seconds())
        if gap < best_gap:
            best, best_gap = x, gap
    return best


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@api.post("/journal/import")
async def import_journal(payload: JournalImportPayload) -> Dict[str, Any]:
    """Importe dans le journal les trades DEJA realises par le bot chez le broker.

    Source unique : l'historique des transactions MetaApi (P&L, prix et heures
    reels). Seules les positions portant le magic number du bot sont reprises. Les
    trades deja presents ne sont jamais ecrases. Le RR prevu et le SL/TP sont
    retrouves via le journal des signaux quand un signal execute correspond."""
    if not metaapi_client.is_configured():
        raise HTTPException(status_code=400,
                            detail="MetaApi non configure — impossible de lire l'historique du broker.")
    s = await store.get_settings()
    magic = int(s.get("magic_number", 990077))
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=payload.days + 1)
    try:
        deals = await metaapi_client.get_deals_by_time_range(start, end)
    except MetaApiConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for d in deals:
        pid = str(d.get("positionId") or "")
        if pid:
            groups.setdefault(pid, []).append(d)

    executed = [x for x in await store.list_signals(500) if x.get("status") == "executed"]
    imported = already = still_open = not_ours = 0
    for pid, ds in groups.items():
        # Le magic peut n'etre porte que par la transaction d'entree -> on regarde
        # tout le groupe. Aucune position d'un autre robot / manuelle n'est reprise.
        if not any(int(x.get("magic", 0) or 0) == magic for x in ds):
            not_ours += 1
            continue
        ds.sort(key=bot_loop._deal_time)
        ins = [x for x in ds if str(x.get("entryType", "")).endswith("_IN")]
        outs = [x for x in ds if str(x.get("entryType", "")).endswith("_OUT")]
        if not ins or not outs:
            still_open += 1   # position encore ouverte (ou historique incomplet)
            continue
        first, last = ins[0], outs[-1]
        pnl = sum(float(x.get("profit", 0) or 0) + float(x.get("swap", 0) or 0)
                  + float(x.get("commission", 0) or 0) for x in ds)
        symbol = first.get("symbol") or last.get("symbol") or ""
        side = "buy" if "BUY" in str(first.get("type", "")).upper() else "sell"
        open_time = bot_loop._deal_time(first)
        entry = float(first.get("price", 0) or 0) or None
        exit_price = float(last.get("price", 0) or 0) or None
        sig = _match_executed_signal(executed, symbol, side, open_time)
        sl = sig.get("sl") if sig else None
        tp = sig.get("tp") if sig else None
        trade = {
            "id": pid,
            "symbol": symbol,
            "side": side,
            "volume": float(first.get("volume", 0) or 0),
            "entry": entry,
            "sl": sl,
            "sl_initial": sl,
            "tp": tp,
            "planned_rr": sig.get("rr") if sig else None,
            "open_time": open_time,
            "close_time": bot_loop._deal_time(last),
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "result": "win" if pnl > 0 else ("loss" if pnl < 0 else "be"),
            # Meme deduction TP/SL que le live (bot_loop) — une seule logique.
            "exit_reason": bot_loop._exit_reason({"tp": tp, "sl": sl, "sl_initial": sl},
                                                 exit_price),
            "pnl_source": "broker",
            "status": "closed",
            "session": sig.get("session") if sig else None,
            "mode": None,
            "timeframe": sig.get("timeframe") if sig else None,
            "reason": sig.get("reason") if sig else None,
            "source": "import",
            "settings_snapshot": {},   # reglages de l'epoque inconnus
        }
        if await store.add_trade(trade):
            imported += 1
        else:
            already += 1

    logger.info("Journal: import termine — %d importes, %d deja presents, %d encore "
                "ouverts, %d hors bot (sur %d positions).",
                imported, already, still_open, not_ours, len(groups))
    return {"imported": imported, "already_present": already, "still_open": still_open,
            "ignored_not_bot": not_ours, "positions_scanned": len(groups),
            "deals_scanned": len(deals)}


# ---------------- montage ----------------

app.include_router(api)

# CORS. Piège Starlette : allow_credentials=True avec l'origine joker "*" fait
# refléter l'origine appelante dans Access-Control-Allow-Origin AVEC credentials —
# c'est-à-dire ouvrir les credentials à tous les sites. On ne les autorise donc
# que si CORS_ORIGINS liste des origines explicites.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials="*" not in _cors_origins,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
