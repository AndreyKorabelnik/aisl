from collections import Counter
from pathlib import Path

from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.scanners.java_syntax import parse_java_text
from code_analyzer_core.scanners.java_field_lineage import _return_expressions
from code_analyzer_core.scanners.java_persistence_lineage import (
    _collection_add_expressions,
    _collection_element_vars,
    _direct_assignment_bindings,
    _extract_getter_source_fields,
    _method_returns_storage_read,
)


def _method_info_from_code(code: str) -> dict:
    method = parse_java_text(code).methods[0]
    return {
        "method_calls": [c.__dict__ for c in method.calls],
        "syntax_assignments": [a.__dict__ for a in method.assignments],
        "returns": [r.__dict__ for r in method.returns],
        "object_creations": [c.__dict__ for c in method.object_creations],
        "lambdas": [l.__dict__ for l in method.lambdas],
        "method_references": [r.__dict__ for r in method.method_references],
        "field_accesses": [f.__dict__ for f in method.field_accesses],
    }


def test_request_propagation_uses_tree_sitter_calls_not_comment_or_string(tmp_path: Path) -> None:
    src = tmp_path / "DemoController.java"
    src.write_text(
        """
        @RestController
        class DemoController {
          @PostMapping("/demo")
          public DemoResponse create(@RequestBody DemoRequest request) {
            // fakeClient.forward(request);
            String fake = "stringClient.forward(request)";
            helper.forward(request);
            DemoResponse response = new DemoResponse(request.getId());
            return new DemoEnvelope(response).unwrap();
          }
        }
        class DemoRequest { String id; }
        class DemoResponse { DemoResponse(String id) {} }
        class DemoEnvelope { DemoEnvelope(DemoResponse response) {} DemoResponse unwrap() { return null; } }
        """,
        encoding="utf-8",
    )

    _facts, _schemas, interfaces, _relations, _mapper_facts, warnings = scan_java_files([src])

    assert warnings == []
    propagation = []
    for iface in interfaces:
        propagation.extend((iface.properties or {}).get("request_field_propagation") or [])
    joined = "\n".join(propagation)
    assert "helper.forward(request)" in joined
    assert "new DemoEnvelope(response)" in joined
    assert "fakeClient.forward" not in joined
    assert "stringClient.forward" not in joined


def test_return_expressions_are_extracted_from_tree_sitter_and_unwrap_response_entity() -> None:
    returns = _return_expressions(
        """
        {
          String fake = "return notAStatement;";
          return ResponseEntity.ok(response);
        }
        """
    )

    assert returns == ["response"]


def test_storage_read_return_detection_uses_tree_sitter_return_and_assignment_spans() -> None:
    access = {"receiver_expression": "bookingRepository", "storage_method": "findById"}
    direct_mi = {
        "returns": [{"expression": "bookingRepository.findById(id)", "start_byte": 100, "end_byte": 130}],
        "syntax_assignments": [],
        "method_calls": [{"receiver": "bookingRepository", "method": "findById", "start_byte": 107, "end_byte": 129}],
    }
    ok, reasons = _method_returns_storage_read(access, direct_mi)
    assert ok
    assert "direct_return_of_storage_read_call" in reasons

    assigned_mi = {
        "returns": [{"expression": "booking", "start_byte": 210, "end_byte": 225}],
        "syntax_assignments": [
            {"target": "booking", "expression": "bookingRepository.findById(id)", "start_byte": 50, "end_byte": 95}
        ],
        "method_calls": [{"receiver": "bookingRepository", "method": "findById", "start_byte": 68, "end_byte": 94}],
    }
    ok, reasons = _method_returns_storage_read(access, assigned_mi)
    assert ok
    assert "return_of_storage_read_variable:booking" in reasons


def test_collection_add_and_addall_use_tree_sitter_calls_not_comment_or_string() -> None:
    code = """
    class Demo {
      void m() {
        java.util.List<Record> toAdd = new java.util.ArrayList<>();
        // toAdd.add(fakeComment);
        String fake = "toAdd.add(fakeString)";
        toAdd.add(entity);
        Collections.addAll(toAdd, first, second);
      }
    }
    """
    mi = _method_info_from_code(code)

    assert _collection_add_expressions("", "toAdd", method_info=mi) == ["entity", "first", "second"]
    assert _collection_element_vars("", "toAdd", method_info=mi) == ["entity", "first", "second"]


def test_collection_stream_return_vars_use_tree_sitter_lambda_body() -> None:
    code = """
    class Demo {
      void m(java.util.List<Request> requests) {
        java.util.List<Record> toAdd = requests.stream()
          .map(rq -> { Record rec = toRecord(rq); return rec; })
          .collect(Collectors.toList());
      }
      Record toRecord(Request rq) { return new Record(); }
    }
    """
    mi = _method_info_from_code(code)

    assert _collection_element_vars("", "toAdd", method_info=mi) == ["rec"]

from code_analyzer_core.scanners.java_persistence_lineage import (
    _constructor_mappings_for_method,
    _emit_mapper_save_lineage_facts,
    _mapper_method_signatures,
    _mapstruct_annotation_facts,
)


