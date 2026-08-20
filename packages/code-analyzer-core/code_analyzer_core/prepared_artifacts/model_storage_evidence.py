from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.models import Fact
from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts
from code_analyzer_core.tsa_interpreter import interpret_tsa_facts

CONTRACT_VERSION = "core_evidence_artifact_contract/v1"
ARTIFACT_KIND = "model-storage-evidence"
SCHEMA_VERSION = "model-storage-evidence/v1"
ANALYZER_ID = "java-model-storage-analyzer"
RELATIVE_PATH = "evidence/model-storage-evidence.json"

_REFERENCE_METHODS = {
    "referenceField",
    "referenceCollection",
    "replaceReferenceCollection",
    "replacePolymorphicReferenceCollection",
    "reference",
    "references",
}
_KEY_METHODS = {"key", "setKey", "withKey"}
_ALIAS_METHODS = {"alias", "setAlias", "withAlias"}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relative(repository: Path, value: object) -> str:
    path = Path(str(value or ""))
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except Exception:
        return path.as_posix().lstrip("/") or "unknown"


def _source_refs(repository: Path, fact: Fact) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for ref in fact.evidence:
        row = {
            "repository_relative_path": _relative(repository, ref.file_path),
            "line_start": int(ref.line_start or 1),
            "line_end": int(ref.line_end or ref.line_start or 1),
            "extractor": ref.extractor or "java_tree_sitter",
        }
        key = tuple(row.values())
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda item: (item["repository_relative_path"], item["line_start"], item["line_end"], item["extractor"]))


def _source_snapshot(repository: Path, files: list[Path], repo_id: str) -> dict[str, Any]:
    entries = []
    for path in sorted((p for p in files if p.suffix.lower() == ".java"), key=lambda p: _relative(repository, p)):
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        entries.append({
            "repository_relative_path": _relative(repository, path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_size": len(payload),
        })
    material = {"source_id": repo_id, "scope": "java_model_storage_sources", "files": entries}
    return {
        "source_id": repo_id,
        "revision": None,
        "fingerprint": _fingerprint(material),
        "scope": "java_model_storage_sources",
        "file_count": len(entries),
    }


def _method_names(facts: list[Fact]) -> set[str]:
    return {
        str(fact.properties.get("method") or "")
        for fact in facts
        if fact.fact_type == "java_method_call_observation"
    }


def _applicable(facts: list[Fact]) -> tuple[bool, dict[str, bool]]:
    methods = _method_names(facts)
    signature = {
        "reference_api_observed": bool(methods & _REFERENCE_METHODS),
        "key_api_observed": bool(methods & _KEY_METHODS),
        "alias_api_observed": bool(methods & _ALIAS_METHODS),
    }
    return all(signature.values()), signature


def _record(repository: Path, fact: Fact) -> dict[str, Any]:
    properties = deepcopy(fact.properties or {})
    observation_id = str(properties.get("observation_id") or "")
    return {
        "observation_id": observation_id,
        "observation_kind": properties.get("observation_kind") or properties.get("tsa_observation_kind"),
        "api_framework": properties.get("api_framework") or "tsa_change_vector",
        "properties": properties,
        "source_refs": _source_refs(repository, fact),
    }


def build_model_storage_evidence(
    *,
    repository: Path,
    files: list[Path],
    repo_id: str,
) -> dict[str, Any]:
    """Publish observed model-to-storage identities and reference construction.

    Core reuses universal Java source observations and a framework interpreter.
    The artifact preserves exact expressions and provenance; it does not map
    aliases to SQL/PDM objects, infer PK/FK, normalize physical names, or assign
    business meaning.
    """
    java_files = [item for item in files if item.suffix.lower() == ".java"]
    diagnostics: list[dict[str, Any]] = []
    generic_facts: list[Fact] = []
    source_status: dict[str, Any] = {}
    interpreted: list[Fact] = []
    interpreter_status: dict[str, Any] = {}

    if java_files:
        generic_facts, source_status = build_java_source_observation_facts(java_files)
    applicable, signature = _applicable(generic_facts)
    if applicable:
        interpreted, interpreter_status = interpret_tsa_facts(generic_facts)

    section_types = {
        "storage_records": "storage_record_observation",
        "storage_references": "storage_reference_observation",
        "storage_key_lineage": "tsa_storage_key_lineage_observation",
        "reference_value_derivations": "tsa_reference_value_derivation_observation",
    }
    payload: dict[str, list[dict[str, Any]]] = {}
    for section, fact_type in section_types.items():
        rows = [_record(repository, fact) for fact in interpreted if fact.fact_type == fact_type]
        rows.sort(key=lambda item: (str(item.get("observation_id") or ""), json.dumps(item, sort_keys=True, default=str)))
        payload[section] = rows

    parse_warnings = [str(value) for value in source_status.get("parse_warnings") or [] if str(value)]
    for warning in sorted(set(parse_warnings)):
        diagnostics.append({
            "code": "java_parse_warning",
            "severity": "warning",
            "message": warning,
            "source_refs": [],
        })

    if not java_files or not applicable:
        coverage_status = "not_applicable"
    elif parse_warnings:
        coverage_status = "partial"
    else:
        coverage_status = "complete"

    counts = {f"{section}_count": len(rows) for section, rows in payload.items()}
    coverage = {
        "coverage_status": coverage_status,
        "java_files_discovered": len(java_files),
        "source_observation_count": len(generic_facts),
        "interpreter_observation_count": len(interpreted),
        **signature,
        **counts,
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
        "source_snapshot": _source_snapshot(repository, java_files, repo_id),
        "foundation": {"used": True, "contract_version": "java_source_observations/internal", "fingerprint": None, "sections": ["java_source_observations"]},
        "parameters": {"language": "java", "interpreter": "tsa_change_vector", "record_limit": None},
        "coverage": coverage,
        "diagnostics": diagnostics,
        "provenance": {
            "parser_provider": "tree_sitter",
            "observation_source": "code_analyzer_core.scanners.java_source_observations.build_java_source_observation_facts",
            "framework_interpreter": "code_analyzer_core.tsa_interpreter.interpret_tsa_facts",
            "interpreter_status": interpreter_status,
            "execution_runtime": "core_evidence_runtime/v1",
            "semantic_routing": "artifact_kind_plus_schema_version",
            "inference_policy": "observed_framework_api_bindings_only_no_physical_mapping_or_business_verdict",
        },
        "payload": payload,
    }
    material = {key: deepcopy(value) for key, value in artifact.items() if key not in {"content_fingerprint", "artifact_id"}}
    artifact["content_fingerprint"] = _fingerprint(material)
    artifact["artifact_id"] = f"model_storage_{artifact['content_fingerprint'][:24]}"
    return artifact
