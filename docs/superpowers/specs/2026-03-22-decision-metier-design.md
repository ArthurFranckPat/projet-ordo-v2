# Design Document - Couche Décision Métier

**Date** : 2026-03-22
**Auteur** : Claude
**Statut** : Draft

---

## 1. Résumé

Ce document décrit l'architecture et l'implémentation d'une **couche décision métier** pour le système d'ordonnancement. Cette couche permet de prendre des décisions nuancées (acceptation partielle, report, rejet) basées sur des critères métier configurables, plutôt qu'une approche binaire (faisable/non faisable).

### Cas motivant

Composant 11019971 :
- Besoin : 147 unités
- Stock disponible : 145 unités
- Manque : 2 unités (1.4%)

**Actuellement** : OF rejeté (0/147 servi)
**Avec décision métier** : OF accepté pour 145 unités (98.6%)

---

## 2. Architecture

### 2.1 Structure du module

```
src/decisions/
├── __init__.py              # Exports publics
├── models.py                # DecisionAction, DecisionResult, DecisionContext
├── engine.py                # DecisionEngine (orchestrateur)
├── smart_rule.py            # SmartDecisionRule (règle unifiée)
├── criteria/
│   ├── __init__.py          # Exports des critères
│   ├── base.py              # BaseCriterion (interface)
│   ├── completion.py        # CompletionCriterion
│   ├── client.py            # ClientCriterion
│   └── urgency.py           # UrgencyCriterion
├── config.py                # Chargeur de configuration YAML
├── persistence.py           # Historique JSON
└── reports.py               # Génération de rapports

config/
└── decisions.yaml           # Configuration centralisée

data/
└── decisions_history.json   # Historique (auto-généré)

tests/decisions/
├── test_criteria/           # Tests unitaires des critères
├── test_smart_rule.py       # Tests de la règle unifiée
├── test_engine.py           # Tests du moteur
└── test_integration.py      # Tests d'intégration
```

### 2.2 Flux de données

```
DataLoader
    ↓
DecisionEngine (pré-allocation)
    ├─ SmartDecisionRule.evaluate()
    │   ├─ CompletionCriterion.score()
    │   ├─ ClientCriterion.score()
    │   └─ UrgencyCriterion.score()
    └─ Décision: ACCEPT_PARTIAL → modifie OF.qte_restante
    ↓
AllocationManager (allocation virtuelle)
    ↓
DecisionEngine (post-allocation)
    ├─ SmartDecisionRule.evaluate()
    └─ Décision: DEFER/REJECT
    ↓
AllocationResult + DecisionResult
    ↓
Persistance JSON + Rapports
```

---

## 3. Models

### 3.1 DecisionAction (Enum)

Actions possibles après décision métier :

- `ACCEPT_AS_IS` : OF accepté tel quel
- `ACCEPT_PARTIAL` : OF accepté avec quantité réduite
- `REJECT` : OF rejeté
- `DEFER` : OF reporté
- `DEFER_PARTIAL` : Partie immédiate + partie reportée

### 3.2 DecisionResult (Dataclass)

```python
@dataclass
class DecisionResult:
    action: DecisionAction
    reason: str                         # Explication courte
    modified_quantity: Optional[int]     # Pour ACCEPT_PARTIAL
    defer_date: Optional[date]           # Pour DEFER
    metadata: Dict[str, Any]            # Métadonnées détaillées
    timestamp: datetime                  # Timestamp de la décision
```

**metadata contient :**
- `original_quantity` : Quantité avant décision
- `completion_rate` : Taux de complétion
- `missing_components` : Composants manquants
- `criteria_scores` : Scores par critère
- `weighted_score` : Score pondéré final
- `rule_applied` : Règle appliquée

### 3.3 DecisionContext (Dataclass)

Contexte disponible pour les critères :

```python
@dataclass
class DecisionContext:
    of: OF
    commande: Optional[CommandeClient]
    feasibility_result: Optional[FeasibilityResult]
    available_stock: Dict[str, int]
    allocated_stock: Dict[str, int]
    competing_ofs: List[OF]
    current_date: Optional[date]
```

