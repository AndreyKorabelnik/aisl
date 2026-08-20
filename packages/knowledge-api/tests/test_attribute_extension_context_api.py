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
        rows = [
            (
                'join-country','ucp','type-birth-place','com.acme.BirthPlace','field-country','country','Country',
                'type-country','com.acme.Country','dictionary','one','exact',False,'[]',
                'resolve_reference_value_to_target_key','confirmed','transformation_required',
                json.dumps(['"Country_" + birthPlace.getCountry().getCode()']),json.dumps(['code']),
                json.dumps(['"Country_" + country.getCode()']),json.dumps([]),json.dumps([]),
                json.dumps([{'match_basis':'exact_structural_expression_signature','canonical_signature':['Country_', 'code']}]),
                json.dumps({'observed_sql_relations':['src.birth_place']}),
                json.dumps({'observed_sql_relations':['src.country'],'observed_field_usages':['name']}),
                json.dumps([{
                    'sql_join_edge_id':'sql-join-country','file':'country.sql','line_start':12,
                    'join_type':'left','predicate':'bp.country_code = c.code',
                    'column_pairs':[{'left_column':'country_code','right_column':'code'}],
                    'resolution_status':'resolved','physical_join_confirmed':True,
                    'relationship_relevance':'exact_source_field_to_target_key',
                    'relationship_relevance_basis':{'exact_column_pair_match':True},
                }]),json.dumps([]),
                json.dumps({
                    'classification':'exact_structural_expression_signature',
                    'source_storage_field_observation_count':1,
                    'source_storage_field_observations':[{
                        'evidence_kind':'observed_storage_reference_field','observation_id':'storage-1',
                        'repo_id':'ucp','storage_reference_field_name':'countryCode',
                        'reference_operation':'referenceField',
                        'reference_value_expression':'Country_ + countryCode',
                        'source_refs':[{'repository_relative_path':'BirthPlace.java','line_start':42,'line_end':42,'extractor':'storage-profile'}],
                    }],
                    'source_relationship_field_observed_in_sql':True,
                    'exact_relationship_sql_join_observed':True,
                    'sql_join_example_relevance_counts':{'exact_source_field_to_target_key':1},
                    'usefulness':{
                        'classification':'confirmed','claim_kind':'existing_sql_join',
                        'recommended_action':'reuse_observed_sql_join','residual_checks':[],
                        'classification_basis':{'relationship_confidence':'confirmed'},
                        'row_multiplicity':'one',
                    },
                }),json.dumps({'code_relationship_id':'rel-country','source_refs':[{'repository_relative_path':'BirthPlace.java','line_start':40,'line_end':43,'extractor':'java'}]}),'[]',
            ),
            (
                'join-identifications','ucp','type-individual','com.acme.Individual','field-identifications','identifications','List<AbstractIdentification>',
                'type-identification','com.acme.AbstractIdentification','polymorphic_owned','many','observed_inherited_specialization',True,
                json.dumps(['com.acme.Passport','com.acme.Inn']),'resolve_reference_collection','confirmed',
                'unresolved_requires_subtype_or_representation','[]','[]','[]','[]','[]','[]',
                json.dumps({'observed_sql_relations':['src.individual']}),json.dumps({}),'[]','[]',
                json.dumps({
                    'classification':'polymorphic_collection',
                    'source_storage_field_observation_count':0,
                    'source_storage_field_observations':[],
                    'source_relationship_field_observed_in_sql':False,
                    'exact_relationship_sql_join_observed':False,
                    'sql_join_example_relevance_counts':{},
                    'usefulness':{
                        'classification':'ambiguity','claim_kind':'polymorphic_collection_navigation',
                        'recommended_action':'select_concrete_target_or_representation_before_sql',
                        'candidate_targets':['com.acme.Passport','com.acme.Inn'],
                        'residual_checks':['select_subtype_or_physical_representation'],
                        'classification_basis':{'relationship_confidence':'confirmed','polymorphic':True},
                        'row_multiplicity':'many',
                    },
                }),json.dumps({'code_relationship_id':'rel-identifications','source_refs':[{'repository_relative_path':'Individual.java','line_start':90,'line_end':90,'extractor':'java'}]}),
                json.dumps([{'code':'physical_join_not_established_for_polymorphic_collection','message':'subtype required'}]),
            ),
        ]
        con.executemany(
            "INSERT INTO attribute_extension_join_semantic VALUES (" + ",".join("?" for _ in range(30)) + ")",
            rows,
        )
        con.execute("""CREATE TABLE attribute_extension_object_anchor (
            anchor_id VARCHAR, logical_type_occurrence_id VARCHAR, logical_fully_qualified_name VARCHAR,
            storage_aliases_json JSON, storage_key_fields_json JSON, storage_key_expressions_json JSON,
            observed_sql_relations_json JSON, observed_field_usages_json JSON, observed_sql_projections_json JSON,
            observed_sql_joins_json JSON, physical_candidates_json JSON, knowledge_class VARCHAR,
            basis_json JSON, provenance_json JSON)""")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-ind','t','com.acme.Individual','[]','[]','[]','[]','[]','[]','[]','[]','observed','{}','{}')")
        con.execute("INSERT INTO attribute_extension_object_anchor VALUES ('a-ident','t2','com.acme.AbstractIdentification','[]','[]','[]','[]','[]','[]','[]','[]','observed','{}','{}')")
        con.execute("""CREATE TABLE attribute_extension_context_gap (
            gap_id VARCHAR, gap_kind VARCHAR, severity VARCHAR, owner_kind VARCHAR, owner_id VARCHAR,
            message VARCHAR, details_json JSON)""")
        con.execute("INSERT INTO attribute_extension_context_gap VALUES ('g-ident','polymorphic_collection_sql_unresolved','info','join_semantic','join-identifications','subtype required','{}')")
    finally:
        con.close()
    return path


