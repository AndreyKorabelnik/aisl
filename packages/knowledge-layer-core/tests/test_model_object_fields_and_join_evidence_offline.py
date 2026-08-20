from knowledge_layer_core.workspace_schema import DDL
from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery


def test_model_object_fields_view_combines_effective_fields_and_key_roles() -> None:
    block = DDL.split("CREATE VIEW v_model_object_fields", 1)[1].split("CREATE VIEW v_model_relationship_join_evidence", 1)[0]
    assert "effective_entity_field" in block
    assert "model_object_key_member" in block
    assert "f.inherited" in block
    assert "m.role_name AS key_role_name" in block


def test_join_evidence_view_exposes_observed_components_without_verdict() -> None:
    block = DDL.split("CREATE VIEW v_model_relationship_join_evidence", 1)[1].split("CREATE VIEW v_model_relationships", 1)[0].lower()
    assert "source_key_observation_count" in block
    assert "target_key_observation_count" in block
    assert "key_expression_count" in block
    assert "polymorphic_target_count" in block
    assert "key_expression_binding_count" in block
    assert "bound_reference_operation_count" in block
    for forbidden in ("joinable", "confidence", "verdict", "probability", "score"):
        assert forbidden not in block


def test_query_surface_exposes_fields_and_join_evidence() -> None:
    assert hasattr(WorkspaceKnowledgeQuery, "model_object_fields")
    assert hasattr(WorkspaceKnowledgeQuery, "model_relationship_join_evidence")


def test_expression_binding_view_exposes_reference_operation_and_endpoint_context() -> None:
    block = DDL.split("CREATE VIEW v_model_relationship_key_expression_bindings", 1)[1].split("CREATE VIEW v_model_relationship_join_evidence", 1)[0]
    assert "reference_operation_observation_id" in block
    assert "source_object_fqcn" in block
    assert "source_field_name" in block
    assert "target_type_fqcn" in block
    assert "endpoint_key_observation_ids_json" in block
    assert hasattr(WorkspaceKnowledgeQuery, "model_relationship_key_expression_bindings")
