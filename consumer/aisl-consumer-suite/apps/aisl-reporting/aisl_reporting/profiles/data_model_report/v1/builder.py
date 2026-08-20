from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text
from ....knowledge_api import KnowledgeApiSourceError


def _items(client: Any, path: str, *, params: Mapping[str, Any] | None = None, max_items: int = 5000) -> tuple[list[dict[str, Any]], int, bool]:
    base = dict(params or {})
    offset = 0
    values: list[dict[str, Any]] = []
    total = 0
    while len(values) < max_items:
        payload = client.get_json(path, params={**base, "offset": offset, "limit": min(500, max_items - len(values))})
        page_items = [dict(item) for item in payload.get("items") or () if isinstance(item, Mapping)]
        page = payload.get("page") or {}
        total = int(page.get("total") or len(values) + len(page_items))
        values.extend(page_items)
        offset += len(page_items)
        if not page_items or offset >= total:
            break
    return values, total, len(values) < total


def _text(value: Any) -> str:
    return str(value or "").strip()


def _focus_match(item: Mapping[str, Any], terms: tuple[str, ...]) -> bool:
    if not terms:
        return True
    text = canonical_json(item).casefold()
    return any(term.casefold() in text for term in terms)


def _select(
    items: list[dict[str, Any]],
    focus: tuple[str, ...],
    limit: int,
    *,
    preferred_names: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], str]:
    ranked = sorted(
        items,
        key=lambda item: (
            0 if _focus_match(item, focus) else 1,
            -int(item.get("relationship_count") or 0),
            -int(item.get("field_count") or 0),
            _text(item.get("table_name")),
        ),
    )
    if focus:
        selected = [item for item in ranked if _focus_match(item, focus)][:limit]
        if not selected:
            return [], "no_effective_entity_matches_focus"
        return selected, "matched"

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_name.setdefault(_text(item.get("table_name")), []).append(item)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for name in preferred_names:
        candidates = by_name.get(name) or []
        if len(candidates) != 1:
            continue
        item = candidates[0]
        item_id = _text(item.get("table_id"))
        if item_id and item_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item_id)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for item in ranked:
            item_id = _text(item.get("table_id"))
            if item_id in selected_ids:
                continue
            selected.append(item)
            if item_id:
                selected_ids.add(item_id)
            if len(selected) >= limit:
                break
    return selected, "lineage_prioritized" if preferred_names else "not_requested"


