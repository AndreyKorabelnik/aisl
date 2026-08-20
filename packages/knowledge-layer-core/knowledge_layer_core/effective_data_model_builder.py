from __future__ import annotations

import json
import os
import uuid
from contextlib import suppress
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from .effective_data_model_schema import (
    EFFECTIVE_DATA_MODEL_DATABASE,
    EFFECTIVE_DATA_MODEL_DDL,
    EFFECTIVE_DATA_MODEL_SCHEMA_VERSION,
    EFFECTIVE_DATA_MODEL_TABLES,
    MODEL_DOMAIN_CLUSTER_VIEW_SCHEMA_VERSION,
)
from prepared_knowledge_runtime.io import write_manifest
from .logical_physical_mapping_ingestion import ResolvedKnowledgeLayerInput, resolve_knowledge_layer_input
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _json(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _rows(connection: Any, sql: str, parameters: Sequence[object] | None = None) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, list(parameters or ()))
    names = [str(item[0]) for item in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _table_counts(connection: Any) -> dict[str, int]:
    return {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        for table in EFFECTIVE_DATA_MODEL_TABLES
    }


def _input(
    item: Mapping[str, Any],
    *,
    model_kind: str,
    schema_version: str,
    source_materialization_id: str,
) -> ResolvedKnowledgeLayerInput:
    return resolve_knowledge_layer_input(
        item,
        model_kind=model_kind,
        schema_version=schema_version,
        source_materialization_id=source_materialization_id,
    )


def _source_row(scope_id: str, role: str, source: ResolvedKnowledgeLayerInput) -> list[object]:
    item = source.input_item
    manifest = source.manifest
    source_id = stable_id(
        "effective_data_model_source",
        scope_id,
        role,
        item.get("artifact_id"),
        item.get("content_fingerprint"),
    )
    return [
        source_id,
        scope_id,
        role,
        item.get("model_kind"),
        item.get("schema_version"),
        item.get("source_materialization_id"),
        item.get("artifact_id"),
        item.get("content_fingerprint"),
        str(source.output_path),
        str(source.manifest_path),
        canonical_json((manifest.get("metadata") or {}).get("coverage") or {}),
        canonical_json(manifest.get("metadata") or {}),
        canonical_json({
            "source_evidence": manifest.get("source_evidence") or [],
            "validation_status": manifest.get("validation_status"),
            "validation": manifest.get("validation") or {},
        }),
    ]


def _group_one(rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        grouped[tuple(str(item.get(key) or "") for key in keys)].append(dict(item))
    return grouped


def _gap(
    *,
    source_layer: str,
    gap_kind: str,
    message: str,
    source_gap_id: object = None,
    severity: str = "warning",
    owner_kind: object = None,
    owner_id: object = None,
    details: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    effective_gap_id = stable_id(
        "effective_data_model_gap",
        source_layer,
        source_gap_id,
        gap_kind,
        owner_kind,
        owner_id,
        message,
    )
    return {
        "effective_gap_id": effective_gap_id,
        "source_layer": source_layer,
        "source_gap_id": str(source_gap_id or "") or None,
        "gap_kind": gap_kind,
        "severity": severity,
        "owner_kind": str(owner_kind or "") or None,
        "owner_id": str(owner_id or "") or None,
        "message": message,
        "details": dict(details or {}),
        "provenance": dict(provenance or {}),
    }


def _insert_gap(connection: Any, item: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT INTO effective_data_model_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            item["effective_gap_id"], item["source_layer"], item.get("source_gap_id"), item["gap_kind"],
            item["severity"], item.get("owner_kind"), item.get("owner_id"), item["message"],
            canonical_json(item.get("details") or {}), canonical_json(item.get("provenance") or {}),
        ],
    )


def _copy_input_gaps(
    connection: Any,
    *,
    code: ResolvedKnowledgeLayerInput,
    physical: ResolvedKnowledgeLayerInput,
    mapping: ResolvedKnowledgeLayerInput,
) -> None:
    code_connection = connect_database(code.database_path, read_only=True)
    try:
        for row in _rows(code_connection, "SELECT * FROM code_declared_model_gap ORDER BY gap_occurrence_id"):
            _insert_gap(connection, _gap(
                source_layer="code_declared_data_model",
                source_gap_id=row.get("gap_occurrence_id"),
                gap_kind=str(row.get("gap_code") or "code_declared_gap"),
                severity=str(row.get("severity") or "warning"),
                owner_kind=row.get("owner_kind"),
                owner_id=row.get("owner_occurrence_id"),
                message=str(row.get("message") or "Code-declared model gap."),
                details={"source_refs": _json(row.get("source_refs_json"), []), "payload": _json(row.get("payload_json"), {})},
                provenance={"source_artifact_id": code.input_item.get("artifact_id")},
            ))
    finally:
        code_connection.close()

    physical_connection = connect_database(physical.database_path, read_only=True)
    try:
        for row in _rows(physical_connection, "SELECT * FROM physical_model_gap ORDER BY physical_model_gap_id"):
            _insert_gap(connection, _gap(
                source_layer="physical_data_model",
                source_gap_id=row.get("physical_model_gap_id"),
                gap_kind=str(row.get("gap_kind") or "physical_model_gap"),
                owner_kind="physical_object",
                owner_id=row.get("owner_pdm_object_id"),
                message=str(row.get("message") or "Physical model gap."),
                details={"unresolved_ref": row.get("unresolved_ref")},
                provenance={"source_artifact_id": physical.input_item.get("artifact_id")},
            ))
    finally:
        physical_connection.close()

    mapping_connection = connect_database(mapping.database_path, read_only=True)
    try:
        for row in _rows(mapping_connection, "SELECT * FROM logical_physical_mapping_gap ORDER BY mapping_gap_id"):
            _insert_gap(connection, _gap(
                source_layer="logical_physical_mapping",
                source_gap_id=row.get("mapping_gap_id"),
                gap_kind=str(row.get("gap_kind") or "logical_physical_mapping_gap"),
                severity=str(row.get("severity") or "warning"),
                owner_kind=row.get("owner_kind"),
                owner_id=row.get("owner_id"),
                message=str(row.get("message") or "Logical/physical mapping gap."),
                details=_json(row.get("details_json"), {}),
                provenance={
                    "source_artifact_id": mapping.input_item.get("artifact_id"),
                    "source_ref": _json(row.get("source_ref_json"), {}),
                },
            ))
    finally:
        mapping_connection.close()


def _load_inventories(
    code: ResolvedKnowledgeLayerInput,
    physical: ResolvedKnowledgeLayerInput,
    mapping: ResolvedKnowledgeLayerInput,
) -> dict[str, Any]:
    code_connection = connect_database(code.database_path, read_only=True)
    try:
        code_types = _rows(code_connection, "SELECT * FROM code_declared_type ORDER BY repo_id, fully_qualified_name, type_occurrence_id")
        code_fields = _rows(code_connection, "SELECT * FROM code_declared_field ORDER BY repo_id, field_occurrence_id")
        effective_fields = _rows(code_connection, "SELECT * FROM code_declared_effective_field ORDER BY repo_id, effective_owner_type_occurrence_id, field_name, field_occurrence_id")
        relationships = _rows(code_connection, "SELECT * FROM code_declared_relationship ORDER BY repo_id, relationship_occurrence_id")
    finally:
        code_connection.close()

    physical_connection = connect_database(physical.database_path, read_only=True)
    try:
        physical_tables = _rows(physical_connection, "SELECT * FROM physical_model_table ORDER BY physical_model_table_id")
        physical_columns = _rows(physical_connection, "SELECT * FROM physical_model_column ORDER BY physical_model_column_id")
        physical_keys = _rows(physical_connection, "SELECT * FROM physical_model_key ORDER BY physical_model_key_id")
        physical_relationships = _rows(physical_connection, "SELECT * FROM physical_model_relationship ORDER BY physical_model_relationship_id")
    finally:
        physical_connection.close()

    mapping_connection = connect_database(mapping.database_path, read_only=True)
    try:
        mapping_sources = _rows(mapping_connection, "SELECT mapping_source_id, source_snapshot_json FROM logical_physical_mapping_source ORDER BY mapping_source_id")
        entity_mappings = _rows(mapping_connection, "SELECT * FROM logical_physical_entity_mapping ORDER BY repo_id, logical_type_id, entity_mapping_id")
        field_mappings = _rows(mapping_connection, "SELECT * FROM logical_physical_field_mapping ORDER BY repo_id, logical_field_id, field_mapping_id")
        key_mappings = _rows(mapping_connection, "SELECT * FROM logical_physical_key_mapping ORDER BY mapping_source_id, key_mapping_id")
        relationship_mappings = _rows(mapping_connection, "SELECT * FROM logical_physical_relationship_mapping ORDER BY mapping_source_id, relationship_mapping_id")
    finally:
        mapping_connection.close()

    source_repo = {
        str(row["mapping_source_id"]): str((_json(row.get("source_snapshot_json"), {}) or {}).get("source_id") or "")
        for row in mapping_sources
    }
    for row in key_mappings:
        row["repo_id"] = source_repo.get(str(row.get("mapping_source_id") or ""), "")
    for row in relationship_mappings:
        row["repo_id"] = source_repo.get(str(row.get("mapping_source_id") or ""), "")

    return {
        "code_types": code_types,
        "code_fields": code_fields,
        "effective_fields": effective_fields,
        "code_relationships": relationships,
        "physical_tables": physical_tables,
        "physical_columns": physical_columns,
        "physical_keys": physical_keys,
        "physical_relationships": physical_relationships,
        "entity_mappings": entity_mappings,
        "field_mappings": field_mappings,
        "key_mappings": key_mappings,
        "relationship_mappings": relationship_mappings,
    }


def _mapping_choice(
    connection: Any,
    grouped: Mapping[tuple[str, ...], list[dict[str, Any]]],
    key: tuple[str, ...],
    *,
    owner_kind: str,
    owner_id: str,
) -> dict[str, Any] | None:
    candidates = grouped.get(key, [])
    if len(candidates) <= 1:
        return dict(candidates[0]) if candidates else None
    _insert_gap(connection, _gap(
        source_layer="effective_data_model_composition",
        gap_kind="multiple_mapping_rows_for_logical_object",
        owner_kind=owner_kind,
        owner_id=owner_id,
        message="More than one logical/physical mapping row refers to the same logical object; no mapping was selected.",
        details={"candidate_ids": [
            item.get("entity_mapping_id") or item.get("field_mapping_id") or item.get("relationship_mapping_id")
            for item in candidates
        ]},
    ))
    return None


def _insert_composition(
    connection: Any,
    *,
    scope_id: str,
    inventory: Mapping[str, Any],
    code_input: ResolvedKnowledgeLayerInput,
    physical_input: ResolvedKnowledgeLayerInput,
    mapping_input: ResolvedKnowledgeLayerInput,
) -> dict[str, Any]:
    code_types = [dict(row) for row in inventory["code_types"]]
    code_fields = [dict(row) for row in inventory["code_fields"]]
    effective_fields = [dict(row) for row in inventory["effective_fields"]]
    code_relationships = [dict(row) for row in inventory["code_relationships"]]
    physical_tables = [dict(row) for row in inventory["physical_tables"]]
    physical_columns = [dict(row) for row in inventory["physical_columns"]]
    physical_keys = [dict(row) for row in inventory["physical_keys"]]
    physical_relationships = [dict(row) for row in inventory["physical_relationships"]]
    entity_mappings = [dict(row) for row in inventory["entity_mappings"]]
    field_mappings = [dict(row) for row in inventory["field_mappings"]]
    key_mappings = [dict(row) for row in inventory["key_mappings"]]
    relationship_mappings = [dict(row) for row in inventory["relationship_mappings"]]

    type_by_occurrence = {str(row["type_occurrence_id"]): row for row in code_types}
    field_by_occurrence = {str(row["field_occurrence_id"]): row for row in code_fields}
    physical_table_by_id = {str(row["physical_model_table_id"]): row for row in physical_tables}
    physical_column_by_id = {str(row["physical_model_column_id"]): row for row in physical_columns}

    entities_by_logical = _group_one(entity_mappings, ("repo_id", "logical_type_id"))
    fields_by_logical = _group_one(field_mappings, ("repo_id", "logical_field_id"))
    relationships_by_logical = _group_one(relationship_mappings, ("repo_id", "logical_field_id"))

    entity_by_occurrence: dict[str, dict[str, Any]] = {}
    entity_by_logical: dict[tuple[str, str], dict[str, Any]] = {}
    entity_mapping_by_id: dict[str, dict[str, Any]] = {str(row.get("entity_mapping_id") or ""): row for row in entity_mappings}

    for logical in code_types:
        repo_id = str(logical["repo_id"])
        type_id = str(logical["type_id"])
        mapping = _mapping_choice(
            connection,
            entities_by_logical,
            (repo_id, type_id),
            owner_kind="logical_type",
            owner_id=type_id,
        )
        status = str((mapping or {}).get("mapping_status") or "not_mapped")
        basis = str((mapping or {}).get("mapping_basis") or "no_persistence_type_mapping")
        physical_id = str((mapping or {}).get("physical_model_table_id") or "") or None
        physical = physical_table_by_id.get(str(physical_id or ""))
        if status == "matched" and physical is None:
            _insert_gap(connection, _gap(
                source_layer="effective_data_model_composition",
                gap_kind="mapped_physical_table_missing",
                owner_kind="logical_type",
                owner_id=type_id,
                message="A matched entity mapping references a physical table absent from the supplied physical model.",
                details={"physical_model_table_id": physical_id},
            ))
            status = "unresolved"
            physical_id = None
        layer_status = {
            "matched": "cross_layer_matched",
            "not_applicable": "logical_only_not_applicable",
            "unresolved": "logical_only_unresolved_mapping",
            "ambiguous": "logical_only_ambiguous_mapping",
            "not_mapped": "logical_only_no_persistence_mapping",
        }.get(status, "logical_only_unresolved_mapping")
        effective_entity_id = stable_id("effective_data_model_entity", scope_id, repo_id, logical["type_occurrence_id"])
        row = {
            "effective_entity_id": effective_entity_id,
            "repo_id": repo_id,
            "logical_type_id": type_id,
            "logical_type_occurrence_id": str(logical["type_occurrence_id"]),
            "entity_mapping_id": (mapping or {}).get("entity_mapping_id"),
            "mapping_status": status,
            "physical_model_table_id": physical_id,
        }
        entity_by_occurrence[str(logical["type_occurrence_id"])] = row
        entity_by_logical[(repo_id, type_id)] = row
        connection.execute(
            "INSERT INTO effective_data_model_entity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                effective_entity_id, scope_id, repo_id, type_id, logical["type_occurrence_id"],
                logical["fully_qualified_name"], logical["simple_name"], logical.get("package_name"), logical["type_kind"],
                (mapping or {}).get("persistence_kind"), (mapping or {}).get("entity_mapping_id"), status, basis,
                physical_id, (physical or {}).get("table_name"), (physical or {}).get("table_code"), layer_status,
                canonical_json(["code_declared_data_model"] + (["logical_physical_mapping", "physical_data_model"] if physical_id else [])),
                canonical_json(_json((mapping or {}).get("diagnostics_json"), [])),
                canonical_json({
                    "logical": {"source_artifact_id": code_input.input_item.get("artifact_id"), "type_occurrence_id": logical["type_occurrence_id"]},
                    "mapping": {"source_artifact_id": mapping_input.input_item.get("artifact_id"), "entity_mapping_id": (mapping or {}).get("entity_mapping_id")},
                    "physical": {"source_artifact_id": physical_input.input_item.get("artifact_id"), "physical_model_table_id": physical_id},
                }),
            ],
        )

    for effective in effective_fields:
        field = field_by_occurrence.get(str(effective["field_occurrence_id"]))
        owner_entity = entity_by_occurrence.get(str(effective["effective_owner_type_occurrence_id"]))
        if field is None or owner_entity is None:
            _insert_gap(connection, _gap(
                source_layer="effective_data_model_composition",
                gap_kind="effective_field_reference_missing",
                owner_kind="effective_field",
                owner_id=str(effective.get("effective_field_occurrence_id") or ""),
                message="Code-declared effective field references a missing field or owner type.",
                details=dict(effective),
                severity="error",
            ))
            continue
        repo_id = str(effective["repo_id"])
        logical_field_id = str(field["field_id"])
        mapping = _mapping_choice(
            connection,
            fields_by_logical,
            (repo_id, logical_field_id),
            owner_kind="logical_field",
            owner_id=logical_field_id,
        )
        status = str((mapping or {}).get("mapping_status") or "not_mapped")
        basis = str((mapping or {}).get("mapping_basis") or "no_persistence_field_mapping")
        physical_column_id = str((mapping or {}).get("physical_model_column_id") or "") or None
        physical = physical_column_by_id.get(str(physical_column_id or ""))
        diagnostics = list(_json((mapping or {}).get("diagnostics_json"), []))
        if bool(effective.get("is_inherited")) and mapping is not None:
            declared_entity_mapping_id = str(mapping.get("entity_mapping_id") or "")
            effective_entity_mapping_id = str(owner_entity.get("entity_mapping_id") or "")
            if not declared_entity_mapping_id or declared_entity_mapping_id != effective_entity_mapping_id:
                diagnostics.append({
                    "code": "inherited_field_requires_persistence_inheritance_mapping",
                    "message": "The declared field mapping is not reused across a different effective owner without explicit persistence inheritance evidence.",
                })
                status = "unresolved"
                basis = "persistence_inheritance_mapping_required"
                physical_column_id = None
                physical = None
                _insert_gap(connection, _gap(
                    source_layer="effective_data_model_composition",
                    gap_kind="inherited_field_requires_persistence_inheritance_mapping",
                    owner_kind="logical_field",
                    owner_id=logical_field_id,
                    message="Inherited logical field cannot be attached to the effective owner's physical table without explicit persistence inheritance evidence.",
                    details={
                        "declared_entity_mapping_id": declared_entity_mapping_id or None,
                        "effective_entity_mapping_id": effective_entity_mapping_id or None,
                    },
                ))
        if status == "matched" and physical is None:
            status = "unresolved"
            physical_column_id = None
            _insert_gap(connection, _gap(
                source_layer="effective_data_model_composition",
                gap_kind="mapped_physical_column_missing",
                owner_kind="logical_field",
                owner_id=logical_field_id,
                message="A matched field mapping references a physical column absent from the supplied physical model.",
            ))
        layer_status = {
            "matched": "cross_layer_matched",
            "not_applicable": "logical_only_not_applicable",
            "unresolved": "logical_only_unresolved_mapping",
            "ambiguous": "logical_only_ambiguous_mapping",
            "not_mapped": "logical_only_no_persistence_mapping",
        }.get(status, "logical_only_unresolved_mapping")
        effective_field_id = stable_id(
            "effective_data_model_field",
            scope_id,
            repo_id,
            effective["effective_field_occurrence_id"],
        )
        connection.execute(
            "INSERT INTO effective_data_model_field VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                effective_field_id, owner_entity["effective_entity_id"], repo_id, logical_field_id,
                field["field_occurrence_id"], field["name"], field["declared_type_expression"],
                field.get("normalized_type_expression"), bool(effective.get("is_inherited")), int(effective.get("inherited_depth") or 0),
                (mapping or {}).get("persistence_role"), (mapping or {}).get("field_mapping_id"), status, basis,
                physical_column_id, (physical or {}).get("column_name"), (physical or {}).get("column_code"),
                (physical or {}).get("data_type"), (physical or {}).get("mandatory"), layer_status,
                canonical_json(["code_declared_data_model"] + (["logical_physical_mapping", "physical_data_model"] if physical_column_id else [])),
                canonical_json(diagnostics),
                canonical_json({
                    "logical": {"source_artifact_id": code_input.input_item.get("artifact_id"), "effective_field_occurrence_id": effective["effective_field_occurrence_id"], "field_occurrence_id": field["field_occurrence_id"]},
                    "mapping": {"source_artifact_id": mapping_input.input_item.get("artifact_id"), "field_mapping_id": (mapping or {}).get("field_mapping_id")},
                    "physical": {"source_artifact_id": physical_input.input_item.get("artifact_id"), "physical_model_column_id": physical_column_id},
                }),
            ],
        )

    for mapping in key_mappings:
        repo_id = str(mapping.get("repo_id") or "")
        entity = entity_by_logical.get((repo_id, str(mapping.get("logical_type_id") or "")))
        effective_key_id = stable_id("effective_data_model_key", scope_id, repo_id, mapping.get("key_mapping_id"))
        connection.execute(
            "INSERT INTO effective_data_model_key VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                effective_key_id, (entity or {}).get("effective_entity_id"), repo_id,
                mapping.get("logical_type_id"), mapping.get("logical_field_id"), mapping.get("key_kind"),
                mapping.get("key_mapping_id"), mapping.get("mapping_status"), mapping.get("mapping_basis"),
                mapping.get("physical_model_table_id"), mapping.get("physical_model_column_id"), mapping.get("physical_model_key_id"),
                mapping.get("diagnostics_json") or canonical_json([]),
                canonical_json({
                    "mapping": {"source_artifact_id": mapping_input.input_item.get("artifact_id"), "key_mapping_id": mapping.get("key_mapping_id")},
                    "physical": {"source_artifact_id": physical_input.input_item.get("artifact_id")},
                }),
            ],
        )

    effective_relationship_rows: list[dict[str, Any]] = []
    for logical in code_relationships:
        repo_id = str(logical["repo_id"])
        field = field_by_occurrence.get(str(logical["field_occurrence_id"]))
        source_entity = entity_by_occurrence.get(str(logical["source_type_occurrence_id"]))
        target_entity = entity_by_occurrence.get(str(logical["target_type_occurrence_id"]))
        if field is None or source_entity is None or target_entity is None:
            _insert_gap(connection, _gap(
                source_layer="effective_data_model_composition",
                gap_kind="logical_relationship_reference_missing",
                owner_kind="logical_relationship",
                owner_id=str(logical.get("relationship_occurrence_id") or ""),
                message="Code-declared relationship references a missing field or endpoint type.",
                details=dict(logical),
                severity="error",
            ))
            continue
        logical_field_id = str(field["field_id"])
        mapping = _mapping_choice(
            connection,
            relationships_by_logical,
            (repo_id, logical_field_id),
            owner_kind="logical_relationship",
            owner_id=logical_field_id,
        )
        status = str((mapping or {}).get("mapping_status") or "not_mapped")
        basis = str((mapping or {}).get("mapping_basis") or "no_persistence_relationship_mapping")
        effective_relationship_id = stable_id(
            "effective_data_model_relationship",
            scope_id,
            repo_id,
            logical["relationship_occurrence_id"],
        )
        layer_status = "cross_layer_matched" if status == "matched" else "logical_only_" + status
        connection.execute(
            "INSERT INTO effective_data_model_relationship VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                effective_relationship_id, repo_id, logical["relationship_occurrence_id"],
                source_entity["effective_entity_id"], target_entity["effective_entity_id"],
                logical_field_id, field["field_occurrence_id"], logical["relationship_kind"],
                (mapping or {}).get("relationship_mapping_id"), status, basis,
                (mapping or {}).get("source_physical_table_id"), (mapping or {}).get("target_physical_table_id"),
                (mapping or {}).get("source_physical_column_id"), (mapping or {}).get("target_physical_column_id"),
                (mapping or {}).get("physical_model_relationship_id"), layer_status,
                (mapping or {}).get("diagnostics_json") or canonical_json([]),
                canonical_json({
                    "logical": {"source_artifact_id": code_input.input_item.get("artifact_id"), "relationship_occurrence_id": logical["relationship_occurrence_id"]},
                    "mapping": {"source_artifact_id": mapping_input.input_item.get("artifact_id"), "relationship_mapping_id": (mapping or {}).get("relationship_mapping_id")},
                    "physical": {"source_artifact_id": physical_input.input_item.get("artifact_id"), "physical_model_relationship_id": (mapping or {}).get("physical_model_relationship_id")},
                }),
            ],
        )
        effective_relationship_rows.append({
            "effective_relationship_id": effective_relationship_id,
            "source_effective_entity_id": source_entity["effective_entity_id"],
            "target_effective_entity_id": target_entity["effective_entity_id"],
            "physical_model_relationship_id": (mapping or {}).get("physical_model_relationship_id"),
        })

    matched_tables = {str(row.get("physical_model_table_id")) for row in entity_mappings if row.get("mapping_status") == "matched" and row.get("physical_model_table_id")}
    matched_columns = {str(row.get("physical_model_column_id")) for row in field_mappings if row.get("mapping_status") == "matched" and row.get("physical_model_column_id")}
    matched_columns.update(str(row.get("physical_model_column_id")) for row in key_mappings if row.get("mapping_status") == "matched" and row.get("physical_model_column_id"))
    for row in relationship_mappings:
        if row.get("mapping_status") == "matched":
            matched_columns.update(str(row.get(key)) for key in ("source_physical_column_id", "target_physical_column_id") if row.get(key))
    matched_keys = {str(row.get("physical_model_key_id")) for row in key_mappings if row.get("mapping_status") == "matched" and row.get("physical_model_key_id")}
    matched_relationships = {str(row.get("physical_model_relationship_id")) for row in relationship_mappings if row.get("mapping_status") == "matched" and row.get("physical_model_relationship_id")}

    def insert_unmapped(kind: str, object_id: str, parent_id: object, name: object, code: object) -> None:
        connection.execute(
            "INSERT INTO effective_data_model_unmapped_physical_object VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                stable_id("effective_data_model_unmapped_physical_object", kind, object_id),
                kind, object_id, parent_id, name, code, "not_referenced_by_matched_explicit_mapping",
                canonical_json(["physical_data_model"]),
                canonical_json({"source_artifact_id": physical_input.input_item.get("artifact_id"), "physical_object_id": object_id}),
            ],
        )

    for row in physical_tables:
        object_id = str(row["physical_model_table_id"])
        if object_id not in matched_tables:
            insert_unmapped("table", object_id, None, row.get("table_name"), row.get("table_code"))
    for row in physical_columns:
        object_id = str(row["physical_model_column_id"])
        if object_id not in matched_columns:
            insert_unmapped("column", object_id, row.get("physical_model_table_id"), row.get("column_name"), row.get("column_code"))
    for row in physical_keys:
        object_id = str(row["physical_model_key_id"])
        if object_id not in matched_keys:
            insert_unmapped("key", object_id, row.get("physical_model_table_id"), row.get("key_name"), row.get("key_code"))
    for row in physical_relationships:
        object_id = str(row["physical_model_relationship_id"])
        if object_id not in matched_relationships:
            insert_unmapped("relationship", object_id, None, row.get("relationship_name"), row.get("relationship_code"))

    domain_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for logical in code_types:
        entity = entity_by_occurrence[str(logical["type_occurrence_id"])]
        domain_key = str(logical.get("package_name") or "<default-package>")
        domain_members[domain_key].append(entity)
    for domain_key in sorted(domain_members):
        members = sorted(item["effective_entity_id"] for item in domain_members[domain_key])
        tables = sorted({str(item.get("physical_model_table_id")) for item in domain_members[domain_key] if item.get("physical_model_table_id")})
        domain_id = stable_id("model_domain", scope_id, "code_package", domain_key)
        connection.execute(
            "INSERT INTO model_domain VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                domain_id, scope_id, "code_package", domain_key, domain_key,
                "technical_grouping_not_business_domain", canonical_json(members), canonical_json(tables),
                "exact_code_package_membership", canonical_json({"source_artifact_id": code_input.input_item.get("artifact_id")}),
            ],
        )

    entity_ids = sorted(item["effective_entity_id"] for item in entity_by_occurrence.values())
    parent = {item: item for item in entity_ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for row in effective_relationship_rows:
        union(row["source_effective_entity_id"], row["target_effective_entity_id"])
    components: dict[str, list[str]] = defaultdict(list)
    for item in entity_ids:
        components[find(item)].append(item)
    relation_by_component: dict[str, list[str]] = defaultdict(list)
    for row in effective_relationship_rows:
        relation_by_component[find(row["source_effective_entity_id"])].append(row["effective_relationship_id"])
    entity_record_by_id = {item["effective_entity_id"]: item for item in entity_by_occurrence.values()}
    for ordinal, root in enumerate(sorted(components), start=1):
        members = sorted(components[root])
        tables = sorted({str(entity_record_by_id[item].get("physical_model_table_id")) for item in members if entity_record_by_id[item].get("physical_model_table_id")})
        relationships = sorted(relation_by_component.get(root, []))
        cluster_id = stable_id("model_entity_cluster", scope_id, *members)
        connection.execute(
            "INSERT INTO model_entity_cluster VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                cluster_id, scope_id, "code_declared_relationship_connected_component", f"technical-cluster-{ordinal}",
                "technical_grouping_not_business_domain", canonical_json(members), canonical_json(tables),
                canonical_json(relationships), "weakly_connected_component_of_code_declared_relationships",
                canonical_json({"source_artifact_id": code_input.input_item.get("artifact_id")}),
            ],
        )

    metrics = {
        "logical_entities": len(code_types),
        "logical_fields": len(effective_fields),
        "logical_relationships": len(code_relationships),
        "matched_entities": sum(1 for row in entity_mappings if row.get("mapping_status") == "matched"),
        "matched_fields": sum(1 for row in field_mappings if row.get("mapping_status") == "matched"),
        "matched_keys": sum(1 for row in key_mappings if row.get("mapping_status") == "matched"),
        "matched_relationships": sum(1 for row in relationship_mappings if row.get("mapping_status") == "matched"),
        "physical_tables": len(physical_tables),
        "physical_columns": len(physical_columns),
        "physical_keys": len(physical_keys),
        "physical_relationships": len(physical_relationships),
    }
    for name, value in sorted(metrics.items()):
        group = "logical" if name.startswith("logical_") else "mapping" if name.startswith("matched_") else "physical"
        connection.execute(
            "INSERT INTO effective_data_model_coverage VALUES (?, ?, ?, ?, ?, ?)",
            [stable_id("effective_data_model_coverage", scope_id, group, name), scope_id, group, name, int(value), canonical_json({})],
        )
    return metrics