def test_mapper_signatures_and_mapstruct_annotations_use_tree_sitter_not_comments(tmp_path: Path) -> None:
    src = tmp_path / "BookingMapper.java"
    src.write_text(
        '''
        import org.mapstruct.Mapper;
        import org.mapstruct.Mapping;
        @Mapper
        interface BookingMapper {
          // @Mapping(source="commentField", target="commentId")
          String fake = "@Mapping(source=\\\"stringField\\\", target=\\\"stringId\\\")";
          @Mapping(source="bookingId", target="id")
          BookingEntity toEntity(BookingRequest request);
        }
        class BookingRequest {}
        class BookingEntity {}
        ''',
        encoding="utf-8",
    )

    signatures = _mapper_method_signatures([src])
    assert signatures["toEntity"][0]["source_container"] == "BookingRequest"
    assert signatures["toEntity"][0]["target_container"] == "BookingEntity"
    assert signatures["toEntity"][0]["syntax_provider"] == "tree_sitter"

    facts, _seq = _mapstruct_annotation_facts([src], ctx={"project_code": "P", "system_name": "S", "repo_id": "R"})
    pairs = {(f.properties["source_field"], f.properties["target_field"]) for f in facts}
    assert pairs == {("bookingId", "id")}


def test_mapper_save_lineage_uses_tree_sitter_calls_and_method_references() -> None:
    code = '''
    class DemoService {
      BookingMapper mapper;
      BookingRepository repo;
      void create(BookingRequest request, java.util.List<BookingRequest> requests) {
        // repo.save(mapper.toEntity(fake));
        String fake = "repo.save(mapper.toEntity(fake))";
        BookingEntity entity = mapper.toEntity(request);
        repo.save(entity);
        repo.save(mapper.toEntity(request));
        java.util.List<BookingEntity> entities = requests.stream()
          .map(mapper::toEntity)
          .collect(Collectors.toList());
        repo.saveAll(entities);
      }
    }
    '''
    method = parse_java_text(code).methods[0]
    mi = {
        "operation": "DemoService.create",
        "file": "DemoService.java",
        "line_start": 1,
        "method_calls": [c.__dict__ for c in method.calls],
        "syntax_assignments": [a.__dict__ for a in method.assignments],
        "method_references": [r.__dict__ for r in method.method_references],
        "var_types": {"request": "BookingRequest", "requests": "List<BookingRequest>"},
    }
    facts, lineage_seq, gap_seq = _emit_mapper_save_lineage_facts(
        ctx={},
        methods={"DemoService.create": mi},
        mapper_signatures={"toEntity": [{"source_container": "BookingRequest", "target_container": "BookingEntity"}]},
        container_by_name={"BookingEntity": {"storage_target": "reservation.booking"}},
        start_lineage_seq=0,
        start_gap_seq=0,
    )

    lineage = [f for f in facts if f.fact_type == "source_to_storage_lineage"]
    assert lineage_seq == 3
    assert gap_seq == 3
    assert len(lineage) == 3
    expressions = [f.properties["assignment_expression"] for f in lineage]
    assert expressions.count("mapper.toEntity(request)") == 2
    assert "mapper::toEntity" in expressions
    assert all(f.properties["storage_target"] == "reservation.booking" for f in lineage)
    assert "fake" not in "\n".join(expressions)


def test_constructor_mappings_use_tree_sitter_object_creations_not_comments_or_strings() -> None:
    code = '''
    class DemoService {
      BookingEntity create(BookingRequest request) {
        // new BookingEntity(fake.getId(), fake.getStatus());
        String fake = "new BookingEntity(fake.getId(), fake.getStatus())";
        return new BookingEntity(request.getId(), request.getStatus());
      }
    }
    '''
    method = parse_java_text(code).methods[0]
    mi = {
        "operation": "DemoService.create",
        "file": "DemoService.java",
        "line_start": 1,
        "params": [{"name": "request", "type": "BookingRequest"}],
        "var_types": {"request": "BookingRequest"},
        "method_calls": [c.__dict__ for c in method.calls],
        "field_accesses": [f.__dict__ for f in method.field_accesses],
        "object_creations": [c.__dict__ for c in method.object_creations],
    }
    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(
        mi,
        {"BookingEntity": {"fields": [{"name": "id"}, {"name": "status"}]}},
        {"project_code": "P", "system_name": "S", "repo_id": "R"},
        0,
        0,
        0,
    )

    mappings = [f for f in facts if f.fact_type == "attribute_mapping"]
    assert map_seq == 2
    assert der_seq == 0
    assert gap_seq == 0
    assert {(f.properties["source_field"], f.properties["target_field"]) for f in mappings} == {("id", "id"), ("status", "status")}

from code_analyzer_core.scanners.java_output_provenance import (
    _constructor_arg_bindings,
    _getter_receiver_field,
    _variable_origins,
)


