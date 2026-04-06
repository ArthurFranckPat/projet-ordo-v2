"""AUTORESEARCH bootstrap scheduler.

This module intentionally implements a pragmatic V1:
- it reuses existing loaders/models/checkers
- it specializes only PP_830 and PP_153
- it schedules existing OFs on a 15-workday horizon
- it writes the outputs expected by AUTORESEARCH_SPEC.md
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from ..algorithms.charge_calculator import calculate_article_charge
from ..algorithms.allocation import StockState
from ..algorithms.matching import CommandeOFMatcher
from ..checkers.recursive import RecursiveChecker
from .calendar import build_workdays, next_workday, previous_workday
from .weights import load_weights

PP_830 = "PP_830"
PP_153 = "PP_153"
PLANNING_WORKDAYS = 5
DEMAND_CALENDAR_DAYS = 15
LINE_CAPACITY_HOURS = 14.0
LINE_MIN_OPEN_HOURS = 7.0
BUFFER_THRESHOLDS = {
    "BDH2216AL": 673,
    "BDH2231AL": 598,
    "BDH2251AL": 598,
}


@dataclass
class CandidateOF:
    """Scheduling candidate on one target line."""

    num_of: str
    article: str
    description: str
    line: str
    due_date: date
    quantity: int
    charge_hours: float
    is_buffer_bdh: bool = False
    scheduled_day: Optional[date] = None
    start_hour: Optional[float] = None
    end_hour: Optional[float] = None
    reason: str = ""
    deviations: int = 0


@dataclass
class DaySchedule:
    """Daily schedule for one line."""

    line: str
    day: date
    assignments: list[CandidateOF] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return round(sum(item.charge_hours for item in self.assignments), 3)


@dataclass
class SchedulerResult:
    """Final scheduling outputs."""

    score: float
    taux_service: float
    taux_ouverture: float
    nb_deviations: int
    planning_pp830: list[CandidateOF]
    planning_pp153: list[CandidateOF]
    stock_projection: list[dict[str, object]]
    alerts: list[str]
    weights: dict[str, float]
    unscheduled_rows: list[dict[str, object]]
    order_rows: list[dict[str, object]]


def run_schedule(
    loader,
    *,
    reference_date: Optional[date] = None,
    planning_workdays: int = PLANNING_WORKDAYS,
    demand_calendar_days: int = DEMAND_CALENDAR_DAYS,
    output_dir: str = "outputs",
    weights_path: str = "config/weights.json",
) -> SchedulerResult:
    """Run the AUTORESEARCH bootstrap scheduler."""
    reference_date = reference_date or date.today()
    weights = load_weights(weights_path)
    workdays = build_workdays(reference_date, planning_workdays)
    demand_horizon_end = reference_date + timedelta(days=demand_calendar_days)
    target_lines = _build_target_line_articles(loader)
    checker = RecursiveChecker(loader, use_receptions=True)
    material_state = _build_material_stock_state(loader)
    receptions_by_day = _build_receptions_by_day(loader)

    candidates, matching_alerts, matching_results = _select_candidates_from_matching(
        loader=loader,
        planning_workdays=workdays,
        demand_horizon_end=demand_horizon_end,
        target_lines=target_lines,
    )

    day_plans = {
        PP_830: [DaySchedule(line=PP_830, day=day) for day in workdays],
        PP_153: [DaySchedule(line=PP_153, day=day) for day in workdays],
    }
    alerts: list[str] = list(matching_alerts)

    projected_buffer = {
        article: float(loader.get_stock(article).disponible() if loader.get_stock(article) else 0)
        for article in BUFFER_THRESHOLDS
    }
    incoming_buffer: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    stock_projection: list[dict[str, object]] = []

    by_line = {
        PP_830: [candidate for candidate in candidates if candidate.line == PP_830],
        PP_153: [candidate for candidate in candidates if candidate.line == PP_153],
    }

    for day in workdays:
        _apply_receptions_for_day(material_state, receptions_by_day, day)
        for article, qty in incoming_buffer[day].items():
            projected_buffer[article] += qty

        pp830_day = _schedule_line(
            line=PP_830,
            day=day,
            candidates=by_line[PP_830],
            loader=loader,
            checker=checker,
            projected_buffer=projected_buffer,
            material_state=material_state,
            alerts=alerts,
        )
        day_plans[PP_830][workdays.index(day)] = pp830_day

        for assignment in pp830_day.assignments:
            for article, qty in _tracked_bdh_requirements(loader, assignment.article, assignment.quantity).items():
                projected_buffer[article] -= qty

        pp153_day = _schedule_pp153(
            day=day,
            candidates=by_line[PP_153],
            loader=loader,
            checker=checker,
            projected_buffer=projected_buffer,
            incoming_buffer=incoming_buffer,
            material_state=material_state,
            alerts=alerts,
        )
        day_plans[PP_153][workdays.index(day)] = pp153_day

        for article in BUFFER_THRESHOLDS:
            stock_projection.append(
                {
                    "jour": day.isoformat(),
                    "article": article,
                    "stock_projete": round(projected_buffer[article], 3),
                }
            )

    planning_pp830 = [assignment for plan in day_plans[PP_830] for assignment in plan.assignments]
    planning_pp153 = [assignment for plan in day_plans[PP_153] for assignment in plan.assignments]
    _mark_unscheduled_candidates(by_line, alerts)
    unscheduled_rows = _build_unscheduled_rows(by_line)

    planned_by_of = {assignment.num_of: assignment.scheduled_day for assignment in planning_pp830 + planning_pp153}
    candidate_by_of = {candidate.num_of: candidate for candidate in candidates}
    planning_horizon_end = next_workday(workdays[-1])
    order_rows = _build_order_rows(matching_results, planned_by_of, candidate_by_of, loader, checker)
    taux_service, on_time, total_candidates = _compute_service_rate_from_matching(
        matching_results,
        planned_by_of,
        evaluation_horizon_end=planning_horizon_end,
    )
    taux_ouverture = _compute_open_rate(day_plans)
    nb_deviations = sum(candidate.deviations for candidate in candidates)
    deviation_penalty = min(
        1.0,
        nb_deviations / max(1, len(planning_pp830) + len(planning_pp153)),
    )
    score = (
        taux_service * weights["w1"]
        + taux_ouverture * weights["w2"]
        - deviation_penalty * weights["w3"]
    )

    result = SchedulerResult(
        score=round(score, 3),
        taux_service=round(taux_service, 3),
        taux_ouverture=round(taux_ouverture, 3),
        nb_deviations=nb_deviations,
        planning_pp830=planning_pp830,
        planning_pp153=planning_pp153,
        stock_projection=stock_projection,
        alerts=alerts,
        weights=weights,
        unscheduled_rows=unscheduled_rows,
        order_rows=order_rows,
    )
    _write_outputs(output_dir, result)
    return result


def _build_target_line_articles(loader) -> dict[str, set[str]]:
    target_lines = {PP_830: set(), PP_153: set()}
    for article, gamme in loader.gammes.items():
        for op in gamme.operations:
            if op.poste_charge in target_lines:
                target_lines[op.poste_charge].add(article)
    return target_lines


def _is_target_scope_order(besoin, loader, target_lines) -> bool:
    """Retourne True si le besoin appartient reellement au scope 830/153."""
    if besoin.article in target_lines[PP_830] or besoin.article in target_lines[PP_153]:
        return True
    if besoin.of_contremarque:
        linked_of = loader.get_of_by_num(besoin.of_contremarque)
        if linked_of is not None:
            if linked_of.article in target_lines[PP_830] or linked_of.article in target_lines[PP_153]:
                return True
    return False


def _select_candidates_from_matching(loader, planning_workdays, demand_horizon_end, target_lines) -> tuple[list[CandidateOF], list[str], list]:
    """Construit les candidats à partir du matching existant commande->OF.

    On réutilise le matcher du repo pour éviter de reconstruire la logique
    métier MTS/NOR/MTO. Le scheduler ne décide ensuite que du placement
    journalier et de la stratégie buffer BDH.
    """
    reference_date = planning_workdays[0]
    planning_horizon_end = next_workday(planning_workdays[-1])
    commandes = [
        besoin
        for besoin in loader.commandes_clients
        if besoin.est_commande()
        and besoin.qte_restante > 0
        and reference_date <= besoin.date_expedition_demandee <= demand_horizon_end
        and _is_target_scope_order(besoin, loader, target_lines)
    ]
    commandes.sort(key=lambda b: (b.date_expedition_demandee, b.date_commande or date.max, b.num_commande))

    matcher = CommandeOFMatcher(loader, date_tolerance_days=30)
    matching_results = matcher.match_commandes(commandes)

    candidate_specs: dict[str, dict[str, object]] = {}
    alerts: list[str] = []
    for result in matching_results:
        if result.of is None:
            alerts.append(
                f"COMMANDE {result.commande.num_commande} ({result.commande.article}) sans OF matché : {result.matching_method}"
            )
            continue

        of = result.of
        line = None
        if of.article in target_lines[PP_830]:
            line = PP_830
        elif of.article in target_lines[PP_153]:
            line = PP_153
        if line is None:
            continue

        spec = candidate_specs.setdefault(
            of.num_of,
            {
                'of': of,
                'line': line,
                'due_date': result.commande.date_expedition_demandee,
                'orders': set(),
            },
        )
        if result.commande.date_expedition_demandee < spec['due_date']:
            spec['due_date'] = result.commande.date_expedition_demandee
        spec['orders'].add(result.commande.num_commande)

    # Ajouter les OF BDH comme levier de reconstitution tampon sur PP_153.
    for tracked_article in BUFFER_THRESHOLDS:
        buffer_ofs = [
            of for of in loader.ofs
            if of.article == tracked_article and of.qte_restante > 0 and of.statut_num in (1, 2, 3)
        ]
        buffer_ofs.sort(key=lambda item: (item.date_fin, 0 if item.is_ferme() else 1, item.num_of))
        for of in buffer_ofs[:8]:
            candidate_specs.setdefault(
                of.num_of,
                {
                    'of': of,
                    'line': PP_153,
                    'due_date': of.date_fin,
                    'orders': set(),
                },
            )

    candidates: list[CandidateOF] = []
    for spec in candidate_specs.values():
        of = spec['of']
        line = spec['line']
        due_date = spec['due_date']
        charge_map = calculate_article_charge(of.article, of.qte_restante, loader)
        charge_hours = round(charge_map.get(line, 0.0), 3)
        if charge_hours <= 0:
            continue
        candidates.append(
            CandidateOF(
                num_of=of.num_of,
                article=of.article,
                description=of.description,
                line=line,
                due_date=due_date,
                quantity=of.qte_restante,
                charge_hours=charge_hours,
                is_buffer_bdh=of.article in BUFFER_THRESHOLDS and line == PP_153,
            )
        )

    candidates.sort(key=lambda item: (item.due_date > planning_horizon_end, item.due_date, 0 if item.is_buffer_bdh else 1, item.charge_hours, item.num_of))
    return candidates, alerts, matching_results


def _schedule_line(line, day, candidates, loader, checker, projected_buffer, material_state, alerts) -> DaySchedule:
    plan = DaySchedule(line=line, day=day)
    used_hours = 0.0
    earliest_blocked_due: Optional[date] = None

    for candidate in candidates:
        if candidate.scheduled_day is not None:
            continue
        if candidate.charge_hours <= 0:
            continue
        if used_hours + candidate.charge_hours > LINE_CAPACITY_HOURS:
            continue

        status, reason = _availability_status(checker, loader, candidate, day, material_state)
        if status == "blocked":
            candidate.reason = reason
            if earliest_blocked_due is None or candidate.due_date < earliest_blocked_due:
                earliest_blocked_due = candidate.due_date
            continue

        requirements = _tracked_bdh_requirements(loader, candidate.article, candidate.quantity)
        if any(projected_buffer[article] < qty for article, qty in requirements.items()):
            candidate.reason = _format_buffer_shortage_reason(requirements, projected_buffer)
            continue

        candidate.reason = ""
        candidate.deviations = 1 if earliest_blocked_due and candidate.due_date > earliest_blocked_due else 0
        candidate.scheduled_day = day
        candidate.start_hour = round(used_hours, 3)
        used_hours += candidate.charge_hours
        candidate.end_hour = round(used_hours, 3)
        plan.assignments.append(candidate)
        _reserve_candidate_components(loader, checker, candidate, day, material_state)

        if used_hours >= LINE_CAPACITY_HOURS:
            break

    if plan.total_hours < LINE_MIN_OPEN_HOURS:
        for assignment in plan.assignments:
            assignment.scheduled_day = None
            assignment.start_hour = None
            assignment.end_hour = None
            assignment.reason = "ligne non ouverte (<7h)"
        if plan.assignments:
            alerts.append(f"{line} {day.isoformat()} : ligne fermée car charge < 7h")
        plan.assignments = []

    return plan


def _schedule_pp153(day, candidates, loader, checker, projected_buffer, incoming_buffer, material_state, alerts) -> DaySchedule:
    plan = DaySchedule(line=PP_153, day=day)
    used_hours = 0.0

    shortage_articles = {
        article
        for article, threshold in BUFFER_THRESHOLDS.items()
        if projected_buffer.get(article, 0.0) < threshold
    }
    buffer_first = bool(shortage_articles)

    def sort_key(candidate: CandidateOF) -> tuple:
        if buffer_first:
            if candidate.is_buffer_bdh and candidate.article in shortage_articles:
                priority = 0
            elif not candidate.is_buffer_bdh:
                priority = 1
            else:
                priority = 2
            return (priority, candidate.due_date, candidate.charge_hours, candidate.article)

        # Hors tension buffer, les commandes directes PP_153 passent avant la reconstitution.
        return (0 if not candidate.is_buffer_bdh else 1, candidate.due_date, candidate.charge_hours, candidate.article)

    for candidate in sorted(candidates, key=sort_key):
        if candidate.scheduled_day is not None:
            continue
        if used_hours + candidate.charge_hours > LINE_CAPACITY_HOURS:
            continue

        status, reason = _availability_status(checker, loader, candidate, day, material_state)
        if status == "blocked":
            candidate.reason = reason
            continue

        candidate.reason = ""
        candidate.scheduled_day = day
        candidate.start_hour = round(used_hours, 3)
        used_hours += candidate.charge_hours
        candidate.end_hour = round(used_hours, 3)
        plan.assignments.append(candidate)
        _reserve_candidate_components(loader, checker, candidate, day, material_state)

        if candidate.is_buffer_bdh:
            availability_day = next_workday(day)
            incoming_buffer[availability_day][candidate.article] += candidate.quantity

        if used_hours >= LINE_CAPACITY_HOURS:
            break

    if plan.total_hours < LINE_MIN_OPEN_HOURS:
        for assignment in plan.assignments:
            if assignment.is_buffer_bdh:
                availability_day = next_workday(day)
                incoming_buffer[availability_day][assignment.article] -= assignment.quantity
            assignment.scheduled_day = None
            assignment.start_hour = None
            assignment.end_hour = None
            assignment.reason = "ligne non ouverte (<7h)"
        if plan.assignments:
            alerts.append(f"{PP_153} {day.isoformat()} : ligne fermée car charge < 7h")
        plan.assignments = []

    return plan




def _format_feasibility_cause(result) -> str:
    """Rend une cause métier lisible à partir du résultat du checker."""
    details: list[str] = []
    if getattr(result, 'missing_components', None):
        missing = ', '.join(
            f"{article} x{quantity}"
            for article, quantity in sorted(result.missing_components.items())
        )
        details.append(f"composants indisponibles: {missing}")
    if getattr(result, 'alerts', None):
        details.extend(result.alerts[:3])
    if not details:
        return "composants indisponibles"
    return ' | '.join(details)


def _format_buffer_shortage_reason(requirements: dict[str, float], projected_buffer: dict[str, float]) -> str:
    """Explique quel stock tampon BDH manque réellement."""
    shortages = []
    for article, required_qty in sorted(requirements.items()):
        available_qty = projected_buffer.get(article, 0.0)
        if available_qty < required_qty:
            shortages.append(
                f"{article} besoin={round(required_qty, 3)} dispo={round(available_qty, 3)}"
            )
    if not shortages:
        return "stock tampon BDH insuffisant"
    return "stock tampon BDH insuffisant: " + ', '.join(shortages)


def _build_unscheduled_rows(by_line: dict[str, list[CandidateOF]]) -> list[dict[str, object]]:
    """Construit un export structuré des OF non planifiés avec leur cause."""
    rows: list[dict[str, object]] = []
    for line, candidates in by_line.items():
        for candidate in candidates:
            if candidate.scheduled_day is not None:
                continue
            rows.append(
                {
                    'ligne': line,
                    'of': candidate.num_of,
                    'article': candidate.article,
                    'date_echeance': candidate.due_date.isoformat(),
                    'charge_h': round(candidate.charge_hours, 3),
                    'cause': candidate.reason or 'capacité insuffisante ou hors horizon',
                }
            )
    rows.sort(key=lambda row: (row['ligne'], row['date_echeance'], row['of']))
    return rows


def _build_material_stock_state(loader) -> StockState:
    """Initialise l'état de stock virtuel pour les composants."""
    initial_stock = {}
    for article, stock in loader.stocks.items():
        initial_stock[article] = stock.disponible()
    return StockState(initial_stock)


