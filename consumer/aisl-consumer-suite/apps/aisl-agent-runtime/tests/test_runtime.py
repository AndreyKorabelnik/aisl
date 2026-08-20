from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import httpx

from aisl_sdk import AislClient, AislContractError
from aisl_agent_runtime.providers import ScriptedProvider
from aisl_agent_runtime.runtime import AgentRuntime, ConsumerProfile

SYSTEM='sdk-acceptance-rich'
REV='rev-test'
PROFILE='data-model/v1'


def revision_payload():
    return {
        'system_id': SYSTEM,
        'revision_id': REV,
        'base_revision_id': None,
        'ordinal': 1,
        'state': 'active',
        'capabilities': ['common.code-declared-data-model'],
        'knowledge_artifacts': [],
    }


def integration_profile():
    return {
        'schema_version':'llm_integration_profile/v1',
        'scope':{'system_id':SYSTEM,'revision_id':REV,'revision_binding':'pinned'},
        'capabilities':['common.code-declared-data-model'],
        'knowledge_artifacts':[],
        'integration_profile':{'profile_id':PROFILE,'profile_version':'1','profile_fingerprint':'x','fingerprint':'fp-1'},
        'policy':{'grounding':'GROUNDING RULE: facts require tool results.','evidence_statuses':['observed','ambiguity','gap'],'rules':{'no_relation_or_join_guessing':True}},
        'tools':[
            {
                'name':'search_declared_data_objects',
                'description':'search',
                'arguments':{'search':'string|null','include_fields':'boolean','offset':'integer','limit':'integer'},
                'required_capabilities':['common.code-declared-data-model'],
                'warnings':[],
                'api_binding':{
                    'binding_kind':'knowledge_api_http','method':'GET',
                    'path_template':f'/api/knowledge/v1/systems/{{system_id}}/data-model/declared-objects',
                    'revision_binding':{'location':'query','name':'revision_id','value_from':'scope.revision_id'},
                    'expected_schema_versions':['knowledge_api/v1'],
                    'arguments':{
                        'search':{'location':'query','name':'search','transform':'identity'},
                        'include_fields':{'location':'query','name':'include_fields','transform':'bool'},
                        'offset':{'location':'query','name':'offset','transform':'bounded_int'},
                        'limit':{'location':'query','name':'limit','transform':'bounded_int'},
                    },
                    'fixed_query':{},'operation_id':'search-op'
                }
            },
            {
                'name':'get_data_model_object_context',
                'description':'context',
                'arguments':{'object_id':'string'},
                'required_capabilities':['common.code-declared-data-model'],
                'warnings':['do not infer join'],
                'api_binding':{
                    'binding_kind':'knowledge_api_http','method':'GET',
                    'path_template':f'/api/knowledge/v1/systems/{{system_id}}/data-model/object-context/{{object_id}}',
                    'revision_binding':{'location':'query','name':'revision_id','value_from':'scope.revision_id'},
                    'expected_schema_versions':['data_model_object_context/v1'],
                    'arguments':{'object_id':{'location':'path','name':'object_id','transform':'url_segment'}},
                    'fixed_query':{},'operation_id':'ctx-op'
                }
            }
        ],
        'retrieval_guidance':{'profile_id':PROFILE,'profile_version':'1','content':'RETRIEVAL RULE: exact object -> object context.'},
        'generated_from':{}
    }


