"""Typed request and response models for the generic orchestration API v1.

The models in this module are the source of truth for the OpenAPI contract. Runtime
implementations may add internal persistence or execution models, but public HTTP
payloads must remain compatible with these types.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ContractModel(BaseModel):
    """Base model with strict public-payload behaviour."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApiError(ContractModel):
    schema_version: str = "generic_api/v1"
    code: Identifier
    message: NonEmptyText
    details: dict[str, JsonValue] = Field(default_factory=dict)
    request_id: str | None = None


class PageMeta(ContractModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=500)
    total: int = Field(ge=0)


class ResourceDeletedResponse(ContractModel):
    id: Identifier
    status: str = "deleted"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class ComponentVersion(ContractModel):
    component: Identifier
    version: str | None = None
    status: AvailabilityStatus
    executable: str | None = None
    detail: str | None = None


class VersionResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    application: str = "knowledge-control-plane"
    application_version: str
    api_version: str = "v1"
    generated_at: datetime
    components: list[ComponentVersion] = Field(default_factory=list)


class Capability(ContractModel):
    id: Identifier
    status: AvailabilityStatus
    description: str
    reason: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CapabilitiesResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    capabilities: list[Capability]


class PathStatus(ContractModel):
    value: str | None = None
    configured: bool = False
    exists: bool | None = None
    readable: bool | None = None
    writable: bool | None = None


class RuntimePaths(ContractModel):
    repository_roots: list[str] = Field(default_factory=list)
    analysis_output_root: PathStatus
    runtime_root: PathStatus
    allowed_output_roots: list[str] = Field(default_factory=list)


class ToolCommands(ContractModel):
    static_analysis_runner: NonEmptyText = "static-analysis-runner"


class ConfigurationResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    revision: int = Field(ge=1)
    paths: RuntimePaths
    commands: ToolCommands


class PathConfigurationPatch(ContractModel):
    repository_roots: list[str] | None = None
    analysis_output_root: str | None = None
    runtime_root: str | None = None
    allowed_output_roots: list[str] | None = None


class ToolCommandsPatch(ContractModel):
    static_analysis_runner: str | None = None


class ConfigurationPatch(ContractModel):
    paths: PathConfigurationPatch | None = None
    commands: ToolCommandsPatch | None = None


class ConfigurationUpdateRequest(ContractModel):
    expected_revision: int = Field(ge=1)
    configuration: ConfigurationPatch


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(ContractModel):
    code: Identifier
    severity: ValidationSeverity
    field: str | None = None
    message: NonEmptyText
    remediation: str | None = None


class ResolvedTool(ContractModel):
    tool: Identifier
    command: str
    resolved_path: str | None = None
    version: str | None = None
    status: AvailabilityStatus


class ConfigurationValidationRequest(ContractModel):
    configuration: ConfigurationPatch | None = None


class ConfigurationValidationResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    tools: list[ResolvedTool] = Field(default_factory=list)


class RepositorySourceKind(StrEnum):
    LOCAL = "local"
    BITBUCKET = "bitbucket"


class RepositoryStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class RepositorySummary(ContractModel):
    repository_id: Identifier
    name: NonEmptyText
    source_kind: RepositorySourceKind
    location: NonEmptyText
    status: RepositoryStatus
    default_branch: str | None = None
    revision: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RepositoryListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[RepositorySummary]
    page: PageMeta


class GitTrackedRefKind(StrEnum):
    HEAD = "head"
    BRANCH = "branch"
    REF = "ref"


class GitTrackedRef(ContractModel):
    kind: GitTrackedRefKind = GitTrackedRefKind.HEAD
    name: str | None = None

    @model_validator(mode="after")
    def validate_name(self) -> "GitTrackedRef":
        if self.kind is GitTrackedRefKind.HEAD:
            if self.name not in {None, "", "HEAD"}:
                raise ValueError("HEAD tracked ref must not define a custom name")
            self.name = None
        elif not (self.name or "").strip():
            raise ValueError("branch/ref tracked ref requires name")
        return self


