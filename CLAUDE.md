# Ordonnancement Production v2

Système de gestion de production et d'ordonnancement manufacturier avec analyse des commandes MTS/MTO/NOR.

## 📁 Structure des données

### Fichiers CSV disponibles

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `articles.csv` | 6 910 | Catalogue produits |
| `of_entetes.csv` | 15 285 | Ordres de fabrication (en-têtes) |
| `of_composants.csv` | 215 299 | Nomenclatures OF (composants) |
| `nomenclatures.csv` | 25 028 | **Nomenclatures articles (table principale)** |
| `gammes.csv` | 2 954 | Gammes de production |
| `commandes_clients.csv` | 835 | Commandes clients |
| `stock.csv` | 6 833 | État des stocks |
| `receptions_oa.csv` | 1 805 | Réceptions fournisseurs |

## 🗂️ Structure des tables

### articles.csv - Catalogue produits
```
ARTICLE         → Code article (PK)
DESCRIPTION     → Description produit
CATEGORIE       → Catégorie (AP, APV, PF3, PFAS, etc.)
TYPE_APPRO      → Type d'approvisionnement (ACHAT ou FABRICATION)
DELAI_REAPPRO   → Délai de réapprovisionnement (jours)
```

### of_entetes.csv - Ordres de fabrication
```
NUM_OF              → Numéro d'OF (PK)
ARTICLE             → Code article à fabriquer (FK → articles)
DESCRIPTION         → Description
STATUT_NUM_OF       → Status (1 = Ferme/Affermi, 3 = Suggéré)
STATUT_TEXTE_OF     → Status texte ("Ferme", "Suggéré")
DATE_FIN            → Date de fin prévue
QTE_A_FABRIQUER     → Quantité à fabriquer
QTE_FABRIQUEE       → Quantité fabriquée
QTE_RESTANTE        → Quantité restante
```

**Statuts OF :**
- **1 = Ferme (Affermi/WOP)** : OF déjà lancé en production, prioritaire pour le matching
- **3 = Suggéré (WOS)** : OF suggéré par le moteur CBN/MRP, utilisé si pas d'OF affermi disponible

### of_composants.csv - Nomenclatures OF
```
NUM_OF                  → Numéro d'OF (FK → of_entetes)
ARTICLE                 → Code article composant (FK → articles)
DESCRIPTION             → Description composant
QUANTITE_REQUISE        → Quantité requise
DATE_BESOIN_COMPOSANT   → Date de besoin du composant
```

### nomenclatures.csv - Nomenclatures articles ⭐
```
Article parent           → Article fabriqué (code)
Designation parent      → Description de l'article parent
Niveau                  → Niveau de profondeur (5, 10, 15, 20, 25...)
Article composant       → Code du composant nécessaire
Désignation composant   → Description du composant
Qté lien                → Quantité nécessaire pour 1 unité parent (peut être décimale)
Type article            → "Acheté" ou "Fabriqué"
```

**Caractéristiques :**
- **2 501 articles** avec nomenclature connue
- **25 028 lignes** de relations parent → composant
- **1 474 articles** ont des composants fabriqués (niveau 2+)
- Permet la **vérification récursive complète**
- **Couverture : 84%** des articles FABRICATION

**Exemple :**
```csv
"MH7652";"MH REG03 -- 2,3 BDH";    5;"MH7649";"MH ---- PRER03 2,3 BDH";1;"Fabriqué"
"MH7652";"MH REG03 -- 2,3 BDH";   10;"E4074";"ROULEAU ETIQ NON DECOUPE";0,000005;"Acheté"
"MH7652";"MH REG03 -- 2,3 BDH";   30;"D5624";"ETIQ PVC ROSE 70x55";3;"Acheté"
```

**Utilisation :**
- Remplace `of_composants.csv` pour la vérification de faisabilité
- Permet de connaître la nomenclature **indépendamment des OF**
- Essentiel pour la vérification récursive des composants FABRIQUÉS

### gammes.csv - Gammes de production
```
ARTICLE         → Code article (FK → articles)
POSTE_CHARGE    → Poste de travail (PP_XXX)
LIBELLE_POSTE   → Description du poste
CADENCE         → Cadence (unités/heure)
```

