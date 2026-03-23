"""Tests des modèles de décision."""

import pytest
from datetime import date, datetime
from src.agents.models import DecisionAction, DecisionResult, DecisionContext
from src.models.of import OF
from src.checkers.base import FeasibilityResult


def test_decision_action_enum():
    """Test que DecisionAction a toutes les valeurs requises."""
    assert hasattr(DecisionAction, 'ACCEPT_AS_IS')
    assert hasattr(DecisionAction, 'ACCEPT_PARTIAL')
    assert hasattr(DecisionAction, 'REJECT')
    assert hasattr(DecisionAction, 'DEFER')
    assert hasattr(DecisionAction, 'DEFER_PARTIAL')


def test_decision_result_creation():
    """Test la création d'un DecisionResult."""
    result = DecisionResult(
        action=DecisionAction.ACCEPT_AS_IS,
        reason="Test reason"
    )

    assert result.action == DecisionAction.ACCEPT_AS_IS
    assert result.reason == "Test reason"
    assert result.modified_quantity is None
    assert result.defer_date is None
    assert result.metadata == {}
    assert isinstance(result.timestamp, datetime)


def test_decision_result_with_partial_acceptance():
    """Test DecisionResult avec acceptation partielle."""
    result = DecisionResult(
        action=DecisionAction.ACCEPT_PARTIAL,
        reason="Accepter 98.6%",
        modified_quantity=145,
        metadata={
            "original_quantity": 147,
            "completion_rate": 0.986
        }
    )

    assert result.action == DecisionAction.ACCEPT_PARTIAL
    assert result.modified_quantity == 145
    assert result.metadata["original_quantity"] == 147


def test_decision_context_creation():
    """Test la création d'un DecisionContext."""
    of = OF(
        num_of="F123",
        article="TEST",
        description="Test article",
        statut_num=1,
        statut_texte="Ferme",
        date_fin=date(2026, 3, 30),
        qte_a_fabriquer=100,
        qte_fabriquee=0,
        qte_restante=100
    )
    feasibility = FeasibilityResult(feasible=False)

    context = DecisionContext(
        of=of,
        feasibility_result=feasibility,
        initial_stock={"COMP1": 50},
        allocated_stock={},
        remaining_stock={"COMP1": 50}
    )

    assert context.of.num_of == "F123"
    assert context.feasibility_result.feasible is False
    assert context.initial_stock == {"COMP1": 50}
    assert context.allocated_stock == {}
    assert context.remaining_stock == {"COMP1": 50}


def test_decision_context_with_all_fields():
    """Test DecisionContext avec tous les champs."""
    from src.models.besoin_client import BesoinClient, NatureBesoin, TypeCommande

    of = OF(
        num_of="F123",
        article="TEST",
        description="Test article",
        statut_num=1,
        statut_texte="Ferme",
        date_fin=date(2026, 3, 30),
        qte_a_fabriquer=100,
        qte_fabriquee=0,
        qte_restante=100
    )
    commande = BesoinClient(
        nom_client="ALDES",
        code_pays="FR",
        type_commande=TypeCommande.MTS,
        num_commande="C123",
        nature_besoin=NatureBesoin.COMMANDE,
        article="TEST",
        of_contremarque="",
        date_commande=date(2026, 3, 20),
        date_expedition_demandee=date(2026, 3, 30),
        qte_commandee=100,
        qte_allouee=0,
        qte_restante=100
    )

    context = DecisionContext(
        of=of,
        commande=commande,
        feasibility_result=None,
        initial_stock={},
        allocated_stock={},
        remaining_stock={},
        competing_ofs=[of],
        current_date=date(2026, 3, 22)
    )

    assert context.commande.nom_client == "ALDES"
    assert context.competing_ofs == [of]
    assert context.current_date == date(2026, 3, 22)
