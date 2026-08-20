from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


_DETAIL_LIMITS = {
    "executive": {"top_sources": 15, "profile_items": 15},
    "standard": {"top_sources": 40, "profile_items": 50},
    "detailed": {"top_sources": 80, "profile_items": 100},
}


@lru_cache(maxsize=1)
def _audience_policies() -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(Path(__file__).with_name("audience-policy.yaml").read_text(encoding="utf-8")) or {}
    required = {"business", "architecture", "engineering"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"sql source inventory audience policy is incomplete: {missing}")
    return {str(key): dict(value or {}) for key, value in payload.items()}


def _matches_focus(item: Mapping[str, Any], terms: tuple[str, ...]) -> bool:
    if not terms:
        return True
    text = canonical_json(item).casefold()
    return any(term.casefold() in text for term in terms)




def _evidence_refs(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(ref) for ref in (value.get("evidence_refs") or ()) if isinstance(ref, Mapping)]


def _evidence_ids(value: Mapping[str, Any]) -> list[str]:
    return [
        str(ref.get("evidence_id"))
        for ref in _evidence_refs(value)
        if str(ref.get("evidence_id") or "").strip()
    ]


def _evidence_index(items: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        for ref in _evidence_refs(item):
            evidence_id = str(ref.get("evidence_id") or "").strip()
            if evidence_id:
                result[evidence_id] = ref
        for field in item.get("fields") or ():
            if not isinstance(field, Mapping):
                continue
            for ref in _evidence_refs(field):
                evidence_id = str(ref.get("evidence_id") or "").strip()
                if evidence_id:
                    result[evidence_id] = ref
    return result

def _compact_coverage(raw: Mapping[str, Any]) -> dict[str, Any]:
    repositories = list(raw.get("repositories") or ())
    repo_coverages = []
    for repository in repositories:
        coverage = dict(repository.get("coverage_json") or {})
        source = dict(((coverage.get("column_usages") or {}).get("source_inventory") or {}))
        gaps = dict(coverage.get("gaps") or {})
        repo_coverages.append({
            "repo_id": repository.get("repo_id"),
            "analysis_status": repository.get("analysis_status"),
            "source_content_fingerprint": repository.get("source_content_fingerprint"),
            "source_inventory": source,
            "lineage_gaps": gaps,
        })
    return {
        "analysis_status": raw.get("analysis_status"),
        "repositories": repo_coverages,
    }


def _compact_field(field: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": field.get("name"),
        "usage_roles": list(field.get("usage_roles") or ()),
        "occurrence_count": int(field.get("occurrence_count") or 0),
        "statement_count": int(field.get("statement_count") or 0),
    }


def _compact_source(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relation_id": item.get("relation_id"),
        "repo_id": item.get("repo_id"),
        "relation_identity": item.get("relation_identity"),
        "relation_kind": item.get("relation_kind"),
        "usage_roles": list(item.get("usage_roles") or ()),
        "occurrence_count": int(item.get("occurrence_count") or 0),
        "statement_count": int(item.get("statement_count") or 0),
        "field_count": int(item.get("field_count") or len(item.get("fields") or ())),
        "fields": [_compact_field(field) for field in (item.get("fields") or ())],
    }


def _with_examples(item: Mapping[str, Any], *, max_fields: int = 12) -> dict[str, Any]:
    result = _compact_source(item)
    result["evidence_ids"] = _evidence_ids(item)[:3]
    fields = []
    for field in item.get("fields") or ():
        value = _compact_field(field)
        value["evidence_ids"] = _evidence_ids(field)[:1]
        fields.append(value)
        if len(fields) >= max_fields:
            break
    result["field_examples"] = fields
    result.pop("fields", None)
    return result


def _role_statistics(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    distinct_field_counts: Counter[str] = Counter()
    field_occurrences: Counter[str] = Counter()
    for item in items:
        for role in item.get("usage_roles") or ():
            source_counts[str(role)] += 1
        for field in item.get("fields") or ():
            for role in field.get("usage_roles") or ():
                distinct_field_counts[str(role)] += 1
                field_occurrences[str(role)] += int((field.get("evidence_count_by_role") or {}).get(role) or 0)
    return {
        "source_count_by_role": dict(sorted(source_counts.items())),
        "distinct_field_count_by_role": dict(sorted(distinct_field_counts.items())),
        "field_occurrence_count_by_role": dict(sorted(field_occurrences.items())),
    }


def _source_profiles(items: list[dict[str, Any]]) -> dict[str, Any]:
    join_or_filter_only = []
    projection_sources = []
    high_reuse = []
    for item in items:
        field_roles = {str(role) for field in item.get("fields") or () for role in (field.get("usage_roles") or ())}
        compact = {
            "relation_id": item.get("relation_id"),
            "relation_identity": item.get("relation_identity"),
            "field_count": int(item.get("field_count") or 0),
            "occurrence_count": int(item.get("occurrence_count") or 0),
            "statement_count": int(item.get("statement_count") or 0),
        }
        if field_roles and field_roles <= {"join", "filter"}:
            join_or_filter_only.append(compact)
        if "projection" in field_roles:
            projection_sources.append(compact)
        if compact["statement_count"] >= 5:
            high_reuse.append(compact)
    rank = lambda value: (-int(value.get("statement_count") or 0), -int(value.get("field_count") or 0), str(value.get("relation_identity") or ""))
    return {
        "join_or_filter_only": sorted(join_or_filter_only, key=rank),
        "projection_sources": sorted(projection_sources, key=rank),
        "high_reuse_sources": sorted(high_reuse, key=rank),
    }



def _source_catalog_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build deterministic navigation groups without replacing the complete catalog."""

    def schema_or_prefix(item: Mapping[str, Any]) -> str:
        identity = str(item.get("relation_identity") or "").strip()
        if not identity:
            return "unknown"
        if "." in identity:
            return identity.rsplit(".", 1)[0]
        if "/" in identity:
            return identity.rsplit("/", 1)[0]
        return "unqualified"

    dimensions = {
        "by_repository": lambda item: str(item.get("repo_id") or "unknown"),
        "by_relation_kind": lambda item: str(item.get("relation_kind") or "unknown"),
        "by_schema_or_prefix": schema_or_prefix,
    }
    result: dict[str, list[dict[str, Any]]] = {}
    for dimension, key_fn in dimensions.items():
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(key_fn(item), []).append(item)
        rows = []
        for key in sorted(grouped):
            values = sorted(grouped[key], key=lambda item: str(item.get("relation_identity") or ""))
            rows.append({
                "group": key,
                "source_count": len(values),
                "used_field_count": sum(len(item.get("fields") or ()) for item in values),
                "sources": [str(item.get("relation_identity") or "") for item in values],
                "complete_group_catalog": True,
            })
        result[dimension] = rows
    return result

def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("sql source inventory report requires a resolved Knowledge API revision")
    if "common.sql-source-inventory" not in set(source.capabilities):
        raise ValueError("profile sql-source-inventory-report/v1 requires capability common.sql-source-inventory")

    payload = source.client.get_json(
        f"/api/knowledge/v1/systems/{source.system_id}/sql/source-inventory",
        params={
            "revision_id": source.revision_id,
            "view": "business_sources",
            "max_evidence_per_role": 3,
        },
    )
    all_items = [dict(item) for item in (payload.get("items") or ()) if isinstance(item, Mapping)]
    selected = [item for item in all_items if _matches_focus(item, request.focus)]
    focus_status = "applied" if request.focus else "not_requested"
    if request.focus and not selected:
        selected = all_items
        focus_status = "no_exact_match_fallback_to_full_inventory"

    compact_catalog = [_compact_source(item) for item in selected]
    detail_limits = _DETAIL_LIMITS[request.detail_level]
    ranked = sorted(
        selected,
        key=lambda item: (
            -int(item.get("field_count") or 0),
            -int(item.get("statement_count") or 0),
            -int(item.get("occurrence_count") or 0),
            str(item.get("relation_identity") or ""),
        ),
    )
    top_sources = [_with_examples(item) for item in ranked[: detail_limits["top_sources"]]]
    profiles = _source_profiles(selected)
    for key in profiles:
        profiles[key] = profiles[key][: detail_limits["profile_items"]]

    all_evidence = _evidence_index(selected)
    selected_evidence_ids: set[str] = set()
    for item in top_sources:
        selected_evidence_ids.update(str(value) for value in (item.get("evidence_ids") or ()) if value)
        for field in item.get("field_examples") or ():
            selected_evidence_ids.update(str(value) for value in (field.get("evidence_ids") or ()) if value)
    evidence_payload = (
        {key: all_evidence[key] for key in sorted(selected_evidence_ids) if key in all_evidence}
        if request.include_evidence
        else {}
    )

    field_count = sum(len(item.get("fields") or ()) for item in selected)
    relation_evidence_count = sum(int(item.get("evidence_count") or 0) for item in selected)
    field_evidence_count = sum(
        int(field.get("evidence_count") or 0)
        for item in selected
        for field in (item.get("fields") or ())
        if isinstance(field, Mapping)
    )
    coverage = _compact_coverage(dict(payload.get("coverage") or {}))
    execution = dict(source.revision.get("execution") or {})
    repository_ids = sorted({str(item.get("repo_id")) for item in selected if item.get("repo_id")})

    sections = {
        "summary": {
            "source_count": len(selected),
            "used_field_count": field_count,
            "complete_source_catalog": True,
            "complete_field_catalog": True,
            "relation_evidence_count": relation_evidence_count,
            "field_evidence_count": field_evidence_count,
            "inventory_schema_version": payload.get("inventory_schema_version"),
            "view": dict(payload.get("filters") or {}).get("view"),
            "focus_status": focus_status,
        },
        "source_inventory": {
            "items": compact_catalog,
            "top_sources": top_sources,
            "catalog_groups": _source_catalog_groups(selected),
            "complete_source_catalog": True,
            "complete_field_catalog": True,
            "selection_policy": "complete-business-source-catalog-plus-ranked-evidence/v1",
        },
        "usage_analysis": {
            "roles": _role_statistics(selected),
            "source_profiles": profiles,
        },
        "limitations": {
            "coverage": coverage,
            "statement": "Unmapped or ambiguous field usages remain coverage limitations and are not assigned to a source relation by this report.",
        },
        "technical_appendix": {
            "source_references": [evidence_payload[key] for key in sorted(evidence_payload)[:80]],
            "revision_id": source.revision_id,
            "artifact_id": (source.selected_artifact or {}).get("artifact_id"),
            "scope_limit": f"Inventory is limited to external physical and physical-template SQL sources observed in published revision {source.revision_id} of system {source.system_id}.",
        },
    }

    required_sections = [
        "Краткий вывод",
        "Источники данных витрины",
        "Используемые поля",
        "Характер использования",
        "Основные зависимости и паттерны использования",
        "Приложение A. Полнота анализа и ограничения доказательности",
        "Приложение B. Неоднозначности и вопросы для уточнения",
        "Приложение C. Технические доказательства и provenance",
    ]
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": {
            "kind": str(execution.get("scope_kind") or "repository"),
            "id": source.system_id,
            "repository_ids": repository_ids,
        },
        "audience_policy": _audience_policies()[request.audience],
        "report_blueprint": {
            "required_sections": required_sections,
            "complete_catalog_requirement": "For standard and detailed reports include every source relation and all deterministically bound fields from sections.source_inventory.items; use catalog_groups only for navigation, never as a replacement for the complete catalog.",
            "evidence_requirement": "Use evidence only from evidence_index; the complete compact catalog intentionally omits per-row evidence to keep the dataset bounded.",
        },
        "coverage": {
            "source_count": len(selected),
            "used_field_count": field_count,
            "relation_evidence_count": relation_evidence_count,
            "field_evidence_count": field_evidence_count,
            "analysis": coverage,
            "focus_status": focus_status,
        },
        "sections": sections,
        "evidence_index": evidence_payload,
        "interpretation_policy": {
            "resolved_source_fields": "May be stated as observed facts tied to a source relation.",
            "unmapped_fields": "Must remain limitations and must not be assigned or semantically classified.",
            "technical_intermediates": "Are excluded from the business source inventory by the canonical business_sources view.",
            "business_meaning": "Human-readable grouping or purpose is interpretation and must be labelled accordingly.",
            "missing_runtime_facts": ["owners", "SLA", "runtime volumes", "production freshness", "runtime topology"],
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
