from __future__ import annotations

from pathlib import Path
import json

from code_analyzer_core.prepared_artifacts.value_flow_evidence import build_value_flow_evidence


def test_value_flow_evidence_publishes_atomic_records_without_task_semantics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main/java/demo/Mapper.java"
    source.parent.mkdir(parents=True)
    source.write_text("""
        package demo;
        class Mapper {
            String map(Request request) {
                String value = request.getValue();
                return value == null ? "unknown" : value.trim();
            }
        }
        class Request { String getValue(){ return "x"; } }
    """, encoding="utf-8")
    out = tmp_path / "out"
    artifact = build_value_flow_evidence(
        repository=repo, files=[source], repo_id="demo", output_root=out, parameters={}
    )
    assert artifact["artifact_kind"] == "value-flow-evidence"
    assert artifact["schema_version"] == "value-flow-evidence/v1"
    assert artifact["coverage"]["field_occurrence_count"] > 0
    assert artifact["coverage"]["field_flow_edge_count"] > 0
    serialized = json.dumps(artifact, sort_keys=True)
    assert "task_suite_profile_semantics" not in serialized
    assert "legacy_fallback" not in serialized
    names = {item["artifact_name"] for item in artifact["payload"]["artifacts"]}
    assert names == {
        "catalog/field_occurrences.json",
        "catalog/field_flow_edges.json",
        "system_interface_catalog.json",
    }
