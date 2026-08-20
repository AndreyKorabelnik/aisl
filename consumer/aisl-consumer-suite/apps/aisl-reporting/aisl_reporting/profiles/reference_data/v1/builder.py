from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from ....contracts import REPORT_DATASET_SCHEMA, ReportRequest
from ....files import canonical_json, sha256_text


_DETAIL_LIMITS = {"executive": 12, "standard": 40, "detailed": 100}
_USAGE_SAMPLE_LIMITS = {"executive": 4, "standard": 12, "detailed": 30}


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


def _candidate(item: dict[str, Any]) -> dict[str, Any]:
    representation = str(item.get("representation_kind") or "unknown")
    source_set = str(item.get("source_set") or "unknown")
    if representation == "declared_value_set":
        maintenance_signals = ["embedded_in_code_or_config"]
        basis = "Explicitly declared values were extracted from code or configuration."
    elif representation == "literal_populated_storage_target":
        maintenance_signals = ["literal_population_observed"]
        basis = "Literal INSERT population into a storage target is observed; reference-data meaning, ownership and source of truth are not established."
    elif representation == "annotated_dictionary_object":
        maintenance_signals = ["dictionary_marker_observed"]
        basis = "Dictionary annotation/model classification is observed; population and ownership are not established."
    else:
        maintenance_signals = ["unknown"]
        basis = "A technical representation candidate is observed; reference-data meaning, ownership and source of truth are not established."
    return {
        "candidate_id": item.get("reference_object_id") or item.get("object_id"),
        "name": item.get("name"),
        "qualified_name": item.get("qualified_name") or item.get("fqcn"),
        "repo_id": item.get("repo_id"),
        "representation_kind": representation,
        "implementation_form": item.get("syntax_kind") or item.get("object_kind") or representation,
        "source_set": source_set,
        "definition_mode_observed": item.get("definition_mode_observed"),
        "repository_embedded_definition_evidence_present": bool(item.get("repository_embedded_definition_evidence_present")),
        "definition_authority_interpretation": item.get("definition_authority_interpretation") or "not_assigned",
        "own_nsi_status": item.get("own_nsi_status") or "not_assigned",
        "description": item.get("description"),
        "display_name": item.get("display_name"),
        "entries_count": item.get("entries_count"),
        "sample_entries": list(item.get("sample_entries") or ())[:5],
        "extraction_truncated": bool(item.get("extraction_truncated")),
        "observed_maintenance_signals": maintenance_signals,
        "maintenance_mode": "not_established",
        "ownership_interpretation": "not_established",
        "source_of_truth": "not_established",
        "candidate_basis": basis,
        "official_nsi_status": "not_established",
        "human_validation_required": True,
        "evidence_ids": sorted(set(item.get("evidence_ids") or ()))[:2],
    }


def _compact_value(value: Any, max_chars: int = 240) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = str(value) if isinstance(value, str) else value
        return text[:max_chars] + "…" if isinstance(text, str) and len(text) > max_chars else text
    if isinstance(value, list):
        return [_compact_value(item, max_chars=120) for item in value[:8]]
    if isinstance(value, dict):
        return {str(key): _compact_value(item, max_chars=120) for key, item in list(value.items())[:12]}
    return str(value)[:max_chars]


