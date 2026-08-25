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
    # 4e etage journalier (D1) — Synthese V3 §2 : DAILY (contexte) > H1 (zones de fond)
    # > M15 (structure/POI) > M5 (entree). Le scalping garde son etage M15 valide en
    # backtest et se voit AJOUTER H1 au-dessus (D8) : le biais monte sans qu'on perde
    # le niveau qui etait le seul valide. "" = etage journalier desactive.
    "intraday_d1": "D1",
    "scalping_d1": "H1",
    "intraday_htf": "H1",        # biais
    "intraday_mtf": "M15",       # structure / order blocks (POI)
    "intraday_ltf": "M5",        # déclencheur / entrée
    "scalping_htf": "M15",       # biais (M15 validé en backtest 6 mois ; H1 = perdant, DD catastrophique)
    "scalping_mtf": "M5",        # structure / order blocks (POI)
    "scalping_ltf": "M1",        # déclencheur / entrée

    # --- Détection SMC : méthodes de tracé (Manuel de détection + Synthèse V3) ---
    # Voir DECISIONS.md 2026-08-25. Chaque option conserve l'ancienne méthode pour
    # pouvoir comparer en backtest plutôt que de basculer à l'aveugle.
    "swing_method": "two_candle",   # two_candle (manuel §1.1) | fractal (historique)
    "swing_confirm": 2,             # nb de bougies opposées consécutives qui valident un swing
    "ob_zone": "wick",              # wick (manuel §4.1 : high→low) | body (historique : open/close)
    "structure_break_mode": "close",  # close (conservateur) | wick (agressif) — manuel §1.3
    # range_bound (borne opposée du range, défaut) | liquidity (BSL/SSL la plus proche)
    # | nearest_swing (historique)
    "tp_target": "range_bound",
    # Liquidité BSL/SSL : deux sommets sont « alignés » (= un seul réservoir de
    # liquidité) si leur écart est sous ce facteur x l'amplitude moyenne d'une bougie.
    "liquidity_cluster_atr": 0.25,
    # Placement du SL : "poi" = bord de l'order block / du sweep (historique) ;
    # "protected" = AU-DELÀ du creux/sommet protégé le plus proche (Synthèse V3
    # §Étape 8). "protected" ne fait qu'éloigner le SL, jamais le resserrer.
    "sl_mode": "poi",
    # Le piège à stops placé juste avant la POI doit avoir été pris avant d'entrer.
    "require_inducement_swept": False,
    # Second CHOCH (Synthèse V3 §Étape 4, « ne pas prendre le premier CHOCH ») :
    # un 1er CHOCH sur l'UT structure PUIS un 2nd sur l'UT d'entrée.
    "require_second_choch": False,
    "second_choch_window": 20,     # bougies du niveau structure
    # Range asiatique (Manuel §6.1) : fenêtre 23h→7h heure de Paris. Ses bornes sont
    # des niveaux de LIQUIDITÉ pour la session de Londres, jamais des points d'entrée.
    # ⚠️ Le manuel le dit pertinent surtout sur paires européennes ; l'or bouge la
    # nuit → à valider en backtest avant activation.
    "asia_start_hour": 23,
    "asia_end_hour": 7,
    "asia_tz": "Europe/Paris",
    "use_asia_liquidity": False,     # ajouter Asia High/Low aux niveaux de liquidité
    "use_pdh_pdl_liquidity": False,  # ajouter PDH/PDL aux niveaux de liquidité
    # Zones acceptées comme POI : "ob" (order blocks seuls, défaut) ou "ob_bpr"
    # (order blocks + Balance Price Range). Manuel §3.3 : le BPR « peut servir de POI ».
    # Liste séparée par des virgules pour tester chaque type SÉPARÉMENT (Synthèse V3
    # §11) : "ob" (défaut), "ob,bpr", "breaker", "mitigation", "rejection", ou les
    # raccourcis "ob_bpr" et "all".
    "poi_source": "ob",
    # OTE (Manuel §5.2) : retracement 62-79%, filtre plus strict que premium/discount.
    "require_ote": False,
    "ote_low_pct": 0.618,
    "ote_high_pct": 0.786,
    # Rejection Block : part minimale de la bougie que doit occuper la mèche de rejet.
    "rejection_wick_ratio": 0.5,
    # Fraîcheur de l'OB (manuel §4.1 « OB déjà testé = à éviter », nuancé par la Synthèse
    # V3 §5.8 « facteur de qualité, pas condition absolue ») : 0 = filtre DÉSACTIVÉ, le
    # compteur de touchés reste affiché. N > 0 = écarte un OB déjà retouché N fois.
    "max_ob_touches": 0,
    # Displacement (Synthèse V3 §Étape 5) — défini comme « la bougie de cassure laisse
    # une FVG ». OFF par défaut : à valider en backtest avant d'en faire un verrou.
    "require_displacement": False,

    # Règles SMC strictes (désactivables pour comparer en backtest)
    "require_fvg_entry": False,        # confluence FVG (OFF par défaut — backtests: dégrade les résultats en verrou dur)
    "require_sweep_then_choch": False, # confluence séquence sweep→CHoCH (OFF par défaut)
    "require_unmitigated_ob": False,   # OB POI non invalidé (OFF par défaut)
    "require_premium_discount": True,  # achat en discount / vente en premium (utilisé live + backtest)
    # Mode d'entrée sur l'order block POI (comparaison backtest 2026-07-28, cf. DECISIONS.md) :
    #   "close" (défaut) = la clôture doit être DANS le corps de l'OB — strict, seul mode rentable en backtest
    #   "tap" = une bougie récente a touché l'OB (mèches comprises) — beaucoup plus de trades, PERDANT en backtest
    #   "zone_50" = la cloture doit avoir depasse la LIGNE MEDIANE de l'OB (moitie profonde
    #     de la zone) — meilleur ratio, declenche moins souvent. Entree au MARCHE a la
    #     cloture, ce n'est PAS un ordre limite pose a 50%.
    "ob_entry_mode": "close",

    # Journal — mode diagnostic : journalise AUSSI les rejets précoces (pas de biais / pas de POI /
    # hors zone), regroupés. OFF par défaut (sinon spam). Sert à comprendre les setups écartés.
    "verbose_journal": False,

    # Contexte journalier (Synthese V3 §Etape 1) — les 2 seuls concepts backtestes de
    # la playlist, mais sur GER40/indices et PAS sur l'or : filtres OFF par defaut,
    # a valider en backtest sur XAUUSD avant d'en faire des verrous (D2).
    "require_daily_bias": False,   # le biais HTF doit correspondre au Daily Bias PDH/PDL
    "require_po3": False,          # le Power of 3 du jour doit aller dans le sens du biais
    "po3_wick_ratio": 0.20,        # part de la bougie journaliere que doit faire la meche
                                   # de manipulation pour compter comme Power of 3


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

    # --- Gestion échelonnée TP1/TP2/TP3 (Synthèse V3 §Étape 9) ---
    # ⚠️ Lève la règle « TP partiels : NON implémentés volontairement » (décision D3②
    # du 2026-08-25, cf. DECISIONS.md). Implémenté et testé, mais laissé OFF par défaut :
    # l'activer change le profil de résultat de toute la stratégie (winrate en hausse,
    # R moyen en baisse) et doit passer par un backtest avant le réel.
    # TP3 = la cible du signal (borne du range ou liquidité selon tp_target).
    "partial_tp_enabled": False,
    "tp1_r": 1.0,               # TP1 à N x le risque
    "tp1_close_pct": 50.0,      # % du volume INITIAL fermé à TP1
    "tp1_to_breakeven": True,   # après TP1, le SL remonte à l'entrée (trade « gratuit »)
    "tp2_close_pct": 30.0,      # % du volume INITIAL fermé à TP2 (à mi-chemin TP1→TP3)

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

    # Journal de trading — capital de référence de la courbe d'évolution.
    # 0 = déduit automatiquement (solde actuel du compte − P&L cumulé du journal).
    "journal_initial_balance": 0.0,

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
    bias: Optional[str] = None          # bullish | bearish — direction du setup (surtout utile sur les rejets)


