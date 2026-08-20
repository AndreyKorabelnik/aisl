from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from code_analyzer_core.data_model_observations import (
    KeyObservationKind,
    ObservationEvidenceRef,
    RelationshipKind,
    RelationshipSourceKind,
    TableColumnPair,
    TableColumnRef,
    TableKeyObservation,
    TableRef,
    TableRelationshipObservation,
)
from code_analyzer_core.models import EvidenceRef, Fact
from code_analyzer_core.scanners.java_syntax import (
    JavaAnnotation,
    JavaCall,
    JavaClass,
    JavaField,
    annotation_args_map,
    annotation_string_arg,
    parse_java_files,
    unquote_annotation_value,
)
from code_analyzer_core.scanners.sql_table_observations import (
    _key_fact,
    _key_index,
    _matched_declared_keys,
    _relationship_fact,
)
from code_analyzer_core.utils import normalize_name


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").replace("\\", "/").strip().lower() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:20]}"


def _rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def _annotation(annotations: Iterable[JavaAnnotation], name: str) -> JavaAnnotation | None:
    expected = name.split(".")[-1]
    return next((item for item in annotations if item.name.split(".")[-1] == expected), None)


def _has_annotation(annotations: Iterable[JavaAnnotation], name: str) -> bool:
    return _annotation(annotations, name) is not None


def _simple_type(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"\?\s+extends\s+|\?\s+super\s+", "", text)
    if "<" in text and ">" in text:
        inner = text[text.find("<") + 1:text.rfind(">")]
        parts = [part.strip() for part in inner.split(",") if part.strip()]
        text = parts[-1] if parts else text.split("<", 1)[0]
    text = text.replace("[]", "").strip()
    return text.split(".")[-1] or None


def _entity_table_ref(cls: JavaClass) -> TableRef:
    table_ann = _annotation(cls.annotations, "Table")
    entity_ann = _annotation(cls.annotations, "Entity")
    table_name = (
        annotation_string_arg(table_ann.arguments, "name") if table_ann else None
    ) or (
        annotation_string_arg(entity_ann.arguments, "name") if entity_ann else None
    ) or normalize_name(cls.name)
    schema_name = annotation_string_arg(table_ann.arguments, "schema") if table_ann else None
    table_name = normalize_name(table_name)
    schema_name = normalize_name(schema_name) or None
    qualified = f"{schema_name}.{table_name}" if schema_name else table_name
    return TableRef(table_name=table_name, schema_name=schema_name, qualified_table_name=qualified)


def _field_column_name(field: JavaField) -> str:
    column_ann = _annotation(field.annotations, "Column")
    join_ann = _annotation(field.annotations, "JoinColumn")
    value = (
        annotation_string_arg(column_ann.arguments, "name") if column_ann else None
    ) or (
        annotation_string_arg(join_ann.arguments, "name") if join_ann else None
    ) or field.name
    return normalize_name(value)


def _evidence(repo: Path, path: Path, line_start: int, line_end: int, kind: str, snippet: str | None = None) -> ObservationEvidenceRef:
    return ObservationEvidenceRef(
        file=_rel(repo, path),
        line_start=line_start,
        line_end=line_end,
        kind=kind,
        snippet=(snippet or "")[:2000] or None,
    )


def _evidence_from_fact(fact: Fact, *, fallback_kind: str) -> list[ObservationEvidenceRef]:
    refs: list[ObservationEvidenceRef] = []
    for raw in fact.evidence:
        refs.append(ObservationEvidenceRef(
            file=raw.file_path,
            line_start=raw.line_start,
            line_end=raw.line_end,
            kind=raw.extractor or fallback_kind,
            snippet=raw.snippet,
        ))
    return refs


def _table_ref_from_identity(identity: dict[str, Any] | None, *, unresolved: str | None = None) -> TableRef:
    identity = identity or {}
    table_name = normalize_name(identity.get("table_name") or identity.get("normalized_table_name")) or None
    schema_name = normalize_name(identity.get("schema_name")) or None
    qualified_raw = str(identity.get("qualified_table_name") or "").strip().strip('"`').lower()
    qualified = qualified_raw or None
    if qualified and schema_name and "." not in qualified:
        qualified = f"{schema_name}.{qualified}"
    if table_name:
        return TableRef(table_name=table_name, schema_name=schema_name, qualified_table_name=qualified or (f"{schema_name}.{table_name}" if schema_name else table_name))
    return TableRef(unresolved_name=unresolved or "unresolved_table")


