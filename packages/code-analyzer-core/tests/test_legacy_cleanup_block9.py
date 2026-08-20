from __future__ import annotations

import inspect
import json
from pathlib import Path

import code_analyzer_core.repository_contract as repository_contract
from code_evidence import access, commands
from code_evidence.catalog import load_evidence_tool_catalog


def test_old_workspace_input_contract_is_not_exposed() -> None:
    assert "workspace" not in inspect.signature(commands.export_manifest).parameters
    assert "repo_id" not in inspect.signature(commands.export_manifest).parameters
    assert "workspace_path" not in inspect.signature(access.execute_evidence_request).parameters
    assert "workspace_path" not in inspect.signature(access.execute_evidence_requests).parameters
    assert not hasattr(repository_contract, "WORKSPACE_CONTRACT_VERSION")
    assert not hasattr(repository_contract, "resolve_repository_static_output")


def test_old_workspace_evidence_tools_and_arguments_are_absent() -> None:
    catalog = load_evidence_tool_catalog()
    command_ids = {item["command_id"] for item in catalog["commands"]}
    assert {"workspace_summary", "repo_summary", "workspace_search"}.isdisjoint(command_ids)
    text = json.dumps(catalog, ensure_ascii=False)
    assert "--workspace" not in text
    for item in catalog["commands"]:
        assert "workspace_path" not in (item.get("required_args") or [])
        assert "workspace_path" not in (item.get("optional_args") or [])


def test_export_manifest_is_static_analysis_output_only(tmp_path: Path) -> None:
    out = tmp_path / "static-analysis-output"
    out.mkdir()
    (out / "facts.json").write_text('[{"evidence_id":"e1","kind":"fact"}]', encoding="utf-8")
    payload = commands.export_manifest(analysis_out=out)
    assert payload["source"] == {"static_analysis_output": str(out.resolve())}
    assert "workspace_type" not in payload
    assert payload["evidence_ids"] == ["e1"]


def test_current_source_has_no_old_workspace_layout_branch() -> None:
    command_source = inspect.getsource(commands)
    contract_source = inspect.getsource(repository_contract)
    assert "LEGACY_WORKSPACE_LAYOUT_NOT_SUPPORTED" not in command_source
    assert "LEGACY_WORKSPACE_LAYOUT_NOT_SUPPORTED" not in contract_source
    assert "workspace_manifest.json" not in command_source
    assert "if False and workspace" not in command_source
