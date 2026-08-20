from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.scanners.repo_scanner import is_analyzer_eligible_file

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "repository-structure-evidence"
SCHEMA_VERSION = "repository-structure-evidence/v1"
ANALYZER_ID = "repository-structure-analyzer"
RELATIVE_PATH = "evidence/repository-structure-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, path: Path) -> str:
    try:
        return path.relative_to(repository).as_posix()
    except ValueError:
        return path.name


def _extension(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix else "<none>"


def _finalize(artifact: dict[str, Any]) -> dict[str, Any]:
    material = {key: deepcopy(value) for key, value in artifact.items() if key not in {"content_fingerprint", "artifact_id"}}
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"repository_structure_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_repository_structure_evidence(
    *,
    repository: Path,
    all_files: Iterable[Path],
    repo_id: str,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish concept-agnostic observed repository file/coverage evidence.

    No file contents are interpreted here.  The artifact records the complete Core file
    frontier, content identity and whether a file belongs to the historical analyzer input
    whitelist.  Concepts, novelty and business semantics are deliberately downstream.
    """
    if parameters:
        raise ValueError("repository-structure-evidence/v1 does not accept runtime parameters")
    repository = repository.expanduser().resolve()
    diagnostics: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    extension_counts: Counter[str] = Counter()
    eligible_extension_counts: Counter[str] = Counter()
    unreadable_count = 0
    for path in sorted((Path(item) for item in all_files), key=lambda item: _relative(repository, item)):
        relative = _relative(repository, path)
        extension = _extension(path)
        eligible = is_analyzer_eligible_file(path)
        extension_counts[extension] += 1
        if eligible:
            eligible_extension_counts[extension] += 1
        try:
            payload = path.read_bytes()
            byte_size = len(payload)
            sha256 = hashlib.sha256(payload).hexdigest()
            readable = True
        except OSError as exc:
            byte_size = None
            sha256 = None
            readable = False
            unreadable_count += 1
            diagnostics.append({
                "code": "repository_file_unreadable",
                "severity": "warning",
                "message": f"Repository file could not be read: {relative}",
                "source_refs": [{"repository_relative_path": relative}],
                "details": {"error_type": type(exc).__name__},
            })
        records.append({
            "repository_relative_path": relative,
            "file_name": path.name,
            "extension": extension,
            "byte_size": byte_size,
            "sha256": sha256,
            "readable": readable,
            "is_symlink": path.is_symlink(),
            "analyzer_eligible": eligible,
            "analyzer_frontier_status": "eligible" if eligible else "outside_frontier",
        })

    outside_frontier_extensions = [
        {"extension": extension, "file_count": count, "status": "outside_analyzer_frontier"}
        for extension, count in sorted(extension_counts.items())
        if eligible_extension_counts.get(extension, 0) == 0
    ]
    extension_inventory = [
        {
            "extension": extension,
            "file_count": count,
            "analyzer_eligible_file_count": eligible_extension_counts.get(extension, 0),
            "outside_analyzer_frontier_file_count": count - eligible_extension_counts.get(extension, 0),
        }
        for extension, count in sorted(extension_counts.items())
    ]
    snapshot_material = {
        "source_id": repo_id,
        "scope": "repository_all_files",
        "files": [
            {
                "repository_relative_path": item["repository_relative_path"],
                "sha256": item["sha256"],
                "byte_size": item["byte_size"],
                "readable": item["readable"],
            }
            for item in records
        ],
    }
    snapshot = {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(snapshot_material),
        "scope": "repository_all_files",
        "file_count": len(records),
    }
    coverage_status = "partial" if unreadable_count else "complete"
    eligible_count = sum(1 for item in records if item["analyzer_eligible"])
    return _finalize({
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": snapshot,
        "parameters": {},
        "coverage": {
            "coverage_status": coverage_status,
            "all_file_count": len(records),
            "analyzer_eligible_file_count": eligible_count,
            "outside_analyzer_frontier_file_count": len(records) - eligible_count,
            "extension_family_count": len(extension_inventory),
            "outside_analyzer_frontier_extension_family_count": len(outside_frontier_extensions),
            "unreadable_file_count": unreadable_count,
        },
        "repository_identity": {"repo_id": repo_id},
        "files": records,
        "extension_inventory": extension_inventory,
        "outside_analyzer_frontier_extension_families": outside_frontier_extensions,
        "diagnostics": diagnostics,
        "semantic_policy": {
            "classification": "observed_fact_only",
            "concept_classification_performed": False,
            "novelty_scoring_performed": False,
            "business_meaning_inferred": False,
        },
    })
