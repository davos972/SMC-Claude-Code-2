import React, { useEffect, useState } from "react";

export default function SessionRail({ rail }) {
    const [nowFrac, setNowFrac] = useState(rail?.now_frac || 0);

    useEffect(() => {
        const update = () => {
            const d = new Date();
            const utcSec = d.getUTCHours() * 3600 + d.getUTCMinutes() * 60 + d.getUTCSeconds();
            setNowFrac(utcSec / 86400);
        };
        update();
        const t = setInterval(update, 30000);
        return () => clearInterval(t);
    }, []);

    if (!rail) return null;

    // Une session peut être à cheval sur minuit UTC (typiquement l'Asie :
    // 08h–11h Tokyo ≈ 23h–02h UTC) → on la coupe en deux segments visuels.
    const windows = [
        { key: "london", label: "LONDRES", start: rail.london_start_frac, end: rail.london_end_frac },
        { key: "newyork", label: "NEW\nYORK", start: rail.newyork_start_frac, end: rail.newyork_end_frac },
    ];
    if (rail.asia_enabled) {
        windows.push({ key: "asia", label: "ASIE", start: rail.asia_start_frac, end: rail.asia_end_frac });
    }
    const segments = [];
    windows.forEach((w) => {
        if (w.start == null || w.end == null) return;
        if (w.end >= w.start) {
            segments.push({ ...w, id: w.key, left: w.start * 100, width: (w.end - w.start) * 100 });
        } else {
            segments.push({ ...w, id: `${w.key}-a`, left: w.start * 100, width: (1 - w.start) * 100 });
            segments.push({ ...w, id: `${w.key}-b`, left: 0, width: w.end * 100, label: "" });
        }
    });
    const nowPct = nowFrac * 100;

    return (
        <div className="w-full" data-testid="session-rail">
            <div className="flex items-center justify-between text-[11px] text-text-secondary mb-2 num">
                <span>00h</span>
                <span className="text-text-primary font-sans uppercase tracking-wider text-[10px] font-bold">
                    Sessions de trading (heure locale)
                </span>
                <span>24h</span>
            </div>
            <div className="relative w-full h-10 bg-bg rounded-xl border border-bd overflow-hidden">
                {/* Hour ticks */}
                <div className="absolute inset-0 flex">
                    {Array.from({ length: 24 }).map((_, i) => (
                        <div key={`tick-${i}`} className="flex-1 border-r border-bd/40 last:border-none" />
                    ))}
                </div>
                {/* Fenêtres de session (Londres / New York / Asie si activée) */}
                {segments.map((seg) => (
                    <div
                        key={seg.id}
                        data-testid={`session-window-${seg.id}`}
                        className="absolute top-0 bottom-0 bg-gradient-to-b from-gold/30 to-gold/10 border-x border-gold/50"
                        style={{ left: `${seg.left}%`, width: `${seg.width}%` }}
                    >
                        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gold tracking-wider leading-tight text-center px-1 whitespace-pre">
                            {seg.label}
                        </div>
                    </div>
                ))}
                {/* Current time marker */}
                <div
                    className="absolute top-0 bottom-0 w-0.5 bg-text-primary shadow-[0_0_8px_#E9ECF2] z-10"
                    style={{ left: `${nowPct}%` }}
                    data-testid="now-marker"
                />
            </div>
        </div>
    );
}
