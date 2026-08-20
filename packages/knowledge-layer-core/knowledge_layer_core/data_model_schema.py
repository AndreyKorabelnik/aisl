from __future__ import annotations

"""Scope-neutral DuckDB schema for deterministic data-model knowledge materialization.

The tables and views in this module are valid for one or many repository-evidence inputs.
Workspace-only correspondence and framework-specific relationship projections remain in
``knowledge-layer-core``.
"""

CORE_SCHEMA_VERSION = "knowledge_layer_data_model_core/v1"

CORE_TABLE_DDL = 'CREATE TABLE workspace_build (\n    build_id VARCHAR PRIMARY KEY,\n    workspace_id VARCHAR NOT NULL,\n    analysis_mode VARCHAR NOT NULL,\n    selection_manifest_path VARCHAR NOT NULL,\n    selection_fingerprint VARCHAR NOT NULL,\n    builder_version VARCHAR NOT NULL,\n    schema_version VARCHAR NOT NULL,\n    started_at TIMESTAMP NOT NULL,\n    completed_at TIMESTAMP,\n    build_status VARCHAR NOT NULL,\n    counts_json JSON,\n    checks_json JSON\n);\n\nCREATE TABLE workspace_repository (\n    repo_id VARCHAR PRIMARY KEY,\n    repository_analysis_manifest VARCHAR NOT NULL,\n    source_repository_path VARCHAR,\n    static_analysis_output VARCHAR NOT NULL,\n    analysis_fingerprint VARCHAR NOT NULL,\n    system_name VARCHAR,\n    project_code VARCHAR,\n    analyzer_version VARCHAR,\n    analysis_profile VARCHAR,\n    code_model_schema_version VARCHAR NOT NULL,\n    conceptual_model_projection_sha256 VARCHAR NOT NULL,\n    source_quality_gates_json JSON,\n    coverage_summary_json JSON,\n    provenance_json JSON\n);\n\nCREATE TABLE source_record (\n    record_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    section_name VARCHAR NOT NULL,\n    local_record_id VARCHAR,\n    occurrence_ordinal BIGINT NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_domain (\n    domain_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_domain_id VARCHAR,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    basis VARCHAR,\n    physical_asset_count BIGINT,\n    entity_count BIGINT,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_cluster (\n    cluster_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_cluster_id VARCHAR,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    cluster_basis_json JSON,\n    entity_ids_json JSON,\n    physical_asset_ids_json JSON,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_entity (\n    entity_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_entity_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    canonical_name VARCHAR,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    qualified_name VARCHAR,\n    normalized_qualified_name VARCHAR,\n    schema_name VARCHAR,\n    domain_name VARCHAR,\n    source_kind VARCHAR,\n    entity_fact_kind VARCHAR,\n    evidence_level VARCHAR,\n    name_source VARCHAR,\n    description VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_attribute (\n    attribute_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    entity_occurrence_id VARCHAR NOT NULL,\n    local_attribute_id VARCHAR,\n    occurrence_ordinal BIGINT NOT NULL,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    data_type VARCHAR,\n    nullable BOOLEAN,\n    default_value VARCHAR,\n    description VARCHAR,\n    evidence_level VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_association (\n    association_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_association_id VARCHAR NOT NULL,\n    from_local_entity_id VARCHAR,\n    to_local_entity_id VARCHAR,\n    from_entity_occurrence_id VARCHAR,\n    to_entity_occurrence_id VARCHAR,\n    from_entity_occurrence_ids_json JSON,\n    to_entity_occurrence_ids_json JSON,\n    evidence_type VARCHAR,\n    relationship_kind VARCHAR,\n    from_multiplicity VARCHAR,\n    to_multiplicity VARCHAR,\n    from_role VARCHAR,\n    to_role VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE java_type_declaration (\n    java_type_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_type_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    fqcn VARCHAR NOT NULL,\n    simple_name VARCHAR NOT NULL,\n    package_name VARCHAR,\n    class_kind VARCHAR,\n    modifiers VARCHAR,\n    is_abstract BOOLEAN,\n    annotations_json JSON NOT NULL,\n    type_parameters_json JSON NOT NULL,\n    extends_reference VARCHAR,\n    implements_json JSON NOT NULL,\n    source_path VARCHAR,\n    source_scope VARCHAR,\n    syntax_provider VARCHAR,\n    cycle_observed BOOLEAN,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE code_field_observation (\n    code_field_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_attribute_occurrence_id VARCHAR,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    owner_fqcn VARCHAR NOT NULL,\n    owner_name VARCHAR,\n    owner_kind VARCHAR,\n    field_name VARCHAR NOT NULL,\n    attribute_role VARCHAR,\n    declared_type VARCHAR,\n    raw_type VARCHAR,\n    container_kind VARCHAR,\n    element_type VARCHAR,\n    annotations_json JSON NOT NULL,\n    model_exclusion_observed BOOLEAN NOT NULL,\n    model_exclusion_annotations_json JSON NOT NULL,\n    source_path VARCHAR,\n    source_scope VARCHAR,\n    line_start BIGINT,\n    evidence_maturity_level VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE java_inheritance_observation (\n    inheritance_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_observation_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    child_fqcn VARCHAR NOT NULL,\n    child_java_type_occurrence_id VARCHAR,\n    relation_kind VARCHAR NOT NULL,\n    declared_parent_reference VARCHAR,\n    declared_parent_type VARCHAR,\n    declared_parent_type_arguments_json JSON NOT NULL,\n    resolution_kind VARCHAR NOT NULL,\n    resolved_parent_fqcn VARCHAR,\n    parent_java_type_occurrence_id VARCHAR,\n    candidate_parent_fqcns_json JSON NOT NULL,\n    source_path VARCHAR,\n    source_scope VARCHAR,\n    line_start BIGINT,\n    line_end BIGINT,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE effective_entity_field (\n    effective_field_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_effective_field_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    effective_owner_fqcn VARCHAR NOT NULL,\n    effective_owner_name VARCHAR,\n    effective_owner_kind VARCHAR,\n    effective_owner_entity_occurrence_id VARCHAR,\n    effective_owner_entity_occurrence_ids_json JSON NOT NULL,\n    field_name VARCHAR NOT NULL,\n    declared_type VARCHAR,\n    effective_type VARCHAR,\n    declaration_owner_fqcn VARCHAR,\n    declaration_java_type_occurrence_id VARCHAR,\n    association_origin VARCHAR,\n    inherited BOOLEAN NOT NULL,\n    inheritance_depth BIGINT,\n    inheritance_path_json JSON NOT NULL,\n    container_kind VARCHAR,\n    element_type VARCHAR,\n    field_annotations_json JSON NOT NULL,\n    model_exclusion_observed BOOLEAN NOT NULL,\n    model_exclusion_annotations_json JSON NOT NULL,\n    source_path VARCHAR,\n    source_scope VARCHAR,\n    syntax_provider VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE effective_entity_association (\n    effective_association_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_effective_association_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    effective_owner_fqcn VARCHAR NOT NULL,\n    effective_owner_name VARCHAR,\n    effective_owner_kind VARCHAR,\n    effective_owner_entity_occurrence_id VARCHAR,\n    effective_owner_entity_occurrence_ids_json JSON NOT NULL,\n    source_field VARCHAR NOT NULL,\n    declared_type VARCHAR,\n    effective_type VARCHAR,\n    target_type_reference VARCHAR,\n    target_type_reference_observed VARCHAR,\n    target_observed_fqcn VARCHAR,\n    target_entity_occurrence_id VARCHAR,\n    target_entity_occurrence_ids_json JSON NOT NULL,\n    target_model_kind VARCHAR,\n    target_resolution_kind VARCHAR,\n    target_candidates_json JSON NOT NULL,\n    declaration_owner_fqcn VARCHAR,\n    declaration_java_type_occurrence_id VARCHAR,\n    association_origin VARCHAR,\n    inherited BOOLEAN NOT NULL,\n    inheritance_depth BIGINT,\n    inheritance_path_json JSON NOT NULL,\n    container_kind VARCHAR,\n    element_type VARCHAR,\n    model_exclusion_observed BOOLEAN NOT NULL,\n    model_exclusion_annotations_json JSON NOT NULL,\n    evidence_maturity_level VARCHAR,\n    syntax_provider VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_generalization (\n    generalization_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_generalization_id VARCHAR,\n    parent_local_entity_id VARCHAR,\n    child_local_entity_id VARCHAR,\n    parent_entity_occurrence_id VARCHAR,\n    child_entity_occurrence_id VARCHAR,\n    parent_entity_occurrence_ids_json JSON,\n    child_entity_occurrence_ids_json JSON,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE physical_asset (\n    physical_asset_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_asset_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    asset_type VARCHAR,\n    schema_name VARCHAR,\n    name VARCHAR NOT NULL,\n    qualified_name VARCHAR,\n    normalized_qualified_name VARCHAR NOT NULL,\n    source_type VARCHAR,\n    description VARCHAR,\n    column_count BIGINT,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE physical_asset_fact (\n    physical_asset_fact_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_asset_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    physical_asset_occurrence_id VARCHAR,\n    physical_asset_occurrence_ids_json JSON,\n    schema_name VARCHAR,\n    name VARCHAR,\n    qualified_name VARCHAR,\n    normalized_qualified_name VARCHAR NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE physical_column (\n    physical_column_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    physical_asset_fact_occurrence_id VARCHAR NOT NULL,\n    local_asset_id VARCHAR NOT NULL,\n    physical_asset_occurrence_id VARCHAR,\n    normalized_asset_qualified_name VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    data_type VARCHAR,\n    nullable BOOLEAN,\n    default_value VARCHAR,\n    description VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE physical_constraint (\n    physical_constraint_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    physical_asset_fact_occurrence_id VARCHAR NOT NULL,\n    local_asset_id VARCHAR NOT NULL,\n    physical_asset_occurrence_id VARCHAR,\n    normalized_asset_qualified_name VARCHAR NOT NULL,\n    constraint_kind VARCHAR NOT NULL,\n    constraint_name VARCHAR,\n    columns_json JSON,\n    referenced_qualified_name VARCHAR,\n    referenced_columns_json JSON,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE entity_physical_mapping (\n    mapping_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_entity_id VARCHAR,\n    local_physical_asset_id VARCHAR,\n    entity_occurrence_id VARCHAR,\n    physical_asset_occurrence_id VARCHAR,\n    entity_occurrence_ids_json JSON,\n    physical_asset_occurrence_ids_json JSON,\n    fact_kind VARCHAR,\n    mapping_basis_json JSON,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE declared_value_set (\n    value_set_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_value_set_id VARCHAR,\n    name VARCHAR,\n    syntax_kind VARCHAR,\n    source_set VARCHAR,\n    entries_count BIGINT,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_dictionary_entry (\n    dictionary_entry_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_entry_id VARCHAR,\n    object_name VARCHAR,\n    attribute_name VARCHAR,\n    description VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE workspace_missing_fact (\n    gap_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_gap_id VARCHAR,\n    category VARCHAR,\n    missing_fact_kind VARCHAR,\n    required_for_operation VARCHAR,\n    description VARCHAR NOT NULL,\n    affected_entity_ids_json JSON,\n    affected_physical_asset_ids_json JSON,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE persistent_structure (\n    structure_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_structure_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    storage_kind VARCHAR,\n    storage_target VARCHAR,\n    container_kind VARCHAR,\n    container_name VARCHAR NOT NULL,\n    container_fqcn VARCHAR,\n    normalized_container_fqcn VARCHAR,\n    normalized_container_name VARCHAR NOT NULL,\n    field_count BIGINT,\n    source_scope VARCHAR,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    entity_occurrence_id VARCHAR,\n    entity_occurrence_ids_json JSON NOT NULL,\n    matching_basis_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE persistent_structure_attribute (\n    structure_attribute_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    structure_occurrence_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    name VARCHAR NOT NULL,\n    normalized_name VARCHAR NOT NULL,\n    java_field VARCHAR,\n    storage_field VARCHAR,\n    data_type VARCHAR,\n    raw_type VARCHAR,\n    attribute_role VARCHAR,\n    key_role VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_table (\n    db_table_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_table_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    table_name VARCHAR NOT NULL,\n    normalized_table_name VARCHAR NOT NULL,\n    schema_name VARCHAR,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    description VARCHAR,\n    source_type VARCHAR,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    evidence_maturity_level VARCHAR,\n    physical_asset_occurrence_id VARCHAR,\n    physical_asset_occurrence_ids_json JSON NOT NULL,\n    matching_basis_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_column (\n    db_column_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_column_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    table_name VARCHAR NOT NULL,\n    normalized_table_name VARCHAR NOT NULL,\n    schema_name VARCHAR,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    column_name VARCHAR NOT NULL,\n    normalized_column_name VARCHAR NOT NULL,\n    sql_type VARCHAR,\n    nullable BOOLEAN,\n    default_value VARCHAR,\n    description VARCHAR,\n    source_type VARCHAR,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    evidence_maturity_level VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_key (\n    db_key_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_key_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    constraint_name VARCHAR,\n    constraint_kind VARCHAR,\n    table_name VARCHAR NOT NULL,\n    normalized_table_name VARCHAR NOT NULL,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    columns_json JSON NOT NULL,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_relationship (\n    db_relationship_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_relationship_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    constraint_name VARCHAR,\n    relationship_kind VARCHAR,\n    source_table VARCHAR NOT NULL,\n    normalized_source_table VARCHAR NOT NULL,\n    source_qualified_table_name VARCHAR,\n    normalized_source_qualified_table_name VARCHAR NOT NULL,\n    source_columns_json JSON NOT NULL,\n    target_table VARCHAR NOT NULL,\n    normalized_target_table VARCHAR NOT NULL,\n    target_qualified_table_name VARCHAR,\n    normalized_target_qualified_table_name VARCHAR NOT NULL,\n    target_columns_json JSON NOT NULL,\n    source_db_table_occurrence_id VARCHAR,\n    source_db_table_occurrence_ids_json JSON NOT NULL,\n    target_db_table_occurrence_id VARCHAR,\n    target_db_table_occurrence_ids_json JSON NOT NULL,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_constraint (\n    db_constraint_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_constraint_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    constraint_name VARCHAR,\n    constraint_kind VARCHAR,\n    table_name VARCHAR NOT NULL,\n    normalized_table_name VARCHAR NOT NULL,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    column_name VARCHAR,\n    expression VARCHAR,\n    literal_values_json JSON NOT NULL,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_index (\n    db_index_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_index_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    index_name VARCHAR,\n    table_name VARCHAR NOT NULL,\n    normalized_table_name VARCHAR NOT NULL,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    columns_json JSON NOT NULL,\n    unique_index BOOLEAN,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_partitioning (\n    db_partitioning_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_partitioning_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    partition_fact_kind VARCHAR NOT NULL,\n    table_name VARCHAR,\n    normalized_table_name VARCHAR NOT NULL,\n    schema_name VARCHAR,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    partition_strategy VARCHAR,\n    partition_columns_json JSON NOT NULL,\n    partition_table_name VARCHAR,\n    partition_schema_name VARCHAR,\n    qualified_partition_table_name VARCHAR,\n    normalized_qualified_partition_table_name VARCHAR NOT NULL,\n    partition_bound_kind VARCHAR,\n    partition_bound_expression VARCHAR,\n    tablespace VARCHAR,\n    source_set VARCHAR,\n    is_test_source BOOLEAN,\n    module_name VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_sequence (\n    db_sequence_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_sequence_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    sequence_name VARCHAR,\n    normalized_sequence_name VARCHAR NOT NULL,\n    schema_name VARCHAR,\n    qualified_sequence_name VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE db_schema_trigger (\n    db_trigger_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_trigger_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    trigger_name VARCHAR,\n    table_name VARCHAR,\n    normalized_table_name VARCHAR NOT NULL,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE table_relationship_observation (\n    relationship_observation_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_observation_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    schema_version VARCHAR NOT NULL,\n    relation_kind VARCHAR NOT NULL,\n    source_kind VARCHAR NOT NULL,\n    statement_id VARCHAR,\n    query_id VARCHAR,\n    join_type VARCHAR,\n    direction VARCHAR,\n    left_local_table_id VARCHAR,\n    left_table_name VARCHAR,\n    left_schema_name VARCHAR,\n    left_qualified_table_name VARCHAR,\n    left_normalized_qualified_table_name VARCHAR NOT NULL,\n    left_unresolved_name VARCHAR,\n    left_db_table_occurrence_id VARCHAR,\n    left_db_table_occurrence_ids_json JSON NOT NULL,\n    right_local_table_id VARCHAR,\n    right_table_name VARCHAR,\n    right_schema_name VARCHAR,\n    right_qualified_table_name VARCHAR,\n    right_normalized_qualified_table_name VARCHAR NOT NULL,\n    right_unresolved_name VARCHAR,\n    right_db_table_occurrence_id VARCHAR,\n    right_db_table_occurrence_ids_json JSON NOT NULL,\n    matched_declared_keys_json JSON NOT NULL,\n    properties_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE table_relationship_column_pair (\n    pair_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    relationship_observation_occurrence_id VARCHAR NOT NULL,\n    pair_ordinal BIGINT NOT NULL,\n    predicate_ordinal BIGINT,\n    operator VARCHAR NOT NULL,\n    left_local_column_id VARCHAR,\n    left_column_name VARCHAR,\n    left_normalized_column_name VARCHAR NOT NULL,\n    left_unresolved_name VARCHAR,\n    left_db_column_occurrence_id VARCHAR,\n    left_db_column_occurrence_ids_json JSON NOT NULL,\n    right_local_column_id VARCHAR,\n    right_column_name VARCHAR,\n    right_normalized_column_name VARCHAR NOT NULL,\n    right_unresolved_name VARCHAR,\n    right_db_column_occurrence_id VARCHAR,\n    right_db_column_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE table_key_observation (\n    key_observation_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_observation_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    source_record_id VARCHAR NOT NULL,\n    schema_version VARCHAR NOT NULL,\n    key_kind VARCHAR NOT NULL,\n    source_kind VARCHAR NOT NULL,\n    local_table_id VARCHAR,\n    table_name VARCHAR,\n    schema_name VARCHAR,\n    qualified_table_name VARCHAR,\n    normalized_qualified_table_name VARCHAR NOT NULL,\n    unresolved_table_name VARCHAR,\n    db_table_occurrence_id VARCHAR,\n    db_table_occurrence_ids_json JSON NOT NULL,\n    constraint_name VARCHAR,\n    index_name VARCHAR,\n    entity_name VARCHAR,\n    observation_basis_json JSON NOT NULL,\n    properties_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE table_key_observation_column (\n    key_column_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    key_observation_occurrence_id VARCHAR NOT NULL,\n    column_ordinal BIGINT NOT NULL,\n    local_column_id VARCHAR,\n    column_name VARCHAR,\n    normalized_column_name VARCHAR NOT NULL,\n    unresolved_name VARCHAR,\n    db_column_occurrence_id VARCHAR,\n    db_column_occurrence_ids_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE data_model_local_correspondence_observation (\n    observation_id VARCHAR PRIMARY KEY,\n    observation_kind VARCHAR NOT NULL,\n    repo_id VARCHAR NOT NULL,\n    normalized_value VARCHAR NOT NULL,\n    left_object_kind VARCHAR NOT NULL,\n    left_occurrence_id VARCHAR NOT NULL,\n    right_object_kind VARCHAR NOT NULL,\n    right_occurrence_id VARCHAR NOT NULL,\n    basis_json JSON NOT NULL\n);\n\nCREATE TABLE source_inspection_request (\n    request_occurrence_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    local_request_id VARCHAR,\n    request_kind VARCHAR,\n    description VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE evidence_ref (\n    evidence_ref_id VARCHAR,\n    repo_id VARCHAR NOT NULL,\n    owner_type VARCHAR NOT NULL,\n    owner_occurrence_id VARCHAR NOT NULL,\n    file_path VARCHAR,\n    line_start BIGINT,\n    line_end BIGINT,\n    json_pointer VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE source_observation (\n    source_observation_occurrence_id VARCHAR,\n    repo_id VARCHAR NOT NULL,\n    local_observation_id VARCHAR NOT NULL,\n    occurrence_ordinal BIGINT NOT NULL,\n    fact_type VARCHAR NOT NULL,\n    name VARCHAR,\n    source_path VARCHAR,\n    line_start BIGINT,\n    line_end BIGINT,\n    extractor VARCHAR,\n    syntax_provider VARCHAR,\n    owner_fqcn VARCHAR,\n    owner_type VARCHAR,\n    owner_method VARCHAR,\n    owner_operation VARCHAR,\n    owner_kind VARCHAR,\n    owner_scope_kind VARCHAR,\n    member_name VARCHAR,\n    reference_role VARCHAR,\n    referenced_type VARCHAR,\n    resolution_kind VARCHAR,\n    resolved_fqcn VARCHAR,\n    candidate_fqcns_json JSON,\n    annotation_name VARCHAR,\n    annotation_fqcn VARCHAR,\n    annotation_resolution VARCHAR,\n    arguments_json JSON,\n    argument_count BIGINT,\n    configuration_format VARCHAR,\n    configuration_path VARCHAR,\n    parent_path VARCHAR,\n    node_kind VARCHAR,\n    scalar_value_json JSON,\n    child_count BIGINT,\n    target_method VARCHAR,\n    receiver_expression VARCHAR,\n    argument_index BIGINT,\n    source_expression VARCHAR,\n    target_variable VARCHAR,\n    assignment_kind VARCHAR,\n    target_kind VARCHAR,\n    expression_text VARCHAR,\n    input_symbols_json JSON,\n    expression_tree_json JSON,\n    nested_calls_json JSON,\n    operation_kind VARCHAR,\n    dependency_kind VARCHAR,\n    group_id VARCHAR,\n    artifact_id VARCHAR,\n    dependency_version VARCHAR,\n    dependency_scope VARCHAR,\n    coordinate VARCHAR,\n    call_observation_local_id VARCHAR,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE configuration_type_correspondence_observation (\n    observation_id VARCHAR PRIMARY KEY,\n    source_observation_occurrence_id VARCHAR NOT NULL,\n    source_repo_id VARCHAR NOT NULL,\n    configuration_path VARCHAR,\n    referenced_fqcn VARCHAR NOT NULL,\n    target_repo_id VARCHAR NOT NULL,\n    target_java_type_occurrence_id VARCHAR NOT NULL,\n    match_scope VARCHAR NOT NULL,\n    match_basis VARCHAR NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE model_object_key_observation (\n    key_observation_id VARCHAR PRIMARY KEY,\n    repo_id VARCHAR NOT NULL,\n    object_fqcn VARCHAR NOT NULL,\n    java_type_occurrence_id VARCHAR,\n    annotation_observation_occurrence_id VARCHAR NOT NULL,\n    annotation_name VARCHAR NOT NULL,\n    annotation_fqcn VARCHAR,\n    observation_basis VARCHAR NOT NULL,\n    source_path VARCHAR,\n    line_start BIGINT,\n    line_end BIGINT,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE model_object_key_member (\n    key_member_id VARCHAR PRIMARY KEY,\n    key_observation_id VARCHAR NOT NULL,\n    repo_id VARCHAR NOT NULL,\n    position BIGINT NOT NULL,\n    role_name VARCHAR NOT NULL,\n    field_name VARCHAR NOT NULL,\n    field_occurrence_id VARCHAR,\n    field_owner_fqcn VARCHAR,\n    field_resolution_kind VARCHAR NOT NULL,\n    inheritance_depth BIGINT,\n    candidate_field_occurrence_ids_json JSON NOT NULL,\n    argument_expression_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE model_embedded_field_observation (\n    embedded_field_id VARCHAR PRIMARY KEY,\n    source_repo_id VARCHAR NOT NULL,\n    source_object_fqcn VARCHAR NOT NULL,\n    source_field_occurrence_id VARCHAR NOT NULL,\n    source_field_name VARCHAR NOT NULL,\n    source_field_owner_fqcn VARCHAR NOT NULL,\n    target_type_fqcn VARCHAR NOT NULL,\n    target_java_type_occurrence_id VARCHAR,\n    cardinality VARCHAR NOT NULL,\n    source_field_inherited BOOLEAN NOT NULL,\n    source_field_inheritance_depth BIGINT NOT NULL,\n    observation_basis_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE model_relationship_candidate (\n    candidate_id VARCHAR PRIMARY KEY,\n    source_repo_id VARCHAR NOT NULL,\n    source_object_fqcn VARCHAR NOT NULL,\n    source_field_occurrence_id VARCHAR NOT NULL,\n    source_field_name VARCHAR NOT NULL,\n    source_field_owner_fqcn VARCHAR NOT NULL,\n    target_type_reference VARCHAR,\n    candidate_kind VARCHAR NOT NULL,\n    candidate_target_fqcns_json JSON NOT NULL,\n    model_exclusion_observed BOOLEAN NOT NULL,\n    model_exclusion_annotations_json JSON NOT NULL,\n    observation_basis_json JSON NOT NULL,\n    payload_json JSON NOT NULL\n);\n\nCREATE TABLE build_phase_metric (\n    build_id VARCHAR NOT NULL,\n    phase_order BIGINT NOT NULL,\n    phase_name VARCHAR NOT NULL,\n    repo_id VARCHAR,\n    started_at TIMESTAMP NOT NULL,\n    duration_seconds DOUBLE NOT NULL,\n    row_count BIGINT NOT NULL,\n    details_json JSON\n);'

