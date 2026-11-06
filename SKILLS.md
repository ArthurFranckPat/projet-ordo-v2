# Skills & Compétences - Ordonnancement Production v2

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATEUR AGENT                       │
│              (Sélectionne les compétences adaptées)          │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Organization │ │  Scheduling  │ │   LLM Decision│
│    Agent     │ │    Agent     │ │     Agent     │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│     TOOL 1   │ │     TOOL 2   │ │    TOOL N    │
│  (Basic API) │ │  (Basic API) │ │  (Basic API) │
└──────────────┘ └──────────────┘ └──────────────┘
```

**Principe architectural :**
- **Tools (Outils)** : Fonctions atomiques qui exposent une API simple
- **Skills/Agents** : Compétences métier qui combinent plusieurs outils
- **Orchestrateur** : Agent qui sélectionne la compétence adaptée à la tâche

---

## 🛠️ Tools (Outils disponibles)

Les outils sont des fonctions atomiques avec une API simple, réutilisables dans différentes compétences.

### 1. detect_bottlenecks - Détection de goulots

**Fichier** : `src/agents/tools/bottleneck_detector.py`

**Description** : Analyse la heatmap de charge et identifie les postes en saturation.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `charge_heatmap: Dict[str, Dict[str, float]]` - Heatmap des charges (semaine × poste)
- `capacite_nominal: float = 35.0` - Capacité nominale (heures/semaine)

**Sorties** :
- `List[BottleneckAlert]` avec :
  - `poste: str` - Code poste
  - `libelle: str` - Libellé poste
  - `semaine: str` - BACKLOG, EN_COURS, S+1, S+2, S+3
  - `charge_heures: float` - Charge calculée
  - `capacite_heures: float` - Capacité retenue
  - `taux_charge: float` - Taux de charge (0-1+)
  - `niveau: str` - "saturé", "tension", "sous_chargé"
  - `ofs_contributeurs: List[str]` - OFs les plus contributeurs

**Exemple d'utilisation** :
```python
from src.agents.tools import detect_bottlenecks

alerts = detect_bottlenecks(loader, heatmap, capacite_nominal=35.0)
for alert in alerts:
    print(f"{alert.poste}: {alert.taux_charge:.0%} - {alert.niveau}")
