# CONTEXTE PROJET — GoldFlow SMC (bot de trading automatique MT5)

> Prompt de contexte pour Claude Code. Lis ce document en entier avant toute
> modification du code.
>
> **Répartition des quatre documents — ne jamais raconter la même chose dans deux
> d'entre eux** (c'est ce qui a fait diverger le commit de prod le 2026-08-26) :
>
> | Fichier | Contient | Ne contient PAS |
> |---|---|---|
> | `CLAUDE.md` (ici) | Ce qui EST vrai aujourd'hui : état, règles, garde-fous, commandes | Le récit de comment on y est arrivé |
> | `DECISIONS.md` | Le POURQUOI, daté : décision, raison, alternatives écartées | L'état courant |
> | `../REPRISE.md` | Le bloc à copier-coller pour ouvrir une session | Toute documentation de fond |
> | `../CONTEXTE-COWORK.md` | Le brief autonome pour un assistant **sans accès au dépôt** — et la **carte du code** (« où trouver quoi ») | Rien qui contredise le §0 d'ici, qui fait autorité |
> | `docs/` | Les **documents SMC de David** qui font autorité sur la stratégie (`.docx` + conversion `.md`) | Toute règle d'implémentation — le code, lui, n'applique que ce qui est validé en backtest |

---

## 0. ÉTAT COURANT — 2026-09-07

**Ce qui tourne.** Prod sur Render (`goldflow-backend` + `goldflow-frontend`), base
MongoDB Atlas. **La prod tourne sur `origin/main`, pas sur la copie locale** — le vrai
numéro se lit toujours avec `git rev-parse --short origin/main`, ne jamais le supposer.
Dernier commit déployé : **`506e7bc`** (2026-09-07). Le dernier commit qui touche le
**moteur** reste `db61adb` (anti-anticipation, 2026-08-26) : depuis, seuls le frontend et
la documentation ont bougé. `6465189` allège la page Réglages — c'est le **frontend** ;
`backend/` n'a pas changé depuis le 2026-08-26, donc aucun changement de comportement du
bot n'a été déployé.
🟢 **État du bot : EN MARCHE**, sur la configuration validée, **aucune position ouverte**.
Lu dans Atlas le **2026-09-07 à 05:16 UTC** (`bot_state.running = true`, `trades_today = 0`).
Redémarré par David le 2026-08-27 à 17:59 UTC, après l'écriture des réglages testés à 15:44.
⚠️ Cet état change sans prévenir : **toujours le relire dans Atlas**, ne jamais le recopier
d'ici — c'est la règle qui a coûté 34 h de trading non documenté (§9).

**Premiers résultats réels sur la configuration validée — 8 trades, du 2026-08-27 au
2026-09-04** (collection `trades`, métriques par `backtest._compute_metrics`) :

| Trades | Gagnants | Winrate | Profit factor | P&L | DD max | RR prévu moyen |
|---|---|---|---|---|---|---|
| 8 | 4 | 50 % | **0,84** | **−29,73 $** | 3,12 % | 2,48 |

Sorties : 4 SL, 3 « trailing_sl », 1 TP. Sens : **7 ventes pour 1 achat**.

🔴 **NE RIEN CONCLURE DE CES CHIFFRES — 8 TRADES NE MESURENT RIEN.** C'est le résultat
direct de la règle du §8 : avec un écart-type d'environ 60 $ par trade, il faut plusieurs
centaines de trades pour distinguer une performance d'un tirage au sort. Un PF de 0,84 sur
8 trades est parfaitement compatible avec la configuration mesurée à 1,21, comme il le
serait avec une configuration perdante. **Ne pas changer un réglage sur cette base**, et ne
pas non plus s'en rassurer. Au rythme observé (~1 trade/jour), il faudra des mois avant que
ce journal dise quoi que ce soit.

ℹ️ **« trailing_sl » n'est PAS un trailing stop qui se serait rallumé.** `trailing_mode`
vaut bien `off` ; `bot_loop.py:233` étiquette `trailing_sl` **toute** sortie dont le SL
avait été déplacé — ici par TP1, qui remonte le stop à l'entrée (`tp1_to_breakeven`). Ces
3 sorties sont des trades passés en break-even puis clôturés, c'est le comportement normal
des TP partiels. Vérifié le 2026-09-07, ne pas rouvrir.

🚨 **NE JAMAIS LIRE `settings.bot_running` POUR CONNAÎTRE L'ÉTAT DU BOT — C'EST UN CHAMP
MORT.** Il n'existe que comme défaut dans `models.py:200` et **aucun code ne le lit**
(vérifié par recherche sur tout le backend et le frontend). Le champ qui commande est
**`bot_state.running`**, dans la collection Mongo `bot_state` ; c'est lui que teste
l'auto-reprise au démarrage du serveur (`server.py:105`). Cette confusion a coûté cher :
le §0 a affirmé pendant deux jours que le bot était à l'arrêt **alors qu'il tournait**.
Démarré le 2026-08-26 à 04:31 UTC, il a tourné environ 34 h sur la pile de prod mesurée
perdante et pris **2 trades le 2026-08-27** avant d'être arrêté.

⚠️ **L'APK Android tourne sur `d90c6a7`** (n° 9) et est désormais **EN RETARD** : la page
Réglages a été allégée le 2026-08-27 (§5). Ce n'est pas bloquant pour le trading — l'APK
parle au même backend et les réglages sont les mêmes — mais l'app mobile affiche encore
l'ancien écran, sans le bloc « Configuration validée ». À recompiler quand David le
voudra (GitHub Actions, cf. §6bis).

🚨 **NE PAS DÉMARRER LE BOT SUR LES RÉGLAGES ACTUELLEMENT ENREGISTRÉS EN PROD.** La pile
d'étages qui y est enregistrée (scalping `H1→M5→M1→M1`) a été mesurée le 2026-08-26 :
**perdante sur les trois périodes, PF 0,86, −3 848 $ sur 1 481 trades, DD 48 %, t −2,85**.
C'est le résultat le plus significatif du projet, et il est négatif (§0ter).

✅ **DÉCISION PRISE ET APPLIQUÉE le 2026-08-27** (accord explicite de David, bot à
l'arrêt au moment de l'écriture). Les réglages ci-dessous sont **désormais ceux enregistrés
dans Atlas** — 11 clés modifiées, détail et valeurs précédentes dans `DECISIONS.md`. Le bot
n'a PAS été redémarré : c'est la décision suivante, et elle appartient à David.

```
Mode          intraday
Étages        D1 → H1 → M15 → M1
Filtre        require_unmitigated_ob = ON   (seule confluence active)
Sessions      Londres 08:00–17:00 et New York 08:00–17:00 (heures LOCALES)
RR minimum    1
TP partiels   activés
Risque        1 % par trade
```

**576 trades sur trois périodes indépendantes · PF 1,21 · +3 148 $ sur 4 919 $ ·
DD max 11,9 % · t +2,08 · rentable sur les TROIS périodes**, et régulièrement : 10 mois
gagnants sur 14, encore +1 250 $ sur 459 trades en retirant les trois meilleurs mois.

⚠️ **Ce `t +2,08` répond à « cette config gagne-t-elle de l'argent ? », PAS à « est-elle
meilleure que sa référence ? »** — deux questions différentes, longtemps confondues ici
(§0ter, entrée `DECISIONS.md` du 2026-08-27). Sur la seconde, l'écart vaut +3,22 $/trade
± 3,33 $, soit **t +0,97 : indécidable**.

✅ **La réserve « 2/3 en entrée M1 » est LEVÉE — elle décrivait du bruit** (mesuré le
2026-08-27) : l'écart de −0,13 de PF hors échantillon vaut −1,85 $/trade ± 11,71 $, soit
t −0,16. Ne plus la citer.

