# AUTORESEARCH — Moteur d'ordonnancement PP_830 / PP_153

## Objectif

Construire un moteur d'ordonnancement qui, à partir de données CSV exports Sage X3,
produit un planning hebdomadaire optimisé pour deux lignes de production :
- **PP_830** — LIGNE EASY HOME (assemblage kits)
- **PP_153** — LIGNE ASSEMBLAGE BDH (bouches hygro, fournisseur interne de PP_830)

---

## Données d'entrée (CSV)

| Fichier | Contenu |
|---|---|
| `data/statique/articles.csv` | Catalogue articles (TYPE_APPRO : ACHAT / FABRICATION) |
| `data/statique/gammes.csv` | Article × Poste de charge × Cadence (u/h) |
| `data/statique/nomenclatures.csv` | BOM récursive parent → composants + quantités |
| `data/dynamique/besoins_clients.csv` | Commandes fermes (NATURE_BESOIN = "COMMANDE" uniquement) |
| `data/dynamique/of_entetes.csv` | OF existants (WOP statut=1 / WOS statut=3) |
| `data/dynamique/stock.csv` | Stock physique, alloué, bloqué par article |
| `data/dynamique/receptions_oa.csv` | Réceptions fournisseurs prévues (article + date + qté) |

> **Important** : ne jamais utiliser les lignes NATURE_BESOIN = "PREVISION" du fichier besoins.

---

## Contexte métier

### Architecture multi-niveaux

```
Niveau 3 — Sous-ensembles (postes amont PP_153)
    ↓ disponibles J-1 à J-2
Niveau 2 — PP_153 (BDH stock tampon + PF directs)
    ↓ stock tampon BDH disponible J-1
Niveau 1 — PP_830 (kits Easy Home → clients)
    ↓ expédition
Clients
```

Les sous-ensembles entrant dans les articles PP_153 sont à identifier
via la nomenclature (TYPE_ARTICLE = "Fabriqué" dans nomenclatures.csv).
Leurs OF doivent être ordonnancés au même titre que les OF PP_153 et PP_830.

- **MTS** : commande liée à un WOP via OF_CONTREMARQUE. L'OF existe déjà.
- **NOR/MTO** : pas de lien direct. Le CBN génère des WOS à affermir.

### Lien PP_153 → PP_830

PP_153 produit des BDH (bouches hygro) qui alimentent un **stock tampon**.
PP_830 consomme ces BDH pour assembler ses kits.
PP_153 produit aussi des PF vendus en direct (commandes propres).

### Articles PP_153 impliqués (stock tampon pour PP_830)

| Article | Cadence PP_153 | Présent dans kits PP_830 |
|---|---|---|
| BDH2216AL | 640 u/h | 18/18 kits BDH (100%) |
| BDH2231AL | 360 u/h | 16/18 kits BDH (89%) |
| BDH2251AL | 360 u/h | 16/18 kits BDH (89%) |

Quantité consommée par kit : 1 unité de chaque BDH présent.

---

## Règles métier (non négociables)

### R1 — Capacité journalière
- 2 shifts × 7h = **14h/jour** disponibles sur chaque ligne
- Seuil minimum d'ouverture : **7h/jour** (1 shift minimum)
- En dessous de 7h planifiées → ligne considérée "non ouverte" ce jour

### R2 — Disponibilité des composants
- Applicable à **toutes les lignes** sans exception
- Tous les composants d'un OF doivent être disponibles en stock
  **J-1 ou J-2 avant la date de lancement** de cet OF
- Si composants insuffisants → OF non lançable, reporter au premier jour où c'est possible
- Vérification récursive : si composant = FABRICATION, vérifier ses propres composants

### R3 — Stock tampon BDH (seuils minimums)
Calculés pour couvrir 1 shift complet de PP_830 sans production PP_153 :

| BDH | Stock tampon minimum |
|---|---|
| BDH2216AL | 673 u |
| BDH2231AL | 598 u |
| BDH2251AL | 598 u |

### R4 — Priorité PP_153
```
Début de chaque shift :
  Si stock_BDH < seuil_tampon (une des 3 références)
    → Produire BDH EN PREMIER sur PP_153
  Sinon
    → Commandes directes PP_153 en priorité (tri EDD)
```

### R5 — Chaîne de délais BDH → PP_830
```
J-2 : composants de PP_153 disponibles en stock
J-1 : OF BDH lancé sur PP_153 → BDH produits et mis en stock
J   : OF kit lancé sur PP_830 → BDH consommés depuis stock tampon
```

### R6 — Séquencement PP_830
- Tri principal : **EDD** (Earliest Due Date) — respect des délais clients
- Contrainte : composants disponibles J-1 à J-2 (R2)
- Si charge journalière > 14h → reporter l'OF le plus long au lendemain
- Si charge journalière < 7h → compléter avec OF suivant disponible

### R7 — Règle d'affermissement
- Interdit de lancer un OF si un composant **ACHAT** est en rupture
- Autorisé si le composant en rupture est **FABRICATION** (on peut lancer un OF amont)

---

## Métriques à optimiser

### KPI principal
```
taux_service = nb_OF_livrés_dans_délai / nb_OF_total
```
"Dans les délais" = date expédition ≤ date_expedition_demandee

