from pathlib import Path

from code_analyzer_core.models import Direction, FieldInfo, InterfaceInfo, InterfaceKind, SchemaInfo
from code_analyzer_core.scanners.java_field_flow_builder import (
    FieldFlowBuilder,
    JavaFileContext,
    build_java_field_flow_facts,
    iter_named,
)
from code_analyzer_core.scanners.java_syntax import parse_java_workspace
from code_analyzer_core.scanners.java_scanner import scan_java_files


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _graph(facts):
    occurrences = {
        f.properties["occurrence_id"]: f.properties
        for f in facts
        if f.fact_type == "field_occurrence"
    }
    edges = [f.properties for f in facts if f.fact_type == "field_flow_edge"]
    return occurrences, edges


def _edge_paths(occurrences, edges, kind):
    out = []
    for edge in edges:
        if edge["edge_kind"] != kind:
            continue
        source = occurrences[edge["source_occurrence_id"]]
        target = occurrences[edge["target_occurrence_id"]]
        out.append((source.get("field_path") or source.get("symbol"), target.get("field_path") or target.get("symbol"), edge))
    return out


def test_local_helper_return_builder_and_guard_are_ast_backed(tmp_path: Path):
    path = _write(tmp_path, "Mapper.java", """
        class Mapper {
            LocalDate parse(String value) {
                return LocalDate.parse(value);
            }
            void map(Request request, TargetBuilder targetBuilder) {
                String raw = request.getProfile().getBirthDate().getValue();
                LocalDate birthDate = parse(raw);
                if (birthDate != null) {
                    targetBuilder.birthDate(birthDate);
                }
            }
        }
    """)

    facts, status = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, edges = _graph(facts)

    assert status["parser"] == "tree-sitter-java"
    assert status["java_files_parsed"] == 1
    assert status["java_files_with_parse_errors"] == 0
    assert all((x.get("ast_node") or {}).get("node_type") for x in occurrences.values())

    initializers = _edge_paths(occurrences, edges, "variable_initializer")
    assert any(source == "request.profile.birthDate.value" and target == "raw" for source, target, _ in initializers)

    bindings = _edge_paths(occurrences, edges, "method_argument_binding")
    assert any(source == "raw" and target == "value" for source, target, _ in bindings)

    assert _edge_paths(occurrences, edges, "method_return")
    assert _edge_paths(occurrences, edges, "return_to_caller")

    builder_edges = _edge_paths(occurrences, edges, "builder_argument")
    birth_builder = next(edge for source, target, edge in builder_edges if source == "birthDate" and target == "targetBuilder.birthDate")
    assert birth_builder["guards"]
    assert birth_builder["guards"][0]["branch"] == "consequence"
    assert "birthDate != null" in birth_builder["guards"][0]["expression_text"]


def test_shadowed_local_variable_resolves_to_nearest_block(tmp_path: Path):
    path = _write(tmp_path, "Shadow.java", """
        class Shadow {
            void map(Request request, Target target) {
                String value = request.getPrimary();
                if (request.isFallback()) {
                    String value = request.getFallback();
                    target.setValue(value);
                }
            }
        }
    """)
    facts, _ = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, edges = _graph(facts)
    setter = _edge_paths(occurrences, edges, "setter_argument")
    assert len(setter) == 1
    source_id = next(e["source_occurrence_id"] for e in edges if e["edge_kind"] == "setter_argument")
    source = occurrences[source_id]
    assert source["symbol"] == "value"
    # The selected declaration is the inner declaration, which starts after the outer one.
    values = sorted((x for x in occurrences.values() if x.get("symbol") == "value" and x.get("occurrence_kind") == "local_variable"), key=lambda x: x["ast_node"]["start_byte"])
    assert len(values) == 2
    assert source_id == values[-1]["occurrence_id"]


def test_ambiguous_overload_is_not_guessed(tmp_path: Path):
    path = _write(tmp_path, "Overloads.java", """
        class Overloads {
            String convert(String value) { return value; }
            Integer convert(Integer value) { return value; }
            void map(Object value, Target target) {
                target.setValue(convert(value));
            }
        }
    """)
    facts, status = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, edges = _graph(facts)
    invocation = next(x for x in occurrences.values() if x.get("field_path") == "Overloads.convert()")
    assert invocation["resolution_status"] == "ambiguous"
    assert len(invocation["candidate_method_ids"]) == 2
    assert not any(e["edge_kind"] == "method_argument_binding" and e.get("callee_method_id") in invocation["candidate_method_ids"] for e in edges)
    assert status["diagnostics_count"] >= 1


