"""Rapport d'actions appro sur les ruptures composants du plan S+1."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from rich.console import Console
from rich.table import Table

from ..algorithms.matching import MatchingResult
from ..checkers.base import FeasibilityResult
from ..loaders.data_loader import DataLoader


console = Console()

NO_SUPPLIER = "SANS_FOURNISSEUR"
NO_PURCHASE_ORDER = "APPRO SANS CA OUVERTE"

ACTION_MESSAGES = {
    "RETARD_FOURNISSEUR": "Relancer immédiatement le fournisseur et la commande achat ouverte.",
    "COUVERTURE_TARDIVE": "Demander l'avancement de la réception ou arbitrer avec l'ordonnancement.",
    "AUCUNE_COUVERTURE": "Lancer ou confirmer l'approvisionnement sans délai.",
    "SURVEILLANCE": "Suivre la réception planifiée et confirmer la disponibilité au lancement.",
}

ACTION_PRIORITY = {
    "RETARD_FOURNISSEUR": 0,
    "AUCUNE_COUVERTURE": 1,
    "COUVERTURE_TARDIVE": 2,
    "SURVEILLANCE": 3,
}


@dataclass
class ComponentActionLine:
    """Ligne de rapport par composant bloquant."""

    article_composant: str
    description: Optional[str]
    missing_qty_total: int
    nb_ofs_impactes: int
    ofs_impactes: List[str]
    commandes_impactees: List[str]
    nb_commandes_impactees: int
    date_expedition_la_plus_proche: Optional[date]
    stock_disponible: int
    qte_reception_attendue: Optional[int]
    date_premiere_reception: Optional[date]
    fournisseurs_concernes: List[str]
    commandes_achat_concernees: List[str]
    niveau_action: str
    action_recommandee: str
    supplier_refs: List[tuple[str, str]] = field(default_factory=list, repr=False)


@dataclass
class SupplierActionLine:
    """Ligne d'exécution appro par fournisseur / commande achat."""

    fournisseur: str
    num_commande_achat: str
    articles_concernes: List[str]
    nb_components: int
    nb_ofs_impactes: int
    nb_commandes_impactees: int
    date_action_la_plus_urgente: Optional[date]
    action_recommandee: str


@dataclass
class ActionReport:
    """Rapport d'actions appro pour le plan S+1."""

    reference_date: date
    component_lines: List[ComponentActionLine] = field(default_factory=list)
    supplier_lines: List[SupplierActionLine] = field(default_factory=list)
    components_without_coverage: List[ComponentActionLine] = field(default_factory=list)
    impacted_ofs: int = 0
    impacted_commandes: int = 0


def build_action_report(
    loader: DataLoader,
    resultats_matching: List[MatchingResult],
    resultats_faisabilite: Dict[str, FeasibilityResult],
    reference_date: Optional[date] = None,
) -> ActionReport:
    """Construit le rapport d'actions appro à partir du plan S+1."""
    if reference_date is None:
        reference_date = date.today()

    of_contexts = _collect_failing_of_contexts(resultats_matching, resultats_faisabilite)
    component_lines = _build_component_lines(loader, of_contexts, reference_date)
    supplier_lines = _build_supplier_lines(component_lines)

    impacted_ofs = len({of for line in component_lines for of in line.ofs_impactes})
    impacted_commandes = len(
        {commande for line in component_lines for commande in line.commandes_impactees}
    )

    return ActionReport(
        reference_date=reference_date,
        component_lines=component_lines,
        supplier_lines=supplier_lines,
        components_without_coverage=[
            line for line in component_lines if line.niveau_action == "AUCUNE_COUVERTURE"
        ],
        impacted_ofs=impacted_ofs,
        impacted_commandes=impacted_commandes,
    )


