"""Forex Factory weekly calendar (free, no key)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("goldflow.news")

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

_cache: Dict[str, Any] = {"ts": None, "data": [], "error": None}
_CACHE_TTL = 600  # 10 minutes
# Tolérance aux pannes du flux (décision 2026-07-30, cf. DECISIONS.md) : en cas
# d'échec, on sert le DERNIER calendrier valide s'il a moins de 12 h — c'est un
# calendrier hebdomadaire publié à l'avance, il reste exact pendant des heures.
# Au-delà (ou si jamais récupéré), on renvoie l'erreur → le bot suspend les
# entrées par prudence, comme avant. En juillet 2026, 120 micro-coupures du flux
# avaient bloqué le bot en pleine session (trade du 01-07 14h02 manqué).
_STALE_MAX_S = 12 * 3600


async def fetch_calendar(currency: str = "USD") -> Dict[str, Any]:
    """Return calendar events (filtered by currency by default). Caches 10min.
    On fetch failure, serves the last good calendar if younger than 12h (stale=True)."""
    now = datetime.now(timezone.utc)
    if _cache["ts"] and (now - _cache["ts"]).total_seconds() < _CACHE_TTL:
        events = _filter(_cache["data"], currency)
        return {"events": events, "error": None, "fetched_at": _cache["ts"].isoformat()}

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(CALENDAR_URL, headers={"User-Agent": "GoldFlow-SMC/1.0"})
            r.raise_for_status()
            data = r.json()
        _cache["ts"] = now
        _cache["data"] = data
        _cache["error"] = None
        return {"events": _filter(data, currency), "error": None, "fetched_at": now.isoformat()}
    except Exception as e:
        _cache["error"] = str(e)
        age_s = (now - _cache["ts"]).total_seconds() if _cache["ts"] else None
        if age_s is not None and age_s < _STALE_MAX_S:
            logger.warning("Flux news injoignable (%s) — calendrier en cache servi (âge %.0f min).",
                           e, age_s / 60)
            return {"events": _filter(_cache["data"], currency), "error": None,
                    "stale": True, "fetched_at": _cache["ts"].isoformat(),
                    "fetch_error": str(e)}
        return {"events": [], "error": f"Calendrier indisponible: {e}", "fetched_at": None}


def _filter(events: List[Dict[str, Any]], currency: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in events:
        if currency and ev.get("country") != currency and ev.get("currency") != currency:
            continue
        out.append({
            "title": ev.get("title", ev.get("event", "")),
            "country": ev.get("country", currency),
            "date": ev.get("date"),
            "impact": (ev.get("impact") or "").lower(),
            "actual": ev.get("actual"),
            "forecast": ev.get("forecast"),
            "previous": ev.get("previous"),
        })
    return out


def is_in_news_pause(events: List[Dict[str, Any]], minutes_before: int, minutes_after: int,
                     now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Return the upcoming high-impact event causing a pause, or None."""
    if now is None:
        now = datetime.now(timezone.utc)
    for ev in events:
        if (ev.get("impact") or "").lower() != "high":
            continue
        d = ev.get("date")
        if not d:
            continue
        try:
            t = datetime.fromisoformat(d.replace("Z", "+00:00"))
        except Exception:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        diff_min = (t - now).total_seconds() / 60
        if -minutes_after <= diff_min <= minutes_before:
            return {"event": ev, "diff_min": diff_min}
    return None
