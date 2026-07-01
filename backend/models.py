"""Pydantic models and Mongo helpers for GoldFlow SMC."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, List, Optional, Literal
from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _to_str(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)


PyObjectId = Annotated[str, BeforeValidator(_to_str)]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


# ---------- Settings ----------

DEFAULT_SETTINGS = {
    # MetaApi
    "metaapi_token": "",
    "metaapi_account_id": "",
    "account_type": "demo",  # demo | real
    "real_confirmed": False,

    # Symbol(s)
    "active_symbol": "XAUUSD",
    "symbols": ["XAUUSD"],

    # Mode — top-down 3 niveaux : biais (HTF) → structure/POI (MTF) → entrée (LTF)
    "trading_mode": "intraday",  # intraday | scalping
    "intraday_htf": "H1",        # biais
    "intraday_mtf": "M15",       # structure / order blocks (POI)
    "intraday_ltf": "M5",        # déclencheur / entrée
    "scalping_htf": "M15",       # biais (M15 validé en backtest 6 mois ; H1 = perdant, DD catastrophique)
    "scalping_mtf": "M5",        # structure / order blocks (POI)
    "scalping_ltf": "M1",        # déclencheur / entrée

    # Règles SMC strictes (désactivables pour comparer en backtest)
    "require_fvg_entry": False,        # confluence FVG (OFF par défaut — backtests: dégrade les résultats en verrou dur)
    "require_sweep_then_choch": False, # confluence séquence sweep→CHoCH (OFF par défaut)
    "require_unmitigated_ob": False,   # OB POI non invalidé (OFF par défaut)

    # Journal — mode diagnostic : journalise AUSSI les rejets précoces (pas de biais / pas de POI /
    # hors zone), regroupés. OFF par défaut (sinon spam). Sert à comprendre les setups écartés.
    "verbose_journal": False,

    # Risk
    "risk_per_trade_pct": 1.0,
    "min_rr": 2.0,
    "max_consec_losses": 3,
    "max_drawdown_pct": 3.0,
    "max_trades_per_day": 5,
    "resume_policy": "next_session",  # next_session | next_day
    "fractal_n": 3,
    "recent_window": 6,          # LTF candles within which a sweep/CHoCH must occur
    "max_lot_per_trade": 10.0,   # hard cap on computed lot size (anti over-leverage)

    # Trailing stop — MÊME logique live (bot_loop) + backtest. OFF par défaut.
    "trailing_mode": "off",        # off | breakeven | r_trail | structure
    "trailing_trigger_r": 1.0,     # profit (en R) à partir duquel le trailing s'active
    "trailing_distance_r": 1.0,    # r_trail : distance verrouillée sous la meilleure excursion
    "trailing_lookback": 5,        # structure : nb de bougies suivies
    "trailing_buffer": 0.0,        # marge (prix) ajoutée sous/sur le niveau

    # Sessions (local times)
    "session_london_start": "08:00",
    "session_london_end": "11:00",
    "session_newyork_start": "08:00",
    "session_newyork_end": "11:00",

    # News
    "news_filter_enabled": True,
    "news_minutes_before": 30,
    "news_minutes_after": 30,
    "close_positions_before_news": False,

    # Prop firm — défauts calés sur BlueGuardian Instant Funding (vérifié juin 2026)
    "prop_firm_enabled": False,
    "prop_daily_dd_pct": 3.0,           # perte journalière max (% du solde initial)
    "prop_total_dd_pct": 6.0,           # drawdown max (% du solde initial)
    "prop_safety_margin_pct": 20.0,     # le bot s'arrête à (1 - marge) des limites réelles
    "prop_profit_target_pct": 0.0,      # BlueGuardian Instant : aucun objectif de profit
    "prop_initial_balance": 25000.0,    # taille du compte financé
    # --- spécifiques BlueGuardian (0/false = règle désactivée pour une autre firme) ---
    "prop_trailing_dd": True,           # drawdown max GLISSANT (vs statique type FTMO)
    "prop_trailing_lock_profit_pct": 6.0,  # le plancher trailing se verrouille au solde initial après ce profit
    "prop_guardian_shield_pct": 1.0,    # Guardian Shield : perte FLOTTANTE max des positions ouvertes (% solde initial)
    "prop_consistency_pct": 20.0,       # cohérence : profit d'un jour ≤ X% du profit total (payout uniquement)
    "prop_daily_reset_hour_est": 17,    # heure de reset du jour (17 = 17h00 EST chez BlueGuardian)

    # Notifications
    "notif_open_trade": True,
    "notif_close_trade": True,
    "notif_dd_warning": True,
    "notif_bot_stop": True,
    "notif_connection": True,
    "notif_news": True,

    # Execution
    "signal_only_mode": True,  # default ON for first launch
    "bot_running": False,
    "stop_reason": None,  # manual | drawdown | consec_losses | None

    # Backtest defaults
    "default_spread_points": 25,

    # Magic
    "magic_number": 990077,
    "order_comment_tag": "GFSMC",
}


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="allow")


class SettingsOut(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------- Signals ----------

class Signal(BaseModel):
    id: str
    symbol: str
    timeframe: str
    side: Literal["buy", "sell"]
    status: Literal["accepted", "rejected", "executed", "news_pause"]
    reason: str
    rr: Optional[float] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    time: str
    session: Optional[str] = None  # london | newyork | unknown
    count: int = 1                 # nb de rejets identiques regroupés sous cette ligne
    last_time: Optional[str] = None  # heure du dernier rejet identique (plage horaire)
    reject_stage: Optional[str] = None  # insufficient | no_bias | no_poi | out_of_zone | near_miss
    reason_key: Optional[str] = None    # raison normalisée (nombres neutralisés) pour le regroupement


# ---------- Notifications ----------

class Notification(BaseModel):
    id: str
    type: Literal["info", "success", "warning", "error"]
    category: str  # open_trade | close_trade | dd_warning | bot_stop | connection | news
    title: str
    message: str
    time: str
    read: bool = False


# ---------- Backtests ----------

class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    mode: Literal["intraday", "scalping"] = "intraday"
    spread_points: float = 25.0


class BacktestTrade(BaseModel):
    id: str
    side: str
    entry_time: str
    exit_time: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    pnl: float
    rr: float
    reason: str
    result: Literal["win", "loss", "be"]


class BacktestResult(BaseModel):
    id: str
    status: Literal["pending", "running", "done", "error"]
    progress: float
    symbol: str
    start_date: str
    end_date: str
    mode: str
    spread_points: float
    created_at: str
    finished_at: Optional[str] = None
    trades: List[BacktestTrade] = []
    metrics: dict = {}
    equity_curve: List[dict] = []
    error: Optional[str] = None
