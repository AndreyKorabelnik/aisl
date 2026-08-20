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
ARTIFACT_KIND = "data-model-candidate-evidence"
SCHEMA_VERSION = "data-model-candidate-evidence/v1"
ANALYZER_ID = "data-model-candidate-analyzer"
RELATIVE_PATH = "evidence/data-model-candidate-evidence.json"


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
        entries.append({
            "repository_relative_path": _relative(repository, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_size": len(payload),
        })
    material = {"source_id": repo_id, "scope": "data_model_candidate_sources", "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "data_model_candidate_sources",
        "file_count": len(entries),
    }


def _profile() -> dict[str, Any]:
    return {
        "profile_id": "internal-data-model-candidate-evidence-v1",
        "profile_version": 1,
        "name": "Typed data model candidate evidence",
        "workspace_types": ["java"],
        "capabilities": ["data-model.candidate-discovery"],
        "pipeline": {
            "stages": [
                {"id": "scan_files"},
                {"id": "maven_dependency_scan"},
                {"id": "gradle_dependency_scan"},
                {"id": "java_structural_scan"},
                {"id": "java_data_model_candidate_scan"},
            ],
            "final_stages": [
                {"id": "core_output"},
                {"id": "normalize_facts"},
                {"id": "compact_package"},
            ],
        },
        "output_contract": {
            "intent": "typed_data_model_candidate_evidence",
            "policy": {
                "full_data_model_analysis_not_requested": True,
                "no_business_decisions": True,
            },
        },
    }


def _finalize(artifact: dict[str, Any]) -> dict[str, Any]:
    material = {
        key: deepcopy(value)
        for key, value in artifact.items()
        if key not in {"content_fingerprint", "artifact_id"}
    }
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"data_model_candidate_{artifact['content_fingerprint'][:24]}"
    return artifact


def build_data_model_candidate_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
    output_root: Path,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        raise ValueError("data-model-candidate-evidence/v1 does not accept runtime parameters")

    repository = repository.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    snapshot = _source_snapshot(repository, files, repo_id)
    payload_root = output_root / "evidence" / "data-model-candidate-payload"
    marker = payload_root / "data-model-candidate-payload-manifest.json"
    expected = {
        "schema_version": "data_model_candidate_payload_manifest/v1",
        "core_version": CORE_VERSION,
        "repo_id": repo_id,
        "source_fingerprint": snapshot["fingerprint"],
        "analyzer_id": ANALYZER_ID,
    }
    if marker.is_file():
        current = json.loads(marker.read_text(encoding="utf-8"))
        if {key: current.get(key) for key in expected} != expected:
            raise ValueError("existing data-model candidate payload does not match the current evidence request")
    else:
        if payload_root.exists():
            shutil.rmtree(payload_root)
        result = run_analysis(
            repository,
            payload_root,
            project_code=repo_id,
            system_name=repo_id,
            repo_id=repo_id,
            analysis_profile=_profile(),
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
            ) + "\n",
            encoding="utf-8",
        )

    profile_path = payload_root / "compact" / "data_model_candidate_profile.json"
    if not profile_path.is_file():
        raise ValueError("Core did not publish compact/data_model_candidate_profile.json")
    candidate = json.loads(profile_path.read_text(encoding="utf-8"))
    if candidate.get("schema_version") != "data_model_candidate_profile/v1":
        raise ValueError(f"unsupported candidate profile schema: {candidate.get('schema_version')!r}")
    candidate["producer"] = {
        "component": "code-analyzer-core",
        "analyzer_id": ANALYZER_ID,
        "analyzer_version": CORE_VERSION,
    }

    coverage = dict(candidate.get("coverage") or {})
    diagnostics = [
        {
            "code": "data_model_candidate_scan_partial",
            "severity": "warning",
            "message": "Candidate scan completed with partial parser coverage",
            "source_refs": [],
        }
    ] if coverage.get("status") == "partial" else []

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
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {},
        "coverage": {
            "coverage_status": str(coverage.get("status") or "partial"),
            "source_file_count": len(files),
            "candidate_status": candidate.get("candidate_status"),
            "score": int(candidate.get("score") or 0),
            "evidence_count": len(candidate.get("evidence") or []),
            "full_data_model_analysis_performed": False,
        },
        "repository_identity": {"repo_id": repo_id},
        "candidate_profile": candidate,
        "diagnostics": diagnostics,
        "semantic_policy": {
            "decision_owner": "user",
        },
    })
