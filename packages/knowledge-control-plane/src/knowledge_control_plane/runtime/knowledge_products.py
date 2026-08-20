from __future__ import annotations

import json

from knowledge_control_plane.api.generic_v1.models import (
    KnowledgeProductInfo,
    KnowledgeProductListResponse,
    PageMeta,
)

from .errors import ResourceNotFound
from .knowledge_contracts import discover_knowledge_contract_paths


class KnowledgeProductCatalogService:
    """Read-only projection of the Runner-owned Knowledge Product Catalog."""

    def __init__(self) -> None:
        path = discover_knowledge_contract_paths().knowledge_catalog
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._fingerprint = str(payload.get("catalog_fingerprint") or "")
        if not self._fingerprint:
            raise ValueError("knowledge catalog does not expose catalog_fingerprint")
        items: list[KnowledgeProductInfo] = []
        for item in payload.get("knowledge_types") or []:
            if not isinstance(item, dict) or not item.get("knowledge_id") or not item.get("title"):
                continue
            availability = item.get("availability") if isinstance(item.get("availability"), dict) else {}
            materialization = item.get("materialization") if isinstance(item.get("materialization"), dict) else {}
            sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
            items.append(
                KnowledgeProductInfo(
                    knowledge_id=str(item["knowledge_id"]),
                    title=str(item["title"]),
                    summary=str(item.get("summary") or "") or None,
                    category=str(item.get("category") or "") or None,
                    supported_scopes=list(item.get("supported_scopes") or []),
                    profile_v2_selectable=bool(item.get("profile_v2_selectable")),
                    runtime_status=str(availability.get("status") or "") or None,
                    runtime_executable=bool(availability.get("can_execute_through_target_contracts")),
                    required_knowledge_dependencies=[str(value) for value in item.get("required_knowledge_dependencies") or []],
                    recommended_knowledge_dependencies=[str(value) for value in item.get("recommended_knowledge_dependencies") or []],
                    materialization_id=str(materialization.get("materialization_id") or "") or None,
                    produced_capabilities=[str(value) for value in materialization.get("capabilities") or []],
                    required_sources=[value for value in sources.get("required") or [] if isinstance(value, dict)],
                    optional_sources=[value for value in sources.get("optional") or [] if isinstance(value, dict)],
                )
            )
        self._items = items
        self._by_id = {item.knowledge_id: item for item in items}

    @property
    def catalog_fingerprint(self) -> str:
        return self._fingerprint

    def all(self) -> list[KnowledgeProductInfo]:
        return list(self._items)

    def get(self, knowledge_id: str) -> KnowledgeProductInfo:
        item = self._by_id.get(knowledge_id)
        if item is None:
            raise ResourceNotFound("knowledge product", knowledge_id)
        return item

    def list(self, *, offset: int, limit: int, search: str | None = None) -> KnowledgeProductListResponse:
        items = self._items
        if search:
            needle = search.casefold()
            items = [
                item
                for item in items
                if needle in item.knowledge_id.casefold()
                or needle in item.title.casefold()
                or needle in (item.summary or "").casefold()
            ]
        return KnowledgeProductListResponse(
            catalog_fingerprint=self._fingerprint,
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )
