from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts
from code_analyzer_core.scanners.java_trace_builder import build_java_traceability_facts
from code_analyzer_core.utils import write_json
from code_evidence.commands import show, field_lineage, export_manifest
from evidence_access_test_utils import assert_evidence_tool_registered


def _analyze(files: list[Path]):
    flow_facts, _ = build_java_data_flow_facts(files)
    trace_facts, status = build_java_traceability_facts(files, flow_facts)
    return flow_facts + trace_facts, status


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
    write_json(out / "core" / "repository.json", {"repo_path": str(repo), "stack": ["java"], "files_analyzed": 1})
    write_json(out / "manifest.json", {"repo_path": str(repo)})
    write_json(out / "diagnostics" / "scanner_status_summary.json", {})
    write_normalized_fact_store(result, out / "facts")
    build_navigation(result, out)
    return out


def _props(facts, fact_type):
    return [f.properties for f in facts if f.fact_type == fact_type]


def test_ingress_field_used_for_lookup_is_not_returned_without_target_field(tmp_path: Path):
    src = tmp_path / "Controller.java"
    src.write_text(
        """
        @RestController
        class ClientProfileController {
          private final ProfileService service;
          @PostMapping("/profilesByCard")
          public ProfilesByCardResponse profileByCard(@RequestBody ProfilesByCardRequest request) {
            ProfilesByCardResponse response = service.findByCard(request);
            return response;
          }
        }
        class ProfilesByCardRequest { private java.util.List<String> cardNumbers; }
        class ProfilesByCardResponse { private java.util.List<ProfileByCard> profiles; }
        class ProfileByCard { private String stateCode; }
        interface ProfileService { ProfilesByCardResponse findByCard(ProfilesByCardRequest request); }
        class ProfileServiceImpl implements ProfileService { public ProfilesByCardResponse findByCard(ProfilesByCardRequest request) { return null; } }
        """,
        encoding="utf-8",
    )
    facts, status = _analyze([src])
    lineages = _props(facts, "field_lineage")
    roles = {(x["source_field"], x["field_role"], x.get("target_boundary")) for x in lineages}

    assert status["field_lineages_extracted"] >= 2
    assert ("cardNumbers", "input_attribute_received", None) in roles
    assert ("cardNumbers", "input_attribute_used_for_lookup", "service_or_lookup") in roles
    assert not any(x["source_field"] == "cardNumbers" and x["field_role"] == "returned_in_response" for x in lineages)


def test_explicit_rest_response_field_lineage(tmp_path: Path):
    src = tmp_path / "Controller.java"
    src.write_text(
        """
        @RestController
        class EchoController {
          @PostMapping("/echo")
          public EchoResponse echo(@RequestBody EchoRequest request) {
            EchoResponse response = new EchoResponse();
            response.setStateCode(request.getStateCode());
            return response;
          }
        }
        class EchoRequest { private String stateCode; public String getStateCode() { return stateCode; } }
        class EchoResponse { private String stateCode; public void setStateCode(String stateCode) {} }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    lineages = _props(facts, "field_lineage")

    returned = [x for x in lineages if x["field_role"] == "returned_in_response"]
    assert returned
    assert returned[0]["source_field"] == "stateCode"
    assert returned[0]["target_boundary"] == "rest_response"
    assert returned[0]["target_field"] == "stateCode"
    assert returned[0]["evidence_maturity_dimensions"]["field_mapping"] == "confirmed"
    assert returned[0]["evidence_maturity_dimensions"]["end_to_end_trace"] == "confirmed"


def test_ingress_field_to_kafka_key_and_storage_field(tmp_path: Path):
    src = tmp_path / "App.java"
    src.write_text(
        """
        @RestController
        class Controller {
          private final Service service;
          @PostMapping("/sync")
          public void sync(@RequestBody SyncRequest request) { service.publishAndStore(request); }
        }
        class Service {
          private final Repo repository;
          public void publishAndStore(SyncRequest request) {
            StoredEntity entity = new StoredEntity();
            entity.setStateCode(request.getStateCode());
            repository.save(entity);
            kafkaTemplate.send(topic, request.getObjectId(), request);
          }
        }
        class SyncRequest {
          private String objectId;
          private String stateCode;
          public String getObjectId() { return objectId; }
          public String getStateCode() { return stateCode; }
        }
        class StoredEntity { private String stateCode; public void setStateCode(String stateCode) {} }
        interface Repo { void save(StoredEntity entity); }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    lineages = _props(facts, "field_lineage")

    assert any(x["source_field"] == "objectId" and x["target_boundary"] == "kafka" and x["target_field"] == "message_key" for x in lineages)
    assert any(x["source_field"] == "stateCode" and x["target_boundary"] == "storage" and x["target_field"] == "stateCode" for x in lineages)


def test_field_lineage_cli_and_manifest(tmp_path: Path):
    src = tmp_path / "Controller.java"
    src.write_text(
        """
        @RestController
        class EchoController {
          @PostMapping("/echo")
          public EchoResponse echo(@RequestBody EchoRequest request) {
            EchoResponse response = new EchoResponse();
            response.setStateCode(request.getStateCode());
            return response;
          }
        }
        class EchoRequest { private String stateCode; public String getStateCode() { return stateCode; } }
        class EchoResponse { private String stateCode; public void setStateCode(String stateCode) {} }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    out = _write_analysis_out(tmp_path, facts, tmp_path)

    listed = field_lineage(out, "stateCode")
    assert listed["hit_count"] >= 1
    first_id = listed["hits"][0]["item"].get("field_lineage_id") or listed["hits"][0]["item"].get("properties", {}).get("field_lineage_id")
    assert first_id.startswith("field_lineage_")
    shown = show(out, first_id)
    assert shown["kind"] == "field-lineage"
    manifest = export_manifest(analysis_out=out)
    assert first_id in manifest["evidence_ids"]

    assert_evidence_tool_registered("field_lineage")


def test_field_lineage_strict_contract_no_blocked_keys(tmp_path: Path):
    src = tmp_path / "Controller.java"
    src.write_text(
        """
        @RestController
        class EchoController {
          @PostMapping("/echo")
          public EchoResponse echo(@RequestBody EchoRequest request) {
            EchoResponse response = new EchoResponse();
            response.setStateCode(request.getStateCode());
            return response;
          }
        }
        class EchoRequest { private String stateCode; public String getStateCode() { return stateCode; } }
        class EchoResponse { private String stateCode; public void setStateCode(String stateCode) {} }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    for props in _props(facts, "field_lineage"):
        assert "assess" + "ment" not in props
        assert "con" + "fidence" not in props
        assert "evidence_maturity_dimensions" in props
