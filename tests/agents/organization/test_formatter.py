import io
import math
from contextlib import redirect_stdout

def test_format_organization_table():
    """Format results as console table"""
    from src.agents.organization.formatter import format_organization_table
    from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType

    result = PosteChargeResult(
        poste="PP_830",
        charge_s1=25.0,
        charge_s2=35.0,
        charge_s3=45.0,
        charge_s4=60.0,
        trend=TrendType.UPWARD,
        slope=11.67,
        recommended_org=OrganizationType(type="2x8", hours=70.0),
        charge_treated=25.0,
        coverage_pct=100.0
    )

    results = {"PP_830": result}

    # Capture stdout
    f = io.StringIO()
    with redirect_stdout(f):
        format_organization_table(results)
    output = f.getvalue()

    # Verify content
    assert "PP_830" in output
    assert "25.0h" in output
    assert ("⬆️" in output or "UPWARD" in output or "Hausse" in output)
    assert "2x8" in output


def test_partial_org_shows_number_of_days():
    """Quand l'organisation est 'partial', afficher le nombre précis de jours (ex: 2J (1×8))."""
    from src.agents.organization.formatter import format_organization_table
    from src.agents.organization.models import PosteChargeResult, TrendType, OrganizationType

    charge_s1 = 10.0  # ceil(10 / 7) = 2 jours
    result = PosteChargeResult(
        poste="PP_153",
        charge_s1=charge_s1,
        charge_s2=8.0,
        charge_s3=6.0,
        charge_s4=4.0,
        trend=TrendType.DOWNWARD,
        recommended_org=OrganizationType(type="partial", hours=17.5),
        charge_treated=charge_s1,
        coverage_pct=100.0
    )

    f = io.StringIO()
    with redirect_stdout(f):
        format_organization_table({"PP_153": result})
    output = f.getvalue()

    days = math.ceil(charge_s1 / 7.0)  # = 2
    assert f"{days}J" in output, f"Expected '{days}J' in output for charge {charge_s1}h, got: {output}"
    assert "partial" not in output.lower(), "Le mot 'partial' ne doit pas apparaître brut"
