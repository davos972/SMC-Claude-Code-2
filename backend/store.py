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
    await db.notifications.insert_one(n)


async def list_notifications(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db.notifications.find({}, {"_id": 0}).sort("time", -1).limit(limit)
    return await cur.to_list(length=limit)


async def mark_all_read() -> None:
    db = get_db()
    await db.notifications.update_many({"read": False}, {"$set": {"read": True}})


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
            "trades_today": 0,
            "day_start_equity": 0.0,
            "session_start_equity": 0.0,
            "last_status_change": None,
        }
        await db.bot_state.insert_one(default)
        default.pop("_id", None)
        return default
    doc.pop("_id", None)
    return doc
