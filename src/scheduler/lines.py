from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from .models import CandidateOF, DaySchedule
from .calendar import next_workday
from .material import (
    BUFFER_THRESHOLDS,
    availability_status,
    tracked_bdh_requirements,
    tracked_kanban_requirements,
    format_buffer_shortage_reason,
    reserve_candidate_components,
)
from .heuristics import pp830_sort_key, pp153_sort_key

LINE_CAPACITY_HOURS = 14.0
LINE_MIN_OPEN_HOURS = 7.0
SETUP_TIME_HOURS = 0.25


class LineScheduler(ABC):
    """Classe abstraite pour la planification d'une ligne."""
    
    def __init__(self, line_name: str):
        self.line_name = line_name

    @abstractmethod
    def schedule_day(self, day: date, candidates: list[CandidateOF], loader, checker, projected_buffer: dict[str, float], incoming_buffer: dict[date, dict[str, int]], material_state, alerts: list[str]) -> DaySchedule:
        pass

    def _mark_candidate_deviation(self, candidate: CandidateOF, earliest_blocked_due: Optional[date], deviation_marked: bool) -> bool:
        candidate.deviations = 0
        if (
            not deviation_marked
            and earliest_blocked_due is not None
            and not candidate.is_buffer_bdh
            and candidate.due_date > earliest_blocked_due
        ):
            candidate.deviations = 1
            return True
        return deviation_marked

    def _assign_candidate_time(self, candidate: CandidateOF, last_article: Optional[str], used_hours: float, day: date) -> float:
        setup_time = SETUP_TIME_HOURS if last_article and candidate.article != last_article else 0.0
        used_hours += setup_time
        candidate.scheduled_day = day
        candidate.start_hour = round(used_hours, 3)
        used_hours += candidate.charge_hours
        candidate.end_hour = round(used_hours, 3)
        return used_hours

    def _handle_under_capacity(self, plan: DaySchedule, day: date, incoming_buffer: dict[date, dict[str, int]], alerts: list[str]) -> None:
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
                alerts.append(f"{self.line_name} {day.isoformat()} : ligne fermée car charge < 7h")
            plan.assignments = []


class PP830Scheduler(LineScheduler):
    def __init__(self):
        super().__init__("PP_830")

    def schedule_day(self, day: date, candidates: list[CandidateOF], loader, checker, projected_buffer: dict[str, float], incoming_buffer: dict[date, dict[str, int]], material_state, alerts: list[str]) -> DaySchedule:
        plan = DaySchedule(line=self.line_name, day=day)
        used_hours = 0.0
        earliest_blocked_due: Optional[date] = None
        deviation_marked = False

        unscheduled = [c for c in candidates if c.scheduled_day is None and c.charge_hours > 0]
        last_article = None
        
        family_counts = {}
        kanban_articles = {"11028877", "11033880", "11033919"}
        kanban_conso = {a: 0.0 for a in kanban_articles}

        while unscheduled and used_hours < LINE_CAPACITY_HOURS:
            def sort_key(candidate: CandidateOF) -> tuple:
                return pp830_sort_key(
                    candidate,
                    last_article,
                    loader,
                    family_counts,
                    kanban_conso,
                    kanban_articles,
                    tracked_kanban_requirements
                )

            unscheduled.sort(key=sort_key)
            
            candidate_idx = -1
            for i, c in enumerate(unscheduled):
                setup_time = SETUP_TIME_HOURS if last_article and c.article != last_article else 0.0
                if used_hours + c.charge_hours + setup_time <= LINE_CAPACITY_HOURS:
                    status, reason = availability_status(checker, loader, c, day, material_state)
                    if status != "blocked":
                        requirements = tracked_bdh_requirements(loader, c.article, c.quantity)
                        if not any(projected_buffer[article] < qty for article, qty in requirements.items()):
                            candidate_idx = i
                            break
                        else:
                            c.reason = format_buffer_shortage_reason(requirements, projected_buffer)
                            if earliest_blocked_due is None or c.due_date < earliest_blocked_due:
                                earliest_blocked_due = c.due_date
                    else:
                        c.reason = reason
                        if earliest_blocked_due is None or c.due_date < earliest_blocked_due:
                            earliest_blocked_due = c.due_date
                    
            if candidate_idx == -1:
                break 
                
            candidate = unscheduled.pop(candidate_idx)

            status, reason = availability_status(checker, loader, candidate, day, material_state)
            requirements = tracked_bdh_requirements(loader, candidate.article, candidate.quantity)
            
            candidate.reason = ""
            deviation_marked = self._mark_candidate_deviation(candidate, earliest_blocked_due, deviation_marked)
                
            used_hours = self._assign_candidate_time(candidate, last_article, used_hours, day)
            
            plan.assignments.append(candidate)
            last_article = candidate.article
            
            art_info = loader.get_article(candidate.article)
            if art_info:
                desc = art_info.description.upper()
                parts = desc.split()
                fam_cand = next((p for p in parts if len(p) >= 3 and p not in ["ESH", "ESHKIT", "ESHGPE", "CBL", "CPT", "BDH", "BIP", "GP", "PNEU", "BOIT"]), None)
                if fam_cand:
                    family_counts[fam_cand] = family_counts.get(fam_cand, 0) + 1
                    
            kanban_reqs = tracked_kanban_requirements(loader, candidate.article, candidate.quantity, kanban_articles)
            for k_art, qty_needed in kanban_reqs.items():
                kanban_conso[k_art] += qty_needed

            reserve_candidate_components(loader, checker, candidate, day, material_state)
            
            for article, qty in requirements.items():
                projected_buffer[article] -= qty

        self._handle_under_capacity(plan, day, incoming_buffer, alerts)

        return plan


