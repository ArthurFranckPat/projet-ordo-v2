"""Analyseur de résultats du scheduler.

Prend le SchedulerResult + les outils d'agent existants et produit
une analyse structurée prête à être formatée.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ...loaders.data_loader import DataLoader
from ...scheduler.models import SchedulerResult, CandidateOF
from ..tools.rescheduling_messages import ReschedulingMessage, get_rescheduling_messages
from ..tools.late_receptions import LateReceptionImpact, check_late_receptions_impact
from ..tools.bottleneck_detector import BottleneckAlert, detect_bottlenecks
from ..tools.service_rate_kpis import ServiceRateKPIs, get_service_rate_kpis
from .config import AnalysisConfig


@dataclass
class LineAnalysis:
    """Analyse d'une ligne de production."""
    line: str
    total_ofs: int
    total_hours: float
    charge_by_day: dict[str, float] = field(default_factory=dict)
    ofs_non_planifies: list[dict] = field(default_factory=list)
    changements_serie: int = 0


@dataclass
class AlerteOrdonnanceur:
    """Une alerte pour l'ordonnanceur."""
    niveau: str  # CRITIQUE, ATTENTION, INFO
    categorie: str  # SERVICE, CAPACITE, MATERIEL, GOULOT
    message: str
    action: str
    details: Optional[dict] = None


@dataclass
class AnalyseResult:
    """Résultat complet de l'analyse ordonnancement."""
    date_analyse: date
    mode: str  # "quotidien" ou "hebdomadaire"

    # KPIs scheduler
    score: float
    taux_service: float
    taux_ouverture: float
    nb_deviations: int
    nb_jit: int
    nb_changements_serie: int

    # Détail par ligne
    lignes: list[LineAnalysis] = field(default_factory=list)

    # OFs non planifiés
    ofs_non_planifies: list[dict] = field(default_factory=list)
    nb_ofs_non_planifies: int = 0

    # Alertes scheduler
    alertes_scheduler: list[str] = field(default_factory=list)

    # Outils agent
    messages_reordonnancement: list[ReschedulingMessage] = field(default_factory=list)
    receptions_en_retard: list[LateReceptionImpact] = field(default_factory=list)
    alertes_goulots: list[BottleneckAlert] = field(default_factory=list)
    kpis_service: Optional[ServiceRateKPIs] = None

    # Alertes consolidées
    alertes: list[AlerteOrdonnanceur] = field(default_factory=list)

    # Stock BDH projeté
    stock_bdh_projete: list[dict] = field(default_factory=list)

    # Order rows (lignes de commande avec statut)
    order_rows: list[dict] = field(default_factory=list)


def analyze_scheduler_result(
    result: SchedulerResult,
    loader: DataLoader,
    config: AnalysisConfig,
    reference_date: date,
    mode: str = "quotidien",
) -> AnalyseResult:
    """Analyse complète du résultat du scheduler.

    Combine :
    1. Les KPIs du scheduler (score, taux_service, taux_ouverture)
    2. L'analyse par ligne (charge, OFs non planifiés)
    3. Les outils agent existants (messages, réceptions, goulots, KPIs)
    4. La consolidation des alertes
    """
    # 1. Analyse par ligne
    lignes = _analyze_lines(result)

    # 2. Outils agent
    messages = get_rescheduling_messages(loader, reference_date)
    receptions_retard = check_late_receptions_impact(loader, reference_date)
    goulots = detect_bottlenecks(
        loader, reference_date,
        num_weeks=config.num_weeks_heatmap,
        capacite_par_poste=None,
    )
    kpis = get_service_rate_kpis(loader, reference_date, capacite_par_poste=None)

    # 3. Alertes consolidées
    alertes = _consolidate_alertes(
        result=result,
        lignes=lignes,
        messages=messages,
        receptions_retard=receptions_retard,
        goulots=goulots,
        kpis=kpis,
        config=config,
    )

    # 4. OFs non planifiés (top N)
    ofs_non_planifies = sorted(
        result.unscheduled_rows,
        key=lambda r: (r.get("date_echeance", ""), r.get("ligne", "")),
    )[:config.max_ofs_non_planifies_report]

    return AnalyseResult(
        date_analyse=reference_date,
        mode=mode,
        score=result.score,
        taux_service=result.taux_service,
        taux_ouverture=result.taux_ouverture,
        nb_deviations=result.nb_deviations,
        nb_jit=result.nb_jit,
        nb_changements_serie=result.nb_changements_serie,
        lignes=lignes,
        ofs_non_planifies=ofs_non_planifies,
        nb_ofs_non_planifies=len(result.unscheduled_rows),
        alertes_scheduler=result.alerts,
        messages_reordonnancement=messages,
        receptions_en_retard=receptions_retard,
        alertes_goulots=goulots,
        kpis_service=kpis,
        alertes=alertes,
        stock_bdh_projete=result.stock_projection,
        order_rows=result.order_rows,
    )


