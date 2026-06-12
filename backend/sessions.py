"""Trading session helpers (London / New York local times with DST)."""
from __future__ import annotations

from datetime import datetime, time
from typing import Dict, Optional
import pytz


LONDON = pytz.timezone("Europe/London")
NEWYORK = pytz.timezone("America/New_York")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def is_in_session(now_utc: datetime, settings: Dict) -> Dict[str, object]:
    """Return {in_session: bool, session: 'london'|'newyork'|None, next_session: str}."""
    london_start = _parse_hhmm(settings.get("session_london_start", "08:00"))
    london_end = _parse_hhmm(settings.get("session_london_end", "11:00"))
    ny_start = _parse_hhmm(settings.get("session_newyork_start", "08:00"))
    ny_end = _parse_hhmm(settings.get("session_newyork_end", "11:00"))

    now_london = now_utc.astimezone(LONDON).time()
    now_ny = now_utc.astimezone(NEWYORK).time()

    in_london = london_start <= now_london < london_end
    in_ny = ny_start <= now_ny < ny_end

    if in_london:
        return {"in_session": True, "session": "london", "next_session": None}
    if in_ny:
        return {"in_session": True, "session": "newyork", "next_session": None}
    return {"in_session": False, "session": None, "next_session": "london"}


def session_rail_segments(settings: Dict, now_utc: Optional[datetime] = None) -> Dict[str, object]:
    """Compute current-time marker position (0..1) on a 24h rail, and
    the % positions of London + NY windows mapped to UTC for visual."""
    if now_utc is None:
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)

    london_start = _parse_hhmm(settings.get("session_london_start", "08:00"))
    london_end = _parse_hhmm(settings.get("session_london_end", "11:00"))
    ny_start = _parse_hhmm(settings.get("session_newyork_start", "08:00"))
    ny_end = _parse_hhmm(settings.get("session_newyork_end", "11:00"))

    # Convert local times today to UTC fractions of 24h
    today_london = LONDON.localize(datetime.combine(now_utc.astimezone(LONDON).date(), london_start))
    today_london_end = LONDON.localize(datetime.combine(now_utc.astimezone(LONDON).date(), london_end))
    today_ny = NEWYORK.localize(datetime.combine(now_utc.astimezone(NEWYORK).date(), ny_start))
    today_ny_end = NEWYORK.localize(datetime.combine(now_utc.astimezone(NEWYORK).date(), ny_end))

    def frac(d: datetime) -> float:
        utc = d.astimezone(pytz.UTC)
        return (utc.hour * 3600 + utc.minute * 60 + utc.second) / 86400.0

    now_frac = (now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second) / 86400.0

    return {
        "now_frac": now_frac,
        "london_start_frac": frac(today_london),
        "london_end_frac": frac(today_london_end),
        "newyork_start_frac": frac(today_ny),
        "newyork_end_frac": frac(today_ny_end),
        "now_utc_iso": now_utc.isoformat(),
    }