class PP153Scheduler(LineScheduler):
    def __init__(self):
        super().__init__("PP_153")

    def schedule_day(self, day: date, candidates: list[CandidateOF], loader, checker, projected_buffer: dict[str, float], incoming_buffer: dict[date, dict[str, int]], material_state, alerts: list[str]) -> DaySchedule:
        plan = DaySchedule(line=self.line_name, day=day)
        used_hours = 0.0
        earliest_blocked_due: Optional[date] = None
        deviation_marked = False

        shortage_articles = {
            article
            for article, threshold in BUFFER_THRESHOLDS.items()
            if projected_buffer.get(article, 0.0) < threshold
        }

        unscheduled = [c for c in candidates if c.scheduled_day is None]
        last_article = None

        while unscheduled and used_hours < LINE_CAPACITY_HOURS:
            def sort_key(candidate: CandidateOF) -> tuple:
                return pp153_sort_key(
                    candidate,
                    last_article,
                    shortage_articles,
                    loader
                )

            unscheduled.sort(key=sort_key)
            
            candidate_idx = -1
            for i, c in enumerate(unscheduled):
                setup_time = SETUP_TIME_HOURS if last_article and c.article != last_article else 0.0
                if used_hours + c.charge_hours + setup_time <= LINE_CAPACITY_HOURS:
                    status, _ = availability_status(checker, loader, c, day, material_state)
                    if status != "blocked":
                        candidate_idx = i
                        break
                    else:
                        if earliest_blocked_due is None or c.due_date < earliest_blocked_due:
                            earliest_blocked_due = c.due_date
                    
            if candidate_idx == -1:
                break 
                
            candidate = unscheduled.pop(candidate_idx)

            status, reason = availability_status(checker, loader, candidate, day, material_state)
            
            candidate.reason = ""
            deviation_marked = self._mark_candidate_deviation(candidate, earliest_blocked_due, deviation_marked)
                
            used_hours = self._assign_candidate_time(candidate, last_article, used_hours, day)
            
            plan.assignments.append(candidate)
            last_article = candidate.article
            reserve_candidate_components(loader, checker, candidate, day, material_state)
            
            if candidate.is_buffer_bdh:
                availability_day = next_workday(day)
                incoming_buffer[availability_day][candidate.article] += candidate.quantity
                
            if candidate.is_buffer_bdh and candidate.article in shortage_articles:
                projected_buffer[candidate.article] += candidate.quantity
                if projected_buffer[candidate.article] >= BUFFER_THRESHOLDS[candidate.article]:
                    shortage_articles.remove(candidate.article)

        self._handle_under_capacity(plan, day, incoming_buffer, alerts)

        return plan
