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
    Mitigation: a subsequent candle's wick or body re-enters the OB zone.
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
        # Mitigation: scan forward
        for k in range(j + 1, len(candles)):
            cand = candles[k]
            if ob.direction == "bullish":
                if cand["low"] <= ob.top:  # price came back into OB
                    ob.mitigated = True
                    ob.mitigated_idx = k
                    ob.mitigated_time = cand["time"]
                    break
            else:
                if cand["high"] >= ob.bottom:
                    ob.mitigated = True
                    ob.mitigated_idx = k
                    ob.mitigated_time = cand["time"]
                    break
        obs.append(ob)
    return obs


def detect_fvgs(candles: List[Candle]) -> List[FVG]:
    """3-candle FVG: gap between c1.high and c3.low (bullish) or c1.low and c3.high (bearish).
    Also marks `filled` and `filled_idx` if a subsequent candle closes the gap."""
    fvgs: List[FVG] = []
    for i in range(2, len(candles)):
        c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
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

def analyze(candles_htf: List[Candle], candles_ltf: List[Candle], fractal_n: int = 3,
            min_rr: float = 2.0, recent_window: int = 6) -> Dict[str, Any]:
    """Run full SMC analysis. Returns dict with detections + optional signal at latest LTF candle."""
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
    if len(candles_htf) < fractal_n * 2 + 5 or len(candles_ltf) < fractal_n * 2 + 5:
        out["reject_reason"] = "Insufficient candles"
        return out

    # HTF analysis
    swings_htf = find_swings(candles_htf, n=fractal_n)
    events_htf = detect_structure(candles_htf, swings_htf)
    obs_htf = detect_order_blocks(candles_htf, events_htf)

    out["swings_htf"] = [asdict(s) for s in swings_htf]
    out["structure_htf"] = [asdict(e) for e in events_htf]
    out["order_blocks_htf"] = [asdict(o) for o in obs_htf]

    bias = events_htf[-1].direction if events_htf else None
    out["bias"] = bias

    # LTF analysis
    swings_ltf = find_swings(candles_ltf, n=fractal_n)
    events_ltf = detect_structure(candles_ltf, swings_ltf)
    obs_ltf = detect_order_blocks(candles_ltf, events_ltf)
    fvgs_ltf = detect_fvgs(candles_ltf)
    sweeps_ltf = detect_liquidity_sweeps(candles_ltf, swings_ltf)
    pd = premium_discount(swings_htf)

    out["swings_ltf"] = [asdict(s) for s in swings_ltf]
    out["structure_ltf"] = [asdict(e) for e in events_ltf]
    out["order_blocks_ltf"] = [asdict(o) for o in obs_ltf]
    out["fvgs_ltf"] = [asdict(f) for f in fvgs_ltf]
    out["sweeps_ltf"] = [asdict(s) for s in sweeps_ltf]
    out["premium_discount"] = pd

    if not bias or not pd:
        out["reject_reason"] = "No HTF bias or no defined range"
        return out

    # Build signal candidate from the last LTF candle
    last = candles_ltf[-1]
    last_idx = len(candles_ltf) - 1
    last_close = last["close"]

    # Must have a recent CHoCH or sweep on LTF (within `recent_window` candles,
    # configurable: 6 candles = 6 min in M1 scalping but 30 min in M5 intraday).
    recent_sweeps = [s for s in sweeps_ltf if last_idx - s.idx <= recent_window]
    recent_choch = [e for e in events_ltf if e.kind == "CHoCH" and last_idx - e.idx <= recent_window]

    poi_obs = [o for o in obs_htf if o.direction == bias]
    if not poi_obs:
        out["reject_reason"] = "No HTF order block matching bias"
        return out
    poi = poi_obs[-1]

    # Must be in discount (for bullish) or premium (for bearish)
    if bias == "bullish":
        if last_close > pd["mid"]:
            out["reject_reason"] = "Price not in discount zone"
            return out
        if not (poi.bottom <= last_close <= poi.top * 1.001):
            out["reject_reason"] = "Price not inside HTF order block"
            return out
        if not (recent_sweeps or recent_choch):
            out["reject_reason"] = "No LTF sweep or CHoCH confirmation in POI"
            return out
        # Build signal
        entry = last_close
        sl = poi.bottom * 0.999
        # TP = next opposite liquidity: nearest swing high above
        target_highs = [s.price for s in swings_htf if s.kind == "high" and s.price > entry]
        if not target_highs:
            out["reject_reason"] = "No upward liquidity target"
            return out
        tp = min(target_highs)
        risk = entry - sl
        reward = tp - entry
        if risk <= 0:
            out["reject_reason"] = "Invalid SL placement"
            return out
        rr = reward / risk
        if rr < min_rr:
            out["reject_reason"] = f"RR {rr:.2f} < min {min_rr}"
            return out
        out["signal"] = asdict(Signal(
            side="buy", entry=entry, sl=sl, tp=tp, rr=rr,
            reason=f"Sweep/CHoCH LTF dans OB H1 discount → BUY (RR 1:{rr:.2f})",
            poi_top=poi.top, poi_bottom=poi.bottom,
        ))
        return out

    else:  # bearish
        if last_close < pd["mid"]:
            out["reject_reason"] = "Price not in premium zone"
            return out
        if not (poi.bottom * 0.999 <= last_close <= poi.top):
            out["reject_reason"] = "Price not inside HTF order block"
            return out
        if not (recent_sweeps or recent_choch):
            out["reject_reason"] = "No LTF sweep or CHoCH confirmation in POI"
            return out
        entry = last_close
        sl = poi.top * 1.001
        target_lows = [s.price for s in swings_htf if s.kind == "low" and s.price < entry]
        if not target_lows:
            out["reject_reason"] = "No downward liquidity target"
            return out
        tp = max(target_lows)
        risk = sl - entry
        reward = entry - tp
        if risk <= 0:
            out["reject_reason"] = "Invalid SL placement"
            return out
        rr = reward / risk
        if rr < min_rr:
            out["reject_reason"] = f"RR {rr:.2f} < min {min_rr}"
            return out
        out["signal"] = asdict(Signal(
            side="sell", entry=entry, sl=sl, tp=tp, rr=rr,
            reason=f"Sweep/CHoCH LTF dans OB H1 premium → SELL (RR 1:{rr:.2f})",
            poi_top=poi.top, poi_bottom=poi.bottom,
        ))
        return out
