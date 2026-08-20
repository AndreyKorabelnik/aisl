from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping


def _props(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("observed_payload")
    if not isinstance(payload, Mapping):
        return {}
    props = payload.get("properties")
    return dict(props) if isinstance(props, Mapping) else {}


def _public_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    props = _props(row)
    keys = (
        "observation_id", "repo_id", "api_framework", "source_owner_fqcn",
        "source_operation", "source_alias", "source_field", "relationship_field",
        "reference_operation", "target_converter_operation", "target_alias",
        "target_storage_key_field", "target_storage_key_expression",
        "source_key_expression", "target_key_expression_template",
        "composed_target_key_expression", "source_key_passed_into_target_key",
        "value_converter_operation", "composed_reference_value_expression",
        "source_refs",
    )
    result = {key: row.get(key) for key in keys if row.get(key) is not None}
    # Preserve additional formalized expression/tree data without exposing the full
    # producer envelope. These values are observed evidence, not API inference.
    for key in (
        "reference_value_expression",
        "composed_reference_value_expression_tree",
        "target_key_expression_tree",
        "source_key_expression_tree",
        "composed_target_key_expression_tree",
    ):
        if key in props and props.get(key) is not None:
            result[key] = props.get(key)
    return result


def _mapping_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relationship_mapping_id": row.get("relationship_mapping_id"),
        "storage_observation_id": row.get("storage_observation_id"),
        "storage_repo_id": row.get("storage_repo_id"),
        "storage_relation_kind": row.get("storage_relation_kind"),
        "source_alias": row.get("source_alias"),
        "source_field": row.get("source_field"),
        "target_alias": row.get("target_alias"),
        "effective_field_occurrence_id": row.get("effective_field_occurrence_id"),
        "field_is_inherited": row.get("field_is_inherited"),
        "declared_target_type_occurrence_id": row.get("declared_target_type_occurrence_id"),
        "declared_target_fqcn": row.get("declared_target_fqcn"),
        "observed_target_type_occurrence_id": row.get("observed_target_type_occurrence_id"),
        "observed_target_fqcn": row.get("observed_target_fqcn"),
        "target_alignment": row.get("target_alignment"),
        "knowledge_class": row.get("knowledge_class"),
        "storage_key_expression": row.get("storage_key_expression"),
        "mapping_status": row.get("mapping_status"),
        "mapping_basis": row.get("mapping_basis"),
    }


