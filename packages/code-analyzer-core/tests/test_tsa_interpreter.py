from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.tsa_interpreter import interpret_tsa_facts


def ev(line=1):
    return [EvidenceRef(file_path="src/Test.java", line_start=line, extractor="tree_sitter")]


def test_tsa_interpreter_emits_annotations_registrations_and_directives():
    facts = [
        Fact(fact_type="code_annotation", name="x.Root@MetaRootEntity", properties={"observation_id":"a1","annotation":"MetaRootEntity","owner_kind":"type","owner_fqcn":"x.Root"}, evidence=ev()),
        Fact(fact_type="configuration_object_observation", name="cfg", properties={"observation_id":"c1","configuration_path":"pojoConverters.types[1]","scalar_fields":{"className":"x.Root","converterClass":"x.Conv"}}, evidence=ev(2)),
        Fact(fact_type="configuration_entry", name="excluded", properties={"observation_id":"e1","configuration_path":"excludedFields[0]","value":"x.Root:secret"}, evidence=ev(3)),
    ]
    out, status = interpret_tsa_facts(facts)
    kinds = {f.properties["tsa_observation_kind"] for f in out}
    assert kinds == {"tsa_meta_annotation", "pojo_converter_registration", "excluded_field"}
    assert status["observations_emitted"] == 3
    assert all("confidence" not in f.properties for f in out)


def test_tsa_interpreter_links_reference_and_key_calls_to_argument_ast():
    facts = [
        Fact(fact_type="java_method_call_observation", name="ref", properties={"observation_id":"call-r","owner_fqcn":"x.Conv","owner_operation":"x.Conv.convert","receiver_expression":"ceb","method":"referenceCollection"}, evidence=ev(10)),
        Fact(fact_type="call_argument_flow_observation", name="ref-arg", properties={"observation_id":"arg-r","call_observation_id":"call-r","argument_index":0,"source_expression":"items","input_symbols":["items"],"expression_tree":{"node_type":"identifier"}}, evidence=ev(10)),
        Fact(fact_type="java_method_call_observation", name="key", properties={"observation_id":"call-k","owner_fqcn":"x.Conv","owner_operation":"x.Conv.convert","receiver_expression":"ceb","method":"key"}, evidence=ev(11)),
        Fact(fact_type="call_argument_flow_observation", name="key-arg", properties={"observation_id":"arg-k","call_observation_id":"call-k","argument_index":0,"source_expression":"parentKey + '_' + id","input_symbols":["parentKey","id"],"expression_tree":{"node_type":"binary_expression"}}, evidence=ev(11)),
    ]
    out, _ = interpret_tsa_facts(facts)
    ref = next(f for f in out if f.fact_type == "tsa_reference_operation_observation")
    key = next(f for f in out if f.fact_type == "tsa_key_expression_observation")
    assert ref.properties["argument_expressions"] == ["items"]
    assert key.properties["key_expression"] == "parentKey + '_' + id"
    assert key.properties["input_symbols"] == ["parentKey", "id"]
    assert "primary" not in key.properties


def test_tsa_interpreter_covers_real_ucp_meta_annotation_family_without_verdicts():
    annotations = [
        "MetaRootEntity",
        "MetaVersionedEntity",
        "MetaEntity",
        "MetaDictionary",
        "MetaVersionedDictionary",
        "MetaIgnore",
    ]
    facts = [
        Fact(
            fact_type="code_annotation",
            name=f"x.Type{i}@{annotation}",
            properties={
                "observation_id": f"ann-{i}",
                "annotation": annotation,
                "annotation_fqcn": f"ru.sbrf.ucp.meta.annotations.{annotation}",
                "owner_kind": "type",
                "owner_fqcn": f"x.Type{i}",
            },
            evidence=ev(i + 20),
        )
        for i, annotation in enumerate(annotations)
    ]
    out, status = interpret_tsa_facts(facts)
    assert {fact.properties["annotation"] for fact in out} == set(annotations)
    ignored = next(fact for fact in out if fact.properties["annotation"] == "MetaIgnore")
    assert ignored.properties["observation_policy"].endswith("no storage or entity verdict")
    assert "excluded" not in ignored.properties
    assert status["counts_by_kind"]["tsa_meta_annotation"] == len(annotations)


