from pathlib import Path

import yaml

from code_analyzer_core.spec_analysis import run_spec_analysis
from code_evidence.commands import (
    db_table_catalog,
    evidence_coverage,
    foreign_data_persistence_cases,
    system_data_model_overview,
    transformation_catalog,
)


def _write_spec_artifacts(root: Path) -> Path:
    artifacts = root / "reports" / "demo" / "artifacts"
    artifacts.mkdir(parents=True)
    payload = {
        "metadata": {
            "repo_id": "demo_repo",
            "substitution_grade": True,
            "generated_from_code_evidence": True,
            "authoritative_specification": False,
            "business_owner_confirmed": False,
            "business_decisions_made": False,
            "section_order": ["interfaces", "payload_schemas", "storages", "storage_attributes", "transformations", "gaps"],
            "export_completeness": {
                "interfaces": {"status": "complete", "exported": 1, "total": 1},
                "transformations": {"status": "complete", "exported": 1, "total": 1},
            },
        },
        "system": {"repo_id": "demo_repo", "system_name": "Demo Spec System"},
        "interfaces": [
            {
                "id": "IFACE-1",
                "direction": "inbound",
                "kind": "rest",
                "endpoint_or_resource": "/demo",
                "operation": "DemoController.create",
                "payload_schema_ref": "PAYLOAD-1",
                "evidence_status": "derived_by_static_analysis",
            }
        ],
        "payload_schemas": [
            {
                "id": "PAYLOAD-1",
                "java_class_name": "DemoRequest",
                "fields": [{"name": "clientId", "java_type": "String", "evidence_status": "derived_by_static_analysis"}],
            }
        ],
        "storages": [{"id": "STORE-1", "physical_name": "DEMO_TABLE", "schema_name": "PUBLIC", "storage_kind": "database"}],
        "storage_attributes": [
            {"id": "ATTR-1", "storage_ref": "STORE-1", "table_name": "DEMO_TABLE", "physical_name": "CLIENT_ID", "sql_type": "varchar"}
        ],
        "flows": [
            {"id": "FLOW-1", "flow_kind": "inbound_to_storage", "source": {"object": "DemoRequest", "operation": "DemoController.create"}, "target": {"object": "DEMO_TABLE"}, "status": "confirmed"}
        ],
        "transformations": [
            {"id": "TRN-1", "source_object": "DemoRequest", "source_attribute": "clientId", "target_object": "DEMO_TABLE", "target_attribute": "CLIENT_ID", "transformation_kind": "direct_mapping", "status": "derived_by_static_analysis"}
        ],
        "access_paths": [],
        "gaps": [{"id": "GAP-1", "gap_type": "owner_confirmation_missing", "reason": "Needs owner confirmation"}],
        "new_future_section": [{"id": "FUTURE-1", "name": "preserved"}],
    }
    (artifacts / "data-evidence.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (artifacts / "proposal.md").write_text("# Proposal", encoding="utf-8")
    return artifacts


def test_analyze_spec_builds_standard_analysis_output_and_ordinary_views(tmp_path: Path) -> None:
    artifacts = _write_spec_artifacts(tmp_path)
    result_root = tmp_path / "repository-result"
    static_out = result_root / "static-analysis-output"
    result = run_spec_analysis(spec_artifacts=artifacts, analysis_out=static_out, repo_id="demo_repo", system_name="Demo Spec System")
    analysis_out = Path(result["analysis_out"])

    manifest = __import__("json").loads((result_root / "repository-analysis-manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_scope"] == "repository"
    assert manifest["repo_id"] == "demo_repo"
    assert manifest["static_analysis_output"] == "static-analysis-output"
    assert "workspace_summary" not in result

    overview = system_data_model_overview(analysis_out)
    assert overview["system_overview"]["repo_id"] == "demo_repo"
    assert overview["coverage"]["event_source_count"] >= 1
    assert overview["coverage"]["mapping_count"] == 1

    tables = db_table_catalog(analysis_out)
    assert tables["matched_count"] == 1
    assert tables["items"][0]["table_name"] == "DEMO_TABLE"

    transformations = transformation_catalog(analysis_out)
    assert transformations["matched_count"] == 1
    assert transformations["items"][0]["source_attribute"] == "clientId"

    fdp = foreign_data_persistence_cases(analysis_out)
    assert fdp["risk_decision"] == "not_made_by_analyzer"

    coverage = evidence_coverage(analysis_out)["coverage"]
    assert coverage["source_type"] == "spec_artifacts"
    assert coverage["code_evidence_included"] is False
    assert coverage["source_inspection_available"] is False
    assert coverage["substitution_grade"] is True
