from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SQL_ANALYSIS_SOURCE_SCHEMA_VERSION = "sql-analysis/v1"
SQL_ANALYSIS_SCHEMA_VERSION = "knowledge_layer_sql/v2"
SQL_ANALYSIS_DATABASE = "knowledge-layer.duckdb"


@dataclass(frozen=True, slots=True)
class SqlFactSchema:
    fact_type: str
    id_field: str
    fields: tuple[str, ...]


SQL_FACT_SCHEMAS: tuple[SqlFactSchema, ...] = (
    SqlFactSchema("sql_statement", "sql_statement_id", (
        "sql_statement_id", "repo_id", "query_id", "file", "line_start", "line_end",
        "operation", "statement_hash", "statement_type", "target_relation_name", "unit_kind",
        "select_scope_ids", "semantic_placeholders", "write_target_ids", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_script_statement", "sql_script_statement_id", (
        "sql_script_statement_id", "repo_id", "file", "line_start", "line_end", "statement_kind",
        "leading_token", "statement_preview", "contains_embedded_sql", "embedded_sql_first_keyword",
        "embedded_sql_keywords", "embedded_sql_preview", "referenced_sql_paths", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_script_call", "sql_script_call_id", (
        "sql_script_call_id", "repo_id", "parent_script_statement_id", "file", "line_start", "line_end",
        "call_symbol", "named_arguments", "positional_arguments", "referenced_placeholders",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_script_binding", "sql_script_binding_id", (
        "sql_script_binding_id", "repo_id", "parent_script_statement_id", "file", "line_start", "line_end",
        "binding_kind", "binding_name", "value_expression", "scalar_value", "is_sql_path_candidate",
        "referenced_placeholders", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_script_embedded_sql", "sql_script_embedded_sql_id", (
        "sql_script_embedded_sql_id", "repo_id", "parent_script_statement_id", "file", "line_start", "line_end",
        "first_keyword", "sql_preview", "sql_role", "affects_logical_sql_graph", "canonical_lineage_inclusion",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_script_invocation", "sql_script_invocation_id", (
        "sql_script_invocation_id", "repo_id", "parent_script_statement_id", "file", "line_start",
        "invocation_kind", "target_path_template", "invoked_symbol", "resolution_status", "resolution_basis",
        "resolved_file", "resolution_candidates", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_semantic_placeholder", "sql_semantic_placeholder_id", (
        "sql_semantic_placeholder_id", "repo_id", "query_id", "file", "line_start", "placeholder", "syntax",
        "template", "usage_roles", "binding_ids", "resolved_variants", "resolution_status",
        "affects_logical_sql_graph", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_workflow_binding", "sql_workflow_binding_id", (
        "sql_workflow_binding_id", "repo_id", "file", "line_start", "line_end", "config_format",
        "binding_path", "parent_path", "binding_name", "value_type", "scalar_value", "value_expression",
        "referenced_placeholders", "resolution_status", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_select_scope", "sql_select_scope_id", (
        "sql_select_scope_id", "repo_id", "query_id", "file", "line_start", "parent_scope_id", "scope_kind",
        "scope_name", "scope_ordinal", "expression_index", "relation_count", "projection_count", "column_usage_count",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_relation", "sql_relation_id", (
        "sql_relation_id", "repo_id", "query_id", "scope_id", "file", "line_start", "relation_kind",
        "relation_name", "template_name", "logical_name", "alias", "usage_role", "definition_status",
        "source_scope_ids", "placeholder_refs", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_column_usage", "sql_column_usage_id", (
        "sql_column_usage_id", "repo_id", "query_id", "scope_id", "file", "line_start", "column_name",
        "column_ordinal", "usage_role", "table_or_alias", "relation_id", "relation_kind", "relation_name",
        "resolution_status", "resolution_basis", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_projection", "sql_projection_id", (
        "sql_projection_id", "repo_id", "query_id", "scope_id", "file", "line_start", "projection_ordinal",
        "output_name", "expression", "expression_kind", "is_wildcard", "source_column_count",
        "source_column_usage_ids", "resolution_status", "resolution_basis", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_write_target", "sql_write_target_id", (
        "sql_write_target_id", "repo_id", "query_id", "file", "line_start", "operation_kind",
        "target_relation_name", "target_logical_name", "target_relation_kind", "target_placeholder_refs",
        "explicit_target_columns", "source_scope_ids", "binding_mode", "field_mapping_status", "resolution_status",
        "arity_status", "branch_projection_counts", "branch_wildcard_flags", "count_mismatch",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_target_projection_binding", "sql_target_projection_binding_id", (
        "sql_target_projection_binding_id", "repo_id", "query_id", "file", "line_start", "write_target_id",
        "target_relation_name", "target_column", "target_column_ordinal", "source_scope_id", "branch_ordinal",
        "projection_id", "projection_output_name", "projection_resolution_status", "mapping_status", "mapping_basis",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_join_edge", "sql_join_edge_id", (
        "sql_join_edge_id", "repo_id", "query_id", "scope_id", "file", "line_start", "join_ordinal", "join_type",
        "condition_kind", "predicate", "left_relation_id", "left_relation_ids", "left_relation_names",
        "right_relation_id", "right_relation_kind", "right_relation_name", "participating_relation_ids",
        "column_pairs", "expression_links", "using_columns", "additional_predicates", "temporal_or_range_predicates",
        "resolution_status", "resolution_reasons", "physical_join_confirmed", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_direct_column_lineage", "sql_direct_column_lineage_id", (
        "sql_direct_column_lineage_id", "repo_id", "query_id", "file", "line_start", "write_target_id",
        "target_projection_binding_id", "target_relation_name", "target_relation_kind", "target_column",
        "target_mapping_status", "source_scope_id", "branch_ordinal", "projection_id", "projection_ordinal",
        "expression", "expression_kind", "source_kind", "source_column_usage_id", "source_column",
        "source_table_or_alias", "source_usage_role", "source_relation_id", "source_relation_name",
        "source_relation_kind", "source_resolution_status", "physical_origin_status", "direct_lineage_status",
        "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_recursive_column_lineage", "sql_recursive_column_lineage_id", (
        "sql_recursive_column_lineage_id", "repo_id", "query_id", "file", "line_start", "direct_lineage_id",
        "write_target_id", "target_projection_binding_id", "target_relation_name", "target_relation_kind",
        "target_column", "target_mapping_status", "root_projection_id", "root_expression", "root_expression_kind",
        "terminal_source_kind", "terminal_column_usage_id", "terminal_column", "terminal_relation_id",
        "terminal_relation_name", "terminal_relation_kind", "terminal_expression", "terminal_expression_kind",
        "recursion_depth", "branch_path", "transformation_path", "recursive_resolution_status",
        "physical_origin_status", "lineage_status", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_object_dependency", "sql_object_dependency_id", (
        "sql_object_dependency_id", "repo_id", "query_id", "file", "line_start", "source_relation_name",
        "target_relation_name", "dependency_kind", "operation", "evidence_maturity_level", "evidence",
    )),
    SqlFactSchema("sql_scoped_lineage_gap", "sql_scoped_lineage_gap_id", (
        "sql_scoped_lineage_gap_id", "repo_id", "query_id", "file", "line_start", "gap_kind", "analysis_status",
        "impact", "write_target_id", "target_relation_name", "target_column", "target_mapping_status",
        "source_scope_id", "projection_id", "projection_resolution_status", "mapping_basis", "source_column_usage_id",
        "source_column", "table_or_alias", "direct_lineage_id", "source_relation_id", "source_relation_name",
        "source_relation_kind", "recursion_depth", "branch_path", "evidence_maturity_level", "evidence",
    )),
)

SQL_FACT_SCHEMA_BY_TYPE = {schema.fact_type: schema for schema in SQL_FACT_SCHEMAS}
SQL_ANALYSIS_FACT_TYPES = tuple(schema.fact_type for schema in SQL_FACT_SCHEMAS)

INTEGER_FIELDS = {
    "line_start", "line_end", "column_ordinal", "scope_ordinal", "expression_index", "relation_count",
    "projection_count", "column_usage_count", "projection_ordinal", "source_column_count", "target_column_ordinal",
    "branch_ordinal", "join_ordinal", "recursion_depth",
}
BOOLEAN_FIELDS = {
    "contains_embedded_sql", "is_sql_path_candidate", "affects_logical_sql_graph", "is_wildcard",
    "count_mismatch", "physical_join_confirmed",
}
JSON_FIELDS = {
    "select_scope_ids", "semantic_placeholders", "write_target_ids", "embedded_sql_keywords", "referenced_sql_paths",
    "named_arguments", "positional_arguments",
    "referenced_placeholders", "resolution_candidates", "usage_roles", "binding_ids", "resolved_variants",
    "source_scope_ids", "placeholder_refs", "source_column_usage_ids", "target_placeholder_refs",
    "explicit_target_columns", "branch_projection_counts", "branch_wildcard_flags", "left_relation_ids",
    "left_relation_names", "participating_relation_ids", "column_pairs", "expression_links", "using_columns",
    "additional_predicates", "temporal_or_range_predicates", "resolution_reasons", "branch_path",
    "transformation_path", "evidence",
}


def database_column_name(source_field: str) -> str:
    return f"{source_field}_json" if source_field in JSON_FIELDS else source_field


def database_column_type(source_field: str) -> str:
    if source_field in JSON_FIELDS:
        return "JSON"
    if source_field in INTEGER_FIELDS:
        return "BIGINT"
    if source_field in BOOLEAN_FIELDS:
        return "BOOLEAN"
    return "VARCHAR"


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_ddl(schema: SqlFactSchema) -> str:
    columns: list[str] = []
    for field in schema.fields:
        name = database_column_name(field)
        data_type = database_column_type(field)
        constraints: list[str] = []
        if field == schema.id_field:
            constraints.append("PRIMARY KEY")
        if field in {schema.id_field, "repo_id"}:
            constraints.append("NOT NULL")
        suffix = " " + " ".join(constraints) if constraints else ""
        columns.append(f"    {_quoted(name)} {data_type}{suffix}")
    columns.append("    payload_json JSON NOT NULL")
    return f"CREATE TABLE {_quoted(schema.fact_type)} (\n" + ",\n".join(columns) + "\n);"


SQL_ANALYSIS_TABLE_DDL = """
CREATE TABLE sql_analysis_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    source_content_fingerprint VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);


CREATE TABLE sql_relation_semantic_role (
    sql_relation_semantic_role_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    relation_kind VARCHAR NOT NULL,
    relation_identity VARCHAR NOT NULL,
    normalized_identity VARCHAR NOT NULL,
    template_name VARCHAR,
    logical_name VARCHAR,
    semantic_role VARCHAR NOT NULL,
    classification_status VARCHAR NOT NULL,
    hidden_by_default BOOLEAN NOT NULL,
    classification_reasons_json JSON NOT NULL,
    read_occurrence_count BIGINT NOT NULL,
    write_occurrence_count BIGINT NOT NULL,
    downstream_target_count BIGINT NOT NULL,
    owned_namespace BOOLEAN NOT NULL,
    technical_name_signal BOOLEAN NOT NULL,
    dropped_in_repository BOOLEAN NOT NULL,
    evidence_json JSON NOT NULL
);

CREATE TABLE sql_workflow_file_reference (
    sql_workflow_file_reference_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_kind VARCHAR NOT NULL,
    source_fact_id VARCHAR NOT NULL,
    line_start BIGINT,
    reference_ordinal BIGINT NOT NULL,
    target_path_template VARCHAR NOT NULL,
    resolved_target_file VARCHAR,
    resolved_target_kind VARCHAR,
    resolution_status VARCHAR NOT NULL,
    resolution_basis VARCHAR NOT NULL,
    candidate_count BIGINT NOT NULL,
    resolution_candidates_json JSON NOT NULL,
    evidence_json JSON NOT NULL
);

CREATE TABLE sql_workflow_context_file (
    sql_workflow_context_file_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    reachable_file VARCHAR NOT NULL,
    reachable_file_kind VARCHAR NOT NULL,
    context_hop_count BIGINT NOT NULL,
    context_files_json JSON NOT NULL,
    context_reference_ids_json JSON NOT NULL,
    resolution_status VARCHAR NOT NULL,
    resolution_reasons_json JSON NOT NULL
);

CREATE TABLE sql_placeholder_binding_resolution (
    sql_placeholder_binding_resolution_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    sql_file VARCHAR NOT NULL,
    query_id VARCHAR,
    sql_semantic_placeholder_id VARCHAR NOT NULL,
    placeholder VARCHAR NOT NULL,
    usage_roles_json JSON NOT NULL,
    sql_workflow_binding_id VARCHAR NOT NULL,
    binding_file VARCHAR NOT NULL,
    binding_line_start BIGINT,
    binding_path VARCHAR,
    binding_name VARCHAR NOT NULL,
    binding_value_expression VARCHAR,
    resolved_value VARCHAR,
    context_hop_count BIGINT NOT NULL,
    context_files_json JSON NOT NULL,
    context_reference_ids_json JSON NOT NULL,
    resolution_status VARCHAR NOT NULL,
    resolution_reasons_json JSON NOT NULL,
    evidence_json JSON NOT NULL
);

CREATE TABLE sql_workflow_target_column_lineage (
    sql_workflow_target_column_lineage_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    workflow_target_logical_name VARCHAR NOT NULL,
    transform_reference_id VARCHAR NOT NULL,
    query_id VARCHAR,
    file VARCHAR,
    line_start BIGINT,
    target_column VARCHAR NOT NULL,
    root_projection_id VARCHAR,
    root_expression VARCHAR,
    root_expression_kind VARCHAR,
    terminal_source_kind VARCHAR NOT NULL,
    terminal_column_usage_id VARCHAR,
    terminal_column VARCHAR,
    terminal_relation_id VARCHAR,
    terminal_relation_name VARCHAR,
    terminal_relation_kind VARCHAR,
    recursion_depth BIGINT NOT NULL,
    branch_path_json JSON NOT NULL,
    transformation_path_json JSON NOT NULL,
    recursive_resolution_status VARCHAR NOT NULL,
    physical_origin_status VARCHAR NOT NULL,
    lineage_status VARCHAR NOT NULL,
    evidence_maturity_level VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    evidence_json JSON NOT NULL
);

CREATE TABLE sql_workflow_target_lineage_gap (
    sql_workflow_target_lineage_gap_id VARCHAR PRIMARY KEY,
    repo_id VARCHAR NOT NULL,
    workflow_context_file VARCHAR NOT NULL,
    workflow_target_logical_name VARCHAR NOT NULL,
    transform_reference_id VARCHAR NOT NULL,
    query_id VARCHAR,
    file VARCHAR,
    line_start BIGINT,
    target_column VARCHAR,
    projection_id VARCHAR,
    projection_resolution_status VARCHAR,
    gap_kind VARCHAR NOT NULL,
    impact VARCHAR NOT NULL,
    mapping_basis VARCHAR NOT NULL,
    evidence_maturity_level VARCHAR NOT NULL,
    evidence_json JSON NOT NULL
);

CREATE TABLE sql_analysis_repository (
    repo_id VARCHAR PRIMARY KEY,
    sql_analysis_manifest VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    source_content_fingerprint VARCHAR NOT NULL,
    analysis_status VARCHAR NOT NULL,
    system_name VARCHAR,
    project_code VARCHAR,
    analysis_profile VARCHAR,
    producer_name VARCHAR NOT NULL,
    producer_version VARCHAR NOT NULL,
    source_created_at VARCHAR,
    coverage_json JSON NOT NULL,
    source_manifest_json JSON NOT NULL
);
""" + "\n\n".join(_table_ddl(schema) for schema in SQL_FACT_SCHEMAS)

SQL_ANALYSIS_VIEW_DDL = """
CREATE VIEW v_sql_relation_field_usage AS
SELECT
    r.repo_id,
    r.sql_relation_id,
    r.query_id,
    r.scope_id,
    r.relation_kind,
    r.relation_name,
    r.template_name,
    r.logical_name,
    r.alias,
    r.usage_role AS relation_usage_role,
    r.definition_status,
    r.file,
    r.line_start,
    u.sql_column_usage_id,
    u.column_name,
    u.column_ordinal,
    u.usage_role AS column_usage_role,
    u.table_or_alias,
    u.resolution_status AS column_resolution_status,
    u.resolution_basis AS column_resolution_basis,
    u.file AS column_file,
    u.line_start AS column_line_start
FROM sql_relation r
LEFT JOIN sql_column_usage u ON u.repo_id=r.repo_id AND u.relation_id=r.sql_relation_id;
"""

SQL_ANALYSIS_INDEX_DDL = """
CREATE INDEX idx_sql_relation_inventory
    ON sql_relation(repo_id, relation_kind, template_name, relation_name);
CREATE INDEX idx_sql_relation_scope
    ON sql_relation(repo_id, query_id, scope_id);
CREATE INDEX idx_sql_column_usage_relation
    ON sql_column_usage(repo_id, relation_id, column_name, usage_role);
CREATE INDEX idx_sql_join_scope
    ON sql_join_edge(repo_id, query_id, scope_id, join_ordinal);
CREATE INDEX idx_sql_recursive_target
    ON sql_recursive_column_lineage(repo_id, target_relation_name, target_column);
CREATE INDEX idx_sql_recursive_source
    ON sql_recursive_column_lineage(repo_id, terminal_relation_name, terminal_column);
CREATE INDEX idx_sql_workflow_binding_lookup
    ON sql_workflow_binding(repo_id, binding_name, resolution_status, file);
CREATE INDEX idx_sql_workflow_file_reference_source
    ON sql_workflow_file_reference(repo_id, source_file, resolution_status);
CREATE INDEX idx_sql_workflow_context_file_lookup
    ON sql_workflow_context_file(repo_id, reachable_file, workflow_context_file, resolution_status);
CREATE INDEX idx_sql_workflow_target_lineage
    ON sql_workflow_target_column_lineage(repo_id, workflow_target_logical_name, target_column);
CREATE INDEX idx_sql_workflow_target_lineage_gap
    ON sql_workflow_target_lineage_gap(repo_id, workflow_target_logical_name, target_column, gap_kind);
CREATE INDEX idx_sql_placeholder_binding_sql
    ON sql_placeholder_binding_resolution(repo_id, sql_file, placeholder, resolution_status);
CREATE INDEX idx_sql_placeholder_binding_context
    ON sql_placeholder_binding_resolution(repo_id, workflow_context_file, binding_name, resolved_value);
CREATE INDEX idx_sql_relation_semantic_role
    ON sql_relation_semantic_role(repo_id, relation_kind, normalized_identity, semantic_role, hidden_by_default);
"""

SQL_ANALYSIS_DDL = "\n\n".join((SQL_ANALYSIS_TABLE_DDL, SQL_ANALYSIS_VIEW_DDL, SQL_ANALYSIS_INDEX_DDL))
SQL_ANALYSIS_TABLES = (
    "sql_analysis_build",
    "sql_analysis_repository",
    "sql_relation_semantic_role",
    "sql_workflow_file_reference",
    "sql_workflow_context_file",
    "sql_placeholder_binding_resolution",
    "sql_workflow_target_column_lineage",
    "sql_workflow_target_lineage_gap",
    *SQL_ANALYSIS_FACT_TYPES,
)
SQL_ANALYSIS_VIEWS = ("v_sql_relation_field_usage",)


def sql_fact_database_columns(schema: SqlFactSchema) -> tuple[str, ...]:
    return tuple(database_column_name(field) for field in schema.fields) + ("payload_json",)


def iter_sql_fact_schemas() -> Iterable[SqlFactSchema]:
    return iter(SQL_FACT_SCHEMAS)
