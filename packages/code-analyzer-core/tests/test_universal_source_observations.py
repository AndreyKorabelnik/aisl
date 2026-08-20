from pathlib import Path

from code_analyzer_core.scanners import java_source_observations as obs
from code_analyzer_core.scanners.config_scanner import scan_config_files
from code_analyzer_core.scanners.java_interaction_enrichment import scan_maven_dependencies
from code_analyzer_core.scanners.java_persistence_lineage import _normalized_model_annotation_contracts
from code_analyzer_core.scanners.java_syntax import (
    JavaAnnotation,
    JavaAssignment,
    JavaCall,
    JavaClass,
    JavaField,
    JavaInitializer,
    JavaMethod,
    JavaParam,
    JavaSyntaxFile,
)


def test_universal_java_observations_are_syntactic_and_structured(tmp_path):
    path = tmp_path / "src/main/java/example/Converter.java"
    path.parent.mkdir(parents=True)
    path.write_text(
        '''package example;
        @MetaRootEntity(id = "id")
        class Individual extends BaseEntity {
          private String id;
          ChangeVector convert(Individual individual, Ceb ceb) {
            String blockKey = "Individual_" + individual.getId();
            ceb.referenceField("gender", blockKey);
            CONVERTERS.put("individual", new Converter());
            return null;
          }
        }
        ''',
        encoding="utf-8",
    )

    facts, status = obs.build_java_source_observation_facts([path])
    by_type = {}
    for fact in facts:
        by_type.setdefault(fact.fact_type, []).append(fact)

    annotation = by_type["code_annotation"][0]
    assert annotation.properties["annotation"] == "MetaRootEntity"
    assert annotation.properties["arguments"]["id"]["raw"] == '"id"'
    assert annotation.properties["arguments"]["id"]["node_type"] == "string_literal"
    assert "replica" not in str(annotation.properties).lower()

    constructed = next(
        fact for fact in by_type["constructed_value_observation"]
        if fact.properties.get("target_variable") == "blockKey"
    )
    assert constructed.properties["expression_tree"]["node_type"] == "binary_expression"
    assert constructed.properties["expression_tree"]["operator"] == "+"
    assert "individual.getId" in constructed.properties["input_symbols"]

    flows = by_type["call_argument_flow_observation"]
    gender_flow = next(
        fact for fact in flows
        if fact.properties["target_method"] == "referenceField"
        and fact.properties["argument_index"] == 1
    )
    assert gender_flow.properties["source_expression"] == "blockKey"
    assert gender_flow.properties["input_symbols"] == ["blockKey"]
    assert gender_flow.properties["expression_tree"]["node_type"] == "identifier"

    mutation = next(
        fact for fact in by_type["collection_mutation_observation"]
        if fact.properties.get("receiver_expression") == "CONVERTERS"
    )
    assert mutation.properties["operation_kind"] == "map_entry_assignment"
    assert status["provider"] == "tree_sitter"
    assert status["parse_warnings"] == []

def test_structured_config_preserves_lists_scalars_and_paths(tmp_path):
    path = tmp_path / "CONFIGURE-MODEL.yaml"
    path.write_text(
        """whitelist:\n  excludedTypes:\n    - a.Type\ncustomFields:\n  - source: person.gender\n    targetType: java.lang.String\ndateAsString: true\n""",
        encoding="utf-8",
    )
    facts = scan_config_files([path])
    entries = {f.properties.get("configuration_path"): f for f in facts if f.fact_type == "configuration_entry"}
    assert entries["whitelist.excludedTypes"].properties["node_kind"] == "list"
    assert entries["whitelist.excludedTypes[0]"].properties["value"] == "a.Type"
    assert entries["customFields[0].source"].properties["value"] == "person.gender"
    assert entries["customFields[0].targetType"].properties["value"] == "java.lang.String"
    assert entries["dateAsString"].properties["value"] is True