### commandes_clients.csv - Commandes clients
```
NUM_COMMANDE                → Numéro de commande
LIGNE_COMMANDE              → Ligne de commande
CODE_CLIENT                 → Code client
NOM_CLIENT                  → Nom client
ARTICLE                     → Code article (FK → articles)
DESCRIPTION                 → Description
QTE_COMMANDEE               → Quantité commandée
QTE_ALLOUEE                 → Quantité allouée
QTE_RESTANTE                → Quantité restante à servir
DATE_EXPEDITION_DEMANDEE    → Date d'expédition demandée
FLAG_CONTREMARQUE           → Type (5 = MTS, 1 = NOR/MTO)
OF_CONTREMARQUE             → OF lié (MTS uniquement)
```

### stock.csv - État des stocks
```
ARTICLE         → Code article (FK → articles)
STOCK_PHYSIQUE  → Stock physique disponible
STOCK_ALLOUE    → Stock alloué
STOCK_BLOQUE    → Stock bloqué
```

### receptions_oa.csv - Réceptions fournisseurs
```
NUM_COMMANDE            → Numéro de commande fournisseur
ARTICLE                 → Code article (FK → articles)
CODE_FOURNISSEUR        → Code fournisseur
QUANTITE_RESTANTE       → Quantité à recevoir
DATE_RECEPTION_PREVUE   → Date de réception prévue
```

## 🔗 Relations entre tables

```
┌─────────────────┐
│  articles       │ ← Table centrale
│  ────────────   │
│  ARTICLE (PK)   │
└────────┬────────┘
         │
         ├──────────────────┬──────────────────┬──────────────────┬───────────────┐
         │                  │                  │                  │               │
         ▼                  ▼                  ▼                  ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ of_entetes      │ │ gammes          │ │ commandes_      │ │ stock           │ │ receptions_oa   │
│ (WOP/WOS)       │ │                 │ │ clients         │ │                 │ │                 │
└────────┬────────┘ └─────────────────┘ └────────┬────────┘ └─────────────────┘ └─────────────────┘
         │                                      │
         │                                      │ OF_CONTREMARQUE
         │                                      │ (MTS uniquement)
         │                                      └─────→ of_entetes.NUM_OF
         │
         ▼
┌─────────────────┐
│ of_composants   │
│ (Nomenclatures) │
└─────────────────┘
```

## 🏷️ Types de commandes

### MTS (FLAG_CONTREMARQUE = 5) - Make To Stock avec contre-marque

**Caractéristiques :**
- ✅ Contre-marque OBLIGATOIRE
- ✅ Lien direct commande → OF via `OF_CONTREMARQUE`
- ✅ Génère un WOP (Work Order Planned)
- ✅ Allocation AUTOMATIQUE du stock à la commande
- ✅ Principalement client ALDES (335/332 commandes)

**Flux :**
```
Commande MTS
    ↓
Création WOP (lien obligatoire)
    ↓
Affermissement par l'ordonnanceur
    ↓
Fabrication
    ↓
Entrée en stock
    ↓
Allocation AUTOMATIQUE à la commande
    ↓
Expédition
```

**Exemples d'articles MTS :**
- ESHKIT CPT HYGMW- BDH (448 unités)
- BDH1050 -75 R03PNE -30 N 125AL (384 unités)
- KIT OPT BDH BAIN CELLIER D80 (48 unités)

### NOR/MTO (FLAG_CONTREMARQUE = 1) - Normal / Make To Order

**Caractéristiques :**
- ✅ Pas de contre-marque
- ✅ PAS de lien direct commande → OF
- ✅ Traité par le moteur CBN/MRP
- ✅ Génère des WOS (Work Order Suggested)
- ✅ Regroupement hebdomadaire des besoins
- ✅ Allocation MANUELLE du stock aux commandes
- ✅ 14 clients différents (NOR = tous sauf ALDES, MTO = ALDES)

**Flux :**
```
Commande NOR/MTO
    ↓
Moteur CBN/MRP (calcul des besoins nets)
    ↓
Génération WOS suggérés (regroupement hebdo)
    ↓
Affermissement par l'ordonnanceur
    ↓
Fabrication pour le stock
    ↓
Entrée en stock
    ↓
Allocation MANUELLE aux commandes
    ↓
Expédition
```

