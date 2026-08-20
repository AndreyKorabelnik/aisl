from __future__ import annotations

MODEL_STORAGE_DATABASE = "knowledge-layer.duckdb"
MODEL_STORAGE_SCHEMA_VERSION = "model-storage-semantics/v1"
MODEL_STORAGE_SOURCE_SCHEMA_VERSION = "model-storage-evidence/v1"

MODEL_STORAGE_DDL = r"""
CREATE TABLE model_storage_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE model_storage_source (
    model_storage_source_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    artifact_path VARCHAR NOT NULL,
    source_snapshot_json JSON NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    coverage_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE model_storage_record (
    observation_id VARCHAR PRIMARY KEY,
    model_storage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    api_framework VARCHAR,
    owner_fqcn VARCHAR,
    owner_operation VARCHAR,
    storage_alias VARCHAR,
    storage_key_field VARCHAR,
    storage_key_expression VARCHAR,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE model_storage_reference (
    observation_id VARCHAR PRIMARY KEY,
    model_storage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    api_framework VARCHAR,
    source_owner_fqcn VARCHAR,
    source_operation VARCHAR,
    source_alias VARCHAR,
    source_field VARCHAR,
    reference_operation VARCHAR,
    target_converter_operation VARCHAR,
    target_alias VARCHAR,
    target_storage_key_field VARCHAR,
    target_storage_key_expression VARCHAR,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE model_storage_key_lineage (
    observation_id VARCHAR PRIMARY KEY,
    model_storage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    api_framework VARCHAR,
    source_owner_fqcn VARCHAR,
    source_operation VARCHAR,
    source_alias VARCHAR,
    relationship_field VARCHAR,
    reference_operation VARCHAR,
    target_alias VARCHAR,
    source_key_expression VARCHAR,
    target_key_expression_template VARCHAR,
    composed_target_key_expression VARCHAR,
    source_key_passed_into_target_key BOOLEAN,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE model_storage_reference_derivation (
    observation_id VARCHAR PRIMARY KEY,
    model_storage_source_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    api_framework VARCHAR,
    source_owner_fqcn VARCHAR,
    source_operation VARCHAR,
    source_alias VARCHAR,
    relationship_field VARCHAR,
    reference_operation VARCHAR,
    value_converter_operation VARCHAR,
    composed_reference_value_expression VARCHAR,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE INDEX idx_model_storage_record_alias ON model_storage_record(storage_alias);
CREATE INDEX idx_model_storage_reference_source ON model_storage_reference(source_alias, source_field);
CREATE INDEX idx_model_storage_reference_target ON model_storage_reference(target_alias);
CREATE INDEX idx_model_storage_key_lineage_source ON model_storage_key_lineage(source_alias, relationship_field);
CREATE INDEX idx_model_storage_key_lineage_target ON model_storage_key_lineage(target_alias);
"""

MODEL_STORAGE_TABLES = (
    "model_storage_build",
    "model_storage_source",
    "model_storage_record",
    "model_storage_reference",
    "model_storage_key_lineage",
    "model_storage_reference_derivation",
)