```

---

### 2. check_late_receptions_impact - Impact des réceptions tardives

**Fichier** : `src/agents/tools/late_receptions.py`

**Description** : Identifie les OFs impactés par des réceptions fournisseurs en retard.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `current_date: date` - Date de référence
- `horizon_days: int = 7` - Horizon d'analyse (jours)

**Sorties** :
- `LateReceptionImpact` avec :
  - `receptions_retard: List[Dict]` - Réceptions en retard
  - `ofs_impactes: Dict[str, List[str]]` - OFs impactés par article
  - `severity: str` - "critique", "modérée", "faible"

---

### 3. get_competing_ofs_for_component - Concurrence composants

**Fichier** : `src/agents/tools/component_competition.py`

**Description** : Identifie les OFs en concurrence pour les mêmes composants.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `article_composant: str` - Code du composant
- `date_reference: date` - Date de référence

**Sorties** :
- `ComponentCompetition` avec :
  - `article_composant: str` - Composant analysé
  - `stock_disponible: int` - Stock disponible
  - `ofs_concurrents: List[CompetingOF]` - OFs en concurrence
  - `total_besoin: int` - Besoin total
  - `ratio_couverture: float` - Ratio couverture

---

### 4. suggest_ofs_to_affirm - Suggestions d'affermissement

**Fichier** : `src/agents/tools/of_affirm_suggester.py`

**Description** : Suggère les OFs à afermir en priorité.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `horizon_semaines: int = 4` - Horizon d'analyse
- `reference_date: date = None` - Date de référence

**Sorties** :
- `OFAffirmSuggestion` avec :
  - `ofs_affirmables: List[Dict]` - OFs suggérés
  - `ofs_non_affirmables: List[Dict]` - OFs non faisables
  - `affirmation_plan: AffirmationPlan` - Plan d'affermissement
  - `rationale: str` - Rationnel des choix

---

### 5. sequence_ofs_for_poste - Séquencement OFs

**Fichier** : `src/agents/tools/of_sequencer.py`

**Description** : Séquence les OFs pour un poste donné selon des règles de priorité.

**Entrées** :
- `ofs: List[OF]` - OFs à séquencer
- `poste: str` - Code du poste
- `loader: DataLoader` - Accès aux données (pour gammes)

**Sorties** :
- `OFSequence` avec :
  - `poste: str` - Poste de charge
  - `ofs_sequences: List[SequencedOF]` - OFs séquencés
  - `total_heures: float` - Temps total
  - `rang_final: int` - Rang final du poste

---

### 6. get_rescheduling_messages - Messages de report

**Fichier** : `src/agents/tools/rescheduling_messages.py`

**Description** : Génère les messages de report pour les OFs décalés.

**Entrées** :
- `ofs_recalled: List[Dict]` - OFs à décaler
- `current_date: date` - Date de référence
- `reason: str` - Raison du report

**Sorties** :
- `List[ReschedulingMessage]` avec :
  - `num_of: str` - Numéro OF
  - `client: str` - Client impacté
  - `ancienne_date: date` - Date initiale
  - `nouvelle_date: date` - Date proposée
  - `message: str` - Message formaté

---

### 7. simulate_schedule_impact - Simulation de scénarios

**Fichier** : `src/agents/tools/schedule_simulator.py`

**Description** : Simule l'impact d'un plan de charge sur les délais.

**Entrées** :
- `ofs_planifies: List[Dict]` - OFs planifiés
- `organization: str` - Organisation (2x8, 3x8)
- `loader: DataLoader` - Accès aux données

**Sorties** :
- `SimulationResult` avec :
  - `impact_delai: Dict[str, int]` - Impact délai par OF
  - `ofs_risque: List[str]` - OFs à risque
  - `taux_service: float` - Taux de service simulé

---

### 8. get_service_rate_kpis - KPIs taux de service

**Fichier** : `src/agents/tools/service_rate_kpis.py`

**Description** : Calcule les KPIs de taux de service.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `horizon_semaines: int = 4` - Horizon d'analyse

**Sorties** :
- `ServiceRateKPIs` avec :
  - `taux_service_global: float` - Taux global
  - `taux_par_client: Dict[str, float]` - Taux par client
  - `commandes_en_retard: List[str]` - Commandes en retard
  - `evolution: List[float]` - Evolution hebdo

---

### 9. summarize_week_status - Résumé hebdomadaire

**Fichier** : `src/agents/tools/week_summary.py`

**Description** : Génère un résumé du statut de la semaine.

**Entrées** :
- `loader: DataLoader` - Accès aux données
- `semaine: str` - Semaine cible (ex: "2026-W12")
- `reference_date: date = None` - Date de référence

**Sorties** :
- `WeekSummary` avec :
  - `semaine: str` - Semaine analysée
  - `ofs_actifs: int` - Nombre d'OFs actifs
  - `ofs_affirmes: int` - OFs affermis
  - `ofs_suggeres: int` - OFs suggérés
  - `top_postes: List[Tuple[str, float]]` - Top postes de charge
  - `alertes: List[str]` - Alertes

---

## 🤖 Skills / Agents (Compétences métier)

Les compétences combinent plusieurs outils pour résoudre des problèmes métier complexes.

### 1. OrganizationAgent - Analyse d'organisation

**Fichier** : `src/agents/organization/organization_agent.py`

**Description** : Analyse et recommande l'organisation des ateliers (2×8, 3×8, etc.).

**Outils utilisés** :
- `calculate_weekly_charge_heatmap` - Calcul des charges
- `detect_bottlenecks` - Détection des goulots
- `summarize_week_status` - Résumé hebdomadaire

**Entrées** :
- `reference_date: date = None` - Date de référence
- `matcher: CommandeOFMatcher = None` - Matcher commande→OF

**Sorties** :
- `Dict[str, PosteChargeResult]` avec :
  - Clé: Code poste (PP_xxx)
  - Valeur: Organisation recommandée (2×8, 3×8, etc.)

**Workflow** :
1. Calculer la charge par poste sur 4 semaines
2. Analyser les tendances
3. Évaluer les organisations possibles
4. Recommander l'organisation optimale

**Exemple d'utilisation** :
```python
from src.agents.organization import OrganizationAgent

agent = OrganizationAgent(loader)
result = agent.analyze_workshop_organization(reference_date=date(2026, 3, 24))
for poste, org_result in result.items():
    print(f"{poste}: {org_result.organization_recommandee}")