def _validate(connection: Any, *, source_count: int, expected_entities: int, expected_fields: int) -> dict[str, Any]:
    entity_count = int(connection.execute("SELECT count(*) FROM effective_data_model_entity").fetchone()[0])
    field_count = int(connection.execute("SELECT count(*) FROM effective_data_model_field").fetchone()[0])
    orphan_fields = int(connection.execute(
        """SELECT count(*) FROM effective_data_model_field f
           LEFT JOIN effective_data_model_entity e ON e.effective_entity_id=f.effective_entity_id
           WHERE e.effective_entity_id IS NULL"""
    ).fetchone()[0])
    orphan_relationships = int(connection.execute(
        """SELECT count(*) FROM effective_data_model_relationship r
           LEFT JOIN effective_data_model_entity s ON s.effective_entity_id=r.source_effective_entity_id
           LEFT JOIN effective_data_model_entity t ON t.effective_entity_id=r.target_effective_entity_id
           WHERE s.effective_entity_id IS NULL OR t.effective_entity_id IS NULL"""
    ).fetchone()[0])
    invalid_mapped_entities = int(connection.execute(
        "SELECT count(*) FROM effective_data_model_entity WHERE mapping_status='matched' AND physical_model_table_id IS NULL"
    ).fetchone()[0])
    invalid_mapped_fields = int(connection.execute(
        "SELECT count(*) FROM effective_data_model_field WHERE mapping_status='matched' AND physical_model_column_id IS NULL"
    ).fetchone()[0])
    source_rows = int(connection.execute("SELECT count(*) FROM effective_data_model_source").fetchone()[0])
    cluster_members = []
    for row in connection.execute("SELECT member_effective_entity_ids_json FROM model_entity_cluster").fetchall():
        cluster_members.extend(_json(row[0], []))
    entity_ids = [str(row[0]) for row in connection.execute("SELECT effective_entity_id FROM effective_data_model_entity").fetchall()]
    cluster_members_valid = sorted(cluster_members) == sorted(entity_ids) and len(cluster_members) == len(set(cluster_members))
    checks = {
        "required_source_rows_present": source_rows == source_count,
        "entity_count_matches_code_declared_types": entity_count == expected_entities,
        "field_count_matches_code_declared_effective_fields": field_count == expected_fields,
        "orphan_effective_fields": orphan_fields,
        "orphan_effective_relationships": orphan_relationships,
        "matched_entities_have_physical_table": invalid_mapped_entities == 0,
        "matched_fields_have_physical_column": invalid_mapped_fields == 0,
        "clusters_partition_effective_entities": cluster_members_valid,
        "physical_objects_are_not_promoted_to_logical_entities": True,
        "name_similarity_matching_used": False,
    }
    if not all(value is True or value == 0 for value in checks.values()):
        raise ValueError(f"effective data model validation failed: {checks}")
    return checks


