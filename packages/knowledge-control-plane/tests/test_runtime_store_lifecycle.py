from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from knowledge_control_plane.api.generic_v1.models import (
    JobDetails, JobKind, JobOutputOptions, JobProgress, JobStatus, JobTarget,
)
from knowledge_control_plane.runtime import store as store_module
from knowledge_control_plane.runtime.store import RuntimeStore


def _job(job_id: str, status: JobStatus) -> JobDetails:
    return JobDetails(
        job_id=job_id,
        kind=JobKind.KNOWLEDGE_EXECUTION,
        status=status,
        scenario_id="build-data-model-v1",
        knowledge_profile_id="data-model-v1",
        knowledge_ids=["code-declared-data-model"],
        target=JobTarget(repository_id="repo", system_id="system"),
        progress=JobProgress(current_stage="prepare_inputs", message=status.value),
        created_at=datetime.now(UTC),
        output=JobOutputOptions(),
    )


def test_runtime_store_closes_every_sqlite_connection(monkeypatch, tmp_path: Path) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(store_module.sqlite3, "connect", tracked_connect)
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.quick_check()
    store.load_configuration()
    store.list_repositories()
    store.list_workspaces()
    store.list_jobs()
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


def test_runtime_schema_is_versioned_and_rejects_old_database(tmp_path: Path) -> None:
    current = tmp_path / "current.sqlite3"
    RuntimeStore(current)
    with sqlite3.connect(current) as connection:
        assert connection.execute("SELECT value FROM runtime_metadata WHERE key='schema_version'").fetchone()[0] == "3"

    old = tmp_path / "old.sqlite3"
    with sqlite3.connect(old) as connection:
        connection.execute("CREATE TABLE jobs(job_id TEXT)")
    with pytest.raises(RuntimeError, match="legacy Knowledge Control Plane runtime database is not supported"):
        RuntimeStore(old)


def test_runtime_store_recovers_only_generic_job_states(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    for job_id, status in (("queued", JobStatus.QUEUED), ("preparing", JobStatus.PREPARING), ("running", JobStatus.RUNNING), ("done", JobStatus.SUCCEEDED)):
        job = _job(job_id, status)
        store.insert_job(job, request_json="{}", idempotency_key=None)
    queued, interrupted = store.recover_incomplete_jobs()
    assert queued == ["queued"]
    assert interrupted == ["preparing", "running"]
    assert store.delete_job("done") is True
    assert store.get_job("done") is None
