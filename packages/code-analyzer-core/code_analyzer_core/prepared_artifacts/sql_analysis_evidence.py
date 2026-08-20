from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.sql_profile import _build_repo_artifacts, _write_sql_analysis_artifact
from code_analyzer_core.sql_artifact import validate_sql_analysis_artifact

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "sql-analysis"
SCHEMA_VERSION = "sql-analysis/v1"
ANALYZER_ID = "sql-analysis-analyzer"
RELATIVE_PATH = "evidence/sql-analysis-evidence.json"
CANONICAL_MANIFEST_RELATIVE_PATH = "sql-analysis/manifest.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except Exception:
        return path.as_posix().lstrip("/")


def _source_snapshot(repository: Path, files: list[Path], repo_id: str) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in sorted(files, key=lambda item: _relative(repository, item)):
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        entries.append({
            "repository_relative_path": _relative(repository, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_size": len(payload),
        })
    material = {"source_id": repo_id, "scope": "sql_analysis_sources", "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "sql_analysis_sources",
        "file_count": len(entries),
    }


def build_sql_analysis_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the existing SQL analyzer behind the generic Core evidence runtime.

    The canonical sql-analysis/v1 shards are retained, but their manifest is
    referenced by a generic evidence envelope. Task, Suite and Core Profile
    identifiers are not part of the execution or semantic contract.
    """
    params = dict(parameters or {})
    allowed = {"project_code", "system_name"}
    unsupported = sorted(set(params) - allowed)
    if unsupported:
        raise ValueError("sql-analysis/v1 unsupported runtime parameters: " + ", ".join(unsupported))
    project_code = str(params.get("project_code") or "UNKNOWN")
    system_name = str(params.get("system_name") or repo_id)
    started_at = datetime.now(timezone.utc).isoformat()
    artifacts = _build_repo_artifacts(repository, repo_id, project_code, system_name, files)
    artifacts.setdefault("repository", {})["analysis_profile"] = None
    artifacts.setdefault("repository", {})["analysis_profile_source"] = None
    evidence_root = output_root / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest = _write_sql_analysis_artifact(evidence_root, artifacts, started_at)
    manifest_path = evidence_root / CANONICAL_MANIFEST_RELATIVE_PATH
    validation = validate_sql_analysis_artifact(manifest_path)
    if not validation.get("valid"):
        raise ValueError(f"generated sql-analysis/v1 artifact is invalid: {validation.get('errors')}")
    coverage = json.loads((manifest_path.parent / str((manifest.get("coverage") or {}).get("path"))).read_text(encoding="utf-8"))
    diagnostics: list[dict[str, Any]] = []
    if str(manifest.get("analysis_status") or "") == "partial":
        diagnostics.append({
            "code": "sql_analysis_partial",
            "severity": "warning",
            "message": "SQL analysis published partial coverage; localized resolution statuses and gaps are preserved.",
            "source_refs": [],
        })
    envelope: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": _source_snapshot(repository, files, repo_id),
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {"project_code": project_code, "system_name": system_name},
        "coverage": {
            "coverage_status": "partial" if manifest.get("analysis_status") == "partial" else "complete",
            "sql_files_scanned": int((coverage.get("source_inventory") or {}).get("files_scanned") or 0),
            "sql_unit_count": int((coverage.get("source_inventory") or {}).get("sql_units") or 0),
            "sql_statement_count": int((coverage.get("source_inventory") or {}).get("sql_statements") or 0),
            "lineage_gap_count": int((coverage.get("gaps") or {}).get("total") or 0),
        },
        "diagnostics": diagnostics,
        "provenance": {
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
            "canonical_payload_contract": "sql-analysis/v1-jsonl-shards",
        },
        "payload": {
            "canonical_manifest_path": CANONICAL_MANIFEST_RELATIVE_PATH,
            "canonical_content_fingerprint": manifest.get("content_fingerprint"),
            "analysis_status": manifest.get("analysis_status"),
            "fact_shards": [
                {
                    "fact_type": item.get("fact_type"),
                    "id_field": item.get("id_field"),
                    "path": str(Path("sql-analysis") / str(item.get("path"))),
                    "record_count": item.get("record_count"),
                    "sha256": item.get("sha256"),
                    "byte_size": item.get("byte_size"),
                }
                for item in manifest.get("facts") or []
            ],
            "coverage_path": str(Path("sql-analysis") / str((manifest.get("coverage") or {}).get("path"))),
        },
    }
    material = {key: deepcopy(value) for key, value in envelope.items() if key not in {"content_fingerprint", "artifact_id"}}
    envelope["content_fingerprint"] = _fingerprint(material)
    envelope["artifact_id"] = f"sql_analysis_{envelope['content_fingerprint'][:24]}"
    return envelope
