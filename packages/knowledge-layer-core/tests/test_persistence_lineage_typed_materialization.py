from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize
from prepared_knowledge_runtime.query import KnowledgeLayerQuery
from prepared_knowledge_runtime import ForeignDataPersistenceQueryService


def _evidence(root: Path) -> dict:
    evidence_root = root / "evidence"
    payload = evidence_root / "persistence-lineage-payload" / "compact"
    payload.mkdir(parents=True)
    values = {
        "source_to_storage_lineage.json": [
            {
                "source_to_storage_lineage_id": "s2s-1",
                "storage_access_id": "access-should-not-own-lineage-identity",
                "source_kind": "kafka_consumed",
                "source_operation": "CustomerConsumer.onReceive",
                "source_payload": "CustomerEvent",
                "source_field": "id",
                "storage_object": "customer",
                "storage_field": "id",
                "lineage_status": "confirmed",
                "evidence_maturity_level": "confirmed",
                "evidence_maturity_dimensions": {"source_boundary": "confirmed"},
            }
        ],
        "storage_to_access_lineage.json": [
            {
                "storage_to_access_lineage_id": "s2a-1",
                "storage_object": "customer",
                "storage_field": "id",
                "response_field": "id",
            }
        ],
        "persistent_writes.json": [
            {"persistent_write_id": "write-1", "storage_object": "customer"}
        ],
        "storage_accesses.json": [
            {"storage_access_id": "read-1", "storage_object": "customer"}
        ],
        "storage_lineage_gaps.json": [],
        "stored_field_to_response_field_mappings.json": [
            {
                "stored_field_to_response_field_mapping_id": "map-1",
                "storage_field": "id",
                "response_field": "id",
            }
        ],
    }
    descriptors = []
    for name, value in values.items():
        path = payload / name
        path.write_text(json.dumps(value), encoding="utf-8")
        descriptors.append(
            {
                "artifact_name": name,
                "relative_path": path.relative_to(evidence_root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "section": None,
            }
        )
    envelope = evidence_root / "persistence-lineage-evidence.json"
    content = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_id": "persistence-demo",
        "artifact_kind": "persistence-lineage-evidence",
        "schema_version": "persistence-lineage-evidence/v1",
        "content_fingerprint": "persistence-fp",
        "source_snapshot": {"source_id": "demo", "fingerprint": "source-fp"},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {},
        "payload": {
            "repository_identity": {"repo_id": "demo"},
            "artifacts": descriptors,
        },
    }
    envelope.write_text(json.dumps(content), encoding="utf-8")
    return {
        "artifact_id": content["artifact_id"],
        "artifact_kind": content["artifact_kind"],
        "schema_version": content["schema_version"],
        "content_fingerprint": content["content_fingerprint"],
        "location": {"kind": "file", "path": str(envelope)},
    }


def test_persistence_lineage_materializes_from_typed_evidence(tmp_path: Path) -> None:
    output = tmp_path / "knowledge"
    result = materialize(
        {
            "schema_version": "knowledge_materialization_request/v1",
            "materialization_id": "persistence-lineage",
            "scope_id": "demo",
            "inputs": {
                "evidence_artifacts": [_evidence(tmp_path)],
                "knowledge_artifacts": [],
            },
            "parameters": {},
        },
        output,
    )
    assert result["status"] == "completed"
    assert result["published_capabilities"] == [
        "workspace.fdp-paths",
        "workspace.persistence-lineage",
    ]
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute(
            "select count(*) from subject_knowledge_record "
            "where materialization_id='persistence-lineage'"
        ).fetchone()[0] == 5
        assert con.execute(
            "select local_record_id from subject_knowledge_record "
            "where artifact_name='source_to_storage_lineage.json'"
        ).fetchone()[0] == "s2s-1"
        assert con.execute(
            "select count(*) from information_schema.columns "
            "where lower(column_name) in ('task_id','profile_id','suite_id')"
        ).fetchone()[0] == 0
    finally:
        con.close()
    query = KnowledgeLayerQuery(output / "knowledge-layer.duckdb")
    assert query.persistence_lineage_records()["total_count"] == 5
    assert query.fdp_paths(direction="source-to-storage")["total_count"] == 1
    assert query.fdp_paths(direction="storage-to-access")["total_count"] == 1

    service = ForeignDataPersistenceQueryService(output / "knowledge-layer.duckdb")
    all_paths = service.list_paths()
    assert all_paths.summary["direction_counts"] == {"source-to-storage": 1, "storage-to-access": 1}
    assert all_paths.page.total_count == 2
    paths = service.list_paths(direction="source-to-storage")
    assert paths.items[0]["source_interpretation"] == {
        "status": "confirmed_external_ingress",
        "source_kind": "kafka_consumed",
        "source_system": None,
        "business_source_decision": "not_made_by_analyzer",
        "reason": "typed persistence evidence confirms an external/runtime ingress boundary",
        "source_payload": "CustomerEvent",
        "named_source_system_required_for_technical_ingress": False,
        "named_source_system_required_for_governance": True,
    }
