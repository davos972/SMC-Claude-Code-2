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

## 2026-08-26 — Campagne de backtests sur moteur corrigé : validation hors échantillon obligatoire
**Décision :** toute règle SMC candidate doit battre la référence sur DEUX périodes — la
période d'étude (15 déc. 2025 → 12 juin 2026) ET une période hors échantillon jamais
utilisée pour choisir (12 juin → 26 août 2026, cache téléchargé après coup). Un bon score
sur la seule période d'étude ne vaut rien. Réglages de la campagne (validés par David) :
étages D1→H1→M15→M5, sessions Londres 08:00-17:00 et New York 08:00-17:00 (heures locales),
spread 16 points (Axi), capital = solde réel du compte, risque 1 %, trades/jour illimités,
arrêt à 3 pertes dans la même session, TP partiels actifs, confluences toutes OFF au départ.
**Retenu :** `require_unmitigated_ob = True` + `sl_mode = "protected"` — 243 trades sur
8,5 mois, PF 1,26, DD 8,0 %, t +1,68, au-dessus de la référence sur les DEUX périodes
(1,21 vs 0,97 en étude ; 1,38 vs 1,30 hors échantillon). C'est la Smart Money Trap du
Manuel (§4.1 : ne pas entrer sur un OB déjà mitigé) plus le SL structurel de la Synthèse
(étape 8). **Pas encore appliqué en prod** : t < 2, donc piste sérieuse, pas preuve.
**Écarté — et c'est le résultat important :** `ob_entry_mode = "zone_50"` (entrée sous la
médiane de l'OB) finissait **n°1** de la période d'étude — 176 trades, PF 1,36, puis 1,43
combinée au SL protégé, avec t = +2,06, le seul résultat significatif de la matrice. Hors
échantillon : **PF 0,72**, très en dessous d'une référence à 1,30. Sans le découpage en
deux périodes, cette configuration serait partie en production. Idem pour toutes ses
combinaisons (second CHOCH : 2,54 → 0,35).
**Également écarté :** OTE (PF 0,71, le plus destructeur), inducement pris (0,79), FVG
obligatoire (0,82), Rejection block (0,90), séquence sweep→CHoCH (0,94), retrait du filtre
premium/discount (0,94 — le noyau du document tient). **Power of 3 : question du seuil
tranchée** — testé à 0,20 / 0,35 / 0,50, aucun n'aide (0,93-0,95 contre 0,97 pour la
référence). Ce n'est pas un problème de calibrage, le filtre n'apporte rien sur l'or ;
ses 97,75 % viennent d'indices. **TP partiels vs TP unique** : winrate 49 % contre 32 %,
mais PF identique (0,97 vs 1,00) — ils lissent la courbe, ils n'ajoutent pas d'espérance.
**Non modélisé :** commissions, slippage, exécution partielle, filtre news. Scripts :
`backend/_matrix2.py`, `_oos.py`, `_report2.py` (jetables, convention `_*`).

## 2026-08-26 — La raison d'un signal décrit ce qui s'est vraiment produit
**Décision :** `smc._signal_reason` compose le texte du signal à partir des conditions
RÉELLEMENT constatées : déclencheur (`Sweep→CHoCH` / `CHoCH→Sweep` selon l'ordre réel des
index / `Sweep seul` / `CHoCH seul`), présence ou non d'une FVG non comblée, type de POI
retenu (OB / BPR / Breaker / Mitigation / Rejection, lu dans `poi.zone`) et son état
mitigé ou non, mode d'entrée (`dans` / `tap sur` / `sous la médiane de`), zone
premium/discount déduite du **prix réel** et non du sens du trade, et en suffixe les
confluences vérifiées (`displacement`, `inducement pris`, `2e CHoCH`). `fvg_ok` est donc
calculé même quand `require_fvg_entry` est désactivé. Quand tous les filtres du noyau sont
actifs, le texte produit est **identique au mot près** à l'ancien.
Tests : `backend/tests/test_signal_reason.py` (8 tests unitaires).
**Pourquoi :** le texte était figé (`"Sweep→CHoCH + FVG dans OB {zone}"`) alors que les
filtres sont désactivables et le sont en prod. Mesuré sur un mois réel de XAUUSD avec les
réglages de backtest validés : sur 45 trades, **0** n'avait la séquence sweep→CHoCH,
**aucun** n'avait de FVG, et 9 étaient sur un OB déjà mitigé — tous étiquetés
« Sweep→CHoCH + FVG ». David lit ce journal pour comprendre le bot ; un texte décoratif y
est un mensonge, pas un détail cosmétique.
**Écarté :** (1) ajouter des champs booléens structurés au `Signal` et composer la phrase
côté frontend — plus lourd (migration Mongo, 2 écrans) sans rien apporter à la lecture ;
à reconsidérer le jour où on voudra filtrer les trades par type de déclencheur. (2) Se
contenter du snapshot des réglages déjà stocké dans `trades` — il dit quels filtres
étaient actifs, pas ce qui s'est produit sur CE setup (filtre FVG désactivé, une FVG peut
être présente ou non). (3) Ajouter un champ `kind` à `OrderBlock` pour nommer le type de
POI — inutile, `zone` porte déjà l'information.
**Note :** cette décision avait été prise le 2026-08-25 sur l'ancien `smc.py` ; ces
travaux, non commités, ont été rendus caducs par la réécriture du moteur du même jour.
Réimplémentée ici sur le nouveau moteur, enrichie des nouveaux types de POI et des
confluences.