CORE_VIEW_DDL = "CREATE VIEW v_data_model_entity AS\nSELECT e.*,\n       (SELECT count(*) FROM data_model_attribute a WHERE a.entity_occurrence_id=e.entity_occurrence_id) AS inline_attribute_count,\n       (SELECT count(*)\n        FROM persistent_structure ps\n        JOIN persistent_structure_attribute psa USING(structure_occurrence_id)\n        WHERE ps.entity_occurrence_id=e.entity_occurrence_id) AS persistent_structure_attribute_count\nFROM data_model_entity e;\n\nCREATE VIEW v_physical_asset AS\nSELECT p.*,\n       (SELECT count(*) FROM physical_column c\n        WHERE c.repo_id=p.repo_id AND c.local_asset_id=p.local_asset_id) AS conceptual_model_column_count,\n       (SELECT count(*) FROM physical_asset_fact f\n        WHERE f.repo_id=p.repo_id AND f.local_asset_id=p.local_asset_id) AS fact_occurrence_count,\n       (SELECT count(*) FROM db_schema_table t\n        WHERE t.physical_asset_occurrence_id=p.physical_asset_occurrence_id) AS db_table_observation_count,\n       (SELECT count(*) FROM db_schema_column c\n        JOIN db_schema_table t USING(db_table_occurrence_id)\n        WHERE t.physical_asset_occurrence_id=p.physical_asset_occurrence_id) AS db_schema_column_count\nFROM physical_asset p;\n\nCREATE VIEW v_code_field_observation AS\nSELECT code_field_occurrence_id, repo_id, local_attribute_occurrence_id, occurrence_ordinal,\n       owner_fqcn, owner_name, owner_kind, field_name, attribute_role, declared_type, raw_type,\n       container_kind, element_type, annotations_json, model_exclusion_observed,\n       model_exclusion_annotations_json, source_path, source_scope, line_start, evidence_maturity_level\nFROM code_field_observation;\n\nCREATE VIEW v_source_observation_compact AS\nSELECT source_observation_occurrence_id, repo_id, local_observation_id, occurrence_ordinal,\n       fact_type, name, source_path, line_start, line_end, extractor, syntax_provider,\n       owner_fqcn, owner_type, owner_method, owner_operation, owner_kind, owner_scope_kind,\n       member_name, reference_role, referenced_type, resolution_kind, resolved_fqcn,\n       candidate_fqcns_json, annotation_name, annotation_fqcn, annotation_resolution,\n       argument_count, configuration_format, configuration_path, parent_path, node_kind,\n       scalar_value_json, child_count, target_method, receiver_expression, argument_index,\n       source_expression, target_variable, assignment_kind, target_kind, expression_text,\n       input_symbols_json, operation_kind, dependency_kind, group_id, artifact_id,\n       dependency_version, dependency_scope, coordinate, call_observation_local_id\nFROM source_observation;\n\nCREATE VIEW v_code_annotations AS\nSELECT c.*, s.arguments_json\nFROM v_source_observation_compact c\nJOIN source_observation s USING(source_observation_occurrence_id)\nWHERE c.fact_type='code_annotation';\n\nCREATE VIEW v_configuration_entries AS\nSELECT * FROM v_source_observation_compact WHERE fact_type='configuration_entry';\n\nCREATE VIEW v_artifact_dependencies AS\nSELECT * FROM v_source_observation_compact WHERE fact_type='external_dependency';\n\nCREATE VIEW v_java_method_calls AS\nSELECT c.*, s.arguments_json\nFROM v_source_observation_compact c\nJOIN source_observation s USING(source_observation_occurrence_id)\nWHERE c.fact_type='java_method_call_observation';\n\nCREATE VIEW v_call_argument_flows AS\nSELECT * FROM v_source_observation_compact WHERE fact_type='call_argument_flow_observation';\n\nCREATE VIEW v_constructed_values AS\nSELECT * FROM v_source_observation_compact WHERE fact_type='constructed_value_observation';\n\nCREATE VIEW v_collection_mutations AS\nSELECT c.*, s.arguments_json\nFROM v_source_observation_compact c\nJOIN source_observation s USING(source_observation_occurrence_id)\nWHERE c.fact_type='collection_mutation_observation';\n\nCREATE VIEW v_type_references AS\nSELECT * FROM v_source_observation_compact WHERE fact_type='type_reference_observation';\n\nCREATE VIEW v_model_object_keys AS\nSELECT k.key_observation_id, k.repo_id, k.object_fqcn, k.java_type_occurrence_id,\n       k.annotation_observation_occurrence_id, k.annotation_name, k.annotation_fqcn,\n       k.observation_basis, k.source_path, k.line_start, k.line_end,\n       json_extract_string(t.payload_json, '$.display_name') AS display_name,\n       json_extract_string(t.payload_json, '$.description') AS description,\n       (SELECT count(*) FROM model_object_key_member m\n        WHERE m.key_observation_id=k.key_observation_id) AS member_count,\n       (SELECT count(*) FROM model_object_key_member m\n        WHERE m.key_observation_id=k.key_observation_id\n          AND m.field_resolution_kind IN ('direct_field','inherited_field')) AS resolved_member_count\nFROM model_object_key_observation k\nLEFT JOIN java_type_declaration t\n  ON t.java_type_occurrence_id=k.java_type_occurrence_id;"

