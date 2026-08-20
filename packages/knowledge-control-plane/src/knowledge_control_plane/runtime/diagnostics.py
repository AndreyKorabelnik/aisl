from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import sys
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_control_plane import __version__
from knowledge_control_plane.api.generic_v1.models import (
    ArtifactKind,
    ArtifactSummary,
    AvailabilityStatus,
    ConfigurationValidationRequest,
    DiagnosticCheck,
    DiagnosticStatus,
    DiagnosticsBundleRequest,
    DiagnosticsBundleResponse,
    JobComparisonResponse,
    JobDetails,
    JobDifference,
    JobStatus,
    ReproducibleCommand,
    ReproducibleCommandsResponse,
    RuntimeDiagnosticsResponse,
)

from .artifacts import ArtifactRegistry
from .configuration import ConfigurationService
from .errors import ResourceNotFound
from .settings import RuntimeSettings
from .knowledge_api_client import KnowledgeApiHttpClient
from .store import RuntimeStore, utc_now


_TERMINAL = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}


def _duration_seconds(job: JobDetails) -> float | None:
    if job.started_at is None:
        return None
    end = job.finished_at or utc_now()
    return max(0.0, (end - job.started_at).total_seconds())


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


class DiagnosticsService:
    """Operational diagnostics without exposing protected configuration values."""

    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        store: RuntimeStore,
        configuration: ConfigurationService,
        artifacts: ArtifactRegistry,
        knowledge_api: KnowledgeApiHttpClient,
    ) -> None:
        self.settings = settings
        self.store = store
        self.configuration = configuration
        self.artifacts = artifacts
        self.knowledge_api = knowledge_api

    def system(self) -> RuntimeDiagnosticsResponse:
        checks: list[DiagnosticCheck] = []
        validation = self.configuration.validate(ConfigurationValidationRequest())
        for tool in validation.tools:
            checks.append(
                DiagnosticCheck(
                    check_id=f"tool.{tool.tool}",
                    category="tools",
                    status=(
                        DiagnosticStatus.PASS
                        if tool.status is AvailabilityStatus.AVAILABLE
                        else DiagnosticStatus.FAIL
                    ),
                    summary=(
                        f"{tool.tool} available"
                        if tool.status is AvailabilityStatus.AVAILABLE
                        else f"{tool.tool} unavailable"
                    ),
                    detail=tool.version or tool.resolved_path or "configured executable is not resolvable",
                    remediation=(
                        None
                        if tool.status is AvailabilityStatus.AVAILABLE
                        else "Install the executable or update the protected tool configuration"
                    ),
                    metadata={
                        "resolved_path": tool.resolved_path,
                        "version": tool.version,
                    },
                )
            )
        for issue in validation.issues:
            status = {
                "error": DiagnosticStatus.FAIL,
                "warning": DiagnosticStatus.WARNING,
                "info": DiagnosticStatus.PASS,
            }[issue.severity.value]
            checks.append(
                DiagnosticCheck(
                    check_id=f"configuration.{issue.code}",
                    category="configuration",
                    status=status,
                    summary=issue.message,
                    detail=issue.field,
                    remediation=issue.remediation,
                )
            )

        database_check = self.store.quick_check()
        checks.append(
            DiagnosticCheck(
                check_id="runtime.sqlite",
                category="runtime",
                status=DiagnosticStatus.PASS if database_check == "ok" else DiagnosticStatus.FAIL,
                summary="SQLite runtime store is healthy" if database_check == "ok" else "SQLite runtime store failed integrity check",
                detail=database_check,
                remediation=None if database_check == "ok" else "Stop knowledge-control-plane and restore or recreate the runtime SQLite database",
                metadata={"database_path": str(self.settings.database_path)},
            )
        )

        log_path = self.settings.runtime_log_path
        checks.append(
            DiagnosticCheck(
                check_id="runtime.log_file",
                category="runtime",
                status=DiagnosticStatus.PASS if log_path.parent.is_dir() else DiagnosticStatus.FAIL,
                summary="Runtime log file is configured" if log_path.parent.is_dir() else "Runtime log directory is unavailable",
                detail=str(log_path),
                remediation=None if log_path.parent.is_dir() else "Create the runtime log directory or set KNOWLEDGE_CONTROL_PLANE_LOG_FILE",
                metadata={
                    "log_path": str(log_path),
                    "level": self.settings.runtime_log_level,
                    "max_bytes": self.settings.runtime_log_max_bytes,
                    "backup_count": self.settings.runtime_log_backup_count,
                },
            )
        )

        try:
            usage = shutil.disk_usage(self.settings.runtime_root)
            free_ratio = usage.free / usage.total if usage.total else 0.0
            disk_status = DiagnosticStatus.PASS if free_ratio >= 0.1 else DiagnosticStatus.WARNING
            checks.append(
                DiagnosticCheck(
                    check_id="runtime.disk_space",
                    category="runtime",
                    status=disk_status,
                    summary="Runtime filesystem has sufficient free space" if disk_status is DiagnosticStatus.PASS else "Runtime filesystem is low on free space",
                    detail=f"{usage.free} bytes free of {usage.total}",
                    remediation=None if disk_status is DiagnosticStatus.PASS else "Free disk space before starting another analysis",
                    metadata={"free_bytes": usage.free, "total_bytes": usage.total},
                )
            )
        except OSError as exc:
            checks.append(
                DiagnosticCheck(
                    check_id="runtime.disk_space",
                    category="runtime",
                    status=DiagnosticStatus.FAIL,
                    summary="Cannot inspect runtime filesystem",
                    detail=str(exc),
                )
            )

        try:
            knowledge_health = self.knowledge_api.health()
            knowledge_ok = knowledge_health.get("status") == "ok"
            checks.append(
                DiagnosticCheck(
                    check_id="service.knowledge_api",
                    category="services",
                    status=DiagnosticStatus.PASS if knowledge_ok else DiagnosticStatus.WARNING,
                    summary=(
                        "Knowledge API is available"
                        if knowledge_ok
                        else "Knowledge API reports degraded status"
                    ),
                    detail=self.settings.knowledge_api_base_url,
                    remediation=None if knowledge_ok else "Inspect Knowledge API health and runtime logs",
                    metadata={"health": knowledge_health},
                )
            )
        except Exception as exc:
            checks.append(
                DiagnosticCheck(
                    check_id="service.knowledge_api",
                    category="services",
                    status=DiagnosticStatus.FAIL,
                    summary="Knowledge API is unavailable",
                    detail=str(exc),
                    remediation=(
                        "Start knowledge-api and configure KNOWLEDGE_API_BASE_URL "
                        "before running a publishing pipeline"
                    ),
                    metadata={"base_url": self.settings.knowledge_api_base_url},
                )
            )

        git_path = shutil.which("git")
        checks.append(
            DiagnosticCheck(
                check_id="tool.git",
                category="tools",
                status=DiagnosticStatus.PASS if git_path else DiagnosticStatus.WARNING,
                summary="Git checkout is available" if git_path else "Git checkout is unavailable",
                detail=git_path,
                remediation=None if git_path else "Install git to analyze remote repositories",
            )
        )

        jobs = self.store.list_jobs()
        active = sum(job.status not in _TERMINAL for job in jobs)
        checks.append(
            DiagnosticCheck(
                check_id="runtime.jobs",
                category="runtime",
                status=DiagnosticStatus.PASS,
                summary=f"Runtime contains {len(jobs)} jobs; {active} active",
                metadata={
                    "total": len(jobs),
                    "active": active,
                    "by_status": dict(Counter(job.status.value for job in jobs)),
                },
            )
        )

        env_presence = {
            name: bool(os.getenv(name))
            for name in (
                "BITBUCKET_USERNAME",
                "BITBUCKET_TOKEN",
                "BITBUCKET_ACCESS_TOKEN",
            )
        }
        checks.append(
            DiagnosticCheck(
                check_id="security.protected_environment",
                category="security",
                status=DiagnosticStatus.PASS,
                summary="Protected environment inspected without exposing values",
                metadata=env_presence,
            )
        )

        overall = DiagnosticStatus.PASS
        if any(check.status is DiagnosticStatus.FAIL for check in checks):
            overall = DiagnosticStatus.FAIL
        elif any(check.status is DiagnosticStatus.WARNING for check in checks):
            overall = DiagnosticStatus.WARNING
        return RuntimeDiagnosticsResponse(
            generated_at=datetime.now(UTC),
            application_version=__version__,
            overall_status=overall,
            checks=checks,
        )

    def reproducible_commands(self, job_id: str) -> ReproducibleCommandsResponse:
        job = self._job(job_id)
        entries = self.store.list_logs(job_id, cursor=0, limit=100_000)
        commands: list[ReproducibleCommand] = []
        for entry in entries:
            prefix = "Executing: "
            if entry.message.startswith(prefix):
                commands.append(
                    ReproducibleCommand(
                        stage=entry.stage,
                        command_line=entry.message[len(prefix):],
                        working_directory=None,
                        environment_names=[],
                        secrets_redacted=True,
                    )
                )
        if not commands and job.command is not None:
            commands.append(
                ReproducibleCommand(
                    stage=job.progress.current_stage,
                    command_line=shlex.join([job.command.executable, *job.command.arguments]),
                    working_directory=job.command.working_directory,
                    environment_names=job.command.environment_names,
                    secrets_redacted=job.command.secrets_redacted,
                )
            )
        elif commands and job.command is not None:
            last = commands[-1]
            commands[-1] = last.model_copy(
                update={
                    "working_directory": job.command.working_directory,
                    "environment_names": job.command.environment_names,
                }
            )
        return ReproducibleCommandsResponse(job_id=job_id, commands=commands)

    def compare(self, left_job_id: str, right_job_id: str) -> JobComparisonResponse:
        left = self._job(left_job_id)
        right = self._job(right_job_id)
        left_artifacts = self.store.list_artifacts(left_job_id)
        right_artifacts = self.store.list_artifacts(right_job_id)
        differences: list[JobDifference] = []

        def add(field: str, left_value: Any, right_value: Any) -> None:
            differences.append(
                JobDifference(
                    field=field,
                    left=_json_value(left_value),
                    right=_json_value(right_value),
                    changed=left_value != right_value,
                )
            )

        add("kind", left.kind, right.kind)
        add("status", left.status, right.status)
        add("scenario_id", left.scenario_id, right.scenario_id)
        add("knowledge_profile_id", left.knowledge_profile_id, right.knowledge_profile_id)
        add("target", left.target.model_dump(mode="json"), right.target.model_dump(mode="json"))
        add("duration_seconds", _duration_seconds(left), _duration_seconds(right))
        add("exit_code", left.exit_code, right.exit_code)
        add("failure_code", left.failure.code if left.failure else None, right.failure.code if right.failure else None)
        add("artifact_count", len(left_artifacts), len(right_artifacts))
        add(
            "artifacts_by_kind",
            dict(Counter(item.kind.value for item in left_artifacts)),
            dict(Counter(item.kind.value for item in right_artifacts)),
        )
        add(
            "stages",
            {stage.stage_id: stage.status.value for stage in left.stages},
            {stage.stage_id: stage.status.value for stage in right.stages},
        )
        add("parameters", left.parameters, right.parameters)
        return JobComparisonResponse(
            left_job_id=left_job_id,
            right_job_id=right_job_id,
            differences=differences,
            changed_count=sum(item.changed for item in differences),
        )

    def create_bundle(
        self, job_id: str, request: DiagnosticsBundleRequest
    ) -> DiagnosticsBundleResponse:
        job = self._job(job_id)
        root = (self.settings.jobs_root / job_id / "diagnostics").resolve()
        jobs_root = self.settings.jobs_root.resolve()
        if root != jobs_root and jobs_root not in root.parents:
            raise ValueError("diagnostics path escaped jobs root")
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path = root / f"diagnostics-{job_id}-{timestamp}.zip"

        logs = self.store.list_logs(job_id, cursor=0, limit=request.max_log_entries)
        artifact_items = self.store.list_artifacts(job_id)
        commands = self.reproducible_commands(job_id)
        diagnostics = self.system()
        configuration = self.configuration.get()
        public_configuration = configuration.model_dump(mode="json")
        public_configuration["commands"] = {
            name: {"configured": bool(value), "executable": shlex.split(value)[0] if shlex.split(value) else None}
            for name, value in configuration.commands.model_dump().items()
        }
        metadata = {
            "schema_version": "knowledge_control_plane_diagnostics/v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "application_version": __version__,
            "python": sys.version,
            "platform": platform.platform(),
            "job_id": job_id,
            "artifact_content_included": False,
            "environment_values_included": False,
        }
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            self._write_json(archive, "metadata.json", metadata)
            self._write_json(archive, "job.json", job.model_dump(mode="json"))
            self._write_json(archive, "commands.json", commands.model_dump(mode="json"))
            self._write_json(archive, "runtime-diagnostics.json", diagnostics.model_dump(mode="json"))
            self._write_json(archive, "configuration.json", public_configuration)
            self._write_json(
                archive,
                "artifacts.json",
                [item.model_dump(mode="json") for item in artifact_items],
            )
            log_lines = "\n".join(item.model_dump_json() for item in logs)
            archive.writestr("logs.jsonl", log_lines + ("\n" if log_lines else ""))
            archive.writestr(
                "logs.txt",
                "\n".join(
                    f"{item.timestamp.isoformat()} [{item.level.value}] [{item.stream.value}]"
                    f"{f' [{item.stage}]' if item.stage else ''} {item.message}"
                    for item in logs
                )
                + ("\n" if logs else ""),
            )
            archive.writestr(
                "README.txt",
                "Knowledge Control Plane diagnostics bundle.\n"
                "This archive contains sanitized runtime metadata, command lines, logs, and artifact metadata.\n"
                "It does not contain source repositories, artifact payloads, TLS private keys, tokens, or environment values.\n",
            )
        summary = self.artifacts.register_file(
            job_id=job_id,
            path=path,
            relative_path=f"diagnostics/{path.name}",
            kind=ArtifactKind.DIAGNOSTICS_BUNDLE,
        )
        refreshed = self._job(job_id).model_copy(
            update={"artifact_count": len(self.store.list_artifacts(job_id))}
        )
        self.store.update_job(refreshed)
        return DiagnosticsBundleResponse(job_id=job_id, artifact=summary)

    def log_text(
        self,
        job_id: str,
        *,
        level: Any = None,
        stream: Any = None,
        stage: str | None = None,
        search: str | None = None,
    ) -> str:
        self._job(job_id)
        entries, _ = self.store.list_logs_filtered(
            job_id,
            cursor=0,
            limit=100_000,
            level=level,
            stream=stream,
            stage=stage,
            search=search,
        )
        return "\n".join(
            f"{item.timestamp.isoformat()} [{item.level.value}] [{item.stream.value}]"
            f"{f' [{item.stage}]' if item.stage else ''} {item.message}"
            for item in entries
        ) + ("\n" if entries else "")

    def _job(self, job_id: str) -> JobDetails:
        job = self.store.get_job(job_id)
        if job is None:
            raise ResourceNotFound("job", job_id)
        return job

    @staticmethod
    def _write_json(archive: zipfile.ZipFile, name: str, payload: Any) -> None:
        archive.writestr(
            name,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_value)
            + "\n",
        )