**Exemples d'articles NOR/MTO :**
- EAR 0*35 L-- SP -- BLC AE
- BXCC1245---- R0 --- - -- 100AE
- MR MONO D160 170M3/100CFM

## 📊 Différences clés MTS vs NOR/MTO

| Aspect | MTS (FLAG 5) | NOR/MTO (FLAG 1) |
|--------|--------------|------------------|
| **Contre-marque** | OBLIGATOIRE | Aucune |
| **Lien OF → commande** | OUI (obligatoire) | NON |
| **Type OF** | WOP (Planifié) | WOS (Suggéré) |
| **Génération OF** | 1 commande = 1 WOP | Regroupement hebdo = 1 WOS |
| **Allocation stock** | **AUTOMATIQUE** | **MANUELLE** |
| **Clients** | Surtout ALDES | Tous clients (14) |
| **Articles** | Spécifiques/kits | Standards |
| **Traitement** | Manuel (1 par 1) | Automatisé (CBN/MRP) |
| **Entrée stock** | Oui | Oui |

## 🔧 Terminologie

### WOP - Work Order Planned
- Ordre de fabrication planifié
- Lien obligatoire avec une commande MTS
- Quantité = quantité de la commande
- Allocation automatique grâce au lien OF_CONTREMARQUE

### WOS - Work Order Suggested
- Ordre de fabrication suggéré
- PAS de lien avec les commandes
- Généré par le moteur CBN/MRP
- Regroupe les besoins par article et par semaine
- Allocation manuelle aux commandes

### Contre-marque
- Marquage qui lie une commande client à un OF spécifique
- Présent uniquement pour MTS (FLAG 5)
- Stock lié automatiquement à la commande
- Champ `OF_CONTREMARQUE` dans commandes_clients

### CBN/MRP
- Calcul des Besoins Nets / Material Requirements Planning
- Moteur de calcul pour NOR/MTO
- Regroupe les besoins hebdomadaires
- Génère des WOS suggérés

## 🔄 Exemples concrets

### MTS - Lien obligatoire + Allocation automatique
```
Commande: AR2600881 | ALDES | ESHKIT CPT HYGMW- BDH | 448 unités | FLAG 5 | OF="F426-07941"
    ↓
Génère: WOP F426-07941 pour 448 unités
    ↓
Fabriqué → Entrée en stock
    ↓
Allocation AUTOMATIQUE : Les 448 unités réservées pour AR2600881
```

### NOR/MTO - Regroupement CBN + Allocation manuelle
```
Commande 1: AR2600410 | AERECO | EAR2019GM | 360 unités | FLAG 1 | semaine 12
Commande 2: AR2600411 | AERECO | EAR2019GM | 360 unités | FLAG 1 | semaine 12
    ↓
Moteur CBN/MRP regroupe
    ↓
Génère: 1 WOS pour 720 unités (semaine 12)
    ↓
Fabriqué → Entrée en stock (720 disponibles)
    ↓
Allocation MANUELLE : 360 à AR2600410 + 360 à AR2600411
```

## 🎯 Points clés pour le développement

1. **Lien MTS** : `commandes_clients.OF_CONTREMARQUE` → `of_entetes.NUM_OF`
2. **Pas de lien NOR/MTO** : Les WOS ne sont pas liés aux commandes dans la base
3. **Allocation** : MTS = auto, NOR/MTO = manuel (champ QTE_ALLOUEE)
4. **Regroupement** : Le CBN regroupe par article et semaine pour NOR/MTO
5. **Clients** :
   - MTS : Principalement ALDES (80001)
   - NOR : Autres clients (AERECO, PARTN-AIR, KROBATH, etc.)
   - MTO : ALDES avec FLAG 1
6. **Types d'approvisionnement** :
   - ACHAT : Réceptions fournisseurs
   - FABRICATION : OF (WOP ou WOS)

## 📈 Statistiques actuelles

| Type | Nombre | % du total |
|------|--------|------------|
| MTS (FLAG 5) | 332 | 41% |
| NOR/MTO (FLAG 1) | 483 | 59% |

## 🔍 Requêtes utiles

