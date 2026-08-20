from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.logging_utils import RunLogger


def test_run_logger_writes_consumer_runtime_contract(tmp_path: Path) -> None:
    logger = RunLogger(tmp_path)
    logger.start("java_field_flow_build", "Building field flow", source_path="/private/repo", token="secret")
    logger.done("java_field_flow_build", "field_occurrences=12, field_edges=7", count=7)

    rows = [json.loads(line) for line in (tmp_path / "runtime_events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["status"] for row in rows] == ["running", "ready"]
    assert rows[0]["component"] == "code_analyzer_core"
    assert rows[0]["format"] == "framework_runtime_event"
    assert rows[0]["title"] == "Прослеживание атрибутов"
    assert rows[0]["message"].startswith("Строятся локальные")
    assert rows[0]["visibility"] == "user"
    assert "source_path" not in rows[0]["details"]
    assert "token" not in rows[0]["details"]
    assert rows[1]["details"]["count"] == 7

    progress = json.loads((tmp_path / "runtime_progress.json").read_text(encoding="utf-8"))
    assert progress["events_count"] == 2
    assert progress["latest_event"]["phase"] == "java_field_flow_build"
    assert progress["artifacts"]["runtime_events"] == "diagnostics/runtime_events.jsonl"
    assert (tmp_path / "analysis_log.jsonl").exists()
