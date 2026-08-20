from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.pipeline import run_analysis

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "persistence-lineage-evidence"
SCHEMA_VERSION = "persistence-lineage-evidence/v1"
ANALYZER_ID = "persistence-lineage-analyzer"
RELATIVE_PATH = "evidence/persistence-lineage-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except Exception:
        return path.as_posix().lstrip("/") or "unknown"


def _source_snapshot(repository: Path, files: Iterable[Path], repo_id: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted((Path(item) for item in files), key=lambda item: _relative(repository, item)):
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        entries.append(
            {
                "repository_relative_path": _relative(repository, path),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byte_size": len(payload),
            }
        )
    material = {
        "source_id": repo_id,
        "scope": "persistence_lineage_sources",
        "files": entries,
    }
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "persistence_lineage_sources",
        "file_count": len(entries),
    }


def _profile(*, max_depth: int, deep: bool) -> dict[str, Any]:
    return {
        "profile_id": "internal-persistence-lineage-evidence-v1",
        "profile_version": 1,
        "name": "Typed persistence lineage evidence",
        "workspace_types": ["java"],
        "capabilities": ["lineage.persistence"],
        "pipeline": {
            "stages": [
                {"id": "scan_files"},
                {"id": "config_scan"},
                {"id": "maven_dependency_scan"},
                {"id": "gradle_dependency_scan"},
                {"id": "openapi_scan"},
                {"id": "java_structural_scan"},
                {
                    "id": "java_source_observation_build",
                    "options": {"framework_interpreters": []},
                },
                {"id": "java_system_interaction_enrichment"},
                {"id": "sql_scan"},
                {"id": "db_schema_scan"},
                {
                    "id": "java_persistence_lineage_build",
                    "options": {
                        "max_depth": max_depth,
                        "deep": deep,
                        "suspend_automatic_gc": deep,
                        "progress_interval": 25,
                    },
                },
            ],
            "final_stages": [
                {"id": "core_output"},
                {"id": "normalize_facts"},
                {"id": "compact_package"},
            ],
        },
        "output_contract": {
            "intent": "typed_persistence_lineage_evidence",
            "policy": {
                "no_business_decisions": True,
                "all_direct_paths_preserved": True,
            },
        },
    }


def _descriptor(root: Path, path: Path, *, artifact_name: str) -> dict[str, Any]:
    return {
        "artifact_name": artifact_name,
        "relative_path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "section": None,
    }


def _count(path: Path) -> int:
    if not path.is_file():
        return 0
    value = json.loads(path.read_text(encoding="utf-8"))
    return len(value) if isinstance(value, list) else 0


def _finalize(artifact: dict[str, Any]) -> dict[str, Any]:
    material = {
        key: deepcopy(value)
        for key, value in artifact.items()
        if key not in {"content_fingerprint", "artifact_id"}
    }
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"persistence_lineage_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_persistence_lineage_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    allowed = {"persistence_depth", "max_depth"}
    unsupported = sorted(str(key) for key in parameters if str(key) not in allowed)
    if unsupported:
        raise ValueError(
            "persistence-lineage-evidence/v1 unsupported runtime parameters: "
            + ", ".join(unsupported)
        )
    depth = str(parameters.get("persistence_depth") or "deep").strip().lower()
    if depth not in {"standard", "deep"}:
        raise ValueError("persistence_depth must be 'standard' or 'deep'")
    deep = depth == "deep"
    max_depth = int(parameters.get("max_depth") or (7 if deep else 4))
    if max_depth < 1 or max_depth > 32:
        raise ValueError("max_depth must be between 1 and 32")

    repository = repository.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    snapshot = _source_snapshot(repository, files, repo_id)
    payload_root = output_root / "evidence" / "persistence-lineage-payload"
    marker = payload_root / "persistence-lineage-payload-manifest.json"
    expected = {
        "schema_version": "persistence_lineage_payload_manifest/v1",
        "core_version": CORE_VERSION,
        "repo_id": repo_id,
        "source_fingerprint": snapshot["fingerprint"],
        "profile_id": "internal-persistence-lineage-evidence-v1",
        "persistence_depth": depth,
        "max_depth": max_depth,
    }
    if marker.is_file():
        current = json.loads(marker.read_text(encoding="utf-8"))
        if {key: current.get(key) for key in expected} != expected:
            raise ValueError(
                "existing persistence-lineage payload does not match the current evidence request"
            )
    else:
        if payload_root.exists():
            shutil.rmtree(payload_root)
        result = run_analysis(
            repository,
            payload_root,
            project_code=repo_id,
            system_name=repo_id,
            repo_id=repo_id,
            analysis_profile=_profile(max_depth=max_depth, deep=deep),
        )
        marker.write_text(
            json.dumps(
                {
                    **expected,
                    "coverage": result.coverage or {},
                    },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    names = (
        "source_to_storage_lineage.json",
        "storage_to_access_lineage.json",
        "persistent_writes.json",
        "storage_accesses.json",
        "storage_lineage_gaps.json",
        "stored_field_to_response_field_mappings.json",
    )
    diagnostics: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for name in names:
        path = payload_root / "compact" / name
        counts[name] = _count(path)
        if path.is_file():
            artifacts.append(
                _descriptor(output_root / "evidence", path, artifact_name=name)
            )
        else:
            diagnostics.append(
                {
                    "code": "persistence_lineage_payload_missing",
                    "severity": "warning",
                    "message": f"{name} was not produced",
                    "source_refs": [],
                }
            )

    status_path = payload_root / "diagnostics" / "java_persistence_lineage_status.json"
    status = (
        json.loads(status_path.read_text(encoding="utf-8"))
        if status_path.is_file()
        else {}
    )
    return _finalize(
        {
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": ARTIFACT_KIND,
            "schema_version": SCHEMA_VERSION,
            "producer": {
                "component": "code-analyzer-core",
                "analyzer_id": ANALYZER_ID,
                "analyzer_version": CORE_VERSION,
            },
            "source_snapshot": snapshot,
            "foundation": {
                "used": False,
                "contract_version": None,
                "fingerprint": None,
                "sections": [],
            },
            "parameters": {
                "persistence_depth": depth,
                "max_depth": max_depth,
            },
            "coverage": {
                "coverage_status": "partial" if diagnostics else "complete",
                "source_file_count": len(files),
                "source_to_storage_lineage_count": counts[
                    "source_to_storage_lineage.json"
                ],
                "storage_to_access_lineage_count": counts[
                    "storage_to_access_lineage.json"
                ],
                "persistent_write_count": counts["persistent_writes.json"],
                "storage_access_count": counts["storage_accesses.json"],
                "lineage_gap_count": counts["storage_lineage_gaps.json"],
                "stored_field_mapping_count": counts[
                    "stored_field_to_response_field_mappings.json"
                ],
                "core_status": status,
            },
            "diagnostics": diagnostics,
            "provenance": {
                "execution_runtime": "core_evidence_runtime/v1",
                "semantic_routing": "artifact_kind_plus_schema_version",
                "source_pipeline": "internal-persistence-lineage-evidence-v1",
            },
            "payload": {
                "repository_identity": {"repo_id": repo_id},
                "artifacts": artifacts,
            },
        }
    )
