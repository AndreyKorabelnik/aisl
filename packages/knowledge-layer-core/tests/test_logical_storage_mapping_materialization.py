from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import materialize, registered_materialization_ids
from knowledge_layer_core.metrics import canonical_json


def _knowledge_output(root: Path, *, repo_ids: list[str], ddl: list[str], inserts: list[tuple[str, list[tuple]]]) -> tuple[dict, Path]:
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
    return {"content_fingerprint":fp,"location":{"kind":"knowledge-layer","output_path":str(root),"manifest_path":str(mp)}},mp


def _getter_tree(prefix: str, field: str) -> dict:
    return {
        "node_type": "binary_expression",
        "operator": "+",
        "children": [
            {"field": "left", "node_type": "string_literal", "value": json.dumps(prefix)},
            {"field": "operator", "node_type": "+", "value": "+"},
            {
                "field": "right",
                "node_type": "method_invocation",
                "children": [
                    {"field": "object", "node_type": "identifier", "value": "receiver"},
                    {"field": "name", "node_type": "identifier", "value": "get" + field[:1].upper() + field[1:]},
                    {"field": "arguments", "node_type": "argument_list", "value": "()"},
                ],
            },
        ],
    }


def _base_code(tmp_path: Path) -> dict:
    code_base,_=_knowledge_output(tmp_path/'code',repo_ids=['model'],ddl=[
        'create table code_declared_type(repo_id varchar,type_occurrence_id varchar,fully_qualified_name varchar)',
        'create table code_declared_field(field_occurrence_id varchar,name varchar)',
        'create table code_declared_effective_field(effective_field_occurrence_id varchar,effective_owner_type_occurrence_id varchar,field_occurrence_id varchar,field_name varchar,is_inherited boolean)',
        'create table code_declared_relationship(relationship_occurrence_id varchar,repo_id varchar,source_type_occurrence_id varchar,target_type_occurrence_id varchar,field_occurrence_id varchar)',
        'create table code_declared_inheritance(subtype_occurrence_id varchar,resolved_supertype_occurrence_id varchar)',
    ],inserts=[
        ('insert into code_declared_type values (?,?,?)',[('model','parent','demo.Parent'),('model','base-child','demo.AbstractChild'),('model','child','demo.Child')]),
        ('insert into code_declared_field values (?,?)',[('field','children')]),
        ('insert into code_declared_effective_field values (?,?,?,?,?)',[('ef','parent','field','children',True)]),
        ('insert into code_declared_relationship values (?,?,?,?,?)',[('rel','model','parent','base-child','field')]),
        ('insert into code_declared_inheritance values (?,?)',[('child','base-child')]),
    ])
    return {"artifact_id":"code-art","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","source_materialization_id":"code-declared-data-model",**code_base}


def _storage_fixture(tmp_path: Path, *, extra_records: list[tuple]=[], derivations: list[tuple]=[]) -> dict:
    storage_base,_=_knowledge_output(tmp_path/'storage',repo_ids=['adapter'],ddl=[
        'create table model_storage_record(observation_id varchar,repo_id varchar,storage_alias varchar,storage_key_field varchar,storage_key_expression varchar,payload_json json)',
        'create table model_storage_reference(observation_id varchar,repo_id varchar,source_alias varchar,source_field varchar,target_alias varchar,target_storage_key_expression varchar,payload_json json)',
        'create table model_storage_key_lineage(observation_id varchar,repo_id varchar,source_alias varchar,relationship_field varchar,target_alias varchar,composed_target_key_expression varchar,payload_json json)',
        'create table model_storage_reference_derivation(observation_id varchar,repo_id varchar,source_alias varchar,relationship_field varchar,reference_operation varchar,source_operation varchar,value_converter_operation varchar,composed_reference_value_expression varchar,payload_json json)',
    ],inserts=[
        ('insert into model_storage_record values (?,?,?,?,?,?)',[('r','adapter','demo.Parent','id','"Parent_" + id','{}'),*extra_records]),
        ('insert into model_storage_key_lineage values (?,?,?,?,?,?,?)',[('l','adapter','demo.Parent','children','demo.Child','parentKey + ".children_" + child.id','{}')]),
        ('insert into model_storage_reference_derivation values (?,?,?,?,?,?,?,?,?)',derivations),
    ])
    return {"artifact_id":"storage-art","model_kind":"model-storage-semantics","schema_version":"model-storage-semantics/v1","source_materialization_id":"model-storage-semantics",**storage_base}