class RemoteRepositoryCandidate(ContractModel):
    location: NonEmptyText
    name: str | None = None
    tracked_ref: GitTrackedRef | None = None


class RepositoryDiscoverRequest(ContractModel):
    roots: list[str] | None = None
    remotes: list[RemoteRepositoryCandidate] | None = None
    refresh: bool = False
    defer_checkout: bool = False

    @model_validator(mode="after")
    def require_a_source(self) -> "RepositoryDiscoverRequest":
        if not self.roots and not self.remotes:
            raise ValueError("at least one local root or remote repository is required")
        return self


class RepositoryDiscoverResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    repositories: list[RepositorySummary]
    discovered_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class SourceSnapshotKind(StrEnum):
    GIT = "git"
    FILE = "file"


class SourceSnapshotAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class SourceSnapshot(ContractModel):
    source_id: Identifier
    source_kind: SourceSnapshotKind
    location: NonEmptyText
    requested_ref: GitTrackedRef | None = None
    resolved_version: dict[str, JsonValue] = Field(default_factory=dict)
    checked_at: datetime
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    availability: SourceSnapshotAvailability = SourceSnapshotAvailability.AVAILABLE
    diagnostic: str | None = None


class ProductionRefreshMode(StrEnum):
    MANUAL = "manual"
    POLL = "poll"


class ProductionRefreshPolicy(ContractModel):
    mode: ProductionRefreshMode = ProductionRefreshMode.MANUAL
    interval: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "ProductionRefreshPolicy":
        if self.mode is ProductionRefreshMode.POLL and not (self.interval or "").strip():
            raise ValueError("poll refresh policy requires interval")
        if self.mode is ProductionRefreshMode.MANUAL and self.interval is not None:
            raise ValueError("manual refresh policy must not define interval")
        return self


class ProductionFreshnessStatus(StrEnum):
    UP_TO_DATE = "up_to_date"
    CHANGE_DETECTED = "change_detected"
    STALE = "stale"
    UPDATE_QUEUED = "update_queued"
    UPDATE_RUNNING = "update_running"
    UPDATE_FAILED = "update_failed"
    SOURCE_UNAVAILABLE = "source_unavailable"


class ProductionRegistration(ContractModel):
    production_id: Identifier
    system_id: Identifier
    scenario_id: Identifier
    knowledge_profile_id: Identifier
    repository_ids: list[Identifier] = Field(min_length=1)
    physical_model_path: str | None = None
    display_name: str | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    refresh_policy: ProductionRefreshPolicy = Field(default_factory=ProductionRefreshPolicy)
    enabled: bool = True
    revision: int = Field(default=1, ge=1)
    freshness_status: ProductionFreshnessStatus = ProductionFreshnessStatus.STALE
    last_checked_at: datetime | None = None
    last_observed_source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    last_successful_bundle_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_successful_production_revision: int | None = Field(default=None, ge=1)
    last_successful_source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    desired_source_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    last_refresh_job_id: Identifier | None = None
    diagnostics: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_sources(self) -> "ProductionRegistration":
        if len(set(self.repository_ids)) != len(self.repository_ids):
            raise ValueError("repository_ids must contain unique values")
        return self


class ProductionCreateRequest(ContractModel):
    production_id: Identifier | None = None
    system_id: Identifier
    scenario_id: Identifier
    knowledge_profile_id: Identifier
    repository_ids: list[Identifier] = Field(min_length=1)
    physical_model_path: str | None = None
    display_name: str | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    refresh_policy: ProductionRefreshPolicy = Field(default_factory=ProductionRefreshPolicy)
    enabled: bool = True


class ProductionUpdateRequest(ContractModel):
    expected_revision: int = Field(ge=1)
    scenario_id: Identifier | None = None
    knowledge_profile_id: Identifier | None = None
    repository_ids: list[Identifier] | None = None
    physical_model_path: str | None = None
    display_name: str | None = None
    parameters: dict[str, JsonValue] | None = None
    refresh_policy: ProductionRefreshPolicy | None = None
    enabled: bool | None = None


class ProductionListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[ProductionRegistration]
    page: PageMeta


class ProductionFreshnessResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    production: ProductionRegistration
    observed_source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    changed_source_ids: list[Identifier] = Field(default_factory=list)
    enqueued_job_id: Identifier | None = None


class ProductionFreshnessListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[ProductionFreshnessResponse] = Field(default_factory=list)


class WorkspaceSummary(ContractModel):
    workspace_id: Identifier
    name: NonEmptyText
    description: str | None = None
    repository_ids: list[Identifier]
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class WorkspaceListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[WorkspaceSummary]
    page: PageMeta


class WorkspaceCreateRequest(ContractModel):
    workspace_id: Identifier | None = None
    name: NonEmptyText
    description: str | None = None
    repository_ids: list[Identifier] = Field(min_length=1)


class WorkspaceUpdateRequest(ContractModel):
    expected_revision: int = Field(ge=1)
    name: NonEmptyText | None = None
    description: str | None = None
    repository_ids: list[Identifier] | None = None


class ExecutionScope(StrEnum):
    REPOSITORY = "repository"
    WORKSPACE = "workspace"


class ScenarioSourceMode(StrEnum):
    REPOSITORY = "repository"
    REPOSITORIES = "repositories"
    KNOWLEDGE_REVISIONS = "knowledge_revisions"


class ScenarioParameter(ContractModel):
    name: Identifier
    value_type: str
    required: bool = False
    default: JsonValue = None
    description: str | None = None
    allowed_values: list[JsonValue] | None = None


class KnowledgeProfileOrigin(StrEnum):
    PLATFORM = "platform"
    USER = "user"


class KnowledgeProfileDefinition(ContractModel):
    profile_id: Identifier
    name: NonEmptyText
    execution_scope: ExecutionScope
    origin: KnowledgeProfileOrigin = KnowledgeProfileOrigin.PLATFORM
    version: str | None = None
    description: str | None = None
    source_path: str = "builtin"
    knowledge_ids: list[Identifier]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_knowledge_ids(self) -> "KnowledgeProfileDefinition":
        if not self.knowledge_ids:
            raise ValueError("knowledge profile must contain at least one knowledge_id")
        if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
            raise ValueError("knowledge profile knowledge_ids must be unique")
        return self


class KnowledgeProfileCreateRequest(ContractModel):
    profile_id: Identifier | None = None
    name: NonEmptyText
    execution_scope: ExecutionScope
    description: str | None = None
    knowledge_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_knowledge_ids(self) -> "KnowledgeProfileCreateRequest":
        if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
            raise ValueError("knowledge profile knowledge_ids must be unique")
        return self


class KnowledgeProfileUpdateRequest(ContractModel):
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    name: NonEmptyText | None = None
    execution_scope: ExecutionScope | None = None
    description: str | None = None
    knowledge_ids: list[Identifier] | None = None

    @model_validator(mode="after")
    def validate_knowledge_ids(self) -> "KnowledgeProfileUpdateRequest":
        if self.knowledge_ids is not None:
            if not self.knowledge_ids:
                raise ValueError("knowledge profile must contain at least one knowledge_id")
            if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
                raise ValueError("knowledge profile knowledge_ids must be unique")
        return self


class KnowledgeProfileCopyRequest(ContractModel):
    profile_id: Identifier | None = None
    name: NonEmptyText | None = None


class KnowledgeProfileResolutionResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    profile_id: Identifier
    valid: bool
    overall_status: str | None = None
    plan_fingerprint: str | None = None
    requested_knowledge_ids: list[Identifier] = Field(default_factory=list)
    resolved_knowledge_ids: list[Identifier] = Field(default_factory=list)
    implicit_dependency_ids: list[Identifier] = Field(default_factory=list)
    required_sources: list[dict[str, JsonValue]] = Field(default_factory=list)
    planned_materializations: list[dict[str, JsonValue]] = Field(default_factory=list)
    knowledge_model_dependencies: list[dict[str, JsonValue]] = Field(default_factory=list)
    knowledge_nodes: list[dict[str, JsonValue]] = Field(default_factory=list)
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    raw: dict[str, JsonValue] = Field(default_factory=dict)


class KnowledgeProfileListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[KnowledgeProfileDefinition]
    page: PageMeta


class ScenarioDefinition(ContractModel):
    scenario_id: Identifier
    name: NonEmptyText
    knowledge_profile_id: Identifier
    source_mode: ScenarioSourceMode
    version: str | None = None
    description: str | None = None
    source_path: str = "builtin"
    parameters: list[ScenarioParameter] = Field(default_factory=list)
    assistant_profile_id: NonEmptyText | None = None


class ScenarioListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[ScenarioDefinition]
    page: PageMeta


class KnowledgeProductInfo(ContractModel):
    knowledge_id: Identifier
    title: NonEmptyText
    summary: str | None = None
    category: str | None = None
    supported_scopes: list[ExecutionScope] = Field(default_factory=list)
    profile_v2_selectable: bool = False
    runtime_status: str | None = None
    runtime_executable: bool = False
    required_knowledge_dependencies: list[Identifier] = Field(default_factory=list)
    recommended_knowledge_dependencies: list[Identifier] = Field(default_factory=list)
    materialization_id: str | None = None
    produced_capabilities: list[str] = Field(default_factory=list)
    required_sources: list[dict[str, JsonValue]] = Field(default_factory=list)
    optional_sources: list[dict[str, JsonValue]] = Field(default_factory=list)


class KnowledgeProductListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    catalog_fingerprint: str
    items: list[KnowledgeProductInfo]
    page: PageMeta


class JobKind(StrEnum):
    KNOWLEDGE_EXECUTION = "knowledge_execution"


class JobReusePolicy(StrEnum):
    REUSE_IF_UNCHANGED = "reuse_if_unchanged"
    FORCE_REBUILD = "force_rebuild"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class StageProgressMode(StrEnum):
    DETERMINATE = "determinate"
    INDETERMINATE = "indeterminate"


class JobStage(ContractModel):
    stage_id: Identifier
    name: NonEmptyText
    description: NonEmptyText
    progress_mode: StageProgressMode
    status: PipelineStageStatus = PipelineStageStatus.PENDING
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    artifact_count: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_progress_contract(self) -> "JobStage":
        if self.progress_mode is StageProgressMode.INDETERMINATE and self.progress_percent is not None:
            raise ValueError("indeterminate stage cannot expose progress_percent")
        return self


class KnowledgeRevisionInput(ContractModel):
    system_id: Identifier
    revision_id: Identifier


