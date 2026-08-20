from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    JobDetails,
    JobFailure,
    JobKind,
    JobOutputOptions,
    JobProgress,
    JobPublicationBundle,
    JobStatus,
    KnowledgeProfileDefinition,
    ProductionCreateRequest,
    ProductionFreshnessStatus,
    ProductionRefreshMode,
    ProductionRefreshPolicy,
    ProductionUpdateRequest,
    RepositoryDiscoverRequest,
    ScenarioDefinition,
    ScenarioSourceMode,
    SourceSnapshot,
    SourceSnapshotKind,
)
from knowledge_control_plane.runtime.errors import RuntimeApiError
from knowledge_control_plane.runtime.freshness import FreshnessService, source_snapshot_fingerprint
from knowledge_control_plane.runtime.jobs import JobManager
from knowledge_control_plane.runtime.productions import ProductionService
from knowledge_control_plane.runtime.repositories import RepositoryService
from knowledge_control_plane.runtime.settings import RuntimeSettings
from knowledge_control_plane.runtime.store import RuntimeStore


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, text: str) -> str:
    (repo / "value.txt").write_text(text, encoding="utf-8")
    _git(repo, "add", "value.txt")
    _git(repo, "commit", "-m", text)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.test")
    _git(repo, "config", "user.name", "Test")
    _commit(repo, "A")
    return repo


def _settings(tmp_path: Path) -> RuntimeSettings:
    settings = RuntimeSettings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "knowledge-control-plane.sqlite3",
        jobs_root=tmp_path / "runtime" / "jobs",
        default_analysis_output_root=tmp_path / "outputs" / "analysis",
    )
    settings.ensure_directories()
    return settings


class _Catalog:
    def __init__(self, value):
        self.value = value

    def get(self, _identifier: str):
        return self.value


class _FakeJobs:
    def __init__(self, store: RuntimeStore):
        self.store = store
        self.created: list[JobDetails] = []

    async def create(self, request):
        job_id = f"job-refresh-{len(self.created) + 1}"
        job = JobDetails(
            job_id=job_id,
            display_name=request.display_name,
            kind=JobKind.KNOWLEDGE_EXECUTION,
            status=JobStatus.QUEUED,
            scenario_id=request.scenario_id,
            knowledge_profile_id=request.knowledge_profile_id or "profile",
            production_id=request.production_id,
            production_revision=request.production_revision,
            target=request.target,
            progress=JobProgress(message="Queued"),
            created_at=datetime.now(UTC),
            output=JobOutputOptions(),
            source_snapshots=list(request.source_snapshots),
            source_snapshot_fingerprint=request.source_snapshot_fingerprint,
        )
        self.store.insert_job(job, request_json=request.model_dump_json(), idempotency_key=None)
        self.created.append(job)
        return job

    def get(self, job_id: str) -> JobDetails:
        job = self.store.get_job(job_id)
        if job is None:
            from knowledge_control_plane.runtime.errors import ResourceNotFound
            raise ResourceNotFound("job", job_id)
        return job


def _services(tmp_path: Path):
    settings = _settings(tmp_path)
    store = RuntimeStore(settings.database_path)
    repositories = RepositoryService(store, settings)
    repo_path = _repo(tmp_path)
    repository = repositories.discover(RepositoryDiscoverRequest(roots=[str(repo_path)])).repositories[0]
    profile = KnowledgeProfileDefinition(
        profile_id="profile",
        name="Profile",
        execution_scope=ExecutionScope.REPOSITORY,
        knowledge_ids=["code-declared-data-model"],
        fingerprint="a" * 64,
    )
    scenario = ScenarioDefinition(
        scenario_id="scenario",
        name="Scenario",
        knowledge_profile_id="profile",
        source_mode=ScenarioSourceMode.REPOSITORY,
    )
    productions = ProductionService(
        store=store,
        repositories=repositories,
        profiles=_Catalog(profile),
        scenarios=_Catalog(scenario),
    )
    jobs = _FakeJobs(store)
    freshness = FreshnessService(
        store=store,
        productions=productions,
        repositories=repositories,
        jobs=jobs,  # type: ignore[arg-type]
    )
    production = productions.create(
        ProductionCreateRequest(
            production_id="prod",
            system_id="system",
            scenario_id="scenario",
            knowledge_profile_id="profile",
            repository_ids=[repository.repository_id],
            refresh_policy=ProductionRefreshPolicy(mode=ProductionRefreshMode.POLL, interval="P1D"),
        )
    )
    return store, repositories, repo_path, repository, productions, jobs, freshness, production


