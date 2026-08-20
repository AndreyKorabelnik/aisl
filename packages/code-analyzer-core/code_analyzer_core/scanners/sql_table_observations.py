from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import sqlglot
    from sqlglot import exp
    from sqlglot.optimizer.scope import traverse_scope
except Exception:  # pragma: no cover - dependency is required by pyproject
    sqlglot = None
    exp = None
    traverse_scope = None

from code_analyzer_core.data_model_observations import (
    KeyObservationKind,
    MatchedDeclaredKeyRef,
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
from code_analyzer_core.scanners.sql_scanner import (
    is_ignorable_sql_fragment,
    normalize_sql_for_parsing,
    split_sql_statements,
)
from code_analyzer_core.utils import read_text

logging.getLogger("sqlglot").setLevel(logging.ERROR)


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").replace("\\", "/").strip().lower() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8', errors='ignore')).hexdigest()[:20]}"


def _rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except Exception:
        return str(path).replace("\\", "/")


def _clean_identifier(value: str | None) -> str | None:
    text = str(value or "").strip().strip('"`[]')
    return text.lower() or None


def _table_ref(node: Any) -> TableRef | None:
    if exp is None or node is None:
        return None
    if isinstance(node, exp.Schema):
        node = node.this
    if isinstance(node, exp.Alias):
        node = node.this
    if isinstance(node, exp.Table):
        table_name = _clean_identifier(node.name)
        schema_name = _clean_identifier(node.db)
        catalog_name = _clean_identifier(node.catalog)
        qualified = ".".join(part for part in (catalog_name, schema_name, table_name) if part)
        if not table_name:
            return None
        return TableRef(
            table_name=table_name,
            schema_name=schema_name,
            qualified_table_name=qualified or table_name,
        )
    return None


def _table_key(table: TableRef) -> str:
    return str(table.qualified_table_name or table.table_name or table.unresolved_name or "").lower()


def _column_ref(node: Any) -> TableColumnRef | None:
    if exp is None or not isinstance(node, exp.Column):
        return None
    name = _clean_identifier(node.name)
    if not name:
        return None
    return TableColumnRef(column_name=name)


def _alias_map(expression: Any) -> dict[str, TableRef]:
    aliases: dict[str, TableRef] = {}
    if exp is None or expression is None:
        return aliases
    for table in expression.find_all(exp.Table):
        ref = _table_ref(table)
        if ref is None:
            continue
        alias = _clean_identifier(table.alias_or_name)
        if alias:
            aliases[alias] = ref
        if ref.table_name:
            aliases.setdefault(ref.table_name, ref)
        if ref.qualified_table_name:
            aliases.setdefault(ref.qualified_table_name, ref)
    return aliases


def _resolve_column_table(column: Any, aliases: dict[str, TableRef]) -> TableRef | None:
    if exp is None or not isinstance(column, exp.Column):
        return None
    qualifier = _clean_identifier(column.table)
    if qualifier:
        return aliases.get(qualifier) or TableRef(unresolved_name=qualifier)
    if len({_table_key(value) for value in aliases.values()}) == 1:
        return next(iter(aliases.values()))
    return None


def _evidence(rel: str, line_start: int, statement: str, kind: str) -> ObservationEvidenceRef:
    return ObservationEvidenceRef(
        file=rel,
        line_start=line_start,
        line_end=line_start + statement.count("\n"),
        kind=kind,
        snippet=statement[:2000],
    )


def _fact_evidence(refs: list[ObservationEvidenceRef]) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            file_path=ref.file,
            line_start=ref.line_start,
            line_end=ref.line_end,
            snippet=ref.snippet,
            extractor=ref.kind,
        )
        for ref in refs
    ]


def _relationship_fact(item: TableRelationshipObservation) -> Fact:
    props = item.model_dump(mode="json", exclude_none=True)
    props.pop("fact_type", None)
    props.pop("evidence_refs", None)
    return Fact(
        fact_type="table_relationship_observation",
        name=f"{_table_key(item.left_table)} -> {_table_key(item.right_table)} [{item.relation_kind.value}]",
        properties=props,
        evidence=_fact_evidence(item.evidence_refs),
    )


