from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .logical_physical_mapping_ingestion import (
    ResolvedKnowledgeLayerInput,
    ResolvedPersistenceMappingEvidence,
    resolve_knowledge_layer_input,
    resolve_persistence_mapping_evidence,
)
from .logical_physical_mapping_schema import (
    LOGICAL_PHYSICAL_MAPPING_DATABASE,
    LOGICAL_PHYSICAL_MAPPING_DDL,
    LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION,
    LOGICAL_PHYSICAL_MAPPING_SCHEMA_VERSION,
    LOGICAL_PHYSICAL_MAPPING_TABLES,
)
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _normalized_identifier(value: object) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and ((text[0], text[-1]) in {("`", "`"), ('"', '"'), ("[", "]")}):
        text = text[1:-1]
    return text.strip().casefold()


def _json_value(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _table_counts(connection: Any) -> dict[str, int]:
    return {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        for table in LOGICAL_PHYSICAL_MAPPING_TABLES
    }


def _first(items: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    return dict(items[0]) if len(items) == 1 else None


def _gap(
    *,
    source_id: str,
    gap_kind: str,
    owner_kind: str,
    owner_id: str,
    message: str,
    source_ref: Mapping[str, Any] | None = None,
    severity: str = "warning",
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "mapping_gap_id": stable_id("logical_physical_mapping_gap", source_id, gap_kind, owner_kind, owner_id, message),
        "mapping_source_id": source_id,
        "gap_kind": gap_kind,
        "severity": severity,
        "owner_kind": owner_kind,
        "owner_id": owner_id,
        "message": message,
        "source_ref": dict(source_ref or {}),
        "details": dict(details or {}),
    }


def _resolve_code_inventory(code_input: ResolvedKnowledgeLayerInput) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    connection = connect_database(code_input.database_path, read_only=True)
    try:
        types = {
            (str(row[0]), str(row[1])): {
                "repo_id": row[0], "type_id": row[1], "type_occurrence_id": row[2],
                "fully_qualified_name": row[3], "simple_name": row[4],
            }
            for row in connection.execute(
                "SELECT repo_id, type_id, type_occurrence_id, fully_qualified_name, simple_name FROM code_declared_type"
            ).fetchall()
        }
        fields = {
            (str(row[0]), str(row[1])): {
                "repo_id": row[0], "field_id": row[1], "field_occurrence_id": row[2],
                "owner_type_occurrence_id": row[3], "name": row[4],
            }
            for row in connection.execute(
                "SELECT repo_id, field_id, field_occurrence_id, owner_type_occurrence_id, name FROM code_declared_field"
            ).fetchall()
        }
        return types, fields
    finally:
        connection.close()


def _resolve_physical_inventory(physical_input: ResolvedKnowledgeLayerInput) -> dict[str, Any]:
    connection = connect_database(physical_input.database_path, read_only=True)
    try:
        table_rows = connection.execute(
            """SELECT physical_model_table_id, table_name, table_code, package_code_path_json,
                      logical_identity, physical_model_source_id
               FROM physical_model_table ORDER BY physical_model_table_id"""
        ).fetchall()
        tables: dict[str, dict[str, Any]] = {}
        table_name_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in table_rows:
            table = {
                "physical_model_table_id": str(row[0]),
                "table_name": row[1], "table_code": row[2],
                "package_code_path": _json_value(row[3], []),
                "logical_identity": row[4], "physical_model_source_id": row[5],
            }
            tables[table["physical_model_table_id"]] = table
            for name in {str(row[1] or ""), str(row[2] or "")}:
                normalized = _normalized_identifier(name)
                if normalized:
                    table_name_index[normalized].append(table)

        columns: dict[str, dict[str, Any]] = {}
        columns_by_table_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            """SELECT physical_model_column_id, physical_model_table_id, column_name, column_code
               FROM physical_model_column ORDER BY physical_model_column_id"""
        ).fetchall():
            column = {
                "physical_model_column_id": str(row[0]), "physical_model_table_id": str(row[1]),
                "column_name": row[2], "column_code": row[3],
            }
            columns[column["physical_model_column_id"]] = column
            for name in {str(row[2] or ""), str(row[3] or "")}:
                normalized = _normalized_identifier(name)
                if normalized:
                    columns_by_table_name[(column["physical_model_table_id"], normalized)].append(column)

        keys: dict[str, dict[str, Any]] = {}
        keys_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            """SELECT physical_model_key_id, physical_model_table_id, key_kind, column_codes_json
               FROM physical_model_key ORDER BY physical_model_key_id"""
        ).fetchall():
            key = {
                "physical_model_key_id": str(row[0]), "physical_model_table_id": str(row[1]),
                "key_kind": row[2], "column_codes": _json_value(row[3], []),
            }
            keys[key["physical_model_key_id"]] = key
            keys_by_table[key["physical_model_table_id"]].append(key)

        relationships: list[dict[str, Any]] = []
        for row in connection.execute(
            """SELECT physical_model_relationship_id, parent_table_id, child_table_id, joins_json
               FROM physical_model_relationship ORDER BY physical_model_relationship_id"""
        ).fetchall():
            relationships.append({
                "physical_model_relationship_id": str(row[0]),
                "parent_table_id": str(row[1] or ""), "child_table_id": str(row[2] or ""),
                "joins": _json_value(row[3], []),
            })
        return {
            "tables": tables,
            "table_name_index": table_name_index,
            "columns": columns,
            "columns_by_table_name": columns_by_table_name,
            "keys": keys,
            "keys_by_table": keys_by_table,
            "relationships": relationships,
        }
    finally:
        connection.close()


