from __future__ import annotations

from pathlib import Path


def test_pinned_execution_result_schema_matches_runner_owner() -> None:
    api_schema = Path(__file__).parents[1] / "knowledge_api" / "schemas" / "knowledge_execution_result_v2.schema.json"
    runner_schema = Path(__file__).parents[2] / "static-analysis-runner" / "schemas" / "knowledge_execution_result_v2.schema.json"
    assert api_schema.read_bytes() == runner_schema.read_bytes()