```

---

### 2. SchedulingAgent - Planification de charge

**Fichier** : `src/agents/scheduling/scheduling_agent.py`

**Description** : Construit le plan de charge hebdomadaire optimisé.

**Outils utilisés** :
- `detect_bottlenecks` - Identifier les gaps
- `suggest_ofs_to_affirm` - Suggestions d'affermissement
- `sequence_ofs_for_poste` - Séquencement
- `simulate_schedule_impact` - Simulation

**Entrées** :
- `s1_feasible_ofs: List[OF]` - OFs faisables S+1
- `feasibility_results: Dict` - Résultats de faisabilité
- `reference_date: date = None` - Date de référence
- `matcher: CommandeOFMatcher = None` - Matcher commande→OF

**Sorties** :
- `SchedulingResult` avec :
  - `plan_semaine: Dict[str, PosteSchedule]` - Plan par poste
  - `candidats_selectionnes: List[CandidateOF]` - OFs sélectionnés
  - `gaps_resolus: List[str]` - Gaps résolus
  - `kpi_amelioration: Dict` - KPIs d'amélioration

**Workflow** :
1. Extraire les composants en rupture depuis S+1
2. Calculer la charge S+1 par poste
3. Identifier les postes en gap
4. Chercher des OFs S+2/S+3 faisables
5. Scorer et sélectionner les candidats
6. Retourner le plan recommandé

---

### 3. LLM Decision Agent - Décision métier assistée par LLM

**Fichier** : `src/agents/llm/llm_decision_rule.py`

**Description** : Prend des décisions métier nuancées (ACCEPT, DEFER, REJECT) pour les OFs.

**Outils utilisés** :
- `check_late_receptions_impact` - Réceptions tardives
- `get_competing_ofs_for_component` - Concurrence composants
- `get_service_rate_kpis` - KPIs

**Entrées** :
- `of: OF` - OF à analyser
- `commande: BesoinClient = None` - Commande associée
- `current_date: date = None` - Date de référence

**Sorties** :
- `DecisionResult` avec :
  - `action: str` - ACCEPT_AS_IS, ACCEPT_PARTIAL, DEFER, DEFER_PARTIAL, REJECT
  - `reason: str` - Raison de la décision
  - `modified_quantity: int = None` - Quantité modifiée
  - `defer_date: str = None` - Date de report
  - `action_required: str` - Action requise
  - `confidence: float` - Confiance (0-1)
  - `metadata: LLMDecisionMetadata` - Métadonnées structurées

**Workflow** :
1. Analyser le contexte (OF, commande, composants)
2. Pré-filtrage : Cas évidents sans appel LLM
3. Construction du prompt structuré
4. Appel au LLM (Mistral)
5. Parsing et validation de la réponse
6. Fallback si erreur

---

## 🎯 Comment recréer ces skills sur Claude ou autre plateforme

### Étape 1 : Créer les tools (fonctions de base)

Sur Claude Code ou une autre plateforme, créez des fonctions avec les mêmes signatures :

```python
# Exemple : Tool detect_bottlenecks
def detect_bottlenecks(
    charge_heatmap: Dict[str, Dict[str, float]],
    capacite_nominal: float = 35.0
) -> List[Dict]:
    """Analyse la heatmap de charge et identifie les goulots."""
    alerts = []
    for semaine, postes in charge_heatmap.items():
        for poste, charge in postes.items():
            taux = charge / capacite_nominal
            if taux >= 1.00:
                alerts.append({
                    "poste": poste,
                    "semaine": semaine,
                    "taux": taux,
                    "niveau": "saturé"
                })
    return alerts
```

### Étape 2 : Créer les prompts de compétences

Pour chaque compétence, créez un prompt qui décrit :

**Prompt OrganizationAgent** :
```
Tu es un expert en ordonnancement production.

Ta compétence : ANALYSE D'ORGANISATION

Tu as accès à ces outils :
- calculate_weekly_charge_heatmap(loader, horizon_semaines)
- detect_bottlenecks(charge_heatmap, capacite_nominal)
- summarize_week_status(loader, semaine)

Ta tâche :
1. Calculer la charge par poste sur les 4 prochaines semaines
2. Identifier les postes en goulot d'étranglement
3. Recommander l'organisation optimale (2×8, 3×8) pour chaque poste

Format de réponse attendu :
{
  "poste": "PP_XXX",
  "organization": "2×8" | "3×8" | "1×8",
  "rationale": "explication",
  "charge_semaine_1": 45.5,
  "capacite": 70.0
}
```

**Prompt SchedulingAgent** :
```
Tu es un expert en ordonnancement production.

Ta compétence : PLANIFICATION DE CHARGE

Tu as accès à ces outils :
- detect_bottlenecks(charge_heatmap, capacite_nominal)
- suggest_ofs_to_affirm(loader, horizon_semaines)
- sequence_ofs_for_poste(ofs, poste, loader)
- simulate_schedule_impact(ofs_planifies, organization, loader)

Ta tâche :
1. Identifier les postes en gap S+1
2. Chercher des OFs S+2/S+3 faisables pour combler les gaps
3. Sélectionner et séquencer les OFs optimaux
4. Simuler l'impact du plan

Format de réponse attendu :
{
  "plan_semaine": {
    "PP_XXX": {
      "ofs_selectionnes": ["F426-08419", "F426-08164"],
      "charge_totale": 68.5,
      "organisation": "2×8"
    }
  }
}
```

**Prompt LLMDecisionAgent** :
```
Tu es un expert en ordonnancement production.

