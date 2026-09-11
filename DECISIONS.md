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

## 2026-09-11 — La boucle ne se figeait pas : le gardien la tuait
**Décision :** séparer les deux pouls du bot, interdire au gardien de relancer la boucle
pour une panne du broker, et ramener les délais de reconnexion MetaApi de 240 s à 60 s
par étape. Demandé par David après le constat de 132 relances automatiques depuis juillet.

**Le diagnostic renverse la question posée.** On cherchait pourquoi « la boucle se fige ».
Elle ne se figeait pas : **le gardien tuait une boucle vivante**. Trois faits, tous
vérifiables dans le code, sans les logs Render :

1. **Le pouls mesurait la mauvaise chose.** `_last_heartbeat` n'était mis à jour qu'après
   une lecture MetaApi RÉUSSIE. Quand le broker ne répondait pas, la boucle tournait très
   bien — elle réessayait toutes les 30 s — mais son pouls ne battait plus. Le gardien
   concluait « boucle figée ».
2. **Le seuil était incohérent avec les délais en aval.** `_connect()` enchaîne cinq
   `wait_for` (get_account, deploy, wait_connected, connect, wait_synchronized) qui étaient
   **à 240 s chacun : jusqu'à 20 MINUTES**. Le gardien frappait à **5**. Le commentaire du
   code affirmait « reconnexion à froid ~4 min → pas de fausse alerte » — faux d'un
   facteur 4 à 5.
3. **D'où un cercle vicieux.** Reconnexion > 5 min → le gardien tue la boucle EN PLEINE
   reconnexion → elle repart de zéro → retuée 5 min plus tard, indéfiniment.

