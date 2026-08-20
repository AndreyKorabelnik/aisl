from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX


def _create_system(client: TestClient, system_id: str = "integration") -> None:
    r = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": system_id, "display_name": system_id, "metadata": {}},
    )
    assert r.status_code == 201, r.text


def test_integration_profile_is_revision_pinned_and_capability_gated(
    canonical_client: TestClient, canonical_publication: dict
) -> None:
    _create_system(canonical_client)
    pub = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/integration/revisions",
        json=canonical_publication,
    )
    assert pub.status_code == 201, pub.text
    revision_id = pub.json()["revision"]["revision_id"]

    response = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/integration/llm-integration-profile",
        params={"revision_id": revision_id, "profile_id": "data-model/v1"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "llm_integration_profile/v1"
    assert payload["scope"] == {
        "system_id": "integration",
        "revision_id": revision_id,
        "revision_binding": "pinned",
    }
    names = {tool["name"] for tool in payload["tools"]}
    assert {"search_data_objects", "get_data_object", "get_analysis_coverage"} <= names
    assert "get_sql_field_calculation" not in names
    assert "get_physical_model_table" not in names
    assert "get_knowledge_context" not in names
    for tool in payload["tools"]:
        assert tool["api_binding"]["operation_id"]
        assert tool["api_binding"]["revision_binding"]["value_from"] == "scope.revision_id"


def test_unknown_integration_profile_is_explicit_404(
    canonical_client: TestClient, canonical_publication: dict
) -> None:
    _create_system(canonical_client, "missing-profile")
    pub = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/missing-profile/revisions",
        json=canonical_publication,
    )
    assert pub.status_code == 201
    response = canonical_client.get(
        f"{KNOWLEDGE_API_PREFIX}/systems/missing-profile/llm-integration-profile",
        params={"profile_id": "missing/v1"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "integration_profile_not_found"
