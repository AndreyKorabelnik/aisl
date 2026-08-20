from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .io_utils import now_utc, prepare_output, read_json, relative_or_absolute, stable_fingerprint, write_json, write_jsonl
from .repository_acquisition import (
    _clone_repository,
    _failure_message,
    _sanitize_repository_url,
    _write_askpass_script,
    prepare_repository_acquisition_run,
    select_repository_sources,
)
from .repository_sources import PortfolioRepositorySource
from .evidence_executor import execute_core_evidence_request
from .runtime_support import validate_core_version
from .version import __version__

_RUN_MANIFEST_SCHEMA = "data_model_discovery_run_manifest/v1"
_RUN_SUMMARY_SCHEMA = "data_model_discovery_run_summary/v1"
_INVENTORY_SCHEMA = "data_model_candidate_inventory/v1"


@dataclass(frozen=True, slots=True)
class DataModelDiscoveryRunResult:
    output: Path
    source_manifest: Path
    inventory_path: Path
    manifest: dict[str, Any]
    summary: dict[str, Any]


def _candidate_request(*, source_id: str) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": "core_evidence_execution_request/v1",
        "source": {"source_kind": "repository", "source_id": source_id},
        "evidence_requirements": [
            {
                "artifact_kind": "data-model-candidate-evidence",
                "schema_version": "data-model-candidate-evidence/v1",
                "parameters": {},
                "required_by": ["data-model-discovery"],
            }
        ],
        "orchestration": {
            "producer": "static-analysis-runner",
            "runner_version": __version__,
            "semantic_routing": "artifact_kind_plus_schema_version",
        },
    }
    request["request_fingerprint"] = stable_fingerprint(request)
    return request