### Articles MTS
```sql
SELECT DISTINCT cc.ARTICLE, a.DESCRIPTION, COUNT(*) as nb_commandes
FROM commandes_clients cc
JOIN articles a ON cc.ARTICLE = a.ARTICLE
WHERE cc.FLAG_CONTREMARQUE = 5
GROUP BY cc.ARTICLE, a.DESCRIPTION
ORDER BY nb_commandes DESC
```

### Commandes NOR/MTO par client
```sql
SELECT CODE_CLIENT, NOM_CLIENT, COUNT(*) as nb_commandes
FROM commandes_clients
WHERE FLAG_CONTREMARQUE = 1
GROUP BY CODE_CLIENT, NOM_CLIENT
ORDER BY nb_commandes DESC
```

### WOS regroupement hebdo
```sql
SELECT ARTICLE, WEEK(DATE_EXPEDITION_DEMANDEE, 1) as semaine,
       SUM(QTE_RESTANTE) as total_besoin
FROM commandes_clients
WHERE FLAG_CONTREMARQUE = 1 AND QTE_RESTANTE > 0
GROUP BY ARTICLE, semaine
ORDER BY ARTICLE, semaine
```

---

## 🔄 Processus d'ordonnancement

### Cycle hebdomadaire

#### 1. Réunion de charge (Tous les mardis)
- **Participants** : Supply + Production
- **Objectif** : Décider l'organisation des ateliers (2×8, 3×8, etc.)
- **Horizon** : S+1 à S+3 (semaine(s) suivante(s))
- **Base** : Charge de production calculée sur les cadences (`gammes.csv`)
- **Question clé** : "Quelle organisation pour répondre aux besoins de S+1/S+2/S+3 ?"

#### 2. Affermissement et lancement (Courant de semaine)
- L'ordonnanceur afermit les OF (WOP et WOS)
- Édition des dossiers de fabrication
- Lancement en production

### Règle d'affermissement
```
INTERDIT d'affermir un OF si un composant est en rupture
  ↓
SAUF si ce composant est un sous-ensemble ou semi-fini fabriqué (en interne)
```

**Exemple de la règle :**
- Composant ACHAT en rupture → ❌ INTERDIT d'affermir
- Composant FABRICATION en rupture → ✅ AUTORISÉ (car on peut lancer un OF pour le composant)

**Mais attention** : Si le composant FABRICATION a lui-même des composants en rupture, il faut vérifier récursivement !

### Contexte approvisionnement
- **Commandes clients** : Passées à 15-21 jours
- **Appros composants** : Délais moyens de 28 jours ou plus
- **Conséquence** : Les appros sont rarement déclenchées par les commandes clients
- **Solution** : Appros déclenchées sur la base de **prévisions** remontées hebdomadairement

---

## 🎯 Problème : Vérification faisabilité composants

### Le problème
Lors de la réunion de charge, on décide d'une organisation (ex: 2×8) pour S+1 à S+3.
**Question** : Comment vérifier qu'on aura les composants nécessaires pour réaliser la production ?

### Enjeux
- Si on valide un 2×8 mais que les composants manquent → Production bloquée
- Si on valide un OF mais que ses composants manquent -> OF bloqué
- L'ordonnanceur doit savoir quels OF sont réellement faisables

### Paramètres de vérification
- **Horizon** : S+1 à S+3 (pas seulement S+1)
- **Récursion** : Vérification complète jusqu'aux composants ACHAT
- **2 niveaux de vérification** :
  - **Immédiate** : Stock disponible uniquement
  - **Projetée** : Stock + réceptions fournisseurs (si date réception ≤ date besoin)

### Règle de nomenclature
- **1 article fabriqué = 1 nomenclature** (standard)
- **Nomenclatures disponibles dans `nomenclatures.csv`**
- **Couverture : 84%** des articles FABRICATION (2 501 / 2 964)
- Pour les 16% restants → Alerte "Nomenclature non disponible"

### Algorithme de vérification récursive
```
Pour chaque OF à vérifier:
  Pour chaque composant de la nomenclature:
    Si TYPE = ACHAT:
      Vérifier stock disponible (ou projeté avec réceptions)
    Si TYPE = FABRICATION:
      Vérifier récursivement les composants de cet article
```

---

## ⚖️ Gestion de la concurrence composants

