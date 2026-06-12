/* eslint-disable react-hooks/set-state-in-effect */
import React, { useEffect, useState, useCallback, useRef } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import Backtest from "./pages/Backtest";
import Stats from "./pages/Stats";
import Settings from "./pages/Settings";
import { endpoints } from "./api/client";
import { registerServiceWorker, requestPermission, sendPushNotification } from "./lib/pushNotifications";

const TOASTER_OPTIONS = {
    style: { background: "#151B24", border: "1px solid #242E3D", color: "#E9ECF2" },
};

function App() {
    const [settings, setSettings] = useState(null);
    const [botState, setBotState] = useState(null);
    const lastNotifId = useRef(null);

    // Register service worker and request push notification permission
    useEffect(() => {
        registerServiceWorker().then(() => requestPermission());
    }, []);

    const refresh = useCallback(async () => {
        try {
            const [s, b] = await Promise.all([endpoints.settings(), endpoints.botState()]);
            setSettings(s.data);
            setBotState(b.data);
        } catch (err) {
            console.error("Refresh failed:", err);
        }
    }, []);

    // Poll notifications and send push for new unread ones (works with app in background)
    useEffect(() => {
        const pollNotifs = async () => {
            try {
                const { data } = await endpoints.notifications();
                const items = data.items || [];
                const newest = items.find((n) => !n.read);
                if (newest && newest.id !== lastNotifId.current) {
                    lastNotifId.current = newest.id;
                    sendPushNotification({ title: newest.title, body: newest.message, tag: newest.category });
                }
            } catch { /* ignore */ }
        };
        const t = setInterval(pollNotifs, 8000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 4000);
        return () => clearInterval(t);
    }, [refresh]);

    return (
        <BrowserRouter>
            <AppShell botState={botState} settings={settings}>
                <Routes>
                    <Route path="/" element={<Dashboard botState={botState} settings={settings} refresh={refresh} />} />
                    <Route path="/backtest" element={<Backtest settings={settings} />} />
                    <Route path="/stats" element={<Stats />} />
                    <Route path="/settings" element={<Settings settings={settings} refresh={refresh} />} />
                </Routes>
            </AppShell>
            <Toaster theme="dark" position="top-center" toastOptions={TOASTER_OPTIONS} />
        </BrowserRouter>
    );
}

export default App;
