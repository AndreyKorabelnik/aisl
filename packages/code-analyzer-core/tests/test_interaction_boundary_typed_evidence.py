from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import code_analyzer_core.prepared_artifacts.interaction_boundary_evidence as boundary
from code_analyzer_core.evidence_runtime import registered_evidence_analyzers


def test_interaction_boundary_analyzer_publishes_http_catalog(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repo"
    source = repository / "src/main/java/demo/Client.java"
    source.parent.mkdir(parents=True)
    source.write_text("package demo; class Client {}", encoding="utf-8")

    def fake_run(repository: Path, output: Path, **kwargs):
        compact = output / "compact"
        compact.mkdir(parents=True)
        (compact / "system_interface_catalog.json").write_text(
            json.dumps({"all_interfaces": [
                {"interface_id": "in", "direction": "inbound", "boundary_kind": "rest_request", "protocol": "http"},
                {"interface_id": "out", "direction": "outbound", "boundary_kind": "http_outbound", "protocol": "http"},
                {"interface_id": "response", "direction": "outbound", "boundary_kind": "rest_response", "protocol": "rest"},
            ]}), encoding="utf-8"
        )
        assert kwargs["analysis_profile"]["profile_id"] == "internal-interaction-boundary-evidence-v1"
        return SimpleNamespace(coverage={})

    monkeypatch.setattr(boundary, "run_analysis", fake_run)
    artifact = boundary.build_interaction_boundary_evidence(
        repository=repository,
        files=[source],
        repo_id="source-app",
        output_root=tmp_path / "out",
        parameters={"system_id": "source", "project_id": "p1", "service_aliases": ["source-service"]},
    )

    assert artifact["artifact_kind"] == "interaction-boundary-evidence"
    assert artifact["schema_version"] == "interaction-boundary-evidence/v1"
    assert artifact["coverage"]["boundary_count"] == 2
    assert artifact["coverage"]["inbound_boundary_count"] == 1
    assert artifact["coverage"]["outbound_boundary_count"] == 1
    descriptor = artifact["payload"]["boundary_catalog"]
    assert descriptor["artifact_name"] == "interaction_boundary_catalog.json"
    assert descriptor["section"] == "boundaries"
    catalog = json.loads((tmp_path / "out" / "evidence" / descriptor["relative_path"]).read_text(encoding="utf-8"))
    assert [item["interface_id"] for item in catalog["boundaries"]] == ["in", "out"]
    assert artifact["payload"]["repository_identity"]["service_aliases"] == ["source-service"]
    assert "task_suite_profile_semantics" not in artifact["provenance"]


def test_interaction_boundary_analyzer_is_registered() -> None:
    identities = {(item.artifact_kind, item.schema_version) for item in registered_evidence_analyzers()}
    assert ("interaction-boundary-evidence", "interaction-boundary-evidence/v1") in identities