def test_tsa_interpreter_composes_reference_collection_storage_key_lineage(tmp_path):
    from pathlib import Path
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/IndividualToChangeVectorConverter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class IndividualToChangeVectorConverter {
          Object convert(Individual individual, Builder ceb, Vector cvb) {
            String key = "Individual_" + individual.getId();
            ceb.key(key);
            ceb.alias("example.Individual");
            ceb.replaceReferenceCollection(
                "addresses",
                convertAddressCollection(cvb, individual.getAddresses(), "addresses", key)
            );
            return null;
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
            ceb().key(key);
            ceb().alias("example.Address");
            return key;
          }

          Builder ceb() { return null; }
        }
        ''',
        encoding="utf-8",
    )

    generic_facts, _ = build_java_source_observation_facts([source_path])
    out, status = interpret_tsa_facts(generic_facts)

    lineage = next(fact for fact in out if fact.fact_type == "tsa_storage_key_lineage_observation")
    props = lineage.properties
    assert props["relationship_field"] == "addresses"
    assert props["reference_operation"] == "replaceReferenceCollection"
    assert props["source_alias"] == "example.Individual"
    assert props["target_alias"] == "example.Address"
    assert props["target_storage_key_field"] == "key"
    assert props["source_key_expression"] == '"Individual_" + individual.getId()'
    assert props["target_key_expression_template"] == 'parentKey + "." + fieldName + "_" + address.getId()'
    assert '"Individual_"' in props["composed_target_key_expression"]
    assert '"addresses"' in props["composed_target_key_expression"]
    assert "address.getId()" in props["composed_target_key_expression"]
    assert props["source_key_passed_into_target_key"] is True
    assert "parentKey" in props["source_key_parameter_bindings"]
    assert [row["callee_parameter"] for row in props["binding_path"] if row["callee_operation"].endswith("convertAddressCollection")][-2:] == ["fieldName", "parentKey"]
    assert status["counts_by_kind"]["reference_collection_storage_key_lineage"] == 1
    assert "join" not in props
    assert "physical_table" not in props


def test_tsa_interpreter_composes_reference_field_value_derivation(tmp_path):
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/IndividualToChangeVectorConverter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class IndividualToChangeVectorConverter {
          Object convertAddress(Address address, Builder ceb) {
            ceb.alias("example.Address");
            ceb.referenceField("country", convertCountry(address.getCountry()));
            return null;
          }

          String convertCountry(Country country) {
            return "Country_" + country.getCode();
          }
        }
        ''',
        encoding="utf-8",
    )

    generic_facts, _ = build_java_source_observation_facts([source_path])
    out, status = interpret_tsa_facts(generic_facts)

    derivation = next(
        fact for fact in out
        if fact.fact_type == "tsa_reference_value_derivation_observation"
    )
    props = derivation.properties
    assert props["relationship_field"] == "country"
    assert props["reference_operation"] == "referenceField"
    assert props["source_alias"] == "example.Address"
    assert props["reference_value_expression"] == "convertCountry(address.getCountry())"
    assert props["value_converter_operation"].endswith("convertCountry")
    assert props["return_expression_template"] == '"Country_" + country.getCode()'
    assert '"Country_"' in props["composed_reference_value_expression"]
    assert "address.getCountry()" in props["composed_reference_value_expression"]
    assert props["value_converter_parameter_bindings"] == [
        {
            "parameter": "country",
            "resolved_expression": "address.getCountry()",
            "source_observation_id": props["value_converter_parameter_bindings"][0]["source_observation_id"],
        }
    ]
    assert status["counts_by_kind"]["reference_field_value_derivation"] == 1
    assert "target_key" not in props
    assert "join" not in props


