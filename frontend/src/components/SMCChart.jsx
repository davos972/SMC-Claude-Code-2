import React, { useEffect, useRef, useState, useCallback } from "react";
import { createChart, CandlestickSeries, LineSeries } from "lightweight-charts";
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
export default function SMCChart({ candles, analysis, height = 320, errorMessage }) {
    const containerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRef = useRef(null);
    const lineSeriesRef = useRef([]); // BOS/CHoCH line series
    const priceLinesRef = useRef([]); // premium/discount mid line
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
        const timesByIdx = candles.map((c) => toUnixTime(c.time));
        const lastTime = timesByIdx[timesByIdx.length - 1];
        const containerWidth = containerRef.current?.clientWidth || 480;

        const boxes = [];
        const labels = [];

        const timeToX = (idx) => {
            const t = timesByIdx[Math.min(idx, timesByIdx.length - 1)];
            const x = ts.timeToCoordinate(t);
            return x == null ? null : x;
        };
        const priceToY = (price) => {
            const y = series.priceToCoordinate(price);
            return y == null ? null : y;
        };

        // --- Order Blocks (dashed gold) ---
        (analysis.order_blocks_htf || []).slice(-6).forEach((ob, k) => {
            const x1 = timeToX(ob.start_idx);
            // Right edge: mitigated_idx if mitigated else last candle (extend forward)
            const endIdx = ob.mitigated && ob.mitigated_idx >= 0 ? ob.mitigated_idx : candles.length - 1;
            const x2raw = timeToX(endIdx);
            const x2 = ob.mitigated ? x2raw : (x2raw != null ? Math.max(x2raw, containerWidth - 8) : null);
            const yTop = priceToY(ob.top);
            const yBot = priceToY(ob.bottom);
            if (x1 == null || x2 == null || yTop == null || yBot == null) return;
            const opacity = ob.mitigated ? 0.25 : 1;
            boxes.push({
                key: `ob-${k}-${ob.start_idx}`,
                left: Math.min(x1, x2), top: Math.min(yTop, yBot),
                width: Math.max(2, Math.abs(x2 - x1)), height: Math.max(2, Math.abs(yBot - yTop)),
                style: {
                    border: `1.5px dashed ${COLORS.borderOB}`,
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

        // --- FVG (solid colored border, green/red) ---
        (analysis.fvgs_ltf || []).slice(-10).forEach((fvg, k) => {
            const x1 = timeToX(fvg.idx);
            const endIdx = fvg.filled && fvg.filled_idx >= 0 ? fvg.filled_idx : candles.length - 1;
            const x2raw = timeToX(endIdx);
            const x2 = fvg.filled ? x2raw : (x2raw != null ? Math.max(x2raw, containerWidth - 8) : null);
            const yTop = priceToY(fvg.top);
            const yBot = priceToY(fvg.bottom);
            if (x1 == null || x2 == null || yTop == null || yBot == null) return;
            const isBull = fvg.direction === "bullish";
            const opacity = fvg.filled ? 0.25 : 1;
            boxes.push({
                key: `fvg-${k}-${fvg.idx}`,
                left: Math.min(x1, x2), top: Math.min(yTop, yBot),
                width: Math.max(2, Math.abs(x2 - x1)), height: Math.max(2, Math.abs(yBot - yTop)),
                style: {
                    border: `1.5px solid ${isBull ? COLORS.borderBull : COLORS.borderBear}`,
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

        // --- BOS / CHoCH labels (blue) — line itself drawn via LineSeries below ---
        (analysis.structure_htf || []).slice(-6).forEach((e, k) => {
            const xEnd = timeToX(e.idx);
            const y = priceToY(e.price);
            if (xEnd == null || y == null) return;
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

        setOverlayBoxes(boxes);
        setOverlayLabels(labels);
    }, [candles, analysis]);

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
            recomputeOverlay();
        };
        window.addEventListener("resize", onResize);
        const unsubRange = chart.timeScale().subscribeVisibleTimeRangeChange(recomputeOverlay);
        const unsubCrosshair = chart.subscribeCrosshairMove(recomputeOverlay);

        return () => {
            window.removeEventListener("resize", onResize);
            try { unsubRange?.(); } catch (e) { /* ignore */ }
            try { unsubCrosshair?.(); } catch (e) { /* ignore */ }
            chart.remove();
            chartRef.current = null;
            seriesRef.current = null;
        };
    }, [height, recomputeOverlay]);

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

        // Remove previous BOS/CHoCH line series
        lineSeriesRef.current.forEach((ls) => {
            try { chart.removeSeries(ls); } catch (e) { /* ignore */ }
        });
        lineSeriesRef.current = [];
        // Remove previous priceLines
        priceLinesRef.current.forEach((pl) => {
            try { series.removePriceLine(pl); } catch (e) { /* ignore */ }
        });
        priceLinesRef.current = [];

        if (analysis) {
            // BOS / CHoCH : draw blue dashed line from swing_time to break_time at price
            (analysis.structure_htf || []).slice(-6).forEach((e) => {
                if (e.swing_idx < 0 || e.swing_idx >= data.length) return;
                const t1 = data[Math.min(e.swing_idx, data.length - 1)]?.time;
                const t2 = data[Math.min(e.idx, data.length - 1)]?.time;
                if (!t1 || !t2 || t1 === t2) return;
                try {
                    const ls = chart.addSeries(LineSeries, {
                        color: COLORS.bos,
                        lineWidth: 1,
                        lineStyle: 2, // dashed
                        priceLineVisible: false,
                        lastValueVisible: false,
                        crosshairMarkerVisible: false,
                    });
                    ls.setData([
                        { time: t1, value: e.price },
                        { time: t2, value: e.price },
                    ]);
                    lineSeriesRef.current.push(ls);
                } catch (err) { console.error("addLineSeries failed:", err); }
            });

            // Sweep markers : red arrows
            const markers = [];
            (analysis.sweeps_ltf || []).slice(-12).forEach((s) => {
                const ts = data[Math.min(s.idx, data.length - 1)]?.time;
                if (!ts) return;
                if (s.kind === "high_sweep") {
                    markers.push({
                        time: ts, position: "aboveBar",
                        color: COLORS.sweep, shape: "arrowDown", text: "SWEEP",
                    });
                } else {
                    markers.push({
                        time: ts, position: "belowBar",
                        color: COLORS.sweep, shape: "arrowUp", text: "SWEEP",
                    });
                }
            });
            try { series.setMarkers && series.setMarkers(markers); } catch (e) { console.error("setMarkers:", e); }

            // Premium/Discount mid as gold dotted line
            const pd = analysis.premium_discount;
            if (pd?.mid) {
                try {
                    const line = series.createPriceLine({
                        price: pd.mid,
                        color: "#E3B341",
                        lineWidth: 1,
                        lineStyle: 3, // dotted
                        axisLabelVisible: false,
                        title: "50% (P/D)",
                    });
                    priceLinesRef.current.push(line);
                } catch (err) { /* ignore */ }
            }
        }

        chart.timeScale().fitContent();
        // Defer overlay compute until after the chart settles its layout
        requestAnimationFrame(recomputeOverlay);
    }, [candles, analysis, recomputeOverlay]);

    const showError = errorMessage || (!candles || candles.length === 0);

    return (
        <div className="w-full bg-bg rounded-card border border-bd overflow-hidden" data-testid="smc-chart">
            <div className="relative" style={{ height }}>
                <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
                <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ height }}>
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
                                fontWeight: l.bold ? 700 : 600,
                                color: l.color,
                                opacity: l.opacity,
                                background: "rgba(13,17,23,0.65)",
                                padding: "0 4px",
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
        </div>
    );
}

function LegendItem({ label, border, bg, dashed, line, arrow, color }) {
    let swatch;
    if (line) {
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
