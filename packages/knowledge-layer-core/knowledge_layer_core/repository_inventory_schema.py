from __future__ import annotations

REPOSITORY_INVENTORY_DATABASE = "knowledge-layer.duckdb"
REPOSITORY_INVENTORY_SCHEMA_VERSION = "repository-inventory/v5"

REPOSITORY_INVENTORY_DDL = r"""
CREATE TABLE repository_inventory_build (
    build_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL, schema_version VARCHAR NOT NULL, build_status VARCHAR NOT NULL,
    evaluation_phase VARCHAR NOT NULL, evaluation_basis_json JSON NOT NULL,
    started_at TIMESTAMP NOT NULL, completed_at TIMESTAMP,
    counts_json JSON NOT NULL, checks_json JSON NOT NULL
);
CREATE TABLE repository_inventory_source (
    source_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    artifact_id VARCHAR NOT NULL, artifact_kind VARCHAR NOT NULL, schema_version VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL, artifact_path VARCHAR NOT NULL, coverage_json JSON NOT NULL, diagnostics_json JSON NOT NULL
);
CREATE TABLE repository_inventory_identity (
    scope_id VARCHAR NOT NULL, repo_id VARCHAR PRIMARY KEY, repository_id VARCHAR, repository_name VARCHAR,
    source_kind VARCHAR, repository_url VARCHAR, default_branch VARCHAR, source_metadata_json JSON NOT NULL
);
CREATE TABLE repository_inventory_file (
    file_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    repository_relative_path VARCHAR NOT NULL, file_name VARCHAR NOT NULL, extension VARCHAR NOT NULL,
    byte_size BIGINT, sha256 VARCHAR, readable BOOLEAN NOT NULL, analyzer_eligible BOOLEAN NOT NULL,
    analyzer_frontier_status VARCHAR NOT NULL, source_artifact_id VARCHAR NOT NULL
);
CREATE TABLE repository_inventory_extension (
    extension_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    extension VARCHAR NOT NULL, file_count BIGINT NOT NULL, analyzer_eligible_file_count BIGINT NOT NULL,
    outside_analyzer_frontier_file_count BIGINT NOT NULL, source_artifact_id VARCHAR NOT NULL
);
CREATE TABLE repository_inventory_technology (
    technology_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    category VARCHAR NOT NULL, technology VARCHAR NOT NULL, status VARCHAR NOT NULL,
    confidence VARCHAR NOT NULL, basis_json JSON NOT NULL
);
CREATE TABLE repository_inventory_interface (
    interface_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    direction VARCHAR NOT NULL, boundary_kind VARCHAR, protocol VARCHAR, operation VARCHAR,
    endpoint_or_topic VARCHAR, http_method VARCHAR, peer_system VARCHAR, peer_resolution_status VARCHAR NOT NULL,
    evidence_status VARCHAR NOT NULL, source_artifact_id VARCHAR NOT NULL, basis_json JSON NOT NULL
);
CREATE TABLE repository_inventory_structural_family (
    family_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    family_kind VARCHAR NOT NULL, family_label VARCHAR NOT NULL, source_artifact_kind VARCHAR,
    source_schema_version VARCHAR, occurrence_count BIGINT NOT NULL, structural_salience_score DOUBLE NOT NULL,
    discovery_kind VARCHAR NOT NULL, discovery_basis_json JSON NOT NULL,
    observed_metrics_json JSON NOT NULL, evidence_refs_json JSON NOT NULL
);
CREATE TABLE repository_inventory_structural_member (
    member_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    family_id VARCHAR NOT NULL, source_member_id VARCHAR NOT NULL, repository_relative_path VARCHAR NOT NULL,
    content_sha256 VARCHAR, syntax VARCHAR NOT NULL, parse_status VARCHAR NOT NULL,
    structure_signature VARCHAR NOT NULL, variant_signature VARCHAR, variant_roles_json JSON NOT NULL,
    structural_size_json JSON NOT NULL, minority_states_json JSON NOT NULL, cardinality_extremes_json JSON NOT NULL,
    observation_truncated BOOLEAN NOT NULL, provenance_json JSON NOT NULL
);
CREATE TABLE repository_inventory_candidate (
    candidate_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    family_id VARCHAR NOT NULL, family_kind VARCHAR NOT NULL, structural_salience_score DOUBLE NOT NULL,
    discovery_kind VARCHAR NOT NULL, basis_json JSON NOT NULL
);
CREATE TABLE repository_inventory_completeness (
    completeness_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    subject_kind VARCHAR NOT NULL, subject_id VARCHAR NOT NULL, status VARCHAR NOT NULL,
    evidence_evaluation_status VARCHAR NOT NULL, basis_json JSON NOT NULL, diagnostics_json JSON NOT NULL
);
CREATE TABLE repository_inventory_coverage_gap (
    gap_occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    gap_kind VARCHAR NOT NULL, subject_kind VARCHAR NOT NULL, subject_id VARCHAR NOT NULL,
    discovery_kind VARCHAR NOT NULL, coverage_status VARCHAR NOT NULL, relevance_status VARCHAR NOT NULL,
    family_id VARCHAR, source_artifact_id VARCHAR, localization_scope_kind VARCHAR NOT NULL,
    localization_status VARCHAR NOT NULL, evidence_refs_json JSON NOT NULL,
    diagnostics_json JSON NOT NULL, basis_json JSON NOT NULL
);

CREATE TABLE repository_inventory_source_occurrence (
    occurrence_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    repository_relative_path VARCHAR NOT NULL, localization_kind VARCHAR NOT NULL,
    line_start BIGINT, line_end BIGINT, content_sha256 VARCHAR, provenance_json JSON NOT NULL
);
CREATE TABLE repository_inventory_object_occurrence (
    link_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    object_kind VARCHAR NOT NULL, object_id VARCHAR NOT NULL, occurrence_id VARCHAR NOT NULL,
    linkage_role VARCHAR NOT NULL, basis_json JSON NOT NULL
);
CREATE TABLE repository_inventory_diagnostic (
    diagnostic_id VARCHAR PRIMARY KEY, scope_id VARCHAR NOT NULL, repo_id VARCHAR NOT NULL,
    code VARCHAR NOT NULL, severity VARCHAR NOT NULL, message VARCHAR NOT NULL, basis_json JSON NOT NULL
);
CREATE INDEX idx_repository_inventory_source_occurrence_path ON repository_inventory_source_occurrence(repo_id, repository_relative_path, line_start);
CREATE INDEX idx_repository_inventory_object_occurrence_object ON repository_inventory_object_occurrence(repo_id, object_kind, object_id);
CREATE INDEX idx_repository_inventory_object_occurrence_occurrence ON repository_inventory_object_occurrence(repo_id, occurrence_id);
CREATE INDEX idx_repository_inventory_structural_member_family ON repository_inventory_structural_member(repo_id, family_id);
CREATE INDEX idx_repository_inventory_structural_member_path ON repository_inventory_structural_member(repo_id, repository_relative_path);
CREATE INDEX idx_repository_inventory_file_extension ON repository_inventory_file(repo_id, extension);
CREATE INDEX idx_repository_inventory_family_kind ON repository_inventory_structural_family(repo_id, family_kind);
CREATE INDEX idx_repository_inventory_family_discovery ON repository_inventory_structural_family(repo_id, discovery_kind);
CREATE INDEX idx_repository_inventory_candidate_discovery ON repository_inventory_candidate(repo_id, discovery_kind);
CREATE INDEX idx_repository_inventory_completeness ON repository_inventory_completeness(repo_id, subject_kind, status);
CREATE INDEX idx_repository_inventory_gap ON repository_inventory_coverage_gap(repo_id, gap_kind, discovery_kind, coverage_status);
CREATE INDEX idx_repository_inventory_interface_direction ON repository_inventory_interface(repo_id, direction);
CREATE INDEX idx_repository_inventory_technology ON repository_inventory_technology(repo_id, category, technology);
"""