def render_action_report_console(report: ActionReport) -> None:
    """Affiche une synthèse console du rapport d'actions."""
    console.print()
    console.print(
        f"[bold cyan]📣 Rapport d'actions appro S+1 — "
        f"{report.reference_date.strftime('%d/%m/%Y')}[/bold cyan]"
    )

    if not report.component_lines:
        console.print("[green]Aucun composant bloquant détecté sur le plan S+1.[/green]")
        console.print()
        return

    console.print(
        f"[bold]Composants critiques :[/bold] {len(report.component_lines)}"
        f" | OF impactés : {report.impacted_ofs}"
        f" | Commandes impactées : {report.impacted_commandes}"
    )

    table = Table(title="Vue composant", show_lines=False)
    table.add_column("Composant", style="cyan", no_wrap=True)
    table.add_column("Manque", justify="right")
    table.add_column("Cmd", justify="right")
    table.add_column("OF", justify="right")
    table.add_column("Échéance", style="white")
    table.add_column("Réception", style="white")
    table.add_column("Action", style="yellow")

    for line in report.component_lines:
        table.add_row(
            line.article_composant,
            str(line.missing_qty_total),
            str(line.nb_commandes_impactees),
            str(line.nb_ofs_impactes),
            _format_date(line.date_expedition_la_plus_proche),
            _format_reception(line),
            line.niveau_action,
        )

    console.print(table)

    supplier_table = Table(title="Vue fournisseur / commande achat", show_lines=False)
    supplier_table.add_column("Fournisseur", style="cyan")
    supplier_table.add_column("CA", style="white")
    supplier_table.add_column("Articles", style="white")
    supplier_table.add_column("Cmd", justify="right")
    supplier_table.add_column("OF", justify="right")
    supplier_table.add_column("Urgence", style="white")
    supplier_table.add_column("Action", style="yellow")

    for line in report.supplier_lines:
        supplier_table.add_row(
            str(line.fournisseur),
            str(line.num_commande_achat),
            ", ".join(str(article) for article in line.articles_concernes[:3]),
            str(line.nb_commandes_impactees),
            str(line.nb_ofs_impactes),
            _format_date(line.date_action_la_plus_urgente),
            str(line.action_recommandee),
        )

    console.print(supplier_table)
    console.print()


def write_action_report_markdown(report: ActionReport, output_path: str) -> None:
    """Écrit le rapport d'actions au format Markdown."""
    lines: List[str] = [
        "# Rapport d'actions appro S+1",
        "",
        f"Généré le : {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"Date de référence : {report.reference_date.strftime('%d/%m/%Y')}",
        "",
        "## Résumé exécutif",
        "",
        f"- Composants critiques : {len(report.component_lines)}",
        f"- OF impactés : {report.impacted_ofs}",
        f"- Commandes impactées : {report.impacted_commandes}",
        f"- Composants sans couverture identifiée : {len(report.components_without_coverage)}",
        "",
    ]

    if not report.component_lines:
        lines.extend(
            [
                "Aucun composant bloquant détecté sur le plan S+1.",
                "",
                "## Actions appro par fournisseur / CA",
                "",
                "Aucune action requise.",
                "",
                "## Composants sans couverture identifiée",
                "",
                "Aucun.",
            ]
        )
        _write_lines(output_path, lines)
        return

    lines.extend(["## Composants critiques", ""])
    for line in report.component_lines:
        lines.extend(
            [
                f"### {line.article_composant} — {line.niveau_action}",
                "",
                f"- Description : {line.description or 'N/A'}",
                f"- Quantité manquante totale : {line.missing_qty_total}",
                f"- Stock disponible : {line.stock_disponible}",
                f"- Commandes impactées ({line.nb_commandes_impactees}) : "
                f"{', '.join(line.commandes_impactees) if line.commandes_impactees else 'Aucune'}",
                f"- OF impactés ({line.nb_ofs_impactes}) : "
                f"{', '.join(line.ofs_impactes) if line.ofs_impactes else 'Aucun'}",
                f"- Première échéance client : {_format_date(line.date_expedition_la_plus_proche)}",
                f"- Réceptions ouvertes : {_format_reception(line)}",
                f"- Fournisseurs concernés : "
                f"{', '.join(line.fournisseurs_concernes) if line.fournisseurs_concernes else 'Aucun'}",
                f"- Commandes achat concernées : "
                f"{', '.join(line.commandes_achat_concernees) if line.commandes_achat_concernees else NO_PURCHASE_ORDER}",
                f"- Action recommandée : {line.action_recommandee}",
                "",
            ]
        )

    lines.extend(["## Actions appro par fournisseur / CA", ""])
    for line in report.supplier_lines:
        lines.extend(
            [
                f"### {line.fournisseur} / {line.num_commande_achat}",
                "",
                f"- Articles concernés ({line.nb_components}) : {', '.join(line.articles_concernes)}",
                f"- Commandes impactées : {line.nb_commandes_impactees}",
                f"- OF impactés : {line.nb_ofs_impactes}",
                f"- Date la plus urgente : {_format_date(line.date_action_la_plus_urgente)}",
                f"- Action recommandée : {line.action_recommandee}",
                "",
            ]
        )

    lines.extend(["## Composants sans couverture identifiée", ""])
    if report.components_without_coverage:
        for line in report.components_without_coverage:
            lines.append(
                f"- {line.article_composant} — manque {line.missing_qty_total}, "
                f"échéance {_format_date(line.date_expedition_la_plus_proche)}"
            )
    else:
        lines.append("Aucun.")

    _write_lines(output_path, lines)