def _evidence_index(value: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            evidence_id = _text(item.get("evidence_id"))
            repo_id = _text(item.get("repo_id"))
            path = _text(item.get("path"))
            if evidence_id and repo_id and path:
                result[evidence_id] = {
                    "evidence_id": evidence_id,
                    "repo_id": repo_id,
                    "path": path,
                    "line_start": item.get("line_start"),
                    "line_end": item.get("line_end"),
                    "extractor": item.get("extractor"),
                    "maturity": _text(item.get("maturity")) or "observed",
                    "role": item.get("role"),
                }
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return dict(sorted(result.items()))


def _logical_inventory(table_summaries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in table_summaries:
        result.append({
            "object_id": item.get("table_id"),
            "repo_id": None,
            "fqcn": item.get("table_name"),
            "name": item.get("table_name"),
            "package_name": None,
            "object_kind": item.get("table_kind") or "effective_entity",
            "display_name": item.get("display_name"),
            "description": item.get("description"),
            "direct_field_count": int(item.get("field_count") or 0),
            "relationship_count": int(item.get("relationship_count") or 0),
            "evidence_ids": [],
        })
    return result


def _compact_storage_observation(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "table_id", "table_name", "table_code", "column_id", "column_name",
            "column_code", "mapping_status", "match_basis", "evidence_ids",
        )
        if item.get(key) not in (None, [], {})
    }


def _compact_logical_field(item: Mapping[str, Any]) -> dict[str, Any]:
    observations = [
        _compact_storage_observation(value)
        for value in item.get("storage_observations") or ()
        if isinstance(value, Mapping)
    ]
    observation_count = int(item.get("storage_observation_count") or len(observations))
    description = _text(item.get("description"))
    mapping_status = None
    if description.startswith("Mapping status ") and description.endswith("."):
        mapping_status = description[len("Mapping status ") : -1]
        description = ""
    return {
        key: value
        for key, value in {
            "name": item.get("name"),
            "type": item.get("type"),
            "target_object": item.get("target_object"),
            "description": description or None,
            "mapping_status": mapping_status,
            "inherited": True if item.get("inherited") else None,
            "storage_observation_count": observation_count if observation_count else None,
            "storage_observations": observations[:3] or None,
            "storage_observations_truncated": True
            if bool(item.get("storage_observations_truncated")) or len(observations) > 3
            else None,
        }.items()
        if value not in (None, [], {})
    }


def _compact_logical_key(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("key_id", "name", "kind", "fields", "inherited", "source", "evidence_ids")
        if item.get(key) not in (None, [], {})
    }


def _compact_logical_relationship(item: Mapping[str, Any]) -> dict[str, Any]:
    target = item.get("target") or {}
    target_object = (target.get("object") or {}) if isinstance(target, Mapping) else {}
    join = item.get("join") or {}
    compact_join = {
        key: value
        for key, value in {
            "method": join.get("method") if isinstance(join, Mapping) else None,
            "source_fields": list(join.get("source_fields") or ()) if isinstance(join, Mapping) else [],
            "target_fields": list(join.get("target_fields") or ()) if isinstance(join, Mapping) else [],
            "physical_join_confirmed": True
            if isinstance(join, Mapping) and join.get("physical_join_confirmed")
            else None,
            "match_basis": join.get("match_basis") if isinstance(join, Mapping) else None,
        }.items()
        if value not in (None, [], {})
    }
    return {
        key: value
        for key, value in {
            "kind": item.get("kind"),
            "source_field": item.get("source_field"),
            "cardinality": item.get("cardinality"),
            "target_name": target_object.get("name"),
            "target_kind": target_object.get("kind"),
            "join": compact_join or None,
        }.items()
        if value not in (None, [], {})
    }


def _logical_bundle(
    detail: Mapping[str, Any],
    *,
    field_limit: int,
    relationship_limit: int,
) -> dict[str, Any]:
    obj = dict(detail.get("object") or {})
    all_fields = [dict(item) for item in detail.get("fields") or () if isinstance(item, Mapping)]
    all_keys = [dict(item) for item in detail.get("keys") or () if isinstance(item, Mapping)]
    all_relationships = [dict(item) for item in detail.get("relationships") or () if isinstance(item, Mapping)]
    fields = [_compact_logical_field(item) for item in all_fields[:field_limit]]
    keys = [_compact_logical_key(item) for item in all_keys[:10]]
    relationships = [
        _compact_logical_relationship(item) for item in all_relationships[:relationship_limit]
    ]
    return {
        "object": {
            "object_id": obj.get("id"),
            "fqcn": obj.get("name"),
            "name": obj.get("name"),
            "object_kind": obj.get("kind"),
            "display_name": obj.get("display_name"),
            "description": obj.get("description"),
        },
        "fields": fields,
        "fields_truncated": len(fields) < len(all_fields),
        "keys": keys,
        "keys_truncated": len(keys) < len(all_keys),
        "relationships": relationships,
        "relationships_truncated": len(relationships) < len(all_relationships),
        "summary": {
            "field_count": len(all_fields),
            "selected_field_count": len(fields),
            "inherited_field_count": sum(1 for item in all_fields if item.get("inherited")),
            "collection_field_count": sum(1 for item in all_fields if item.get("target_object")),
            "key_count": len(all_keys),
            "selected_key_count": len(keys),
            "relationship_count": len(all_relationships),
            "selected_relationship_count": len(relationships),
            "relation_kind_counts": dict(sorted(Counter(_text(item.get("kind")) or "unknown" for item in all_relationships).items())),
        },
    }


def _compact_physical_column(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "ordinal", "column_name", "column_code",
            "data_type", "length", "precision", "scale", "mandatory",
        )
        if item.get(key) is not None
    }


