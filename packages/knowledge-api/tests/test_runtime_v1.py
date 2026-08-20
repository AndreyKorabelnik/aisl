from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiRuntimeError, KnowledgeApiSettings, sha256_file
from knowledge_api.contract_v1.service import KnowledgeDomainService


def _create_system(client: TestClient, system_id: str = "ucp") -> dict:
    response = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={
            "system_id": system_id,
            "display_name": "UCP",
            "description": "Unified customer profile",
            "metadata": {"owner": "data-governance"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_publish_and_query_complete_knowledge_flow(canonical_client, canonical_publication) -> None:
    system = _create_system(canonical_client)
    assert system["active_revision_id"] is None

    published = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=canonical_publication,
    )
    assert published.status_code == 201, published.text
    revision = published.json()["revision"]
    assert revision["state"] == "active"
    assert revision["execution"]["knowledge_profile_id"] == "canonical-profile"
    assert revision["execution_result"]["schema_version"] == "knowledge_execution_result/v2"
    assert len(revision["knowledge_artifacts"]) == 1
    assert revision["capabilities"] == ["common.cross-layer-data-model", "common.effective-data-model"]

    system = canonical_client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp").json()
    assert system["active_revision_id"] == revision["revision_id"]
    assert system["revision_count"] == 1

    tables = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/tables",
        params={"include_fields": "true"},
    )
    assert tables.status_code == 200, tables.text
    payload = tables.json()
    assert payload["revision_id"] == revision["revision_id"]
    assert payload["items"][0]["table_name"] == "Individual"
    assert payload["items"][0]["relationship_count"] == 1
    assert payload["items"][0]["fields"][0]["name"] == "id"

    table_id = payload["items"][0]["table_id"]
    detail = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/tables/{table_id}"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["keys"][0]["fields"] == ["id"]
    field = detail.json()["fields"][0]
    assert field["storage_observation_count"] == 1
    assert field["storage_observations"][0]["physical_field_name"] == "id"
    assert field["storage_observations"][0]["evidence_ids"] == ["evidence-field-id"]
    assert field["storage_observations"][0]["evidence_refs"][0] == {
        "evidence_id": "evidence-field-id",
        "repo_id": "repo-a",
        "path": "src/IndividualConverter.java",
        "line_start": 12,
        "line_end": 12,
        "extractor": "java_tree_sitter",
        "maturity": "observed",
        "role": "physical_field_name",
    }
    relationship = detail.json()["relationships"][0]
    assert relationship == {
        "relationship_id": "relationship-birth-country",
        "kind": "reference",
        "source_field": "birthCountry",
        "cardinality": "one",
        "target": {
            "object": {
                "id": "dictionary:example.Country",
                "name": "Country",
                "kind": "dictionary",
            }
        },
        "join": {
            "method": "logical_key_correspondence",
            "source_fields": ["birthCountry"],
            "target_fields": ["code"],
            "target_kind": "logical_identity",
            "requires_encoding_interpretation": False,
            "physical_join_confirmed": False,
        },
    }

    relationship_detail = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/tables/{table_id}/relationships/relationship-birth-country"
    )
    assert relationship_detail.status_code == 200, relationship_detail.text
    full_relationship = relationship_detail.json()["relationship"]
    assert full_relationship["target"]["logical_identity"]["fields"] == ["code"]
    assert full_relationship["provenance"]["evidence_ids"] == ["evidence-1"]


def test_relationship_detail_returns_404_for_unknown_relationship(
    canonical_client, canonical_publication
) -> None:
    _create_system(canonical_client)
    canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=canonical_publication
    )
    response = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/tables/replica:example.Individual/relationships/missing"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "relationship_not_found"


def test_publication_is_idempotent(canonical_client, canonical_publication) -> None:
    _create_system(canonical_client)
    first = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=canonical_publication
    )
    second = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=canonical_publication
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["revision"]["revision_id"] == second.json()["revision"]["revision_id"]
    revisions = canonical_client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions").json()
    assert revisions["page"]["total"] == 1


