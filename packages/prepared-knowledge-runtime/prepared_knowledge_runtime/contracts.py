from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

from .errors import KnowledgeLayerContractError

SCHEMA_VERSION = "knowledge_layer/v1"
ARTIFACT_ID = "knowledge_layer"
SUPPORTED_MODES = ("data-model", "sql", "observed-storage-usage", "model-storage-semantics", "system-description", "reference-data", "system-interactions", "repository-value-flow", "persistence-lineage", "repository-inventory")
ScopeType = Literal["repository", "workspace"]
BuildStatus = Literal["pending", "complete", "failed"]
ValidationStatus = Literal["pending", "complete", "failed"]


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise KnowledgeLayerContractError(f"{field_name} must not be empty")
    return normalized


def _unique_texts(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(_required_text(value, field_name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise KnowledgeLayerContractError(f"{field_name} must contain unique values")
    return normalized


def derive_scope_type(repository_count: int) -> ScopeType:
    if repository_count < 1:
        raise KnowledgeLayerContractError("repository_count must be at least 1")
    return "repository" if repository_count == 1 else "workspace"


@dataclass(frozen=True, slots=True)
class KnowledgeLayerManifest:
    scope_id: str
    repository_ids: tuple[str, ...]
    modes: tuple[str, ...]
    producer_version: str
    build_id: str
    build_status: BuildStatus
    producer: str = "knowledge-layer-core"
    database_path: str = "knowledge-layer.duckdb"
    manifest_path: str = "knowledge-layer-manifest.json"
    deterministic: bool = True
    llm_generated: bool = False
    counts: Mapping[str, int] = field(default_factory=dict)
    materialized_marts: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    artifacts: Mapping[str, str] = field(default_factory=dict)
    source_evidence: tuple[Mapping[str, Any], ...] = ()
    validation_status: ValidationStatus = "pending"
    validation: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_id", _required_text(self.scope_id, "scope_id"))
        object.__setattr__(self, "repository_ids", _unique_texts(self.repository_ids, "repository_ids"))
        object.__setattr__(self, "modes", _unique_texts(self.modes, "modes"))
        object.__setattr__(self, "producer", _required_text(self.producer, "producer"))
        object.__setattr__(self, "producer_version", _required_text(self.producer_version, "producer_version"))
        object.__setattr__(self, "capabilities", _unique_texts(self.capabilities, "capabilities"))
        object.__setattr__(self, "artifacts", {"database": self.database_path, "manifest": self.manifest_path, **dict(self.artifacts)})
        object.__setattr__(self, "build_id", _required_text(self.build_id, "build_id"))
        if not self.repository_ids:
            raise KnowledgeLayerContractError("repository_ids must contain at least one repository")
        unsupported = sorted(set(self.modes) - set(SUPPORTED_MODES))
        if unsupported:
            raise KnowledgeLayerContractError(f"unsupported modes: {unsupported}; supported={list(SUPPORTED_MODES)}")
        if self.build_status not in {"pending", "complete", "failed"}:
            raise KnowledgeLayerContractError(f"unsupported build_status: {self.build_status!r}")
        if self.validation_status not in {"pending", "complete", "failed"}:
            raise KnowledgeLayerContractError(f"unsupported validation_status: {self.validation_status!r}")
        if self.build_status == "complete" and self.validation_status != "complete":
            raise KnowledgeLayerContractError("complete build requires complete validation")

    @property
    def repository_count(self) -> int:
        return len(self.repository_ids)

    @property
    def scope_type(self) -> ScopeType:
        return derive_scope_type(self.repository_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": ARTIFACT_ID,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "deterministic": self.deterministic,
            "llm_generated": self.llm_generated,
            "scope_id": self.scope_id,
            "scope_type": self.scope_type,
            "repository_count": self.repository_count,
            "repository_ids": list(self.repository_ids),
            "modes": list(self.modes),
            "build_id": self.build_id,
            "build_status": self.build_status,
            "database_path": self.database_path,
            "manifest_path": self.manifest_path,
            "counts": dict(self.counts),
            "materialized_marts": list(self.materialized_marts),
            "capabilities": list(self.capabilities),
            "artifacts": {"database": self.database_path, "manifest": self.manifest_path, **dict(self.artifacts)},
            "source_evidence": [dict(item) for item in self.source_evidence],
            "validation": {"status": self.validation_status, **dict(self.validation)},
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeLayerManifest":
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise KnowledgeLayerContractError(f"unsupported schema_version: {payload.get('schema_version')!r}")
        if payload.get("artifact_id") != ARTIFACT_ID:
            raise KnowledgeLayerContractError(f"unsupported artifact_id: {payload.get('artifact_id')!r}")
        validation = payload.get("validation") or {}
        manifest = cls(
            scope_id=str(payload.get("scope_id") or ""),
            repository_ids=tuple(str(item) for item in (payload.get("repository_ids") or [])),
            modes=tuple(str(item) for item in (payload.get("modes") or [])),
            producer=str(payload.get("producer") or "knowledge-layer-core"),
            producer_version=str(payload.get("producer_version") or ""),
            build_id=str(payload.get("build_id") or ""),
            build_status=str(payload.get("build_status") or "pending"),  # type: ignore[arg-type]
            database_path=str(payload.get("database_path") or "knowledge-layer.duckdb"),
            manifest_path=str(payload.get("manifest_path") or "knowledge-layer-manifest.json"),
            deterministic=bool(payload.get("deterministic", True)),
            llm_generated=bool(payload.get("llm_generated", False)),
            counts=dict(payload.get("counts") or {}),
            materialized_marts=tuple(str(item) for item in (payload.get("materialized_marts") or [])),
            capabilities=tuple(str(item) for item in (payload.get("capabilities") or [])),
            artifacts={str(key): str(value) for key, value in dict(payload.get("artifacts") or {}).items()},
            source_evidence=tuple(dict(item) for item in (payload.get("source_evidence") or [])),
            validation_status=str(validation.get("status") or "pending"),  # type: ignore[arg-type]
            validation={key: value for key, value in validation.items() if key != "status"},
            metadata=dict(payload.get("metadata") or {}),
        )
        declared_count = payload.get("repository_count")
        if declared_count is not None and int(declared_count) != manifest.repository_count:
            raise KnowledgeLayerContractError("repository_count does not match repository_ids")
        declared_scope = payload.get("scope_type")
        if declared_scope is not None and declared_scope != manifest.scope_type:
            raise KnowledgeLayerContractError("scope_type does not match repository_count")
        return manifest
