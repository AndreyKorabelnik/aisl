from __future__ import annotations

import json
from typing import Any


class ModelStorageSemanticsUnavailableError(RuntimeError):
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


def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["source_refs"] = _json_value(row.pop("source_refs_json", None), [])
        row["observed_payload"] = _json_value(row.pop("payload_json", None), {})
    return rows


def get_model_storage_object_context(query: Any, source_fqcn: str) -> dict[str, Any]:
    """Return observed storage semantics whose exact source alias is the FQCN."""
    required = {
        "model_storage_record",
        "model_storage_reference",
        "model_storage_key_lineage",
        "model_storage_reference_derivation",
    }
    if not all(query._has_relation(name) for name in required):
        raise ModelStorageSemanticsUnavailableError(
            "model-storage-semantics/v1 relations are unavailable"
        )

    with query._connect() as con:
        records = _normalize(query._rows(con.execute(
            """
            SELECT observation_id, repo_id, api_framework, owner_fqcn,
                   owner_operation, storage_alias, storage_key_field,
                   storage_key_expression, source_refs_json, payload_json
            FROM model_storage_record
            WHERE storage_alias = ?
            ORDER BY repo_id, observation_id
            """,
            [source_fqcn],
        )))
        references = _normalize(query._rows(con.execute(
            """
            SELECT observation_id, repo_id, api_framework, source_owner_fqcn,
                   source_operation, source_alias, source_field, reference_operation,
                   target_converter_operation, target_alias, target_storage_key_field,
                   target_storage_key_expression, source_refs_json, payload_json
            FROM model_storage_reference
            WHERE source_alias = ?
            ORDER BY source_field, repo_id, observation_id
            """,
            [source_fqcn],
        )))
        key_lineage = _normalize(query._rows(con.execute(
            """
            SELECT observation_id, repo_id, api_framework, source_owner_fqcn,
                   source_operation, source_alias, relationship_field,
                   reference_operation, target_alias, source_key_expression,
                   target_key_expression_template, composed_target_key_expression,
                   source_key_passed_into_target_key, source_refs_json, payload_json
            FROM model_storage_key_lineage
            WHERE source_alias = ?
            ORDER BY relationship_field, repo_id, observation_id
            """,
            [source_fqcn],
        )))
        derivations = _normalize(query._rows(con.execute(
            """
            SELECT observation_id, repo_id, api_framework, source_owner_fqcn,
                   source_operation, source_alias, relationship_field,
                   reference_operation, value_converter_operation,
                   composed_reference_value_expression, source_refs_json, payload_json
            FROM model_storage_reference_derivation
            WHERE source_alias = ?
            ORDER BY relationship_field, repo_id, observation_id
            """,
            [source_fqcn],
        )))

    return {
        "schema_version": "model-storage-object-context/v1",
        "source_fqcn": source_fqcn,
        "storage_records": records,
        "storage_references": references,
        "storage_key_lineage": key_lineage,
        "reference_value_derivations": derivations,
    }
