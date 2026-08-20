from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("duckdb")

from knowledge_layer_core import SQL_ANALYSIS_DDL
from prepared_knowledge_runtime import connect_database, initialize_schema

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService


def _create_sql_knowledge_layer(
    path: Path,
    *,
    include_context: bool = False,
    include_lineage: bool = False,
    include_target_resolution: bool = False,
) -> None:
    con = connect_database(path)
    initialize_schema(con, SQL_ANALYSIS_DDL)
    coverage = {
        "schema_version": "sql-analysis/v1",
        "analysis_status": "partial",
        "fact_counts": {"sql_relation": 1, "sql_column_usage": 2},
        "gaps": {"total": 1, "by_kind": {"target_column_unresolved": 1}},
    }
    con.execute(
        """
        INSERT INTO sql_analysis_repository(
            repo_id, sql_analysis_manifest, source_schema_version,
            source_content_fingerprint, analysis_status, system_name,
            project_code, analysis_profile, producer_name, producer_version,
            source_created_at, coverage_json, source_manifest_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "datamart_profile_fl",
            "sql-analysis-manifest.json",
            "sql-analysis/v1",
            "a" * 64,
            "partial",
            "Profile FL",
            "b2c",
            "sql-mart-lineage",
            "code-analyzer-core",
            "0.42.2",
            "2026-07-31T00:00:00Z",
            json.dumps(coverage),
            json.dumps({"schema_version": "sql-analysis/v1"}),
        ],
    )
    con.execute(
        """
        INSERT INTO sql_relation(
            sql_relation_id, repo_id, query_id, scope_id, file, line_start,
            relation_kind, relation_name, template_name, logical_name, alias,
            usage_role, definition_status, source_scope_ids_json,
            placeholder_refs_json, evidence_maturity_level, evidence_json,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "relation-1",
            "datamart_profile_fl",
            "query-1",
            "scope-1",
            "sql/client.sql",
            10,
            "physical_template",
            "${source_schema}.client",
            "${source_schema}.client",
            "client",
            "cl",
            "from",
            "not_applicable",
            "[]",
            '["source_schema"]',
            "observed",
            '[{"file":"sql/client.sql","line_start":10}]',
            '{"sql_relation_id":"relation-1"}',
        ],
    )
    con.execute(
        """
        INSERT INTO sql_relation(
            sql_relation_id, repo_id, query_id, scope_id, file, line_start,
            relation_kind, relation_name, template_name, logical_name, alias,
            usage_role, definition_status, source_scope_ids_json,
            placeholder_refs_json, evidence_maturity_level, evidence_json,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "relation-temp",
            "datamart_profile_fl",
            "query-temp",
            "scope-temp",
            "sql/temp.sql",
            5,
            "physical",
            "work.tmp_client",
            None,
            "tmp_client",
            "tmp",
            "from",
            "not_applicable",
            "[]",
            "[]",
            "observed",
            '[{"file":"sql/temp.sql","line_start":5}]',
            '{"sql_relation_id":"relation-temp"}',
        ],
    )
    con.executemany(
        """
        INSERT INTO sql_relation_semantic_role(
            sql_relation_semantic_role_id, repo_id, relation_kind, relation_identity,
            normalized_identity, template_name, logical_name, semantic_role,
            classification_status, hidden_by_default, classification_reasons_json,
            read_occurrence_count, write_occurrence_count, downstream_target_count,
            owned_namespace, technical_name_signal, dropped_in_repository, evidence_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            [
                "role-source", "datamart_profile_fl", "physical_template",
                "${source_schema}.client", "${source_schema}.client",
                "${source_schema}.client", "client", "external_source", "confirmed",
                False, '["read_without_local_write_evidence"]', 1, 0, 0, False, False, False,
                '[{"file":"sql/client.sql","line_start":10}]',
            ],
            [
                "role-temp", "datamart_profile_fl", "physical",
                "work.tmp_client", "work.tmp_client", None, "tmp_client",
                "internal_intermediate", "confirmed", True,
                '["written_inside_repository","read_to_build_another_local_target"]',
                1, 1, 1, True, True, False,
                '[{"file":"sql/temp.sql","line_start":5}]',
            ],
        ],
    )

    rows = [
        ("usage-1", "client_id", "projection", 12),
        ("usage-2", "status", "filter", 13),
    ]
    for usage_id, column_name, usage_role, line in rows:
        con.execute(
            """
            INSERT INTO sql_column_usage(
                sql_column_usage_id, repo_id, query_id, scope_id, file, line_start,
                column_name, column_ordinal, usage_role, table_or_alias, relation_id,
                relation_kind, relation_name, resolution_status, resolution_basis,
                evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                usage_id,
                "datamart_profile_fl",
                "query-1",
                "scope-1",
                "sql/client.sql",
                line,
                column_name,
                1,
                usage_role,
                "cl",
                "relation-1",
                "physical_template",
                "${source_schema}.client",
                "resolved",
                "qualified_alias",
                "observed",
                json.dumps([{"file": "sql/client.sql", "line_start": line}]),
                json.dumps({"sql_column_usage_id": usage_id}),
            ],
        )

    if include_context:
        con.execute(
            """
            INSERT INTO sql_statement(
                sql_statement_id, repo_id, query_id, file, line_start, line_end,
                operation, statement_hash, statement_type, target_relation_name, unit_kind,
                select_scope_ids_json, semantic_placeholders_json, write_target_ids_json,
                evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "statement-1", "datamart_profile_fl", "query-1", "sql/client.sql",
                10, 20, "select", "hash-1", "select", None, "query",
                '["scope-1"]', "[]", "[]", "observed",
                '[{"file":"sql/client.sql","line_start":10}]',
                '{"sql_statement_id":"statement-1"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_select_scope(
                sql_select_scope_id, repo_id, query_id, file, line_start, parent_scope_id,
                scope_kind, scope_name, scope_ordinal, expression_index, relation_count,
                projection_count, column_usage_count, evidence_maturity_level, evidence_json,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "scope-1", "datamart_profile_fl", "query-1", "sql/client.sql", 10, None,
                "select", "main", 0, 0, 2, 1, 3, "observed",
                '[{"file":"sql/client.sql","line_start":10}]',
                '{"sql_select_scope_id":"scope-1"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_relation(
                sql_relation_id, repo_id, query_id, scope_id, file, line_start,
                relation_kind, relation_name, template_name, logical_name, alias,
                usage_role, definition_status, source_scope_ids_json,
                placeholder_refs_json, evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "relation-2", "datamart_profile_fl", "query-1", "scope-1",
                "sql/client.sql", 11, "derived", "prepared", None, "prepared", "p",
                "join", "defined", '["scope-prepared"]', "[]", "observed",
                '[{"file":"sql/client.sql","line_start":11}]',
                '{"sql_relation_id":"relation-2"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_column_usage(
                sql_column_usage_id, repo_id, query_id, scope_id, file, line_start,
                column_name, column_ordinal, usage_role, table_or_alias, relation_id,
                relation_kind, relation_name, resolution_status, resolution_basis,
                evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "usage-ambiguous", "datamart_profile_fl", "query-1", "scope-1",
                "sql/client.sql", 14, "id", 1, "projection", None, None, None, None,
                "ambiguous", "ambiguous_unqualified", "observed",
                '[{"file":"sql/client.sql","line_start":14}]',
                '{"sql_column_usage_id":"usage-ambiguous"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_join_edge(
                sql_join_edge_id, repo_id, query_id, scope_id, file, line_start,
                join_ordinal, join_type, condition_kind, predicate, left_relation_id,
                left_relation_ids_json, left_relation_names_json, right_relation_id,
                right_relation_kind, right_relation_name, participating_relation_ids_json,
                column_pairs_json, expression_links_json, using_columns_json,
                additional_predicates_json, temporal_or_range_predicates_json,
                resolution_status, resolution_reasons_json, physical_join_confirmed,
                evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "join-1", "datamart_profile_fl", "query-1", "scope-1",
                "sql/client.sql", 11, 1, "inner", "on", "cl.id = p.id",
                "relation-1", '["relation-1"]', '["${source_schema}.client"]',
                "relation-2", "derived", "prepared", '["relation-1","relation-2"]',
                '[{"left":"cl.id","right":"p.id"}]', "[]", "[]", "[]", "[]",
                "resolved", "[]", False, "observed",
                '[{"file":"sql/client.sql","line_start":11}]',
                '{"sql_join_edge_id":"join-1"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_projection(
                sql_projection_id, repo_id, query_id, scope_id, file, line_start,
                projection_ordinal, output_name, expression, expression_kind, is_wildcard,
                source_column_count, source_column_usage_ids_json, resolution_status,
                resolution_basis, evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "projection-1", "datamart_profile_fl", "query-1", "scope-1",
                "sql/client.sql", 14, 1, "id", "id", "column", False, 1,
                '["usage-ambiguous"]', "ambiguous", "ambiguous_unqualified", "observed",
                '[{"file":"sql/client.sql","line_start":14}]',
                '{"sql_projection_id":"projection-1"}',
            ],
        )

    if include_lineage:
        lineage_columns = (
            "sql_recursive_column_lineage_id, repo_id, query_id, file, line_start, "
            "direct_lineage_id, write_target_id, target_projection_binding_id, "
            "target_relation_name, target_relation_kind, target_column, target_mapping_status, "
            "root_projection_id, root_expression, root_expression_kind, terminal_source_kind, "
            "terminal_column_usage_id, terminal_column, terminal_relation_id, terminal_relation_name, "
            "terminal_relation_kind, terminal_expression, terminal_expression_kind, recursion_depth, "
            "branch_path_json, transformation_path_json, recursive_resolution_status, "
            "physical_origin_status, lineage_status, evidence_maturity_level, evidence_json, payload_json"
        )
        lineage_rows = [
            [
                "recursive-normalized-a", "datamart_profile_fl", "query-lineage",
                "sql/target.sql", 10, "direct-normalized-a", "write-client-profile",
                "binding-normalized", "mart.client_profile", "physical", "normalized_name",
                "confirmed", "projection-normalized", "upper(c.name)",
                "normalization_or_cast", "column", "usage-source-name-a", "name",
                "relation-source-client", "src.client", "physical", "c.name", "direct_column",
                1, json.dumps([{
                    "intermediate_relation_name": "prepared",
                    "definition_branch_ordinal": 1,
                    "projection_output_name": "normalized_name",
                }]), json.dumps([
                    {"expression_kind": "direct_column", "expression": "c.name"},
                    {"expression_kind": "normalization_or_cast", "expression": "upper(c.name)"},
                ]), "resolved", "confirmed", "confirmed", "confirmed",
                json.dumps([{"relative_file": "sql/target.sql", "line_start": 10}]),
                json.dumps({"sql_recursive_column_lineage_id": "recursive-normalized-a"}),
            ],
            [
                "recursive-normalized-b", "datamart_profile_fl", "query-lineage",
                "sql/target.sql", 11, "direct-normalized-b", "write-client-profile",
                "binding-normalized", "mart.client_profile", "physical", "normalized_name",
                "confirmed", "projection-normalized", "upper(a.name)",
                "normalization_or_cast", "column", "usage-source-name-b", "name",
                "relation-source-alias", "src.client_alias", "physical", "a.name", "direct_column",
                2, json.dumps([{
                    "intermediate_relation_name": "combined",
                    "definition_branch_ordinal": 2,
                    "projection_output_name": "normalized_name",
                }]), json.dumps([
                    {"expression_kind": "direct_column", "expression": "a.name"},
                    {"expression_kind": "normalization_or_cast", "expression": "upper(a.name)"},
                ]), "resolved", "confirmed", "confirmed", "confirmed",
                json.dumps([{"relative_file": "sql/target.sql", "line_start": 11}]),
                json.dumps({"sql_recursive_column_lineage_id": "recursive-normalized-b"}),
            ],
            [
                "recursive-region-partial", "datamart_profile_fl", "query-lineage",
                "sql/target.sql", 12, "direct-region", "write-client-profile", "binding-region",
                "mart.client_profile", "physical", "region_name", "confirmed",
                "projection-region", "region_name", "direct_column", "unresolved",
                "usage-region", "region_name", None, None, None, "region_name", "direct_column",
                1, json.dumps([{
                    "intermediate_relation_name": "prepared",
                    "projection_output_name": "region_name",
                }]), json.dumps([
                    {"expression_kind": "direct_column", "expression": "region_name"},
                ]), "partial", "unresolved", "partial", "confirmed",
                json.dumps([{"relative_file": "sql/target.sql", "line_start": 12}]),
                json.dumps({"sql_recursive_column_lineage_id": "recursive-region-partial"}),
            ],
        ]
        placeholders = ", ".join("?" for _ in lineage_rows[0])
        con.executemany(
            f"INSERT INTO sql_recursive_column_lineage({lineage_columns}) VALUES ({placeholders})",
            lineage_rows,
        )

        gap_columns = (
            "sql_scoped_lineage_gap_id, repo_id, query_id, file, line_start, gap_kind, "
            "analysis_status, impact, write_target_id, target_relation_name, target_column, "
            "target_mapping_status, source_scope_id, projection_id, projection_resolution_status, "
            "mapping_basis, source_column_usage_id, source_column, table_or_alias, direct_lineage_id, "
            "source_relation_id, source_relation_name, source_relation_kind, recursion_depth, "
            "branch_path_json, evidence_maturity_level, evidence_json, payload_json"
        )
        gap_row = [
            "gap-region-ambiguous", "datamart_profile_fl", "query-lineage",
            "sql/target.sql", 12, "ambiguous_source_relation", "partial",
            "terminal_source_unresolved", "write-client-profile", "mart.client_profile",
            "region_name", "confirmed", "scope-region", "projection-region", "ambiguous",
            "ambiguous_unqualified", "usage-region", "region_name", None, "direct-region",
            None, None, None, 1, json.dumps([{
                "intermediate_relation_name": "prepared",
            }]), "confirmed",
            json.dumps([{"relative_file": "sql/target.sql", "line_start": 12}]),
            json.dumps({"sql_scoped_lineage_gap_id": "gap-region-ambiguous"}),
        ]
        con.execute(
            f"INSERT INTO sql_scoped_lineage_gap({gap_columns}) VALUES "
            f"({', '.join('?' for _ in gap_row)})",
            gap_row,
        )

    if include_target_resolution:
        con.execute(
            """
            INSERT INTO sql_workflow_binding(
                sql_workflow_binding_id, repo_id, file, line_start, line_end,
                config_format, binding_path, parent_path, binding_name, value_type,
                scalar_value, value_expression, referenced_placeholders_json,
                resolution_status, evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "binding-client-profile", "datamart_profile_fl", "workflow/client.yaml",
                5, 5, "yaml", "param.main_table_name", "param", "main_table_name",
                "string", "client_profile", "client_profile", "[]", "literal",
                "confirmed", '[{"relative_file":"workflow/client.yaml","line_start":5}]',
                '{"sql_workflow_binding_id":"binding-client-profile"}',
            ],
        )
        con.executemany(
            """
            INSERT INTO sql_workflow_context_file(
                sql_workflow_context_file_id, repo_id, workflow_context_file,
                reachable_file, reachable_file_kind, context_hop_count,
                context_files_json, context_reference_ids_json,
                resolution_status, resolution_reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                [
                    "context-client-source", "datamart_profile_fl", "workflow/client.yaml",
                    "sql/client.sql", "sql", 1,
                    '["workflow/client.yaml","sql/client.sql"]', '["ref-source"]',
                    "resolved", '["exact_repository_local_path"]',
                ],
                [
                    "context-client-target", "datamart_profile_fl", "workflow/client.yaml",
                    "sql/client_profile.sql", "sql", 1,
                    '["workflow/client.yaml","sql/client_profile.sql"]', '["ref-target"]',
                    "resolved", '["exact_repository_local_path"]',
                ],
            ],
        )
        con.execute(
            """
            INSERT INTO sql_write_target(
                sql_write_target_id, repo_id, query_id, file, line_start,
                operation_kind, target_relation_name, target_logical_name,
                target_relation_kind, target_placeholder_refs_json,
                explicit_target_columns_json, source_scope_ids_json, binding_mode,
                field_mapping_status, resolution_status, arity_status,
                branch_projection_counts_json, branch_wildcard_flags_json,
                count_mismatch, evidence_maturity_level, evidence_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "write-client-profile", "datamart_profile_fl", "query-target",
                "sql/client_profile.sql", 1, "insert", "mart.client_profile", "client_profile",
                "physical", "[]", "[]", '["scope-1"]', "ordinal", "resolved",
                "resolved", "matched", "[]", "[]", False, "confirmed",
                '[{"relative_file":"sql/client_profile.sql","line_start":1}]',
                '{"sql_write_target_id":"write-client-profile"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_relation(
                sql_relation_id, repo_id, query_id, scope_id, file, line_start,
                relation_kind, relation_name, template_name, logical_name, alias,
                usage_role, definition_status, source_scope_ids_json,
                placeholder_refs_json, evidence_maturity_level, evidence_json,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "relation-output-read", "datamart_profile_fl", "query-reconcile",
                "scope-reconcile", "sql/reconcile.sql", 4, "physical",
                "mart.client_profile", None, "client_profile", "cp", "from",
                "not_applicable", "[]", "[]", "confirmed",
                '[{"file":"sql/reconcile.sql","line_start":4}]',
                '{"sql_relation_id":"relation-output-read"}',
            ],
        )
        con.execute(
            """
            INSERT INTO sql_relation_semantic_role(
                sql_relation_semantic_role_id, repo_id, relation_kind,
                relation_identity, normalized_identity, template_name, logical_name,
                semantic_role, classification_status, hidden_by_default,
                classification_reasons_json, read_occurrence_count,
                write_occurrence_count, downstream_target_count, owned_namespace,
                technical_name_signal, dropped_in_repository, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "role-client-profile", "datamart_profile_fl", "physical",
                "mart.client_profile", "mart.client_profile", None, "client_profile",
                "output_target", "confirmed", False,
                '["written_inside_repository","not_read_to_build_another_local_target"]',
                1, 1, 0, True, False, False,
                '[{"file":"sql/client_profile.sql","line_start":1}]',
            ],
        )

    con.execute("CHECKPOINT")
    con.close()


