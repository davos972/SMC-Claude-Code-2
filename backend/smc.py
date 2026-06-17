"""Smart Money Concepts engine — SHARED between live bot and backtester.

Inputs: list of OHLC candles in ascending time order.
Each candle: {"time": iso_str_or_epoch, "open": f, "high": f, "low": f, "close": f}

Outputs of analyze(): dict with detected swings, structure events (BOS/CHoCH),
order blocks, fair value gaps, liquidity sweeps, current bias, premium/discount,
and any actionable signal at the latest candle.
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


@dataclass
class StructureEvent:
    idx: int
    time: Any
    kind: Literal["BOS", "CHoCH"]
    direction: Literal["bullish", "bearish"]
    price: float
    swing_idx: int = -1
    swing_time: Any = None


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

def find_swings(candles: List[Candle], n: int = 3) -> List[Swing]:
    """Fractal swings: candle is a swing high if its high is strictly greater
    than highs of n candles on each side. Same for low."""
    swings: List[Swing] = []
    L = len(candles)
    for i in range(n, L - n):
        h = candles[i]["high"]
        lo = candles[i]["low"]
        is_high = all(candles[i - j]["high"] < h and candles[i + j]["high"] < h for j in range(1, n + 1))
        is_low = all(candles[i - j]["low"] > lo and candles[i + j]["low"] > lo for j in range(1, n + 1))
        if is_high:
            swings.append(Swing(idx=i, time=candles[i]["time"], price=h, kind="high"))
        if is_low:
            swings.append(Swing(idx=i, time=candles[i]["time"], price=lo, kind="low"))
    return swings


def detect_structure(candles: List[Candle], swings: List[Swing]) -> List[StructureEvent]:
    """Detect BOS / CHoCH events.

    Logic:
    - Track current bias (None at start)
    - For each candle after a swing, if close > last bearish swing high, bullish BOS (if bias already bullish) or CHoCH (if bias bearish)
    """
    events: List[StructureEvent] = []
    bias: Optional[str] = None
    last_high: Optional[Swing] = None
    last_low: Optional[Swing] = None
    swing_iter = iter(swings)
    next_swing = next(swing_iter, None)

    for i, c in enumerate(candles):
        # update swings reaching index i
        while next_swing is not None and next_swing.idx <= i:
            if next_swing.kind == "high":
                last_high = next_swing
            else:
                last_low = next_swing
            next_swing = next(swing_iter, None)

        close = c["close"]
        # Bullish break: close above last confirmed swing high
        if last_high and close > last_high.price:
            kind = "BOS" if bias == "bullish" else "CHoCH"
            events.append(StructureEvent(
                idx=i, time=c["time"], kind=kind, direction="bullish",
                price=last_high.price, swing_idx=last_high.idx, swing_time=last_high.time,
            ))
            bias = "bullish"
            last_high = None  # consume
        elif last_low and close < last_low.price:
            kind = "BOS" if bias == "bearish" else "CHoCH"
            events.append(StructureEvent(
                idx=i, time=c["time"], kind=kind, direction="bearish",
                price=last_low.price, swing_idx=last_low.idx, swing_time=last_low.time,
            ))
            bias = "bearish"
            last_low = None
    return events


def detect_order_blocks(candles: List[Candle], events: List[StructureEvent]) -> List[OrderBlock]:
    """The Order Block is the last opposite-color candle before the impulsive
    move that caused the BOS/CHoCH event.

    OB body (top/bottom) is the candle BODY (open/close), not the wicks.
    Invalidation ("mitigated"): a later candle CLOSES through the OB (price genuinely
    broke the level), NOT merely a wick tap. This matters because the entry logic needs
    price to RETURN into the OB to trade it — counting that first tap as "mitigated"
    would make the `require_unmitigated_ob` filter reject every valid setup.
    Same philosophy as the liquidity-sweep mitigation (close-through = consumed).
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
        # body of the candle
        top = max(c["open"], c["close"])
        bottom = min(c["open"], c["close"])
        ob = OrderBlock(
            start_idx=j, end_idx=ev.idx, top=top, bottom=bottom,
            direction=ev.direction, time=c["time"],
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
    """Compute current range premium/discount based on most recent swing high and low."""
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


# ---------------- analysis pipeline ----------------

def _build_signal(direction, candles_entry, last_close, last_idx, poi, pd_struct,
                  swings_target, sweeps_entry, events_entry, fvgs_entry,
                  min_rr, recent_window, require_fvg, require_sequence):
    """Evaluate the entry trigger on the entry timeframe for a given HTF bias direction.
    Returns (Signal, None) if all conditions pass, else (None, reject_reason)."""
    bullish = direction == "bullish"

    # 1) Premium/Discount (range computed on the structure tier)
    if bullish and last_close > pd_struct["mid"]:
        return None, "Prix hors zone discount"
    if not bullish and last_close < pd_struct["mid"]:
        return None, "Prix hors zone premium"

    # 2) Price must be inside the POI (structure-tier order block)
    if bullish:
        if not (poi.bottom <= last_close <= poi.top * 1.001):
            return None, "Prix hors de l'order block POI"
    else:
        if not (poi.bottom * 0.999 <= last_close <= poi.top):
            return None, "Prix hors de l'order block POI"

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
        targets = [s.price for s in swings_target if s.kind == "high" and s.price > entry]
        if not targets:
            return None, "Pas de liquidité haussière cible"
        tp = min(targets)
        risk, reward = entry - sl, tp - entry
    else:
        sweep_high = candles_entry[chosen_sweep.idx]["high"] if chosen_sweep else poi.top
        sl = max(poi.top, sweep_high) * 1.001
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
            fractal_n: int = 3, min_rr: float = 2.0, recent_window: int = 6,
            require_fvg: bool = True, require_sequence: bool = True,
            require_unmitigated: bool = True) -> Dict[str, Any]:
    """Top-down 3-tier SMC analysis: bias (HTF) → structure/POI (MTF) → entry trigger (LTF).
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
        "signal": None,
        "reject_reason": None,
    }
    min_len = fractal_n * 2 + 5
    if len(candles_bias) < min_len or len(candles_struct) < min_len or len(candles_entry) < min_len:
        out["reject_reason"] = "Insufficient candles"
        return out

    # --- Tier 1: BIAS (HTF) — direction only ---
    swings_bias = find_swings(candles_bias, n=fractal_n)
    events_bias = detect_structure(candles_bias, swings_bias)
    out["swings_htf"] = [asdict(s) for s in swings_bias]
    out["structure_htf"] = [asdict(e) for e in events_bias]
    bias = events_bias[-1].direction if events_bias else None
    out["bias"] = bias

    # --- Tier 2: STRUCTURE / POI (MTF) — order blocks + dealing range ---
    swings_struct = find_swings(candles_struct, n=fractal_n)
    events_struct = detect_structure(candles_struct, swings_struct)
    obs_struct = detect_order_blocks(candles_struct, events_struct)
    pd_struct = premium_discount(swings_struct)
    out["order_blocks_htf"] = [asdict(o) for o in obs_struct]
    out["premium_discount"] = pd_struct

    # --- Tier 3: ENTRY trigger (LTF) — sweeps, CHoCH, FVG ---
    swings_entry = find_swings(candles_entry, n=fractal_n)
    events_entry = detect_structure(candles_entry, swings_entry)
    obs_entry = detect_order_blocks(candles_entry, events_entry)
    fvgs_entry = detect_fvgs(candles_entry)
    sweeps_entry = detect_liquidity_sweeps(candles_entry, swings_entry)
    out["swings_ltf"] = [asdict(s) for s in swings_entry]
    out["structure_ltf"] = [asdict(e) for e in events_entry]
    out["order_blocks_ltf"] = [asdict(o) for o in obs_entry]
    out["fvgs_ltf"] = [asdict(f) for f in fvgs_entry]
    out["sweeps_ltf"] = [asdict(s) for s in sweeps_entry]

    if not bias or not pd_struct:
        out["reject_reason"] = "Pas de biais HTF ou pas de range défini"
        return out

    # POI: order block on the structure tier, in the bias direction, optionally unmitigated only.
    poi_obs = [o for o in obs_struct if o.direction == bias]
    if require_unmitigated:
        poi_obs = [o for o in poi_obs if not o.mitigated]
    if not poi_obs:
        out["reject_reason"] = ("Aucun order block non mitigé dans le sens du biais"
                                if require_unmitigated
                                else "Aucun order block dans le sens du biais")
        return out
    poi = poi_obs[-1]

    # Build the entry candidate from the latest entry-tier candle.
    # recent_window is in candles: 6 candles = 6 min in M1 scalping, 30 min in M5 intraday.
    last = candles_entry[-1]
    last_idx = len(candles_entry) - 1
    last_close = last["close"]

    # TP cible la liquidité du niveau STRUCTURE (MTF, ex. M15) — même étage que la POI —
    # et non plus un swing HTF lointain : cibles plus proches → meilleur taux de réussite.
    sig, reason = _build_signal(
        bias, candles_entry, last_close, last_idx, poi, pd_struct,
        swings_struct, sweeps_entry, events_entry, fvgs_entry,
        min_rr, recent_window, require_fvg, require_sequence,
    )
    if sig is None:
        out["reject_reason"] = reason
    else:
        out["signal"] = asdict(sig)
    return out
