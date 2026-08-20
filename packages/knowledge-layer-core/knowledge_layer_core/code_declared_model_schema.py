from __future__ import annotations

CODE_DECLARED_MODEL_DATABASE = "knowledge-layer.duckdb"
CODE_DECLARED_MODEL_SCHEMA_VERSION = "code-declared-data-model/v1"
CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION = "java-type-structure-evidence/v1"
CODE_DECLARED_MODEL_RUN_MANIFEST_SCHEMA_VERSION = "static_repository_analysis_run_manifest/v1"

CODE_DECLARED_MODEL_DDL = r'''
CREATE TABLE code_declared_model_build (
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

CREATE TABLE code_declared_model_source (
    source_occurrence_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    runner_manifest_path VARCHAR NOT NULL,
    runner_version VARCHAR,
    artifact_id VARCHAR NOT NULL,
    artifact_kind VARCHAR NOT NULL,
    artifact_schema_version VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL,
    source_snapshot_fingerprint VARCHAR NOT NULL,
    source_revision VARCHAR,
    coverage_status VARCHAR NOT NULL,
    coverage_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    artifact_json JSON NOT NULL
);

CREATE TABLE code_declared_source_unit (
    source_unit_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    source_unit_id VARCHAR NOT NULL,
    repository_relative_path VARCHAR NOT NULL,
    source_set VARCHAR,
    package_name VARCHAR,
    language VARCHAR NOT NULL,
    parse_status VARCHAR NOT NULL,
    parse_error_count BIGINT NOT NULL,
    imports_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_type (
    type_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    type_id VARCHAR NOT NULL,
    source_unit_occurrence_id VARCHAR NOT NULL,
    fully_qualified_name VARCHAR NOT NULL,
    simple_name VARCHAR NOT NULL,
    package_name VARCHAR,
    type_kind VARCHAR NOT NULL,
    enclosing_type_occurrence_id VARCHAR,
    source_set VARCHAR,
    modifier_tokens_json JSON NOT NULL,
    type_parameters_json JSON NOT NULL,
    documentation_json JSON,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_field (
    field_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    field_id VARCHAR NOT NULL,
    owner_type_occurrence_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    declared_type_expression VARCHAR NOT NULL,
    normalized_type_expression VARCHAR,
    is_static BOOLEAN NOT NULL,
    is_final BOOLEAN NOT NULL,
    initializer_present BOOLEAN,
    modifier_tokens_json JSON NOT NULL,
    documentation_json JSON,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_inheritance (
    inheritance_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    inheritance_id VARCHAR NOT NULL,
    subtype_occurrence_id VARCHAR NOT NULL,
    resolved_supertype_occurrence_id VARCHAR,
    relation_kind VARCHAR NOT NULL,
    declared_supertype_expression VARCHAR NOT NULL,
    resolution_status VARCHAR NOT NULL,
    resolved_fqcn VARCHAR,
    candidate_supertype_ids_json JSON NOT NULL,
    candidate_fqcns_json JSON NOT NULL,
    type_arguments_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_type_reference (
    type_reference_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    type_reference_id VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_occurrence_id VARCHAR NOT NULL,
    reference_role VARCHAR NOT NULL,
    declared_type_expression VARCHAR NOT NULL,
    referenced_type_token VARCHAR NOT NULL,
    resolution_status VARCHAR NOT NULL,
    resolved_type_occurrence_id VARCHAR,
    resolved_fqcn VARCHAR,
    candidate_type_ids_json JSON NOT NULL,
    candidate_fqcns_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_annotation (
    annotation_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    annotation_id VARCHAR NOT NULL,
    target_kind VARCHAR NOT NULL,
    target_occurrence_id VARCHAR NOT NULL,
    annotation_name VARCHAR NOT NULL,
    arguments_raw VARCHAR,
    structured_arguments_json JSON NOT NULL,
    resolution_status VARCHAR NOT NULL,
    resolved_annotation_type VARCHAR,
    candidate_annotation_types_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_enum_constant (
    enum_constant_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    enum_constant_id VARCHAR NOT NULL,
    owner_type_occurrence_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    arguments_raw_json JSON NOT NULL,
    source_ref_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE code_declared_effective_field (
    effective_field_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    effective_owner_type_occurrence_id VARCHAR NOT NULL,
    field_occurrence_id VARCHAR NOT NULL,
    declaring_type_occurrence_id VARCHAR NOT NULL,
    field_name VARCHAR NOT NULL,
    inherited_depth BIGINT NOT NULL,
    is_inherited BOOLEAN NOT NULL,
    derivation_kind VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE code_declared_relationship (
    relationship_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    source_type_occurrence_id VARCHAR NOT NULL,
    target_type_occurrence_id VARCHAR NOT NULL,
    field_occurrence_id VARCHAR NOT NULL,
    type_reference_occurrence_id VARCHAR NOT NULL,
    relationship_kind VARCHAR NOT NULL,
    resolution_status VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE code_declared_model_gap (
    gap_occurrence_id VARCHAR PRIMARY KEY,
    source_occurrence_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    gap_code VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR,
    owner_occurrence_id VARCHAR,
    message VARCHAR NOT NULL,
    source_refs_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE INDEX idx_code_declared_type_repo_fqcn ON code_declared_type(repo_id, fully_qualified_name);
CREATE INDEX idx_code_declared_field_owner_name ON code_declared_field(owner_type_occurrence_id, name);
CREATE INDEX idx_code_declared_inheritance_subtype ON code_declared_inheritance(subtype_occurrence_id);
CREATE INDEX idx_code_declared_effective_owner_name ON code_declared_effective_field(effective_owner_type_occurrence_id, field_name);
CREATE INDEX idx_code_declared_relationship_source ON code_declared_relationship(source_type_occurrence_id);
CREATE INDEX idx_code_declared_relationship_target ON code_declared_relationship(target_type_occurrence_id);
CREATE INDEX idx_code_declared_gap_repo_code ON code_declared_model_gap(repo_id, gap_code);
'''

CODE_DECLARED_MODEL_TABLES = (
    "code_declared_model_build",
    "code_declared_model_source",
    "code_declared_source_unit",
    "code_declared_type",
    "code_declared_field",
    "code_declared_inheritance",
    "code_declared_type_reference",
    "code_declared_annotation",
    "code_declared_enum_constant",
    "code_declared_effective_field",
    "code_declared_relationship",
    "code_declared_model_gap",
)
