import React, { useEffect, useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import { Lock, AlertTriangle, Save, Plug, CheckCircle2, Loader2, Globe } from "lucide-react";
import SegmentedControl from "../components/SegmentedControl";
import { endpoints, getBackendUrl, setBackendUrl } from "../api/client";

const TRADING_MODE_OPTIONS = [
    { value: "intraday", label: "Intraday (H1 → M5)" },
    { value: "scalping", label: "Scalping (M15 → M1)" },
];

const RESUME_POLICY_OPTIONS = [
    { value: "next_session", label: "Prochaine session" },
    { value: "next_day", label: "Lendemain" },
];

const ACCOUNT_TYPE_OPTIONS = [
    { value: "demo", label: "Démo" },
    { value: "real", label: "Réel", icon: <Lock className="w-3.5 h-3.5" /> },
];

export default function Settings({ settings, refresh }) {
    const [local, setLocal] = useState(null);
    const [saving, setSaving] = useState(false);
    const [showRealModal, setShowRealModal] = useState(false);
    const [token, setToken] = useState("");
    const [connectionStatus, setConnectionStatus] = useState(null);
    const [mtStatus, setMtStatus] = useState(null);
    const [loadTimedOut, setLoadTimedOut] = useState(false);
    const [backendUrl, setBackendUrlLocal] = useState(getBackendUrl());
    const initialized = useRef(false);
    const debounceTimers = useRef({});

    // Only initialize local state once on first load — never overwrite user edits from polling
    useEffect(() => {
        if (settings && !initialized.current) {
            setLocal({ ...settings });
            initialized.current = true;
        }
    }, [settings]);

    // If the settings never arrive (backend down / unreachable), stop the infinite "Chargement…"
    // after 8s and surface an explicit error with a retry, instead of hanging silently.
    useEffect(() => {
        if (initialized.current) return;
        const t = setTimeout(() => {
            if (!initialized.current) setLoadTimedOut(true);
        }, 8000);
        return () => clearTimeout(t);
    }, [settings]);

    // Poll the MetaApi account state (configured / deploying / connected / last_error)
    useEffect(() => {
        let alive = true;
        const load = async () => {
            try {
                const { data } = await endpoints.metaapiStatus();
                if (alive) setMtStatus(data);
            } catch (e) {
                console.error("metaapi status load failed:", e);
                if (alive) setMtStatus({ fetch_error: true });
            }
        };
        load();
        const t = setInterval(load, 10000);
        return () => { alive = false; clearInterval(t); };
    }, []);

    const set = (k, v) => setLocal((s) => ({ ...s, [k]: v }));

    // Save a single field immediately (for toggles, selects)
    const saveField = useCallback(async (key, value) => {
        try {
            await endpoints.updateSettings({ [key]: value });
        } catch {
            toast.error("Erreur de sauvegarde");
        }
    }, []);

    // Save a single field with 600ms debounce (for number inputs)
    const saveFieldDebounced = useCallback((key, value) => {
        if (debounceTimers.current[key]) clearTimeout(debounceTimers.current[key]);
        debounceTimers.current[key] = setTimeout(() => saveField(key, value), 600);
    }, [saveField]);

    const setAndSave = (k, v) => { set(k, v); saveField(k, v); };
    const setAndSaveDebounced = (k, v) => { set(k, v); saveFieldDebounced(k, v); };

    const save = async (updates) => {
        setSaving(true);
        try {
            const base = updates || local;
            const payload = { ...base };
            if (!token && payload.metaapi_token === undefined) {
                delete payload.metaapi_token;
            } else if (token) {
                payload.metaapi_token = token;
            }
            await endpoints.updateSettings(payload);
            toast.success("Paramètres sauvegardés");
            setToken("");
            refresh && refresh();
        } catch (e) {
            toast.error("Erreur de sauvegarde");
        } finally { setSaving(false); }
    };

    const testConnection = async () => {
        setConnectionStatus("testing");
        try {
            const { data } = await endpoints.testConnection();
            setConnectionStatus(data.ok ? "ok" : "error");
            if (data.ok) toast.success("Connexion MetaApi réussie");
            else toast.error(data.error || "Échec de connexion");
        } catch {
            setConnectionStatus("error");
            toast.error("Échec de connexion");
        }
    };

    if (!local) {
        if (loadTimedOut) {
            return (
                <div className="text-center py-12 px-4 space-y-3" data-testid="settings-load-error">
                    <AlertTriangle className="w-8 h-8 text-gold mx-auto" />
                    <div className="text-sm font-semibold text-text-primary">
                        Impossible de charger les réglages
                    </div>
                    <div className="text-xs text-text-secondary max-w-xs mx-auto">
                        Le backend ne répond pas. En local, vérifie qu&apos;il est bien démarré
                        (port&nbsp;8000). En ligne, vérifie l&apos;état du service Render.
                    </div>
                    <button
                        onClick={() => { setLoadTimedOut(false); refresh && refresh(); }}
                        className="mt-2 px-4 py-2 bg-gold text-bg font-bold rounded-xl hover:brightness-110 transition-all"
                        data-testid="settings-retry-button"
                    >
                        Réessayer
                    </button>
                </div>
            );
        }
        return (
            <div className="text-center py-12 text-text-secondary flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Chargement…
            </div>
        );
    }

    const onAccountTypeChange = (v) => {
        if (v === "real") {
            setShowRealModal(true);
        } else {
            set("account_type", "demo");
            save({ account_type: "demo", real_confirmed: false });
        }
    };

    return (
        <div className="space-y-4 animate-fade-in" data-testid="settings-page">
            {/* Backend server URL (per-device override, used by the mobile app) */}
            <Section title="Serveur" icon={<Globe className="w-4 h-4" />}>
                <Field label="URL du serveur backend">
                    <input
                        type="url"
                        value={backendUrl}
                        onChange={(e) => setBackendUrlLocal(e.target.value)}
                        placeholder="ex. https://goldflow-backend.onrender.com"
                        className="num w-full bg-bg border border-bd rounded-xl px-3 py-3 focus:border-gold focus:outline-none"
                        data-testid="settings-backend-url"
                    />
                </Field>
                <div className="text-xs text-text-secondary">
                    Adresse du backend que cette application utilise (mémorisée sur cet appareil).
                    Changer d&apos;adresse recharge l&apos;application.
                </div>
                <button
                    onClick={() => { setBackendUrl(backendUrl); window.location.reload(); }}
                    className="w-full py-3 border border-bd rounded-xl text-text-primary hover:border-gold/50 transition-colors flex items-center justify-center gap-2"
                    data-testid="settings-backend-url-apply"
                >
                    <Save className="w-4 h-4" />
                    <span className="text-sm">Appliquer et recharger</span>
                </button>
            </Section>

            {/* MetaApi connection */}
            <Section title="Connexion MetaApi" icon={<Plug className="w-4 h-4" />}>
                <MetaApiStatusBanner status={mtStatus} />
                <Field label="Token MetaApi">
                    <input
                        type="password"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        placeholder={local.metaapi_token_masked || "Colle ton token MetaApi"}
                        className="w-full bg-bg border border-bd rounded-xl px-3 py-3 num focus:border-gold focus:outline-none focus:ring-1 focus:ring-gold/40"
                        data-testid="settings-metaapi-token"
                    />
                </Field>
                <Field label="Account ID">
                    <input
                        type="text"
                        value={local.metaapi_account_id || ""}
                        onChange={(e) => set("metaapi_account_id", e.target.value)}
                        placeholder="ex. a1b2c3d4-demo"
                        className="num w-full bg-bg border border-bd rounded-xl px-3 py-3 focus:border-gold focus:outline-none"
                        data-testid="settings-metaapi-accountid"
                    />
                </Field>
                <Field label="Type de compte">
                    <SegmentedControl
                        value={local.account_type}
                        onChange={onAccountTypeChange}
                        options={ACCOUNT_TYPE_OPTIONS}
                        testid="settings-account-type"
                    />
                </Field>
                {local.account_type === "real" && (
                    <div className="text-xs text-gold bg-gold/10 border border-gold/30 rounded-xl p-3 flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 mt-0.5" />
                        <span>Compte réel actif. Les ordres seront placés avec de l&apos;argent réel.</span>
                    </div>
                )}
                {local.account_type !== "real" && (
                    <div className="text-xs text-text-secondary bg-bg border border-bd rounded-xl p-3 flex items-start gap-2">
                        <Lock className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <span>Le compte réel nécessite une double confirmation et l&apos;acceptation des risques.</span>
                    </div>
                )}
                <div className="flex gap-2">
                    <button onClick={() => save({ metaapi_account_id: local.metaapi_account_id })}
                            disabled={saving}
                            className="flex-1 py-3 bg-gold text-bg font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                            data-testid="save-metaapi-button">
                        <Save className="w-4 h-4" />
                        <span>{saving ? "…" : "Sauvegarder"}</span>
                    </button>
                    <button onClick={testConnection}
                            className="px-4 py-3 border border-bd rounded-xl text-text-primary hover:border-gold/50 transition-colors flex items-center gap-2"
                            data-testid="test-connection-button">
                        {connectionStatus === "ok" ? <CheckCircle2 className="w-4 h-4 text-green" /> : <Plug className="w-4 h-4" />}
                        <span className="text-sm">Tester</span>
                    </button>
                </div>
            </Section>

            {/* Mode */}
            <Section title="Mode de trading">
                <Field label="Mode">
                    <SegmentedControl
                        value={local.trading_mode}
                        onChange={(v) => setAndSave("trading_mode", v)}
                        options={TRADING_MODE_OPTIONS}
                        testid="settings-trading-mode"
                    />
                </Field>
                <Toggle
                    label="Mode signal uniquement"
                    description="Le bot détecte et logge sans exécuter d'ordres."
                    value={local.signal_only_mode}
                    onChange={(v) => setAndSave("signal_only_mode", v)}
                    testid="settings-signal-only"
                />
                <NumberField
                    label="Fenêtre sweep/CHoCH (bougies LTF)"
                    value={local.recent_window}
                    onChange={(v) => setAndSaveDebounced("recent_window", v)}
                    step={1}
                    testid="settings-recent-window"
                />
            </Section>

            {/* Stratégie SMC */}
            <Section title="Stratégie SMC">
                <div className="text-xs text-text-secondary -mt-1">
                    Analyse top-down 3 niveaux : biais → structure/POI → entrée.
                </div>
                <Toggle
                    label="FVG obligatoire à l'entrée"
                    description="Le prix doit revenir dans une FVG non comblée du bon sens."
                    value={local.require_fvg_entry}
                    onChange={(v) => setAndSave("require_fvg_entry", v)}
                    testid="settings-require-fvg"
                />
                <Toggle
                    label="Séquence sweep → CHoCH"
                    description="Exige un balayage de liquidité PUIS un changement de structure."
                    value={local.require_sweep_then_choch}
                    onChange={(v) => setAndSave("require_sweep_then_choch", v)}
                    testid="settings-require-sequence"
                />
                <Toggle
                    label="Order block non mitigé"
                    description="N'entre que sur des zones vierges (non déjà retouchées)."
                    value={local.require_unmitigated_ob}
                    onChange={(v) => setAndSave("require_unmitigated_ob", v)}
                    testid="settings-require-unmitigated"
                />
                <Toggle
                    label="Journal diagnostic (voir tous les rejets)"
                    description="Journalise aussi les setups écartés tôt (pas de biais, pas de POI, hors zone), regroupés. À activer ponctuellement pour comprendre pourquoi des setups sont ignorés — laisse OFF en temps normal."
                    value={local.verbose_journal}
                    onChange={(v) => setAndSave("verbose_journal", v)}
                    testid="settings-verbose-journal"
                />
                <div className="text-[10px] uppercase font-bold tracking-widest text-text-secondary pt-1">
                    Intraday — biais / structure / entrée
                </div>
                <div className="grid grid-cols-3 gap-2">
                    <SelectField label="Biais" value={local.intraday_htf} onChange={(v) => setAndSave("intraday_htf", v)} options={TF_LIST} testid="settings-intraday-htf" />
                    <SelectField label="Structure" value={local.intraday_mtf} onChange={(v) => setAndSave("intraday_mtf", v)} options={TF_LIST} testid="settings-intraday-mtf" />
                    <SelectField label="Entrée" value={local.intraday_ltf} onChange={(v) => setAndSave("intraday_ltf", v)} options={TF_LIST} testid="settings-intraday-ltf" />
                </div>
                <div className="text-[10px] uppercase font-bold tracking-widest text-text-secondary pt-1">
                    Scalping — biais / structure / entrée
                </div>
                <div className="grid grid-cols-3 gap-2">
                    <SelectField label="Biais" value={local.scalping_htf} onChange={(v) => setAndSave("scalping_htf", v)} options={TF_LIST} testid="settings-scalping-htf" />
                    <SelectField label="Structure" value={local.scalping_mtf} onChange={(v) => setAndSave("scalping_mtf", v)} options={TF_LIST} testid="settings-scalping-mtf" />
                    <SelectField label="Entrée" value={local.scalping_ltf} onChange={(v) => setAndSave("scalping_ltf", v)} options={TF_LIST} testid="settings-scalping-ltf" />
                </div>
            </Section>

            {/* Trailing stop */}
            <Section title="Trailing stop">
                <div className="text-xs text-text-secondary -mt-1">
                    Resserre automatiquement le SL des trades en cours (modifié chez le broker). OFF par défaut.
                    Mes backtests : n&apos;augmente pas le profit mais réduit le drawdown ; éviter « break-even seul ».
                </div>
                <Field label="Mode">
                    <select
                        value={local.trailing_mode || "off"}
                        onChange={(e) => setAndSave("trailing_mode", e.target.value)}
                        className="num w-full bg-bg border border-bd rounded-xl px-3 py-2.5 focus:border-gold focus:outline-none"
                        data-testid="settings-trailing-mode"
                    >
                        <option value="off">Désactivé</option>
                        <option value="breakeven">Break-even (SL → entrée)</option>
                        <option value="r_trail">R-trail (distance fixe)</option>
                        <option value="structure">Structure (suit les bougies)</option>
                    </select>
                </Field>
                {local.trailing_mode && local.trailing_mode !== "off" && (
                    <>
                        <NumberField label="Déclenchement (en R)" value={local.trailing_trigger_r}
                            onChange={(v) => setAndSaveDebounced("trailing_trigger_r", v)} step="0.1"
                            testid="settings-trailing-trigger"
                            hint="Profit atteint (en multiples du risque) avant d'activer le trailing." />
                        {local.trailing_mode === "r_trail" && (
                            <NumberField label="Distance verrouillée (en R)" value={local.trailing_distance_r}
                                onChange={(v) => setAndSaveDebounced("trailing_distance_r", v)} step="0.1"
                                testid="settings-trailing-distance" />
                        )}
                        {local.trailing_mode === "structure" && (
                            <NumberField label="Bougies suivies" value={local.trailing_lookback}
                                onChange={(v) => setAndSaveDebounced("trailing_lookback", v)} step="1"
                                testid="settings-trailing-lookback" />
                        )}
                        <NumberField label="Marge / buffer (en prix)" value={local.trailing_buffer}
                            onChange={(v) => setAndSaveDebounced("trailing_buffer", v)} step="0.01"
                            testid="settings-trailing-buffer" />
                    </>
                )}
            </Section>

            {/* Sessions */}
            <Section title="Sessions de trading">
                <div className="text-xs text-text-secondary -mt-1">
                    Le bot ne trade que pendant ces fenêtres (heure locale de chaque place,
                    heure d&apos;été gérée automatiquement).
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <TimeField label="Londres début" value={local.session_london_start} onChange={(v) => setAndSave("session_london_start", v)} testid="settings-london-start" />
                    <TimeField label="Londres fin" value={local.session_london_end} onChange={(v) => setAndSave("session_london_end", v)} testid="settings-london-end" />
                    <TimeField label="New York début" value={local.session_newyork_start} onChange={(v) => setAndSave("session_newyork_start", v)} testid="settings-ny-start" />
                    <TimeField label="New York fin" value={local.session_newyork_end} onChange={(v) => setAndSave("session_newyork_end", v)} testid="settings-ny-end" />
                </div>
            </Section>

            {/* Risk */}
            <Section title="Gestion du risque">
                <Slider
                    label="Risque par trade"
                    min={0.25} max={2} step={0.25}
                    value={local.risk_per_trade_pct}
                    onChange={(v) => setAndSaveDebounced("risk_per_trade_pct", v)}
                    suffix="%"
                    testid="settings-risk-per-trade"
                />
                <NumberField label="RR minimum" value={local.min_rr} onChange={(v) => setAndSaveDebounced("min_rr", v)} step={0.1} testid="settings-min-rr" />
                <NumberField label="Pertes consécutives max" value={local.max_consec_losses} onChange={(v) => setAndSaveDebounced("max_consec_losses", v)} step={1} testid="settings-max-losses" />
                <NumberField label="Drawdown maximum (%)" value={local.max_drawdown_pct} onChange={(v) => setAndSaveDebounced("max_drawdown_pct", v)} step={0.1} testid="settings-max-dd" />
                <NumberField label="Trades max / jour" value={local.max_trades_per_day} onChange={(v) => setAndSaveDebounced("max_trades_per_day", v)} step={1} testid="settings-max-trades" />
                <Field label="Reprise après arrêt auto">
                    <SegmentedControl
                        value={local.resume_policy}
                        onChange={(v) => setAndSave("resume_policy", v)}
                        options={RESUME_POLICY_OPTIONS}
                        testid="settings-resume-policy"
                    />
                </Field>
            </Section>

            {/* News */}
            <Section title="Filtre actualités économiques">
                <Toggle label="Activer le filtre Forex Factory"
                    value={local.news_filter_enabled}
                    onChange={(v) => setAndSave("news_filter_enabled", v)}
                    testid="settings-news-filter" />
                <NumberField label="Pause avant news (min)" value={local.news_minutes_before} onChange={(v) => setAndSaveDebounced("news_minutes_before", v)} step={5} testid="settings-news-before" />
                <NumberField label="Pause après news (min)" value={local.news_minutes_after} onChange={(v) => setAndSaveDebounced("news_minutes_after", v)} step={5} testid="settings-news-after" />
                <Toggle label="Fermer positions avant annonce forte"
                    value={local.close_positions_before_news}
                    onChange={(v) => setAndSave("close_positions_before_news", v)}
                    testid="settings-news-close" />
            </Section>

            {/* Prop Firm */}
            <Section title="Mode Prop Firm">
                <Toggle label="Activer le mode Prop Firm"
                    value={local.prop_firm_enabled}
                    onChange={(v) => setAndSave("prop_firm_enabled", v)}
                    testid="settings-propfirm" />
                {local.prop_firm_enabled && (
                    <div className="space-y-3 animate-fade-in">
                        <div className="text-xs text-text-secondary -mt-1">
                            Défauts calés sur BlueGuardian Instant. Le bot s&apos;arrête AVANT les limites
                            réelles (marge de sécurité). Garde-fous appliqués en live : Guardian Shield et drawdowns.
                        </div>
                        <NumberField label="Solde initial" value={local.prop_initial_balance} onChange={(v) => setAndSaveDebounced("prop_initial_balance", v)} step={100} testid="settings-prop-balance" />
                        <NumberField label="Guardian Shield (%)"
                            hint="Perte flottante max des positions ouvertes. Le bot ferme tout AVANT ce seuil."
                            value={local.prop_guardian_shield_pct} onChange={(v) => setAndSaveDebounced("prop_guardian_shield_pct", v)} step={0.1} testid="settings-prop-guardian" />
                        <NumberField label="Drawdown jour max (%)" value={local.prop_daily_dd_pct} onChange={(v) => setAndSaveDebounced("prop_daily_dd_pct", v)} step={0.1} testid="settings-prop-dd-day" />
                        <NumberField label="Drawdown total max (%)" value={local.prop_total_dd_pct} onChange={(v) => setAndSaveDebounced("prop_total_dd_pct", v)} step={0.1} testid="settings-prop-dd-total" />
                        <Toggle label="Drawdown total glissant (trailing)"
                            description="Le plancher de perte suit le plus haut solde atteint (sinon fixe au solde initial)."
                            value={local.prop_trailing_dd}
                            onChange={(v) => setAndSave("prop_trailing_dd", v)}
                            testid="settings-prop-trailing-dd" />
                        {local.prop_trailing_dd && (
                            <NumberField label="Verrou du plancher après profit (%)"
                                hint="Une fois ce profit atteint, le plancher se verrouille au solde initial."
                                value={local.prop_trailing_lock_profit_pct} onChange={(v) => setAndSaveDebounced("prop_trailing_lock_profit_pct", v)} step={0.5} testid="settings-prop-lock" />
                        )}
                        <NumberField label="Heure de reset journalier (EST)"
                            hint="Heure à laquelle le compteur de perte du jour repart à zéro (BlueGuardian : 17h EST)."
                            value={local.prop_daily_reset_hour_est} onChange={(v) => setAndSaveDebounced("prop_daily_reset_hour_est", v)} step={1} testid="settings-prop-reset-hour" />
                        <NumberField label="Marge de sécurité (%)" value={local.prop_safety_margin_pct} onChange={(v) => setAndSaveDebounced("prop_safety_margin_pct", v)} step={1} testid="settings-prop-margin" />
                        <NumberField label="Objectif de profit (%)" value={local.prop_profit_target_pct} onChange={(v) => setAndSaveDebounced("prop_profit_target_pct", v)} step={0.5} testid="settings-prop-target" />
                        <NumberField label="Cohérence (%)"
                            hint="Indicatif (non bloquant) : un jour ne doit pas dépasser ce % du profit total pour le retrait."
                            value={local.prop_consistency_pct} onChange={(v) => setAndSaveDebounced("prop_consistency_pct", v)} step={1} testid="settings-prop-consistency" />
                    </div>
                )}
            </Section>

            {/* Notifications */}
            <Section title="Notifications">
                <Toggle label="Ouverture de trade" value={local.notif_open_trade} onChange={(v) => setAndSave("notif_open_trade", v)} testid="settings-notif-open" />
                <Toggle label="Clôture de trade" value={local.notif_close_trade} onChange={(v) => setAndSave("notif_close_trade", v)} testid="settings-notif-close" />
                <Toggle label="Avertissement drawdown" value={local.notif_dd_warning} onChange={(v) => setAndSave("notif_dd_warning", v)} testid="settings-notif-dd" />
                <Toggle label="Arrêt automatique" value={local.notif_bot_stop} onChange={(v) => setAndSave("notif_bot_stop", v)} testid="settings-notif-stop" />
                <Toggle label="Perte/rétablissement connexion" value={local.notif_connection} onChange={(v) => setAndSave("notif_connection", v)} testid="settings-notif-conn" />
                <Toggle label="Annonce éco imminente" value={local.notif_news} onChange={(v) => setAndSave("notif_news", v)} testid="settings-notif-news" />
            </Section>

            {/* Save All */}
            <button onClick={() => save(local)} disabled={saving}
                className="w-full py-3.5 bg-gold text-bg font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                data-testid="save-all-settings">
                <Save className="w-4 h-4" />
                <span>{saving ? "Sauvegarde…" : "Sauvegarder tous les paramètres"}</span>
            </button>

            {showRealModal && (
                <RealAccountModal
                    onCancel={() => setShowRealModal(false)}
                    onConfirm={() => {
                        set("account_type", "real");
                        set("real_confirmed", true);
                        save({ account_type: "real", real_confirmed: true });
                        setShowRealModal(false);
                    }}
                />
            )}
        </div>
    );
}

function Section({ title, icon, children }) {
    return (
        <div className="bg-panel border border-bd rounded-card p-4">
            <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-3 flex items-center gap-2">
                {icon}{title}
            </div>
            <div className="space-y-3">{children}</div>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <div>
            <label className="text-[10px] uppercase font-bold tracking-widest text-text-secondary block mb-1.5">
                {label}
            </label>
            {children}
        </div>
    );
}

function NumberField({ label, value, onChange, step, testid, hint }) {
    return (
        <Field label={label}>
            <input
                type="number"
                value={value ?? ""}
                step={step}
                onChange={(e) => onChange(parseFloat(e.target.value))}
                className="num w-full bg-bg border border-bd rounded-xl px-3 py-2.5 focus:border-gold focus:outline-none"
                data-testid={testid}
            />
            {hint && <div className="text-xs text-text-secondary mt-1">{hint}</div>}
        </Field>
    );
}

const TF_LIST = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

function SelectField({ label, value, onChange, options, testid }) {
    return (
        <Field label={label}>
            <select
                value={value || ""}
                onChange={(e) => onChange(e.target.value)}
                className="num w-full bg-bg border border-bd rounded-xl px-3 py-2.5 focus:border-gold focus:outline-none"
                data-testid={testid}
            >
                {options.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
        </Field>
    );
}

function TimeField({ label, value, onChange, testid }) {
    return (
        <Field label={label}>
            <input
                type="time"
                value={value || ""}
                onChange={(e) => onChange(e.target.value)}
                className="num w-full bg-bg border border-bd rounded-xl px-3 py-2.5 focus:border-gold focus:outline-none"
                data-testid={testid}
            />
        </Field>
    );
}

function Toggle({ label, description, value, onChange, testid }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <div className="flex-1 min-w-0">
                <div className="text-sm">{label}</div>
                {description && <div className="text-xs text-text-secondary">{description}</div>}
            </div>
            <button
                type="button"
                role="switch"
                aria-checked={value}
                onClick={() => onChange(!value)}
                data-testid={testid}
                className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 ${value ? "bg-green" : "bg-bd"}`}
            >
                <span className={`absolute top-0.5 ${value ? "left-[22px]" : "left-0.5"} w-5 h-5 rounded-full bg-white shadow transition-all`} />
            </button>
        </div>
    );
}

function Slider({ label, min, max, step, value, onChange, suffix, testid }) {
    return (
        <Field label={`${label} — ${value}${suffix || ""}`}>
            <input
                type="range" min={min} max={max} step={step}
                value={value}
                onChange={(e) => onChange(parseFloat(e.target.value))}
                className="w-full accent-gold"
                data-testid={testid}
            />
            <div className="flex justify-between text-[10px] text-text-secondary num mt-1">
                <span>{min}{suffix}</span><span>{max}{suffix}</span>
            </div>
        </Field>
    );
}

function MetaApiStatusBanner({ status }) {
    if (!status) {
        return (
            <div className="text-xs text-text-secondary bg-bg border border-bd rounded-xl p-3 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Lecture de l&apos;état du compte…</span>
            </div>
        );
    }

    let cls = "text-text-secondary bg-bg border-bd";
    let icon = <Plug className="w-4 h-4 mt-0.5 flex-shrink-0" />;
    let title = "État inconnu";
    let detail = null;

    if (status.fetch_error) {
        cls = "text-red bg-red/10 border-red/30";
        icon = <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />;
        title = "État du compte indisponible";
        detail = "Impossible de joindre le backend.";
    } else if (!status.configured) {
        cls = "text-text-secondary bg-bg border-bd";
        icon = <Plug className="w-4 h-4 mt-0.5 flex-shrink-0" />;
        title = "MetaApi non configuré";
        detail = "Renseigne ton token et ton Account ID ci-dessous.";
    } else if (status.deploying) {
        cls = "text-gold bg-gold/10 border-gold/30";
        icon = <Loader2 className="w-4 h-4 mt-0.5 flex-shrink-0 animate-spin" />;
        title = "Déploiement du compte en cours…";
        detail = "Un compte inactif peut prendre 1 à 4 minutes à redémarrer. Patiente.";
    } else if (status.connected) {
        cls = "text-green bg-green/10 border-green/30";
        icon = <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />;
        title = "Connecté à MetaApi";
        detail = status.account_id ? `Compte ${status.account_id}` : null;
    } else if (status.last_error) {
        cls = "text-red bg-red/10 border-red/30";
        icon = <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />;
        title = "Erreur de connexion";
        detail = status.last_error;
    } else {
        cls = "text-text-secondary bg-bg border-bd";
        icon = <Plug className="w-4 h-4 mt-0.5 flex-shrink-0" />;
        title = "Configuré — non connecté";
        detail = "La connexion s'établira au prochain appel (test, graphique…).";
    }

    return (
        <div className={`text-xs border rounded-xl p-3 flex items-start gap-2 ${cls}`} data-testid="metaapi-status-banner">
            {icon}
            <div className="min-w-0">
                <div className="font-bold">{title}</div>
                {detail && <div className="opacity-90 break-words">{detail}</div>}
            </div>
        </div>
    );
}

function RealAccountModal({ onCancel, onConfirm }) {
    const [check1, setCheck1] = useState(false);
    const [check2, setCheck2] = useState(false);
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" data-testid="real-account-modal">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
            <div className="relative w-full max-w-sm bg-panel border border-red/40 rounded-2xl p-5 animate-fade-in">
                <div className="flex items-center gap-2 text-red mb-3">
                    <AlertTriangle className="w-5 h-5" />
                    <h3 className="font-bold">Passage en compte réel</h3>
                </div>
                <p className="text-sm text-text-secondary leading-relaxed mb-4">
                    Tu t&apos;apprêtes à activer le trading sur un compte réel.
                    Les ordres placés engageront ton vrai capital. Le trading sur le forex et l&apos;or comporte des risques de perte importants.
                </p>
                <label className="flex items-start gap-2 mb-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={check1} onChange={(e) => setCheck1(e.target.checked)} className="mt-0.5 accent-gold" data-testid="real-check-1" />
                    <span>Je comprends que les ordres seront placés avec de l&apos;argent réel.</span>
                </label>
                <label className="flex items-start gap-2 mb-4 text-sm cursor-pointer">
                    <input type="checkbox" checked={check2} onChange={(e) => setCheck2(e.target.checked)} className="mt-0.5 accent-gold" data-testid="real-check-2" />
                    <span>J&apos;accepte les risques liés au trading automatique.</span>
                </label>
                <div className="flex gap-2">
                    <button onClick={onCancel} className="flex-1 py-2.5 border border-bd rounded-xl text-text-secondary" data-testid="real-cancel">Annuler</button>
                    <button
                        onClick={onConfirm}
                        disabled={!check1 || !check2}
                        className="flex-1 py-2.5 bg-red text-bg font-bold rounded-xl disabled:opacity-40"
                        data-testid="real-confirm"
                    >Activer le réel</button>
                </div>
            </div>
        </div>
    );
}
