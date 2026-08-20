from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

SYSTEM_PREFIX = "/api/knowledge/v1/systems/{system_id}"


def _q(name: str | None = None, transform: str = "identity") -> dict[str, str]:
    return {"location": "query", "name": name or "", "transform": transform}


def _p(name: str | None = None) -> dict[str, str]:
    return {"location": "path", "name": name or "", "transform": "url_segment"}


def _b(name: str | None = None, transform: str = "identity") -> dict[str, str]:
    return {"location": "body", "name": name or "", "transform": transform}


def get(path: str, *, args: Mapping[str, Mapping[str, str]] | None = None, fixed_query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "binding_kind": "knowledge_api_http",
        "method": "GET",
        "path_template": SYSTEM_PREFIX + path,
        "revision_binding": {"location": "query", "name": "revision_id", "value_from": "scope.revision_id"},
        "expected_schema_versions": ["knowledge_api/v1"],
        "arguments": {k: dict(v) for k, v in (args or {}).items()},
        "fixed_query": dict(fixed_query or {}),
    }


def post(path: str, *, args: Mapping[str, Mapping[str, str]] | None = None, fixed_body: Mapping[str, Any] | None = None, revision_location: str = "query") -> dict[str, Any]:
    binding: dict[str, Any] = {
        "binding_kind": "knowledge_api_http",
        "method": "POST",
        "path_template": SYSTEM_PREFIX + path,
        "arguments": {k: dict(v) for k, v in (args or {}).items()},
        "expected_schema_versions": ["knowledge_api/v1"],
        "fixed_body": deepcopy(dict(fixed_body or {})),
    }
    binding["revision_binding"] = {"location": revision_location, "name": "revision_id", "value_from": "scope.revision_id"}
    return binding


def wrapped_query(path: str, query_kind: str, *, filters: Mapping[str, str | tuple[str, str]] | None = None, extra_args: Mapping[str, Mapping[str, str]] | None = None) -> dict[str, Any]:
    args: dict[str, Mapping[str, str]] = {
        "max_results": {"location": "body", "name": "max_results", "transform": "bounded_int"}
    }
    for tool_arg, spec in (filters or {}).items():
        if isinstance(spec, tuple):
            target, transform = spec
        else:
            target, transform = spec, "identity"
        args[tool_arg] = {"location": "body_filter", "name": target, "transform": transform}
    args.update(extra_args or {})
    return post(
        path,
        args=args,
        fixed_body={"query_kind": query_kind},
        revision_location="body",
    )


