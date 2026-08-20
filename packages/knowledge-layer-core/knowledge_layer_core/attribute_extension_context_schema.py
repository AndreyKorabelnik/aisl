from __future__ import annotations

ATTRIBUTE_EXTENSION_CONTEXT_DATABASE = "knowledge-layer.duckdb"
ATTRIBUTE_EXTENSION_CONTEXT_SCHEMA_VERSION = "data-model-attribute-extension-context/v1"

ATTRIBUTE_EXTENSION_CONTEXT_DDL = r'''
CREATE TABLE attribute_extension_context_build (
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

CREATE TABLE attribute_extension_context_source (
    source_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_role VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    output_path VARCHAR NOT NULL
);

CREATE TABLE attribute_extension_object_anchor (
    anchor_id VARCHAR PRIMARY KEY,
    logical_type_occurrence_id VARCHAR NOT NULL,
    logical_fully_qualified_name VARCHAR NOT NULL,
    storage_aliases_json JSON NOT NULL,
    storage_key_fields_json JSON NOT NULL,
    storage_key_expressions_json JSON NOT NULL,
    observed_sql_relations_json JSON NOT NULL,
    observed_field_usages_json JSON NOT NULL,
    observed_sql_projections_json JSON NOT NULL,
    observed_sql_joins_json JSON NOT NULL,
    physical_candidates_json JSON NOT NULL,
    knowledge_class VARCHAR NOT NULL,
    basis_json JSON NOT NULL,
    provenance_json JSON NOT NULL
);

CREATE TABLE attribute_extension_join_semantic (
    join_semantic_id VARCHAR PRIMARY KEY,
    source_repo_id VARCHAR NOT NULL,
    source_type_occurrence_id VARCHAR NOT NULL,
    source_fqcn VARCHAR NOT NULL,
    source_field_occurrence_id VARCHAR NOT NULL,
    source_field VARCHAR NOT NULL,
    declared_type_expression VARCHAR,
    target_type_occurrence_id VARCHAR NOT NULL,
    target_fqcn VARCHAR NOT NULL,
    relationship_kind VARCHAR NOT NULL,
    cardinality VARCHAR NOT NULL,
    target_alignment VARCHAR NOT NULL,
    polymorphic BOOLEAN NOT NULL,
    concrete_targets_json JSON NOT NULL,
    join_method VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL,
    sql_generation_status VARCHAR NOT NULL,
    source_reference_expressions_json JSON NOT NULL,
    target_key_fields_json JSON NOT NULL,
    target_key_expressions_json JSON NOT NULL,
    source_parent_key_expressions_json JSON NOT NULL,
    child_key_expressions_json JSON NOT NULL,
    structural_correspondences_json JSON NOT NULL,
    source_sql_anchor_json JSON NOT NULL,
    target_sql_anchor_json JSON NOT NULL,
    observed_sql_join_examples_json JSON NOT NULL,
    physical_candidates_json JSON NOT NULL,
    basis_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL
);

CREATE TABLE attribute_extension_context_gap (
    gap_id VARCHAR PRIMARY KEY,
    gap_kind VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    owner_kind VARCHAR NOT NULL,
    owner_id VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    details_json JSON NOT NULL
);

CREATE INDEX idx_attr_ext_anchor_fqcn ON attribute_extension_object_anchor(logical_fully_qualified_name);
CREATE INDEX idx_attr_ext_join_source ON attribute_extension_join_semantic(source_fqcn, source_field);
CREATE INDEX idx_attr_ext_join_target ON attribute_extension_join_semantic(target_fqcn);
CREATE INDEX idx_attr_ext_join_method ON attribute_extension_join_semantic(join_method);
CREATE INDEX idx_attr_ext_gap_kind ON attribute_extension_context_gap(gap_kind);
'''

ATTRIBUTE_EXTENSION_CONTEXT_TABLES = (
    "attribute_extension_context_build",
    "attribute_extension_context_source",
    "attribute_extension_object_anchor",
    "attribute_extension_join_semantic",
    "attribute_extension_context_gap",
)
