from pathlib import Path

import tomllib

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profile import load_profile


def test_distribution_has_no_framework_runtime_dependency() -> None:
    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    deps = {str(item).split("=", 1)[0].split("<", 1)[0].split(">", 1)[0].strip().lower() for item in data["project"]["dependencies"]}
    assert "evidence-common" not in deps
    assert "code-analyzer-core" not in deps
    assert "static-analysis-runner" not in deps
    assert "knowledge-layer-core" not in deps
    assert "knowledge-control-plane" not in deps
    assert "knowledge-api" not in deps


def test_request_is_aisl_revision_only() -> None:
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="system-a",
        revision_id="rev-a",
    )
    payload = request.to_dict()
    assert payload["knowledge_api"]["revision_id"] == "rev-a"
    assert "input_artifact" not in payload
    assert "input_kind" not in payload


def test_all_registered_profiles_require_published_knowledge() -> None:
    for profile_id in [
        "system-description/v1",
        "data-model-report/v1",
        "declared-data-model-report/v1",
        "reference-data-report/v1",
        "foreign-data-persistence-report/v1",
        "workspace-interaction/v1",
        "sql-source-inventory-report/v1",
        "sql-change-analysis-report/v1",
        "workspace-sql-catalog-report/v1",
        "observed-storage-usage-report/v1",
    ]:
        profile = load_profile(profile_id)
        assert profile.knowledge_requirement is not None