def test_second_active_revision_supersedes_first(
    canonical_client, canonical_publication, canonical_artifacts
) -> None:
    _create_system(canonical_client)
    first = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=canonical_publication
    ).json()["revision"]

    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    second_execution = write_execution_result(
        canonical_artifacts["root"],
        [
            KnowledgeArtifactSpec(
                database=canonical_artifacts["knowledge"],
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
            )
        ],
        profile_id="canonical-profile",
        scope_id="ucp",
        execution_token="job-456",
    )
    second_payload = publication_payload(second_execution)
    second = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=second_payload
    )
    assert second.status_code == 201, second.text
    second_revision = second.json()["revision"]

    revisions = canonical_client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions").json()["items"]
    states = {item["revision_id"]: item["state"] for item in revisions}
    assert states[first["revision_id"]] == "superseded"
    assert states[second_revision["revision_id"]] == "active"


def test_publication_rejects_digest_mismatch(canonical_client, canonical_publication) -> None:
    _create_system(canonical_client)
    payload = deepcopy(canonical_publication)
    payload["execution_result"]["sha256"] = "0" * 64
    response = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=payload
    )
    assert response.status_code == 409
    assert response.json()["code"] == "artifact_digest_mismatch"


def test_publication_rejects_path_outside_allowed_root(
    tmp_path: Path, canonical_publication, canonical_service
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    payload = deepcopy(canonical_publication)
    payload["execution_result"] = {
        "uri": outside.as_uri(),
        "sha256": sha256_file(outside),
        "media_type": "application/json",
        "schema_version": "knowledge_execution_result/v2",
        "byte_size": outside.stat().st_size,
    }
    with TestClient(create_contract_app(service=canonical_service)) as client:
        _create_system(client)
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "artifact_path_not_allowed"


def test_persistence_survives_service_restart(
    tmp_path: Path, canonical_artifacts, canonical_publication, canonical_service
) -> None:
    query_factory_type = type(canonical_service.query_factory)

    settings = KnowledgeApiSettings(
        database_path=tmp_path / "persistent.sqlite3",
        allowed_roots=(canonical_artifacts["root"],),
    )
    first_service = KnowledgeDomainService(settings, query_factory=query_factory_type())
    with TestClient(create_contract_app(service=first_service)) as client:
        _create_system(client)
        publish = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=canonical_publication
        )
        assert publish.status_code == 201
        revision_id = publish.json()["revision"]["revision_id"]

    second_service = KnowledgeDomainService(settings, query_factory=query_factory_type())
    with TestClient(create_contract_app(service=second_service)) as client:
        system = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp")
        assert system.status_code == 200
        assert system.json()["active_revision_id"] == revision_id
        tables = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/tables")
        assert tables.status_code == 200
        assert tables.json()["items"][0]["table_name"] == "Individual"


def test_revision_exposes_knowledge_artifacts_and_capabilities(
    canonical_client, canonical_publication
) -> None:
    _create_system(canonical_client)
    revision = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=canonical_publication,
    ).json()["revision"]

    artifacts = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/knowledge-artifacts"
    )
    assert artifacts.status_code == 200, artifacts.text
    artifact = artifacts.json()["items"][0]
    assert artifact["model_kind"] == "effective-data-model"
    assert artifacts.json()["revision_id"] == revision["revision_id"]

    detail = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/knowledge-artifacts/{artifact['artifact_id']}"
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["artifact"]["content_fingerprint"] == artifact["content_fingerprint"]

    capabilities = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/capabilities"
    )
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["capabilities"] == [
        "common.cross-layer-data-model",
        "common.effective-data-model",
    ]


