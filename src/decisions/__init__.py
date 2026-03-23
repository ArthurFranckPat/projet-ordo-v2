"""Couche décision métier pour l'ordonnancement.

Ce module fournit un système de décision nuancée basé sur des critères
configurables pour prendre des décisions d'acceptation, de rejet ou de
report d'OFs (Ordres de Fabrication).

Le système peut fonctionner en deux modes :
- Mode classique : règles statiques (SmartDecisionRule)
- Mode LLM : décisions nuancées via LLM (LLMBasedDecisionRule)
"""

from .models import DecisionAction, DecisionResult, DecisionContext
from .engine import DecisionEngine

# Composants LLM
from .llm import (
    LLMAnalysisContext,
    OFInfo,
    CommandeInfo,
    ComposantAnalyse,
    ComposantCritique,
    SituationGlobale
)
from .llm.llm_client import BaseLLMClient, MockLLMClient
from .llm.llm_decision_rule import LLMBasedDecisionRule
from .llm.context_builder import LLMContextBuilder
from .llm.prompt_builder import LLMPromptBuilder
from .llm.response_parser import LLMResponseParser, ParsedLLMDecision

__all__ = [
    # Core
    "DecisionAction",
    "DecisionResult",
    "DecisionContext",
    "DecisionEngine",

    # LLM Models
    "LLMAnalysisContext",
    "OFInfo",
    "CommandeInfo",
    "ComposantAnalyse",
    "ComposantCritique",
    "SituationGlobale",

    # LLM Components
    "BaseLLMClient",
    "MockLLMClient",
    "LLMBasedDecisionRule",
    "LLMContextBuilder",
    "LLMPromptBuilder",
    "LLMResponseParser",
    "ParsedLLMDecision",
]