def _publication(database: Path) -> dict:
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    execution_result = write_execution_result(
        database.parent,
        [
            KnowledgeArtifactSpec(
                database=database,
                model_kind="sql-observed-data-usage",
                schema_version="knowledge_layer_sql/v2",
                materialization_id="sql-analysis",
                capabilities=(
                    "common.sql-analysis",
                    "common.sql-relation-fields",
                    "common.sql-source-inventory",
                    "common.sql-source-inventory-export",
                    "common.sql-relation-semantic-roles",
                    "common.sql-target-column-lineage",
                    "common.sql-field-calculation",
                    "common.sql-target-resolution",
                    "common.sql-attribute-insertion-context",
                ),
            )
        ],
        scope_id="profile-fl",
        execution_token="sql-run-1",
    )
    return publication_payload(execution_result)



def test_sql_artifact_selection_prefers_workspace_catalog_over_repository_artifact(tmp_path: Path) -> None:
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    service = KnowledgeDomainService(settings)
    revision = {
        "knowledge_artifacts": [
            {
                "artifact_id": "repo-sql",
                "model_kind": "sql-observed-data-usage",
                "capabilities": ["common.sql-analysis", "common.sql-source-inventory"],
                "database": {"sha256": "a" * 64},
            },
            {
                "artifact_id": "workspace-sql",
                "model_kind": "workspace-sql-catalog",
                "capabilities": [
                    "common.sql-analysis",
                    "common.sql-source-inventory",
                    "common.workspace-sql-catalog",
                ],
                "database": {"sha256": "b" * 64},
            },
        ]
    }

    selected = service._sql_artifact_record(
        revision,
        required_capability="common.sql-analysis",
    )

    assert selected["artifact_id"] == "workspace-sql"
    assert selected["model_kind"] == "workspace-sql-catalog"


