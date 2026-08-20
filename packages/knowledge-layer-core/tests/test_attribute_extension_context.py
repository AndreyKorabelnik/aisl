from __future__ import annotations

from knowledge_layer_core.attribute_extension_context_builder import (
    _classify_join,
    _structural_correspondences,
    _usefulness_classification,
)
from knowledge_layer_core.key_expression_correspondence import canonical_key_expression_node, infer_key_fields_from_expression_tree
from knowledge_layer_core.materialization_contracts import CURRENT_MATERIALIZATIONS


def _payload(properties: dict) -> str:
    import json
    return json.dumps({"properties": properties, "source_refs": []})


def _tree_country(receiver: str) -> dict:
    return {
        "node_type": "binary_expression", "operator": "+", "children": [
            {"field": "left", "node_type": "string_literal", "value": '"Country_"', "children": [{"node_type": "string_fragment", "value": "Country_"}]},
            {"field": "operator", "node_type": "+", "value": "+"},
            {"field": "right", "node_type": "method_invocation", "children": [
                {"field": "object", "node_type": "identifier", "value": receiver},
                {"field": "name", "node_type": "identifier", "value": "getCode"},
                {"field": "arguments", "node_type": "argument_list", "value": "()"},
            ]},
        ],
    }


def test_shared_expression_correspondence_ignores_receiver_only_for_observed_field() -> None:
    left = _tree_country("birthPlaceCountry")
    right = _tree_country("country")
    assert infer_key_fields_from_expression_tree(right) == ("code",)
    assert canonical_key_expression_node(left, ("code",)) == canonical_key_expression_node(right, ("code",))
    assert canonical_key_expression_node(left, ("id",)) is None


def test_join_classifier_preserves_direct_single_reference_as_equals_without_structural_match() -> None:
    storage = [{
        "storage_relation_kind": "single_reference",
        "target_alias": "example.BirthPlace",
        "target_alignment": "exact_declared_target",
        "payload_json": _payload({"reference_operation": "referenceField", "target_storage_key_expression": "parentKey + '.birthPlace'"}),
    }]
    method, confidence, status, basis, diagnostics = _classify_join(
        declared_target_fqcn="example.BirthPlace", storage_relationships=storage,
        derivations=[{"composed_reference_value_expression": "key"}],
        target_records=[{"storage_key_expression": "parentKey + '.birthPlace'"}],
        structural_correspondences=[],
    )
    assert (method, confidence) == ("equals", "confirmed")
    assert status == "direct_candidate_requires_physical_representation_check"
    assert basis["kind"] == "exact_single_reference_to_declared_target"
    assert diagnostics == []


def test_join_classifier_derives_parent_identity_for_collection_key() -> None:
    storage = [{
        "storage_relation_kind": "collection_reference", "target_alias": "example.Emigration",
        "target_alignment": "exact_declared_target",
        "payload_json": _payload({
            "reference_operation": "replaceReferenceCollection",
            "source_key_passed_into_target_key": True,
            "composed_target_key_expression": '"Individual_" + id + ".emigrations_" + childId',
        }),
    }]
    method, confidence, status, basis, _ = _classify_join(
        declared_target_fqcn="example.Emigration", storage_relationships=storage,
        derivations=[], target_records=[], structural_correspondences=[],
    )
    assert (method, confidence, status) == ("derive_source_identity_from_target_key", "confirmed", "transformation_required")
    assert basis["source_key_passed_into_target_key"] is True


def test_join_classifier_uses_exact_structural_reference_key_correspondence() -> None:
    derivation = {
        "observation_id": "ref-1", "composed_reference_value_expression": '"Country_" + birthPlace.getCountry().getCode()',
        "payload_json": _payload({"composed_reference_value_expression_tree": _tree_country("birthPlaceCountry")}),
    }
    target = {
        "observation_id": "key-1", "storage_key_expression": '"Country_" + country.getCode()',
        "payload_json": _payload({"storage_key_expression_tree": _tree_country("country")}),
    }
    matches = _structural_correspondences([derivation], [target])
    assert len(matches) == 1
    assert matches[0]["match_basis"] == "exact_structural_expression_signature"
    assert matches[0]["target_key_fields"] == ["code"]
    method, confidence, status, basis, diagnostics = _classify_join(
        declared_target_fqcn="example.Country", storage_relationships=[], derivations=[derivation],
        target_records=[target], structural_correspondences=matches,
    )
    assert (method, confidence, status) == ("resolve_reference_value_to_target_key", "confirmed", "transformation_required")
    assert basis["kind"] == "exact_structural_reference_value_to_target_key"
    assert diagnostics == []


