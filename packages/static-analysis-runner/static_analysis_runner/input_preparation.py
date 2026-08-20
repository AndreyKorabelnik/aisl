from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from .execution import command_parts, run_process
from .io_utils import read_json, sha256_file, stable_fingerprint, write_json
from .knowledge_execution_planning import (
    build_knowledge_input_inventory,
    inspect_repository_source,
)
from .producer_reuse import ProducerArtifactStore, build_reuse_decision
from .runtime_support import validate_core_version


def _revision_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    revision = payload.get("revision")
    if isinstance(revision, Mapping):
        return revision
    return payload


def knowledge_artifacts_from_published_revision(
    payload: Mapping[str, Any],
    *,
    source_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Normalize all Prepared Knowledge artifacts from one published revision.

    Selection is deliberately not performed here. The execution planner owns deciding
    which available knowledge artifacts satisfy the selected Knowledge Profile.
    """
    revision = _revision_payload(payload)
    system_id = str(revision.get("system_id") or payload.get("system_id") or "").strip()
    revision_id = str(revision.get("revision_id") or payload.get("revision_id") or "").strip()
    if not system_id or not revision_id:
        raise ValueError("published revision must define system_id and revision_id")

    result: list[dict[str, Any]] = []
    for raw in revision.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("published revision contains a non-object knowledge artifact")
        artifact = dict(raw)
        required = ("artifact_id", "model_kind", "schema_version", "source_materialization_id")
        missing = [name for name in required if not str(artifact.get(name) or "").strip()]
        if missing:
            raise ValueError("published knowledge artifact is incomplete: " + ", ".join(missing))

        manifest = artifact.get("manifest") if isinstance(artifact.get("manifest"), Mapping) else {}
        uri = str(manifest.get("uri") or "").strip()
        parsed = urlsplit(uri)
        if parsed.scheme != "file":
            raise ValueError(
                "existing Prepared Knowledge input currently requires local file:// manifests; "
                f"got {uri!r}"
            )
        manifest_path = Path(unquote(parsed.path)).expanduser().resolve()
        if not manifest_path.is_file():
            raise FileNotFoundError(f"published knowledge artifact manifest is unavailable: {manifest_path}")

        result.append({
            "artifact_id": str(artifact["artifact_id"]),
            "model_kind": str(artifact["model_kind"]),
            "schema_version": str(artifact["schema_version"]),
            "source_materialization_id": str(artifact["source_materialization_id"]),
            "content_fingerprint": artifact.get("content_fingerprint"),
            "status": str(artifact.get("status") or "completed"),
            "scope_id": system_id,
            "location": {
                "kind": "knowledge-layer",
                "manifest_path": str(manifest_path),
                "output_path": str(manifest_path.parent),
                "exists": True,
            },
            "provenance": {
                "source": "knowledge-api-revision",
                "source_system_id": system_id,
                "source_revision_id": revision_id,
                "published_capabilities": list(artifact.get("capabilities") or []),
                **({"revision_snapshot_path": str(source_path.resolve())} if source_path is not None else {}),
            },
        })
    return result


_PHYSICAL_MODEL_PRODUCER_KIND = "physical-model"
_PHYSICAL_MODEL_PRODUCER_ID = "code-analyzer-core:analyze-physical-model"
_PHYSICAL_MODEL_SCHEMA_VERSION = "physical-model/v1"
_PHYSICAL_MODEL_MIN_CORE_VERSION = (0, 43, 1)
_PHYSICAL_MODEL_CONTRACT_FINGERPRINT = stable_fingerprint({
    "artifact_kind": "physical-model",
    "schema_version": _PHYSICAL_MODEL_SCHEMA_VERSION,
    "producer_entrypoint": "analyze-physical-model",
})


def _validate_cached_physical_model(
    payload_root: Path,
    _entry: Mapping[str, Any],
    *,
    expected_core_version: str,
    expected_source_sha256: str,
    expected_source_name: str,
    expected_source_id: str,
) -> dict[str, Any]:
    manifest_path = payload_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"physical-model manifest is missing: {manifest_path}")
    manifest = read_json(manifest_path)
    if str(manifest.get("schema_version") or "") != _PHYSICAL_MODEL_SCHEMA_VERSION:
        raise ValueError(f"unexpected physical-model schema: {manifest.get('schema_version')!r}")
    if str(manifest.get("core_version") or "") != expected_core_version:
        raise ValueError("physical-model producer version mismatch")
    if str(manifest.get("physical_model_source_id") or "") != expected_source_id:
        raise ValueError("physical-model source id mismatch")
    source = manifest.get("source") or {}
    if str(source.get("sha256") or "") != expected_source_sha256:
        raise ValueError("physical-model source SHA-256 mismatch")
    if str(source.get("file") or "") != expected_source_name:
        raise ValueError("physical-model source filename mismatch")
    if not str(manifest.get("content_fingerprint") or ""):
        raise ValueError("physical-model manifest has no content_fingerprint")
    metadata_path = payload_root / str(source.get("metadata_path") or "")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"physical-model metadata is missing: {metadata_path}")
    for raw in manifest.get("facts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("physical-model manifest contains a non-object fact descriptor")
        relative = str(raw.get("path") or "")
        candidate = (payload_root / relative).resolve()
        try:
            candidate.relative_to(payload_root.resolve())
        except ValueError as exc:
            raise ValueError(f"physical-model fact path escapes payload: {relative!r}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"physical-model fact file is missing: {candidate}")
        expected_sha = str(raw.get("sha256") or "")
        if expected_sha and sha256_file(candidate) != expected_sha:
            raise ValueError(f"physical-model fact SHA-256 mismatch: {relative}")
    return manifest


def _physical_model_descriptor(*, manifest_path: Path, source_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    fingerprint = str(manifest.get("content_fingerprint") or "").strip()
    if not fingerprint:
        raise ValueError("physical-model manifest has no content_fingerprint")
    return {
        "artifact_id": f"physical-model-{fingerprint[:24]}",
        "artifact_kind": "physical-model",
        "schema_version": _PHYSICAL_MODEL_SCHEMA_VERSION,
        "content_fingerprint": fingerprint,
        "status": "completed",
        "producer_kind": "core_external_input_preparation",
        "scope_id": manifest.get("physical_model_source_id"),
        "location": {
            "kind": "file",
            "path": str(manifest_path),
            "exists": True,
        },
        "provenance": {
            "producer": "code-analyzer-core physical-model",
            "producer_version": manifest.get("core_version"),
            "source_path": str(source_path),
            "source_sha256": (manifest.get("source") or {}).get("sha256"),
            "manifest_path": str(manifest_path),
        },
    }


def prepare_physical_model_artifact(
    model_path: Path,
    *,
    scope_id: str,
    output_root: Path,
    core_command: str = "code-analyzer-core",
    producer_cache_root: Path | None = None,
    force_rebuild: bool = False,
    reuse_decisions: list[dict[str, Any]] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Ask Core to extract physical-model/v1, with optional content-addressed reuse."""
    model = model_path.expanduser().resolve()
    if not model.is_file() or model.suffix.casefold() != ".pdm":
        raise ValueError(f"PowerDesigner .pdm file required: {model}")
    resolved_output_root = output_root.expanduser().resolve()
    resolved_output_root.mkdir(parents=True, exist_ok=True)
    target = resolved_output_root / "physical-model"
    log_path = resolved_output_root / "physical-model-core.log"

    store: ProducerArtifactStore | None = None
    reuse_key: str | None = None
    core_version: str | None = None
    lookup_status = "miss"
    invalid_diagnostic: str | None = None
    source_sha256 = sha256_file(model)
    reuse_material: dict[str, Any] | None = None
    if producer_cache_root is not None:
        core_version = validate_core_version(
            core_command=core_command,
            log_path=resolved_output_root / "physical-model-core-version.log",
            progress=progress,
            minimum_version=_PHYSICAL_MODEL_MIN_CORE_VERSION,
        )
        store = ProducerArtifactStore(producer_cache_root)
        reuse_material = {
            "producer": {"id": _PHYSICAL_MODEL_PRODUCER_ID, "version": core_version},
            "input": {
                "content_sha256": source_sha256,
                "source_file_name": model.name,
                "source_id": scope_id,
            },
            "output_contract": {
                "artifact_kind": "physical-model",
                "schema_version": _PHYSICAL_MODEL_SCHEMA_VERSION,
                "contract_fingerprint": _PHYSICAL_MODEL_CONTRACT_FINGERPRINT,
            },
            "semantic_parameters": {},
        }
        reuse_key = store.reuse_key(reuse_material)
        lookup = store.lookup(
            producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
            reuse_key=reuse_key,
            validator=lambda payload, entry: _validate_cached_physical_model(
                payload,
                entry,
                expected_core_version=core_version or "",
                expected_source_sha256=source_sha256,
                expected_source_name=model.name,
                expected_source_id=scope_id,
            ),
        )
        lookup_status = lookup.status
        if lookup.status == "hit" and not force_rebuild:
            assert lookup.payload_root is not None
            manifest_path = lookup.payload_root / "manifest.json"
            original_elapsed = float(((lookup.entry or {}).get("metadata") or {}).get("build_elapsed_seconds") or 0.0)
            decision = build_reuse_decision(
                node_id=f"physical-model:{scope_id}",
                producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
                producer_id=_PHYSICAL_MODEL_PRODUCER_ID,
                producer_version=core_version,
                action="reused",
                reuse_key=reuse_key,
                basis="content_addressed_completed_artifact",
                source_id=scope_id,
                artifact_reference=str(manifest_path),
                saved_seconds=original_elapsed or None,
            )
            if reuse_decisions is not None:
                reuse_decisions.append(decision)
            if progress:
                progress(f"REUSE physical-model:{scope_id} key={reuse_key[:16]} basis=content_addressed_completed_artifact")
            return _physical_model_descriptor(manifest_path=manifest_path, source_path=model)
        if lookup.status == "invalid":
            invalid_diagnostic = lookup.diagnostic or "reuse artifact validation failed"
            store.quarantine(
                producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
                reuse_key=reuse_key,
                diagnostic=invalid_diagnostic,
            )

    started = time.monotonic()
    command = command_parts(core_command) + [
        "analyze-physical-model",
        str(model),
        "--artifact-output",
        str(target),
        "--source-id",
        scope_id,
        "--clean-output",
    ]
    if progress:
        reason = "force_rebuild" if force_rebuild else ("cache_invalid" if invalid_diagnostic else "cache_miss")
        progress(f"BUILD physical-model:{scope_id} reason={reason}")
    completed = run_process(command, log_path=log_path)
    elapsed = time.monotonic() - started
    if completed.returncode != 0:
        raise RuntimeError(f"code-analyzer-core analyze-physical-model exited with code {completed.returncode}")
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("code-analyzer-core did not publish physical-model/v1 manifest.json")
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != _PHYSICAL_MODEL_SCHEMA_VERSION:
        raise ValueError(f"unexpected physical-model schema: {manifest.get('schema_version')!r}")
    if core_version is None:
        core_version = str(manifest.get("core_version") or "unknown")

    artifact_manifest = manifest_path
    should_publish = store is not None and reuse_key is not None and (
        not force_rebuild or lookup_status != "hit"
    )
    if should_publish:
        assert store is not None and reuse_key is not None
        payload_root, _entry = store.publish_directory(
            producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
            reuse_key=reuse_key,
            source_root=target,
            metadata={
                "producer_id": _PHYSICAL_MODEL_PRODUCER_ID,
                "producer_version": core_version,
                "input_content_sha256": source_sha256,
                "output_contract_fingerprint": _PHYSICAL_MODEL_CONTRACT_FINGERPRINT,
                "reuse_material": reuse_material,
                "build_elapsed_seconds": elapsed,
            },
        )
        _validate_cached_physical_model(
            payload_root,
            _entry,
            expected_core_version=core_version,
            expected_source_sha256=source_sha256,
            expected_source_name=model.name,
            expected_source_id=scope_id,
        )
        artifact_manifest = payload_root / "manifest.json"

    if store is not None and reuse_key is not None and force_rebuild and lookup_status == "hit":
        lookup = store.lookup(
            producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
            reuse_key=reuse_key,
            validator=lambda payload, entry: _validate_cached_physical_model(
                payload,
                entry,
                expected_core_version=core_version or "",
                expected_source_sha256=source_sha256,
                expected_source_name=model.name,
                expected_source_id=scope_id,
            ),
        )
        if lookup.status == "hit" and lookup.payload_root is not None:
            cached = read_json(lookup.payload_root / "manifest.json")
            if str(cached.get("content_fingerprint") or "") != str(manifest.get("content_fingerprint") or ""):
                raise RuntimeError("force rebuild produced a different physical-model content fingerprint for the same reuse key")

    if reuse_decisions is not None and reuse_key is not None:
        reason = "force_rebuild" if force_rebuild else ("cache_invalid" if invalid_diagnostic else "cache_miss")
        reuse_decisions.append(build_reuse_decision(
            node_id=f"physical-model:{scope_id}",
            producer_kind=_PHYSICAL_MODEL_PRODUCER_KIND,
            producer_id=_PHYSICAL_MODEL_PRODUCER_ID,
            producer_version=core_version,
            action="built",
            reuse_key=reuse_key,
            basis="canonical_producer_execution",
            source_id=scope_id,
            invalidation_reason=reason,
            artifact_reference=str(artifact_manifest),
            elapsed_seconds=elapsed,
            diagnostics=([invalid_diagnostic] if invalid_diagnostic else []),
        ))
    return _physical_model_descriptor(manifest_path=artifact_manifest, source_path=model)


def prepare_knowledge_input_inventory(
    *,
    scope_kind: str,
    scope_id: str,
    repositories: Sequence[Path],
    core_evidence_catalog: Mapping[str, Any],
    materialization_catalog: Mapping[str, Any],
    preparation_root: Path,
    physical_model_path: Path | None = None,
    published_revisions: Sequence[tuple[Path, Mapping[str, Any]]] = (),
    core_command: str = "code-analyzer-core",
    producer_cache_root: Path | None = None,
    force_rebuild: bool = False,
    reuse_decision_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
    repository_metadata_by_source_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare raw user/control-plane inputs into the canonical Runner inventory."""
    source_snapshots = [inspect_repository_source(path) for path in repositories]
    metadata_by_source_id = {
        str(key): dict(value)
        for key, value in (repository_metadata_by_source_id or {}).items()
        if isinstance(value, Mapping)
    }
    known_source_ids = {str(item.get("source_id") or "") for item in source_snapshots}
    unknown_metadata_ids = sorted(set(metadata_by_source_id) - known_source_ids)
    if unknown_metadata_ids:
        raise ValueError(f"repository metadata references unknown source ids: {unknown_metadata_ids}")
    for item in source_snapshots:
        source_id = str(item.get("source_id") or "")
        metadata = metadata_by_source_id.get(source_id)
        if metadata:
            item["source_metadata"] = metadata
    typed_artifacts: list[dict[str, Any]] = []
    reuse_decisions: list[dict[str, Any]] = []
    if physical_model_path is not None:
        typed_artifacts.append(
            prepare_physical_model_artifact(
                physical_model_path,
                scope_id=scope_id,
                output_root=preparation_root,
                core_command=core_command,
                producer_cache_root=producer_cache_root,
                force_rebuild=force_rebuild,
                reuse_decisions=reuse_decisions,
                progress=progress,
            )
        )
    knowledge_artifacts: list[dict[str, Any]] = []
    for source_path, revision in published_revisions:
        knowledge_artifacts.extend(
            knowledge_artifacts_from_published_revision(revision, source_path=source_path)
        )
    inventory = build_knowledge_input_inventory(
        scope_kind=scope_kind,
        scope_id=scope_id,
        source_snapshots=source_snapshots,
        core_evidence_catalog=core_evidence_catalog,
        materialization_catalog=materialization_catalog,
        typed_artifacts=typed_artifacts,
        knowledge_artifacts=knowledge_artifacts,
    )
    if reuse_decision_path is not None:
        write_json(reuse_decision_path, {
            "schema_version": "producer_reuse_decisions/v1",
            "decisions": reuse_decisions,
        })
    return inventory