def _full_method_info_from_code(code: str) -> dict:
    method = parse_java_text(code).methods[0]
    return {
        "body": method.body,
        "params": [{"name": p.name, "type": p.type} for p in method.params],
        "method_calls": [c.__dict__ for c in method.calls],
        "syntax_assignments": [a.__dict__ for a in method.assignments],
        "returns": [r.__dict__ for r in method.returns],
        "object_creations": [c.__dict__ for c in method.object_creations],
        "lambdas": [l.__dict__ for l in method.lambdas],
        "method_references": [r.__dict__ for r in method.method_references],
        "enhanced_for": [f.__dict__ for f in method.enhanced_for],
        "field_accesses": [f.__dict__ for f in method.field_accesses],
    }


def test_output_variable_origins_use_tree_sitter_loops_and_lambdas_not_comments() -> None:
    code = '''
    class Demo {
      void m(java.util.List<Request> requests) {
        // for (Request fake : requests) {}
        String fake = "requests.forEach(fake -> out.add(fake))";
        for (Request rq : requests) { out.add(rq.getId()); }
        requests.stream().map(item -> item.getId()).collect(Collectors.toList());
      }
    }
    '''
    mi = _full_method_info_from_code(code)
    origins = _variable_origins(mi["body"], mi["params"], mi)

    assert origins["rq"]["immediate_origin_kind"] == "collection_element"
    assert origins["rq"]["origin_container"] == "requests"
    assert origins["item"]["immediate_origin_kind"] == "collection_element"
    assert origins["item"]["origin_container"] == "requests"
    assert "fake" in origins  # real local var assignment
    assert origins["fake"]["immediate_origin_kind"] != "collection_element"


def test_output_constructor_arg_bindings_use_tree_sitter_object_creations_not_comments() -> None:
    code = '''
    class Demo {
      Response m(Request request) {
        // return new Response(fake.getId());
        String fake = "new Response(fake.getId())";
        return new Response(request.getId(), request.status);
      }
    }
    '''
    mi = _full_method_info_from_code(code)
    bindings = _constructor_arg_bindings("new Response(request.getId(), request.status)", method_info=mi)

    assert [(b["target_type"], b["target_index"], b["source_expression"]) for b in bindings] == [
        ("Response", 0, "request.getId()"),
        ("Response", 1, "request.status"),
    ]
    assert "fake" not in "\n".join(str(b) for b in bindings)


def test_output_getter_receiver_field_uses_tree_sitter_getter_and_field_access() -> None:
    code = '''
    class Demo {
      void m(Request request) {
        String a = request.getId();
        String b = request.status;
        String fake = "request.getFake()";
      }
    }
    '''
    mi = _full_method_info_from_code(code)

    assert _getter_receiver_field("request.getId()", mi) == ("request", "id")
    assert _getter_receiver_field("request.status", mi) == ("request", "status")
    assert _getter_receiver_field("request.getFake()", mi) == ("request", "fake")  # synthetic expression, not method body text

from code_analyzer_core.scanners.java_field_lineage import (
    _setter_bindings as _field_setter_bindings,
    _builder_bindings as _field_builder_bindings,
)
from code_analyzer_core.scanners.java_output_provenance import (
    _setter_bindings_any_source,
    _builder_bindings_any_source,
)


def test_setter_builder_mappings_use_tree_sitter_not_comments_or_strings(tmp_path: Path) -> None:
    src = tmp_path / "DemoMapper.java"
    src.write_text(
        '''
        class DemoMapper {
          Response map(Request request) {
            // target.setFake(request.getFake());
            String fake = "Response.builder().fake(request.getFake()).build()";
            Response target = new Response();
            target.setId(request.getId());
            target.setActive(request.isActive());
            Response built = Response.builder()
              .status(request.status)
              .code(request.getCode())
              .build();
            return target;
          }
        }
        class Request { String status; String getId(){return null;} boolean isActive(){return false;} String getCode(){return null;} }
        class Response { void setId(String v){} void setActive(boolean v){} static Builder builder(){return null;} }
        class Builder { Builder status(String v){return this;} Builder code(String v){return this;} Response build(){return null;} }
        ''',
        encoding="utf-8",
    )
    _facts, _schemas, _interfaces, _relations, mapper_facts, warnings = scan_java_files([src])

    assert warnings == []
    names = "\n".join(f.name for f in mapper_facts)
    assert "request.getId -> target.setId" in names
    assert "request.getActive -> target.setActive" in names
    assert "request.getCode -> builder.code" in names
    assert "builder.status" in names
    assert "Fake" not in names


def test_field_lineage_setter_builder_helpers_use_tree_sitter_nodes() -> None:
    code = '''
    class Demo {
      Response m(Request request) {
        // target.setFake(request.getFake());
        String fake = "Response.builder().fake(request.getFake()).build()";
        Response target = new Response();
        target.setId(request.getId());
        Response built = Response.builder().status(request.status).code(request.getCode()).build();
        return built;
      }
    }
    '''
    mi = _full_method_info_from_code(code)

    setter = _field_setter_bindings(mi["body"], source_param="request", method_info=mi)
    builder = _field_builder_bindings(mi["body"], source_param="request", method_info=mi)

    assert {(b["target_variable"], b["target_field"], b["source_field"]) for b in setter} == {("target", "id", "id")}
    assert {(b["target_field"], b["source_field"]) for b in builder} == {("status", "status"), ("code", "code")}
    assert "fake" not in "\n".join(str(b) for b in setter + builder).lower()


