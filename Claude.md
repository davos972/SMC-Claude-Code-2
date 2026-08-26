# CONTEXTE PROJET — GoldFlow SMC (bot de trading automatique MT5)

> Prompt de contexte pour Claude Code. Lis ce document en entier avant toute modification du code.

## 1. Vision du projet

Application web de **trading 100% automatique** sur **MetaTrader 5**, basée sur la stratégie **Smart Money Concepts (SMC)**. Développée initialement avec Emergent, code sur GitHub : `davos972/SMC-APP` (backend FastAPI/Python + frontend React, base MongoDB).

- Instrument actif : **XAUUSD (or)** — architecture multi-symboles prévue pour ajouter des indices (US30, NAS100) plus tard
- Compte **démo par défaut** ; passage en réel verrouillé derrière une double confirmation explicite
- Propriétaire : David, utilisateur non-développeur — explique tes changements simplement, en français

## 2. Décisions d'architecture VERROUILLÉES (ne pas remettre en question)

1. **Connexion MT5 via MetaApi (metaapi.cloud)** exclusivement — jamais de connexion directe MT5, jamais de données simulées ou codées en dur. SDK : `metaapi_cloud_sdk` (Python)
2. **SL et TP toujours placés chez le broker** dans l'ordre envoyé — jamais gérés uniquement par l'app
3. **Un seul moteur SMC** (`backend/smc.py`) partagé entre trading live et backtest — interdiction d'avoir deux logiques
4. Chaque ordre du bot porte un **magic number/commentaire** ; le bot ne touche jamais aux positions sans cet identifiant
5. Base **MongoDB**, app **mono-utilisateur sans login**, secrets dans `backend/.env` (non versionné). Depuis l'audit 2026-07-09 : l'API publique (Render) se protège par **clé API** (`API_KEY` côté serveur + header `X-API-Key`, saisie dans Réglages → Serveur) — indispensable en prod, sinon l'API de trading est ouverte à tous
6. Pas de widget TradingView : graphique **lightweight-charts** alimenté par les bougies MetaApi

## 3. Stratégie SMC (règles du moteur)

> Depuis le 2026-08-25, le moteur suit le **« Manuel de détection SMC »** et la
> **« Synthèse stratégie V3 »** fournis par David (voir DECISIONS.md). Toute méthode
> antérieure reste accessible en réglage pour être comparée en backtest.

- **Analyse top-down 4 étages** : contexte journalier (D1) → biais (HTF) → structure/POI (MTF) → déclencheur (LTF). L'étage journalier est un ENRICHISSEMENT : le désactiver (`intraday_d1=""`) ramène exactement à l'analyse 3 niveaux d'avant
- **Deux modes** (un seul actif) : Intraday D1→H1→M15→M5 et Scalping H1→M15→M5→M1, tous paramétrables
- **Swing high/low** : **règle des deux bougies** par défaut (`swing_method`) — un sommet est validé après 2 bougies baissières consécutives. La comparaison est `>=`, donc les **sommets ÉGAUX (doubles sommets) sont détectés**, ce que la fractale stricte manquait. Fractale N bougies toujours disponible
- **Biais haute timeframe** : structure de marché (HH/HL, LH/LL), BOS (continuation), CHoCH (retournement). Cassure sur clôture (défaut) ou sur mèche (`structure_break_mode`)
- **Liquidité BSL/SSL** : les sommets ALIGNÉS forment un seul réservoir, d'autant plus gros qu'il a été testé souvent. Niveaux **protégés** (creux en tendance haussière) vs **cibles**. Peuvent inclure PDH/PDL et les bornes du range asiatique
- **Zones d'intérêt** : order blocks (**tracés mèches comprises**, `ob_zone`), FVG, IFVG, BPR, Breaker, Mitigation et Rejection Blocks, sweeps, premium/discount, OTE 62-79%. Les zones acceptées comme POI se choisissent dans `poi_source`
- **Inducement** : le piège à stops juste avant la POI, détecté et affiché
- **Entrée basse timeframe** valide si : biais clair + retour dans une POI bien placée + sweep ou CHoCH LTF + RR minimum atteignable. Confluences supplémentaires toutes **OFF par défaut** (displacement, second CHOCH, inducement pris, OTE, Daily Bias, Power of 3)
- **Règle de méthode (Synthèse V3 §10)** : noyau + **1 à 3 confluences maximum**. Ne JAMAIS tout activer en même temps — « cet empilement ne se produit quasiment jamais et paralyse l'exécution ». Chaque variable se teste SÉPARÉMENT en backtest
- **Analyse à la clôture de bougie** de la timeframe d'entrée (pas tick par tick)
- **Sessions strictes** : trading UNIQUEMENT pendant Londres (8h–11h heure de Londres) et New York (8h–11h heure de NY), heure d'été gérée via pytz (`backend/sessions.py`). Les positions ouvertes restent ouvertes après la session (protégées par SL/TP broker)

