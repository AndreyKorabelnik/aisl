from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .consumer_contracts import EvidenceRef, Gap, Page, QueryRequest, QueryResult, ScopeRef
from .normalization import stable_id
from .query import KnowledgeLayerQuery

_SYMBOLIC_ENDPOINTS = {"URI", "API_URI", "CARD_LIFE_CYCLE_URL", "PROFILES_BY_DEVICE_ID_URL"}


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


def _source_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/")
    if not raw:
        return ""
    # Canonical runner staging layout: keep the path inside the selected repository.
    if "/selected/" in raw:
        suffix = raw.split("/selected/", 1)[1]
        parts = suffix.split("/", 1)
        return parts[1] if len(parts) == 2 else parts[0]
    # Preserve the nearest project/module segment for normal source trees.
    if "/src/" in raw:
        prefix, suffix = raw.split("/src/", 1)
        component = prefix.rstrip("/").split("/")[-1]
        return f"{component}/src/{suffix}" if component else f"src/{suffix}"
    # Keep already-relative paths unchanged. Absolute fallback paths are reduced
    # to their stable tail rather than leaking a build-machine root.
    if not raw.startswith("/"):
        return raw
    parts = [part for part in raw.split("/") if part]
    for marker in ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        if marker in parts:
            index = len(parts) - 1 - parts[::-1].index(marker)
            return "/".join(parts[max(0, index - 2):])
    return "/".join(parts[-4:])



