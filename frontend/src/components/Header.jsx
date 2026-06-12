/* eslint-disable react-hooks/set-state-in-effect */
import React, { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { endpoints } from "../api/client";
import NotificationsSheet from "./NotificationsSheet";

export default function Header({ botState, settings }) {
    const [unread, setUnread] = useState(0);
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);

    const load = async () => {
        try {
            const { data } = await endpoints.notifications();
            setItems(data.items || []);
            setUnread(data.unread || 0);
        } catch (err) { console.error("Notifications fetch failed:", err); }
    };

    useEffect(() => {
        load();
        const t = setInterval(load, 5000);
        return () => clearInterval(t);
    }, []);

    const accountLabel = settings?.account_type === "real" ? "Compte réel" : "Compte démo";
    const status = botState?.effective_status;
    const statusMap = {
        active: { label: "ACTIF", dot: "bg-green", text: "text-green", ring: "border-green/40 bg-green/5" },
        out_of_session: { label: "HORS SESSION", dot: "bg-gold", text: "text-gold", ring: "border-gold/40 bg-gold/5" },
        stopped: { label: "ARRÊTÉ", dot: "bg-text-secondary", text: "text-text-secondary", ring: "border-bd bg-panel" },
    };
    const st = statusMap[status] || statusMap.stopped;

    return (
        <header className="sticky top-0 z-40 bg-bg/95 backdrop-blur-md border-b border-bd" data-testid="app-header">
            <div className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-gold to-amber-700 flex items-center justify-center text-bg font-bold shadow-glow-gold flex-shrink-0">
                        Au
                    </div>
                    <div className="min-w-0">
                        <div className="font-semibold text-lg leading-tight truncate">
                            GoldFlow <span className="text-gold">SMC</span>
                        </div>
                        <div className="text-xs text-text-secondary mt-0.5 truncate">
                            MT5 · {accountLabel}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${st.ring}`} data-testid="bot-status-pill">
                        <span className={`w-1.5 h-1.5 rounded-full ${st.dot} ${status === "active" ? "animate-pulse-dot" : ""}`} />
                        <span className={`text-[11px] font-semibold tracking-wider ${st.text}`}>{st.label}</span>
                    </div>
                    <button
                        type="button"
                        onClick={() => setOpen(true)}
                        className="relative w-10 h-10 rounded-xl border border-bd bg-panel flex items-center justify-center hover:border-gold/40 transition-colors"
                        data-testid="open-notifications-button"
                        aria-label="Notifications"
                    >
                        <Bell className="w-5 h-5 text-gold" strokeWidth={2} />
                        {unread > 0 && (
                            <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red text-bg text-[10px] font-bold flex items-center justify-center num"
                                data-testid="notifications-badge">
                                {unread}
                            </span>
                        )}
                    </button>
                </div>
            </div>
            <NotificationsSheet open={open} onClose={() => { setOpen(false); load(); }} items={items} />
        </header>
    );
}