---

## 4. Critères de Décision

### 4.1 Interface BaseCriterion

```python
class BaseCriterion(ABC):
    CRITERION_ID: str
    CRITERION_NAME: str
    DESCRIPTION: str

    @abstractmethod
    def score(self, context: DecisionContext) -> float:
        """Score 0.0 (défavorable) à 1.0 (favorable)"""
        pass

    @abstractmethod
    def suggest_action(self, context: DecisionContext, score: float) -> Optional[DecisionAction]:
        """Suggère une action basée sur le score"""
        pass

    def is_applicable(self, context: DecisionContext) -> bool:
        """Vérifie si le critère s'applique"""
        return True
```

### 4.2 CompletionCriterion

**Rôle** : Évalue le taux de complétion de l'OF.

**Scoring** :
- 1.0 si ≥ 95% (target)
- 0.0 si ≤ 80% (min acceptable)
- Interpolation linéaire entre les deux

**Suggestion** :
- Score 1.0 → `ACCEPT_AS_IS`
- Score ≥ 0.8 + gap ≤ 10 unités → `ACCEPT_PARTIAL`

**Configuration** :
```yaml
completion:
  min_acceptable_rate: 0.80
  target_completion_rate: 0.95
  max_absolute_gap: 10
```

### 4.3 ClientCriterion

**Rôle** : Priorise les clients stratégiques.

**Scoring** :
- 1.0 : Client prioritaire (ALDES)
- 0.8 : Client stratégique (AERECO, PARTN-AIR)
- 0.5 : Client standard

**Suggestion** :
- Client prioritaire + gap ≤ 5% → `ACCEPT_AS_IS`

**Configuration** :
```yaml
client:
  priority_clients: [ALDES]
  strategic_clients: [AERECO, PARTN-AIR]
  priority_client_max_gap: 0.05
```

### 4.4 UrgencyCriterion

**Rôle** : Évalue l'urgence temporelle de l'OF.

**Scoring** :
- 1.0 : Très urgent (≤ 3 jours)
- 0.8 : Urgent (≤ 7 jours)
- 0.5 : Comfortable (≤ 21 jours)
- 0.3 : Beaucoup de temps

**Suggestion** :
- Très urgent + gap ≤ 5% → `ACCEPT_AS_IS`
- Urgent + gap ≤ 2% → `ACCEPT_AS_IS`

**Configuration** :
```yaml
urgency:
  very_urgent_days: 3
  urgent_days: 7
  comfortable_days: 21
  very_urgent_tolerance: 0.05
  urgent_tolerance: 0.02
```

---

## 5. SmartDecisionRule

### 5.1 Rôle

Règle unifiée qui combine tous les critères avec un système de scoring pondéré.

### 5.2 Algorithme

1. **Calculer les scores** de chaque critère applicable
2. **Calculer le score pondéré** :
   ```
   weighted_score = Σ(score_i × weight_i)
   ```
3. **Récupérer les suggestions** explicites des critères
4. **Décider l'action** :
   - Si suggestions explicites → utiliser la meilleure
   - Sinon, basé sur le score pondéré :
     - ≥ 0.7 → `ACCEPT_AS_IS`
     - ≤ 0.3 → `REJECT`
     - Entre les deux → vérifier `ACCEPT_PARTIAL`
5. **Générer raison et métadonnées**

### 5.3 Poids par défaut

```yaml
criteria_weights:
  completion: 0.5
  client: 0.3
  urgency: 0.2
```

---

## 6. Configuration

### 6.1 Fichier YAML

```yaml
# config/decisions.yaml

smart_rule:
  enabled: true
  criteria_weights:
    completion: 0.5
    client: 0.3
    urgency: 0.2

completion:
  min_acceptable_rate: 0.80
  target_completion_rate: 0.95
  max_absolute_gap: 10

client:
  priority_clients: [ALDES]
  strategic_clients: [AERECO, PARTN-AIR]
  priority_client_max_gap: 0.05

urgency:
  very_urgent_days: 3
  urgent_days: 7
  comfortable_days: 21
  very_urgent_tolerance: 0.05
  urgent_tolerance: 0.02

thresholds:
  accept_threshold: 0.7
  reject_threshold: 0.3

persistence:
  enabled: true
  file_path: "data/decisions_history.json"
  max_entries: 10000

reports:
  enabled: true
  output_dir: "reports/decisions"
  format: ["markdown", "json"]
```

