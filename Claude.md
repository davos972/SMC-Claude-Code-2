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
5. Base **MongoDB**, app **mono-utilisateur sans login**, secrets dans `backend/.env` (non versionné)
6. Pas de widget TradingView : graphique **lightweight-charts** alimenté par les bougies MetaApi

## 3. Stratégie SMC (règles du moteur)

- **Biais haute timeframe** : structure de marché (HH/HL, LH/LL), BOS (continuation), CHoCH (retournement)
- **Zones d'intérêt** : order blocks, Fair Value Gaps, liquidity sweeps, zones premium/discount (achat en discount, vente en premium uniquement)
- **Entrée basse timeframe** valide si : biais HTF clair + retour dans une POI bien placée + sweep ou CHoCH LTF + RR minimum atteignable
- **Deux modes** (un seul actif à la fois) : Intraday (H1 → M5) et Scalping (M15 → M1), timeframes paramétrables
- **Swing high/low** : méthode fractale, N bougies de chaque côté (défaut 3, paramétrable)
- **Analyse à la clôture de bougie** de la timeframe d'entrée (pas tick par tick)
- **Sessions strictes** : trading UNIQUEMENT pendant Londres (8h–11h heure de Londres) et New York (8h–11h heure de NY), heure d'été gérée via pytz (`backend/sessions.py`). Les positions ouvertes restent ouvertes après la session (protégées par SL/TP broker)

## 4. Gestion du risque (tout paramétrable dans Réglages)

- Risque par trade 0,25–2% (défaut 1%), lot calculé selon la distance du SL
- SL structurel (sous/sur l'order block ou le sweep), TP sur la liquidité opposée, RR minimum (défaut 1:2) sinon trade ignoré
- **Arrêt auto après 3 pertes consécutives** (break-even ne compte pas) — reprise paramétrable : prochaine session (défaut) ou lendemain
- **Arrêt auto sur drawdown max** (défaut 3%) — même politique de reprise
- Max 5 trades/jour, une seule position par symbole
- **Mode prop firm** activable (règles FTMO : DD jour/total, marge de sécurité 20% — s'arrête AVANT les limites réelles)
- **Filtre news** : pause 30 min avant/après les annonces USD à fort impact (flux Forex Factory / faireconomy, `backend/news.py`)
- **Mode « Signal uniquement »** : détecte et journalise sans exécuter — mode par défaut au premier lancement
- TP partiels et trailing stop : NON implémentés volontairement (points d'extension prévus)

## 5. Fonctionnalités de l'app

- **Dashboard** : bouton START/STOP manuel rond + rail des sessions 24h avec marqueur « maintenant », solde/équité/P&L jour, graphique avec zones SMC, positions ouvertes avec clôture d'urgence, journal des signaux (y compris setups REJETÉS avec la raison), annonces éco du jour
- **Backtest** (simple) : config actuelle sur période choisie (max 6 mois), données M1 MetaApi, spread simulé paramétrable (défaut 25 points XAUUSD), rapport (winrate, profit factor, RR, DD max, courbe d'équité, liste des trades cliquables sur le graphique), avertissement performances passées
- **Stats live** : winrate, RR moyen, profit factor, stats par session et jour de semaine
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

## 7. État actuel et problèmes connus

Le code (revue complète faite) est globalement conforme. Problème en cours : **échec de connexion MetaApi** après changement d'environnement. Diagnostic confirmé :
1. `backend/.env` non versionné → base MongoDB neuve → token perdu (à ressaisir dans Réglages)
2. `metaapi_client.py/_connect` : timeouts `deploy()` et `wait_connected()` de 30 s trop courts — un redéploiement de compte inactif prend 1-2 min → porter à **240 s**
3. `frontend/src/api/client.js` : timeout axios global 30 s → créer une instance `apiLong` (300 s) pour `testConnection`, `candles`, `startBacktest`
4. À ajouter : fallback `METAAPI_TOKEN`/`METAAPI_ACCOUNT_ID` depuis le `.env` au démarrage si la base est vide ; affichage de l'état du compte (`DEPLOYING`...) et de `last_error` dans Réglages

## 8. Marche à suivre choisie

1. Corriger la connexion MetaApi (point 7) en priorité
2. Vérifier la conformité du graphique aux specs visuelles SMC du point 6 (styles récents, possiblement pas encore implémentés)
3. Fiabiliser le backtest : téléchargement M1 par lots avec pauses (limites de débit MetaApi), progression en % visible, try/catch global passant le statut à « error » avec message consultable, timeout global 15 min, bouton annuler/supprimer
4. Valider en mode « Signal uniquement » sur compte démo plusieurs jours avant d'activer l'exécution automatique
5. Toujours : tester chaque changement, demander/montrer les logs en cas d'erreur plutôt que corriger à l'aveugle

## 9. Garde-fous pour Claude Code

- Ne jamais committer de token/secret ; `.env` reste hors Git
- Ne jamais simplifier la stratégie SMC vers des indicateurs classiques (moyennes mobiles, RSI)
- Ne jamais envoyer d'ordre sans SL/TP
- Ne pas activer le compte réel ni assouplir sa double confirmation
- Préserver le mode dégradé explicite : si MetaApi n'est pas configuré/connecté, afficher l'erreur, jamais de données factices
