from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from knowledge_api.contract_v1 import (
    KNOWLEDGE_API_PREFIX,
    KNOWLEDGE_API_SCHEMA_VERSION,
    create_contract_app,
)
from knowledge_api.contract_v1.models import PublishedArtifact, RevisionCreateRequest

EXPECTED_PATHS = {
    "/api/knowledge/v1/health",
    "/api/knowledge/v1/version",
    "/api/knowledge/v1/capabilities",
    "/api/knowledge/v1/artifact-store/gc",
    "/api/knowledge/v1/systems",
    "/api/knowledge/v1/systems/{system_id}",
    "/api/knowledge/v1/systems/{system_id}/revisions",
    "/api/knowledge/v1/systems/{system_id}/revisions/{revision_id}",
    "/api/knowledge/v1/systems/{system_id}/revisions/{revision_id}/activate",
    "/api/knowledge/v1/systems/{system_id}/knowledge-artifacts",
    "/api/knowledge/v1/systems/{system_id}/knowledge-artifacts/{artifact_id}",
    "/api/knowledge/v1/systems/{system_id}/knowledge-items/{artifact_id}/{item_kind}/{local_id}",
    "/api/knowledge/v1/systems/{system_id}/llm-integration-profile",
    "/api/knowledge/v1/systems/{system_id}/capabilities",
    "/api/knowledge/v1/systems/{system_id}/attribute-paths/resolve",
    "/api/knowledge/v1/systems/{system_id}/coverage",
    "/api/knowledge/v1/systems/{system_id}/data-model/lineage",
    "/api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-context",
    "/api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-guidance",
    "/api/knowledge/v1/systems/{system_id}/data-model/declared-summary",
    "/api/knowledge/v1/systems/{system_id}/data-model/declared-objects",
    "/api/knowledge/v1/systems/{system_id}/data-model/declared-objects/{object_id}",
    "/api/knowledge/v1/systems/{system_id}/data-model/object-context/{object_id}",
    "/api/knowledge/v1/systems/{system_id}/interactions",
    "/api/knowledge/v1/systems/{system_id}/interactions/boundary-interactions",
    "/api/knowledge/v1/systems/{system_id}/interactions/boundaries",
    "/api/knowledge/v1/systems/{system_id}/interactions/execution-contexts",
    "/api/knowledge/v1/systems/{system_id}/interactions/field-contracts",
    "/api/knowledge/v1/systems/{system_id}/interactions/{interaction_id}/guidance",
    "/api/knowledge/v1/systems/{system_id}/interactions/diagnostics",
    "/api/knowledge/v1/systems/{system_id}/interactions/coverage",
    "/api/knowledge/v1/systems/{system_id}/data-model/tables",
    "/api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}",
    "/api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}/relationships/{relationship_id}",
    "/api/knowledge/v1/systems/{system_id}/physical-model",
    "/api/knowledge/v1/systems/{system_id}/physical-model/tables",
    "/api/knowledge/v1/systems/{system_id}/physical-model/tables/{table_id}",
    "/api/knowledge/v1/systems/{system_id}/physical-model/columns",
    "/api/knowledge/v1/systems/{system_id}/physical-model/keys",
    "/api/knowledge/v1/systems/{system_id}/physical-model/relationships",
    "/api/knowledge/v1/systems/{system_id}/physical-model/gaps",
    "/api/knowledge/v1/systems/{system_id}/storage-usage/accesses",
    "/api/knowledge/v1/systems/{system_id}/storage-usage/gaps",
    "/api/knowledge/v1/systems/{system_id}/system-description/guidance",
    "/api/knowledge/v1/systems/{system_id}/system-description/query",
    "/api/knowledge/v1/systems/{system_id}/foreign-data-persistence/query",
    "/api/knowledge/v1/systems/{system_id}/foreign-data-persistence/guidance",
    "/api/knowledge/v1/systems/{system_id}/reference-data/query",
    "/api/knowledge/v1/systems/{system_id}/reference-data/guidance",
    "/api/knowledge/v1/systems/{system_id}/sql/relations",
    "/api/knowledge/v1/systems/{system_id}/sql/source-inventory",
    "/api/knowledge/v1/systems/{system_id}/sql/source-inventory.jsonl",
    "/api/knowledge/v1/systems/{system_id}/sql/target-column-lineage",
    "/api/knowledge/v1/systems/{system_id}/sql/field-calculation",
    "/api/knowledge/v1/systems/{system_id}/sql/workspace-catalog",
    "/api/knowledge/v1/systems/{system_id}/sql/target-candidates",
    "/api/knowledge/v1/systems/{system_id}/sql/attribute-insertion-context",
    "/api/knowledge/v1/systems/{system_id}/sql/column-usages/{sql_column_usage_id}",
    "/api/knowledge/v1/systems/{system_id}/sql/relation-materializations",
    "/api/knowledge/v1/systems/{system_id}/sql/query-context",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/coverage",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/technologies",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/interfaces",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/inputs",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/outputs",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/structural-families",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/discovery",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/coverage-gaps",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/source-occurrences",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/source-occurrences/{occurrence_id}",
    "/api/knowledge/v1/systems/{system_id}/repository-inventory/diagnostics",
    "/api/knowledge/v1/portfolio/inventory",
    "/api/knowledge/v1/portfolio/inventory/facets",
    "/api/knowledge/v1/portfolio/inventory/{system_id}",
    "/api/knowledge/v1/portfolio/interaction-graph",
}


