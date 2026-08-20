from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_analyzer_core.prepared_artifacts.sql_analysis_evidence import build_sql_analysis_evidence
from code_analyzer_core.scanners.repo_scanner import scan_files

_FACT_BY_FILENAME = {
    "queries.json": "sql_statement",
    "script_statements.json": "sql_script_statement",
    "script_calls.json": "sql_script_call",
    "script_bindings.json": "sql_script_binding",
    "script_embedded_sql.json": "sql_script_embedded_sql",
    "script_invocations.json": "sql_script_invocation",
    "sql_select_scope.json": "sql_select_scope",
    "sql_relation.json": "sql_relation",
    "sql_projection.json": "sql_projection",
    "sql_column_usage.json": "sql_column_usage",
    "sql_write_target.json": "sql_write_target",
    "sql_target_projection_binding.json": "sql_target_projection_binding",
    "sql_join_edge.json": "sql_join_edge",
    "sql_direct_column_lineage.json": "sql_direct_column_lineage",
    "sql_recursive_column_lineage.json": "sql_recursive_column_lineage",
    "sql_scoped_lineage_gap.json": "sql_scoped_lineage_gap",
    "sql_semantic_placeholder.json": "sql_semantic_placeholder",
    "sql_workflow_binding.json": "sql_workflow_binding",
}


def run_sql_evidence(
    repo_path: str | Path,
    analysis_out: str | Path,
    repo_id: str,
    project_code: str = "UNKNOWN",
    system_name: str | None = None,
) -> dict[str, Any]:
    repository = Path(repo_path).resolve()
    output = Path(analysis_out).resolve()
    return build_sql_analysis_evidence(
        repository=repository,
        files=scan_files(repository),
        repo_id=repo_id,
        output_root=output,
        parameters={
            "project_code": project_code,
            "system_name": system_name or repo_id,
        },
    )


def canonical_sql_root(output: str | Path) -> Path:
    return Path(output) / "evidence" / "sql-analysis"


def read_fact(output: str | Path, fact_type: str) -> list[dict[str, Any]]:
    path = canonical_sql_root(output) / "facts" / f"{fact_type}.jsonl"
    if not path.exists():
        return []
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ordinal_fields = (
        "statement_ordinal",
        "scope_ordinal",
        "relation_ordinal",
        "projection_ordinal",
        "usage_ordinal",
        "join_ordinal",
        "branch_ordinal",
        "target_column_ordinal",
    )
    def semantic_key(item: dict[str, Any]) -> tuple[Any, ...]:
        ordinals = tuple(item.get(field) if item.get(field) is not None else 10**9 for field in ordinal_fields)
        fact_id = next((str(value) for key, value in item.items() if key.endswith("_id") and key.startswith("sql_")), "")
        return (str(item.get("file") or ""), int(item.get("line_start") or 0), str(item.get("query_id") or ""), *ordinals, fact_id)
    return sorted(rows, key=semantic_key)


def read_sql_output(path: Path) -> Any:
    """Read a canonical SQL fact by the historical test filename only.

    The mapping exists only in tests while assertions are migrated from JSON
    aggregates to sql-analysis/v1 JSONL shards. It is not part of Core runtime.
    """
    fact_type = _FACT_BY_FILENAME.get(path.name)
    if fact_type is None:
        raise AssertionError(f"test requested a non-canonical SQL output: {path}")
    output = path
    while output.name not in {"compact", "sql", "facts"} and output.parent != output:
        output = output.parent
    if output.name == "facts":
        output = output.parent
    else:
        output = output.parent
    return read_fact(output, fact_type)