def _build_receptions_by_day(loader) -> dict[date, list[tuple[str, int]]]:
    """Indexe les réceptions fournisseurs par jour."""
    receptions_by_day: dict[date, list[tuple[str, int]]] = defaultdict(list)
    for reception in loader.receptions:
        receptions_by_day[reception.date_reception_prevue].append(
            (reception.article, reception.quantite_restante)
        )
    return receptions_by_day


def _apply_receptions_for_day(material_state: StockState, receptions_by_day, day: date) -> None:
    """Ajoute au stock virtuel les réceptions disponibles ce jour."""
    for article, quantity in receptions_by_day.get(day, []):
        material_state.add_supply(article, quantity)


def _reserve_candidate_components(loader, checker, candidate, day: date, material_state: StockState) -> None:
    """Réserve virtuellement les composants consommés par un OF planifié."""
    allocations = _collect_component_reservations(
        loader,
        checker,
        candidate.article,
        candidate.quantity,
        day,
        material_state,
    )
    if allocations:
        material_state.allocate(candidate.num_of, allocations)


def _collect_component_reservations(
    loader,
    checker,
    article: str,
    quantity: int,
    day: date,
    material_state: StockState,
    seen: Optional[set[str]] = None,
) -> dict[str, int]:
    """Collecte les réservations matière induites par un OF.

    Réserve les achats directs, les AFANT résolus sur une seule variante,
    et les sous-ensembles fabriqués effectivement consommés depuis le stock.
    """
    seen = seen or set()
    if article in seen:
        return {}
    seen.add(article)

    nomenclature = loader.get_nomenclature(article)
    if nomenclature is None:
        return {}

    allocations: dict[str, int] = defaultdict(int)
    for composant in nomenclature.composants:
        qte_composant = int(composant.qte_lien * quantity)
        article_code = composant.article_composant

        if checker._is_component_treated_as_purchase(article_code, composant.is_achete(), composant.is_fabrique()):
            if checker._is_phantom_article(article_code):
                options = [(article_code, 1.0)] + [
                    option for option in checker._get_phantom_variants(article_code)
                    if option[0] != article_code
                ]
                for variant_article, qte_lien in options:
                    variant_qty = int(qte_lien * qte_composant)
                    if material_state.get_available(variant_article) >= variant_qty:
                        allocations[variant_article] += variant_qty
                        break
            else:
                allocations[article_code] += qte_composant
            continue

        if composant.is_fabrique():
            if material_state.get_available(article_code) >= qte_composant:
                allocations[article_code] += qte_composant
            else:
                nested = _collect_component_reservations(
                    loader,
                    checker,
                    article_code,
                    qte_composant,
                    day,
                    material_state,
                    seen.copy(),
                )
                for nested_article, nested_qty in nested.items():
                    allocations[nested_article] += nested_qty

    return dict(allocations)