def _set_baseline(productions: ProductionService, repositories: RepositoryService, production):
    snapshot = repositories.resolve_snapshot(production.repository_ids[0])
    assert snapshot.availability.value == "available"
    return productions.update_runtime_state(
        production.model_copy(
            update={
                "freshness_status": ProductionFreshnessStatus.UP_TO_DATE,
                "last_successful_bundle_sha256": "a" * 64,
                "last_successful_production_revision": production.revision,
                "last_successful_source_snapshots": [snapshot],
                "last_observed_source_snapshots": [snapshot],
                "desired_source_snapshot_fingerprint": source_snapshot_fingerprint([snapshot]),
            }
        )
    )


@pytest.mark.asyncio
async def test_unchanged_baseline_does_not_enqueue(tmp_path: Path) -> None:
    _store, repositories, _repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    _set_baseline(productions, repositories, production)

    result = await freshness.check("prod")

    assert result.production.freshness_status is ProductionFreshnessStatus.UP_TO_DATE
    assert result.enqueued_job_id is None
    assert jobs.created == []


@pytest.mark.asyncio
async def test_changed_commit_enqueues_once_and_failed_build_retries_without_moving_baseline(tmp_path: Path) -> None:
    store, repositories, repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    baseline = _set_baseline(productions, repositories, production)
    baseline_sha = baseline.last_successful_source_snapshots[0].resolved_version["commit_sha"]
    new_sha = _commit(repo_path, "B")

    first = await freshness.check("prod")
    second_while_queued = await freshness.check("prod")
    assert first.enqueued_job_id == "job-refresh-1"
    assert second_while_queued.enqueued_job_id is None
    assert len(jobs.created) == 1
    assert jobs.created[0].source_snapshots[0].resolved_version["commit_sha"] == new_sha

    failed = store.get_job("job-refresh-1")
    assert failed is not None
    store.update_job(
        failed.model_copy(
            update={
                "status": JobStatus.FAILED,
                "failure": JobFailure(code="test_failure", message="boom", retryable=True),
                "finished_at": datetime.now(UTC),
            }
        )
    )

    retry = await freshness.check("prod")
    current = productions.get("prod")
    assert retry.enqueued_job_id == "job-refresh-2"
    assert len(jobs.created) == 2
    assert current.last_successful_source_snapshots[0].resolved_version["commit_sha"] == baseline_sha


@pytest.mark.asyncio
async def test_source_unavailable_is_not_no_change(tmp_path: Path) -> None:
    _store, repositories, repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    _set_baseline(productions, repositories, production)
    (repo_path / "value.txt").write_text("dirty", encoding="utf-8")

    result = await freshness.check("prod")

    assert result.production.freshness_status is ProductionFreshnessStatus.SOURCE_UNAVAILABLE
    assert result.enqueued_job_id is None
    assert jobs.created == []
    assert result.production.diagnostics


@pytest.mark.asyncio
async def test_newer_commit_waits_for_active_pinned_job_then_queues_next(tmp_path: Path) -> None:
    store, repositories, repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    _set_baseline(productions, repositories, production)
    sha_b = _commit(repo_path, "B")
    first = await freshness.check("prod")
    assert first.enqueued_job_id == "job-refresh-1"

    running = store.get_job("job-refresh-1")
    assert running is not None
    store.update_job(running.model_copy(update={"status": JobStatus.RUNNING, "started_at": datetime.now(UTC)}))
    sha_c = _commit(repo_path, "C")

    while_running = await freshness.check("prod")
    assert while_running.enqueued_job_id is None
    assert while_running.production.freshness_status is ProductionFreshnessStatus.UPDATE_RUNNING
    assert len(jobs.created) == 1
    assert while_running.production.diagnostics

    completed = store.get_job("job-refresh-1")
    assert completed is not None
    store.update_job(
        completed.model_copy(
            update={
                "status": JobStatus.SUCCEEDED,
                "finished_at": datetime.now(UTC),
                "publication_bundle": JobPublicationBundle(
                    path="/tmp/job-refresh-1.aisl.zip",
                    sha256="b" * 64,
                    member_count=3,
                ),
            }
        )
    )
    next_result = await freshness.check("prod")
    assert next_result.enqueued_job_id == "job-refresh-2"
    assert len(jobs.created) == 2
    assert jobs.created[0].source_snapshots[0].resolved_version["commit_sha"] == sha_b
    assert jobs.created[1].source_snapshots[0].resolved_version["commit_sha"] == sha_c
    current = productions.get("prod")
    assert current.last_successful_bundle_sha256 == "b" * 64
    assert current.last_successful_source_snapshots[0].resolved_version["commit_sha"] == sha_b


