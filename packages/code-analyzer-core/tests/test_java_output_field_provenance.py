from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts
from code_analyzer_core.scanners.java_trace_builder import build_java_traceability_facts
from code_analyzer_core.utils import write_json
from code_evidence.commands import output_field_provenance, show, export_manifest
from evidence_access_test_utils import assert_evidence_tool_registered


def _analyze(files: list[Path]):
    flow_facts, _ = build_java_data_flow_facts(files)
    trace_facts, status = build_java_traceability_facts(files, flow_facts)
    return flow_facts + trace_facts, status


def _props(facts, fact_type):
    return [f.properties for f in facts if f.fact_type == fact_type]


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


def test_rest_response_service_result_fields_are_not_assumed_ingress(tmp_path: Path):
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
        class ProfilesByCardResponse { private String cardState; private String blockDesc; }
        interface ProfileService { ProfilesByCardResponse findByCard(ProfilesByCardRequest request); }
        """,
        encoding="utf-8",
    )
    facts, status = _analyze([src])
    prov = _props(facts, "output_field_provenance")

    assert status["output_field_provenance_extracted"] >= 2
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}
    assert by_field["cardState"]["immediate_origin_kind"] == "service_result_field"
    assert by_field["cardState"]["ultimate_origin_kind"] == "unknown"
    assert by_field["cardState"]["trace_status"] == "unresolved"
    assert "assess" + "ment" not in by_field["cardState"]
    assert "con" + "fidence" not in by_field["cardState"]
    assert by_field["cardState"]["evidence_maturity_dimensions"]["output_provenance"] == "unresolved"
    assert by_field["blockDesc"]["origin_kind"] == "unknown"
    assert not any(x["published_field"] == "cardState" and x["origin_kind"] == "ingress_field" for x in prov)


def test_output_field_provenance_strict_contract_no_blocked_keys(tmp_path: Path):
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
    facts, status = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    assert prov
    for props in prov:
        assert "assess" + "ment" not in props
        assert "con" + "fidence" not in props
        assert props["trace_status"] in {"confirmed", "unresolved"}
        assert set(props["evidence_maturity_dimensions"].values()) <= {"confirmed", "unresolved", "not_applicable"}
    assert "output_field_provenance_" + "assess" + "ment_counts" not in status
    assert "output_field_provenance_trace_status_counts" in status


def test_rest_response_field_from_db_and_constant_provenance(tmp_path: Path):
    src = tmp_path / "Controller.java"
    src.write_text(
        """
        @RestController
        class StateController {
          private final StateRepository repository;
          @PostMapping("/state")
          public StateResponse getState(@RequestBody StateRequest request) {
            StateEntity entity = repository.findById(request.getObjectId());
            StateResponse response = new StateResponse();
            response.setStateCode(entity.getStateCode());
            response.setDefaultFlag("Y");
            return response;
          }
        }
        class StateRequest { private String objectId; public String getObjectId() { return objectId; } }
        class StateEntity { private String stateCode; public String getStateCode() { return stateCode; } }
        class StateResponse { private String stateCode; private String defaultFlag; public void setStateCode(String stateCode) {} public void setDefaultFlag(String defaultFlag) {} }
        interface StateRepository { StateEntity findById(String objectId); }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}

    assert by_field["stateCode"]["ultimate_origin_kind"] == "db_read_field"
    assert by_field["stateCode"]["origin_field"] == "stateCode"
    assert by_field["defaultFlag"]["origin_kind"] == "constant"


def test_output_field_provenance_cli_navigation_manifest(tmp_path: Path):
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

    listed = output_field_provenance(out, "stateCode")
    assert listed["hit_count"] >= 1
    first_id = listed["hits"][0]["item"].get("output_field_provenance_id") or listed["hits"][0]["item"].get("properties", {}).get("output_field_provenance_id")
    assert first_id.startswith("output_field_provenance_")
    shown = show(out, first_id)
    assert shown["kind"] == "output-field-provenance"
    manifest = export_manifest(analysis_out=out)
    assert first_id in manifest["evidence_ids"]

    assert_evidence_tool_registered("output_field_provenance")