**La preuve est dans la forme des données, pas seulement dans le code.** Les relances ne
sont pas dispersées : elles tombent à **exactement 15 minutes d'intervalle**, en séries.
15 min = `_WATCHDOG_NOTIFY_GAP_S`, l'anti-spam des notifications. Le bot tournait donc en
rond **toutes les minutes** (l'intervalle réel du gardien) et David n'en voyait qu'une
alerte sur quinze. Les **48 relances du 2026-07-12 ne sont pas 48 incidents : c'est une
seule panne de ~12 h**. Mesuré le 2026-09-11 : une reconnexion saine prend **4,6 s** — le
problème n'apparaissait que quand MetaApi avait un hoquet, c'est-à-dire précisément quand
le gardien aggravait au lieu d'aider.

**Le correctif, en quatre points :**
1. **Deux pouls distincts.** `_last_loop_beat` (battu en HAUT du tour, avant tout appel
   réseau) prouve que la boucle vit ; `_last_metaapi_ok` dit que le broker répond. Le
   gardien ne relance que sur le premier.
2. **Aucune relance pendant une reconnexion en cours** — `metaapi_client.is_connecting()`
   expose l'état du verrou de connexion. C'est ce point qui casse le cercle vicieux.
3. **Délais de connexion 240 s → 60 s par étape.** Pire cas : 1 200 s → **300 s**, sous le
   seuil du gardien. Une connexion qui n'aboutit pas doit échouer VITE et être retentée au
   tour suivant, pas bloquer 20 minutes.
4. **Alerte honnête** : nouvelle catégorie `metaapi_down` — « MetaApi injoignable depuis
   N min », sans relance. Sans ça, le prochain qui regarde referait le même faux diagnostic.

**Seuils recalculés, et non devinés :** `_WATCHDOG_STALE_S` passe de 300 à **600 s**, parce
que le pire tour NORMAL (4 téléchargements de bougies à 90 s + lectures de compte + ordre)
vaut ~470 s. À 300 s, le gardien tuait aussi des boucles simplement lentes.
`_METAAPI_STALE_S` reste à 300 s : l'alerte broker arrive AVANT le seuil de relance, pour
qu'on voie la cause plutôt qu'une relance mystérieuse.

⚠️ **Risque corrigé au passage, plus grave que les alertes** : le gardien `cancel()` la
boucle. Le pouls datait d'AVANT les quatre `get_candles` (90 s chacun), donc un tour lent
pouvait dépasser 300 s **pendant un `place_order`**. L'ordre partait chez le broker, et le
code qui écrit la ligne de journal ne s'exécutait jamais. `_restore_open_trades` rattrapait
au redémarrage, mais la fenêtre est désormais fermée.

**Figé par 8 tests** (`backend/tests/test_watchdog.py`), dont deux vérifient la COHÉRENCE
DES SEUILS — ils cassent si quelqu'un rallonge les délais de connexion ou raccourcit le
seuil du gardien. Les tests ont été validés en réintroduisant volontairement chacun des
deux bugs : ils échouent bien.

**Écarté :** (1) **Relever seulement le seuil du gardien** : masque le symptôme, laisse le
pouls mesurer la mauvaise chose, et n'empêche pas la relance inutile pendant une panne
broker. (2) **Supprimer le gardien** : il a une vraie utilité — la boucle figée ~2 jours du
2026-07-08 est ce qui l'a fait naître. (3) **Raccourcir les délais sans toucher au pouls** :
réduit la fenêtre du cercle vicieux sans la fermer. (4) **Rafraîchir le pouls pendant les
appels MetaApi longs** : plus fidèle, mais il faudrait instrumenter le client à chaque
étape — le point 2 (`is_connecting`) obtient le même résultat en trois lignes.

## 2026-09-10 — Le journal de trading archive le graphique et les conditions de chaque trade
**Décision :** chaque trade pris par le bot enregistre désormais, en plus de son résultat,
**(a)** les conditions SMC validées sous forme structurée et **(b)** un instantané du
graphique — les 201 bougies d'entrée ET les zones que le moteur a réellement calculées.
L'onglet Stats les affiche dans le détail dépliable du trade. Demande de David, qui veut
« voir le graphique et toutes les conditions acceptées » en relisant son journal.

**Pourquoi ces deux ajouts et pas seulement le texte existant.** Le champ `reason`
(`_signal_reason`) résume la décision en une phrase, mais il ne dit pas **quels filtres
étaient EXIGÉS** et lesquels étaient seulement **constatés**. Sans cette distinction, on
lit « displacement · 2e CHoCH » et on croit que ces confluences filtraient, alors qu'elles
sont OFF : elles étaient simplement vraies ce jour-là. Le bloc `conditions` porte
maintenant `exige: true/false` sur chaque ligne, et l'écran affiche l'étiquette
**exigée / constatée**.

**Le graphique est REJOUÉ, pas photographié** (choix de David après présentation des deux
options). On stocke bougies + zones, et le composant `SMCChart` existant les redessine :
zoomable, avec les calques, ~66 Ko par trade (mesuré). Une vraie image PNG aurait imposé
un moteur de navigateur sur Render — lourd, fragile au redémarrage, et non zoomable.

**Un piège évité au passage — la liste du journal serait devenue inutilisable.**
`store.list_trades` renvoyait le document entier : à 66 Ko par trade et 500 trades, la
réponse de `GET /api/journal` aurait atteint **plusieurs dizaines de Mo**, sur mobile en
4G. L'instantané est donc **exclu de la liste** (projection Mongo) et chargé trade par
trade par `GET /api/journal/{id}/chart`. Mesuré après coup : 2 Ko par trade dans la liste
au lieu de 68.

**Le moteur n'a été touché que pour SORTIR de l'information.** `_build_signal` remplit
`ctx_out["conditions"]` juste avant de renvoyer le signal — le mécanisme `ctx_out` existait
déjà pour l'inducement. **Aucune branche de décision modifiée** ; les 25 tests unitaires
passent à l'identique. Le repère `db61adb` (dernier changement de comportement du moteur)
reste valable : les décisions de trading n'ont pas bougé.

**Les 5 trades déjà en base ont été reconstitués — et la reconstitution a été VÉRIFIÉE.**
David a demandé de traiter aussi l'historique malgré la réserve annoncée (le live analyse
des bougies supérieures en formation, à la seconde près, qu'un rejeu ne reproduit pas).
Le contrôle mis en place compare la phrase `reason` rejouée à celle enregistrée, caractère
par caractère : **les 5 sont identiques**, RR compris. L'instantané porte donc
`source: "reconstitue_verifie"` et l'écran le dit sans alarmer. Si un rejeu divergeait, il
serait marqué `"reconstitue"` et l'écran afficherait un avertissement rouge avec la phrase
obtenue — on ne présente jamais des zones recalculées comme celles qui ont décidé (§9).

🔑 **Ce qui a rendu la reconstitution fidèle, et qu'il faut retenir** : la première version
sortait des RR faux (1,75 → **2,21** sur le trade du 08/09). Cause : le bot décide à
07:00:23 sur une bougie M1 **en formation**, alors que le rejeu prenait la bougie close.
Or `_build_signal` pose `entry = last_close` — le **prix d'entrée enregistré EST donc,
exactement, le dernier close vu par le moteur**. En forçant le close de la dernière bougie
à `trade["entry"]`, les 5 rejeux sont devenus identiques. Toute reconstitution future d'une
décision live doit faire ça.

**Écarté :** (1) **L'image PNG** — moteur de navigateur côté serveur, cf. ci-dessus.
(2) **Stocker l'instantané dans la liste du journal** — réponse API ingérable.
(3) **Archiver aussi les setups REJETÉS** : ce serait le plus intéressant pour comprendre
le bot, mais la collection `signals` est purgée chaque jour (décision du 2026-09-08) et
un rejet ne crée pas de document `trades`. Traité séparément — voir le chantier ouvert.
(4) **Afficher les lignes « Biais journalier / Power of 3 / OTE » quand ces filtres sont
OFF** : le moteur ne mesure rien à leur sujet dans ce cas, afficher « — constatée » aurait
été trompeur. Ces lignes n'apparaissent que si le filtre a réellement filtré.

## 2026-09-08 (fin) — Mode prop firm activé, risque ramené de 1 % à 0,4 %
**Décision :** `prop_firm_enabled` passe à **True** (activé par David lui-même dans l'app)
et `risk_per_trade_pct` de **1 % à 0,4 %** (écrit par Claude, bot à l'arrêt, accord
explicite). Le bot a été redémarré par David à 08:09 UTC et tourne depuis en mode prop.

**Pourquoi 0,4 % et pas 1 % : à 1 %, la stratégie perd le compte.** Rejeu des 575 trades
sur 50 000 $ avec les vraies limites, par `backend/_prop_replay.py` — **aucun backtest
relancé**, on rejoue la courbe d'équité trade par trade parce que le moteur de backtest ne
modélise pas les règles prop (elles vivent dans `bot_loop.py`, côté live).

| Scénario | Compte perdu | Survie | Pic avant la perte |
|---|---|---|---|
| Mode prop OFF, risque 1 % | 18/07/2025 | **16 jours** | +3,2 % |
| Mode prop ON, risque 0,8 % | 22/10/2025 | **3,7 mois** | +7,2 % (+3 584 $) |

**La cause est structurelle, pas un défaut de réglage** : le drawdown mesuré de la
stratégie est de **11,9 %** quand la limite prop est de **6 %** — le double. Aucun arrêt
préventif ne corrige ça ; le mode prop retarde la perte, il ne l'évite pas. Il y a bien eu
du profit avant la perte, intégralement rendu.

**Balayage du risque — le seul levier qui marche :**

| Risque | Verdict | Coussin minimal | Gain sur 14 mois |
|---|---|---|---|
| 1,0 / 0,8 / 0,65 % | **perdu** (16 j / 112 j / 414 j) | — | — |
| 0,6 % | conservé | **356 $ (0,7 %)** | +39,9 % |
| **0,4 % (retenu)** | conservé | **909 $ (1,8 %)** | **+25,1 %** |
| 0,3 % | conservé | 1 444 $ (2,9 %) | +18,4 % |

**Pourquoi 0,4 % plutôt que 0,6 %, qui rapporte plus.** À 0,6 % le compte survit en passant
à **356 $ du couperet**, soit 0,7 % du capital : ce n'est pas de la survie, c'est de la
chance — une séquence légèrement différente le tuait. 0,4 % double le coussin pour un tiers
de rendement en moins. **Choix de David après présentation des deux.**

🚨 **Piège de lecture à retenir : le COUSSIN MINIMAL, pas le drawdown.** Des comptes
survivent à 10,7 % de drawdown alors que la limite affichée est 6 %. La raison : une fois
le plancher **verrouillé au capital initial** (dès que le high watermark atteint +6 %), la
contrainte n'est plus « ne pas perdre 6 % depuis le pic » mais **« ne jamais repasser sous
50 000 $ »**. C'est exactement ce qui a tué le scénario B : pic à 53 584 $, puis repli à
49 936 $ — **64 $ sous le solde initial**, après trois mois de profit.

⚠️ **Réserve capitale : c'est UNE seule séquence historique.** Tenir ces 14 mois à 0,4 % ne
dit pas qu'on tiendrait les 14 prochains. Les limites prop sont **absolues et
définitives** ; le drawdown, lui, est aléatoire. C'est précisément pourquoi on prend de la
marge au lieu de viser la frontière. Réserve de méthode : la séquence de trades est celle
produite avec les garde-fous standard, les arrêts prop ajoutés par-dessus (ils ne peuvent
que retirer des trades).

**Vérifié en production le 2026-09-10** (2 jours après) : 3 trades réels, pertes à
**−209,79 $ et −209,82 $** = 0,42 % du capital → **le risque de 0,4 % est bien appliqué**.
Coussin face au plancher : **2 580 $ (5,2 %)**. Collection `signals` à 0 → la purge
quotidienne fonctionne. `day_start_ref` correct → le correctif `new_day_state` tient.

**Écarté :** (1) **0,6 %** malgré son +39,9 % — coussin de 0,7 %, trop mince. (2) **Garder
1 %** : mesuré perdant sur le compte. (3) **Toucher à la stratégie** pour réduire son
drawdown : rien dans la campagne ne permet de le faire sans dégrader l'espérance ; le
risque par trade est le levier propre. (4) **Modéliser les règles prop dans
`backtest.py`** : elles sont une contrainte de compte, pas une décision de trading — les
mettre dans le moteur mélangerait deux responsabilités. Le rejeu par `_prop_replay.py`
répond à la question sans toucher au moteur.

## 2026-09-08 (suite) — Nouveau compte 50 000 $ et règle de cohérence prop firm
**Décision :** le compte démo Axi (~4 900 $) est remplacé par un **compte à 50 000 $**.
Journal de trading remis à zéro, collection `signals` vidée, limites prop firm corrigées,
et la **règle de cohérence est implémentée — en surveillance seule, sans jamais arrêter
le bot**. Poussé en production.

**Pourquoi la règle de cohérence n'arrête pas le bot.** C'est le point qui a demandé une
décision explicite de David. Les trois autres règles prop protègent le COMPTE : les violer
le fait perdre. Celle-ci est différente — le meilleur jour doit rester ≤ 20 % du profit
total **au moment du payout** ; la violer ne casse rien, elle **retarde un retrait**.
Arrêter le bot pour la respecter reviendrait à renoncer à du profit réel pour protéger une
date. Elle est donc **calculée, affichée et notifiée**, jamais bloquante.
Second argument, mathématique : au démarrage le cumul vaut 0, donc le premier jour gagnant
pèse **100 %** du total. Une application stricte interdirait le tout premier trade
gagnant. La règle n'est satisfiable qu'après plusieurs jours — c'est normal, et le test
`test_un_seul_jour_gagnant_depasse_forcement` le fige.

**Ce que le bot calcule** (`bot_loop.prop_consistency`, calcul PUR, partagé avec
`GET /api/prop/consistency` — jamais deux versions) : profit par **jour prop** (reset 17h
EST, pas jour calendaire), meilleur jour, ratio, et surtout **combien de profit il manque
ailleurs pour redevenir conforme** (`total_requis = meilleur_jour × 100 / limite`). La
notification ne part qu'au **changement de situation** (signature « date du meilleur jour
+ ratio » mémorisée dans `bot_state`) : sans ça, chaque clôture de trade renverrait la
même alerte pendant des jours. Un P&L inconnu est **exclu**, jamais estimé (§9).

**Deux champs morts découverts en lisant le code — ne pas s'y fier :**
`prop_profit_target_pct` et `prop_consistency_pct` n'étaient lus **par aucun code
backend** (0 occurrence hors `models.py` et le JSX). Le second l'est désormais ; le
premier reste mort et le restera — un compte **Instant Funding n'a pas d'objectif de
profit**. Troisième champ mort du projet après `settings.bot_running` et la colonne PROD
du §0bis : **la doc et l'interface ne prouvent jamais qu'un réglage est branché.**

**Corrections de réglages appliquées** (bot à l'arrêt, accord explicite de David,
anciennes valeurs dans `_settings_backup_2026-09-08_prop.json`) :

| Réglage | Atlas | Corrigé | Remarque |
|---|---|---|---|
| `prop_daily_dd_pct` | 5 | **3** | Atlas avait dérivé ; `models.py:179` disait déjà 3 |
| `prop_total_dd_pct` | 10 | **6** | idem, `models.py:180` |
| `prop_initial_balance` | 10 000 | **50 000** | sinon toutes les limites 5× trop serrées |

**Piège évité au changement de compte, à retenir.** `bot_state` gardait
`day_start_equity = 4 858,87 $` — l'équité de l'ANCIEN compte — **avec la date du jour
déjà inscrite**. Le rollover de `bot_loop.py:585` ne se déclenche qu'au changement de
jour : il n'aurait donc PAS recalculé la référence. Le coupe-circuit de drawdown aurait
comparé l'équité du nouveau compte à l'ancien solde et, le nouveau compte étant plus gros,
c'était sans conséquence ici — **mais avec un compte plus petit, le bot se serait arrêté
seul dès le premier tour**. Corrigé en vidant `current_day`, ce qui force le recalcul
depuis le compte réel **sans inscrire aucun montant**. À refaire à chaque changement de
compte.

**Vérifié, pas supposé :** **21 tests passent** (11 existants + 10 nouveaux dans
`backend/tests/test_prop_consistency.py`), dont le regroupement par jour prop — deux
trades à des dates calendaires différentes (8 sept. 21:30 UTC et 9 sept. 16:00 UTC)
tombent bien dans le **même** jour prop, et dans deux jours distincts hors mode prop.
`server.py` importe et expose `/api/prop/consistency`. Écritures Atlas relues après coup.

**Ajouts du même jour, après le redémarrage du bot par David.**

**(a) Purge quotidienne des signaux — demandée et faite.** La collection `signals` est
vidée à chaque nouveau jour de trading, dans le rollover de `bot_loop`. Elle ne sert qu'à
comprendre la journée en cours et gonflait sans limite (4 515 documents). **Les `trades`
ne sont jamais purgés** : c'est le journal de performance.

**(b) Bug trouvé en vérifiant l'état après le redémarrage — la protection journalière
prop était inopérante.** Après le changement de compte, Atlas montrait
`day_start_equity = 50 000 $` mais **`day_start_ref = 4 858,87 $`**, l'équité de l'ancien
compte. Cause : **trois endroits écrivaient les repères du jour, chacun à sa façon.**
`/bot/start` (`server.py:352`) et `/bot/resume` mettaient à jour `day_start_equity` mais
**oubliaient `day_start_ref` et `prop_hwm_balance`** — et fixaient `current_day` au jour
**calendaire** au lieu du jour prop, ce qui empêchait ensuite le rollover de la boucle de
corriger quoi que ce soit. `day_start_ref` étant LE repère de la perte journalière en mode
prop (`bot_loop.py:698`), la protection aurait été **inopérante toute la journée** dès
l'activation du mode prop.

Corrigé par **une source unique**, `bot_loop.new_day_state`, appelée par les trois
endroits — la duplication était la cause, pas le symptôme. Figé par 4 tests, dont celui
qui vérifie que `current_day` suit le jour prop (21:30 UTC = 17:30 à New York = jour
suivant) et non le calendaire. **25 tests au total.**

⚠️ **Sans effet en production aujourd'hui** : `prop_firm_enabled` est à `False`, donc
`day_start_ref` n'est pas lu. La valeur périmée reste en base jusqu'au prochain rollover
quotidien, qui la corrigera seul. À savoir avant d'activer le mode prop.

**Écarté :** (1) **Arrêter le bot sur la règle de cohérence** — voir ci-dessus ; l'option
« arrêt » a été proposée à David, il a choisi la surveillance. (2) **Activer
`prop_firm_enabled`** : décision séparée, non prise. (3) **Toucher au frontend** pour
afficher le ratio de cohérence : l'endpoint existe, l'affichage viendra si David le
demande. (4) **Écrire `day_start_ref` à la main dans Atlas** pour corriger tout de suite :
le bot tourne, et la valeur se corrigera d'elle-même au prochain rollover — écrire sous
une boucle en vol pour un champ inutilisé aujourd'hui n'en vaut pas le risque.

## 2026-09-08 — Plusieurs positions simultanées : un levier, pas un avantage
**Décision :** le moteur de backtest sait désormais tenir N positions simultanées
(`backtest.py`), **plafonné par le drawdown maximum** — avec 1 % par trade et 3 % de DD,
la borne est 3, appliquée par le code (`max_positions_allowed`) et non par la prudence du
réglage. **Le bot live n'a PAS été touché** (choix de David) : `bot_loop.py` et `models.py`
sont inchangés, le comportement en production est strictement identique. Les défauts
(`max_concurrent_positions=1`, `max_concurrent_per_side=0`, `consec_loss_grouping="each"`)
reproduisent exactement l'ancien moteur. **Rien n'est déployé.**

**Pourquoi cette campagne :** question de David — « que se passerait-il si le bot pouvait
ouvrir plusieurs trades à la fois, sans jamais risquer plus que le drawdown maximum ? »
Contrairement à la question sur les TP, elle **ne pouvait pas** se répondre sur les fichiers
existants : `backtest.py:328` faisait `if open_trade: continue`, donc le moteur n'analysait
même pas le marché pendant qu'une position était ouverte — les signaux manqués n'existaient
nulle part. 24 runs (4 variantes × 2 entrées × 3 périodes).

**Résultat principal : l'avantage PAR TRADE ne change pas.** Mesuré en multiples de R,
et c'est le point de méthode le plus important de la journée :

| Entrée | Référence | `multi3` | `multi3-batch` |
|---|---|---|---|
| M1 (prod) | +0,098 R | +0,100 (t **+0,04**) | +0,108 (t **+0,19**) |
| M5 | +0,078 R | +0,054 (t **−0,38**) | +0,064 (t **−0,23**) |

Aucun écart significatif, dans aucun sens, sur aucune timeframe. **Ce qui change, c'est le
volume et le risque, dans le même rapport** : en M1, +114 % à +152 % de trades, R total
× 2,2 à × 2,8, et **drawdown × 2,0 à × 2,4** (11,9 % → 24,3 % / 28,7 %). Le rendement
rapporté au risque (R total / pire DD) passe de 4,75 à 5,07 / 5,46 en M1 et de 2,88 à
1,93 / 2,96 en M5 — **les deux timeframes ne s'accordent même pas sur le signe.**

🚨 **Piège majeur évité, à retenir : les P&L en dollars sont trompeurs quand le nombre de
trades change beaucoup.** `multi3-batch` affiche **+10 694 $** contre +3 148 $ — soit
+240 %, un chiffre spectaculaire qui aurait pu emporter la décision. Mais les lots sont
dimensionnés sur l'équité courante : plus le compte grossit, plus chaque trade pèse. Une
partie de ce +240 % est de la **capitalisation**, pas de l'avantage. En R, l'écart par
trade tombe à +0,010 (t +0,19). **Toute comparaison entre variantes de volumes différents
doit se faire en R.** Ce piège n'existait pas jusqu'ici parce que toutes les variantes de
la campagne avaient des volumes comparables.

✅ **Une question tranchée définitivement : « au plus une position par sens » ne fait
RIEN.** 588 trades contre 576 en M1 (+2 %), 452 contre 447 en M5 (+1 %) — et des P&L à
0,2 % près. C'est la conséquence directe des **96 % de trades rapprochés de même sens**
mesurés la veille : les occasions manquées sont presque toutes dans la direction déjà
prise, donc interdire le doublon de sens les bloque toutes. Ce n'était pas un compromis
prudent, c'est un non-événement. **`multi3-1side` et `multi3-1side-batch` donnent des
fichiers strictement identiques** sur les 6 combinaisons — la règle « lot = 1 perte » ne
se déclenche jamais, puisqu'il faudrait qu'un achat et une vente perdent dans la même
bougie.

**Ce que la campagne dit vraiment, et qu'il faut dire sans l'habiller :** trois positions
de même sens sur le même instrument se comportent comme **une position de taille triple**.
Le drawdown le confirme (× 2,4). C'est donc **une décision d'appétit au risque, pas un
résultat statistique** — et monter le risque par trade sur une seule position produirait à
peu près le même effet, en bien plus simple à opérer.

⚠️ **Réserve qui compte plus ici qu'ailleurs : les coûts de transaction.** Commissions,
slippage et exécution partielle ne sont pas modélisés. À 2,5 fois plus de trades, ils sont
multipliés par 2,5 **alors que l'avantage par trade est inchangé**. L'avantage réel serait
donc plus faible que le backtest ne le montre, et d'autant plus érodé que le volume monte.
Le filtre news, non modélisé lui aussi, couperait également plus de trades.

**Méthode :** moteur `ef32ba4` + le changement ci-dessus. **Non-régression prouvée avant
tout résultat** : avec les défauts, deux configurations rejouées (M5 `conf-unmitigated` et
M1 `rr-1-unmit` sur `oos`) redonnent les fichiers stockés **trade par trade et champ par
champ**, sur 11 champs — 68 trades / +955,68 $ et 79 trades / +376,39 $. Les 11 tests
unitaires passent. Le plafond dur a été vérifié séparément : réglé à 10 avec 1 % de risque
et 3 % de DD, il autorise 3 ; à 2 % de risque, il tombe à 1.

**Écarté :** (1) **Toucher `bot_loop.py`** — David a demandé le backtest seul tant qu'on ne
sait pas si l'idée tient ; l'écart temporaire avec la règle d'architecture n° 3 est assumé
et à rattraper si la décision est prise. (2) **Ajouter les réglages dans `models.py`** :
inutile tant que le live ne les lit pas, et ça les ferait apparaître dans Atlas sans effet.
(3) **Conclure sur les dollars** : c'était le piège, cf. ci-dessus. (4) **Trancher entre M1
et M5** : ils divergent, aucun écart n'est significatif, il n'y a rien à départager.
(5) **Recommander l'activation** : l'arbitrage rendement/risque appartient à David.

## 2026-09-07 (suite) — « SL à TP1 quand TP2 est touché » : écarté par comptage, pas par statistique
**Décision :** l'idée de David — *quand le prix atteint TP2, remonter le SL au niveau de
TP1* — est **écartée**, et **aucun backtest n'a été lancé**. La gestion de position reste
inchangée : TP1 à 1R ferme 50 % et met le SL à l'entrée, TP2 ferme 30 %, les 20 % restants
courent jusqu'à TP3. Nouvel outil au §8 : `backend/_tp_management.py`.

**Pourquoi : la règle coupe 2 à 3 fois plus de gagnants qu'elle n'en sauve.** Sur les
575 trades de la configuration validée, 196 (34 %) atteignent TP2 et sont donc concernés :

| | Trades | Effet |
|---|---|---|
| Retombaient au break-even → **sauvés** | 33 | **+368 $** |
| Allaient jusqu'à TP3 → **coupés** | **57 à 89** | **−517 $** |
| Ne repassent jamais sous TP1 | 74 | 0 $ |
| **Net** | | **−0,19 à −0,26 $/trade** |

**La cause est mécanique, et c'est le vrai enseignement.** TP2 est placé à **mi-chemin
entre TP1 et TP3** (`compute_tp_ladder`, `backtest.py:442`). Quand le prix atteint TP2,
TP1 est donc encore **à l'intérieur de sa respiration normale** : **55 % des trades qui
finissent par toucher TP3 repassent sous TP1 en chemin** avant de repartir. Y poser le SL
ne sécurise pas un gain, ça fait sortir sur du bruit. **Toute variante de cette idée — un
SL à un palier intermédiaire après une prise partielle — se heurtera au même mur.**

**Le balayage compte autant que le résultat.** Conformément à la règle de robustesse posée
le matin même (§9), le niveau du SL n'a pas été testé à une seule valeur mais aux **onze**
niveaux de 0R (break-even, comportement actuel) à 1R (TP1, la proposition). **Aucun n'est
positif**, et le nombre de gagnants coupés grimpe régulièrement de 1 à 57. Le comportement
actuel est le meilleur des onze. Sans ce balayage, on aurait pu conclure « c'est mauvais à
TP1 mais peut-être bon à mi-chemin » — la réponse est non, à tous les niveaux.

**Ce qui rend le résultat solide alors qu'il n'est PAS significatif.** L'effet vaut
|t| < 0,1, très loin du seuil de 2 — mais **il n'a pas été obtenu par une comparaison de
moyennes**. Les 33 sauvés et les 57-89 coupés sont des **comptages exacts** obtenus en
rejouant les bougies M1 réelles entre le TP2 et la sortie de chaque trade. C'est une
question de dénombrement, pas d'inférence : elle n'a pas de marge d'erreur statistique.
**C'est la première fois sur ce projet qu'une question est tranchée ainsi**, et c'est la
bonne réponse au problème récurrent du §8 (« une variable qui ne change le gain moyen que
de 2 à 3 $ par trade n'est pas mesurable ») : quand l'effet est trop petit pour être
mesuré, il faut le **compter** au lieu de l'estimer.

**Sizing fait AVANT toute décision, et c'est ce qui a évité la campagne.** Le gain maximum
théorique — si aucun gagnant n'était coupé — valait **+368 $, soit +0,64 $/trade, t +0,24**,
pour une marge de mesure de ±2,64 $/trade. Il aurait fallu **~68 fois plus de données**
pour départager les deux variantes. Un backtest aurait donc produit deux chiffres dont
l'écart aurait été du bruit, pour ~40 minutes de calcul et une modification du moteur.

**Réserves honnêtes :** (1) **l'effet de rebrassage n'est pas modélisé** — couper une
position plus tôt libère le créneau pour la suivante (§0ter), donc un vrai backtest
donnerait un autre chiffre ; imprévisible, et c'est du bruit, pas du signal. (2) **La
méthode a un plancher de précision d'environ ±40 $** (±0,07 $/trade) : au niveau 0R, qui
est le comportement actuel, l'effet devrait valoir exactement 0 et vaut −39,97 $, un trade
sur 196 tombant dans un cas limite de bornes de bougie. (3) **Le nombre de coupés est une
fourchette (57 à 89)** selon qu'on inclut ou non la bougie finale : l'ordre intra-bougie du
moteur décide, et il n'est pas reconstituable depuis les fichiers de résultats. La
conclusion tient dans les deux cas.

**Écarté :** (1) **Lancer la campagne quand même** — proposé à David avec le sizing, il a
choisi d'y renoncer. (2) **Coder le réglage « au cas où »** : toute nouvelle règle arrive
OFF (§9), mais ajouter un réglage mort dans `compute_tp_ladder` et `bot_loop` pour une idée
mesurée négative ne fait qu'alourdir le moteur. (3) **Chercher un niveau de SL optimal** :
c'est exactement le sur-apprentissage que la règle de robustesse interdit, et le balayage
montre qu'il n'y a rien à optimiser.

## 2026-09-07 — Août 2026 : la question ne tenait pas ; et le bot suit bien la tendance
**Décision :** le chantier « août 2026 » est **clos**, et le §0ter reçoit trois résultats
neufs. Aucun backtest relancé, aucun réglage touché : tout est recalculé depuis les
186 fichiers de `_matrix2_out/` et les trois caches M1, par un script nouveau et rejouable,
`backend/_directional.py`. Nouvelle règle de méthode au §9 : **tout résultat qui dépend
d'un paramètre libre doit être rejoué sur plusieurs valeurs de ce paramètre avant d'être
annoncé.**

**La question posée était :** « août 2026 est le mois le plus directionnel des 16 mesurés
(+576 $, directivité 0,312) et le pire de la stratégie (−361 $, PF 0,73) ; une stratégie
SMC censée suivre le biais directionnel qui perd son plus gros mois de tendance, c'est
peut-être le vrai signal. »

**Réponse : la prémisse est fausse sur les deux points.**

1. **Le bot n'a pas combattu la hausse d'août — il l'a suivie.** Sur les 32 trades du mois,
   **25 sont des ACHATS (78 %)** dans un marché qui montait de +576 $. Les 7 ventes
   à contre-sens portent −320 $ des −361 $ du mois. Mais 7 trades ne démontrent rien : le
   perdant moyen vaut −56 $ toutes périodes confondues.
2. **Août n'est pas significativement pire que les autres mois** : écart de −17,84 $ par
   trade **± 13,55 $**, soit **t −1,32**. Et le mois seul vaut −11,29 $ ± 13,28 (t −0,85).
   Comme le 2026-08-27, il fallait d'abord vérifier qu'il y avait quelque chose à
   expliquer. Il n'y a rien.

**Et surtout, la généralisation ne tient pas non plus.** La bonne façon de poser la
question n'était pas « pourquoi ce mois-là » (1 mois, 32 trades) mais « la performance
dépend-elle de la directivité du marché » (14 mois, 575 trades). Réponse :

| Mesure | Résultat | Verdict |
|---|---|---|
| corrélation directivité ↔ gain moyen/trade (14 mois) | r −0,14, **t −0,50** | aucun lien |
| mois directionnels vs mois hachés, au niveau du trade | **+3,30 $/trade ± 5,35**, t +0,62 | aucun lien — et le signe est POSITIF |

Autrement dit, non seulement la stratégie ne souffre pas des marchés directionnels, mais
elle y fait plutôt (insignifiamment) mieux.

**Ce qui EST démontré, et qui est rassurant : le bot suit bien le biais directionnel.**
La part de ventes d'un mois est corrélée au mouvement net du marché à **r −0,73, t −3,72**
sur 14 mois — il vend moins quand ça monte, plus quand ça descend. C'est le **troisième
résultat du projet à dépasser le seuil des 2**, après « la pile de prod perd » (t −2,85) et
« la pile A bat la pile de prod » (t +2,17). Ce n'est pas une découverte exploitable :
c'est le contrôle que le mécanisme du §3 fonctionne comme prévu.

**Le résultat le plus important de la journée est un résultat ÉVITÉ.** En comparant les
trades pris dans le sens de la tendance des 20 jours écoulés à ceux pris à contre-courant,
on obtient **+8,83 $/trade ± 5,32, t +1,66** — le plus gros effet mesuré de la journée, et
une conclusion très vendeuse : « 42 % des trades sont à contre-courant et ne rapportent
rien, il faut un filtre de tendance ». Le contrôle de robustesse la détruit :

| Fenêtre | 5 j | 10 j | 20 j | 40 j | 60 j |
|---|---|---|---|---|---|
| t | −0,02 | +0,92 | **+1,66** | +0,76 | −0,48 |

**Le `t` change de signe selon la fenêtre.** Il n'y a pas d'effet : il y a un choix de
fenêtre, et 20 jours était le tirage le plus flatteur. C'est exactement le mécanisme du
piège `zone_50`, transposé d'un réglage du moteur à un paramètre d'analyse — et cette fois
il a été attrapé avant publication, parce que le contrôle a été fait. D'où la règle du §9.

**Contrôle indirect par un filtre déjà mesuré.** `require_daily_bias` (« ne trader que dans
le sens du biais journalier ») est la version « moteur » de cette idée, et il a été mesuré
sur les trois périodes en entrée M5 dès la campagne. Recalculé en question (b) — bat-il sa
référence ? — il donne **+6,96 $/trade ± 4,96, t +1,40, gagnant 3/3** : le plus fort écart
de confluence de toute la campagne, devant `require_unmitigated_ob` (+3,68 ± 3,40, t +1,08).
**Mais il n'atteint pas le seuil des 2, il coûte 70 % des trades (149 contre 488), et il
n'ajoute rien par-dessus l'OB non mitigé (+2,54 $ ± 5,57, t +0,45).** Il reste OFF. Les
deux approches — la mienne, ad hoc, et celle du moteur — convergent donc sur « non démontré ».

**Correctif de code au passage — le même bug que `_period.py`, encore armé.**
`_matrix2.py:204` figeait `"mode": "intraday"` dans la requête, alors que `backtest.py:163`
choisit les étages d'après **la requête**, pas d'après `trading_mode`. Une variante
« scalping » lancée par `_matrix2.py` aurait donc tourné avec les étages *intraday*, sans
aucun message. **Vérifié : aucun chiffre publié n'en souffre** — les 12 fichiers de piles
sont en `2025h2`/`etude`/`oos`, produits par `_period.py` qui était corrigé, et
`prod-stack` fait 482/758/241 trades là où la pile A en fait 249/328/90 (runs réellement
différents). Les totaux reproduisent la doc au dollar près : 1 481 trades, −3 848 $,
PF 0,86. Le bug était **latent, pas rétroactif**. Corrigé le 2026-09-07.

**Validation de la méthode avant d'en tirer des conclusions**, comme le 2026-08-27 :
le script reproduit la définition de directivité de la session précédente (**0,312 et
+576 $ pour août 2026**, au dixième près), le gain moyen de la config recommandée
(**+5,56 $ ± 2,64, t +2,11** contre +5,47 et t +2,08 publiés — l'écart vient d'un doublon
retiré à la jointure des périodes, 575 trades au lieu de 576) et le `t +1,08` de
`require_unmitigated_ob` en M5.

**Écarté :** (1) **Chercher une explication de marché à août 2026** — c'était la demande,
mais il n'y a ni anomalie du mois ni relation générale à expliquer. (2) **Recommander un
filtre de tendance** sur la foi du t +1,66 : c'est précisément ce que la règle du 2026-08-27
interdit, et le contrôle de robustesse a montré qu'elle avait raison. (3) **Relancer une
campagne de backtests** : la question se répondait entièrement sur les fichiers existants,
et `require_daily_bias` était déjà mesuré sur les trois périodes. (4) **Activer
`require_daily_bias`** malgré son 3/3 : t +1,40 ne passe pas le seuil, et il n'apporte rien
au-dessus du filtre déjà actif. (5) **Ré-exécuter les piles avec `_matrix2.py` corrigé** :
les résultats publiés viennent de `_period.py`, ils sont bons ; les rejouer coûterait des
heures pour retrouver les mêmes chiffres.

**Note sur ce qui reste vraiment ouvert.** Après ce chantier, il n'y a plus de question de
fond en attente sur la stratégie — seulement la validation en démo, qui prendra des mois.

**Les deux questions d'interface ont été tranchées le même jour** (voir l'entrée « La page
Réglages » du 2026-08-27, dont elles étaient la conclusion) : `API_KEY` **est** définie sur
Render, donc le bloc « Dépannage » reste **définitivement** — c'est devenu un garde-fou du
§9, plus une option ; et les sections « Contexte journalier », « Trailing stop » et « Mode
Prop Firm » sont **conservées**. **La page Réglages est figée ; aucun code n'a été
modifié.**

**Malentendu à ne pas reproduire, signalé par David le 2026-09-07.** En annonçant le
correctif de `_matrix2.py`, la formule « `prod-stack` lit maintenant bien `H1→M5→M1→M1` » a
fait craindre que le BOT tourne sur les mauvais étages. Ce n'était pas le cas — `prod-stack`
est une **variante de banc d'essai**, la reconstitution volontaire de l'ancienne
configuration, qui n'existe que pour mesurer à quel point elle perdait. **Toujours préciser
si l'on parle du bot ou d'une variante de test** : les deux manipulent les mêmes noms de
réglages et David n'a aucun moyen de les distinguer sans qu'on le dise. Contrôle refait
devant lui : `trading_mode = intraday` → le moteur lit la famille `intraday_*` →
**`D1→H1→M15→M1`**, les clés `scalping_*` dormant en base sans être lues.

## 2026-08-27 (suite) — La page Réglages ne montre plus que ce qui se décide encore
**Décision :** l'écran Réglages passe de **987 à 734 lignes** et de 14 sections à 9. Sont
retirés de l'interface les réglages sur lesquels la campagne a statué et que David ne
changera plus : **mode de trading, réglage des quatre étages, méthodes de détection
(swing, tracé OB, cassure, cible TP, placement SL, displacement), liquidité et zones
(second CHoCH, inducement, OTE, PDH/PDL, range asiatique, `poi_source`), sessions de
trading, trades par jour, et le sélecteur démo/réel.** En tête de page arrive un bloc
**« Configuration validée » en LECTURE SEULE**.

⚠️ **Aucune valeur n'a été modifiée en base.** Retirer un champ de l'écran ne touche pas
Atlas, et `put_settings` continue d'accepter toutes les clés (la liste blanche
`DEFAULT_SETTINGS` est inchangée) : un script ou un futur écran peut toujours les écrire.
C'est un changement d'**interface**, pas de comportement.

