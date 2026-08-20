from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from aisl_sdk import (
    project_data_model_object,
    AislApiError,
    AislClient,
    AislContractError,
    AislTransportError,
)


def _response(request: httpx.Request, status: int, payload) -> httpx.Response:
    return httpx.Response(status, json=payload, request=request)


def test_list_systems_paginates_and_preserves_search() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        q = request.url.params
        offset = int(q["offset"])
        assert q["search"] == "ucp"
        if offset == 0:
            return _response(request, 200, {
                "schema_version": "knowledge_api/v1",
                "items": [
                    {"system_id": "ucp-a", "display_name": "A", "active_revision_id": "rev-a", "revision_count": 1, "created_at": "2026-08-17T00:00:00Z", "updated_at": "2026-08-17T00:00:00Z"},
                    {"system_id": "ucp-b", "display_name": "B", "active_revision_id": None, "revision_count": 0, "created_at": "2026-08-17T00:00:00Z", "updated_at": "2026-08-17T00:00:00Z"},
                ],
                "page": {"offset": 0, "limit": 2, "total": 3},
            })
        return _response(request, 200, {
            "schema_version": "knowledge_api/v1",
            "items": [{"system_id": "ucp-c", "display_name": "C", "active_revision_id": "rev-c", "revision_count": 2, "created_at": "2026-08-17T00:00:00Z", "updated_at": "2026-08-17T00:00:00Z"}],
            "page": {"offset": 2, "limit": 1, "total": 3},
        })

    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        systems = client.list_systems(search="ucp", page_size=2)
    assert [s.system_id for s in systems] == ["ucp-a", "ucp-b", "ucp-c"]
    assert len(seen) == 2


def test_active_revision_is_explicitly_resolved_then_pinned() -> None:
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/api/knowledge/v1/systems/ucp":
            return _response(request, 200, {"system_id": "ucp", "display_name": "UCP", "active_revision_id": "rev-2", "revision_count": 2, "created_at": "x", "updated_at": "x", "metadata": {}})
        if request.url.path == "/api/knowledge/v1/systems/ucp/revisions/rev-2":
            return _response(request, 200, _revision("ucp", "rev-2"))
        raise AssertionError(request.url)

    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        revision = client.active_revision("ucp")
        assert revision.revision_id == "rev-2"
        # A pinned refresh reads the exact id and never re-resolves active_revision_id.
        requested.clear()
        refreshed = revision.refresh_metadata()
        assert refreshed.revision_id == "rev-2"
        assert all("/systems/ucp/revisions/rev-2" in url for url in requested)
        assert all(not url.endswith("/systems/ucp") for url in requested)


def test_explicit_revision_rejects_identity_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, 200, _revision("ucp", "rev-other"))
    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AislContractError, match="identity mismatch"):
            client.revision("ucp", "rev-wanted")


def test_revision_products_and_capabilities_are_pinned() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/revisions/" in request.url.path:
            return _response(request, 200, _revision("ucp", "rev-1"))
        if request.url.path.endswith("/capabilities"):
            assert request.url.params["revision_id"] == "rev-1"
            return _response(request, 200, {"schema_version": "knowledge_api/v1", "system_id": "ucp", "revision_id": "rev-1", "capabilities": ["common.code-declared-data-model"]})
        if request.url.path.endswith("/knowledge-artifacts"):
            assert request.url.params["revision_id"] == "rev-1"
            return _response(request, 200, {"schema_version": "knowledge_api/v1", "system_id": "ucp", "revision_id": "rev-1", "items": [_product()], "page": {"offset": 0, "limit": 100, "total": 1}})
        raise AssertionError(request.url)

    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        revision = client.revision("ucp", "rev-1")
        assert revision.capabilities == ("common.code-declared-data-model",)
        assert revision.get_capabilities() == ("common.code-declared-data-model",)
        assert [p.artifact_id for p in revision.list_products()] == ["kp-1"]