⚠️ **Mais ce qui est démontré, c'est la PILE D'ÉTAGES, pas le filtre.** `D1→H1→M15→M1`
contre la pile de prod : **t +2,17** (et +2,89 avec le filtre) — solide, et sans biais de
sélection. `require_unmitigated_ob` contre sa propre référence : **t +0,97, non démontré
dans les deux sens**. Il reste un choix par défaut raisonnable, ce n'est pas un acquis.
Sans lui, la pile A seule fait PF 1,10, t +1,10, rentable 3/3.

**Chantiers ouverts, dans l'ordre**

1. ~~La décision d'appliquer ou non cette configuration.~~ **FAIT le 2026-08-27.** Les
   11 réglages sont écrits dans Atlas et vérifiés côté moteur (`params_from_settings`
   renvoie bien `require_unmitigated = True`, `min_rr = 1.0`, étages `D1→H1→M15→M1`).
   ~~Reste à décider : redémarrer le bot.~~ **FAIT — David a redémarré le bot à 17:59 UTC
   le 2026-08-27**, sur la nouvelle configuration. Le chantier 1 est clos.
   **Journal de trading remis à zéro le même jour** (18:43 UTC, à sa demande) : les
   17 trades clôturés de l'ancienne configuration ont été supprimés de la collection
   `trades` pour que l'onglet Stats ne mesure QUE la nouvelle. La position ouverte a été
   conservée. Sauvegarde intégrale des 18 documents avant suppression.
2. **Valider en démo — mais pour la bonne raison.** Son rôle est de vérifier que
   l'exécution réelle se comporte comme le backtest le suppose : spread, slippage, filtre
   news, SL/TP effectivement posés chez le broker, comportement du bot sur plusieurs
   jours. ⚠️ **Elle ne peut PAS départager deux configurations proches** : au rythme
   mesuré (~41 trades/mois), il faudrait ~2 450 trades, soit près de cinq ans. Ne jamais
   lui demander de valider un avantage statistique (`DECISIONS.md`, 2026-08-27).
