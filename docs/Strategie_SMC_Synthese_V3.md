**STRATÉGIE DE TRADING SMC / ICT**

*Synthèse complète & playbook exécutable*

**Version 3**

Document de référence bâti à partir des 29 vidéos de la playlist

Fusion des meilleurs éléments de deux synthèses (Claude + ChatGPT)

*Formateur : Jérémy Delsol (chaîne Admirals)*

> **⚠ Avertissement important** **Ce document est une synthèse structurée de la playlist, pas une preuve que chaque règle est profitable.** Les statistiques citées (68 %, 97,75 %) décrivent les backtests présentés dans les vidéos — ce ne sont PAS les performances de la stratégie finale. Seuls le Daily Bias et le Power of 3 journalier reposent sur un backtest à grande échelle. Tous les autres concepts sont illustrés par des exemples choisis et doivent être validés par votre propre backtest. Le trading comporte un risque de perte en capital. Ce document est éducatif, pas un conseil en investissement.

# **Table des matières**

# **1. Philosophie générale**

Le principe central de toute la playlist tient en une phrase : **on ne trade pas un concept SMC, on trade un scénario de marché.**

Un FVG, un Order Block, un BPR, un Rejection Block ou un Mitigation Block n'est jamais qu'une **zone d'intervention potentielle**. Ce sont le contexte, la liquidité et la structure qui déterminent si cette zone mérite d'être tradée. Le formateur le résume brutalement : « 90 % des traders SMC ne tradent pas la liquidité — ils *sont* la liquidité ».

**La séquence fondamentale**

> **CONTEXTE**

▼

> **LIQUIDITÉ**

▼

> **MANIPULATION**

▼

> **STRUCTURE**

▼

> **ZONE (POI)**

▼

> **RETEST**

▼

> **ENTRÉE**

▼

> **GESTION**

> **Réalité à garder en tête** Le trading SMC ne permet PAS de « trader comme les banques ». Il permet seulement de tenter de profiter d'une petite partie des mouvements générés par les institutionnels. Aucune stratégie n'atteint 100 % de réussite. Tout est un arbitrage entre taux de réussite et ratio risque/rendement.

# **2. Architecture multi-timeframe**

La lecture du marché se fait toujours du plus grand timeframe vers le plus petit. Chaque niveau a un rôle précis et non interchangeable :

| **Niveau** | **Rôle** |
|---|---|
| DAILY | Biais général / contexte (Daily Bias, Power of 3) |
| H1 | Zones importantes / structure de fond |
| M15 | Structure intermédiaire / liquidité / range / POI |
| M5 | MSS / CHOCH / displacement / zone d'entrée |
| M1 | Optimisation éventuelle de l'entrée (« sniper ») |

> **Règle fondamentale** **HTF = contexte**   ·   **MTF = localisation**   ·   **LTF = exécution** Un changement de structure sur M1 ne signifie donc JAMAIS automatiquement que la tendance H1/M15 s'est retournée. C'est l'erreur n°1 des débutants (voir §11).

# **3. Le processus étape par étape (cœur de la méthode)**

Structure officielle confirmée par la vidéo « Stratégie SMC de A à Z » : deux modules — **Module 1 = Analyse** (UT supérieure) et **Module 2 = Exécution** (UT inférieure).

## **Module 1 — Analyse (contexte & localisation)**

### **Étape 1 · Tendance de fond (UT supérieure — Daily / H4 / H1)**

- Identifier la tendance via la théorie de Dow (sommets/creux croissants = haussier ; décroissants = baissier).
- **Filtre Daily Bias (optionnel, validé 68 %) :** marquer PDH (Previous Daily High) et PDL (Previous Daily Low). Continuation si clôture au-delà ; signal de shift si sweep + réintégration dans le range.
- **Filtre Power of 3 (optionnel, ≈98 %) :** anticiper qu'une mèche de manipulation par rapport à l'open du jour précède la vraie expansion — ne pas se faire piéger par ce premier mouvement contraire.

### **Étape 2 · Marquer la liquidité et le Range Asiatique**

