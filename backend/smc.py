"""Smart Money Concepts engine — SHARED between live bot and backtester.

Inputs: list of OHLC candles in ascending time order.
Each candle: {"time": iso_str_or_epoch, "open": f, "high": f, "low": f, "close": f}

Outputs of analyze(): dict with detected swings, structure events (BOS/CHoCH),
order blocks, fair value gaps, liquidity sweeps, current bias, premium/discount,
and any actionable signal at the latest candle.

Les règles de détection suivent le « Manuel de détection SMC » et la « Synthèse
stratégie V3 » (décisions B1–B6 / D1–D9, cf. DECISIONS.md 2026-08-25).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import List, Optional, Literal, Dict, Any


Candle = Dict[str, Any]


@dataclass
class Swing:
    idx: int
    time: Any
    price: float
    kind: Literal["high", "low"]
    # Indice de la bougie à partir de laquelle le swing est VALIDÉ (règle des 2 bougies
    # du manuel, ou i+n en fractale). Avant cet indice le swing n'existe pas encore :
    # detect_structure ne doit pas s'en servir (sinon on casse une structure sur un
    # sommet qui n'est pas encore confirmé).
    confirm_idx: int = -1


@dataclass
class StructureEvent:
    idx: int
    time: Any
    kind: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    price: float
    swing_idx: int = -1
    swing_time: Any = None
    # Displacement (Synthèse V3 §Étape 5) : la cassure est-elle un déplacement FORT ?
    # Définition binaire retenue (D5①) : la bougie de cassure laisse une FVG.
    displacement: bool = False


@dataclass
class OrderBlock:
    start_idx: int
    end_idx: int
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"]
    time: Any
    mitigated: bool = False
    mitigated_idx: int = -1
    mitigated_time: Any = None
    # Indices des bougies qui ont RETOUCHÉ la zone après la cassure (une entrée dans
    # la zone = un touché, peu importe le nombre de bougies qui y séjournent).
    # Sert au filtre de fraîcheur (D7②) : le manuel écarte un OB déjà testé, mais la
    # Synthèse V3 §5.8 en fait « un facteur de qualité, pas une condition absolue » →
    # on EXPOSE le compteur, et le rejet est un réglage désactivable.
    touch_idx: List[int] = field(default_factory=list)
    zone: str = "wick"  # wick | body — méthode de tracé utilisée


@dataclass
class FVG:
    idx: int
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"]
    time: Any
    filled: bool = False
    filled_idx: int = -1
    filled_time: Any = None


@dataclass
class LiquiditySweep:
    idx: int
    price: float
    kind: Literal["high_sweep", "low_sweep"]
    time: Any
    mitigated: bool = False
    mitigated_idx: int = -1
    mitigated_time: Any = None


@dataclass
class DailyContext:
    """Contexte journalier — Synthèse V3 §Étape 1 (« Module 1 · Analyse »).

    Deux briques, les SEULES de la playlist appuyées par un backtest à grande échelle
    (§6). Attention : ces backtests portent sur GER40 et des indices, PAS sur l'or —
    d'où les filtres OFF par défaut tant qu'ils n'ont pas été validés sur XAUUSD (D2②).
    """
    pdh: Optional[float] = None          # Previous Daily High
    pdl: Optional[float] = None          # Previous Daily Low
    day_open: Optional[float] = None     # ouverture de la journée en cours
    bias: Optional[str] = None           # bullish | bearish | None (inside day)
    bias_reason: str = ""
    po3_direction: Optional[str] = None  # bullish | bearish | None
    po3_reason: str = ""
    structure_bias: Optional[str] = None  # biais de structure du niveau journalier


@dataclass
class Signal:
    side: Literal["buy", "sell"]
    entry: float
    sl: float
    tp: float
    rr: float
    reason: str
    poi_top: float
    poi_bottom: float


# ---------------- core detection ----------------

def _swings_fractal(candles: List[Candle], n: int = 3) -> List[Swing]:
    """Fractale historique : le high doit dépasser STRICTEMENT les n bougies de chaque côté.
    Conséquence connue : un double sommet parfait (deux highs égaux) n'est pas détecté."""
    swings: List[Swing] = []
    L = len(candles)
    for i in range(n, L - n):
        h = candles[i]["high"]
        lo = candles[i]["low"]
        is_high = all(candles[i - j]["high"] < h and candles[i + j]["high"] < h for j in range(1, n + 1))
        is_low = all(candles[i - j]["low"] > lo and candles[i + j]["low"] > lo for j in range(1, n + 1))
        if is_high:
            swings.append(Swing(idx=i, time=candles[i]["time"], price=h, kind="high", confirm_idx=i + n))
        if is_low:
            swings.append(Swing(idx=i, time=candles[i]["time"], price=lo, kind="low", confirm_idx=i + n))
    return swings


