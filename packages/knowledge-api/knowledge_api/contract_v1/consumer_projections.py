from __future__ import annotations

"""Consumer-oriented deterministic read projections over canonical Knowledge API payloads.

These helpers only select, bound and reorder already-published fields. They do not
classify relationships, infer joins, choose business meaning or create new evidence.
The canonical raw Knowledge API endpoint remains available for full-detail reads.
"""

from typing import Any, Mapping, Sequence

ATTRIBUTE_EXTENSION_GUIDANCE_SCHEMA_VERSION = "data-model-attribute-extension-guidance/v1"
SYSTEM_INTERACTION_GUIDANCE_SCHEMA_VERSION = "system-interaction-guidance/v1"
SYSTEM_DESCRIPTION_GUIDANCE_SCHEMA_VERSION = "system-description-guidance/v1"
FOREIGN_DATA_PERSISTENCE_GUIDANCE_SCHEMA_VERSION = "foreign-data-persistence-guidance/v1"
REFERENCE_DATA_GUIDANCE_SCHEMA_VERSION = "reference-data-guidance/v1"


def _text(value: Any, *, limit: int = 1600) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"… <truncated {len(text) - limit} chars>"


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _bounded(value: Any, *, limit: int) -> tuple[list[Any], dict[str, Any]]:
    items = _sequence(value)
    shown = items[:limit]
    return shown, {
        "source_total": len(items),
        "presented": len(shown),
        "truncated": len(items) > limit,
    }


def _pick(value: Any, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {key: value.get(key) for key in keys if value.get(key) is not None}


def _source_ref(value: Any) -> dict[str, Any] | None:
    result = _pick(
        value,
        (
            "repository_relative_path",
            "line_start",
            "line_end",
            "extractor",
            "evidence_id",
        ),
    )
    return result or None


def _compact_source_refs(value: Any, *, limit: int = 4) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw, meta = _bounded(value, limit=limit)
    refs = [ref for ref in (_source_ref(item) for item in raw) if ref]
    meta["presented"] = len(refs)
    return refs, meta


def _compact_storage_observation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "evidence_kind",
            "observation_id",
            "repo_id",
            "api_framework",
            "source_owner_fqcn",
            "source_operation",
            "source_alias",
            "storage_reference_field_name",
            "reference_operation",
            "value_converter_operation",
            "reference_value_expression",
        ),
    )
    refs, ref_meta = _compact_source_refs(value.get("source_refs"), limit=3)
    if refs:
        result["source_refs"] = refs
    if ref_meta["truncated"]:
        result["source_refs_projection"] = ref_meta
    return result or None


def _compact_correspondence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "match_basis",
            "reference_observation_id",
            "target_key_observation_id",
            "target_key_fields",
            "reference_expression",
            "target_key_expression",
            "canonical_signature",
        ),
    )
    refs, ref_meta = _compact_source_refs(value.get("source_refs"), limit=2)
    target_refs, target_ref_meta = _compact_source_refs(value.get("target_source_refs"), limit=2)
    if refs:
        result["source_refs"] = refs
    if target_refs:
        result["target_source_refs"] = target_refs
    if ref_meta["truncated"] or target_ref_meta["truncated"]:
        result["source_ref_projection"] = {
            "source": ref_meta,
            "target": target_ref_meta,
        }
    return result or None


def _compact_column_pair(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "left_relation_id",
            "left_column_usage_id",
            "left_column",
            "right_relation_id",
            "right_column_usage_id",
            "right_column",
            "operator",
            "resolution_status",
        ),
    ) or None


def _compact_join_example(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "sql_join_edge_id",
            "repo_id",
            "query_id",
            "file",
            "line_start",
            "join_type",
            "condition_kind",
            "left_relation_id",
            "right_relation_id",
            "right_relation_name",
            "resolution_status",
            "physical_join_confirmed",
            "relationship_relevance",
            "relationship_relevance_basis",
        ),
    )
    predicate = _text(value.get("predicate"), limit=1400)
    if predicate:
        result["predicate"] = predicate
    pairs_raw, pairs_meta = _bounded(value.get("column_pairs"), limit=6)
    pairs = [pair for pair in (_compact_column_pair(item) for item in pairs_raw) if pair]
    if pairs:
        result["column_pairs"] = pairs
    if pairs_meta["truncated"]:
        result["column_pairs_projection"] = pairs_meta
    additional, additional_meta = _bounded(value.get("additional_predicates"), limit=3)
    if additional:
        result["additional_predicates"] = additional
    temporal, temporal_meta = _bounded(value.get("temporal_or_range_predicates"), limit=3)
    if temporal:
        result["temporal_or_range_predicates"] = temporal
    if additional_meta["truncated"] or temporal_meta["truncated"]:
        result["predicate_projection"] = {
            "additional": additional_meta,
            "temporal_or_range": temporal_meta,
        }
    return result or None


def _compact_sql_relation(value: Any) -> dict[str, Any] | None:
    result = _pick(
        value,
        (
            "sql_relation_id",
            "repo_id",
            "relation_name",
            "logical_name",
            "usage_role",
            "representation_variant",
            "knowledge_class",
            "mapping_basis",
        ),
    )
    return result or None


def _compact_field_usage(value: Any) -> dict[str, Any] | None:
    result = _pick(
        value,
        (
            "field",
            "sql_column_usage_id",
            "sql_relation_id",
            "query_id",
            "file",
            "column",
            "usage_role",
            "knowledge_class",
            "mapping_basis",
        ),
    )
    return result or None


def _compact_projection(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "sql_projection_id",
            "repo_id",
            "query_id",
            "file",
            "line_start",
            "output_name",
            "expression_kind",
            "resolution_status",
            "resolution_basis",
        ),
    )
    expression = _text(value.get("expression"), limit=1000)
    if expression:
        result["expression"] = expression
    return result or None


def _compact_physical_candidate(value: Any) -> dict[str, Any] | None:
    result = _pick(
        value,
        (
            "physical_model_table_id",
            "physical_table_name",
            "physical_table_code",
            "mapping_basis",
            "knowledge_class",
        ),
    )
    return result or None


