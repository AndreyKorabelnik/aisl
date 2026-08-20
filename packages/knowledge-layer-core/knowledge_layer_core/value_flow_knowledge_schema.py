from __future__ import annotations

VALUE_FLOW_KNOWLEDGE_DATABASE = "knowledge-layer.duckdb"
VALUE_FLOW_KNOWLEDGE_SCHEMA_VERSION = "repository_value_flow_knowledge/v1"
VALUE_FLOW_KNOWLEDGE_DDL = r"""
CREATE TABLE IF NOT EXISTS value_flow_knowledge_build (
 build_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, producer_version VARCHAR NOT NULL,
 schema_version VARCHAR NOT NULL, evidence_schema_version VARCHAR NOT NULL,
 started_at VARCHAR NOT NULL, completed_at VARCHAR, build_status VARCHAR NOT NULL,
 counts_json JSON NOT NULL, checks_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS value_flow_evidence_source (
 scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL, artifact_id VARCHAR NOT NULL,
 content_fingerprint VARCHAR NOT NULL, payload_json JSON NOT NULL,
 PRIMARY KEY(scope_id, repo_id)
);
CREATE TABLE IF NOT EXISTS value_flow_evidence_record (
 record_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
 artifact_name VARCHAR NOT NULL, local_record_id VARCHAR, occurrence_ordinal BIGINT NOT NULL,
 payload_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS repository_value_node (
 value_node_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
 occurrence_id VARCHAR NOT NULL, node_kind VARCHAR NOT NULL, operation VARCHAR, owner_ref VARCHAR,
 display_ref VARCHAR NOT NULL, type_ref VARCHAR, wire_path VARCHAR, source_path VARCHAR,
 provenance_json JSON NOT NULL, payload_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS repository_value_flow_edge (
 value_flow_edge_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, source_repo_id VARCHAR NOT NULL,
 target_repo_id VARCHAR NOT NULL, source_value_node_id VARCHAR NOT NULL, target_value_node_id VARCHAR NOT NULL,
 source_occurrence_id VARCHAR NOT NULL, target_occurrence_id VARCHAR NOT NULL, flow_kind VARCHAR NOT NULL,
 source_edge_kind VARCHAR NOT NULL, transformation_kind VARCHAR NOT NULL, naming_relation VARCHAR NOT NULL,
 value_preservation VARCHAR NOT NULL, confidence VARCHAR NOT NULL, derivation_id VARCHAR, derivation_kind VARCHAR,
 derivation_source_count INTEGER NOT NULL, guards_json JSON NOT NULL, provenance_json JSON NOT NULL, payload_json JSON NOT NULL
);

CREATE OR REPLACE VIEW repository_value_flow_edge_classified AS
SELECT *,
       CASE lower(confidence)
         WHEN 'confirmed' THEN 'confirmed'
         WHEN 'probable' THEN 'derived'
         ELSE 'candidate'
       END AS knowledge_class
FROM repository_value_flow_edge;

CREATE OR REPLACE VIEW repository_value_flow_edge_strict AS
SELECT * FROM repository_value_flow_edge_classified
WHERE knowledge_class = 'confirmed';

CREATE OR REPLACE VIEW repository_value_flow_edge_working AS
SELECT * FROM repository_value_flow_edge_classified
WHERE knowledge_class IN ('confirmed', 'derived');

CREATE OR REPLACE VIEW repository_value_flow_edge_exploratory AS
SELECT * FROM repository_value_flow_edge_classified;
"""
