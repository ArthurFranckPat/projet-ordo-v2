#!/usr/bin/env python
"""Script de debug pour voir les réponses brutes du LLM."""

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

def main():
    """Test un OF problématique et affiche la réponse brute du LLM."""
    # Charger les données
    loader = DataLoader(data_dir="data")

    # Créer le client LLM
    llm_client = MistralLLMClient(
        model="mistral-large-latest",
        temperature=0.3
    )

    # Créer la règle de décision
    decision_rule = LLMBasedDecisionRule(llm_client=llm_client)

    # Prendre un OF problématique
    of = loader.get_of_by_num("SGAE10624443540")

    if not of:
        print("OF non trouvé")
        return 1

    print(f"OF: {of.num_of}")
    print(f"Article: {of.article}")
    print(f"Quantité: {of.qte_restante}")
    print()

    # Construire le contexte et le prompt
    from src.decisions.llm.context_builder import LLMContextBuilder
    from src.decisions.llm.prompt_builder import LLMPromptBuilder

    context_builder = LLMContextBuilder(loader=loader)
    prompt_builder = LLMPromptBuilder()

    context = context_builder.build_context(of, None)

    print("=" * 80)
    print("CONTEXTE D'ANALYSE")
    print("=" * 80)
    print(f"Faisabilité: {context.situation_globale.faisabilite}")

    if context.situation_globale.raison_blocage:
        print(f"Raison blocage: {context.situation_globale.raison_blocage}")

    print(f"Nombre de composants: {len(context.composants)}")
    print()

    # Construire le prompt
    prompt_dict = context.to_dict()
    prompt = prompt_builder.build_decision_prompt(prompt_dict)
    system_prompt = prompt_builder.build_system_prompt()

    print("=" * 80)
    print("PROMPT ENVOYÉ AU LLM")
    print("=" * 80)
    print(f"Longueur prompt: {len(prompt)} caractères")
    print()
    print("--- DERNIERS 500 CARACTÈRES DU PROMPT ---")
    print(prompt[-500:])
    print()

    # Appeler le LLM
    print("=" * 80)
    print("APPEL AU LLM...")
    print("=" * 80)

    try:
        response = llm_client.call_llm(prompt, system_prompt)

        print(f"Longueur réponse: {len(response)} caractères")
        print()
        print("--- RÉPONSE BRUTE DU LLM ---")
        print(response)
        print()
        print("=" * 80)
        print("--- FIN RÉPONSE ---")
        print()

        # Essayer de parser
        print("=" * 80)
        print("TENTATIVE DE PARSING...")
        print("=" * 80)

        from src.decisions.llm.response_parser import LLMResponseParser
        parser = LLMResponseParser()

        try:
            parsed = parser.parse_decision(response)
            print(f"✅ PARSING RÉUSSI")
            print(f"Action: {parsed.action}")
            print(f"Reason: {parsed.reason}")
            print(f"Confidence: {parsed.confidence}")
        except Exception as e:
            print(f"❌ ERREUR DE PARSING: {e}")
            print()
            print("--- RÉPONSE NETTOYÉE ---")
            cleaned = parser._clean_response(response)
            print(cleaned)

    except Exception as e:
        print(f"❌ ERREUR LLM: {e}")
        import traceback
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    sys.exit(main())
