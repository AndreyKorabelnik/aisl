from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime.query import KnowledgeLayerQuery


_REQUIRED = (
    "repository_inventory_build", "repository_inventory_source", "repository_inventory_identity",
    "repository_inventory_file", "repository_inventory_extension", "repository_inventory_technology",
    "repository_inventory_interface", "repository_inventory_structural_family",
    "repository_inventory_candidate", "repository_inventory_completeness", "repository_inventory_coverage_gap",
    "repository_inventory_diagnostic",
)


def _database(tmp_path: Path) -> Path:
    db = tmp_path / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    try:
        for name in _REQUIRED:
            con.execute(f"CREATE TABLE {name}(dummy VARCHAR)")
        con.execute(
            "CREATE TABLE repository_inventory_source_occurrence(" 
            "occurrence_id VARCHAR, scope_id VARCHAR, repo_id VARCHAR, repository_relative_path VARCHAR, "
            "localization_kind VARCHAR, line_start BIGINT, line_end BIGINT, content_sha256 VARCHAR, provenance_json JSON)"
        )
        con.execute(
            "CREATE TABLE repository_inventory_object_occurrence(" 
            "link_id VARCHAR, scope_id VARCHAR, repo_id VARCHAR, object_kind VARCHAR, object_id VARCHAR, "
            "occurrence_id VARCHAR, linkage_role VARCHAR, basis_json JSON)"
        )
        con.execute(
            "INSERT INTO repository_inventory_source_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["occ-1", "scope", "repo", "src/Foo.java", "declaration", 10, 20, "a" * 64,
             json.dumps([{"source_artifact_kind": "java-type-structure-evidence"}])],
        )
        con.execute(
            "INSERT INTO repository_inventory_object_occurrence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["link-1", "scope", "repo", "structural_family", "family-1", "occ-1", "observed_family_occurrence", json.dumps({"evidence_refs": ["ev-1"]})],
        )
    finally:
        con.close()
    return db


def test_source_occurrence_list_filters_by_knowledge_object(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery.from_database(_database(tmp_path))
    page = query.list_repository_inventory_source_occurrences(object_kind="structural_family", object_id="family-1")
    assert page["total_count"] == 1
    assert page["items"][0]["occurrence_id"] == "occ-1"
    assert page["items"][0]["repository_relative_path"] == "src/Foo.java"
    assert page["items"][0]["provenance_json"][0]["source_artifact_kind"] == "java-type-structure-evidence"


def test_source_occurrence_detail_preserves_reverse_links(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery.from_database(_database(tmp_path))
    detail = query.get_repository_inventory_source_occurrence("occ-1")
    assert detail is not None
    assert detail["schema_version"] == "repository-source-occurrence-query/v1"
    assert detail["occurrence"]["localization_kind"] == "declaration"
    assert detail["object_links"][0]["object_kind"] == "structural_family"
    assert detail["object_links"][0]["basis_json"]["evidence_refs"] == ["ev-1"]
    assert query.get_repository_inventory_source_occurrence("missing") is None