def _jpa_relationship_observations(
    facts: list[Fact],
    *,
    repo_id: str,
    db_schema: dict[str, Any],
) -> list[TableRelationshipObservation]:
    entity_tables: dict[str, TableRef] = {}
    for fact in facts:
        if fact.fact_type != "jpa_entity":
            continue
        entity = str(fact.properties.get("entity_class") or fact.name or "").split(".")[-1]
        if entity:
            entity_tables[entity] = _table_ref_from_identity(fact.properties, unresolved=entity)

    declared_keys = _key_index(db_schema)
    out: list[TableRelationshipObservation] = []
    for fact in facts:
        if fact.fact_type != "jpa_relationship":
            continue
        props = fact.properties or {}
        source_entity = str(props.get("source_entity") or "") or None
        target_entity = str(props.get("target_entity") or "") or None
        left_table = _table_ref_from_identity(props.get("source_table_identity"), unresolved=source_entity)
        right_table = entity_tables.get(str(target_entity)) or TableRef(unresolved_name=target_entity or str(props.get("target_type") or "unresolved_target_entity"))
        pairs: list[TableColumnPair] = []
        for ordinal, join in enumerate(props.get("join_columns") or []):
            if not isinstance(join, dict):
                continue
            left_column = normalize_name(join.get("join_column")) or None
            right_column = normalize_name(join.get("referenced_column")) or None
            if left_column and right_column:
                pairs.append(TableColumnPair(
                    left=TableColumnRef(column_name=left_column),
                    right=TableColumnRef(column_name=right_column),
                    operator="joins_to",
                    predicate_ordinal=ordinal,
                ))
        refs = _evidence_from_fact(fact, fallback_kind="jpa_relationship")
        if not refs:
            continue
        relationship_kind = str(props.get("relationship_kind") or "association")
        observation = TableRelationshipObservation(
            observation_id=_stable_id(
                "table_relationship_observation",
                repo_id,
                refs[0].file,
                refs[0].line_start,
                source_entity,
                props.get("source_field"),
                target_entity,
                relationship_kind,
            ),
            repo_id=repo_id,
            relation_kind=RelationshipKind.ORM_MAPPING,
            left_table=left_table,
            right_table=right_table,
            column_pairs=pairs,
            source_kind=RelationshipSourceKind.ORM,
            statement_id=None,
            matched_declared_keys=_matched_declared_keys(left_table, right_table, pairs, declared_keys),
            properties={
                "source_entity": source_entity,
                "source_field": props.get("source_field"),
                "target_entity": target_entity,
                "target_type": props.get("target_type"),
                "orm_annotation_kind": relationship_kind,
                "mapped_by": props.get("mapped_by"),
                "optional": props.get("optional"),
                "fetch": props.get("fetch"),
                "join_columns_declared": props.get("join_columns") or [],
                "referenced_column_unspecified": bool((props.get("join_columns") or []) and not pairs),
                "parser": "tree_sitter_jpa_annotations",
            },
            evidence_refs=refs,
        )
        out.append(observation)
    return out


def _id_class_name(cls: JavaClass) -> str | None:
    ann = _annotation(cls.annotations, "IdClass")
    if not ann:
        return None
    raw = unquote_annotation_value(annotation_args_map(ann.arguments).get("value"))
    if not raw:
        return None
    return raw.replace(".class", "").split(".")[-1].strip() or None


