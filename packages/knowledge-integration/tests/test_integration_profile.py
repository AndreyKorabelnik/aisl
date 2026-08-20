from __future__ import annotations

from knowledge_integration import generate_integration_profile
from knowledge_integration.api_bindings import TOOL_API_BINDINGS
from knowledge_integration.profile_registry import DATA_MODEL_PROFILE_ID, FOREIGN_DATA_PERSISTENCE_PROFILE_ID, SYSTEM_INTERACTIONS_PROFILE_ID
from knowledge_integration.tool_catalog import TOOL_CAPABILITY_REQUIREMENTS, tools_for_capabilities


def _ctx(capabilities):
    return {
        "system_id": "sys",
        "revision_id": "rev-1",
        "capabilities": capabilities,
        "knowledge_artifacts": [{"artifact_id": "a1", "model_kind": "x", "capabilities": capabilities}],
    }


def test_profile_is_deterministic_and_revision_pinned():
    caps = ["common.effective-data-model", "common.physical-model.tables"]
    a = generate_integration_profile(_ctx(caps), profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    b = generate_integration_profile(_ctx(list(reversed(caps))), profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    assert a == b
    assert a["integration_profile"]["fingerprint"] == b["integration_profile"]["fingerprint"]
    assert a["scope"]["revision_id"] == "rev-1"
    assert a["scope"]["revision_binding"] == "pinned"


def test_capability_change_changes_tool_set_and_fingerprint():
    narrow = generate_integration_profile(_ctx(["workspace.system-interactions"]), profile_id=SYSTEM_INTERACTIONS_PROFILE_ID).to_dict()
    wide = generate_integration_profile(_ctx(["workspace.system-interactions", "common.sql-field-calculation"]), profile_id=SYSTEM_INTERACTIONS_PROFILE_ID).to_dict()
    ntools = {t["name"] for t in narrow["tools"]}
    wtools = {t["name"] for t in wide["tools"]}
    assert "get_sql_field_calculation" not in ntools
    assert "get_sql_field_calculation" in wtools
    assert narrow["integration_profile"]["fingerprint"] != wide["integration_profile"]["fingerprint"]


def test_external_tools_are_capability_gated_and_have_http_bindings():
    caps = sorted({c for values in TOOL_CAPABILITY_REQUIREMENTS.values() for c in values})
    profile = generate_integration_profile(_ctx(caps), profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    names = {t["name"] for t in profile["tools"]}
    assert "get_knowledge_context" not in names
    assert names == (tools_for_capabilities(caps) - {"get_knowledge_context"})
    for tool in profile["tools"]:
        binding = tool["api_binding"]
        assert binding["binding_kind"] == "knowledge_api_http"
        assert binding["operation_id"]
        assert binding["path_template"].startswith("/api/knowledge/v1/systems/{system_id}")


def test_all_canonical_tools_have_binding_definition():
    assert set(TOOL_API_BINDINGS) == set(TOOL_CAPABILITY_REQUIREMENTS)


def test_artifact_order_does_not_change_profile_fingerprint():
    caps = ["common.effective-data-model"]
    base = {
        "system_id": "sys",
        "revision_id": "rev-1",
        "capabilities": caps,
        "knowledge_artifacts": [
            {"artifact_id": "b", "model_kind": "b", "content_fingerprint": "2", "capabilities": caps},
            {"artifact_id": "a", "model_kind": "a", "content_fingerprint": "1", "capabilities": caps},
        ],
    }
    rev = {**base, "knowledge_artifacts": list(reversed(base["knowledge_artifacts"]))}
    a = generate_integration_profile(base, profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    b = generate_integration_profile(rev, profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    assert a == b


def test_every_external_tool_argument_has_exactly_one_binding_mapping():
    from knowledge_integration.tool_catalog import TOOL_CATALOG
    for name, definition in TOOL_CATALOG.items():
        binding = TOOL_API_BINDINGS[name]
        if binding.get("binding_kind") != "knowledge_api_http":
            continue
        assert set(definition.get("arguments") or {}) == set(binding.get("arguments") or {}), name


def test_http_request_builder_uses_canonical_binding() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    req = build_knowledge_api_http_request(
        "get_data_object",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={"object_id": "entity/A"},
    )
    assert req.method == "GET"
    assert req.path == "/api/knowledge/v1/systems/sys%2Fa/data-model/tables/entity%2FA"
    assert req.query == {"revision_id": "rev-1"}
    assert req.body is None


def test_http_request_builder_rejects_revision_override() -> None:
    import pytest
    from knowledge_integration.http_request import build_knowledge_api_http_request
    with pytest.raises(ValueError, match="pinned"):
        build_knowledge_api_http_request(
            "get_analysis_coverage",
            system_id="sys",
            revision_id="rev-1",
            arguments={"revision_id": "rev-2"},
        )


def test_attribute_addition_v13_uses_compact_join_guidance() -> None:
    from knowledge_integration.profile_registry import ATTRIBUTE_ADDITION_PROFILE_ID, load_profile

    profile = load_profile(ATTRIBUTE_ADDITION_PROFILE_ID)
    assert profile.version == "13"
    assert "source extraction" in profile.content
    assert "include_fields=false" in profile.content
    assert "Declared relationship" not in profile.content
    assert "declared relationship" in profile.content
    assert "observed SQL" in profile.content
    assert "find_sql_target_candidates" in profile.content
    assert "source_storage_field_observations" in profile.content
    assert "relationship_relevance" in profile.content
    assert "target_key_analog" in profile.content
    assert "usefulness.classification" in profile.content
    assert "collection_storage_navigation" in profile.content
    assert "polymorphic_collection_navigation" in profile.content
    assert "ambiguity" in profile.content
    assert "компакт" in profile.content.lower()
    assert "Не воспроизводи raw tool JSON" in profile.content

    from knowledge_integration import generate_integration_profile
    generated = generate_integration_profile(_ctx(["common.data-model-attribute-extension-context"]), profile_id=ATTRIBUTE_ADDITION_PROFILE_ID).to_dict()
    tool = next(item for item in generated["tools"] if item["name"] == "get_data_model_attribute_extension_context")
    assert tool["api_binding"]["path_template"].endswith("/data-model/attribute-extension-guidance")
    assert "action-oriented" in tool["description"]


def test_declared_model_result_views_are_bounded_and_explicit() -> None:
    from knowledge_integration.result_views import model_result_view

    heavy_annotation = {
        "annotation_occurrence_id": "ann-1",
        "annotation_name": "MetaEntity",
        "arguments_raw": 'name = "Client"',
        "resolution_status": "explicit_import",
        "resolved_annotation_type": "example.MetaEntity",
        "structured_arguments": [{"expression_tree": {"text": "x" * 20000}}],
    }
    fields = [
        {
            "effective_field_occurrence_id": f"ef-{index}",
            "field_occurrence_id": f"f-{index}",
            "declaring_type_occurrence_id": "type-1",
            "name": f"field{index}",
            "declared_type_expression": "String",
            "documentation": {"summary": f"Field {index}"},
            "annotations": [heavy_annotation],
        }
        for index in range(30)
    ]
    raw = {
        "schema_version": "knowledge_assistant_tool_response/v1",
        "request": {
            "schema_version": "knowledge_assistant_tool_request/v1",
            "tool": "search_declared_data_objects",
            "arguments": {"search": "client", "include_fields": True},
        },
        "status": "complete",
        "result": {
            "system_id": "demo",
            "revision_id": "rev-1",
            "filters": {"search": "client", "include_fields": True},
            "page": {"offset": 0, "limit": 1, "total": 2},
            "items": [{
                "object_id": "type-1",
                "repo_id": "repo",
                "fqcn": "example.Client",
                "name": "Client",
                "field_count": 30,
                "relationship_count": 0,
                "retrieval_score": 990,
                "score_basis": "field_name_exact",
                "match_evidence": [{
                    "target_kind": "field",
                    "match_kind": "field_name_exact",
                    "score": 990,
                    "field_occurrence_id": "f-0",
                    "field_name": "field0",
                    "declared_type_expression": "String",
                    "documentation": {"summary": "Field 0"},
                    "evidence_role": "direct_observed_field_match",
                }],
                "binding_summary": {
                    "incoming_relationship_count": 1,
                    "outgoing_relationship_count": 0,
                    "has_observed_incoming_binding": True,
                    "incoming_examples": [{
                        "relationship_id": "r-1",
                        "source_object_id": "owner-1",
                        "source_fqcn": "example.Owner",
                        "source_name": "Owner",
                        "field_occurrence_id": "owner-field",
                        "source_field": "client",
                        "declared_type_expression": "Client",
                        "relationship_kind": "declared_field_type_reference",
                        "resolution_status": "resolved",
                    }],
                    "incoming_examples_truncated": False,
                },
                "annotations": [heavy_annotation],
                "fields": fields,
            }],
        },
        "grounding_reference_ids": ["type-1", *[f"ef-{i}" for i in range(30)]],
        "warnings": [],
    }
    view = model_result_view(raw)
    assert view["view"]["projection"] == "declared_object_discovery_cards"
    assert view["view"]["continuation_available"] is True
    assert view["view"]["source_has_more"] is True
    assert view["view"]["projection_truncated"] is True
    assert view["view"]["field_truncation_present"] is True
    assert view["result"]["items"][0]["object_id"] == "type-1"
    assert view["result"]["items"][0]["retrieval_score"] == 990
    assert view["result"]["items"][0]["match_evidence"][0]["field_name"] == "field0"
    assert view["result"]["items"][0]["binding_summary"]["incoming_examples"][0]["source_field"] == "client"
    assert "fields" not in view["result"]["items"][0]
    assert view["view"]["field_projection"] == "omitted_for_discovery_use_exact_object"
    assert view["view"]["field_truncation_present"] is True
    assert "structured_arguments" not in view["result"]["items"][0]["annotations"][0]


def test_exact_declared_object_view_preserves_all_fields_and_relationships_compactly() -> None:
    from knowledge_integration.result_views import model_result_view

    raw = {
        "schema_version": "knowledge_assistant_tool_response/v1",
        "request": {"tool": "get_declared_data_object", "arguments": {"object_id": "type-1"}},
        "status": "complete",
        "result": {
            "system_id": "demo",
            "revision_id": "rev-1",
            "object": {
                "object_id": "type-1",
                "fqcn": "example.Client",
                "fields": [
                    {
                        "effective_field_occurrence_id": f"ef-{i}",
                        "name": f"field{i}",
                        "declared_type_expression": "String",
                        "annotations": [{
                            "annotation_name": "Demo",
                            "structured_arguments": [{"expression_tree": {"text": "x" * 20000}}],
                        }],
                    }
                    for i in range(52)
                ],
                "relationships": [
                    {"relationship_id": f"rel-{i}", "source_field": f"field{i}", "target_fqcn": "example.Other"}
                    for i in range(41)
                ],
                "inheritance": [{"inheritance_occurrence_id": "inh-1", "resolved_fqcn": "example.Base"}],
            },
        },
        "warnings": [],
    }
    view = model_result_view(raw)
    assert view["view"]["projection"] == "declared_object_complete_compact_structure"
    assert view["view"]["fields_source_total"] == view["view"]["fields_presented"] == 52
    assert view["view"]["relationships_source_total"] == view["view"]["relationships_presented"] == 41
    assert view["view"]["fields_truncated"] is False
    assert view["view"]["relationships_truncated"] is False
    assert len(view["result"]["object"]["fields"]) == 52
    assert "structured_arguments" not in view["result"]["object"]["fields"][0]["annotations"][0]


def test_declared_search_batch_view_deduplicates_and_preserves_query_provenance() -> None:
    from knowledge_integration.result_views import batch_model_result_view, model_result_view

    def raw(query: str, items: list[tuple[str, int]]):
        return {
            "schema_version": "knowledge_assistant_tool_response/v1",
            "request": {"tool": "search_declared_data_objects", "arguments": {"search": query, "limit": 5}},
            "status": "complete",
            "result": {
                "page": {"offset": 0, "limit": 5, "total": len(items)},
                "items": [
                    {
                        "object_id": value,
                        "fqcn": f"example.{value}",
                        "retrieval_score": score,
                        "score_basis": "field_name_exact" if score >= 900 else "substring",
                        "match_evidence": [{
                            "target_kind": "field", "match_kind": "field_name_exact", "score": score,
                            "field_occurrence_id": f"f-{query}-{value}", "field_name": query,
                            "evidence_role": "direct_observed_field_match",
                        }],
                    }
                    for value, score in items
                ],
            },
            "warnings": [],
        }

    merged = batch_model_result_view([
        model_result_view(raw("consent", [("Consent", 1000), ("Channel", 700)])),
        model_result_view(raw("channel", [("Channel", 990), ("Preference", 800)])),
    ])
    assert merged["view"]["projection"] == "declared_object_discovery_batch_merge"
    assert merged["view"]["source_call_count"] == 2
    assert merged["view"]["items_presented_unique"] == 3
    assert [item["object_id"] for item in merged["result"]["items"]] == ["Consent", "Channel", "Preference"]
    items = {item["object_id"]: item for item in merged["result"]["items"]}
    assert items["Channel"]["retrieval_score"] == 990
    assert items["Channel"]["matched_queries"] == ["consent", "channel"]
    assert len(items["Channel"]["match_evidence"]) == 2
    assert items["Channel"]["matched_searches"] == [
        {"search": "consent", "task_ref": None},
        {"search": "channel", "task_ref": None},
    ]
    assert merged["calls"][0]["search"] == "consent"


def test_universal_knowledge_item_tool_is_base_revision_pinned_read() -> None:
    from knowledge_integration import generate_integration_profile
    profile = generate_integration_profile(_ctx([]), profile_id=DATA_MODEL_PROFILE_ID).to_dict()
    tools = {tool["name"]: tool for tool in profile["tools"]}
    assert "get_knowledge_item" in tools
    tool = tools["get_knowledge_item"]
    assert tool["required_capabilities"] == []
    assert set(tool["arguments"]) == {"artifact_id", "item_kind", "local_id"}
    assert "semantic search" in tool["description"]
    assert tool["api_binding"]["path_template"].endswith(
        "/knowledge-items/{artifact_id}/{item_kind}/{local_id}"
    )


def test_universal_knowledge_item_request_uses_pinned_revision_and_exact_path() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    req = build_knowledge_api_http_request(
        "get_knowledge_item",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={
            "artifact_id": "artifact/code model",
            "item_kind": "declared_field",
            "local_id": "field/x",
        },
    )
    assert req.method == "GET"
    assert req.path == (
        "/api/knowledge/v1/systems/sys%2Fa/knowledge-items/"
        "artifact%2Fcode%20model/declared_field/field%2Fx"
    )
    assert req.query == {"revision_id": "rev-1"}
    assert req.body is None


def test_universal_knowledge_item_warning_preserves_unknown_state() -> None:
    from knowledge_integration.tool_catalog import tool_warnings
    warnings = tool_warnings("get_knowledge_item", {})
    assert warnings
    assert "must not be interpreted" in warnings[0]


def test_system_interactions_v2_prefers_compact_exact_context() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    from knowledge_integration.profile_registry import load_profile

    profile = load_profile(SYSTEM_INTERACTIONS_PROFILE_ID)
    assert profile.version == "2"
    assert "get_system_interaction_context" in profile.content
    assert "предпочтительный compact read" in profile.content
    assert profile.content.index("get_system_interaction_context") < profile.content.index("list_interaction_boundaries")

    generated = generate_integration_profile(
        _ctx(["workspace.system-interactions"]),
        profile_id=SYSTEM_INTERACTIONS_PROFILE_ID,
    ).to_dict()
    tools = {item["name"]: item for item in generated["tools"]}
    tool = tools["get_system_interaction_context"]
    assert tool["arguments"] == {"interaction_id": "string"}
    binding = tool["api_binding"]
    assert binding["path_template"].endswith("/interactions/{interaction_id}/guidance")
    assert binding["fixed_query"] == {"context_limit": 8, "field_limit": 20}

    request = build_knowledge_api_http_request(
        "get_system_interaction_context",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={"interaction_id": "interaction/A"},
    )
    assert request.method == "GET"
    assert request.path == "/api/knowledge/v1/systems/sys%2Fa/interactions/interaction%2FA/guidance"
    assert request.query == {"revision_id": "rev-1", "context_limit": 8, "field_limit": 20}
    assert request.body is None


def test_system_description_v2_prefers_compact_context() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    from knowledge_integration.profile_registry import SYSTEM_DESCRIPTION_PROFILE_ID, load_profile

    profile = load_profile(SYSTEM_DESCRIPTION_PROFILE_ID)
    assert profile.version == "2"
    assert "get_system_description_context" in profile.content
    assert "preferred compact read" in profile.content
    assert profile.content.index("get_system_description_context") < profile.content.index("get_system_repository_composition")
    assert "Do not reproduce raw tool JSON" in profile.content

    generated = generate_integration_profile(
        _ctx(["common.system-description"]),
        profile_id=SYSTEM_DESCRIPTION_PROFILE_ID,
    ).to_dict()
    tools = {item["name"]: item for item in generated["tools"]}
    tool = tools["get_system_description_context"]
    assert tool["arguments"] == {}
    binding = tool["api_binding"]
    assert binding["path_template"].endswith("/system-description/guidance")
    assert binding["fixed_query"] == {
        "technology_limit": 12,
        "interface_limit": 12,
        "integration_limit": 8,
        "event_limit": 8,
        "storage_limit": 10,
        "journey_limit": 8,
        "gap_limit": 20,
    }

    request = build_knowledge_api_http_request(
        "get_system_description_context",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={},
    )
    assert request.method == "GET"
    assert request.path == "/api/knowledge/v1/systems/sys%2Fa/system-description/guidance"
    assert request.query == {
        "revision_id": "rev-1",
        "technology_limit": 12,
        "interface_limit": 12,
        "integration_limit": 8,
        "event_limit": 8,
        "storage_limit": 10,
        "journey_limit": 8,
        "gap_limit": 20,
    }
    assert request.body is None


def test_foreign_data_persistence_v2_prefers_compact_context() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    from knowledge_integration.profile_registry import load_profile

    profile = load_profile(FOREIGN_DATA_PERSISTENCE_PROFILE_ID)
    assert profile.version == "2"
    assert "get_fdp_context" in profile.content
    assert "preferred compact read" in profile.content
    assert profile.content.index("get_fdp_context") < profile.content.index("list_fdp_paths")
    assert "raw tool JSON" in profile.content

    generated = generate_integration_profile(
        _ctx(["workspace.fdp-paths"]),
        profile_id=FOREIGN_DATA_PERSISTENCE_PROFILE_ID,
    ).to_dict()
    tools = {item["name"]: item for item in generated["tools"]}
    tool = tools["get_fdp_context"]
    assert tool["arguments"] == {"token": "string|null"}
    binding = tool["api_binding"]
    assert binding["path_template"].endswith("/foreign-data-persistence/guidance")
    assert binding["fixed_query"] == {
        "path_limit": 12,
        "case_limit": 12,
        "storage_summary_limit": 12,
        "evidence_limit": 40,
    }

    request = build_knowledge_api_http_request(
        "get_fdp_context",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={"token": "DEVICE_LINK"},
    )
    assert request.method == "GET"
    assert request.path == "/api/knowledge/v1/systems/sys%2Fa/foreign-data-persistence/guidance"
    assert request.query == {
        "revision_id": "rev-1",
        "token": "DEVICE_LINK",
        "path_limit": 12,
        "case_limit": 12,
        "storage_summary_limit": 12,
        "evidence_limit": 40,
    }
    assert request.body is None



def test_reference_data_v2_prefers_compact_context() -> None:
    from knowledge_integration.http_request import build_knowledge_api_http_request
    from knowledge_integration.profile_registry import REFERENCE_DATA_PROFILE_ID, load_profile

    profile = load_profile(REFERENCE_DATA_PROFILE_ID)
    assert profile.version == "2"
    assert "get_reference_data_context" in profile.content
    assert "preferred compact read" in profile.content
    assert profile.content.index("get_reference_data_context") < profile.content.index("get_reference_data_landscape")
    assert "Не воспроизводи raw tool JSON" in profile.content

    generated = generate_integration_profile(
        _ctx(["common.reference-data"]),
        profile_id=REFERENCE_DATA_PROFILE_ID,
    ).to_dict()
    tools = {item["name"]: item for item in generated["tools"]}
    tool = tools["get_reference_data_context"]
    assert tool["arguments"] == {"token": "string|null"}
    binding = tool["api_binding"]
    assert binding["path_template"].endswith("/reference-data/guidance")
    assert binding["fixed_query"] == {
        "candidate_limit": 200,
        "local_definition_limit": 12,
        "literal_write_limit": 12,
        "usage_limit": 16,
        "gap_limit": 12,
        "evidence_limit": 40,
    }

    request = build_knowledge_api_http_request(
        "get_reference_data_context",
        system_id="sys/a",
        revision_id="rev-1",
        arguments={"token": "operatorId"},
    )
    assert request.method == "GET"
    assert request.path == "/api/knowledge/v1/systems/sys%2Fa/reference-data/guidance"
    assert request.query == {
        "revision_id": "rev-1",
        "token": "operatorId",
        "candidate_limit": 200,
        "local_definition_limit": 12,
        "literal_write_limit": 12,
        "usage_limit": 16,
        "gap_limit": 12,
        "evidence_limit": 40,
    }
    assert request.body is None


def test_data_model_profile_exposes_object_context_tool_from_declared_model_capability() -> None:
    profile = generate_integration_profile(
        _ctx(["common.code-declared-data-model"]),
        profile_id=DATA_MODEL_PROFILE_ID,
    ).to_dict()
    tools = {item["name"]: item for item in profile["tools"]}
    assert "get_data_model_object_context" in tools
    binding = tools["get_data_model_object_context"]["api_binding"]
    assert binding["path_template"].endswith("/data-model/object-context/{object_id}")
    assert binding["expected_schema_versions"] == ["data_model_object_context/v2"]
