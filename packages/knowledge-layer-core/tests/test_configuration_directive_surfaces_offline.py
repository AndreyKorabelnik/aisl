from knowledge_layer_core.workspace_evidence import TOOL_IDS
from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery
from knowledge_layer_core.workspace_schema import DDL, SCHEMA_VERSION


def test_configuration_directive_views_preserve_facts_without_verdicts() -> None:
    assert SCHEMA_VERSION == "workspace_data_model/v16"
    for view in (
        "v_model_configuration_directives",
        "v_model_configuration_directive_matches",
        "v_model_object_configuration_observations",
        "v_model_relationship_configuration_observations",
    ):
        assert f"CREATE VIEW {view}" in DDL
    block = DDL.split("CREATE VIEW v_model_configuration_directives", 1)[1].split(
        "CREATE VIEW v_tsa_reference_operations", 1
    )[0].lower()
    for required in (
        "configured_target_type",
        "configured_target_collection_type",
        "converter_instantiator",
        "directive_scope_kind",
        "sibling_configuration_entry_ids_json",
    ):
        assert required in block
    for forbidden in ("confidence", "verdict", "probability", "score", "published"):
        assert forbidden not in block


def test_effective_field_projection_and_configuration_queries_are_exposed() -> None:
    for method in (
        "model_configuration_directives",
        "model_configuration_directive_matches",
        "model_object_configuration",
        "model_object_fields",
        "model_relationship_join_evidence",
    ):
        assert hasattr(WorkspaceKnowledgeQuery, method)
    for tool in (
        "workspace_data_model_model_configuration_directives",
        "workspace_data_model_model_configuration_directive_matches",
        "workspace_data_model_model_object_configuration",
        "workspace_data_model_model_object_fields",
        "workspace_data_model_model_relationship_join_evidence",
    ):
        assert tool in TOOL_IDS
