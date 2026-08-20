from __future__ import annotations

import re
from typing import Iterable

from knowledge_control_plane.api.generic_v1.models import (
    JobCreateRequest,
    JobOutputOptions,
    JobReusePolicy,
    JobTarget,
    PageMeta,
    ProductionCreateRequest,
    ProductionListResponse,
    ProductionRegistration,
    ProductionUpdateRequest,
    ScenarioSourceMode,
    SourceSnapshot,
)

from .errors import ResourceNotFound, RevisionConflict, RuntimeApiError
from .profiles import KnowledgeProfileService
from .repositories import RepositoryService
from .scenarios import ScenarioService
from .store import RuntimeStore, utc_now


def _default_production_id(system_id: str, profile_id: str) -> str:
    raw = f"{system_id}-{profile_id}"
    value = re.sub(r"[^A-Za-z0-9._:-]+", "-", raw).strip("-._:")
    return (value or "production")[:200]


class ProductionService:
    """Durable binding of system + Knowledge Profile + selected source repositories.

    This is control-plane configuration. It does not plan Knowledge Products and does
    not replace Scenario/Profile/Runner ownership.
    """

    def __init__(
        self,
        *,
        store: RuntimeStore,
        repositories: RepositoryService,
        profiles: KnowledgeProfileService,
        scenarios: ScenarioService,
    ) -> None:
        self.store = store
        self.repositories = repositories
        self.profiles = profiles
        self.scenarios = scenarios

    def list(self, *, offset: int, limit: int, search: str | None = None) -> ProductionListResponse:
        items = self.store.list_productions()
        if search:
            needle = search.casefold()
            items = [
                item for item in items
                if needle in item.production_id.casefold()
                or needle in item.system_id.casefold()
                or needle in (item.display_name or "").casefold()
                or needle in item.knowledge_profile_id.casefold()
            ]
        return ProductionListResponse(
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )

    def get(self, production_id: str) -> ProductionRegistration:
        item = self.store.get_production(production_id)
        if item is None:
            raise ResourceNotFound("production", production_id)
        return item

    def create(self, request: ProductionCreateRequest) -> ProductionRegistration:
        production_id = request.production_id or _default_production_id(
            request.system_id, request.knowledge_profile_id
        )
        if self.store.get_production(production_id) is not None:
            raise RuntimeApiError(409, "production_exists", f"production already exists: {production_id}")
        now = utc_now()
        production = ProductionRegistration(
            production_id=production_id,
            system_id=request.system_id,
            scenario_id=request.scenario_id,
            knowledge_profile_id=request.knowledge_profile_id,
            repository_ids=list(request.repository_ids),
            physical_model_path=request.physical_model_path,
            display_name=request.display_name,
            parameters=dict(request.parameters),
            refresh_policy=request.refresh_policy,
            enabled=request.enabled,
            created_at=now,
            updated_at=now,
            diagnostics=["production has not been freshness-checked yet"],
        )
        self.validate(production)
        self.store.insert_production(production)
        return production

    def update(self, production_id: str, request: ProductionUpdateRequest) -> ProductionRegistration:
        current = self.get(production_id)
        if current.revision != request.expected_revision:
            raise RevisionConflict("production", request.expected_revision, current.revision)
        updates = {
            name: getattr(request, name)
            for name in request.model_fields_set
            if name != "expected_revision"
        }
        updated = current.model_copy(
            update={
                **updates,
                "revision": current.revision + 1,
                "updated_at": utc_now(),
            }
        )
        self.validate(updated)
        self.store.update_production(updated)
        return updated

    def delete(self, production_id: str):
        from knowledge_control_plane.api.generic_v1.models import ResourceDeletedResponse

        self.get(production_id)
        if not self.store.delete_production(production_id):
            raise ResourceNotFound("production", production_id)
        return ResourceDeletedResponse(id=production_id)

    def validate(self, production: ProductionRegistration) -> None:
        scenario = self.scenarios.get(production.scenario_id)
        profile = self.profiles.get(production.knowledge_profile_id)
        if scenario.source_mode is ScenarioSourceMode.KNOWLEDGE_REVISIONS:
            raise RuntimeApiError(
                422,
                "production_source_mode_unsupported",
                "automatic source refresh requires a repository-backed scenario",
            )
        expected_scope = (
            "repository" if scenario.source_mode is ScenarioSourceMode.REPOSITORY else "workspace"
        )
        if profile.execution_scope.value != expected_scope:
            raise RuntimeApiError(
                422,
                "production_profile_scope_mismatch",
                "Knowledge Profile execution scope is incompatible with scenario source mode",
                details={
                    "scenario_id": scenario.scenario_id,
                    "source_mode": scenario.source_mode.value,
                    "knowledge_profile_id": profile.profile_id,
                    "execution_scope": profile.execution_scope.value,
                },
            )
        if scenario.source_mode is ScenarioSourceMode.REPOSITORY and len(production.repository_ids) != 1:
            raise RuntimeApiError(
                422,
                "production_repository_count_invalid",
                "single-repository scenario requires exactly one registered repository",
            )
        for repository_id in production.repository_ids:
            self.repositories.get(repository_id)
        # Reuse the canonical job validator for secrets and basic execution shape.
        self.build_job_request(production)

    def build_job_request(
        self,
        production: ProductionRegistration,
        *,
        source_snapshots: Iterable[SourceSnapshot] = (),
        source_snapshot_fingerprint: str | None = None,
        force_rebuild: bool = False,
    ) -> JobCreateRequest:
        scenario = self.scenarios.get(production.scenario_id)
        snapshots = list(source_snapshots)
        target = JobTarget(
            repository_id=(
                production.repository_ids[0]
                if scenario.source_mode is ScenarioSourceMode.REPOSITORY
                else None
            ),
            repository_ids=(
                list(production.repository_ids)
                if scenario.source_mode is ScenarioSourceMode.REPOSITORIES
                else []
            ),
            system_id=production.system_id,
            physical_model_path=production.physical_model_path,
        )
        return JobCreateRequest(
            display_name=production.display_name or production.system_id,
            target=target,
            scenario_id=production.scenario_id,
            knowledge_profile_id=production.knowledge_profile_id,
            parameters=dict(production.parameters),
            output=JobOutputOptions(),
            reuse_policy=(JobReusePolicy.FORCE_REBUILD if force_rebuild else JobReusePolicy.REUSE_IF_UNCHANGED),
            production_id=production.production_id,
            production_revision=production.revision,
            source_snapshots=snapshots,
            source_snapshot_fingerprint=source_snapshot_fingerprint,
        )

    def update_runtime_state(self, production: ProductionRegistration) -> ProductionRegistration:
        updated = production.model_copy(update={"updated_at": utc_now()})
        self.store.update_production(updated)
        return updated