def test_tsa_interpreter_resolves_reused_local_names_by_lexical_scope(tmp_path):
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/ParentConverter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class ParentConverter {
          Object convert(Parent parent, Builder builder) {
            if (parent.first() != null) {
              String refKey = convertFirst(parent.first());
              builder.referenceField("first", refKey);
            }
            if (parent.second() != null) {
              String refKey = convertSecond(parent.second());
              builder.referenceField("second", refKey);
            }
            return null;
          }
          String convertFirst(Child child) { return "First_" + child.id(); }
          String convertSecond(Child child) { return "Second_" + child.id(); }
        }
        ''',
        encoding="utf-8",
    )

    facts, _ = build_java_source_observation_facts([source_path])
    result_bindings = [
        fact for fact in facts
        if fact.fact_type == "java_call_result_binding_observation"
    ]
    assert len(result_bindings) == 2
    assert all(fact.properties.get("target_scope_start_byte") is not None for fact in result_bindings)
    assert all(fact.properties.get("target_assignment_start_byte") is not None for fact in result_bindings)

    out, status = interpret_tsa_facts(facts)
    derivations = [
        fact for fact in out
        if fact.fact_type == "tsa_reference_value_derivation_observation"
    ]
    assert [(fact.properties["relationship_field"], fact.properties["value_converter_operation"]) for fact in derivations] == [
        ("first", "ParentConverter.convertFirst"),
        ("second", "ParentConverter.convertSecond"),
    ]
    assert all(
        fact.properties["reference_value_binding_resolution"] == "nearest_visible_dominating_assignment"
        for fact in derivations
    )
    assert status["counts_by_kind"]["reference_field_value_derivation"] == 2


def test_configurable_builder_api_roles_publish_generic_storage_record_and_reference(tmp_path):
    from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts

    source_path = tmp_path / "src/main/java/example/GenericConverter.java"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '''package example;
        class GenericConverter {
          Object convert(Parent parent, Writer parentWriter) {
            String reference = makeChild(parent.child(), "child", "Parent_" + parent.id());
            parentWriter.linkField("child", reference);
            return null;
          }
          String makeChild(Child child, String segment, String parentKey) {
            String recordKey = parentKey + "." + segment;
            Writer writer = createWriter();
            writer.recordType("example.Child");
            writer.recordId(recordKey);
            return recordKey;
          }
          Writer createWriter() { return null; }
        }
        ''',
        encoding="utf-8",
    )
    api_roles = {
        "framework": "example_writer",
        "reference_methods": {
            "linkField": {"kind": "field", "field_argument": 0, "value_argument": 1},
        },
        "record_key_methods": {
            "recordId": {"value_argument": 0, "storage_field": "record_key"},
        },
        "record_alias_methods": {
            "recordType": {"value_argument": 0},
        },
    }

    facts, _ = build_java_source_observation_facts([source_path])
    out, status = interpret_tsa_facts(facts, api_roles=api_roles)

    storage_record = next(fact for fact in out if fact.fact_type == "storage_record_observation")
    assert storage_record.properties["api_framework"] == "example_writer"
    assert storage_record.properties["storage_alias"] == "example.Child"
    assert storage_record.properties["storage_key_field"] == "record_key"
    assert storage_record.properties["storage_key_expression"] == 'parentKey + "." + segment'
    assert storage_record.properties["physical_reference_encoding"] == "downstream_interpretation_required"

    storage_reference = next(fact for fact in out if fact.fact_type == "storage_reference_observation")
    assert storage_reference.properties["source_field"] == "child"
    assert storage_reference.properties["target_alias"] == "example.Child"
    assert storage_reference.properties["target_storage_key_field"] == "record_key"
    assert storage_reference.properties["target_storage_key_expression"] == 'parentKey + "." + segment'
    assert storage_reference.properties["value_origin"] == "returned_target_storage_key"
    assert storage_reference.properties["physical_encoding"] == "downstream_interpretation_required"
    assert "separator" not in storage_reference.properties
    assert "normalization" not in storage_reference.properties
    assert status["counts_by_kind"]["reference_value_from_target_storage_record"] == 1
