import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
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
    news: (currency = "USD") => api.get(`/news?currency=${currency}`),
    closePosition: (id) => api.post(`/positions/${id}/close`),
    cancelBacktest: (id) => api.delete(`/backtest/${id}`),
    analysisAtTime: (symbol, timestamp, mode = "intraday") =>
        apiLong.get(`/analysis/at-time`, { params: { symbol, timestamp, mode } }),
    startBacktest: (payload) => apiLong.post("/backtest", payload),
    getBacktest: (id) => api.get(`/backtest/${id}`),
    listBacktests: () => api.get("/backtests"),
    stats: () => api.get("/stats"),
};
