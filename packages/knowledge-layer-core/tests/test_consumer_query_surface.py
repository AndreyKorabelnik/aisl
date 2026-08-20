from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("duckdb")
import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery


def test_relation_materialization_query_exposes_prepared_mapping(tmp_path: Path) -> None:
    db = tmp_path / "cross.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE cross_artifact_relation_materialization (
        materialization_id VARCHAR, workflow_context_file VARCHAR, materialization_kind VARCHAR,
        source_file VARCHAR, source_fact_id VARCHAR, source_symbol VARCHAR, query_file VARCHAR,
        query_id VARCHAR, source_table_name VARCHAR, output_table_name VARCHAR,
        resolution_status VARCHAR, knowledge_class VARCHAR, mapping_basis VARCHAR, provenance_json JSON
    )""")
    con.execute(
        "INSERT INTO cross_artifact_relation_materialization VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            "mat-1", "workflow.yaml", "script_call", "prep.sql", "call-1", "runAndSaveSqlHdfs",
            "stg_individual_bv.sql", "query-145", None, "stg_individual_bv",
            "matched", "derived", "structured_script_call", '{"evidence":"observed"}',
        ],
    )
    con.close()

    result = KnowledgeLayerQuery(db).list_relation_materializations(
        output_table_name="STG_INDIVIDUAL_BV", max_results=20
    )
    assert result["not_available"] is False
    assert result["total_count"] == 1
    item = result["items"][0]
    assert item["query_id"] == "query-145"
    assert item["query_file"] == "stg_individual_bv.sql"
    assert item["resolution_status"] == "matched"
    assert item["provenance_json"] == {"evidence": "observed"}


def test_sql_query_context_selects_root_scope_and_final_projection(tmp_path: Path) -> None:
    db = tmp_path / "sql.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE sql_select_scope (
        sql_select_scope_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, file VARCHAR, line_start BIGINT,
        parent_scope_id VARCHAR, scope_kind VARCHAR, scope_name VARCHAR, scope_ordinal BIGINT,
        expression_index BIGINT, relation_count BIGINT, projection_count BIGINT,
        column_usage_count BIGINT, evidence_maturity_level VARCHAR, evidence_json JSON
    )""")
    con.execute("""CREATE TABLE sql_statement (
        sql_statement_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, file VARCHAR, line_start BIGINT,
        line_end BIGINT, operation VARCHAR, statement_type VARCHAR, target_relation_name VARCHAR,
        unit_kind VARCHAR, evidence_maturity_level VARCHAR, evidence_json JSON
    )""")
    con.execute("""CREATE TABLE sql_relation (
        sql_relation_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, scope_id VARCHAR, file VARCHAR,
        line_start BIGINT, relation_kind VARCHAR, relation_name VARCHAR, template_name VARCHAR,
        logical_name VARCHAR, alias VARCHAR, usage_role VARCHAR, definition_status VARCHAR,
        source_scope_ids_json JSON, placeholder_refs_json JSON, evidence_maturity_level VARCHAR,
        evidence_json JSON
    )""")
    con.execute("""CREATE TABLE sql_column_usage (
        sql_column_usage_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, scope_id VARCHAR, file VARCHAR,
        line_start BIGINT, column_name VARCHAR, column_ordinal BIGINT, usage_role VARCHAR,
        table_or_alias VARCHAR, relation_id VARCHAR, relation_kind VARCHAR, relation_name VARCHAR,
        resolution_status VARCHAR, resolution_basis VARCHAR, evidence_maturity_level VARCHAR,
        evidence_json JSON
    )""")
    con.execute("""CREATE TABLE sql_join_edge (
        sql_join_edge_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, scope_id VARCHAR, file VARCHAR,
        line_start BIGINT, join_ordinal BIGINT, join_type VARCHAR, condition_kind VARCHAR, predicate VARCHAR,
        left_relation_id VARCHAR, left_relation_ids_json JSON, left_relation_names_json JSON,
        right_relation_id VARCHAR, right_relation_kind VARCHAR, right_relation_name VARCHAR,
        participating_relation_ids_json JSON, column_pairs_json JSON, expression_links_json JSON,
        using_columns_json JSON, additional_predicates_json JSON, temporal_or_range_predicates_json JSON,
        resolution_status VARCHAR, resolution_reasons_json JSON, physical_join_confirmed BOOLEAN,
        evidence_maturity_level VARCHAR, evidence_json JSON
    )""")
    con.execute("""CREATE TABLE sql_projection (
        sql_projection_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, scope_id VARCHAR, file VARCHAR,
        line_start BIGINT, projection_ordinal BIGINT, output_name VARCHAR, expression VARCHAR,
        expression_kind VARCHAR, is_wildcard BOOLEAN, source_column_count BIGINT,
        source_column_usage_ids_json JSON, resolution_status VARCHAR, resolution_basis VARCHAR,
        evidence_maturity_level VARCHAR, evidence_json JSON
    )""")
    con.execute("INSERT INTO sql_select_scope VALUES ('root','repo','q','bv.sql',1,NULL,'statement',NULL,1,1,1,2,1,'observed','[]')")
    con.execute("INSERT INTO sql_select_scope VALUES ('cte','repo','q','bv.sql',1,'root','cte','pre_u',2,1,1,1,0,'observed','[]')")
    con.execute("INSERT INTO sql_statement VALUES ('stmt','repo','q','bv.sql',1,100,NULL,'select',NULL,'query','observed','[]')")
    con.execute("INSERT INTO sql_relation VALUES ('rel','repo','q','root','bv.sql',83,'physical','stg_union',NULL,'stg_union','u','read','not_applicable','[]','[]','observed','[]')")
    con.execute("INSERT INTO sql_column_usage VALUES ('usage','repo','q','root','bv.sql',99,'countryresident',1,'projection','u','rel','physical','stg_union','resolved','qualified_alias','observed','[]')")
    con.execute("INSERT INTO sql_projection VALUES ('p1','repo','q','root','bv.sql',83,1,'countryresident','countryresident','direct_column',false,1,'[\"usage\"]','resolved','scoped_ast','observed','[]')")
    con.execute("INSERT INTO sql_projection VALUES ('p2','repo','q','root','bv.sql',83,2,'partystatus','partystatus','direct_column',false,0,'[]','resolved','scoped_ast','observed','[]')")
    con.close()

    result = KnowledgeLayerQuery(db).get_sql_query_context(repo_id="repo", query_id="q")
    assert result["selection_status"] == "selected"
    assert result["scope"]["sql_select_scope_id"] == "root"
    assert [row["output_name"] for row in result["projections"]] == ["countryresident", "partystatus"]
    assert result["child_scopes"][0]["scope_name"] == "pre_u"
    assert result["scope_relations"][0]["observed_fields"] == [
        {"name": "countryresident", "usage_roles": ["projection"]}
    ]


def test_sql_query_context_does_not_guess_multiple_roots(tmp_path: Path) -> None:
    db = tmp_path / "ambiguous.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE sql_select_scope (
        sql_select_scope_id VARCHAR, repo_id VARCHAR, query_id VARCHAR, file VARCHAR, line_start BIGINT,
        parent_scope_id VARCHAR, scope_kind VARCHAR, scope_name VARCHAR, scope_ordinal BIGINT,
        expression_index BIGINT, relation_count BIGINT, projection_count BIGINT,
        column_usage_count BIGINT, evidence_maturity_level VARCHAR, evidence_json JSON
    )""")
    con.execute("INSERT INTO sql_select_scope VALUES ('a','repo','q','x.sql',1,NULL,'statement',NULL,1,1,0,0,0,'observed','[]')")
    con.execute("INSERT INTO sql_select_scope VALUES ('b','repo','q','x.sql',1,NULL,'statement',NULL,2,1,0,0,0,'observed','[]')")
    con.close()
    result = KnowledgeLayerQuery(db).get_sql_query_context(repo_id="repo", query_id="q")
    assert result["selection_status"] == "ambiguous"
    assert len(result["scope_candidates"]) == 2
    assert result["diagnostics"] == ["multiple_sql_scope_candidates"]
