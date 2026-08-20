from __future__ import annotations

from pathlib import Path

from knowledge_layer_core import CORE_DDL
from prepared_knowledge_runtime import KnowledgeLayerQuery, connect_database, write_json


def _create_empty_scope(tmp_path: Path, *, repository_count: int = 1) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    database = root / "knowledge-layer.duckdb"
    connection = connect_database(database)
    connection.execute(CORE_DDL)
    connection.execute(
        """INSERT INTO workspace_build VALUES (
            'build-1', 'scope-1', 'data-model', '', 'selection', '0.7.0',
            'knowledge_layer_data_model_core/v1', current_timestamp, current_timestamp,
            'complete', '{}', '{}'
        )"""
    )
    for index in range(repository_count):
        repo_id = f"repo-{index + 1}"
        connection.execute(
            """INSERT INTO workspace_repository VALUES (
                ?, '', NULL, '', ?, ?, ?, '0.36.32', 'repository-system-description.yaml',
                'code_conceptual_model/v2', ?, '{}', '{}', '{}'
            )""",
            [repo_id, f"fingerprint-{index}", f"System {index + 1}", f"P{index + 1}", f"projection-{index}"],
        )
    connection.close()
    write_json(
        root / "knowledge-layer-manifest.json",
        {
            "schema_version": "knowledge_layer/v1",
            "artifact_id": "knowledge-layer",
            "scope_id": "scope-1",
            "scope_type": "repository" if repository_count == 1 else "workspace",
            "repository_count": repository_count,
            "repository_ids": [f"repo-{index + 1}" for index in range(repository_count)],
            "database_path": "knowledge-layer.duckdb",
        },
    )
    return root


def test_query_opens_scope_neutral_artifact_and_reports_capabilities(tmp_path: Path) -> None:
    root = _create_empty_scope(tmp_path)
    query = KnowledgeLayerQuery(root)

    assert query.database_path == root / "knowledge-layer.duckdb"
    assert query.manifest()["scope_type"] == "repository"
    assert "common.data-model" in query.capabilities()
    assert "workspace.cross-repository" not in query.capabilities()
    overview = query.get_overview()
    assert overview["scope_type"] == "repository"
    assert overview["repositories"][0]["repo_id"] == "repo-1"


def test_scope_neutral_aliases_return_empty_complete_pages(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_create_empty_scope(tmp_path))

    assert query.list_entities()["kind"] == "knowledge-layer-entities"
    assert query.list_entities()["total_count"] == 0
    assert query.list_tables()["kind"] == "knowledge-layer-tables"
    assert query.list_keys()["kind"] == "knowledge-layer-keys"
    assert query.list_relationships()["kind"] == "knowledge-layer-relationships"
    assert query.search_source_observations()["kind"] == "knowledge-layer-source-observations"
    assert query.list_gaps()["kind"] == "knowledge-layer-gaps"
    assert query.get_entity("missing")["not_found"] is True
    assert query.get_table("missing")["not_found"] is True


def test_scope_type_is_workspace_for_multiple_repositories(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_create_empty_scope(tmp_path, repository_count=2))
    assert query.get_overview()["scope_type"] == "workspace"
    assert query.repositories()["total_count"] == 2


def test_query_opens_canonical_manifest_path(tmp_path: Path) -> None:
    root = _create_empty_scope(tmp_path)
    query = KnowledgeLayerQuery(root / "knowledge-layer-manifest.json")

    assert query.artifact_root == root
    assert query.database_path == root / "knowledge-layer.duckdb"
    assert query.manifest()["scope_id"] == "scope-1"