def test_maven_dependency_scan_is_independent_of_interaction_stage(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text(
        """<project><properties><model.version>1.2.3</model.version></properties><dependencies><dependency><groupId>com.example</groupId><artifactId>model</artifactId><version>${model.version}</version></dependency></dependencies></project>""",
        encoding="utf-8",
    )
    facts, status = scan_maven_dependencies([pom])
    assert status["dependencies_extracted"] == 1
    assert facts[0].properties["coordinate"] == "com.example:model:1.2.3"
    assert "provider" not in facts[0].properties


def test_generic_core_has_no_default_meta_annotation_semantics():
    assert _normalized_model_annotation_contracts() == {}
    assert _normalized_model_annotation_contracts({"BusinessObject": "meta_entity"}) == {"BusinessObject": "meta_entity"}


def test_full_source_observation_store_is_uncapped_and_cli_is_bounded(tmp_path):
    from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
    from code_analyzer_core.prepared_artifacts.source_observation_fact_store import write_source_observation_fact_store
    from code_analyzer_core.normalizer import write_normalized_fact_store
    from code_evidence.commands import facts_by_type

    result = AnalysisResult(system_name="sample", project_code="sample", repo_path=str(tmp_path))
    result.facts = [
        Fact(
            fact_type="java_method_call_observation",
            name=f"Example.call{index}",
            properties={"observation_id": f"call_{index:04d}", "method": f"call{index}"},
            evidence=[EvidenceRef(file_path="src/main/java/Example.java", line_start=index + 1, extractor="java_tree_sitter")],
        )
        for index in range(620)
    ]
    facts_dir = tmp_path / "analysis" / "facts"
    compact_summary = write_normalized_fact_store(result, facts_dir, max_items_per_type=500)
    full_status = write_source_observation_fact_store(result=result, facts_dir=facts_dir)

    assert compact_summary["persisted_by_type"]["java_method_call_observation"] == 500
    assert full_status["fact_type_counts"]["java_method_call_observation"] == 620
    assert sum(1 for _ in (facts_dir / "full_by_type" / "java_method_call_observation.jsonl").open(encoding="utf-8")) == 620

    payload = facts_by_type(tmp_path / "analysis", "java-method-call-observation", max_results=17)
    assert payload["fact_store_source"] == "full_by_type_jsonl"
    assert payload["returned"] == 17
    assert payload["facts"][0]["fact_id"] == "call_0000"



def test_static_and_field_initializers_publish_calls_without_api_semantics(tmp_path, monkeypatch):
    path = tmp_path / "src/main/java/example/Registry.java"
    path.parent.mkdir(parents=True)
    path.write_text("package example; class Registry {}", encoding="utf-8")
    pair_call = JavaCall(
        receiver="Pair",
        method="of",
        args=("EquivalentSystemType.class", "KeyType.DICTIONARY_CODE"),
        args_text="(EquivalentSystemType.class, KeyType.DICTIONARY_CODE)",
        text="Pair.of(EquivalentSystemType.class, KeyType.DICTIONARY_CODE)",
        line_start=4,
        line_end=4,
        start_byte=40,
        end_byte=100,
    )
    field = JavaField(
        class_name="Registry",
        name="ENTRIES",
        type="List<Pair<Class<?>, KeyType>>",
        raw="private static final List<?> ENTRIES = List.of(Pair.of(...));",
        line_start=4,
        line_end=4,
        initializer="List.of(Pair.of(EquivalentSystemType.class, KeyType.DICTIONARY_CODE))",
        initializer_calls=(pair_call,),
    )
    put_call = JavaCall(
        receiver="CONVERTERS",
        method="put",
        args=('"individual"', "new IndividualConverter()"),
        args_text='("individual", new IndividualConverter())',
        text='CONVERTERS.put("individual", new IndividualConverter())',
        line_start=7,
        line_end=7,
        start_byte=120,
        end_byte=180,
    )
    initializer = JavaInitializer(
        class_name="Registry",
        is_static=True,
        text="static { CONVERTERS.put(...); }",
        file=path,
        line_start=6,
        line_end=8,
        calls=(put_call,),
    )
    cls = JavaClass(
        name="Registry",
        kind="class",
        file=path,
        package="example",
        annotations=(),
        modifiers="public",
        text="class Registry {}",
        line_start=1,
        line_end=10,
        fields=(field,),
        initializers=(initializer,),
    )
    parsed = JavaSyntaxFile(
        file=path,
        text=path.read_text(),
        package="example",
        imports=("org.apache.commons.lang3.tuple.Pair", "example.EquivalentSystemType", "example.KeyType"),
        classes=(cls,),
    )
    monkeypatch.setattr(obs, "parse_java_files", lambda files: ((parsed,), ()))
    facts, _ = obs.build_java_source_observation_facts([path])

    calls = [fact for fact in facts if fact.fact_type == "java_method_call_observation"]
    assert any(f.properties["method"] == "of" and f.properties["owner_scope_kind"] == "field_initializer" for f in calls)
    assert any(f.properties["method"] == "put" and f.properties["owner_scope_kind"] == "static_initializer" for f in calls)
    mutation = next(f for f in facts if f.fact_type == "collection_mutation_observation")
    assert mutation.properties["operation_kind"] == "map_entry_assignment"
    assert "registry" not in mutation.fact_type
    field_value = next(
        f for f in facts
        if f.fact_type == "constructed_value_observation" and f.properties.get("target_kind") == "field_initializer"
    )
    assert field_value.properties["target_variable"] == "ENTRIES"


def test_expression_structuring_comes_directly_from_tree_sitter_ast():
    from code_analyzer_core.scanners.java_syntax import parse_java_text

    parsed = parse_java_text(
        '''class Expressions {
          String make(Individual individual, String parentKey, String fieldName, Child child) {
            String blockKey = "Individual_" + individual.getId();
            String childKey = parentKey + "." +
                (child != null ? fieldName + "_" + child.getId() : fieldName);
            return childKey;
          }
        }''',
        file="Expressions.java",
    )
    assert parsed.parse_errors == 0
    method = parsed.classes[0].methods[0]
    block_key = next(item for item in method.assignments if item.target == "blockKey")
    child_key = next(item for item in method.assignments if item.target == "childKey")

    assert block_key.expression_tree["node_type"] == "binary_expression"
    assert block_key.expression_tree["operator"] == "+"
    assert block_key.input_symbols == ("individual.getId", "individual")

    assert child_key.expression_tree["node_type"] == "binary_expression"
    assert child_key.expression_tree["operator"] == "+"
    assert {"parentKey", "child", "fieldName", "child.getId"}.issubset(child_key.input_symbols)

    def node_types(tree):
        yield tree.get("node_type")
        for child in tree.get("children", []):
            yield from node_types(child)

    assert "ternary_expression" in set(node_types(child_key.expression_tree))

def test_real_tree_sitter_parses_field_and_static_initializers(tmp_path):
    from code_analyzer_core.scanners.java_syntax import parse_java_file, tree_sitter_available

    ok, detail = tree_sitter_available()
    if not ok:
        import pytest
        pytest.skip(detail)

    source = tmp_path / "src/main/java/example/Registry.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''package example;
        import java.util.List;
        class Registry {
          static final List<Object> ENTRIES = List.of(
              Pair.of(EquivalentSystemType.class, localFromNsiDict(
                  EquivalentSystemType.class, "Source", KeyType.DICTIONARY_CODE)), // item 1
              initIgniteType(SEQ++, "Individual", KeyType.IGNITE_LONG_ID) // item 2
          );
          static {
            CONVERTERS.put("individual", new IndividualConverter());
            ENTRY_TYPES.add(localDict(EquivalentSystemType.class));
          }
        }
        ''',
        encoding="utf-8",
    )
    parsed = parse_java_file(source)
    cls = parsed.classes[0]
    field = next(item for item in cls.fields if item.name == "ENTRIES")
    assert field.initializer
    assert {call.method for call in field.initializer_calls} >= {
        "of", "localFromNsiDict", "initIgniteType"
    }
    assert len(cls.initializers) == 1
    initializer = cls.initializers[0]
    assert initializer.is_static is True
    assert {(call.receiver, call.method) for call in initializer.calls} >= {
        ("CONVERTERS", "put"), ("ENTRY_TYPES", "add")
    }

    facts, status = obs.build_java_source_observation_facts([source])
    assert status["parse_warnings"] == []
    calls = [fact for fact in facts if fact.fact_type == "java_method_call_observation"]
    assert any(
        fact.properties.get("owner_scope_kind") == "field_initializer"
        and fact.properties.get("method") == "initIgniteType"
        for fact in calls
    )
    assert any(
        fact.properties.get("owner_scope_kind") == "static_initializer"
        and fact.properties.get("receiver_expression") == "CONVERTERS"
        and fact.properties.get("method") == "put"
        for fact in calls
    )


def test_yaml_config_observations_preserve_exact_lines_group_objects_and_comments(tmp_path):
    path = tmp_path / "CONFIGURE-CONVERTERS.yaml"
    path.write_text(
        """pojoConverters:\n  types:\n    # main individual model\n    - className: 'com.example.model.Individual'\n      v3Compatible: true\n    - className: 'com.example.model.Address' # nested model\n      dateFormat: yyyy-MM-dd\ncustomFields:\n  - source: 'com.example.model.Individual:gender'\n    targetType: 'java.lang.String'\nartifact: '${project.artifactId}'\n""",
        encoding="utf-8",
    )

    facts = scan_config_files([path])
    entries = {
        fact.properties.get("configuration_path"): fact
        for fact in facts
        if fact.fact_type == "configuration_entry"
    }
    first_class = entries["pojoConverters.types[0].className"]
    second_class = entries["pojoConverters.types[1].className"]
    assert first_class.evidence[0].line_start == 4
    assert second_class.evidence[0].line_start == 6
    assert first_class.properties["scalar_shape"] == "java_type_reference"
    assert first_class.properties["path_segments"] == ["pojoConverters", "types", 0, "className"]

    objects = {
        fact.properties.get("configuration_path"): fact
        for fact in facts
        if fact.fact_type == "configuration_object_observation"
    }
    first_object = objects["pojoConverters.types[0]"]
    assert first_object.properties["scalar_fields"] == {
        "className": "com.example.model.Individual",
        "v3Compatible": True,
    }
    assert first_object.properties["referenced_values"][0]["scalar_shape"] == "java_type_reference"

    references = [fact for fact in facts if fact.fact_type == "configuration_reference_observation"]
    member = next(fact for fact in references if fact.properties["reference_kind"] == "qualified_member_reference")
    assert member.properties["owner_qualified_name"] == "com.example.model.Individual"
    assert member.properties["member_name"] == "gender"
    template = next(fact for fact in references if fact.properties["reference_kind"] == "template_variable_reference")
    assert template.properties["template_variable"] == "project.artifactId"

    comments = [fact for fact in facts if fact.fact_type == "configuration_comment_observation"]
    assert any(fact.properties["comment_text"] == "main individual model" for fact in comments)
    inline = next(fact for fact in comments if fact.properties["comment_text"] == "nested model")
    assert inline.properties["comment_kind"] == "inline"
    assert inline.properties["associated_configuration_path"] == "pojoConverters.types[1].className"


def test_configuration_observations_do_not_assign_domain_verdicts(tmp_path):
    path = tmp_path / "CONFIGURE-MODEL.yaml"
    path.write_text(
        """whitelist:\n  excludedFields:\n    - 'com.example.model.Individual:globalKey'\n""",
        encoding="utf-8",
    )
    facts = scan_config_files([path])
    payload = " ".join(str(fact.properties).lower() for fact in facts)
    for forbidden in ("primary_key", "foreign_key", "replica_table", "join_on", "confidence", "verdict"):
        assert forbidden not in payload


def test_method_calls_publish_receiver_structure_nesting_and_method_references(tmp_path):
    path = tmp_path / "Mapper.java"
    path.write_text(
        '''class Mapper {
          String map(Request request) {
            return Response.builder()
                .key(keyOf(request.getId()))
                .items(request.getItems().stream().map(this::convert).toList())
                .build();
          }
          String convert(Item item) { return item.toString(); }
          String keyOf(String value) { return value; }
        }''',
        encoding="utf-8",
    )

    facts, status = obs.build_java_source_observation_facts([path])
    assert status["status"] == "success"

    calls = [fact for fact in facts if fact.fact_type == "java_method_call_observation"]
    by_method = {}
    for fact in calls:
        by_method.setdefault(fact.properties["method"], []).append(fact)

    build = by_method["build"][0]
    assert build.properties["receiver_expression_tree"]["node_type"] == "method_invocation"
    assert build.properties["receiver_input_symbols"]
    assert build.properties["call_depth"] == 0
    assert build.properties["nested_call_observation_ids"]

    get_id = by_method["getId"][0]
    assert get_id.properties["parent_call_observation_id"]
    assert get_id.properties["call_depth"] >= 1

    refs = [fact for fact in facts if fact.fact_type == "java_method_reference_observation"]
    assert len(refs) == 1
    ref = refs[0]
    assert ref.properties["qualifier_expression"] == "this"
    assert ref.properties["referenced_method"] == "convert"
    assert ref.properties["qualifier_expression_tree"]["node_type"] == "this"


def test_configuration_references_resolve_exact_java_types_fields_and_unresolved(tmp_path):
    java = tmp_path / "src/main/java/com/example/model/Individual.java"
    java.parent.mkdir(parents=True)
    java.write_text(
        """package com.example.model; public class Individual { String gender; }""",
        encoding="utf-8",
    )
    cfg = tmp_path / "CONFIGURE-CONVERTERS.yaml"
    cfg.write_text(
        """types:
  - className: 'com.example.model.Individual'
fields:
  - source: 'com.example.model.Individual:gender'
  - source: 'com.example.model.Individual:missing'
""",
        encoding="utf-8",
    )
    facts = scan_config_files([cfg, java])
    resolutions = [f for f in facts if f.fact_type == "configuration_reference_resolution_observation"]
    by_value = {f.properties["reference_value"]: f for f in resolutions}
    assert by_value["com.example.model.Individual"].properties["resolution_status"] == "resolved_unique"
    assert by_value["com.example.model.Individual:gender"].properties["resolution_status"] == "resolved_unique"
    assert by_value["com.example.model.Individual:missing"].properties["resolution_status"] == "unresolved"
    assert by_value["com.example.model.Individual:gender"].properties["candidates"][0]["member_name"] == "gender"
    payload = " ".join(str(f.properties).lower() for f in resolutions)
    for forbidden in ("primary_key", "foreign_key", "replica_table", "join_on", "confidence", "verdict"):
        assert forbidden not in payload


def test_exact_same_class_call_bindings_preserve_key_helper_value_flow(tmp_path):
    path = tmp_path / "src/main/java/example/Converter.java"
    path.parent.mkdir(parents=True)
    path.write_text(
        '''package example;
        class Converter {
          void convert(Individual individual, Builder ceb, Vector cvb) {
            String key = "Individual_" + individual.getId();
            ceb.replaceReferenceCollection(
                "addresses",
                convertAddressCollection(cvb, individual.getAddresses(), "addresses", key)
            );
          }

          java.util.List<String> convertAddressCollection(
              Vector cvb, java.util.Collection<Address> entities,
              String fieldName, String parentKey) {
            java.util.List<String> keys = new java.util.ArrayList<>();
            for (Address address : entities) {
              String key = convertAddress(cvb, address, fieldName, parentKey);
              keys.add(key);
            }
            return keys;
          }

          String convertAddress(Vector cvb, Address address, String fieldName, String parentKey) {
            String key = parentKey + "." + fieldName + "_" + address.getId();
            return key;
          }
        }
        ''',
        encoding="utf-8",
    )

    facts, status = obs.build_java_source_observation_facts([path])
    parameter_bindings = [
        fact for fact in facts
        if fact.fact_type == "java_call_parameter_binding_observation"
    ]
    result_bindings = [
        fact for fact in facts
        if fact.fact_type == "java_call_result_binding_observation"
    ]

    root_parent = next(
        fact for fact in parameter_bindings
        if fact.properties["caller_operation"] == "Converter.convert"
        and fact.properties["callee_method"] == "convertAddressCollection"
        and fact.properties["callee_parameter"] == "parentKey"
    )
    assert root_parent.properties["caller_expression"] == "key"
    assert root_parent.properties["caller_input_symbols"] == ["key"]
    assert root_parent.properties["resolution"] == "exact_same_class_name_and_arity"

    root_field = next(
        fact for fact in parameter_bindings
        if fact.properties["caller_operation"] == "Converter.convert"
        and fact.properties["callee_method"] == "convertAddressCollection"
        and fact.properties["callee_parameter"] == "fieldName"
    )
    assert root_field.properties["caller_expression"] == '"addresses"'
    assert root_field.properties["caller_expression_tree"]["node_type"] == "string_literal"

    nested_parent = next(
        fact for fact in parameter_bindings
        if fact.properties["caller_operation"] == "Converter.convertAddressCollection"
        and fact.properties["callee_method"] == "convertAddress"
        and fact.properties["callee_parameter"] == "parentKey"
    )
    assert nested_parent.properties["caller_expression"] == "parentKey"

    collection_result = next(
        fact for fact in result_bindings
        if fact.properties["caller_operation"] == "Converter.convert"
        and fact.properties["callee_method"] == "convertAddressCollection"
    )
    assert collection_result.properties["result_target_kind"] == "parent_call_argument"
    assert collection_result.properties["parent_argument_index"] == 1

    child_result = next(
        fact for fact in result_bindings
        if fact.properties["caller_operation"] == "Converter.convertAddressCollection"
        and fact.properties["callee_method"] == "convertAddress"
    )
    assert child_result.properties["result_target_kind"] == "assigned_variable"
    assert child_result.properties["target_variable"] == "key"
    assert status["fact_type_counts"]["java_call_parameter_binding_observation"] >= 8
    assert status["fact_type_counts"]["java_call_result_binding_observation"] >= 2


def test_full_source_store_includes_configuration_reference_resolutions(tmp_path):
    from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
    from code_analyzer_core.prepared_artifacts.source_observation_fact_store import write_source_observation_fact_store

    result = AnalysisResult(system_name="sample", project_code="sample", repo_path=str(tmp_path))
    result.config_facts = [
        Fact(
            fact_type="configuration_reference_resolution_observation",
            name="example.Customer",
            properties={
                "observation_id": "config-resolution-1",
                "reference_value": "example.Customer",
                "resolution_kind": "exact_java_type",
                "resolved_qualified_name": "example.Customer",
            },
            evidence=[EvidenceRef(file_path="application.yaml", line_start=3, extractor="config_scanner")],
        )
    ]

    status = write_source_observation_fact_store(result=result, facts_dir=tmp_path / "facts")
    target = tmp_path / "facts" / "full_by_type" / "configuration_reference_resolution_observation.jsonl"

    assert status["fact_type_counts"]["configuration_reference_resolution_observation"] == 1
    assert target.is_file()
    assert "example.Customer" in target.read_text(encoding="utf-8")


def test_declared_parameters_and_interface_correspondence_are_published_without_runtime_selection(tmp_path):
    path = tmp_path / "src/main/java/example/Service.java"
    path.parent.mkdir(parents=True)
    path.write_text(
        '''package example;
        import java.util.Set;

        interface Dao {
          void save(Set<String> values, boolean active);
        }

        class FirstDao implements Dao {
          @Override public void save(Set<String> allValues, boolean enabled) { }
        }

        class SecondDao implements Dao {
          @Override public void save(Set<String> items, boolean flag) { }
        }

        class Service {
          Dao dao;
          void run(Set<String> phones) {
            dao.save(phones, true);
          }
        }
        ''',
        encoding="utf-8",
    )

    facts, status = obs.build_java_source_observation_facts([path])

    parameters = [fact for fact in facts if fact.fact_type == "java_method_parameter_observation"]
    dao_parameters = [
        fact for fact in parameters
        if fact.properties["owner_fqcn"] == "example.Dao"
        and fact.properties["method_name"] == "save"
    ]
    assert [(f.properties["parameter_position"], f.properties["parameter_name"], f.properties["parameter_type"]) for f in dao_parameters] == [
        (0, "values", "Set<String>"),
        (1, "active", "boolean"),
    ]
    assert all(f.properties["declaration_kind"] == "interface_method_parameter" for f in dao_parameters)

    bindings = [
        fact for fact in facts
        if fact.fact_type == "java_call_parameter_binding_observation"
        and fact.properties.get("caller_operation") == "Service.run"
    ]
    assert len(bindings) == 2
    assert {fact.properties["callee_owner_fqcn"] for fact in bindings} == {"example.Dao"}
    assert {fact.properties["callee_parameter"] for fact in bindings} == {"values", "active"}
    assert all(
        fact.properties["resolution"] == "exact_declared_receiver_type_and_unique_source_method_name_arity"
        for fact in bindings
    )

    implementations = [fact for fact in facts if fact.fact_type == "java_method_implementation_observation"]
    assert {fact.properties["implementation_owner_fqcn"] for fact in implementations} == {
        "example.FirstDao", "example.SecondDao"
    }
    assert all(fact.properties["relation_kind"] == "correspondence" for fact in implementations)
    assert all("runtime dispatch" in fact.properties["observation_policy"] for fact in implementations)

    parameter_correspondences = [
        fact for fact in facts
        if fact.fact_type == "java_method_parameter_correspondence_observation"
    ]
    assert len(parameter_correspondences) == 4
    assert {
        (fact.properties["implementation_owner_fqcn"], fact.properties["parameter_position"], fact.properties["declared_parameter"], fact.properties["implementation_parameter"])
        for fact in parameter_correspondences
    } == {
        ("example.FirstDao", 0, "values", "allValues"),
        ("example.FirstDao", 1, "active", "enabled"),
        ("example.SecondDao", 0, "values", "items"),
        ("example.SecondDao", 1, "active", "flag"),
    }
    assert status["fact_type_counts"]["java_method_parameter_observation"] >= 7
