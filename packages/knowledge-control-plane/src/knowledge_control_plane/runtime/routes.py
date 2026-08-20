from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from knowledge_control_plane import __version__
from knowledge_control_plane.api.generic_v1.contract import ERROR_RESPONSES, GENERIC_API_PREFIX
from knowledge_control_plane.api.generic_v1.models import (
    ArtifactContentResponse,
    ArtifactListResponse,
    ArtifactSummary,
    AvailabilityStatus,
    CapabilitiesResponse,
    Capability,
    ComponentVersion,
    ConfigurationResponse,
    ConfigurationUpdateRequest,
    ConfigurationValidationRequest,
    ConfigurationValidationResponse,
    DiagnosticsBundleRequest,
    DiagnosticsBundleResponse,
    JobActionResponse,
    JobCommandPreviewResponse,
    JobComparisonResponse,
    JobCreateRequest,
    JobDetails,
    JobKind,
    JobListResponse,
    JobLogsResponse,
    JobRetryRequest,
    JobStatus,
    KnowledgeProductInfo,
    KnowledgeProductListResponse,
    LogLevel,
    LogStream,
    KnowledgeProfileCopyRequest,
    KnowledgeProfileCreateRequest,
    KnowledgeProfileDefinition,
    KnowledgeProfileListResponse,
    KnowledgeProfileOrigin,
    KnowledgeProfileResolutionResponse,
    KnowledgeProfileUpdateRequest,
    ScenarioDefinition,
    ScenarioListResponse,
    ProductionCreateRequest,
    ProductionFreshnessListResponse,
    ProductionFreshnessResponse,
    ProductionListResponse,
    ProductionRegistration,
    ProductionStructureResponse,
    ProductionUpdateRequest,
    ReproducibleCommandsResponse,
    RepositoryDiscoverRequest,
    RepositoryDiscoverResponse,
    RepositoryListResponse,
    RepositorySourceKind,
    RepositorySummary,
    ResourceDeletedResponse,
    RuntimeDiagnosticsResponse,
    VersionResponse,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceSummary,
    WorkspaceUpdateRequest,
)

from .context import RuntimeContext
from .jobs import TERMINAL_STATUSES

router = APIRouter(prefix=GENERIC_API_PREFIX)


def _context(request: Request) -> RuntimeContext:
    return request.app.state.knowledge_control_plane_runtime


@router.get("/version", response_model=VersionResponse, tags=["discovery"], responses=ERROR_RESPONSES)
def get_version(request: Request) -> VersionResponse:
    context = _context(request)
    validation = context.configuration.validate(ConfigurationValidationRequest())
    return VersionResponse(
        application_version=__version__,
        generated_at=datetime.now(UTC),
        components=[
            ComponentVersion(
                component=item.tool,
                version=item.version,
                status=item.status,
                executable=item.resolved_path,
                detail=None if item.resolved_path else f"command not found: {item.command}",
            )
            for item in validation.tools
        ],
    )


@router.get("/capabilities", response_model=CapabilitiesResponse, tags=["discovery"], responses=ERROR_RESPONSES)
def get_capabilities(request: Request) -> CapabilitiesResponse:
    context = _context(request)
    validation = context.configuration.validate(ConfigurationValidationRequest())
    tools = {item.tool: item for item in validation.tools}

    def available(tool: str) -> AvailabilityStatus:
        item = tools.get(tool)
        return item.status if item else AvailabilityStatus.UNAVAILABLE

    api_status = AvailabilityStatus.UNAVAILABLE
    api_reason: str | None = None
    try:
        health = context.knowledge_api.health()
        if health.get("status") == "ok":
            api_status = AvailabilityStatus.AVAILABLE
        elif health.get("status") == "degraded":
            api_status = AvailabilityStatus.DEGRADED
        else:
            api_reason = "Knowledge API health response is not healthy"
    except Exception as exc:
        api_reason = str(exc)

    runner = available("static_analysis_runner")
    execution_status = (
        AvailabilityStatus.AVAILABLE
        if runner is AvailabilityStatus.AVAILABLE
        else AvailabilityStatus.UNAVAILABLE
    )
    return CapabilitiesResponse(
        capabilities=[
            Capability(
                id="knowledge_execution",
                status=execution_status,
                description="Compile and execute a Knowledge Profile through Core and KLC",
                reason=None if execution_status is AvailabilityStatus.AVAILABLE else "static-analysis-runner must be available",
            ),
            Capability(
                id="publication_bundle",
                status=AvailabilityStatus.AVAILABLE,
                description="Build a self-contained AISL publication bundle for import by AISL Server",
            ),
            Capability(
                id="published_knowledge_inputs",
                status=api_status,
                description="Read pinned AISL revisions when a composition scenario consumes already published knowledge",
                reason=api_reason,
                metadata={"base_url": context.settings.knowledge_api_base_url},
            ),
            Capability(
                id="operational_diagnostics",
                status=AvailabilityStatus.AVAILABLE,
                description="Inspect jobs and create sanitized diagnostics bundles",
            ),
        ]
    )


