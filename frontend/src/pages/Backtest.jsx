import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, History as HistoryIcon, X, Trash2, ChevronRight } from "lucide-react";
import SegmentedControl from "../components/SegmentedControl";
import SMCChart from "../components/SMCChart";
import { endpoints } from "../api/client";
import { fmtMoney, fmtPct, fmtPrice, fmtDate, fmtTime } from "../lib/format";

const MODE_OPTIONS = [
    { value: "intraday", label: "Intraday (H1 → M5)" },
    { value: "scalping", label: "Scalping (M15 → M1)" },
];

export default function Backtest({ settings }) {
    const [from, setFrom] = useState(() => new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10));
    const [to, setTo] = useState(() => new Date().toISOString().slice(0, 10));
    const today = new Date().toISOString().slice(0, 10);
    const [mode, setMode] = useState(settings?.trading_mode || "intraday");
    const [spread, setSpread] = useState(settings?.default_spread_points || 25);
    const [current, setCurrent] = useState(null);
    const [polling, setPolling] = useState(false);
    const [history, setHistory] = useState([]);
    const [selectedTrade, setSelectedTrade] = useState(null);
    const [tradeChart, setTradeChart] = useState({ loading: false, candles: [], analysis: null, error: null });
    const [liveSpread, setLiveSpread] = useState(null); // real broker spread (AXI) via MetaApi
    // Trailing stop — ce backtest uniquement (le bot live ne l'applique jamais).
    const [trailingMode, setTrailingMode] = useState("off");
    const [trailingTriggerR, setTrailingTriggerR] = useState(1.0);
    const [trailingDistanceR, setTrailingDistanceR] = useState(1.0);
    const [trailingLookback, setTrailingLookback] = useState(5);
    const [trailingBuffer, setTrailingBuffer] = useState(0.0);

    useEffect(() => {
        endpoints.listBacktests().then(({ data }) => setHistory(data || []))
            .catch((e) => console.error("listBacktests failed:", e));
    }, []);

    // Fetch the live broker spread (ask − bid) and use it as the realistic default.
    useEffect(() => {
        endpoints.symbolSpread("XAUUSD").then(({ data }) => {
            if (data?.configured && typeof data.spread_points === "number") {
                setLiveSpread(data);
                setSpread(data.spread_points);
            }
        }).catch((e) => console.error("symbolSpread failed:", e));
    }, []);

    useEffect(() => {
        if (!polling || !current?.id) return;
        const t = setInterval(async () => {
            try {
                const { data } = await endpoints.getBacktest(current.id);
                setCurrent(data);
                if (data.status === "done" || data.status === "error") {
                    setPolling(false);
                    endpoints.listBacktests().then(({ data }) => setHistory(data || []));
                    if (data.status === "done") toast.success("Backtest terminé");
                    if (data.status === "error") toast.error(data.error || "Erreur backtest");
                }
            } catch (err) { console.error("Backtest poll failed:", err); }
        }, 1500);
        return () => clearInterval(t);
    }, [polling, current?.id]);

    const onStart = async () => {
        try {
            const { data } = await endpoints.startBacktest({
                symbol: "XAUUSD",
                start_date: from,
                end_date: to,
                mode,
                spread_points: Number(spread),
                trailing_mode: trailingMode,
                trailing_trigger_r: Number(trailingTriggerR),
                trailing_distance_r: Number(trailingDistanceR),
                trailing_lookback: Number(trailingLookback),
                trailing_buffer: Number(trailingBuffer),
            });
            setCurrent({ ...data, progress: 0, status: "pending", trades: [], metrics: {}, equity_curve: [] });
            setPolling(true);
            toast("Backtest lancé…");
        } catch (e) {
            toast.error("Impossible de lancer le backtest");
        }
    };

    const onCancel = async (id) => {
        try {
            await endpoints.cancelBacktest(id);
            toast("Backtest annulé");
            setPolling(false);
            const { data } = await endpoints.getBacktest(id);
            setCurrent(data);
        } catch (e) {
            toast.error("Échec de l'annulation");
        }
    };

    const onOpenHistory = async (h) => {
        try {
            const { data } = await endpoints.getBacktest(h.id);
            setSelectedTrade(null);
            setPolling(false);
            setCurrent(data);
            window.scrollTo({ top: 0, behavior: "smooth" });
        } catch (e) {
            toast.error("Impossible de charger ce backtest");
        }
    };

    const onDelete = async (id, clearCurrent = false) => {
        if (!window.confirm("Supprimer définitivement ce backtest ?")) return;
        try {
            await endpoints.cancelBacktest(id);
            if (clearCurrent) setCurrent(null);
            endpoints.listBacktests().then(({ data }) => setHistory(data || []));
            toast("Backtest supprimé");
        } catch (e) {
            toast.error("Échec de la suppression");
        }
    };

    return (
        <div className="space-y-4 animate-fade-in" data-testid="backtest-page">
            <div className="bg-panel border border-bd rounded-card p-4 space-y-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary">
                    Nouveau backtest
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">Du</label>
                        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} max={today}
                            className="num w-full mt-1 bg-bg border border-bd rounded-xl px-3 py-3 text-sm focus:border-gold focus:outline-none"
                            data-testid="backtest-from" />
                    </div>
                    <div>
                        <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">Au</label>
                        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} max={today}
                            className="num w-full mt-1 bg-bg border border-bd rounded-xl px-3 py-3 text-sm focus:border-gold focus:outline-none"
                            data-testid="backtest-to" />
                    </div>
                </div>

                <div>
                    <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">Configuration</label>
                    <SegmentedControl
                        value={mode}
                        onChange={setMode}
                        options={MODE_OPTIONS}
                        testid="backtest-mode"
                    />
                </div>

                <div>
                    <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">Spread moyen simulé</label>
                    <div className="relative mt-1">
                        <input type="number" value={spread} onChange={(e) => setSpread(e.target.value)} min="0"
                            className="num w-full bg-bg border border-bd rounded-xl px-3 py-3 text-sm focus:border-gold focus:outline-none"
                            data-testid="backtest-spread" />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary text-sm">points</span>
                    </div>
                    {liveSpread ? (
                        <div className="text-xs text-text-secondary mt-1.5 flex items-center gap-2 flex-wrap" data-testid="backtest-live-spread">
                            <span>Spread live AXI : <span className="num text-text-primary">{liveSpread.spread_points} pts</span> (≈ {liveSpread.spread_price} $)</span>
                            {Number(spread) !== liveSpread.spread_points && (
                                <button type="button" onClick={() => setSpread(liveSpread.spread_points)}
                                    className="text-gold underline hover:brightness-110" data-testid="apply-live-spread">
                                    appliquer
                                </button>
                            )}
                        </div>
                    ) : (
                        <div className="text-xs text-text-secondary mt-1.5">
                            Compté une fois par trade (coût aller-retour). Mets une moyenne un peu plus haute que le spread calme pour intégrer news/ouvertures.
                        </div>
                    )}
                </div>

                <div>
                    <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">
                        Trailing stop (ce backtest uniquement)
                    </label>
                    <select value={trailingMode} onChange={(e) => setTrailingMode(e.target.value)}
                        className="num w-full mt-1 bg-bg border border-bd rounded-xl px-3 py-3 text-sm focus:border-gold focus:outline-none"
                        data-testid="backtest-trailing-mode">
                        <option value="off">Désactivé</option>
                        <option value="breakeven">Break-even (SL ramené au prix d&apos;entrée)</option>
                        <option value="r_trail">Trailing par R (verrouille le profit)</option>
                        <option value="structure">Trailing structurel (suit les bougies)</option>
                    </select>
                    <div className="text-xs text-text-secondary mt-1.5">
                        N&apos;affecte que ce backtest, jamais le bot en live. Réduit surtout le drawdown.
                    </div>
                    {trailingMode !== "off" && (
                        <div className="grid grid-cols-2 gap-3 mt-3">
                            <TInput label="Déclenche à (R)" value={trailingTriggerR} onChange={setTrailingTriggerR} step="0.1" testid="backtest-trailing-trigger" />
                            {trailingMode === "r_trail" && (
                                <TInput label="Distance (R)" value={trailingDistanceR} onChange={setTrailingDistanceR} step="0.1" testid="backtest-trailing-distance" />
                            )}
                            {trailingMode === "structure" && (
                                <TInput label="Lookback (bougies)" value={trailingLookback} onChange={setTrailingLookback} step="1" testid="backtest-trailing-lookback" />
                            )}
                            {(trailingMode === "breakeven" || trailingMode === "structure") && (
                                <TInput label="Buffer (prix)" value={trailingBuffer} onChange={setTrailingBuffer} step="0.01" testid="backtest-trailing-buffer" />
                            )}
                        </div>
                    )}
                </div>

                <button onClick={onStart} disabled={polling}
                    className="w-full py-3.5 bg-gold text-bg font-bold rounded-xl text-center hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                    data-testid="run-backtest-button">
                    <Play className="w-4 h-4" fill="currentColor" />
                    <span>{polling ? "En cours…" : "Lancer le backtest"}</span>
                </button>

                {current && (
                    <div className="space-y-2 pt-2 border-t border-bd" data-testid="backtest-progress">
                        <div className="flex items-center justify-between text-xs">
                            <span className="text-text-secondary uppercase tracking-widest font-bold">
                                {({pending: "En file…", running: "Progression", done: "Terminé", error: "Échec"})[current.status] || current.status}
                            </span>
                            <span className="num">{current.progress?.toFixed(0) || 0}%</span>
                        </div>
                        <div className="w-full h-2 bg-bg rounded-full overflow-hidden">
                            <div className="h-full bg-gold transition-all" style={{ width: `${current.progress || 0}%` }} />
                        </div>
                        {current.progress_label && (
                            <div className="text-xs text-text-secondary" data-testid="backtest-progress-label">
                                {current.progress_label}
                            </div>
                        )}
                        {current.error && (
                            <div className="text-sm text-red bg-red/10 border border-red/30 rounded-xl p-3 mt-2" data-testid="backtest-error">
                                <div className="font-semibold mb-1">Erreur :</div>
                                <div className="text-text-secondary break-words">{current.error}</div>
                            </div>
                        )}
                        {(current.status === "running" || current.status === "pending") && (
                            <button
                                type="button"
                                onClick={() => onCancel(current.id)}
                                className="w-full mt-2 py-2 border border-red/40 text-red rounded-xl text-sm font-semibold flex items-center justify-center gap-2 hover:bg-red/10 transition-colors"
                                data-testid="cancel-backtest-button"
                            >
                                <X className="w-4 h-4" /> Annuler le backtest
                            </button>
                        )}
                        {(current.status === "error" || current.status === "done") && (
                            <button
                                type="button"
                                onClick={() => onDelete(current.id, true)}
                                className="w-full mt-2 py-2 border border-bd text-text-secondary rounded-xl text-sm flex items-center justify-center gap-2 hover:border-red/40 hover:text-red transition-colors"
                                data-testid="delete-current-backtest-button"
                            >
                                <Trash2 className="w-4 h-4" /> Supprimer ce backtest
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* Results */}
            {current?.status === "done" && (
                <Results bt={current} onSelectTrade={setSelectedTrade} />
            )}

            {selectedTrade && (
                <TradeDetail
                    trade={selectedTrade}
                    mode={current?.mode || "intraday"}
                    symbol={current?.symbol || "XAUUSD"}
                    chart={tradeChart}
                    onLoadChart={async () => {
                        setTradeChart({ loading: true, candles: [], analysis: null, error: null });
                        try {
                            const { data } = await endpoints.analysisAtTime(
                                current?.symbol || "XAUUSD",
                                selectedTrade.entry_time,
                                current?.mode || "intraday",
                            );
                            if (data?.configured === false) {
                                setTradeChart({ loading: false, candles: [], analysis: null, error: "MetaApi non configuré." });
                            } else if (data?.error) {
                                setTradeChart({ loading: false, candles: [], analysis: null, error: data.error });
                            } else {
                                setTradeChart({ loading: false, candles: data.candles_ltf || [], analysis: data.result || null, error: null });
                            }
                        } catch (e) {
                            setTradeChart({ loading: false, candles: [], analysis: null, error: e.message });
                        }
                    }}
                    onClose={() => { setSelectedTrade(null); setTradeChart({ loading: false, candles: [], analysis: null, error: null }); }}
                />
            )}

            {/* History */}
            {history.length > 0 && (
                <div className="bg-panel border border-bd rounded-card p-4">
                    <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3 flex items-center gap-2">
                        <HistoryIcon className="w-4 h-4" /> Historique des backtests
                    </div>
                    <div className="space-y-2" data-testid="backtest-history">
                        {history.map((h) => {
                            const isOpenable = h.status === "done";
                            const isActive = current?.id === h.id;
                            const m = h.metrics || {};
                            return (
                            <div
                                key={h.id}
                                role={isOpenable ? "button" : undefined}
                                tabIndex={isOpenable ? 0 : undefined}
                                onClick={isOpenable ? () => onOpenHistory(h) : undefined}
                                onKeyDown={isOpenable ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpenHistory(h); } } : undefined}
                                data-testid="backtest-history-row"
                                className={`flex items-center justify-between gap-2 py-2 px-2 -mx-2 rounded-lg border-b border-bd last:border-0 transition-colors ${
                                    isOpenable ? "cursor-pointer hover:bg-bd/40" : ""
                                } ${isActive ? "bg-gold/5 ring-1 ring-gold/40" : ""}`}
                            >
                                <div className="text-sm flex-1 min-w-0">
                                    <div className="truncate">{fmtDate(h.start_date)} → {fmtDate(h.end_date)}</div>
                                    <div className="text-xs text-text-secondary">{h.mode} · {h.symbol}</div>
                                    {h.status === "done" && (
                                        <div className="text-xs text-text-secondary mt-0.5 num">
                                            {m.trades_count ?? 0} trades · winrate {fmtPct(m.winrate)}
                                        </div>
                                    )}
                                    {h.error && (
                                        <div className="text-xs text-red mt-0.5 truncate" title={h.error}>{h.error}</div>
                                    )}
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                    <span className={`text-xs px-2 py-1 rounded-md ${
                                        h.status === "done" ? "bg-green/15 text-green" :
                                        h.status === "error" ? "bg-red/15 text-red" :
                                        "bg-gold/15 text-gold"
                                    }`}>{h.status}</span>
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); onDelete(h.id); }}
                                        className="w-8 h-8 rounded-md border border-bd text-text-secondary hover:text-red hover:border-red/40 flex items-center justify-center transition-colors"
                                        data-testid={`delete-history-${h.id.slice(0, 8)}`}
                                        title={h.status === "running" || h.status === "pending" ? "Annuler" : "Supprimer"}
                                    >
                                        {h.status === "running" || h.status === "pending"
                                            ? <X className="w-4 h-4" />
                                            : <Trash2 className="w-4 h-4" />}
                                    </button>
                                    {isOpenable && <ChevronRight className="w-4 h-4 text-text-secondary" />}
                                </div>
                            </div>
                            );
                        })}
                    </div>
                </div>
            )}

            <div className="text-xs text-text-secondary italic px-2 text-center" data-testid="backtest-disclaimer">
                Les performances passées ne préjugent pas des performances futures.
            </div>
        </div>
    );
}

