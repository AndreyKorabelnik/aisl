from aisl_agent_runtime.providers import ScriptedProvider


def test_scripted_provider_is_explicit_test_double():
    p=ScriptedProvider([{'message':{'role':'assistant','content':'x'},'finish_reason':'stop'}])
    out=p.complete(system_prompt='s',messages=[{'role':'user','content':'q'}],tools=[])
    assert out['message']['content']=='x'
    assert len(p.calls)==1
