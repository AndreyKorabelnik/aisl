from __future__ import annotations

import json
import zipfile
from pathlib import Path

from knowledge_api.contract_v1.runtime import KnowledgeApiRuntimeError, KnowledgeApiSettings, sha256_file
from knowledge_api.publication import stable_fingerprint
from knowledge_api.publication_bundle import import_publication_bundle
from tests.execution_fixtures import KnowledgeArtifactSpec, write_execution_result


def _build_transport_bundle(source_roots: list[Path], execution_result: Path, target: Path) -> Path:
    mappings = []
    members = []
    archived: list[tuple[Path, str]] = []
    for index, source_root in enumerate(source_roots):
        source_root = source_root.resolve()
        prefix = "payload/execution" if index == 0 else f"payload/external/{index:03d}"
        mappings.append({"source_root": str(source_root), "payload_prefix": prefix, "role": "execution" if index == 0 else "publication-artifact-package"})
        for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
            rel = path.relative_to(source_root).as_posix()
            archive_path = f"{prefix}/{rel}"
            members.append({
                "path": archive_path,
                "source_path": str(path.resolve()),
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
            })
            archived.append((path, archive_path))
    execution_path = f"payload/execution/{execution_result.relative_to(source_roots[0]).as_posix()}"
    manifest = {
        "schema_version": "aisl_publication_bundle/v2",
        "created_at": "2026-08-18T12:00:00+00:00",
        "producer": {"component": "knowledge-control-plane", "version": "test"},
        "job_id": "job-test",
        "system": {"system_id": "ucp", "display_name": "UCP"},
        "source_mappings": mappings,
        "execution_result": {
            "path": execution_path,
            "source_path": str(execution_result.resolve()),
            "sha256": sha256_file(execution_result),
            "schema_version": "knowledge_execution_result/v2",
        },
        "publication_defaults": {"activate": True, "labels": ["automated-analysis"], "metadata": {}},
        "members": members,
    }
    manifest["bundle_fingerprint"] = stable_fingerprint(manifest)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bundle-manifest.json", json.dumps(manifest, sort_keys=True))
        for path, archive_path in archived:
            archive.write(path, archive_path)
    return target


def _settings(tmp_path: Path) -> KnowledgeApiSettings:
    return KnowledgeApiSettings(
        database_path=tmp_path / "server" / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path / "server-only",),
        artifact_store_path=tmp_path / "server" / "artifact-store",
    )


def test_server_imports_bundle_without_producer_allowed_root(tmp_path: Path) -> None:
    producer_root = tmp_path / "producer-output" / "knowledge-execution"
    database = producer_root / "materializations" / "001-code-model" / "knowledge-layer.duckdb"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"portable-knowledge")
    (producer_root / "materialization-runtime.stdout.log").write_bytes(b"")
    execution = write_execution_result(
        producer_root,
        [KnowledgeArtifactSpec(
            database=database,
            model_kind="code-declared-data-model",
            schema_version="code-declared-data-model/v1",
            materialization_id="code-declared-data-model",
            capabilities=("common.code-declared-data-model",),
        )],
        scope_id="ucp",
    )
    bundle = _build_transport_bundle([producer_root], execution, tmp_path / "ucp.aisl.zip")

    result = import_publication_bundle(settings=_settings(tmp_path), bundle_path=bundle)

    assert result["status"] == "published"
    assert result["system_id"] == "ucp"
    assert result["revision_id"].startswith("rev-")
    assert result["active"] is True
    blobs = list((tmp_path / "server" / "artifact-store" / "sha256").rglob("blob"))
    assert blobs
    assert all(producer_root not in path.parents for path in blobs)


def test_server_imports_external_core_evidence_from_bundle_mapping(tmp_path: Path) -> None:
    execution_root = tmp_path / "producer" / "outputs" / "knowledge-execution"
    database = execution_root / "materializations" / "001-code-model" / "knowledge-layer.duckdb"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"portable-knowledge")
    execution = write_execution_result(
        execution_root,
        [KnowledgeArtifactSpec(
            database=database,
            model_kind="code-declared-data-model",
            schema_version="code-declared-data-model/v1",
            materialization_id="code-declared-data-model",
            capabilities=("common.code-declared-data-model",),
        )],
        scope_id="ucp",
    )

    evidence_root = tmp_path / "producer" / "runtime" / "control-plane" / "producer-artifacts" / "core-evidence" / "payload" / "core-evidence" / "evidence"
    evidence_root.mkdir(parents=True)
    descriptor = evidence_root / "java-type-structure-evidence.json"
    evidence_id = "core_evidence_test"
    content_fp = "a" * 64
    descriptor_payload = {
        "artifact_id": evidence_id,
        "artifact_kind": "java-type-structure-evidence",
        "schema_version": "java-type-structure-evidence/v1",
        "content_fingerprint": content_fp,
        "source_snapshot": {"source_id": "ucp-api"},
    }
    descriptor.write_text(json.dumps(descriptor_payload, sort_keys=True), encoding="utf-8")

    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["evidence_artifacts"] = [{
        "artifact_id": evidence_id,
        "artifact_kind": "java-type-structure-evidence",
        "schema_version": "java-type-structure-evidence/v1",
        "content_fingerprint": content_fp,
        "status": "completed",
        "contract_version": "core_evidence_artifact_contract/v1",
        "location": {
            "kind": "file",
            "path": str(descriptor.resolve()),
            "sha256": sha256_file(descriptor),
            "bytes": descriptor.stat().st_size,
        },
        "provenance": {"source_snapshot": {"source_id": "ucp-api"}},
    }]
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    bundle = _build_transport_bundle([execution_root, evidence_root], execution, tmp_path / "ucp-with-evidence.aisl.zip")
    result = import_publication_bundle(settings=_settings(tmp_path), bundle_path=bundle)

    assert result["status"] == "published"
    assert result["system_id"] == "ucp"
    assert result["revision_id"].startswith("rev-")
    # The producer path is not allowed and does not exist under server storage;
    # imported bytes are owned by the server CAS.
    blobs = list((tmp_path / "server" / "artifact-store" / "sha256").rglob("blob"))
    assert len(blobs) >= 3


def test_server_rejects_tampered_bundle_member(tmp_path: Path) -> None:
    producer_root = tmp_path / "producer" / "knowledge-execution"
    database = producer_root / "materializations" / "001-code-model" / "knowledge-layer.duckdb"
    database.parent.mkdir(parents=True)
    database.write_bytes(b"knowledge")
    execution = write_execution_result(
        producer_root,
        [KnowledgeArtifactSpec(
            database=database,
            model_kind="code-declared-data-model",
            schema_version="code-declared-data-model/v1",
            materialization_id="code-declared-data-model",
            capabilities=("common.code-declared-data-model",),
        )],
    )
    original = _build_transport_bundle([producer_root], execution, tmp_path / "original.aisl.zip")
    tampered = tmp_path / "tampered.aisl.zip"
    with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(tampered, "w") as out:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("knowledge-layer.duckdb"):
                data += b"tamper"
            out.writestr(info, data)

    try:
        import_publication_bundle(settings=_settings(tmp_path), bundle_path=tampered)
    except KnowledgeApiRuntimeError as exc:
        assert exc.code == "publication_bundle_member_identity_invalid"
    else:
        raise AssertionError("tampered bundle must be rejected")
