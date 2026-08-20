from __future__ import annotations

from typing import Any, Iterable, Mapping

# The catalog is intentionally limited to typed canonical Knowledge API endpoints.
# A provider exposes a tool only when the selected revision publishes every
# capability listed in TOOL_CAPABILITY_REQUIREMENTS for that tool.

TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "get_knowledge_context": {
        "description": (
            "Return the pinned Knowledge API system/revision, published capabilities, "
            "typed knowledge artifacts and their coverage/diagnostics."
        ),
        "arguments": {},
    },
    "get_knowledge_item": {
        "description": (
            "Read one exact published AISL knowledge item by artifact_id, item_kind and local_id in the pinned revision. "
            "Use this as deterministic verification after candidate discovery. The response preserves typed payload, "
            "available evidence/issues/correspondence and explicit available/not_available/unsupported facet states. "
            "This tool does not perform semantic search and unsupported/not_available never proves absence."
        ),
        "arguments": {
            "artifact_id": "string",
            "item_kind": "string",
            "local_id": "string",
        },
    },
    "get_analysis_coverage": {
        "description": (
            "Return canonical effective-model coverage and explicit limitations. "
            "Counts are diagnostic facts, not accuracy percentages."
        ),
        "arguments": {},
    },
    "search_data_objects": {
        "description": (
            "List or search effective logical data objects in the pinned revision. "
            "Omit search to list objects page by page."
        ),
        "arguments": {
            "search": "string|null",
            "table_kind": "string|null",
            "include_fields": "boolean",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_data_object": {
        "description": (
            "Return one exact effective data object with fields, keys, relationships "
            "and published provenance."
        ),
        "arguments": {"object_id": "string"},
    },
    "get_declared_data_model_summary": {
        "description": (
            "Summarize the code-declared model in the pinned revision with raw/filtered counts, "
            "observed type/field annotation frequencies and explicit model gaps. Exact annotation "
            "filters are caller-selected evidence projections, not framework-owned business semantics."
        ),
        "arguments": {
            "repo_id": "string|null",
            "type_annotations": "array[string]",
            "exclude_field_annotations": "array[string]",
        },
    },
    "search_declared_data_objects": {
        "description": (
            "List or search code-declared data objects in the pinned prepared revision, "
            "including observed annotations, documentation and inherited effective field occurrences. "
            "The search argument is lexical discovery: use one short token or short phrase per call; "
            "issue synonyms/translations as independent calls instead of concatenating them. Results are "
            "deterministically ranked and may include bounded match_evidence showing which observed type/field "
            "caused the hit plus binding_summary for observed incoming/outgoing declared relationships. "
            "retrieval_score is ranking metadata, never semantic confidence. Optional exact annotation filters "
            "select a caller-defined evidence projection; declared-code facts do not prove storage mappings or "
            "physical JOIN semantics."
        ),
        "arguments": {
            "repo_id": "string|null",
            "search": "string|null",
            "type_annotations": "array[string]",
            "include_fields": "boolean",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_declared_data_object": {
        "description": (
            "Return one exact code-declared data object with effective inherited fields, "
            "declared relationships, inheritance, source references and provenance. "
            "Declared relationships do not by themselves prove storage JOIN semantics."
        ),
        "arguments": {"object_id": "string"},
    },
    "get_data_model_object_context": {
        "description": (
            "Return one exact object-centric technical data-model context for an external LLM: "
            "declared object/fields/relationships plus exact published logical-storage and "
            "model-storage semantics when those products exist in the pinned revision. Missing "
            "storage knowledge is explicit as not_available/not_observed. The tool never invents "
            "a physical SQL JOIN or upgrades an ambiguous mapping."
        ),
        "arguments": {"object_id": "string"},
    },
    "get_data_model_attribute_extension_context": {
        "description": (
            "Return a compact action-oriented projection of KLC-materialized relationship/JOIN semantics for one selected source relationship. "
            "The projection promotes KLC basis.usefulness, exact-vs-analog SQL JOIN relevance, storage-reference observations, key/reference expressions, SQL anchors, residual checks and explicit gaps while keeping the full canonical context available behind Knowledge API. "
            "source_type/target_type accept either stable object/type occurrence IDs from model tools or FQCNs; "
            "source_field accepts either a field occurrence ID or field name. "
            "This tool only reshapes already-published facts/inferences; it does not generate SQL, choose business meaning or upgrade confidence."
        ),
        "arguments": {
            "source_type": "string|null",
            "source_field": "string|null",
            "target_type": "string|null",
            "join_method": "string|null",
            "confidence": "string|null",
            "sql_generation_status": "string|null",
            "search": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_data_object_relationship": {
        "description": (
            "Return one exact relationship of an effective data object, preserving "
            "logical identity, storage evidence, join status and provenance."
        ),
        "arguments": {"object_id": "string", "relationship_id": "string"},
    },
    "search_physical_model_tables": {
        "description": (
            "List or search physical-model tables and optionally columns. Physical "
            "structure does not prove observed SQL read/write usage."
        ),
        "arguments": {
            "search": "string|null",
            "source_id": "string|null",
            "include_columns": "boolean",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_physical_model_table": {
        "description": (
            "Return one exact physical table with columns, keys and incoming/outgoing "
            "relationships."
        ),
        "arguments": {"table_id": "string"},
    },
    "list_physical_model_relationships": {
        "description": (
            "Return deterministic physical-model relationships for an optional table. "
            "They are structural evidence and do not replace observed SQL JOIN evidence."
        ),
        "arguments": {
            "table_id": "string|null",
            "direction": "any|parent|child",
            "source_id": "string|null",
            "resolution_status": "string|null",
            "search": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "list_physical_model_gaps": {
        "description": (
            "Return extraction and unresolved-reference gaps from the physical model. "
            "A gap is not silently converted into a mapping."
        ),
        "arguments": {
            "source_id": "string|null",
            "gap_kind": "string|null",
            "search": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "resolve_attribute_path": {
        "description": (
            "Resolve a bounded local or cross-repository attribute path from the pinned revision. "
            "The API deterministically prefers enriched cross-repository value-flow when published. "
            "Use knowledge_view=working by default; strict keeps confirmed only, exploratory also includes candidates."
        ),
        "arguments": {
            "source": "string",
            "target": "string|null",
            "selected_repo_ids": "array[string]",
            "knowledge_view": "strict|working|exploratory",
            "minimum_confidence": "unknown|probable|confirmed",
            "max_hops": "integer",
            "max_paths": "integer",
        },
    },
    "list_observed_storage_accesses": {
        "description": (
            "List observed storage reads and writes from the pinned revision. "
            "Unresolved target expressions remain unresolved and are not promoted to physical tables."
        ),
        "arguments": {
            "repo_id": "string|null",
            "access_kind": "read|write|null",
            "storage_kind": "string|null",
            "target_resolution_status": "string|null",
            "search": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "list_observed_storage_gaps": {
        "description": "List explicit unresolved or partial observed-storage access gaps.",
        "arguments": {
            "repo_id": "string|null",
            "gap_code": "string|null",
            "severity": "string|null",
            "search": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "list_used_source_tables_and_fields": {
        "description": (
            "Return the canonical SQL Source Inventory for external business-source "
            "tables, deterministically resolved fields, usage roles and coverage."
        ),
        "arguments": {
            "repo_id": "string|null",
            "search": "string|null",
            "usage_role": "string|null",
            "max_evidence_per_role": "integer",
        },
    },
    "get_sql_field_calculation": {
        "description": (
            "Return the observed SQL expression, transformation paths and every terminal "
            "source for one target field. No preferred origin is inferred."
        ),
        "arguments": {
            "target_relation": "string",
            "target_column": "string",
            "repo_id": "string|null",
            "include_gaps": "boolean",
            "max_gaps": "integer",
        },
    },
    "get_workspace_sql_catalog": {
        "description": (
            "Return the repository composition, source artifacts and coverage of the "
            "published workspace SQL catalog."
        ),
        "arguments": {},
    },
    "find_sql_target_candidates": {
        "description": (
            "Return deterministic ranked SQL target candidates for source relation, "
            "source column and business-entity hints. The tool does not generate SQL."
        ),
        "arguments": {
            "repo_id": "string|null",
            "source_relation_hints": "array[string]",
            "source_column_hints": "array[string]",
            "business_entity_hints": "array[string]",
            "limit": "integer",
        },
    },
    "get_sql_attribute_insertion_context": {
        "description": (
            "Return the best observed SQL scope for introducing an attribute and all "
            "diagnostics for partial/probable propagation."
        ),
        "arguments": {
            "target_relation": "string",
            "repo_id": "string|null",
            "source_relation_hints": "array[string]",
            "source_column_hints": "array[string]",
            "max_results": "integer",
        },
    },
    "list_sql_relation_materializations": {
        "description": (
            "Return exact observed workflow/query-to-output relation materializations. "
            "Use this to follow SQL propagation across staging/intermediate relations; no lineage is inferred."
        ),
        "arguments": {
            "output_table_name": "string|null",
            "query_id": "string|null",
            "workflow_context_file": "string|null",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_sql_query_context": {
        "description": (
            "Return one exact SQL query/select-scope context with statement, visible relations, JOINs and projections. "
            "Use it to inspect explicit propagation points before proposing a change."
        ),
        "arguments": {
            "repo_id": "string",
            "query_id": "string",
            "scope_id": "string|null",
        },
    },
    "get_sql_column_usage_context": {
        "description": (
            "Return one exact SQL column usage with statement, SELECT scope, visible "
            "relations, JOINs and projections."
        ),
        "arguments": {"sql_column_usage_id": "string"},
    },
    "get_sql_target_column_lineage": {
        "description": (
            "Return deterministic recursive SQL lineage for one target relation and "
            "optional column. Every terminal branch and scoped gap is preserved."
        ),
        "arguments": {
            "target_relation": "string",
            "target_column": "string|null",
            "repo_id": "string|null",
            "lineage_status": "string|null",
            "include_gaps": "boolean",
            "max_gaps": "integer",
            "offset": "integer",
            "limit": "integer",
        },
    },
    "get_reference_data_context": {
        "description": (
            "Return a compact facts-only Reference Data context for discovery or one optional token: exact KLC counts, "
            "bounded candidate representations, local-definition evidence, literal writes, usage-kind summary, representative usage/gaps and provenance. "
            "Use this first for common NSI/reference-data questions. It never assigns official NSI status, ownership or source of truth."
        ),
        "arguments": {"token": "string|null"},
    },
    "search_reference_data": {
        "description": "Search observed reference-data candidate representations (declared value sets, literal-populated storage targets and optional annotated dictionaries). Candidate evidence does not establish official NSI status, ownership or source of truth.",
        "arguments": {"token": "string|null", "include_non_production": "boolean", "max_results": "integer"},
    },
    "get_reference_data_object": {
        "description": "Return one exact reference-data candidate representation with evidence. Do not upgrade it to own NSI or global authority without supporting context.",
        "arguments": {"object_id": "string", "max_results": "integer"},
    },
    "get_reference_data_candidate_context": {
        "description": "Assemble one grounded technical context for a reference-data candidate after representation aggregation: local definition evidence/modes, literal writes, usage observations and gaps. It does not assign reference semantics or own-NSI status.",
        "arguments": {"token": "string", "include_non_production": "boolean", "max_results": "integer"},
    },
    "list_declared_value_sets": {
        "description": "List observed declared value sets such as enums, SQL literal row sets and configuration-declared sets, preserving source_set and provenance.",
        "arguments": {"token": "string|null", "source_sets": "array[string]", "include_values": "boolean", "max_results": "integer"},
    },
    "list_reference_literal_writes": {
        "description": "List observed literal writes to storage. Literal population is candidate evidence only and may represent configuration, operational seed data or a reference table.",
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "get_reference_usage_observations": {
        "description": "Return storage, lineage, ingress, dependency, configuration and JOIN observations relevant to a token so candidate semantics can be evaluated from evidence.",
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "get_reference_data_gaps": {
        "description": "Return explicit unresolved reference-data evidence gaps. Absence with incomplete evidence is not proof.",
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "get_reference_data_landscape": {
        "description": "Return the combined facts-only reference-data landscape and semantic policy. Official NSI status, owner and source of truth remain unassigned by framework knowledge.",
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "get_fdp_context": {
        "description": (
            "Return a compact facts-only FDP context for an optional technical token: exact KLC path/case summaries, "
            "bounded representative paths and mechanical cases, storage overlap summaries, evidence and interpretation policy. "
            "Use this first for common FDP/attribute-journey questions; use detailed FDP tools only for drill-down."
        ),
        "arguments": {"token": "string|null"},
    },
    "list_fdp_paths": {
        "description": (
            "List KLC-materialized foreign-data-persistence path fragments. Source-to-storage and "
            "storage-to-access segments remain independent unless an exact confirmed mechanical case joins them."
        ),
        "arguments": {
            "direction": "source-to-storage|storage-to-access|null",
            "token": "string|null",
            "max_results": "integer",
        },
    },
    "get_fdp_path": {
        "description": (
            "Return one exact FDP path with technical source interpretation, storage/access identity, "
            "field mappings, maturity, evidence and missing links."
        ),
        "arguments": {"path_id": "string"},
    },
    "list_fdp_cases": {
        "description": (
            "List mechanical source→storage→access cases. Only same_data_end_to_end_status=confirmed "
            "proves an exact-field technical bridge; no business FDP/risk verdict is assigned."
        ),
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "get_fdp_landscape": {
        "description": (
            "Return the combined FDP path/case landscape and KLC interpretation policy, preserving "
            "coverage, unresolved paths and the rule that technical ingress is not a business ownership verdict."
        ),
        "arguments": {"token": "string|null", "max_results": "integer"},
    },
    "list_system_interactions": {
        "description": (
            "List matched repository/system interaction summaries from the pinned revision. "
            "One interaction can have multiple execution contexts; operation_count is not a call-frequency metric."
        ),
        "arguments": {
            "source_repo_id": "string|null", "target_repo_id": "string|null", "protocol": "string|null",
            "offset": "integer", "limit": "integer",
        },
    },
    "get_system_interaction_context": {
        "description": (
            "Return one compact exact interaction context for a selected interaction_id: matched outbound/target endpoints, "
            "KLC match status/confidence/basis, bounded local execution contexts and bounded field contracts. "
            "This is a deterministic consumer projection over already-published typed knowledge; use detailed list tools only for drill-down or continuation."
        ),
        "arguments": {"interaction_id": "string"},
    },
    "list_interaction_boundaries": {
        "description": (
            "List observed inbound/outbound repository interaction boundaries with addressing, contract fingerprint and provenance."
        ),
        "arguments": {
            "repo_id": "string|null", "project_id": "string|null", "direction": "string|null",
            "protocol": "string|null", "http_method": "string|null", "service_identity": "string|null",
            "offset": "integer", "limit": "integer",
        },
    },
    "list_interaction_execution_contexts": {
        "description": (
            "List optional local execution contexts that explain how a trigger reaches an outbound boundary. "
            "Execution context is evidence about a path, not the condition for existence of the boundary interaction."
        ),
        "arguments": {
            "boundary_interaction_id": "string|null", "interaction_id": "string|null",
            "source_repo_id": "string|null", "trigger_kind": "string|null", "path_status": "string|null",
            "offset": "integer", "limit": "integer",
        },
    },
    "list_interaction_field_contracts": {
        "description": (
            "List KLC-materialized field-level contracts across matched interaction boundaries, preserving match and type-compatibility status."
        ),
        "arguments": {
            "boundary_interaction_id": "string|null", "interaction_id": "string|null",
            "source_repo_id": "string|null", "target_repo_id": "string|null", "wire_path": "string|null",
            "match_status": "string|null", "offset": "integer", "limit": "integer",
        },
    },
    "list_interaction_diagnostics": {
        "description": (
            "List explicit interaction matching diagnostics, including ambiguous/unresolved candidate evidence. "
            "Do not convert diagnostics into matched edges."
        ),
        "arguments": {
            "source_repo_id": "string|null", "match_status": "string|null", "offset": "integer", "limit": "integer",
        },
    },
    "list_interaction_coverage": {
        "description": (
            "List per-repository interaction analysis and matching coverage when that independent knowledge capability is published."
        ),
        "arguments": {
            "repo_id": "string|null", "project_id": "string|null", "coverage_status": "string|null",
            "matching_coverage_status": "string|null", "offset": "integer", "limit": "integer",
        },
    },
    "get_system_description_context": {
        "description": (
            "Return one compact action-oriented System Description context from the pinned revision: "
            "scope/modules, exact KLC-owned inventory summaries, bounded representative interfaces/integrations/events/storage/journeys, coverage, gaps and provenance. "
            "This projection does not infer business purpose, functional areas, runtime topology, storage ownership or relationships."
        ),
        "arguments": {},
    },
    "get_system_scope_overview": {
        "description": "Return KLC scope/build overview and published capabilities for prepared System Description knowledge.",
        "arguments": {"max_results": "integer"},
    },
    "get_system_repository_composition": {
        "description": "Return repositories/modules and build-file evidence from prepared System Description knowledge.",
        "arguments": {"max_results": "integer"},
    },
    "get_system_technologies": {
        "description": "Return observed build technologies and declared dependencies; declared dependencies are not proof of runtime use.",
        "arguments": {"max_results": "integer"},
    },
    "list_system_interfaces": {
        "description": "List observed system boundaries such as REST requests and Kafka consumers/producers with evidence and resolution status.",
        "arguments": {
            "direction": "inbound|outbound|null",
            "boundary_kinds": "array[string]|null",
            "include_test": "boolean",
            "max_results": "integer",
        },
    },
    "list_system_integrations": {
        "description": "List observed outbound HTTP/messaging integrations from canonical System Description knowledge.",
        "arguments": {"max_results": "integer"},
    },
    "list_system_events": {
        "description": "List observed Kafka consume/publish boundaries from canonical System Description knowledge.",
        "arguments": {"max_results": "integer"},
    },
    "list_system_storage_targets": {
        "description": "List observed storage targets and access counts; this does not invent physical relationships or source-of-truth semantics.",
        "arguments": {"representative": "boolean", "max_results": "integer"},
    },
    "get_system_description_coverage": {
        "description": "Return System Description analysis coverage from the prepared artifact, including source and payload coverage.",
        "arguments": {"max_results": "integer"},
    },
    "get_system_description_gaps": {
        "description": "Return explicit System Description gaps such as entrypoints without observed downstream storage/external continuation.",
        "arguments": {"max_results": "integer"},
    },
    "get_system_representative_journeys": {
        "description": "Return deterministic representative System Description journeys selected by KLC from observed entrypoint, storage and external-call evidence.",
        "arguments": {"max_results": "integer"},
    },
}

TOOL_CAPABILITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "get_knowledge_context": (),
    "get_knowledge_item": (),
    "get_analysis_coverage": ("common.effective-data-model",),
    "search_data_objects": ("common.effective-data-model",),
    "get_data_object": ("common.effective-data-model",),
    "get_data_object_relationship": ("common.effective-data-model",),
    "get_declared_data_model_summary": ("common.code-declared-data-model",),
    "search_declared_data_objects": ("common.code-declared-data-model",),
    "get_declared_data_object": ("common.code-declared-data-model",),
    "get_data_model_object_context": ("common.code-declared-data-model",),
    "get_data_model_attribute_extension_context": ("common.data-model-attribute-extension-context",),
    "search_physical_model_tables": ("common.physical-model.tables",),
    "get_physical_model_table": ("common.physical-model.tables",),
    "list_physical_model_relationships": ("common.physical-model.relationships",),
    "list_physical_model_gaps": ("common.physical-model.gaps",),
    "resolve_attribute_path": ("workspace.attribute-path-resolver",),
    "list_observed_storage_accesses": ("common.storage-read-write-inventory",),
    "list_observed_storage_gaps": ("common.storage-access-gaps",),
    "list_used_source_tables_and_fields": ("common.sql-source-inventory-export",),
    "get_sql_field_calculation": ("common.sql-field-calculation",),
    "get_workspace_sql_catalog": ("common.workspace-sql-catalog",),
    "find_sql_target_candidates": ("common.sql-target-resolution",),
    "get_sql_attribute_insertion_context": ("common.sql-attribute-insertion-context",),
    "list_sql_relation_materializations": ("common.relation-materialization",),
    "get_sql_query_context": ("common.sql-analysis",),
    "get_sql_column_usage_context": ("common.sql-analysis",),
    "get_sql_target_column_lineage": ("common.sql-target-column-lineage",),
    "get_reference_data_context": ("common.reference-data",),
    "search_reference_data": ("common.reference-data",),
    "get_reference_data_object": ("common.reference-data",),
    "get_reference_data_candidate_context": ("common.reference-data",),
    "list_declared_value_sets": ("common.reference-data",),
    "list_reference_literal_writes": ("common.reference-data",),
    "get_reference_usage_observations": ("common.reference-data",),
    "get_reference_data_gaps": ("common.reference-data",),
    "get_reference_data_landscape": ("common.reference-data",),
    "get_fdp_context": ("workspace.fdp-paths",),
    "list_fdp_paths": ("workspace.fdp-paths",),
    "get_fdp_path": ("workspace.fdp-paths",),
    "list_fdp_cases": ("workspace.fdp-paths",),
    "get_fdp_landscape": ("workspace.fdp-paths",),
    "list_system_interactions": ("workspace.system-interactions",),
    "get_system_interaction_context": ("workspace.system-interactions",),
    "list_interaction_boundaries": ("workspace.repository-interaction-boundaries",),
    "list_interaction_execution_contexts": ("workspace.system-interactions",),
    "list_interaction_field_contracts": ("workspace.system-interaction-field-contracts",),
    "list_interaction_diagnostics": ("workspace.system-interactions",),
    "list_interaction_coverage": ("workspace.repository-interaction-coverage",),
    "get_system_description_context": ("common.system-description",),
    "get_system_scope_overview": ("common.system-description",),
    "get_system_repository_composition": ("common.system-description",),
    "get_system_technologies": ("common.system-description",),
    "list_system_interfaces": ("common.system-description",),
    "list_system_integrations": ("common.system-description",),
    "list_system_events": ("common.system-description",),
    "list_system_storage_targets": ("common.system-description",),
    "get_system_description_coverage": ("common.system-description",),
    "get_system_description_gaps": ("common.system-description",),
    "get_system_representative_journeys": ("common.system-description",),
}


def catalog(tool_names: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    allowed = set(tool_names) if tool_names is not None else set(TOOL_CATALOG)
    return {name: dict(TOOL_CATALOG[name]) for name in sorted(allowed) if name in TOOL_CATALOG}


def tools_for_capabilities(capabilities: Iterable[str]) -> set[str]:
    available = set(str(value) for value in capabilities)
    return {
        name
        for name, required in TOOL_CAPABILITY_REQUIREMENTS.items()
        if all(capability in available for capability in required)
    }


def tool_warnings(tool: str, payload: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    if tool == "get_analysis_coverage":
        warnings.append(
            "Coverage counts are diagnostic occurrences, not accuracy percentages; "
            "not_observed and empty catalogs do not prove absence."
        )
    if tool in {
        "get_declared_data_model_summary",
        "search_declared_data_objects",
        "get_declared_data_object",
        "get_data_model_object_context",
        "search_physical_model_tables",
        "get_physical_model_table",
        "list_physical_model_relationships",
    }:
        if tool in {"get_declared_data_model_summary", "search_declared_data_objects", "get_declared_data_object", "get_data_model_object_context"}:
            warnings.append(
                "Code-declared relationships and fields are declared-model facts; they do not by themselves prove storage JOIN semantics or physical mappings."
            )
        else:
            warnings.append(
                "Physical-model facts confirm structure only; they do not assign observed SQL "
                "read/write roles or replace SQL JOIN evidence."
            )
    if tool == "list_physical_model_gaps":
        warnings.append(
            "Physical-model gaps remain explicit and non-blocking unless they invalidate the selected object."
        )
    if tool == "list_used_source_tables_and_fields":
        warnings.append(
            "The inventory contains evidence-resolved business sources only; unmapped fields are not assigned by inference."
        )
    if tool == "resolve_attribute_path":
        warnings.append(
            "Attribute-path knowledge classes are deterministic KLC classifications: working includes confirmed+derived; exploratory may include candidates."
        )
    if tool in {
        "get_sql_field_calculation",
        "find_sql_target_candidates",
        "get_sql_attribute_insertion_context",
        "list_sql_relation_materializations",
        "get_sql_query_context",
        "get_sql_target_column_lineage",
        "get_data_model_attribute_extension_context",
    }:
        warnings.append(
            "Probable, partial, ambiguous and unresolved SQL results must retain their returned status."
        )
    if tool in {"get_fdp_context", "list_fdp_paths", "get_fdp_path", "list_fdp_cases", "get_fdp_landscape"}:
        warnings.append(
            "FDP knowledge is static technical lineage. External/runtime ingress is not a business/legal ownership verdict; source/storage/access fragments remain separate unless an exact confirmed same-data case proves the bridge."
        )
        warnings.append(
            "Probable, candidate and unresolved paths plus missing_links must remain explicit; do not auto-select the first grounded candidate."
        )
    if tool in {"list_system_interactions", "get_system_interaction_context", "list_interaction_boundaries", "list_interaction_execution_contexts", "list_interaction_field_contracts", "list_interaction_diagnostics", "list_interaction_coverage"}:
        warnings.append(
            "Interaction confidence and match status are static-analysis knowledge, not runtime telemetry; probable/ambiguous/unresolved states must remain explicit."
        )
    if tool == "list_interaction_execution_contexts":
        warnings.append(
            "Multiple execution contexts for one boundary interaction explain distinct local trigger paths and must not be counted as multiple boundary interactions."
        )
    if tool in {
        "get_system_description_context", "get_system_scope_overview", "get_system_repository_composition", "get_system_technologies",
        "list_system_interfaces", "list_system_integrations", "list_system_events",
        "list_system_storage_targets", "get_system_description_coverage",
        "get_system_description_gaps", "get_system_representative_journeys",
    }:
        warnings.append(
            "System Description facts are static-analysis knowledge. Business purpose/capability wording is an interpretation over cited evidence; do not present it as explicit product documentation or runtime telemetry."
        )
    if tool == "get_knowledge_item":
        warnings.append(
            "This is an exact AISL item read, not semantic discovery. A facet state of unsupported or not_available "
            "must not be interpreted as evidence that the underlying fact is absent."
        )
    if tool == "get_system_technologies":
        warnings.append(
            "A declared dependency confirms declaration only; it does not by itself confirm runtime use."
        )
    if tool == "list_system_storage_targets":
        warnings.append(
            "Observed storage access does not prove table relationships, ownership or source-of-truth semantics."
        )
    if tool in {"get_system_description_coverage", "get_system_description_gaps"}:
        warnings.append(
            "Explicit gaps and coverage limits must remain visible; empty results do not prove absence unless coverage supports that conclusion."
        )
    return tuple(warnings)

TOOL_CATALOG_VERSION = "9"
