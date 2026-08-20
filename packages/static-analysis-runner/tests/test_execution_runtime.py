from __future__ import annotations

import json
import sys
from pathlib import Path

from static_analysis_runner.execution import run_process


def test_run_process_records_runtime_metrics(tmp_path: Path):
    log = tmp_path / "process.log"
    runtime = tmp_path / "runtime.jsonl"
    result = run_process(
        [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(0.05)"],
        log_path=log,
        runtime_diagnostics_path=runtime,
        heartbeat_interval_seconds=0.01,
    )
    assert result.returncode == 0
    assert result.elapsed_seconds is not None and result.elapsed_seconds >= 0
    assert result.pid is not None
    assert runtime.is_file()
    events = [json.loads(line) for line in runtime.read_text().splitlines()]
    assert events[0]["event"] == "process_started"
    assert events[-1]["event"] == "process_completed"
    assert events[-1]["returncode"] == 0


def test_run_process_observes_progress_file(tmp_path: Path):
    progress = tmp_path / "runtime_progress.json"
    runtime = tmp_path / "runtime.jsonl"
    script = (
        "import json,time,pathlib; "
        f"p=pathlib.Path({str(progress)!r}); "
        "p.write_text(json.dumps({'events_count':1,'phase':'scan','status':'running','updated_at':'x'})); "
        "time.sleep(0.08)"
    )
    result = run_process(
        [sys.executable, "-c", script],
        log_path=tmp_path / "process.log",
        progress_path=progress,
        runtime_diagnostics_path=runtime,
        heartbeat_interval_seconds=0.01,
    )
    assert result.returncode == 0
    events = [json.loads(line) for line in runtime.read_text().splitlines()]
    heartbeats = [item for item in events if item["event"] == "heartbeat"]
    assert any((item.get("progress") or {}).get("phase") == "scan" for item in heartbeats)