def test_deep_rest_response_service_result_resolves_external_field(tmp_path: Path):
    src = tmp_path / "DeepController.java"
    src.write_text(
        """
        @RestController
        class MbController {
          private final ProfileHandler handler;
          @PostMapping("/mb")
          public MbResponse mbInfo(@RequestBody MbRequest request) {
            MbResponse response = handler.process(request);
            return response;
          }
        }
        @Service
        class ProfileHandler {
          private final RemoteGateway gateway;
          public MbResponse process(MbRequest request) {
            RemoteProfile remote = gateway.load(request.getPhoneNumbers());
            MbProfile profile = new MbProfile();
            profile.setPaymentBlock(remote.getPaymentBlock());
            MbResponse response = new MbResponse();
            response.setPaymentBlock(profile.getPaymentBlock());
            return response;
          }
        }
        class MbRequest { private java.util.List<String> phoneNumbers; public java.util.List<String> getPhoneNumbers() { return phoneNumbers; } }
        class RemoteProfile { private String paymentBlock; public String getPaymentBlock() { return paymentBlock; } }
        class MbProfile { private String paymentBlock; public String getPaymentBlock() { return paymentBlock; } public void setPaymentBlock(String paymentBlock) {} }
        class MbResponse { private String paymentBlock; public void setPaymentBlock(String paymentBlock) {} }
        interface RemoteGateway { RemoteProfile load(java.util.List<String> phoneNumbers); }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}

    assert by_field["paymentBlock"]["immediate_origin_kind"] == "service_result_field"
    assert by_field["paymentBlock"]["ultimate_origin_kind"] == "external_service_response_field"
    assert by_field["paymentBlock"]["origin_field"] == "paymentBlock"
    assert "phoneNumbers" in by_field["paymentBlock"].get("lookup_fields", [])
    assert by_field["paymentBlock"].get("provenance_depth", 0) >= 1


def test_deep_mapper_result_resolves_repository_read_through_mapper(tmp_path: Path):
    src = tmp_path / "DeepMapperController.java"
    src.write_text(
        """
        @RestController
        class StateController {
          private final StateService service;
          @PostMapping("/state")
          public StateResponse getState(@RequestBody StateRequest request) {
            StateResponse response = service.getState(request);
            return response;
          }
        }
        @Service
        class StateService {
          private final StateRepository repository;
          private final StateMapper mapper;
          public StateResponse getState(StateRequest request) {
            StateEntity entity = repository.findById(request.getObjectId());
            return mapper.toResponse(entity);
          }
        }
        @Component
        class StateMapper {
          public StateResponse toResponse(StateEntity entity) {
            StateResponse response = new StateResponse();
            response.setStateCode(entity.getStateCode());
            return response;
          }
        }
        class StateRequest { private String objectId; public String getObjectId() { return objectId; } }
        class StateEntity { private String stateCode; public String getStateCode() { return stateCode; } }
        class StateResponse { private String stateCode; public void setStateCode(String stateCode) {} }
        interface StateRepository { StateEntity findById(String objectId); }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}

    assert by_field["stateCode"]["immediate_origin_kind"] == "service_result_field"
    assert by_field["stateCode"]["ultimate_origin_kind"] in {"db_read_field", "repository_result_field"}
    assert by_field["stateCode"].get("origin_field") == "stateCode"
    assert "objectId" in by_field["stateCode"].get("lookup_fields", [])


