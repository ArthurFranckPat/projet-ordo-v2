#!/usr/bin/env python
"""Script de test avec le vrai LLM Mistral.

Ce script utilise la vraie API Mistral (pas le mock).
Nécessite une clé API Mistral valide.
"""

import sys
import os
from pathlib import Path

# Charger les variables d'environnement depuis .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv non installé, utiliser les variables d'environnement existantes

# Ajouter src au path
sys.path.insert(0, str(Path(__file__).parent))

from src.loaders.data_loader import DataLoader
from src.decisions.llm.mistral_client import MistralLLMClient
from src.decisions.llm.llm_decision_rule import LLMBasedDecisionRule


def main():
    """Test du système avec vrai LLM Mistral."""
    print("=" * 80)
    print("TEST DU SYSTÈME DE DÉCISION LLM - MISTRAL RÉEL")
    print("=" * 80)
    print()

    # Vérifier la clé API
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("❌ Erreur: Variable d'environnement MISTRAL_API_KEY non définie")
        print()
        print("Pour utiliser ce script:")
        print("  export MISTRAL_API_KEY='votre_clé_ici'")
        print("  python test_mistral_real.py")
        print()
        print("Ou créer un fichier .env avec:")
        print("  MISTRAL_API_KEY=votre_clé_ici")
        return 1

    print(f"✓ Clé API trouvée (longueur: {len(api_key)} caractères)")
    print()

    # 1. Charger les données
    print("1. Chargement des données...")
    loader = DataLoader(data_dir="data")
    print(f"   ✓ {len(loader.ofs)} OFs chargés")
    print(f"   ✓ {len(loader.commandes_clients)} commandes chargées")
    print(f"   ✓ {len(loader.nomenclatures)} nomenclatures chargées")
    print(f"   ✓ {len(loader.stocks)} stocks chargés")
    print(f"   ✓ {len(loader.allocations)} allocations chargées")
    print()

    # 2. Récupérer F126-44769
    print("2. Récupération de F126-44769...")
    of = loader.get_of_by_num("F126-44769")
    if not of:
        print("   ✗ OF non trouvé !")
        return 1

    print(f"   ✓ OF trouvé : {of.num_of}")
    print(f"     - Article : {of.article}")
    print(f"     - Description : {of.description}")
    print(f"   - Quantité restante : {of.qte_restante}")
    print(f"   - Date de fin : {of.date_fin}")
    print(f"   - Statut : {of.statut_texte}")
    print()

    # 3. Récupérer la commande associée (si disponible)
    print("3. Recherche de commande associée...")
    commande = None
    for cmd in loader.commandes_clients:
        if cmd.article == of.article and cmd.qte_restante > 0:
            commande = cmd
            break

    if commande:
        print(f"   ✓ Commande trouvée : {commande.num_commande}")
        print(f"     - Client : {commande.nom_client}")
        print(f"   - Quantité restante : {commande.qte_restante}")
    else:
        print("   ⚠ Aucune commande associée trouvée")
    print()

    # 4. Créer le client LLM Mistral
    print("4. Initialisation du client Mistral...")
    try:
        llm_client = MistralLLMClient(
            model="mistral-large-latest",
            temperature=0.3
        )
        print("   ✓ Client Mistral initialisé")
        print(f"     - Modèle: {llm_client.model}")
        print(f"     - Température: {llm_client.temperature}")
        print()
    except Exception as e:
        print(f"   ✗ Erreur d'initialisation: {e}")
        return 1

    # 5. Créer la règle de décision LLM
    print("5. Initialisation de LLMBasedDecisionRule...")
    decision_rule = LLMBasedDecisionRule(
        llm_client=llm_client,
        config_path="config/decisions_llm.yaml"
    )
    print("   ✓ Règle de décision initialisée")
    print()

    # 6. Évaluer l'OF
    print("6. Évaluation de l'OF avec Mistral...")
    try:
        print("   → Construction du contexte...")
        decision = decision_rule.evaluate(
            of=of,
            commande=commande,
            loader=loader,
            competing_ofs=None
        )
        print()
        print("   ✓ Décision obtenue !")
        print()

        # 7. Afficher le résultat
        print("=" * 80)
        print("RÉSULTAT DE LA DÉCISION")
        print("=" * 80)
        print()
        print(f"Action : {decision.action.value}")
        print()
        print(f"Raison : {decision.reason}")
        print()

        if decision.modified_quantity:
            print(f"Quantité modifiée : {decision.modified_quantity}")
            print()

        if decision.defer_date:
            print(f"Date de report : {decision.defer_date}")
            print()

        if "action_required" in decision.metadata:
            print(f"Action requise : {decision.metadata['action_required']}")
            print()

        if decision.metadata:
            print("Métadonnées :")
            for key, value in decision.metadata.items():
                if key != "action_required":
                    print(f"  - {key} : {value}")
            print()

        print("=" * 80)
        print("TEST TERMINÉ AVEC SUCCÈS")
        print("=" * 80)

    except Exception as e:
        print(f"\n   ✗ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