CORE_DDL = "\n\n".join((CORE_TABLE_DDL, CORE_VIEW_DDL))

CORE_DATA_TABLES = (
    'workspace_repository',
    'source_record',
    'data_model_domain',
    'data_model_cluster',
    'data_model_entity',
    'data_model_attribute',
    'data_model_association',
    'java_type_declaration',
    'code_field_observation',
    'java_inheritance_observation',
    'effective_entity_field',
    'effective_entity_association',
    'data_model_generalization',
    'physical_asset',
    'physical_asset_fact',
    'physical_column',
    'physical_constraint',
    'entity_physical_mapping',
    'declared_value_set',
    'data_dictionary_entry',
    'persistent_structure',
    'persistent_structure_attribute',
    'db_schema_table',
    'db_schema_column',
    'db_schema_key',
    'db_schema_relationship',
    'db_schema_constraint',
    'db_schema_index',
    'db_schema_partitioning',
    'db_schema_sequence',
    'db_schema_trigger',
    'table_relationship_observation',
    'table_relationship_column_pair',
    'table_key_observation',
    'table_key_observation_column',
    'data_model_local_correspondence_observation',
    'workspace_missing_fact',
    'source_inspection_request',
    'evidence_ref',
    'source_observation',
    'configuration_type_correspondence_observation',
    'model_object_key_observation',
    'model_object_key_member',
    'model_embedded_field_observation',
    'model_relationship_candidate',
)
CORE_TABLES = (
    'workspace_build',
    'workspace_repository',
    'source_record',
    'data_model_domain',
    'data_model_cluster',
    'data_model_entity',
    'data_model_attribute',
    'data_model_association',
    'java_type_declaration',
    'code_field_observation',
    'java_inheritance_observation',
    'effective_entity_field',
    'effective_entity_association',
    'data_model_generalization',
    'physical_asset',
    'physical_asset_fact',
    'physical_column',
    'physical_constraint',
    'entity_physical_mapping',
    'declared_value_set',
    'data_dictionary_entry',
    'workspace_missing_fact',
    'persistent_structure',
    'persistent_structure_attribute',
    'db_schema_table',
    'db_schema_column',
    'db_schema_key',
    'db_schema_relationship',
    'db_schema_constraint',
    'db_schema_index',
    'db_schema_partitioning',
    'db_schema_sequence',
    'db_schema_trigger',
    'table_relationship_observation',
    'table_relationship_column_pair',
    'table_key_observation',
    'table_key_observation_column',
    'data_model_local_correspondence_observation',
    'source_inspection_request',
    'evidence_ref',
    'source_observation',
    'configuration_type_correspondence_observation',
    'model_object_key_observation',
    'model_object_key_member',
    'model_embedded_field_observation',
    'model_relationship_candidate',
    'build_phase_metric',
)
CORE_VIEWS = (
    'v_data_model_entity',
    'v_physical_asset',
    'v_code_field_observation',
    'v_source_observation_compact',
    'v_code_annotations',
    'v_configuration_entries',
    'v_artifact_dependencies',
    'v_java_method_calls',
    'v_call_argument_flows',
    'v_constructed_values',
    'v_collection_mutations',
    'v_type_references',
    'v_model_object_keys',
)

