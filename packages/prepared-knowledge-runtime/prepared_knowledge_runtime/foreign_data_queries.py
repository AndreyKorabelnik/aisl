from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .consumer_contracts import EvidenceRef, Page, QueryRequest, QueryResult, ScopeRef
from .normalization import stable_id
from .query import KnowledgeLayerQuery
from .reporting_queries import _source_path

_DIRECTIONS = {"source-to-storage", "storage-to-access"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return dict(result) if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _portable(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(k): _portable(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item, key) for item in value]
    if isinstance(value, str) and value.startswith("/"):
        lowered = key.casefold()
        if lowered in {"file", "file_path", "source_file", "source_path", "repo_path", "repository_path", "source_root"} or lowered.endswith(("_file", "_file_path", "_source_path")):
            return _source_path(value)
    return value


def _status(value: Any, default: str = "unresolved") -> str:
    result = str(value or default).strip().lower()
    aliases = {"complete": "confirmed", "resolved": "confirmed", "observed": "confirmed", "candidate": "candidate", "partial": "unresolved"}
    return aliases.get(result, result or default)


def _normalized_field_mappings(payload: Mapping[str, Any], *, direction: str) -> list[dict[str, Any]]:
    """Expose a uniform field-mapping shape for FDP path formats.

    Older/aggregated path records carry a ``field_mappings`` array, while the
    canonical Core source-to-storage catalogue uses one row per mapping with
    top-level ``source_field`` and ``storage_field`` properties.  Mechanical
    bridging must understand both without rewriting or weakening the raw fact.
    """
    mappings = [dict(item) for item in (payload.get("field_mappings") or ()) if isinstance(item, Mapping)]
    if direction != "source-to-storage":
        return mappings

    source_field = str(payload.get("source_field") or "").strip()
    storage_field = str(
        payload.get("storage_field")
        or payload.get("saved_object_field")
        or payload.get("target_field")
        or ""
    ).strip()
    if not source_field or not storage_field:
        return mappings
    signature = (source_field.casefold(), storage_field.casefold())
    existing = {
        (
            str(item.get("source_field") or "").strip().casefold(),
            str(item.get("storage_field") or item.get("target_field") or "").strip().casefold(),
        )
        for item in mappings
    }
    if signature not in existing:
        mappings.append({
            "source_field": source_field,
            "storage_field": storage_field,
            "target_field": storage_field,
            "mapping_type": str(payload.get("assignment_kind") or "source_to_storage_scalar_mapping"),
            "status": _status(payload.get("evidence_maturity_level") or payload.get("lineage_status")),
            "mapping_basis": "canonical_source_to_storage_row",
        })
    return mappings


def _source_interpretation(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Expose technical source/origin semantics already present in typed evidence.

    This is deliberately not a business ownership decision.  Core
    ``source_kind`` values such as ``kafka_consumed`` and ``rest_ingress`` are
    observed boundary classifications, so the FDP read side may surface them as
    confirmed technical ingress without guessing a named upstream system.
    Ordinary method inputs stay runtime candidates; local/generated origins are
    kept separate from external ingress.
    """
    existing = payload.get("source_interpretation")
    if isinstance(existing, Mapping) and existing:
        return dict(existing)

    source_kind = str(payload.get("source_kind") or "").strip()
    source_payload = str(payload.get("source_payload") or "").strip()
    lineage_status = _status(payload.get("evidence_maturity_level") or payload.get("lineage_status"))
    boundary_maturity = _status(
        (payload.get("evidence_maturity_dimensions") or {}).get("source_boundary")
        if isinstance(payload.get("evidence_maturity_dimensions"), Mapping)
        else None
    )

    external_kinds = {
        "kafka_consumed", "rest_ingress", "external_service_response",
        "file_input", "message_queue",
    }
    local_kinds = {"storage_read", "cache_read", "computed", "constant"}

    if source_kind in external_kinds:
        confirmed = boundary_maturity == "confirmed" and lineage_status == "confirmed"
        status = "confirmed_external_ingress" if confirmed else "external_ingress_candidate"
        reason = (
            "typed persistence evidence confirms an external/runtime ingress boundary"
            if confirmed
            else "typed persistence evidence identifies an external/runtime ingress kind but the full source-to-storage path is not confirmed"
        )
    elif source_kind in local_kinds:
        status = "internal_generated_or_local_candidate"
        reason = "typed persistence evidence identifies a local/generated/storage-derived source kind"
    elif source_payload and source_payload.casefold() not in {"unknown", "none", "null"}:
        status = "runtime_input_candidate"
        reason = "a runtime input payload is observed, but no confirmed external boundary is attached to this path"
    else:
        status = "unknown_origin"
        reason = "the path does not contain enough technical source evidence to classify its origin"

    return {
        "status": status,
        "source_kind": source_kind or None,
        "source_system": None,
        "business_source_decision": "not_made_by_analyzer",
        "reason": reason,
        "source_payload": source_payload or None,
        "named_source_system_required_for_technical_ingress": False,
        "named_source_system_required_for_governance": True,
    }


class ForeignDataPersistenceQueryService:
    """Facts-only FDP path facade.

    The service preserves source, persistence and access segments independently.
    It never assigns a business FDP/risk verdict. Confirmed mechanical bridges require
    exact storage-object and storage-field identity plus one confirmed source path and
    one confirmed access path. Table-level aggregation is summary-only.
    """

    def __init__(self, artifact: str | Path, *, manifest: str | Path | Mapping[str, Any] | None = None) -> None:
        self.query = (
            KnowledgeLayerQuery.from_database(artifact, manifest=manifest)
            if manifest is not None
            else KnowledgeLayerQuery(artifact)
        )
        manifest = self.query.manifest()
        repo_ids = tuple(str(item) for item in (manifest.get("repository_ids") or ()))
        kind = str(manifest.get("scope_type") or ("repository" if len(repo_ids) == 1 else "workspace"))
        self.scope = ScopeRef(kind=kind, scope_id=str(manifest.get("scope_id") or Path(artifact).stem), repository_ids=repo_ids)

    @staticmethod
    def _evidence(repo_id: str, owner_id: str, refs: Iterable[Mapping[str, Any]], maturity: str) -> tuple[list[str], list[EvidenceRef]]:
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
                maturity=maturity,
            ))
        return ids, evidence

    def _collect(self, *, direction: str | None = None, token: str = "", max_results: int = 10000) -> tuple[list[dict[str, Any]], int, list[EvidenceRef]]:
        if direction is not None and direction not in _DIRECTIONS:
            raise ValueError(f"unsupported FDP direction: {direction!r}")
        if direction is None:
            source_rows, source_total, source_evidence = self._collect(
                direction="source-to-storage", token=token, max_results=max_results
            )
            remaining = max(0, max_results - len(source_rows))
            access_rows, access_total, access_evidence = self._collect(
                direction="storage-to-access", token=token, max_results=remaining or 1
            )
            rows = source_rows + (access_rows if remaining else [])
            rows.sort(key=lambda item: (str(item.get("repo_id")), str(item.get("direction")), str(item.get("storage_object")), str(item.get("path_id"))))
            return rows[:max_results], source_total + access_total, source_evidence + (access_evidence if remaining else [])
        rows: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        page_token = ""
        total = 0
        while len(rows) < max_results:
            page = self.query.fdp_paths(token=token, direction=direction, max_results=min(500, max_results - len(rows)), page_token=page_token)
            total = int(page.get("total_count") or 0)
            for record in page.get("items") or ():
                payload = _portable(_payload(record.get("payload_json")))
                repo_id = str(record.get("repo_id") or "unknown")
                artifact = str(record.get("artifact_name") or "")
                actual_direction = "source-to-storage" if artifact.endswith("source_to_storage_lineage.json") else "storage-to-access"
                path_id = str(
                    payload.get("source_to_storage_lineage_id")
                    or payload.get("storage_to_access_lineage_id")
                    or record.get("local_record_id")
                    or record.get("record_occurrence_id")
                )
                maturity = _status(payload.get("evidence_maturity_level") or payload.get("lineage_status"))
                ids, refs = self._evidence(repo_id, path_id, payload.get("evidence") or (), maturity)
                evidence.extend(refs)
                storage_object = (
                    payload.get("storage_target")
                    or payload.get("target_storage_object")
                    or payload.get("source_storage_object")
                    or payload.get("qualified_table_name")
                )
                normalized_field_mappings = _normalized_field_mappings(payload, direction=actual_direction)
                rows.append({
                    "path_id": path_id,
                    "direction": actual_direction,
                    "repo_id": repo_id,
                    "storage_object": storage_object,
                    "source_operation": payload.get("source_operation") or payload.get("source_boundary") or payload.get("ingress_boundary"),
                    "source_interpretation": _source_interpretation(payload) if actual_direction == "source-to-storage" else {},
                    "access_boundary": payload.get("access_boundary"),
                    "lineage_status": _status(payload.get("lineage_status")),
                    "evidence_maturity_level": maturity,
                    "evidence_maturity_dimensions": dict(payload.get("evidence_maturity_dimensions") or {}),
                    "path": list(payload.get("path") or ()),
                    "field_mappings": normalized_field_mappings,
                    "persistent_write_refs": list(payload.get("persistent_write_refs") or ()),
                    "missing_links": list(payload.get("missing_links") or ()),
                    "candidate_signals": [dict(item) for item in (payload.get("candidate_signals") or ())],
                    "risk_eligibility": dict(payload.get("risk_eligibility") or {}),
                    "same_data_link": dict(payload.get("same_data_link") or {}),
                    "raw_fact": payload,
                    "evidence_ids": ids,
                })
            page_token = str(page.get("next_token") or "")
            if not page_token:
                break
        rows.sort(key=lambda item: (str(item.get("repo_id")), str(item.get("direction")), str(item.get("storage_object")), str(item.get("path_id"))))
        return rows, total, evidence

    @staticmethod
    def _result(request: QueryRequest, items: list[dict[str, Any]], *, total: int | None = None, summary: Mapping[str, Any] | None = None, evidence: Iterable[EvidenceRef] = ()) -> QueryResult:
        by_id = {ref.evidence_id: ref for ref in evidence}
        total_count = len(items) if total is None else int(total)
        return QueryResult(
            request=request,
            items=tuple(items),
            summary=dict(summary or {}),
            evidence=tuple(by_id[key] for key in sorted(by_id)),
            page=Page(total_count=total_count, returned_count=len(items), truncated=len(items) < total_count),
        )

    def list_paths(self, *, direction: str | None = None, token: str = "", max_results: int = 10000) -> QueryResult:
        rows, total, evidence = self._collect(direction=direction, token=token, max_results=max_results)
        counts = Counter(str(item.get("direction")) for item in rows)
        maturity = Counter(str(item.get("evidence_maturity_level") or "unresolved") for item in rows)
        request = QueryRequest("list_foreign_data_persistence_paths", self.scope, filters={"direction": direction, "token": token}, max_results=max_results)
        return self._result(request, rows, total=total, summary={
            "path_count": total,
            "returned_path_count": len(rows),
            "direction_counts": dict(sorted(counts.items())),
            "maturity_counts": dict(sorted(maturity.items())),
            "business_fdp_decision_assigned": False,
            "same_data_end_to_end_required": True,
        }, evidence=evidence)

    def get_path(self, path_id: str) -> QueryResult:
        path_id = str(path_id or "").strip()
        if not path_id:
            raise ValueError("path_id must not be empty")
        rows, _, evidence = self._collect(max_results=10000)
        matches = [item for item in rows if str(item.get("path_id")) == path_id]
        ids = {eid for item in matches for eid in item.get("evidence_ids") or ()}
        request = QueryRequest("get_foreign_data_persistence_path", self.scope, filters={"path_id": path_id}, max_results=1)
        return self._result(request, matches[:1], summary={"not_found": not bool(matches)}, evidence=[ref for ref in evidence if ref.evidence_id in ids])

    def list_mechanical_cases(self, *, token: str = "", max_results: int = 10000) -> QueryResult:
        rows, _, evidence = self._collect(token=token, max_results=max_results)
        grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"source_paths": [], "access_paths": []})
        unkeyed: list[dict[str, Any]] = []
        for item in rows:
            storage = str(item.get("storage_object") or "").strip()
            if not storage:
                unkeyed.append(item)
                continue
            bucket = grouped[(str(item.get("repo_id")), storage)]
            bucket["source_paths" if item.get("direction") == "source-to-storage" else "access_paths"].append(item)

        def field_entries(path: Mapping[str, Any]) -> list[tuple[str, str]]:
            direction = str(path.get("direction") or "")
            values: dict[str, str] = {}
            for mapping in path.get("field_mappings") or ():
                if not isinstance(mapping, Mapping):
                    continue
                raw = (
                    mapping.get("storage_field") or mapping.get("target_field")
                    if direction == "source-to-storage"
                    else mapping.get("storage_field") or mapping.get("source_field")
                )
                display = str(raw or "").strip().strip('"')
                if not display:
                    continue
                identity = display.rsplit(".", 1)[-1].casefold()
                values.setdefault(identity, display.rsplit(".", 1)[-1])
            return sorted(values.items())

        def confirmed(path: Mapping[str, Any]) -> bool:
            return _status(path.get("evidence_maturity_level") or path.get("lineage_status")) == "confirmed"

        cases: list[dict[str, Any]] = []
        storage_summaries: list[dict[str, Any]] = []
        for (repo_id, storage), bucket in sorted(grouped.items()):
            source_paths = sorted(bucket["source_paths"], key=lambda item: str(item.get("path_id")))
            access_paths = sorted(bucket["access_paths"], key=lambda item: str(item.get("path_id")))
            source_by_field: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
            access_by_field: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
            for path in source_paths:
                for identity, display in field_entries(path):
                    source_by_field[identity].append((path, display))
            for path in access_paths:
                for identity, display in field_entries(path):
                    access_by_field[identity].append((path, display))

            table_case_count_before = len(cases)
            all_fields = sorted(set(source_by_field) | set(access_by_field))
            for field_identity in all_fields:
                source_entries = source_by_field.get(field_identity) or []
                access_entries = access_by_field.get(field_identity) or []
                if source_entries and access_entries:
                    for source_path, source_display in source_entries:
                        for access_path, access_display in access_entries:
                            source_ok = confirmed(source_path)
                            access_ok = confirmed(access_path)
                            overlap_field = source_display or access_display
                            evidence_ids = sorted({
                                *list(source_path.get("evidence_ids") or ()),
                                *list(access_path.get("evidence_ids") or ()),
                            })
                            cases.append({
                                "case_id": stable_id(
                                    "fdp_case", repo_id, storage, field_identity,
                                    source_path.get("path_id"), access_path.get("path_id"),
                                ),
                                "case_granularity": "storage_field_path_pair",
                                "repo_id": repo_id,
                                "storage_object": storage,
                                "storage_field": overlap_field,
                                "source_path_id": source_path.get("path_id"),
                                "access_path_id": access_path.get("path_id"),
                                "source_paths": [source_path],
                                "access_paths": [access_path],
                                "bridge_basis": "exact_storage_object_field_and_path_pair",
                                "source_to_storage_observed": True,
                                "storage_to_access_observed": True,
                                "same_data_field_overlap": [overlap_field],
                                "same_data_end_to_end_status": "confirmed" if source_ok and access_ok else "unresolved",
                                "business_fdp_decision": "not_assigned",
                                "risk_decision": "not_assigned",
                                "missing_links": [
                                    *([] if source_ok else ["source_to_storage_path_not_confirmed"]),
                                    *([] if access_ok else ["storage_to_access_path_not_confirmed"]),
                                ],
                                "evidence_ids": evidence_ids,
                            })
                elif source_entries:
                    for source_path, source_display in source_entries:
                        cases.append({
                            "case_id": stable_id("fdp_case", repo_id, storage, field_identity, source_path.get("path_id"), "no_access"),
                            "case_granularity": "storage_field_path_pair",
                            "repo_id": repo_id,
                            "storage_object": storage,
                            "storage_field": source_display,
                            "source_path_id": source_path.get("path_id"),
                            "access_path_id": None,
                            "source_paths": [source_path],
                            "access_paths": [],
                            "bridge_basis": "exact_storage_object_and_field_without_access_path",
                            "source_to_storage_observed": True,
                            "storage_to_access_observed": False,
                            "same_data_field_overlap": [],
                            "same_data_end_to_end_status": "unresolved",
                            "business_fdp_decision": "not_assigned",
                            "risk_decision": "not_assigned",
                            "missing_links": ["storage_to_access_path_not_observed"],
                            "evidence_ids": list(source_path.get("evidence_ids") or ()),
                        })
                else:
                    for access_path, access_display in access_entries:
                        cases.append({
                            "case_id": stable_id("fdp_case", repo_id, storage, field_identity, "no_source", access_path.get("path_id")),
                            "case_granularity": "storage_field_path_pair",
                            "repo_id": repo_id,
                            "storage_object": storage,
                            "storage_field": access_display,
                            "source_path_id": None,
                            "access_path_id": access_path.get("path_id"),
                            "source_paths": [],
                            "access_paths": [access_path],
                            "bridge_basis": "exact_storage_object_and_field_without_source_path",
                            "source_to_storage_observed": False,
                            "storage_to_access_observed": True,
                            "same_data_field_overlap": [],
                            "same_data_end_to_end_status": "unresolved",
                            "business_fdp_decision": "not_assigned",
                            "risk_decision": "not_assigned",
                            "missing_links": ["source_to_storage_path_not_observed"],
                            "evidence_ids": list(access_path.get("evidence_ids") or ()),
                        })

            # Paths with no physical field identity remain visible but cannot prove same data.
            for path in [*source_paths, *access_paths]:
                if field_entries(path):
                    continue
                is_source = path.get("direction") == "source-to-storage"
                cases.append({
                    "case_id": stable_id("fdp_case", repo_id, storage, path.get("path_id"), "field_unresolved"),
                    "case_granularity": "path_without_storage_field",
                    "repo_id": repo_id,
                    "storage_object": storage,
                    "storage_field": None,
                    "source_path_id": path.get("path_id") if is_source else None,
                    "access_path_id": None if is_source else path.get("path_id"),
                    "source_paths": [path] if is_source else [],
                    "access_paths": [] if is_source else [path],
                    "bridge_basis": "storage_field_identity_not_available",
                    "source_to_storage_observed": is_source,
                    "storage_to_access_observed": not is_source,
                    "same_data_field_overlap": [],
                    "same_data_end_to_end_status": "unresolved",
                    "business_fdp_decision": "not_assigned",
                    "risk_decision": "not_assigned",
                    "missing_links": ["storage_field_identity_not_available"],
                    "evidence_ids": list(path.get("evidence_ids") or ()),
                })

            overlap_fields = sorted(set(source_by_field) & set(access_by_field))
            table_cases = cases[table_case_count_before:]
            storage_summaries.append({
                "repo_id": repo_id,
                "storage_object": storage,
                "source_path_count": len(source_paths),
                "access_path_count": len(access_paths),
                "source_field_count": len(source_by_field),
                "access_field_count": len(access_by_field),
                "overlap_fields": [source_by_field[field][0][1] for field in overlap_fields],
                "exact_case_count": len(table_cases),
                "confirmed_case_count": sum(1 for item in table_cases if item["same_data_end_to_end_status"] == "confirmed"),
                "aggregation_policy": "summary_only_not_end_to_end_proof",
            })

        for item in unkeyed:
            cases.append({
                "case_id": stable_id("fdp_case", item.get("repo_id"), item.get("path_id")),
                "case_granularity": "path_without_storage_object",
                "repo_id": item.get("repo_id"),
                "storage_object": None,
                "storage_field": None,
                "source_path_id": item.get("path_id") if item.get("direction") == "source-to-storage" else None,
                "access_path_id": item.get("path_id") if item.get("direction") == "storage-to-access" else None,
                "source_paths": [item] if item.get("direction") == "source-to-storage" else [],
                "access_paths": [item] if item.get("direction") == "storage-to-access" else [],
                "bridge_basis": "storage_object_identity_not_available",
                "source_to_storage_observed": item.get("direction") == "source-to-storage",
                "storage_to_access_observed": item.get("direction") == "storage-to-access",
                "same_data_field_overlap": [],
                "same_data_end_to_end_status": "unresolved",
                "business_fdp_decision": "not_assigned",
                "risk_decision": "not_assigned",
                "missing_links": ["storage_object_identity_not_available"],
                "evidence_ids": list(item.get("evidence_ids") or ()),
            })

        cases.sort(key=lambda item: (
            str(item.get("repo_id")), str(item.get("storage_object")), str(item.get("storage_field")),
            str(item.get("source_path_id")), str(item.get("access_path_id")), str(item.get("case_id")),
        ))
        ids = {eid for item in cases for eid in item.get("evidence_ids") or ()}
        request = QueryRequest("list_foreign_data_persistence_cases", self.scope, filters={"token": token}, max_results=max_results)
        return self._result(request, cases[:max_results], total=len(cases), summary={
            "case_count": len(cases),
            "case_granularity": "storage_field_path_pair",
            "source_and_access_case_count": sum(1 for item in cases if item["source_to_storage_observed"] and item["storage_to_access_observed"]),
            "same_data_confirmed_case_count": sum(1 for item in cases if item["same_data_end_to_end_status"] == "confirmed"),
            "storage_summary_count": len(storage_summaries),
            "storage_summaries": storage_summaries,
            "business_fdp_decision_assigned": False,
            "mechanical_bridge_only": True,
        }, evidence=[ref for ref in evidence if ref.evidence_id in ids])

    def get_landscape(self, *, token: str = "", max_results: int = 10000) -> QueryResult:
        paths = self.list_paths(token=token, max_results=max_results)
        cases = self.list_mechanical_cases(token=token, max_results=max_results)
        item = {
            "scope": self.scope.to_dict(),
            "paths": [dict(value) for value in paths.items],
            "cases": [dict(value) for value in cases.items],
            "interpretation_policy": {
                "facts_only": True,
                "business_fdp_decision_assigned": False,
                "external_origin_requires_evidence": True,
                "local_persistence_is_not_external_access": True,
                "storage_to_access_is_not_source_to_storage": True,
                "exact_storage_identity_alone_is_not_same_data_proof": True,
                "exact_storage_field_and_confirmed_path_pair_required": True,
                "candidate_signals_are_navigation_only": True,
            },
        }
        request = QueryRequest("get_foreign_data_persistence_landscape", self.scope, filters={"token": token}, max_results=max_results)
        summary = {**dict(paths.summary), **{f"case_{k}": v for k, v in cases.summary.items()}}
        return self._result(request, [item], summary=summary, evidence=[*paths.evidence, *cases.evidence])
