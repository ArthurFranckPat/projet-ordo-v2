"""Tests for OrganizationEvaluator"""

import pytest


def test_get_organization_scenarios():
    """Scenarios are ordered ascending by hours so the selection loop works correctly."""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator

    evaluator = OrganizationEvaluator()
    scenarios = evaluator.get_organization_scenarios()

    assert len(scenarios) == 4
    # Must be sorted ascending so the first-match loop selects the lightest covering scenario
    hours = [s.hours for s in scenarios]
    assert hours == sorted(hours), f"Scenarios must be sorted ascending by hours, got {hours}"
    # partial is the lightest
    assert scenarios[0].type == "partial"
    assert scenarios[0].hours == 17.5
    assert scenarios[1].type == "1x8"
    assert scenarios[2].type == "2x8"
    assert scenarios[3].type == "3x8"


def test_charge_within_tolerance_does_not_jump_to_next_tier():
    """37.3h ne doit pas déclencher 2x8 : 37.3h ≤ 35h × 1.10 (tolérance ±10%)."""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_153",
        charge_s1=37.3,
        charge_s2=25.7,
        charge_s3=29.7,
        charge_s4=10.0,
        trend=TrendType.DOWNWARD
    )

    org = evaluator.select_optimal_organization(result)

    assert org.type == "1x8", (
        f"37.3h est dans la tolérance ±10% de 1x8 (35h), attendu 1x8, obtenu {org.type}"
    )


def test_select_optimal_organization_exceeds_all_scenarios():
    """When charge exceeds all scenarios, return the heaviest (3x8), not the lightest."""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=200.0,  # Far exceeds 3x8 (105h)
        charge_s2=200.0,
        charge_s3=200.0,
        charge_s4=200.0,
        trend=TrendType.STABLE
    )

    org = evaluator.select_optimal_organization(result)

    assert org.type == "3x8", f"Expected 3x8 for overloaded poste, got {org.type}"


def test_select_optimal_organization_picks_partial_for_low_charge():
    """For very low charge (< 17.5h), partial organization is selected."""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=10.0,
        charge_s2=12.0,
        charge_s3=11.0,
        charge_s4=9.0,
        trend=TrendType.STABLE
    )

    org = evaluator.select_optimal_organization(result)

    assert org.type == "partial", f"Expected partial for low charge (10h), got {org.type}"


def test_evaluate_organization_coverage():
    """Evaluate coverage rate for an organization"""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=25.0,
        charge_s2=35.0,
        charge_s3=45.0,
        charge_s4=60.0,
        trend=TrendType.UPWARD
    )

    org = OrganizationType(type="1x8", hours=35.0)

    charge_treated, coverage_pct = evaluator.evaluate_organization(result, org)

    assert charge_treated == 25.0  # S+1 charge
    assert coverage_pct == 100.0  # 25/35 = 71% mais charge traitée = 100% de S+1


def test_select_optimal_organization_stable_trend():
    """Select organization for stable trend"""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=35.0,  # Exactement 1x8
        charge_s2=36.0,
        charge_s3=34.0,
        charge_s4=35.0,
        trend=TrendType.STABLE
    )

    org = evaluator.select_optimal_organization(result)

    assert org.type == "1x8"
    assert org.hours == 35.0


def test_select_optimal_organization_upward_trend():
    """Select organization for upward trend - should upgrade one level"""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=30.0,  # 1x8 suffirait normalement
        charge_s2=45.0,
        charge_s3=55.0,
        charge_s4=65.0,
        trend=TrendType.UPWARD  # Mais tendance haussière → anticiper
    )

    org = evaluator.select_optimal_organization(result)

    # Avec +10 de marge, 30+10 = 40, donc 2x8 (70h) sélectionné
    assert org.type == "2x8"
    assert org.hours == 70.0


def test_select_optimal_organization_downward_trend():
    """Select organization for downward trend - base organization"""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=70.0,  # 2x8
        charge_s2=60.0,
        charge_s3=50.0,
        charge_s4=40.0,
        trend=TrendType.DOWNWARD  # Tendance baissière → pas d'anticipation
    )

    org = evaluator.select_optimal_organization(result)

    # Reste sur 2x8 (base S+1)
    assert org.type == "2x8"
    assert org.hours == 70.0


def test_evaluate_organization_insufficient_capacity():
    """Evaluate organization when capacity is insufficient"""
    from src.agents.organization.organization_evaluator import OrganizationEvaluator
    from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType

    evaluator = OrganizationEvaluator()

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=70.0,  # 2x8 needed
        charge_s2=80.0,
        charge_s3=90.0,
        charge_s4=100.0,
        trend=TrendType.UPWARD
    )

    org = OrganizationType(type="1x8", hours=35.0)  # Capacity insufficient

    charge_treated, coverage_pct = evaluator.evaluate_organization(result, org)

    # Only 35h treated out of 70h
    assert charge_treated == 35.0
    assert coverage_pct == 50.0  # 35/70 = 50%
