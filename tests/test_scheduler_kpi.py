from datetime import date

from src.scheduler.kpi import compute_kpis, load_weights
from src.scheduler.models import CandidateOF, ScheduledTask


def test_load_weights_renormalizes_values(tmp_path):
    weights_file = tmp_path / "weights.json"
    weights_file.write_text('{"w1": 7, "w2": 2, "w3": 1}', encoding="utf-8")

    weights = load_weights(weights_file)

    assert weights == {"w1": 0.7, "w2": 0.2, "w3": 0.1}


def test_compute_kpis_returns_normalized_score():
    candidates = [
        CandidateOF(
            num_of="OF1",
            article="ART1",
            description="Test",
            line="PP_830",
            due_date=date(2026, 4, 6),
            charge_hours=7.0,
            quantity=10,
        )
    ]
    tasks = [
        ScheduledTask(
            num_of="OF1",
            article="ART1",
            line="PP_830",
            scheduled_day=date(2026, 4, 6),
            start_hour=0.0,
            end_hour=7.0,
            charge_hours=7.0,
            due_date=date(2026, 4, 6),
            quantity=10,
            comfortable=True,
            kind="direct",
        )
    ]

    kpis = compute_kpis(candidates, tasks, [date(2026, 4, 6)], deviations=0, weights={"w1": 0.7, "w2": 0.2, "w3": 0.1})

    assert kpis.taux_service == 1.0
    assert kpis.score == 0.75
