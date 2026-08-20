from __future__ import annotations

from importlib import resources
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import yaml

from .version import __version__

KNOWLEDGE_CATALOG_SCHEMA_VERSION = "knowledge_catalog/v2"
KNOWLEDGE_PROFILE_SCHEMA_VERSION = "knowledge_profile/v2"
KNOWLEDGE_PROFILE_CONTRACT_ID = "knowledge_profile_contract/v2"
KNOWLEDGE_RESOLUTION_PLAN_SCHEMA_VERSION = "knowledge_resolution_plan/v2"
KNOWLEDGE_RESOLVER_CONTRACT_ID = "knowledge_resolver_contract/v2"
SUPPORTED_KLC_SCHEMA = "knowledge_materialization_catalog/v3"
SUPPORTED_CORE_TARGET_SCHEMA = "core_target_analysis_contracts/v1"
SUPPORTED_CORE_EVIDENCE_SCHEMA = "core_evidence_contract_catalog/v1"
SUPPORTED_EXECUTION_SCHEMA = "analysis_execution_result_catalog/v1"


# User-facing knowledge types are deliberately separate from technical materialization IDs.
# The catalog is compiled from the official KLC contract, while this policy provides
# stable product wording and explicitly marks internal materializations.
KNOWLEDGE_PRODUCT_CATALOG_SCHEMA_VERSION = "knowledge_product_catalog/v1"
DEFAULT_KNOWLEDGE_PRODUCT_CATALOG_RESOURCE = "knowledge-product-catalog.v1.json"


# Technical source policy for catalog presentation. It never changes evidence semantics.
_EVIDENCE_SOURCE_POLICY: dict[str, dict[str, Any]] = {
    "analysis-execution-result": {
        "foundation_requirements": [],
        "mapping_status": "contract_only_not_runtime_source",
        "producer_kind": "runner",
        "source_category": "execution",
        "title": "Результат выполнения анализа",
    },
    "interaction-coverage": {
        "foundation_requirements": [],
        "mapping_status": "current_klc_output",
        "producer_kind": "klc",
        "producer_materialization_id": "interaction-coverage",
        "source_category": "knowledge-output",
        "title": "Покрытие взаимодействий",
    },
    "physical-model": {
        "foundation_requirements": [],
        "mapping_status": "current_external_typed_artifact",
        "producer_kind": "external",
        "source_category": "external-model",
        "title": "Предоставленная физическая модель",
    },
    "repository-interaction-evidence": {
        "foundation_requirements": [],
        "mapping_status": "current_klc_output",
        "producer_kind": "klc",
        "producer_materialization_id": "system-interactions",
        "source_category": "knowledge-output",
        "title": "Сопоставленные взаимодействия репозиториев",
    },
    "repository-metadata": {
        "foundation_requirements": [],
        "mapping_status": "proposed_typed_metadata",
        "producer_kind": "runner",
        "source_category": "execution-input",
        "title": "Метаданные репозитория и системы",
    },
    "repository-value-flow": {
        "foundation_requirements": [],
        "mapping_status": "current_klc_output",
        "producer_kind": "klc",
        "producer_materialization_id": "repository-value-flow",
        "source_category": "knowledge-output",
        "title": "Граф потоков значений репозитория",
    },
}

_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_fingerprinted_payload(
    payload: Mapping[str, Any],
    *,
    expected_schema: str,
    fingerprint_field: str,
    label: str,
) -> None:
    schema = str(payload.get("schema_version") or "")
    if schema != expected_schema:
        raise ValueError(f"unsupported {label} schema: {schema!r}; expected {expected_schema!r}")
    actual = str(payload.get(fingerprint_field) or "")
    if not actual:
        raise ValueError(f"{label} has no {fingerprint_field}")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != fingerprint_field}
    expected = _fingerprint(material)
    if actual != expected:
        raise ValueError(f"{label} fingerprint does not match canonical content")


def load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def validate_knowledge_product_catalog(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        expected_schema=KNOWLEDGE_PRODUCT_CATALOG_SCHEMA_VERSION,
        fingerprint_field="catalog_fingerprint",
        label="knowledge product catalog",
    )
    catalog_id = str(payload.get("catalog_id") or "").strip()
    if not catalog_id:
        raise ValueError("knowledge product catalog catalog_id is required")
    entries = payload.get("knowledge_types")
    if not isinstance(entries, list) or not entries:
        raise ValueError("knowledge product catalog knowledge_types must be a non-empty list")

    by_id: dict[str, Mapping[str, Any]] = {}
    dependency_graph: dict[str, set[str]] = {}
    list_fields = {
        "contains",
        "supported_scopes",
        "required_knowledge_dependencies",
        "recommended_knowledge_dependencies",
        "knowledge_dependencies",
        "required_internal_materializations",
        "optional_internal_materializations",
    }
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"knowledge product catalog entry {index} must be an object")
        knowledge_id = str(entry.get("knowledge_id") or "")
        if not _PROFILE_ID_RE.fullmatch(knowledge_id):
            raise ValueError(
                f"knowledge product catalog entry {index} knowledge_id must match ^[a-z0-9][a-z0-9._-]{{1,127}}$"
            )
        if knowledge_id in by_id:
            raise ValueError(f"duplicate knowledge product knowledge_id: {knowledge_id}")
        materialization_id = str(entry.get("materialization_id") or "").strip()
        if not materialization_id:
            raise ValueError(f"knowledge product {knowledge_id!r} has no materialization_id")
        for field in ("title", "summary", "category"):
            if not str(entry.get(field) or "").strip():
                raise ValueError(f"knowledge product {knowledge_id!r} field {field!r} is required")
        for field in list_fields:
            value = entry.get(field)
            if value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
                raise ValueError(f"knowledge product {knowledge_id!r} field {field!r} must be a list of strings")
        scopes = set(str(value) for value in entry.get("supported_scopes") or [])
        if not scopes or not scopes.issubset({"repository", "workspace"}):
            raise ValueError(
                f"knowledge product {knowledge_id!r} supported_scopes must be a non-empty subset of repository/workspace"
            )
        input_mode = str(entry.get("knowledge_input_mode") or "materialize_dependencies")
        if input_mode not in {"materialize_dependencies", "existing_artifacts_only"}:
            raise ValueError(f"knowledge product {knowledge_id!r} has unsupported knowledge_input_mode {input_mode!r}")
        by_id[knowledge_id] = entry

    known = set(by_id)
    for knowledge_id, entry in sorted(by_id.items()):
        dependencies = set(str(value) for value in entry.get("required_knowledge_dependencies") or [])
        dependencies.update(str(value) for value in entry.get("recommended_knowledge_dependencies") or [])
        dependencies.update(str(value) for value in entry.get("knowledge_dependencies") or [])
        unknown = sorted(dependencies - known)
        if unknown:
            raise ValueError(
                f"knowledge product {knowledge_id!r} references unknown knowledge dependencies: {unknown}"
            )
        if knowledge_id in dependencies:
            raise ValueError(f"knowledge product {knowledge_id!r} cannot depend on itself")
        dependency_graph[knowledge_id] = dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(knowledge_id: str, trail: tuple[str, ...]) -> None:
        if knowledge_id in visited:
            return
        if knowledge_id in visiting:
            cycle = " -> ".join((*trail, knowledge_id))
            raise ValueError(f"knowledge product dependency cycle detected: {cycle}")
        visiting.add(knowledge_id)
        for dependency in sorted(dependency_graph.get(knowledge_id) or []):
            visit(dependency, (*trail, knowledge_id))
        visiting.remove(knowledge_id)
        visited.add(knowledge_id)

    for knowledge_id in sorted(dependency_graph):
        visit(knowledge_id, ())

    internal = payload.get("internal_materializations") or []
    if not isinstance(internal, list):
        raise ValueError("knowledge product catalog internal_materializations must be a list")
    seen_internal: set[str] = set()
    for index, entry in enumerate(internal):
        if not isinstance(entry, Mapping):
            raise ValueError(f"internal materialization entry {index} must be an object")
        materialization_id = str(entry.get("materialization_id") or "").strip()
        reason = str(entry.get("reason_not_user_selectable") or "").strip()
        if not materialization_id or not reason:
            raise ValueError(
                f"internal materialization entry {index} requires materialization_id and reason_not_user_selectable"
            )
        if materialization_id in seen_internal:
            raise ValueError(f"duplicate internal materialization_id: {materialization_id}")
        seen_internal.add(materialization_id)

    for knowledge_id, entry in sorted(by_id.items()):
        required_internal = set(str(value) for value in entry.get("required_internal_materializations") or [])
        optional_internal = set(str(value) for value in entry.get("optional_internal_materializations") or [])
        unknown_internal = sorted((required_internal | optional_internal) - seen_internal)
        if unknown_internal:
            raise ValueError(
                f"knowledge product {knowledge_id!r} references unknown internal materializations: {unknown_internal}"
            )
        overlap = sorted(required_internal & optional_internal)
        if overlap:
            raise ValueError(
                f"knowledge product {knowledge_id!r} marks internal materializations as both required and optional: {overlap}"
            )


