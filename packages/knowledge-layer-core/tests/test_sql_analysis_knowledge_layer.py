from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowledge_layer_core import SQL_ANALYSIS_FACT_TYPES, SQL_ANALYSIS_SOURCE_SCHEMA_VERSION, SQL_FACT_SCHEMAS, build_sql_knowledge_layer, resolve_sql_analysis_artifact
from knowledge_layer_core.progress import bind_progress
from prepared_knowledge_runtime import KnowledgeLayerQuery

pytest.importorskip("duckdb")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write(path: Path, content: bytes) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest(), len(content)


def _artifact(
    tmp_path: Path,
    *,
    include_semantic_roles: bool = False,
    include_source_coverage: bool = False,
) -> Path:
    root = tmp_path / "sql-analysis"
    facts = root / "facts"
    repo_id = "repo-sql"
    rows = {
        "sql_relation": [
            {
                "fact_type": "sql_relation",
                "sql_relation_id": "rel-1",
                "repo_id": repo_id,
                "query_id": "q1",
                "scope_id": "scope-1",
                "file": "sql/load.sql",
                "line_start": 2,
                "relation_kind": "physical_template",
                "relation_name": "${source_schema}.client",
                "template_name": "${source_schema}.client",
                "logical_name": "client",
                "alias": "cl",
                "usage_role": "read",
                "definition_status": "not_applicable",
                "source_scope_ids": [],
                "placeholder_refs": ["source_schema"],
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/load.sql", "line_start": 2}],
            },
            {
                "fact_type": "sql_relation",
                "sql_relation_id": "rel-2",
                "repo_id": repo_id,
                "query_id": "q2",
                "scope_id": "scope-2",
                "file": "sql/reload.sql",
                "line_start": 7,
                "relation_kind": "physical_template",
                "relation_name": "${source_schema}.client",
                "template_name": "${source_schema}.client",
                "logical_name": "client",
                "alias": "src",
                "usage_role": "read",
                "definition_status": "not_applicable",
                "source_scope_ids": [],
                "placeholder_refs": ["source_schema"],
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/reload.sql", "line_start": 7}],
            },
        ],
        "sql_column_usage": [
            {
                "fact_type": "sql_column_usage",
                "sql_column_usage_id": "col-1",
                "repo_id": repo_id,
                "query_id": "q1",
                "scope_id": "scope-1",
                "file": "sql/load.sql",
                "line_start": 3,
                "column_name": "client_id",
                "column_ordinal": 1,
                "usage_role": "projection",
                "table_or_alias": "cl",
                "relation_id": "rel-1",
                "relation_kind": "physical_template",
                "relation_name": "${source_schema}.client",
                "resolution_status": "resolved",
                "resolution_basis": "qualified_alias",
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/load.sql", "line_start": 3}],
            },
            {
                "fact_type": "sql_column_usage",
                "sql_column_usage_id": "col-2",
                "repo_id": repo_id,
                "query_id": "q1",
                "scope_id": "scope-1",
                "file": "sql/load.sql",
                "line_start": 4,
                "column_name": "client_id",
                "column_ordinal": 2,
                "usage_role": "join",
                "table_or_alias": "cl",
                "relation_id": "rel-1",
                "relation_kind": "physical_template",
                "relation_name": "${source_schema}.client",
                "resolution_status": "resolved",
                "resolution_basis": "qualified_alias",
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/load.sql", "line_start": 4}],
            },
            {
                "fact_type": "sql_column_usage",
                "sql_column_usage_id": "col-3",
                "repo_id": repo_id,
                "query_id": "q2",
                "scope_id": "scope-2",
                "file": "sql/reload.sql",
                "line_start": 8,
                "column_name": "birth_dt",
                "column_ordinal": 1,
                "usage_role": "filter",
                "table_or_alias": "src",
                "relation_id": "rel-2",
                "relation_kind": "physical_template",
                "relation_name": "${source_schema}.client",
                "resolution_status": "resolved",
                "resolution_basis": "qualified_alias",
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/reload.sql", "line_start": 8}],
            },
        ],
    }
    rows["sql_workflow_binding"] = [
        {
            "fact_type": "sql_workflow_binding",
            "sql_workflow_binding_id": "workflow-binding-main",
            "repo_id": repo_id,
            "file": "workflow/client.yaml",
            "line_start": 5,
            "line_end": 5,
            "config_format": "yaml",
            "binding_path": "param.main_table_name",
            "parent_path": "param",
            "binding_name": "main_table_name",
            "value_type": "string",
            "scalar_value": "client_profile",
            "value_expression": "client_profile",
            "referenced_placeholders": [],
            "resolution_status": "literal",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "workflow/client.yaml", "line_start": 5}],
        },
        {
            "fact_type": "sql_workflow_binding",
            "sql_workflow_binding_id": "workflow-binding-sql-file",
            "repo_id": repo_id,
            "file": "workflow/client.yaml",
            "line_start": 4,
            "line_end": 4,
            "config_format": "yaml",
            "binding_path": "param.sql.file",
            "parent_path": "param",
            "binding_name": "sql.file",
            "value_type": "string",
            "scalar_value": "sql/target.sql",
            "value_expression": "sql/target.sql",
            "referenced_placeholders": [],
            "resolution_status": "literal",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "workflow/client.yaml", "line_start": 4}],
        },
        {
            "fact_type": "sql_workflow_binding",
            "sql_workflow_binding_id": "workflow-binding-stage",
            "repo_id": repo_id,
            "file": "workflow/client.yaml",
            "line_start": 6,
            "line_end": 6,
            "config_format": "yaml",
            "binding_path": "param.main_table_name_stg",
            "parent_path": "param",
            "binding_name": "main_table_name_stg",
            "value_type": "string",
            "scalar_value": "${main_table_name}_stg",
            "value_expression": "${main_table_name}_stg",
            "referenced_placeholders": ["main_table_name"],
            "resolution_status": "template",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "workflow/client.yaml", "line_start": 6}],
        },
    ]
    rows["sql_semantic_placeholder"] = [
        {
            "fact_type": "sql_semantic_placeholder",
            "sql_semantic_placeholder_id": "placeholder-main-table",
            "repo_id": repo_id,
            "query_id": "q-lineage",
            "file": "sql/target.sql",
            "line_start": 1,
            "placeholder": "main_table_name",
            "syntax": "braced_or_template",
            "template": "${$main_table_name}",
            "usage_roles": ["target_relation"],
            "binding_ids": [],
            "resolved_variants": [],
            "resolution_status": "unresolved",
            "affects_logical_sql_graph": True,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/target.sql", "line_start": 1}],
        }
    ]
    if include_semantic_roles:
        rows["sql_relation"].extend([
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-temp", "repo_id": repo_id,
                "query_id": "q-temp-read", "scope_id": "scope-temp", "file": "sql/final.sql",
                "line_start": 20, "relation_kind": "physical", "relation_name": "work.tmp_client",
                "template_name": None, "logical_name": "tmp_client", "alias": "tmp", "usage_role": "from",
                "definition_status": "not_applicable", "source_scope_ids": [], "placeholder_refs": [],
                "evidence_maturity_level": "confirmed", "evidence": [{"relative_file": "sql/final.sql", "line_start": 20}],
            },
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-output", "repo_id": repo_id,
                "query_id": "q-output-read", "scope_id": "scope-output", "file": "sql/reconcile.sql",
                "line_start": 4, "relation_kind": "physical", "relation_name": "mart.client_profile",
                "template_name": None, "logical_name": "client_profile", "alias": "m", "usage_role": "from",
                "definition_status": "not_applicable", "source_scope_ids": [], "placeholder_refs": [],
                "evidence_maturity_level": "confirmed", "evidence": [{"relative_file": "sql/reconcile.sql", "line_start": 4}],
            },
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-vendor-stg", "repo_id": repo_id,
                "query_id": "q-vendor", "scope_id": "scope-vendor", "file": "sql/vendor.sql",
                "line_start": 3, "relation_kind": "physical", "relation_name": "vendor_stg.customer",
                "template_name": None, "logical_name": "customer", "alias": "v", "usage_role": "from",
                "definition_status": "not_applicable", "source_scope_ids": [], "placeholder_refs": [],
                "evidence_maturity_level": "confirmed", "evidence": [{"relative_file": "sql/vendor.sql", "line_start": 3}],
            },
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-shared-stage", "repo_id": repo_id,
                "query_id": "q-shared", "scope_id": "scope-shared", "file": "sql/shared.sql",
                "line_start": 8, "relation_kind": "physical", "relation_name": "work.shared_stage",
                "template_name": None, "logical_name": "shared_stage", "alias": "s", "usage_role": "from",
                "definition_status": "not_applicable", "source_scope_ids": [], "placeholder_refs": [],
                "evidence_maturity_level": "confirmed", "evidence": [{"relative_file": "sql/shared.sql", "line_start": 8}],
            },
        ])
        rows["sql_write_target"] = [
            {
                "fact_type": "sql_write_target", "sql_write_target_id": "write-temp", "repo_id": repo_id,
                "query_id": "q-temp-write", "file": "sql/prepare.sql", "line_start": 1,
                "operation_kind": "create_table", "target_relation_name": "work.tmp_client",
                "target_logical_name": "tmp_client", "target_relation_kind": "physical",
                "target_placeholder_refs": [], "explicit_target_columns": [], "source_scope_ids": [],
                "binding_mode": "ordinal", "field_mapping_status": "resolved", "resolution_status": "resolved",
                "arity_status": "matched", "branch_projection_counts": [], "branch_wildcard_flags": [],
                "count_mismatch": False, "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/prepare.sql", "line_start": 1}],
            },
            {
                "fact_type": "sql_write_target", "sql_write_target_id": "write-output", "repo_id": repo_id,
                "query_id": "q-output-write", "file": "sql/final.sql", "line_start": 1,
                "operation_kind": "insert", "target_relation_name": "mart.client_profile",
                "target_logical_name": "client_profile", "target_relation_kind": "physical",
                "target_placeholder_refs": [], "explicit_target_columns": [], "source_scope_ids": [],
                "binding_mode": "ordinal", "field_mapping_status": "resolved", "resolution_status": "resolved",
                "arity_status": "matched", "branch_projection_counts": [], "branch_wildcard_flags": [],
                "count_mismatch": False, "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/final.sql", "line_start": 1}],
            },
        ]
        rows["sql_object_dependency"] = [
            {
                "fact_type": "sql_object_dependency", "sql_object_dependency_id": "dep-temp-output",
                "repo_id": repo_id, "query_id": "q-output-write", "file": "sql/final.sql", "line_start": 1,
                "source_relation_name": "work.tmp_client", "target_relation_name": "mart.client_profile",
                "dependency_kind": "write_from_read", "operation": "insert",
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/final.sql", "line_start": 1}],
            },
            {
                "fact_type": "sql_object_dependency", "sql_object_dependency_id": "dep-shared-output",
                "repo_id": repo_id, "query_id": "q-shared", "file": "sql/shared.sql", "line_start": 8,
                "source_relation_name": "work.shared_stage", "target_relation_name": "mart.client_profile",
                "dependency_kind": "write_from_read", "operation": "insert",
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/shared.sql", "line_start": 8}],
            },
        ]
    if include_source_coverage:
        rows["sql_relation"].extend([
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-generated-a", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 2, "relation_kind": "physical_template",
                "relation_name": "${source_schema}.individual_hist",
                "template_name": "${source_schema}.individual_hist", "logical_name": "individual_hist",
                "alias": "ind", "usage_role": "from", "definition_status": "not_applicable",
                "source_scope_ids": [], "placeholder_refs": ["source_schema"],
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/generated.sql", "line_start": 2}],
            },
            {
                "fact_type": "sql_relation", "sql_relation_id": "rel-generated-b", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 3, "relation_kind": "physical_template",
                "relation_name": "${source_schema}.birthdate_hist",
                "template_name": "${source_schema}.birthdate_hist", "logical_name": "birthdate_hist",
                "alias": "bd", "usage_role": "join", "definition_status": "not_applicable",
                "source_scope_ids": [], "placeholder_refs": ["source_schema"],
                "evidence_maturity_level": "confirmed",
                "evidence": [{"relative_file": "sql/generated.sql", "line_start": 3}],
            },
        ])
        rows["sql_select_scope"] = [{
            "fact_type": "sql_select_scope", "sql_select_scope_id": "scope-generated",
            "repo_id": repo_id, "query_id": "q-generated", "file": "sql/generated.sql",
            "line_start": 1, "parent_scope_id": None, "scope_kind": "select", "scope_name": None,
            "scope_ordinal": 1, "expression_index": 0, "relation_count": 3,
            "projection_count": 1, "column_usage_count": 5, "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/generated.sql", "line_start": 1}],
        }]
        rows["sql_statement"] = [{
            "fact_type": "sql_statement", "sql_statement_id": "stmt-generated", "repo_id": repo_id,
            "query_id": "q-generated", "file": "sql/generated.sql", "line_start": 1, "line_end": 9,
            "operation": "select", "statement_hash": "hash-generated", "statement_type": "select",
            "target_relation_name": None, "unit_kind": "sql", "select_scope_ids": ["scope-generated"],
            "semantic_placeholders": ["source_schema"], "write_target_ids": [],
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/generated.sql", "line_start": 1}],
        }]
        rows["sql_join_edge"] = [{
            "fact_type": "sql_join_edge", "sql_join_edge_id": "join-generated", "repo_id": repo_id,
            "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
            "line_start": 3, "join_ordinal": 1, "join_type": "left", "condition_kind": "on",
            "predicate": "ind.id = bd.id", "left_relation_id": "rel-generated-a",
            "left_relation_ids": ["rel-generated-a"],
            "left_relation_names": ["${source_schema}.individual_hist"],
            "right_relation_id": "rel-generated-b", "right_relation_kind": "physical_template",
            "right_relation_name": "${source_schema}.birthdate_hist",
            "participating_relation_ids": ["rel-generated-a", "rel-generated-b"],
            "column_pairs": [{"left_column": "id", "right_column": "id"}],
            "expression_links": [], "using_columns": [], "additional_predicates": [],
            "temporal_or_range_predicates": [], "resolution_status": "resolved",
            "resolution_reasons": [], "physical_join_confirmed": True,
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/generated.sql", "line_start": 3}],
        }]
        rows["sql_projection"] = [{
            "fact_type": "sql_projection", "sql_projection_id": "projection-generated",
            "repo_id": repo_id, "query_id": "q-generated", "scope_id": "scope-generated",
            "file": "sql/generated.sql", "line_start": 7, "projection_ordinal": 1,
            "output_name": "id", "expression": "id", "expression_kind": "column",
            "is_wildcard": False, "source_column_count": 1,
            "source_column_usage_ids": ["col-ambiguous"], "resolution_status": "ambiguous",
            "resolution_basis": "ambiguous_unqualified", "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/generated.sql", "line_start": 7}],
        }]
        rows["sql_relation"].append({
            "fact_type": "sql_relation", "sql_relation_id": "rel-generated", "repo_id": repo_id,
            "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
            "line_start": 3, "relation_kind": "generated", "relation_name": "participant",
            "template_name": "participant", "logical_name": "participant", "alias": "participant",
            "usage_role": "generated_source", "definition_status": "resolved", "source_scope_ids": [],
            "placeholder_refs": [], "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/generated.sql", "line_start": 3}],
        })
        rows["sql_column_usage"].extend([
            {
                "fact_type": "sql_column_usage", "sql_column_usage_id": "col-generated", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 4, "column_name": "status", "column_ordinal": 1,
                "usage_role": "projection", "table_or_alias": "participant", "relation_id": "rel-generated",
                "relation_kind": "generated", "relation_name": "participant", "resolution_status": "resolved",
                "resolution_basis": "generated_alias", "evidence_maturity_level": "confirmed", "evidence": [],
            },
            {
                "fact_type": "sql_column_usage", "sql_column_usage_id": "col-semantic", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 5, "column_name": "${business_date}", "column_ordinal": 2,
                "usage_role": "projection", "table_or_alias": None, "relation_id": None,
                "relation_kind": None, "relation_name": None, "resolution_status": "semantic_parameter",
                "resolution_basis": "semantic_parameter", "evidence_maturity_level": "confirmed", "evidence": [],
            },
            {
                "fact_type": "sql_column_usage", "sql_column_usage_id": "col-output", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 6, "column_name": "result_alias", "column_ordinal": 3,
                "usage_role": "order_by", "table_or_alias": None, "relation_id": None,
                "relation_kind": None, "relation_name": None, "resolution_status": "projection_output",
                "resolution_basis": "projection_output", "evidence_maturity_level": "confirmed", "evidence": [],
            },
            {
                "fact_type": "sql_column_usage", "sql_column_usage_id": "col-ambiguous", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 7, "column_name": "id", "column_ordinal": 4,
                "usage_role": "projection", "table_or_alias": None, "relation_id": None,
                "relation_kind": None, "relation_name": None, "resolution_status": "ambiguous",
                "resolution_basis": "ambiguous_unqualified", "evidence_maturity_level": "confirmed", "evidence": [],
            },
            {
                "fact_type": "sql_column_usage", "sql_column_usage_id": "col-unavailable", "repo_id": repo_id,
                "query_id": "q-generated", "scope_id": "scope-generated", "file": "sql/generated.sql",
                "line_start": 8, "column_name": "flag", "column_ordinal": 5,
                "usage_role": "filter", "table_or_alias": None, "relation_id": None,
                "relation_kind": None, "relation_name": None, "resolution_status": "unresolved",
                "resolution_basis": "relation_unavailable", "evidence_maturity_level": "confirmed", "evidence": [],
            },
        ])

    rows["sql_recursive_column_lineage"] = [
        {
            "fact_type": "sql_recursive_column_lineage",
            "sql_recursive_column_lineage_id": "recursive-normalized-a",
            "repo_id": repo_id,
            "query_id": "q-lineage",
            "file": "sql/target.sql",
            "line_start": 10,
            "direct_lineage_id": "direct-normalized-a",
            "write_target_id": "write-client-profile",
            "target_projection_binding_id": "binding-normalized",
            "target_relation_name": "mart.client_profile",
            "target_relation_kind": "physical",
            "target_column": "normalized_name",
            "target_mapping_status": "confirmed",
            "root_projection_id": "projection-normalized",
            "root_expression": "upper(c.name)",
            "root_expression_kind": "normalization_or_cast",
            "terminal_source_kind": "column",
            "terminal_column_usage_id": "usage-source-name-a",
            "terminal_column": "name",
            "terminal_relation_id": "relation-source-client",
            "terminal_relation_name": "src.client",
            "terminal_relation_kind": "physical",
            "terminal_expression": "c.name",
            "terminal_expression_kind": "direct_column",
            "recursion_depth": 1,
            "branch_path": [{
                "intermediate_relation_name": "prepared",
                "definition_branch_ordinal": 1,
                "projection_output_name": "normalized_name",
            }],
            "transformation_path": [
                {"expression_kind": "direct_column", "expression": "c.name"},
                {"expression_kind": "normalization_or_cast", "expression": "upper(c.name)"},
            ],
            "recursive_resolution_status": "resolved",
            "physical_origin_status": "confirmed",
            "lineage_status": "confirmed",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/target.sql", "line_start": 10}],
        },
        {
            "fact_type": "sql_recursive_column_lineage",
            "sql_recursive_column_lineage_id": "recursive-normalized-b",
            "repo_id": repo_id,
            "query_id": "q-lineage",
            "file": "sql/target.sql",
            "line_start": 11,
            "direct_lineage_id": "direct-normalized-b",
            "write_target_id": "write-client-profile",
            "target_projection_binding_id": "binding-normalized",
            "target_relation_name": "mart.client_profile",
            "target_relation_kind": "physical",
            "target_column": "normalized_name",
            "target_mapping_status": "confirmed",
            "root_projection_id": "projection-normalized",
            "root_expression": "upper(a.name)",
            "root_expression_kind": "normalization_or_cast",
            "terminal_source_kind": "column",
            "terminal_column_usage_id": "usage-source-name-b",
            "terminal_column": "name",
            "terminal_relation_id": "relation-source-alias",
            "terminal_relation_name": "src.client_alias",
            "terminal_relation_kind": "physical",
            "terminal_expression": "a.name",
            "terminal_expression_kind": "direct_column",
            "recursion_depth": 2,
            "branch_path": [{
                "intermediate_relation_name": "combined",
                "definition_branch_ordinal": 2,
                "projection_output_name": "normalized_name",
            }],
            "transformation_path": [
                {"expression_kind": "direct_column", "expression": "a.name"},
                {"expression_kind": "normalization_or_cast", "expression": "upper(a.name)"},
            ],
            "recursive_resolution_status": "resolved",
            "physical_origin_status": "confirmed",
            "lineage_status": "confirmed",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/target.sql", "line_start": 11}],
        },
        {
            "fact_type": "sql_recursive_column_lineage",
            "sql_recursive_column_lineage_id": "recursive-region-partial",
            "repo_id": repo_id,
            "query_id": "q-lineage",
            "file": "sql/target.sql",
            "line_start": 12,
            "direct_lineage_id": "direct-region",
            "write_target_id": "write-client-profile",
            "target_projection_binding_id": "binding-region",
            "target_relation_name": "mart.client_profile",
            "target_relation_kind": "physical",
            "target_column": "region_name",
            "target_mapping_status": "confirmed",
            "root_projection_id": "projection-region",
            "root_expression": "region_name",
            "root_expression_kind": "direct_column",
            "terminal_source_kind": "unresolved",
            "terminal_column_usage_id": "usage-region",
            "terminal_column": "region_name",
            "terminal_relation_id": None,
            "terminal_relation_name": None,
            "terminal_relation_kind": None,
            "terminal_expression": "region_name",
            "terminal_expression_kind": "direct_column",
            "recursion_depth": 1,
            "branch_path": [{
                "intermediate_relation_name": "prepared",
                "projection_output_name": "region_name",
            }],
            "transformation_path": [{"expression_kind": "direct_column", "expression": "region_name"}],
            "recursive_resolution_status": "partial",
            "physical_origin_status": "unresolved",
            "lineage_status": "partial",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/target.sql", "line_start": 12}],
        },
    ]
    rows["sql_scoped_lineage_gap"] = [
        {
            "fact_type": "sql_scoped_lineage_gap",
            "sql_scoped_lineage_gap_id": "gap-region-ambiguous",
            "repo_id": repo_id,
            "query_id": "q-lineage",
            "file": "sql/target.sql",
            "line_start": 12,
            "gap_kind": "ambiguous_source_relation",
            "analysis_status": "partial",
            "impact": "terminal_source_unresolved",
            "write_target_id": "write-client-profile",
            "target_relation_name": "mart.client_profile",
            "target_column": "region_name",
            "target_mapping_status": "confirmed",
            "source_scope_id": "scope-region",
            "projection_id": "projection-region",
            "projection_resolution_status": "ambiguous",
            "mapping_basis": "ambiguous_unqualified",
            "source_column_usage_id": "usage-region",
            "source_column": "region_name",
            "table_or_alias": None,
            "direct_lineage_id": "direct-region",
            "source_relation_id": None,
            "source_relation_name": None,
            "source_relation_kind": None,
            "recursion_depth": 1,
            "branch_path": [{"intermediate_relation_name": "prepared"}],
            "evidence_maturity_level": "confirmed",
            "evidence": [{"relative_file": "sql/target.sql", "line_start": 12}],
        }
    ]

    fact_manifest = []
    for schema in SQL_FACT_SCHEMAS:
        payloads = rows.get(schema.fact_type, [])
        content = "".join(_canonical(row) + "\n" for row in payloads).encode("utf-8")
        sha, size = _write(facts / f"{schema.fact_type}.jsonl", content)
        fact_manifest.append(
            {
                "fact_type": schema.fact_type,
                "id_field": schema.id_field,
                "path": f"facts/{schema.fact_type}.jsonl",
                "record_count": len(payloads),
                "sha256": sha,
                "byte_size": size,
            }
        )
    coverage = {
        "artifact": "sql_analysis_coverage",
        "schema_version": SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
        "analysis_status": "partial",
        "fact_counts": {fact_type: len(rows.get(fact_type, [])) for fact_type in SQL_ANALYSIS_FACT_TYPES},
    }
    coverage_bytes = (_canonical(coverage) + "\n").encode("utf-8")
    coverage_sha, coverage_size = _write(root / "coverage.json", coverage_bytes)
    fingerprint_input = "\n".join(
        f"{entry['fact_type']}:{entry['record_count']}:{entry['sha256']}"
        for entry in fact_manifest
    ) + f"\ncoverage:{coverage_sha}"
    content_fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    manifest = {
        "artifact": "sql_analysis",
        "contract_version": "1.0",
        "schema_version": SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
        "created_at": "2026-07-31T18:00:00+00:00",
        "analysis_status": "partial",
        "repository": {
            "repo_id": repo_id,
            "system_name": "system-sql",
            "project_code": "SQL",
            "analysis_profile": "sql-mart-lineage",
        },
        "producer": {"name": "code-analyzer-core", "version": "0.42.2"},
        "facts": fact_manifest,
        "coverage": {"path": "coverage.json", "sha256": coverage_sha, "byte_size": coverage_size},
        "content_fingerprint": content_fingerprint,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(_canonical(manifest), encoding="utf-8")
    return manifest_path


def test_resolver_validates_all_eighteen_shards(tmp_path: Path) -> None:
    artifact = resolve_sql_analysis_artifact(_artifact(tmp_path))
    assert artifact.repo_id == "repo-sql"
    assert tuple(artifact.fact_entries) == SQL_ANALYSIS_FACT_TYPES


def test_builder_streams_typed_sql_tables_and_query_returns_used_fields(tmp_path: Path) -> None:
    progress_messages: list[str] = []
    with bind_progress(progress_messages.append):
        manifest = build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    assert manifest["modes"] == ["sql"]
    assert manifest["capabilities"] == [
        "common.sql-analysis",
        "common.sql-relation-fields",
        "common.sql-source-inventory",
        "common.sql-source-inventory-export",
        "common.sql-relation-semantic-roles",
        "common.sql-target-column-lineage",
        "common.sql-field-calculation",
        "common.sql-workflow-bindings",
        "common.sql-workflow-context",
        "common.sql-target-resolution",
        "common.sql-attribute-insertion-context",
    ]
    assert manifest["counts"]["sql_relation"] == 2
    assert manifest["counts"]["sql_column_usage"] == 3
    assert manifest["counts"]["sql_workflow_binding"] == 3
    assert any("sql-analysis ingest sql_relation records=2 started" in item for item in progress_messages)
    assert any("sql-analysis workflow_context completed" in item for item in progress_messages)
    assert any("sql-analysis workflow_target_lineage completed" in item for item in progress_messages)
    assert any("sql-analysis checkpoint completed" in item for item in progress_messages)
    assert any("sql-analysis atomic publish completed" in item for item in progress_messages)

    query = KnowledgeLayerQuery(tmp_path / "knowledge")
    assert "common.sql-analysis" in query.capabilities()
    result = query.list_sql_relations(
        repo_id="repo-sql",
        relation_kind="physical_template",
        include_fields=True,
        max_evidence_per_role=1,
    )
    assert result["total_count"] == 1
    relation = result["items"][0]
    assert relation["relation_identity"] == "${source_schema}.client"
    assert relation["occurrence_count"] == 2
    assert relation["resolved_names"] == []
    assert relation["statement_count"] == 2
    assert relation["field_count"] == 2
    fields = {field["name"]: field for field in relation["fields"]}
    assert fields["client_id"]["usage_roles"] == ["join", "projection"]
    assert fields["client_id"]["occurrence_count"] == 2
    assert fields["client_id"]["evidence_count"] == 2
    assert fields["client_id"]["evidence_count_by_role"] == {"join": 1, "projection": 1}
    assert len(fields["client_id"]["evidence_refs"]) == 2
    assert fields["client_id"]["evidence_truncated"] is False
    assert fields["birth_dt"]["usage_roles"] == ["filter"]
    assert relation["evidence_count"] == 2
    assert relation["evidence_count_by_role"] == {"read": 2}
    assert len(relation["evidence_refs"]) == 1
    assert relation["evidence_truncated"] is True

    export = query.export_sql_source_inventory(
        repo_id="repo-sql", relation_kind="physical_template", max_evidence_per_role=1
    )
    assert export["schema_version"] == "sql-source-inventory/v1"
    assert export["item_count"] == 1
    assert {item["relation_kind"] for item in export["items"]} <= {"physical", "physical_template"}
    assert export["items"][0]["relation_identity"] == "${source_schema}.client"
    first_export = query.write_sql_source_inventory_jsonl(
        tmp_path / "inventory-1.jsonl",
        repo_id="repo-sql", relation_kind="physical_template", max_evidence_per_role=1,
    )
    second_export = query.write_sql_source_inventory_jsonl(
        tmp_path / "inventory-2.jsonl",
        repo_id="repo-sql", relation_kind="physical_template", max_evidence_per_role=1,
    )
    assert first_export["sha256"] == second_export["sha256"]
    assert first_export["record_count"] == 2
    records = [json.loads(line) for line in (tmp_path / "inventory-1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[0]["record_type"] == "inventory_metadata"
    assert records[1]["record_type"] == "source_relation"
    assert records[1]["relation"]["field_count"] == 2
    assert result["coverage"]["analysis_status"] == "partial"
    overview = query.get_overview()
    assert overview["repositories"][0]["repo_id"] == "repo-sql"
    assert overview["build"]["schema_version"] == "knowledge_layer_sql/v2"
    direct = KnowledgeLayerQuery(tmp_path / "knowledge" / "knowledge-layer.duckdb")
    assert direct.manifest()["scope_id"] == "repo-sql"
    assert direct.manifest()["repository_count"] == 1


def test_sql_relation_evidence_limit_is_validated(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")
    with pytest.raises(ValueError, match="max_evidence_per_role"):
        query.list_sql_relations(max_evidence_per_role=0)
    with pytest.raises(ValueError, match="max_evidence_per_role"):
        query.export_sql_source_inventory(max_evidence_per_role=True)


def test_resolver_rejects_tampered_shard(tmp_path: Path) -> None:
    manifest_path = _artifact(tmp_path)
    relation_path = manifest_path.parent / "facts" / "sql_relation.jsonl"
    relation_path.write_text(relation_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        resolve_sql_analysis_artifact(manifest_path)


def test_relation_semantic_roles_hide_local_intermediates_but_keep_external_staging(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path, include_semantic_roles=True), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    business = query.list_sql_relations(repo_id="repo-sql", view="business_sources", include_fields=False)
    assert {item["relation_identity"] for item in business["items"]} == {
        "${source_schema}.client",
        "vendor_stg.customer",
    }
    assert all(item["semantic_role"] == "external_source" for item in business["items"])

    export = query.export_sql_source_inventory(repo_id="repo-sql", view="business_sources")
    identities = [item["relation_identity"] for item in export["items"]]
    assert identities == ["${source_schema}.client", "vendor_stg.customer"]
    assert identities == sorted(identities, key=lambda value: (value.casefold(), value))
    for item in export["items"]:
        field_names = [field["name"] for field in item["fields"]]
        assert field_names == sorted(field_names, key=lambda value: (value.casefold(), value))

    technical = query.list_sql_relations(repo_id="repo-sql", view="technical", include_fields=False)
    roles = {item["relation_identity"]: (item["semantic_role"], item["classification_status"]) for item in technical["items"]}
    assert roles["work.tmp_client"] == ("internal_intermediate", "confirmed")
    assert roles["work.shared_stage"] == ("internal_intermediate", "probable")
    assert roles["mart.client_profile"] == ("output_target", "confirmed")
    assert "technical_name_signal" in next(
        item["classification_reasons"] for item in technical["items"]
        if item["relation_identity"] == "work.shared_stage"
    )

    all_relations = query.list_sql_relations(repo_id="repo-sql", view="all", include_fields=False)
    assert all_relations["total_count"] == 5
    classification = all_relations["coverage"]["relation_classification"]
    assert classification["hidden_by_default"] == 3
    assert classification["visible_by_default"] == 2
    assert classification["by_role"] == {
        "external_source": 2,
        "internal_intermediate": 2,
        "output_target": 1,
    }


def test_source_inventory_coverage_separates_non_source_values_from_real_gaps(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path, include_source_coverage=True), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    coverage = query.sql_source_inventory_coverage(repo_id="repo-sql")
    assert coverage["status"] == "partial"
    assert coverage["column_usages"] == {
        "total": 8,
        "relation_field_candidates": 5,
        "resolved_relation_fields": 3,
        "unresolved_relation_fields": 2,
        "relation_field_resolution_rate": pytest.approx(3 / 5),
    }
    assert coverage["resolved_by_relation_kind"] == {"physical_template": 3}
    assert coverage["non_source_values"] == {
        "semantic_parameters": 1,
        "projection_outputs": 1,
        "generated_fields": 1,
    }
    assert coverage["limitations"] == {
        "ambiguous_unqualified": 1,
        "relation_unavailable": 1,
    }

    relation_page = query.list_sql_relations(repo_id="repo-sql", include_fields=False)
    assert relation_page["coverage"]["source_inventory"] == coverage


def test_sql_column_usage_context_exposes_scope_without_inference(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path, include_source_coverage=True), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    context = query.get_sql_column_usage_context("col-ambiguous")
    assert context["usage"]["column_name"] == "id"
    assert context["usage"]["resolution_status"] == "ambiguous"
    assert context["usage"]["resolution_basis"] == "ambiguous_unqualified"
    assert context["scope"]["sql_select_scope_id"] == "scope-generated"
    assert context["statement"]["sql_statement_id"] == "stmt-generated"
    assert {item["alias"] for item in context["scope_relations"]} == {"ind", "bd", "participant"}
    assert context["counts"] == {"scope_relations": 3, "joins": 1, "projections": 1}
    assert context["joins"][0]["predicate"] == "ind.id = bd.id"
    assert context["projections"][0]["source_column_usage_ids_json"] == ["col-ambiguous"]
    assert all("observed_fields" in item for item in context["scope_relations"])

    missing = query.get_sql_column_usage_context("missing")
    assert missing == {
        "kind": "knowledge-layer-sql-column-usage-context",
        "sql_column_usage_id": "missing",
        "not_found": True,
    }


def test_target_column_lineage_query_preserves_all_terminal_branches_and_gaps(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    result = query.list_sql_target_column_lineage(
        "mart.client_profile",
        repo_id="repo-sql",
        max_results=10,
    )

    assert result["schema_version"] == "sql-target-column-lineage/v1"
    assert result["total_count"] == 3
    assert result["summary"] == {
        "path_count": 3,
        "target_column_count": 2,
        "terminal_source_count": 2,
        "max_recursion_depth": 2,
        "by_lineage_status": {"confirmed": 2, "partial": 1},
        "by_recursive_resolution_status": {"partial": 1, "resolved": 2},
        "by_physical_origin_status": {"confirmed": 2, "unresolved": 1},
        "by_target_mapping_status": {"confirmed": 3},
        "workflow_target_logical_name": None,
        "workflow_target_resolution_status": None,
    }
    normalized = [item for item in result["items"] if item["target_column"] == "normalized_name"]
    assert [(item["terminal_relation_name"], item["terminal_column"]) for item in normalized] == [
        ("src.client", "name"),
        ("src.client_alias", "name"),
    ]
    assert normalized[0]["branch_path_json"][0]["intermediate_relation_name"] == "prepared"
    assert normalized[0]["transformation_path_json"][-1]["expression"] == "upper(c.name)"
    assert result["gap_count"] == 1
    assert result["gaps_by_kind"] == {"ambiguous_source_relation": 1}
    assert result["gaps"][0]["target_column"] == "region_name"

    field = query.list_sql_target_column_lineage(
        "mart.client_profile",
        target_column="normalized_name",
        repo_id="repo-sql",
        max_results=1,
    )
    assert field["total_count"] == 2
    assert field["returned_count"] == 1
    assert field["truncated"] is True

    calculation = query.get_sql_field_calculation(
        "mart.client_profile",
        "normalized_name",
        repo_id="repo-sql",
    )
    assert calculation["schema_version"] == "sql-field-calculation/v1"
    assert calculation["coverage_status"] == "complete"
    assert calculation["lineage_path_count"] == 2
    assert calculation["terminal_source_count"] == 2
    assert {(item["relation_name"], item["column_name"]) for item in calculation["terminal_sources"]} == {
        ("src.client", "name"),
        ("src.client_alias", "name"),
    }
    assert {item["expression"] for item in calculation["calculations"]} == {"upper(c.name)", "upper(a.name)"}
    assert field["next_token"]
    assert field["gap_count"] == 0
    second = query.list_sql_target_column_lineage(
        "mart.client_profile",
        target_column="normalized_name",
        repo_id="repo-sql",
        max_results=1,
        page_token=field["next_token"],
    )
    assert second["returned_count"] == 1
    assert second["truncated"] is False
    assert second["items"][0]["sql_recursive_column_lineage_id"] != field["items"][0]["sql_recursive_column_lineage_id"]



def test_workflow_target_lineage_materialization_and_query_projection(tmp_path: Path) -> None:
    from knowledge_layer_core.sql_workflow_target_lineage import materialize_sql_workflow_target_lineage
    import duckdb

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    db = output / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    # Reuse typed rows from the fixture and change only identities needed by this workflow-only target.
    con.execute(
        "INSERT INTO sql_workflow_binding SELECT * REPLACE ("
        "'workflow-binding-only' AS sql_workflow_binding_id, 'workflow/only.yaml' AS file, "
        "'workflow_only' AS scalar_value, 'workflow_only' AS value_expression) "
        "FROM sql_workflow_binding WHERE sql_workflow_binding_id='workflow-binding-main'"
    )
    con.execute(
        "INSERT INTO sql_relation SELECT * REPLACE ("
        "'rel-workflow-target-read' AS sql_relation_id, 'q-downstream' AS query_id, "
        "'scope-downstream' AS scope_id, 'sql/downstream.sql' AS file, "
        "'mart.workflow_only' AS relation_name, 'workflow_only' AS logical_name, 'wf' AS alias) "
        "FROM sql_relation WHERE sql_relation_id='rel-output'"
    )
    con.execute(
        "INSERT INTO sql_statement SELECT * REPLACE ("
        "'stmt-workflow-only' AS sql_statement_id, 'q-workflow-only' AS query_id, "
        "'sql/workflow_only.sql' AS file, ['scope-workflow-only']::JSON AS select_scope_ids_json) "
        "FROM sql_statement WHERE sql_statement_id='stmt-generated'"
    )
    con.execute(
        "INSERT INTO sql_select_scope SELECT * REPLACE ("
        "'scope-workflow-only' AS sql_select_scope_id, 'q-workflow-only' AS query_id, "
        "'sql/workflow_only.sql' AS file, 1 AS relation_count, 1 AS projection_count, 1 AS column_usage_count) "
        "FROM sql_select_scope WHERE sql_select_scope_id='scope-generated'"
    )
    con.execute(
        "INSERT INTO sql_relation SELECT * REPLACE ("
        "'rel-workflow-source' AS sql_relation_id, 'q-workflow-only' AS query_id, "
        "'scope-workflow-only' AS scope_id, 'sql/workflow_only.sql' AS file, "
        "'physical' AS relation_kind, 'src.people' AS relation_name, 'people' AS logical_name, "
        "'p' AS alias, []::JSON AS source_scope_ids_json, []::JSON AS placeholder_refs_json) "
        "FROM sql_relation WHERE sql_relation_id='rel-generated-a'"
    )
    con.execute(
        "INSERT INTO sql_column_usage SELECT * REPLACE ("
        "'usage-workflow-source' AS sql_column_usage_id, 'q-workflow-only' AS query_id, "
        "'scope-workflow-only' AS scope_id, 'sql/workflow_only.sql' AS file, "
        "'first_name' AS column_name, 'p' AS table_or_alias, 'rel-workflow-source' AS relation_id, "
        "'physical' AS relation_kind, 'src.people' AS relation_name, 'resolved' AS resolution_status) "
        "FROM sql_column_usage WHERE sql_column_usage_id='col-1'"
    )
    con.execute(
        "INSERT INTO sql_projection SELECT * REPLACE ("
        "'projection-workflow-only' AS sql_projection_id, 'q-workflow-only' AS query_id, "
        "'scope-workflow-only' AS scope_id, 'sql/workflow_only.sql' AS file, "
        "'first_name' AS output_name, 'p.first_name' AS expression, 'column' AS expression_kind, "
        "['usage-workflow-source']::JSON AS source_column_usage_ids_json, 'resolved' AS resolution_status) "
        "FROM sql_projection WHERE sql_projection_id='projection-generated'"
    )
    con.execute(
        "INSERT INTO sql_workflow_file_reference VALUES ("
        "'ref-workflow-only', 'repo-sql', 'sql/driver.sql', 'script_invocation', 'invocation-only', 1, 1, "
        "'$datamart/wf/${main_table_name}/${main_table_name}.sql', 'sql/workflow_only.sql', 'sql', "
        "'resolved', 'exact_context_resolution', 1, '[\"sql/workflow_only.sql\"]', '[]')"
    )
    con.execute(
        "INSERT INTO sql_workflow_context_file VALUES ("
        "'context-workflow-only', 'repo-sql', 'workflow/only.yaml', 'sql/workflow_only.sql', 'sql', 1, "
        "'[\"workflow/only.yaml\",\"sql/workflow_only.sql\"]', '[\"ref-workflow-only\"]', "
        "'resolved', '[\"resolved_reference\"]')"
    )
    summary = materialize_sql_workflow_target_lineage(con, repo_id='repo-sql')
    con.close()

    assert summary['workflow_transform_count'] >= 1
    assert summary['lineage_path_count'] >= 1
    query = KnowledgeLayerQuery(output)
    result = query.list_sql_target_column_lineage(
        'mart.workflow_only', repo_id='repo-sql', max_results=10
    )
    assert result['total_count'] == 1
    assert result['summary']['workflow_target_logical_name'] == 'workflow_only'
    assert result['summary']['workflow_target_resolution_status'] == 'workflow_confirmed_unique'
    item = result['items'][0]
    assert item['target_column'] == 'first_name'
    assert item['target_relation_kind'] == 'workflow_resolved'
    assert item['target_mapping_status'] == 'workflow_confirmed_unique'
    assert (item['terminal_relation_name'], item['terminal_column']) == ('src.people', 'first_name')
    calculation = query.get_sql_field_calculation(
        'mart.workflow_only', 'first_name', repo_id='repo-sql'
    )
    assert calculation['coverage_status'] == 'complete'
    assert calculation['terminal_sources'][0]['relation_name'] == 'src.people'

def test_target_column_lineage_query_validates_exact_target_filters(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="target_relation_name"):
        query.list_sql_target_column_lineage(" ")
    with pytest.raises(ValueError, match="target_column"):
        query.list_sql_target_column_lineage("mart.client_profile", target_column=" ")
    with pytest.raises(ValueError, match="max_gaps"):
        query.list_sql_target_column_lineage("mart.client_profile", max_gaps=0)


def test_workflow_binding_query_preserves_literals_templates_and_evidence(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    result = query.list_sql_workflow_bindings(
        repo_id="repo-sql",
        binding_name="main_table_name",
        max_results=10,
    )

    assert result["schema_version"] == "sql-workflow-bindings/v1"
    assert result["total_count"] == 1
    assert result["summary"]["by_resolution_status"] == {"literal": 1}
    item = result["items"][0]
    assert item["scalar_value"] == "client_profile"
    assert item["binding_path"] == "param.main_table_name"
    assert item["referenced_placeholders_json"] == []
    assert item["evidence_json"][0]["relative_file"] == "workflow/client.yaml"
    assert "common.sql-workflow-bindings" in query.capabilities()

    template = query.list_sql_workflow_bindings(resolution_status="template")
    assert template["total_count"] == 1
    assert template["items"][0]["referenced_placeholders_json"] == ["main_table_name"]


def test_workflow_context_resolves_placeholder_only_through_referenced_sql_file(tmp_path: Path) -> None:
    manifest = build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    assert manifest["counts"]["sql_workflow_file_reference"] >= 1
    assert manifest["counts"]["sql_workflow_context_file"] >= 2
    assert manifest["counts"]["sql_placeholder_binding_resolution"] == 1
    files = query.list_sql_workflow_context_files(
        repo_id="repo-sql", reachable_file="sql/target.sql", max_results=10,
    )
    assert files["total_count"] == 1
    assert files["items"][0]["workflow_context_file"] == "workflow/client.yaml"
    assert files["items"][0]["context_hop_count"] == 1
    result = query.list_sql_placeholder_binding_resolutions(
        repo_id="repo-sql",
        sql_file="sql/target.sql",
        placeholder="main_table_name",
        max_results=10,
    )

    assert result["total_count"] == 1
    assert result["summary"]["by_resolution_status"] == {"resolved": 1}
    item = result["items"][0]
    assert item["workflow_context_file"] == "workflow/client.yaml"
    assert item["resolved_value"] == "client_profile"
    assert item["context_files_json"] == ["workflow/client.yaml", "sql/target.sql"]
    assert item["context_hop_count"] == 1
    assert "common.sql-workflow-context" in query.capabilities()


def test_sql_target_candidates_rank_published_business_target_before_intermediate(tmp_path: Path) -> None:
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True), tmp_path / "knowledge"
    )
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    result = query.find_sql_target_candidates(
        repo_id="repo-sql",
        business_entity_hints=["client"],
        max_results=10,
    )

    assert result["schema_version"] == "sql-target-candidates/v1"
    assert result["candidates"][0]["logical_target_name"] == "client_profile"
    assert result["candidates"][0]["recommended_target_relation"] == "mart.client_profile"
    assert result["candidates"][0]["target_relation_recommendation_status"] == "confirmed_unique"
    assert result["candidates"][0]["target_relation_recommendation_reasons"] == [
        "single_observed_target_relation"
    ]
    assert result["candidates"][0]["target_kind"] == "published_or_terminal"
    assert "target_consumed_outside_own_workflow" in result["candidates"][0]["reasons"]
    assert "observed_data_write" in result["candidates"][0]["reasons"]
    assert result["candidates"][0]["score"] > next(
        item["score"] for item in result["candidates"]
        if item["logical_target_name"] == "tmp_client"
    )
    assert "common.sql-target-resolution" in query.capabilities()


def test_sql_target_candidates_validate_limit(tmp_path: Path) -> None:
    build_sql_knowledge_layer(_artifact(tmp_path), tmp_path / "knowledge")
    query = KnowledgeLayerQuery(tmp_path / "knowledge")

    with pytest.raises(ValueError, match="max_results"):
        query.find_sql_target_candidates(max_results=0)


def test_sql_attribute_insertion_context_returns_best_observed_source_scope(tmp_path: Path) -> None:
    output = tmp_path / "knowledge-layer"
    build_sql_knowledge_layer(_artifact(tmp_path, include_semantic_roles=True), output)
    query = KnowledgeLayerQuery(output)

    result = query.resolve_sql_attribute_insertion_context(
        "client_profile",
        source_relation_hints=["client"],
        source_column_hints=["client_id"],
        max_results=10,
    )

    assert result["target"]["logical_target_name"] == "client_profile"
    assert result["target"]["target_sql_files"] == ["sql/target.sql"]
    assert result["recommended_insertion"]["file"] == "sql/load.sql"
    assert result["recommended_insertion"]["matched_relation_hints"] == ["client"]
    assert result["recommended_insertion"]["matched_column_hints"] == ["client_id"]
    assert result["recommended_insertion"]["propagation_status"] == "partial"
    assert "exact_propagation_path_to_target_not_observed" in result["recommended_insertion"]["diagnostics"]
    assert "recommended_scope_has_no_exact_end_to_end_target_dependency_path" in result["diagnostics"]
    assert "common.sql-attribute-insertion-context" in query.capabilities()


def test_sql_attribute_insertion_context_validates_required_hints(tmp_path: Path) -> None:
    output = tmp_path / "knowledge-layer"
    build_sql_knowledge_layer(_artifact(tmp_path, include_semantic_roles=True), output)
    query = KnowledgeLayerQuery(output)

    with pytest.raises(ValueError, match="source_relation_hints"):
        query.resolve_sql_attribute_insertion_context("client_profile", source_relation_hints=[])
    with pytest.raises(ValueError, match="max_results"):
        query.resolve_sql_attribute_insertion_context(
            "client_profile", source_relation_hints=["client"], max_results=0
        )


def test_workflow_target_lineage_reuses_single_relation_wildcard_traversal(tmp_path: Path) -> None:
    """A wildcard CTE with one observed input must propagate the requested column.

    This regression protects the canonical workflow target lineage from reintroducing
    a second weaker resolver beside SqlProducerColumnTraversal.  No source column is
    guessed when a wildcard scope has multiple relations; that ambiguity remains a gap.
    """
    from knowledge_layer_core.sql_workflow_target_lineage import materialize_sql_workflow_target_lineage
    import duckdb

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    db = output / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "INSERT INTO sql_workflow_binding SELECT * REPLACE ("
        "'workflow-binding-wildcard' AS sql_workflow_binding_id, 'workflow/wildcard.yaml' AS file, "
        "'workflow_wildcard' AS scalar_value, 'workflow_wildcard' AS value_expression) "
        "FROM sql_workflow_binding WHERE sql_workflow_binding_id='workflow-binding-main'"
    )
    con.execute(
        "INSERT INTO sql_statement SELECT * REPLACE ("
        "'stmt-workflow-wildcard' AS sql_statement_id, 'q-workflow-wildcard' AS query_id, "
        "'sql/workflow_wildcard.sql' AS file, ['scope-workflow-wildcard']::JSON AS select_scope_ids_json) "
        "FROM sql_statement WHERE sql_statement_id='stmt-generated'"
    )
    con.execute(
        "INSERT INTO sql_select_scope SELECT * REPLACE ("
        "'scope-workflow-wildcard' AS sql_select_scope_id, 'q-workflow-wildcard' AS query_id, "
        "'sql/workflow_wildcard.sql' AS file, 1 AS relation_count, 1 AS projection_count, 1 AS column_usage_count) "
        "FROM sql_select_scope WHERE sql_select_scope_id='scope-generated'"
    )
    con.execute(
        "INSERT INTO sql_select_scope SELECT * REPLACE ("
        "'scope-workflow-wild-source' AS sql_select_scope_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wildcard' AS parent_scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "1 AS relation_count, 1 AS projection_count, 0 AS column_usage_count) "
        "FROM sql_select_scope WHERE sql_select_scope_id='scope-generated'"
    )
    con.execute(
        "INSERT INTO sql_relation SELECT * REPLACE ("
        "'rel-workflow-wild-cte' AS sql_relation_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wildcard' AS scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "'cte' AS relation_kind, 'prepared' AS relation_name, 'prepared' AS logical_name, 'p' AS alias, "
        "['scope-workflow-wild-source']::JSON AS source_scope_ids_json) "
        "FROM sql_relation WHERE sql_relation_id='rel-generated-a'"
    )
    con.execute(
        "INSERT INTO sql_relation SELECT * REPLACE ("
        "'rel-workflow-wild-source' AS sql_relation_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wild-source' AS scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "'physical' AS relation_kind, 'src.people' AS relation_name, 'people' AS logical_name, 'src' AS alias, "
        "[]::JSON AS source_scope_ids_json, []::JSON AS placeholder_refs_json) "
        "FROM sql_relation WHERE sql_relation_id='rel-generated-a'"
    )
    con.execute(
        "INSERT INTO sql_column_usage SELECT * REPLACE ("
        "'usage-workflow-wild-root' AS sql_column_usage_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wildcard' AS scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "'first_name' AS column_name, 'p' AS table_or_alias, 'rel-workflow-wild-cte' AS relation_id, "
        "'cte' AS relation_kind, 'prepared' AS relation_name, 'resolved' AS resolution_status, "
        "'projection' AS usage_role) FROM sql_column_usage WHERE sql_column_usage_id='col-1'"
    )
    con.execute(
        "INSERT INTO sql_projection SELECT * REPLACE ("
        "'projection-workflow-wild-root' AS sql_projection_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wildcard' AS scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "'first_name' AS output_name, 'p.first_name' AS expression, 'column' AS expression_kind, false AS is_wildcard, "
        "['usage-workflow-wild-root']::JSON AS source_column_usage_ids_json, 'resolved' AS resolution_status) "
        "FROM sql_projection WHERE sql_projection_id='projection-generated'"
    )
    con.execute(
        "INSERT INTO sql_projection SELECT * REPLACE ("
        "'projection-workflow-wild-star' AS sql_projection_id, 'q-workflow-wildcard' AS query_id, "
        "'scope-workflow-wild-source' AS scope_id, 'sql/workflow_wildcard.sql' AS file, "
        "NULL AS output_name, '*' AS expression, 'wildcard' AS expression_kind, true AS is_wildcard, "
        "[]::JSON AS source_column_usage_ids_json, 'resolved' AS resolution_status) "
        "FROM sql_projection WHERE sql_projection_id='projection-generated'"
    )
    con.execute(
        "INSERT INTO sql_workflow_file_reference VALUES ("
        "'ref-workflow-wildcard', 'repo-sql', 'sql/driver.sql', 'script_invocation', 'invocation-wildcard', 1, 1, "
        "'$datamart/wf/${main_table_name}/${main_table_name}.sql', 'sql/workflow_wildcard.sql', 'sql', "
        "'resolved', 'exact_context_resolution', 1, '[\"sql/workflow_wildcard.sql\"]', '[]')"
    )
    con.execute(
        "INSERT INTO sql_workflow_context_file VALUES ("
        "'context-workflow-wildcard', 'repo-sql', 'workflow/wildcard.yaml', 'sql/workflow_wildcard.sql', 'sql', 1, "
        "'[\"workflow/wildcard.yaml\",\"sql/workflow_wildcard.sql\"]', '[\"ref-workflow-wildcard\"]', "
        "'resolved', '[\"resolved_reference\"]')"
    )
    summary = materialize_sql_workflow_target_lineage(con, repo_id='repo-sql')
    rows = con.execute(
        "SELECT terminal_relation_name, terminal_column FROM sql_workflow_target_column_lineage "
        "WHERE workflow_target_logical_name='workflow_wildcard' AND target_column='first_name'"
    ).fetchall()
    con.close()

    assert summary['lineage_path_count'] >= 1
    assert rows == [('src.people', 'first_name')]


def test_workflow_target_lineage_can_anchor_on_observed_final_materialization_without_dummy_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A final workflow materialization is a valid target anchor without a SQL projection.

    This protects the generic case used by workflows whose published target is produced by
    an observed copy/config transform rather than by a final `${main_table_name}.sql`
    invocation.  SQL query/projection identifiers must stay NULL rather than being
    fabricated merely to satisfy the historical schema shape.
    """
    import duckdb
    import knowledge_layer_core.sql_workflow_target_lineage as target_lineage

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"))
    con.execute(
        "INSERT INTO sql_workflow_binding SELECT * REPLACE ("
        "'workflow-binding-materialized' AS sql_workflow_binding_id, "
        "'workflow/materialized.yaml' AS file, 'final_mat' AS scalar_value, "
        "'final_mat' AS value_expression) "
        "FROM sql_workflow_binding WHERE sql_workflow_binding_id='workflow-binding-main'"
    )

    final_producer = {
        "id": "m-final",
        "workflow": "workflow/materialized.yaml",
        "kind": "workflow_copy",
        "table": "final_mat",
        "source_table": "stage_mat",
        "source_file": "workflow/pipeline.json",
        "provenance": {"binding_evidence": [{"relative_file": "workflow/pipeline.json", "line_start": 1}]},
    }

    class _Materializations:
        def producers(self, workflow: str, table: str):
            if workflow == "workflow/materialized.yaml" and table == "final_mat":
                return [(final_producer, [])]
            return []

        def output_contract(self, producer, seen=None):
            if producer.get("id") == "m-final":
                return {"value"}, "workflow_copy_source_materialization_contract"
            return None, "missing"

    class _Traversal:
        projections = {}
        materializations = _Materializations()

        def materialized_table_column_origins(self, workflow: str, table: str, column: str, *args):
            if (workflow, table, column) != ("workflow/materialized.yaml", "final_mat", "value"):
                return []
            return [{
                "relation_id": "r-observed-source",
                "column": "source_value",
                "materialization_path": ["m-final"],
                "workflow_dependency_path": [],
                "projection_path": [],
                "lineage_status": "confirmed",
                "evidence": [{"relative_file": "sql/stage.sql", "line_start": 3}],
            }]

    class _Observations:
        materializations = [final_producer]

    monkeypatch.setattr(target_lineage, "derive_sql_producer_observations", lambda *_a, **_k: _Observations())
    monkeypatch.setattr(
        target_lineage,
        "build_sql_producer_traversal",
        lambda *_a, **_k: (
            _Traversal(),
            {},
            {"r-observed-source": {"id": "r-observed-source", "kind": "physical", "name": "src.observed"}},
        ),
    )

    summary = target_lineage.materialize_sql_workflow_target_lineage(con, repo_id="repo-sql")
    row = con.execute(
        "SELECT query_id, root_projection_id, target_column, terminal_relation_name, terminal_column, "
        "mapping_basis, branch_path_json "
        "FROM sql_workflow_target_column_lineage "
        "WHERE workflow_context_file='workflow/materialized.yaml' AND workflow_target_logical_name='final_mat'"
    ).fetchone()
    con.close()

    assert summary["lineage_path_count"] >= 1
    assert row is not None
    assert row[0] is None
    assert row[1] is None
    assert row[2:5] == ("value", "src.observed", "source_value")
    assert "observed_final_materialization" in row[5]
    assert "workflow_target_materialization" in row[6]


def test_workflow_target_lineage_preserves_partial_final_contract_from_consistent_observed_source_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb
    import knowledge_layer_core.sql_workflow_target_lineage as target_lineage

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"))
    con.execute(
        "INSERT INTO sql_workflow_binding SELECT * REPLACE ("
        "'workflow-binding-partial-materialized' AS sql_workflow_binding_id, "
        "'workflow/partial-materialized.yaml' AS file, 'final_partial' AS scalar_value, "
        "'final_partial' AS value_expression) "
        "FROM sql_workflow_binding WHERE sql_workflow_binding_id='workflow-binding-main'"
    )

    final_producer = {
        "id": "m-final-partial", "workflow": "workflow/partial-materialized.yaml",
        "kind": "workflow_copy", "table": "final_partial", "source_table": "stage_partial",
        "source_file": "workflow/pipeline.json", "provenance": {},
    }
    complete_source = {
        "id": "m-stage-complete", "workflow": "workflow/partial-materialized.yaml",
        "kind": "sql_write", "table": "stage_partial", "source_file": "sql/stage.sql",
    }
    incomplete_source = {
        "id": "m-stage-incomplete", "workflow": "workflow/partial-materialized.yaml",
        "kind": "config_transform", "table": "stage_partial", "source_table": "missing_pre",
        "source_file": "sql/historicity.json", "provenance": {},
    }

    class _Materializations:
        def producers(self, workflow: str, table: str):
            if workflow != "workflow/partial-materialized.yaml":
                return []
            if table == "final_partial":
                return [(final_producer, [])]
            if table == "stage_partial":
                return [(complete_source, []), (incomplete_source, [])]
            return []

        def output_contract(self, producer, seen=None):
            if producer.get("id") == "m-final-partial":
                return None, "workflow_copy_source_contract_incomplete"
            if producer.get("id") == "m-stage-complete":
                return {"value"}, "sql_write_source_scope_output_contract"
            return None, "config_transform_source_producer_missing"

    class _Traversal:
        projections = {}
        materializations = _Materializations()

        def materialized_table_column_origins(self, workflow: str, table: str, column: str, *args):
            if (workflow, table, column) != ("workflow/partial-materialized.yaml", "final_partial", "value"):
                return []
            return [{
                "relation_id": "r-partial-source", "column": "source_value",
                "materialization_path": ["m-final-partial", "m-stage-complete"],
                "workflow_dependency_path": [], "projection_path": [],
                "recursive_resolution_status": "resolved", "physical_origin_status": "confirmed",
                "lineage_status": "confirmed", "evidence": [{"relative_file": "sql/stage.sql", "line_start": 3}],
            }]

    class _Observations:
        materializations = [final_producer, complete_source, incomplete_source]

    monkeypatch.setattr(target_lineage, "derive_sql_producer_observations", lambda *_a, **_k: _Observations())
    monkeypatch.setattr(
        target_lineage, "build_sql_producer_traversal",
        lambda *_a, **_k: (
            _Traversal(), {},
            {"r-partial-source": {"id": "r-partial-source", "kind": "physical", "name": "src.partial"}},
        ),
    )

    target_lineage.materialize_sql_workflow_target_lineage(con, repo_id="repo-sql")
    row = con.execute(
        "SELECT target_column, terminal_relation_name, terminal_column, recursive_resolution_status, "
        "lineage_status, mapping_basis, evidence_json FROM sql_workflow_target_column_lineage "
        "WHERE workflow_context_file='workflow/partial-materialized.yaml' AND workflow_target_logical_name='final_partial'"
    ).fetchone()
    gaps = con.execute(
        "SELECT gap_kind FROM sql_workflow_target_lineage_gap "
        "WHERE workflow_context_file='workflow/partial-materialized.yaml' AND workflow_target_logical_name='final_partial'"
    ).fetchall()
    con.close()

    assert row is not None
    assert row[:3] == ("value", "src.partial", "source_value")
    assert row[3] == "partial"
    assert row[4] == "partial"
    assert "partial_consistent_output_contract" in row[5]
    assert gaps == []


def test_workflow_target_lineage_uses_explicit_s2t_table_list_target_without_main_table_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb
    import knowledge_layer_core.sql_workflow_target_lineage as target_lineage

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"))

    final_producer = {
        "id": "m-s2t-final",
        "workflow": "workflow/s2t.yaml",
        "kind": "workflow_copy",
        "table": "final_s2t",
        "source_table": "stage_s2t",
        "source_file": "workflow/pipeline.json",
        "resolution_status": "matched",
        "mapping_basis": "observed_workflow_s2t_table_list",
        "provenance": {"binding_evidence": [{"relative_file": "workflow/pipeline.json", "line_start": 5}]},
    }

    class _Materializations:
        def producers(self, workflow: str, table: str):
            if workflow == "workflow/s2t.yaml" and table == "final_s2t":
                return [(final_producer, [])]
            return []

        def output_contract(self, producer, seen=None):
            if producer.get("id") == "m-s2t-final":
                return {"value"}, "workflow_copy_source_materialization_contract"
            return None, "missing"

    class _Traversal:
        projections = {}
        materializations = _Materializations()

        def materialized_table_column_origins(self, workflow: str, table: str, column: str, *args):
            if (workflow, table, column) != ("workflow/s2t.yaml", "final_s2t", "value"):
                return []
            return [{
                "relation_id": "r-s2t-source",
                "column": "source_value",
                "materialization_path": ["m-s2t-final"],
                "workflow_dependency_path": [],
                "projection_path": [],
                "lineage_status": "confirmed",
                "evidence": [{"relative_file": "sql/stage.sql", "line_start": 3}],
            }]

    class _Observations:
        materializations = [final_producer]

    monkeypatch.setattr(target_lineage, "derive_sql_producer_observations", lambda *_a, **_k: _Observations())
    monkeypatch.setattr(
        target_lineage,
        "build_sql_producer_traversal",
        lambda *_a, **_k: (
            _Traversal(),
            {},
            {"r-s2t-source": {"id": "r-s2t-source", "kind": "physical", "name": "src.s2t"}},
        ),
    )

    summary = target_lineage.materialize_sql_workflow_target_lineage(con, repo_id="repo-sql")
    row = con.execute(
        "SELECT workflow_context_file, workflow_target_logical_name, target_column, terminal_relation_name, terminal_column, mapping_basis "
        "FROM sql_workflow_target_column_lineage WHERE workflow_context_file='workflow/s2t.yaml'"
    ).fetchone()
    con.close()

    assert summary["lineage_path_count"] >= 1
    assert row is not None
    assert row[:5] == ("workflow/s2t.yaml", "final_s2t", "value", "src.s2t", "source_value")
    assert "observed_final_materialization" in row[5]


def test_workflow_target_lineage_uses_scoped_observed_workflow_copy_as_target_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb
    import knowledge_layer_core.sql_workflow_target_lineage as target_lineage

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"))

    final_producer = {
        "id": "m-scoped-s2t-final",
        "workflow": "resources/ctl/ctl.yml",
        "kind": "workflow_copy",
        "table": "final_scoped",
        "source_table": "stage_scoped",
        "source_file": "etl/workflows/pa/conf/b2c_sql_config.json",
        "resolution_status": "matched",
        "mapping_basis": "observed_scoped_parameter_environment_plus_referenced_s2t_table_list",
        "provenance": {
            "parameter_records": [{
                "name": "s2t.target.table.name",
                "value": "final_scoped",
                "evidence": [{"relative_file": "resources/ctl/ctl.yml", "line_start": 12}],
            }],
            "template_evidence": [{
                "relative_file": "etl/workflows/pa/conf/b2c_sql_config.json",
                "line_start": 42,
            }],
        },
    }

    class _Materializations:
        def producers(self, workflow: str, table: str):
            if workflow == "resources/ctl/ctl.yml" and table == "final_scoped":
                return [(final_producer, [])]
            return []

        def output_contract(self, producer, seen=None):
            if producer.get("id") == "m-scoped-s2t-final":
                return {"value"}, "workflow_copy_source_materialization_contract"
            return None, "missing"

    class _Traversal:
        projections = {}
        materializations = _Materializations()

        def materialized_table_column_origins(self, workflow: str, table: str, column: str, *args):
            if (workflow, table, column) != ("resources/ctl/ctl.yml", "final_scoped", "value"):
                return []
            return [{
                "relation_id": "r-scoped-source",
                "column": "source_value",
                "materialization_path": ["m-scoped-s2t-final"],
                "workflow_dependency_path": [],
                "projection_path": [],
                "lineage_status": "confirmed",
                "evidence": [{"relative_file": "sql/stage.sql", "line_start": 3}],
            }]

    class _Observations:
        materializations = [final_producer]

    monkeypatch.setattr(target_lineage, "derive_sql_producer_observations", lambda *_a, **_k: _Observations())
    monkeypatch.setattr(
        target_lineage,
        "build_sql_producer_traversal",
        lambda *_a, **_k: (
            _Traversal(),
            {},
            {"r-scoped-source": {"id": "r-scoped-source", "kind": "physical", "name": "src.scoped"}},
        ),
    )

    summary = target_lineage.materialize_sql_workflow_target_lineage(con, repo_id="repo-sql")
    row = con.execute(
        "SELECT workflow_context_file, workflow_target_logical_name, target_column, terminal_relation_name, terminal_column, evidence_json "
        "FROM sql_workflow_target_column_lineage WHERE workflow_context_file='resources/ctl/ctl.yml'"
    ).fetchone()
    con.close()

    assert summary["lineage_path_count"] >= 1
    assert row is not None
    assert row[:5] == ("resources/ctl/ctl.yml", "final_scoped", "value", "src.scoped", "source_value")
    assert "resources/ctl/ctl.yml" in str(row[5])
    assert "b2c_sql_config.json" in str(row[5])


def test_workflow_target_lineage_preserves_useful_partial_lineage_when_one_direct_branch_contract_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb
    import knowledge_layer_core.sql_workflow_target_lineage as target_lineage

    output = tmp_path / "knowledge"
    build_sql_knowledge_layer(
        _artifact(tmp_path, include_semantic_roles=True, include_source_coverage=True), output
    )
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"))

    complete_write = {
        "id": "m-write-complete",
        "workflow": "workflow/insurance.yaml",
        "kind": "sql_write",
        "table": "final_table",
        "source_file": "sql/final.sql",
        "source_scopes": ["scope-final"],
        "mapping_basis": "observed_sql_write_target_with_resolved_target_and_source_scope",
        "provenance": {},
    }
    incomplete_copy = {
        "id": "m-copy-incomplete",
        "workflow": "workflow/insurance.yaml",
        "kind": "workflow_copy",
        "table": "final_table",
        "source_table": "final_table_diff",
        "source_file": "workflow/move.json",
        "resolution_status": "matched",
        "mapping_basis": "observed_workflow_s2t_table_list",
        "provenance": {"binding_evidence": [{"relative_file": "workflow/move.json", "line_start": 10}]},
    }

    class _Materializations:
        def producers(self, workflow: str, table: str):
            if workflow == "workflow/insurance.yaml" and table == "final_table":
                return [(complete_write, []), (incomplete_copy, [])]
            return []

        def output_contract(self, producer, seen=None):
            if producer.get("id") == "m-write-complete":
                return {"value"}, "sql_write_source_scope_output_contract"
            if producer.get("id") == "m-copy-incomplete":
                return None, "workflow_copy_source_producer_missing"
            return None, "missing"

    class _Traversal:
        projections = {}
        materializations = _Materializations()

        def materialized_table_column_origins(self, workflow: str, table: str, column: str, *args):
            if (workflow, table, column) != ("workflow/insurance.yaml", "final_table", "value"):
                return []
            return [{
                "relation_id": "r-source",
                "column": "source_value",
                "materialization_path": ["m-write-complete"],
                "workflow_dependency_path": [],
                "projection_path": [],
                "recursive_resolution_status": "resolved",
                "physical_origin_status": "confirmed",
                "lineage_status": "confirmed",
                "evidence": [{"relative_file": "sql/final.sql", "line_start": 3}],
            }]

    class _Observations:
        materializations = [complete_write, incomplete_copy]

    monkeypatch.setattr(target_lineage, "derive_sql_producer_observations", lambda *_a, **_k: _Observations())
    monkeypatch.setattr(
        target_lineage,
        "build_sql_producer_traversal",
        lambda *_a, **_k: (
            _Traversal(),
            {},
            {"r-source": {"id": "r-source", "kind": "physical", "name": "src.observed"}},
        ),
    )

    summary = target_lineage.materialize_sql_workflow_target_lineage(con, repo_id="repo-sql")
    row = con.execute(
        "SELECT workflow_target_logical_name,target_column,terminal_relation_name,terminal_column,"
        "recursive_resolution_status,lineage_status,mapping_basis "
        "FROM sql_workflow_target_column_lineage WHERE workflow_context_file='workflow/insurance.yaml'"
    ).fetchone()
    gap = con.execute(
        "SELECT gap_kind,impact,mapping_basis FROM sql_workflow_target_lineage_gap "
        "WHERE workflow_context_file='workflow/insurance.yaml' AND workflow_target_logical_name='final_table'"
    ).fetchone()
    con.close()

    assert summary["lineage_path_count"] >= 1
    assert row is not None
    assert row[:4] == ("final_table", "value", "src.observed", "source_value")
    assert row[4] == "partial"
    assert row[5] == "partial"
    assert "partial_consistent_output_contract" in row[6]
    assert gap == (
        "workflow_target_materialization_branch_incomplete",
        "target_column_set_partial",
        "consistent_complete_direct_producer_contract_with_incomplete_sibling_branches",
    )


def test_workflow_target_lineage_aggregates_equivalent_technical_paths_without_merging_source_facts() -> None:
    from knowledge_layer_core.sql_workflow_target_lineage import _aggregate_equivalent_terminals

    common = {
        "terminal_source_kind": "column_usage",
        "terminal_column_usage_id": "usage-1",
        "terminal_relation_id": "relation-1",
        "terminal_relation_name": "src.table",
        "terminal_relation_kind": "physical",
        "terminal_column": "source_col",
        "transformations": [{"kind": "projection", "expression": "source_col"}],
        "recursive_resolution_status": "resolved",
        "physical_origin_status": "confirmed",
        "lineage_status": "confirmed",
    }
    rows = _aggregate_equivalent_terminals([
        {**common, "materialization_path": ["m2", "m3"], "workflow_dependency_path": ["d1"]},
        {**common, "materialization_path": ["m1"], "workflow_dependency_path": []},
        {
            **common,
            "terminal_column_usage_id": "usage-2",
            "terminal_column": "other_col",
            "materialization_path": ["m4"],
            "workflow_dependency_path": [],
        },
    ])

    assert len(rows) == 2
    aggregated = next(item for item in rows if item["terminal_column_usage_id"] == "usage-1")
    assert aggregated["materialization_path"] == ["m1"]
    assert aggregated["_equivalent_observed_path_count"] == 2
    assert aggregated["_equivalent_column_usage_ids"] == {"usage-1"}
    assert aggregated["_equivalent_materialization_ids"] == {"m1", "m2", "m3"}
    assert aggregated["_equivalent_workflow_dependency_ids"] == {"d1"}


def test_workflow_target_lineage_treats_passthrough_projection_ids_as_provenance() -> None:
    from knowledge_layer_core.sql_workflow_target_lineage import _aggregate_equivalent_terminals

    base = {
        "terminal_source_kind": "column_usage",
        "terminal_relation_id": "relation-1",
        "terminal_relation_name": "src.table",
        "terminal_relation_kind": "physical",
        "terminal_column": "source_col",
        "recursive_resolution_status": "resolved",
        "physical_origin_status": "confirmed",
        "lineage_status": "confirmed",
        "materialization_path": ["m1"],
        "workflow_dependency_path": [],
    }
    rows = _aggregate_equivalent_terminals([
        {**base, "terminal_column_usage_id": "usage-a", "transformations": [
            {"projection_id": "p-a", "expression_kind": "direct_column", "expression": "s.source_col"},
            {"projection_id": "p-root-a", "expression_kind": "normalization_or_cast", "expression": "cast(x as string)"},
        ]},
        {**base, "terminal_column_usage_id": "usage-b", "transformations": [
            {"projection_id": "p-b", "expression_kind": "direct_column", "expression": "q.source_col"},
            {"projection_id": "p-root-b", "expression_kind": "normalization_or_cast", "expression": "CAST(x AS STRING)"},
        ]},
        {**base, "terminal_column_usage_id": "usage-c", "transformations": [
            {"projection_id": "p-c", "expression_kind": "normalization_or_cast", "expression": "cast(x as bigint)"},
        ]},
    ])

    assert len(rows) == 2
    cast_string = next(item for item in rows if item["_equivalent_observed_path_count"] == 2)
    assert cast_string["_equivalent_column_usage_ids"] == {"usage-a", "usage-b"}
    assert cast_string["_equivalent_projection_ids"] == {"p-a", "p-b", "p-root-a", "p-root-b"}
