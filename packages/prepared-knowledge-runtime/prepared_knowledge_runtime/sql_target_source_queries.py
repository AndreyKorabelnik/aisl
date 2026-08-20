from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from .normalization import normalize_db_identifier

if TYPE_CHECKING:
    from .query import KnowledgeLayerQuery

SQL_TARGET_VALUE_SOURCE_QUERY_SCHEMA_VERSION = "sql-target-value-source-query/v1"


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _normalize_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["supporting_raw_mapping_ids"] = _json_value(item.pop("supporting_raw_mapping_ids_json", None), [])
    item["semantic_evidence"] = _json_value(item.pop("semantic_evidence_json", None), [])
    item["provenance"] = _json_value(item.pop("provenance_json", None), {})
    return item


def _normalize_gap(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["evidence"] = _json_value(item.pop("evidence_json", None), {})
    return item


def list_sql_target_value_sources(
    query: "KnowledgeLayerQuery",
    target_relation: str,
    *,
    target_column: str | None = None,
    repo_id: str | None = None,
    mapping_status: str | None = None,
    include_gaps: bool = True,
    max_gaps: int = 500,
    max_results: int = 100,
    page_token: str = "",
) -> dict[str, Any]:
    requested_relation = str(target_relation or "").strip()
    normalized_relation = normalize_db_identifier(requested_relation)
    logical_target = normalized_relation.split(".")[-1] if normalized_relation else ""
    if not logical_target:
        raise ValueError("target_relation must not be empty")
    column = str(target_column or "").strip() or None
    if target_column is not None and column is None:
        raise ValueError("target_column must not be empty when provided")
    if max_gaps < 1:
        raise ValueError("max_gaps must be >= 1")

    filters = {
        "target_relation": requested_relation,
        "workflow_target_logical_name": logical_target,
        "target_column": column,
        "repo_id": repo_id,
        "mapping_status": mapping_status,
        "include_gaps": bool(include_gaps),
    }
    if not query._has_relation("sql_target_value_source_mapping"):
        result = query._empty_page(
            kind="knowledge-layer-sql-target-value-sources",
            query_id="sql_target_value_sources",
            filters=filters,
            max_results=max_results,
            page_token=page_token,
        )
        result.update({
            "schema_version": SQL_TARGET_VALUE_SOURCE_QUERY_SCHEMA_VERSION,
            "not_available": True,
            "summary": {"value_mapping_count": 0, "target_column_count": 0, "source_relation_count": 0, "by_mapping_status": {}, "by_normalization_kind": {}},
            "gaps": [], "gap_count": 0, "gaps_truncated": False, "gaps_by_kind": {},
        })
        return result

    clauses = ["lower(workflow_target_logical_name)=?"]
    args: list[Any] = [logical_target.casefold()]
    if column is not None:
        clauses.append("lower(target_column)=?")
        args.append(column.casefold())
    if repo_id:
        clauses.append("repo_id=?")
        args.append(str(repo_id))
    if mapping_status:
        clauses.append("mapping_status=?")
        args.append(str(mapping_status))
    where = " AND ".join(clauses)
    query_id = "sql_target_value_sources"
    page_size = query._normalize_page_size(max_results)
    offset = query._decode_page_token(page_token, query_id=query_id, filters=filters)

    with query._connect() as con:
        total_count = int(con.execute(f"SELECT count(*) FROM sql_target_value_source_mapping WHERE {where}", args).fetchone()[0])
        rows = query._rows(con.execute(
            "SELECT * FROM sql_target_value_source_mapping WHERE " + where +
            " ORDER BY lower(target_column), target_column, lower(coalesce(source_sql_relation_name,'')), source_sql_relation_name, "
            "lower(coalesce(source_sql_column,'')), source_sql_column, value_mapping_id LIMIT ? OFFSET ?",
            [*args, page_size, offset],
        ))
        target_column_count = int(con.execute(
            f"SELECT count(DISTINCT lower(target_column)) FROM sql_target_value_source_mapping WHERE {where}", args
        ).fetchone()[0])
        source_relation_count = int(con.execute(
            f"SELECT count(DISTINCT lower(coalesce(source_sql_relation_name,''))) FROM sql_target_value_source_mapping WHERE {where}", args
        ).fetchone()[0])
        status_rows = con.execute(
            f"SELECT mapping_status,count(*) FROM sql_target_value_source_mapping WHERE {where} GROUP BY mapping_status ORDER BY mapping_status", args
        ).fetchall()
        norm_rows = con.execute(
            f"SELECT normalization_kind,count(*) FROM sql_target_value_source_mapping WHERE {where} GROUP BY normalization_kind ORDER BY normalization_kind", args
        ).fetchall()

        gaps: list[dict[str, Any]] = []
        gap_count = 0
        gap_kind_rows: list[tuple[Any, Any]] = []
        if include_gaps and query._has_relation("sql_target_source_mapping_gap"):
            gap_clauses = ["lower(workflow_target_logical_name)=?"]
            gap_args: list[Any] = [logical_target.casefold()]
            if column is not None:
                gap_clauses.append("lower(coalesce(target_column,''))=?")
                gap_args.append(column.casefold())
            if repo_id:
                gap_clauses.append("repo_id=?")
                gap_args.append(str(repo_id))
            gap_where = " AND ".join(gap_clauses)
            gap_count = int(con.execute(f"SELECT count(*) FROM sql_target_source_mapping_gap WHERE {gap_where}", gap_args).fetchone()[0])
            gaps = [_normalize_gap(row) for row in query._rows(con.execute(
                "SELECT * FROM sql_target_source_mapping_gap WHERE " + gap_where +
                " ORDER BY lower(coalesce(target_column,'')), target_column, gap_kind, gap_id LIMIT ?",
                [*gap_args, int(max_gaps)],
            ))]
            gap_kind_rows = con.execute(
                f"SELECT gap_kind,count(*) FROM sql_target_source_mapping_gap WHERE {gap_where} GROUP BY gap_kind ORDER BY gap_kind", gap_args
            ).fetchall()

    items = [_normalize_item(row) for row in rows]
    page = query._page_result(
        kind="knowledge-layer-sql-target-value-sources",
        query_id=query_id,
        filters=filters,
        items=items,
        total_count=total_count,
        offset=offset,
        page_size=page_size,
    )
    page.update({
        "schema_version": SQL_TARGET_VALUE_SOURCE_QUERY_SCHEMA_VERSION,
        "not_available": False,
        "summary": {
            "value_mapping_count": total_count,
            "target_column_count": target_column_count,
            "source_relation_count": source_relation_count,
            "by_mapping_status": {str(k or "unknown"): int(v) for k, v in status_rows},
            "by_normalization_kind": {str(k or "unknown"): int(v) for k, v in norm_rows},
        },
        "gaps": gaps,
        "gap_count": gap_count,
        "gaps_truncated": len(gaps) < gap_count,
        "gaps_by_kind": {str(k or "unknown"): int(v) for k, v in gap_kind_rows},
    })
    return page
