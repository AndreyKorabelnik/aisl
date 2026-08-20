from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from knowledge_control_plane.runtime.publication_bundle import BUNDLE_SCHEMA_VERSION, build_publication_bundle


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_producer_builds_self_contained_publication_bundle(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    execution_root = producer / "outputs" / "knowledge-execution"
    artifact = execution_root / "materializations" / "001-model" / "knowledge-layer.duckdb"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"knowledge")

    external_descriptor = producer / "runtime" / "producer-artifacts" / "core" / "payload" / "core-evidence" / "evidence" / "java-type-structure-evidence.json"
    external_descriptor.parent.mkdir(parents=True)
    external_descriptor.write_text('{"artifact_id":"evidence-1"}\n', encoding="utf-8")

    execution = execution_root / "knowledge_execution_result.json"
    execution.write_text(
        json.dumps({
            "schema_version": "knowledge_execution_result/v2",
            "evidence_artifacts": [{
                "location": {"kind": "file", "path": str(external_descriptor)},
            }],
            "knowledge_artifacts": [{
                "location": {
                    "kind": "knowledge-layer",
                    "output_path": str(artifact.parent),
                    "manifest_path": str(artifact.parent / "manifest.json"),
                }
            }],
        }),
        encoding="utf-8",
    )

    bundle = build_publication_bundle(
        job_id="job-1",
        system_id="ucp",
        display_name="UCP",
        execution_root=execution_root,
        execution_result_path=execution,
        output_path=tmp_path / "out" / "ucp.aisl.zip",
    )

    assert bundle.schema_version == BUNDLE_SCHEMA_VERSION == "aisl_publication_bundle/v2"
    assert bundle.sha256 == _sha(bundle.path)
    with zipfile.ZipFile(bundle.path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("bundle-manifest.json"))
    assert "bundle-manifest.json" in names
    assert "payload/execution/knowledge_execution_result.json" in names
    assert "payload/execution/materializations/001-model/knowledge-layer.duckdb" in names
    external_members = [name for name in names if name.endswith("/java-type-structure-evidence.json")]
    assert len(external_members) == 1
    assert manifest["system"]["system_id"] == "ucp"
    assert manifest["execution_result"]["sha256"] == _sha(execution)
    assert len(manifest["source_mappings"]) == 2
    assert manifest["source_mappings"][0]["source_root"] == str(execution_root.resolve())
    assert any(item["source_root"] == str(external_descriptor.parent.resolve()) for item in manifest["source_mappings"])
    assert bundle.member_count >= 3
