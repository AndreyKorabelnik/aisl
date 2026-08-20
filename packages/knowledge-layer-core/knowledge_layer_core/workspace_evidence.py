from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery


def _tool(command_id: str, description: str, required: list[str], optional: list[str]) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "description": description,
        "required_args": ["workspace_path", *required],
        "optional_args": optional,
        "workspace_knowledge_scoped": True,
        "analysis_mode": "data-model",
        "strict_arguments": True,
    }


TOOLS = [
    _tool("workspace_data_model_overview", "Return deterministic workspace data-model counts and selected repositories.", [], []),
    _tool("workspace_data_model_source_observations", "Search compact universal source observations imported from repository evidence. Results remain syntax/configuration facts and carry no domain classification, confidence, status or join verdict.", [], ["token", "repo_id", "fact_type", "owner_fqcn", "target_method", "max_results", "page_token"]),
    _tool("workspace_data_model_source_observation_detail", "Return one full universal source observation, including its original payload and evidence location, without semantic interpretation.", ["observation_id"], []),
    _tool("workspace_data_model_code_types", "Search observed Java type declarations with stable pagination. Results preserve syntax facts and do not classify types as tables, roots, nested objects or dictionaries.", [], ["token", "repo_id", "class_kind", "annotation", "max_results", "page_token"]),
    _tool("workspace_data_model_code_fields", "Search observed code fields independently of conceptual entity classification; field annotations and container/element types are preserved as facts.", [], ["token", "repo_id", "owner_fqcn", "max_results", "page_token"]),
    _tool("workspace_data_model_code_annotations", "Search observed code annotations and structured arguments; annotation meaning is not assigned by WKL.", [], ["token", "repo_id", "owner_fqcn", "max_results", "page_token"]),
    _tool("workspace_data_model_configuration_entries", "Search structured configuration paths, node kinds and scalar/list values without interpreting project-specific configuration semantics.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_configuration_observations", "Search all configuration evidence forms: flattened entries, grouped mapping objects, lexical references and source comments. Full source payloads are preserved and no publication, key or relationship verdict is assigned.", [], ["token", "repo_id", "fact_type", "max_results", "page_token"]),
    _tool("workspace_data_model_model_configuration_directives", "Return normalized excluded-field, excluded-type, custom-field and custom-converter directives with mechanically paired sibling values and provenance; no field is removed and no publication verdict is assigned.", [], ["token", "directive_kind", "object_id", "field_name", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_model_configuration_directive_matches", "Return exact configuration-directive correspondences to observed model objects and effective fields, preserving unmatched directives separately.", [], ["directive_kind", "object_id", "field_name", "match_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_model_object_configuration", "Return model objects with observed configured type-exclusion directives; the object remains queryable and no exclusion verdict is applied by WKL.", [], ["object_id", "repo_id", "excluded_only"]),
    _tool("workspace_data_model_artifact_dependencies", "Search source-declared artifact dependency coordinates imported from repository evidence.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_method_calls", "Search observed method calls, receivers and owner methods without classifying APIs or repository roles.", [], ["token", "repo_id", "owner_fqcn", "target_method", "max_results", "page_token"]),
    _tool("workspace_data_model_call_argument_flows", "Search observed values flowing into call arguments, preserving expression and provenance without assigning business meaning.", [], ["token", "repo_id", "owner_fqcn", "target_method", "max_results", "page_token"]),
    _tool("workspace_data_model_constructed_values", "Search observed assignments and constructed expressions, including input symbols and AST payload through detail lookup.", [], ["token", "repo_id", "owner_fqcn", "max_results", "page_token"]),
    _tool("workspace_data_model_collection_mutations", "Search observed collection/map mutation calls and their linked call observations without assigning registry semantics.", [], ["token", "repo_id", "owner_fqcn", "target_method", "max_results", "page_token"]),
    _tool("workspace_data_model_type_references", "Search observed type references and repository-local resolution details, including unresolved or ambiguous candidates.", [], ["token", "repo_id", "owner_fqcn", "max_results", "page_token"]),
    _tool("workspace_data_model_type_reference_resolutions", "Return exact cross-repository type-definition candidates. Multiple candidates are preserved and WKL does not choose a provider.", [], ["token", "source_repo_id", "target_repo_id", "match_scope", "max_results", "page_token"]),
    _tool("workspace_data_model_configuration_type_correspondences", "Return exact FQCN correspondences between configuration references and observed Java declarations. No publication, provider, replica, semantic-equivalence or confidence verdict is assigned.", [], ["token", "source_repo_id", "target_repo_id", "configuration_path", "match_scope", "max_results", "page_token"]),
    _tool("workspace_data_model_model_object_keys", "Return annotation-declared object key roles with exact direct or inherited field resolution. The observation preserves annotation and field evidence without assigning SQL primary-key or join verdicts.", [], ["object_id", "repo_id", "annotation"]),
    _tool("workspace_data_model_model_object_fields", "Return direct and inherited fields for configured model objects, including observed key roles and configuration directives without removing fields or assigning publication verdicts.", [], ["object_id", "repo_id", "inherited", "key_only"]),
    _tool("workspace_data_model_model_relationship_join_evidence", "Return observed relationship endpoint keys, expressions, reference operations, polymorphic targets and configuration exclusions without assigning joinability.", [], ["relationship_id", "source_object_id", "target_object_id"]),
    _tool("workspace_data_model_model_relationship_key_expression_bindings", "Return exact expression-to-reference-operation bindings and endpoint key observation ids without a JOIN verdict.", [], ["relationship_id", "endpoint_role", "reference_operation_observation_id"]),
    _tool("workspace_data_model_model_relationship_storage_key_derivation", "Return exact TSA storage-key derivation observations attached by source FQCN, source field and target FQCN equality; no SQL or JOIN verdict is generated.", [], ["relationship_id", "source_object_id", "target_object_id"]),
    _tool("workspace_data_model_model_relationships", "Return materialized field-to-target relationships backed by exact Java type resolution and observed converter reference operations, including key expressions and polymorphic targets.", [], ["source_object_id", "target_object_id", "relation_kind"]),
    _tool("workspace_data_model_model_embedded_fields", "Return resolved non-scalar fields that are workspace Java types but have no observed converter reference operation or configured target-object registration.", [], ["source_object_id"]),
    _tool("workspace_data_model_model_relationship_candidates", "Return excluded or unresolved relationship candidates separately from resolved relationships.", [], ["source_object_id", "candidate_kind"]),
    _tool("workspace_data_model_artifact_dependency_correspondences", "Return exact group/artifact coordinate co-occurrences across selected repositories; no producer/provider role is assigned.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_type_neighborhood", "Return a compact facts-only neighborhood for one observed type: definition, direct and inherited code fields, effective fields when available, inheritance, source observations, exact cross-repository candidates, configuration mentions and evidence.", ["type_id"], ["max_results"]),
    _tool("workspace_data_model_repositories", "Return selected repositories and imported model counts with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "max_results", "page_token"]),
    _tool("workspace_data_model_entities", "Find repository-scoped conceptual entity occurrences with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_entity_detail", "Return one entity occurrence, attributes, associations, mappings and evidence.", ["entity_id"], []),
    _tool("workspace_data_model_physical_assets", "Find repository-scoped physical assets with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_physical_asset_detail", "Return a physical asset occurrence with conceptual facts, DB schema observations, columns, keys, constraints and mappings.", ["asset_id"], []),
    _tool("workspace_data_model_persistent_structures", "Find repository-scoped persistent structure occurrences and their technical containers with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_persistent_structure_detail", "Return a persistent structure, observed fields, exact entity-name correspondences and evidence.", ["structure_id"], []),
    _tool("workspace_data_model_db_schema_tables", "Find repository-scoped DB schema table observations with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_db_schema_table_detail", "Return DB columns, keys, foreign keys, checks, indexes, partitioning, triggers and exact physical-asset correspondences.", ["table_id"], []),
    _tool("workspace_data_model_declared_table_relationships", "Return declared physical foreign-key observations separately from query and ORM observations.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_observed_table_relationships", "Return facts-only SQL, ORM, jOOQ, data-movement, view, partition and shared-key relationship observations.", [], ["token", "repo_id", "relation_kind", "source_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_table_relationship_detail", "Return one observed table relationship, column pairs and source evidence.", ["observation_id"], []),
    _tool("workspace_data_model_table_neighbors", "Return observed relationship occurrences adjacent to a resolved table without merging them into an inferred graph.", ["table_id"], ["relation_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_data_movement_observations", "Return observed source-to-target data movement statements separately from declared relationships.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_declared_primary_keys", "Return explicitly declared physical primary keys.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_table_key_observations", "Return declared keys, ORM identity and facts-only key-usage candidates without assigning primary-key verdicts.", [], ["token", "repo_id", "key_kind", "source_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_table_key_detail", "Return one key observation, observed columns and source evidence.", ["observation_id"], []),
    _tool("workspace_data_model_tables_without_declared_key", "Return physical table observations for which no declared primary key was imported.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_entity_inheritance", "Return repository-wide Java inheritance observations extracted from Tree-sitter declarations.", [], ["token", "repo_id", "relation_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_effective_entity_fields", "Return direct and inherited effective fields with declaration owner and inheritance path.", [], ["token", "repo_id", "entity_id", "inherited", "model_exclusion_observed", "max_results", "page_token"]),
    _tool("workspace_data_model_effective_entity_associations", "Return direct and inherited business-model associations without converting Java collection shape into physical FK or runtime cardinality.", [], ["token", "repo_id", "entity_id", "target_entity_id", "inherited", "model_exclusion_observed", "max_results", "page_token"]),
    _tool("workspace_data_model_effective_entity_model", "Return one conceptual entity with its complete effective fields, inherited associations, declaration owners and source evidence.", ["entity_id"], []),
    _tool("workspace_data_model_entity_neighbors", "Return effective association occurrences adjacent to an entity; observations remain separate and facts-only.", ["entity_id"], ["max_results", "page_token"]),
    _tool("workspace_data_model_associations", "Return observed repository associations without semantic classification, with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_correspondence_observations", "Return exact technical-name correspondence observations with deterministic pagination; no equivalence verdict is assigned. Use next_token as page_token; token is only a search filter.", [], ["token", "observation_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_missing_facts", "Return source evidence gaps preserved from repository analysis with deterministic pagination. Use next_token as page_token; token is only a search filter.", [], ["token", "repo_id", "missing_fact_kind", "max_results", "page_token"]),
    _tool("workspace_data_model_missing_fact_detail", "Return one source evidence gap with its complete deterministic diagnostic payload and evidence references.", ["gap_id"], []),
    _tool("workspace_data_model_missing_fact_summary", "Return compact grouped missing-fact counts by repository, category, kind and required operation with deterministic pagination.", [], ["token", "repo_id", "max_results", "page_token"]),
    _tool("workspace_data_model_entity_evidence", "Resolve an entity and its attributes to source evidence references.", ["entity_id"], ["max_results"]),
]
TOOL_IDS = {tool["command_id"] for tool in TOOLS}


def load_evidence_tool_catalog() -> dict[str, Any]:
    return {
        "format": "workspace_data_model_evidence_tool_catalog",
        "format_version": "1.0",
        "producer": "knowledge-layer-core",
        "analysis_mode": "data-model",
        "tools": TOOLS,
    }


def execute_evidence_request(request: dict[str, Any], *, workspace_path: str | Path) -> dict[str, Any]:
    command_id = str(request.get("command_id") or "").strip()
    if command_id not in TOOL_IDS:
        raise ValueError(f"unknown workspace data-model tool: {command_id}")
    tool = next(item for item in TOOLS if item["command_id"] == command_id)
    method_name = str(tool.get("query_method") or command_id.removeprefix("workspace_data_model_"))
    aliases = {
        "overview": "overview",
        "source_observations": "source_observations",
        "source_observation_detail": "source_observation_detail",
        "code_types": "code_types",
        "code_fields": "code_fields",
        "code_annotations": "code_annotations",
        "configuration_entries": "configuration_entries",
        "configuration_observations": "configuration_observations",
        "artifact_dependencies": "artifact_dependencies",
        "method_calls": "method_calls",
        "call_argument_flows": "call_argument_flows",
        "constructed_values": "constructed_values",
        "collection_mutations": "collection_mutations",
        "type_references": "type_references",
        "type_reference_resolutions": "type_reference_resolutions",
        "configuration_type_correspondences": "configuration_type_correspondences",
        "model_object_keys": "model_object_keys",
        "model_object_fields": "model_object_fields",
        "model_relationship_join_evidence": "model_relationship_join_evidence",
        "model_relationship_key_expression_bindings": "model_relationship_key_expression_bindings",
        "model_relationship_storage_key_derivation": "model_relationship_storage_key_derivation",
        "model_configuration_directives": "model_configuration_directives",
        "model_configuration_directive_matches": "model_configuration_directive_matches",
        "model_object_configuration": "model_object_configuration",
        "model_relationships": "model_relationships",
        "model_embedded_fields": "model_embedded_fields",
        "model_relationship_candidates": "model_relationship_candidates",
        "artifact_dependency_correspondences": "artifact_dependency_correspondences",
        "type_neighborhood": "type_neighborhood",
        "repositories": "repositories",
        "entities": "entities",
        "entity_detail": "entity_detail",
        "physical_assets": "physical_assets",
        "physical_asset_detail": "physical_asset_detail",
        "persistent_structures": "persistent_structures",
        "persistent_structure_detail": "persistent_structure_detail",
        "db_schema_tables": "db_schema_tables",
        "db_schema_table_detail": "db_schema_table_detail",
        "declared_table_relationships": "declared_table_relationships",
        "observed_table_relationships": "observed_table_relationships",
        "table_relationship_detail": "table_relationship_detail",
        "table_neighbors": "table_neighbors",
        "data_movement_observations": "data_movement_observations",
        "declared_primary_keys": "declared_primary_keys",
        "table_key_observations": "table_key_observations",
        "table_key_detail": "table_key_detail",
        "tables_without_declared_key": "tables_without_declared_key",
        "entity_inheritance": "entity_inheritance",
        "effective_entity_fields": "effective_entity_fields",
        "effective_entity_associations": "effective_entity_associations",
        "effective_entity_model": "effective_entity_model",
        "entity_neighbors": "entity_neighbors",
        "associations": "associations",
        "correspondence_observations": "correspondence_observations",
        "missing_facts": "missing_facts",
        "missing_fact_detail": "missing_fact_detail",
        "missing_fact_summary": "missing_fact_summary",
        "entity_evidence": "entity_evidence",
    }
    query = WorkspaceKnowledgeQuery(workspace_path)
    method = getattr(query, aliases.get(method_name, method_name))
    arguments = request.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError(f"{command_id}: arguments must be an object")
    arguments = {key: value for key, value in arguments.items() if key != "workspace_path"}
    signature = inspect.signature(method)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name in arguments:
            value = arguments[name]
            if name == "max_results" and isinstance(value, str) and value.isdigit():
                value = int(value)
            kwargs[name] = value
        elif parameter.default is inspect.Parameter.empty:
            raise ValueError(f"{command_id}: missing required argument: {name}")
    return method(**kwargs)
