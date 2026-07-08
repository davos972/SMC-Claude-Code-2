import axios from "axios";

// Backend URL resolution order:
// 1. Override saved on this device (Réglages → « URL du serveur ») — lets the
//    mobile APK or any browser point to another backend without rebuilding.
// 2. Build-time env (REACT_APP_BACKEND_URL) — default for the web app.
function resolveBackendUrl() {
    try {
        const stored = window.localStorage.getItem("goldflow_backend_url");
        if (stored && stored.trim()) return stored.trim().replace(/\/+$/, "");
    } catch { /* localStorage indisponible : on retombe sur l'env */ }
    return (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");
}

export function getBackendUrl() {
    return resolveBackendUrl();
}

export function setBackendUrl(url) {
    try {
        if (url && url.trim()) window.localStorage.setItem("goldflow_backend_url", url.trim());
        else window.localStorage.removeItem("goldflow_backend_url");
    } catch { /* ignore */ }
}

const BACKEND_URL = resolveBackendUrl();
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API,
    timeout: 30000,
});

// Long-timeout instance for MetaApi operations that can take 1-4 minutes (deploy, backtest, candles)
export const apiLong = axios.create({
    baseURL: API,
    timeout: 5 * 60 * 1000,
});

export const endpoints = {
    health: () => api.get("/health"),
    settings: () => api.get("/settings"),
    updateSettings: (updates) => api.put("/settings", { updates }),
    metaapiStatus: () => api.get("/metaapi/status"),
    testConnection: () => apiLong.post("/metaapi/test-connection"),
    account: () => api.get("/account"),
    positions: () => api.get("/positions"),
    price: (sym) => api.get(`/price/${sym}`),
    candles: (sym, tf, limit = 200) => apiLong.get(`/candles/${sym}`, { params: { timeframe: tf, limit } }),
    botStart: () => api.post("/bot/start"),
    botStop: () => api.post("/bot/stop"),
    botState: () => api.get("/bot/state"),
    runAnalysis: (symbol, persist = false, timeframe = null) => apiLong.post("/analysis/run", { symbol, persist, timeframe }),
    signals: (limit = 50) => api.get(`/signals?limit=${limit}`),
    clearSignals: () => api.delete("/signals"),
    notifications: () => api.get("/notifications"),
    readAllNotifications: () => api.post("/notifications/read-all"),
    deleteNotification: (id) => api.delete(`/notifications/${id}`),
    news: (currency = "USD") => api.get(`/news?currency=${currency}`),
    closePosition: (id) => api.post(`/positions/${id}/close`),
    cancelBacktest: (id) => api.delete(`/backtest/${id}`),
    analysisAtTime: (symbol, timestamp, mode = "intraday") =>
        apiLong.get(`/analysis/at-time`, { params: { symbol, timestamp, mode } }),
    startBacktest: (payload) => apiLong.post("/backtest", payload),
    getBacktest: (id) => api.get(`/backtest/${id}`),
    listBacktests: () => api.get("/backtests"),
    symbolSpread: (symbol = "XAUUSD") => api.get(`/symbol/spread?symbol=${symbol}`),
    stats: () => api.get("/stats"),
};
