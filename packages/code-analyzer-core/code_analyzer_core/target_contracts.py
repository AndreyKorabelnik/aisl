from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.resources as resources
import json
from pathlib import Path
from typing import Any, Mapping

from code_analyzer_core import __version__ as CORE_VERSION

TARGET_CONTRACTS_SCHEMA_VERSION = "core_target_analysis_contracts/v1"
SUPPORTED_CORE_CATALOG_SCHEMA = "core_analysis_catalog/v1"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _load_definitions() -> dict[str, Any]:
    resource = resources.files("code_analyzer_core").joinpath("resources/core_target_contract_definitions_v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _validate_catalog(catalog: Mapping[str, Any]) -> None:
    schema = str(catalog.get("schema_version") or "")
    if schema != SUPPORTED_CORE_CATALOG_SCHEMA:
        raise ValueError(
            f"unsupported Core catalog schema: {schema!r}; expected {SUPPORTED_CORE_CATALOG_SCHEMA!r}"
        )
    actual = str(catalog.get("catalog_fingerprint") or "")
    if not actual:
        raise ValueError("Core catalog has no catalog_fingerprint")
    material = {str(k): deepcopy(v) for k, v in catalog.items() if str(k) != "catalog_fingerprint"}
    expected = _fingerprint(material)
    if actual != expected:
        raise ValueError("Core catalog fingerprint does not match canonical content")
    if not isinstance(catalog.get("stage_catalog"), Mapping):
        raise ValueError("Core catalog has no stage_catalog")
    if not isinstance(catalog.get("foundation_fragments"), list):
        raise ValueError("Core catalog has no foundation_fragments")


def _stage_index(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stage_catalog = catalog.get("stage_catalog") or {}
    return {
        str(item.get("stage_id")): dict(item)
        for item in stage_catalog.get("stages") or []
        if isinstance(item, Mapping) and item.get("stage_id")
    }


def _derived_index(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    stage_catalog = catalog.get("stage_catalog") or {}
    payload = stage_catalog.get("java_derived_stage_contracts") or {}
    return {
        str(item.get("stage_id")): dict(item)
        for item in payload.get("contracts") or []
        if isinstance(item, Mapping) and item.get("stage_id")
    }


def _foundation_assessment(
    catalog: Mapping[str, Any],
    *,
    stage_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fragments = catalog.get("foundation_fragments") or []
    current_ids: list[str] = []
    for fragment in fragments:
        for stage_id in (fragment or {}).get("resolved_stage_ids") or []:
            sid = str(stage_id)
            if sid and sid not in current_ids:
                current_ids.append(sid)

    violations: list[dict[str, Any]] = []
    target_ids: list[str] = []
    for sid in current_ids:
        descriptor = stage_index.get(sid) or {}
        category = str(descriptor.get("category") or "")
        produces = [str(item) for item in descriptor.get("produces") or []]
        if category != "base_evidence":
            violations.append({
                "code": "non_base_stage_in_foundation",
                "stage_id": sid,
                "current_category": category or None,
                "produces": produces,
                "required_transition": "move_to_independent_evidence_analyzer_or_knowledge_layer",
                "reason": "Target Foundation is restricted to technical source indexes and base source observations.",
            })
            continue
        target_ids.append(sid)

    return {
        "contract_id": "core_foundation_contract/v1",
        "current_fragment_ids": [str((item or {}).get("fragment_id") or "") for item in fragments],
        "current_stage_ids": current_ids,
        "target_stage_ids_under_current_classification": target_ids,
        "violations": violations,
        "compliant": not violations,
    }


def _analyzer_assessment(
    catalog: Mapping[str, Any],
    *,
    stage_index: Mapping[str, Mapping[str, Any]],
    derived_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    internal_dependency_findings: list[dict[str, Any]] = []
    internal_state_findings: list[dict[str, Any]] = []
    knowledge_materializations: list[dict[str, Any]] = []
    technical_packaging: list[str] = []

    for sid in sorted(stage_index):
        descriptor = stage_index[sid]
        category = str(descriptor.get("category") or "")
        if category == "knowledge_materialization_candidate":
            knowledge_materializations.append({
                "stage_id": sid,
                "produces": [str(item) for item in descriptor.get("produces") or []],
                "target_owner": "knowledge-layer-core",
                "required_transition": "replace_with_typed_evidence_inputs_and_KLC_materialization",
            })
        elif category == "technical_packaging":
            technical_packaging.append(sid)

        observed = derived_index.get(sid) or {}
        dependencies = [str(item) for item in observed.get("upstream_stage_dependencies") or []]
        if dependencies:
            internal_dependency_findings.append({
                "stage_id": sid,
                "dependencies": dependencies,
                "required_transition": "keep_internal_to_one_analyzer_or_promote_to_explicit_typed_input_only_if_reused_across_public_analyzers",
                "recommended_action": observed.get("recommended_action"),
            })
        reads = str(observed.get("reads_analysis_result") or "none")
        if reads != "none":
            internal_state_findings.append({
                "stage_id": sid,
                "reads_analysis_result": reads,
                "analysis_result_reads": [str(item) for item in observed.get("analysis_result_reads") or []],
                "required_transition": "narrow_internal_state_access_when_useful; this is not a public-analyzer dependency by itself",
            })

    return {
        "contract_id": "core_evidence_analyzer_contract/v1",
        "observed_internal_stage_dependency_findings": internal_dependency_findings,
        "observed_internal_pipeline_state_findings": internal_state_findings,
        "knowledge_materializations_inside_core": knowledge_materializations,
        "technical_packaging_stage_ids": technical_packaging,
        "boundary_assessment": {
            "public_analyzer_dependency_status": "no_declared_public_analyzer_artifact_dependencies",
            "internal_stage_dependencies_are_allowed": True,
            "internal_pipeline_state_is_analyzer_implementation_detail": True,
        },
        "compliant": not knowledge_materializations,
    }


def build_core_target_analysis_contracts(core_catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic Core target contracts and current runtime assessment."""
    _validate_catalog(core_catalog)
    definitions = _load_definitions()
    stage_index = _stage_index(core_catalog)
    derived_index = _derived_index(core_catalog)

    foundation = _foundation_assessment(core_catalog, stage_index=stage_index)
    analyzers = _analyzer_assessment(
        core_catalog,
        stage_index=stage_index,
        derived_index=derived_index,
    )
    from code_analyzer_core.evidence_runtime import registered_evidence_analyzers

    registered_identities = [
        {
            "artifact_kind": item.artifact_kind,
            "schema_version": item.schema_version,
            "analyzer_id": item.analyzer_id,
            "analyzer_version": item.analyzer_version,
            "artifact_relative_path": item.artifact_relative_path,
        }
        for item in registered_evidence_analyzers()
    ]

    payload: dict[str, Any] = {
        "schema_version": TARGET_CONTRACTS_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "execution_effect": "none",
        "purpose": "Core-owned target contracts and current-state boundary assessment for independent typed evidence analyzers.",
        "source": {
            "core_catalog_schema_version": core_catalog.get("schema_version"),
            "core_catalog_fingerprint": core_catalog.get("catalog_fingerprint"),
            "core_catalog_version": core_catalog.get("core_version"),
            "target_definition_schema_version": definitions.get("schema_version"),
        },
        "architecture_goal": definitions.get("architecture_goal"),
        "contracts": deepcopy(definitions.get("contracts") or {}),
        "external_contract_requirements": deepcopy(definitions.get("external_contract_requirements") or []),
        "current_state_assessment": {
            "foundation": foundation,
            "evidence_analyzers": analyzers,
            "evidence_runtime": {
                "contract_id": "core_evidence_runtime/v1",
                "request_schema_version": "core_evidence_execution_request/v1",
                "result_schema_version": "core_evidence_execution_result/v1",
                "dispatch_rule": "artifact_kind_plus_schema_version",
                "registered_analyzer_count": len(registered_identities),
                "registered_analyzers": registered_identities,
                "implicit_monolithic_publication": False,
            },
            "evidence_artifacts": {
                "contract_id": "core_evidence_artifact_contract/v1",
                "current_status": "canonical_envelope_enforced_for_registered_runtime_artifacts",
                "runtime_contract_id": "core_evidence_runtime/v1",
                "semantic_routing_rule": "artifact_kind_plus_schema_version_not_task_id",
                "remaining_work": "register each remaining evidence family in the Core runtime when its independent analyzer is implemented",
            },
        },
        "summary": {
            "foundation_current_stage_count": len(foundation["current_stage_ids"]),
            "foundation_target_stage_count_under_current_classification": len(foundation["target_stage_ids_under_current_classification"]),
            "foundation_violation_count": len(foundation["violations"]),
            "observed_internal_stage_dependency_count": len(analyzers["observed_internal_stage_dependency_findings"]),
            "observed_internal_pipeline_state_read_count": len(analyzers["observed_internal_pipeline_state_findings"]),
            "knowledge_materialization_inside_core_count": len(analyzers["knowledge_materializations_inside_core"]),
            "technical_packaging_stage_count": len(analyzers["technical_packaging_stage_ids"]),
            "registered_evidence_analyzer_count": len(registered_identities),
            "external_contract_requirement_count": len(definitions.get("external_contract_requirements") or []),
        },
        "completed_runtime_contracts": [
            "core_evidence_runtime/v1",
            "core_evidence_execution_request/v1",
            "core_evidence_execution_result/v1",
            "core_evidence_artifact_contract/v1",
        ],
        "next_architectural_work": [
            "add each new evidence family through a Core-owned analyzer registration and contract",
            "keep Runner execution generic and selected only by artifact_kind plus schema_version",
            "remove remaining knowledge materializations from the monolithic Core pipeline as their typed replacements become current",
        ],
    }
    payload["contracts_fingerprint"] = _fingerprint(payload)
    return payload


def write_core_target_analysis_contracts(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def render_core_target_analysis_contracts_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    assessment = payload.get("current_state_assessment") or {}
    foundation = assessment.get("foundation") or {}
    analyzers = assessment.get("evidence_analyzers") or {}

    lines = [
        "# Core Target Analysis Contracts v1",
        "",
        f"- Core version: `{payload.get('core_version')}`",
        f"- Schema: `{payload.get('schema_version')}`",
        f"- Execution effect: `{payload.get('execution_effect')}`",
        f"- Fingerprint: `{payload.get('contracts_fingerprint')}`",
        "",
        "## Target boundary",
        "",
        "- Foundation is a Core-owned immutable technical source index.",
        "- Public Core analyzers produce independent typed evidence artifacts.",
        "- KLC composes evidence into knowledge models.",
        "- Runner records execution and lifecycle but does not define evidence semantics.",
        "- Evidence meaning is selected by `artifact_kind + schema_version`, not by `task_id`.",
        "",
        "## Current assessment",
        "",
        f"- Foundation stages now: **{summary.get('foundation_current_stage_count', 0)}**",
        f"- Foundation stages allowed by the target contract under current classification: **{summary.get('foundation_target_stage_count_under_current_classification', 0)}**",
        f"- Foundation violations: **{summary.get('foundation_violation_count', 0)}**",
        f"- Observed internal stage dependencies: **{summary.get('observed_internal_stage_dependency_count', 0)}**",
        f"- Internal pipeline-state reads: **{summary.get('observed_internal_pipeline_state_read_count', 0)}**",
        f"- Knowledge materializations still inside Core: **{summary.get('knowledge_materialization_inside_core_count', 0)}**",
        f"- Registered generic evidence analyzers: **{summary.get('registered_evidence_analyzer_count', 0)}**",
        "- Generic Core evidence runtime: `core_evidence_runtime/v1`",
        "",
        "## Foundation transition",
        "",
    ]
    violations = foundation.get("violations") or []
    if violations:
        for item in violations:
            lines.append(
                f"- `{item.get('stage_id')}` must leave Foundation: {item.get('reason')}"
            )
    else:
        lines.append("- No current Foundation violations detected.")

    lines.extend(["", "## Internal analyzer implementation diagnostics", "", "These are analyzer-internal stage/reuse diagnostics, not dependencies between public evidence analyzers.", ""])
    for item in analyzers.get("observed_internal_stage_dependency_findings") or []:
        deps = ", ".join(f"`{value}`" for value in item.get("dependencies") or [])
        lines.append(f"- `{item.get('stage_id')}` depends on {deps}.")
    for item in analyzers.get("observed_internal_pipeline_state_findings") or []:
        reads = ", ".join(f"`{value}`" for value in item.get("analysis_result_reads") or [])
        lines.append(f"- `{item.get('stage_id')}` reads analyzer-owned pipeline state: {reads or item.get('reads_analysis_result')}.")

    lines.extend(["", "## Knowledge materializations to remove from Core", ""])
    for item in analyzers.get("knowledge_materializations_inside_core") or []:
        lines.append(f"- `{item.get('stage_id')}` → `knowledge-layer-core`.")

    lines.extend(["", "## Next contract owners", ""])
    for item in payload.get("external_contract_requirements") or []:
        lines.append(
            f"- `{item.get('contract_id')}` — **{item.get('owner')}**: {item.get('required_rule')}"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_core_target_analysis_contracts_markdown(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_core_target_analysis_contracts_markdown(payload), encoding="utf-8")
    return target
