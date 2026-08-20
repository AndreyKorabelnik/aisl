from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_api.data_model_models import (
    DataObjectRef,
    FieldCatalogField,
    FieldCatalogResponse,
    FieldCatalogTable,
    TableDetailResponse,
    TableField,
    TableFieldStorageEvidenceRef,
    TableFieldStorageObservation,
    TableKey,
    TableRelationship,
    TableRelationshipSummary,
)
from knowledge_api.query_source import KnowledgeArtifactSource
from knowledge_api.effective_data_model_query import DataObjectNotFoundError


class FakeDataModelApiService:
    def analysis_coverage(self, system_id: str) -> dict:
        return {
            "schema_version": "analysis_coverage/v1",
            "status": "partial",
            "statement": "Coverage describes observed facts and known limitations; absence of evidence does not prove absence in source systems.",
            "count_basis": "diagnostic_occurrences_not_unique_business_elements",
            "summary": {
                "repository_count": 1,
                "observed_fact_count": 42,
                "known_gap_count": 3,
                "unresolved_count": 3,
                "conflicting_count": 0,
                "unsupported_count": 0,
                "not_observed_count": 0,
                "requires_interpretation_count": 1,
                "physical_join_observation_count": 2,
            },
            "domains": {
                "source_facts": {"status": "observed", "observed_fact_count": 42},
                "data_model": {"status": "partial", "relationship_count": 5, "unresolved_relationship_candidate_count": 1},
                "physical_storage": {"status": "requires_interpretation", "storage_evidence_relationship_count": 1, "requires_interpretation_count": 1, "physical_join_observation_count": 2},
                "analysis_gaps": {"status": "observed", "known_gap_count": 3, "status_counts": {"unresolved": 3}},
            },
            "limitations": [{
                "source": "workspace_missing_fact",
                "status": "unresolved",
                "repo_id": "repo-a",
                "category": "resolution",
                "kind": "source_expression_not_resolved",
                "required_for_operation": "field_flow",
                "count": 3,
            }],
            "limitations_total_groups": 1,
            "limitations_truncated": False,
        }

    def field_catalog(self, system_id: str) -> FieldCatalogResponse:
        return FieldCatalogResponse(
            system_id=system_id,
            tables=[
                FieldCatalogTable(
                    table_id="replica:example.Individual",
                    table_name="Individual",
                    description="Физическое лицо",
                    fields=[FieldCatalogField(field_name="id", description="Идентификатор")],
                )
            ],
        )

    def relationship_counts(self) -> dict[str, int]:
        return {"replica:example.Individual": 1}

    def table_detail(self, system_id: str, table_id: str) -> TableDetailResponse:
        if table_id == "missing":
            raise DataObjectNotFoundError(table_id)
        return TableDetailResponse(
            schema_version="data_model_api/v4",
            system_id=system_id,
            workspace_id="workspace-1",
            build_id="build-1",
            generated_at="2026-07-28T10:00:00+00:00",
            object=DataObjectRef(id=table_id, name="Individual", kind="replica"),
            fields=[TableField(
                name="id",
                type="long",
                storage_observation_count=1,
                storage_observations=[TableFieldStorageObservation(
                    physical_field_name="id",
                    operation="primitiveField",
                    object_alias="example.Individual",
                    value_expression="individual.getId()",
                    converter_owner_fqcn="example.IndividualConverter",
                    converter_method="convert",
                    call_observation_id="call-id",
                    match_basis="exact_converter_alias_and_exact_model_field_name",
                    value_mapping_status="observed_expression_not_semantically_interpreted",
                    evidence_ids=["evidence-field-id"],
                    evidence_refs=[TableFieldStorageEvidenceRef(
                        evidence_id="evidence-field-id",
                        repo_id="repo-a",
                        path="src/IndividualConverter.java",
                        line_start=12,
                        line_end=12,
                        extractor="java_tree_sitter",
                        maturity="observed",
                        role="physical_field_name",
                    )],
                )],
            )],
            keys=[TableKey(kind="replica_key", fields=["id"], collocation_field="id")],
            relationships=[
                TableRelationshipSummary(
                    relationship_id="relationship-birth-country",
                    kind="reference",
                    source_field="birthCountry",
                    cardinality="one",
                    target={
                        "object": {
                            "id": "dictionary:example.Country",
                            "name": "Country",
                            "kind": "dictionary",
                        }
                    },
                    join={
                        "method": "logical_key_correspondence",
                        "source_fields": ["birthCountry"],
                        "target_fields": ["code"],
                        "target_kind": "logical_identity",
                        "requires_encoding_interpretation": False,
                        "physical_join_confirmed": False,
                    },
                )
            ],
        )

    def relationship_detail(self, table_id: str, relationship_id: str) -> TableRelationship:
        if table_id == "missing":
            raise DataObjectNotFoundError(table_id)
        if relationship_id != "relationship-birth-country":
            from knowledge_api.effective_data_model_query import RelationshipNotFoundError
            raise RelationshipNotFoundError(relationship_id)
        return TableRelationship(
            relationship_id="relationship-birth-country",
            kind="reference",
            source={"field": "birthCountry", "cardinality": "one"},
            target={
                "object": DataObjectRef(id="dictionary:example.Country", name="Country", kind="dictionary"),
                "aliases": [],
                "logical_identity": {
                    "status": "observed",
                    "fields": ["code"],
                    "version_fields": [],
                    "collocation_fields": [],
                    "classification_basis": "observed_key_member_role",
                },
                "storage_key": {"status": "not_observed", "fields": [], "expressions": [], "evidence": []},
            },
            reference={
                "assignment_operations": [],
                "value_origins": [],
                "encoding_inputs": {
                    "type_component": {"source": "target_alias", "values": []},
                    "key_component": {"source": "target_storage_key", "fields": []},
                },
                "physical_encoding": {"status": "not_observed"},
            },
            join={
                "method": "logical_key_correspondence",
                "source": {"field": "birthCountry"},
                "target": {"kind": "logical_identity", "fields": ["code"]},
                "requires_encoding_interpretation": False,
                "physical_join_confirmed": False,
            },
            provenance={"evidence_ids": ["evidence-1"]},
        )


