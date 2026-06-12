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

    const lStart = (rail.london_start_frac || 0) * 100;
    const lEnd = (rail.london_end_frac || 0) * 100;
    const nStart = (rail.newyork_start_frac || 0) * 100;
    const nEnd = (rail.newyork_end_frac || 0) * 100;
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
                {/* London window */}
                <div
                    className="absolute top-0 bottom-0 bg-gradient-to-b from-gold/30 to-gold/10 border-x border-gold/50"
                    style={{ left: `${lStart}%`, width: `${lEnd - lStart}%` }}
                >
                    <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gold tracking-wider">
                        LONDRES
                    </div>
                </div>
                {/* New York window */}
                <div
                    className="absolute top-0 bottom-0 bg-gradient-to-b from-gold/30 to-gold/10 border-x border-gold/50"
                    style={{ left: `${nStart}%`, width: `${nEnd - nStart}%` }}
                >
                    <div className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-gold tracking-wider leading-tight text-center px-1">
                        NEW<br />YORK
                    </div>
                </div>
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