def _availability_status(checker, loader, candidate, day: date, material_state: Optional[StockState] = None) -> tuple[str, str]:
    date_j2 = previous_workday(day, 2)
    date_j1 = previous_workday(day, 1)
    date_j0 = day
    runtime_checker = (
        RecursiveChecker(
            loader,
            use_receptions=False,
            check_date=day,
            stock_state=material_state,
        )
        if material_state is not None
        else checker
    )

    for status, need_date in (
        ("comfortable", date_j2),
        ("comfortable", date_j1),
        ("tight", date_j0),
    ):
        result = runtime_checker._check_article_recursive(
            article=candidate.article,
            qte_besoin=candidate.quantity,
            date_besoin=need_date,
            depth=0,
            of_parent_est_ferme=False,
            num_of_parent=candidate.num_of,
        )
        if result.feasible:
            return status, ""

    stock = loader.get_stock(candidate.article)
    if stock and stock.disponible() >= candidate.quantity:
        return "tight", ""
    return "blocked", _format_feasibility_cause(result)


def _tracked_bdh_requirements(loader, article: str, quantity: int, seen: Optional[set[str]] = None) -> dict[str, float]:
    seen = seen or set()
    if article in seen:
        return {}
    seen.add(article)

    requirements: dict[str, float] = defaultdict(float)
    nomenclature = loader.get_nomenclature(article)
    if nomenclature is None:
        return {}

    for composant in nomenclature.composants:
        comp_qty = composant.qte_lien * quantity
        if composant.article_composant in BUFFER_THRESHOLDS:
            requirements[composant.article_composant] += comp_qty
        elif composant.is_fabrique():
            nested = _tracked_bdh_requirements(
                loader,
                composant.article_composant,
                int(comp_qty),
                seen.copy(),
            )
            for nested_article, nested_qty in nested.items():
                requirements[nested_article] += nested_qty

    return dict(requirements)


