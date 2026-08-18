"""Trading session helpers (London / New York / Asia local times with DST)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import pytz


LONDON = pytz.timezone("Europe/London")
NEWYORK = pytz.timezone("America/New_York")
TOKYO = pytz.timezone("Asia/Tokyo")


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _in_window(now_local: time, start: time, end: time) -> bool:
    """Fenêtre horaire locale, en gérant le passage de minuit (start > end).

    La session asiatique peut être réglée à cheval sur minuit (ex. 23:00→02:00),
    ce que la comparaison simple `start <= t < end` renverrait toujours faux.
    """
    if start <= end:
        return start <= now_local < end
    return now_local >= start or now_local < end


def _windows(settings: Dict) -> List[Tuple[str, pytz.BaseTzInfo, time, time]]:
    """Sessions actives, dans l'ordre de priorité (Londres, New York, Asie).

    L'Asie n'est présente que si `session_asia_enabled` est vrai — OFF par défaut,
    donc le comportement historique (Londres + NY seulement) est inchangé.
    """
    out: List[Tuple[str, pytz.BaseTzInfo, time, time]] = [
        ("london", LONDON,
         _parse_hhmm(settings.get("session_london_start", "08:00")),
         _parse_hhmm(settings.get("session_london_end", "11:00"))),
        ("newyork", NEWYORK,
         _parse_hhmm(settings.get("session_newyork_start", "08:00")),
         _parse_hhmm(settings.get("session_newyork_end", "11:00"))),
    ]
    if settings.get("session_asia_enabled"):
        out.append(("asia", TOKYO,
                    _parse_hhmm(settings.get("session_asia_start", "08:00")),
                    _parse_hhmm(settings.get("session_asia_end", "11:00"))))
    return out


def is_in_session(now_utc: datetime, settings: Dict) -> Dict[str, object]:
    """Return {in_session: bool, session: 'london'|'newyork'|'asia'|None, next_session: str}."""
    for name, tz, start, end in _windows(settings):
        if _in_window(now_utc.astimezone(tz).time(), start, end):
            return {"in_session": True, "session": name, "next_session": None}
    return {"in_session": False, "session": None, "next_session": "london"}


def session_rail_segments(settings: Dict, now_utc: Optional[datetime] = None) -> Dict[str, object]:
    """Compute current-time marker position (0..1) on a 24h rail, and
    the % positions of the active session windows mapped to UTC for visual."""
    if now_utc is None:
        now_utc = datetime.now(pytz.UTC)

    def frac(d: datetime) -> float:
        utc = d.astimezone(pytz.UTC)
        return (utc.hour * 3600 + utc.minute * 60 + utc.second) / 86400.0

    now_frac = (now_utc.hour * 3600 + now_utc.minute * 60 + now_utc.second) / 86400.0

    out: Dict[str, object] = {
        "now_frac": now_frac,
        "now_utc_iso": now_utc.isoformat(),
        "asia_enabled": bool(settings.get("session_asia_enabled")),
    }
    for name, tz, start, end in _windows(settings):
        today = now_utc.astimezone(tz).date()
        d_start = tz.localize(datetime.combine(today, start))
        d_end = tz.localize(datetime.combine(today, end))
        if end <= start:  # fenêtre à cheval sur minuit → la fin est le lendemain
            d_end += timedelta(days=1)
        out[f"{name}_start_frac"] = frac(d_start)
        out[f"{name}_end_frac"] = frac(d_end)
    return out