TOOL_API_BINDINGS: dict[str, dict[str, Any]] = {
    # Context is embedded in the Integration Profile itself and is not an external HTTP tool.
    "get_knowledge_context": {
        "binding_kind": "profile_context",
        "external_exposure": False,
        "value_from": ["scope", "capabilities", "knowledge_artifacts", "generated_from"],
    },
    "get_knowledge_item": get(
        "/knowledge-items/{artifact_id}/{item_kind}/{local_id}",
        args={
            "artifact_id": _p("artifact_id"),
            "item_kind": _p("item_kind"),
            "local_id": _p("local_id"),
        },
    ),
    "get_analysis_coverage": get("/coverage"),
    "search_data_objects": get("/data-model/tables", args={"search": _q("search"), "table_kind": _q("table_kind"), "include_fields": _q("include_fields", "bool"), "offset": _q("offset", "bounded_int"), "limit": _q("limit", "bounded_int")}),
    "get_data_object": get("/data-model/tables/{table_id}", args={"object_id": _p("table_id")}),
    "get_data_object_relationship": get("/data-model/tables/{table_id}/relationships/{relationship_id}", args={"object_id": _p("table_id"), "relationship_id": _p("relationship_id")}),
    "get_declared_data_model_summary": get("/data-model/declared-summary", args={"repo_id": _q("repo_id"), "type_annotations": _q("type_annotations", "csv"), "exclude_field_annotations": _q("exclude_field_annotations", "csv")}),
    "search_declared_data_objects": get("/data-model/declared-objects", args={"repo_id": _q("repo_id"), "search": _q("search"), "type_annotations": _q("type_annotations", "csv"), "include_fields": _q("include_fields", "bool"), "offset": _q("offset", "bounded_int"), "limit": _q("limit", "bounded_int")}),
    "get_declared_data_object": get("/data-model/declared-objects/{object_id}", args={"object_id": _p("object_id")}),
    "get_data_model_object_context": get("/data-model/object-context/{object_id}", args={"object_id": _p("object_id")}),
    "get_data_model_attribute_extension_context": get("/data-model/attribute-extension-guidance", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["source_type", "source_field", "target_type", "join_method", "confidence", "sql_generation_status", "search", "offset", "limit"]}),
    "get_reference_data_context": get(
        "/reference-data/guidance",
        args={"token": _q("token")},
        fixed_query={
            "candidate_limit": 200,
            "local_definition_limit": 12,
            "literal_write_limit": 12,
            "usage_limit": 16,
            "gap_limit": 12,
            "evidence_limit": 40,
        },
    ),
    "search_reference_data": wrapped_query("/reference-data/query", "search_reference_data", filters={"token": "token", "include_non_production": ("include_non_production", "bool")}),
    "get_reference_data_object": wrapped_query("/reference-data/query", "get_reference_data_object", filters={"object_id": "object_id"}),
    "get_reference_data_candidate_context": wrapped_query("/reference-data/query", "get_candidate_context", filters={"token": "token", "include_non_production": ("include_non_production", "bool")}),
    "list_declared_value_sets": wrapped_query("/reference-data/query", "list_declared_value_sets", filters={"token": "token", "source_sets": ("source_sets", "list"), "include_values": ("include_values", "bool")}),
    "list_reference_literal_writes": wrapped_query("/reference-data/query", "list_literal_writes", filters={"token": "token"}),
    "get_reference_usage_observations": wrapped_query("/reference-data/query", "get_usage_observations", filters={"token": "token"}),
    "get_reference_data_gaps": wrapped_query("/reference-data/query", "get_gap_summary", filters={"token": "token"}),
    "get_reference_data_landscape": wrapped_query("/reference-data/query", "get_landscape", filters={"token": "token"}),
    "get_fdp_context": get(
        "/foreign-data-persistence/guidance",
        args={"token": _q("token")},
        fixed_query={"path_limit": 12, "case_limit": 12, "storage_summary_limit": 12, "evidence_limit": 40},
    ),
    "list_fdp_paths": wrapped_query("/foreign-data-persistence/query", "list_paths", filters={"direction": "direction", "token": "token"}),
    "get_fdp_path": post("/foreign-data-persistence/query", args={"path_id": {"location": "body_filter", "name": "path_id", "transform": "identity"}}, fixed_body={"query_kind": "get_path", "max_results": 100}, revision_location="body"),
    "list_fdp_cases": wrapped_query("/foreign-data-persistence/query", "list_mechanical_cases", filters={"token": "token"}),
    "get_fdp_landscape": wrapped_query("/foreign-data-persistence/query", "get_landscape", filters={"token": "token"}),
    "list_system_interactions": get("/interactions", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["source_repo_id", "target_repo_id", "protocol", "offset", "limit"]}),
    "get_system_interaction_context": get("/interactions/{interaction_id}/guidance", args={"interaction_id": _p("interaction_id")}, fixed_query={"context_limit": 8, "field_limit": 20}),
    "list_interaction_boundaries": get("/interactions/boundaries", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["repo_id", "project_id", "direction", "protocol", "http_method", "service_identity", "offset", "limit"]}),
    "list_interaction_execution_contexts": get("/interactions/execution-contexts", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["boundary_interaction_id", "interaction_id", "source_repo_id", "trigger_kind", "path_status", "offset", "limit"]}),
    "list_interaction_field_contracts": get("/interactions/field-contracts", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["boundary_interaction_id", "interaction_id", "source_repo_id", "target_repo_id", "wire_path", "match_status", "offset", "limit"]}),
    "list_interaction_diagnostics": get("/interactions/diagnostics", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["source_repo_id", "match_status", "offset", "limit"]}),
    "list_interaction_coverage": get("/interactions/coverage", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["repo_id", "project_id", "coverage_status", "matching_coverage_status", "offset", "limit"]}),
    "get_system_description_context": get(
        "/system-description/guidance",
        fixed_query={
            "technology_limit": 12,
            "interface_limit": 12,
            "integration_limit": 8,
            "event_limit": 8,
            "storage_limit": 10,
            "journey_limit": 8,
            "gap_limit": 20,
        },
    ),
    "get_system_scope_overview": wrapped_query("/system-description/query", "get_scope_overview"),
    "get_system_repository_composition": wrapped_query("/system-description/query", "get_repository_composition"),
    "get_system_technologies": wrapped_query("/system-description/query", "get_technologies"),
    "list_system_interfaces": wrapped_query("/system-description/query", "list_interfaces", filters={"direction": "direction", "boundary_kinds": ("boundary_kinds", "list"), "include_test": ("include_test", "bool")}),
    "list_system_integrations": wrapped_query("/system-description/query", "list_integrations"),
    "list_system_events": wrapped_query("/system-description/query", "list_events"),
    "list_system_storage_targets": wrapped_query("/system-description/query", "list_data_objects", filters={"representative": ("representative", "bool")}),
    "get_system_description_coverage": wrapped_query("/system-description/query", "get_analysis_coverage"),
    "get_system_description_gaps": wrapped_query("/system-description/query", "get_gap_summary"),
    "get_system_representative_journeys": wrapped_query("/system-description/query", "get_representative_journeys"),
    "search_physical_model_tables": get("/physical-model/tables", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "bool" if name == "include_columns" else "identity") for name in ["search", "source_id", "include_columns", "offset", "limit"]}),
    "get_physical_model_table": get("/physical-model/tables/{table_id}", args={"table_id": _p("table_id")}),
    "list_physical_model_relationships": get("/physical-model/relationships", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["table_id", "direction", "source_id", "resolution_status", "search", "offset", "limit"]}),
    "list_physical_model_gaps": get("/physical-model/gaps", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["source_id", "gap_kind", "search", "offset", "limit"]}),
    "resolve_attribute_path": post("/attribute-paths/resolve", args={name: _b(name, "list" if name in {"selected_repo_ids"} else "bounded_int" if name in {"max_hops", "max_paths"} else "identity") for name in ["source", "target", "selected_repo_ids", "knowledge_view", "minimum_confidence", "max_hops", "max_paths"]}, fixed_body={"max_branching": 20, "allowed_edge_kinds": []}, revision_location="query"),
    "list_observed_storage_accesses": get("/storage-usage/accesses", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["repo_id", "access_kind", "storage_kind", "target_resolution_status", "search", "offset", "limit"]}),
    "list_observed_storage_gaps": get("/storage-usage/gaps", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["repo_id", "gap_code", "severity", "search", "offset", "limit"]}),
    "list_used_source_tables_and_fields": get("/sql/source-inventory", args={"repo_id": _q("repo_id"), "search": _q("search"), "usage_role": _q("usage_role"), "max_evidence_per_role": _q("max_evidence_per_role", "bounded_int")}, fixed_query={"view": "business_sources"}),
    "get_sql_field_calculation": get("/sql/field-calculation", args={"target_relation": _q("target_relation"), "target_column": _q("target_column"), "repo_id": _q("repo_id"), "include_gaps": _q("include_gaps", "bool"), "max_gaps": _q("max_gaps", "bounded_int")}),
    "get_workspace_sql_catalog": get("/sql/workspace-catalog"),
    "find_sql_target_candidates": get("/sql/target-candidates", args={"repo_id": _q("repo_id"), "source_relation_hints": _q("source_relation", "list"), "source_column_hints": _q("source_column", "list"), "business_entity_hints": _q("business_entity", "list"), "limit": _q("limit", "bounded_int")}),
    "get_sql_attribute_insertion_context": post("/sql/attribute-insertion-context", args={"target_relation": _b("target_relation"), "repo_id": _b("repo_id"), "source_relation_hints": _b("source_relation_hints", "list"), "source_column_hints": _b("source_column_hints", "list"), "max_results": _b("max_results", "bounded_int")}, revision_location="query"),
    "list_sql_relation_materializations": get("/sql/relation-materializations", args={name: _q(name, "bounded_int" if name in {"offset", "limit"} else "identity") for name in ["output_table_name", "query_id", "workflow_context_file", "offset", "limit"]}),
    "get_sql_query_context": get("/sql/query-context", args={"repo_id": _q("repo_id"), "query_id": _q("query_id"), "scope_id": _q("scope_id")}),
    "get_sql_column_usage_context": get("/sql/column-usages/{sql_column_usage_id}", args={"sql_column_usage_id": _p("sql_column_usage_id")}),
    "get_sql_target_column_lineage": get("/sql/target-column-lineage", args={name: _q(name, "bool" if name == "include_gaps" else "bounded_int" if name in {"max_gaps", "offset", "limit"} else "identity") for name in ["target_relation", "target_column", "repo_id", "lineage_status", "include_gaps", "max_gaps", "offset", "limit"]}),
}


