"""Fonction main_s1 pour le mode S+1."""

from datetime import date

from rich.console import Console

from .checkers import ProjectedChecker
from .algorithms import CommandeOFMatcher
from .reports import format_rapport_s1


def main_s1(args, loader):
    """Fonction principale pour le mode S+1.

    Parameters
    ----------
    args
        Arguments de ligne de commande
    loader : DataLoader
        Loader de données
    """
    from rich.console import Console

    console = Console()
    horizon = args.horizon
    date_ref = date.today()

    console.print(f"[bold cyan]🎯 MODE S+1 : Commandes des {horizon} prochains jours[/bold cyan]")
    console.print(f"   Date de référence : {date_ref.strftime('%d/%m/%Y')}")
    console.print()

    # 1. Récupérer les commandes de S+1
    console.print(f"[bold cyan]📋 Recherche des commandes S+1...[/bold cyan]")
    commandes_s1 = loader.get_commandes_s1(date_ref, horizon)

    if not commandes_s1:
        console.print("[yellow]⚠️  Aucune commande trouvée pour l'horizon S+1[/yellow]")
        return

    console.print(f"✅ {len(commandes_s1)} commandes trouvées")
    console.print()

    # 2. Matcher les commandes avec les OF
    console.print(f"[bold cyan]🔗 Matching commande→OF...[/bold cyan]")
    matcher = CommandeOFMatcher(loader, date_tolerance_days=10)
    resultats_matching = matcher.match_commandes(commandes_s1)

    of_trouves = sum(1 for r in resultats_matching if r.of is not None)
    console.print(f"✅ {of_trouves}/{len(commandes_s1)} OF matchés")

    # Détail par type
    mts_count = sum(1 for r in resultats_matching if r.commande.is_mts() and r.of is not None)
    nor_mto_count = sum(1 for r in resultats_matching if r.commande.is_nor_mto() and r.of is not None)
    console.print(f"   MTS : {mts_count}")
    console.print(f"   NOR/MTO : {nor_mto_count}")
    console.print()

    # 3. Vérifier la faisabilité des OF
    ofs_a_verifier = [r.of for r in resultats_matching if r.of is not None]

    if ofs_a_verifier:
        console.print(f"[bold cyan]🔍 Vérification de faisabilité...[/bold cyan]")
        checker = ProjectedChecker(loader)
        resultats_faisabilite = checker.check_all_ofs(ofs_a_verifier)

        faisables = sum(1 for r in resultats_faisabilite.values() if r.feasible)
        console.print(f"✅ {faisables}/{len(ofs_a_verifier)} OF faisables")
        console.print()
    else:
        resultats_faisabilite = {}
        console.print("[yellow]⚠️  Aucun OF à vérifier[/yellow]")
        console.print()

    # 4. Afficher le rapport
    format_rapport_s1(resultats_matching, resultats_faisabilite)
