from prepared_knowledge_runtime.consumer_contracts import EvidenceRef, QueryRequest, QueryResult, ScopeRef


def test_query_result_serializes_stable_contract():
    scope = ScopeRef("repository", "demo", ("demo",))
    request = QueryRequest("get_scope_overview", scope, max_results=1)
    result = QueryResult(request=request, items=({"name": "demo"},), evidence=(EvidenceRef("e1", "demo", "src/A.java", 1, 2),))
    payload = result.to_dict()
    assert payload["schema_version"] == "knowledge_query/v1"
    assert payload["query"]["scope"]["id"] == "demo"
    assert payload["evidence"][0]["path"] == "src/A.java"