TOOL_API_BINDINGS["get_data_model_object_context"]["expected_schema_versions"] = ["data_model_object_context/v2"]
TOOL_API_BINDINGS["resolve_attribute_path"]["expected_schema_versions"] = ["knowledge_attribute_path_query/v1"]


def binding(tool_name: str) -> dict[str, Any]:
    if tool_name not in TOOL_API_BINDINGS:
        raise KeyError(f"missing Knowledge API binding for integration tool: {tool_name}")
    return deepcopy(TOOL_API_BINDINGS[tool_name])


def external_tool_names() -> set[str]:
    return {
        name for name, value in TOOL_API_BINDINGS.items()
        if value.get("external_exposure", True) and value.get("binding_kind") == "knowledge_api_http"
    }
_OPERATION_IDS: dict[str, str] = {
    'get_knowledge_item': 'get_aisl_knowledge_item_api_knowledge_v1_systems__system_id__knowledge_items__artifact_id___item_kind___local_id__get',
    'find_sql_target_candidates': 'find_sql_target_candidates_api_knowledge_v1_systems__system_id__sql_target_candidates_get',
    'get_analysis_coverage': 'analysis_coverage_api_knowledge_v1_systems__system_id__coverage_get',
    'get_data_model_attribute_extension_context': 'get_attribute_extension_guidance_api_knowledge_v1_systems__system_id__data_model_attribute_extension_guidance_get',
    'get_data_object': 'get_table_api_knowledge_v1_systems__system_id__data_model_tables__table_id__get',
    'get_data_object_relationship': 'get_relationship_api_knowledge_v1_systems__system_id__data_model_tables__table_id__relationships__relationship_id__get',
    'get_declared_data_model_summary': 'summarize_declared_data_model_api_knowledge_v1_systems__system_id__data_model_declared_summary_get',
    'get_declared_data_object': 'get_declared_data_object_api_knowledge_v1_systems__system_id__data_model_declared_objects__object_id__get',
    'get_data_model_object_context': 'get_data_model_object_context_api_knowledge_v1_systems__system_id__data_model_object_context__object_id__get',
    'get_fdp_context': 'get_foreign_data_persistence_guidance_api_knowledge_v1_systems__system_id__foreign_data_persistence_guidance_get',
    'get_fdp_landscape': 'query_foreign_data_persistence_api_knowledge_v1_systems__system_id__foreign_data_persistence_query_post',
    'get_fdp_path': 'query_foreign_data_persistence_api_knowledge_v1_systems__system_id__foreign_data_persistence_query_post',
    'get_physical_model_table': 'get_physical_model_table_api_knowledge_v1_systems__system_id__physical_model_tables__table_id__get',
    'get_reference_data_context': 'get_reference_data_guidance_api_knowledge_v1_systems__system_id__reference_data_guidance_get',
    'get_reference_data_candidate_context': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'get_reference_data_gaps': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'get_reference_data_landscape': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'get_reference_data_object': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'get_reference_usage_observations': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'get_sql_attribute_insertion_context': 'resolve_sql_attribute_insertion_context_api_knowledge_v1_systems__system_id__sql_attribute_insertion_context_post',
    'get_sql_column_usage_context': 'get_sql_column_usage_context_api_knowledge_v1_systems__system_id__sql_column_usages__sql_column_usage_id__get',
    'get_sql_field_calculation': 'get_sql_field_calculation_api_knowledge_v1_systems__system_id__sql_field_calculation_get',
    'get_sql_query_context': 'get_sql_query_context_api_knowledge_v1_systems__system_id__sql_query_context_get',
    'get_sql_target_column_lineage': 'list_sql_target_column_lineage_api_knowledge_v1_systems__system_id__sql_target_column_lineage_get',
    'get_system_description_coverage': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_system_description_gaps': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_system_interaction_context': 'get_system_interaction_guidance_api_knowledge_v1_systems__system_id__interactions__interaction_id__guidance_get',
    'get_system_repository_composition': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_system_representative_journeys': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_system_description_context': 'get_system_description_guidance_api_knowledge_v1_systems__system_id__system_description_guidance_get',
    'get_system_scope_overview': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_system_technologies': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'get_workspace_sql_catalog': 'get_workspace_sql_catalog_api_knowledge_v1_systems__system_id__sql_workspace_catalog_get',
    'list_declared_value_sets': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'list_fdp_cases': 'query_foreign_data_persistence_api_knowledge_v1_systems__system_id__foreign_data_persistence_query_post',
    'list_fdp_paths': 'query_foreign_data_persistence_api_knowledge_v1_systems__system_id__foreign_data_persistence_query_post',
    'list_interaction_boundaries': 'list_repository_interaction_boundaries_api_knowledge_v1_systems__system_id__interactions_boundaries_get',
    'list_interaction_coverage': 'list_repository_interaction_coverage_api_knowledge_v1_systems__system_id__interactions_coverage_get',
    'list_interaction_diagnostics': 'list_system_interaction_diagnostics_api_knowledge_v1_systems__system_id__interactions_diagnostics_get',
    'list_interaction_execution_contexts': 'list_system_interaction_execution_contexts_api_knowledge_v1_systems__system_id__interactions_execution_contexts_get',
    'list_interaction_field_contracts': 'list_system_interaction_field_contracts_api_knowledge_v1_systems__system_id__interactions_field_contracts_get',
    'list_observed_storage_accesses': 'list_observed_storage_accesses_api_knowledge_v1_systems__system_id__storage_usage_accesses_get',
    'list_observed_storage_gaps': 'list_observed_storage_gaps_api_knowledge_v1_systems__system_id__storage_usage_gaps_get',
    'list_physical_model_gaps': 'list_physical_model_gaps_api_knowledge_v1_systems__system_id__physical_model_gaps_get',
    'list_physical_model_relationships': 'list_physical_model_relationships_api_knowledge_v1_systems__system_id__physical_model_relationships_get',
    'list_reference_literal_writes': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
    'list_sql_relation_materializations': 'list_sql_relation_materializations_api_knowledge_v1_systems__system_id__sql_relation_materializations_get',
    'list_system_events': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'list_system_integrations': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'list_system_interactions': 'list_system_interactions_api_knowledge_v1_systems__system_id__interactions_get',
    'list_system_interfaces': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'list_system_storage_targets': 'query_system_description_api_knowledge_v1_systems__system_id__system_description_query_post',
    'list_used_source_tables_and_fields': 'export_sql_source_inventory_api_knowledge_v1_systems__system_id__sql_source_inventory_get',
    'resolve_attribute_path': 'resolve_attribute_paths_api_knowledge_v1_systems__system_id__attribute_paths_resolve_post',
    'search_data_objects': 'list_tables_api_knowledge_v1_systems__system_id__data_model_tables_get',
    'search_declared_data_objects': 'list_declared_data_objects_api_knowledge_v1_systems__system_id__data_model_declared_objects_get',
    'search_physical_model_tables': 'list_physical_model_tables_api_knowledge_v1_systems__system_id__physical_model_tables_get',
    'search_reference_data': 'query_reference_data_api_knowledge_v1_systems__system_id__reference_data_query_post',
}

for _tool_name, _operation_id in _OPERATION_IDS.items():
    TOOL_API_BINDINGS[_tool_name]["operation_id"] = _operation_id
