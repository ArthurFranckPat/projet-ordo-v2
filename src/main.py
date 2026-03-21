"""Point d'entrée principal du système de vérification de faisabilité."""

import argparse
from datetime import date
from pathlib import Path

from rich.console import Console

from .loaders import DataLoader
from .checkers import ImmediateChecker, ProjectedChecker, RecursiveChecker
from .algorithms import AllocationManager
from .utils import format_of_table, format_detailed_report, format_summary
from .main_s1 import main_s1

console = Console()


def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(
        description="Système de vérification de faisabilité des composants pour l'ordonnancement production"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Répertoire contenant les fichiers CSV (défaut: data)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite le nombre d'OF à vérifier (pour les tests)",
    )
    parser.add_argument(
        "--of",
        type=str,
        default=None,
        help="Numéro d'OF spécifique à vérifier (ex: F426-08419)",
    )
    parser.add_argument(
        "--commande",
        type=str,
        default=None,
        help="Numéro de commande client à vérifier (ex: AR2600885)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Affiche un rapport détaillé pour chaque OF",
    )
    parser.add_argument(
        "--no-allocation",
        action="store_true",
        help="Désactive la gestion de la concurrence",
    )
    parser.add_argument(
        "--s1",
        action="store_true",
        help="Mode S+1 : Vérifier les OF pour les commandes des 7 prochains jours",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=7,
        help="Horizon en jours pour le mode S+1 (défaut: 7)",
    )

    args = parser.parse_args()

    # Vérifier que le répertoire de données existe
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        console.print(f"[bold red]Erreur: Répertoire de données introuvable: {data_dir}[/bold red]")
        return

    # Charger les données
    console.print(f"[bold cyan]Chargement des données depuis {data_dir}...[/bold cyan]")
    loader = DataLoader(args.data_dir)
    loader.load_all()

    console.print(f"✅ {len(loader.articles)} articles chargés")
    console.print(f"✅ {len(loader.nomenclatures)} nomenclatures chargées")
    console.print(f"✅ {len(loader.ofs)} OF chargés")
    console.print(f"✅ {len(loader.stocks)} stocks chargés")
    console.print(f"✅ {len(loader.receptions)} réceptions chargées")
    console.print(f"✅ {len(loader.commandes_clients)} commandes clients chargées")
    console.print()

    # Mode S+1
    if args.s1:
        main_s1(args, loader)
        return

    # Mode vérification commande
    if args.commande:
        commandes = [c for c in loader.commandes_clients if c.num_commande == args.commande]
        if not commandes:
            console.print(f"[bold red]Erreur: Commande {args.commande} introuvable[/bold red]")
            return

        commande = commandes[0]
        type_str = "MTS" if commande.is_mts() else "NOR/MTO"
        console.print(f"🎯 Vérification de la commande {args.commande}")
        console.print(f"   Client: {commande.nom_client}")
        console.print(f"   Article: {commande.article} - {commande.description}")
        console.print(f"   Qté restante: {commande.qte_restante}")
        console.print(f"   Type: {type_str}")
        if commande.is_mts() and commande.of_contremarque:
            console.print(f"   OF lié: {commande.of_contremarque}")
        console.print()

        # Vérifier les allocations
        allocations = loader.get_allocations_of(args.commande)
        if allocations:
            console.print(f"   📦 Allocations: {len(allocations)} composant(s)")
            for alloc in allocations[:5]:
                console.print(f"      - {alloc.article}: {alloc.qte_allouee}")
            if len(allocations) > 5:
                console.print(f"      ... et {len(allocations) - 5} autres")
        else:
            console.print(f"   📦 Aucune allocation connue")
        console.print()

        # Vérification récursive
        console.print("[bold cyan]🔍 Vérification récursive avec allocations...[/bold cyan]")
        checker = RecursiveChecker(loader)
        result = checker.check_commande(commande)

        console.print(f"   {result}")
        if result.missing_components:
            console.print()
            console.print("[bold red]Composants manquants:[/bold red]")
            for article, qte in result.missing_components.items():
                console.print(f"   ❌ {article}: {qte} unités")
        if result.alerts:
            console.print()
            console.print("[yellow]Alertes:[/yellow]")
            for alert in result.alerts[:5]:
                console.print(f"   ⚠️  {alert}")
            if len(result.alerts) > 5:
                console.print(f"   ... et {len(result.alerts) - 5} autres alertes")
        console.print()
        console.print(f"   📊 Composants vérifiés: {result.components_checked}")
        console.print(f"   📊 Profondeur récursion: {result.depth}")
        console.print()

        return

    # Sélectionner les OF à vérifier
    if args.of:
        # OF spécifique
        ofs = [of for of in loader.ofs if of.num_of == args.of]
        if not ofs:
            console.print(f"[bold red]Erreur: OF {args.of} introuvable[/bold red]")
            return
        console.print(f"🎯 Vérification de l'OF {args.of}")
    else:
        # Tous les OF à vérifier
        ofs = loader.get_ofs_to_check()

        # Limiter le nombre d'OF si demandé
        if args.limit:
            ofs = ofs[: args.limit]
            console.print(f"📋 Limite: {len(ofs)} OF à vérifier")

    console.print(f"📋 {len(ofs)} OF à vérifier")
    console.print()

    # Vérification immédiate
    console.print("[bold cyan]🔍 Vérification immédiate (stock actuel)...[/bold cyan]")
    immediate_checker = ImmediateChecker(loader)
    immediate_results = immediate_checker.check_all_ofs(ofs)

    imm_feasible = sum(1 for r in immediate_results.values() if r.feasible)
    console.print(f"✅ Terminé: {imm_feasible}/{len(ofs)} OF faisables")
    console.print()

    # Vérification projetée
    console.print("[bold cyan]🔮 Vérification projetée (stock + réceptions)...[/bold cyan]")
    projected_checker = ProjectedChecker(loader)
    projected_results = projected_checker.check_all_ofs(ofs)

    proj_feasible = sum(1 for r in projected_results.values() if r.feasible)
    console.print(f"✅ Terminé: {proj_feasible}/{len(ofs)} OF faisables")
    console.print()

    # Gestion de la concurrence
    allocation_results = None
    if not args.no_allocation:
        console.print("[bold cyan]📦 Gestion de la concurrence...[/bold cyan]")
        allocation_manager = AllocationManager(loader, projected_checker)
        allocation_results = allocation_manager.allocate_stock(ofs)

        alloc_feasible = sum(1 for r in allocation_results.values() if r.status.value == "feasible")
        console.print(f"✅ Terminé: {alloc_feasible}/{len(ofs)} OF alloués")
        console.print()

    # Afficher les résultats
    format_of_table(ofs, immediate_results, projected_results, allocation_results)
    format_summary(immediate_results, projected_results, allocation_results)

    # Rapport détaillé si demandé
    if args.detailed:
        for of in ofs:
            result = projected_results.get(of.num_of)
            if result and not result.feasible:
                format_detailed_report(of, result)


if __name__ == "__main__":
    main()
