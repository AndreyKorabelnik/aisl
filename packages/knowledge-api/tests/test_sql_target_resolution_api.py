from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_api.sql_query import KnowledgeQueryAdapter


class _FakeKlcQuery:
    def capabilities(self) -> tuple[str, ...]:
        return (
            "common.sql-target-resolution",
            "common.sql-attribute-insertion-context",
            "common.sql-relation-fields",
            "common.sql-analysis",
            "common.sql-field-calculation",
            "common.workspace-sql-catalog",
        )

    def list_sql_relations(self, **kwargs):
        return {"total_count": 1, "items": []}

    def find_sql_target_candidates(self, **kwargs):
        return {
            "schema_version": "sql-target-candidates/v1",
            "filters": kwargs,
            "candidate_count": 1,
            "returned_count": 1,
            "candidates": [
                {
                    "rank": 1,
                    "repo_id": "datamart_profile_fl",
                    "logical_target_name": "epk_client",
                    "target_relation_candidates": ["custom_b2c_profile_fl.epk_client"],
                    "target_kind": "published_or_terminal",
                    "score": 114,
                    "reasons": ["declared_workflow_target"],
                    "workflow_contexts": ["workflow/epk_client.yaml"],
                    "workflow_context_count": 1,
                    "write_observations": [],
                    "read_observations": [],
                    "source_relation_matches": [],
                    "source_column_matches": [
                        {
                            "column_name": "countryresident",
                            "evidence_json": json.dumps([{"file": "sql/epk_client.sql", "line_start": 10}]),
                        }
                    ],
                    "semantic_roles": ["external_source"],
                    "diagnostics": [],
                }
            ],
            "diagnostics": [],
        }

    def get_sql_field_calculation(self, target_relation_name: str, target_column: str, **kwargs):
        return {
            "schema_version": "sql-field-calculation/v1",
            "target_relation_name": target_relation_name,
            "target_column": target_column,
            "repo_id": kwargs.get("repo_id"),
            "calculations": [{"expression": "upper(src.name)", "terminal_sources": [{"relation_name": "src.client", "column_name": "name"}]}],
            "calculation_count": 1,
            "terminal_sources": [{"relation_name": "src.client", "column_name": "name", "source_kind": "physical"}],
            "terminal_source_count": 1,
            "lineage_paths": [{"target_column": target_column, "terminal_relation_name": "src.client", "terminal_column": "name"}],
            "lineage_path_count": 1,
            "lineage_statuses": ["confirmed"],
            "physical_origin_statuses": ["confirmed"],
            "gaps": [],
            "gap_count": 0,
            "gaps_truncated": False,
            "gaps_by_kind": {},
            "coverage_status": "complete",
        }

    def get_workspace_sql_catalog(self):
        return {
            "schema_version": "workspace-sql-catalog/v1",
            "scope_id": "workspace-a",
            "sources": [{"artifact_id": "sql-repo-a", "repository_ids": ["repo-a"]}],
            "source_count": 1,
            "repository_ids": ["repo-a"],
            "repository_count": 1,
            "coverage": {"coverage_status": "complete"},
        }

    def resolve_sql_attribute_insertion_context(self, target_relation: str, **kwargs):
        candidate = self.find_sql_target_candidates(
            repo_id=kwargs.get("repo_id"),
            source_relation_hints=kwargs.get("source_relation_hints"),
            source_column_hints=kwargs.get("source_column_hints"),
            business_entity_hints=[target_relation],
            max_results=kwargs.get("max_results"),
        )["candidates"][0]
        insertion = {
            "rank": 1,
            "repo_id": "datamart_profile_fl",
            "file": "sql/stg_epk_client_birthplace_snp.sql",
            "query_id": "query-1",
            "scope_id": "scope-1",
            "score": 80,
            "reasons": ["source_relation_observed"],
            "matched_relation_hints": ["birthplace"],
            "matched_column_hints": ["regioncode"],
            "relation_matches": [],
            "column_matches": [],
            "source_workflow_contexts": [],
            "source_workflow_targets": ["epk_client"],
            "propagation_status": "probable",
            "propagation_basis": "workflow_context",
            "statements": [
                {
                    "sql_statement_id": "statement-1",
                    "evidence_json": json.dumps([{"file": "sql/stg_epk_client_birthplace_snp.sql"}]),
                }
            ],
            "scope_relations": [],
            "joins": [],
            "projections": [],
            "write_observations": [],
            "diagnostics": [],
        }
        return {
            "schema_version": "sql-attribute-insertion-context/v1",
            "filters": {"target_relation": target_relation, **kwargs},
            "target": {
                "logical_target_name": "epk_client",
                "candidate": candidate,
                "workflow_contexts": ["workflow/epk_client.yaml"],
                "target_sql_files": ["sql/epk_client.sql"],
            },
            "recommended_insertion": insertion,
            "insertion_candidates": [insertion],
            "candidate_count": 1,
            "returned_count": 1,
            "diagnostics": ["recommended_scope_has_no_exact_end_to_end_target_dependency_path"],
        }


class _StaticKnowledgeFactory:
    def __init__(self, adapter: KnowledgeQueryAdapter) -> None:
        self.adapter = adapter

    def get(self, system):
        return self.adapter