def _collect_failing_of_contexts(
    resultats_matching: Iterable[MatchingResult],
    resultats_faisabilite: Dict[str, FeasibilityResult],
) -> Dict[str, dict]:
    contexts: Dict[str, dict] = {}

    for match in resultats_matching:
        if match.of is None:
            continue

        feasibility = resultats_faisabilite.get(match.of.num_of)
        if feasibility is None or feasibility.feasible or not feasibility.missing_components:
            continue

        context = contexts.setdefault(
            match.of.num_of,
            {
                "of": match.of,
                "feasibility": feasibility,
                "commandes": [],
            },
        )
        context["commandes"].append(match.commande)

    return contexts


def _build_component_lines(
    loader: DataLoader,
    of_contexts: Dict[str, dict],
    reference_date: date,
) -> List[ComponentActionLine]:
    aggregated: Dict[str, dict] = {}

    for of_num, context in of_contexts.items():
        of = context["of"]
        commandes = context["commandes"]
        feasibility = context["feasibility"]

        for article_composant, quantity in feasibility.missing_components.items():
            entry = aggregated.setdefault(
                article_composant,
                {
                    "missing_qty_total": 0,
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                    "fallback_dates": [],
                },
            )
            entry["missing_qty_total"] += int(quantity)
            entry["ofs"].add(of_num)
            entry["fallback_dates"].append(of.date_fin)

            for commande in commandes:
                entry["commandes"].add(commande.num_commande)
                entry["dates"].append(commande.date_expedition_demandee)

    lines: List[ComponentActionLine] = []
    for article_composant, entry in aggregated.items():
        receptions = [
            reception
            for reception in loader.get_receptions(article_composant)
            if reception.quantite_restante > 0
        ]
        receptions.sort(key=lambda r: r.date_reception_prevue)

        stock = loader.get_stock(article_composant)
        stock_disponible = stock.disponible() if stock else 0
        qte_reception_attendue = sum(r.quantite_restante for r in receptions) or None
        date_premiere_reception = receptions[0].date_reception_prevue if receptions else None

        commandes_achat = _unique_preserve_order(r.num_commande for r in receptions if r.num_commande)
        fournisseurs = _unique_preserve_order(
            r.code_fournisseur for r in receptions if r.code_fournisseur
        )
        supplier_refs = _unique_supplier_refs(receptions)
        date_expedition = (
            min(entry["dates"]) if entry["dates"] else min(entry["fallback_dates"], default=None)
        )
        niveau_action = _classify_component_action(receptions, reference_date, date_expedition)
        description = _get_article_description(loader, article_composant)

        lines.append(
            ComponentActionLine(
                article_composant=article_composant,
                description=description,
                missing_qty_total=entry["missing_qty_total"],
                nb_ofs_impactes=len(entry["ofs"]),
                ofs_impactes=sorted(entry["ofs"]),
                commandes_impactees=sorted(entry["commandes"]),
                nb_commandes_impactees=len(entry["commandes"]),
                date_expedition_la_plus_proche=date_expedition,
                stock_disponible=stock_disponible,
                qte_reception_attendue=qte_reception_attendue,
                date_premiere_reception=date_premiere_reception,
                fournisseurs_concernes=fournisseurs,
                commandes_achat_concernees=commandes_achat,
                niveau_action=niveau_action,
                action_recommandee=ACTION_MESSAGES[niveau_action],
                supplier_refs=supplier_refs,
            )
        )

    lines.sort(
        key=lambda line: (
            -line.nb_commandes_impactees,
            line.date_expedition_la_plus_proche or date.max,
            -line.nb_ofs_impactes,
            -line.missing_qty_total,
            line.article_composant,
        )
    )
    return lines


