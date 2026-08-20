from __future__ import annotations

import os
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .io_utils import (
    now_utc,
    prepare_output,
    read_json,
    relative_or_absolute,
    stable_fingerprint,
    write_json,
    write_jsonl,
)
from .input_preparation import prepare_knowledge_input_inventory
from .knowledge_execution import execute_knowledge_execution_plan
from .knowledge_execution_planning import compile_knowledge_execution_plan
from .knowledge_planning import load_profile as load_knowledge_profile, resolve_knowledge_profile
from .repository_acquisition import (
    _clone_repository,
    _failure_message,
    _sanitize_repository_url,
    _write_askpass_script,
    prepare_repository_acquisition_run,
    select_repository_sources,
)
from .repository_sources import PortfolioRepositorySource
from .version import __version__

_RUN_MANIFEST_SCHEMA = "repository_batch_run_manifest/v1"
_RUN_SUMMARY_SCHEMA = "repository_batch_run_summary/v1"
_REPOSITORY_RESULT_SCHEMA = "repository_batch_repository_result/v1"


@dataclass(frozen=True, slots=True)
class RepositoryBatchRunResult:
    output: Path
    source_manifest: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]


def _repository_profile(profile: Mapping[str, Any], *, repo_id: str) -> dict[str, Any]:
    payload = deepcopy(dict(profile))
    scope = dict(payload.get("scope") or {})
    if str(scope.get("kind") or "").strip() != "repository":
        raise ValueError(
            "repository batch requires a repository-scoped knowledge_profile/v2; "
            f"got scope.kind={scope.get('kind')!r}"
        )
    scope["kind"] = "repository"
    scope["scope_id"] = repo_id
    payload["scope"] = scope
    return payload


def _repository_metadata(
    source: PortfolioRepositorySource,
    *,
    resolved_commit: str,
) -> dict[str, Any]:
    return {
        "repository_url": _sanitize_repository_url(source.clone_url),
        "requested_ref": source.ref,
        "resolved_commit": resolved_commit,
        "system_id": source.system_id,
        "project_id": source.project_id,
        "service_aliases": list(source.service_aliases),
        "source_metadata": dict(source.metadata),
        "acquisition": {
            "kind": "temporary_git_checkout",
            "checkout_persistence": "removed_after_repository_execution",
        },
    }


def _repository_result(
    *,
    source: PortfolioRepositorySource,
    status: str,
    started_at: str,
    finished_at: str,
    resolved_commit: str | None,
    failure_stage: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    knowledge_execution_result: str | None = None,
    knowledge_execution_result_fingerprint: str | None = None,
    published_capabilities: list[str] | None = None,
    knowledge_artifact_count: int | None = None,
    temporary_checkout_removed: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": _REPOSITORY_RESULT_SCHEMA,
        "repo_id": source.repo_id,
        "status": status,
        "repository_url": _sanitize_repository_url(source.clone_url),
        "requested_ref": source.ref,
        "resolved_commit": resolved_commit,
        "system_id": source.system_id,
        "project_id": source.project_id,
        "service_aliases": list(source.service_aliases),
        "source_metadata": dict(source.metadata),
        "failure_stage": failure_stage,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "knowledge_execution_result": knowledge_execution_result,
        "knowledge_execution_result_fingerprint": knowledge_execution_result_fingerprint,
        "published_capabilities": list(published_capabilities or []),
        "knowledge_artifact_count": knowledge_artifact_count,
        "temporary_checkout_removed": temporary_checkout_removed,
        "started_at": started_at,
        "finished_at": finished_at,
        "producer": {
            "component": "static-analysis-runner",
            "runner_version": __version__,
            "execution_semantics": "independent_repository_knowledge_execution",
        },
    }
    payload["result_fingerprint"] = stable_fingerprint(payload)
    return payload