**Pourquoi :** demande de David — « enlever les réglages qu'on ne touche pas ». Le motif de
fond est plus fort que le confort : sur une colonne de 480 px, **86 contrôles dont ~40
doivent rester à leur valeur mesurée** transforment chaque visite en occasion de casser
une configuration qui a coûté trois périodes de backtest à établir. Le risque le plus
concret était le sélecteur **Mode**, à deux touches du « scalping » — qui aurait
instantanément réactivé les clés `scalping_*` toujours en base, c'est-à-dire la pile
mesurée **perdante** (PF 0,86, t −2,85).

**Le bloc « Configuration validée » est le cœur du changement.** Il n'affiche pas des
valeurs codées en dur : il **lit les réglages réellement enregistrés** et les compare à la
configuration mesurée (constante `CONFIG_VALIDEE`, 30 clés). Vert quand tout correspond,
**rouge avec la liste nominative des écarts** dès qu'un réglage dérive. Autrement dit,
l'écran cesse d'être un formulaire pour devenir un **contrôle** : masquer un réglage sans
rendre sa valeur visible aurait juste déplacé le problème — on ne verrait plus la dérive
au lieu de ne plus pouvoir la provoquer. Il porte aussi l'avertissement « performances
passées » et rappelle que `require_unmitigated_ob` **n'est pas démontré supérieur** à son
absence.