def test_http_endpoint_exposes_agent_ready_context_without_resolving_polymorphic_join(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [KnowledgeArtifactSpec(
            database=artifact,
            model_kind='data-model-attribute-extension-context',
            schema_version='data-model-attribute-extension-context/v1',
            materialization_id='data-model-attribute-extension-context',
            capabilities=('common.data-model-attribute-extension-context','common.data-model-agent-join-semantics'),
        )],
        scope_id='ucp', execution_token='run-ucp',
    )
    settings = KnowledgeApiSettings(database_path=tmp_path/'api.sqlite3', allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f'{KNOWLEDGE_API_PREFIX}/systems', json={'system_id':'ucp','display_name':'UCP'}).status_code == 201
        pub = client.post(f'{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions', json=publication_payload(result))
        assert pub.status_code == 201, pub.text
        revision_id = pub.json()['revision']['revision_id']
        response = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/attribute-extension-context',
            params={'revision_id':revision_id,'source_type':'com.acme.Individual','source_field':'identifications'},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['context_query_schema_version'] == 'data-model-attribute-extension-query/v1'
    assert body['page']['total'] == 1
    item = body['items'][0]
    assert item['join_method'] == 'resolve_reference_collection'
    assert item['polymorphic'] is True
    assert item['sql_generation_status'] == 'unresolved_requires_subtype_or_representation'
    assert item['diagnostics'][0]['code'] == 'physical_join_not_established_for_polymorphic_collection'
    assert {a['logical_fully_qualified_name'] for a in body['object_anchors']} == {'com.acme.Individual','com.acme.AbstractIdentification'}
    assert body['gap_count'] == 1
    assert body['gaps'][0]['gap_kind'] == 'polymorphic_collection_sql_unresolved'


