from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.resources as resources
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION

CATALOG_SCHEMA_VERSION = "core_evidence_contract_catalog/v1"
SUPPORTED_CORE_CATALOG_SCHEMA = "core_analysis_catalog/v1"
SUPPORTED_TARGET_CONTRACTS_SCHEMA = "core_target_analysis_contracts/v1"

_ALLOWED_EXECUTION_CLASSES = {"always_on", "bounded_preflight", "full_analysis"}
_ALLOWED_PREFLIGHT_PHASES = {None, "p0", "p1"}
_ALLOWED_DISCOVERY_ROLES = {
    "generic_structural",
    "specialized_candidate",
    "specialized_observation",
    "domain_evidence",
}
_ALLOWED_APPLICABILITY_STATUS = {"formalized", "not_formalized"}
_ALLOWED_BUDGET_CLASSES = {
    "metadata_only",
    "hard_bounded_content",
    "measured_bounded_current",
    "full_analysis",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_fingerprint(payload: Mapping[str, Any], field: str, label: str) -> None:
    actual = str(payload.get(field) or "")
    if not actual:
        raise ValueError(f"{label} has no {field}")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != field}
    if actual != _fingerprint(material):
        raise ValueError(f"{label} fingerprint does not match canonical content")


def _load_definitions() -> dict[str, Any]:
    resource = resources.files("code_analyzer_core").joinpath(
        "resources/core_evidence_contract_definitions_v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def _validate_preflight_planning(contract: Mapping[str, Any]) -> None:
    identity = f"{contract.get('artifact_kind')}/{contract.get('schema_version')}"
    planning = contract.get("preflight_planning")
    if not isinstance(planning, Mapping):
        raise ValueError(f"Core evidence contract {identity} has no preflight_planning metadata")

    execution_class = str(planning.get("execution_class") or "")
    if execution_class not in _ALLOWED_EXECUTION_CLASSES:
        raise ValueError(f"Core evidence contract {identity} has invalid planning execution_class")
    phase = planning.get("preflight_phase")
    if phase not in _ALLOWED_PREFLIGHT_PHASES:
        raise ValueError(f"Core evidence contract {identity} has invalid preflight_phase")
    if execution_class == "always_on" and phase != "p0":
        raise ValueError(f"Core evidence contract {identity} always_on planning must be P0")
    if execution_class == "bounded_preflight" and phase != "p1":
        raise ValueError(f"Core evidence contract {identity} bounded_preflight planning must be P1")
    if execution_class == "full_analysis" and phase is not None:
        raise ValueError(f"Core evidence contract {identity} full_analysis planning cannot declare a preflight phase")

    if str(planning.get("discovery_role") or "") not in _ALLOWED_DISCOVERY_ROLES:
        raise ValueError(f"Core evidence contract {identity} has invalid discovery_role")

    applicability = planning.get("applicability")
    if not isinstance(applicability, Mapping):
        raise ValueError(f"Core evidence contract {identity} has no applicability metadata")
    if str(applicability.get("status") or "") not in _ALLOWED_APPLICABILITY_STATUS:
        raise ValueError(f"Core evidence contract {identity} has invalid applicability status")
    for key in ("required_languages_any_of", "required_extensions_any_of"):
        value = applicability.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Core evidence contract {identity} planning {key} must be a string list")
    if applicability.get("basis") != "observed_source_landscape":
        raise ValueError(f"Core evidence contract {identity} planning applicability must use observed source landscape")
    if applicability.get("when_unresolved") != "execute_if_explicitly_requested_else_do_not_hard_skip":
        raise ValueError(f"Core evidence contract {identity} has unsafe unresolved applicability behavior")

    safety = planning.get("selection_safety")
    if not isinstance(safety, Mapping):
        raise ValueError(f"Core evidence contract {identity} has no selection_safety metadata")
    if safety.get("concept_inference_may_hard_skip") is not False:
        raise ValueError(f"Core evidence contract {identity} must not allow concept inference to hard-skip")
    if safety.get("hard_skip_requires_observed_non_applicability") is not True:
        raise ValueError(f"Core evidence contract {identity} must require observed non-applicability for hard skip")
    if safety.get("explicit_request_behavior") != "execute_or_report_observed_blocking_precondition":
        raise ValueError(f"Core evidence contract {identity} has unsafe explicit-request behavior")

    budget = planning.get("budget")
    if not isinstance(budget, Mapping) or str(budget.get("class") or "") not in _ALLOWED_BUDGET_CLASSES:
        raise ValueError(f"Core evidence contract {identity} has invalid budget metadata")
    if not isinstance(budget.get("hard_bounds_declared"), bool):
        raise ValueError(f"Core evidence contract {identity} budget must declare hard_bounds_declared")


def _stage_index(core_catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stage_catalog = core_catalog.get("stage_catalog") or {}
    return {
        str(item.get("stage_id")): dict(item)
        for item in stage_catalog.get("stages") or []
        if isinstance(item, Mapping) and item.get("stage_id")
    }


def _validate_inputs(
    core_catalog: Mapping[str, Any],
    target_contracts: Mapping[str, Any],
) -> None:
    if str(core_catalog.get("schema_version") or "") != SUPPORTED_CORE_CATALOG_SCHEMA:
        raise ValueError("unsupported Core catalog schema")
    if str(target_contracts.get("schema_version") or "") != SUPPORTED_TARGET_CONTRACTS_SCHEMA:
        raise ValueError("unsupported Core target-contract schema")
    _validate_fingerprint(core_catalog, "catalog_fingerprint", "Core catalog")
    _validate_fingerprint(target_contracts, "contracts_fingerprint", "Core target contracts")
    artifact_contract = ((target_contracts.get("contracts") or {}).get("evidence_artifact") or {})
    if artifact_contract.get("contract_id") != "core_evidence_artifact_contract/v1":
        raise ValueError("Core target contracts do not expose core_evidence_artifact_contract/v1")


def build_core_evidence_contract_catalog(
    core_catalog: Mapping[str, Any],
    target_contracts: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the generic Core-owned typed evidence contract catalog.

    The catalog defines payload contracts only. It does not execute analyzers or
    claim that a contract is already emitted at runtime.
    """
    _validate_inputs(core_catalog, target_contracts)
    definitions = _load_definitions()
    stage_index = _stage_index(core_catalog)

    contracts: list[dict[str, Any]] = []
    for raw in definitions.get("contracts") or []:
        contract = deepcopy(raw)
        _validate_preflight_planning(contract)
        producer = contract.get("producer") or {}
        stage_ids = [str(value) for value in producer.get("current_source_stage_ids") or []]
        missing_stage_ids = [stage_id for stage_id in stage_ids if stage_id not in stage_index]
        current_sources = []
        for stage_id in stage_ids:
            descriptor = stage_index.get(stage_id) or {}
            current_sources.append({
                "stage_id": stage_id,
                "present": stage_id in stage_index,
                "category": descriptor.get("category"),
                "produces": [str(value) for value in descriptor.get("produces") or []],
            })
        runtime_publication = contract.get("runtime_publication") or {}
        published = contract.get("contract_status") == "runtime_published"
        from code_analyzer_core.evidence_runtime import registered_evidence_analyzers

        registrations = {
            item.semantic_identity: item
            for item in registered_evidence_analyzers()
        }
        identity = (str(contract.get("artifact_kind") or ""), str(contract.get("schema_version") or ""))
        registration = registrations.get(identity)
        expected_analyzer_id = str(runtime_publication.get("producer_analyzer_id") or "")
        expected_path = str(runtime_publication.get("artifact_relative_path") or "")
        registration_valid = bool(
            registration is not None
            and registration.analyzer_id == expected_analyzer_id
            and registration.artifact_relative_path == expected_path
        )
        contract["current_state_assessment"] = {
            "source_stages": current_sources,
            "missing_source_stage_ids": missing_stage_ids,
            "source_observations_available": not missing_stage_ids,
            "runtime_contract_id": runtime_publication.get("runtime_contract_id"),
            "runtime_registration_present": registration is not None,
            "runtime_registration_valid": registration_valid,
            "typed_runtime_artifact_published": bool(published and registration_valid),
            "runtime_status": (
                "registered_in_generic_core_evidence_runtime"
                if published and registration_valid
                else "runtime_registration_missing_or_invalid"
            ),
        }
        contract["contract_fingerprint"] = _fingerprint(contract)
        contracts.append(contract)

    contracts.sort(key=lambda item: (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or "")))
    payload: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "execution_effect": "none",
        "purpose": definitions.get("purpose"),
        "source": {
            "core_catalog_schema_version": core_catalog.get("schema_version"),
            "core_catalog_fingerprint": core_catalog.get("catalog_fingerprint"),
            "core_target_contracts_schema_version": target_contracts.get("schema_version"),
            "core_target_contracts_fingerprint": target_contracts.get("contracts_fingerprint"),
            "definition_schema_version": definitions.get("schema_version"),
        },
        "artifact_envelope_contract": "core_evidence_artifact_contract/v1",
        "semantic_routing_rule": "artifact_kind_plus_schema_version_not_task_id",
        "contracts": contracts,
        "summary": {
            "contract_count": len(contracts),
            "defined_not_published_count": sum(
                1 for item in contracts if item.get("contract_status") == "defined_not_published"
            ),
            "runtime_published_count": sum(
                1
                for item in contracts
                if (item.get("current_state_assessment") or {}).get("typed_runtime_artifact_published")
            ),
            "planning_execution_class_counts": {
                execution_class: sum(
                    1
                    for item in contracts
                    if (item.get("preflight_planning") or {}).get("execution_class") == execution_class
                )
                for execution_class in sorted(_ALLOWED_EXECUTION_CLASSES)
            },
            "generic_preflight_contract_count": sum(
                1
                for item in contracts
                if (item.get("preflight_planning") or {}).get("preflight_phase") in {"p0", "p1"}
                and (item.get("preflight_planning") or {}).get("discovery_role") == "generic_structural"
            ),
        },
        "next_step": "compile Knowledge Resolution Plan evidence requirements into core_evidence_execution_request/v1",
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def write_core_evidence_contract_catalog(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def render_core_evidence_contract_catalog_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Core Evidence Contract Catalog v1",
        "",
        f"- Core version: `{payload.get('core_version')}`",
        f"- Schema: `{payload.get('schema_version')}`",
        f"- Execution effect: `{payload.get('execution_effect')}`",
        f"- Contracts: `{(payload.get('summary') or {}).get('contract_count')}`",
        "",
        "## Boundary",
        "",
        "Evidence meaning is selected by `artifact_kind + schema_version`. Task, Suite and Profile identifiers are execution provenance only.",
        "",
    ]
    for contract in payload.get("contracts") or []:
        lines.extend([
            f"## {contract.get('artifact_kind')} — {contract.get('schema_version')}",
            "",
            str(contract.get("definition") or ""),
            "",
            f"- Status: `{contract.get('contract_status')}`",
            f"- Planning class: `{(contract.get('preflight_planning') or {}).get('execution_class')}`",
            f"- Preflight phase: `{(contract.get('preflight_planning') or {}).get('preflight_phase')}`",
            f"- Discovery role: `{(contract.get('preflight_planning') or {}).get('discovery_role')}`",
            f"- Target analyzer: `{(contract.get('producer') or {}).get('target_analyzer_id')}`",
            f"- Consumer knowledge: `{', '.join(contract.get('intended_knowledge_consumers') or [])}`",
            f"- Record limit: `{(contract.get('publication_policy') or {}).get('record_limit')}`",
            "",
            "### Payload sections",
            "",
        ])
        for section in (contract.get("payload") or {}).get("sections") or []:
            lines.append(f"- `{section.get('section')}` — identity `{section.get('record_identity')}`")
        lines.extend(["", "### Forbidden semantics", ""])
        for item in contract.get("forbidden_semantics") or []:
            lines.append(f"- {item}")
        lines.extend(["", "### Current gaps", ""])
        for item in contract.get("current_state_gaps") or []:
            lines.append(f"- {item}")
        assessment = contract.get("current_state_assessment") or {}
        lines.extend([
            "",
            "### Current state",
            "",
            f"- Source observations available: `{assessment.get('source_observations_available')}`",
            f"- Typed runtime artifact published: `{assessment.get('typed_runtime_artifact_published')}`",
            f"- Runtime status: `{assessment.get('runtime_status')}`",
            "",
        ])
    lines.extend([
        "## Next step",
        "",
        str(payload.get("next_step") or ""),
        "",
    ])
    return "\n".join(lines)


def write_core_evidence_contract_catalog_markdown(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_core_evidence_contract_catalog_markdown(payload), encoding="utf-8")
    return target