def test_sql_artifact_selection_uses_repository_artifact_without_workspace_catalog(tmp_path: Path) -> None:
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    service = KnowledgeDomainService(settings)
    revision = {
        "knowledge_artifacts": [
            {
                "artifact_id": "repo-sql",
                "model_kind": "sql-observed-data-usage",
                "capabilities": ["common.sql-analysis"],
                "database": {"sha256": "a" * 64},
            }
        ]
    }

    selected = service._sql_artifact_record(
        revision,
        required_capability="common.sql-analysis",
    )

    assert selected["artifact_id"] == "repo-sql"

def test_sql_only_revision_can_be_published_and_queried(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        created = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        )
        assert created.status_code == 201, created.text
        published = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        assert published.status_code == 201, published.text
        revision_id = published.json()["revision"]["revision_id"]

        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/relations",
            params={
                "revision_id": revision_id,
                "repo_id": "datamart_profile_fl",
                "include_fields": "true",
            },
        )
        data_model_response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/data-model/tables"
        )
    assert response.status_code == 200, response.text
    assert data_model_response.status_code == 409
    assert data_model_response.json()["code"] == "knowledge_artifact_unavailable"
    payload = response.json()
    assert payload["system_id"] == "profile-fl"
    assert payload["revision_id"] == revision_id
    assert payload["page"] == {"offset": 0, "limit": 50, "total": 1}
    assert payload["coverage"]["analysis_status"] == "partial"
    assert payload["coverage"]["relation_classification"]["total_relations"] == 2
    assert payload["coverage"]["relation_classification"]["hidden_by_default"] == 1
    source_inventory = payload["coverage"]["source_inventory"]
    assert source_inventory["status"] == "complete"
    assert source_inventory["column_usages"] == {
        "total": 2,
        "relation_field_candidates": 2,
        "resolved_relation_fields": 2,
        "unresolved_relation_fields": 0,
        "relation_field_resolution_rate": 1.0,
    }
    assert source_inventory["non_source_values"] == {
        "semantic_parameters": 0,
        "projection_outputs": 0,
        "generated_fields": 0,
    }
    assert source_inventory["limitations"] == {}
    assert payload["coverage"]["repositories"][0]["coverage_json"]["gaps"]["total"] == 1

    relation = payload["items"][0]
    assert relation["relation_kind"] == "physical_template"
    assert relation["relation_identity"] == "${source_schema}.client"
    assert relation["resolved_names"] == []
    assert relation["semantic_role"] == "external_source"
    assert relation["classification_status"] == "confirmed"
    assert relation["hidden_by_default"] is False
    assert {field["name"] for field in relation["fields"]} == {"client_id", "status"}
    roles = {field["name"]: field["usage_roles"] for field in relation["fields"]}
    assert roles == {"client_id": ["projection"], "status": ["filter"]}
    assert relation["evidence_count"] == 1
    assert relation["evidence_count_by_role"] == {"from": 1}
    assert relation["evidence_truncated"] is False
    assert relation["evidence_refs"] == [{
        "file": "sql/client.sql",
        "line_start": 10,
        "usage_role": "from",
        "query_id": "query-1",
        "scope_id": "scope-1",
        "evidence_id": "relation-1",
    }]


