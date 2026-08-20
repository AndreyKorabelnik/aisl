from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.materialization_runtime import materialize
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


CAPABILITIES = ("workspace.fdp-paths", "workspace.persistence-lineage")


def _typed_evidence(root: Path) -> dict:
    evidence_root = root / "evidence"
    payload = evidence_root / "persistence-lineage-payload" / "compact"
    payload.mkdir(parents=True)
    values = {
        "source_to_storage_lineage.json": [
            {
                "source_to_storage_lineage_id": "s2s-1",
                "source_kind": "kafka_consumed",
                "source_operation": "CustomerConsumer.onReceive",
                "source_payload": "CustomerEvent",
                "source_field": "id",
                "storage_object": "CUSTOMER",
                "storage_field": "ID",
                "lineage_status": "confirmed",
                "evidence_maturity_level": "confirmed",
                "evidence_maturity_dimensions": {"source_boundary": "confirmed"},
                "evidence": [{"file": "src/CustomerConsumer.java", "line_start": 10, "line_end": 20}],
            }
        ],
        "storage_to_access_lineage.json": [
            {
                "storage_to_access_lineage_id": "s2a-1",
                "storage_object": "CUSTOMER",
                "storage_field": "ID",
                "access_boundary": "CustomerController.get",
                "lineage_status": "confirmed",
                "evidence_maturity_level": "confirmed",
                "field_mappings": [{"storage_field": "ID", "response_field": "id"}],
                "evidence": [{"file": "src/CustomerController.java", "line_start": 30, "line_end": 40}],
            }
        ],
        "persistent_writes.json": [{"persistent_write_id": "write-1", "storage_object": "CUSTOMER"}],
        "storage_accesses.json": [{"storage_access_id": "read-1", "storage_object": "CUSTOMER"}],
        "storage_lineage_gaps.json": [],
        "stored_field_to_response_field_mappings.json": [
            {"stored_field_to_response_field_mapping_id": "map-1", "storage_field": "ID", "response_field": "id"}
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
        "payload": {"repository_identity": {"repo_id": "demo"}, "artifacts": descriptors},
    }
    envelope.write_text(json.dumps(content), encoding="utf-8")
    return {
        "artifact_id": content["artifact_id"],
        "artifact_kind": content["artifact_kind"],
        "schema_version": content["schema_version"],
        "content_fingerprint": content["content_fingerprint"],
        "location": {"kind": "file", "path": str(envelope)},
    }


def _artifact(tmp_path: Path) -> Path:
    output = tmp_path / "knowledge"
    result = materialize(
        {
            "schema_version": "knowledge_materialization_request/v1",
            "materialization_id": "persistence-lineage",
            "scope_id": "client-profile",
            "inputs": {"evidence_artifacts": [_typed_evidence(tmp_path)], "knowledge_artifacts": []},
            "parameters": {},
        },
        output,
    )
    assert result["status"] == "completed"
    return output / "knowledge-layer.duckdb"


def _client(tmp_path: Path, *, capabilities: tuple[str, ...] = CAPABILITIES) -> tuple[TestClient, str]:
    artifact = _artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="persistence-lineage",
                schema_version="persistence-lineage/v1",
                materialization_id="persistence-lineage",
                capabilities=capabilities,
            )
        ],
        profile_id="persistence-lineage",
        scope_id="client-profile",
        execution_token="run-fdp",
    )
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings)))
    client.__enter__()
    assert client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "client-profile", "display_name": "Client Profile"},
    ).status_code == 201
    pub = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/revisions",
        json=publication_payload(result),
    )
    assert pub.status_code == 201, pub.text
    return client, pub.json()["revision"]["revision_id"]


def _query(client: TestClient, revision_id: str, query_kind: str, *, filters: dict | None = None):
    return client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/foreign-data-persistence/query",
        json={"revision_id": revision_id, "query_kind": query_kind, "filters": filters or {}, "max_results": 100},
    )