def _compact_physical_table(item: Mapping[str, Any], *, column_limit: int) -> dict[str, Any]:
    columns = [dict(value) for value in item.get("columns") or () if isinstance(value, Mapping)]
    selected_columns = [_compact_physical_column(value) for value in columns[:column_limit]]
    return {
        key: value
        for key, value in {
            "physical_model_table_id": item.get("physical_model_table_id"),
            "model_name": item.get("model_name"),
            "model_code": item.get("model_code"),
            "package_path": item.get("package_path"),
            "package_code_path": item.get("package_code_path"),
            "table_name": item.get("table_name"),
            "table_code": item.get("table_code"),
            "logical_identity": item.get("logical_identity"),
            "column_count": int(item.get("column_count") or len(columns)),
            "selected_column_count": len(selected_columns),
            "columns_truncated": len(selected_columns) < len(columns),
            "key_count": int(item.get("key_count") or 0),
            "inbound_relationship_count": int(item.get("inbound_relationship_count") or 0),
            "outbound_relationship_count": int(item.get("outbound_relationship_count") or 0),
            "source_file": item.get("source_file"),
            "columns": selected_columns,
        }.items()
        if value not in (None, [], {})
    }


def _compact_physical_relationship(item: Mapping[str, Any]) -> dict[str, Any]:
    joins = [dict(value) for value in item.get("joins") or () if isinstance(value, Mapping)]
    return {
        key: value
        for key, value in {
            "physical_model_relationship_id": item.get("physical_model_relationship_id"),
            "relationship_name": item.get("relationship_name"),
            "relationship_code": item.get("relationship_code"),
            "cardinality": item.get("cardinality"),
            "parent_table_id": item.get("parent_table_id"),
            "parent_table_code": item.get("parent_table_code"),
            "parent_table_name": item.get("parent_table_name"),
            "child_table_id": item.get("child_table_id"),
            "child_table_code": item.get("child_table_code"),
            "child_table_name": item.get("child_table_name"),
            "joins": [
                {
                    key: join.get(key)
                    for key in ("child_column_code", "parent_column_code")
                    if join.get(key) is not None
                }
                for join in joins
            ],
            "resolution_status": item.get("resolution_status"),
            "source_file": item.get("source_file"),
        }.items()
        if value not in (None, [], {})
    }


def _logical_er(inventory: list[dict[str, Any]], details: list[dict[str, Any]], total_relationships: int) -> dict[str, Any]:
    details_by_id = {_text((item.get("object") or {}).get("id")): item for item in details}
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for item in inventory[:40]:
        detail = details_by_id.get(_text(item.get("object_id"))) or {}
        fields = [dict(value) for value in detail.get("fields") or () if isinstance(value, Mapping)]
        key_names = {
            _text(name)
            for key in detail.get("keys") or () if isinstance(key, Mapping)
            for name in key.get("fields") or ()
        }
        entities.append({
            "entity_id": item.get("object_id"),
            "repo_id": item.get("repo_id"),
            "name": item.get("name"),
            "qualified_name": item.get("fqcn"),
            "package_name": item.get("package_name"),
            "object_kind": item.get("object_kind"),
            "display_name": item.get("display_name"),
            "description": item.get("description"),
            "direct_field_count": item.get("direct_field_count"),
            "attributes": [
                {
                    "name": field.get("name"),
                    "type": field.get("type"),
                    "inherited": bool(field.get("inherited")),
                    "key": _text(field.get("name")) in key_names,
                    "evidence_ids": [
                        _text(eid)
                        for obs in field.get("storage_observations") or () if isinstance(obs, Mapping)
                        for eid in obs.get("evidence_ids") or () if _text(eid)
                    ],
                }
                for field in fields[:8]
            ],
            "attribute_count": len(fields) or int(item.get("direct_field_count") or 0),
            "attributes_truncated": len(fields) > 8,
            "keys": list(detail.get("keys") or ())[:5],
            "evidence_ids": [],
        })
        for relation in detail.get("relationships") or ():
            if not isinstance(relation, Mapping):
                continue
            target = relation.get("target") or {}
            target_object = target.get("object") or {}
            join = relation.get("join") or {}
            relationships.append({
                "relationship_id": relation.get("relationship_id"),
                "from": item.get("fqcn"),
                "to": target_object.get("name"),
                "field": relation.get("source_field"),
                "relation_kind": relation.get("kind"),
                "cardinality": relation.get("cardinality"),
                "inherited": False,
                "polymorphic_targets": [value.get("name") for value in relation.get("polymorphic_targets") or () if isinstance(value, Mapping)],
                "evidence_ids": [],
                "basis": join.get("match_basis") or "effective_data_model_relationship",
            })
    unique = {(_text(item.get("relationship_id")), _text(item.get("from")), _text(item.get("to"))): item for item in relationships}
    selected = sorted(unique.values(), key=lambda item: (_text(item.get("from")), _text(item.get("to")), _text(item.get("field"))))[:20]
    return {
        "status": "observed" if inventory else "not_observed",
        "diagram_kind": "logical_er",
        "mode": "complete" if total_relationships <= 30 else "overview",
        "entities": entities,
        "relationships": selected,
        "entity_count": len(inventory),
        "relationship_count": total_relationships,
        "selected_entity_count": len(entities),
        "selected_relationship_count": len(selected),
        "relationships_truncated": len(selected) < total_relationships,
        "selection_policy": "all_relationships_up_to_30/v1" if total_relationships <= 30 else "deterministic_first_30/v1",
        "domain_groups": [],
    }


