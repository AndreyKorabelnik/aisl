from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.interaction_field_contract_knowledge_schema import INTERACTION_FIELD_CONTRACT_DDL
from knowledge_layer_core.interaction_knowledge_schema import INTERACTION_KNOWLEDGE_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _interaction_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "system-interactions.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(INTERACTION_KNOWLEDGE_DDL)
        con.execute(
            "INSERT INTO interaction_knowledge_build VALUES "
            "('b','workspace','test','workspace_system_interaction/v6','interaction-boundary-evidence/v1','complete','now','now','{}','{}')"
        )
        con.execute(
            "INSERT INTO repository_interaction_boundary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "b-out", "workspace", "repo-a", "sys-a", "p", json.dumps(["service-a"]),
                "outbound-1", "outbound", "http", "http", "getUser", "GET",
                json.dumps(["/users/{id}"]), json.dumps(["users.internal"]), json.dumps(["user-service"]),
                json.dumps([]), json.dumps(["user.base-url"]), "fp-1",
                json.dumps({"source": "A.java"}), json.dumps({}),
            ],
        )
        con.execute(
            "INSERT INTO system_interaction VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ["i-1", "workspace", "repo-a", "repo-b", "http", 1, 2, "matched", "confirmed", json.dumps(["bi-1"]), json.dumps({})],
        )
        con.execute(
            "INSERT INTO system_boundary_interaction VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "bi-1", "i-1", "workspace", "repo-a", "outbound-1", "getUser", "GET", "/users/{id}",
                "repo-b", "inbound-1", "getUser", "/users/{id}", "http", "matched", "confirmed", "confirmed",
                json.dumps({"basis": "authority_method_path"}), json.dumps({"source": "A.java"}), json.dumps({}),
            ],
        )
        for idx, trigger in enumerate(("rest", "scheduler"), start=1):
            con.execute(
                "INSERT INTO system_interaction_execution_context VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    f"ctx-{idx}", "bi-1", "i-1", "workspace", "repo-a", f"ingress-{idx}", trigger,
                    f"/{trigger}", "outbound-1", "getUser", trigger, "complete", 2,
                    json.dumps(["m1", "m2"]), json.dumps({"source": f"C{idx}.java"}), json.dumps({}),
                ],
            )
        con.execute(
            "INSERT INTO system_interaction_match_diagnostic VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "d-1", "workspace", "repo-a", "outbound-1", "getUser", "http", "GET",
                json.dumps(["/users/{id}"]), "matched", "confirmed", json.dumps([{"repo_id": "repo-b"}]), json.dumps({}),
            ],
        )
    finally:
        con.close()
    return path


def _field_contract_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "interaction-field-contracts.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(INTERACTION_FIELD_CONTRACT_DDL)
        con.execute(
            "INSERT INTO interaction_field_contract_build VALUES "
            "('b','workspace','test','workspace_system_interaction_field_contract/v2','complete','now','now','{}','{}')"
        )
        con.execute(
            "INSERT INTO system_interaction_field_contract VALUES (" + ",".join("?" for _ in range(28)) + ")",
            [
                "fc-1", "bi-1", "i-1", "workspace", "repo-a", "outbound-1", "getUser", "UserRequest",
                "user.id", "id", "id", "String", "java", "repo-b", "inbound-1", "getUser", "UserRequest",
                "user.id", "id", "id", "String", "java", "user.id", "wire_name", "matched", "compatible",
                json.dumps({"source": "UserRequest.java"}), json.dumps({}),
            ],
        )
    finally:
        con.close()
    return path


