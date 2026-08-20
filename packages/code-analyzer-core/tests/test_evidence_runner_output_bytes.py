from __future__ import annotations

from pathlib import Path

from code_evidence import access, commands
from code_evidence.access import execute_evidence_requests


def test_execute_evidence_requests_returns_failed_result_for_backend_exception(tmp_path: Path, monkeypatch):
    def fake_evidence_coverage(analysis_out, token="", max_results=10000):
        raise RuntimeError("backend failure")

    monkeypatch.setattr(commands, "evidence_coverage", fake_evidence_coverage)
    monkeypatch.setattr(access, "_catalog_commands", lambda: {"evidence_coverage": {"command_id": "evidence_coverage"}})

    payload = execute_evidence_requests(
        [
            {
                "request_id": "req_error",
                "reason": "exercise evidence access error capture",
                "command_id": "evidence_coverage",
                "arguments": {"static_analysis_output_path": str(tmp_path)},
            }
        ],
        static_analysis_output=tmp_path,
        max_output_chars=200,
    )

    result = payload["results"][0]
    assert result["status"] == "failed"
    assert result["execution_error"] == "backend failure"
    assert result["payload"] == {"error": "backend failure"}
    assert "backend failure" in result["stdout_preview"]
    assert result["backend"] == "evidence_access_api"