def _physical_er(tables: list[dict[str, Any]], relationships: list[dict[str, Any]], total_relationships: int) -> dict[str, Any]:
    nodes = []
    for item in tables[:40]:
        qualified = item.get("table_code") or item.get("table_name") or item.get("physical_model_table_id")
        columns = [dict(value) for value in item.get("columns") or () if isinstance(value, Mapping)]
        nodes.append({
            "table_id": item.get("physical_model_table_id"),
            "name": qualified,
            "qualified_name": qualified,
            "description": item.get("description") or item.get("comment"),
            "attributes": [
                {
                    "name": column.get("column_code") or column.get("column_name"),
                    "type": column.get("data_type"),
                    "primary_key": False,
                }
                for column in columns[:8]
            ],
            "primary_key_columns": [],
            "attribute_count": len(columns) or int(item.get("column_count") or 0),
            "attributes_truncated": len(columns) > 8,
        })
    edges = []
    for item in relationships[:20]:
        from_table = item.get("child_table_code") or item.get("child_table_name") or item.get("child_table_id")
        to_table = item.get("parent_table_code") or item.get("parent_table_name") or item.get("parent_table_id")
        edges.append({
            "relationship_id": item.get("physical_model_relationship_id"),
            "from_table": from_table,
            "to_table": to_table,
            "from_columns": [join.get("child_column_code") or join.get("child_column_name") for join in item.get("joins") or () if isinstance(join, Mapping)],
            "to_columns": [join.get("parent_column_code") or join.get("parent_column_name") for join in item.get("joins") or () if isinstance(join, Mapping)],
            "cardinality": item.get("cardinality"),
            "status": item.get("resolution_status"),
            "basis": "physical_model_relationship",
        })
    return {
        "status": "observed" if tables else "not_observed",
        "diagram_kind": "physical_er",
        "mode": "complete" if total_relationships <= 30 else "overview",
        "tables": nodes,
        "relationships": edges,
        "table_count": len(tables),
        "declared_relationship_count": total_relationships,
        "selected_table_count": len(nodes),
        "selected_relationship_count": len(edges),
        "relationships_truncated": len(edges) < total_relationships,
        "selection_policy": "all_relationships_up_to_30/v1" if total_relationships <= 30 else "deterministic_first_30/v1",
        "domain_groups": [],
    }




def _compact_lineage_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "logical_type": item.get("logical_fully_qualified_name"),
            "logical_field": item.get("logical_field_name"),
            "storage_alias": item.get("storage_alias"),
            "source_relation": item.get("source_sql_relation"),
            "source_usage_role": item.get("source_sql_usage_role"),
            "source_sql_file": item.get("source_sql_file"),
            "source_column": item.get("source_sql_column_name"),
            "target_table": item.get("target_table_code"),
            "target_column": item.get("physical_column_code"),
            "transform_sql_file": item.get("transform_sql_file"),
            "transformation": item.get("target_projection_expression"),
            "knowledge_class": item.get("knowledge_class"),
            "basis": item.get("mapping_basis"),
        }.items()
        if value not in (None, [], {})
    }


