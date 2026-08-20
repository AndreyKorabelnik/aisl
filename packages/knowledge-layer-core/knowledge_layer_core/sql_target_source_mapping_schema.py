from __future__ import annotations

SQL_TARGET_SOURCE_MAPPING_SCHEMA_VERSION = "sql-target-source-mapping/v2"
SQL_TARGET_SOURCE_MAPPING_DATABASE = "knowledge-layer.duckdb"

SQL_TARGET_SOURCE_MAPPING_DDL = r"""
CREATE TABLE sql_target_source_mapping_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    producer_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at VARCHAR NOT NULL,
    completed_at VARCHAR,
    counts_json JSON NOT NULL,
    checks_json JSON NOT NULL
);
CREATE TABLE sql_target_source_mapping_source (
    source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_role VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    model_kind VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    output_path VARCHAR NOT NULL
);
CREATE TABLE sql_observed_workflow_dependency (
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
CREATE TABLE sql_observed_relation_materialization (
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
-- Raw/syntactic ultimate SQL origins.  These rows preserve every supported path
-- through observed relation producers and are never rewritten by semantic
-- normalisation.
CREATE TABLE sql_target_source_mapping (
    mapping_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    workflow_target_logical_name VARCHAR NOT NULL,
    target_column VARCHAR NOT NULL,
    source_branch VARCHAR,
    source_branch_scope_id VARCHAR,
    source_branch_ordinal BIGINT,
    branch_relation_name VARCHAR,
    driver_relation_name VARCHAR,
    driver_relation_status VARCHAR NOT NULL,
    driver_relation_basis VARCHAR NOT NULL,
    driver_relation_candidates_json JSON NOT NULL,
    source_relation_role VARCHAR NOT NULL,
    source_relation_role_basis VARCHAR NOT NULL,
    root_projection_id VARCHAR,
    root_expression VARCHAR,
    local_lineage_id VARCHAR NOT NULL,
    immediate_source_column_usage_id VARCHAR,
    immediate_source_relation_id VARCHAR,
    immediate_source_relation_name VARCHAR,
    immediate_source_column VARCHAR,
    source_sql_column_usage_id VARCHAR,
    source_sql_relation_id VARCHAR,
    source_sql_relation_name VARCHAR,
    source_sql_relation_kind VARCHAR,
    source_sql_column VARCHAR,
    source_sql_file VARCHAR,
    source_usage_role VARCHAR,
    producer_hop_count BIGINT NOT NULL,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    local_transformation_path_json JSON NOT NULL,
    producer_transformation_path_json JSON NOT NULL,
    materialization_path_json JSON NOT NULL,
    workflow_dependency_path_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);
-- Product value origins.  Several raw paths may collapse into one value origin
-- only when independent typed evidence proves the equivalence.
CREATE TABLE sql_target_value_source_mapping (
    value_mapping_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    workflow_target_logical_name VARCHAR NOT NULL,
    target_column VARCHAR NOT NULL,
    source_branch VARCHAR,
    source_branch_scope_id VARCHAR,
    source_branch_ordinal BIGINT,
    branch_relation_name VARCHAR,
    driver_relation_name VARCHAR,
    driver_relation_status VARCHAR NOT NULL,
    driver_relation_basis VARCHAR NOT NULL,
    driver_relation_candidates_json JSON NOT NULL,
    source_relation_role VARCHAR NOT NULL,
    source_relation_role_basis VARCHAR NOT NULL,
    source_sql_column_usage_id VARCHAR,
    source_sql_relation_id VARCHAR,
    source_sql_relation_name VARCHAR,
    source_sql_column VARCHAR,
    source_sql_file VARCHAR,
    source_representation VARCHAR,
    normalization_kind VARCHAR NOT NULL,
    mapping_status VARCHAR NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    supporting_raw_mapping_ids_json JSON NOT NULL,
    semantic_evidence_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);
CREATE TABLE sql_target_source_mapping_gap (
    gap_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    workflow_target_logical_name VARCHAR NOT NULL,
    target_column VARCHAR,
    root_projection_id VARCHAR,
    local_lineage_id VARCHAR,
    gap_kind VARCHAR NOT NULL,
    impact VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    evidence_json JSON NOT NULL
);
CREATE INDEX idx_sql_target_source_mapping_target ON sql_target_source_mapping(repo_id, workflow_target_logical_name, target_column);
CREATE INDEX idx_sql_target_source_mapping_source ON sql_target_source_mapping(source_sql_relation_name, source_sql_column);
CREATE INDEX idx_sql_target_value_source_mapping_target ON sql_target_value_source_mapping(repo_id, workflow_target_logical_name, target_column);
CREATE INDEX idx_sql_target_value_source_mapping_source ON sql_target_value_source_mapping(source_sql_relation_name, source_sql_column);
CREATE INDEX idx_sql_relation_materialization_output ON sql_observed_relation_materialization(workflow_context_file, output_table_name);
"""

SQL_TARGET_SOURCE_MAPPING_TABLES = (
    "sql_target_source_mapping_build",
    "sql_target_source_mapping_source",
    "sql_observed_workflow_dependency",
    "sql_observed_relation_materialization",
    "sql_target_source_mapping",
    "sql_target_value_source_mapping",
    "sql_target_source_mapping_gap",
)
