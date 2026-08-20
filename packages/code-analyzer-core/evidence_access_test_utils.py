from __future__ import annotations

from pathlib import Path
from typing import Any

from code_evidence.access import execute_evidence_request
from code_evidence.catalog import load_evidence_tool_catalog


def evidence_tool_ids() -> set[str]:
    catalog = load_evidence_tool_catalog()
    return {str(item.get("command_id")) for item in (catalog.get("tools") or catalog.get("commands") or []) if item.get("command_id")}


def assert_evidence_tool_registered(command_id: str) -> None:
    assert command_id in evidence_tool_ids()


def run_evidence_tool(
    command_id: str,
    *,
    analysis_out: Path | None = None,
    llm_out: Path | None = None,
    **arguments: Any,
) -> dict[str, Any]:
    return execute_evidence_request(
        {"command_id": command_id, "arguments": arguments},
        static_analysis_output=analysis_out,
        llm_analysis_output=llm_out,
    )