- Marquer les niveaux où des stops se concentrent : PDH, PDL, Asia High, Asia Low, sommets/creux précédents, bornes de range, sommets/creux M15/H1 importants.
- **Range Asiatique :** fenêtre 23h–7h (Paris), surtout sur paires européennes (EUR, GBP, CHF). Sert de phase d'accumulation ; ses bornes deviennent des références de liquidité pour la session de Londres.

### **Étape 3 · Attendre la manipulation (prise de liquidité)**

- Ne pas simplement attendre que le prix touche une zone. Chercher la séquence : prise de liquidité → réaction → réintégration.
- **Modèle AMD / Power of 3 :** Accumulation (range) → Manipulation (sweep d'un creux/sommet) → Distribution (mouvement réel).

### **Étape 4 · Confirmation par CHOCH (le point clé anti-piège)**

> **Ne pas prendre le premier CHOCH** Un CHOCH / MSS sur petite UT n'est PAS automatiquement un vrai retournement. Il peut être : une simple structure interne, de l'inducement, ou une prise de liquidité avant le vrai mouvement. **Séquence recherchée :** Sweep → Réintégration → MSS/CHOCH pertinent → Displacement → Zone → Retest.

- Attendre un premier CHOCH sur l'UT de travail (biais confirmé), puis descendre sur UT inférieure et attendre un SECOND CHOCH avant d'entrer — plutôt qu'un ordre en attente direct dès l'arrivée en zone.
- **Astuces pour ne pas confondre structure interne et externe :** règle des deux bougies (valider un sommet après 2 bougies opposées consécutives) ; et changer d'UT pour trancher un signal ambigu.

### **Étape 5 · Identifier le displacement et la zone (POI)**

- Un déplacement fort (displacement) est préférable à un mouvement lent : il laisse une FVG, une imbalance ou un Order Block exploitable.
- **Validation POI :** un OB+FVG ne devient un vrai Point of Interest que s'il combine BOS en amont + FVG + zone de demande/supply définie + cohérence avec le biais directionnel.

## **Module 2 — Exécution (entrée & gestion)**

### **Étape 6 · Filtre Premium / Discount + OTE**

- Tracer le Dealing Range (sommet ↔ creux de référence) → niveau médian 50 %.
- **Vendre uniquement en Premium (>50 %), acheter uniquement en Discount (<50 %).** Rejeter tout signal du mauvais côté, même s'il coche les autres critères.
- **Version renforcée (OTE) :** restreindre l'entrée à la zone de retracement 62–79 % (centre ~70,5 %). Attention à ne pas sur-optimiser.

### **Étape 7 · Entrée sur la zone + confirmation LTF**

- Attendre le retour du prix dans la zone (retest), puis une confirmation en M5/M1 (bougie de rejet, MSS local, FVG/IFVG).
- **Options d'affinage :** Order Block 2.0 (OB mineur dans l'OB majeur, UT inférieure) ou entrée sur la ligne médiane 50 % de la zone — meilleurs ratios, mais déclenchement moins fréquent.

### **Étape 8 · Stop Loss structurel**

> **La règle d'or du stop-loss** **Mauvaise logique :** un stop ultra-serré uniquement pour afficher un gros R:R. **Bonne logique :** placer le SL là où le scénario devient réellement invalide (sommet/creux protégé, structure majeure, extrémité de zone). Rappel martelé dans la playlist : « stop-loss trop serré = stop-loss trop souvent touché ». Tenir compte de l'inducement (le prix va souvent chercher une liquidité juste avant la zone) et de l'AMD (prix moyen : le prix peut osciller dans toute la zone avant de repartir).

### **Étape 9 · Gestion de position (targets échelonnées)**

- **TP1 :** 1R ou premier niveau structurel → prise partielle, puis passage à break-even.
- **TP2 :** niveau intermédiaire (prix médian, FVG/BPR, liquidité intermédiaire).
- **TP3 :** liquidité majeure (Asia High/Low, PDH/PDL, borne opposée du range, sommet/creux important).
- Choix de target clé : rester sur l'UT de travail par défaut ; n'élargir vers l'UT supérieure que si le setup est aligné ET qu'une structure supérieure est proche.

