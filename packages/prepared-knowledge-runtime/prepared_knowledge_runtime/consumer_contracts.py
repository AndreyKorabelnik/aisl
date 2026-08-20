from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping

from .errors import KnowledgeLayerContractError

CONSUMER_SCHEMA_VERSION = "knowledge_query/v1"
ScopeKind = Literal["repository", "workspace"]
FactStatus = Literal["confirmed", "observed", "candidate", "unresolved"]


def _text(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise KnowledgeLayerContractError(f"{name} must not be empty")
    return result


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(frozen=True, slots=True)
class ScopeRef:
    kind: ScopeKind
    scope_id: str
    repository_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_id", _text(self.scope_id, "scope_id"))
        object.__setattr__(self, "repository_ids", tuple(str(v).strip() for v in self.repository_ids if str(v).strip()))
        if self.kind not in {"repository", "workspace"}:
            raise KnowledgeLayerContractError(f"unsupported scope kind: {self.kind!r}")
        if self.kind == "repository" and len(self.repository_ids) > 1:
            raise KnowledgeLayerContractError("repository scope cannot contain multiple repository_ids")

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.scope_id, "repository_ids": list(self.repository_ids)}


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    repo_id: str
    path: str
    line_start: int | None = None
    line_end: int | None = None
    extractor: str | None = None
    snippet: str | None = None
    maturity: str = "observed"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "repo_id", _text(self.repo_id, "repo_id"))
        object.__setattr__(self, "path", _text(self.path, "path"))
        if self.line_start is not None and int(self.line_start) < 1:
            raise KnowledgeLayerContractError("line_start must be positive")
        if self.line_end is not None and self.line_start is not None and int(self.line_end) < int(self.line_start):
            raise KnowledgeLayerContractError("line_end must be >= line_start")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "repo_id": self.repo_id,
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "extractor": self.extractor,
            "snippet": self.snippet,
            "maturity": self.maturity,
        }


@dataclass(frozen=True, slots=True)
class Gap:
    gap_id: str
    repo_id: str
    category: str
    missing_fact_kind: str
    required_for_operation: str | None = None
    description: str | None = None
    affected_object_ids: tuple[str, ...] = ()
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "repo_id": self.repo_id,
            "category": self.category,
            "missing_fact_kind": self.missing_fact_kind,
            "required_for_operation": self.required_for_operation,
            "description": self.description,
            "affected_object_ids": list(self.affected_object_ids),
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class Page:
    total_count: int
    returned_count: int
    truncated: bool = False
    next_token: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_count": int(self.total_count),
            "returned_count": int(self.returned_count),
            "truncated": bool(self.truncated),
            "next_token": self.next_token,
        }


@dataclass(frozen=True, slots=True)
class QueryRequest:
    query_kind: str
    scope: ScopeRef
    filters: Mapping[str, Any] = field(default_factory=dict)
    max_results: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_kind", _text(self.query_kind, "query_kind"))
        object.__setattr__(self, "filters", _mapping(self.filters))
        if int(self.max_results) < 1:
            raise KnowledgeLayerContractError("max_results must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.query_kind,
            "scope": self.scope.to_dict(),
            "filters": dict(self.filters),
            "max_results": int(self.max_results),
        }


@dataclass(frozen=True, slots=True)
class QueryResult:
    request: QueryRequest
    items: tuple[Mapping[str, Any], ...] = ()
    summary: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[EvidenceRef, ...] = ()
    gaps: tuple[Gap, ...] = ()
    page: Page | None = None
    schema_version: str = CONSUMER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query": self.request.to_dict(),
            "items": [dict(item) for item in self.items],
            "summary": dict(self.summary),
            "evidence": [item.to_dict() for item in self.evidence],
            "gaps": [item.to_dict() for item in self.gaps],
            "pagination": self.page.to_dict() if self.page else None,
        }


def evidence_index(refs: Iterable[EvidenceRef]) -> dict[str, dict[str, Any]]:
    return {ref.evidence_id: ref.to_dict() for ref in sorted(refs, key=lambda item: item.evidence_id)}