def test_output_provenance_setter_builder_any_source_preserves_complex_expressions() -> None:
    code = '''
    class Demo {
      Response m(Request request) {
        Response target = new Response();
        target.setAgeGroup(calcAgeGroup(request.getBirthDate()));
        Response built = Response.builder().displayName(format(request.getFirstName(), request.getLastName())).build();
        return built;
      }
    }
    '''
    mi = _full_method_info_from_code(code)

    setter = _setter_bindings_any_source(mi["body"], mi)
    builder = _builder_bindings_any_source(mi["body"], mi)

    assert {b["target_field"]: b["source_expression"] for b in setter}["ageGroup"] == "calcAgeGroup(request.getBirthDate())"
    assert {b["target_field"]: b["source_expression"] for b in builder}["displayName"] == "format(request.getFirstName(), request.getLastName())"


def test_direct_assignment_and_getter_source_fields_use_tree_sitter_not_comments_or_strings() -> None:
    code = '''
    class Demo {
      void m(Request request, Response target) {
        // target.fake = request.getFake();
        String fake = "target.stringField = request.getStringField()";
        target.id = request.getId();
        target.status = request.status;
        target.displayName = format(request.getFirstName(), request.lastName);
      }
    }
    '''
    mi = _full_method_info_from_code(code)
    mi["var_types"] = {"request": "Request", "target": "Response"}

    bindings = _direct_assignment_bindings(mi)
    assert {(b["target_variable"], b["target_field"], b["source_expression"]) for b in bindings} == {
        ("target", "id", "request.getId()"),
        ("target", "status", "request.status"),
        ("target", "displayName", "format(request.getFirstName(), request.lastName)"),
    }
    assert "fake" not in "\n".join(str(b).lower() for b in bindings)
    assert "stringfield" not in "\n".join(str(b).lower() for b in bindings)

    fields = _extract_getter_source_fields("format(request.getFirstName(), request.lastName)", mi)
    assert {(f["container"], f["field"], f["variable"]) for f in fields} == {
        ("Request", "firstName", "request"),
        ("Request", "lastName", "request"),
    }


def test_direct_assignment_bindings_ignore_non_field_assignments() -> None:
    code = '''
    class Demo {
      void m(Request request, Response target) {
        target = new Response();
        target.items[0] = request.getId();
        this.target.id = request.getId();
      }
    }
    '''
    mi = _full_method_info_from_code(code)
    bindings = _direct_assignment_bindings(mi)

    assert [(b["target_variable"], b["target_field"], b["source_expression"]) for b in bindings] == [
        ("this.target", "id", "request.getId()")
    ]

from code_analyzer_core.scanners.java_field_lineage import _extract_all_schema_fields
from code_analyzer_core.scanners.java_persistence_lineage import (
    _extract_java_attribute_containers,
    _repository_entity_types,
)


def test_jpa_annotation_metadata_uses_tree_sitter_annotations_not_comments_or_strings(tmp_path: Path) -> None:
    src = tmp_path / "JpaDemo.java"
    src.write_text(
        '''
        import jakarta.persistence.*;
        // @Table(name = "comment_table")
        @Entity
        @Table(name = "real_table")
        class RealEntity {
          String fake = "@Column(name=\"string_col\", nullable=false)";
          @Id @Column(name = "real_id", nullable = false, unique = true)
          private String id;
          @JoinColumn(name = "client_id", referencedColumnName = "id")
          @ManyToOne
          private ClientEntity client;
        }
        interface RealRepository extends org.springframework.data.jpa.repository.JpaRepository<RealEntity, String> {}
        class ClientEntity { private String id; }
        ''',
        encoding="utf-8",
    )

    containers = _extract_java_attribute_containers([src])
    real = next(c for c in containers if c["container_name"] == "RealEntity")
    assert real["storage_target"] == "real_table"
    assert real["container_kind"] == "entity"
    fields = {f["name"]: f for f in real["fields"]}
    assert fields["id"]["storage_field"] == "real_id"
    assert fields["id"]["nullable"] is False
    assert fields["id"]["unique"] is True
    assert fields["client"]["key_role"] == "foreign_key"
    assert fields["client"]["referenced_column"] == "id"
    assert "string_col" not in {f["storage_field"] for f in real["fields"]}
    assert _repository_entity_types([src]) == {"RealEntity": ["RealRepository"]}


