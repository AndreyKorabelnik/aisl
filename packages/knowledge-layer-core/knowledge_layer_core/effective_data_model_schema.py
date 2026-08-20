from __future__ import annotations

EFFECTIVE_DATA_MODEL_DATABASE = "knowledge-layer.duckdb"
EFFECTIVE_DATA_MODEL_SCHEMA_VERSION = "effective-data-model/v1"
MODEL_DOMAIN_CLUSTER_VIEW_SCHEMA_VERSION = "model-domain-cluster-view/v1"

EFFECTIVE_DATA_MODEL_DDL = r'''
CREATE TABLE effective_data_model_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    domain_cluster_schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE effective_data_model_source (
    source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_role VARCHAR NOT NULL,
    model_kind VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_materialization_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    output_path VARCHAR NOT NULL,
    manifest_path VARCHAR NOT NULL,
    coverage_json JSON NOT NULL,
    metadata_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_entity (
    effective_entity_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    logical_type_id VARCHAR NOT NULL,
    logical_type_occurrence_id VARCHAR NOT NULL,
    logical_fully_qualified_name VARCHAR NOT NULL,
    logical_name VARCHAR NOT NULL,
    logical_package_name VARCHAR,
    logical_type_kind VARCHAR NOT NULL,
    persistence_kind VARCHAR,
    entity_mapping_id VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    physical_model_table_id VARCHAR,
    physical_table_name VARCHAR,
    physical_table_code VARCHAR,
    layer_status VARCHAR NOT NULL,
    source_layers_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_field (
    effective_field_id VARCHAR PRIMARY KEY,
    effective_entity_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    logical_field_id VARCHAR NOT NULL,
    logical_field_occurrence_id VARCHAR NOT NULL,
    logical_field_name VARCHAR NOT NULL,
    declared_type_expression VARCHAR NOT NULL,
    normalized_type_expression VARCHAR,
    is_inherited BOOLEAN NOT NULL,
    inherited_depth BIGINT NOT NULL,
    persistence_role VARCHAR,
    field_mapping_id VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    physical_model_column_id VARCHAR,
    physical_column_name VARCHAR,
    physical_column_code VARCHAR,
    physical_data_type VARCHAR,
    physical_mandatory BOOLEAN,
    layer_status VARCHAR NOT NULL,
    source_layers_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_key (
    effective_key_id VARCHAR PRIMARY KEY,
    effective_entity_id VARCHAR,
    repo_id VARCHAR NOT NULL,
    logical_type_id VARCHAR NOT NULL,
    logical_field_id VARCHAR,
    key_kind VARCHAR NOT NULL,
    key_mapping_id VARCHAR NOT NULL,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    physical_model_table_id VARCHAR,
    physical_model_column_id VARCHAR,
    physical_model_key_id VARCHAR,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_relationship (
    effective_relationship_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    logical_relationship_occurrence_id VARCHAR NOT NULL,
    source_effective_entity_id VARCHAR NOT NULL,
    target_effective_entity_id VARCHAR NOT NULL,
    logical_field_id VARCHAR NOT NULL,
    logical_field_occurrence_id VARCHAR NOT NULL,
    relationship_kind VARCHAR NOT NULL,
    relationship_mapping_id VARCHAR,
    mapping_status VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    source_physical_table_id VARCHAR,
    target_physical_table_id VARCHAR,
    source_physical_column_id VARCHAR,
    target_physical_column_id VARCHAR,
    physical_model_relationship_id VARCHAR,
    layer_status VARCHAR NOT NULL,
    diagnostics_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_unmapped_physical_object (
    unmapped_object_id VARCHAR PRIMARY KEY,
    object_kind VARCHAR NOT NULL,
    physical_object_id VARCHAR NOT NULL,
    parent_physical_object_id VARCHAR,
    physical_name VARCHAR,
    physical_code VARCHAR,
    reason VARCHAR NOT NULL,
    source_layers_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_gap (
    effective_gap_id VARCHAR PRIMARY KEY,
    source_layer VARCHAR NOT NULL,
    source_gap_id VARCHAR,
    gap_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR,
    owner_id VARCHAR,
    message VARCHAR NOT NULL,
    details_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE effective_data_model_coverage (
    coverage_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    metric_group VARCHAR NOT NULL,
    metric_name VARCHAR NOT NULL,
    metric_value BIGINT NOT NULL,
    details_json JSON NOT NULL
);

CREATE TABLE model_domain (
    domain_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    domain_kind VARCHAR NOT NULL,
    domain_key VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    semantic_status VARCHAR NOT NULL,
    member_effective_entity_ids_json JSON NOT NULL,
    member_physical_table_ids_json JSON NOT NULL,
    derivation_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE model_entity_cluster (
    cluster_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    cluster_kind VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    semantic_status VARCHAR NOT NULL,
    member_effective_entity_ids_json JSON NOT NULL,
    member_physical_table_ids_json JSON NOT NULL,
    relationship_ids_json JSON NOT NULL,
    derivation_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE INDEX idx_effective_entity_repo_type ON effective_data_model_entity(repo_id, logical_type_id);
CREATE INDEX idx_effective_entity_physical_table ON effective_data_model_entity(physical_model_table_id);
CREATE INDEX idx_effective_field_entity_name ON effective_data_model_field(effective_entity_id, logical_field_name);
CREATE INDEX idx_effective_field_physical_column ON effective_data_model_field(physical_model_column_id);
CREATE INDEX idx_effective_relationship_source ON effective_data_model_relationship(source_effective_entity_id);
CREATE INDEX idx_effective_relationship_target ON effective_data_model_relationship(target_effective_entity_id);
CREATE INDEX idx_effective_gap_layer_kind ON effective_data_model_gap(source_layer, gap_kind);
'''

EFFECTIVE_DATA_MODEL_TABLES = (
    "effective_data_model_build",
    "effective_data_model_source",
    "effective_data_model_entity",
    "effective_data_model_field",
    "effective_data_model_key",
    "effective_data_model_relationship",
    "effective_data_model_unmapped_physical_object",
    "effective_data_model_gap",
    "effective_data_model_coverage",
    "model_domain",
    "model_entity_cluster",
)
