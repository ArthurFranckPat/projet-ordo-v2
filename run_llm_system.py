#!/usr/bin/env python
"""Script principal exécutant le système de décision LLM complet."""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Ajouter src au path
sys.path.insert(0, str(Path(__file__).parent))

from src.loaders.data_loader import DataLoader
from src.decisions.llm.mistral_client import MistralLLMClient
from src.decisions import DecisionEngine
from src.algorithms import AllocationManager
from src.checkers import RecursiveChecker
from src.models.besoin_client import BesoinClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def main():
    """Exécute le système complet avec le LLM."""
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]SYSTÈME DE DÉCISION LLM - MODE COMPLET[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    # 1. Charger les données
    console.print("[bold cyan]1. Chargement des données...[/bold cyan]")
    loader = DataLoader(data_dir="data")
    console.print(f"   ✅ {len(loader.ofs)} OFs chargés")
    console.print(f"   ✅ {len(loader.commandes_clients)} commandes chargées")
    console.print(f"   ✅ {len(loader.nomenclatures)} nomenclatures chargées")
    console.print(f"   ✅ {len(loader.stocks)} stocks chargés")
    console.print(f"   ✅ {len(loader.allocations)} allocations chargées")
    console.print()

    # 2. Initialiser le client LLM
    console.print("[bold cyan]2. Initialisation du client Mistral...[/bold cyan]")
    try:
        llm_client = MistralLLMClient(
            model="mistral-large-latest",
            temperature=0.3
        )
        console.print(f"   ✅ Client Mistral initialisé")
        console.print(f"      - Modèle: {llm_client.model}")
        console.print()
    except Exception as e:
        console.print(f"   [bold red]❌ Erreur d'initialisation: {e}[/bold red]")
        return 1

    # 3. Créer le DecisionEngine en mode LLM
    console.print("[bold cyan]3. Initialisation du DecisionEngine (mode LLM)...[/bold cyan]")
    decision_engine = DecisionEngine(
        use_llm=True,
        llm_client=llm_client,
        loader=loader,
        persistence_enabled=True
    )
    console.print("   ✅ DecisionEngine initialisé en mode LLM")
    console.print()

    # 4. Créer le checker récursif
    console.print("[bold cyan]4. Initialisation du checker récursif...[/bold cyan]")
    checker = RecursiveChecker(
        loader,
        use_receptions=True,
        check_date=None  # Date du jour
    )
    console.print("   ✅ Checker récursif initialisé")
    console.print()

    # 5. Créer l'allocation manager
    console.print("[bold cyan]5. Initialisation de l'AllocationManager...[/bold cyan]")
    allocation_manager = AllocationManager(
        data_loader=loader,
        checker=checker,
        decision_engine=decision_engine
    )
    console.print("   ✅ AllocationManager initialisé")
    console.print()

    # 6. Récupérer les OFs à vérifier
    console.print("[bold cyan]6. Récupération des OFs à vérifier...[/bold cyan]")
    ofs = loader.get_ofs_to_check()
    console.print(f"   📋 {len(ofs)} OFs à vérifier")
    console.print()

    # 7. Lancer l'allocation avec décisions LLM
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]7. Lancement de l'allocation avec décisions LLM...[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    results = allocation_manager.allocate_stock(ofs)

    # 8. Analyser les résultats
    console.print()
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]RÉSULTATS DES DÉCISIONS LLM[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    # Compter les décisions
    decision_counts = {}
    for of_num, result in results.items():
        if result.decision:
            action = result.decision.action.value
            decision_counts[action] = decision_counts.get(action, 0) + 1

    console.print("[bold]Répartition des décisions :[/bold]")
    for action, count in sorted(decision_counts.items()):
        percentage = (count / len(results)) * 100
        console.print(f"   {action:20} : {count:4} ({percentage:5.1f}%)")
    console.print()

    # Afficher les décisions intéressantes
    console.print("[bold]Décisions détaillées :[/bold]")
    console.print()

    # Décisions ACCEPT_PARTIAL
    partial_decisions = [
        (of_num, r) for of_num, r in results.items()
        if r.decision and r.decision.action.value == "accept_partial"
    ]

    if partial_decisions:
        console.print("[yellow]ACCEPT_PARTIAL (acceptation partielle) :[/yellow]")
        for of_num, result in partial_decisions[:10]:
            console.print(f"   • {of_num}")
            console.print(f"     Action: {result.decision.action.value}")
            console.print(f"     Quantité modifiée: {result.decision.modified_quantity}")
            console.print(f"     Raison: {result.decision.reason[:80]}...")
            console.print()
        if len(partial_decisions) > 10:
            console.print(f"   ... et {len(partial_decisions) - 10} autres")
        console.print()

    # Décisions DEFER
    defer_decisions = [
        (of_num, r) for of_num, r in results.items()
        if r.decision and r.decision.action.value == "defer"
    ]

    if defer_decisions:
        console.print("[cyan]DEFER (reporté) :[/cyan]")
        for of_num, result in defer_decisions[:10]:
            console.print(f"   • {of_num}")
            console.print(f"     Date de report: {result.decision.defer_date}")
            console.print(f"     Raison: {result.decision.reason[:80]}...")
            console.print()
        if len(defer_decisions) > 10:
            console.print(f"   ... et {len(defer_decisions) - 10} autres")
        console.print()

    # Décisions REJECT
    reject_decisions = [
        (of_num, r) for of_num, r in results.items()
        if r.decision and r.decision.action.value == "reject"
    ]

    if reject_decisions:
        console.print("[red]REJECT (rejeté) :[/red]")
        for of_num, result in reject_decisions[:10]:
            console.print(f"   • {of_num}")
            console.print(f"     Raison: {result.decision.reason[:80]}...")
            if "action_required" in result.decision.metadata:
                console.print(f"     Action requise: {result.decision.metadata['action_required']}")
            console.print()
        if len(reject_decisions) > 10:
            console.print(f"   ... et {len(reject_decisions) - 10} autres")
        console.print()

    # Résumé final
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print(f"[bold green]✅ TRAITEMENT TERMINÉ : {len(results)} OFs analysés[/bold green]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]❌ Interruption par l'utilisateur[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ Erreur: {e}[/bold red]")
        import traceback
        console.print(traceback.format_exc())
        sys.exit(1)
