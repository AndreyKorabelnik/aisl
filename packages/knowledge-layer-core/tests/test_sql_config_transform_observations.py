from __future__ import annotations

import json

import duckdb

from knowledge_layer_core.sql_producer_observations import derive_sql_producer_observations


def test_historicity_call_and_referenced_config_produce_observed_transform_and_resolve_write_template() -> None:
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE sql_workflow_binding(sql_workflow_binding_id VARCHAR,repo_id VARCHAR,file VARCHAR,binding_name VARCHAR,binding_path VARCHAR,scalar_value VARCHAR,value_expression VARCHAR,evidence_json JSON,line_start BIGINT)")
    c.execute("CREATE TABLE sql_workflow_context_file(repo_id VARCHAR,workflow_context_file VARCHAR,reachable_file VARCHAR,resolution_status VARCHAR)")
    c.execute("CREATE TABLE sql_statement(repo_id VARCHAR,query_id VARCHAR,file VARCHAR)")
    c.execute("CREATE TABLE sql_select_scope(repo_id VARCHAR,query_id VARCHAR,parent_scope_id VARCHAR)")
    c.execute("CREATE TABLE sql_script_call(repo_id VARCHAR,sql_script_call_id VARCHAR,file VARCHAR,line_start BIGINT,call_symbol VARCHAR,named_arguments_json JSON,positional_arguments_json JSON,evidence_json JSON)")
    c.execute("CREATE TABLE sql_write_target(repo_id VARCHAR,sql_write_target_id VARCHAR,file VARCHAR,line_start BIGINT,query_id VARCHAR,operation_kind VARCHAR,target_relation_name VARCHAR,source_scope_ids_json JSON,payload_json JSON,evidence_json JSON)")

    repo = "r"
    wf = "workflow.yaml"
    script = "wf/load.sql"
    config = "wf/model_historicity.json"
    c.execute("INSERT INTO sql_workflow_context_file VALUES (?,?,?,?)", [repo, wf, script, "resolved"])
    bindings = {
        "params.increment.schemaName": "dm_stg",
        "params.increment.tableName": "target_prestg",
        "params.output.schemaName": "dm_stg",
        "params.output.tableNameSnp": "target_stg",
        "params.target.partitioning.snp[0].initialColumn": "end_dt",
        "params.target.partitioning.snp[0].partitioningColumn": "part_day",
    }
    for i, (path, value) in enumerate(bindings.items(), 1):
        c.execute("INSERT INTO sql_workflow_binding VALUES (?,?,?,?,?,?,?,?,?)", [f"b{i}", repo, config, path.split('.')[-1], path, value, value, json.dumps([]), i])
    c.execute("INSERT INTO sql_script_call VALUES (?,?,?,?,?,?,?,?)", [repo, "call-h", script, 50, "historicity", json.dumps({}), json.dumps(['"$root/wf/model_historicity.json"']), json.dumps([])])
    c.execute("INSERT INTO sql_write_target VALUES (?,?,?,?,?,?,?,?,?,?)", [repo, "write-1", script, 20, "q1", "insert", "dm_stg.target_${$pre}stg", json.dumps(["scope-1"]), json.dumps({}), json.dumps([])])

    observed = derive_sql_producer_observations(c, repo_id=repo)
    transforms = [m for m in observed.materializations if m["kind"] == "config_transform"]
    assert len(transforms) == 1
    assert transforms[0]["workflow"] == wf
    assert transforms[0]["source_table"] == "target_prestg"
    assert transforms[0]["table"] == "target_stg"
    assert transforms[0]["provenance"]["column_mappings"] == {"part_day": "end_dt"}

    resolved_writes = [m for m in observed.materializations if m["kind"] == "sql_write" and m["mapping_basis"] == "observed_sql_write_template_resolved_by_referenced_transform_config"]
    assert {m["table"] for m in resolved_writes} == {"target_prestg", "target_stg"}
    assert all(m["source_scopes"] == ["scope-1"] for m in resolved_writes)