# Scope-neutral build-system marts. They are populated mechanically from source
# observations and do not infer module purpose, ownership, or architecture.
CORE_TABLE_DDL += """

CREATE TABLE build_project (
    project_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    project_name VARCHAR NOT NULL,
    build_system VARCHAR NOT NULL,
    root_directory VARCHAR,
    module_paths_json JSON NOT NULL,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE build_module (
    module_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    module_path VARCHAR NOT NULL,
    module_name VARCHAR,
    project_directory VARCHAR,
    build_file VARCHAR,
    build_system VARCHAR NOT NULL,
    declared_in_settings BOOLEAN,
    evidence_maturity_level VARCHAR,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE build_dependency (
    dependency_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    source_module_path VARCHAR,
    target_module_path VARCHAR,
    dependency_kind VARCHAR NOT NULL,
    configuration VARCHAR,
    dependency_scope VARCHAR,
    source_set VARCHAR,
    is_test_source BOOLEAN,
    group_id VARCHAR,
    artifact_id VARCHAR,
    dependency_version VARCHAR,
    coordinate VARCHAR,
    alias VARCHAR,
    resolution_basis VARCHAR,
    evidence_maturity_level VARCHAR,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE build_plugin (
    plugin_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    module_path VARCHAR,
    plugin_id VARCHAR NOT NULL,
    plugin_version VARCHAR,
    application_kind VARCHAR,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE build_repository_observation (
    repository_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    module_path VARCHAR,
    repository_url_expression VARCHAR,
    repository_url VARCHAR,
    evidence_maturity_level VARCHAR,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE build_source_set (
    source_set_occurrence_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    module_path VARCHAR,
    source_set VARCHAR NOT NULL,
    source_observation_occurrence_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL
);
"""

