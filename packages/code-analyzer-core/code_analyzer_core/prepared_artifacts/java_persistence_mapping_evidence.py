from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.prepared_artifacts.java_type_structure_evidence import (
    build_java_type_structure_evidence,
)

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "java-persistence-mapping-evidence"
SCHEMA_VERSION = "java-persistence-mapping-evidence/v1"
ANALYZER_ID = "java-persistence-mapping-analyzer"
RELATIVE_PATH = "evidence/java-persistence-mapping-evidence.json"

_TYPE_ANNOTATIONS = {
    "Entity",
    "MappedSuperclass",
    "Embeddable",
    "Table",
    "SecondaryTable",
    "SecondaryTables",
    "IdClass",
    "Inheritance",
    "DiscriminatorColumn",
    "DiscriminatorValue",
    "Access",
}
_FIELD_ANNOTATIONS = {
    "Id",
    "EmbeddedId",
    "Column",
    "JoinColumn",
    "JoinColumns",
    "JoinTable",
    "OneToOne",
    "OneToMany",
    "ManyToOne",
    "ManyToMany",
    "Embedded",
    "Transient",
    "Version",
    "Basic",
    "Enumerated",
    "Convert",
    "AttributeOverride",
    "AttributeOverrides",
    "AssociationOverride",
    "AssociationOverrides",
    "MapsId",
    "OrderColumn",
    "CollectionTable",
}
_RELATIONSHIP_ANNOTATIONS = {"OneToOne", "OneToMany", "ManyToOne", "ManyToMany"}
_UNSUPPORTED_COMPOSITE_ANNOTATIONS = {
    "SecondaryTables",
    "JoinColumns",
    "JoinTable",
    "AttributeOverride",
    "AttributeOverrides",
    "AssociationOverride",
    "AssociationOverrides",
    "CollectionTable",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    material = "\u001f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _simple_annotation_name(value: Any) -> str:
    return str(value or "").strip().rsplit(".", 1)[-1]


def _argument_map(annotation: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not annotation:
        return result
    for index, raw in enumerate(annotation.get("structured_arguments") or []):
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or ("value" if index == 0 else f"arg_{index}"))
        expression = raw.get("expression_tree") or {}
        literal: Any = None
        literal_status = "not_literal"
        node_type = str(raw.get("node_type") or expression.get("node_type") or "")
        raw_value = raw.get("raw")
        if node_type == "string_literal":
            fragments = [
                str(item.get("value") or "")
                for item in expression.get("children") or []
                if isinstance(item, Mapping) and item.get("node_type") == "string_fragment"
            ]
            literal = "".join(fragments)
            literal_status = "literal"
        elif node_type in {"true", "false"}:
            literal = node_type == "true"
            literal_status = "literal"
        elif node_type in {"decimal_integer_literal", "hex_integer_literal", "octal_integer_literal", "binary_integer_literal"}:
            literal = str(raw_value or expression.get("value") or "")
            literal_status = "literal"
        elif node_type in {"identifier", "field_access", "scoped_identifier"}:
            literal = str(raw_value or expression.get("text") or "")
            literal_status = "symbolic"
        result[name] = {
            "raw": raw_value,
            "node_type": node_type or None,
            "literal_status": literal_status,
            "value": literal,
        }
    return result


def _arg_value(annotation: Mapping[str, Any] | None, name: str) -> Any:
    return (_argument_map(annotation).get(name) or {}).get("value")


def _arg_record(annotation: Mapping[str, Any] | None, name: str) -> dict[str, Any] | None:
    item = _argument_map(annotation).get(name)
    return dict(item) if item else None


def _annotation_index(payload: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("annotation_declarations") or []:
        if not isinstance(item, Mapping):
            continue
        target_id = str(item.get("target_id") or "")
        if target_id:
            result.setdefault(target_id, []).append(dict(item))
    for values in result.values():
        values.sort(key=lambda item: (
            _simple_annotation_name(item.get("annotation_name")),
            str(item.get("annotation_id") or ""),
        ))
    return result


def _annotations_by_name(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        result.setdefault(_simple_annotation_name(item.get("annotation_name")), []).append(item)
    return result


def _first(index: Mapping[str, list[dict[str, Any]]], name: str) -> dict[str, Any] | None:
    values = index.get(name) or []
    return values[0] if values else None


def _source_ref(*items: Mapping[str, Any] | None) -> dict[str, Any]:
    for item in items:
        if isinstance(item, Mapping) and isinstance(item.get("source_ref"), Mapping):
            return dict(item["source_ref"])
    return {"repository_relative_path": "unknown", "line_start": 1, "line_end": 1, "extractor": "java_tree_sitter"}


def _mapping_argument(
    *,
    annotation: Mapping[str, Any] | None,
    argument_name: str,
    diagnostics: list[dict[str, Any]],
    owner_kind: str,
    owner_id: str,
    annotation_name: str,
) -> Any:
    record = _arg_record(annotation, argument_name)
    if record is None:
        return None
    if record.get("literal_status") in {"literal", "symbolic"}:
        return record.get("value")
    diagnostics.append({
        "code": "non_literal_persistence_annotation_argument",
        "severity": "warning",
        "message": f"{annotation_name}.{argument_name} is not a literal or symbolic value and was not resolved.",
        "owner_kind": owner_kind,
        "owner_id": owner_id,
        "annotation_id": (annotation or {}).get("annotation_id"),
        "argument_name": argument_name,
        "raw_expression": record.get("raw"),
        "source_refs": [_source_ref(annotation)],
    })
    return None


def _mapping_annotation_ids(index: Mapping[str, list[dict[str, Any]]], allowed: set[str]) -> list[str]:
    return sorted({
        str(item.get("annotation_id"))
        for name, items in index.items()
        if name in allowed
        for item in items
        if item.get("annotation_id")
    })


def build_java_persistence_mapping_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
) -> dict[str, Any]:
    """Publish declared Java persistence mappings as typed evidence.

    This analyzer normalizes only explicit persistence annotations and their
    source references. It does not match logical names to physical objects,
    apply JPA default naming, inspect observed storage usage, or assign
    confidence scores. Those are KLC or separate evidence responsibilities.
    """
    structural = build_java_type_structure_evidence(
        repository=repository,
        files=files,
        repo_id=repo_id,
    )
    source_payload = structural.get("payload") or {}
    annotation_index = _annotation_index(source_payload)
    types = {
        str(item.get("type_id")): dict(item)
        for item in source_payload.get("type_declarations") or []
        if isinstance(item, Mapping) and item.get("type_id")
    }
    fields = {
        str(item.get("field_id")): dict(item)
        for item in source_payload.get("field_declarations") or []
        if isinstance(item, Mapping) and item.get("field_id")
    }
    field_type_refs: dict[str, list[dict[str, Any]]] = {}
    for item in source_payload.get("type_reference_observations") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("owner_kind") == "field" and item.get("reference_role") == "field_type":
            field_type_refs.setdefault(str(item.get("owner_id") or ""), []).append(dict(item))

    diagnostics: list[dict[str, Any]] = []
    persistence_types: list[dict[str, Any]] = []
    persistence_fields: list[dict[str, Any]] = []
    persistence_keys: list[dict[str, Any]] = []
    persistence_relationships: list[dict[str, Any]] = []
    persistence_inheritance: list[dict[str, Any]] = []
    mapping_gaps: list[dict[str, Any]] = []

    persistence_type_ids: set[str] = set()
    for type_id, item in sorted(types.items(), key=lambda pair: (str(pair[1].get("fully_qualified_name") or ""), pair[0])):
        annotations = _annotations_by_name(annotation_index.get(type_id, []))
        entity = _first(annotations, "Entity")
        mapped_superclass = _first(annotations, "MappedSuperclass")
        embeddable = _first(annotations, "Embeddable")
        table = _first(annotations, "Table")
        if not any((entity, mapped_superclass, embeddable, table)):
            continue
        if entity:
            persistence_kind = "entity"
        elif mapped_superclass:
            persistence_kind = "mapped_superclass"
        elif embeddable:
            persistence_kind = "embeddable"
        else:
            persistence_kind = "table_annotation_without_persistence_type_annotation"
            diagnostics.append({
                "code": "table_annotation_without_persistence_type_annotation",
                "severity": "warning",
                "message": "@Table was observed without @Entity, @MappedSuperclass or @Embeddable on the same type.",
                "owner_kind": "type",
                "owner_id": type_id,
                "source_refs": [_source_ref(table, item)],
            })
        persistence_type_ids.add(type_id)
        record = {
            "persistence_type_mapping_id": _stable_id("java_persistence_type", repo_id, type_id),
            "type_id": type_id,
            "fully_qualified_name": item.get("fully_qualified_name"),
            "simple_name": item.get("simple_name"),
            "persistence_kind": persistence_kind,
            "entity_name_explicit": _mapping_argument(
                annotation=entity,
                argument_name="name",
                diagnostics=diagnostics,
                owner_kind="type",
                owner_id=type_id,
                annotation_name="Entity",
            ),
            "table_name_explicit": _mapping_argument(
                annotation=table,
                argument_name="name",
                diagnostics=diagnostics,
                owner_kind="type",
                owner_id=type_id,
                annotation_name="Table",
            ),
            "schema_name_explicit": _mapping_argument(
                annotation=table,
                argument_name="schema",
                diagnostics=diagnostics,
                owner_kind="type",
                owner_id=type_id,
                annotation_name="Table",
            ),
            "catalog_name_explicit": _mapping_argument(
                annotation=table,
                argument_name="catalog",
                diagnostics=diagnostics,
                owner_kind="type",
                owner_id=type_id,
                annotation_name="Table",
            ),
            "annotation_ids": _mapping_annotation_ids(annotations, _TYPE_ANNOTATIONS),
            "mapping_basis": "explicit_java_persistence_annotations",
            "source_ref": _source_ref(entity, mapped_superclass, embeddable, table, item),
        }
        persistence_types.append(record)
        if persistence_kind == "entity" and not record["table_name_explicit"]:
            mapping_gaps.append({
                "mapping_gap_id": _stable_id("java_persistence_gap", repo_id, type_id, "explicit_table_name_absent"),
                "gap_code": "explicit_table_name_absent",
                "severity": "info",
                "owner_kind": "type",
                "owner_id": type_id,
                "message": "Entity has no explicit @Table(name=...) declaration; default naming was not inferred.",
                "source_refs": [record["source_ref"]],
            })

        inheritance_annotation = _first(annotations, "Inheritance")
        discriminator_column = _first(annotations, "DiscriminatorColumn")
        discriminator_value = _first(annotations, "DiscriminatorValue")
        if any((inheritance_annotation, discriminator_column, discriminator_value)):
            persistence_inheritance.append({
                "persistence_inheritance_mapping_id": _stable_id("java_persistence_inheritance", repo_id, type_id),
                "type_id": type_id,
                "fully_qualified_name": item.get("fully_qualified_name"),
                "strategy_expression": _mapping_argument(
                    annotation=inheritance_annotation,
                    argument_name="strategy",
                    diagnostics=diagnostics,
                    owner_kind="type",
                    owner_id=type_id,
                    annotation_name="Inheritance",
                ),
                "discriminator_column_name_explicit": _mapping_argument(
                    annotation=discriminator_column,
                    argument_name="name",
                    diagnostics=diagnostics,
                    owner_kind="type",
                    owner_id=type_id,
                    annotation_name="DiscriminatorColumn",
                ),
                "discriminator_value_explicit": _mapping_argument(
                    annotation=discriminator_value,
                    argument_name="value",
                    diagnostics=diagnostics,
                    owner_kind="type",
                    owner_id=type_id,
                    annotation_name="DiscriminatorValue",
                ),
                "annotation_ids": _mapping_annotation_ids(annotations, {"Inheritance", "DiscriminatorColumn", "DiscriminatorValue"}),
                "source_ref": _source_ref(inheritance_annotation, discriminator_column, discriminator_value, item),
            })

        id_class = _first(annotations, "IdClass")
        if id_class:
            persistence_keys.append({
                "persistence_key_mapping_id": _stable_id("java_persistence_key", repo_id, type_id, "id_class"),
                "owner_type_id": type_id,
                "field_id": None,
                "key_kind": "id_class",
                "column_name_explicit": None,
                "id_class_expression": _mapping_argument(
                    annotation=id_class,
                    argument_name="value",
                    diagnostics=diagnostics,
                    owner_kind="type",
                    owner_id=type_id,
                    annotation_name="IdClass",
                ),
                "annotation_ids": [id_class.get("annotation_id")],
                "source_ref": _source_ref(id_class, item),
            })

    for field_id, field in sorted(fields.items(), key=lambda pair: (str(pair[1].get("owner_type_id") or ""), str(pair[1].get("name") or ""), pair[0])):
        annotations = _annotations_by_name(annotation_index.get(field_id, []))
        relevant_names = set(annotations) & _FIELD_ANNOTATIONS
        if not relevant_names:
            continue
        owner_type_id = str(field.get("owner_type_id") or "")
        owner = types.get(owner_type_id) or {}
        column = _first(annotations, "Column")
        join_column = _first(annotations, "JoinColumn")
        relationship_annotation = next((_first(annotations, name) for name in sorted(_RELATIONSHIP_ANNOTATIONS) if _first(annotations, name)), None)
        relationship_kind = _simple_annotation_name((relationship_annotation or {}).get("annotation_name")) or None
        if _first(annotations, "Transient"):
            persistence_role = "transient"
        elif _first(annotations, "EmbeddedId"):
            persistence_role = "embedded_id"
        elif _first(annotations, "Id"):
            persistence_role = "id"
        elif _first(annotations, "Version"):
            persistence_role = "version"
        elif relationship_annotation:
            persistence_role = "relationship"
        elif _first(annotations, "Embedded"):
            persistence_role = "embedded"
        else:
            persistence_role = "basic"

        type_refs = sorted(field_type_refs.get(field_id, []), key=lambda item: str(item.get("type_reference_id") or ""))
        resolved_target_ids = sorted({str(item.get("resolved_type_id")) for item in type_refs if item.get("resolved_type_id")})
        candidate_target_ids = sorted({str(value) for item in type_refs for value in item.get("candidate_type_ids") or [] if value})
        resolved_target_type_id = resolved_target_ids[0] if len(resolved_target_ids) == 1 else None
        mapping = {
            "persistence_field_mapping_id": _stable_id("java_persistence_field", repo_id, field_id),
            "field_id": field_id,
            "owner_type_id": owner_type_id,
            "owner_fully_qualified_name": owner.get("fully_qualified_name"),
            "field_name": field.get("name"),
            "declared_type_expression": field.get("declared_type_expression"),
            "persistence_role": persistence_role,
            "column_name_explicit": _mapping_argument(
                annotation=column,
                argument_name="name",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name="Column",
            ),
            "column_table_name_explicit": _mapping_argument(
                annotation=column,
                argument_name="table",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name="Column",
            ),
            "nullable_declared": _mapping_argument(
                annotation=column,
                argument_name="nullable",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name="Column",
            ),
            "relationship_kind": relationship_kind,
            "relationship_mapped_by_explicit": _mapping_argument(
                annotation=relationship_annotation,
                argument_name="mappedBy",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name=relationship_kind or "Relationship",
            ),
            "join_column_name_explicit": _mapping_argument(
                annotation=join_column,
                argument_name="name",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name="JoinColumn",
            ),
            "referenced_column_name_explicit": _mapping_argument(
                annotation=join_column,
                argument_name="referencedColumnName",
                diagnostics=diagnostics,
                owner_kind="field",
                owner_id=field_id,
                annotation_name="JoinColumn",
            ),
            "resolved_target_type_id": resolved_target_type_id,
            "candidate_target_type_ids": candidate_target_ids,
            "annotation_ids": _mapping_annotation_ids(annotations, _FIELD_ANNOTATIONS),
            "mapping_basis": "explicit_java_persistence_annotations",
            "source_ref": _source_ref(column, join_column, relationship_annotation, next(iter(annotation_index.get(field_id, [])), None), field),
        }
        persistence_fields.append(mapping)

        for unsupported_name in sorted(relevant_names & _UNSUPPORTED_COMPOSITE_ANNOTATIONS):
            annotation = _first(annotations, unsupported_name)
            diagnostics.append({
                "code": "unsupported_composite_persistence_annotation",
                "severity": "warning",
                "message": f"@{unsupported_name} was preserved as raw annotation evidence but is not normalized in java-persistence-mapping-evidence/v1.",
                "owner_kind": "field",
                "owner_id": field_id,
                "annotation_id": (annotation or {}).get("annotation_id"),
                "source_refs": [_source_ref(annotation, field)],
            })

        if owner_type_id not in persistence_type_ids and persistence_role != "transient":
            mapping_gaps.append({
                "mapping_gap_id": _stable_id("java_persistence_gap", repo_id, field_id, "owner_not_persistence_type"),
                "gap_code": "owner_not_persistence_type",
                "severity": "warning",
                "owner_kind": "field",
                "owner_id": field_id,
                "message": "Persistence field annotation was observed on a type not declared as @Entity, @MappedSuperclass or @Embeddable.",
                "source_refs": [mapping["source_ref"]],
            })

        if persistence_role in {"id", "embedded_id"}:
            persistence_keys.append({
                "persistence_key_mapping_id": _stable_id("java_persistence_key", repo_id, field_id, persistence_role),
                "owner_type_id": owner_type_id,
                "field_id": field_id,
                "key_kind": persistence_role,
                "column_name_explicit": mapping["column_name_explicit"],
                "id_class_expression": None,
                "annotation_ids": _mapping_annotation_ids(annotations, {"Id", "EmbeddedId", "Column"}),
                "source_ref": mapping["source_ref"],
            })

        if relationship_annotation:
            persistence_relationships.append({
                "persistence_relationship_mapping_id": _stable_id("java_persistence_relationship", repo_id, field_id),
                "source_type_id": owner_type_id,
                "field_id": field_id,
                "target_type_id": resolved_target_type_id,
                "candidate_target_type_ids": candidate_target_ids,
                "relationship_kind": relationship_kind,
                "mapped_by_explicit": mapping["relationship_mapped_by_explicit"],
                "join_column_name_explicit": mapping["join_column_name_explicit"],
                "referenced_column_name_explicit": mapping["referenced_column_name_explicit"],
                "annotation_ids": _mapping_annotation_ids(annotations, _RELATIONSHIP_ANNOTATIONS | {"JoinColumn", "JoinColumns", "JoinTable", "MapsId"}),
                "source_ref": mapping["source_ref"],
            })

    for values, keys in (
        (persistence_types, ("fully_qualified_name", "persistence_type_mapping_id")),
        (persistence_fields, ("owner_fully_qualified_name", "field_name", "persistence_field_mapping_id")),
        (persistence_keys, ("owner_type_id", "field_id", "persistence_key_mapping_id")),
        (persistence_relationships, ("source_type_id", "field_id", "persistence_relationship_mapping_id")),
        (persistence_inheritance, ("fully_qualified_name", "persistence_inheritance_mapping_id")),
        (mapping_gaps, ("gap_code", "owner_kind", "owner_id", "mapping_gap_id")),
    ):
        values.sort(key=lambda item, keys=keys: tuple(str(item.get(key) or "") for key in keys))
    diagnostics.sort(key=lambda item: (
        str(item.get("code") or ""),
        str(item.get("owner_kind") or ""),
        str(item.get("owner_id") or ""),
        str(item.get("message") or ""),
    ))

    base_coverage = dict(structural.get("coverage") or {})
    coverage_status = str(base_coverage.get("coverage_status") or "unknown")
    if diagnostics and coverage_status == "complete":
        coverage_status = "partial"
    coverage = {
        "coverage_status": coverage_status,
        "java_files_in_scope": base_coverage.get("java_files_in_scope"),
        "java_files_parsed": base_coverage.get("java_files_parsed"),
        "java_files_failed": base_coverage.get("java_files_failed"),
        "java_files_with_parse_errors": base_coverage.get("java_files_with_parse_errors"),
        "persistence_type_mapping_count": len(persistence_types),
        "persistence_field_mapping_count": len(persistence_fields),
        "persistence_key_mapping_count": len(persistence_keys),
        "persistence_relationship_mapping_count": len(persistence_relationships),
        "persistence_inheritance_mapping_count": len(persistence_inheritance),
        "mapping_gap_count": len(mapping_gaps),
        "diagnostic_count": len(diagnostics),
        "unsupported_composite_annotation_count": sum(
            1 for item in diagnostics if item.get("code") == "unsupported_composite_persistence_annotation"
        ),
    }
    payload = {
        "persistence_type_mappings": persistence_types,
        "persistence_field_mappings": persistence_fields,
        "persistence_key_mappings": persistence_keys,
        "persistence_relationship_mappings": persistence_relationships,
        "persistence_inheritance_mappings": persistence_inheritance,
        "mapping_gaps": mapping_gaps,
    }
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": deepcopy(structural.get("source_snapshot") or {}),
        "foundation": {
            "used": False,
            "contract_version": None,
            "fingerprint": None,
            "sections": [],
        },
        "parameters": {
            "language": "java",
            "include_test_sources": True,
            "mapping_policy": "explicit_persistence_annotations_only",
            "jpa_default_naming_inference": False,
            "record_limit": None,
        },
        "coverage": coverage,
        "diagnostics": diagnostics,
        "provenance": {
            "parser_provider": "tree_sitter",
            "source_structural_artifact_fingerprint": structural.get("content_fingerprint"),
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
        },
        "payload": payload,
    }
    artifact["content_fingerprint"] = _fingerprint(artifact)
    artifact["artifact_id"] = f"java_persistence_mapping_{artifact['content_fingerprint'][:24]}"
    return artifact