def test_controller_boundary_reuses_existing_interface_fact(tmp_path: Path):
    path = _write(tmp_path, "Controller.java", """
        class Controller {
            Response update(Request request) {
                return new Response(request.getValue());
            }
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="POST /update request",
            direction=Direction.INBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Request",
            operation="Controller.update",
            path="/update",
            method="POST",
        ),
        InterfaceInfo(
            name="POST /update",
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Response",
            operation="Controller.update",
            path="/update",
            method="POST",
        ),
    ]
    facts, _ = build_java_field_flow_facts([path], interfaces=interfaces, repository_id="repo-a")
    occurrences, edges = _graph(facts)
    inbound = next(x for x in occurrences.values() if x.get("occurrence_kind") == "inbound_payload")
    outbound = next(x for x in occurrences.values() if x.get("occurrence_kind") == "outbound_payload")
    assert inbound["boundary_path"] == "/update"
    assert outbound["boundary_path"] == "/update"
    boundary_edges = _edge_paths(occurrences, edges, "boundary_payload_binding")
    assert len(boundary_edges) == 2


def test_ucp_change_dt_chain_keeps_direct_edges_and_end_date_guard(tmp_path: Path):
    path = _write(tmp_path, "UpdatePhoneFlagsImpl.java", """
        class UpdatePhoneFlagsImpl {
            private FlagAttribute createFlagAttribute(FlagDto flagDto) {
                String updateDateTime = flagDto.getChangeDt();
                FlagAttributeBuilder flagAttributeBuilder = FlagAttribute.builder()
                        .updateDateTime(updateDateTime);
                if (BooleanUtils.isFalse(flagDto.getValue())) {
                    flagAttributeBuilder.endDate(updateDateTime);
                }
                return flagAttributeBuilder.build();
            }
        }
    """)
    facts, _ = build_java_field_flow_facts([path], repository_id="sbpr-ucp-intergation")
    occurrences, edges = _graph(facts)

    initializers = _edge_paths(occurrences, edges, "variable_initializer")
    assert any(source == "flagDto.changeDt" and target == "updateDateTime" for source, target, _ in initializers)

    builders = _edge_paths(occurrences, edges, "builder_argument")
    assert any(source == "updateDateTime" and target == "FlagAttribute.builder.updateDateTime" for source, target, _ in builders)
    end_date = next(edge for source, target, edge in builders if source == "updateDateTime" and target == "flagAttributeBuilder.endDate")
    assert "BooleanUtils.isFalse(flagDto.getValue())" in end_date["guards"][0]["expression_text"]


def test_ucp_overloaded_birth_date_helper_is_resolved_by_argument_types(tmp_path: Path):
    path = _write(tmp_path, "SbprCreateServiceMapperImpl.java", """
        class SbprCreateServiceMapperImpl {
            Request map(CreateLightClientRequest request) {
                RequestBuilder builder = Request.builder();
                setBirthDate(request, builder);
                return builder.build();
            }
            Request map(BaseProfileResponseDto baseProfile) {
                RequestBuilder builder = Request.builder();
                setBirthDate(baseProfile, builder);
                return builder.build();
            }
            private void setBirthDate(CreateLightClientRequest request, RequestBuilder builder) {
                LocalDate birthDate = LocalDate.parse(request.getProfile().getBirthDate().getValue());
                builder.birthDate(birthDate);
            }
            private void setBirthDate(BaseProfileResponseDto baseProfile, RequestBuilder builder) {
                LocalDate birthDate = LocalDate.parse(baseProfile.getBirthDate());
                builder.birthDate(birthDate);
            }
        }
    """)
    facts, status = build_java_field_flow_facts([path], repository_id="sbpr-ucp-intergation")
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "method_argument_binding")

    assert any(source == "request" and target == "request" for source, target, _ in bindings)
    assert any(source == "baseProfile" and target == "baseProfile" for source, target, _ in bindings)
    ambiguous_set_birth_date = [
        d for d in status["diagnostics"]
        if d.get("kind") == "ambiguous_method_call" and "setBirthDate" in str(d.get("expression"))
    ]
    assert ambiguous_set_birth_date == []


def test_ids_are_stable_for_same_repository_relative_path(tmp_path: Path):
    source = """
        class Stable {
            void map(Request request, Target target) {
                String value = request.getValue();
                target.setValue(value);
            }
        }
    """
    root_a = tmp_path / "checkout-a"
    root_b = tmp_path / "checkout-b"
    path_a = _write(root_a, "src/main/java/Stable.java", source)
    path_b = _write(root_b, "src/main/java/Stable.java", source)

    facts_a, _ = build_java_field_flow_facts([path_a], repository_id="stable-repo", repository_root=root_a)
    facts_b, _ = build_java_field_flow_facts([path_b], repository_id="stable-repo", repository_root=root_b)

    occurrence_ids_a = sorted(f.properties["occurrence_id"] for f in facts_a if f.fact_type == "field_occurrence")
    occurrence_ids_b = sorted(f.properties["occurrence_id"] for f in facts_b if f.fact_type == "field_occurrence")
    edge_ids_a = sorted(f.properties["edge_id"] for f in facts_a if f.fact_type == "field_flow_edge")
    edge_ids_b = sorted(f.properties["edge_id"] for f in facts_b if f.fact_type == "field_flow_edge")
    assert occurrence_ids_a == occurrence_ids_b
    assert edge_ids_a == edge_ids_b



def test_rest_request_fields_bind_concrete_payload_symbol_to_wire_contract(tmp_path: Path):
    path = _write(tmp_path, "Client.java", """
        class Client {
            Response send(Request request) {
                HttpEntity<Request> entity = new HttpEntity<>(request);
                return restTemplate.exchange("/search", HttpMethod.POST, entity, Response.class).getBody();
            }
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="POST /search",
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Response",
            operation="Client.send",
            path="/search",
            method="POST",
            properties={
                "boundary_role": "http_outbound",
                "request_payload_expression": "entity",
                "request_payload_type": "Request",
            },
        )
    ]
    schemas = [SchemaInfo(name="Request", source_type="java", fields=[
        FieldInfo(
            name="profileId",
            type="String",
            serialized_name="sberProfileId",
            serialized_name_basis="gson_serialized_name_annotation",
            serialization_library="gson",
        )
    ])]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="repo-a"
    )
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "rest_request_serialization_field")
    assert len(bindings) == 1
    source, target, edge = bindings[0]
    assert source == "request.profileId"
    assert target == "boundary:rest:/search:request.sberProfileId"
    assert edge["wire_field_path"] == "sberProfileId"
    assert edge["serialized_name_basis"] == "gson_serialized_name_annotation"
    boundary = occurrences[edge["target_occurrence_id"]]
    assert boundary["occurrence_kind"] == "boundary_field"
    assert boundary["field_binding_basis"] == "typed_payload_symbol_used_in_boundary_operation"


