import React, { useEffect, useState } from "react";
import { endpoints } from "../api/client";
import KPICard from "../components/KPICard";
import { fmtPct } from "../lib/format";

export default function Stats() {
    const [stats, setStats] = useState(null);
    const [signals, setSignals] = useState([]);

    useEffect(() => {
        endpoints.stats().then(({ data }) => setStats(data))
            .catch((e) => console.error("stats load failed:", e));
        endpoints.signals(500).then(({ data }) => setSignals(data || []))
            .catch((e) => console.error("signals load failed:", e));
    }, []);

    const accepted = signals.filter((s) => s.status === "accepted" || s.status === "executed");
    const rejected = signals.filter((s) => s.status === "rejected");
    const executed = signals.filter((s) => s.status === "executed");
    const acceptanceRate = signals.length ? (accepted.length / signals.length) * 100 : 0;
    const avgRR = accepted.length
        ? accepted.reduce((sum, s) => sum + (s.rr || 0), 0) / accepted.length
        : 0;

    return (
        <div className="space-y-4 animate-fade-in" data-testid="stats-page">
            <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary px-1">
                Statistiques live
            </div>

            <div className="grid grid-cols-2 gap-3">
                <KPICard label="Signaux totaux" value={signals.length} testid="stats-total-signals" />
                <KPICard label="Acceptés" value={accepted.length} accent="positive" testid="stats-accepted" />
                <KPICard label="Rejetés" value={rejected.length} accent="negative" testid="stats-rejected" />
                <KPICard label="Taux d'acceptation" value={fmtPct(acceptanceRate)} accent="gold" testid="stats-rate" />
                <KPICard label="RR moyen" value={`1:${avgRR.toFixed(2)}`} testid="stats-rr" />
                <KPICard label="Exécutés" value={executed.length} testid="stats-executed" />
            </div>

            {/* Equity curve (from executed signals' estimated cumulative RR) */}
            {executed.length > 0 && (
                <div className="bg-panel border border-bd rounded-card p-4">
                    <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                        Courbe d&apos;équité estimée (signaux exécutés)
                    </div>
                    <EquityCurve signals={executed} />
                </div>
            )}

            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Répartition par statut
                </div>
                <Bars data={{
                    "Acceptés": accepted.length,
                    "Rejetés": rejected.length,
                    "Pause news": signals.filter((s) => s.status === "news_pause").length,
                }} />
            </div>

            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Par session de trading
                </div>
                <Bars data={bySession(signals)} />
            </div>

            <div className="bg-panel border border-bd rounded-card p-4">
                <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3">
                    Par jour de la semaine
                </div>
                <Bars data={byDay(signals)} />
            </div>

            <div className="text-xs text-text-secondary text-center italic">
                Les statistiques live se mettent à jour à chaque nouveau signal détecté par le bot.
            </div>
        </div>
    );
}

function bySession(signals) {
    const counts = { Londres: 0, "New York": 0, Autre: 0 };
    signals.forEach((s) => {
        const sess = s.session;
        if (sess === "london") counts["Londres"] += 1;
        else if (sess === "newyork") counts["New York"] += 1;
        else counts["Autre"] += 1;
    });
    return counts;
}

function byDay(signals) {
    const days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
    const counts = { Lun: 0, Mar: 0, Mer: 0, Jeu: 0, Ven: 0, Sam: 0, Dim: 0 };
    signals.forEach((s) => {
        try {
            const d = new Date(s.time);
            const idx = (d.getDay() + 6) % 7;
            counts[days[idx]] += 1;
        } catch { /* ignore */ }
    });
    return counts;
}

function EquityCurve({ signals }) {
    // Build a simple point-to-point curve from signal timestamps (no real P&L → use +1 per win, -1 per loss estimate)
    // Signals sorted oldest first
    const sorted = [...signals].sort((a, b) => new Date(a.time) - new Date(b.time));
    let equity = 100;
    const points = [{ x: 0, y: equity }];
    sorted.forEach((s, i) => {
        // Approximate: accepted/executed = +rr points, no real P&L available
        equity += s.rr ? s.rr * 0.5 : 0.5;
        points.push({ x: i + 1, y: equity });
    });
    const minY = Math.min(...points.map((p) => p.y));
    const maxY = Math.max(...points.map((p) => p.y));
    const rangeY = maxY - minY || 1;
    const W = 320, H = 80;
    const px = (i) => (i / (points.length - 1)) * W;
    const py = (y) => H - ((y - minY) / rangeY) * (H - 8) - 4;
    const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ");

    return (
        <div className="overflow-x-auto">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 80 }}>
                <polyline points={points.map((p, i) => `${px(i)},${py(p.y)}`).join(" ")}
                    fill="none" stroke="#E3B341" strokeWidth="1.5" />
                <circle cx={px(points.length - 1)} cy={py(points[points.length - 1].y)}
                    r="3" fill="#E3B341" />
            </svg>
            <div className="flex justify-between text-[10px] text-text-secondary num mt-1">
                <span>Début</span>
                <span>Fin · {signals.length || points.length - 1} trades</span>
            </div>
        </div>
    );
}

function Bars({ data }) {
    const max = Math.max(1, ...Object.values(data));
    return (
        <div className="space-y-2">
            {Object.entries(data).map(([k, v]) => (
                <div key={k} className="flex items-center gap-3">
                    <span className="w-20 text-xs text-text-secondary">{k}</span>
                    <div className="flex-1 h-3 bg-bg rounded-full overflow-hidden border border-bd">
                        <div
                            className="h-full bg-gradient-to-r from-gold/60 to-gold"
                            style={{ width: `${(v / max) * 100}%` }}
                        />
                    </div>
                    <span className="num text-sm font-bold w-8 text-right">{v}</span>
                </div>
            ))}
        </div>
    );
}
