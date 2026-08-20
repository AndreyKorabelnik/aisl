from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from aisl_reporting import ReportRequest, prepare_report
from aisl_reporting.knowledge_api import KnowledgeApiSourceError


def _transport(database_path: Path, *, include_effective: bool = True, database_uri: str | None = None, include_lineage: bool = False) -> httpx.MockTransport:
    artifact = {
        "artifact_id": "artifact-effective",
        "model_kind": "effective-data-model",
        "schema_version": "effective-data-model/v1",
        "source_materialization_id": "effective-data-model",
        "content_fingerprint": "a" * 64,
        "physical_artifacts": [
            {
                "role": "database",
                "uri": database_uri or database_path.resolve().as_uri(),
                "sha256": "b" * 64,
                "media_type": "application/vnd.duckdb",
                "schema_version": "effective-data-model/v1",
                "filename": database_path.name,
            },
            {
                "role": "manifest",
                "uri": database_path.resolve().as_uri(),
                "sha256": "c" * 64,
                "media_type": "application/json",
                "schema_version": "knowledge_layer/v1",
                "filename": "knowledge-layer-manifest.json",
            },
        ],
        "capabilities": ["common.effective-data-model", "common.cross-layer-data-model"],
        "coverage": {"status": "complete"},
        "diagnostics": [],
    }
    physical = {
        **artifact,
        "artifact_id": "artifact-physical",
        "model_kind": "physical-data-model",
        "schema_version": "knowledge_layer_physical_model/v1",
        "source_materialization_id": "physical-model",
        "content_fingerprint": "d" * 64,
        "capabilities": ["common.physical-model", "common.physical-model.tables"],
    }
    lineage_artifact = {
        **artifact,
        "artifact_id": "artifact-cross-lineage",
        "model_kind": "cross-artifact-data-model-mapping",
        "schema_version": "cross-artifact-data-model-mapping/v3",
        "source_materialization_id": "cross-artifact-data-model-mapping",
        "content_fingerprint": "1" * 64,
        "capabilities": ["common.cross-artifact-data-model-mapping", "common.logical-field-physical-lineage"],
    }
    artifacts = ([artifact] if include_effective else []) + [physical] + ([lineage_artifact] if include_lineage else [])
    revision = {
        "system_id": "client-profile",
        "revision_id": "rev-1",
        "ordinal": 1,
        "state": "active",
        "created_at": "2026-08-05T12:00:00Z",
        "execution": {
            "schema_version": "knowledge_execution_result/v1",
            "status": "completed",
            "runner_version": "0.9.51",
            "result_fingerprint": "e" * 64,
            "plan_fingerprint": "f" * 64,
            "knowledge_profile_id": "profile-effective",
            "scope_kind": "repository",
            "scope_id": "repo-client-profile",
            "started_at": "2026-08-05T11:59:00Z",
            "completed_at": "2026-08-05T12:00:00Z",
            "semantic_policy": {},
        },
        "execution_result": {key: value for key, value in artifact["physical_artifacts"][1].items() if key != "role"},
        "knowledge_artifacts": artifacts,
        "capabilities": sorted({cap for item in artifacts for cap in item["capabilities"]}),
        "labels": [],
        "metadata": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        if path == "/api/knowledge/v1/systems/client-profile":
            return httpx.Response(200, json={"system_id": "client-profile", "active_revision_id": "rev-1"})
        if path == "/api/knowledge/v1/systems/client-profile/revisions/rev-1":
            return httpx.Response(200, json=revision)
        if path == "/api/knowledge/v1/systems/client-profile/data-model/tables":
            return httpx.Response(200, json={
                "schema_version": "knowledge_api/v1",
                "system_id": "client-profile",
                "revision_id": "rev-1",
                "items": [{
                    "table_id": "entity-customer",
                    "table_name": "Customer",
                    "table_kind": "effective_entity",
                    "description": "Customer entity; physical table customer_tbl.",
                    "field_count": 2,
                    "relationship_count": 1,
                    "fields": [
                        {"name": "id", "type": "Long", "inherited": False},
                        {"name": "address", "type": "Address", "inherited": False},
                    ],
                }],
                "page": {"offset": 0, "limit": 500, "total": 1},
            })
        if path == "/api/knowledge/v1/systems/client-profile/data-model/tables/entity-customer":
            return httpx.Response(200, json={
                "schema_version": "knowledge_api/v1",
                "system_id": "client-profile",
                "revision_id": "rev-1",
                "object": {"id": "entity-customer", "name": "Customer", "kind": "effective_entity"},
                "fields": [
                    {"name": "id", "type": "Long", "inherited": False, "storage_observation_count": 0, "storage_observations": []},
                    {"name": "address", "type": "Address", "target_object": "Address", "inherited": False, "storage_observation_count": 0, "storage_observations": []},
                ],
                "keys": [{"kind": "primary", "fields": ["id"], "provenance": {}}],
                "relationships": [{
                    "relationship_id": "relationship-address",
                    "kind": "many_to_one",
                    "source_field": "address",
                    "cardinality": "one",
                    "target": {"object": {"id": "entity-address", "name": "Address", "kind": "effective_entity"}},
                    "join": {"method": "physical_model_relationship", "source_fields": ["address_id"], "target_fields": ["id"], "requires_encoding_interpretation": False, "physical_join_confirmed": True},
                }],
                "embedded_objects": [], "relationship_candidate_count": 0,
                "indexes": [], "constraints": [], "partitioning": [], "triggers": [],
            })
        if path == "/api/knowledge/v1/systems/client-profile/coverage":
            return httpx.Response(200, json={
                "schema_version": "analysis_coverage/v1",
                "system_id": "client-profile", "revision_id": "rev-1", "status": "complete",
                "statement": "Coverage from effective model.", "count_basis": "materialized rows",
                "summary": {"repository_count": 1, "observed_fact_count": 4, "known_gap_count": 0, "unresolved_count": 0, "conflicting_count": 0, "unsupported_count": 0, "not_observed_count": 0, "requires_interpretation_count": 0, "physical_join_observation_count": 1},
                "domains": {
                    "source_facts": {"status": "available", "observed_fact_count": 4},
                    "data_model": {"status": "complete", "relationship_count": 1, "unresolved_relationship_candidate_count": 0},
                    "physical_storage": {"status": "available", "storage_evidence_relationship_count": 1, "requires_interpretation_count": 0, "physical_join_observation_count": 1},
                    "analysis_gaps": {"status": "complete", "known_gap_count": 0, "status_counts": {}},
                },
                "limitations": [], "limitations_total_groups": 0, "limitations_truncated": False,
            })
        if path == "/api/knowledge/v1/systems/client-profile/physical-model":
            return httpx.Response(200, json={"schema_version": "knowledge_api/v1", "physical_model_schema_version": "physical-model-query/v1", "system_id": "client-profile", "revision_id": "rev-1", "sources": [], "counts": {"tables": 1, "relationships": 1}, "relationship_resolution": {"resolved": 1}, "key_kinds": {"primary": 1}, "gap_kinds": {}})
        if path == "/api/knowledge/v1/systems/client-profile/physical-model/tables":
            return httpx.Response(200, json={
                "schema_version": "knowledge_api/v1", "physical_model_schema_version": "physical-model-query/v1", "system_id": "client-profile", "revision_id": "rev-1",
                "items": [{"physical_model_table_id": "table-customer", "physical_model_source_id": "pdm-1", "table_name": "Customer", "table_code": "customer_tbl", "column_count": 2, "key_count": 1, "columns": [{"physical_model_column_id": "col-id", "physical_model_source_id": "pdm-1", "column_code": "id", "data_type": "bigint"}, {"physical_model_column_id": "col-address", "physical_model_source_id": "pdm-1", "column_code": "address_id", "data_type": "bigint"}]}],
                "page": {"offset": 0, "limit": 500, "total": 1},
            })
        if path == "/api/knowledge/v1/systems/client-profile/physical-model/relationships":
            return httpx.Response(200, json={
                "schema_version": "knowledge_api/v1", "physical_model_schema_version": "physical-model-query/v1", "system_id": "client-profile", "revision_id": "rev-1",
                "items": [{"physical_model_relationship_id": "fk-customer-address", "physical_model_source_id": "pdm-1", "child_table_code": "customer_tbl", "parent_table_code": "address_tbl", "cardinality": "many_to_one", "joins": [{"child_column_code": "address_id", "parent_column_code": "id"}], "resolution_status": "resolved"}],
                "page": {"offset": 0, "limit": 500, "total": 1},
            })
        if path == "/api/knowledge/v1/systems/client-profile/data-model/lineage":
            return httpx.Response(200, json={
                "schema_version": "knowledge_api/v1", "lineage_schema_version": "data-model-lineage-query/v1",
                "system_id": "client-profile", "revision_id": "rev-1", "filters": {},
                "items": [
                    {"lineage_id":"l1","logical_fully_qualified_name":"example.Customer","logical_field_name":"id","storage_alias":"example.Customer","source_sql_relation":"example_customer","source_sql_usage_role":"projection","source_sql_file":"src.sql","source_sql_column_name":"id","workflow_context_file":"wf.yaml","target_table_code":"customer_tbl","physical_model_table_id":"pt","physical_model_column_id":"pc1","physical_column_code":"id","transform_sql_file":"target.sql","target_projection_expression":"cast(id as bigint)","knowledge_class":"derived","mapping_basis":"observed","projection_path":["p1"],"materialization_path":["m1"],"workflow_dependency_path":[],"provenance":{}},
                    {"lineage_id":"l2","logical_fully_qualified_name":"example.Customer","logical_field_name":"address","storage_alias":"example.Customer","source_sql_relation":"example_customer","source_sql_usage_role":"projection","source_sql_file":"src.sql","source_sql_column_name":"address","workflow_context_file":"wf.yaml","target_table_code":"customer_tbl","physical_model_table_id":"pt","physical_model_column_id":"pc2","physical_column_code":"address_id","transform_sql_file":"target.sql","target_projection_expression":"address as address_id","knowledge_class":"derived","mapping_basis":"observed","projection_path":["p2"],"materialization_path":["m1"],"workflow_dependency_path":[],"provenance":{}}
                ],
                "page": {"offset": 0, "limit": 500, "total": 2},
                "summary": {"path_count":2,"logical_field_count":2,"target_table_count":1,"target_column_count":2,"source_sql_file_count":1,"transform_sql_file_count":1,"by_knowledge_class":{"derived":2}},
            })
        if path == "/api/knowledge/v1/systems/client-profile/physical-model/gaps":
            return httpx.Response(200, json={"schema_version": "knowledge_api/v1", "physical_model_schema_version": "physical-model-query/v1", "system_id": "client-profile", "revision_id": "rev-1", "items": [], "page": {"offset": 0, "limit": 500, "total": 0}})
        return httpx.Response(404, json={"detail": {"path": path, "params": params}})

    return httpx.MockTransport(handler)


def test_data_model_report_is_built_from_api_revision(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        api_transport=_transport(database),
        detail_level="standard",
    )
    prepared = prepare_report(request)
    dataset = prepared.dataset
    assert dataset["coverage"]["report_mode"] == "logical_and_physical"
    assert dataset["coverage"]["model_object_count"] == 1
    assert dataset["coverage"]["physical_object_count"] == 1
    assert dataset["request"]["knowledge_source"]["selected_artifact"]["model_kind"] == "effective-data-model"
    assert dataset["interpretation_policy"]["no_legacy_combined_database"] is True
    assert dataset["sections"]["diagrams"]["logical_er"]["relationship_count"] == 1
    assert dataset["sections"]["diagrams"]["physical_er"]["declared_relationship_count"] == 1
    compact_field = dataset["sections"]["selected_objects"][0]["fields"][0]
    assert compact_field == {"name": "id", "type": "Long"}
    compact_table = dataset["sections"]["physical_model_observations"]["representative_objects"][0]
    assert "physical_model_source_id" not in compact_table
    assert "physical_model_column_id" not in compact_table["columns"][0]
    assert dataset["validation"]["dataset_bytes"] < 500_000


def test_missing_required_knowledge_fails_without_fallback(tmp_path: Path) -> None:
    database = tmp_path / "physical.duckdb"
    database.write_bytes(b"fixture")
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        api_transport=_transport(database, include_effective=False),
    )
    with pytest.raises(KnowledgeApiSourceError, match="does not provide knowledge required"):
        prepare_report(request)


