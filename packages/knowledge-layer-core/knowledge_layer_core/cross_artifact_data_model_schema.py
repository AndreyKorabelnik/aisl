from __future__ import annotations

CROSS_ARTIFACT_DATABASE = "knowledge-layer.duckdb"
CROSS_ARTIFACT_SCHEMA_VERSION = "cross-artifact-data-model-mapping/v6"

CROSS_ARTIFACT_DDL = r'''
CREATE TABLE cross_artifact_mapping_build (
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

CREATE TABLE cross_artifact_mapping_source (
    source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_role VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    output_path VARCHAR NOT NULL
);

CREATE TABLE cross_artifact_storage_sql_mapping (
    mapping_id VARCHAR PRIMARY KEY,
    storage_alias VARCHAR NOT NULL,
    logical_type_occurrence_id VARCHAR,
    logical_fully_qualified_name VARCHAR,
    sql_relation_id VARCHAR NOT NULL,
    sql_repo_id VARCHAR NOT NULL,
    sql_relation_name VARCHAR,
    sql_logical_name VARCHAR NOT NULL,
    sql_usage_role VARCHAR,
    representation_variant VARCHAR NOT NULL,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_logical_field_sql_usage (
    mapping_id VARCHAR PRIMARY KEY,
    logical_type_occurrence_id VARCHAR NOT NULL,
    logical_fully_qualified_name VARCHAR,
    effective_field_occurrence_id VARCHAR NOT NULL,
    logical_field_name VARCHAR NOT NULL,
    sql_column_usage_id VARCHAR NOT NULL,
    sql_relation_id VARCHAR NOT NULL,
    sql_query_id VARCHAR NOT NULL,
    sql_file VARCHAR NOT NULL,
    sql_column_name VARCHAR NOT NULL,
    sql_usage_role VARCHAR,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_workflow_projection_physical_mapping (
    mapping_id VARCHAR PRIMARY KEY,
    workflow_context_file VARCHAR NOT NULL,
    target_table_code VARCHAR NOT NULL,
    physical_model_table_id VARCHAR NOT NULL,
    physical_model_column_id VARCHAR NOT NULL,
    physical_column_code VARCHAR NOT NULL,
    transform_sql_file VARCHAR NOT NULL,
    transform_query_id VARCHAR NOT NULL,
    projection_id VARCHAR NOT NULL,
    projection_output_name VARCHAR NOT NULL,
    projection_expression VARCHAR,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_workflow_dependency (
    dependency_id VARCHAR PRIMARY KEY,
    producer_workflow_context_file VARCHAR NOT NULL,
    consumer_workflow_context_file VARCHAR NOT NULL,
    entity_identity VARCHAR NOT NULL,
    producer_entity_expression VARCHAR NOT NULL,
    consumer_trigger_expression VARCHAR NOT NULL,
    resolution_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_relation_materialization (
    materialization_id VARCHAR PRIMARY KEY,
    workflow_context_file VARCHAR NOT NULL,
    materialization_kind VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_fact_id VARCHAR NOT NULL,
    source_symbol VARCHAR,
    query_file VARCHAR,
    query_id VARCHAR,
    source_table_name VARCHAR,
    output_table_name VARCHAR NOT NULL,
    resolution_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_target_source_mapping (
    mapping_id VARCHAR PRIMARY KEY,
    workflow_context_file VARCHAR NOT NULL,
    target_table_code VARCHAR NOT NULL,
    physical_model_table_id VARCHAR NOT NULL,
    physical_model_column_id VARCHAR NOT NULL,
    target_column VARCHAR NOT NULL,
    transform_sql_file VARCHAR NOT NULL,
    transform_query_id VARCHAR NOT NULL,
    target_projection_id VARCHAR NOT NULL,
    target_projection_expression VARCHAR,
    source_sql_column_usage_id VARCHAR,
    source_sql_relation_id VARCHAR NOT NULL,
    source_sql_relation_name VARCHAR NOT NULL,
    source_sql_relation_kind VARCHAR NOT NULL,
    source_sql_column VARCHAR NOT NULL,
    source_sql_file VARCHAR NOT NULL,
    source_usage_role VARCHAR,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    projection_path_json JSON NOT NULL,
    transformation_path_json JSON NOT NULL,
    materialization_path_json JSON NOT NULL,
    workflow_dependency_path_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_value_origin_physical_lineage (
    lineage_id VARCHAR PRIMARY KEY,
    origin_kind VARCHAR NOT NULL,
    origin_identity VARCHAR NOT NULL,
    logical_type_occurrence_id VARCHAR,
    logical_fully_qualified_name VARCHAR,
    effective_field_occurrence_id VARCHAR,
    logical_field_name VARCHAR,
    storage_alias VARCHAR,
    storage_key_field VARCHAR,
    storage_key_expression VARCHAR,
    source_sql_column_usage_id VARCHAR,
    source_sql_relation_id VARCHAR,
    source_sql_file VARCHAR NOT NULL,
    source_sql_column_name VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    target_table_code VARCHAR NOT NULL,
    physical_model_table_id VARCHAR NOT NULL,
    physical_model_column_id VARCHAR NOT NULL,
    physical_column_code VARCHAR NOT NULL,
    transform_sql_file VARCHAR NOT NULL,
    transform_query_id VARCHAR NOT NULL,
    target_projection_id VARCHAR NOT NULL,
    target_projection_expression VARCHAR,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    origin_semantics_json JSON NOT NULL,
    projection_path_json JSON NOT NULL,
    materialization_path_json JSON NOT NULL,
    workflow_dependency_path_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_sql_physical_mapping (
    mapping_id VARCHAR PRIMARY KEY,
    sql_object_kind VARCHAR NOT NULL,
    sql_object_id VARCHAR NOT NULL,
    sql_repo_id VARCHAR NOT NULL,
    sql_name VARCHAR NOT NULL,
    sql_context VARCHAR,
    physical_model_table_id VARCHAR NOT NULL,
    physical_table_name VARCHAR,
    physical_table_code VARCHAR NOT NULL,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE cross_artifact_mapping_gap (
    gap_id VARCHAR PRIMARY KEY,
    gap_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    details_json JSON NOT NULL
);

CREATE INDEX idx_cross_storage_sql_alias ON cross_artifact_storage_sql_mapping(storage_alias);
CREATE INDEX idx_cross_storage_sql_relation ON cross_artifact_storage_sql_mapping(sql_relation_id);
CREATE INDEX idx_cross_field_sql_field ON cross_artifact_logical_field_sql_usage(logical_type_occurrence_id, logical_field_name);
CREATE INDEX idx_cross_field_sql_usage ON cross_artifact_logical_field_sql_usage(sql_column_usage_id);
CREATE INDEX idx_cross_workflow_projection_target ON cross_artifact_workflow_projection_physical_mapping(target_table_code, physical_column_code);
CREATE INDEX idx_cross_workflow_projection_query ON cross_artifact_workflow_projection_physical_mapping(transform_query_id);
CREATE INDEX idx_cross_workflow_dependency_consumer ON cross_artifact_workflow_dependency(consumer_workflow_context_file);
CREATE INDEX idx_cross_workflow_dependency_producer ON cross_artifact_workflow_dependency(producer_workflow_context_file);
CREATE INDEX idx_cross_relation_materialization_output ON cross_artifact_relation_materialization(output_table_name);
CREATE INDEX idx_cross_relation_materialization_query ON cross_artifact_relation_materialization(query_id);
CREATE INDEX idx_cross_target_source_target ON cross_artifact_target_source_mapping(target_table_code, target_column);
CREATE INDEX idx_cross_target_source_source ON cross_artifact_target_source_mapping(source_sql_relation_name, source_sql_column);
CREATE INDEX idx_cross_value_origin_kind ON cross_artifact_value_origin_physical_lineage(origin_kind);
CREATE INDEX idx_cross_value_origin_field ON cross_artifact_value_origin_physical_lineage(logical_type_occurrence_id, logical_field_name);
CREATE INDEX idx_cross_value_origin_storage ON cross_artifact_value_origin_physical_lineage(storage_alias, storage_key_field);
CREATE INDEX idx_cross_value_origin_target ON cross_artifact_value_origin_physical_lineage(target_table_code, physical_column_code);
CREATE INDEX idx_cross_sql_physical_code ON cross_artifact_sql_physical_mapping(physical_table_code);
CREATE INDEX idx_cross_gap_kind ON cross_artifact_mapping_gap(gap_kind);
'''

CROSS_ARTIFACT_TABLES = (
    "cross_artifact_mapping_build",
    "cross_artifact_mapping_source",
    "cross_artifact_storage_sql_mapping",
    "cross_artifact_logical_field_sql_usage",
    "cross_artifact_workflow_projection_physical_mapping",
    "cross_artifact_workflow_dependency",
    "cross_artifact_relation_materialization",
    "cross_artifact_target_source_mapping",
    "cross_artifact_value_origin_physical_lineage",
    "cross_artifact_sql_physical_mapping",
    "cross_artifact_mapping_gap",
)
