from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery


DDL = """
CREATE TABLE subject_knowledge_record (
    record_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    materialization_id VARCHAR NOT NULL,
    artifact_name VARCHAR NOT NULL,
    record_kind VARCHAR NOT NULL,
    local_record_id VARCHAR,
    occurrence_ordinal BIGINT NOT NULL,
    search_text VARCHAR,
    payload_json JSON NOT NULL
);
"""


def _database(path: Path) -> Path:
    with duckdb.connect(str(path)) as con:
        con.execute(DDL)
        confirmed = {
            "source_to_storage_lineage_id": "s2s-1",
            "source_operation": "Demo.accept",
            "source_payload": "Request",
            "source_field": "clientId",
            "storage_target": "DEVICE_LINK",
            "storage_field": "CLIENT_ID",
            "lineage_status": "confirmed",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": "src/Demo.java", "line_start": 10, "line_end": 12, "extractor": "demo"}],
        }
        gap = {
            "storage_lineage_gap_id": "gap-1",
            "gap_kind": "storage_target_unresolved",
            "reason": "storage target was not resolved",
            "missing_links": ["physical storage"],
            "source_inspection_required": True,
            "source_inspection_request_ids": ["inspect-1"],
            "evidence": [{"file": "src/Gap.java", "line_start": 3, "line_end": 3}],
        }
        con.executemany(
            "INSERT INTO subject_knowledge_record VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("occ-s2s", "src", "demo", "repo", "persistence-lineage", "source_to_storage_lineage.json", "source_to_storage_lineage", "s2s-1", 1, "clientId DEVICE_LINK CLIENT_ID", json.dumps(confirmed)),
                ("occ-gap", "src", "demo", "repo", "persistence-lineage", "storage_lineage_gaps.json", "storage_lineage_gaps", "gap-1", 2, "storage target unresolved", json.dumps(gap)),
            ],
        )
    return path


def test_exact_persistence_lineage_item_preserves_evidence_without_cross_product_guess(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_database(tmp_path / "knowledge-layer.duckdb"))
    result = query.get_aisl_knowledge_item(
        model_kind="persistence-lineage",
        item_kind="source_to_storage_lineage",
        local_id="s2s-1",
    )
    assert result["item"]["source_field"] == "clientId"
    assert result["item"]["storage_target"] == "DEVICE_LINK"
    assert result["item"]["storage_field"] == "CLIENT_ID"
    assert result["issues"] == []
    assert result["evidence"][0]["evidence_kind"] == "observed_source"
    assert result["source_fragments"][0]["locator"] == "src/Demo.java:10-12"
    assert "correspondence" not in result


def test_persistence_lineage_gap_remains_explicit_issue(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_database(tmp_path / "knowledge-layer.duckdb"))
    result = query.get_aisl_knowledge_item(
        model_kind="persistence-lineage",
        item_kind="storage_lineage_gap",
        local_id="gap-1",
    )
    assert result["issues"][0]["kind"] == "missing_information"
    assert result["issues"][0]["details"]["source_inspection_required"] is True
    assert result["issues"][0]["details"]["missing_links"] == ["physical storage"]


def test_unknown_persistence_lineage_item_kind_is_explicitly_unsupported(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_database(tmp_path / "knowledge-layer.duckdb"))
    result = query.get_aisl_knowledge_item(
        model_kind="persistence-lineage",
        item_kind="invented",
        local_id="x",
    )
    assert result["unsupported"] is True
    assert "source_to_storage_lineage" in result["supported_item_kinds"]
