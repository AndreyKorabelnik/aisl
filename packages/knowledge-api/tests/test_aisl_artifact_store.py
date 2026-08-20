from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_api.artifact_store import AislArtifactStore
from knowledge_api.contract_v1.models import PublishedArtifact
from knowledge_api.contract_v1.runtime import KnowledgeApiRuntimeError, KnowledgeApiSettings, ArtifactValidator, sha256_file


def _descriptor(path: Path) -> PublishedArtifact:
    return PublishedArtifact(
        uri=path.as_uri(),
        sha256=sha256_file(path),
        media_type="application/json",
        schema_version="pilot/v1",
        byte_size=path.stat().st_size,
        filename=path.name,
    )


def test_content_addressed_import_is_deduplicated_and_filename_is_not_identity(tmp_path: Path) -> None:
    source_a = tmp_path / "producer-a" / "evidence.json"
    source_b = tmp_path / "producer-b" / "same-content.json"
    source_a.parent.mkdir(); source_b.parent.mkdir()
    source_a.write_bytes(b'{"x":1}\n'); source_b.write_bytes(source_a.read_bytes())
    store = AislArtifactStore(tmp_path / "aisl-store")

    first = store.import_artifact(_descriptor(source_a), source_a)
    second = store.import_artifact(_descriptor(source_b), source_b)

    first_path = store.path_for_digest(first.sha256)
    second_path = store.path_for_digest(second.sha256)
    assert first.sha256 == second.sha256
    assert first.uri == f"aisl+sha256://{first.sha256}"
    assert second.uri == first.uri
    assert first_path == second_path
    assert first_path.name == "blob"
    assert first_path.read_bytes() == source_a.read_bytes()
    assert first.filename == "evidence.json"
    assert second.filename == "same-content.json"


def test_existing_corrupt_blob_is_rejected_instead_of_silently_reused(tmp_path: Path) -> None:
    source = tmp_path / "producer" / "evidence.json"
    source.parent.mkdir(); source.write_bytes(b'{"x":1}\n')
    descriptor = _descriptor(source)
    store = AislArtifactStore(tmp_path / "aisl-store")
    imported = store.import_artifact(descriptor, source)
    target = store.path_for_digest(imported.sha256)
    target.chmod(0o644)
    target.write_bytes(b"corrupt")

    with pytest.raises(KnowledgeApiRuntimeError) as exc:
        store.import_artifact(descriptor, source)
    assert exc.value.code == "aisl_artifact_store_corrupt"


def test_logical_locator_digest_must_match_artifact_identity(tmp_path: Path) -> None:
    source = tmp_path / "producer" / "evidence.json"
    source.parent.mkdir(); source.write_bytes(b'{"x":1}\n')
    store = AislArtifactStore(tmp_path / "aisl-store")
    imported = store.import_artifact(_descriptor(source), source)
    validator = ArtifactValidator(KnowledgeApiSettings(database_path=tmp_path / "catalog.sqlite3", allowed_roots=(tmp_path / "producer",), artifact_store_path=store.root))
    mismatched = imported.model_copy(update={"uri": f"aisl+sha256://{'0' * 64}"})
    with pytest.raises(KnowledgeApiRuntimeError) as exc:
        validator.validate(mismatched)
    assert exc.value.code == "artifact_locator_digest_mismatch"