def test_fdp_query_surface_preserves_klc_path_and_case_semantics(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        paths = _query(client, revision_id, "list_paths", filters={"token": "CustomerEvent"})
        assert paths.status_code == 200, paths.text
        payload = paths.json()
        assert payload["revision_id"] == revision_id
        assert payload["query"]["kind"] == "list_foreign_data_persistence_paths"
        assert payload["summary"]["business_fdp_decision_assigned"] is False
        assert payload["summary"]["same_data_end_to_end_required"] is True
        assert payload["items"][0]["source_interpretation"]["status"] == "confirmed_external_ingress"
        assert payload["items"][0]["source_interpretation"]["source_system"] is None

        cases = _query(client, revision_id, "list_mechanical_cases", filters={"token": "CUSTOMER"})
        assert cases.status_code == 200, cases.text
        cp = cases.json()
        assert cp["summary"]["mechanical_bridge_only"] is True
        assert cp["summary"]["same_data_confirmed_case_count"] == 0
        assert cp["items"]
        assert all(item["business_fdp_decision"] == "not_assigned" for item in cp["items"])
        assert all(item["same_data_end_to_end_status"] == "unresolved" for item in cp["items"])

        landscape = _query(client, revision_id, "get_landscape", filters={"token": "CUSTOMER"})
        assert landscape.status_code == 200, landscape.text
        policy = landscape.json()["items"][0]["interpretation_policy"]
        assert policy["facts_only"] is True
        assert policy["business_fdp_decision_assigned"] is False
        assert policy["exact_storage_field_and_confirmed_path_pair_required"] is True
    finally:
        client.__exit__(None, None, None)


def test_fdp_guidance_is_compact_revision_bound_and_preserves_mechanical_boundary(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/foreign-data-persistence/guidance",
            params={
                "revision_id": revision_id,
                "token": "CUSTOMER",
                "path_limit": 4,
                "case_limit": 4,
                "storage_summary_limit": 4,
                "evidence_limit": 8,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["guidance_schema_version"] == "foreign-data-persistence-guidance/v1"
        assert payload["revision_id"] == revision_id
        assert payload["token"] == "CUSTOMER"
        assert payload["path_summary"]["business_fdp_decision_assigned"] is False
        assert payload["case_summary"]["mechanical_bridge_only"] is True
        # The small fixture deliberately does not prove an exact confirmed bridge;
        # the compact projection must not upgrade it merely because both sides exist.
        assert payload["case_summary"]["same_data_confirmed_case_count"] == 0
        assert payload["cases"][0]["same_data_end_to_end_status"] == "unresolved"
        assert payload["cases"][0]["business_fdp_decision"] == "not_assigned"
        assert payload["cases"][0]["source_paths"][0]["source_interpretation"]["status"] == "confirmed_external_ingress"
        assert any(path.get("access_boundary") == "CustomerController.get" for path in payload["paths"])
        assert payload["interpretation_policy"]["facts_only"] is True
        assert payload["interpretation_policy"]["exact_storage_field_and_confirmed_path_pair_required"] is True
        assert payload["projection"]["semantic_derivation"] == "none"
        assert payload["projection"]["canonical_detail_endpoint"] == "/foreign-data-persistence/query"
        assert "raw_fact" not in json.dumps(payload)
    finally:
        client.__exit__(None, None, None)


def test_fdp_query_rejects_unsupported_filters_and_requires_fdp_capability(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        invalid = _query(client, revision_id, "list_paths", filters={"business_risk": "yes"})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_foreign_data_persistence_query"
    finally:
        client.__exit__(None, None, None)

    other = tmp_path / "without-capability"
    other.mkdir()
    client, revision_id = _client(other, capabilities=("workspace.persistence-lineage",))
    try:
        unavailable = _query(client, revision_id, "list_paths")
        assert unavailable.status_code == 409
        assert unavailable.json()["code"] == "knowledge_artifact_unavailable"
    finally:
        client.__exit__(None, None, None)
