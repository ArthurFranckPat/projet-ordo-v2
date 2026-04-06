from typing import Optional
from .models import CandidateOF


def pp830_sort_key(
    candidate: CandidateOF,
    last_article: Optional[str],
    loader,
    family_counts: dict[str, int],
    kanban_conso: dict[str, float],
    kanban_articles: set[str],
    tracked_kanban_requirements_fn,
) -> tuple:
    priority = 0 if candidate.is_buffer_bdh else 1
    serie_bonus = 0 if candidate.article == last_article else 1

    mix_penalty = 0
    art_info = loader.get_article(candidate.article)
    if art_info:
        desc = art_info.description.upper()
        parts = desc.split()
        fam_cand = next(
            (
                p
                for p in parts
                if len(p) >= 3
                and p not in ["ESH", "ESHKIT", "ESHGPE", "CBL", "CPT", "BDH", "BIP", "GP", "PNEU", "BOIT"]
            ),
            None,
        )
        if fam_cand:
            if family_counts:
                avg_other = sum(c for f, c in family_counts.items() if f != fam_cand) / max(
                    1, len(family_counts) - (1 if fam_cand in family_counts else 0)
                )
                if family_counts.get(fam_cand, 0) > avg_other + 1:
                    mix_penalty = 1

    kanban_penalty = 0
    kanban_reqs = tracked_kanban_requirements_fn(loader, candidate.article, candidate.quantity, kanban_articles)
    for k_art, qty_needed in kanban_reqs.items():
        current_conso = kanban_conso[k_art]
        kanban_penalty += int((current_conso + qty_needed) / 100)

    return (
        priority,
        mix_penalty,
        kanban_penalty,
        serie_bonus,
        candidate.due_date,
        candidate.charge_hours,
        candidate.article,
    )


def pp153_sort_key(
    candidate: CandidateOF,
    last_article: Optional[str],
    shortage_articles: set[str],
    loader,
) -> tuple:
    if candidate.is_buffer_bdh and candidate.article in shortage_articles:
        priority = 0
    elif not candidate.is_buffer_bdh:
        priority = 1
    else:
        priority = 2

    serie_bonus = 1
    if last_article:
        if candidate.article == last_article:
            serie_bonus = 0
        else:
            last_nom = loader.get_nomenclature(last_article)
            cand_nom = loader.get_nomenclature(candidate.article)
            if last_nom and cand_nom:
                last_comps = {c.article_composant for c in last_nom.composants}
                cand_comps = {c.article_composant for c in cand_nom.composants}
                if last_comps & cand_comps:
                    serie_bonus = 0.5

    return (
        priority,
        serie_bonus,
        candidate.due_date,
        candidate.charge_hours,
        candidate.article,
    )