def test_getter_setter_schema_hints_use_tree_sitter_methods_not_comments_or_strings(tmp_path: Path) -> None:
    src = tmp_path / "GeneratedDto.java"
    src.write_text(
        '''
        class GeneratedDto {
          // public void setCommentField(String value) {}
          String fake = "public String getStringField() { return null; }";
          public void setStatusCode(String statusCode) {}
          public String getDisplayName() { return null; }
          public boolean isActive() { return false; }
        }
        ''',
        encoding="utf-8",
    )

    fields = _extract_all_schema_fields([src])["GeneratedDto"]
    by_name = {f["name"]: f for f in fields}
    assert by_name["statusCode"]["schema_hint"] == "setter_method"
    assert by_name["displayName"]["schema_hint"] == "getter_method"
    assert by_name["active"]["schema_hint"] == "getter_method"
    assert "commentField" not in by_name
    assert "stringField" not in by_name



def _constructor_method_info(
    code: str,
    *,
    file: str,
    class_fqcn: str,
    imports: list[str] | None = None,
    class_field_types: dict[str, str] | None = None,
    class_field_declarations: dict[str, dict] | None = None,
) -> dict:
    method = parse_java_text(code).methods[0]
    return {
        "operation": f"{class_fqcn.rsplit('.', 1)[-1]}.{method.name}",
        "class_name": class_fqcn.rsplit('.', 1)[-1],
        "class_fqcn": class_fqcn,
        "file": file,
        "line_start": 1,
        "body": method.body,
        "params": [{"name": p.name, "type": p.type} for p in method.params],
        "var_types": {p.name: p.type for p in method.params},
        "raw_var_types": {p.name: p.type for p in method.params},
        "class_field_types": class_field_types or {},
        "class_field_declarations": class_field_declarations or {},
        "method_calls": [c.__dict__ for c in method.calls],
        "field_accesses": [f.__dict__ for f in method.field_accesses],
        "object_creations": [c.__dict__ for c in method.object_creations],
        "syntax_assignments": [a.__dict__ for a in method.assignments],
        "lambdas": [item.__dict__ for item in method.lambdas],
        "enhanced_for": [item.__dict__ for item in method.enhanced_for],
        "imports": imports or [],
    }


def test_constructor_target_resolution_uses_explicit_import_when_simple_names_collide() -> None:
    mi = _constructor_method_info(
        """
        class CardService {
          Card create(CardRequest request) {
            return new Card(request.getNumber());
          }
        }
        """,
        file="/repo/src/main/java/com/example/service/CardService.java",
        class_fqcn="com.example.service.CardService",
        imports=["com.example.domain.Card"],
    )
    containers = [
        {"container_name": "Card", "fqcn": "com.example.domain.Card", "fields": [{"name": "number"}]},
        {"container_name": "Card", "fqcn": "com.example.db.generated.Card", "fields": [{"name": "CARDID"}]},
    ]
    diagnostics = Counter()

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(
        mi, containers, {}, 0, 0, 0, diagnostics=diagnostics,
    )

    mappings = [fact for fact in facts if fact.fact_type == "attribute_mapping"]
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert [(fact.properties["source_field"], fact.properties["target_field"]) for fact in mappings] == [("number", "number")]
    assert diagnostics["target_resolution_explicit_import"] == 1


def test_constructor_target_collision_emits_one_ambiguity_gap_not_foreign_fields() -> None:
    mi = _constructor_method_info(
        """
        class CardService {
          Card create(CardRequest request) {
            return new Card(request.getNumber());
          }
        }
        """,
        file="/repo/src/main/java/com/example/service/CardService.java",
        class_fqcn="com.example.service.CardService",
    )
    containers = [
        {"container_name": "Card", "fqcn": "com.example.domain.Card", "fields": [{"name": "number"}]},
        {"container_name": "Card", "fqcn": "com.example.db.generated.Card", "fields": [{"name": "CARDID"}]},
    ]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    gaps = [fact for fact in facts if fact.fact_type == "data_model_lineage_gap"]
    assert map_seq == 0
    assert der_seq == 0
    assert gap_seq == 1
    assert len(gaps) == 1
    assert gaps[0].properties["gap_kind"] == "constructor_target_type_ambiguous"
    assert gaps[0].properties["field"] is None
    assert gaps[0].properties["candidate_target_fqcns"] == [
        "com.example.db.generated.Card",
        "com.example.domain.Card",
    ]
    assert "CARDID" not in str(gaps[0].properties)


def test_non_production_constructor_unresolved_is_suppressed_but_confirmed_mapping_remains() -> None:
    test_mi = _constructor_method_info(
        """
        class ResponseTest {
          Response create(Request request) {
            Response mapped = new Response(request.getStatus());
            return new Response(null);
          }
        }
        """,
        file="/repo/src/test/java/com/example/ResponseTest.java",
        class_fqcn="com.example.ResponseTest",
    )
    generated_mi = _constructor_method_info(
        """
        class GeneratedFactory {
          Response create() { return new Response(null); }
        }
        """,
        file="/repo/build/generated/sources/com/example/GeneratedFactory.java",
        class_fqcn="com.example.GeneratedFactory",
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "status"}]}]
    diagnostics = Counter()

    test_facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(
        test_mi, containers, {}, 0, 0, 0, diagnostics=diagnostics,
    )
    generated_facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(
        generated_mi, containers, {}, map_seq, der_seq, gap_seq, diagnostics=diagnostics,
    )

    assert any(fact.fact_type == "attribute_mapping" for fact in test_facts)
    assert not any(fact.fact_type == "data_model_lineage_gap" for fact in test_facts + generated_facts)
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert diagnostics["suppressed_test_code_observed_origins"] == 1
    assert diagnostics["suppressed_generated_code_observed_origins"] == 1


