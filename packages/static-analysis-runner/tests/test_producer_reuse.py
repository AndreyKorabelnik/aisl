from __future__ import annotations

import hashlib
import json
from pathlib import Path

from static_analysis_runner.input_preparation import prepare_physical_model_artifact
from static_analysis_runner.producer_reuse import ProducerArtifactStore
from static_analysis_runner.runtime_support import validate_core_version


def _write_executable(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def _physical_core(path: Path, *, analyze_exit: int = 0, version: str = "0.44.23a3") -> Path:
    return _write_executable(
        path,
        f'''#!/usr/bin/env python3
import hashlib, json, pathlib, sys
args=sys.argv[1:]
if args == ['version']:
    print('code-analyzer-core {version}')
    raise SystemExit(0)
if not args or args[0] != 'analyze-physical-model':
    raise SystemExit(2)
if {analyze_exit}:
    raise SystemExit({analyze_exit})
source=pathlib.Path(args[1])
out=pathlib.Path(args[args.index('--artifact-output')+1])
source_id=args[args.index('--source-id')+1]
out.mkdir(parents=True, exist_ok=True)
sha=hashlib.sha256(source.read_bytes()).hexdigest()
(out/'metadata.json').write_text(json.dumps({{'source_id':source_id}})+'\\n', encoding='utf-8')
manifest={{
  'schema_version':'physical-model/v1',
  'core_version':'{version}',
  'physical_model_source_id':source_id,
  'source':{{'file':source.name,'sha256':sha,'metadata_path':'metadata.json'}},
  'facts':[],
  'content_fingerprint':hashlib.sha256((sha+'|'+source_id).encode()).hexdigest(),
}}
(out/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\\n', encoding='utf-8')
''',
    )


def test_reuse_key_is_deterministic_and_semantic_material_changes_it(tmp_path: Path) -> None:
    store = ProducerArtifactStore(tmp_path / "cache")
    material = {
        "producer": {"id": "core:a", "version": "1.2.3a4"},
        "input": {"fingerprint": "abc"},
        "output_contract": {"fingerprint": "contract-a"},
        "semantic_parameters": {"mode": "x"},
    }
    first = store.reuse_key(material)
    second = store.reuse_key(dict(reversed(list(material.items()))))
    assert first == second
    changed_input = {**material, "input": {"fingerprint": "def"}}
    changed_version = {**material, "producer": {"id": "core:a", "version": "1.2.3a5"}}
    changed_parameter = {**material, "semantic_parameters": {"mode": "y"}}
    assert store.reuse_key(changed_input) != first
    assert store.reuse_key(changed_version) != first
    assert store.reuse_key(changed_parameter) != first


def test_validate_core_version_preserves_prerelease_identity(tmp_path: Path) -> None:
    core = _write_executable(
        tmp_path / "core",
        "#!/usr/bin/env python3\nprint('code-analyzer-core 0.44.23a3')\n",
    )
    assert validate_core_version(core_command=str(core), log_path=tmp_path / "version.log") == "0.44.23a3"


def test_physical_model_reuse_and_force_rebuild_are_real(tmp_path: Path) -> None:
    model = tmp_path / "model.pdm"
    model.write_text("<Model id='x'/>\n", encoding="utf-8")
    core = _physical_core(tmp_path / "core")
    cache = tmp_path / "cache"

    first_decisions: list[dict] = []
    first = prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-1",
        core_command=str(core),
        producer_cache_root=cache,
        reuse_decisions=first_decisions,
    )
    assert first_decisions[0]["action"] == "built"
    assert first_decisions[0]["invalidation_reason"] == "cache_miss"

    # Same producer version remains callable for key validation, but analysis itself must not execute.
    _physical_core(core, analyze_exit=97)
    second_decisions: list[dict] = []
    second = prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-2",
        core_command=str(core),
        producer_cache_root=cache,
        reuse_decisions=second_decisions,
    )
    assert second_decisions[0]["action"] == "reused"
    assert first["content_fingerprint"] == second["content_fingerprint"]

    _physical_core(core)
    forced_decisions: list[dict] = []
    forced = prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-3",
        core_command=str(core),
        producer_cache_root=cache,
        force_rebuild=True,
        reuse_decisions=forced_decisions,
    )
    assert forced_decisions[0]["action"] == "built"
    assert forced_decisions[0]["invalidation_reason"] == "force_rebuild"
    assert forced["content_fingerprint"] == first["content_fingerprint"]

    # Force rebuild on an empty registry still publishes the newly built artifact.
    fresh_cache = tmp_path / "fresh-cache"
    forced_empty_decisions: list[dict] = []
    forced_empty = prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-4",
        core_command=str(core),
        producer_cache_root=fresh_cache,
        force_rebuild=True,
        reuse_decisions=forced_empty_decisions,
    )
    assert forced_empty_decisions[0]["action"] == "built"
    _physical_core(core, analyze_exit=97)
    after_forced_decisions: list[dict] = []
    after_forced = prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-5",
        core_command=str(core),
        producer_cache_root=fresh_cache,
        reuse_decisions=after_forced_decisions,
    )
    assert after_forced_decisions[0]["action"] == "reused"
    assert after_forced["content_fingerprint"] == forced_empty["content_fingerprint"]


def test_invalid_cached_physical_model_is_diagnosed_and_rebuilt(tmp_path: Path) -> None:
    model = tmp_path / "model.pdm"
    model.write_text("<Model/>\n", encoding="utf-8")
    core = _physical_core(tmp_path / "core")
    cache = tmp_path / "cache"
    decisions: list[dict] = []
    prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-1",
        core_command=str(core),
        producer_cache_root=cache,
        reuse_decisions=decisions,
    )
    key = decisions[0]["reuse_key"]
    payload = ProducerArtifactStore(cache).entry_root("physical-model", key) / "payload"
    (payload / "metadata.json").unlink()

    rebuilt: list[dict] = []
    prepare_physical_model_artifact(
        model,
        scope_id="system-a",
        output_root=tmp_path / "run-2",
        core_command=str(core),
        producer_cache_root=cache,
        reuse_decisions=rebuilt,
    )
    assert rebuilt[0]["action"] == "built"
    assert rebuilt[0]["invalidation_reason"] == "cache_invalid"
    assert rebuilt[0]["diagnostics"]
    invalid_entries = list((cache / "invalid" / "physical-model").glob(f"{key}-*"))
    assert invalid_entries
    invalid_record = json.loads((invalid_entries[0] / "invalid.json").read_text(encoding="utf-8"))
    assert invalid_record["schema_version"] == "producer_artifact_reuse_invalid/v1"
    assert invalid_record["reuse_key"] == key
    assert "missing" in invalid_record["diagnostic"].casefold()