**Écarté — et c'est le seul point où la demande de David n'a pas été suivie à la lettre :
la section « Serveur » n'a pas été supprimée**, elle a été déplacée tout en bas dans un
bloc replié « Dépannage — connexion de cet appareil ». Elle contient l'**URL du backend et
la clé API**, stockées par appareil dans `localStorage` (`client.js`), pas en base.
L'URL a un repli à la compilation (`REACT_APP_BACKEND_URL`) — **la clé API n'en a aucun**.
La supprimer rendrait toute nouvelle installation de l'APK, ou tout `localStorage` vidé,
**définitivement incapable de joindre le serveur** dès lors que `API_KEY` est définie sur
Render : plus d'écran pour la saisir, et aucune correction possible sans recompiler.
Repliée, elle est invisible en usage normal et reste disponible le jour où elle sauve
l'installation. **À signaler à David : si `API_KEY` n'est PAS définie sur Render, il peut
demander la suppression pure et simple.**

**Écarté aussi :** (1) **supprimer les sections « Contexte journalier », « Trailing stop »
et « Mode Prop Firm »**, qui répondent pourtant au même critère (réglages jamais touchés,
tous OFF) — David ne les a pas nommées, et retirer plus que demandé est exactement le
genre d'initiative qui fait perdre confiance dans un écran. Elles restent, à lui de
trancher. (2) **Effacer les clés devenues invisibles de la base** : elles documentent ce
qui tournait, et le §0bis prévient déjà qu'un retour en mode scalping les réactiverait.
(3) **Masquer les champs plutôt que les retirer** (`disabled`) : un champ grisé invite
encore à chercher comment le réactiver.