@router.get("/diagnostics", response_model=RuntimeDiagnosticsResponse, tags=["diagnostics"], responses=ERROR_RESPONSES)
def get_runtime_diagnostics(request: Request) -> RuntimeDiagnosticsResponse:
    return _context(request).diagnostics.system()


@router.get("/diagnostics/runtime-log", response_class=PlainTextResponse, tags=["diagnostics"], responses=ERROR_RESPONSES)
def download_runtime_log(request: Request, max_bytes: Annotated[int, Query(ge=1024, le=10_000_000)] = 2_000_000) -> PlainTextResponse:
    path = _context(request).settings.runtime_log_path
    if not path.is_file():
        return PlainTextResponse("", headers={"Content-Disposition": 'attachment; filename="knowledge-control-plane.log"'})
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - max_bytes))
        content = stream.read().decode("utf-8", errors="replace")
    return PlainTextResponse(content, headers={"Content-Disposition": 'attachment; filename="knowledge-control-plane.log"'})


@router.get("/configuration", response_model=ConfigurationResponse, tags=["configuration"], responses=ERROR_RESPONSES)
def get_configuration(request: Request) -> ConfigurationResponse:
    return _context(request).configuration.get()


@router.put("/configuration", response_model=ConfigurationResponse, tags=["configuration"], responses=ERROR_RESPONSES)
def update_configuration(request: Request, payload: ConfigurationUpdateRequest) -> ConfigurationResponse:
    return _context(request).configuration.update(payload)


@router.post("/configuration/validate", response_model=ConfigurationValidationResponse, tags=["configuration"], responses=ERROR_RESPONSES)
def validate_configuration(request: Request, payload: ConfigurationValidationRequest) -> ConfigurationValidationResponse:
    return _context(request).configuration.validate(payload)


@router.get("/repositories", response_model=RepositoryListResponse, tags=["repositories"], responses=ERROR_RESPONSES)
def list_repositories(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50, source_kind: RepositorySourceKind | None = None, search: str | None = None) -> RepositoryListResponse:
    return _context(request).repositories.list(offset=offset, limit=limit, source_kind=source_kind, search=search)


@router.post("/repositories/discover", response_model=RepositoryDiscoverResponse, tags=["repositories"], responses=ERROR_RESPONSES)
def discover_repositories(request: Request, payload: RepositoryDiscoverRequest) -> RepositoryDiscoverResponse:
    return _context(request).repositories.discover(payload)


@router.get("/repositories/{repository_id}", response_model=RepositorySummary, tags=["repositories"], responses=ERROR_RESPONSES)
def get_repository(request: Request, repository_id: str) -> RepositorySummary:
    return _context(request).repositories.get(repository_id)


@router.get("/productions", response_model=ProductionListResponse, tags=["productions"], responses=ERROR_RESPONSES)
def list_productions(
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    search: str | None = None,
) -> ProductionListResponse:
    return _context(request).productions.list(offset=offset, limit=limit, search=search)


@router.post(
    "/productions",
    response_model=ProductionRegistration,
    status_code=status.HTTP_201_CREATED,
    tags=["productions"],
    responses=ERROR_RESPONSES,
)
def create_production(request: Request, payload: ProductionCreateRequest) -> ProductionRegistration:
    return _context(request).productions.create(payload)


@router.post(
    "/productions/refresh-check-due",
    response_model=ProductionFreshnessListResponse,
    tags=["productions"],
    responses=ERROR_RESPONSES,
)
async def refresh_check_due(request: Request, enqueue: bool = True) -> ProductionFreshnessListResponse:
    return ProductionFreshnessListResponse(items=await _context(request).freshness.check_due(enqueue=enqueue))


