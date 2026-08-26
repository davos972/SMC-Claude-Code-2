# Documents de référence de la stratégie SMC

Ces deux documents sont **la source de la stratégie** implémentée dans `backend/smc.py`.
Ils appartiennent à David et ont été versés au dépôt le **2026-08-26** : jusque-là, le
`CLAUDE.md` et le code s'y référaient une trentaine de fois (« Manuel §4.1 », « Synthèse
V3 §10 ») sans que personne d'autre puisse les consulter — donc sans qu'aucune règle du
moteur soit vérifiable à la source.

| Fichier | Contenu |
|---|---|
| `Manuel_Detection_SMC.docx` | **Manuel de détection** : comment reconnaître chaque objet SMC sur un graphique (définition, détection pas à pas, tracé, pièges) |
| `Strategie_SMC_Synthese_V3.docx` | **Synthèse stratégie V3** : la méthode d'exécution en 9 étapes, le noyau / les confluences / les variantes, et le plan de backtest |

## Le `.docx` fait foi, le `.md` est une commodité

Chaque document existe en deux formats :

- le **`.docx` original** — c'est lui qui fait autorité en cas de doute ;
- une **conversion Markdown** (`.md`) du même contenu, pour que le texte soit lisible et
  cherchable (`grep`) directement dans le dépôt, y compris par un modèle qui ne sait pas
  ouvrir un `.docx`.

La conversion est produite par `docx2md.py`, qui n'utilise que la bibliothèque standard
de Python (ni `pandoc` ni `python-docx` ne sont installés sur le PC de David) :

```powershell
py docs/docx2md.py docs/Manuel_Detection_SMC.docx docs/Manuel_Detection_SMC.md
py docs/docx2md.py docs/Strategie_SMC_Synthese_V3.docx docs/Strategie_SMC_Synthese_V3.md
```

**Si tu modifies un document, modifie le `.docx` puis régénère le `.md`** — jamais
l'inverse, sinon les deux divergent.

## Plan des deux documents

Les numéros de section ci-dessous sont ceux que citent `backend/smc.py`, `CLAUDE.md` et
`DECISIONS.md`. Ils ont été vérifiés un par un le 2026-08-26.

**Manuel de détection**
1. Structure & tendance (1.1 swings · 1.2 externe/interne · 1.3 CHOCH · 1.4 BOS)
2. Liquidité (2.1 BSL · 2.2 SSL · 2.3 Sweep · 2.4 Inducement)
3. Zones d'imbalance (3.1 FVG · 3.2 IFVG · 3.3 BPR)
4. Order Blocks (4.1 OB · 4.2 **OB 2.0** · 4.3 Breaker · 4.4 Mitigation · 4.5 Rejection)
5. Zones de prix (5.1 Premium/Discount · 5.2 OTE)
6. Repères temporels (6.1 Range asiatique · 6.2 **SMT Divergence**)
7. Tableau récapitulatif

**Synthèse stratégie V3**
1. Philosophie · 2. Architecture multi-timeframe
3. Le processus en 9 étapes (Étapes 1-5 analyse, 6-9 exécution)
4. Le setup complet · 5. Bibliothèque des concepts (5.1 à 5.8)
6. Les deux concepts validés par backtest · 7. Les 5 erreurs critiques
8. Quand NE PAS trader · 9. Checklist
10. **Noyau, confluences, variantes** — la règle « 1 à 3 confluences maximum »
11. Plan de backtest · 12. Résumé

## Ce que le code fait différemment, et pourquoi

Les documents décrivent la méthode idéale ; le moteur applique ce qui a été **validé en
backtest**. Deux écarts assumés, à ne pas « corriger » sans mesure :

- **Le noyau du §10 exige sweep ET CHOCH.** Le moteur exige sweep **OU** CHoCH
  (`backend/smc.py:1207`). Imposer la séquence sweep→CHoCH a été mesuré et dégrade les
  résultats (PF 0,94 contre 0,97 pour la référence) ; le réglage existe
  (`require_sweep_then_choch`) mais reste OFF. Voir `CLAUDE.md` §0ter.
- **OTE (Manuel §5.2)**, **inducement (§2.4)** et **Power of 3** sont détectés et
  affichés, mais jamais imposés comme filtres : mesurés sur XAUUSD, ils dégradent tous
  les résultats. Les statistiques citées dans la Synthèse V3 viennent de GER40 et
  d'indices, **pas de l'or**.

Règle générale : le document propose, le backtest dispose (`CLAUDE.md` §8 et §9).
