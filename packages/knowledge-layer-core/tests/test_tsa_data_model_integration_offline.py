from knowledge_layer_core.model_relations import build_model_relationship_rows
from knowledge_layer_core.workspace_schema import DDL
import json


def test_tsa_views_extract_configured_class_name_property():
    block = DDL.split("CREATE VIEW v_tsa_converter_configurations", 1)[1].split("CREATE VIEW", 1)[0]
    assert "$.properties.configured_class_name" in block
    assert "$.properties.class_name" not in block


def test_tsa_reference_and_key_observations_feed_relationship_mart():
    root = "example.Root"
    child = "example.Child"
    converter = "example.RootConverter"
    relationships, expressions, polymorphic, embedded, candidates = build_model_relationship_rows(
        key_rows=[{"key_observation_id": "key-root", "repo_id": "model", "object_fqcn": root}],
        type_rows=[
            {"java_type_occurrence_id": "type-root", "repo_id": "model", "fqcn": root},
            {"java_type_occurrence_id": "type-child", "repo_id": "model", "fqcn": child},
        ],
        field_rows=[{
            "code_field_occurrence_id": "field-children", "repo_id": "model", "owner_fqcn": root,
            "field_name": "children", "declared_type": "List<Child>", "container_kind": "collection",
            "element_type": "Child", "annotations_json": "[]", "model_exclusion_observed": False,
            "model_exclusion_annotations_json": "[]",
        }],
        inheritance_rows=[],
        type_reference_rows=[{
            "source_observation_occurrence_id": "ref-type", "repo_id": "model", "owner_fqcn": root,
            "member_name": "children", "reference_role": "field_type", "referenced_type": "Child",
            "resolved_fqcn": child, "candidate_fqcns_json": "[]",
        }],
        method_call_rows=[], argument_flow_rows=[], constructed_value_rows=[],
        tsa_reference_rows=[{
            "source_observation_occurrence_id": "tsa-ref", "repo_id": "converter", "owner_fqcn": converter,
            "owner_method": "convert", "tsa_observation_kind": "reference_collection_call",
            "method": "referenceCollection", "argument_expressions_json": '["children"]',
        }],
        tsa_key_expression_rows=[{
            "source_observation_occurrence_id": "tsa-key", "repo_id": "converter", "owner_fqcn": converter,
            "owner_method": "convert", "key_expression": '"Root_" + id',
            "key_input_symbols_json": '["id"]',
        }],
    )
    assert len(relationships) == 1
    relation = relationships[0]
    assert relation[2] == root
    assert relation[6] == "children"
    assert relation[11] == child
    assert relation[14] == "reference_collection"
    assert relation[15] == "many"
    assert relation[17] == "referenceCollection"
    assert relation[19] == '["tsa-ref"]'
    assert any(row[1] == relation[0] and row[2] == "source" and row[3] == '"Root_" + id' for row in expressions)
    assert polymorphic == []
    assert embedded == []
    assert candidates == []