def test_data_model_helpers_always_send_exact_revision() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "/revisions/" in request.url.path:
            return _response(request, 200, _revision("ucp", "rev-fixed"))
        assert request.url.params["revision_id"] == "rev-fixed"
        if request.url.path.endswith("/declared-objects"):
            return _response(request, 200, {"items": [{"object_id": "type:Individual", "qualified_name": "pkg.Individual"}], "page": {"offset": 0, "limit": 100, "total": 1}})
        if "/data-model/object-context/" in request.url.path:
            return _response(request, 200, {"object": {"object_id": "type:Individual"}, "storage_context": {"status": "ambiguous"}})
        raise AssertionError(request.url)

    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        revision = client.revision("ucp", "rev-fixed")
        objects = revision.search_declared_data_objects(search="Individual")
        assert objects[0]["qualified_name"] == "pkg.Individual"
        context = revision.get_data_model_object_context("type:Individual")
        assert context["storage_context"]["status"] == "ambiguous"


def test_path_segments_are_percent_encoded() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path)
        return _response(request, 200, {"object": {"object_id": "a/b"}})

    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        revision = object.__new__(__import__("aisl_sdk").PinnedRevision)
        object.__setattr__(revision, "client", client)
        object.__setattr__(revision, "summary", __import__("aisl_sdk").RevisionSummary.from_payload(_revision("s/id", "r/id")))
        revision.get_data_model_object_context("a/b")
    raw = seen[0].decode()
    assert "s%2Fid" in raw and "a%2Fb" in raw


def test_http_error_is_structured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, 404, {"code": "not_found", "message": "missing"})
    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AislApiError) as caught:
            client.get_system("missing")
    assert caught.value.status_code == 404
    assert caught.value.detail["code"] == "not_found"


def test_non_json_and_non_object_are_contract_errors() -> None:
    responses = iter([
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[1, 2, 3]),
    ])
    def handler(request: httpx.Request) -> httpx.Response:
        r = next(responses)
        r.request = request
        return r
    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AislContractError, match="non-JSON"):
            client.get_json("/x")
        with pytest.raises(AislContractError, match="root must be an object"):
            client.get_json("/x")


def test_transport_error_is_distinct() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)
    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AislTransportError, match="ConnectError"):
            client.get_json("/x")


def test_pagination_rejects_non_object_items_and_bounds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, 200, {"items": ["bad"], "page": {"offset": 0, "limit": 1, "total": 1}})
    with AislClient("http://knowledge", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AislContractError, match="items must be objects"):
            client.collect_pages("/x", page_size=1)
        with pytest.raises(ValueError, match="between 1 and 500"):
            client.collect_pages("/x", page_size=501)
        assert client.collect_pages("/x", max_results=0) == []


def test_custom_headers_are_forwarded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Test-Token"] == "abc"
        return _response(request, 200, {"schema_version": "knowledge_api/v1", "capabilities": []})
    with AislClient("http://knowledge", headers={"X-Test-Token": "abc"}, transport=httpx.MockTransport(handler)) as client:
        assert client.service_capabilities()["capabilities"] == []


def test_no_framework_dependency_is_imported() -> None:
    import aisl_sdk
    forbidden = ("code_analyzer_core", "static_analysis_runner", "knowledge_layer_core", "knowledge_control_plane", "knowledge_api")
    source = open(aisl_sdk.__file__, encoding="utf-8").read()
    for name in forbidden:
        assert name not in source


def _product() -> dict:
    return {
        "artifact_id": "kp-1",
        "model_kind": "code-declared-data-model",
        "schema_version": "code_declared_data_model/v1",
        "product_slot_id": "slot-1",
        "origin_kind": "derived",
        "producer_ref": "knowledge-layer-core@1",
        "producer_contract_ref": "materialization/x",
        "content_fingerprint": "a" * 64,
        "source_materialization_id": "code-declared-data-model",
        "physical_artifacts": [
            {"role": "database", "uri": "aisl+sha256://" + "b" * 64, "sha256": "b" * 64, "media_type": "application/vnd.duckdb"},
            {"role": "manifest", "uri": "aisl+sha256://" + "c" * 64, "sha256": "c" * 64, "media_type": "application/json"},
        ],
        "capabilities": ["common.code-declared-data-model"],
        "coverage": {}, "diagnostics": [], "provenance": {}, "exact_dependency_product_ids": [],
    }