def test_join_classifier_keeps_polymorphic_collection_sql_unresolved() -> None:
    storage = [
        {"storage_relation_kind": "collection_reference", "target_alias": target, "target_alignment": "observed_inherited_specialization",
         "payload_json": _payload({"reference_operation": "replacePolymorphicReferenceCollection", "source_key_passed_into_target_key": True, "composed_target_key_expression": "parent.key"})}
        for target in ("example.Passport", "example.Inn")
    ]
    method, confidence, status, basis, diagnostics = _classify_join(
        declared_target_fqcn="example.AbstractIdentification", storage_relationships=storage,
        derivations=[], target_records=[], structural_correspondences=[],
    )
    assert (method, confidence) == ("resolve_reference_collection", "confirmed")
    assert status == "unresolved_requires_subtype_or_representation"
    assert sorted(basis["observed_concrete_targets"]) == ["example.Inn", "example.Passport"]
    assert diagnostics[0]["code"] == "physical_join_not_established_for_polymorphic_collection"


def test_materialization_contract_exposes_attribute_extension_context() -> None:
    contract = next(item for item in CURRENT_MATERIALIZATIONS if item.materialization_id == "data-model-attribute-extension-context")
    assert contract.produced_models == ("data-model-attribute-extension-context/v1",)
    assert "common.data-model-agent-join-semantics" in contract.capabilities
    assert {item.source_materialization_id for item in contract.required_knowledge_models} == {
        "code-declared-data-model", "model-storage-semantics", "logical-storage-mapping",
        "cross-artifact-data-model-mapping", "sql-analysis",
    }


def test_storage_reference_field_observations_preserve_observed_name_and_provenance() -> None:
    from knowledge_layer_core.attribute_extension_context_builder import _storage_reference_field_observations

    rows = [{
        "observation_id": "obs-region",
        "repo_id": "tsa",
        "api_framework": "tsa_change_vector",
        "source_owner_fqcn": "example.Converter",
        "source_operation": "Converter.convertBirthPlace",
        "source_alias": "example.BirthPlace",
        "relationship_field": "regionCode",
        "reference_operation": "referenceField",
        "value_converter_operation": "Converter.convertRegion",
        "composed_reference_value_expression": '"Region_" + region.getCode()',
        "source_refs_json": '[{"repository_relative_path":"Converter.java","line_start":42,"line_end":42}]',
        "payload_json": _payload({}),
    }]
    result = _storage_reference_field_observations(rows)
    assert result == [{
        "evidence_kind": "observed_storage_reference_field",
        "observation_id": "obs-region",
        "repo_id": "tsa",
        "api_framework": "tsa_change_vector",
        "source_owner_fqcn": "example.Converter",
        "source_operation": "Converter.convertBirthPlace",
        "source_alias": "example.BirthPlace",
        "storage_reference_field_name": "regionCode",
        "reference_operation": "referenceField",
        "value_converter_operation": "Converter.convertRegion",
        "reference_value_expression": '"Region_" + region.getCode()',
        "source_refs": [{"repository_relative_path": "Converter.java", "line_start": 42, "line_end": 42}],
    }]


def test_sql_join_example_relevance_distinguishes_exact_join_from_target_key_analog() -> None:
    from knowledge_layer_core.attribute_extension_context_builder import _annotate_sql_join_examples

    source_anchor = {
        "observed_sql_relations": [{"sql_relation_id": "birth-place"}],
        "observed_field_usages": [],
    }
    target_anchor = {
        "observed_sql_relations": [{"sql_relation_id": "region"}],
        "observed_field_usages": [],
    }
    observations = [{"storage_reference_field_name": "regionCode"}]
    analog = {
        "sql_join_edge_id": "analog",
        "file": "analog.sql",
        "line_start": 10,
        "participating_relation_ids": ["address", "region"],
        "left_relation_id": "address",
        "right_relation_id": "region",
        "column_pairs": [{
            "left_relation_id": "address", "left_column": "regioncode", "left_column_usage_id": "u-address",
            "right_relation_id": "region", "right_column": "key", "right_column_usage_id": "u-region-key",
        }],
    }
    exact = {
        "sql_join_edge_id": "exact",
        "file": "birth.sql",
        "line_start": 20,
        "participating_relation_ids": ["birth-place", "region"],
        "left_relation_id": "birth-place",
        "right_relation_id": "region",
        "column_pairs": [{
            "left_relation_id": "birth-place", "left_column": "regioncode", "left_column_usage_id": "u-birth-region",
            "right_relation_id": "region", "right_column": "key", "right_column_usage_id": "u-region-key-2",
        }],
    }
    result = _annotate_sql_join_examples(
        [analog, exact], source_field="regionCode", source_anchor=source_anchor, target_anchor=target_anchor,
        target_key_fields=["key"], storage_field_observations=observations,
    )
    assert [item["sql_join_edge_id"] for item in result] == ["exact", "analog"]
    assert result[0]["relationship_relevance"] == "exact_source_field_to_target_key"
    assert result[0]["relationship_relevance_basis"]["exact_column_pair_match"] is True
    assert result[0]["relationship_relevance_basis"]["source_field_match_basis"] == [
        "source_relation_column_matches_storage_reference_field"
    ]
    assert result[1]["relationship_relevance"] == "target_key_analog"
    assert result[1]["relationship_relevance_basis"]["source_field_usage_match"] is False
    assert result[1]["relationship_relevance_basis"]["target_key_usage_match"] is True