**Vérifié, pas supposé :** `npx craco build` **réussit** (190,65 kB gzip, seul avertissement
restant : une dépendance `useCallback` préexistante dans `Dashboard.jsx`, sans rapport) ;
analyse syntaxique JSX via `@babel/parser` ; aucune référence orpheline aux dix
identifiants supprimés (`onAccountTypeChange`, `ACCOUNT_TYPE_OPTIONS`,
`TRADING_MODE_OPTIONS`, `showRealModal`, `RealAccountModal`, `SelectField`, `TimeField`,
`TF_LIST`, `TF_OPT`, import `Lock`) ; **aucun `data-testid` supprimé n'est référencé
ailleurs** dans `frontend/src` ni dans les tests backend — rien de cassé. Le code mort a
été retiré avec les sections : deux aides de rendu, deux constantes, la modale de
confirmation du compte réel et un import.

**Découvert au passage — le §0 affirmait une chose fausse depuis des semaines.** Le
chantier « l'état du compte MetaApi et `last_error` ne sont pas affichés dans Réglages »
était **déjà fait**. Le composant `MetaApiStatusBanner` couvre six états — non configuré,
en déploiement, connecté, **erreur avec le texte de `last_error`**, backend injoignable,
configuré-non-connecté — et se rafraîchit toutes les 10 s. Le §0 est corrigé ; **plus aucun
reliquat technique n'est ouvert.** Troisième affirmation de la documentation invalidée en
deux jours en allant simplement lire le code, après le champ mort `bot_running` et la
colonne PROD du §0bis.

**Note sur le verrou du compte réel :** retirer le sélecteur démo/réel **ne l'affaiblit
pas**, il le renforce — le passage en réel n'est plus déclenchable depuis l'app, et la
double confirmation côté backend (`put_settings` refuse `account_type="real"` sans
`real_confirmed`) reste intacte. Un texte en lecture seule rappelle à sa place que c'est le
**token MetaApi** qui détermine le compte, aujourd'hui un compte démo chez Axi — ce que le
libellé « Réel » laissait croire à tort.