## 2026-08-26 — Le backtest lisait le futur (anticipation sur les étages HTF/MTF/D1)
**Décision :** les fenêtres d'analyse des étages supérieurs ne sont plus découpées par
`bisect.bisect_right(htf_times, cur_time)` sur les temps de **début** de bougie. Une
bougie supérieure n'est visible que si elle est CLÔTURÉE à la minute de décision, et la
bougie EN FORMATION est reconstruite depuis les bougies du niveau d'entrée déjà écoulées
(`backtest._partial_bar`) — exactement ce que le bot live reçoit du broker. Le calcul
passe par des index (`_dec = (i+1) * ltf_minutes`), l'agrégation étant positionnelle.
Test de non-régression : `backend/tests/test_backtest_lookahead.py` (3 tests ; les 2
premiers ÉCHOUENT sur l'ancien code, vérifié).
**Pourquoi :** `bisect_right` sur les temps de début inclut la bougie en cours, déjà
agrégée avec son high/low/close DÉFINITIFS. Preuve sur données réelles (cache M1 XAUUSD) :
en analysant la bougie M1 de 16:47, la fenêtre HTF contenait la bougie M5 16:45→16:49
terminée, close 4669,95 — le prix de 16:49. En scalping avec `scalping_d1="H1"`, le filtre
Daily Bias voyait jusqu'à 59 minutes d'avenir ; c'était TOUT son avantage apparent.
Mesuré sur 6 mois de XAUUSD M1 (40 configurations rejouées sur 3 moteurs) : Daily Bias
PF 1,52 → 0,80, Power of 3 PF 1,20 → 0,82, meilleure combinaison +47 412 $ → +894 $,
ligne de base PF 0,85 → 0,81. Aucune des 40 configurations n'a d'avantage démontrable
une fois le biais retiré (meilleur PF 1,06, t ≈ 0,5), alors que la perte de la config de
prod, elle, est significative (t = −2,75). Le garde-fou « jamais d'anticipation » existait
déjà dans CLAUDE.md §9 mais ne visait que le journalier : il vaut pour les quatre étages.
**Écarté :** (1) simplement SUPPRIMER la bougie en cours des fenêtres — plus sévère que le
live, qui la voit partielle ; écart mesuré non négligeable (PF base 0,82 vs 0,81) et,
surtout, ce n'est pas ce que fait le bot. (2) Garder `bisect` en visant les temps de FIN de
bougie — équivalent mais dépendant du format des temps (str ISO vs datetime) là où
l'arithmétique d'index est exacte. (3) Ne rien changer et « corriger mentalement » les
résultats : impossible, l'effet va de −2 % à +90 % de P&L selon les filtres.
**Reste à vérifier :** le rejeu `/analysis/at-time` (server.py) demande à MetaApi les
bougies jusqu'à un horodatage ; si l'API renvoie la bougie CONTENANT cet instant, le même
biais existe à l'affichage. Sans effet sur les décisions de trading, à traiter à part.

## 2026-08-25 — Retrait du mode « Signal uniquement »

**Décision :** le mode « Signal uniquement » est SUPPRIMÉ — réglage, branche dans
`bot_loop`, interrupteur dans les Réglages, champ `signal_only_mode` de `/api/health`
et de l'état du bot. Un setup validé part désormais toujours à l'exécution.

**Pourquoi :** David trade sur un compte DÉMO Axi. Sur un compte démo le mode
n'apportait rien — il empêchait simplement de voir le comportement réel du bot, alors
que c'est précisément ce qu'on veut observer avant d'envisager le réel. Décision prise
par David le 2026-08-25.

**Ce qui NE change pas :** le verrou du compte réel est indépendant et reste entier —
`account_type` reste à `demo` par défaut et le passage en réel exige toujours la double
confirmation `real_confirmed`. Le mode signal n'a jamais été ce qui protégeait du réel.

**Écarté :** garder le réglage en le passant simplement à False par défaut. Écarté à la
demande de David : un interrupteur qu'on ne remettra jamais sur ON est du code mort et
une case de plus à lire dans les Réglages. Si le besoin revient (tester une nouvelle
confluence sans polluer le journal), le journal diagnostic `verbose_journal` couvre déjà
la lecture des setups écartés, et le backtest couvre la validation d'une stratégie.

## 2026-08-25 — Alignement du moteur sur le « Manuel de détection SMC » et la « Synthèse stratégie V3 »

David a fourni deux documents (manuel de détection des indicateurs + synthèse de la
playlist SMC/ICT de Jérémy Delsol). Comparaison ligne à ligne avec `backend/smc.py`,
puis 15 arbitrages tranchés par David (B1–B6, D1–D9). Détail des divergences relevées
avant décision : voir l'historique de la session.

**Ce qui était déjà conforme** : FVG (règle des 3 bougies au caractère près), sweep
(mèche au-delà + réintégration), BOS/CHoCH, OB à l'origine d'une cassure,
premium/discount, architecture top-down.

**Décisions appliquées** — chaque ancienne méthode reste accessible en réglage, pour
comparer en backtest plutôt que basculer à l'aveugle :

| # | Décision | Ancienne méthode conservée sous |
|---|---|---|
| B1 | Swings par la règle des 2 bougies (+ détection des sommets ÉGAUX, que la fractale stricte manquait) | `swing_method="fractal"` |
| B2 | Order block tracé mèches comprises (high→low) | `ob_zone="body"` |
| B3/D7 | Compteur de touchés exposé, rejet désactivable | `max_ob_touches=0` (OFF) |
| B4 | TP sur la borne opposée du dealing range | `tp_target="nearest_swing"` |
| B5 | Cassure sur clôture ou sur mèche, au choix | `structure_break_mode` |
| B6 | Mode d'entrée « au-delà des 50% de l'OB » | `ob_entry_mode="zone_50"` |
| D1 | 4e étage journalier au-dessus du biais | `intraday_d1=""` (désactivé) |
| D2 | Daily Bias PDH/PDL + Power of 3 codés, filtres OFF | — |
| D3 | **TP partiels TP1/TP2/TP3**, activés par défaut | `partial_tp_enabled=False` |
| D4 | Second CHOCH exigible | `require_second_choch=False` |
| D5 | Displacement = « la bougie de cassure laisse une FVG » | `require_displacement=False` |
| D6 | Range asiatique + PDH/PDL comme niveaux de liquidité | OFF par défaut |
| D8 | Biais du scalping monté à H1 | l'étage M15 est conservé |
| D9 | Ordre d'implémentation revu selon le classement §10 de la Synthèse | — |

### Deux règles verrouillées levées

**TP partiels (D3).** Claude.md §4 disait « TP partiels : NON implémentés
volontairement ». La Synthèse V3 §Étape 9 en fait le cœur de la gestion de position.
David a tranché pour l'implémentation. Le SL et le TP FINAL restent posés CHEZ LE
BROKER — la règle « SL/TP toujours chez le broker » n'est pas touchée : seules les
prises intermédiaires sont pilotées par le bot, et si l'app s'arrête la position reste
protégée comme avant. **Activés par défaut** à la demande explicite de David
(2026-08-25) : c'est la gestion de position que décrit la stratégie, pas une option
parmi d'autres. Conséquence mesurée sur données synthétiques : le profit factor passe
de 10,46 à 4,59, le runner étant écrêté par les prises. C'est l'arbitrage attendu
(plus de gagnants, gain moyen plus faible) et il est assumé. Réglage par défaut :
TP1 à 1R ferme 50% et remonte le SL au break-even, TP2 ferme 30%, les 20% restants
courent jusqu'à la cible. `partial_tp_enabled=False` rétablit le TP unique pour
comparer en backtest.

**Biais du scalping (D8).** Nos backtests disaient `scalping_htf=M15` validé et H1
perdant avec un drawdown catastrophique ; la Synthèse V3 §7 considère à l'inverse
qu'un biais pris trop bas est « l'erreur n°1 ». Contradiction signalée à David, qui a
tranché pour monter le biais. Résolue sans sacrifier le backtest : le 4e étage permet
d'AJOUTER H1 au-dessus plutôt que de REMPLACER M15. Scalping = H1 → M15 → M5 → M1.

### Alternatives écartées

- **Activer les nouveaux filtres par défaut** : écarté. La Synthèse V3 §10 est
  explicite — « noyau + 1 à 3 confluences + confirmation », et l'empilement de tous les
  concepts « ne se produit quasiment jamais et paralyse l'exécution ». Tout ce qui est
  ajouté est donc détecté et affiché, mais désactivé comme filtre.
- **Ordre d'implémentation initial** (IFVG → BPR → Rejection → OTE) : écarté après
  lecture du §10, qui classe IFVG, Rejection et OTE en simples « variantes » et met en
  avant l'inducement, le range asiatique, le second CHOCH et les niveaux protégés.
  Le seul élément du NOYAU qui manquait au moteur était la liquidité BSL/SSL — traitée
  en premier.
- **OB 2.0 et SMT Divergence** : non implémentés. Le premier impose un 5e étage de
  timeframe, le second impose de suivre en continu un second instrument corrélé, ce qui
  casserait l'architecture mono-symbole. La Synthèse les classe elle-même en dernier.
- **Range asiatique activé par défaut** : écarté. Le manuel §6.1 le donne pertinent
  « surtout sur paires européennes, peu volatiles la nuit » — l'or bouge la nuit.

### Pièges rencontrés et corrigés

- **Agrégation journalière du backtest** : `_aggregate` regroupe par NOMBRE de bougies.
  Correct en H1, faux en journalier (l'or fait ~1380 bougies M1 par jour, pas 1440) —
  les « journées » auraient dérivé et le PDH/PDL n'aurait correspondu à aucune séance.
  Ajout de `_aggregate_daily`, par date calendaire.
- **Anticipation sur la bougie du jour** : pré-agréger la journée en cours donnerait au
  bot le high et le low de fin de journée dès le matin. La bougie du jour est
  reconstruite au fil de l'eau depuis les bougies déjà écoulées. Vérifié par test.
- **Double prise partielle après un redémarrage** : le suivi mémoire repart vide, TP1
  aurait été repris et aurait refermé une seconde fois la même part du volume. Les
  prises déjà encaissées sont relues du journal et marquées faites.
- **Quatre appels à `analyze()` maintenus à la main** (bot, backtest, dashboard, rejeu) :
  les deux de `server.py` avaient été oubliés, le graphique aurait affiché des zones
  tracées avec d'autres réglages que ceux décidant des trades. Conversion réglages →
  paramètres centralisée dans `smc.params_from_settings`.

## 2026-08-19 — Journal de trading : les trades réels enfin persistés (collection `trades`)
**Décision :** création d'une collection MongoDB `trades` qui garde chaque trade RÉEL
du bot de son ouverture à sa clôture (`store.add_trade/close_trade/update_trade`).
`bot_loop` y écrit à l'ouverture (RR prévu, entrée/SL/TP, session, timeframe, et un
**instantané des réglages actifs** — 20 clés) et à la clôture (P&L réel lu chez le
broker, prix/heure de sortie, TP vs SL vs SL suiveur déduit du prix de sortie). La
page **Stats devient le Journal de trading** (P&L global, nb de trades, winrate,
profit factor, drawdown max, courbe d'évolution vs capital de départ, détail de
chaque trade). Les métriques réutilisent `backtest._compute_metrics` : une seule
définition de winrate / profit factor / drawdown dans toute l'app. Un bouton
**« Importer l'historique du broker »** (`POST /api/journal/import`) reconstruit les
trades passés depuis l'historique des transactions MetaApi (filtré sur le magic
number, jamais les trades manuels), en retrouvant le RR prévu via le journal des
signaux quand un signal exécuté correspond (±15 min).
**Pourquoi :** avant, un trade fermé servait uniquement à incrémenter le compteur de
pertes consécutives, puis était **oublié** — aucun historique n'existait, et la
« courbe d'équité » de la page Stats était une estimation à partir des signaux, sans
aucun P&L réel. Impossible pour David de savoir ce que le bot avait accompli.
Au passage, la reprise du suivi après redémarrage (`_restore_open_trades`) corrige un
trou réel : `_open_positions` étant en mémoire seule, un redémarrage du serveur avec
une position ouverte faisait perdre la détection de sa clôture (donc le comptage de
la perte).
**Écarté :** (1) recalculer le journal à la volée depuis MetaApi à chaque affichage —
lent, dépendant de la connexion, et incapable de restituer les réglages de l'époque.
(2) Déduire les trades du journal des signaux — un signal « exécuté » ne dit ni le
P&L réel ni la sortie réelle. (3) Inventer un P&L quand l'historique broker est
indisponible : le trade est marqué `result: "unknown"`, **sans P&L**, et exclu des
statistiques (jamais compté comme un gain). (4) 5e onglet dédié — David a choisi de
remplacer le contenu de la page Stats en gardant le nom de l'onglet.