def test_api_projection_does_not_require_shared_file_system(tmp_path: Path) -> None:
    database = tmp_path / "not-shared.duckdb"
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        api_transport=_transport(
            database,
            database_uri="s3://knowledge-artifacts/effective-model.duckdb",
        ),
    )

    prepared = prepare_report(request)

    assert prepared.dataset["coverage"]["model_object_count"] == 1
    assert prepared.dataset["request"]["knowledge_source"]["selected_artifact"]["model_kind"] == "effective-data-model"


def test_built_report_manifest_preserves_resolved_revision(tmp_path: Path) -> None:
    from aisl_reporting.pipeline import build_report
    from aisl_reporting.renderer import FileRenderer

    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    response = tmp_path / "response.md"
    headings = [
        "Краткий вывод", "Область отчёта", "Резюме модели данных", "ER-диаграммы",
        "Каталог объектов", "Детальное описание ключевых объектов", "Атрибуты и наследование",
        "Ключи", "Связи и правила JOIN", "Справочники", "Межрепозиторные соответствия",
        "Физическая модель", "Архитектурные и бизнес-выводы",
        "Приложение A. Полнота анализа и ограничения доказательности",
        "Приложение B. Неоднозначности и вопросы для уточнения",
        "Приложение C. Технические доказательства и provenance",
    ]
    response.write_text("\n\n".join(f"# {heading}\n\nТест." for heading in headings), encoding="utf-8")
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        api_transport=_transport(database),
    )

    manifest = build_report(request, tmp_path / "out", FileRenderer(response), heartbeat_sec=0)

    assert manifest.request.revision_id == "rev-1"
    assert manifest.to_dict()["request"]["knowledge_api"]["revision_id"] == "rev-1"


