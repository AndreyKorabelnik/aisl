from pathlib import Path

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts
from code_analyzer_core.scanners.java_trace_builder import build_java_traceability_facts
from code_analyzer_core.utils import write_json
from evidence_access_test_utils import assert_evidence_tool_registered
from code_evidence.commands import export_manifest, show, trace, traces_for_operation, traces_for_payload


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


def _props(facts, fact_type):
    return [f.properties for f in facts if f.fact_type == fact_type]


def test_rest_ingress_to_service_to_outbound_kafka_confirmed(tmp_path: Path):
    src = tmp_path / "App.java"
    src.write_text(
        """
        @RestController
        public class Controller {
          private final Publisher publisher;
          @PostMapping("/events")
          public void receive(@RequestBody Event event) {
            publisher.publish(event);
          }
        }
        class Publisher {
          public void publish(Event event) {
            kafkaTemplate.send(topic, dtoToString(event));
          }
        }
        class Event {
          private String phoneNumber;
        }
        """,
        encoding="utf-8",
    )

    facts, status = _analyze([src])

    assert status["ingress_extracted"] == 1
    assert status["method_calls_extracted"] == 1
    traces = _props(facts, "data_trace")
    assert len(traces) == 1
    assert traces[0]["trace_type"] == "ingress_to_outbound"
    assert traces[0]["trace_status"] == "confirmed"
    assert traces[0]["ingress_id"] == "ingress_000001"
    assert "call_000001" in traces[0]["evidence_refs"]
    assert "flow_000001" in traces[0]["evidence_refs"]


