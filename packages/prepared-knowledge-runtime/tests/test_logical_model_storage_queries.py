from __future__ import annotations

import json
from pathlib import Path

import duckdb

from prepared_knowledge_runtime import KnowledgeLayerQuery


def _manifest(root: Path, capabilities: list[str]) -> None:
    (root / "knowledge-layer-manifest.json").write_text(
        json.dumps({
            "schema_version": "knowledge_layer/v1",
            "database_path": "knowledge-layer.duckdb",
            "capabilities": capabilities,
        }),
        encoding="utf-8",
    )


def test_logical_storage_object_context_reads_exact_bound_relationship(tmp_path: Path) -> None:
    root = tmp_path / "mapping"; root.mkdir()
    con = duckdb.connect(str(root / "knowledge-layer.duckdb"))
    con.execute("create table logical_storage_entity_mapping(entity_mapping_id varchar,mapping_source_id varchar,storage_observation_id varchar,storage_repo_id varchar,storage_alias varchar,storage_key_expression varchar,logical_repo_id varchar,logical_type_occurrence_id varchar,logical_fully_qualified_name varchar,mapping_status varchar,mapping_basis varchar,candidate_logical_type_ids_json json,payload_json json)")
    con.execute("create table logical_storage_relationship_mapping(relationship_mapping_id varchar,mapping_source_id varchar,storage_observation_id varchar,storage_repo_id varchar,storage_relation_kind varchar,source_alias varchar,source_field varchar,target_alias varchar,source_logical_repo_id varchar,source_logical_type_occurrence_id varchar,effective_field_occurrence_id varchar,field_is_inherited boolean,declared_target_type_occurrence_id varchar,declared_target_fqcn varchar,observed_target_type_occurrence_id varchar,observed_target_fqcn varchar,target_alignment varchar,knowledge_class varchar,storage_key_expression varchar,mapping_status varchar,mapping_basis varchar,payload_json json)")
    con.execute("create table logical_storage_join_semantic(join_semantic_id varchar,mapping_source_id varchar,relationship_occurrence_id varchar,source_logical_repo_id varchar,source_logical_type_occurrence_id varchar,source_fqcn varchar,source_field_occurrence_id varchar,source_field varchar,declared_target_type_occurrence_id varchar,declared_target_fqcn varchar,join_kind varchar,status varchar,join_readiness varchar,source_reference_expressions_json json,target_identity_expressions_json json,target_key_fields_json json,structural_correspondences_json json,candidate_count bigint,basis_json json,provenance_json json,diagnostics_json json)")
    con.execute("create table logical_storage_mapping_gap(mapping_gap_id varchar,mapping_source_id varchar,gap_kind varchar,severity varchar,owner_kind varchar,owner_id varchar,message varchar,details_json json)")
    con.execute("insert into logical_storage_entity_mapping values ('em','s','record','tsa','demo.Parent','\"Parent_\" + id','model','parent','demo.Parent','matched','exact_storage_alias_to_fqcn','[]','{}')")
    con.execute("insert into logical_storage_join_semantic values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ["js","s","rel","model","parent","demo.Parent","field","child","child","demo.Child","target_storage_key_reference","strongly_supported","executable_storage_join",json.dumps(["convertChild(parent.child)"]),json.dumps(['"Child_" + id']),json.dumps(["id"]),json.dumps([]),1,json.dumps({"match_basis":"observed_storage_reference_binding","physical_join_claimed":False}),json.dumps({"evidence_ids":["ref"]}),json.dumps([])])
    con.execute("insert into logical_storage_relationship_mapping values ('rm','s','ref','tsa','single_reference','demo.Parent','child','demo.Child','model','parent','ef',false,'child','demo.Child','child','demo.Child','exact_declared_target','confirmed','\"Child_\" + id','matched','exact_fqcn_plus_effective_field','{}')")
    con.close(); _manifest(root, ["common.logical-storage-mapping", "common.logical-storage-join-semantics"])

    result = KnowledgeLayerQuery(root).get_logical_storage_object_context("parent")
    assert result["entity_mappings"][0]["mapping_status"] == "matched"
    rel = result["relationship_mappings"][0]
    assert rel["source_field"] == "child"
    assert rel["target_alignment"] == "exact_declared_target"
    assert rel["knowledge_class"] == "confirmed"
    join_semantic = result["join_semantics"][0]
    assert join_semantic["relationship_occurrence_id"] == "rel"
    assert join_semantic["status"] == "strongly_supported"
    assert join_semantic["join_readiness"] == "executable_storage_join"


def test_model_storage_object_context_preserves_reference_derivation(tmp_path: Path) -> None:
    root = tmp_path / "storage"; root.mkdir()
    con = duckdb.connect(str(root / "knowledge-layer.duckdb"))
    con.execute("create table model_storage_record(observation_id varchar,repo_id varchar,api_framework varchar,owner_fqcn varchar,owner_operation varchar,storage_alias varchar,storage_key_field varchar,storage_key_expression varchar,source_refs_json json,payload_json json)")
    con.execute("create table model_storage_reference(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,source_field varchar,reference_operation varchar,target_converter_operation varchar,target_alias varchar,target_storage_key_field varchar,target_storage_key_expression varchar,source_refs_json json,payload_json json)")
    con.execute("create table model_storage_key_lineage(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,relationship_field varchar,reference_operation varchar,target_alias varchar,source_key_expression varchar,target_key_expression_template varchar,composed_target_key_expression varchar,source_key_passed_into_target_key boolean,source_refs_json json,payload_json json)")
    con.execute("create table model_storage_reference_derivation(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,relationship_field varchar,reference_operation varchar,value_converter_operation varchar,composed_reference_value_expression varchar,source_refs_json json,payload_json json)")
    con.execute("insert into model_storage_reference values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ['ref','tsa','tsa','ParentConverter','convert','demo.Parent','child','referenceField','ChildConverter.convert','demo.Child','key','\"Child_\" + child.id','[]', json.dumps({'properties': {'reference_value_expression': 'convertChild(parent.child)'}})])
    con.execute("insert into model_storage_reference_derivation values (?,?,?,?,?,?,?,?,?,?,?,?)", ['drv','tsa','tsa','ParentConverter','convert','demo.Parent','child','referenceField','convertChild','\"Child_\" + child.getId()','[]', json.dumps({'properties': {'composed_reference_value_expression_tree': {'kind': 'concat'}}})])
    con.close(); _manifest(root, ["common.model-storage-semantics"])

    result = KnowledgeLayerQuery(root).get_model_storage_object_context("demo.Parent")
    assert result["storage_references"][0]["target_storage_key_field"] == "key"
    derivation = result["reference_value_derivations"][0]
    assert derivation["composed_reference_value_expression"] == '"Child_" + child.getId()'
    assert derivation["observed_payload"]["properties"]["composed_reference_value_expression_tree"] == {"kind": "concat"}
