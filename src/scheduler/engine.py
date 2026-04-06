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
from .models import CandidateOF, DaySchedule, SchedulerResult
from .reporting import build_unscheduled_rows, build_order_rows, write_outputs
from .lines import PP830Scheduler, PP153Scheduler

from .material import (
    BUFFER_THRESHOLDS,
    build_material_stock_state,
    build_receptions_by_day,
    apply_receptions_for_day,
    reserve_candidate_components,
    availability_status,
    tracked_bdh_requirements,
    tracked_kanban_requirements,
    format_buffer_shortage_reason
)

PP_830 = "PP_830"
PP_153 = "PP_153"
PLANNING_WORKDAYS = 5
DEMAND_CALENDAR_DAYS = 15
LINE_CAPACITY_HOURS = 14.0
LINE_MIN_OPEN_HOURS = 7.0
SETUP_TIME_HOURS = 0.25  # 15 minutes de changement de série par défaut


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
    material_state = build_material_stock_state(loader)
    receptions_by_day = build_receptions_by_day(loader)

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

    pp830_scheduler = PP830Scheduler()
    pp153_scheduler = PP153Scheduler()

    for day in workdays:
        apply_receptions_for_day(material_state, receptions_by_day, day)
        for article, qty in incoming_buffer[day].items():
            projected_buffer[article] += qty

        pp830_day = pp830_scheduler.schedule_day(
            day=day,
            candidates=by_line[PP_830],
            loader=loader,
            checker=checker,
            projected_buffer=projected_buffer,
            incoming_buffer=incoming_buffer,
            material_state=material_state,
            alerts=alerts,
        )
        day_plans[PP_830][workdays.index(day)] = pp830_day

        for assignment in pp830_day.assignments:
            for article, qty in tracked_bdh_requirements(loader, assignment.article, assignment.quantity).items():
                projected_buffer[article] -= qty

        pp153_day = pp153_scheduler.schedule_day(
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
    unscheduled_rows = build_unscheduled_rows(by_line)

    planned_by_of = {assignment.num_of: assignment.scheduled_day for assignment in (planning_pp830 + planning_pp153)}
    candidate_by_of = {candidate.num_of: candidate for candidate in candidates}
    planning_horizon_end = next_workday(workdays[-1])
    order_rows = build_order_rows(matching_results, planned_by_of, candidate_by_of, loader, checker, availability_status)
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

    nb_jit = sum(1 for c in planning_pp830 + planning_pp153 if c.scheduled_day == c.due_date)
    jit_penalty = min(
        1.0,
        nb_jit / max(1, len(planning_pp830) + len(planning_pp153)),
    )

    score = (
        taux_service * weights["w1"]
        + taux_ouverture * weights["w2"]
        - deviation_penalty * weights["w3"]
        - jit_penalty * weights.get("w4", 0.1)
    )

    nb_changements_serie = sum(
        1 for plan in day_plans[PP_830] + day_plans[PP_153]
        for i in range(1, len(plan.assignments))
        if plan.assignments[i].article != plan.assignments[i-1].article
    )

    result = SchedulerResult(
        score=round(score, 3),
        taux_service=round(taux_service, 3),
        taux_ouverture=round(taux_ouverture, 3),
        nb_deviations=nb_deviations,
        nb_jit=nb_jit,
        nb_changements_serie=nb_changements_serie,
        planning_pp830=planning_pp830,
        planning_pp153=planning_pp153,
        stock_projection=stock_projection,
        alerts=alerts,
        weights=weights,
        unscheduled_rows=unscheduled_rows,
        order_rows=order_rows,
    )
    write_outputs(output_dir, result)
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
        for of in buffer_ofs[:25]:
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


def _mark_unscheduled_candidates(by_line, alerts) -> None:
    for line, candidates in by_line.items():
        for candidate in candidates:
            if candidate.scheduled_day is None:
                reason = candidate.reason or "capacité insuffisante ou hors horizon"
                alerts.append(f"{line} {candidate.num_of} ({candidate.article}) non planifiable : {reason}")

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