def test_compact_guidance_promotes_usefulness_and_preserves_ambiguity_without_new_inference(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [KnowledgeArtifactSpec(
            database=artifact,
            model_kind='data-model-attribute-extension-context',
            schema_version='data-model-attribute-extension-context/v1',
            materialization_id='data-model-attribute-extension-context',
            capabilities=('common.data-model-attribute-extension-context','common.data-model-agent-join-semantics'),
        )],
        scope_id='ucp-guidance', execution_token='run-ucp-guidance',
    )
    settings = KnowledgeApiSettings(database_path=tmp_path/'guidance.sqlite3', allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f'{KNOWLEDGE_API_PREFIX}/systems', json={'system_id':'ucp-guidance','display_name':'UCP'}).status_code == 201
        pub = client.post(f'{KNOWLEDGE_API_PREFIX}/systems/ucp-guidance/revisions', json=publication_payload(result))
        assert pub.status_code == 201, pub.text
        revision_id = pub.json()['revision']['revision_id']

        raw = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/ucp-guidance/data-model/attribute-extension-context',
            params={'revision_id':revision_id,'source_type':'com.acme.BirthPlace','source_field':'country'},
        )
        guidance = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/ucp-guidance/data-model/attribute-extension-guidance',
            params={'revision_id':revision_id,'source_type':'com.acme.BirthPlace','source_field':'country'},
        )
        ambiguous = client.get(
            f'{KNOWLEDGE_API_PREFIX}/systems/ucp-guidance/data-model/attribute-extension-guidance',
            params={'revision_id':revision_id,'source_type':'com.acme.Individual','source_field':'identifications'},
        )

    assert raw.status_code == guidance.status_code == ambiguous.status_code == 200
    assert len(guidance.content) < len(raw.content)
    body = guidance.json()
    assert body['guidance_schema_version'] == 'data-model-attribute-extension-guidance/v1'
    assert body['projection']['semantic_derivation'] == 'none'
    assert body['projection']['canonical_detail_endpoint'] == '/data-model/attribute-extension-context'
    item = body['items'][0]
    assert item['source_fqcn'] == 'com.acme.BirthPlace'
    assert item['source_field'] == 'country'
    assert item['target_fqcn'] == 'com.acme.Country'
    assert item['confidence'] == 'confirmed'
    assert item['usefulness']['classification'] == 'confirmed'
    assert item['usefulness']['claim_kind'] == 'existing_sql_join'
    assert item['observed_sql_join_examples'][0]['relationship_relevance'] == 'exact_source_field_to_target_key'
    assert item['observed_sql_join_examples'][0]['predicate'] == 'bp.country_code = c.code'
    assert item['source_storage_field_observations'][0]['storage_reference_field_name'] == 'countryCode'
    assert item['provenance']['code_relationship_id'] == 'rel-country'
    assert 'basis' not in item
    assert 'object_anchors' not in body

    amb = ambiguous.json()['items'][0]
    assert amb['confidence'] == 'confirmed'
    assert amb['polymorphic'] is True
    assert amb['usefulness']['classification'] == 'ambiguity'
    assert amb['usefulness']['candidate_targets'] == ['com.acme.Passport','com.acme.Inn']
    assert amb['usefulness']['residual_checks'] == ['select_subtype_or_physical_representation']
    assert amb['diagnostics'][0]['code'] == 'physical_join_not_established_for_polymorphic_collection'


def test_guidance_projection_reports_bounded_truncation_explicitly() -> None:
    from knowledge_api.contract_v1.consumer_projections import project_attribute_extension_guidance

    join_examples = [
        {
            'sql_join_edge_id': f'j-{idx}',
            'predicate': f'a.c{idx} = b.c{idx}',
            'relationship_relevance': 'target_key_analog',
            'column_pairs': [{'left_column': f'c{pair}', 'right_column': f'k{pair}'} for pair in range(10)],
        }
        for idx in range(20)
    ]
    raw = {
        'schema_version':'knowledge_api/v1',
        'context_schema_version':'data-model-attribute-extension-context/v1',
        'system_id':'demo','revision_id':'rev-1','filters':{},
        'page':{'offset':0,'limit':50,'total':1},
        'summary':{},
        'items':[{
            'join_semantic_id':'join-1','source_repo_id':'repo','source_type_occurrence_id':'s',
            'source_fqcn':'example.Source','source_field_occurrence_id':'sf','source_field':'ref',
            'target_type_occurrence_id':'t','target_fqcn':'example.Target','relationship_kind':'declared',
            'cardinality':'one','target_alignment':'exact','polymorphic':False,'concrete_targets':[],
            'join_method':'resolve_reference_value_to_target_key','confidence':'confirmed',
            'sql_generation_status':'transformation_required','observed_sql_join_examples':join_examples,
            'basis':{'usefulness':{'classification':'strongly_supported','claim_kind':'proposed_sql_join',
                    'recommended_action':'derive_join_from_published_reference_and_key_encoding',
                    'residual_checks':['confirm_source_sql_column_or_projection']}},
            'diagnostics':[],
        }],
        'gaps':[{'gap_id':f'g-{i}','gap_kind':'demo','severity':'info','owner_kind':'join_semantic','owner_id':'join-1','message':'x'} for i in range(30)],
        'gap_count':30,'gaps_truncated':False,
    }
    view = project_attribute_extension_guidance(raw)
    assert len(json.dumps(view, ensure_ascii=False)) < len(json.dumps(raw, ensure_ascii=False))
    item = view['items'][0]
    assert len(item['observed_sql_join_examples']) == 6
    assert item['projection']['observed_sql_join_examples'] == {'source_total':20,'presented':6,'truncated':True}
    assert item['observed_sql_join_examples'][0]['column_pairs_projection']['truncated'] is True
    assert len(view['gaps']) == 20
    assert view['gaps_truncated'] is True
    assert view['projection']['gap_projection'] == {'source_total':30,'presented':20,'truncated':True}