class ReportingQueryService:
    """Stable, typed query facade for report builders and assistant tools.

    Consumers do not issue arbitrary SQL and do not depend on DuckDB table layouts.
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

    def _subject_only_system_description(self) -> bool:
        return (
            "common.system-description" in self.query.capabilities()
            and not self.query._has_relation("workspace_repository")
        )

    def _system_description_records(self, artifact_name: str, *, max_items: int = 10000) -> tuple[list[dict[str, Any]], int]:
        return self._collect(
            self.query.search_subject_records,
            max_items=max_items,
            materialization_id="system-description",
            artifact_name=artifact_name,
        )

    @staticmethod
    def _module_from_build_evidence(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
        refs = payload.get("evidence") or payload.get("evidence_refs") or ()
        if not refs:
            return None, None
        raw = str((refs[0] or {}).get("file") or (refs[0] or {}).get("file_path") or "")
        path = _source_path(raw)
        if not path:
            return None, None
        p = Path(path)
        if p.name not in {"build.gradle", "build.gradle.kts", "pom.xml"}:
            return None, path
        parent = str(p.parent).replace("\\", "/")
        return (parent if parent not in {"", "."} else "."), path

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
            path = _source_path(ref.get("file") or ref.get("file_path"))
            if not path:
                continue
            line_start = ref.get("line_start")
            line_end = ref.get("line_end")
            evidence_id = stable_id("evidence", repo_id, owner_id, path, line_start, line_end, index)
            item = EvidenceRef(
                evidence_id=evidence_id,
                repo_id=repo_id,
                path=path,
                line_start=int(line_start) if line_start is not None else None,
                line_end=int(line_end) if line_end is not None else None,
                extractor=str(ref.get("extractor") or "") or None,
                snippet=str(ref.get("snippet") or "") or None,
                maturity=maturity or "observed",
            )
            ids.append(evidence_id)
            evidence.append(item)
        return ids, evidence

    @staticmethod
    def _result(request: QueryRequest, items: list[dict[str, Any]], *, total: int | None = None, summary: Mapping[str, Any] | None = None, evidence: Iterable[EvidenceRef] = (), gaps: Iterable[Gap] = ()) -> QueryResult:
        ev_by_id = {item.evidence_id: item for item in evidence}
        total_count = len(items) if total is None else int(total)
        return QueryResult(
            request=request,
            items=tuple(items),
            summary=dict(summary or {}),
            evidence=tuple(ev_by_id[key] for key in sorted(ev_by_id)),
            gaps=tuple(gaps),
            page=Page(total_count=total_count, returned_count=len(items), truncated=len(items) < total_count),
        )

    def get_scope_overview(self) -> QueryResult:
        overview = self.query.get_overview()
        build = dict(overview.get("build") or {})
        manifest = dict(overview.get("manifest") or {})
        counts = dict(build.get("counts_json") or manifest.get("counts") or {})
        item = {
            "scope": self.scope.to_dict(),
            "build_id": build.get("build_id") or manifest.get("build_id"),
            "producer": manifest.get("producer"),
            "producer_version": manifest.get("producer_version") or build.get("builder_version"),
            "build_status": build.get("build_status") or manifest.get("build_status"),
            "capabilities": list(overview.get("capabilities") or ()),
            "counts": counts,
            "analysis_scope_kind": overview.get("analysis_scope_kind"),
        }
        request = QueryRequest("get_scope_overview", self.scope, max_results=1)
        return self._result(request, [item], summary={"repository_count": len(self.scope.repository_ids), "fact_count": counts.get("source_observation", 0), "evidence_count": counts.get("evidence_ref", 0)})

    def get_repository_composition(self, *, max_results: int = 500) -> QueryResult:
        if self._subject_only_system_description():
            manifest = self.query.manifest()
            repo_ids = [str(value) for value in (manifest.get("repository_ids") or self.scope.repository_ids)]
            repositories = [{"repo_id": repo_id, "scope_id": self.scope.scope_id} for repo_id in repo_ids]
            records, _ = self._system_description_records("external_dependencies.json", max_items=max_results * 4)
            evidence: list[EvidenceRef] = []
            modules_by_path: dict[str, dict[str, Any]] = {}
            for record in records:
                payload = _payload(record.get("payload_json"))
                if payload.get("dependency_kind") != "gradle_artifact" or payload.get("is_test_source"):
                    continue
                module_path, build_file = self._module_from_build_evidence(payload)
                if not module_path:
                    continue
                item = modules_by_path.setdefault(module_path, {
                    "module_id": stable_id("subject_module", record.get("repo_id"), module_path),
                    "repo_id": record.get("repo_id"), "module_path": module_path,
                    "module_name": Path(module_path).name if module_path != "." else "root",
                    "build_system": "gradle", "build_file": build_file,
                    "dependency_count": 0, "dependent_count": None, "plugin_count": None, "evidence_ids": [],
                })
                item["dependency_count"] += 1
                ids, refs = self._evidence(str(record.get("repo_id") or "unknown"), str(record.get("record_occurrence_id")), payload.get("evidence") or (), str(payload.get("evidence_level") or "confirmed"))
                evidence.extend(refs)
                item["evidence_ids"] = sorted(set([*item["evidence_ids"], *ids]))[:3]
            normalized_modules = sorted(modules_by_path.values(), key=lambda item: str(item.get("module_path")))[:max_results]
            request = QueryRequest("get_repository_composition", self.scope, max_results=max_results)
            return self._result(request, [{"repositories": repositories, "modules": normalized_modules}], summary={"repository_count": len(repositories), "module_count": len(normalized_modules), "source": "system-description/v1"}, evidence=evidence)

        repositories, repo_total = self._collect(self.query.repositories, max_items=max_results)
        modules, module_total = self._collect(self.query.list_modules, max_items=max_results)
        evidence: list[EvidenceRef] = []
        normalized_modules: list[dict[str, Any]] = []
        for item in modules:
            payload = _payload(item.get("payload_json"))
            ids, refs = self._evidence(str(item.get("repo_id") or "unknown"), str(item.get("module_occurrence_id") or item.get("module_path")), payload.get("evidence") or (), str(item.get("evidence_maturity_level") or "confirmed"))
            evidence.extend(refs)
            normalized_modules.append({
                "module_id": item.get("module_occurrence_id"), "repo_id": item.get("repo_id"),
                "module_path": item.get("module_path"), "module_name": item.get("module_name"),
                "build_system": item.get("build_system"), "build_file": _source_path(item.get("build_file")),
                "dependency_count": item.get("dependency_count"), "dependent_count": item.get("dependent_count"),
                "plugin_count": item.get("plugin_count"), "evidence_ids": ids,
            })
        request = QueryRequest("get_repository_composition", self.scope, max_results=max_results)
        items = [{"repositories": repositories, "modules": normalized_modules}]
        return self._result(request, items, summary={"repository_count": repo_total, "module_count": module_total}, evidence=evidence)

    def get_technologies(self, *, max_results: int = 1000) -> QueryResult:
        if self._subject_only_system_description():
            records, total = self._system_description_records("external_dependencies.json", max_items=max_results * 4)
            evidence: list[EvidenceRef] = []
            items: list[dict[str, Any]] = []
            seen: set[tuple[str, str | None]] = set()
            for record in records:
                payload = _payload(record.get("payload_json"))
                if payload.get("dependency_kind") != "gradle_artifact" or payload.get("is_test_source"):
                    continue
                coordinate = str(payload.get("name") or "")
                module_path, _ = self._module_from_build_evidence(payload)
                key = (coordinate, module_path)
                if not coordinate or key in seen:
                    continue
                seen.add(key)
                parts = coordinate.split(":")
                ids, refs = self._evidence(str(record.get("repo_id") or "unknown"), str(record.get("record_occurrence_id")), payload.get("evidence") or (), str(payload.get("evidence_level") or "confirmed"))
                evidence.extend(refs)
                items.append({
                    "technology_id": record.get("record_occurrence_id"), "kind": "declared_dependency",
                    "repo_id": record.get("repo_id"), "module_path": module_path, "coordinate": coordinate,
                    "group_id": parts[0] if len(parts) > 1 else None, "artifact_id": parts[1] if len(parts) > 1 else coordinate,
                    "version": parts[2] if len(parts) > 2 else None, "configuration": None,
                    "runtime_use_confirmed": False, "evidence_ids": ids,
                })
                if len(items) >= max_results:
                    break
            request = QueryRequest("get_technologies", self.scope, max_results=max_results)
            return self._result(request, items, total=len(items), summary={"plugin_count": 0, "declared_dependency_count": len(items), "source": "system-description/v1"}, evidence=evidence)

        plugins, plugin_total = self._collect(self.query.build_plugins, max_items=max_results)
        dependencies, dependency_total = self._collect(self.query.external_dependencies, max_items=max_results, include_test=False)
        evidence: list[EvidenceRef] = []
        normalized_plugins: list[dict[str, Any]] = []
        for item in plugins:
            payload = _payload(item.get("payload_json"))
            ids, refs = self._evidence(str(item.get("repo_id") or "unknown"), str(item.get("plugin_occurrence_id") or item.get("plugin_id")), payload.get("evidence") or (), "confirmed")
            evidence.extend(refs)
            normalized_plugins.append({
                "technology_id": item.get("plugin_occurrence_id"), "kind": "build_plugin", "repo_id": item.get("repo_id"),
                "module_path": item.get("module_path"), "name": item.get("plugin_id"), "version": item.get("plugin_version"),
                "application_kind": item.get("application_kind"), "evidence_ids": ids,
            })
        normalized_dependencies: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in dependencies:
            key = (item.get("source_module_path"), item.get("coordinate"), item.get("configuration"))
            if key in seen:
                continue
            seen.add(key)
            payload = _payload(item.get("payload_json"))
            ids, refs = self._evidence(str(item.get("repo_id") or "unknown"), str(item.get("dependency_occurrence_id") or item.get("coordinate")), payload.get("evidence") or (), str(item.get("evidence_maturity_level") or "confirmed"))
            evidence.extend(refs)
            normalized_dependencies.append({
                "technology_id": item.get("dependency_occurrence_id"), "kind": "declared_dependency", "repo_id": item.get("repo_id"),
                "module_path": item.get("source_module_path"), "coordinate": item.get("coordinate"),
                "group_id": item.get("group_id"), "artifact_id": item.get("artifact_id"), "version": item.get("dependency_version"),
                "configuration": item.get("configuration"), "runtime_use_confirmed": False, "evidence_ids": ids,
            })
        items = sorted(normalized_plugins + normalized_dependencies, key=lambda x: (str(x.get("kind")), str(x.get("name") or x.get("coordinate")), str(x.get("module_path"))))
        request = QueryRequest("get_technologies", self.scope, max_results=max_results)
        return self._result(request, items, total=plugin_total + dependency_total, summary={"plugin_count": plugin_total, "declared_dependency_count": dependency_total}, evidence=evidence)

    def list_interfaces(self, *, direction: str | None = None, boundary_kinds: Iterable[str] | None = None, include_test: bool = False, max_results: int = 1000) -> QueryResult:
        records, total = self._collect(self.query.system_interfaces, max_items=max_results * 4)
        allowed = set(boundary_kinds or ())
        evidence: list[EvidenceRef] = []
        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for record in records:
            payload = _payload(record.get("payload_json"))
            if not include_test and payload.get("is_test_source"):
                continue
            if direction and payload.get("direction") != direction:
                continue
            if allowed and payload.get("boundary_kind") not in allowed:
                continue
            endpoint = payload.get("endpoint_or_topic_resolved") or payload.get("endpoint_or_topic_raw")
            key = (payload.get("operation"), endpoint, payload.get("http_method"), payload.get("payload_schema_ref"), payload.get("boundary_kind"))
            if key in seen:
                continue
            seen.add(key)
            ids, refs = self._evidence(str(record.get("repo_id") or "unknown"), str(record.get("record_occurrence_id")), payload.get("evidence_refs") or (), str(payload.get("evidence_level") or "observed"))
            evidence.extend(refs)
            items.append({
                "interface_id": payload.get("interface_id") or record.get("local_record_id") or record.get("record_occurrence_id"),
                "repo_id": record.get("repo_id"), "operation": payload.get("operation"), "direction": payload.get("direction"),
                "boundary_kind": payload.get("boundary_kind"), "protocol": payload.get("protocol"),
                "endpoint_or_topic": endpoint, "http_method": payload.get("http_method"),
                "payload_schema": payload.get("payload_schema_ref"), "request_payload_type": payload.get("request_payload_type"),
                "response_payload_type": payload.get("response_payload_type"), "resolution_status": payload.get("resolution_status"),
                "evidence_level": payload.get("evidence_level"), "attribute_count": payload.get("attribute_count"),
                "evidence_ids": ids,
            })
            if len(items) >= max_results:
                break
        items.sort(key=lambda x: (str(x.get("direction")), str(x.get("boundary_kind")), str(x.get("endpoint_or_topic")), str(x.get("operation"))))
        filters = {"direction": direction, "boundary_kinds": sorted(allowed), "include_test": include_test}
        request = QueryRequest("list_interfaces", self.scope, filters=filters, max_results=max_results)
        counts: dict[str, int] = {}
        for item in items:
            key = str(item.get("boundary_kind") or "unknown")
            counts[key] = counts.get(key, 0) + 1
        return self._result(request, items, total=total, summary={"selected_count": len(items), "boundary_kind_counts": counts}, evidence=evidence)

    def list_integrations(self, *, max_results: int = 1000) -> QueryResult:
        interface_result = self.list_interfaces(direction="outbound", boundary_kinds=("http_outbound", "kafka_publish"), max_results=max_results)
        records, _ = self._collect(self.query.search_subject_records, max_items=max_results * 2, materialization_id="system-description", artifact_name="external_dependencies.json", record_kind="external_dependencies")
        items = [dict(item) for item in interface_result.items]
        evidence = list(interface_result.evidence)
        seen_ops = {(item.get("operation"), item.get("boundary_kind")) for item in items}
        for record in records:
            payload = _payload(record.get("payload_json"))
            if payload.get("is_test_source") or payload.get("dependency_kind") != "http_outbound":
                continue
            key = (payload.get("operation"), "http_outbound")
            if key in seen_ops:
                continue
            seen_ops.add(key)
            refs_value = payload.get("evidence") or payload.get("evidence_refs") or ()
            ids, refs = self._evidence(str(record.get("repo_id") or "unknown"), str(record.get("record_occurrence_id")), refs_value, str(payload.get("evidence_level") or "observed"))
            evidence.extend(refs)
            endpoint = payload.get("endpoint_path") or payload.get("endpoint_expression")
            items.append({
                "interface_id": record.get("local_record_id") or record.get("record_occurrence_id"), "repo_id": record.get("repo_id"),
                "operation": payload.get("operation"), "direction": "outbound", "boundary_kind": "http_outbound", "protocol": "http",
                "endpoint_or_topic": endpoint, "base_url_property_key": payload.get("base_url_property_key"),
                "request_payload_type": payload.get("request_payload_type"), "response_payload_type": payload.get("response_payload_type"),
                "client_type": payload.get("client_receiver_type"), "evidence_level": payload.get("evidence_level"), "evidence_ids": ids,
            })
        # Prefer concrete endpoints over symbolic duplicates for the same operation.
        selected: dict[tuple[Any, Any], dict[str, Any]] = {}
        for item in items:
            key = (item.get("operation"), item.get("boundary_kind"))
            old = selected.get(key)
            symbolic = item.get("endpoint_or_topic") in _SYMBOLIC_ENDPOINTS
            if old is None or (old.get("endpoint_or_topic") in _SYMBOLIC_ENDPOINTS and not symbolic):
                selected[key] = item
        normalized = sorted(selected.values(), key=lambda x: (str(x.get("boundary_kind")), str(x.get("operation")), str(x.get("endpoint_or_topic"))))[:max_results]
        request = QueryRequest("list_integrations", self.scope, max_results=max_results)
        return self._result(request, normalized, summary={"integration_count": len(normalized)}, evidence=evidence)

    def list_events(self, *, max_results: int = 1000) -> QueryResult:
        return self.list_interfaces(boundary_kinds=("kafka_consume", "kafka_publish"), max_results=max_results)

    def list_data_objects(self, *, max_results: int = 100, representative: bool = True) -> QueryResult:
        if self._subject_only_system_description():
            records, total = self._system_description_records("storage_usage_summaries.json", max_items=max(10000, max_results))
            evidence: list[EvidenceRef] = []
            items: list[dict[str, Any]] = []
            for record in records:
                payload = _payload(record.get("payload_json"))
                target = str(payload.get("storage_target") or "")
                if not target or "test" in set(payload.get("source_sets") or ()):
                    continue
                ids, refs = self._evidence(str(record.get("repo_id") or "unknown"), str(record.get("record_occurrence_id")), payload.get("evidence") or (), str(payload.get("evidence_level") or "observed"))
                evidence.extend(refs)
                items.append({
                    "object_id": payload.get("storage_usage_summary_id") or record.get("local_record_id"),
                    "repo_id": record.get("repo_id"), "object_kind": "observed_storage_target",
                    "name": target, "qualified_name": target, "source_type": "observed_storage_usage",
                    "evidence_level": payload.get("evidence_level"), "column_count": 0, "key_count": 0,
                    "relationship_count": 0, "observed_relationship_count": 0, "index_count": 0,
                    "selection_score": int(payload.get("access_count") or 0) + int(payload.get("operation_count") or 0),
                    "access_count": payload.get("access_count"), "read_count": payload.get("read_count"),
                    "write_count": payload.get("write_count"), "mutation_count": payload.get("mutation_count"),
                    "evidence_ids": ids,
                })
            items.sort(key=(lambda item: (-int(item.get("selection_score") or 0), str(item.get("qualified_name")))) if representative else (lambda item: str(item.get("qualified_name"))))
            items = items[:max_results]
            request = QueryRequest("list_data_objects", self.scope, filters={"representative": representative}, max_results=max_results)
            return self._result(request, items, total=total, summary={"table_count": total, "selection_policy": "observed-storage-usage/v1", "source": "system-description/v1"}, evidence=evidence)

        tables, total = self._collect(self.query.list_tables, max_items=max(10000, max_results))
        items: list[dict[str, Any]] = []
        for table in tables:
            if table.get("is_test_source"):
                continue
            score = (
                int(table.get("relationship_count") or 0) * 6
                + int(table.get("observed_relationship_count") or 0) * 3
                + int(table.get("key_count") or 0) * 4
                + int(table.get("key_observation_count") or 0) * 2
                + min(int(table.get("column_count") or 0), 20)
                + min(int(table.get("index_count") or 0), 5)
            )
            items.append({
                "object_id": table.get("db_table_occurrence_id"), "repo_id": table.get("repo_id"), "object_kind": "table",
                "name": table.get("table_name"), "schema": table.get("schema_name"), "qualified_name": table.get("qualified_table_name"),
                "module_name": table.get("module_name"), "source_type": table.get("source_type"), "evidence_level": table.get("evidence_maturity_level"),
                "column_count": table.get("column_count"), "key_count": table.get("key_count"), "relationship_count": table.get("relationship_count"),
                "observed_relationship_count": table.get("observed_relationship_count"), "index_count": table.get("index_count"),
                "selection_score": score,
            })
        if representative:
            items.sort(key=lambda x: (-int(x.get("selection_score") or 0), str(x.get("qualified_name")), str(x.get("object_id"))))
        else:
            items.sort(key=lambda x: (str(x.get("qualified_name")), str(x.get("object_id"))))
        items = items[:max_results]
        evidence: list[EvidenceRef] = []
        for item in items:
            detail = self.query.get_table(str(item.get("object_id") or ""))
            ids: list[str] = []
            for ref in detail.get("evidence_refs") or ():
                if str(ref.get("owner_occurrence_id") or "") != str(item.get("object_id") or ""):
                    continue
                path = _source_path(ref.get("file_path") or _payload(ref.get("payload_json")).get("file"))
                if not path:
                    continue
                evidence_id = str(ref.get("evidence_ref_id") or stable_id("evidence", item.get("repo_id"), item.get("object_id"), path, ref.get("line_start"), ref.get("line_end")))
                ids.append(evidence_id)
                evidence.append(EvidenceRef(
                    evidence_id=evidence_id, repo_id=str(ref.get("repo_id") or item.get("repo_id") or "unknown"),
                    path=path, line_start=int(ref["line_start"]) if ref.get("line_start") is not None else None,
                    line_end=int(ref["line_end"]) if ref.get("line_end") is not None else None,
                    extractor=str(_payload(ref.get("payload_json")).get("extractor") or "") or None,
                    maturity=str(item.get("evidence_level") or "confirmed"),
                ))
            item["evidence_ids"] = sorted(set(ids))
            table_rows = detail.get("db_schema_tables") or ()
            if table_rows:
                item["description"] = table_rows[0].get("description")
        request = QueryRequest("list_data_objects", self.scope, filters={"representative": representative}, max_results=max_results)
        return self._result(request, items, total=total, summary={"table_count": total, "selection_policy": "relationship-key-usage-score/v1" if representative else "alphabetical/v1"}, evidence=evidence)

    def list_relationships(self, *, max_results: int = 500) -> QueryResult:
        if self._subject_only_system_description():
            request = QueryRequest("list_relationships", self.scope, max_results=max_results)
            return self._result(request, [], total=0, summary={"relationship_count": 0, "status": "not_materialized_in_system-description/v1"})
        relationships, total = self._collect(self.query.list_relationships, max_items=max_results)
        normalized: list[dict[str, Any]] = []
        evidence: list[EvidenceRef] = []
        for item in relationships:
            relationship_id = str(item.get("relationship_observation_occurrence_id") or "")
            detail = self.query.table_relationship_detail(relationship_id) if relationship_id else {}
            ids: list[str] = []
            for ref in detail.get("evidence_refs") or ():
                path = _source_path(ref.get("file_path") or _payload(ref.get("payload_json")).get("file"))
                if not path:
                    continue
                evidence_id = str(ref.get("evidence_ref_id") or stable_id("evidence", item.get("repo_id"), relationship_id, path, ref.get("line_start"), ref.get("line_end")))
                ids.append(evidence_id)
                evidence.append(EvidenceRef(
                    evidence_id=evidence_id, repo_id=str(ref.get("repo_id") or item.get("repo_id") or "unknown"),
                    path=path, line_start=int(ref["line_start"]) if ref.get("line_start") is not None else None,
                    line_end=int(ref["line_end"]) if ref.get("line_end") is not None else None,
                    extractor=str(_payload(ref.get("payload_json")).get("kind") or "") or None,
                    maturity="observed",
                ))
            column_pairs = [
                {"left_column": pair.get("left_column_name") or pair.get("left_unresolved_name"),
                 "operator": pair.get("operator"),
                 "right_column": pair.get("right_column_name") or pair.get("right_unresolved_name")}
                for pair in detail.get("column_pairs") or ()
            ]
            normalized.append({
                "relationship_id": relationship_id, "repo_id": item.get("repo_id"),
                "relation_kind": item.get("relation_kind"), "source_kind": item.get("source_kind"), "join_type": item.get("join_type"),
                "left_table": item.get("left_qualified_table_name") or item.get("left_table_name"),
                "right_table": item.get("right_qualified_table_name") or item.get("right_table_name"),
                "column_pair_count": item.get("column_pair_count"), "column_pairs": column_pairs,
                "matched_declared_keys": item.get("matched_declared_keys_json") or [], "evidence_ids": sorted(set(ids)),
            })
        request = QueryRequest("list_relationships", self.scope, max_results=max_results)
        return self._result(request, normalized, total=total, summary={"relationship_count": total}, evidence=evidence)

    def get_analysis_coverage(self, *, max_results: int = 100) -> QueryResult:
        if self._subject_only_system_description():
            manifest = self.query.manifest()
            source = dict((manifest.get("metadata") or {}).get("coverage") or {})
            coverage = {
                "status": source.get("coverage_status") or manifest.get("build_status") or "unknown",
                "summary": {
                    "source_file_count": source.get("source_file_count"),
                    "payload_artifact_count": source.get("payload_artifact_count"),
                    "missing_payload_artifact_count": source.get("missing_payload_artifact_count"),
                    "coverage_status": source.get("coverage_status"),
                },
                "limitations": [],
                "source": "system-description/v1",
            }
            request = QueryRequest("get_analysis_coverage", self.scope, max_results=max_results)
            return self._result(request, [coverage], total=1, summary=dict(coverage["summary"]))
        coverage = self.query.analysis_coverage(max_limitations=max_results)
        request = QueryRequest("get_analysis_coverage", self.scope, max_results=max_results)
        return self._result(
            request,
            [coverage],
            total=1,
            summary=dict(coverage.get("summary") or {}),
        )

    def get_gap_summary(self, *, max_results: int = 100) -> QueryResult:
        if self._subject_only_system_description():
            scenarios, _ = self._system_description_records("system_scenarios.json", max_items=1000)
            unresolved = sum(1 for record in scenarios if not (_payload(record.get("payload_json")).get("storage_touches") or _payload(record.get("payload_json")).get("external_calls")))
            gaps: list[Gap] = []
            if unresolved:
                gaps.append(Gap(
                    gap_id=stable_id("gap_summary", self.scope.scope_id, "scenario_composition", "downstream_boundary_not_observed"),
                    repo_id=self.scope.repository_ids[0] if self.scope.repository_ids else "unknown",
                    category="scenario_composition", missing_fact_kind="downstream_boundary_not_observed",
                    required_for_operation=None, count=unresolved,
                ))
            request = QueryRequest("get_gap_summary", self.scope, max_results=max_results)
            return self._result(request, [gap.to_dict() for gap in gaps], total=len(gaps), summary={"group_count": len(gaps), "gap_count": unresolved, "source": "system-description/v1"}, gaps=gaps)
        rows, total = self._collect(self.query.missing_fact_summary, max_items=max_results)
        gaps = [Gap(
            gap_id=stable_id("gap_summary", row.get("repo_id"), row.get("category"), row.get("missing_fact_kind"), row.get("required_for_operation")),
            repo_id=str(row.get("repo_id") or "unknown"), category=str(row.get("category") or "unknown"),
            missing_fact_kind=str(row.get("missing_fact_kind") or "unknown"), required_for_operation=row.get("required_for_operation"),
            count=int(row.get("missing_fact_count") or 0),
        ) for row in rows]
        request = QueryRequest("get_gap_summary", self.scope, max_results=max_results)
        return self._result(request, [gap.to_dict() for gap in gaps], total=total, summary={"group_count": total, "gap_count": sum(gap.count for gap in gaps)}, gaps=gaps)

    def get_representative_journeys(self, *, max_results: int = 10) -> QueryResult:
        scenarios, total = self._collect(self.query.system_scenarios, max_items=1000)
        items: list[dict[str, Any]] = []
        for record in scenarios:
            payload = _payload(record.get("payload_json"))
            item = {
                "journey_id": payload.get("scenario_id") or record.get("local_record_id"), "repo_id": record.get("repo_id"),
                "operation": payload.get("operation"), "evidence_level": payload.get("evidence_level"),
                "entrypoints": payload.get("entrypoints") or [], "external_calls": payload.get("external_calls") or [],
                "storage_touches": payload.get("storage_touches") or [], "is_complete": bool(payload.get("external_calls") or payload.get("storage_touches")),
            }
            score = len(item["external_calls"]) * 4 + len(item["storage_touches"]) * 4 + len(item["entrypoints"])
            item["selection_score"] = score
            items.append(item)
        items.sort(key=lambda x: (-int(x["selection_score"]), str(x.get("operation")), str(x.get("journey_id"))))
        selected = items[:max_results]
        request = QueryRequest("get_representative_journeys", self.scope, max_results=max_results)
        return self._result(request, selected, total=total, summary={"scenario_count": total, "complete_selected": sum(1 for i in selected if i["is_complete"]), "selection_policy": "boundary-storage-external-coverage/v1"})
