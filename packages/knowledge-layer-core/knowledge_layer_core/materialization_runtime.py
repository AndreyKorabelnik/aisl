from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .code_declared_model_builder import build_code_declared_data_model_knowledge_layer
from .repository_inventory_builder import build_repository_inventory_knowledge_layer
from .effective_data_model_builder import build_effective_data_model_knowledge_layer
from .logical_physical_mapping_builder import build_logical_physical_mapping_knowledge_layer
from .physical_model_builder import build_physical_model_knowledge_layer
from .observed_storage_usage_builder import build_observed_storage_usage_knowledge_layer
from .model_storage_semantics_builder import build_model_storage_semantics_knowledge_layer
from .logical_storage_mapping_builder import build_logical_storage_mapping_knowledge_layer
from .cross_artifact_data_model_builder import build_cross_artifact_data_model_mapping_knowledge_layer
from .attribute_extension_context_builder import build_attribute_extension_context_knowledge_layer
from .sql_analysis_builder import build_sql_knowledge_layer
from .sql_target_source_mapping_builder import build_sql_target_source_mapping_knowledge_layer
from .workspace_sql_catalog_builder import build_workspace_sql_catalog
from .subject_knowledge_builder import build_subject_knowledge_layer
from .interaction_knowledge_builder import build_system_interactions_knowledge_layer
from .interaction_field_contract_knowledge_builder import build_system_interaction_field_contract_knowledge_layer
from .cross_repository_value_flow_builder import build_cross_repository_value_flow_knowledge_layer
from .value_flow_knowledge_builder import build_repository_value_flow_knowledge_layer
from .materialization_contracts import CURRENT_MATERIALIZATIONS
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .version import __version__
from .progress import bind_progress, emit_progress

MATERIALIZATION_REQUEST_SCHEMA_VERSION = "knowledge_materialization_request/v1"
MATERIALIZATION_EXECUTION_RESULT_SCHEMA_VERSION = "knowledge_materialization_execution_result/v1"
MATERIALIZATION_RUNTIME_CONTRACT_ID = "knowledge_materialization_runtime/v1"


@dataclass(frozen=True, slots=True)
class MaterializationHandler:
    materialization_id: str
    invoke: Callable[[Mapping[str, Any], Path, str, bool, str, int], dict[str, Any]]


def _fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _require_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


def _materialization_contract(materialization_id: str) -> dict[str, Any]:
    matches = [
        item.to_dict()
        for item in CURRENT_MATERIALIZATIONS
        if item.materialization_id == materialization_id
    ]
    if len(matches) != 1:
        raise ValueError(f"materialization contract not found or ambiguous: {materialization_id!r}")
    return matches[0]


def _semantic_identity(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _require_text(item.get("artifact_kind"), field="evidence artifact_kind"),
        _require_text(item.get("schema_version"), field="evidence schema_version"),
    )




def _semantic_request_material(request: Mapping[str, Any]) -> dict[str, Any]:
    inputs = request.get("inputs") or {}
    evidence = []
    for item in (inputs.get("evidence_artifacts") or []):
        if isinstance(item, Mapping):
            evidence.append({
                "artifact_id": item.get("artifact_id"),
                "artifact_kind": item.get("artifact_kind"),
                "schema_version": item.get("schema_version"),
                "content_fingerprint": item.get("content_fingerprint"),
            })
    knowledge = []
    for item in (inputs.get("knowledge_artifacts") or []):
        if isinstance(item, Mapping):
            knowledge.append({
                "artifact_id": item.get("artifact_id"),
                "model_kind": item.get("model_kind"),
                "schema_version": item.get("schema_version"),
                "source_materialization_id": item.get("source_materialization_id"),
                "content_fingerprint": item.get("content_fingerprint"),
            })
    return {
        "schema_version": request.get("schema_version"),
        "materialization_id": request.get("materialization_id"),
        "scope_id": request.get("scope_id"),
        "inputs": {
            "evidence_artifacts": sorted(evidence, key=lambda value: (str(value.get("artifact_kind")), str(value.get("schema_version")), str(value.get("artifact_id")))),
            "knowledge_artifacts": sorted(knowledge, key=lambda value: (str(value.get("source_materialization_id")), str(value.get("model_kind")), str(value.get("schema_version")), str(value.get("artifact_id")))),
        },
        "parameters": dict(request.get("parameters") or {}),
    }