def _compact_properties(kind: str, properties: dict[str, Any]) -> dict[str, Any]:
    preferred = {
        "storage_operations": ("operation", "storage_target", "table", "qualified_table_name", "owner_fqcn", "method_name", "access_kind"),
        "source_to_storage_lineage": ("source_operation", "source_field", "source_expression", "storage_target", "target_field", "mapping_status", "lineage_status"),
        "ingress_and_jobs": ("direction", "kind", "operation", "path", "method", "topic", "job_name", "source_set"),
        "external_dependencies": ("dependency_kind", "coordinate", "operation", "endpoint_path", "endpoint_expression", "client_receiver_type"),
        "configuration_facts": ("configuration_path", "key", "value", "value_type", "source_set"),
        "join_observations": ("source_table", "target_table", "join_condition_preview", "observation_status"),
        "physical_assets": ("qualified_table_name", "table_name", "description", "source_scope", "source_type"),
        "physical_attributes": ("qualified_table_name", "table_name", "column_name", "description", "sql_type"),
        "physical_constraints": ("qualified_table_name", "table_name", "constraint_kind", "constraint_name", "columns", "source_table", "target_table"),
        "observed_relations": ("source_table", "target_table", "relation_kind", "source_columns", "target_columns"),
    }.get(kind, ())
    result = {key: _compact_value(properties.get(key)) for key in preferred if properties.get(key) is not None}
    if not result:
        result = {str(key): _compact_value(value) for key, value in list(properties.items())[:8]}
    return result


def _detailed_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    result = _candidate(raw)
    result["sample_entries"] = list(raw.get("sample_entries") or ())[:20]
    result["declared_values"] = list(raw.get("declared_values") or ())[:80]
    result["evidence_ids"] = sorted(set(raw.get("evidence_ids") or ()))[:8]
    return result


def _usage_samples(items: list[dict[str, Any]], limit: int, *, focus_terms: tuple[str, ...] = ()) -> dict[str, Any]:
    counts = Counter(str(item.get("observation_kind") or "unknown") for item in items)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for kind in sorted(counts):
        candidates = [item for item in items if item.get("observation_kind") == kind]
        focused = [item for item in candidates if focus_terms and any(term in canonical_json(item).casefold() for term in focus_terms)]
        selected = focused[:limit]
        if len(selected) < limit:
            selected_ids = {str(item.get("record_id") or item.get("fact_id") or id(item)) for item in selected}
            for item in candidates:
                item_id = str(item.get("record_id") or item.get("fact_id") or id(item))
                if item_id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(item_id)
                if len(selected) >= limit:
                    break
        grouped[kind] = [
            {
                "fact_id": item.get("fact_id"),
                "repo_id": item.get("repo_id"),
                "name": item.get("name"),
                "source_set": item.get("source_set"),
                "properties": _compact_properties(kind, dict(item.get("properties") or {})),
                "evidence_ids": list(item.get("evidence_ids") or ())[:1],
            }
            for item in selected
        ]
    return {"counts": dict(sorted(counts.items())), "samples": grouped}


def _owner_questions(candidate_count: int, value_set_count: int, gap_count: int) -> list[dict[str, str]]:
    questions = [
        {
            "question_id": "Q-OWN-NSI",
            "question": "Какие кандидаты действительно обладают справочной семантикой и определяются внутри анализируемой системы, а какие являются state/config/integration vocabularies?",
            "basis": f"Статический анализ сформировал {candidate_count} технических representations; own-NSI verdict требует совместной оценки reference semantics и definition origin.",
        },
        {
            "question_id": "Q-UPSTREAM-AUTHORITY",
            "question": "Для каких локально определённых кандидатов существует более ранний внешний источник или authoritative master вне анализируемого контекста?",
            "basis": "Локальный seed/enum/resource доказывает definition evidence внутри repository, но отсутствие upstream evidence не доказывает глобальную первичность.",
        },
    ]
    if value_set_count:
        questions.append({
            "question_id": "Q-EMBEDDED-VALUES",
            "question": "Какие встроенные наборы значений являются собственными справочниками системы, а какие только техническими enum/config/state наборами?",
            "basis": f"Обнаружено {value_set_count} явно объявленных наборов значений; форма хранения сама по себе не определяет НСИ.",
        })
    if gap_count:
        questions.append({
            "question_id": "Q-POPULATION-PATHS",
            "question": "Какие пути регулярного наполнения и изменения необходимо подтвердить вручную?",
            "basis": f"В reference-data evidence зафиксировано {gap_count} unresolved gaps.",
        })
    return questions


