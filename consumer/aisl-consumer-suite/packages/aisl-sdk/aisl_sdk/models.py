from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _tuple_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _tuple_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(str(item) for item in value if str(item))


@dataclass(frozen=True, slots=True)
class SystemSummary:
    system_id: str
    display_name: str
    active_revision_id: str | None
    revision_count: int
    raw: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SystemSummary":
        return cls(
            system_id=str(payload.get("system_id") or ""),
            display_name=str(payload.get("display_name") or ""),
            active_revision_id=(str(payload.get("active_revision_id")) if payload.get("active_revision_id") else None),
            revision_count=int(payload.get("revision_count") or 0),
            raw=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeProduct:
    artifact_id: str
    model_kind: str
    schema_version: str
    product_slot_id: str
    origin_kind: str
    capabilities: tuple[str, ...]
    exact_dependency_product_ids: tuple[str, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "KnowledgeProduct":
        return cls(
            artifact_id=str(payload.get("artifact_id") or ""),
            model_kind=str(payload.get("model_kind") or ""),
            schema_version=str(payload.get("schema_version") or ""),
            product_slot_id=str(payload.get("product_slot_id") or ""),
            origin_kind=str(payload.get("origin_kind") or ""),
            capabilities=_tuple_strings(payload.get("capabilities")),
            exact_dependency_product_ids=_tuple_strings(payload.get("exact_dependency_product_ids")),
            raw=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class RevisionSummary:
    system_id: str
    revision_id: str
    base_revision_id: str | None
    ordinal: int
    state: str
    capabilities: tuple[str, ...]
    products: tuple[KnowledgeProduct, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RevisionSummary":
        return cls(
            system_id=str(payload.get("system_id") or ""),
            revision_id=str(payload.get("revision_id") or ""),
            base_revision_id=(str(payload.get("base_revision_id")) if payload.get("base_revision_id") else None),
            ordinal=int(payload.get("ordinal") or 0),
            state=str(payload.get("state") or ""),
            capabilities=_tuple_strings(payload.get("capabilities")),
            products=tuple(KnowledgeProduct.from_payload(item) for item in _tuple_dicts(payload.get("knowledge_artifacts"))),
            raw=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class Page:
    offset: int
    limit: int
    total: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "Page":
        data = _dict(payload)
        return cls(
            offset=int(data.get("offset") or 0),
            limit=int(data.get("limit") or 0),
            total=int(data.get("total") or 0),
        )