def _key_fact(item: TableKeyObservation) -> Fact:
    props = item.model_dump(mode="json", exclude_none=True)
    props.pop("fact_type", None)
    props.pop("evidence_refs", None)
    return Fact(
        fact_type="table_key_observation",
        name=f"{_table_key(item.table)}({','.join(col.column_name or col.unresolved_name or '' for col in item.columns)}) [{item.key_kind.value}]",
        properties=props,
        evidence=_fact_evidence(item.evidence_refs),
    )


def _key_index(db_schema: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in db_schema.get("keys") or []:
        if not isinstance(raw, dict):
            continue
        table_name = _clean_identifier(raw.get("table_name"))
        qualified = _clean_identifier(raw.get("qualified_table_name"))
        columns = [_clean_identifier(value) for value in raw.get("columns") or []]
        columns = [value for value in columns if value]
        if not table_name or not columns:
            continue
        kind = str(raw.get("constraint_kind") or "").lower()
        if kind not in {"primary_key", "unique_key"}:
            continue
        record = {
            "key_id": raw.get("db_schema_key_id") or _stable_id("db_schema_key", qualified or table_name, kind, columns),
            "key_kind": "declared_primary_key" if kind == "primary_key" else "declared_unique_key",
            "columns": columns,
        }
        for key in {table_name, qualified or ""}:
            if key:
                out[key].append(record)
    return out


def _matched_declared_keys(
    left_table: TableRef,
    right_table: TableRef,
    pairs: list[TableColumnPair],
    keys: dict[str, list[dict[str, Any]]],
) -> list[MatchedDeclaredKeyRef]:
    matched: list[MatchedDeclaredKeyRef] = []
    for side, table, columns in (
        ("left", left_table, [pair.left.column_name for pair in pairs]),
        ("right", right_table, [pair.right.column_name for pair in pairs]),
    ):
        observed = [column for column in columns if column]
        if not observed:
            continue
        candidates: list[dict[str, Any]] = []
        for table_identity in {_table_key(table), str(table.table_name or "").lower()}:
            candidates.extend(keys.get(table_identity) or [])
        seen: set[str] = set()
        for candidate in candidates:
            key_id = str(candidate["key_id"])
            if key_id in seen:
                continue
            seen.add(key_id)
            declared = [str(column).lower() for column in candidate["columns"]]
            if len(declared) == len(observed) and set(declared) == set(observed):
                matched.append(MatchedDeclaredKeyRef(
                    side=side,
                    key_id=key_id,
                    key_kind=str(candidate["key_kind"]),
                    matched_columns=observed,
                ))
    return matched


def _column_pairs_by_table_pair(predicate: Any, aliases: dict[str, TableRef]) -> dict[tuple[str, str], tuple[TableRef, TableRef, list[TableColumnPair]]]:
    grouped: dict[tuple[str, str], tuple[TableRef, TableRef, list[TableColumnPair]]] = {}
    if exp is None or predicate is None:
        return grouped
    ordinal = 0
    for equality in predicate.find_all(exp.EQ):
        left_node = equality.left
        right_node = equality.right
        if not isinstance(left_node, exp.Column) or not isinstance(right_node, exp.Column):
            continue
        left_table = _resolve_column_table(left_node, aliases)
        right_table = _resolve_column_table(right_node, aliases)
        left_column = _column_ref(left_node)
        right_column = _column_ref(right_node)
        if left_table is None or right_table is None or left_column is None or right_column is None:
            continue
        if _table_key(left_table) == _table_key(right_table):
            continue
        direct_key = (_table_key(left_table), _table_key(right_table))
        reverse_key = (direct_key[1], direct_key[0])
        pair = TableColumnPair(left=left_column, right=right_column, operator="=", predicate_ordinal=ordinal)
        ordinal += 1
        if direct_key in grouped:
            grouped[direct_key][2].append(pair)
        elif reverse_key in grouped:
            grouped[reverse_key][2].append(TableColumnPair(
                left=right_column,
                right=left_column,
                operator="=",
                predicate_ordinal=pair.predicate_ordinal,
            ))
        else:
            grouped[direct_key] = (left_table, right_table, [pair])
    return grouped


def _relationship(
    *,
    repo_id: str,
    relation_kind: RelationshipKind,
    left_table: TableRef,
    right_table: TableRef,
    pairs: list[TableColumnPair],
    source_kind: RelationshipSourceKind,
    statement_id: str,
    evidence: ObservationEvidenceRef,
    key_index: dict[str, list[dict[str, Any]]],
    join_type: str | None = None,
    direction: str | None = None,
    properties: dict[str, Any] | None = None,
) -> TableRelationshipObservation:
    return TableRelationshipObservation(
        observation_id=_stable_id(
            "table_relationship_observation",
            repo_id,
            statement_id,
            relation_kind.value,
            _table_key(left_table),
            _table_key(right_table),
            [(p.left.column_name, p.right.column_name) for p in pairs],
        ),
        repo_id=repo_id,
        relation_kind=relation_kind,
        left_table=left_table,
        right_table=right_table,
        column_pairs=pairs,
        source_kind=source_kind,
        statement_id=statement_id,
        join_type=join_type,
        direction=direction,
        matched_declared_keys=_matched_declared_keys(left_table, right_table, pairs, key_index),
        properties=properties or {},
        evidence_refs=[evidence],
    )


def _join_type(join: Any) -> str:
    side = str(getattr(join, "side", "") or "").lower()
    kind = str(getattr(join, "kind", "") or "").lower()
    return "_".join(part for part in (side, kind) if part) or "inner"


def _extract_join_relationships(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
    key_index: dict[str, list[dict[str, Any]]],
) -> list[TableRelationshipObservation]:
    out: list[TableRelationshipObservation] = []
    aliases = _alias_map(expression)
    for join in expression.find_all(exp.Join):
        on = join.args.get("on")
        for left, right, pairs in _column_pairs_by_table_pair(on, aliases).values():
            out.append(_relationship(
                repo_id=repo_id,
                relation_kind=RelationshipKind.SQL_JOIN_PREDICATE,
                left_table=left,
                right_table=right,
                pairs=pairs,
                source_kind=RelationshipSourceKind.SQL,
                statement_id=statement_id,
                evidence=evidence,
                key_index=key_index,
                join_type=_join_type(join),
                properties={"predicate_location": "join_on", "parser": "sqlglot"},
            ))
    return out


def _extract_scope_predicates(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
    key_index: dict[str, list[dict[str, Any]]],
) -> list[TableRelationshipObservation]:
    out: list[TableRelationshipObservation] = []
    if traverse_scope is None:
        return out
    aliases = _alias_map(expression)
    seen: set[str] = set()
    for scope in traverse_scope(expression):
        where = scope.expression.args.get("where") if hasattr(scope.expression, "args") else None
        if where is None:
            continue
        local_aliases = {str(alias).lower() for alias in scope.sources}
        external_aliases = {_clean_identifier(column.table) for column in scope.external_columns}
        external_aliases.discard(None)
        for left, right, pairs in _column_pairs_by_table_pair(where, aliases).values():
            pair_aliases: set[str] = set()
            for equality in where.find_all(exp.EQ):
                if isinstance(equality.left, exp.Column) and isinstance(equality.right, exp.Column):
                    pair_aliases.update(filter(None, (_clean_identifier(equality.left.table), _clean_identifier(equality.right.table))))
            correlated = bool(pair_aliases & local_aliases and pair_aliases & external_aliases)
            kind = RelationshipKind.CORRELATED_SUBQUERY_PREDICATE if correlated else RelationshipKind.SQL_JOIN_PREDICATE
            item = _relationship(
                repo_id=repo_id,
                relation_kind=kind,
                left_table=left,
                right_table=right,
                pairs=pairs,
                source_kind=RelationshipSourceKind.SQL,
                statement_id=statement_id,
                evidence=evidence,
                key_index=key_index,
                properties={"predicate_location": "where", "parser": "sqlglot"},
            )
            if item.observation_id not in seen:
                seen.add(item.observation_id)
                out.append(item)
    return out


def _direct_tables(node: Any) -> list[TableRef]:
    if exp is None or node is None:
        return []
    out: list[TableRef] = []
    seen: set[str] = set()
    for table in node.find_all(exp.Table):
        ref = _table_ref(table)
        if ref is None or _table_key(ref) in seen:
            continue
        seen.add(_table_key(ref))
        out.append(ref)
    return out


def _insert_target_and_columns(expression: Any) -> tuple[TableRef | None, list[str]]:
    node = expression.this
    columns: list[str] = []
    if isinstance(node, exp.Schema):
        columns = [_clean_identifier(item.name) for item in node.expressions if isinstance(item, exp.Identifier)]
        columns = [column for column in columns if column]
        node = node.this
    return _table_ref(node), columns


def _insert_pairs(source: TableRef, target_columns: list[str], select: Any, aliases: dict[str, TableRef]) -> list[TableColumnPair]:
    pairs: list[TableColumnPair] = []
    if not isinstance(select, exp.Select) or not target_columns:
        return pairs
    for ordinal, (target_column, projection) in enumerate(zip(target_columns, select.expressions)):
        source_column = projection.this if isinstance(projection, exp.Alias) else projection
        if not isinstance(source_column, exp.Column):
            continue
        source_table = _resolve_column_table(source_column, aliases)
        if source_table is None or _table_key(source_table) != _table_key(source):
            continue
        pairs.append(TableColumnPair(
            left=TableColumnRef(column_name=_clean_identifier(source_column.name)),
            right=TableColumnRef(column_name=target_column),
            operator="maps_to",
            predicate_ordinal=ordinal,
        ))
    return pairs


def _extract_data_movement(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
    key_index: dict[str, list[dict[str, Any]]],
) -> list[TableRelationshipObservation]:
    out: list[TableRelationshipObservation] = []
    aliases = _alias_map(expression)
    if isinstance(expression, exp.Insert):
        target, target_columns = _insert_target_and_columns(expression)
        source_expression = expression.args.get("expression")
        if target and source_expression is not None and not isinstance(source_expression, exp.Values):
            for source in _direct_tables(source_expression):
                if _table_key(source) == _table_key(target):
                    continue
                out.append(_relationship(
                    repo_id=repo_id,
                    relation_kind=RelationshipKind.DATA_MOVEMENT,
                    left_table=source,
                    right_table=target,
                    pairs=_insert_pairs(source, target_columns, source_expression, aliases),
                    source_kind=RelationshipSourceKind.SQL,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                    direction="source_to_target",
                    properties={"operation": "insert_select", "parser": "sqlglot"},
                ))
    elif isinstance(expression, exp.Update):
        target = _table_ref(expression.this)
        from_node = expression.args.get("from_")
        if target and from_node is not None:
            for source in _direct_tables(from_node):
                if _table_key(source) == _table_key(target):
                    continue
                pairs: list[TableColumnPair] = []
                for assignment in expression.expressions:
                    if not isinstance(assignment, exp.EQ):
                        continue
                    target_column = assignment.left
                    source_column = assignment.right
                    if isinstance(target_column, exp.Column) and isinstance(source_column, exp.Column):
                        resolved_source = _resolve_column_table(source_column, aliases)
                        if resolved_source and _table_key(resolved_source) == _table_key(source):
                            pairs.append(TableColumnPair(
                                left=TableColumnRef(column_name=_clean_identifier(source_column.name)),
                                right=TableColumnRef(column_name=_clean_identifier(target_column.name)),
                                operator="maps_to",
                                predicate_ordinal=len(pairs),
                            ))
                out.append(_relationship(
                    repo_id=repo_id,
                    relation_kind=RelationshipKind.DATA_MOVEMENT,
                    left_table=source,
                    right_table=target,
                    pairs=pairs,
                    source_kind=RelationshipSourceKind.SQL,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                    direction="source_to_target",
                    properties={"operation": "update_from", "parser": "sqlglot"},
                ))
    elif isinstance(expression, exp.Merge):
        target = _table_ref(expression.this)
        using = expression.args.get("using")
        sources = _direct_tables(using)
        if target:
            for source in sources:
                if _table_key(source) == _table_key(target):
                    continue
                out.append(_relationship(
                    repo_id=repo_id,
                    relation_kind=RelationshipKind.DATA_MOVEMENT,
                    left_table=source,
                    right_table=target,
                    pairs=[],
                    source_kind=RelationshipSourceKind.SQL,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                    direction="source_to_target",
                    properties={"operation": "merge", "parser": "sqlglot"},
                ))
    elif isinstance(expression, exp.Create) and str(expression.args.get("kind") or "").upper() in {"VIEW", "MATERIALIZED VIEW"}:
        target = _table_ref(expression.this)
        source_expression = expression.args.get("expression")
        if target and source_expression is not None:
            for source in _direct_tables(source_expression):
                if _table_key(source) == _table_key(target):
                    continue
                out.append(_relationship(
                    repo_id=repo_id,
                    relation_kind=RelationshipKind.VIEW_DEPENDENCY,
                    left_table=source,
                    right_table=target,
                    pairs=[],
                    source_kind=RelationshipSourceKind.SQL,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                    direction="source_to_target",
                    properties={"operation": "create_view", "parser": "sqlglot"},
                ))
    return out


def _declared_key_observations(
    db_schema: dict[str, Any],
    *,
    repo_id: str,
) -> list[TableKeyObservation]:
    out: list[TableKeyObservation] = []
    for raw in db_schema.get("keys") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("constraint_kind") or "").lower()
        key_kind = {
            "primary_key": KeyObservationKind.DECLARED_PRIMARY_KEY,
            "unique_key": KeyObservationKind.DECLARED_UNIQUE_KEY,
        }.get(kind)
        columns = [_clean_identifier(value) for value in raw.get("columns") or []]
        columns = [value for value in columns if value]
        table_name = _clean_identifier(raw.get("table_name"))
        if key_kind is None or not columns or not table_name:
            continue
        file = str(raw.get("file") or "unknown")
        line = raw.get("line_start")
        out.append(TableKeyObservation(
            observation_id=_stable_id("table_key_observation", repo_id, raw.get("db_schema_key_id"), key_kind.value),
            repo_id=repo_id,
            key_kind=key_kind,
            table=TableRef(
                table_id=raw.get("db_schema_table_id"),
                table_name=table_name,
                schema_name=_clean_identifier(raw.get("schema_name")),
                qualified_table_name=_clean_identifier(raw.get("qualified_table_name")) or table_name,
            ),
            columns=[TableColumnRef(column_name=column) for column in columns],
            constraint_name=raw.get("constraint_name"),
            source_kind=RelationshipSourceKind.GENERATED_SCHEMA if str(raw.get("source_type") or "").startswith("jooq") else RelationshipSourceKind.DDL,
            evidence_refs=[ObservationEvidenceRef(file=file, line_start=line, kind=str(raw.get("source_type") or "declared_db_key"))],
        ))
    for raw in db_schema.get("indexes") or []:
        if not isinstance(raw, dict) or not raw.get("unique"):
            continue
        columns = [_clean_identifier(value) for value in raw.get("columns") or []]
        columns = [value for value in columns if value]
        table_name = _clean_identifier(raw.get("table_name"))
        if not columns or not table_name:
            continue
        file = str(raw.get("file") or "unknown")
        line = raw.get("line_start")
        out.append(TableKeyObservation(
            observation_id=_stable_id("table_key_observation", repo_id, raw.get("db_schema_index_id"), "declared_unique_index"),
            repo_id=repo_id,
            key_kind=KeyObservationKind.DECLARED_UNIQUE_INDEX,
            table=TableRef(table_name=table_name, schema_name=_clean_identifier(raw.get("schema_name")), qualified_table_name=_clean_identifier(raw.get("qualified_table_name")) or table_name),
            columns=[TableColumnRef(column_name=column) for column in columns],
            index_name=raw.get("index_name"),
            source_kind=RelationshipSourceKind.GENERATED_SCHEMA if str(raw.get("source_type") or "").startswith("jooq") else RelationshipSourceKind.DDL,
            evidence_refs=[ObservationEvidenceRef(file=file, line_start=line, kind=str(raw.get("source_type") or "declared_unique_index"))],
        ))
    return out