Ta compétence : DÉCISION MÉTIER NUANCÉE

Ta tâche : Analyser un OF et proposer une décision parmi :
- ACCEPT_AS_IS: L'OF est faisable en l'état
- ACCEPT_PARTIAL: L'OF est partiellement faisable
- DEFER: L'OF sera faisable plus tard
- DEFER_PARTIAL: Report avec acceptation partielle
- REJECT: L'OF n'est pas faisable

Contexte fourni :
- Informations OF (numéro, article, quantité, date)
- Informations commande (si disponible)
- Analyse des composants (stock, allocation, situation)
- Composants critiques

Format de réponse OBLIGATOIRE (JSON uniquement) :
{
  "action": "ACCEPT_AS_IS",
  "reason": "raison en 2-3 phrases",
  "modified_quantity": null,
  "defer_date": null,
  "action_required": "action concrète",
  "confidence": 0.8,
  "metadata": {
    "composants_limitants": [],
    "situation": "disponible",
    "delai_estime": null,
    "action_nature": null
  }
}
```

### Étape 3 : Créer l'orchestrateur

Créez un agent orchestrateur qui route vers la bonne compétence :

```
Tu es un orchestrateur pour l'ordonnancement production.

Tu as accès à ces compétences :
- OrganizationAgent : Analyse et recommande l'organisation des ateliers
- SchedulingAgent : Planifie la charge hebdomadaire
- LLMDecisionAgent : Prend des décisions métier nuancées

Route la demande de l'utilisateur vers la bonne compétence :

→ "Quelle organisation pour S+1 ?" → OrganizationAgent
→ "Comment combler les gaps S+1 ?" → SchedulingAgent
→ "Est-ce que cet OF est faisable ?" → LLMDecisionAgent
→ "Dois-je afermir cet OF ?" → LLMDecisionAgent
```

---

## 📋 Récapitulatif

| Niveau | Nombre | Description |
|--------|--------|-------------|
| **Tools** | 9 | Fonctions atomiques réutilisables |
| **Skills/Agents** | 3 | Compétences métier combinant des tools |
| **Orchestrateur** | 1 | Agent qui route vers les skills |

### Tools disponibles
1. `detect_bottlenecks` - Détection de goulots
2. `check_late_receptions_impact` - Impact réceptions tardives
3. `get_competing_ofs_for_component` - Concurrence composants
4. `suggest_ofs_to_affirm` - Suggestions d'affermissement
5. `sequence_ofs_for_poste` - Séquencement OFs
6. `get_rescheduling_messages` - Messages de report
7. `simulate_schedule_impact` - Simulation scénarios
8. `get_service_rate_kpis` - KPIs taux de service
9. `summarize_week_status` - Résumé hebdomadaire

### Compétences disponibles
1. **OrganizationAgent** - Analyse d'organisation atelier
2. **SchedulingAgent** - Planification de charge
3. **LLMDecisionAgent** - Décision métier assistée par LLM

---

## 🔄 Flux de travail typique

```
Utilisateur : "Quelle organisation pour S+1 ?"
    ↓
Orchestrateur : Route vers OrganizationAgent
    ↓
OrganizationAgent :
    1. calculate_weekly_charge_heatmap()
    2. detect_bottlenecks()
    3. summarize_week_status()
    ↓
Résultat : "Recommandé : 2×8 sur PP_105, 3×8 sur PP_120"
```

```
Utilisateur : "Est-ce que l'OF F426-08419 est faisable ?"
    ↓
Orchestrateur : Route vers LLMDecisionAgent
    ↓
LLMDecisionAgent :
    1. Analyser le contexte OF
    2. check_late_receptions_impact()
    3. get_competing_ofs_for_component()
    4. Appel LLM
    ↓
Résultat : "ACCEPT_AS_IS : Tous les composants disponibles"
```

---

## 📦 Dépendances

Les tools et agents dépendent de :

- `DataLoader` : Accès aux données (OF, commandes, stock, nomenclatures)
- `CommandeOFMatcher` : Matching commande→OF
- `OF`, `BesoinClient` : Modèles de données

Pour recréer sur une autre plateforme, vous devez fournir :
1. Un accès aux données (via API ou fichiers)
2. Les modèles de données équivalents
3. Une implémentation des outils de base

---

## 🎓 Utilisation pédagogique

Ce référentiel de compétences peut servir de base pour :
- Former des agents d'ordonnancement sur d'autres systèmes ERP
- Créer des démonstrateurs de capacités IA
- Enseigner les principes d'architecture multi-agents
- Benchmark de différentes plateformes d'IA

La structure modulaire (tools → skills → orchestrator) est un pattern réutilisable dans d'autres domaines.