def _materialize(tmp_path: Path, code: dict, storage: dict) -> Path:
    req={"schema_version":"knowledge_materialization_request/v1","materialization_id":"logical-storage-mapping","scope_id":"workspace","inputs":{"evidence_artifacts":[],"knowledge_artifacts":[code,storage]},"parameters":{}}
    result=materialize(req,tmp_path/'out')
    assert result['status']=='completed'
    return tmp_path/'out/knowledge-layer.duckdb'


def test_logical_storage_mapping_uses_exact_fqcn_effective_field_and_inheritance(tmp_path: Path) -> None:
    assert 'logical-storage-mapping' in registered_materialization_ids()
    code=_base_code(tmp_path)
    storage=_storage_fixture(tmp_path)
    db=_materialize(tmp_path,code,storage)
    c=duckdb.connect(str(db),read_only=True)
    assert c.execute('select mapping_status,mapping_basis from logical_storage_entity_mapping').fetchone()==('matched','exact_storage_alias_to_fqcn')
    row=c.execute('select field_is_inherited,target_alignment,knowledge_class,mapping_status from logical_storage_relationship_mapping').fetchone()
    assert row==(True,'observed_inherited_specialization','derived','matched')
    join=c.execute("select join_kind,status,join_readiness from logical_storage_join_semantic where relationship_occurrence_id='rel'").fetchone()
    assert join==('storage_key_relationship','strongly_supported','transformation_required')
    assert c.execute('select count(*) from logical_storage_mapping_gap').fetchone()[0]==0
    c.close()


def test_logical_storage_mapping_materializes_exact_reference_to_target_identity_join(tmp_path: Path) -> None:
    target_tree=_getter_tree('Country_','code')
    source_tree=_getter_tree('Country_','code')
    code_base,_=_knowledge_output(tmp_path/'code',repo_ids=['model'],ddl=[
        'create table code_declared_type(repo_id varchar,type_occurrence_id varchar,fully_qualified_name varchar)',
        'create table code_declared_field(field_occurrence_id varchar,name varchar)',
        'create table code_declared_effective_field(effective_field_occurrence_id varchar,effective_owner_type_occurrence_id varchar,field_occurrence_id varchar,field_name varchar,is_inherited boolean)',
        'create table code_declared_relationship(relationship_occurrence_id varchar,repo_id varchar,source_type_occurrence_id varchar,target_type_occurrence_id varchar,field_occurrence_id varchar)',
        'create table code_declared_inheritance(subtype_occurrence_id varchar,resolved_supertype_occurrence_id varchar)',
    ],inserts=[
        ('insert into code_declared_type values (?,?,?)',[('model','individual','demo.Individual'),('model','country','demo.Country')]),
        ('insert into code_declared_field values (?,?)',[('birth-country','birthCountry')]),
        ('insert into code_declared_effective_field values (?,?,?,?,?)',[('ef','individual','birth-country','birthCountry',False)]),
        ('insert into code_declared_relationship values (?,?,?,?,?)',[('rel-country','model','individual','country','birth-country')]),
    ])
    code={"artifact_id":"code-art","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","source_materialization_id":"code-declared-data-model",**code_base}
    storage=_storage_fixture(
        tmp_path,
        extra_records=[('country-key','adapter','demo.Country','code','"Country_" + country.getCode()',json.dumps({'properties':{'storage_key_expression_tree':target_tree}}))],
        derivations=[('country-ref','adapter','demo.Individual','birthCountry','referenceField','Individual.convert','convertCountry','"Country_" + individual.getBirthCountry().getCode()',json.dumps({'properties':{'composed_reference_value_expression_tree':source_tree}}))],
    )
    db=_materialize(tmp_path,code,storage)
    c=duckdb.connect(str(db),read_only=True)
    row=c.execute("select join_kind,status,join_readiness,candidate_count,basis_json from logical_storage_join_semantic where relationship_occurrence_id='rel-country'").fetchone()
    assert row[:4]==('reference_value_to_target_identity','strongly_supported','executable_storage_join',1)
    basis=json.loads(row[4])
    assert basis['match_basis']=='exact_structural_expression_signature'
    assert basis['physical_join_claimed'] is False
    correspondence=json.loads(c.execute("select structural_correspondences_json from logical_storage_join_semantic where relationship_occurrence_id='rel-country'").fetchone()[0])
    assert correspondence[0]['target_key_fields']==['code']
    c.close()


