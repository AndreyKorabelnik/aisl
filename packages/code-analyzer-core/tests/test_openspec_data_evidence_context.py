from pathlib import Path
import json

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids
from code_evidence.commands import openspec_data_evidence_context, openspec_data_evidence_full
from code_evidence.catalog import filter_evidence_tool_catalog, load_evidence_tool_catalog
from evidence_access_test_utils import assert_evidence_tool_registered


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture(out: Path):
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {
        "repo_id": "demo",
        "project_code": "DEMO",
        "system_name": "demo-system",
        "analysis_profile": {"profile_id": "code-to-openspec-data-evidence"},
        "evidence_provider": {"capabilities": ["openspec-data-evidence-context"]},
    })
    _write(out / "facts" / "fact_summary.json", {"facts_by_type": {"attribute_occurrence": 4}})
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "DemoController.create", "path": "POST /objects", "schema_ref": "CreateRequest"}
        ],
        "operations": [{"id": "operation_000001", "operation": "DemoController.create", "interfaces": ["interface_000001"]}],
    })
    _write(out / "facts" / "facts_by_type" / "sql_create.json", [
        {"fact_type": "sql_create", "properties": {"kind": "create", "tables": ["demo_object"], "columns": ["object_id", "state_code"], "statement_preview": "create table demo_object (object_id varchar(64), state_code varchar(32))"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_occurrence.json", [
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000001", "container_name": "CreateRequest", "container_kind": "request", "attribute_name": "objectId", "attribute_type": "String"}, "evidence": []},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000002", "container_name": "CreateRequest", "container_kind": "request", "attribute_name": "stateCode", "attribute_type": "String"}, "evidence": []},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000003", "container_name": "DemoEntity", "container_kind": "entity", "attribute_name": "objectId", "attribute_type": "String"}, "evidence": []},
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_mapping.json", [
        {"properties": {"attribute_mapping_id": "attribute_mapping_000001", "source_container": "CreateRequest", "source_field": "objectId", "target_container": "DemoEntity", "target_field": "objectId", "mapping_kind": "direct"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "operation": "DemoService.create", "source_payload": "CreateRequest", "saved_object": "DemoEntity", "storage_target": "demo_object", "lineage_status": "confirmed"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_to_access_lineage.json", [
        {"properties": {"storage_to_access_lineage_id": "storage_to_access_lineage_000001", "source_storage_object": "demo_object", "response_or_payload_type": "DemoResponse", "access_boundary": "DemoController.get", "lineage_status": "confirmed"}, "evidence": []}
    ])
    _write(out / "facts" / "facts_by_type" / "data_model_lineage_gap.json", [
        {"properties": {"data_model_lineage_gap_id": "data_model_lineage_gap_000001", "gap_kind": "field_mapping_unresolved", "container": "DemoEntity", "field": "stateCode", "reason": "stateCode mapping not resolved"}, "evidence": []}
    ])
    _write(out / "evidence_coverage.json", {"artifact": "evidence_coverage", "limitations": [{"component": "spoon_scan", "status": "removed_from_fast_core", "gap_type": "analysis_method_removed_from_fast_core", "impact": "deep Java AST evidence is not collected"}]})


def test_code_to_openspec_data_evidence_profile_loads():
    profile = load_analysis_profile(Path("analysis-profiles/code-to-openspec-data-evidence.yaml"))
    assert profile["profile_id"] == "code-to-openspec-data-evidence"
    stages = profile_stage_ids(profile)
    for stage in ["scan_files", "config_scan", "java_structural_scan", "sql_scan", "db_schema_scan", "java_data_model_lineage_build", "java_persistence_lineage_build", "declared_value_scan", "compact_package"]:
        assert stage in stages


def test_openspec_data_evidence_context_smoke(tmp_path: Path):
    out = tmp_path / "analysis-output"
    _fixture(out)
    ctx = openspec_data_evidence_context(out, section="summary", max_items=20)
    assert ctx["kind"] == "openspec-data-evidence-context"
    assert ctx["generation_policy"]["business_decisions_made"] is False
    assert ctx["sections"]["summary"]["counts"]["interfaces"] == 1

    flows = openspec_data_evidence_context(out, section="flows", max_items=20)
    assert flows["sections"]["flows"]["included_count"] >= 1
    assert flows["policy"]["analyzer_role"] == "deterministic_evidence_only_no_openspec_generation"

    full = openspec_data_evidence_context(out, max_items=20)
    assert "authority_signals" in full["sections"]
    assert "source_of_truth_candidates" not in full["sections"]
    assert "lifecycle_evidence_signals" in full["sections"]
    assert full["sections"]["external_data_persistence_cases"]["items"][0]["risk_decision"] == "not_made_by_analyzer"
    assert any(g["gap_type"] == "analysis_method_removed_from_fast_core" for g in full["sections"]["gaps"]["items"])
    assert any(o["omission_type"] == "system_graph_not_included" for o in full["omissions"])


def test_openspec_data_evidence_context_tool_catalog():
    assert_evidence_tool_registered("openspec_data_evidence_context")
    catalog = load_evidence_tool_catalog()
    assert any(c["command_id"] == "openspec_data_evidence_context" and c.get("agent_visible") for c in catalog["commands"])
    assert any(c["command_id"] == "openspec_data_evidence_full" and c.get("agent_visible") for c in catalog["commands"])
    subset = filter_evidence_tool_catalog(
        catalog,
        workspace_type="java",
        analysis_profile="code-to-openspec-data-evidence",
        capabilities={"openspec-data-evidence-context", "openspec-data-evidence-full"},
        agent_visible_only=True,
    )
    assert any(c["view_name"] == "openspec-data-evidence-context" for c in subset["commands"])
    assert any(c["view_name"] == "openspec-data-evidence-full" for c in subset["commands"])
    assert_evidence_tool_registered("openspec_data_evidence_full")


def test_openspec_data_evidence_full_is_substitution_grade_full_export(tmp_path: Path):
    out = tmp_path / "analysis-output"
    _fixture(out)
    full = openspec_data_evidence_full(out)
    assert full["kind"] == "openspec-data-evidence-full"
    assert full["metadata"]["substitution_grade"] is True
    assert full["metadata"]["authoritative_specification"] is False
    assert full["metadata"]["business_decisions_made"] is False
    assert isinstance(full["interfaces"], list) and len(full["interfaces"]) == 1
    assert isinstance(full["payload_schemas"], list) and full["payload_schemas"]
    assert isinstance(full["transformations"], list) and full["transformations"]
    assert isinstance(full["gaps"], list) and full["gaps"]
    assert full["metadata"]["export_completeness"]["interfaces"]["status"] == "complete"
    assert full["metadata"]["export_completeness"]["transformations"]["exported"] == len(full["transformations"])
    assert full["policy"]["no_sampling_rule"].startswith("Factual sections")


def test_openspec_data_evidence_full_preserves_future_sections(monkeypatch, tmp_path: Path):
    out = tmp_path / "analysis-output"
    out.mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo", "analysis_profile": {"profile_id": "code-to-openspec-data-evidence"}})

    def fake_context(analysis_out: Path, section=None, token="", max_items=100):
        return {
            "kind": "openspec-data-evidence-context",
            "analysis_profile": "code-to-openspec-data-evidence",
            "repo_id": "demo",
            "sections": {
                "system": {"repo_id": "demo"},
                "interfaces": {"section_name": "interfaces", "matched_count": 1, "items": [{"id": "IFACE-1"}]},
                "future_section": {"section_name": "future_section", "matched_count": 1, "items": [{"id": "FUTURE-1"}]},
            },
            "evidence_ref_index": [],
            "omissions": [],
        }

    monkeypatch.setattr("code_evidence.commands.openspec_data_evidence_context", fake_context)
    full = openspec_data_evidence_full(out)
    assert "future_section" in full
    assert full["future_section"] == [{"id": "FUTURE-1"}]
    assert "future_section" in full["metadata"]["export_completeness"]
    assert "future_section" in full["metadata"]["section_order"]
    assert "schema_evolution_policy" in full["metadata"]
