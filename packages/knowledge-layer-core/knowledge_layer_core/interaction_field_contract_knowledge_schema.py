from __future__ import annotations

INTERACTION_FIELD_CONTRACT_DATABASE = "knowledge-layer.duckdb"
INTERACTION_FIELD_CONTRACT_SCHEMA_VERSION = "workspace_system_interaction_field_contract/v2"

INTERACTION_FIELD_CONTRACT_DDL = r'''
CREATE TABLE IF NOT EXISTS interaction_field_contract_build (
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

CREATE TABLE IF NOT EXISTS system_interaction_field_contract (
    field_contract_id VARCHAR PRIMARY KEY,
    boundary_interaction_id VARCHAR NOT NULL,
    interaction_id VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    source_repo_id VARCHAR NOT NULL,
    outbound_interface_id VARCHAR NOT NULL,
    outbound_operation VARCHAR,
    outbound_payload_type VARCHAR,
    outbound_field_path VARCHAR NOT NULL,
    outbound_attribute_name VARCHAR,
    outbound_wire_name VARCHAR,
    outbound_field_type VARCHAR,
    outbound_source_schema VARCHAR,
    target_repo_id VARCHAR NOT NULL,
    target_ingress_interface_id VARCHAR NOT NULL,
    target_ingress_operation VARCHAR,
    target_payload_type VARCHAR,
    target_field_path VARCHAR NOT NULL,
    target_attribute_name VARCHAR,
    target_wire_name VARCHAR,
    target_field_type VARCHAR,
    target_source_schema VARCHAR,
    wire_path VARCHAR NOT NULL,
    match_kind VARCHAR NOT NULL,
    match_status VARCHAR NOT NULL,
    type_compatibility VARCHAR NOT NULL,
    provenance_json JSON NOT NULL,
    payload_json JSON NOT NULL
);
'''
