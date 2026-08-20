from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime.query import KnowledgeLayerQuery


def _artifact(tmp_path: Path) -> Path:
    db=tmp_path/'knowledge-layer.duckdb'
    c=duckdb.connect(str(db))
    c.execute('''CREATE TABLE sql_target_value_source_mapping(\n      value_mapping_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, workflow_target_logical_name VARCHAR, target_column VARCHAR,\n      source_sql_column_usage_id VARCHAR, source_sql_relation_id VARCHAR, source_sql_relation_name VARCHAR, source_sql_column VARCHAR, source_sql_file VARCHAR,\n      source_representation VARCHAR, normalization_kind VARCHAR, mapping_status VARCHAR, knowledge_class VARCHAR, mapping_basis VARCHAR,\n      supporting_raw_mapping_ids_json JSON, semantic_evidence_json JSON, provenance_json JSON)''')
    c.execute('''CREATE TABLE sql_target_source_mapping_gap(\n      gap_id VARCHAR, repo_id VARCHAR, workflow_context_file VARCHAR, workflow_target_logical_name VARCHAR, target_column VARCHAR, root_projection_id VARCHAR,\n      local_lineage_id VARCHAR, gap_kind VARCHAR, impact VARCHAR, mapping_basis VARCHAR, evidence_json JSON)''')
    c.execute('INSERT INTO sql_target_value_source_mapping VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
      'v1','repo','wf.yaml','epk_client','confirmedbyoperator',None,'r1','${snp_src_schema_name}.individual','confirmedByOperator','read.sql',None,
      'direct_terminal_source','partial','derived','raw_terminal_sql_origin',json.dumps(['raw1']),json.dumps([]),json.dumps({'placeholder_resolution_status':'partial'})])
    c.execute('INSERT INTO sql_target_source_mapping_gap VALUES (?,?,?,?,?,?,?,?,?,?,?)',[
      'g1','repo','wf.yaml','epk_client','confirmedbyoperator',None,None,'source_relation_placeholder_unresolved','source_identity_incomplete',
      'observed_workflow_placeholder_binding_resolution',json.dumps({'placeholder':'snp_src_schema_name'})])
    c.close()
    return db


def test_sql_target_value_source_query_is_compact_and_capability_backed(tmp_path: Path) -> None:
    q=KnowledgeLayerQuery(_artifact(tmp_path))
    assert 'common.sql-target-value-source-mapping' in q.capabilities()
    result=q.list_sql_target_value_sources('custom_b2c_profile_fl.epk_client',target_column='confirmedbyoperator',include_gaps=True)
    assert result['schema_version']=='sql-target-value-source-query/v1'
    assert result['total_count']==1
    assert result['summary']['target_column_count']==1
    assert result['items'][0]['source_sql_relation_name']=='${snp_src_schema_name}.individual'
    assert result['items'][0]['mapping_status']=='partial'
    assert result['gap_count']==1
    assert result['gaps'][0]['gap_kind']=='source_relation_placeholder_unresolved'