def build_data_model_object_context(
    declared_object: Mapping[str, Any],
    *,
    logical_storage: Mapping[str, Any] | None,
    model_storage: Mapping[str, Any] | None,
    published_capabilities: set[str],
) -> dict[str, Any]:
    """Build a deterministic object-centric read projection for external agents.

    All semantic claims come from selected published products. Missing products are
    explicit. The projection does not infer physical SQL joins.
    """
    obj = dict(declared_object)
    declared_relationships = [dict(item) for item in obj.pop("relationships", [])]
    fields = [dict(item) for item in obj.pop("fields", [])]

    logical_storage_available = logical_storage is not None
    model_storage_available = model_storage is not None

    mappings_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    join_semantics_by_relationship: dict[str, dict[str, Any]] = {}
    entity_mappings: list[dict[str, Any]] = []
    mapping_gaps: list[dict[str, Any]] = []
    if logical_storage_available:
        entity_mappings = [dict(row) for row in logical_storage.get("entity_mappings") or ()]
        mapping_gaps = [dict(row) for row in logical_storage.get("gaps") or ()]
        for raw in logical_storage.get("relationship_mappings") or ():
            row = dict(raw)
            mappings_by_field[str(row.get("source_field") or "")].append(row)
        for raw in logical_storage.get("join_semantics") or ():
            row = dict(raw)
            relationship_id = str(row.get("relationship_occurrence_id") or "")
            if relationship_id:
                join_semantics_by_relationship[relationship_id] = row

    references_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lineage_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    derivations_by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    storage_records: list[dict[str, Any]] = []
    if model_storage_available:
        storage_records = [dict(row) for row in model_storage.get("storage_records") or ()]
        for raw in model_storage.get("storage_references") or ():
            row = dict(raw); references_by_field[str(row.get("source_field") or "")].append(row)
        for raw in model_storage.get("storage_key_lineage") or ():
            row = dict(raw); lineage_by_field[str(row.get("relationship_field") or "")].append(row)
        for raw in model_storage.get("reference_value_derivations") or ():
            row = dict(raw); derivations_by_field[str(row.get("relationship_field") or "")].append(row)

    rich_relationships: list[dict[str, Any]] = []
    for declared in declared_relationships:
        field_name = str(declared.get("source_field") or "")
        mappings = mappings_by_field.get(field_name, [])
        exact_mappings = [
            row for row in mappings
            if row.get("mapping_status") == "matched"
            and str(row.get("declared_target_type_occurrence_id") or "")
               == str(declared.get("target_type_occurrence_id") or "")
        ]
        selected = exact_mappings[0] if len(exact_mappings) == 1 else None

        references = references_by_field.get(field_name, [])
        lineages = lineage_by_field.get(field_name, [])
        derivations = derivations_by_field.get(field_name, [])
        observations = [
            *[_public_observation(row) for row in references],
            *[_public_observation(row) for row in lineages],
        ]

        if not logical_storage_available:
            storage_status = "not_available"
            storage_basis = "common.logical-storage-mapping is not published in the selected revision"
        elif selected is not None:
            storage_status = "matched"
            storage_basis = str(selected.get("mapping_basis") or "")
        elif mappings:
            storage_status = "ambiguous" if len(mappings) > 1 else str(mappings[0].get("mapping_status") or "unresolved")
            storage_basis = "published logical-storage mapping does not yield one exact target binding"
        else:
            storage_status = "not_observed"
            storage_basis = "no published storage relationship mapping is bound to this declared field"

        storage_join = join_semantics_by_relationship.get(str(declared.get("relationship_id") or ""))
        if storage_join is None:
            storage_join_projection = {
                "status": "not_available" if not logical_storage_available else "unresolved",
                "join_readiness": "not_ready",
                "join_kind": "not_established",
                "basis": {
                    "match_basis": "logical_storage_mapping_not_published" if not logical_storage_available else "storage_join_semantics_not_published_for_relationship",
                    "physical_join_claimed": False,
                },
            }
        else:
            storage_join_projection = {
                "join_semantic_id": storage_join.get("join_semantic_id"),
                "join_kind": storage_join.get("join_kind"),
                "status": storage_join.get("status"),
                "join_readiness": storage_join.get("join_readiness"),
                "source_reference_expressions": list(storage_join.get("source_reference_expressions") or []),
                "target_identity_expressions": list(storage_join.get("target_identity_expressions") or []),
                "target_key_fields": list(storage_join.get("target_key_fields") or []),
                "structural_correspondences": list(storage_join.get("structural_correspondences") or []),
                "candidate_count": int(storage_join.get("candidate_count") or 0),
                "basis": dict(storage_join.get("basis") or {}),
                "provenance": dict(storage_join.get("provenance") or {}),
                "diagnostics": list(storage_join.get("diagnostics") or []),
            }

        rich_relationships.append({
            "relationship_id": declared.get("relationship_id"),
            "source_field": field_name,
            "declared_relationship": declared,
            "target": {
                "object_id": declared.get("target_type_occurrence_id"),
                "fqcn": declared.get("target_fqcn"),
                "name": declared.get("target_name"),
            },
            "cardinality": {
                "value": declared.get("cardinality_hint"),
                "basis": declared.get("cardinality_basis"),
            },
            "storage_semantics": {
                "status": storage_status,
                "basis": storage_basis,
                "mapping": _mapping_projection(selected) if selected is not None else None,
                "candidate_mappings": [_mapping_projection(row) for row in mappings] if selected is None and mappings else [],
                "observations": observations,
                "reference_value_derivations": [_public_observation(row) for row in derivations],
            },
            "storage_join": storage_join_projection,
            "physical_mapping": {
                "status": "not_observed",
                "physical_join_confirmed": False,
                "basis": "this read model contains declared-model and model-storage knowledge only; no physical SQL/PDM join is asserted",
            },
        })

    storage_identities: list[dict[str, Any]] = []
    for row in entity_mappings:
        observation_id = str(row.get("storage_observation_id") or "")
        record = next((item for item in storage_records if str(item.get("observation_id") or "") == observation_id), None)
        storage_identities.append({
            "status": row.get("mapping_status"),
            "basis": row.get("mapping_basis"),
            "storage_alias": row.get("storage_alias"),
            "storage_key_expression": row.get("storage_key_expression"),
            "storage_repo_id": row.get("storage_repo_id"),
            "observation": _public_observation(record) if record is not None else None,
        })

    storage_context_status = (
        "available" if logical_storage_available else "not_available"
    )
    if logical_storage_available and not model_storage_available:
        storage_context_status = "partial"

    return {
        "object": obj,
        "fields": fields,
        "relationships": rich_relationships,
        "storage_identities": storage_identities,
        "storage_context": {
            "status": storage_context_status,
            "logical_storage_mapping_published": logical_storage_available,
            "model_storage_semantics_published": model_storage_available,
            "required_capability": "common.code-declared-data-model",
            "optional_capabilities": [
                "common.logical-storage-mapping",
                "common.logical-storage-join-semantics",
                "common.model-storage-semantics",
            ],
            "published_optional_capabilities": sorted(
                cap for cap in published_capabilities
                if cap in {"common.logical-storage-mapping", "common.logical-storage-join-semantics", "common.model-storage-semantics"}
            ),
        },
        "gaps": mapping_gaps,
    }