def _coverage_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "coverage-artifact"
    root.mkdir()
    path = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """CREATE TABLE repository_interaction_coverage (
                coverage_id VARCHAR, scope_id VARCHAR, repo_id VARCHAR, system_id VARCHAR, project_id VARCHAR,
                analysis_status VARCHAR, inbound_boundary_count BIGINT, outbound_boundary_count BIGINT,
                matched_outbound_count BIGINT, confirmed_outbound_count BIGINT, probable_outbound_count BIGINT,
                ambiguous_outbound_count BIGINT, unresolved_outbound_count BIGINT,
                matching_coverage_status VARCHAR, coverage_status VARCHAR, payload_json JSON
            )"""
        )
        con.execute(
            "INSERT INTO repository_interaction_coverage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ["cov-1", "workspace", "repo-a", "sys-a", "p", "completed", 1, 1, 1, 1, 0, 0, 0, "complete", "complete", json.dumps({})],
        )
    finally:
        con.close()
    (root / "knowledge-layer-manifest.json").write_text(
        json.dumps({"capabilities": ["workspace.repository-interaction-coverage"], "artifacts": {"database": "knowledge-layer.duckdb"}}),
        encoding="utf-8",
    )
    return path


def _client(tmp_path: Path, *, include_field_contracts: bool = True, include_coverage: bool = True) -> tuple[TestClient, str]:
    specs = [
        KnowledgeArtifactSpec(
            database=_interaction_artifact(tmp_path),
            model_kind="system-interactions",
            schema_version="workspace_system_interaction/v6",
            materialization_id="system-interactions",
            capabilities=("workspace.system-interactions", "workspace.repository-interaction-boundaries"),
        )
    ]
    if include_field_contracts:
        specs.append(
            KnowledgeArtifactSpec(
                database=_field_contract_artifact(tmp_path),
                model_kind="interaction-field-contracts",
                schema_version="workspace_system_interaction_field_contract/v2",
                materialization_id="interaction-field-contracts",
                capabilities=("workspace.system-interaction-field-contracts",),
            )
        )
    if include_coverage:
        specs.append(
            KnowledgeArtifactSpec(
                database=_coverage_artifact(tmp_path),
                model_kind="interaction-coverage",
                schema_version="repository_interaction_coverage/v1",
                materialization_id="interaction-coverage",
                capabilities=("workspace.repository-interaction-coverage",),
            )
        )
    result = write_execution_result(tmp_path, specs, scope_id="workspace", execution_token="run-interactions")
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings)))
    client.__enter__()
    assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "portfolio", "display_name": "Portfolio"}).status_code == 201
    pub = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/revisions", json=publication_payload(result))
    assert pub.status_code == 201, pub.text
    return client, pub.json()["revision"]["revision_id"]


