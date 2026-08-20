from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids
from knowledge_layer_core.metrics import canonical_json


def _knowledge_output(root: Path, *, repo_ids: list[str], ddl: list[str], inserts: list[tuple[str, list[tuple]]]) -> dict:
    root.mkdir(parents=True)
    db_path=root/'knowledge-layer.duckdb'
    c=duckdb.connect(str(db_path))
    for sql in ddl: c.execute(sql)
    for sql,rows in inserts:
        for row in rows: c.execute(sql,row)
    c.close()
    manifest={"schema_version":"knowledge_layer/v1","database_path":"knowledge-layer.duckdb","repository_ids":repo_ids}
    mp=root/'knowledge-layer-manifest.json'; mp.write_text(json.dumps(manifest),encoding='utf-8')
    fp=hashlib.sha256(canonical_json(manifest).encode('utf-8')).hexdigest()
    return {"content_fingerprint":fp,"location":{"kind":"knowledge-layer","output_path":str(root),"manifest_path":str(mp)}}


def test_cross_artifact_mapping_uses_explicit_identity_rules(tmp_path: Path) -> None:
    assert 'cross-artifact-data-model-mapping' in registered_materialization_ids()
    storage=_knowledge_output(tmp_path/'storage',repo_ids=['model'],ddl=[
        'create table logical_storage_entity_mapping(storage_observation_id varchar,storage_alias varchar,storage_key_expression varchar,logical_type_occurrence_id varchar,logical_fully_qualified_name varchar,mapping_status varchar,payload_json json)',
    ],inserts=[('insert into logical_storage_entity_mapping values (?,?,?,?,?,?,?)',[
        ('storage-customer','com.acme.model.Customer','Customer_ + id','type-customer','com.acme.model.Customer','matched','{"properties":{"storage_key_field":"key"}}'),
    ])])
    code=_knowledge_output(tmp_path/'code',repo_ids=['model'],ddl=[
        'create table code_declared_effective_field(effective_field_occurrence_id varchar,effective_owner_type_occurrence_id varchar,field_name varchar)',
    ],inserts=[('insert into code_declared_effective_field values (?,?,?)',[
        ('field-name','type-customer','name'),
    ])])
    sql=_knowledge_output(tmp_path/'sql',repo_ids=['dm'],ddl=[
        'create table sql_relation(sql_relation_id varchar,repo_id varchar,relation_name varchar,logical_name varchar,usage_role varchar,relation_kind varchar,file varchar,line_start bigint)',
        'create table sql_write_target(sql_write_target_id varchar,repo_id varchar,query_id varchar,file varchar,line_start bigint,operation_kind varchar,target_relation_name varchar,target_logical_name varchar,source_scope_ids_json json,payload_json json,evidence_json json)',
        'create table sql_placeholder_binding_resolution(sql_placeholder_binding_resolution_id varchar,repo_id varchar,resolved_value varchar,placeholder varchar,binding_name varchar,binding_file varchar,sql_file varchar,resolution_status varchar)',
        'create table sql_column_usage(sql_column_usage_id varchar,query_id varchar,file varchar,column_name varchar,usage_role varchar,relation_id varchar,resolution_status varchar)',
        'create table sql_workflow_binding(sql_workflow_binding_id varchar,file varchar,line_start bigint,binding_name varchar,scalar_value varchar,value_expression varchar,resolution_status varchar,evidence_json json)',
        'create table sql_workflow_file_reference(sql_workflow_file_reference_id varchar,source_file varchar,source_kind varchar,source_fact_id varchar,target_path_template varchar,resolved_target_file varchar,resolution_status varchar,resolution_basis varchar)',
        'create table sql_workflow_context_file(workflow_context_file varchar,reachable_file varchar,reachable_file_kind varchar,context_reference_ids_json varchar,resolution_status varchar,context_hop_count bigint)',
        'create table sql_statement(query_id varchar,file varchar,statement_type varchar,line_start bigint)',
        'create table sql_select_scope(sql_select_scope_id varchar,query_id varchar,parent_scope_id varchar,scope_ordinal bigint)',
        'create table sql_projection(sql_projection_id varchar,scope_id varchar,output_name varchar,expression varchar,resolution_status varchar,is_wildcard boolean,projection_ordinal bigint)',
    ],inserts=[
        ('insert into sql_relation values (?,?,?,?,?,?,?,?)',[
            ('rel-source','dm','${src}.com_acme_model_customer','com_acme_model_customer','from','physical_template','load.sql',10),
            ('rel-target','dm','dm.customer_dim','customer_dim','from','physical','read.sql',3),
        ]),
        ('insert into sql_write_target values (?,?,?,?,?,?,?,?,?,?,?)',[
            ('write','dm','query-transform','load.sql',50,'insert','dm.customer_dim','customer_dim','["scope-root"]','{"resolved_target_relation_name":"dm.customer_dim"}','[]'),
        ]),
        ('insert into sql_placeholder_binding_resolution values (?,?,?,?,?,?,?,?)',[
            ('bind','dm','customer_dim','main_table','main_table','wf.yaml','common.sql','resolved'),
        ]),
        ('insert into sql_column_usage values (?,?,?,?,?,?,?)',[
            ('usage-name','query-transform','transform.sql','name','projection','rel-source','resolved'),
        ]),
        ('insert into sql_workflow_binding values (?,?,?,?,?,?,?,?)',[
            ('wb-producer','producer.yaml',1,'entities','job-1','job-1','literal','[]'),
            ('wb-trigger','wf.yaml',1,'trigger','job-1.2','job-1.2','literal','[]'),
            ('wb-main','wf.yaml',2,'main_table_name','customer_dim','customer_dim','literal','[]'),
        ]),
        ('insert into sql_workflow_file_reference values (?,?,?,?,?,?,?,?)',[
            ('ref-transform','common/calc.sql','script_invocation','inv-1','$root/${$main_table_name}/${$main_table_name}.sql','transform.sql','resolved','contextual_template_resolution'),
        ]),
        ('insert into sql_workflow_context_file values (?,?,?,?,?,?)',[
            ('wf.yaml','transform.sql','sql','["ref-transform"]','resolved',2),
        ]),
        ('insert into sql_statement values (?,?,?,?)',[
            ('query-transform','transform.sql','select',1),
        ]),
        ('insert into sql_select_scope values (?,?,?,?)',[
            ('scope-root','query-transform',None,1),
        ]),
        ('insert into sql_projection values (?,?,?,?,?,?,?)',[
            ('projection-name','scope-root','name','upper(name) as name','resolved',False,1),
        ]),
    ])
    physical=_knowledge_output(tmp_path/'physical',repo_ids=[],ddl=[
        'create table physical_model_table(physical_model_table_id varchar,table_name varchar,table_code varchar)',
        'create table physical_model_column(physical_model_column_id varchar,physical_model_table_id varchar,column_name varchar,column_code varchar,ordinal bigint)',
    ],inserts=[
        ('insert into physical_model_table values (?,?,?)',[
            ('pdm-customer','Customer dimension','customer_dim'),
        ]),
        ('insert into physical_model_column values (?,?,?,?,?)',[
            ('pdm-col-name','pdm-customer','Name','name',1),
        ]),
    ])
    items=[
        {"artifact_id":"storage-art","model_kind":"logical-storage-model-mapping","schema_version":"logical-storage-model-mapping/v2","source_materialization_id":"logical-storage-mapping",**storage},
        {"artifact_id":"code-art","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","source_materialization_id":"code-declared-data-model",**code},
        {"artifact_id":"sql-art","model_kind":"sql-observed-data-usage","schema_version":"knowledge_layer_sql/v2","source_materialization_id":"sql-analysis",**sql},
        {"artifact_id":"physical-art","model_kind":"physical-data-model","schema_version":"knowledge_layer_physical_model/v1","source_materialization_id":"physical-model",**physical},
    ]
    result=materialize({"schema_version":"knowledge_materialization_request/v1","materialization_id":"cross-artifact-data-model-mapping","scope_id":"workspace","inputs":{"evidence_artifacts":[],"knowledge_artifacts":items},"parameters":{}},tmp_path/'out')
    assert result['status']=='completed'
    assert 'common.sql-target-source-mapping' in result['published_capabilities']
    manifest=json.loads((tmp_path/'out/knowledge-layer-manifest.json').read_text(encoding='utf-8'))
    assert 'cross-artifact-target-source-mapping' in manifest['materialized_marts']
    assert 'common.sql-target-source-mapping' in manifest['capabilities']
    c=duckdb.connect(str(tmp_path/'out/knowledge-layer.duckdb'),read_only=True)
    tables={row[0] for row in c.execute("select table_name from information_schema.tables where table_schema='main'").fetchall()}
    assert 'cross_artifact_value_origin_physical_lineage' in tables
    assert 'cross_artifact_logical_field_physical_lineage' not in tables
    assert c.execute("select storage_alias,sql_logical_name,knowledge_class,mapping_basis from cross_artifact_storage_sql_mapping").fetchall()==[
        ('com.acme.model.Customer','com_acme_model_customer','derived','unique_flattened_qualified_name')
    ]
    rows=c.execute("select sql_object_kind,sql_name,physical_table_code,knowledge_class from cross_artifact_sql_physical_mapping order by sql_object_kind").fetchall()
    assert rows==[
        ('relation','customer_dim','customer_dim','derived'),
        ('resolved_binding','customer_dim','customer_dim','derived'),
        ('write_target','customer_dim','customer_dim','derived'),
    ]
    assert c.execute("select logical_field_name,sql_column_name,knowledge_class from cross_artifact_logical_field_sql_usage").fetchall()==[
        ('name','name','derived')
    ]
    assert c.execute("select target_table_code,projection_output_name,physical_column_code,knowledge_class from cross_artifact_workflow_projection_physical_mapping").fetchall()==[
        ('customer_dim','name','name','derived')
    ]
    assert c.execute("select producer_workflow_context_file,consumer_workflow_context_file,entity_identity,resolution_status,knowledge_class from cross_artifact_workflow_dependency").fetchall()==[
        ('producer.yaml','wf.yaml','job-1','matched','derived')
    ]
    c.close()