## 2026-08-10 — Pertes consécutives comptées PAR SESSION
**Décision :** l'arrêt auto après N pertes consécutives (défaut 3) ne compte plus que les pertes d'une MÊME session : le compteur est remis à 0 au début de chaque nouvelle session (clé `jour|session`). Implémenté en miroir dans le live (`bot_loop`, nouveau champ `consec_session` dans `bot_state`) et le backtest (`run_backtest`, `rm["session"]`). Une perte encaissée HORS session (SL touché après la fermeture) compte pour la session en cours et est soldée au début de la suivante.
**Pourquoi :** demande de David — avant, 2 pertes à Londres + 1 perte à New York stoppaient le bot, alors que chaque session repart sur un contexte de marché neuf. Preuve par scénario synthétique (pertes forcées 2 Londres + 3 NY, analyse monkeypatchée) : avant = arrêt à la 1re perte NY (3 trades) ; après = les 3 signaux NY passent (5 trades) et un 4e signal NY après 3 pertes NY reste bien bloqué. 25/25 tests d'intégration OK.
**Écarté :** (1) reset au changement de jour seulement — ne répond pas à la demande (le cumul Londres→NY persiste) ; (2) rattacher une perte hors session à la session où le trade a été OUVERT — suivi plus complexe pour le même effet pratique, puisque l'arrêt n'est de toute façon évalué qu'en session.

