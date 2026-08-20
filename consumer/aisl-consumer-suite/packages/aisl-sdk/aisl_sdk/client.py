from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Sequence
from urllib.parse import quote

import httpx

from .errors import AislApiError, AislContractError, AislTransportError
from .models import KnowledgeProduct, Page, RevisionSummary, SystemSummary
from .integration import ConsumerIntegration

_JSON_OBJECT = dict[str, Any]


def _required_text(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _path_segment(value: str, name: str) -> str:
    return quote(_required_text(value, name), safe="")


@dataclass(frozen=True, slots=True)
class PinnedRevision:
    """Immutable client-side handle pinned to one exact AISL revision."""

    client: "AislClient"
    summary: RevisionSummary

    @property
    def system_id(self) -> str:
        return self.summary.system_id

    @property
    def revision_id(self) -> str:
        return self.summary.revision_id

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self.summary.capabilities

    @property
    def products(self) -> tuple[KnowledgeProduct, ...]:
        return self.summary.products

    def refresh_metadata(self) -> "PinnedRevision":
        """Re-read this exact revision id; never follows active/latest."""
        return self.client.revision(self.system_id, self.revision_id)

    def list_products(
        self,
        *,
        model_kind: str | None = None,
        capability: str | None = None,
        page_size: int = 100,
        max_results: int = 10_000,
    ) -> list[KnowledgeProduct]:
        path = f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}/knowledge-artifacts"
        params: dict[str, Any] = {"revision_id": self.revision_id}
        if model_kind is not None:
            params["model_kind"] = model_kind
        if capability is not None:
            params["capability"] = capability
        items = self.client.collect_pages(
            path,
            params=params,
            page_size=page_size,
            max_results=max_results,
        )
        return [KnowledgeProduct.from_payload(item) for item in items]

    def get_product(self, artifact_id: str) -> KnowledgeProduct:
        path = (
            f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}"
            f"/knowledge-artifacts/{_path_segment(artifact_id, 'artifact_id')}"
        )
        payload = self.client.get_json(path, params={"revision_id": self.revision_id})
        artifact = payload.get("artifact")
        if not isinstance(artifact, Mapping):
            raise AislContractError(f"Knowledge API response has no artifact object for GET {path}")
        return KnowledgeProduct.from_payload(artifact)

    def get_capabilities(self) -> tuple[str, ...]:
        path = f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}/capabilities"
        payload = self.client.get_json(path, params={"revision_id": self.revision_id})
        values = payload.get("capabilities") or ()
        if not isinstance(values, list):
            raise AislContractError(f"Knowledge API capabilities must be an array for GET {path}")
        return tuple(str(value) for value in values if str(value))

    def declared_data_model_summary(
        self,
        *,
        repo_id: str | None = None,
        type_annotations: str | None = None,
        exclude_field_annotations: str | None = None,
    ) -> _JSON_OBJECT:
        path = f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}/data-model/declared-summary"
        params: dict[str, Any] = {"revision_id": self.revision_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        if type_annotations is not None:
            params["type_annotations"] = type_annotations
        if exclude_field_annotations is not None:
            params["exclude_field_annotations"] = exclude_field_annotations
        return self.client.get_json(path, params=params)

    def search_declared_data_objects(
        self,
        *,
        search: str | None = None,
        repo_id: str | None = None,
        type_annotations: str | None = None,
        include_fields: bool = False,
        page_size: int = 100,
        max_results: int = 1_000,
    ) -> list[_JSON_OBJECT]:
        path = f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}/data-model/declared-objects"
        params: dict[str, Any] = {
            "revision_id": self.revision_id,
            "include_fields": include_fields,
        }
        if search is not None:
            params["search"] = search
        if repo_id is not None:
            params["repo_id"] = repo_id
        if type_annotations is not None:
            params["type_annotations"] = type_annotations
        return self.client.collect_pages(path, params=params, page_size=page_size, max_results=max_results)

    def get_declared_data_object(self, object_id: str) -> _JSON_OBJECT:
        path = (
            f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}"
            f"/data-model/declared-objects/{_path_segment(object_id, 'object_id')}"
        )
        return self.client.get_json(path, params={"revision_id": self.revision_id})

    def integration(self, profile_id: str) -> ConsumerIntegration:
        """Load the canonical Integration Profile for this exact immutable revision."""
        return ConsumerIntegration.load(self.client, system_id=self.system_id, revision_id=self.revision_id, profile_id=profile_id)

    def get_data_model_object_context(self, object_id: str) -> _JSON_OBJECT:
        path = (
            f"/api/knowledge/v1/systems/{_path_segment(self.system_id, 'system_id')}"
            f"/data-model/object-context/{_path_segment(object_id, 'object_id')}"
        )
        return self.client.get_json(path, params={"revision_id": self.revision_id})