def _orm_identity_observations(
    repo: Path,
    parsed_files: list[Any],
    *,
    repo_id: str,
) -> list[TableKeyObservation]:
    classes: dict[str, tuple[Any, JavaClass]] = {}
    for parsed in parsed_files:
        for cls in parsed.classes:
            classes[cls.name] = (parsed, cls)

    out: list[TableKeyObservation] = []
    for parsed, cls in classes.values():
        if not (_has_annotation(cls.annotations, "Entity") or _has_annotation(cls.annotations, "Table")):
            continue
        table = _entity_table_ref(cls)
        direct_id_fields = [field for field in cls.fields if _has_annotation(field.annotations, "Id")]
        embedded_fields = [field for field in cls.fields if _has_annotation(field.annotations, "EmbeddedId")]
        id_class = _id_class_name(cls)
        columns: list[TableColumnRef] = []
        basis: list[str] = []
        unresolved = False

        if direct_id_fields:
            columns.extend(TableColumnRef(column_name=_field_column_name(field)) for field in direct_id_fields)
            basis.append("jpa_id_annotations")

        for field in embedded_fields:
            embedded_type = _simple_type(field.type)
            embedded = classes.get(str(embedded_type))
            if embedded:
                _, embedded_cls = embedded
                embedded_columns = [
                    TableColumnRef(column_name=_field_column_name(item))
                    for item in embedded_cls.fields
                    if "static" not in str(item.raw or "")
                ]
                columns.extend(embedded_columns)
                basis.append("jpa_embedded_id")
                if _annotation(field.annotations, "AttributeOverrides"):
                    basis.append("attribute_overrides_present_not_expanded")
            else:
                columns.append(TableColumnRef(unresolved_name=f"{field.name}:{embedded_type or 'embedded_id_type'}"))
                basis.append("jpa_embedded_id_type_unresolved")
                unresolved = True

        if id_class:
            id_class_entry = classes.get(id_class)
            if id_class_entry:
                _, id_cls = id_class_entry
                entity_by_name = {field.name: field for field in cls.fields}
                mapped = []
                for id_field in id_cls.fields:
                    entity_field = entity_by_name.get(id_field.name)
                    mapped.append(TableColumnRef(column_name=_field_column_name(entity_field or id_field)))
                if not direct_id_fields:
                    columns.extend(mapped)
                basis.append("jpa_id_class")
            else:
                if not columns:
                    columns.append(TableColumnRef(unresolved_name=f"IdClass:{id_class}"))
                basis.append("jpa_id_class_type_unresolved")
                unresolved = True

        dedup: list[TableColumnRef] = []
        seen: set[str] = set()
        for column in columns:
            key = str(column.column_name or column.unresolved_name or "")
            if key and key not in seen:
                seen.add(key)
                dedup.append(column)
        columns = dedup
        if not columns:
            continue

        first_line = min(
            [field.line_start for field in direct_id_fields + embedded_fields] or [cls.line_start]
        )
        refs = [_evidence(repo, parsed.file, first_line, cls.line_end, "jpa_identity_annotation", cls.text[:1600])]
        out.append(TableKeyObservation(
            observation_id=_stable_id("table_key_observation", repo_id, parsed.file, cls.name, "orm_identity", [c.column_name or c.unresolved_name for c in columns]),
            repo_id=repo_id,
            key_kind=KeyObservationKind.UNRESOLVED_KEY_MAPPING if unresolved else KeyObservationKind.ORM_IDENTITY,
            table=table,
            columns=columns,
            entity_name=cls.name,
            source_kind=RelationshipSourceKind.ORM,
            observation_basis=basis,
            properties={
                "entity_class": cls.name,
                "id_class": id_class,
                "identity_mapping_complete": not unresolved,
                "parser": "tree_sitter_jpa_annotations",
            },
            evidence_refs=refs,
        ))
    return out


def _jooq_schema_maps(db_schema: dict[str, Any]) -> tuple[dict[str, TableRef], dict[tuple[str, str], str]]:
    tables: dict[str, TableRef] = {}
    columns: dict[tuple[str, str], str] = {}
    for raw in db_schema.get("tables") or []:
        if not isinstance(raw, dict):
            continue
        table_name = normalize_name(raw.get("table_name"))
        if not table_name:
            continue
        schema = normalize_name(raw.get("schema_name")) or None
        qualified_raw = str(raw.get("qualified_table_name") or "").strip().strip('"`').lower()
        qualified = qualified_raw or (f"{schema}.{table_name}" if schema else table_name)
        ref = TableRef(
            table_id=raw.get("db_schema_table_id"),
            table_name=table_name,
            schema_name=schema,
            qualified_table_name=qualified,
        )
        for constant in (raw.get("table_constant"), raw.get("table_class"), str(raw.get("table_name") or "").upper()):
            if constant:
                tables[str(constant).split(".")[-1].upper()] = ref
    for raw in db_schema.get("columns") or []:
        if not isinstance(raw, dict):
            continue
        table_constant = str(raw.get("table_constant") or str(raw.get("table_name") or "").upper()).split(".")[-1].upper()
        field_constant = str(raw.get("field_constant") or "").split(".")[-1].upper()
        column_name = normalize_name(raw.get("column_name"))
        if table_constant and field_constant and column_name:
            columns[(table_constant, field_constant)] = column_name
    return tables, columns


