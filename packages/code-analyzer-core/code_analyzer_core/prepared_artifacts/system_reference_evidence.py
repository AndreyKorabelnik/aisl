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

SYSTEM_DESCRIPTION_ARTIFACT_KIND = "system-description-evidence"
SYSTEM_DESCRIPTION_SCHEMA_VERSION = "system-description-evidence/v1"
SYSTEM_DESCRIPTION_ANALYZER_ID = "system-description-analyzer"
SYSTEM_DESCRIPTION_RELATIVE_PATH = "evidence/system-description-evidence.json"

REFERENCE_DATA_ARTIFACT_KIND = "reference-data-evidence"
REFERENCE_DATA_SCHEMA_VERSION = "reference-data-evidence/v1"
REFERENCE_DATA_ANALYZER_ID = "reference-data-analyzer"
REFERENCE_DATA_RELATIVE_PATH = "evidence/reference-data-evidence.json"


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


def _source_snapshot(
    repository: Path,
    files: Iterable[Path],
    repo_id: str,
    *,
    scope: str,
) -> dict[str, Any]:
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
    material = {"source_id": repo_id, "scope": scope, "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": scope,
        "file_count": len(entries),
    }



def _system_description_profile() -> dict[str, Any]:
    """Dedicated lightweight observed-fact pipeline for system-description evidence.

    System description needs repository composition, interfaces, interaction evidence,
    coarse scenarios and observed storage usage. It must not depend on deep persistence
    lineage or declared-value extraction, which belong to separate knowledge families.
    """
    return {
        "profile_id": "internal-system-description-evidence-v1",
        "profile_version": 1,
        "name": "Typed system-description evidence",
        "workspace_types": ["java"],
        "capabilities": ["system.description"],
        "pipeline": {
            "stages": [
                {"id": "scan_files"},
                {"id": "config_scan"},
                {"id": "maven_dependency_scan"},
                {"id": "gradle_dependency_scan"},
                {"id": "openapi_scan"},
                {"id": "java_structural_scan"},
                {"id": "java_source_observation_build", "options": {"framework_interpreters": []}},
                {"id": "java_system_interaction_enrichment"},
                {"id": "sql_scan"},
                {"id": "db_schema_scan"},
                {"id": "java_data_flow_build"},
                {"id": "java_traceability_build"},
                {"id": "java_table_observation_build"},
                {"id": "system_description_enrichment"},
            ],
            "final_stages": [
                {"id": "core_output"},
                {"id": "normalize_facts"},
                {"id": "compact_package"},
            ],
        },
        "output_contract": {
            "intent": "typed_system_description_evidence",
            "policy": {
                "observed_facts_only": True,
                "no_business_decisions": True,
                "deep_persistence_not_requested": True,
                "declared_values_not_requested": True,
            },
        },
    }


