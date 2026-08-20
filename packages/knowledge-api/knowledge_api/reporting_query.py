from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from prepared_knowledge_runtime.reporting_queries import ReportingQueryService

from .query_source import KnowledgeArtifactSource


class ReportingKnowledgeUnavailableError(RuntimeError):
    pass


class ReportingKnowledgeQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> "ReportingKnowledgeQueryAdapter": ...


class CachedReportingKnowledgeQueryFactory:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[tuple[int, int] | None, tuple[int, int] | None], ReportingKnowledgeQueryAdapter]] = {}
        self._lock = RLock()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> "ReportingKnowledgeQueryAdapter":
        path = system.database_path.resolve()
        database_signature = self._signature(path)
        manifest = system.manifest_path.resolve() if system.manifest_path is not None else None
        manifest_signature = self._signature(manifest) if manifest is not None else None
        signature = (database_signature, manifest_signature)
        if database_signature is None:
            raise ReportingKnowledgeUnavailableError(
                f"typed knowledge artifact is unavailable for system {system.system_id}: {path}"
            )
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            try:
                adapter = ReportingKnowledgeQueryAdapter(path, manifest=manifest)
            except Exception as exc:  # pragma: no cover - normalized by service tests
                raise ReportingKnowledgeUnavailableError(str(exc)) from exc
            self._cache[key] = (signature, adapter)
            return adapter


class ReportingKnowledgeQueryAdapter:
    """Thin adapter over the canonical KLC ReportingQueryService.

    Query semantics, evidence normalization, gap construction and representative-journey
    selection remain KLC-owned. The API only validates the small public dispatch contract.
    """

    SUPPORTED_QUERY_KINDS = (
        "get_scope_overview",
        "get_repository_composition",
        "get_technologies",
        "list_interfaces",
        "list_integrations",
        "list_events",
        "list_data_objects",
        "list_relationships",
        "get_analysis_coverage",
        "get_gap_summary",
        "get_representative_journeys",
    )

    _FILTERS: dict[str, frozenset[str]] = {
        "get_scope_overview": frozenset(),
        "get_repository_composition": frozenset(),
        "get_technologies": frozenset(),
        "list_interfaces": frozenset({"direction", "boundary_kinds", "include_test"}),
        "list_integrations": frozenset(),
        "list_events": frozenset(),
        "list_data_objects": frozenset({"representative"}),
        "list_relationships": frozenset(),
        "get_analysis_coverage": frozenset(),
        "get_gap_summary": frozenset(),
        "get_representative_journeys": frozenset(),
    }

    def __init__(self, artifact: str | Path, *, manifest: str | Path | None = None) -> None:
        self.service = ReportingQueryService(artifact, manifest=manifest)

    def call(
        self,
        query_kind: str,
        *,
        filters: Mapping[str, Any] | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        normalized = str(query_kind or "").strip()
        if normalized not in self._FILTERS:
            raise ValueError(f"unsupported reporting query kind: {normalized}")
        if int(max_results) < 1:
            raise ValueError("max_results must be positive")
        values = {str(key): value for key, value in dict(filters or {}).items() if value is not None}
        unknown = sorted(set(values) - set(self._FILTERS[normalized]))
        if unknown:
            raise ValueError(
                f"unsupported filters for {normalized}: {', '.join(unknown)}"
            )

        if normalized == "get_scope_overview":
            result = self.service.get_scope_overview()
        elif normalized == "get_repository_composition":
            result = self.service.get_repository_composition(max_results=max_results)
        elif normalized == "get_technologies":
            result = self.service.get_technologies(max_results=max_results)
        elif normalized == "list_interfaces":
            raw_boundary_kinds = values.get("boundary_kinds")
            boundary_kinds = None
            if isinstance(raw_boundary_kinds, (list, tuple, set)):
                boundary_kinds = tuple(str(item) for item in raw_boundary_kinds if str(item).strip())
            result = self.service.list_interfaces(
                direction=str(values["direction"]) if values.get("direction") is not None else None,
                boundary_kinds=boundary_kinds,
                include_test=bool(values.get("include_test", False)),
                max_results=max_results,
            )
        elif normalized == "list_integrations":
            result = self.service.list_integrations(max_results=max_results)
        elif normalized == "list_events":
            result = self.service.list_events(max_results=max_results)
        elif normalized == "list_data_objects":
            result = self.service.list_data_objects(
                max_results=max_results,
                representative=bool(values.get("representative", True)),
            )
        elif normalized == "list_relationships":
            result = self.service.list_relationships(max_results=max_results)
        elif normalized == "get_analysis_coverage":
            result = self.service.get_analysis_coverage(max_results=max_results)
        elif normalized == "get_gap_summary":
            result = self.service.get_gap_summary(max_results=max_results)
        elif normalized == "get_representative_journeys":
            result = self.service.get_representative_journeys(max_results=max_results)
        else:  # pragma: no cover - exhaustive dispatch guard
            raise AssertionError(normalized)
        return result.to_dict()
