import React, { useEffect, useRef, useState, useCallback } from "react";
import { createChart, CandlestickSeries } from "lightweight-charts";
import { AlertTriangle } from "lucide-react";

const COLORS = {
    bgBull: "rgba(63, 182, 139, 0.20)",
    borderBull: "rgba(63, 182, 139, 0.95)",
    bgBear: "rgba(224, 99, 94, 0.20)",
    borderBear: "rgba(224, 99, 94, 0.95)",
    bgOB: "rgba(227, 179, 65, 0.12)",
    borderOB: "rgba(227, 179, 65, 0.95)",
    bos: "#3B82F6",
    sweep: "#E0635E",
};

const toUnixTime = (t) => (typeof t === "number" ? t : Math.floor(new Date(t).getTime() / 1000));

/**
 * SMC chart powered by lightweight-charts.
 *  - FVG : rectangles with solid border (green for bullish, red for bearish), semi-transparent fill,
 *    extending from gap origin rightward until filled (or to chart edge if still valid).
 *  - Order Blocks : dashed yellow border, very light yellow fill, extending until mitigated.
 *  - Sweeps : red arrows pointing at the wick extremity, with "SWEEP" label.
 *  - BOS / CHoCH : blue dashed horizontal line from origin swing to break candle, with label.
 *  - Mitigated/filled zones are kept at very low opacity so they remain visible historically.
 */
