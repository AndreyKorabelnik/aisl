from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.pipeline import run_analysis

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "interaction-boundary-evidence"
SCHEMA_VERSION = "interaction-boundary-evidence/v1"
ANALYZER_ID = "interaction-boundary-analyzer"
RELATIVE_PATH = "evidence/interaction-boundary-evidence.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


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
        entries.append({
            "repository_relative_path": _relative(repository, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_size": len(payload),
        })
    material = {"source_id": repo_id, "scope": "interaction_boundary_sources", "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "interaction_boundary_sources",
        "file_count": len(entries),
    }


def _profile() -> dict[str, Any]:
    return {
        "profile_id": "internal-interaction-boundary-evidence-v1",
        "profile_version": 1,
        "name": "Typed HTTP interaction boundary evidence",
        "workspace_types": ["java"],
        "capabilities": ["system.interfaces", "system.interactions"],
        "pipeline": {
            "stages": [
                {"id": "scan_files"},
                {"id": "config_scan"},
                {"id": "maven_dependency_scan"},
                {"id": "gradle_dependency_scan"},
                {"id": "openapi_scan"},
                {"id": "java_structural_scan"},
                {"id": "java_system_interaction_enrichment"},
            ],
            "final_stages": [
                {"id": "core_output"},
                {"id": "normalize_facts"},
                {"id": "compact_package"},
            ],
        },
        "output_contract": {
            "intent": "typed_http_interaction_boundary_evidence",
            "policy": {
                "http_only": True,
                "execution_context_not_requested": True,
                "value_flow_not_requested": True,
                "no_business_decisions": True,
            },
        },
    }


def _normalize_identity(parameters: Mapping[str, Any]) -> dict[str, Any]:
    aliases = parameters.get("service_aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return {
        "system_id": str(parameters.get("system_id") or "").strip() or None,
        "project_id": str(parameters.get("project_id") or "").strip() or None,
        "service_aliases": sorted({str(item).strip() for item in aliases if str(item).strip()}),
    }


def _finalize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    material = {key: deepcopy(value) for key, value in artifact.items() if key not in {"content_fingerprint", "artifact_id"}}
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"interaction_boundary_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_interaction_boundary_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    repository = repository.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    source_snapshot = _source_snapshot(repository, files, repo_id)
    identity = _normalize_identity(parameters)
    payload_root = output_root / "evidence" / "interaction-boundary-payload"
    marker = payload_root / "interaction-boundary-payload-manifest.json"
    expected = {
        "schema_version": "interaction_boundary_payload_manifest/v1",
        "core_version": CORE_VERSION,
        "repo_id": repo_id,
        "source_fingerprint": source_snapshot["fingerprint"],
        "profile_id": "internal-interaction-boundary-evidence-v1",
        "repository_identity": identity,
    }
    if marker.is_file():
        current = json.loads(marker.read_text(encoding="utf-8"))
        if {key: current.get(key) for key in expected} != expected:
            raise ValueError("existing interaction-boundary payload does not match the current evidence request")
    else:
        if payload_root.exists():
            shutil.rmtree(payload_root)
        result = run_analysis(
            repository,
            payload_root,
            project_code=identity["project_id"] or repo_id,
            system_name=identity["system_id"] or repo_id,
            repo_id=repo_id,
            analysis_profile=_profile(),
        )
        marker.write_text(
            json.dumps({
                **expected,
                "coverage": result.coverage or {},
            }, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    source_catalog = payload_root / "compact" / "system_interface_catalog.json"
    catalog = payload_root / "typed" / "interaction_boundary_catalog.json"
    diagnostics: list[dict[str, Any]] = []
    interfaces: list[dict[str, Any]] = []
    if source_catalog.is_file():
        raw = json.loads(source_catalog.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping):
            observed = [dict(item) for item in (raw.get("all_interfaces") or []) if isinstance(item, Mapping)]
            interfaces = [
                item
                for item in observed
                if (str(item.get("direction") or ""), str(item.get("boundary_kind") or ""))
                in {("inbound", "rest_request"), ("outbound", "http_outbound")}
            ]
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text(
                json.dumps({"boundaries": interfaces}, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        diagnostics.append({
            "code": "interaction_boundary_catalog_missing",
            "severity": "warning",
            "message": "system_interface_catalog.json was not produced",
            "source_refs": [],
        })
    relative_path = catalog.resolve().relative_to((output_root / "evidence").resolve()).as_posix() if catalog.is_file() else None
    envelope = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": ANALYZER_ID,
            "analyzer_version": CORE_VERSION,
        },
        "source_snapshot": source_snapshot,
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": identity,
        "coverage": {
            "coverage_status": "partial" if diagnostics else "complete",
            "source_file_count": len(files),
            "boundary_count": len(interfaces),
            "inbound_boundary_count": sum(1 for item in interfaces if str(item.get("direction") or "") == "inbound"),
            "outbound_boundary_count": sum(1 for item in interfaces if str(item.get("direction") or "") == "outbound"),
        },
        "diagnostics": diagnostics,
        "provenance": {
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
            "source_pipeline": "internal-interaction-boundary-evidence-v1",
        },
        "payload": {
            "repository_identity": {"repo_id": repo_id, **identity},
            "boundary_catalog": ({
                "artifact_name": "interaction_boundary_catalog.json",
                "relative_path": relative_path,
                "sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
                "bytes": catalog.stat().st_size,
                "section": "boundaries",
            } if catalog.is_file() else None),
        },
    }
    return _finalize_artifact(envelope)