def _schema_filtered_candidates(candidates: list[dict[str, Any]], declared_schema: object) -> tuple[list[dict[str, Any]], bool]:
    schema = _normalized_identifier(declared_schema)
    if not schema:
        return candidates, True
    comparable = [
        item for item in candidates
        if any(_normalized_identifier(part) == schema for part in (item.get("package_code_path") or []))
    ]
    if comparable:
        return comparable, True
    return candidates, False


def _insert_gap(connection: Any, item: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT INTO logical_physical_mapping_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [item["mapping_gap_id"], item["mapping_source_id"], item["gap_kind"], item["severity"],
         item["owner_kind"], item["owner_id"], item["message"],
         canonical_json(item.get("source_ref") or {}) if item.get("source_ref") is not None else None,
         canonical_json(item.get("details") or {})],
    )


def _materialize_one_evidence(
    connection: Any,
    *,
    evidence: ResolvedPersistenceMappingEvidence,
    scope_id: str,
    code_input: ResolvedKnowledgeLayerInput,
    physical_input: ResolvedKnowledgeLayerInput,
    code_types: Mapping[tuple[str, str], Mapping[str, Any]],
    code_fields: Mapping[tuple[str, str], Mapping[str, Any]],
    physical: Mapping[str, Any],
) -> dict[str, int]:
    source_id = stable_id("logical_physical_mapping_source", scope_id, evidence.source_id, evidence.content_fingerprint)
    artifact = evidence.artifact
    connection.execute(
        "INSERT INTO logical_physical_mapping_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [source_id, scope_id, artifact.get("artifact_id"), evidence.content_fingerprint, str(evidence.artifact_path),
         code_input.input_item.get("artifact_id"), code_input.input_item.get("content_fingerprint"), str(code_input.output_path),
         physical_input.input_item.get("artifact_id"), physical_input.input_item.get("content_fingerprint"), str(physical_input.output_path),
         canonical_json(artifact.get("coverage") or {}), canonical_json(artifact.get("diagnostics") or []),
         canonical_json(artifact.get("source_snapshot") or {}), canonical_json(artifact)],
    )
    repo_id = evidence.source_id
    gaps: list[dict[str, Any]] = []
    entity_by_type: dict[str, dict[str, Any]] = {}

    for row in evidence.payload["persistence_type_mappings"]:
        type_id = str(row.get("type_id") or "")
        persistence_id = str(row["persistence_type_mapping_id"])
        logical = code_types.get((repo_id, type_id))
        row_diagnostics: list[dict[str, Any]] = []
        if logical is None:
            gaps.append(_gap(source_id=source_id, gap_kind="logical_type_not_found", owner_kind="persistence_type_mapping",
                             owner_id=persistence_id, message="Persistence type mapping does not resolve to the code-declared model.",
                             source_ref=row.get("source_ref"), details={"repo_id": repo_id, "type_id": type_id}))

        persistence_kind = str(row.get("persistence_kind") or "unknown")
        declared_table = str(row.get("table_name_explicit") or "").strip() or None
        candidates: list[dict[str, Any]] = []
        status = "unresolved"
        basis = "explicit_table_annotation"
        selected: dict[str, Any] | None = None
        if persistence_kind in {"mapped_superclass", "embeddable"}:
            status = "not_applicable"
            basis = "persistence_kind_has_no_table_identity"
        elif not declared_table:
            gaps.append(_gap(source_id=source_id, gap_kind="explicit_table_name_absent", owner_kind="persistence_type_mapping",
                             owner_id=persistence_id, message="No explicit @Table name is available; JPA default naming is not inferred.",
                             source_ref=row.get("source_ref"), details={"persistence_kind": persistence_kind}))
        else:
            candidates = list(physical["table_name_index"].get(_normalized_identifier(declared_table), []))
            candidates, schema_verified = _schema_filtered_candidates(candidates, row.get("schema_name_explicit"))
            if row.get("schema_name_explicit") and not schema_verified and candidates:
                diagnostic = {"code": "declared_schema_not_comparable", "declared_schema": row.get("schema_name_explicit")}
                row_diagnostics.append(diagnostic)
                gaps.append(_gap(source_id=source_id, gap_kind="declared_schema_not_comparable", owner_kind="persistence_type_mapping",
                                 owner_id=persistence_id, message="The physical-model contract has no dedicated schema identity matching the declared schema; table-name evidence remains usable only when unique.",
                                 source_ref=row.get("source_ref"), details=diagnostic))
            if len(candidates) == 1:
                selected = candidates[0]
                status = "matched"
            elif not candidates:
                gaps.append(_gap(source_id=source_id, gap_kind="physical_table_not_found", owner_kind="persistence_type_mapping",
                                 owner_id=persistence_id, message="Explicit table name was not found in the supplied physical model.",
                                 source_ref=row.get("source_ref"), details={"declared_table_name": declared_table}))
            else:
                status = "ambiguous"
                gaps.append(_gap(source_id=source_id, gap_kind="physical_table_ambiguous", owner_kind="persistence_type_mapping",
                                 owner_id=persistence_id, message="Explicit table name resolves to multiple physical tables.",
                                 source_ref=row.get("source_ref"), details={"candidate_ids": [item["physical_model_table_id"] for item in candidates]}))

        entity_mapping_id = stable_id("logical_physical_entity_mapping", source_id, persistence_id)
        entity = {
            "entity_mapping_id": entity_mapping_id, "mapping_source_id": source_id, "repo_id": repo_id,
            "persistence_type_mapping_id": persistence_id, "logical_type_id": type_id,
            "logical_type_occurrence_id": logical.get("type_occurrence_id") if logical else None,
            "logical_fully_qualified_name": row.get("fully_qualified_name") or (logical or {}).get("fully_qualified_name") or type_id,
            "persistence_kind": persistence_kind, "declared_catalog_name": row.get("catalog_name_explicit"),
            "declared_schema_name": row.get("schema_name_explicit"), "declared_table_name": declared_table,
            "physical_model_table_id": selected.get("physical_model_table_id") if selected else None,
            "physical_table_name": selected.get("table_name") if selected else None,
            "physical_table_code": selected.get("table_code") if selected else None,
            "mapping_status": status, "mapping_basis": basis,
            "candidate_ids": [item["physical_model_table_id"] for item in candidates],
            "diagnostics": row_diagnostics, "source_ref": row.get("source_ref") or {}, "payload": row,
        }
        entity_by_type[type_id] = entity
        connection.execute(
            "INSERT INTO logical_physical_entity_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [entity_mapping_id, source_id, repo_id, persistence_id, type_id, entity["logical_type_occurrence_id"],
             entity["logical_fully_qualified_name"], persistence_kind, entity["declared_catalog_name"],
             entity["declared_schema_name"], declared_table, entity["physical_model_table_id"],
             entity["physical_table_name"], entity["physical_table_code"], status, basis,
             canonical_json(entity["candidate_ids"]), canonical_json(row_diagnostics), canonical_json(entity["source_ref"]), canonical_json(row)],
        )

    field_by_id: dict[str, dict[str, Any]] = {}
    for row in evidence.payload["persistence_field_mappings"]:
        persistence_id = str(row["persistence_field_mapping_id"])
        field_id = str(row.get("field_id") or "")
        owner_type_id = str(row.get("owner_type_id") or "")
        logical = code_fields.get((repo_id, field_id))
        owner = entity_by_type.get(owner_type_id)
        role = str(row.get("persistence_role") or "unknown")
        explicit_name = row.get("join_column_name_explicit") if role == "relationship" else row.get("column_name_explicit")
        declared_name = str(explicit_name or "").strip() or None
        status = "unresolved"
        basis = "explicit_join_column_annotation" if role == "relationship" else "explicit_column_annotation"
        candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        diagnostics: list[dict[str, Any]] = []
        if logical is None:
            gaps.append(_gap(source_id=source_id, gap_kind="logical_field_not_found", owner_kind="persistence_field_mapping",
                             owner_id=persistence_id, message="Persistence field mapping does not resolve to the code-declared model.",
                             source_ref=row.get("source_ref"), details={"repo_id": repo_id, "field_id": field_id}))
        if role == "transient":
            status = "not_applicable"
            basis = "explicit_transient_annotation"
        elif owner is None or owner.get("mapping_status") != "matched":
            gaps.append(_gap(source_id=source_id, gap_kind="owner_entity_not_mapped", owner_kind="persistence_field_mapping",
                             owner_id=persistence_id, message="Field cannot be mapped because its owning entity has no unique physical table.",
                             source_ref=row.get("source_ref"), details={"owner_type_id": owner_type_id}))
        elif not declared_name:
            gaps.append(_gap(source_id=source_id, gap_kind="explicit_column_name_absent", owner_kind="persistence_field_mapping",
                             owner_id=persistence_id, message="No explicit column or join-column name is available; JPA default naming is not inferred.",
                             source_ref=row.get("source_ref"), details={"persistence_role": role}))
        else:
            table_id = str(owner.get("physical_model_table_id") or "")
            candidates = list(physical["columns_by_table_name"].get((table_id, _normalized_identifier(declared_name)), []))
            if len(candidates) == 1:
                selected = candidates[0]
                status = "matched"
            elif not candidates:
                gaps.append(_gap(source_id=source_id, gap_kind="physical_column_not_found", owner_kind="persistence_field_mapping",
                                 owner_id=persistence_id, message="Explicit column name was not found in the mapped physical table.",
                                 source_ref=row.get("source_ref"), details={"declared_column_name": declared_name, "physical_model_table_id": table_id}))
            else:
                status = "ambiguous"
                gaps.append(_gap(source_id=source_id, gap_kind="physical_column_ambiguous", owner_kind="persistence_field_mapping",
                                 owner_id=persistence_id, message="Explicit column name resolves to multiple columns in the mapped physical table.",
                                 source_ref=row.get("source_ref"), details={"candidate_ids": [item["physical_model_column_id"] for item in candidates]}))
        field_mapping_id = stable_id("logical_physical_field_mapping", source_id, persistence_id)
        mapped = {
            "field_mapping_id": field_mapping_id, "mapping_source_id": source_id, "entity_mapping_id": owner.get("entity_mapping_id") if owner else None,
            "repo_id": repo_id, "persistence_field_mapping_id": persistence_id, "logical_field_id": field_id,
            "logical_field_occurrence_id": logical.get("field_occurrence_id") if logical else None,
            "logical_field_name": row.get("field_name") or (logical or {}).get("name") or field_id,
            "logical_owner_type_id": owner_type_id, "persistence_role": role,
            "declared_column_name": row.get("column_name_explicit"), "declared_join_column_name": row.get("join_column_name_explicit"),
            "physical_model_column_id": selected.get("physical_model_column_id") if selected else None,
            "physical_column_name": selected.get("column_name") if selected else None,
            "physical_column_code": selected.get("column_code") if selected else None,
            "mapping_status": status, "mapping_basis": basis,
            "candidate_ids": [item["physical_model_column_id"] for item in candidates],
            "diagnostics": diagnostics, "source_ref": row.get("source_ref") or {}, "payload": row,
        }
        field_by_id[field_id] = mapped
        connection.execute(
            "INSERT INTO logical_physical_field_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [field_mapping_id, source_id, mapped["entity_mapping_id"], repo_id, persistence_id, field_id,
             mapped["logical_field_occurrence_id"], mapped["logical_field_name"], owner_type_id, role,
             mapped["declared_column_name"], mapped["declared_join_column_name"], mapped["physical_model_column_id"],
             mapped["physical_column_name"], mapped["physical_column_code"], status, basis,
             canonical_json(mapped["candidate_ids"]), canonical_json(diagnostics), canonical_json(mapped["source_ref"]), canonical_json(row)],
        )

    for row in evidence.payload["persistence_key_mappings"]:
        persistence_id = str(row["persistence_key_mapping_id"])
        field_id = str(row.get("field_id") or "")
        owner_type_id = str(row.get("owner_type_id") or "")
        field_mapping = field_by_id.get(field_id)
        entity = entity_by_type.get(owner_type_id)
        physical_column_id = field_mapping.get("physical_model_column_id") if field_mapping else None
        physical_table_id = entity.get("physical_model_table_id") if entity else None
        key_candidates: list[dict[str, Any]] = []
        if physical_table_id and physical_column_id:
            column = physical["columns"].get(physical_column_id) or {}
            normalized_column = _normalized_identifier(column.get("column_code") or column.get("column_name"))
            for key in physical["keys_by_table"].get(physical_table_id, []):
                codes = {_normalized_identifier(value) for value in key.get("column_codes") or []}
                if normalized_column and normalized_column in codes:
                    key_candidates.append(key)
        status = "matched" if len(key_candidates) == 1 else ("ambiguous" if len(key_candidates) > 1 else "unresolved")
        selected = _first(key_candidates)
        diagnostics: list[dict[str, Any]] = []
        if status != "matched":
            gaps.append(_gap(source_id=source_id, gap_kind="physical_key_not_uniquely_resolved", owner_kind="persistence_key_mapping",
                             owner_id=persistence_id, message="Declared persistence key does not resolve to exactly one physical key.",
                             source_ref=row.get("source_ref"), details={"candidate_ids": [item["physical_model_key_id"] for item in key_candidates]}))
        key_mapping_id = stable_id("logical_physical_key_mapping", source_id, persistence_id)
        connection.execute(
            "INSERT INTO logical_physical_key_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [key_mapping_id, source_id, persistence_id, owner_type_id, field_id or None, row.get("key_kind"),
             row.get("column_name_explicit"), physical_table_id, physical_column_id,
             selected.get("physical_model_key_id") if selected else None, status, "explicit_id_and_column_annotations",
             canonical_json(diagnostics), canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )

    for row in evidence.payload["persistence_relationship_mappings"]:
        persistence_id = str(row["persistence_relationship_mapping_id"])
        field_id = str(row.get("field_id") or "")
        source_type_id = str(row.get("source_type_id") or "")
        target_type_id = str(row.get("target_type_id") or "")
        source_entity = entity_by_type.get(source_type_id)
        target_entity = entity_by_type.get(target_type_id)
        source_field = field_by_id.get(field_id)
        source_table_id = source_entity.get("physical_model_table_id") if source_entity else None
        target_table_id = target_entity.get("physical_model_table_id") if target_entity else None
        source_column_id = source_field.get("physical_model_column_id") if source_field else None
        target_column_candidates: list[dict[str, Any]] = []
        referenced = str(row.get("referenced_column_name_explicit") or "").strip()
        if target_table_id and referenced:
            target_column_candidates = list(physical["columns_by_table_name"].get((target_table_id, _normalized_identifier(referenced)), []))
        target_column = _first(target_column_candidates)
        relation_candidates = []
        if source_table_id and target_table_id and source_column_id and target_column:
            source_column = physical["columns"].get(source_column_id) or {}
            source_code = _normalized_identifier(source_column.get("column_code") or source_column.get("column_name"))
            target_code = _normalized_identifier(target_column.get("column_code") or target_column.get("column_name"))
            for rel in physical["relationships"]:
                table_pair = {rel.get("parent_table_id"), rel.get("child_table_id")}
                if {source_table_id, target_table_id} != table_pair:
                    continue
                for join in rel.get("joins") or []:
                    parent = _normalized_identifier((join or {}).get("parent_column_code"))
                    child = _normalized_identifier((join or {}).get("child_column_code"))
                    if {parent, child} == {source_code, target_code}:
                        relation_candidates.append(rel)
                        break
        endpoints_resolved = bool(source_table_id and target_table_id and source_column_id and target_column)
        status = "matched" if endpoints_resolved and len(relation_candidates) == 1 else "unresolved"
        if endpoints_resolved and len(relation_candidates) > 1:
            status = "ambiguous"
        diagnostics: list[dict[str, Any]] = []
        if not referenced:
            gaps.append(_gap(source_id=source_id, gap_kind="explicit_referenced_column_absent", owner_kind="persistence_relationship_mapping",
                             owner_id=persistence_id, message="No explicit referencedColumnName is available; target key defaults are not inferred.",
                             source_ref=row.get("source_ref")))
        elif len(target_column_candidates) != 1:
            gaps.append(_gap(source_id=source_id, gap_kind="target_physical_column_not_uniquely_resolved", owner_kind="persistence_relationship_mapping",
                             owner_id=persistence_id, message="Referenced target column does not resolve uniquely in the target physical table.",
                             source_ref=row.get("source_ref"), details={"candidate_ids": [item["physical_model_column_id"] for item in target_column_candidates]}))
        if not endpoints_resolved:
            gaps.append(_gap(source_id=source_id, gap_kind="relationship_endpoint_not_mapped", owner_kind="persistence_relationship_mapping",
                             owner_id=persistence_id, message="Relationship mapping has an unresolved logical or physical endpoint.",
                             source_ref=row.get("source_ref")))
        elif not relation_candidates:
            gaps.append(_gap(source_id=source_id, gap_kind="physical_relationship_not_found", owner_kind="persistence_relationship_mapping",
                             owner_id=persistence_id, message="Explicit relationship endpoints and join columns are mapped, but no matching physical relationship is present in the supplied physical model.",
                             source_ref=row.get("source_ref"), details={"source_table_id": source_table_id, "target_table_id": target_table_id}))
        elif len(relation_candidates) > 1:
            gaps.append(_gap(source_id=source_id, gap_kind="physical_relationship_ambiguous", owner_kind="persistence_relationship_mapping",
                             owner_id=persistence_id, message="Explicit relationship endpoints and join columns resolve to multiple physical relationships.",
                             source_ref=row.get("source_ref"), details={"candidate_ids": [item["physical_model_relationship_id"] for item in relation_candidates]}))
        relationship_mapping_id = stable_id("logical_physical_relationship_mapping", source_id, persistence_id)
        selected_rel = _first(relation_candidates)
        connection.execute(
            "INSERT INTO logical_physical_relationship_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [relationship_mapping_id, source_id, persistence_id, field_id, source_type_id, target_type_id or None,
             source_entity.get("entity_mapping_id") if source_entity else None,
             target_entity.get("entity_mapping_id") if target_entity else None,
             row.get("relationship_kind"), row.get("join_column_name_explicit"), row.get("referenced_column_name_explicit"),
             source_table_id, target_table_id, source_column_id,
             target_column.get("physical_model_column_id") if target_column else None,
             selected_rel.get("physical_model_relationship_id") if selected_rel else None,
             status, "explicit_relationship_and_join_column_annotations", canonical_json(diagnostics),
             canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )

    for row in evidence.payload["mapping_gaps"]:
        original_id = str(row.get("mapping_gap_id") or "")
        gaps.append(_gap(source_id=source_id, gap_kind=str(row.get("gap_kind") or "core_persistence_mapping_gap"),
                         owner_kind=str(row.get("owner_kind") or "core_evidence"), owner_id=original_id,
                         message=str(row.get("message") or "Core persistence mapping evidence gap."),
                         source_ref=row.get("source_ref"), severity=str(row.get("severity") or "warning"), details=row))
    for item in gaps:
        _insert_gap(connection, item)
    return {
        "logical_physical_mapping_source": 1,
        "logical_physical_entity_mapping": len(evidence.payload["persistence_type_mappings"]),
        "logical_physical_field_mapping": len(evidence.payload["persistence_field_mappings"]),
        "logical_physical_key_mapping": len(evidence.payload["persistence_key_mappings"]),
        "logical_physical_relationship_mapping": len(evidence.payload["persistence_relationship_mappings"]),
        "logical_physical_mapping_gap": len(gaps),
    }