def test_sql_join_example_relevance_preserves_related_target_relation_as_analog() -> None:
    from knowledge_layer_core.attribute_extension_context_builder import _annotate_sql_join_examples

    result = _annotate_sql_join_examples(
        [{
            "sql_join_edge_id": "timezone",
            "file": "phone.sql",
            "line_start": 30,
            "participating_relation_ids": ["region", "timezone"],
            "left_relation_id": "region",
            "right_relation_id": "timezone",
            "column_pairs": [{
                "left_relation_id": "region", "left_column": "timezone", "left_column_usage_id": "u-timezone",
                "right_relation_id": "timezone", "right_column": "key", "right_column_usage_id": "u-key",
            }],
        }],
        source_field="regionCode",
        source_anchor={"observed_sql_relations": [{"sql_relation_id": "birth-place"}], "observed_field_usages": []},
        target_anchor={"observed_sql_relations": [{"sql_relation_id": "region"}], "observed_field_usages": []},
        target_key_fields=["key"],
        storage_field_observations=[{"storage_reference_field_name": "regionCode"}],
    )
    assert result[0]["relationship_relevance"] == "target_relation_analog"
    assert result[0]["relationship_relevance_basis"]["target_relation_match"] is True
    assert result[0]["relationship_relevance_basis"]["target_key_usage_match"] is False


def test_usefulness_classification_calibrates_exact_analog_collection_and_polymorphic() -> None:
    exact = _usefulness_classification(
        join_method="resolve_reference_value_to_target_key", relationship_confidence="confirmed",
        sql_generation_status="transformation_required", cardinality="one", polymorphic=False,
        concrete_targets=[],
        basis={
            "exact_relationship_sql_join_observed": True,
            "source_relationship_field_observed_in_sql": True,
            "source_storage_field_observation_count": 2,
        },
        source_object_observed_in_sql=True, target_object_observed_in_sql=True,
    )
    assert exact["classification"] == "confirmed"
    assert exact["claim_kind"] == "existing_sql_join"
    assert exact["recommended_action"] == "reuse_observed_sql_join"

    analog = _usefulness_classification(
        join_method="resolve_reference_value_to_target_key", relationship_confidence="confirmed",
        sql_generation_status="transformation_required", cardinality="one", polymorphic=False,
        concrete_targets=[],
        basis={
            "exact_relationship_sql_join_observed": False,
            "source_relationship_field_observed_in_sql": False,
            "source_storage_field_observation_count": 3,
        },
        source_object_observed_in_sql=True, target_object_observed_in_sql=True,
    )
    assert analog["classification"] == "strongly_supported"
    assert analog["claim_kind"] == "proposed_sql_join"
    assert "confirm_source_sql_column_or_projection" in analog["residual_checks"]

    collection = _usefulness_classification(
        join_method="derive_source_identity_from_target_key", relationship_confidence="confirmed",
        sql_generation_status="transformation_required", cardinality="many", polymorphic=False,
        concrete_targets=[],
        basis={
            "exact_relationship_sql_join_observed": False,
            "source_relationship_field_observed_in_sql": False,
            "source_storage_field_observation_count": 0,
        },
        source_object_observed_in_sql=True, target_object_observed_in_sql=True,
    )
    assert collection["classification"] == "strongly_supported"
    assert collection["claim_kind"] == "collection_storage_navigation"
    assert collection["row_multiplicity"] == "many"
    assert collection["recommended_action"] == "derive_parent_identity_from_child_storage_key"

    polymorphic = _usefulness_classification(
        join_method="resolve_reference_collection", relationship_confidence="confirmed",
        sql_generation_status="unresolved_requires_subtype_or_representation", cardinality="many", polymorphic=True,
        concrete_targets=["example.Passport", "example.Inn"],
        basis={
            "exact_relationship_sql_join_observed": False,
            "source_relationship_field_observed_in_sql": False,
            "source_storage_field_observation_count": 0,
        },
        source_object_observed_in_sql=True, target_object_observed_in_sql=False,
    )
    assert polymorphic["classification"] == "ambiguity"
    assert polymorphic["claim_kind"] == "polymorphic_collection_navigation"
    assert polymorphic["candidate_targets"] == ["example.Passport", "example.Inn"]
    assert polymorphic["recommended_action"] == "select_concrete_target_or_representation_before_sql"
