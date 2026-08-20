from pathlib import Path

import pytest

from prepared_knowledge_runtime import KnowledgeLayerContractError, KnowledgeLayerManifest, derive_scope_type

def test_scope_type_is_derived_from_repository_count():
    assert derive_scope_type(1) == "repository"
    assert derive_scope_type(2) == "workspace"

def test_zero_repository_scope_fails_closed():
    with pytest.raises(KnowledgeLayerContractError):
        derive_scope_type(0)

def test_complete_manifest_requires_complete_validation():
    with pytest.raises(KnowledgeLayerContractError):
        KnowledgeLayerManifest(
            scope_id="at900", repository_ids=("at900",), modes=("data-model",),
            producer_version="0.1.0", build_id="b1", build_status="complete",
        )

def test_manifest_round_trip_for_repository_scope():
    manifest = KnowledgeLayerManifest(
        scope_id="at900", repository_ids=("at900",), modes=("data-model",),
        producer_version="0.1.0", build_id="b1", build_status="complete",
        validation_status="complete", counts={"entities": 10}, materialized_marts=("effective-model",),
    )
    restored = KnowledgeLayerManifest.from_dict(manifest.to_dict())
    assert restored == manifest
    assert restored.scope_type == "repository"

def test_manifest_round_trip_for_workspace_scope():
    manifest = KnowledgeLayerManifest(
        scope_id="ucp", repository_ids=("ucp-api", "ucp-tsa-v4"), modes=("data-model",),
        producer_version="0.1.0", build_id="b2", build_status="pending",
    )
    restored = KnowledgeLayerManifest.from_dict(manifest.to_dict())
    assert restored.scope_type == "workspace"
    assert restored.repository_count == 2
