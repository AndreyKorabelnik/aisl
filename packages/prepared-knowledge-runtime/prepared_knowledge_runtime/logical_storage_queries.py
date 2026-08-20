from __future__ import annotations

import json
from typing import Any


class LogicalStorageMappingUnavailableError(RuntimeError):
    pass


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def get_logical_storage_object_context(query: Any, object_id: str) -> dict[str, Any]:
    """Return exact logical→storage bindings for one code-declared type occurrence.

    This is a read projection over logical-storage-model-mapping/v2.  It never
    performs fuzzy matching or invents a physical JOIN.
    """
    required = {
        "logical_storage_entity_mapping",
        "logical_storage_relationship_mapping",
        "logical_storage_join_semantic",
        "logical_storage_mapping_gap",
    }
    if not all(query._has_relation(name) for name in required):
        raise LogicalStorageMappingUnavailableError(
            "logical-storage-model-mapping/v2 relations are unavailable"
        )

    with query._connect() as con:
        entity_rows = query._rows(con.execute(
            """
            SELECT entity_mapping_id, storage_observation_id, storage_repo_id,
                   storage_alias, storage_key_expression, logical_repo_id,
                   logical_type_occurrence_id, logical_fully_qualified_name,
                   mapping_status, mapping_basis, candidate_logical_type_ids_json,
                   payload_json
            FROM logical_storage_entity_mapping
            WHERE logical_type_occurrence_id = ?
               OR ? IN (SELECT unnest(CAST(candidate_logical_type_ids_json AS VARCHAR[])))
            ORDER BY mapping_status, storage_repo_id, storage_alias, storage_observation_id
            """,
            [object_id, object_id],
        ))
        relationship_rows = query._rows(con.execute(
            """
            SELECT relationship_mapping_id, storage_observation_id, storage_repo_id,
                   storage_relation_kind, source_alias, source_field, target_alias,
                   source_logical_repo_id, source_logical_type_occurrence_id,
                   effective_field_occurrence_id, field_is_inherited,
                   declared_target_type_occurrence_id, declared_target_fqcn,
                   observed_target_type_occurrence_id, observed_target_fqcn,
                   target_alignment, knowledge_class, storage_key_expression,
                   mapping_status, mapping_basis, payload_json
            FROM logical_storage_relationship_mapping
            WHERE source_logical_type_occurrence_id = ?
            ORDER BY source_field, storage_repo_id, storage_observation_id
            """,
            [object_id],
        ))
        join_rows = query._rows(con.execute(
            """
            SELECT join_semantic_id, relationship_occurrence_id,
                   source_logical_repo_id, source_logical_type_occurrence_id,
                   source_fqcn, source_field_occurrence_id, source_field,
                   declared_target_type_occurrence_id, declared_target_fqcn,
                   join_kind, status, join_readiness,
                   source_reference_expressions_json, target_identity_expressions_json,
                   target_key_fields_json, structural_correspondences_json,
                   candidate_count, basis_json, provenance_json, diagnostics_json
            FROM logical_storage_join_semantic
            WHERE source_logical_type_occurrence_id = ?
            ORDER BY source_field, declared_target_fqcn, relationship_occurrence_id
            """,
            [object_id],
        ))
        observation_ids = [
            str(row.get("storage_observation_id") or "")
            for row in [*entity_rows, *relationship_rows]
            if str(row.get("storage_observation_id") or "")
        ]
        gaps: list[dict[str, Any]] = []
        if observation_ids:
            placeholders = ",".join("?" for _ in observation_ids)
            gaps = query._rows(con.execute(
                f"""
                SELECT mapping_gap_id, gap_kind, severity, owner_kind, owner_id,
                       message, details_json
                FROM logical_storage_mapping_gap
                WHERE owner_id IN ({placeholders})
                ORDER BY severity, gap_kind, owner_id
                """,
                observation_ids,
            ))

    for row in entity_rows:
        row["candidate_logical_type_ids"] = _json_value(
            row.pop("candidate_logical_type_ids_json", None), []
        )
        row["observed_payload"] = _json_value(row.pop("payload_json", None), {})
    for row in relationship_rows:
        row["observed_payload"] = _json_value(row.pop("payload_json", None), {})
    for row in join_rows:
        row["source_reference_expressions"] = _json_value(row.pop("source_reference_expressions_json", None), [])
        row["target_identity_expressions"] = _json_value(row.pop("target_identity_expressions_json", None), [])
        row["target_key_fields"] = _json_value(row.pop("target_key_fields_json", None), [])
        row["structural_correspondences"] = _json_value(row.pop("structural_correspondences_json", None), [])
        row["basis"] = _json_value(row.pop("basis_json", None), {})
        row["provenance"] = _json_value(row.pop("provenance_json", None), {})
        row["diagnostics"] = _json_value(row.pop("diagnostics_json", None), [])
    for row in gaps:
        row["details"] = _json_value(row.pop("details_json", None), {})

    return {
        "schema_version": "logical-storage-object-context/v2",
        "object_id": object_id,
        "entity_mappings": entity_rows,
        "relationship_mappings": relationship_rows,
        "join_semantics": join_rows,
        "gaps": gaps,
    }
