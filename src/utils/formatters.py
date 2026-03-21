"""Formatters - Utilitaires pour le formatage et l'affichage des résultats."""

from typing import Optional

from rich.console import Console
from rich.table import Table

from ..checkers.base import FeasibilityResult
from ..models.of import OF
from ..algorithms.allocation import AllocationResult, AllocationStatus


console = Console()


def format_of_table(
    ofs: list[OF],
    immediate_results: dict[str, FeasibilityResult],
    projected_results: dict[str, FeasibilityResult],
    allocation_results: Optional[dict[str, AllocationResult]] = None,
):
    """Affiche un tableau récapitulatif des OF et de leur faisabilité.

    Parameters
    ----------
    ofs : list[OF]
        Liste des OF à afficher
    immediate_results : dict[str, FeasibilityResult]
        Résultats de vérification immédiate
    projected_results : dict[str, FeasibilityResult]
        Résultats de vérification projetée
    allocation_results : Optional[dict[str, AllocationResult]]
        Résultats d'allocation (optionnel)
    """
    table = Table(title="📋 Résultats de vérification de faisabilité des OF")

    table.add_column("Numéro OF", style="cyan", no_wrap=True)
    table.add_column("Article", style="magenta")
    table.add_column("Qté restante", justify="right", style="white")
    table.add_column("Date fin", style="white")
    table.add_column("Immédiat", justify="center")
    table.add_column("Projeté", justify="center")
    if allocation_results:
        table.add_column("Allocation", justify="center")
    table.add_column("Composants manquants", style="red")

    for of in ofs:
        imm_result = immediate_results.get(of.num_of)
        proj_result = projected_results.get(of.num_of)
        alloc_result = allocation_results.get(of.num_of) if allocation_results else None

        # Statuts
        imm_status = "✅" if imm_result and imm_result.feasible else "❌"
        proj_status = "✅" if proj_result and proj_result.feasible else "❌"
        alloc_status = _format_allocation_status(alloc_result) if alloc_result else "N/A"

        # Composants manquants
        missing = _format_missing_components(proj_result)

        # Ajouter la ligne
        row = [
            of.num_of,
            of.article,
            str(of.qte_restante),
            of.date_fin.strftime("%Y-%m-%d"),
            imm_status,
            proj_status,
        ]
        if allocation_results:
            row.append(alloc_status)
        row.append(missing)

        table.add_row(*row)

    console.print(table)


def format_detailed_report(
    of: OF,
    result: FeasibilityResult,
    show_tree: bool = True,
):
    """Affiche un rapport détaillé pour un OF.

    Parameters
    ----------
    of : OF
        Ordre de fabrication
    result : FeasibilityResult
        Résultat de la vérification
    show_tree : bool
        Si True, affiche l'arbre de nomenclature
    """
    console.print(f"\n{'=' * 80}")
    console.print(f"📦 [bold cyan]OF {of.num_of}[/bold cyan] - {of.description}")
    console.print(f"   Article : [bold magenta]{of.article}[/bold magenta]")
    console.print(f"   Quantité : {of.qte_restante} à fabriquer")
    console.print(f"   Date fin : {of.date_fin.strftime('%Y-%m-%d')}")
    console.print(f"{'=' * 80}\n")

    # Statut
    status = "✅ [bold green]FAISABLE[/bold green]" if result.feasible else "❌ [bold red]NON FAISABLE[/bold red]"
    console.print(f"Statut : {status}")
    console.print(f"Composants vérifiés : {result.components_checked}")
    console.print(f"Profondeur récursion : {result.depth}")

    # Alertes
    if result.alerts:
        console.print("\n⚠️  [bold yellow]Alertes :[/bold yellow]")
        for alert in result.alerts:
            console.print(f"   • {alert}")

    # Composants manquants
    if result.missing_components:
        console.print("\n❌ [bold red]Composants manquants :[/bold red]")
        for article, quantity in result.missing_components.items():
            console.print(f"   • {article} : {quantity} unités")
    else:
        console.print("\n✅ [bold green]Tous les composants sont disponibles[/bold green]")


def format_summary(
    immediate_results: dict[str, FeasibilityResult],
    projected_results: dict[str, FeasibilityResult],
    allocation_results: Optional[dict[str, AllocationResult]] = None,
):
    """Affiche un résumé des résultats.

    Parameters
    ----------
    immediate_results : dict[str, FeasibilityResult]
        Résultats de vérification immédiate
    projected_results : dict[str, FeasibilityResult]
        Résultats de vérification projetée
    allocation_results : Optional[dict[str, AllocationResult]]
        Résultats d'allocation (optionnel)
    """
    console.print("\n" + "=" * 80)
    console.print("📊 [bold]RÉSUME DES RESULTATS[/bold]")
    console.print("=" * 80 + "\n")

    # Vérification immédiate
    imm_feasible = sum(1 for r in immediate_results.values() if r.feasible)
    imm_total = len(immediate_results)
    console.print(f"🔍 [bold]Vérification immédiate (stock actuel)[/bold]")
    console.print(f"   ✅ Faisables : {imm_feasible}/{imm_total} ({imm_feasible / imm_total * 100:.1f}%)")
    console.print(f"   ❌ Non faisables : {imm_total - imm_feasible}/{imm_total}")

    # Vérification projetée
    proj_feasible = sum(1 for r in projected_results.values() if r.feasible)
    proj_total = len(projected_results)
    console.print(f"\n🔮 [bold]Vérification projetée (stock + réceptions)[/bold]")
    console.print(f"   ✅ Faisables : {proj_feasible}/{proj_total} ({proj_feasible / proj_total * 100:.1f}%)")
    console.print(f"   ❌ Non faisables : {proj_total - proj_feasible}/{proj_total}")

    # Allocation
    if allocation_results:
        alloc_feasible = sum(1 for r in allocation_results.values() if r.status == AllocationStatus.FEASIBLE)
        alloc_total = len(allocation_results)
        console.print(f"\n📦 [bold]Allocation avec gestion de la concurrence[/bold]")
        console.print(f"   ✅ Alloués : {alloc_feasible}/{alloc_total} ({alloc_feasible / alloc_total * 100:.1f}%)")
        console.print(f"   ❌ Non alloués : {alloc_total - alloc_feasible}/{alloc_total}")

    console.print()


def _format_allocation_status(result: AllocationResult) -> str:
    """Formate le statut d'allocation.

    Parameters
    ----------
    result : AllocationResult
        Résultat d'allocation

    Returns
    -------
    str
        Statut formaté avec emoji
    """
    if result.status == AllocationStatus.FEASIBLE:
        return "✅"
    elif result.status == AllocationStatus.NOT_FEASIBLE:
        return "❌"
    else:
        return "⏭️"


def _format_missing_components(result: Optional[FeasibilityResult]) -> str:
    """Formate les composants manquants.

    Parameters
    ----------
    result : Optional[FeasibilityResult]
        Résultat de vérification

    Returns
    -------
    str
        Liste des composants manquants formatée
    """
    if not result or not result.missing_components:
        return "-"

    items = [f"{art}:{qty}" for art, qty in result.missing_components.items()]
    return ", ".join(items)