def load_knowledge_product_catalog(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        resource = resources.files("static_analysis_runner").joinpath(
            "resources", DEFAULT_KNOWLEDGE_PRODUCT_CATALOG_RESOURCE
        )
        payload = json.loads(resource.read_text(encoding="utf-8"))
    else:
        payload = load_json_object(path, label="knowledge product catalog")
    if not isinstance(payload, dict):
        raise ValueError("knowledge product catalog must be a JSON object")
    validate_knowledge_product_catalog(payload)
    return deepcopy(payload)


def _knowledge_product_policy_index(product_catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in product_catalog.get("knowledge_types") or []:
        knowledge_id = str(entry.get("knowledge_id") or "")
        policy = deepcopy(dict(entry))
        policy.pop("knowledge_id", None)
        result[knowledge_id] = policy
    return result


def _internal_materialization_policy(product_catalog: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(entry.get("materialization_id") or ""): str(entry.get("reason_not_user_selectable") or "")
        for entry in product_catalog.get("internal_materializations") or []
    }


def load_profile(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("knowledge profile must be an object")
    return payload


def _materializations_by_id(klc: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    values = klc.get("materializations") or []
    if not isinstance(values, list):
        raise ValueError("KLC materialization catalog field 'materializations' must be a list")
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("KLC materialization entry must be an object")
        materialization_id = str(value.get("materialization_id") or "")
        if not materialization_id:
            raise ValueError("KLC materialization entry has no materialization_id")
        if materialization_id in result:
            raise ValueError(f"duplicate KLC materialization_id: {materialization_id}")
        result[materialization_id] = deepcopy(dict(value))
    return result


def _validate_inputs(
    klc: Mapping[str, Any],
    core: Mapping[str, Any],
    core_evidence: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    _validate_fingerprinted_payload(
        klc,
        expected_schema=SUPPORTED_KLC_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="KLC materialization catalog",
    )
    _validate_fingerprinted_payload(
        core,
        expected_schema=SUPPORTED_CORE_TARGET_SCHEMA,
        fingerprint_field="contracts_fingerprint",
        label="Core target contracts",
    )
    _validate_fingerprinted_payload(
        core_evidence,
        expected_schema=SUPPORTED_CORE_EVIDENCE_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="Core evidence contract catalog",
    )
    _validate_fingerprinted_payload(
        execution,
        expected_schema=SUPPORTED_EXECUTION_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="Runner execution result catalog",
    )
    if str((klc.get("contract") or {}).get("contract_id") or "") != "knowledge_materialization_contract/v3":
        raise ValueError("KLC catalog is missing knowledge_materialization_contract/v3")
    if str((core.get("contracts") or {}).get("evidence_artifact", {}).get("contract_id") or "") != "core_evidence_artifact_contract/v1":
        raise ValueError("Core target contracts are missing core_evidence_artifact_contract/v1")
    if str((execution.get("contract") or {}).get("contract_id") or "") != "analysis_execution_result_contract/v1":
        raise ValueError("Runner catalog is missing analysis_execution_result_contract/v1")
    if str(core_evidence.get("artifact_envelope_contract") or "") != "core_evidence_artifact_contract/v1":
        raise ValueError("Core evidence catalog is missing core_evidence_artifact_contract/v1")


def _runtime_availability(materialization: Mapping[str, Any]) -> dict[str, Any]:
    runtime = ((materialization.get("current_implementation") or {}).get("runtime") or {})
    materialization_id = str(materialization.get("materialization_id") or "")
    runtime_registered = (
        runtime.get("registered") is True
        and str(runtime.get("contract_id") or "") == "knowledge_materialization_runtime/v1"
        and str(runtime.get("handler_id") or "") == materialization_id
    )
    if runtime_registered:
        return {
            "status": "current_typed",
            "business_knowledge_available_now": True,
            "target_contract_status": "current",
            "can_execute_through_target_contracts": True,
            "runtime_handler_id": materialization_id,
            "explanation": "Materialization зарегистрирована в общем KLC runtime и исполняется через типизированный контракт.",
        }
    return {
        "status": "unavailable_unregistered",
        "business_knowledge_available_now": False,
        "target_contract_status": "unavailable",
        "can_execute_through_target_contracts": False,
        "runtime_handler_id": None,
        "explanation": "Materialization описана текущим KLC контрактом, но не зарегистрирована в общем runtime; скрытый fallback не используется.",
    }


def _core_evidence_contract_index(
    core_evidence: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in core_evidence.get("contracts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core evidence catalog contains a non-object contract")
        item = deepcopy(dict(raw))
        key = (
            str(item.get("artifact_kind") or "").strip(),
            str(item.get("schema_version") or "").strip(),
        )
        if not all(key) or key in result:
            raise ValueError(f"invalid or duplicate Core evidence contract identity: {key}")
        result[key] = item
    return result


def _evidence_source(
    evidence: Mapping[str, Any],
    *,
    core_evidence_contracts: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    artifact_kind = str(evidence.get("artifact_kind") or "")
    if not artifact_kind:
        raise ValueError("materialization evidence entry has no artifact_kind")
    schema_versions = sorted(str(value) for value in evidence.get("schema_versions") or [])
    core_contracts = [
        deepcopy(dict(core_evidence_contracts[(artifact_kind, schema_version)]))
        for schema_version in schema_versions
        if (artifact_kind, schema_version) in core_evidence_contracts
    ]
    if core_contracts:
        if len(core_contracts) != len(schema_versions):
            missing = sorted(
                schema_version
                for schema_version in schema_versions
                if (artifact_kind, schema_version) not in core_evidence_contracts
            )
            raise ValueError(
                f"Core evidence family {artifact_kind!r} has only a partial contract set; missing schemas: {missing}"
            )
        analyzer_ids = sorted({
            str((contract.get("runtime_publication") or {}).get("producer_analyzer_id")
                or (contract.get("producer") or {}).get("target_analyzer_id")
                or "")
            for contract in core_contracts
            if str((contract.get("runtime_publication") or {}).get("producer_analyzer_id")
                   or (contract.get("producer") or {}).get("target_analyzer_id")
                   or "")
        })
        registration_statuses = sorted({
            str((contract.get("runtime_publication") or {}).get("registration_status") or "not_registered")
            for contract in core_contracts
        })
        runtime_contract_ids = sorted({
            str((contract.get("runtime_publication") or {}).get("runtime_contract_id") or "")
            for contract in core_contracts
            if str((contract.get("runtime_publication") or {}).get("runtime_contract_id") or "")
        })
        runtime_published = all(status == "registered" for status in registration_statuses)
        return {
            "artifact_kind": artifact_kind,
            "schema_versions": schema_versions,
            "contract_status": str(evidence.get("contract_status") or "unknown"),
            "purpose": str(evidence.get("purpose") or ""),
            "production_policy": str(evidence.get("production_policy") or "produce_if_missing"),
            "title": str(core_contracts[0].get("title") or artifact_kind),
            "source_category": str(core_contracts[0].get("source_category") or "source-code"),
            "producer_kind": "core",
            "producer_materialization_id": None,
            "analyzer_ids": analyzer_ids,
            "producer_registration_status": "registered" if runtime_published else "not_registered",
            "runtime_contract_ids": runtime_contract_ids,
            "source_languages": sorted({
                str((contract.get("producer") or {}).get("source_language") or "")
                for contract in core_contracts
                if str((contract.get("producer") or {}).get("source_language") or "")
            }),
            "mapping_status": "runtime_published" if runtime_published else "contract_defined_not_runtime_published",
            "runtime_publication": "current" if runtime_published else "not_implemented",
            "foundation_requirements": sorted({
                str(value)
                for contract in core_contracts
                for value in ((contract.get("producer") or {}).get("required_foundation_sections") or [])
            }),
            "core_contract_fingerprints": sorted(
                str(contract.get("contract_fingerprint") or "")
                for contract in core_contracts
                if str(contract.get("contract_fingerprint") or "")
            ),
        }

    policy = deepcopy(_EVIDENCE_SOURCE_POLICY.get(artifact_kind) or {
        "title": artifact_kind,
        "source_category": "unknown",
        "producer_kind": "unknown",
        "mapping_status": "contract_not_registered_by_a_producer",
        "foundation_requirements": [],
    })
    mapping_status = str(policy.get("mapping_status") or "contract_not_registered_by_a_producer")
    return {
        "artifact_kind": artifact_kind,
        "schema_versions": schema_versions,
        "contract_status": str(evidence.get("contract_status") or "unknown"),
        "purpose": str(evidence.get("purpose") or ""),
        "production_policy": str(evidence.get("production_policy") or "produce_if_missing"),
        "title": str(policy.get("title") or artifact_kind),
        "source_category": str(policy.get("source_category") or "unknown"),
        "producer_kind": str(policy.get("producer_kind") or "unknown"),
        "producer_materialization_id": policy.get("producer_materialization_id"),
        "analyzer_ids": [],
        "producer_registration_status": "not_applicable",
        "runtime_contract_ids": [],
        "source_languages": [],
        "mapping_status": mapping_status,
        "runtime_publication": "current" if mapping_status.startswith("current_") else "not_implemented",
        "foundation_requirements": sorted(str(value) for value in policy.get("foundation_requirements") or []),
        "core_contract_fingerprints": [],
    }


def _knowledge_model_source(model: Mapping[str, Any]) -> dict[str, Any]:
    model_kind = str(model.get("model_kind") or "")
    source_materialization_id = str(model.get("source_materialization_id") or "")
    if not model_kind or not source_materialization_id:
        raise ValueError("materialization knowledge model input must define model_kind and source_materialization_id")
    return {
        "model_kind": model_kind,
        "schema_versions": sorted(str(value) for value in model.get("schema_versions") or []),
        "source_materialization_id": source_materialization_id,
        "purpose": str(model.get("purpose") or ""),
        "semantic_selector": "model_kind_plus_schema_version",
    }


def _build_knowledge_type(
    knowledge_id: str,
    policy: Mapping[str, Any],
    materialization: Mapping[str, Any],
    *,
    core_evidence_contracts: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    input_contract = materialization.get("input_contract") or {}
    required = [
        _evidence_source(value, core_evidence_contracts=core_evidence_contracts)
        for value in (input_contract.get("required_evidence") or [])
    ]
    optional = [
        _evidence_source(value, core_evidence_contracts=core_evidence_contracts)
        for value in (input_contract.get("optional_evidence") or [])
    ]
    required_models = [
        _knowledge_model_source(value)
        for value in (input_contract.get("required_knowledge_models") or [])
    ]
    optional_models = [
        _knowledge_model_source(value)
        for value in (input_contract.get("optional_knowledge_models") or [])
    ]
    availability = _runtime_availability(materialization)
    profile_selectable = bool(policy.get("profile_v2_selectable", True))
    supported_scopes = [str(value) for value in policy.get("supported_scopes") or []]
    if not set(supported_scopes).intersection({"repository", "workspace"}):
        profile_selectable = False
    return {
        "knowledge_id": knowledge_id,
        "title": str(policy.get("title") or knowledge_id),
        "summary": str(policy.get("summary") or materialization.get("definition") or ""),
        "category": str(policy.get("category") or "other"),
        "contains": [str(value) for value in policy.get("contains") or []],
        "supported_scopes": supported_scopes,
        "scope_behavior": policy.get("scope_behavior"),
        "source_note": policy.get("source_note"),
        "knowledge_input_mode": str(policy.get("knowledge_input_mode") or "materialize_dependencies"),
        "required_knowledge_dependencies": sorted(str(value) for value in policy.get("required_knowledge_dependencies") or []),
        "required_internal_materializations": sorted(str(value) for value in policy.get("required_internal_materializations") or []),
        "optional_internal_materializations": sorted(str(value) for value in policy.get("optional_internal_materializations") or []),
        "recommended_knowledge_dependencies": sorted(str(value) for value in (policy.get("recommended_knowledge_dependencies") or policy.get("knowledge_dependencies") or [])),
        "profile_v2_selectable": profile_selectable,
        "selection_note": policy.get("selection_note"),
        "availability": availability,
        "materialization": {
            "materialization_id": str(materialization.get("materialization_id") or ""),
            "scope": str(materialization.get("scope") or ""),
            "lifecycle": str(materialization.get("lifecycle") or ""),
            "definition": str(materialization.get("definition") or ""),
            "models": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("models") or [])),
            "capabilities": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("capabilities") or [])),
            "conditional_capabilities": sorted(
                str(value)
                for value in ((materialization.get("outputs") or {}).get("conditional_capabilities") or [])
            ),
            "materialized_marts": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("materialized_marts") or [])),
        },
        "sources": {
            "required": required,
            "optional": optional,
        },
        "knowledge_inputs": {
            "required": required_models,
            "optional": optional_models,
        },
        "expected_metadata": [
            "coverage",
            "diagnostics",
            "provenance",
            "content_fingerprint",
        ],
    }


def _build_internal_materialization(
    materialization: Mapping[str, Any],
    *,
    reason_not_user_selectable: str,
    core_evidence_contracts: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    input_contract = materialization.get("input_contract") or {}
    return {
        "materialization_id": str(materialization.get("materialization_id") or ""),
        "reason_not_user_selectable": reason_not_user_selectable,
        "lifecycle": str(materialization.get("lifecycle") or ""),
        "scope": str(materialization.get("scope") or ""),
        "definition": str(materialization.get("definition") or ""),
        "sources": {
            "required": [
                _evidence_source(value, core_evidence_contracts=core_evidence_contracts)
                for value in (input_contract.get("required_evidence") or [])
            ],
            "optional": [
                _evidence_source(value, core_evidence_contracts=core_evidence_contracts)
                for value in (input_contract.get("optional_evidence") or [])
            ],
        },
        "knowledge_inputs": {
            "required": [
                _knowledge_model_source(value)
                for value in (input_contract.get("required_knowledge_models") or [])
            ],
            "optional": [
                _knowledge_model_source(value)
                for value in (input_contract.get("optional_knowledge_models") or [])
            ],
        },
        "materialization": {
            "materialization_id": str(materialization.get("materialization_id") or ""),
            "scope": str(materialization.get("scope") or ""),
            "lifecycle": str(materialization.get("lifecycle") or ""),
            "definition": str(materialization.get("definition") or ""),
            "models": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("models") or [])),
            "capabilities": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("capabilities") or [])),
            "conditional_capabilities": sorted(
                str(value)
                for value in ((materialization.get("outputs") or {}).get("conditional_capabilities") or [])
            ),
            "materialized_marts": sorted(str(value) for value in ((materialization.get("outputs") or {}).get("materialized_marts") or [])),
        },
    }


