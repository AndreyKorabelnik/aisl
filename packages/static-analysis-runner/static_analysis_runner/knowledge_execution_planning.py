from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io_utils import read_json, sha256_file, stable_fingerprint
from .knowledge_planning import resolve_knowledge_profile, validate_knowledge_catalog
from .runtime_support import repository_revision
from .version import __version__

KNOWLEDGE_INPUT_INVENTORY_SCHEMA_VERSION = "knowledge_input_inventory/v1"
KNOWLEDGE_EXECUTION_PLAN_SCHEMA_VERSION = "knowledge_execution_plan/v1"
SUPPORTED_CORE_EVIDENCE_CATALOG_SCHEMA = "core_evidence_contract_catalog/v1"
SUPPORTED_MATERIALIZATION_CATALOG_SCHEMA = "knowledge_materialization_catalog/v3"
SUPPORTED_REPOSITORY_RUN_MANIFEST_SCHEMA = "static_repository_analysis_run_manifest/v1"
SUPPORTED_CORE_ARTIFACT_CONTRACT = "core_evidence_artifact_contract/v1"

_IGNORED_DIRECTORIES = {
    ".git", ".gradle", ".idea", "__pycache__", "build", "dist", "node_modules", "out", "target"
}
_LANGUAGE_BY_SUFFIX = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".py": "python",
    ".sql": "sql",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".properties": "properties",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_fingerprinted_payload(
    payload: Mapping[str, Any],
    *,
    schema_version: str,
    fingerprint_field: str,
    label: str,
) -> None:
    actual_schema = str(payload.get("schema_version") or "")
    if actual_schema != schema_version:
        raise ValueError(f"unsupported {label} schema: {actual_schema!r}; expected {schema_version!r}")
    actual_fingerprint = str(payload.get(fingerprint_field) or "")
    if not actual_fingerprint:
        raise ValueError(f"{label} has no {fingerprint_field}")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != fingerprint_field}
    if actual_fingerprint != _fingerprint(material):
        raise ValueError(f"{label} fingerprint does not match canonical content")


def _validate_core_catalog(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        schema_version=SUPPORTED_CORE_EVIDENCE_CATALOG_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="Core evidence contract catalog",
    )
    if str(payload.get("artifact_envelope_contract") or "") != SUPPORTED_CORE_ARTIFACT_CONTRACT:
        raise ValueError(f"Core evidence catalog is missing {SUPPORTED_CORE_ARTIFACT_CONTRACT}")


def _validate_materialization_catalog(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        schema_version=SUPPORTED_MATERIALIZATION_CATALOG_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="KLC materialization catalog",
    )
    runtime = payload.get("runtime_contract") or {}
    if str(runtime.get("contract_id") or "") != "knowledge_materialization_runtime/v1":
        raise ValueError("KLC materialization catalog is missing knowledge_materialization_runtime/v1")