def transport(request: httpx.Request) -> httpx.Response:
    path=request.url.path
    q=parse_qs(request.url.query.decode() if isinstance(request.url.query,bytes) else str(request.url.query))
    if path == f'/api/knowledge/v1/systems/{SYSTEM}/revisions/{REV}':
        return httpx.Response(200,json=revision_payload())
    if path == f'/api/knowledge/v1/systems/{SYSTEM}/llm-integration-profile':
        assert q['revision_id']==[REV]; assert q['profile_id']==[PROFILE]
        return httpx.Response(200,json=integration_profile())
    if path == f'/api/knowledge/v1/systems/{SYSTEM}/data-model/declared-objects':
        assert q['revision_id']==[REV]; assert q['search']==['Individual']; assert q['include_fields']==['false']
        return httpx.Response(200,json={'schema_version':'knowledge_api/v1','items':[{'object_id':'t-ind','fqcn':'com.acme.Individual'}],'page':{'offset':0,'limit':20,'total':1}})
    if path == f'/api/knowledge/v1/systems/{SYSTEM}/data-model/object-context/t-ind':
        assert q['revision_id']==[REV]
        return httpx.Response(200,json={
            'schema_version':'data_model_object_context/v1','object':{'object_id':'t-ind'},
            'relationships':[{'storage_semantics':{'status':'ambiguous','candidate_mappings':[{'key':'a'},{'key':'b'}]},'physical_mapping':{'physical_join_confirmed':False}}]
        })
    return httpx.Response(404,json={'detail':path})


def client():
    return AislClient('http://test',transport=httpx.MockTransport(transport))


def test_profile_is_revision_pinned_and_prompt_uses_profile_rules():
    p=ConsumerProfile.load(client(),system_id=SYSTEM,revision_id=REV,profile_id=PROFILE)
    assert p.system_id==SYSTEM and p.revision_id==REV and p.profile_id==PROFILE
    assert 'GROUNDING RULE' in p.system_prompt
    assert 'RETRIEVAL RULE' in p.system_prompt
    assert 'get_data_model_object_context' in p.system_prompt
    assert {x['function']['name'] for x in p.openai_tools}=={'search_declared_data_objects','get_data_model_object_context'}


def test_scripted_tool_loop_preserves_trace_and_scope():
    provider=ScriptedProvider([
        {'message':{'role':'assistant','content':None,'tool_calls':[{'id':'s1','type':'function','function':{'name':'search_declared_data_objects','arguments':json.dumps({'search':'Individual','include_fields':False,'offset':0,'limit':20})}}]},'finish_reason':'tool_calls'},
        {'message':{'role':'assistant','content':None,'tool_calls':[{'id':'s2','type':'function','function':{'name':'get_data_model_object_context','arguments':json.dumps({'object_id':'t-ind'})}}]},'finish_reason':'tool_calls'},
        {'message':{'role':'assistant','content':'Ambiguous storage mapping; physical JOIN is not confirmed.'},'finish_reason':'stop'},
    ])
    runtime=AgentRuntime(client=client(),provider=provider)
    session=runtime.create_session(system_id=SYSTEM,revision_id=REV,profile_id=PROFILE)
    result=session.ask('How is Individual stored?')
    assert result['scope']['revision_id']==REV
    assert result['answer'].startswith('Ambiguous')
    calls=[c for r in result['trace'] for c in r['tool_calls']]
    assert [c['tool_name'] for c in calls]==['search_declared_data_objects','get_data_model_object_context']
    ctx=calls[1]['result']['relationships'][0]
    assert ctx['storage_semantics']['status']=='ambiguous'
    assert len(ctx['storage_semantics']['candidate_mappings'])==2
    assert ctx['physical_mapping']['physical_join_confirmed'] is False
    assert len(provider.calls)==3



def test_profile_scope_mismatch_is_rejected():
    def bad(request:httpx.Request)->httpx.Response:
        if '/revisions/' in request.url.path: return httpx.Response(200,json=revision_payload())
        p=integration_profile(); p['scope']['revision_id']='rev-other'
        return httpx.Response(200,json=p)
    c=AislClient('http://test',transport=httpx.MockTransport(bad))
    try:
        ConsumerProfile.load(c,system_id=SYSTEM,revision_id=REV,profile_id=PROFILE)
    except AislContractError as exc:
        assert 'scope does not match' in str(exc)
    else:
        raise AssertionError('expected ValueError')
