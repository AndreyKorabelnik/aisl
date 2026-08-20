from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from knowledge_api.contract_v1 import KNOWLEDGE_API_PREFIX
from knowledge_api.contract_v1.models import RevisionCreateRequest
from knowledge_api.contract_v1.service import KnowledgeDomainService


def test_system_patch_merges_metadata_and_supports_null_deletion(canonical_client: TestClient) -> None:
    created = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={
            "system_id": "ucp",
            "display_name": "UCP",
            "description": "old",
            "metadata": {"owner": "old", "keep": "yes"},
        },
    )
    assert created.status_code == 201
    updated = canonical_client.patch(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp",
        json={
            "display_name": "Единый профиль клиента",
            "description": None,
            "metadata": {"owner": "customer-data", "obsolete": None},
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["display_name"] == "Единый профиль клиента"
    assert payload["description"] is None
    assert payload["metadata"] == {"keep": "yes", "owner": "customer-data"}


def test_revision_activation_and_system_delete_are_public_contracts(
    canonical_client: TestClient,
    canonical_publication: dict,
    canonical_artifacts: dict,
) -> None:
    assert canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "ucp", "display_name": "UCP"},
    ).status_code == 201
    first_payload = deepcopy(canonical_publication)
    first = canonical_client.post(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=first_payload)
    assert first.status_code == 201
    first_id = first.json()["revision"]["revision_id"]

    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    second_execution = write_execution_result(
        canonical_artifacts["root"],
        [
            KnowledgeArtifactSpec(
                database=canonical_artifacts["knowledge"],
                model_kind="effective-data-model",
                schema_version="effective-data-model/v1",
                materialization_id="effective-data-model",
                capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
            )
        ],
        profile_id="canonical-profile",
        scope_id="ucp",
        execution_token="second",
    )
    second_payload = publication_payload(second_execution)
    second = canonical_client.post(f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions", json=second_payload)
    assert second.status_code == 201
    second_id = second.json()["revision"]["revision_id"]
    assert second_id != first_id

    activated = canonical_client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions/{first_id}/activate"
    )
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"

    deleted = canonical_client.delete(f"{KNOWLEDGE_API_PREFIX}/systems/ucp")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_revision_count"] == 2
    assert canonical_client.get(f"{KNOWLEDGE_API_PREFIX}/systems/ucp").status_code == 404


def test_revision_identity_ignores_uri_and_activation(canonical_publication: dict) -> None:
    first = RevisionCreateRequest.model_validate(canonical_publication)
    second_payload = deepcopy(canonical_publication)
    second_payload["execution_result"]["uri"] = second_payload["execution_result"]["uri"].replace(
        "file://", "file://localhost"
    )
    second_payload["execution_result"]["filename"] = "renamed.json"
    second_payload["activate"] = False
    second = RevisionCreateRequest.model_validate(second_payload)
    fingerprint = "f" * 64
    assert KnowledgeDomainService._revision_id("ucp", first, fingerprint) == KnowledgeDomainService._revision_id(
        "ucp", second, fingerprint
    )
