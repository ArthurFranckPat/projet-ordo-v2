#!/usr/bin/env python
"""Test du LLM avec E7211 (composant au forfait)."""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from src.loaders.data_loader import DataLoader
from src.decisions.llm.mistral_client import MistralLLMClient
from src.decisions.llm.llm_decision_rule import LLMBasedDecisionRule

def main():
    """Test E7211 avec le LLM."""
    loader = DataLoader(data_dir="data")

    # OF AEA1241XX qui avait le problème
    of = loader.get_of_by_num("SGAE10624435479")

    if not of:
        print("OF non trouvé")
        return 1

    print(f"OF: {of.num_of}")
    print(f"Article: {of.article}")
    print(f"Quantité: {of.qte_restante}")
    print()

    # Créer le client LLM
    llm_client = MistralLLMClient(
        model="mistral-large-latest",
        temperature=0.3
    )

    decision_rule = LLMBasedDecisionRule(llm_client=llm_client)

    # Analyser
    print("Analyse LLM...")
    decision = decision_rule.evaluate(of=of, commande=None, loader=loader)

    print()
    print(f"Action: {decision.action.value}")
    print(f"Reason: {decision.reason}")
    print()

    # Regarder ce qui se passe pour E7211
    nomenclature = loader.get_nomenclature(of.article)
    if nomenclature:
        for comp in nomenclature.composants:
            if comp.article_composant == "E7211":
                print(f"Composant E7211:")
                print(f"  Nature: {comp.nature_consommation.value}")
                print(f"  Qté lien: {comp.qte_lien}")
                print(f"  Quantité requise (avant correction): {comp.qte_lien * of.qte_restante}")

                # Calcul corrigé
                from src.models.nomenclature import NatureConsommation
                if comp.nature_consommation == NatureConsommation.FORFAIT:
                    qte_requise_corrigee = int(comp.qte_lien)
                else:
                    qte_requise_corrigee = int(comp.qte_lien * of.qte_restante)

                print(f"  Quantité requise (avec correction): {qte_requise_corrigee}")
                print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