@router.get("/productions/{production_id}", response_model=ProductionRegistration, tags=["productions"], responses=ERROR_RESPONSES)
def get_production(request: Request, production_id: str) -> ProductionRegistration:
    return _context(request).productions.get(production_id)


@router.patch("/productions/{production_id}", response_model=ProductionRegistration, tags=["productions"], responses=ERROR_RESPONSES)
def update_production(
    request: Request,
    production_id: str,
    payload: ProductionUpdateRequest,
) -> ProductionRegistration:
    return _context(request).productions.update(production_id, payload)


@router.delete("/productions/{production_id}", response_model=ResourceDeletedResponse, tags=["productions"], responses=ERROR_RESPONSES)
def delete_production(request: Request, production_id: str) -> ResourceDeletedResponse:
    return _context(request).productions.delete(production_id)


@router.post(
    "/productions/{production_id}/refresh-check",
    response_model=ProductionFreshnessResponse,
    tags=["productions"],
    responses=ERROR_RESPONSES,
)
async def refresh_check_production(
    request: Request,
    production_id: str,
    enqueue: bool = True,
    force: bool = False,
) -> ProductionFreshnessResponse:
    return await _context(request).freshness.check(production_id, enqueue=enqueue, force=force)


@router.get("/workspaces", response_model=WorkspaceListResponse, tags=["workspaces"], responses=ERROR_RESPONSES)
def list_workspaces(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50, search: str | None = None) -> WorkspaceListResponse:
    return _context(request).workspaces.list(offset=offset, limit=limit, search=search)


@router.post("/workspaces", response_model=WorkspaceSummary, status_code=status.HTTP_201_CREATED, tags=["workspaces"], responses=ERROR_RESPONSES)
def create_workspace(request: Request, payload: WorkspaceCreateRequest) -> WorkspaceSummary:
    return _context(request).workspaces.create(payload)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSummary, tags=["workspaces"], responses=ERROR_RESPONSES)
def get_workspace(request: Request, workspace_id: str) -> WorkspaceSummary:
    return _context(request).workspaces.get(workspace_id)


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceSummary, tags=["workspaces"], responses=ERROR_RESPONSES)
def update_workspace(request: Request, workspace_id: str, payload: WorkspaceUpdateRequest) -> WorkspaceSummary:
    return _context(request).workspaces.update(workspace_id, payload)


@router.delete("/workspaces/{workspace_id}", response_model=ResourceDeletedResponse, tags=["workspaces"], responses=ERROR_RESPONSES)
def delete_workspace(request: Request, workspace_id: str) -> ResourceDeletedResponse:
    return _context(request).workspaces.delete(workspace_id)


@router.get("/knowledge-products", response_model=KnowledgeProductListResponse, tags=["knowledge-products"], responses=ERROR_RESPONSES)
def list_knowledge_products(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 100, search: str | None = None) -> KnowledgeProductListResponse:
    return _context(request).knowledge_products.list(offset=offset, limit=limit, search=search)


@router.get("/knowledge-products/{knowledge_id:path}", response_model=KnowledgeProductInfo, tags=["knowledge-products"], responses=ERROR_RESPONSES)
def get_knowledge_product(request: Request, knowledge_id: str) -> KnowledgeProductInfo:
    return _context(request).knowledge_products.get(knowledge_id)