def _jooq_field_ref(text: str | None, tables: dict[str, TableRef], columns: dict[tuple[str, str], str]) -> tuple[TableRef, TableColumnRef] | None:
    raw = str(text or "").strip().strip("()")
    match = re.fullmatch(r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)\.(?P<field>[A-Za-z_][A-Za-z0-9_]*)", raw)
    if not match:
        return None
    table_constant = match.group("table").upper()
    field_constant = match.group("field").upper()
    table = tables.get(table_constant) or TableRef(unresolved_name=table_constant)
    column = columns.get((table_constant, field_constant)) or normalize_name(field_constant)
    return table, TableColumnRef(column_name=column)


def _calls_inside(call: JavaCall, calls: Iterable[JavaCall], method_name: str) -> list[JavaCall]:
    return [
        item for item in calls
        if item.method == method_name
        and item.start_byte >= call.start_byte
        and item.end_byte <= call.end_byte
    ]


def _jooq_relationship_and_key_observations(
    repo: Path,
    parsed_files: list[Any],
    *,
    repo_id: str,
    db_schema: dict[str, Any],
) -> tuple[list[TableRelationshipObservation], list[TableKeyObservation]]:
    table_map, column_map = _jooq_schema_maps(db_schema)
    declared_keys = _key_index(db_schema)
    relationships: list[TableRelationshipObservation] = []
    keys: list[TableKeyObservation] = []

    for parsed in parsed_files:
        for cls in parsed.classes:
            for method in cls.methods:
                for on_call in [call for call in method.calls if call.method == "on"]:
                    grouped: dict[tuple[str, str], tuple[TableRef, TableRef, list[TableColumnPair]]] = {}
                    for equality in _calls_inside(on_call, method.calls, "eq"):
                        if not equality.args:
                            continue
                        left = _jooq_field_ref(equality.receiver, table_map, column_map)
                        right = _jooq_field_ref(equality.args[0], table_map, column_map)
                        if not left or not right:
                            continue
                        left_table, left_column = left
                        right_table, right_column = right
                        if str(left_table.qualified_table_name or left_table.unresolved_name) == str(right_table.qualified_table_name or right_table.unresolved_name):
                            continue
                        direct = (str(left_table.qualified_table_name or left_table.unresolved_name), str(right_table.qualified_table_name or right_table.unresolved_name))
                        reverse = (direct[1], direct[0])
                        pair = TableColumnPair(left=left_column, right=right_column, operator="=", predicate_ordinal=len(grouped.get(direct, (None, None, []))[2]))
                        if direct in grouped:
                            grouped[direct][2].append(pair)
                        elif reverse in grouped:
                            grouped[reverse][2].append(TableColumnPair(left=right_column, right=left_column, operator="=", predicate_ordinal=len(grouped[reverse][2])))
                        else:
                            grouped[direct] = (left_table, right_table, [pair])
                    for left_table, right_table, pairs in grouped.values():
                        ref = _evidence(repo, parsed.file, on_call.line_start, on_call.line_end, "tree_sitter_jooq_on", on_call.text)
                        relationships.append(TableRelationshipObservation(
                            observation_id=_stable_id("table_relationship_observation", repo_id, parsed.file, on_call.start_byte, [p.model_dump(mode="json") for p in pairs]),
                            repo_id=repo_id,
                            relation_kind=RelationshipKind.SQL_JOIN_PREDICATE,
                            left_table=left_table,
                            right_table=right_table,
                            column_pairs=pairs,
                            source_kind=RelationshipSourceKind.JOOQ,
                            statement_id=_stable_id("java_statement", repo_id, parsed.file, on_call.start_byte, on_call.end_byte),
                            query_id=f"{cls.name}.{method.name}",
                            join_type="jooq_join",
                            matched_declared_keys=_matched_declared_keys(left_table, right_table, pairs, declared_keys),
                            properties={"java_operation": f"{cls.name}.{method.name}", "parser": "tree_sitter_call_expression"},
                            evidence_refs=[ref],
                        ))

                lookup_columns: dict[str, tuple[TableRef, list[TableColumnRef], JavaCall]] = {}
                for predicate_call in [call for call in method.calls if call.method in {"where", "and"}]:
                    for equality in _calls_inside(predicate_call, method.calls, "eq"):
                        left = _jooq_field_ref(equality.receiver, table_map, column_map)
                        right = _jooq_field_ref(equality.args[0] if equality.args else None, table_map, column_map)
                        if left is None or right is not None:
                            continue
                        table, column = left
                        key = str(table.qualified_table_name or table.unresolved_name)
                        lookup_columns.setdefault(key, (table, [], predicate_call))[1].append(column)
                for table, columns, predicate_call in lookup_columns.values():
                    dedup: list[TableColumnRef] = []
                    seen: set[str] = set()
                    for column in columns:
                        name = str(column.column_name or column.unresolved_name)
                        if name and name not in seen:
                            seen.add(name)
                            dedup.append(column)
                    if not dedup:
                        continue
                    keys.append(TableKeyObservation(
                        observation_id=_stable_id("table_key_observation", repo_id, parsed.file, predicate_call.start_byte, "jooq_lookup", [c.column_name for c in dedup]),
                        repo_id=repo_id,
                        key_kind=KeyObservationKind.LOOKUP_KEY_USAGE,
                        table=table,
                        columns=dedup,
                        source_kind=RelationshipSourceKind.JOOQ,
                        observation_basis=["jooq_where_equality"],
                        properties={"java_operation": f"{cls.name}.{method.name}", "parser": "tree_sitter_call_expression"},
                        evidence_refs=[_evidence(repo, parsed.file, predicate_call.line_start, predicate_call.line_end, "tree_sitter_jooq_where", predicate_call.text)],
                    ))
    return relationships, keys


