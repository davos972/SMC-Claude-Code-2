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
    // Zones ajoutées d'après le Manuel de détection SMC (2026-08-25)
    bgIFVG: "rgba(169, 116, 255, 0.14)",
    borderIFVG: "rgba(169, 116, 255, 0.95)",
    bgBPR: "rgba(94, 200, 217, 0.14)",
    borderBPR: "rgba(94, 200, 217, 0.95)",
    bgBreaker: "rgba(255, 140, 66, 0.12)",
    borderBreaker: "rgba(255, 140, 66, 0.95)",
    bgMitigation: "rgba(120, 160, 255, 0.12)",
    borderMitigation: "rgba(120, 160, 255, 0.95)",
    bgRejection: "rgba(200, 200, 210, 0.10)",
    borderRejection: "rgba(200, 200, 210, 0.85)",
    bgOTE: "rgba(227, 179, 65, 0.10)",
    borderOTE: "rgba(227, 179, 65, 0.55)",
    bsl: "#3FB68B",
    ssl: "#E0635E",
    asia: "#8A94A6",
    inducement: "#E3B341",
};

// Calques affichables. Les 5 historiques sont ON, les zones ajoutées sont OFF :
// la Synthèse V3 §10 met en garde contre l'empilement de tous les concepts à la fois
// (« cet empilement ne se produit quasiment jamais et paralyse l'exécution »).
// Chacun s'active à la demande et le choix est mémorisé sur l'appareil.
const LAYERS = [
    { key: "ob", label: "OB" },
    { key: "fvg", label: "FVG" },
    { key: "struct", label: "BOS" },
    { key: "swings", label: "HH/LL" },
    { key: "sweeps", label: "Sweep" },
    { key: "liquidity", label: "BSL/SSL" },
    { key: "inducement", label: "Induc." },
    { key: "asia", label: "Asia" },
    { key: "ote", label: "OTE" },
    { key: "ifvg", label: "IFVG" },
    { key: "bpr", label: "BPR" },
    { key: "blocks", label: "BRK/MB/RB" },
];
const DEFAULT_LAYERS = {
    ob: true, fvg: true, struct: true, swings: true, sweeps: true,
    liquidity: false, inducement: false, asia: false, ote: false,
    ifvg: false, bpr: false, blocks: false,
};
const LAYERS_KEY = "goldflow.chartLayers";