def test_nested_collection_response_field_provenance_resolves_external_element_field(tmp_path: Path):
    src = tmp_path / "NestedController.java"
    src.write_text(
        """
        @RestController
        class MbClientProfileController {
          private final ProfileHandler handler;
          @PostMapping("/mb")
          public MbClientProfileResponse mbInfoByPhoneAndCard(@RequestBody MbClientProfileRequest request) {
            MbClientProfileResponse response = handler.process(request);
            return response;
          }
        }
        @Service
        class ProfileHandler {
          private final ProfileGateway profileGateway;
          public MbClientProfileResponse process(MbClientProfileRequest request) {
            ExternalProfileResponse extResponse = profileGateway.loadProfiles(request.getPhoneNumbers(), request.getCardNumbers());
            MbClientProfileResponse response = new MbClientProfileResponse();
            response.setMbClientProfiles(extResponse.getProfiles());
            return response;
          }
        }
        class MbClientProfileRequest {
          private java.util.List<String> phoneNumbers;
          private java.util.List<String> cardNumbers;
          public java.util.List<String> getPhoneNumbers() { return phoneNumbers; }
          public java.util.List<String> getCardNumbers() { return cardNumbers; }
        }
        class MbClientProfileResponse {
          private java.util.List<MbClientProfile> mbClientProfiles;
          public void setMbClientProfiles(java.util.List<MbClientProfile> mbClientProfiles) {}
        }
        class ExternalProfileResponse {
          private java.util.List<MbClientProfile> profiles;
          public java.util.List<MbClientProfile> getProfiles() { return profiles; }
        }
        class MbClientProfile {
          private String paymentBlock;
          private String operator;
          public String getPaymentBlock() { return paymentBlock; }
          public String getOperator() { return operator; }
        }
        interface ProfileGateway { ExternalProfileResponse loadProfiles(java.util.List<String> phoneNumbers, java.util.List<String> cardNumbers); }
        """,
        encoding="utf-8",
    )
    facts, status = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}

    assert status["output_field_provenance_nested_fields"] >= 2
    assert "mbClientProfiles[*].paymentBlock" in by_field
    assert "mbClientProfiles[*].operator" in by_field
    payment = by_field["mbClientProfiles[*].paymentBlock"]
    assert payment["nested_field_provenance"] is True
    assert payment["container_field"] == "mbClientProfiles"
    assert payment["element_type"] == "MbClientProfile"
    assert payment["ultimate_origin_kind"] == "external_service_response_field"
    assert payment["origin_field"] in {"profiles[*].paymentBlock", "paymentBlock"}
    assert set(payment.get("lookup_fields") or []) >= {"phoneNumbers", "cardNumbers"}


def test_nested_collection_response_field_unknown_has_unresolved_boundary(tmp_path: Path):
    src = tmp_path / "NestedUnknownController.java"
    src.write_text(
        """
        @RestController
        class ProfileController {
          @PostMapping("/profiles")
          public ProfileResponse profiles(@RequestBody ProfileRequest request) {
            return new ProfileResponse();
          }
        }
        class ProfileRequest { private String objectId; }
        class ProfileResponse { private java.util.List<ProfileItem> items; }
        class ProfileItem { private String stateCode; private String stateName; }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    prov = _props(facts, "output_field_provenance")
    by_field = {x["published_field"]: x for x in prov if x["published_boundary"] == "rest_response"}

    assert by_field["items[*].stateCode"]["ultimate_origin_kind"] == "unknown"
    assert by_field["items[*].stateCode"]["unresolved_boundary"] == "nested_container"
    assert by_field["items[*].stateCode"]["missing_links"]


def test_call_chain_diagnostic_distinguishes_absent_caller(tmp_path: Path):
    from code_evidence.commands import call_chain_diagnostic

    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        @Component
        class PhoneBlockResyncHandler {
          private final KafkaTemplate kafkaTemplate;
          public void sendEvent(PhoneBlockEvent event) {
            kafkaTemplate.send("topic", event);
          }
        }
        class PhoneBlockEvent { private String objectId; }
        interface KafkaTemplate { void send(String topic, Object value); }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    diags = _props(facts, "call_chain_diagnostic")
    assert diags
    diag = next(x for x in diags if x["target_operation"] == "PhoneBlockResyncHandler.sendEvent")
    assert diag["caller_status"] == "not_found_in_repository"
    assert "outside analyzed scope" in " ".join(diag["missing_links"])

    out = _write_analysis_out(tmp_path, facts, tmp_path)
    listed = call_chain_diagnostic(out, "PhoneBlockResyncHandler.sendEvent")
    assert listed["hit_count"] >= 1
