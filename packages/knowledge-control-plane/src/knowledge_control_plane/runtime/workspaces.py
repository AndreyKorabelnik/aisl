from __future__ import annotations

import re
import uuid

from knowledge_control_plane.api.generic_v1.models import (
    PageMeta,
    ResourceDeletedResponse,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceSummary,
    WorkspaceUpdateRequest,
)

from .errors import ResourceNotFound, RevisionConflict, RuntimeApiError
from .repositories import RepositoryService
from .store import RuntimeStore, utc_now


def _workspace_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._:-]+", "-", name).strip("-._:").lower()
    return slug or f"workspace-{uuid.uuid4().hex[:10]}"


class WorkspaceService:
    def __init__(self, store: RuntimeStore, repositories: RepositoryService) -> None:
        self.store = store
        self.repositories = repositories

    def _validate_repositories(self, repository_ids: list[str]) -> None:
        missing = [item for item in repository_ids if self.store.get_repository(item) is None]
        if missing:
            raise RuntimeApiError(
                400,
                "unknown_repository",
                "workspace contains unknown repositories",
                details={"repository_ids": missing},
            )

    def create(self, request: WorkspaceCreateRequest) -> WorkspaceSummary:
        self._validate_repositories(request.repository_ids)
        workspace_id = request.workspace_id or _workspace_id(request.name)
        if self.store.get_workspace(workspace_id) is not None:
            raise RuntimeApiError(409, "resource_exists", f"workspace already exists: {workspace_id}")
        now = utc_now()
        workspace = WorkspaceSummary(
            workspace_id=workspace_id,
            name=request.name,
            description=request.description,
            repository_ids=list(dict.fromkeys(request.repository_ids)),
            revision=1,
            created_at=now,
            updated_at=now,
        )
        self.store.insert_workspace(workspace)
        return workspace

    def list(self, *, offset: int, limit: int, search: str | None) -> WorkspaceListResponse:
        items = self.store.list_workspaces()
        if search:
            needle = search.casefold()
            items = [
                item
                for item in items
                if needle in item.name.casefold()
                or (item.description is not None and needle in item.description.casefold())
            ]
        total = len(items)
        return WorkspaceListResponse(
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=total),
        )

    def get(self, workspace_id: str) -> WorkspaceSummary:
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            raise ResourceNotFound("workspace", workspace_id)
        return workspace

    def update(self, workspace_id: str, request: WorkspaceUpdateRequest) -> WorkspaceSummary:
        current = self.get(workspace_id)
        if request.expected_revision != current.revision:
            raise RevisionConflict("workspace", request.expected_revision, current.revision)
        repository_ids = request.repository_ids if request.repository_ids is not None else current.repository_ids
        self._validate_repositories(repository_ids)
        updated = current.model_copy(
            update={
                "name": request.name if request.name is not None else current.name,
                "description": (
                    request.description
                    if "description" in request.model_fields_set
                    else current.description
                ),
                "repository_ids": list(dict.fromkeys(repository_ids)),
                "revision": current.revision + 1,
                "updated_at": utc_now(),
            }
        )
        self.store.update_workspace(updated)
        return updated

    def delete(self, workspace_id: str) -> ResourceDeletedResponse:
        if not self.store.delete_workspace(workspace_id):
            raise ResourceNotFound("workspace", workspace_id)
        return ResourceDeletedResponse(id=workspace_id)