def _profile_contract() -> dict[str, Any]:
    return {
        "contract_id": KNOWLEDGE_PROFILE_CONTRACT_ID,
        "schema_version": KNOWLEDGE_PROFILE_SCHEMA_VERSION,
        "owner": "product-control-plane",
        "definition": "User-owned selection of knowledge for one repository or workspace business scope.",
        "required_fields": ["schema_version", "profile_id", "title", "scope", "knowledge", "presentation"],
        "scope": {
            "supported_kinds": ["repository", "workspace"],
            "required_fields": ["kind", "scope_id"],
        },
        "knowledge_entry": {
            "required_fields": ["knowledge_id"],
            "optional_fields": ["options"],
        },
        "business_options": {
            "include_optional_sources": "boolean",
            "minimum_coverage": "number_0_to_1_or_null",
        },
        "presentation_options": {
            "include_evidence": "boolean",
            "include_coverage": "boolean",
            "include_gaps": "boolean",
            "include_technical_details": "boolean",
        },
        "forbidden_user_fields": [
            "task_id", "suite_id", "core_profile_id", "stage_id", "analyzer_id",
            "materialization_id", "artifact_kind", "schema_version_override", "output_file",
        ],
    }


def _resolver_contract() -> dict[str, Any]:
    return {
        "contract_id": KNOWLEDGE_RESOLVER_CONTRACT_ID,
        "schema_version": KNOWLEDGE_RESOLUTION_PLAN_SCHEMA_VERSION,
        "owner": "static-analysis-runner-control-plane",
        "definition": "Deterministically compile a user knowledge profile into KLC materializations, evidence requirements, Core sources and Foundation requirements.",
        "execution_effect": "none",
        "rules": [
            "User selects knowledge, not Core stages, analyzers or KLC materializations.",
            "Materializations are resolved from knowledge_catalog/v2.",
            "Required knowledge dependencies are expanded deterministically; recommended dependencies remain optional diagnostics.",
            "Different source families remain separate knowledge and are never treated as interchangeable inputs.",
            "Evidence semantics are resolved by artifact_kind + schema_version.",
            "Required evidence is never silently downgraded to optional evidence.",
            "Actual repository source availability is not inferred in contract-only mode.",
            "Removed Task/Suite selectors are not accepted by the installed runtime.",
        ],
    }