def _merge_key_observations(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
) -> list[TableKeyObservation]:
    if not isinstance(expression, exp.Merge):
        return []
    aliases = _alias_map(expression)
    pairs_by_table = _column_pairs_by_table_pair(expression.args.get("on"), aliases)
    out: list[TableKeyObservation] = []
    for left, right, pairs in pairs_by_table.values():
        for table, columns, side in (
            (left, [pair.left for pair in pairs], "left"),
            (right, [pair.right for pair in pairs], "right"),
        ):
            out.append(TableKeyObservation(
                observation_id=_stable_id("table_key_observation", repo_id, statement_id, "merge", _table_key(table), [column.column_name for column in columns]),
                repo_id=repo_id,
                key_kind=KeyObservationKind.MERGE_MATCH_KEY,
                table=table,
                columns=columns,
                source_kind=RelationshipSourceKind.SQL,
                observation_basis=["merge_match_predicate"],
                properties={"merge_side": side, "statement_id": statement_id},
                evidence_refs=[evidence],
            ))
    return out


def _upsert_key_observations(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
) -> list[TableKeyObservation]:
    if not isinstance(expression, exp.Insert):
        return []
    target, _ = _insert_target_and_columns(expression)
    conflict = expression.args.get("conflict")
    if target is None or conflict is None:
        return []
    columns: list[TableColumnRef] = []
    for ordered in conflict.args.get("conflict_keys") or []:
        node = ordered.this if isinstance(ordered, exp.Ordered) else ordered
        if isinstance(node, exp.Column) and _clean_identifier(node.name):
            columns.append(TableColumnRef(column_name=_clean_identifier(node.name)))
    if not columns:
        return []
    return [TableKeyObservation(
        observation_id=_stable_id("table_key_observation", repo_id, statement_id, "upsert", _table_key(target), [column.column_name for column in columns]),
        repo_id=repo_id,
        key_kind=KeyObservationKind.UPSERT_CONFLICT_KEY,
        table=target,
        columns=columns,
        source_kind=RelationshipSourceKind.SQL,
        observation_basis=["on_conflict_columns"],
        properties={"statement_id": statement_id},
        evidence_refs=[evidence],
    )]


