# Journal de décisions — GoldFlow SMC

> Une entrée par décision structurante : quoi, pourquoi, alternatives écartées.
> C'est le « pourquoi le code est comme ça » — ce qui empêche un futur modèle
> (ou toi dans six mois) de « réamériorer » ce qui a été délibérément écarté.
> Ajouter les nouvelles entrées EN HAUT.

## Modèle d'entrée

```
## AAAA-MM-JJ — Titre court
**Décision :** ...
**Pourquoi :** ...
**Écarté :** ... (et pourquoi)
```

---

## 2026-07-30 — APK : signature permanente via secret GitHub (fin des désinstallations forcées)
**Décision :** le workflow `android-apk.yml` signait chaque APK avec la clé de debug JETABLE générée par le runner → signature différente à chaque build → Android refusait toute mise à jour par-dessus l'app installée (vécu par David le 29-07). Désormais une clé PKCS12 permanente (alias/mot de passe standard du debug Android) est injectée depuis le secret GitHub `ANDROID_DEBUG_KEYSTORE_B64` vers `~/.android/debug.keystore` avant le build, avec échec EXPLICITE du workflow si le secret manque (sinon retour silencieux à une clé jetable). Copie de secours de la clé chez David : dossier `cles-apk/` À CÔTÉ du dépôt (jamais dedans). Empreinte SHA-256 : B1:96:C0:98:…:FE:7F. Un dernier cycle désinstaller/réinstaller est nécessaire pour passer sur cette signature.
**Pourquoi :** sans clé stable, chaque mise à jour d'APK exige de désinstaller (perte des réglages d'appareil : URL backend, clé API).
**Écarté :** (1) committer le keystore dans le dépôt — interdit (garde-fou secrets), même privé ; (2) passer en build release signé via build.gradle — plus propre mais touche le projet Android pour le même résultat ; le keystore de debug standard suffit pour une app mono-utilisateur hors Play Store.
**Décision :** à la demande de David (pouvoir tester lui-même), les deux verrous d'entrée mis en évidence par la comparaison du même jour deviennent des Réglages : (1) `ob_entry_mode` — `"close"` (défaut, comportement historique : la clôture doit être DANS le corps de l'OB) ou `"tap"` (une des `recent_window` dernières bougies a touché l'OB, mèches comprises ; l'OB le plus récemment touché parmi les candidats du biais est retenu) — implémenté DANS le moteur unique `smc.py` (`analyze`/`_build_signal`), transmis par `bot_loop`, `backtest` et les deux endpoints d'analyse de `server.py` ; (2) interrupteur « Premium/Discount obligatoire » ajouté à l'UI (la clé backend existait depuis l'audit du 09-07 mais n'était pas exposée). L'UI affiche un avertissement doré explicite quand « tap » est choisi (perdant en backtest : PF 0,85–0,92, DD jusqu'à 68 %). Défauts = comportement d'avant, vérifié au trade près (64 trades, PF 1,23 identiques sur le cache 6 mois) ; « tap » reproduit exactement la variante expérimentale (529 trades). 25/25 tests d'intégration OK.
**Pourquoi :** garder la recommandation « ne rien assouplir » tout en laissant David expérimenter sans modification de code, en backtest ou en mode signal uniquement ; le garde-fou est l'information (avertissement chiffré dans l'UI), pas l'interdiction.
**Écarté :** (1) un second moteur/fork pour le mode tap — interdit (moteur unique) ; (2) élargir la tolérance du test « clôture dans l'OB » (0,1 %) par un paramètre numérique — un troisième réglage cryptique de plus, le select à deux modes est plus lisible ; (3) laisser `require_premium_discount` hors UI — incohérent dès lors qu'on expose le reste.
**Décision :** après 6 semaines quasi sans trade en live (1 exécuté, ~9 450 rejets journalisés dont 82 % « prix hors zone »), comparaison backtest sur 6 mois de M1 XAUUSD (déc. 2025 → juin 2026, cache local, réglages prod : min_rr=1, FVG/séquence/OB-non-mitigé OFF, trailing breakeven ON, risque 2 %) via `_compare_entry_options.py`. Verdict : la config actuelle est LA SEULE nettement rentable (64 trades, WR 42 %, PF 1,23, +1 390 $, DD 9,8 %). Toutes les variantes « plus de trades » dégradent : sans premium/discount (93 trades, PF 1,04), intraday H1/M15/M5 (49 trades, PF 0,85, perdant), moteur « tap » (entrée sur touche de l'OB au lieu de clôture dedans : 204–529 trades, PF 0,85–0,92, DD jusqu'à 68 %). → Le moteur reste inchangé ; la rareté des trades vient surtout du RÉGIME DE MARCHÉ (le même backtest passe de ~11 trades/mois déc.–mars à 3–5/mois avr.–juin) et non d'un bug.
**Pourquoi :** l'exigence « clôture dans le corps de l'OB » est précisément ce qui fait la sélectivité rentable ; chaque assouplissement testé ajoute des trades perdants. Écart live/backtest par ailleurs mesuré : fenêtres d'analyse 300/300/300 (live) vs 100/150/200 (backtest) → −21 % de trades seulement (52 vs 66), pas la cause d'un blocage total ; le filtre news (pauses 1 h autour des annonces USD pendant les sessions) enlève le reste.
**Écarté :** (1) moteur « tap » — grosse perte, DD ruineux. (2) Désactiver premium/discount — divise le PF par 1,2 et double le DD pour 45 % de trades en plus. (3) Passage en intraday — perdant sur la période. Scripts et résultats : `backend/_compare_entry_options.py`, `_entry_windows_test.py`, `_entry_cmp_*.json`.

