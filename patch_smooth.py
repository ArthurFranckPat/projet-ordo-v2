import re

with open("src/scheduler/engine.py", "r") as f:
    content = f.read()

old_block = """    # Determiner la capacité par ligne
    from ..agents.organization.charge_calculator import ChargeCalculator
    from ..algorithms.matching import CommandeOFMatcher
    calculator = ChargeCalculator(loader)
    matcher_capa = CommandeOFMatcher(loader, date_tolerance_days=30)
    hours_per_poste = calculator.calculate_charge_for_horizon(reference_date, 1, matcher_capa)
    
    # Règle : Target = max(7.0, charge S+1 / 5 jours).
    line_capacities = {}
    line_min_open = {}
    for line in target_lines.keys():
        target_hours = hours_per_poste.get(line, 0) / 5.0
        # On peut caper à 14h max par exemple, mais laisser un min de 0 (pour que les petites charges passent)
        # Mais le min open ne devrait pas bloquer si on a un besoin. On met 7.0 par défaut, ou moins si target est faible.
        capacity = max(7.0, min(14.0, target_hours * 1.5)) # Marge de 50% pour absorber
        min_open = 0.0 # Ne pas fermer la ligne si on a de la charge
        line_capacities[line] = capacity
        line_min_open[line] = min_open

    candidates, alerts, matching_results = _select_candidates_from_matching(
        loader, workdays, demand_horizon_end, target_lines
    )"""

new_block = """    candidates, alerts, matching_results = _select_candidates_from_matching(
        loader, workdays, demand_horizon_end, target_lines
    )

    # Calcul de la charge brute cible par ligne en se basant sur les candidats réels
    # Cela inclut les commandes fermes, prévisions (si NOR) et les tampons BDH
    hours_per_poste = {}
    max_of_per_poste = {}
    for c in candidates:
        hours_per_poste[c.line] = hours_per_poste.get(c.line, 0.0) + c.charge_hours
        max_of_per_poste[c.line] = max(max_of_per_poste.get(c.line, 0.0), c.charge_hours)

    line_capacities = {}
    line_min_open = {}
    for line in target_lines.keys():
        target_hours = hours_per_poste.get(line, 0.0)
        max_of = max_of_per_poste.get(line, 0.0)
        
        if target_hours == 0:
            line_capacities[line] = 7.0
            line_min_open[line] = 0.0
            continue
            
        # Lissage de la charge :
        # On détermine le nombre de jours actifs nécessaires (base 1 shift = 7h)
        active_days = max(1, round(target_hours / 7.0))
        active_days = min(len(workdays), active_days)
        
        # Charge journalière lissée sur les jours actifs
        smoothed_daily = target_hours / active_days
        
        # Marge fine (5%) pour le bin packing, afin d'éviter les sauts d'ouverture en fin de semaine
        capacity = smoothed_daily * 1.05
        
        # On garantit au moins un shift (7h) ou la taille du plus gros OF pour ne pas le bloquer
        capacity = max(7.0, capacity, max_of)
        
        # Capacité physique maximale : 2 shifts (14h)
        capacity = min(14.0, capacity)
        
        line_capacities[line] = capacity
        line_min_open[line] = 0.0"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("src/scheduler/engine.py", "w") as f:
        f.write(content)
    print("Patch applied successfully.")
else:
    print("Old block not found. File may have been changed.")