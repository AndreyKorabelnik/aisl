from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from knowledge_control_plane.api.generic_v1.models import (
    ScenarioSourceMode,
    JobCreateRequest,
    JobOutputOptions,
    JobReusePolicy,
    JobStatus,
    JobTarget,
    KnowledgeRevisionInput,
    RepositoryDiscoverRequest,
)

from .context import RuntimeContext
from .errors import RuntimeApiError


@dataclass(frozen=True, slots=True)
class OneShotRunOptions:
    scenario_id: str
    system_id: str
    repositories: tuple[str, ...] = ()
    knowledge_revisions: tuple[KnowledgeRevisionInput, ...] = ()
    physical_model_path: str | None = None
    display_name: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    output_path: str | None = None
    replace: bool = False
    force_rebuild: bool = False


def _resolve_repository_id(context: RuntimeContext, repository_path: str) -> str:
    requested = Path(repository_path).expanduser().resolve()
    discovered = context.repositories.discover(
        RepositoryDiscoverRequest(
            roots=[str(requested)],
            refresh=False,
            defer_checkout=True,
        )
    )
    if not discovered.repositories:
        raise RuntimeApiError(
            404,
            "repository_not_found",
            f"repository was not discovered: {requested}",
            details={"warnings": discovered.warnings},
        )
    exact = [
        item
        for item in discovered.repositories
        if Path(item.location).expanduser().resolve() == requested
    ]
    if len(exact) == 1:
        return exact[0].repository_id
    if len(discovered.repositories) == 1:
        return discovered.repositories[0].repository_id
    raise RuntimeApiError(
        409,
        "repository_ambiguous",
        "repository path contains multiple independently discoverable projects; select one project directory",
        details={
            "requested": str(requested),
            "candidates": [
                {"repository_id": item.repository_id, "location": item.location}
                for item in discovered.repositories
            ],
        },
    )


def build_job_request(context: RuntimeContext, options: OneShotRunOptions) -> JobCreateRequest:
    scenario = context.scenarios.get(options.scenario_id)
    profile = context.profiles.get(scenario.knowledge_profile_id)
    repository_id: str | None = None
    repository_ids: list[str] = []
    revisions = list(options.knowledge_revisions)

    if scenario.source_mode is ScenarioSourceMode.REPOSITORY:
        if len(options.repositories) != 1:
            raise RuntimeApiError(
                422,
                "repository_required",
                f"scenario {scenario.scenario_id} requires --repository exactly once",
            )
        if revisions:
            raise RuntimeApiError(
                422,
                "knowledge_revisions_not_allowed",
                f"repository scenario {scenario.scenario_id} does not accept --knowledge-revision",
            )
        repository_id = _resolve_repository_id(context, options.repositories[0])
    elif scenario.source_mode is ScenarioSourceMode.REPOSITORIES:
        if not options.repositories:
            raise RuntimeApiError(
                422,
                "repositories_required",
                f"scenario {scenario.scenario_id} requires one or more --repository values",
            )
        if revisions:
            raise RuntimeApiError(
                422,
                "knowledge_revisions_not_allowed",
                f"source-backed workspace scenario {scenario.scenario_id} does not accept --knowledge-revision",
            )
        repository_ids = [_resolve_repository_id(context, value) for value in options.repositories]
        if len(set(repository_ids)) != len(repository_ids):
            raise RuntimeApiError(422, "duplicate_repository", "the same repository was selected more than once")
    elif scenario.source_mode is ScenarioSourceMode.KNOWLEDGE_REVISIONS:
        if options.repositories:
            raise RuntimeApiError(
                422,
                "repository_not_allowed",
                f"knowledge-revision scenario {scenario.scenario_id} does not accept --repository",
            )
        if not revisions:
            raise RuntimeApiError(
                422,
                "knowledge_revisions_required",
                f"scenario {scenario.scenario_id} requires --knowledge-revision SYSTEM_ID:REVISION_ID",
            )
    else:  # pragma: no cover
        raise RuntimeApiError(422, "unsupported_scenario_source_mode", str(scenario.source_mode))


    return JobCreateRequest(
        display_name=options.display_name or options.system_id,
        target=JobTarget(
            repository_id=repository_id,
            repository_ids=repository_ids,
            system_id=options.system_id,
            physical_model_path=options.physical_model_path,
            knowledge_revisions=revisions,
        ),
        scenario_id=scenario.scenario_id,
        knowledge_profile_id=profile.profile_id,
        parameters=dict(options.parameters),
        output=JobOutputOptions(output_path=options.output_path, replace=options.replace),
        reuse_policy=(
            JobReusePolicy.FORCE_REBUILD
            if options.force_rebuild
            else JobReusePolicy.REUSE_IF_UNCHANGED
        ),
    )


async def run_one_shot(
    context: RuntimeContext,
    options: OneShotRunOptions,
    *,
    on_log: Callable[[str], None] | None = None,
) -> Any:
    request = build_job_request(context, options)
    await context.jobs.start()
    created = None
    cursor = 0
    try:
        created = await context.jobs.create(request)
        heartbeat_seconds = float(getattr(context.settings, "one_shot_heartbeat_seconds", 30.0))
        last_visible_log = time.monotonic()
        if on_log is not None:
            on_log(f"run_log={context.settings.job_run_log_path(created.job_id)}")
        while True:
            if on_log is not None:
                page = context.jobs.logs(job_id=created.job_id, cursor=cursor, limit=500)
                for entry in page.entries:
                    stage = f"[{entry.stage}] " if entry.stage else ""
                    on_log(f"{entry.timestamp.isoformat()} {entry.level.value.upper():7s} {stage}{entry.message}")
                if page.entries:
                    cursor = page.entries[-1].sequence + 1
                    last_visible_log = time.monotonic()

            current = context.jobs.get(created.job_id)
            if current.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
                if on_log is not None:
                    page = context.jobs.logs(job_id=created.job_id, cursor=cursor, limit=500)
                    for entry in page.entries:
                        stage = f"[{entry.stage}] " if entry.stage else ""
                        on_log(f"{entry.timestamp.isoformat()} {entry.level.value.upper():7s} {stage}{entry.message}")
                return current
            if on_log is not None and time.monotonic() - last_visible_log >= heartbeat_seconds:
                await context.jobs.heartbeat(created.job_id)
                last_visible_log = time.monotonic()
            await asyncio.sleep(context.settings.event_poll_interval_seconds)
    except asyncio.CancelledError:
        if created is not None:
            await context.jobs.cancel(created.job_id)
        raise
    finally:
        await context.jobs.stop()


def parse_knowledge_revision(value: str) -> KnowledgeRevisionInput:
    system_id, separator, revision_id = value.partition(":")
    if not separator or not system_id.strip() or not revision_id.strip():
        raise ValueError("knowledge revision must have SYSTEM_ID:REVISION_ID format")
    return KnowledgeRevisionInput(system_id=system_id.strip(), revision_id=revision_id.strip())


def parse_parameters(values: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in values:
        name, separator, value = raw.partition("=")
        if not separator or not name.strip():
            raise ValueError("parameter must have NAME=VALUE format")
        result[name.strip()] = value
    return result
