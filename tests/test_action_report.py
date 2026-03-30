"""Tests pour le rapport d'actions appro S+1."""

from datetime import date

from src.algorithms.matching import MatchingResult
from src.checkers.base import FeasibilityResult
from src.models.article import Article, TypeApprovisionnement
from src.reports import build_action_report, write_action_report_markdown

from .agents.tools.conftest import (
    TODAY,
    make_commande,
    make_loader,
    make_of,
    make_reception,
    make_stock,
)


def _make_feasibility(**missing_components):
    result = FeasibilityResult(feasible=False)
    for article, quantity in missing_components.items():
        result.add_missing(article, quantity)
    return result


def test_build_action_report_aggregates_and_prioritizes_components():
    """Agrège les ruptures d'un même composant et les trie par impact client."""
    of_1 = make_of("OF_A", "PF_A", 3, date(2026, 3, 26))
    of_2 = make_of("OF_B", "PF_B", 3, date(2026, 3, 27))
    cmd_1 = make_commande("CMD_1", "PF_A", date(2026, 3, 24))
    cmd_2 = make_commande("CMD_2", "PF_B", date(2026, 3, 25))

    loader = make_loader(
        ofs=[of_1, of_2],
        commandes=[cmd_1, cmd_2],
        receptions=[
            make_reception("COMP_A", date(2026, 3, 22), qte=10, fournisseur="SUP_A"),
        ],
        stocks={
            "COMP_A": make_stock("COMP_A", physique=0),
            "COMP_B": make_stock("COMP_B", physique=0),
        },
    )
    loader.articles = {
        "COMP_A": Article("COMP_A", "Composant A", "AP", TypeApprovisionnement.ACHAT, 7),
        "COMP_B": Article("COMP_B", "Composant B", "AP", TypeApprovisionnement.ACHAT, 7),
    }
    loader.get_article.side_effect = lambda article: loader.articles.get(article)

    matching_results = [
        MatchingResult(commande=cmd_1, of=of_1, matching_method="MTS"),
        MatchingResult(commande=cmd_2, of=of_2, matching_method="MTS"),
    ]
    feasibility_results = {
        "OF_A": _make_feasibility(COMP_A=5, COMP_B=2),
        "OF_B": _make_feasibility(COMP_A=3),
    }

    report = build_action_report(loader, matching_results, feasibility_results, reference_date=TODAY)

    assert [line.article_composant for line in report.component_lines] == ["COMP_A", "COMP_B"]

    comp_a = report.component_lines[0]
    assert comp_a.description == "Composant A"
    assert comp_a.missing_qty_total == 8
    assert comp_a.nb_ofs_impactes == 2
    assert comp_a.nb_commandes_impactees == 2
    assert comp_a.date_expedition_la_plus_proche == date(2026, 3, 24)
    assert comp_a.niveau_action == "RETARD_FOURNISSEUR"

    comp_b = report.component_lines[1]
    assert comp_b.niveau_action == "AUCUNE_COUVERTURE"
    assert report.impacted_ofs == 2
    assert report.impacted_commandes == 2


def test_build_action_report_classifies_all_action_levels():
    """Classe correctement les composants selon la situation appro."""
    of_1 = make_of("OF_1", "PF_1", 3, date(2026, 3, 28))
    cmd_1 = make_commande("CMD_1", "PF_1", date(2026, 3, 25))

    loader = make_loader(
        ofs=[of_1],
        commandes=[cmd_1],
        receptions=[
            make_reception("COMP_RET", date(2026, 3, 20), qte=10, fournisseur="SUP_1"),
            make_reception("COMP_TARD", date(2026, 3, 29), qte=10, fournisseur="SUP_2"),
            make_reception("COMP_OK", date(2026, 3, 24), qte=10, fournisseur="SUP_3"),
        ],
        stocks={
            "COMP_RET": make_stock("COMP_RET", physique=0),
            "COMP_TARD": make_stock("COMP_TARD", physique=0),
            "COMP_NONE": make_stock("COMP_NONE", physique=0),
            "COMP_OK": make_stock("COMP_OK", physique=0),
        },
    )
    loader.get_article.side_effect = lambda article: None

    matching_results = [MatchingResult(commande=cmd_1, of=of_1, matching_method="MTS")]
    feasibility_results = {
        "OF_1": _make_feasibility(
            COMP_RET=1,
            COMP_TARD=1,
            COMP_NONE=1,
            COMP_OK=1,
        )
    }

    report = build_action_report(loader, matching_results, feasibility_results, reference_date=TODAY)
    levels = {line.article_composant: line.niveau_action for line in report.component_lines}

    assert levels == {
        "COMP_RET": "RETARD_FOURNISSEUR",
        "COMP_TARD": "COUVERTURE_TARDIVE",
        "COMP_NONE": "AUCUNE_COUVERTURE",
        "COMP_OK": "SURVEILLANCE",
    }