### 6.2 Chargement de configuration

```python
import yaml

def load_config(config_path: str = "config/decisions.yaml") -> Dict[str, Any]:
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)
```

---

## 7. Intégration

### 7.1 AllocationManager

**Modifications à `src/algorithms/allocation.py`** :

1. Ajouter paramètre `decision_engine` au `__init__`
2. **Pré-allocation** :
   - Évaluer tous les OF avec `DecisionEngine.evaluate_pre_allocation()`
   - Sauvegarder les quantités originales
   - Appliquer `ACCEPT_PARTIAL` (modifier `OF.qte_restante`)
   - Lancer l'allocation virtuelle
   - Restaurer les quantités originales
3. **Post-allocation** :
   - Pour les OF `NOT_FEASIBLE` sans décision pré-allocation
   - Évaluer avec `DecisionEngine.evaluate_post_allocation()`
   - Appliquer `DEFER` ou `REJECT`

### 7.2 Enrichissement AllocationResult

```python
@dataclass
class AllocationResult:
    of_num: str
    status: AllocationStatus
    feasibility_result: Optional[FeasibilityResult] = None
    allocated_quantity: dict[str, int] = None
    decision: Optional[DecisionResult] = None  # NOUVEAU
```

---

## 8. Persistance

### 8.1 DecisionPersistence

**Fichier** : `src/decisions/persistence.py`

**Fonctionnalités** :
- Sauvegarder chaque décision dans `data/decisions_history.json`
- Format JSON avec timestamp, OF, action, reason, metadata
- Rotation automatique après X entrées (défaut: 10000)

**Structure d'une entrée** :
```json
{
  "timestamp": "2026-03-22T10:30:00",
  "of_num": "F426-08419",
  "phase": "pre",
  "action": "accept_partial",
  "reason": "Score 0.85 → Accepter 98.6% (145/147)",
  "modified_quantity": 145,
  "metadata": {
    "weighted_score": 0.85,
    "criteria_scores": {"completion": 1.0, "client": 0.5, "urgency": 0.8},
    "original_quantity": 147
  }
}
```

---

## 9. Rapports

### 9.1 DecisionReporter

**Fichier** : `src/decisions/reports.py`

**Fonctionnalités** :
- `generate_markdown_report()` : Rapport lisible
- `generate_json_report()` : Rapport machine-readable

### 9.2 Format Markdown

```markdown
# Rapport de Décisions Métier

Généré le : 22/03/2026 10:30

## Résumé

- Total OFs traités : 150
- OFs avec décision : 23

### Par action

- **accept_as_is** : 15
- **accept_partial** : 5
- **defer** : 2
- **reject** : 1

## Détail par OF

### F426-08419

- **Action** : accept_partial
- **Raison** : Score 0.85 → Accepter 98.6% (145/147)
- **Quantité modifiée** : 145
- **Score** : 0.85
```

---

## 10. Tests

### 10.1 Tests unitaires

**Fichiers** :
- `tests/decisions/test_criteria/test_completion.py`
- `tests/decisions/test_criteria/test_client.py`
- `tests/decisions/test_criteria/test_urgency.py`
- `tests/decisions/test_smart_rule.py`
- `tests/decisions/test_engine.py`

**Exemple de test** :
```python
def test_completion_criterion_98_6_percent():
    """Test le cas motivant : 145/147 (98.6%)"""

    of = OF(num_of="F426-TEST", article="TEST", qte_restante=147)

    feasibility = FeasibilityResult(feasible=False)
    feasibility.add_missing("11019971", 2)

    context = DecisionContext(
        of=of,
        feasibility_result=feasibility,
        available_stock={"11019971": 145}
    )

    criterion = CompletionCriterion({
        "target_completion_rate": 0.95,
        "max_absolute_gap": 10
    })

    score = criterion.score(context)
    action = criterion.suggest_action(context, score)

    assert score == 1.0
    assert action == DecisionAction.ACCEPT_PARTIAL
```

