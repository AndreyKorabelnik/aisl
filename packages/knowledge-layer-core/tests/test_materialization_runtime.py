from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_layer_core.materialization_runtime import (
    MATERIALIZATION_EXECUTION_RESULT_SCHEMA_VERSION,
    MATERIALIZATION_REQUEST_SCHEMA_VERSION,
    MATERIALIZATION_RUNTIME_CONTRACT_ID,
    _manifest_diagnostics,
    materialize,
    registered_materialization_ids,
)
from test_code_declared_model_builder import _write_runner_input


def _request(manifest: Path) -> dict:
    run = json.loads(manifest.read_text(encoding="utf-8"))
    artifact = run["evidence_artifacts"][0]
    return {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "code-declared-data-model",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": artifact["artifact_id"],
                "artifact_kind": artifact["artifact_kind"],
                "schema_version": artifact["schema_version"],
                "content_fingerprint": artifact["content_fingerprint"],
                "registration_manifest_path": str(manifest),
            }],
            "knowledge_artifacts": [],
        },
        "parameters": {},
    }


def test_generic_runtime_dispatches_registered_materialization(tmp_path: Path) -> None:
    manifest = _write_runner_input(tmp_path, "repo-a")
    output = tmp_path / "knowledge"
    result = materialize(_request(manifest), output)

    assert result["schema_version"] == MATERIALIZATION_EXECUTION_RESULT_SCHEMA_VERSION
    assert result["runtime_contract_id"] == MATERIALIZATION_RUNTIME_CONTRACT_ID
    assert result["materialization_id"] == "code-declared-data-model"
    assert result["status"] == "completed"
    assert result["published_capabilities"]
    assert len(result["knowledge_artifacts"]) == 1
    artifact = result["knowledge_artifacts"][0]
    assert artifact["model_kind"] == "code-declared-data-model"
    assert artifact["schema_version"] == "code-declared-data-model/v1"
    assert Path(result["output"]["manifest_path"]).is_file()



def test_product_identity_is_stable_across_repeated_executions(tmp_path: Path) -> None:
    manifest = _write_runner_input(tmp_path, "repo-stable")
    request = _request(manifest)

    first = materialize(request, tmp_path / "knowledge-first")
    second = materialize(request, tmp_path / "knowledge-second")

    first_artifact = first["knowledge_artifacts"][0]
    second_artifact = second["knowledge_artifacts"][0]
    assert first_artifact["content_fingerprint"] == second_artifact["content_fingerprint"]
    assert first_artifact["artifact_id"] == second_artifact["artifact_id"]
    assert first["started_at"] != second["started_at"] or first["completed_at"] != second["completed_at"]
    first_manifest = json.loads(Path(first["output"]["manifest_path"]).read_text(encoding="utf-8"))
    assert "started_at" not in (first_manifest.get("metadata") or {})
    assert "completed_at" not in (first_manifest.get("metadata") or {})
    for item in first_manifest.get("source_evidence") or []:
        assert "runner_manifest" not in item
        assert "artifact_path" not in item


def test_runtime_registry_is_explicit_and_generic() -> None:
    assert registered_materialization_ids() == ("code-declared-data-model", "cross-artifact-data-model-mapping", "cross-repository-value-flow", "data-model-attribute-extension-context", "effective-data-model", "interaction-field-contracts", "logical-physical-mapping", "logical-storage-mapping", "model-storage-semantics", "observed-storage-usage", "persistence-lineage", "physical-model", "reference-data", "repository-inventory", "repository-value-flow", "sql-analysis", "sql-target-source-mapping", "system-description", "system-interactions", "workspace-sql-catalog")


def test_unknown_materialization_fails_without_fallback(tmp_path: Path) -> None:
    request = {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "unknown-knowledge",
        "scope_id": "scope-a",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": []},
    }
    with pytest.raises(ValueError, match="not registered"):
        materialize(request, tmp_path / "knowledge")


def test_missing_required_evidence_fails_before_handler(tmp_path: Path) -> None:
    request = {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "code-declared-data-model",
        "scope_id": "scope-a",
        "inputs": {"evidence_artifacts": [], "knowledge_artifacts": []},
    }
    with pytest.raises(ValueError, match="missing required evidence"):
        materialize(request, tmp_path / "knowledge")


def test_manifest_diagnostics_are_generic_runtime_diagnostics() -> None:
    manifest = {
        "metadata": {
            "diagnostics": [{
                "code": "example_gap",
                "severity": "warning",
                "message": "Visible partial result",
            }]
        }
    }
    assert _manifest_diagnostics(manifest) == [{
        "code": "example_gap",
        "severity": "warning",
        "message": "Visible partial result",
    }]
    assert _manifest_diagnostics({"metadata": {}}) == []
