from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prepared_knowledge_runtime import KnowledgeLayerQuery
from knowledge_layer_core.materialization_runtime import (
    MATERIALIZATION_REQUEST_SCHEMA_VERSION,
    materialize,
)
from prepared_knowledge_runtime import ReportingQueryService


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _envelope(root: Path, *, kind: str, version: str, payload: dict) -> Path:
    path = root / "evidence" / f"{kind}.json"
    value = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_id": f"artifact-{kind}",
        "artifact_kind": kind,
        "schema_version": version,
        "content_fingerprint": hashlib.sha256(kind.encode()).hexdigest(),
        "producer": {"component": "code-analyzer-core", "analyzer_id": f"{kind}-analyzer", "analyzer_version": "0.44.2"},
        "source_snapshot": {"source_id": "repo-a", "fingerprint": "source-fingerprint"},
        "coverage": {"coverage_status": "complete"},
        "diagnostics": [],
        "provenance": {},
        "payload": payload,
    }
    _write_json(path, value)
    return path


def _request(materialization_id: str, path: Path, kind: str, version: str) -> dict:
    return {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": materialization_id,
        "scope_id": "repo-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": f"artifact-{kind}",
                "artifact_kind": kind,
                "schema_version": version,
                "content_fingerprint": hashlib.sha256(kind.encode()).hexdigest(),
                "location": {"kind": "file", "path": str(path)},
            }],
            "knowledge_artifacts": [],
        },
        "parameters": {},
    }


def test_system_description_materializes_typed_records_without_task_semantics(tmp_path: Path) -> None:
    evidence = tmp_path / "input"
    compact = evidence / "evidence" / "subject-knowledge-payload" / "compact"
    _write_json(compact / "system_interface_catalog.json", {"all_interfaces": [{"interface_id": "api-1", "protocol": "http"}]})
    _write_json(compact / "system_scenarios.json", [{"scenario_id": "scenario-1", "name": "Lookup"}])
    path = _envelope(evidence, kind="system-description-evidence", version="system-description-evidence/v1", payload={
        "artifacts": [
            {"artifact_name": "system_interface_catalog.json", "relative_path": "subject-knowledge-payload/compact/system_interface_catalog.json", "sections": ["all_interfaces"]},
            {"artifact_name": "system_scenarios.json", "relative_path": "subject-knowledge-payload/compact/system_scenarios.json", "sections": []},
        ]
    })
    result = materialize(_request("system-description", path, "system-description-evidence", "system-description-evidence/v1"), tmp_path / "system")
    assert result["status"] == "completed"
    query = KnowledgeLayerQuery(Path(result["output"]["manifest_path"]).parent)
    assert "common.system-description" in query.capabilities()
    interfaces = query.system_interfaces()
    assert interfaces["total_count"] == 1
    item = interfaces["items"][0]
    assert item["materialization_id"] == "system-description"
    assert "task_id" not in item and "profile_id" not in item
    assert query.system_scenarios()["total_count"] == 1


def test_reference_data_materializes_jsonl_sections_without_task_semantics(tmp_path: Path) -> None:
    evidence = tmp_path / "input"
    detail = evidence / "evidence" / "subject-knowledge-payload" / "compact" / "reference_data_fact_base"
    detail.mkdir(parents=True)
    row = {"declared_value_set_id": "status-values", "name": "Status", "values": ["ACTIVE", "BLOCKED"]}
    (detail / "declared_value_sets.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    physical_row = {
        "fact_id": "column-bank-code",
        "fact_type": "db_schema_column",
        "name": "corporateclients_request_log",
        "properties": {
            "table_name": "corporateclients_request_log",
            "column_name": "bank_code",
            "description": "must correspond to TERBANK reference data",
            "source_set": "production",
        },
        "evidence": [{"file_path": "db/changelog/terbank.sql", "line_start": 10, "line_end": 10, "extractor": "db_schema_scan"}],
    }
    (detail / "physical_attributes.jsonl").write_text(json.dumps(physical_row) + "\n", encoding="utf-8")
    path = _envelope(evidence, kind="reference-data-evidence", version="reference-data-evidence/v1", payload={
        "sections": [
            {
                "section": "declared_value_sets",
                "relative_path": "subject-knowledge-payload/compact/reference_data_fact_base/declared_value_sets.jsonl",
                "records_count": 1,
                "format": "jsonl",
            },
            {
                "section": "physical_attributes",
                "relative_path": "subject-knowledge-payload/compact/reference_data_fact_base/physical_attributes.jsonl",
                "records_count": 1,
                "format": "jsonl",
            },
        ]
    })
    result = materialize(_request("reference-data", path, "reference-data-evidence", "reference-data-evidence/v1"), tmp_path / "reference")
    assert result["status"] == "completed"
    query = KnowledgeLayerQuery(Path(result["output"]["manifest_path"]).parent)
    assert "common.reference-data" in query.capabilities()
    records = query.reference_data_records(record_kind="declared_value_sets")
    assert records["total_count"] == 1
    item = records["items"][0]
    assert item["materialization_id"] == "reference-data"
    assert "task_id" not in item and "profile_id" not in item