def test_publication_rejects_nested_artifact_path_outside_allowed_root(tmp_path: Path) -> None:
    import json

    from knowledge_api.publication import build_publication_request, stable_fingerprint
    from tests.execution_fixtures import KnowledgeArtifactSpec, write_execution_result

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    database = allowed / "effective.duckdb"
    database.write_bytes(b"fixture")
    execution = write_execution_result(
        allowed,
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
    outside_manifest = outside / "manifest.json"
    outside_manifest.write_text("{}", encoding="utf-8")
    payload["knowledge_artifacts"][0]["location"]["manifest_path"] = str(outside_manifest)
    payload.pop("result_fingerprint")
    payload["result_fingerprint"] = stable_fingerprint(payload)
    execution.write_text(json.dumps(payload), encoding="utf-8")
    request, _ = build_publication_request(
        execution_result=execution,
                labels=[],
        metadata={},
        activate=True,
    )
    service = KnowledgeDomainService(
        KnowledgeApiSettings(
            database_path=tmp_path / "guard.sqlite3",
            allowed_roots=(allowed,),
        )
    )
    with pytest.raises(KnowledgeApiRuntimeError) as caught:
        service.validate_publication("test-system", request)
    assert caught.value.code == "artifact_path_not_allowed"



def test_incremental_publication_composes_single_revision_snapshot(
    canonical_client, canonical_artifacts
) -> None:
    from knowledge_api.publication import build_publication_request, stable_fingerprint
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    _create_system(canonical_client)
    root = canonical_artifacts["root"]
    auxiliary = root / "repository-inventory.duckdb"
    auxiliary.write_bytes(b"repository inventory fixture")
    old_context = root / "attribute-extension-context-old.duckdb"
    old_context.write_bytes(b"old attribute extension context fixture")
    base_execution = write_execution_result(
        root,
        [
            KnowledgeArtifactSpec(
                database=canonical_artifacts["knowledge"],
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
            ),
            KnowledgeArtifactSpec(
                database=auxiliary,
                model_kind="repository-inventory",
                schema_version="repository-inventory/v3",
                materialization_id="repository-inventory",
                capabilities=("common.repository-inventory",),
            ),
            KnowledgeArtifactSpec(
                database=old_context,
                model_kind="data-model-attribute-extension-context",
                schema_version="data-model-attribute-extension-context/v1",
                materialization_id="data-model-attribute-extension-context",
                capabilities=("common.old-context-capability",),
            ),
        ],
        profile_id="base-profile",
        scope_id="ucp",
        execution_token="base-snapshot",
    )
    base = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=publication_payload(base_execution),
    )
    assert base.status_code == 201, base.text
    base_revision = base.json()["revision"]
    assert base_revision["base_revision_id"] is None
    assert len(base_revision["knowledge_artifacts"]) == 3
    old_context_artifact_id = next(
        item["artifact_id"] for item in base_revision["knowledge_artifacts"]
        if item["source_materialization_id"] == "data-model-attribute-extension-context"
    )

    context_db = root / "attribute-extension-context.duckdb"
    context_db.write_bytes(b"attribute extension context fixture")
    incremental_execution = write_execution_result(
        root,
        [KnowledgeArtifactSpec(
            database=context_db,
            model_kind="data-model-attribute-extension-context",
            schema_version="data-model-attribute-extension-context/v1",
            materialization_id="data-model-attribute-extension-context",
            capabilities=("common.data-model-agent-join-semantics",),
        )],
        profile_id="incremental-profile",
        scope_id="ucp",
        execution_token="incremental-snapshot",
    )
    payload = json.loads(incremental_execution.read_text(encoding="utf-8"))
    effective = next(
        item for item in base_revision["knowledge_artifacts"]
        if item["source_materialization_id"] == "effective-data-model"
    )
    payload["materialization_executions"][0]["input_knowledge_artifact_ids"] = [effective["artifact_id"]]
    payload["external_knowledge_artifacts"] = [{
        "artifact_id": effective["artifact_id"],
        "model_kind": effective["model_kind"],
        "schema_version": effective["schema_version"],
        "source_materialization_id": effective["source_materialization_id"],
        "content_fingerprint": effective["content_fingerprint"],
        "source_system_id": "ucp",
        "source_revision_id": base_revision["revision_id"],
        "published_capabilities": effective["capabilities"],
    }]
    payload["result_fingerprint"] = stable_fingerprint(
        {key: value for key, value in payload.items() if key != "result_fingerprint"}
    )
    incremental_execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    delta_only, _ = build_publication_request(
        execution_result=incremental_execution,
                labels=[],
        metadata={},
        activate=True,
    )
    rejected = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=delta_only.model_dump(mode="json"),
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == "publication_base_revision_required"

    composed, _ = build_publication_request(
        execution_result=incremental_execution,
                base_revision_id=base_revision["revision_id"],
        labels=[],
        metadata={},
        activate=True,
    )
    published = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=composed.model_dump(mode="json"),
    )
    assert published.status_code == 201, published.text
    revision = published.json()["revision"]
    assert revision["base_revision_id"] == base_revision["revision_id"]
    assert len(revision["knowledge_artifacts"]) == 3
    new_context_artifact_id = next(
        item["artifact_id"] for item in revision["knowledge_artifacts"]
        if item["source_materialization_id"] == "data-model-attribute-extension-context"
    )
    assert new_context_artifact_id != old_context_artifact_id
    assert {item["source_materialization_id"] for item in revision["knowledge_artifacts"]} == {
        "effective-data-model",
        "repository-inventory",
        "data-model-attribute-extension-context",
    }
    assert revision["capabilities"] == [
        "common.cross-layer-data-model",
        "common.data-model-agent-join-semantics",
        "common.effective-data-model",
        "common.repository-inventory",
    ]
    assert "common.old-context-capability" not in revision["capabilities"]
    caps = canonical_client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/capabilities")
    assert caps.status_code == 200, caps.text
    assert caps.json()["revision_id"] == revision["revision_id"]
    assert caps.json()["capabilities"] == revision["capabilities"]


