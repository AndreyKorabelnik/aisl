from __future__ import annotations

import json
from pathlib import Path

from code_evidence.commands import foreign_data_persistence_cases


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_fdp_cases_include_external_ingress_source_interpretation(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo"})
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {
                "id": "interface_000001",
                "kind": "rest",
                "direction": "inbound",
                "operation": "DemoController.create",
                "path": "POST /objects",
                "schema_ref": "CreateRequest",
            }
        ],
        "operations": [
            {"id": "operation_000001", "operation": "DemoController.create", "interfaces": ["interface_000001"]}
        ],
    })
    _write(out / "facts" / "facts_by_type" / "attribute_mapping.json", [
        {
            "properties": {
                "attribute_mapping_id": "attribute_mapping_000001",
                "source_container": "CreateRequest",
                "source_field": "clientId",
                "target_container": "DemoEntity",
                "target_field": "clientId",
                "mapping_kind": "direct",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.create",
                "source_kind": "rest_controller",
                "source_payload": "CreateRequest",
                "saved_object": "DemoEntity",
                "storage_target": "demo.demo_entity",
                "lineage_status": "confirmed",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {
            "properties": {
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "source_storage_object": "demo.demo_entity",
                "access_boundary": "DemoQueryController.get",
                "lineage_status": "candidate",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=100)

    assert view["risk_decision"] == "not_made_by_analyzer"
    assert view["by_source_interpretation_status"]["confirmed_external_ingress"] == 1
    assert view["fdp_source_origin_summary"]["with_external_access_by_source_interpretation_status"]["confirmed_external_ingress"] == 1
    case = view["cases"][0]
    interpretation = case["source_interpretation"]
    assert interpretation["status"] == "confirmed_external_ingress"
    assert interpretation["business_source_decision"] == "not_made_by_analyzer"
    assert interpretation["related_inbound_event_sources"][0]["interface_id"] == "interface_000001"
    assert interpretation["related_object_mappings"][0]["mapping_id"] == "attribute_mapping_000001"
    assert "exact upstream business system is not identified by static analysis" in interpretation["not_proven"]


def test_fdp_cases_distinguish_runtime_input_from_unknown_origin(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo"})
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoService.create",
                "source_payload": "CreateRequest",
                "saved_object": "DemoEntity",
                "storage_target": "demo.demo_entity",
                "lineage_status": "unresolved",
            }
        },
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000002",
                "operation": "DemoService.refresh",
                "saved_object": "RefreshEntity",
                "storage_target": "demo.refresh_entity",
                "lineage_status": "unresolved",
            }
        },
    ])

    view = foreign_data_persistence_cases(out, max_results=100)
    statuses = {case["local_persistence"]["storage_refs"][0]: case["source_interpretation"]["status"] for case in view["cases"]}

    assert statuses["demo.demo_entity"] == "runtime_input_candidate"
    assert statuses["demo.refresh_entity"] == "unknown_origin"
    assert view["fdp_source_origin_summary"]["by_source_interpretation_status"]["runtime_input_candidate"] == 1
    assert view["fdp_source_origin_summary"]["by_source_interpretation_status"]["unknown_origin"] == 1