def _validate(connection: Any, *, source_count: int) -> dict[str, Any]:
    checks = {
        "source_count_matches": int(connection.execute("SELECT count(*) FROM logical_physical_mapping_source").fetchone()[0]) == source_count,
        "duplicate_entity_mapping_ids": int(connection.execute(
            "SELECT count(*) FROM (SELECT entity_mapping_id FROM logical_physical_entity_mapping GROUP BY entity_mapping_id HAVING count(*) > 1)"
        ).fetchone()[0]),
        "duplicate_field_mapping_ids": int(connection.execute(
            "SELECT count(*) FROM (SELECT field_mapping_id FROM logical_physical_field_mapping GROUP BY field_mapping_id HAVING count(*) > 1)"
        ).fetchone()[0]),
        "entity_status_counts": {
            str(row[0]): int(row[1]) for row in connection.execute(
                "SELECT mapping_status, count(*) FROM logical_physical_entity_mapping GROUP BY mapping_status ORDER BY mapping_status"
            ).fetchall()
        },
        "field_status_counts": {
            str(row[0]): int(row[1]) for row in connection.execute(
                "SELECT mapping_status, count(*) FROM logical_physical_field_mapping GROUP BY mapping_status ORDER BY mapping_status"
            ).fetchall()
        },
        "key_status_counts": {
            str(row[0]): int(row[1]) for row in connection.execute(
                "SELECT mapping_status, count(*) FROM logical_physical_key_mapping GROUP BY mapping_status ORDER BY mapping_status"
            ).fetchall()
        },
        "relationship_status_counts": {
            str(row[0]): int(row[1]) for row in connection.execute(
                "SELECT mapping_status, count(*) FROM logical_physical_relationship_mapping GROUP BY mapping_status ORDER BY mapping_status"
            ).fetchall()
        },
        "jpa_default_naming_inference_used": False,
        "name_similarity_matching_used": False,
    }
    if not checks["source_count_matches"] or checks["duplicate_entity_mapping_ids"] or checks["duplicate_field_mapping_ids"]:
        raise ValueError(f"logical-physical mapping validation failed: {checks}")
    return checks