### Le problème
Plusieurs OF peuvent nécessiter le même composant en même temps.

**Exemple :**
```
Stock disponible de E7368 : 1000 unités

OF A (F426-08419) → Besoin : 384 unités → Date : 13/03/2026
OF B (F426-08164) → Besoin : 800 unités → Date : 17/03/2026
OF C (F426-08734) → Besoin : 500 unités → Date : 30/03/2026

Total besoin : 1684 unités
Stock disponible : 1000 unités
→ Comment allouer le stock ?
```

### Approche 1 : Pas d'allocation virtuelle
```python
def verifier_sans_concurrence(liste_of):
    """
    Chaque OF est vérifié indépendamment
    Le stock disponible est le même pour tous
    Pas d'interaction entre OF
    """
    for of in liste_of:
        result = verifier_faisabilite_of(of)
        # Le stock est "virtuel" - pas d'allocation réelle
        # OF A et OF B voient tous les deux le même stock disponible
```

**Avantage** : Simple
**Risque** : Si on valide 2 OF alors que le stock ne suffit que pour 1

### Approche 2 : Gestion de la concurrence (2 règles)

**Règle 1 : Date de besoin**
- OF avec date besoin plus tôt = prioritaire

**Règle 2 : Faisabilité**
- Si un OF est 100% faisable avec le stock dispo → il passe **avant** un OF prioritaire mais non faisable

**Exemple :**
```
Stock disponible : 20 unités

OF A : Date 13/03, Besoin 30 → Pas faisable (manque 10)
OF B : Date 15/03, Besoin 20 → ✅ Faisable !

Sans règle 2:
  OF A (13/03) passe → alloue 20 → manque 10 → ❌ Bloqué
  OF B (15/03) après → plus de stock → ❌ Bloqué

Avec règle 2:
  OF B (15/03) passe → alloue 20 → ✅ Complet
  OF A (13/03) attend → (sera rejoué quand du stock arrive)
```

**Autre exemple :**
```
Stock : 50 unités

OF A : Date 10/03, Besoin 40 → ✅ Faisable
OF B : Date 12/03, Besoin 20 → ✅ Faisable
OF C : Date 14/03, Besoin 30 → Pas faisable

Ordre:
1. OF A (10/03) + faisable → Alloue 40 → Reste 10
2. OF B (12/03) + pas faisable (besoin 20, reste 10) → Passe
3. OF C (14/03) + pas faisable → Attend

Résultat : OF A validé, OF B rejeté (ou différé), OF C rejeté
```

**Principe** : Maximiser le nombre d'OF complètement faisables plutôt que respecter strictement l'ordre chronologique.

---

## 📋 Résumé des contraintes

| Aspect | Contrainte |
|--------|------------|
| **Horizon approvisionnement** | Appros sur prévisions (pas commandes clients) |
| **Horizon vérification** | S+1 à S+3 |
| **Récursion** | Vérification complète jusqu'aux composants ACHAT |
| **Niveaux vérification** | Immédiate (stock) + Projetée (stock + réceptions) |
| **Concurrence** | Gestion par date de besoin + faisabilité |
| **Règle affermissement** | Interdit si composant ACHAT en rupture |

---

## ✅ Disponibilité des données pour la vérification

### Ce qui est disponible

| Donnée | Fichier | Couverture | Utilité |
|--------|---------|------------|---------|
| **Nomenclatures** | `nomenclatures.csv` | 84% (2 501/2 964) | ⭐ Vérification récursive |
| **OF à vérifier** | `of_entetes.csv` | 15 285 OF | Identification des besoins |
| **Type approvisionnement** | `articles.csv` | 100% | Distinction ACHAT/FABRIQUÉ |
| **Stock disponible** | `stock.csv` | 99% (6 833/6 910) | Vérification immédiate |
| **Réceptions fournisseurs** | `receptions_oa.csv` | 520 articles | Vérification projetée |
| **Gammes de production** | `gammes.csv` | - | Non utilisé pour faisabilité composants |

### Points forts

✅ **Nomenclatures.csv résout le problème critique**
- Permet la vérification récursive complète
- Indépendante des OF existants
- Couvre 84% des articles FABRICATION

✅ **Données stock complètes**
- 99% des articles ont un enregistrement stock
- Stock physique, alloué, bloqué disponibles