def _ensure_system_description_payload(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    payload_root = output_root.expanduser().resolve() / "evidence" / "system-description-payload"
    marker = payload_root / "system-description-payload-manifest.json"
    source_snapshot = _source_snapshot(repository, files, repo_id, scope="system_description_sources")
    expected = {
        "schema_version": "system_description_payload_manifest/v1",
        "core_version": CORE_VERSION,
        "repo_id": repo_id,
        "source_fingerprint": source_snapshot["fingerprint"],
        "profile_id": "internal-system-description-evidence-v1",
    }
    if marker.is_file():
        current = json.loads(marker.read_text(encoding="utf-8"))
        identity = {key: current.get(key) for key in expected}
        if identity != expected:
            raise ValueError("existing system-description payload does not match the current evidence request")
        return payload_root, current
    if payload_root.exists():
        shutil.rmtree(payload_root)
    result = run_analysis(
        repository,
        payload_root,
        project_code=repo_id,
        system_name=repo_id,
        repo_id=repo_id,
        analysis_profile=_system_description_profile(),
    )
    manifest = {
        **expected,
        "coverage": result.coverage or {},
        "source_snapshot": source_snapshot,
    }
    marker.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload_root, manifest

def _reference_data_profile() -> dict[str, Any]:
    """Dedicated observed-fact pipeline for reference-data evidence.

    Reference-data/NSI assessment needs declared values plus observed storage, join,
    lineage, ingress and external-dependency context. Those are source-grounded facts
    produced inside this analyzer; KLC/LLM owns semantic classification.
    """
    return {
        "profile_id": "internal-reference-data-evidence-v1",
        "profile_version": 1,
        "name": "Typed reference-data evidence",
        "workspace_types": ["java"],
        "analysis_parameters": {"persistence_depth": "deep"},
        "capabilities": ["reference-data.declared-values"],
        "pipeline": {
            "stages": [
                {"id": "scan_files"},
                {"id": "config_scan"},
                {"id": "maven_dependency_scan"},
                {"id": "gradle_dependency_scan"},
                {"id": "openapi_scan"},
                {"id": "java_structural_scan"},
                {"id": "java_source_observation_build", "options": {"framework_interpreters": []}},
                {"id": "java_system_interaction_enrichment"},
                {"id": "sql_scan"},
                {"id": "db_schema_scan"},
                {"id": "java_data_flow_build"},
                {"id": "java_traceability_build"},
                {
                    "id": "java_persistence_lineage_build",
                    "options": {
                        "max_depth": 7,
                        "deep": True,
                        "suspend_automatic_gc": True,
                        "progress_interval": 25,
                    },
                },
                {"id": "java_data_model_lineage_build", "options": {"max_depth": 4}},
                {"id": "java_table_observation_build"},
                {"id": "declared_value_scan"},
                {"id": "declared_value_summary_scan"},
                {"id": "system_description_enrichment"},
                {"id": "reference_data_fact_base"},
            ],
            "final_stages": [
                {"id": "core_output"},
                {"id": "normalize_facts"},
                {"id": "compact_package"},
            ],
        },
        "output_contract": {
            "intent": "typed_reference_data_evidence",
            "policy": {
                "observed_facts_only": True,
                "no_business_decisions": True,
            },
        },
    }


def _ensure_reference_data_payload(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    payload_root = output_root.expanduser().resolve() / "evidence" / "reference-data-payload"
    marker = payload_root / "reference-data-payload-manifest.json"
    source_snapshot = _source_snapshot(repository, files, repo_id, scope="reference_data_sources")
    expected = {
        "schema_version": "reference_data_payload_manifest/v1",
        "core_version": CORE_VERSION,
        "repo_id": repo_id,
        "source_fingerprint": source_snapshot["fingerprint"],
        "profile_id": "internal-reference-data-evidence-v1",
    }
    if marker.is_file():
        current = json.loads(marker.read_text(encoding="utf-8"))
        identity = {key: current.get(key) for key in expected}
        if identity != expected:
            raise ValueError("existing reference-data payload does not match the current evidence request")
        return payload_root, current
    if payload_root.exists():
        shutil.rmtree(payload_root)
    result = run_analysis(
        repository,
        payload_root,
        project_code=repo_id,
        system_name=repo_id,
        repo_id=repo_id,
        analysis_profile=_reference_data_profile(),
    )
    manifest = {
        **expected,
        "coverage": result.coverage or {},
        "source_snapshot": source_snapshot,
    }
    marker.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload_root, manifest


def _file_descriptor(payload_root: Path, path: Path, *, artifact_name: str, sections: list[str] | None) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "artifact_name": artifact_name,
        "relative_path": path.resolve().relative_to(payload_root.parent.resolve()).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "sections": list(sections or []),
    }


def _coverage_status(result_coverage: Mapping[str, Any], diagnostics: list[dict[str, Any]]) -> str:
    explicit = str((result_coverage.get("evidence_coverage") or {}).get("coverage_status") or "").strip()
    if explicit in {"complete", "partial", "not_applicable"}:
        return explicit
    if diagnostics:
        return "partial"
    return "complete"


def _finalize_artifact(artifact: dict[str, Any], *, prefix: str) -> dict[str, Any]:
    material = {
        key: deepcopy(value)
        for key, value in artifact.items()
        if key not in {"content_fingerprint", "artifact_id"}
    }
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"{prefix}_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_system_description_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
) -> dict[str, Any]:
    repository = repository.expanduser().resolve()
    payload_root, payload_manifest = _ensure_system_description_payload(
        repository=repository,
        files=files,
        repo_id=repo_id,
        output_root=output_root,
    )
    compact = payload_root / "compact"
    specifications = (
        ("system_interface_catalog.json", ["all_interfaces"]),
        ("system_scenarios.json", None),
        ("scenario_storage_summaries.json", None),
        ("storage_usage_summaries.json", None),
        ("external_dependencies.json", None),
        ("access_boundaries.json", None),
        ("data_sources.json", None),
    )
    artifacts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for artifact_name, sections in specifications:
        path = compact / artifact_name
        if not path.is_file():
            diagnostics.append(
                {
                    "code": "system_description_payload_missing",
                    "severity": "warning",
                    "message": f"Expected compact artifact was not produced: {artifact_name}",
                    "source_refs": [],
                }
            )
            continue
        artifacts.append(
            _file_descriptor(payload_root, path, artifact_name=artifact_name, sections=sections)
        )
    coverage = {
        "coverage_status": _coverage_status(payload_manifest.get("coverage") or {}, diagnostics),
        "source_file_count": len(files),
        "payload_artifact_count": len(artifacts),
        "expected_payload_artifact_count": len(specifications),
        "missing_payload_artifact_count": len(specifications) - len(artifacts),
    }
    return _finalize_artifact(
        {
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": SYSTEM_DESCRIPTION_ARTIFACT_KIND,
            "schema_version": SYSTEM_DESCRIPTION_SCHEMA_VERSION,
            "producer": {
                "component": "code-analyzer-core",
                "analyzer_id": SYSTEM_DESCRIPTION_ANALYZER_ID,
                "analyzer_version": CORE_VERSION,
            },
            "source_snapshot": _source_snapshot(
                repository,
                files,
                repo_id,
                scope="system_description_sources",
            ),
            "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
            "parameters": {},
            "coverage": coverage,
            "diagnostics": diagnostics,
            "provenance": {
                "execution_runtime": "core_evidence_runtime/v1",
                "semantic_routing": "artifact_kind_plus_schema_version",
                "source_pipeline": "internal-system-description-evidence-v1",
            },
            "payload": {"artifacts": artifacts},
        },
        prefix="system_description",
    )


