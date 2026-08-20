from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from prepared_knowledge_runtime import KnowledgeLayerQuery
from prepared_knowledge_runtime.repository_inventory_queries import RepositoryInventoryUnavailableError

from .query_source import KnowledgeArtifactSource


class KnowledgeArtifactUnavailableError(RuntimeError):
    pass


class SqlAnalysisUnavailableError(RuntimeError):
    pass


class SqlColumnUsageNotFoundError(LookupError):
    pass


class PhysicalModelUnavailableError(RuntimeError):
    pass


class PhysicalModelTableNotFoundError(LookupError):
    pass


class AttributeExtensionContextUnavailableError(RuntimeError):
    pass


class KnowledgeQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> "KnowledgeQueryAdapter": ...


class CachedKnowledgeQueryFactory:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[tuple[int, int] | None, tuple[int, int] | None], KnowledgeQueryAdapter]] = {}
        self._lock = RLock()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> "KnowledgeQueryAdapter":
        path = system.database_path.resolve()
        database_signature = self._signature(path)
        manifest = system.manifest_path.resolve() if system.manifest_path is not None else None
        manifest_signature = self._signature(manifest) if manifest is not None else None
        signature = (database_signature, manifest_signature)
        if database_signature is None:
            raise KnowledgeArtifactUnavailableError(
                f"typed knowledge artifact is unavailable for system {system.system_id}: {path}"
            )
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            adapter = KnowledgeQueryAdapter(path, manifest=manifest)
            self._cache[key] = (signature, adapter)
            return adapter


