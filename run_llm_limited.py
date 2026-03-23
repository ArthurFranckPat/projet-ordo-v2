#!/usr/bin/env python
"""Script limité testant le système de décision LLM sur un petit échantillon."""

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
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def main():
    """Test le système LLM sur un échantillon limité."""
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]SYSTÈME DE DÉCISION LLM - MODE LIMITÉ (20 OFs)[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    # 1. Charger les données
    console.print("[bold cyan]1. Chargement des données...[/bold cyan]")
    loader = DataLoader(data_dir="data")
    console.print(f"   ✅ {len(loader.ofs)} OFs chargés")
    console.print()

    # 2. Initialiser le client LLM
    console.print("[bold cyan]2. Initialisation du client Mistral...[/bold cyan]")
    try:
        llm_client = MistralLLMClient(
            model="mistral-large-latest",
            temperature=0.3
        )
        console.print(f"   ✅ Client Mistral initialisé")
        console.print()
    except Exception as e:
        console.print(f"   [bold red]❌ Erreur: {e}[/bold red]")
        return 1

    # 3. Créer le DecisionEngine
    console.print("[bold cyan]3. Initialisation du DecisionEngine...[/bold cyan]")
    decision_engine = DecisionEngine(
        use_llm=True,
        llm_client=llm_client,
        loader=loader
    )
    console.print("   ✅ DecisionEngine initialisé")
    console.print()

    # 4. Sélectionner un échantillon d'OFs
    console.print("[bold cyan]4. Sélection de l'échantillon...[/bold cyan]")
    all_ofs = loader.get_ofs_to_check()

    # Prendre les 20 premiers OFs qui ont une nomenclature
    sample_ofs = []
    for of in all_ofs:
        if len(sample_ofs) >= 20:
            break
        nomenclature = loader.get_nomenclature(of.article)
        if nomenclature and nomenclature.composants:
            sample_ofs.append(of)

    console.print(f"   📋 {len(sample_ofs)} OFs sélectionnés (avec nomenclature)")
    console.print()

    # 5. Traitement avec affichage détaillé
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]5. Traitement des OFs avec décisions LLM...[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    results = {}
    success_count = 0
    fallback_count = 0

    for i, of in enumerate(sample_ofs, 1):
        console.print(f"[{i}/{len(sample_ofs)}] [bold]{of.num_of}[/bold] - {of.article}...")

        try:
            # Récupérer la commande associée si disponible
            commande = None
            for cmd in loader.commandes_clients:
                if cmd.article == of.article and cmd.qte_restante > 0:
                    commande = cmd
                    break

            # Évaluer avec le LLM
            decision = decision_engine.evaluate_pre_allocation(
                of=of,
                initial_stock={},
                commande=commande
            )

            results[of.num_of] = decision

            # Afficher le résultat
            action_emoji = {
                "accept_as_is": "✅",
                "accept_partial": "🟡",
                "defer": "⏰",
                "defer_partial": "⏰🟡",
                "reject": "❌"
            }.get(decision.action.value, "❓")

            console.print(f"    {action_emoji} Action: {decision.action.value}")

            if decision.modified_quantity:
                console.print(f"    📊 Quantité: {decision.modified_quantity}")

            if decision.defer_date:
                console.print(f"    📅 Date: {decision.defer_date}")

            console.print(f"    💭 {decision.reason[:100]}...")

            if decision.metadata.get("llm_generated"):
                success_count += 1
                console.print(f"    ✨ LLM (confiance: {decision.metadata.get('llm_confidence', 'N/A')})")
            else:
                fallback_count += 1
                console.print(f"    ⚠️  Fallback")

            console.print()

        except Exception as e:
            console.print(f"    [bold red]❌ Erreur: {e}[/bold red]")
            console.print()

    # 6. Résumé
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]RÉSUME[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()
    console.print(f"✅ OFs traités : {len(results)}")
    console.print(f"✨ Décisions LLM : {success_count} ({success_count/len(results)*100:.1f}%)")
    console.print(f"⚠️  Fallbacks : {fallback_count} ({fallback_count/len(results)*100:.1f}%)")
    console.print()

    # Répartition des actions
    action_counts = {}
    for decision in results.values():
        action = decision.action.value
        action_counts[action] = action_counts.get(action, 0) + 1

    console.print("[bold]Répartition des actions :[/bold]")
    for action, count in sorted(action_counts.items()):
        console.print(f"   {action:20} : {count:2}")
    console.print()

    console.print("[bold green]✅ TEST TERMINÉ[/bold green]")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]❌ Interruption[/bold red]")
        sys.exit(1)