def _contracts_by_evidence_identity(payload: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in payload.get("contracts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core evidence catalog contains a non-object contract")
        item = deepcopy(dict(raw))
        key = (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
        if not all(key) or key in result:
            raise ValueError(f"invalid or duplicate Core evidence contract identity: {key}")
        result[key] = item
    return result


def _materializations_by_id(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    values = payload.get("materializations") or []
    if not isinstance(values, list):
        raise ValueError("KLC materialization catalog field 'materializations' must be a list")
    for raw in values:
        if not isinstance(raw, Mapping):
            raise ValueError("KLC materialization entry must be an object")
        item = deepcopy(dict(raw))
        materialization_id = str(item.get("materialization_id") or "")
        if not materialization_id or materialization_id in result:
            raise ValueError(f"invalid or duplicate materialization_id: {materialization_id!r}")
        result[materialization_id] = item
    return result


def _scan_source_landscape(repository: Path) -> tuple[list[str], list[str], int]:
    """Observe generic source facts used by owner-provided applicability predicates."""
    languages: set[str] = set()
    extensions: set[str] = set()
    file_count = 0
    for current, directories, names in os.walk(repository, topdown=True, followlinks=False):
        directories[:] = sorted(item for item in directories if item not in _IGNORED_DIRECTORIES)
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            file_count += 1
            suffix = path.suffix.lower()
            if suffix:
                extensions.add(suffix)
            language = _LANGUAGE_BY_SUFFIX.get(suffix)
            if language:
                languages.add(language)
    return sorted(languages), sorted(extensions), file_count


def inspect_repository_source(repository: str | Path, *, source_id: str | None = None) -> dict[str, Any]:
    path = Path(repository).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"repository source is not a directory: {path}")
    resolved_source_id = str(source_id or path.name).strip()
    if not resolved_source_id:
        raise ValueError("repository source_id is empty")
    languages, extensions, file_count = _scan_source_landscape(path)
    revision = repository_revision(path)
    snapshot_fingerprint = stable_fingerprint({
        "source_id": resolved_source_id,
        "revision": revision,
        "languages": languages,
        "extensions": extensions,
        "file_count": file_count,
    })
    return {
        "snapshot_id": f"source_snapshot_{snapshot_fingerprint[:24]}",
        "source_kind": "repository",
        "source_id": resolved_source_id,
        "availability": "available",
        "languages": languages,
        "extensions": extensions,
        "file_count": file_count,
        "revision": revision,
        "location": {"kind": "directory", "path": str(path)},
        "snapshot_fingerprint": snapshot_fingerprint,
    }


def _normalize_location(raw: Mapping[str, Any], *, base: Path | None = None) -> dict[str, Any]:
    location = deepcopy(dict(raw.get("location") or {}))
    path_value = str(
        location.get("path")
        or location.get("manifest_path")
        or location.get("output_path")
        or raw.get("path")
        or ""
    ).strip()
    if path_value:
        candidate = Path(path_value)
        if base is not None and not candidate.is_absolute():
            candidate = (base / candidate).resolve()
        else:
            candidate = candidate.expanduser().resolve()
        location["path"] = str(candidate)
        location.setdefault("kind", "file")
        location["exists"] = candidate.exists()
        if candidate.is_file():
            location.setdefault("sha256", sha256_file(candidate))
            location.setdefault("bytes", candidate.stat().st_size)
    else:
        location.setdefault("kind", "unresolved")
        location["exists"] = False
    return location


def _normalize_typed_artifact(raw: Mapping[str, Any], *, base: Path | None = None) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    artifact_kind = str(item.get("artifact_kind") or "").strip()
    schema_version = str(item.get("schema_version") or "").strip()
    if not artifact_kind or not schema_version:
        raise ValueError("typed artifact must define artifact_kind and schema_version")
    location = _normalize_location(item, base=base)
    status = str(item.get("status") or "completed")
    # A partial Core result is still a valid typed artifact: its diagnostics and
    # coverage describe the known gaps, while the observed facts remain usable.
    # KLC already accepts completed/partial evidence; inventory reuse must not
    # silently drop the artifact and thereby omit an entire repository.
    available = bool(location.get("exists", True)) and status in {"completed", "partial"}
    artifact_id = str(item.get("artifact_id") or "").strip()
    if not artifact_id:
        artifact_id = f"input_artifact_{stable_fingerprint({'kind': artifact_kind, 'version': schema_version, 'location': location})[:24]}"
    normalized = {
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "schema_version": schema_version,
        "contract_version": item.get("contract_version"),
        "content_fingerprint": item.get("content_fingerprint"),
        "availability": "available" if available else "unavailable",
        "status": status,
        "producer_kind": str(item.get("producer_kind") or "external_or_previous_execution"),
        "scope_id": item.get("scope_id"),
        "location": location,
        "registration_manifest_path": item.get("registration_manifest_path"),
        "coverage": deepcopy(item.get("coverage") or {}),
        "diagnostics": deepcopy(item.get("diagnostics") or {}),
        "provenance": deepcopy(item.get("provenance") or {}),
    }
    source_metadata = item.get("source_metadata") or {}
    if isinstance(source_metadata, Mapping) and source_metadata:
        normalized["source_metadata"] = deepcopy(dict(source_metadata))
    return normalized


def _normalize_knowledge_artifact(raw: Mapping[str, Any], *, base: Path | None = None) -> dict[str, Any]:
    item = deepcopy(dict(raw))
    model_kind = str(item.get("model_kind") or "").strip()
    schema_version = str(item.get("schema_version") or "").strip()
    source_materialization_id = str(item.get("source_materialization_id") or item.get("materialization_id") or "").strip()
    if not model_kind or not schema_version or not source_materialization_id:
        raise ValueError("knowledge artifact must define model_kind, schema_version and source_materialization_id")
    location = _normalize_location(item, base=base)
    available = bool(location.get("exists", True)) and str(item.get("status") or "completed") == "completed"
    artifact_id = str(item.get("artifact_id") or "").strip()
    if not artifact_id:
        artifact_id = f"input_knowledge_{stable_fingerprint({'kind': model_kind, 'version': schema_version, 'source': source_materialization_id, 'location': location})[:24]}"
    return {
        "artifact_id": artifact_id,
        "model_kind": model_kind,
        "schema_version": schema_version,
        "source_materialization_id": source_materialization_id,
        "content_fingerprint": item.get("content_fingerprint"),
        "availability": "available" if available else "unavailable",
        "status": str(item.get("status") or ("completed" if available else "unavailable")),
        "scope_id": item.get("scope_id"),
        "location": location,
        "materialization_result_path": item.get("materialization_result_path"),
        "provenance": deepcopy(item.get("provenance") or {}),
    }


def artifacts_from_repository_run_manifest(path: str | Path) -> list[dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve()
    payload = read_json(manifest_path)
    if str(payload.get("schema_version") or "") != SUPPORTED_REPOSITORY_RUN_MANIFEST_SCHEMA:
        raise ValueError(f"unsupported repository run manifest schema: {payload.get('schema_version')!r}")
    result: list[dict[str, Any]] = []
    for raw in payload.get("evidence_artifacts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("repository run manifest contains a non-object evidence artifact")
        item = dict(raw)
        item["registration_manifest_path"] = str(manifest_path)
        result.append(_normalize_typed_artifact(item, base=manifest_path.parent))
    return result


def knowledge_from_materialization_result(path: str | Path) -> list[dict[str, Any]]:
    result_path = Path(path).expanduser().resolve()
    payload = read_json(result_path)
    result: list[dict[str, Any]] = []
    for raw in payload.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("materialization result contains a non-object knowledge artifact")
        item = dict(raw)
        item.setdefault("source_materialization_id", payload.get("materialization_id"))
        item["materialization_result_path"] = str(result_path)
        result.append(_normalize_knowledge_artifact(item, base=result_path.parent))
    return result


def build_knowledge_input_inventory(
    *,
    scope_kind: str,
    scope_id: str,
    source_snapshots: Sequence[Mapping[str, Any]],
    core_evidence_catalog: Mapping[str, Any],
    materialization_catalog: Mapping[str, Any],
    typed_artifacts: Sequence[Mapping[str, Any]] = (),
    knowledge_artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    _validate_core_catalog(core_evidence_catalog)
    _validate_materialization_catalog(materialization_catalog)
    resolved_scope_kind = str(scope_kind).strip()
    resolved_scope_id = str(scope_id).strip()
    if resolved_scope_kind not in {"repository", "workspace", "portfolio"}:
        raise ValueError(f"unsupported scope kind: {resolved_scope_kind!r}")
    if not resolved_scope_id:
        raise ValueError("scope_id is required")

    normalized_sources: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    for raw in source_snapshots:
        item = deepcopy(dict(raw))
        source_id = str(item.get("source_id") or "").strip()
        if not source_id or source_id in seen_source_ids:
            raise ValueError(f"invalid or duplicate source_id: {source_id!r}")
        seen_source_ids.add(source_id)
        item.setdefault("source_kind", "repository")
        item.setdefault("availability", "available")
        item.setdefault("languages", [])
        item.setdefault("extensions", None)
        item.setdefault("snapshot_id", f"source_snapshot_{stable_fingerprint(item)[:24]}")
        item.setdefault("snapshot_fingerprint", stable_fingerprint({k: v for k, v in item.items() if k != "snapshot_fingerprint"}))
        normalized_sources.append(item)

    normalized_artifacts = [_normalize_typed_artifact(item) for item in typed_artifacts]
    normalized_knowledge = [_normalize_knowledge_artifact(item) for item in knowledge_artifacts]
    evidence_contracts = _contracts_by_evidence_identity(core_evidence_catalog)
    materializations = _materializations_by_id(materialization_catalog)

    producer_contracts: list[dict[str, Any]] = []
    for (artifact_kind, schema_version), contract in sorted(evidence_contracts.items()):
        runtime = contract.get("runtime_publication") or {}
        producer = contract.get("producer") or {}
        registration_status = str(runtime.get("registration_status") or "")
        producer_contracts.append({
            "artifact_kind": artifact_kind,
            "schema_version": schema_version,
            "contract_known": True,
            "producer_kind": "core",
            "producer_registered": registration_status == "registered",
            "analyzer_id": runtime.get("producer_analyzer_id") or producer.get("target_analyzer_id"),
            "source_language": producer.get("source_language"),
            "foundation_requirements": sorted(str(value) for value in producer.get("required_foundation_sections") or []),
            "runtime_contract_id": runtime.get("runtime_contract_id"),
            "preflight_planning": deepcopy(contract.get("preflight_planning") or {}),
            "contract_fingerprint": contract.get("contract_fingerprint"),
        })

    materialization_registrations: list[dict[str, Any]] = []
    for materialization_id, contract in sorted(materializations.items()):
        runtime = (contract.get("current_implementation") or {}).get("runtime") or {}
        materialization_registrations.append({
            "materialization_id": materialization_id,
            "contract_known": True,
            "runtime_registered": runtime.get("registered") is True,
            "handler_id": runtime.get("handler_id"),
            "runtime_contract_id": runtime.get("contract_id"),
            "lifecycle": contract.get("lifecycle"),
            "catalog_section": contract.get("catalog_section"),
        })

    diagnostics: list[dict[str, Any]] = []
    if not normalized_sources:
        diagnostics.append({
            "diagnostic_id": "no_source_snapshots",
            "severity": "info",
            "effect": "Core-produced evidence cannot be planned unless an equivalent typed artifact is already available.",
        })
    unavailable_inputs = [
        item.get("artifact_id") for item in [*normalized_artifacts, *normalized_knowledge]
        if item.get("availability") != "available"
    ]
    if unavailable_inputs:
        diagnostics.append({
            "diagnostic_id": "declared_inputs_unavailable",
            "severity": "warning",
            "artifact_ids": sorted(str(value) for value in unavailable_inputs),
            "effect": "Unavailable inputs remain visible and cannot satisfy required execution-plan dependencies.",
        })

    payload: dict[str, Any] = {
        "schema_version": KNOWLEDGE_INPUT_INVENTORY_SCHEMA_VERSION,
        "producer": {"component": "static-analysis-runner", "version": __version__},
        "scope": {"kind": resolved_scope_kind, "scope_id": resolved_scope_id},
        "source_snapshots": sorted(normalized_sources, key=lambda value: str(value.get("source_id") or "")),
        "typed_artifacts": sorted(normalized_artifacts, key=lambda value: (value["artifact_kind"], value["schema_version"], value["artifact_id"])),
        "knowledge_artifacts": sorted(normalized_knowledge, key=lambda value: (value["model_kind"], value["schema_version"], value["artifact_id"])),
        "producer_catalog": {
            "core_evidence_contract_catalog": {
                "schema_version": core_evidence_catalog.get("schema_version"),
                "catalog_fingerprint": core_evidence_catalog.get("catalog_fingerprint"),
                "contracts": producer_contracts,
            },
            "knowledge_materialization_catalog": {
                "schema_version": materialization_catalog.get("schema_version"),
                "catalog_fingerprint": materialization_catalog.get("catalog_fingerprint"),
                "materializations": materialization_registrations,
            },
        },
        "availability_policy": {
            "contract_presence_is_not_input_availability": True,
            "producer_registration_is_not_source_availability": True,
            "missing_required_input": "blocking_diagnostic_no_fallback",
        },
        "summary": {
            "source_snapshot_count": len(normalized_sources),
            "available_typed_artifact_count": sum(item["availability"] == "available" for item in normalized_artifacts),
            "available_knowledge_artifact_count": sum(item["availability"] == "available" for item in normalized_knowledge),
            "registered_core_producer_count": sum(item["producer_registered"] for item in producer_contracts),
            "registered_materialization_count": sum(item["runtime_registered"] for item in materialization_registrations),
        },
        "diagnostics": diagnostics,
    }
    payload["inventory_fingerprint"] = _fingerprint(payload)
    return payload


def validate_knowledge_input_inventory(payload: Mapping[str, Any]) -> dict[str, Any]:
    _validate_fingerprinted_payload(
        payload,
        schema_version=KNOWLEDGE_INPUT_INVENTORY_SCHEMA_VERSION,
        fingerprint_field="inventory_fingerprint",
        label="knowledge input inventory",
    )
    scope = payload.get("scope") or {}
    if str(scope.get("kind") or "") not in {"repository", "workspace", "portfolio"}:
        raise ValueError("knowledge input inventory has invalid scope.kind")
    if not str(scope.get("scope_id") or ""):
        raise ValueError("knowledge input inventory has no scope_id")

    seen_source_ids: set[str] = set()
    seen_snapshot_ids: set[str] = set()
    for raw in payload.get("source_snapshots") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("knowledge input inventory contains a non-object source snapshot")
        source_id = str(raw.get("source_id") or "")
        snapshot_id = str(raw.get("snapshot_id") or "")
        if not source_id or source_id in seen_source_ids:
            raise ValueError(f"invalid or duplicate inventory source_id: {source_id!r}")
        if not snapshot_id or snapshot_id in seen_snapshot_ids:
            raise ValueError(f"invalid or duplicate inventory snapshot_id: {snapshot_id!r}")
        seen_source_ids.add(source_id)
        seen_snapshot_ids.add(snapshot_id)

    seen_artifact_ids: set[str] = set()
    for collection_name in ("typed_artifacts", "knowledge_artifacts"):
        for raw in payload.get(collection_name) or []:
            if not isinstance(raw, Mapping):
                raise ValueError(f"knowledge input inventory contains a non-object item in {collection_name}")
            artifact_id = str(raw.get("artifact_id") or "")
            if not artifact_id or artifact_id in seen_artifact_ids:
                raise ValueError(f"invalid or duplicate inventory artifact_id: {artifact_id!r}")
            seen_artifact_ids.add(artifact_id)
            if raw.get("availability") == "available" and not bool((raw.get("location") or {}).get("exists")):
                raise ValueError(f"available inventory artifact {artifact_id!r} has no existing location")

    summary = payload.get("summary") or {}
    expected_summary = {
        "source_snapshot_count": len(payload.get("source_snapshots") or []),
        "available_typed_artifact_count": sum(
            isinstance(item, Mapping) and item.get("availability") == "available"
            for item in payload.get("typed_artifacts") or []
        ),
        "available_knowledge_artifact_count": sum(
            isinstance(item, Mapping) and item.get("availability") == "available"
            for item in payload.get("knowledge_artifacts") or []
        ),
    }
    for key, expected in expected_summary.items():
        if int(summary.get(key, -1)) != expected:
            raise ValueError(f"knowledge input inventory summary field {key!r} is inconsistent")
    return deepcopy(dict(payload))


def _available_evidence(inventory: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in inventory.get("typed_artifacts") or []:
        if not isinstance(raw, Mapping) or raw.get("availability") != "available":
            continue
        key = (str(raw.get("artifact_kind") or ""), str(raw.get("schema_version") or ""))
        result.setdefault(key, []).append(deepcopy(dict(raw)))
    return result


def _available_knowledge(inventory: Mapping[str, Any]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for raw in inventory.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping) or raw.get("availability") != "available":
            continue
        key = (
            str(raw.get("model_kind") or ""),
            str(raw.get("schema_version") or ""),
            str(raw.get("source_materialization_id") or ""),
        )
        result.setdefault(key, []).append(deepcopy(dict(raw)))
    return result


def _evaluate_core_applicability(contract: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate only the Core-owned declarative predicate against observed source facts.

    Runner does not infer concepts or inspect analyzer implementation.  Missing predicate
    formalization or missing source-landscape dimensions remains unresolved and cannot hard-skip.
    """
    planning = contract.get("preflight_planning") or {}
    applicability = planning.get("applicability") or {}
    result: dict[str, Any] = {
        "status": "unresolved",
        "basis": applicability.get("basis") or "unknown",
        "contract_status": applicability.get("status") or "not_formalized",
        "source_id": source.get("source_id"),
        "required_languages_any_of": sorted(str(value) for value in applicability.get("required_languages_any_of") or []),
        "required_extensions_any_of": sorted(str(value).lower() for value in applicability.get("required_extensions_any_of") or []),
        "observed_languages": sorted(str(value) for value in source.get("languages") or []),
        "observed_extensions": (
            sorted(str(value).lower() for value in source.get("extensions") or [])
            if isinstance(source.get("extensions"), list)
            else None
        ),
    }
    if applicability.get("status") != "formalized":
        result["reason"] = "core_applicability_not_formalized"
        return result
    if applicability.get("basis") != "observed_source_landscape":
        result["reason"] = "unsupported_applicability_basis"
        return result

    required_languages = set(result["required_languages_any_of"])
    required_extensions = set(result["required_extensions_any_of"])
    languages_raw = source.get("languages")
    extensions_raw = source.get("extensions")
    if required_languages and not isinstance(languages_raw, list):
        result["reason"] = "source_language_landscape_unresolved"
        return result
    if required_extensions and not isinstance(extensions_raw, list):
        result["reason"] = "source_extension_landscape_unresolved"
        return result

    observed_languages = set(result["observed_languages"])
    observed_extensions = set(result["observed_extensions"] or [])
    failed_dimensions: list[str] = []
    if required_languages and not required_languages.intersection(observed_languages):
        failed_dimensions.append("required_languages_any_of")
    if required_extensions and not required_extensions.intersection(observed_extensions):
        failed_dimensions.append("required_extensions_any_of")
    if failed_dimensions:
        result["status"] = "not_applicable"
        result["reason"] = "observed_source_landscape_does_not_match_core_predicate"
        result["failed_dimensions"] = failed_dimensions
        return result

    result["status"] = "applicable"
    result["reason"] = "observed_source_landscape_matches_core_predicate"
    return result


def _topological_order(nodes_by_id: Mapping[str, Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> list[str]:
    nodes = set(nodes_by_id)
    incoming = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}

    # Core evidence production is a single execution phase that precedes KLC
    # materialization.  The graph may contain independent ready materializations
    # (for example, an external typed-artifact input), so lexical node ordering
    # is insufficient: it can interleave KLC execution between Core analyzers.
    # This priority is semantic only by generic node kind and never by evidence
    # family, knowledge_id or materialization_id.
    phase_priority = {
        "source_snapshot": 0,
        "typed_evidence_artifact": 0,
        "knowledge_artifact": 0,
        "core_evidence_analyzer": 1,
        "knowledge_materialization": 3,
    }

    def ready_key(node_id: str) -> tuple[int, str]:
        node_kind = str((nodes_by_id.get(node_id) or {}).get("node_kind") or "")
        # Planned evidence/knowledge nodes are unlocked only by their producers;
        # keeping them before materializations lets their dependency edges become
        # ready without breaking the Core-before-KLC phase boundary.
        if node_kind == "typed_evidence_artifact" and (nodes_by_id.get(node_id) or {}).get("satisfaction_mode") == "planned_core_output":
            return (2, node_id)
        if node_kind == "knowledge_artifact" and (nodes_by_id.get(node_id) or {}).get("satisfaction_mode") == "planned_materialization_output":
            return (4, node_id)
        return (phase_priority.get(node_kind, 2), node_id)
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source not in nodes or target not in nodes or source == target:
            continue
        if target not in outgoing[source]:
            outgoing[source].add(target)
            incoming[target] += 1
    ready = sorted((node_id for node_id, count in incoming.items() if count == 0), key=ready_key)
    result: list[str] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for target in sorted(outgoing[current]):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort(key=ready_key)
    if len(result) != len(nodes):
        unresolved = sorted(nodes - set(result))
        raise ValueError(f"knowledge execution graph contains a cycle: {unresolved}")
    return result


def compile_knowledge_execution_plan(
    *,
    knowledge_catalog: Mapping[str, Any],
    knowledge_profile: Mapping[str, Any],
    input_inventory: Mapping[str, Any],
    core_evidence_catalog: Mapping[str, Any],
    materialization_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    validate_knowledge_catalog(knowledge_catalog)
    inventory = validate_knowledge_input_inventory(input_inventory)
    _validate_core_catalog(core_evidence_catalog)
    _validate_materialization_catalog(materialization_catalog)

    inventory_catalogs = inventory.get("producer_catalog") or {}
    inventory_core = inventory_catalogs.get("core_evidence_contract_catalog") or {}
    inventory_klc = inventory_catalogs.get("knowledge_materialization_catalog") or {}
    if str(inventory_core.get("catalog_fingerprint") or "") != str(core_evidence_catalog.get("catalog_fingerprint") or ""):
        raise ValueError("knowledge input inventory Core evidence catalog fingerprint does not match the supplied catalog")
    if str(inventory_klc.get("catalog_fingerprint") or "") != str(materialization_catalog.get("catalog_fingerprint") or ""):
        raise ValueError("knowledge input inventory KLC materialization catalog fingerprint does not match the supplied catalog")

    catalog_source = knowledge_catalog.get("source") or {}
    if str(catalog_source.get("core_evidence_contract_catalog_fingerprint") or "") != str(core_evidence_catalog.get("catalog_fingerprint") or ""):
        raise ValueError("knowledge catalog Core evidence fingerprint does not match the supplied catalog")
    if str(catalog_source.get("klc_materialization_catalog_fingerprint") or "") != str(materialization_catalog.get("catalog_fingerprint") or ""):
        raise ValueError("knowledge catalog KLC materialization fingerprint does not match the supplied catalog")

    resolution_plan = resolve_knowledge_profile(knowledge_catalog, knowledge_profile)

    profile_scope = (resolution_plan.get("profile") or {}).get("scope") or {}
    inventory_scope = inventory.get("scope") or {}
    if (
        str(profile_scope.get("kind") or "") != str(inventory_scope.get("kind") or "")
        or str(profile_scope.get("scope_id") or "") != str(inventory_scope.get("scope_id") or "")
    ):
        raise ValueError("knowledge profile scope does not match knowledge input inventory scope")

    core_contracts = _contracts_by_evidence_identity(core_evidence_catalog)
    materialization_contracts = _materializations_by_id(materialization_catalog)
    existing_evidence = _available_evidence(inventory)
    existing_knowledge = _available_knowledge(inventory)
    sources = [
        deepcopy(dict(item)) for item in inventory.get("source_snapshots") or []
        if isinstance(item, Mapping) and item.get("availability") == "available"
    ]

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    evidence_node_ids: dict[tuple[str, str], list[str]] = {}
    analyzer_groups: dict[tuple[str, str], dict[str, Any]] = {}

    resolution_materializations = [
        item
        for item in (resolution_plan.get("technical_plan") or {}).get("materializations") or []
        if isinstance(item, Mapping)
    ]
    unavailable_optional_consumers: set[str] = set()
    for item in resolution_materializations:
        if str(item.get("execution_requirement") or "required") != "optional":
            continue
        materialization_id = str(item.get("materialization_id") or "")
        contract = materialization_contracts.get(materialization_id)
        runtime = ((contract or {}).get("current_implementation") or {}).get("runtime") or {}
        if not (
            contract is not None
            and runtime.get("registered") is True
            and str(runtime.get("handler_id") or "") == materialization_id
        ):
            unavailable_optional_consumers.add(f"internal:{materialization_id}")

    for source in sources:
        node_id = f"source:{source['source_id']}"
        nodes[node_id] = {
            "node_id": node_id,
            "node_kind": "source_snapshot",
            "execution_required": False,
            "source_snapshot": source,
        }

    requirements = (resolution_plan.get("technical_plan") or {}).get("evidence_requirements") or []
    for raw in requirements:
        if not isinstance(raw, Mapping):
            raise ValueError("knowledge resolution plan contains a non-object evidence requirement")
        artifact_kind = str(raw.get("artifact_kind") or "")
        schema_version = str(raw.get("schema_version") or "")
        identity = (artifact_kind, schema_version)
        required_by = sorted(str(value) for value in raw.get("required_by") or [])
        optional_by = sorted(
            str(value)
            for value in raw.get("optional_by") or []
            if str(value) not in unavailable_optional_consumers
        )
        if not required_by and not optional_by:
            continue
        is_required = bool(required_by)
        production_policy = str(raw.get("production_policy") or "produce_if_missing")
        if production_policy not in {"produce_if_missing", "existing_only"}:
            raise ValueError(f"unsupported evidence production_policy: {production_policy!r}")

        matching_existing = existing_evidence.get(identity, [])
        if matching_existing:
            for artifact in matching_existing:
                node_id = f"evidence:{artifact['artifact_id']}"
                nodes[node_id] = {
                    "node_id": node_id,
                    "node_kind": "typed_evidence_artifact",
                    "execution_required": False,
                    "satisfaction_mode": "existing_typed_artifact",
                    "artifact": artifact,
                    "required_by": required_by,
                    "optional_by": optional_by,
                }
                evidence_node_ids.setdefault(identity, []).append(node_id)
            continue

        if not is_required and production_policy == "existing_only":
            diagnostics.append({
                "diagnostic_id": "optional_evidence_existing_only_not_available",
                "severity": "info",
                "artifact_kind": artifact_kind,
                "schema_version": schema_version,
                "optional_by": optional_by,
                "production_policy": production_policy,
                "effect": "Optional evidence is not present and will not be produced by the default bounded execution plan.",
            })
            continue

        core_contract = core_contracts.get(identity)
        if core_contract is not None:
            runtime = core_contract.get("runtime_publication") or {}
            producer = core_contract.get("producer") or {}
            analyzer_id = str(runtime.get("producer_analyzer_id") or producer.get("target_analyzer_id") or "")
            registered = runtime.get("registration_status") == "registered"
            source_language = str(producer.get("source_language") or "").strip()

            source_applicability = [
                (source, _evaluate_core_applicability(core_contract, source))
                for source in sources
            ]
            observed_not_applicable = [
                (source, decision)
                for source, decision in source_applicability
                if decision.get("status") == "not_applicable"
            ]
            unresolved_applicability = [
                (source, decision)
                for source, decision in source_applicability
                if decision.get("status") == "unresolved"
            ]
            applicability_eligible = [
                (source, decision)
                for source, decision in source_applicability
                if decision.get("status") != "not_applicable"
            ]

            if observed_not_applicable:
                diagnostics.append({
                    "diagnostic_id": (
                        "required_evidence_observed_not_applicable"
                        if is_required and not applicability_eligible
                        else "evidence_observed_not_applicable_for_source"
                    ),
                    "severity": "error" if is_required and not applicability_eligible else "info",
                    "artifact_kind": artifact_kind,
                    "schema_version": schema_version,
                    "required_by": required_by,
                    "optional_by": optional_by,
                    "production_policy": production_policy,
                    "basis": "observed_source_landscape",
                    "source_decisions": [decision for _, decision in observed_not_applicable],
                    "effect": (
                        "Explicitly required evidence has an observed blocking non-applicability precondition."
                        if is_required and not applicability_eligible
                        else "Automatic production is omitted only for source snapshots that are observed non-applicable; other sources remain eligible."
                    ),
                })
            if is_required and source_applicability and not applicability_eligible:
                # Explicit requirements are never silently optimized away.  An observed
                # blocking precondition is surfaced as an error and the materialization
                # will also retain its required_evidence_unsatisfied diagnostic below.
                continue

            if unresolved_applicability:
                diagnostics.append({
                    "diagnostic_id": "evidence_applicability_unresolved_execution_preserved",
                    "severity": "info",
                    "artifact_kind": artifact_kind,
                    "schema_version": schema_version,
                    "required_by": required_by,
                    "optional_by": optional_by,
                    "production_policy": production_policy,
                    "source_decisions": [decision for _, decision in unresolved_applicability],
                    "effect": "Applicability is unresolved; Runner preserves execution eligibility instead of hard-skipping.",
                })

            matching_source_decisions = [
                (source, decision)
                for source, decision in applicability_eligible
                if not source_language or source_language in set(str(value) for value in source.get("languages") or [])
            ]
            if registered and analyzer_id and matching_source_decisions:
                for source, applicability_decision in matching_source_decisions:
                    group_key = (analyzer_id, str(source["source_id"]))
                    group = analyzer_groups.setdefault(group_key, {
                        "analyzer_id": analyzer_id,
                        "source": source,
                        "requirements": [],
                        "foundation_requirements": set(),
                    })
                    group["requirements"].append({
                        "artifact_kind": artifact_kind,
                        "schema_version": schema_version,
                        "required_by": required_by,
                        "optional_by": optional_by,
                        "contract_fingerprint": core_contract.get("contract_fingerprint"),
                        "production_policy": production_policy,
                        "applicability": applicability_decision,
                    })
                    group["foundation_requirements"].update(
                        str(value) for value in producer.get("required_foundation_sections") or []
                    )
                continue
            if observed_not_applicable and not applicability_eligible and not is_required:
                # This is the only automatic hard-skip path: the owner-provided Core
                # predicate is formalized and every source snapshot is observed non-applicable.
                continue
            diagnostic_id = "core_evidence_producer_not_registered" if not registered or not analyzer_id else "compatible_source_snapshot_missing"
            diagnostic = {
                "diagnostic_id": diagnostic_id,
                "severity": "error" if is_required else "info",
                "artifact_kind": artifact_kind,
                "schema_version": schema_version,
                "required_by": required_by,
                "optional_by": optional_by,
                "producer_registered": registered,
                "analyzer_id": analyzer_id or None,
                "required_source_language": source_language or None,
                "effect": "Required evidence cannot be produced for this execution." if is_required else "Optional evidence will not be produced.",
            }
            diagnostics.append(diagnostic)
            continue

        diagnostics.append({
            "diagnostic_id": "required_external_typed_artifact_missing" if is_required else "optional_typed_artifact_unavailable",
            "severity": "error" if is_required else "info",
            "artifact_kind": artifact_kind,
            "schema_version": schema_version,
            "required_by": required_by,
            "optional_by": optional_by,
            "contract_known_to_materialization": True,
            "producer_registered": False,
            "effect": "Provide this typed artifact explicitly; no Core producer is registered and no fallback is allowed." if is_required else "Optional input was not supplied.",
        })

    for (analyzer_id, source_id), group in sorted(analyzer_groups.items()):
        node_id = f"analyzer:{analyzer_id}:{source_id}"
        output_identities = sorted(
            (item["artifact_kind"], item["schema_version"]) for item in group["requirements"]
        )
        nodes[node_id] = {
            "node_id": node_id,
            "node_kind": "core_evidence_analyzer",
            "execution_required": True,
            "runtime_contract_id": "core_evidence_runtime/v1",
            "analyzer_id": analyzer_id,
            "source_snapshot_id": group["source"].get("snapshot_id"),
            "source_id": source_id,
            "foundation_requirements": sorted(group["foundation_requirements"]),
            "evidence_requirements": sorted(
                group["requirements"], key=lambda value: (value["artifact_kind"], value["schema_version"])
            ),
            "expected_outputs": [
                {"artifact_kind": kind, "schema_version": version} for kind, version in output_identities
            ],
        }
        source_node = f"source:{source_id}"
        if source_node in nodes:
            edges.append({"from": source_node, "to": node_id, "edge_kind": "source_input"})
        for artifact_kind, schema_version in output_identities:
            planned_artifact_id = f"planned_evidence_{stable_fingerprint({'node': node_id, 'kind': artifact_kind, 'version': schema_version})[:24]}"
            artifact_node_id = f"evidence:{planned_artifact_id}"
            requirement = next(
                item for item in group["requirements"]
                if item["artifact_kind"] == artifact_kind and item["schema_version"] == schema_version
            )
            nodes[artifact_node_id] = {
                "node_id": artifact_node_id,
                "node_kind": "typed_evidence_artifact",
                "execution_required": False,
                "satisfaction_mode": "planned_core_output",
                "artifact": {
                    "artifact_id": planned_artifact_id,
                    "artifact_kind": artifact_kind,
                    "schema_version": schema_version,
                    "producer_analyzer_node_id": node_id,
                    "availability": "planned",
                },
                "required_by": requirement["required_by"],
                "optional_by": requirement["optional_by"],
                "production_policy": requirement.get("production_policy") or "produce_if_missing",
            }
            evidence_node_ids.setdefault((artifact_kind, schema_version), []).append(artifact_node_id)
            edges.append({"from": node_id, "to": artifact_node_id, "edge_kind": "produces_evidence"})

    materialization_nodes: dict[str, str] = {}
    selected_materializations = [
        deepcopy(dict(item))
        for item in (resolution_plan.get("technical_plan") or {}).get("materializations") or []
        if isinstance(item, Mapping)
    ]
    candidate_by_id: dict[str, dict[str, Any]] = {}
    for raw in selected_materializations:
        materialization_id = str(raw.get("materialization_id") or "")
        if not materialization_id:
            raise ValueError("knowledge resolution plan contains a materialization without materialization_id")
        if materialization_id in candidate_by_id:
            raise ValueError(f"knowledge resolution plan contains duplicate materialization: {materialization_id}")
        candidate_by_id[materialization_id] = raw

    active_ids = {
        materialization_id
        for materialization_id, raw in candidate_by_id.items()
        if str(raw.get("execution_requirement") or "required") != "optional"
    }
    optional_pending = {
        materialization_id
        for materialization_id, raw in candidate_by_id.items()
        if str(raw.get("execution_requirement") or "required") == "optional"
    }
    optional_skip_reasons: dict[str, dict[str, Any]] = {}

    def missing_optional_inputs(materialization_id: str) -> dict[str, Any]:
        contract = materialization_contracts.get(materialization_id)
        if contract is None:
            return {"contract_missing": True}
        runtime = (contract.get("current_implementation") or {}).get("runtime") or {}
        if not (runtime.get("registered") is True and str(runtime.get("handler_id") or "") == materialization_id):
            return {"runtime_registered": False}
        input_contract = contract.get("input_contract") or {}
        missing_evidence: list[dict[str, Any]] = []
        for raw in input_contract.get("required_evidence") or []:
            if not isinstance(raw, Mapping):
                continue
            artifact_kind = str(raw.get("artifact_kind") or "")
            versions = [str(value) for value in raw.get("schema_versions") or []]
            if not any(evidence_node_ids.get((artifact_kind, version)) for version in versions):
                missing_evidence.append({"artifact_kind": artifact_kind, "schema_versions": versions})
        missing_knowledge: list[dict[str, Any]] = []
        for raw in input_contract.get("required_knowledge_models") or []:
            if not isinstance(raw, Mapping):
                continue
            model_kind = str(raw.get("model_kind") or "")
            versions = [str(value) for value in raw.get("schema_versions") or []]
            source_materialization_id = str(raw.get("source_materialization_id") or "")
            existing_match = any(
                existing_knowledge.get((model_kind, version, source_materialization_id))
                for version in versions
            )
            source_contract = materialization_contracts.get(source_materialization_id)
            source_models = set(
                str(value) for value in ((source_contract or {}).get("outputs") or {}).get("models") or []
            )
            planned_match = (
                source_materialization_id in active_ids
                and any(version in source_models for version in versions)
            )
            if not existing_match and not planned_match:
                missing_knowledge.append({
                    "model_kind": model_kind,
                    "schema_versions": versions,
                    "source_materialization_id": source_materialization_id,
                })
        result: dict[str, Any] = {}
        if missing_evidence:
            result["required_evidence"] = missing_evidence
        if missing_knowledge:
            result["required_knowledge"] = missing_knowledge
        return result

    while optional_pending:
        activated_this_round: list[str] = []
        terminal_skips: list[str] = []
        for materialization_id in sorted(optional_pending):
            reasons = missing_optional_inputs(materialization_id)
            if not reasons:
                active_ids.add(materialization_id)
                activated_this_round.append(materialization_id)
                continue
            if reasons.get("contract_missing") or reasons.get("runtime_registered") is False:
                optional_skip_reasons[materialization_id] = reasons
                terminal_skips.append(materialization_id)
        optional_pending.difference_update(activated_this_round)
        optional_pending.difference_update(terminal_skips)
        if activated_this_round or terminal_skips:
            continue
        # Remaining candidates depend on evidence/knowledge that is not available or
        # on another optional candidate that could not become active.
        for materialization_id in sorted(optional_pending):
            optional_skip_reasons[materialization_id] = missing_optional_inputs(materialization_id)
        break

    for materialization_id, reasons in sorted(optional_skip_reasons.items()):
        diagnostics.append({
            "diagnostic_id": "optional_internal_materialization_skipped",
            "severity": "info",
            "materialization_id": materialization_id,
            "basis": "required_typed_inputs_not_available_or_producible",
            "details": reasons,
            "effect": "Optional enrichment is omitted; explicitly requested knowledge remains executable and no fallback knowledge is invented.",
        })

    selected_materializations = [
        raw for raw in selected_materializations
        if str(raw.get("materialization_id") or "") in active_ids
    ]
    selected_ids = {str(item.get("materialization_id") or "") for item in selected_materializations}
    for raw in selected_materializations:
        materialization_id = str(raw.get("materialization_id") or "")
        contract = materialization_contracts.get(materialization_id)
        if contract is None:
            diagnostics.append({
                "diagnostic_id": "materialization_contract_missing",
                "severity": "error",
                "materialization_id": materialization_id,
                "effect": "Execution cannot continue without a KLC materialization contract.",
            })
            continue
        runtime = (contract.get("current_implementation") or {}).get("runtime") or {}
        registered = runtime.get("registered") is True and str(runtime.get("handler_id") or "") == materialization_id
        node_id = f"materialization:{materialization_id}"
        materialization_nodes[materialization_id] = node_id
        nodes[node_id] = {
            "node_id": node_id,
            "node_kind": "knowledge_materialization",
            "execution_required": True,
            "runtime_contract_id": runtime.get("contract_id"),
            "materialization_id": materialization_id,
            "runtime_registered": registered,
            "knowledge_id": raw.get("knowledge_id"),
            "selection_origin": raw.get("selection_origin"),
            "execution_requirement": raw.get("execution_requirement") or "required",
            "required_by": sorted(str(value) for value in raw.get("required_by") or []),
            "optional_by": sorted(str(value) for value in raw.get("optional_by") or []),
            "expected_models": sorted(str(value) for value in (contract.get("outputs") or {}).get("models") or []),
            "expected_capabilities": sorted(str(value) for value in (contract.get("outputs") or {}).get("capabilities") or []),
            "conditional_capabilities": sorted(
                str(value)
                for value in (contract.get("outputs") or {}).get("conditional_capabilities") or []
            ),
        }
        if not registered:
            diagnostics.append({
                "diagnostic_id": "materialization_not_registered",
                "severity": "error",
                "materialization_id": materialization_id,
                "lifecycle": contract.get("lifecycle"),
                "effect": "The contract is known, but the KLC runtime handler is not registered; legacy execution is not allowed.",
            })

    required_model_kinds: dict[tuple[str, str], set[str]] = {}
    for selected_id in sorted(materialization_nodes):
        selected_contract = materialization_contracts[selected_id]
        selected_inputs = selected_contract.get("input_contract") or {}
        for group_name in ("required_knowledge_models", "optional_knowledge_models"):
            for raw_model in selected_inputs.get(group_name) or []:
                if not isinstance(raw_model, Mapping):
                    continue
                source_id = str(raw_model.get("source_materialization_id") or "")
                model_kind = str(raw_model.get("model_kind") or "")
                for schema_version in raw_model.get("schema_versions") or []:
                    required_model_kinds.setdefault((source_id, str(schema_version)), set()).add(model_kind)

    planned_knowledge_nodes: dict[tuple[str, str, str], list[str]] = {}
    for materialization_id, materialization_node_id in sorted(materialization_nodes.items()):
        contract = materialization_contracts[materialization_id]
        for schema_version in sorted(str(value) for value in (contract.get("outputs") or {}).get("models") or []):
            model_kinds = sorted(required_model_kinds.get((materialization_id, schema_version)) or [])
            if not model_kinds:
                model_kinds = [schema_version.rsplit("/", 1)[0]]
            for model_kind in model_kinds:
                planned_artifact_id = f"planned_knowledge_{stable_fingerprint({'materialization': materialization_id, 'kind': model_kind, 'version': schema_version})[:24]}"
                knowledge_node_id = f"knowledge:{planned_artifact_id}"
                nodes[knowledge_node_id] = {
                    "node_id": knowledge_node_id,
                    "node_kind": "knowledge_artifact",
                    "execution_required": False,
                    "satisfaction_mode": "planned_materialization_output",
                    "artifact": {
                        "artifact_id": planned_artifact_id,
                        "model_kind": model_kind,
                        "schema_version": schema_version,
                        "source_materialization_id": materialization_id,
                        "producer_materialization_node_id": materialization_node_id,
                        "availability": "planned",
                    },
                }
                planned_knowledge_nodes.setdefault((model_kind, schema_version, materialization_id), []).append(knowledge_node_id)
                edges.append({"from": materialization_node_id, "to": knowledge_node_id, "edge_kind": "produces_knowledge"})

    for materialization_id, node_id in sorted(materialization_nodes.items()):
        contract = materialization_contracts[materialization_id]
        input_contract = contract.get("input_contract") or {}
        for requirement_group, required in (("required_evidence", True), ("optional_evidence", False)):
            for raw in input_contract.get(requirement_group) or []:
                if not isinstance(raw, Mapping):
                    continue
                kind = str(raw.get("artifact_kind") or "")
                versions = [str(value) for value in raw.get("schema_versions") or []]
                matched = [
                    evidence_node_id
                    for version in versions
                    for evidence_node_id in evidence_node_ids.get((kind, version), [])
                ]
                for evidence_node_id in sorted(set(matched)):
                    edges.append({
                        "from": evidence_node_id,
                        "to": node_id,
                        "edge_kind": "required_evidence" if required else "optional_evidence",
                    })
                if required and not matched:
                    diagnostics.append({
                        "diagnostic_id": "required_evidence_unsatisfied",
                        "severity": "error",
                        "materialization_id": materialization_id,
                        "artifact_kind": kind,
                        "schema_versions": versions,
                        "effect": "No existing or planned evidence artifact can satisfy this materialization input.",
                    })
        for requirement_group, required in (("required_knowledge_models", True), ("optional_knowledge_models", False)):
            for raw in input_contract.get(requirement_group) or []:
                if not isinstance(raw, Mapping):
                    continue
                model_kind = str(raw.get("model_kind") or "")
                versions = [str(value) for value in raw.get("schema_versions") or []]
                source_materialization_id = str(raw.get("source_materialization_id") or "")
                matched_planned_nodes = [
                    knowledge_node_id
                    for version in versions
                    for knowledge_node_id in planned_knowledge_nodes.get((model_kind, version, source_materialization_id), [])
                ]
                matched_existing = [
                    item
                    for version in versions
                    for item in existing_knowledge.get((model_kind, version, source_materialization_id), [])
                ]
                if matched_planned_nodes:
                    for knowledge_node_id in sorted(set(matched_planned_nodes)):
                        edges.append({
                            "from": knowledge_node_id,
                            "to": node_id,
                            "edge_kind": "required_knowledge" if required else "optional_knowledge",
                            "model_kind": model_kind,
                            "schema_versions": versions,
                        })
                elif matched_existing:
                    for artifact in matched_existing:
                        knowledge_node_id = f"knowledge:{artifact['artifact_id']}"
                        nodes.setdefault(knowledge_node_id, {
                            "node_id": knowledge_node_id,
                            "node_kind": "knowledge_artifact",
                            "execution_required": False,
                            "satisfaction_mode": "existing_knowledge_artifact",
                            "artifact": artifact,
                        })
                        edges.append({
                            "from": knowledge_node_id,
                            "to": node_id,
                            "edge_kind": "required_knowledge" if required else "optional_knowledge",
                            "model_kind": model_kind,
                            "schema_versions": versions,
                        })
                elif required:
                    diagnostics.append({
                        "diagnostic_id": "required_knowledge_unsatisfied",
                        "severity": "error",
                        "materialization_id": materialization_id,
                        "model_kind": model_kind,
                        "schema_versions": versions,
                        "source_materialization_id": source_materialization_id,
                        "source_materialization_selected": source_materialization_id in selected_ids,
                        "effect": "Required knowledge is neither available nor produced by the selected execution graph.",
                    })

    node_list = [nodes[node_id] for node_id in sorted(nodes)]
    edge_list = sorted(
        edges,
        key=lambda value: (str(value.get("from") or ""), str(value.get("to") or ""), str(value.get("edge_kind") or "")),
    )
    graph_order = _topological_order(nodes, edge_list)
    execution_order = [
        node_id for node_id in graph_order
        if nodes[node_id].get("execution_required") is True
    ]
    blocking_diagnostics = [item for item in diagnostics if item.get("severity") == "error"]
    expected_capabilities = sorted({
        capability
        for node in node_list
        if node.get("node_kind") == "knowledge_materialization"
        for capability in node.get("expected_capabilities") or []
    })
    expected_models = sorted({
        model
        for node in node_list
        if node.get("node_kind") == "knowledge_materialization"
        for model in node.get("expected_models") or []
    })
    foundation_requirements = sorted({
        requirement
        for node in node_list
        if node.get("node_kind") == "core_evidence_analyzer"
        for requirement in node.get("foundation_requirements") or []
    })

    payload: dict[str, Any] = {
        "schema_version": KNOWLEDGE_EXECUTION_PLAN_SCHEMA_VERSION,
        "producer": {"component": "static-analysis-runner", "version": __version__},
        "scope": deepcopy(inventory_scope),
        "request": {
            "knowledge_profile_id": (resolution_plan.get("profile") or {}).get("profile_id"),
            "knowledge_profile_fingerprint": (resolution_plan.get("source") or {}).get("knowledge_profile_fingerprint"),
            "knowledge_catalog_fingerprint": knowledge_catalog.get("catalog_fingerprint"),
            "knowledge_resolution_plan_fingerprint": resolution_plan.get("plan_fingerprint"),
            "resolved_knowledge_ids": (resolution_plan.get("resolved_selection") or {}).get("resolved_knowledge_ids") or [],
        },
        "inputs": {
            "knowledge_input_inventory_fingerprint": inventory.get("inventory_fingerprint"),
            "core_evidence_contract_catalog_fingerprint": core_evidence_catalog.get("catalog_fingerprint"),
            "knowledge_materialization_catalog_fingerprint": materialization_catalog.get("catalog_fingerprint"),
        },
        "graph": {
            "nodes": node_list,
            "edges": edge_list,
            "topological_order": graph_order,
            "execution_order": execution_order,
        },
        "foundation_requirements": foundation_requirements,
        "expected_outputs": {
            "knowledge_models": expected_models,
            "capabilities": expected_capabilities,
        },
        "status": {
            "overall": "ready" if not blocking_diagnostics else "blocked",
            "blocking_diagnostic_count": len(blocking_diagnostics),
            "execution_node_count": len(execution_order),
            "core_analyzer_node_count": sum(item.get("node_kind") == "core_evidence_analyzer" for item in node_list),
            "materialization_node_count": sum(item.get("node_kind") == "knowledge_materialization" for item in node_list),
            "existing_typed_artifact_count": sum(item.get("satisfaction_mode") == "existing_typed_artifact" for item in node_list),
            "existing_knowledge_artifact_count": sum(item.get("satisfaction_mode") == "existing_knowledge_artifact" for item in node_list),
        },
        "semantic_policy": {
            "evidence_identity": ["artifact_kind", "schema_version"],
            "knowledge_identity": ["model_kind", "schema_version", "source_materialization_id"],
            "core_dispatch": "core_owned_analyzer_registry",
            "klc_dispatch": "materialization_id_to_klc_owned_handler",
            "orchestration_semantics": "knowledge_contracts_only",
        },
        "diagnostics": sorted(
            diagnostics,
            key=lambda value: (
                0 if value.get("severity") == "error" else 1,
                str(value.get("diagnostic_id") or ""),
                str(value.get("materialization_id") or ""),
                str(value.get("artifact_kind") or ""),
            ),
        ),
        "next_step": "execute_with_knowledge_execute" if not blocking_diagnostics else "resolve_blocking_inputs_or_runtime_registrations",
    }
    payload["plan_fingerprint"] = _fingerprint(payload)
    return payload



def validate_knowledge_execution_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    _validate_fingerprinted_payload(
        payload,
        schema_version=KNOWLEDGE_EXECUTION_PLAN_SCHEMA_VERSION,
        fingerprint_field="plan_fingerprint",
        label="knowledge execution plan",
    )
    scope = payload.get("scope") or {}
    if str(scope.get("kind") or "") not in {"repository", "workspace", "portfolio"}:
        raise ValueError("knowledge execution plan has invalid scope.kind")
    if not str(scope.get("scope_id") or ""):
        raise ValueError("knowledge execution plan has no scope_id")

    graph = payload.get("graph") or {}
    raw_nodes = graph.get("nodes") or []
    raw_edges = graph.get("edges") or []
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("knowledge execution plan graph nodes and edges must be lists")

    nodes: dict[str, Mapping[str, Any]] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise ValueError("knowledge execution plan contains a non-object graph node")
        node_id = str(raw.get("node_id") or "")
        if not node_id or node_id in nodes:
            raise ValueError(f"invalid or duplicate execution-plan node_id: {node_id!r}")
        if not str(raw.get("node_kind") or ""):
            raise ValueError(f"execution-plan node {node_id!r} has no node_kind")
        if not isinstance(raw.get("execution_required"), bool):
            raise ValueError(f"execution-plan node {node_id!r} has invalid execution_required")
        nodes[node_id] = raw

    edge_identities: set[tuple[str, str, str]] = set()
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise ValueError("knowledge execution plan contains a non-object graph edge")
        source = str(raw.get("from") or "")
        target = str(raw.get("to") or "")
        edge_kind = str(raw.get("edge_kind") or "")
        if source not in nodes or target not in nodes:
            raise ValueError(f"execution-plan edge references an unknown node: {source!r} -> {target!r}")
        if source == target:
            raise ValueError(f"execution-plan self-edge is not allowed: {source!r}")
        identity = (source, target, edge_kind)
        if not edge_kind or identity in edge_identities:
            raise ValueError(f"invalid or duplicate execution-plan edge: {identity!r}")
        edge_identities.add(identity)

    topological_order = [str(value) for value in graph.get("topological_order") or []]
    if len(topological_order) != len(nodes) or set(topological_order) != set(nodes):
        raise ValueError("knowledge execution plan topological_order does not contain every graph node exactly once")
    positions = {node_id: index for index, node_id in enumerate(topological_order)}
    for source, target, _ in edge_identities:
        if positions[source] >= positions[target]:
            raise ValueError(f"knowledge execution plan topological_order violates edge {source!r} -> {target!r}")

    expected_execution_order = [
        node_id for node_id in topological_order if nodes[node_id].get("execution_required") is True
    ]
    actual_execution_order = [str(value) for value in graph.get("execution_order") or []]
    if actual_execution_order != expected_execution_order:
        raise ValueError("knowledge execution plan execution_order does not match executable nodes in topological order")

    diagnostics = payload.get("diagnostics") or []
    if not isinstance(diagnostics, list):
        raise ValueError("knowledge execution plan diagnostics must be a list")
    blocking_count = sum(
        isinstance(item, Mapping) and item.get("severity") == "error" for item in diagnostics
    )
    status = payload.get("status") or {}
    if int(status.get("blocking_diagnostic_count", -1)) != blocking_count:
        raise ValueError("knowledge execution plan blocking_diagnostic_count is inconsistent")
    expected_status = "ready" if blocking_count == 0 else "blocked"
    if str(status.get("overall") or "") != expected_status:
        raise ValueError("knowledge execution plan overall status is inconsistent")
    if int(status.get("execution_node_count", -1)) != len(actual_execution_order):
        raise ValueError("knowledge execution plan execution_node_count is inconsistent")

    policy = payload.get("semantic_policy") or {}
    expected_policy = {
        "evidence_identity": ["artifact_kind", "schema_version"],
        "knowledge_identity": ["model_kind", "schema_version", "source_materialization_id"],
        "core_dispatch": "core_owned_analyzer_registry",
        "klc_dispatch": "materialization_id_to_klc_owned_handler",
        "orchestration_semantics": "knowledge_contracts_only",
    }
    if policy != expected_policy:
        raise ValueError("knowledge execution plan semantic policy is invalid")

    return deepcopy(dict(payload))