def _dedup_key_observations(
    expression: Any,
    *,
    repo_id: str,
    statement_id: str,
    evidence: ObservationEvidenceRef,
) -> list[TableKeyObservation]:
    aliases = _alias_map(expression)
    out: list[TableKeyObservation] = []
    for window in expression.find_all(exp.Window):
        if not isinstance(window.this, exp.RowNumber):
            continue
        partition_columns = [column for column in window.args.get("partition_by") or [] if isinstance(column, exp.Column)]
        by_table: dict[str, tuple[TableRef, list[TableColumnRef]]] = {}
        for column in partition_columns:
            table = _resolve_column_table(column, aliases)
            column_ref = _column_ref(column)
            if table is None or column_ref is None:
                continue
            key = _table_key(table)
            by_table.setdefault(key, (table, []))[1].append(column_ref)
        for table, columns in by_table.values():
            if not columns:
                continue
            out.append(TableKeyObservation(
                observation_id=_stable_id("table_key_observation", repo_id, statement_id, "row_number_partition", _table_key(table), [column.column_name for column in columns]),
                repo_id=repo_id,
                key_kind=KeyObservationKind.DEDUPLICATION_PARTITION_KEY,
                table=table,
                columns=columns,
                source_kind=RelationshipSourceKind.SQL,
                observation_basis=["row_number_partition_by"],
                properties={"statement_id": statement_id},
                evidence_refs=[evidence],
            ))
    return out