def _swings_two_candle(candles: List[Candle], confirm: int = 2) -> List[Swing]:
    """Règle des deux bougies (Manuel §1.1, Synthèse V3 §5.1) — méthode par défaut.

    Un sommet est validé si :
      1. la montée culmine sur la bougie i        → high[i] >= high[i-1]
      2. les `confirm` bougies suivantes sont BAISSIÈRES consécutives (close < open)
      3. aucune de ces bougies ne dépasse le high de i
    Symétrique pour un creux. Le `>=` de la règle 1 est délibéré : il capte les
    doubles sommets / sommets alignés, que la fractale stricte manquait — or le manuel
    en fait la source de liquidité la plus importante (§2.1).
    """
    swings: List[Swing] = []
    L = len(candles)
    confirm = max(1, confirm)
    for i in range(1, L - confirm):
        nxt = candles[i + 1: i + 1 + confirm]
        h = candles[i]["high"]
        lo = candles[i]["low"]
        if h >= candles[i - 1]["high"] \
                and all(c["close"] < c["open"] for c in nxt) \
                and all(c["high"] <= h for c in nxt):
            swings.append(Swing(idx=i, time=candles[i]["time"], price=h, kind="high",
                                confirm_idx=i + confirm))
        if lo <= candles[i - 1]["low"] \
                and all(c["close"] > c["open"] for c in nxt) \
                and all(c["low"] >= lo for c in nxt):
            swings.append(Swing(idx=i, time=candles[i]["time"], price=lo, kind="low",
                                confirm_idx=i + confirm))
    return swings


def find_swings(candles: List[Candle], n: int = 3, method: str = "two_candle",
                confirm: int = 2) -> List[Swing]:
    """Points pivots. `method` = "two_candle" (défaut, manuel SMC) ou "fractal" (historique)."""
    if method == "fractal":
        return _swings_fractal(candles, n)
    return _swings_two_candle(candles, confirm)


def _has_displacement(fvgs: Optional[List[FVG]], idx: int, direction: str) -> bool:
    """Displacement (D5①) : la bougie de cassure participe à une FVG du même sens.
    `fvg.idx` désigne la bougie DU MILIEU du motif à 3 bougies, d'où la tolérance de ±1."""
    if not fvgs:
        return False
    return any(f.direction == direction and abs(f.idx - idx) <= 1 for f in fvgs)


def detect_structure(candles: List[Candle], swings: List[Swing], break_mode: str = "close",
                     fvgs: Optional[List[FVG]] = None) -> List[StructureEvent]:
    """Detect BOS / CHoCH events.

    - `break_mode` = "close" (conservateur, défaut) ou "wick" (agressif) — le manuel §1.3
      laisse explicitement le choix. En "close" la clôture doit dépasser le niveau ;
      en "wick" la mèche suffit.
    - Un swing n'est pris en compte qu'à partir de son `confirm_idx` (règle des 2 bougies) :
      on ne casse jamais une structure sur un sommet pas encore validé.
    """
    events: List[StructureEvent] = []
    bias: Optional[str] = None
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None
    swing_iter = iter(swings)
    next_swing = next(swing_iter, None)

    def _ready(s: Swing) -> int:
        return s.confirm_idx if s.confirm_idx >= 0 else s.idx

    for i, c in enumerate(candles):
        # update swings reaching index i (une fois CONFIRMÉS)
        while next_swing is not None and _ready(next_swing) <= i:
            if next_swing.kind == "high":
                last_high = next_swing
            else:
                last_low = next_swing
            next_swing = next(swing_iter, None)

        up = c["close"] if break_mode == "close" else c["high"]
        dn = c["close"] if break_mode == "close" else c["low"]
        # Bullish break: price above last confirmed swing high
        if last_high and up > last_high.price:
            kind = "BOS" if bias == "bullish" else "CHoCH"
            events.append(StructureEvent(
                idx=i, time=c["time"], kind=kind, direction="bullish",
                price=last_high.price, swing_idx=last_high.idx, swing_time=last_high.time,
                displacement=_has_displacement(fvgs, i, "bullish"),
            ))
            bias = "bullish"
            last_high = None  # consume
        elif last_low and dn < last_low.price:
            kind = "BOS" if bias == "bearish" else "CHoCH"
            events.append(StructureEvent(
                idx=i, time=c["time"], kind=kind, direction="bearish",
                price=last_low.price, swing_idx=last_low.idx, swing_time=last_low.time,
                displacement=_has_displacement(fvgs, i, "bearish"),
            ))
            bias = "bearish"
            last_low = None
    return events


