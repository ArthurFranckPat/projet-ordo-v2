"""Tests for LLMOrganizationAdvisor"""

import json
import pytest
from unittest.mock import MagicMock
from datetime import date

from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType


def _make_result(charge_s1=37.3, trend=TrendType.DOWNWARD):
    return PosteChargeResult(
        poste="PP_153",
        charge_s1=charge_s1,
        charge_s2=25.7,
        charge_s3=29.7,
        charge_s4=10.0,
        trend=trend,
        slope=-9.1,
    )


def test_llm_selects_organization_from_response():
    """LLM recommande 1x8 pour une charge de 37.3h en tendance baissière."""
    from src.agents.organization.llm_org_advisor import LLMOrganizationAdvisor

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.return_value = json.dumps({
        "organisation": "1x8",
        "raison": "Charge de 37.3h avec tendance baissière — 1×8 suffit.",
        "confiance": 0.9
    })

    advisor = LLMOrganizationAdvisor(llm_client)
    org = advisor.select_optimal_organization(_make_result())

    assert org.type == "1x8"
    assert org.hours == 35.0
    llm_client.call_llm_with_retry.assert_called_once()


def test_llm_can_recommend_2x8():
    """LLM peut choisir 2x8 pour une charge élevée en tendance haussière."""
    from src.agents.organization.llm_org_advisor import LLMOrganizationAdvisor

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.return_value = json.dumps({
        "organisation": "2x8",
        "raison": "Charge croissante sur 4 semaines, anticiper la hausse.",
        "confiance": 0.85
    })

    result = _make_result(charge_s1=62.0, trend=TrendType.UPWARD)
    advisor = LLMOrganizationAdvisor(llm_client)
    org = advisor.select_optimal_organization(result)

    assert org.type == "2x8"
    assert org.hours == 70.0


def test_llm_org_advisor_falls_back_on_llm_error():
    """Fallback algorithmique quand le LLM lève une exception."""
    from src.agents.organization.llm_org_advisor import LLMOrganizationAdvisor

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.side_effect = RuntimeError("timeout")

    advisor = LLMOrganizationAdvisor(llm_client)
    org = advisor.select_optimal_organization(_make_result(charge_s1=37.3, trend=TrendType.DOWNWARD))

    # Fallback : 37.3h ≤ 35×1.10=38.5h → algorithme retourne 1x8
    assert org.type == "1x8"


def test_llm_org_advisor_falls_back_on_invalid_json():
    """Fallback algorithmique quand la réponse LLM n'est pas du JSON valide."""
    from src.agents.organization.llm_org_advisor import LLMOrganizationAdvisor

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.return_value = "Je recommande 1x8 car la charge est faible."

    advisor = LLMOrganizationAdvisor(llm_client)
    org = advisor.select_optimal_organization(_make_result())

    assert org.type in ("partial", "1x8", "2x8", "3x8")


def test_llm_org_advisor_falls_back_on_unknown_org_type():
    """Fallback algorithmique si le LLM retourne un type inconnu."""
    from src.agents.organization.llm_org_advisor import LLMOrganizationAdvisor

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.return_value = json.dumps({
        "organisation": "4x8",
        "raison": "Charge exceptionnelle.",
        "confiance": 0.5
    })

    advisor = LLMOrganizationAdvisor(llm_client)
    org = advisor.select_optimal_organization(_make_result())

    assert org.type in ("partial", "1x8", "2x8", "3x8")


def test_organization_agent_uses_llm_when_provided():
    """OrganizationAgent utilise LLMOrganizationAdvisor quand llm_client est fourni."""
    from src.agents.organization.organization_agent import OrganizationAgent

    llm_client = MagicMock()
    llm_client.call_llm_with_retry.return_value = json.dumps({
        "organisation": "2x8",
        "raison": "Le LLM a décidé 2x8.",
        "confiance": 0.95
    })

    loader = MagicMock()
    loader.commandes_clients = []

    agent = OrganizationAgent(loader, llm_client=llm_client)

    # Stub charge_calculator pour retourner des résultats prédéfinis
    from src.agents.organization.models import PosteChargeResult, TrendType
    fake_results = {
        "PP_830": PosteChargeResult(
            poste="PP_830", charge_s1=60.0, charge_s2=55.0,
            charge_s3=65.0, charge_s4=70.0, trend=TrendType.UPWARD
        )
    }
    agent.charge_calculator.calculate_charge_horizons = MagicMock(return_value=fake_results)

    results = agent.analyze_workshop_organization(reference_date=date.today())

    assert results["PP_830"].recommended_org.type == "2x8"
    llm_client.call_llm_with_retry.assert_called_once()
