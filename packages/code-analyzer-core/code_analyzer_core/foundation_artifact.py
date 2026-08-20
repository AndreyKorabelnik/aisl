from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.models import AnalysisResult, Fact
from code_analyzer_core.utils import write_json

FOUNDATION_SCHEMA_VERSION = "repository_analysis_foundation/v1"
FOUNDATION_STAGE_IDS = (
    "scan_files",
    "config_scan",
    "maven_dependency_scan",
    "gradle_dependency_scan",
    "openapi_scan",
    "java_structural_scan",
    "java_source_observation_build",
    "sql_scan",
    "db_schema_scan",
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def repository_state_fingerprint(repo: Path, files: Iterable[Path]) -> dict[str, Any]:
    """Fast same-working-tree identity for an internal reusable artifact.

    This intentionally uses path, size and mtime_ns. The artifact is an internal
    run cache, not a long-lived source archive; callers can rebuild it whenever
    repository metadata changes.
    """
    entries: list[dict[str, Any]] = []
    for path in sorted((Path(item) for item in files), key=lambda item: item.relative_to(repo).as_posix()):
        stat = path.stat()
        entries.append({
            "path": path.relative_to(repo).as_posix(),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        })
    return {
        "basis": "relative_path,size,mtime_ns",
        "files_count": len(entries),
        "total_bytes": sum(item["size"] for item in entries),
        "sha256": _canonical_sha256(entries),
    }


def foundation_stage_signature(profile: dict[str, Any]) -> dict[str, Any]:
    pipeline = profile.get("pipeline") or {}
    entries = [*(pipeline.get("stages") or []), *(pipeline.get("final_stages") or [])]
    selected: list[Any] = []
    for item in entries:
        stage_id = str(item.get("id")) if isinstance(item, dict) else str(item)
        if stage_id in FOUNDATION_STAGE_IDS:
            selected.append(item)
    ids = [str(item.get("id")) if isinstance(item, dict) else str(item) for item in selected]
    missing = [stage for stage in FOUNDATION_STAGE_IDS if stage not in ids]
    if missing:
        raise ValueError(f"foundation definition is missing required stages: {missing}")
    payload = {"stages": selected}
    return {"sha256": _canonical_sha256(payload), **payload}


def _link_or_copy(source: Path, target: Path) -> str:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        return "in_place"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def write_foundation_artifact(
    *,
    artifact_root: Path,
    repository: Path,
    files: list[Path],
    profile: dict[str, Any],
    result: AnalysisResult,
    db_schema: dict[str, Any],
    table_observations: dict[str, Any],
    statuses: dict[str, Any],
    optional_sections: dict[str, Any] | None,
    source_output_root: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    full_result = result.model_dump(mode="json")
    deferred_result = {
        "facts": full_result.pop("facts", []),
        "mapper_facts": full_result.pop("mapper_facts", []),
        "config_facts": full_result.pop("config_facts", []),
    }
    snapshot = {
        "analysis_result": full_result,
        "db_schema": db_schema,
        "table_observations": table_observations,
        "statuses": statuses,
    }
    write_json(artifact_root / "foundation-snapshot.json", snapshot)
    write_json(artifact_root / "foundation-deferred-result.json", deferred_result)
    write_json(artifact_root / "foundation-optional-sections.json", optional_sections or {})

    source_manifest = source_output_root / "facts" / "full_fact_manifest.json"
    store_files: list[dict[str, Any]] = []
    link_modes: set[str] = set()
    if source_manifest.is_file():
        target_manifest = artifact_root / "facts" / "full_fact_manifest.json"
        link_modes.add(_link_or_copy(source_manifest, target_manifest))
        source_by_type = source_output_root / "facts" / "full_by_type"
        if source_by_type.is_dir():
            for source in sorted(source_by_type.glob("*.jsonl")):
                target = artifact_root / "facts" / "full_by_type" / source.name
                link_modes.add(_link_or_copy(source, target))
                store_files.append({"path": target.relative_to(artifact_root).as_posix(), "bytes": target.stat().st_size})

    manifest = {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "producer": {"name": "code-analyzer-core", "version": CORE_VERSION},
        "repository": {
            "repo_id": repo_id,
            "path": str(repository),
            "state": repository_state_fingerprint(repository, files),
        },
        "analysis_identity": {
            "project_code": project_code,
            "system_name": system_name,
        },
        "foundation": foundation_stage_signature(profile),
        "snapshot": "foundation-snapshot.json",
        "deferred_result": "foundation-deferred-result.json",
        "optional_sections": "foundation-optional-sections.json",
        "source_observation_store": {
            "manifest": "facts/full_fact_manifest.json" if source_manifest.is_file() else None,
            "files": store_files,
            "materialization": sorted(link_modes),
        },
    }
    manifest["artifact_fingerprint"] = _canonical_sha256({k: v for k, v in manifest.items() if k != "artifact_fingerprint"})
    write_json(artifact_root / "foundation-manifest.json", manifest)
    return manifest


def load_foundation_artifact(
    *,
    artifact_root: Path,
    repository: Path,
    files: list[Path],
    profile: dict[str, Any],
    output_root: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
) -> tuple[AnalysisResult, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = artifact_root.expanduser().resolve()
    manifest_path = root / "foundation-manifest.json"
    snapshot_path = root / "foundation-snapshot.json"
    if not manifest_path.is_file() or not snapshot_path.is_file():
        raise ValueError(f"invalid foundation artifact: expected {manifest_path} and {snapshot_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != FOUNDATION_SCHEMA_VERSION:
        raise ValueError(f"unsupported foundation schema: {manifest.get('schema_version')!r}")
    expected_state = repository_state_fingerprint(repository, files)
    actual_state = ((manifest.get("repository") or {}).get("state") or {})
    if actual_state.get("sha256") != expected_state.get("sha256"):
        raise ValueError("foundation artifact repository state does not match the current repository")
    expected_signature = foundation_stage_signature(profile)
    actual_signature = manifest.get("foundation") or {}
    if actual_signature.get("sha256") != expected_signature.get("sha256"):
        raise ValueError("foundation artifact stage signature does not match the selected task profile")
    if str((manifest.get("repository") or {}).get("repo_id") or "") != repo_id:
        raise ValueError("foundation artifact repo_id does not match the requested repo_id")
    identity = manifest.get("analysis_identity") or {}
    if identity.get("project_code") != project_code or identity.get("system_name") != system_name:
        raise ValueError("foundation artifact project/system identity does not match the requested analysis")

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    result = AnalysisResult.model_validate(snapshot.get("analysis_result") or {})
    db_schema = dict(snapshot.get("db_schema") or {})
    table_observations = dict(snapshot.get("table_observations") or {})
    statuses = dict(snapshot.get("statuses") or {})
    deferred_sections = {"path": str(root / str(manifest.get("deferred_result") or "foundation-deferred-result.json")), "loaded": False}
    optional_sections = {"path": str(root / str(manifest.get("optional_sections") or "foundation-optional-sections.json")), "loaded": False}

    source_store = manifest.get("source_observation_store") or {}
    linked: list[str] = []
    source_manifest_rel = source_store.get("manifest")
    if source_manifest_rel:
        source_manifest = root / str(source_manifest_rel)
        target_manifest = output_root / "facts" / "full_fact_manifest.json"
        _link_or_copy(source_manifest, target_manifest)
        linked.append(target_manifest.relative_to(output_root).as_posix())
        for item in source_store.get("files") or []:
            rel = str((item or {}).get("path") or "")
            if not rel:
                continue
            source = root / rel
            target = output_root / rel
            _link_or_copy(source, target)
            linked.append(target.relative_to(output_root).as_posix())
        store_status = dict(statuses.get("source_observation_fact_store_status") or {})
        store_status["manifest_path"] = str(target_manifest)
        statuses["source_observation_fact_store_status"] = store_status
        result.coverage["source_observation_fact_store"] = store_status

    reuse = {
        "status": "reused",
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "artifact_root": str(root),
        "artifact_fingerprint": manifest.get("artifact_fingerprint"),
        "repository_state": expected_state,
        "linked_store_files": linked,
    }
    return result, db_schema, table_observations, statuses, deferred_sections, optional_sections, reuse


def hydrate_foundation_result(result: AnalysisResult, deferred_sections: dict[str, Any]) -> dict[str, Any]:
    if deferred_sections.get("loaded"):
        return deferred_sections
    path = Path(str(deferred_sections.get("path") or ""))
    if not path.is_file():
        raise ValueError(f"foundation deferred result not found: {path}")
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result.facts.extend(Fact.model_validate(item) for item in payload.get("facts") or [])
        result.mapper_facts.extend(Fact.model_validate(item) for item in payload.get("mapper_facts") or [])
        result.config_facts.extend(Fact.model_validate(item) for item in payload.get("config_facts") or [])
    finally:
        if gc_was_enabled:
            gc.enable()
    deferred_sections["loaded"] = True
    deferred_sections["counts"] = {
        "facts": len(payload.get("facts") or []),
        "mapper_facts": len(payload.get("mapper_facts") or []),
        "config_facts": len(payload.get("config_facts") or []),
    }
    return deferred_sections


def load_foundation_optional_sections(optional_sections: dict[str, Any]) -> dict[str, Any]:
    if optional_sections.get("loaded"):
        return dict(optional_sections.get("payload") or {})
    path = Path(str(optional_sections.get("path") or ""))
    if not path.is_file():
        optional_sections["loaded"] = True
        optional_sections["payload"] = {}
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    optional_sections["loaded"] = True
    optional_sections["payload"] = payload
    return dict(payload or {})
