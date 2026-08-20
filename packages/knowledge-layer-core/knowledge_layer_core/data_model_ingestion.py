from __future__ import annotations

"""Common deterministic ingestion for conceptual and Java effective-model inventory.

The loaders in this module operate on repository-scoped rows and are valid for both
single-repository and multi-repository knowledge-layer builds. They publish facts and
mechanical projections only; workspace correspondence and framework interpretation
remain outside the core.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from .bulk import bulk_insert as _bulk_insert
from prepared_knowledge_runtime.normalization import (
    normalize_db_identifier,
    normalize_text,
    stable_id,
)

try:
    import duckdb
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    duckdb = None

_EXCLUDED_DATA_MODEL_SOURCE_SETS = {
    "test",
    "test_code",
    "fixture",
    "example",
    "example_sample",
    "sample",
    "documentation",
}

def _included_static_data_model_record(item: dict[str, Any] | None) -> bool:
    """Return whether a raw static fact belongs in the production data-model projection.

    Raw source records are always preserved separately.  This predicate controls
    only materialization into the data-model tables.  When a scanner merged
    multiple source occurrences, one production occurrence is sufficient to keep
    the fact; no test occurrence is allowed to suppress production evidence.
    """
    item = item or {}

    def included_single(source: dict[str, Any]) -> bool:
        source_set = str(source.get("source_set") or source.get("source_scope") or "").strip().lower()
        if source_set in _EXCLUDED_DATA_MODEL_SOURCE_SETS:
            return False
        if bool(source.get("is_test_source")):
            return False
        return True

    occurrences = [x for x in item.get("source_occurrences") or [] if isinstance(x, dict)]
    if occurrences:
        return any(included_single(x) for x in occurrences)
    return included_single(item)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL record in {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record must be an object in {path}:{line_number}")
            yield value


def _local_id(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _string(item: dict[str, Any], *keys: str) -> str | None:
    return _local_id(item, *keys)


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _evidence_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("evidence_refs")
    if raw is None:
        raw = item.get("evidence")
    if not isinstance(raw, list):
        return []
    return [value for value in raw if isinstance(value, dict)]


def _insert_evidence_refs(
    con: duckdb.DuckDBPyConnection,
    *,
    repo_id: str,
    owner_type: str,
    owner_occurrence_id: str,
    item: dict[str, Any],
) -> int:
    rows: list[tuple[Any, ...]] = []
    for position, evidence in enumerate(_evidence_items(item)):
        file_path = _string(evidence, "file_path", "file", "relative_file", "path")
        line_start = _int(evidence.get("line_start") or evidence.get("line"))
        line_end = _int(evidence.get("line_end"))
        json_pointer = _string(evidence, "json_pointer", "pointer")
        ref_id = stable_id(
            "ev",
            repo_id,
            owner_type,
            owner_occurrence_id,
            position,
            file_path,
            line_start,
            line_end,
            json_pointer,
            _json(evidence),
        )
        rows.append(
            (
                ref_id,
                repo_id,
                owner_type,
                owner_occurrence_id,
                file_path,
                line_start,
                line_end,
                json_pointer,
                _json(evidence),
            )
        )
    if rows:
        con.executemany("INSERT INTO evidence_ref VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def _record_id(repo_id: str, section: str, item: dict[str, Any], ordinal: int) -> tuple[str, str | None]:
    local = _local_id(
        item,
        "domain_id",
        "cluster_id",
        "entity_id",
        "association_id",
        "generalization_id",
        "asset_id",
        "mapping_id",
        "declared_value_set_id",
        "java_type_declaration_id",
        "java_inheritance_observation_id",
        "effective_entity_field_id",
        "effective_entity_association_id",
        "fact_id",
        "gap_id",
        "request_id",
        "persistent_structure_id",
        "db_schema_table_id",
        "db_schema_column_id",
        "db_schema_key_id",
        "db_schema_relationship_id",
        "db_schema_constraint_id",
        "db_schema_index_id",
        "db_schema_partitioning_id",
        "db_schema_sequence_id",
        "db_schema_trigger_id",
        "observation_id",
        "id",
    )
    identity = local or hashlib.sha256(_json(item).encode("utf-8")).hexdigest()
    return stable_id("record", repo_id, section, identity, ordinal), local


def _source_record(
    con: duckdb.DuckDBPyConnection,
    repo_id: str,
    section: str,
    item: dict[str, Any],
    ordinal: int,
) -> tuple[str, str | None]:
    record_id, local_id = _record_id(repo_id, section, item, ordinal)
    con.execute(
        "INSERT INTO source_record VALUES (?, ?, ?, ?, ?, ?)",
        [record_id, repo_id, section, local_id, ordinal, _json(item)],
    )
    return record_id, local_id


def _occurrence_candidates(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str,
    repo_id: str,
    local_column: str,
    local_id: str | None,
    occurrence_column: str,
) -> list[str]:
    if not local_id:
        return []
    return [
        row[0]
        for row in con.execute(
            f"SELECT {occurrence_column} FROM {table} WHERE repo_id=? AND {local_column}=? ORDER BY occurrence_ordinal, {occurrence_column}",
            [repo_id, local_id],
        ).fetchall()
    ]


def _single(candidates: list[str]) -> str | None:
    return candidates[0] if len(candidates) == 1 else None


def _source_record_values(repo_id: str, section: str, item: dict[str, Any], ordinal: int) -> tuple[str, str | None, tuple[Any, ...]]:
    record_id, local_id = _record_id(repo_id, section, item, ordinal)
    return record_id, local_id, (record_id, repo_id, section, local_id, ordinal, _json(item))


def _evidence_ref_rows(repo_id: str, owner_type: str, owner_occurrence_id: str, item: dict[str, Any]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for position, evidence in enumerate(_evidence_items(item)):
        file_path = _string(evidence, "file_path", "file", "relative_file", "path")
        line_start = _int(evidence.get("line_start") or evidence.get("line"))
        line_end = _int(evidence.get("line_end"))
        json_pointer = _string(evidence, "json_pointer", "pointer")
        ref_id = stable_id("ev", repo_id, owner_type, owner_occurrence_id, position, file_path, line_start, line_end, json_pointer, _json(evidence))
        rows.append((ref_id, repo_id, owner_type, owner_occurrence_id, file_path, line_start, line_end, json_pointer, _json(evidence)))
    return rows


def _first_evidence_location(item: dict[str, Any]) -> tuple[str | None, int | None, int | None, str | None]:
    evidence = _evidence_items(item)
    first = evidence[0] if evidence else {}
    return (
        _string(first, "file_path", "file", "relative_file", "path"),
        _int(first.get("line_start") or first.get("line")),
        _int(first.get("line_end")),
        _string(first, "extractor"),
    )