def test_explicit_deserializer_binds_wire_contract_to_local_dto_field(tmp_path: Path):
    path = _write(tmp_path, "Service.java", """
        class Service {
            HttpResponse search(AggregatedHttpRequest httpRequest) {
                String json = httpRequest.contentUtf8();
                RequestDto requestDto = jsonConverter.deserialize(json, RequestDto.class);
                return service.call(requestDto);
            }
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="POST /search request",
            direction=Direction.INBOUND,
            kind=InterfaceKind.REST,
            schema_ref="RequestDto",
            operation="Service.search",
            path="/search",
            method="POST",
            properties={"boundary_role": "rest_request", "request_payload_type": "RequestDto"},
        )
    ]
    schemas = [SchemaInfo(name="RequestDto", source_type="java", fields=[
        FieldInfo(name="sberProfileId", type="String", serialized_name="sberProfileId")
    ])]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="repo-b"
    )
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "rest_request_deserialization_field")
    assert len(bindings) == 1
    source, target, edge = bindings[0]
    assert source == "boundary:rest:/search:request.sberProfileId"
    assert target == "requestDto.sberProfileId"
    assert edge["field_binding_basis"] == "explicit_deserializer_result_type"
    assert occurrences[edge["source_occurrence_id"]]["occurrence_kind"] == "boundary_field"



def test_kafka_payload_fields_use_serialization_and_deserialization_relations(tmp_path: Path):
    producer = _write(tmp_path, "Producer.java", """
        class Producer {
            void publish(ProfileEvent event) {
                kafkaTemplate.send("profile.events", event);
            }
        }
    """)
    consumer = _write(tmp_path, "Consumer.java", """
        class Consumer {
            void consume(ProfileEvent event) {
                service.handle(event);
            }
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="profile.events",
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.KAFKA,
            schema_ref="ProfileEvent",
            operation="Producer.publish",
            path="profile.events",
            properties={"boundary_role": "kafka_publish", "payload_expression": "event"},
        ),
        InterfaceInfo(
            name="profile.events",
            direction=Direction.INBOUND,
            kind=InterfaceKind.KAFKA,
            schema_ref="ProfileEvent",
            operation="Consumer.consume",
            path="profile.events",
            properties={"boundary_role": "kafka_consume"},
        ),
    ]
    schemas = [SchemaInfo(name="ProfileEvent", fields=[
        FieldInfo(name="profileId", type="String", serialized_name="profile_id",
                  serialized_name_basis="jackson_json_property_annotation", serialization_library="jackson")
    ])]

    facts, _ = build_java_field_flow_facts(
        [producer, consumer], interfaces=interfaces, schemas=schemas, repository_id="repo-kafka"
    )
    occurrences, edges = _graph(facts)
    outbound = _edge_paths(occurrences, edges, "kafka_message_serialization_field")
    inbound = _edge_paths(occurrences, edges, "kafka_message_deserialization_field")
    assert any(source == "event.profileId" and target.endswith("message.profile_id") for source, target, _ in outbound)
    assert any(source.endswith("message.profile_id") and target == "event.profileId" for source, target, _ in inbound)


def _has_directed_path(occurrences, edges, source_predicate, target_predicate):
    starts = [oid for oid, item in occurrences.items() if source_predicate(item)]
    targets = {oid for oid, item in occurrences.items() if target_predicate(item)}
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["source_occurrence_id"], []).append(edge["target_occurrence_id"])
    seen = set(starts)
    queue = list(starts)
    while queue:
        current = queue.pop(0)
        if current in targets:
            return True
        for nxt in adjacency.get(current, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def test_boundary_seeded_nested_builder_projects_only_requested_child_field(tmp_path: Path):
    path = _write(tmp_path, "NestedBuilderClient.java", """
        class NestedBuilderClient {
            void process(Source source) {
                Outbound request = Outbound.builder()
                    .phone(Phone.builder()
                        .phoneNumber(source.getPhoneNumber())
                        .ignored(source.getIgnored())
                        .build())
                    .build();
                send(request);
            }
            void send(Outbound request) { }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /phone",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="Response",
        operation="NestedBuilderClient.send",
        path="/phone",
        method="POST",
        properties={"request_payload_type": "Outbound", "request_payload_expression": "request"},
    )]
    schemas = [
        SchemaInfo(name="Outbound", source_type="java", fields=[FieldInfo(name="phone", type="Phone")]),
        SchemaInfo(name="Phone", source_type="java", fields=[FieldInfo(name="phoneNumber", type="String")]),
    ]
    facts, status = build_java_field_flow_facts(path and [path], interfaces=interfaces, schemas=schemas, repository_id="repo-a")
    occurrences, edges = _graph(facts)

    assert status["object_field_projection"]["mode"] == "boundary_seeded_demand_driven"
    assert status["object_field_projection"]["projection_seed_fields"] == 2
    assert any(item.get("field_path") == "Outbound.builder.phone.phoneNumber" for item in occurrences.values())
    assert not any(
        item.get("occurrence_kind") == "projected_object_field" and str(item.get("field_path", "")).endswith(".ignored")
        for item in occurrences.values()
    )
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "source.phoneNumber",
        lambda item: item.get("field_path") == "boundary:rest:/phone:request.phone.phoneNumber",
    )


def test_boundary_seeded_helper_builder_mutation_reaches_wire_field(tmp_path: Path):
    path = _write(tmp_path, "HelperBuilderClient.java", """
        class HelperBuilderClient {
            void process(Input input) {
                OutboundBuilder builder = Outbound.builder();
                completePhone(input.getPhone(), builder);
                Outbound request = builder.build();
                send(request);
            }
            void completePhone(PhoneInput phone, OutboundBuilder builder) {
                PhoneDto phoneDto = PhoneDto.builder()
                    .phoneNumber(phone.getPhoneNumber())
                    .build();
                builder.phoneNumber(phoneDto);
            }
            void send(Outbound request) { }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /updateOrCreate",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="Response",
        operation="HelperBuilderClient.send",
        path="/updateOrCreate",
        method="POST",
        properties={"request_payload_type": "Outbound", "request_payload_expression": "request"},
    )]
    schemas = [
        SchemaInfo(name="Outbound", source_type="java", fields=[FieldInfo(name="phoneNumber", type="PhoneDto")]),
        SchemaInfo(name="PhoneDto", source_type="java", fields=[FieldInfo(name="phoneNumber", type="String")]),
    ]
    facts, _ = build_java_field_flow_facts([path], interfaces=interfaces, schemas=schemas, repository_id="repo-a")
    occurrences, edges = _graph(facts)

    assert any(item.get("field_path") == "builder.phoneNumber.phoneNumber" for item in occurrences.values())
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "input.phone.phoneNumber",
        lambda item: item.get("field_path") == "boundary:rest:/updateOrCreate:request.phoneNumber.phoneNumber",
    )