def build_reference_data_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
) -> dict[str, Any]:
    repository = repository.expanduser().resolve()
    payload_root, payload_manifest = _ensure_reference_data_payload(
        repository=repository,
        files=files,
        repo_id=repo_id,
        output_root=output_root,
    )
    compact = payload_root / "compact"
    manifest_path = compact / "reference_data_fact_base_manifest.json"
    diagnostics: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_sections = manifest.get("section_index") or manifest.get("sections") or []
        if isinstance(raw_sections, Mapping):
            raw_sections = [dict(value, section=name) for name, value in raw_sections.items()]
        for raw in raw_sections if isinstance(raw_sections, list) else []:
            if not isinstance(raw, Mapping):
                continue
            relative = str(raw.get("relative_path") or "").strip()
            if not relative:
                continue
            path = compact / relative
            if not path.is_file():
                diagnostics.append(
                    {
                        "code": "reference_data_section_missing",
                        "severity": "warning",
                        "message": f"Reference-data section file is missing: {relative}",
                        "source_refs": [],
                    }
                )
                continue
            payload = path.read_bytes()
            sections.append(
                {
                    "section": str(raw.get("section") or raw.get("name") or path.stem),
                    "relative_path": path.resolve().relative_to(payload_root.parent.resolve()).as_posix(),
                    "records_count": int(raw.get("records_count") or 0),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                    "format": str(raw.get("format") or "jsonl"),
                }
            )
    else:
        diagnostics.append(
            {
                "code": "reference_data_manifest_missing",
                "severity": "warning",
                "message": "reference_data_fact_base_manifest.json was not produced",
                "source_refs": [],
            }
        )
    coverage = {
        "coverage_status": _coverage_status(payload_manifest.get("coverage") or {}, diagnostics),
        "source_file_count": len(files),
        "section_count": len(sections),
        "record_count": sum(int(item.get("records_count") or 0) for item in sections),
        "missing_section_count": sum(1 for item in diagnostics if item.get("code") == "reference_data_section_missing"),
    }
    return _finalize_artifact(
        {
            "contract_version": CONTRACT_VERSION,
            "artifact_kind": REFERENCE_DATA_ARTIFACT_KIND,
            "schema_version": REFERENCE_DATA_SCHEMA_VERSION,
            "producer": {
                "component": "code-analyzer-core",
                "analyzer_id": REFERENCE_DATA_ANALYZER_ID,
                "analyzer_version": CORE_VERSION,
            },
            "source_snapshot": _source_snapshot(
                repository,
                files,
                repo_id,
                scope="reference_data_sources",
            ),
            "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
            "parameters": {},
            "coverage": coverage,
            "diagnostics": diagnostics,
            "provenance": {
                "execution_runtime": "core_evidence_runtime/v1",
                "semantic_routing": "artifact_kind_plus_schema_version",
                "source_pipeline": "internal-reference-data-evidence-v1",
                "classification_policy": "observed_facts_only",
            },
            "payload": {"sections": sections},
        },
        prefix="reference_data",
    )
