from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .consumer_contracts import EvidenceRef, Gap, Page, QueryRequest, QueryResult, ScopeRef
from .data_model_queries import DataModelQueryService
from .normalization import stable_id
from .query import KnowledgeLayerQuery
from .reporting_queries import _source_path

_REFERENCE_ARTIFACTS = {
    "declared_value_sets": "reference_data_fact_base/declared_value_sets.jsonl",
    "declared_value_set_summaries": "reference_data_fact_base/declared_value_set_summaries.jsonl",
    "declared_values": "reference_data_fact_base/declared_values.jsonl",
    "literal_data_writes": "reference_data_fact_base/literal_data_writes.jsonl",
    "physical_assets": "reference_data_fact_base/physical_assets.jsonl",
    "physical_attributes": "reference_data_fact_base/physical_attributes.jsonl",
    "physical_constraints": "reference_data_fact_base/physical_constraints.jsonl",
    "storage_operations": "reference_data_fact_base/storage_operations.jsonl",
    "join_observations": "reference_data_fact_base/join_observations.jsonl",
    "source_to_storage_lineage": "reference_data_fact_base/source_to_storage_lineage.jsonl",
    "ingress_and_jobs": "reference_data_fact_base/ingress_and_jobs.jsonl",
    "external_dependencies": "reference_data_fact_base/external_dependencies.jsonl",
    "observed_relations": "reference_data_fact_base/observed_relations.jsonl",
    "configuration_facts": "reference_data_fact_base/configuration_facts.jsonl",
    "unresolved_gaps": "reference_data_fact_base/unresolved_gaps.jsonl",
}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return dict(decoded) if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}




