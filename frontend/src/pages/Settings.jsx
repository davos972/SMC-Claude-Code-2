import React, { useEffect, useState, useRef, useCallback } from "react";
import { toast } from "sonner";
import { AlertTriangle, Save, Plug, CheckCircle2, Loader2, Globe } from "lucide-react";
import SegmentedControl from "../components/SegmentedControl";
import { endpoints, getBackendUrl, setBackendUrl, getApiKey, setApiKey } from "../api/client";

const RESUME_POLICY_OPTIONS = [
    { value: "next_session", label: "Prochaine session" },
    { value: "next_day", label: "Lendemain" },
];

export default function Settings({ settings, refresh }) {
    const [local, setLocal] = useState(null);
    const [saving, setSaving] = useState(false);
    const [token, setToken] = useState("");
    const [connectionStatus, setConnectionStatus] = useState(null);
    const [mtStatus, setMtStatus] = useState(null);
    const [loadTimedOut, setLoadTimedOut] = useState(false);
    const [backendUrl, setBackendUrlLocal] = useState(getBackendUrl());
    const [apiKey, setApiKeyLocal] = useState(getApiKey());
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

    return (
        <div className="space-y-4 animate-fade-in" data-testid="settings-page">
            {/* Récapitulatif en lecture seule de la configuration validée en backtest
                (campagne du 2026-08-26, appliquée en prod le 2026-08-27). Les réglages
                correspondants ont été retirés de cet écran : ce bloc sert à VÉRIFIER qu'ils
                sont bien ceux-là, et à rendre visible toute dérive. */}
            <ConfigValidee local={local} />

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
                <div className="text-xs text-text-secondary bg-bg border border-bd rounded-xl p-3">
                    C&apos;est le <b>token MetaApi</b> ci-dessus qui détermine le compte utilisé —
                    aujourd&apos;hui un compte <b>démo</b> chez Axi. Le sélecteur démo/réel a été retiré
                    de cet écran : il ne changeait pas de compte, et son libellé prêtait à confusion.
                </div>
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

            {/* Stratégie SMC */}
            <Section title="Stratégie SMC">
                <div className="text-xs text-text-secondary -mt-1">
                    Analyse top-down 4 niveaux : contexte journalier → biais → structure/POI → entrée.
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
                    label="Premium/Discount obligatoire"
                    description="Achat uniquement en zone discount, vente uniquement en premium. Backtest 6 mois : le désactiver ajoute ~45% de trades mais divise le profit par 4 et double le drawdown."
                    value={local.require_premium_discount}
                    onChange={(v) => setAndSave("require_premium_discount", v)}
                    testid="settings-require-pd"
                />
                <Field label="Mode d'entrée order block">
                    <select
                        value={local.ob_entry_mode || "close"}
                        onChange={(e) => setAndSave("ob_entry_mode", e.target.value)}
                        className="num w-full bg-bg border border-bd rounded-xl px-3 py-2.5 focus:border-gold focus:outline-none"
                        data-testid="settings-ob-entry-mode"
                    >
                        <option value="close">Clôture dans l&apos;OB (strict — recommandé)</option>
                        <option value="zone_50">Clôture au-delà des 50% de l&apos;OB (meilleur ratio)</option>
                        <option value="tap">Touche récente de l&apos;OB (tap — expérimental)</option>
                    </select>
                </Field>
                {local.ob_entry_mode === "tap" && (
                    <div className="text-xs text-gold bg-gold/10 border border-gold/30 rounded-xl p-3 flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <span>
                            Mode tap : il suffit qu&apos;une bougie récente ait touché l&apos;order block
                            (mèches comprises) au lieu d&apos;exiger une clôture dedans. Prend beaucoup
                            plus de trades, mais <b>perdant sur le backtest 6 mois</b> (déc. 2025 → juin 2026 :
                            profit factor 0,85–0,92, drawdown jusqu&apos;à 68%). À vérifier en
                            backtest avant toute utilisation.
                        </span>
                    </div>
                )}
                <Toggle
                    label="Journal diagnostic (voir tous les rejets)"
                    description="Journalise aussi les setups écartés tôt (pas de biais, pas de POI, hors zone), regroupés. À activer ponctuellement pour comprendre pourquoi des setups sont ignorés — laisse OFF en temps normal."
                    value={local.verbose_journal}
                    onChange={(v) => setAndSave("verbose_journal", v)}
                    testid="settings-verbose-journal"
                />
            </Section>


            {/* Contexte journalier */}
            <Section title="Contexte journalier">
                <div className="text-xs text-text-secondary -mt-1">
                    Les deux seuls concepts de la playlist appuyés par un backtest à grande
                    échelle — mais sur indices, <b>pas sur l&apos;or</b>. À valider en backtest sur
                    XAUUSD avant d&apos;en faire des verrous.
                </div>
                <Toggle
                    label="Daily Bias (PDH / PDL) obligatoire"
                    description="Le biais doit correspondre au sens du jour : clôture au-delà du haut/bas de la veille (continuation), ou sweep puis réintégration (retournement). Un inside day bloque tout trade."
                    value={local.require_daily_bias}
                    onChange={(v) => setAndSave("require_daily_bias", v)}
                    testid="settings-require-daily-bias"
                />
                <Toggle
                    label="Power of 3 obligatoire"
                    description="La mèche de manipulation du jour doit aller dans le sens du biais."
                    value={local.require_po3}
                    onChange={(v) => setAndSave("require_po3", v)}
                    testid="settings-require-po3"
                />
                <NumberField label="Power of 3 — taille minimale de la mèche (0-1)"
                    value={local.po3_wick_ratio}
                    onChange={(v) => setAndSaveDebounced("po3_wick_ratio", v)} step={0.05}
                    testid="settings-po3-ratio" />
            </Section>


            {/* TP échelonnés */}
            <Section title="Take profit échelonnés">
                <Toggle
                    label="Prises partielles TP1 / TP2 / TP3"
                    description="Actif par défaut. TP1 encaisse une part et remonte le stop à l'entrée, TP2 une autre part, le reste court jusqu'à la cible finale. Le stop et la cible finale restent posés chez le broker : si l'app s'arrête, la position reste protégée."
                    value={local.partial_tp_enabled}
                    onChange={(v) => setAndSave("partial_tp_enabled", v)}
                    testid="settings-partial-tp"
                />
                {local.partial_tp_enabled && (
                    <>
                        <NumberField label="TP1 — distance (en R)" value={local.tp1_r}
                            onChange={(v) => setAndSaveDebounced("tp1_r", v)} step={0.1}
                            testid="settings-tp1-r" />
                        <NumberField label="TP1 — part fermée (%)" value={local.tp1_close_pct}
                            onChange={(v) => setAndSaveDebounced("tp1_close_pct", v)} step={5}
                            testid="settings-tp1-pct" />
                        <Toggle
                            label="Stop au break-even après TP1"
                            description="Le trade devient gratuit dès la première prise."
                            value={local.tp1_to_breakeven}
                            onChange={(v) => setAndSave("tp1_to_breakeven", v)}
                            testid="settings-tp1-be"
                        />
                        <NumberField label="TP2 — part fermée (%)" value={local.tp2_close_pct}
                            onChange={(v) => setAndSaveDebounced("tp2_close_pct", v)} step={5}
                            testid="settings-tp2-pct" />
                        <div className="text-xs text-gold bg-gold/10 border border-gold/30 rounded-xl p-3 flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                            <span>
                                Gestion active par défaut, conforme à la stratégie. Elle donne
                                plus de trades gagnants mais un gain moyen plus faible, car le
                                runner est écrêté par les prises. Désactive-la pour revenir au
                                take profit unique et <b>comparer les deux en backtest</b>.
                            </span>
                        </div>
                    </>
                )}
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

            {/* Connexion de CET appareil au backend. Rarement utile, mais indispensable
                sur un nouvel appareil ou après réinstallation de l'APK : sans la clé API,
                l'application ne peut plus joindre le serveur. Replié, jamais supprimé. */}
            <details className="bg-panel border border-bd rounded-card p-4" data-testid="settings-depannage">
                <summary className="text-[11px] font-bold uppercase tracking-widest text-text-secondary cursor-pointer flex items-center gap-2">
                    <Globe className="w-4 h-4" />Dépannage — connexion de cet appareil
                </summary>
                <div className="text-xs text-text-secondary mt-3">
                    À ne toucher que si l&apos;application n&apos;arrive plus à joindre le serveur
                    (nouvel appareil, APK réinstallée). Ces deux valeurs sont mémorisées sur cet
                    appareil uniquement, pas en base.
                </div>
                <div className="space-y-3 mt-3">
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
                    <Field label="Clé API (si le serveur en exige une)">
                        <input
                            type="password"
                            value={apiKey}
                            onChange={(e) => setApiKeyLocal(e.target.value)}
                            placeholder="Clé secrète (header X-API-Key)"
                            className="num w-full bg-bg border border-bd rounded-xl px-3 py-3 focus:border-gold focus:outline-none"
                            data-testid="settings-api-key"
                        />
                    </Field>
                    <div className="text-xs text-text-secondary">
                        Doit correspondre à la variable d&apos;environnement API_KEY du backend
                        (mémorisée sur cet appareil). Laisser vide si le serveur n&apos;en exige pas.
                    </div>
                    <button
                        onClick={() => { setBackendUrl(backendUrl); setApiKey(apiKey); window.location.reload(); }}
                        className="w-full py-3 border border-bd rounded-xl text-text-primary hover:border-gold/50 transition-colors flex items-center justify-center gap-2"
                        data-testid="settings-backend-url-apply"
                    >
                        <Save className="w-4 h-4" />
                        <span className="text-sm">Appliquer et recharger</span>
                    </button>
                </div>
            </details>

            {/* Save All */}
            <button onClick={() => save(local)} disabled={saving}
                className="w-full py-3.5 bg-gold text-bg font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-60 flex items-center justify-center gap-2"
                data-testid="save-all-settings">
                <Save className="w-4 h-4" />
                <span>{saving ? "Sauvegarde…" : "Sauvegarder tous les paramètres"}</span>
            </button>

        </div>
    );
}

