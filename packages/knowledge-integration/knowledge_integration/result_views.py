from __future__ import annotations

"""Bounded model-facing views of Knowledge API tool results.

The raw Knowledge API response remains the provenance/source-of-truth payload.  This
module only derives an explicit, diagnosable representation suitable for LLM
context.  No semantic facts are invented and no truncation is silent.
"""

from typing import Any, Mapping, Sequence

MODEL_RESULT_VIEW_SCHEMA = "knowledge_integration_model_result_view/v1"


def _text(value: Any, *, limit: int = 1200) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"… <truncated {len(text) - limit} chars>"


def _source_ref(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value.get(key)
        for key in ("repository_relative_path", "line_start", "line_end", "extractor")
        if value.get(key) is not None
    }
    return result or None


def _documentation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in ("display_name", "summary", "description"):
        text = _text(value.get(key), limit=800)
        if text:
            result[key] = text
    tags = value.get("tags")
    if isinstance(tags, Mapping):
        compact_tags = {
            str(k): _text(v, limit=300)
            for k, v in tags.items()
            if _text(v, limit=300)
        }
        if compact_tags:
            result["tags"] = compact_tags
    return result or None


def _annotation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in (
        "annotation_occurrence_id",
        "annotation_name",
        "arguments_raw",
        "resolution_status",
        "resolved_annotation_type",
    ):
        val = value.get(key)
        if val is not None:
            result[key] = _text(val, limit=1000) if isinstance(val, str) else val
    candidates = value.get("candidate_annotation_types")
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        result["candidate_annotation_types"] = [str(v) for v in candidates[:20]]
        if len(candidates) > 20:
            result["candidate_annotation_types_truncated"] = True
    src = _source_ref(value.get("source_ref"))
    if src:
        result["source_ref"] = src
    return result or None


def _annotations(values: Any, *, limit: int = 20) -> tuple[list[dict[str, Any]], bool, int]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return [], False, 0
    items = [item for item in (_annotation(v) for v in values[:limit]) if item]
    return items, len(values) > limit, len(values)


def _brief_annotation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    name = _text(value.get("annotation_name"), limit=300)
    if name:
        result["annotation_name"] = name
    raw = _text(value.get("arguments_raw"), limit=800)
    if raw:
        result["arguments_raw"] = raw
    status = _text(value.get("resolution_status"), limit=200)
    if status:
        result["resolution_status"] = status
    return result or None


def _brief_annotations(values: Any, *, limit: int = 20) -> tuple[list[dict[str, Any]], bool, int]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return [], False, 0
    items = [item for item in (_brief_annotation(v) for v in values[:limit]) if item]
    return items, len(values) > limit, len(values)


