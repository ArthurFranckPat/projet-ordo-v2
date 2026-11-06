import re

with open("src/scheduler/engine.py", "r") as f:
    content = f.read()

# 1. Update imports
content = content.replace("from .lines import PP830Scheduler, PP153Scheduler", "from .lines import GenericLineScheduler")

# 2. Update run_schedule signature
content = content.replace("def run_schedule(\n    loader,", "def run_schedule(\n    loader,\n    lines_config: Optional[list[str]] = None,")

# 3. Update target_lines
content = content.replace("target_lines = _build_target_line_articles(loader)", "target_lines = _build_target_line_articles(loader, lines_config)")

# 4. Update day_plans and by_line initialization
old_day_plans = """    day_plans = {
        PP_830: [DaySchedule(line=PP_830, day=day) for day in workdays],
        PP_153: [DaySchedule(line=PP_153, day=day) for day in workdays],
    }"""
new_day_plans = """    day_plans = {
        line: [DaySchedule(line=line, day=day) for day in workdays]
        for line in target_lines.keys()
    }"""
content = content.replace(old_day_plans, new_day_plans)

old_by_line = """    by_line = {
        PP_830: [candidate for candidate in candidates if candidate.line == PP_830],
        PP_153: [candidate for candidate in candidates if candidate.line == PP_153],
    }"""
new_by_line = """    by_line = {
        line: [candidate for candidate in candidates if candidate.line == line]
        for line in target_lines.keys()
    }"""
content = content.replace(old_by_line, new_by_line)

# 5. Schedulers initialization
old_schedulers = """    pp830_scheduler = PP830Scheduler()
    pp153_scheduler = PP153Scheduler()"""
new_schedulers = """    schedulers = {line: GenericLineScheduler(line) for line in target_lines.keys()}"""
content = content.replace(old_schedulers, new_schedulers)

# 6. Scheduling loop
old_scheduling_loop = """        pp830_day = pp830_scheduler.schedule_day(
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
        day_plans[PP_153][workdays.index(day)] = pp153_day"""
new_scheduling_loop = """        for line, scheduler in schedulers.items():
            day_plan = scheduler.schedule_day(
                day=day,
                candidates=by_line[line],
                loader=loader,
                checker=checker,
                projected_buffer=projected_buffer,
                incoming_buffer=incoming_buffer,
                material_state=material_state,
                alerts=alerts,
            )
            day_plans[line][workdays.index(day)] = day_plan
            
            for assignment in day_plan.assignments:
                for article, qty in tracked_bdh_requirements(loader, assignment.article, assignment.quantity).items():
                    projected_buffer[article] -= qty"""
content = content.replace(old_scheduling_loop, new_scheduling_loop)

# 7. Collect plannings
old_plannings = """    planning_pp830 = [assignment for plan in day_plans[PP_830] for assignment in plan.assignments]
    planning_pp153 = [assignment for plan in day_plans[PP_153] for assignment in plan.assignments]
    _mark_unscheduled_candidates(by_line, alerts)
    unscheduled_rows = build_unscheduled_rows(by_line)

    planned_by_of = {assignment.num_of: assignment.scheduled_day for assignment in (planning_pp830 + planning_pp153)}"""
new_plannings = """    plannings = {
        line: [assignment for plan in day_plans[line] for assignment in plan.assignments]
        for line in target_lines.keys()
    }
    _mark_unscheduled_candidates(by_line, alerts)
    unscheduled_rows = build_unscheduled_rows(by_line)

    all_assignments = [a for p in plannings.values() for a in p]
    planned_by_of = {assignment.num_of: assignment.scheduled_day for assignment in all_assignments}"""
content = content.replace(old_plannings, new_plannings)

old_nb_deviations = """    deviation_penalty = min(
        1.0,
        nb_deviations / max(1, len(planning_pp830) + len(planning_pp153)),
    )

    nb_jit = sum(1 for c in planning_pp830 + planning_pp153 if c.scheduled_day == c.due_date)
    jit_penalty = min(
        1.0,
        nb_jit / max(1, len(planning_pp830) + len(planning_pp153)),
    )"""
new_nb_deviations = """    deviation_penalty = min(
        1.0,
        nb_deviations / max(1, len(all_assignments)),
    )

    nb_jit = sum(1 for c in all_assignments if c.scheduled_day == c.due_date)
    jit_penalty = min(
        1.0,
        nb_jit / max(1, len(all_assignments)),
    )"""