# ---------- Trades (journal de trading) ----------

class Trade(BaseModel):
    """Un trade RÉEL du bot, journalisé de son ouverture à sa clôture.

    L'identifiant est celui de la position chez le broker (jamais un UUID) : c'est
    lui qui permet de retrouver le P&L réalisé réel dans l'historique MetaApi."""
    id: str
    symbol: str
    side: Literal["buy", "sell"]
    volume: float = 0.0
    entry: Optional[float] = None
    sl: Optional[float] = None           # SL au moment de la sortie (trailing inclus)
    sl_initial: Optional[float] = None   # SL d'origine, avant tout trailing
    tp: Optional[float] = None
    planned_rr: Optional[float] = None   # RR prévu au moment de l'entrée
    open_time: str
    close_time: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None          # None = inconnu (jamais 0 par défaut)
    result: Optional[Literal["win", "loss", "be", "unknown"]] = None
    exit_reason: Optional[str] = None    # tp | sl | trailing_sl | other | unknown
    pnl_source: Optional[str] = None     # broker | equity_delta
    status: Literal["open", "closed"] = "open"
    session: Optional[str] = None        # london | newyork | unknown
    mode: Optional[str] = None           # intraday | scalping
    timeframe: Optional[str] = None
    reason: Optional[str] = None
    # Prises partielles TP1/TP2 deja encaissees : [{reason, price, volume}].
    # `volume` ci-dessus reste le volume INITIAL du trade.
    partials: List[dict] = []
    source: Literal["bot", "import"] = "bot"
    settings_snapshot: dict = {}         # réglages actifs au moment du trade


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
    # Prises partielles TP1/TP2/TP3 : [{reason, price, pct, pnl, time}].
    # Vide quand la gestion echelonnee est desactivee.
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
    partials: List[dict] = []
    exit_reason: Optional[str] = None


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