✅ **Réponses fournisseurs**
- Dates de réception prévues disponibles
- Permettent la vérification "projetée"

### Limitations

⚠️ **16% d'articles FABRICATION sans nomenclature**
- ~463 articles non couverts
- Solution : Alerte "Nomenclature non disponible"
- Vérification manuelle requise pour ces cas

### Conclusion

**Les données sont SUFFISANTES pour implémenter la vérification de faisabilité :**
- ✅ Algorithme récursif fonctionnel
- ✅ Gestion de la concurrence possible
- ✅ 2 niveaux de vérification (immédiate/projetée)
- ⚠️ 16% de cas limites gérés par alertes

---

## 🎯 Algorithme de Matching Commande→OF

### Logique de matching pour NOR/MTO

**Pour les commandes NOR/MTO (FLAG = 1) :**

1. **Vérifier le stock disponible**
   - Allouer le stock disponible pour l'article
   - Si stock complet (besoin_net = 0) → Pas d'OF nécessaire
   - Sinon → Besoin net à couvrir par OF

2. **Vérifier le type d'article**
   - **Article ACHAT** → Pas d'OF, besoin d'approvisionnement fournisseur
   - **Article FABRICATION** → Chercher un OF (affermi prioritaire, puis suggéré)

3. **Recherche d'OF avec priorité**
   - **Priorité 1** : OF affermis (statut 1) - déjà lancés en production
   - **Priorité 2** : OF suggérés (statut 3) - créés par CBN/MRP
   - **Critères de tri** : Type d'OF → Date de besoin → Quantité disponible

4. **Partage d'OF**
   - Plusieurs commandes peuvent partager un OF si capacité suffisante
   - Suivi de consommation via `OFConso`

### Priorité de sélection des OF

```
Ordre de priorité :
1. Type d'OF : Affermi (statut 1) > Suggéré (statut 3)
2. Proximité de date : Écart croissant avec date d'expédition
3. Quantité disponible : Décroissante (pour minimiser le nombre d'OF)
```

**Clé de tri** : `(priorite, ecart_days, -qte_restante)`

### Résultats obtenus

**Taux de service NOR/MTO (S+1) :**
- Avant : 89.1% (115/129)
- Après : 99.2% (128/129)
- Gain : +13 commandes servies

**Répartition NOR/MTO :**
- 76.7% servies par stock complet
- 12.4% servies par OF affermi
- 10.1% servies par OF suggéré
- 0.8% articles ACHAT (besoin approvisionnement)
- 0.0% articles FABRICATION sans OF

### Exemple de fonctionnement

**Cas AR2600929 :**
- Commande : Article EMM716HU, 2160 unités pour le 25/03/2026
- OF disponible : F126-44769 (affermi, 2160 unités, 24/03/2026)
- Résultat : OF affermi utilisé (prioritaire sur les suggérés)

---

## 📊 Implémentations réalisées

### Matching commande→OF avec partage d'OF

**Fichier** : `src/algorithms/matching.py`

**Fonctionnalités :**
1. Allocation de stock avant recherche d'OF (utilise QTE_RESTANTE)
2. Distinction ACHAT vs FABRICATION
3. Priorité OF affermi > OF suggéré
4. Partage d'OF entre plusieurs commandes (via OFConso)
5. Gestion de la consommation des OF

**Classes clés :**
- `OFConso` : Suivi de la consommation d'un OF
- `StockAllocation` : Résultat de l'allocation de stock
- `MatchingResult` : Résultat du matching commande→OF

### Vérification de faisabilité des OF

**Fichiers** : `src/checkers/`

**Fonctionnalités :**
1. Vérification immédiate (stock actuel)
2. Vérification projetée (stock + réceptions fournisseurs)
3. Vérification récursive des nomenclatures jusqu'aux composants ACHAT
4. Gestion de la concurrence composants entre OF

---

## 🔧 Commandes utiles

### Lancer le mode S+1
```bash
python -m src.main --data-dir data --s1 --horizon 7
```

### Lancer avec un OF spécifique
```bash
python -m src.main --data-dir data --of F426-08419
```

### Lancer en mode détaillé
```bash
python -m src.main --data-dir data --detailed
```
