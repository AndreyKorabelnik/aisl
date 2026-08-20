from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.subject_knowledge_schema import SUBJECT_KNOWLEDGE_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


CAPABILITIES = (
    "common.system-description",
    "common.system-interfaces",
    "common.system-scenarios",
    "common.system-dependencies",
)


def _record(
    record_id: str,
    artifact_name: str,
    record_kind: str,
    local_id: str,
    ordinal: int,
    payload: dict,
) -> tuple:
    return (
        record_id,
        "src-1",
        "client-profile",
        "client-profile",
        "system-description",
        artifact_name,
        record_kind,
        local_id,
        ordinal,
        " ".join(str(value) for value in payload.values() if isinstance(value, (str, int))),
        json.dumps(payload),
    )


def _system_description_artifact(tmp_path: Path, *, capabilities: tuple[str, ...] = CAPABILITIES) -> Path:
    root = tmp_path / ("system-description" if capabilities else "system-description-without-capability")
    root.mkdir()
    path = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(SUBJECT_KNOWLEDGE_DDL)
        con.execute(
            "INSERT INTO subject_knowledge_build VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "build-1", "client-profile", "system-description", "test", "subject-knowledge-records/v1",
                "system-description-evidence/v1", "f" * 64, "complete", "2026-08-09 00:00:00",
                "2026-08-09 00:00:01", json.dumps({"subject_knowledge_record": 8}), json.dumps({}),
            ],
        )
        con.execute(
            "INSERT INTO subject_knowledge_source VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "src-1", "client-profile", "client-profile", "system-description", "evidence-1",
                "system-description-evidence", "system-description-evidence/v1", "evidence.json", "e" * 64,
                json.dumps({"source_id": "client-profile"}),
                json.dumps({"source_file_count": 42, "payload_artifact_count": 7, "missing_payload_artifact_count": 0, "coverage_status": "complete"}),
                json.dumps([]), json.dumps({}),
            ],
        )
        rows = [
            _record(
                "r-dep", "external_dependencies.json", "external_dependencies", "dep-1", 1,
                {
                    "dependency_kind": "gradle_artifact", "name": "org.springframework:spring-web:6.0",
                    "is_test_source": False, "evidence_level": "observed",
                    "evidence": [{"file": "client-profile-app/build.gradle", "line_start": 10, "line_end": 10}],
                },
            ),
            _record(
                "r-http-out", "external_dependencies.json", "external_dependencies", "out-1", 2,
                {
                    "dependency_kind": "http_outbound", "operation": "lookupOperator",
                    "endpoint_path": "/api/inf/operator/get-by-phone-number/{phone}", "is_test_source": False,
                    "evidence_level": "observed", "evidence": [{"file": "client-profile-app/src/InfoChangeServiceImpl.java", "line_start": 48, "line_end": 55}],
                },
            ),
            _record(
                "r-rest", "system_interface_catalog.json", "interfaces", "if-rest", 3,
                {
                    "interface_id": "if-rest", "operation": "updateTps", "direction": "inbound",
                    "boundary_kind": "rest_request", "protocol": "http", "endpoint_or_topic_resolved": "/tps/update",
                    "http_method": "POST", "evidence_level": "observed", "attribute_count": 2,
                    "evidence_refs": [{"file": "client-profile-app/src/TpsController.java", "line_start": 25, "line_end": 61}],
                },
            ),
            _record(
                "r-kafka", "system_interface_catalog.json", "interfaces", "if-kafka", 4,
                {
                    "interface_id": "if-kafka", "operation": "removeDevice", "direction": "inbound",
                    "boundary_kind": "kafka_consume", "protocol": "kafka", "endpoint_or_topic_resolved": "remove-device",
                    "evidence_level": "observed", "attribute_count": 1,
                    "evidence_refs": [{"file": "client-profile-app/src/RemoveDeviceConsumer.java", "line_start": 34, "line_end": 53}],
                },
            ),
            _record(
                "r-storage", "storage_usage_summaries.json", "storage_usage_summaries", "st-1", 5,
                {
                    "storage_usage_summary_id": "st-1", "storage_target": "DEVICE_LINK", "source_sets": ["main"],
                    "access_count": 3, "operation_count": 2, "read_count": 1, "write_count": 2, "mutation_count": 1,
                    "evidence_level": "observed", "evidence": [{"file": "client-profile-app/src/DeviceLinkDao.java", "line_start": 40, "line_end": 80}],
                },
            ),
            _record(
                "r-s1", "system_scenarios.json", "system_scenarios", "scenario-1", 6,
                {
                    "scenario_id": "scenario-1", "operation": "POST /tps/update", "evidence_level": "observed",
                    "entrypoints": [{"kind": "rest", "path": "/tps/update"}],
                    "external_calls": [], "storage_touches": [{"target": "DEVICE_LINK"}],
                },
            ),
            _record(
                "r-s2", "system_scenarios.json", "system_scenarios", "scenario-2", 7,
                {
                    "scenario_id": "scenario-2", "operation": "Kafka removeDevice", "evidence_level": "observed",
                    "entrypoints": [{"kind": "kafka", "topic": "remove-device"}],
                    "external_calls": [{"operation": "notify"}], "storage_touches": [],
                },
            ),
            _record(
                "r-gap", "system_scenarios.json", "system_scenarios", "scenario-gap", 8,
                {
                    "scenario_id": "scenario-gap", "operation": "GET /entrypoint-only", "evidence_level": "observed",
                    "entrypoints": [{"kind": "rest", "path": "/entrypoint-only"}], "external_calls": [], "storage_touches": [],
                },
            ),
        ]
        con.executemany("INSERT INTO subject_knowledge_record VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    finally:
        con.close()
    (root / "knowledge-layer-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "knowledge_layer/v1", "scope_id": "client-profile", "scope_type": "repository",
                "repository_ids": ["client-profile"], "producer": "knowledge-layer-core", "producer_version": "test",
                "build_id": "build-1", "build_status": "complete", "counts": {"subject_knowledge_record": 8},
                "capabilities": list(capabilities), "artifacts": {"database": "knowledge-layer.duckdb"},
                "metadata": {"coverage": {"source_file_count": 42, "payload_artifact_count": 7, "missing_payload_artifact_count": 0, "coverage_status": "complete"}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _client(tmp_path: Path, *, capabilities: tuple[str, ...] = CAPABILITIES) -> tuple[TestClient, str]:
    artifact = _system_description_artifact(tmp_path, capabilities=capabilities)
    result = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="system-description",
                schema_version="system-description/v1",
                materialization_id="system-description",
                capabilities=capabilities,
                manifest_path=artifact.parent / "knowledge-layer-manifest.json",
            )
        ],
        profile_id="system-description",
        scope_id="client-profile",
        execution_token="run-system-description",
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


def _query(client: TestClient, revision_id: str, query_kind: str, *, filters: dict | None = None, max_results: int = 100):
    return client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/system-description/query",
        json={"revision_id": revision_id, "query_kind": query_kind, "filters": filters or {}, "max_results": max_results},
    )