def _publication_request() -> RevisionCreateRequest:
    return RevisionCreateRequest(
        execution_result=PublishedArtifact(
            uri="file:///outputs/ucp/knowledge_execution_result.json",
            sha256="a" * 64,
            media_type="application/json",
            schema_version="knowledge_execution_result/v2",
            byte_size=123,
        ),
    )


def test_contract_constants_are_canonical() -> None:
    assert KNOWLEDGE_API_PREFIX == "/api/knowledge/v1"
    assert KNOWLEDGE_API_SCHEMA_VERSION == "knowledge_api/v1"


def test_openapi_contains_only_knowledge_domain_paths() -> None:
    schema = create_contract_app().openapi()
    assert set(schema["paths"]) == EXPECTED_PATHS
    rendered = json.dumps(schema, sort_keys=True)
    assert "/jobs" not in rendered
    assert "/workspaces" not in rendered
    assert "/repositories" not in rendered
    assert "assistant-diagnostics" not in rendered
    assert "force_rebuild" not in rendered


def test_publication_contract_is_execution_result_driven() -> None:
    request = _publication_request()
    dumped = request.model_dump(mode="json")
    assert dumped["execution_result"]["schema_version"] == "knowledge_execution_result/v2"
    assert "source" not in dumped
    assert "knowledge_layer" not in dumped


def test_publication_rejects_non_absolute_artifact_uri() -> None:
    with pytest.raises(ValidationError, match="URI scheme"):
        PublishedArtifact(
            uri="outputs/model.duckdb",
            sha256="a" * 64,
            media_type="application/vnd.duckdb",
        )


def test_publication_rejects_invalid_sha256() -> None:
    with pytest.raises(ValidationError):
        PublishedArtifact(
            uri="file:///outputs/model.duckdb",
            sha256="not-a-digest",
            media_type="application/vnd.duckdb",
        )


def test_publication_rejects_wrong_artifact_media_types() -> None:
    request = _publication_request().model_dump(mode="python")
    request["execution_result"]["media_type"] = "text/markdown"
    with pytest.raises(ValidationError, match="execution_result media_type"):
        RevisionCreateRequest.model_validate(request)

    request = _publication_request().model_dump(mode="python")
    request["execution_result"]["schema_version"] = "knowledge_execution_result/v0"
    with pytest.raises(ValidationError, match="execution_result schema_version"):
        RevisionCreateRequest.model_validate(request)


def test_revision_aware_queries_are_expressed_in_openapi() -> None:
    schema = create_contract_app().openapi()
    table_list = schema["paths"][f"{KNOWLEDGE_API_PREFIX}/systems/{{system_id}}/data-model/tables"]["get"]
    parameters = {item["name"]: item for item in table_list["parameters"]}
    assert parameters["revision_id"]["required"] is False
    assert parameters["include_fields"]["schema"]["default"] is False
    assert parameters["limit"]["schema"]["maximum"] == 500

    detail = schema["paths"][f"{KNOWLEDGE_API_PREFIX}/systems/{{system_id}}/data-model/tables/{{table_id}}"]["get"]
    detail_parameters = {item["name"]: item for item in detail["parameters"]}
    assert detail_parameters["revision_id"]["required"] is False


def test_reporting_is_not_part_of_knowledge_api_contract() -> None:
    schema = create_contract_app().openapi()
    assert all("/reports" not in path for path in schema["paths"])
    assert "report" not in RevisionCreateRequest.model_fields

def test_contract_routes_are_runtime_backed(tmp_path: Path) -> None:
    from knowledge_api.contract_v1.runtime import KnowledgeApiSettings

    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        response = client.get(f"{KNOWLEDGE_API_PREFIX}/systems")
        assert response.status_code == 200
        assert response.json()["items"] == []


def test_exported_contract_openapi_matches_generated_document() -> None:
    path = Path(__file__).parents[1] / "schemas" / "knowledge-v1.openapi.json"
    assert path.exists()
    expected = create_contract_app().openapi()
    actual = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected


def test_invalid_publication_payload_returns_canonical_validation_error(tmp_path: Path) -> None:
    from knowledge_api.contract_v1.runtime import KnowledgeApiSettings

    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        created = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "validation-smoke", "display_name": "Validation smoke"},
        )
        assert created.status_code == 201
        response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/validation-smoke/revisions",
            json={"activate": True},
        )
    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "request_validation_failed"
    assert payload["details"]["errors"]
    assert all("url" not in error for error in payload["details"]["errors"])


def test_coverage_endpoint_is_revision_aware(canonical_client: TestClient, canonical_publication: dict) -> None:
    assert canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "coverage-system", "display_name": "Coverage system"},
    ).status_code == 201
    published = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/coverage-system/revisions",
        json=canonical_publication,
    )
    assert published.status_code == 201
    revision_id = published.json()["revision"]["revision_id"]
    response = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/coverage-system/coverage",
        params={"revision_id": revision_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "analysis_coverage/v1"
    assert payload["revision_id"] == revision_id
    assert payload["status"] == "partial"
    assert payload["summary"]["observed_fact_count"] == 42
    assert payload["domains"]["data_model"]["unresolved_relationship_candidate_count"] == 1
    assert payload["limitations"][0]["kind"] == "source_expression_not_resolved"