### KPI secondaire
```
taux_ouverture = heures_planifiées / heures_disponibles
objectif : ≥ 7h/jour (1 shift minimum)
```

### Score composite (pour la boucle autoresearch)
```
score = taux_service × 0.7 + taux_ouverture × 0.3
```
Maximiser ce score sur l'horizon S+1 à S+3.

---

## Outputs attendus

```
outputs/
├── planning_PP830.csv     # OF × jour × heure_début × heure_fin × charge_h
├── planning_PP153.csv     # idem PP_153
├── stock_BDH_projeté.csv  # BDH2216/2231/2251 × jour × stock_projeté
├── kpis.json              # taux_service, taux_ouverture, score
└── alertes.txt            # OF non planifiables + raison
```

---

## Structure du moteur suggérée

```
src/
├── loaders/          # Chargement et validation des CSV (existant)
├── models/           # Dataclasses OF, Besoin, Stock, BOM (existant)
├── checkers/         # Vérification faisabilité composants (existant)
└── scheduler/        # NOUVEAU — cœur du POC
    ├── bom_graph.py       # BOM en DAG pour traversée rapide
    ├── demand_solver.py   # Calcul besoins nets + matching OF
    ├── capacity.py        # Modèle capacité journalière (shifts)
    ├── buffer_manager.py  # Gestion stock tampon BDH
    ├── sequencer.py       # Séquencement PP_830 et PP_153
    └── kpi.py             # Calcul taux_service + taux_ouverture
```

---

## Règle de faisabilité des composants

### Ce qui est bloquant dur
- Composant ACHAT **absent du stock ET aucune réception prévue ≤ date_besoin** → OF bloqué
- Composant FABRICATION en rupture sans OF amont planifiable → OF bloqué

### Ce qui est faisable (mais tendu)
- Composant ACHAT avec réception prévue **le jour J même** → OF faisable
- Composant FABRICATION couvert par un OF amont finissant le jour J → OF faisable

### Critère de préférence (robustesse)
L'algorithme distingue deux catégories d'OF :
- **OF confortable** : tous les composants disponibles en stock J-1 ou J-2
- **OF tendu** : au moins un composant dépendant d'une réception ou d'une fabrication amont le jour J

**Règle de déviation :**
Si un OF tendu (date proche) et un OF confortable (date plus lointaine) sont en compétition
pour la même capacité, l'algorithme **évalue le scénario de déviation** :

```
Scénario A (EDD pur) :
  → Lancer OF tendu (date proche)
  → Risque : si aléa sur réception/fabrication → retard commande proche

Scénario B (déviation) :
  → Lancer OF confortable (date lointaine)
  → Projeter stock résiduel des composants partagés avec OF tendu
  → Évaluer si OF tendu reste faisable le lendemain
  → Si retard OF tendu ≤ 1 jour → scénario B acceptable
```

Chaque déviation est **pénalisée dans le score** (w3).
L'objectif est de minimiser le retard total pondéré, pas de maximiser le respect de l'EDD pur.

---

## Score composite

```
score = taux_service  × w1
      + taux_ouverture × w2
      - nb_déviations  × w3

contrainte : w1 + w2 + w3 = 1.0
bornes     : w1 ∈ [0.5, 0.85]
             w2 ∈ [0.1, 0.35]
             w3 ∈ [0.05, 0.20]
```

La pénalité w3 doit être suffisamment élevée pour que la déviation reste
un dernier recours, mais pas trop pour ne pas bloquer des décisions robustes légitimes.

---

## Paramètres de la boucle autoresearch

```
GOAL     : maximiser score (voir formule ci-dessus)
COMMAND  : python -m src.main --schedule
METRIC   : dernière ligne stdout → "SCORE: X.XXX"
IN_SCOPE : src/scheduler/, config/weights.json
HORIZON  : 15 jours ouvrés glissants à partir d'aujourd'hui
REVERT_IF: score baisse OU programme plante OU taux_service < 0.80
NEVER_TOUCH: src/loaders/, src/models/, règles métier R1 à R7
```

### Ce que l'agent peut modifier
- Les poids w1/w2/w3 dans `config/weights.json`
- L'algorithme de séquencement dans `src/scheduler/sequencer.py`
- La logique de détection OF confortable vs tendu
- La logique de projection du stock résiduel
- Le seuil de déclenchement de reconstitution BDH

### Ce que l'agent ne touche jamais
- Les règles métier R1 à R7
- Les loaders et modèles de données
- La règle de priorité PP_830 > commandes directes PP_153 (absolue)
- L'horizon glissant 15 jours ouvrés
- La définition de "bloquant dur" sur les composants

---

## Décisions métier finalisées

| Question | Décision |
|---|---|
| Poids score | **Paramètres optimisables** par l'agent (w1/w2/w3) |
| Conflit PP_153 : BDH vs commande directe urgente | **PP_830 toujours prioritaire** — sans exception |
| Horizon | **15 jours ouvrés glissants** — recalculé à chaque run |
| Composant disponible le jour J | **Faisable mais tendu** — pénalisé via w3 |
| Déviation EDD | **Acceptable si retard ≤ 1 jour** sur commande proche |