def _portable_properties(value: Any, key: str = "") -> Any:
    """Remove build-machine roots from path-like fact properties."""
    if isinstance(value, dict):
        return {str(k): _portable_properties(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_portable_properties(item, key) for item in value]
    if isinstance(value, tuple):
        return [_portable_properties(item, key) for item in value]
    if isinstance(value, str) and value.startswith("/"):
        lowered = key.casefold()
        path_keys = {
            "repo_path", "repository_path", "source_path", "source_file",
            "file_path", "workspace_path", "output_path", "source_root",
            "repository_root", "workspace_root",
        }
        if lowered in path_keys or lowered.endswith(("_file_path", "_source_path", "_repository_path")):
            return _source_path(value)
    return value

def _source_set(value: Any) -> str:
    result = str(value or "unknown").strip().lower()
    aliases = {"main": "production", "example": "example_sample", "sample": "example_sample"}
    result = aliases.get(result, result)
    allowed = {"production", "migration", "test", "fixture", "example_sample", "generated", "documentation", "unknown"}
    return result if result in allowed else "unknown"


def _included_in_production_view(source_set: Any) -> bool:
    # Unknown/generated repository evidence must remain visible: absence of an explicit
    # production label is not evidence that the declaration is non-production.
    # Only explicitly non-production/documentation source sets are excluded.
    return _source_set(source_set) not in {"test", "fixture", "example_sample", "documentation"}


def _technical_aliases(*values: Any) -> set[str]:
    aliases: set[str] = set()
    for raw in values:
        text = str(raw or "").strip().casefold()
        if not text:
            continue
        aliases.add(text)
        basename = text.rsplit(".", 1)[-1]
        aliases.add(basename)
        for suffix in ("_dml_literal_rows", "_literal_rows"):
            if basename.endswith(suffix):
                basename = basename[: -len(suffix)]
        while basename and (basename[0].isdigit() or basename[0] in "._-"):
            basename = basename[1:]
        if basename:
            aliases.add(basename)
    return {value for value in aliases if len(value) >= 2}


def _candidate_matches_token(item: Mapping[str, Any], token: str) -> bool:
    needle = str(token or "").strip().casefold()
    if not needle:
        return True
    fields = (
        item.get("name"), item.get("qualified_name"), item.get("fqcn"),
        item.get("target_table"), item.get("reference_object_id"),
    )
    aliases = _technical_aliases(*fields)
    if any(needle in value for value in aliases):
        return True
    # Value samples are useful for a human/LLM lookup but do not establish semantic identity.
    samples = item.get("sample_entries") or ()
    return needle in json.dumps(samples, ensure_ascii=False, sort_keys=True).casefold()


def _definition_mode(item: Mapping[str, Any]) -> str:
    representation = str(item.get("representation_kind") or "").strip().casefold()
    syntax = str(item.get("syntax_kind") or "").strip().casefold()
    if representation == "literal_populated_storage_target" or syntax == "sql_values_rows":
        return "source_seed_sql"
    if syntax in {"java_enum", "java_static_list"}:
        return "code"
    if syntax in {"yaml_map", "json_map", "properties_prefix", "csv_table", "tsv_table", "xml_elements"}:
        return "source_file"
    if representation == "declared_value_set":
        return "source_declared_value_set"
    if representation == "annotated_dictionary_object":
        return "code_model"
    return "unresolved"


def _observation_matches_aliases(item: Mapping[str, Any], aliases: set[str]) -> bool:
    if not aliases:
        return False
    props = dict(item.get("properties") or {})
    fields = [
        item.get("name"), item.get("fact_id"),
        props.get("table_name"), props.get("qualified_table_name"), props.get("storage_target"),
        props.get("source_table"), props.get("target_table"),
        props.get("source_field"), props.get("target_field"),
        props.get("operation"), props.get("owner_fqcn"), props.get("method_name"),
        props.get("description"), props.get("path"), props.get("topic"), props.get("endpoint_path"),
    ]
    haystack = " ".join(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in fields if value is not None).casefold()
    return any(alias in haystack for alias in aliases)


class ReferenceDataQueryService:
    """Typed facts-only reference-data query facade.

    This service exposes observed dictionaries, declared value sets, literal writes,
    usage and population evidence. It does not declare official NSI status,
    ownership or source of truth.
    """

    def __init__(self, artifact: str | Path, *, manifest: str | Path | Mapping[str, Any] | None = None) -> None:
        self.query = (
            KnowledgeLayerQuery.from_database(artifact, manifest=manifest)
            if manifest is not None
            else KnowledgeLayerQuery(artifact)
        )
        self.data_model = DataModelQueryService(artifact, manifest=manifest)
        manifest = self.query.manifest()
        repo_ids = tuple(str(item) for item in (manifest.get("repository_ids") or ()))
        kind = str(manifest.get("scope_type") or ("repository" if len(repo_ids) == 1 else "workspace"))
        self.scope = ScopeRef(kind=kind, scope_id=str(manifest.get("scope_id") or Path(artifact).stem), repository_ids=repo_ids)

    @staticmethod
    def _collect(method: Callable[..., dict[str, Any]], *, max_items: int = 10000, page_size: int = 500, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        items: list[dict[str, Any]] = []
        token = ""
        total = 0
        while len(items) < max_items:
            page = method(max_results=min(page_size, max_items - len(items)), page_token=token, **kwargs)
            total = int(page.get("total_count") or 0)
            items.extend(dict(item) for item in (page.get("items") or ()))
            token = str(page.get("next_token") or "")
            if not token:
                break
        return items, total

    @staticmethod
    def _evidence(repo_id: str, owner_id: str, refs: Iterable[Mapping[str, Any]], maturity: str = "observed") -> tuple[list[str], list[EvidenceRef]]:
        ids: list[str] = []
        evidence: list[EvidenceRef] = []
        for index, ref in enumerate(refs or ()):
            path = _source_path(ref.get("file_path") or ref.get("file"))
            if not path:
                continue
            line_start = ref.get("line_start")
            line_end = ref.get("line_end")
            evidence_id = stable_id("evidence", repo_id, owner_id, path, line_start, line_end, index)
            ids.append(evidence_id)
            evidence.append(EvidenceRef(
                evidence_id=evidence_id,
                repo_id=repo_id,
                path=path,
                line_start=int(line_start) if line_start is not None else None,
                line_end=int(line_end) if line_end is not None else None,
                extractor=str(ref.get("extractor") or "") or None,
                snippet=str(ref.get("snippet") or "") or None,
                maturity=maturity or "observed",
            ))
        return ids, evidence

    @staticmethod
    def _result(
        request: QueryRequest,
        items: list[dict[str, Any]],
        *,
        total: int | None = None,
        summary: Mapping[str, Any] | None = None,
        evidence: Iterable[EvidenceRef] = (),
        gaps: Iterable[Gap] = (),
    ) -> QueryResult:
        by_id = {item.evidence_id: item for item in evidence}
        total_count = len(items) if total is None else int(total)
        return QueryResult(
            request=request,
            items=tuple(items),
            summary=dict(summary or {}),
            evidence=tuple(by_id[key] for key in sorted(by_id)),
            gaps=tuple(gaps),
            page=Page(total_count=total_count, returned_count=len(items), truncated=len(items) < total_count),
        )

    def _records(self, section: str, *, token: str = "", max_results: int = 10000) -> tuple[list[dict[str, Any]], int, list[EvidenceRef]]:
        artifact_name = _REFERENCE_ARTIFACTS[section]
        records, total = self._collect(
            self.query.reference_data_records,
            max_items=max_results,
            token=token,
            artifact_name=artifact_name,
            record_kind=section,
        )
        evidence: list[EvidenceRef] = []
        normalized: list[dict[str, Any]] = []
        for record in records:
            payload = _payload(record.get("payload_json"))
            properties = _portable_properties(dict(payload.get("properties") or {}))
            repo_id = str(record.get("repo_id") or "unknown")
            local_id = str(payload.get("fact_id") or record.get("local_record_id") or record.get("record_occurrence_id"))
            ids, refs = self._evidence(repo_id, local_id, payload.get("evidence") or (), str(properties.get("evidence_level") or "observed"))
            evidence.extend(refs)
            normalized.append({
                "record_id": record.get("record_occurrence_id"),
                "fact_id": payload.get("fact_id") or record.get("local_record_id"),
                "fact_type": payload.get("fact_type") or record.get("record_kind"),
                "repo_id": repo_id,
                "name": payload.get("name"),
                "source_set": _source_set(properties.get("source_set")),
                "properties": properties,
                "evidence_ids": ids,
            })
        return normalized, total, evidence

    def list_declared_value_sets(
        self,
        *,
        token: str = "",
        source_sets: Iterable[str] | None = None,
        include_values: bool = True,
        max_results: int = 5000,
    ) -> QueryResult:
        rows, total, evidence = self._records("declared_value_sets", token=token, max_results=max_results)
        allowed = {_source_set(value) for value in (source_sets or ())}
        if allowed:
            rows = [row for row in rows if row.get("source_set") in allowed]
        values_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
        value_evidence: list[EvidenceRef] = []
        if include_values:
            values, _, value_evidence = self._records("declared_values", token=token, max_results=20000)
            for row in values:
                props = row.get("properties") or {}
                set_id = str(props.get("declared_value_set_id") or "")
                if set_id:
                    values_by_set[set_id].append({
                        "declared_value_id": props.get("declared_value_id") or row.get("fact_id"),
                        "key": props.get("key") or props.get("name") or row.get("name"),
                        "value": props.get("value"),
                        "ordinal": props.get("ordinal"),
                        "source_set": row.get("source_set"),
                        "evidence_ids": list(row.get("evidence_ids") or ()),
                    })
        items: list[dict[str, Any]] = []
        for row in rows:
            props = row.get("properties") or {}
            set_id = str(props.get("declared_value_set_id") or row.get("fact_id") or "")
            samples = list(props.get("sample_entries") or ())
            values = sorted(values_by_set.get(set_id, ()), key=lambda item: (item.get("ordinal") is None, item.get("ordinal") or 0, str(item.get("key"))))
            evidence_ids = list(row.get("evidence_ids") or ())
            for value in values[:20]:
                evidence_ids.extend(value.get("evidence_ids") or ())
            items.append({
                "reference_object_id": set_id,
                "representation_kind": "declared_value_set",
                "repo_id": row.get("repo_id"),
                "name": row.get("name") or props.get("name"),
                "qualified_name": props.get("qualified_name") or props.get("owner_fqcn"),
                "syntax_kind": props.get("syntax_kind"),
                "container_kind": props.get("container_kind"),
                "entries_count": int(props.get("entries_count") or len(values) or len(samples)),
                "sample_entries": samples[:20],
                "declared_values": values[:80],
                "extraction_truncated": bool(props.get("extraction_truncated")),
                "source_set": row.get("source_set"),
                "is_production_evidence": row.get("source_set") in {"production", "migration"},
                "included_in_production_view": _included_in_production_view(row.get("source_set")),
                "evidence_ids": sorted(set(str(value) for value in evidence_ids if value)),
            })
        items.sort(key=lambda item: (str(item.get("source_set")), str(item.get("name")), str(item.get("qualified_name"))))
        counts = Counter(str(item.get("syntax_kind") or "unknown") for item in items)
        source_counts = Counter(str(item.get("source_set") or "unknown") for item in items)
        request = QueryRequest("list_declared_value_sets", self.scope, filters={"token": token, "source_sets": sorted(allowed)}, max_results=max_results)
        return self._result(
            request,
            items,
            total=total,
            summary={
                "declared_value_set_count": len(items),
                "declared_value_count": sum(int(item.get("entries_count") or 0) for item in items),
                "syntax_kind_counts": dict(sorted(counts.items())),
                "source_set_counts": dict(sorted(source_counts.items())),
            },
            evidence=[*evidence, *value_evidence],
        )

    def list_dictionary_objects(self, *, token: str = "", max_results: int = 5000) -> QueryResult:
        request = QueryRequest("list_dictionary_objects", self.scope, filters={"token": token}, max_results=max_results)
        if not self.query._has_relation("java_type_declaration"):
            return self._result(
                request,
                [],
                summary={
                    "dictionary_object_count": 0,
                    "dictionary_object_enrichment_available": False,
                    "dictionary_object_enrichment_basis": "code-declared-data-model_not_materialized_in_this_artifact",
                },
            )
        result = self.data_model.search_objects(token=token, object_kinds=("dictionary",), max_results=max_results)
        items = []
        for row in result.items:
            item = dict(row)
            item.update({
                "reference_object_id": item.get("object_id"),
                "representation_kind": "annotated_dictionary_object",
                "source_set": "production",
                "human_validation_required": True,
            })
            items.append(item)
        return self._result(
            request,
            items,
            total=result.page.total_count,
            summary={
                "dictionary_object_count": len(items),
                "dictionary_object_enrichment_available": True,
                "dictionary_object_enrichment_basis": "code-declared-data-model_tables_present",
            },
            evidence=result.evidence,
        )

    def list_literal_writes(self, *, token: str = "", max_results: int = 5000) -> QueryResult:
        rows, total, evidence = self._records("literal_data_writes", token=token, max_results=max_results)
        items = []
        for row in rows:
            props = row.get("properties") or {}
            items.append({
                "write_id": props.get("literal_data_write_id") or row.get("fact_id"),
                "repo_id": row.get("repo_id"),
                "target_table": props.get("qualified_table_name") or props.get("target_table") or row.get("name"),
                "operation": props.get("operation"),
                "columns": list(props.get("columns") or ()),
                "values": props.get("values") or {},
                "parameterized": props.get("parameterized"),
                "source_set": row.get("source_set"),
                "evidence_ids": row.get("evidence_ids") or [],
            })
        request = QueryRequest("list_literal_writes", self.scope, filters={"token": token}, max_results=max_results)
        return self._result(request, items, total=total, summary={"literal_write_count": len(items), "source_set_counts": dict(sorted(Counter(str(item.get("source_set")) for item in items).items()))}, evidence=evidence)

    def list_literal_write_targets(self, *, token: str = "", max_results: int = 5000) -> QueryResult:
        writes = self.list_literal_writes(token=token, max_results=max_results)
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        evidence_index = {item.evidence_id: item for item in writes.evidence}
        for row in writes.items:
            operation = str(row.get("operation") or "").strip().lower()
            if operation != "insert":
                continue
            repo_id = str(row.get("repo_id") or "unknown")
            target_table = str(row.get("target_table") or "").strip()
            if not target_table:
                continue
            key = (repo_id, target_table)
            item = grouped.setdefault(key, {
                "reference_object_id": stable_id("reference_literal_target", repo_id, target_table),
                "representation_kind": "literal_populated_storage_target",
                "repo_id": repo_id,
                "name": target_table,
                "target_table": target_table,
                "literal_insert_count": 0,
                "columns": set(),
                "source_sets": set(),
                "evidence_ids": set(),
                "reference_candidate_basis": "literal_insert_into_storage_target_observed",
                "semantic_classification_performed": False,
                "official_nsi_status_established": False,
                "human_validation_required": True,
            })
            item["literal_insert_count"] += 1
            item["columns"].update(str(value) for value in (row.get("columns") or ()) if str(value))
            if row.get("source_set"):
                item["source_sets"].add(str(row.get("source_set")))
            item["evidence_ids"].update(str(value) for value in (row.get("evidence_ids") or ()) if str(value))
        items: list[dict[str, Any]] = []
        evidence_ids: set[str] = set()
        for value in grouped.values():
            evidence_ids.update(value["evidence_ids"])
            items.append({
                **value,
                "columns": sorted(value["columns"]),
                "source_sets": sorted(value["source_sets"]),
                "evidence_ids": sorted(value["evidence_ids"]),
            })
        items.sort(key=lambda item: (str(item.get("repo_id")), str(item.get("target_table"))))
        request = QueryRequest("list_literal_write_targets", self.scope, filters={"token": token}, max_results=max_results)
        return self._result(
            request,
            items[:max_results],
            total=len(items),
            summary={
                "literal_populated_target_count": len(items),
                "semantic_classification_performed": False,
                "official_nsi_status_established": False,
            },
            evidence=[evidence_index[eid] for eid in sorted(evidence_ids) if eid in evidence_index],
        )

    def get_usage_observations(self, *, token: str = "", max_results_per_section: int = 5000) -> QueryResult:
        sections = ("physical_assets", "physical_attributes", "physical_constraints", "observed_relations", "storage_operations", "source_to_storage_lineage", "ingress_and_jobs", "external_dependencies", "configuration_facts", "join_observations")
        evidence: list[EvidenceRef] = []
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for section in sections:
            rows, _, refs = self._records(section, token=token, max_results=max_results_per_section)
            evidence.extend(refs)
            counts[section] = len(rows)
            for row in rows:
                items.append({"observation_kind": section, **row})
        items.sort(key=lambda item: (str(item.get("observation_kind")), str(item.get("repo_id")), str(item.get("name")), str(item.get("fact_id"))))
        request = QueryRequest("get_reference_data_usage", self.scope, filters={"token": token}, max_results=max_results_per_section * len(sections))
        return self._result(request, items, summary={"section_counts": counts, "observation_count": len(items)}, evidence=evidence)

    def get_gap_summary(self, *, token: str = "", max_results: int = 5000) -> QueryResult:
        rows, total, evidence = self._records("unresolved_gaps", token=token, max_results=max_results)
        items = []
        for row in rows:
            props = row.get("properties") or {}
            items.append({
                "gap_id": props.get("storage_lineage_gap_id") or props.get("data_model_lineage_gap_id") or row.get("fact_id"),
                "repo_id": row.get("repo_id"),
                "gap_kind": props.get("gap_kind") or props.get("missing_fact_kind") or row.get("fact_type"),
                "name": row.get("name"),
                "source_set": row.get("source_set"),
                "properties": props,
                "evidence_ids": row.get("evidence_ids") or [],
            })
        counts = Counter(str(item.get("gap_kind") or "unknown") for item in items)
        request = QueryRequest("get_reference_data_gap_summary", self.scope, filters={"token": token}, max_results=max_results)
        return self._result(request, items, total=total, summary={"gap_count": total, "returned_gap_count": len(items), "gap_kind_counts": dict(sorted(counts.items()))}, evidence=evidence)

    def search_reference_data(self, *, token: str = "", include_non_production: bool = True, max_results: int = 5000) -> QueryResult:
        # Search after representation aggregation. Raw-section token filtering can miss a
        # table whose semantic name is only present in the aggregated target identity.
        # The caller limit applies to search results, not to the candidate catalog scan.
        # Applying it before token matching makes candidates disappear solely because
        # they sort after the first N representations.
        catalog_limit = max(10000, int(max_results))
        dictionaries = self.list_dictionary_objects(token="", max_results=catalog_limit)
        value_sets = self.list_declared_value_sets(token="", max_results=catalog_limit)
        literal_targets = self.list_literal_write_targets(token="", max_results=catalog_limit)
        all_items = [dict(item) for item in dictionaries.items]
        all_items.extend(dict(item) for item in value_sets.items if include_non_production or item.get("included_in_production_view"))
        all_items.extend(dict(item) for item in literal_targets.items)
        for item in all_items:
            mode = _definition_mode(item)
            item["definition_mode_observed"] = mode if mode != "unresolved" else None
            item["repository_embedded_definition_evidence_present"] = mode != "unresolved"
            item["definition_authority_interpretation"] = "not_assigned"
            item["own_nsi_status"] = "not_assigned"
        items = [item for item in all_items if _candidate_matches_token(item, token)]
        items.sort(key=lambda item: (str(item.get("representation_kind")), str(item.get("name") or item.get("fqcn"))))
        referenced_ids = {str(eid) for item in items for eid in (item.get("evidence_ids") or ()) if str(eid)}
        evidence_by_id = {ref.evidence_id: ref for ref in [*dictionaries.evidence, *value_sets.evidence, *literal_targets.evidence]}
        request = QueryRequest("search_reference_data", self.scope, filters={"token": token, "include_non_production": include_non_production}, max_results=max_results)
        return self._result(
            request,
            items[:max_results],
            total=len(items),
            summary={
                "candidate_representation_count": len(items),
                "catalog_candidate_representation_count": len(all_items),
                "dictionary_object_count": sum(1 for item in items if item.get("representation_kind") == "annotated_dictionary_object"),
                "dictionary_object_enrichment_available": bool(dictionaries.summary.get("dictionary_object_enrichment_available")),
                "dictionary_object_enrichment_basis": dictionaries.summary.get("dictionary_object_enrichment_basis"),
                "declared_value_set_count": sum(1 for item in items if item.get("representation_kind") == "declared_value_set"),
                "literal_populated_target_count": sum(1 for item in items if item.get("representation_kind") == "literal_populated_storage_target"),
                "semantic_classification_performed": False,
                "official_nsi_status_established": False,
            },
            evidence=[evidence_by_id[eid] for eid in sorted(referenced_ids) if eid in evidence_by_id],
        )

    def get_candidate_context(
        self,
        *,
        token: str,
        include_non_production: bool = True,
        max_results: int = 500,
    ) -> QueryResult:
        token = str(token or "").strip()
        if not token:
            raise ValueError("token must not be empty")
        candidates = self.search_reference_data(
            token=token, include_non_production=include_non_production, max_results=max_results
        )
        candidate_items = [dict(item) for item in candidates.items]
        aliases = _technical_aliases(token)
        for item in candidate_items:
            aliases.update(_technical_aliases(item.get("name"), item.get("qualified_name"), item.get("target_table")))

        # Usage/gap records already have a search_text index; keep those queries token-scoped
        # so one candidate-context request does not load the whole fact base. The aggregation-first
        # correction is needed for candidate representations, not for these indexed observations.
        literal_writes = self.list_literal_writes(token=token, max_results=max_results)
        usage = self.get_usage_observations(token=token, max_results_per_section=max_results)
        gaps = self.get_gap_summary(token=token, max_results=max_results)
        matched_writes = [dict(item) for item in literal_writes.items]
        matched_usage = [dict(item) for item in usage.items]
        matched_gaps = [dict(item) for item in gaps.items]

        definition_modes = sorted({_definition_mode(item) for item in candidate_items if _definition_mode(item) != "unresolved"})
        local_definition_evidence = [
            {
                "candidate_id": item.get("reference_object_id") or item.get("object_id"),
                "representation_kind": item.get("representation_kind"),
                "definition_mode": _definition_mode(item),
                "source_set": item.get("source_set") or (item.get("source_sets") or ["unknown"])[0],
                "basis": item.get("reference_candidate_basis") or "declared_values_observed_in_analyzed_repository",
                "evidence_ids": list(item.get("evidence_ids") or ()),
            }
            for item in candidate_items
            if _definition_mode(item) != "unresolved"
        ]
        usage_counts = Counter(str(item.get("observation_kind") or "unknown") for item in matched_usage)
        item = {
            "token": token,
            "technical_aliases": sorted(aliases),
            "candidate_representations": candidate_items,
            "local_definition_evidence": local_definition_evidence,
            "literal_writes": matched_writes[:max_results],
            "usage_observations": matched_usage[:max_results],
            "gaps": matched_gaps[:max_results],
            "interpretation_policy": {
                "reference_semantics_assigned": False,
                "own_nsi_status_assigned": False,
                "global_definition_authority_established": False,
                "local_definition_evidence_is_context_local": True,
                "absence_of_upstream_evidence_is_not_global_proof": True,
                "human_or_llm_interpretation_required": True,
            },
        }
        evidence = [*candidates.evidence, *literal_writes.evidence, *usage.evidence, *gaps.evidence]
        referenced_ids = {str(eid) for value in (candidate_items + matched_writes + matched_usage + matched_gaps) for eid in (value.get("evidence_ids") or ()) if str(eid)}
        evidence_by_id = {ref.evidence_id: ref for ref in evidence}
        request = QueryRequest(
            "get_reference_data_candidate_context", self.scope,
            filters={"token": token, "include_non_production": include_non_production}, max_results=max_results,
        )
        return self._result(
            request, [item],
            summary={
                "candidate_representation_count": len(candidate_items),
                "local_definition_evidence_count": len(local_definition_evidence),
                "definition_modes_observed": definition_modes,
                "literal_write_count": len(matched_writes),
                "usage_observation_count": len(matched_usage),
                "usage_kind_counts": dict(sorted(usage_counts.items())),
                "gap_count": len(matched_gaps),
                "semantic_classification_performed": False,
                "own_nsi_status_established": False,
            },
            evidence=[evidence_by_id[eid] for eid in sorted(referenced_ids) if eid in evidence_by_id],
        )

    def get_reference_data_object(self, object_id: str) -> QueryResult:
        object_id = str(object_id or "").strip()
        if not object_id:
            raise ValueError("object_id must not be empty")
        dictionary = None
        if self.query._has_relation("java_type_declaration"):
            dictionary = self.data_model.get_object(object_id)
        if dictionary is not None and dictionary.items and dict(dictionary.items[0]).get("object_kind") == "dictionary":
            item = dict(dictionary.items[0])
            item.update({"reference_object_id": item.get("object_id"), "representation_kind": "annotated_dictionary_object", "source_set": "production"})
            relation_evidence = []
            try:
                relations = self.data_model.get_relationships(target_object_id=object_id)
                item["incoming_relationships"] = [dict(value) for value in relations.items]
                relation_evidence = list(relations.evidence)
            except AttributeError:
                item["incoming_relationships"] = []
                item["relationship_catalog_available"] = False
            item["human_validation_required"] = True
            request = QueryRequest("get_reference_data_object", self.scope, filters={"object_id": object_id}, max_results=1)
            return self._result(request, [item], evidence=[*dictionary.evidence, *relation_evidence])
        value_sets = self.list_declared_value_sets(max_results=10000)
        matches = [dict(item) for item in value_sets.items if str(item.get("reference_object_id")) == object_id]
        request = QueryRequest("get_reference_data_object", self.scope, filters={"object_id": object_id}, max_results=1)
        if matches:
            evidence_ids = set(matches[0].get("evidence_ids") or ())
            refs = [item for item in value_sets.evidence if item.evidence_id in evidence_ids]
            return self._result(request, matches[:1], evidence=refs)
        literal_targets = self.list_literal_write_targets(max_results=10000)
        literal_matches = [dict(item) for item in literal_targets.items if str(item.get("reference_object_id")) == object_id]
        if literal_matches:
            evidence_ids = set(literal_matches[0].get("evidence_ids") or ())
            refs = [item for item in literal_targets.evidence if item.evidence_id in evidence_ids]
            return self._result(request, literal_matches[:1], evidence=refs)
        return self._result(request, [], summary={
            "not_found": True,
            "dictionary_object_enrichment_available": self.query._has_relation("java_type_declaration"),
        })

    def get_landscape(self, *, token: str = "", max_results: int = 5000) -> QueryResult:
        candidates = self.search_reference_data(token=token, include_non_production=True, max_results=max_results)
        literal_writes = self.list_literal_writes(token=token, max_results=max_results)
        usage = self.get_usage_observations(token=token, max_results_per_section=max_results)
        gaps = self.get_gap_summary(token=token, max_results=max_results)
        source_counts = Counter(str(item.get("source_set") or "unknown") for item in candidates.items)
        representation_counts = Counter(str(item.get("representation_kind") or "unknown") for item in candidates.items)
        item = {
            "scope": self.scope.to_dict(),
            "candidate_representations": [dict(value) for value in candidates.items],
            "literal_writes": [dict(value) for value in literal_writes.items],
            "usage_observations": [dict(value) for value in usage.items],
            "gaps": [dict(value) for value in gaps.items],
            "semantic_policy": {
                "facts_only": True,
                "official_nsi_status_established": False,
                "ownership_established": False,
                "source_of_truth_established": False,
                "human_validation_required": True,
                "absence_is_not_proof": True,
            },
        }
        request = QueryRequest("get_reference_data_landscape", self.scope, filters={"token": token}, max_results=max_results)
        summary = {
            **dict(candidates.summary),
            "literal_write_count": len(literal_writes.items),
            "usage_observation_count": len(usage.items),
            "gap_count": len(gaps.items),
            "source_set_counts": dict(sorted(source_counts.items())),
            "representation_kind_counts": dict(sorted(representation_counts.items())),
            "usage_section_counts": dict(usage.summary.get("section_counts") or {}),
        }
        return self._result(request, [item], summary=summary, evidence=[*candidates.evidence, *literal_writes.evidence, *usage.evidence, *gaps.evidence])
