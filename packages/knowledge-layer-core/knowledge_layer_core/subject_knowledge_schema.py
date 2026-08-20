from __future__ import annotations

SUBJECT_KNOWLEDGE_DATABASE = "knowledge-layer.duckdb"
SUBJECT_KNOWLEDGE_SCHEMA_VERSION = "subject-knowledge-records/v1"

SUBJECT_KNOWLEDGE_DDL = r"""
CREATE TABLE subject_knowledge_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    materialization_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    source_content_fingerprint VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON NOT NULL,
    checks_json JSON NOT NULL
);

CREATE TABLE subject_knowledge_source (
    source_occurrence_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    materialization_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    artifact_kind VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    artifact_path VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    source_snapshot_json JSON NOT NULL,
    coverage_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

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

CREATE INDEX idx_subject_record_materialization ON subject_knowledge_record(materialization_id, repo_id);
CREATE INDEX idx_subject_record_artifact ON subject_knowledge_record(artifact_name, record_kind);
CREATE INDEX idx_subject_record_local ON subject_knowledge_record(local_record_id);
"""
