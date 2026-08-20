from __future__ import annotations

OBSERVED_STORAGE_DATABASE = "knowledge-layer.duckdb"
OBSERVED_STORAGE_SCHEMA_VERSION = "observed-storage-usage/v1"
OBSERVED_STORAGE_SOURCE_SCHEMA_VERSION = "storage-usage-evidence/v1"

OBSERVED_STORAGE_DDL = r"""
CREATE TABLE observed_storage_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    source_content_fingerprint VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE observed_storage_source (
    storage_usage_source_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    artifact_path VARCHAR NOT NULL,
    source_snapshot_json JSON NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    coverage_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE observed_storage_access (
    storage_access_id VARCHAR PRIMARY KEY,
    storage_usage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    operation VARCHAR,
    operation_signature VARCHAR,
    class_name VARCHAR,
    method_name VARCHAR,
    access_kind VARCHAR NOT NULL,
    operation_kind VARCHAR,
    write_kind VARCHAR,
    mutation_kind VARCHAR,
    storage_kind VARCHAR,
    storage_target_expression VARCHAR,
    target_resolution_level VARCHAR,
    target_resolution_status VARCHAR,
    receiver_expression VARCHAR,
    receiver_declared_type VARCHAR,
    storage_method VARCHAR,
    payload_expression VARCHAR,
    payload_role VARCHAR,
    writes_new_payload BOOLEAN,
    selected_fields_json JSON NOT NULL,
    selected_field_refs_json JSON NOT NULL,
    result_type VARCHAR,
    sql_preview VARCHAR,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE observed_storage_read (
    storage_read_id VARCHAR PRIMARY KEY,
    storage_access_id VARCHAR NOT NULL,
    storage_usage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    operation VARCHAR,
    storage_target_expression VARCHAR,
    storage_kind VARCHAR,
    storage_method VARCHAR,
    selected_fields_json JSON NOT NULL,
    result_type VARCHAR,
    target_resolution_status VARCHAR,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE observed_storage_write (
    storage_write_id VARCHAR PRIMARY KEY,
    storage_access_id VARCHAR NOT NULL,
    storage_usage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    operation VARCHAR,
    storage_target_expression VARCHAR,
    storage_kind VARCHAR,
    storage_method VARCHAR,
    write_kind VARCHAR,
    mutation_kind VARCHAR,
    payload_expression VARCHAR,
    payload_role VARCHAR,
    writes_new_payload BOOLEAN,
    target_resolution_status VARCHAR,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE observed_storage_usage_gap (
    storage_usage_gap_id VARCHAR PRIMARY KEY,
    storage_usage_source_id VARCHAR NOT NULL,
    gap_code VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    details_json JSON NOT NULL,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE INDEX idx_observed_storage_access_repo_kind ON observed_storage_access(repo_id, access_kind);
CREATE INDEX idx_observed_storage_access_target ON observed_storage_access(storage_target_expression);
CREATE INDEX idx_observed_storage_read_target ON observed_storage_read(storage_target_expression);
CREATE INDEX idx_observed_storage_write_target ON observed_storage_write(storage_target_expression);
CREATE INDEX idx_observed_storage_gap_owner ON observed_storage_usage_gap(owner_kind, owner_id);
"""

OBSERVED_STORAGE_TABLES = (
    "observed_storage_build",
    "observed_storage_source",
    "observed_storage_access",
    "observed_storage_read",
    "observed_storage_write",
    "observed_storage_usage_gap",
)