# **4. Le setup complet, de A à Z**

Le modèle mental à mémoriser, du contexte à la sortie :

> **CONTEXTE (HTF)**

▼

> **DAILY BIAS**

▼

> **H1 / M15**

▼

> **RANGE / POI**

▼

> **LIQUIDITÉ**

▼

> **SWEEP / MANIPULATION**

▼

> **RÉINTÉGRATION**

▼

> **MSS / CHOCH**

▼

> **DISPLACEMENT**

▼

> **FVG / IFVG / BPR / OB / RB**

▼

> **RETEST**

▼

> **CONFIRMATION LTF**

▼

> **ENTRÉE**

▼

> **SL STRUCTUREL**

▼

> **TP → LIQUIDITÉ**

## **Version LONG (achat)**

- Daily Bias haussier
- Contexte H1/M15 haussier ou range pertinent
- Asia Low / PDL / creux important identifié
- Londres prend cette liquidité (sweep)
- Réintégration dans le range
- MSS / CHOCH haussier pertinent
- Displacement (déplacement fort)
- Zone identifiée : FVG / IFVG / BPR / RB / OB (en Discount)
- Retour du prix dans la zone (retest)
- Confirmation M5 / M1
- Entrée LONG
- SL structurel sous le creux protégé
- TP échelonnés vers la liquidité supérieure

## **Version SHORT (vente)**

- Daily Bias baissier
- Contexte H1/M15 baissier ou range pertinent
- Asia High / PDH / sommet important identifié
- Londres prend cette liquidité (sweep)
- Réintégration dans le range
- MSS / CHOCH baissier pertinent
- Displacement (déplacement fort)
- Zone identifiée : FVG / IFVG / BPR / RB / OB (en Premium)
- Retour du prix dans la zone (retest)
- Confirmation M5 / M1
- Entrée SHORT
- SL structurel au-dessus du sommet protégé
- TP échelonnés vers la liquidité inférieure

# **5. Bibliothèque des concepts (référence détaillée)**

*Chaque concept indique entre crochets la ou les vidéos sources.*

## **5.1 Structure de marché — externe vs interne  [V4, V21]**

- **Structure externe (majeure) :** sommets/creux de référence — définit le biais directionnel.
- **Structure interne (mineure) :** mouvements internes = recherche de liquidité, PAS un changement de tendance.
- **Règle :** structure externe > structure interne. Le biais ne change qu'à la cassure d'un niveau de référence majeur.
- **Astuce des deux bougies :** valider un sommet après 2 bougies baissières consécutives (inverse pour un creux).

## **5.2 CHOCH & BOS  [V5]**

- **CHOCH (Change of Character) :** première cassure à contre-tendance = début de retournement.
- **BOS (Break of Structure) :** cassure confirmant la continuation d'une tendance établie.
- **Mémo :** CHOCH = début de tendance ; BOS = poursuite. Clôture (conservateur) ou mèche (agressif), au choix.

## **5.3 Liquidité (BSL / SSL) & Inducement  [V3, V10, V11]**

- **Buy Side Liquidity (BSL) :** au-dessus d'un sommet. Sell Side Liquidity (SSL) : sous un creux.
- **Principe :** le marché va chercher ces stops (piège) avant de repartir dans l'autre sens.
- **Inducement :** liquidité créée juste avant un POI pour piéger les entrées trop précoces. Le vrai mouvement démarre après ce piège.
**Les 8 zones d'inducement typiques :**

- Sommets/creux de structure en tendance
- Supports/résistances testés plusieurs fois
- Lignes de tendance (trendlines)
- Bornes de range / consolidation (surtout session asiatique)
- Figures chartistes (double sommet/creux)
- Niveaux de retracement Fibonacci
- L'Order Block / zone demande-offre elle-même
- Autour des publications économiques (NFP, FOMC, taux)

