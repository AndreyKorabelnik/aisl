from pathlib import Path

from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService


def _artifact(artifact_id: str, source: str, sha: str, *, cross: bool = False):
    caps = ["workspace.attribute-path-resolver", "workspace.repository-value-flow"]
    if cross:
        caps.append("workspace.cross-repository-value-flow")
    return {
        "artifact_id": artifact_id,
        "source_materialization_id": source,
        "database": {"sha256": sha},
        "capabilities": caps,
    }


def test_value_flow_selector_prefers_enriched_artifact(tmp_path: Path) -> None:
    service = KnowledgeDomainService(KnowledgeApiSettings(database_path=tmp_path / "api.sqlite", allowed_roots=(tmp_path,)))
    revision = {"knowledge_artifacts": [
        _artifact("local", "repository-value-flow", "a" * 64),
        _artifact("cross", "cross-repository-value-flow", "b" * 64, cross=True),
    ]}
    selected = service._value_flow_artifact_record(revision)
    assert selected["artifact_id"] == "cross"
    assert selected["source_materialization_id"] == "cross-repository-value-flow"


def test_value_flow_selector_uses_local_when_enriched_is_absent(tmp_path: Path) -> None:
    service = KnowledgeDomainService(KnowledgeApiSettings(database_path=tmp_path / "api.sqlite", allowed_roots=(tmp_path,)))
    revision = {"knowledge_artifacts": [_artifact("local", "repository-value-flow", "a" * 64)]}
    selected = service._value_flow_artifact_record(revision)
    assert selected["artifact_id"] == "local"
