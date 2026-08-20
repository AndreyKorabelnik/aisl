from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "attribute-extension.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute("""CREATE TABLE attribute_extension_context_build (
            build_id VARCHAR, scope_id VARCHAR, builder_version VARCHAR, schema_version VARCHAR,
            build_status VARCHAR, started_at TIMESTAMP, completed_at TIMESTAMP,
            counts_json JSON, checks_json JSON)""")
        con.execute("INSERT INTO attribute_extension_context_build VALUES ('b','workspace','test','data-model-attribute-extension-context/v1','complete',now(),now(),'{}','{}')")
        con.execute("""CREATE TABLE attribute_extension_join_semantic (
            join_semantic_id VARCHAR, source_repo_id VARCHAR, source_type_occurrence_id VARCHAR,
            source_fqcn VARCHAR, source_field_occurrence_id VARCHAR, source_field VARCHAR,
            declared_type_expression VARCHAR, target_type_occurrence_id VARCHAR, target_fqcn VARCHAR,
            relationship_kind VARCHAR, cardinality VARCHAR, target_alignment VARCHAR, polymorphic BOOLEAN,
            concrete_targets_json JSON, join_method VARCHAR, confidence VARCHAR, sql_generation_status VARCHAR,
            source_reference_expressions_json JSON, target_key_fields_json JSON, target_key_expressions_json JSON,
            source_parent_key_expressions_json JSON, child_key_expressions_json JSON,
            structural_correspondences_json JSON, source_sql_anchor_json JSON, target_sql_anchor_json JSON,
            observed_sql_join_examples_json JSON, physical_candidates_json JSON, basis_json JSON,
            provenance_json JSON, diagnostics_json JSON)""")
        row = (
            'join-nationality','ucp-api','code_declared_type_ab7a680e2b9b7d3d330e',
            'com.sbt.bm.ucp.retail.model.individual.Emigration','code_declared_field_e4b4101c3b11849e53e7',
            'nationality','Country','code_declared_type_98837e617da9658e0de8',
            'com.sbt.bm.ucp.common.model.dictionary.Country','declared_field_type_reference','one','exact',False,'[]',
            'resolve_reference_value_to_target_key','confirmed','transformation_required',
            json.dumps([]),json.dumps(['code']),json.dumps([]),json.dumps([]),json.dumps([]),json.dumps([]),
            json.dumps({'observed_sql_relations':[{'relation_name':'${snp_src_schema_name}.com_sbt_bm_ucp_retail_model_individual_emigration'}],
                        'observed_field_usages':[{'field':'nationality','column':'nationality'}]}),
            json.dumps({'observed_sql_relations':[{'relation_name':'country'}]}),
            json.dumps([]),json.dumps([]),json.dumps({'kind':'trace-regression'}),
            json.dumps({'evidence_ids':['trace-nationality']}),json.dumps([]),
        )
        con.execute("INSERT INTO attribute_extension_join_semantic VALUES (" + ",".join("?" for _ in range(30)) + ")", row)
        con.execute("""CREATE TABLE attribute_extension_object_anchor (
            anchor_id VARCHAR, logical_type_occurrence_id VARCHAR, logical_fully_qualified_name VARCHAR,
            storage_aliases_json JSON, storage_key_fields_json JSON, storage_key_expressions_json JSON,
            observed_sql_relations_json JSON, observed_field_usages_json JSON, observed_sql_projections_json JSON,
            observed_sql_joins_json JSON, physical_candidates_json JSON, knowledge_class VARCHAR,
            basis_json JSON, provenance_json JSON)""")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-src','code_declared_type_ab7a680e2b9b7d3d330e','com.sbt.bm.ucp.retail.model.individual.Emigration','[]','[]','[]','[]','[]','[]','[]','[]','confirmed','{}','{}')")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-tgt','code_declared_type_98837e617da9658e0de8','com.sbt.bm.ucp.common.model.dictionary.Country','[]','[]','[]','[]','[]','[]','[]','[]','confirmed','{}','{}')")
        con.execute("""CREATE TABLE attribute_extension_context_gap (
            gap_id VARCHAR, gap_kind VARCHAR, severity VARCHAR, owner_kind VARCHAR, owner_id VARCHAR,
            message VARCHAR, details_json JSON)""")
    finally:
        con.close()
    return path


def test_declared_object_ids_handoff_to_attribute_extension_context(tmp_path: Path) -> None:
    query = KnowledgeLayerQuery(_artifact(tmp_path))
    result = query.list_attribute_extension_join_semantics(
        source_type='code_declared_type_ab7a680e2b9b7d3d330e',
        source_field='nationality',
        target_type='code_declared_type_98837e617da9658e0de8',
    )
    assert result['total_count'] == 1
    assert result['items'][0]['source_fqcn'].endswith('.Emigration')
    assert result['items'][0]['target_fqcn'].endswith('.Country')
    assert result['items'][0]['source_sql_anchor']['observed_field_usages'][0]['field'] == 'nationality'


def test_field_occurrence_id_is_also_accepted(tmp_path: Path) -> None:
    result = KnowledgeLayerQuery(_artifact(tmp_path)).list_attribute_extension_join_semantics(
        source_type='com.sbt.bm.ucp.retail.model.individual.Emigration',
        source_field='code_declared_field_e4b4101c3b11849e53e7',
        target_type='com.sbt.bm.ucp.common.model.dictionary.Country',
    )
    assert result['total_count'] == 1