## **5.4 FVG, IFVG & BPR  [V2, V23, V29]**

- **FVG (Fair Value Gap) :** gap sur 3 bougies (pas de contact entre bougie 1 et bougie 3) = imbalance. Tend à être comblé tôt ou tard.
- **IFVG (Inverted FVG) :** une FVG cassée par une clôture de l'autre côté devient un signal de retournement / nouvelle zone de retest. La clôture est indispensable (une mèche ne suffit pas).
- **BPR (Balance Price Range) :** zone commune entre une FVG haussière et une FVG baissière opposées (avec confirmation IFVG). Combine plusieurs confirmations à lui seul — peut servir de POI et même de biais directionnel.

> **Définition du BPR (mot du formateur)** *« Ce n'est pas juste un FVG, pas juste un IFVG : c'est le cumul de prise de liquidité autour des sommets, d'un FVG haussier, d'un FVG baissier cassé pour devenir un IFVG, illustrant toute une zone de prix d'équilibre. »*

## **5.5 Order Block & variantes  [V1, V6, V14, V24, V25]**

- **Order Block (OB) :** dernière bougie opposée avant le mouvement impulsif. Meilleure qualité s'il est à l'origine d'un BOS.
- **Order Block 2.0 :** affiner l'entrée via un OB mineur (UT inférieure) dans l'OB majeur — meilleur ratio, mais plus souvent manqué.
- **Breaker Block :** OB cassé alors que la structure CONTINUE (nouveau plus bas/haut) — devient zone de retest dans le sens du mouvement.
- **Mitigation Block :** apparaît quand la structure NE continue PAS (creux plus haut en tendance baissière) — zone où les positions perdantes sont neutralisées avant retournement.
- **Rejection Block :** l'espace de la mèche d'une bougie de rejet dans une zone clé (surtout aux bornes d'un range).

## **5.6 Smart Money Trap & SMT Divergence  [V12, V13]**

- **Smart Money Trap (3 OB à éviter) :** OB de contre-tendance pure ; OB sans prise de liquidité préalable ; OB déjà mitigé/testé.
- **SMT Divergence :** divergence de prix entre deux actifs corrélés (même horodatage). Pas un signal en soi — une confirmation supplémentaire du biais. Ex. S&P 500 / Nasdaq (corrélation +), USDX / EUR-USD (corrélation −).

## **5.7 Premium / Discount, OTE & POI/AMD  [V8, V9, V15, V18]**

- **Premium / Discount :** au-dessus/en dessous du niveau 50 % d'un range. Acheter en Discount, vendre en Premium.
- **OTE (Optimal Trade Entry) :** retracement 62–79 % (centre ~70,5 %) — filtre plus strict, entrées plus sélectives.
- **POI (Point Of Interest) :** zone d'intérêt cohérente avec le biais (≠ n'importe quel OB).
- **AMD :** Accumulation → Manipulation → Distribution (ICT/Power of 3). Équivalent Wyckoff : Accumulation → Markup → Distribution → Markdown, avec le « Spring » comme prise de liquidité.

## **5.8 Niveaux forts / faibles & zones fraîches  [V19, V22]**

- **Tendance haussière :** creux = forts/protégés (référence SL) ; sommets = faibles/cibles.
- **Tendance baissière :** sommets = forts/protégés ; creux = faibles/cibles.
- **Fraîcheur :** une zone non mitigée (jamais retestée) est privilégiée — facteur de qualité, pas condition absolue.
- **8 clés du Supply/Demand institutionnel [V19] :** retournement, BOS, prise de liquidité, grandes UT, alignement MTF, Premium/Discount, fraîcheur, confirmation.

# **6. Les deux concepts validés par backtest**

Point crucial : sur l'ensemble de la playlist, seuls deux concepts sont appuyés par un backtest à grande échelle. Tous les autres reposent sur des exemples choisis *a posteriori*.

