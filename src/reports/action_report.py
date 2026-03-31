"""Rapport d'actions appro sur les ruptures composants du plan S+1."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from rich.console import Console
from rich.table import Table

from ..algorithms.charge_calculator import is_valid_poste
from ..algorithms.matching import MatchingResult
from ..checkers.base import FeasibilityResult
from ..loaders.data_loader import DataLoader
from ..models.nomenclature import NatureConsommation


console = Console()

NO_SUPPLIER = "SANS_FOURNISSEUR"
NO_PURCHASE_ORDER = "APPRO SANS CA OUVERTE"
KANBAN_POSTE_OPEN_HOURS_PER_DAY = 7.0
KANBAN_WAIT_DAYS_PER_HANDOFF = 1.0
KANBAN_AGEING_DAYS = 3.0
KANBAN_DEFAULT_REPLENISHMENT_DAYS = 7.0

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

KANBAN_ACTION_MESSAGES = {
    "ARRET_IMMINENT": "Maintenir prioritairement le poste en production et arbitrer immédiatement les lancements.",
    "TRES_TENDU": "Securiser le sequencement du poste et accelerer les entrees manquantes.",
    "SOUS_SEUIL": "Surveiller et planifier la continuite du poste sur la semaine.",
}

KANBAN_PRIORITY = {
    "ARRET_IMMINENT": 0,
    "TRES_TENDU": 1,
    "SOUS_SEUIL": 2,
}


@dataclass(frozen=True)
class _KanbanReference:
    """Référence métier servant à identifier un article kanban via son successeur direct."""

    type_flux: str
    cadence: float
    ref: str


KANBAN_REFERENCES = [
    _KanbanReference("BDH", 180.0, "MH7623"),
    _KanbanReference("BXC", 90.0, "MH4295"),
    _KanbanReference("EAR", 220.0, "EH4275"),
    _KanbanReference("EAR", 220.0, "EH6243"),
    _KanbanReference("0", 340.0, "EP2360"),
    _KanbanReference("EHM", 133.0, "EH6134"),
    _KanbanReference("BDH", 180.0, "MH7648"),
    _KanbanReference("EHT", 80.0, "MH2918"),
    _KanbanReference("ETH", 130.0, "MH7114"),
    _KanbanReference("EMM", 340.0, "EP4573"),
    _KanbanReference("EMM", 340.0, "EP2925"),
    _KanbanReference("EAR", 220.0, "EH4559"),
    _KanbanReference("BDS", 112.0, "MH6272"),
    _KanbanReference("EAW", 63.0, "EH5466"),
    _KanbanReference("EAR", 220.0, "EH4235"),
    _KanbanReference("EHM", 133.0, "EH6133"),
    _KanbanReference("ETH", 130.0, "MH6830"),
    _KanbanReference("EMM", 340.0, "EP6503"),
    _KanbanReference("EMM", 340.0, "EP2926"),
    _KanbanReference("EHP", 165.0, "EH6050"),
    _KanbanReference("BDH", 180.0, "MH7649"),
    _KanbanReference("BHM", 109.0, "MH4648"),
    _KanbanReference("EHM", 133.0, "EH6882"),
    _KanbanReference("ETH", 135.0, "MH6833"),
    _KanbanReference("BDH", 180.0, "MH7650"),
    _KanbanReference("BDC", 94.0, "MH6264"),
    _KanbanReference("BDS", 112.0, "MH4721"),
    _KanbanReference("EHP", 165.0, "EH5852"),
    _KanbanReference("BHM", 109.0, "MH0705"),
    _KanbanReference("BDS", 112.0, "MH6270"),
]


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
    stock_sous_controle: int
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
class PosteChargeRiskLine:
    """Vue poste de charge potentiellement à l'arrêt."""

    poste: str
    libelle: str
    charge_risquee_heures: float
    nb_ofs_impactes: int
    ofs_impactes: List[str]
    composants_bloquants: List[str]
    nb_commandes_impactees: int
    date_echeance_la_plus_proche: Optional[date]


@dataclass
class PosteKanbanRiskLine:
    """Vue poste fournisseur à maintenir en marche pour alimenter le kanban."""

    poste_fournisseur: str
    libelle_poste_fournisseur: str
    postes_consommateurs: List[str]
    articles_kanban_concernes: List[str]
    refs_kanban_sources: List[str]
    stock_equivalent_jours: float
    seuil_couverture_jours: float
    jours_manquants: float
    nb_ofs_s1_impactes: int
    nb_commandes_s1_impactees: int
    date_echeance_la_plus_proche: Optional[date]
    action_recommandee: str
    niveau_risque: str