### 10.2 Tests d'intégration

**Fichier** : `tests/decisions/test_integration.py`

**Scénarios** :
- DecisionEngine + AllocationManager complet
- Vérification de l'enrichissement de AllocationResult
- Vérification de la persistance
- Vérification des rapports

---

## 11. Implémentation

### 11.1 Ordre d'implémentation

1. **Models** (`models.py`)
2. **Interface critère** (`criteria/base.py`)
3. **Critères** (`criteria/completion.py`, `client.py`, `urgency.py`)
4. **Configuration** (`config.py`)
5. **SmartDecisionRule** (`smart_rule.py`)
6. **DecisionEngine** (`engine.py`)
7. **Persistance** (`persistence.py`)
8. **Rapports** (`reports.py`)
9. **Intégration AllocationManager** (`allocation.py`)
10. **Tests**

### 11.2 Fichiers à créer

- `src/decisions/__init__.py`
- `src/decisions/models.py`
- `src/decisions/engine.py`
- `src/decisions/smart_rule.py`
- `src/decisions/config.py`
- `src/decisions/criteria/__init__.py`
- `src/decisions/criteria/base.py`
- `src/decisions/criteria/completion.py`
- `src/decisions/criteria/client.py`
- `src/decisions/criteria/urgency.py`
- `src/decisions/persistence.py`
- `src/decisions/reports.py`
- `config/decisions.yaml`
- Tests correspondants

### 11.3 Fichiers à modifier

- `src/algorithms/allocation.py` (intégration DecisionEngine)
- `src/models/__init__.py` (exports)
- `requirements.txt` (ajouter PyYAML si nécessaire)

---

## 12. Risques et Mitigations

### 12.1 Risques

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Performance (temps de calcul) | Moyen | Cache des scores, évaluation paresseuse |
| Complexité de configuration | Moyen | Valeurs par défaut raisonnables, documentation |
| Conflits entre critères | Faible | Règle unifiée avec scoring, pas priorité stricte |
| Trop d'acceptations partielles | Moyen | Seuils configurables, monitoring |

### 12.2 Stratégie de déploiement

1. **Phase 1** : Développement et tests unitaires
2. **Phase 2** : Tests d'intégration sur données réelles
3. **Phase 3** : Déploiement en mode "audit" (décisions calculées mais pas appliquées)
4. **Phase 4** : Déploiement progressif (commencer par ACCEPT_PARTIAL uniquement)
5. **Phase 5** : Déploiement complet

---

## 13. Success Criteria

Le système est considéré réussi si :

1. ✅ Le cas motivant (145/147) est accepté à 98.6%
2. ✅ Taux de service client augmente (mesure avant/après)
3. ✅ Aucune régression sur les OFs 100% faisables
4. ✅ Décisions explicables (reason + metadata)
5. ✅ Configuration modifiable sans changer le code
6. ✅ Tests coverage ≥ 80%
7. ✅ Performance : < 2 secondes pour 100 OFs

---

## 14. Évolutions futures

### 14.1 Nouveaux critères

- **GeographicCriterion** : Priorité par région
- **ValueCriterion** : Priorité par valeur de commande
- **SeasonalityCriterion** : Ajustements saisonniers

### 14.2 Machine Learning

- Utiliser l'historique des décisions pour entraîner un modèle
- Suggérer des ajustements de seuils
- Prédire les risques de rupture

### 14.3 Interface utilisateur

- Dashboard de visualisation des décisions
- Interface de modification de la configuration
- Validation interactive des décisions

---

## 15. Références

- Plan original : `.claude/plans/decision-metier.md`
- Code existant : `src/algorithms/allocation.py`, `src/checkers/`
- Configuration : PyYAML https://pyyaml.org/