def _mapping_coverage(
    *,
    counts: Mapping[str, int],
    checks: Mapping[str, Any],
    logical_type_count: int,
    physical_table_count: int,
    source_count: int,
) -> dict[str, Any]:
    status_counts_by_kind = {
        "entity": dict(checks.get("entity_status_counts") or {}),
        "field": dict(checks.get("field_status_counts") or {}),
        "key": dict(checks.get("key_status_counts") or {}),
        "relationship": dict(checks.get("relationship_status_counts") or {}),
    }
    status_totals: dict[str, int] = {}
    for values in status_counts_by_kind.values():
        for status, count in values.items():
            status_totals[str(status)] = status_totals.get(str(status), 0) + int(count or 0)
    observed = sum(status_totals.values())
    not_applicable = int(status_totals.get("not_applicable") or 0)
    applicable = observed - not_applicable
    matched = int(status_totals.get("matched") or 0)
    unresolved = int(status_totals.get("unresolved") or 0)
    ambiguous = int(status_totals.get("ambiguous") or 0)
    gap_count = int(counts.get("logical_physical_mapping_gap") or 0)
    if observed == 0:
        mapping_coverage_status = "no_mapping_evidence"
    elif matched == applicable and gap_count == 0:
        mapping_coverage_status = "complete_for_observed_mapping_evidence"
    else:
        mapping_coverage_status = "partial"
    return {
        "analysis_status": "complete" if gap_count == 0 else "partial",
        "mapping_coverage_status": mapping_coverage_status,
        "mapping_coverage_basis": "observed_explicit_persistence_mapping_records_only",
        "source_count": int(source_count),
        "logical_declared_type_count": int(logical_type_count),
        "physical_table_count": int(physical_table_count),
        "observed_mapping_count": observed,
        "applicable_mapping_count": applicable,
        "matched_mapping_count": matched,
        "unresolved_mapping_count": unresolved,
        "ambiguous_mapping_count": ambiguous,
        "not_applicable_mapping_count": not_applicable,
        "gap_count": gap_count,
        "status_counts": dict(sorted(status_totals.items())),
        "status_counts_by_kind": status_counts_by_kind,
        "does_not_claim_all_logical_objects_are_mapped": True,
        "does_not_claim_all_physical_objects_are_mapped": True,
    }