def run_repository_batch(
    *,
    output: str | Path,
    work_dir: str | Path,
    knowledge_profile: str | Path,
    knowledge_catalog: str | Path,
    core_evidence_catalog: str | Path,
    materialization_catalog: str | Path,
    bitbucket_project_url: str | None = None,
    repository_sources: str | Path | None = None,
    core_command: str = "code-analyzer-core",
    auth_mode: str = "auto",
    token_env: str = "BITBUCKET_TOKEN",
    username_env: str = "BITBUCKET_USERNAME",
    password_env: str = "BITBUCKET_PASSWORD",
    api_base_path: str = "/rest/api/latest",
    ca_bundle: str | Path | None = None,
    insecure_skip_tls_verify: bool = False,
    timeout_seconds: float = 60.0,
    page_size: int = 100,
    max_repositories: int | None = None,
    clone_retries: int = 2,
    clone_timeout_seconds: float = 300.0,
    producer_cache_root: str | Path | None = None,
    force_rebuild: bool = False,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    replace: bool = False,
    progress: Callable[[str], None] | None = None,
) -> RepositoryBatchRunResult:
    """Execute the canonical repository knowledge pipeline independently for N repos.

    Repository discovery is a batch/orchestration concern only. Every repository gets
    its own repository-scoped knowledge profile, input inventory, execution plan and
    execution result. Repository contents are cloned into a Runner-owned temporary
    directory and deleted immediately after that repository finishes (success or
    failure). No multi-repository Core/Runner analysis scope is created here.
    """
    profile_path = Path(knowledge_profile).expanduser().resolve()
    knowledge_catalog_path = Path(knowledge_catalog).expanduser().resolve()
    core_catalog_path = Path(core_evidence_catalog).expanduser().resolve()
    materialization_catalog_path = Path(materialization_catalog).expanduser().resolve()
    protected = tuple(
        value
        for value in (
            profile_path,
            knowledge_catalog_path,
            core_catalog_path,
            materialization_catalog_path,
            Path(repository_sources).expanduser().resolve() if repository_sources else None,
        )
        if value is not None
    )
    root = prepare_output(output, replace=replace, protected_paths=protected)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    base_profile = load_knowledge_profile(profile_path)
    if str((base_profile.get("scope") or {}).get("kind") or "").strip() != "repository":
        raise ValueError("repository batch accepts only repository-scoped knowledge profiles")
    knowledge_catalog_payload = read_json(knowledge_catalog_path)
    core_catalog_payload = read_json(core_catalog_path)
    materialization_catalog_payload = read_json(materialization_catalog_path)
    # Validate knowledge selection before any repository contents are downloaded.
    resolve_knowledge_profile(knowledge_catalog_payload, base_profile)

    started_at = now_utc()
    if progress:
        progress("Discovering repositories for independent batch execution")
    sources = select_repository_sources(
        bitbucket_project_url=bitbucket_project_url,
        repository_sources=repository_sources,
        auth_mode=auth_mode,
        token_env=token_env,
        username_env=username_env,
        password_env=password_env,
        api_base_path=api_base_path,
        ca_bundle=ca_bundle,
        insecure_skip_tls_verify=insecure_skip_tls_verify,
        timeout_seconds=timeout_seconds,
        page_size=page_size,
        max_repositories=max_repositories,
    )
    source_manifest = root / "repository-sources.json"
    write_json(source_manifest, sources.to_dict())
    run_id = "repository-batch-" + stable_fingerprint(
        {
            "started_at": started_at,
            "repository_sources": sources.portfolio_fingerprint,
            "knowledge_profile": base_profile,
        }
    )[:16]
    run_root, stale_removed = prepare_repository_acquisition_run(
        work_dir,
        namespace="repository-batch",
        run_id=run_id,
    )
    askpass_script = _write_askpass_script(run_root)

    repository_results: list[dict[str, Any]] = []
    clone_attempt_rows: list[dict[str, Any]] = []
    secret_values = (
        os.environ.get(token_env, ""),
        os.environ.get(username_env, ""),
        os.environ.get(password_env, ""),
    )

    try:
        for index, source in enumerate(sources.repositories, start=1):
            if progress:
                progress(
                    f"Repository batch {index}/{len(sources.repositories)}: {source.repo_id}"
                )
            slot = run_root / "repository-slot"
            preparation_root = run_root / "repository-preparation"
            shutil.rmtree(slot, ignore_errors=True)
            shutil.rmtree(preparation_root, ignore_errors=True)
            repository_path = slot / source.repo_id
            persistent = root / "repositories" / source.repo_id
            persistent.mkdir(parents=True, exist_ok=True)
            started_repository_at = now_utc()
            resolved_commit: str | None = None
            failure_stage: str | None = None
            result: dict[str, Any] | None = None
            try:
                failure_stage = "download"
                resolved_commit, attempts = _clone_repository(
                    source=source,
                    target=repository_path,
                    logs=logs / "clone",
                    auth_mode=auth_mode,
                    token_env=token_env,
                    username_env=username_env,
                    password_env=password_env,
                    askpass_script=askpass_script,
                    retries=clone_retries,
                    timeout_seconds=clone_timeout_seconds,
                )
                clone_attempt_rows.extend(
                    {"repo_id": source.repo_id, **attempt} for attempt in attempts
                )

                repository_profile = _repository_profile(base_profile, repo_id=source.repo_id)
                write_json(persistent / "knowledge-profile.json", repository_profile)

                failure_stage = "input_preparation"
                inventory = prepare_knowledge_input_inventory(
                    scope_kind="repository",
                    scope_id=source.repo_id,
                    repositories=[repository_path],
                    core_evidence_catalog=core_catalog_payload,
                    materialization_catalog=materialization_catalog_payload,
                    preparation_root=preparation_root,
                    core_command=core_command,
                    producer_cache_root=(
                        Path(producer_cache_root).expanduser().resolve()
                        if producer_cache_root is not None
                        else None
                    ),
                    force_rebuild=force_rebuild,
                    progress=progress,
                    repository_metadata_by_source_id={
                        source.repo_id: _repository_metadata(
                            source,
                            resolved_commit=resolved_commit,
                        )
                    },
                )
                input_inventory_path = persistent / "knowledge-input-inventory.json"
                write_json(input_inventory_path, inventory)

                failure_stage = "planning"
                execution_plan = compile_knowledge_execution_plan(
                    knowledge_catalog=knowledge_catalog_payload,
                    knowledge_profile=repository_profile,
                    input_inventory=inventory,
                    core_evidence_catalog=core_catalog_payload,
                    materialization_catalog=materialization_catalog_payload,
                )
                execution_plan_path = persistent / "knowledge-execution-plan.json"
                write_json(execution_plan_path, execution_plan)
                if str((execution_plan.get("status") or {}).get("overall") or "") != "ready":
                    raise RuntimeError("repository knowledge execution plan is blocked; see persisted plan diagnostics")

                failure_stage = "execution"
                execution_output = persistent / "knowledge-execution"
                execution_result = execute_knowledge_execution_plan(
                    execution_plan=execution_plan_path,
                    core_evidence_catalog=core_catalog_path,
                    materialization_catalog=materialization_catalog_path,
                    output=execution_output,
                    core_command=core_command,
                    replace=True,
                    duckdb_memory_limit=duckdb_memory_limit,
                    duckdb_threads=duckdb_threads,
                    producer_cache_root=producer_cache_root,
                    force_rebuild=force_rebuild,
                    progress=progress,
                )
                result = _repository_result(
                    source=source,
                    status="completed",
                    started_at=started_repository_at,
                    finished_at=now_utc(),
                    resolved_commit=resolved_commit,
                    knowledge_execution_result=relative_or_absolute(
                        execution_output / "knowledge_execution_result.json",
                        root,
                    ),
                    knowledge_execution_result_fingerprint=str(
                        execution_result.get("result_fingerprint") or ""
                    ),
                    published_capabilities=[
                        str(value)
                        for value in execution_result.get("published_capabilities") or []
                    ],
                    knowledge_artifact_count=len(
                        execution_result.get("knowledge_artifacts") or []
                    ),
                    temporary_checkout_removed=False,
                )
            except Exception as exc:
                message = _failure_message(exc, secret_values=secret_values)
                code_by_stage = {
                    "download": "repository_clone_failed",
                    "input_preparation": "repository_input_preparation_failed",
                    "planning": "repository_knowledge_planning_failed",
                    "execution": "repository_knowledge_execution_failed",
                }
                status_by_stage = {
                    "download": "download_failed",
                    "input_preparation": "production_failed",
                    "planning": "production_failed",
                    "execution": "production_failed",
                }
                result = _repository_result(
                    source=source,
                    status=status_by_stage.get(failure_stage or "", "production_failed"),
                    started_at=started_repository_at,
                    finished_at=now_utc(),
                    resolved_commit=resolved_commit,
                    failure_stage=failure_stage,
                    failure_code=code_by_stage.get(
                        failure_stage or "", "repository_batch_execution_failed"
                    ),
                    failure_message=message,
                    temporary_checkout_removed=False,
                )
                if progress:
                    progress(
                        "Repository failed but batch continues: "
                        f"{source.repo_id}: {message}"
                    )
            finally:
                shutil.rmtree(slot, ignore_errors=True)
                shutil.rmtree(preparation_root, ignore_errors=True)
                if slot.exists() or preparation_root.exists():
                    raise RuntimeError(
                        "temporary repository cleanup failed; refusing to continue batch: "
                        f"{source.repo_id}: {run_root}"
                    )

            assert result is not None
            result["temporary_checkout_removed"] = True
            # Cleanup status is part of the repository result fingerprint.
            result.pop("result_fingerprint", None)
            result["result_fingerprint"] = stable_fingerprint(result)
            write_json(persistent / "repository-batch-result.json", result)
            repository_results.append(result)

        write_jsonl(root / "clone-attempts.jsonl", clone_attempt_rows)
        completed_at = now_utc()
        completed = sum(item.get("status") == "completed" for item in repository_results)
        failed = len(repository_results) - completed
        status = "completed" if completed and not failed else "partial" if completed else "failed"
        manifest: dict[str, Any] = {
            "schema_version": _RUN_MANIFEST_SCHEMA,
            "runner": {"producer": "static-analysis-runner", "version": __version__},
            "status": status,
            "execution_semantics": "independent_repository_knowledge_execution",
            "source_manifest": relative_or_absolute(source_manifest, root),
            "repository_source_fingerprint": sources.portfolio_fingerprint,
            "repository_selection": dict(
                (sources.source.get("repository_selection") or {})
                if isinstance(sources.source, Mapping)
                else {}
            ),
            "knowledge_profile": {
                "path": str(profile_path),
                "profile_id": base_profile.get("profile_id"),
                "scope_kind": "repository",
                "per_repository_scope_id": "repo_id",
            },
            "repository_results": repository_results,
            "summary": {
                "total": len(repository_results),
                "completed": completed,
                "failed": failed,
            },
            "temporary_work": {
                "run_id": run_id,
                "stale_runs_removed": stale_removed,
                "execution_mode": "sequential",
                "max_concurrent_checkouts": 1,
                "repository_checkout_removed_after_each_repository": True,
                "persistent_repository_checkout_count": 0,
            },
            "started_at": started_at,
            "completed_at": completed_at,
        }
        manifest["run_fingerprint"] = stable_fingerprint(manifest)
        summary = {
            "schema_version": _RUN_SUMMARY_SCHEMA,
            "status": status,
            "repository_count": len(repository_results),
            "repositories_completed": completed,
            "repositories_failed": failed,
            "execution_mode": "sequential",
            "max_concurrent_checkouts": 1,
            "persistent_repository_checkout_count": 0,
            "output": str(root),
        }
        write_json(root / "repository-batch-run-manifest.json", manifest)
        write_json(root / "repository-batch-run-summary.json", summary)
        return RepositoryBatchRunResult(
            output=root,
            source_manifest=source_manifest,
            manifest=manifest,
            summary=summary,
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        if run_root.exists():
            raise RuntimeError(f"temporary repository batch run cleanup failed: {run_root}")