def test_data_model_report_consumes_cross_artifact_lineage(tmp_path: Path) -> None:
    database = tmp_path / "effective.duckdb"
    database.write_bytes(b"fixture")
    request = ReportRequest(
        report_type="data-model-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="client-profile",
        api_transport=_transport(database, include_lineage=True),
        detail_level="standard",
    )
    dataset = prepare_report(request).dataset
    assert dataset["coverage"]["knowledge_layer_counts"]["cross_artifact_lineage_paths"] == 2
    assert dataset["sections"]["field_lineage"]["unique_correspondence_count"] == 2
    assert dataset["sections"]["transformations"]["count"] == 2
    assert dataset["sections"]["data_journeys"]["count"] == 1
    observed = dataset["sections"]["diagrams"]["observed_usage"]
    assert observed["status"] == "observed"
    assert observed["relationship_count"] == 2
    assert observed["relationships"][0]["target_table"] == "customer_tbl"
    assert dataset["validation"]["dataset_bytes"] < 500_000


def test_lineage_priority_selects_only_unique_exact_logical_names() -> None:
    from aisl_reporting.profiles.data_model_report.v1.builder import _select
    items = [
        {"table_id":"individual","table_name":"Individual","field_count":10,"relationship_count":5},
        {"table_id":"builder-a","table_name":"Builder","field_count":100,"relationship_count":100},
        {"table_id":"builder-b","table_name":"Builder","field_count":90,"relationship_count":90},
        {"table_id":"other","table_name":"Other","field_count":50,"relationship_count":50},
    ]
    selected, status = _select(items, (), 2, preferred_names=("Individual", "Builder"))
    assert [item["table_id"] for item in selected] == ["individual", "builder-a"]
    assert status == "lineage_prioritized"