def build_knowledge_catalog(
    klc: Mapping[str, Any],
    core: Mapping[str, Any],
    core_evidence: Mapping[str, Any],
    execution: Mapping[str, Any],
    *,
    product_catalog: Mapping[str, Any] | None = None,
    product_catalog_source: str | None = None,
) -> dict[str, Any]:
    _validate_inputs(klc, core, core_evidence, execution)
    if product_catalog is None:
        product_catalog = load_knowledge_product_catalog()
        effective_product_catalog_source = product_catalog_source or "packaged-default"
    else:
        validate_knowledge_product_catalog(product_catalog)
        product_catalog = deepcopy(dict(product_catalog))
        effective_product_catalog_source = product_catalog_source or "external"
    knowledge_policy = _knowledge_product_policy_index(product_catalog)
    internal_materialization_policy = _internal_materialization_policy(product_catalog)

    core_evidence_contracts = _core_evidence_contract_index(core_evidence)
    materializations = _materializations_by_id(klc)
    knowledge_types: list[dict[str, Any]] = []
    for knowledge_id in sorted(knowledge_policy):
        policy = knowledge_policy[knowledge_id]
        materialization_id = str(policy["materialization_id"])
        materialization = materializations.get(materialization_id)
        if materialization is None:
            raise ValueError(
                f"knowledge product {knowledge_id!r} references missing KLC materialization {materialization_id!r}"
            )
        knowledge_types.append(
            _build_knowledge_type(knowledge_id, policy, materialization, core_evidence_contracts=core_evidence_contracts)
        )

    knowledge_by_id = {str(value["knowledge_id"]): value for value in knowledge_types}
    materialization_to_knowledge: dict[str, set[str]] = {}
    for value in knowledge_types:
        materialization_id = str((value.get("materialization") or {}).get("materialization_id") or "")
        if materialization_id:
            materialization_to_knowledge.setdefault(materialization_id, set()).add(str(value["knowledge_id"]))
    for knowledge_id, value in sorted(knowledge_by_id.items()):
        required_dependencies = set(str(item) for item in value.get("required_knowledge_dependencies") or [])
        recommended_dependencies = set(str(item) for item in value.get("recommended_knowledge_dependencies") or [])
        unknown = sorted((required_dependencies | recommended_dependencies) - set(knowledge_by_id))
        if unknown:
            raise ValueError(f"knowledge product {knowledge_id!r} references unknown knowledge dependencies: {unknown}")
        if knowledge_id in required_dependencies or knowledge_id in recommended_dependencies:
            raise ValueError(f"knowledge product {knowledge_id!r} cannot depend on itself")
        required_model_sources = {
            str(item.get("source_materialization_id") or "")
            for item in (value.get("knowledge_inputs") or {}).get("required") or []
        }
        missing_dependency_declarations: list[str] = []
        for source in sorted(required_model_sources):
            candidate_knowledge_ids = materialization_to_knowledge.get(source, set())
            if candidate_knowledge_ids and not candidate_knowledge_ids.intersection(required_dependencies):
                missing_dependency_declarations.append(source)
        if str(value.get("knowledge_input_mode") or "materialize_dependencies") == "existing_artifacts_only":
            missing_dependency_declarations = []
        if missing_dependency_declarations:
            raise ValueError(
                f"knowledge product {knowledge_id!r} is missing required dependency declarations for KLC model inputs: "
                f"{missing_dependency_declarations}"
            )

    internal_materializations = []
    for materialization_id, reason in sorted(internal_materialization_policy.items()):
        materialization = materializations.get(materialization_id)
        if materialization is None:
            raise ValueError(f"internal materialization policy references missing {materialization_id!r}")
        internal_materializations.append(
            _build_internal_materialization(
                materialization,
                reason_not_user_selectable=reason,
                core_evidence_contracts=core_evidence_contracts,
            )
        )

    mapped_materializations = {
        str(value["materialization"]["materialization_id"])
        for value in knowledge_types
    } | set(internal_materialization_policy)
    uncatalogued = sorted(set(materializations) - mapped_materializations)

    selectable = [value for value in knowledge_types if value["profile_v2_selectable"]]
    runtime_counts: dict[str, int] = {}
    for value in selectable:
        status = str(value["availability"]["status"])
        runtime_counts[status] = runtime_counts.get(status, 0) + 1

    business_available_now_count = sum(
        bool((value.get("availability") or {}).get("business_knowledge_available_now"))
        for value in selectable
    )
    target_contract_ready_count = sum(
        bool((value.get("availability") or {}).get("can_execute_through_target_contracts"))
        for value in selectable
    )

    payload: dict[str, Any] = {
        "schema_version": KNOWLEDGE_CATALOG_SCHEMA_VERSION,
        "runner_version": __version__,
        "purpose": "User-facing catalog of selectable KLC knowledge and deterministic source lineage to Core evidence producers.",
        "architecture_goal": {
            "developer_creates": ["Core analyzers", "evidence schemas", "KLC materializations", "knowledge types"],
            "user_selects": ["repository or workspace scope", "knowledge types", "business-level options"],
            "system_resolves": ["materializations", "evidence", "Core sources", "Foundation requirements", "execution plan"],
            "ui_previews": ["knowledge contents", "required and optional sources", "runtime availability", "expected gaps", "technical lineage on demand"],
        },
        "execution_effect": "none",
        "source": {
            "knowledge_product_catalog_schema": product_catalog.get("schema_version"),
            "knowledge_product_catalog_fingerprint": product_catalog.get("catalog_fingerprint"),
            "knowledge_product_catalog_id": product_catalog.get("catalog_id"),
            "knowledge_product_catalog_source": effective_product_catalog_source,
            "klc_materialization_catalog_schema": klc.get("schema_version"),
            "klc_materialization_catalog_fingerprint": klc.get("catalog_fingerprint"),
            "core_target_contracts_schema": core.get("schema_version"),
            "core_target_contracts_fingerprint": core.get("contracts_fingerprint"),
            "core_evidence_contract_catalog_schema": core_evidence.get("schema_version"),
            "core_evidence_contract_catalog_fingerprint": core_evidence.get("catalog_fingerprint"),
            "execution_result_catalog_schema": execution.get("schema_version"),
            "execution_result_catalog_fingerprint": execution.get("catalog_fingerprint"),
        },
        "contracts": {
            "knowledge_profile": _profile_contract(),
            "knowledge_resolver": _resolver_contract(),
        },
        "knowledge_types": knowledge_types,
        "data_model_knowledge_decomposition": {
            "source_contract": "knowledge_materialization_catalog/v3",
            "independent_knowledge_ids": [
                "code-declared-data-model", "physical-data-model", "logical-physical-mapping",
                "sql-source-inventory", "observed-storage-usage"
            ],
            "composite_knowledge_ids": ["effective-data-model"],
            "rule": "Different source families produce different knowledge; composite knowledge is resolved through explicit knowledge dependencies.",
        },
        "internal_materializations": internal_materializations,
        "current_state_assessment": {
            "source_availability_mode": "contract_only_repository_not_scanned",
            "uncatalogued_materialization_ids": uncatalogued,
            "proposed_evidence_kinds": sorted({
                source["artifact_kind"]
                for knowledge in knowledge_types
                for group in ("required", "optional")
                for source in knowledge["sources"][group]
                if source["contract_status"] in {"proposed", "contract_only"}
            }),
            "technical_stage_visibility": "advanced_diagnostics_only",
        },
        "summary": {
            "knowledge_type_count": len(knowledge_types),
            "profile_v2_selectable_count": len(selectable),
            "internal_materialization_count": len(internal_materializations),
            "uncatalogued_materialization_count": len(uncatalogued),
            "runtime_status_counts": dict(sorted(runtime_counts.items())),
            "business_available_now_count": business_available_now_count,
            "target_contract_ready_count": target_contract_ready_count,
            "required_source_kind_count": len({
                source["artifact_kind"]
                for knowledge in selectable
                for source in knowledge["sources"]["required"]
            }),
        },
        "next_step": "resolve_knowledge_profile_then_compile_execution_plan",
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def validate_knowledge_catalog(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        expected_schema=KNOWLEDGE_CATALOG_SCHEMA_VERSION,
        fingerprint_field="catalog_fingerprint",
        label="knowledge catalog",
    )
    contracts = payload.get("contracts") or {}
    if str((contracts.get("knowledge_profile") or {}).get("contract_id") or "") != KNOWLEDGE_PROFILE_CONTRACT_ID:
        raise ValueError("knowledge catalog is missing knowledge_profile_contract/v2")
    if str((contracts.get("knowledge_resolver") or {}).get("contract_id") or "") != KNOWLEDGE_RESOLVER_CONTRACT_ID:
        raise ValueError("knowledge catalog is missing knowledge_resolver_contract/v2")


def validate_knowledge_profile(profile: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any]:
    validate_knowledge_catalog(catalog)
    if str(profile.get("schema_version") or "") != KNOWLEDGE_PROFILE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported knowledge profile schema: {profile.get('schema_version')!r}; expected {KNOWLEDGE_PROFILE_SCHEMA_VERSION!r}"
        )
    profile_id = str(profile.get("profile_id") or "")
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError("knowledge profile profile_id must match ^[a-z0-9][a-z0-9._-]{1,127}$")
    title = str(profile.get("title") or "").strip()
    if not title:
        raise ValueError("knowledge profile title is required")
    scope = profile.get("scope") or {}
    if not isinstance(scope, Mapping):
        raise ValueError("knowledge profile scope must be an object")
    scope_kind = str(scope.get("kind") or "")
    if scope_kind not in {"repository", "workspace"}:
        raise ValueError("knowledge profile scope.kind must be repository or workspace")
    scope_id = str(scope.get("scope_id") or "").strip()
    if not scope_id:
        raise ValueError("knowledge profile scope.scope_id is required")
    entries = profile.get("knowledge") or []
    if not isinstance(entries, list) or not entries:
        raise ValueError("knowledge profile knowledge must be a non-empty list")
    catalog_by_id = {
        str(value.get("knowledge_id") or ""): value
        for value in (catalog.get("knowledge_types") or [])
        if isinstance(value, Mapping)
    }
    public_knowledge_by_materialization: dict[str, set[str]] = {}
    for knowledge_id, knowledge in catalog_by_id.items():
        materialization_id = str((knowledge.get("materialization") or {}).get("materialization_id") or "")
        if materialization_id:
            public_knowledge_by_materialization.setdefault(materialization_id, set()).add(knowledge_id)
    internal_by_id = {
        str(value.get("materialization_id") or ""): value
        for value in (catalog.get("internal_materializations") or [])
        if isinstance(value, Mapping)
    }
    normalized_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"knowledge profile entry {index} must be an object")
        knowledge_id = str(entry.get("knowledge_id") or "")
        if not knowledge_id:
            raise ValueError(f"knowledge profile entry {index} has no knowledge_id")
        if knowledge_id in seen:
            raise ValueError(f"duplicate knowledge_id in profile: {knowledge_id}")
        seen.add(knowledge_id)
        knowledge = catalog_by_id.get(knowledge_id)
        if knowledge is None:
            raise ValueError(f"unknown knowledge_id: {knowledge_id}")
        if not bool(knowledge.get("profile_v2_selectable")):
            raise ValueError(f"knowledge_id {knowledge_id!r} is not selectable in knowledge_profile/v2")
        supported_scopes = set(str(value) for value in knowledge.get("supported_scopes") or [])
        if scope_kind not in supported_scopes:
            raise ValueError(
                f"knowledge_id {knowledge_id!r} does not support scope {scope_kind!r}; supported: {sorted(supported_scopes)}"
            )
        options = entry.get("options") or {}
        if not isinstance(options, Mapping):
            raise ValueError(f"knowledge profile entry {knowledge_id!r} options must be an object")
        unknown_option_keys = sorted(set(str(key) for key in options) - {"include_optional_sources", "minimum_coverage"})
        if unknown_option_keys:
            raise ValueError(f"knowledge profile entry {knowledge_id!r} has unsupported options: {unknown_option_keys}")
        include_optional = bool(options.get("include_optional_sources", True))
        minimum_coverage = options.get("minimum_coverage")
        if minimum_coverage is not None:
            if isinstance(minimum_coverage, bool) or not isinstance(minimum_coverage, (int, float)):
                raise ValueError(f"knowledge profile entry {knowledge_id!r} minimum_coverage must be a number or null")
            if not 0 <= float(minimum_coverage) <= 1:
                raise ValueError(f"knowledge profile entry {knowledge_id!r} minimum_coverage must be between 0 and 1")
            minimum_coverage = float(minimum_coverage)
        normalized_entries.append({
            "knowledge_id": knowledge_id,
            "options": {
                "include_optional_sources": include_optional,
                "minimum_coverage": minimum_coverage,
            },
        })

    presentation = profile.get("presentation") or {}
    if not isinstance(presentation, Mapping):
        raise ValueError("knowledge profile presentation must be an object")
    allowed_presentation = {"include_evidence", "include_coverage", "include_gaps", "include_technical_details"}
    unknown_presentation = sorted(set(str(key) for key in presentation) - allowed_presentation)
    if unknown_presentation:
        raise ValueError(f"knowledge profile has unsupported presentation options: {unknown_presentation}")

    forbidden_fields = set((catalog.get("contracts") or {}).get("knowledge_profile", {}).get("forbidden_user_fields") or [])
    found_forbidden: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                key_text = str(key)
                child = f"{path}.{key_text}" if path else key_text
                if key_text in forbidden_fields:
                    found_forbidden.append(child)
                walk(nested, child)
        elif isinstance(value, list):
            for i, nested in enumerate(value):
                walk(nested, f"{path}[{i}]")

    walk(profile, "")
    if found_forbidden:
        raise ValueError(f"knowledge profile contains forbidden technical fields: {sorted(found_forbidden)}")

    return {
        "schema_version": KNOWLEDGE_PROFILE_SCHEMA_VERSION,
        "profile_id": profile_id,
        "title": title,
        "scope": {"kind": scope_kind, "scope_id": scope_id},
        "knowledge": normalized_entries,
        "presentation": {
            "include_evidence": bool(presentation.get("include_evidence", True)),
            "include_coverage": bool(presentation.get("include_coverage", True)),
            "include_gaps": bool(presentation.get("include_gaps", True)),
            "include_technical_details": bool(presentation.get("include_technical_details", False)),
        },
    }