def test_standalone_system_description_supports_reporting_facade(tmp_path: Path) -> None:

    evidence = tmp_path / "input"
    compact = evidence / "evidence" / "subject-knowledge-payload" / "compact"
    _write_json(compact / "system_interface_catalog.json", {"all_interfaces": [{
        "interface_id": "api-1", "protocol": "rest", "direction": "inbound",
        "boundary_kind": "rest_request", "operation": "ProfileController.load",
        "endpoint_or_topic_resolved": "/profile", "evidence_refs": [],
    }]})
    _write_json(compact / "system_scenarios.json", [{
        "scenario_id": "scenario-1", "operation": "ProfileController.load",
        "entrypoints": [{"boundary_role": "rest_request"}],
        "storage_touches": [{"storage_target": "PROFILE"}], "external_calls": [],
    }])
    _write_json(compact / "external_dependencies.json", [{
        "dependency_kind": "gradle_artifact", "name": "org.springframework:spring-web:1.0",
        "source_set": "main", "is_test_source": False,
        "evidence": [{"file": "client-profile-app/build.gradle", "line_start": 10, "extractor": "gradle_source_declaration"}],
    }])
    _write_json(compact / "storage_usage_summaries.json", [{
        "storage_usage_summary_id": "storage-1", "storage_target": "PROFILE", "access_count": 3,
        "operation_count": 2, "read_count": 2, "write_count": 1, "mutation_count": 0,
        "source_sets": ["main"], "evidence": [],
    }])
    path = _envelope(evidence, kind="system-description-evidence", version="system-description-evidence/v1", payload={
        "artifacts": [
            {"artifact_name": "system_interface_catalog.json", "relative_path": "subject-knowledge-payload/compact/system_interface_catalog.json", "sections": ["all_interfaces"]},
            {"artifact_name": "system_scenarios.json", "relative_path": "subject-knowledge-payload/compact/system_scenarios.json", "sections": []},
            {"artifact_name": "external_dependencies.json", "relative_path": "subject-knowledge-payload/compact/external_dependencies.json", "sections": []},
            {"artifact_name": "storage_usage_summaries.json", "relative_path": "subject-knowledge-payload/compact/storage_usage_summaries.json", "sections": []},
        ]
    })
    result = materialize(_request("system-description", path, "system-description-evidence", "system-description-evidence/v1"), tmp_path / "system-reporting")
    service = ReportingQueryService(Path(result["output"]["manifest_path"]).parent)

    assert service.get_repository_composition().summary["module_count"] == 1
    assert service.get_technologies().summary["declared_dependency_count"] == 1
    assert service.list_data_objects().summary["table_count"] == 1
    assert service.get_representative_journeys().items[0]["is_complete"] is True
    assert service.get_analysis_coverage().items[0]["status"] == "complete"


