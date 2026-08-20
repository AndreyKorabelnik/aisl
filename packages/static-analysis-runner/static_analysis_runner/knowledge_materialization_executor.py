from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from .io_utils import (
    now_utc,
    prepare_output,
    read_json,
    relative_or_absolute,
    stable_fingerprint,
    write_json,
)
from .knowledge_compat import require_knowledge_layer_core
from .producer_reuse import ProducerArtifactStore, build_reuse_decision
from .version import __version__

KNOWLEDGE_MATERIALIZATION_RUN_SCHEMA_VERSION = "knowledge_materialization_execution_run/v1"
SUPPORTED_RESOLUTION_PLAN_SCHEMA = "knowledge_resolution_plan/v2"
SUPPORTED_MATERIALIZATION_CATALOG_SCHEMA = "knowledge_materialization_catalog/v3"
SUPPORTED_REPOSITORY_RUN_SCHEMA = "static_repository_analysis_run_manifest/v1"
SUPPORTED_KLC_RESULT_SCHEMA = "knowledge_materialization_execution_result/v1"
_MATERIALIZATION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_MATERIALIZATION_PRODUCER_KIND = "knowledge-materialization"
_MATERIALIZATION_REUSE_IDENTITY_FIELD = "producer_reuse_key"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _materialization_payload_integrity(materialization_root: Path) -> list[dict[str, Any]]:
    """Fingerprint the immutable KLC result payload, including the DuckDB bytes.

    KLC manifest fingerprints intentionally describe knowledge/provenance content and are
    not a byte-integrity checksum for the database. The reuse registry therefore records
    file hashes for the actual immutable result payload so corruption is never accepted
    silently.
    """
    required = [materialization_root / "materialization-result.json"]
    knowledge_root = materialization_root / "knowledge-layer"
    if not knowledge_root.is_dir():
        raise FileNotFoundError(f"materialization knowledge-layer output is missing: {knowledge_root}")
    required.extend(sorted(path for path in knowledge_root.rglob("*") if path.is_file()))
    records: list[dict[str, Any]] = []
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"materialization reuse payload file is missing: {path}")
        records.append({
            "path": path.relative_to(materialization_root).as_posix(),
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    return records


def _validate_payload_integrity(payload_root: Path, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        raise ValueError("materialization reuse entry has no payload integrity manifest")
    for raw in records:
        relative = Path(str(raw.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe materialization reuse payload path: {relative}")
        path = (payload_root / relative).resolve()
        path.relative_to(payload_root.resolve())
        if not path.is_file():
            raise FileNotFoundError(f"cached materialization payload file is missing: {relative}")
        expected_size = int(raw.get("size") or -1)
        if path.stat().st_size != expected_size:
            raise ValueError(f"cached materialization payload size mismatch: {relative}")
        expected_sha = str(raw.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError(f"cached materialization payload has invalid SHA-256 record: {relative}")
        if _sha256_file(path) != expected_sha:
            raise ValueError(f"cached materialization payload SHA-256 mismatch: {relative}")


def _evidence_reuse_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    fingerprint = str(item.get("content_fingerprint") or "").strip()
    if not fingerprint:
        raise ValueError(f"evidence artifact has no content_fingerprint: {item.get('artifact_id')!r}")
    identity = {
        "artifact_kind": str(item.get("artifact_kind") or ""),
        "schema_version": str(item.get("schema_version") or ""),
        "content_fingerprint": fingerprint,
    }
    if identity["artifact_kind"] == "repository-structure-evidence":
        source_metadata = item.get("source_metadata") or {}
        if isinstance(source_metadata, Mapping) and source_metadata:
            identity["source_metadata"] = deepcopy(dict(source_metadata))
    return identity


def _knowledge_reuse_identity(item: Mapping[str, Any]) -> dict[str, Any]:
    stable_key = str(item.get(_MATERIALIZATION_REUSE_IDENTITY_FIELD) or "").strip()
    if stable_key and not re.fullmatch(r"[0-9a-f]{64}", stable_key):
        raise ValueError(f"knowledge artifact has invalid producer reuse key: {stable_key!r}")
    content_fingerprint = str(item.get("content_fingerprint") or "").strip()
    if not stable_key and not content_fingerprint:
        raise ValueError(f"knowledge artifact has no stable reuse identity: {item.get('artifact_id')!r}")
    return {
        "source_materialization_id": str(item.get("source_materialization_id") or ""),
        "model_kind": str(item.get("model_kind") or ""),
        "schema_version": str(item.get("schema_version") or ""),
        "semantic_content_identity": {
            "kind": "materialization_reuse_key" if stable_key else "content_fingerprint",
            "value": stable_key or content_fingerprint,
        },
    }


def _materialization_reuse_material(
    *,
    materialization_id: str,
    scope_id: str,
    klc_version: str,
    request_schema_version: str,
    contract: Mapping[str, Any],
    runtime_contract: Mapping[str, Any],
    evidence_artifacts: Sequence[Mapping[str, Any]],
    knowledge_artifacts: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Stable semantic identity for one KLC DAG producer node.

    Build-local artifact ids, paths, timestamps, plan/job ids and raw downstream KLC
    fingerprints are deliberately excluded. A downstream KLC artifact produced by this
    mechanism carries its materialization reuse key, which becomes the stable semantic
    content identity for dependent nodes.
    """
    evidence = sorted(
        (_evidence_reuse_identity(item) for item in evidence_artifacts),
        key=lambda value: (
            value["artifact_kind"], value["schema_version"], value["content_fingerprint"]
        ),
    )
    knowledge = sorted(
        (_knowledge_reuse_identity(item) for item in knowledge_artifacts),
        key=lambda value: (
            value["source_materialization_id"], value["model_kind"], value["schema_version"],
            value["semantic_content_identity"]["kind"], value["semantic_content_identity"]["value"],
        ),
    )
    return {
        "producer": {
            "id": f"knowledge-layer-core:{materialization_id}",
            "version": str(klc_version),
            "runtime_contract_id": str(runtime_contract.get("contract_id") or ""),
        },
        "materialization_id": materialization_id,
        "scope_id": scope_id,
        "request_schema_version": request_schema_version,
        "materialization_contract_fingerprint": stable_fingerprint(dict(contract)),
        "runtime_contract_fingerprint": stable_fingerprint(dict(runtime_contract)),
        "effective_inputs": {
            "evidence_artifacts": evidence,
            "knowledge_artifacts": knowledge,
        },
        "semantic_parameters": deepcopy(dict(parameters)),
    }


def _validate_cached_materialization(
    payload_root: Path,
    entry: Mapping[str, Any],
    *,
    expected_reuse_material: Mapping[str, Any],
    materialization_id: str,
    klc_version: str,
) -> None:
    metadata = entry.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("materialization reuse entry metadata is invalid")
    if dict(metadata.get("reuse_material") or {}) != dict(expected_reuse_material):
        raise ValueError("materialization reuse material mismatch")
    _validate_payload_integrity(payload_root, tuple(metadata.get("payload_integrity") or ()))
    result_path = payload_root / "materialization-result.json"
    result = read_json(result_path)
    if result.get("schema_version") != SUPPORTED_KLC_RESULT_SCHEMA or result.get("status") != "completed":
        raise ValueError("cached KLC result is not a completed supported materialization result")
    if str(result.get("materialization_id") or "") != materialization_id:
        raise ValueError("cached KLC result materialization identity mismatch")
    producer = result.get("producer") or {}
    if str(producer.get("component") or "") != "knowledge-layer-core":
        raise ValueError("cached KLC result producer component mismatch")
    if str(producer.get("version") or "") != str(klc_version):
        raise ValueError("cached KLC result producer version mismatch")
    actual_result_fingerprint = str(result.get("result_fingerprint") or "")
    if not actual_result_fingerprint or actual_result_fingerprint != _canonical_fingerprint(
        result, fingerprint_field="result_fingerprint"
    ):
        raise ValueError("cached KLC result fingerprint is invalid")
    knowledge_root = payload_root / "knowledge-layer"
    manifest_path = knowledge_root / "knowledge-layer-manifest.json"
    manifest = read_json(manifest_path)
    if str(manifest.get("build_status") or "") != "complete":
        raise ValueError("cached KLC knowledge-layer manifest is incomplete")
    manifest_fingerprint = stable_fingerprint(manifest)
    artifacts = [dict(item) for item in (result.get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    if not artifacts:
        raise ValueError("cached KLC result has no knowledge artifacts")
    for artifact in artifacts:
        if str(artifact.get("source_materialization_id") or "") != materialization_id:
            raise ValueError("cached KLC knowledge artifact source materialization mismatch")
        if str(artifact.get("content_fingerprint") or "") != manifest_fingerprint:
            raise ValueError("cached KLC knowledge artifact fingerprint does not match manifest")
    database_value = manifest.get("database_path") or (manifest.get("artifacts") or {}).get("database")
    database_path = knowledge_root / str(database_value or "knowledge-layer.duckdb")
    if not database_path.is_file():
        raise FileNotFoundError(f"cached KLC database is missing: {database_path.name}")


def _restore_cached_materialization(payload_root: Path, materialization_root: Path) -> dict[str, Any]:
    """Restore immutable knowledge bytes and emit an execution-local KLC result receipt.

    The cached KLC result retains the original build paths by design. Those paths are not
    valid execution identity for a later reuse run, so the reused run writes a fresh local
    receipt whose output/artifact locations point at the current materialization directory
    and whose result fingerprint is recomputed. The immutable cached payload is never
    mutated.
    """
    cached_knowledge = payload_root / "knowledge-layer"
    target_knowledge = materialization_root / "knowledge-layer"
    if target_knowledge.exists():
        shutil.rmtree(target_knowledge)
    shutil.copytree(cached_knowledge, target_knowledge)

    cached_result = read_json(payload_root / "materialization-result.json")
    active_result = deepcopy(dict(cached_result))
    manifest_path = target_knowledge / "knowledge-layer-manifest.json"
    output = deepcopy(dict(active_result.get("output") or {}))
    output["path"] = str(target_knowledge)
    output["manifest_path"] = str(manifest_path)
    active_result["output"] = output
    artifacts: list[dict[str, Any]] = []
    for raw in active_result.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        artifact = deepcopy(dict(raw))
        artifact["location"] = {
            "kind": "knowledge-layer",
            "output_path": str(target_knowledge),
            "manifest_path": str(manifest_path),
        }
        artifacts.append(artifact)
    active_result["knowledge_artifacts"] = artifacts
    active_result["result_fingerprint"] = _canonical_fingerprint(
        active_result, fingerprint_field="result_fingerprint"
    )
    target_result = materialization_root / "materialization-result.json"
    write_json(target_result, active_result)
    return active_result


def _activate_materialization_result(
    result: Mapping[str, Any],
    *,
    materialization_root: Path,
    reuse_key: str | None,
) -> dict[str, Any]:
    """Rebind execution-local locations without mutating the immutable KLC result file."""
    active = deepcopy(dict(result))
    knowledge_root = materialization_root / "knowledge-layer"
    manifest_path = knowledge_root / "knowledge-layer-manifest.json"
    output = deepcopy(dict(active.get("output") or {}))
    output["path"] = str(knowledge_root)
    output["manifest_path"] = str(manifest_path)
    active["output"] = output
    artifacts: list[dict[str, Any]] = []
    for raw in active.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        artifact = deepcopy(dict(raw))
        artifact["location"] = {
            "kind": "knowledge-layer",
            "output_path": str(knowledge_root),
            "manifest_path": str(manifest_path),
        }
        artifact["materialization_result_path"] = str(materialization_root / "materialization-result.json")
        artifact.setdefault("status", "completed")
        if reuse_key is not None:
            artifact[_MATERIALIZATION_REUSE_IDENTITY_FIELD] = reuse_key
        artifacts.append(artifact)
    active["knowledge_artifacts"] = artifacts
    return active


def _execute_klc_materialization_isolated(
    *,
    request_path: Path,
    output_path: Path,
    result_path: Path,
    duckdb_memory_limit: str,
    duckdb_threads: int,
    materialization_id: str,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute one generic KLC materialization in a fresh interpreter.

    DuckDB-heavy materializations stay isolated one-per-process. Worker stdout/stderr
    are persisted as before and are also streamed to the Runner progress callback so
    an orchestrator can observe long KLC phases without changing runtime semantics.
    """
    stdout_path = result_path.with_name("materialization-runtime.stdout.log")
    stderr_path = result_path.with_name("materialization-runtime.stderr.log")
    command = [
        sys.executable,
        "-m",
        "static_analysis_runner.klc_materialization_worker",
        "--request",
        str(request_path),
        "--output",
        str(output_path),
        "--result",
        str(result_path),
        "--duckdb-memory-limit",
        str(duckdb_memory_limit),
        "--duckdb-threads",
        str(max(1, int(duckdb_threads))),
    ]
    started = time.monotonic()
    if progress:
        progress(f"[materialization:{materialization_id}] worker started")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def drain(stream: Any, sink: list[str], label: str) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            sink.append(line)
            text = line.rstrip("\r\n")
            if progress and text:
                progress(f"[materialization:{materialization_id}][{label}] {text}")
        stream.close()

    stdout_thread = threading.Thread(
        target=drain, args=(process.stdout, stdout_lines, "stdout"), daemon=True
    )
    stderr_thread = threading.Thread(
        target=drain, args=(process.stderr, stderr_lines, "stderr"), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    stdout_text = "".join(stdout_lines)
    stderr_text = "".join(stderr_lines)
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    elapsed = time.monotonic() - started
    if progress:
        progress(
            f"[materialization:{materialization_id}] worker exited code={returncode}; duration={elapsed:.1f}s"
        )
    if returncode != 0:
        detail = (stderr_text or stdout_text or "KLC worker failed without output").strip()
        raise RuntimeError(
            f"isolated KLC materialization failed with exit code {returncode}: {detail}"
        )
    if not result_path.is_file():
        raise RuntimeError("isolated KLC materialization completed without a result artifact")
    return read_json(result_path)


def _canonical_fingerprint(payload: Mapping[str, Any], *, fingerprint_field: str) -> str:
    material = {
        str(key): deepcopy(value)
        for key, value in payload.items()
        if str(key) != fingerprint_field
    }
    return stable_fingerprint(material)


def _validate_catalog(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SUPPORTED_MATERIALIZATION_CATALOG_SCHEMA:
        raise ValueError(
            f"unsupported KLC materialization catalog schema: {payload.get('schema_version')!r}"
        )
    actual = str(payload.get("catalog_fingerprint") or "")
    if not actual or actual != _canonical_fingerprint(payload, fingerprint_field="catalog_fingerprint"):
        raise ValueError("KLC materialization catalog fingerprint is invalid")
    runtime = payload.get("runtime_contract") or {}
    if str(runtime.get("contract_id") or "") != "knowledge_materialization_runtime/v1":
        raise ValueError("KLC materialization catalog has no generic runtime contract")
    if str(runtime.get("generic_entrypoint") or "") != "knowledge_layer_core.materialization_runtime.materialize":
        raise ValueError("KLC materialization catalog declares an unsupported generic entrypoint")


def _validate_plan(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SUPPORTED_RESOLUTION_PLAN_SCHEMA:
        raise ValueError(f"unsupported knowledge resolution plan schema: {payload.get('schema_version')!r}")
    expected = stable_fingerprint({
        str(key): deepcopy(value)
        for key, value in payload.items()
        if str(key) != "plan_fingerprint"
    })
    if str(payload.get("plan_fingerprint") or "") != expected:
        raise ValueError("knowledge resolution plan fingerprint is invalid")


def _contracts_by_id(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    values = catalog.get("materializations") or []
    if not isinstance(values, list):
        raise ValueError("KLC materialization catalog field 'materializations' must be a list")
    for raw in values:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        materialization_id = str(item.get("materialization_id") or "").strip()
        if not materialization_id or materialization_id in result:
            raise ValueError(f"invalid or duplicate materialization_id: {materialization_id!r}")
        result[materialization_id] = item
    return result


def _selected_materialization_ids(plan: Mapping[str, Any]) -> tuple[str, ...]:
    technical = plan.get("technical_plan") or {}
    raw = technical.get("materializations") or []
    ids = tuple(str(item.get("materialization_id") or "").strip() for item in raw if isinstance(item, Mapping))
    if not ids or any(not item for item in ids):
        raise ValueError("knowledge resolution plan has no valid materializations")
    if len(set(ids)) != len(ids):
        raise ValueError("knowledge resolution plan contains duplicate materializations")
    return ids


def _topological_order(
    selected: Sequence[str],
    contracts: Mapping[str, Mapping[str, Any]],
    available_knowledge: Sequence[Mapping[str, Any]] = (),
) -> tuple[str, ...]:
    selected_set = set(selected)
    dependencies: dict[str, set[str]] = {item: set() for item in selected}
    for materialization_id in selected:
        contract = contracts.get(materialization_id)
        if contract is None:
            raise ValueError(f"materialization is missing from KLC catalog: {materialization_id!r}")
        input_contract = contract.get("input_contract") or {}
        for requirement in input_contract.get("required_knowledge_models") or []:
            if not isinstance(requirement, Mapping):
                continue
            source = str(requirement.get("source_materialization_id") or "").strip()
            if source in selected_set:
                dependencies[materialization_id].add(source)
                continue
            model_kind = str(requirement.get("model_kind") or "").strip()
            versions = {str(item) for item in (requirement.get("schema_versions") or [])}
            satisfied_by_existing = any(
                str(item.get("source_materialization_id") or "") == source
                and str(item.get("model_kind") or "") == model_kind
                and str(item.get("schema_version") or "") in versions
                for item in available_knowledge
            )
            if not satisfied_by_existing:
                raise ValueError(
                    f"materialization {materialization_id!r} requires unavailable knowledge materialization {source!r}"
                )
        for requirement in input_contract.get("optional_knowledge_models") or []:
            if not isinstance(requirement, Mapping):
                continue
            source = str(requirement.get("source_materialization_id") or "").strip()
            if source in selected_set:
                dependencies[materialization_id].add(source)

    ordered: list[str] = []
    remaining = {key: set(value) for key, value in dependencies.items()}
    preference = {value: index for index, value in enumerate(selected)}
    while remaining:
        ready = sorted(
            (item for item, deps in remaining.items() if not deps),
            key=lambda item: (preference[item], item),
        )
        if not ready:
            raise ValueError(f"knowledge materialization dependency cycle: {remaining}")
        # The execution plan already owns the deterministic order of independent
        # graph branches. Consume one ready node at a time so a newly unlocked
        # dependency may keep its valid plan position ahead of another branch.
        # Processing an entire ready layer here imposed a second, incompatible
        # topological ordering and rejected otherwise valid typed plans.
        item = ready[0]
        ordered.append(item)
        remaining.pop(item)
        for deps in remaining.values():
            deps.discard(item)
    return tuple(ordered)


def _collect_evidence(repository_run_manifests: Iterable[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen_artifact_ids: dict[str, tuple[str, str, str]] = {}
    for manifest_path in repository_run_manifests:
        payload = read_json(manifest_path)
        if payload.get("schema_version") != SUPPORTED_REPOSITORY_RUN_SCHEMA:
            raise ValueError(f"unsupported repository run manifest schema: {manifest_path}")
        if payload.get("status") != "completed":
            raise ValueError(f"repository run is not completed: {manifest_path}")
        repository = payload.get("repository") or {}
        repo_id = str(repository.get("repo_id") or "").strip()
        if not repo_id:
            raise ValueError(f"repository run has no repository.repo_id: {manifest_path}")
        sources.append({
            "repo_id": repo_id,
            "manifest_path": str(manifest_path),
            "revision": repository.get("revision"),
        })
        for raw in payload.get("evidence_artifacts") or []:
            if not isinstance(raw, Mapping):
                raise ValueError(f"repository run contains a non-object evidence registration: {manifest_path}")
            item = dict(raw)
            artifact_id = str(item.get("artifact_id") or "").strip()
            kind = str(item.get("artifact_kind") or "").strip()
            version = str(item.get("schema_version") or "").strip()
            fingerprint = str(item.get("content_fingerprint") or "").strip()
            if not all((artifact_id, kind, version, fingerprint)):
                raise ValueError(f"incomplete evidence registration in {manifest_path}")
            identity = (kind, version, fingerprint)
            previous = seen_artifact_ids.get(artifact_id)
            if previous is not None and previous != identity:
                raise ValueError(f"conflicting evidence artifact_id across repository runs: {artifact_id}")
            seen_artifact_ids[artifact_id] = identity
            evidence.append({
                "artifact_id": artifact_id,
                "artifact_kind": kind,
                "schema_version": version,
                "content_fingerprint": fingerprint,
                "registration_manifest_path": str(manifest_path),
                "repo_id": repo_id,
                "status": item.get("status"),
            })
    return evidence, sources


def _collect_existing_knowledge(result_paths: Iterable[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in result_paths:
        payload = read_json(path)
        if payload.get("schema_version") != SUPPORTED_KLC_RESULT_SCHEMA or payload.get("status") != "completed":
            raise ValueError(f"not a completed KLC materialization result: {path}")
        for raw in payload.get("knowledge_artifacts") or []:
            if isinstance(raw, Mapping):
                item = dict(raw)
                item["materialization_result_path"] = str(path)
                artifacts.append(item)
    return artifacts


def _matching_evidence(
    requirements: Sequence[Mapping[str, Any]],
    available: Sequence[Mapping[str, Any]],
    *,
    required: bool,
    materialization_id: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for requirement in requirements:
        kind = str(requirement.get("artifact_kind") or "").strip()
        versions = {str(item) for item in (requirement.get("schema_versions") or [])}
        matches = [
            dict(item)
            for item in available
            if str(item.get("artifact_kind") or "") == kind
            and str(item.get("schema_version") or "") in versions
            and str(item.get("status") or "") in {"completed", "partial"}
        ]
        if required and not matches:
            raise ValueError(
                f"materialization {materialization_id!r} has no required evidence {kind}/{sorted(versions)}"
            )
        selected.extend(matches)
    unique = {str(item["artifact_id"]): item for item in selected}
    return [unique[key] for key in sorted(unique)]


def _matching_knowledge(
    requirements: Sequence[Mapping[str, Any]],
    available: Sequence[Mapping[str, Any]],
    *,
    required: bool,
    materialization_id: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for requirement in requirements:
        model_kind = str(requirement.get("model_kind") or "").strip()
        source = str(requirement.get("source_materialization_id") or "").strip()
        versions = {str(item) for item in (requirement.get("schema_versions") or [])}
        matches = [
            dict(item)
            for item in available
            if str(item.get("model_kind") or "") == model_kind
            and str(item.get("source_materialization_id") or "") == source
            and str(item.get("schema_version") or "") in versions
        ]
        if required and not matches:
            raise ValueError(
                f"materialization {materialization_id!r} has no required knowledge input "
                f"{source}:{model_kind}/{sorted(versions)}"
            )
        selected.extend(matches)
    unique = {str(item["artifact_id"]): item for item in selected}
    return [unique[key] for key in sorted(unique)]


def _scope_id(plan: Mapping[str, Any], override: str | None) -> str:
    if override and override.strip():
        return override.strip()
    profile = plan.get("profile") or {}
    scope = profile.get("scope") or {}
    value = str(scope.get("scope_id") or scope.get("id") or "").strip()
    if not value:
        raise ValueError("scope_id is missing from knowledge profile; provide --scope-id")
    return value


def execute_knowledge_materialization_plan(
    *,
    resolution_plan: str | Path,
    materialization_catalog: str | Path,
    repository_run_manifests: Iterable[str | Path],
    output: str | Path,
    existing_materialization_results: Iterable[str | Path] = (),
    scope_id: str | None = None,
    replace: bool = False,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute a Knowledge Resolution Plan without materialization-specific Runner code."""
    plan_path = Path(resolution_plan).expanduser().resolve()
    catalog_path = Path(materialization_catalog).expanduser().resolve()
    repository_paths = tuple(Path(item).expanduser().resolve() for item in repository_run_manifests)
    result_paths = tuple(Path(item).expanduser().resolve() for item in existing_materialization_results)
    if not repository_paths and not result_paths:
        raise ValueError("at least one repository run or existing materialization result is required")
    if duckdb_threads < 1:
        raise ValueError("duckdb_threads must be at least 1")

    plan = read_json(plan_path)
    catalog = read_json(catalog_path)
    _validate_plan(plan)
    _validate_catalog(catalog)
    contracts = _contracts_by_id(catalog)
    selected = _selected_materialization_ids(plan)
    evidence, sources = _collect_evidence(repository_paths)
    knowledge_artifacts = _collect_existing_knowledge(result_paths)
    order = _topological_order(selected, contracts, knowledge_artifacts)
    resolved_scope_id = _scope_id(plan, scope_id)

    protected = (plan_path, catalog_path, *repository_paths, *result_paths)
    root = prepare_output(output, replace=replace, protected_paths=protected)
    klc, klc_version = require_knowledge_layer_core(
        context="generic knowledge materialization execution",
        required_symbols=("materialize", "MATERIALIZATION_REQUEST_SCHEMA_VERSION"),
    )

    started_at = now_utc()
    executions: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    for ordinal, materialization_id in enumerate(order, start=1):
        if not _MATERIALIZATION_ID_PATTERN.fullmatch(materialization_id):
            raise ValueError(f"unsafe materialization_id: {materialization_id!r}")
        contract = contracts[materialization_id]
        runtime = ((contract.get("current_implementation") or {}).get("runtime") or {})
        if runtime.get("registered") is not True:
            raise ValueError(f"materialization is not registered in KLC runtime: {materialization_id!r}")
        if str(runtime.get("handler_id") or "") != materialization_id:
            raise ValueError(f"KLC runtime handler identity mismatch for {materialization_id!r}")
        input_contract = contract.get("input_contract") or {}
        required_evidence = _matching_evidence(
            tuple(item for item in (input_contract.get("required_evidence") or []) if isinstance(item, Mapping)),
            evidence,
            required=True,
            materialization_id=materialization_id,
        )
        optional_evidence = _matching_evidence(
            tuple(item for item in (input_contract.get("optional_evidence") or []) if isinstance(item, Mapping)),
            evidence,
            required=False,
            materialization_id=materialization_id,
        )
        required_knowledge = _matching_knowledge(
            tuple(item for item in (input_contract.get("required_knowledge_models") or []) if isinstance(item, Mapping)),
            knowledge_artifacts,
            required=True,
            materialization_id=materialization_id,
        )
        optional_knowledge = _matching_knowledge(
            tuple(item for item in (input_contract.get("optional_knowledge_models") or []) if isinstance(item, Mapping)),
            knowledge_artifacts,
            required=False,
            materialization_id=materialization_id,
        )
        request = {
            "schema_version": str(getattr(klc, "MATERIALIZATION_REQUEST_SCHEMA_VERSION")),
            "materialization_id": materialization_id,
            "scope_id": resolved_scope_id,
            "inputs": {
                "evidence_artifacts": required_evidence + [
                    item for item in optional_evidence if item["artifact_id"] not in {x["artifact_id"] for x in required_evidence}
                ],
                "knowledge_artifacts": required_knowledge + [
                    item for item in optional_knowledge if item["artifact_id"] not in {x["artifact_id"] for x in required_knowledge}
                ],
            },
            "parameters": {},
            "orchestration": {
                "runner_version": __version__,
                "resolution_plan_fingerprint": plan.get("plan_fingerprint"),
                "materialization_catalog_fingerprint": catalog.get("catalog_fingerprint"),
            },
        }
        materialization_root = root / "materializations" / f"{ordinal:03d}-{materialization_id}"
        request_path = materialization_root / "materialization-request.json"
        result_path = materialization_root / "materialization-result.json"
        write_json(request_path, request)
        materialization_started = time.monotonic()
        if progress:
            progress(
                f"[materialization:{materialization_id}] started "
                f"({ordinal}/{len(order)})"
            )
        result = _execute_klc_materialization_isolated(
            request_path=request_path,
            output_path=materialization_root / "knowledge-layer",
            result_path=result_path,
            duckdb_memory_limit=duckdb_memory_limit,
            duckdb_threads=duckdb_threads,
            materialization_id=materialization_id,
            progress=progress,
        )
        if result.get("schema_version") != SUPPORTED_KLC_RESULT_SCHEMA or result.get("status") != "completed":
            raise RuntimeError(f"KLC returned invalid materialization result for {materialization_id!r}")
        if str(result.get("materialization_id") or "") != materialization_id:
            raise RuntimeError(f"KLC returned wrong materialization_id for {materialization_id!r}")
        new_artifacts = [dict(item) for item in (result.get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
        for item in new_artifacts:
            item["materialization_result_path"] = str(result_path)
        knowledge_artifacts.extend(new_artifacts)
        published = sorted({str(item) for item in (result.get("published_capabilities") or []) if str(item)})
        capabilities.update(published)
        if progress:
            counts = dict((result.get("output") or {}).get("counts") or {})
            counts_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
            suffix = f"; counts: {counts_text}" if counts_text else ""
            progress(
                f"[materialization:{materialization_id}] completed; "
                f"duration={time.monotonic() - materialization_started:.1f}s{suffix}"
            )
        executions.append({
            "materialization_execution_id": result.get("execution_id"),
            "materialization_id": materialization_id,
            "status": "completed",
            "input_artifact_ids": [item["artifact_id"] for item in request["inputs"]["evidence_artifacts"]],
            "input_knowledge_artifact_ids": [item["artifact_id"] for item in request["inputs"]["knowledge_artifacts"]],
            "request": relative_or_absolute(request_path, root),
            "result": relative_or_absolute(result_path, root),
            "output_manifest": relative_or_absolute(Path(result["output"]["manifest_path"]), root),
            "published_capabilities": published,
            "knowledge_artifact_ids": [item.get("artifact_id") for item in new_artifacts],
            "producer": result.get("producer"),
            "started_at": result.get("started_at"),
            "completed_at": result.get("completed_at"),
        })

    completed_at = now_utc()
    run = {
        "schema_version": KNOWLEDGE_MATERIALIZATION_RUN_SCHEMA_VERSION,
        "runner": {"producer": "static-analysis-runner", "version": __version__},
        "knowledge_layer_core": {
            "version": klc_version,
            "runtime_contract_id": "knowledge_materialization_runtime/v1",
            "execution_isolation": "one_process_per_materialization",
        },
        "scope_id": resolved_scope_id,
        "resolution_plan": {
            "path": str(plan_path),
            "plan_fingerprint": plan.get("plan_fingerprint"),
        },
        "materialization_catalog": {
            "path": str(catalog_path),
            "catalog_fingerprint": catalog.get("catalog_fingerprint"),
        },
        "sources": sources,
        "execution_order": list(order),
        "materialization_executions": executions,
        "knowledge_artifacts": knowledge_artifacts,
        "published_capabilities": sorted(capabilities),
        "semantic_policy": {
            "runner_dispatch": "generic_contract_driven",
            "klc_dispatch": "materialization_id_to_klc_owned_handler",
            "capability_publication": "completed_materialization_results_only",
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
        "diagnostics": [],
    }
    run["execution_fingerprint"] = stable_fingerprint({
        "scope_id": resolved_scope_id,
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "catalog_fingerprint": catalog.get("catalog_fingerprint"),
        "source_artifacts": sorted(
            (item["artifact_id"], item["artifact_kind"], item["schema_version"], item["content_fingerprint"])
            for item in evidence
        ),
        "materialization_results": [
            (item["materialization_id"], item["materialization_execution_id"], tuple(item["knowledge_artifact_ids"]))
            for item in executions
        ],
    })
    write_json(root / "knowledge_materialization_execution_run.json", run)
    write_json(root / "knowledge_materialization_execution_summary.json", {
        "schema_version": "knowledge_materialization_execution_summary/v1",
        "scope_id": resolved_scope_id,
        "status": "completed",
        "materialization_count": len(executions),
        "knowledge_artifact_count": len(knowledge_artifacts),
        "published_capabilities": sorted(capabilities),
        "execution_fingerprint": run["execution_fingerprint"],
    })
    return run


def execute_materialization_execution_plan(
    *,
    execution_plan: Mapping[str, Any],
    materialization_catalog: Mapping[str, Any],
    evidence_artifacts: Sequence[Mapping[str, Any]],
    knowledge_artifacts: Sequence[Mapping[str, Any]],
    output: str | Path,
    replace: bool = False,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    producer_cache_root: str | Path | None = None,
    force_rebuild: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute KLC nodes directly from knowledge_execution_plan/v1."""
    from .knowledge_execution_planning import validate_knowledge_execution_plan

    if duckdb_threads < 1:
        raise ValueError("duckdb_threads must be at least 1")
    plan = validate_knowledge_execution_plan(execution_plan)
    catalog = deepcopy(dict(materialization_catalog))
    _validate_catalog(catalog)
    expected_catalog_fingerprint = str(
        (plan.get("inputs") or {}).get("knowledge_materialization_catalog_fingerprint") or ""
    )
    if expected_catalog_fingerprint != str(catalog.get("catalog_fingerprint") or ""):
        raise ValueError("knowledge execution plan materialization catalog fingerprint does not match")
    if str((plan.get("status") or {}).get("overall") or "") != "ready":
        raise ValueError("knowledge execution plan is blocked and cannot be materialized")

    nodes = {
        str(item.get("node_id") or ""): dict(item)
        for item in (plan.get("graph") or {}).get("nodes") or []
        if isinstance(item, Mapping)
    }
    execution_order = [str(value) for value in (plan.get("graph") or {}).get("execution_order") or []]
    materialization_nodes = [
        nodes[node_id]
        for node_id in execution_order
        if str((nodes.get(node_id) or {}).get("node_kind") or "") == "knowledge_materialization"
    ]
    if not materialization_nodes:
        raise ValueError("knowledge execution plan has no materialization nodes")

    contracts = _contracts_by_id(catalog)
    selected_ids = [str(node.get("materialization_id") or "") for node in materialization_nodes]
    if any(not value for value in selected_ids) or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("knowledge execution plan has invalid materialization node identities")
    expected_order = list(_topological_order(selected_ids, contracts, knowledge_artifacts))
    if selected_ids != expected_order:
        raise ValueError(
            f"knowledge execution plan materialization order is invalid: "
            f"actual={selected_ids}, expected={expected_order}"
        )

    resolved_scope_id = str((plan.get("scope") or {}).get("scope_id") or "").strip()
    if not resolved_scope_id:
        raise ValueError("knowledge execution plan has no scope_id")
    root = prepare_output(output, replace=replace)
    available_evidence = [deepcopy(dict(item)) for item in evidence_artifacts]
    available_knowledge = [deepcopy(dict(item)) for item in knowledge_artifacts]
    for item in available_evidence:
        if not all(str(item.get(field) or "") for field in ("artifact_id", "artifact_kind", "schema_version")):
            raise ValueError("incomplete evidence artifact supplied to materialization executor")
        item.setdefault("status", "completed")
    for item in available_knowledge:
        if not all(
            str(item.get(field) or "")
            for field in ("artifact_id", "model_kind", "schema_version", "source_materialization_id")
        ):
            raise ValueError("incomplete knowledge artifact supplied to materialization executor")

    klc, klc_version = require_knowledge_layer_core(
        context="knowledge execution plan materialization",
        required_symbols=("materialize", "MATERIALIZATION_REQUEST_SCHEMA_VERSION"),
    )
    producer_store = ProducerArtifactStore(producer_cache_root) if producer_cache_root is not None else None
    started_at = now_utc()
    executions: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    produced_knowledge: list[dict[str, Any]] = []
    producer_reuse_decisions: list[dict[str, Any]] = []
    for ordinal, node in enumerate(materialization_nodes, start=1):
        materialization_id = str(node.get("materialization_id") or "")
        if not _MATERIALIZATION_ID_PATTERN.fullmatch(materialization_id):
            raise ValueError(f"unsafe materialization_id: {materialization_id!r}")
        contract = contracts.get(materialization_id)
        if contract is None:
            raise ValueError(f"materialization is missing from KLC catalog: {materialization_id!r}")
        runtime = ((contract.get("current_implementation") or {}).get("runtime") or {})
        if runtime.get("registered") is not True:
            raise ValueError(f"materialization is not registered in KLC runtime: {materialization_id!r}")
        if str(runtime.get("handler_id") or "") != materialization_id:
            raise ValueError(f"KLC runtime handler identity mismatch for {materialization_id!r}")
        if str(node.get("runtime_contract_id") or "") != str(runtime.get("contract_id") or ""):
            raise ValueError(f"execution-plan runtime contract mismatch for {materialization_id!r}")
        input_contract = contract.get("input_contract") or {}
        required_evidence = _matching_evidence(
            tuple(item for item in (input_contract.get("required_evidence") or []) if isinstance(item, Mapping)),
            available_evidence,
            required=True,
            materialization_id=materialization_id,
        )
        optional_evidence = _matching_evidence(
            tuple(item for item in (input_contract.get("optional_evidence") or []) if isinstance(item, Mapping)),
            available_evidence,
            required=False,
            materialization_id=materialization_id,
        )
        required_knowledge = _matching_knowledge(
            tuple(item for item in (input_contract.get("required_knowledge_models") or []) if isinstance(item, Mapping)),
            available_knowledge,
            required=True,
            materialization_id=materialization_id,
        )
        optional_knowledge = _matching_knowledge(
            tuple(item for item in (input_contract.get("optional_knowledge_models") or []) if isinstance(item, Mapping)),
            available_knowledge,
            required=False,
            materialization_id=materialization_id,
        )
        required_evidence_ids = {str(item["artifact_id"]) for item in required_evidence}
        required_knowledge_ids = {str(item["artifact_id"]) for item in required_knowledge}
        request_schema_version = str(getattr(klc, "MATERIALIZATION_REQUEST_SCHEMA_VERSION"))
        parameters = dict(node.get("parameters") or {})
        request = {
            "schema_version": request_schema_version,
            "materialization_id": materialization_id,
            "scope_id": resolved_scope_id,
            "inputs": {
                "evidence_artifacts": required_evidence + [
                    item for item in optional_evidence
                    if str(item["artifact_id"]) not in required_evidence_ids
                ],
                "knowledge_artifacts": required_knowledge + [
                    item for item in optional_knowledge
                    if str(item["artifact_id"]) not in required_knowledge_ids
                ],
            },
            "parameters": parameters,
            "orchestration": {
                "runner_version": __version__,
                "knowledge_execution_plan_fingerprint": plan.get("plan_fingerprint"),
                "execution_node_id": node.get("node_id"),
                "materialization_catalog_fingerprint": catalog.get("catalog_fingerprint"),
            },
        }
        materialization_root = root / "materializations" / f"{ordinal:03d}-{materialization_id}"
        request_path = materialization_root / "materialization-request.json"
        result_path = materialization_root / "materialization-result.json"
        write_json(request_path, request)
        reuse_material: dict[str, Any] | None = None
        reuse_key: str | None = None
        lookup = None
        invalid_diagnostic: str | None = None
        if producer_store is not None:
            reuse_material = _materialization_reuse_material(
                materialization_id=materialization_id,
                scope_id=resolved_scope_id,
                klc_version=klc_version,
                request_schema_version=request_schema_version,
                contract=contract,
                runtime_contract=dict(catalog.get("runtime_contract") or {}),
                evidence_artifacts=request["inputs"]["evidence_artifacts"],
                knowledge_artifacts=request["inputs"]["knowledge_artifacts"],
                parameters=parameters,
            )
            reuse_key = producer_store.reuse_key(reuse_material)
            lookup = producer_store.lookup(
                producer_kind=_MATERIALIZATION_PRODUCER_KIND,
                reuse_key=reuse_key,
                validator=lambda payload, entry, material=reuse_material, mid=materialization_id: (
                    _validate_cached_materialization(
                        payload,
                        entry,
                        expected_reuse_material=material,
                        materialization_id=mid,
                        klc_version=klc_version,
                    )
                ),
            )
            if lookup.status == "invalid":
                invalid_diagnostic = lookup.diagnostic or "materialization reuse artifact validation failed"
                producer_store.quarantine(
                    producer_kind=_MATERIALIZATION_PRODUCER_KIND,
                    reuse_key=reuse_key,
                    diagnostic=invalid_diagnostic,
                )

        materialization_started = time.monotonic()
        execution_action = "built"
        invalidation_reason: str | None = None
        if lookup is not None and lookup.status == "hit" and not force_rebuild:
            assert lookup.payload_root is not None and reuse_key is not None and reuse_material is not None
            if progress:
                progress(
                    f"REUSE materialization:{materialization_id} key={reuse_key[:16]} "
                    "basis=effective_inputs_materializer_contract"
                )
            result = _restore_cached_materialization(lookup.payload_root, materialization_root)
            execution_action = "reused"
            original_elapsed = ((lookup.entry or {}).get("metadata") or {}).get("build_elapsed_seconds")
            producer_reuse_decisions.append(build_reuse_decision(
                node_id=str(node.get("node_id") or ""),
                producer_kind=_MATERIALIZATION_PRODUCER_KIND,
                producer_id=f"knowledge-layer-core:{materialization_id}",
                producer_version=klc_version,
                action="reused",
                reuse_key=reuse_key,
                basis="effective_inputs_materializer_contract",
                source_id=resolved_scope_id,
                artifact_reference=str(result_path),
                saved_seconds=(float(original_elapsed) if original_elapsed is not None else None),
            ))
        else:
            if producer_store is None:
                invalidation_reason = "reuse_disabled"
            elif force_rebuild:
                invalidation_reason = "force_rebuild"
            elif invalid_diagnostic:
                invalidation_reason = "cache_invalid"
            else:
                invalidation_reason = "cache_miss"
            if progress:
                progress(
                    f"BUILD materialization:{materialization_id} reason={invalidation_reason} "
                    f"({ordinal}/{len(materialization_nodes)})"
                )
                progress(
                    f"[materialization:{materialization_id}] started "
                    f"({ordinal}/{len(materialization_nodes)})"
                )
            result = _execute_klc_materialization_isolated(
                request_path=request_path,
                output_path=materialization_root / "knowledge-layer",
                result_path=result_path,
                duckdb_memory_limit=duckdb_memory_limit,
                duckdb_threads=duckdb_threads,
                materialization_id=materialization_id,
                progress=progress,
            )
        if result.get("schema_version") != SUPPORTED_KLC_RESULT_SCHEMA or result.get("status") != "completed":
            raise RuntimeError(f"KLC returned invalid materialization result for {materialization_id!r}")
        if str(result.get("materialization_id") or "") != materialization_id:
            raise RuntimeError(f"KLC returned wrong materialization_id for {materialization_id!r}")
        active_result = _activate_materialization_result(
            result,
            materialization_root=materialization_root,
            reuse_key=reuse_key,
        )
        new_artifacts = [dict(item) for item in (active_result.get("knowledge_artifacts") or []) if isinstance(item, Mapping)]

        elapsed = time.monotonic() - materialization_started
        if (
            execution_action == "built"
            and producer_store is not None
            and reuse_key is not None
            and reuse_material is not None
        ):
            if force_rebuild and lookup is not None and lookup.status == "hit":
                # KLC raw fingerprints contain build-local provenance/timestamps and therefore
                # cannot be compared byte-for-byte across force rebuilds. The stable key already
                # binds exact KLC version + contract + effective semantic inputs; keep the prior
                # immutable cached artifact and expose this execution as an explicit rebuild.
                pass
            else:
                integrity = _materialization_payload_integrity(materialization_root)
                payload_root, entry = producer_store.publish_directory(
                    producer_kind=_MATERIALIZATION_PRODUCER_KIND,
                    reuse_key=reuse_key,
                    source_root=materialization_root,
                    metadata={
                        "reuse_material": reuse_material,
                        "producer_id": f"knowledge-layer-core:{materialization_id}",
                        "producer_version": klc_version,
                        "materialization_id": materialization_id,
                        "scope_id": resolved_scope_id,
                        "build_elapsed_seconds": elapsed,
                        "payload_integrity": integrity,
                    },
                )
                _validate_cached_materialization(
                    payload_root,
                    entry,
                    expected_reuse_material=reuse_material,
                    materialization_id=materialization_id,
                    klc_version=klc_version,
                )
            producer_reuse_decisions.append(build_reuse_decision(
                node_id=str(node.get("node_id") or ""),
                producer_kind=_MATERIALIZATION_PRODUCER_KIND,
                producer_id=f"knowledge-layer-core:{materialization_id}",
                producer_version=klc_version,
                action="built",
                reuse_key=reuse_key,
                basis="canonical_materialization_execution",
                source_id=resolved_scope_id,
                invalidation_reason=invalidation_reason,
                artifact_reference=str(result_path),
                elapsed_seconds=elapsed,
                diagnostics=([invalid_diagnostic] if invalid_diagnostic else []),
            ))

        available_knowledge.extend(new_artifacts)
        produced_knowledge.extend(new_artifacts)
        published = sorted({str(item) for item in (active_result.get("published_capabilities") or []) if str(item)})
        capabilities.update(published)
        if progress and execution_action == "built":
            counts = dict((active_result.get("output") or {}).get("counts") or {})
            counts_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
            suffix = f"; counts: {counts_text}" if counts_text else ""
            progress(
                f"[materialization:{materialization_id}] completed; "
                f"duration={elapsed:.1f}s{suffix}"
            )
        executions.append({
            "execution_node_id": node.get("node_id"),
            "materialization_execution_id": active_result.get("execution_id"),
            "materialization_id": materialization_id,
            "status": "completed",
            "execution_action": execution_action,
            **({"reuse_key": reuse_key} if reuse_key is not None else {}),
            "input_artifact_ids": [item["artifact_id"] for item in request["inputs"]["evidence_artifacts"]],
            "input_knowledge_artifact_ids": [item["artifact_id"] for item in request["inputs"]["knowledge_artifacts"]],
            "request": relative_or_absolute(request_path, root),
            "result": relative_or_absolute(result_path, root),
            "output_manifest": relative_or_absolute(
                materialization_root / "knowledge-layer" / "knowledge-layer-manifest.json", root
            ),
            "published_capabilities": published,
            "knowledge_artifact_ids": [item.get("artifact_id") for item in new_artifacts],
            "producer": active_result.get("producer"),
            "started_at": active_result.get("started_at"),
            "completed_at": active_result.get("completed_at"),
        })

    completed_at = now_utc()
    run = {
        "schema_version": KNOWLEDGE_MATERIALIZATION_RUN_SCHEMA_VERSION,
        "runner": {"producer": "static-analysis-runner", "version": __version__},
        "knowledge_layer_core": {
            "version": klc_version,
            "runtime_contract_id": "knowledge_materialization_runtime/v1",
            "execution_isolation": "one_process_per_materialization",
        },
        "scope_id": resolved_scope_id,
        "knowledge_execution_plan": {
            "plan_fingerprint": plan.get("plan_fingerprint"),
        },
        "materialization_catalog": {
            "catalog_fingerprint": catalog.get("catalog_fingerprint"),
        },
        "execution_order": selected_ids,
        "materialization_executions": executions,
        "knowledge_artifacts": available_knowledge,
        "produced_knowledge_artifacts": produced_knowledge,
        "published_capabilities": sorted(capabilities),
        "producer_reuse_decisions": producer_reuse_decisions,
        "semantic_policy": {
            "runner_dispatch": "generic_contract_driven",
            "klc_dispatch": "materialization_id_to_klc_owned_handler",
            "capability_publication": "completed_materialization_results_only",
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
        "diagnostics": [],
    }
    run["execution_fingerprint"] = stable_fingerprint({
        "scope_id": resolved_scope_id,
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "catalog_fingerprint": catalog.get("catalog_fingerprint"),
        "source_artifacts": sorted(
            (
                str(item.get("artifact_id") or ""),
                str(item.get("artifact_kind") or ""),
                str(item.get("schema_version") or ""),
                str(item.get("content_fingerprint") or ""),
            )
            for item in available_evidence
        ),
        "materialization_results": [
            (
                item["materialization_id"],
                item["materialization_execution_id"],
                tuple(item["knowledge_artifact_ids"]),
            )
            for item in executions
        ],
    })
    write_json(root / "knowledge_materialization_execution_run.json", run)
    write_json(root / "knowledge_materialization_execution_summary.json", {
        "schema_version": "knowledge_materialization_execution_summary/v1",
        "scope_id": resolved_scope_id,
        "status": "completed",
        "materialization_count": len(executions),
        "knowledge_artifact_count": len(produced_knowledge),
        "published_capabilities": sorted(capabilities),
        "execution_fingerprint": run["execution_fingerprint"],
    })
    return run
