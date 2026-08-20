from __future__ import annotations

LOGICAL_STORAGE_DATABASE = "knowledge-layer.duckdb"
LOGICAL_STORAGE_SCHEMA_VERSION = "logical-storage-model-mapping/v2"

LOGICAL_STORAGE_DDL = r"""
CREATE TABLE logical_storage_mapping_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE logical_storage_mapping_source (
    mapping_source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    code_declared_artifact_id VARCHAR NOT NULL,
    code_declared_content_fingerprint VARCHAR NOT NULL,
    code_declared_output_path VARCHAR NOT NULL,
    model_storage_artifact_id VARCHAR NOT NULL,
    model_storage_content_fingerprint VARCHAR NOT NULL,
    model_storage_output_path VARCHAR NOT NULL
);

CREATE TABLE logical_storage_entity_mapping (
    entity_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    storage_observation_id VARCHAR NOT NULL,
    storage_repo_id VARCHAR NOT NULL,
    storage_alias VARCHAR NOT NULL,
    storage_key_expression VARCHAR,
    logical_repo_id VARCHAR,
    logical_type_occurrence_id VARCHAR,
    logical_fully_qualified_name VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    candidate_logical_type_ids_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_storage_relationship_mapping (
    relationship_mapping_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    storage_observation_id VARCHAR NOT NULL,
    storage_repo_id VARCHAR NOT NULL,
    storage_relation_kind VARCHAR NOT NULL,
    source_alias VARCHAR NOT NULL,
    source_field VARCHAR NOT NULL,
    target_alias VARCHAR,
    source_logical_repo_id VARCHAR,
    source_logical_type_occurrence_id VARCHAR,
    effective_field_occurrence_id VARCHAR,
    field_is_inherited BOOLEAN,
    declared_target_type_occurrence_id VARCHAR,
    declared_target_fqcn VARCHAR,
    observed_target_type_occurrence_id VARCHAR,
    observed_target_fqcn VARCHAR,
    target_alignment VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    storage_key_expression VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE logical_storage_join_semantic (
    join_semantic_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    relationship_occurrence_id VARCHAR NOT NULL,
    source_logical_repo_id VARCHAR NOT NULL,
    source_logical_type_occurrence_id VARCHAR NOT NULL,
    source_fqcn VARCHAR NOT NULL,
    source_field_occurrence_id VARCHAR NOT NULL,
    source_field VARCHAR NOT NULL,
    declared_target_type_occurrence_id VARCHAR NOT NULL,
    declared_target_fqcn VARCHAR NOT NULL,
    join_kind VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    join_readiness VARCHAR NOT NULL,
    source_reference_expressions_json JSON NOT NULL,
    target_identity_expressions_json JSON NOT NULL,
    target_key_fields_json JSON NOT NULL,
    structural_correspondences_json JSON NOT NULL,
    candidate_count BIGINT NOT NULL,
    basis_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL
);

CREATE TABLE logical_storage_mapping_gap (
    mapping_gap_id VARCHAR PRIMARY KEY,
    mapping_source_id VARCHAR NOT NULL,
    gap_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    details_json JSON NOT NULL
);

CREATE INDEX idx_lsm_entity_alias ON logical_storage_entity_mapping(storage_alias);
CREATE INDEX idx_lsm_relationship_source ON logical_storage_relationship_mapping(source_alias, source_field);
CREATE INDEX idx_lsm_relationship_target ON logical_storage_relationship_mapping(target_alias);
CREATE INDEX idx_lsm_relationship_logical_source ON logical_storage_relationship_mapping(source_logical_type_occurrence_id);
CREATE INDEX idx_lsm_join_source ON logical_storage_join_semantic(source_logical_type_occurrence_id, source_field);
CREATE INDEX idx_lsm_join_target ON logical_storage_join_semantic(declared_target_type_occurrence_id);
CREATE INDEX idx_lsm_join_status ON logical_storage_join_semantic(status, join_readiness);
CREATE INDEX idx_lsm_gap_kind ON logical_storage_mapping_gap(gap_kind);
"""

LOGICAL_STORAGE_TABLES = (
    "logical_storage_mapping_build",
    "logical_storage_mapping_source",
    "logical_storage_entity_mapping",
    "logical_storage_relationship_mapping",
    "logical_storage_join_semantic",
    "logical_storage_mapping_gap",
)
