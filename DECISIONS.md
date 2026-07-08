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