def detect_order_blocks(candles: List[Candle], events: List[StructureEvent],
                        zone: str = "wick") -> List[OrderBlock]:
    """The Order Block is the last opposite-color candle before the impulsive
    move that caused the BOS/CHoCH event.

    `zone` = "wick" (défaut, Manuel §4.1 : rectangle entre le HIGH et le LOW de la bougie)
    ou "body" (ancien comportement : corps open/close uniquement). La zone en mèches est
    plus large → SL plus éloigné mais plus réaliste (« stop trop serré = stop trop souvent
    touché », Synthèse V3 §Étape 8).

    Invalidation ("mitigated"): a later candle CLOSES through the OB (price genuinely
    broke the level), NOT merely a wick tap. This matters because the entry logic needs
    price to RETURN into the OB to trade it — counting that first tap as "mitigated"
    would make the `require_unmitigated_ob` filter reject every valid setup.
    Les simples retouches sont comptées à part dans `touch_idx` (filtre de fraîcheur).
    """
    obs: List[OrderBlock] = []
    for ev in events:
        # walk backwards from event idx to find the last opposite candle
        if ev.direction == "bullish":
            search = (j for j in range(ev.idx - 1, max(-1, ev.idx - 12), -1)
                      if candles[j]["close"] < candles[j]["open"])
        else:
            search = (j for j in range(ev.idx - 1, max(-1, ev.idx - 12), -1)
                      if candles[j]["close"] > candles[j]["open"])
        j = next(search, None)
        if j is None:
            continue
        c = candles[j]
        if zone == "body":
            top = max(c["open"], c["close"])
            bottom = min(c["open"], c["close"])
        else:
            top = c["high"]
            bottom = c["low"]
        ob = OrderBlock(
            start_idx=j, end_idx=ev.idx, top=top, bottom=bottom,
            direction=ev.direction, time=c["time"], zone=zone,
        )
        # Invalidation: scan forward for a candle CLOSING through the OB.
        for k in range(j + 1, len(candles)):
            cand = candles[k]
            if ob.direction == "bullish":
                if cand["close"] < ob.bottom:  # closed below a bullish OB → invalidated
                    ob.mitigated = True
                    ob.mitigated_idx = k
                    ob.mitigated_time = cand["time"]
                    break
            else:
                if cand["close"] > ob.top:  # closed above a bearish OB → invalidated
                    ob.mitigated = True
                    ob.mitigated_idx = k
                    ob.mitigated_time = cand["time"]
                    break
        # Retouches APRÈS la cassure (le mouvement impulsif a quitté la zone) : une
        # entrée dans la zone = un touché, quel que soit le nombre de bougies qui y restent.
        inside_prev = False
        for k in range(ev.idx + 1, len(candles)):
            cand = candles[k]
            inside = cand["low"] <= ob.top and cand["high"] >= ob.bottom
            if inside and not inside_prev:
                ob.touch_idx.append(k)
            inside_prev = inside
        obs.append(ob)
    return obs