def test_cross_artifact_target_source_mapping_reaches_ultimate_sql_source_without_logical_model_binding(tmp_path: Path) -> None:
    from knowledge_layer_core.code_declared_model_schema import CODE_DECLARED_MODEL_DDL
    from knowledge_layer_core.logical_storage_mapping_schema import LOGICAL_STORAGE_DDL
    from knowledge_layer_core.physical_model_schema import PHYSICAL_MODEL_DDL
    from knowledge_layer_core.sql_analysis_schema import SQL_ANALYSIS_DDL

    storage = _knowledge_output(tmp_path/'storage-ultimate', repo_ids=['model'], ddl=[LOGICAL_STORAGE_DDL], inserts=[])
    code = _knowledge_output(tmp_path/'code-ultimate', repo_ids=['model'], ddl=[CODE_DECLARED_MODEL_DDL], inserts=[])
    sql = _knowledge_output(tmp_path/'sql-ultimate', repo_ids=['dm'], ddl=[SQL_ANALYSIS_DDL], inserts=[
        ("insert into sql_workflow_binding (sql_workflow_binding_id,repo_id,file,binding_name,scalar_value,resolution_status,payload_json,evidence_json) values (?,?,?,?,?,?,?,?)", [
            ('wb-main','dm','wf.yaml','main_table_name','customer_dim','literal','{}','[]'),
        ]),
        ("insert into sql_workflow_file_reference (sql_workflow_file_reference_id,repo_id,source_file,source_kind,source_fact_id,reference_ordinal,target_path_template,resolved_target_file,resolution_status,resolution_basis,candidate_count,resolution_candidates_json,evidence_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ('ref-final','dm','wf.yaml','script_invocation','call-final',1,'${main_table_name}.sql','final.sql','resolved','contextual_template_resolution',1,'["final.sql"]','[]'),
        ]),
        ("insert into sql_workflow_context_file (sql_workflow_context_file_id,repo_id,workflow_context_file,reachable_file,reachable_file_kind,context_hop_count,context_files_json,context_reference_ids_json,resolution_status,resolution_reasons_json) values (?,?,?,?,?,?,?,?,?,?)", [
            ('ctx-final','dm','wf.yaml','final.sql','sql',1,'["wf.yaml","final.sql"]','["ref-final"]','resolved','[]'),
            ('ctx-prep','dm','wf.yaml','prep.sql','script',1,'["wf.yaml","prep.sql"]','[]','resolved','[]'),
        ]),
        ("insert into sql_statement (sql_statement_id,repo_id,query_id,file,line_start,statement_type,payload_json) values (?,?,?,?,?,?,?)", [
            ('stmt-final','dm','q-final','final.sql',1,'select','{}'),
            ('stmt-stage','dm','q-stage','stage.sql',1,'select','{}'),
        ]),
        ("insert into sql_select_scope (sql_select_scope_id,repo_id,query_id,file,line_start,parent_scope_id,scope_kind,scope_ordinal,payload_json) values (?,?,?,?,?,?,?,?,?)", [
            ('scope-final','dm','q-final','final.sql',1,None,'select',1,'{"output_columns":["last_name"],"output_contract_status":"complete","output_contract_basis":"explicit_projection"}'),
            ('scope-stage','dm','q-stage','stage.sql',1,None,'select',1,'{"output_columns":["last_name"],"output_contract_status":"complete","output_contract_basis":"explicit_projection"}'),
        ]),
        ("insert into sql_relation (sql_relation_id,repo_id,query_id,scope_id,file,line_start,relation_kind,relation_name,logical_name,usage_role,source_scope_ids_json,payload_json) values (?,?,?,?,?,?,?,?,?,?,?,?)", [
            ('rel-stage','dm','q-final','scope-final','final.sql',2,'physical','dm_stg.stage_names','stage_names','from','[]','{}'),
            ('rel-source','dm','q-stage','scope-stage','stage.sql',2,'physical','src.individual_name','individual_name','from','[]','{}'),
        ]),
        ("insert into sql_column_usage (sql_column_usage_id,repo_id,query_id,scope_id,file,line_start,column_name,usage_role,table_or_alias,relation_id,relation_kind,relation_name,resolution_status,resolution_basis,payload_json,evidence_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ('usage-stage','dm','q-final','scope-final','final.sql',3,'last_name','projection','s','rel-stage','physical','dm_stg.stage_names','resolved','qualified_relation','{}','[]'),
            ('usage-source','dm','q-stage','scope-stage','stage.sql',3,'surname','projection','n','rel-source','physical','src.individual_name','resolved','qualified_relation','{}','[]'),
        ]),
        ("insert into sql_projection (sql_projection_id,repo_id,query_id,scope_id,file,line_start,projection_ordinal,output_name,expression,expression_kind,is_wildcard,source_column_usage_ids_json,resolution_status,payload_json,evidence_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ('projection-final','dm','q-final','scope-final','final.sql',3,1,'last_name','last_name','column',False,'["usage-stage"]','resolved','{}','[]'),
            ('projection-stage','dm','q-stage','scope-stage','stage.sql',3,1,'last_name','surname as last_name','column',False,'["usage-source"]','resolved','{}','[]'),
        ]),
        ("insert into sql_script_call (sql_script_call_id,repo_id,file,line_start,call_symbol,named_arguments_json,positional_arguments_json,referenced_placeholders_json,payload_json,evidence_json) values (?,?,?,?,?,?,?,?,?,?)", [
            ('call-stage','dm','prep.sql',10,'runAndSaveSqlHdfs','{"queryPath":"stage.sql","tableName":"stage_names"}','[]','[]','{}','[]'),
        ]),
    ])
    physical = _knowledge_output(tmp_path/'physical-ultimate', repo_ids=[], ddl=[PHYSICAL_MODEL_DDL], inserts=[
        ("insert into physical_model_table (physical_model_table_id,physical_model_source_id,table_name,table_code,payload_json) values (?,?,?,?,?)", [
            ('pdm-target','pdm-source','Customer dimension','customer_dim','{}'),
        ]),
        ("insert into physical_model_column (physical_model_column_id,physical_model_table_id,physical_model_source_id,ordinal,column_name,column_code,payload_json) values (?,?,?,?,?,?,?)", [
            ('pdm-last-name','pdm-target','pdm-source',1,'Last name','last_name','{}'),
        ]),
    ])
    items = [
        {"artifact_id":"storage-art","model_kind":"logical-storage-model-mapping","schema_version":"logical-storage-model-mapping/v2","source_materialization_id":"logical-storage-mapping",**storage},
        {"artifact_id":"code-art","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","source_materialization_id":"code-declared-data-model",**code},
        {"artifact_id":"sql-art","model_kind":"sql-observed-data-usage","schema_version":"knowledge_layer_sql/v2","source_materialization_id":"sql-analysis",**sql},
        {"artifact_id":"physical-art","model_kind":"physical-data-model","schema_version":"knowledge_layer_physical_model/v1","source_materialization_id":"physical-model",**physical},
    ]
    result = materialize({"schema_version":"knowledge_materialization_request/v1","materialization_id":"cross-artifact-data-model-mapping","scope_id":"workspace","inputs":{"evidence_artifacts":[],"knowledge_artifacts":items},"parameters":{}}, tmp_path/'out-ultimate')
    assert result['status'] == 'completed'
    c = duckdb.connect(str(tmp_path/'out-ultimate/knowledge-layer.duckdb'), read_only=True)
    assert c.execute(
        "select target_table_code,target_column,source_sql_relation_name,source_sql_column,materialization_path_json from cross_artifact_target_source_mapping"
    ).fetchall() == [
        ('customer_dim','last_name','src.individual_name','surname','["' + c.execute("select materialization_id from cross_artifact_relation_materialization where output_table_name='stage_names'").fetchone()[0] + '"]')
    ]
    assert c.execute("select count(*) from cross_artifact_value_origin_physical_lineage").fetchone()[0] == 0
    c.close()