def _service(tmp_path: Path) -> KnowledgeDomainService:
    artifact = tmp_path / "knowledge-layer.duckdb"
    artifact.write_bytes(b"fixture")
    adapter = KnowledgeQueryAdapter.__new__(KnowledgeQueryAdapter)
    adapter.query = _FakeKlcQuery()
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    return KnowledgeDomainService(
        settings,
        knowledge_query_factory=_StaticKnowledgeFactory(adapter),
    )


def _publish(client: TestClient, artifact: Path) -> str:
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    assert client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "profile-fl", "display_name": "Profile FL"},
    ).status_code == 201
    execution_result = write_execution_result(
        artifact.parent,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="workspace-sql-catalog",
                schema_version="workspace-sql-catalog/v1",
                materialization_id="workspace-sql-catalog",
                capabilities=(
                    "common.sql-analysis",
                    "common.sql-source-inventory",
                    "common.sql-field-calculation",
                    "common.sql-target-resolution",
                    "common.sql-attribute-insertion-context",
                    "common.workspace-sql-catalog",
                ),
            )
        ],
        scope_id="profile-fl",
        execution_token="run-1",
    )
    response = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
        json=publication_payload(execution_result),
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def test_adapter_normalizes_nested_json_fields() -> None:
    adapter = KnowledgeQueryAdapter.__new__(KnowledgeQueryAdapter)
    adapter.query = _FakeKlcQuery()
    targets = adapter.find_sql_target_candidates(
        repo_id="datamart_profile_fl",
        source_relation_hints=["Individual"],
        source_column_hints=["countryresident"],
        business_entity_hints=["client"],
        max_results=5,
    )
    evidence = targets["candidates"][0]["source_column_matches"][0]["evidence_json"]
    assert evidence == [{"file": "sql/epk_client.sql", "line_start": 10}]

    insertion = adapter.resolve_sql_attribute_insertion_context(
        target_relation="epk_client",
        repo_id="datamart_profile_fl",
        source_relation_hints=["BirthPlace"],
        source_column_hints=["regionCode"],
        max_results=5,
    )
    statement_evidence = insertion["recommended_insertion"]["statements"][0]["evidence_json"]
    assert statement_evidence == [{"file": "sql/stg_epk_client_birthplace_snp.sql"}]


def test_target_candidates_and_insertion_context_http_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "knowledge-layer.duckdb"
    service = _service(tmp_path)
    with TestClient(create_contract_app(service=service)) as client:
        revision_id = _publish(client, artifact)
        targets = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/target-candidates",
            params=[
                ("revision_id", revision_id),
                ("repo_id", "datamart_profile_fl"),
                ("source_relation", "Individual"),
                ("source_column", "countryresident"),
                ("business_entity", "client"),
                ("limit", "5"),
            ],
        )
        insertion = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/attribute-insertion-context",
            params={"revision_id": revision_id},
            json={
                "repo_id": "datamart_profile_fl",
                "target_relation": "epk_client",
                "source_relation_hints": ["BirthPlace"],
                "source_column_hints": ["regionCode"],
                "max_results": 5,
            },
        )
        calculation = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/field-calculation",
            params={
                "revision_id": revision_id,
                "repo_id": "datamart_profile_fl",
                "target_relation": "mart.client_profile",
                "target_column": "normalized_name",
            },
        )
        workspace = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/workspace-catalog",
            params={"revision_id": revision_id},
        )
        invalid = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/attribute-insertion-context",
            json={
                "target_relation": "epk_client",
                "source_relation_hints": [],
            },
        )

    assert targets.status_code == 200, targets.text
    target_payload = targets.json()
    assert target_payload["revision_id"] == revision_id
    assert target_payload["candidate_schema_version"] == "sql-target-candidates/v1"
    assert target_payload["candidates"][0]["logical_target_name"] == "epk_client"
    assert target_payload["candidates"][0]["source_column_matches"][0]["evidence_json"] == [
        {"file": "sql/epk_client.sql", "line_start": 10}
    ]

    assert insertion.status_code == 200, insertion.text
    insertion_payload = insertion.json()
    assert insertion_payload["revision_id"] == revision_id
    assert insertion_payload["insertion_schema_version"] == "sql-attribute-insertion-context/v1"
    assert insertion_payload["target"]["logical_target_name"] == "epk_client"
    assert insertion_payload["recommended_insertion"]["file"].endswith(
        "stg_epk_client_birthplace_snp.sql"
    )
    assert insertion_payload["recommended_insertion"]["statements"][0]["evidence_json"] == [
        {"file": "sql/stg_epk_client_birthplace_snp.sql"}
    ]
    assert calculation.status_code == 200, calculation.text
    calculation_payload = calculation.json()
    assert calculation_payload["calculation_schema_version"] == "sql-field-calculation/v1"
    assert calculation_payload["coverage_status"] == "complete"
    assert calculation_payload["terminal_sources"][0]["relation_name"] == "src.client"

    assert workspace.status_code == 200, workspace.text
    workspace_payload = workspace.json()
    assert workspace_payload["catalog_schema_version"] == "workspace-sql-catalog/v1"
    assert workspace_payload["repository_ids"] == ["repo-a"]

    assert invalid.status_code == 422
