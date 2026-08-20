from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import ExecutionScope, ScenarioSourceMode

from .context import RuntimeContext
from .errors import RuntimeApiError
from .knowledge_contracts import discover_knowledge_contract_paths, serialize_knowledge_profile


@dataclass(frozen=True, slots=True)
class RepositoryBatchScenarioOptions:
    scenario_id: str
    bitbucket_project_url: str
    output_path: str | None = None
    replace: bool = False
    force_rebuild: bool = False
    repository_limit: int | None = None
    auth_mode: str = "auto"
    ca_bundle: str | None = None
    insecure_skip_tls_verify: bool = False
    timeout_seconds: float = 60.0
    clone_retries: int = 2
    clone_timeout_seconds: float = 300.0
    duckdb_memory_limit: str = "1GB"
    duckdb_threads: int = 1


def _default_output_path(context: RuntimeContext, *, scenario_id: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return (
        context.settings.default_analysis_output_root
        / "repository-batches"
        / f"{scenario_id}-{stamp}"
    ).resolve()


def run_repository_batch_scenario(
    context: RuntimeContext,
    options: RepositoryBatchScenarioOptions,
) -> dict[str, Any]:
    """Run one repository-scoped Analysis Scenario independently for a Bitbucket project.

    Knowledge Control Plane owns scenario/profile selection and pinned contract discovery.
    Static Analysis Runner remains the only owner of repository batch acquisition/execution.
    The Control Plane does not clone repositories and does not create a multi-repository
    analysis scope.
    """
    scenario = context.scenarios.get(options.scenario_id)
    if scenario.source_mode is not ScenarioSourceMode.REPOSITORY:
        raise RuntimeApiError(
            422,
            "repository_batch_scenario_scope_mismatch",
            "--bitbucket-project-url requires a repository-scoped Analysis Scenario",
            details={
                "scenario_id": scenario.scenario_id,
                "source_mode": scenario.source_mode.value,
            },
        )
    profile = context.profiles.get(scenario.knowledge_profile_id)
    if profile.execution_scope is not ExecutionScope.REPOSITORY:
        raise RuntimeApiError(
            422,
            "repository_batch_profile_scope_mismatch",
            "repository batch requires a repository-scoped Knowledge Profile",
            details={
                "scenario_id": scenario.scenario_id,
                "knowledge_profile_id": profile.profile_id,
                "execution_scope": profile.execution_scope.value,
            },
        )
    required_parameters = [
        item.name
        for item in scenario.parameters
        if item.required
    ]
    if required_parameters:
        raise RuntimeApiError(
            422,
            "repository_batch_required_inputs_unsupported",
            "selected scenario requires per-run inputs that repository batch does not provide",
            details={
                "scenario_id": scenario.scenario_id,
                "required_parameters": required_parameters,
            },
        )

    contracts = discover_knowledge_contract_paths()
    output = (
        Path(options.output_path).expanduser().resolve()
        if options.output_path
        else _default_output_path(context, scenario_id=scenario.scenario_id)
    )
    work_dir = context.settings.runtime_root / "repository-batch-work"
    control_root = context.settings.runtime_root / "repository-batch-control"
    control_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="run-", dir=control_root) as temporary:
        profile_path = Path(temporary) / "knowledge-profile.json"
        profile_payload = serialize_knowledge_profile(
            profile,
            scope_id="repository-batch-template",
        )
        profile_path.write_text(
            json.dumps(profile_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        command = [
            *context.configuration.command_parts("static_analysis_runner"),
            "repository-batch-run",
            "--bitbucket-project-url",
            options.bitbucket_project_url,
            "--knowledge-profile",
            str(profile_path),
            "--knowledge-catalog",
            str(contracts.knowledge_catalog),
            "--core-evidence-catalog",
            str(contracts.core_evidence_catalog),
            "--materialization-catalog",
            str(contracts.materialization_catalog),
            "--output",
            str(output),
            "--work-dir",
            str(work_dir),
            "--auth-mode",
            options.auth_mode,
            "--timeout-seconds",
            str(options.timeout_seconds),
            "--clone-retries",
            str(options.clone_retries),
            "--clone-timeout-seconds",
            str(options.clone_timeout_seconds),
            "--duckdb-memory-limit",
            options.duckdb_memory_limit,
            "--duckdb-threads",
            str(options.duckdb_threads),
        ]
        if options.repository_limit is not None:
            command.extend(["--repository-limit", str(options.repository_limit)])
        if options.ca_bundle:
            command.extend(["--ca-bundle", str(Path(options.ca_bundle).expanduser().resolve())])
        if options.insecure_skip_tls_verify:
            command.append("--insecure-skip-tls-verify")
        if options.force_rebuild:
            command.append("--force-rebuild")
        if options.replace:
            command.append("--replace")
        else:
            command.append("--no-replace")

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                text=True,
            )
            stdout, _ = process.communicate()
        except OSError as exc:
            raise RuntimeApiError(
                503,
                "static_analysis_runner_unavailable",
                f"Static Analysis Runner is unavailable: {exc}",
            ) from exc
        if process.returncode != 0:
            raise RuntimeApiError(
                500,
                "repository_batch_execution_failed",
                "Static Analysis Runner repository batch execution failed",
                details={"returncode": process.returncode, "output": str(output)},
            )
        try:
            summary = json.loads(stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeApiError(
                500,
                "repository_batch_invalid_runner_response",
                "Static Analysis Runner returned an invalid repository batch summary",
                details={"output": str(output)},
            ) from exc
        if not isinstance(summary, dict):
            raise RuntimeApiError(
                500,
                "repository_batch_invalid_runner_response",
                "Static Analysis Runner returned a non-object repository batch summary",
                details={"output": str(output)},
            )

    return {
        **summary,
        "scenario_id": scenario.scenario_id,
        "knowledge_profile_id": profile.profile_id,
        "bitbucket_project_url": options.bitbucket_project_url,
        "output": str(output),
    }
