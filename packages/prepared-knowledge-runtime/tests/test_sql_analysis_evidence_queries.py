from __future__ import annotations

import json
from pathlib import Path

import pytest

from prepared_knowledge_runtime import SqlAnalysisEvidenceQuery


def _write_package(root: Path) -> tuple[Path, Path, dict[str, Path]]:
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.json"
    coverage = root / "coverage.json"
    statements = root / "sql_statement.jsonl"
    joins = root / "sql_join_edge.jsonl"
    manifest.write_text(json.dumps({
        "artifact": "sql_analysis",
        "schema_version": "sql-analysis/v1",
        "repository": {"repo_id": "repo-sql"},
        "facts": [
            {"fact_type": "sql_statement", "id_field": "statement_id"},
            {"fact_type": "sql_join_edge", "id_field": "join_edge_id"},
        ],
    }), encoding="utf-8")
    coverage.write_text(json.dumps({
        "schema_version": "sql-analysis/v1",
        "status": "complete",
        "files": 1,
    }), encoding="utf-8")
    statements.write_text(json.dumps({
        "statement_id": "stmt-1",
        "repo_id": "repo-sql",
        "kind": "select",
        "evidence": [{"relative_file": "queries/customer.sql", "line_start": 3, "line_end": 5, "extractor": "sqlglot"}],
    }) + "\n", encoding="utf-8")
    joins.write_text(json.dumps({
        "join_edge_id": "join-1",
        "repo_id": "repo-sql",
        "left_relation": "customer",
        "right_relation": "address",
        "evidence": [{"relative_file": "queries/customer.sql", "line_start": 4, "extractor": "sqlglot"}],
    }) + "\n", encoding="utf-8")
    return manifest, coverage, {"sql_statement": statements, "sql_join_edge": joins}


def test_sql_analysis_native_reader_uses_explicit_published_members(tmp_path: Path) -> None:
    manifest, coverage, fact_paths = _write_package(tmp_path / "cas-layout")
    query = SqlAnalysisEvidenceQuery(manifest_path=manifest, coverage_path=coverage, fact_paths=fact_paths)

    result = query.get_aisl_knowledge_item(item_kind="sql_statement", local_id="stmt-1")

    assert result["item"]["statement_id"] == "stmt-1"
    assert result["coverage"]["status"] == "complete"
    assert result["source_fragments"][0]["locator"] == "repo://repo-sql/queries/customer.sql#L3-L5"
    assert result["evidence"][0]["basis"] == "sql-analysis/v1:sql_statement"


def test_sql_analysis_native_reader_requires_every_manifest_shard(tmp_path: Path) -> None:
    manifest, coverage, fact_paths = _write_package(tmp_path / "cas-layout")
    fact_paths.pop("sql_join_edge")

    with pytest.raises(ValueError, match="missing fact shard: sql_join_edge"):
        SqlAnalysisEvidenceQuery(manifest_path=manifest, coverage_path=coverage, fact_paths=fact_paths)
