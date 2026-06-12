import React, { useEffect, useState } from "react";
import { endpoints } from "../api/client";
import KPICard from "../components/KPICard";
import { fmtPct } from "../lib/format";

export default function Stats() {
    const [stats, setStats] = useState(null);
    const [signals, setSignals] = useState([]);

    useEffect(() => {
        endpoints.stats().then(({ data }) => setStats(data)).catch(() => {});
        endpoints.signals(200).then(({ data }) => setSignals(data || [])).catch(() => {});
    }, []);

    // Compute stats client-side from signals
    const accepted = signals.filter((s) => s.status === "accepted" || s.status === "executed");
    const rejected = signals.filter((s) => s.status === "rejected");
    const acceptanceRate = signals.length ? (accepted.length / signals.length) * 100 : 0;
    const avgRR = accepted.length ? (accepted.reduce((sum, s) => sum + (s.rr || 0), 0) / accepted.length) : 0;

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
                <KPICard label="Exécutés" value={stats?.executed || 0} testid="stats-executed" />
            </div>

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

function byDay(signals) {
    const days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
    const counts = { Lun: 0, Mar: 0, Mer: 0, Jeu: 0, Ven: 0, Sam: 0, Dim: 0 };
    signals.forEach((s) => {
        try {
            const d = new Date(s.time);
            const idx = (d.getDay() + 6) % 7; // Monday=0
            counts[days[idx]] += 1;
        } catch (err) { console.error("Invalid signal time:", err); }
    });
    return counts;
}

function Bars({ data }) {
    const max = Math.max(1, ...Object.values(data));
    return (
        <div className="space-y-2">
            {Object.entries(data).map(([k, v]) => (
                <div key={k} className="flex items-center gap-3">
                    <span className="w-16 text-xs text-text-secondary">{k}</span>
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