class KnowledgeQueryAdapter:
    """Producer-neutral adapter over generic KLC capabilities.

    This adapter exposes KLC capabilities that have their own typed query contracts,
    including SQL and physical-model knowledge. API pagination is offset-based; KLC's
    internal continuation tokens stay behind this boundary.
    """

    EXTERNAL_RELATION_KINDS = ("physical", "physical_template")

    def __init__(self, artifact: str | Path, *, manifest: str | Path | None = None) -> None:
        self.query = KnowledgeLayerQuery.from_database(artifact, manifest=manifest)

    def capabilities(self) -> tuple[str, ...]:
        return self.query.capabilities()

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities()

    def get_logical_storage_object_context(self, object_id: str) -> dict[str, Any]:
        if not self.has_capability("common.logical-storage-mapping"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose logical-storage mapping")
        return self.query.get_logical_storage_object_context(object_id)

    def get_model_storage_object_context(self, source_fqcn: str) -> dict[str, Any]:
        if not self.has_capability("common.model-storage-semantics"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose model-storage semantics")
        return self.query.get_model_storage_object_context(source_fqcn)

    def resolve_attribute_paths(
        self,
        *,
        source: str,
        target: str | None,
        selected_repo_ids: list[str],
        max_hops: int,
        max_paths: int,
        max_branching: int,
        allowed_edge_kinds: list[str],
        minimum_confidence: str,
        knowledge_view: str,
    ) -> dict[str, Any]:
        if not self.has_capability("workspace.attribute-path-resolver"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose attribute-path resolution")
        return self.query.resolve_attribute_paths(
            source,
            target=target,
            selected_repo_ids=selected_repo_ids,
            max_hops=max_hops,
            max_paths=max_paths,
            max_branching=max_branching,
            allowed_edge_kinds=allowed_edge_kinds or None,
            minimum_confidence=minimum_confidence,
            knowledge_view=knowledge_view,
        )

    def sql_relation_count(self, *, repo_id: str | None = None) -> int:
        if not self.has_capability("common.sql-analysis"):
            return 0
        result = self.query.list_sql_relations(
            repo_id=repo_id,
            relation_kind=None,
            view="all",
            include_fields=False,
            max_results=1,
        )
        return int(result.get("total_count") or 0)

    def list_sql_relations(
        self,
        *,
        repo_id: str | None,
        relation_kind: str | None,
        usage_role: str | None,
        view: str,
        search: str | None,
        include_fields: bool,
        max_evidence_per_role: int,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-relation-fields"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL relation/field inventory")
        if not self.has_capability("common.sql-relation-semantic-roles"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL relation semantic roles")

        relation_kinds = (relation_kind,) if relation_kind else self.EXTERNAL_RELATION_KINDS
        totals: dict[str, int] = {}
        for kind in relation_kinds:
            first = self.query.list_sql_relations(
                repo_id=repo_id,
                relation_kind=kind,
                usage_role=usage_role,
                view=view,
                token=search or "",
                include_fields=include_fields,
                max_evidence_per_role=max_evidence_per_role,
                max_results=1,
            )
            totals[kind] = int(first.get("total_count") or 0)

        requested_start = offset
        remaining = limit
        items: list[dict[str, Any]] = []
        consumed_before_kind = 0
        for kind in relation_kinds:
            kind_total = totals[kind]
            if requested_start >= consumed_before_kind + kind_total:
                consumed_before_kind += kind_total
                continue
            local_offset = max(0, requested_start - consumed_before_kind)
            if remaining > 0:
                items.extend(
                    self._read_kind_page(
                        repo_id=repo_id,
                        relation_kind=kind,
                        usage_role=usage_role,
                        view=view,
                        search=search,
                        include_fields=include_fields,
                        max_evidence_per_role=max_evidence_per_role,
                        offset=local_offset,
                        limit=remaining,
                    )
                )
                remaining = limit - len(items)
            consumed_before_kind += kind_total
            if remaining <= 0:
                break

        coverage = self.query.sql_analysis_coverage(repo_id=repo_id)
        coverage["relation_classification"] = self.query.sql_relation_semantic_role_coverage(repo_id=repo_id)
        coverage["source_inventory"] = self.query.sql_source_inventory_coverage(repo_id=repo_id)
        return {
            "items": items,
            "total_count": sum(totals.values()),
            "coverage": coverage,
        }

    def export_sql_source_inventory(
        self,
        *,
        repo_id: str | None,
        relation_kind: str | None,
        usage_role: str | None,
        view: str,
        search: str | None,
        max_evidence_per_role: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-source-inventory-export"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL source inventory export")
        relation_kinds = (relation_kind,) if relation_kind else self.EXTERNAL_RELATION_KINDS
        items: list[dict[str, Any]] = []
        coverage: dict[str, Any] = {}
        for kind in relation_kinds:
            result = self.query.export_sql_source_inventory(
                repo_id=repo_id,
                relation_kind=kind,
                usage_role=usage_role,
                view=view,
                token=search or "",
                max_evidence_per_role=max_evidence_per_role,
            )
            items.extend(result.get("items") or ())
            coverage = dict(result.get("coverage") or coverage)
        items.sort(key=lambda item: (
            str(item.get("repo_id") or "").casefold(),
            str(item.get("repo_id") or ""),
            str(item.get("relation_identity") or "").casefold(),
            str(item.get("relation_identity") or ""),
            str(item.get("relation_kind") or ""),
            str(item.get("relation_id") or ""),
        ))
        return {
            "schema_version": "sql-source-inventory/v1",
            "filters": {
                "repo_id": repo_id,
                "relation_kind": relation_kind,
                "usage_role": usage_role,
                "view": view,
                "search": search,
                "max_evidence_per_role": max_evidence_per_role,
            },
            "item_count": len(items),
            "items": items,
            "coverage": coverage,
        }

    def list_sql_target_column_lineage(
        self,
        *,
        target_relation: str,
        target_column: str | None,
        repo_id: str | None,
        lineage_status: str | None,
        include_gaps: bool,
        max_gaps: int,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-target-column-lineage"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose target-column SQL lineage"
            )

        token = ""
        current_offset = 0
        selected: list[dict[str, Any]] = []
        first_result: dict[str, Any] | None = None
        while True:
            page = self.query.list_sql_target_column_lineage(
                target_relation,
                target_column=target_column,
                repo_id=repo_id,
                lineage_status=lineage_status,
                include_gaps=include_gaps,
                max_gaps=max_gaps,
                max_results=500,
                page_token=token,
            )
            if page.get("not_available"):
                raise SqlAnalysisUnavailableError(
                    "knowledge layer does not expose target-column SQL lineage"
                )
            if first_result is None:
                first_result = dict(page)
            page_items = [dict(item) for item in page.get("items") or ()]
            page_end = current_offset + len(page_items)
            if offset < page_end and len(selected) < limit:
                start = max(0, offset - current_offset)
                selected.extend(page_items[start : start + (limit - len(selected))])
            next_token = page.get("next_token")
            if len(selected) >= limit or not next_token or not page_items:
                break
            token = str(next_token)
            current_offset = page_end

        result = first_result or {
            "summary": {}, "gaps": [], "gap_count": 0,
            "gaps_truncated": False, "gaps_by_kind": {}, "total_count": 0,
        }
        return {
            "schema_version": str(result.get("schema_version") or "sql-target-column-lineage/v1"),
            "filters": dict(result.get("filters") or {}),
            "items": selected,
            "total_count": int(result.get("total_count") or 0),
            "summary": dict(result.get("summary") or {}),
            "gaps": [dict(item) for item in result.get("gaps") or ()],
            "gap_count": int(result.get("gap_count") or 0),
            "gaps_truncated": bool(result.get("gaps_truncated")),
            "gaps_by_kind": {
                str(key): int(value) for key, value in (result.get("gaps_by_kind") or {}).items()
            },
        }

    def list_sql_target_value_sources(
        self,
        *,
        target_relation: str,
        target_column: str | None,
        include_gaps: bool,
        max_gaps: int,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Return the compact product S2T projection from KLC value-source knowledge.

        Pagination is by target column. KLC stores one row per proven source value;
        this adapter groups those rows and keeps gap-only targets visible without
        interpreting SQL or inferring missing origins in the API layer.
        """
        if not self.has_capability("common.sql-target-value-source-mapping"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose product SQL target/source mapping"
            )

        rows: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        token = ""
        while True:
            page = self.query.list_sql_target_value_sources(
                target_relation,
                target_column=target_column,
                include_gaps=include_gaps,
                # Read enough diagnostics to retain gap-only target columns. The
                # public API applies max_gaps after grouping/projection.
                max_gaps=max(max_gaps, 5000) if include_gaps else 0,
                max_results=500,
                page_token=token,
            )
            if page.get("not_available"):
                raise SqlAnalysisUnavailableError(
                    "knowledge layer does not expose product SQL target/source mapping"
                )
            if first is None:
                first = dict(page)
            rows.extend(dict(item) for item in page.get("items") or ())
            next_token = page.get("next_token")
            if not next_token:
                break
            token = str(next_token)

        first = first or {}
        all_gaps = [dict(item) for item in first.get("gaps") or ()] if include_gaps else []
        columns: set[str] = {
            str(row.get("target_column") or "").strip()
            for row in rows
            if str(row.get("target_column") or "").strip()
        }
        columns.update(
            str(gap.get("target_column") or "").strip()
            for gap in all_gaps
            if str(gap.get("target_column") or "").strip()
        )
        if target_column:
            columns = {value for value in columns if value.casefold() == target_column.casefold()}
        ordered_columns = sorted(columns, key=lambda value: (value.casefold(), value))

        rows_by_column: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            column = str(row.get("target_column") or "").strip()
            if column:
                rows_by_column.setdefault(column.casefold(), []).append(row)
        gaps_by_column: dict[str, list[dict[str, Any]]] = {}
        for gap in all_gaps:
            column = str(gap.get("target_column") or "").strip()
            if column:
                gaps_by_column.setdefault(column.casefold(), []).append(gap)

        mappings: list[dict[str, Any]] = []
        for column in ordered_columns[offset : offset + limit]:
            source_rows = rows_by_column.get(column.casefold(), [])
            deduped: dict[tuple[str, str], dict[str, Any]] = {}
            for row in source_rows:
                relation = str(row.get("source_sql_relation_name") or "").strip()
                source_column = str(row.get("source_sql_column") or "").strip()
                if not relation or not source_column:
                    continue
                key = (relation.casefold(), source_column.casefold())
                prior = deduped.get(key)
                if prior is None or str(row.get("mapping_status") or "") < str(prior.get("mapping_status") or ""):
                    deduped[key] = row
            sources = [
                {
                    "relation": str(row.get("source_sql_relation_name") or ""),
                    "column": str(row.get("source_sql_column") or ""),
                    "status": str(row.get("mapping_status") or "resolved"),
                }
                for row in sorted(
                    deduped.values(),
                    key=lambda item: (
                        str(item.get("source_sql_relation_name") or "").casefold(),
                        str(item.get("source_sql_relation_name") or ""),
                        str(item.get("source_sql_column") or "").casefold(),
                        str(item.get("source_sql_column") or ""),
                    ),
                )
            ]
            statuses = {str(row.get("mapping_status") or "").strip().casefold() for row in source_rows}
            if not sources:
                mapping_status = "unresolved"
            elif statuses and statuses <= {"complete", "confirmed", "resolved"}:
                mapping_status = "complete"
            else:
                mapping_status = "partial"
            mappings.append(
                {
                    "target_column": column,
                    "sources": sources,
                    "mapping_status": mapping_status,
                    "source_count": len(sources),
                    "dependency_count": 0,
                }
            )

        source_identities = {
            (str(row.get("source_sql_relation_name") or "").casefold(), str(row.get("source_sql_column") or "").casefold())
            for row in rows
            if str(row.get("source_sql_relation_name") or "").strip()
            and str(row.get("source_sql_column") or "").strip()
        }
        status_by_column: dict[str, str] = {}
        for column in ordered_columns:
            source_rows = rows_by_column.get(column.casefold(), [])
            if not source_rows:
                status_by_column[column] = "unresolved"
                continue
            statuses = {str(row.get("mapping_status") or "").strip().casefold() for row in source_rows}
            status_by_column[column] = "complete" if statuses and statuses <= {"complete", "confirmed", "resolved"} else "partial"

        public_gaps = []
        for gap in all_gaps[:max_gaps]:
            evidence = gap.get("evidence") if isinstance(gap.get("evidence"), dict) else {}
            owner_id = str(gap.get("root_projection_id") or gap.get("local_lineage_id") or gap.get("target_column") or gap.get("gap_id") or "unknown")
            public_gaps.append(
                {
                    "gap_id": str(gap.get("gap_id") or "unknown_gap"),
                    "gap_kind": str(gap.get("gap_kind") or "unresolved"),
                    "severity": str(gap.get("impact") or "unknown"),
                    "owner_id": owner_id,
                    "message": str(gap.get("mapping_basis") or gap.get("gap_kind") or "unresolved target/source mapping"),
                    "details": {
                        "target_column": gap.get("target_column"),
                        "workflow_context_file": gap.get("workflow_context_file"),
                        "impact": gap.get("impact"),
                        "mapping_basis": gap.get("mapping_basis"),
                        "evidence": evidence,
                    },
                }
            )

        unresolved_placeholder_count = len({
            (str(row.get("source_sql_relation_name") or "").casefold(), str(row.get("source_sql_column") or "").casefold())
            for row in rows
            if "${" in str(row.get("source_sql_relation_name") or "")
        })
        return {
            "schema_version": "target-source-mapping/v1",
            "target_relation": target_relation,
            "filters": {"target_column": target_column},
            "mappings": mappings,
            "total_count": len(ordered_columns),
            "summary": {
                "target_column_count": len(ordered_columns),
                "source_count": len(source_identities),
                "dependency_count": 0,
                "complete_count": sum(1 for value in status_by_column.values() if value == "complete"),
                "partial_count": sum(1 for value in status_by_column.values() if value == "partial"),
                "no_source_count": sum(1 for value in status_by_column.values() if value == "unresolved"),
                "unresolved_placeholder_source_count": unresolved_placeholder_count,
            },
            "gaps": public_gaps,
            "gap_count": int(first.get("gap_count") or len(all_gaps)),
            "gaps_truncated": int(first.get("gap_count") or len(all_gaps)) > len(public_gaps),
        }

    def get_sql_field_calculation(
        self,
        *,
        target_relation: str,
        target_column: str,
        repo_id: str | None,
        include_gaps: bool,
        max_gaps: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-field-calculation"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL field calculation and origin"
            )
        result = self.query.get_sql_field_calculation(
            target_relation,
            target_column,
            repo_id=repo_id,
            include_gaps=include_gaps,
            max_gaps=max_gaps,
        )
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL field calculation and origin"
            )
        return self._normalize_json_values(result)

    def get_workspace_sql_catalog(self) -> dict[str, Any]:
        if not self.has_capability("common.workspace-sql-catalog"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose a workspace SQL catalog"
            )
        result = self.query.get_workspace_sql_catalog()
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose a workspace SQL catalog"
            )
        return self._normalize_json_values(result)

    @classmethod
    def _normalize_json_values(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls._normalize_json_values(item) for item in value]
        if isinstance(value, dict):
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                if key.endswith("_json") and isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
                normalized[key] = cls._normalize_json_values(item)
            return normalized
        return value

    def _read_workspace_page(
        self,
        method_name: str,
        *,
        required_capability: str,
        offset: int,
        limit: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self.has_capability(required_capability):
            raise KnowledgeArtifactUnavailableError(
                f"knowledge layer does not expose required capability: {required_capability}"
            )
        method = getattr(self.query, method_name)
        token = ""
        current_offset = 0
        selected: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        while len(selected) < limit:
            try:
                page = method(max_results=500, page_token=token, **kwargs)
            except RepositoryInventoryUnavailableError as exc:
                raise KnowledgeArtifactUnavailableError(str(exc)) from exc
            if page.get("not_available"):
                raise KnowledgeArtifactUnavailableError(
                    f"knowledge layer query is unavailable: {method_name}"
                )
            if first is None:
                first = dict(page)
            page_items = [dict(item) for item in page.get("items") or ()]
            page_end = current_offset + len(page_items)
            if offset < page_end:
                start = max(0, offset - current_offset)
                selected.extend(page_items[start : start + (limit - len(selected))])
            next_token = page.get("next_token")
            if not next_token or not page_items:
                break
            token = str(next_token)
            current_offset = page_end
        first = first or {}
        return {
            "query_kind": str(first.get("kind") or method_name),
            "items": self._normalize_json_values(selected),
            "total_count": int(first.get("total_count") or 0),
        }

    def list_system_interactions(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "system_interactions",
            required_capability="workspace.system-interactions",
            offset=offset, limit=limit, **kwargs,
        )

    def list_system_boundary_interactions(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "system_boundary_interactions",
            required_capability="workspace.system-interactions",
            offset=offset, limit=limit, **kwargs,
        )

    def list_repository_interaction_boundaries(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "repository_interaction_boundaries",
            required_capability="workspace.repository-interaction-boundaries",
            offset=offset, limit=limit, **kwargs,
        )

    def list_system_interaction_execution_contexts(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "system_interaction_execution_contexts",
            required_capability="workspace.system-interactions",
            offset=offset, limit=limit, **kwargs,
        )

    def list_system_interaction_field_contracts(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "system_interaction_field_contracts",
            required_capability="workspace.system-interaction-field-contracts",
            offset=offset, limit=limit, **kwargs,
        )

    def list_system_interaction_diagnostics(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "system_interaction_diagnostics",
            required_capability="workspace.system-interactions",
            offset=offset, limit=limit, **kwargs,
        )

    def list_repository_interaction_coverage(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_workspace_page(
            "repository_interaction_coverage",
            required_capability="workspace.repository-interaction-coverage",
            offset=offset, limit=limit, **kwargs,
        )

    def repository_inventory_summary(self) -> dict[str, Any]:
        if not self.has_capability("common.repository-inventory"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository inventory")
        try:
            return self._normalize_json_values(self.query.repository_inventory_summary())
        except RepositoryInventoryUnavailableError as exc:
            raise KnowledgeArtifactUnavailableError(str(exc)) from exc

    def repository_inventory_coverage(self) -> dict[str, Any]:
        if not self.has_capability("common.repository-inventory"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository inventory")
        try:
            return self._normalize_json_values(self.query.repository_inventory_coverage())
        except RepositoryInventoryUnavailableError as exc:
            raise KnowledgeArtifactUnavailableError(str(exc)) from exc

    def repository_inventory_portfolio_snapshot(self) -> dict[str, Any]:
        if not self.has_capability("common.repository-inventory"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository inventory")
        try:
            return self._normalize_json_values(self.query.repository_inventory_portfolio_snapshot())
        except RepositoryInventoryUnavailableError as exc:
            raise KnowledgeArtifactUnavailableError(str(exc)) from exc

    def _read_repository_inventory_page(self, method_name: str, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.repository-inventory"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository inventory")
        method = getattr(self.query, method_name)
        token = ""
        current_offset = 0
        selected: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        while len(selected) < limit:
            page = method(max_results=500, page_token=token, **kwargs)
            if first is None:
                first = dict(page)
            page_items = [dict(item) for item in page.get("items") or ()]
            page_end = current_offset + len(page_items)
            if offset < page_end:
                start = max(0, offset - current_offset)
                selected.extend(page_items[start:start + (limit - len(selected))])
            next_token = page.get("next_token")
            if not next_token or not page_items:
                break
            token = str(next_token)
            current_offset = page_end
        return {
            "query_kind": str((first or {}).get("kind") or method_name),
            "items": self._normalize_json_values(selected),
            "total_count": int((first or {}).get("total_count") or 0),
        }

    def list_repository_inventory_technologies(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_technologies", offset=offset, limit=limit, **kwargs)

    def list_repository_inventory_interfaces(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_interfaces", offset=offset, limit=limit, **kwargs)

    def list_repository_inventory_structural_families(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_structural_families", offset=offset, limit=limit, **kwargs)

    def list_repository_inventory_discovery(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_discovery", offset=offset, limit=limit, **kwargs)

    def list_repository_inventory_coverage_gaps(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_coverage_gaps", offset=offset, limit=limit, **kwargs)

    def list_repository_inventory_source_occurrences(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.repository-source-occurrences"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository source occurrences")
        return self._read_repository_inventory_page("list_repository_inventory_source_occurrences", offset=offset, limit=limit, **kwargs)

    def get_repository_inventory_source_occurrence(self, occurrence_id: str) -> dict[str, Any] | None:
        if not self.has_capability("common.repository-source-occurrences"):
            raise KnowledgeArtifactUnavailableError("knowledge layer does not expose repository source occurrences")
        return self._normalize_json_values(self.query.get_repository_inventory_source_occurrence(occurrence_id))

    def list_repository_inventory_diagnostics(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        return self._read_repository_inventory_page("list_repository_inventory_diagnostics", offset=offset, limit=limit, **kwargs)

    def physical_model_table_count(self) -> int:
        if not self.has_capability("common.physical-model.tables"):
            return 0
        summary = self.query.physical_model_summary()
        return int((summary.get("counts") or {}).get("tables") or 0)

    def physical_model_summary(self) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.query"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model queries")
        result = self.query.physical_model_summary()
        if result.get("not_available"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model facts")
        return self._normalize_json_values(result)

    def _read_physical_page(
        self,
        method_name: str,
        *,
        offset: int,
        limit: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        method = getattr(self.query, method_name)
        token = ""
        current_offset = 0
        selected: list[dict[str, Any]] = []
        first: dict[str, Any] | None = None
        while len(selected) < limit:
            page = method(max_results=500, page_token=token, **kwargs)
            if page.get("not_available"):
                raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model facts")
            if first is None:
                first = dict(page)
            page_items = [dict(item) for item in page.get("items") or ()]
            page_end = current_offset + len(page_items)
            if offset < page_end:
                start = max(0, offset - current_offset)
                selected.extend(page_items[start : start + (limit - len(selected))])
            next_token = page.get("next_token")
            if not next_token or not page_items:
                break
            token = str(next_token)
            current_offset = page_end
        return {
            "schema_version": str((first or {}).get("schema_version") or "physical-model-query/v1"),
            "items": self._normalize_json_values(selected),
            "total_count": int((first or {}).get("total_count") or 0),
        }

    def list_physical_model_tables(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.tables"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model tables")
        return self._read_physical_page(
            "list_physical_model_tables", offset=offset, limit=limit, **kwargs
        )

    def get_physical_model_table(self, table_id: str) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.tables"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model tables")
        result = self.query.get_physical_model_table(table_id)
        if result.get("not_available"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model tables")
        if result.get("not_found"):
            raise PhysicalModelTableNotFoundError(table_id)
        return self._normalize_json_values(result)

    def list_physical_model_columns(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.columns"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model columns")
        return self._read_physical_page(
            "list_physical_model_columns", offset=offset, limit=limit, **kwargs
        )

    def list_physical_model_keys(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.keys"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model keys")
        return self._read_physical_page(
            "list_physical_model_keys", offset=offset, limit=limit, **kwargs
        )

    def list_physical_model_relationships(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.relationships"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model relationships")
        return self._read_physical_page(
            "list_physical_model_relationships", offset=offset, limit=limit, **kwargs
        )

    def list_physical_model_gaps(self, *, offset: int, limit: int, **kwargs: Any) -> dict[str, Any]:
        if not self.has_capability("common.physical-model.gaps"):
            raise PhysicalModelUnavailableError("knowledge layer does not expose physical-model gaps")
        return self._read_physical_page(
            "list_physical_model_gaps", offset=offset, limit=limit, **kwargs
        )

    def find_sql_target_candidates(
        self,
        *,
        repo_id: str | None,
        source_relation_hints: list[str] | tuple[str, ...] | None,
        source_column_hints: list[str] | tuple[str, ...] | None,
        business_entity_hints: list[str] | tuple[str, ...] | None,
        max_results: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-target-resolution"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL target resolution"
            )
        result = self.query.find_sql_target_candidates(
            repo_id=repo_id,
            source_relation_hints=source_relation_hints,
            source_column_hints=source_column_hints,
            business_entity_hints=business_entity_hints,
            max_results=max_results,
        )
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL target resolution"
            )
        return self._normalize_json_values(result)

    def resolve_sql_attribute_insertion_context(
        self,
        *,
        target_relation: str,
        repo_id: str | None,
        source_relation_hints: list[str] | tuple[str, ...],
        source_column_hints: list[str] | tuple[str, ...] | None,
        max_results: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-attribute-insertion-context"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL attribute insertion context"
            )
        result = self.query.resolve_sql_attribute_insertion_context(
            target_relation,
            repo_id=repo_id,
            source_relation_hints=source_relation_hints,
            source_column_hints=source_column_hints,
            max_results=max_results,
        )
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError(
                "knowledge layer does not expose SQL attribute insertion context"
            )
        return self._normalize_json_values(result)

    def list_attribute_extension_join_semantics(
        self,
        *,
        source_type: str | None,
        source_field: str | None,
        target_type: str | None,
        join_method: str | None,
        confidence: str | None,
        sql_generation_status: str | None,
        search: str | None,
        offset: int,
        limit: int,
        include_gaps: bool = True,
        max_gaps: int = 100,
    ) -> dict[str, Any]:
        result = self.query.list_attribute_extension_join_semantics(
            source_type=source_type,
            source_field=source_field,
            target_type=target_type,
            join_method=join_method,
            confidence=confidence,
            sql_generation_status=sql_generation_status,
            search=search,
            offset=offset,
            limit=limit,
            include_gaps=include_gaps,
            max_gaps=max_gaps,
        )
        if result.get("not_available"):
            raise AttributeExtensionContextUnavailableError(
                "knowledge layer does not expose data-model attribute-extension context"
            )
        return result

    def get_aisl_knowledge_item(self, *, model_kind: str, item_kind: str, local_id: str) -> dict[str, Any]:
        result = self.query.get_aisl_knowledge_item(model_kind=model_kind, item_kind=item_kind, local_id=local_id)
        return self._normalize_json_values(result)

    def summarize_code_declared_model(
        self,
        *,
        repo_id: str | None,
        type_annotations: tuple[str, ...] = (),
        exclude_field_annotations: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not self.has_capability("common.code-declared-data-model"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose the code-declared data model"
            )
        result = self.query.summarize_code_declared_model(
            repo_id=repo_id,
            type_annotations=type_annotations,
            exclude_field_annotations=exclude_field_annotations,
        )
        if result.get("not_available"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose code-declared data-model facts"
            )
        return self._normalize_json_values(result)

    def list_code_declared_objects(
        self,
        *,
        repo_id: str | None,
        search: str | None,
        include_fields: bool,
        type_annotations: tuple[str, ...] = (),
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.code-declared-data-model"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose the code-declared data model"
            )
        result = self.query.list_code_declared_objects(
            repo_id=repo_id,
            search=search,
            include_fields=include_fields,
            type_annotations=type_annotations,
            offset=offset,
            limit=limit,
        )
        if result.get("not_available"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose code-declared data-model facts"
            )
        return self._normalize_json_values(result)

    def get_code_declared_object(self, object_id: str) -> dict[str, Any]:
        if not self.has_capability("common.code-declared-data-model"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose the code-declared data model"
            )
        result = self.query.get_code_declared_object(object_id)
        if result.get("not_available"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose code-declared data-model facts"
            )
        return self._normalize_json_values(result)

    def list_relation_materializations(
        self,
        *,
        output_table_name: str | None,
        query_id: str | None,
        workflow_context_file: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if not self.has_capability("common.relation-materialization"):
            raise KnowledgeArtifactUnavailableError(
                "knowledge layer does not expose relation materializations"
            )
        token = ""
        current_offset = 0
        while True:
            page = self.query.list_relation_materializations(
                output_table_name=output_table_name,
                query_id=query_id,
                workflow_context_file=workflow_context_file,
                max_results=min(500, max(limit + offset, 1)),
                page_token=token,
            )
            if page.get("not_available"):
                raise KnowledgeArtifactUnavailableError(
                    "knowledge layer does not expose relation materialization facts"
                )
            items = list(page.get("items") or ())
            total = int(page.get("total_count") or 0)
            if current_offset + len(items) >= offset or not page.get("next_token"):
                start = max(0, offset - current_offset)
                return {
                    "schema_version": str(page.get("schema_version") or "relation-materialization-query/v1"),
                    "filters": dict(page.get("filters") or {
                        "output_table_name": output_table_name,
                        "query_id": query_id,
                        "workflow_context_file": workflow_context_file,
                    }),
                    "items": items[start:start + limit],
                    "total_count": total,
                }
            current_offset += len(items)
            token = str(page.get("next_token") or "")

    def get_sql_query_context(
        self,
        *,
        repo_id: str,
        query_id: str,
        scope_id: str | None,
    ) -> dict[str, Any]:
        if not self.has_capability("common.sql-analysis"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL analysis facts")
        result = self.query.get_sql_query_context(
            repo_id=repo_id, query_id=query_id, scope_id=scope_id
        )
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL query context")
        return self._normalize_json_values(result)

    def get_sql_column_usage_context(self, sql_column_usage_id: str) -> dict[str, Any]:
        if not self.has_capability("common.sql-analysis"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL analysis facts")
        result = self.query.get_sql_column_usage_context(sql_column_usage_id)
        if result.get("not_available"):
            raise SqlAnalysisUnavailableError("knowledge layer does not expose SQL column usage context")
        if result.get("not_found"):
            raise SqlColumnUsageNotFoundError(sql_column_usage_id)
        return result

    def _read_kind_page(
        self,
        *,
        repo_id: str | None,
        relation_kind: str,
        usage_role: str | None,
        view: str,
        search: str | None,
        include_fields: bool,
        max_evidence_per_role: int,
        offset: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        token = ""
        current_offset = 0
        selected: list[dict[str, Any]] = []
        while len(selected) < limit:
            page = self.query.list_sql_relations(
                repo_id=repo_id,
                relation_kind=relation_kind,
                usage_role=usage_role,
                view=view,
                token=search or "",
                include_fields=include_fields,
                max_evidence_per_role=max_evidence_per_role,
                max_results=500,
                page_token=token,
            )
            page_items = list(page.get("items") or ())
            page_end = current_offset + len(page_items)
            if offset < page_end:
                start = max(0, offset - current_offset)
                selected.extend(page_items[start : start + (limit - len(selected))])
            next_token = page.get("next_token")
            if not next_token or not page_items:
                break
            token = str(next_token)
            current_offset = page_end
        return selected