def test_standalone_reference_data_query_does_not_require_code_declared_model(tmp_path: Path) -> None:
    from prepared_knowledge_runtime.reference_data_queries import ReferenceDataQueryService

    evidence = tmp_path / "input-query"
    detail = evidence / "evidence" / "subject-knowledge-payload" / "compact" / "reference_data_fact_base"
    detail.mkdir(parents=True)
    row = {
        "fact_id": "declared-value-set-status",
        "fact_type": "declared_value_set",
        "name": "Status",
        "properties": {
            "declared_value_set_id": "status-values",
            "syntax_kind": "java_enum",
            "name": "Status",
            "entries_count": 2,
            "sample_entries": [
                {"key": "ACTIVE", "value": "ACTIVE"},
                {"key": "BLOCKED", "value": "BLOCKED"},
            ],
            "source_set": "production",
        },
        "evidence": [{"file_path": "src/main/java/Status.java", "line_start": 1, "line_end": 4, "extractor": "declared_value_scan"}],
    }
    (detail / "declared_value_sets.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    physical_row = {
        "fact_id": "column-bank-code",
        "fact_type": "db_schema_column",
        "name": "corporateclients_request_log",
        "properties": {
            "table_name": "corporateclients_request_log",
            "column_name": "bank_code",
            "description": "must correspond to TERBANK reference data",
            "source_set": "production",
        },
        "evidence": [{"file_path": "db/changelog/terbank.sql", "line_start": 10, "line_end": 10, "extractor": "db_schema_scan"}],
    }
    (detail / "physical_attributes.jsonl").write_text(json.dumps(physical_row) + "\n", encoding="utf-8")
    path = _envelope(evidence, kind="reference-data-evidence", version="reference-data-evidence/v1", payload={
        "sections": [
            {
                "section": "declared_value_sets",
                "relative_path": "subject-knowledge-payload/compact/reference_data_fact_base/declared_value_sets.jsonl",
                "records_count": 1,
                "format": "jsonl",
            },
            {
                "section": "physical_attributes",
                "relative_path": "subject-knowledge-payload/compact/reference_data_fact_base/physical_attributes.jsonl",
                "records_count": 1,
                "format": "jsonl",
            },
        ]
    })
    result = materialize(_request("reference-data", path, "reference-data-evidence", "reference-data-evidence/v1"), tmp_path / "reference-query")
    service = ReferenceDataQueryService(Path(result["output"]["manifest_path"]).parent)

    search = service.search_reference_data(token="Status", max_results=10)
    assert search.page.total_count == 1
    assert search.items[0]["reference_object_id"] == "status-values"
    assert search.summary["dictionary_object_enrichment_available"] is False
    assert search.summary["official_nsi_status_established"] is False

    detail_result = service.get_reference_data_object("status-values")
    assert detail_result.page.total_count == 1
    assert detail_result.items[0]["representation_kind"] == "declared_value_set"

    usage = service.get_usage_observations(token="TERBANK")
    assert usage.summary["section_counts"]["physical_attributes"] == 1
    assert usage.items[0]["observation_kind"] == "physical_attributes"
    assert usage.items[0]["properties"]["description"] == "must correspond to TERBANK reference data"


def test_reference_data_candidate_context_searches_after_aggregation(tmp_path: Path) -> None:
    from prepared_knowledge_runtime.reference_data_queries import ReferenceDataQueryService

    evidence = tmp_path / "input-reference-context"
    detail = evidence / "evidence" / "subject-knowledge-payload" / "compact" / "reference_data_fact_base"
    detail.mkdir(parents=True)
    rows = {
        "declared_value_sets.jsonl": {
            "fact_id": "set-mobileoperator",
            "fact_type": "declared_value_set",
            "name": "99.18.MOBILEOPERATOR_dml_literal_rows",
            "properties": {
                "declared_value_set_id": "mobileoperator-values",
                "syntax_kind": "sql_values_rows",
                "entries_count": 2,
                "sample_entries": [{"key": "01", "value": "Operator A"}, {"key": "02", "value": "Operator B"}],
                "source_set": "production",
            },
            "evidence": [{"file_path": "db/99.18.MOBILEOPERATOR_dml.sql", "line_start": 4, "extractor": "sql_values"}],
        },
        "literal_data_writes.jsonl": {
            "fact_id": "write-mobileoperator",
            "fact_type": "literal_data_write",
            "name": "seed mobile operator",
            "properties": {
                "literal_data_write_id": "write-mobileoperator",
                "target_table": "placeholder.mobileoperator",
                "operation": "insert",
                "columns": ["operatorid", "operatorname"],
                "values": {"operatorid": "01", "operatorname": "Operator A"},
                "source_set": "production",
            },
            "evidence": [{"file_path": "db/99.18.MOBILEOPERATOR_dml.sql", "line_start": 4, "extractor": "sql_insert"}],
        },
        "physical_assets.jsonl": {
            "fact_id": "table-mobileoperator",
            "fact_type": "db_schema_table",
            "name": "mbk_cache.mobileoperator",
            "properties": {
                "table_name": "mobileoperator",
                "qualified_table_name": "mbk_cache.mobileoperator",
                "description": "Таблица определяет операторов мобильной связи",
                "source_set": "production",
            },
            "evidence": [{"file_path": "db/59.MOBILEOPERATOR_ddl.sql", "line_start": 4, "extractor": "sql_create_table"}],
        },
        "join_observations.jsonl": {
            "fact_id": "join-mobileoperator",
            "fact_type": "join_observation",
            "name": "link->mobileoperator",
            "properties": {
                "source_table": "link",
                "target_table": "mobileoperator",
                "source_set": "production",
            },
            "evidence": [{"file_path": "src/LinkDao.java", "line_start": 10, "extractor": "join"}],
        },
    }
    sections = []
    for filename, row in rows.items():
        (detail / filename).write_text(json.dumps(row) + "\n", encoding="utf-8")
        section = filename.removesuffix(".jsonl")
        sections.append({
            "section": section,
            "relative_path": f"subject-knowledge-payload/compact/reference_data_fact_base/{filename}",
            "records_count": 1,
            "format": "jsonl",
        })
    path = _envelope(
        evidence,
        kind="reference-data-evidence",
        version="reference-data-evidence/v1",
        payload={"sections": sections},
    )
    result = materialize(
        _request("reference-data", path, "reference-data-evidence", "reference-data-evidence/v1"),
        tmp_path / "reference-context-query",
    )
    service = ReferenceDataQueryService(Path(result["output"]["manifest_path"]).parent)

    # Raw-row token filtering used to miss this candidate because the canonical table
    # identity is only available after literal-write aggregation.
    search = service.search_reference_data(token="MOBILEOPERATOR", max_results=20)
    assert search.page.total_count == 2
    production_view = service.search_reference_data(token="MOBILEOPERATOR", include_non_production=False, max_results=20)
    assert production_view.page.total_count == 2
    # Caller pagination is applied after token matching; a tiny result limit must not
    # make the candidate disappear because unrelated catalog rows sort first.
    tiny_page = service.search_reference_data(token="MOBILEOPERATOR", include_non_production=True, max_results=1)
    assert tiny_page.page.total_count == 2
    assert tiny_page.page.returned_count == 1
    assert tiny_page.items[0]["name"] in {"99.18.MOBILEOPERATOR_dml_literal_rows", "placeholder.mobileoperator"}
    assert {item["representation_kind"] for item in search.items} == {
        "declared_value_set", "literal_populated_storage_target"
    }

    context = service.get_candidate_context(token="MOBILEOPERATOR", max_results=50)
    assert context.page.total_count == 1
    payload = context.items[0]
    assert context.summary["local_definition_evidence_count"] == 2
    assert context.summary["definition_modes_observed"] == ["source_seed_sql"]
    assert context.summary["own_nsi_status_established"] is False
    assert len(payload["literal_writes"]) == 1
    assert any(item["observation_kind"] == "physical_assets" for item in payload["usage_observations"])
    assert any(item["observation_kind"] == "join_observations" for item in payload["usage_observations"])
    assert payload["interpretation_policy"]["absence_of_upstream_evidence_is_not_global_proof"] is True


