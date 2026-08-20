from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from code_analyzer_core import __version__ as CORE_VERSION

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "structured-file-shape-evidence"
SCHEMA_VERSION = "structured-file-shape-evidence/v1"
ANALYZER_ID = "structured-file-shape-analyzer"
RELATIVE_PATH = "evidence/structured-file-shape-evidence.json"

_SUPPORTED_SYNTAX_BY_EXTENSION = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_DEPTH = 10
_MAX_VISITED_NODES = 50_000
_MAX_SEQUENCE_CHILDREN = 128
_MAX_PATH_OBSERVATIONS = 512
_MAX_STATE_OBSERVATIONS = 512
_MAX_CARDINALITY_OBSERVATIONS = 256


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, path: Path) -> str:
    try:
        return path.relative_to(repository).as_posix()
    except ValueError:
        return path.name


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    return type(value).__name__.lower()


def _state(value: Any) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return "empty" if value == "" else "nonempty"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "zero" if value == 0 else "nonzero"
    if isinstance(value, list):
        return "empty" if not value else "nonempty"
    if isinstance(value, dict):
        return "empty" if not value else "nonempty"
    return None


def _escape_pointer_token(value: str) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _array_bucket(length: int) -> str:
    if length == 0:
        return "0"
    if length == 1:
        return "1"
    if length <= 4:
        return "2-4"
    if length <= 16:
        return "5-16"
    if length <= 64:
        return "17-64"
    return "65+"


def _parse_payload(path: Path, syntax: str) -> Any:
    text = path.read_text(encoding="utf-8")
    if syntax == "json":
        return json.loads(text)
    if syntax == "yaml":
        return yaml.safe_load(text)
    raise ValueError(f"unsupported structured syntax: {syntax}")


def _observe_structure(value: Any) -> dict[str, Any]:
    path_types: Counter[tuple[str, str]] = Counter()
    states: Counter[tuple[str, str, str]] = Counter()
    cardinalities: dict[str, tuple[int, str]] = {}
    counts: Counter[str] = Counter()
    max_depth_seen = 0
    truncated = False
    visited = 0

    def walk(node: Any, pointer: str, depth: int) -> None:
        nonlocal max_depth_seen, truncated, visited
        if truncated:
            return
        if visited >= _MAX_VISITED_NODES:
            truncated = True
            return
        visited += 1
        max_depth_seen = max(max_depth_seen, depth)
        value_type = _value_type(node)
        path_types[(pointer or "/", value_type)] += 1
        counts["node_count"] += 1
        counts[f"{value_type}_count"] += 1
        state = _state(node)
        if state is not None:
            states[(pointer or "/", value_type, state)] += 1
        if depth >= _MAX_DEPTH:
            if isinstance(node, (dict, list)) and node:
                truncated = True
            return
        if isinstance(node, dict):
            for key in sorted(node, key=lambda item: str(item)):
                child_pointer = (pointer + "/" if pointer else "/") + _escape_pointer_token(str(key))
                walk(node[key], child_pointer, depth + 1)
                if truncated:
                    break
        elif isinstance(node, list):
            cardinalities[pointer or "/"] = (len(node), _array_bucket(len(node)))
            for child in node[:_MAX_SEQUENCE_CHILDREN]:
                child_pointer = (pointer or "") + "/*"
                walk(child, child_pointer or "/*", depth + 1)
                if truncated:
                    break
            if len(node) > _MAX_SEQUENCE_CHILDREN:
                truncated = True

    walk(value, "", 0)
    path_rows = [
        {"path": path, "value_type": value_type, "occurrence_count": count}
        for (path, value_type), count in sorted(path_types.items(), key=lambda item: (item[0][0], item[0][1]))[:_MAX_PATH_OBSERVATIONS]
    ]
    state_rows = [
        {"path": path, "value_type": value_type, "state": state, "occurrence_count": count}
        for (path, value_type, state), count in sorted(states.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))[:_MAX_STATE_OBSERVATIONS]
    ]
    cardinality_rows = [
        {"path": path, "length": length, "bucket": bucket}
        for path, (length, bucket) in sorted(cardinalities.items())[:_MAX_CARDINALITY_OBSERVATIONS]
    ]
    shape_material = {
        "root_type": _value_type(value),
        "path_types": [(row["path"], row["value_type"]) for row in path_rows],
    }
    variant_material = {
        "shape_signature": _fingerprint(shape_material),
        "states": [(row["path"], row["value_type"], row["state"]) for row in state_rows],
        "cardinality_buckets": [(row["path"], row["bucket"]) for row in cardinality_rows],
    }
    return {
        "root_type": _value_type(value),
        "structure_signature": _fingerprint(shape_material),
        "variant_signature": _fingerprint(variant_material),
        "structural_size": {
            "node_count": int(counts.get("node_count", 0)),
            "object_count": int(counts.get("object_count", 0)),
            "array_count": int(counts.get("array_count", 0)),
            "scalar_count": int(sum(counts.get(f"{kind}_count", 0) for kind in ("string", "number", "boolean", "null"))),
            "max_depth": max_depth_seen,
            "path_type_count": len(path_rows),
            "max_array_length": max((row["length"] for row in cardinality_rows), default=0),
        },
        "path_observations": path_rows,
        "state_observations": state_rows,
        "cardinality_observations": cardinality_rows,
        "observation_truncated": truncated,
    }