def _epoch(t: Any) -> Optional[float]:
    """Best-effort conversion of a candle time (epoch number or ISO string) to epoch seconds."""
    if isinstance(t, (int, float)):
        return float(t)
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def detect_fvgs(candles: List[Candle]) -> List[FVG]:
    """3-candle FVG: gap between c1.high and c3.low (bullish) or c1.low and c3.high (bearish).
    Also marks `filled` and `filled_idx` if a subsequent candle closes the gap.

    FVGs that straddle a market gap (weekend / session break — i.e. missing candles) are skipped:
    the price jump across a closed market is not a real fair value gap."""
    fvgs: List[FVG] = []
    # Typical spacing between candles (median delta) — used to detect abnormal time gaps.
    times = [_epoch(c.get("time")) for c in candles]
    deltas = sorted(b - a for a, b in zip(times, times[1:]) if a is not None and b is not None and b > a)
    typical_dt = deltas[len(deltas) // 2] if deltas else None

    for i in range(2, len(candles)):
        c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
        # Skip if these 3 candles span a market gap (more than ~3x the normal step over 2 bars).
        if typical_dt:
            t1, t3 = times[i - 2], times[i]
            if t1 is not None and t3 is not None and (t3 - t1) > typical_dt * 3:
                continue
        fvg: Optional[FVG] = None
        if c3["low"] > c1["high"]:
            fvg = FVG(idx=i - 1, top=c3["low"], bottom=c1["high"], direction="bullish", time=c2["time"])
        elif c3["high"] < c1["low"]:
            fvg = FVG(idx=i - 1, top=c1["low"], bottom=c3["high"], direction="bearish", time=c2["time"])
        if fvg is None:
            continue
        # Forward scan for fill
        for k in range(i + 1, len(candles)):
            cand = candles[k]
            if fvg.direction == "bullish":
                if cand["low"] <= fvg.bottom:
                    fvg.filled = True
                    fvg.filled_idx = k
                    fvg.filled_time = cand["time"]
                    break
            else:
                if cand["high"] >= fvg.top:
                    fvg.filled = True
                    fvg.filled_idx = k
                    fvg.filled_time = cand["time"]
                    break
        fvgs.append(fvg)
    return fvgs


def detect_liquidity_sweeps(candles: List[Candle], swings: List[Swing], lookback: int = 20) -> List[LiquiditySweep]:
    """A sweep is a wick that pierces a recent swing high/low but closes back."""
    sweeps: List[LiquiditySweep] = []
    highs = [s for s in swings if s.kind == "high"]
    lows = [s for s in swings if s.kind == "low"]

    for i, c in enumerate(candles):
        # recent swings before this candle
        rec_highs = [s for s in highs if s.idx < i and i - s.idx <= lookback]
        rec_lows = [s for s in lows if s.idx < i and i - s.idx <= lookback]
        for s in rec_highs:
            if c["high"] > s.price and c["close"] < s.price:
                sweeps.append(LiquiditySweep(idx=i, price=s.price, kind="high_sweep", time=c["time"]))
                break
        for s in rec_lows:
            if c["low"] < s.price and c["close"] > s.price:
                sweeps.append(LiquiditySweep(idx=i, price=s.price, kind="low_sweep", time=c["time"]))
                break

    # Mitigation: a sweep stays "fresh" until price later CLOSES through the swept level
    # (the liquidity is then consumed / the level genuinely broken — no longer a sweep signal).
    #   high_sweep  → mitigated once a later candle closes ABOVE the swept high
    #   low_sweep   → mitigated once a later candle closes BELOW the swept low
    for sw in sweeps:
        for k in range(sw.idx + 1, len(candles)):
            cc = candles[k]
            if (sw.kind == "high_sweep" and cc["close"] > sw.price) or \
               (sw.kind == "low_sweep" and cc["close"] < sw.price):
                sw.mitigated = True
                sw.mitigated_idx = k
                sw.mitigated_time = cc["time"]
                break
    return sweeps


def premium_discount(swings: List[Swing]) -> Optional[Dict[str, float]]:
    """Fallback range premium/discount: most recent swing high and low (méthode brute)."""
    if len(swings) < 2:
        return None
    last_high = next((s for s in reversed(swings) if s.kind == "high"), None)
    last_low = next((s for s in reversed(swings) if s.kind == "low"), None)
    if not last_high or not last_low:
        return None
    top, bottom = last_high.price, last_low.price
    if top <= bottom:
        return None
    mid = (top + bottom) / 2
    return {"top": top, "bottom": bottom, "mid": mid}


def dealing_range(swings: List[Swing], events: List[StructureEvent]) -> Optional[Dict[str, float]]:
    """Dealing range SMC basé sur la dernière jambe d'impulsion (BOS/CHoCH le plus récent).

    Plutôt que 2 swings bruts, on délimite la fourchette par la JAMBE qui a cassé la structure :
    - cassure haussière : du creux d'origine (avant la cassure) jusqu'au plus haut atteint depuis →
      discount = moitié basse de cette jambe (zone d'achat).
    - cassure baissière : du sommet d'origine jusqu'au plus bas atteint → premium = moitié haute.
    Le 50% (mid) sépare premium et discount. Repli sur premium_discount() si données insuffisantes.
    Les bornes sont AUSSI la liquidité cible (Manuel §5.1 : « le sommet = BSL, le creux = SSL »).
    """
    if not events:
        return premium_discount(swings)
    ev = events[-1]
    bullish = ev.direction == "bullish"
    if bullish:
        # creux d'origine : dernier swing bas AVANT la cassure
        origin = next((s for s in reversed(swings) if s.kind == "low" and s.idx < ev.swing_idx), None)
        if origin is None:
            return premium_discount(swings)
        highs = [s.price for s in swings if s.kind == "high" and s.idx >= origin.idx]
        top = max(highs) if highs else ev.price
        bottom = origin.price
    else:
        origin = next((s for s in reversed(swings) if s.kind == "high" and s.idx < ev.swing_idx), None)
        if origin is None:
            return premium_discount(swings)
        lows = [s.price for s in swings if s.kind == "low" and s.idx >= origin.idx]
        bottom = min(lows) if lows else ev.price
        top = origin.price
    if top <= bottom:
        return premium_discount(swings)
    return {"top": top, "bottom": bottom, "mid": (top + bottom) / 2}


def daily_context(candles_daily: Optional[List[Candle]], po3_wick_ratio: float = 0.20,
                  swing_method: str = "two_candle", swing_confirm: int = 2,
                  fractal_n: int = 3, break_mode: str = "close") -> Optional[DailyContext]:
    """Daily Bias (PDH/PDL) + Power of 3 sur la bougie journalière en cours.

    Daily Bias (Synthèse V3 §Étape 1, ~68% sur GER40 / 10 ans) :
      - clôture AU-DELÀ du PDH / PDL          → continuation dans ce sens
      - mèche au-delà PUIS réintégration       → signal de SHIFT (sens opposé)
      - ni l'un ni l'autre                     → inside day, pas de biais (§8 : ne pas trader)

    Power of 3 / AMD (§Étape 3, ~97,75% des bougies journalières) : une mèche de
    MANIPULATION par rapport à l'ouverture du jour précède la vraie expansion. Une
    grande mèche BASSE suivie d'une clôture au-dessus de l'open = manipulation
    baissière puis distribution haussière.

    Renvoie None si l'historique journalier est absent ou trop court : le contexte
    journalier ne doit JAMAIS bloquer l'analyse, seulement l'enrichir.
    """
    if not candles_daily or len(candles_daily) < 2:
        return None
    prev, today = candles_daily[-2], candles_daily[-1]
    ctx = DailyContext(pdh=prev["high"], pdl=prev["low"], day_open=today["open"])

    c, h, l, o = today["close"], today["high"], today["low"], today["open"]
    if c > ctx.pdh:
        ctx.bias, ctx.bias_reason = "bullish", "Clôture au-dessus du PDH (continuation)"
    elif c < ctx.pdl:
        ctx.bias, ctx.bias_reason = "bearish", "Clôture sous le PDL (continuation)"
    elif h > ctx.pdh:
        ctx.bias, ctx.bias_reason = "bearish", "Sweep du PDH puis réintégration (shift)"
    elif l < ctx.pdl:
        ctx.bias, ctx.bias_reason = "bullish", "Sweep du PDL puis réintégration (shift)"
    else:
        ctx.bias_reason = "Inside day — pas de biais journalier"

    rng = h - l
    if rng > 0:
        if (o - l) / rng >= po3_wick_ratio and c > o:
            ctx.po3_direction = "bullish"
            ctx.po3_reason = "Mèche de manipulation basse sous l'open puis expansion haussière"
        elif (h - o) / rng >= po3_wick_ratio and c < o:
            ctx.po3_direction = "bearish"
            ctx.po3_reason = "Mèche de manipulation haute au-dessus de l'open puis expansion baissière"
        else:
            ctx.po3_reason = "Pas de manipulation nette par rapport à l'open du jour"

    # Biais de STRUCTURE du niveau journalier (indépendant du PDH/PDL).
    if len(candles_daily) >= max(fractal_n * 2, swing_confirm * 2) + 5:
        sw = find_swings(candles_daily, n=fractal_n, method=swing_method, confirm=swing_confirm)
        ev = detect_structure(candles_daily, sw, break_mode, detect_fvgs(candles_daily))
        if ev:
            ctx.structure_bias = ev[-1].direction
    return ctx


# ---------------- analysis pipeline ----------------

# Rejets « prix mal placé » (pas dans la POI / mauvaise zone premium-discount) = bruit,
# pas un vrai quasi-setup. Doit correspondre EXACTEMENT aux textes de _build_signal.
_OUT_OF_ZONE_REASONS = {
    "Prix hors zone discount",
    "Prix hors zone premium",
    "Prix hors de l'order block POI",
    "Aucun order block touché récemment (tap)",
    "Prix pas au-delà des 50% de l'order block POI",
}


def _build_signal(direction, candles_entry, last_close, last_idx, poi_list, pd_struct,
                  swings_target, sweeps_entry, events_entry, fvgs_entry,
                  min_rr, recent_window, require_fvg, require_sequence, require_pd=True,
                  ob_entry_mode="close", tp_target="range_bound", require_displacement=False):
    """Evaluate the entry trigger on the entry timeframe for a given HTF bias direction.
    Returns (Signal, None) if all conditions pass, else (None, reject_reason)."""
    bullish = direction == "bullish"

    # 1) Premium/Discount (range computed on the structure tier) — achat en discount, vente en premium
    if require_pd:
        if bullish and last_close > pd_struct["mid"]:
            return None, "Prix hors zone discount"
        if not bullish and last_close < pd_struct["mid"]:
            return None, "Prix hors zone premium"

    # 2) POI (structure-tier order block) — trois modes d'entrée (Réglages → ob_entry_mode) :
    #    "close" (validé backtest) : la DERNIÈRE CLÔTURE doit être DANS la zone de l'OB le
    #      plus récent. Strict — c'est la sélectivité qui rend le bot rentable.
    #    "zone_50" (Manuel §4.1 / Synthèse V3 §Étape 7) : la clôture doit avoir dépassé la
    #      LIGNE MÉDIANE de l'OB (moitié profonde de la zone) — meilleur ratio, déclenche
    #      moins souvent. NB : c'est une entrée au marché à la clôture, PAS un ordre limite
    #      posé à 50% (le bot n'envoie que des ordres au marché).
    #    "tap" (expérimental, perdant en backtest 6 mois 2025-12→2026-06 : PF 0.85-0.92,
    #      DD jusqu'à 68% — voir DECISIONS.md 2026-07-28) : une des `recent_window`
    #      dernières bougies a TOUCHÉ un OB (mèches comprises). Beaucoup plus de trades.
    if ob_entry_mode == "tap":
        recent_candles = candles_entry[max(0, last_idx - recent_window + 1): last_idx + 1]
        poi = next((ob for ob in reversed(poi_list)
                    if any(c["low"] <= ob.top and c["high"] >= ob.bottom for c in recent_candles)),
                   None)
        if poi is None:
            return None, "Aucun order block touché récemment (tap)"
    else:
        poi = poi_list[-1]
        if bullish:
            if not (poi.bottom <= last_close <= poi.top * 1.001):
                return None, "Prix hors de l'order block POI"
        else:
            if not (poi.bottom * 0.999 <= last_close <= poi.top):
                return None, "Prix hors de l'order block POI"
        if ob_entry_mode == "zone_50":
            poi_mid = (poi.top + poi.bottom) / 2
            if (bullish and last_close > poi_mid) or (not bullish and last_close < poi_mid):
                return None, "Prix pas au-delà des 50% de l'order block POI"

    # 3) Entry-tier confirmation
    want_sweep = "low_sweep" if bullish else "high_sweep"
    recent_sweeps = [s for s in sweeps_entry
                     if s.kind == want_sweep and last_idx - s.idx <= recent_window]
    recent_choch = [e for e in events_entry
                    if e.kind == "CHoCH" and e.direction == direction and last_idx - e.idx <= recent_window]
    chosen_sweep = recent_sweeps[-1] if recent_sweeps else None

    if require_sequence:
        # Imposed sequence: liquidity sweep FIRST, then a CHoCH in the bias direction.
        if not chosen_sweep:
            return None, "Pas de sweep de liquidité récent (entrée)"
        if not any(e.idx > chosen_sweep.idx for e in recent_choch):
            return None, "Pas de CHoCH après le sweep (séquence non respectée)"
    else:
        if not (recent_sweeps or recent_choch):
            return None, "Pas de sweep ni CHoCH récent (entrée)"

    # 3bis) Displacement (Synthèse V3 §Étape 5) : la cassure doit être un déplacement FORT,
    #       défini comme « la bougie de cassure laisse une FVG » (D5①).
    if require_displacement:
        recent_events = [e for e in events_entry
                         if e.direction == direction and last_idx - e.idx <= recent_window]
        if not any(e.displacement for e in recent_events):
            return None, "Pas de displacement sur la cassure (entrée)"

    # 4) Strict FVG: price must sit inside an unfilled FVG of the bias direction
    if require_fvg:
        fvg_ok = any(
            f.direction == direction and not f.filled and f.bottom <= last_close <= f.top
            for f in fvgs_entry
        )
        if not fvg_ok:
            return None, "Prix hors d'une FVG non comblée (entrée)"

    # 5) Entry / SL / TP
    entry = last_close
    if bullish:
        sweep_low = candles_entry[chosen_sweep.idx]["low"] if chosen_sweep else poi.bottom
        sl = min(poi.bottom, sweep_low) * 0.999
        # TP — "range_bound" (défaut, B4②) : la borne OPPOSÉE du dealing range, qui EST la
        # liquidité visée (Manuel §5.1, Synthèse V3 §Étape 9 « TP3 : borne opposée du range »).
        # "nearest_swing" : ancien comportement, le swing opposé le plus proche du niveau structure.
        tp = None
        if tp_target == "range_bound" and pd_struct.get("top", 0) > entry:
            tp = pd_struct["top"]
        if tp is None:
            targets = [s.price for s in swings_target if s.kind == "high" and s.price > entry]
            if not targets:
                return None, "Pas de liquidité haussière cible"
            tp = min(targets)
        risk, reward = entry - sl, tp - entry
    else:
        sweep_high = candles_entry[chosen_sweep.idx]["high"] if chosen_sweep else poi.top
        sl = max(poi.top, sweep_high) * 1.001
        tp = None
        if tp_target == "range_bound" and 0 < pd_struct.get("bottom", 0) < entry:
            tp = pd_struct["bottom"]
        if tp is None:
            targets = [s.price for s in swings_target if s.kind == "low" and s.price < entry]
            if not targets:
                return None, "Pas de liquidité baissière cible"
            tp = max(targets)
        risk, reward = sl - entry, entry - tp

    if risk <= 0:
        return None, "Placement SL invalide"
    rr = reward / risk
    if rr < min_rr:
        return None, f"RR {rr:.2f} < min {min_rr}"

    side = "buy" if bullish else "sell"
    zone = "discount" if bullish else "premium"
    sig = Signal(
        side=side, entry=entry, sl=sl, tp=tp, rr=rr,
        reason=f"Sweep→CHoCH + FVG dans OB {zone} → {side.upper()} (RR 1:{rr:.2f})",
        poi_top=poi.top, poi_bottom=poi.bottom,
    )
    return sig, None


def analyze(candles_bias: List[Candle], candles_struct: List[Candle], candles_entry: List[Candle],
            candles_daily: Optional[List[Candle]] = None,
            fractal_n: int = 3, min_rr: float = 2.0, recent_window: int = 6,
            require_fvg: bool = True, require_sequence: bool = True,
            require_unmitigated: bool = True, require_pd: bool = True,
            ob_entry_mode: str = "close",
            swing_method: str = "two_candle", swing_confirm: int = 2,
            ob_zone: str = "wick", break_mode: str = "close",
            tp_target: str = "range_bound", max_ob_touches: int = 0,
            require_displacement: bool = False,
            require_daily_bias: bool = False, require_po3: bool = False,
            po3_wick_ratio: float = 0.20) -> Dict[str, Any]:
    """Top-down SMC analysis sur 4 étages (Synthèse V3 §2) :
    contexte journalier (D1) → biais (HTF) → structure/POI (MTF) → déclencheur (LTF).

    L'étage journalier est OPTIONNEL et non bloquant : sans historique D1 exploitable,
    l'analyse se déroule exactement comme avant sur 3 étages.
    Returns dict with detections + optional signal at the latest entry candle."""
    out: Dict[str, Any] = {
        "bias": None,
        "swings_htf": [],
        "structure_htf": [],
        "order_blocks_htf": [],
        "swings_ltf": [],
        "structure_ltf": [],
        "order_blocks_ltf": [],
        "fvgs_ltf": [],
        "sweeps_ltf": [],
        "premium_discount": None,
        # Contexte journalier (4e etage) : Daily Bias PDH/PDL + Power of 3. None si
        # l'historique D1 n'est pas fourni ou trop court.
        "daily": None,
        "signal": None,
        "reject_reason": None,
        # Stade atteint avant le rejet : insufficient | no_bias | no_poi | entry.
        # Seul "entry" = vrai quasi-setup (POI trouvée, entrée tentée puis échouée).
        "reject_stage": None,
    }
    min_len = max(fractal_n * 2, swing_confirm * 2) + 5
    if len(candles_bias) < min_len or len(candles_struct) < min_len or len(candles_entry) < min_len:
        out["reject_reason"] = "Insufficient candles"
        out["reject_stage"] = "insufficient"
        return out

    def _swings(candles):
        return find_swings(candles, n=fractal_n, method=swing_method, confirm=swing_confirm)

    # --- Tier 0: CONTEXTE JOURNALIER (D1) — Daily Bias + Power of 3 ---
    daily = daily_context(candles_daily, po3_wick_ratio, swing_method, swing_confirm,
                          fractal_n, break_mode)
    out["daily"] = asdict(daily) if daily else None

    # --- Tier 1: BIAS (HTF) — direction only ---
    swings_bias = _swings(candles_bias)
    fvgs_bias = detect_fvgs(candles_bias)
    events_bias = detect_structure(candles_bias, swings_bias, break_mode, fvgs_bias)
    out["swings_htf"] = [asdict(s) for s in swings_bias]
    out["structure_htf"] = [asdict(e) for e in events_bias]
    bias = events_bias[-1].direction if events_bias else None
    out["bias"] = bias

    # --- Tier 2: STRUCTURE / POI (MTF) — order blocks + dealing range ---
    swings_struct = _swings(candles_struct)
    fvgs_struct = detect_fvgs(candles_struct)
    events_struct = detect_structure(candles_struct, swings_struct, break_mode, fvgs_struct)
    obs_struct = detect_order_blocks(candles_struct, events_struct, ob_zone)
    pd_struct = dealing_range(swings_struct, events_struct)
    out["order_blocks_htf"] = [asdict(o) for o in obs_struct]
    out["premium_discount"] = pd_struct

    # --- Tier 3: ENTRY trigger (LTF) — sweeps, CHoCH, FVG ---
    swings_entry = _swings(candles_entry)
    fvgs_entry = detect_fvgs(candles_entry)
    events_entry = detect_structure(candles_entry, swings_entry, break_mode, fvgs_entry)
    obs_entry = detect_order_blocks(candles_entry, events_entry, ob_zone)
    sweeps_entry = detect_liquidity_sweeps(candles_entry, swings_entry)
    out["swings_ltf"] = [asdict(s) for s in swings_entry]
    out["structure_ltf"] = [asdict(e) for e in events_entry]
    out["order_blocks_ltf"] = [asdict(o) for o in obs_entry]
    out["fvgs_ltf"] = [asdict(f) for f in fvgs_entry]
    out["sweeps_ltf"] = [asdict(s) for s in sweeps_entry]

    if not bias or not pd_struct:
        out["reject_reason"] = "Pas de biais HTF ou pas de range défini"
        out["reject_stage"] = "no_bias"
        return out

    # Filtres du contexte journalier — OFF par défaut (D2②) : les chiffres de la
    # Synthèse V3 viennent d'indices, pas de l'or. À valider en backtest sur XAUUSD
    # avant d'en faire un verrou. Sans historique D1, ces filtres ne peuvent rien rejeter.
    if require_daily_bias and daily:
        if not daily.bias:
            out["reject_reason"] = f"Pas de Daily Bias ({daily.bias_reason})"
            out["reject_stage"] = "no_bias"
            return out
        if daily.bias != bias:
            out["reject_reason"] = f"Biais HTF contraire au Daily Bias ({daily.bias_reason})"
            out["reject_stage"] = "no_bias"
            return out
    if require_po3 and daily and daily.po3_direction and daily.po3_direction != bias:
        out["reject_reason"] = f"Power of 3 contraire au biais ({daily.po3_reason})"
        out["reject_stage"] = "no_bias"
        return out

    # POI: order block on the structure tier, in the bias direction, optionally unmitigated only.
    poi_obs = [o for o in obs_struct if o.direction == bias]
    if require_unmitigated:
        poi_obs = [o for o in poi_obs if not o.mitigated]
    # Fraîcheur (D7②) : 0 = filtre désactivé. Sinon on écarte l'OB déjà retouché
    # `max_ob_touches` fois AVANT la bougie courante du niveau structure.
    if max_ob_touches > 0:
        last_struct_idx = len(candles_struct) - 1
        poi_obs = [o for o in poi_obs
                   if sum(1 for t in o.touch_idx if t < last_struct_idx) < max_ob_touches]
    if not poi_obs:
        if max_ob_touches > 0:
            out["reject_reason"] = "Aucun order block assez frais dans le sens du biais"
        elif require_unmitigated:
            out["reject_reason"] = "Aucun order block non mitigé dans le sens du biais"
        else:
            out["reject_reason"] = "Aucun order block dans le sens du biais"
        out["reject_stage"] = "no_poi"
        return out

    # Build the entry candidate from the latest entry-tier candle.
    # recent_window is in candles: 6 candles = 6 min in M1 scalping, 30 min in M5 intraday.
    last = candles_entry[-1]
    last_idx = len(candles_entry) - 1
    last_close = last["close"]

    sig, reason = _build_signal(
        bias, candles_entry, last_close, last_idx, poi_obs, pd_struct,
        swings_struct, sweeps_entry, events_entry, fvgs_entry,
        min_rr, recent_window, require_fvg, require_sequence, require_pd,
        ob_entry_mode, tp_target, require_displacement,
    )
    if sig is None:
        out["reject_reason"] = reason
        # near_miss = prix bien placé (dans la POI + bonne zone) mais déclencheur/RR
        # manquant = vrai quasi-setup à journaliser. out_of_zone = prix mal placé = bruit.
        out["reject_stage"] = "out_of_zone" if reason in _OUT_OF_ZONE_REASONS else "near_miss"
    else:
        out["signal"] = asdict(sig)
    return out