def _analyze_lines(result: SchedulerResult) -> list[LineAnalysis]:
    """Analyse détaillée par ligne de production."""
    analyses = []
    for line, planning in result.plannings.items():
        charge_by_day = defaultdict(float)
        changements = 0
        last_article = None

        for item in planning:
            if item.scheduled_day:
                day_key = item.scheduled_day.isoformat()
                charge_by_day[day_key] += item.charge_hours
            if last_article and item.article != last_article:
                changements += 1
            last_article = item.article

        # OFs non planifiés pour cette ligne
        ofs_np = [r for r in result.unscheduled_rows if r.get("ligne") == line]

        analyses.append(LineAnalysis(
            line=line,
            total_ofs=len(planning),
            total_hours=round(sum(item.charge_hours for item in planning), 1),
            charge_by_day=dict(charge_by_day),
            ofs_non_planifies=ofs_np,
            changements_serie=changements,
        ))

    return analyses


def _consolidate_alertes(
    result: SchedulerResult,
    lignes: list[LineAnalysis],
    messages: list[ReschedulingMessage],
    receptions_retard: list[LateReceptionImpact],
    goulots: list[BottleneckAlert],
    kpis: ServiceRateKPIs,
    config: AnalysisConfig,
) -> list[AlerteOrdonnanceur]:
    """Consolide toutes les sources d'alerte en une liste triée par sévérité."""
    alertes: list[AlerteOrdonnanceur] = []

    # --- Taux de service ---
    if result.taux_service < config.seuil_taux_service_alerte:
        alertes.append(AlerteOrdonnanceur(
            niveau="CRITIQUE",
            categorie="SERVICE",
            message=f"Taux de service scheduler: {result.taux_service:.1%} (seuil: {config.seuil_taux_service_alerte:.0%})",
            action="Vérifier les OFs non planifiés et les commandes sans OF matché",
        ))

    # --- Taux d'ouverture ---
    if result.taux_ouverture < config.seuil_taux_ouverture_min:
        alertes.append(AlerteOrdonnanceur(
            niveau="ATTENTION",
            categorie="CAPACITE",
            message=f"Sous-charge atelier: taux d'ouverture {result.taux_ouverture:.1%}",
            action="Opportunité d'avancer des OFs S+2/S+3",
        ))
    elif result.taux_ouverture > config.seuil_taux_ouverture_max:
        alertes.append(AlerteOrdonnanceur(
            niveau="ATTENTION",
            categorie="CAPACITE",
            message=f"Saturation atelier: taux d'ouverture {result.taux_ouverture:.1%}",
            action="Revoir les priorités ou envisager des heures sup",
        ))

    # --- Déviations ---
    if result.nb_deviations > config.seuil_deviations_alerte:
        alertes.append(AlerteOrdonnanceur(
            niveau="ATTENTION",
            categorie="CAPACITE",
            message=f"{result.nb_deviations} déviations de planning détectées",
            action="Vérifier les OFs qui ont sauté devant d'autres",
        ))

    # --- Messages de réordonnancement critiques ---
    msgs_critiques = [m for m in messages if m.priorite == 1]
    if msgs_critiques:
        alertes.append(AlerteOrdonnanceur(
            niveau="CRITIQUE",
            categorie="MATERIEL",
            message=f"{len(msgs_critiques)} OF(s) en retard ou retard imminent",
            action="Consulter les messages de réordonnancement",
            details={"messages": [
                {"of": m.num_of, "type": m.type, "msg": m.message}
                for m in msgs_critiques[:5]
            ]},
        ))

    # --- Réceptions en retard ---
    recep_critiques = [r for r in receptions_retard if r.niveau_risque == "CRITIQUE"]
    if recep_critiques:
        alertes.append(AlerteOrdonnanceur(
            niveau="CRITIQUE",
            categorie="MATERIEL",
            message=f"{len(recep_critiques)} réception(s) fournisseur en retard critique",
            action="Relancer les fournisseurs ou revoir le planning",
            details={"receptions": [
                {"article": r.article, "fournisseur": r.fournisseur, "retard_j": r.jours_retard}
                for r in recep_critiques[:5]
            ]},
        ))

    # --- Goulots saturés ---
    goulots_satures = [g for g in goulots if g.statut == "SATURE"]
    if goulots_satures:
        alertes.append(AlerteOrdonnanceur(
            niveau="ATTENTION",
            categorie="GOULOT",
            message=f"{len(goulots_satures)} poste(s) en saturation",
            action="Revoir la répartition de charge ou ajouter des ressources",
            details={"goulots": [
                {"poste": g.poste, "semaine": g.semaine, "taux": g.taux_charge}
                for g in goulots_satures[:5]
            ]},
        ))

    # --- Commandes en retard (KPIs service) ---
    if kpis.nb_commandes_en_retard > 0:
        alertes.append(AlerteOrdonnanceur(
            niveau="CRITIQUE" if kpis.nb_commandes_en_retard > 10 else "ATTENTION",
            categorie="SERVICE",
            message=f"{kpis.nb_commandes_en_retard} commande(s) en retard (KPIs service)",
            action="Prioriser les commandes dépassées",
        ))

    # --- Trier par sévérité ---
    niveau_order = {"CRITIQUE": 0, "ATTENTION": 1, "INFO": 2}
    alertes.sort(key=lambda a: niveau_order.get(a.niveau, 9))

    return alertes
