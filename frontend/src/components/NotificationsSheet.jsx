import React, { useEffect } from "react";
import { X, CheckCheck } from "lucide-react";
import { endpoints } from "../api/client";
import { fmtTime } from "../lib/format";

const typeStyles = {
    info: "border-blue-400/40 bg-blue-400/5 text-blue-300",
    success: "border-green/40 bg-green/5 text-green",
    warning: "border-gold/40 bg-gold/5 text-gold",
    error: "border-red/40 bg-red/5 text-red",
};

export default function NotificationsSheet({ open, onClose, items }) {
    useEffect(() => {
        if (open) {
            endpoints.readAllNotifications().catch(() => {});
            document.body.style.overflow = "hidden";
        } else {
            document.body.style.overflow = "";
        }
        return () => { document.body.style.overflow = ""; };
    }, [open]);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" data-testid="notifications-sheet">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-[480px] bg-panel border-t border-bd rounded-t-2xl sm:rounded-2xl max-h-[80vh] flex flex-col animate-fade-in">
                <div className="flex items-center justify-between px-4 py-3 border-b border-bd">
                    <div className="flex items-center gap-2">
                        <CheckCheck className="w-5 h-5 text-gold" />
                        <h3 className="text-lg font-semibold">Notifications</h3>
                    </div>
                    <button onClick={onClose} className="w-9 h-9 rounded-lg hover:bg-bd flex items-center justify-center" data-testid="close-notifications-button">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="overflow-y-auto flex-1">
                    {items.length === 0 ? (
                        <div className="text-center py-12 text-text-secondary text-sm">
                            Aucune notification pour le moment.
                        </div>
                    ) : (
                        items.map((n) => (
                            <div key={n.id} className={`px-4 py-3 border-b border-bd ${!n.read ? "bg-gold/5" : ""}`}>
                                <div className="flex items-center justify-between gap-2 mb-1">
                                    <span className={`text-[10px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full border ${typeStyles[n.type] || typeStyles.info}`}>
                                        {n.type}
                                    </span>
                                    <span className="text-xs text-text-secondary num">{fmtTime(n.time)}</span>
                                </div>
                                <div className="font-semibold text-sm">{n.title}</div>
                                <div className="text-sm text-text-secondary mt-0.5">{n.message}</div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
