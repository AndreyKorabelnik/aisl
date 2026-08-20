from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_api.contract_v1.runtime import KnowledgeApiRuntimeError
from knowledge_api.publication import build_publication_request, stable_fingerprint
from tests.execution_fixtures import KnowledgeArtifactSpec, write_execution_result


def test_execution_publication_builder_uses_completed_result(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    execution = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=database,
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model",),
            )
        ],
        profile_id="effective-profile",
        scope_id="ucp",
    )
    request, warnings = build_publication_request(
        execution_result=execution,
        labels=["data-model"],
        metadata={},
        activate=True,
    )
    assert warnings == []
    assert request.execution_result.schema_version == "knowledge_execution_result/v2"
    assert request.execution_result.media_type == "application/json"
    assert request.execution_result.byte_size == execution.stat().st_size
    assert request.labels == ["data-model"]


def test_execution_publication_builder_rejects_invalid_fingerprint(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    execution = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=database,
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model",),
            )
        ],
    )
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["scope"]["scope_id"] = "tampered"
    execution.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(KnowledgeApiRuntimeError) as caught:
        build_publication_request(
            execution_result=execution,
                labels=[],
            metadata={},
            activate=True,
        )
    assert caught.value.code == "knowledge_execution_result_fingerprint_invalid"


def test_execution_publication_builder_rejects_unknown_contract_property(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    execution = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=database,
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model",),
            )
        ],
    )
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["legacy_knowledge_layer"] = {"uri": "file:///forbidden.duckdb"}
    payload["result_fingerprint"] = stable_fingerprint(
        {key: value for key, value in payload.items() if key != "result_fingerprint"}
    )
    execution.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(KnowledgeApiRuntimeError) as caught:
        build_publication_request(
            execution_result=execution,
                labels=[],
            metadata={},
            activate=True,
        )

    assert caught.value.code == "knowledge_execution_result_contract_invalid"
    assert caught.value.details["validator"] == "additionalProperties"


def test_stable_fingerprint_is_order_independent_for_json_objects() -> None:
    assert stable_fingerprint({"a": 1, "b": 2}) == stable_fingerprint({"b": 2, "a": 1})


def test_execution_publication_validates_exact_external_dependency_registry(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    execution = write_execution_result(
        tmp_path,
        [KnowledgeArtifactSpec(
            database=database,
            model_kind="effective-data-model",
            schema_version="effective-data-model/v1",
            materialization_id="effective-data-model",
            capabilities=("common.effective-data-model",),
        )],
    )
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["materialization_executions"][0]["input_knowledge_artifact_ids"] = ["prior-code-model"]
    payload["external_knowledge_artifacts"] = [{
        "artifact_id": "prior-code-model",
        "model_kind": "code-declared-data-model",
        "schema_version": "code-declared-data-model/v1",
        "source_materialization_id": "code-declared-data-model",
        "content_fingerprint": "prior-content-fingerprint",
        "source_system_id": "source-system",
        "source_revision_id": "rev-source-1",
        "published_capabilities": ["common.code-declared-data-model"],
    }]
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload), encoding="utf-8")

    request, warnings = build_publication_request(
        execution_result=execution,
        labels=[],
        metadata={},
        activate=True,
    )
    assert warnings == []
    assert request.execution_result.schema_version == "knowledge_execution_result/v2"

    payload["external_knowledge_artifacts"] = []
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(KnowledgeApiRuntimeError) as caught:
        build_publication_request(
            execution_result=execution,
                labels=[],
            metadata={},
            activate=True,
        )
    assert caught.value.code == "knowledge_dependency_unresolved"
