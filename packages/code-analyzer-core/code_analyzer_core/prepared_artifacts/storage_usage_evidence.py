from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.scanners.java_call_observations import (
    _build_method_index,
    _build_storage_facts,
)

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "storage-usage-evidence"
SCHEMA_VERSION = "storage-usage-evidence/v1"
ANALYZER_ID = "java-storage-usage-analyzer"
RELATIVE_PATH = "evidence/storage-usage-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\u001f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _relative(repository: Path, value: object) -> str:
    path = Path(str(value or ""))
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except Exception:
        return path.as_posix().lstrip("/") or "unknown"


def _source_ref(repository: Path, access: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repository_relative_path": _relative(repository, access.get("file")),
        "line_start": int(access.get("line_start") or 1),
        "line_end": int(access.get("line_end") or access.get("line_start") or 1),
        "extractor": "java_tree_sitter_storage_call",
    }


def _source_snapshot(repository: Path, files: list[Path], repo_id: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted((item for item in files if item.suffix.lower() == ".java"), key=lambda p: _relative(repository, p)):
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        entries.append({
            "repository_relative_path": _relative(repository, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_size": len(payload),
        })
    material = {"source_id": repo_id, "scope": "java_storage_usage_sources", "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "java_storage_usage_sources",
        "file_count": len(entries),
    }


def build_storage_usage_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
) -> dict[str, Any]:
    """Publish observed Java storage reads/writes without model inference.

    The analyzer reuses Core-owned Tree-sitter storage-call observations. It
    records exact call, receiver, declared type, operation and source location.
    It does not infer physical tables from repository names, apply naming
    similarity, or claim field-level lineage when the call does not expose it.
    """
    java_files = [item for item in files if item.suffix.lower() == ".java"]
    methods, _class_fields, _class_infos, parse_warnings = _build_method_index(java_files)
    raw_accesses = _build_storage_facts(methods)

    accesses: list[dict[str, Any]] = []
    reads: list[dict[str, Any]] = []
    writes: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for warning in sorted({str(item) for item in parse_warnings if str(item)}):
        diagnostics.append({
            "code": "java_parse_warning",
            "severity": "warning",
            "message": warning,
            "source_refs": [],
        })

    for index, raw in enumerate(sorted(raw_accesses, key=lambda item: (
        _relative(repository, item.get("file")),
        int(item.get("line_start") or 0),
        str(item.get("operation") or ""),
        str(item.get("storage_method") or ""),
        str(item.get("storage_access_id") or ""),
    )), 1):
        source_ref = _source_ref(repository, raw)
        target = str(raw.get("table_or_repository") or "").strip() or None
        resolution_status = str(raw.get("storage_resolution_status") or "unknown")
        resolution_level = str(raw.get("storage_resolution_level") or "unresolved")
        access_id = _stable_id(
            "storage_access",
            repo_id,
            source_ref["repository_relative_path"],
            source_ref["line_start"],
            raw.get("operation"),
            raw.get("receiver_expression"),
            raw.get("storage_method"),
            raw.get("access_kind"),
            target,
        )
        record = {
            "storage_access_id": access_id,
            "repo_id": repo_id,
            "operation": raw.get("operation"),
            "operation_signature": raw.get("operation_signature"),
            "class_name": raw.get("class_name"),
            "method_name": raw.get("method_name"),
            "access_kind": raw.get("access_kind"),
            "operation_kind": raw.get("operation_kind"),
            "write_kind": raw.get("write_kind"),
            "mutation_kind": raw.get("mutation_kind"),
            "storage_kind": raw.get("storage_kind") or "repository_or_storage_api",
            "storage_target_expression": target,
            "target_resolution_level": resolution_level,
            "target_resolution_status": resolution_status,
            "receiver_expression": raw.get("receiver_expression"),
            "receiver_declared_type": raw.get("receiver_declared_type"),
            "storage_method": raw.get("storage_method"),
            "payload_expression": raw.get("payload_expression"),
            "payload_role": raw.get("payload_role"),
            "writes_new_payload": bool(raw.get("writes_new_payload")),
            "selected_fields": sorted({str(value) for value in (raw.get("selected_fields") or []) if str(value)}),
            "selected_field_refs": sorted({str(value) for value in (raw.get("selected_field_refs") or []) if str(value)}),
            "result_type": raw.get("result_type") or raw.get("payload_type"),
            "sql_preview": raw.get("sql_preview"),
            "source_ref": source_ref,
        }
        accesses.append(record)

        if record["access_kind"] == "read":
            reads.append({
                "storage_read_id": _stable_id("storage_read", access_id),
                "storage_access_id": access_id,
                "repo_id": repo_id,
                "operation": record["operation"],
                "storage_target_expression": target,
                "storage_kind": record["storage_kind"],
                "storage_method": record["storage_method"],
                "selected_fields": record["selected_fields"],
                "result_type": record["result_type"],
                "target_resolution_status": resolution_status,
                "source_ref": source_ref,
            })
        elif record["access_kind"] in {"write", "mutation"}:
            writes.append({
                "storage_write_id": _stable_id("storage_write", access_id),
                "storage_access_id": access_id,
                "repo_id": repo_id,
                "operation": record["operation"],
                "storage_target_expression": target,
                "storage_kind": record["storage_kind"],
                "storage_method": record["storage_method"],
                "write_kind": record["write_kind"],
                "mutation_kind": record["mutation_kind"],
                "payload_expression": record["payload_expression"],
                "payload_role": record["payload_role"],
                "writes_new_payload": record["writes_new_payload"],
                "target_resolution_status": resolution_status,
                "source_ref": source_ref,
            })

        unresolved = (
            not target
            or resolution_level in {"unresolved", "custom_dao_boundary"}
            or resolution_status in {"unknown", "dao_implementation_not_resolved"}
        )
        if unresolved:
            gap_code = "storage_target_not_resolved" if not target else "storage_implementation_not_resolved"
            gaps.append({
                "storage_usage_gap_id": _stable_id("storage_usage_gap", access_id, gap_code),
                "gap_code": gap_code,
                "severity": "warning",
                "owner_kind": "storage_access",
                "owner_id": access_id,
                "message": (
                    "Storage target is not present in the observed call."
                    if not target
                    else "Storage boundary is observed but its implementation or physical target is not resolved."
                ),
                "details": {
                    "target_expression": target,
                    "target_resolution_level": resolution_level,
                    "target_resolution_status": resolution_status,
                },
                "source_refs": [source_ref],
            })

    for collection in (accesses, reads, writes, gaps):
        collection.sort(key=lambda item: tuple(str(item.get(key) or "") for key in sorted(item)))

    snapshot = _source_snapshot(repository, java_files, repo_id)
    if not java_files:
        coverage_status = "not_applicable"
    elif parse_warnings or gaps:
        coverage_status = "partial"
    else:
        coverage_status = "complete"
    coverage = {
        "coverage_status": coverage_status,
        "java_files_discovered": len(java_files),
        "java_methods_indexed": len(methods),
        "storage_access_count": len(accesses),
        "storage_read_count": len(reads),
        "storage_write_count": len(writes),
        "storage_gap_count": len(gaps),
        "access_kind_counts": dict(sorted(Counter(str(item.get("access_kind") or "unknown") for item in accesses).items())),
        "storage_kind_counts": dict(sorted(Counter(str(item.get("storage_kind") or "unknown") for item in accesses).items())),
    }
    artifact: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": snapshot,
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {"language": "java", "include_test_sources": True, "record_limit": None},
        "coverage": coverage,
        "diagnostics": diagnostics,
        "provenance": {
            "parser_provider": "tree_sitter",
            "observation_source": "code_analyzer_core.scanners.java_call_observations._build_storage_facts",
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
            "inference_policy": "observed_calls_only_no_physical_name_guessing",
        },
        "payload": {
            "storage_accesses": accesses,
            "storage_reads": reads,
            "storage_writes": writes,
            "storage_usage_gaps": gaps,
        },
    }
    material = {key: deepcopy(value) for key, value in artifact.items() if key not in {"content_fingerprint", "artifact_id"}}
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"storage_usage_{artifact['content_fingerprint'][:24]}"
    return artifact
