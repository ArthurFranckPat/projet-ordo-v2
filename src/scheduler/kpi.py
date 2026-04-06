"""Calcul des KPIs AUTORESEARCH."""

from __future__ import annotations

import json
from pathlib import Path

from .capacity import MAX_DAY_HOURS, TARGET_LINES, is_line_open
from .models import CandidateOF, PlanningKPIs, ScheduledTask

DEFAULT_WEIGHTS = {
    "w1": 0.7,
    "w2": 0.2,
    "w3": 0.1,
}


def load_weights(path: str | Path) -> dict[str, float]:
    """Charge les poids et les renormalise si besoin."""
    file_path = Path(path)
    if not file_path.exists():
        return DEFAULT_WEIGHTS.copy()

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    weights = {
        "w1": float(data.get("w1", DEFAULT_WEIGHTS["w1"])),
        "w2": float(data.get("w2", DEFAULT_WEIGHTS["w2"])),
        "w3": float(data.get("w3", DEFAULT_WEIGHTS["w3"])),
    }
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {key: value / total for key, value in weights.items()}


def compute_kpis(
    candidates: list[CandidateOF],
    planned_tasks: list[ScheduledTask],
    horizon_days: list,
    deviations: int,
    weights: dict[str, float],
) -> PlanningKPIs:
    """Calcule les KPIs exposes par le scheduler.

    Les OF de type `buffer` servent la robustesse du systeme mais ne doivent pas
    degrader artificiellement le taux de service client.
    """
    planned_by_num = {task.num_of: task for task in planned_tasks}
    service_candidates = [candidate for candidate in candidates if candidate.kind != "buffer"] or candidates
    total_candidates = len(service_candidates)
    on_time = 0
    for candidate in service_candidates:
        task = planned_by_num.get(candidate.num_of)
        if task and task.scheduled_day <= candidate.due_date:
            on_time += 1

    taux_service = on_time / total_candidates if total_candidates else 0.0

    hours_by_day_line = {(day, line): 0.0 for day in horizon_days for line in TARGET_LINES}
    for task in planned_tasks:
        hours_by_day_line[(task.scheduled_day, task.line)] += task.charge_hours

    total_available_hours = len(hours_by_day_line) * MAX_DAY_HOURS
    planned_hours = sum(hours_by_day_line.values())
    taux_ouverture = planned_hours / total_available_hours if total_available_hours else 0.0

    deviation_ratio = deviations / max(total_candidates, 1)
    raw_score = (
        taux_service * weights["w1"]
        + taux_ouverture * weights["w2"]
        - deviation_ratio * weights["w3"]
    )
    score = max(0.0, min(1.0, raw_score))

    return PlanningKPIs(
        taux_service=round(taux_service, 4),
        taux_ouverture=round(taux_ouverture, 4),
        nb_deviations=deviations,
        score=round(score, 4),
    )