export default function SMCChart({ candles, analysis, price, height = 320, errorMessage }) {
    const containerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRef = useRef(null);
    const priceLinesRef = useRef([]); // premium/discount mid line
    const lastStepRef = useRef(null); // candle spacing — to fit the view only when timeframe changes
    const [overlayBoxes, setOverlayBoxes] = useState([]);
    const [overlayLabels, setOverlayLabels] = useState([]);

    const recomputeOverlay = useCallback(() => {
        const chart = chartRef.current;
        const series = seriesRef.current;
        if (!chart || !series || !analysis || !candles || candles.length === 0) {
            setOverlayBoxes([]);
            setOverlayLabels([]);
            return;
        }
        const ts = chart.timeScale();
        // Right edge of the candle area = width of the time scale (EXCLUDES the price axis on the
        // right). Zones must stop here so they don't overflow onto the price labels.
        const containerWidth = (typeof ts.width === "function" ? ts.width() : null)
            || containerRef.current?.clientWidth || 480;

        const boxes = [];
        const labels = [];

        // Position zones by their real timestamp (not by candle index): the analysis runs on
        // its own candle arrays (HTF + LTF, 300 each) which differ from the chart's candle array,
        // so index-based positioning lands zones off-screen. Time-based mapping is robust.
        const timeToX = (rawTime) => {
            if (rawTime == null) return null;
            const x = ts.timeToCoordinate(toUnixTime(rawTime));
            return x == null ? null : x;
        };
        const priceToY = (price) => {
            const y = series.priceToCoordinate(price);
            return y == null ? null : y;
        };

        // --- Order Blocks (dashed gold box) — last few, active bold / mitigated faded ---
        (analysis.order_blocks_htf || []).slice(-3).forEach((ob, k) => {
            const x1 = timeToX(ob.time);
            // Always extend the box to the right edge of the candle area (like FVGs) so OBs stay
            // visible; mitigated ones are just faded (opacity below) rather than truncated.
            const x2 = x1 != null ? containerWidth - 8 : null;
            const yTop = priceToY(ob.top);
            const yBot = priceToY(ob.bottom);
            if (x1 == null || x2 == null || yTop == null || yBot == null) return;
            const opacity = ob.mitigated ? 0.25 : 1;
            boxes.push({
                key: `ob-${k}-${ob.start_idx}`,
                left: Math.min(x1, x2), top: Math.min(yTop, yBot),
                width: Math.max(2, Math.abs(x2 - x1)), height: Math.max(6, Math.abs(yBot - yTop)),
                style: {
                    border: `1px dashed ${COLORS.borderOB}`,
                    background: COLORS.bgOB,
                    opacity,
                    borderRadius: 2,
                },
                testid: `smc-zone-ob${ob.mitigated ? "-mitigated" : ""}`,
            });
            labels.push({
                key: `ob-l-${k}-${ob.start_idx}`,
                left: Math.min(x1, x2) + 4,
                top: Math.min(yTop, yBot) - 14,
                text: `OB ${ob.direction === "bullish" ? "↑" : "↓"}`,
                color: COLORS.borderOB,
                opacity,
            });
        });

        // --- FVG (solid colored border, green/red) — only ACTIVE (unfilled) ones ---
        (analysis.fvgs_ltf || []).filter((f) => !f.filled).slice(-5).forEach((fvg, k) => {
            const x1 = timeToX(fvg.time);
            const x2raw = fvg.filled && fvg.filled_time ? timeToX(fvg.filled_time) : (x1 != null ? containerWidth - 8 : null);
            const x2 = fvg.filled ? x2raw : (x2raw != null ? Math.max(x2raw, containerWidth - 8) : null);
            const yTop = priceToY(fvg.top);
            const yBot = priceToY(fvg.bottom);
            if (x1 == null || x2 == null || yTop == null || yBot == null) return;
            const isBull = fvg.direction === "bullish";
            const opacity = fvg.filled ? 0.25 : 1;
            boxes.push({
                key: `fvg-${k}-${fvg.idx}`,
                left: Math.min(x1, x2), top: Math.min(yTop, yBot),
                width: Math.max(2, Math.abs(x2 - x1)), height: Math.max(6, Math.abs(yBot - yTop)),
                style: {
                    border: `1px solid ${isBull ? COLORS.borderBull : COLORS.borderBear}`,
                    background: isBull ? COLORS.bgBull : COLORS.bgBear,
                    opacity,
                    borderRadius: 4,
                },
                testid: `smc-zone-fvg-${isBull ? "bull" : "bear"}${fvg.filled ? "-filled" : ""}`,
            });
            labels.push({
                key: `fvg-l-${k}-${fvg.idx}`,
                left: Math.min(x1, x2) + 4,
                top: Math.min(yTop, yBot) - 14,
                text: "FVG",
                color: isBull ? COLORS.borderBull : COLORS.borderBear,
                opacity,
            });
        });

        // --- BOS / CHoCH (blue dashed horizontal line + label), most recent only ---
        // Drawn as an HTML overlay line (not a chart LineSeries, which crashed the time scale).
        (analysis.structure_htf || []).slice(-2).forEach((e, k) => {
            const xEnd = timeToX(e.time);
            const y = priceToY(e.price);
            if (xEnd == null || y == null) return;
            const xStart = e.swing_time != null ? timeToX(e.swing_time) : null;
            if (xStart != null) {
                boxes.push({
                    key: `struct-line-${k}-${e.idx}`,
                    left: Math.min(xStart, xEnd), top: y,
                    width: Math.max(2, Math.abs(xEnd - xStart)), height: 0,
                    style: { borderTop: `1.5px dashed ${COLORS.bos}`, background: "transparent" },
                    testid: "smc-zone-bos",
                });
            }
            labels.push({
                key: `struct-l-${k}-${e.idx}`,
                left: xEnd + 4,
                top: y - 18,
                text: `${e.kind} ${e.direction === "bullish" ? "↑" : "↓"}`,
                color: COLORS.bos,
                bold: true,
                opacity: 1,
            });
        });

        // --- Swing structure labels HH / HL / LH / LL ---
        // Classify each swing against the previous swing of the same kind:
        //   high → HH (higher high) if above previous high, else LH (lower high)
        //   low  → HL (higher low)  if above previous low,  else LL (lower low)
        // Green = bullish structure (HH/HL), red = bearish structure (LH/LL).
        let prevHigh = null;
        let prevLow = null;
        (analysis.swings_ltf || []).slice(-10).forEach((sw, k) => {
            const isHigh = sw.kind === "high";
            let label;
            if (isHigh) {
                label = prevHigh == null ? "H" : (sw.price >= prevHigh ? "HH" : "LH");
                prevHigh = sw.price;
            } else {
                label = prevLow == null ? "L" : (sw.price >= prevLow ? "HL" : "LL");
                prevLow = sw.price;
            }
            const x = timeToX(sw.time);
            const y = priceToY(sw.price);
            if (x == null || y == null) return;
            const bullish = label === "HH" || label === "HL";
            labels.push({
                key: `sw-${k}-${sw.idx}`,
                left: x - 8,
                top: isHigh ? y - 16 : y + 4,
                text: label,
                color: bullish ? COLORS.borderBull : COLORS.borderBear,
                bold: true,
                opacity: 0.95,
            });
        });

        // --- Liquidity sweeps : red arrow pointing at the swept wick + "Sweep" label ---
        // high_sweep = a high was taken (arrow points DOWN onto the wick top),
        // low_sweep  = a low was taken  (arrow points UP   onto the wick bottom).
        // Drawn as HTML overlay (lightweight-charts v5 has no series.setMarkers).
        (analysis.sweeps_ltf || []).filter((s) => !s.mitigated).slice(-6).forEach((s, k) => {
            const x = timeToX(s.time);
            const y = priceToY(s.price);
            if (x == null || y == null) return;
            const isHigh = s.kind === "high_sweep";
            labels.push({
                key: `sweep-${k}-${s.idx}`,
                left: x - 14,
                top: isHigh ? y - 22 : y + 6,
                text: isHigh ? "↓ Sweep" : "↑ Sweep",
                color: COLORS.sweep,
                bold: true,
                opacity: 1,
            });
        });

        setOverlayBoxes(boxes);
        setOverlayLabels(labels);
    }, [candles, analysis]);

    // Always call the latest recomputeOverlay from chart subscriptions WITHOUT making the
    // init effect depend on it (otherwise the chart is destroyed/recreated on every data or
    // analysis update — which stacked multiple chart canvases and broke the price scale).
    const recomputeRef = useRef(recomputeOverlay);
    useEffect(() => { recomputeRef.current = recomputeOverlay; }, [recomputeOverlay]);

    // Init chart once
    useEffect(() => {
        if (!containerRef.current) return;
        const chart = createChart(containerRef.current, {
            layout: {
                background: { color: "#0D1117" },
                textColor: "#8A94A6",
                attributionLogo: false,
            },
            localization: { locale: "fr-FR" },
            grid: { vertLines: { color: "#151B24" }, horzLines: { color: "#151B24" } },
            rightPriceScale: { borderColor: "#242E3D" },
            timeScale: { borderColor: "#242E3D", timeVisible: true, secondsVisible: false, rightOffset: 5 },
            crosshair: { mode: 0 },
            width: containerRef.current.clientWidth,
            height,
            handleScroll: true,
            handleScale: true,
        });
        chartRef.current = chart;
        seriesRef.current = chart.addSeries(CandlestickSeries, {
            upColor: "#3FB68B", downColor: "#E0635E",
            borderVisible: false,
            wickUpColor: "#3FB68B", wickDownColor: "#E0635E",
        });

        const onResize = () => {
            if (containerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
            }
            recomputeRef.current();
        };
        const recompute = () => recomputeRef.current();
        window.addEventListener("resize", onResize);
        const unsubRange = chart.timeScale().subscribeVisibleTimeRangeChange(recompute);
        const unsubCrosshair = chart.subscribeCrosshairMove(recompute);

        return () => {
            window.removeEventListener("resize", onResize);
            try { unsubRange?.(); } catch (e) { /* ignore */ }
            try { unsubCrosshair?.(); } catch (e) { /* ignore */ }
            chart.remove();
            chartRef.current = null;
            seriesRef.current = null;
        };
    }, [height]);

    // Update data + markers + lines when candles/analysis change
    useEffect(() => {
        const series = seriesRef.current;
        const chart = chartRef.current;
        if (!series || !chart || !candles || candles.length === 0) return;
        const data = candles.map((c) => ({
            time: toUnixTime(c.time),
            open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close),
        })).sort((a, b) => a.time - b.time);
        series.setData(data);
        // Auto-fit the view ONLY on the first load or when the timeframe changes (detected via the
        // candle spacing), never on routine 20s refreshes — so the user can pan/zoom freely without
        // the chart snapping back to the latest price.
        const step = data.length > 1 ? data[1].time - data[0].time : null;
        if (step !== lastStepRef.current) {
            lastStepRef.current = step;
            chart.timeScale().fitContent();
        }

        // Remove previous priceLines
        priceLinesRef.current.forEach((pl) => {
            try { series.removePriceLine(pl); } catch (e) { /* ignore */ }
        });
        priceLinesRef.current = [];

        if (analysis) {
            // Sweeps are drawn as an HTML overlay in recomputeOverlay (lightweight-charts v5
            // removed series.setMarkers), so nothing to do here for them.

            // Premium/Discount mid as gold dotted line
            const pd = analysis.premium_discount;
            if (pd?.mid) {
                try {
                    const line = series.createPriceLine({
                        price: pd.mid,
                        color: "#A974FF", // violet — distinct from the gold used for Order Blocks
                        lineWidth: 1,
                        lineStyle: 3, // dotted
                        axisLabelVisible: false,
                        title: "50% (P/D)",
                    });
                    priceLinesRef.current.push(line);
                } catch (err) { /* ignore */ }
            }
        }

        // Defer overlay compute until after the chart settles its layout
        requestAnimationFrame(recomputeOverlay);
    }, [candles, analysis, recomputeOverlay]);

    // Live price → grow the current (last) candle in real time. MetaApi only returns CLOSED
    // candles, so between candle refreshes we extend the last bar's close/high/low from the live
    // bid so the user sees the price moving. series.update() with the same time updates the bar
    // (no new bar). When loadCandles brings a fresh closed candle, this effect rebases on it.
    useEffect(() => {
        const series = seriesRef.current;
        if (!series || !price || !candles || candles.length === 0) return;
        const live = Number(price.bid ?? price.ask);
        if (!live || Number.isNaN(live)) return;
        const last = candles[candles.length - 1];
        try {
            series.update({
                time: toUnixTime(last.time),
                open: Number(last.open),
                high: Math.max(Number(last.high), live),
                low: Math.min(Number(last.low), live),
                close: live,
            });
        } catch (e) { /* time older than last bar — ignore */ }
    }, [price, candles]);

    const showError = errorMessage || (!candles || candles.length === 0);

    return (
        <div className="w-full bg-bg rounded-card border border-bd overflow-hidden" data-testid="smc-chart">
            <div className="relative" style={{ height }}>
                <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
                <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ height, zIndex: 3 }}>
                    {overlayBoxes.map((b) => (
                        <div
                            key={b.key}
                            data-testid={b.testid}
                            style={{
                                position: "absolute",
                                left: `${b.left}px`,
                                top: `${b.top}px`,
                                width: `${b.width}px`,
                                height: `${b.height}px`,
                                ...b.style,
                            }}
                        />
                    ))}
                    {overlayLabels.map((l) => (
                        <span
                            key={l.key}
                            style={{
                                position: "absolute",
                                left: `${l.left}px`,
                                top: `${l.top}px`,
                                fontSize: 10,
                                fontWeight: l.bold ? 700 : 500,
                                color: l.color,
                                opacity: l.opacity,
                                background: "rgba(13,17,23,0.6)",
                                padding: "0 3px",
                                borderRadius: 3,
                                whiteSpace: "nowrap",
                                pointerEvents: "none",
                            }}
                        >
                            {l.text}
                        </span>
                    ))}
                </div>
                {showError && (
                    <div className="absolute inset-0 flex items-center justify-center bg-bg/85 backdrop-blur-sm" data-testid="smc-chart-empty">
                        <div className="max-w-[80%] text-center px-4 py-3 rounded-xl border border-bd bg-panel">
                            <AlertTriangle className="w-6 h-6 text-gold mx-auto mb-2" />
                            <div className="text-sm font-semibold text-text-primary">
                                {errorMessage || "Aucune bougie chargée"}
                            </div>
                            <div className="text-xs text-text-secondary mt-1">
                                {errorMessage
                                    ? "Vérifie ta connexion MetaApi dans Réglages."
                                    : "Vérifie ta connexion MetaApi puis recharge."}
                            </div>
                        </div>
                    </div>
                )}
            </div>
            <Legend />
        </div>
    );
}