def _validate_runner_registration_binding(item: Mapping[str, Any]) -> None:
    raw_path = item.get("registration_manifest_path")
    if raw_path is None:
        return
    manifest_path = Path(_require_text(raw_path, field="registration_manifest_path")).expanduser().resolve()
    manifest = _read_json_object(manifest_path)
    if manifest.get("schema_version") != "static_repository_analysis_run_manifest/v1":
        raise ValueError(f"unsupported Runner registration manifest schema: {manifest.get('schema_version')!r}")
    matches = [
        entry for entry in (manifest.get("evidence_artifacts") or [])
        if isinstance(entry, Mapping)
        and str(entry.get("artifact_kind") or "") == str(item.get("artifact_kind") or "")
        and str(entry.get("schema_version") or "") == str(item.get("schema_version") or "")
    ]
    if len(matches) != 1:
        raise ValueError("Runner registration manifest must contain exactly one matching evidence artifact")
    registered = matches[0]
    for field in ("artifact_id", "content_fingerprint"):
        if str(registered.get(field) or "") != str(item.get(field) or ""):
            raise ValueError(f"Runner registration {field} does not match materialization request")


def _validate_evidence_inputs(contract: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    inputs = request.get("inputs") or {}
    if not isinstance(inputs, Mapping):
        raise ValueError("request.inputs must be an object")
    raw_evidence = inputs.get("evidence_artifacts") or []
    if not isinstance(raw_evidence, list):
        raise ValueError("request.inputs.evidence_artifacts must be a list")
    evidence = tuple(dict(item) for item in raw_evidence if isinstance(item, Mapping))
    if len(evidence) != len(raw_evidence):
        raise ValueError("request.inputs.evidence_artifacts contains a non-object item")

    input_contract = contract.get("input_contract") or {}
    requirements = tuple(input_contract.get("required_evidence") or ())
    optional = tuple(input_contract.get("optional_evidence") or ())
    allowed: dict[str, set[str]] = {}
    for requirement in (*requirements, *optional):
        if not isinstance(requirement, Mapping):
            continue
        kind = _require_text(requirement.get("artifact_kind"), field="contract artifact_kind")
        versions = {str(item).strip() for item in (requirement.get("schema_versions") or []) if str(item).strip()}
        if not versions:
            raise ValueError(f"materialization contract has no schema versions for {kind}")
        allowed.setdefault(kind, set()).update(versions)

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        kind, version = _semantic_identity(item)
        _validate_runner_registration_binding(item)
        if kind not in allowed or version not in allowed[kind]:
            raise ValueError(
                f"unsupported evidence semantic identity for {contract.get('materialization_id')}: {kind}/{version}"
            )
        by_kind.setdefault(kind, []).append(item)

    missing: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            continue
        kind = str(requirement.get("artifact_kind") or "")
        versions = {str(item) for item in (requirement.get("schema_versions") or [])}
        if not any(str(item.get("schema_version") or "") in versions for item in by_kind.get(kind, [])):
            missing.append(f"{kind}:{sorted(versions)}")
    if missing:
        raise ValueError(f"missing required evidence for {contract.get('materialization_id')}: {missing}")
    return evidence


def _validate_knowledge_inputs(contract: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    inputs = request.get("inputs") or {}
    raw_models = inputs.get("knowledge_artifacts") or []
    if not isinstance(raw_models, list):
        raise ValueError("request.inputs.knowledge_artifacts must be a list")
    models = tuple(dict(item) for item in raw_models if isinstance(item, Mapping))
    if len(models) != len(raw_models):
        raise ValueError("request.inputs.knowledge_artifacts contains a non-object item")

    input_contract = contract.get("input_contract") or {}
    requirements = tuple(input_contract.get("required_knowledge_models") or ())
    optional = tuple(input_contract.get("optional_knowledge_models") or ())
    allowed: set[tuple[str, str, str]] = set()
    for requirement in (*requirements, *optional):
        if not isinstance(requirement, Mapping):
            continue
        model_kind = _require_text(requirement.get("model_kind"), field="contract model_kind")
        source = _require_text(requirement.get("source_materialization_id"), field="contract source_materialization_id")
        for version in requirement.get("schema_versions") or []:
            allowed.add((model_kind, str(version), source))

    provided: set[tuple[str, str, str]] = set()
    for item in models:
        identity = (
            _require_text(item.get("model_kind"), field="knowledge model_kind"),
            _require_text(item.get("schema_version"), field="knowledge schema_version"),
            _require_text(item.get("source_materialization_id"), field="knowledge source_materialization_id"),
        )
        if identity not in allowed:
            raise ValueError(
                f"unsupported knowledge input for {contract.get('materialization_id')}: {identity}"
            )
        provided.add(identity)

    missing = []
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            continue
        model_kind = str(requirement.get("model_kind") or "")
        source = str(requirement.get("source_materialization_id") or "")
        versions = {str(item) for item in (requirement.get("schema_versions") or [])}
        if not any((model_kind, version, source) in provided for version in versions):
            missing.append(f"{source}:{model_kind}:{sorted(versions)}")
    if missing:
        raise ValueError(f"missing required knowledge inputs for {contract.get('materialization_id')}: {missing}")
    return models


def _evidence_location_path(item: Mapping[str, Any]) -> Path:
    location = item.get("location") or {}
    if isinstance(location, Mapping) and str(location.get("kind") or "") == "file" and location.get("path"):
        return Path(str(location["path"])).expanduser().resolve()
    raw_manifest = item.get("registration_manifest_path")
    if raw_manifest is None:
        raise ValueError("typed evidence has neither file location nor registration_manifest_path")
    manifest_path = Path(_require_text(raw_manifest, field="registration_manifest_path")).expanduser().resolve()
    manifest = _read_json_object(manifest_path)
    matches = [
        entry for entry in (manifest.get("evidence_artifacts") or [])
        if isinstance(entry, Mapping)
        and str(entry.get("artifact_kind") or "") == str(item.get("artifact_kind") or "")
        and str(entry.get("schema_version") or "") == str(item.get("schema_version") or "")
    ]
    if len(matches) != 1:
        raise ValueError("Runner registration manifest must contain exactly one matching evidence artifact")
    location = matches[0].get("location") or {}
    if str(location.get("kind") or "") != "file":
        raise ValueError("typed evidence location.kind must be 'file'")
    relative = Path(_require_text(location.get("path"), field="typed evidence location.path"))
    if relative.is_absolute():
        raise ValueError("Runner-registered typed evidence location.path must be relative")
    path = (manifest_path.parent / relative).resolve()
    try:
        path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("Runner-registered typed evidence path escapes run root") from exc
    return path


def _invoke_physical_model(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    evidence = [
        item for item in ((request.get("inputs") or {}).get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "physical-model"
        and str(item.get("schema_version") or "") == "physical-model/v1"
    ]
    if len(evidence) != 1:
        raise ValueError("physical-model materialization requires exactly one physical-model/v1 artifact")
    return build_physical_model_knowledge_layer(
        _evidence_location_path(evidence[0]),
        output,
        scope_id=scope_id,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )


def _invoke_logical_physical_mapping(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    inputs = request.get("inputs") or {}
    evidence = [
        dict(item) for item in (inputs.get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "java-persistence-mapping-evidence"
        and str(item.get("schema_version") or "") == "java-persistence-mapping-evidence/v1"
    ]
    knowledge = [dict(item) for item in (inputs.get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    code = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model")]
    physical = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model")]
    if len(code) != 1 or len(physical) != 1:
        raise ValueError("logical-physical-mapping requires exactly one code-declared and one physical-model knowledge artifact")
    return build_logical_physical_mapping_knowledge_layer(
        evidence, code[0], physical[0], output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_effective_data_model(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [dict(item) for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    identities = {
        "code": ("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
        "physical": ("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
        "mapping": ("logical-physical-model-mapping", "logical-physical-model-mapping/v1", "logical-physical-mapping"),
    }
    selected: dict[str, dict[str, Any]] = {}
    for role, identity in identities.items():
        matches = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == identity]
        if len(matches) != 1:
            raise ValueError(f"effective-data-model requires exactly one {identity} knowledge artifact")
        selected[role] = matches[0]
    optional = [item for item in knowledge if item not in selected.values()]
    return build_effective_data_model_knowledge_layer(
        selected["code"],
        selected["physical"],
        selected["mapping"],
        output,
        scope_id=scope_id,
        optional_knowledge_items=optional,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )



def _invoke_logical_storage_mapping(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [dict(item) for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    code = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model")]
    storage = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics")]
    if len(code) != 1 or len(storage) != 1:
        raise ValueError("logical-storage-mapping requires exactly one code-declared-data-model and one model-storage-semantics knowledge input")
    return build_logical_storage_mapping_knowledge_layer(
        code[0], storage[0], output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_cross_artifact_data_model_mapping(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [dict(item) for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    identities = {
        "logical_storage": ("logical-storage-model-mapping", "logical-storage-model-mapping/v2", "logical-storage-mapping"),
        "code_declared": ("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
        "sql": ("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
        "physical": ("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
    }
    selected = {}
    for role, identity in identities.items():
        matches = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == identity]
        if len(matches) != 1:
            raise ValueError(f"cross-artifact-data-model-mapping requires exactly one {identity} knowledge artifact")
        selected[role] = matches[0]
    return build_cross_artifact_data_model_mapping_knowledge_layer(
        selected["logical_storage"], selected["code_declared"], selected["sql"], selected["physical"], output,
        scope_id=scope_id, replace=replace, duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_attribute_extension_context(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [dict(item) for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    identities = {
        "code": ("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
        "storage": ("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics"),
        "logical_storage": ("logical-storage-model-mapping", "logical-storage-model-mapping/v2", "logical-storage-mapping"),
        "cross": ("cross-artifact-data-model-mapping", "cross-artifact-data-model-mapping/v6", "cross-artifact-data-model-mapping"),
        "sql": ("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
    }
    selected: dict[str, dict[str, Any]] = {}
    for role, identity in identities.items():
        matches = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == identity]
        if len(matches) != 1:
            raise ValueError(f"data-model-attribute-extension-context requires exactly one {identity} knowledge artifact")
        selected[role] = matches[0]
    return build_attribute_extension_context_knowledge_layer(
        selected["code"], selected["storage"], selected["logical_storage"], selected["cross"], selected["sql"], output,
        scope_id=scope_id, replace=replace, duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_sql_target_source_mapping(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [dict(item) for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    sql = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis")]
    storage = [item for item in knowledge if (item.get("model_kind"), item.get("schema_version"), item.get("source_materialization_id")) == ("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics")]
    if len(sql) != 1 or len(storage) > 1:
        raise ValueError("sql-target-source-mapping requires exactly one sql-observed-data-usage and at most one model-storage-semantics knowledge input")
    return build_sql_target_source_mapping_knowledge_layer(
        sql[0], output, scope_id=scope_id, model_storage_item=storage[0] if storage else None, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_model_storage_semantics(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    inputs = request.get("inputs") or {}
    evidence = [
        dict(item) for item in (inputs.get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "model-storage-evidence"
        and str(item.get("schema_version") or "") == "model-storage-evidence/v1"
    ]
    resolved_evidence = []
    for item in evidence:
        resolved = dict(item)
        resolved["location"] = {"kind": "file", "path": str(_evidence_location_path(item))}
        resolved_evidence.append(resolved)
    return build_model_storage_semantics_knowledge_layer(
        resolved_evidence,
        output,
        scope_id=scope_id,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )


def _invoke_observed_storage_usage(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    inputs = request.get("inputs") or {}
    evidence = [
        dict(item) for item in (inputs.get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "storage-usage-evidence"
        and str(item.get("schema_version") or "") == "storage-usage-evidence/v1"
    ]
    knowledge = [dict(item) for item in (inputs.get("knowledge_artifacts") or []) if isinstance(item, Mapping)]
    resolved_evidence = []
    for item in evidence:
        resolved = dict(item)
        resolved["location"] = {"kind": "file", "path": str(_evidence_location_path(item))}
        resolved_evidence.append(resolved)
    return build_observed_storage_usage_knowledge_layer(
        resolved_evidence,
        output,
        scope_id=scope_id,
        knowledge_items=knowledge,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )


def _sql_canonical_manifest_from_envelope(item: Mapping[str, Any]) -> Path:
    envelope_path = _evidence_location_path(item)
    envelope = _read_json_object(envelope_path)
    if envelope.get("contract_version") != "core_evidence_artifact_contract/v1":
        raise ValueError("sql-analysis input is not a generic Core evidence envelope")
    if (envelope.get("artifact_kind"), envelope.get("schema_version")) != ("sql-analysis", "sql-analysis/v1"):
        raise ValueError("unexpected sql-analysis evidence semantic identity")
    relative = str(((envelope.get("payload") or {}).get("canonical_manifest_path") or ""))
    if not relative or Path(relative).is_absolute():
        raise ValueError("sql-analysis canonical manifest path must be envelope-relative")
    resolved = (envelope_path.parent / relative).resolve()
    try:
        resolved.relative_to(envelope_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("sql-analysis canonical manifest path escapes envelope root") from exc
    return resolved


def _invoke_sql_analysis(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    evidence = [
        dict(item) for item in ((request.get("inputs") or {}).get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "sql-analysis"
        and str(item.get("schema_version") or "") == "sql-analysis/v1"
    ]
    if len(evidence) != 1:
        raise ValueError("sql-analysis materialization requires exactly one sql-analysis/v1 artifact")
    return build_sql_knowledge_layer(
        _sql_canonical_manifest_from_envelope(evidence[0]),
        output,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )



def _invoke_workspace_sql_catalog(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [
        dict(item)
        for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("model_kind") or "") == "sql-observed-data-usage"
        and str(item.get("schema_version") or "") == "knowledge_layer_sql/v2"
        and str(item.get("source_materialization_id") or "") == "sql-analysis"
    ]
    if not knowledge:
        raise ValueError("workspace-sql-catalog requires at least one sql-observed-data-usage knowledge artifact")
    return build_workspace_sql_catalog(
        knowledge,
        output,
        scope_id=scope_id,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )

def _invoke_subject_knowledge(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
    *,
    materialization_id: str,
    artifact_kind: str,
    schema_version: str,
    produced_model: str,
    capabilities: tuple[str, ...],
) -> dict[str, Any]:
    raw = [
        dict(item) for item in ((request.get("inputs") or {}).get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == artifact_kind
        and str(item.get("schema_version") or "") == schema_version
    ]
    evidence = []
    for item in raw:
        resolved = dict(item)
        resolved["location"] = {"kind": "file", "path": str(_evidence_location_path(item))}
        evidence.append(resolved)
    return build_subject_knowledge_layer(
        evidence, output, scope_id=scope_id, materialization_id=materialization_id,
        expected_artifact_kind=artifact_kind, expected_schema_version=schema_version,
        produced_model=produced_model, capabilities=capabilities, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_system_description(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    return _invoke_subject_knowledge(
        request, output, scope_id, replace, duckdb_memory_limit, duckdb_threads,
        materialization_id="system-description",
        artifact_kind="system-description-evidence",
        schema_version="system-description-evidence/v1",
        produced_model="system-description/v1",
        capabilities=("common.system-description", "common.system-interfaces", "common.system-scenarios", "common.system-dependencies"),
    )


def _invoke_reference_data(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    return _invoke_subject_knowledge(
        request, output, scope_id, replace, duckdb_memory_limit, duckdb_threads,
        materialization_id="reference-data",
        artifact_kind="reference-data-evidence",
        schema_version="reference-data-evidence/v1",
        produced_model="reference-data/v1",
        capabilities=("common.reference-data", "common.declared-value-sets", "common.reference-data-facts"),
    )


def _invoke_persistence_lineage(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    return _invoke_subject_knowledge(
        request, output, scope_id, replace, duckdb_memory_limit, duckdb_threads,
        materialization_id="persistence-lineage",
        artifact_kind="persistence-lineage-evidence",
        schema_version="persistence-lineage-evidence/v1",
        produced_model="persistence-lineage/v1",
        capabilities=("workspace.persistence-lineage", "workspace.fdp-paths"),
    )


def _invoke_system_interactions(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    raw = [
        dict(item) for item in ((request.get("inputs") or {}).get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "interaction-boundary-evidence"
        and str(item.get("schema_version") or "") == "interaction-boundary-evidence/v1"
    ]
    evidence = []
    for item in raw:
        resolved = dict(item)
        resolved["location"] = {"kind": "file", "path": str(_evidence_location_path(item))}
        evidence.append(resolved)
    return build_system_interactions_knowledge_layer(
        evidence, output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_cross_repository_value_flow(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [
        dict(item)
        for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or [])
        if isinstance(item, Mapping)
    ]
    return build_cross_repository_value_flow_knowledge_layer(
        knowledge, output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_interaction_field_contracts(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    knowledge = [
        dict(item)
        for item in ((request.get("inputs") or {}).get("knowledge_artifacts") or [])
        if isinstance(item, Mapping)
    ]
    return build_system_interaction_field_contract_knowledge_layer(
        knowledge, output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


def _invoke_repository_value_flow(
    request: Mapping[str, Any], output: Path, scope_id: str, replace: bool,
    duckdb_memory_limit: str, duckdb_threads: int,
) -> dict[str, Any]:
    raw = [dict(item) for item in ((request.get("inputs") or {}).get("evidence_artifacts") or [])
           if isinstance(item, Mapping) and str(item.get("artifact_kind") or "") == "value-flow-evidence"
           and str(item.get("schema_version") or "") == "value-flow-evidence/v1"]
    evidence=[]
    for item in raw:
        resolved=dict(item); resolved["location"]={"kind":"file","path":str(_evidence_location_path(item))}; evidence.append(resolved)
    return build_repository_value_flow_knowledge_layer(evidence, output, scope_id=scope_id, replace=replace, duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads)


def _invoke_code_declared(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    evidence = tuple((request.get("inputs") or {}).get("evidence_artifacts") or ())
    registration_manifests = []
    for item in evidence:
        path = _require_text(item.get("registration_manifest_path"), field="registration_manifest_path")
        registration_manifests.append(Path(path).expanduser().resolve())
    return build_code_declared_data_model_knowledge_layer(
        registration_manifests,
        output,
        scope_id=scope_id,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
    )


def _invoke_repository_inventory(
    request: Mapping[str, Any],
    output: Path,
    scope_id: str,
    replace: bool,
    duckdb_memory_limit: str,
    duckdb_threads: int,
) -> dict[str, Any]:
    evidence = [dict(item) for item in ((request.get("inputs") or {}).get("evidence_artifacts") or []) if isinstance(item, Mapping)]
    paths = [_evidence_location_path(item) for item in evidence]
    return build_repository_inventory_knowledge_layer(
        evidence, paths, output, scope_id=scope_id, replace=replace,
        duckdb_memory_limit=duckdb_memory_limit, duckdb_threads=duckdb_threads,
    )


_HANDLERS: dict[str, MaterializationHandler] = {
    "repository-inventory": MaterializationHandler(
        materialization_id="repository-inventory",
        invoke=_invoke_repository_inventory,
    ),
    "system-description": MaterializationHandler(
        materialization_id="system-description",
        invoke=_invoke_system_description,
    ),
    "reference-data": MaterializationHandler(
        materialization_id="reference-data",
        invoke=_invoke_reference_data,
    ),
    "persistence-lineage": MaterializationHandler(
        materialization_id="persistence-lineage",
        invoke=_invoke_persistence_lineage,
    ),
    "system-interactions": MaterializationHandler(
        materialization_id="system-interactions",
        invoke=_invoke_system_interactions,
    ),
    "interaction-field-contracts": MaterializationHandler(
        materialization_id="interaction-field-contracts",
        invoke=_invoke_interaction_field_contracts,
    ),
    "cross-repository-value-flow": MaterializationHandler(
        materialization_id="cross-repository-value-flow",
        invoke=_invoke_cross_repository_value_flow,
    ),
    "repository-value-flow": MaterializationHandler(
        materialization_id="repository-value-flow",
        invoke=_invoke_repository_value_flow,
    ),
    "code-declared-data-model": MaterializationHandler(
        materialization_id="code-declared-data-model",
        invoke=_invoke_code_declared,
    ),
    "physical-model": MaterializationHandler(
        materialization_id="physical-model",
        invoke=_invoke_physical_model,
    ),
    "logical-physical-mapping": MaterializationHandler(
        materialization_id="logical-physical-mapping",
        invoke=_invoke_logical_physical_mapping,
    ),
    "effective-data-model": MaterializationHandler(
        materialization_id="effective-data-model",
        invoke=_invoke_effective_data_model,
    ),
    "logical-storage-mapping": MaterializationHandler(
        materialization_id="logical-storage-mapping",
        invoke=_invoke_logical_storage_mapping,
    ),
    "cross-artifact-data-model-mapping": MaterializationHandler(
        materialization_id="cross-artifact-data-model-mapping",
        invoke=_invoke_cross_artifact_data_model_mapping,
    ),
    "data-model-attribute-extension-context": MaterializationHandler(
        materialization_id="data-model-attribute-extension-context",
        invoke=_invoke_attribute_extension_context,
    ),
    "sql-target-source-mapping": MaterializationHandler(
        materialization_id="sql-target-source-mapping",
        invoke=_invoke_sql_target_source_mapping,
    ),
    "model-storage-semantics": MaterializationHandler(
        materialization_id="model-storage-semantics",
        invoke=_invoke_model_storage_semantics,
    ),
    "observed-storage-usage": MaterializationHandler(
        materialization_id="observed-storage-usage",
        invoke=_invoke_observed_storage_usage,
    ),
    "sql-analysis": MaterializationHandler(
        materialization_id="sql-analysis",
        invoke=_invoke_sql_analysis,
    ),
    "workspace-sql-catalog": MaterializationHandler(
        materialization_id="workspace-sql-catalog",
        invoke=_invoke_workspace_sql_catalog,
    ),
}


def registered_materialization_ids() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


def _manifest_diagnostics(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = manifest.get('metadata') or {}
    raw = metadata.get('diagnostics') if isinstance(metadata, Mapping) else []
    return [dict(item) for item in (raw or []) if isinstance(item, Mapping)]


def _canonicalize_knowledge_product_manifest(
    manifest: Mapping[str, Any],
    *,
    output: Path,
) -> dict[str, Any]:
    """Remove execution-local metadata before a KnowledgeProduct is identified.

    ``content_fingerprint`` is the canonical manifest fingerprint throughout KLC.
    Therefore the persisted manifest itself must contain only stable product metadata:
    runtime timestamps and local staging/cache paths belong to execution provenance and
    must not make identical semantic production yield different product identities.
    """
    normalized = json.loads(json.dumps(manifest))
    metadata = normalized.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("started_at", None)
        metadata.pop("completed_at", None)

    local_path_keys = {
        "runner_manifest",
        "artifact_path",
        "physical_model_manifest",
        "sql_analysis_manifest",
        "registration_manifest_path",
        "output_path",
    }
    source_evidence = normalized.get("source_evidence")
    if isinstance(source_evidence, list):
        for item in source_evidence:
            if not isinstance(item, dict):
                continue
            for key in local_path_keys:
                item.pop(key, None)

    manifest_path = output / "knowledge-layer-manifest.json"
    manifest_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized

def _knowledge_artifacts(
    *,
    contract: Mapping[str, Any],
    materialization_id: str,
    manifest: Mapping[str, Any],
    output: Path,
) -> list[dict[str, Any]]:
    manifest_path = output / "knowledge-layer-manifest.json"
    manifest_fingerprint = _fingerprint(manifest)
    models = [str(item) for item in ((contract.get("outputs") or {}).get("models") or [])]
    artifacts: list[dict[str, Any]] = []
    all_contracts = [item.to_dict() for item in CURRENT_MATERIALIZATIONS]
    for schema_version in models:
        dependent_model_kinds = sorted({
            str(requirement.get("model_kind") or "")
            for candidate in all_contracts
            for group in ("required_knowledge_models", "optional_knowledge_models")
            for requirement in ((candidate.get("input_contract") or {}).get(group) or [])
            if isinstance(requirement, Mapping)
            and str(requirement.get("source_materialization_id") or "") == materialization_id
            and schema_version in {str(value) for value in (requirement.get("schema_versions") or [])}
            and str(requirement.get("model_kind") or "")
        })
        model_kinds = dependent_model_kinds or [schema_version.rsplit("/", 1)[0]]
        for model_kind in model_kinds:
            artifacts.append({
                "artifact_id": stable_id("knowledge_artifact", materialization_id, model_kind, schema_version, manifest_fingerprint),
                "model_kind": model_kind,
                "schema_version": schema_version,
                "source_materialization_id": materialization_id,
                "content_fingerprint": manifest_fingerprint,
                "location": {
                    "kind": "knowledge-layer",
                    "output_path": str(output),
                    "manifest_path": str(manifest_path),
                },
                "coverage": dict(manifest.get("metadata") or {}).get("coverage") or {},
                "diagnostics": _manifest_diagnostics(manifest),
            })
    return artifacts


def materialize(
    request: Mapping[str, Any],
    output: str | Path,
    *,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute one registered KLC materialization through a stable generic boundary."""
    if not isinstance(request, Mapping):
        raise ValueError("materialization request must be an object")
    if request.get("schema_version") != MATERIALIZATION_REQUEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported materialization request schema: {request.get('schema_version')!r}; "
            f"expected {MATERIALIZATION_REQUEST_SCHEMA_VERSION!r}"
        )
    materialization_id = _require_text(request.get("materialization_id"), field="materialization_id")
    scope_id = _require_text(request.get("scope_id"), field="scope_id")
    handler = _HANDLERS.get(materialization_id)
    if handler is None:
        raise ValueError(f"materialization is not registered in KLC runtime: {materialization_id!r}")
    contract = _materialization_contract(materialization_id)
    evidence = _validate_evidence_inputs(contract, request)
    knowledge = _validate_knowledge_inputs(contract, request)
    output_path = Path(output).expanduser().resolve()
    started_at = utc_now()
    request_fingerprint = _fingerprint(_semantic_request_material(request))
    execution_id = stable_id(
        "knowledge_materialization_execution",
        materialization_id,
        scope_id,
        request_fingerprint,
        __version__,
    )
    with bind_progress(progress):
        emit_progress(f"materialization {materialization_id} handler started")
        manifest = handler.invoke(
            request,
            output_path,
            scope_id,
            replace,
            duckdb_memory_limit,
            duckdb_threads,
        )
        manifest = _canonicalize_knowledge_product_manifest(manifest, output=output_path)
        emit_progress(f"materialization {materialization_id} handler completed")
    completed_at = utc_now()
    actual_capabilities = sorted({str(item) for item in (manifest.get("capabilities") or []) if str(item)})
    declared_capabilities = sorted({str(item) for item in ((contract.get("outputs") or {}).get("capabilities") or []) if str(item)})
    conditional_capabilities = sorted({
        str(item)
        for item in ((contract.get("outputs") or {}).get("conditional_capabilities") or [])
        if str(item)
    })
    undeclared = sorted(
        set(actual_capabilities) - set(declared_capabilities) - set(conditional_capabilities)
    )
    if undeclared:
        raise ValueError(f"materialization published undeclared capabilities: {undeclared}")
    result = {
        "schema_version": MATERIALIZATION_EXECUTION_RESULT_SCHEMA_VERSION,
        "runtime_contract_id": MATERIALIZATION_RUNTIME_CONTRACT_ID,
        "execution_id": execution_id,
        "materialization_id": materialization_id,
        "scope_id": scope_id,
        "producer": {"component": "knowledge-layer-core", "version": __version__},
        "request_fingerprint": request_fingerprint,
        "inputs": {
            "evidence_artifacts": [
                {
                    "artifact_id": item.get("artifact_id"),
                    "artifact_kind": item.get("artifact_kind"),
                    "schema_version": item.get("schema_version"),
                    "content_fingerprint": item.get("content_fingerprint"),
                    "registration_manifest_path": item.get("registration_manifest_path"),
                }
                for item in evidence
            ],
            "knowledge_artifacts": [
                {
                    "artifact_id": item.get("artifact_id"),
                    "model_kind": item.get("model_kind"),
                    "schema_version": item.get("schema_version"),
                    "source_materialization_id": item.get("source_materialization_id"),
                    "content_fingerprint": item.get("content_fingerprint"),
                }
                for item in knowledge
            ],
        },
        "output": {
            "path": str(output_path),
            "manifest_path": str(output_path / "knowledge-layer-manifest.json"),
            "counts": dict(manifest.get("counts") or {}),
            "materialized_marts": list(manifest.get("materialized_marts") or []),
        },
        "knowledge_artifacts": _knowledge_artifacts(
            contract=contract,
            materialization_id=materialization_id,
            manifest=manifest,
            output=output_path,
        ),
        "published_capabilities": actual_capabilities,
        "status": "completed",
        "started_at": started_at,
        "completed_at": completed_at,
        "diagnostics": _manifest_diagnostics(manifest),
    }
    result["result_fingerprint"] = _fingerprint(result)
    return result


def materialize_from_request_file(
    request_path: str | Path,
    output: str | Path,
    *,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    return materialize(
        _read_json_object(Path(request_path).expanduser().resolve()),
        output,
        replace=replace,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
        progress=progress,
    )