def scan_sql_table_observations(
    repo: Path,
    files: list[Path],
    *,
    repo_id: str,
    db_schema: dict[str, Any],
) -> dict[str, Any]:
    relationships: list[TableRelationshipObservation] = []
    keys: list[TableKeyObservation] = _declared_key_observations(db_schema, repo_id=repo_id)
    warnings: list[dict[str, Any]] = []
    key_index = _key_index(db_schema)
    statements = 0
    parsed = 0

    if sqlglot is None or exp is None:
        return {
            "relationships": [],
            "keys": [item.model_dump(mode="json", exclude_none=True) for item in keys],
            "facts": [_key_fact(item) for item in keys],
            "overview": {
                "status": "sqlglot_unavailable",
                "statements": 0,
                "parsed_statements": 0,
                "relationship_observations": 0,
                "key_observations": len(keys),
            },
            "warnings": [{"reason": "sqlglot_unavailable"}],
        }

    for path in files:
        if path.suffix.lower() != ".sql":
            continue
        text = read_text(path)
        rel = _rel(repo, path)
        for line_start, statement in split_sql_statements(text):
            normalized = normalize_sql_for_parsing(statement)
            if not normalized or is_ignorable_sql_fragment(statement):
                continue
            statements += 1
            statement_id = _stable_id("sql_statement", repo_id, rel, line_start, normalized)
            evidence = _evidence(rel, line_start, statement, "sqlglot_table_observation")
            try:
                expressions = sqlglot.parse(normalized, read=None, error_level="ignore") or []
            except Exception as exc:
                warnings.append({"file": rel, "line_start": line_start, "reason": "sqlglot_parse_exception", "exception": str(exc)})
                continue
            for expression in expressions:
                if expression is None:
                    continue
                parsed += 1
                relationships.extend(_extract_join_relationships(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                ))
                relationships.extend(_extract_scope_predicates(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                ))
                relationships.extend(_extract_data_movement(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                    key_index=key_index,
                ))
                keys.extend(_merge_key_observations(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                ))
                keys.extend(_upsert_key_observations(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                ))
                keys.extend(_dedup_key_observations(
                    expression,
                    repo_id=repo_id,
                    statement_id=statement_id,
                    evidence=evidence,
                ))

    relationship_by_id = {item.observation_id: item for item in relationships}
    key_by_id = {item.observation_id: item for item in keys}
    relationships = list(relationship_by_id.values())
    keys = list(key_by_id.values())
    relationship_payloads = [item.model_dump(mode="json", exclude_none=True) for item in relationships]
    key_payloads = [item.model_dump(mode="json", exclude_none=True) for item in keys]
    facts = [_relationship_fact(item) for item in relationships] + [_key_fact(item) for item in keys]
    relationship_counts: dict[str, int] = defaultdict(int)
    for item in relationships:
        relationship_counts[item.relation_kind.value] += 1
    key_counts: dict[str, int] = defaultdict(int)
    for item in keys:
        key_counts[item.key_kind.value] += 1
    return {
        "relationships": relationship_payloads,
        "keys": key_payloads,
        "facts": facts,
        "overview": {
            "status": "completed",
            "statements": statements,
            "parsed_statements": parsed,
            "relationship_observations": len(relationships),
            "key_observations": len(keys),
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "key_counts": dict(sorted(key_counts.items())),
            "facts_only_policy": "observed syntax and declared schema facts only; no confidence, cardinality, semantic equivalence, or verdict",
        },
        "warnings": warnings,
    }