class AislClient:
    """Thin public HTTP client over the canonical Knowledge API v1 contract.

    This client owns transport convenience only. It does not read AISL storage,
    materialize knowledge, interpret ambiguity, or duplicate Knowledge Integration
    policy/tool-selection semantics.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: float = 30.0,
        headers: Mapping[str, str] | None = None,
        verify: bool | str | ssl.SSLContext = True,
        cert: str | tuple[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = _required_text(base_url, "base_url").rstrip("/")
        self.base_url = normalized
        self._client = httpx.Client(
            base_url=normalized,
            timeout=float(timeout_sec),
            headers=dict(headers or {}),
            verify=verify,
            cert=cert,
            transport=transport,
        )

    def __enter__(self) -> "AislClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request_object(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> _JSON_OBJECT:
        try:
            response = self._client.request(method, path, params=params, json=(dict(payload) if payload is not None else None))
        except httpx.HTTPError as exc:
            raise AislTransportError(f"Knowledge API request failed: {type(exc).__name__}: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail: Any = response.json()
            except ValueError:
                detail = response.text
            raise AislApiError(status_code=response.status_code, method=method, path=path, detail=detail)
        try:
            result = response.json()
        except ValueError as exc:
            raise AislContractError(f"Knowledge API returned non-JSON response for {method.upper()} {path}") from exc
        if not isinstance(result, dict):
            raise AislContractError(f"Knowledge API response root must be an object for {method.upper()} {path}")
        return result

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> _JSON_OBJECT:
        return self._request_object("GET", path, params=params)

    def post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        params: Mapping[str, Any] | None = None,
    ) -> _JSON_OBJECT:
        return self._request_object("POST", path, params=params, payload=payload)

    def service_capabilities(self) -> _JSON_OBJECT:
        return self.get_json("/api/knowledge/v1/capabilities")

    def list_systems(
        self,
        *,
        search: str | None = None,
        page_size: int = 100,
        max_results: int = 10_000,
    ) -> list[SystemSummary]:
        params: dict[str, Any] = {}
        if search is not None:
            params["search"] = search
        items = self.collect_pages(
            "/api/knowledge/v1/systems",
            params=params,
            page_size=page_size,
            max_results=max_results,
        )
        return [SystemSummary.from_payload(item) for item in items]

    def get_system(self, system_id: str) -> SystemSummary:
        path = f"/api/knowledge/v1/systems/{_path_segment(system_id, 'system_id')}"
        return SystemSummary.from_payload(self.get_json(path))

    def list_revisions(
        self,
        system_id: str,
        *,
        page_size: int = 100,
        max_results: int = 10_000,
    ) -> list[RevisionSummary]:
        path = f"/api/knowledge/v1/systems/{_path_segment(system_id, 'system_id')}/revisions"
        items = self.collect_pages(path, page_size=page_size, max_results=max_results)
        return [RevisionSummary.from_payload(item) for item in items]

    def revision(self, system_id: str, revision_id: str) -> PinnedRevision:
        sid = _required_text(system_id, "system_id")
        rid = _required_text(revision_id, "revision_id")
        path = f"/api/knowledge/v1/systems/{_path_segment(sid, 'system_id')}/revisions/{_path_segment(rid, 'revision_id')}"
        summary = RevisionSummary.from_payload(self.get_json(path))
        if summary.system_id != sid or summary.revision_id != rid:
            raise AislContractError(
                f"Knowledge API revision identity mismatch: requested {sid}/{rid}, "
                f"received {summary.system_id}/{summary.revision_id}"
            )
        return PinnedRevision(client=self, summary=summary)

    def active_revision(self, system_id: str) -> PinnedRevision:
        """Explicitly resolve active_revision_id once, then pin the concrete id."""
        system = self.get_system(system_id)
        if not system.active_revision_id:
            raise AislContractError(f"system {system.system_id!r} has no active Knowledge API revision")
        return self.revision(system.system_id, system.active_revision_id)

    def iter_pages(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        page_size: int = 100,
        max_results: int = 10_000,
        item_decoder: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> Iterator[Any]:
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
        if max_results < 0:
            raise ValueError("max_results must be >= 0")
        if max_results == 0:
            return
        offset = 0
        emitted = 0
        while emitted < max_results:
            limit = min(page_size, max_results - emitted)
            query = dict(params or {})
            query["offset"] = offset
            query["limit"] = limit
            payload = self.get_json(path, params=query)
            raw_items = payload.get("items")
            if not isinstance(raw_items, list):
                raise AislContractError(f"Knowledge API paged response must contain items array for GET {path}")
            page = Page.from_payload(payload.get("page") if isinstance(payload.get("page"), Mapping) else None)
            decoded: Sequence[Any] = [
                item_decoder(item) if item_decoder is not None else dict(item)
                for item in raw_items
                if isinstance(item, Mapping)
            ]
            if len(decoded) != len(raw_items):
                raise AislContractError(f"Knowledge API paged response items must be objects for GET {path}")
            for item in decoded:
                if emitted >= max_results:
                    return
                yield item
                emitted += 1
            consumed = len(raw_items)
            if consumed == 0:
                return
            offset += consumed
            if page.total and offset >= page.total:
                return
            if consumed < limit and not page.total:
                return

    def collect_pages(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        page_size: int = 100,
        max_results: int = 10_000,
    ) -> list[_JSON_OBJECT]:
        return list(self.iter_pages(path, params=params, page_size=page_size, max_results=max_results))
