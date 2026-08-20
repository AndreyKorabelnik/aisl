from __future__ import annotations

import json
from pathlib import Path

from code_evidence.commands import foreign_data_persistence_case_detail, foreign_data_persistence_cases


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _base(out: Path) -> None:
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo"})


def test_fdp_enriches_persistent_write_refs_and_saved_attributes_from_direct_write_ref(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "persistent_write_id": "persistent_write_000001",
                "operation": "DemoController.create",
                "source_kind": "rest_controller",
                "source_payload": "CreateRequest",
                "saved_object": "DemoRecord",
                "storage_target": "public.demo_table",
                "lineage_status": "confirmed",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "persistent_write.json", [
        {
            "properties": {
                "persistent_write_id": "persistent_write_000001",
                "storage_target": "public.demo_table",
                "saved_object": "DemoRecord",
                "written_fields": ["CLIENT_ID", "STATUS"],
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    case = view["cases"][0]

    assert case["local_persistence"]["persistent_write_refs"] == ["persistent_write_000001"]
    assert case["local_persistence"]["persistent_write_refs"]
    assert "persistent_write_match_status" not in case["local_persistence"]
    attrs = case["local_persistence"]["saved_attributes"]
    assert {a["storage_attribute"] for a in attrs} >= {"CLIENT_ID", "STATUS"}
    assert view["local_persistence_summary"]["with_direct_persistent_write_refs"] == 1
    assert view["local_persistence_summary"]["with_saved_attributes"] == 1


def test_fdp_enriches_overlap_persistent_write_refs_by_storage_match_and_filters_access(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.saveNoAccess",
                "source_payload": "NoAccessRequest",
                "saved_object": "NoAccessRecord",
                "storage_target": "public.no_access_table",
                "lineage_status": "unresolved",
            }
        },
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000002",
                "operation": "DemoController.saveWithAccess",
                "source_payload": "WithAccessRequest",
                "saved_object": "WithAccessRecord",
                "storage_target": "public.with_access_table",
                "lineage_status": "unresolved",
            }
        },
    ])
    _write(out / "facts" / "facts_by_type" / "persistent_write.json", [
        {
            "properties": {
                "persistent_write_id": "persistent_write_000002",
                "storage_target": "public.with_access_table",
                "saved_object": "WithAccessRecord",
                "target_columns": ["UCP_ID"],
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {
            "properties": {
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "source_storage_object": "public.with_access_table",
                "access_boundary": "DemoQueryController.get",
                "lineage_status": "candidate",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=1, external_access="observed_in_code")

    assert view["matched_count"] == 1
    assert view["included_count"] == 1
    case = view["cases"][0]
    assert case["external_access"]["status"] == "observed_in_code"
    assert case["local_persistence"]["persistent_write_refs"] == []
    assert case["local_persistence"]["overlap_persistent_write_refs"] == ["persistent_write_000002"]
    assert "persistent_write_match_status" not in case["local_persistence"]
    assert {a["storage_attribute"] for a in case["local_persistence"]["saved_attributes"]} == {"UCP_ID"}


def test_fdp_same_data_link_keeps_name_based_mapping_candidate_not_confirmed(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.create",
                "source_payload": "CreateRequest",
                "saved_object": "DemoRecord",
                "storage_target": "public.demo_table",
                "storage_fields": ["client_id"],
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {
            "properties": {
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "source_storage_object": "public.demo_table",
                "access_boundary": "DemoQueryController.get",
                "lineage_status": "candidate",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "stored_field_to_response_field_mapping.json", [
        {
            "properties": {
                "stored_field_to_response_field_mapping_id": "stored_field_to_response_field_mapping_000001",
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "storage_object": "public.demo_table",
                "storage_field": "client_id",
                "response_field": "clientId",
                "mapping_type": "inferred_from_names",
                "evidence_level": "candidate",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    case = view["cases"][0]

    assert case["same_data_link"]["status"] == "candidate_overlap"
    assert case["same_data_link"]["stored_to_response_mapping_refs"] == ["stored_field_to_response_field_mapping_000001"]
    assert case["same_data_link"]["overlapping_attributes"][0]["mapping_status"] == "inferred_from_names"
    assert view["same_data_field_summary"]["with_overlapping_attributes"] == 1


def test_fdp_case_detail_returns_single_enriched_case(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.create",
                "source_payload": "CreateRequest",
                "saved_object": "DemoRecord",
                "storage_target": "public.demo_table",
                "lineage_status": "unresolved",
            }
        }
    ])
    view = foreign_data_persistence_cases(out, max_results=10)
    case_id = view["cases"][0]["id"]

    detail = foreign_data_persistence_case_detail(out, case_id=case_id)

    assert detail["found"] is True
    assert detail["case"]["id"] == case_id
    assert "source_interpretation" in detail["case"]



def test_fdp_storage_only_match_with_two_writes_is_candidate_not_confirmed(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.create",
                "source_payload": "CreateRequest",
                "storage_target": "public.shared_table",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "persistent_write.json", [
        {"properties": {"persistent_write_id": "persistent_write_000001", "storage_target": "public.shared_table", "target_columns": ["A"]}},
        {"properties": {"persistent_write_id": "persistent_write_000002", "storage_target": "public.shared_table", "target_columns": ["B"]}},
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    lp = view["cases"][0]["local_persistence"]

    assert lp["persistent_write_refs"] == []
    assert set(lp["overlap_persistent_write_refs"]) == {"persistent_write_000001", "persistent_write_000002"}
    assert "persistent_write_match_status" not in lp


def test_fdp_schema_only_fallback_does_not_count_as_saved_attributes(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.schema_only_table"}}
    ])
    _write(out / "compact" / "db_schema_columns.json", [
        {"db_schema_column_id": "db_schema_column_000001", "table_name": "public.schema_only_table", "column_name": "CLIENT_ID"},
        {"db_schema_column_id": "db_schema_column_000002", "table_name": "public.schema_only_table", "column_name": "STATUS"},
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    lp = view["cases"][0]["local_persistence"]

    assert lp["saved_attributes"] == []
    assert {a["storage_attribute"] for a in lp["schema_only_attributes"]} == {"public.schema_only_table.CLIENT_ID", "public.schema_only_table.STATUS"}
    assert view["local_persistence_summary"]["with_saved_attributes"] == 0
    assert view["local_persistence_summary"]["with_schema_only_attributes"] == 1


def test_fdp_case_id_includes_source_to_storage_lineage_id_for_duplicate_shapes(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    duplicate_props = {
        "operation": "DemoController.create",
        "source_payload": "CreateRequest",
        "storage_target": "public.demo_table",
    }
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {**duplicate_props, "source_to_storage_lineage_id": "source_to_storage_lineage_000001"}},
        {"properties": {**duplicate_props, "source_to_storage_lineage_id": "source_to_storage_lineage_000002"}},
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    ids = [case["id"] for case in view["cases"]]

    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_fdp_filtered_view_writes_filter_specific_lazy_artifact(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.no_access"}},
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000002", "storage_target": "public.with_access"}},
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.with_access"}}
    ])

    foreign_data_persistence_cases(out, max_results=10)
    foreign_data_persistence_cases(out, max_results=10, external_access="observed_in_code")

    lazy_files = sorted((out / "lazy" / "foreign-data-persistence-cases").glob("*.json"))
    names = [p.name for p in lazy_files]
    assert len(lazy_files) == 2
    assert any(name.startswith("filter_external_access_observed_in_code") for name in names)


def test_fdp_access_linkage_uses_structured_storage_not_json_blob_substring(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {
            "properties": {
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "source_storage_object": "public.other_table",
                "debug_blob": "public.demo_table appears only in a diagnostic JSON blob and must not create linkage",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    assert view["cases"][0]["external_access"]["status"] == "not_observed"


def test_fdp_same_data_link_access_only_has_explicit_basis(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.demo_table"}}
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    sdl = view["cases"][0]["same_data_link"]

    assert sdl["status"] == "unresolved"
    assert sdl["overlap_basis"] == "access_lineage_only"
    assert sdl["field_evidence_status"] == "no_field_mapping"
    assert sdl["end_to_end_same_data"]["basis"] == "storage_access_only"


def test_fdp_unknown_payload_does_not_match_unknown_ingress_payload(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "OtherController.get", "schema_ref": "unknown", "path": "/other"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "source_payload": "unknown", "storage_target": "public.demo_table"}}
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["source_interpretation"]["status"] == "unknown_origin"
    assert case["source_interpretation"]["related_inbound_event_sources"] == []
    assert "placeholder_source_payload_discarded" in case["source_interpretation"]["discarded_signals"]


def test_fdp_unrelated_rest_endpoint_does_not_make_unknown_source_external_candidate(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "UnrelatedController.reload", "schema_ref": "ReloadRequest", "path": "/reload"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "source_payload": "unknown", "operation": "DemoService.save", "storage_target": "public.demo_table"}}
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["source_interpretation"]["status"] == "unknown_origin"
    assert case["source_interpretation"]["related_inbound_event_sources"] == []


def test_fdp_mockito_test_constructs_do_not_confirm_production_runtime_chain(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "persistent_write.json", [
        {"properties": {"persistent_write_id": "persistent_write_000001", "storage_target": "public.demo_table", "target_columns": ["CLIENT_ID"], "snippet": "verify(linkDao).save(record);"}, "evidence": [{"file_path": "src/test/java/DemoTest.java", "snippet": "verify(linkDao).save(record);"}]}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.demo_table", "snippet": "doAnswer(...).when(regHistoryEventDao)"}, "evidence": [{"file_path": "src/test/java/DemoTest.java", "snippet": "doAnswer(...).when(regHistoryEventDao)"}]}
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["local_persistence"]["persistent_write_refs"] == []
    assert case["local_persistence"]["overlap_persistent_write_refs"] == []
    assert case["external_access"]["status"] == "not_observed"
    assert case["risk_eligibility"]["risk_eligible"] is False


def test_fdp_storage_to_access_mapping_without_source_to_storage_mapping_not_e2e_confirmed(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "stored_field_to_response_field_mapping.json", [
        {"properties": {"stored_field_to_response_field_mapping_id": "stored_field_to_response_field_mapping_000001", "storage_to_access_lineage_id": "storage_to_access_lineage_000001", "storage_object": "public.demo_table", "storage_field": "client_id", "response_field": "clientId", "evidence_level": "confirmed"}}
    ])

    sdl = foreign_data_persistence_cases(out, max_results=10)["cases"][0]["same_data_link"]

    assert sdl["storage_to_access"]["status"] == "confirmed"
    assert sdl["source_to_storage"]["status"] == "unresolved"
    assert sdl["end_to_end_same_data"]["status"] == "candidate"
    assert sdl["end_to_end_same_data"]["basis"] == "storage_access_only"
    assert sdl["status"] == "candidate_overlap"


def test_fdp_target_only_saved_attribute_is_write_target_not_source_mapping(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table", "storage_fields": ["CLIENT_ID"]}}
    ])

    lp = foreign_data_persistence_cases(out, max_results=10)["cases"][0]["local_persistence"]

    assert len(lp["write_target_fields"]) == 1
    assert lp["write_target_fields"][0]["source_mapping_available"] is False
    assert lp["source_to_saved_field_mappings"] == []


def test_fdp_noisy_field_strings_are_rejected_and_not_used_for_confirmed_mapping(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "storage_target": "public.demo_table", "storage_fields": ["; /**", "CLIENT_ID"]}}
    ])

    lp = foreign_data_persistence_cases(out, max_results=10)["cases"][0]["local_persistence"]

    assert {a["storage_attribute"] for a in lp["write_target_fields"]} == {"CLIENT_ID"}
    assert lp["rejected_noisy_fields"]
    assert lp["field_quality_summary"]["rejected_noisy_field_count"] == 1


def test_fdp_complete_production_field_chain_gets_e2e_confirmed(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [{"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "DemoController.create", "schema_ref": "CreateRequest", "path": "/objects"}]
    })
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "operation": "DemoController.create", "source_kind": "rest_controller", "source_payload": "CreateRequest", "saved_object": "DemoEntity", "storage_target": "public.demo_table", "lineage_status": "confirmed"}}
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_mapping.json", [
        {"properties": {"attribute_mapping_id": "attribute_mapping_000001", "source_container": "CreateRequest", "source_field": "clientId", "target_container": "DemoEntity", "target_field": "CLIENT_ID", "mapping_kind": "direct", "evidence_level": "confirmed"}}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "stored_field_to_response_field_mapping.json", [
        {"properties": {"stored_field_to_response_field_mapping_id": "stored_field_to_response_field_mapping_000001", "storage_to_access_lineage_id": "storage_to_access_lineage_000001", "storage_object": "public.demo_table", "storage_field": "CLIENT_ID", "response_field": "clientId", "evidence_level": "confirmed"}}
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["source_interpretation"]["status"] == "confirmed_external_ingress"
    assert case["local_persistence"]["source_to_saved_field_mappings"]
    assert case["same_data_link"]["end_to_end_same_data"]["status"] == "confirmed"
    assert case["same_data_link"]["status"] == "confirmed_overlap"


def test_fdp_uses_factory_method_mapping_hint_as_candidate_source_segment(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoService.save",
                "source_payload": "CreateRequest",
                "saved_object": "DemoRecord",
                "storage_target": "public.demo_table",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "factory_method_mapping.json", [
        {
            "properties": {
                "factory_method_mapping_id": "factory_method_mapping_000001",
                "operation": "DemoMapper.createRecord",
                "target_container": "DemoRecord",
                "field_mappings": [
                    {
                        "target_container": "DemoRecord",
                        "target_field": "CLIENT_ID",
                        "source_object": "request",
                        "source_field": "clientId",
                        "mapping_kind": "factory_setter_mapping",
                        "mapping_status": "candidate",
                    }
                ],
                "mapping_status": "candidate",
                "evidence_policy": "factory mapping is local source-level evidence; persistence requires a separate storage/write link",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "public.demo_table"}}
    ])
    _write(out / "facts" / "facts_by_type" / "stored_field_to_response_field_mapping.json", [
        {
            "properties": {
                "stored_field_to_response_field_mapping_id": "stored_field_to_response_field_mapping_000001",
                "storage_to_access_lineage_id": "storage_to_access_lineage_000001",
                "storage_object": "public.demo_table",
                "storage_field": "CLIENT_ID",
                "response_field": "clientId",
                "evidence_level": "confirmed",
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert len(mappings) == 1
    assert mappings[0]["storage_attribute"] == "CLIENT_ID"
    assert mappings[0]["source_attribute"] == "clientId"
    assert mappings[0]["mapping_status"] == "candidate"
    assert mappings[0]["mapping_kind"] == "factory_setter_mapping"
    assert mappings[0]["evidence_refs"] == ["factory_method_mapping_000001"]
    assert case["same_data_link"]["source_to_storage"]["status"] == "candidate"
    assert case["same_data_link"]["end_to_end_same_data"]["status"] == "candidate"


def test_fdp_reads_inline_source_to_saved_field_mappings_from_source_to_storage_fact(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "DemoController.create",
                "source_payload": "CreateRequest",
                "saved_object": "DemoEntity",
                "storage_target": "public.demo_table",
                "source_to_saved_field_mappings": [
                    {
                        "storage_attribute": "STATUS",
                        "source_attribute": "status",
                        "source_object": "request",
                        "saved_object": "DemoEntity",
                        "mapping_status": "candidate",
                        "mapping_kind": "builder_field_assignment",
                        "evidence_refs": ["source_to_storage_lineage_000001"],
                    }
                ],
            }
        }
    ])

    lp = foreign_data_persistence_cases(out, max_results=10)["cases"][0]["local_persistence"]

    assert lp["write_target_fields"] == []
    assert len(lp["source_to_saved_field_mappings"]) == 1
    assert lp["source_to_saved_field_mappings"][0]["storage_attribute"] == "STATUS"
    assert lp["source_to_saved_field_mappings"][0]["source_attribute"] == "status"
    assert lp["source_to_saved_field_mappings"][0]["mapping_kind"] == "builder_field_assignment"


def test_fdp_uses_jooq_bind_order_write_slots_as_candidate_source_mappings(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "PhoneDao.updatePhones",
                "source_payload": "PhoneRequest",
                "saved_object": "PHONE",
                "storage_target": "PHONE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "jooq_batch_bind_mapping.json", [
        {
            "properties": {
                "jooq_batch_bind_mapping_id": "jooq_batch_bind_mapping_000001",
                "operation": "PhoneDao.updatePhones",
                "storage_table": "PHONE",
                "mapping_kind": "jooq_batch_bind_order",
                "write_target_fields": [
                    {"storage_field": "OPERATORID", "field_role": "write_target_field", "source_object": "p", "source_field": "operatorId", "source_expression": "p.getOperatorId()"},
                    {"storage_field": "PHONEBLOCKCODE", "field_role": "write_target_field", "source_object": "p", "source_field": "phoneBlockCode", "source_expression": "p.getPhoneBlockCode()"},
                ],
                "where_key_fields": [
                    {"storage_field": "PHONEID", "field_role": "where_key_field", "source_object": "p", "source_field": "phoneId", "source_expression": "p.getPhoneId()"}
                ],
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert {m["storage_attribute"] for m in mappings} == {"OPERATORID", "PHONEBLOCKCODE"}
    assert {m["source_attribute"] for m in mappings} == {"operatorId", "phoneBlockCode"}
    assert all(m["mapping_status"] == "candidate" for m in mappings)
    assert "PHONEID" not in {m["storage_attribute"] for m in mappings}
    assert case["same_data_link"]["source_to_storage"]["status"] == "candidate"


def test_fdp_uses_stream_collection_mapper_bridge_as_candidate_mapping(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "PhoneService.saveAll",
                "source_payload": "SpreadProfileRq",
                "saved_object": "UcpPhone_2Record",
                "storage_target": "UCP_PHONE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "stream_collection_lineage.json", [
        {
            "properties": {
                "stream_collection_lineage_id": "stream_collection_lineage_000001",
                "operation": "PhoneService.saveAll",
                "source_collection": "requests",
                "source_collection_type": "List",
                "source_element_type": "SpreadProfileRq",
                "method_references": [{"qualifier": "this", "method": "createUcpPhone", "text": "this::createUcpPhone"}],
                "lineage_status": "candidate_collection_provenance",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "factory_method_mapping.json", [
        {
            "properties": {
                "factory_method_mapping_id": "factory_method_mapping_000001",
                "operation": "PhoneService.createUcpPhone",
                "method_name": "createUcpPhone",
                "target_container": "UcpPhone_2Record",
                "field_mappings": [
                    {"target_container": "UcpPhone_2Record", "target_field": "UCPID", "source_object": "request", "source_field": "ucpId", "mapping_kind": "factory_setter_mapping"}
                ],
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert len(mappings) == 1
    assert mappings[0]["storage_attribute"] == "UCPID"
    assert mappings[0]["source_attribute"] == "ucpId"
    assert mappings[0]["source_object"] == "SpreadProfileRq"
    assert mappings[0]["mapping_kind"] == "stream_collection_factory_setter_mapping"
    assert set(mappings[0]["evidence_refs"]) == {"factory_method_mapping_000001", "stream_collection_lineage_000001"}
    assert mappings[0]["mapping_status"] == "candidate"


def test_fdp_uses_spring_dependency_hint_to_link_ingress_to_service_write(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "ProfileController.save", "schema_ref": "ProfileRequest", "path": "/profiles"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileServiceImpl.save",
                "source_kind": "method_input",
                "source_payload": "unknown",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "spring_component_dependency.json", [
        {
            "properties": {
                "spring_component_dependency_id": "spring_component_dependency_000001",
                "source_class": "ProfileController",
                "declared_type": "ProfileService",
                "candidate_implementations": ["ProfileServiceImpl"],
                "dependency_resolution_status": "candidate",
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    interp = case["source_interpretation"]

    assert interp["status"] == "external_ingress_candidate"
    assert "confidence" not in interp
    assert "candidate_call_path_via_spring_component_dependency" in interp["related_inbound_event_sources"][0]["match_reason"]
    assert interp["related_inbound_event_sources"][0]["hint_refs"] == ["spring_component_dependency_000001"]
    assert "source_payload_unknown" in interp["not_proven"]


def test_fdp_uses_template_dispatch_hint_to_link_template_ingress_to_override_write(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "system_ingress.json", [
        {
            "properties": {
                "ingress_id": "ingress_000001",
                "origin_kind": "rest_controller",
                "operation": "AbstractDalResultHandler.handle",
                "payload_type": "DalRequest",
                "class_name": "AbstractDalResultHandler",
                "method_name": "handle",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "QuickServiceUpdateHandler.handleByDal",
                "source_kind": "method_input",
                "source_payload": "unknown",
                "saved_object": "QuickServiceRecord",
                "storage_target": "QUICK_SERVICE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "template_method_dispatch.json", [
        {
            "properties": {
                "template_method_dispatch_id": "template_method_dispatch_000001",
                "subclass": "QuickServiceUpdateHandler",
                "superclass": "AbstractDalResultHandler",
                "override_operation": "QuickServiceUpdateHandler.handleByDal",
                "candidate_template_operations": ["AbstractDalResultHandler.handle"],
                "dispatch_status": "candidate_template_override",
            }
        }
    ])

    interp = foreign_data_persistence_cases(out, max_results=10)["cases"][0]["source_interpretation"]

    assert interp["status"] == "external_ingress_candidate"
    assert "candidate_call_path_via_template_method_dispatch" in interp["related_inbound_event_sources"][0]["match_reason"]
    assert interp["related_inbound_event_sources"][0]["hint_refs"] == ["template_method_dispatch_000001"]


def test_fdp_uses_jooq_parameterized_sql_write_slots_as_candidate_source_mappings(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "PhoneDao.updatePhone",
                "source_payload": "PhoneRequest",
                "saved_object": "PHONE",
                "storage_target": "PHONE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "jooq_parameterized_sql_mapping.json", [
        {
            "properties": {
                "jooq_parameterized_sql_mapping_id": "jooq_parameterized_sql_mapping_000001",
                "operation": "PhoneDao.updatePhone",
                "storage_table": "PHONE",
                "mapping_kind": "parameterized_sql_bind_order",
                "write_target_fields": [
                    {"storage_field": "OPERATORID", "field_role": "write_target_field", "source_object": "p", "source_field": "operatorId", "source_expression": "p.getOperatorId()"}
                ],
                "where_key_fields": [
                    {"storage_field": "PHONEID", "field_role": "where_key_field", "source_object": "p", "source_field": "phoneId", "source_expression": "p.getPhoneId()"}
                ],
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert len(mappings) == 1
    assert mappings[0]["storage_attribute"] == "OPERATORID"
    assert mappings[0]["source_attribute"] == "operatorId"
    assert mappings[0]["mapping_kind"] == "parameterized_sql_bind_order"
    assert "PHONEID" not in {m["storage_attribute"] for m in mappings}
    assert case["evidence_maturity"]["segments"]["source_to_storage_field_chain"]["status"] == "candidate"


def test_fdp_uses_method_call_argument_binding_to_link_ingress_to_service_write(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "ProfileController.save", "schema_ref": "ProfileRequest", "path": "/profiles"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "method_call.json", [
        {
            "properties": {
                "call_id": "call_000001",
                "caller_operation_id": "ProfileController.save",
                "callee_operation_id": "ProfileServiceImpl.save",
                "receiver_expression": "profileService",
                "resolution_kind": "spring_interface_dispatch",
                "argument_bindings": [
                    {
                        "caller_expression": "request",
                        "caller_source_parameter": "request",
                        "callee_parameter": "request",
                        "relation": "same_parameter",
                        "source_type": "ProfileRequest",
                        "target_type": "ProfileRequest",
                    }
                ],
                "source_scope": "production_code",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileServiceImpl.save",
                "source_kind": "method_input",
                "source_payload": "unknown",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    case = view["cases"][0]
    interp = case["source_interpretation"]

    assert interp["status"] == "external_ingress_candidate"
    ev = interp["related_inbound_event_sources"][0]
    assert "candidate_call_path_via_argument_binding" in ev["match_reason"]
    assert ev["hint_refs"] == ["call_000001"]
    assert ev["call_path"]["argument_propagation_status"] == "candidate_payload_argument_match"
    assert case["evidence_maturity"]["summary"]["has_call_argument_propagation"] is True
    assert view["fdp_evidence_maturity_summary"]["with_method_call_argument_propagation"] == 1


def test_fdp_uses_mapstruct_mapper_signature_as_object_bridge_not_field_mapping(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileService.save",
                "source_payload": "ProfileRequest",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "mapstruct_mapper_signature.json", [
        {
            "properties": {
                "mapstruct_mapper_signature_id": "mapstruct_mapper_signature_000001",
                "operation": "ProfileMapper.toRecord",
                "source_container": "ProfileRequest",
                "target_container": "ProfileRecord",
                "mapping_kind": "mapstruct_mapper_signature",
                "mapping_status": "candidate_object_bridge",
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["source_interpretation"]["related_object_mappings"][0]["mapping_type"] == "mapstruct_mapper_signature"
    assert case["local_persistence"]["source_to_saved_field_mappings"] == []
    assert case["evidence_maturity"]["segments"]["source_to_mapped_object"]["status"] == "candidate"
    assert "mapper_signature" in case["evidence_maturity"]["segments"]["source_to_mapped_object"]["hint_families"]


def test_fdp_uses_multi_hop_method_call_argument_path(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "ProfileController.save", "schema_ref": "ProfileRequest", "path": "/profiles"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "method_call.json", [
        {
            "properties": {
                "call_id": "call_000001",
                "caller_operation_id": "ProfileController.save",
                "callee_operation_id": "ProfileFacade.submit",
                "resolution_kind": "spring_interface_dispatch",
                "argument_bindings": [
                    {"caller_expression": "request", "caller_source_parameter": "request", "callee_parameter": "command", "relation": "same_object", "source_type": "ProfileRequest", "target_type": "ProfileRequest"}
                ],
                "source_scope": "production_code",
            }
        },
        {
            "properties": {
                "call_id": "call_000002",
                "caller_operation_id": "ProfileFacade.submit",
                "callee_operation_id": "ProfileHandler.handle",
                "resolution_kind": "spring_field_injection",
                "argument_bindings": [
                    {"caller_expression": "command", "caller_source_parameter": "command", "callee_parameter": "payload", "relation": "same_object", "source_type": "ProfileRequest", "target_type": "ProfileRequest"}
                ],
                "source_scope": "production_code",
            }
        },
        {
            "properties": {
                "call_id": "call_000003",
                "caller_operation_id": "ProfileHandler.handle",
                "callee_operation_id": "ProfileDao.save",
                "resolution_kind": "spring_field_injection",
                "argument_bindings": [
                    {"caller_expression": "payload", "caller_source_parameter": "payload", "callee_parameter": "record", "relation": "derived_object", "source_type": "ProfileRequest", "target_type": "ProfileRecord"}
                ],
                "source_scope": "production_code",
            }
        },
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileDao.save",
                "source_kind": "method_input",
                "source_payload": "unknown",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])

    view = foreign_data_persistence_cases(out, max_results=10)
    case = view["cases"][0]
    ev = case["source_interpretation"]["related_inbound_event_sources"][0]

    assert case["source_interpretation"]["status"] == "external_ingress_candidate"
    assert "candidate_multi_hop_call_path_via_argument_binding" in ev["match_reason"]
    assert ev["hint_refs"] == ["call_000001", "call_000002", "call_000003"]
    assert ev["call_path"]["path_kind"] == "multi_hop_method_call_argument_path"
    assert ev["call_path"]["hop_count"] == 3
    assert ev["call_path"]["argument_propagation_status"] == "candidate_payload_argument_match"
    assert case["evidence_maturity"]["summary"]["has_multi_hop_call_argument_propagation"] is True
    assert view["fdp_evidence_maturity_summary"]["with_multi_hop_method_call_argument_propagation"] == 1


def test_fdp_multi_hop_call_path_requires_payload_argument_continuity(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "ProfileController.save", "schema_ref": "ProfileRequest", "path": "/profiles"}
        ]
    })
    _write(out / "facts" / "facts_by_type" / "method_call.json", [
        {
            "properties": {
                "call_id": "call_000001",
                "caller_operation_id": "ProfileController.save",
                "callee_operation_id": "ProfileFacade.submit",
                "argument_bindings": [
                    {"caller_expression": "request", "caller_source_parameter": "request", "callee_parameter": "command", "relation": "same_object", "source_type": "ProfileRequest", "target_type": "ProfileRequest"}
                ],
                "source_scope": "production_code",
            }
        },
        {
            "properties": {
                "call_id": "call_000002",
                "caller_operation_id": "ProfileFacade.submit",
                "callee_operation_id": "ProfileDao.save",
                "argument_bindings": [
                    {"caller_expression": "other", "caller_source_parameter": "other", "callee_parameter": "record", "relation": "same_object", "source_type": "OtherRequest", "target_type": "ProfileRecord"}
                ],
                "source_scope": "production_code",
            }
        },
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileDao.save",
                "source_kind": "method_input",
                "source_payload": "unknown",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]

    assert case["source_interpretation"]["status"] == "unknown_origin"
    assert not any("candidate_multi_hop_call_path" in str(ev.get("match_reason")) for ev in case["source_interpretation"]["related_inbound_event_sources"])
    assert not any(isinstance(ev.get("call_path"), dict) for ev in case["source_interpretation"]["related_inbound_event_sources"])
    assert case["evidence_maturity"]["summary"]["has_multi_hop_call_argument_propagation"] is False


def test_payload_alias_assignment_map_preserves_same_object_relation() -> None:
    from types import SimpleNamespace

    from code_analyzer_core.scanners.java_flow_builder import _assignment_map_from_syntax
    from code_analyzer_core.scanners.java_trace_common import _source_parameter_from_expression

    assignments = [
        SimpleNamespace(assignment_kind="variable_declaration", target="payload", expression="request", start_byte=1, line_start=1),
        SimpleNamespace(assignment_kind="variable_declaration", target="command", expression="payload", start_byte=2, line_start=2),
        SimpleNamespace(assignment_kind="assignment_expression", target="forwarded", expression="command", start_byte=3, line_start=3),
    ]

    amap = _assignment_map_from_syntax(assignments, {"request"})
    source_param, relation, via_local = _source_parameter_from_expression("forwarded", {"request"}, amap)

    assert amap["command"]["source_parameter"] == "request"
    assert amap["command"]["alias_depth"] == 1
    assert amap["forwarded"]["alias_via"] == ["payload", "command"]
    assert source_param == "request"
    assert relation == "same_object"
    assert via_local == "forwarded"


def test_fdp_uses_mapstruct_annotation_field_mappings_as_candidate_source_mappings(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "ProfileService.save",
                "source_payload": "ProfileRequest",
                "saved_object": "ProfileRecord",
                "storage_target": "PROFILE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "mapstruct_mapper_signature.json", [
        {
            "properties": {
                "mapstruct_mapper_signature_id": "mapstruct_mapper_signature_000001",
                "operation": "ProfileMapper.toRecord",
                "source_container": "ProfileRequest",
                "target_container": "ProfileRecord",
                "mapping_kind": "mapstruct_mapper_signature",
                "mapping_status": "candidate_object_bridge_with_field_annotations",
                "field_mappings": [
                    {
                        "source_field": "clientId",
                        "source_path": "client.id",
                        "target_field": "clientId",
                        "target_path": "clientId",
                        "mapping_kind": "mapstruct_annotation_field_mapping",
                    }
                ],
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert len(mappings) == 1
    assert mappings[0]["source_attribute"] == "clientId"
    assert mappings[0]["storage_attribute"] == "clientId"
    assert mappings[0]["mapping_kind"] == "mapstruct_annotation_field_mapping"
    assert case["evidence_maturity"]["segments"]["source_to_storage_field_chain"]["status"] == "candidate"


def test_fdp_uses_named_parameter_sql_write_slots_as_candidate_source_mappings(tmp_path: Path) -> None:
    out = tmp_path / "analysis-output"
    _base(out)
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {
            "properties": {
                "source_to_storage_lineage_id": "source_to_storage_lineage_000001",
                "operation": "PhoneDao.updatePhone",
                "source_payload": "PhoneRequest",
                "saved_object": "PHONE",
                "storage_target": "PHONE",
                "lineage_status": "unresolved",
            }
        }
    ])
    _write(out / "facts" / "facts_by_type" / "jooq_parameterized_sql_mapping.json", [
        {
            "properties": {
                "jooq_parameterized_sql_mapping_id": "jooq_parameterized_sql_mapping_000001",
                "operation": "PhoneDao.updatePhone",
                "storage_table": "PHONE",
                "mapping_kind": "named_parameter_sql_mapping",
                "write_target_fields": [
                    {"storage_field": "OPERATORID", "field_role": "write_target_field", "bind_parameter": "operatorId", "source_object": "p", "source_field": "operatorId", "source_expression": "p.getOperatorId()"}
                ],
                "where_key_fields": [
                    {"storage_field": "PHONEID", "field_role": "where_key_field", "bind_parameter": "phoneId", "source_object": "p", "source_field": "phoneId", "source_expression": "p.getPhoneId()"}
                ],
            }
        }
    ])

    case = foreign_data_persistence_cases(out, max_results=10)["cases"][0]
    mappings = case["local_persistence"]["source_to_saved_field_mappings"]

    assert len(mappings) == 1
    assert mappings[0]["storage_attribute"] == "OPERATORID"
    assert mappings[0]["source_attribute"] == "operatorId"
    assert mappings[0]["mapping_kind"] == "named_parameter_sql_mapping"
    assert "PHONEID" not in {m["storage_attribute"] for m in mappings}
