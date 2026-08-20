from __future__ import annotations

LOGICAL_PHYSICAL_MAPPING_DATABASE = "knowledge-layer.duckdb"
LOGICAL_PHYSICAL_MAPPING_SCHEMA_VERSION = "logical-physical-model-mapping/v1"
LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION = "java-persistence-mapping-evidence/v1"

LOGICAL_PHYSICAL_MAPPING_DDL = r'''
CREATE TABLE logical_physical_mapping_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    evidence_schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE logical_physical_mapping_source (
    mapping_source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    evidence_artifact_id VARCHAR NOT NULL,
    evidence_content_fingerprint VARCHAR NOT NULL,
    evidence_path VARCHAR NOT NULL,
    code_declared_artifact_id VARCHAR NOT NULL,
    code_declared_content_fingerprint VARCHAR NOT NULL,
    code_declared_output_path VARCHAR NOT NULL,
    physical_model_artifact_id VARCHAR NOT NULL,
    physical_model_content_fingerprint VARCHAR NOT NULL,
    physical_model_output_path VARCHAR NOT NULL,
    evidence_coverage_json JSON NOT NULL,
    evidence_diagnostics_json JSON NOT NULL,
    source_snapshot_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_physical_entity_mapping (
    entity_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    repo_id VARCHAR,
    persistence_type_mapping_id VARCHAR NOT NULL,
    logical_type_id VARCHAR NOT NULL,
    logical_type_occurrence_id VARCHAR,
    logical_fully_qualified_name VARCHAR NOT NULL,
    persistence_kind VARCHAR NOT NULL,
    declared_catalog_name VARCHAR,
    declared_schema_name VARCHAR,
    declared_table_name VARCHAR,
    physical_model_table_id VARCHAR,
    physical_table_name VARCHAR,
    physical_table_code VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    candidate_physical_table_ids_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_physical_field_mapping (
    field_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    entity_mapping_id VARCHAR,
    repo_id VARCHAR,
    persistence_field_mapping_id VARCHAR NOT NULL,
    logical_field_id VARCHAR NOT NULL,
    logical_field_occurrence_id VARCHAR,
    logical_field_name VARCHAR NOT NULL,
    logical_owner_type_id VARCHAR NOT NULL,
    persistence_role VARCHAR NOT NULL,
    declared_column_name VARCHAR,
    declared_join_column_name VARCHAR,
    physical_model_column_id VARCHAR,
    physical_column_name VARCHAR,
    physical_column_code VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    candidate_physical_column_ids_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_physical_key_mapping (
    key_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    persistence_key_mapping_id VARCHAR NOT NULL,
    logical_type_id VARCHAR NOT NULL,
    logical_field_id VARCHAR,
    key_kind VARCHAR NOT NULL,
    declared_column_name VARCHAR,
    physical_model_table_id VARCHAR,
    physical_model_column_id VARCHAR,
    physical_model_key_id VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    diagnostics_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_physical_relationship_mapping (
    relationship_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    persistence_relationship_mapping_id VARCHAR NOT NULL,
    logical_field_id VARCHAR NOT NULL,
    source_logical_type_id VARCHAR NOT NULL,
    target_logical_type_id VARCHAR,
    source_entity_mapping_id VARCHAR,
    target_entity_mapping_id VARCHAR,
    relationship_kind VARCHAR NOT NULL,
    declared_join_column_name VARCHAR,
    declared_referenced_column_name VARCHAR,
    source_physical_table_id VARCHAR,
    target_physical_table_id VARCHAR,
    source_physical_column_id VARCHAR,
    target_physical_column_id VARCHAR,
    physical_model_relationship_id VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    diagnostics_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_physical_mapping_gap (
    mapping_gap_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    gap_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    source_ref_json JSON,
    details_json JSON NOT NULL
);

CREATE INDEX idx_lpm_entity_logical_type ON logical_physical_entity_mapping(logical_type_id);
CREATE INDEX idx_lpm_entity_physical_table ON logical_physical_entity_mapping(physical_model_table_id);
CREATE INDEX idx_lpm_field_logical_field ON logical_physical_field_mapping(logical_field_id);
CREATE INDEX idx_lpm_field_physical_column ON logical_physical_field_mapping(physical_model_column_id);
CREATE INDEX idx_lpm_gap_kind ON logical_physical_mapping_gap(gap_kind);
'''

LOGICAL_PHYSICAL_MAPPING_TABLES = (
    "logical_physical_mapping_build",
    "logical_physical_mapping_source",
    "logical_physical_entity_mapping",
    "logical_physical_field_mapping",
    "logical_physical_key_mapping",
    "logical_physical_relationship_mapping",
    "logical_physical_mapping_gap",
)
