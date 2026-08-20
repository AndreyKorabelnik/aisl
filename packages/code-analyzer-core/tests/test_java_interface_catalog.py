from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.models import AnalysisResult, Direction, InterfaceKind
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.scanners.java_scanner import scan_java_files


def test_rest_boundary_joins_class_and_method_mapping_and_extracts_params(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "TpsController.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        import org.springframework.web.bind.annotation.*;
        @RestController
        @RequestMapping("/tps")
        class TpsController {
          @PostMapping("/update")
          public UpdateResponse update(
              @RequestHeader(name = "X-Request-Id", required = false) String requestId,
              @RequestBody UpdateRequest request) {
            return new UpdateResponse();
          }
          @GetMapping("/tables/{tableId}")
          public TableData getTable(@PathVariable String tableId, @RequestParam(name = "version", required = false) String version) {
            return new TableData();
          }
        }
        class UpdateRequest { String clientId; }
        class UpdateResponse { String status; }
        class TableData { String value; }
        ''',
        encoding="utf-8",
    )

    _facts, schemas, interfaces, relations, _mapper_facts, warnings = scan_java_files([src])

    assert warnings == []
    by_path = {(i.direction.value, i.path, i.schema_ref): i for i in interfaces}
    assert ("inbound", "/tps/update", "UpdateRequest") in by_path
    assert ("outbound", "/tps/update", "UpdateResponse") in by_path
    assert ("inbound", "/tps/tables/{tableId}", "method_parameters") in by_path
    table_req = by_path[("inbound", "/tps/tables/{tableId}", "method_parameters")]
    assert table_req.method == "GET"
    assert table_req.properties["request_parameters"] == [
        {"name": "tableId", "java_parameter": "tableId", "java_type": "String", "source": "PathVariable", "required": None, "default_value": None},
        {"name": "version", "java_parameter": "version", "java_type": "String", "source": "RequestParam", "required": False, "default_value": None},
    ]
    assert table_req.properties["source_set"] == "main"
    assert not table_req.properties["is_test_source"]
    assert any(r.properties["path"] == "/tps/update" for r in relations)


def test_system_interface_catalog_is_production_first_and_contains_attributes(tmp_path: Path) -> None:
    main_src = tmp_path / "src" / "main" / "java" / "demo" / "ProfileController.java"
    test_src = tmp_path / "src" / "test" / "java" / "demo" / "ProfileControllerTest.java"
    main_src.parent.mkdir(parents=True)
    test_src.parent.mkdir(parents=True)
    main_src.write_text(
        '''
        import org.springframework.web.bind.annotation.*;
        @RestController
        @RequestMapping("/profiles")
        class ProfileController {
          @PostMapping("/{id}")
          public ProfileResponse save(@PathVariable String id, @RequestBody ProfileRequest request) { return new ProfileResponse(); }
        }
        class ProfileRequest { String clientId; String phone; }
        class ProfileResponse { String status; }
        ''',
        encoding="utf-8",
    )
    test_src.write_text(
        '''
        import org.springframework.web.bind.annotation.*;
        @RestController
        class ProfileControllerTest {
          @PostMapping("/test-only")
          public TestResponse test(@RequestBody TestRequest request) { return new TestResponse(); }
        }
        class TestRequest { String id; }
        class TestResponse { String status; }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files([main_src, test_src])
    assert warnings == []
    result = AnalysisResult(system_name="demo", project_code="demo", repo_path=str(tmp_path), files_analyzed=2)
    result.facts = facts
    result.schemas = schemas
    result.interfaces = interfaces
    result.relations = relations
    result.mapper_facts = mapper_facts

    build_navigation(result, tmp_path / "out", max_items=100)
    catalog = json.loads((tmp_path / "out" / "compact" / "system_interface_catalog.json").read_text(encoding="utf-8"))

    assert catalog["summary"]["production_total"] == 2
    assert catalog["summary"]["test_total"] == 2
    assert all(not x["is_test_source"] for x in catalog["production_interfaces"])
    req = next(x for x in catalog["production_interfaces"] if x["boundary_kind"] == "rest_request")
    assert req["endpoint_or_topic_resolved"] == "/profiles/{id}"
    assert {a["attribute_name"] for a in req["attributes"]} == {"id", "clientId", "phone"}


def test_kafka_outbound_send_patterns_extract_payload_and_key(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "KafkaPublisher.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        class KafkaTemplate<K,V> { void send(Object... args) {} }
        class ProducerRecord<K,V> { ProducerRecord(String t, V v) {} ProducerRecord(String t, K k, V v) {} ProducerRecord(String t, Integer p, K k, V v) {} }
        class KafkaPublisher {
          private KafkaTemplate<String, Event> kafkaTemplate;
          private KafkaTemplate<String, Event> kafkaOperations;
          void publish(String topic, String key, Event event) {
            kafkaTemplate.send(topic, key, event);
            kafkaTemplate.send(topic, 0, key, event);
            kafkaOperations.send(new ProducerRecord<>(topic, key, event), (metadata, exception) -> {});
            ProducerRecord<String, Event> record = new ProducerRecord<>(topic, key, event);
            kafkaTemplate.send(record);
            kafkaTemplate.executeInTransaction(tpl -> tpl.send(topic, key, event));
          }
        }
        class Event { String clientId; }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files([src])
    assert warnings == []
    sends = [i for i in interfaces if i.kind == InterfaceKind.KAFKA and i.direction == Direction.OUTBOUND]
    assert len(sends) == 5
    assert {s.properties["send_pattern"] for s in sends} == {
        "send_topic_key_payload",
        "send_topic_partition_key_payload",
        "producer_record_inline",
        "producer_record_assigned_variable",
    }
    assert all(s.properties["payload_expression"] == "event" for s in sends)
    assert all(s.properties["message_key_expression"] == "key" for s in sends)
    assert all(s.schema_ref == "Event" for s in sends)


def test_openapi_scan_extracts_contract_interfaces_and_described_attributes(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.openapi_scanner import scan_openapi_files

    spec = tmp_path / "src" / "main" / "resources" / "api" / "demo.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        '''
        openapi: 3.0.0
        info: { title: Demo API, version: '1.0' }
        paths:
          /tps/update:
            post:
              operationId: updateTps
              parameters:
                - name: X-Request-Id
                  in: header
                  required: false
                  schema: { type: string }
                  description: Request id
              requestBody:
                content:
                  application/json:
                    schema: { $ref: '#/components/schemas/UpdateTpsRequest' }
              responses:
                '200':
                  content:
                    application/json:
                      schema: { $ref: '#/components/schemas/UpdateTpsResponse' }
        components:
          schemas:
            UpdateTpsRequest:
              required: [ucpId]
              properties:
                ucpId:
                  type: string
                  description: Идентификатор ЕПК
                phoneNumber:
                  type: string
                  description: Номер телефона
            UpdateTpsResponse:
              properties:
                status: { type: string, description: Статус }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, warnings = scan_openapi_files([spec])

    assert warnings == []
    assert len(facts) == 1
    assert {s.name for s in schemas} == {"UpdateTpsRequest", "UpdateTpsResponse"}
    req_schema = next(s for s in schemas if s.name == "UpdateTpsRequest")
    assert req_schema.fields[0].description == "Идентификатор ЕПК"
    assert "required" in req_schema.fields[0].annotations
    assert {(i.direction.value, i.path, i.schema_ref) for i in interfaces} == {
        ("inbound", "/tps/update", "UpdateTpsRequest"),
        ("outbound", "/tps/update", "UpdateTpsResponse"),
    }
    req = next(i for i in interfaces if i.direction == Direction.INBOUND)
    assert req.properties["request_parameters"][0]["source"] == "RequestHeader"
    assert req.properties["openapi_operation_id"] == "updateTps"


def test_kafka_topic_property_binding_from_consumer_props_and_settings(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "KafkaConsumerDemo.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        import org.springframework.kafka.annotation.KafkaListener;
        enum Settings { KAFKA_TOPIC_PROFILE("kafka.topic.profile.name"); Settings(String key) {} }
        enum ConsumerProps { PROFILE("id", Settings.KAFKA_TOPIC_PROFILE, Settings.KAFKA_TOPIC_PROFILE, Settings.KAFKA_TOPIC_PROFILE); ConsumerProps(String id, Settings topic, Settings concurrency, Settings toggle) {} }
        class ApplicationSettings { String getStringValue(Settings s) { return ""; } }
        class BaseConsumer { BaseConsumer(ConsumerProps props, ApplicationSettings settings) {} }
        class ProfileEvent { String clientId; }
        class ProfileConsumer extends BaseConsumer {
          ProfileConsumer(ApplicationSettings settings) { super(ConsumerProps.PROFILE, settings); }
          @KafkaListener(topics = "#{__listener.props.getTopic(settings)}", id = "#{__listener.props.getId()}")
          public void onReceive(ProfileEvent event) {}
        }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files([src])
    assert warnings == []
    consume = next(i for i in interfaces if i.kind == InterfaceKind.KAFKA and i.direction == Direction.INBOUND)
    assert consume.name == "#{__listener.props.getTopic(settings)}"
    assert consume.properties["consumer_props_symbol"] == "PROFILE"
    assert consume.properties["topic_settings_symbol"] == "KAFKA_TOPIC_PROFILE"
    assert consume.properties["topic_property_key"] == "kafka.topic.profile.name"

    result = AnalysisResult(system_name="demo", project_code="demo", repo_path=str(tmp_path), files_analyzed=1)
    result.facts = facts
    result.schemas = schemas
    result.interfaces = interfaces
    result.relations = relations
    result.mapper_facts = mapper_facts
    result.config_facts = [
        __import__("code_analyzer_core.models", fromlist=["Fact"]).Fact(
            fact_type="config_property",
            name="kafka.topic.profile.name",
            properties={"value": "profile-topic"},
        )
    ]
    build_navigation(result, tmp_path / "out-kafka", max_items=100)
    catalog = json.loads((tmp_path / "out-kafka" / "compact" / "system_interface_catalog.json").read_text(encoding="utf-8"))
    item = next(x for x in catalog["production_interfaces"] if x["boundary_kind"] == "kafka_consume")
    assert item["endpoint_or_topic_property_key"] == "kafka.topic.profile.name"
    assert item["endpoint_or_topic_resolved"] == "profile-topic"
    assert item["resolution_status"] == "resolved_config_value"


def test_kafka_publish_topic_property_binding_from_settings_assignment(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "KafkaPublisherSettingsDemo.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        enum Settings { KAFKA_TOPIC_OUT("kafka.topic.out.name"); Settings(String key) {} }
        class ApplicationSettings { String getStringValue(Settings s) { return ""; } }
        class KafkaTemplate<K,V> { void send(Object... args) {} }
        class Event { String id; }
        class Publisher {
          private KafkaTemplate<String, Event> kafkaTemplate;
          private ApplicationSettings settings;
          void publish(Event event) {
            String topic = settings.getStringValue(Settings.KAFKA_TOPIC_OUT);
            kafkaTemplate.send(topic, event.getId(), event);
          }
        }
        ''',
        encoding="utf-8",
    )

    _facts, _schemas, interfaces, _relations, _mapper_facts, warnings = scan_java_files([src])
    assert warnings == []
    publish = next(i for i in interfaces if i.kind == InterfaceKind.KAFKA and i.direction == Direction.OUTBOUND)
    assert publish.properties["topic_property_key"] == "kafka.topic.out.name"
    assert publish.properties["topic_settings_symbol"] == "KAFKA_TOPIC_OUT"
    assert publish.properties["topic_resolution_basis"] == "local_assignment_settings_getStringValue"


def test_http_outbound_catalog_uses_direct_rest_client_call_and_config_binding(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "RemoteClientDemo.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        import org.springframework.context.annotation.*;
        import org.springframework.boot.context.properties.ConfigurationProperties;
        import org.springframework.beans.factory.annotation.Qualifier;
        class RestClient { <T> T postForObject(String url, Object request, Class<T> responseType) { return null; } }
        class RestClientProperties {}
        class SslProperties {}
        class RemoteRequest { String clientId; }
        class RemoteResponse { String status; }
        class RemoteClient {
          private static final String API_URI = "/remote/get";
          private final RestClient restClient;
          RemoteClient(RestClient restClient) { this.restClient = restClient; }
          RemoteResponse call(RemoteRequest request) { return restClient.postForObject(API_URI, request, RemoteResponse.class); }
        }
        class AppConfig {
          @Bean
          @ConfigurationProperties("rest.remote")
          public RestClientProperties remoteProperties() { return new RestClientProperties(); }
          @Bean
          public RemoteClient remoteClient(@Qualifier("remoteProperties") RestClientProperties restProperties, SslProperties sslProperties) {
            return new RemoteClient(new RestClient(restProperties, sslProperties));
          }
        }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files([src])
    assert warnings == []
    outbound = next(i for i in interfaces if i.properties.get("boundary_role") == "http_outbound")
    assert outbound.path == "/remote/get"
    assert outbound.method == "POST"
    assert outbound.properties["base_url_property_key"] == "rest.remote.url"
    assert outbound.properties["base_url_resolution_status"] == "resolved_single_bean_configuration_properties"
    assert outbound.properties["request_payload_type"] == "RemoteRequest"
    assert outbound.properties["response_payload_type"] == "RemoteResponse"

    result = AnalysisResult(system_name="demo", project_code="demo", repo_path=str(tmp_path), files_analyzed=1)
    result.facts = facts
    result.schemas = schemas
    result.interfaces = interfaces
    result.relations = relations
    result.mapper_facts = mapper_facts
    result.config_facts = [
        __import__("code_analyzer_core.models", fromlist=["Fact"]).Fact(
            fact_type="config_property",
            name="rest.remote.url",
            properties={"value": "https://remote.example"},
        )
    ]
    build_navigation(result, tmp_path / "out-http", max_items=100)
    catalog = json.loads((tmp_path / "out-http" / "compact" / "system_interface_catalog.json").read_text(encoding="utf-8"))
    item = next(x for x in catalog["production_interfaces"] if x["boundary_kind"] == "http_outbound")
    assert item["protocol"] == "http"
    assert item["endpoint_or_topic_property_key"] == "rest.remote.url"
    assert item["endpoint_or_topic_resolved"] == "https://remote.example/remote/get"
    assert item["request_payload_type"] == "RemoteRequest"
    assert item["response_payload_type"] == "RemoteResponse"


def test_schema_fields_publish_observed_json_wire_names(tmp_path: Path) -> None:
    src = tmp_path / "WireDto.java"
    src.write_text(
        '''
        import com.google.gson.annotations.SerializedName;
        import com.fasterxml.jackson.annotation.JsonProperty;
        class GsonDto { @SerializedName("profile_id") String profileId; }
        class JacksonDto { @JsonProperty("phone_number") String phoneNumber; }
        ''',
        encoding="utf-8",
    )
    _facts, schemas, _interfaces, _relations, _mapper_facts, warnings = scan_java_files([src])
    assert warnings == []
    by_name = {schema.name: schema for schema in schemas}
    gson = by_name["GsonDto"].fields[0]
    jackson = by_name["JacksonDto"].fields[0]
    assert gson.serialized_name == "profile_id"
    assert gson.serialized_name_basis == "gson_serialized_name_annotation"
    assert gson.serialization_library == "gson"
    assert jackson.serialized_name == "phone_number"
    assert jackson.serialized_name_basis == "jackson_json_property_annotation"
    assert jackson.serialization_library == "jackson"


def test_static_serialization_name_constants_are_not_schema_fields(tmp_path: Path) -> None:
    src = tmp_path / "GeneratedDto.java"
    src.write_text(
        '''
        class GeneratedDto {
          public static final String SERIALIZED_NAME_ID = "id";
          private String id;
        }
        ''',
        encoding="utf-8",
    )
    _facts, schemas, _interfaces, _relations, _mapper_facts, _warnings = scan_java_files([src])
    dto = next(schema for schema in schemas if schema.name == "GeneratedDto")
    assert [field.name for field in dto.fields] == ["id"]


def test_grpc_service_exposes_request_and_response_boundaries(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "WriterGrpcServer.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        @GrpcService
        class WriterGrpcServer implements CloudWriterService {
          @Override
          public Multi<GrpcWriteResponse> writeWalRecords(Multi<GrpcWalRecord> request) {
            return null;
          }
        }
        interface CloudWriterService {}
        class Multi<T> {}
        class GrpcWalRecord { String data; }
        class GrpcWriteResponse { String status; }
        ''',
        encoding="utf-8",
    )

    facts, _schemas, interfaces, _relations, _mapper_facts, warnings = scan_java_files([src])

    assert warnings == []
    grpc = [i for i in interfaces if i.kind == InterfaceKind.GRPC]
    assert {(i.direction, i.schema_ref, i.properties["boundary_role"]) for i in grpc} == {
        (Direction.INBOUND, "GrpcWalRecord", "grpc_request"),
        (Direction.OUTBOUND, "GrpcWriteResponse", "grpc_response"),
    }
    assert all(i.path == "CloudWriterService/writeWalRecords" for i in grpc)
    assert any(f.fact_type == "grpc_service_declaration" for f in facts)


def test_external_facade_implementation_exposes_callback_boundaries(tmp_path: Path) -> None:
    src = tmp_path / "src" / "main" / "java" / "demo" / "SampleFacadeImpl.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        '''
        class SampleFacadeImpl implements InitDataSampleFacade, InternalProvider {
          @Override
          public LoadResult loadBatch(String entityType, int batchNum) { return null; }
        }
        class LoadResult { String status; }
        ''',
        encoding="utf-8",
    )

    facts, _schemas, interfaces, _relations, _mapper_facts, warnings = scan_java_files([src])

    assert warnings == []
    callbacks = [i for i in interfaces if i.kind == InterfaceKind.CALLBACK]
    assert {(i.direction, i.schema_ref, i.properties["boundary_role"]) for i in callbacks} == {
        (Direction.INBOUND, "method_parameters", "framework_callback_request"),
        (Direction.OUTBOUND, "LoadResult", "framework_callback_response"),
    }
    request = next(i for i in callbacks if i.direction == Direction.INBOUND)
    assert request.path == "InitDataSampleFacade/loadBatch"
    assert request.properties["request_parameters"] == [
        {"name": "entityType", "type": "String"},
        {"name": "batchNum", "type": "int"},
    ]
    assert not any(i.path and i.path.startswith("InternalProvider/") for i in callbacks)
    assert any(
        f.fact_type == "framework_callback_implementation"
        and f.properties["interface_name"] == "InitDataSampleFacade"
        for f in facts
    )