def resolve_knowledge_profile(catalog: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_knowledge_profile(profile, catalog)
    catalog_by_id = {
        str(value.get("knowledge_id") or ""): value
        for value in (catalog.get("knowledge_types") or [])
        if isinstance(value, Mapping)
    }
    public_knowledge_by_materialization: dict[str, set[str]] = {}
    for knowledge_id, knowledge in catalog_by_id.items():
        materialization_id = str((knowledge.get("materialization") or {}).get("materialization_id") or "")
        if materialization_id:
            public_knowledge_by_materialization.setdefault(materialization_id, set()).add(knowledge_id)
    internal_by_id = {
        str(value.get("materialization_id") or ""): value
        for value in (catalog.get("internal_materializations") or [])
        if isinstance(value, Mapping)
    }
    requested_ids = [str(value["knowledge_id"]) for value in normalized["knowledge"]]
    requested_set = set(requested_ids)
    requested_options = {str(value["knowledge_id"]): deepcopy(value["options"]) for value in normalized["knowledge"]}
    scope_kind = str((normalized.get("scope") or {}).get("kind") or "")
    resolved_entries: dict[str, dict[str, Any]] = {}
    resolving: set[str] = set()

    def add_knowledge(knowledge_id: str, *, origin: str, required_by: str | None = None) -> None:
        if knowledge_id in resolving:
            raise ValueError(f"cyclic required knowledge dependency detected at {knowledge_id!r}")
        knowledge = catalog_by_id.get(knowledge_id)
        if knowledge is None:
            raise ValueError(f"required knowledge dependency is missing from catalog: {knowledge_id}")
        if not bool(knowledge.get("profile_v2_selectable")):
            raise ValueError(f"required knowledge dependency {knowledge_id!r} is not selectable")
        supported_scopes = set(str(value) for value in knowledge.get("supported_scopes") or [])
        if scope_kind not in supported_scopes:
            raise ValueError(
                f"required knowledge dependency {knowledge_id!r} does not support scope {scope_kind!r}; supported: {sorted(supported_scopes)}"
            )
        existing = resolved_entries.get(knowledge_id)
        if existing is not None:
            if required_by:
                existing["required_by"].add(required_by)
            if origin == "user_requested":
                existing["selection_origin"] = "user_requested"
            return
        resolving.add(knowledge_id)
        entry = {
            "knowledge_id": knowledge_id,
            "options": deepcopy(requested_options.get(knowledge_id) or {
                "include_optional_sources": True,
                "minimum_coverage": None,
            }),
            "selection_origin": origin,
            "required_by": set([required_by]) if required_by else set(),
        }
        resolved_entries[knowledge_id] = entry
        for dependency in sorted(str(value) for value in knowledge.get("required_knowledge_dependencies") or []):
            add_knowledge(dependency, origin="required_dependency", required_by=knowledge_id)
        resolving.remove(knowledge_id)

    for requested_id in requested_ids:
        add_knowledge(requested_id, origin="user_requested")

    resolved_ids = sorted(resolved_entries)
    resolved_set = set(resolved_ids)
    knowledge_preview: list[dict[str, Any]] = []
    materializations: list[dict[str, Any]] = []
    evidence_index: dict[tuple[str, str], dict[str, Any]] = {}
    knowledge_model_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    foundation_requirements: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    unresolved_dependencies: list[dict[str, str]] = []

    def merge_production_policy(current: str, incoming: str) -> str:
        values = {str(current or "produce_if_missing"), str(incoming or "produce_if_missing")}
        return "produce_if_missing" if "produce_if_missing" in values else "existing_only"

    readiness_statuses: list[str] = []
    for knowledge_id in resolved_ids:
        entry = resolved_entries[knowledge_id]
        knowledge = catalog_by_id[knowledge_id]
        options = entry["options"]
        availability = deepcopy(knowledge.get("availability") or {})
        readiness_statuses.append(str(availability.get("status") or "unknown"))
        required_dependencies = [str(value) for value in knowledge.get("required_knowledge_dependencies") or []]
        recommended_dependencies = [str(value) for value in knowledge.get("recommended_knowledge_dependencies") or []]
        for dependency in recommended_dependencies:
            if dependency not in resolved_set:
                unresolved_dependencies.append({"knowledge_id": knowledge_id, "recommended_dependency": dependency})
        source_groups = ["required"]
        if bool(options.get("include_optional_sources")):
            source_groups.append("optional")
        preview_sources: list[dict[str, Any]] = []
        for group in source_groups:
            for source in (knowledge.get("sources") or {}).get(group) or []:
                source_copy = deepcopy(source)
                source_copy["requirement"] = group
                source_copy["actual_source_availability"] = "not_assessed"
                preview_sources.append(source_copy)
                for schema_version in source_copy.get("schema_versions") or [""]:
                    key = (str(source_copy["artifact_kind"]), str(schema_version))
                    aggregate = evidence_index.setdefault(key, {
                        "artifact_kind": key[0],
                        "schema_version": key[1],
                        "title": source_copy.get("title"),
                        "producer_kind": source_copy.get("producer_kind"),
                        "contract_status": source_copy.get("contract_status"),
                        "mapping_status": source_copy.get("mapping_status"),
                        "production_policy": source_copy.get("production_policy") or "produce_if_missing",
                        "required_by": [],
                        "optional_by": [],
                        "analyzer_ids": [],
                        "producer_registration_status": source_copy.get("producer_registration_status"),
                        "runtime_contract_ids": [],
                        "source_languages": [],
                        "foundation_requirements": [],
                    })
                    target_list = aggregate["required_by"] if group == "required" else aggregate["optional_by"]
                    target_list.append(knowledge_id)
                    aggregate["production_policy"] = merge_production_policy(aggregate.get("production_policy"), source_copy.get("production_policy"))
                    aggregate["analyzer_ids"] = sorted(set(aggregate["analyzer_ids"]) | set(source_copy.get("analyzer_ids") or []))
                    aggregate["runtime_contract_ids"] = sorted(set(aggregate["runtime_contract_ids"]) | set(source_copy.get("runtime_contract_ids") or []))
                    aggregate["source_languages"] = sorted(set(aggregate["source_languages"]) | set(source_copy.get("source_languages") or []))
                    aggregate["foundation_requirements"] = sorted(set(aggregate["foundation_requirements"]) | set(source_copy.get("foundation_requirements") or []))
                    foundation_requirements.update(source_copy.get("foundation_requirements") or [])
        preview_knowledge_inputs: list[dict[str, Any]] = []
        for group in ("required", "optional"):
            for model in (knowledge.get("knowledge_inputs") or {}).get(group) or []:
                model_copy = deepcopy(model)
                model_copy["requirement"] = group
                preview_knowledge_inputs.append(model_copy)
                for schema_version in model_copy.get("schema_versions") or [""]:
                    key = (str(model_copy["model_kind"]), str(schema_version), str(model_copy["source_materialization_id"]))
                    aggregate = knowledge_model_index.setdefault(key, {
                        "model_kind": key[0],
                        "schema_version": key[1],
                        "source_materialization_id": key[2],
                        "purpose": model_copy.get("purpose"),
                        "required_by": [],
                        "optional_by": [],
                    })
                    target_list = aggregate["required_by"] if group == "required" else aggregate["optional_by"]
                    target_list.append(knowledge_id)

        materialization = deepcopy(knowledge.get("materialization") or {})
        materialization["knowledge_id"] = knowledge_id
        materialization["availability"] = availability
        materializations.append(materialization)
        knowledge_preview.append({
            "knowledge_id": knowledge_id,
            "title": knowledge.get("title"),
            "summary": knowledge.get("summary"),
            "contains": deepcopy(knowledge.get("contains") or []),
            "availability": availability,
            "expected_metadata": deepcopy(knowledge.get("expected_metadata") or []),
            "minimum_coverage": options.get("minimum_coverage"),
            "sources": preview_sources,
            "knowledge_inputs": preview_knowledge_inputs,
            "required_knowledge_dependencies": required_dependencies,
            "required_internal_materializations": sorted(str(value) for value in knowledge.get("required_internal_materializations") or []),
            "optional_internal_materializations": sorted(str(value) for value in knowledge.get("optional_internal_materializations") or []),
            "recommended_knowledge_dependencies": recommended_dependencies,
            "selection_origin": entry["selection_origin"],
            "required_by": sorted(entry["required_by"]),
        })

    internal_selected: dict[str, dict[str, Any]] = {}
    internal_resolving: set[str] = set()

    def add_evidence_requirement(source: Mapping[str, Any], *, requirement: str, consumer_id: str) -> None:
        for schema_version in source.get("schema_versions") or [""]:
            key = (str(source.get("artifact_kind") or ""), str(schema_version))
            aggregate = evidence_index.setdefault(key, {
                "artifact_kind": key[0],
                "schema_version": key[1],
                "title": source.get("title"),
                "producer_kind": source.get("producer_kind"),
                "contract_status": source.get("contract_status"),
                "mapping_status": source.get("mapping_status"),
                "production_policy": source.get("production_policy") or "produce_if_missing",
                "required_by": [],
                "optional_by": [],
                "analyzer_ids": [],
                "producer_registration_status": source.get("producer_registration_status"),
                "runtime_contract_ids": [],
                "source_languages": [],
                "foundation_requirements": [],
            })
            target_list = aggregate["required_by"] if requirement == "required" else aggregate["optional_by"]
            target_list.append(consumer_id)
            aggregate["production_policy"] = merge_production_policy(aggregate.get("production_policy"), source.get("production_policy"))
            aggregate["analyzer_ids"] = sorted(set(aggregate["analyzer_ids"]) | set(source.get("analyzer_ids") or []))
            aggregate["runtime_contract_ids"] = sorted(set(aggregate["runtime_contract_ids"]) | set(source.get("runtime_contract_ids") or []))
            aggregate["source_languages"] = sorted(set(aggregate["source_languages"]) | set(source.get("source_languages") or []))
            aggregate["foundation_requirements"] = sorted(set(aggregate["foundation_requirements"]) | set(source.get("foundation_requirements") or []))
            foundation_requirements.update(source.get("foundation_requirements") or [])

    def add_model_requirement(model: Mapping[str, Any], *, requirement: str, consumer_id: str) -> None:
        for schema_version in model.get("schema_versions") or [""]:
            key = (str(model.get("model_kind") or ""), str(schema_version), str(model.get("source_materialization_id") or ""))
            aggregate = knowledge_model_index.setdefault(key, {
                "model_kind": key[0],
                "schema_version": key[1],
                "source_materialization_id": key[2],
                "purpose": model.get("purpose"),
                "required_by": [],
                "optional_by": [],
            })
            target_list = aggregate["required_by"] if requirement == "required" else aggregate["optional_by"]
            target_list.append(consumer_id)

    def add_internal_materialization(
        materialization_id: str,
        *,
        required_by: str,
        requirement: str = "required",
    ) -> None:
        if requirement not in {"required", "optional"}:
            raise ValueError(f"unsupported internal materialization requirement: {requirement!r}")
        internal = internal_by_id.get(materialization_id)
        if internal is None:
            raise ValueError(f"internal materialization is missing from catalog: {materialization_id}")
        selected = internal_selected.setdefault(materialization_id, {
            "entry": internal,
            "required_by": set(),
            "optional_by": set(),
            "processed_requirement": None,
        })
        selected[f"{requirement}_by"].add(required_by)
        effective_requirement = "required" if selected["required_by"] else "optional"
        processed_requirement = selected.get("processed_requirement")
        if processed_requirement == "required" or processed_requirement == effective_requirement:
            return
        if materialization_id in internal_resolving:
            raise ValueError(f"cyclic internal materialization dependency detected at {materialization_id!r}")
        internal_resolving.add(materialization_id)
        consumer_id = f"internal:{materialization_id}"
        for source in (internal.get("sources") or {}).get("required") or []:
            add_evidence_requirement(source, requirement=effective_requirement, consumer_id=consumer_id)
        for source in (internal.get("sources") or {}).get("optional") or []:
            add_evidence_requirement(source, requirement="optional", consumer_id=consumer_id)
        for requirement in ("required", "optional"):
            for model in (internal.get("knowledge_inputs") or {}).get(requirement) or []:
                model_requirement = effective_requirement if requirement == "required" else "optional"
                add_model_requirement(model, requirement=model_requirement, consumer_id=consumer_id)
                source_materialization_id = str(model.get("source_materialization_id") or "")
                if requirement != "required" or not source_materialization_id:
                    continue
                if source_materialization_id in internal_by_id:
                    add_internal_materialization(
                        source_materialization_id,
                        required_by=consumer_id,
                        requirement=effective_requirement,
                    )
                    continue
                public_candidates = public_knowledge_by_materialization.get(source_materialization_id, set())
                if public_candidates and not public_candidates.intersection(resolved_set):
                    raise ValueError(
                        f"internal materialization {materialization_id!r} requires public knowledge from "
                        f"{source_materialization_id!r}, but none of {sorted(public_candidates)} is selected"
                    )
        selected["processed_requirement"] = effective_requirement
        internal_resolving.remove(materialization_id)

    for knowledge in knowledge_preview:
        knowledge_id = str(knowledge.get("knowledge_id") or "")
        for materialization_id in sorted(str(value) for value in knowledge.get("required_internal_materializations") or []):
            add_internal_materialization(materialization_id, required_by=knowledge_id, requirement="required")
        if knowledge_id in requested_options and bool(
            requested_options[knowledge_id].get("include_optional_sources", True)
        ):
            for materialization_id in sorted(str(value) for value in knowledge.get("optional_internal_materializations") or []):
                add_internal_materialization(materialization_id, required_by=knowledge_id, requirement="optional")
        for model in (knowledge.get("knowledge_inputs") or []):
            if str(model.get("requirement") or "") != "required":
                continue
            source_materialization_id = str(model.get("source_materialization_id") or "")
            if source_materialization_id in internal_by_id:
                add_internal_materialization(source_materialization_id, required_by=knowledge_id, requirement="required")

    for materialization_id in sorted(internal_selected):
        internal = internal_selected[materialization_id]["entry"]
        materialization = deepcopy(internal.get("materialization") or {})
        materialization["knowledge_id"] = None
        required_by = sorted(internal_selected[materialization_id]["required_by"])
        optional_by = sorted(set(internal_selected[materialization_id]["optional_by"]) - set(required_by))
        execution_requirement = "required" if required_by else "optional"
        materialization["selection_origin"] = (
            "internal_dependency" if execution_requirement == "required" else "optional_internal_enrichment"
        )
        materialization["execution_requirement"] = execution_requirement
        materialization["required_by"] = required_by
        materialization["optional_by"] = optional_by
        materializations.append(materialization)

    for item in evidence_index.values():
        item["required_by"] = sorted(set(item["required_by"]))
        item["optional_by"] = sorted(set(item["optional_by"]) - set(item["required_by"]))

    for item in knowledge_model_index.values():
        item["required_by"] = sorted(set(item["required_by"]))
        item["optional_by"] = sorted(set(item["optional_by"]) - set(item["required_by"]))


    typed = sum(status == "current_typed" for status in readiness_statuses)
    unavailable = len(readiness_statuses) - typed
    target_contract_not_current = sum(
        str((value.get("availability") or {}).get("target_contract_status") or "") != "current"
        for value in knowledge_preview
    )
    if typed and unavailable:
        overall = "mixed_current_and_unavailable"
    elif unavailable:
        overall = "unavailable"
    else:
        overall = "current_typed"

    if internal_selected:
        required_internal_ids = sorted(
            materialization_id
            for materialization_id, value in internal_selected.items()
            if value["required_by"]
        )
        optional_internal_ids = sorted(
            materialization_id
            for materialization_id, value in internal_selected.items()
            if not value["required_by"]
        )
        if required_internal_ids:
            diagnostics.append({
                "diagnostic_id": "internal_materialization_dependencies_added",
                "severity": "info",
                "materialization_ids": required_internal_ids,
                "effect": "Required KLC technical dependencies were added automatically; they remain non-selectable in the user profile.",
            })
        if optional_internal_ids:
            diagnostics.append({
                "diagnostic_id": "optional_internal_materialization_enrichment_added",
                "severity": "info",
                "materialization_ids": optional_internal_ids,
                "effect": "Optional KLC enrichment was added to the execution candidate set; it is executed only when its required typed inputs are available or producible.",
            })
    if unresolved_dependencies:
        diagnostics.append({
            "diagnostic_id": "recommended_knowledge_dependencies_not_selected",
            "severity": "info",
            "details": unresolved_dependencies,
            "effect": "Selected knowledge remains in the plan; UI should explain that related knowledge can enrich or support it.",
        })
    diagnostics.append({
        "diagnostic_id": "source_availability_not_assessed",
        "severity": "info",
        "effect": "This read-only resolution uses contracts only and does not inspect the selected repository/workspace.",
    })
    if target_contract_not_current:
        diagnostics.append({
            "diagnostic_id": "materialization_runtime_unavailable",
            "severity": "warning",
            "knowledge_ids": sorted(
                value["knowledge_id"]
                for value in knowledge_preview
                if str((value.get("availability") or {}).get("target_contract_status") or "") != "current"
            ),
            "effect": "Selected knowledge has a declared KLC contract but no registered runtime materializer; execution must remain blocked rather than use an older path.",
        })

    payload: dict[str, Any] = {
        "schema_version": KNOWLEDGE_RESOLUTION_PLAN_SCHEMA_VERSION,
        "resolver_contract_id": KNOWLEDGE_RESOLVER_CONTRACT_ID,
        "execution_effect": "none",
        "resolution_mode": "contract_only_repository_not_scanned",
        "source": {
            "knowledge_catalog_fingerprint": catalog.get("catalog_fingerprint"),
            "knowledge_profile_fingerprint": _fingerprint(normalized),
        },
        "profile": normalized,
        "resolved_selection": {
            "requested_knowledge_ids": requested_ids,
            "resolved_knowledge_ids": resolved_ids,
            "implicit_required_knowledge_ids": sorted(resolved_set - requested_set),
        },
        "status": {
            "overall": overall,
            "requested_knowledge_count": len(requested_ids),
            "resolved_knowledge_count": len(knowledge_preview),
            "implicit_required_dependency_count": len(resolved_set - requested_set),
            "internal_materialization_dependency_count": len(internal_selected),
            "optional_internal_materialization_count": sum(
                not value["required_by"] for value in internal_selected.values()
            ),
            "current_typed_count": typed,
            "unavailable_materialization_count": unavailable,
            "target_contract_not_current_count": target_contract_not_current,
            "actual_source_availability": "not_assessed",
        },
        "knowledge_preview": knowledge_preview,
        "technical_plan": {
            "materializations": sorted(materializations, key=lambda value: str(value.get("materialization_id") or "")),
            "internal_materialization_ids": sorted(internal_selected),
            "optional_internal_materialization_ids": sorted(
                materialization_id
                for materialization_id, value in internal_selected.items()
                if not value["required_by"]
            ),
            "evidence_requirements": sorted(evidence_index.values(), key=lambda value: (value["artifact_kind"], value["schema_version"])),
            "knowledge_model_dependencies": sorted(knowledge_model_index.values(), key=lambda value: (value["model_kind"], value["schema_version"], value["source_materialization_id"])),
            "foundation_requirements": sorted(foundation_requirements),
        },
        "diagnostics": diagnostics,
        "next_step": "inspect_repository_or_workspace_sources_then_compile_runtime_execution_plan",
    }
    payload["plan_fingerprint"] = _fingerprint(payload)
    return payload


def render_knowledge_catalog_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Каталог знаний",
        "",
        f"- Схема: `{payload.get('schema_version')}`",
        f"- Fingerprint: `{payload.get('catalog_fingerprint')}`",
        f"- Исполнение изменено: `{payload.get('execution_effect')}`",
        "",
        "Пользователь выбирает знания и область repository/workspace. Core stages, analyzers и KLC materializations остаются внутренними техническими сущностями.",
        "",
        "## Доступные виды знаний",
        "",
    ]
    for knowledge in payload.get("knowledge_types") or []:
        selectable = "да" if knowledge.get("profile_v2_selectable") else "нет"
        availability = knowledge.get("availability") or {}
        lines.extend([
            f"### {knowledge.get('title')} (`{knowledge.get('knowledge_id')}`)",
            "",
            str(knowledge.get("summary") or ""),
            "",
            f"- Области: `{', '.join(knowledge.get('supported_scopes') or [])}`",
            f"- Можно выбрать в knowledge_profile/v2: **{selectable}**",
            f"- Готовность: `{availability.get('status')}` — {availability.get('explanation')}",
            f"- KLC materialization: `{(knowledge.get('materialization') or {}).get('materialization_id')}`",
            "- В базу знаний войдут: " + "; ".join(knowledge.get("contains") or []),
            "- Обязательные источники:",
        ])
        for source in (knowledge.get("sources") or {}).get("required") or []:
            analyzers = ", ".join(source.get("analyzer_ids") or []) or "внешний/не зарегистрирован"
            lines.append(
                f"  - **{source.get('title')}** — `{source.get('artifact_kind')}`; producer/analyzer: `{analyzers}`; статус: `{source.get('producer_registration_status')}`"
            )
        required_dependencies = knowledge.get("required_knowledge_dependencies") or []
        recommended_dependencies = knowledge.get("recommended_knowledge_dependencies") or []
        if required_dependencies:
            lines.append("- Обязательные знания: " + ", ".join(f"`{value}`" for value in required_dependencies))
        if recommended_dependencies:
            lines.append("- Рекомендуемые знания: " + ", ".join(f"`{value}`" for value in recommended_dependencies))
        required_models = (knowledge.get("knowledge_inputs") or {}).get("required") or []
        optional_models = (knowledge.get("knowledge_inputs") or {}).get("optional") or []
        if required_models:
            lines.append("- Обязательные модели KLC:")
            for model in required_models:
                lines.append(
                    f"  - `{model.get('model_kind')}` из `{model.get('source_materialization_id')}`"
                )
        if optional_models:
            lines.append("- Дополнительные модели KLC:")
            for model in optional_models:
                lines.append(
                    f"  - `{model.get('model_kind')}` из `{model.get('source_materialization_id')}`"
                )
        optional = (knowledge.get("sources") or {}).get("optional") or []
        if optional:
            lines.append("- Дополнительные источники:")
            for source in optional:
                analyzers = ", ".join(source.get("analyzer_ids") or []) or "внешний/не зарегистрирован"
                lines.append(
                    f"  - **{source.get('title')}** — `{source.get('artifact_kind')}`; producer/analyzer: `{analyzers}`; статус: `{source.get('producer_registration_status')}`"
                )
        lines.append("")
    lines.extend([
        "## Внутренние materializations",
        "",
    ])
    for value in payload.get("internal_materializations") or []:
        lines.append(f"- `{value.get('materialization_id')}` — {value.get('reason_not_user_selectable')}")
    lines.extend([
        "",
        "## Следующий шаг",
        "",
        f"`{payload.get('next_step')}`",
        "",
    ])
    return "\n".join(lines)