def test_reference_data_candidate_context_classifies_csv_as_source_file_definition(tmp_path: Path) -> None:
    from prepared_knowledge_runtime.reference_data_queries import ReferenceDataQueryService

    evidence = tmp_path / "input-reference-csv"
    detail = evidence / "evidence" / "subject-knowledge-payload" / "compact" / "reference_data_fact_base"
    detail.mkdir(parents=True)
    row = {
        "fact_id": "set-country-csv",
        "fact_type": "declared_value_set",
        "name": "data/countries.csv",
        "properties": {
            "declared_value_set_id": "country-csv-values",
            "syntax_kind": "csv_table",
            "entries_count": 2,
            "sample_entries": [{"code": "RU", "name": "Russia"}, {"code": "DE", "name": "Germany"}],
            "source_set": "production",
        },
        "evidence": [{"file_path": "data/countries.csv", "line_start": 1, "extractor": "declared_value_scanner"}],
    }
    filename = "declared_value_sets.jsonl"
    (detail / filename).write_text(json.dumps(row) + "\n", encoding="utf-8")
    path = _envelope(
        evidence,
        kind="reference-data-evidence",
        version="reference-data-evidence/v1",
        payload={"sections": [{
            "section": "declared_value_sets",
            "relative_path": f"subject-knowledge-payload/compact/reference_data_fact_base/{filename}",
            "records_count": 1,
            "format": "jsonl",
        }]},
    )
    result = materialize(
        _request("reference-data", path, "reference-data-evidence", "reference-data-evidence/v1"),
        tmp_path / "reference-csv-query",
    )
    service = ReferenceDataQueryService(Path(result["output"]["manifest_path"]).parent)

    search = service.search_reference_data(token="countries", max_results=20)
    assert search.page.total_count == 1
    assert search.items[0]["definition_mode_observed"] == "source_file"
    assert search.items[0]["repository_embedded_definition_evidence_present"] is True
    assert search.items[0]["own_nsi_status"] == "not_assigned"

    context = service.get_candidate_context(token="countries", max_results=20)
    assert context.summary["definition_modes_observed"] == ["source_file"]
    assert context.summary["own_nsi_status_established"] is False