| **Concept** | **Ce que dit le backtest** |
|---|---|
| Daily Bias  [V26] | ≈68 % de scénarios valides sur ~1 779 opportunités (GER40, 10 ans). Décrit un biais journalier via PDH/PDL, pas un winrate de trade complet. |
| Power of 3 journalier  [V27] | ≈97,75 % des ~3 245 bougies journalières présentent une mèche opposée au mouvement final. Décrit un comportement (manipulation avant expansion), pas un trade avec SL/TP. |

> **Lecture honnête de ces chiffres** Ces pourcentages décrivent la fréquence d'un scénario, pas la rentabilité d'une stratégie. Un biais correct à 68 % ne dit rien du ratio, des stops touchés, ni des coûts. Ce sont néanmoins les deux briques les plus solides à tester en priorité.

# **7. Les 5 erreurs critiques à éviter  [V28]**

- **Privilégier les concepts SMC à l'analyse multi-timeframe** — trader une seule UT sans contexte génère des faux signaux à la chaîne.
- **Trader tous les FVG / CHOCH / OB sans filtre** — viser le qualitatif aligné au contexte supérieur, pas chaque zone.
- **Confondre CHOCH et prise de liquidité** — le premier CHOCH est souvent un piège. Ne pas empiler tous les concepts.
- **Stop-loss irréalistes sans contexte** — « stop trop serré = stop trop souvent touché ».
- **Absence de confirmation dans la zone** — l'ordre direct maximise le ratio mais s'expose au passage sans réaction ; la confirmation sécurise au prix d'un ratio moindre.

# **8. Quand NE PAS trader**

- Daily Bias absent ou Inside Day sans direction claire
- Marché au milieu d'un range, sans avantage
- Aucune liquidité identifiable
- Simple CHOCH M1 sans contexte supérieur
- FVG isolé, ou zone contradictoire avec le contexte
- SL trop serré ou target irréaliste
- Entrée motivée par le FOMO
- Setup nécessitant trop d'interprétation subjective

# **9. Checklist avant chaque entrée**

### **Contexte**

- ☐  Daily Bias identifié ? H1/M15 cohérent ? Tendance ou range défini ?
- ☐  PDH / PDL / Asia High / Asia Low marqués ?

### **Liquidité**

- ☐  Où est la liquidité ? Niveau HTF significatif ?
- ☐  Sweep effectué ? Réintégration confirmée ?

### **Structure**

- ☐  Structure externe et interne définies ?
- ☐  CHOCH pertinent sur le bon timeframe ? MSS confirmé ? Displacement présent ?

### **Zone**

- ☐  Zone claire (FVG / IFVG / BPR / OB / RB / MB) et alignée au contexte ?
- ☐  Zone fraîche ? Premium/Discount cohérent ?

### **Entrée & Risque**

- ☐  Prix revenu sur la zone ? Confirmation LTF ? Pas de FOMO ?
- ☐  SL sur invalidation structurelle ? Risque par trade défini ? R:R acceptable ?
- ☐  TP1 / TP2 / TP final définis ?

> **La règle des 5 questions (avant de cliquer)** **1. Où sommes-nous ?** → contexte HTF. **2. Où est la liquidité ?** → PDH/PDL, Asia, sommets/creux, range. **3. Quelle liquidité vient d'être prise ?** → sweep / manipulation. **4. Où est mon entrée ?** → zone + retest + confirmation. **5. Où le scénario est-il invalidé ?** → SL structurel. **Une réponse pas claire = PAS DE TRADE.**

# **10. Noyau, confluences, variantes (comment ne rien empiler)**

La playlist accumule ~28 concepts. L'erreur fatale (voir §7) est de tous les exiger simultanément. La règle : un **noyau obligatoire**, enrichi de **1 à 3 confluences** seulement, plus une confirmation. Les **variantes** ne servent qu'au réglage fin et se testent une par une.

### **🟥 Noyau — obligatoire, à tester en premier**

- Structure HTF (biais)
- Biais directionnel confirmé
- Liquidité identifiée
- Sweep / prise de liquidité
- CHOCH pertinent
- POI cohérent avec le contexte
- Premium / Discount respecté
- Confirmation LTF
- SL structurel
- Target structurelle

