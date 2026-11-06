"""LLM-based organization advisor for workshop scheduling."""

import json
import logging
from typing import Optional

from .models import OrganizationType, PosteChargeResult
from .organization_evaluator import OrganizationEvaluator

logger = logging.getLogger(__name__)

_VALID_ORG_TYPES = {
    "partial": 17.5,
    "1x8": 35.0,
    "2x8": 70.0,
    "3x8": 105.0,
}

_SYSTEM_PROMPT = """Tu es un expert en ordonnancement de production manufacturière.
Tu reçois la charge hebdomadaire d'un poste de travail sur 4 semaines et tu recommandes
l'organisation la plus adaptée pour la semaine S+1.

Organisations disponibles (par ordre croissant de capacité) :
- "partial" : travail partiel (~17.5h/semaine, soit 2.5 jours en 1×8)
- "1x8"    : 1 équipe × 8h/jour = 35h/semaine
- "2x8"    : 2 équipes × 8h/jour = 70h/semaine
- "3x8"    : 3 équipes × 8h/jour = 105h/semaine

Règles de sélection :
- Tendance stable ou baissière : choisir l'organisation couvrant S+1 avec une tolérance de ±10%
- Tendance haussière : anticiper d'un niveau au-dessus de S+1

Réponds UNIQUEMENT en JSON avec ce format exact :
{
  "organisation": "<type>",
  "raison": "<explication courte en français>",
  "confiance": <0.0 à 1.0>
}"""


def _build_prompt(result: PosteChargeResult) -> str:
    return f"""Poste : {result.poste}
Charge S+1 : {result.charge_s1:.1f}h
Charge S+2 : {result.charge_s2:.1f}h
Charge S+3 : {result.charge_s3:.1f}h
Charge S+4 : {result.charge_s4:.1f}h
Tendance : {result.trend.value}

Quelle organisation recommandes-tu pour S+1 ?"""


class LLMOrganizationAdvisor:
    """Utilise un LLM pour sélectionner l'organisation atelier.

    Remplace l'algorithme de OrganizationEvaluator.select_optimal_organization().
    Fallback algorithmique automatique si le LLM échoue ou retourne une valeur invalide.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self._fallback = OrganizationEvaluator()

    def _parse_response(self, response: str) -> Optional[OrganizationType]:
        """Parse la réponse JSON du LLM, fallback si invalide."""
        try:
            # Extraire le JSON (le LLM peut ajouter du texte avant/après)
            start = response.find("{")
            end = response.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("Pas de JSON trouvé dans la réponse")
            data = json.loads(response[start:end])

            org_type = data.get("organisation", "").strip().lower()
            if org_type not in _VALID_ORG_TYPES:
                raise ValueError(f"Type d'organisation inconnu : {org_type!r}")

            return OrganizationType(type=org_type, hours=_VALID_ORG_TYPES[org_type])

        except (ValueError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"LLM response parse error ({e}), using fallback")
            return None

    def select_optimal_organization(self, result: PosteChargeResult) -> OrganizationType:
        """Sélectionne l'organisation via le LLM avec fallback algorithmique."""
        try:
            response = self.llm_client.call_llm_with_retry(
                prompt=_build_prompt(result),
                system_prompt=_SYSTEM_PROMPT,
            )
            org = self._parse_response(response)
            if org is not None:
                return org
        except Exception as e:
            logger.warning(f"[{result.poste}] LLM org advisor failed ({e}), using fallback")

        return self._fallback.select_optimal_organization(result)
