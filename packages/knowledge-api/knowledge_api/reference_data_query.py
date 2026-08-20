from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from prepared_knowledge_runtime import ReferenceDataQueryService

from .query_source import KnowledgeArtifactSource


class ReferenceDataKnowledgeUnavailableError(RuntimeError):
    pass


class ReferenceDataQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> "ReferenceDataQueryAdapter": ...


class CachedReferenceDataQueryFactory:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[tuple[int, int] | None, tuple[int, int] | None], ReferenceDataQueryAdapter]] = {}
        self._lock = RLock()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> "ReferenceDataQueryAdapter":
        path = system.database_path.resolve()
        database_signature = self._signature(path)
        manifest = system.manifest_path.resolve() if system.manifest_path is not None else None
        manifest_signature = self._signature(manifest) if manifest is not None else None
        signature = (database_signature, manifest_signature)
        if database_signature is None:
            raise ReferenceDataKnowledgeUnavailableError(
                f"typed knowledge artifact is unavailable for system {system.system_id}: {path}"
            )
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            try:
                adapter = ReferenceDataQueryAdapter(path, manifest=manifest)
            except Exception as exc:  # pragma: no cover
                raise ReferenceDataKnowledgeUnavailableError(str(exc)) from exc
            self._cache[key] = (signature, adapter)
            return adapter


class ReferenceDataQueryAdapter:
    """Thin dispatch over KLC ReferenceDataQueryService.

    Reference-data candidate formation, provenance, source-set handling and
    uncertainty semantics stay KLC-owned. The API does not decide official NSI
    status, ownership or authoritative source of truth.
    """

    _FILTERS: dict[str, frozenset[str]] = {
        "search_reference_data": frozenset({"token", "include_non_production"}),
        "get_reference_data_object": frozenset({"object_id"}),
        "get_candidate_context": frozenset({"token", "include_non_production"}),
        "list_declared_value_sets": frozenset({"token", "source_sets", "include_values"}),
        "list_literal_writes": frozenset({"token"}),
        "get_usage_observations": frozenset({"token"}),
        "get_gap_summary": frozenset({"token"}),
        "get_landscape": frozenset({"token"}),
    }

    def __init__(self, artifact: str | Path, *, manifest: str | Path | None = None) -> None:
        self.service = ReferenceDataQueryService(artifact, manifest=manifest)

    def call(self, query_kind: str, *, filters: Mapping[str, Any] | None = None, max_results: int = 100) -> dict[str, Any]:
        normalized = str(query_kind or "").strip()
        if normalized not in self._FILTERS:
            raise ValueError(f"unsupported reference-data query kind: {normalized}")
        if int(max_results) < 1:
            raise ValueError("max_results must be positive")
        values = {str(key): value for key, value in dict(filters or {}).items() if value is not None}
        unknown = sorted(set(values) - set(self._FILTERS[normalized]))
        if unknown:
            raise ValueError(f"unsupported filters for {normalized}: {', '.join(unknown)}")

        token = str(values.get("token") or "")
        if normalized == "search_reference_data":
            result = self.service.search_reference_data(
                token=token,
                include_non_production=bool(values.get("include_non_production", True)),
                max_results=max_results,
            )
        elif normalized == "get_candidate_context":
            if not token:
                raise ValueError("token is required for get_candidate_context")
            result = self.service.get_candidate_context(
                token=token,
                include_non_production=bool(values.get("include_non_production", True)),
                max_results=max_results,
            )
        elif normalized == "get_reference_data_object":
            object_id = str(values.get("object_id") or "").strip()
            if not object_id:
                raise ValueError("object_id is required for get_reference_data_object")
            result = self.service.get_reference_data_object(object_id)
        elif normalized == "list_declared_value_sets":
            source_sets_raw = values.get("source_sets") or []
            if isinstance(source_sets_raw, str):
                source_sets = (source_sets_raw,)
            elif isinstance(source_sets_raw, (list, tuple, set)):
                source_sets = tuple(str(value) for value in source_sets_raw if str(value))
            else:
                raise ValueError("source_sets must be a string or array of strings")
            result = self.service.list_declared_value_sets(
                token=token,
                source_sets=source_sets,
                include_values=bool(values.get("include_values", True)),
                max_results=max_results,
            )
        elif normalized == "list_literal_writes":
            result = self.service.list_literal_writes(token=token, max_results=max_results)
        elif normalized == "get_usage_observations":
            result = self.service.get_usage_observations(token=token, max_results_per_section=max_results)
        elif normalized == "get_gap_summary":
            result = self.service.get_gap_summary(token=token, max_results=max_results)
        else:
            result = self.service.get_landscape(token=token, max_results=max_results)
        return result.to_dict()