def test_data_model_gap_compact_item_keeps_constructor_resolution_metadata() -> None:
    from code_analyzer_core.models import EvidenceRef, Fact
    from code_analyzer_core.navigation import _data_model_lineage_gap_brief_from_fact

    fact = Fact(
        fact_type="data_model_lineage_gap",
        name="constructor gap",
        properties={
            "data_model_lineage_gap_id": "gap-1",
            "gap_kind": "constructor_mapping_not_resolved",
            "container": "Card",
            "field": "number",
            "source_scope": "production_code",
            "target_container_fqcn": "com.example.domain.Card",
            "target_type_reference": "Card",
            "target_resolution_kind": "explicit_import",
            "candidate_target_fqcns": ["com.example.domain.Card"],
            "constructor_argument_index": 0,
            "constructor_argument_expression_kind": "constant_or_default",
        },
        evidence=[EvidenceRef(file_path="/repo/src/main/java/CardService.java", line_start=10)],
    )

    item = _data_model_lineage_gap_brief_from_fact(fact)
    assert item["source_scope"] == "production_code"
    assert item["target_container_fqcn"] == "com.example.domain.Card"
    assert item["target_resolution_kind"] == "explicit_import"
    assert item["constructor_argument_index"] == 0
    assert item["constructor_argument_expression_kind"] == "constant_or_default"