@router.get("/knowledge-profiles", response_model=KnowledgeProfileListResponse, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def list_knowledge_profiles(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50, search: str | None = None, origin: KnowledgeProfileOrigin | None = None) -> KnowledgeProfileListResponse:
    return _context(request).profiles.list(offset=offset, limit=limit, search=search, origin=origin)


@router.post("/knowledge-profiles", response_model=KnowledgeProfileDefinition, status_code=status.HTTP_201_CREATED, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def create_knowledge_profile(request: Request, payload: KnowledgeProfileCreateRequest) -> KnowledgeProfileDefinition:
    return _context(request).profiles.create(payload)


@router.get("/knowledge-profiles/{profile_id:path}", response_model=KnowledgeProfileDefinition, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def get_knowledge_profile(request: Request, profile_id: str) -> KnowledgeProfileDefinition:
    return _context(request).profiles.get(profile_id)


@router.patch("/knowledge-profiles/{profile_id:path}", response_model=KnowledgeProfileDefinition, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def update_knowledge_profile(request: Request, profile_id: str, payload: KnowledgeProfileUpdateRequest) -> KnowledgeProfileDefinition:
    return _context(request).profiles.update(profile_id, payload)


@router.delete("/knowledge-profiles/{profile_id:path}", response_model=ResourceDeletedResponse, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def delete_knowledge_profile(request: Request, profile_id: str) -> ResourceDeletedResponse:
    _context(request).profiles.delete(profile_id)
    return ResourceDeletedResponse(id=profile_id)


@router.post("/knowledge-profiles/{profile_id:path}/copy", response_model=KnowledgeProfileDefinition, status_code=status.HTTP_201_CREATED, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def copy_knowledge_profile(request: Request, profile_id: str, payload: KnowledgeProfileCopyRequest) -> KnowledgeProfileDefinition:
    return _context(request).profiles.copy(profile_id, payload)


@router.get("/knowledge-profiles/{profile_id:path}/resolution", response_model=KnowledgeProfileResolutionResponse, tags=["knowledge-profiles"], responses=ERROR_RESPONSES)
def resolve_knowledge_profile(request: Request, profile_id: str) -> KnowledgeProfileResolutionResponse:
    return _context(request).profiles.resolve(profile_id)


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["scenarios"], responses=ERROR_RESPONSES)
def list_scenarios(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50, search: str | None = None) -> ScenarioListResponse:
    return _context(request).scenarios.list(offset=offset, limit=limit, search=search)


@router.get("/scenarios/{scenario_id:path}", response_model=ScenarioDefinition, tags=["scenarios"], responses=ERROR_RESPONSES)
def get_scenario(request: Request, scenario_id: str) -> ScenarioDefinition:
    return _context(request).scenarios.get(scenario_id)


@router.post("/jobs/preview", response_model=JobCommandPreviewResponse, tags=["jobs"], responses=ERROR_RESPONSES)
def preview_job(request: Request, payload: JobCreateRequest) -> JobCommandPreviewResponse:
    return _context(request).jobs.preview(payload)


@router.post("/jobs", response_model=JobDetails, status_code=status.HTTP_202_ACCEPTED, tags=["jobs"], responses=ERROR_RESPONSES)
async def create_job(request: Request, payload: JobCreateRequest) -> JobDetails:
    return await _context(request).jobs.create(payload)


@router.get("/jobs", response_model=JobListResponse, tags=["jobs"], responses=ERROR_RESPONSES)
def list_jobs(request: Request, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50, job_status: Annotated[JobStatus | None, Query(alias="status")] = None, kind: JobKind | None = None) -> JobListResponse:
    return _context(request).jobs.list(offset=offset, limit=limit, status=job_status, kind=kind)


@router.get("/jobs/{job_id}/production-structure", response_model=ProductionStructureResponse, tags=["jobs"], responses=ERROR_RESPONSES)
def get_job_production_structure(request: Request, job_id: str) -> ProductionStructureResponse:
    return _context(request).production_structure.for_job(job_id)


@router.get("/jobs/{job_id}", response_model=JobDetails, tags=["jobs"], responses=ERROR_RESPONSES)
def get_job(request: Request, job_id: str) -> JobDetails:
    return _context(request).jobs.get(job_id)


@router.delete("/jobs/{job_id}", response_model=ResourceDeletedResponse, tags=["jobs"], responses=ERROR_RESPONSES)
def delete_job(request: Request, job_id: str) -> ResourceDeletedResponse:
    return _context(request).jobs.delete(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobActionResponse, status_code=status.HTTP_202_ACCEPTED, tags=["jobs"], responses=ERROR_RESPONSES)
async def cancel_job(request: Request, job_id: str) -> JobActionResponse:
    return await _context(request).jobs.cancel(job_id)


@router.post("/jobs/{job_id}/retry", response_model=JobActionResponse, status_code=status.HTTP_202_ACCEPTED, tags=["jobs"], responses=ERROR_RESPONSES)
async def retry_job(request: Request, job_id: str, payload: JobRetryRequest) -> JobActionResponse:
    return await _context(request).jobs.retry(job_id, payload)


@router.get("/jobs/{job_id}/logs", response_model=JobLogsResponse, tags=["jobs"], responses=ERROR_RESPONSES)
def get_job_logs(request: Request, job_id: str, cursor: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=5000)] = 500, level: LogLevel | None = None, stream: LogStream | None = None, stage: str | None = None, search: str | None = None) -> JobLogsResponse:
    return _context(request).jobs.logs(job_id=job_id, cursor=cursor, limit=limit, level=level, stream=stream, stage=stage, search=search)


@router.get("/jobs/{job_id}/logs/download", response_class=Response, tags=["diagnostics"], responses=ERROR_RESPONSES)
def download_job_logs(request: Request, job_id: str, level: LogLevel | None = None, stream: LogStream | None = None, stage: str | None = None, search: str | None = None) -> PlainTextResponse:
    content = _context(request).diagnostics.log_text(job_id, level=level, stream=stream, stage=stage, search=search)
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{job_id}.log"'})


@router.get("/jobs/{job_id}/commands", response_model=ReproducibleCommandsResponse, tags=["diagnostics"], responses=ERROR_RESPONSES)
def get_reproducible_commands(request: Request, job_id: str) -> ReproducibleCommandsResponse:
    return _context(request).diagnostics.reproducible_commands(job_id)


@router.get("/jobs/{job_id}/compare/{other_job_id}", response_model=JobComparisonResponse, tags=["diagnostics"], responses=ERROR_RESPONSES)
def compare_jobs(request: Request, job_id: str, other_job_id: str) -> JobComparisonResponse:
    return _context(request).diagnostics.compare(job_id, other_job_id)


@router.post("/jobs/{job_id}/diagnostics-bundle", response_model=DiagnosticsBundleResponse, status_code=status.HTTP_201_CREATED, tags=["diagnostics"], responses=ERROR_RESPONSES)
def create_diagnostics_bundle(request: Request, job_id: str, payload: DiagnosticsBundleRequest) -> DiagnosticsBundleResponse:
    return _context(request).diagnostics.create_bundle(job_id, payload)


@router.get(
    "/jobs/{job_id}/events",
    tags=["jobs"],
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {}}}, **ERROR_RESPONSES},
)
async def stream_job_events(request: Request, job_id: str, after: Annotated[int, Query(ge=0)] = 0) -> StreamingResponse:
    context = _context(request)
    context.jobs.get(job_id)

    async def generate():
        cursor = after
        idle_cycles = 0
        while True:
            events = context.store.list_events(job_id, after=cursor)
            if events:
                idle_cycles = 0
                for event in events:
                    cursor = event.sequence
                    yield f"id: {event.sequence}\nevent: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
            else:
                idle_cycles += 1
            job = context.jobs.get(job_id)
            if job.status in TERMINAL_STATUSES and not events:
                break
            if await request.is_disconnected():
                break
            if idle_cycles >= 100:
                idle_cycles = 0
                yield ": heartbeat\n\n"
            await asyncio.sleep(context.settings.event_poll_interval_seconds)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactListResponse, tags=["artifacts"], responses=ERROR_RESPONSES)
def list_job_artifacts(request: Request, job_id: str) -> ArtifactListResponse:
    _context(request).jobs.get(job_id)
    return _context(request).artifacts.list_for_job(job_id)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactSummary, tags=["artifacts"], responses=ERROR_RESPONSES)
def get_artifact(request: Request, artifact_id: str) -> ArtifactSummary:
    return _context(request).artifacts.get(artifact_id)[0]


@router.get("/artifacts/{artifact_id}/content", response_model=ArtifactContentResponse, tags=["artifacts"], responses=ERROR_RESPONSES)
def get_artifact_content(request: Request, artifact_id: str, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=5_000_000)] = 500_000) -> ArtifactContentResponse:
    return _context(request).artifacts.content(artifact_id, offset=offset, limit=limit)


@router.get(
    "/artifacts/{artifact_id}/download",
    response_class=FileResponse,
    tags=["artifacts"],
    responses={200: {"content": {"application/octet-stream": {}}}, **ERROR_RESPONSES},
)
def download_artifact(request: Request, artifact_id: str) -> FileResponse:
    summary, path = _context(request).artifacts.get(artifact_id)
    return FileResponse(path, media_type=summary.media_type, filename=summary.name)