function Legend() {
    return (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1.5 px-3 py-2 border-t border-bd text-[11px] text-text-secondary">
            <LegendItem label="FVG haussier" border={COLORS.borderBull} bg={COLORS.bgBull} />
            <LegendItem label="FVG baissier" border={COLORS.borderBear} bg={COLORS.bgBear} />
            <LegendItem label="Order Block" border={COLORS.borderOB} bg={COLORS.bgOB} dashed />
            <LegendItem label="BOS/CHoCH" line color={COLORS.bos} />
            <LegendItem label="Sweep" arrow color={COLORS.sweep} />
            <LegendItem label="Structure HH/HL/LH/LL" structure />
            <LegendItem label="50% Premium/Discount" line color="#A974FF" />
        </div>
    );
}

function LegendItem({ label, border, bg, dashed, line, arrow, color, structure }) {
    let swatch;
    if (structure) {
        swatch = (
            <span style={{ fontSize: 9, fontWeight: 700, lineHeight: 1 }} aria-hidden>
                <span style={{ color: COLORS.borderBull }}>HH</span>
                <span style={{ color: COLORS.borderBear }}>LL</span>
            </span>
        );
    } else if (line) {
        swatch = (
            <span
                style={{ width: 16, height: 0, borderTop: `1.5px dashed ${color}`, display: "inline-block" }}
                aria-hidden
            />
        );
    } else if (arrow) {
        swatch = (
            <span style={{ color, fontSize: 14, lineHeight: 1, fontWeight: 700 }} aria-hidden>↓</span>
        );
    } else {
        swatch = (
            <span
                style={{
                    width: 16, height: 10, display: "inline-block",
                    border: dashed ? `1.2px dashed ${border}` : `1.2px solid ${border}`,
                    background: bg,
                    borderRadius: 2,
                }}
                aria-hidden
            />
        );
    }
    return (
        <div className="flex items-center gap-1.5 min-w-0">
            {swatch}
            <span className="truncate">{label}</span>
        </div>
    );
}
