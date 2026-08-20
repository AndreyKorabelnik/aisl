from __future__ import annotations

"""Scope-neutral physical, persistence, schema and source-observation materialization."""

import json
from typing import Any, Iterable

from .bulk import bulk_insert as _bulk_insert
from .data_model_ingestion import (
    _bool,
    _evidence_ref_rows,
    _first_evidence_location,
    _included_static_data_model_record,
    _insert_evidence_refs,
    _int,
    _json,
    _local_id,
    _occurrence_candidates,
    _single,
    _source_record,
    _source_record_values,
    _string,
)
from prepared_knowledge_runtime.normalization import (
    normalize_db_identifier,
    normalize_field_correspondence_path,
    normalize_text,
    stable_id,
)

try:
    import duckdb
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    duckdb = None

def _load_physical_assets(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "physical_assets", item, ordinal)
        local_asset_id = local_id or stable_id("local_asset", _json(item))
        occurrence_id = stable_id("asset", repo_id, local_asset_id, ordinal)
        name = str(item.get("name") or local_asset_id)
        schema_name = _string(item, "schema", "schema_name")
        qualified_name = _string(item, "qualified_name") or ".".join(value for value in (schema_name, name) if value)
        con.execute(
            "INSERT INTO physical_asset VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id,
                repo_id,
                local_asset_id,
                ordinal,
                record_id,
                _string(item, "asset_type", "asset_kind", "type"),
                schema_name,
                name,
                qualified_name,
                normalize_db_identifier(qualified_name),
                _string(item, "source_type"),
                _string(item, "description"),
                _int(item.get("column_count")),
                _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="physical_asset", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _constraint_rows(
    *,
    repo_id: str,
    fact_occurrence_id: str,
    local_asset_id: str,
    asset_occurrence_id: str | None,
    normalized_asset_name: str,
    item: dict[str, Any],
) -> Iterator[tuple[Any, ...]]:
    constraints = item.get("constraints") or {}
    if not isinstance(constraints, dict):
        constraints = {}
    primary_key = constraints.get("primary_key") or []
    if primary_key:
        payload = {"columns": primary_key}
        yield (
            stable_id("constraint", fact_occurrence_id, "primary_key", 0, _json(primary_key)),
            repo_id,
            fact_occurrence_id,
            local_asset_id,
            asset_occurrence_id,
            normalized_asset_name,
            "primary_key",
            None,
            _json(primary_key),
            None,
            _json([]),
            _json(payload),
        )
    list_kinds = {
        "foreign_keys": "foreign_key",
        "unique_constraints": "unique",
        "indexes": "index",
        "checks": "check",
    }
    for source_key, kind in list_kinds.items():
        values = constraints.get(source_key) or []
        if not isinstance(values, list):
            continue
        for position, value in enumerate(values):
            payload = value if isinstance(value, dict) else {"value": value}
            columns = payload.get("columns") or payload.get("column_names") or []
            referenced_name = _string(payload, "referenced_qualified_name", "referenced_table", "target_table")
            referenced_columns = payload.get("referenced_columns") or payload.get("target_columns") or []
            constraint_name = _string(payload, "constraint_name", "name", "index_name")
            yield (
                stable_id("constraint", fact_occurrence_id, kind, constraint_name, position, _json(payload)),
                repo_id,
                fact_occurrence_id,
                local_asset_id,
                asset_occurrence_id,
                normalized_asset_name,
                kind,
                constraint_name,
                _json(columns),
                referenced_name,
                _json(referenced_columns),
                _json(payload),
            )


def _load_physical_asset_facts(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    rows: Iterable[dict[str, Any]],
) -> tuple[int, int, int]:
    """Load physical facts in batches without per-column DuckDB round trips."""
    asset_candidates_by_local: dict[str, list[str]] = {}
    asset_details: dict[str, tuple[str | None, str | None, str | None]] = {}
    for local_id, occurrence_id, qualified_name, schema_name, name in con.execute(
        """
        SELECT local_asset_id, physical_asset_occurrence_id, qualified_name, schema_name, name
        FROM physical_asset
        WHERE repo_id=?
        ORDER BY local_asset_id, occurrence_ordinal, physical_asset_occurrence_id
        """,
        [repo_id],
    ).fetchall():
        asset_candidates_by_local.setdefault(str(local_id), []).append(str(occurrence_id))
        asset_details[str(occurrence_id)] = (qualified_name, schema_name, name)

    source_rows: list[tuple[Any, ...]] = []
    fact_rows: list[tuple[Any, ...]] = []
    column_rows: list[tuple[Any, ...]] = []
    constraint_rows_all: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []

    fact_count = 0
    column_count = 0
    constraint_count = 0
    for ordinal, item in enumerate(rows):
        record_id, source_local_id, source_values = _source_record_values(
            repo_id, "physical_asset_facts", item, ordinal
        )
        source_rows.append(source_values)
        local_asset_id = source_local_id or stable_id("local_asset_fact", _json(item))
        asset_candidates = list(asset_candidates_by_local.get(local_asset_id) or [])
        singular_asset = _single(asset_candidates)
        schema_name = _string(item, "schema", "schema_name")
        name = _string(item, "name")
        qualified_name = _string(item, "qualified_name")
        if not qualified_name and singular_asset:
            details = asset_details.get(singular_asset)
            if details:
                qualified_name = details[0]
                schema_name = schema_name or details[1]
                name = name or details[2]
        normalized_qualified_name = normalize_db_identifier(qualified_name or name or local_asset_id)
        fact_occurrence_id = stable_id("asset_fact", repo_id, local_asset_id, ordinal)
        fact_rows.append(
            (
                fact_occurrence_id,
                repo_id,
                local_asset_id,
                ordinal,
                record_id,
                singular_asset,
                _json(asset_candidates),
                schema_name,
                name,
                qualified_name,
                normalized_qualified_name,
                _json(item),
            )
        )
        evidence_rows.extend(
            _evidence_ref_rows(repo_id, "physical_asset_fact", fact_occurrence_id, item)
        )

        raw_columns = item.get("columns") or []
        if not isinstance(raw_columns, list):
            raw_columns = []
        for position, column in enumerate(raw_columns):
            if not isinstance(column, dict):
                continue
            column_name = str(column.get("name") or f"column_{position}")
            column_occurrence_id = stable_id(
                "column", fact_occurrence_id, normalize_text(column_name), position
            )
            column_rows.append(
                (
                    column_occurrence_id,
                    repo_id,
                    fact_occurrence_id,
                    local_asset_id,
                    singular_asset,
                    normalized_qualified_name,
                    position,
                    column_name,
                    normalize_text(column_name),
                    _string(column, "type", "data_type", "sql_type"),
                    _bool(column.get("nullable")),
                    None if column.get("default_value") is None else str(column.get("default_value")),
                    _string(column, "description"),
                    _json(column),
                )
            )
            evidence_rows.extend(
                _evidence_ref_rows(repo_id, "physical_column", column_occurrence_id, column)
            )
            column_count += 1

        item_constraints = list(
            _constraint_rows(
                repo_id=repo_id,
                fact_occurrence_id=fact_occurrence_id,
                local_asset_id=local_asset_id,
                asset_occurrence_id=singular_asset,
                normalized_asset_name=normalized_qualified_name,
                item=item,
            )
        )
        constraint_rows_all.extend(item_constraints)
        constraint_count += len(item_constraints)
        fact_count += 1

    _bulk_insert(con, "INSERT INTO source_record VALUES (?, ?, ?, ?, ?, ?)", source_rows)
    _bulk_insert(con, "INSERT INTO physical_asset_fact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", fact_rows)
    _bulk_insert(con, "INSERT INTO physical_column VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", column_rows)
    _bulk_insert(con, "INSERT INTO physical_constraint VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", constraint_rows_all)
    _bulk_insert(con, "INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", evidence_rows)
    return fact_count, column_count, constraint_count


def _load_mappings(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "physical_to_entity_mappings", item, ordinal)
        local_entity_id = _local_id(item, "entity_id")
        local_asset_id = _local_id(item, "physical_asset_id", "asset_id")
        entity_candidates = _occurrence_candidates(
            con,
            table="data_model_entity",
            repo_id=repo_id,
            local_column="local_entity_id",
            local_id=local_entity_id,
            occurrence_column="entity_occurrence_id",
        )
        asset_candidates = _occurrence_candidates(
            con,
            table="physical_asset",
            repo_id=repo_id,
            local_column="local_asset_id",
            local_id=local_asset_id,
            occurrence_column="physical_asset_occurrence_id",
        )
        occurrence_id = stable_id("mapping", repo_id, local_id or record_id, ordinal)
        con.execute(
            "INSERT INTO entity_physical_mapping VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id,
                repo_id,
                local_entity_id,
                local_asset_id,
                _single(entity_candidates),
                _single(asset_candidates),
                _json(entity_candidates),
                _json(asset_candidates),
                _string(item, "fact_kind"),
                _json(item.get("mapping_basis") or []),
                _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="entity_physical_mapping", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _flush_stream_rows(
    con: duckdb.DuckDBPyConnection,
    *,
    source_rows: list[tuple[Any, ...]],
    value_sql: str,
    value_rows: list[tuple[Any, ...]],
    evidence_rows: list[tuple[Any, ...]],
) -> None:
    _bulk_insert(con, "INSERT INTO source_record VALUES (?, ?, ?, ?, ?, ?)", source_rows)
    _bulk_insert(con, value_sql, value_rows)
    _bulk_insert(con, "INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", evidence_rows)
    source_rows.clear()
    value_rows.clear()
    evidence_rows.clear()


def _load_value_sets(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    source_rows: list[tuple[Any, ...]] = []
    value_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id, source_row = _source_record_values(repo_id, "declared_value_sets", item, ordinal)
        source_rows.append(source_row)
        occurrence_id = stable_id("value_set", repo_id, local_id or record_id, ordinal)
        value_rows.append((occurrence_id, repo_id, local_id, _string(item, "name"), _string(item, "syntax_kind"), _string(item, "source_set"), _int(item.get("entries_count")), _json(item)))
        evidence_rows.extend(_evidence_ref_rows(repo_id, "declared_value_set", occurrence_id, item))
        count += 1
        if len(value_rows) >= 500:
            _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO declared_value_set VALUES (?, ?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO declared_value_set VALUES (?, ?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    return count


def _load_dictionary(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    source_rows: list[tuple[Any, ...]] = []
    value_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id, source_row = _source_record_values(repo_id, "data_dictionary", item, ordinal)
        source_rows.append(source_row)
        occurrence_id = stable_id("dictionary", repo_id, local_id or record_id, ordinal)
        value_rows.append((occurrence_id, repo_id, local_id, _string(item, "object_name", "table_name", "entity_name"), _string(item, "attribute_name", "column_name", "field_name"), _string(item, "description", "comment", "text"), _json(item)))
        evidence_rows.extend(_evidence_ref_rows(repo_id, "data_dictionary_entry", occurrence_id, item))
        count += 1
        if len(value_rows) >= 500:
            _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO data_dictionary_entry VALUES (?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO data_dictionary_entry VALUES (?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    return count


def _load_gaps(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    source_rows: list[tuple[Any, ...]] = []
    value_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id, source_row = _source_record_values(repo_id, "evidence_gaps", item, ordinal)
        source_rows.append(source_row)
        occurrence_id = stable_id("gap", repo_id, local_id or record_id, ordinal)
        description = str(item.get("description") or item.get("message") or item.get("missing_fact_kind") or "Unspecified missing fact")
        value_rows.append((occurrence_id, repo_id, local_id, _string(item, "category"), _string(item, "missing_fact_kind", "gap_type", "kind"), _string(item, "required_for_operation"), description, _json(item.get("affected_entity_ids") or []), _json(item.get("affected_physical_asset_ids") or []), _json(item)))
        evidence_rows.extend(_evidence_ref_rows(repo_id, "workspace_missing_fact", occurrence_id, item))
        count += 1
        if len(value_rows) >= 500:
            _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO workspace_missing_fact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO workspace_missing_fact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    return count


def _load_requests(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    source_rows: list[tuple[Any, ...]] = []
    value_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id, source_row = _source_record_values(repo_id, "source_inspection_requests", item, ordinal)
        source_rows.append(source_row)
        occurrence_id = stable_id("inspection", repo_id, local_id or record_id, ordinal)
        value_rows.append((occurrence_id, repo_id, local_id, _string(item, "request_kind", "kind"), _string(item, "description", "reason", "request"), _json(item)))
        evidence_rows.extend(_evidence_ref_rows(repo_id, "source_inspection_request", occurrence_id, item))
        count += 1
        if len(value_rows) >= 500:
            _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO source_inspection_request VALUES (?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    _flush_stream_rows(con, source_rows=source_rows, value_sql="INSERT INTO source_inspection_request VALUES (?, ?, ?, ?, ?, ?)", value_rows=value_rows, evidence_rows=evidence_rows)
    return count


def _technical_type_name(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = raw.rsplit(".", 1)[-1]
    return normalize_field_correspondence_path(raw)


def _entity_candidates_for_structure(
    con: duckdb.DuckDBPyConnection,
    *,
    repo_id: str,
    container_name: str,
    container_fqcn: str | None = None,
    storage_target: str | None = None,
) -> tuple[list[str], list[str]]:
    # Prefer an exact observed qualified Java type identity.  A simple class
    # name is only a fallback because distinct packages may declare the same
    # name (for example two independent Consent classes).
    qualified_candidates: list[str] = []
    for observed_qualified in (container_fqcn, storage_target):
        raw = str(observed_qualified or "").strip()
        if not raw or "." not in raw or any(token in raw for token in ("(", ")", " ")):
            continue
        normalized_qualified = normalize_db_identifier(raw)
        if not normalized_qualified:
            continue
        exact = [
            row[0]
            for row in con.execute(
                "SELECT entity_occurrence_id FROM data_model_entity WHERE repo_id=? AND normalized_qualified_name=? ORDER BY occurrence_ordinal, entity_occurrence_id",
                [repo_id, normalized_qualified],
            ).fetchall()
        ]
        if exact:
            qualified_candidates.extend(exact)
    qualified_candidates = list(dict.fromkeys(qualified_candidates))
    if qualified_candidates:
        return qualified_candidates, ["exact_normalized_qualified_type_name"]

    normalized = _technical_type_name(container_name)
    if not normalized:
        return [], []
    candidates: list[str] = []
    for occurrence_id, name, canonical_name, qualified_name in con.execute(
        "SELECT entity_occurrence_id, name, canonical_name, qualified_name FROM data_model_entity WHERE repo_id=? ORDER BY occurrence_ordinal, entity_occurrence_id",
        [repo_id],
    ).fetchall():
        observed = {
            _technical_type_name(name),
            _technical_type_name(canonical_name),
            _technical_type_name(qualified_name),
        }
        if normalized in observed:
            candidates.append(occurrence_id)
    return candidates, (["exact_normalized_technical_type_name"] if candidates else [])


def _physical_asset_candidates_for_table(
    con: duckdb.DuckDBPyConnection,
    *,
    repo_id: str,
    table_name: str | None,
    qualified_table_name: str | None,
) -> tuple[list[str], list[str]]:
    normalized_qualified = normalize_db_identifier(qualified_table_name)
    if normalized_qualified:
        exact = [
            row[0]
            for row in con.execute(
                "SELECT physical_asset_occurrence_id FROM physical_asset WHERE repo_id=? AND normalized_qualified_name=? ORDER BY occurrence_ordinal, physical_asset_occurrence_id",
                [repo_id, normalized_qualified],
            ).fetchall()
        ]
        if exact:
            return exact, ["exact_normalized_qualified_table_name"]
    normalized_table = normalize_db_identifier(table_name or qualified_table_name).rsplit(".", 1)[-1]
    if not normalized_table:
        return [], []
    candidates = [
        row[0]
        for row in con.execute(
            """
            SELECT physical_asset_occurrence_id
            FROM physical_asset
            WHERE repo_id=? AND split_part(normalized_qualified_name, '.', -1)=?
            ORDER BY occurrence_ordinal, physical_asset_occurrence_id
            """,
            [repo_id, normalized_table],
        ).fetchall()
    ]
    return candidates, (["exact_normalized_short_table_name"] if candidates else [])


def _db_table_candidates(
    con: duckdb.DuckDBPyConnection,
    *,
    repo_id: str,
    local_table_id: str | None = None,
    table_name: str | None,
    qualified_table_name: str | None,
    module_name: str | None,
    source_set: str | None,
) -> list[str]:
    if local_table_id:
        exact_local = [
            row[0]
            for row in con.execute(
                "SELECT db_table_occurrence_id FROM db_schema_table WHERE repo_id=? AND local_table_id=? ORDER BY occurrence_ordinal, db_table_occurrence_id",
                [repo_id, local_table_id],
            ).fetchall()
        ]
        if exact_local:
            return exact_local
    normalized_qualified = normalize_db_identifier(qualified_table_name)
    if normalized_qualified:
        rows = con.execute(
            """
            SELECT db_table_occurrence_id FROM db_schema_table
            WHERE repo_id=? AND normalized_qualified_table_name=?
            ORDER BY occurrence_ordinal, db_table_occurrence_id
            """,
            [repo_id, normalized_qualified],
        ).fetchall()
        if rows:
            return [row[0] for row in rows]
    normalized_table = normalize_db_identifier(table_name or qualified_table_name).rsplit(".", 1)[-1]
    if not normalized_table:
        return []
    rows = con.execute(
        """
        SELECT db_table_occurrence_id, module_name, source_set
        FROM db_schema_table
        WHERE repo_id=? AND normalized_table_name=?
        ORDER BY occurrence_ordinal, db_table_occurrence_id
        """,
        [repo_id, normalized_table],
    ).fetchall()
    if module_name:
        same_module = [row[0] for row in rows if row[1] == module_name and (not source_set or row[2] == source_set)]
        if same_module:
            return same_module
    if source_set:
        same_set = [row[0] for row in rows if row[2] == source_set]
        if same_set:
            return same_set
    return [row[0] for row in rows]


def _db_column_candidates(
    con: duckdb.DuckDBPyConnection,
    *,
    repo_id: str,
    table_candidates: list[str],
    local_column_id: str | None = None,
    column_name: str | None,
) -> list[str]:
    if local_column_id:
        clauses = ["repo_id=?", "local_column_id=?"]
        args: list[Any] = [repo_id, local_column_id]
        if table_candidates:
            placeholders = ",".join("?" for _ in table_candidates)
            clauses.append(f"db_table_occurrence_id IN ({placeholders})")
            args.extend(table_candidates)
        exact_local = [
            row[0]
            for row in con.execute(
                f"SELECT db_column_occurrence_id FROM db_schema_column WHERE {' AND '.join(clauses)} ORDER BY occurrence_ordinal, db_column_occurrence_id",
                args,
            ).fetchall()
        ]
        if exact_local:
            return exact_local
    normalized_column = normalize_db_identifier(column_name).rsplit(".", 1)[-1]
    if not table_candidates or not normalized_column:
        return []
    placeholders = ",".join("?" for _ in table_candidates)
    return [
        row[0]
        for row in con.execute(
            f"""
            SELECT db_column_occurrence_id
            FROM db_schema_column
            WHERE repo_id=?
              AND db_table_occurrence_id IN ({placeholders})
              AND normalized_column_name=?
            ORDER BY occurrence_ordinal, db_column_occurrence_id
            """,
            [repo_id, *table_candidates, normalized_column],
        ).fetchall()
    ]


def _table_ref_values(item: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None, str | None, str]:
    local_table_id = _string(item, "table_id")
    table_name = _string(item, "table_name")
    schema_name = _string(item, "schema_name")
    qualified = _string(item, "qualified_table_name")
    unresolved = _string(item, "unresolved_name")
    normalized = normalize_db_identifier(qualified or table_name or unresolved)
    return local_table_id, table_name, schema_name, qualified, unresolved, normalized


def _column_ref_values(item: dict[str, Any]) -> tuple[str | None, str | None, str | None, str]:
    local_column_id = _string(item, "column_id")
    column_name = _string(item, "column_name")
    unresolved = _string(item, "unresolved_name")
    normalized = normalize_db_identifier(column_name or unresolved).rsplit(".", 1)[-1]
    return local_column_id, column_name, unresolved, normalized


def _insert_local_correspondence(
    con: duckdb.DuckDBPyConnection,
    *,
    observation_kind: str,
    repo_id: str,
    normalized_value: str,
    left_object_kind: str,
    left_occurrence_id: str,
    right_object_kind: str,
    right_occurrence_id: str,
    basis: list[str],
) -> None:
    observation_id = stable_id(
        "local_observation",
        observation_kind,
        repo_id,
        normalized_value,
        left_object_kind,
        left_occurrence_id,
        right_object_kind,
        right_occurrence_id,
    )
    con.execute(
        "INSERT OR IGNORE INTO data_model_local_correspondence_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            observation_id,
            observation_kind,
            repo_id,
            normalized_value,
            left_object_kind,
            left_occurrence_id,
            right_object_kind,
            right_occurrence_id,
            _json({"basis": basis, "meaning": "technical_correspondence_only_no_semantic_equivalence"}),
        ],
    )


def _load_persistent_structures(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    rows: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    structure_count = 0
    attribute_count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "persistent_structures", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_structure_id = local_id or stable_id("local_structure", _json(item))
        occurrence_id = stable_id("persistent_structure", repo_id, local_structure_id, ordinal)
        container_name = str(item.get("container_name") or local_structure_id)
        container_fqcn = _string(item, "container_fqcn", "qualified_name")
        storage_target = _string(item, "storage_target")
        candidates, basis = _entity_candidates_for_structure(
            con,
            repo_id=repo_id,
            container_name=container_name,
            container_fqcn=container_fqcn,
            storage_target=storage_target,
        )
        con.execute(
            "INSERT INTO persistent_structure VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id,
                repo_id,
                local_structure_id,
                ordinal,
                record_id,
                _string(item, "storage_kind"),
                storage_target,
                _string(item, "container_kind"),
                container_name,
                container_fqcn,
                normalize_db_identifier(container_fqcn),
                _technical_type_name(container_name),
                _int(item.get("field_count")),
                _string(item, "source_scope"),
                _string(item, "source_set"),
                _bool(item.get("is_test_source")),
                _string(item, "module_name"),
                _single(candidates),
                _json(candidates),
                _json(basis),
                _json(item),
            ],
        )
        _insert_evidence_refs(
            con,
            repo_id=repo_id,
            owner_type="persistent_structure",
            owner_occurrence_id=occurrence_id,
            item=item,
        )
        for entity_occurrence_id in candidates:
            _insert_local_correspondence(
                con,
                observation_kind="exact_persistent_structure_entity_name",
                repo_id=repo_id,
                normalized_value=(normalize_db_identifier(container_fqcn) if "exact_normalized_qualified_type_name" in basis else _technical_type_name(container_name)),
                left_object_kind="persistent_structure",
                left_occurrence_id=occurrence_id,
                right_object_kind="data_model_entity",
                right_occurrence_id=entity_occurrence_id,
                basis=basis,
            )
        raw_fields = item.get("fields") or []
        if not isinstance(raw_fields, list):
            raw_fields = []
        for position, field in enumerate(raw_fields):
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or field.get("java_field") or field.get("storage_field") or f"field_{position}")
            field_occurrence_id = stable_id(
                "persistent_structure_attribute",
                occurrence_id,
                normalize_field_correspondence_path(name),
                position,
            )
            con.execute(
                "INSERT INTO persistent_structure_attribute VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    field_occurrence_id,
                    repo_id,
                    occurrence_id,
                    position,
                    name,
                    normalize_field_correspondence_path(name),
                    _string(field, "java_field"),
                    _string(field, "storage_field"),
                    _string(field, "type"),
                    _string(field, "raw_type"),
                    _string(field, "role"),
                    _string(field, "key_role"),
                    _json(field),
                ],
            )
            _insert_evidence_refs(
                con,
                repo_id=repo_id,
                owner_type="persistent_structure_attribute",
                owner_occurrence_id=field_occurrence_id,
                item=field,
            )
            attribute_count += 1
        structure_count += 1
    return structure_count, attribute_count


def _load_db_schema_tables(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    rows: Iterable[dict[str, Any]],
) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_tables", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_table_id = local_id or stable_id("local_db_table", _json(item))
        occurrence_id = stable_id("db_table", repo_id, local_table_id, ordinal)
        table_name = str(item.get("table_name") or item.get("name") or local_table_id)
        qualified = _string(item, "qualified_table_name") or table_name
        candidates, basis = _physical_asset_candidates_for_table(
            con,
            repo_id=repo_id,
            table_name=table_name,
            qualified_table_name=qualified,
        )
        con.execute(
            "INSERT INTO db_schema_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id,
                repo_id,
                local_table_id,
                ordinal,
                record_id,
                table_name,
                normalize_db_identifier(table_name).rsplit(".", 1)[-1],
                _string(item, "schema_name"),
                qualified,
                normalize_db_identifier(qualified),
                _string(item, "description"),
                _string(item, "source_type"),
                _string(item, "source_set"),
                _bool(item.get("is_test_source")),
                _string(item, "module_name"),
                _string(item, "evidence_maturity_level"),
                _single(candidates),
                _json(candidates),
                _json(basis),
                _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_table", owner_occurrence_id=occurrence_id, item=item)
        for asset_occurrence_id in candidates:
            _insert_local_correspondence(
                con,
                observation_kind="exact_db_table_physical_asset_name",
                repo_id=repo_id,
                normalized_value=normalize_db_identifier(qualified or table_name),
                left_object_kind="db_schema_table",
                left_occurrence_id=occurrence_id,
                right_object_kind="physical_asset",
                right_occurrence_id=asset_occurrence_id,
                basis=basis,
            )
        count += 1
    return count


def _db_table_fields(item: dict[str, Any]) -> tuple[str, str, str | None, str, str | None, str | None]:
    table_name = str(item.get("table_name") or item.get("source_table") or item.get("name") or "")
    qualified = _string(item, "qualified_table_name") or table_name
    return (
        table_name,
        normalize_db_identifier(table_name).rsplit(".", 1)[-1],
        qualified,
        normalize_db_identifier(qualified),
        _string(item, "module_name"),
        _string(item, "source_set"),
    )


def _load_db_schema_columns(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_columns", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_column_id = local_id or stable_id("local_db_column", _json(item))
        occurrence_id = stable_id("db_column", repo_id, local_column_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(con, repo_id=repo_id, table_name=table_name, qualified_table_name=qualified, module_name=module_name, source_set=source_set)
        column_name = str(item.get("column_name") or item.get("name") or local_column_id)
        con.execute(
            "INSERT INTO db_schema_column VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_column_id, ordinal, record_id,
                table_name, normalized_table, _string(item, "schema_name"), qualified, normalized_qualified,
                column_name, normalize_db_identifier(column_name), _string(item, "sql_type", "data_type"),
                _bool(item.get("nullable")), None if item.get("default_value") is None else str(item.get("default_value")),
                _string(item, "description"), _string(item, "source_type"), source_set,
                _bool(item.get("is_test_source")), module_name, _string(item, "evidence_maturity_level"),
                _single(candidates), _json(candidates), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_column", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_keys(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_keys", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_key_id = local_id or stable_id("local_db_key", _json(item))
        occurrence_id = stable_id("db_key", repo_id, local_key_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(con, repo_id=repo_id, table_name=table_name, qualified_table_name=qualified, module_name=module_name, source_set=source_set)
        con.execute(
            "INSERT INTO db_schema_key VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_key_id, ordinal, record_id,
                _string(item, "constraint_name", "name"), _string(item, "constraint_kind", "kind"),
                table_name, normalized_table, qualified, normalized_qualified, _json(item.get("columns") or []),
                source_set, _bool(item.get("is_test_source")), module_name, _single(candidates), _json(candidates), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_key", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_relationships(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_relationships", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_relationship_id = local_id or stable_id("local_db_relationship", _json(item))
        occurrence_id = stable_id("db_relationship", repo_id, local_relationship_id, ordinal)
        source_table = str(item.get("source_table") or "")
        target_table = str(item.get("target_table") or "")
        source_qualified = _string(item, "source_qualified_table_name") or source_table
        target_qualified = _string(item, "target_qualified_table_name") or target_table
        module_name = _string(item, "module_name")
        source_set = _string(item, "source_set")
        source_candidates = _db_table_candidates(con, repo_id=repo_id, table_name=source_table, qualified_table_name=source_qualified, module_name=module_name, source_set=source_set)
        target_candidates = _db_table_candidates(con, repo_id=repo_id, table_name=target_table, qualified_table_name=target_qualified, module_name=module_name, source_set=source_set)
        con.execute(
            "INSERT INTO db_schema_relationship VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_relationship_id, ordinal, record_id,
                _string(item, "constraint_name"), _string(item, "relationship_kind", "kind"),
                source_table, normalize_db_identifier(source_table).rsplit(".", 1)[-1], source_qualified, normalize_db_identifier(source_qualified), _json(item.get("source_columns") or []),
                target_table, normalize_db_identifier(target_table).rsplit(".", 1)[-1], target_qualified, normalize_db_identifier(target_qualified), _json(item.get("target_columns") or []),
                _single(source_candidates), _json(source_candidates), _single(target_candidates), _json(target_candidates),
                source_set, _bool(item.get("is_test_source")), module_name, _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_relationship", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_constraints(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_constraints", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_constraint_id = local_id or stable_id("local_db_constraint", _json(item))
        occurrence_id = stable_id("db_constraint", repo_id, local_constraint_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(con, repo_id=repo_id, table_name=table_name, qualified_table_name=qualified, module_name=module_name, source_set=source_set)
        con.execute(
            "INSERT INTO db_schema_constraint VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_constraint_id, ordinal, record_id,
                _string(item, "constraint_name", "name"), _string(item, "constraint_kind", "kind"),
                table_name, normalized_table, qualified, normalized_qualified, _string(item, "column_name"),
                _string(item, "expression"), _json(item.get("literal_values") or []), source_set,
                _bool(item.get("is_test_source")), module_name, _single(candidates), _json(candidates), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_constraint", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_indexes(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_indexes", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_index_id = local_id or stable_id("local_db_index", _json(item))
        occurrence_id = stable_id("db_index", repo_id, local_index_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(con, repo_id=repo_id, table_name=table_name, qualified_table_name=qualified, module_name=module_name, source_set=source_set)
        con.execute(
            "INSERT INTO db_schema_index VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_index_id, ordinal, record_id, _string(item, "index_name", "name"),
                table_name, normalized_table, qualified, normalized_qualified, _json(item.get("columns") or []),
                _bool(item.get("unique")), source_set, _bool(item.get("is_test_source")), module_name,
                _single(candidates), _json(candidates), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_index", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_partitioning(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_partitioning", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_id = local_id or stable_id("local_db_partitioning", _json(item))
        occurrence_id = stable_id("db_partitioning", repo_id, local_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(
            con,
            repo_id=repo_id,
            table_name=table_name,
            qualified_table_name=qualified,
            module_name=module_name,
            source_set=source_set,
        )
        fact_kind = str(item.get("partition_fact_kind") or "parent_partitioning")
        partition_table_name = _string(item, "partition_table_name")
        qualified_partition = _string(item, "qualified_partition_table_name") or partition_table_name
        normalized_qualified_partition = normalize_db_identifier(qualified_partition or "")
        con.execute(
            "INSERT INTO db_schema_partitioning VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_id, ordinal, record_id, fact_kind,
                table_name, normalized_table, _string(item, "schema_name"), qualified, normalized_qualified,
                _string(item, "partition_strategy"), _json(item.get("partition_columns") or []),
                partition_table_name, _string(item, "partition_schema_name"), qualified_partition,
                normalized_qualified_partition, _string(item, "partition_bound_kind"),
                _string(item, "partition_bound_expression"), _string(item, "tablespace"), source_set,
                _bool(item.get("is_test_source")), module_name, _single(candidates), _json(candidates), _json(item),
            ],
        )
        _insert_evidence_refs(
            con, repo_id=repo_id, owner_type="db_schema_partitioning", owner_occurrence_id=occurrence_id, item=item
        )
        count += 1
    return count


def _load_db_schema_sequences(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_sequences", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_id = local_id or stable_id("local_db_sequence", _json(item))
        occurrence_id = stable_id("db_sequence", repo_id, local_id, ordinal)
        name = _string(item, "sequence_name", "name") or local_id
        qualified = _string(item, "qualified_sequence_name") or name
        con.execute(
            "INSERT INTO db_schema_sequence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, repo_id, local_id, ordinal, record_id, name, normalize_db_identifier(name), _string(item, "schema_name"), qualified, _json(item)],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_sequence", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_db_schema_triggers(con: duckdb.DuckDBPyConnection, repo_id: str, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "db_schema_triggers", item, ordinal)
        if not _included_static_data_model_record(item):
            continue
        local_id = local_id or stable_id("local_db_trigger", _json(item))
        occurrence_id = stable_id("db_trigger", repo_id, local_id, ordinal)
        table_name, normalized_table, qualified, normalized_qualified, module_name, source_set = _db_table_fields(item)
        candidates = _db_table_candidates(con, repo_id=repo_id, table_name=table_name, qualified_table_name=qualified, module_name=module_name, source_set=source_set)
        con.execute(
            "INSERT INTO db_schema_trigger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, repo_id, local_id, ordinal, record_id, _string(item, "trigger_name", "name"), table_name, normalized_table, qualified, normalized_qualified, _single(candidates), _json(candidates), _json(item)],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="db_schema_trigger", owner_occurrence_id=occurrence_id, item=item)
        count += 1
    return count


def _load_table_relationship_observations(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    rows: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    observation_count = 0
    pair_count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "table_relationship_observations", item, ordinal)
        local_observation_id = local_id or stable_id("local_table_relationship_observation", _json(item))
        occurrence_id = stable_id("table_relationship_observation", repo_id, local_observation_id, ordinal)
        left = item.get("left_table") if isinstance(item.get("left_table"), dict) else {}
        right = item.get("right_table") if isinstance(item.get("right_table"), dict) else {}
        ltid, lt, ls, lq, lu, ln = _table_ref_values(left)
        rtid, rt, rs, rq, ru, rn = _table_ref_values(right)
        source_kind = _string(item, "source_kind") or "unknown"
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        left_candidates = _db_table_candidates(
            con, repo_id=repo_id, local_table_id=ltid, table_name=lt or lu, qualified_table_name=lq,
            module_name=_string(properties, "module_name"), source_set=_string(properties, "source_set"),
        )
        right_candidates = _db_table_candidates(
            con, repo_id=repo_id, local_table_id=rtid, table_name=rt or ru, qualified_table_name=rq,
            module_name=_string(properties, "module_name"), source_set=_string(properties, "source_set"),
        )
        con.execute(
            "INSERT INTO table_relationship_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_observation_id, ordinal, record_id,
                _string(item, "schema_version") or "table_relationship_observation/v1",
                _string(item, "relation_kind") or "unknown", source_kind,
                _string(item, "statement_id"), _string(item, "query_id"), _string(item, "join_type"), _string(item, "direction"),
                ltid, lt, ls, lq, ln, lu, _single(left_candidates), _json(left_candidates),
                rtid, rt, rs, rq, rn, ru, _single(right_candidates), _json(right_candidates),
                _json(item.get("matched_declared_keys") or []), _json(properties), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="table_relationship_observation", owner_occurrence_id=occurrence_id, item=item)
        raw_pairs = item.get("column_pairs") if isinstance(item.get("column_pairs"), list) else []
        for pair_ordinal, pair in enumerate(raw_pairs):
            if not isinstance(pair, dict):
                continue
            left_col = pair.get("left") if isinstance(pair.get("left"), dict) else {}
            right_col = pair.get("right") if isinstance(pair.get("right"), dict) else {}
            lcid, lcn, lcu, lcnn = _column_ref_values(left_col)
            rcid, rcn, rcu, rcnn = _column_ref_values(right_col)
            left_column_candidates = _db_column_candidates(con, repo_id=repo_id, table_candidates=left_candidates, local_column_id=lcid, column_name=lcn or lcu)
            right_column_candidates = _db_column_candidates(con, repo_id=repo_id, table_candidates=right_candidates, local_column_id=rcid, column_name=rcn or rcu)
            pair_id = stable_id("table_relationship_column_pair", occurrence_id, pair_ordinal)
            con.execute(
                "INSERT INTO table_relationship_column_pair VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    pair_id, repo_id, occurrence_id, pair_ordinal, _int(pair.get("predicate_ordinal")),
                    _string(pair, "operator") or "=",
                    lcid, lcn, lcnn, lcu, _single(left_column_candidates), _json(left_column_candidates),
                    rcid, rcn, rcnn, rcu, _single(right_column_candidates), _json(right_column_candidates),
                    _json(pair),
                ],
            )
            pair_count += 1
        observation_count += 1
    return observation_count, pair_count


def _load_table_key_observations(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    rows: Iterable[dict[str, Any]],
) -> tuple[int, int]:
    observation_count = 0
    column_count = 0
    for ordinal, item in enumerate(rows):
        record_id, local_id = _source_record(con, repo_id, "table_key_observations", item, ordinal)
        local_observation_id = local_id or stable_id("local_table_key_observation", _json(item))
        occurrence_id = stable_id("table_key_observation", repo_id, local_observation_id, ordinal)
        table = item.get("table") if isinstance(item.get("table"), dict) else {}
        local_table_id, tn, sn, qn, unresolved, normalized = _table_ref_values(table)
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        table_candidates = _db_table_candidates(
            con, repo_id=repo_id, local_table_id=local_table_id, table_name=tn or unresolved, qualified_table_name=qn,
            module_name=_string(properties, "module_name"), source_set=_string(properties, "source_set"),
        )
        con.execute(
            "INSERT INTO table_key_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                occurrence_id, repo_id, local_observation_id, ordinal, record_id,
                _string(item, "schema_version") or "table_key_observation/v1",
                _string(item, "key_kind") or "unknown", _string(item, "source_kind") or "unknown",
                local_table_id, tn, sn, qn, normalized, unresolved, _single(table_candidates), _json(table_candidates),
                _string(item, "constraint_name"), _string(item, "index_name"), _string(item, "entity_name"),
                _json(item.get("observation_basis") or []), _json(properties), _json(item),
            ],
        )
        _insert_evidence_refs(con, repo_id=repo_id, owner_type="table_key_observation", owner_occurrence_id=occurrence_id, item=item)
        raw_columns = item.get("columns") if isinstance(item.get("columns"), list) else []
        for column_ordinal, column in enumerate(raw_columns):
            if not isinstance(column, dict):
                continue
            local_column_id, cn, unresolved_column, normalized_column = _column_ref_values(column)
            candidates = _db_column_candidates(con, repo_id=repo_id, table_candidates=table_candidates, local_column_id=local_column_id, column_name=cn or unresolved_column)
            column_id = stable_id("table_key_observation_column", occurrence_id, column_ordinal)
            con.execute(
                "INSERT INTO table_key_observation_column VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [column_id, repo_id, occurrence_id, column_ordinal, local_column_id, cn, normalized_column, unresolved_column, _single(candidates), _json(candidates), _json(column)],
            )
            column_count += 1
        observation_count += 1
    return observation_count, column_count


def _source_observation_row(repo_id: str, item: dict[str, Any], ordinal: int) -> tuple[tuple[Any, ...], list[tuple[Any, ...]]]:
    properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    forbidden_decision_fields = {"confidence", "score", "status", "verdict", "probability", "severity"}
    observed_decision_fields = sorted(
        forbidden_decision_fields & ({str(key).lower() for key in item} | {str(key).lower() for key in properties})
    )
    if observed_decision_fields:
        raise ValueError(
            f"source observation contains forbidden decision fields: repo={repo_id}, "
            f"ordinal={ordinal}, fields={observed_decision_fields}"
        )
    fact_type = str(item.get("fact_type") or "").strip()
    local_id = str(item.get("fact_id") or properties.get("observation_id") or "").strip()
    if not fact_type or not local_id:
        raise ValueError(f"source observation requires fact_type and fact_id: repo={repo_id}, ordinal={ordinal}")
    occurrence_id = stable_id("source_observation", repo_id, fact_type, local_id, ordinal)
    evidence_path, line_start, line_end, extractor = _first_evidence_location(item)
    source_path = _string(properties, "source_path") or evidence_path
    method = _string(properties, "target_method", "method")
    arguments = properties.get("arguments")
    input_symbols = properties.get("input_symbols")
    expression_tree = properties.get("expression_tree")
    nested_calls = properties.get("nested_calls")
    candidates = properties.get("candidate_fqcns") or properties.get("annotation_candidate_fqcns") or []
    scalar_value = properties.get("value") if "value" in properties else None
    if fact_type == "configuration_object_observation":
        scalar_value = properties.get("scalar_fields")
    elif fact_type == "configuration_reference_observation":
        scalar_value = properties.get("reference_value")
    elif fact_type == "configuration_comment_observation":
        scalar_value = properties.get("comment_text")

    configuration_path = _string(properties, "configuration_path")
    parent_path = _string(properties, "parent_path", "container_path", "associated_configuration_path")
    node_kind = _string(properties, "node_kind", "reference_kind", "comment_kind")
    member_name = _string(properties, "member_name", "key")
    owner_fqcn = _string(properties, "owner_fqcn", "owner_qualified_name")
    referenced_type = _string(properties, "referenced_type")
    if not referenced_type and properties.get("reference_kind") == "java_type_reference":
        referenced_type = _string(properties, "reference_value")
    row = (
        occurrence_id,
        repo_id,
        local_id,
        ordinal,
        fact_type,
        _string(item, "name"),
        source_path,
        line_start,
        line_end,
        extractor,
        _string(properties, "syntax_provider"),
        owner_fqcn,
        _string(properties, "owner_type"),
        _string(properties, "owner_method"),
        _string(properties, "owner_operation"),
        _string(properties, "owner_kind"),
        _string(properties, "owner_scope_kind"),
        member_name,
        _string(properties, "reference_role"),
        referenced_type,
        _string(properties, "resolution", "resolution_kind"),
        _string(properties, "resolved_fqcn"),
        _json(candidates),
        _string(properties, "annotation"),
        _string(properties, "annotation_fqcn"),
        _string(properties, "annotation_resolution"),
        _json(arguments or {}),
        _int(properties.get("argument_count")),
        _string(properties, "configuration_format"),
        configuration_path,
        parent_path,
        node_kind,
        _json(scalar_value),
        _int(properties.get("child_count")),
        method,
        _string(properties, "receiver_expression"),
        _int(properties.get("argument_index")),
        _string(properties, "source_expression"),
        _string(properties, "target_variable"),
        _string(properties, "assignment_kind"),
        _string(properties, "target_kind"),
        _string(properties, "expression", "call_text"),
        _json(input_symbols or []),
        _json(expression_tree or {}),
        _json(nested_calls or []),
        _string(properties, "operation_kind"),
        _string(properties, "dependency_kind"),
        _string(properties, "group_id"),
        _string(properties, "artifact_id"),
        _string(properties, "version"),
        _string(properties, "scope"),
        _string(properties, "coordinate"),
        _string(properties, "call_observation_id"),
        _json(item),
    )
    return row, _evidence_ref_rows(repo_id, "source_observation", occurrence_id, item)


def _load_source_observations(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    fact_type: str,
    rows: Iterable[dict[str, Any]],
    *,
    batch_size: int = 100000,
) -> int:
    observation_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    count = 0
    for ordinal, item in enumerate(rows):
        observed_type = str(item.get("fact_type") or "").strip()
        if observed_type != fact_type:
            raise ValueError(
                f"source observation fact_type mismatch for {repo_id}/{fact_type}: observed={observed_type!r}"
            )
        row, refs = _source_observation_row(repo_id, item, ordinal)
        observation_rows.append(row)
        evidence_rows.extend(refs)
        count += 1
        if len(observation_rows) >= batch_size:
            _bulk_insert(con, "INSERT INTO source_observation VALUES (" + ",".join("?" for _ in observation_rows[0]) + ")", observation_rows)
            _bulk_insert(con, "INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", evidence_rows)
            observation_rows.clear()
            evidence_rows.clear()
    if observation_rows:
        _bulk_insert(con, "INSERT INTO source_observation VALUES (" + ",".join("?" for _ in observation_rows[0]) + ")", observation_rows)
        _bulk_insert(con, "INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", evidence_rows)
    return count


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _build_effective_entity_fields_from_code(con: duckdb.DuckDBPyConnection) -> int:
    """Materialize direct/inherited field observations when the repository did not publish an effective-field projection.

    The construction is mechanical: start from each observed Java type, follow resolved
    ``extends`` observations, and select the nearest observed declaration for every field
    name.  No conceptual-entity, persistence, publication, or relationship verdict is
    assigned.  Existing repository-published effective fields always take precedence.
    """
    type_rows = _rows_from_cursor(con.execute(
        """SELECT java_type_occurrence_id, repo_id, fqcn, simple_name, class_kind
           FROM java_type_declaration
           ORDER BY repo_id, fqcn, occurrence_ordinal, java_type_occurrence_id"""
    ))
    field_rows = _rows_from_cursor(con.execute(
        """SELECT code_field_occurrence_id, repo_id, occurrence_ordinal, source_record_id,
                  owner_fqcn, owner_name, owner_kind, field_name, declared_type, raw_type,
                  container_kind, element_type, annotations_json, model_exclusion_observed,
                  model_exclusion_annotations_json, source_path, source_scope, line_start,
                  evidence_maturity_level, payload_json
           FROM code_field_observation
           ORDER BY repo_id, owner_fqcn, occurrence_ordinal, field_name, code_field_occurrence_id"""
    ))
    inheritance_rows = _rows_from_cursor(con.execute(
        """SELECT inheritance_occurrence_id, repo_id, child_fqcn, relation_kind,
                  resolved_parent_fqcn, parent_java_type_occurrence_id
           FROM java_inheritance_observation
           WHERE resolved_parent_fqcn IS NOT NULL
           ORDER BY repo_id, child_fqcn,
                    CASE WHEN relation_kind='extends' THEN 0 ELSE 1 END,
                    occurrence_ordinal, inheritance_occurrence_id"""
    ))
    if not type_rows or not field_rows:
        return 0

    existing = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in con.execute(
            "SELECT repo_id, effective_owner_fqcn, field_name FROM effective_entity_field"
        ).fetchall()
    }
    types_by_occurrence = {
        str(row.get("java_type_occurrence_id") or ""): row
        for row in type_rows
        if row.get("java_type_occurrence_id")
    }
    types_by_repo_fqcn: dict[tuple[str, str], list[dict[str, Any]]] = {}
    types_by_fqcn: dict[str, list[dict[str, Any]]] = {}
    for row in type_rows:
        repo_id = str(row.get("repo_id") or "")
        fqcn = str(row.get("fqcn") or "")
        if fqcn:
            types_by_repo_fqcn.setdefault((repo_id, fqcn), []).append(row)
            types_by_fqcn.setdefault(fqcn, []).append(row)

    fields_by_repo_owner: dict[tuple[str, str], list[dict[str, Any]]] = {}
    fields_by_owner: dict[str, list[dict[str, Any]]] = {}
    for row in field_rows:
        repo_id = str(row.get("repo_id") or "")
        owner = str(row.get("owner_fqcn") or "")
        if owner:
            fields_by_repo_owner.setdefault((repo_id, owner), []).append(row)
            fields_by_owner.setdefault(owner, []).append(row)

    parents_by_repo_child: dict[tuple[str, str], list[dict[str, Any]]] = {}
    parents_by_child: dict[str, list[dict[str, Any]]] = {}
    for row in inheritance_rows:
        repo_id = str(row.get("repo_id") or "")
        child = str(row.get("child_fqcn") or "")
        if child:
            parents_by_repo_child.setdefault((repo_id, child), []).append(row)
            parents_by_child.setdefault(child, []).append(row)

    entity_occurrences: dict[tuple[str, str], list[str]] = {}
    for repo_id, qualified_name, occurrence_id in con.execute(
        """SELECT repo_id, qualified_name, entity_occurrence_id
           FROM data_model_entity
           WHERE qualified_name IS NOT NULL
           ORDER BY repo_id, qualified_name, entity_occurrence_id"""
    ).fetchall():
        entity_occurrences.setdefault((str(repo_id), str(qualified_name)), []).append(str(occurrence_id))

    evidence_by_owner: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for owner_type, owner_occurrence_id, file_path, line_start, line_end, json_pointer, payload_json in con.execute(
        """SELECT owner_type, owner_occurrence_id, file_path, line_start, line_end,
                  json_pointer, payload_json
           FROM evidence_ref
           WHERE owner_type IN ('code_field_observation','java_inheritance_observation')
           ORDER BY owner_type, owner_occurrence_id, evidence_ref_id"""
    ).fetchall():
        evidence_by_owner.setdefault((str(owner_type), str(owner_occurrence_id)), []).append({
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_end,
            "json_pointer": json_pointer,
            "payload": _json_value(payload_json),
        })

    def declaration_fields(repo_id: str, owner_fqcn: str) -> list[dict[str, Any]]:
        local = fields_by_repo_owner.get((repo_id, owner_fqcn), [])
        if local:
            return local
        global_rows = fields_by_owner.get(owner_fqcn, [])
        global_repos = {str(row.get("repo_id") or "") for row in global_rows}
        return global_rows if len(global_repos) == 1 else []

    def parent_step(repo_id: str, child_fqcn: str) -> tuple[str, str, str] | None:
        candidates = list(parents_by_repo_child.get((repo_id, child_fqcn), []))
        if not candidates:
            global_candidates = parents_by_child.get(child_fqcn, [])
            candidate_repos = {str(row.get("repo_id") or "") for row in global_candidates}
            if len(candidate_repos) == 1:
                candidates = list(global_candidates)
        if not candidates:
            return None
        extends = [row for row in candidates if str(row.get("relation_kind") or "") == "extends"]
        candidates = extends or candidates
        distinct = {
            (str(row.get("resolved_parent_fqcn") or ""), str(row.get("parent_java_type_occurrence_id") or ""))
            for row in candidates
            if row.get("resolved_parent_fqcn")
        }
        if len(distinct) != 1:
            return None
        parent_fqcn, parent_type_id = next(iter(distinct))
        parent_repo = repo_id
        if parent_type_id and parent_type_id in types_by_occurrence:
            parent_repo = str(types_by_occurrence[parent_type_id].get("repo_id") or repo_id)
        elif not types_by_repo_fqcn.get((repo_id, parent_fqcn)):
            definitions = types_by_fqcn.get(parent_fqcn, [])
            definition_repos = {str(row.get("repo_id") or "") for row in definitions}
            if len(definition_repos) == 1:
                parent_repo = next(iter(definition_repos))
            else:
                return None
        selected = sorted(
            candidates,
            key=lambda row: (
                0 if str(row.get("relation_kind") or "") == "extends" else 1,
                str(row.get("inheritance_occurrence_id") or ""),
            ),
        )[0]
        return parent_repo, parent_fqcn, str(selected.get("inheritance_occurrence_id") or "")

    table_rows: list[tuple[Any, ...]] = []
    evidence_rows: list[tuple[Any, ...]] = []
    ordinal = int(con.execute("SELECT count(*) FROM effective_entity_field").fetchone()[0])
    for effective_type in type_rows:
        effective_repo = str(effective_type.get("repo_id") or "")
        effective_fqcn = str(effective_type.get("fqcn") or "")
        if not effective_repo or not effective_fqcn:
            continue
        lineage: list[tuple[str, str, str | None]] = [(effective_repo, effective_fqcn, None)]
        visited = {(effective_repo, effective_fqcn)}
        while True:
            current_repo, current_fqcn, _ = lineage[-1]
            step = parent_step(current_repo, current_fqcn)
            if step is None:
                break
            parent_repo, parent_fqcn, inheritance_id = step
            marker = (parent_repo, parent_fqcn)
            if marker in visited:
                break
            visited.add(marker)
            lineage.append((parent_repo, parent_fqcn, inheritance_id))

        observed_names: set[str] = set()
        inheritance_ids: list[str] = []
        for depth, (declaration_repo, declaration_fqcn, incoming_inheritance_id) in enumerate(lineage):
            if incoming_inheritance_id:
                inheritance_ids.append(incoming_inheritance_id)
            fields = declaration_fields(declaration_repo, declaration_fqcn)
            by_name: dict[str, list[dict[str, Any]]] = {}
            for field in fields:
                name = str(field.get("field_name") or "")
                if name:
                    by_name.setdefault(name, []).append(field)
            for field_name in sorted(by_name):
                if field_name in observed_names:
                    continue
                observed_names.add(field_name)
                candidates = sorted(
                    by_name[field_name],
                    key=lambda row: (
                        int(row.get("occurrence_ordinal") or 0),
                        str(row.get("code_field_occurrence_id") or ""),
                    ),
                )
                for field in candidates:
                    if (effective_repo, effective_fqcn, field_name) in existing:
                        continue
                    code_field_id = str(field.get("code_field_occurrence_id") or "")
                    local_id = stable_id(
                        "derived_effective_field_local",
                        effective_repo,
                        effective_fqcn,
                        field_name,
                        code_field_id,
                    )
                    occurrence_id = stable_id(
                        "effective_field_from_code",
                        effective_repo,
                        effective_fqcn,
                        field_name,
                        code_field_id,
                    )
                    declaration_type_candidates = types_by_repo_fqcn.get((declaration_repo, declaration_fqcn), [])
                    declaration_type_id = (
                        str(declaration_type_candidates[0].get("java_type_occurrence_id") or "")
                        if len(declaration_type_candidates) == 1
                        else None
                    )
                    owner_entities = entity_occurrences.get((effective_repo, effective_fqcn), [])
                    path = [item[1] for item in lineage[: depth + 1]]
                    path_inheritance_ids = [item for item in inheritance_ids if item]
                    source_payload = _json_value(field.get("payload_json")) or {}
                    source_properties = (
                        source_payload.get("properties")
                        if isinstance(source_payload.get("properties"), dict)
                        else {}
                    )
                    payload = {
                        "construction_kind": "code_field_inheritance_projection",
                        "effective_owner_fqcn": effective_fqcn,
                        "declaration_owner_fqcn": declaration_fqcn,
                        "source_code_field_occurrence_id": code_field_id,
                        "source_inheritance_occurrence_ids": path_inheritance_ids,
                        "candidate_declaration_count_at_selected_depth": len(candidates),
                        "field_name_shadowing_applied": depth > 0,
                        "semantic_verdict_assigned": False,
                        "display_name": source_properties.get("display_name"),
                        "description": source_properties.get("description"),
                        "documentation_summary": source_properties.get("documentation_summary"),
                        "documentation_tags": source_properties.get("documentation_tags") or {},
                    }
                    table_rows.append((
                        occurrence_id,
                        effective_repo,
                        local_id,
                        ordinal,
                        str(field.get("source_record_id") or ""),
                        effective_fqcn,
                        str(effective_type.get("simple_name") or effective_fqcn.rsplit(".", 1)[-1]),
                        str(effective_type.get("class_kind") or ""),
                        owner_entities[0] if len(owner_entities) == 1 else None,
                        _json(owner_entities),
                        field_name,
                        field.get("declared_type"),
                        field.get("declared_type"),
                        declaration_fqcn,
                        declaration_type_id,
                        "code_inheritance_projection",
                        depth > 0,
                        depth,
                        _json(path),
                        field.get("container_kind"),
                        field.get("element_type"),
                        _json(_json_value(field.get("annotations_json")) or []),
                        bool(field.get("model_exclusion_observed")),
                        _json(_json_value(field.get("model_exclusion_annotations_json")) or []),
                        field.get("source_path"),
                        field.get("source_scope"),
                        "tree_sitter",
                        _json(payload),
                    ))
                    source_evidence: list[tuple[str, str, dict[str, Any]]] = [
                        ("code_field_observation", code_field_id, item)
                        for item in evidence_by_owner.get(("code_field_observation", code_field_id), [])
                    ]
                    for inheritance_id in path_inheritance_ids:
                        source_evidence.extend(
                            ("java_inheritance_observation", inheritance_id, item)
                            for item in evidence_by_owner.get(("java_inheritance_observation", inheritance_id), [])
                        )
                    for position, (source_owner_type, source_owner_id, evidence) in enumerate(source_evidence):
                        evidence_payload = {
                            "derived_from_owner_type": source_owner_type,
                            "derived_from_owner_occurrence_id": source_owner_id,
                            "source_evidence": evidence.get("payload"),
                        }
                        evidence_rows.append((
                            stable_id("ev", effective_repo, "effective_entity_field", occurrence_id, position, source_owner_type, source_owner_id),
                            effective_repo,
                            "effective_entity_field",
                            occurrence_id,
                            evidence.get("file_path"),
                            evidence.get("line_start"),
                            evidence.get("line_end"),
                            evidence.get("json_pointer"),
                            _json(evidence_payload),
                        ))
                    existing.add((effective_repo, effective_fqcn, field_name))
                    ordinal += 1

    _bulk_insert(
        con,
        "INSERT INTO effective_entity_field VALUES (" + ",".join("?" for _ in range(28)) + ")",
        table_rows,
    )
    _bulk_insert(con, "INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", evidence_rows)
    return len(table_rows)


def _rows_from_cursor(cursor: Any) -> list[dict[str, Any]]:
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _build_configuration_type_correspondences(con: duckdb.DuckDBPyConnection) -> int:
    """Materialize exact FQCN correspondences from configuration references to Java declarations.

    This is a facts-only technical correspondence. It does not classify publication,
    provider ownership, replica role, confidence, or semantic equivalence.
    """
    target_rows = con.execute(
        "SELECT fqcn, repo_id, java_type_occurrence_id "
        "FROM java_type_declaration "
        "WHERE fqcn IS NOT NULL AND trim(fqcn) <> '' "
        "ORDER BY fqcn, repo_id, java_type_occurrence_id"
    ).fetchall()
    targets: dict[str, list[tuple[str, str]]] = {}
    for fqcn, repo_id, occurrence_id in target_rows:
        targets.setdefault(str(fqcn), []).append((str(repo_id), str(occurrence_id)))

    rows: list[tuple[Any, ...]] = []
    source_rows = con.execute(
        """SELECT source_observation_occurrence_id, repo_id, configuration_path, referenced_type
           FROM source_observation
           WHERE fact_type='configuration_reference_observation'
             AND node_kind='java_type_reference'
             AND referenced_type IS NOT NULL
             AND trim(referenced_type) <> ''
           ORDER BY repo_id, occurrence_ordinal, source_observation_occurrence_id"""
    ).fetchall()
    for occurrence_id, source_repo_id, configuration_path, referenced_fqcn in source_rows:
        fqcn = str(referenced_fqcn).strip()
        for target_repo_id, target_occurrence_id in targets.get(fqcn, []):
            match_scope = "repository_local" if str(source_repo_id) == target_repo_id else "cross_repository"
            match_basis = "exact_fqcn"
            observation_id = stable_id(
                "configuration_type_correspondence",
                occurrence_id,
                fqcn,
                target_repo_id,
                target_occurrence_id,
            )
            payload = {
                "source_observation_occurrence_id": occurrence_id,
                "source_repo_id": source_repo_id,
                "configuration_path": configuration_path,
                "referenced_fqcn": fqcn,
                "target_repo_id": target_repo_id,
                "target_java_type_occurrence_id": target_occurrence_id,
                "match_scope": match_scope,
                "match_basis": match_basis,
            }
            rows.append((
                observation_id,
                occurrence_id,
                source_repo_id,
                configuration_path,
                fqcn,
                target_repo_id,
                target_occurrence_id,
                match_scope,
                match_basis,
                _json(payload),
            ))
    _bulk_insert(
        con,
        "INSERT INTO configuration_type_correspondence_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)



def _build_build_dependency_marts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Project source-observed build declarations into scope-neutral marts.

    The projection preserves the original source observation and payload. It does
    not resolve artifacts from repositories or infer module semantics.
    """
    fact_types = (
        "gradle_project_observation",
        "gradle_module_observation",
        "module_dependency_observation",
        "external_dependency",
        "gradle_plugin_observation",
        "gradle_repository_observation",
        "gradle_source_set_observation",
    )
    placeholders = ",".join("?" for _ in fact_types)
    rows = _rows_from_cursor(con.execute(
        f"SELECT source_observation_occurrence_id, repo_id, fact_type, name, payload_json "
        f"FROM source_observation WHERE fact_type IN ({placeholders}) "
        f"ORDER BY repo_id, fact_type, occurrence_ordinal, source_observation_occurrence_id",
        list(fact_types),
    ))
    projects: list[tuple[Any, ...]] = []
    modules: list[tuple[Any, ...]] = []
    dependencies: list[tuple[Any, ...]] = []
    plugins: list[tuple[Any, ...]] = []
    repositories: list[tuple[Any, ...]] = []
    source_sets: list[tuple[Any, ...]] = []
    seen_dependencies: set[tuple[str, str]] = set()
    for row in rows:
        payload = _json_value(row.get("payload_json")) or {}
        properties = payload.get("properties") if isinstance(payload, dict) else {}
        properties = properties if isinstance(properties, dict) else {}
        fact_type = str(row.get("fact_type") or "")
        occurrence_id = str(row.get("source_observation_occurrence_id") or "")
        repo_id = str(row.get("repo_id") or "")
        name = str(row.get("name") or "")
        if fact_type == "gradle_project_observation":
            projects.append((
                stable_id("build_project", repo_id, occurrence_id), repo_id,
                str(properties.get("root_project_name") or name),
                str(properties.get("build_system") or "gradle"),
                properties.get("root_directory"),
                _json(properties.get("module_paths") or []),
                occurrence_id, _json(payload),
            ))
        elif fact_type == "gradle_module_observation":
            modules.append((
                stable_id("build_module", repo_id, occurrence_id), repo_id,
                str(properties.get("module_path") or name),
                properties.get("module_name"), properties.get("project_directory"),
                properties.get("build_file"), str(properties.get("build_system") or "gradle"),
                bool(properties.get("declared_in_settings")),
                properties.get("evidence_maturity_level"), occurrence_id, _json(payload),
            ))
        elif fact_type in {"module_dependency_observation", "external_dependency"}:
            # Gradle external declarations have a parallel gradle-specific fact; the
            # generic external_dependency is the canonical mart input.
            key = (repo_id, occurrence_id)
            if key in seen_dependencies:
                continue
            seen_dependencies.add(key)
            dependencies.append((
                stable_id("build_dependency", repo_id, occurrence_id), repo_id,
                properties.get("source_module_path"), properties.get("target_module_path"),
                str(properties.get("dependency_kind") or ("module" if properties.get("target_module_path") else "external")),
                properties.get("configuration"), properties.get("scope"),
                properties.get("source_set"), bool(properties.get("is_test_source")),
                properties.get("group_id"), properties.get("artifact_id"),
                properties.get("version"), properties.get("coordinate"), properties.get("alias"),
                properties.get("resolution_basis"), properties.get("evidence_maturity_level"),
                occurrence_id, _json(payload),
            ))
        elif fact_type == "gradle_plugin_observation":
            plugins.append((
                stable_id("build_plugin", repo_id, occurrence_id), repo_id,
                properties.get("module_path"), str(properties.get("plugin_id") or name),
                properties.get("version"), properties.get("application_kind"),
                occurrence_id, _json(payload),
            ))
        elif fact_type == "gradle_repository_observation":
            repositories.append((
                stable_id("build_repository", repo_id, occurrence_id), repo_id,
                properties.get("module_path"), properties.get("repository_url_expression"),
                properties.get("repository_url"), properties.get("evidence_maturity_level"),
                occurrence_id, _json(payload),
            ))
        elif fact_type == "gradle_source_set_observation":
            source_sets.append((
                stable_id("build_source_set", repo_id, occurrence_id), repo_id,
                properties.get("module_path"), str(properties.get("source_set") or name),
                occurrence_id, _json(payload),
            ))
    _bulk_insert(con, "INSERT INTO build_project VALUES (?, ?, ?, ?, ?, ?, ?, ?)", projects)
    _bulk_insert(con, "INSERT INTO build_module VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", modules)
    _bulk_insert(con, "INSERT INTO build_dependency VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", dependencies)
    _bulk_insert(con, "INSERT INTO build_plugin VALUES (?, ?, ?, ?, ?, ?, ?, ?)", plugins)
    _bulk_insert(con, "INSERT INTO build_repository_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?)", repositories)
    _bulk_insert(con, "INSERT INTO build_source_set VALUES (?, ?, ?, ?, ?, ?)", source_sets)
    return {
        "projects": len(projects),
        "modules": len(modules),
        "dependencies": len(dependencies),
        "plugins": len(plugins),
        "repositories": len(repositories),
        "source_sets": len(source_sets),
    }
