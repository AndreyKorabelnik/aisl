from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from prepared_knowledge_runtime import ForeignDataPersistenceQueryService

from .query_source import KnowledgeArtifactSource


class ForeignDataPersistenceKnowledgeUnavailableError(RuntimeError):
    pass


class ForeignDataPersistenceQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> "ForeignDataPersistenceQueryAdapter": ...


class CachedForeignDataPersistenceQueryFactory:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[tuple[int, int] | None, tuple[int, int] | None], ForeignDataPersistenceQueryAdapter]] = {}
        self._lock = RLock()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> "ForeignDataPersistenceQueryAdapter":
        path = system.database_path.resolve()
        database_signature = self._signature(path)
        manifest = system.manifest_path.resolve() if system.manifest_path is not None else None
        manifest_signature = self._signature(manifest) if manifest is not None else None
        signature = (database_signature, manifest_signature)
        if database_signature is None:
            raise ForeignDataPersistenceKnowledgeUnavailableError(
                f"typed knowledge artifact is unavailable for system {system.system_id}: {path}"
            )
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            try:
                adapter = ForeignDataPersistenceQueryAdapter(path, manifest=manifest)
            except Exception as exc:  # pragma: no cover - normalized by service tests
                raise ForeignDataPersistenceKnowledgeUnavailableError(str(exc)) from exc
            self._cache[key] = (signature, adapter)
            return adapter


class ForeignDataPersistenceQueryAdapter:
    """Thin adapter over KLC ForeignDataPersistenceQueryService.

    All path construction, technical-origin interpretation, exact-field mechanical
    bridging, evidence normalization and unresolved-gap semantics stay KLC-owned.
    The API validates only the small public dispatch/filter contract.
    """

    SUPPORTED_QUERY_KINDS = (
        "list_paths",
        "get_path",
        "list_mechanical_cases",
        "get_landscape",
    )

    _FILTERS: dict[str, frozenset[str]] = {
        "list_paths": frozenset({"direction", "token"}),
        "get_path": frozenset({"path_id"}),
        "list_mechanical_cases": frozenset({"token"}),
        "get_landscape": frozenset({"token"}),
    }

    def __init__(self, artifact: str | Path, *, manifest: str | Path | None = None) -> None:
        self.service = ForeignDataPersistenceQueryService(artifact, manifest=manifest)

    def call(
        self,
        query_kind: str,
        *,
        filters: Mapping[str, Any] | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        normalized = str(query_kind or "").strip()
        if normalized not in self._FILTERS:
            raise ValueError(f"unsupported foreign-data-persistence query kind: {normalized}")
        if int(max_results) < 1:
            raise ValueError("max_results must be positive")
        values = {str(key): value for key, value in dict(filters or {}).items() if value is not None}
        unknown = sorted(set(values) - set(self._FILTERS[normalized]))
        if unknown:
            raise ValueError(
                f"unsupported filters for {normalized}: {', '.join(unknown)}"
            )

        if normalized == "list_paths":
            direction = str(values.get("direction") or "").strip() or None
            if direction not in {None, "source-to-storage", "storage-to-access"}:
                raise ValueError("direction must be source-to-storage or storage-to-access")
            result = self.service.list_paths(
                direction=direction,
                token=str(values.get("token") or ""),
                max_results=max_results,
            )
        elif normalized == "get_path":
            path_id = str(values.get("path_id") or "").strip()
            if not path_id:
                raise ValueError("path_id is required for get_path")
            result = self.service.get_path(path_id)
        elif normalized == "list_mechanical_cases":
            result = self.service.list_mechanical_cases(
                token=str(values.get("token") or ""),
                max_results=max_results,
            )
        else:
            result = self.service.get_landscape(
                token=str(values.get("token") or ""),
                max_results=max_results,
            )
        return result.to_dict()
