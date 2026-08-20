from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Protocol

from prepared_knowledge_runtime.observed_storage_usage_queries import (
    ObservedStorageUsageReadService as StorageUsageQueryAdapter,
    ObservedStorageUsageUnavailableError,
)

from .query_source import KnowledgeArtifactSource


class StorageUsageQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> StorageUsageQueryAdapter: ...


class CachedStorageUsageQueryFactory:
    """API-local cache for the KLC-owned observed-storage reader."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[int, int] | None, StorageUsageQueryAdapter]] = {}
        self._lock = RLock()

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> StorageUsageQueryAdapter:
        path = system.database_path.resolve()
        signature = self._signature(path)
        if signature is None:
            raise ObservedStorageUsageUnavailableError(
                f"observed-storage artifact is unavailable for system {system.system_id}: {path}"
            )
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            adapter = StorageUsageQueryAdapter(path)
            self._cache[key] = (signature, adapter)
            return adapter