def test_interaction_read_surface_is_revision_bound_and_preserves_klc_facts(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        base = f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/interactions"
        interactions = client.get(base, params={"revision_id": revision_id, "source_repo_id": "repo-a"})
        assert interactions.status_code == 200, interactions.text
        body = interactions.json()
        assert body["revision_id"] == revision_id
        assert body["query_kind"] == "knowledge-layer-system-interactions"
        assert body["page"]["total"] == 1
        assert body["items"][0]["confidence"] == "confirmed"
        assert body["items"][0]["boundary_interaction_ids_json"] == ["bi-1"]

        boundary_interactions = client.get(base + "/boundary-interactions", params={"revision_id": revision_id, "source_repo_id": "repo-a"})
        assert boundary_interactions.status_code == 200, boundary_interactions.text
        boundary_item = boundary_interactions.json()["items"][0]
        assert boundary_item["boundary_interaction_id"] == "bi-1"
        assert boundary_item["payload_json"] == {}

        boundaries = client.get(base + "/boundaries", params={"revision_id": revision_id, "repo_id": "repo-a"})
        assert boundaries.status_code == 200, boundaries.text
        assert boundaries.json()["items"][0]["service_identities_json"] == ["user-service"]

        contexts = client.get(base + "/execution-contexts", params={"revision_id": revision_id, "interaction_id": "i-1"})
        assert contexts.status_code == 200, contexts.text
        assert contexts.json()["page"]["total"] == 2
        assert {item["trigger_kind"] for item in contexts.json()["items"]} == {"rest", "scheduler"}

        fields = client.get(base + "/field-contracts", params={"revision_id": revision_id, "interaction_id": "i-1"})
        assert fields.status_code == 200, fields.text
        assert fields.json()["items"][0]["wire_path"] == "user.id"

        diagnostics = client.get(base + "/diagnostics", params={"revision_id": revision_id, "source_repo_id": "repo-a"})
        assert diagnostics.status_code == 200, diagnostics.text
        assert diagnostics.json()["items"][0]["candidate_matches_json"] == [{"repo_id": "repo-b"}]

        coverage = client.get(base + "/coverage", params={"revision_id": revision_id, "repo_id": "repo-a"})
        assert coverage.status_code == 200, coverage.text
        assert coverage.json()["items"][0]["coverage_status"] == "complete"
    finally:
        client.__exit__(None, None, None)


def test_interaction_surfaces_do_not_fallback_to_wrong_artifact(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path, include_field_contracts=False, include_coverage=False)
    try:
        base = f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/interactions"
        assert client.get(base, params={"revision_id": revision_id}).status_code == 200

        field_contracts = client.get(base + "/field-contracts", params={"revision_id": revision_id})
        assert field_contracts.status_code == 409
        assert field_contracts.json()["code"] == "knowledge_artifact_unavailable"

        coverage = client.get(base + "/coverage", params={"revision_id": revision_id})
        assert coverage.status_code == 409
        assert coverage.json()["code"] == "knowledge_artifact_unavailable"
    finally:
        client.__exit__(None, None, None)


def test_system_interaction_guidance_compacts_exact_interaction_without_semantic_upgrade(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        base = f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/interactions"
        response = client.get(
            base + "/i-1/guidance",
            params={"revision_id": revision_id, "context_limit": 1, "field_limit": 1},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["guidance_schema_version"] == "system-interaction-guidance/v1"
        assert body["revision_id"] == revision_id
        assert body["interaction_id"] == "i-1"
        assert body["summary"] == {
            "boundary_interaction_count": 1,
            "boundary_interactions_presented": 1,
            "boundary_interactions_truncated": False,
            "execution_context_count": 2,
            "field_contract_availability": "available",
            "field_contract_count": 1,
        }
        assert body["projection"]["semantic_derivation"] == "none"
        item = body["items"][0]
        assert item["boundary_interaction_id"] == "bi-1"
        assert item["match_status"] == "matched"
        assert item["confidence"] == "confirmed"
        assert item["source"]["outbound_operation"] == "getUser"
        assert item["source"]["outbound_endpoint"] == "/users/{id}"
        assert item["target"]["target_ingress_operation"] == "getUser"
        assert item["target"]["target_ingress_endpoint"] == "/users/{id}"
        assert item["execution_context_summary"] == {
            "source_total": 2,
            "presented": 1,
            "truncated": True,
        }
        assert len(item["execution_contexts"]) == 1
        assert item["field_contract_summary"] == {
            "availability": "available",
            "source_total": 1,
            "presented": 1,
            "truncated": False,
        }
        assert item["field_contracts"][0]["wire_path"] == "user.id"
        assert item["field_contracts"][0]["match_status"] == "matched"
        assert "payload_json" not in item
    finally:
        client.__exit__(None, None, None)


def test_system_interaction_guidance_keeps_missing_field_contract_product_explicit(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path, include_field_contracts=False, include_coverage=False)
    try:
        base = f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/interactions"
        response = client.get(base + "/i-1/guidance", params={"revision_id": revision_id})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"]["field_contract_availability"] == "not_available"
        assert body["summary"]["field_contract_count"] == 0
        item = body["items"][0]
        assert item["field_contract_summary"] == {
            "availability": "not_available",
            "source_total": 0,
            "presented": 0,
            "truncated": False,
        }
        assert "field_contracts" not in item
    finally:
        client.__exit__(None, None, None)


def test_system_interaction_guidance_reports_unknown_exact_interaction(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        base = f"{KNOWLEDGE_API_PREFIX}/systems/portfolio/interactions"
        response = client.get(base + "/missing/guidance", params={"revision_id": revision_id})
        assert response.status_code == 404
        assert response.json()["code"] == "system_interaction_not_found"
    finally:
        client.__exit__(None, None, None)