class JobTarget(ContractModel):
    repository_id: Identifier | None = None
    repository_ids: list[Identifier] = Field(default_factory=list)
    system_id: Identifier
    physical_model_path: str | None = None
    knowledge_revisions: list[KnowledgeRevisionInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_selection(self) -> "JobTarget":
        if len(set(self.repository_ids)) != len(self.repository_ids):
            raise ValueError("repository_ids must contain unique values")
        selected_sources = sum(
            (
                bool(self.repository_id),
                bool(self.repository_ids),
                bool(self.knowledge_revisions),
            )
        )
        if selected_sources > 1:
            raise ValueError(
                "repository_id, repository_ids and knowledge_revisions are mutually exclusive"
            )
        return self


class JobOutputOptions(ContractModel):
    output_path: str | None = None
    replace: bool = False


class JobCreateRequest(ContractModel):
    display_name: NonEmptyText | None = None
    kind: JobKind = JobKind.KNOWLEDGE_EXECUTION
    target: JobTarget
    scenario_id: Identifier
    knowledge_profile_id: Identifier | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    output: JobOutputOptions = Field(default_factory=JobOutputOptions)
    idempotency_key: str | None = Field(default=None, max_length=200)
    reuse_policy: JobReusePolicy = JobReusePolicy.REUSE_IF_UNCHANGED
    production_id: Identifier | None = None
    production_revision: int | None = Field(default=None, ge=1)
    source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    source_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_knowledge_execution(self) -> "JobCreateRequest":
        if self.kind is not JobKind.KNOWLEDGE_EXECUTION:
            raise ValueError("only knowledge_execution jobs are supported")
        if not self.target.system_id:
            raise ValueError("knowledge_execution requires system_id")
        if (
            not self.target.repository_id
            and not self.target.repository_ids
            and not self.target.knowledge_revisions
        ):
            raise ValueError(
                "knowledge_execution requires repository_id, repository_ids or knowledge_revisions"
            )
        secret_name = re.compile(
            r"(?:^|[_-])(?:access[_-]?token|token|password|secret|api[_-]?key|private[_-]?key)(?:$|[_-])",
            re.IGNORECASE,
        )
        forbidden = sorted(name for name in self.parameters if secret_name.search(name))
        if forbidden:
            raise ValueError(
                "secret values are not accepted in job parameters; use protected configuration: "
                + ", ".join(forbidden)
            )
        return self


class ProductionArtifactNode(ContractModel):
    node_id: str
    node_kind: str
    title: str
    status: str | None = None
    model_kind: str | None = None
    schema_version: str | None = None
    producer_id: str | None = None
    artifact_id: str | None = None
    fingerprint: str | None = None
    coverage: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProductionStructureResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    job_id: Identifier
    scenario_id: Identifier
    knowledge_profile_id: Identifier
    profile_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    execution_plan: dict[str, JsonValue] = Field(default_factory=dict)
    execution_result: dict[str, JsonValue] = Field(default_factory=dict)
    nodes: list[ProductionArtifactNode] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)


class JobProgress(ContractModel):
    current_stage: Identifier | None = None
    message: str | None = None



class JobFailure(ContractModel):
    code: Identifier
    message: NonEmptyText
    stage: Identifier | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)
    retryable: bool = False


class CommandPreview(ContractModel):
    executable: NonEmptyText
    arguments: list[str] = Field(default_factory=list)
    working_directory: str | None = None
    environment_names: list[str] = Field(default_factory=list)
    secrets_redacted: bool = True


class JobSummary(ContractModel):
    job_id: Identifier
    display_name: NonEmptyText | None = None
    kind: JobKind
    status: JobStatus
    scenario_id: Identifier
    knowledge_profile_id: Identifier
    production_id: Identifier | None = None
    production_revision: int | None = Field(default=None, ge=1)
    target: JobTarget
    progress: JobProgress
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None




class ProducerReuseDecision(ContractModel):
    node_id: Identifier
    producer_kind: Identifier
    producer_id: NonEmptyText
    producer_version: NonEmptyText
    source_id: str | None = None
    action: str = Field(pattern=r"^(built|reused)$")
    reuse_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    basis: NonEmptyText
    invalidation_reason: str | None = None
    artifact_reference: str | None = None
    elapsed_seconds: float | None = Field(default=None, ge=0)
    saved_seconds: float | None = Field(default=None, ge=0)
    diagnostics: list[str] = Field(default_factory=list)


class JobReuseInfo(ContractModel):
    policy: JobReusePolicy = JobReusePolicy.REUSE_IF_UNCHANGED
    producer_nodes: list[ProducerReuseDecision] = Field(default_factory=list)


class JobPublicationBundle(ContractModel):
    schema_version: NonEmptyText = "aisl_publication_bundle/v2"
    path: NonEmptyText
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    member_count: int = Field(ge=1)


class JobDetails(JobSummary):
    schema_version: str = "generic_api/v1"
    knowledge_ids: list[Identifier] = Field(default_factory=list)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    source_snapshots: list[SourceSnapshot] = Field(default_factory=list)
    source_snapshot_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output: JobOutputOptions
    command: CommandPreview | None = None
    exit_code: int | None = None
    failure: JobFailure | None = None
    artifact_count: int = Field(0, ge=0)
    event_cursor: int = Field(0, ge=0)
    stages: list[JobStage] = Field(default_factory=list)
    reuse: JobReuseInfo = Field(default_factory=JobReuseInfo)
    publication_bundle: JobPublicationBundle | None = None


class JobListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[JobSummary]
    page: PageMeta


class JobRetryRequest(ContractModel):
    from_stage: Identifier | None = None
    parameter_overrides: dict[str, JsonValue] = Field(default_factory=dict)


class JobActionResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    job: JobDetails


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class LogStream(StrEnum):
    SYSTEM = "system"
    STDOUT = "stdout"
    STDERR = "stderr"


class JobLogEntry(ContractModel):
    sequence: int = Field(ge=0)
    timestamp: datetime
    level: LogLevel
    stream: LogStream
    stage: Identifier | None = None
    message: str


class JobLogsResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    job_id: Identifier
    entries: list[JobLogEntry]
    next_cursor: int | None = Field(default=None, ge=0)
    complete: bool


class JobEventType(StrEnum):
    SNAPSHOT = "snapshot"
    STATUS = "status"
    PROGRESS = "progress"
    LOG = "log"
    ARTIFACT = "artifact"
    HEARTBEAT = "heartbeat"


class JobEvent(ContractModel):
    sequence: int = Field(ge=0)
    timestamp: datetime
    event_type: JobEventType
    job_id: Identifier
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ArtifactKind(StrEnum):
    KNOWLEDGE_PROFILE = "knowledge_profile"
    TYPED_INPUT_DESCRIPTOR = "typed_input_descriptor"
    INPUT_INVENTORY = "input_inventory"
    EXECUTION_PLAN = "execution_plan"
    EXECUTION_RESULT = "execution_result"
    PUBLICATION_BUNDLE = "publication_bundle"
    KNOWLEDGE_ARTIFACT = "knowledge_artifact"
    RUN_LOG = "run_log"
    MANIFEST = "manifest"
    EVIDENCE = "evidence"
    CONFIGURATION_SNAPSHOT = "configuration_snapshot"
    DIAGNOSTICS_BUNDLE = "diagnostics_bundle"
    OTHER = "other"


class ArtifactSummary(ContractModel):
    artifact_id: Identifier
    job_id: Identifier
    kind: ArtifactKind
    name: NonEmptyText
    media_type: NonEmptyText
    size_bytes: int = Field(ge=0)
    created_at: datetime
    relative_path: str | None = None
    content_available: bool
    downloadable: bool
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ArtifactListResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    items: list[ArtifactSummary]


class ArtifactContentResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    artifact: ArtifactSummary
    content: str
    truncated: bool = False
    next_offset: int | None = Field(default=None, ge=0)


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class DiagnosticCheck(ContractModel):
    check_id: Identifier
    category: Identifier
    status: DiagnosticStatus
    summary: NonEmptyText
    detail: str | None = None
    remediation: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RuntimeDiagnosticsResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    generated_at: datetime
    application_version: str
    overall_status: DiagnosticStatus
    checks: list[DiagnosticCheck]


class ReproducibleCommand(ContractModel):
    stage: Identifier | None = None
    command_line: NonEmptyText
    working_directory: str | None = None
    environment_names: list[str] = Field(default_factory=list)
    secrets_redacted: bool = True


class ReproducibleCommandsResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    job_id: Identifier
    commands: list[ReproducibleCommand]


class JobCommandPreviewResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    normalized_request: JobCreateRequest
    commands: list[ReproducibleCommand]
    placeholders: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class JobDifference(ContractModel):
    field: NonEmptyText
    left: JsonValue = None
    right: JsonValue = None
    changed: bool


class JobComparisonResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    left_job_id: Identifier
    right_job_id: Identifier
    differences: list[JobDifference]
    changed_count: int = Field(ge=0)


class DiagnosticsBundleRequest(ContractModel):
    max_log_entries: int = Field(100_000, ge=1, le=100_000)


class DiagnosticsBundleResponse(ContractModel):
    schema_version: str = "generic_api/v1"
    job_id: Identifier
    artifact: ArtifactSummary