CORE_VIEW_DDL += """

CREATE VIEW v_build_module AS
SELECT m.*,
       (SELECT count(*) FROM build_dependency d WHERE d.repo_id=m.repo_id AND d.source_module_path=m.module_path) AS dependency_count,
       (SELECT count(*) FROM build_dependency d WHERE d.repo_id=m.repo_id AND d.target_module_path=m.module_path) AS dependent_count,
       (SELECT count(*) FROM build_plugin p WHERE p.repo_id=m.repo_id AND p.module_path=m.module_path) AS plugin_count
FROM build_module m;

CREATE VIEW v_build_dependency AS
SELECT d.*,
       CASE WHEN d.target_module_path IS NOT NULL THEN 'module' ELSE 'external' END AS target_kind
FROM build_dependency d;

CREATE VIEW v_external_library AS
SELECT repo_id, group_id, artifact_id, dependency_version, coordinate,
       count(*) AS declaration_count,
       list(distinct source_module_path ORDER BY source_module_path) AS source_modules,
       list(distinct configuration ORDER BY configuration) AS configurations
FROM build_dependency
WHERE target_module_path IS NULL AND coordinate IS NOT NULL
GROUP BY repo_id, group_id, artifact_id, dependency_version, coordinate;
"""

# Recompute exported schema after extending the common tables/views above.
CORE_DDL = "\n\n".join((CORE_TABLE_DDL, CORE_VIEW_DDL))
CORE_DATA_TABLES = tuple(CORE_DATA_TABLES) + (
    "build_project",
    "build_module",
    "build_dependency",
    "build_plugin",
    "build_repository_observation",
    "build_source_set",
)
CORE_TABLES = tuple(CORE_TABLES) + (
    "build_project",
    "build_module",
    "build_dependency",
    "build_plugin",
    "build_repository_observation",
    "build_source_set",
)
CORE_VIEWS = tuple(CORE_VIEWS) + (
    "v_build_module",
    "v_build_dependency",
    "v_external_library",
)