def _compact_anchor(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = _pick(value, ("storage_aliases", "storage_key_fields", "storage_key_expressions"))
    projection: dict[str, Any] = {}

    rel_raw, rel_meta = _bounded(value.get("observed_sql_relations"), limit=8)
    rels = [item for item in (_compact_sql_relation(v) for v in rel_raw) if item]
    if rels:
        result["observed_sql_relations"] = rels
    projection["observed_sql_relations"] = rel_meta

    usage_raw, usage_meta = _bounded(value.get("observed_field_usages"), limit=8)
    usages = [item for item in (_compact_field_usage(v) for v in usage_raw) if item]
    if usages:
        result["observed_field_usages"] = usages
    projection["observed_field_usages"] = usage_meta

    proj_raw, proj_meta = _bounded(value.get("observed_sql_projections"), limit=6)
    projections = [item for item in (_compact_projection(v) for v in proj_raw) if item]
    if projections:
        result["observed_sql_projections"] = projections
    projection["observed_sql_projections"] = proj_meta

    phys_raw, phys_meta = _bounded(value.get("physical_candidates"), limit=6)
    physical = [item for item in (_compact_physical_candidate(v) for v in phys_raw) if item]
    if physical:
        result["physical_candidates"] = physical
    projection["physical_candidates"] = phys_meta

    if any(meta.get("truncated") for meta in projection.values()):
        result["projection"] = projection
    return result


def _compact_diagnostic(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(value, ("code", "severity", "status", "storage_reference_field_names", "relevance_counts"))
    message = _text(value.get("message"), limit=1000)
    if message:
        result["message"] = message
    return result or None


def _compact_gap(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(value, ("gap_id", "gap_kind", "severity", "owner_kind", "owner_id"))
    message = _text(value.get("message"), limit=1000)
    if message:
        result["message"] = message
    details = value.get("details")
    if isinstance(details, Mapping):
        # Details are preserved only when already small/actionable. Full raw details remain
        # available on the canonical context endpoint.
        compact_details = _pick(
            details,
            (
                "code",
                "reason",
                "candidate_targets",
                "missing_relations",
                "source_type",
                "source_field",
                "target_type",
            ),
        )
        if compact_details:
            result["details"] = compact_details
    return result or None


def _compact_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = _pick(value, ("code_relationship_id",))
    refs, refs_meta = _compact_source_refs(value.get("source_refs"), limit=4)
    if refs:
        result["source_refs"] = refs
    if refs_meta["truncated"]:
        result["source_refs_projection"] = refs_meta
    return result


def _compact_item(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "join_semantic_id",
            "source_repo_id",
            "source_fqcn",
            "source_field",
            "target_fqcn",
            "confidence",
            "relationship_kind",
            "cardinality",
            "target_alignment",
            "polymorphic",
            "join_method",
            "sql_generation_status",
            "declared_type_expression",
        ),
    )
    # Only non-empty optional collections are useful to an LLM.
    for key in (
        "concrete_targets",
        "source_reference_expressions",
        "target_key_fields",
        "target_key_expressions",
        "source_parent_key_expressions",
        "child_key_expressions",
    ):
        items = _sequence(value.get(key))
        if items:
            result[key] = items

    basis = value.get("basis") if isinstance(value.get("basis"), Mapping) else {}
    usefulness = basis.get("usefulness") if isinstance(basis.get("usefulness"), Mapping) else {}
    if usefulness:
        # This is a direct KLC-owned value, promoted for visibility only.
        result["usefulness"] = dict(usefulness)
    basis_summary = _pick(
        basis,
        (
            "source_storage_field_observation_count",
            "source_relationship_field_observed_in_sql",
            "exact_relationship_sql_join_observed",
            "sql_join_example_relevance_counts",
        ),
    )
    if basis_summary:
        result["basis_summary"] = basis_summary

    item_projection: dict[str, Any] = {}

    storage_raw, storage_meta = _bounded(basis.get("source_storage_field_observations"), limit=6)
    storage = [item for item in (_compact_storage_observation(v) for v in storage_raw) if item]
    if storage:
        result["source_storage_field_observations"] = storage
    item_projection["source_storage_field_observations"] = storage_meta

    corr_raw, corr_meta = _bounded(value.get("structural_correspondences"), limit=4)
    correspondences = [item for item in (_compact_correspondence(v) for v in corr_raw) if item]
    if correspondences:
        result["structural_correspondences"] = correspondences
    item_projection["structural_correspondences"] = corr_meta

    join_raw, join_meta = _bounded(value.get("observed_sql_join_examples"), limit=6)
    joins = [item for item in (_compact_join_example(v) for v in join_raw) if item]
    if joins:
        result["observed_sql_join_examples"] = joins
    item_projection["observed_sql_join_examples"] = join_meta

    source_anchor = _compact_anchor(value.get("source_sql_anchor"))
    if source_anchor:
        result["source_sql_anchor"] = source_anchor
    target_anchor = _compact_anchor(value.get("target_sql_anchor"))
    if target_anchor:
        result["target_sql_anchor"] = target_anchor

    phys_raw, phys_meta = _bounded(value.get("physical_candidates"), limit=6)
    physical = [item for item in (_compact_physical_candidate(v) for v in phys_raw) if item]
    if physical:
        result["physical_candidates"] = physical
    item_projection["physical_candidates"] = phys_meta

    diag_raw, diag_meta = _bounded(value.get("diagnostics"), limit=12)
    diagnostics = [item for item in (_compact_diagnostic(v) for v in diag_raw) if item]
    if diagnostics:
        result["diagnostics"] = diagnostics
    item_projection["diagnostics"] = diag_meta

    provenance = _compact_provenance(value.get("provenance"))
    if provenance:
        result["provenance"] = provenance

    if any(meta.get("truncated") for meta in item_projection.values()):
        result["projection"] = item_projection
    return result or None


def project_attribute_extension_guidance(context: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact action-oriented view from the canonical context response.

    No value is semantically upgraded here. In particular ``usefulness`` is copied
    verbatim from KLC ``basis.usefulness`` and confidence/ambiguity/gaps are preserved.
    """
    raw_items = _sequence(context.get("items"))
    items = [item for item in (_compact_item(value) for value in raw_items) if item]

    gap_raw, gap_meta = _bounded(context.get("gaps"), limit=20)
    gaps = [item for item in (_compact_gap(value) for value in gap_raw) if item]

    projection = {
        "semantic_derivation": "none",
        "canonical_detail_endpoint": "/data-model/attribute-extension-context",
    }
    if len(items) != len(raw_items):
        projection["item_projection"] = {
            "source_total": len(raw_items),
            "presented": len(items),
        }
    if gap_meta.get("truncated"):
        projection["gap_projection"] = gap_meta

    gap_count = int(context.get("gap_count") or 0)
    result = {
        "schema_version": context.get("schema_version"),
        "guidance_schema_version": ATTRIBUTE_EXTENSION_GUIDANCE_SCHEMA_VERSION,
        "context_schema_version": context.get("context_schema_version"),
        "system_id": context.get("system_id"),
        "revision_id": context.get("revision_id"),
        "filters": dict(context.get("filters") or {}),
        "items": items,
        "page": dict(context.get("page") or {}),
        "gap_count": gap_count,
        "gaps_truncated": bool(context.get("gaps_truncated")) or bool(gap_meta.get("truncated")),
        "projection": projection,
    }
    if gaps:
        result["gaps"] = gaps
    return result


def _compact_interaction_match_basis(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    contract = value.get("contract") if isinstance(value.get("contract"), Mapping) else {}
    result = _pick(
        value,
        (
            "lookup_basis",
            "path_basis",
            "address_basis",
            "http_method",
            "outbound_path",
            "target_path",
            "service_identity_overlap",
            "property_identity_overlap",
            "authority_overlap",
        ),
    )
    contract_summary = _pick(
        contract,
        (
            "outbound_request_payload_type",
            "inbound_request_payload_type",
            "request_payload_type_match",
            "request_field_overlap_count",
            "request_field_similarity",
        ),
    )
    overlap, overlap_meta = _bounded(contract.get("request_field_overlap"), limit=12)
    if overlap:
        contract_summary["request_field_overlap"] = overlap
    if overlap_meta.get("truncated"):
        contract_summary["request_field_overlap_projection"] = overlap_meta
    if contract_summary:
        result["contract"] = contract_summary
    return result or None


def _compact_interaction_provenance(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "outbound_interface_record_id",
            "target_ingress_record_id",
            "source_ingress_record_id",
            "call_chain_basis",
        ),
    )
    for key in (
        "outbound_interface_record_ids",
        "target_candidate_interface_ids",
        "call_chain_evidence_record_ids",
    ):
        items, meta = _bounded(value.get(key), limit=8)
        if items:
            result[key] = items
        if meta.get("truncated"):
            result[f"{key}_projection"] = meta
    return result or None


def _compact_interaction_execution_context(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "execution_context_id",
            "boundary_interaction_id",
            "interaction_id",
            "source_repo_id",
            "source_ingress_operation",
            "source_ingress_endpoint",
            "outbound_operation",
            "trigger_kind",
            "path_status",
            "call_chain_length",
        ),
    )
    chain, chain_meta = _bounded(value.get("call_chain_json"), limit=12)
    if chain:
        result["call_chain"] = chain
    if chain_meta.get("truncated"):
        result["call_chain_projection"] = chain_meta
    provenance = _compact_interaction_provenance(value.get("provenance_json"))
    if provenance:
        result["provenance"] = provenance
    return result or None


def _compact_interaction_field_contract(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "field_contract_id",
            "boundary_interaction_id",
            "interaction_id",
            "wire_path",
            "match_kind",
            "match_status",
            "type_compatibility",
        ),
    )
    source = _pick(
        value,
        (
            "source_repo_id",
            "outbound_payload_type",
            "outbound_field_path",
            "outbound_attribute_name",
            "outbound_wire_name",
            "outbound_field_type",
            "outbound_source_schema",
        ),
    )
    target = _pick(
        value,
        (
            "target_repo_id",
            "target_payload_type",
            "target_field_path",
            "target_attribute_name",
            "target_wire_name",
            "target_field_type",
            "target_source_schema",
        ),
    )
    if source:
        result["source"] = source
    if target:
        result["target"] = target
    provenance = value.get("provenance_json") if isinstance(value.get("provenance_json"), Mapping) else {}
    evidence: dict[str, Any] = _pick(
        provenance,
        (
            "boundary_confidence",
            "boundary_match_status",
            "match_basis",
            "normalization",
        ),
    )
    for side in ("outbound_evidence_refs", "target_evidence_refs"):
        refs, meta = _bounded(provenance.get(side), limit=2)
        compact_refs = [
            _pick(item, ("repository_relative_path", "file", "line_start", "line_end", "extractor", "evidence_id"))
            for item in refs
            if isinstance(item, Mapping)
        ]
        compact_refs = [item for item in compact_refs if item]
        if compact_refs:
            evidence[side] = compact_refs
        if meta.get("truncated"):
            evidence[f"{side}_projection"] = meta
    if evidence:
        result["evidence"] = evidence
    return result or None


def _compact_boundary_interaction(
    value: Any,
    *,
    execution_contexts: Sequence[Mapping[str, Any]],
    field_contracts: Sequence[Mapping[str, Any]],
    execution_context_total: int,
    field_contract_total: int,
    execution_contexts_truncated: bool,
    field_contracts_truncated: bool,
    field_contracts_available: bool,
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "boundary_interaction_id",
            "interaction_id",
            "source_repo_id",
            "target_repo_id",
            "protocol",
            "http_method",
            "match_status",
            "confidence",
            "local_execution_status",
        ),
    )
    source = _pick(value, ("outbound_interface_id", "outbound_operation", "outbound_endpoint"))
    target = _pick(value, ("target_ingress_interface_id", "target_ingress_operation", "target_ingress_endpoint"))
    if source:
        result["source"] = source
    if target:
        result["target"] = target
    match_basis = _compact_interaction_match_basis(value.get("match_basis_json"))
    if match_basis:
        result["match_basis"] = match_basis
    provenance = _compact_interaction_provenance(value.get("provenance_json"))
    if provenance:
        result["provenance"] = provenance

    compact_contexts = [item for item in (_compact_interaction_execution_context(raw) for raw in execution_contexts) if item]
    if compact_contexts:
        result["execution_contexts"] = compact_contexts
    result["execution_context_summary"] = {
        "source_total": execution_context_total,
        "presented": len(compact_contexts),
        "truncated": execution_contexts_truncated,
    }

    compact_fields = [item for item in (_compact_interaction_field_contract(raw) for raw in field_contracts) if item]
    if compact_fields:
        result["field_contracts"] = compact_fields
    result["field_contract_summary"] = {
        "availability": "available" if field_contracts_available else "not_available",
        "source_total": field_contract_total if field_contracts_available else 0,
        "presented": len(compact_fields),
        "truncated": field_contracts_truncated if field_contracts_available else False,
    }
    return result or None


def project_system_interaction_guidance(
    *,
    system_id: str,
    revision_id: str,
    interaction_id: str,
    boundary_result: Mapping[str, Any],
    execution_context_result: Mapping[str, Any],
    field_contract_result: Mapping[str, Any] | None,
    context_limit: int,
    field_limit: int,
) -> dict[str, Any]:
    """Build a compact exact-id interaction view from canonical typed reads.

    This performs exact-id grouping and bounded field selection only. It never
    upgrades match/confidence/type compatibility or invents a peer, endpoint,
    field correspondence, execution path or business meaning.
    """
    boundary_items = [dict(v) for v in _sequence(boundary_result.get("items")) if isinstance(v, Mapping)]
    context_items = [dict(v) for v in _sequence(execution_context_result.get("items")) if isinstance(v, Mapping)]
    field_items = (
        [dict(v) for v in _sequence(field_contract_result.get("items")) if isinstance(v, Mapping)]
        if isinstance(field_contract_result, Mapping)
        else []
    )
    field_available = field_contract_result is not None
    context_totals = (
        execution_context_result.get("total_count_by_boundary")
        if isinstance(execution_context_result.get("total_count_by_boundary"), Mapping)
        else {}
    )
    field_totals = (
        field_contract_result.get("total_count_by_boundary")
        if isinstance(field_contract_result, Mapping)
        and isinstance(field_contract_result.get("total_count_by_boundary"), Mapping)
        else {}
    )

    items: list[dict[str, Any]] = []
    for boundary in boundary_items:
        boundary_id = str(boundary.get("boundary_interaction_id") or "")
        contexts = [v for v in context_items if str(v.get("boundary_interaction_id") or "") == boundary_id]
        fields = [v for v in field_items if str(v.get("boundary_interaction_id") or "") == boundary_id]
        compact = _compact_boundary_interaction(
            boundary,
            execution_contexts=contexts[:context_limit],
            field_contracts=fields[:field_limit],
            execution_context_total=int(context_totals.get(boundary_id) or len(contexts)),
            field_contract_total=int(field_totals.get(boundary_id) or len(fields)),
            execution_contexts_truncated=int(context_totals.get(boundary_id) or len(contexts)) > len(contexts),
            field_contracts_truncated=int(field_totals.get(boundary_id) or len(fields)) > len(fields),
            field_contracts_available=field_available,
        )
        if compact:
            items.append(compact)

    boundary_total = int(boundary_result.get("total_count") or len(boundary_items))
    context_total = int(execution_context_result.get("total_count") or len(context_items))
    field_total = int(field_contract_result.get("total_count") or len(field_items)) if isinstance(field_contract_result, Mapping) else 0
    return {
        "schema_version": "knowledge_api/v1",
        "guidance_schema_version": SYSTEM_INTERACTION_GUIDANCE_SCHEMA_VERSION,
        "system_id": system_id,
        "revision_id": revision_id,
        "interaction_id": interaction_id,
        "items": items,
        "summary": {
            "boundary_interaction_count": boundary_total,
            "boundary_interactions_presented": len(items),
            "boundary_interactions_truncated": boundary_total > len(boundary_items),
            "execution_context_count": context_total,
            "field_contract_availability": "available" if field_available else "not_available",
            "field_contract_count": field_total,
        },
        "projection": {
            "semantic_derivation": "none",
            "grouping_basis": "exact interaction_id and boundary_interaction_id",
            "context_limit_per_boundary": context_limit,
            "field_limit_per_boundary": field_limit,
            "canonical_detail_endpoints": [
                "/interactions/boundary-interactions",
                "/interactions/execution-contexts",
                "/interactions/field-contracts",
            ],
        },
    }



def _compact_system_description_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "evidence_id",
            "repo_id",
            "path",
            "line_start",
            "line_end",
            "extractor",
            "maturity",
        ),
    ) or None


def _compact_system_description_module(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "module_id",
            "repo_id",
            "module_path",
            "module_name",
            "build_system",
            "build_file",
            "dependency_count",
            "dependent_count",
            "plugin_count",
            "evidence_ids",
        ),
    ) or None


def _compact_system_description_technology(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "technology_id",
            "kind",
            "repo_id",
            "module_path",
            "coordinate",
            "group_id",
            "artifact_id",
            "version",
            "configuration",
            "runtime_use_confirmed",
            "evidence_ids",
        ),
    ) or None


def _compact_system_description_interface(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "interface_id",
            "repo_id",
            "operation",
            "direction",
            "boundary_kind",
            "protocol",
            "endpoint_or_topic",
            "http_method",
            "payload_schema",
            "request_payload_type",
            "response_payload_type",
            "resolution_status",
            "evidence_level",
            "attribute_count",
            "evidence_ids",
        ),
    ) or None


def _compact_system_description_storage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _pick(
        value,
        (
            "object_id",
            "repo_id",
            "object_kind",
            "name",
            "qualified_name",
            "source_type",
            "evidence_level",
            "selection_score",
            "access_count",
            "read_count",
            "write_count",
            "mutation_count",
            "evidence_ids",
        ),
    ) or None


def _compact_system_description_journey(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "journey_id",
            "repo_id",
            "operation",
            "evidence_level",
            "is_complete",
            "selection_score",
        ),
    )
    entrypoints, entry_meta = _bounded(value.get("entrypoints"), limit=2)
    external_calls, external_meta = _bounded(value.get("external_calls"), limit=4)
    storage_touches, storage_meta = _bounded(value.get("storage_touches"), limit=6)
    if entrypoints:
        result["entrypoints"] = [
            _pick(item, ("boundary_role", "kind", "direction", "method", "path", "topic", "schema_ref"))
            for item in entrypoints
            if isinstance(item, Mapping)
        ]
    if external_calls:
        result["external_calls"] = [
            _pick(
                item,
                (
                    "fact_type",
                    "dependency_kind",
                    "name",
                    "operation",
                    "endpoint_path",
                    "base_url_property_key",
                    "request_payload_type",
                    "response_payload_type",
                ),
            )
            for item in external_calls
            if isinstance(item, Mapping)
        ]
    if storage_touches:
        result["storage_touches"] = [
            _pick(
                item,
                (
                    "fact_type",
                    "name",
                    "operation",
                    "access_kind",
                    "storage_method",
                    "storage_target",
                ),
            )
            for item in storage_touches
            if isinstance(item, Mapping)
        ]
    if entry_meta["truncated"] or external_meta["truncated"] or storage_meta["truncated"]:
        result["detail_projection"] = {
            "entrypoints": entry_meta,
            "external_calls": external_meta,
            "storage_touches": storage_meta,
        }
    return result or None


def _system_description_query_total(value: Mapping[str, Any]) -> int:
    pagination = value.get("pagination")
    if isinstance(pagination, Mapping) and pagination.get("total_count") is not None:
        return int(pagination.get("total_count") or 0)
    return len(_sequence(value.get("items")))


def _system_description_section(
    result: Mapping[str, Any],
    *,
    compact,
    limit: int,
    source_total: int | None = None,
) -> dict[str, Any]:
    raw_items = [item for item in _sequence(result.get("items")) if isinstance(item, Mapping)]
    items = [item for item in (compact(value) for value in raw_items[:limit]) if item]
    resolved_source_total = _system_description_query_total(result) if source_total is None else int(source_total)
    section: dict[str, Any] = {
        "summary": dict(result.get("summary") or {}),
        "items": items,
        "presentation": {
            "source_total": resolved_source_total,
            "presented": len(items),
            "truncated": resolved_source_total > len(items),
        },
    }
    return section


def _collect_evidence_ids(value: Any, target: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "evidence_ids":
                for evidence_id in _sequence(nested):
                    normalized = str(evidence_id or "").strip()
                    if normalized:
                        target.add(normalized)
            else:
                _collect_evidence_ids(nested, target)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _collect_evidence_ids(nested, target)


def _compact_fdp_source_interpretation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "status",
            "source_kind",
            "source_system",
            "business_source_decision",
            "source_payload",
            "named_source_system_required_for_technical_ingress",
            "named_source_system_required_for_governance",
        ),
    )
    reason = _text(value.get("reason"), limit=500)
    if reason:
        result["reason"] = reason
    return result or None


def _compact_fdp_field_mapping(value: Any) -> dict[str, Any] | None:
    return _pick(
        value,
        (
            "source_field",
            "storage_field",
            "target_field",
            "response_field",
            "mapping_type",
            "status",
            "mapping_basis",
        ),
    ) or None


def _compact_fdp_path(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "path_id",
            "direction",
            "repo_id",
            "storage_object",
            "source_operation",
            "access_boundary",
            "lineage_status",
            "evidence_maturity_level",
        ),
    )
    source = _compact_fdp_source_interpretation(value.get("source_interpretation"))
    if source:
        result["source_interpretation"] = source
    maturity = value.get("evidence_maturity_dimensions")
    if isinstance(maturity, Mapping) and maturity:
        result["evidence_maturity_dimensions"] = dict(maturity)
    path, path_meta = _bounded(value.get("path"), limit=8)
    if path:
        result["path"] = path
    if path_meta.get("truncated"):
        result["path_projection"] = path_meta
    mappings_raw, mapping_meta = _bounded(value.get("field_mappings"), limit=8)
    mappings = [item for item in (_compact_fdp_field_mapping(v) for v in mappings_raw) if item]
    if mappings:
        result["field_mappings"] = mappings
    if mapping_meta.get("truncated"):
        result["field_mapping_projection"] = mapping_meta
    missing, missing_meta = _bounded(value.get("missing_links"), limit=8)
    if missing:
        result["missing_links"] = missing
    if missing_meta.get("truncated"):
        result["missing_link_projection"] = missing_meta
    evidence_ids, evidence_meta = _bounded(value.get("evidence_ids"), limit=8)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if evidence_meta.get("truncated"):
        result["evidence_projection"] = evidence_meta
    same_data_link = value.get("same_data_link")
    if isinstance(same_data_link, Mapping) and same_data_link:
        result["same_data_link"] = dict(same_data_link)
    return result or None


def _compact_fdp_case(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "case_id",
            "case_granularity",
            "repo_id",
            "storage_object",
            "storage_field",
            "source_path_id",
            "access_path_id",
            "bridge_basis",
            "source_to_storage_observed",
            "storage_to_access_observed",
            "same_data_end_to_end_status",
            "business_fdp_decision",
            "risk_decision",
        ),
    )
    overlap, overlap_meta = _bounded(value.get("same_data_field_overlap"), limit=8)
    if overlap:
        result["same_data_field_overlap"] = overlap
    if overlap_meta.get("truncated"):
        result["same_data_field_overlap_projection"] = overlap_meta
    missing, missing_meta = _bounded(value.get("missing_links"), limit=8)
    if missing:
        result["missing_links"] = missing
    if missing_meta.get("truncated"):
        result["missing_link_projection"] = missing_meta
    source_paths = [item for item in (_compact_fdp_path(v) for v in _sequence(value.get("source_paths"))[:2]) if item]
    access_paths = [item for item in (_compact_fdp_path(v) for v in _sequence(value.get("access_paths"))[:2]) if item]
    if source_paths:
        result["source_paths"] = source_paths
    if access_paths:
        result["access_paths"] = access_paths
    evidence_ids, evidence_meta = _bounded(value.get("evidence_ids"), limit=8)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if evidence_meta.get("truncated"):
        result["evidence_projection"] = evidence_meta
    return result or None


def _compact_fdp_storage_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "repo_id",
            "storage_object",
            "source_path_count",
            "access_path_count",
            "source_field_count",
            "access_field_count",
            "exact_case_count",
            "confirmed_case_count",
            "aggregation_policy",
        ),
    )
    overlap, overlap_meta = _bounded(value.get("overlap_fields"), limit=12)
    if overlap:
        result["overlap_fields"] = overlap
    if overlap_meta.get("truncated"):
        result["overlap_field_projection"] = overlap_meta
    return result or None


def _fdp_priority_path(value: Mapping[str, Any]) -> tuple[int, int, str, str]:
    maturity = str(value.get("evidence_maturity_level") or value.get("lineage_status") or "")
    source_status = str((value.get("source_interpretation") or {}).get("status") or "") if isinstance(value.get("source_interpretation"), Mapping) else ""
    return (
        0 if maturity == "confirmed" else 1,
        0 if source_status == "confirmed_external_ingress" else 1,
        str(value.get("storage_object") or ""),
        str(value.get("path_id") or ""),
    )


def _fdp_priority_case(value: Mapping[str, Any]) -> tuple[int, int, str, str, str]:
    confirmed = str(value.get("same_data_end_to_end_status") or "") == "confirmed"
    both = bool(value.get("source_to_storage_observed")) and bool(value.get("storage_to_access_observed"))
    return (
        0 if confirmed else 1,
        0 if both else 1,
        str(value.get("storage_object") or ""),
        str(value.get("storage_field") or ""),
        str(value.get("case_id") or ""),
    )


def project_foreign_data_persistence_guidance(
    *,
    system_id: str,
    revision_id: str,
    token: str,
    paths_result: Mapping[str, Any],
    cases_result: Mapping[str, Any],
    interpretation_policy: Mapping[str, Any],
    limits: Mapping[str, int],
) -> dict[str, Any]:
    """Build a compact facts-only FDP view from canonical KLC query results.

    Existing path/case statuses, exact field identities and business-decision boundaries
    are copied verbatim. Selection prefers already-confirmed mechanical evidence but
    does not create or upgrade a lineage relation.
    """
    raw_paths = [v for v in _sequence(paths_result.get("items")) if isinstance(v, Mapping)]
    raw_cases = [v for v in _sequence(cases_result.get("items")) if isinstance(v, Mapping)]
    selected_paths = sorted(raw_paths, key=_fdp_priority_path)[: int(limits["path_limit"])]
    selected_cases = sorted(raw_cases, key=_fdp_priority_case)[: int(limits["case_limit"])]
    paths = [item for item in (_compact_fdp_path(v) for v in selected_paths) if item]
    cases = [item for item in (_compact_fdp_case(v) for v in selected_cases) if item]

    case_summary = dict(cases_result.get("summary") or {})
    storage_raw = [v for v in _sequence(case_summary.pop("storage_summaries", [])) if isinstance(v, Mapping)]
    storage_raw.sort(
        key=lambda value: (
            0 if int(value.get("confirmed_case_count") or 0) > 0 else 1,
            0 if (value.get("overlap_fields") or []) else 1,
            str(value.get("storage_object") or ""),
        )
    )
    storage_selected = storage_raw[: int(limits["storage_summary_limit"])]
    storage_summaries = [item for item in (_compact_fdp_storage_summary(v) for v in storage_selected) if item]

    evidence_ids: set[str] = set()
    _collect_evidence_ids(paths, evidence_ids)
    _collect_evidence_ids(cases, evidence_ids)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for result in (paths_result, cases_result):
        for raw in _sequence(result.get("evidence")):
            if not isinstance(raw, Mapping):
                continue
            evidence_id = str(raw.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id not in evidence_ids or evidence_id in evidence_by_id:
                continue
            compact = _pick(raw, ("evidence_id", "repo_id", "path", "line_start", "line_end", "extractor", "maturity"))
            snippet = _text(raw.get("snippet"), limit=300)
            if snippet:
                compact["snippet"] = snippet
            if compact:
                evidence_by_id[evidence_id] = compact
    evidence_limit = int(limits["evidence_limit"])
    evidence = [evidence_by_id[key] for key in sorted(evidence_by_id)[:evidence_limit]]

    path_summary = dict(paths_result.get("summary") or {})
    path_page = dict(paths_result.get("pagination") or {})
    case_page = dict(cases_result.get("pagination") or {})
    return {
        "schema_version": "knowledge_api/v1",
        "guidance_schema_version": FOREIGN_DATA_PERSISTENCE_GUIDANCE_SCHEMA_VERSION,
        "system_id": system_id,
        "revision_id": revision_id,
        "token": token,
        "path_summary": path_summary,
        "case_summary": case_summary,
        "paths": paths,
        "cases": cases,
        "storage_summaries": storage_summaries,
        "interpretation_policy": dict(interpretation_policy),
        "evidence": evidence,
        "projection": {
            "semantic_derivation": "none",
            "selection_basis": "existing KLC maturity/same-data status, then deterministic identity ordering",
            "limits": {str(key): int(value) for key, value in limits.items()},
            "path_source": {
                "source_total": int(path_summary.get("path_count") or len(raw_paths)),
                "read_returned": len(raw_paths),
                "read_truncated": bool(path_page.get("truncated")),
                "presented": len(paths),
                "presentation_truncated": len(raw_paths) > len(paths) or bool(path_page.get("truncated")),
            },
            "case_source": {
                "source_total": int(case_summary.get("case_count") or len(raw_cases)),
                "read_returned": len(raw_cases),
                "read_truncated": bool(case_page.get("truncated")),
                "presented": len(cases),
                "presentation_truncated": len(raw_cases) > len(cases) or bool(case_page.get("truncated")),
            },
            "storage_summary_source": {
                "source_total": int(case_summary.get("storage_summary_count") or len(storage_raw)),
                "presented": len(storage_summaries),
                "presentation_truncated": len(storage_raw) > len(storage_summaries),
            },
            "evidence_source": {
                "referenced_total": len(evidence_by_id),
                "presented": len(evidence),
                "presentation_truncated": len(evidence_by_id) > len(evidence),
            },
            "canonical_detail_endpoint": "/foreign-data-persistence/query",
            "interpretation_boundary": (
                "This projection preserves technical static lineage only. Confirmed external ingress does not assign "
                "an upstream system, business ownership, legal FDP classification or risk verdict; only KLC-confirmed "
                "exact storage-object+field path pairs may be reported as confirmed same-data bridges."
            ),
        },
    }


def _compact_reference_representation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        (
            "reference_object_id",
            "representation_kind",
            "repo_id",
            "name",
            "qualified_name",
            "syntax_kind",
            "container_kind",
            "entries_count",
            "source_set",
            "is_production_evidence",
            "included_in_production_view",
            "definition_mode_observed",
            "repository_embedded_definition_evidence_present",
            "definition_authority_interpretation",
            "own_nsi_status",
        ),
    )
    sample, sample_meta = _bounded(value.get("sample_entries"), limit=4)
    if sample:
        result["sample_entries"] = sample
    if sample_meta.get("truncated"):
        result["sample_entries_projection"] = sample_meta
    evidence_ids, evidence_meta = _bounded(value.get("evidence_ids"), limit=4)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if evidence_meta.get("truncated"):
        result["evidence_projection"] = evidence_meta
    return result or None


def _compact_reference_local_definition(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        ("candidate_id", "representation_kind", "definition_mode", "source_set", "basis"),
    )
    evidence_ids, meta = _bounded(value.get("evidence_ids"), limit=4)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if meta.get("truncated"):
        result["evidence_projection"] = meta
    return result or None


def _compact_reference_literal_write(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        ("write_id", "repo_id", "target_table", "operation", "columns", "parameterized", "source_set"),
    )
    evidence_ids, meta = _bounded(value.get("evidence_ids"), limit=4)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if meta.get("truncated"):
        result["evidence_projection"] = meta
    return result or None


def _compact_reference_usage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(
        value,
        ("observation_kind", "record_id", "fact_id", "fact_type", "repo_id", "name", "source_set"),
    )
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        compact_properties = _pick(
            properties,
            (
                "boundary_role", "direction", "kind", "operation", "path", "schema_ref",
                "topic_property_key", "target_table", "qualified_table_name", "table_name",
                "column_name", "field", "container", "source_operation", "storage_target",
                "storage_field", "join_type", "left_table", "right_table", "configuration_path",
                "source_path", "fact_kind", "dependency_kind",
            ),
        )
        if compact_properties:
            result["properties"] = compact_properties
    evidence_ids, meta = _bounded(value.get("evidence_ids"), limit=4)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if meta.get("truncated"):
        result["evidence_projection"] = meta
    return result or None


def _compact_reference_gap(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = _pick(value, ("gap_id", "repo_id", "gap_kind", "name", "source_set"))
    properties = value.get("properties")
    if isinstance(properties, Mapping):
        compact_properties = _pick(
            properties,
            ("reason", "operation", "container", "field", "missing_links", "source_path"),
        )
        if compact_properties:
            result["properties"] = compact_properties
    evidence_ids, meta = _bounded(value.get("evidence_ids"), limit=4)
    if evidence_ids:
        result["evidence_ids"] = evidence_ids
    if meta.get("truncated"):
        result["evidence_projection"] = meta
    return result or None


def _representative_reference_usage(values: list[Mapping[str, Any]], limit: int) -> list[Mapping[str, Any]]:
    # Deterministically expose breadth before depth: one observed item per usage kind,
    # then fill remaining slots in canonical source order. This is presentation only.
    selected: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    seen_kinds: set[str] = set()
    for value in values:
        kind = str(value.get("observation_kind") or "")
        if kind and kind not in seen_kinds:
            selected.append(value)
            seen_ids.add(id(value))
            seen_kinds.add(kind)
            if len(selected) >= limit:
                return selected
    for value in values:
        if id(value) in seen_ids:
            continue
        selected.append(value)
        if len(selected) >= limit:
            break
    return selected


def project_reference_data_guidance(
    *,
    system_id: str,
    revision_id: str,
    token: str,
    discovery_result: Mapping[str, Any] | None,
    context_result: Mapping[str, Any] | None,
    semantic_policy: Mapping[str, Any],
    limits: Mapping[str, int],
) -> dict[str, Any]:
    """Build a compact facts-only Reference Data view without assigning NSI semantics."""
    normalized_token = str(token or "").strip()
    source = context_result if normalized_token else discovery_result
    source = source or {}
    summary = dict(source.get("summary") or {})
    items = [v for v in _sequence(source.get("items")) if isinstance(v, Mapping)]

    if normalized_token:
        item = items[0] if items else {}
        raw_candidates = [v for v in _sequence(item.get("candidate_representations")) if isinstance(v, Mapping)]
        raw_local = [v for v in _sequence(item.get("local_definition_evidence")) if isinstance(v, Mapping)]
        raw_writes = [v for v in _sequence(item.get("literal_writes")) if isinstance(v, Mapping)]
        raw_usage = [v for v in _sequence(item.get("usage_observations")) if isinstance(v, Mapping)]
        raw_gaps = [v for v in _sequence(item.get("gaps")) if isinstance(v, Mapping)]
        interpretation_policy = dict(item.get("interpretation_policy") or semantic_policy)
    else:
        raw_candidates = items
        raw_local = []
        raw_writes = []
        raw_usage = []
        raw_gaps = []
        interpretation_policy = dict(semantic_policy)

    candidate_limit = int(limits["candidate_limit"])
    local_limit = int(limits["local_definition_limit"])
    write_limit = int(limits["literal_write_limit"])
    usage_limit = int(limits["usage_limit"])
    gap_limit = int(limits["gap_limit"])
    evidence_limit = int(limits["evidence_limit"])

    candidate_selected = raw_candidates[:candidate_limit]
    local_selected = raw_local[:local_limit]
    write_selected = raw_writes[:write_limit]
    usage_selected = _representative_reference_usage(raw_usage, usage_limit)
    gap_selected = raw_gaps[:gap_limit]

    candidates = [x for x in (_compact_reference_representation(v) for v in candidate_selected) if x]
    if not normalized_token:
        # Discovery needs identity/shape, not value/evidence payloads for every catalog entry.
        # Exact token guidance keeps those details for interpretation.
        for candidate in candidates:
            candidate.pop("sample_entries", None)
            candidate.pop("sample_entries_projection", None)
            candidate.pop("evidence_ids", None)
            candidate.pop("evidence_projection", None)
    local_defs = [x for x in (_compact_reference_local_definition(v) for v in local_selected) if x]
    writes = [x for x in (_compact_reference_literal_write(v) for v in write_selected) if x]
    usage = [x for x in (_compact_reference_usage(v) for v in usage_selected) if x]
    gaps = [x for x in (_compact_reference_gap(v) for v in gap_selected) if x]

    evidence_ids: set[str] = set()
    _collect_evidence_ids(candidates, evidence_ids)
    _collect_evidence_ids(local_defs, evidence_ids)
    _collect_evidence_ids(writes, evidence_ids)
    _collect_evidence_ids(usage, evidence_ids)
    _collect_evidence_ids(gaps, evidence_ids)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for raw in _sequence(source.get("evidence")):
        if not isinstance(raw, Mapping):
            continue
        evidence_id = str(raw.get("evidence_id") or "").strip()
        if not evidence_id or evidence_id not in evidence_ids or evidence_id in evidence_by_id:
            continue
        compact = _pick(raw, ("evidence_id", "repo_id", "path", "line_start", "line_end", "extractor", "maturity"))
        snippet = _text(raw.get("snippet"), limit=300)
        if snippet:
            compact["snippet"] = snippet
        if compact:
            evidence_by_id[evidence_id] = compact
    evidence = [evidence_by_id[k] for k in sorted(evidence_by_id)[:evidence_limit]]

    usage_summary = {
        "source_total": int(summary.get("usage_observation_count") or len(raw_usage)),
        "by_kind": dict(summary.get("usage_kind_counts") or {}),
        "presented": len(usage),
        "truncated": int(summary.get("usage_observation_count") or len(raw_usage)) > len(usage),
    }
    projection = {
        "semantic_derivation": "none",
        "classification_boundary": "reference semantics, definition authority and own-NSI verdict remain consumer interpretation",
        "candidate_projection": {"source_total": int(summary.get("candidate_representation_count") or len(raw_candidates)), "presented": len(candidates), "truncated": int(summary.get("candidate_representation_count") or len(raw_candidates)) > len(candidates)},
        "local_definition_projection": {"source_total": int(summary.get("local_definition_evidence_count") or len(raw_local)), "presented": len(local_defs), "truncated": int(summary.get("local_definition_evidence_count") or len(raw_local)) > len(local_defs)},
        "literal_write_projection": {"source_total": int(summary.get("literal_write_count") or len(raw_writes)), "presented": len(writes), "truncated": int(summary.get("literal_write_count") or len(raw_writes)) > len(writes)},
        "gap_projection": {"source_total": int(summary.get("gap_count") or len(raw_gaps)), "presented": len(gaps), "truncated": int(summary.get("gap_count") or len(raw_gaps)) > len(gaps)},
        "evidence_projection": {"requested_ids": len(evidence_ids), "presented": len(evidence), "truncated": len(evidence_ids) > len(evidence)},
    }
    return {
        "schema_version": "knowledge_api/v1",
        "guidance_schema_version": REFERENCE_DATA_GUIDANCE_SCHEMA_VERSION,
        "system_id": system_id,
        "revision_id": revision_id,
        "token": normalized_token,
        "summary": summary,
        "candidate_representations": candidates,
        "local_definition_evidence": local_defs,
        "literal_writes": writes,
        "usage_summary": usage_summary,
        "usage_observations": usage,
        "gaps": gaps,
        "interpretation_policy": interpretation_policy,
        "evidence": evidence,
        "projection": projection,
    }


def project_system_description_guidance(
    *,
    system_id: str,
    revision_id: str,
    scope_result: Mapping[str, Any],
    composition_result: Mapping[str, Any],
    technologies_result: Mapping[str, Any],
    interfaces_result: Mapping[str, Any],
    integrations_result: Mapping[str, Any],
    events_result: Mapping[str, Any],
    storage_result: Mapping[str, Any],
    journeys_result: Mapping[str, Any],
    gaps_result: Mapping[str, Any],
    coverage_result: Mapping[str, Any],
    limits: Mapping[str, int],
) -> dict[str, Any]:
    """Build a bounded System Description read from canonical KLC reporting queries.

    The projection copies KLC-owned counts/statuses and selects already-ranked items.
    It does not infer business purpose, functional areas, runtime topology, storage
    ownership/relationships, or upgrade evidence/confidence states.
    """
    scope_items = [dict(v) for v in _sequence(scope_result.get("items")) if isinstance(v, Mapping)]
    scope = _pick(
        scope_items[0] if scope_items else {},
        (
            "scope",
            "build_id",
            "producer",
            "producer_version",
            "build_status",
            "capabilities",
            "counts",
            "analysis_scope_kind",
        ),
    )

    composition_items = [v for v in _sequence(composition_result.get("items")) if isinstance(v, Mapping)]
    composition_value = composition_items[0] if composition_items else {}
    repositories = [
        _pick(value, ("repo_id", "scope_id"))
        for value in _sequence(composition_value.get("repositories"))
        if isinstance(value, Mapping)
    ]
    modules = [
        item
        for item in (
            _compact_system_description_module(value)
            for value in _sequence(composition_value.get("modules"))
        )
        if item
    ]
    composition = {
        "summary": dict(composition_result.get("summary") or {}),
        "repositories": repositories,
        "modules": modules,
    }

    technologies = _system_description_section(
        technologies_result,
        compact=_compact_system_description_technology,
        limit=int(limits["technology_limit"]),
        source_total=int(technologies_result.get("summary", {}).get("declared_dependency_count") or 0)
        + int(technologies_result.get("summary", {}).get("plugin_count") or 0),
    )
    interfaces = _system_description_section(
        interfaces_result,
        compact=_compact_system_description_interface,
        limit=int(limits["interface_limit"]),
        source_total=int(interfaces_result.get("summary", {}).get("selected_count") or 0),
    )
    integrations = _system_description_section(
        integrations_result,
        compact=_compact_system_description_interface,
        limit=int(limits["integration_limit"]),
        source_total=int(integrations_result.get("summary", {}).get("integration_count") or 0),
    )
    events = _system_description_section(
        events_result,
        compact=_compact_system_description_interface,
        limit=int(limits["event_limit"]),
        source_total=int(events_result.get("summary", {}).get("selected_count") or 0),
    )
    storage = _system_description_section(
        storage_result,
        compact=_compact_system_description_storage,
        limit=int(limits["storage_limit"]),
        source_total=int(storage_result.get("summary", {}).get("table_count") or 0),
    )
    journeys = _system_description_section(
        journeys_result,
        compact=_compact_system_description_journey,
        limit=int(limits["journey_limit"]),
        source_total=int(journeys_result.get("summary", {}).get("scenario_count") or 0),
    )

    raw_gap_items = [dict(v) for v in _sequence(gaps_result.get("items")) if isinstance(v, Mapping)]
    gap_items = raw_gap_items[: int(limits["gap_limit"])]
    gaps = {
        "summary": dict(gaps_result.get("summary") or {}),
        "items": gap_items,
        "presentation": {
            "source_total": int(gaps_result.get("summary", {}).get("group_count") or len(raw_gap_items)),
            "presented": len(gap_items),
            "truncated": int(gaps_result.get("summary", {}).get("group_count") or len(raw_gap_items)) > len(gap_items),
        },
    }
    coverage_items = [dict(v) for v in _sequence(coverage_result.get("items")) if isinstance(v, Mapping)]
    coverage = {
        "summary": dict(coverage_result.get("summary") or {}),
        "items": coverage_items,
    }

    selected_sections = {
        "composition": composition,
        "technologies": technologies,
        "interfaces": interfaces,
        "integrations": integrations,
        "events": events,
        "storage_targets": storage,
        "representative_journeys": journeys,
    }
    evidence_ids: set[str] = set()
    _collect_evidence_ids(selected_sections, evidence_ids)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for result in (
        composition_result,
        technologies_result,
        interfaces_result,
        integrations_result,
        events_result,
        storage_result,
    ):
        for raw in _sequence(result.get("evidence")):
            compact = _compact_system_description_evidence(raw)
            if not compact:
                continue
            evidence_id = str(compact.get("evidence_id") or "")
            if evidence_id and evidence_id in evidence_ids and evidence_id not in evidence_by_id:
                evidence_by_id[evidence_id] = compact

    return {
        "schema_version": "knowledge_api/v1",
        "guidance_schema_version": SYSTEM_DESCRIPTION_GUIDANCE_SCHEMA_VERSION,
        "system_id": system_id,
        "revision_id": revision_id,
        "scope": scope,
        "composition": composition,
        "observed_inventory": {
            "technologies": technologies,
            "interfaces": interfaces,
            "integrations": integrations,
            "events": events,
            "storage_targets": storage,
        },
        "representative_journeys": journeys,
        "coverage": coverage,
        "gaps": gaps,
        "evidence": [evidence_by_id[key] for key in sorted(evidence_by_id)],
        "projection": {
            "semantic_derivation": "none",
            "selection_basis": "canonical KLC query ordering and representative selection",
            "limits": {str(key): int(value) for key, value in limits.items()},
            "canonical_detail_endpoint": "/system-description/query",
            "interpretation_boundary": (
                "Business purpose and functional-area labels are not produced by this projection; "
                "they remain consumer interpretations over the returned static-analysis evidence."
            ),
        },
    }
