import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, RefreshCw, ChevronDown, Settings2 } from "lucide-react";
import { endpoints } from "../api/client";
import KPICard from "../components/KPICard";
import { fmtPct, fmtPnL, fmtMoney, fmtPrice, fmtDate, fmtTime } from "../lib/format";

// Journal de trading : les trades RÉELS du bot (collection `trades` côté backend),
// avec le P&L réel lu chez le broker. Aucune valeur n'est estimée ici — un trade
// dont le P&L est inconnu est affiché comme tel et exclu des statistiques.

const EXIT_LABELS = {
    tp: { label: "TP atteint", cls: "bg-green/15 text-green" },
    sl: { label: "SL touché", cls: "bg-red/15 text-red" },
    trailing_sl: { label: "SL suiveur", cls: "bg-gold/15 text-gold" },
    other: { label: "Clôture manuelle / auto", cls: "bg-bd text-text-secondary" },
    unknown: { label: "Sortie inconnue", cls: "bg-bd text-text-secondary" },
};

const SESSION_LABELS = { london: "Londres", newyork: "New York", unknown: "Hors session" };

export default function Stats() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const [importing, setImporting] = useState(false);
    const [importDays, setImportDays] = useState(180);
    const [openId, setOpenId] = useState(null);
    const [capitalInput, setCapitalInput] = useState("");
    const [showCapital, setShowCapital] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await endpoints.journal(500);
            setData(data);
            setError(null);
        } catch (e) {
            setError(e?.response?.data?.detail || e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const trades = useMemo(() => data?.trades || [], [data]);
    const m = data?.metrics || {};
    const currency = data?.currency || "€";
    const initial = data?.initial_balance;

    const onImport = async () => {
        setImporting(true);
        try {
            const { data: res } = await endpoints.importJournal(Number(importDays) || 180);
            toast.success(
                `${res.imported} trade(s) importé(s)` +
                (res.already_present ? ` · ${res.already_present} déjà présent(s)` : "") +
                (res.still_open ? ` · ${res.still_open} encore ouvert(s)` : ""),
            );
            await load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || e.message);
        } finally {
            setImporting(false);
        }
    };

    const onSaveCapital = async () => {
        const v = Number(String(capitalInput).replace(",", "."));
        if (Number.isNaN(v) || v < 0) { toast.error("Montant invalide"); return; }
        try {
            await endpoints.updateSettings({ journal_initial_balance: v });
            toast.success(v > 0 ? "Capital de départ enregistré" : "Capital de départ : calcul automatique");
            setShowCapital(false);
            await load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || e.message);
        }
    };

    return (
        <div className="space-y-4 animate-fade-in" data-testid="journal-page">
            <div className="flex items-center justify-between px-1">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary">
                    Journal de trading
                </div>
                <button type="button" onClick={load} disabled={loading}
                    className="text-text-secondary hover:text-gold transition-colors disabled:opacity-40"
                    data-testid="journal-refresh" title="Rafraîchir">
                    <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </button>
            </div>

            {error && (
                <div className="bg-red/10 border border-red/40 text-red rounded-card p-3 text-sm"
                     data-testid="journal-error">
                    Journal indisponible : {error}
                </div>
            )}

            {/* Métriques globales */}
            <div className="grid grid-cols-2 gap-3">
                <KPICard label="P&L global" testid="journal-pnl"
                    value={m.total_pnl === undefined ? "—" : fmtPnL(m.total_pnl, currency)}
                    accent={(m.total_pnl || 0) >= 0 ? "positive" : "negative"}
                    sub={m.pnl_pct !== null && m.pnl_pct !== undefined ? `${m.pnl_pct >= 0 ? "+" : ""}${fmtPct(m.pnl_pct)} du capital` : null} />
                <KPICard label="Trades" value={m.trades_count ?? 0} testid="journal-count"
                    sub={m.trades_count ? `${m.wins ?? 0} G · ${m.losses ?? 0} P` : null} />
                <KPICard label="Winrate" value={m.trades_count ? fmtPct(m.winrate) : "—"}
                    accent="gold" testid="journal-winrate" />
                <KPICard label="Profit factor" value={m.trades_count ? (m.profit_factor ?? 0).toFixed(2) : "—"}
                    testid="journal-pf" />
                <KPICard label="Drawdown max" testid="journal-dd" accent="negative"
                    value={m.trades_count ? (m.max_drawdown_pct !== undefined ? fmtPct(m.max_drawdown_pct) : fmtMoney(m.max_drawdown_money, currency, 2)) : "—"}
                    sub={m.max_drawdown_pct !== undefined && m.max_drawdown_money !== undefined
                        ? fmtMoney(m.max_drawdown_money, currency, 2) : null} />
                <KPICard label="RR moyen prévu" value={m.trades_count ? `1:${(m.avg_rr ?? 0).toFixed(2)}` : "—"}
                    testid="journal-rr" />
            </div>

            {(m.open_trades > 0 || m.unknown_pnl > 0) && (
                <div className="text-xs text-text-secondary px-1" data-testid="journal-notes">
                    {m.open_trades > 0 && <div>{m.open_trades} trade(s) encore ouvert(s) — non comptés dans les statistiques.</div>}
                    {m.unknown_pnl > 0 && <div>{m.unknown_pnl} trade(s) au P&L inconnu (historique broker indisponible) — exclus des statistiques.</div>}
                </div>
            )}

            {/* Courbe d'évolution vs capital de départ */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="flex items-center justify-between mb-3">
                    <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary">
                        Évolution du capital
                    </div>
                    <button type="button" onClick={() => { setShowCapital((v) => !v); setCapitalInput(initial ? String(initial) : ""); }}
                        className="text-[11px] text-text-secondary hover:text-gold flex items-center gap-1"
                        data-testid="journal-capital-toggle">
                        <Settings2 className="w-3.5 h-3.5" /> Capital de départ
                    </button>
                </div>

                {showCapital && (
                    <div className="mb-3 bg-bg border border-bd rounded-xl p-3 space-y-2">
                        <div className="text-xs text-text-secondary">
                            Montant de départ servant de référence à la courbe. Laisser 0 pour le
                            calcul automatique (solde actuel du compte moins le P&L du journal).
                        </div>
                        <div className="flex gap-2">
                            <input type="number" step="0.01" value={capitalInput}
                                onChange={(e) => setCapitalInput(e.target.value)}
                                placeholder="0 = automatique"
                                className="num flex-1 bg-panel border border-bd rounded-xl px-3 py-2 text-sm focus:border-gold focus:outline-none"
                                data-testid="journal-capital-input" />
                            <button type="button" onClick={onSaveCapital}
                                className="px-4 rounded-xl bg-gold/15 text-gold text-sm font-semibold border border-gold/40"
                                data-testid="journal-capital-save">Enregistrer</button>
                        </div>
                    </div>
                )}

                <EquityCurve curve={data?.equity_curve || []} initial={initial} currency={currency} />

                <div className="flex justify-between text-xs text-text-secondary num mt-2">
                    <span>
                        Départ : {initial ? fmtMoney(initial, currency, 2) : "inconnu"}
                        {data?.initial_balance_source === "auto" && " (auto)"}
                    </span>
                    <span className={((m.total_pnl || 0) >= 0) ? "text-green" : "text-red"}>
                        Actuel : {initial ? fmtMoney(initial + (m.total_pnl || 0), currency, 2) : fmtPnL(m.total_pnl || 0, currency)}
                    </span>
                </div>
                {!initial && (
                    <div className="text-xs text-text-secondary italic mt-2">
                        Capital de départ inconnu (MetaApi non joignable) : la courbe part de 0 et le
                        drawdown est affiché en devise, pas en pourcentage.
                    </div>
                )}
            </div>

            {/* Import de l'historique broker */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-2">
                    Importer l&apos;historique du broker
                </div>
                <div className="text-xs text-text-secondary mb-3">
                    Récupère chez MetaApi les trades du bot déjà réalisés (P&L, prix et heures réels).
                    Seules les positions portant le magic number du bot sont reprises, et les trades
                    déjà présents ne sont jamais écrasés.
                </div>
                <div className="flex gap-2">
                    <input type="number" min="1" max="1000" value={importDays}
                        onChange={(e) => setImportDays(e.target.value)}
                        className="num w-24 bg-bg border border-bd rounded-xl px-3 py-2 text-sm focus:border-gold focus:outline-none"
                        data-testid="journal-import-days" />
                    <span className="text-xs text-text-secondary self-center">jours en arrière</span>
                    <button type="button" onClick={onImport} disabled={importing}
                        className="ml-auto px-4 py-2 rounded-xl bg-gold/15 text-gold text-sm font-semibold border border-gold/40 flex items-center gap-2 disabled:opacity-50"
                        data-testid="journal-import">
                        <Download className="w-4 h-4" /> {importing ? "Import…" : "Importer"}
                    </button>
                </div>
            </div>

            {/* Détail des trades */}
            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Trades ({trades.length})
                </div>
                {trades.length === 0 && !loading && (
                    <div className="text-sm text-text-secondary" data-testid="journal-empty">
                        Aucun trade enregistré. Les trades exécutés par le bot arrivent ici
                        automatiquement ; pour les trades déjà passés, utilise le bouton
                        « Importer » ci-dessus.
                    </div>
                )}
                <div className="space-y-1">
                    {trades.map((t) => (
                        <TradeRow key={t.id} t={t} currency={currency}
                            open={openId === t.id}
                            onToggle={() => setOpenId(openId === t.id ? null : t.id)} />
                    ))}
                </div>
            </div>

            <div className="text-xs text-text-secondary text-center italic">
                Les performances passées ne préjugent pas des performances futures.
            </div>
        </div>
    );
}

function TradeRow({ t, currency, open, onToggle }) {
    const isOpen = t.status === "open";
    const pnl = typeof t.pnl === "number" ? t.pnl : null;
    const exit = EXIT_LABELS[t.exit_reason] || EXIT_LABELS.unknown;
    const notes = t.settings_notes || [];

    return (
        <div className="border-b border-bd last:border-0" data-testid="journal-trade-row">
            <button type="button" onClick={onToggle}
                className="w-full text-left flex items-center gap-2 py-2 hover:bg-bd/30 rounded-lg px-1 transition-colors">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    t.side === "buy" ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}>
                    {String(t.side || "").toUpperCase()}
                </span>
                <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">
                        {t.symbol}
                        <span className="text-text-secondary num text-xs ml-2">
                            {fmtDate(t.open_time)} · {fmtTime(t.open_time)}
                        </span>
                    </div>
                    <div className="text-[11px] text-text-secondary num">
                        RR prévu {t.planned_rr ? `1:${Number(t.planned_rr).toFixed(2)}` : "inconnu"}
                        {" · "}
                        {isOpen ? "en cours" : exit.label}
                        {notes.length > 0 && " · réglages ⚙"}
                    </div>
                </div>
                <span className={`num text-sm font-bold ${
                    isOpen ? "text-text-secondary" : pnl === null ? "text-text-secondary"
                        : pnl >= 0 ? "text-green" : "text-red"}`}>
                    {isOpen ? "—" : pnl === null ? "?" : fmtPnL(pnl, currency)}
                </span>
                <ChevronDown className={`w-4 h-4 text-text-secondary transition-transform ${open ? "rotate-180" : ""}`} />
            </button>

            {open && (
                <div className="px-1 pb-3 space-y-2 text-sm" data-testid="journal-trade-detail">
                    <div className="flex flex-wrap gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isOpen ? "bg-gold/15 text-gold" : exit.cls}`}>
                            {isOpen ? "Position ouverte" : exit.label}
                        </span>
                        {t.session && (
                            <span className="px-2 py-0.5 rounded text-[10px] bg-bd text-text-secondary">
                                {SESSION_LABELS[t.session] || t.session}
                            </span>
                        )}
                        {t.mode && (
                            <span className="px-2 py-0.5 rounded text-[10px] bg-bd text-text-secondary">
                                {t.mode}{t.timeframe ? ` · ${t.timeframe}` : ""}
                            </span>
                        )}
                        {t.source === "import" && (
                            <span className="px-2 py-0.5 rounded text-[10px] bg-bd text-text-secondary">
                                importé du broker
                            </span>
                        )}
                    </div>

                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        <Field label="Ouverture" value={`${fmtDate(t.open_time)} ${fmtTime(t.open_time)}`} />
                        <Field label="Clôture" value={t.close_time ? `${fmtDate(t.close_time)} ${fmtTime(t.close_time)}` : "—"} />
                        <Field label="Volume" value={t.volume ? `${t.volume} lot` : "—"} />
                        <Field label="RR prévu" value={t.planned_rr ? `1:${Number(t.planned_rr).toFixed(2)}` : "inconnu"} />
                        <Field label="Entrée" value={fmtPrice(t.entry)} />
                        <Field label="Sortie" value={fmtPrice(t.exit_price)} />
                        <Field label="SL" value={fmtPrice(t.sl)} cls="text-red" />
                        <Field label="TP" value={fmtPrice(t.tp)} cls="text-green" />
                        {t.sl_initial !== undefined && t.sl_initial !== null && t.sl_initial !== t.sl && (
                            <Field label="SL d'origine" value={fmtPrice(t.sl_initial)} />
                        )}
                        <Field label="P&L" value={pnl === null ? "inconnu" : fmtPnL(pnl, currency)}
                            cls={pnl === null ? "" : pnl >= 0 ? "text-green" : "text-red"} />
                    </div>

                    {t.pnl_source === "equity_delta" && (
                        <div className="text-[11px] text-text-secondary italic">
                            P&L estimé par la variation d&apos;équité (historique broker indisponible
                            au moment de la clôture).
                        </div>
                    )}

                    {t.reason && (
                        <div className="text-xs text-text-secondary leading-relaxed">{t.reason}</div>
                    )}

                    <div>
                        <div className="text-[10px] uppercase font-bold tracking-widest text-text-secondary mb-1">
                            Réglages particuliers
                        </div>
                        {notes.length === 0 ? (
                            <div className="text-xs text-text-secondary">
                                {t.source === "import"
                                    ? "Inconnus (trade importé du broker)."
                                    : "Aucun — réglages par défaut."}
                            </div>
                        ) : (
                            <ul className="text-xs text-text-primary space-y-0.5">
                                {notes.map((n) => <li key={n}>• {n}</li>)}
                            </ul>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function Field({ label, value, cls = "" }) {
    return (
        <div>
            <span className="text-text-secondary">{label} : </span>
            <span className={`num ${cls}`}>{value}</span>
        </div>
    );
}

function EquityCurve({ curve, initial, currency }) {
    if (!curve || curve.length < 2) {
        return (
            <div className="h-24 flex items-center justify-center text-xs text-text-secondary"
                 data-testid="journal-equity-empty">
                Pas encore assez de trades clôturés pour tracer la courbe.
            </div>
        );
    }
    const base = initial || 0;
    const values = curve.map((p) => p.equity);
    const min = Math.min(...values, base);
    const max = Math.max(...values, base);
    const range = max - min || 1;
    const W = 320, H = 110, PAD = 6;
    const px = (i) => (i / (curve.length - 1)) * W;
    const py = (v) => H - PAD - ((v - min) / range) * (H - 2 * PAD);
    const line = curve.map((p, i) => `${px(i).toFixed(1)},${py(p.equity).toFixed(1)}`).join(" ");
    const area = `${px(0)},${H} ${line} ${px(curve.length - 1)},${H}`;
    const last = values[values.length - 1];
    const up = last >= base;
    const color = up ? "#3FB68B" : "#E0635E";

    return (
        <div>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 110 }}
                 preserveAspectRatio="none" data-testid="journal-equity-curve">
                <defs>
                    <linearGradient id="jeq" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity="0.30" />
                        <stop offset="100%" stopColor={color} stopOpacity="0" />
                    </linearGradient>
                </defs>
                <polygon points={area} fill="url(#jeq)" />
                {/* Ligne de la mise de départ */}
                <line x1="0" y1={py(base)} x2={W} y2={py(base)}
                      stroke="#8A94A6" strokeWidth="1" strokeDasharray="4 4" />
                <polyline points={line} fill="none" stroke={color} strokeWidth="2"
                          vectorEffect="non-scaling-stroke" />
                <circle cx={px(curve.length - 1)} cy={py(last)} r="3" fill={color} />
            </svg>
            <div className="flex justify-between text-[10px] text-text-secondary num mt-1">
                <span>{fmtDate(curve[0].time)}</span>
                <span>{curve.length - 1} trades clôturés</span>
                <span>{fmtMoney(max, currency, 0)} max</span>
            </div>
        </div>
    );
}