def _build_supplier_lines(component_lines: List[ComponentActionLine]) -> List[SupplierActionLine]:
    aggregated: Dict[tuple[str, str], dict] = {}

    for line in component_lines:
        pairs = line.supplier_refs
        if not pairs:
            pairs = [(NO_SUPPLIER, NO_PURCHASE_ORDER)]

        for fournisseur, commande_achat in pairs:
            key = (fournisseur or NO_SUPPLIER, commande_achat or NO_PURCHASE_ORDER)
            entry = aggregated.setdefault(
                key,
                {
                    "articles": set(),
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                    "niveaux": [],
                },
            )
            entry["articles"].add(line.article_composant)
            entry["ofs"].update(line.ofs_impactes)
            entry["commandes"].update(line.commandes_impactees)
            if line.date_expedition_la_plus_proche is not None:
                entry["dates"].append(line.date_expedition_la_plus_proche)
            entry["niveaux"].append(line.niveau_action)

    supplier_lines: List[SupplierActionLine] = []
    for (fournisseur, commande_achat), entry in aggregated.items():
        niveau = min(entry["niveaux"], key=lambda n: ACTION_PRIORITY[n])
        supplier_lines.append(
            SupplierActionLine(
                fournisseur=fournisseur,
                num_commande_achat=commande_achat,
                articles_concernes=sorted(entry["articles"]),
                nb_components=len(entry["articles"]),
                nb_ofs_impactes=len(entry["ofs"]),
                nb_commandes_impactees=len(entry["commandes"]),
                date_action_la_plus_urgente=min(entry["dates"]) if entry["dates"] else None,
                action_recommandee=ACTION_MESSAGES[niveau],
            )
        )

    supplier_lines.sort(
        key=lambda line: (
            line.date_action_la_plus_urgente or date.max,
            -line.nb_commandes_impactees,
            line.fournisseur,
            line.num_commande_achat,
        )
    )
    return supplier_lines


def _classify_component_action(
    receptions: List,
    reference_date: date,
    date_expedition_la_plus_proche: Optional[date],
) -> str:
    if not receptions:
        return "AUCUNE_COUVERTURE"

    if any(reception.date_reception_prevue < reference_date for reception in receptions):
        return "RETARD_FOURNISSEUR"

    if (
        date_expedition_la_plus_proche is not None
        and min(reception.date_reception_prevue for reception in receptions) > date_expedition_la_plus_proche
    ):
        return "COUVERTURE_TARDIVE"

    return "SURVEILLANCE"


def _get_article_description(loader: DataLoader, article_code: str) -> Optional[str]:
    article = None

    if hasattr(loader, "get_article"):
        try:
            article = loader.get_article(article_code)
        except Exception:
            article = None

    if article is None and hasattr(loader, "articles"):
        articles = getattr(loader, "articles")
        if isinstance(articles, dict):
            article = articles.get(article_code)

    return getattr(article, "description", None)


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _unique_supplier_refs(receptions: Iterable) -> List[tuple[str, str]]:
    seen = set()
    result = []
    for reception in receptions:
        key = (
            str(reception.code_fournisseur).strip() if reception.code_fournisseur else NO_SUPPLIER,
            str(reception.num_commande).strip() if reception.num_commande else NO_PURCHASE_ORDER,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _format_date(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value else "-"


def _format_reception(line: ComponentActionLine) -> str:
    if line.qte_reception_attendue is None or line.date_premiere_reception is None:
        return "Aucune"
    return (
        f"{line.qte_reception_attendue} le "
        f"{line.date_premiere_reception.strftime('%d/%m/%Y')}"
    )


def _write_lines(output_path: str, lines: List[str]) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
