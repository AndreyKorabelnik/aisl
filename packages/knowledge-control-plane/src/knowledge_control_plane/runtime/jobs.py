from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shlex
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    ArtifactKind,
    JobActionResponse,
    JobCommandPreviewResponse,
    JobCreateRequest,
    JobDetails,
    JobEventType,
    JobFailure,
    JobKind,
    JobListResponse,
    JobLogsResponse,
    JobProgress,
    JobRetryRequest,
    JobStatus,
    LogLevel,
    LogStream,
    PageMeta,
    PipelineStageStatus,
    ProducerReuseDecision,
    JobReuseInfo,
    JobPublicationBundle,
    ReproducibleCommand,
    ResourceDeletedResponse,
)

from .artifacts import ArtifactRegistry
from .commands import CommandBuilder, CommandSpec
from .errors import InvalidState, ResourceNotFound, RuntimeApiError
from .knowledge_api_client import KnowledgeApiHttpClient
from .publication_bundle import build_publication_bundle
from .observability import append_job_run_log
from .pipeline import PipelinePlan, PipelinePlanner
from .process import ProcessExecutor
from .repositories import RepositoryService
from .settings import RuntimeSettings
from .store import RuntimeStore, utc_now

TERMINAL_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobManagerState:
    started: bool
    queued: int
    running: tuple[str, ...]


