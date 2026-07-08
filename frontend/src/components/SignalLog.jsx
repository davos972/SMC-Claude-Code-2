import React from "react";
import { CheckCircle2, XCircle, Pause, TrendingUp, TrendingDown } from "lucide-react";
import { fmtTime } from "../lib/format";

const iconForStatus = (s, side) => {
    if (s === "accepted" || s === "executed") {
        return side === "sell" ? (
            <div className="w-10 h-10 rounded-xl bg-red/10 text-red flex items-center justify-center">
                <TrendingDown className="w-5 h-5" />
            </div>
        ) : (
            <div className="w-10 h-10 rounded-xl bg-green/10 text-green flex items-center justify-center">
                <TrendingUp className="w-5 h-5" />
            </div>
        );
    }
    if (s === "rejected") {
        return (
            <div className="w-10 h-10 rounded-xl bg-text-secondary/10 text-text-secondary flex items-center justify-center">
                <XCircle className="w-5 h-5" />
            </div>
        );
    }
    if (s === "news_pause") {
        return (
            <div className="w-10 h-10 rounded-xl bg-gold/10 text-gold flex items-center justify-center">
                <Pause className="w-5 h-5" />
            </div>
        );
    }
    return (
        <div className="w-10 h-10 rounded-xl bg-bd/40 text-text-secondary flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5" />
        </div>
    );
};

// Libellés courts des stades de rejet (mode journal diagnostic).
const STAGE_LABELS = {
    no_bias: "Pas de biais",
    no_poi: "Pas de POI",
    out_of_zone: "Hors zone",
    near_miss: "Quasi-setup",
    insufficient: "Données insuff.",
};

const titleForStatus = (s, side) => {
    if (s === "executed") return side === "buy" ? "BUY exécuté" : "SELL exécuté";
    if (s === "accepted") return side === "buy" ? "Signal BUY" : "Signal SELL";
    if (s === "rejected") return "Setup rejeté";
    if (s === "news_pause") return "Pause actualité";
    return "Signal";
};

export default function SignalLog({ signals }) {
    if (!signals || signals.length === 0) {
        return (
            <div className="text-center py-8 text-sm text-text-secondary">
                Aucun signal pour le moment. Lance l&apos;analyse depuis le dashboard.
            </div>
        );
    }
    return (
        <div className="flex flex-col" data-testid="signal-log">
            {signals.map((s) => (
                <div
                    key={s.id}
                    className="flex items-start gap-3 py-3 border-b border-bd last:border-0"
                    data-testid={`signal-item-${s.status}`}
                >
                    {iconForStatus(s.status, s.side)}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-text-primary">{titleForStatus(s.status, s.side)}</span>
                            {s.count > 1 && (
                                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full border border-bd text-text-secondary num">
                                    ×{s.count}
                                </span>
                            )}
                            {s.status === "rejected" && (s.bias === "bullish" || s.bias === "bearish") && (
                                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                                    s.bias === "bullish" ? "border-green/40 text-green" : "border-red/40 text-red"
                                }`}>
                                    {s.bias === "bullish" ? "Haussier" : "Baissier"}
                                </span>
                            )}
                            {s.status === "rejected" && s.reject_stage && STAGE_LABELS[s.reject_stage] && (
                                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border border-bd text-text-secondary">
                                    {STAGE_LABELS[s.reject_stage]}
                                </span>
                            )}
                            {s.rr && (
                                <span className="text-[11px] font-bold px-2 py-0.5 rounded-full border border-green/40 text-green num">
                                    RR 1:{s.rr.toFixed(1).replace(".", ",")}
                                </span>
                            )}
                            <span className="text-xs text-text-secondary num ml-auto">
                                {s.count > 1 && s.last_time
                                    ? `${fmtTime(s.time)} → ${fmtTime(s.last_time)}`
                                    : fmtTime(s.time)}
                            </span>
                        </div>
                        <div className="text-sm text-text-secondary mt-1 leading-snug">
                            {s.reason}
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}
