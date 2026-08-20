from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text

_DETAIL_LIMIT = 20
_CATALOG_LIMIT = 20_000


def _annotation_names(item: Mapping[str, Any]) -> list[str]:
    return sorted({str(v.get("annotation_name") or "") for v in (item.get("annotations") or ()) if isinstance(v, Mapping) and str(v.get("annotation_name") or "")})


def _compact_object(item: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = item.get("source_ref") if isinstance(item.get("source_ref"), Mapping) else {}
    documentation = item.get("documentation") if isinstance(item.get("documentation"), Mapping) else {}
    binding = item.get("binding_summary") if isinstance(item.get("binding_summary"), Mapping) else {}
    return {
        "object_id": str(item.get("object_id") or ""),
        "repo_id": str(item.get("repo_id") or ""),
        "fqcn": str(item.get("fqcn") or ""),
        "name": str(item.get("name") or ""),
        "package_name": str(item.get("package_name") or ""),
        "type_kind": str(item.get("type_kind") or ""),
        "source_set": str(item.get("source_set") or ""),
        "field_count": int(item.get("field_count") or 0),
        "relationship_count": int(item.get("relationship_count") or 0),
        "incoming_relationship_count": int(binding.get("incoming_relationship_count") or 0),
        "annotations": _annotation_names(item),
        "display_name": str(documentation.get("display_name") or documentation.get("summary") or ""),
        "source_ref": {
            "repository_relative_path": str(source_ref.get("repository_relative_path") or ""),
            "line_start": source_ref.get("line_start"),
            "line_end": source_ref.get("line_end"),
            "extractor": str(source_ref.get("extractor") or ""),
        },
    }


def _structural_rank(item: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
    documentation = item.get("documentation") if isinstance(item.get("documentation"), Mapping) else {}
    return (
        1 if documentation else 0,
        len(item.get("annotations") or ()),
        int(item.get("relationship_count") or 0) + int(((item.get("binding_summary") or {}).get("incoming_relationship_count") or 0)),
        int(item.get("field_count") or 0),
        str(item.get("fqcn") or ""),
    )


def _compact_field(field: Mapping[str, Any]) -> dict[str, Any]:
    doc = field.get("documentation") if isinstance(field.get("documentation"), Mapping) else {}
    src = field.get("source_ref") if isinstance(field.get("source_ref"), Mapping) else {}
    return {
        "name": str(field.get("name") or ""),
        "declared_type_expression": str(field.get("declared_type_expression") or ""),
        "is_inherited": bool(field.get("is_inherited")),
        "inherited_depth": int(field.get("inherited_depth") or 0),
        "documentation": {key: doc.get(key) for key in ("summary", "display_name", "description") if doc.get(key) is not None},
        "annotations": _annotation_names(field),
        "source_ref": {
            "repository_relative_path": str(src.get("repository_relative_path") or ""),
            "line_start": src.get("line_start"),
            "line_end": src.get("line_end"),
        },
    }


def _compact_relationship(rel: Mapping[str, Any]) -> dict[str, Any]:
    target = rel.get("target") if isinstance(rel.get("target"), Mapping) else {}
    declared = rel.get("declared_relationship") if isinstance(rel.get("declared_relationship"), Mapping) else {}
    storage = rel.get("storage_semantics") if isinstance(rel.get("storage_semantics"), Mapping) else {}
    physical = rel.get("physical_mapping") if isinstance(rel.get("physical_mapping"), Mapping) else {}
    candidates = []
    for candidate in storage.get("candidate_mappings") or ():
        if not isinstance(candidate, Mapping):
            continue
        candidates.append({
            "knowledge_class": candidate.get("knowledge_class"),
            "mapping_status": candidate.get("mapping_status"),
            "target_alignment": candidate.get("target_alignment"),
            "storage_relation_kind": candidate.get("storage_relation_kind"),
            "storage_key_expression": candidate.get("storage_key_expression"),
            "basis": candidate.get("mapping_basis"),
            "repo_id": candidate.get("storage_repo_id"),
        })
    reference_derivations = []
    for derivation in storage.get("reference_value_derivations") or ():
        if not isinstance(derivation, Mapping):
            continue
        reference_derivations.append({
            "repo_id": derivation.get("repo_id"),
            "source_operation": derivation.get("source_operation"),
            "value_converter_operation": derivation.get("value_converter_operation"),
            "composed_reference_value_expression": derivation.get("composed_reference_value_expression"),
        })
    return {
        "source_field": str(rel.get("source_field") or ""),
        "declared_type_expression": declared.get("declared_type_expression"),
        "target_fqcn": target.get("fqcn"),
        "resolution_status": target.get("resolution_status") or declared.get("resolution_status"),
        "cardinality": rel.get("cardinality"),
        "storage_status": storage.get("status"),
        "storage_basis": storage.get("basis"),
        "storage_candidates": candidates,
        "reference_value_derivations": reference_derivations,
        "physical_status": physical.get("status"),
        "physical_join_confirmed": bool(physical.get("physical_join_confirmed")),
    }


def _compact_context(context: Mapping[str, Any]) -> dict[str, Any]:
    obj = context.get("object") if isinstance(context.get("object"), Mapping) else {}
    storage_context = context.get("storage_context") if isinstance(context.get("storage_context"), Mapping) else {}
    identities = []
    for item in context.get("storage_identities") or ():
        if isinstance(item, Mapping):
            identities.append({key: item.get(key) for key in ("status", "basis", "storage_alias", "storage_key_expression", "storage_repo_id") if item.get(key) is not None})
    return {
        "object": {
            **_compact_object({**obj, "field_count": len(context.get("fields") or ()), "relationship_count": len(context.get("relationships") or ())}),
            "documentation": dict(obj.get("documentation") or {}),
            "inheritance": [
                {key: item.get(key) for key in ("relation_kind", "declared_supertype_expression", "resolution_status", "resolved_fqcn") if item.get(key) is not None}
                for item in (obj.get("inheritance") or ()) if isinstance(item, Mapping)
            ],
        },
        "fields": [_compact_field(item) for item in (context.get("fields") or ()) if isinstance(item, Mapping)],
        "relationships": [_compact_relationship(item) for item in (context.get("relationships") or ()) if isinstance(item, Mapping)],
        "storage_identities": identities,
        "storage_context": dict(storage_context),
        "gaps": list(context.get("gaps") or ()),
    }


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("declared-data-model-report/v1 requires a resolved Knowledge API revision")

    pinned = source.client.revision(source.system_id, source.revision_id)
    summary = pinned.declared_data_model_summary()
    objects = pinned.search_declared_data_objects(include_fields=False, max_results=_CATALOG_LIMIT)
    compact_catalog = [_compact_object(item) for item in objects]

    repo_counts = Counter(str(item.get("repo_id") or "") for item in objects if str(item.get("repo_id") or ""))
    kind_counts = Counter(str(item.get("type_kind") or "") for item in objects if str(item.get("type_kind") or ""))
    source_set_counts = Counter(str(item.get("source_set") or "") for item in objects if str(item.get("source_set") or ""))

    selected: list[Mapping[str, Any]] = []
    selected_ids: set[str] = set()
    for focus in request.focus:
        for item in pinned.search_declared_data_objects(search=focus, include_fields=False, max_results=20):
            oid = str(item.get("object_id") or "")
            if oid and oid not in selected_ids:
                selected.append(item); selected_ids.add(oid)
            if len(selected) >= _DETAIL_LIMIT:
                break
        if len(selected) >= _DETAIL_LIMIT:
            break

    if len(selected) < _DETAIL_LIMIT:
        for item in sorted(objects, key=_structural_rank, reverse=True):
            oid = str(item.get("object_id") or "")
            if oid and oid not in selected_ids:
                selected.append(item); selected_ids.add(oid)
            if len(selected) >= _DETAIL_LIMIT:
                break

    detailed = []
    relationship_storage_status = Counter()
    physical_status = Counter()
    storage_context_status = Counter()
    gap_count = 0
    for item in selected:
        context = pinned.get_data_model_object_context(str(item.get("object_id") or ""))
        compact = _compact_context(context)
        detailed.append(compact)
        storage_context_status[str((compact.get("storage_context") or {}).get("status") or "unknown")] += 1
        gap_count += len(compact.get("gaps") or ())
        for relationship in compact.get("relationships") or ():
            relationship_storage_status[str(relationship.get("storage_status") or "not_observed")] += 1
            physical_status[str(relationship.get("physical_status") or "not_observed")] += 1

    capabilities = list(source.capabilities)
    storage_caps = [cap for cap in capabilities if cap in {"common.model-storage-semantics", "common.logical-storage-mapping"}]
    counts = dict(summary.get("counts") or {})
    observed_total = len(objects)
    declared_total = int(counts.get("type_count") or observed_total)

    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": {
            "kind": str((source.revision.get("execution") or {}).get("scope_kind") or "repository"),
            "id": source.system_id,
            "revision_id": source.revision_id,
            "repository_counts": dict(sorted(repo_counts.items())),
        },
        "audience_policy": {
            "language": "ru",
            "fact_boundary": "Only declared-model facts and explicitly published optional storage semantics may be stated as facts.",
        },
        "report_blueprint": {
            "required_sections": [
                "Краткий вывод",
                "Состав объявленной модели",
                "Каталог объектов",
                "Ключевые объекты и поля",
                "Объявленные связи",
                "Наблюдаемая storage-семантика",
                "Неоднозначности и пробелы",
                "Технические доказательства и provenance",
            ]
        },
        "coverage": {
            "declared_model_build": dict(summary.get("build") or {}),
            "counts": counts,
            "catalog_objects_returned": observed_total,
            "catalog_complete_against_summary": observed_total == declared_total,
            "detail_object_count": len(detailed),
            "detail_selection_limit": _DETAIL_LIMIT,
            "gap_counts": list(summary.get("gap_counts") or ()),
            "detail_gap_count": gap_count,
            "capabilities": capabilities,
            "optional_storage_capabilities_published": storage_caps,
        },
        "sections": {
            "model_summary": {
                "counts": counts,
                "type_annotation_counts": list(summary.get("type_annotation_counts") or ()),
                "field_annotation_counts": list(summary.get("field_annotation_counts") or ()),
                "gap_counts": list(summary.get("gap_counts") or ()),
                "repository_counts": dict(sorted(repo_counts.items())),
                "type_kind_counts": dict(sorted(kind_counts.items())),
                "source_set_counts": dict(sorted(source_set_counts.items())),
            },
            "complete_object_catalog": compact_catalog,
            "detailed_objects": detailed,
            "storage_observation_summary": {
                "storage_context_status_counts": dict(sorted(storage_context_status.items())),
                "relationship_storage_status_counts": dict(sorted(relationship_storage_status.items())),
                "physical_mapping_status_counts": dict(sorted(physical_status.items())),
            },
            "technical_appendix": {
                "revision_id": source.revision_id,
                "artifact_id": (source.selected_artifact or {}).get("artifact_id"),
                "selected_model_kind": (source.selected_artifact or {}).get("model_kind"),
                "selected_schema_version": (source.selected_artifact or {}).get("schema_version"),
                "capabilities": capabilities,
            },
        },
        "evidence_index": {},
        "interpretation_policy": {
            "declared_relationship": "A resolved declared field type reference is structural evidence and does not by itself prove a business association or physical foreign key.",
            "storage_semantics": "Storage semantics are included only when the corresponding optional AISL capabilities are published; ambiguous candidates remain ambiguous.",
            "physical_mapping": "No physical SQL/PDM join may be asserted unless the published object-context explicitly confirms it.",
            "catalog_detail": "The compact object catalog is exhaustive when catalog_complete_against_summary=true; detailed object contexts are a deterministic bounded selection and are not exhaustive.",
            "absence": "Absence from a bounded detail selection is not evidence that an object or relationship is absent from the published declared model.",
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
