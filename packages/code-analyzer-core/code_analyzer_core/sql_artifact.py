from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SQL_ANALYSIS_CONTRACT_VERSION = "1.0"
SQL_ANALYSIS_SCHEMA_VERSION = "sql-analysis/v1"

SQL_CANONICAL_FACTS: tuple[tuple[str, str], ...] = (
    ("sql_statement", "sql_statement_id"),
    ("sql_script_statement", "sql_script_statement_id"),
    ("sql_script_call", "sql_script_call_id"),
    ("sql_script_binding", "sql_script_binding_id"),
    ("sql_script_embedded_sql", "sql_script_embedded_sql_id"),
    ("sql_script_invocation", "sql_script_invocation_id"),
    ("sql_semantic_placeholder", "sql_semantic_placeholder_id"),
    ("sql_workflow_binding", "sql_workflow_binding_id"),
    ("sql_select_scope", "sql_select_scope_id"),
    ("sql_relation", "sql_relation_id"),
    ("sql_column_usage", "sql_column_usage_id"),
    ("sql_projection", "sql_projection_id"),
    ("sql_write_target", "sql_write_target_id"),
    ("sql_target_projection_binding", "sql_target_projection_binding_id"),
    ("sql_join_edge", "sql_join_edge_id"),
    ("sql_direct_column_lineage", "sql_direct_column_lineage_id"),
    ("sql_recursive_column_lineage", "sql_recursive_column_lineage_id"),
    ("sql_object_dependency", "sql_object_dependency_id"),
    ("sql_scoped_lineage_gap", "sql_scoped_lineage_gap_id"),
)


def sql_analysis_content_fingerprint(shards: list[dict[str, Any]], coverage_sha256: str) -> str:
    content_input = "\n".join(
        f"{item['fact_type']}:{item['record_count']}:{item['sha256']}" for item in shards
    ) + f"\ncoverage:{coverage_sha256}"
    return hashlib.sha256(content_input.encode("utf-8")).hexdigest()


def _safe_child(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
        return candidate
    except Exception:
        return None


def _nonportable_locations(value: Any, path: str = "$.") -> list[str]:
    issues: list[str] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_nonportable_locations(item, f"{path}[{index}]."))
        return issues
    if not isinstance(value, dict):
        return issues
    for key, item in value.items():
        location = f"{path}{key}"
        if key in {"absolute_file", "repo_path", "analysis_out", "static_analysis_output"}:
            issues.append(location)
        if key == "file" and isinstance(item, str) and Path(item).is_absolute():
            issues.append(location)
        issues.extend(_nonportable_locations(item, f"{location}."))
    return issues


