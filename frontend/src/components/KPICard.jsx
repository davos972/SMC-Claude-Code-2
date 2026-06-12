import React from "react";

export default function KPICard({ label, value, accent = "default", testid, sub }) {
    const colorMap = {
        default: "text-text-primary",
        positive: "text-green",
        negative: "text-red",
        gold: "text-gold",
    };
    return (
        <div className="bg-panel rounded-card border border-bd p-4 flex flex-col gap-1 animate-fade-in" data-testid={testid}>
            <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-text-secondary">
                {label}
            </div>
            <div className={`num text-xl sm:text-2xl font-bold ${colorMap[accent]}`}>
                {value}
            </div>
            {sub && <div className="text-xs text-text-secondary num">{sub}</div>}
        </div>
    );
}