class StaticFactory:
    def __init__(self) -> None:
        self.service = FakeDataModelApiService()
        self.system_ids: list[str] = []

    def get(self, system: KnowledgeArtifactSource) -> FakeDataModelApiService:
        self.system_ids.append(system.system_id)
        return self.service

from knowledge_api.contract_v1.contract import create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings, sha256_file
from knowledge_api.contract_v1.service import KnowledgeDomainService


@pytest.fixture
def canonical_artifacts(tmp_path: Path) -> dict[str, Path]:
    from tests.execution_fixtures import KnowledgeArtifactSpec, write_execution_result

    root = tmp_path / "published"
    root.mkdir()
    knowledge = root / "effective-data-model.duckdb"
    knowledge.write_bytes(b"effective data model fixture")
    execution_result = write_execution_result(
        root,
        [
            KnowledgeArtifactSpec(
                database=knowledge,
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
            )
        ],
        profile_id="canonical-profile",
        scope_id="ucp",
        execution_token="job-123",
    )
    return {
        "root": root,
        "knowledge": knowledge,
        "execution_result": execution_result,
    }


@pytest.fixture
def canonical_service(tmp_path: Path, canonical_artifacts: dict[str, Path]) -> KnowledgeDomainService:
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(canonical_artifacts["root"],),
    )
    return KnowledgeDomainService(settings, query_factory=StaticFactory())


@pytest.fixture
def canonical_client(canonical_service: KnowledgeDomainService) -> TestClient:
    return TestClient(create_contract_app(service=canonical_service))


@pytest.fixture
def canonical_publication(canonical_artifacts: dict[str, Path]) -> dict:
    from tests.execution_fixtures import publication_payload

    return publication_payload(
        canonical_artifacts["execution_result"],
    )
