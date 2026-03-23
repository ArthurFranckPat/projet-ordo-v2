#!/usr/bin/env python
"""Script principal : Analyse des commandes clients avec le LLM.

Point d'entrée : LES COMMANDES CLIENTS (pas les OFs)
Pour chaque commande, le système décide si elle est satisfaisable.
"""

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
from src.decisions.llm.llm_decision_rule import LLMBasedDecisionRule
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def main():
    """Analyse les commandes clients avec le système LLM."""
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]ANALYSE DES COMMANDES CLIENTS - SYSTÈME LLM[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    # 1. Charger les données
    console.print("[bold cyan]1. Chargement des données...[/bold cyan]")
    loader = DataLoader(data_dir="data")
    console.print(f"   ✅ {len(loader.commandes_clients)} commandes clients")
    console.print(f"   ✅ {len(loader.ofs)} OFs disponibles")
    console.print(f"   ✅ {len(loader.stocks)} stocks")
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

    # 3. Créer la règle de décision LLM
    console.print("[bold cyan]3. Initialisation de la règle de décision LLM...[/bold cyan]")
    decision_rule = LLMBasedDecisionRule(
        llm_client=llm_client,
        config_path="config/decisions_llm.yaml"
    )
    console.print("   ✅ Règle de décision LLM initialisée")
    console.print()

    # 4. Récupérer les commandes à analyser
    console.print("[bold cyan]4. Sélection des commandes à analyser...[/bold cyan]")

    # Filtrer les commandes avec quantité restante > 0
    commandes = [c for c in loader.commandes_clients if c.qte_restante > 0]

    console.print(f"   📋 {len(commandes)} commandes à servir (qté restante > 0)")
    console.print()

    # 5. Analyser chaque commande
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]5. Analyse des commandes avec le LLM...[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    results = []
    llm_count = 0
    stock_count = 0
    of_count = 0

    for i, commande in enumerate(commandes, 1):
        console.print(f"[{i}/{len(commandes)}] [bold]{commande.num_commande}[/bold] - {commande.nom_client}")
        console.print(f"    Article: {commande.article}")
        console.print(f"    Qté: {commande.qte_restante} | Date: {commande.date_expedition_demandee}")
        console.print(f"    Type: {'MTS' if commande.is_mts() else 'NOR/MTO'}")

        try:
            # Étape 1: Allouer le stock disponible
            stock_dispo = 0
            stock_info = loader.get_stock(commande.article)
            if stock_info:
                stock_dispo = max(0, stock_info.stock_physique - stock_info.stock_alloue - stock_info.stock_bloque)

            qte_allouee = min(commande.qte_restante, stock_dispo)
            besoin_net = commande.qte_restante - qte_allouee

            if besoin_net > 0:
                console.print(f"    📦 Stock: {qte_allouee} unités | Besoin net: {besoin_net} unités")
            else:
                console.print(f"    ✅ Stock complet ({qte_allouee} unités)")
                stock_count += 1

            # Étape 2: Si besoin net > 0, chercher un OF
            of_match = None

            if besoin_net > 0:
                # Chercher un OF pour cet article
                ofs_article = [of for of in loader.ofs if of.article == commande.article and of.qte_restante > 0]

                if ofs_article:
                    # Prendre le premier OF affermi disponible (statut 1 = Ferme)
                    of_affermi = [of for of in ofs_article if of.statut_num == 1]
                    of_suggere = [of for of in ofs_article if of.statut_num == 3]

                    ofs_tries = (of_affermi or of_suggere)

                    if ofs_tries:
                        of = ofs_tries[0]
                        qte_of_allouee = min(besoin_net, of.qte_restante)

                        of_match = type('OFMatch', (), {
                            'of': of,
                            'qte_allouee': qte_of_allouee
                        })()

                        of_str = f"{of.num_of} ({qte_of_allouee} unités)"
                        console.print(f"    📦 OF trouvé: {of_str}")
                        of_count += 1
                    else:
                        console.print(f"    ⚠️  OFs disponibles mais statut inconnu")
                else:
                    console.print(f"    ⚠️  Aucun OF trouvé pour {besoin_net} unités")

            # Étape 3: Décision LLM sur l'OF (si trouvé)
            decision = None
            if of_match:
                console.print(f"    🤖 Analyse LLM de l'OF {of_match.of.num_of}...")
                decision = decision_rule.evaluate(
                    of=of_match.of,
                    commande=commande,
                    loader=loader
                )
                llm_count += 1
            elif besoin_net > 0:
                # Pas d'OF trouvé mais besoin > 0 → problème
                console.print(f"    ❌ Commande NON satisfaisable (besoin {besoin_net}, pas d'OF)")
            else:
                # Stock complet → OK
                console.print(f"    ✅ Commande satisfaisable par stock")

            # Enregistrer le résultat
            results.append({
                "commande": commande,
                "qte_allouee": qte_allouee,
                "of_match": of_match,
                "decision": decision,
                "satisfaisable": (besoin_net == 0) or (of_match is not None and decision and decision.action.value in ["accept_as_is", "accept_partial"])
            })

            # Afficher la décision LLM si présente
            if decision:
                action_emoji = {
                    "accept_as_is": "✅",
                    "accept_partial": "🟡",
                    "defer": "⏰",
                    "defer_partial": "⏰🟡",
                    "reject": "❌"
                }.get(decision.action.value, "❓")

                console.print(f"    {action_emoji} Décision LLM: {decision.action.value}")

                if decision.modified_quantity:
                    console.print(f"       Qté modifiée: {decision.modified_quantity}")

                if decision.defer_date:
                    console.print(f"       Date report: {decision.defer_date}")

                console.print(f"       💭 {decision.reason[:80]}...")

            console.print()

            # Limiter à 20 commandes pour le test
            if i >= 20:
                console.print("[yellow]... (limité à 20 commandes pour le test)[/yellow]")
                console.print()
                break

        except Exception as e:
            console.print(f"    [bold red]❌ Erreur: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc()[:200])
            console.print()

    # 6. Résumé
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print("[bold cyan]RÉSUMÉ[/bold cyan]")
    console.print("[bold cyan]" + "=" * 80 + "[/bold cyan]")
    console.print()

    # Statistiques
    satisfaisables = sum(1 for r in results if r["satisfaisable"])
    non_satisfaisables = len(results) - satisfaisables

    console.print(f"📊 Commandes analysées : {len(results)}")
    console.print(f"   ✅ Satisfaisables : {satisfaisables} ({satisfaisables/len(results)*100:.1f}%)")
    console.print(f"   ❌ Non satisfaisables : {non_satisfaisables} ({non_satisfaisables/len(results)*100:.1f}%)")
    console.print()
    console.print(f"📦 Servies par stock : {stock_count}")
    console.print(f"📦 Servies par OF : {of_count}")
    console.print(f"🤖 Décisions LLM : {llm_count}")
    console.print()

    # Tableau récapitulatif
    table = Table(title="Détail des commandes")
    table.add_column("Commande", style="cyan")
    table.add_column("Client")
    table.add_column("Article")
    table.add_column("Qté")
    table.add_column("Stock")
    table.add_column("OF")
    table.add_column("Décision")
    table.add_column("Statut")

    for r in results:
        c = r["commande"]
        stock_qte = r["qte_allouee"]
        of_str = r["of_match"].of.num_of if r["of_match"] else "-"
        decision_str = r["decision"].action.value if r["decision"] else "-"
        status_emoji = "✅" if r["satisfaisable"] else "❌"

        table.add_row(
            c.num_commande,
            c.nom_client[:20],
            c.article[:15],
            str(c.qte_restante),
            str(stock_qte),
            of_str[:10] if of_str != "-" else "-",
            decision_str[:15] if decision_str != "-" else "-",
            status_emoji
        )

    console.print(table)
    console.print()

    console.print("[bold green]✅ ANALYSE TERMINÉE[/bold green]")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]❌ Interruption[/bold red]")
        sys.exit(1)
