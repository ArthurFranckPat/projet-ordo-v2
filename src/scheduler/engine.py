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
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..algorithms.charge_calculator import calculate_article_charge
from ..checkers.recursive import RecursiveChecker
from .calendar import build_workdays, next_workday, previous_workday
from .weights import load_weights

PP_830 = "PP_830"
PP_153 = "PP_153"
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


def run_schedule(
    loader,
    *,
    reference_date: Optional[date] = None,
    horizon_workdays: int = 15,
    output_dir: str = "outputs",
    weights_path: str = "config/weights.json",
) -> SchedulerResult:
    """Run the AUTORESEARCH bootstrap scheduler."""
    reference_date = reference_date or date.today()
    weights = load_weights(weights_path)
    workdays = build_workdays(reference_date, horizon_workdays)
    target_lines = _build_target_line_articles(loader)
    due_dates_by_of, article_demand_buckets = _build_due_date_indexes(
        loader,
        reference_date=reference_date,
        horizon_end=next_workday(workdays[-1]),
    )
    checker = RecursiveChecker(loader, use_receptions=True)

    candidates = _select_candidates(
        loader=loader,
        workdays=workdays,
        target_lines=target_lines,
        due_dates_by_of=due_dates_by_of,
        article_demand_buckets=article_demand_buckets,
    )

    day_plans = {
        PP_830: [DaySchedule(line=PP_830, day=day) for day in workdays],
        PP_153: [DaySchedule(line=PP_153, day=day) for day in workdays],
    }
    alerts: list[str] = []

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
        for article, qty in incoming_buffer[day].items():
            projected_buffer[article] += qty

        pp830_day = _schedule_line(
            line=PP_830,
            day=day,
            candidates=by_line[PP_830],
            loader=loader,
            checker=checker,
            projected_buffer=projected_buffer,
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

    taux_service, on_time, total_candidates = _compute_service_rate(candidates)
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


def _build_due_date_indexes(
    loader,
    *,
    reference_date: date,
    horizon_end: date,
) -> tuple[dict[str, date], dict[str, list[tuple[date, int]]]]:
    due_by_of: dict[str, date] = {}
    demand_buckets_by_article: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for besoin in loader.commandes_clients:
        if not besoin.est_commande() or besoin.qte_restante <= 0:
            continue
        if not (reference_date <= besoin.date_expedition_demandee <= horizon_end):
            continue
        demand_buckets_by_article[besoin.article].append((besoin.date_expedition_demandee, besoin.qte_restante))
        if besoin.of_contremarque:
            current_of_due = due_by_of.get(besoin.of_contremarque)
            if current_of_due is None or besoin.date_expedition_demandee < current_of_due:
                due_by_of[besoin.of_contremarque] = besoin.date_expedition_demandee

    for article, buckets in demand_buckets_by_article.items():
        buckets.sort(key=lambda item: item[0])

    return due_by_of, demand_buckets_by_article


def _select_candidates(loader, workdays, target_lines, due_dates_by_of, article_demand_buckets) -> list[CandidateOF]:
    horizon_end = workdays[-1]
    grouped_ofs: dict[tuple[str, str], list] = defaultdict(list)
    for of in loader.ofs:
        if of.qte_restante <= 0:
            continue

        line = None
        if of.article in target_lines[PP_830]:
            line = PP_830
        elif of.article in target_lines[PP_153]:
            line = PP_153
        if line is None:
            continue

        has_firm_demand = of.num_of in due_dates_by_of or of.article in article_demand_buckets
        is_buffer_bdh = of.article in BUFFER_THRESHOLDS and line == PP_153
        if not has_firm_demand and not is_buffer_bdh:
            continue

        grouped_ofs[(of.article, line)].append(of)

    candidates: list[CandidateOF] = []
    for (article, line), ofs in grouped_ofs.items():
        ofs.sort(key=lambda item: (item.date_fin, 0 if item.is_ferme() else 1, item.num_of))
        demand_buckets = article_demand_buckets.get(article, [])
        covered_quantity = 0

        for of in ofs:
            if of.num_of in due_dates_by_of:
                due_date = due_dates_by_of[of.num_of]
            elif demand_buckets:
                cumulative = 0
                due_date = demand_buckets[-1][0]
                target_quantity = covered_quantity + of.qte_restante
                for bucket_due, bucket_qty in demand_buckets:
                    cumulative += bucket_qty
                    due_date = bucket_due
                    if cumulative >= target_quantity:
                        break
                covered_quantity += of.qte_restante
            else:
                due_date = of.date_fin

            if due_date > next_workday(horizon_end):
                continue

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

    candidates.sort(key=lambda item: (item.due_date, 0 if item.is_buffer_bdh else 1, item.charge_hours))
    return candidates


def _schedule_line(line, day, candidates, loader, checker, projected_buffer, alerts) -> DaySchedule:
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

        status, reason = _availability_status(checker, loader, candidate, day)
        if status == "blocked":
            candidate.reason = reason
            if earliest_blocked_due is None or candidate.due_date < earliest_blocked_due:
                earliest_blocked_due = candidate.due_date
            continue

        requirements = _tracked_bdh_requirements(loader, candidate.article, candidate.quantity)
        if any(projected_buffer[article] < qty for article, qty in requirements.items()):
            candidate.reason = "stock tampon BDH insuffisant"
            continue

        candidate.reason = ""
        candidate.deviations = 1 if earliest_blocked_due and candidate.due_date > earliest_blocked_due else 0
        candidate.scheduled_day = day
        candidate.start_hour = round(used_hours, 3)
        used_hours += candidate.charge_hours
        candidate.end_hour = round(used_hours, 3)
        plan.assignments.append(candidate)

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


def _schedule_pp153(day, candidates, loader, checker, projected_buffer, incoming_buffer, alerts) -> DaySchedule:
    plan = DaySchedule(line=PP_153, day=day)
    used_hours = 0.0

    buffer_first = any(projected_buffer[article] < threshold for article, threshold in BUFFER_THRESHOLDS.items())

    def sort_key(candidate: CandidateOF) -> tuple:
        shortage = max(0.0, BUFFER_THRESHOLDS.get(candidate.article, 0) - projected_buffer.get(candidate.article, 0.0))
        if buffer_first and candidate.is_buffer_bdh:
            return (0, -shortage, candidate.due_date, candidate.charge_hours)
        if buffer_first and not candidate.is_buffer_bdh:
            return (1, candidate.due_date, candidate.charge_hours, candidate.article)
        return (0 if candidate.is_buffer_bdh else 1, candidate.due_date, candidate.charge_hours, candidate.article)

    for candidate in sorted(candidates, key=sort_key):
        if candidate.scheduled_day is not None:
            continue
        if used_hours + candidate.charge_hours > LINE_CAPACITY_HOURS:
            continue

        status, reason = _availability_status(checker, loader, candidate, day)
        if status == "blocked":
            candidate.reason = reason
            continue

        candidate.reason = ""
        candidate.scheduled_day = day
        candidate.start_hour = round(used_hours, 3)
        used_hours += candidate.charge_hours
        candidate.end_hour = round(used_hours, 3)
        plan.assignments.append(candidate)

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


def _availability_status(checker, loader, candidate, day: date) -> tuple[str, str]:
    date_j2 = previous_workday(day, 2)
    date_j1 = previous_workday(day, 1)
    date_j0 = day

    for status, need_date in (
        ("comfortable", date_j2),
        ("comfortable", date_j1),
        ("tight", date_j0),
    ):
        result = checker._check_article_recursive(
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
    return "blocked", "composants indisponibles"


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
