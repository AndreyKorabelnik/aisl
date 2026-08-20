from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Protocol

from prepared_knowledge_runtime.cross_artifact_lineage_queries import (
    DataModelLineageReadService as DataModelLineageQueryService,
    DataModelLineageUnavailableError,
)

from .query_source import KnowledgeArtifactSource


class DataModelLineageQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> DataModelLineageQueryService: ...


class CachedDataModelLineageQueryFactory:
    """API-local cache for the KLC-owned lineage reader."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: dict[str, tuple[tuple[int, int] | None, DataModelLineageQueryService]] = {}

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> DataModelLineageQueryService:
        path = system.database_path.expanduser().resolve()
        signature = self._signature(path)
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            service = DataModelLineageQueryService(path)
            self._cache[key] = (signature, service)
            return service