class JobManager:
    """Durable executor for the canonical knowledge execution product route."""

    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        store: RuntimeStore,
        command_builder: CommandBuilder,
        executor: ProcessExecutor,
        artifacts: ArtifactRegistry,
        repositories: RepositoryService,
        pipeline_planner: PipelinePlanner,
        knowledge_api: KnowledgeApiHttpClient,
        **_unused,
    ) -> None:
        self.settings = settings
        self.store = store
        self.command_builder = command_builder
        self.executor = executor
        self.artifacts = artifacts
        self.repositories = repositories
        self.pipeline_planner = pipeline_planner
        self.knowledge_api = knowledge_api
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._running: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._started = False
        self._state_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._state_lock:
            if self._started:
                return
            self._started = True
            queued, interrupted = self.store.recover_incomplete_jobs()
            for job_id in interrupted:
                job = self._require_job(job_id)
                failed = job.model_copy(
                    update={
                        "status": JobStatus.FAILED,
                        "finished_at": utc_now(),
                        "failure": JobFailure(
                            code="backend_restarted",
                            message="knowledge execution was interrupted by backend restart",
                            stage=job.progress.current_stage,
                            retryable=True,
                        ),
                        "progress": JobProgress(
                            current_stage=job.progress.current_stage,
                            message="Interrupted by backend restart",
                        ),
                    }
                )
                self.store.update_job(failed)
                await self._emit_snapshot(failed)
            for job_id in queued:
                self._queue.put_nowait(job_id)
            self._workers = [
                asyncio.create_task(self._worker(index), name=f"knowledge-control-plane-worker-{index}")
                for index in range(self.settings.max_concurrent_jobs)
            ]

    async def stop(self) -> None:
        async with self._state_lock:
            if not self._started:
                return
            self._started = False
            running = list(self._running)
        for job_id in running:
            self._cancel_requested.add(job_id)
            await self.executor.cancel(job_id)
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def state(self) -> JobManagerState:
        return JobManagerState(
            started=self._started,
            queued=self._queue.qsize(),
            running=tuple(sorted(self._running)),
        )

    def preview(self, request: JobCreateRequest) -> JobCommandPreviewResponse:
        digest = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()[:12]
        job_id = f"preview-{digest}"
        plan = self.pipeline_planner.build(job_id=job_id, request=request, preview=True)
        pinned_ids = {item.source_id for item in request.source_snapshots if item.source_kind.value == "git"}
        repository_paths = tuple(
            self.repositories.pinned_execution_path(repository_id, job_id=job_id)
            if repository_id in pinned_ids
            else self.repositories.planned_execution_path(repository_id)
            for repository_id in plan.repository_ids
        )
        commands: list[ReproducibleCommand] = []

        snapshot_map = {item.source_id: item for item in request.source_snapshots}
        for repository_id in plan.repository_ids:
            snapshot = snapshot_map.get(repository_id)
            if snapshot is not None:
                commit_sha = str(snapshot.resolved_version.get("commit_sha") or "")
                checkouts = self.repositories.pinned_checkout_commands(
                    repository_id,
                    job_id=job_id,
                    commit_sha=commit_sha,
                    preview=True,
                )
            else:
                checkout = self.repositories.preview_checkout_command(
                    repository_id,
                    refresh=request.reuse_policy.value == "force_rebuild",
                )
                checkouts = [] if checkout is None else [checkout]
            for checkout in checkouts:
                commands.append(
                    ReproducibleCommand(
                        stage="checkout",
                        command_line=shlex.join(checkout.argv).replace(job_id, "<job-id>"),
                        working_directory=str(checkout.cwd).replace(job_id, "<job-id>"),
                        environment_names=sorted(checkout.environment),
                    )
                )
        commands.append(
            self._preview_command(
                self.command_builder.input_prepare(
                    plan=plan,
                    request=request,
                    repository_paths=repository_paths,
                    published_revision_snapshots=tuple(
                        plan.knowledge_input_root / f"published-revision-{index:03d}.json"
                        for index, _item in enumerate(request.target.knowledge_revisions, start=1)
                    ),
                    physical_model_path=self._planned_physical_model_path(plan, request),
                ),
                job_id,
            )
        )
        commands.append(self._preview_command(self.command_builder.execution_plan(plan=plan), job_id))
        commands.append(self._preview_command(self.command_builder.execute(plan=plan, request=request), job_id))
        warnings = [
            "Runner owns profile validation, dependency resolution, input normalization and Producer execution.",
            "Capabilities become available only after successful Runner execution and publication.",
        ]
        return JobCommandPreviewResponse(
            normalized_request=request,
            commands=commands,
            placeholders={
                "job_id": "assigned on create",
                "revision_id": "assigned by Knowledge API",
            },
            warnings=warnings,
        )

    @staticmethod
    def _preview_command(command: CommandSpec, job_id: str) -> ReproducibleCommand:
        preview = command.preview()
        return ReproducibleCommand(
            stage=command.stage,
            command_line=shlex.join([preview.executable, *preview.arguments]).replace(job_id, "<job-id>"),
            working_directory=preview.working_directory,
            environment_names=preview.environment_names,
            secrets_redacted=True,
        )

    async def create(self, request: JobCreateRequest) -> JobDetails:
        if request.idempotency_key:
            existing = self.store.get_job_by_idempotency_key(request.idempotency_key)
            if existing is not None:
                return existing
        # Validate all product requirements before persisting the job.
        plan = self.pipeline_planner.build(
            job_id=f"validation-{uuid.uuid4().hex[:12]}", request=request, preview=True
        )
        self._validate_source_snapshots(request, plan.repository_ids)
        scenario = self.pipeline_planner.scenarios.get(request.scenario_id)
        now = utc_now()
        job_id = f"job-{uuid.uuid4().hex}"
        details = JobDetails(
            job_id=job_id,
            display_name=request.display_name,
            kind=request.kind,
            status=JobStatus.QUEUED,
            scenario_id=request.scenario_id,
            knowledge_profile_id=plan.knowledge_profile_id,
            production_id=request.production_id,
            production_revision=request.production_revision,
            target=request.target,
            progress=JobProgress(current_stage=None, message="Queued"),
            created_at=now,
            knowledge_ids=list(plan.knowledge_ids),
            parameters=request.parameters,
            source_snapshots=list(request.source_snapshots),
            source_snapshot_fingerprint=request.source_snapshot_fingerprint,
            output=request.output,
            stages=self.pipeline_planner.stages(request),
            reuse={"policy": request.reuse_policy, "producer_nodes": []},
        )
        self.store.insert_job(
            details,
            request_json=request.model_dump_json(),
            idempotency_key=request.idempotency_key,
        )
        await self._append_log(job_id, LogLevel.INFO, LogStream.SYSTEM, "Knowledge execution job created", None)
        await self._emit_snapshot(details)
        self._queue.put_nowait(job_id)
        return details

    def get(self, job_id: str) -> JobDetails:
        return self._require_job(job_id)

    def list(
        self,
        *,
        offset: int,
        limit: int,
        status: JobStatus | None,
        kind: JobKind | None,
    ) -> JobListResponse:
        jobs = self.store.list_jobs()
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        if kind is not None:
            jobs = [job for job in jobs if job.kind is kind]
        summaries = [
            job.model_copy(update={}).model_dump(
                include={
                    "job_id", "display_name", "kind", "status", "scenario_id", "knowledge_profile_id", "production_id", "production_revision", "target",
                    "progress", "created_at", "started_at", "finished_at",
                }
            )
            for job in jobs
        ]
        from knowledge_control_plane.api.generic_v1.models import JobSummary

        items = [JobSummary.model_validate(item) for item in summaries]
        return JobListResponse(
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )

    def delete(self, job_id: str) -> ResourceDeletedResponse:
        job = self._require_job(job_id)
        if job.status not in TERMINAL_STATUSES:
            raise InvalidState("only terminal knowledge executions can be deleted")
        if not self.store.delete_job(job_id):
            raise ResourceNotFound("job", job_id)
        return ResourceDeletedResponse(id=job_id)

    async def cancel(self, job_id: str) -> JobActionResponse:
        job = self._require_job(job_id)
        if job.status in TERMINAL_STATUSES:
            return JobActionResponse(job=job)
        self._cancel_requested.add(job_id)
        await self.executor.cancel(job_id)
        return JobActionResponse(job=self._require_job(job_id))

    async def retry(self, job_id: str, request: JobRetryRequest) -> JobActionResponse:
        source = self._require_job(job_id)
        if source.status not in TERMINAL_STATUSES:
            raise InvalidState("only terminal knowledge executions can be retried")
        if request.from_stage:
            raise RuntimeApiError(
                400,
                "partial_retry_not_supported",
                "knowledge execution retry creates a new complete immutable run",
            )
        raw = self.store.get_job_request_json(job_id)
        if raw is None:
            raise ResourceNotFound("job request", job_id)
        original = JobCreateRequest.model_validate_json(raw)
        retried = original.model_copy(
            update={
                "parameters": {**original.parameters, **request.parameter_overrides},
                "idempotency_key": None,
            }
        )
        return JobActionResponse(job=await self.create(retried))

    def logs(
        self,
        *,
        job_id: str,
        cursor: int,
        limit: int,
        level: LogLevel | None = None,
        stream: LogStream | None = None,
        stage: str | None = None,
        search: str | None = None,
    ) -> JobLogsResponse:
        self._require_job(job_id)
        entries, has_more = self.store.list_logs_filtered(
            job_id,
            cursor=cursor,
            limit=limit,
            level=level,
            stream=stream,
            stage=stage,
            search=search,
        )
        next_cursor = entries[-1].sequence + 1 if entries and has_more else None
        return JobLogsResponse(
            job_id=job_id,
            entries=entries,
            next_cursor=next_cursor,
            complete=self._require_job(job_id).status in TERMINAL_STATUSES and not has_more,
        )

    async def _worker(self, _index: int) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                self._running.add(job_id)
                await self._run(job_id)
            except asyncio.CancelledError:
                raise
            finally:
                self._running.discard(job_id)
                self._queue.task_done()

    async def _run(self, job_id: str) -> None:
        job = self._require_job(job_id)
        raw = self.store.get_job_request_json(job_id)
        if raw is None:
            raise ResourceNotFound("job request", job_id)
        request = JobCreateRequest.model_validate_json(raw)
        plan = None
        try:
            plan = self.pipeline_planner.build(job_id=job_id, request=request, created_at=job.created_at)
            uses_source_repositories = bool(plan.repository_ids)
            first_stage = "checkout" if uses_source_repositories else "prepare_inputs"
            first_message = (
                "Preparing source repositories"
                if uses_source_repositories
                else "Preparing existing knowledge inputs"
            )
            job = job.model_copy(
                update={
                    "status": JobStatus.PREPARING,
                    "started_at": utc_now(),
                    "progress": JobProgress(current_stage=first_stage, message=first_message),
                }
            )
            self.store.update_job(job)
            await self._emit_snapshot(job)
            repository_paths: tuple[Path, ...] = ()
            if uses_source_repositories:
                await self._run_checkouts(
                    job_id,
                    plan.repository_ids,
                    request=request,
                    refresh=request.reuse_policy.value == "force_rebuild",
                )
                pinned_ids = {item.source_id for item in request.source_snapshots if item.source_kind.value == "git"}
                repository_paths = tuple(
                    self.repositories.pinned_execution_path(repository_id, job_id=job_id)
                    if repository_id in pinned_ids
                    else self.repositories.execution_path(repository_id)
                    for repository_id in plan.repository_ids
                )
            plan.root.mkdir(parents=True, exist_ok=True)
            job = self._require_job(job_id)
            run_info_path = self._write_run_info(plan, job)
            self.artifacts.register_file(
                job_id=job_id,
                path=run_info_path,
                relative_path="RUN_INFO.json",
                kind=ArtifactKind.MANIFEST,
            )
            physical_model_path = self._prepare_physical_model_source(plan, request)

            await self._stage_running(job_id, "prepare_inputs", "Preparing Knowledge Profile and typed inputs")
            profile_path = self.pipeline_planner.materialize_profile(plan, request)
            self.artifacts.register_file(
                job_id=job_id,
                path=profile_path,
                relative_path="contracts/knowledge-profile.json",
                kind=ArtifactKind.KNOWLEDGE_PROFILE,
            )
            revision_snapshots = self._snapshot_published_knowledge_inputs(
                job_id=job_id,
                plan=plan,
                request=request,
            )
            await self._execute(
                job_id,
                self.command_builder.input_prepare(
                    plan=plan,
                    request=request,
                    repository_paths=repository_paths,
                    published_revision_snapshots=revision_snapshots,
                    physical_model_path=physical_model_path,
                ),
            )
            preparation_reuse = plan.contracts_root / "producer-reuse-preparation.json"
            if preparation_reuse.is_file():
                await self._record_producer_reuse_decisions(
                    job_id,
                    json.loads(preparation_reuse.read_text(encoding="utf-8")).get("decisions") or [],
                    stage="prepare_inputs",
                )
            self.artifacts.register_file(
                job_id=job_id,
                path=plan.input_inventory_path,
                relative_path="contracts/knowledge-input-inventory.json",
                kind=ArtifactKind.INPUT_INVENTORY,
            )
            await self._stage_succeeded(job_id, "prepare_inputs", "Runner normalized execution inputs")

            await self._stage_running(job_id, "runner_plan", "Runner is compiling the execution DAG")
            await self._execute(job_id, self.command_builder.execution_plan(plan=plan))
            execution_plan = json.loads(plan.execution_plan_path.read_text(encoding="utf-8"))
            if str((execution_plan.get("status") or {}).get("overall") or "") != "ready":
                raise RuntimeApiError(
                    409,
                    "knowledge_execution_plan_blocked",
                    "knowledge execution plan is blocked by missing inputs or contracts",
                    details={"diagnostics": execution_plan.get("diagnostics") or []},
                )
            self.artifacts.register_file(
                job_id=job_id,
                path=plan.input_inventory_path,
                relative_path="contracts/knowledge-input-inventory.json",
                kind=ArtifactKind.INPUT_INVENTORY,
            )
            self.artifacts.register_file(
                job_id=job_id,
                path=plan.execution_plan_path,
                relative_path="contracts/knowledge-execution-plan.json",
                kind=ArtifactKind.EXECUTION_PLAN,
            )
            await self._stage_succeeded(job_id, "runner_plan", "Runner execution DAG is ready")

            await self._stage_running(job_id, "runner_execution", "Runner is executing the canonical Producer plan")
            await self._execute(
                job_id,
                self.command_builder.execute(plan=plan, request=request),
                scan=False,
            )
            if not plan.execution_result_path.is_file():
                raise RuntimeError("knowledge-execute did not produce knowledge_execution_result.json")
            result = json.loads(plan.execution_result_path.read_text(encoding="utf-8"))
            if result.get("status") != "completed":
                raise RuntimeError("knowledge execution result is not completed")
            await self._record_producer_reuse_decisions(
                job_id,
                ((result.get("producer_reuse") or {}).get("decisions") or []),
                stage="runner_execution",
            )
            await self._log_materialization_summaries(job_id, plan.execution_root)
            scan_started = time.monotonic()
            await self._append_log(
                job_id,
                LogLevel.INFO,
                LogStream.SYSTEM,
                "Runner process completed; scanning output artifacts",
                "runner_execution",
            )
            registered = await asyncio.to_thread(
                self.artifacts.scan,
                job_id=job_id,
                output_path=plan.execution_root,
                relative_prefix="knowledge-execution",
            )
            await self._append_log(
                job_id,
                LogLevel.SUCCESS,
                LogStream.SYSTEM,
                f"Runner artifact scan completed; registered={len(registered)}; duration={self._format_duration(time.monotonic() - scan_started)}",
                "runner_execution",
            )
            self.artifacts.register_file(
                job_id=job_id,
                path=plan.execution_result_path,
                relative_path="knowledge-execution/knowledge_execution_result.json",
                kind=ArtifactKind.EXECUTION_RESULT,
            )
            await self._stage_succeeded(
                job_id,
                "runner_execution",
                f"Runner completed; knowledge artifacts produced: {len(result.get('knowledge_artifacts') or [])}",
            )

            await self._stage_running(job_id, "bundle", "Building self-contained AISL publication bundle")
            bundle_result = await asyncio.to_thread(
                build_publication_bundle,
                job_id=job_id,
                system_id=plan.system_id,
                display_name=request.display_name or plan.system_id,
                execution_root=plan.execution_root,
                execution_result_path=plan.execution_result_path,
                output_path=plan.root / "bundle" / f"{job_id}.aisl.zip",
                labels=["automated-analysis"],
                metadata=self._bundle_metadata(request, plan),
            )
            self.artifacts.register_file(
                job_id=job_id,
                path=bundle_result.path,
                relative_path=f"bundle/{bundle_result.path.name}",
                kind=ArtifactKind.PUBLICATION_BUNDLE,
            )
            final_bundle = JobPublicationBundle(
                schema_version=bundle_result.schema_version,
                path=str(bundle_result.path),
                sha256=bundle_result.sha256,
                member_count=bundle_result.member_count,
            )
            job = self._require_job(job_id).model_copy(update={"publication_bundle": final_bundle})
            self.store.update_job(job)
            await self._stage_succeeded(job_id, "bundle", f"AISL publication bundle ready: {bundle_result.path.name}")

            completed = self._require_job(job_id).model_copy(
                update={
                    "status": JobStatus.SUCCEEDED,
                    "finished_at": utc_now(),
                    "progress": JobProgress(current_stage=None, message="Knowledge production completed; bundle ready for AISL Server import"),
                    "publication_bundle": final_bundle,
                    "artifact_count": len(self.store.list_artifacts(job_id)),
                    "exit_code": 0,
                }
            )
            self.store.update_job(completed)
            self._write_run_info(plan, completed)
            total_duration = (completed.finished_at - completed.started_at).total_seconds() if completed.started_at and completed.finished_at else None
            suffix = f"; duration={self._format_duration(total_duration)}" if total_duration is not None else ""
            await self._append_log(job_id, LogLevel.SUCCESS, LogStream.SYSTEM, f"Knowledge execution completed{suffix}", None)
            await self._emit_snapshot(completed)
        except asyncio.CancelledError:
            await self._mark_cancelled(job_id)
            if plan is not None and plan.root.is_dir():
                self._write_run_info(plan, self._require_job(job_id))
            raise
        except Exception as exc:
            await self._mark_failed(job_id, exc)
            if plan is not None and plan.root.is_dir():
                self._write_run_info(plan, self._require_job(job_id))

    def _write_run_info(self, plan, job: JobDetails) -> Path:
        return self.pipeline_planner.output_safety.write_run_info(
            plan.root,
            job_id=job.job_id,
            system_id=plan.system_id,
            scenario_id=plan.scenario_id,
            display_name=job.display_name,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            status=job.status.value,
        )

    def _snapshot_published_knowledge_inputs(
        self,
        *,
        job_id: str,
        plan: PipelinePlan,
        request: JobCreateRequest,
    ) -> tuple[Path, ...]:
        """Persist immutable revision responses; Runner owns artifact normalization/selection."""
        snapshots: list[Path] = []
        for index, revision_input in enumerate(request.target.knowledge_revisions, start=1):
            revision = self.knowledge_api.get_revision(
                revision_input.system_id,
                revision_input.revision_id,
            )
            target = plan.knowledge_input_root / f"published-revision-{index:03d}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(revision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.artifacts.register_file(
                job_id=job_id,
                path=target,
                relative_path=f"inputs/published-revisions/{target.name}",
                kind=ArtifactKind.CONFIGURATION_SNAPSHOT,
            )
            snapshots.append(target)
        return tuple(snapshots)

    @staticmethod
    def _aggregate_source_fingerprint(snapshots) -> str:
        payload = [
            {"source_id": item.source_id, "snapshot_fingerprint": item.snapshot_fingerprint}
            for item in sorted(snapshots, key=lambda value: value.source_id)
        ]
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _validate_source_snapshots(self, request: JobCreateRequest, repository_ids: tuple[str, ...]) -> None:
        snapshots = list(request.source_snapshots)
        if not snapshots:
            if request.source_snapshot_fingerprint is not None:
                raise RuntimeApiError(422, "source_snapshot_invalid", "source snapshot fingerprint requires source snapshots")
            return
        source_ids = [item.source_id for item in snapshots]
        if len(source_ids) != len(set(source_ids)):
            raise RuntimeApiError(422, "source_snapshot_invalid", "source snapshots must have unique source_id values")
        unavailable = [item.source_id for item in snapshots if item.availability.value != "available"]
        if unavailable:
            raise RuntimeApiError(
                422,
                "source_snapshot_unavailable",
                "knowledge execution cannot start from unavailable source snapshots",
                details={"source_ids": unavailable},
            )
        git_snapshots = {item.source_id: item for item in snapshots if item.source_kind.value == "git"}
        if set(git_snapshots) != set(repository_ids):
            raise RuntimeApiError(
                422,
                "source_snapshot_repository_mismatch",
                "pinned Git snapshots must match the selected repositories exactly",
                details={"expected": sorted(repository_ids), "actual": sorted(git_snapshots)},
            )
        for repository_id, snapshot in git_snapshots.items():
            commit_sha = str(snapshot.resolved_version.get("commit_sha") or "")
            if snapshot.resolved_version.get("kind") != "git_commit" or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha):
                raise RuntimeApiError(
                    422,
                    "source_snapshot_invalid",
                    "Git source snapshot must resolve to an immutable commit SHA",
                    details={"repository_id": repository_id},
                )
        file_snapshots = [item for item in snapshots if item.source_kind.value == "file"]
        if request.target.physical_model_path:
            if len(file_snapshots) != 1:
                raise RuntimeApiError(
                    422,
                    "source_snapshot_physical_model_mismatch",
                    "pinned physical-model execution requires exactly one file snapshot",
                )
            file_snapshot = file_snapshots[0]
            sha256 = str(file_snapshot.resolved_version.get("sha256") or "")
            if file_snapshot.resolved_version.get("kind") != "sha256" or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
                raise RuntimeApiError(422, "source_snapshot_invalid", "file source snapshot must contain SHA-256")
        elif file_snapshots:
            raise RuntimeApiError(422, "source_snapshot_physical_model_mismatch", "file snapshot supplied without physical_model_path")
        expected = self._aggregate_source_fingerprint(snapshots)
        if request.source_snapshot_fingerprint != expected:
            raise RuntimeApiError(
                422,
                "source_snapshot_fingerprint_mismatch",
                "aggregate source snapshot fingerprint does not match the supplied snapshots",
                details={"expected": expected, "actual": request.source_snapshot_fingerprint},
            )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _planned_physical_model_path(self, plan: PipelinePlan, request: JobCreateRequest) -> Path | None:
        file_snapshots = [item for item in request.source_snapshots if item.source_kind.value == "file"]
        if file_snapshots:
            return plan.physical_input_root / Path(file_snapshots[0].location).name
        if request.target.physical_model_path:
            return Path(request.target.physical_model_path).expanduser().resolve()
        return None

    def _prepare_physical_model_source(self, plan: PipelinePlan, request: JobCreateRequest) -> Path | None:
        file_snapshots = [item for item in request.source_snapshots if item.source_kind.value == "file"]
        if not file_snapshots:
            return Path(request.target.physical_model_path).expanduser().resolve() if request.target.physical_model_path else None
        snapshot = file_snapshots[0]
        source = Path(snapshot.location).expanduser().resolve()
        expected_sha = str(snapshot.resolved_version.get("sha256") or "").lower()
        if not source.is_file():
            raise RuntimeApiError(409, "source_snapshot_unavailable", f"pinned file source is unavailable: {source}")
        observed_before = self._sha256_file(source)
        if observed_before != expected_sha:
            raise RuntimeApiError(
                409,
                "source_snapshot_mismatch",
                "physical-model source changed after freshness resolution",
                details={"expected": expected_sha, "actual": observed_before, "path": str(source)},
            )
        plan.physical_input_root.mkdir(parents=True, exist_ok=True)
        target = plan.physical_input_root / source.name
        shutil.copy2(source, target)
        observed_copy = self._sha256_file(target)
        if observed_copy != expected_sha:
            target.unlink(missing_ok=True)
            raise RuntimeApiError(
                409,
                "source_snapshot_mismatch",
                "job-local physical-model snapshot does not match resolved SHA-256",
                details={"expected": expected_sha, "actual": observed_copy},
            )
        return target

    @staticmethod
    def _bundle_metadata(request: JobCreateRequest, plan: PipelinePlan) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "knowledge_profile_id": plan.knowledge_profile_id,
            "scenario_id": plan.scenario_id,
        }
        if plan.assistant_profile_id:
            # Scenario configuration still uses the historical field name, but the
            # bundle boundary exposes neutral consumer terminology. No Assistant
            # runtime is activated by this metadata.
            metadata["integration_profile_id"] = plan.assistant_profile_id
        if request.production_id is not None:
            metadata["production_id"] = request.production_id
            metadata["production_revision"] = request.production_revision
        if request.source_snapshots:
            metadata["source_snapshots"] = [item.model_dump(mode="json") for item in request.source_snapshots]
            metadata["source_snapshot_fingerprint"] = request.source_snapshot_fingerprint
        return metadata

    async def _run_checkouts(
        self,
        job_id: str,
        repository_ids: tuple[str, ...],
        *,
        request: JobCreateRequest,
        refresh: bool,
    ) -> None:
        if not repository_ids:
            raise RuntimeError("checkout requires at least one repository_id")
        await self._stage_running(
            job_id,
            "checkout",
            f"Preparing {len(repository_ids)} source repository revision(s)",
        )
        snapshot_map = {item.source_id: item for item in request.source_snapshots}
        for repository_id in repository_ids:
            snapshot = snapshot_map.get(repository_id)
            if snapshot is not None:
                commit_sha = str(snapshot.resolved_version.get("commit_sha") or "")
                commands = self.repositories.pinned_checkout_commands(
                    repository_id,
                    job_id=job_id,
                    commit_sha=commit_sha,
                )
                try:
                    for command in commands:
                        wrapped = CommandSpec(
                            stage="checkout",
                            argv=command.argv,
                            cwd=command.cwd,
                            environment=command.environment,
                            output_path=command.target,
                        )
                        result = await self._execute(job_id, wrapped, scan=False)
                        if result.exit_code != 0:
                            raise RuntimeError(f"repository pinned checkout failed with exit code {result.exit_code}")
                    self.repositories.finalize_pinned_checkout(
                        repository_id,
                        job_id=job_id,
                        expected_commit_sha=commit_sha,
                    )
                except Exception:
                    self.repositories.cleanup_failed_pinned_checkout(repository_id, job_id=job_id)
                    raise
                await self._append_log(
                    job_id,
                    LogLevel.INFO,
                    LogStream.SYSTEM,
                    f"Repository pinned to {commit_sha}: {repository_id}",
                    "checkout",
                )
                continue

            command = self.repositories.checkout_command(repository_id, refresh=refresh)
            if command is None:
                self.repositories.execution_path(repository_id)
                await self._append_log(
                    job_id,
                    LogLevel.INFO,
                    LogStream.SYSTEM,
                    f"Repository is ready: {repository_id}",
                    "checkout",
                )
                continue
            wrapped = CommandSpec(
                stage="checkout",
                argv=command.argv,
                cwd=command.cwd,
                environment=command.environment,
                output_path=command.target,
            )
            try:
                result = await self._execute(job_id, wrapped, scan=False)
            except Exception:
                if command.action == "clone":
                    self.repositories.cleanup_failed_checkout(repository_id, command.target)
                raise
            if result.exit_code != 0:
                if command.action == "clone":
                    self.repositories.cleanup_failed_checkout(repository_id, command.target)
                raise RuntimeError(f"repository checkout failed with exit code {result.exit_code}")
            self.repositories.finalize_checkout(repository_id, command.target)
            await self._append_log(
                job_id,
                LogLevel.INFO,
                LogStream.SYSTEM,
                f"Repository checkout completed: {repository_id}",
                "checkout",
            )
        await self._stage_succeeded(
            job_id,
            "checkout",
            f"Source repositories ready: {len(repository_ids)}",
        )

    async def _record_producer_reuse_decisions(
        self,
        job_id: str,
        raw_decisions: list[dict[str, Any]],
        *,
        stage: str,
    ) -> None:
        if not raw_decisions:
            return
        decisions = [ProducerReuseDecision.model_validate(item) for item in raw_decisions]
        current = self._require_job(job_id)
        merged = {item.node_id: item for item in current.reuse.producer_nodes}
        for decision in decisions:
            merged[decision.node_id] = decision
        reuse = JobReuseInfo(policy=current.reuse.policy, producer_nodes=list(merged.values()))
        self.store.update_job(current.model_copy(update={"reuse": reuse}))
        for decision in decisions:
            if decision.action == "reused":
                message = (
                    f"REUSE {decision.node_id} key={decision.reuse_key[:16]} "
                    f"basis={decision.basis}"
                )
                level = LogLevel.SUCCESS
            else:
                message = (
                    f"BUILD {decision.node_id} reason={decision.invalidation_reason or 'canonical_execution'} "
                    f"key={decision.reuse_key[:16]}"
                )
                level = LogLevel.INFO
            await self._append_log(job_id, level, LogStream.SYSTEM, message, stage)

    async def _execute(self, job_id: str, command: CommandSpec, *, scan: bool = True):
        job = self._require_job(job_id).model_copy(update={"command": command.preview()})
        self.store.update_job(job)
        timeout = int(job.parameters.get("process_timeout_seconds", 3600))
        result = await self.executor.execute(
            job_id=job_id,
            command=command,
            timeout_seconds=timeout,
            on_log=lambda level, stream, message, stage: self._append_log(
                job_id, level, stream, message, stage
            ),
        )
        if result.timed_out:
            raise RuntimeError(f"stage timed out: {command.stage}")
        if result.cancelled or job_id in self._cancel_requested:
            raise asyncio.CancelledError()
        if result.exit_code != 0:
            raise RuntimeError(f"stage {command.stage} failed with exit code {result.exit_code}")
        if scan:
            registered = self.artifacts.scan(
                job_id=job_id,
                output_path=command.output_path,
                relative_prefix=command.stage,
            )
            if registered:
                current = self._require_job(job_id)
                self.store.update_job(
                    current.model_copy(update={"artifact_count": len(self.store.list_artifacts(job_id))})
                )
        return result

    @staticmethod
    def _find_schema_file(root: Path, schema_version: str) -> Path | None:
        for path in sorted(root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("schema_version") == schema_version:
                return path.resolve()
        return None

    async def _stage_running(self, job_id: str, stage_id: str, message: str) -> None:
        job = self._require_job(job_id)
        stages = []
        for stage in job.stages:
            if stage.stage_id == stage_id:
                stage = stage.model_copy(
                    update={
                        "status": PipelineStageStatus.RUNNING,
                        "started_at": stage.started_at or utc_now(),
                        "message": message,
                    }
                )
            stages.append(stage)
        updated = job.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "progress": JobProgress(current_stage=stage_id, message=message),
                "stages": stages,
            }
        )
        self.store.update_job(updated)
        await self._append_log(job_id, LogLevel.INFO, LogStream.SYSTEM, message, stage_id)
        await self._emit_snapshot(updated)

    async def _stage_succeeded(self, job_id: str, stage_id: str, message: str) -> None:
        job = self._require_job(job_id)
        stages = []
        finished_at = utc_now()
        duration_seconds: float | None = None
        for stage in job.stages:
            if stage.stage_id == stage_id:
                if stage.started_at is not None:
                    duration_seconds = max(0.0, (finished_at - stage.started_at).total_seconds())
                stage = stage.model_copy(
                    update={
                        "status": PipelineStageStatus.SUCCEEDED,
                        "finished_at": finished_at,
                        "message": message,
                        "artifact_count": len(self.store.list_artifacts(job_id)),
                    }
                )
            stages.append(stage)
        updated = job.model_copy(update={"stages": stages})
        self.store.update_job(updated)
        suffix = f"; duration={self._format_duration(duration_seconds)}" if duration_seconds is not None else ""
        await self._append_log(job_id, LogLevel.SUCCESS, LogStream.SYSTEM, f"{message}{suffix}", stage_id)
        await self._emit_snapshot(updated)

    async def _mark_failed(self, job_id: str, exc: Exception) -> None:
        job = self._require_job(job_id)
        stage_id = job.progress.current_stage
        stages = []
        for stage in job.stages:
            if stage.stage_id == stage_id and stage.status is PipelineStageStatus.RUNNING:
                stage = stage.model_copy(
                    update={
                        "status": PipelineStageStatus.FAILED,
                        "finished_at": utc_now(),
                        "message": str(exc),
                    }
                )
            stages.append(stage)
        failure_message = str(exc) or type(exc).__name__
        failed_stage = next((item for item in stages if item.stage_id == stage_id), None) if stage_id else None
        if failed_stage is not None and failed_stage.started_at is not None and failed_stage.finished_at is not None:
            elapsed = max(0.0, (failed_stage.finished_at - failed_stage.started_at).total_seconds())
            failure_message = f"{failure_message}; duration={self._format_duration(elapsed)}"
        failure = JobFailure(
            code="knowledge_execution_failed",
            message=failure_message,
            stage=stage_id,
            details={"exception_type": type(exc).__name__},
            retryable=True,
        )
        failed = job.model_copy(
            update={
                "status": JobStatus.FAILED,
                "finished_at": utc_now(),
                "failure": failure,
                "progress": JobProgress(current_stage=stage_id, message=failure.message),
                "stages": stages,
                "artifact_count": len(self.store.list_artifacts(job_id)),
                "exit_code": 1,
            }
        )
        self.store.update_job(failed)
        await self._append_log(job_id, LogLevel.ERROR, LogStream.SYSTEM, failure.message, stage_id)
        await self._emit_snapshot(failed)

    async def _mark_cancelled(self, job_id: str) -> None:
        job = self._require_job(job_id)
        stages = [
            stage.model_copy(
                update={
                    "status": PipelineStageStatus.CANCELLED,
                    "finished_at": utc_now(),
                    "message": "Cancelled",
                }
            )
            if stage.status is PipelineStageStatus.RUNNING
            else stage
            for stage in job.stages
        ]
        cancelled = job.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "finished_at": utc_now(),
                "progress": JobProgress(current_stage=job.progress.current_stage, message="Cancelled"),
                "stages": stages,
            }
        )
        self.store.update_job(cancelled)
        await self._emit_snapshot(cancelled)

    async def _append_log(
        self,
        job_id: str,
        level: LogLevel,
        stream: LogStream,
        message: str,
        stage: str | None,
    ):
        entry = self.store.append_log(
            job_id,
            level=level,
            stream=stream,
            message=message,
            stage=stage,
        )
        try:
            append_job_run_log(self.settings, job_id, entry)
        except OSError as exc:
            _LOGGER.warning("Unable to mirror canonical job log to %s: %s", self.settings.job_run_log_path(job_id), exc)
        event = self.store.append_event(
            job_id,
            event_type=JobEventType.LOG,
            payload=entry.model_dump(mode="json"),
        )
        current = self.store.get_job(job_id)
        if current is not None:
            self.store.update_job(current.model_copy(update={"event_cursor": event.sequence}))
        return entry

    async def heartbeat(self, job_id: str) -> None:
        job = self._require_job(job_id)
        if job.status in TERMINAL_STATUSES:
            return
        now = utc_now()
        stage_id = job.progress.current_stage
        stage_started = None
        if stage_id:
            stage_started = next((item.started_at for item in job.stages if item.stage_id == stage_id), None)
        parts = ["Still running"]
        if stage_started is not None:
            parts.append(f"stage_elapsed={self._format_duration(max(0.0, (now - stage_started).total_seconds()))}")
        if job.started_at is not None:
            parts.append(f"job_elapsed={self._format_duration(max(0.0, (now - job.started_at).total_seconds()))}")
        await self._append_log(job_id, LogLevel.INFO, LogStream.SYSTEM, "; ".join(parts), stage_id)

    @staticmethod
    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "unknown"
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, remaining = divmod(int(seconds), 60)
        if minutes < 60:
            return f"{minutes}m {remaining:02d}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m {remaining:02d}s"

    async def _log_materialization_summaries(self, job_id: str, execution_root: Path) -> None:
        for receipt in sorted(execution_root.rglob("materialization-result.json")):
            try:
                payload = json.loads(receipt.read_text(encoding="utf-8"))
            except Exception:
                continue
            materialization_id = str(payload.get("materialization_id") or receipt.parent.name)
            counts = ((payload.get("output") or {}).get("counts") or {})
            if not isinstance(counts, dict) or not counts:
                continue
            items = []
            for key, value in sorted(counts.items()):
                if isinstance(value, (int, float)):
                    items.append(f"{key}={value}")
            if not items:
                continue
            await self._append_log(
                job_id,
                LogLevel.INFO,
                LogStream.SYSTEM,
                f"Materialization {materialization_id} counts: {', '.join(items)}",
                "runner_execution",
            )

    async def _emit_snapshot(self, job: JobDetails) -> None:
        event = self.store.append_event(
            job.job_id,
            event_type=JobEventType.SNAPSHOT,
            payload=job.model_dump(mode="json"),
        )
        if job.event_cursor != event.sequence:
            job = job.model_copy(update={"event_cursor": event.sequence})
            self.store.update_job(job)

    def _require_job(self, job_id: str) -> JobDetails:
        job = self.store.get_job(job_id)
        if job is None:
            raise ResourceNotFound("job", job_id)
        return job