def test_method_parameter_to_outbound_without_ingress_is_unknown_origin(tmp_path: Path):
    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        public class PhoneBlockResyncHandler {
          public void sendEvent(KafkaRequest<PhoneBlockResyncEvent> event) {
            kafkaTemplate.send(topic, dtoToString(event));
          }
        }
        """,
        encoding="utf-8",
    )

    facts, status = _analyze([src])

    assert status["ingress_extracted"] == 0
    traces = _props(facts, "data_trace")
    assert len(traces) == 1
    assert traces[0]["trace_status"] == "outbound_only_unknown_origin"
    assert traces[0]["earliest_observed_operation_id"] == "PhoneBlockResyncHandler.sendEvent"
    assert "no confirmed ingress/data-origin operation" in traces[0]["missing_links"]


def test_kafka_listener_to_service_to_http_client_strict_trace(tmp_path: Path):
    src = tmp_path / "Consumer.java"
    src.write_text(
        """
        public class Consumer {
          private final Sender sender;
          @KafkaListener(topics = "in-topic")
          public void onMessage(Event event) {
            sender.send(event);
          }
        }
        class Sender {
          public void send(Event event) {
            restTemplate.postForObject(url, event, Response.class);
          }
        }
        class Event {
          private String ucpId;
        }
        class Response {}
        """,
        encoding="utf-8",
    )

    facts, _ = _analyze([src])
    traces = _props(facts, "data_trace")

    assert len(traces) == 1
    assert traces[0]["trace_type"] == "ingress_to_outbound"
    assert traces[0]["origin_kind"] == "kafka_listener"
    assert traces[0]["sink_kind"] == "http_client"
    assert traces[0]["trace_status"] in {"confirmed", "unresolved"}


def test_ingress_to_repository_save_and_read_only_not_persistence_trace(tmp_path: Path):
    src = tmp_path / "App.java"
    src.write_text(
        """
        @RestController
        class Controller {
          private final Service service;
          @PostMapping("/save")
          public void receive(@RequestBody Event event) {
            service.store(event);
          }
        }
        class Service {
          private final EventRepository eventRepository;
          public Event load(String id) {
            return eventRepository.findById(id);
          }
          public void store(Event event) {
            eventRepository.save(event);
          }
        }
        class Event {
          private String requestId;
        }
        """,
        encoding="utf-8",
    )

    facts, status = _analyze([src])
    storage = _props(facts, "storage_access")
    traces = _props(facts, "data_trace")

    assert status["storage_access_counts"] == {"read": 1, "write": 1}
    assert {x["access_kind"] for x in storage} == {"read", "write"}
    assert len(traces) == 1
    assert traces[0]["trace_type"] == "ingress_to_persistence"
    assert traces[0]["trace_status"] == "confirmed"
    assert traces[0]["db_write_kind"] == "save"
    assert traces[0]["storage_access_id"]


def test_argument_binding_derived_object_marks_unresolved_trace_under_strict_contract(tmp_path: Path):
    src = tmp_path / "App.java"
    src.write_text(
        """
        @RestController
        class Controller {
          private final Publisher publisher;
          @PostMapping("/events")
          public void receive(@RequestBody Event event) {
            OutEvent out = mapper.map(event);
            publisher.publish(out);
          }
        }
        class Publisher {
          public void publish(OutEvent out) {
            kafkaTemplate.send(topic, dtoToString(out));
          }
        }
        class Event { private String requestId; }
        class OutEvent { private String requestId; }
        """,
        encoding="utf-8",
    )

    facts, _ = _analyze([src])
    calls = _props(facts, "method_call")
    traces = _props(facts, "data_trace")

    assert calls[0]["argument_bindings"][0]["relation"] == "derived_object"
    assert traces[0]["trace_status"] == "unresolved"
    assert traces[0]["same_data_chain_status"] == "unresolved"


def test_trace_cli_manifest_and_contract_support_new_evidence(tmp_path: Path):
    src = tmp_path / "Publisher.java"
    src.write_text(
        """
        public class PhoneBlockResyncHandler {
          public void sendEvent(KafkaRequest<PhoneBlockResyncEvent> event) {
            kafkaTemplate.send(topic, dtoToString(event));
          }
        }
        """,
        encoding="utf-8",
    )
    facts, _ = _analyze([src])
    out = _write_analysis_out(tmp_path, facts, tmp_path)

    manifest = export_manifest(analysis_out=out)
    assert "trace_000001" in manifest["evidence_ids"]
    assert show(out, "trace_000001")["kind"] == "trace"
    assert trace(out, "", trace_type="ingress_to_outbound")["hit_count"] == 1
    assert traces_for_operation(out, "PhoneBlockResyncHandler.sendEvent")["hit_count"] == 1
    assert traces_for_payload(out, "KafkaRequest")["hit_count"] == 1

    for command_id in ["show", "trace", "ingress", "call", "storage_access", "traces_for_operation", "traces_for_payload"]:
        assert_evidence_tool_registered(command_id)


def test_source_only_spring_interface_dispatch_wrapper_to_kafka_unresolved_under_strict_contract(tmp_path: Path):
    src = tmp_path / "SpringGraph.java"
    src.write_text(
        """
        @RestController
        class Controller {
          private final ProfileService profileService;
          @PostMapping("/events")
          public void receive(@RequestBody Event event) {
            profileService.process(event);
          }
        }
        interface ProfileService {}
        @Service
        class ProfileServiceImpl implements ProfileService {
          private final PhoneBlockResyncHandler handler;
          public void process(Event event) {
            handler.sendEvent(new KafkaRequest<Event>(event));
          }
        }
        class PhoneBlockResyncHandler {
          public void sendEvent(KafkaRequest<Event> event) {
            kafkaTemplate.send(topic, dtoToString(event));
          }
        }
        class Event { private String phoneNumber; }
        """,
        encoding="utf-8",
    )

    facts, status = _analyze([src])
    calls = _props(facts, "method_call")
    traces = _props(facts, "data_trace")

    assert status["mode"] == "source_only_spring_traceability_graph"
    assert any(c["resolution_kind"] == "spring_interface_dispatch" for c in calls)
    assert any(c["argument_relation"] == "derived_object" for c in calls)
    assert len(traces) == 1
    assert traces[0]["trace_status"] == "unresolved"
    assert traces[0]["same_data_chain_status"] == "unresolved"
    assert traces[0]["origin_kind"] == "rest_controller"
    assert traces[0]["related_flow_id"] == "flow_000001"
    assert {s["kind"] for s in traces[0]["steps"]} >= {"ingress", "method_call", "outbound_sink"}


def test_self_call_and_setter_field_derivation_to_outbound_unresolved_under_strict_contract(tmp_path: Path):
    src = tmp_path / "SelfAndSetter.java"
    src.write_text(
        """
        @RestController
        class Controller {
          private final Publisher publisher;
          @PostMapping("/events")
          public void receive(@RequestBody Event event) {
            process(event);
          }
          private void process(Event event) {
            OutEvent out = new OutEvent();
            out.setPhoneNumber(event.getPhoneNumber());
            publisher.publish(out);
          }
        }
        class Publisher {
          public void publish(OutEvent out) {
            kafkaTemplate.send(topic, dtoToString(out));
          }
        }
        class Event { private String phoneNumber; }
        class OutEvent { private String phoneNumber; }
        """,
        encoding="utf-8",
    )

    facts, _ = _analyze([src])
    calls = _props(facts, "method_call")
    traces = _props(facts, "data_trace")

    assert any(c["resolution_kind"] == "this_call" for c in calls)
    assert any(c["argument_relation"] == "field_extracted" for c in calls)
    assert len(traces) == 1
    assert traces[0]["trace_status"] == "unresolved"
    assert "field_extracted" in traces[0]["argument_relation_chain"]


def test_method_call_contract_preserves_overloaded_caller_bodies_and_signatures(tmp_path: Path):
    src = tmp_path / "OverloadedMapper.java"
    src.write_text(
        """
        class CreateRequest {}
        class UpdateRequest {}
        class CreateName {}
        class UpdateName {}
        class Target {}

        class Service {
          private final Mapper mapper;

          public Target create(CreateRequest request) {
            return mapper.map(request);
          }

          public Target update(UpdateRequest request) {
            return mapper.map(request);
          }
        }

        class Mapper {
          public Target map(CreateRequest request) {
            complete(new CreateName());
            return new Target();
          }

          public Target map(UpdateRequest request) {
            complete(new UpdateName());
            return new Target();
          }

          private void complete(CreateName name) {}
          private void complete(UpdateName name) {}
        }
        """,
        encoding="utf-8",
    )

    facts, _ = _analyze([src])
    calls = _props(facts, "method_call")

    service_calls = [
        call for call in calls
        if call.get("caller_operation_id") in {"Service.create", "Service.update"}
        and call.get("callee_operation_id") == "Mapper.map"
    ]
    assert {
        call.get("callee_operation_signature") for call in service_calls
    } == {
        "Mapper#map(CreateRequest)",
        "Mapper#map(UpdateRequest)",
    }
    assert all(call.get("overload_resolution") == "exact_argument_types" for call in service_calls)

    mapper_calls = [
        call for call in calls
        if call.get("caller_operation_id") == "Mapper.map"
        and call.get("callee_operation_id") == "Mapper.complete"
    ]
    # Both overloaded caller bodies must survive the method index.  The nested
    # object creation does not provide a compiler-grade argument type, so each
    # call keeps both same-arity candidates and exposes their signatures rather
    # than silently overwriting one overload.
    assert {
        call.get("caller_operation_signature") for call in mapper_calls
    } == {
        "Mapper#map(CreateRequest)",
        "Mapper#map(UpdateRequest)",
    }
    assert {
        call.get("callee_operation_signature") for call in mapper_calls
    } == {
        "Mapper#complete(CreateName)",
        "Mapper#complete(UpdateName)",
    }
    assert all(call.get("overload_resolution") == "ambiguous_same_arity" for call in mapper_calls)
