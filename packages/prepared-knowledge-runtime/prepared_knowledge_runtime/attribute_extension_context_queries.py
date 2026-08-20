from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .query import KnowledgeLayerQuery

ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION = "data-model-attribute-extension-context/v1"
ATTRIBUTE_EXTENSION_CONTEXT_QUERY_SCHEMA_VERSION = "data-model-attribute-extension-query/v1"

_JOIN_JSON_FIELDS = {
    "concrete_targets_json": "concrete_targets",
    "source_reference_expressions_json": "source_reference_expressions",
    "target_key_fields_json": "target_key_fields",
    "target_key_expressions_json": "target_key_expressions",
    "source_parent_key_expressions_json": "source_parent_key_expressions",
    "child_key_expressions_json": "child_key_expressions",
    "structural_correspondences_json": "structural_correspondences",
    "source_sql_anchor_json": "source_sql_anchor",
    "target_sql_anchor_json": "target_sql_anchor",
    "observed_sql_join_examples_json": "observed_sql_join_examples",
    "physical_candidates_json": "physical_candidates",
    "basis_json": "basis",
    "provenance_json": "provenance",
    "diagnostics_json": "diagnostics",
}

_ANCHOR_JSON_FIELDS = {
    "storage_aliases_json": "storage_aliases",
    "storage_key_fields_json": "storage_key_fields",
    "storage_key_expressions_json": "storage_key_expressions",
    "observed_sql_relations_json": "observed_sql_relations",
    "observed_field_usages_json": "observed_field_usages",
    "observed_sql_projections_json": "observed_sql_projections",
    "observed_sql_joins_json": "observed_sql_joins",
    "physical_candidates_json": "physical_candidates",
    "basis_json": "basis",
    "provenance_json": "provenance",
}


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _normalize(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    item = dict(row)
    for source, target in mapping.items():
        default: Any = {} if target in {"source_sql_anchor", "target_sql_anchor", "basis", "provenance"} else []
        item[target] = _json_value(item.pop(source, None), default)
    return item


def _normalize_gap(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["details"] = _json_value(item.pop("details_json", None), {})
    return item


def list_attribute_extension_join_semantics(
    query: "KnowledgeLayerQuery",
    *,
    source_type: str | None = None,
    source_field: str | None = None,
    target_type: str | None = None,
    join_method: str | None = None,
    confidence: str | None = None,
    sql_generation_status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
    include_gaps: bool = True,
    max_gaps: int = 100,
) -> dict[str, Any]:
    """Read KLC-materialized agent-ready join semantics without adding inference.

    All relationship classification, key correspondence, physical candidate and SQL-anchor
    knowledge is produced by ``data-model-attribute-extension-context/v1``. This query only
    filters, decodes JSON payloads and returns related anchors/gaps.
    """
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    if max_gaps < 0 or max_gaps > 1000:
        raise ValueError("max_gaps must be between 0 and 1000")

    required = {
        "attribute_extension_context_build",
        "attribute_extension_join_semantic",
        "attribute_extension_object_anchor",
        "attribute_extension_context_gap",
    }
    missing = sorted(name for name in required if not query._has_relation(name))
    if missing:
        return {
            "schema_version": ATTRIBUTE_EXTENSION_CONTEXT_QUERY_SCHEMA_VERSION,
            "context_schema_version": ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION,
            "not_available": True,
            "missing_relations": missing,
            "filters": {},
            "items": [],
            "object_anchors": [],
            "gaps": [],
            "gap_count": 0,
            "gaps_truncated": False,
            "total_count": 0,
            "summary": {"by_join_method": {}, "by_confidence": {}, "by_sql_generation_status": {}},
        }

    clauses: list[str] = []
    params: list[Any] = []

    def exact(column: str, value: str | None) -> None:
        if value is None:
            return
        clauses.append(f"lower({column})=lower(?)")
        params.append(value)

    def exact_identity(columns: tuple[str, ...], value: str | None) -> None:
        if value is None:
            return
        clauses.append("(" + " OR ".join(f"lower({column})=lower(?)" for column in columns) + ")")
        params.extend([value] * len(columns))

    # Consumer hand-offs commonly carry stable occurrence/object identifiers from
    # declared/effective-model reads. Accept either those identifiers or the FQCN/name
    # stored beside them. This is identifier normalization only; it adds no inference.
    exact_identity(("source_fqcn", "source_type_occurrence_id"), source_type)
    exact_identity(("source_field", "source_field_occurrence_id"), source_field)
    exact_identity(("target_fqcn", "target_type_occurrence_id"), target_type)
    exact("join_method", join_method)
    exact("confidence", confidence)
    exact("sql_generation_status", sql_generation_status)
    normalized_search = (search or "").strip()
    if normalized_search:
        term = f"%{normalized_search}%"
        clauses.append(
            "(source_fqcn ILIKE ? OR source_field ILIKE ? OR target_fqcn ILIKE ? OR declared_type_expression ILIKE ?)"
        )
        params.extend([term, term, term, term])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    with query._connect() as con:
        build_rows = query._rows(con.execute("SELECT * FROM attribute_extension_context_build ORDER BY completed_at DESC LIMIT 1"))
        build = build_rows[0] if build_rows else {}
        if str(build.get("schema_version") or "") != ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION:
            raise ValueError(
                f"attribute-extension artifact schema mismatch: expected {ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION!r}"
            )
        if str(build.get("build_status") or "") != "complete":
            raise ValueError("attribute-extension context build is incomplete")

        total = int(con.execute("SELECT count(*) FROM attribute_extension_join_semantic" + where, params).fetchone()[0])
        rows = query._rows(
            con.execute(
                "SELECT * FROM attribute_extension_join_semantic"
                + where
                + " ORDER BY lower(source_fqcn), lower(source_field), lower(target_fqcn), join_semantic_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
        )
        method_counts = {
            str(key): int(count)
            for key, count in con.execute(
                "SELECT join_method,count(*) FROM attribute_extension_join_semantic" + where + " GROUP BY join_method ORDER BY join_method",
                params,
            ).fetchall()
        }
        confidence_counts = {
            str(key): int(count)
            for key, count in con.execute(
                "SELECT confidence,count(*) FROM attribute_extension_join_semantic" + where + " GROUP BY confidence ORDER BY confidence",
                params,
            ).fetchall()
        }
        sql_status_counts = {
            str(key): int(count)
            for key, count in con.execute(
                "SELECT sql_generation_status,count(*) FROM attribute_extension_join_semantic" + where + " GROUP BY sql_generation_status ORDER BY sql_generation_status",
                params,
            ).fetchall()
        }

        fqcn_values = sorted({
            str(value)
            for row in rows
            for value in (row.get("source_fqcn"), row.get("target_fqcn"))
            if value
        })
        anchor_rows: list[dict[str, Any]] = []
        if fqcn_values:
            placeholders = ",".join("?" for _ in fqcn_values)
            anchor_rows = query._rows(
                con.execute(
                    "SELECT * FROM attribute_extension_object_anchor "
                    f"WHERE logical_fully_qualified_name IN ({placeholders}) "
                    "ORDER BY lower(logical_fully_qualified_name), anchor_id",
                    fqcn_values,
                )
            )

        page_ids = [str(row.get("join_semantic_id") or "") for row in rows if row.get("join_semantic_id")]
        gap_rows: list[dict[str, Any]] = []
        gap_count = 0
        if include_gaps and page_ids:
            placeholders = ",".join("?" for _ in page_ids)
            gap_count = int(
                con.execute(
                    "SELECT count(*) FROM attribute_extension_context_gap "
                    f"WHERE owner_kind='join_semantic' AND owner_id IN ({placeholders})",
                    page_ids,
                ).fetchone()[0]
            )
            if max_gaps:
                gap_rows = query._rows(
                    con.execute(
                        "SELECT * FROM attribute_extension_context_gap "
                        f"WHERE owner_kind='join_semantic' AND owner_id IN ({placeholders}) "
                        "ORDER BY severity, gap_kind, gap_id LIMIT ?",
                        [*page_ids, max_gaps],
                    )
                )

    return {
        "schema_version": ATTRIBUTE_EXTENSION_CONTEXT_QUERY_SCHEMA_VERSION,
        "context_schema_version": ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION,
        "not_available": False,
        "filters": {
            "source_type": source_type,
            "source_field": source_field,
            "target_type": target_type,
            "join_method": join_method,
            "confidence": confidence,
            "sql_generation_status": sql_generation_status,
            "search": search,
        },
        "items": [_normalize(row, _JOIN_JSON_FIELDS) for row in rows],
        "object_anchors": [_normalize(row, _ANCHOR_JSON_FIELDS) for row in anchor_rows],
        "gaps": [_normalize_gap(row) for row in gap_rows],
        "gap_count": gap_count,
        "gaps_truncated": gap_count > len(gap_rows),
        "total_count": total,
        "summary": {
            "by_join_method": method_counts,
            "by_confidence": confidence_counts,
            "by_sql_generation_status": sql_status_counts,
        },
    }
