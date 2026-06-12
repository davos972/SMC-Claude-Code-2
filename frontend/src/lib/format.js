export const fmtMoney = (v, currency = "€", digits = 0) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const sign = v < 0 ? "-" : "";
    const abs = Math.abs(v);
    const parts = abs.toFixed(digits).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u202F");
    return `${sign}${parts.join(",")} ${currency}`;
};

export const fmtPnL = (v, currency = "€") => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const s = v > 0 ? "+" : v < 0 ? "-" : "";
    const abs = Math.abs(v);
    return `${s}${abs.toFixed(2).replace(".", ",")} ${currency}`;
};

export const fmtPrice = (v, decimals = 2) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const n = Number(v);
    const parts = n.toFixed(decimals).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u202F");
    return parts.join(",");
};

export const fmtPct = (v, digits = 1) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return `${v.toFixed(digits).replace(".", ",")} %`;
};

export const fmtTime = (iso) => {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    } catch {
        return "—";
    }
};

export const fmtDate = (iso) => {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleDateString("fr-FR");
    } catch {
        return "—";
    }
};