def scan_java_table_observations(
    repo: Path,
    files: list[Path],
    *,
    repo_id: str,
    facts: list[Fact],
    db_schema: dict[str, Any],
) -> dict[str, Any]:
    parsed_files, parse_warnings = parse_java_files(files)
    relationships = _jpa_relationship_observations(facts, repo_id=repo_id, db_schema=db_schema)
    keys = _orm_identity_observations(repo, parsed_files, repo_id=repo_id)
    jooq_relationships, jooq_keys = _jooq_relationship_and_key_observations(
        repo,
        parsed_files,
        repo_id=repo_id,
        db_schema=db_schema,
    )
    relationships.extend(jooq_relationships)
    keys.extend(jooq_keys)

    relationships = list({item.observation_id: item for item in relationships}.values())
    keys = list({item.observation_id: item for item in keys}.values())
    relationship_counts: dict[str, int] = defaultdict(int)
    source_counts: dict[str, int] = defaultdict(int)
    for item in relationships:
        relationship_counts[item.relation_kind.value] += 1
        source_counts[item.source_kind.value] += 1
    key_counts: dict[str, int] = defaultdict(int)
    for item in keys:
        key_counts[item.key_kind.value] += 1

    return {
        "relationships": [item.model_dump(mode="json", exclude_none=True) for item in relationships],
        "keys": [item.model_dump(mode="json", exclude_none=True) for item in keys],
        "facts": [_relationship_fact(item) for item in relationships] + [_key_fact(item) for item in keys],
        "overview": {
            "status": "completed",
            "relationship_observations": len(relationships),
            "key_observations": len(keys),
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "relationship_source_counts": dict(sorted(source_counts.items())),
            "key_counts": dict(sorted(key_counts.items())),
            "syntax_provider": "tree_sitter",
            "facts_only_policy": "observable ORM/jOOQ mappings only; unresolved physical targets are retained; no confidence, cardinality, or verdict",
        },
        "warnings": [{"reason": warning} for warning in parse_warnings],
    }
