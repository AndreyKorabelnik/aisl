from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _manifest(root: Path, capabilities: list[str]) -> None:
    (root / "knowledge-layer-manifest.json").write_text(json.dumps({
        "schema_version": "knowledge_layer/v1", "artifact_id": root.name,
        "build_status": "complete", "database_path": "knowledge-layer.duckdb",
        "capabilities": capabilities,
    }), encoding="utf-8")


def _cross_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "cross"; root.mkdir()
    db = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE cross_artifact_relation_materialization (
        materialization_id VARCHAR, workflow_context_file VARCHAR, materialization_kind VARCHAR,
        source_file VARCHAR, source_fact_id VARCHAR, source_symbol VARCHAR, query_file VARCHAR,
        query_id VARCHAR, source_table_name VARCHAR, output_table_name VARCHAR,
        resolution_status VARCHAR, knowledge_class VARCHAR, mapping_basis VARCHAR, provenance_json JSON)""")
    con.execute("INSERT INTO cross_artifact_relation_materialization VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        "mat","wf.yaml","script_call","prep.sql","call","runAndSaveSqlHdfs","bv.sql","q",None,
        "stg_individual_bv","matched","derived","structured_script_call",'{"evidence":"observed"}'
    ])
    con.close(); _manifest(root,["common.relation-materialization"]); return db


def _sql_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "sql"; root.mkdir()
    db = root / "knowledge-layer.duckdb"; con = duckdb.connect(str(db))
    con.execute("CREATE TABLE sql_select_scope (sql_select_scope_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,file VARCHAR,line_start BIGINT,parent_scope_id VARCHAR,scope_kind VARCHAR,scope_name VARCHAR,scope_ordinal BIGINT,expression_index BIGINT,relation_count BIGINT,projection_count BIGINT,column_usage_count BIGINT,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("CREATE TABLE sql_statement (sql_statement_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,file VARCHAR,line_start BIGINT,line_end BIGINT,operation VARCHAR,statement_type VARCHAR,target_relation_name VARCHAR,unit_kind VARCHAR,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("CREATE TABLE sql_relation (sql_relation_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,scope_id VARCHAR,file VARCHAR,line_start BIGINT,relation_kind VARCHAR,relation_name VARCHAR,template_name VARCHAR,logical_name VARCHAR,alias VARCHAR,usage_role VARCHAR,definition_status VARCHAR,source_scope_ids_json JSON,placeholder_refs_json JSON,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("CREATE TABLE sql_column_usage (sql_column_usage_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,scope_id VARCHAR,file VARCHAR,line_start BIGINT,column_name VARCHAR,column_ordinal BIGINT,usage_role VARCHAR,table_or_alias VARCHAR,relation_id VARCHAR,relation_kind VARCHAR,relation_name VARCHAR,resolution_status VARCHAR,resolution_basis VARCHAR,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("CREATE TABLE sql_join_edge (sql_join_edge_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,scope_id VARCHAR,file VARCHAR,line_start BIGINT,join_ordinal BIGINT,join_type VARCHAR,condition_kind VARCHAR,predicate VARCHAR,left_relation_id VARCHAR,left_relation_ids_json JSON,left_relation_names_json JSON,right_relation_id VARCHAR,right_relation_kind VARCHAR,right_relation_name VARCHAR,participating_relation_ids_json JSON,column_pairs_json JSON,expression_links_json JSON,using_columns_json JSON,additional_predicates_json JSON,temporal_or_range_predicates_json JSON,resolution_status VARCHAR,resolution_reasons_json JSON,physical_join_confirmed BOOLEAN,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("CREATE TABLE sql_projection (sql_projection_id VARCHAR,repo_id VARCHAR,query_id VARCHAR,scope_id VARCHAR,file VARCHAR,line_start BIGINT,projection_ordinal BIGINT,output_name VARCHAR,expression VARCHAR,expression_kind VARCHAR,is_wildcard BOOLEAN,source_column_count BIGINT,source_column_usage_ids_json JSON,resolution_status VARCHAR,resolution_basis VARCHAR,evidence_maturity_level VARCHAR,evidence_json JSON)")
    con.execute("INSERT INTO sql_select_scope VALUES ('root','repo','q','bv.sql',1,NULL,'statement',NULL,1,1,1,2,1,'observed','[]')")
    con.execute("INSERT INTO sql_statement VALUES ('stmt','repo','q','bv.sql',1,100,NULL,'select',NULL,'query','observed','[]')")
    con.execute("INSERT INTO sql_relation VALUES ('rel','repo','q','root','bv.sql',83,'physical','stg_union',NULL,'stg_union','u','read','not_applicable','[]','[]','observed','[]')")
    con.execute("INSERT INTO sql_column_usage VALUES ('usage','repo','q','root','bv.sql',99,'countryresident',1,'projection','u','rel','physical','stg_union','resolved','qualified_alias','observed','[]')")
    con.execute("INSERT INTO sql_projection VALUES ('p1','repo','q','root','bv.sql',83,1,'countryresident','countryresident','direct_column',false,1,'[\"usage\"]','resolved','scoped_ast','observed','[]')")
    con.execute("INSERT INTO sql_projection VALUES ('p2','repo','q','root','bv.sql',83,2,'partystatus','partystatus','direct_column',false,0,'[]','resolved','scoped_ast','observed','[]')")
    con.close(); _manifest(root,["common.sql-analysis"]); return db


def test_external_llm_can_follow_materialization_to_exact_sql_scope(tmp_path: Path) -> None:
    cross = _cross_artifact(tmp_path); sql = _sql_artifact(tmp_path)
    result = write_execution_result(tmp_path,[
        KnowledgeArtifactSpec(cross,"cross-artifact-data-model-mapping","cross-artifact-data-model-mapping/v6","cross-artifact-data-model-mapping",("common.relation-materialization",)),
        KnowledgeArtifactSpec(sql,"sql-observed-data-usage","knowledge_layer_sql/v2","sql-analysis",("common.sql-analysis",)),
    ])
    settings=KnowledgeApiSettings(database_path=tmp_path/'api.sqlite3',allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f'{KNOWLEDGE_API_PREFIX}/systems',json={'system_id':'dm','display_name':'DM'}).status_code==201
        pub=client.post(f'{KNOWLEDGE_API_PREFIX}/systems/dm/revisions',json=publication_payload(result)); assert pub.status_code==201,pub.text
        rev=pub.json()['revision']['revision_id']
        mats=client.get(f'{KNOWLEDGE_API_PREFIX}/systems/dm/sql/relation-materializations',params={'revision_id':rev,'output_table_name':'stg_individual_bv'})
        assert mats.status_code==200,mats.text
        item=mats.json()['items'][0]; assert item['query_id']=='q' and item['query_file']=='bv.sql'
        ctx=client.get(f'{KNOWLEDGE_API_PREFIX}/systems/dm/sql/query-context',params={'revision_id':rev,'repo_id':'repo','query_id':'q'})
        assert ctx.status_code==200,ctx.text
        body=ctx.json(); assert body['selection_status']=='selected'
        assert [p['output_name'] for p in body['projections']]==['countryresident','partystatus']