def test_system_description_query_surface_preserves_klc_reporting_contract(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        overview = _query(client, revision_id, "get_scope_overview")
        assert overview.status_code == 200, overview.text
        assert overview.json()["revision_id"] == revision_id
        assert overview.json()["query"]["kind"] == "get_scope_overview"
        assert "common.system-description" in overview.json()["items"][0]["capabilities"]

        composition = _query(client, revision_id, "get_repository_composition")
        assert composition.status_code == 200, composition.text
        assert composition.json()["summary"]["module_count"] == 1
        assert composition.json()["items"][0]["modules"][0]["module_path"] == "client-profile-app"

        interfaces = _query(
            client, revision_id, "list_interfaces",
            filters={"direction": "inbound", "boundary_kinds": ["rest_request", "kafka_consume"]},
        )
        assert interfaces.status_code == 200, interfaces.text
        assert {item["boundary_kind"] for item in interfaces.json()["items"]} == {"rest_request", "kafka_consume"}
        assert interfaces.json()["evidence"]

        integrations = _query(client, revision_id, "list_integrations")
        assert integrations.status_code == 200, integrations.text
        assert integrations.json()["items"][0]["endpoint_or_topic"] == "/api/inf/operator/get-by-phone-number/{phone}"

        events = _query(client, revision_id, "list_events")
        assert events.status_code == 200, events.text
        assert {item["boundary_kind"] for item in events.json()["items"]} == {"kafka_consume"}

        storage = _query(client, revision_id, "list_data_objects")
        assert storage.status_code == 200, storage.text
        assert storage.json()["items"][0]["qualified_name"] == "DEVICE_LINK"

        journeys = _query(client, revision_id, "get_representative_journeys", max_results=2)
        assert journeys.status_code == 200, journeys.text
        assert journeys.json()["summary"]["scenario_count"] == 3
        assert journeys.json()["summary"]["complete_selected"] == 2
        assert all(item["is_complete"] for item in journeys.json()["items"])

        gaps = _query(client, revision_id, "get_gap_summary")
        assert gaps.status_code == 200, gaps.text
        assert gaps.json()["summary"]["gap_count"] == 1
        assert gaps.json()["gaps"][0]["missing_fact_kind"] == "downstream_boundary_not_observed"

        coverage = _query(client, revision_id, "get_analysis_coverage")
        assert coverage.status_code == 200, coverage.text
        assert coverage.json()["summary"]["source_file_count"] == 42
        assert coverage.json()["summary"]["coverage_status"] == "complete"
    finally:
        client.__exit__(None, None, None)


def test_system_description_query_rejects_non_klc_filters_and_does_not_fallback(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        invalid = _query(client, revision_id, "get_scope_overview", filters={"invented": "value"})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_system_description_query"
    finally:
        client.__exit__(None, None, None)

    other_root = tmp_path / "no-capability"
    other_root.mkdir()
    client, revision_id = _client(other_root, capabilities=())
    try:
        missing = _query(client, revision_id, "get_scope_overview")
        assert missing.status_code == 409
        assert missing.json()["code"] == "knowledge_artifact_unavailable"
    finally:
        client.__exit__(None, None, None)


def test_system_description_guidance_is_compact_revision_bound_projection(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/system-description/guidance",
            params={
                "revision_id": revision_id,
                "technology_limit": 1,
                "interface_limit": 1,
                "integration_limit": 1,
                "event_limit": 1,
                "storage_limit": 1,
                "journey_limit": 1,
                "gap_limit": 1,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["guidance_schema_version"] == "system-description-guidance/v1"
        assert payload["revision_id"] == revision_id
        assert payload["projection"]["semantic_derivation"] == "none"
        assert "Business purpose" in payload["projection"]["interpretation_boundary"]

        assert payload["composition"]["summary"]["module_count"] == 1
        assert payload["composition"]["modules"][0]["module_name"] == "client-profile-app"
        assert payload["observed_inventory"]["interfaces"]["summary"]["selected_count"] == 2
        assert payload["observed_inventory"]["interfaces"]["presentation"] == {
            "source_total": 2,
            "presented": 1,
            "truncated": True,
        }
        assert payload["observed_inventory"]["integrations"]["summary"]["integration_count"] == 1
        assert payload["observed_inventory"]["events"]["summary"]["selected_count"] == 1
        assert payload["observed_inventory"]["storage_targets"]["summary"]["table_count"] == 1
        assert payload["representative_journeys"]["summary"]["scenario_count"] == 3
        assert payload["representative_journeys"]["presentation"]["truncated"] is True
        # The projection must preserve, not upgrade, the KLC-owned evidence state.
        assert payload["representative_journeys"]["items"][0]["evidence_level"] in {"observed", "unresolved", "confirmed"}
        assert payload["coverage"]["summary"]["source_file_count"] == 42
        assert payload["coverage"]["summary"]["coverage_status"] == "complete"
        assert payload["gaps"]["summary"]["gap_count"] == 1
        assert payload["gaps"]["items"][0]["missing_fact_kind"] == "downstream_boundary_not_observed"

        selected_evidence_ids = set()
        for section in payload["observed_inventory"].values():
            for item in section["items"]:
                selected_evidence_ids.update(item.get("evidence_ids") or [])
        selected_evidence_ids.update(
            evidence_id
            for module in payload["composition"]["modules"]
            for evidence_id in module.get("evidence_ids") or []
        )
        returned_evidence_ids = {item["evidence_id"] for item in payload["evidence"]}
        assert selected_evidence_ids <= returned_evidence_ids
        assert all("path" in item for item in payload["evidence"])
    finally:
        client.__exit__(None, None, None)


def test_system_description_guidance_requires_published_system_description_capability(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    root.mkdir()
    client, revision_id = _client(root, capabilities=())
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/client-profile/system-description/guidance",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "knowledge_artifact_unavailable"
    finally:
        client.__exit__(None, None, None)