def build_logical_physical_mapping_knowledge_layer(
    persistence_evidence_items: Sequence[Mapping[str, Any]],
    code_declared_knowledge_item: Mapping[str, Any],
    physical_model_knowledge_item: Mapping[str, Any],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    if not persistence_evidence_items:
        raise ValueError("logical-physical mapping requires at least one java-persistence-mapping-evidence artifact")
    evidence = tuple(resolve_persistence_mapping_evidence(item) for item in persistence_evidence_items)
    code_input = resolve_knowledge_layer_input(
        code_declared_knowledge_item,
        model_kind="code-declared-data-model",
        schema_version="code-declared-data-model/v1",
        source_materialization_id="code-declared-data-model",
    )
    physical_input = resolve_knowledge_layer_input(
        physical_model_knowledge_item,
        model_kind="physical-data-model",
        schema_version="knowledge_layer_physical_model/v1",
        source_materialization_id="physical-model",
    )
    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path)
    staging_path.mkdir(parents=True)
    database_path = staging_path / LOGICAL_PHYSICAL_MAPPING_DATABASE
    started_at = utc_now()
    build_id = stable_id(
        "logical_physical_mapping_build", scope_id,
        *(item.content_fingerprint for item in evidence),
        code_input.input_item.get("content_fingerprint"), physical_input.input_item.get("content_fingerprint"), __version__,
    )
    connection = None
    try:
        code_types, code_fields = _resolve_code_inventory(code_input)
        physical = _resolve_physical_inventory(physical_input)
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, LOGICAL_PHYSICAL_MAPPING_DDL)
        connection.execute(
            "INSERT INTO logical_physical_mapping_build VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [build_id, scope_id, __version__, LOGICAL_PHYSICAL_MAPPING_SCHEMA_VERSION,
             LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION, "building", started_at, canonical_json({}), canonical_json({})],
        )
        for item in evidence:
            _materialize_one_evidence(
                connection, evidence=item, scope_id=scope_id, code_input=code_input, physical_input=physical_input,
                code_types=code_types, code_fields=code_fields, physical=physical,
            )
        checks = _validate(connection, source_count=len(evidence))
        counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute(
            "UPDATE logical_physical_mapping_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None
        repository_ids = tuple(sorted({item.source_id for item in evidence}))
        product_coverage = _mapping_coverage(
            counts=counts,
            checks=checks,
            logical_type_count=len(code_types),
            physical_table_count=len(physical["tables"]),
            source_count=len(evidence),
        )
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=repository_ids,
            modes=("data-model",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("logical-physical-entity-mapping", "logical-physical-field-mapping", "mapping-gaps"),
            capabilities=("common.logical-physical-mapping", "common.entity-table-mapping", "common.field-column-mapping"),
            artifacts={"database": LOGICAL_PHYSICAL_MAPPING_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple({
                "artifact_id": item.artifact.get("artifact_id"), "artifact_kind": item.artifact.get("artifact_kind"),
                "schema_version": item.artifact.get("schema_version"), "content_fingerprint": item.content_fingerprint,
                "artifact_path": str(item.artifact_path), "source_snapshot": item.artifact.get("source_snapshot") or {},
            } for item in evidence) + (
                {"knowledge_artifact_id": code_input.input_item.get("artifact_id"), "schema_version": "code-declared-data-model/v1", "output_path": str(code_input.output_path)},
                {"knowledge_artifact_id": physical_input.input_item.get("artifact_id"), "schema_version": "knowledge_layer_physical_model/v1", "output_path": str(physical_input.output_path)},
            ),
            validation_status="complete",
            validation=checks,
            metadata={
                "mapping_schema_version": LOGICAL_PHYSICAL_MAPPING_SCHEMA_VERSION,
                "mapping_policy": "explicit_identifiers_unique_exact_match_only",
                "jpa_default_naming_inference": False,
                "name_similarity_matching": False,
                "schema_catalog_qualifiers": "preserved_without_inference",
                "started_at": started_at,
                "completed_at": completed_at,
                "coverage": product_coverage,
            },
        )
        write_manifest(staging_path / "knowledge-layer-manifest.json", manifest)
        publish_directory_atomic(staging_path, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging_path)
        raise