def test_storage_join_semantics_keep_multiple_relationships_for_one_field(tmp_path: Path) -> None:
    target_tree=_getter_tree('Country_','code')
    source_tree=_getter_tree('Country_','code')
    code_base,_=_knowledge_output(tmp_path/'code',repo_ids=['model'],ddl=[
        'create table code_declared_type(repo_id varchar,type_occurrence_id varchar,fully_qualified_name varchar)',
        'create table code_declared_field(field_occurrence_id varchar,name varchar)',
        'create table code_declared_effective_field(effective_field_occurrence_id varchar,effective_owner_type_occurrence_id varchar,field_occurrence_id varchar,field_name varchar,is_inherited boolean)',
        'create table code_declared_relationship(relationship_occurrence_id varchar,repo_id varchar,source_type_occurrence_id varchar,target_type_occurrence_id varchar,field_occurrence_id varchar)',
        'create table code_declared_inheritance(subtype_occurrence_id varchar,resolved_supertype_occurrence_id varchar)',
    ],inserts=[
        ('insert into code_declared_type values (?,?,?)',[('model','individual','demo.Individual'),('model','country','demo.Country'),('model','region','demo.Region')]),
        ('insert into code_declared_field values (?,?)',[('location','location')]),
        ('insert into code_declared_effective_field values (?,?,?,?,?)',[('ef','individual','location','location',False)]),
        ('insert into code_declared_relationship values (?,?,?,?,?)',[
            ('rel-country','model','individual','country','location'),('rel-region','model','individual','region','location')
        ]),
    ])
    code={"artifact_id":"code-art","model_kind":"code-declared-data-model","schema_version":"code-declared-data-model/v1","source_materialization_id":"code-declared-data-model",**code_base}
    storage=_storage_fixture(
        tmp_path,
        extra_records=[
            ('country-key','adapter','demo.Country','code','"Country_" + country.getCode()',json.dumps({'properties':{'storage_key_expression_tree':target_tree}})),
            ('region-key','adapter','demo.Region','id','"Region_" + region.getId()',json.dumps({'properties':{'storage_key_expression_tree':_getter_tree('Region_','id')}})),
        ],
        derivations=[('location-ref','adapter','demo.Individual','location','referenceField','Individual.convert','convertLocation','"Country_" + individual.getLocation().getCode()',json.dumps({'properties':{'composed_reference_value_expression_tree':source_tree}}))],
    )
    db=_materialize(tmp_path,code,storage)
    c=duckdb.connect(str(db),read_only=True)
    rows=c.execute("select relationship_occurrence_id,declared_target_fqcn,status,join_readiness from logical_storage_join_semantic where source_field='location' order by relationship_occurrence_id").fetchall()
    assert rows==[
        ('rel-country','demo.Country','strongly_supported','executable_storage_join'),
        ('rel-region','demo.Region','strongly_supported','requires_validation'),
    ]
    c.close()
