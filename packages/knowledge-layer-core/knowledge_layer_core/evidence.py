from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from prepared_knowledge_runtime.query import KnowledgeLayerQuery


def _tool(command_id: str, description: str, required: list[str], optional: list[str]) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "description": description,
        "required_args": ["knowledge_layer_path", *required],
        "optional_args": optional,
        "knowledge_layer_scoped": True,
        "workspace_knowledge_scoped": True,
        "analysis_mode": "data-model",
        "strict_arguments": True,
    }

TOOLS: list[dict[str, Any]] = [{'command_id': 'workspace_data_model_overview', 'description': 'Return deterministic workspace data-model counts and selected repositories.', 'required_args': ['knowledge_layer_path'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_source_observations', 'description': 'Search compact universal source observations imported from repository evidence. Results remain syntax/configuration facts and carry no domain classification, confidence, status or join verdict.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'fact_type', 'owner_fqcn', 'target_method', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_source_observation_detail', 'description': 'Return one full universal source observation, including its original payload and evidence location, without semantic interpretation.', 'required_args': ['knowledge_layer_path', 'observation_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_code_types', 'description': 'Search observed Java type declarations with stable pagination. Results preserve syntax facts and do not classify types as tables, roots, nested objects or dictionaries.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'class_kind', 'annotation', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_code_fields', 'description': 'Search observed code fields independently of conceptual entity classification; field annotations and container/element types are preserved as facts.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_code_annotations', 'description': 'Search observed code annotations and structured arguments; annotation meaning is not assigned by WKL.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_configuration_entries', 'description': 'Search structured configuration paths, node kinds and scalar/list values without interpreting project-specific configuration semantics.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_configuration_observations', 'description': 'Search all configuration evidence forms: flattened entries, grouped mapping objects, lexical references and source comments. Full source payloads are preserved and no publication, key or relationship verdict is assigned.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'fact_type', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_artifact_dependencies', 'description': 'Search source-declared artifact dependency coordinates imported from repository evidence.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_method_calls', 'description': 'Search observed method calls, receivers and owner methods without classifying APIs or repository roles.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'target_method', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_call_argument_flows', 'description': 'Search observed values flowing into call arguments, preserving expression and provenance without assigning business meaning.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'target_method', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_constructed_values', 'description': 'Search observed assignments and constructed expressions, including input symbols and AST payload through detail lookup.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_collection_mutations', 'description': 'Search observed collection/map mutation calls and their linked call observations without assigning registry semantics.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'target_method', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_type_references', 'description': 'Search observed type references and repository-local resolution details, including unresolved or ambiguous candidates.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'owner_fqcn', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_configuration_type_correspondences', 'description': 'Return exact FQCN correspondences between configuration references and observed Java declarations. No publication, provider, replica, semantic-equivalence or confidence verdict is assigned.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'source_repo_id', 'target_repo_id', 'configuration_path', 'match_scope', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_model_object_keys', 'description': 'Return annotation-declared object key roles with exact direct or inherited field resolution. The observation preserves annotation and field evidence without assigning SQL primary-key or join verdicts.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['object_id', 'repo_id', 'annotation'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_model_embedded_fields', 'description': 'Return resolved non-scalar fields that are workspace Java types but have no observed converter reference operation or configured target-object registration.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['source_object_id'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_type_neighborhood', 'description': 'Return a compact facts-only neighborhood for one observed type: definition, direct and inherited code fields, effective fields when available, inheritance, source observations, exact cross-repository candidates, configuration mentions and evidence.', 'required_args': ['knowledge_layer_path', 'type_id'], 'optional_args': ['max_results'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_repositories', 'description': 'Return selected repositories and imported model counts with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_entities', 'description': 'Find repository-scoped conceptual entity occurrences with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_entity_detail', 'description': 'Return one entity occurrence, attributes, associations, mappings and evidence.', 'required_args': ['knowledge_layer_path', 'entity_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_physical_assets', 'description': 'Find repository-scoped physical assets with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_physical_asset_detail', 'description': 'Return a physical asset occurrence with conceptual facts, DB schema observations, columns, keys, constraints and mappings.', 'required_args': ['knowledge_layer_path', 'asset_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_persistent_structures', 'description': 'Find repository-scoped persistent structure occurrences and their technical containers with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_persistent_structure_detail', 'description': 'Return a persistent structure, observed fields, exact entity-name correspondences and evidence.', 'required_args': ['knowledge_layer_path', 'structure_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_db_schema_tables', 'description': 'Find repository-scoped DB schema table observations with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_db_schema_table_detail', 'description': 'Return DB columns, keys, foreign keys, checks, indexes, partitioning, triggers and exact physical-asset correspondences.', 'required_args': ['knowledge_layer_path', 'table_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_declared_table_relationships', 'description': 'Return declared physical foreign-key observations separately from query and ORM observations.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_observed_table_relationships', 'description': 'Return facts-only SQL, ORM, jOOQ, data-movement, view, partition and shared-key relationship observations.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'relation_kind', 'source_kind', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_table_relationship_detail', 'description': 'Return one observed table relationship, column pairs and source evidence.', 'required_args': ['knowledge_layer_path', 'observation_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_table_neighbors', 'description': 'Return observed relationship occurrences adjacent to a resolved table without merging them into an inferred graph.', 'required_args': ['knowledge_layer_path', 'table_id'], 'optional_args': ['relation_kind', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_data_movement_observations', 'description': 'Return observed source-to-target data movement statements separately from declared relationships.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_declared_primary_keys', 'description': 'Return explicitly declared physical primary keys.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_table_key_observations', 'description': 'Return declared keys, ORM identity and facts-only key-usage candidates without assigning primary-key verdicts.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'key_kind', 'source_kind', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_table_key_detail', 'description': 'Return one key observation, observed columns and source evidence.', 'required_args': ['knowledge_layer_path', 'observation_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_tables_without_declared_key', 'description': 'Return physical table observations for which no declared primary key was imported.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_entity_inheritance', 'description': 'Return repository-wide Java inheritance observations extracted from Tree-sitter declarations.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'relation_kind', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_effective_entity_fields', 'description': 'Return direct and inherited effective fields with declaration owner and inheritance path.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'entity_id', 'inherited', 'model_exclusion_observed', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_effective_entity_associations', 'description': 'Return direct and inherited business-model associations without converting Java collection shape into physical FK or runtime cardinality.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'entity_id', 'target_entity_id', 'inherited', 'model_exclusion_observed', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_effective_entity_model', 'description': 'Return one conceptual entity with its complete effective fields, inherited associations, declaration owners and source evidence.', 'required_args': ['knowledge_layer_path', 'entity_id'], 'optional_args': [], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_entity_neighbors', 'description': 'Return effective association occurrences adjacent to an entity; observations remain separate and facts-only.', 'required_args': ['knowledge_layer_path', 'entity_id'], 'optional_args': ['max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_associations', 'description': 'Return observed repository associations without semantic classification, with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_missing_facts', 'description': 'Return source evidence gaps preserved from repository analysis with deterministic pagination. Use next_token as page_token; token is only a search filter.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'missing_fact_kind', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_missing_fact_summary', 'description': 'Return compact grouped missing-fact counts by repository, category, kind and required operation with deterministic pagination.', 'required_args': ['knowledge_layer_path'], 'optional_args': ['token', 'repo_id', 'max_results', 'page_token'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}, {'command_id': 'workspace_data_model_entity_evidence', 'description': 'Resolve an entity and its attributes to source evidence references.', 'required_args': ['knowledge_layer_path', 'entity_id'], 'optional_args': ['max_results'], 'workspace_knowledge_scoped': True, 'analysis_mode': 'data-model', 'strict_arguments': True, 'knowledge_layer_scoped': True}]




def _capability_tool(
    command_id: str,
    description: str,
    method_name: str,
    required: list[str],
    optional: list[str],
    required_capabilities: list[str],
) -> dict[str, Any]:
    tool = _tool(command_id, description, required, optional)
    tool.update({
        "query_method": method_name,
        "required_capabilities": required_capabilities,
    })
    return tool


# Full gap payloads are intentionally exposed through a detail command rather
# than copied into compact list responses.
TOOLS.append(_tool(
    "workspace_data_model_missing_fact_detail",
    "Return one source evidence gap with its complete deterministic diagnostic payload and evidence references.",
    ["gap_id"],
    [],
))

COMMON_CAPABILITY_TOOLS: list[dict[str, Any]] = [
    _capability_tool(
        "knowledge_layer_build_modules",
        "List mechanically observed build modules and their Gradle source provenance.",
        "list_modules", [], ["token", "repo_id", "max_results", "page_token"],
        ["common.build-dependencies"],
    ),
    _capability_tool(
        "knowledge_layer_module_dependencies",
        "List source-declared inter-module build dependencies without assigning subsystem semantics.",
        "module_dependencies", [], ["repo_id", "source_module_path", "target_module_path", "configuration", "max_results", "page_token"],
        ["common.build-dependencies"],
    ),
    _capability_tool(
        "knowledge_layer_external_dependencies",
        "List mechanically resolved external build dependency declarations, configurations, aliases and coordinates.",
        "external_dependencies", [], ["token", "repo_id", "source_module_path", "configuration", "include_test", "max_results", "page_token"],
        ["common.build-dependencies"],
    ),
    _capability_tool(
        "knowledge_layer_build_plugins",
        "List observed build plugins and declared versions by module.",
        "build_plugins", [], ["repo_id", "module_path", "max_results", "page_token"],
        ["common.build-dependencies"],
    ),
    _capability_tool(
        "knowledge_layer_module_neighborhood",
        "Return one build module with adjacent module/external dependencies and plugins.",
        "module_neighborhood", ["module_path"], ["repo_id", "max_results"],
        ["common.build-dependencies"],
    ),
]

def _knowledge_tool(
    command_id: str,
    description: str,
    method_name: str,
    required: list[str],
    optional: list[str],
    required_capabilities: list[str],
) -> dict[str, Any]:
    tool = _tool(command_id, description, required, optional)
    tool.update({
        "query_method": method_name,
        "typed_knowledge_scoped": True,
        "required_capabilities": required_capabilities,
    })
    return tool


TYPED_KNOWLEDGE_TOOLS: list[dict[str, Any]] = [
    _knowledge_tool(
        "knowledge_layer_overview",
        "Return the canonical typed knowledge-layer overview, capabilities and repositories.",
        "overview", [], [], [],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interfaces",
        "Search system interface observations materialized by the typed system-description knowledge model.",
        "system_interfaces", [], ["token", "repo_id", "record_kind", "max_results", "page_token"],
        ["common.system-description"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_scenarios",
        "Search system scenario observations materialized by the typed system-description knowledge model.",
        "system_scenarios", [], ["token", "repo_id", "record_kind", "max_results", "page_token"],
        ["common.system-description"],
    ),
    _knowledge_tool(
        "knowledge_layer_reference_data_records",
        "Search reference-data observations and declared-value records materialized by the typed reference-data knowledge model.",
        "reference_data_records", [], ["token", "repo_id", "artifact_name", "record_kind", "max_results", "page_token"],
        ["common.reference-data"],
    ),
    _knowledge_tool(
        "knowledge_layer_persistence_lineage_records",
        "Search persistence, write, access and source/storage lineage records materialized by the typed persistence-lineage knowledge model.",
        "persistence_lineage_records", [], ["token", "repo_id", "artifact_name", "record_kind", "max_results", "page_token"],
        ["workspace.persistence-lineage"],
    ),
    _knowledge_tool(
        "knowledge_layer_fdp_paths",
        "Search factual source-to-storage and storage-to-access paths for Foreign Data Persistence interpretation. The tool does not assign an FDP verdict.",
        "fdp_paths", [], ["token", "repo_id", "direction", "max_results", "page_token"],
        ["workspace.fdp-paths"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_interaction_boundaries",
        "List normalized repository HTTP boundaries with repository system/project metadata, configured service aliases, authority, service identity, paths and contract fingerprint.",
        "repository_interaction_boundaries", [], ["repo_id", "system_id", "project_id", "direction", "protocol", "http_method", "service_identity", "max_results", "page_token"],
        ["workspace.repository-interaction-boundaries"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interactions",
        "List canonical cross-repository system interaction edges materialized from observed endpoints and call reachability.",
        "system_interactions", [], ["source_repo_id", "target_repo_id", "protocol", "max_results", "page_token"],
        ["workspace.system-interactions"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_boundary_interactions",
        "List boundary-level outbound-to-inbound interactions independently from local execution paths.",
        "system_boundary_interactions", [], ["interaction_id", "source_repo_id", "target_repo_id", "match_status", "confidence", "local_execution_status", "max_results", "page_token"],
        ["workspace.system-interactions"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interaction_execution_contexts",
        "List optional local trigger-to-outbound execution contexts attached to boundary interactions.",
        "system_interaction_execution_contexts", [], ["boundary_interaction_id", "interaction_id", "source_repo_id", "trigger_kind", "path_status", "max_results", "page_token"],
        ["workspace.system-interactions"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_interaction_coverage",
        "List per-repository topology boundary counts, outbound match status counts and coverage status.",
        "repository_interaction_coverage", [], ["repo_id", "system_id", "project_id", "coverage_status", "matching_coverage_status", "max_results", "page_token"],
        ["workspace.repository-interaction-coverage"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_interaction_islands",
        "List strict or extended weakly connected repository interaction islands, including isolated repositories.",
        "repository_interaction_islands", [], ["mode", "minimum_node_count", "coverage_status", "max_results", "page_token"],
        ["workspace.repository-interaction-islands"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_interaction_island_members",
        "List repository members and directed degree statistics for interaction islands.",
        "repository_interaction_island_members", [], ["island_id", "mode", "repo_id", "max_results", "page_token"],
        ["workspace.repository-interaction-islands"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interaction_field_contracts",
        "List exact cross-repository request-wire field contracts for already confirmed operation interactions. Rows represent protocol contract continuity, not attribute transformation.",
        "system_interaction_field_contracts", [], ["boundary_interaction_id", "interaction_id", "source_repo_id", "target_repo_id", "wire_path", "match_status", "max_results", "page_token"],
        ["workspace.system-interaction-field-contracts"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_value_nodes",
        "List typed repository-local value nodes, including HTTP wire fields, without transitive composition.",
        "repository_value_nodes", [], ["repo_id", "node_kind", "operation", "max_results", "page_token"],
        ["workspace.repository-value-flow"],
    ),
    _knowledge_tool(
        "knowledge_layer_repository_value_flow_edges",
        "List direct value-flow edges, including repository-local mappings and confirmed or probable candidate cross-repository HTTP request/response transport with evidence packets.",
        "repository_value_flow_edges", [], ["repo_id", "source_repo_id", "target_repo_id", "flow_kind", "transformation_kind", "naming_relation", "value_preservation", "confidence", "derivation_id", "derivation_kind", "max_results", "page_token"],
        ["workspace.repository-value-flow"],
    ),
    _knowledge_tool(
        "knowledge_layer_attribute_paths",
        "Resolve bounded confirmed, probable-candidate and partial attribute paths over the canonical direct value-flow graph for an explicit repository selection. Paths include compact evidence summaries and are never persisted.",
        "resolve_attribute_paths", ["source", "selected_repo_ids"], ["target", "max_hops", "max_paths", "max_branching", "allowed_edge_kinds", "minimum_confidence"],
        ["workspace.attribute-path-resolver"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interaction_graph",
        "Return the compact workspace graph with system nodes, system edges, operation edges and deterministic match diagnostics summary.",
        "system_interaction_graph", [], [],
        ["workspace.system-interactions"],
    ),
    _knowledge_tool(
        "knowledge_layer_system_interaction_diagnostics",
        "List matched, unresolved and ambiguous outbound-interface composition diagnostics without inventing a target edge.",
        "system_interaction_diagnostics", [], ["source_repo_id", "match_status", "max_results", "page_token"],
        ["workspace.system-interactions"],
    ),
]

TOOLS.extend(COMMON_CAPABILITY_TOOLS)
TOOLS.extend(TYPED_KNOWLEDGE_TOOLS)

TOOL_IDS = {tool["command_id"] for tool in TOOLS}


def load_evidence_tool_catalog() -> dict[str, Any]:
    return {
        "format": "knowledge_layer_data_model_evidence_tool_catalog",
        "format_version": "1.0",
        "producer": "knowledge-layer-core",
        "analysis_mode": "data-model",
        "scope": "knowledge-layer",
        "tools": TOOLS,
    }


def execute_evidence_request(
    request: dict[str, Any],
    *,
    knowledge_layer_path: str | Path | None = None,
    workspace_path: str | Path | None = None,
) -> dict[str, Any]:
    command_id = str(request.get("command_id") or "").strip()
    if command_id not in TOOL_IDS:
        raise ValueError(f"unknown knowledge-layer data-model tool: {command_id}")
    tool = next(item for item in TOOLS if item["command_id"] == command_id)
    method_name = str(tool.get("query_method") or command_id.removeprefix("workspace_data_model_"))
    query_path = knowledge_layer_path if knowledge_layer_path is not None else workspace_path
    if query_path is None:
        raise ValueError("knowledge_layer_path is required")
    query = KnowledgeLayerQuery(query_path)
    method = getattr(query, method_name)
    arguments = request.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError(f"{command_id}: arguments must be an object")
    arguments = {
        key: value for key, value in arguments.items()
        if key not in {"knowledge_layer_path", "workspace_path"}
    }
    required_names = [
        str(name) for name in (tool.get("required_args") or [])
        if str(name) not in {"knowledge_layer_path", "workspace_path"}
    ]
    optional_names = [
        str(name) for name in (tool.get("optional_args") or [])
        if str(name) not in {"knowledge_layer_path", "workspace_path"}
    ]
    allowed_names = set(required_names) | set(optional_names)
    missing = [name for name in required_names if name not in arguments]
    if missing:
        raise ValueError(f"{command_id}: missing required argument: {missing[0]}")
    transport_names = {"max_results", "page_token"}
    unknown = sorted(set(arguments) - allowed_names - transport_names)
    if unknown:
        raise ValueError(f"{command_id}: unknown arguments: {unknown}")
    kwargs: dict[str, Any] = {}
    for name, value in arguments.items():
        if name not in allowed_names:
            continue
        if name == "max_results" and isinstance(value, str) and value.isdigit():
            value = int(value)
        kwargs[name] = value
    return method(**kwargs)