def _revision(system_id: str, revision_id: str) -> dict:
    return {
        "system_id": system_id,
        "revision_id": revision_id,
        "base_revision_id": None,
        "ordinal": 1,
        "state": "active",
        "created_at": "2026-08-17T00:00:00Z",
        "execution": {
            "schema_version": "knowledge_execution_result/v2", "status": "completed", "runner_version": "0.0",
            "result_fingerprint": "d" * 64, "plan_fingerprint": "e" * 64, "knowledge_profile_id": "p",
            "scope_kind": "system", "scope_id": system_id, "started_at": "2026-08-17T00:00:00Z", "completed_at": "2026-08-17T00:00:00Z", "semantic_policy": {},
        },
        "execution_result": {"uri": "aisl+sha256://" + "f" * 64, "sha256": "f" * 64, "media_type": "application/json", "schema_version": "knowledge_execution_result/v2"},
        "knowledge_artifacts": [_product()],
        "capabilities": ["common.code-declared-data-model"],
        "labels": [], "metadata": {},
    }


def test_revision_integration_profile_and_tool_execution_are_pinned() -> None:
    profile = {
        "schema_version":"llm_integration_profile/v1",
        "scope":{"system_id":"ucp","revision_id":"rev-1","revision_binding":"pinned"},
        "integration_profile":{"profile_id":"data-model/v1","fingerprint":"fp"},
        "tools":[{
            "name":"search_declared_data_objects","description":"search","arguments":{"search":"string|null","include_fields":"boolean"},
            "api_binding":{"binding_kind":"knowledge_api_http","method":"GET","path_template":"/api/knowledge/v1/systems/{system_id}/data-model/declared-objects","revision_binding":{"location":"query","name":"revision_id"},"arguments":{"search":{"location":"query","name":"search","transform":"identity"},"include_fields":{"location":"query","name":"include_fields","transform":"bool"}},"fixed_query":{},"expected_schema_versions":["knowledge_api/v1"],"operation_id":"search-op"}
        }],
        "policy":{"grounding":"x"},"retrieval_guidance":{"content":"y"}
    }
    def handler(request: httpx.Request) -> httpx.Response:
        if "/revisions/" in request.url.path:
            return _response(request,200,_revision("ucp","rev-1"))
        if request.url.path.endswith("/llm-integration-profile"):
            assert request.url.params["revision_id"]=="rev-1"; assert request.url.params["profile_id"]=="data-model/v1"
            return _response(request,200,profile)
        if request.url.path.endswith("/declared-objects"):
            assert request.url.params["revision_id"]=="rev-1"; assert request.url.params["search"]=="Individual"; assert request.url.params["include_fields"]=="false"
            return _response(request,200,{"items":[{"object_id":"t-ind"}],"page":{"offset":0,"limit":100,"total":1}})
        raise AssertionError(request.url)
    with AislClient("http://knowledge",transport=httpx.MockTransport(handler)) as client:
        integration=client.revision("ucp","rev-1").integration("data-model/v1")
        assert integration.fingerprint=="fp"
        result=integration.execute_tool("search_declared_data_objects",{"search":"Individual","include_fields":False})
        assert result.operation_id=="search-op"
        assert result.result["items"][0]["object_id"]=="t-ind"


def test_integration_rejects_unlisted_tool() -> None:
    from aisl_sdk import ConsumerIntegration
    integration=ConsumerIntegration(client=None,system_id="s",revision_id="r",profile_id="p",fingerprint="",raw={"tools":[]})
    with pytest.raises(AislContractError, match="not allowed"):
        integration.execute_tool("invent_join",{})


def _projection_context(relationships):
    return {
        "schema_version": "data_model_object_context/v2",
        "system_id": "s",
        "revision_id": "r",
        "object": {
            "object_id": "obj", "name": "Individual", "fqcn": "demo.Individual", "type_kind": "class",
            "documentation": {"description": "Person"},
        },
        "fields": [{"name": "location", "declared_type_expression": "Location"}],
        "relationships": relationships,
        "storage_identities": [],
        "storage_context": {"status": "available"},
        "gaps": [],
    }