def _finalize(artifact: dict[str, Any]) -> dict[str, Any]:
    material = {key: deepcopy(value) for key, value in artifact.items() if key not in {"content_fingerprint", "artifact_id"}}
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"structured_file_shape_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_structured_file_shape_evidence(
    *,
    repository: Path,
    all_files: Iterable[Path],
    repo_id: str,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish bounded concept-agnostic structural observations for supported structured files.

    The analyzer records only source structure, scalar *types* and bounded structural states
    such as boolean/null/empty/non-empty. It never exports arbitrary scalar values or
    interprets business semantics. Unsupported syntaxes remain outside this evidence family.
    """
    if parameters:
        raise ValueError("structured-file-shape-evidence/v1 does not accept runtime parameters")
    repository = repository.expanduser().resolve()
    diagnostics: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    candidate_count = parsed_count = failed_count = skipped_large_count = 0

    for path in sorted((Path(item) for item in all_files), key=lambda item: _relative(repository, item)):
        syntax = _SUPPORTED_SYNTAX_BY_EXTENSION.get(path.suffix.lower())
        if not syntax:
            continue
        candidate_count += 1
        relative = _relative(repository, path)
        try:
            byte_size = path.stat().st_size
        except OSError as exc:
            failed_count += 1
            diagnostics.append({
                "code": "structured_file_stat_failed",
                "severity": "warning",
                "message": f"Structured file metadata could not be read: {relative}",
                "source_refs": [{"repository_relative_path": relative}],
                "details": {"error_type": type(exc).__name__},
            })
            continue
        if byte_size > _MAX_FILE_BYTES:
            skipped_large_count += 1
            diagnostics.append({
                "code": "structured_file_shape_limit_exceeded",
                "severity": "info",
                "message": f"Structured file exceeds bounded shape-analysis size limit: {relative}",
                "source_refs": [{"repository_relative_path": relative}],
                "details": {"byte_size": byte_size, "max_file_bytes": _MAX_FILE_BYTES},
            })
            continue
        try:
            raw_bytes = path.read_bytes()
            value = _parse_payload(path, syntax)
            observations = _observe_structure(value)
        except Exception as exc:
            failed_count += 1
            diagnostics.append({
                "code": "structured_file_parse_failed",
                "severity": "warning",
                "message": f"Supported structured file could not be parsed: {relative}",
                "source_refs": [{"repository_relative_path": relative}],
                "details": {"syntax": syntax, "error_type": type(exc).__name__},
            })
            continue
        parsed_count += 1
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        member_id = f"structured_member_{_fingerprint({'repo_id': repo_id, 'path': relative, 'sha256': source_sha256})[:24]}"
        members.append({
            "member_id": member_id,
            "repository_relative_path": relative,
            "content_identity": {"sha256": source_sha256, "byte_size": len(raw_bytes)},
            "syntax": syntax,
            "parse_status": "parsed",
            **observations,
            "provenance": {"repository_relative_path": relative, "source_sha256": source_sha256},
        })

    coverage_status = "complete" if failed_count == 0 and skipped_large_count == 0 else "partial"
    snapshot_material = {
        "source_id": repo_id,
        "scope": "supported_structured_files",
        "members": [
            {"repository_relative_path": item["repository_relative_path"], "sha256": item["content_identity"]["sha256"]}
            for item in members
        ],
        "candidate_count": candidate_count,
        "failed_count": failed_count,
        "skipped_large_count": skipped_large_count,
    }
    return _finalize({
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": {
            "source_id": repo_id,
            "revision": None,
            "fingerprint": _fingerprint(snapshot_material),
            "scope": "supported_structured_files",
            "file_count": candidate_count,
        },
        "parameters": {},
        "coverage": {
            "coverage_status": coverage_status,
            "candidate_file_count": candidate_count,
            "parsed_file_count": parsed_count,
            "parse_failed_file_count": failed_count,
            "bounded_skip_file_count": skipped_large_count,
            "member_count": len(members),
            "supported_syntaxes": sorted(set(_SUPPORTED_SYNTAX_BY_EXTENSION.values())),
        },
        "repository_identity": {"repo_id": repo_id},
        "members": members,
        "diagnostics": diagnostics,
        "observation_policy": {
            "classification": "observed_structural_fact_only",
            "arbitrary_scalar_values_exported": False,
            "boolean_null_empty_states_exported": True,
            "business_meaning_inferred": False,
            "family_membership_inferred": False,
            "limits": {
                "max_file_bytes": _MAX_FILE_BYTES,
                "max_depth": _MAX_DEPTH,
                "max_visited_nodes": _MAX_VISITED_NODES,
                "max_sequence_children": _MAX_SEQUENCE_CHILDREN,
                "max_path_observations": _MAX_PATH_OBSERVATIONS,
            },
        },
    })
