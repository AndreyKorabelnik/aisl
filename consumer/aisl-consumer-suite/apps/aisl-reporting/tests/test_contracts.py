from pathlib import Path

import pytest

from aisl_reporting.contracts import ReportRequest


def _knowledge_request(**kwargs):
    return ReportRequest(
        report_type=kwargs.pop("report_type", "data-model-report"),
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        **kwargs,
    )


def test_report_request_has_versioned_profile_and_api_revision_source():
    request = _knowledge_request()
    assert request.profile_id == "data-model-report/v1"
    assert request.to_dict()["schema_version"] == "aisl_report_request/v1"
    assert request.to_dict()["knowledge_api"]["system_id"] == "client-profile"


def test_report_request_rejects_unsafe_output():
    with pytest.raises(ValueError):
        _knowledge_request(output_name="../report.md")


def test_report_request_dataset_representation_is_portable() -> None:
    request = _knowledge_request(revision_id="rev-1")
    payload = request.to_dataset_dict()
    assert payload["knowledge_api"] == {
        "api_url": "http://knowledge-api.test",
        "system_id": "client-profile",
        "revision_id": "rev-1",
    }


def test_data_model_renderer_prompt_preserves_generic_encoding_boundary() -> None:
    prompt = (
        Path(__file__).parents[1]
        / "aisl_reporting"
        / "profiles"
        / "data_model_report"
        / "v1"
        / "renderer-prompt.md"
    ).read_text(encoding="utf-8")
    assert "тип из `target_alias`" in prompt
    assert "ключ из `target_storage_key`" in prompt
    assert "не придумывай separator" in prompt
    assert "явно заданы дополнительной инструкцией" in prompt
    assert "Явно укажи `physical_join_confirmed=false`" in prompt


def test_report_request_explicit_instruction_files_are_portable(tmp_path: Path) -> None:
    rule = tmp_path / "storage-rule.md"
    rule.write_text("Use target alias and storage key.", encoding="utf-8")
    request = _knowledge_request(instruction_files=(rule,))
    assert request.to_dict()["instruction_files"] == [str(rule)]
    assert request.to_dataset_dict()["instruction_files"] == ["storage-rule.md"]


def test_explicit_instruction_file_is_appended_only_when_supplied(tmp_path: Path) -> None:
    from aisl_reporting.pipeline import _renderer_prompt_with_explicit_instructions

    base = "GENERIC BASE PROMPT"
    plain = _knowledge_request()
    assert _renderer_prompt_with_explicit_instructions(base, plain) == base

    rule = tmp_path / "storage-rule.md"
    rule.write_text("Normalize aliases according to the selected storage contract.", encoding="utf-8")
    explicit = _knowledge_request(instruction_files=(rule,))
    prompt = _renderer_prompt_with_explicit_instructions(base, explicit)
    assert "GENERIC BASE PROMPT" in prompt
    assert "storage-rule.md" in prompt
    assert "Normalize aliases according to the selected storage contract." in prompt
    assert "не является фактом Knowledge Layer" in prompt


def test_empty_explicit_instruction_file_is_rejected_at_prompt_build(tmp_path: Path) -> None:
    from aisl_reporting.pipeline import _renderer_prompt_with_explicit_instructions

    rule = tmp_path / "empty.md"
    rule.write_text("   ", encoding="utf-8")
    request = _knowledge_request(instruction_files=(rule,))
    with pytest.raises(ValueError, match="must not be empty"):
        _renderer_prompt_with_explicit_instructions("base", request)
