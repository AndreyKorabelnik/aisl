from pathlib import Path

from aisl_reporting.cli import _request


def _knowledge(profile: str, audience: str | None = None):
    return _request(
        profile=profile,
        audience=audience,
        detail_level="standard" if audience is None else "detailed",
        focus=[],
        output_name="report.md",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
    )


def test_system_description_defaults_to_business_audience():
    assert _knowledge("system-description/v1").audience == "business"


def test_other_reports_default_to_architecture_audience():
    assert _knowledge("data-model-report/v1").audience == "architecture"


def test_explicit_audience_is_preserved():
    assert _knowledge("system-description/v1", "engineering").audience == "engineering"


def test_sql_source_inventory_report_defaults_to_business_audience():
    assert _knowledge("sql-source-inventory-report/v1").audience == "business"

