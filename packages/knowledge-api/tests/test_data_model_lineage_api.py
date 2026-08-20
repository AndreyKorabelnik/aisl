from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "cross-artifact.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute("""CREATE TABLE cross_artifact_mapping_build (
            build_id VARCHAR, scope_id VARCHAR, builder_version VARCHAR, schema_version VARCHAR,
            build_status VARCHAR, started_at TIMESTAMP, completed_at TIMESTAMP,
            counts_json JSON, checks_json JSON)""")
        con.execute("INSERT INTO cross_artifact_mapping_build VALUES ('b','workspace','test','cross-artifact-data-model-mapping/v6','complete',now(),now(),'{}','{}')")
        con.execute("""CREATE TABLE cross_artifact_workflow_projection_physical_mapping (
            mapping_id VARCHAR, workflow_context_file VARCHAR, target_table_code VARCHAR,
            physical_model_table_id VARCHAR, physical_model_column_id VARCHAR, physical_column_code VARCHAR,
            transform_sql_file VARCHAR, transform_query_id VARCHAR, projection_id VARCHAR,
            projection_output_name VARCHAR, projection_expression VARCHAR, mapping_status VARCHAR,
            knowledge_class VARCHAR, mapping_basis VARCHAR, provenance_json JSON)""")
        con.execute("""CREATE TABLE cross_artifact_value_origin_physical_lineage (
            lineage_id VARCHAR, origin_kind VARCHAR, origin_identity VARCHAR,
            logical_type_occurrence_id VARCHAR, logical_fully_qualified_name VARCHAR,
            effective_field_occurrence_id VARCHAR, logical_field_name VARCHAR,
            storage_alias VARCHAR, storage_key_field VARCHAR, storage_key_expression VARCHAR,
            source_sql_column_usage_id VARCHAR, source_sql_relation_id VARCHAR,
            source_sql_file VARCHAR, source_sql_column_name VARCHAR,
            workflow_context_file VARCHAR, target_table_code VARCHAR, physical_model_table_id VARCHAR,
            physical_model_column_id VARCHAR, physical_column_code VARCHAR, transform_sql_file VARCHAR,
            transform_query_id VARCHAR, target_projection_id VARCHAR, target_projection_expression VARCHAR,
            knowledge_class VARCHAR, mapping_basis VARCHAR, origin_semantics_json JSON,
            projection_path_json JSON, materialization_path_json JSON, workflow_dependency_path_json JSON,
            provenance_json JSON)""")
        con.execute("""CREATE TABLE cross_artifact_mapping_gap (
            gap_id VARCHAR, gap_kind VARCHAR, severity VARCHAR, owner_kind VARCHAR,
            owner_id VARCHAR, message VARCHAR, details_json JSON)""")
        con.executemany(
            "INSERT INTO cross_artifact_workflow_projection_physical_mapping VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ('m-active','wf.yaml','epk_client','pt','pc-active','active_flag','target.sql','q-target','p-active','active_flag','cast(active_flag as tinyint)','matched','derived','exact','{}'),
                ('m-epk','wf.yaml','epk_client','pt','pc-epk','epk_id','target.sql','q-target','p-epk','epk_id','cast(epk_id as bigint)','matched','derived','exact','{}'),
            ],
        )
        rows = [
            ('l-active-current','logical_field','example.Individual.endDate','t-ind','example.Individual','f-end','endDate',None,None,None,'u-active-current','r-ind','src.sql','enddate','wf.yaml','epk_client','pt','pc-active','active_flag','target.sql','q-target','p-active','cast(active_flag as tinyint)','derived','observed',json.dumps({'origin_kind':'logical_field','lineage_role':'control'}),json.dumps(['p-active']),json.dumps(['mat-active']),json.dumps([]),json.dumps({'evidence':'observed'})),
            ('l-active-history','logical_field','example.Individual.endDate','t-ind','example.Individual','f-end','endDate',None,None,None,'u-active-history','r-ind-h','hist.sql','enddate','wf.yaml','epk_client','pt','pc-active','active_flag','target.sql','q-target','p-active','cast(active_flag as tinyint)','derived','observed',json.dumps({'origin_kind':'logical_field','lineage_role':'control'}),json.dumps(['p-active']),json.dumps(['mat-active-h']),json.dumps([]),json.dumps({'evidence':'observed'})),
            ('l-epk','logical_field','example.Individual.id','t-ind','example.Individual','f-id','id',None,None,None,'u-epk','r-ind','src.sql','id','wf.yaml','epk_client','pt','pc-epk','epk_id','target.sql','q-target','p-epk','cast(epk_id as bigint)','derived','observed',json.dumps({'origin_kind':'logical_field','lineage_role':'value'}),json.dumps(['p-epk']),json.dumps(['mat-epk']),json.dumps([]),json.dumps({'evidence':'observed'})),
            ('l-epk-storage','storage_identity','example.Name.key','t-name','example.Name',None,None,'example.Name','key','parentKey + id','u-key','r-name','name.sql','key','wf.yaml','epk_client','pt','pc-epk','epk_id','target.sql','q-target','p-epk','cast(epk_id as bigint)','derived','observed_storage_identity',json.dumps({'origin_kind':'storage_identity','lineage_role':'value'}),json.dumps(['p-epk']),json.dumps(['mat-name']),json.dumps([]),json.dumps({'evidence':'observed'})),
        ]
        con.executemany(
            "INSERT INTO cross_artifact_value_origin_physical_lineage VALUES (" + ",".join("?" for _ in range(30)) + ")",
            rows,
        )
    finally:
        con.close()
    return path


def _published_client(tmp_path: Path):
    artifact = _artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [KnowledgeArtifactSpec(
            database=artifact,
            model_kind='cross-artifact-data-model-mapping',
            schema_version='cross-artifact-data-model-mapping/v6',
            materialization_id='cross-artifact-data-model-mapping',
            capabilities=('common.cross-artifact-data-model-mapping','common.value-origin-physical-lineage'),
        )],
        scope_id='dm', execution_token='run-dm',
    )
    settings = KnowledgeApiSettings(database_path=tmp_path/'api.sqlite3', allowed_roots=(tmp_path,))
    return result, settings


def test_data_model_lineage_http_contract_exposes_v6_detail(tmp_path: Path) -> None:
    result, settings = _published_client(tmp_path)
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f'{KNOWLEDGE_API_PREFIX}/systems', json={'system_id':'dm','display_name':'DM'}).status_code == 201
        pub = client.post(f'{KNOWLEDGE_API_PREFIX}/systems/dm/revisions', json=publication_payload(result))
        assert pub.status_code == 201, pub.text
        revision_id = pub.json()['revision']['revision_id']
        response = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/dm/data-model/lineage',
            params={'revision_id':revision_id,'logical_field':'endDate','target_table':'epk_client'},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['lineage_schema_version'] == 'data-model-lineage-query/v2'
    assert body['page']['total'] == 2
    assert body['summary']['by_origin_kind'] == {'logical_field': 2}
    assert body['summary']['by_knowledge_class'] == {'derived': 2}
    item = body['items'][0]
    assert item['source_sql_relation_id'] in {'r-ind','r-ind-h'}
    assert item['physical_column_code'] == 'active_flag'
    assert item['origin_semantics']['lineage_role'] == 'control'
    assert item['materialization_path']


def test_target_column_lineage_requires_canonical_sql_lineage_artifact(tmp_path: Path) -> None:
    result, settings = _published_client(tmp_path)
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f'{KNOWLEDGE_API_PREFIX}/systems', json={'system_id':'dm','display_name':'DM'}).status_code == 201
        pub = client.post(f'{KNOWLEDGE_API_PREFIX}/systems/dm/revisions', json=publication_payload(result))
        assert pub.status_code == 201, pub.text
        revision_id = pub.json()['revision']['revision_id']
        response = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/dm/sql/target-column-lineage',
            params={'revision_id':revision_id,'target_relation':'custom_b2c_profile_fl.epk_client','limit':50},
        )
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'knowledge_artifact_unavailable'
