"""Modeles pour le scheduler AUTORESEARCH."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class CandidateOF:
    """OF candidat au planning journalier."""

    num_of: str
    article: str
    description: str
    line: str
    due_date: date
    charge_hours: float
    quantity: int
    tracked_bdh_qty: dict[str, int] = field(default_factory=dict)
    related_orders: list[str] = field(default_factory=list)
    kind: str = "direct"


@dataclass(frozen=True)
class ScheduledTask:
    """Affectation d'un OF sur une journee."""

    num_of: str
    article: str
    line: str
    scheduled_day: date
    start_hour: float
    end_hour: float
    charge_hours: float
    due_date: date
    quantity: int
    comfortable: bool
    kind: str


@dataclass(frozen=True)
class BufferSnapshot:
    """Etat projete du stock BDH a une date."""

    day: date
    article: str
    stock_projected: int


@dataclass(frozen=True)
class PlanningKPIs:
    """KPIs exposes par le scheduler."""

    taux_service: float
    taux_ouverture: float
    nb_deviations: int
    score: float


@dataclass(frozen=True)
class PlanningResult:
    """Resultat complet du scheduler."""

    planning_pp830: list[ScheduledTask]
    planning_pp153: list[ScheduledTask]
    stock_projection: list[BufferSnapshot]
    alerts: list[str]
    kpis: PlanningKPIs