@pytest.mark.asyncio
async def test_production_configuration_revision_triggers_refresh_without_source_change(tmp_path: Path) -> None:
    _store, repositories, _repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    baseline = _set_baseline(productions, repositories, production)
    updated = productions.update(
        "prod",
        ProductionUpdateRequest(expected_revision=baseline.revision, parameters={"duckdb_threads": 1}),
    )
    assert updated.revision == baseline.revision + 1

    result = await freshness.check("prod")

    assert result.enqueued_job_id == "job-refresh-1"
    assert jobs.created[0].production_revision == updated.revision
    assert "configuration revision" in " ".join(result.production.diagnostics) or result.production.freshness_status is ProductionFreshnessStatus.UPDATE_QUEUED


def test_local_git_refresh_checkout_is_detached_at_resolved_commit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = RuntimeStore(settings.database_path)
    repositories = RepositoryService(store, settings)
    repo_path = _repo(tmp_path)
    repository = repositories.discover(RepositoryDiscoverRequest(roots=[str(repo_path)])).repositories[0]
    snapshot = repositories.resolve_snapshot(repository.repository_id)
    sha_a = snapshot.resolved_version["commit_sha"]
    _commit(repo_path, "B")

    commands = repositories.pinned_checkout_commands(
        repository.repository_id,
        job_id="job-pin",
        commit_sha=str(sha_a),
    )
    for command in commands:
        env = os.environ.copy()
        env.update(command.environment)
        subprocess.run(command.argv, cwd=command.cwd, env=env, check=True, capture_output=True, text=True)
    target = repositories.finalize_pinned_checkout(
        repository.repository_id,
        job_id="job-pin",
        expected_commit_sha=str(sha_a),
    )

    assert _git(target, "rev-parse", "HEAD") == sha_a
    assert _git(target, "branch", "--show-current") == ""
    assert (target / "value.txt").read_text(encoding="utf-8") == "A"


def test_physical_model_mutation_after_snapshot_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "model.pdm"
    source.write_bytes(b"A")
    expected = hashlib.sha256(b"A").hexdigest()
    snapshot_payload = f"file:{source}:{expected}".encode()
    snapshot = SourceSnapshot(
        source_id="physical-model",
        source_kind=SourceSnapshotKind.FILE,
        location=str(source),
        resolved_version={"kind": "sha256", "sha256": expected, "byte_size": 1},
        checked_at=datetime.now(UTC),
        snapshot_fingerprint=hashlib.sha256(snapshot_payload).hexdigest(),
    )
    request = SimpleNamespace(
        source_snapshots=[snapshot],
        target=SimpleNamespace(physical_model_path=str(source)),
    )
    plan = SimpleNamespace(physical_input_root=tmp_path / "job" / "inputs" / "physical-model")
    source.write_bytes(b"B")

    manager = object.__new__(JobManager)
    with pytest.raises(RuntimeApiError, match="physical-model source changed") as exc_info:
        manager._prepare_physical_model_source(plan, request)  # type: ignore[arg-type]
    assert exc_info.value.code == "source_snapshot_mismatch"

@pytest.mark.asyncio
async def test_manual_force_refresh_enqueues_even_when_sources_are_unchanged(tmp_path: Path) -> None:
    _store, repositories, _repo_path, _repository, productions, jobs, freshness, production = _services(tmp_path)
    _set_baseline(productions, repositories, production)

    result = await freshness.check("prod", enqueue=True, force=True)

    assert result.enqueued_job_id == "job-refresh-1"
    raw = jobs.store.get_job_request_json("job-refresh-1")
    assert raw is not None
    from knowledge_control_plane.api.generic_v1.models import JobCreateRequest, JobReusePolicy
    request = JobCreateRequest.model_validate_json(raw)
    assert request.reuse_policy is JobReusePolicy.FORCE_REBUILD