def test_external_dependency_nested_builder_seeds_boundary_without_local_schema(tmp_path: Path):
    path = _write(tmp_path, "ExternalDtoClient.java", """
        class ExternalDtoClient {
            void process(Input input) {
                ExternalRequest request = ExternalRequest.builder()
                    .phone(PhoneAttribute.builder()
                        .phoneNumber(input.getPhoneNumber())
                        .build())
                    .build();
                send(request);
            }
            void send(ExternalRequest request) { }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /external",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="ExternalResponse",
        operation="ExternalDtoClient.send",
        path="/external",
        method="POST",
        properties={"request_payload_type": "ExternalRequest", "request_payload_expression": "request"},
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="repo-external"
    )
    occurrences, edges = _graph(facts)

    assert status["object_field_projection"]["observed_builder_boundary_fields"] >= 2
    target = "boundary:rest:/external:request.phone.phoneNumber"
    assert any(item.get("field_path") == target for item in occurrences.values())
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "input.phoneNumber",
        lambda item: item.get("field_path") == target,
    )
    boundary = next(item for item in occurrences.values() if item.get("field_path") == target)
    assert boundary["wire_alias_resolution_status"] == "unverified_external_contract"
    assert boundary["field_path_basis"] == "tree_sitter_observed_builder_object_path"


def test_unique_interface_implementation_parameter_bridge_keeps_nested_payload_flow(tmp_path: Path):
    path = _write(tmp_path, "InterfaceProxyClient.java", """
        interface ExternalProxy {
            void send(ExternalRequest request);
        }
        class ExternalProxyImpl implements ExternalProxy {
            public void send(ExternalRequest request) { }
        }
        class Service {
            ExternalProxy proxy;
            void process(Input input) {
                ExternalRequest request = ExternalRequest.builder()
                    .phone(PhoneAttribute.builder()
                        .phoneNumber(input.getPhoneNumber())
                        .build())
                    .build();
                proxy.send(request);
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /external",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="ExternalResponse",
        operation="ExternalProxyImpl.send",
        path="/external",
        method="POST",
        properties={"request_payload_type": "ExternalRequest", "request_payload_expression": "request"},
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="repo-interface"
    )
    occurrences, edges = _graph(facts)
    target = "boundary:rest:/external:request.phone.phoneNumber"

    assert status["object_field_projection"]["interface_implementation_bindings"] >= 1
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "input.phoneNumber",
        lambda item: item.get("field_path") == target,
    )
    assert any(edge["edge_kind"] == "interface_implementation_parameter_binding_field_projection" for edge in edges)


def test_http_client_response_fields_bind_boundary_to_local_dto(tmp_path: Path):
    path = _write(tmp_path, "ResponseClient.java", """
        class ResponseClient {
            Response send(Request request) {
                Response response = restTemplate.exchange(
                    "/update", HttpMethod.POST, new HttpEntity<>(request), Response.class
                ).getBody();
                return response;
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /update",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="Response",
        operation="ResponseClient.send",
        path="/update",
        method="POST",
        properties={
            "boundary_role": "http_outbound",
            "request_payload_type": "Request",
            "response_payload_type": "Response",
        },
    )]
    schemas = [
        SchemaInfo(name="Request", source_type="java", fields=[FieldInfo(name="value", type="String")]),
        SchemaInfo(name="Response", source_type="java", fields=[
            FieldInfo(name="profileId", type="String", serialized_name="sberProfileId")
        ]),
    ]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="response-client"
    )
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "rest_response_deserialization_field")

    assert any(
        source == "boundary:rest:/update:response.sberProfileId"
        and target == "response.profileId"
        for source, target, _ in bindings
    )
    payload_bindings = _edge_paths(occurrences, edges, "boundary_response_payload_binding")
    assert any(source == "boundary:rest:/update:response" and target == "response" for source, target, _ in payload_bindings)



def test_external_http_response_getter_is_published_as_correspondence(tmp_path: Path):
    path = _write(tmp_path, "ExternalUserInfoClient.java", """
        class ExternalUserInfoClient {
            Profile load(String ucpId) {
                UserInfo userInfo = restTemplate.exchange(
                    "/userinfo", HttpMethod.GET, null, UserInfo.class
                ).getBody();
                return Profile.builder()
                    .firstName(userInfo.getGivenName())
                    .email(userInfo.email)
                    .build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="GET /userinfo",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="UserInfo",
        operation="ExternalUserInfoClient.load",
        path="/userinfo",
        method="GET",
        properties={
            "boundary_role": "http_outbound",
            "response_payload_type": "UserInfo",
        },
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="external-userinfo-client"
    )
    occurrences, edges = _graph(facts)
    correspondences = _edge_paths(occurrences, edges, "response_property_correspondence")

    assert any(
        source == "boundary:rest:/userinfo:response.givenName"
        and target == "userInfo.givenName"
        and edge.get("relation_class") == "correspondence"
        and edge.get("wire_alias_verified") is False
        for source, target, edge in correspondences
    )
    assert any(
        source == "boundary:rest:/userinfo:response.email"
        and target == "userInfo.email"
        for source, target, _edge in correspondences
    )
    boundary = next(
        item for item in occurrences.values()
        if item.get("field_path") == "boundary:rest:/userinfo:response.givenName"
    )
    assert boundary["field_binding_kind"] == "rest_response_observed_getter_property"
    assert boundary["property_name_basis"] == "java_beans_getter"
    assert boundary["wire_alias_resolution_status"] == "unverified_external_contract"
    assert status["parser"] == "tree-sitter-java"

def test_external_http_response_chained_getter_receiver_is_observed(tmp_path: Path):
    path = _write(tmp_path, "ExternalBirthdateClient.java", """
        class ExternalBirthdateClient {
            Profile load() {
                UserInfo userInfo = restTemplate.exchange(
                    "/userinfo", HttpMethod.GET, null, UserInfo.class
                ).getBody();
                String birthdate = userInfo.getBirthdate() != null
                    ? userInfo.getBirthdate().format(formatter)
                    : null;
                return Profile.builder().birthDate(birthdate).build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="GET /userinfo",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="UserInfo",
        operation="ExternalBirthdateClient.load",
        path="/userinfo",
        method="GET",
        properties={
            "boundary_role": "http_outbound",
            "response_payload_type": "UserInfo",
        },
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="external-birthdate-client"
    )
    occurrences, edges = _graph(facts)
    correspondences = _edge_paths(occurrences, edges, "response_property_correspondence")
    assert any(
        source == "boundary:rest:/userinfo:response.birthdate"
        and target == "userInfo.birthdate"
        and edge.get("property_name_basis") == "java_beans_getter"
        for source, target, edge in correspondences
    )
    receiver_edges = _edge_paths(occurrences, edges, "invocation_receiver")
    assert any(
        source == "userInfo.birthdate"
        and target.endswith("getBirthdate().format()")
        for source, target, _edge in receiver_edges
    )
    assert status["parser"] == "tree-sitter-java"


def test_external_http_response_getters_are_reached_through_return_and_mapper_bindings(tmp_path: Path):
    path = _write(tmp_path, "ExternalResponseJourney.java", """
        interface UserInfoService {
            UserInfo load(Request request);
        }
        class UserInfoServiceImpl implements UserInfoService {
            RestTemplate restTemplate;
            public UserInfo load(Request request) {
                ResponseEntity<UserInfo> response = restTemplate.exchange(
                    "/userinfo", HttpMethod.POST, new HttpEntity<>(request), UserInfo.class
                );
                UserInfo body = response.getBody();
                return body;
            }
        }
        interface ProfileMapper {
            Profile map(UserInfo userInfo);
        }
        class ProfileMapperImpl implements ProfileMapper {
            public Profile map(UserInfo userInfo) {
                return Profile.builder()
                    .firstName(userInfo.getGivenName())
                    .email(userInfo.getEmail())
                    .build();
            }
        }
        class ProfileService {
            UserInfoService userInfoService;
            ProfileMapper profileMapper;
            Profile execute(Request request) {
                UserInfo userInfo = userInfoService.load(request);
                return profileMapper.map(userInfo);
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /userinfo",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="UserInfo",
        operation="UserInfoServiceImpl.load",
        path="/userinfo",
        method="POST",
        properties={
            "boundary_role": "http_outbound",
            "request_payload_type": "Request",
            "response_payload_type": "UserInfo",
        },
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="external-response-journey"
    )
    occurrences, edges = _graph(facts)
    correspondences = _edge_paths(occurrences, edges, "response_property_correspondence")

    given = next(
        edge for source, target, edge in correspondences
        if source == "boundary:rest:/userinfo:response.givenName"
        and target == "userInfo.givenName"
    )
    assert given["relation_class"] == "correspondence"
    assert given["wire_alias_verified"] is False
    assert "method_return" in given["object_binding_path"]
    assert "return_to_caller" in given["object_binding_path"]
    assert "method_argument_binding" in given["object_binding_path"]
    assert any(
        source == "boundary:rest:/userinfo:response.email" and target == "userInfo.email"
        for source, target, _edge in correspondences
    )
    assert status["object_field_projection"]["external_response_property_observations"] >= 2
    assert status["object_field_projection"]["external_response_property_objects_visited"] >= 2


def test_http_client_response_projection_follows_used_helper_fields_only(tmp_path: Path):
    path = _write(tmp_path, "ResponseClientHelper.java", """
        class ResponseClientHelper {
            ActivateResponse send(Request request) {
                UpdateResponse response = restTemplate.exchange(
                    "/update", HttpMethod.POST, new HttpEntity<>(request), UpdateResponse.class
                ).getBody();
                return map(response);
            }
            ActivateResponse map(UpdateResponse response) {
                BaseProfile base = baseProfile(response);
                return ActivateResponse.builder()
                    .profileId(response.getProfileId())
                    .surName(response.getName().getSurname())
                    .firstName(response.getName().getName())
                    .baseProfile(base)
                    .build();
            }
            BaseProfile baseProfile(UpdateResponse response) {
                return BaseProfile.builder()
                    .phone(response.getPhone().getValue())
                    .build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /update",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="UpdateResponse",
        operation="ResponseClientHelper.send",
        path="/update",
        method="POST",
        properties={
            "boundary_role": "http_outbound",
            "request_payload_type": "Request",
            "response_payload_type": "UpdateResponse",
        },
    )]
    schemas = [
        SchemaInfo(name="Request", source_type="java", fields=[FieldInfo(name="value", type="String")]),
        SchemaInfo(name="Phone", source_type="java", fields=[FieldInfo(name="value", type="String")]),
        SchemaInfo(name="Name", source_type="java", fields=[
            FieldInfo(name="surname", type="String"),
            FieldInfo(name="name", type="String"),
        ]),
        SchemaInfo(name="UpdateResponse", source_type="java", fields=[
            FieldInfo(name="profileId", type="String", serialized_name="sberProfileId"),
            FieldInfo(name="phone", type="Phone", nested_type="Phone"),
            FieldInfo(name="name", type="Name", nested_type="Name"),
            FieldInfo(name="unused", type="String"),
        ]),
    ]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="response-client-helper"
    )
    occurrences, edges = _graph(facts)

    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/update:response.sberProfileId",
        lambda item: item.get("field_path") == "ActivateResponse.builder.profileId",
    )
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/update:response.phone.value",
        lambda item: item.get("field_path") == "BaseProfile.builder.phone",
    )
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/update:response.name.surname",
        lambda item: item.get("field_path") == "ActivateResponse.builder.surName",
    )
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/update:response.name.name",
        lambda item: item.get("field_path") == "ActivateResponse.builder.firstName",
    )
    assert any(edge["edge_kind"] == "method_argument_binding_field_projection" for edge in edges)
    assert status["object_field_projection"]["projection_seed_skipped_without_sink"] >= 1
    assert not any(
        item.get("occurrence_kind") == "projected_object_field"
        and str(item.get("field_path") or "").endswith(".unused")
        for item in occurrences.values()
    )


def test_explicitly_serialized_server_response_fields_bind_to_boundary(tmp_path: Path):
    path = _write(tmp_path, "ResponseController.java", """
        class ResponseController {
            Service service;
            HttpResponse update(Request request) {
                var response = service.process(request);
                String responseJson = jsonConverter.serialize(response);
                return HttpResponse.of(HttpStatus.OK, MediaType.JSON_UTF_8, responseJson);
            }
        }
        class Service {
            ResponseDto process(Request request) {
                return ResponseDto.builder().profileId(request.getProfileId()).build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /update response",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="HttpResponse",
        operation="ResponseController.update",
        path="/update",
        method="POST",
        properties={
            "boundary_role": "rest_response",
            "response_payload_type": "HttpResponse",
        },
    )]
    schemas = [SchemaInfo(name="ResponseDto", source_type="java", fields=[
        FieldInfo(name="profileId", type="String", serialized_name="sberProfileId")
    ])]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="response-server"
    )
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "rest_response_serialization_field")

    matching = [
        edge for source, target, edge in bindings
        if source == "response.profileId"
        and target == "boundary:rest:/update:response.sberProfileId"
    ]
    assert len(matching) == 1
    assert matching[0]["field_binding_basis"] == "explicit_serializer_argument_reaching_response"
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "request.profileId",
        lambda item: item.get("field_path") == "boundary:rest:/update:response.sberProfileId",
    )


def test_generic_server_response_wrapper_uses_declared_payload_type(tmp_path: Path):
    path = _write(tmp_path, "AsyncController.java", """
        class AsyncController {
            CompletableFuture<ResponseDto> update(Request request) {
                ResponseDto response = service.process(request);
                return CompletableFuture.completedFuture(response);
            }
        }
        class Service {
            ResponseDto process(Request request) {
                return ResponseDto.builder().status(request.getStatus()).build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /async response",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="ResponseDto",
        operation="AsyncController.update",
        path="/async",
        method="POST",
        properties={
            "boundary_role": "rest_response",
            "response_payload_type": "ResponseDto",
        },
    )]
    schemas = [SchemaInfo(name="ResponseDto", source_type="java", fields=[
        FieldInfo(name="status", type="String")
    ])]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="async-server"
    )
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "rest_response_serialization_field")

    assert any(
        target == "boundary:rest:/async:response.status"
        for _source, target, _edge in bindings
    )


def test_logging_only_serializer_does_not_create_response_binding(tmp_path: Path):
    path = _write(tmp_path, "LoggingController.java", """
        class LoggingController {
            HttpResponse update(Request request) {
                ResponseDto response = service.process(request);
                String debugJson = jsonConverter.serialize(response);
                logger.info(debugJson);
                return HttpResponse.of(HttpStatus.NO_CONTENT);
            }
        }
        class Service {
            ResponseDto process(Request request) { return new ResponseDto(); }
        }
    """)
    interfaces = [InterfaceInfo(
        name="POST /logging response",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="HttpResponse",
        operation="LoggingController.update",
        path="/logging",
        method="POST",
        properties={
            "boundary_role": "rest_response",
            "response_payload_type": "HttpResponse",
        },
    )]
    schemas = [SchemaInfo(name="ResponseDto", source_type="java", fields=[
        FieldInfo(name="status", type="String")
    ])]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="logging-server"
    )
    _occurrences, edges = _graph(facts)
    assert not any(edge["edge_kind"] == "rest_response_serialization_field" for edge in edges)


def test_collection_foreach_lambda_and_add_publish_element_flow(tmp_path: Path):
    path = _write(tmp_path, "CollectionMapper.java", """
        class CollectionMapper {
            void map(UserInfo userInfo, TargetBuilder target) {
                List<ShippingAddress> shippingAddresses = userInfo.getShippingAddresses();
                List<DeliveryAddressDto> deliveryAddressDtos = new ArrayList<>();
                shippingAddresses.forEach(shippingAddress -> {
                    deliveryAddressDtos.add(DeliveryAddressDto.builder()
                            .id(shippingAddress.getId())
                            .build());
                });
                target.deliveryAddress(deliveryAddressDtos);
            }
        }
    """)

    facts, status = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, edges = _graph(facts)

    lambda_parameter = next(
        item
        for item in occurrences.values()
        if item.get("occurrence_kind") == "lambda_parameter"
        and item.get("symbol") == "shippingAddress"
    )
    assert lambda_parameter["declared_type"] == "ShippingAddress"
    assert lambda_parameter["parameter_type_basis"] == "declared_collection_generic_argument"

    element_binding = _edge_paths(occurrences, edges, "collection_element_to_lambda_parameter")
    assert any(
        source == "shippingAddresses" and target == "shippingAddress"
        for source, target, _ in element_binding
    )

    additions = _edge_paths(occurrences, edges, "collection_element_addition")
    assert any(target == "deliveryAddressDtos" for _, target, _ in additions)

    shipping_id = next(
        item
        for item in occurrences.values()
        if item.get("field_path") == "shippingAddress.id"
    )
    assert shipping_id["resolution_status"] == "resolved"
    assert not any(
        item.get("occurrence_kind") == "unresolved_identifier"
        and item.get("symbol") == "shippingAddress"
        for item in occurrences.values()
    )
    assert status["edge_kind_counts"]["collection_element_to_lambda_parameter"] == 1
    assert status["edge_kind_counts"]["collection_element_addition"] == 1


def test_nested_collection_lambdas_bind_only_their_own_parameters(tmp_path: Path):
    path = _write(tmp_path, "NestedCollectionMapper.java", """
        class NestedCollectionMapper {
            void map(List<Outer> outers, Target target) {
                List<Result> results = new ArrayList<>();
                outers.forEach(outer -> {
                    List<Inner> inners = outer.getInners();
                    inners.forEach(inner -> results.add(Result.builder()
                            .outerId(outer.getId())
                            .innerId(inner.getId())
                            .build()));
                });
                target.results(results);
            }
        }
    """)

    facts, status = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, edges = _graph(facts)
    bindings = _edge_paths(occurrences, edges, "collection_element_to_lambda_parameter")

    assert any(source == "outers" and target == "outer" for source, target, _ in bindings)
    assert any(source == "inners" and target == "inner" for source, target, _ in bindings)
    assert status["edge_kind_counts"]["collection_element_to_lambda_parameter"] == 2
    assert not any(item.get("kind") == "unsupported_collection_lambda_arity" for item in status.get("diagnostics", []))


def test_explicit_typed_lambda_uses_tree_sitter_parameter_type(tmp_path: Path):
    path = _write(tmp_path, "TypedLambdaMapper.java", """
        class TypedLambdaMapper {
            void map(List<ShippingAddress> addresses) {
                addresses.forEach((ShippingAddress address) -> address.getId());
            }
        }
    """)

    facts, _ = build_java_field_flow_facts([path], repository_id="repo-a")
    occurrences, _ = _graph(facts)
    parameter = next(
        item for item in occurrences.values()
        if item.get("occurrence_kind") == "lambda_parameter" and item.get("symbol") == "address"
    )
    assert parameter["declared_type"] == "ShippingAddress"
    assert parameter["parameter_type_basis"] == "explicit_lambda_parameter_type"


def test_external_response_nested_collection_properties_are_observed_through_lambda_bindings(tmp_path: Path):
    path = _write(tmp_path, "ExternalShippingClient.java", """
        class ExternalShippingClient {
            Profile load() {
                UserInfo userInfo = restTemplate.exchange(
                    "/userinfo", HttpMethod.GET, null, UserInfo.class
                ).getBody();
                List<ShippingAddress> shippingAddresses = userInfo.getShippingAddresses();
                List<DeliveryAddressDto> deliveryAddressDtos = new ArrayList<>();
                shippingAddresses.forEach(shippingAddress -> {
                    DeliveryAddress address = shippingAddress.getAddress();
                    deliveryAddressDtos.add(DeliveryAddressDto.builder()
                        .id(shippingAddress.getId())
                        .line(address.getLine3())
                        .build());
                });
                return Profile.builder().deliveryAddress(deliveryAddressDtos).build();
            }
        }
    """)
    interfaces = [InterfaceInfo(
        name="GET /userinfo",
        direction=Direction.OUTBOUND,
        kind=InterfaceKind.REST,
        schema_ref="UserInfo",
        operation="ExternalShippingClient.load",
        path="/userinfo",
        method="GET",
        properties={
            "boundary_role": "http_outbound",
            "response_payload_type": "UserInfo",
        },
    )]

    facts, status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=[], repository_id="external-shipping-client"
    )
    occurrences, edges = _graph(facts)
    correspondences = _edge_paths(occurrences, edges, "response_property_correspondence")

    shipping_id = next(
        edge for source, target, edge in correspondences
        if source == "boundary:rest:/userinfo:response.shippingAddresses.id"
        and target == "shippingAddress.id"
    )
    assert shipping_id["relation_class"] == "correspondence"
    assert shipping_id["property_path_depth"] == 1
    assert "collection_element_to_lambda_parameter" in shipping_id["object_binding_path"]
    assert "observed_property_value" in shipping_id["object_binding_path"]

    address_line = next(
        edge for source, target, edge in correspondences
        if source == "boundary:rest:/userinfo:response.shippingAddresses.address.line3"
        and target == "address.line3"
    )
    assert address_line["property_path_depth"] == 2
    assert "variable_initializer" in address_line["object_binding_path"]
    assert status["object_field_projection"]["external_response_property_observations"] >= 4

    contributions = _edge_paths(occurrences, edges, "object_field_contribution_to_built_object")
    shipping_contribution = next(
        edge for source, target, edge in contributions
        if source == "shippingAddress" and target == "DeliveryAddressDto.builder.build()"
    )
    assert shipping_contribution["contribution_basis"] == "observed_builder_argument_field_owner"
    assert shipping_contribution["contributed_builder_fields"] == ["id"]
    assert shipping_contribution["contributor_field_paths"] == ["id"]

    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/userinfo:response.shippingAddresses",
        lambda item: item.get("field_path") == "Profile.builder.deliveryAddress",
    )
    assert status["object_field_projection"]["object_contribution_edges_created"] >= 1


def test_inbound_controller_interface_implementation_nested_field_reaches_outbound_sink(tmp_path: Path):
    path = _write(tmp_path, "IngressInterfaceChain.java", """
        class Controller {
            Service service;
            void handle(Input request) { service.process(request); }
        }
        interface Service { void process(Input request); }
        class ServiceImpl implements Service {
            ExternalProxy proxy;
            public void process(Input request) {
                processPhone(request.getProfile().getPhone());
            }
            void processPhone(Phone phone) {
                ExternalRequest outbound = ExternalRequest.builder()
                    .phoneNumber(phone.getPhoneNumber())
                    .build();
                proxy.send(outbound);
            }
        }
        interface ExternalProxy { void send(ExternalRequest request); }
        class ExternalProxyImpl implements ExternalProxy {
            public void send(ExternalRequest request) { }
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="POST /in request",
            direction=Direction.INBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Input",
            operation="Controller.handle",
            path="/in",
            method="POST",
            properties={"request_payload_type": "Input"},
        ),
        InterfaceInfo(
            name="POST /out request",
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.REST,
            schema_ref="ExternalResponse",
            operation="ExternalProxyImpl.send",
            path="/out",
            method="POST",
            properties={"request_payload_type": "ExternalRequest", "request_payload_expression": "request"},
        ),
    ]
    schemas = [
        SchemaInfo(name="Input", source_type="java", fields=[FieldInfo(name="profile", type="Profile", nested_type="Profile")]),
        SchemaInfo(name="Profile", source_type="java", fields=[FieldInfo(name="phone", type="Phone", nested_type="Phone")]),
        SchemaInfo(name="Phone", source_type="java", fields=[FieldInfo(name="phoneNumber", type="String")]),
        SchemaInfo(name="ExternalRequest", source_type="java", fields=[FieldInfo(name="phoneNumber", type="String")]),
    ]

    facts, _ = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="repo-ingress-chain"
    )
    occurrences, edges = _graph(facts)
    assert _has_directed_path(
        occurrences,
        edges,
        lambda item: item.get("field_path") == "boundary:rest:/in:request.profile.phone.phoneNumber",
        lambda item: item.get("field_path") == "boundary:rest:/out:request.phoneNumber",
    )
    assert any(
        edge.get("edge_kind") == "observed_nested_object_field_projection"
        for edge in edges
    )


def test_grpc_and_callback_boundaries_keep_protocol_specific_field_bindings(tmp_path: Path):
    grpc_path = _write(tmp_path, "GrpcService.java", """
        @GrpcService
        class GrpcService implements CloudWriterService {
            @Override
            GrpcResponse write(GrpcRequest request) {
                return new GrpcResponse(request.getData());
            }
        }
        class GrpcRequest { String data; String getData() { return data; } }
        class GrpcResponse { String status; GrpcResponse(String status) { this.status = status; } }
    """)
    callback_path = _write(tmp_path, "ReplicaFacade.java", """
        class ReplicaFacade implements InitDataSampleFacade {
            @Override
            LoadResult load(DataRequest request) {
                return new LoadResult(request.getEntityType());
            }
        }
        class DataRequest { String entityType; String getEntityType() { return entityType; } }
        class LoadResult { String value; LoadResult(String value) { this.value = value; } }
    """)
    files = [grpc_path, callback_path]
    _scan_facts, schemas, interfaces, _relations, _mapper, warnings = scan_java_files(files)
    assert warnings == []

    facts, _status = build_java_field_flow_facts(
        files,
        interfaces=interfaces,
        schemas=schemas,
        repository_id="topology-repo",
    )
    occurrences, _edges = _graph(facts)
    boundary_fields = [
        item for item in occurrences.values()
        if item.get("occurrence_kind") == "boundary_field"
    ]
    binding_kinds = {item.get("field_binding_kind") for item in boundary_fields}
    boundary_kinds = {item.get("boundary_kind") for item in boundary_fields}

    assert "grpc_request_deserialization_field" in binding_kinds
    assert "grpc_response_serialization_field" in binding_kinds
    assert "callback_request_deserialization_field" in binding_kinds
    assert "callback_response_serialization_field" in binding_kinds
    assert {"grpc", "callback"}.issubset(boundary_kinds)


def test_multi_step_invocation_receiver_chain_preserves_collection_getter(tmp_path: Path):
    path = _write(tmp_path, "ScopeMapper.java", """
        class ScopeMapper {
            Target map(Request request) {
                Set<String> scopes = request.getScopes().stream()
                    .map(scope -> "deliveryAddress".equals(scope) ? "shipping_addresses" : scope)
                    .collect(Collectors.toSet());
                String modifiedScopes = String.join(" ", scopes);
                return Target.builder().scope(modifiedScopes).build();
            }
        }
    """)

    facts, status = build_java_field_flow_facts([path], repository_id="scope-mapper")
    occurrences, edges = _graph(facts)
    receiver_edges = _edge_paths(occurrences, edges, "invocation_receiver")

    assert any(
        source == "request.scopes" and target.endswith("getScopes().stream()")
        for source, target, _edge in receiver_edges
    )
    assert any(
        source.endswith("getScopes().stream()") and ".map()" in target
        for source, target, _edge in receiver_edges
    )
    assert any(
        ".map()" in source and ".collect()" in target
        for source, target, _edge in receiver_edges
    )
    assert status["parser"] == "tree-sitter-java"


def test_inbound_collection_field_projects_only_to_exact_observed_downstream_consumer(tmp_path: Path):
    path = _write(tmp_path, "CollectionBoundary.java", """
        class Controller {
            Service service;
            void handle(Request request) {
                service.execute(request);
            }
        }
        class Service {
            Mapper mapper;
            Client client;
            void execute(Request request) {
                client.send(mapper.map(request));
            }
        }
        class Mapper {
            Target map(Request request) {
                Set<String> scopes = request.getScopes().stream()
                    .map(scope -> scope)
                    .collect(Collectors.toSet());
                return Target.builder().scope(String.join(" ", scopes)).build();
            }
        }
        class Client {
            void send(Target target) {}
        }
    """)
    interfaces = [
        InterfaceInfo(
            name="POST /scope request",
            direction=Direction.INBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Request",
            operation="Controller.handle",
            path="/scope",
            method="POST",
        ),
        InterfaceInfo(
            name="POST /target request",
            direction=Direction.OUTBOUND,
            kind=InterfaceKind.REST,
            schema_ref="Target",
            operation="Client.send",
            path="/target",
            method="POST",
            properties={"request_payload_type": "Target", "boundary_role": "http_outbound"},
        ),
    ]
    schemas = [
        SchemaInfo(
            name="Request",
            fields=[
                FieldInfo(name="scopes", type="Set<String>"),
                FieldInfo(name="unused", type="String"),
            ],
        ),
        SchemaInfo(name="Target", fields=[FieldInfo(name="scope", type="String")]),
    ]

    facts, _status = build_java_field_flow_facts(
        [path], interfaces=interfaces, schemas=schemas, repository_id="collection-boundary"
    )
    occurrences, edges = _graph(facts)
    adjacency = {}
    for edge in edges:
        adjacency.setdefault(edge["source_occurrence_id"], []).append(edge["target_occurrence_id"])

    source = next(
        oid for oid, item in occurrences.items()
        if item.get("field_path") == "boundary:rest:/scope:request.scopes"
    )
    target = next(
        oid for oid, item in occurrences.items()
        if item.get("field_path") == "boundary:rest:/target:request.scope"
    )
    queue = [source]
    seen = {source}
    while queue:
        current = queue.pop(0)
        for next_id in adjacency.get(current, []):
            if next_id not in seen:
                seen.add(next_id)
                queue.append(next_id)

    assert target in seen
    assert not any(
        item.get("operation") == "Mapper.map"
        and item.get("field_path") == "request.unused"
        for item in occurrences.values()
    )


def test_expression_memoization_reuses_repeated_ast_subexpressions(tmp_path: Path):
    path = _write(tmp_path, "MemoizedChains.java", """
        class MemoizedChains {
            void map(Request request, Target target) {
                String value = request.getProfile().getName().trim();
                target.setValue(value);
            }
        }
    """)

    workspace = parse_java_workspace([path])
    builder = FieldFlowBuilder(
        [JavaFileContext(parsed) for parsed in workspace.parsed_files],
        repository_id="repo-performance",
        repository_root=tmp_path,
    )
    index = builder.file_indexes[0]
    method = next(item for item in index.methods if item.name == "map")
    expression = next(
        node
        for node in iter_named(method.body, "method_invocation")
        if index.ctx.text(node).endswith(".trim()")
    )

    first = builder._expression(index, method, expression, role="variable_initializer")
    second = builder._expression(index, method, expression, role="variable_initializer")

    assert first == second
    assert builder._expression_cache_hits == 1
    assert builder._expression_cache_misses > 0
    assert builder._expression_cycle_preventions == 0