def _mark_unscheduled_candidates(by_line, alerts) -> None:
    for line, candidates in by_line.items():
        for candidate in candidates:
            if candidate.scheduled_day is None:
                reason = candidate.reason or "capacité insuffisante ou hors horizon"
                alerts.append(f"{line} {candidate.num_of} ({candidate.article}) non planifiable : {reason}")






def _build_order_rows(matching_results, planned_by_of: dict[str, date], candidate_by_of: dict[str, CandidateOF], loader, checker) -> list[dict[str, object]]:
    """Construit un rapport métier des lignes de besoin avec cause."""
    rows: list[dict[str, object]] = []
    for result in matching_results:
        commande = result.commande
        of = result.of
        planned_day = planned_by_of.get(of.num_of) if of else None
        candidate = candidate_by_of.get(of.num_of) if of else None

        if of is None:
            if 'stock complet' in result.matching_method.lower():
                statut = 'Servie sur stock'
                cause = 'stock complet'
            else:
                statut = 'Non couverte'
                cause = ' | '.join(result.alertes) if result.alertes else result.matching_method
        elif planned_day is None:
            statut = 'Non planifiée'
            cause = candidate.reason if candidate and candidate.reason else 'OF matché mais non injecté au planning'
        elif planned_day <= commande.date_expedition_demandee:
            statut = 'Servie par OF planifié à temps'
            cause = 'OF planifié à temps'
        else:
            statut = 'Servie en retard'
            if candidate is not None:
                status_at_due, reason_at_due = _availability_status(checker, loader, candidate, commande.date_expedition_demandee)
                if status_at_due == 'blocked':
                    cause = reason_at_due
                else:
                    cause = (
                        f"planifié le {planned_day.isoformat()} après l'échéance du {commande.date_expedition_demandee.isoformat()} | "
                        "capacité ligne saturée avant son tour"
                    )
            else:
                cause = f"planifié le {planned_day.isoformat()} après l'échéance du {commande.date_expedition_demandee.isoformat()}"

        rows.append({
            'commande': commande.num_commande,
            'article_commande': commande.article,
            'date_demande': commande.date_expedition_demandee.isoformat(),
            'qte': commande.qte_restante,
            'of': of.num_of if of else '',
            'article_of': of.article if of else '',
            'jour_planifie': planned_day.isoformat() if planned_day else '',
            'statut': statut,
            'cause': cause,
            'matching': result.matching_method,
        })

    rows.sort(key=lambda row: (row['date_demande'], row['commande'], row['article_commande']))
    return rows


