"""Tests pour FeasibilityFilter."""

from unittest.mock import MagicMock
from src.agents.scheduling.feasibility_filter import FeasibilityFilter


def _make_of(num_of, article="ART001"):
    of = MagicMock()
    of.num_of = num_of
    of.article = article
    return of


def _make_feasibility_result(feasible, missing=None):
    r = MagicMock()
    r.feasible = feasible
    r.missing_components = missing or {}
    return r


def test_extract_stockout_components_from_non_feasible():
    """Les composants manquants des OFs non faisables sont extraits."""
    f = FeasibilityFilter()
    of1 = _make_of("F001")
    of2 = _make_of("F002")
    feas = {
        "F001": _make_feasibility_result(False, {"COMP01": 100, "COMP02": 50}),
        "F002": _make_feasibility_result(True),
    }
    stockouts = f.extract_stockout_components(feas)
    assert "COMP01" in stockouts
    assert "COMP02" in stockouts


def test_no_stockout_if_all_feasible():
    """Aucun stockout si tous les OFs sont faisables."""
    f = FeasibilityFilter()
    feas = {"F001": _make_feasibility_result(True)}
    assert f.extract_stockout_components(feas) == set()


def test_filter_ofs_not_using_stockout():
    """Un OF qui n'utilise pas les composants en rupture passe le filtre."""
    loader = MagicMock()
    # nomenclature de ART002 ne contient pas COMP01
    nom = MagicMock()
    nom.composants = [MagicMock(article_composant="COMP99")]
    loader.get_nomenclature.return_value = nom

    f = FeasibilityFilter()
    of = _make_of("F003", "ART002")
    result = f.of_uses_stockout_component(of, stockout_components={"COMP01"}, loader=loader)
    assert result is False


def test_filter_ofs_using_stockout():
    """Un OF qui utilise un composant ACHAT en rupture est filtré."""
    loader = MagicMock()
    nom = MagicMock()
    comp = MagicMock(article_composant="COMP01")
    comp.is_achete.return_value = True
    comp.is_fabrique.return_value = False
    nom.composants = [comp]
    loader.get_nomenclature.return_value = nom

    f = FeasibilityFilter()
    of = _make_of("F004", "ART003")
    result = f.of_uses_stockout_component(of, stockout_components={"COMP01"}, loader=loader)
    assert result is True


def test_fabrication_component_in_stockout_does_not_block():
    """Un composant FABRICATION en rupture NE doit PAS bloquer l'OF (règle affermissement)."""
    loader = MagicMock()
    nom_art = MagicMock()
    comp_fab = MagicMock(article_composant="SEMI01")
    comp_fab.is_achete.return_value = False
    comp_fab.is_fabrique.return_value = True
    nom_art.composants = [comp_fab]

    nom_semi = MagicMock()
    nom_semi.composants = []

    def get_nom(article):
        if article == "ART001":
            return nom_art
        if article == "SEMI01":
            return nom_semi
        return None

    loader.get_nomenclature.side_effect = get_nom

    f = FeasibilityFilter()
    of = _make_of("F005", "ART001")
    result = f.of_uses_stockout_component(of, stockout_components={"SEMI01"}, loader=loader)
    assert result is False


def test_deep_achat_component_in_stockout_blocks():
    """Un composant ACHAT en rupture au niveau 2 doit bloquer l'OF (vérification récursive)."""
    loader = MagicMock()
    nom_art = MagicMock()
    comp_fab = MagicMock(article_composant="SEMI01")
    comp_fab.is_achete.return_value = False
    comp_fab.is_fabrique.return_value = True
    nom_art.composants = [comp_fab]

    nom_semi = MagicMock()
    comp_achat = MagicMock(article_composant="PIECE01")
    comp_achat.is_achete.return_value = True
    comp_achat.is_fabrique.return_value = False
    nom_semi.composants = [comp_achat]

    def get_nom(article):
        if article == "ART001":
            return nom_art
        if article == "SEMI01":
            return nom_semi
        return None

    loader.get_nomenclature.side_effect = get_nom

    f = FeasibilityFilter()
    of = _make_of("F006", "ART001")
    result = f.of_uses_stockout_component(of, stockout_components={"PIECE01"}, loader=loader)
    assert result is True
