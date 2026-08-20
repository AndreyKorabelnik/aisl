from pathlib import Path

import pytest
import yaml

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.pipeline import (
    _renderer_prompt_with_common_policy,
    _renderer_prompt_with_explicit_instructions,
    _required_headings,
)
from aisl_reporting.profile import load_profile


PROFILES = (
    ("system-description", "v1"),
    ("data-model-report", "v1"),
    ("declared-data-model-report", "v1"),
    ("reference-data-report", "v1"),
    ("foreign-data-persistence-report", "v1"),
    ("workspace-interaction", "v1"),
    ("sql-source-inventory-report", "v1"),
    ("sql-change-analysis-report", "v1"),
    ("workspace-sql-catalog-report", "v1"),
    ("observed-storage-usage-report", "v1"),
)

APPENDICES = (
    "Приложение A. Полнота анализа и ограничения доказательности",
    "Приложение B. Неоднозначности и вопросы для уточнения",
    "Приложение C. Технические доказательства и provenance",
)


@pytest.mark.parametrize(("report_type", "report_version"), PROFILES)
def test_common_policy_and_contract_structure_are_composed_for_every_report_profile(
    report_type: str,
    report_version: str,
) -> None:
    request = ReportRequest(
        report_type=report_type,
        report_version=report_version,
        api_url="http://knowledge-api.test",
        system_id="fixture",
        audience="architecture",
    )
    profile = load_profile(request.profile_id)
    contract = yaml.safe_load(profile.text("report-contract.yaml")) or {}
    prompt = _renderer_prompt_with_common_policy(profile.text("renderer-prompt.md"), contract, request)

    assert prompt.count("# Общая редакционная политика доказательных отчётов") == 1
    assert prompt.count("# Обязательная структура текущего профиля") == 1
    assert prompt.index("# Общая редакционная политика") < prompt.index("# Профильные правила")

    structure = prompt.split("# Обязательная структура текущего профиля", 1)[1].split("# Профильные правила", 1)[0]
    positions = []
    for heading in _required_headings(contract, request):
        token = f"`{heading}`"
        assert token in structure
        positions.append(structure.index(token))
    assert positions == sorted(positions)
    if report_type in {"system-description", "data-model-report", "declared-data-model-report", "reference-data-report", "foreign-data-persistence-report", "workspace-interaction", "sql-source-inventory-report"}:
        assert tuple(contract["required_headings"][-3:]) == APPENDICES


def test_business_specific_heading_is_first_in_composed_structure() -> None:
    request = ReportRequest(
        report_type="system-description",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        audience="business",
    )
    profile = load_profile(request.profile_id)
    contract = yaml.safe_load(profile.text("report-contract.yaml")) or {}
    headings = _required_headings(contract, request)
    assert headings[0] == "О системе"
    assert headings[1] == "Краткий вывод"


def test_explicit_instruction_block_remains_last(tmp_path: Path) -> None:
    rule = tmp_path / "selected-profile-rule.md"
    rule.write_text("Дополнительное правило выбранного профиля.", encoding="utf-8")
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        instruction_files=(rule,),
    )
    profile = load_profile(request.profile_id)
    contract = yaml.safe_load(profile.text("report-contract.yaml")) or {}
    base = _renderer_prompt_with_common_policy(profile.text("renderer-prompt.md"), contract, request)
    prompt = _renderer_prompt_with_explicit_instructions(base, request)
    assert prompt.rfind("# Явные дополнительные инструкции пользователя/профиля") > prompt.rfind("# Профильные правила")
    assert prompt.rstrip().endswith("Дополнительное правило выбранного профиля.")


def test_data_model_prompt_requires_physical_er_without_invented_edges() -> None:
    profile = load_profile("data-model-report/v1")
    prompt = profile.text("renderer-prompt.md")
    assert "Раздел `ER-диаграммы` обязателен" in prompt
    assert "sections.diagrams.physical_er.tables" in prompt
    assert "sections.diagrams.physical_er.relationships" in prompt
    assert "sections.diagrams.observed_usage.relationships" in prompt
    assert "physical_er.mode=entity_only" in prompt
    assert "без выдуманных рёбер" in prompt
    assert "Declared FK/explicit relationship и observed SQL/JOOQ JOIN не смешивай" in prompt
    assert "Только `physical_er.relationships`" in prompt


def test_fdp_report_uses_current_persistence_lineage_knowledge_contract() -> None:
    profile = load_profile("foreign-data-persistence-report/v1")
    requirement = profile.knowledge_requirement
    assert requirement is not None
    assert requirement.model_kind == "persistence-lineage"
    assert requirement.required_capabilities == ("workspace.fdp-paths", "workspace.persistence-lineage")
    assert "common.foreign-data-persistence" not in requirement.required_capabilities
