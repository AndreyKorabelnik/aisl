from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Protocol

from prepared_knowledge_runtime.effective_data_model_queries import (
    DataObjectNotFoundError,
    EffectiveDataModelReadService,
    EffectiveDataModelUnavailableError,
    RelationshipNotFoundError,
)

from .data_model_models import FieldCatalogResponse, TableDetailResponse, TableRelationship
from .query_source import KnowledgeArtifactSource
from .version import API_SCHEMA_VERSION


class EffectiveDataModelQueryService:
    """HTTP-model projection over the KLC-owned effective-model read contract."""

    def __init__(self, path: str | Path) -> None:
        self._reader = EffectiveDataModelReadService(path)

    def field_catalog(self, system_id: str) -> FieldCatalogResponse:
        return FieldCatalogResponse.model_validate(self._reader.field_catalog(system_id))

    def relationship_counts(self) -> dict[str, int]:
        return self._reader.relationship_counts()

    def table_detail(self, system_id: str, table_id: str) -> TableDetailResponse:
        payload = dict(self._reader.table_detail(system_id, table_id))
        payload["schema_version"] = API_SCHEMA_VERSION
        return TableDetailResponse.model_validate(payload)

    def relationship_detail(self, table_id: str, relationship_id: str) -> TableRelationship:
        return TableRelationship.model_validate(self._reader.relationship_detail(table_id, relationship_id))

    def analysis_coverage(self, system_id: str) -> dict:
        return self._reader.analysis_coverage(system_id)


class EffectiveDataModelQueryFactory(Protocol):
    def get(self, system: KnowledgeArtifactSource) -> EffectiveDataModelQueryService: ...


class CachedEffectiveDataModelQueryFactory:
    """API-local cache for the KLC-owned effective-model reader."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: dict[str, tuple[tuple[int, int] | None, EffectiveDataModelQueryService]] = {}

    @staticmethod
    def _signature(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def get(self, system: KnowledgeArtifactSource) -> EffectiveDataModelQueryService:
        path = system.database_path.expanduser().resolve()
        signature = self._signature(path)
        key = str(path)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                return cached[1]
            service = EffectiveDataModelQueryService(path)
            self._cache[key] = (signature, service)
            return service