def test_key_expression_bindings_preserve_each_reference_operation():
    root = "example.Root"
    child = "example.Child"
    converter = "example.RootConverter"
    common = dict(
        key_rows=[
            {"key_observation_id": "key-root", "repo_id": "model", "object_fqcn": root},
            {"key_observation_id": "key-child", "repo_id": "model", "object_fqcn": child},
        ],
        type_rows=[
            {"java_type_occurrence_id": "type-root", "repo_id": "model", "fqcn": root},
            {"java_type_occurrence_id": "type-child", "repo_id": "model", "fqcn": child},
        ],
        field_rows=[{
            "code_field_occurrence_id": "field-child", "repo_id": "model", "owner_fqcn": root,
            "field_name": "child", "declared_type": "Child", "container_kind": None,
            "element_type": "Child", "annotations_json": "[]", "model_exclusion_observed": False,
            "model_exclusion_annotations_json": "[]",
        }],
        inheritance_rows=[],
        type_reference_rows=[{
            "source_observation_occurrence_id": "ref-type", "repo_id": "model", "owner_fqcn": root,
            "member_name": "child", "reference_role": "field_type", "referenced_type": "Child",
            "resolved_fqcn": child, "candidate_fqcns_json": "[]",
        }],
        method_call_rows=[], argument_flow_rows=[], constructed_value_rows=[],
        tsa_reference_rows=[
            {"source_observation_occurrence_id": "tsa-ref-pojo", "repo_id": "converter",
             "owner_fqcn": converter, "owner_method": "convert", "method": "referenceField",
             "argument_expressions_json": '["child"]'},
            {"source_observation_occurrence_id": "tsa-ref-json", "repo_id": "converter",
             "owner_fqcn": converter, "owner_method": "convert", "method": "referenceField",
             "argument_expressions_json": '["child"]'},
        ],
        tsa_key_expression_rows=[{
            "source_observation_occurrence_id": "tsa-key", "repo_id": "converter",
            "owner_fqcn": converter, "owner_method": "convert",
            "key_expression": '"Root_" + id', "key_input_symbols_json": '["id"]',
        }],
    )
    relationships, expressions, _, _, _ = build_model_relationship_rows(**common)
    assert len(relationships) == 1
    assert len(expressions) == 1
    payload = json.loads(expressions[0][9])
    bindings = payload["observations"]
    assert {b["reference_operation_observation_id"] for b in bindings} == {"tsa-ref-pojo", "tsa-ref-json"}
    assert all(b["source_object_fqcn"] == root for b in bindings)
    assert all(b["target_type_fqcn"] == child for b in bindings)
    assert all(b["endpoint_key_observation_ids"] == ["key-root"] for b in bindings)


def test_converter_type_does_not_shadow_configured_model_name():
    root = "example.Root"
    child = "example.Child"
    converter = "example.RootToChangeVectorConverter"
    relationships, expressions, _, _, _ = build_model_relationship_rows(
        key_rows=[{"key_observation_id": "key-root", "repo_id": "model", "object_fqcn": root}],
        type_rows=[
            {"java_type_occurrence_id": "type-root", "repo_id": "model", "fqcn": root},
            {"java_type_occurrence_id": "type-child", "repo_id": "model", "fqcn": child},
            {"java_type_occurrence_id": "type-converter", "repo_id": "converter", "fqcn": converter},
        ],
        field_rows=[{
            "code_field_occurrence_id": "field-child", "repo_id": "model", "owner_fqcn": root,
            "field_name": "child", "declared_type": "Child", "container_kind": None,
            "element_type": "Child", "annotations_json": "[]", "model_exclusion_observed": False,
            "model_exclusion_annotations_json": "[]",
        }],
        inheritance_rows=[],
        type_reference_rows=[{
            "source_observation_occurrence_id": "field-ref", "repo_id": "model", "owner_fqcn": root,
            "member_name": "child", "reference_role": "field_type", "resolved_fqcn": child,
            "candidate_fqcns_json": "[]",
        }],
        method_call_rows=[], argument_flow_rows=[], constructed_value_rows=[],
        tsa_reference_rows=[{
            "source_observation_occurrence_id": "tsa-ref", "repo_id": "converter",
            "owner_fqcn": converter, "owner_operation": "RootToChangeVectorConverter.convert",
            "method": "referenceField", "argument_expressions_json": '["child", "refKey"]',
        }],
        tsa_key_expression_rows=[{
            "source_observation_occurrence_id": "tsa-key", "repo_id": "converter",
            "owner_fqcn": converter, "owner_operation": "RootToChangeVectorConverter.convert",
            "key_expression": '"Root_" + id', "key_input_symbols_json": '["id"]',
        }],
    )
    assert len(relationships) == 1
    assert relationships[0][2] == root
    assert relationships[0][18] == '["example.RootToChangeVectorConverter"]'
    assert len(expressions) == 1
    assert expressions[0][3] == '"Root_" + id'