content = content.replace(old_nb_deviations, new_nb_deviations)

old_nb_changements = """    nb_changements_serie = sum(
        1 for plan in day_plans[PP_830] + day_plans[PP_153]
        for i in range(1, len(plan.assignments))
        if plan.assignments[i].article != plan.assignments[i-1].article
    )"""
new_nb_changements = """    nb_changements_serie = sum(
        1 for plans in day_plans.values() for plan in plans
        for i in range(1, len(plan.assignments))
        if plan.assignments[i].article != plan.assignments[i-1].article
    )"""
content = content.replace(old_nb_changements, new_nb_changements)

old_result = """    result = SchedulerResult(
        score=round(score, 3),
        taux_service=round(taux_service, 3),
        taux_ouverture=round(taux_ouverture, 3),
        nb_deviations=nb_deviations,
        nb_jit=nb_jit,
        nb_changements_serie=nb_changements_serie,
        planning_pp830=planning_pp830,
        planning_pp153=planning_pp153,
        stock_projection=stock_projection,"""
new_result = """    result = SchedulerResult(
        score=round(score, 3),
        taux_service=round(taux_service, 3),
        taux_ouverture=round(taux_ouverture, 3),
        nb_deviations=nb_deviations,
        nb_jit=nb_jit,
        nb_changements_serie=nb_changements_serie,
        plannings=plannings,
        stock_projection=stock_projection,"""
content = content.replace(old_result, new_result)

# Replace build functions
content = re.sub(
    r"def _build_target_line_articles\(loader\) -> dict\[str, set\[str\]\]:.*?return target_lines",
    """def _build_target_line_articles(loader, lines_config=None) -> dict[str, set[str]]:
    target_lines = {}
    if lines_config is None:
        lines_config = {op.poste_charge for gamme in loader.gammes.values() for op in gamme.operations}
    
    for line in lines_config:
        target_lines[line] = set()

    for article, gamme in loader.gammes.items():
        for op in gamme.operations:
            if op.poste_charge in target_lines:
                target_lines[op.poste_charge].add(article)
    return target_lines""",
    content,
    flags=re.DOTALL
)

content = re.sub(
    r"def _is_target_scope_order\(besoin, loader, target_lines\) -> bool:.*?return False",
    """def _is_target_scope_order(besoin, loader, target_lines) -> bool:
    if any(besoin.article in articles for articles in target_lines.values()):
        return True
    if besoin.of_contremarque:
        linked_of = loader.get_of_by_num(besoin.of_contremarque)
        if linked_of is not None:
            if any(linked_of.article in articles for articles in target_lines.values()):
                return True
    return False""",
    content,
    flags=re.DOTALL
)

# Update _select_candidates_from_matching
old_line_selection = """        line = None
        if of.article in target_lines[PP_830]:
            line = PP_830
        elif of.article in target_lines[PP_153]:
            line = PP_153
        if line is None:
            continue"""
new_line_selection = """        line = None
        for l, articles in target_lines.items():
            if of.article in articles:
                line = l
                break
        if line is None:
            continue"""
content = content.replace(old_line_selection, new_line_selection)

old_bdh = """        for of in buffer_ofs[:25]:
            candidate_specs.setdefault(
                of.num_of,
                {
                    'of': of,
                    'line': PP_153,
                    'due_date': of.date_fin,
                    'orders': set(),
                },
            )"""
new_bdh = """        for of in buffer_ofs[:25]:
            line = None
            for l, articles in target_lines.items():
                if tracked_article in articles:
                    line = l
                    break
            if line:
                candidate_specs.setdefault(
                    of.num_of,
                    {
                        'of': of,
                        'line': line,
                        'due_date': of.date_fin,
                        'orders': set(),
                    },
                )"""
content = content.replace(old_bdh, new_bdh)

old_is_buffer_bdh = """is_buffer_bdh=of.article in BUFFER_THRESHOLDS and line == PP_153,"""
new_is_buffer_bdh = """is_buffer_bdh=of.article in BUFFER_THRESHOLDS,"""
content = content.replace(old_is_buffer_bdh, new_is_buffer_bdh)

with open("src/scheduler/engine.py", "w") as f:
    f.write(content)
