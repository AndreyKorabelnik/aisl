from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from static_analysis_runner.cli import app
from static_analysis_runner.execution_result_contracts import (
    build_analysis_execution_result_catalog,
    render_analysis_execution_result_markdown,
)

runner = CliRunner()


def _fingerprint(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _core_payload() -> dict:
    payload = {
        "schema_version": "core_target_analysis_contracts/v1",
        "core_version": "0.43.22",
        "contracts": {
            "foundation": {"contract_id": "core_foundation_contract/v1"},
            "evidence_analyzer": {"contract_id": "core_evidence_analyzer_contract/v1"},
            "evidence_artifact": {"contract_id": "core_evidence_artifact_contract/v1"},
        },
    }
    payload["contracts_fingerprint"] = _fingerprint(payload)
    return payload


def _klc_payload() -> dict:
    payload = {
        "schema_version": "knowledge_materialization_catalog/v3",
        "klc_version": "0.53.9",
        "contract": {"contract_id": "knowledge_materialization_contract/v3"},
        "evidence_routing_contract": {"contract_id": "evidence_semantic_routing/v1"},
        "summary": {
            "materialization_count": 21,
            "runtime_registered_materialization_count": 19,
            "runtime_unregistered_materialization_count": 2,
        },
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def test_build_execution_result_contract_records_target_ownership_and_current_gaps():
    payload = build_analysis_execution_result_catalog(_core_payload(), _klc_payload())

    assert payload["schema_version"] == "analysis_execution_result_catalog/v1"
    assert payload["contract"]["contract_id"] == "analysis_execution_result_contract/v1"
    assert payload["contract"]["owner"] == "static-analysis-runner"
    evidence = payload["contract"]["required_sections"]["evidence_artifacts"]
    assert evidence["semantic_identity"] == ["artifact_kind", "schema_version"]
    assert "task_id" in evidence["forbidden_semantic_selectors"]
    assert payload["summary"] == {
        "current_manifest_variant_count": 3,
        "fully_compliant_manifest_count": 3,
        "manifest_variants_with_any_typed_registry_count": 3,
        "manifest_variants_with_direct_or_indirect_foundation_identity_count": 0,
        "task_semantic_coupled_variant_count": 0,
        "klc_materialization_count": 21,
        "klc_runtime_registered_materialization_count": 19,
        "klc_runtime_unregistered_materialization_count": 2,
    }


def test_revised_sequence_records_completed_runtime_and_release_validation():
    payload = build_analysis_execution_result_catalog(_core_payload(), _klc_payload())
    sequence = payload["planning_conclusions"]["revised_sequence"]

    assert sequence[0]["step"] == "generic_knowledge_materialization_executor/v1"
    assert sequence[0]["status"] == "completed"
    assert sequence[1]["step"] == "generic_core_evidence_runtime_and_executor"
    assert sequence[1]["status"] == "completed"
    assert sequence[2]["step"] == "knowledge_execution_plan/v1"
    assert sequence[2]["status"] == "completed"
    assert sequence[3]["step"] == "knowledge_execute_and_result/v1"
    assert sequence[3]["status"] == "completed"
    assert sequence[4]["step"] == "consumer_release_validation"
    assert sequence[4]["status"] == "next"
    assert "portfolio topology and Islands v1" in payload["planning_conclusions"]["explicitly_deferred"]


def test_catalog_is_deterministic_and_markdown_mentions_main_finding():
    first = build_analysis_execution_result_catalog(_core_payload(), _klc_payload())
    second = build_analysis_execution_result_catalog(_core_payload(), _klc_payload())

    assert first == second
    assert first["catalog_fingerprint"] == second["catalog_fingerprint"]
    markdown = render_analysis_execution_result_markdown(first)
    assert "one installed product runtime" in markdown
    assert "generic_knowledge_materialization_executor/v1" in markdown


def test_rejects_modified_core_target_contracts():
    core = _core_payload()
    core["core_version"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        build_analysis_execution_result_catalog(core, _klc_payload())


def test_rejects_modified_klc_materialization_catalog():
    klc = _klc_payload()
    klc["summary"]["task_semantic_route_count"] = 1
    with pytest.raises(ValueError, match="fingerprint"):
        build_analysis_execution_result_catalog(_core_payload(), klc)


def test_cli_exports_json_and_markdown(tmp_path: Path):
    core = tmp_path / "core.json"
    klc = tmp_path / "klc.json"
    output = tmp_path / "execution.json"
    markdown = tmp_path / "execution.md"
    core.write_text(json.dumps(_core_payload()), encoding="utf-8")
    klc.write_text(json.dumps(_klc_payload()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "execution-result-contract",
            "--core-target-contracts",
            str(core),
            "--klc-materialization-contracts",
            str(klc),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["schema_version"] == "analysis_execution_result_catalog/v1"
    assert summary["next_step"] == "consumer_release_validation"
    assert output.is_file()
    assert markdown.is_file()