@dataclass
class _KanbanComponentLine:
    """Détail interne par article kanban sous seuil."""

    article_kanban: str
    refs_kanban_sources: List[str]
    types_kanban_sources: List[str]
    articles_plan_concernes: List[str]
    postes_fournisseurs: List[str]
    postes_consommateurs: List[str]
    stock_equivalent_jours: float
    seuil_couverture_jours: float
    jours_manquants: float
    nb_ofs_s1_impactes: int
    ofs_s1_impactes: List[str]
    nb_commandes_s1_impactees: int
    commandes_s1_impactees: List[str]
    date_echeance_la_plus_proche: Optional[date]
    action_recommandee: str
    niveau_risque: str
    libelles_postes_fournisseurs: Dict[str, str] = field(default_factory=dict, repr=False)
    seuils_par_poste_fournisseur: Dict[str, float] = field(default_factory=dict, repr=False)


@dataclass
class ActionReport:
    """Rapport d'actions appro pour le plan S+1."""

    reference_date: date
    component_lines: List[ComponentActionLine] = field(default_factory=list)
    supplier_lines: List[SupplierActionLine] = field(default_factory=list)
    poste_charge_lines: List[PosteChargeRiskLine] = field(default_factory=list)
    poste_kanban_lines: List[PosteKanbanRiskLine] = field(default_factory=list)
    kanban_component_lines: List[_KanbanComponentLine] = field(default_factory=list, repr=False)
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
    poste_charge_lines = _build_poste_charge_lines(loader, of_contexts)
    kanban_component_lines = _build_kanban_component_lines(
        loader,
        resultats_matching,
        reference_date,
    )
    poste_kanban_lines = _build_poste_kanban_lines(kanban_component_lines)

    impacted_ofs = len(
        {
            of_num
            for line in component_lines
            for of_num in line.ofs_impactes
        }
        | {
            of_num
            for line in kanban_component_lines
            for of_num in line.ofs_s1_impactes
        }
    )
    impacted_commandes = len(
        {
            commande
            for line in component_lines
            for commande in line.commandes_impactees
        }
        | {
            commande
            for line in kanban_component_lines
            for commande in line.commandes_s1_impactees
        }
    )

    return ActionReport(
        reference_date=reference_date,
        component_lines=component_lines,
        supplier_lines=supplier_lines,
        poste_charge_lines=poste_charge_lines,
        poste_kanban_lines=poste_kanban_lines,
        kanban_component_lines=kanban_component_lines,
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

    if not _report_has_content(report):
        console.print("[green]Aucune alerte composant ou kanban détectée sur le plan S+1.[/green]")
        console.print()
        return

    console.print(
        f"[bold]Composants critiques :[/bold] {len(report.component_lines)}"
        f" | Articles kanban sous seuil : {len(report.kanban_component_lines)}"
        f" | OF impactés : {report.impacted_ofs}"
        f" | Commandes impactées : {report.impacted_commandes}"
    )

    if report.component_lines:
        table = Table(title="Vue composant", show_lines=False)
        table.add_column("Composant", style="cyan", no_wrap=True)
        table.add_column("Manque", justify="right")
        table.add_column("Cmd", justify="right")
        table.add_column("OF", justify="right")
        table.add_column("Besoin OF", style="white")
        table.add_column("Réception", style="white")
        table.add_column("CQ", justify="right")
        table.add_column("Action", style="yellow")

        for line in report.component_lines:
            table.add_row(
                line.article_composant,
                str(line.missing_qty_total),
                str(line.nb_commandes_impactees),
                str(line.nb_ofs_impactes),
                _format_date(line.date_expedition_la_plus_proche),
                _format_reception(line),
                str(line.stock_sous_controle),
                line.action_recommandee,
            )

        console.print(table)
    else:
        console.print("[green]Aucun composant bloquant détecté sur le plan S+1.[/green]")

    if report.poste_charge_lines:
        poste_table = Table(title="Vue poste de charge à risque", show_lines=False)
        poste_table.add_column("Poste", style="cyan")
        poste_table.add_column("Libellé", style="white")
        poste_table.add_column("Heures à risque", justify="right")
        poste_table.add_column("Cmd", justify="right")
        poste_table.add_column("OF", justify="right")
        poste_table.add_column("Échéance", style="white")
        poste_table.add_column("Composants", style="yellow")

        for line in report.poste_charge_lines:
            poste_table.add_row(
                line.poste,
                line.libelle,
                f"{line.charge_risquee_heures:.1f}h",
                str(line.nb_commandes_impactees),
                str(line.nb_ofs_impactes),
                _format_date(line.date_echeance_la_plus_proche),
                ", ".join(line.composants_bloquants[:3]),
            )

        console.print(poste_table)

    if report.poste_kanban_lines:
        kanban_table = Table(title="Vue poste fournisseur / couverture kanban", show_lines=False)
        kanban_table.add_column("Poste", style="cyan")
        kanban_table.add_column("Kanban", style="white")
        kanban_table.add_column("Postes aval", style="white")
        kanban_table.add_column("Couverture", justify="right")
        kanban_table.add_column("Seuil", justify="right")
        kanban_table.add_column("Cmd", justify="right")
        kanban_table.add_column("Échéance", style="white")
        kanban_table.add_column("Action", style="yellow")

        for line in report.poste_kanban_lines:
            kanban_table.add_row(
                line.poste_fournisseur,
                ", ".join(line.articles_kanban_concernes[:3]),
                ", ".join(line.postes_consommateurs[:3]),
                f"{line.stock_equivalent_jours:.1f}j",
                f"{line.seuil_couverture_jours:.1f}j",
                str(line.nb_commandes_s1_impactees),
                _format_date(line.date_echeance_la_plus_proche),
                line.action_recommandee,
            )

        console.print(kanban_table)
    else:
        console.print("[green]Aucun poste fournisseur sous seuil kanban sur le plan S+1.[/green]")

    if report.supplier_lines:
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
        f"- Postes fournisseurs sous seuil kanban : {len(report.poste_kanban_lines)}",
        f"- Articles kanban sous seuil : {len(report.kanban_component_lines)}",
        f"- OF impactés : {report.impacted_ofs}",
        f"- Commandes impactées : {report.impacted_commandes}",
        f"- Composants sans couverture identifiée : {len(report.components_without_coverage)}",
        "",
    ]

    if not _report_has_content(report):
        lines.extend(
            [
                "Aucune alerte composant ou kanban détectée sur le plan S+1.",
                "",
                "## Composants critiques",
                "",
                "Aucun composant bloquant détecté sur le plan S+1.",
                "",
                "## Postes de charge à risque d'arrêt",
                "",
                "Aucun.",
                "",
                "## Postes fournisseurs à maintenir en marche",
                "",
                "Aucun.",
                "",
                "## Articles kanban sous seuil",
                "",
                "Aucun.",
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
    if report.component_lines:
        for line in report.component_lines:
            lines.extend(
                [
                    f"### {line.article_composant} — {line.niveau_action}",
                    "",
                    f"- Description : {line.description or 'N/A'}",
                    f"- Quantité manquante totale : {line.missing_qty_total}",
                    f"- Stock disponible : {line.stock_disponible}",
                    f"- Stock sous contrôle qualité : {line.stock_sous_controle}",
                    f"- Commandes impactées ({line.nb_commandes_impactees}) : "
                    f"{', '.join(line.commandes_impactees) if line.commandes_impactees else 'Aucune'}",
                    f"- OF impactés ({line.nb_ofs_impactes}) : "
                    f"{', '.join(line.ofs_impactes) if line.ofs_impactes else 'Aucun'}",
                    f"- Première date de besoin OF : {_format_date(line.date_expedition_la_plus_proche)}",
                    f"- Réceptions ouvertes : {_format_reception(line)}",
                    f"- Fournisseurs concernés : "
                    f"{', '.join(line.fournisseurs_concernes) if line.fournisseurs_concernes else 'Aucun'}",
                    f"- Commandes achat concernées : "
                    f"{', '.join(line.commandes_achat_concernees) if line.commandes_achat_concernees else NO_PURCHASE_ORDER}",
                    f"- Action recommandée : {line.action_recommandee}",
                    "",
                ]
            )
    else:
        lines.extend(["Aucun composant bloquant détecté sur le plan S+1.", ""])

    lines.extend(["## Postes de charge à risque d'arrêt", ""])
    if report.poste_charge_lines:
        for line in report.poste_charge_lines:
            lines.extend(
                [
                    f"### {line.poste} — {line.libelle}",
                    "",
                    f"- Heures à risque : {line.charge_risquee_heures:.1f}h",
                    f"- Commandes impactées : {line.nb_commandes_impactees}",
                    f"- OF impactés ({line.nb_ofs_impactes}) : {', '.join(line.ofs_impactes)}",
                    f"- Première échéance : {_format_date(line.date_echeance_la_plus_proche)}",
                    f"- Composants bloquants : {', '.join(line.composants_bloquants)}",
                    "",
                ]
            )
    else:
        lines.extend(["Aucun.", ""])

    lines.extend(["## Postes fournisseurs à maintenir en marche", ""])
    if report.poste_kanban_lines:
        for line in report.poste_kanban_lines:
            lines.extend(
                [
                    f"### {line.poste_fournisseur} — {line.niveau_risque}",
                    "",
                    f"- Libellé poste : {line.libelle_poste_fournisseur or 'N/A'}",
                    f"- Couverture estimée : {line.stock_equivalent_jours:.1f} jours",
                    f"- Seuil de couverture : {line.seuil_couverture_jours:.1f} jours",
                    f"- Jours manquants : {line.jours_manquants:.1f}",
                    f"- Articles kanban concernés : {', '.join(line.articles_kanban_concernes)}",
                    f"- Références sources : {', '.join(line.refs_kanban_sources)}",
                    f"- Postes consommateurs : {', '.join(line.postes_consommateurs)}",
                    f"- Commandes S+1 impactées : {line.nb_commandes_s1_impactees}",
                    f"- OF S+1 impactés : {line.nb_ofs_s1_impactes}",
                    f"- Première échéance : {_format_date(line.date_echeance_la_plus_proche)}",
                    f"- Action recommandée : {line.action_recommandee}",
                    "",
                ]
            )
    else:
        lines.extend(["Aucun.", ""])

    lines.extend(["## Articles kanban sous seuil", ""])
    if report.kanban_component_lines:
        for line in report.kanban_component_lines:
            lines.extend(
                [
                    f"### {line.article_kanban} — {line.niveau_risque}",
                    "",
                    f"- Références sources : {', '.join(line.refs_kanban_sources)}",
                    f"- Types flux : {', '.join(line.types_kanban_sources) if line.types_kanban_sources else 'N/A'}",
                    f"- Articles du plan concernés : {', '.join(line.articles_plan_concernes)}",
                    f"- Couverture estimée : {line.stock_equivalent_jours:.1f} jours",
                    f"- Seuil de couverture : {line.seuil_couverture_jours:.1f} jours",
                    f"- Jours manquants : {line.jours_manquants:.1f}",
                    f"- Postes fournisseurs : {', '.join(line.postes_fournisseurs)}",
                    f"- Postes consommateurs : {', '.join(line.postes_consommateurs)}",
                    f"- Commandes S+1 impactées ({line.nb_commandes_s1_impactees}) : "
                    f"{', '.join(line.commandes_s1_impactees)}",
                    f"- OF S+1 impactés ({line.nb_ofs_s1_impactes}) : {', '.join(line.ofs_s1_impactes)}",
                    f"- Première échéance : {_format_date(line.date_echeance_la_plus_proche)}",
                    f"- Action recommandée : {line.action_recommandee}",
                    "",
                ]
            )
    else:
        lines.extend(["Aucun.", ""])

    lines.extend(["## Actions appro par fournisseur / CA", ""])
    if report.supplier_lines:
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
    else:
        lines.extend(["Aucune action requise.", ""])

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

        date_besoin_of = _get_component_need_date(of, commandes)

        for article_composant, quantity in feasibility.missing_components.items():
            entry = aggregated.setdefault(
                article_composant,
                {
                    "missing_qty_total": 0,
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                },
            )
            entry["missing_qty_total"] += int(quantity)
            entry["ofs"].add(of_num)
            if date_besoin_of is not None:
                entry["dates"].append(date_besoin_of)

            for commande in commandes:
                entry["commandes"].add(commande.num_commande)

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
        stock_sous_controle = getattr(stock, "stock_sous_controle", 0) if stock else 0
        qte_reception_attendue = sum(r.quantite_restante for r in receptions) or None
        date_premiere_reception = receptions[0].date_reception_prevue if receptions else None

        commandes_achat = _unique_preserve_order(r.num_commande for r in receptions if r.num_commande)
        fournisseurs = _unique_preserve_order(
            r.code_fournisseur for r in receptions if r.code_fournisseur
        )
        supplier_refs = _unique_supplier_refs(receptions)
        date_expedition = min(entry["dates"]) if entry["dates"] else None
        niveau_action = _classify_component_action(receptions, reference_date, date_expedition)
        description = _get_article_description(loader, article_composant)
        action_recommandee = _build_component_action_message(
            niveau_action=niveau_action,
            stock_sous_controle=stock_sous_controle,
            missing_qty_total=entry["missing_qty_total"],
        )

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
                stock_sous_controle=stock_sous_controle,
                qte_reception_attendue=qte_reception_attendue,
                date_premiere_reception=date_premiere_reception,
                fournisseurs_concernes=fournisseurs,
                commandes_achat_concernees=commandes_achat,
                niveau_action=niveau_action,
                action_recommandee=action_recommandee,
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


def _build_poste_charge_lines(
    loader: DataLoader,
    of_contexts: Dict[str, dict],
) -> List[PosteChargeRiskLine]:
    aggregated: Dict[str, dict] = {}

    for context in of_contexts.values():
        of = context["of"]
        gamme = loader.get_gamme(of.article)
        if not gamme:
            continue

        commandes = context["commandes"]
        composants_bloquants = sorted(context["feasibility"].missing_components.keys())
        date_echeance = min(
            (commande.date_expedition_demandee for commande in commandes),
            default=of.date_fin,
        )

        for op in gamme.operations:
            if not is_valid_poste(op.poste_charge) or op.cadence <= 0:
                continue

            entry = aggregated.setdefault(
                op.poste_charge,
                {
                    "libelle": op.libelle_poste,
                    "charge": 0.0,
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                    "composants": set(),
                },
            )
            entry["charge"] += of.qte_restante / op.cadence
            entry["ofs"].add(of.num_of)
            entry["composants"].update(composants_bloquants)
            entry["dates"].append(date_echeance)
            for commande in commandes:
                entry["commandes"].add(commande.num_commande)

    lines: List[PosteChargeRiskLine] = []
    for poste, entry in aggregated.items():
        lines.append(
            PosteChargeRiskLine(
                poste=poste,
                libelle=entry["libelle"],
                charge_risquee_heures=round(entry["charge"], 2),
                nb_ofs_impactes=len(entry["ofs"]),
                ofs_impactes=sorted(entry["ofs"]),
                composants_bloquants=sorted(entry["composants"]),
                nb_commandes_impactees=len(entry["commandes"]),
                date_echeance_la_plus_proche=min(entry["dates"]) if entry["dates"] else None,
            )
        )

    lines.sort(
        key=lambda line: (
            line.date_echeance_la_plus_proche or date.max,
            -line.nb_commandes_impactees,
            -line.charge_risquee_heures,
            line.poste,
        )
    )
    return lines


def _build_kanban_component_lines(
    loader: DataLoader,
    resultats_matching: Iterable[MatchingResult],
    reference_date: date,
) -> List[_KanbanComponentLine]:
    kanban_successors = _resolve_kanban_successors(loader)
    if not kanban_successors:
        return []

    aggregated: Dict[str, dict] = {}

    for match in resultats_matching:
        if match.of is None:
            continue

        article_plan = match.of.article or match.commande.article
        qte_plan = _get_parent_quantity(match)
        if not article_plan or qte_plan <= 0:
            continue

        kanban_needs = _collect_kanban_needs(
            loader,
            article_plan,
            qte_plan,
            set(kanban_successors),
        )
        if not kanban_needs:
            continue

        date_echeance = match.commande.date_expedition_demandee or match.of.date_fin
        for article_kanban, qte_kanban in kanban_needs:
            metadata = kanban_successors[article_kanban]
            entry = aggregated.setdefault(
                article_kanban,
                {
                    "needed_qty": 0,
                    "refs": set(),
                    "types": set(),
                    "articles_plan": set(),
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                },
            )
            entry["needed_qty"] += qte_kanban
            entry["refs"].update(metadata["refs"])
            entry["types"].update(metadata["types"])
            entry["articles_plan"].add(article_plan)
            entry["ofs"].add(match.of.num_of)
            entry["commandes"].add(match.commande.num_commande)
            entry["dates"].append(date_echeance)

    lines: List[_KanbanComponentLine] = []
    for article_kanban, entry in aggregated.items():
        if entry["needed_qty"] <= 0:
            continue

        postes_consommateurs_info = _get_valid_poste_info(loader.get_gamme(article_kanban))
        postes_fournisseurs_info = _collect_fabricated_poste_info(loader, article_kanban)
        if not postes_consommateurs_info or not postes_fournisseurs_info:
            continue

        consumer_daily_capacity = _get_consumer_daily_capacity(postes_consommateurs_info)
        if consumer_daily_capacity <= 0:
            continue

        date_echeance = min(entry["dates"]) if entry["dates"] else reference_date
        available_qty = _get_available_supply(loader, article_kanban, date_echeance)
        stock_equivalent_jours = available_qty / consumer_daily_capacity
        seuils_par_poste = _compute_supplier_thresholds(
            postes_consommateurs_info,
            postes_fournisseurs_info,
            _get_upstream_depth(loader, article_kanban),
        )
        seuil_couverture = max(seuils_par_poste.values(), default=KANBAN_DEFAULT_REPLENISHMENT_DAYS)
        if stock_equivalent_jours >= seuil_couverture:
            continue

        niveau_risque = _classify_kanban_risk(stock_equivalent_jours)
        lines.append(
            _KanbanComponentLine(
                article_kanban=article_kanban,
                refs_kanban_sources=sorted(entry["refs"]),
                types_kanban_sources=sorted(entry["types"]),
                articles_plan_concernes=sorted(entry["articles_plan"]),
                postes_fournisseurs=sorted(postes_fournisseurs_info),
                postes_consommateurs=sorted(postes_consommateurs_info),
                stock_equivalent_jours=round(stock_equivalent_jours, 2),
                seuil_couverture_jours=round(seuil_couverture, 2),
                jours_manquants=round(
                    max(seuil_couverture - stock_equivalent_jours, 0.0), 2
                ),
                nb_ofs_s1_impactes=len(entry["ofs"]),
                ofs_s1_impactes=sorted(entry["ofs"]),
                nb_commandes_s1_impactees=len(entry["commandes"]),
                commandes_s1_impactees=sorted(entry["commandes"]),
                date_echeance_la_plus_proche=date_echeance,
                action_recommandee=KANBAN_ACTION_MESSAGES[niveau_risque],
                niveau_risque=niveau_risque,
                libelles_postes_fournisseurs={
                    poste: info["label"] for poste, info in postes_fournisseurs_info.items()
                },
                seuils_par_poste_fournisseur=seuils_par_poste,
            )
        )

    lines.sort(
        key=lambda line: (
            KANBAN_PRIORITY[line.niveau_risque],
            -line.nb_commandes_s1_impactees,
            line.date_echeance_la_plus_proche or date.max,
            -line.jours_manquants,
            line.article_kanban,
        )
    )
    return lines


def _build_poste_kanban_lines(
    kanban_component_lines: List[_KanbanComponentLine],
) -> List[PosteKanbanRiskLine]:
    aggregated: Dict[str, dict] = {}

    for line in kanban_component_lines:
        for poste_fournisseur in line.postes_fournisseurs:
            entry = aggregated.setdefault(
                poste_fournisseur,
                {
                    "libelle": line.libelles_postes_fournisseurs.get(poste_fournisseur, ""),
                    "postes_consommateurs": set(),
                    "articles_kanban": set(),
                    "refs": set(),
                    "stock_days": [],
                    "thresholds": [],
                    "jours_manquants": [],
                    "ofs": set(),
                    "commandes": set(),
                    "dates": [],
                    "niveaux": [],
                },
            )
            if not entry["libelle"]:
                entry["libelle"] = line.libelles_postes_fournisseurs.get(poste_fournisseur, "")
            entry["postes_consommateurs"].update(line.postes_consommateurs)
            entry["articles_kanban"].add(line.article_kanban)
            entry["refs"].update(line.refs_kanban_sources)
            entry["stock_days"].append(line.stock_equivalent_jours)
            seuil_poste = line.seuils_par_poste_fournisseur.get(
                poste_fournisseur,
                line.seuil_couverture_jours,
            )
            entry["thresholds"].append(seuil_poste)
            entry["jours_manquants"].append(
                max(seuil_poste - line.stock_equivalent_jours, 0.0)
            )
            entry["ofs"].update(line.ofs_s1_impactes)
            entry["commandes"].update(line.commandes_s1_impactees)
            if line.date_echeance_la_plus_proche is not None:
                entry["dates"].append(line.date_echeance_la_plus_proche)
            entry["niveaux"].append(line.niveau_risque)

    poste_lines: List[PosteKanbanRiskLine] = []
    for poste_fournisseur, entry in aggregated.items():
        niveau_risque = min(entry["niveaux"], key=lambda niveau: KANBAN_PRIORITY[niveau])
        poste_lines.append(
            PosteKanbanRiskLine(
                poste_fournisseur=poste_fournisseur,
                libelle_poste_fournisseur=entry["libelle"],
                postes_consommateurs=sorted(entry["postes_consommateurs"]),
                articles_kanban_concernes=sorted(entry["articles_kanban"]),
                refs_kanban_sources=sorted(entry["refs"]),
                stock_equivalent_jours=round(min(entry["stock_days"]), 2),
                seuil_couverture_jours=round(max(entry["thresholds"]), 2),
                jours_manquants=round(max(entry["jours_manquants"]), 2),
                nb_ofs_s1_impactes=len(entry["ofs"]),
                nb_commandes_s1_impactees=len(entry["commandes"]),
                date_echeance_la_plus_proche=min(entry["dates"]) if entry["dates"] else None,
                action_recommandee=KANBAN_ACTION_MESSAGES[niveau_risque],
                niveau_risque=niveau_risque,
            )
        )

    poste_lines.sort(
        key=lambda line: (
            KANBAN_PRIORITY[line.niveau_risque],
            -line.nb_commandes_s1_impactees,
            line.date_echeance_la_plus_proche or date.max,
            -line.jours_manquants,
            line.poste_fournisseur,
        )
    )
    return poste_lines


def _resolve_kanban_successors(loader: DataLoader) -> Dict[str, dict]:
    """Résout les successeurs directs des références métier kanban."""
    ref_map = {}
    for reference in KANBAN_REFERENCES:
        ref_map.setdefault(reference.ref, reference)

    successors: Dict[str, dict] = {}
    for article_parent, nomenclature in loader.nomenclatures.items():
        for composant in nomenclature.composants:
            reference = ref_map.get(composant.article_composant)
            if reference is None:
                continue

            entry = successors.setdefault(
                article_parent,
                {
                    "refs": set(),
                    "types": set(),
                },
            )
            entry["refs"].add(reference.ref)
            if reference.type_flux and reference.type_flux != "0":
                entry["types"].add(reference.type_flux)

    return successors


def _collect_kanban_needs(
    loader: DataLoader,
    article_parent: str,
    quantity: int,
    kanban_articles: set[str],
    visited: Optional[set[str]] = None,
) -> List[tuple[str, int]]:
    """Descend récursivement la nomenclature pour retrouver les articles kanban requis."""
    if visited is None:
        visited = set()
    if article_parent in visited:
        return []

    visited = visited | {article_parent}
    nomenclature = loader.get_nomenclature(article_parent)
    if nomenclature is None:
        return []

    demands: List[tuple[str, int]] = []
    for composant in nomenclature.composants:
        if not composant.is_fabrique():
            continue

        child_article = composant.article_composant
        child_quantity = _compute_component_need(composant, quantity)
        if child_quantity <= 0:
            continue

        if child_article in kanban_articles:
            demands.append((child_article, child_quantity))

        demands.extend(
            _collect_kanban_needs(
                loader,
                child_article,
                child_quantity,
                kanban_articles,
                visited,
            )
        )

    return demands


def _collect_fabricated_poste_labels(
    loader: DataLoader,
    article: str,
    visited: Optional[set[str]] = None,
) -> Dict[str, str]:
    """Collecte récursivement les postes valides de l'article et de ses composants fabriqués."""
    if visited is None:
        visited = set()
    if article in visited:
        return {}

    visited = visited | {article}
    postes = {
        poste: info["label"]
        for poste, info in _get_valid_poste_info(loader.get_gamme(article)).items()
    }

    nomenclature = loader.get_nomenclature(article)
    if nomenclature is None:
        return postes

    for composant in nomenclature.composants:
        if not composant.is_fabrique():
            continue
        postes.update(
            _collect_fabricated_poste_labels(
                loader,
                composant.article_composant,
                visited,
            )
        )

    return postes


def _collect_fabricated_poste_info(
    loader: DataLoader,
    article: str,
    visited: Optional[set[str]] = None,
) -> Dict[str, dict]:
    """Collecte récursivement les postes valides et leurs cadences sur la chaîne amont."""
    if visited is None:
        visited = set()
    if article in visited:
        return {}

    visited = visited | {article}
    postes = dict(_get_valid_poste_info(loader.get_gamme(article)))

    nomenclature = loader.get_nomenclature(article)
    if nomenclature is None:
        return postes

    for composant in nomenclature.composants:
        if not composant.is_fabrique():
            continue
        for poste, info in _collect_fabricated_poste_info(
            loader,
            composant.article_composant,
            visited,
        ).items():
            existing = postes.get(poste)
            if existing is None or (
                existing["cadence"] <= 0 < info["cadence"]
                or info["cadence"] > existing["cadence"]
            ):
                postes[poste] = info

    return postes


def _get_upstream_depth(
    loader: DataLoader,
    article: str,
    visited: Optional[set[str]] = None,
) -> int:
    """Retourne la profondeur max de composants fabriqués sous l'article."""
    if visited is None:
        visited = set()
    if article in visited:
        return 0

    visited = visited | {article}
    nomenclature = loader.get_nomenclature(article)
    if nomenclature is None:
        return 0

    child_depths = []
    for composant in nomenclature.composants:
        if not composant.is_fabrique():
            continue
        child_depths.append(
            1 + _get_upstream_depth(loader, composant.article_composant, visited)
        )

    return max(child_depths, default=0)


def _compute_supplier_thresholds(
    postes_consommateurs_info: Dict[str, dict],
    postes_fournisseurs_info: Dict[str, dict],
    upstream_depth: int,
) -> Dict[str, float]:
    """Calcule un seuil de couverture par poste fournisseur à partir des cadences."""
    max_consumer_cadence = _get_max_consumer_cadence(postes_consommateurs_info)
    if max_consumer_cadence <= 0:
        return {}
    base_lead_time = KANBAN_AGEING_DAYS + (
        max(upstream_depth, 1) * KANBAN_WAIT_DAYS_PER_HANDOFF
    )

    thresholds: Dict[str, float] = {}
    for poste, info in postes_fournisseurs_info.items():
        supplier_cadence = float(info["cadence"])
        if supplier_cadence <= 0:
            thresholds[poste] = KANBAN_DEFAULT_REPLENISHMENT_DAYS
            continue

        thresholds[poste] = base_lead_time + (max_consumer_cadence / supplier_cadence)

    return thresholds


def _get_max_consumer_cadence(postes_consommateurs_info: Dict[str, dict]) -> float:
    cadences = [
        float(info["cadence"])
        for info in postes_consommateurs_info.values()
        if float(info["cadence"]) > 0
    ]
    return max(cadences, default=0.0)


def _get_consumer_daily_capacity(postes_consommateurs_info: Dict[str, dict]) -> float:
    max_consumer_cadence = _get_max_consumer_cadence(postes_consommateurs_info)
    if max_consumer_cadence <= 0:
        return 0.0
    return max_consumer_cadence * KANBAN_POSTE_OPEN_HOURS_PER_DAY


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


def _build_component_action_message(
    niveau_action: str,
    stock_sous_controle: int,
    missing_qty_total: int,
) -> str:
    """Compose la recommandation d'action composant avec focus contrôle qualité."""
    base_message = ACTION_MESSAGES[niveau_action]
    if stock_sous_controle <= 0:
        return base_message

    qc_message = (
        f"Accelerer le controle qualite du stock bloque ({stock_sous_controle} u)"
    )
    if stock_sous_controle >= missing_qty_total > 0:
        return f"{qc_message} pour couvrir le besoin prioritaire. {base_message}"
    return f"{qc_message}, puis completer l'appro si necessaire. {base_message}"


def _classify_kanban_risk(stock_equivalent_jours: float) -> str:
    if stock_equivalent_jours <= 0:
        return "ARRET_IMMINENT"
    if stock_equivalent_jours < 2:
        return "TRES_TENDU"
    return "SOUS_SEUIL"


def _get_component_need_date(of, commandes: Optional[Iterable] = None) -> Optional[date]:
    """Date à laquelle le composant doit être disponible pour l'OF."""
    if getattr(of, "date_debut", None) is not None:
        return of.date_debut
    if commandes:
        dates_commandes = [
            commande.date_expedition_demandee
            for commande in commandes
            if getattr(commande, "date_expedition_demandee", None) is not None
        ]
        if dates_commandes:
            return min(dates_commandes)
    if getattr(of, "date_fin", None) is not None:
        return of.date_fin
    return None


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


def _get_parent_quantity(match: MatchingResult) -> int:
    for quantity in (
        getattr(match.commande, "qte_restante", 0),
        getattr(match.commande, "qte_commandee", 0),
        getattr(match.of, "qte_restante", 0) if match.of else 0,
    ):
        if quantity:
            return int(quantity)
    return 0


def _compute_component_need(composant, qte_parent: int) -> int:
    if getattr(composant, "nature_consommation", None) == NatureConsommation.FORFAIT:
        return max(int(composant.qte_lien), 1) if composant.qte_lien else 1
    return int(composant.qte_lien * qte_parent)


def _get_available_supply(
    loader: DataLoader,
    article: str,
    date_echeance: date,
) -> int:
    stock = loader.get_stock(article)
    stock_disponible = stock.disponible() if stock else 0

    receptions_qty = sum(
        reception.quantite_restante
        for reception in loader.get_receptions(article)
        if reception.quantite_restante > 0 and reception.date_reception_prevue <= date_echeance
    )

    ofs_qty = sum(
        of.qte_restante
        for of in _get_ofs_by_article(loader, article)
        if of.qte_restante > 0 and of.date_fin <= date_echeance
    )

    return stock_disponible + receptions_qty + ofs_qty


def _get_ofs_by_article(loader: DataLoader, article: str) -> List:
    if hasattr(loader, "get_ofs_by_article"):
        try:
            ofs = loader.get_ofs_by_article(article)
            if isinstance(ofs, list):
                return ofs
        except Exception:
            pass

    if hasattr(loader, "ofs"):
        try:
            return [
                of
                for of in getattr(loader, "ofs")
                if getattr(of, "article", None) == article and getattr(of, "qte_restante", 0) > 0
            ]
        except Exception:
            return []

    return []


def _get_valid_poste_info(gamme) -> Dict[str, dict]:
    if gamme is None or not hasattr(gamme, "operations"):
        return {}

    postes: Dict[str, dict] = {}
    for op in gamme.operations:
        poste = str(getattr(op, "poste_charge", "") or "").strip()
        if not poste or not is_valid_poste(poste):
            continue

        label = str(getattr(op, "libelle_poste", "") or "").strip()
        cadence = float(getattr(op, "cadence", 0.0) or 0.0)
        existing = postes.get(poste)
        if existing is None or (
            existing["cadence"] <= 0 < cadence
            or cadence > existing["cadence"]
        ):
            postes[poste] = {
                "label": label,
                "cadence": cadence,
            }

    return postes


def _get_valid_poste_labels(gamme) -> Dict[str, str]:
    return {
        poste: info["label"]
        for poste, info in _get_valid_poste_info(gamme).items()
    }


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


def _report_has_content(report: ActionReport) -> bool:
    return any(
        [
            report.component_lines,
            report.poste_charge_lines,
            report.poste_kanban_lines,
            report.supplier_lines,
        ]
    )


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