## 2026-08-27 (suite) — Application des réglages testés, et le bot qui tournait à notre insu
**Décision :** les **11 réglages de la configuration de référence sont écrits dans Atlas**
(accord explicite de David, bot à l'arrêt au moment de l'écriture) : mode `intraday`,
étages `D1→H1→M15→M1`, `require_unmitigated_ob` ON, sessions Londres et New York
08:00–17:00 locales, TP partiels ON, trades/jour illimités, et **désactivation de
`require_daily_bias` et `require_second_choch`** qui étaient actifs en prod. **Le bot n'a
PAS été redémarré** — c'est une décision distincte, elle appartient à David.

**Découverte majeure, faite en lisant Atlas avant d'écrire : le bot TOURNAIT.** Le §0
affirmait « bot à l'arrêt (`bot_running: false`) » depuis deux jours. La réalité :
`bot_state.running = true` depuis le **2026-08-26 04:31 UTC**, soit ~34 h de trading réel,
avec **2 trades pris le 2026-08-27** — sur la pile d'étages mesurée la veille à PF 0,86 /
t −2,85. David l'a arrêté à 14:48 UTC avant toute écriture.

**Cause racine : `settings.bot_running` est un champ MORT.** Il n'existe que comme valeur
par défaut dans `models.py:200` et **aucun code ne le lit** — vérifié par recherche sur
l'ensemble du backend et du frontend. Le champ qui commande réellement est
`bot_state.running` (collection `bot_state`), celui que teste l'auto-reprise au démarrage
du serveur (`server.py:105`) et la boucle elle-même. Personne n'avait vérifié que le champ
cité dans la documentation était celui que le code utilise. **C'est la même erreur que les
trois faux-semblants de l'outillage `_*` du 2026-08-26 : croire la prose plutôt que
d'exécuter le code.** Garde-fou ajouté au §9.

**Second écart découvert au passage — la colonne PROD du §0bis était fausse.** Elle
annonçait « confluences toutes OFF ». En réalité `require_second_choch` était **ON** dès le
snapshot du 2026-08-25, et `require_daily_bias` a été activé en prod entre le 25 et le 27.
La campagne forçait toutes les confluences à OFF (`_matrix2.base_settings`), ce qui a
masqué l'écart. **Conséquence à assumer : le backtest « pile de prod » (PF 0,86, t −2,85)
ne modélisait pas exactement ce qui tournait.** La conclusion tient — c'est la pile
d'étages qui perd, et l'écart mesuré contre la pile A reste significatif — mais ce chiffre
ne doit plus être présenté comme la mesure fidèle de la prod d'alors.

**Les 11 clés modifiées** (valeurs précédentes → nouvelles) :

| Réglage | Avant | Après |
|---|---|---|
| `trading_mode` | scalping | **intraday** |
| `intraday_ltf` | M5 | **M1** |
| `require_unmitigated_ob` | False | **True** |
| `require_daily_bias` | **True** | False |
| `require_second_choch` | **True** | False |
| `partial_tp_enabled` | False | **True** |
| `session_london_start` / `_end` | 01:00 / 23:00 | **08:00 / 17:00** |
| `session_newyork_start` / `_end` | 12:00 / 00:00 | **08:00 / 17:00** |
| `max_trades_per_day` | 500 | **999999** |

Inchangés parce que déjà conformes : `min_rr` (1), `intraday_d1/htf/mtf` (D1/H1/M15),
`risk_per_trade_pct` (1 %), `max_consec_losses` (3), `max_drawdown_pct` (3 %),
`trailing_mode` (off), `require_premium_discount` (True), `swing_method`, `ob_zone`,
`sl_mode`, `ob_entry_mode`, `tp_target`, filtre news.

**Méthode d'écriture, à réutiliser telle quelle :** la cible n'a pas été recopiée depuis la
prose du `CLAUDE.md` mais **reconstruite en exécutant `_matrix2.base_settings("on", "m1")`
+ `VARIANTS["rr-1-unmit"]`** — les réglages exacts qui ont produit les chiffres. Le script
d'application refuse d'écrire si `bot_state.running` est vrai, filtre les clés par la même
liste blanche `DEFAULT_SETTINGS` que `put_settings` (`server.py:161`), ne touche jamais aux
clés secrètes / compte / notifications, et **sauvegarde les anciennes valeurs dans un
fichier de restauration avant d'écrire**. La liste blanche a d'ailleurs servi : la clé
`signal_only_mode`, encore présente dans le snapshot de prod, a été écartée (le mode a été
retiré le 2026-08-25).

