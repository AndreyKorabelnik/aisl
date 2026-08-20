from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from aisl_sdk import AislClient
from aisl_sdk.errors import AislClientError


class KnowledgeApiSourceError(RuntimeError):
    """Raised when a report cannot be grounded in a published Knowledge API revision."""


@dataclass(frozen=True, slots=True)
class KnowledgeRequirement:
    model_kind: str | None = None
    required_capabilities: tuple[str, ...] = ()
    optional_model_kinds: tuple[str, ...] = ()
    optional_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeApiRevision:
    api_url: str
    system_id: str
    revision_id: str
    revision: Mapping[str, Any]
    artifacts: tuple[Mapping[str, Any], ...]
    capabilities: tuple[str, ...]
    client: AislClient
    selected_artifact: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        selected = self.selected_artifact or {}
        return {
            "source_kind": "knowledge_api_revision",
            "api_url": self.api_url,
            "system_id": self.system_id,
            "revision_id": self.revision_id,
            "execution": dict(self.revision.get("execution") or {}),
            "capabilities": list(self.capabilities),
            "artifact_count": len(self.artifacts),
            "selected_artifact": {
                key: selected.get(key)
                for key in (
                    "artifact_id", "model_kind", "schema_version", "source_materialization_id",
                    "content_fingerprint", "capabilities", "coverage", "diagnostics",
                )
                if selected.get(key) is not None
            } or None,
        }

    def with_selected(self, artifact: Mapping[str, Any] | None) -> "KnowledgeApiRevision":
        return KnowledgeApiRevision(
            api_url=self.api_url,
            system_id=self.system_id,
            revision_id=self.revision_id,
            revision=self.revision,
            artifacts=self.artifacts,
            capabilities=self.capabilities,
            client=self.client,
            selected_artifact=artifact,
        )

    def query_system_description(self, query_kind: str, *, filters: Mapping[str, Any] | None = None, max_results: int = 100) -> dict[str, Any]:
        return self.client.post_json(
            f"/api/knowledge/v1/systems/{self.system_id}/system-description/query",
            {"revision_id": self.revision_id, "query_kind": query_kind, "filters": dict(filters or {}), "max_results": int(max_results)},
        )

    def query_reference_data(self, query_kind: str, *, filters: Mapping[str, Any] | None = None, max_results: int = 100) -> dict[str, Any]:
        return self.client.post_json(
            f"/api/knowledge/v1/systems/{self.system_id}/reference-data/query",
            {"revision_id": self.revision_id, "query_kind": query_kind, "filters": dict(filters or {}), "max_results": int(max_results)},
        )

    def query_foreign_data_persistence(self, query_kind: str, *, filters: Mapping[str, Any] | None = None, max_results: int = 100) -> dict[str, Any]:
        return self.client.post_json(
            f"/api/knowledge/v1/systems/{self.system_id}/foreign-data-persistence/query",
            {"revision_id": self.revision_id, "query_kind": query_kind, "filters": dict(filters or {}), "max_results": int(max_results)},
        )

    def _collect_interaction_page(self, suffix: str = "", *, filters: Mapping[str, Any] | None = None, max_results: int = 20_000, page_size: int = 500) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        base = f"/api/knowledge/v1/systems/{self.system_id}/interactions"
        path = base + (f"/{suffix.strip('/')}" if suffix else "")
        while len(items) < max_results:
            limit = min(page_size, max_results - len(items))
            params = {"revision_id": self.revision_id, "offset": offset, "limit": limit, **{key: value for key, value in dict(filters or {}).items() if value is not None}}
            page = self.client.get_json(path, params=params)
            page_items = [dict(item) for item in page.get("items") or () if isinstance(item, Mapping)]
            items.extend(page_items)
            total = int((page.get("page") or {}).get("total") or 0)
            offset += len(page_items)
            if not page_items or offset >= total:
                break
        return items[:max_results]

    def list_system_interactions(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 5_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page(filters=filters, max_results=max_results)

    def list_system_boundary_interactions(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 5_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("boundary-interactions", filters=filters, max_results=max_results)

    def list_repository_interaction_boundaries(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 20_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("boundaries", filters=filters, max_results=max_results)

    def list_system_interaction_execution_contexts(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 5_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("execution-contexts", filters=filters, max_results=max_results)

    def list_system_interaction_field_contracts(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 20_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("field-contracts", filters=filters, max_results=max_results)

    def list_system_interaction_diagnostics(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 10_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("diagnostics", filters=filters, max_results=max_results)

    def list_repository_interaction_coverage(self, *, filters: Mapping[str, Any] | None = None, max_results: int = 5_000) -> list[dict[str, Any]]:
        return self._collect_interaction_page("coverage", filters=filters, max_results=max_results)


def resolve_revision(client: AislClient, system_id: str, revision_id: str | None = None) -> KnowledgeApiRevision:
    """Resolve active once when omitted, then keep one immutable revision id."""
    sid = str(system_id or "").strip()
    if not sid:
        raise ValueError("system_id must not be empty")
    try:
        pinned = client.revision(sid, revision_id) if str(revision_id or "").strip() else client.active_revision(sid)
    except AislClientError as exc:
        raise KnowledgeApiSourceError(str(exc)) from exc
    artifacts = tuple(dict(item.raw) for item in pinned.products)
    capabilities = tuple(sorted(set(pinned.capabilities)))
    if not artifacts:
        raise KnowledgeApiSourceError(f"Knowledge API revision {pinned.revision_id!r} contains no published knowledge artifacts")
    return KnowledgeApiRevision(
        api_url=client.base_url,
        system_id=pinned.system_id,
        revision_id=pinned.revision_id,
        revision=dict(pinned.summary.raw),
        artifacts=artifacts,
        capabilities=capabilities,
        client=client,
    )


def _artifact_matches(artifact: Mapping[str, Any], *, model_kind: str | None, capabilities: Iterable[str]) -> bool:
    if model_kind and str(artifact.get("model_kind") or "") != model_kind:
        return False
    present = {str(value) for value in artifact.get("capabilities") or () if str(value)}
    return all(str(required) in present for required in capabilities)


def select_artifact(revision: KnowledgeApiRevision, requirement: KnowledgeRequirement) -> Mapping[str, Any]:
    candidates = [item for item in revision.artifacts if _artifact_matches(item, model_kind=requirement.model_kind, capabilities=requirement.required_capabilities)]
    if not candidates:
        required = {"model_kind": requirement.model_kind, "capabilities": list(requirement.required_capabilities)}
        raise KnowledgeApiSourceError(f"revision {revision.revision_id!r} does not provide knowledge required by the report: {required}")

    def physical_digest(item: Mapping[str, Any], role: str) -> str:
        matches = [raw for raw in item.get("physical_artifacts") or () if isinstance(raw, Mapping) and str(raw.get("role") or "") == role]
        if len(matches) > 1:
            raise KnowledgeApiSourceError(f"published product {item.get('artifact_id')!r} contains duplicate physical role {role!r}")
        return str(matches[0].get("sha256") or "") if matches else ""

    identities = {(physical_digest(item, "database"), str(item.get("content_fingerprint") or "")) for item in candidates}
    if len(identities) > 1:
        raise KnowledgeApiSourceError(
            "multiple different knowledge artifacts satisfy the report requirement: "
            + ", ".join(sorted(str(item.get("artifact_id") or "") for item in candidates))
        )
    return sorted(candidates, key=lambda item: str(item.get("artifact_id") or ""))[0]