// ─── Configuration validée en backtest, affichée en lecture seule ───────────────
// Référence : campagne des trois périodes (2026-08-26), appliquée en prod le 2026-08-27.
// 576 trades, PF 1,21. Les réglages listés ici ne sont plus modifiables depuis l'écran :
// ce bloc existe pour qu'on puisse VOIR qu'ils sont bien appliqués, et repérer une dérive.
const CONFIG_VALIDEE = {
    trading_mode: "intraday",
    intraday_d1: "D1", intraday_htf: "H1", intraday_mtf: "M15", intraday_ltf: "M1",
    require_unmitigated_ob: true, require_premium_discount: true,
    require_fvg_entry: false, require_sweep_then_choch: false, require_displacement: false,
    require_second_choch: false, require_inducement_swept: false, require_ote: false,
    require_daily_bias: false, require_po3: false,
    session_london_start: "08:00", session_london_end: "17:00",
    session_newyork_start: "08:00", session_newyork_end: "17:00",
    min_rr: 1, partial_tp_enabled: true, risk_per_trade_pct: 1,
    max_consec_losses: 3, max_drawdown_pct: 3, trailing_mode: "off",
    swing_method: "two_candle", ob_zone: "wick", structure_break_mode: "close",
    poi_source: "ob", ob_entry_mode: "close", sl_mode: "poi", tp_target: "range_bound",
};

