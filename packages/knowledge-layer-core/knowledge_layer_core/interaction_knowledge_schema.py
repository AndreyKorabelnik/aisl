from __future__ import annotations

INTERACTION_KNOWLEDGE_DATABASE = "knowledge-layer.duckdb"
INTERACTION_KNOWLEDGE_SCHEMA_VERSION = "workspace_system_interaction/v6"

INTERACTION_KNOWLEDGE_DDL = r'''
CREATE TABLE IF NOT EXISTS interaction_knowledge_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    producer_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    input_schema_version VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at VARCHAR NOT NULL,
    completed_at VARCHAR,
    counts_json JSON NOT NULL,
    checks_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS interaction_repository_identity (
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    system_id VARCHAR,
    project_id VARCHAR,
    configured_service_aliases_json JSON NOT NULL,
    source_artifact_id VARCHAR NOT NULL,
    payload_json JSON NOT NULL,
    PRIMARY KEY (scope_id, repo_id)
);

CREATE TABLE IF NOT EXISTS interaction_boundary_evidence_record (
    record_occurrence_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    local_record_id VARCHAR,
    occurrence_ordinal BIGINT NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS repository_interaction_boundary (
    boundary_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    repo_id VARCHAR NOT NULL,
    system_id VARCHAR,
    project_id VARCHAR,
    configured_service_aliases_json JSON NOT NULL,
    interface_id VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    boundary_kind VARCHAR NOT NULL,
    protocol VARCHAR NOT NULL,
    operation VARCHAR,
    http_method VARCHAR,
    normalized_paths_json JSON NOT NULL,
    authorities_json JSON NOT NULL,
    service_identities_json JSON NOT NULL,
    property_identities_json JSON NOT NULL,
    base_url_property_keys_json JSON NOT NULL,
    contract_fingerprint VARCHAR,
    provenance_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS system_interaction (
    interaction_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_repo_id VARCHAR NOT NULL,
    target_repo_id VARCHAR NOT NULL,
    protocol VARCHAR NOT NULL,
    operation_count BIGINT NOT NULL,
    execution_context_count BIGINT NOT NULL,
    match_status VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL,
    boundary_interaction_ids_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS system_boundary_interaction (
    boundary_interaction_id VARCHAR PRIMARY KEY,
    interaction_id VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    source_repo_id VARCHAR NOT NULL,
    outbound_interface_id VARCHAR NOT NULL,
    outbound_operation VARCHAR,
    http_method VARCHAR,
    outbound_endpoint VARCHAR,
    target_repo_id VARCHAR NOT NULL,
    target_ingress_interface_id VARCHAR NOT NULL,
    target_ingress_operation VARCHAR,
    target_ingress_endpoint VARCHAR,
    protocol VARCHAR NOT NULL,
    match_status VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL,
    local_execution_status VARCHAR NOT NULL,
    match_basis_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS system_interaction_execution_context (
    execution_context_id VARCHAR PRIMARY KEY,
    boundary_interaction_id VARCHAR NOT NULL,
    interaction_id VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    source_repo_id VARCHAR NOT NULL,
    source_ingress_interface_id VARCHAR NOT NULL,
    source_ingress_operation VARCHAR,
    source_ingress_endpoint VARCHAR,
    outbound_interface_id VARCHAR NOT NULL,
    outbound_operation VARCHAR,
    trigger_kind VARCHAR NOT NULL,
    path_status VARCHAR NOT NULL,
    call_chain_length BIGINT NOT NULL,
    call_chain_json JSON NOT NULL,
    provenance_json JSON NOT NULL,
    payload_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS system_interaction_match_diagnostic (
    diagnostic_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    source_repo_id VARCHAR NOT NULL,
    outbound_interface_id VARCHAR NOT NULL,
    outbound_operation VARCHAR,
    protocol VARCHAR NOT NULL,
    http_method VARCHAR,
    outbound_paths_json JSON NOT NULL,
    match_status VARCHAR NOT NULL,
    confidence VARCHAR,
    candidate_matches_json JSON NOT NULL,
    payload_json JSON NOT NULL
);
'''