def _lineage_sections(items: list[dict[str, Any]], total: int, truncated: bool) -> dict[str, Any]:
    compact = [_compact_lineage_item(item) for item in items]
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in compact:
        key = (
            _text(item.get("logical_type")),
            _text(item.get("logical_field")),
            _text(item.get("target_table")),
            _text(item.get("target_column")),
        )
        unique.setdefault(key, item)
    correspondences = list(unique.values())
    correspondences.sort(key=lambda item: (
        _text(item.get("target_table")).casefold(),
        _text(item.get("target_column")).casefold(),
        _text(item.get("logical_type")).casefold(),
        _text(item.get("logical_field")).casefold(),
    ))

    transforms: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in correspondences:
        expression = _text(item.get("transformation"))
        if not expression:
            continue
        key = (_text(item.get("target_table")), _text(item.get("target_column")), expression)
        transforms.setdefault(key, {
            "target_table": item.get("target_table"),
            "target_column": item.get("target_column"),
            "expression": expression,
            "transform_sql_file": item.get("transform_sql_file"),
            "logical_inputs": [],
            "knowledge_class": item.get("knowledge_class"),
        })
        logical_input = {"type": item.get("logical_type"), "field": item.get("logical_field")}
        if logical_input not in transforms[key]["logical_inputs"]:
            transforms[key]["logical_inputs"].append(logical_input)

    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in correspondences:
        by_target.setdefault(_text(item.get("target_table")), []).append(item)
    journeys = []
    for table in sorted(by_target, key=lambda value: (value.casefold(), value)):
        rows = by_target[table]
        type_counts = Counter(_text(row.get("logical_type")) for row in rows if _text(row.get("logical_type")))

        def normalized(value: Any) -> str:
            return "".join(ch for ch in _text(value).casefold() if ch.isalnum())

        direct = [
            row for row in rows
            if normalized(row.get("logical_field"))
            and normalized(row.get("logical_field")) == normalized(row.get("target_column"))
        ]
        rare = sorted(
            [row for row in rows if type_counts.get(_text(row.get("logical_type")), 0) <= 2],
            key=lambda row: (
                type_counts.get(_text(row.get("logical_type")), 0),
                _text(row.get("logical_type")).casefold(),
                _text(row.get("target_column")).casefold(),
            ),
        )
        example_rows: list[dict[str, Any]] = []
        seen_examples: set[tuple[str, str, str]] = set()
        for pool, pool_limit in ((direct, 4), (rare, 2), (rows, 8)):
            added = 0
            for row in pool:
                key = (_text(row.get("logical_type")), _text(row.get("logical_field")), _text(row.get("target_column")))
                if key in seen_examples:
                    continue
                seen_examples.add(key)
                example_rows.append(row)
                added += 1
                if len(example_rows) >= 8 or added >= pool_limit:
                    break
            if len(example_rows) >= 8:
                break
        journeys.append({
            "target_table": table,
            "logical_source_types": sorted({_text(row.get("logical_type")) for row in rows if _text(row.get("logical_type"))}),
            "field_correspondence_count": len(rows),
            "examples": [
                {key: row.get(key) for key in ("logical_type", "logical_field", "target_column", "transformation", "knowledge_class") if row.get(key) not in (None, "")}
                for row in example_rows
            ],
            "example_selection_policy": "direct_name_correspondence_then_rare_source_type_then_deterministic_fill/v1",
        })

    usage_relationships = [
        {
            "source_object": item.get("logical_type"),
            "source_field": item.get("logical_field"),
            "source_sql_file": item.get("source_sql_file"),
            "source_column": item.get("source_column"),
            "target_table": item.get("target_table"),
            "target_column": item.get("target_column"),
            "transform_sql_file": item.get("transform_sql_file"),
            "transformation": item.get("transformation"),
            "knowledge_class": item.get("knowledge_class"),
            "basis": item.get("basis"),
        }
        for item in correspondences[:40]
    ]
    return {
        "correspondences": correspondences,
        "transformations": list(transforms.values()),
        "journeys": journeys,
        "observed_usage": {
            "status": "observed" if correspondences else "not_observed",
            "diagram_kind": "observed_usage",
            "relationships": usage_relationships,
            "relationship_count": len(correspondences),
            "relationships_truncated": len(usage_relationships) < len(correspondences) or truncated,
            "semantics": "Published logical-field → SQL → physical-column lineage from cross-artifact-data-model-mapping/v3; derived/candidate status remains explicit.",
        },
        "path_count": total,
        "unique_correspondence_count": len(correspondences),
        "truncated": truncated,
    }