function memeValeur(a, b) {
    if (typeof b === "number") return Number(a) === b;
    return a === b;
}

function ConfigValidee({ local }) {
    const derives = Object.keys(CONFIG_VALIDEE).filter(
        (k) => !memeValeur(local[k], CONFIG_VALIDEE[k])
    );
    const illimite = Number(local.max_trades_per_day) >= 999999;
    const ok = derives.length === 0 && illimite;

    const lignes = [
        ["Mode", local.trading_mode],
        ["Étages", [local.intraday_d1, local.intraday_htf, local.intraday_mtf, local.intraday_ltf].filter(Boolean).join(" → ")],
        ["Filtre actif", local.require_unmitigated_ob ? "Order block non mitigé" : "aucun"],
        ["Premium / Discount", local.require_premium_discount ? "exigé" : "désactivé"],
        ["Sessions (heure locale)", `Londres ${local.session_london_start}–${local.session_london_end} · New York ${local.session_newyork_start}–${local.session_newyork_end}`],
        ["RR minimum", local.min_rr],
        ["Risque par trade", `${local.risk_per_trade_pct} %`],
        ["TP échelonnés", local.partial_tp_enabled ? "activés" : "désactivés"],
        ["Trades par jour", illimite ? "illimité" : local.max_trades_per_day],
        ["Arrêts auto", `${local.max_consec_losses} pertes d'affilée · drawdown ${local.max_drawdown_pct} % (par jour)`],
    ];

    return (
        <div className={`border rounded-card p-4 ${ok ? "bg-panel border-bd" : "bg-red/10 border-red/40"}`}
             data-testid="settings-config-validee">
            <div className="text-[11px] font-bold uppercase tracking-widest text-text-secondary mb-1 flex items-center gap-2">
                {ok ? <CheckCircle2 className="w-4 h-4 text-green" /> : <AlertTriangle className="w-4 h-4 text-red" />}
                Configuration validée
            </div>
            <div className="text-xs text-text-secondary mb-3">
                {ok
                    ? "Le moteur tourne exactement sur la configuration mesurée en backtest (576 trades, profit factor 1,21). Ces réglages ne sont plus modifiables depuis cet écran."
                    : "⚠ Un ou plusieurs réglages ne correspondent plus à la configuration mesurée. Signale-le avant de démarrer le bot."}
            </div>
            <div className="space-y-1.5">
                {lignes.map(([k, v]) => (
                    <div key={k} className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-text-secondary text-xs flex-shrink-0">{k}</span>
                        <span className="num text-right text-text-primary">{String(v)}</span>
                    </div>
                ))}
            </div>
            {!ok && (
                <div className="text-xs text-red mt-3 break-words">
                    Écarts : {[...derives, ...(illimite ? [] : ["max_trades_per_day"])].join(", ")}
                </div>
            )}
            <div className="text-[11px] text-text-secondary mt-3 leading-relaxed">
                Les performances passées ne préjugent pas des performances futures. Le filtre
                « order block non mitigé » n&apos;est pas démontré supérieur à son absence : c&apos;est
                un choix par défaut, pas un acquis.
            </div>
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