def test_sql_source_inventory_json_and_jsonl_exports_are_complete_and_stable(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        )
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        json_response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/source-inventory",
            params={"repo_id": "datamart_profile_fl", "max_evidence_per_role": 1},
        )
        jsonl_response_1 = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/source-inventory.jsonl",
            params={"repo_id": "datamart_profile_fl", "max_evidence_per_role": 1},
        )
        jsonl_response_2 = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/source-inventory.jsonl",
            params={"repo_id": "datamart_profile_fl", "max_evidence_per_role": 1},
        )

    assert json_response.status_code == 200, json_response.text
    payload = json_response.json()
    assert payload["inventory_schema_version"] == "sql-source-inventory/v1"
    assert payload["item_count"] == 1
    assert len(payload["items"]) == 1
    relation = payload["items"][0]
    assert relation["relation_identity"] == "${source_schema}.client"
    assert relation["field_count"] == 2
    assert relation["evidence_count"] == 1
    assert {field["name"] for field in relation["fields"]} == {"client_id", "status"}

    assert jsonl_response_1.status_code == 200, jsonl_response_1.text
    assert jsonl_response_1.headers["content-type"].startswith("application/x-ndjson")
    assert jsonl_response_1.headers["x-record-count"] == "2"
    assert jsonl_response_1.headers["x-content-sha256"] == jsonl_response_2.headers["x-content-sha256"]
    assert jsonl_response_1.content == jsonl_response_2.content
    records = [json.loads(line) for line in jsonl_response_1.text.splitlines()]
    assert records[0]["record_type"] == "inventory_metadata"
    assert records[0]["item_count"] == 1
    assert records[1]["record_type"] == "source_relation"
    assert records[1]["relation"]["relation_identity"] == "${source_schema}.client"