def _write_order_rows_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "commande", "article_commande", "date_demande", "qte", "of", "article_of", "jour_planifie", "statut", "cause", "matching"
        ])
        for row in rows:
            writer.writerow([
                row['commande'], row['article_commande'], row['date_demande'], row['qte'], row['of'], row['article_of'], row['jour_planifie'], row['statut'], row['cause'], row['matching']
            ])


def _compute_service_rate_from_matching(
    matching_results,
    planned_by_of: dict[str, date],
    *,
    evaluation_horizon_end: date | None = None,
) -> tuple[float, int, int]:
    """Calcule le service au niveau commande a partir du matching existant.

    Si `evaluation_horizon_end` est fourni, seules les lignes de besoin dont
    l'échéance tombe dans la fenêtre de pilotage sont prises dans le KPI.
    """
    relevant_results = [
        result for result in matching_results
        if evaluation_horizon_end is None or result.commande.date_expedition_demandee <= evaluation_horizon_end
    ]
    total = len(relevant_results)
    served = 0
    for result in relevant_results:
        if result.of is None:
            if "stock complet" in result.matching_method.lower():
                served += 1
            continue

        scheduled_day = planned_by_of.get(result.of.num_of)
        if scheduled_day and scheduled_day <= result.commande.date_expedition_demandee:
            served += 1

    return ((served / total) if total else 0.0), served, total

