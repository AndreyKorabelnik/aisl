from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from knowledge_control_plane import cli
from knowledge_control_plane.api.generic_v1.models import JobLogEntry, JobStatus, LogLevel, LogStream
from knowledge_control_plane.runtime.jobs import JobManager
from knowledge_control_plane.runtime.observability import append_job_run_log
from knowledge_control_plane.runtime.one_shot import OneShotRunOptions, run_one_shot
from knowledge_control_plane.runtime.settings import RuntimeSettings


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        knowledge_revision=[],
        parameter=[],
        scenario="scenario-v1",
        system_id="system-a",
        repository=[],
        physical_model=None,
        display_name=None,
        output=None,
        replace=False,
        force_rebuild=False,
        as_json=True,
    )


def test_json_mode_keeps_stdout_machine_readable_and_progress_on_stderr(monkeypatch, capsys, tmp_path: Path) -> None:
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    result = SimpleNamespace(
        status=JobStatus.SUCCEEDED,
        job_id="job-1",
        target=SimpleNamespace(system_id="system-a"),
        publication_bundle=None,
        output=SimpleNamespace(output_path=None),
        failure=None,
        model_dump=lambda mode="json": {"status": "succeeded", "job_id": "job-1"},
    )

    async def fake_run(_context, _options, *, on_log=None):
        assert on_log is not None
        on_log("2026-08-12T10:00:00+03:00 INFO [runner_execution] running")
        return result

    monkeypatch.setattr(cli.RuntimeSettings, "from_environment", classmethod(lambda cls: settings))
    monkeypatch.setattr(cli, "configure_runtime_logging", lambda _settings: _settings.runtime_log_path)
    monkeypatch.setattr(cli, "build_runtime_context", lambda _settings: object())
    monkeypatch.setattr(cli, "run_one_shot", fake_run)

    assert cli._run(_args()) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "succeeded", "job_id": "job-1"}
    assert "runner_execution" in captured.err
    assert "running" in captured.err


def test_one_shot_emits_canonical_heartbeat_when_visible_logs_are_silent(tmp_path: Path, monkeypatch) -> None:
    running = SimpleNamespace(status=JobStatus.RUNNING, job_id="job-1")
    succeeded = SimpleNamespace(status=JobStatus.SUCCEEDED, job_id="job-1")

    class Jobs:
        def __init__(self) -> None:
            self.heartbeat_count = 0
            self._done = False

        async def start(self):
            return None

        async def create(self, _request):
            return running

        def logs(self, **_kwargs):
            return SimpleNamespace(entries=[])

        def get(self, _job_id):
            return succeeded if self._done else running

        async def heartbeat(self, _job_id):
            self.heartbeat_count += 1
            self._done = True

        async def stop(self):
            return None

        async def cancel(self, _job_id):
            raise AssertionError("cancel should not be called")

    jobs = Jobs()
    settings = SimpleNamespace(
        event_poll_interval_seconds=0.0001,
        one_shot_heartbeat_seconds=0.0,
        job_run_log_path=lambda job_id: tmp_path / "logs" / "jobs" / job_id / "run.log",
    )
    context = SimpleNamespace(jobs=jobs, settings=settings)
    monkeypatch.setattr("knowledge_control_plane.runtime.one_shot.build_job_request", lambda *_args: object())
    messages: list[str] = []
    completed = asyncio.run(
        run_one_shot(
            context,
            OneShotRunOptions(scenario_id="scenario-v1", system_id="system-a"),
            on_log=messages.append,
        )
    )
    assert completed is succeeded
    assert jobs.heartbeat_count == 1
    assert messages[0].startswith("run_log=")


def test_per_job_run_log_is_human_readable_mirror(tmp_path: Path) -> None:
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    entry = JobLogEntry(
        sequence=1,
        timestamp="2026-08-12T07:00:00Z",
        level=LogLevel.INFO,
        stream=LogStream.SYSTEM,
        stage="runner_execution",
        message="Runner is executing",
    )
    path = append_job_run_log(settings, "job-abc", entry)
    assert path == tmp_path / "runtime" / "control-plane" / "logs" / "jobs" / "job-abc" / "run.log"
    content = path.read_text(encoding="utf-8")
    assert "runner_execution" in content
    assert "Runner is executing" in content
    assert "stream=system" in content


def test_materialization_receipt_counts_are_exposed_as_observability(tmp_path: Path) -> None:
    execution_root = tmp_path / "execution"
    receipt = execution_root / "materializations" / "003-s2t" / "materialization-result.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "materialization_id": "sql-target-source-mapping",
                "output": {
                    "counts": {
                        "sql_target_source_mapping": 930,
                        "sql_target_source_mapping_gap": 945,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    manager = object.__new__(JobManager)
    captured: list[tuple[str, str | None]] = []

    async def fake_append(_job_id, _level, _stream, message, stage):
        captured.append((message, stage))

    manager._append_log = fake_append  # type: ignore[method-assign]
    asyncio.run(manager._log_materialization_summaries("job-1", execution_root))
    assert captured == [
        (
            "Materialization sql-target-source-mapping counts: "
            "sql_target_source_mapping=930, sql_target_source_mapping_gap=945",
            "runner_execution",
        )
    ]


def test_duration_format_is_compact_and_stable() -> None:
    assert JobManager._format_duration(4.25) == "4.2s"
    assert JobManager._format_duration(91) == "1m 31s"
    assert JobManager._format_duration(3670) == "1h 01m 10s"


def test_run_log_mirror_failure_does_not_break_canonical_job_log(tmp_path: Path, monkeypatch) -> None:
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    entry = JobLogEntry(
        sequence=7,
        timestamp="2026-08-12T07:00:00Z",
        level=LogLevel.INFO,
        stream=LogStream.SYSTEM,
        stage="runner_execution",
        message="canonical log survives",
    )

    class Store:
        def append_log(self, *_args, **_kwargs):
            return entry

        def append_event(self, *_args, **_kwargs):
            return SimpleNamespace(sequence=8)

        def get_job(self, _job_id):
            return None

    manager = object.__new__(JobManager)
    manager.settings = settings
    manager.store = Store()
    monkeypatch.setattr(
        "knowledge_control_plane.runtime.jobs.append_job_run_log",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    result = asyncio.run(
        manager._append_log("job-1", LogLevel.INFO, LogStream.SYSTEM, "canonical log survives", "runner_execution")
    )
    assert result is entry