def test_sql_relation_endpoint_defaults_to_external_relations(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        )
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        without_fields = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/relations",
            params={"include_fields": "false", "search": "client"},
        )
    assert without_fields.status_code == 200, without_fields.text
    item = without_fields.json()["items"][0]
    assert "fields" not in item
    assert "field_count" not in item


def test_sql_relation_views_expose_technical_relations_only_on_request(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        )
        client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        default_response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/relations",
            params={"include_fields": "false"},
        )
        technical_response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/relations",
            params={"view": "technical", "include_fields": "false"},
        )
        all_response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/relations",
            params={"view": "all", "include_fields": "false"},
        )

    assert default_response.status_code == 200, default_response.text
    assert [item["relation_identity"] for item in default_response.json()["items"]] == [
        "${source_schema}.client"
    ]
    assert technical_response.status_code == 200, technical_response.text
    technical = technical_response.json()["items"]
    assert [item["relation_identity"] for item in technical] == ["work.tmp_client"]
    assert technical[0]["semantic_role"] == "internal_intermediate"
    assert technical[0]["hidden_by_default"] is True
    assert all_response.status_code == 200, all_response.text
    assert all_response.json()["page"]["total"] == 2


def test_sql_column_usage_context_returns_deterministic_scope(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database, include_context=True)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        created = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        )
        assert created.status_code == 201, created.text
        published = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        assert published.status_code == 201, published.text
        revision_id = published.json()["revision"]["revision_id"]

        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/column-usages/usage-ambiguous",
            params={"revision_id": revision_id},
        )
        missing = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/column-usages/missing-usage"
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["system_id"] == "profile-fl"
    assert payload["revision_id"] == revision_id
    assert payload["usage"]["column_name"] == "id"
    assert payload["usage"]["resolution_status"] == "ambiguous"
    assert payload["usage"]["resolution_basis"] == "ambiguous_unqualified"
    assert payload["statement"]["sql_statement_id"] == "statement-1"
    assert payload["scope"]["sql_select_scope_id"] == "scope-1"
    assert payload["counts"] == {"scope_relations": 2, "joins": 1, "projections": 1}
    assert {item["alias"] for item in payload["scope_relations"]} == {"cl", "p"}
    relation_by_id = {item["sql_relation_id"]: item for item in payload["scope_relations"]}
    assert {field["name"] for field in relation_by_id["relation-1"]["observed_fields"]} == {
        "client_id", "status"
    }
    assert relation_by_id["relation-2"]["observed_fields"] == []
    assert payload["joins"][0]["predicate"] == "cl.id = p.id"
    assert payload["projections"][0]["source_column_usage_ids"] == ["usage-ambiguous"]

    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "sql_column_usage_not_found"


