from __future__ import annotations

from pathlib import Path

from evidence_access_test_utils import assert_evidence_tool_registered, run_evidence_tool
import json


def _sample_llm_out(tmp_path: Path) -> Path:
    llm_out = tmp_path / "llm-out"
    it = llm_out / "iterations" / "iteration_001"
    it.mkdir(parents=True)
    (llm_out / "pipeline_summary.json").write_text(json.dumps({"final_status": "ready_to_assess", "analysis_output": str(tmp_path / "analysis-output")}), encoding="utf-8")
    (llm_out / "state.json").write_text(json.dumps({"status": "ready_to_assess"}), encoding="utf-8")
    (llm_out / "errors.jsonl").write_text('{"iteration":1,"code":"JSON_FENCE_UNWRAPPED","message":"fence"}\n', encoding="utf-8")
    (llm_out / "final_response.json").write_text(json.dumps({
        "status": "ready_to_assess",
        "findings": [{"missing_evidence": ["sample gap"], "attributes": {"sections": {"physical_tables": {"materialization_status": "compact_subset", "omitted_count": 3}}}}],
    }), encoding="utf-8")
    (llm_out / "enabled_evidence_cli.json").write_text(json.dumps({"command_count": 2, "enabled_command_ids": ["llm_run_summary"]}), encoding="utf-8")
    (it / "agent_requests.json").write_text(json.dumps({"agent_requests": [{"request_id": "req_001", "cli_command": "code-evidence evidence llm-errors --llm-out X"}]}), encoding="utf-8")
    (it / "evidence_results.json").write_text(json.dumps({"results": [{"request_id": "req_001", "status": "ok", "stdout_truncated": True}]}), encoding="utf-8")
    (it / "parsed_response.json").write_text(json.dumps({"status": "need_more_evidence", "summary": "need evidence"}), encoding="utf-8")
    (it / "response_parse_meta.json").write_text(json.dumps({"mode": "raw_json"}), encoding="utf-8")
    return llm_out


def test_llm_artifact_evidence_tools(tmp_path: Path):
    llm_out = _sample_llm_out(tmp_path)
    for command_id in [
        "llm_run_summary",
        "llm_final_response",
        "llm_errors",
        "llm_iterations",
        "llm_evidence_results",
        "llm_agent_requests",
        "llm_gaps",
        "llm_truncation_summary",
        "agent_runtime_context",
    ]:
        payload = run_evidence_tool(command_id, llm_out=llm_out, analysis_out=tmp_path / "analysis-output")
        assert "kind" in payload or "format" in payload


def test_llm_artifact_tools_are_registered():
    for command_id in ["llm_errors", "llm_run_summary", "agent_runtime_context"]:
        assert_evidence_tool_registered(command_id)