## 4. Gestion du risque (tout paramétrable dans Réglages)

- Risque par trade 0,25–2% (défaut 1%), lot calculé selon la distance du SL
- SL structurel (sous/sur l'order block ou le sweep), TP sur la liquidité opposée, RR minimum (défaut 1:2) sinon trade ignoré
- **Arrêt auto après 3 pertes consécutives** (break-even ne compte pas) — reprise paramétrable : prochaine session (défaut) ou lendemain
- **Arrêt auto sur drawdown max** (défaut 3%) — même politique de reprise
- Max 5 trades/jour, une seule position par symbole
- **Mode prop firm** activable (défauts calés BlueGuardian Instant Funding : DD jour/total, Guardian Shield, reset 17h EST, high watermark trailing ; marge de sécurité 20% — s'arrête AVANT les limites réelles ; paramétrable pour d'autres firmes)
- **Filtre news** : pause 30 min avant/après les annonces USD à fort impact (flux Forex Factory / faireconomy, `backend/news.py`)
- ~~Mode « Signal uniquement »~~ : **retiré le 2026-08-25** (David trade sur compte démo Axi, où il n'apportait rien). Un setup validé part toujours à l'exécution. Le verrou du compte réel (`account_type` + double confirmation `real_confirmed`) est indépendant et reste en place
- **Trailing stop** : implémenté (logique unique `compute_trailing_sl` partagée live + backtest ; modes breakeven / r_trail / structure), **OFF par défaut**
- **TP partiels TP1/TP2/TP3** : implémentés depuis le 2026-08-25 (décision D3, cf. DECISIONS.md) — la règle « non implémentés volontairement » est LEVÉE. Échelle unique `compute_tp_ladder` partagée live + backtest. **ACTIVÉS PAR DÉFAUT** : TP1 à 1R ferme 50% et remonte le SL à l'entrée, TP2 (mi-chemin TP1↔TP3) ferme 30%, les 20% restants courent jusqu'à la cible. C'est la gestion de position décrite par la stratégie, pas une option. Le SL et le TP FINAL restent posés chez le broker : si l'app s'arrête, la position reste protégée comme avant. `partial_tp_enabled=False` rétablit le TP unique historique pour comparer en backtest

## 5. Fonctionnalités de l'app

- **Dashboard** : bouton START/STOP manuel rond + rail des sessions 24h avec marqueur « maintenant », solde/équité/P&L jour, graphique avec zones SMC, positions ouvertes avec clôture d'urgence, journal des signaux (y compris setups REJETÉS avec la raison), annonces éco du jour
- **Backtest** (simple) : config actuelle sur période choisie (max 6 mois), données M1 MetaApi, spread simulé paramétrable (défaut 25 points XAUUSD), rapport (winrate, profit factor, RR, DD max, courbe d'équité, liste des trades cliquables sur le graphique), avertissement performances passées
- **Journal de trading** (onglet « Stats ») : les trades RÉELS du bot, stockés dans la
  collection Mongo `trades` (écrite par `bot_loop` à l'ouverture puis à la clôture, avec
  le P&L réel du broker). P&L global, nb de trades, winrate, profit factor, drawdown max,
  courbe d'évolution vs capital de départ (réglage `journal_initial_balance`, 0 = déduit
  du solde), et le détail de chaque trade : jour/heure, RR prévu, TP ou SL touché, SL
  suiveur, et les **réglages qui différaient des défauts** au moment du trade. Endpoints
  `GET /api/journal` et `POST /api/journal/import` (import de l'historique broker MetaApi,
  filtré sur le magic number). Métriques calculées par `backtest._compute_metrics` —
  ne jamais en écrire une seconde version
- **Notifications** : in-app (cloche + historique) + push navigateur (Web Push), chaque événement activable
- **Réglages** : token MetaApi + accountId (masqué, jamais exposé au frontend), démo/réel verrouillé, tous les paramètres ci-dessus

## 6. Spécifications visuelles (à respecter strictement)

- Mobile-first, colonne unique max 480px, navigation par onglets en bas (Dashboard/Backtest/Stats/Réglages), mode sombre
- Palette : fond `#0D1117`, panneaux `#151B24`, bordures `#242E3D`, accent or `#E3B341`, vert `#3FB68B`, rouge `#E0635E`, texte `#E9ECF2` / `#8A94A6`. Chiffres en monospace tabulaire
- **Zones SMC sur le graphique** (décision récente, vérifier que c'est implémenté) :
  - FVG : rectangle à **bordure continue**, fond semi-transparent **vert (haussier) / rouge (baissier)**
  - Order block : rectangle à **bordure jaune pointillée**, fond jaune léger
  - Liquidity sweep : **flèche rouge** pointant la mèche + label « Sweep »
  - BOS/CHoCH : **ligne horizontale bleue pointillée** + label « BOS ↑/↓ » ou « CHoCH ↑/↓ »
  - Les zones s'étendent à droite jusqu'à mitigation, puis disparaissent ou passent en opacité réduite. Légende sous le graphique
- **Calques (depuis 2026-08-25)** : les zones ajoutées (BSL/SSL, inducement, range asiatique, OTE, IFVG, BPR, Breaker/Mitigation/Rejection) s'affichent par calques activables, **tous OFF par défaut**. Sur une colonne de 480px, tout afficher rend le graphique illisible — et c'est exactement ce que la Synthèse V3 §10 reproche. Le choix est mémorisé par appareil (localStorage). La légende suit les calques actifs

## 6bis. Déploiement réel et app mobile (état au 2026-07-08)

- **La prod tourne sur Render** : `goldflow-backend` (+ `goldflow-frontend` statique), auto-déployée à chaque push GitHub `main`. Base : **MongoDB Atlas** (`cluster0.lfishca…`, base `goldflow`) — c'est LA mémoire vivante ; un Mongo local ne sert qu'aux tests. ⚠️ Ne jamais lancer un backend local pointé sur Atlas pendant que Render tourne : l'auto-reprise ferait courir DEUX bots sur le même compte.
- **App mobile Android** : Capacitor (`frontend/android/`, appId `com.goldflow.smc`), APK compilé par GitHub Actions (`.github/workflows/android-apk.yml`, « Run workflow », artifact `goldflow-smc-apk`). URL backend modifiable par appareil (Réglages → Serveur). `CORS_ORIGINS` sur Render doit contenir `https://localhost` (origine Capacitor).
- **Notifications push app fermée** : Firebase FCM (`backend/push.py`), clé de service dans l'env `FIREBASE_SERVICE_ACCOUNT` (Render/`.env`, JAMAIS dans Git — `google-services.json` versionné est OK, c'est une config client). Endpoints `/api/push/register` et `/api/push/test`. Toute notification in-app part aussi en push.
- **Clé API (audit 2026-07-09)** : définir `API_KEY` dans Render → toute requête `/api` (sauf `/` et `/health`) exige le header `X-API-Key`. La clé se saisit dans l'app : Réglages → Serveur → Clé API (stockée par appareil). Sans `API_KEY` définie, l'auth est désactivée (ordre de déploiement sûr : pousser le code, puis créer la clé, puis la saisir dans l'app).

## 7. État actuel et problèmes connus

### Point d'état au 2026-08-25 (fin de la session « alignement sur les documents SMC »)

**Déployé en prod.** `main` = `d90c6a7`, Render redéployé, APK n°9 compilé sur ce commit
(signature permanente : s'installe par-dessus l'ancienne app sans désinstaller).

**Ce qui a changé** : moteur aligné sur le Manuel de détection SMC et la Synthèse
stratégie V3 (15 décisions B1–B6 / D1–D9, détail dans DECISIONS.md). Analyse à 4 étages,
liquidité BSL/SSL, inducement, IFVG, BPR, Breaker/Mitigation/Rejection, OTE, range
asiatique, Daily Bias, Power of 3.

**Deux règles verrouillées levées** : TP partiels (implémentés ET **activés par défaut**)
et mode « Signal uniquement » (**supprimé** — David est sur compte démo Axi).

⚠️ **Conséquence à connaître** : le bot passe désormais de vrais ordres dès qu'un setup
valide se présente en session. Le seul frein logiciel restant est le bouton START/STOP.
Le verrou du compte réel (`account_type` + `real_confirmed`) est intact.

**État des filtres** : tout ce qui a été ajouté est OFF par défaut, SAUF les TP partiels.
Le comportement de détection, lui, a changé (swings 2 bougies, OB en mèches, TP borne de
range) — ce ne sont pas des options mais les nouveaux défauts.

### Correctif du 2026-08-26 — anticipation dans le backtest

Le moteur de backtest **lisait le futur** sur les étages HTF/MTF/D1 (détail : DECISIONS.md
2026-08-26 et §9). Corrigé, avec test de non-régression. **Conséquence : tout chiffre de
backtest produit avant ce commit est optimiste et ne doit plus être cité** — y compris les
comparaisons du 2026-07-28 (`_compare_entry_options`) et la première matrice des 40
variantes du 2026-08-25/26. Ordre de grandeur mesuré sur 6 mois de XAUUSD M1 : ligne de
base PF 0,85 → 0,81 ; filtre Daily Bias PF 1,52 → 0,80.

### Campagne de backtests du 2026-08-26 (moteur corrigé) — points 1 à 4 traités

47 configurations rejouées sur 6 mois de M1 réel + validation **hors échantillon**
(12 juin → 26 août). Détail complet : DECISIONS.md 2026-08-26. En résumé :

- **Retenu, pas encore appliqué en prod** : `require_unmitigated_ob` + `sl_mode="protected"`
  (243 trades, PF 1,26, DD 8 %, t +1,68 ; au-dessus de la référence sur les deux périodes)
- **Piège évité** : `ob_entry_mode="zone_50"` finissait n°1 en étude (PF 1,43, t +2,06) et
  fait **0,72** hors échantillon. → **Toute règle candidate doit battre la référence sur
  les DEUX périodes.** Un t significatif sur la seule période d'étude ne prouve rien
- **Power of 3 (question en suspens) : tranchée.** Seuils 0,20 / 0,35 / 0,50 testés, aucun
  n'aide (0,93-0,95 vs 0,97). Ne pas y revenir sans nouvelle donnée
- **Daily Bias sur XAUUSD** : positif mais sur trop peu de trades (104) pour conclure
- **TP partiels vs TP unique** : winrate 49 % vs 32 %, PF identique — confort de lecture,
  pas d'espérance en plus
- **Dégradent la référence** : OTE (0,71), inducement (0,79), FVG obligatoire (0,82),
  Rejection block (0,90), séquence sweep→CHoCH (0,94), sans premium/discount (0,94)

### Ce qui reste à faire

1. **Valider en démo** la configuration retenue avant de l'appliquer en prod (t +1,68 < 2 :
   piste sérieuse, pas preuve).
2. Non implémentés volontairement : **OB 2.0** (impose un 5e étage de timeframe) et
   **SMT Divergence** (impose de suivre un 2e instrument corrélé en continu, casserait
   l'architecture mono-symbole). La Synthèse V3 les classe elle-même en dernier.

### Diagnostic historique (résolu)

~~Problème en cours~~ **Résolu (2026-07-08)** — l'échec de connexion venait du `.env` local pointé sur un Mongo local vide alors que la prod Render/Atlas tournait ; le `.env` local pointe désormais sur Atlas. Diagnostic d'époque conservé :
1. `backend/.env` non versionné → base MongoDB neuve → token perdu (à ressaisir dans Réglages)
2. `metaapi_client.py/_connect` : timeouts `deploy()` et `wait_connected()` de 30 s trop courts — un redéploiement de compte inactif prend 1-2 min → porter à **240 s**
3. `frontend/src/api/client.js` : timeout axios global 30 s → créer une instance `apiLong` (300 s) pour `testConnection`, `candles`, `startBacktest`
4. À ajouter : fallback `METAAPI_TOKEN`/`METAAPI_ACCOUNT_ID` depuis le `.env` au démarrage si la base est vide ; affichage de l'état du compte (`DEPLOYING`...) et de `last_error` dans Réglages

## 8. Marche à suivre choisie

1. Corriger la connexion MetaApi (point 7) en priorité
2. Vérifier la conformité du graphique aux specs visuelles SMC du point 6 (styles récents, possiblement pas encore implémentés)
3. Fiabiliser le backtest : téléchargement M1 par lots avec pauses (limites de débit MetaApi), progression en % visible, try/catch global passant le statut à « error » avec message consultable, timeout global 15 min, bouton annuler/supprimer
4. Valider sur compte démo plusieurs jours avant tout passage en réel (le mode « Signal uniquement » a été retiré ; la validation se fait en backtest puis en démo)
5. Toujours : tester chaque changement, demander/montrer les logs en cas d'erreur plutôt que corriger à l'aveugle

### Plan de backtest des nouvelles règles (Synthèse V3 §11)

Tout ce qui a été ajouté le 2026-08-25 est **désactivé par défaut**. La méthode pour
décider quoi garder — tester chaque variable SÉPARÉMENT, jamais en bloc :

| Variable | Options à comparer une par une |
|---|---|
| Détection des swings | `swing_method` : two_candle vs fractal |
| Tracé de l'OB | `ob_zone` : wick vs body |
| Cible du TP | `tp_target` : range_bound vs liquidity vs nearest_swing |
| Placement du SL | `sl_mode` : poi vs protected |
| Mode d'entrée | `ob_entry_mode` : close vs zone_50 vs tap |
| Type de zone POI | `poi_source` : ob, bpr, breaker, mitigation, rejection (un seul à la fois) |
| Confluences | displacement, second CHOCH, inducement pris, OTE, Daily Bias, PO3 (une à la fois) |
| Gestion | `partial_tp_enabled` : TP unique vs TP1/TP2/TP3 |
| Liquidité | `use_pdh_pdl_liquidity`, `use_asia_liquidity` |

Le backtest accepte ces clés **directement dans la requête**, ce qui permet de comparer
deux méthodes sans rien changer dans les Réglages de l'app.

⚠️ Les chiffres de la Synthèse V3 (68% Daily Bias, 97,75% Power of 3) viennent de
GER40 et d'indices, **pas de l'or**. Ils ne se transfèrent pas automatiquement à XAUUSD.

### Protocole OBLIGATOIRE avant tout backtest (règle posée par David le 2026-08-26)

Un backtest lancé sur un moteur périmé ou avec des réglages non validés ne « donne pas
une indication » : il fait perdre des heures et oriente des décisions dans le vide.
Avant de lancer le moindre backtest, dans cet ordre :

1. **Vérifier que le dépôt local est à jour** : `git fetch origin && git status -sb`.
   S'il est en retard sur `origin/main`, mettre à jour AVANT (la prod tourne sur
   `origin/main`, pas sur la copie locale). Vérifier aussi qu'aucune correction du moteur
   n'est en cours : backtester avec un moteur différent de celui du live n'a aucune valeur.
2. **Lister à David TOUS les réglages qui seront en vigueur** — pas seulement ceux qui
   changent : timeframes des 4 étages, spread, capital, risque, RR minimum, sessions,
   limites (trades/jour, pertes consécutives, drawdown), filtres actifs/inactifs, gestion
   (trailing, TP partiels), période et source des données. Il valide AVANT le lancement.
3. **Rappeler les écarts** entre ces réglages et ceux réellement enregistrés en prod
   (base Atlas), pour qu'il sache ce qui est testé vs ce qui tourne.
4. À la restitution : dire quel moteur (commit) a produit les chiffres, et ce qui n'est
   pas modélisé (commissions, slippage, exécution partielle).
5. **Ne JAMAIS modifier `smc.py`/`backtest.py` pendant qu'une matrice de backtests
   tourne.** Chaque backtest est un processus séparé qui importe le moteur à son
   démarrage : une édition en cours de route fait planter ceux qui démarrent pendant
   la fenêtre d'incohérence (vécu le 2026-08-26 : 8 runs perdus sur un `NameError`),
   et pire, ceux qui passent tournent avec une version différente des autres.

## 9. Garde-fous pour Claude Code

- Ne jamais committer de token/secret ; `.env` reste hors Git
- Ne jamais simplifier la stratégie SMC vers des indicateurs classiques (moyennes mobiles, RSI)
- Ne jamais envoyer d'ordre sans SL/TP
- Ne pas activer le compte réel ni assouplir sa double confirmation
- Préserver le mode dégradé explicite : si MetaApi n'est pas configuré/connecté, afficher l'erreur, jamais de données factices
- Ne pas affaiblir la protection par clé API (`API_KEY`/`X-API-Key`) ni élargir `_PUBLIC_PATHS` dans `server.py`
- **Une seule conversion réglages → moteur** : `smc.params_from_settings`. Les QUATRE appelants d'`analyze()` (bot live, backtest, analyse du dashboard, rejeu) doivent passer par elle. Sans ça, le graphique finit par afficher des zones tracées avec d'autres réglages que ceux qui décident des trades — c'est exactement ce qui était arrivé aux deux appels de `server.py`
- **Toute nouvelle règle SMC arrive DÉSACTIVÉE** : détectée et affichée, mais jamais imposée comme filtre tant qu'un backtest ne l'a pas validée (Synthèse V3 §10 et §11)
- **Jamais d'anticipation dans le backtest** : ne jamais pré-agréger une bougie EN COURS. La règle vaut pour les QUATRE étages, pas seulement le journalier. Elle a été violée jusqu'au 2026-08-26 : les fenêtres HTF/MTF/D1 étaient découpées avec `bisect_right` sur les temps de **début**, ce qui livrait la bougie supérieure en cours déjà agrégée avec son high/low/close définitifs (prouvé : en analysant la M1 de 16:47, le moteur voyait la M5 16:45→16:49 terminée). Toute bougie supérieure non clôturée doit être reconstruite depuis les bougies du niveau d'entrée écoulées (`backtest._partial_bar`). Test de non-régression : `backend/tests/test_backtest_lookahead.py`
- Journal de trading : ne JAMAIS combler un P&L manquant par une estimation. Si
  l'historique broker est indisponible, le trade est clôturé avec `result: "unknown"` et
  `pnl: null`, et il est exclu des statistiques (visible dans la liste, jamais compté)

## 10. Environnement local et commandes (Windows 11, PowerShell)

- Backend : `cd backend` puis `py -m uvicorn server:app --reload --port 8000` — le frontend attend le backend sur `http://localhost:8000` (cf. `frontend/.env`, `REACT_APP_BACKEND_URL`). App FastAPI : `app` dans `server.py`. Dépendances : `py -m pip install -r requirements.txt` (Python 3.14 système, pas de venv dans ce dépôt)
- Frontend : `cd frontend` puis `npm start` (CRA + CRACO)
- Nécessite un MongoDB accessible (cf. `backend/.env`) ; sans MetaApi configuré, l'app démarre en mode dégradé — c'est normal et attendu

## 11. Convention : fichiers préfixés `_` dans `backend/`

Tous les fichiers `_*.py`, `_*.txt`, `_*.log`, `_m1_cache_*.json` sont des **scripts d'expérimentation et des caches jetables** (backtests mensuels, comparaisons de modèles, essais de trailing). Ils ne font PAS partie de l'application : l'app ne doit jamais les importer, ils sont à ignorer en revue de code, et ils sont supprimables sans risque. Ne jamais y placer de logique dont l'app dépend. Le `.gitignore` couvre désormais tout `backend/_*`.

## 12. Tests — état réel (au 2026-07-07)

`backend/tests/backend_test.py` tourne maintenant en local sur Windows. Les chemins
`/app/...` codés en dur ont été remplacés par des chemins résolus depuis `__file__`
(racine du dépôt), et `REACT_APP_BACKEND_URL` est lu depuis `frontend/.env` avec
priorité à la variable d'environnement si elle est déjà définie.

**Tests unitaires (depuis le 2026-08-26) — ni serveur, ni MongoDB, ni MetaApi :**
```powershell
py -m pytest backend/tests/test_backtest_lookahead.py -v
```
Attendu : `3 passed`. Ils vérifient que le backtest ne voit jamais le futur (cf. §9).
C'est le modèle à suivre pour tout nouveau test du moteur : rapide, sans dépendance.

**`backend_test.py`, lui, est un test d'intégration : le backend doit tourner AVANT de lancer pytest.**
Ils tapent sur l'API HTTP (`http://localhost:8000/api`), ils ne démarrent pas le
serveur eux-mêmes. Ils s'exécutent en **mode dégradé** (sans token MetaApi valide) —
c'est voulu : ils vérifient que l'app refuse de simuler des données quand MetaApi
n'est pas connecté.

Procédure exacte (deux terminaux PowerShell), depuis `SMC App/repo/` :

1. **Terminal A — démarrer le backend en mode dégradé, sur une base jetable.**
   Il faut vider `METAAPI_TOKEN`/`METAAPI_ACCOUNT_ID` (sinon le `.env` fournit un
   token et l'app démarre « configurée »), et utiliser une base de test dédiée
   (les tests écrivent en base ; ne pas polluer `goldflow`) :
   ```powershell
   cd backend
   $env:METAAPI_TOKEN=""; $env:METAAPI_ACCOUNT_ID=""; $env:DB_NAME="goldflow_test"
   py -m uvicorn server:app --port 8000
   ```
   Prérequis : MongoDB accessible (cf. `backend/.env`, `MONGO_URL`) et
   `py -m pip install -r requirements.txt` + `py -m pip install pytest`.
   Vérifier que `http://localhost:8000/api/health` renvoie `"configured": false`.
   NB : ne pas définir `API_KEY` dans l'environnement de test (sinon toutes les
   requêtes des tests seraient rejetées en 401).

2. **Terminal B — lancer les tests :**
   ```powershell
   py -m pytest backend/tests/backend_test.py -v
   ```
   Attendu : `25 passed`.

**Piège — variables d'environnement vides sous PowerShell (découvert 2026-08-10).**
`$env:METAAPI_TOKEN=""` SUPPRIME la variable au lieu de la vider → `load_dotenv()`
recharge alors le vrai token depuis `backend/.env` et le serveur démarre CONNECTÉ
à MetaApi (pas en mode dégradé). Démarrer le backend de test via un wrapper Python,
où une variable vide existe réellement :
```powershell
cd backend
py -c "import os; os.environ['METAAPI_TOKEN']=''; os.environ['METAAPI_ACCOUNT_ID']=''; os.environ['DB_NAME']='goldflow_test'; import uvicorn; uvicorn.run('server:app', host='127.0.0.1', port=8000)"
```

**Piège — base propre à chaque exécution.** Un test (`TestZTokenPreservation`) écrit
un faux token en base ; à la relance suivante le backend redémarre « configuré » et
2 tests échouent à tort. Pour rejouer proprement : soit repartir d'une base neuve
(changer `DB_NAME`, ex. `goldflow_test2`), soit supprimer la base de test avant de
relancer le backend. Ne jamais pointer les tests sur la base de production `goldflow`.

## 13. Traces à laisser (pour tout modèle qui travaille ici)

- Décision structurante prise en cours de tâche → entrée dans `DECISIONS.md` (décision, pourquoi, alternatives écartées)
- Piège découvert ou erreur corrigée → ligne dans ce fichier (§9 si c'est un garde-fou)
- Les protocoles complets de travail sont dans les skills `/implementer` et `/revue`, et la méthode générale dans `../../METHODE.md`
