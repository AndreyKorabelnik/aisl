from __future__ import annotations

import json

import duckdb

from knowledge_layer_core.sql_producer_observations import derive_sql_producer_observations


def _base_connection() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE sql_workflow_binding(sql_workflow_binding_id VARCHAR,repo_id VARCHAR,file VARCHAR,line_start BIGINT,binding_name VARCHAR,scalar_value VARCHAR,value_expression VARCHAR,binding_path VARCHAR,evidence_json JSON)")
    c.execute("CREATE TABLE sql_workflow_context_file(repo_id VARCHAR,workflow_context_file VARCHAR,reachable_file VARCHAR,resolution_status VARCHAR)")
    c.execute("CREATE TABLE sql_statement(repo_id VARCHAR,query_id VARCHAR,file VARCHAR)")
    c.execute("CREATE TABLE sql_select_scope(repo_id VARCHAR,query_id VARCHAR,parent_scope_id VARCHAR)")
    c.execute("CREATE TABLE sql_script_statement(repo_id VARCHAR,sql_script_statement_id VARCHAR,file VARCHAR,line_start BIGINT,statement_preview VARCHAR)")
    c.execute("CREATE TABLE sql_script_binding(repo_id VARCHAR,file VARCHAR,line_start BIGINT,binding_name VARCHAR,value_expression VARCHAR,scalar_value VARCHAR)")
    c.execute("CREATE TABLE sql_script_call(repo_id VARCHAR,sql_script_call_id VARCHAR,file VARCHAR,line_start BIGINT,call_symbol VARCHAR,named_arguments_json JSON,positional_arguments_json JSON,evidence_json JSON)")
    return c


def test_literal_list_index_loop_correlates_query_file_and_output_table_without_cartesian_product() -> None:
    c = _base_connection()
    repo = "r"; wf = "workflow.yaml"; script = "wf/dictionaries/calc.sql"
    c.execute("INSERT INTO sql_workflow_context_file VALUES (?,?,?,?)", [repo, wf, script, "resolved"])
    for query_id, file in [("qa", "wf/dictionaries/dict_a.sql"), ("qb", "wf/dictionaries/dict_b.sql")]:
        c.execute("INSERT INTO sql_statement VALUES (?,?,?)", [repo, query_id, file])
        c.execute("INSERT INTO sql_select_scope VALUES (?,?,?)", [repo, query_id, None])
    c.execute("INSERT INTO sql_script_statement VALUES (?,?,?,?,?)", [repo, "s-loop", script, 20, "for i in 0..(size($dict_table_names)-1) loop let table_name = '${$dict_table_names[$i]}'"])
    c.execute("INSERT INTO sql_script_binding VALUES (?,?,?,?,?,?)", [repo, script, 10, "dict_table_names", "['dict_a','dict_b']", None])
    c.execute("INSERT INTO sql_script_binding VALUES (?,?,?,?,?,?)", [repo, script, 21, "query_path", '"$root/wf/dictionaries/${$table_name}.sql"', "$root/wf/dictionaries/${$table_name}.sql"])
    c.execute("INSERT INTO sql_script_call VALUES (?,?,?,?,?,?,?,?)", [repo, "call", script, 30, "runAndSaveSqlHdfs", json.dumps({"queryPath":"$query_path","tableName":"$table_name"}), json.dumps([]), json.dumps([])])

    observed = derive_sql_producer_observations(c, repo_id=repo)
    rows = [m for m in observed.materializations if m["kind"] == "script_call"]
    assert {(m["query_file"], m["table"]) for m in rows} == {
        ("wf/dictionaries/dict_a.sql", "dict_a"),
        ("wf/dictionaries/dict_b.sql", "dict_b"),
    }
    assert all(m["mapping_basis"] == "structured_script_call_plus_observed_literal_loop_candidate_correlation" for m in rows)


def test_computed_list_is_not_interpreted_as_loop_candidates() -> None:
    c = _base_connection()
    repo = "r"; wf = "workflow.yaml"; script = "wf/calc.sql"
    c.execute("INSERT INTO sql_workflow_context_file VALUES (?,?,?,?)", [repo, wf, script, "resolved"])
    c.execute("INSERT INTO sql_statement VALUES (?,?,?)", [repo, "qa", "wf/dict_a.sql"])
    c.execute("INSERT INTO sql_select_scope VALUES (?,?,?)", [repo, "qa", None])
    c.execute("INSERT INTO sql_script_statement VALUES (?,?,?,?,?)", [repo, "s-loop", script, 20, "for i in 0..(size($names)-1) loop let table_name = '${$names[$i]}'"])
    c.execute("INSERT INTO sql_script_binding VALUES (?,?,?,?,?,?)", [repo, script, 10, "names", "load_names()", None])
    c.execute("INSERT INTO sql_script_binding VALUES (?,?,?,?,?,?)", [repo, script, 21, "query_path", '"$root/wf/${$table_name}.sql"', "$root/wf/${$table_name}.sql"])
    c.execute("INSERT INTO sql_script_call VALUES (?,?,?,?,?,?,?,?)", [repo, "call", script, 30, "runAndSaveSqlHdfs", json.dumps({"queryPath":"$query_path","tableName":"$table_name"}), json.dumps([]), json.dumps([])])

    observed = derive_sql_producer_observations(c, repo_id=repo)
    assert [m for m in observed.materializations if m["kind"] == "script_call"] == []


def test_observed_sql_write_target_can_resolve_exact_table_with_unresolved_schema() -> None:
    from knowledge_layer_core.sql_producer_observations import _resolve_observed_output_table

    table, variants, unresolved = _resolve_observed_output_table(
        '${$app.stg.schema.name}.${$main_table_name_stg}',
        script_file='stage.sql',
        before_line=20,
        local_bindings={},
        context_values={
            'main_table_name_stg': ['${main_table_name}_stg'],
            'main_table_name': ['t_dim_client_team_type'],
        },
    )
    assert table == 't_dim_client_team_type_stg'
    assert variants == ['${$app.stg.schema.name}.t_dim_client_team_type_stg']
    assert unresolved == ['app.stg.schema.name']


def test_observed_sql_write_target_does_not_choose_ambiguous_table_component() -> None:
    from knowledge_layer_core.sql_producer_observations import _resolve_observed_output_table

    table, variants, _unresolved = _resolve_observed_output_table(
        '${schema}.${target}',
        script_file='stage.sql',
        before_line=20,
        local_bindings={},
        context_values={'target': ['one', 'two']},
    )
    assert table is None
    assert set(variants) == {'${schema}.one', '${schema}.two'}