def build_dataset(request: ReportRequest) -> dict[str, Any]:
    source = request.knowledge_source
    if source is None:
        raise ValueError("reference-data-report/v1 requires a resolved Knowledge API revision")

    candidates_result = source.query_reference_data("search_reference_data", max_results=10000)
    declared_result = source.query_reference_data("list_declared_value_sets", max_results=10000)
    literal_result = source.query_reference_data("list_literal_writes", max_results=5000)
    usage_result = source.query_reference_data("get_usage_observations", max_results=5000)
    gap_result = source.query_reference_data("get_gap_summary", max_results=5000)
    overview_result = source.query_system_description("get_scope_overview")

    raw_candidates = [dict(item) for item in (candidates_result.get("items") or [])]
    candidates = [_candidate(item) for item in raw_candidates]
    raw_by_id = {str(item.get("reference_object_id") or item.get("object_id")): item for item in raw_candidates}
    production_candidates = [item for item in candidates if item.get("source_set") in {"production", "migration"}]
    non_production_candidates = [item for item in candidates if item.get("source_set") not in {"production", "migration"}]
    representation_counts = Counter(str(item.get("representation_kind") or "unknown") for item in candidates)
    implementation_counts = Counter(str(item.get("implementation_form") or "unknown") for item in candidates)
    source_set_counts = Counter(str(item.get("source_set") or "unknown") for item in candidates)

    focus_terms = tuple(term.casefold() for term in request.focus)
    focused = [
        item for item in candidates
        if focus_terms and any(term in canonical_json(item).casefold() for term in focus_terms)
    ]
    detail_limits = _DETAIL_LIMITS
    if focused:
        limit = detail_limits[request.detail_level]
        focus_buckets: list[list[dict[str, Any]]] = []
        for term in focus_terms:
            matches = [item for item in candidates if term in canonical_json(item).casefold()]
            if matches:
                focus_buckets.append(matches)
        detailed_selection = []
        seen_ids: set[str] = set()
        while len(detailed_selection) < limit and focus_buckets:
            remaining: list[list[dict[str, Any]]] = []
            for bucket in focus_buckets:
                while bucket:
                    item = bucket.pop(0)
                    candidate_id = str(item.get("candidate_id") or item.get("qualified_name") or item.get("name") or "")
                    if candidate_id not in seen_ids:
                        seen_ids.add(candidate_id)
                        detailed_selection.append(item)
                        break
                if bucket:
                    remaining.append(bucket)
                if len(detailed_selection) >= limit:
                    break
            focus_buckets = remaining
    else:
        limit = detail_limits[request.detail_level]
        priority = {"production": 0, "migration": 1, "unknown": 2, "generated": 3, "documentation": 4, "example_sample": 5, "fixture": 6, "test": 7}
        buckets: dict[str, list[dict[str, Any]]] = {}
        for item in candidates:
            buckets.setdefault(str(item.get("representation_kind") or "unknown"), []).append(item)
        for items in buckets.values():
            items.sort(key=lambda item: (priority.get(str(item.get("source_set") or "unknown"), 99), str(item.get("qualified_name") or item.get("name") or "")))
        detailed_selection = []
        kinds = sorted(buckets)
        while len(detailed_selection) < limit and kinds:
            remaining = []
            for kind in kinds:
                items = buckets[kind]
                if items and len(detailed_selection) < limit:
                    detailed_selection.append(items.pop(0))
                if items:
                    remaining.append(kind)
            kinds = remaining
    detailed = [_detailed_candidate(raw_by_id.get(str(item.get("candidate_id")), item)) for item in detailed_selection]

    usage_items = [dict(item) for item in (usage_result.get("items") or [])]
    sample_limits = _USAGE_SAMPLE_LIMITS
    usage = _usage_samples(usage_items, sample_limits[request.detail_level], focus_terms=focus_terms)
    grouped_candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in candidates:
        key = (
            str(item.get("representation_kind") or "unknown"),
            str(item.get("implementation_form") or "unknown"),
            str(item.get("source_set") or "unknown"),
        )
        grouped_candidates.setdefault(key, []).append(item)
    catalog_groups = [
        {
            "representation_kind": key[0],
            "implementation_form": key[1],
            "source_set": key[2],
            "candidate_count": len(items),
            "candidate_names": [str(item.get("qualified_name") or item.get("name")) for item in items[:20]],
            "candidate_names_truncated": len(items) > 20,
        }
        for key, items in sorted(grouped_candidates.items())
    ]
    gaps = [
        {
            "gap_id": item.get("gap_id"), "repo_id": item.get("repo_id"), "gap_kind": item.get("gap_kind"),
            "name": item.get("name"), "source_set": item.get("source_set"),
            "properties": _compact_value(item.get("properties") or {}),
            "evidence_ids": list(item.get("evidence_ids") or ())[:1] if index < 20 else [],
        }
        for index, item in enumerate((gap_result.get("items") or [])[:100])
    ]
    literal_writes = [
        {**dict(item), "evidence_ids": []}
        for item in (literal_result.get("items") or [])[:100]
    ]

    sections = {
        "landscape": {
            "candidate_representation_count": len(candidates),
            "representation_kind_counts": dict(sorted(representation_counts.items())),
            "implementation_form_counts": dict(sorted(implementation_counts.items())),
            "source_set_counts": dict(sorted(source_set_counts.items())),
            "production_or_migration_candidate_count": len(production_candidates),
            "non_production_or_unknown_candidate_count": len(non_production_candidates),
            "declared_value_set_count": len((declared_result.get("items") or [])),
            "declared_value_count": int((declared_result.get("summary") or {}).get("declared_value_count") or 0),
            "literal_write_count": len((literal_result.get("items") or [])),
            "usage_observation_count": len(usage_items),
            "gap_count": int((gap_result.get("summary") or {}).get("gap_count") or len((gap_result.get("items") or []))),
        },
        "complete_candidate_catalog": [
            {key: value for key, value in item.items() if key != "evidence_ids"}
            for item in candidates
        ],
        "candidate_catalog_groups": catalog_groups,
        "production_and_migration_candidates": [
            {key: item.get(key) for key in ("candidate_id", "name", "qualified_name", "repo_id", "representation_kind", "implementation_form", "source_set")}
            for item in production_candidates
        ],
        "non_production_and_unknown_candidates": [
            {key: item.get(key) for key in ("candidate_id", "name", "qualified_name", "repo_id", "representation_kind", "implementation_form", "source_set")}
            for item in non_production_candidates
        ],
        "detailed_candidates": detailed,
        "declared_value_sets": [
            {
                "candidate_id": item.get("reference_object_id"), "name": item.get("name"),
                "qualified_name": item.get("qualified_name"), "repo_id": item.get("repo_id"),
                "syntax_kind": item.get("syntax_kind"), "entries_count": item.get("entries_count"),
                "source_set": item.get("source_set"), "sample_entries": list(item.get("sample_entries") or ())[:5],
                "evidence_ids": [],
            }
            for item in (declared_result.get("items") or [])
        ],
        "literal_population_observations": literal_writes,
        "reads_writes_and_population": usage,
        "usage_observation_kind_counts": dict(
            sorted(Counter(str(item.get("observation_kind") or "unknown") for item in usage_items).items())
        ),
        "conflicts_and_possible_duplicates": {
            "confirmed_conflicts": [],
            "possible_duplicate_policy": "Name similarity alone is not a confirmed duplicate or representation mapping.",
            "requires_human_comparison": True,
        },
        "gaps_and_coverage": {
            "gap_count": int((gap_result.get("summary") or {}).get("gap_count") or len((gap_result.get("items") or []))),
            "gap_kind_counts": dict((gap_result.get("summary") or {}).get("gap_kind_counts") or {}),
            "items": gaps,
            "negative_observation_policy": "Absence of an observed write or external path is not proof that the path does not exist.",
        },
        "owner_questions": _owner_questions(len(candidates), len((declared_result.get("items") or [])), int((gap_result.get("summary") or {}).get("gap_count") or len((gap_result.get("items") or [])))),
    }
    referenced_ids = _referenced_evidence_ids(sections)
    results = [candidates_result, declared_result, literal_result, usage_result, gap_result, overview_result]
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
            "candidate_representation_count": len(candidates),
            "dictionary_object_count": int((candidates_result.get("summary") or {}).get("dictionary_object_count") or 0),
            "declared_value_set_count": int((candidates_result.get("summary") or {}).get("declared_value_set_count") or 0),
            "declared_value_count": int((declared_result.get("summary") or {}).get("declared_value_count") or 0),
            "literal_write_count": len((literal_result.get("items") or [])),
            "usage_observation_count": len(usage_items),
            "gap_count": int((gap_result.get("summary") or {}).get("gap_count") or len((gap_result.get("items") or []))),
            "complete_candidate_catalog": True,
            "semantic_classification_performed": False,
            "official_nsi_status_established": False,
        },
        "sections": sections,
        "evidence_index": _merge_evidence(results, referenced_ids) if request.include_evidence else {},
        "interpretation_policy": {
            "candidate_scope": "The catalog contains observed reference-data representations, not a preclassified own-NSI register.",
            "own_nsi_definition": "Own NSI requires both reference semantics and definition/creation inside the analyzed technical context, with no earlier external origin established in that context.",
            "local_origin_boundary": "Repository-embedded definition evidence establishes only the earliest observed origin in the analyzed context, not global enterprise authority.",
            "external_consumption": "Externally received reference data is normal consumption and must not be classified as own NSI merely because it is cached or written locally.",
            "ownership": "Enterprise owner and authoritative source of truth are never invented without external evidence.",
            "maintenance": "Runtime CRUD, seed SQL, source files and code-declared values are valid local definition modes; local/external/mixed interpretation still requires provenance evidence.",
            "representation_linking": "Separate representations are not merged by name similarity.",
            "source_sets": "Production and migration evidence are separated from test, fixture, example, generated, documentation and unknown evidence.",
            "negative_observations": "No observed path does not mean no path exists.",
        },
    }
    # Fit rich evidence to the profile byte budget deterministically instead of
    # hard-coding a smaller candidate count for every repository. The complete
    # compact candidate catalog is never truncated; only duplicated detailed
    # expansions and usage samples are reduced, with prompt minima preserved.
    target_bytes = 850_000
    min_detailed = 20
    min_usage_total = 10
    def _rebuild_evidence() -> None:
        referenced = _referenced_evidence_ids(dataset["sections"])
        dataset["evidence_index"] = _merge_evidence(results, referenced) if request.include_evidence else {}
    _rebuild_evidence()
    while len(canonical_json(dataset).encode("utf-8")) > target_bytes:
        details = dataset["sections"]["detailed_candidates"]
        if len(details) > min_detailed:
            del details[max(min_detailed, len(details) - 5):]
            _rebuild_evidence()
            continue
        samples = dataset["sections"]["reads_writes_and_population"].get("samples", {})
        total_samples = sum(len(items) for items in samples.values())
        if total_samples <= min_usage_total:
            break
        longest = max((items for items in samples.values() if items), key=len, default=None)
        if longest is None:
            break
        longest.pop()
        _rebuild_evidence()
    dataset["coverage"]["detailed_candidate_count"] = len(dataset["sections"]["detailed_candidates"])
    dataset["coverage"]["usage_sample_count"] = sum(
        len(items) for items in dataset["sections"]["reads_writes_and_population"].get("samples", {}).values()
    )
    dataset["coverage"]["dataset_budget_policy"] = "complete_catalog_plus_budgeted_detail/v1"
    dataset["dataset_fingerprint"] = sha256_text(canonical_json(dataset))
    return dataset
