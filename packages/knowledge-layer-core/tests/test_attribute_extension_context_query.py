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
            'join-country','ucp','type-birth-place','com.acme.BirthPlace','field-country','country','Country',
            'type-country','com.acme.Country','dictionary','one','exact',False,'[]',
            'resolve_reference_value_to_target_key','confirmed','transformation_required',
            json.dumps(['"Country_" + birthPlace.getCountry().getCode()']),json.dumps(['code']),
            json.dumps(['"Country_" + country.getCode()']),json.dumps([]),json.dumps([]),
            json.dumps([{'match_basis':'exact_structural_expression_signature'}]),
            json.dumps({'observed_sql_relations':['src.birth_place']}),
            json.dumps({'observed_sql_relations':['src.country'],'observed_field_usages':['name']}),
            json.dumps([]),json.dumps([]),json.dumps({'classification':'exact'}),
            json.dumps({'evidence_ids':['obs-1']}),json.dumps([]),
        )
        con.execute("INSERT INTO attribute_extension_join_semantic VALUES (" + ",".join("?" for _ in range(30)) + ")", row)
        con.execute("""CREATE TABLE attribute_extension_object_anchor (
            anchor_id VARCHAR, logical_type_occurrence_id VARCHAR, logical_fully_qualified_name VARCHAR,
            storage_aliases_json JSON, storage_key_fields_json JSON, storage_key_expressions_json JSON,
            observed_sql_relations_json JSON, observed_field_usages_json JSON, observed_sql_projections_json JSON,
            observed_sql_joins_json JSON, physical_candidates_json JSON, knowledge_class VARCHAR,
            basis_json JSON, provenance_json JSON)""")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-country','t','com.acme.Country','[]','[]','[]','[\"src.country\"]','[\"name\"]','[]','[]','[]','observed','{}','{}')")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-birth','t2','com.acme.BirthPlace','[]','[]','[]','[\"src.birth_place\"]','[]','[]','[]','[]','observed','{}','{}')")
        con.execute("""CREATE TABLE attribute_extension_context_gap (
            gap_id VARCHAR, gap_kind VARCHAR, severity VARCHAR, owner_kind VARCHAR, owner_id VARCHAR,
            message VARCHAR, details_json JSON)""")
        con.execute("INSERT INTO attribute_extension_context_gap VALUES ('g','test_gap','info','join_semantic','join-country','detail','{\"x\":1}')")
    finally:
        con.close()
    return path


def test_query_returns_materialized_join_semantics_anchors_and_gaps(tmp_path: Path) -> None:
    result = KnowledgeLayerQuery(_artifact(tmp_path)).list_attribute_extension_join_semantics(
        source_type='com.acme.BirthPlace', source_field='country', offset=0, limit=50,
    )
    assert result['total_count'] == 1
    assert result['items'][0]['join_method'] == 'resolve_reference_value_to_target_key'
    assert result['items'][0]['target_sql_anchor']['observed_field_usages'] == ['name']
    assert result['items'][0]['structural_correspondences'][0]['match_basis'] == 'exact_structural_expression_signature'
    assert {a['logical_fully_qualified_name'] for a in result['object_anchors']} == {'com.acme.BirthPlace','com.acme.Country'}
    assert result['gap_count'] == 1
    assert result['gaps'][0]['details'] == {'x': 1}


def test_query_missing_artifact_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / 'empty.duckdb'
    con = duckdb.connect(str(path)); con.execute('CREATE TABLE x(a INTEGER)'); con.close()
    result = KnowledgeLayerQuery(path).list_attribute_extension_join_semantics()
    assert result['not_available'] is True
    assert 'attribute_extension_join_semantic' in result['missing_relations']