def test_incremental_publication_rejects_wrong_base_dependency_identity(
    canonical_client, canonical_artifacts
) -> None:
    from knowledge_api.publication import build_publication_request, stable_fingerprint
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    _create_system(canonical_client)
    base = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=canonical_publication_payload(canonical_artifacts),
    )
    assert base.status_code == 201, base.text
    base_revision = base.json()["revision"]
    effective = base_revision["knowledge_artifacts"][0]

    db = canonical_artifacts["root"] / "derived-wrong-base.duckdb"
    db.write_bytes(b"derived")
    execution = write_execution_result(
        canonical_artifacts["root"],
        [KnowledgeArtifactSpec(
            database=db, model_kind="derived-test", schema_version="derived-test/v1",
            materialization_id="derived-test", capabilities=("common.derived-test",),
        )],
        scope_id="ucp", execution_token="wrong-base",
    )
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["materialization_executions"][0]["input_knowledge_artifact_ids"] = [effective["artifact_id"]]
    payload["external_knowledge_artifacts"] = [{
        "artifact_id": effective["artifact_id"],
        "model_kind": effective["model_kind"],
        "schema_version": effective["schema_version"],
        "source_materialization_id": effective["source_materialization_id"],
        "content_fingerprint": effective["content_fingerprint"],
        "source_system_id": "ucp",
        "source_revision_id": base_revision["revision_id"],
        "published_capabilities": ["common.wrong-capability"],
    }]
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    request, _ = build_publication_request(
        execution_result=execution, base_revision_id=base_revision["revision_id"],
        labels=[], metadata={}, activate=True,
    )
    response = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=request.model_dump(mode="json")
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "publication_base_dependency_identity_mismatch"




def canonical_publication_payload(canonical_artifacts: dict[str, Path]) -> dict:
    from tests.execution_fixtures import publication_payload
    return publication_payload(canonical_artifacts["execution_result"])

def test_pre_016_catalog_schema_is_rejected(tmp_path: Path) -> None:
    import sqlite3

    database = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE systems (
                system_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                description TEXT,
                metadata_json TEXT NOT NULL,
                active_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE revisions (
                revision_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_json TEXT NOT NULL,
                knowledge_layer_json TEXT NOT NULL,
                labels_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            """
        )
    finally:
        connection.close()
    with pytest.raises(RuntimeError, match="new 0.30.11\\+ catalog"):
        KnowledgeDomainService(
            KnowledgeApiSettings(database_path=database, allowed_roots=(tmp_path,))
        )