def build_effective_data_model_knowledge_layer(
    code_declared_knowledge_item: Mapping[str, Any],
    physical_model_knowledge_item: Mapping[str, Any],
    logical_physical_mapping_knowledge_item: Mapping[str, Any],
    output: str | Path,
    *,
    scope_id: str,
    optional_knowledge_items: Sequence[Mapping[str, Any]] = (),
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    code = _input(
        code_declared_knowledge_item,
        model_kind="code-declared-data-model",
        schema_version="code-declared-data-model/v1",
        source_materialization_id="code-declared-data-model",
    )
    physical = _input(
        physical_model_knowledge_item,
        model_kind="physical-data-model",
        schema_version="knowledge_layer_physical_model/v1",
        source_materialization_id="physical-model",
    )
    mapping = _input(
        logical_physical_mapping_knowledge_item,
        model_kind="logical-physical-model-mapping",
        schema_version="logical-physical-model-mapping/v1",
        source_materialization_id="logical-physical-mapping",
    )
    optional: list[ResolvedKnowledgeLayerInput] = []
    allowed_optional = {
        ("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
        ("observed-storage-usage", "observed-storage-usage/v1", "observed-storage-usage"),
    }
    for item in optional_knowledge_items:
        identity = (
            str(item.get("model_kind") or ""),
            str(item.get("schema_version") or ""),
            str(item.get("source_materialization_id") or ""),
        )
        if identity not in allowed_optional:
            raise ValueError(f"unsupported optional effective-data-model input: {identity}")
        optional.append(_input(item, model_kind=identity[0], schema_version=identity[1], source_materialization_id=identity[2]))

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path)
    staging_path.mkdir(parents=True)
    database_path = staging_path / EFFECTIVE_DATA_MODEL_DATABASE
    started_at = utc_now()
    build_id = stable_id(
        "effective_data_model_build",
        scope_id,
        code.input_item.get("content_fingerprint"),
        physical.input_item.get("content_fingerprint"),
        mapping.input_item.get("content_fingerprint"),
        *(item.input_item.get("content_fingerprint") for item in optional),
        __version__,
    )
    connection = None
    transaction_started = False
    try:
        inventory = _load_inventories(code, physical, mapping)
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, EFFECTIVE_DATA_MODEL_DDL)
        # The real physical model contributes thousands of explicitly unmapped
        # objects. Keep composition atomic and avoid one autocommit per row.
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        connection.execute(
            "INSERT INTO effective_data_model_build VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [
                build_id, scope_id, __version__, EFFECTIVE_DATA_MODEL_SCHEMA_VERSION,
                MODEL_DOMAIN_CLUSTER_VIEW_SCHEMA_VERSION, "building", started_at,
                canonical_json({}), canonical_json({}),
            ],
        )
        for role, source in (("code_declared", code), ("physical", physical), ("logical_physical_mapping", mapping)):
            connection.execute(
                "INSERT INTO effective_data_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _source_row(scope_id, role, source),
            )
        for source in optional:
            connection.execute(
                "INSERT INTO effective_data_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _source_row(scope_id, "optional_observed_enrichment", source),
            )
        _copy_input_gaps(connection, code=code, physical=physical, mapping=mapping)
        metrics = _insert_composition(
            connection,
            scope_id=scope_id,
            inventory=inventory,
            code_input=code,
            physical_input=physical,
            mapping_input=mapping,
        )
        checks = _validate(
            connection,
            source_count=3 + len(optional),
            expected_entities=len(inventory["code_types"]),
            expected_fields=len(inventory["effective_fields"]),
        )
        counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute(
            "UPDATE effective_data_model_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("COMMIT")
        transaction_started = False
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        repository_ids = tuple(sorted({str(row.get("repo_id") or "") for row in inventory["code_types"] if str(row.get("repo_id") or "")}))
        gap_count = counts.get("effective_data_model_gap", 0)
        source_items = (code, physical, mapping, *optional)
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=repository_ids,
            modes=("data-model",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("effective-data-model", "model-domains", "entity-clusters", "cross-layer-model-coverage"),
            capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
            artifacts={"database": EFFECTIVE_DATA_MODEL_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple({
                "knowledge_artifact_id": item.input_item.get("artifact_id"),
                "model_kind": item.input_item.get("model_kind"),
                "schema_version": item.input_item.get("schema_version"),
                "source_materialization_id": item.input_item.get("source_materialization_id"),
                "content_fingerprint": item.input_item.get("content_fingerprint"),
                "output_path": str(item.output_path),
            } for item in source_items),
            validation_status="complete",
            validation=checks,
            metadata={
                "effective_data_model_schema_version": EFFECTIVE_DATA_MODEL_SCHEMA_VERSION,
                "model_domain_cluster_view_schema_version": MODEL_DOMAIN_CLUSTER_VIEW_SCHEMA_VERSION,
                "composition_policy": "logical_first_explicit_mapping_only",
                "physical_objects_promoted_to_logical_entities": False,
                "name_similarity_matching": False,
                        "optional_observed_enrichments": [item.input_item.get("source_materialization_id") for item in optional],
                "optional_observed_enrichment_policy": "recorded_as_sources_without_declared_semantic_override",
                "metrics": metrics,
                "started_at": started_at,
                "completed_at": completed_at,
                "coverage": {
                    "status": "complete" if gap_count == 0 else "partial",
                    "gap_count": gap_count,
                    "logical_entity_count": counts.get("effective_data_model_entity", 0),
                    "logical_field_count": counts.get("effective_data_model_field", 0),
                    "unmapped_physical_object_count": counts.get("effective_data_model_unmapped_physical_object", 0),
                },
            },
        )
        write_manifest(staging_path / "knowledge-layer-manifest.json", manifest)
        publish_directory_atomic(staging_path, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            if transaction_started:
                with suppress(Exception):
                    connection.execute("ROLLBACK")
            connection.close()
        remove_path(staging_path)
        raise
