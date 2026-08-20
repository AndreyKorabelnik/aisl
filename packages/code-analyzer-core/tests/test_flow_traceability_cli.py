from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts
from code_analyzer_core.utils import write_json
from evidence_access_test_utils import assert_evidence_tool_registered
from code_evidence.commands import export_manifest, field_flow, flow, show


def _write_analysis_out(tmp_path: Path, facts, repo: Path) -> Path:
    out = tmp_path / "analysis-out"
    for rel in ["core", "compact", "facts/facts_by_type", "diagnostics"]:
        (out / rel).mkdir(parents=True, exist_ok=True)
    result = AnalysisResult(
        system_name="system-a",
        project_code="P",
        repo_path=str(repo),
        stack=["java"],
        files_analyzed=1,
    )
    result.facts.extend(facts)
    write_json(out / "core" / "repository.json", {
        "system_name": "system-a",
        "project_code": "P",
        "repo_path": str(repo),
        "stack": ["java"],
        "files_analyzed": 1,
    })
    write_json(out / "manifest.json", {"repo_path": str(repo)})
    write_json(out / "diagnostics" / "scanner_status_summary.json", {})
    write_normalized_fact_store(result, out / "facts")
    build_navigation(result, out)
    return out


def test_field_flow_for_whole_object_serialization_via_local_variable(tmp_path: Path):
    dto = tmp_path / "EntityEvent.java"
    dto.write_text(
        """
        class EntityEvent {
            private String deviceId;
            private String requestId;
            private String stateCode;
        }
        """,
        encoding="utf-8",
    )
    publisher = tmp_path / "Publisher.java"
    publisher.write_text(
        """
        public class Publisher {
            public void publish(EntityEvent event) {
                String payload = dtoToString(event);
                kafkaTemplate.send(topic, payload);
            }
        }
        """,
        encoding="utf-8",
    )

    facts, status = build_java_data_flow_facts([dto, publisher])

    assert status["flows_extracted"] == 1
    assert status["field_flows_extracted"] == 2
    field_facts = [f for f in facts if f.fact_type == "field_identifier_flow"]
    assert {f.properties["source_field"] for f in field_facts} == {"deviceId", "requestId"}
    assert {f.properties["trace_status"] for f in field_facts} == {"unresolved"}
    assert {f.properties["operation"] for f in field_facts} == {"Publisher.publish"}


def test_show_resolves_flow_and_field_flow_ids(tmp_path: Path):
    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        class EntityEvent {
            private String deviceId;
        }
        public class Publisher {
            public void publish(EntityEvent event) {
                kafkaTemplate.send(topic, dtoToString(event));
            }
        }
        """,
        encoding="utf-8",
    )
    facts, _ = build_java_data_flow_facts([src])
    out = _write_analysis_out(tmp_path, facts, tmp_path)

    manifest = export_manifest(analysis_out=out)
    assert "flow_000001" in manifest["evidence_ids"]
    assert "field_flow_000001" in manifest["evidence_ids"]

    flow_payload = flow(out, "flow_000001")
    field_payload = field_flow(out, "field_flow_000001")
    show_flow = show(out, "flow_000001")
    show_field = show(out, "field_flow_000001")

    assert flow_payload["hit_count"] >= 1
    assert field_payload["hit_count"] >= 1
    assert show_flow["kind"] == "flow"
    assert show_field["kind"] == "field-flow"


def test_evidence_tool_catalog_allows_show_flow_and_field_flow():
    for command_id in ["show", "flow", "field_flow"]:
        assert_evidence_tool_registered(command_id)
