from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_layer_core import CORE_DDL
from prepared_knowledge_runtime import connect_database, write_json
from knowledge_layer_core.evidence import TOOL_IDS, execute_evidence_request, load_evidence_tool_catalog


def _scope(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    db = root / "knowledge-layer.duckdb"
    con = connect_database(db)
    con.execute(CORE_DDL)
    con.execute("""INSERT INTO workspace_build VALUES (
        'build-1', 'scope-1', 'data-model', '', 'selection', '0.9.0',
        'knowledge_layer_data_model_core/v1', current_timestamp, current_timestamp,
        'complete', '{}', '{}'
    )""")
    con.execute("""INSERT INTO workspace_repository VALUES (
        'repo-1', '', NULL, '', 'fingerprint', 'System', 'P1', '0.36.32',
        'repository-system-description.yaml', 'code_conceptual_model/v2', 'projection', '{}', '{}', '{}'
    )""")
    con.close()
    write_json(root / "knowledge-layer-manifest.json", {
        "schema_version": "knowledge_layer/v1",
        "scope_id": "scope-1",
        "scope_type": "repository",
        "repository_count": 1,
        "repository_ids": ["repo-1"],
        "database_path": "knowledge-layer.duckdb",
        "capabilities": ["common.data-model"],
    })
    return root


def test_core_evidence_catalog_is_scope_neutral_and_excludes_extensions() -> None:
    catalog = load_evidence_tool_catalog()
    assert catalog["producer"] == "knowledge-layer-core"
    assert catalog["scope"] == "knowledge-layer"
    assert "workspace_data_model_overview" in TOOL_IDS
    assert "workspace_data_model_entities" in TOOL_IDS
    assert "workspace_data_model_missing_fact_detail" in TOOL_IDS
    assert "workspace_data_model_model_relationships" not in TOOL_IDS
    overview = next(item for item in catalog["tools"] if item["command_id"] == "workspace_data_model_overview")
    assert overview["required_args"] == ["knowledge_layer_path"]
    assert overview["knowledge_layer_scoped"] is True


def test_core_evidence_executor_reads_repository_scope(tmp_path: Path) -> None:
    root = _scope(tmp_path)
    result = execute_evidence_request(
        {"command_id": "workspace_data_model_overview", "arguments": {}},
        knowledge_layer_path=root / "knowledge-layer-manifest.json",
    )
    assert result["scope_type"] == "repository"
    assert result["repositories"][0]["repo_id"] == "repo-1"


def test_core_evidence_executor_rejects_unknown_arguments(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown arguments"):
        execute_evidence_request(
            {"command_id": "workspace_data_model_entities", "arguments": {"bogus": 1}},
            knowledge_layer_path=_scope(tmp_path),
        )


def test_overview_tolerates_pipeline_pagination_transport_arguments(tmp_path: Path) -> None:
    result = execute_evidence_request(
        {"command_id": "workspace_data_model_overview", "arguments": {"max_results": 500}},
        knowledge_layer_path=_scope(tmp_path),
    )
    assert result["scope_type"] == "repository"
