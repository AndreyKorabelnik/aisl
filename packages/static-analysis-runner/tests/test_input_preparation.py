from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from static_analysis_runner.cli import app
from static_analysis_runner.knowledge_execution_planning import _fingerprint
from static_analysis_runner.input_preparation import (
    knowledge_artifacts_from_published_revision,
    prepare_knowledge_input_inventory,
)


def _catalogs() -> tuple[dict, dict]:
    core = {
        "schema_version": "core_evidence_contract_catalog/v1",
        "core_version": "0.44.20",
        "artifact_envelope_contract": "core_evidence_artifact_contract/v1",
        "contracts": [],
    }
    core["catalog_fingerprint"] = _fingerprint(core)
    klc = {
        "schema_version": "knowledge_materialization_catalog/v3",
        "klc_version": "0.59.47",
        "runtime_contract": {"contract_id": "knowledge_materialization_runtime/v1"},
        "materializations": [],
    }
    klc["catalog_fingerprint"] = _fingerprint(klc)
    return core, klc


def test_published_revision_is_normalized_without_product_selection(tmp_path: Path) -> None:
    manifest_a = tmp_path / "a" / "manifest.json"
    manifest_b = tmp_path / "b" / "manifest.json"
    manifest_a.parent.mkdir(); manifest_b.parent.mkdir()
    manifest_a.write_text("{}\n", encoding="utf-8")
    manifest_b.write_text("{}\n", encoding="utf-8")
    revision = {
        "system_id": "repo-a",
        "revision_id": "rev-1",
        "knowledge_artifacts": [
            {
                "artifact_id": "a",
                "model_kind": "knowledge_a/v1",
                "schema_version": "knowledge_a/v1",
                "source_materialization_id": "mat-a",
                "content_fingerprint": "fp-a",
                "capabilities": ["cap.a"],
                "manifest": {"uri": manifest_a.as_uri()},
            },
            {
                "artifact_id": "b",
                "model_kind": "knowledge_b/v1",
                "schema_version": "knowledge_b/v1",
                "source_materialization_id": "mat-b",
                "content_fingerprint": "fp-b",
                "capabilities": ["cap.b"],
                "manifest": {"uri": manifest_b.as_uri()},
            },
        ],
    }
    result = knowledge_artifacts_from_published_revision(revision)
    assert [item["artifact_id"] for item in result] == ["a", "b"]
    assert result[0]["location"]["kind"] == "knowledge-layer"
    assert result[0]["provenance"]["source_revision_id"] == "rev-1"


def test_prepare_inventory_owns_physical_model_core_invocation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "A.java").write_text("class A {}\n", encoding="utf-8")
    pdm = tmp_path / "model.pdm"
    pdm.write_text("<Model/>\n", encoding="utf-8")
    core = tmp_path / "fake-core"
    core.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args=sys.argv[1:]\n"
        "out=pathlib.Path(args[args.index('--artifact-output')+1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out/'manifest.json').write_text(json.dumps({'schema_version':'physical-model/v1','content_fingerprint':'abc123'})+'\\n')\n",
        encoding="utf-8",
    )
    core.chmod(0o755)
    core_catalog, klc_catalog = _catalogs()
    inventory = prepare_knowledge_input_inventory(
        scope_kind="workspace",
        scope_id="system-a",
        repositories=[repo],
        core_evidence_catalog=core_catalog,
        materialization_catalog=klc_catalog,
        preparation_root=tmp_path / "inputs",
        physical_model_path=pdm,
        core_command=str(core),
    )
    assert inventory["summary"]["source_snapshot_count"] == 1
    assert inventory["summary"]["available_typed_artifact_count"] == 1
    artifact = inventory["typed_artifacts"][0]
    assert artifact["artifact_kind"] == "physical-model"
    assert artifact["schema_version"] == "physical-model/v1"
    assert artifact["producer_kind"] == "core_external_input_preparation"


def test_cli_exposes_control_plane_input_preparation() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "knowledge-input-prepare" in result.stdout


def test_prepare_inventory_preserves_authoritative_repository_source_metadata(tmp_path: Path) -> None:
    repo = tmp_path / "profile-api"
    repo.mkdir()
    (repo / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    core_catalog, klc_catalog = _catalogs()
    inventory = prepare_knowledge_input_inventory(
        scope_kind="repository",
        scope_id="profile-api",
        repositories=[repo],
        core_evidence_catalog=core_catalog,
        materialization_catalog=klc_catalog,
        preparation_root=tmp_path / "inputs",
        repository_metadata_by_source_id={
            "profile-api": {
                "repository_id": "registry-profile-api",
                "repository_name": "Profile API",
                "source_kind": "bitbucket",
                "repository_url": "https://bitbucket.example/scm/team/profile-api.git",
                "default_branch": "main",
            }
        },
    )
    snapshot = inventory["source_snapshots"][0]
    assert snapshot["source_metadata"]["repository_url"] == "https://bitbucket.example/scm/team/profile-api.git"
    assert snapshot["source_metadata"]["source_kind"] == "bitbucket"