def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise KnowledgeApiSourceError("data-model-report/v1 requires a resolved Knowledge API revision")
    client = source.client
    system_id = source.system_id
    revision_id = source.revision_id
    prefix = f"/api/knowledge/v1/systems/{system_id}"
    revision_params = {"revision_id": revision_id}

    table_summaries, table_total, table_truncated = _items(
        client,
        f"{prefix}/data-model/tables",
        params={**revision_params, "include_fields": True},
    )
    lineage_available = "common.logical-field-physical-lineage" in set(source.capabilities)
    lineage_items: list[dict[str, Any]] = []
    lineage_total = 0
    lineage_truncated = False
    if lineage_available:
        lineage_items, lineage_total, lineage_truncated = _items(
            client,
            f"{prefix}/data-model/lineage",
            params=revision_params,
            max_items=5000,
        )
    lineage = _lineage_sections(lineage_items, lineage_total, lineage_truncated)
    lineage_type_counts = Counter(
        _text(item.get("logical_fully_qualified_name"))
        for item in lineage_items
        if _text(item.get("logical_fully_qualified_name"))
    )
    preferred_logical_names = tuple(
        fqcn.rsplit(".", 1)[-1]
        for fqcn, _count in sorted(
            lineage_type_counts.items(),
            key=lambda pair: (-pair[1], pair[0].casefold(), pair[0]),
        )
    )
    limits = {"executive": 10, "standard": 20, "detailed": 40}
    selected, focus_status = _select(
        table_summaries,
        request.focus,
        limits[request.detail_level],
        preferred_names=preferred_logical_names,
    )

    details: list[dict[str, Any]] = []
    detail_ids = {_text(item.get("table_id")) for item in selected}
    if table_total <= 60:
        detail_ids.update(_text(item.get("table_id")) for item in table_summaries)
    for table_id in sorted(value for value in detail_ids if value):
        details.append(client.get_json(f"{prefix}/data-model/tables/{table_id}", params=revision_params))

    selected_ids = {_text(item.get("table_id")) for item in selected}
    selected_details = [item for item in details if _text((item.get("object") or {}).get("id")) in selected_ids]
    logical_field_limits = {"executive": 12, "standard": 30, "detailed": 60}
    logical_relationship_limits = {"executive": 8, "standard": 15, "detailed": 30}
    bundles = [
        _logical_bundle(
            item,
            field_limit=logical_field_limits[request.detail_level],
            relationship_limit=logical_relationship_limits[request.detail_level],
        )
        for item in selected_details
    ]
    inventory = _logical_inventory(table_summaries)
    all_relationships = [dict(rel) for item in details for rel in item.get("relationships") or () if isinstance(rel, Mapping)]
    relationship_total = sum(int(item.get("relationship_count") or 0) for item in table_summaries)

    coverage = client.get_json(f"{prefix}/coverage", params=revision_params)
    physical_available = "common.physical-model" in set(source.capabilities)
    physical_summary: dict[str, Any] = {}
    physical_tables: list[dict[str, Any]] = []
    physical_relationships: list[dict[str, Any]] = []
    physical_gaps: list[dict[str, Any]] = []
    physical_relationship_total = 0
    if physical_available:
        physical_summary = client.get_json(f"{prefix}/physical-model", params=revision_params)
        physical_tables, _, _ = _items(
            client,
            f"{prefix}/physical-model/tables",
            params={**revision_params, "include_columns": True},
        )
        physical_relationships, physical_relationship_total, _ = _items(
            client,
            f"{prefix}/physical-model/relationships",
            params=revision_params,
        )
        physical_gaps, _, _ = _items(client, f"{prefix}/physical-model/gaps", params=revision_params)
        target_counts = Counter(_text(item.get("target_table_code")) for item in lineage_items if _text(item.get("target_table_code")))
        target_rank = {name: index for index, (name, _count) in enumerate(sorted(target_counts.items(), key=lambda pair: (-pair[1], pair[0].casefold(), pair[0])))}
        target_set = set(target_rank)
        adjacent_tables: set[str] = set()
        for relation in physical_relationships:
            child = _text(relation.get("child_table_code"))
            parent = _text(relation.get("parent_table_code"))
            if child in target_set and parent:
                adjacent_tables.add(parent)
            if parent in target_set and child:
                adjacent_tables.add(child)
        physical_tables.sort(key=lambda item: (
            0 if _text(item.get("table_code")) in target_rank else 1 if _text(item.get("table_code")) in adjacent_tables else 2,
            target_rank.get(_text(item.get("table_code")), 10**9),
            _text(item.get("table_code") or item.get("table_name")).casefold(),
        ))
        physical_relationships.sort(key=lambda item: (
            0 if (_text(item.get("child_table_code")) in target_set or _text(item.get("parent_table_code")) in target_set) else 1,
            _text(item.get("child_table_code") or item.get("child_table_name")).casefold(),
            _text(item.get("parent_table_code") or item.get("parent_table_name")).casefold(),
        ))

    artifact_diagnostics = [
        dict(value)
        for value in (source.selected_artifact or {}).get("diagnostics") or ()
        if isinstance(value, Mapping)
    ]
    limitations = [dict(value) for value in coverage.get("limitations") or () if isinstance(value, Mapping)]
    gap_items = physical_gaps + artifact_diagnostics + limitations
    gap_summary = {
        "gap_count": len(gap_items),
        "by_kind": dict(sorted(Counter(_text(item.get("gap_kind") or item.get("kind") or item.get("category")) or "unknown" for item in gap_items).items())),
    }

    selected_inventory_ids = {_text(item.get("table_id")) for item in selected}
    logical_er_inventory = (
        [item for item in inventory if _text(item.get("object_id")) in selected_inventory_ids]
        + [item for item in inventory if _text(item.get("object_id")) not in selected_inventory_ids]
    )
    logical_er = _logical_er(logical_er_inventory, details, relationship_total)
    physical_er = _physical_er(physical_tables, physical_relationships, physical_relationship_total)
    observed_usage = lineage["observed_usage"] if lineage_available else {
        "status": "not_observed",
        "diagram_kind": "observed_usage",
        "relationships": [],
        "relationship_count": 0,
        "relationships_truncated": False,
        "semantics": "Cross-artifact logical-field lineage is not published in this Knowledge API revision.",
    }

    evidence = _evidence_index({"details": details, "physical_tables": physical_tables, "physical_relationships": physical_relationships}) if request.include_evidence else {}
    repository_ids = sorted({_text(item.get("repo_id")) for item in evidence.values() if _text(item.get("repo_id"))})
    execution = source.revision.get("execution") or {}
    scope_kind = _text(execution.get("scope_kind")) or "repository"
    if scope_kind not in {"repository", "workspace"}:
        scope_kind = "workspace"
    scope_id = _text(execution.get("scope_id")) or system_id

    object_kind_counts = Counter(_text(item.get("object_kind")) or "effective_entity" for item in inventory)
    relationship_kind_counts = Counter(_text(item.get("kind")) or "unknown" for item in all_relationships)
    join_method_counts = Counter(_text((item.get("join") or {}).get("method")) or "unknown" for item in all_relationships)
    dictionaries = [item for item in inventory if _text(item.get("object_kind")) == "dictionary"]
    sections = {
        "model_inventory": {
            "status": "observed" if inventory else "not_observed",
            "report_mode": "logical_and_physical" if inventory and physical_tables else "logical_only" if inventory else "physical_only" if physical_tables else "not_observed",
            "object_count": table_total,
            "object_kind_counts": dict(sorted(object_kind_counts.items())),
            "root_entities": [item for item in inventory if _text(item.get("object_kind")) in {"root_entity", "entity", "effective_entity"}],
            "catalog_truncated": table_truncated,
        },
        "selected_objects": bundles,
        "relationships_and_joins": {
            "relationship_count": relationship_total,
            "relation_kind_counts": dict(sorted(relationship_kind_counts.items())),
            "join_method_counts": dict(sorted(join_method_counts.items())),
            "items": [_compact_logical_relationship(item) for item in all_relationships[:60]],
            "physical_join_warning": "Only relationships with physical_join_confirmed=true are confirmed physical joins.",
        },
        "referenced_dictionaries": dictionaries,
        "cross_repository_correspondences": {
            "items": lineage["correspondences"][:40],
            "count": lineage["unique_correspondence_count"],
            "status": "observed" if lineage_available and lineage["correspondences"] else "not_published_in_revision",
            "items_truncated": len(lineage["correspondences"]) > 40 or lineage["truncated"],
            "interpretation": "Cross-artifact logical→SQL→physical correspondences; they do not imply repository ownership or runtime dependency.",
        },
        "field_lineage": {
            "status": "observed" if lineage_available and lineage["correspondences"] else "not_published_in_revision",
            "path_count": lineage["path_count"],
            "unique_correspondence_count": lineage["unique_correspondence_count"],
            "items": lineage["correspondences"][:60],
            "items_truncated": len(lineage["correspondences"]) > 60 or lineage["truncated"],
        },
        "transformations": {
            "status": "observed" if lineage_available and lineage["transformations"] else "not_observed",
            "count": len(lineage["transformations"]),
            "items": lineage["transformations"][:20],
            "items_truncated": len(lineage["transformations"]) > 20,
        },
        "data_journeys": {
            "status": "observed" if lineage_available and lineage["journeys"] else "not_observed",
            "count": len(lineage["journeys"]),
            "items": lineage["journeys"][:20],
            "items_truncated": len(lineage["journeys"]) > 20,
        },
        "physical_model_observations": {
            "status": "observed" if physical_tables else "not_available",
            "report_mode": "logical_and_physical" if inventory and physical_tables else "logical_only",
            "summary": physical_summary,
            "object_count": len(physical_tables),
            "relationship_count": physical_relationship_total,
            "representative_objects": [
                _compact_physical_table(
                    item,
                    column_limit={"executive": 12, "standard": 24, "detailed": 40}[request.detail_level],
                )
                for item in physical_tables[: {"executive": 15, "standard": 30, "detailed": 50}[request.detail_level]]
            ],
            "relationships": [
                _compact_physical_relationship(item)
                for item in physical_relationships[: {"executive": 25, "standard": 60, "detailed": 120}[request.detail_level]]
            ],
            "declared_relationship_count": physical_relationship_total,
            "selection_policy": (
                "Knowledge API physical-data-model artifact; deterministic representative tables, "
                "columns and relationships compacted by report detail level with explicit truncation flags."
            ),
            "interpretation": "Physical facts are read from the separately published physical-data-model artifact.",
        },
        "gaps": {"summary": gap_summary, "items": gap_items[:100]},
        "diagrams": {"logical_er": logical_er, "physical_er": physical_er, "observed_usage": observed_usage},
        "owner_questions": [
            {
                "question_id": "Q-MODEL-GAPS",
                "question": "Какие опубликованные gaps модели необходимо закрыть в исходном коде, PDM или mapping-контракте?",
                "basis": f"В активной ревизии опубликовано gaps/limitations: {len(gap_items)}.",
            },
            {
                "question_id": "Q-MODEL-SCOPE",
                "question": "Все ли бизнес-критичные сущности и физические таблицы входят в выбранную ревизию?",
                "basis": f"Effective entities: {table_total}; physical tables: {len(physical_tables)}.",
            },
        ],
    }

    report_mode = sections["model_inventory"]["report_mode"]
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": {"kind": scope_kind, "id": scope_id, "repository_ids": repository_ids},
        "coverage": {
            "analysis_coverage": coverage,
            "knowledge_layer_counts": {
                "effective_entities": table_total,
                "effective_relationships": relationship_total,
                "physical_tables": len(physical_tables),
                "physical_relationships": physical_relationship_total,
                "cross_artifact_lineage_paths": lineage["path_count"],
                "logical_physical_correspondences": lineage["unique_correspondence_count"],
            },
            "report_mode": report_mode,
            "model_object_count": table_total,
            "physical_object_count": len(physical_tables),
            "physical_relationship_count": physical_relationship_total,
            "declared_physical_relationship_count": physical_relationship_total,
            "logical_relationship_count": relationship_total,
            "root_entity_count": sum(1 for item in inventory if _text(item.get("object_kind")) in {"root_entity", "entity", "effective_entity"}),
            "dictionary_count": len(dictionaries),
            "entity_count": table_total,
            "selected_object_count": len(bundles),
            "focus_status": focus_status,
            "api_revision_id": revision_id,
        },
        "sections": sections,
        "evidence_index": evidence,
        "interpretation_policy": {
            "source_of_truth": "Knowledge API revision and typed knowledge artifacts",
            "logical_model": "effective-data-model/v1",
            "physical_model": "knowledge_layer_physical_model/v1 when capability common.physical-model is published",
            "cross_artifact_lineage": "cross-artifact-data-model-mapping/v3 when capability common.logical-field-physical-lineage is published",
            "no_legacy_combined_database": True,
            "no_name_similarity_inference": True,
            "no_task_suite_profile_routing": True,
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