def test_project_data_model_object_preserves_ambiguity_without_physical_join_fallback():
    context=_projection_context([{
        "relationship_id": "rel-1",
        "source_field": "location",
        "declared_relationship": {"relationship_id":"rel-1","relationship_kind":"field_reference"},
        "target": {"fqcn": "demo.Country", "name": "Country"},
        "cardinality": {"value": "one"},
        "storage_semantics": {
            "status": "ambiguous",
            "candidate_mappings": [
                {"storage_key_expression": "a", "storage_relation_kind": "single_reference", "knowledge_class": "confirmed"},
                {"storage_key_expression": "b", "storage_relation_kind": "single_reference", "knowledge_class": "confirmed"},
            ],
        },
        "storage_join": {
            "status": "ambiguous", "join_kind": "reference_value_to_target_identity", "join_readiness": "ambiguous",
            "candidate_count": 2, "basis": {"match_basis": "multiple_structural_join_signatures"},
            "provenance": {"evidence_ids": ["e1", "e2"]},
        },
        "physical_mapping": {"status": "not_observed", "physical_join_confirmed": False},
    }])
    out=project_data_model_object(context)
    rel=out["relationships"][0]
    assert rel["storage_status"] == "ambiguous"
    assert rel["ambiguity"]["candidate_count"] == 2
    assert rel["join"]["status"] == "ambiguous"
    assert "physical_join_confirmed" not in rel["join"]
    assert out["summary"]["ambiguous_relationship_count"] == 1


def test_project_data_model_object_preserves_multiple_relationships_for_one_field():
    relationships=[]
    for rel_id,target,status in [("rel-country","Country","confirmed"),("rel-region","Region","strongly_supported")]:
        relationships.append({
            "relationship_id": rel_id, "source_field": "location",
            "declared_relationship": {"relationship_id": rel_id, "relationship_kind": "field_reference"},
            "target": {"fqcn": f"demo.{target}", "name": target},
            "cardinality": {"value": "one"},
            "storage_semantics": {"status": "available"},
            "storage_join": {
                "status": status,
                "join_kind": "reference_value_to_target_identity",
                "join_readiness": "executable_storage_join" if status=="confirmed" else "requires_validation",
                "candidate_count": 1,
                "basis": {"match_basis": "exact_structural_expression_signature" if status=="confirmed" else "reference_derivation_plus_target_identity_without_exact_signature"},
                "provenance": {"evidence_ids": [rel_id+"-evidence"]},
            },
            "physical_mapping": {"physical_join_confirmed": False},
        })
    out=project_data_model_object(_projection_context(relationships), profile_id="data-model/v1", profile_fingerprint="fp")
    assert len(out["relationships"]) == 2
    assert [r["relationship_id"] for r in out["relationships"]] == ["rel-country","rel-region"]
    assert out["fields"][0]["relationship_count"] == 2
    assert out["summary"]["confirmed_storage_join_count"] == 1
    assert out["summary"]["strongly_supported_storage_join_count"] == 1
    assert out["profile_id"] == "data-model/v1"
    assert out["summary"]["executable_storage_join_count"] == 1


def test_project_data_model_object_counts_strongly_supported_executable_join():
    relationships=[{
        "relationship_id": "rel-country", "source_field": "country",
        "declared_relationship": {"relationship_id": "rel-country", "relationship_kind": "field_reference"},
        "target": {"fqcn": "demo.Country", "name": "Country"},
        "cardinality": {"value": "one"},
        "storage_semantics": {"status": "not_observed"},
        "storage_join": {
            "status": "strongly_supported",
            "join_kind": "reference_value_to_target_identity",
            "join_readiness": "executable_storage_join",
            "candidate_count": 1,
            "basis": {"match_basis": "exact_structural_expression_signature"},
            "provenance": {"evidence_ids": ["ev-country"]},
        },
        "physical_mapping": {"physical_join_confirmed": False},
    }]
    out=project_data_model_object(_projection_context(relationships))
    assert out["summary"]["confirmed_storage_join_count"] == 0
    assert out["summary"]["strongly_supported_storage_join_count"] == 1
    assert out["summary"]["executable_storage_join_count"] == 1