## 2026-07-30 — Filtre news tolérant aux pannes + fenêtres d'analyse live = backtest
**Décision :** enquête sur « 4 trades en backtest juillet, 0 en live » — 3 causes identifiées (pause news sur flux injoignable le 01-07 ; boucle figée du 02 au 07 avant le gardien ; RR 0,82 vs 1,05 sur le setup du 08-07 à cause des fenêtres d'analyse différentes). Deux correctifs : (1) `news.py` sert le DERNIER calendrier valide si le flux faireconomy est injoignable et que le cache a < 12 h (`_STALE_MAX_S`, réponse `stale: true`) — au-delà ou sans cache, blocage prudent inchangé ; en juillet le flux a eu 120 micro-coupures qui bloquaient les entrées en pleine session. (2) Les fenêtres d'analyse deviennent des constantes exportées par `backtest.py` (`WINDOW_HTF=100, WINDOW_MTF=150, WINDOW_LTF=201`) et le live (`bot_loop`) + les endpoints `/analysis/run` (branche 3 niveaux) et `/analysis/at-time` analysent EXACTEMENT ces fenêtres au lieu de 300/300/300 — le backtest validé est la référence. La branche mono-timeframe de `/analysis/run` (zones du graphique) garde ses 300 bougies : c'est de l'affichage, les tronquer ferait disparaître les zones anciennes.
**Pourquoi :** un calendrier hebdo publié à l'avance reste exact des heures — bloquer le trading à chaque hoquet HTTP coûtait des trades validés ; et 300 vs 100-200 bougies changent la structure détectée (~20 % de trades en moins, RR différents sur les setups limites).
**Écarté :** (1) supprimer le filtre news — non, la protection reste, seule la sensibilité aux pannes du FLUX change ; (2) seuil 12 h paramétrable dans Réglages — inutile pour un choix technique stable, constante commentée ; (3) aligner aussi la bougie en formation (le live analyse la bougie courante naissante, le backtest la bougie close) — écart réel mais changer la sémantique d'entrée du live est un chantier séparé, non traité ici.
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