## 2026-07-09 — Audit complet : clé API sur l'API publique + correctifs
**Décision :** audit critique après le déplacement du projet. Correctifs livrés en un lot :
(1) **Clé API** — l'API Render était publique SANS auth : n'importe qui pouvait stopper le bot, fermer les positions, changer les réglages (risque, mode réel, token MetaApi). Si l'env `API_KEY` est définie, tout `/api` (sauf `/` et `/health`) exige le header `X-API-Key` ; clé saisie par appareil (Réglages → Serveur). `API_KEY` absente = auth désactivée (déployable avant de créer la clé, pas de casse).
(2) **CORS** — `allow_credentials=True` avec origine `*` (Starlette reflète alors l'origine appelante = credentials ouverts à tous) → credentials seulement si origines explicites.
(3) **PUT /settings** — liste blanche des clés (avant : n'importe quelle clé injectable dans Mongo).
(4) **Toggles notifications** — les interrupteurs `notif_*` des Réglages n'étaient vérifiés nulle part (aucun effet) → vérifiés dans `store.add_notification`.
(5) **Backtest** — 1 seul à la fois (409 sinon) + cession de l'event loop toutes les 25 bougies : un backtest affamait la boucle live et déclenchait le gardien.
(6) **bot_loop.stop_watchdog** — `global _resume_task` manquant : l'auto-reprise n'était jamais annulée (variable locale morte).
(7) Journal des rejets : direction = biais HTF réel (avant : « buy » codé en dur). (8) `require_premium_discount` ajouté aux réglages (backtest le lisait, le live non → incohérence potentielle). (9) `.gitattributes` (fin du bruit CRLF Windows : 95 fichiers « modifiés » fantômes), `.gitignore` élargi à `backend/_*`. (10) Docs remises en phase avec le code (trailing stop implémenté OFF par défaut — les commentaires « le live ne l'applique jamais » étaient FAUX ; prop firm = BlueGuardian, pas FTMO).
**Pourquoi :** le n°1 est une faille grave sur un bot qui manipule de l'argent réel ; le reste = bugs dormants ou docs mensongères qui auraient fait dériver les prochaines sessions.
**Écarté :** login/comptes multi-utilisateurs (décision « sans login » maintenue — une clé API n'est pas un login) ; suppression du trailing live pour recoller aux docs (c'est la doc qui était périmée, la fonction est utile et OFF par défaut).

## 2026-07-08 — App mobile : Capacitor sur la prod Render existante, URL backend par appareil
**Décision :** l'app Android est le frontend React embarqué dans Capacitor (`frontend/android/`, appId `com.goldflow.smc`), pointée sur la prod **Render existante** (`goldflow-backend.onrender.com`) + MongoDB Atlas — découverts en marche pendant la tâche (le Mongo local du PC était un reliquat figé au 14 juin). APK compilé par GitHub Actions (`.github/workflows/android-apk.yml`, Node 22 requis par Capacitor 8). L'URL du backend est modifiable par appareil (Réglages → Serveur, localStorage), et `CORS_ORIGINS` sur Render inclut `https://localhost` (origine des apps Capacitor).
**Pourquoi :** mêmes données et mêmes fonctions que le web exigées par David → même backend/base ; Render tournait déjà 24/7 avec auto-déploiement GitHub, aucune raison d'introduire un second hébergeur ; l'URL par appareil évite de recompiler l'APK à chaque changement d'environnement.
**Écarté :** (1) Railway — redondant avec la prod Render découverte. (2) Backend sur le PC via IP LAN — inutilisable hors domicile et bot dépendant du PC allumé. (3) Migration du Mongo local vers Atlas — dangereuse, les données locales étaient plus vieilles que celles d'Atlas. (4) React Native/Flutter — réécriture complète interdite par « fonctionnement identique ».

## 2026-07-08 — Gardien de vivacité (watchdog + heartbeat) de la boucle bot
**Décision :** la boucle de trading marque un « pouls » (`_last_heartbeat`) à chaque tour réussi (lecture du compte OK) ; une tâche surveillante indépendante (`_liveness_watchdog`, lancée au démarrage du serveur à côté de l'auto-reprise) relance la boucle — reconnexion MetaApi complète (`metaapi_client.force_reconnect()`) puis `bot_loop.start()` — dès que le pouls dépasse 5 min alors que `running=true`. Notification à David (anti-spam 15 min).
**Pourquoi :** le 2026-07-08, la boucle est restée figée ~2 jours (bot affiché « running » mais idle, `current_day` périmé) : la connexion MetaApi s'était coincée après que le solde MetaApi soit tombé à zéro, et la boucle sautait chaque tour (`continue` sur échec de lecture compte) sans jamais se rétablir. L'auto-reprise au démarrage (commit 2b774b7) ne couvre QUE le redémarrage du serveur — pas une boucle qui meurt ou se bloque sans redémarrage du process.
**Écarté :** (1) auto-reprise au démarrage seule — insuffisante (le cas vécu n'impliquait aucun redémarrage). (2) Watchdog basé sur « la tâche asyncio est-elle vivante ? » — raterait une boucle vivante mais bloquée ; le heartbeat (dernier tour réussi) détecte les DEUX pannes. (3) Seuil court (< 5 min) — écarté car une reconnexion MetaApi à froid peut prendre ~4 min → fausses relances.

## 2026-06 (et avant) — Décisions fondatrices (reprises du CLAUDE.md)

### Connexion via MetaApi uniquement
**Décision :** MT5 via metaapi.cloud (`metaapi_cloud_sdk`), jamais de connexion directe.
**Pourquoi :** app web hébergeable sans terminal MT5 local ; API stable.
**Écarté :** connexion MT5 directe (nécessite Windows + terminal ouvert en permanence) ; données simulées (interdites — mode dégradé explicite à la place).

### SL/TP toujours chez le broker
**Décision :** SL et TP inclus dans l'ordre envoyé, jamais gérés seulement par l'app.
**Pourquoi :** si l'app plante ou perd la connexion, les positions restent protégées.
**Écarté :** gestion logicielle des sorties (un crash = position sans protection).

### Un seul moteur SMC (`backend/smc.py`)
**Décision :** le même code analyse en live et en backtest.
**Pourquoi :** un backtest sur une logique différente du live ne prouve rien.
**Écarté :** moteur de backtest séparé (les deux divergent toujours à terme).

### Magic number obligatoire
**Décision :** le bot ne touche qu'aux positions portant son identifiant.
**Pourquoi :** cohabitation sûre avec des trades manuels sur le même compte.

### TP partiels et trailing stop volontairement absents
> ⚠️ **Partiellement caduc depuis 2026-07** : le trailing stop a finalement été
> implémenté (logique unique live + backtest, OFF par défaut). Seuls les TP
> partiels restent volontairement absents.
**Décision :** non implémentés ; points d'extension prévus.
**Pourquoi :** complexité et risque de bugs > bénéfice tant que la stratégie de base n'est pas validée en signal-only. **Ne pas les ajouter sans décision explicite de David.**

### Mode « Signal uniquement » par défaut
**Décision :** au premier lancement, le bot détecte et journalise sans exécuter.
**Pourquoi :** validation plusieurs jours sur démo avant tout ordre réel — étape obligatoire, pas optionnelle.

### Timeouts MetaApi portés à 240 s (déploiement) / 300 s (axios long)
**Décision :** `deploy()`/`wait_connected()` à 240 s ; instance axios `apiLong` pour `testConnection`, `candles`, `startBacktest`.
**Pourquoi :** le redéploiement d'un compte MetaApi inactif prend 1-2 min ; les 30 s d'origine faisaient échouer la connexion à tort (bug vécu, diagnostic confirmé).

### Graphique lightweight-charts, pas de widget TradingView
**Pourquoi :** contrôle total du rendu des zones SMC ; TradingView ne permet pas de dessiner nos zones custom proprement.

### Sessions strictes Londres/NY via pytz
**Décision :** trading uniquement 8h-11h Londres et 8h-11h NY (`backend/sessions.py`), heure d'été gérée par pytz.
**Écarté :** horaires UTC fixes (cassent deux fois par an aux changements d'heure).