def _field(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in (
        "effective_field_occurrence_id",
        "field_occurrence_id",
        "declaring_type_occurrence_id",
        "name",
        "inherited_depth",
        "is_inherited",
        "derivation_kind",
        "declared_type_expression",
        "normalized_type_expression",
        "is_static",
        "is_final",
    ):
        if value.get(key) is not None:
            result[key] = value.get(key)
    docs = _documentation(value.get("documentation"))
    if docs:
        result["documentation"] = docs
    src = _source_ref(value.get("source_ref"))
    if src:
        result["source_ref"] = src
    provenance = value.get("provenance")
    if isinstance(provenance, Mapping):
        compact_provenance = {
            key: provenance.get(key)
            for key in (
                "declaring_type_occurrence_id",
                "source_field_occurrence_id",
                "basis",
                "does_not_imply_business_association",
            )
            if provenance.get(key) is not None
        }
        if compact_provenance:
            result["provenance"] = compact_provenance
    annotations, annotations_truncated, annotation_total = _brief_annotations(value.get("annotations"))
    if annotations:
        result["annotations"] = annotations
    if annotations_truncated:
        result["annotation_projection"] = {
            "total": annotation_total,
            "returned": len(annotations),
            "truncated": True,
        }
    return result or None


def _relationship(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in (
        "relationship_id",
        "field_occurrence_id",
        "source_field",
        "declared_type_expression",
        "target_type_occurrence_id",
        "target_fqcn",
        "target_name",
        "relationship_kind",
        "resolution_status",
        "is_inherited",
        "inherited_depth",
        "cardinality_hint",
        "cardinality_basis",
    ):
        if value.get(key) is not None:
            result[key] = value.get(key)
    provenance = value.get("provenance")
    if isinstance(provenance, Mapping):
        compact_provenance = {
            key: provenance.get(key)
            for key in (
                "basis",
                "declaration_owner_type_occurrence_id",
                "does_not_imply_business_association",
                "inherited_depth",
                "is_inherited",
            )
            if provenance.get(key) is not None
        }
        if compact_provenance:
            result["provenance"] = compact_provenance
    src = _source_ref(value.get("source_ref"))
    if src:
        result["source_ref"] = src
    source_annotations = value.get("source_field_annotations")
    if isinstance(source_annotations, Sequence) and not isinstance(source_annotations, (str, bytes)) and source_annotations:
        result["source_field_annotation_count"] = len(source_annotations)
        result["source_field_annotations_presented_via_field_entry"] = True
    return result or None


def _inheritance(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value.get(key)
        for key in (
            "inheritance_occurrence_id",
            "relation_kind",
            "declared_supertype_expression",
            "resolution_status",
            "resolved_supertype_occurrence_id",
            "resolved_fqcn",
        )
        if value.get(key) is not None
    }
    candidates = value.get("candidate_fqcns")
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        result["candidate_fqcns"] = [str(v) for v in candidates[:20]]
        if len(candidates) > 20:
            result["candidate_fqcns_truncated"] = True
    src = _source_ref(value.get("source_ref"))
    if src:
        result["source_ref"] = src
    return result or None


def _match_evidence(value: Any, *, limit: int = 5) -> tuple[list[dict[str, Any]], bool, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return [], False, 0
    raw = list(value)
    result: list[dict[str, Any]] = []
    for item in raw[:limit]:
        if not isinstance(item, Mapping):
            continue
        compact = {
            key: item.get(key)
            for key in (
                "target_kind", "match_kind", "score", "field_occurrence_id",
                "effective_field_occurrence_id", "field_name", "declared_type_expression",
                "is_inherited", "inherited_depth", "evidence_role",
            )
            if item.get(key) is not None
        }
        docs = _documentation(item.get("documentation"))
        if docs:
            compact["documentation"] = docs
        src = _source_ref(item.get("source_ref"))
        if src:
            compact["source_ref"] = src
        if compact:
            result.append(compact)
    return result, len(raw) > limit, len(raw)


def _binding_summary(value: Any, *, example_limit: int = 3) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        key: value.get(key)
        for key in (
            "incoming_relationship_count", "outgoing_relationship_count",
            "has_observed_incoming_binding", "incoming_examples_truncated",
        )
        if value.get(key) is not None
    }
    raw_examples = value.get("incoming_examples")
    if isinstance(raw_examples, Sequence) and not isinstance(raw_examples, (str, bytes)):
        examples = []
        for item in list(raw_examples)[:example_limit]:
            if not isinstance(item, Mapping):
                continue
            compact = {
                key: item.get(key)
                for key in (
                    "relationship_id", "source_object_id", "source_fqcn", "source_name",
                    "field_occurrence_id", "source_field", "declared_type_expression",
                    "relationship_kind", "resolution_status",
                )
                if item.get(key) is not None
            }
            src = _source_ref(item.get("source_ref"))
            if src:
                compact["source_ref"] = src
            provenance = item.get("provenance")
            if isinstance(provenance, Mapping):
                compact_provenance = {
                    key: provenance.get(key)
                    for key in ("basis", "does_not_imply_business_association")
                    if provenance.get(key) is not None
                }
                if compact_provenance:
                    compact["provenance"] = compact_provenance
            if compact:
                examples.append(compact)
        result["incoming_examples"] = examples
    return result or None


def _object_card(value: Any, *, include_fields: bool, field_limit: int = 12) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}, {"projection_truncated": False}
    result: dict[str, Any] = {}
    for key in (
        "object_id",
        "repo_id",
        "fqcn",
        "name",
        "package_name",
        "type_kind",
        "source_set",
        "field_count",
        "relationship_count",
        "retrieval_score",
        "score_basis",
    ):
        if value.get(key) is not None:
            result[key] = value.get(key)
    docs = _documentation(value.get("documentation"))
    if docs:
        result["documentation"] = docs
    src = _source_ref(value.get("source_ref"))
    if src:
        result["source_ref"] = src
    annotations, annotations_truncated, annotation_total = _brief_annotations(value.get("annotations"))
    if annotations:
        result["annotations"] = annotations
    matches, matches_truncated, match_total = _match_evidence(value.get("match_evidence"))
    if matches:
        result["match_evidence"] = matches
    if value.get("match_evidence_truncated") or matches_truncated:
        result["match_evidence_truncated"] = True
    binding = _binding_summary(value.get("binding_summary"))
    if binding:
        result["binding_summary"] = binding

    source_field_total = len(value.get("fields") or ()) if isinstance(value.get("fields"), Sequence) else 0
    projection = {
        "fields_source_total": source_field_total,
        "fields_returned": 0,
        "fields_truncated": bool(source_field_total and not include_fields),
        "fields_omitted_for_discovery": bool(source_field_total and not include_fields),
        "annotations_source_total": annotation_total,
        "annotations_returned": len(annotations),
        "annotations_truncated": annotations_truncated,
        "match_evidence_source_total": match_total,
        "match_evidence_returned": len(matches),
        "match_evidence_truncated": bool(value.get("match_evidence_truncated") or matches_truncated),
    }
    if include_fields and isinstance(value.get("fields"), Sequence):
        raw_fields = value.get("fields") or ()
        fields = [item for item in (_field(v) for v in raw_fields[:field_limit]) if item]
        if fields:
            result["fields"] = fields
        projection["fields_returned"] = len(fields)
        projection["fields_truncated"] = len(raw_fields) > field_limit
    return result, projection


def _compact_declared_search(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    items = result.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        items = ()
    # Discovery views intentionally keep all returned object cards, but if a caller
    # asks for fields on a broad search each card exposes only a bounded field sample.
    raw_includes_fields = any(
        isinstance(item, Mapping) and isinstance(item.get("fields"), Sequence) and bool(item.get("fields"))
        for item in items
    )
    include_fields = False
    item_limit = 40
    compact_items: list[dict[str, Any]] = []
    item_projections: list[dict[str, Any]] = []
    for raw in items[:item_limit]:
        card, projection = _object_card(raw, include_fields=include_fields)
        compact_items.append(card)
        item_projections.append({"object_id": card.get("object_id"), **projection})
    compact = {
        key: result.get(key)
        for key in (
            "schema_version",
            "declared_model_query_schema_version",
            "declared_model_schema_version",
            "system_id",
            "revision_id",
            "filters",
            "page",
        )
        if result.get(key) is not None
    }
    compact["items"] = compact_items
    page = result.get("page") if isinstance(result.get("page"), Mapping) else {}
    total = page.get("total")
    offset = page.get("offset", 0)
    returned = len(items)
    continuation = bool(isinstance(total, int) and isinstance(offset, int) and offset + returned < total)
    field_truncated = any(bool(v.get("fields_truncated")) for v in item_projections)
    item_truncated = len(items) > item_limit
    view = {
        "projection": "declared_object_discovery_cards",
        "source_items_returned": returned,
        "source_items_total": total,
        "items_presented": len(compact_items),
        "item_limit": item_limit,
        "items_truncated": item_truncated,
        "continuation_available": continuation or item_truncated,
        "field_projection": "omitted_for_discovery_use_exact_object",
        "source_included_fields": raw_includes_fields,
        "field_limit_per_object": 0,
        "field_truncation_present": field_truncated,
        "item_projections": item_projections,
        "projection_truncated": field_truncated or item_truncated,
        "source_has_more": continuation,
    }
    return compact, view


def _compact_declared_object(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = result.get("object")
    if not isinstance(raw, Mapping):
        return dict(result), {"projection": "identity", "projection_truncated": False}
    obj: dict[str, Any] = {}
    for key in (
        "object_id",
        "repo_id",
        "fqcn",
        "name",
        "package_name",
        "type_kind",
        "source_set",
        "modifier_tokens",
        "type_parameters",
    ):
        if raw.get(key) is not None:
            obj[key] = raw.get(key)
    docs = _documentation(raw.get("documentation"))
    if docs:
        obj["documentation"] = docs
    src = _source_ref(raw.get("source_ref"))
    if src:
        obj["source_ref"] = src
    annotations, annotations_truncated, annotation_total = _annotations(raw.get("annotations"))
    if annotations:
        obj["annotations"] = annotations
    binding = _binding_summary(raw.get("binding_summary"))
    if binding:
        obj["binding_summary"] = binding

    raw_fields = raw.get("fields") if isinstance(raw.get("fields"), Sequence) else ()
    fields = [item for item in (_field(v) for v in raw_fields) if item]
    obj["fields"] = fields
    raw_relationships = raw.get("relationships") if isinstance(raw.get("relationships"), Sequence) else ()
    relationships = [item for item in (_relationship(v) for v in raw_relationships) if item]
    obj["relationships"] = relationships
    raw_inheritance = raw.get("inheritance") if isinstance(raw.get("inheritance"), Sequence) else ()
    inheritance = [item for item in (_inheritance(v) for v in raw_inheritance) if item]
    obj["inheritance"] = inheritance

    compact = {
        key: result.get(key)
        for key in (
            "schema_version",
            "declared_model_query_schema_version",
            "declared_model_schema_version",
            "system_id",
            "revision_id",
        )
        if result.get(key) is not None
    }
    compact["object"] = obj
    view = {
        "projection": "declared_object_complete_compact_structure",
        "fields_source_total": len(raw_fields),
        "fields_presented": len(fields),
        "relationships_source_total": len(raw_relationships),
        "relationships_presented": len(relationships),
        "inheritance_source_total": len(raw_inheritance),
        "inheritance_presented": len(inheritance),
        "annotations_source_total": annotation_total,
        "annotations_presented": len(annotations),
        "annotations_truncated": annotations_truncated,
        "fields_truncated": False,
        "relationships_truncated": False,
        "projection_truncated": annotations_truncated,
        "omitted_detail": [
            "annotation.structured_arguments.expression_tree",
            "duplicate/full provenance detail beyond stable ids/basis",
            "relationship.source_field_annotations duplicated by complete field entries",
        ],
    }
    return compact, view


def model_result_view(tool_response: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded LLM-facing representation of one raw tool response.

    Unknown tools use an identity result projection so the mechanism is universal
    without silently changing semantics for products that do not yet have a compact
    view.  The raw response must be retained by the caller for provenance/trace.
    """
    request = tool_response.get("request")
    tool = str(request.get("tool") or "") if isinstance(request, Mapping) else ""
    raw_result = tool_response.get("result")
    if not isinstance(raw_result, Mapping):
        raw_result = {}

    if tool == "search_declared_data_objects":
        compact_result, view = _compact_declared_search(raw_result)
    elif tool == "get_declared_data_object":
        compact_result, view = _compact_declared_object(raw_result)
    else:
        compact_result = dict(raw_result)
        view = {"projection": "identity", "projection_truncated": False}

    return {
        "schema_version": MODEL_RESULT_VIEW_SCHEMA,
        "source_tool_response_schema_version": tool_response.get("schema_version"),
        "request": dict(request) if isinstance(request, Mapping) else {},
        "status": tool_response.get("status"),
        "result": compact_result,
        "view": {
            **view,
            "raw_result_preserved_outside_llm_context": True,
        },
        "warnings": list(tool_response.get("warnings") or ()),
    }


BATCH_MODEL_RESULT_VIEW_SCHEMA = "knowledge_integration_batch_model_result_view/v1"


def batch_model_result_view(model_views: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge model-facing views for independent tool calls in one Assistant step.

    The raw responses remain separately retained by the Assistant trace.  When every
    call is ``search_declared_data_objects`` this function deterministically de-duplicates
    discovery cards by observed object identity and records which lexical query exposed
    each candidate.  No semantic score or business interpretation is introduced.
    """
    views = [dict(value) for value in model_views if isinstance(value, Mapping)]
    tools = [
        str((value.get("request") or {}).get("tool") or "")
        if isinstance(value.get("request"), Mapping) else ""
        for value in views
    ]
    if views and all(tool == "search_declared_data_objects" for tool in tools):
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        calls: list[dict[str, Any]] = []
        projection_truncated = False
        source_has_more = False
        for index, value in enumerate(views, start=1):
            request = value.get("request") if isinstance(value.get("request"), Mapping) else {}
            arguments = request.get("arguments") if isinstance(request.get("arguments"), Mapping) else {}
            query = _text(arguments.get("search"), limit=240)
            task_ref = _text(value.get("assistant_task_ref"), limit=120)
            result = value.get("result") if isinstance(value.get("result"), Mapping) else {}
            items = result.get("items") if isinstance(result.get("items"), Sequence) and not isinstance(result.get("items"), (str, bytes)) else ()
            meta = value.get("view") if isinstance(value.get("view"), Mapping) else {}
            projection_truncated = projection_truncated or bool(meta.get("projection_truncated"))
            source_has_more = source_has_more or bool(meta.get("source_has_more"))
            calls.append({
                "call_index": index,
                "search": query,
                "task_ref": task_ref,
                "status": value.get("status"),
                "source_items_total": meta.get("source_items_total"),
                "source_items_returned": meta.get("source_items_returned"),
                "items_presented": meta.get("items_presented"),
                "source_has_more": bool(meta.get("source_has_more")),
                "projection_truncated": bool(meta.get("projection_truncated")),
            })
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                identity = str(item.get("object_id") or item.get("fqcn") or "").strip()
                if not identity:
                    identity = f"call-{index}-item-{len(order)+1}"
                if identity not in merged:
                    card = dict(item)
                    card["matched_queries"] = []
                    card["matched_searches"] = []
                    merged[identity] = card
                    order.append(identity)
                else:
                    existing = merged[identity]
                    prior_queries = list(existing.get("matched_queries") or ())
                    prior_searches = list(existing.get("matched_searches") or ())
                    prior_evidence = list(existing.get("match_evidence") or ())
                    if int(item.get("retrieval_score") or 0) > int(existing.get("retrieval_score") or 0):
                        card = dict(item)
                        card["matched_queries"] = prior_queries
                        card["matched_searches"] = prior_searches
                        merged[identity] = card
                    existing_evidence = prior_evidence
                    for ev in merged[identity].get("match_evidence") or ():
                        if ev not in existing_evidence:
                            existing_evidence.append(ev)
                    seen_evidence = {
                        (ev.get("target_kind"), ev.get("match_kind"), ev.get("field_occurrence_id"), ev.get("field_name"))
                        for ev in existing_evidence if isinstance(ev, Mapping)
                    }
                    for ev in item.get("match_evidence") or ():
                        if not isinstance(ev, Mapping):
                            continue
                        key = (ev.get("target_kind"), ev.get("match_kind"), ev.get("field_occurrence_id"), ev.get("field_name"))
                        if key not in seen_evidence:
                            existing_evidence.append(dict(ev))
                            seen_evidence.add(key)
                    existing_evidence.sort(key=lambda ev: (-int(ev.get("score") or 0), str(ev.get("match_kind") or ""), str(ev.get("field_name") or "")))
                    if existing_evidence:
                        merged[identity]["match_evidence"] = existing_evidence[:5]
                        if len(existing_evidence) > 5:
                            merged[identity]["match_evidence_truncated"] = True
                matched = merged[identity].setdefault("matched_queries", [])
                if query and query not in matched:
                    matched.append(query)
                matched_searches = merged[identity].setdefault("matched_searches", [])
                descriptor = {"search": query, "task_ref": task_ref}
                if descriptor not in matched_searches:
                    matched_searches.append(descriptor)
        order.sort(key=lambda key: (
            -int(merged[key].get("retrieval_score") or 0),
            str(merged[key].get("fqcn") or "").lower(),
            key,
        ))
        return {
            "schema_version": BATCH_MODEL_RESULT_VIEW_SCHEMA,
            "batch_kind": "independent_tool_calls",
            "tool": "search_declared_data_objects",
            "calls": calls,
            "result": {"items": [merged[key] for key in order]},
            "view": {
                "projection": "declared_object_discovery_batch_merge",
                "source_call_count": len(views),
                "items_presented_unique": len(order),
                "projection_truncated": projection_truncated,
                "source_has_more": source_has_more,
                "raw_results_preserved_outside_llm_context": True,
                "deduplication_key": "object_id_then_fqcn",
            },
        }

    return {
        "schema_version": BATCH_MODEL_RESULT_VIEW_SCHEMA,
        "batch_kind": "independent_tool_calls",
        "results": views,
        "view": {
            "projection": "batch_of_model_result_views",
            "source_call_count": len(views),
            "projection_truncated": any(
                bool((value.get("view") or {}).get("projection_truncated"))
                for value in views if isinstance(value.get("view"), Mapping)
            ),
            "source_has_more": any(
                bool((value.get("view") or {}).get("source_has_more"))
                for value in views if isinstance(value.get("view"), Mapping)
            ),
            "raw_results_preserved_outside_llm_context": True,
        },
    }