def _compute_service_rate(candidates: list[CandidateOF]) -> tuple[float, int, int]:
    total = len(candidates)
    on_time = 0
    for candidate in candidates:
        if candidate.scheduled_day is not None and candidate.scheduled_day <= candidate.due_date:
            on_time += 1
    return ((on_time / total) if total else 0.0), on_time, total


def _compute_open_rate(day_plans: dict[str, list[DaySchedule]]) -> float:
    available_hours = len(day_plans) * len(next(iter(day_plans.values()))) * LINE_CAPACITY_HOURS
    planned_hours = sum(plan.total_hours for plans in day_plans.values() for plan in plans)
    return (planned_hours / available_hours) if available_hours else 0.0


def _write_outputs(output_dir: str, result: SchedulerResult) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _write_planning_csv(output_path / "planning_PP830.csv", result.planning_pp830)
    _write_planning_csv(output_path / "planning_PP153.csv", result.planning_pp153)
    _write_stock_projection_csv(output_path / "stock_BDH_projete.csv", result.stock_projection)

    _write_unscheduled_csv(output_path / "ofs_non_faisables.csv", result.unscheduled_rows)
    _write_order_rows_csv(output_path / "lignes_commande_statut.csv", result.order_rows)

    with (output_path / "kpis.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "taux_service": result.taux_service,
                "taux_ouverture": result.taux_ouverture,
                "nb_deviations": result.nb_deviations,
                "weights": result.weights,
                "score": result.score,
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    with (output_path / "alertes.txt").open("w", encoding="utf-8") as handle:
        for alert in result.alerts:
            handle.write(alert + "\n")




def _write_unscheduled_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ligne", "of", "article", "date_echeance", "charge_h", "cause"])
        for row in rows:
            writer.writerow([
                row['ligne'],
                row['of'],
                row['article'],
                row['date_echeance'],
                row['charge_h'],
                row['cause'],
            ])


def _write_planning_csv(path: Path, planning: list[CandidateOF]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["num_of", "article", "jour", "heure_debut", "heure_fin", "charge_h", "date_echeance"])
        for item in planning:
            writer.writerow(
                [
                    item.num_of,
                    item.article,
                    item.scheduled_day.isoformat() if item.scheduled_day else "",
                    _format_hour(item.start_hour),
                    _format_hour(item.end_hour),
                    round(item.charge_hours, 3),
                    item.due_date.isoformat(),
                ]
            )


def _write_stock_projection_csv(path: Path, projection: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["jour", "article", "stock_projete"])
        for row in projection:
            writer.writerow([row["jour"], row["article"], row["stock_projete"]])


def _format_hour(value: Optional[float]) -> str:
    if value is None:
        return ""
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    current = datetime(2000, 1, 1, 0, 0).replace(hour=0, minute=0)
    current = current.replace(hour=0, minute=0)
    current = current.replace(hour=(hours % 24), minute=(minutes % 60))
    return current.strftime("%H:%M")