def test_build_action_report_groups_supplier_actions():
    """Regroupe les lignes d'exécution par fournisseur / commande achat."""
    of_1 = make_of("OF_1", "PF_1", 3, date(2026, 3, 26))
    of_2 = make_of("OF_2", "PF_2", 3, date(2026, 3, 27))
    of_3 = make_of("OF_3", "PF_3", 3, date(2026, 3, 28))
    cmd_1 = make_commande("CMD_1", "PF_1", date(2026, 3, 24))
    cmd_2 = make_commande("CMD_2", "PF_2", date(2026, 3, 25))
    cmd_3 = make_commande("CMD_3", "PF_3", date(2026, 3, 26))

    receptions = [
        make_reception("COMP_A", date(2026, 3, 22), qte=5, fournisseur="SUP_X"),
        make_reception("COMP_C", date(2026, 3, 24), qte=5, fournisseur="SUP_X"),
    ]
    receptions[0].num_commande = "CA_X"
    receptions[1].num_commande = "CA_X"

    loader = make_loader(
        ofs=[of_1, of_2, of_3],
        commandes=[cmd_1, cmd_2, cmd_3],
        receptions=receptions,
        stocks={
            "COMP_A": make_stock("COMP_A", physique=0),
            "COMP_B": make_stock("COMP_B", physique=0),
            "COMP_C": make_stock("COMP_C", physique=0),
        },
    )
    loader.get_article.side_effect = lambda article: None

    matching_results = [
        MatchingResult(commande=cmd_1, of=of_1, matching_method="MTS"),
        MatchingResult(commande=cmd_2, of=of_2, matching_method="MTS"),
        MatchingResult(commande=cmd_3, of=of_3, matching_method="MTS"),
    ]
    feasibility_results = {
        "OF_1": _make_feasibility(COMP_A=2),
        "OF_2": _make_feasibility(COMP_B=3),
        "OF_3": _make_feasibility(COMP_C=1),
    }

    report = build_action_report(loader, matching_results, feasibility_results, reference_date=TODAY)
    supplier_lines = {
        (line.fournisseur, line.num_commande_achat): line
        for line in report.supplier_lines
    }

    supplier_line = supplier_lines[("SUP_X", "CA_X")]
    assert supplier_line.nb_components == 2
    assert supplier_line.articles_concernes == ["COMP_A", "COMP_C"]
    assert supplier_line.nb_commandes_impactees == 2
    assert "Relancer" in supplier_line.action_recommandee

    no_cover_line = supplier_lines[("SANS_FOURNISSEUR", "APPRO SANS CA OUVERTE")]
    assert no_cover_line.articles_concernes == ["COMP_B"]


def test_write_action_report_markdown_contains_expected_sections(tmp_path):
    """Le rendu Markdown expose les deux vues et les composants sans couverture."""
    of_1 = make_of("OF_1", "PF_1", 3, date(2026, 3, 26))
    cmd_1 = make_commande("CMD_1", "PF_1", date(2026, 3, 24))

    loader = make_loader(
        ofs=[of_1],
        commandes=[cmd_1],
        receptions=[],
        stocks={"COMP_X": make_stock("COMP_X", physique=0)},
    )
    loader.get_article.side_effect = lambda article: None

    report = build_action_report(
        loader,
        [MatchingResult(commande=cmd_1, of=of_1, matching_method="MTS")],
        {"OF_1": _make_feasibility(COMP_X=4)},
        reference_date=TODAY,
    )

    output_path = tmp_path / "report.md"
    write_action_report_markdown(report, str(output_path))
    content = output_path.read_text(encoding="utf-8")

    assert "# Rapport d'actions appro S+1" in content
    assert "## Composants critiques" in content
    assert "## Actions appro par fournisseur / CA" in content
    assert "## Composants sans couverture identifiée" in content
    assert "COMP_X" in content
    assert "APPRO SANS CA OUVERTE" in content


def test_write_action_report_markdown_empty_report(tmp_path):
    """Le rapport vide reste explicite et sans faux positif."""
    loader = make_loader()
    report = build_action_report(loader, [], {}, reference_date=TODAY)

    output_path = tmp_path / "report.md"
    write_action_report_markdown(report, str(output_path))
    content = output_path.read_text(encoding="utf-8")

    assert "Aucun composant bloquant détecté sur le plan S+1." in content
    assert "Aucune action requise." in content
