from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


def _referenced_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_ids" and isinstance(item, list):
                found.update(str(v) for v in item if str(v))
            else:
                found.update(_referenced_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_referenced_evidence_ids(item))
    return found


def _merge_evidence(results: Iterable[Mapping[str, Any]], referenced_ids: set[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for result in results:
        for ref in result.get("evidence") or ():
            if not isinstance(ref, Mapping):
                continue
            evidence_id = str(ref.get("evidence_id") or "")
            if evidence_id and evidence_id in referenced_ids:
                index[evidence_id] = dict(ref)
    return index


def _compact_mapping(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "source_field", "source_expression", "target_field", "storage_field",
        "response_field", "mapping_status", "basis", "evidence_status",
    )
    return {key: item.get(key) for key in keys if item.get(key) not in (None, "", [], {})}


def _compact_path(item: dict[str, Any]) -> dict[str, Any]:
    source = dict(item.get("source_interpretation") or {})
    risk = dict(item.get("risk_eligibility") or {})
    same_data = dict(item.get("same_data_link") or {})
    return {
        "path_id": item.get("path_id"),
        "direction": item.get("direction"),
        "repo_id": item.get("repo_id"),
        "storage_object": item.get("storage_object"),
        "source_operation": item.get("source_operation"),
        "source_interpretation": {
            key: source.get(key)
            for key in ("status", "source_kind", "source_system", "business_source_decision", "reason")
            if source.get(key) not in (None, "", [], {})
        },
        "access_boundary": item.get("access_boundary"),
        "lineage_status": item.get("lineage_status"),
        "evidence_maturity_level": item.get("evidence_maturity_level"),
        "evidence_maturity_dimensions": dict(item.get("evidence_maturity_dimensions") or {}),
        "path": list(item.get("path") or ()),
        "field_mappings": [_compact_mapping(dict(v)) for v in item.get("field_mappings") or ()],
        "persistent_write_refs": list(item.get("persistent_write_refs") or ()),
        "missing_links": list(item.get("missing_links") or ()),
        "candidate_signals": list(item.get("candidate_signals") or ()),
        "risk_eligibility": {
            key: risk.get(key)
            for key in ("risk_eligible", "risk_status", "blocking_reasons")
            if risk.get(key) not in (None, "", [], {})
        },
        "same_data_link": {
            key: same_data.get(key)
            for key in ("status", "source_to_storage", "storage_to_access", "end_to_end_same_data", "unresolved_reasons")
            if same_data.get(key) not in (None, "", [], {})
        },
        "evidence_ids": list(item.get("evidence_ids") or ()),
    }


def _compact_case(item: dict[str, Any]) -> dict[str, Any]:
    source_path_id = item.get("source_path_id")
    access_path_id = item.get("access_path_id")
    if not source_path_id:
        source_path_id = next((v.get("path_id") for v in item.get("source_paths") or () if v.get("path_id")), None)
    if not access_path_id:
        access_path_id = next((v.get("path_id") for v in item.get("access_paths") or () if v.get("path_id")), None)
    return {
        "case_id": item.get("case_id"),
        "case_granularity": item.get("case_granularity"),
        "repo_id": item.get("repo_id"),
        "storage_object": item.get("storage_object"),
        "storage_field": item.get("storage_field"),
        "source_path_id": source_path_id,
        "access_path_id": access_path_id,
        "bridge_basis": item.get("bridge_basis"),
        "source_to_storage_observed": bool(item.get("source_to_storage_observed")),
        "storage_to_access_observed": bool(item.get("storage_to_access_observed")),
        "same_data_field_overlap": list(item.get("same_data_field_overlap") or ()),
        "same_data_end_to_end_status": item.get("same_data_end_to_end_status"),
        "business_fdp_decision": item.get("business_fdp_decision"),
        "risk_decision": item.get("risk_decision"),
        "missing_links": list(item.get("missing_links") or ()),
        "evidence_ids": list(item.get("evidence_ids") or ()),
    }


_MAX_REPORT_PATHS = 120
_MAX_REPORT_CASES = 160
_MAX_GAP_ITEMS = 80



def _selected_report_paths(paths: list[dict[str, Any]], cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Choose a deterministic, business-useful excerpt within the report budget.

    Full path counts remain in coverage/summary.  The report payload prioritizes
    confirmed same-data cases, then confirmed evidence and source-interpreted
    paths.  This avoids silently dropping the strongest cases while preventing
    large repositories from overflowing the renderer contract.
    """
    confirmed_case_ids: set[str] = set()
    connected_case_ids: set[str] = set()
    for case in cases:
        ids = {str(v) for v in (case.get("source_path_id"), case.get("access_path_id")) if str(v or "")}
        if case.get("source_to_storage_observed") and case.get("storage_to_access_observed"):
            connected_case_ids.update(ids)
        if case.get("same_data_end_to_end_status") == "confirmed":
            confirmed_case_ids.update(ids)

    def priority(item: dict[str, Any]) -> tuple[Any, ...]:
        path_id = str(item.get("path_id") or "")
        source_status = str((item.get("source_interpretation") or {}).get("status") or "")
        maturity = str(item.get("evidence_maturity_level") or "unresolved")
        if path_id in confirmed_case_ids:
            rank = 0
        elif maturity == "confirmed":
            rank = 1
        elif source_status.startswith("confirmed"):
            rank = 2
        elif path_id in connected_case_ids:
            rank = 3
        else:
            rank = 4
        return (rank, str(item.get("storage_object") or ""), str(item.get("direction") or ""), path_id)

    ordered = sorted(paths, key=priority)
    selected = ordered[:_MAX_REPORT_PATHS]
    selected_ids = {str(item.get("path_id") or "") for item in selected}
    return selected, {
        "selection_policy": "confirmed_same_data_cases_then_confirmed_evidence_then_source_interpreted_then_connected_cases",
        "total_path_count": len(paths),
        "selected_path_count": len(selected),
        "omitted_path_count": max(0, len(paths) - len(selected)),
        "max_report_paths": _MAX_REPORT_PATHS,
        "selected_path_ids": sorted(selected_ids),
        "complete_path_catalog": len(selected) == len(paths),
    }


def _path_reference(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "path_id": item.get("path_id"),
        "storage_object": item.get("storage_object"),
        "source_operation": item.get("source_operation"),
        "access_boundary": item.get("access_boundary"),
        "evidence_maturity_level": item.get("evidence_maturity_level"),
        "field_mappings": list(item.get("field_mappings") or ()),
        "missing_links": list(item.get("missing_links") or ()),
        "evidence_ids": list(item.get("evidence_ids") or ()),
    }


def _selected_report_cases(cases: list[dict[str, Any]], selected_paths: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected_path_ids = {str(item.get("path_id") or "") for item in selected_paths if str(item.get("path_id") or "")}

    def priority(item: dict[str, Any]) -> tuple[Any, ...]:
        source_id = str(item.get("source_path_id") or "")
        access_id = str(item.get("access_path_id") or "")
        both_selected = bool(source_id and access_id and source_id in selected_path_ids and access_id in selected_path_ids)
        any_selected = bool((source_id and source_id in selected_path_ids) or (access_id and access_id in selected_path_ids))
        if item.get("same_data_end_to_end_status") == "confirmed":
            rank = 0
        elif both_selected:
            rank = 1
        elif any_selected:
            rank = 2
        elif item.get("source_to_storage_observed") and item.get("storage_to_access_observed"):
            rank = 3
        else:
            rank = 4
        return (
            rank,
            str(item.get("storage_object") or ""),
            str(item.get("storage_field") or ""),
            source_id,
            access_id,
            str(item.get("case_id") or ""),
        )

    ordered = sorted(cases, key=priority)
    confirmed = [item for item in ordered if item.get("same_data_end_to_end_status") == "confirmed"]
    if len(confirmed) > _MAX_REPORT_CASES:
        selected = confirmed
    else:
        selected = ordered[:_MAX_REPORT_CASES]
    selected_case_ids = {str(item.get("case_id") or "") for item in selected}
    return selected, {
        "selection_policy": "all_confirmed_exact_cases_then_selected_path_pairs_then_other_connected_cases",
        "total_case_count": len(cases),
        "selected_case_count": len(selected),
        "omitted_case_count": max(0, len(cases) - len(selected)),
        "max_report_cases": _MAX_REPORT_CASES,
        "confirmed_case_count": len(confirmed),
        "all_confirmed_cases_selected": all(str(item.get("case_id") or "") in selected_case_ids for item in confirmed),
        "complete_case_catalog": len(selected) == len(cases),
    }


def _owner_questions(path_count: int, access_count: int, source_count: int) -> list[dict[str, str]]:
    questions = [
        {
            "question_id": "Q-FDP-SOURCE",
            "question": "Какие внешние или runtime-источники соответствуют обнаруженным storage/access-фрагментам?",
            "basis": f"Найдено {path_count} FDP-фрагментов, из них source→storage: {source_count}.",
        },
        {
            "question_id": "Q-FDP-SAME-DATA",
            "question": "Какие конкретные поля проходят полную цепочку source → local storage → outward access?",
            "basis": "Совпадение storage object не является доказательством идентичности данных на уровне полей.",
        },
    ]
    if access_count:
        questions.append({
            "question_id": "Q-FDP-ACCESS",
            "question": "Какие обнаруженные outward-access boundaries являются внешними бизнес-интерфейсами, а какие локальными техническими вызовами?",
            "basis": f"Обнаружено {access_count} storage→access-фрагментов без автоматически назначенного бизнес-вердикта.",
        })
    return questions


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("foreign-data-persistence-report/v1 requires a resolved Knowledge API revision")

    paths_result = source.query_foreign_data_persistence("list_paths", max_results=10000)
    source_result = source.query_foreign_data_persistence("list_paths", filters={"direction": "source-to-storage"}, max_results=10000)
    access_result = source.query_foreign_data_persistence("list_paths", filters={"direction": "storage-to-access"}, max_results=10000)
    cases_result = source.query_foreign_data_persistence("list_mechanical_cases", max_results=10000)
    landscape_result = source.query_foreign_data_persistence("get_landscape", max_results=10000)
    overview_result = source.query_system_description("get_scope_overview")

    all_paths = [_compact_path(dict(item)) for item in (paths_result.get("items") or [])]
    all_cases = [_compact_case(dict(item)) for item in (cases_result.get("items") or [])]
    paths, path_selection = _selected_report_paths(all_paths, all_cases)
    cases, case_selection = _selected_report_cases(all_cases, paths)
    storage_summaries = [dict(item) for item in ((cases_result.get("summary") or {}).get("storage_summaries") or ())]
    maturity_counts = Counter(str(item.get("evidence_maturity_level") or "unresolved") for item in all_paths)
    missing_link_counts = Counter(
        str(link)
        for item in all_paths
        for link in item.get("missing_links") or ()
        if str(link)
    )
    for item in all_cases:
        missing_link_counts.update(str(link) for link in item.get("missing_links") or () if str(link))

    source_count = len((source_result.get("items") or []))
    access_count = len((access_result.get("items") or []))
    full_segment_case_count = sum(
        1 for item in all_cases
        if item["source_to_storage_observed"] and item["storage_to_access_observed"]
    )
    same_data_confirmed_count = sum(
        1 for item in all_cases if item.get("same_data_end_to_end_status") == "confirmed"
    )
    if same_data_confirmed_count:
        assessment = "end_to_end_same_data_observed"
    elif full_segment_case_count:
        assessment = "investigation_candidates_without_same_data_confirmation"
    elif source_count or access_count:
        assessment = "partial_fragments_only"
    else:
        assessment = "no_fdp_path_facts_materialized"

    sections = {
        "executive_assessment": {
            "assessment": assessment,
            "confirmed_business_fdp_risk_count": 0,
            "business_risk_decision_assigned": False,
            "path_count": len(all_paths),
            "source_to_storage_path_count": source_count,
            "storage_to_access_path_count": access_count,
            "mechanical_case_count": len(all_cases),
            "source_and_access_case_count": full_segment_case_count,
            "same_data_end_to_end_confirmed_case_count": same_data_confirmed_count,
            "business_wording": (
                "Статический анализ обнаружил только частичные FDP-фрагменты; подтверждённый бизнес-риск сохранения чужих данных не устанавливается."
                if assessment == "partial_fragments_only"
                else "Статический анализ не назначает бизнес-вердикт; каждый кандидат требует проверки полноты цепочки и происхождения данных."
            ),
        },
        "complete_path_catalog": paths,
        "path_catalog_selection": path_selection,
        "source_to_storage_paths": [_path_reference(item) for item in paths if item.get("direction") == "source-to-storage"],
        "storage_to_access_paths": [_path_reference(item) for item in paths if item.get("direction") == "storage-to-access"],
        "mechanical_cases": cases,
        "case_catalog_selection": case_selection,
        "storage_summaries": storage_summaries,
        "chain_completeness": {
            "source_to_storage_observed_count": source_count,
            "storage_to_access_observed_count": access_count,
            "both_segments_observed_count": full_segment_case_count,
            "same_data_confirmed_count": same_data_confirmed_count,
            "maturity_counts": dict(sorted(maturity_counts.items())),
            "missing_link_counts": dict(sorted(missing_link_counts.items())),
        },
        "risk_and_governance": {
            "business_fdp_decision_assigned": False,
            "risk_decision_assigned": False,
            "external_origin_requires_evidence": True,
            "named_source_system_required_for_governance": True,
            "named_source_system_required_for_technical_ingress": False,
            "local_persistence_is_not_external_access": True,
            "storage_to_access_is_not_source_to_storage": True,
            "exact_storage_identity_alone_is_not_same_data_proof": True,
            "exact_storage_field_and_confirmed_path_pair_required": True,
        },
        "gaps_and_blockers": {
            "missing_link_counts": dict(sorted(missing_link_counts.items())),
            "items": [
                {
                    "path_id": item.get("path_id"),
                    "repo_id": item.get("repo_id"),
                    "direction": item.get("direction"),
                    "storage_object": item.get("storage_object"),
                    "missing_links": list(item.get("missing_links") or ()),
                    "evidence_ids": list(item.get("evidence_ids") or ()),
                }
                for item in paths if item.get("missing_links")
            ][:_MAX_GAP_ITEMS],
            "selected_gap_item_count": min(_MAX_GAP_ITEMS, sum(1 for item in paths if item.get("missing_links"))),
            "gap_item_selection_truncated": sum(1 for item in paths if item.get("missing_links")) > _MAX_GAP_ITEMS,
            "negative_observation_policy": "Absence of an observed segment is not proof that the segment does not exist.",
        },
        "owner_questions": _owner_questions(len(all_paths), access_count, source_count),
    }
    referenced_ids = _referenced_evidence_ids(sections)
    results = [paths_result, source_result, access_result, cases_result, landscape_result, overview_result]
    overview_item = dict((overview_result.get("items") or [])[0]) if (overview_result.get("items") or []) else {}
    scope = {
        "kind": str(overview_item.get("scope_type") or overview_item.get("scope_kind") or "repository"),
        "id": str(overview_item.get("scope_id") or request.system_id or "unknown"),
        "repository_ids": [str(value) for value in overview_item.get("repository_ids") or () if str(value)],
    }
    dataset: dict[str, Any] = {
        "schema_version": REPORT_DATASET_SCHEMA,
        "profile_id": request.profile_id,
        "request": request.to_dataset_dict(),
        "scope": scope,
        "coverage": {
            "knowledge_layer_counts": dict(overview_item.get("counts") or {}),
            "path_count": len(all_paths),
            "source_to_storage_path_count": source_count,
            "storage_to_access_path_count": access_count,
            "mechanical_case_count": len(all_cases),
            "selected_mechanical_case_count": len(cases),
            "omitted_mechanical_case_count": int(case_selection["omitted_case_count"]),
            "same_data_confirmed_case_count": same_data_confirmed_count,
            "all_confirmed_cases_selected": bool(case_selection["all_confirmed_cases_selected"]),
            "complete_path_catalog": bool(path_selection["complete_path_catalog"]),
            "complete_case_catalog": bool(case_selection["complete_case_catalog"]),
            "selected_path_count": len(paths),
            "omitted_path_count": int(path_selection["omitted_path_count"]),
            "business_fdp_decision_assigned": False,
            "positive_fixture_available": bool(source_count and access_count),
        },
        "sections": sections,
        "evidence_index": _merge_evidence(results, referenced_ids) if request.include_evidence else {},
        "interpretation_policy": {
            "facts_only": True,
            "partial_path": "A source→storage or storage→access fragment is not a complete FDP chain.",
            "business_decision": "The analyzer and report builder do not assign a business FDP or risk decision.",
            "external_origin": "Unknown origin must not be reported as internal origin or external origin.",
            "same_data": "Table identity alone is summary-only. Mechanical same-data confirmation requires one exact storage field and one confirmed source/access path pair.",
            "candidate_signals": "Candidate signals are navigation aids and never confirmed facts.",
            "negative_observation": "No observed path does not prove absence of the path.",
        },
    }
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
