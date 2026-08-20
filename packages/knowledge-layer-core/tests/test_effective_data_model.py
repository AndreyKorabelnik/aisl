from __future__ import annotations

import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import MATERIALIZATION_REQUEST_SCHEMA_VERSION, materialize
from test_code_declared_model_builder import _write_runner_input
from test_logical_physical_mapping import (
    _code_request,
    _physical_request,
    _write_persistence_evidence,
    _write_physical_artifact,
)


def _build_lower_layers(tmp_path: Path, *, omit_explicit_names: bool = False) -> tuple[dict, dict, dict]:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    persistence = _write_persistence_evidence(runner_manifest, omit_explicit_names=omit_explicit_names)
    physical_manifest = _write_physical_artifact(tmp_path / "pdm")
    code = materialize(_code_request(runner_manifest), tmp_path / "code-model")
    physical = materialize(_physical_request(physical_manifest), tmp_path / "physical-model")
    mapping = materialize({
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "logical-physical-mapping",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": persistence["artifact_id"],
                "artifact_kind": persistence["artifact_kind"],
                "schema_version": persistence["schema_version"],
                "content_fingerprint": persistence["content_fingerprint"],
                "registration_manifest_path": str(runner_manifest),
            }],
            "knowledge_artifacts": [code["knowledge_artifacts"][0], physical["knowledge_artifacts"][0]],
        },
        "parameters": {},
    }, tmp_path / "mapping")
    return code, physical, mapping


def _effective_request(code: dict, physical: dict, mapping: dict) -> dict:
    return {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "effective-data-model",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [],
            "knowledge_artifacts": [
                code["knowledge_artifacts"][0],
                physical["knowledge_artifacts"][0],
                mapping["knowledge_artifacts"][0],
            ],
        },
        "parameters": {},
    }


def test_effective_data_model_composes_three_independent_layers(tmp_path: Path) -> None:
    code, physical, mapping = _build_lower_layers(tmp_path)
    result = materialize(_effective_request(code, physical, mapping), tmp_path / "effective")

    assert result["status"] == "completed"
    assert result["published_capabilities"] == ["common.cross-layer-data-model", "common.effective-data-model"]
    assert {(item["model_kind"], item["schema_version"]) for item in result["knowledge_artifacts"]} == {
        ("effective-data-model", "effective-data-model/v1"),
        ("model-domain-cluster-view", "model-domain-cluster-view/v1"),
    }

    connection = duckdb.connect(str(tmp_path / "effective/knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute(
            "SELECT logical_fully_qualified_name, physical_table_code, mapping_status "
            "FROM effective_data_model_entity ORDER BY logical_fully_qualified_name"
        ).fetchall() == [
            ("example.Base", "base_tbl", "matched"),
            ("example.Child", "child_tbl", "matched"),
        ]
        assert connection.execute(
            "SELECT logical_field_name, physical_column_code, mapping_status "
            "FROM effective_data_model_field ORDER BY logical_field_name"
        ).fetchall() == [
            ("id", None, "unresolved"),
            ("id", "base_id", "matched"),
            ("parent", "parent_id", "matched"),
        ]
        assert connection.execute(
            "SELECT count(*) FROM effective_data_model_gap "
            "WHERE gap_kind='inherited_field_requires_persistence_inheritance_mapping'"
        ).fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM effective_data_model_unmapped_physical_object").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM model_domain").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM model_entity_cluster").fetchone()[0] == 1
        checks = json.loads(connection.execute("SELECT checks_json FROM effective_data_model_build").fetchone()[0])
        assert checks["physical_objects_are_not_promoted_to_logical_entities"] is True
    finally:
        connection.close()


def test_unresolved_mapping_keeps_logical_and_physical_objects_separate(tmp_path: Path) -> None:
    code, physical, mapping = _build_lower_layers(tmp_path, omit_explicit_names=True)
    result = materialize(_effective_request(code, physical, mapping), tmp_path / "effective")
    assert result["status"] == "completed"

    connection = duckdb.connect(str(tmp_path / "effective/knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM effective_data_model_entity").fetchone()[0] == 2
        assert connection.execute(
            "SELECT DISTINCT layer_status FROM effective_data_model_entity ORDER BY layer_status"
        ).fetchall() == [("logical_only_unresolved_mapping",)]
        assert connection.execute(
            "SELECT count(*) FROM effective_data_model_unmapped_physical_object WHERE object_kind='table'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM effective_data_model_gap WHERE source_layer='logical_physical_mapping'"
        ).fetchone()[0] > 0
    finally:
        connection.close()
