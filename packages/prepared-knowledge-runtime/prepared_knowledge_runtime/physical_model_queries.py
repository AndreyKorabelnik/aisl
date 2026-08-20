from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .query import KnowledgeLayerQuery

PHYSICAL_MODEL_QUERY_SCHEMA_VERSION = "physical-model-query/v1"


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _normalize_table(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["package_path"] = _json_value(item.pop("package_path_json", None), [])
    item["package_code_path"] = _json_value(item.pop("package_code_path_json", None), [])
    item["evidence"] = _json_value(item.pop("evidence_json", None), {})
    item.pop("payload_json", None)
    return item


def _normalize_column(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["evidence"] = _json_value(item.pop("evidence_json", None), {})
    item.pop("payload_json", None)
    return item


def _normalize_key(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["column_pdm_ids"] = _json_value(item.pop("column_pdm_ids_json", None), [])
    item["column_codes"] = _json_value(item.pop("column_codes_json", None), [])
    item["unresolved_column_refs"] = _json_value(item.pop("unresolved_column_refs_json", None), [])
    item["evidence"] = _json_value(item.pop("evidence_json", None), {})
    item.pop("payload_json", None)
    return item


def _normalize_relationship(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["joins"] = _json_value(item.pop("joins_json", None), [])
    item["evidence"] = _json_value(item.pop("evidence_json", None), {})
    item.pop("payload_json", None)
    return item


def _normalize_gap(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("payload_json", None)
    return item


def physical_model_summary(query: "KnowledgeLayerQuery") -> dict[str, Any]:
    if not query._has_relation("physical_model_source"):
        return {
            "schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION,
            "not_available": True,
            "sources": [],
            "counts": {"tables": 0, "columns": 0, "keys": 0, "relationships": 0, "gaps": 0},
            "relationship_resolution": {},
            "key_kinds": {},
            "gap_kinds": {},
        }
    with query._connect() as con:
        sources = query._rows(con.execute("SELECT * FROM physical_model_source ORDER BY physical_model_source_id"))
        counts = {
            "tables": int(con.execute("SELECT count(*) FROM physical_model_table").fetchone()[0]),
            "columns": int(con.execute("SELECT count(*) FROM physical_model_column").fetchone()[0]),
            "keys": int(con.execute("SELECT count(*) FROM physical_model_key").fetchone()[0]),
            "relationships": int(con.execute("SELECT count(*) FROM physical_model_relationship").fetchone()[0]),
            "gaps": int(con.execute("SELECT count(*) FROM physical_model_gap").fetchone()[0]),
        }
        relationship_resolution = {
            str(kind or "unknown"): int(count)
            for kind, count in con.execute(
                "SELECT resolution_status, count(*) FROM physical_model_relationship GROUP BY resolution_status ORDER BY resolution_status"
            ).fetchall()
        }
        key_kinds = {
            str(kind or "unknown"): int(count)
            for kind, count in con.execute(
                "SELECT key_kind, count(*) FROM physical_model_key GROUP BY key_kind ORDER BY key_kind"
            ).fetchall()
        }
        gap_kinds = {
            str(kind or "unknown"): int(count)
            for kind, count in con.execute(
                "SELECT gap_kind, count(*) FROM physical_model_gap GROUP BY gap_kind ORDER BY gap_kind"
            ).fetchall()
        }
    normalized_sources: list[dict[str, Any]] = []
    for row in sources:
        item = dict(row)
        item["metadata"] = _json_value(item.pop("metadata_json", None), {})
        item.pop("manifest_json", None)
        normalized_sources.append(item)
    return {
        "schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION,
        "not_available": False,
        "sources": normalized_sources,
        "counts": counts,
        "relationship_resolution": relationship_resolution,
        "key_kinds": key_kinds,
        "gap_kinds": gap_kinds,
    }


def list_physical_model_tables(
    query: "KnowledgeLayerQuery",
    *,
    source_id: str | None = None,
    search: str = "",
    include_columns: bool = False,
    max_results: int = 100,
    page_token: str = "",
) -> dict[str, Any]:
    filters = {"source_id": source_id, "search": search, "include_columns": bool(include_columns)}
    query_id = "physical_model_tables"
    if not query._has_relation("physical_model_table"):
        result = query._empty_page(
            kind="knowledge-layer-physical-model-tables", query_id=query_id, filters=filters,
            max_results=max_results, page_token=page_token,
        )
        result.update({"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": True})
        return result
    clauses = ["1=1"]
    args: list[Any] = []
    if source_id:
        clauses.append("t.physical_model_source_id=?")
        args.append(source_id)
    if search:
        clauses.append(
            "(lower(coalesce(t.table_code,'') || ' ' || coalesce(t.table_name,'') || ' ' || "
            "coalesce(t.logical_identity,'') || ' ' || cast(coalesce(t.package_code_path_json,'[]') AS VARCHAR)) LIKE ? "
            "OR EXISTS (SELECT 1 FROM physical_model_column c WHERE c.physical_model_table_id=t.physical_model_table_id "
            "AND lower(coalesce(c.column_code,'') || ' ' || coalesce(c.column_name,'')) LIKE ?))"
        )
        token = f"%{search.casefold()}%"
        args.extend([token, token])
    where = " AND ".join(clauses)
    page_size = query._normalize_page_size(max_results)
    offset = query._decode_page_token(page_token, query_id=query_id, filters=filters)
    select_sql = f"""
        SELECT t.*,
               (SELECT count(*) FROM physical_model_relationship r WHERE r.parent_table_id=t.physical_model_table_id) AS outbound_relationship_count,
               (SELECT count(*) FROM physical_model_relationship r WHERE r.child_table_id=t.physical_model_table_id) AS inbound_relationship_count
        FROM physical_model_table t
        WHERE {where}
        ORDER BY lower(coalesce(t.table_code,'')), t.table_code, t.physical_model_table_id
    """
    with query._connect() as con:
        total_count = int(con.execute(f"SELECT count(*) FROM physical_model_table t WHERE {where}", args).fetchone()[0])
        rows = query._rows(con.execute(select_sql + " LIMIT ? OFFSET ?", [*args, page_size, offset]))
        items = [_normalize_table(row) for row in rows]
        if include_columns and items:
            table_ids = [str(item["physical_model_table_id"]) for item in items]
            placeholders = ",".join("?" for _ in table_ids)
            column_rows = query._rows(con.execute(
                f"SELECT * FROM physical_model_column WHERE physical_model_table_id IN ({placeholders}) "
                "ORDER BY physical_model_table_id, ordinal, lower(coalesce(column_code,'')), physical_model_column_id",
                table_ids,
            ))
            grouped: dict[str, list[dict[str, Any]]] = {table_id: [] for table_id in table_ids}
            for row in column_rows:
                grouped[str(row["physical_model_table_id"])].append(_normalize_column(row))
            for item in items:
                item["columns"] = grouped.get(str(item["physical_model_table_id"]), [])
    result = query._page_result(
        kind="knowledge-layer-physical-model-tables", query_id=query_id, filters=filters,
        items=items, total_count=total_count, offset=offset, page_size=page_size,
    )
    result.update({"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": False})
    return result


def get_physical_model_table(query: "KnowledgeLayerQuery", table_id: str) -> dict[str, Any]:
    if not query._has_relation("physical_model_table"):
        return {"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": True, "not_found": True}
    with query._connect() as con:
        rows = query._rows(con.execute(
            "SELECT t.*, "
            "(SELECT count(*) FROM physical_model_relationship r WHERE r.parent_table_id=t.physical_model_table_id) AS outbound_relationship_count, "
            "(SELECT count(*) FROM physical_model_relationship r WHERE r.child_table_id=t.physical_model_table_id) AS inbound_relationship_count "
            "FROM physical_model_table t WHERE t.physical_model_table_id=?",
            [table_id],
        ))
        if not rows:
            return {"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": False, "not_found": True}
        columns = [_normalize_column(row) for row in query._rows(con.execute(
            "SELECT * FROM physical_model_column WHERE physical_model_table_id=? "
            "ORDER BY ordinal, lower(coalesce(column_code,'')), physical_model_column_id",
            [table_id],
        ))]
        keys = [_normalize_key(row) for row in query._rows(con.execute(
            "SELECT * FROM physical_model_key WHERE physical_model_table_id=? "
            "ORDER BY CASE WHEN key_kind='primary' THEN 0 ELSE 1 END, lower(coalesce(key_code,'')), physical_model_key_id",
            [table_id],
        ))]
        relationships = [_normalize_relationship(row) for row in query._rows(con.execute(
            "SELECT r.*, pt.table_name AS parent_table_name, ct.table_name AS child_table_name "
            "FROM physical_model_relationship r "
            "LEFT JOIN physical_model_table pt ON pt.physical_model_table_id=r.parent_table_id "
            "LEFT JOIN physical_model_table ct ON ct.physical_model_table_id=r.child_table_id "
            "WHERE r.parent_table_id=? OR r.child_table_id=? "
            "ORDER BY lower(coalesce(r.relationship_code,'')), r.physical_model_relationship_id",
            [table_id, table_id],
        ))]
    return {
        "schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION,
        "not_available": False,
        "not_found": False,
        "table": _normalize_table(rows[0]),
        "columns": columns,
        "keys": keys,
        "relationships": relationships,
    }


def _paged_fact_query(
    query: "KnowledgeLayerQuery",
    *,
    table_name: str,
    kind: str,
    query_id: str,
    filters: dict[str, Any],
    where: str,
    args: list[Any],
    order_by: str,
    max_results: int,
    page_token: str,
    select_sql: str | None = None,
    normalizer,
) -> dict[str, Any]:
    if not query._has_relation(table_name):
        result = query._empty_page(
            kind=kind, query_id=query_id, filters=filters, max_results=max_results, page_token=page_token
        )
        result.update({"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": True})
        return result
    page_size = query._normalize_page_size(max_results)
    offset = query._decode_page_token(page_token, query_id=query_id, filters=filters)
    base_select = select_sql or f"SELECT x.* FROM {table_name} x"
    with query._connect() as con:
        total_count = int(con.execute(f"SELECT count(*) FROM {table_name} x WHERE {where}", args).fetchone()[0])
        rows = query._rows(con.execute(
            f"{base_select} WHERE {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*args, page_size, offset],
        ))
    result = query._page_result(
        kind=kind, query_id=query_id, filters=filters, items=[normalizer(row) for row in rows],
        total_count=total_count, offset=offset, page_size=page_size,
    )
    result.update({"schema_version": PHYSICAL_MODEL_QUERY_SCHEMA_VERSION, "not_available": False})
    return result


def list_physical_model_columns(
    query: "KnowledgeLayerQuery", *, table_id: str | None = None, source_id: str | None = None,
    search: str = "", data_type: str | None = None, mandatory: bool | None = None,
    max_results: int = 100, page_token: str = "",
) -> dict[str, Any]:
    filters = {"table_id": table_id, "source_id": source_id, "search": search, "data_type": data_type, "mandatory": mandatory}
    clauses = ["1=1"]
    args: list[Any] = []
    if table_id:
        clauses.append("x.physical_model_table_id=?"); args.append(table_id)
    if source_id:
        clauses.append("x.physical_model_source_id=?"); args.append(source_id)
    if search:
        clauses.append("lower(coalesce(x.column_code,'') || ' ' || coalesce(x.column_name,'')) LIKE ?"); args.append(f"%{search.casefold()}%")
    if data_type:
        clauses.append("lower(coalesce(x.data_type,''))=lower(?)"); args.append(data_type)
    if mandatory is not None:
        clauses.append("x.mandatory=?"); args.append(bool(mandatory))
    return _paged_fact_query(
        query, table_name="physical_model_column", kind="knowledge-layer-physical-model-columns",
        query_id="physical_model_columns", filters=filters, where=" AND ".join(clauses), args=args,
        order_by="x.physical_model_table_id, x.ordinal, lower(coalesce(x.column_code,'')), x.physical_model_column_id",
        max_results=max_results, page_token=page_token, normalizer=_normalize_column,
    )


def list_physical_model_keys(
    query: "KnowledgeLayerQuery", *, table_id: str | None = None, source_id: str | None = None,
    key_kind: str | None = None, search: str = "", max_results: int = 100, page_token: str = "",
) -> dict[str, Any]:
    filters = {"table_id": table_id, "source_id": source_id, "key_kind": key_kind, "search": search}
    clauses = ["1=1"]
    args: list[Any] = []
    if table_id:
        clauses.append("x.physical_model_table_id=?"); args.append(table_id)
    if source_id:
        clauses.append("x.physical_model_source_id=?"); args.append(source_id)
    if key_kind:
        clauses.append("x.key_kind=?"); args.append(key_kind)
    if search:
        clauses.append("lower(coalesce(x.key_code,'') || ' ' || coalesce(x.key_name,'') || ' ' || cast(coalesce(x.column_codes_json,'[]') AS VARCHAR)) LIKE ?")
        args.append(f"%{search.casefold()}%")
    return _paged_fact_query(
        query, table_name="physical_model_key", kind="knowledge-layer-physical-model-keys",
        query_id="physical_model_keys", filters=filters, where=" AND ".join(clauses), args=args,
        order_by="x.physical_model_table_id, CASE WHEN x.key_kind='primary' THEN 0 ELSE 1 END, lower(coalesce(x.key_code,'')), x.physical_model_key_id",
        max_results=max_results, page_token=page_token, normalizer=_normalize_key,
    )


def list_physical_model_relationships(
    query: "KnowledgeLayerQuery", *, table_id: str | None = None, direction: str = "any",
    source_id: str | None = None, resolution_status: str | None = None, search: str = "",
    max_results: int = 100, page_token: str = "",
) -> dict[str, Any]:
    if direction not in {"any", "parent", "child"}:
        raise ValueError("direction must be one of: any, parent, child")
    filters = {"table_id": table_id, "direction": direction, "source_id": source_id, "resolution_status": resolution_status, "search": search}
    clauses = ["1=1"]
    args: list[Any] = []
    if table_id:
        if direction == "parent": clauses.append("x.parent_table_id=?"); args.append(table_id)
        elif direction == "child": clauses.append("x.child_table_id=?"); args.append(table_id)
        else: clauses.append("(x.parent_table_id=? OR x.child_table_id=?)"); args.extend([table_id, table_id])
    if source_id:
        clauses.append("x.physical_model_source_id=?"); args.append(source_id)
    if resolution_status:
        clauses.append("x.resolution_status=?"); args.append(resolution_status)
    if search:
        clauses.append("lower(coalesce(x.relationship_code,'') || ' ' || coalesce(x.relationship_name,'') || ' ' || coalesce(x.parent_table_code,'') || ' ' || coalesce(x.child_table_code,'')) LIKE ?")
        args.append(f"%{search.casefold()}%")
    select_sql = (
        "SELECT x.*, pt.table_name AS parent_table_name, ct.table_name AS child_table_name "
        "FROM physical_model_relationship x "
        "LEFT JOIN physical_model_table pt ON pt.physical_model_table_id=x.parent_table_id "
        "LEFT JOIN physical_model_table ct ON ct.physical_model_table_id=x.child_table_id"
    )
    return _paged_fact_query(
        query, table_name="physical_model_relationship", kind="knowledge-layer-physical-model-relationships",
        query_id="physical_model_relationships", filters=filters, where=" AND ".join(clauses), args=args,
        order_by="lower(coalesce(x.relationship_code,'')), x.physical_model_relationship_id",
        max_results=max_results, page_token=page_token, select_sql=select_sql, normalizer=_normalize_relationship,
    )


def list_physical_model_gaps(
    query: "KnowledgeLayerQuery", *, source_id: str | None = None, gap_kind: str | None = None,
    search: str = "", max_results: int = 100, page_token: str = "",
) -> dict[str, Any]:
    filters = {"source_id": source_id, "gap_kind": gap_kind, "search": search}
    clauses = ["1=1"]
    args: list[Any] = []
    if source_id:
        clauses.append("x.physical_model_source_id=?"); args.append(source_id)
    if gap_kind:
        clauses.append("x.gap_kind=?"); args.append(gap_kind)
    if search:
        clauses.append("lower(coalesce(x.message,'') || ' ' || coalesce(x.unresolved_ref,'') || ' ' || coalesce(x.owner_pdm_object_id,'')) LIKE ?")
        args.append(f"%{search.casefold()}%")
    return _paged_fact_query(
        query, table_name="physical_model_gap", kind="knowledge-layer-physical-model-gaps",
        query_id="physical_model_gaps", filters=filters, where=" AND ".join(clauses), args=args,
        order_by="x.gap_kind, x.physical_model_gap_id", max_results=max_results, page_token=page_token,
        normalizer=_normalize_gap,
    )
