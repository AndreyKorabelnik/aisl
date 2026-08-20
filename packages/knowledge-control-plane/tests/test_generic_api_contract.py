from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from knowledge_control_plane.api.generic_v1 import create_contract_app
from knowledge_control_plane.api.generic_v1.models import JobCreateRequest, JobTarget, RepositoryDiscoverRequest

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "api" / "generic-v1.openapi.json"


def _operations(document: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, path_item in document["paths"].items()
        for method in path_item
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }


def test_contract_exposes_knowledge_execution_product_surface() -> None:
    document = create_contract_app().openapi()
    operations = _operations(document)
    required = {
        ("GET", "/api/v1/knowledge-products"),
        ("GET", "/api/v1/knowledge-profiles"),
        ("GET", "/api/v1/knowledge-profiles/{profile_id}"),
        ("POST", "/api/v1/knowledge-profiles"),
        ("PATCH", "/api/v1/knowledge-profiles/{profile_id}"),
        ("DELETE", "/api/v1/knowledge-profiles/{profile_id}"),
        ("POST", "/api/v1/knowledge-profiles/{profile_id}/copy"),
        ("GET", "/api/v1/knowledge-profiles/{profile_id}/resolution"),
        ("GET", "/api/v1/scenarios"),
        ("GET", "/api/v1/scenarios/{scenario_id}"),
        ("GET", "/api/v1/productions"),
        ("POST", "/api/v1/productions"),
        ("POST", "/api/v1/productions/refresh-check-due"),
        ("POST", "/api/v1/productions/{production_id}/refresh-check"),
        ("POST", "/api/v1/jobs"),
        ("POST", "/api/v1/jobs/preview"),
        ("GET", "/api/v1/jobs/{job_id}/events"),
        ("GET", "/api/v1/jobs/{job_id}/artifacts"),
        ("GET", "/api/v1/jobs/{job_id}/production-structure"),
    }
    assert required <= operations
    forbidden_fragments = ("/profiles", "analysis-artifact", "/jobs/{job_id}/conversation", "/assistant-contexts")
    assert not any(any(fragment in path for fragment in forbidden_fragments) for _, path in operations)
    assert document["x-canonical-knowledge-owner"] == "knowledge-api"
    assert document["x-orchestration-domain-resources"] == [
        "repositories", "productions", "workspaces", "knowledge_products", "knowledge_profiles", "scenarios", "jobs", "artifacts", "diagnostics"
    ]


def test_generated_openapi_is_current() -> None:
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert committed == create_contract_app().openapi()


def test_openapi_operation_ids_are_unique_and_stream_media_types_are_explicit() -> None:
    document = create_contract_app().openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in document["paths"].values()
        for method, operation in path_item.items()
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert "text/event-stream" in document["paths"]["/api/v1/jobs/{job_id}/events"]["get"]["responses"]["200"]["content"]
    assert "application/octet-stream" in document["paths"]["/api/v1/artifacts/{artifact_id}/download"]["get"]["responses"]["200"]["content"]


def test_job_create_contract_rejects_removed_semantic_routes_and_secrets() -> None:
    valid = JobCreateRequest.model_validate({
        "kind": "knowledge_execution",
        "target": {"repository_id": "repo-a", "system_id": "system-a", "physical_model_path": "model.pdm"},
        "scenario_id": "build-data-model-v1",
    })
    assert valid.target.repository_id == "repo-a"
    for kind in ("full_pipeline", "repository_analysis", "workspace_analysis", "report_build"):
        with pytest.raises(ValidationError):
            JobCreateRequest.model_validate({
                "kind": kind,
                "target": {"repository_id": "repo-a", "system_id": "system-a"},
                "scenario_id": "removed",
            })
    with pytest.raises(ValidationError):
        JobCreateRequest.model_validate({
            "kind": "knowledge_execution",
            "target": {"repository_id": "repo-a", "system_id": "system-a"},
            "scenario_id": "build-data-model-v1",
            "parameters": {"access_token": "must-not-be-persisted"},
        })


def test_job_target_and_repository_credentials_are_strict() -> None:
    with pytest.raises(ValidationError):
        JobTarget(repository_id="repo-a", system_id="")
    with pytest.raises(ValidationError):
        RepositoryDiscoverRequest.model_validate({
            "remotes": [{
                "location": "https://stash.example/scm/project/repository.git",
                "auth": {"username": "user", "access_token": "secret-token"},
            }]
        })


def test_job_target_supports_source_backed_workspace_without_mixing_sources() -> None:
    target = JobTarget(repository_ids=["repo-a", "repo-b"], system_id="workspace")
    assert target.repository_id is None
    assert target.repository_ids == ["repo-a", "repo-b"]
    assert target.knowledge_revisions == []
    with pytest.raises(ValidationError):
        JobTarget(repository_id="repo-a", repository_ids=["repo-b"], system_id="workspace")
    with pytest.raises(ValidationError):
        JobTarget(repository_ids=["repo-a", "repo-a"], system_id="workspace")