### **🟧 Confluences fortes — en ajouter 1 à 3, pas davantage**

- FVG · Order Block · BPR
- Inducement · Range Asiatique · PO3 / AMD
- Second CHOCH · Niveaux protégés

### **🟨 Variantes — réglage fin, à backtester séparément**

- OTE · IFVG · Rejection Block · Mitigation Block · Breaker Block
- Order Block 2.0 · SMT Divergence
- Entrée agressive vs 50 % vs confirmation · M1 vs M5

> **La formule à retenir** **Noyau   +   1 à 3 confluences   +   confirmation   =   setup testable** Surtout PAS : Daily Bias + Asia + PO3 + Sweep + CHOCH + BOS + OB + FVG + BPR + IFVG + RB + MB + Breaker + OTE + SMT + Inducement = un seul trade. Cet empilement ne se produit quasiment jamais et paralyse l'exécution.

# **11. Prochaine étape : le plan de backtest**

La playlist offre beaucoup de variantes. Il ne faut pas toutes les mélanger d'un coup. Tester chaque variable SÉPARÉMENT pour isoler ce qui a réellement une meilleure espérance de gain :

| **Variable** | **Options à tester séparément** |
|---|---|
| Entrée | Limit directe · 50 % de zone · confirmation M5 · confirmation M1 |
| Type de zone | FVG · IFVG · BPR · RB · OB · MB · Breaker |
| Liquidité | Asia H/L · PDH/PDL · M15 · H1 · combinaison de niveaux |
| Gestion | TP fixe · 1R+BE · partiel+runner · liquidité suivante · borne opposée |
| Timeframe | M5 seul · M5 → M1 |

> **Recommandation de priorisation** 1. Commencer par isoler Daily Bias + Power of 3 seuls (les deux briques chiffrées) sur votre instrument. 2. Choisir 2–3 concepts d'entrée maximum (ex. OB + FVG + structure), pas tout le catalogue. 3. Backtester chaque brique avant de les combiner. **C'est le backtest — pas la conviction — qui doit décider quelles combinaisons sont profitables.**

## **Règle méthodologique : tout transformer en OUI / NON**

Le plus grand danger de cette approche est le biais d'interprétation rétroactive : voir un setup « évident » sur un graphique dont on connaît déjà l'issue. Le remède : chaque règle doit devenir une **question binaire objective**.

- **Liquidité prise ?** Oui / Non
- **CHOCH confirmé ?** Oui / Non
- **Premium / Discount cohérent ?** Oui / Non
- **POI fraîche (non mitigée) ?** Oui / Non
- **Second CHOCH présent ?** Oui / Non
- **FVG présente ?** Oui / Non
- **Target atteinte ?** Oui / Non
- **SL touché ?** Oui / Non

> **Le test de validité d'une règle** **Deux personnes regardant le même graphique doivent arriver à la même conclusion.** Si une règle laisse place à l'interprétation (« le CHOCH est-il assez net ? »), elle n'est pas encore backtestable : il faut la préciser jusqu'à ce qu'elle devienne un OUI / NON sans ambiguïté.

# **12. Résumé ultra-court**

> Je commence par le Daily Bias et le contexte H1/M15. Je marque les liquidités : PDH, PDL, Asia High/Low, sommets/creux importants. J'attends que le marché prenne une liquidité, idéalement pendant la manipulation de Londres. Je n'entre pas sur le premier CHOCH : j'attends une vraie réaction et un déplacement. Je sélectionne une zone qualitative — FVG, IFVG, BPR, RB, OB. J'attends son retest et une confirmation M5/M1. Je place le SL derrière l'invalidation structurelle. Je prends mes profits progressivement vers les niveaux de liquidité. **Si le contexte, la liquidité, la structure ou l'invalidation ne sont pas clairs : je ne trade pas.**

*Document de synthèse — fusion de deux analyses de la playlist SMC/ICT (29 vidéos). À usage éducatif et personnel. Chaque règle doit être validée par un backtest propre avant toute utilisation en réel.*