def validate_sql_analysis_artifact(manifest_path: str | Path) -> dict[str, Any]:
    """Validate a sql-analysis/v1 artifact without loading whole shards into memory."""
    path = Path(manifest_path)
    root = path.parent
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    shard_results: list[dict[str, Any]] = []

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "valid": False,
            "schema_version": None,
            "content_fingerprint": None,
            "errors": [{"code": "manifest_unreadable", "message": str(exc)}],
            "warnings": [],
            "facts": [],
        }

    if manifest.get("artifact") != "sql_analysis":
        errors.append({"code": "artifact_type_invalid", "actual": manifest.get("artifact")})
    if manifest.get("contract_version") != SQL_ANALYSIS_CONTRACT_VERSION:
        errors.append({"code": "contract_version_unsupported", "actual": manifest.get("contract_version")})
    if manifest.get("schema_version") != SQL_ANALYSIS_SCHEMA_VERSION:
        errors.append({"code": "schema_version_unsupported", "actual": manifest.get("schema_version")})

    entries = manifest.get("facts") if isinstance(manifest.get("facts"), list) else []
    expected = list(SQL_CANONICAL_FACTS)
    actual_pairs = [(str(item.get("fact_type") or ""), str(item.get("id_field") or "")) for item in entries]
    if actual_pairs != expected:
        errors.append({"code": "fact_contract_mismatch", "expected": expected, "actual": actual_pairs})

    for entry in entries:
        fact_type = str(entry.get("fact_type") or "")
        id_field = str(entry.get("id_field") or "")
        relative = str(entry.get("path") or "")
        shard_path = _safe_child(root, relative)
        result = {
            "fact_type": fact_type,
            "path": relative,
            "record_count": 0,
            "sha256": None,
            "byte_size": None,
            "unique_id_count": 0,
        }
        if shard_path is None:
            errors.append({"code": "fact_path_unsafe", "fact_type": fact_type, "path": relative})
            shard_results.append(result)
            continue
        if not shard_path.is_file():
            errors.append({"code": "fact_shard_missing", "fact_type": fact_type, "path": relative})
            shard_results.append(result)
            continue

        digest = hashlib.sha256()
        ids: set[str] = set()
        record_count = 0
        byte_size = 0
        try:
            with shard_path.open("rb") as handle:
                for line_number, line in enumerate(handle, 1):
                    digest.update(line)
                    byte_size += len(line)
                    if not line.strip():
                        errors.append({"code": "empty_jsonl_line", "fact_type": fact_type, "line": line_number})
                        continue
                    try:
                        record = json.loads(line)
                    except Exception as exc:
                        errors.append({"code": "jsonl_record_invalid", "fact_type": fact_type, "line": line_number, "message": str(exc)})
                        continue
                    record_count += 1
                    if not isinstance(record, dict):
                        errors.append({"code": "jsonl_record_not_object", "fact_type": fact_type, "line": line_number})
                        continue
                    record_id = str(record.get(id_field) or "")
                    if not record_id:
                        errors.append({"code": "fact_id_missing", "fact_type": fact_type, "line": line_number, "id_field": id_field})
                    elif record_id in ids:
                        errors.append({"code": "fact_id_duplicate", "fact_type": fact_type, "line": line_number, "fact_id": record_id})
                    else:
                        ids.add(record_id)
                    portable_issues = _nonportable_locations(record)
                    if portable_issues:
                        errors.append({"code": "nonportable_evidence", "fact_type": fact_type, "line": line_number, "locations": portable_issues[:20]})
        except Exception as exc:
            errors.append({"code": "fact_shard_unreadable", "fact_type": fact_type, "message": str(exc)})

        actual_sha = digest.hexdigest()
        result.update({
            "record_count": record_count,
            "sha256": actual_sha,
            "byte_size": byte_size,
            "unique_id_count": len(ids),
        })
        if record_count != int(entry.get("record_count") or 0):
            errors.append({"code": "fact_count_mismatch", "fact_type": fact_type, "expected": entry.get("record_count"), "actual": record_count})
        if actual_sha != entry.get("sha256"):
            errors.append({"code": "fact_sha256_mismatch", "fact_type": fact_type, "expected": entry.get("sha256"), "actual": actual_sha})
        if byte_size != int(entry.get("byte_size") or 0):
            errors.append({"code": "fact_size_mismatch", "fact_type": fact_type, "expected": entry.get("byte_size"), "actual": byte_size})
        shard_results.append(result)

    coverage_entry = manifest.get("coverage") if isinstance(manifest.get("coverage"), dict) else {}
    coverage_path = _safe_child(root, str(coverage_entry.get("path") or ""))
    coverage_sha = ""
    if coverage_path is None or not coverage_path.is_file():
        errors.append({"code": "coverage_missing", "path": coverage_entry.get("path")})
    else:
        payload = coverage_path.read_bytes()
        coverage_sha = hashlib.sha256(payload).hexdigest()
        if coverage_sha != coverage_entry.get("sha256"):
            errors.append({"code": "coverage_sha256_mismatch", "expected": coverage_entry.get("sha256"), "actual": coverage_sha})
        if len(payload) != int(coverage_entry.get("byte_size") or 0):
            errors.append({"code": "coverage_size_mismatch", "expected": coverage_entry.get("byte_size"), "actual": len(payload)})
        try:
            coverage = json.loads(payload)
            if coverage.get("schema_version") != SQL_ANALYSIS_SCHEMA_VERSION:
                errors.append({"code": "coverage_schema_version_invalid", "actual": coverage.get("schema_version")})
        except Exception as exc:
            errors.append({"code": "coverage_invalid", "message": str(exc)})

    if coverage_sha:
        recalculated = sql_analysis_content_fingerprint(entries, coverage_sha)
        if recalculated != manifest.get("content_fingerprint"):
            errors.append({"code": "content_fingerprint_mismatch", "expected": manifest.get("content_fingerprint"), "actual": recalculated})

    if manifest.get("analysis_status") == "partial" and not errors:
        warnings.append({"code": "analysis_partial", "message": "Artifact is structurally valid but contains partial analysis coverage."})

    return {
        "valid": not errors,
        "schema_version": manifest.get("schema_version"),
        "content_fingerprint": manifest.get("content_fingerprint"),
        "analysis_status": manifest.get("analysis_status"),
        "errors": errors,
        "warnings": warnings,
        "facts": shard_results,
    }
