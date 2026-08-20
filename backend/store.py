"""MongoDB store helpers."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from models import DEFAULT_SETTINGS


_mongo: Optional[AsyncIOMotorClient] = None


def get_db():
    global _mongo
    client = _mongo
    if client is None:
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _mongo = client
    return client[os.environ.get("DB_NAME", "goldflow")]


# ---------- Settings ----------

async def get_settings() -> Dict[str, Any]:
    db = get_db()
    doc = await db.settings.find_one({"_id": "global"})
    if not doc:
        s = dict(DEFAULT_SETTINGS)
        s["_id"] = "global"
        await db.settings.insert_one(s)
        s.pop("_id", None)
        return s
    doc.pop("_id", None)
    # merge with defaults to add new keys on upgrade
    merged = dict(DEFAULT_SETTINGS)
    merged.update(doc)
    return merged


async def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    await db.settings.update_one({"_id": "global"}, {"$set": updates}, upsert=True)
    return await get_settings()


# ---------- Signals ----------

async def add_signal(sig: Dict[str, Any]) -> None:
    db = get_db()
    await db.signals.insert_one(sig)


async def add_or_merge_signal(sig: Dict[str, Any]) -> None:
    """Journalise un rejet en REGROUPANT les répétitions : si le dernier signal du
    symbole est un rejet de MÊME raison, on incrémente son compteur et on met à jour
    l'heure de fin, au lieu d'insérer une nouvelle ligne identique chaque minute."""
    db = get_db()
    last = await db.signals.find_one({"symbol": sig.get("symbol")}, sort=[("time", -1)])
    # On fusionne sur la CLÉ normalisée (reason_key) — ex. toutes les variantes
    # "RR x < min 2.0" partagent la même clé → une seule ligne.
    same = (last and last.get("status") == "rejected"
            and last.get("reason_key", last.get("reason")) == sig.get("reason_key", sig.get("reason")))
    if same:
        await db.signals.update_one(
            {"id": last["id"]},
            # On met aussi à jour la raison affichée (dernier RR vu, par ex.).
            {"$inc": {"count": 1},
             "$set": {"last_time": sig.get("time"), "reason": sig.get("reason")}},
        )
        return
    sig.setdefault("count", 1)
    sig.setdefault("last_time", sig.get("time"))
    await db.signals.insert_one(sig)


async def list_signals(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db.signals.find({}, {"_id": 0}).sort("time", -1).limit(limit)
    return await cur.to_list(length=limit)


async def clear_signals() -> None:
    db = get_db()
    await db.signals.delete_many({})


# ---------- Notifications ----------

async def add_notification(n: Dict[str, Any]) -> None:
    db = get_db()
    # Respect des interrupteurs « Notifications » des Réglages (notif_<catégorie>).
    # Avant ce correctif, les toggles existaient dans l'UI mais n'étaient vérifiés
    # nulle part côté backend : ils n'avaient AUCUN effet. Catégorie sans
    # interrupteur (ex. backtest, bot_resume) = toujours activée.
    try:
        s = await get_settings()
        if s.get(f"notif_{n.get('category', '')}", True) is False:
            return
    except Exception:
        pass  # en cas de doute, on notifie (ne jamais perdre une alerte par erreur technique)
    await db.notifications.insert_one(n)
    # Push vers les téléphones enregistrés (canal « au mieux », jamais bloquant)
    try:
        import push
        await push.send_to_all(
            title=n.get("title", "GoldFlow SMC"),
            body=n.get("message", ""),
            category=n.get("category", "goldflow"),
        )
    except Exception:
        pass


# ---------- Push devices (téléphones enregistrés pour les notifications) ----------

async def upsert_push_device(token: str, platform: str = "android") -> None:
    from datetime import datetime, timezone
    db = get_db()
    await db.push_devices.update_one(
        {"token": token},
        {"$set": {
            "token": token,
            "platform": platform,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


async def list_push_devices() -> List[Dict[str, Any]]:
    db = get_db()
    cur = db.push_devices.find({}, {"_id": 0})
    return await cur.to_list(length=100)


async def remove_push_device(token: str) -> None:
    db = get_db()
    await db.push_devices.delete_one({"token": token})


async def list_notifications(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db.notifications.find({}, {"_id": 0}).sort("time", -1).limit(limit)
    return await cur.to_list(length=limit)


async def mark_all_read() -> None:
    db = get_db()
    await db.notifications.update_many({"read": False}, {"$set": {"read": True}})


async def delete_notification(notif_id: str) -> bool:
    db = get_db()
    res = await db.notifications.delete_one({"id": notif_id})
    return res.deleted_count > 0


async def unread_count() -> int:
    db = get_db()
    return await db.notifications.count_documents({"read": False})


# ---------- Backtests ----------

async def save_backtest(bt: Dict[str, Any]) -> None:
    db = get_db()
    await db.backtests.replace_one({"id": bt["id"]}, bt, upsert=True)


async def get_backtest(bt_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.backtests.find_one({"id": bt_id}, {"_id": 0})


async def list_backtests(limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    # exclude trades/equity_curve fields for list
    proj = {"_id": 0, "trades": 0, "equity_curve": 0}
    cur = db.backtests.find({}, proj).sort("created_at", -1).limit(limit)
    return await cur.to_list(length=limit)


# ---------- Trades (journal de trading) ----------
# Collection `trades` : la mémoire durable des trades RÉELS du bot (ouverture →
# clôture). Avant, un trade fermé n'était utilisé que pour compter les pertes
# consécutives puis oublié : aucun historique n'existait.

async def add_trade(trade: Dict[str, Any]) -> bool:
    """Insère un trade s'il n'existe pas déjà (clé = id de position broker).

    `$setOnInsert` garantit qu'un ré-import ou un doublon d'ouverture ne peut
    JAMAIS écraser un trade déjà clôturé (P&L réel). Renvoie True si inséré."""
    db = get_db()
    res = await db.trades.update_one({"id": trade["id"]}, {"$setOnInsert": trade}, upsert=True)
    return res.upserted_id is not None


async def update_trade(trade_id: str, updates: Dict[str, Any]) -> None:
    db = get_db()
    await db.trades.update_one({"id": trade_id}, {"$set": updates})


async def close_trade(trade_id: str, updates: Dict[str, Any]) -> bool:
    """Clôture un trade encore ouvert. Le filtre `status: open` évite qu'une
    seconde détection de fermeture ne réécrive un P&L déjà enregistré."""
    db = get_db()
    payload = dict(updates)
    payload["status"] = "closed"
    res = await db.trades.update_one({"id": trade_id, "status": "open"}, {"$set": payload})
    return res.matched_count > 0


async def list_trades(limit: int = 500, status: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {} if status is None else {"status": status}
    cur = db.trades.find(q, {"_id": 0}).sort("open_time", -1).limit(limit)
    return await cur.to_list(length=limit)


async def get_trade(trade_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db.trades.find_one({"id": trade_id}, {"_id": 0})


async def delete_trade(trade_id: str) -> bool:
    db = get_db()
    res = await db.trades.delete_one({"id": trade_id})
    return res.deleted_count > 0


# ---------- Bot state ----------

async def set_bot_state(state: Dict[str, Any]) -> None:
    db = get_db()
    await db.bot_state.update_one({"_id": "global"}, {"$set": state}, upsert=True)


async def get_bot_state() -> Dict[str, Any]:
    db = get_db()
    doc = await db.bot_state.find_one({"_id": "global"})
    if not doc:
        default = {
            "_id": "global",
            "running": False,
            "stop_reason": None,
            "consec_losses": 0,
            "consec_session": None,
            "trades_today": 0,
            "current_day": None,
            "day_start_equity": 0.0,
            "session_start_equity": 0.0,
            "last_status_change": None,
        }
        await db.bot_state.insert_one(default)
        default.pop("_id", None)
        return default
    doc.pop("_id", None)
    return doc
