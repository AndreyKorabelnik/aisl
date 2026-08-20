from pathlib import Path

from prepared_knowledge_runtime import KnowledgeLayerManifest, load_manifest, write_manifest

def test_manifest_file_round_trip(tmp_path: Path):
    manifest = KnowledgeLayerManifest(
        scope_id="at900", repository_ids=("at900",), modes=("data-model",),
        producer_version="0.1.0", build_id="build", build_status="complete",
        validation_status="complete",
    )
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    assert load_manifest(path) == manifest
