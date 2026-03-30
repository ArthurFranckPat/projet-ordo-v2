"""Tests d'intégration légers pour le rapport d'actions dans main_s1."""

from dataclasses import dataclass
from datetime import date

from src.agents.models import AgentAction, AgentDecision
from src.algorithms.matching import MatchingResult
from src.checkers.base import FeasibilityResult
from src.main_s1 import main_s1

from .agents.tools.conftest import TODAY, make_commande, make_loader, make_of, make_stock


@dataclass
class _Args:
    """Arguments minimaux pour main_s1."""

    horizon: int = 7
    llm: bool = False
    llm_model: str = "mistral-large-latest"
    schedule: bool = False


def test_main_s1_generates_action_report(monkeypatch, tmp_path):
    """Le flux S+1 génère bien le rapport d'actions quand un OF est bloquant."""
    of_1 = make_of("OF_1", "PF_1", 3, date(2026, 3, 26))
    commande = make_commande("CMD_1", "PF_1", date(2026, 3, 24))
    loader = make_loader(
        ofs=[of_1],
        commandes=[commande],
        receptions=[],
        stocks={"COMP_X": make_stock("COMP_X", physique=0)},
    )
    loader.get_article.side_effect = lambda article: None

    feasibility = FeasibilityResult(feasible=False)
    feasibility.add_missing("COMP_X", 4)

    class FakeMatcher:
        def __init__(self, _loader, date_tolerance_days=10):
            self.loader = _loader

        def match_commandes(self, besoins):
            assert besoins == [commande]
            return [MatchingResult(commande=commande, of=of_1, matching_method="MTS")]

    class FakeProjectedChecker:
        def __init__(self, _loader):
            self.loader = _loader

        def check_all_ofs(self, ofs):
            assert ofs == [of_1]
            return {"OF_1": feasibility}

    class FakeAgentEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def evaluate_pre_allocation(self, **_kwargs):
            return AgentDecision(
                action=AgentAction.ACCEPT_AS_IS,
                reason="OK",
                metadata={"weighted_score": 1.0},
            )

        def evaluate_post_allocation(self, **_kwargs):
            return AgentDecision(
                action=AgentAction.REJECT,
                reason="Blocage composant",
                metadata={"weighted_score": 0.1},
            )

    written = {}

    def fake_write_action_report_markdown(report, _output_path):
        real_path = tmp_path / "s1_action_report.md"
        written["path"] = real_path
        from src.reports import write_action_report_markdown as real_writer
        real_writer(report, str(real_path))

    monkeypatch.setattr("src.main_s1.CommandeOFMatcher", FakeMatcher)
    monkeypatch.setattr("src.main_s1.ProjectedChecker", FakeProjectedChecker)
    monkeypatch.setattr("src.main_s1.AgentEngine", FakeAgentEngine)
    monkeypatch.setattr("src.main_s1.format_rapport_s1", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.main_s1.render_action_report_console", lambda report: None)
    monkeypatch.setattr("src.main_s1.write_action_report_markdown", fake_write_action_report_markdown)
    monkeypatch.setattr("src.agents.reports.DecisionReporter.generate_markdown_report", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.agents.reports.DecisionReporter.generate_json_report", lambda *args, **kwargs: None)

    args = _Args()
    main_s1(args, loader, include_previsions=False)

    content = written["path"].read_text(encoding="utf-8")
    assert "COMP_X" in content
    assert "Rapport d'actions appro S+1" in content
    assert "Actions appro par fournisseur / CA" in content