def test_target_column_lineage_uses_canonical_sql_analysis_artifact_and_preserves_filters(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(database, include_lineage=True)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        ).status_code == 201
        published = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        assert published.status_code == 201, published.text
        revision_id = published.json()["revision"]["revision_id"]
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/target-column-lineage",
            params={
                "revision_id": revision_id,
                "target_relation": "mart.client_profile",
                "target_column": "normalized_name",
                "repo_id": "datamart_profile_fl",
                "lineage_status": "confirmed",
                "limit": 1,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["lineage_schema_version"] == "sql-target-column-lineage/v1"
    assert payload["system_id"] == "profile-fl"
    assert payload["revision_id"] == revision_id
    assert payload["target_relation_name"] == "mart.client_profile"
    assert payload["target_column"] == "normalized_name"
    assert payload["repo_id"] == "datamart_profile_fl"
    assert payload["lineage_status"] == "confirmed"
    assert payload["filters"]["repo_id"] == "datamart_profile_fl"
    assert payload["filters"]["lineage_status"] == "confirmed"
    assert payload["page"] == {"offset": 0, "limit": 1, "total": 2}
    assert len(payload["items"]) == 1
    assert payload["items"][0]["target_column"] == "normalized_name"
    assert payload["items"][0]["terminal_relation_name"] in {"src.client", "src.client_alias"}
    assert payload["items"][0]["transformation_path_json"][-1]["expression"].startswith("upper(")
    assert payload["summary"]["path_count"] == 2
    assert payload["summary"]["by_lineage_status"] == {"confirmed": 2}
    assert payload["gap_count"] == 0
    assert payload["gaps"] == []
    assert payload["gaps_by_kind"] == {}


def test_source_inventory_adapter_sorts_across_relation_kinds() -> None:
    from knowledge_api.sql_query import KnowledgeQueryAdapter

    class FakeQuery:
        def capabilities(self):
            return ("common.sql-source-inventory-export",)

        def export_sql_source_inventory(self, *, relation_kind, **kwargs):
            items = {
                "physical": [{
                    "repo_id": "repo", "relation_kind": "physical",
                    "relation_identity": "custom.source", "relation_id": "physical-1", "fields": [],
                }],
                "physical_template": [{
                    "repo_id": "repo", "relation_kind": "physical_template",
                    "relation_identity": "${source_schema}.client", "relation_id": "template-1", "fields": [],
                }],
            }
            return {"items": items[relation_kind], "coverage": {}}

    adapter = KnowledgeQueryAdapter.__new__(KnowledgeQueryAdapter)
    adapter.query = FakeQuery()
    result = adapter.export_sql_source_inventory(
        repo_id="repo", relation_kind=None, usage_role=None, view="business_sources",
        search=None, max_evidence_per_role=1,
    )
    assert [item["relation_identity"] for item in result["items"]] == [
        "${source_schema}.client", "custom.source",
    ]



def test_sql_target_candidates_endpoint_ranks_terminal_target(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(
        database,
        include_context=True,
        include_target_resolution=True,
    )
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        ).status_code == 201
        published = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        assert published.status_code == 201, published.text
        revision_id = published.json()["revision"]["revision_id"]
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/target-candidates",
            params=[
                ("revision_id", revision_id),
                ("repo_id", "datamart_profile_fl"),
                ("source_relation", "client"),
                ("source_column", "client_id"),
                ("business_entity", "client"),
                ("limit", "5"),
            ],
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["candidate_schema_version"] == "sql-target-candidates/v1"
    assert payload["system_id"] == "profile-fl"
    assert payload["revision_id"] == revision_id
    assert payload["returned_count"] == 1
    candidate = payload["candidates"][0]
    assert candidate["logical_target_name"] == "client_profile"
    assert candidate["target_kind"] == "published_or_terminal"
    assert "semantic_output_target" in candidate["reasons"]
    assert candidate["source_relation_matches"][0]["logical_name"] == "client"


def test_sql_attribute_insertion_context_endpoint_returns_best_scope(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    _create_sql_knowledge_layer(
        database,
        include_context=True,
        include_target_resolution=True,
    )
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    with TestClient(create_contract_app(settings=settings)) as client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "profile-fl", "display_name": "Profile FL"},
        ).status_code == 201
        published = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/revisions",
            json=_publication(database),
        )
        assert published.status_code == 201, published.text
        revision_id = published.json()["revision"]["revision_id"]
        response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/attribute-insertion-context",
            params={"revision_id": revision_id},
            json={
                "repo_id": "datamart_profile_fl",
                "target_relation": "client_profile",
                "source_relation_hints": ["client"],
                "source_column_hints": ["client_id"],
                "max_results": 5,
            },
        )
        invalid = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/profile-fl/sql/attribute-insertion-context",
            json={
                "target_relation": "client_profile",
                "source_relation_hints": [],
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["insertion_schema_version"] == "sql-attribute-insertion-context/v1"
    assert payload["system_id"] == "profile-fl"
    assert payload["revision_id"] == revision_id
    assert payload["target"]["logical_target_name"] == "client_profile"
    assert payload["target"]["target_sql_files"] == ["sql/client_profile.sql"]
    recommended = payload["recommended_insertion"]
    assert recommended["file"] == "sql/client.sql"
    assert recommended["matched_relation_hints"] == ["client"]
    assert recommended["matched_column_hints"] == ["client_id"]
    assert recommended["propagation_status"] == "resolved"
    assert recommended["scope_relations"][0]["evidence_json"] == [
        {"file": "sql/client.sql", "line_start": 10}
    ]

    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["code"] == "request_validation_failed"


def test_product_s2t_adapter_groups_value_rows_and_keeps_gap_only_targets() -> None:
    from knowledge_api.sql_query import KnowledgeQueryAdapter

    class FakeQuery:
        def capabilities(self):
            return ("common.sql-target-value-source-mapping",)

        def list_sql_target_value_sources(self, target_relation, **kwargs):
            return {
                "items": [
                    {"target_column":"epk_id","source_sql_relation_name":"${src}.individual","source_sql_column":"id","mapping_status":"partial"},
                    {"target_column":"epk_id","source_sql_relation_name":"hist.individual_hist","source_sql_column":"id","mapping_status":"resolved"},
                    {"target_column":"last_name","source_sql_relation_name":"${src}.individual_name","source_sql_column":"surname","mapping_status":"partial"},
                ],
                "total_count": 3, "next_token": None, "gap_count": 2,
                "gaps": [
                    {"gap_id":"g1","gap_kind":"source_relation_placeholder_unresolved","impact":"source_identity_incomplete","mapping_basis":"observed_binding","target_column":"epk_id","evidence":{}},
                    {"gap_id":"g2","gap_kind":"ultimate_source_identity_unresolved","impact":"source_identity_missing","mapping_basis":"terminal_identity_missing","target_column":"hash_val","evidence":{}},
                ],
            }

    adapter = KnowledgeQueryAdapter.__new__(KnowledgeQueryAdapter)
    adapter.query = FakeQuery()
    result = adapter.list_sql_target_value_sources(
        target_relation="mart.epk_client", target_column=None, include_gaps=True,
        max_gaps=10, offset=0, limit=10,
    )
    assert result["total_count"] == 3
    assert [item["target_column"] for item in result["mappings"]] == ["epk_id", "hash_val", "last_name"]
    epk = result["mappings"][0]
    assert epk["source_count"] == 2
    assert epk["mapping_status"] == "partial"
    assert result["mappings"][1] == {
        "target_column":"hash_val", "sources":[], "mapping_status":"unresolved",
        "source_count":0, "dependency_count":0,
    }
    assert result["summary"]["unresolved_placeholder_source_count"] == 2
    assert result["gap_count"] == 2
