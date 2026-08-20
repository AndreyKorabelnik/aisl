from __future__ import annotations

from typing import Any, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


def _compact_evidence_ref(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Keep a human-readable provenance pointer without transport-local identifiers."""
    result: dict[str, Any] = {}
    for key in ("file", "line_start", "usage_role"):
        value = raw.get(key)
        if value is not None and value != "":
            result[key] = value
    return result


def _compact_field(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve every observed field and aggregate evidence counts in a bounded form."""
    return {
        "name": raw.get("name"),
        "usage_roles": list(raw.get("usage_roles") or []),
        "resolution_statuses": list(raw.get("resolution_statuses") or []),
        "occurrence_count": int(raw.get("occurrence_count") or 0),
        "statement_count": int(raw.get("statement_count") or 0),
        "evidence_count": int(raw.get("evidence_count") or 0),
        "evidence_count_by_role": dict(raw.get("evidence_count_by_role") or {}),
        "evidence_truncated": bool(raw.get("evidence_truncated")),
    }


def _compact_relation(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Project one full source-inventory relation into the report-sized contract.

    No relation or field is dropped. Repeated field-level evidence references are represented
    by exact counts; relation-level evidence keeps the already bounded human-readable sample.
    Canonical evidence remains available through the pinned Knowledge API revision.
    """
    evidence_refs = [
        compact
        for compact in (
            _compact_evidence_ref(ref)
            for ref in raw.get("evidence_refs") or []
            if isinstance(ref, Mapping)
        )
        if compact
    ]
    return {
        "relation_id": raw.get("relation_id"),
        "repo_id": raw.get("repo_id"),
        "relation_kind": raw.get("relation_kind"),
        "relation_identity": raw.get("relation_identity"),
        "template_name": raw.get("template_name"),
        "logical_name": raw.get("logical_name"),
        "resolved_names": list(raw.get("resolved_names") or []),
        "usage_roles": list(raw.get("usage_roles") or []),
        "semantic_role": raw.get("semantic_role"),
        "classification_status": raw.get("classification_status"),
        "classification_reasons": list(raw.get("classification_reasons") or []),
        "write_occurrence_count": int(raw.get("write_occurrence_count") or 0),
        "downstream_target_count": int(raw.get("downstream_target_count") or 0),
        "occurrence_count": int(raw.get("occurrence_count") or 0),
        "statement_count": int(raw.get("statement_count") or 0),
        "field_count": int(raw.get("field_count") or 0),
        "fields": [
            _compact_field(field)
            for field in raw.get("fields") or []
            if isinstance(field, Mapping)
        ],
        "evidence_count": int(raw.get("evidence_count") or 0),
        "evidence_count_by_role": dict(raw.get("evidence_count_by_role") or {}),
        "evidence_refs": evidence_refs,
        "evidence_truncated": bool(raw.get("evidence_truncated")),
    }


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("workspace SQL catalog report requires a resolved Knowledge API revision")
    if "common.workspace-sql-catalog" not in set(source.capabilities):
        raise ValueError("workspace SQL catalog capability is unavailable")

    base = f"/api/knowledge/v1/systems/{source.system_id}/sql"
    catalog = source.client.get_json(
        base + "/workspace-catalog", params={"revision_id": source.revision_id}
    )
    inventory = source.client.get_json(
        base + "/source-inventory",
        params={
            "revision_id": source.revision_id,
            "view": "business_sources",
            "max_evidence_per_role": 1,
        },
    )
    raw_inventory = [
        dict(item) for item in inventory.get("items") or [] if isinstance(item, Mapping)
    ]
    compact_inventory = [_compact_relation(item) for item in raw_inventory]
    raw_field_count = sum(len(item.get("fields") or []) for item in raw_inventory)
    compact_field_count = sum(len(item.get("fields") or []) for item in compact_inventory)

    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": {
            "kind": "workspace",
            "id": source.system_id,
            "repository_ids": list(catalog.get("repository_ids") or []),
        },
        "audience_policy": {
            "language": "ru",
            "fact_boundary": (
                "The report composes published repository SQL facts without inferring "
                "cross-repository lineage."
            ),
        },
        "report_blueprint": {
            "required_sections": [
                "Краткий вывод",
                "Состав workspace",
                "Каталог источников и назначений",
                "Покрытие по репозиториям",
                "Ограничения и provenance",
            ]
        },
        "coverage": dict(catalog.get("coverage") or {}),
        "sections": {
            "summary": {
                "repository_count": catalog.get("repository_count", 0),
                "source_artifact_count": catalog.get("source_count", 0),
                "inventory_item_count": inventory.get("item_count", 0),
                "inventory_field_count": raw_field_count,
            },
            "workspace_sources": list(catalog.get("sources") or []),
            "source_inventory": compact_inventory,
            "source_inventory_coverage": dict(inventory.get("coverage") or {}),
            "inventory_projection": {
                "schema_version": "workspace-sql-report-inventory-projection/v1",
                "relation_policy": "all_relations_preserved",
                "field_policy": "all_fields_preserved",
                "relation_evidence_policy": "one_human_readable_reference_per_usage_role",
                "field_evidence_policy": "exact_counts_without_repeated_reference_objects",
                "canonical_evidence_access": "pinned_knowledge_api_revision",
                "source_relation_count": len(raw_inventory),
                "projected_relation_count": len(compact_inventory),
                "source_field_count": raw_field_count,
                "projected_field_count": compact_field_count,
                "omitted_transport_properties": [
                    "evidence_id",
                    "query_id",
                    "scope_id",
                    "resolution_bases",
                ],
            },
            "technical_appendix": {
                "revision_id": source.revision_id,
                "artifact_id": (source.selected_artifact or {}).get("artifact_id"),
            },
        },
        "evidence_index": {},
        "interpretation_policy": {
            "composition": "No source reanalysis and no cross-repository identity inference.",
            "ambiguity": "Repository provenance is retained for every fact.",
            "inventory_projection": (
                "All relations and fields are retained; repeated transport-level evidence "
                "objects are compacted without changing aggregate evidence counts."
            ),
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