def test_constructor_local_alias_recovers_getter_source_field() -> None:
    mi = _constructor_method_info(
        """
        class BookingService {
          Booking create(BookingRequest request) {
            String id = request.getId();
            return new Booking(id);
          }
        }
        """,
        file="/repo/src/main/java/com/example/BookingService.java",
        class_fqcn="com.example.BookingService",
    )
    mi["var_types"]["id"] = "String"
    mi["raw_var_types"]["id"] = "String"
    containers = [{"container_name": "Booking", "fqcn": "com.example.Booking", "fields": [{"name": "id"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mappings = [fact for fact in facts if fact.fact_type == "attribute_mapping"]
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mappings[0].properties["source_field"] == "id"
    assert mappings[0].properties["target_field"] == "id"
    assert mappings[0].properties["constructor_source_resolution_kind"] == "local_alias"
    assert mappings[0].properties["constructor_alias_expression"] == "request.getId()"


def test_constructor_direct_parameter_pass_through_is_mapping() -> None:
    mi = _constructor_method_info(
        """
        class BookingService {
          Booking create(String id) { return new Booking(id); }
        }
        """,
        file="/repo/src/main/java/com/example/BookingService.java",
        class_fqcn="com.example.BookingService",
    )
    containers = [{"container_name": "Booking", "fqcn": "com.example.Booking", "fields": [{"name": "id"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mappings = [fact for fact in facts if fact.fact_type == "attribute_mapping"]
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mappings[0].properties["source_container"] == "String"
    assert mappings[0].properties["source_field"] == "id"
    assert mappings[0].properties["constructor_source_resolution_kind"] == "method_parameter"


def test_constructor_implicit_class_field_pass_through_is_mapping() -> None:
    mi = _constructor_method_info(
        """
        class CopySource {
          int maxSize;
          CopyTarget copy() { return new CopyTarget(maxSize); }
        }
        """,
        file="/repo/src/main/java/com/example/CopySource.java",
        class_fqcn="com.example.CopySource",
        class_field_types={"maxSize": "int"},
    )
    containers = [{"container_name": "CopyTarget", "fqcn": "com.example.CopyTarget", "fields": [{"name": "maxSize"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mappings = [fact for fact in facts if fact.fact_type == "attribute_mapping"]
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mappings[0].properties["source_container"] == "CopySource"
    assert mappings[0].properties["source_field"] == "maxSize"
    assert mappings[0].properties["constructor_source_resolution_kind"] == "class_field"


def test_constructor_literals_and_named_constants_are_observed_derivations_not_gaps() -> None:
    mi = _constructor_method_info(
        """
        class ResponseFactory {
          Response create() { return new Response(null, SUCCESS); }
        }
        """,
        file="/repo/src/main/java/com/example/ResponseFactory.java",
        class_fqcn="com.example.ResponseFactory",
        class_field_types={"SUCCESS": "String"},
    )
    containers = [{
        "container_name": "Response",
        "fqcn": "com.example.Response",
        "fields": [{"name": "description"}, {"name": "status"}],
    }]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivations = [fact for fact in facts if fact.fact_type == "attribute_derivation"]
    assert map_seq == 0
    assert der_seq == 2
    assert gap_seq == 0
    assert {fact.properties["target_field"] for fact in derivations} == {"description", "status"}
    assert all(fact.properties["derivation_kind"] == "constructor_constant_or_default" for fact in derivations)
    assert {fact.properties["constructor_source_resolution_kind"] for fact in derivations} == {
        "constant_or_default",
        "named_constant",
    }


def test_constructor_nested_object_creation_records_parameter_inputs() -> None:
    mi = _constructor_method_info(
        """
        class ClientFactory {
          Service create(RestProperties rest, SslProperties ssl) {
            return new Service(new RestClient(rest, ssl));
          }
        }
        """,
        file="/repo/src/main/java/com/example/ClientFactory.java",
        class_fqcn="com.example.ClientFactory",
    )
    containers = [
        {"container_name": "Service", "fqcn": "com.example.Service", "fields": [{"name": "client"}]},
        {"container_name": "RestClient", "fqcn": "com.example.RestClient", "fields": [{"name": "rest"}, {"name": "ssl"}]},
    ]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    service_derivation = next(
        fact for fact in facts
        if fact.fact_type == "attribute_derivation" and fact.properties.get("target_container") == "Service"
    )
    assert gap_seq == 0
    assert service_derivation.properties["constructor_source_resolution_kind"] == "object_creation_with_inputs"
    assert {item["field"] for item in service_derivation.properties["source_fields"]} == {"rest", "ssl"}


def test_remaining_constructor_gap_keeps_raw_expression_and_resolution_attempt() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          Response create(Dao dao) { return new Response(dao.load()); }
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "payload"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    gap = next(fact for fact in facts if fact.fact_type == "data_model_lineage_gap")
    assert map_seq == 0
    assert der_seq == 0
    assert gap_seq == 1
    assert gap.properties["constructor_argument_expression"] == "dao.load()"
    assert gap.properties["constructor_source_resolution_kind"] == "unresolved"



def test_constructor_local_value_pass_through_keeps_helper_return_uninterpreted() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          Response create(Dao dao) {
            Payload payload = dao.load();
            return new Response(payload);
          }
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "body"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["source_fields"][0]["field"] == "payload"
    assert derivation.properties["source_fields"][0]["source_kind"] == "local_variable"
    assert derivation.properties["constructor_source_resolution_kind"] == "local_variable"
    assert derivation.properties["source_fields"][0]["declaration_expression"] == "dao.load()"


def test_constructor_lambda_parameter_is_resolved_only_inside_containing_lambda() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          void map(java.util.List<String> cards) {
            cards.forEach(card -> consume(new Profile(card)));
          }
          void consume(Profile profile) {}
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    containers = [{"container_name": "Profile", "fqcn": "com.example.Profile", "fields": [{"name": "cardNumber"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["source_fields"][0]["source_kind"] == "lambda_parameter"
    assert derivation.properties["source_fields"][0]["field"] == "card"
    assert derivation.properties["constructor_source_resolution_kind"] == "lambda_parameter"


def test_constructor_jooq_get_value_uses_observed_field_initializer() -> None:
    mi = _constructor_method_info(
        """
        class Dao {
          Result map(Record record) {
            return new Result(record.getValue(PHONE_ID_FIELD));
          }
        }
        """,
        file="/repo/src/main/java/com/example/Dao.java",
        class_fqcn="com.example.Dao",
        class_field_types={"PHONE_ID_FIELD": "Field<Long>"},
        class_field_declarations={
            "PHONE_ID_FIELD": {
                "initializer": 'DSL.field("phoneId", Long.class)',
                "type": "Field<Long>",
            }
        },
    )
    containers = [{"container_name": "Result", "fqcn": "com.example.Result", "fields": [{"name": "phoneId"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mapping = next(fact for fact in facts if fact.fact_type == "attribute_mapping")
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mapping.properties["source_container"] == "Record"
    assert mapping.properties["source_field"] == "phoneId"
    assert mapping.properties["constructor_source_resolution_kind"] == "jooq_record_get_value"
    assert mapping.properties["constructor_source_kind"] == "jooq_record_field"
    assert mapping.properties["constructor_source_field_reference"] == "PHONE_ID_FIELD"
    assert mapping.properties["constructor_source_field_initializer"] == 'DSL.field("phoneId", Long.class)'


def test_constructor_imported_collections_empty_map_is_observed_default() -> None:
    mi = _constructor_method_info(
        """
        class Controller {
          Response empty() { return new Response(emptyMap()); }
        }
        """,
        file="/repo/src/main/java/com/example/Controller.java",
        class_fqcn="com.example.Controller",
        imports=["java.util.Collections.emptyMap"],
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "items"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["constructor_source_resolution_kind"] == "java_empty_collection_factory"
    assert derivation.properties["derivation_kind"] == "constructor_constant_or_default"


def test_constructor_same_class_copy_expression_uses_class_fields_only_for_same_target() -> None:
    mi = _constructor_method_info(
        """
        class Copy {
          Copy copy() { return new Copy(mergeNotNull(phones, new ArrayList<>())); }
        }
        """,
        file="/repo/src/main/java/com/example/Copy.java",
        class_fqcn="com.example.Copy",
        class_field_types={"phones": "List<Phone>"},
    )
    containers = [{"container_name": "Copy", "fqcn": "com.example.Copy", "fields": [{"name": "phones"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["source_fields"][0]["source_kind"] == "class_field"
    assert derivation.properties["source_fields"][0]["field"] == "phones"
    assert derivation.properties["constructor_source_resolution_kind"] == "same_class_expression_inputs"


def test_constructor_optional_or_else_is_observed_unwrap_not_helper_guess() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          Response create(Optional<Device> lastDevice) {
            return new Response(lastDevice.orElse(null));
          }
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    mi["raw_var_types"]["lastDevice"] = "Optional<Device>"
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "device"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["source_fields"][0]["source_kind"] == "optional_value"
    assert derivation.properties["source_fields"][0]["container"] == "Device"
    assert derivation.properties["constructor_source_resolution_kind"] == "optional_value_unwrap"


def test_constructor_direct_dao_return_remains_gap_after_lexical_resolution() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          Response create(Dao dao, Set<String> ids) {
            return new Response(dao.load(ids));
          }
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "payload"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    gap = next(fact for fact in facts if fact.fact_type == "data_model_lineage_gap")
    assert map_seq == 0
    assert der_seq == 0
    assert gap_seq == 1
    assert gap.properties["constructor_argument_expression"] == "dao.load(ids)"
    assert gap.properties["constructor_source_resolution_kind"] == "unresolved"


def test_constructor_declared_then_branch_assigned_local_is_observed_value() -> None:
    mi = _constructor_method_info(
        """
        class Service {
          Response create(Dao dao, boolean archive) {
            List<Item> items;
            if (archive) {
              items = dao.loadArchive();
            } else {
              items = dao.loadCurrent();
            }
            return new Response(items);
          }
        }
        """,
        file="/repo/src/main/java/com/example/Service.java",
        class_fqcn="com.example.Service",
    )
    containers = [{"container_name": "Response", "fqcn": "com.example.Response", "fields": [{"name": "items"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mapping = next(fact for fact in facts if fact.fact_type == "attribute_mapping")
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mapping.properties["source_container"] == "List"
    assert mapping.properties["source_field"] == "items"
    assert mapping.properties["constructor_source_resolution_kind"] == "local_variable"
    assert mapping.properties["constructor_source_kind"] == "local_variable"



def test_constructor_generic_collections_empty_list_is_observed_default() -> None:
    mi = _constructor_method_info(
        """
        class Factory {
          Result create() { return new Result(Collections.<Error>emptyList()); }
        }
        """,
        file="/repo/src/main/java/com/example/Factory.java",
        class_fqcn="com.example.Factory",
        imports=["java.util.Collections"],
    )
    containers = [{"container_name": "Result", "fqcn": "com.example.Result", "fields": [{"name": "errors"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["constructor_source_resolution_kind"] == "java_empty_collection_factory"
    assert derivation.properties["constructor_factory_api"] == "java.util.Collections.emptyList"


def test_constructor_java_class_literal_is_observed_constant() -> None:
    mi = _constructor_method_info(
        """
        class Factory {
          Provider create() { return new Provider(VersionInfo.class); }
        }
        """,
        file="/repo/src/main/java/com/example/Factory.java",
        class_fqcn="com.example.Factory",
    )
    containers = [{"container_name": "Provider", "fqcn": "com.example.Provider", "fields": [{"name": "entryClass"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    derivation = next(fact for fact in facts if fact.fact_type == "attribute_derivation")
    assert map_seq == 0
    assert der_seq == 1
    assert gap_seq == 0
    assert derivation.properties["constructor_source_resolution_kind"] == "java_class_literal"
    assert derivation.properties["constructor_class_literal_type"] == "VersionInfo"


def test_constructor_enhanced_for_variable_uses_exact_loop_span() -> None:
    mi = _constructor_method_info(
        """
        class Factory {
          void create(Project project) {
            for (Artifact artifact : project.getArtifacts()) {
              consume(new Filter(artifact));
            }
          }
          void consume(Filter filter) {}
        }
        """,
        file="/repo/src/main/java/com/example/Factory.java",
        class_fqcn="com.example.Factory",
    )
    containers = [{"container_name": "Filter", "fqcn": "com.example.Filter", "fields": [{"name": "artifact"}]}]

    facts, map_seq, der_seq, gap_seq = _constructor_mappings_for_method(mi, containers, {}, 0, 0, 0)

    mapping = next(fact for fact in facts if fact.fact_type == "attribute_mapping")
    assert map_seq == 1
    assert der_seq == 0
    assert gap_seq == 0
    assert mapping.properties["source_container"] == "Artifact"
    assert mapping.properties["source_field"] == "artifact"
    assert mapping.properties["constructor_source_resolution_kind"] == "enhanced_for_variable"
    assert mapping.properties["constructor_source_kind"] == "enhanced_for_variable"
    assert mapping.properties["constructor_enhanced_for_iterable"] == "project.getArtifacts()"