3. ~~Comprendre l'inversion de la période juin→août 2026.~~ **TRAITÉ le 2026-08-27 :
   il n'y avait pas d'inversion.** Les trois effets « inversés » sont du bruit (18
   comparaisons, aucune n'atteint |t| = 2), et le régime de juin→août 2026 n'est pas
   aberrant — son amplitude quotidienne (2,07 %) est ENTRE celles des deux autres périodes
   (1,54 % et 2,49 %). Détail complet dans `DECISIONS.md` (2026-08-27).
4. **La seule question de fond qui reste ouverte : août 2026.** C'est le mois le plus
   directionnel des 16 mesurés (+576 $, directivité 0,312, la plus forte de l'échantillon)
   et **le pire mois de la stratégie** (−361 $, PF 0,73). Une stratégie censée suivre le
   biais directionnel qui perd son plus gros mois de tendance — jamais regardé.
5. ~~Petit reste technique : l'état MetaApi et `last_error` pas affichés.~~ **C'ÉTAIT
   FAUX — vérifié le 2026-08-27 en lisant le code.** Le composant `MetaApiStatusBanner`
   (`frontend/src/pages/Settings.jsx`) affiche déjà les six états : non configuré, en
   déploiement, connecté, erreur de connexion **avec le texte de `last_error`**, backend
   injoignable, configuré-non-connecté ; il est rafraîchi toutes les 10 s. Ce chantier
   était clos depuis longtemps. **Plus aucun reliquat technique ouvert.**

**Non implémentés volontairement** : **OB 2.0** (imposerait un 5e étage de timeframe) et
**SMT Divergence** (imposerait de suivre un 2e instrument corrélé en continu, casserait
l'architecture mono-symbole). La Synthèse V3 les classe elle-même en dernier.

### 0bis. Les trois jeux de réglages — à consulter AVANT d'interpréter quoi que ce soit

Trois valeurs différentes coexistent pour les mêmes réglages. Les confondre est l'erreur
la plus coûteuse du projet : elle fait citer un chiffre de backtest pour expliquer un
comportement de prod qui tourne sur de tout autres réglages.

> **Source de la colonne PROD** : lecture EN DIRECT d'Atlas le **2026-08-27**, après
> l'application des réglages testés. Le fichier `backend/_prod_settings.json` reste
> l'instantané du 2026-08-25 — il ne décrit plus la prod, il ne sert qu'à rejouer la
> campagne à l'identique. Relire Atlas avant toute décision qui en dépend.
>
> ⚠️ **Cette colonne a été FAUSSE sur deux points jusqu'au 2026-08-27** : elle annonçait
> « confluences toutes OFF » alors que `require_second_choch` était **ON** dans le snapshot
> du 25, et que `require_daily_bias` avait été activé en prod entre le 25 et le 27. La
> campagne les forçait toutes à OFF (`_matrix2.base_settings`), ce qui a masqué l'écart :
> **le backtest « pile de prod » (PF 0,86) ne modélisait donc pas exactement ce qui
> tournait.** La conclusion ne change pas — c'est la pile d'étages qui perd — mais ne plus
> présenter ce chiffre comme la mesure fidèle de la prod d'alors.

| Réglage | Défaut du code (`backend/models.py`) | PROD (snapshot 2026-08-25) | Validé en BACKTEST (2026-08-26) |
|---|---|---|---|
| **Mode** | intraday | **intraday** ✅ | **intraday** |
| **Étages** | D1→H1→M15→M5 | **D1→H1→M15→M1** ✅ | **D1→H1→M15→M5** (M1 pour la pile A) |
| RR minimum | 2,0 | **1,0** | **1,0** (hérité du snapshot de prod, jamais surchargé par `_matrix2.py`) |
| **TP partiels** | activés | **activés** ✅ | **activés** |
| Session Londres | 08:00–11:00 | **08:00–17:00** ✅ | **08:00–17:00** (heure locale) |
| Session New York | 08:00–11:00 | **08:00–17:00** ✅ | **08:00–17:00** (heure locale) |
| Trades / jour | 5 | **illimité** ✅ | **illimité** |
| Spread simulé | 25 points | 25 points | **16 points** (spread réel du compte Axi) |
| Capital de départ | solde réel du compte | — | solde réel |
| Risque / trade | 1 % | 1 % | 1 % |
| Pertes consécutives | arrêt à 3 (même session) | arrêt à 3 | arrêt à 3 |
| Drawdown max | 3 % | 3 % | 3 % |
| `swing_method` / `ob_zone` | two_candle / wick | two_candle / wick | two_candle / wick |
| `sl_mode` / `ob_entry_mode` / `tp_target` | poi / close / range_bound | poi / close / range_bound | poi / close / range_bound |
| Confluences | toutes OFF | **`require_unmitigated_ob` seule** ✅ | toutes OFF (référence) |
| Filtre news | activé | activé | **non modélisé** |

✅ **Depuis le 2026-08-27, la prod et la configuration mesurée coïncident** (les ✅ de la
table). Ce paragraphe alertait auparavant sur un écart béant — il est résorbé. Les chiffres
de la pile A + OB non mitigé (PF 1,21, 576 trades) décrivent donc bien, pour la première
fois, ce que ferait la prod dans son état actuel — aux réserves habituelles près :
commissions, slippage, exécution partielle et filtre news ne sont pas modélisés, et
l'avantage du filtre lui-même n'est pas démontré (§0ter).

Deux points à garder en tête :

- Les clés `scalping_*` **restent en base** (`H1 / M5 / M1 / M1`) mais **ne sont plus lues**
  depuis le passage en `trading_mode = "intraday"` : le moteur choisit la famille de clés
  selon le mode (`backtest.py:163`). Elles ne sont pas effacées — elles redeviendraient
  actives instantanément si quelqu'un rebasculait le mode en scalping. **C'est la pile
  mesurée perdante ; ne pas rebasculer le mode sans refaire la mesure.**
- `account_type = "real"` avec `real_confirmed = true` : **libellé trompeur**, ce n'est PAS
  de l'argent réel. C'est le token/accountId MetaApi qui détermine le compte utilisé, et
  c'est un compte **démo** chez le broker Axi. Ne pas s'en alarmer, ne pas non plus le
  « corriger » sans demander.

### 0ter. Acquis de la campagne — ne pas re-tester

Ces résultats sont établis sur trois périodes indépendantes de M1 XAUUSD réelles. Les
rejouer coûte des heures pour rien. Le raisonnement complet est dans `DECISIONS.md`
(entrées du 2026-08-26 et du 2026-08-27).

🔴 **RÈGLE DE LECTURE DE TOUTE CETTE SECTION, posée le 2026-08-27.** Un écart de profit
factor entre deux variantes ne vaut RIEN sans sa marge d'erreur. Mesuré : **sur les 46
variantes de la campagne, ZÉRO n'atteint |t| ≥ 2 contre la référence** (le hasard seul en
aurait produit ~2,3), et le tri « bat la référence sur 3 périodes » n'a laissé passer que
**8 variantes sur 16, soit 50 % — le taux d'une pièce de monnaie**. Les écarts ci-dessous
indiquent donc des **tendances, pas des faits établis**. Deux seuls résultats passent le
seuil des 2 : **la pile de prod est perdante** (t −2,85) et **la pile A bat la pile de
prod** (t +2,17 ; +2,89 avec l'OB non mitigé). Tout le reste est indicatif.
Deux questions à ne jamais confondre : « cette config gagne-t-elle ? » (t sur le gain
moyen) et « est-elle meilleure que sa référence ? » (t sur l'ÉCART). La seconde n'avait
jamais été calculée avant le 2026-08-27.

- **Dégradent la performance partout** : OTE (PF 0,71 — le plus destructeur), inducement
  pris (0,79), FVG obligatoire (0,82), Rejection block (0,90), séquence sweep→CHoCH
  imposée (0,94).
- **Power of 3 : question du seuil tranchée.** Testé à 0,20 / 0,35 / 0,50 — aucun n'aide.
  Ce n'est pas un problème de calibrage, le filtre n'apporte rien sur l'or (ses 97,75 %
  viennent d'indices, pas du métal).
- **Le filtre premium/discount se justifie** : le retirer coûte 0,03 à 0,04 de PF.
- **TP partiels vs TP unique** : winrate 49 % contre 32 %, PF identique. Ils lissent la
  courbe, ils n'ajoutent pas d'espérance.
- **`sl_mode="protected"` écarté** : +0,03 / +0,09 / −0,26 selon la période. N'ajoute rien
  à l'OB non mitigé, qui suffit seul.
- **Piège documenté — `ob_entry_mode="zone_50"`** finissait n° 1 de la période d'étude
  (PF 1,43, t +2,06) et fait **0,72** hors échantillon. Sans le découpage en périodes,
  cette configuration serait partie en prod. C'est la raison d'être de la règle
  « plusieurs périodes ou rien ». ⚠️ **Ce t +2,06 a longtemps été présenté comme « le seul
  résultat significatif de la matrice » — c'est faux, et c'est exactement la confusion
  (a)/(b) du chapeau** : il mesure la RENTABILITÉ de la variante, pas sa supériorité sur
  la référence, qui vaut t +1,59 (non significative). Contrôlé le 2026-08-27 : sa chute
  hors échantillon n'est pas significative non plus (t −0,87). La leçon opérationnelle
  tient — **ne pas utiliser `zone_50`** — mais pour la bonne raison : rien n'a jamais
  démontré qu'il apportait quoi que ce soit.
- **RR minimum : testé le 2026-08-26, ne donne aucune règle fiable.** Balayage 1 / 1,5 / 2 / 3,
  avec et sans `require_unmitigated_ob`, sur les trois périodes (24 runs). Monter le RR
  améliore les deux périodes anciennes et **dégrade régulièrement la période hors
  échantillon** (famille OB non mitigé : 1,58 → 1,42 → 1,19 → 1,05 quand le RR passe de 1
  à 3 ; référence seule à RR 3 : 0,73 hors échantillon contre 1,13 et 1,18 ailleurs).
  **`RR 2 + OB non mitigé` est un second piège de type `zone_50`** : meilleure ligne du
  tableau (PF cumulé 1,25, t +1,85 — le t le plus élevé obtenu à ce jour, DD 8,2 % contre
  12,1 %) mais **2/3 périodes seulement**, l'échec portant sur la période hors échantillon.
  Seuls `RR 1` et `RR 1,5` combinés à l'OB non mitigé tiennent 3/3 — c'est-à-dire la
  configuration déjà recommandée. **Le RR de 1 enregistré en prod n'est donc pas un défaut
  à corriger.** ⚠️ **Relu le 2026-08-27 : la conclusion tient, le raisonnement était trop
  fort.** Aucune des comparaisons de RR n'atteint |t| = 2 (la plus forte : 1,26) — le RR
  ne « dégrade » pas la période hors échantillon, il n'y produit aucun effet mesurable. La
  bonne formulation est : **rien ne justifie de changer le RR**, ni à la hausse ni à la
  baisse. ⚠️ Réserve non levée : à RR 1, TP1 tombe sur la cible finale et l'échelle
  de TP partiels est écrasée ; ces runs ne séparent pas l'effet du RR de celui du retour
  d'une échelle de TP fonctionnelle. Un contrôle en `partial_tp_enabled=False` le
  trancherait.
- **Le filtre de session gagne sa place — 24h/24 est moins bon, sur les trois périodes.**
  Mesuré le 2026-08-26 sur la pile A + `require_unmitigated_ob`, un seul écart (les quatre
  horaires passés à 00:00–23:59, couverture vérifiée : 0 minute non couverte sur 1 440) :

  | | Trades | PF cumulé | P&L | Pire DD | t | Gain/trade |
  |---|---|---|---|---|---|---|
  | Sessions 08:00–17:00 | 576 | **1,21** | 3 148 $ | **11,9 %** | **+2,08** | **5,47 $** |
  | 24h/24 | 789 | 1,15 | 3 258 $ | 12,5 % | +1,78 | 4,13 $ |

  **PF plus bas sur 3/3 périodes** (−0,02 / −0,09 / −0,02) et **DD plus haut sur 3/3**
  (+0,6 / +4,2 / +0,7 pt), pour **+37 % de trades** et seulement **+3,5 % de P&L**. Le
  gain par trade tombe de 5,47 $ à 4,13 $ : les heures hors session diluent la qualité
  sans rien rapporter. **C'est le seul résultat de la journée où la période hors
  échantillon confirme les deux autres au lieu de les contredire** — donc le plus fiable.
  ⚠️ Le test est même FAVORABLE au 24 h : sans sessions distinctes, l'arrêt après 3 pertes
  dure jusqu'au lendemain (`resume_policy` compare `jour|session`, et l'étiquette est
  « londres » 1 439 minutes sur 1 440), ce qui protège la variante 24 h. Un vrai bot 24 h
  qui reprendrait plus tôt ferait probablement pire.
- **Ce qui décide, c'est le CONTEXTE au-dessus, pas la timeframe d'entrée.** Quatre piles
  mesurées le 2026-08-26 sur les trois périodes, tout le reste identique (réglages de la
  campagne). Deux critères distincts, à ne pas confondre : « rentable sur chaque période »
  (PF > 1) et « bat sa propre référence sur chaque période ».

  | Pile | Trades | PF cumulé | Pire DD | t | PF par période | Rentable |
  |---|---|---|---|---|---|---|
  | **A** `D1→H1→M15→M1` | 667 | 1,10 | 15,2 % | +1,10 | 1,04 / 1,09 / 1,25 | **3/3** |
  | **A + OB non mitigé** | 576 | **1,21** | **11,9 %** | **+2,08** | 1,08 / 1,33 / 1,12 | **3/3** |
  | B `H1→M15→M5→M1` | 1 035 | 1,02 | 24,0 % | +0,31 | 1,16 / 0,96 / 0,81 | 1/3 |
  | B + OB non mitigé | 1 001 | 1,04 | 23,0 % | +0,56 | 1,16 / 0,99 / 0,85 | 1/3 |
  | C `H1→M5→M1→M1` (prod) | 1 481 | 0,86 | 48,4 % | −2,85 | 0,87 / 0,90 / 0,71 | 0/3 |
  | M5 `D1→H1→M15→M5` | 488 | 1,02 | 12,8 % | +0,22 | 0,99 / 0,97 / 1,30 | 1/3 |
  | M5 + OB non mitigé | 447 | 1,18 | 12,1 % | +1,62 | 1,10 / 1,10 / 1,58 | 3/3 |

  ✅ **Seul duel de tout le projet à passer le seuil des 2 : la pile A contre la pile de
  prod (C)** — écart de +4,84 $/trade ± 2,23 $, **t +2,17** (et **+2,89** pour « A + OB non
  mitigé » contre C). Ces quatre piles ont été décidées d'avance, pas pêchées parmi 47
  candidates : pas de biais de sélection. C'est le résultat le plus solide du projet, et il
  confirme l'avertissement déjà présent dans `models.py` (« H1 = perdant, DD
  catastrophique »). **Scalper en M1 est viable — à condition de garder les quatre étages
  D1→H1→M15 au-dessus.**

  ⚠️ **Deux nuances ajoutées le 2026-08-27, l'ancienne rédaction allait trop loin :**
  (1) **la pile B n'est PAS démontrée perdante.** Contre la pile A elle donne t +0,67 —
  non significatif. L'échec est établi pour la pile de PROD (C), pas pour B.
  (2) **`require_unmitigated_ob` n'est ni ambigu ni acquis : il est non démontré.** Sa
  prétendue faiblesse « 2/3 en M1 » était du bruit (t −0,16 hors échantillon) — mais son
  avantage ne l'est pas davantage (t +0,97 en M1, +1,08 en M5). Le t de +2,08 de « A + OB
  non mitigé » mesure sa RENTABILITÉ, pas sa supériorité sur la référence.
- 🚨 **La pile d'étages enregistrée en PROD est PERDANTE sur les trois périodes.**
  Mesurée le 2026-08-26 (scalping `H1→M5→M1→M1`, tout le reste aux réglages de la
  campagne) : **PF 0,86 · 1 481 trades · −3 848 $ · t −2,85**, PF par période
  0,87 / 0,90 / 0,71, pire drawdown cumulé **48 %**. Avec `require_unmitigated_ob` elle
  remonte à 0,97 — toujours perdante, DD 31 %. **C'est le résultat le plus significatif
  jamais obtenu sur ce projet, et il est négatif** : |t| = 2,85 dépasse le seuil de 2 que
  les configurations gagnantes n'atteignent pas. En prod, `scalping_mtf` et `scalping_ltf`
  valent tous deux M1 : structure et déclencheur sur la même bougie, ce n'est pas
  l'analyse à quatre étages du §3. **Ne pas démarrer le bot sur cette configuration.**
- **Entrée M1 avec un vrai contexte à quatre étages** (`D1→H1→M15→M1`, variante « A ») :
  PF 1,10 seule (667 trades, t +1,10) et **PF 1,21 avec `require_unmitigated_ob`
  (576 trades, t +2,08)**. Rentabilité régulière, vérifiée le 2026-08-27 : **10 mois
  gagnants sur 14**, et encore **+1 250 $ sur 459 trades** en retirant les trois meilleurs
  mois. Ce n'est pas un coup de chance concentré.
- ✅ **L'« inversion » de la période juin→août 2026 n'existe pas** (mesuré le 2026-08-27,
  sans relancer un backtest). Les trois effets qu'on croyait inversés — le RR, `zone_50`,
  le passage M5→M1 — donnent **18 comparaisons dont AUCUNE n'atteint |t| = 2** (la plus
  forte : 1,33). Hors échantillon, l'écart référence ↔ OB non mitigé vaut −1,85 $/trade
  **± 11,71 $** : le vrai effet peut valoir −25 $ comme +21 $. La période n'est pas
  « à l'envers », elle ne compte que **79 trades**. Et son régime n'est pas aberrant :
  amplitude quotidienne **2,07 %**, ENTRE `2025h2` (1,54 %) et `etude` (2,49 %) — c'est
  `2025h2`, marché calme et tendanciel, qui est l'exception. **Ne pas rouvrir ce sujet.**
- ⚠️ **Deux variantes ne comparent jamais les mêmes trades** (mesuré le 2026-08-27) :
  entre la référence et l'OB non mitigé, le recouvrement n'est que de **52 à 66 %**. Un
  filtre ne peut que RETIRER des trades, pourtant il en APPARAÎT (110 coupés / 81 apparus
  sur `2025h2`, 157/106 sur `etude`, 31/20 sur `oos`) : bloquer un trade libère le créneau
  pour le suivant, puisqu'on ne tient qu'une position à la fois. Tout écart mesuré entre
  deux variantes contient donc un **rebrassage de la moitié du portefeuille** en plus de
  l'effet cherché. Ce n'est pas un bug — c'est le comportement réel du bot — mais ça
  interdit de lire un petit écart comme « l'effet du filtre ».
- **Piège de lecture du drawdown** : `max_drawdown_pct` (3 % par défaut) est un
  coupe-circuit **JOURNALIER**, comparé à l'équité de début de journée
  (`backtest.py:130-132`), avec reprise à la session suivante. Un DD cumulé de 30 à 48 %
  est donc parfaitement compatible avec un réglage à 3 %. Ne jamais présenter le réglage
  comme une limite de perte totale.
- ⚠️ **Tout chiffre de backtest produit avant le 2026-08-26 est optimiste** et ne doit plus
  être cité : le moteur lisait le futur (cf. §9). Cela inclut les comparaisons du
  2026-07-28 et la première matrice de 40 variantes.
- **Non modélisé dans tous ces chiffres** : commissions, slippage, exécution partielle,
  filtre news.

---

## 1. Vision du projet

Application web de **trading 100% automatique** sur **MetaTrader 5**, basée sur la stratégie **Smart Money Concepts (SMC)**. Développée initialement avec Emergent, code sur GitHub : `davos972/SMC-Claude-Code-2` (branche `main`) — backend FastAPI/Python + frontend React, base MongoDB.

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
> **« Synthèse stratégie V3 »** fournis par David. **Les deux documents sont dans le
> dépôt** depuis le 2026-08-26 : `docs/Manuel_Detection_SMC.docx` et
> `docs/Strategie_SMC_Synthese_V3.docx`, avec une conversion Markdown lisible et
> cherchable à côté (`docs/README.md` explique le plan des deux, la correspondance des
> numéros de section, et les écarts assumés entre le document et le code).
> Toute règle citée « Manuel §x » ou « Synthèse V3 §y » est donc vérifiable à la source.
> Toute méthode antérieure reste accessible en réglage pour être comparée en backtest.

- **Analyse top-down 4 étages** : contexte journalier (D1) → biais (HTF) → structure/POI (MTF) → déclencheur (LTF). L'étage journalier est un ENRICHISSEMENT : le désactiver (`intraday_d1=""`) ramène exactement à l'analyse 3 niveaux d'avant
- **Deux modes** (un seul actif) : Intraday D1→H1→M15→M5 et Scalping H1→M15→M5→M1, tous paramétrables
- **Swing high/low** : **règle des deux bougies** par défaut (`swing_method`) — un sommet est validé après 2 bougies baissières consécutives. La comparaison est `>=`, donc les **sommets ÉGAUX (doubles sommets) sont détectés**, ce que la fractale stricte manquait. Fractale N bougies toujours disponible
- **Biais haute timeframe** : structure de marché (HH/HL, LH/LL), BOS (continuation), CHoCH (retournement). Cassure sur clôture (défaut) ou sur mèche (`structure_break_mode`)
- **Liquidité BSL/SSL** : les sommets ALIGNÉS forment un seul réservoir, d'autant plus gros qu'il a été testé souvent. Niveaux **protégés** (creux en tendance haussière) vs **cibles**. Peuvent inclure PDH/PDL et les bornes du range asiatique
- **Zones d'intérêt** : order blocks (**tracés mèches comprises**, `ob_zone`), FVG, IFVG, BPR, Breaker, Mitigation et Rejection Blocks, sweeps, premium/discount, OTE 62-79%. Les zones acceptées comme POI se choisissent dans `poi_source`
- **Inducement** : le piège à stops juste avant la POI, détecté et affiché
- **Entrée basse timeframe** valide si : biais clair + retour dans une POI bien placée + sweep ou CHoCH LTF + RR minimum atteignable. Confluences supplémentaires toutes **OFF par défaut** (displacement, second CHOCH, inducement pris, OTE, Daily Bias, Power of 3)
- **Le « noyau »** — ce que le moteur exige TOUJOURS, quels que soient les réglages
  optionnels. C'est la configuration de référence des backtests, celle dont on dit qu'elle
  est « à l'équilibre » (§0). Six conditions, dans l'ordre où `smc.analyze()` les évalue :
  1. un **biais HTF** exploitable et un **range défini** (sinon rejet `no_bias`) ;
  2. une **POI dans le sens du biais** sur l'étage structure — un order block par défaut
     (sinon rejet `no_poi`) ;
  3. le **prix revenu dans cette POI** (`ob_entry_mode="close"` par défaut) ;
  4. un **déclencheur sur la timeframe d'entrée** : un sweep **OU** un CHoCH récent
     (`backend/smc.py:1207`) ;
  5. le **filtre premium/discount** respecté — acheter en discount, vendre en premium
     (`require_premium_discount`, **le seul `require_*` activé par défaut**, `smc.py:1152`) ;
  6. un **RR atteignable ≥ `min_rr`** (`smc.py:1308`).

  Tout le reste (`require_fvg_entry`, `require_sweep_then_choch`, `require_unmitigated_ob`,
  `require_daily_bias`, `require_po3`, `require_ote`, `require_displacement`,
  `require_inducement_swept`, `require_second_choch`) est une **confluence**, OFF par défaut.
- **Règle de méthode (Synthèse V3 §10)** : noyau + **1 à 3 confluences maximum**. Ne JAMAIS tout activer en même temps — « cet empilement ne se produit quasiment jamais et paralyse l'exécution ». Chaque variable se teste SÉPARÉMENT en backtest
- **Analyse à la clôture de bougie** de la timeframe d'entrée (pas tick par tick)
- **Sessions strictes** : trading UNIQUEMENT pendant Londres et New York, heures LOCALES de chaque place, heure d'été gérée via pytz (`backend/sessions.py`). Les positions ouvertes restent ouvertes après la session (protégées par SL/TP broker). ⚠️ Trois valeurs coexistent pour ces horaires — **voir le tableau du §0bis avant de citer un chiffre**

## 4. Gestion du risque (tout paramétrable dans Réglages)

- Risque par trade 0,25–2% (défaut 1%), lot calculé selon la distance du SL
- SL structurel (sous/sur l'order block ou le sweep), TP sur la liquidité opposée, RR minimum (défaut 1:2) sinon trade ignoré
- **Arrêt auto après 3 pertes consécutives** dans la MÊME session (break-even ne compte pas) — reprise paramétrable : prochaine session (défaut) ou lendemain
- **Arrêt auto sur drawdown max** (défaut 3%) — même politique de reprise
- **Trades par jour** : trois valeurs coexistent (§0bis). Une seule position par symbole. Le vrai garde-fou est l'arrêt après 3 pertes consécutives, pas le plafond journalier — David a demandé le 2026-08-26 que le bot puisse prendre toutes les occasions
- **Mode prop firm** activable (défauts calés BlueGuardian Instant Funding : DD jour/total, Guardian Shield, reset 17h EST, high watermark trailing ; marge de sécurité 20% — s'arrête AVANT les limites réelles ; paramétrable pour d'autres firmes)
- **Filtre news** : pause 30 min avant/après les annonces USD à fort impact (flux Forex Factory / faireconomy, `backend/news.py`). **Non modélisé en backtest**
- ~~Mode « Signal uniquement »~~ : **retiré le 2026-08-25** (David trade sur compte démo Axi, où il n'apportait rien). Un setup validé part toujours à l'exécution. Le verrou du compte réel (`account_type` + double confirmation `real_confirmed`) est indépendant et reste en place
- **Trailing stop** : implémenté (logique unique `compute_trailing_sl` partagée live + backtest ; modes breakeven / r_trail / structure), **OFF par défaut**
- **TP partiels TP1/TP2/TP3** : implémentés et **ACTIVÉS PAR DÉFAUT** depuis le 2026-08-25. Échelle unique `compute_tp_ladder` partagée live + backtest. TP1 à 1R ferme 50% et remonte le SL à l'entrée, TP2 (mi-chemin TP1↔TP3) ferme 30%, les 20% restants courent jusqu'à la cible. C'est la gestion de position décrite par la stratégie, pas une option. Le SL et le TP FINAL restent posés chez le broker : si l'app s'arrête, la position reste protégée. `partial_tp_enabled=False` rétablit le TP unique historique pour comparer en backtest

## 5. Fonctionnalités de l'app

- **Dashboard** : bouton START/STOP manuel rond + rail des sessions 24h avec marqueur « maintenant », solde/équité/P&L jour, graphique avec zones SMC, positions ouvertes avec clôture d'urgence, journal des signaux (y compris setups REJETÉS avec la raison), annonces éco du jour
- **Backtest** (simple) : config actuelle sur période choisie, données M1 MetaApi, spread simulé paramétrable, rapport (winrate, profit factor, RR, DD max, courbe d'équité, liste des trades cliquables sur le graphique), avertissement performances passées. Le backtest part du **solde réel du compte** lu chez le broker (10 000 $ uniquement en mode dégradé). ⚠️ La limite « **max 6 mois** » (`backend/server.py:767`) est une limite de l'**API de l'app** ; les scripts `_*` appellent le moteur directement et ne l'ont pas — c'est ainsi que la campagne a tourné sur 8 mois
- **Journal de trading** (onglet « Stats ») : les trades RÉELS du bot, stockés dans la
  collection Mongo `trades` (écrite par `bot_loop` à l'ouverture puis à la clôture, avec
  le P&L réel du broker). P&L global, nb de trades, winrate, profit factor, drawdown max,
  courbe d'évolution vs capital de départ (réglage `journal_initial_balance`, 0 = déduit
  du solde), et le détail de chaque trade : jour/heure, RR prévu, TP ou SL touché, SL
  suiveur, et les **réglages qui différaient des défauts** au moment du trade. Endpoints
  `GET /api/journal` et `POST /api/journal/import` (import de l'historique broker MetaApi,
  filtré sur le magic number). Métriques calculées par `backtest._compute_metrics` —
  ne jamais en écrire une seconde version
- **Le texte d'un signal décrit ce qui s'est vraiment produit** (`smc._signal_reason`,
  depuis le 2026-08-26) : déclencheur réel, présence ou non d'une FVG, type de POI et son
  état mitigé, mode d'entrée, zone premium/discount déduite du prix. Ne jamais y remettre
  un libellé décoratif figé — David lit ce journal pour comprendre le bot
- **Notifications** : in-app (cloche + historique) + push navigateur (Web Push), chaque événement activable
- **Réglages — allégée le 2026-08-27.** L'écran ne montre plus que ce que David peut avoir
  à changer. En tête, un bloc **« Configuration validée » en LECTURE SEULE** qui affiche la
  configuration réellement enregistrée (mode, étages, filtre, sessions, RR, risque, TP,
  limites) et **passe en rouge dès qu'un réglage s'écarte** de celle mesurée en backtest —
  c'est le garde-fou anti-dérive. Restent modifiables : connexion MetaApi, confluences de
  la Stratégie SMC, contexte journalier, TP échelonnés, trailing, risque, filtre news,
  prop firm, notifications. **Retirés de l'écran** (les valeurs restent en base, inchangées,
  et le backend les accepte toujours) : URL serveur + clé API (déplacées en bas dans un
  bloc replié « Dépannage » — **ne jamais les supprimer**, sans elles une APK réinstallée
  ne peut plus joindre le serveur), sélecteur démo/réel, mode de trading, réglage des
  quatre étages, méthodes de détection, liquidité et zones, sessions, trades par jour.
  Le token MetaApi reste masqué et n'est jamais exposé au frontend

## 6. Spécifications visuelles (à respecter strictement)

- Mobile-first, colonne unique max 480px, navigation par onglets en bas (Dashboard/Backtest/Stats/Réglages), mode sombre
- Palette : fond `#0D1117`, panneaux `#151B24`, bordures `#242E3D`, accent or `#E3B341`, vert `#3FB68B`, rouge `#E0635E`, texte `#E9ECF2` / `#8A94A6`. Chiffres en monospace tabulaire
- **Zones SMC sur le graphique** — spécifié ET **implémenté** dans
  `frontend/src/components/SMCChart.jsx` (vérifié le 2026-08-26, inutile de re-auditer) :
  - FVG : rectangle à **bordure continue**, fond semi-transparent **vert (haussier) / rouge (baissier)**
  - Order block : rectangle à **bordure jaune pointillée**, fond jaune léger
  - Liquidity sweep : **flèche rouge** pointant la mèche + label « Sweep »
  - BOS/CHoCH : **ligne horizontale bleue pointillée** + label « BOS ↑/↓ » ou « CHoCH ↑/↓ »
  - Les zones s'étendent à droite jusqu'à mitigation, puis disparaissent ou passent en opacité réduite. Légende sous le graphique
- **Calques (depuis 2026-08-25)** : les zones ajoutées (BSL/SSL, inducement, range asiatique, OTE, IFVG, BPR, Breaker/Mitigation/Rejection) s'affichent par calques activables, **tous OFF par défaut**. Sur une colonne de 480px, tout afficher rend le graphique illisible — et c'est exactement ce que la Synthèse V3 §10 reproche. Le choix est mémorisé par appareil (localStorage). La légende suit les calques actifs

## 6bis. Déploiement réel et app mobile

- **La prod tourne sur Render** : `goldflow-backend` (+ `goldflow-frontend` statique), auto-déployée à chaque push GitHub `main`. Base : **MongoDB Atlas** (`cluster0.lfishca…`, base `goldflow`) — c'est LA mémoire vivante ; un Mongo local ne sert qu'aux tests. ⚠️ Ne jamais lancer un backend local pointé sur Atlas pendant que Render tourne : l'auto-reprise ferait courir DEUX bots sur le même compte.
- **App mobile Android** : Capacitor (`frontend/android/`, appId `com.goldflow.smc`), APK compilé par GitHub Actions (`.github/workflows/android-apk.yml`, « Run workflow », artifact `goldflow-smc-apk`). Signature permanente : le nouvel APK s'installe par-dessus l'ancien sans désinstaller. URL backend modifiable par appareil (Réglages → Serveur). `CORS_ORIGINS` sur Render doit contenir `https://localhost` (origine Capacitor).
- **Notifications push app fermée** : Firebase FCM (`backend/push.py`), clé de service dans l'env `FIREBASE_SERVICE_ACCOUNT` (Render/`.env`, JAMAIS dans Git — `google-services.json` versionné est OK, c'est une config client). Endpoints `/api/push/register` et `/api/push/test`. Toute notification in-app part aussi en push.
- **Clé API (audit 2026-07-09)** : définir `API_KEY` dans Render → toute requête `/api` (sauf `/` et `/health`) exige le header `X-API-Key`. La clé se saisit dans l'app : Réglages → Serveur → Clé API (stockée par appareil). Sans `API_KEY` définie, l'auth est désactivée (ordre de déploiement sûr : pousser le code, puis créer la clé, puis la saisir dans l'app).

## 7. Historique — où aller chercher le « pourquoi »

L'état courant est en §0. Cette section ne garde que les repères de navigation : le récit
complet est dans `DECISIONS.md`, entrée par entrée, la plus récente en haut.

| Date | Ce qui s'est joué | Entrée dans DECISIONS.md |
|---|---|---|
| 2026-08-27 | La page Réglages ne montre plus que ce qui se décide encore | « La page Réglages » |
| 2026-08-27 | **Réglages testés appliqués en prod ; le bot tournait à notre insu** | « Application des réglages testés » |
| 2026-08-27 | **Les trois périodes ne suffisent pas : il manquait la marge d'erreur** | « La règle des trois périodes ne suffit pas » |
| 2026-08-26 | **La pile d'étages décide de tout ; la config de prod est perdante** | « La pile d'étages décide de tout » |
| 2026-08-26 | Documentation : un rôle par fichier, §0 « État courant » | « Documentation : un rôle par fichier » |
| 2026-08-26 | Troisième période de backtest : le SL protégé sort, l'OB non mitigé confirme | « Troisième période » |
| 2026-08-26 | Campagne sur moteur corrigé, règle du hors échantillon | « Campagne de backtests sur moteur corrigé » |
| 2026-08-26 | Le texte d'un signal décrit ce qui s'est vraiment produit | « La raison d'un signal » |
| 2026-08-26 | **Le backtest lisait le futur** — correctif majeur, invalide les chiffres antérieurs | « Le backtest lisait le futur » |
| 2026-08-25 | Alignement du moteur sur le Manuel de détection et la Synthèse V3 (15 décisions B1–B6 / D1–D9) | « Alignement du moteur » |
| 2026-08-25 | Retrait du mode « Signal uniquement » | « Retrait du mode Signal uniquement » |
| 2026-08-19 | Journal de trading : les trades réels persistés (collection `trades`) | « Journal de trading » |
| 2026-08-10 | Pertes consécutives comptées PAR SESSION | « Pertes consécutives » |
| 2026-07-09 | Audit : clé API sur l'API publique | « Audit complet » |
| 2026-07-08 | App mobile Capacitor + watchdog de la boucle bot | deux entrées |

**Anciens problèmes résolus, à ne pas rouvrir** : l'échec de connexion MetaApi de juillet
(`.env` local pointé sur un Mongo vide — résolu le 2026-07-08) ; les timeouts trop courts
(portés à 240 s, `backend/metaapi_client.py`) ; le timeout axios global de 30 s (instance
`apiLong` à 5 min, `frontend/src/api/client.js`) ; la fiabilisation du backtest
(progression, annulation, timeout global, reprise des backtests orphelins au démarrage).
Le seul reliquat de cette série est en §0, point 5.

## 8. Backtest — protocole obligatoire, outillage, plan d'expériences

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
   Le tableau du §0bis est le point de départ de cette liste.
3. **Rappeler les écarts** entre ces réglages et ceux réellement enregistrés en prod
   (colonne PROD du §0bis), pour qu'il sache ce qui est testé vs ce qui tourne.
4. À la restitution : dire quel moteur (commit) a produit les chiffres, et ce qui n'est
   pas modélisé (commissions, slippage, exécution partielle, filtre news).
5. **Ne JAMAIS modifier `smc.py`/`backtest.py` pendant qu'une matrice de backtests
   tourne.** Chaque backtest est un processus séparé qui importe le moteur à son
   démarrage : une édition en cours de route fait planter ceux qui démarrent pendant
   la fenêtre d'incohérence (vécu le 2026-08-26 : 8 runs perdus sur un `NameError`),
   et pire, ceux qui passent tournent avec une version différente des autres.

### Règle de validation : plusieurs périodes ET la marge d'erreur

**Deux conditions, pas une seule.** Depuis le 2026-08-27, une règle ne compte que si :

1. elle bat la référence sur **toutes** les périodes testées, pas seulement sur celle qui
   a servi à la choisir ; **et**
2. **l'écart dépasse sa propre marge d'erreur** — écart de gain moyen par trade et son `t`
   (Welch), pas deux profit factors mis côte à côte.

⚠️ **La condition 1 seule ne trie pas mieux que pile ou face** : sur la campagne, 8 des
16 variantes portées jusqu'au hors échantillon ont tenu 3/3, soit exactement 50 %, et
**aucune des 46 variantes n'atteignait |t| ≥ 2** contre la référence (le hasard seul en
aurait produit ~2,3). Elle reste le premier filtre — elle a écarté `zone_50` avant la
production — mais publier un écart sans sa marge d'erreur a coûté une journée entière de
conclusions à refaire (`DECISIONS.md`, 2026-08-27).

**Ordre de grandeur à avoir en tête avant de lancer quoi que ce soit** : avec ~40 trades
par mois et un écart-type de ~60 $ par trade, départager deux variantes proches demande
**plus de 2 000 trades**. Une variable qui ne change le gain moyen que de 2 à 3 $ par
trade **n'est pas mesurable** sur les données disponibles, ni en backtest, ni en démo.
Le savoir avant évite de lancer des campagnes qui ne peuvent rien prouver.

Trois périodes sont en place :

| Nom | Période | Régime de marché |
|---|---|---|
| `2025h2` | juil. → déc. 2025 | forte tendance haussière (3 311 → 4 311 $) |
| `etude` | 15 déc. 2025 → 12 juin 2026 | période d'étude d'origine |
| `oos` | 12 juin → 26 août 2026 | hors échantillon, téléchargée après coup |

Une période supplémentaire coûte ~30 minutes de calcul et évite un mauvais réglage en
production (cf. le piège `zone_50` en §0ter).

### Outillage en place dans `backend/` (fichiers `_*`, hors Git — voir §11)

- **Caches M1 XAUUSD de la campagne** — les seuls à conserver absolument :
  `_m1_cache_XAUUSD_2025-05-01_2026-01-01.json` (238 257 bougies, mai-juin en chauffe),
  `_m1_cache_XAUUSD_2025-12-15_2026-06-12.json`,
  `_m1_cache_XAUUSD_2026-06-12_2026-08-26.json`
- `_prod_settings.json` : instantané des réglages Atlas du 2026-08-25 (sans secrets)
- `_matrix2.py` (47 variantes + réglages de la campagne), `_period.py` (rejeu sur une
  période nommée avec bougies de chauffe), `_run_matrix2.py` / `_run_period.py` (lancement
  parallèle), `_report2.py` (tableau), `_fetch_m1.py` (téléchargement d'un cache)
- Résultats bruts : `backend/_matrix2_out/_m2_<periode>_<entree>_<dd>_<variante>.json`
- Les autres `_*` (caches mensuels de 2026, US30, USTECH, `_old_smc.py`, `_old_backtest.py`,
  `_compare_*`, `_trailing_*`) sont des reliquats d'expériences antérieures au moteur
  corrigé : sans valeur, supprimables.

**Pour relancer une comparaison** (depuis `backend/`) :
```powershell
py _run_period.py 2025h2 --workers 8          # les 47 variantes sur juil.-déc. 2025
py _report2.py --entry m5 --data 2025h2 --dd on
```

### Plan d'expériences — tester chaque variable SÉPARÉMENT (Synthèse V3 §11)

Tout ce qui a été ajouté le 2026-08-25 est désactivé par défaut. La méthode pour décider
quoi garder — jamais en bloc. Les lignes déjà tranchées sont marquées ; voir §0ter.

| Variable | Options à comparer une par une |
|---|---|
| Détection des swings | `swing_method` : two_candle vs fractal |
| Tracé de l'OB | `ob_zone` : wick vs body |
| Cible du TP | `tp_target` : range_bound vs liquidity vs nearest_swing |
| Placement du SL | `sl_mode` : poi vs protected — **tranché : poi** |
| Mode d'entrée | `ob_entry_mode` : close vs zone_50 vs tap — **tranché : close** |
| Type de zone POI | `poi_source` : ob, bpr, breaker, mitigation, rejection (un seul à la fois) |
| Confluences | displacement, second CHOCH, inducement pris, OTE, Daily Bias, PO3 (une à la fois) — **tranché : OTE, inducement, PO3 écartés** |
| Gestion | `partial_tp_enabled` : TP unique vs TP1/TP2/TP3 — **tranché : sans effet sur l'espérance** |
| Liquidité | `use_pdh_pdl_liquidity`, `use_asia_liquidity` |

Le backtest accepte ces clés **directement dans la requête**, ce qui permet de comparer
deux méthodes sans rien changer dans les Réglages de l'app.

⚠️ Les chiffres de la Synthèse V3 (68% Daily Bias, 97,75% Power of 3) viennent de
GER40 et d'indices, **pas de l'or**. Ils ne se transfèrent pas automatiquement à XAUUSD —
c'est vérifié, pas supposé (§0ter).

### Puis : valider en démo

Un bon backtest n'est pas une preuve. Toute configuration retenue tourne sur le compte
démo Axi pendant plusieurs jours avant qu'on en tire une conclusion.

## 9. Garde-fous pour Claude Code

- **L'état du bot se lit dans `bot_state.running`, JAMAIS dans `settings.bot_running`** —
  ce dernier est un champ mort (`models.py:200`, lu par aucun code). S'y fier a fait
  documenter « bot à l'arrêt » pendant 34 h alors qu'il tradait (§0). Même règle pour
  toute affirmation sur la prod : la lire dans Atlas, pas dans un snapshot ni dans la doc
- **Ne jamais écrire dans les réglages Atlas pendant que `bot_state.running` est vrai** :
  changer le mode, les étages ou les sessions sous une boucle en vol la ferait décider sur
  une configuration à moitié appliquée, éventuellement avec une position ouverte. Arrêter
  d'abord, vérifier, puis écrire
- Ne jamais committer de token/secret ; `.env` reste hors Git
- Ne jamais simplifier la stratégie SMC vers des indicateurs classiques (moyennes mobiles, RSI)
- Ne jamais envoyer d'ordre sans SL/TP
- Ne pas activer le compte réel ni assouplir sa double confirmation
- **Ne changer aucun réglage de trading sans l'accord explicite de David** — y compris un
  réglage recommandé par un backtest. La décision lui appartient (§0)
- Préserver le mode dégradé explicite : si MetaApi n'est pas configuré/connecté, afficher l'erreur, jamais de données factices
- Ne pas affaiblir la protection par clé API (`API_KEY`/`X-API-Key`) ni élargir `_PUBLIC_PATHS` dans `server.py`
- **Une seule conversion réglages → moteur** : `smc.params_from_settings`. Les QUATRE appelants d'`analyze()` (bot live, backtest, analyse du dashboard, rejeu) doivent passer par elle. Sans ça, le graphique finit par afficher des zones tracées avec d'autres réglages que ceux qui décident des trades — c'est exactement ce qui était arrivé aux deux appels de `server.py`
- **Toute nouvelle règle SMC arrive DÉSACTIVÉE** : détectée et affichée, mais jamais imposée comme filtre tant qu'un backtest ne l'a pas validée (Synthèse V3 §10 et §11)
- **Jamais d'anticipation dans le backtest** : ne jamais pré-agréger une bougie EN COURS. La règle vaut pour les QUATRE étages, pas seulement le journalier. Elle a été violée jusqu'au 2026-08-26 : les fenêtres HTF/MTF/D1 étaient découpées avec `bisect_right` sur les temps de **début**, ce qui livrait la bougie supérieure en cours déjà agrégée avec son high/low/close définitifs (prouvé : en analysant la M1 de 16:47, le moteur voyait la M5 16:45→16:49 terminée). Toute bougie supérieure non clôturée doit être reconstruite depuis les bougies du niveau d'entrée écoulées (`backtest._partial_bar`). Test de non-régression : `backend/tests/test_backtest_lookahead.py`
- Journal de trading : ne JAMAIS combler un P&L manquant par une estimation. Si
  l'historique broker est indisponible, le trade est clôturé avec `result: "unknown"` et
  `pnl: null`, et il est exclu des statistiques (visible dans la liste, jamais compté)
- Le texte d'un signal ne doit décrire que des conditions **réellement constatées**
  (`smc._signal_reason`) — jamais un libellé figé qui suppose des filtres actifs

## 10. Environnement local et commandes (Windows 11, PowerShell)

- Backend : `cd backend` puis `py -m uvicorn server:app --reload --port 8000` — le frontend attend le backend sur `http://localhost:8000` (cf. `frontend/.env`, `REACT_APP_BACKEND_URL`). App FastAPI : `app` dans `server.py`. Dépendances : `py -m pip install -r requirements.txt` (Python 3.14 système, pas de venv dans ce dépôt)
- Frontend : `cd frontend` puis `npm start` (CRA + CRACO)
- ⚠️ **Sur un dépôt fraîchement cloné, `backend/.env` et `frontend/.env` N'EXISTENT PAS**
  (ils sont dans le `.gitignore`). Avant tout démarrage : `cp backend/.env.example backend/.env`
  et `cp frontend/.env.example frontend/.env`, puis renseigner au minimum `MONGO_URL`.
  Les deux fichiers `.env.example` sont commentés et listent toutes les variables
  (`MONGO_URL`, `DB_NAME`, `METAAPI_TOKEN`, `API_KEY`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`)
- Nécessite un MongoDB accessible ; sans MetaApi configuré, l'app démarre en mode dégradé — c'est normal et attendu

## 11. Convention : fichiers préfixés `_` dans `backend/`

Tous les fichiers `_*.py`, `_*.txt`, `_*.log`, `_m1_cache_*.json` sont des **scripts
d'expérimentation et des caches** : l'app ne les importe jamais, ils sont à ignorer en
revue de code, et le `.gitignore` couvre tout `backend/_*`. Ne jamais y placer de logique
dont l'app dépend.

⚠️ **« Hors Git » ne veut pas dire « jetable ».** Les trois caches M1 XAUUSD listés au §8
représentent des heures de téléchargement MetaApi et ne sont **pas** reconstituables
rapidement — ne pas les supprimer pour faire de la place. Le reste des `_*` l'est.

## 12. Tests — vérifié le 2026-08-26

**Tests unitaires — ni serveur, ni MongoDB, ni MetaApi. Rapides, à lancer en premier :**
```powershell
py -m pytest backend/tests/test_backtest_lookahead.py backend/tests/test_signal_reason.py -v
```
Attendu : **11 passed** (3 + 8). Le premier fichier vérifie que le backtest ne voit jamais
le futur (cf. §9), le second que le texte d'un signal décrit les conditions réelles.
C'est le modèle à suivre pour tout nouveau test du moteur : rapide, sans dépendance.

**`backend_test.py` est un test d'intégration : le backend doit tourner AVANT pytest.**
Il tape sur l'API HTTP (`http://localhost:8000/api`) et ne démarre pas le serveur
lui-même. Il s'exécute en **mode dégradé** (sans token MetaApi valide) — c'est voulu :
il vérifie que l'app refuse de simuler des données quand MetaApi n'est pas connecté.
Les chemins `/app/...` d'origine ont été remplacés par des chemins résolus depuis
`__file__`, et `REACT_APP_BACKEND_URL` est lu depuis `frontend/.env`.

Procédure exacte (deux terminaux PowerShell), depuis `SMC App/repo/` :

1. **Terminal A — démarrer le backend en mode dégradé, sur une base jetable.**
   Il faut vider `METAAPI_TOKEN`/`METAAPI_ACCOUNT_ID` (sinon le `.env` fournit un
   token et l'app démarre « configurée »), et utiliser une base de test dédiée
   (les tests écrivent en base ; ne pas polluer `goldflow`) :
   ```powershell
   cd backend
   py -c "import os; os.environ['METAAPI_TOKEN']=''; os.environ['METAAPI_ACCOUNT_ID']=''; os.environ['DB_NAME']='goldflow_test'; import uvicorn; uvicorn.run('server:app', host='127.0.0.1', port=8000)"
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
   Attendu : **25 passed**.

**Piège — variables d'environnement vides sous PowerShell (découvert 2026-08-10).**
`$env:METAAPI_TOKEN=""` SUPPRIME la variable au lieu de la vider → `load_dotenv()`
recharge alors le vrai token depuis `backend/.env` et le serveur démarre CONNECTÉ
à MetaApi (pas en mode dégradé). D'où le wrapper Python de l'étape 1, où une variable
vide existe réellement.

**Piège — base propre à chaque exécution.** Un test (`TestZTokenPreservation`) écrit
un faux token en base ; à la relance suivante le backend redémarre « configuré » et
2 tests échouent à tort. Pour rejouer proprement : soit repartir d'une base neuve
(changer `DB_NAME`, ex. `goldflow_test2`), soit supprimer la base de test avant de
relancer le backend. Ne jamais pointer les tests sur la base de production `goldflow`.

## 13. Traces à laisser (pour tout modèle qui travaille ici)

- **Fin de session** → mettre à jour le **§0** de ce fichier : commit de `main`, état du
  bot, décision en attente, chantiers ouverts. C'est la section que tout le monde lit en
  premier ; un §0 périmé fait perdre une demi-heure à chaque reprise
- Décision structurante prise en cours de tâche → entrée dans `DECISIONS.md` (décision, pourquoi, alternatives écartées) + une ligne dans le tableau du §7
- Piège découvert ou erreur corrigée → ligne dans ce fichier (§9 si c'est un garde-fou)
- Résultat de backtest établi sur plusieurs périodes → §0ter, pour que personne ne le rejoue
- **Ne pas dupliquer** : l'état va en §0, le pourquoi va dans `DECISIONS.md`, et
  `../REPRISE.md` ne fait que pointer vers les deux
- Les protocoles complets de travail sont dans les skills `/implementer` et `/revue`, et la méthode générale dans `../METHODE.md`
