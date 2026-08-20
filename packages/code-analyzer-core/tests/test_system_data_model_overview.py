from pathlib import Path
import json

from code_evidence.commands import system_data_model_overview, system_table_catalog, event_source_catalog, system_scenario_catalog
from evidence_access_test_utils import assert_evidence_tool_registered


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_system_data_model_overview_materializes_tables_events_and_flows(tmp_path: Path):
    out = tmp_path / "analysis-output"
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo", "project_code": "DEMO", "system_name": "demo-system"})
    _write(out / "facts" / "fact_summary.json", {"facts_by_type": {"attribute_occurrence": 4}})
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "DemoController.create", "path": "POST /objects", "schema_ref": "CreateRequest"}
        ],
        "operations": [
            {"id": "operation_000001", "operation": "DemoController.create", "interfaces": ["interface_000001"]}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "sql_create.json", [
        {
            "fact_type": "sql_create",
            "properties": {"kind": "create", "tables": ["demo_object"], "columns": ["object_id", "state_code"], "statement_preview": "create table demo_object (object_id varchar(64) primary key, state_code varchar(32) not null)"},
            "evidence": [{"file_path": str(tmp_path / "src/main/resources/db/changelog.sql"), "line_start": 1, "extractor": "sqlglot"}]
        }
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_occurrence.json", [
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000001", "container_name": "CreateRequest", "container_kind": "request", "attribute_name": "objectId", "attribute_type": "String"}, "evidence": []},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000002", "container_name": "CreateRequest", "container_kind": "request", "attribute_name": "stateCode", "attribute_type": "String"}, "evidence": []},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000003", "container_name": "DemoEntity", "container_kind": "entity", "attribute_name": "objectId", "attribute_type": "String"}, "evidence": []},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000004", "container_name": "DemoEntity", "container_kind": "entity", "attribute_name": "stateCode", "attribute_type": "String"}, "evidence": []},
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_mapping.json", [
        {"properties": {"attribute_mapping_id": "attribute_mapping_000001", "source_container": "CreateRequest", "source_field": "objectId", "target_container": "DemoEntity", "target_field": "objectId", "mapping_kind": "direct"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "operation": "DemoService.create", "source_payload": "CreateRequest", "saved_object": "DemoEntity", "storage_target": "demo_object", "lineage_status": "confirmed"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "data_model_lineage_gap.json", [
        {"properties": {"data_model_lineage_gap_id": "data_model_lineage_gap_000001", "gap_kind": "field_mapping_unresolved", "container": "DemoEntity", "field": "stateCode", "reason": "stateCode mapping not resolved"}, "evidence": []}
    ])

    catalog = system_table_catalog(out, max_results=100)
    assert catalog["kind"] == "system-table-catalog"
    assert catalog["items"][0]["table_name"] == "demo_object"
    assert [c["name"] for c in catalog["items"][0]["columns"]] == ["object_id", "state_code"]
    assert catalog["items"][0]["ddl_scope"] == "production_resource"

    event_catalog = event_source_catalog(out, max_results=100)
    assert event_catalog["kind"] == "event-source-catalog"
    assert event_catalog["items"][0]["interface_id"] == "interface_000001"
    assert event_catalog["items"][0]["operation_id"] == "operation_000001"
    assert event_catalog["items"][0]["endpoint_path"] == "POST /objects"

    scenario_catalog = system_scenario_catalog(out, max_results=100)
    assert scenario_catalog["kind"] == "system-scenario-catalog"
    assert scenario_catalog["included_count"] >= 1

    overview = system_data_model_overview(out, max_results=100)
    assert overview["kind"] == "system-data-model-overview"
    assert overview["system_overview"]["repo_id"] == "demo"
    assert overview["sections"]["event_sources"]["included_count"] == 1
    assert overview["sections"]["physical_tables"]["items"][0]["table_name"] == "demo_object"
    assert overview["sections"]["java_data_objects"]["included_count"] == 2
    assert overview["sections"]["data_flows"]["included_count"] >= 1
    assert overview["sections"]["gaps"]["items"][0]["gap_type"] == "field_mapping_unresolved"


def test_system_data_model_tools_are_registered():
    for command_id in [
        "system_data_model_overview",
        "system_table_catalog",
        "event_source_catalog",
        "system_scenario_catalog",
    ]:
        assert_evidence_tool_registered(command_id)
