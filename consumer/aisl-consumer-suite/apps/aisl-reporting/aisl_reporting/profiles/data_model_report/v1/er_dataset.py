from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any, Callable, Iterable, Mapping


ER_RELATIONSHIP_LIMIT = 30
ER_NODE_LIMIT = 60
PHYSICAL_ATTRIBUTE_LIMIT = 12
LOGICAL_ATTRIBUTE_LIMIT = 10


def _text(value: Any) -> str:
    return str(value or "").strip()


def _texts(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values or ():
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def collect_pages(
    method: Callable[..., Mapping[str, Any]],
    *,
    max_items: int = 5000,
    page_size: int = 500,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Collect a bounded public KLC query without relying on relation layouts."""
    items: list[dict[str, Any]] = []
    token = ""
    total = 0
    while len(items) < max_items:
        page = method(
            max_results=min(page_size, max_items - len(items)),
            page_token=token,
            **kwargs,
        )
        total = int(page.get("total_count") or 0)
        items.extend(dict(item) for item in (page.get("items") or ()))
        token = _text(page.get("next_token"))
        if not token:
            break
    return items, total, bool(token) or len(items) < total


def _round_robin(
    items: Iterable[Mapping[str, Any]],
    *,
    limit: int,
    group_key: Callable[[Mapping[str, Any]], str],
    sort_key: Callable[[Mapping[str, Any]], tuple[Any, ...]],
) -> list[dict[str, Any]]:
    groups: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for item in sorted((dict(value) for value in items), key=sort_key):
        groups[group_key(item)].append(item)
    result: list[dict[str, Any]] = []
    ordered_groups = sorted(groups)
    while len(result) < limit and ordered_groups:
        remaining: list[str] = []
        for group in ordered_groups:
            queue = groups[group]
            if queue and len(result) < limit:
                result.append(queue.popleft())
            if queue:
                remaining.append(group)
        ordered_groups = remaining
    return result


def _logical_domain(name: str, inventory_by_fqcn: Mapping[str, Mapping[str, Any]]) -> str:
    item = inventory_by_fqcn.get(name) or {}
    package_name = _text(item.get("package_name"))
    if package_name:
        return package_name
    if "." in name:
        return name.rsplit(".", 1)[0]
    return "(без пакета)"


def _physical_domain(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else "(без схемы)"


def _relationship_source(relation: Mapping[str, Any]) -> str:
    source = relation.get("source") if isinstance(relation.get("source"), Mapping) else {}
    return _text(source.get("object_fqcn"))


def _relationship_target(relation: Mapping[str, Any]) -> str:
    target = relation.get("target") if isinstance(relation.get("target"), Mapping) else {}
    return _text(target.get("type_fqcn"))


def _logical_edge(relation: Mapping[str, Any]) -> dict[str, Any] | None:
    source = relation.get("source") if isinstance(relation.get("source"), Mapping) else {}
    target = relation.get("target") if isinstance(relation.get("target"), Mapping) else {}
    source_name = _text(source.get("object_fqcn"))
    target_name = _text(target.get("type_fqcn"))
    if not source_name or not target_name:
        return None
    return {
        "relationship_id": relation.get("relationship_id"),
        "from": source_name,
        "to": target_name,
        "field": source.get("field"),
        "relation_kind": relation.get("relationship_kind"),
        "cardinality": source.get("cardinality"),
        "inherited": bool(source.get("inherited")),
        "polymorphic_targets": _texts(relation.get("polymorphic_targets") or ()),
        "evidence_ids": _texts(relation.get("evidence_ids") or ()),
        "basis": "logical_relationship_evidence",
    }


def _logical_node(
    item: Mapping[str, Any],
    bundle_by_fqcn: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fqcn = _text(item.get("fqcn"))
    bundle = bundle_by_fqcn.get(fqcn) or {}
    fields = [dict(value) for value in (bundle.get("fields") or ()) if isinstance(value, Mapping)]
    key_fields: set[str] = set()
    keys: list[dict[str, Any]] = []
    for raw_key in bundle.get("keys") or ():
        if not isinstance(raw_key, Mapping):
            continue
        members: list[str] = []
        for raw_member in raw_key.get("members") or ():
            if isinstance(raw_member, Mapping):
                member = _text(raw_member.get("field_name") or raw_member.get("name"))
            else:
                member = _text(raw_member)
            if member:
                members.append(member)
                key_fields.add(member)
        keys.append({
            "key_id": raw_key.get("key_id"),
            "annotation_name": raw_key.get("annotation_name"),
            "members": members,
        })
    attributes = []
    for field in fields[:LOGICAL_ATTRIBUTE_LIMIT]:
        name = _text(field.get("name") or field.get("field_name"))
        attributes.append({
            "name": name,
            "type": field.get("effective_type") or field.get("declared_type") or field.get("type"),
            "inherited": bool(field.get("inherited")),
            "container_kind": field.get("container_kind"),
            "key": name in key_fields,
            "evidence_ids": _texts(field.get("evidence_ids") or ()),
        })
    return {
        "entity_id": item.get("object_id"),
        "repo_id": item.get("repo_id"),
        "name": item.get("name") or (fqcn.rsplit(".", 1)[-1] if fqcn else None),
        "qualified_name": fqcn,
        "package_name": item.get("package_name"),
        "object_kind": item.get("object_kind"),
        "display_name": item.get("display_name"),
        "description": item.get("description"),
        "direct_field_count": int(item.get("direct_field_count") or 0),
        "attributes": attributes,
        "attribute_count": len(fields) if fields else int(item.get("direct_field_count") or 0),
        "attributes_truncated": len(fields) > LOGICAL_ATTRIBUTE_LIMIT,
        "keys": keys[:5],
        "evidence_ids": _texts(item.get("evidence_ids") or ()),
    }


def build_logical_er(
    inventory_items: Iterable[Mapping[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
    selected_bundles: Iterable[Mapping[str, Any]],
    *,
    relationship_limit: int = ER_RELATIONSHIP_LIMIT,
    node_limit: int = ER_NODE_LIMIT,
) -> dict[str, Any]:
    inventory = [dict(item) for item in inventory_items]
    inventory_by_fqcn = {_text(item.get("fqcn")): item for item in inventory if _text(item.get("fqcn"))}
    bundle_by_fqcn: dict[str, Mapping[str, Any]] = {}
    for bundle in selected_bundles:
        obj = bundle.get("object") if isinstance(bundle.get("object"), Mapping) else {}
        fqcn = _text(obj.get("fqcn"))
        if fqcn:
            bundle_by_fqcn[fqcn] = bundle

    normalized = [dict(item) for item in relationships]
    normalized = [item for item in normalized if _relationship_source(item) and _relationship_target(item)]
    normalized.sort(key=lambda item: (
        _relationship_source(item),
        _relationship_target(item),
        _text((item.get("source") or {}).get("field") if isinstance(item.get("source"), Mapping) else ""),
        _text(item.get("relationship_id")),
    ))
    total = len(normalized)
    if total <= relationship_limit:
        selected = normalized
        mode = "complete"
    else:
        selected = _round_robin(
            normalized,
            limit=relationship_limit,
            group_key=lambda item: _logical_domain(_relationship_source(item), inventory_by_fqcn),
            sort_key=lambda item: (
                _relationship_source(item), _relationship_target(item),
                _text((item.get("source") or {}).get("field") if isinstance(item.get("source"), Mapping) else ""),
                _text(item.get("relationship_id")),
            ),
        )
        mode = "overview"
    edges = [edge for edge in (_logical_edge(item) for item in selected) if edge]

    selected_names: list[str] = []
    for edge in edges:
        for name in (_text(edge.get("from")), _text(edge.get("to"))):
            if name and name not in selected_names:
                selected_names.append(name)
    for fqcn in sorted(bundle_by_fqcn):
        if fqcn not in selected_names:
            selected_names.append(fqcn)
    if not selected_names:
        ranked = sorted(
            inventory,
            key=lambda item: (
                {"root_entity": 0, "dictionary": 1, "entity": 2}.get(_text(item.get("object_kind")), 3),
                -int(item.get("direct_field_count") or 0),
                _text(item.get("fqcn")),
            ),
        )
        selected_names = [_text(item.get("fqcn")) for item in ranked if _text(item.get("fqcn"))]
        mode = "entity_only"
    selected_names = selected_names[:node_limit]
    nodes = [
        _logical_node(inventory_by_fqcn.get(name) or {"fqcn": name, "name": name.rsplit(".", 1)[-1]}, bundle_by_fqcn)
        for name in selected_names
    ]

    group_counts = Counter(_logical_domain(_relationship_source(item), inventory_by_fqcn) for item in normalized)
    return {
        "status": "observed" if inventory else "not_observed",
        "diagram_kind": "logical_er",
        "mode": mode if inventory else "not_observed",
        "entities": nodes,
        "relationships": edges,
        "entity_count": len(inventory),
        "relationship_count": total,
        "selected_entity_count": len(nodes),
        "selected_relationship_count": len(edges),
        "relationships_truncated": len(edges) < total,
        "selection_policy": (
            "all_relationships_up_to_30/v1" if total <= relationship_limit
            else "package_round_robin_overview_30/v1"
        ),
        "domain_groups": [
            {"domain": domain, "relationship_count": count}
            for domain, count in sorted(group_counts.items())
        ],
    }


def normalize_declared_relationship(row: Mapping[str, Any]) -> dict[str, Any] | None:
    source = _text(row.get("source_qualified_table_name") or row.get("source_table"))
    target = _text(row.get("target_qualified_table_name") or row.get("target_table"))
    if not source or not target:
        return None
    source_columns = _texts(row.get("source_columns_json") or ())
    target_columns = _texts(row.get("target_columns_json") or ())
    column_pairs = [
        {"from_column": left, "to_column": right}
        for left, right in zip(source_columns, target_columns)
    ]
    return {
        "relationship_id": row.get("db_relationship_occurrence_id") or row.get("local_relationship_id"),
        "repo_id": row.get("repo_id"),
        "constraint_name": row.get("constraint_name"),
        "relationship_kind": row.get("relationship_kind") or "declared_relationship",
        "from_table": source,
        "from_table_id": row.get("source_db_table_occurrence_id"),
        "from_columns": source_columns,
        "to_table": target,
        "to_table_id": row.get("target_db_table_occurrence_id"),
        "to_columns": target_columns,
        "column_pairs": column_pairs,
        "status": "confirmed",
        "basis": "declared_schema_relationship",
        "source_set": row.get("source_set"),
        "module_name": row.get("module_name"),
        "evidence_ids": _texts(row.get("evidence_ids") or ()),
    }


def _physical_table_node(
    name: str,
    *,
    table_id: str | None,
    representative: Mapping[str, Any] | None,
    detail: Mapping[str, Any] | None,
) -> dict[str, Any]:
    representative = representative or {}
    detail = detail or {}
    table_rows = [dict(item) for item in (detail.get("db_schema_tables") or ()) if isinstance(item, Mapping)]
    table_row = next(
        (
            item for item in table_rows
            if _text(item.get("db_table_occurrence_id")) == _text(table_id)
            or _text(item.get("qualified_table_name") or item.get("table_name")) == name
        ),
        table_rows[0] if table_rows else {},
    )
    resolved_id = table_id or table_row.get("db_table_occurrence_id") or representative.get("object_id")
    columns = [
        dict(item) for item in (detail.get("columns") or ())
        if isinstance(item, Mapping)
        and (
            not resolved_id
            or _text(item.get("db_table_occurrence_id")) == _text(resolved_id)
            or _text(item.get("qualified_table_name") or item.get("table_name")) == name
        )
    ]
    keys = [
        dict(item) for item in (detail.get("keys") or ())
        if isinstance(item, Mapping)
        and (
            not resolved_id
            or _text(item.get("db_table_occurrence_id")) == _text(resolved_id)
            or _text(item.get("qualified_table_name") or item.get("table_name")) == name
        )
    ]
    primary_key_columns: list[str] = []
    normalized_keys: list[dict[str, Any]] = []
    for key in keys:
        key_columns = _texts(key.get("columns_json") or ())
        kind = _text(key.get("constraint_kind"))
        if kind.casefold().replace(" ", "_") in {"primary_key", "pk"}:
            for column in key_columns:
                if column not in primary_key_columns:
                    primary_key_columns.append(column)
        normalized_keys.append({
            "key_id": key.get("db_key_occurrence_id") or key.get("local_key_id"),
            "constraint_name": key.get("constraint_name"),
            "constraint_kind": key.get("constraint_kind"),
            "columns": key_columns,
        })
    attributes = [
        {
            "name": column.get("column_name"),
            "type": column.get("sql_type"),
            "nullable": column.get("nullable"),
            "default_value": column.get("default_value"),
            "primary_key": _text(column.get("column_name")) in primary_key_columns,
        }
        for column in columns[:PHYSICAL_ATTRIBUTE_LIMIT]
    ]
    evidence_ids = _texts(representative.get("evidence_ids") or ())
    return {
        "table_id": resolved_id,
        "repo_id": representative.get("repo_id") or table_row.get("repo_id"),
        "name": representative.get("name") or table_row.get("table_name") or name.rsplit(".", 1)[-1],
        "schema": representative.get("schema") or table_row.get("schema_name"),
        "qualified_name": representative.get("qualified_name") or table_row.get("qualified_table_name") or name,
        "description": representative.get("description") or table_row.get("description"),
        "source_type": representative.get("source_type") or table_row.get("source_type"),
        "module_name": representative.get("module_name") or table_row.get("module_name"),
        "attributes": attributes,
        "column_count": len(columns) if columns else int(representative.get("column_count") or 0),
        "attributes_truncated": len(columns) > PHYSICAL_ATTRIBUTE_LIMIT,
        "primary_key_columns": primary_key_columns,
        "keys": normalized_keys[:6],
        "evidence_ids": evidence_ids,
    }


def build_physical_er(
    reporting_service: Any,
    representative_objects: Iterable[Mapping[str, Any]],
    declared_rows: Iterable[Mapping[str, Any]],
    *,
    table_total: int,
    declared_total: int,
    declared_collection_truncated: bool,
    relationship_limit: int = ER_RELATIONSHIP_LIMIT,
    node_limit: int = ER_NODE_LIMIT,
) -> dict[str, Any]:
    declared = [value for value in (normalize_declared_relationship(row) for row in declared_rows) if value]
    declared.sort(key=lambda item: (
        _text(item.get("from_table")), _text(item.get("to_table")),
        ",".join(item.get("from_columns") or ()), _text(item.get("relationship_id")),
    ))
    if declared_total <= relationship_limit and not declared_collection_truncated:
        selected = declared
        mode = "complete"
    else:
        selected = _round_robin(
            declared,
            limit=relationship_limit,
            group_key=lambda item: _physical_domain(_text(item.get("from_table"))),
            sort_key=lambda item: (
                _text(item.get("from_table")), _text(item.get("to_table")),
                ",".join(item.get("from_columns") or ()), _text(item.get("relationship_id")),
            ),
        )
        mode = "overview"

    representatives = [dict(item) for item in representative_objects]
    representative_by_name: dict[str, dict[str, Any]] = {}
    representative_by_id: dict[str, dict[str, Any]] = {}
    for item in representatives:
        name = _text(item.get("qualified_name") or item.get("name"))
        if name:
            representative_by_name[name] = item
        identifier = _text(item.get("object_id"))
        if identifier:
            representative_by_id[identifier] = item

    selected_tables: list[tuple[str, str | None]] = []
    for relation in selected:
        for name_key, id_key in (("from_table", "from_table_id"), ("to_table", "to_table_id")):
            name = _text(relation.get(name_key))
            identifier = _text(relation.get(id_key)) or None
            if name and (name, identifier) not in selected_tables:
                selected_tables.append((name, identifier))
    for item in representatives:
        name = _text(item.get("qualified_name") or item.get("name"))
        identifier = _text(item.get("object_id")) or None
        if name and all(existing[0] != name for existing in selected_tables):
            selected_tables.append((name, identifier))
    if not selected:
        mode = "entity_only" if representatives else "not_observed"
    selected_tables = selected_tables[:node_limit]

    detail_cache: dict[str, Mapping[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    for name, identifier in selected_tables:
        key = identifier or name
        detail: Mapping[str, Any] = {}
        if key:
            try:
                detail = reporting_service.query.get_table(key)
            except Exception as exc:  # Preserve the table node, but expose the failed optional enrichment.
                detail = {}
                diagnostics.append({
                    "code": "physical_er_table_detail_failed",
                    "table": name,
                    "table_id": identifier,
                    "exception_type": type(exc).__name__,
                    "message": str(exc)[:300],
                })
            detail_cache[key] = detail
        representative = representative_by_id.get(_text(identifier)) or representative_by_name.get(name)
        nodes.append(_physical_table_node(name, table_id=identifier, representative=representative, detail=detail))

    group_counts = Counter(_physical_domain(_text(item.get("from_table"))) for item in declared)
    return {
        "status": "observed" if table_total or representatives or declared_total else "not_observed",
        "diagram_kind": "physical_er",
        "mode": mode,
        "tables": nodes,
        "relationships": selected,
        "table_count": table_total,
        "declared_relationship_count": declared_total,
        "selected_table_count": len(nodes),
        "selected_relationship_count": len(selected),
        "relationships_truncated": len(selected) < declared_total or declared_collection_truncated,
        "selection_policy": (
            "all_declared_relationships_up_to_30/v1"
            if declared_total <= relationship_limit and not declared_collection_truncated
            else "schema_round_robin_overview_30/v1"
        ),
        "domain_groups": [
            {"schema": domain, "relationship_count": count}
            for domain, count in sorted(group_counts.items())
        ],
        "diagnostics": diagnostics,
        "relationship_semantics": "Only declared schema relationships belong to this ER model.",
    }


def build_observed_usage(
    relationships: Iterable[Mapping[str, Any]],
    *,
    total: int,
) -> dict[str, Any]:
    items = [dict(item) for item in relationships]
    items.sort(key=lambda item: (
        _text(item.get("left_table")), _text(item.get("right_table")),
        _text(item.get("relation_kind")), _text(item.get("relationship_id")),
    ))
    kind_counts = Counter(_text(item.get("relation_kind")) or "unknown" for item in items)
    source_counts = Counter(_text(item.get("source_kind")) or "unknown" for item in items)
    return {
        "status": "observed" if total else "not_observed",
        "diagram_kind": "observed_usage",
        "relationships": items,
        "relationship_count": total,
        "selected_relationship_count": len(items),
        "relationships_truncated": len(items) < total,
        "relation_kind_counts": dict(sorted(kind_counts.items())),
        "source_kind_counts": dict(sorted(source_counts.items())),
        "semantics": "Observed SQL/JOOQ/data-movement usage; not a declared FK unless matched_declared_keys proves a match.",
    }