**Vérifié après écriture, en exécutant le code du moteur** et non en relisant la base :
`smc.params_from_settings()` sur les réglages vivants renvoie `require_unmitigated = True`
(⚠️ la clé du moteur ne s'appelle PAS `require_unmitigated_ob`), `min_rr = 1.0`,
`sl_mode = poi`, `ob_entry_mode = close`, `tp_target = range_bound`, et les étages lus sont
bien `D1 → H1 → M15 → M1`. `bot_state.running` toujours `False` après l'opération.

**Écarté :** (1) **Passer par l'API `PUT /api/settings` de Render** — plus propre en
principe, mais la clé API se saisit par appareil dans l'app et n'est pas dans le `.env`
local ; l'écriture directe reproduit exactement ce que fait `store.update_settings`
(`store.py:44`), avec la même liste blanche appliquée en amont. (2) **Laisser David saisir
les 11 réglages à la main** dans la page Réglages : onze champs répartis dans cinq
sections, sur mobile, sans possibilité de vérifier le résultat côté moteur — trop d'erreurs
possibles pour un remplacement complet. (3) **Effacer les clés `scalping_*`** devenues
inertes : elles ne sont plus lues en mode intraday, les effacer ferait perdre l'historique
de ce qui tournait, et le §0bis documente désormais qu'elles redeviendraient actives si
quelqu'un rebasculait le mode. (4) **Redémarrer le bot dans la foulée** : jamais sans
demande explicite de David.

**Ce que ça change pour la suite :** pour la première fois, **la prod et la configuration
mesurée coïncident**. Les chiffres de la pile A + OB non mitigé (PF 1,21, 576 trades)
décrivent donc réellement ce que ferait le bot — aux réserves connues près (commissions,
slippage, exécution partielle, filtre news non modélisés ; avantage du filtre non
démontré). L'étape suivante est la validation en démo, dont le rôle a été redéfini le
matin même : vérifier l'exécution réelle, pas départager deux configurations.

## 2026-08-27 — La règle des trois périodes ne suffit pas : il manquait la marge d'erreur
**Décision :** toute comparaison entre deux variantes de backtest doit désormais être
accompagnée de **la marge d'erreur sur l'écart** — l'écart de gain moyen par trade et son
`t` (test de Welch), pas seulement deux profit factors côte à côte. La règle « plusieurs
périodes ou rien » est **conservée mais rétrogradée** : nécessaire, pas suffisante. Une
variante ne compte que si elle bat la référence sur toutes les périodes **et** que l'écart
dépasse sa propre marge d'erreur. Corollaire immédiat : **la réserve qui bloquait la
décision de David (`require_unmitigated_ob` à 2/3 en entrée M1) est retirée — elle
n'existait pas.** Elle décrivait du bruit.

**Pourquoi :** David a demandé pourquoi la période juin→août 2026 « se comporte à
l'envers ». Réponse mesurée : **elle ne se comporte pas à l'envers, il n'y a rien à
expliquer.** Les trois inversions du 2026-08-26 (le RR, `zone_50`, le passage M5→M1) ont
été rejouées au test du bruit sur les 186 fichiers de résultats déjà sur disque, sans
relancer un seul backtest. **Sur 18 comparaisons, aucune n'atteint |t| = 2 ; la plus forte
est à 1,33.** Hors échantillon, l'écart référence ↔ OB non mitigé vaut **−1,85 $ par trade
avec une marge de ± 11,71 $** : le vrai effet peut aussi bien valoir −25 $ que +21 $. Une
direction a été lue dans un nuage de points, trois fois de suite.

**La cause de l'erreur, et c'est le point à retenir : deux questions différentes ont été
confondues.**

| Question | Comment on y répond | Config recommandée |
|---|---|---|
| (a) Cette configuration gagne-t-elle de l'argent ? | `t` sur le gain moyen | **t = +2,08** ✅ |
| (b) Est-elle MEILLEURE que sa référence ? | `t` sur **l'écart** | **t = +0,97** ❌ indécidable |

Le `t +2,08` célébré comme « le premier au-dessus de 2 du projet » répond à la question
(a). C'est la (b) qui justifie d'activer une confluence, et **elle n'avait jamais été
calculée**. L'avantage de `require_unmitigated_ob` sur sa référence vaut **+3,22 $/trade
± 3,33 $** en entrée M1 (fourchette plausible : −3,43 $ à +9,88 $) et **t +1,08** en M5.
Le filtre n'est pas mauvais : il est **non démontré, dans les deux sens**.

**Défaut de méthode découvert au passage — les deux runs ne comparent pas les mêmes
trades.** Un filtre ne peut que RETIRER des opportunités, pourtant des trades
APPARAISSENT : 110 coupés / 81 apparus sur `2025h2`, 157/106 sur `etude`, 31/20 sur `oos`.
Le recouvrement n'est que de **52 à 66 %**. La cause est mécanique et parfaitement
légitime (une seule position à la fois, arrêt après 3 pertes) : bloquer un trade à 13h38
libère le créneau de 13h49. Conséquence : ce qu'on mesurait comme « l'effet du filtre »
est l'effet du filtre **plus un rebrassage de la moitié du portefeuille**. Vaut pour les
47 configurations de la campagne, pas seulement pour celle-ci.

**La règle 3/3 telle qu'appliquée ne trie pas mieux que pile ou face.** Entonnoir réel
reconstruit depuis les fichiers : 46 variantes sur la période d'étude → 31 battent la
référence → 16 portées jusqu'au hors échantillon → **8 tiennent 3/3, soit 50 % de
survie** — exactement le taux d'une pièce de monnaie. Et le chiffre qui résume tout :
**sur les 46 variantes, ZÉRO n'atteint |t| ≥ 2 contre la référence** sur la période
d'étude, alors que le hasard seul en aurait produit environ 2,3. La campagne a trouvé
**moins de signal que du bruit pur n'en aurait fabriqué**. La règle reste utile — elle a
écarté `zone_50` avant la production — mais seule, elle ne discrimine pas.

**Ce qui SURVIT au test, et qui en sort renforcé :**
1. **La pile de prod perd vraiment.** t −2,85 dans l'absolu, et en duel direct contre la
   pile à quatre étages **t = +2,17** (**+2,89** avec l'OB non mitigé). Ce résultat n'a pas
   été pêché parmi 47 candidates : quatre piles décidées d'avance, donc pas de biais de
   sélection. **L'interdiction de démarrer le bot sur les réglages de prod est confirmée.**
2. **La configuration recommandée est régulièrement rentable**, pas portée par un coup de
   chance : 10 mois gagnants sur 14, et **+1 250 $ sur 459 trades même en retirant les
   trois meilleurs mois**.
3. **Ce qui est démontré, c'est la PILE D'ÉTAGES, pas le filtre.** La décision en attente
   porte donc sur `D1→H1→M15→M1` contre le `H1→M5→M1→M1` de la prod — là le dossier est
   net — et non sur `require_unmitigated_ob`, qui reste un choix par défaut raisonnable
   mais non prouvé.

**Corrigé dans le §0ter :** « les deux piles qui prennent H1 comme biais échouent » était
un cran trop affirmatif. La pile B (`H1→M15→M5→M1`) contre la pile A donne **t = +0,67**,
non significatif. L'échec est établi pour la **pile de prod (C)**, pas pour la pile B.

**L'hypothèse « le régime récent diffère » ne tient pas non plus à la mesure.** Calculée
sur les bougies M1 des caches : amplitude quotidienne moyenne de **1,54 %** sur `2025h2`,
**2,49 %** sur `etude`, **2,07 %** hors échantillon. Le hors échantillon est **entre les
deux autres** ; c'est `2025h2` (marché calme et tendanciel) qui est l'exception. Il n'y a
pas de régime aberrant à expliquer, seulement 79 trades.

**Conséquence pour la validation en démo, à dire à David sans détour :** au rythme mesuré
(~41 trades/mois), départager `require_unmitigated_ob` de sa référence demanderait environ
**2 450 trades, soit près de cinq ans**. **La démo ne peut pas trancher cette question.**
Son rôle reste indispensable mais il est autre : vérifier que l'exécution réelle (spread,
slippage, filtre news, ordres posés chez le broker) se comporte comme le backtest le
suppose. Ne jamais lui demander de valider un avantage statistique.

**Écarté :** (1) **Chercher une explication de marché à l'inversion** — c'était la demande
initiale ; il fallait d'abord vérifier qu'il y avait quelque chose à expliquer, et il n'y
avait rien. (2) **Télécharger une quatrième période** : sans marge d'erreur, une période
de plus n'aurait fait qu'ajouter un quatrième tirage à pile ou face — et avec la marge
d'erreur, on voit qu'il en faudrait des dizaines. (3) **Conclure que la configuration
recommandée est mauvaise** : elle ne l'est pas, elle est rentable et régulière ; c'est son
AVANTAGE SUR SA RÉFÉRENCE qui est indécidable, pas sa rentabilité. (4) **Jeter la règle
des trois périodes** : elle a évité `zone_50` en production, elle reste le premier filtre.
(5) **Corriger le rebrassage en forçant les deux runs sur les mêmes trades** : ce serait
mesurer un bot qui n'existe pas — la contrainte « une position à la fois » est réelle.

**Méthode :** aucun backtest relancé, aucun réglage modifié, aucun code de l'app touché.
Tout est recalculé depuis les 186 fichiers de `backend/_matrix2_out/` (qui stockent chaque
trade individuellement) et les trois caches M1. La méthode reproduit **exactement** les
chiffres publiés le 2026-08-26 (PF 1,21 / t +2,08 / 576 trades ; PF 0,86 / t −2,85 /
1 481 trades), ce qui la valide avant d'en tirer des conclusions nouvelles.

**Question ouverte, la seule qui reste :** **août 2026 est le mois le plus directionnel
des 16 mesurés** (+576 $, directivité 0,312, la plus forte de tout l'échantillon) et c'est
**le pire mois de la stratégie** (−361 $, PF 0,73). Une stratégie SMC censée suivre le
biais directionnel qui perd son plus gros mois de tendance, c'est peut-être le vrai signal
— et il n'a jamais été regardé.

## 2026-08-26 (suite) — La pile d'étages décide de tout ; la configuration de prod est perdante
**Décision :** la configuration de référence du projet devient **intraday
`D1 → H1 → M15 → M1`, `require_unmitigated_ob` actif, sessions Londres et New York
08:00–17:00 heures locales, RR 1, TP partiels actifs, risque 1 %** — 576 trades sur trois
périodes indépendantes, PF 1,21, DD max 11,9 %, **t +2,08** (le premier au-dessus de 2 du
projet), rentable sur les TROIS périodes. **Pas encore appliquée en prod** : c'est la
décision de David, et la réserve ci-dessous n'est pas levée.

**Pourquoi cette campagne a eu lieu :** David a demandé des backtests à RR 1, puis a
signalé que la configuration testée entrait en M5 alors qu'il veut scalper en M1. Sa
question était fondée — les 47 configurations de la campagne, et donc la recommandation
`require_unmitigated_ob` à PF 1,18, portaient toutes sur une entrée M5 jamais remise en
cause. Quatre piles d'étages ont alors été mesurées, un seul écart entre elles.

**Ce qui est établi (chiffres complets dans CLAUDE.md §0ter) :**
1. **La pile enregistrée en prod (`H1→M5→M1→M1`) est perdante sur les trois périodes** :
   PF 0,86, −3 848 $, DD 48 %, **t −2,85**. C'est le résultat le plus significatif jamais
   obtenu sur ce projet, et il est négatif. Le bot était à l'arrêt : cela l'a protégé.
2. **Ce qui décide, c'est le contexte au-dessus, pas la timeframe d'entrée.** Les deux
   piles qui gardent `D1→H1→M15` sont rentables (entrée M1 comme M5) ; les deux qui
   prennent H1 comme biais échouent (B : 1/3 ; C : 0/3). `models.py` portait déjà la note
   « H1 = perdant, DD catastrophique » — confirmée sur le moteur corrigé.
3. **Scalper en M1 est viable**, à condition de garder les quatre étages au-dessus.
4. **Le filtre de session se justifie** : en 24h/24, le PF baisse sur 3/3 périodes et le
   DD monte sur 3/3, pour +37 % de trades et +3,5 % de P&L seulement (gain par trade
   5,47 $ → 4,13 $). **Seul test de la journée où la période hors échantillon confirme les
   deux autres** — donc le plus fiable de tous.
5. **Le RR minimum ne donne aucune règle fiable** : monter à 1,5 / 2 / 3 aide sur les deux
   périodes anciennes et dégrade régulièrement la période hors échantillon. Le RR 1
   enregistré en prod n'est pas un défaut.

**Écarté :** (1) `RR 2 + OB non mitigé`, meilleure ligne du balayage RR (PF 1,25, t +1,85,
DD ramené à 8 %) mais 2/3 périodes — même forme de piège que `zone_50`. (2) La pile B
(`H1→M15→M5→M1`, le scalping tel que le code le prévoit) : 1/3, DD 24 %. (3) Le 24h/24.
(4) Conclure sur le seul `t` : celui de la configuration retenue est le meilleur du
projet, mais son avantage sur sa propre référence vient surtout d'une période.

**Réserve non levée, à dire à David chaque fois qu'on cite ces chiffres :**
`require_unmitigated_ob` bat sa propre référence sur 3/3 périodes en entrée M5, mais
seulement **2/3 en entrée M1** (1,12 contre 1,25 hors échantillon). La configuration
retenue est la meilleure mesurée, ce n'est pas une certitude — la validation en démo
reste indispensable.

**Signal de fond à ne pas oublier :** sur cette seule journée, **trois** effets mesurés
sur juillet 2025 → juin 2026 se sont inversés sur juin → août 2026 (le RR, `zone_50`, le
passage M5→M1). Le régime récent du marché diffère. Moyenner trois périodes est peut-être
la mauvaise méthode ; la question n'est pas tranchée.

**Deux bugs de l'outillage corrigés au passage** (fichiers `_*`, hors Git) :
`_run_period.py` ne transmettait pas `--entry` — `--entry m1` tournait silencieusement en
M5, ce qui explique que la variante M1 n'ait jamais abouti depuis des semaines ; et
`_period.py` figeait `mode: "intraday"` dans la requête alors que c'est elle, et non les
réglages, qui décide si le moteur lit les étages `intraday_*` ou `scalping_*`
(`backtest.py:163`) — sans ce correctif, toute variante « scalping » aurait produit des
chiffres faux qui ressemblaient à des vrais. **Leçon : dans cet outillage, vérifier ce qui
est réellement transmis au moteur, jamais ce que l'usage documenté laisse croire.** C'est
la même erreur qui avait fait écrire « RR 2 » dans le §0bis alors que toute la campagne
tournait à RR 1, `min_rr` étant hérité du snapshot de prod sans jamais être surchargé.

**Piège de lecture consigné :** `max_drawdown_pct` (3 %) est un coupe-circuit
**journalier**, comparé à l'équité de début de journée (`backtest.py:130-132`), avec
reprise ensuite. Un DD cumulé de 48 % est parfaitement compatible avec ce réglage. Ne
jamais le présenter comme une limite de perte totale.

## 2026-08-26 (suite) — Documentation : un rôle par fichier, et un §0 « État courant »
**Décision :** les quatre documents Markdown du projet cessent de raconter la même chose.
Rôles exclusifs, énoncés en tête de `CLAUDE.md` : **`CLAUDE.md`** = ce qui EST vrai
aujourd'hui (état, règles, garde-fous, commandes) ; **`DECISIONS.md`** = le POURQUOI daté ;
**`REPRISE.md`** = le bloc à copier-coller pour ouvrir une session, qui ne décrit rien et
ne fait que pointer ; **`CONTEXTE-COWORK.md`** = le seul brief autonome, pour un assistant
sans accès au dépôt, explicitement subordonné au §0 de `CLAUDE.md` en cas de contradiction.
`CLAUDE.md` gagne un **§0 « État courant »** en tête (commit déployé, état du bot, décision
en attente, chantiers ouverts), un **§0bis** comparant les trois jeux de réglages qui
coexistent, et un **§0ter** listant les résultats de backtest déjà acquis pour que personne
ne les rejoue. Le §7 devient une table de renvoi vers ce fichier au lieu d'un troisième
récit. La numérotation §1–§13 est conservée : `DECISIONS.md` (§9) et `CONTEXTE-COWORK.md`
(§12) y renvoient.
**Pourquoi :** l'audit a trouvé le commit de prod **faux** dans `CLAUDE.md` (`dc84d1d` au
lieu de `698ceba`), trois travaux terminés encore listés comme « marche à suivre »
prioritaire (connexion MetaApi, audit du graphique, fiabilisation du backtest), une
instruction « vérifier que c'est implémenté » sur du code implémenté depuis longtemps, et
une contradiction directe entre le §11 (« fichiers `_*` supprimables sans risque ») et le
§7 (« caches à réutiliser ») — un modèle appliquant le §11 effaçait des heures de
téléchargement MetaApi. Toutes ces erreurs viennent du même mécanisme : le même fait
recopié dans plusieurs fichiers, mis à jour dans un seul.
**Découvert au passage, et c'est le plus important :** le dépôt GitHub n'est pas
`davos972/SMC-APP` (affirmé depuis l'origine) mais **`davos972/SMC-Claude-Code-2`**.
Surtout, **l'écart entre la prod et ce qui a été mesuré est bien plus large que les seules
sessions**. D'après `_prod_settings.json` (snapshot Atlas du 2026-08-25), la prod tourne en
mode **scalping H1→M5→M1→M1** avec **TP partiels désactivés**, alors que la campagne des
47 configurations a mesuré **intraday D1→H1→M15→M5, TP partiels actifs**. (Le RR minimum
vaut 1 des deux côtés : `_matrix2.base_settings()` part du snapshot de prod et ne surcharge
jamais `min_rr` — vérifié en exécutant le chemin de code, pas en lisant la prose.) Aucun chiffre de la campagne ne décrit ce que ferait la prod dans son état
actuel. À noter aussi : `scalping_mtf` et `scalping_ltf` valent tous deux M1 — structure
et déclencheur sur la même timeframe, ce qui n'est pas l'analyse à quatre étages du §3 et
n'a jamais été mesuré.
**Écarté :** (1) supprimer `CONTEXTE-COWORK.md` comme pur doublon — il a un public réel
(un assistant sans accès au dépôt) ; il est conservé, corrigé, et explicitement subordonné.
(2) Renuméroter les sections de `CLAUDE.md` pour insérer l'état courant — deux fichiers
pointent sur des numéros ; le §0 évite la casse. (3) Purger l'historique du §7 : les
résultats de backtest acquis (§0ter) doivent rester dans `CLAUDE.md`, pas seulement ici,
sinon quelqu'un rejouera OTE ou Power of 3.
**Complément du même jour — les documents SMC entrent dans le dépôt.** Le `CLAUDE.md` et
`backend/smc.py` citaient le « Manuel de détection SMC » et la « Synthèse stratégie V3 »
une trentaine de fois, avec numéros de section, alors que **ni l'un ni l'autre n'était
dans le projet** : aucune règle du moteur n'était vérifiable à la source. David les a
fournis ; ils sont désormais dans `repo/docs/`, en `.docx` (qui fait foi) **et** en
conversion Markdown lisible et cherchable. La correspondance des numéros a été vérifiée
une par une (Manuel §3.2 = IFVG, §3.3 = BPR, §4.1 = Order Block, §6.1 = Range asiatique ;
V3 §5.8, §Étape 5, §10 = noyau/confluences) — elle colle exactement.
**Écarté :** (1) ne verser que le `.md` — le `.docx` est l'original de David, le perdre
serait perdre l'autorité ; (2) ne verser que le `.docx` — illisible par `grep` et par un
modèle sans convertisseur, donc inutile en pratique ; (3) utiliser `pandoc` ou
`python-docx` : aucun des deux n'est installé sur le PC de David, d'où `docs/docx2md.py`,
écrit avec la seule bibliothèque standard et versé avec les documents pour que la
conversion reste reproductible.
**Écart documenté au passage :** le §10 de la Synthèse V3 met **sweep ET CHOCH** dans le
noyau ; le moteur exige sweep **OU** CHoCH (`smc.py:1207`). Ce n'est pas un oubli : imposer
la séquence a été mesuré et dégrade les résultats (PF 0,94 vs 0,97). Le réglage existe
(`require_sweep_then_choch`), il reste OFF. C'est écrit dans `docs/README.md` pour que
personne ne « corrige » le code vers le document sans refaire la mesure.

**Vérifié, pas supposé :** timeouts MetaApi à 240 s, instance `apiLong`, progression et
annulation du backtest, styles et calques du graphique, repli `.env` sur les tokens,
absence d'affichage de `last_error` dans `frontend/src`, limite des 6 mois côté API,
et `py -m pytest backend/tests/test_backtest_lookahead.py backend/tests/test_signal_reason.py`
→ **11 passed**. Aucun code modifié : cette entrée ne concerne que la documentation.

## 2026-08-26 (suite) — Troisième période : le SL protégé sort, l'OB non mitigé confirme
**Décision :** à la demande de David (« juin-août 2026 et le début 2026 sont des périodes
spéciales »), les 47 configurations ont été rejouées sur un TROISIÈME jeu de données
indépendant : juillet → décembre 2025 (cache `_m1_cache_XAUUSD_2025-05-01_2026-01-01.json`,
238 257 bougies M1, mai-juin en chauffe). L'or y monte de 3 311 à 4 311 $ — une forte
tendance haussière, régime différent des deux autres. Référence : PF 0,99 sur 183 trades.
**Ce qui change :** `sl_mode="protected"` est RETIRÉ de la recommandation. Sur les trois
périodes il fait +0,03 / +0,09 / −0,26 par rapport à la référence : il n'ajoute rien à
l'order block non mitigé, qui suffit seul.
**Recommandation finale :** `require_unmitigated_ob = True` seul — 447 trades cumulés,
PF 1,18, t +1,62, au-dessus de la référence sur les TROIS périodes (1,10 / 1,10 / 1,58 contre
0,99 / 0,97 / 1,30), et il ne coupe que 3 % des opportunités. Second choix, à considérer
ensuite : `require_daily_bias` — plus gros avantage par trade (PF 1,34 cumulé, t +1,69,
3/3) mais il divise le nombre de trades par quatre, donc quatre fois plus de temps pour
valider en démo.
**Sept configurations sur 47 battent la référence sur les trois périodes** : Daily Bias,
TP proche + Daily Bias, OB non mitigé, OB non mitigé + SL protégé, OB non mitigé + TP
proche + Daily Bias, OB non mitigé + Daily Bias, TP au swing le plus proche. Toutes les
combinaisons bâties sur `ob_entry_mode="zone_50"` sont 2/3 (elles s'effondrent hors
échantillon), confirmant le diagnostic de surapprentissage.
**Le noyau seul ne gagne pas :** référence cumulée sur les trois périodes = 488 trades,
PF 1,02, t +0,22. Sans au moins une confluence validée, la stratégie est à l'équilibre.
**Écarté :** conclure sur deux périodes. Sur les deux premières, `sl_mode="protected"`
semblait acquis (3/3 en apparence) ; la troisième l'a départagé. Règle : une période
supplémentaire coûte 30 minutes de calcul et évite un mauvais réglage en production.

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
