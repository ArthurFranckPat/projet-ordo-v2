"""Rapport S+1 - Validation de la faisabilite des OF pour commandes S+1."""

from typing import List

from rich.console import Console
from rich.table import Table

from ..algorithms.matching import MatchingResult
from ..checkers.base import FeasibilityResult


console = Console()


def format_rapport_s1(
    resultats_matching: List[MatchingResult],
    resultats_faisabilite: dict[str, FeasibilityResult],
    include_previsions: bool = False,
):
    """Affiche le rapport S+1 complet."""
    titre = "Validation faisabilite OF - "
    if include_previsions:
        titre += "Besoins S+1 (Commandes + Previsions)"
    else:
        titre += "Commandes S+1"

    # Vue compacte pour eviter les colonnes tronquees dans le terminal.
    table = Table(title=titre, padding=(0, 1))

    table.add_column("Cmd", style="cyan", no_wrap=True)
    table.add_column("Client", style="magenta", max_width=12, overflow="fold")
    table.add_column("Article", style="white", no_wrap=True, max_width=12, overflow="ellipsis")
    table.add_column("Qte", justify="right", style="white", width=4)
    table.add_column("Exp", style="white", no_wrap=True, width=10)
    table.add_column("Besoin", style="cyan", no_wrap=True, width=7)
    table.add_column("Couv.", style="white", no_wrap=True, width=11)
    table.add_column("OF", style="cyan", no_wrap=True, max_width=12, overflow="ellipsis")
    table.add_column("OK", justify="center", width=3)
    table.add_column("Manquants", style="red", overflow="fold", max_width=24)

    for resultat in resultats_matching:
        commande = resultat.commande
        of = resultat.of
        alloc = resultat.stock_allocation

        if commande.is_nor_mto() and alloc:
            stock_dispo = str(alloc.qte_disponible)
            stock_alloue = _format_alloue(alloc)
            besoin_net = str(alloc.besoin_net)
        else:
            stock_dispo = "-"
            stock_alloue = "-"
            besoin_net = "-"

        besoin = f"{'CMD' if commande.est_commande() else 'PREV'}\n{'MTS' if commande.is_mts() else 'NOR'}"
        couverture = _format_couverture(stock_dispo, stock_alloue, besoin_net)

        if of:
            faisability = resultats_faisabilite.get(of.num_of)
            if faisability:
                status = "✅" if faisability.feasible else "❌"
                missing = _format_missing(faisability)
            else:
                status = "⏳"
                missing = "Non verifie"
        else:
            status = "N/A"
            missing = "-"

        table.add_row(
            commande.num_commande,
            commande.nom_client,
            commande.article,
            str(commande.qte_restante),
            commande.date_expedition_demandee.strftime("%d/%m/%Y"),
            besoin,
            couverture,
            of.num_of if of else "Aucun",
            status,
            missing,
        )

    console.print(table)
    _afficher_alertes(resultats_matching)
    _afficher_resume(resultats_matching, resultats_faisabilite, include_previews=include_previsions)


def _format_alloue(alloc) -> str:
    """Formate la quantite allouee en texte compact."""
    erp = alloc.qte_allouee_exist
    virt = alloc.qte_allouee

    if erp > 0 and virt > 0:
        return f"{erp}+~{virt}"
    if erp > 0:
        return str(erp)
    if virt > 0:
        return f"~{virt}"
    return "0"


def _format_couverture(stock_dispo: str, stock_alloue: str, besoin_net: str) -> str:
    """Groupe les informations de couverture sur trois lignes compactes."""
    return f"D:{stock_dispo}\nA:{stock_alloue}\nN:{besoin_net}"


def _format_missing(resultat: FeasibilityResult) -> str:
    """Formate les composants manquants sur plusieurs lignes."""
    if not resultat.missing_components:
        return "-"
    items = [f"{art}:{qty}" for art, qty in resultat.missing_components.items()]
    if len(items) <= 3:
        return "\n".join(items)
    return "\n".join(items[:3] + [f"+{len(items) - 3} autres"])


def _afficher_alertes(resultats: List[MatchingResult]):
    """Affiche les alertes de matching."""
    alertes = []

    for resultat in resultats:
        if resultat.alertes:
            for alerte in resultat.alertes:
                alertes.append(f"ATTN {resultat.commande.num_commande} - {alerte}")

    if alertes:
        console.print("\n[bold yellow]Alertes de matching:[/bold yellow]")
        for alerte in alertes[:10]:
            console.print(f"   {alerte}")
        if len(alertes) > 10:
            console.print(f"   ... et {len(alertes) - 10} autres alertes")


def _afficher_resume(
    resultats_matching: List[MatchingResult],
    resultats_faisabilite: dict[str, FeasibilityResult],
    include_previews: bool = False,
):
    """Affiche le resume des resultats."""
    console.print("\n" + "=" * 80)
    console.print("[bold]RESUME S+1[/bold]")
    console.print("=" * 80 + "\n")

    total = len(resultats_matching)
    commandes = sum(1 for r in resultats_matching if r.commande.est_commande())
    previsions = sum(1 for r in resultats_matching if r.commande.est_prevision())
    mts = sum(1 for r in resultats_matching if r.commande.is_mts())
    nor_mto = sum(1 for r in resultats_matching if r.commande.is_nor_mto())
    of_trouves = sum(1 for r in resultats_matching if r.of is not None)

    if include_previews:
        console.print(f"[bold]Besoins S+1:[/bold] {total}")
        console.print(f"   Commandes : {commandes}")
        console.print(f"   Previsions : {previsions}")
    else:
        console.print(f"[bold]Commandes S+1:[/bold] {total}")

    console.print(f"   MTS : {mts}")
    console.print(f"   NOR/MTO : {nor_mto}")
    console.print(f"   OF trouves : {of_trouves}/{total} ({of_trouves / total * 100:.1f}%)")

    of_verifies = [r.of for r in resultats_matching if r.of is not None]
    if of_verifies and resultats_faisabilite:
        faisables = sum(
            1
            for of in of_verifies
            if of.num_of in resultats_faisabilite and resultats_faisabilite[of.num_of].feasible
        )
        total_verifies = len(of_verifies)
        console.print("\n[bold]Faisabilite des OF:[/bold]")
        console.print(f"   ✅ Faisables : {faisables}/{total_verifies} ({faisables / total_verifies * 100:.1f}%)")
        console.print(f"   ❌ Non faisables : {total_verifies - faisables}/{total_verifies}")

    console.print()
