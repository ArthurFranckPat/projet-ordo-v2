"""Tests for ChargeCalculator"""

import pytest
from unittest.mock import MagicMock
from datetime import date, timedelta

from src.models.besoin_client import BesoinClient, NatureBesoin, TypeCommande


def _make_commande(article, qte, days_offset=3):
    return BesoinClient(
        nom_client="CLIENT",
        code_pays="FR",
        type_commande=TypeCommande.NOR,
        num_commande="CMD001",
        nature_besoin=NatureBesoin.COMMANDE,
        article=article,
        of_contremarque="",
        date_commande=None,
        date_expedition_demandee=date.today() + timedelta(days=days_offset),
        qte_commandee=qte,
        qte_allouee=0,
        qte_restante=qte,
    )


def _make_prevision(article, qte, days_offset=3):
    return BesoinClient(
        nom_client="CLIENT",
        code_pays="FR",
        type_commande=TypeCommande.NOR,
        num_commande="PREV001",
        nature_besoin=NatureBesoin.PREVISION,
        article=article,
        of_contremarque="",
        date_commande=None,
        date_expedition_demandee=date.today() + timedelta(days=days_offset),
        qte_commandee=qte,
        qte_allouee=0,
        qte_restante=qte,
    )


def test_calculate_charge_for_single_horizon():
    """Calculate charge for one week horizon"""
    from src.agents.organization.charge_calculator import ChargeCalculator

    loader = MagicMock()
    cmd1 = _make_commande("ART001", 700)
    loader.commandes_clients = [cmd1]

    operation = MagicMock()
    operation.poste_charge = "PP_830"
    operation.cadence = 100.0
    gamme = MagicMock()
    gamme.operations = [operation]
    loader.get_gamme.return_value = gamme
    loader.get_nomenclature.return_value = None

    calculator = ChargeCalculator(loader)
    charges = calculator.calculate_charge_for_horizon(
        reference_date=date.today(),
        horizon_weeks=1,
    )

    # 700 unités / 100 cadence = 7 heures
    assert charges["PP_830"] == 7.0


def test_previsions_included_in_charge():
    """Les prévisions nettes (après consommation) doivent contribuer à la charge."""
    from src.agents.organization.charge_calculator import ChargeCalculator

    loader = MagicMock()

    # Prévision de 700 unités (pas de commande ferme → prévision nette = 700)
    prev = _make_prevision("ART001", 700)
    loader.commandes_clients = [prev]

    operation = MagicMock()
    operation.poste_charge = "PP_830"
    operation.cadence = 100.0
    gamme = MagicMock()
    gamme.operations = [operation]
    loader.get_gamme.return_value = gamme
    loader.get_nomenclature.return_value = None

    calculator = ChargeCalculator(loader)
    charges = calculator.calculate_charge_for_horizon(
        reference_date=date.today(),
        horizon_weeks=1,
    )

    # 700 unités / cadence 100 = 7h
    assert "PP_830" in charges, "La prévision doit générer de la charge sur PP_830"
    assert charges["PP_830"] == pytest.approx(7.0), f"Attendu 7.0h, obtenu {charges.get('PP_830')}"


def test_previsions_consumed_by_commandes():
    """Les prévisions sont consommées par les commandes : prévision nette = max(0, prev - cmd)."""
    from src.agents.organization.charge_calculator import ChargeCalculator

    loader = MagicMock()

    # Commande ferme : 500 unités
    cmd = _make_commande("ART001", 500)
    # Prévision : 700 unités → nette = 700 - 500 = 200
    prev = _make_prevision("ART001", 700)
    loader.commandes_clients = [cmd, prev]

    operation = MagicMock()
    operation.poste_charge = "PP_830"
    operation.cadence = 100.0
    gamme = MagicMock()
    gamme.operations = [operation]
    loader.get_gamme.return_value = gamme
    loader.get_nomenclature.return_value = None

    calculator = ChargeCalculator(loader)
    charges = calculator.calculate_charge_for_horizon(
        reference_date=date.today(),
        horizon_weeks=1,
    )

    # Commande 500 + prévision nette 200 = 700 unités → 7.0h
    assert charges.get("PP_830") == pytest.approx(7.0), (
        f"Attendu 7.0h (500 cmd + 200 prev nette), obtenu {charges.get('PP_830')}"
    )


def test_invalid_poste_codes_are_excluded():
    """Postes invalides (non PP_xxx) ne doivent pas apparaître dans la charge calculée."""
    from src.agents.organization.charge_calculator import ChargeCalculator

    loader = MagicMock()
    cmd = _make_commande("ART001", 100)
    loader.commandes_clients = [cmd]

    op_valid = MagicMock()
    op_valid.poste_charge = "PP_830"
    op_valid.cadence = 100.0

    op_invalid = MagicMock()
    op_invalid.poste_charge = "POSTE DIV AERECO 9"
    op_invalid.cadence = 50.0

    gamme = MagicMock()
    gamme.operations = [op_valid, op_invalid]
    loader.get_gamme.return_value = gamme
    loader.get_nomenclature.return_value = None

    calculator = ChargeCalculator(loader)
    charges = calculator.calculate_charge_for_horizon(
        reference_date=date.today(),
        horizon_weeks=1,
    )

    assert "PP_830" in charges, "Valid poste PP_830 should be present"
    assert "POSTE DIV AERECO 9" not in charges, "Invalid poste should be excluded"


def test_calculate_charge_horizons_s1_to_s4():
    """Calculate charge for all 4 horizons"""
    from src.agents.organization.charge_calculator import ChargeCalculator
    from src.agents.organization.models import PosteChargeResult

    loader = MagicMock()
    matcher = MagicMock()

    # Mock pour retourner des charges croissantes
    def mock_calculate_horizon(reference_date, horizon_weeks, matcher):
        if horizon_weeks == 1:
            return {"PP_830": 25.0}
        elif horizon_weeks == 2:
            return {"PP_830": 35.0}
        elif horizon_weeks == 3:
            return {"PP_830": 45.0}
        elif horizon_weeks == 4:
            return {"PP_830": 60.0}
        return {}

    calculator = ChargeCalculator(loader)
    calculator.calculate_charge_for_horizon = mock_calculate_horizon

    results = calculator.calculate_charge_horizons(
        reference_date=date.today(),
        matcher=matcher
    )

    assert "PP_830" in results
    assert results["PP_830"].charge_s1 == 25.0
    assert results["PP_830"].charge_s2 == 35.0
    assert results["PP_830"].charge_s3 == 45.0
    assert results["PP_830"].charge_s4 == 60.0
