import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, CheckCheck, Trash2 } from "lucide-react";
import { endpoints } from "../api/client";
import { fmtTime } from "../lib/format";

const typeStyles = {
    info: "border-blue-400/40 bg-blue-400/5 text-blue-300",
    success: "border-green/40 bg-green/5 text-green",
    warning: "border-gold/40 bg-gold/5 text-gold",
    error: "border-red/40 bg-red/5 text-red",
};

export default function NotificationsSheet({ open, onClose, items }) {
    // Local mirror of the list so a deletion is reflected instantly, without waiting
    // for the parent's 5s poll. Kept in sync whenever the props change.
    const [list, setList] = useState(items || []);
    useEffect(() => { setList(items || []); }, [items]);

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

    const handleDelete = async (id) => {
        setList((cur) => cur.filter((n) => n.id !== id)); // optimistic
        try {
            await endpoints.deleteNotification(id);
        } catch (err) {
            console.error("Delete notification failed:", err);
        }
    };

    // Rendered through a portal on document.body: the app header uses backdrop-blur
    // (a backdrop-filter), which would otherwise trap this fixed overlay inside the
    // header and push it off-screen. The portal escapes that containing block.
    return createPortal(
        <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center" data-testid="notifications-sheet">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-[480px] bg-panel border-t border-bd rounded-t-2xl sm:rounded-2xl max-h-[80vh] flex flex-col animate-fade-in">
                <div className="flex items-center justify-between px-4 py-3 border-b border-bd flex-shrink-0">
                    <div className="flex items-center gap-2">
                        <CheckCheck className="w-5 h-5 text-gold" />
                        <h3 className="text-lg font-semibold">Notifications</h3>
                    </div>
                    <button onClick={onClose} className="w-9 h-9 rounded-lg hover:bg-bd flex items-center justify-center" data-testid="close-notifications-button">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="overflow-y-auto flex-1">
                    {list.length === 0 ? (
                        <div className="text-center py-12 text-text-secondary text-sm">
                            Aucune notification pour le moment.
                        </div>
                    ) : (
                        list.map((n) => (
                            <div key={n.id} className={`px-4 py-3 border-b border-bd ${!n.read ? "bg-gold/5" : ""}`}>
                                <div className="flex items-start justify-between gap-2 mb-1">
                                    <span className={`text-[10px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full border ${typeStyles[n.type] || typeStyles.info}`}>
                                        {n.type}
                                    </span>
                                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                                        <span className="text-xs text-text-secondary num">{fmtTime(n.time)}</span>
                                        <button
                                            onClick={() => handleDelete(n.id)}
                                            className="w-7 h-7 rounded-lg hover:bg-red/10 text-text-secondary hover:text-red flex items-center justify-center transition-colors"
                                            data-testid="delete-notification-button"
                                            aria-label="Supprimer cette notification"
                                            title="Supprimer"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                <div className="font-semibold text-sm">{n.title}</div>
                                <div className="text-sm text-text-secondary mt-0.5">{n.message}</div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>,
        document.body,
    );
}
