import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { AlertTriangle, X } from "lucide-react";
import StartStopButton from "../components/StartStopButton";
import SessionRail from "../components/SessionRail";
import KPICard from "../components/KPICard";
import SMCChart from "../components/SMCChart";
import SegmentedControl from "../components/SegmentedControl";
import SignalLog from "../components/SignalLog";
import { endpoints } from "../api/client";
import { fmtMoney, fmtPrice, fmtPnL, fmtTime } from "../lib/format";

const TIMEFRAME_OPTIONS = [
    { value: "H1", label: "H1" },
    { value: "M5", label: "M5" },
    { value: "M1", label: "M1" },
];

export default function Dashboard({ botState, settings, refresh }) {
    const [timeframe, setTimeframe] = useState("M5");
    const [account, setAccount] = useState(null);
    const [positions, setPositions] = useState([]);
    const [price, setPrice] = useState(null);
    const [candles, setCandles] = useState([]);
    const [analysis, setAnalysis] = useState(null);
    const [chartError, setChartError] = useState(null);
    const [signals, setSignals] = useState([]);
    const [news, setNews] = useState({ events: [], pause: null, error: null });
    const [configured, setConfigured] = useState(true);
    const [busy, setBusy] = useState(false);
    const [analyzedAt, setAnalyzedAt] = useState(null);
    const analyzingRef = React.useRef(false);

    const symbol = settings?.active_symbol || "XAUUSD";

    const loadData = useCallback(async () => {
        try {
            const [acc, pos, pr, sig, nw] = await Promise.all([
                endpoints.account(), endpoints.positions(), endpoints.price(symbol),
                endpoints.signals(20), endpoints.news("USD"),
            ]);
            setAccount(acc.data?.data || null);
            setConfigured(acc.data?.configured !== false);
            setPositions(pos.data?.data || []);
            setPrice(pr.data?.data || null);
            setSignals(sig.data || []);
            setNews(nw.data || { events: [], pause: null });
        } catch (err) {
            console.error("Dashboard load failed:", err);
        }
    }, [symbol]);

    const loadCandles = useCallback(async (tf) => {
        try {
            const { data } = await endpoints.candles(symbol, tf, 200);
            if (data?.configured === false) {
                setCandles([]);
                setChartError("MetaApi non configuré.");
                return;
            }
            if (data?.error) {
                setCandles([]);
                setChartError(data.error);
                return;
            }
            const list = data?.data || [];
            setCandles(list);
            setChartError(list.length === 0 ? "Aucune bougie reçue pour cette période." : null);
        } catch (err) {
            console.error("Failed to load candles:", err);
            setCandles([]);
            setChartError("Erreur de chargement des bougies.");
        }
    }, [symbol]);

    // Continuous SMC analysis: runs automatically (no manual button). persist=false so the
    // auto-refresh never writes to the signal journal — only the running bot persists signals.
    // Analyse the SAME timeframe that is selected on the chart (M1→M1, M5→M5, H1→H1) so the
    // SMC zones always match the displayed candles.
    const loadAnalysis = useCallback(async () => {
        if (analyzingRef.current) return; // avoid overlapping requests
        analyzingRef.current = true;
        try {
            const { data } = await endpoints.runAnalysis(symbol, false, timeframe);
            if (data?.result) {
                setAnalysis(data.result);
                setAnalyzedAt(new Date());
            }
        } catch (err) {
            console.error("Auto-analysis failed:", err);
        } finally {
            analyzingRef.current = false;
        }
    }, [symbol, timeframe]);

    useEffect(() => {
        loadData();
        loadCandles(timeframe);
        const t = setInterval(loadData, 5000);
        return () => clearInterval(t);
    }, [loadData, loadCandles, timeframe]);

    // Auto-run the SMC analysis on arrival and refresh it every 20s.
    useEffect(() => {
        loadAnalysis();
        const t = setInterval(loadAnalysis, 20000);
        return () => clearInterval(t);
    }, [loadAnalysis]);

    const onStart = async () => {
        setBusy(true);
        try {
            const { data } = await endpoints.botStart();
            if (data.error) toast.error(data.error);
            else toast.success("Bot démarré");
            refresh && refresh();
        } finally { setBusy(false); }
    };

    const onStop = async () => {
        setBusy(true);
        try {
            await endpoints.botStop();
            toast("Bot arrêté");
            refresh && refresh();
        } finally { setBusy(false); }
    };

    const running = botState?.running;
    const effective = botState?.effective_status;
    const statusLabel = ({
        active: "Bot en marche",
        out_of_session: "Hors session",
        stopped: "Bot arrêté",
    })[effective] || "Bot arrêté";

    const balance = account?.balance;
    const equity = account?.equity;
    const pnlDay = account ? (account.equity - account.balance) : null;
    const currency = account?.currency || "€";

    const priceVal = price?.bid || price?.ask;

    return (
        <div className="space-y-4 animate-fade-in">
            {!configured && <DegradedBanner />}
            {news?.pause && (
                <div className="bg-gold/10 border border-gold/30 rounded-card p-3 flex items-start gap-2" data-testid="news-pause-banner">
                    <AlertTriangle className="w-4 h-4 text-gold mt-0.5" />
                    <div className="text-sm">
                        <span className="font-semibold text-gold">Pause actualité.</span>{" "}
                        <span className="text-text-secondary">
                            {news.pause.event?.title} — reprise dans ~{Math.round(news.pause.diff_min)} min.
                        </span>
                    </div>
                </div>
            )}

            {/* START/STOP + status */}
            <div className="bg-panel border border-bd rounded-card p-5">
                <div className="flex items-center gap-5">
                    <StartStopButton running={running} onClick={running ? onStop : onStart} disabled={busy} />
                    <div className="flex-1 min-w-0 space-y-1">
                        <div className="text-xl font-semibold leading-tight" data-testid="bot-status-label">{statusLabel}</div>
                        <div className="text-sm text-text-secondary">
                            Mode {settings?.trading_mode || "intraday"} · {settings?.signal_only_mode ? "Signal" : "Signal + exécution"}
                        </div>
                        <div className="text-sm text-text-secondary">
                            Pertes consécutives :{" "}
                            <span className="num text-text-primary font-semibold">{botState?.consec_losses || 0}</span>
                            <span className="text-text-secondary"> / </span>
                            <span className="num text-text-primary font-semibold">{botState?.max_consec_losses || 3}</span>
                        </div>
                        <div className="text-sm text-text-secondary">
                            Drawdown jour :{" "}
                            <span className="num text-text-primary font-semibold">0,0%</span>
                            <span className="text-text-secondary"> / </span>
                            <span className="num text-text-primary font-semibold">{(botState?.max_drawdown_pct || 3).toFixed(1).replace(".", ",")}%</span>
                        </div>
                    </div>
                </div>
                <div className="mt-5">
                    <SessionRail rail={botState?.rail} />
                </div>
            </div>

            {/* KPI grid */}
            <div className="grid grid-cols-3 gap-3">
                <KPICard label="SOLDE" value={fmtMoney(balance, currency, 0)} testid="kpi-balance" />
                <KPICard label="ÉQUITÉ" value={fmtMoney(equity, currency, 0)} testid="kpi-equity" />
                <KPICard
                    label="P&L JOUR"
                    value={pnlDay !== null ? fmtPnL(pnlDay, currency) : "—"}
                    accent={pnlDay > 0 ? "positive" : pnlDay < 0 ? "negative" : "default"}
                    testid="kpi-pnl"
                />
            </div>

            {/* Chart card */}
            <div className="bg-panel border border-bd rounded-card p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex items-baseline gap-2 min-w-0">
                        <span className="text-xl font-bold tracking-wide">{symbol}</span>
                        <span className="num text-gold text-xl font-semibold truncate" data-testid="symbol-price">
                            {priceVal ? fmtPrice(priceVal) : "—"}
                        </span>
                    </div>
                    <div className="flex-shrink-0 w-[160px]">
                        <SegmentedControl
                            options={TIMEFRAME_OPTIONS}
                            value={timeframe}
                            onChange={(v) => { setAnalysis(null); setTimeframe(v); }}
                            testid="timeframe-select"
                        />
                    </div>
                </div>
                <SMCChart candles={candles} analysis={analysis} errorMessage={chartError} />
                <div className="flex items-center justify-center gap-2 text-xs text-text-secondary" data-testid="analysis-status">
                    <span className={`w-1.5 h-1.5 rounded-full ${analyzedAt ? "bg-green animate-pulse" : "bg-text-secondary"}`} />
                    {analysis?.bias && (
                        <span>
                            Biais{" "}
                            <span className={`font-semibold ${analysis.bias === "bullish" ? "text-green" : "text-red"}`}>
                                {analysis.bias === "bullish" ? "haussier ↑" : "baissier ↓"}
                            </span>
                            {" · "}
                        </span>
                    )}
                    <span>
                        Analyse SMC en continu{analyzedAt ? ` · maj ${fmtTime(analyzedAt)}` : "…"}
                    </span>
                </div>
            </div>

            {/* Positions */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Positions ouvertes
                </div>
                {positions && positions.length > 0 ? (
                    <div data-testid="open-positions">
                        {positions.map((p) => (
                            <PositionRow key={p.id} p={p} onClose={loadData} />
                        ))}
                    </div>
                ) : (
                    <div className="text-sm text-text-secondary py-4 text-center">
                        Aucune position ouverte
                    </div>
                )}
            </div>

            {/* Signal log */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="flex items-center justify-between mb-2">
                    <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary">
                        Journal des signaux
                    </div>
                </div>
                <SignalLog signals={signals} />
            </div>

            {/* News */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Annonces éco du jour — USD
                </div>
                {news?.error && (
                    <div className="text-sm text-red mb-2" data-testid="news-error">{news.error}</div>
                )}
                <NewsList events={news?.events || []} />
            </div>
        </div>
    );
}

function PositionRow({ p, onClose }) {
    const side = (p.type || "").toLowerCase().includes("buy") || p.type === 0 ? "buy" : "sell";
    const profit = Number(p.profit ?? p.unrealizedProfit ?? 0);
    const [closing, setClosing] = useState(false);

    const handleClose = async () => {
        if (!window.confirm(`Fermer la position ${side.toUpperCase()} ${p.symbol} ?`)) return;
        setClosing(true);
        try {
            await endpoints.closePosition(p.id);
            toast.success("Position fermée");
            onClose && onClose();
        } catch {
            toast.error("Erreur lors de la clôture");
        } finally {
            setClosing(false);
        }
    };

    return (
        <div className="py-2 border-b border-bd last:border-0" data-testid="position-row">
            <div className="flex items-center gap-3">
                <span className={`px-2 py-1 rounded-md text-[11px] font-bold flex-shrink-0 ${side === "buy" ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}>
                    {side.toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                    <div className="font-semibold">{p.symbol}</div>
                    <div className="text-xs text-text-secondary num">
                        {Number(p.volume).toFixed(2)} lot · entrée {fmtPrice(p.openPrice || p.openingPrice)}
                    </div>
                </div>
                <div className={`num font-bold flex-shrink-0 ${profit >= 0 ? "text-green" : "text-red"}`}>
                    {profit >= 0 ? "+" : ""}{profit.toFixed(2)}
                </div>
                <button
                    onClick={handleClose}
                    disabled={closing}
                    title="Fermer la position"
                    className="w-8 h-8 rounded-lg border border-red/40 text-red flex items-center justify-center hover:bg-red/10 transition-colors disabled:opacity-40 flex-shrink-0"
                    data-testid="close-position-button"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
            {(p.stopLoss || p.takeProfit) && (
                <div className="flex gap-4 mt-1 pl-16">
                    {p.stopLoss && (
                        <span className="text-[11px] text-red num">SL {fmtPrice(p.stopLoss)}</span>
                    )}
                    {p.takeProfit && (
                        <span className="text-[11px] text-green num">TP {fmtPrice(p.takeProfit)}</span>
                    )}
                </div>
            )}
        </div>
    );
}

function NewsList({ events }) {
    if (!events || events.length === 0) {
        return <div className="text-sm text-text-secondary py-2">Aucune annonce à venir.</div>;
    }
    return (
        <div className="space-y-2">
            {events.slice(0, 5).map((e) => (
                <div key={`${e.date}-${e.title}`} className="flex items-center gap-3 py-1" data-testid="news-row">
                    <span className={`w-2 h-2 rounded-full ${
                        e.impact === "high" ? "bg-red" : e.impact === "medium" ? "bg-gold" : "bg-text-secondary"
                    }`} />
                    <span className="text-sm flex-1 truncate">{e.title}</span>
                    <span className="text-xs text-text-secondary num">{fmtTime(e.date)}</span>
                </div>
            ))}
        </div>
    );
}

function DegradedBanner() {
    return (
        <div className="bg-gold/10 border border-gold/30 rounded-card p-3 flex items-start gap-2" data-testid="degraded-banner">
            <AlertTriangle className="w-5 h-5 text-gold mt-0.5 flex-shrink-0" />
            <div className="text-sm">
                <span className="font-semibold text-gold">MetaApi non configuré.</span>{" "}
                <span className="text-text-secondary">
                    Renseigne ton token et accountId dans <strong>Réglages</strong> pour activer les données réelles et le trading.
                </span>
            </div>
        </div>
    );
}