function loadLayers() {
    try {
        const raw = window.localStorage.getItem(LAYERS_KEY);
        return raw ? { ...DEFAULT_LAYERS, ...JSON.parse(raw) } : { ...DEFAULT_LAYERS };
    } catch (e) {
        return { ...DEFAULT_LAYERS };
    }
}

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
    const [layers, setLayers] = useState(loadLayers);

    const toggleLayer = useCallback((key) => {
        setLayers((prev) => {
            const next = { ...prev, [key]: !prev[key] };
            try { window.localStorage.setItem(LAYERS_KEY, JSON.stringify(next)); } catch (e) { /* ignore */ }
            return next;
        });
    }, []);

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
        (layers.ob ? analysis.order_blocks_htf || [] : []).slice(-3).forEach((ob, k) => {
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
        (layers.fvg ? analysis.fvgs_ltf || [] : []).filter((f) => !f.filled).slice(-5).forEach((fvg, k) => {
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
        (layers.struct ? analysis.structure_htf || [] : []).slice(-2).forEach((e, k) => {
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
        (layers.swings ? analysis.swings_ltf || [] : []).slice(-10).forEach((sw, k) => {
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
        (layers.sweeps ? analysis.sweeps_ltf || [] : []).filter((s) => !s.mitigated).slice(-6).forEach((s, k) => {
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

        // --- Zones rectangulaires ajoutées (IFVG, BPR, Breaker, Mitigation, Rejection) ---
        // Même rendu que les OB/FVG : bordure + fond translucide, estompé si la zone est
        // déjà invalidée. Chaque famille a sa propre couleur pour rester distinguable.
        const zoneFamilies = [
            { on: layers.ifvg, items: analysis.ifvgs_ltf, take: 3, tag: "IFVG",
              border: COLORS.borderIFVG, bg: COLORS.bgIFVG, dashed: false },
            { on: layers.bpr, items: analysis.bprs_htf, take: 3, tag: "BPR",
              border: COLORS.borderBPR, bg: COLORS.bgBPR, dashed: false },
            { on: layers.blocks, items: analysis.breaker_blocks_htf, take: 2, tag: "BRK",
              border: COLORS.borderBreaker, bg: COLORS.bgBreaker, dashed: true },
            { on: layers.blocks, items: analysis.mitigation_blocks_htf, take: 2, tag: "MB",
              border: COLORS.borderMitigation, bg: COLORS.bgMitigation, dashed: true },
            { on: layers.blocks, items: analysis.rejection_blocks_htf, take: 2, tag: "RB",
              border: COLORS.borderRejection, bg: COLORS.bgRejection, dashed: true },
        ];
        zoneFamilies.forEach((fam) => {
            if (!fam.on) return;
            (fam.items || []).slice(-fam.take).forEach((z, k) => {
                const x1 = timeToX(z.time);
                const yTop = priceToY(z.top);
                const yBot = priceToY(z.bottom);
                if (x1 == null || yTop == null || yBot == null) return;
                const x2 = containerWidth - 8;
                const opacity = z.mitigated ? 0.25 : 1;
                boxes.push({
                    key: `${fam.tag}-${k}-${z.idx ?? z.start_idx}`,
                    left: Math.min(x1, x2), top: Math.min(yTop, yBot),
                    width: Math.max(2, Math.abs(x2 - x1)),
                    height: Math.max(6, Math.abs(yBot - yTop)),
                    style: {
                        border: `1px ${fam.dashed ? "dashed" : "solid"} ${fam.border}`,
                        background: fam.bg, opacity, borderRadius: 3,
                    },
                    testid: `smc-zone-${fam.tag.toLowerCase()}`,
                });
                labels.push({
                    key: `${fam.tag}-l-${k}-${z.idx ?? z.start_idx}`,
                    left: Math.min(x1, x2) + 4, top: Math.min(yTop, yBot) - 14,
                    text: `${fam.tag} ${z.direction === "bullish" ? "↑" : "↓"}`,
                    color: fam.border, opacity,
                });
            });
        });

        // --- Zone OTE (retracement 62-79%) : bande sur toute la largeur ---
        if (layers.ote && analysis.ote) {
            const yTop = priceToY(analysis.ote.top);
            const yBot = priceToY(analysis.ote.bottom);
            if (yTop != null && yBot != null) {
                boxes.push({
                    key: "ote-band",
                    left: 0, top: Math.min(yTop, yBot),
                    width: containerWidth - 8, height: Math.max(6, Math.abs(yBot - yTop)),
                    style: {
                        border: `1px dashed ${COLORS.borderOTE}`,
                        background: COLORS.bgOTE, borderRadius: 2,
                    },
                    testid: "smc-zone-ote",
                });
                labels.push({
                    key: "ote-l", left: 4, top: Math.min(yTop, yBot) - 14,
                    text: "OTE 62-79%", color: COLORS.borderOTE, opacity: 1,
                });
            }
        }

        // --- Inducement : le piège à stops juste avant la POI ---
        if (layers.inducement && analysis.inducement) {
            const ind = analysis.inducement;
            const x = timeToX(ind.time);
            const y = priceToY(ind.price);
            if (x != null && y != null) {
                labels.push({
                    key: "inducement-l", left: x - 10, top: y + 6,
                    text: ind.swept ? "IND pris" : "IND",
                    color: COLORS.inducement, bold: true,
                    opacity: ind.swept ? 0.5 : 1,
                });
            }
        }

        setOverlayBoxes(boxes);
        setOverlayLabels(labels);
    }, [candles, analysis, layers]);

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

            // Niveaux de liquidité : ce sont des NIVEAUX horizontaux, pas des zones —
            // une price line traverse tout le graphique, ce qui est exactement la
            // lecture du manuel (« ligne horizontale prolongée vers la droite »).
            const addLine = (price, color, title, style = 2) => {
                if (price == null) return;
                try {
                    priceLinesRef.current.push(series.createPriceLine({
                        price, color, lineWidth: 1, lineStyle: style,
                        axisLabelVisible: false, title,
                    }));
                } catch (err) { /* ignore */ }
            };

            if (layers.liquidity) {
                // Seulement les réservoirs encore INTACTS (ni balayés ni cassés), les plus
                // testés d'abord : c'est là que la liquidité s'accumule (Manuel §2.1).
                const liq = (analysis.liquidity_htf || [])
                    .filter((l) => !l.broken && !l.swept && l.source === "swing")
                    .sort((a, b) => b.tests - a.tests);
                liq.filter((l) => l.kind === "BSL").slice(0, 3).forEach((l) => addLine(
                    l.price, COLORS.bsl,
                    `BSL${l.tests > 1 ? ` x${l.tests}` : ""}${l.protected ? " •" : ""}`,
                    l.protected ? 0 : 2));
                liq.filter((l) => l.kind === "SSL").slice(0, 3).forEach((l) => addLine(
                    l.price, COLORS.ssl,
                    `SSL${l.tests > 1 ? ` x${l.tests}` : ""}${l.protected ? " •" : ""}`,
                    l.protected ? 0 : 2));
                // PDH / PDL du contexte journalier
                if (analysis.daily) {
                    addLine(analysis.daily.pdh, COLORS.bsl, "PDH", 3);
                    addLine(analysis.daily.pdl, COLORS.ssl, "PDL", 3);
                }
            }

            if (layers.asia && analysis.asian_range) {
                addLine(analysis.asian_range.high, COLORS.asia, "Asia H", 3);
                addLine(analysis.asian_range.low, COLORS.asia, "Asia L", 3);
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
            <LayerChips layers={layers} onToggle={toggleLayer} />
            <Legend layers={layers} />
        </div>
    );
}

function LayerChips({ layers, onToggle }) {
    return (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 border-t border-bd" data-testid="smc-layers">
            {LAYERS.map((l) => (
                <button
                    key={l.key}
                    type="button"
                    onClick={() => onToggle(l.key)}
                    aria-pressed={!!layers[l.key]}
                    data-testid={`smc-layer-${l.key}`}
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium border transition-colors ${
                        layers[l.key]
                            ? "border-gold text-gold bg-gold/10"
                            : "border-bd text-text-secondary"
                    }`}
                >
                    {l.label}
                </button>
            ))}
        </div>
    );
}

function Legend({ layers = DEFAULT_LAYERS }) {
    return (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1.5 px-3 py-2 border-t border-bd text-[11px] text-text-secondary">
            {layers.fvg && <LegendItem label="FVG haussier" border={COLORS.borderBull} bg={COLORS.bgBull} />}
            {layers.fvg && <LegendItem label="FVG baissier" border={COLORS.borderBear} bg={COLORS.bgBear} />}
            {layers.ob && <LegendItem label="Order Block" border={COLORS.borderOB} bg={COLORS.bgOB} dashed />}
            {layers.struct && <LegendItem label="BOS/CHoCH" line color={COLORS.bos} />}
            {layers.sweeps && <LegendItem label="Sweep" arrow color={COLORS.sweep} />}
            {layers.swings && <LegendItem label="Structure HH/HL/LH/LL" structure />}
            <LegendItem label="50% Premium/Discount" line color="#A974FF" />
            {layers.liquidity && <LegendItem label="BSL / SSL (• = protégé)" line color={COLORS.bsl} />}
            {layers.asia && <LegendItem label="Range asiatique" line color={COLORS.asia} />}
            {layers.ote && <LegendItem label="OTE 62-79%" border={COLORS.borderOTE} bg={COLORS.bgOTE} dashed />}
            {layers.ifvg && <LegendItem label="IFVG" border={COLORS.borderIFVG} bg={COLORS.bgIFVG} />}
            {layers.bpr && <LegendItem label="BPR" border={COLORS.borderBPR} bg={COLORS.bgBPR} />}
            {layers.blocks && <LegendItem label="Breaker" border={COLORS.borderBreaker} bg={COLORS.bgBreaker} dashed />}
            {layers.blocks && <LegendItem label="Mitigation" border={COLORS.borderMitigation} bg={COLORS.bgMitigation} dashed />}
            {layers.blocks && <LegendItem label="Rejection" border={COLORS.borderRejection} bg={COLORS.bgRejection} dashed />}
            {layers.inducement && <LegendItem label="Inducement" arrow color={COLORS.inducement} />}
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