def _publish_candidate_profile(
    *,
    analysis_manifest: Mapping[str, Any],
    analysis_output: Path,
    output: Path,
    source: PortfolioRepositorySource,
    resolved_commit: str,
    core_version: str,
) -> tuple[Path, dict[str, Any]]:
    artifacts = [
        dict(item)
        for item in analysis_manifest.get("evidence_artifacts") or []
        if isinstance(item, Mapping)
        and item.get("artifact_kind") == "data-model-candidate-evidence"
        and item.get("schema_version") == "data-model-candidate-evidence/v1"
    ]
    if len(artifacts) != 1:
        raise RuntimeError("data model discovery must publish exactly one typed candidate evidence artifact")
    location = dict(artifacts[0].get("location") or {})
    raw_path = Path(str(location.get("path") or ""))
    evidence_path = raw_path if raw_path.is_absolute() else analysis_output / raw_path
    if not evidence_path.is_file():
        raise RuntimeError(f"data model candidate evidence was not published: {evidence_path}")
    evidence = read_json(evidence_path)
    if evidence.get("schema_version") != "data-model-candidate-evidence/v1":
        raise RuntimeError(f"unsupported candidate evidence schema: {evidence.get('schema_version')!r}")
    profile = dict(evidence.get("candidate_profile") or {})
    if profile.get("schema_version") != "data_model_candidate_profile/v1":
        raise RuntimeError(f"unsupported candidate profile schema: {profile.get('schema_version')!r}")
    staging = output.with_name(f".{output.name}.building-{uuid.uuid4().hex[:12]}")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        profile["repository"] = {
            "repo_id": source.repo_id,
            "repository_url": _sanitize_repository_url(source.clone_url),
            "requested_ref": source.ref,
            "resolved_commit": resolved_commit,
            "system_id": source.system_id,
            "project_id": source.project_id,
            "service_aliases": list(source.service_aliases),
        }
        profile["producer"] = {
            "component": "code-analyzer-core",
            "analyzer_id": "data-model-candidate-analyzer",
            "core_version": core_version,
            "runner_version": __version__,
        }
        profile["evidence_artifact"] = {
            "artifact_id": evidence.get("artifact_id"),
            "artifact_kind": evidence.get("artifact_kind"),
            "schema_version": evidence.get("schema_version"),
            "content_fingerprint": evidence.get("content_fingerprint"),
        }
        profile["profile_fingerprint"] = stable_fingerprint({
            "repository": profile["repository"],
            "candidate_status": profile.get("candidate_status"),
            "score": profile.get("score"),
            "signals": profile.get("signals"),
            "score_components": profile.get("score_components"),
            "evidence": profile.get("evidence"),
            "evidence_artifact": profile["evidence_artifact"],
        })
        write_json(staging / "data-model-candidate-profile.json", profile)
        write_json(staging / "data-model-candidate-evidence.json", evidence)
        if output.exists():
            shutil.rmtree(output)
        os.replace(staging, output)
        return output / "data-model-candidate-profile.json", profile
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _repository_result(
    *,
    source: PortfolioRepositorySource,
    status: str,
    started_at: str,
    finished_at: str,
    resolved_commit: str | None,
    core_version: str,
    candidate_profile: str | None = None,
    candidate_status: str | None = None,
    score: int | None = None,
    failure_stage: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> dict[str, Any]:
    return {
        "repo_id": source.repo_id,
        "status": status,
        "requested_ref": source.ref,
        "resolved_commit": resolved_commit,
        "repository_url": _sanitize_repository_url(source.clone_url),
        "system_id": source.system_id,
        "project_id": source.project_id,
        "candidate_profile": candidate_profile,
        "candidate_status": candidate_status,
        "score": score,
        "failure_stage": failure_stage,
        "failure_code": failure_code,
        "failure_message": failure_message,
        "started_at": started_at,
        "finished_at": finished_at,
        "producer": {
            "runner_version": __version__,
            "core_version": core_version,
            "runtime_contract": "core_evidence_runtime/v1",
        },
    }


def _candidate_entry(profile: Mapping[str, Any], profile_path: str) -> dict[str, Any]:
    repository = dict(profile.get("repository") or {})
    return {
        "repo_id": repository.get("repo_id") or profile.get("repo_id"),
        "repository_url": repository.get("repository_url"),
        "requested_ref": repository.get("requested_ref"),
        "resolved_commit": repository.get("resolved_commit"),
        "candidate_status": profile.get("candidate_status"),
        "score": int(profile.get("score") or 0),
        "signals": dict(profile.get("signals") or {}),
        "score_components": list(profile.get("score_components") or []),
        "evidence": list(profile.get("evidence") or []),
        "candidate_profile": profile_path,
        "profile_fingerprint": profile.get("profile_fingerprint"),
    }


def run_data_model_discovery(
    *,
    output: str | Path,
    work_dir: str | Path,
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
    replace: bool = False,
    progress: Callable[[str], None] | None = None,
) -> DataModelDiscoveryRunResult:
    protected = tuple(
        value
        for value in (
            Path(repository_sources).expanduser().resolve() if repository_sources else None,
        )
        if value is not None
    )
    root = prepare_output(output, replace=replace, protected_paths=protected)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    started_at = now_utc()
    if progress:
        progress("Discovering repositories for data model candidate scan")
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
    source_manifest = root / "portfolio-repository-sources.json"
    write_json(source_manifest, sources.to_dict())
    run_id = "data-model-discovery-" + stable_fingerprint(
        {"started_at": started_at, "portfolio": sources.portfolio_fingerprint}
    )[:16]
    run_root, stale_removed = prepare_repository_acquisition_run(
        work_dir,
        namespace="data-model-discovery",
        run_id=run_id,
    )
    askpass_script = _write_askpass_script(run_root)
    with tempfile.TemporaryDirectory(prefix="data-model-discovery-preflight-") as temporary:
        core_version = validate_core_version(
            core_command=core_command,
            log_path=Path(temporary) / "core-version.log",
            progress=progress,
        )
    (logs / "core-version.log").write_text(core_version + "\n", encoding="utf-8")

    repository_results: list[dict[str, Any]] = []
    candidate_entries: list[dict[str, Any]] = []
    clone_attempt_rows: list[dict[str, Any]] = []
    secret_values = (
        os.environ.get(token_env, ""),
        os.environ.get(username_env, ""),
        os.environ.get(password_env, ""),
    )
    try:
        for index, source in enumerate(sources.repositories, start=1):
            if progress:
                progress(f"Data model discovery repository {index}/{len(sources.repositories)}: {source.repo_id}")
            slot = run_root / "repository-slot"
            analysis_output = run_root / "repository-analysis"
            shutil.rmtree(slot, ignore_errors=True)
            shutil.rmtree(analysis_output, ignore_errors=True)
            repository_path = slot / "repository"
            persistent = root / "repository-results" / source.repo_id
            started_repository_at = now_utc()
            resolved_commit: str | None = None
            try:
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
                clone_attempt_rows.extend({"repo_id": source.repo_id, **attempt} for attempt in attempts)
                analysis_manifest = execute_core_evidence_request(
                    repository=repository_path,
                    request=_candidate_request(source_id=source.repo_id),
                    output=analysis_output,
                    core_command=core_command,
                    repo_id=source.repo_id,
                    replace=True,
                    progress=progress,
                    request_provenance={
                        "workflow": "data-model-discovery",
                        "resolved_commit": resolved_commit,
                        "system_id": source.system_id,
                        "project_id": source.project_id,
                    },
                )
                profile_path, profile = _publish_candidate_profile(
                    analysis_manifest=analysis_manifest,
                    analysis_output=analysis_output,
                    output=persistent,
                    source=source,
                    resolved_commit=resolved_commit,
                    core_version=core_version,
                )
                relative_profile = relative_or_absolute(profile_path, root)
                result = _repository_result(
                    source=source,
                    status="completed",
                    started_at=started_repository_at,
                    finished_at=now_utc(),
                    resolved_commit=resolved_commit,
                    core_version=core_version,
                    candidate_profile=relative_profile,
                    candidate_status=str(profile.get("candidate_status") or "not_candidate"),
                    score=int(profile.get("score") or 0),
                )
                write_json(persistent / "repository-discovery-result.json", result)
                repository_results.append(result)
                if profile.get("candidate_status") != "not_candidate":
                    candidate_entries.append(_candidate_entry(profile, relative_profile))
            except Exception as exc:
                failure_stage = "download" if resolved_commit is None else "analysis"
                status = "download_failed" if resolved_commit is None else "analysis_failed"
                failure_code = "repository_clone_failed" if resolved_commit is None else "repository_data_model_discovery_failed"
                message = _failure_message(exc, secret_values=secret_values)
                shutil.rmtree(persistent, ignore_errors=True)
                persistent.mkdir(parents=True, exist_ok=True)
                result = _repository_result(
                    source=source,
                    status=status,
                    started_at=started_repository_at,
                    finished_at=now_utc(),
                    resolved_commit=resolved_commit,
                    core_version=core_version,
                    failure_stage=failure_stage,
                    failure_code=failure_code,
                    failure_message=message,
                )
                write_json(persistent / "repository-discovery-result.json", result)
                repository_results.append(result)
                if progress:
                    progress(f"Data model discovery failed but portfolio continues: {source.repo_id}: {message}")
            finally:
                shutil.rmtree(slot, ignore_errors=True)
                shutil.rmtree(analysis_output, ignore_errors=True)
                if slot.exists() or analysis_output.exists():
                    raise RuntimeError(f"temporary repository cleanup failed for {source.repo_id}: {run_root}")

        write_jsonl(root / "clone-attempts.jsonl", clone_attempt_rows)
        completed_at = now_utc()
        completed = sum(item["status"] == "completed" for item in repository_results)
        failed = len(repository_results) - completed
        status = "completed" if completed and not failed else "partial" if completed else "failed"
        candidate_entries.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("repo_id") or "")))
        candidate_counts = {
            label: sum(item.get("candidate_status") == label for item in candidate_entries)
            for label in ("strong", "possible", "weak")
        }
        inventory = {
            "schema_version": _INVENTORY_SCHEMA,
            "status": status,
            "source": dict(sources.source),
            "portfolio_fingerprint": sources.portfolio_fingerprint,
            "repository_selection": dict((sources.source.get("repository_selection") or {}) if isinstance(sources.source, Mapping) else {}),
            "repository_summary": {
                "total": len(repository_results),
                "completed": completed,
                "failed": failed,
                "not_candidate": sum(item.get("candidate_status") == "not_candidate" for item in repository_results),
                **candidate_counts,
            },
            "candidates": candidate_entries,
            "repositories": repository_results,
            "coverage": {
                "status": "complete" if not failed else "partial" if completed else "failed",
                "full_data_model_analysis_performed": False,
                "workspace_created": False,
                "decision_owner": "user",
            },
            "started_at": started_at,
            "completed_at": completed_at,
        }
        inventory["inventory_fingerprint"] = stable_fingerprint(
            {
                "portfolio_fingerprint": sources.portfolio_fingerprint,
                "candidates": [
                    {
                        "repo_id": item.get("repo_id"),
                        "candidate_status": item.get("candidate_status"),
                        "score": item.get("score"),
                        "profile_fingerprint": item.get("profile_fingerprint"),
                    }
                    for item in candidate_entries
                ],
                "repository_statuses": [
                    {"repo_id": item.get("repo_id"), "status": item.get("status"), "resolved_commit": item.get("resolved_commit")}
                    for item in repository_results
                ],
            }
        )
        inventory_path = root / "data-model-candidates.json"
        write_json(inventory_path, inventory)
        manifest = {
            "schema_version": _RUN_MANIFEST_SCHEMA,
            "runner": {"producer": "static-analysis-runner", "version": __version__},
            "status": status,
            "source_manifest": relative_or_absolute(source_manifest, root),
            "portfolio_fingerprint": sources.portfolio_fingerprint,
            "repository_selection": inventory["repository_selection"],
            "inventory": relative_or_absolute(inventory_path, root),
            "inventory_fingerprint": inventory["inventory_fingerprint"],
            "repository_results": repository_results,
            "temporary_work": {
                "run_id": run_id,
                "stale_runs_removed": stale_removed,
                "repository_slot_removed_after_each_repository": True,
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
            "candidate_counts": candidate_counts,
            "candidate_count": len(candidate_entries),
            "inventory": relative_or_absolute(inventory_path, root),
            "output": str(root),
        }
        write_json(root / "data-model-discovery-run-manifest.json", manifest)
        write_json(root / "data-model-discovery-run-summary.json", summary)
        return DataModelDiscoveryRunResult(
            output=root,
            source_manifest=source_manifest,
            inventory_path=inventory_path,
            manifest=manifest,
            summary=summary,
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
