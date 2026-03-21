"""Rapport S+1 - Validation de la faisabilité des OF pour commandes S+1."""

from typing import List

from rich.console import Console
from rich.table import Table

from ..algorithms.matching import MatchingResult
from ..checkers.base import FeasibilityResult
from ..models.commande_client import CommandeClient


console = Console()


def format_rapport_s1(
    resultats_matching: List[MatchingResult],
    resultats_faisabilite: dict[str, FeasibilityResult],
):
    """Affiche le rapport S+1 complet.

    Parameters
    ----------
    resultats_matching : List[MatchingResult]
        Résultats du matching commande→OF
    resultats_faisabilite : dict[str, FeasibilityResult]
        Résultats de faisabilité indexés par numéro d'OF
    """
    # Tableau principal
    table = Table(title="📋 Validation de la faisabilité des OF - Commandes S+1")

    table.add_column("Commande", style="cyan", no_wrap=True)
    table.add_column("Client", style="magenta")
    table.add_column("Article", style="white")
    table.add_column("Qté Rst", justify="right", style="white")
    table.add_column("Date exp", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Stock dispo", justify="right", style="white")
    table.add_column("Alloué", justify="right", style="green")
    table.add_column("Besoin net", justify="right", style="yellow")
    table.add_column("OF", style="cyan")
    table.add_column("Faisable", justify="center")
    table.add_column("Composants manquants", style="red")

    for resultat in resultats_matching:
        commande = resultat.commande
        of = resultat.of
        alloc = resultat.stock_allocation

        # Formatage de l'allocation
        if commande.is_nor_mto() and alloc:
            stock_dispo = str(alloc.qte_disponible)
            stock_alloue = str(alloc.qte_allouee)
            besoin_net = str(alloc.besoin_net)
        else:
            stock_dispo = "-"
            stock_alloue = "-"
            besoin_net = "-"

        # Récupérer le résultat de faisabilité
        if of:
            faisability = resultats_faisabilite.get(of.num_of)
            if faisability:
                status = "✅" if faisability.feasible else "❌"
                missing = _format_missing(faisability)
            else:
                status = "⏳"
                missing = "Non vérifié"
        else:
            status = "N/A"
            missing = "-"

        # Ajouter la ligne
        table.add_row(
            commande.num_commande,
            commande.nom_client[:15],
            commande.article[:15],
            str(commande.qte_restante),
            commande.date_expedition_demandee.strftime("%d/%m/%Y"),
            "MTS" if commande.is_mts() else "NOR/MTO",
            stock_dispo,
            stock_alloue,
            besoin_net,
            of.num_of if of else "Aucun",
            status,
            missing,
        )

    console.print(table)

    # Afficher les alertes
    _afficher_alertes(resultats_matching)

    # Résumé
    _afficher_resume(resultats_matching, resultats_faisabilite)


def _format_missing(resultat: FeasibilityResult) -> str:
    """Formate les composants manquants."""
    if not resultat.missing_components:
        return "-"
    items = [f"{art}:{qty}" for art, qty in resultat.missing_components.items()]
    return ", ".join(items)[:30]


def _afficher_alertes(resultats: List[MatchingResult]):
    """Affiche les alertes de matching."""
    alertes = []

    for resultat in resultats:
        if resultat.alertes:
            for alerte in resultat.alertes:
                alertes.append(f"⚠️  {resultat.commande.num_commande} - {alerte}")

    if alertes:
        console.print("\n[bold yellow]Alertes de matching:[/bold yellow]")
        for alerte in alertes[:10]:  # Limiter à 10 alertes
            console.print(f"   {alerte}")
        if len(alertes) > 10:
            console.print(f"   ... et {len(alertes) - 10} autres alertes")


def _afficher_resume(
    resultats_matching: List[MatchingResult],
    resultats_faisabilite: dict[str, FeasibilityResult],
):
    """Affiche le résumé des résultats."""
    console.print("\n" + "=" * 80)
    console.print("📊 [bold]RÉSUME S+1[/bold]")
    console.print("=" * 80 + "\n")

    # Statistiques de matching
    total = len(resultats_matching)
    mts = sum(1 for r in resultats_matching if r.commande.is_mts())
    nor_mto = sum(1 for r in resultats_matching if r.commande.is_nor_mto())
    of_trouves = sum(1 for r in resultats_matching if r.of is not None)

    console.print(f"[bold]Commandes S+1:[/bold] {total}")
    console.print(f"   🏭 MTS : {mts}")
    console.print(f"   📦 NOR/MTO : {nor_mto}")
    console.print(f"   ✅ OF trouvés : {of_trouves}/{total} ({of_trouves / total * 100:.1f}%)")

    # Statistiques de faisabilité
    of_verifies = [r.of for r in resultats_matching if r.of is not None]
    if of_verifies and resultats_faisabilite:
        faisables = sum(
            1
            for of in of_verifies
            if of.num_of in resultats_faisabilite and resultats_faisabilite[of.num_of].feasible
        )
        total_verifies = len(of_verifies)
        console.print(f"\n[bold]Faisabilité des OF:[/bold]")
        console.print(f"   ✅ Faisables : {faisables}/{total_verifies} ({faisables / total_verifies * 100:.1f}%)")
        console.print(f"   ❌ Non faisables : {total_verifies - faisables}/{total_verifies}")

    console.print()
