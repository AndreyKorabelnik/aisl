from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.prepared_artifacts.sql_analysis_evidence import build_sql_analysis_evidence
from knowledge_layer_core.materialization_runtime import materialize
from prepared_knowledge_runtime.query import KnowledgeLayerQuery


def _sql_knowledge(tmp_path: Path, *, repo_id: str, sql_text: str) -> dict:
    repository = tmp_path / repo_id
    repository.mkdir()
    sql_file = repository / "load.sql"
    sql_file.write_text(sql_text, encoding="utf-8")
    evidence_root = tmp_path / f"core-{repo_id}"
    artifact = build_sql_analysis_evidence(
        repository=repository,
        files=[sql_file],
        repo_id=repo_id,
        output_root=evidence_root,
        parameters={},
    )
    envelope = evidence_root / "evidence" / "sql-analysis-evidence.json"
    envelope.parent.mkdir(parents=True, exist_ok=True)
    envelope.write_text(json.dumps(artifact), encoding="utf-8")
    result = materialize(
        {
            "schema_version": "knowledge_materialization_request/v1",
            "materialization_id": "sql-analysis",
            "scope_id": repo_id,
            "inputs": {
                "evidence_artifacts": [
                    {
                        "artifact_id": artifact["artifact_id"],
                        "artifact_kind": "sql-analysis",
                        "schema_version": "sql-analysis/v1",
                        "content_fingerprint": artifact["content_fingerprint"],
                        "location": {"kind": "file", "path": str(envelope)},
                    }
                ],
                "knowledge_artifacts": [],
            },
            "parameters": {},
        },
        tmp_path / f"knowledge-{repo_id}",
    )
    return result["knowledge_artifacts"][0]


def test_workspace_sql_catalog_composes_repository_knowledge_without_reanalysis(tmp_path: Path) -> None:
    first = _sql_knowledge(
        tmp_path,
        repo_id="repo-a",
        sql_text="insert into dm.customer select id, name from src.customer",
    )
    second = _sql_knowledge(
        tmp_path,
        repo_id="repo-b",
        sql_text="insert into dm.address select id, city from src.address",
    )

    result = materialize(
        {
            "schema_version": "knowledge_materialization_request/v1",
            "materialization_id": "workspace-sql-catalog",
            "scope_id": "workspace-a",
            "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [first, second]},
            "parameters": {},
        },
        tmp_path / "workspace",
    )

    assert result["status"] == "completed"
    assert "common.workspace-sql-catalog" in result["published_capabilities"]
    artifact = result["knowledge_artifacts"][0]
    assert artifact["model_kind"] == "workspace-sql-catalog"
    assert artifact["schema_version"] == "workspace-sql-catalog/v1"

    query = KnowledgeLayerQuery(Path(result["output"]["manifest_path"]).parent)
    repositories = query.sql_analysis_coverage()["repositories"]
    assert {item["repo_id"] for item in repositories} == {"repo-a", "repo-b"}
    catalog = query.get_workspace_sql_catalog()
    assert catalog["source_count"] == 2
    assert catalog["repository_ids"] == ["repo-a", "repo-b"]
    inventory = query.export_sql_source_inventory()
    assert {item["repo_id"] for item in inventory["items"]} == {"repo-a", "repo-b"}


def test_workspace_sql_catalog_rejects_duplicate_repository_inputs(tmp_path: Path) -> None:
    first = _sql_knowledge(
        tmp_path,
        repo_id="repo-a",
        sql_text="insert into dm.customer select id from src.customer",
    )
    duplicate = dict(first)
    duplicate["artifact_id"] = "duplicate-artifact"

    try:
        materialize(
            {
                "schema_version": "knowledge_materialization_request/v1",
                "materialization_id": "workspace-sql-catalog",
                "scope_id": "workspace-a",
                "inputs": {"evidence_artifacts": [], "knowledge_artifacts": [first, duplicate]},
                "parameters": {},
            },
            tmp_path / "workspace",
        )
    except ValueError as exc:
        assert "duplicate repository IDs" in str(exc)
    else:
        raise AssertionError("duplicate repository inputs must be rejected")