def render_knowledge_resolution_markdown(payload: Mapping[str, Any]) -> str:
    profile = payload.get("profile") or {}
    status = payload.get("status") or {}
    lines = [
        f"# Предварительный состав базы знаний: {profile.get('title')}",
        "",
        f"- Профиль: `{profile.get('profile_id')}`",
        f"- Область: `{(profile.get('scope') or {}).get('kind')}:{(profile.get('scope') or {}).get('scope_id')}`",
        f"- Статус плана: `{status.get('overall')}`",
        f"- Fingerprint: `{payload.get('plan_fingerprint')}`",
        "- Фактическое наличие исходников: **ещё не проверялось**",
        "",
        "## Что войдёт в базу знаний",
        "",
    ]
    for knowledge in payload.get("knowledge_preview") or []:
        lines.extend([
            f"### {knowledge.get('title')}",
            "",
            str(knowledge.get("summary") or ""),
            "",
            f"Добавлено в план: `{knowledge.get('selection_origin')}`" + (f"; требуется для `{', '.join(knowledge.get('required_by') or [])}`" if knowledge.get('required_by') else ""),
            "",
            "Будут построены: " + "; ".join(knowledge.get("contains") or []),
            "",
            "Источники:",
        ])
        for source in knowledge.get("sources") or []:
            requirement = "обязательный" if source.get("requirement") == "required" else "дополнительный"
            lines.append(
                f"- **{source.get('title')}** ({requirement}) — `{source.get('artifact_kind')}`; фактическая доступность: `{source.get('actual_source_availability')}`"
            )
        model_inputs = knowledge.get("knowledge_inputs") or []
        if model_inputs:
            lines.append("Зависимости от других моделей KLC:")
            for model in model_inputs:
                requirement = "обязательная" if model.get("requirement") == "required" else "дополнительная"
                lines.append(
                    f"- `{model.get('model_kind')}` из `{model.get('source_materialization_id')}` ({requirement})"
                )
        lines.append("")
    lines.extend([
        "## Технический план",
        "",
        "### KLC materializations",
        "",
    ])
    for value in (payload.get("technical_plan") or {}).get("materializations") or []:
        lines.append(
            f"- `{value.get('materialization_id')}` для `{value.get('knowledge_id')}` — `{(value.get('availability') or {}).get('status')}`"
        )
    lines.extend(["", "### Зависимости между моделями KLC", ""])
    for value in (payload.get("technical_plan") or {}).get("knowledge_model_dependencies") or []:
        lines.append(
            f"- `{value.get('model_kind')}` / `{value.get('schema_version')}` из `{value.get('source_materialization_id')}`"
        )
    lines.extend([
        "",
        "### Foundation",
        "",
        ", ".join(f"`{value}`" for value in ((payload.get("technical_plan") or {}).get("foundation_requirements") or [])) or "Не требуется.",
        "",
        "## Диагностика",
        "",
    ])
    for diagnostic in payload.get("diagnostics") or []:
        lines.append(f"- `{diagnostic.get('severity')}` `{diagnostic.get('diagnostic_id')}` — {diagnostic.get('effect') or ''}")
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_markdown(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path