function Results({ bt, onSelectTrade }) {
    const m = bt.metrics || {};
    return (
        <>
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Résultats
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <MetricCard label="Trades" value={m.trades_count} />
                    <MetricCard label="Winrate" value={fmtPct(m.winrate)} accent="positive" />
                    <MetricCard label="Profit Factor" value={(m.profit_factor || 0).toFixed(2)} />
                    <MetricCard label="RR moyen" value={`1:${(m.avg_rr || 0).toFixed(2)}`} />
                    <MetricCard label="Drawdown max" value={fmtPct(m.max_drawdown_pct)} accent="negative" />
                    <MetricCard label="P&L total" value={m.total_pnl?.toFixed(2)} accent={m.total_pnl > 0 ? "positive" : "negative"} />
                </div>
                <EquityCurve curve={bt.equity_curve || []} />
            </div>

            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Trades ({bt.trades?.length || 0})
                </div>
                <div className="space-y-1 max-h-96 overflow-y-auto">
                    {(bt.trades || []).slice(0, 100).map((t) => (
                        <button
                            key={t.id}
                            onClick={() => onSelectTrade(t)}
                            data-testid="backtest-trade-row"
                            className="w-full text-left flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-bd/40 transition-colors"
                        >
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                t.side === "buy" ? "bg-green/15 text-green" : "bg-red/15 text-red"
                            }`}>
                                {t.side.toUpperCase()}
                            </span>
                            <span className="text-xs text-text-secondary num flex-1 truncate">{fmtDate(t.entry_time)}</span>
                            <span className={`text-xs num font-bold ${t.pnl >= 0 ? "text-green" : "text-red"}`}>
                                {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}
                            </span>
                        </button>
                    ))}
                </div>
            </div>
        </>
    );
}

function TInput({ label, value, onChange, step, testid }) {
    return (
        <div>
            <label className="text-[10px] uppercase tracking-widest text-text-secondary font-bold">{label}</label>
            <input type="number" value={value} step={step} onChange={(e) => onChange(e.target.value)}
                className="num w-full mt-1 bg-bg border border-bd rounded-xl px-3 py-2.5 text-sm focus:border-gold focus:outline-none"
                data-testid={testid} />
        </div>
    );
}

function MetricCard({ label, value, accent = "default" }) {
    const colors = { positive: "text-green", negative: "text-red", default: "text-text-primary" };
    return (
        <div className="bg-bg rounded-xl border border-bd p-3">
            <div className="text-[9px] uppercase font-bold tracking-widest text-text-secondary">{label}</div>
            <div className={`num text-lg font-bold mt-1 ${colors[accent]}`}>{value ?? "—"}</div>
        </div>
    );
}

function TradeDetail({ trade, mode, symbol, chart, onLoadChart, onClose }) {
    useEffect(() => {
        if (trade?.entry_time) {
            onLoadChart();
        }
    }, [trade?.id, trade?.entry_time, onLoadChart]);

    return (
        <div className="bg-panel border border-bd rounded-card p-4" data-testid="trade-detail">
            <div className="flex items-center justify-between mb-2">
                <div className="font-semibold">
                    {trade.side?.toUpperCase()} {symbol} —{" "}
                    <span className={trade.pnl >= 0 ? "text-green" : "text-red"}>
                        {trade.pnl >= 0 ? "+" : ""}{trade.pnl.toFixed(2)}
                    </span>
                </div>
                <button onClick={onClose} className="text-text-secondary text-sm hover:text-text-primary" data-testid="close-trade-detail">Fermer</button>
            </div>
            <div className="text-sm text-text-secondary leading-relaxed mb-3">{trade.reason}</div>
            <div className="grid grid-cols-2 gap-3 mb-3 text-sm">
                <div><span className="text-text-secondary">Entrée: </span><span className="num">{fmtPrice(trade.entry)}</span></div>
                <div><span className="text-text-secondary">Sortie: </span><span className="num">{fmtPrice(trade.exit_price)}</span></div>
                <div><span className="text-text-secondary">SL: </span><span className="num text-red">{fmtPrice(trade.sl)}</span></div>
                <div><span className="text-text-secondary">TP: </span><span className="num text-green">{fmtPrice(trade.tp)}</span></div>
                <div className="col-span-2"><span className="text-text-secondary">Entrée le: </span><span className="num">{trade.entry_time}</span></div>
            </div>
            <SMCChart
                candles={chart.candles}
                analysis={chart.analysis}
                errorMessage={chart.error || (chart.loading ? "Chargement de l'analyse SMC…" : null)}
                height={260}
            />
        </div>
    );
}

function EquityCurve({ curve }) {
    if (!curve || curve.length < 2) return null;
    const min = Math.min(...curve.map((p) => p.equity));
    const max = Math.max(...curve.map((p) => p.equity));
    const range = max - min || 1;
    const W = 320, H = 80;
    const points = curve.map((p, i) => {
        const x = (i / (curve.length - 1)) * W;
        const y = H - ((p.equity - min) / range) * H;
        return `${x},${y}`;
    }).join(" ");
    return (
        <div className="mt-4">
            <div className="text-[10px] uppercase font-bold tracking-widest text-text-secondary mb-2">Courbe d&apos;équité</div>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-20" data-testid="equity-curve">
                <polyline points={points} fill="none" stroke="#E3B341" strokeWidth="2" />
            </svg>
        </div>
    );
}
