from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .version import __version__

EXECUTION_RESULT_CONTRACT_ID = "analysis_execution_result_contract/v1"
EXECUTION_RESULT_CATALOG_SCHEMA_VERSION = "analysis_execution_result_catalog/v1"
SUPPORTED_CORE_TARGET_SCHEMA = "core_target_analysis_contracts/v1"
SUPPORTED_KLC_MATERIALIZATION_SCHEMA = "knowledge_materialization_catalog/v3"


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
    material = {
        str(key): deepcopy(value)
        for key, value in payload.items()
        if str(key) != fingerprint_field
    }
    expected = _fingerprint(material)
    if actual != expected:
        raise ValueError(f"{label} fingerprint does not match canonical content")


def _validate_core_target_contracts(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        expected_schema=SUPPORTED_CORE_TARGET_SCHEMA,
        fingerprint_field="contracts_fingerprint",
        label="Core target contracts",
    )
    contracts = payload.get("contracts") or {}
    if not isinstance(contracts, Mapping):
        raise ValueError("Core target contracts have no contracts object")
    evidence = contracts.get("evidence_artifact") or {}
    if str(evidence.get("contract_id") or "") != "core_evidence_artifact_contract/v1":
        raise ValueError("Core target contracts are missing core_evidence_artifact_contract/v1")


def _validate_klc_materialization_catalog(payload: Mapping[str, Any]) -> None:
    _validate_fingerprinted_payload(
        payload,
        expected_schema=SUPPORTED_KLC_MATERIALIZATION_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="KLC materialization catalog",
    )
    contract = payload.get("contract") or {}
    if str(contract.get("contract_id") or "") != "knowledge_materialization_contract/v3":
        raise ValueError("KLC materialization catalog is missing knowledge_materialization_contract/v3")
    routing = payload.get("evidence_routing_contract") or {}
    if str(routing.get("contract_id") or "") != "evidence_semantic_routing/v1":
        raise ValueError("KLC materialization catalog is missing evidence_semantic_routing/v1")


def _target_contract() -> dict[str, Any]:
    return {
        "contract_id": EXECUTION_RESULT_CONTRACT_ID,
        "owner": "static-analysis-runner",
        "definition": (
            "Self-describing record of analysis execution and produced typed evidence artifacts. "
            "Runner owns lifecycle, process, retry and artifact registration; Core owns evidence semantics; "
            "KLC owns knowledge materialization semantics."
        ),
        "execution_scopes": ["repository", "workspace", "portfolio"],
        "required_sections": {
            "identity": {
                "fields": ["execution_id", "execution_fingerprint", "scope", "status"],
                "status_values": ["completed", "partial", "failed", "cancelled"],
            },
            "source_snapshots": {
                "cardinality": "one_or_more",
                "required_fields": ["source_id", "source_kind", "revision", "content_fingerprint"],
                "machine_local_paths": "provenance_only_not_identity",
            },
            "foundation_artifacts": {
                "cardinality": "zero_or_more",
                "required_fields": ["contract_id", "artifact_fingerprint", "source_snapshot_ids", "status"],
                "contract_id": "core_foundation_contract/v1",
            },
            "analyzer_executions": {
                "cardinality": "zero_or_more",
                "required_fields": [
                    "analyzer_execution_id",
                    "analyzer_id",
                    "analyzer_version",
                    "source_snapshot_ids",
                    "status",
                    "attempts",
                ],
                "allowed_request_provenance": ["knowledge_profile_id", "knowledge_execution_plan_fingerprint", "execution_node_id"],
                "semantic_rule": "request provenance never defines artifact meaning",
            },
            "evidence_artifacts": {
                "cardinality": "zero_or_more",
                "contract_id": "core_evidence_artifact_contract/v1",
                "required_fields": [
                    "artifact_id",
                    "artifact_kind",
                    "schema_version",
                    "producer_analyzer_execution_id",
                    "content_fingerprint",
                    "status",
                    "coverage",
                    "diagnostics",
                    "provenance",
                    "location",
                ],
                "semantic_identity": ["artifact_kind", "schema_version"],
                "forbidden_semantic_selectors": ["task_id", "suite_id", "profile_id", "directory_name"],
            },
            "materialization_executions": {
                "cardinality": "zero_or_more",
                "required_fields": [
                    "materialization_execution_id",
                    "materialization_id",
                    "status",
                    "input_artifact_ids",
                    "output_manifest",
                    "request",
                    "result",
                    "published_capabilities",
                    "knowledge_artifact_ids",
                ],
                "contract_id": "knowledge_materialization_contract/v3",
                "ownership_rule": "Runner resolves contract-declared inputs and records execution references; KLC owns dispatch, model semantics, outputs, coverage and capabilities.",
                "dispatch_rule": "Runner calls only the generic KLC materialize(request, output) entrypoint.",
            },
            "lifecycle": {
                "required_fields": ["started_at", "completed_at", "attempts", "diagnostics"],
                "retry_rule": "Every attempt is preserved; successful retry does not erase prior failure provenance.",
                "failure_rule": "Missing or unsupported evidence is explicit; no hidden fallback or silent reinterpretation.",
            },
        },
        "allowed_runner_responsibilities": [
            "resolve and record source snapshots",
            "orchestrate Core analyzer processes",
            "orchestrate Foundation lifecycle without defining its contents",
            "record attempts, timeouts, resource usage and failures",
            "register self-describing evidence artifacts",
            "invoke KLC materializations and record their manifests",
            "compose repository, workspace and portfolio execution scopes",
        ],
        "forbidden_runner_responsibilities": [
            "define evidence semantics from Task, Suite, Core Profile or output path",
            "infer source-code meaning",
            "rewrite unsupported evidence into a different schema",
            "publish a knowledge capability merely because a Task was requested",
            "hide analyzer or materialization failures behind fallback execution",
        ],
        "identity_rules": {
            "execution_fingerprint_inputs": [
                "source snapshot fingerprints",
                "Foundation fingerprints",
                "analyzer ids and versions",
                "evidence-affecting parameters",
                "requested execution composition",
            ],
            "excluded_from_semantic_identity": [
                "absolute paths",
                "process ids",
                "timestamps",
                "retry attempt numbers",
                "log paths",
            ],
        },
    }


def _current_manifest_assessment() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "knowledge_execution_result/v2",
            "scope": "knowledge_execution_plan",
            "implementation_ref": "static_analysis_runner.knowledge_execution.execute_knowledge_execution_plan",
            "strengths": [
                "executes the complete knowledge_execution_plan/v1 in topological order",
                "dispatches Core evidence only by typed artifact identity through the Core-owned registry",
                "registers every validated Core artifact without evidence-family-specific Runner branches",
                "executes KLC materializations through one generic runtime and preserves dependencies",
                "publishes capabilities only from completed KLC results",
                "uses no Task, Suite or Core Profile execution semantics",
                "forbids legacy fallback and dual-write",
            ],
            "gaps": [
                "only one real Core evidence family and one real KLC materializer are currently registered",
                "Foundation reuse, caching and parallel execution are not implemented",
            ],
            "typed_evidence_registry_status": "generic_core_evidence_runtime",
            "foundation_identity_status": "not_yet_requested_by_runtime",
            "analyzer_execution_status": "canonical_knowledge_execution",
            "task_semantic_coupling": False,
            "target_compliance": "full",
        },
        {
            "schema_version": "static_repository_analysis_run_manifest/v1",
            "scope": "repository_evidence",
            "implementation_ref": "static_analysis_runner.evidence_executor.execute_core_evidence_request",
            "strengths": [
                "executes core_evidence_execution_request/v1 produced from an execution-plan node",
                "dispatches Core analyzers only by artifact_kind plus schema_version",
                "validates every Core result and artifact fingerprint before registration",
                "registers arbitrary typed evidence families without Runner family-specific branches",
                "records repository revision, analyzer executions, process lifecycle and request provenance",
                "forbids legacy fallback and dual-write",
            ],
            "gaps": [
                "Foundation reuse is not yet compiled into the generic evidence request",
                "one Core process currently executes the complete evidence request",
            ],
            "typed_evidence_registry_status": "generic_core_evidence_runtime",
            "foundation_identity_status": "not_yet_requested_by_runtime",
            "analyzer_execution_status": "generic_contract_driven",
            "task_semantic_coupling": False,
            "target_compliance": "full",
        },
        {
            "schema_version": "knowledge_materialization_execution_run/v1",
            "scope": "knowledge_resolution_plan",
            "implementation_ref": "static_analysis_runner.knowledge_materialization_executor.execute_knowledge_materialization_plan",
            "strengths": [
                "executes materializations in dependency order from Knowledge Resolution Plan",
                "resolves typed evidence and prior knowledge artifacts from contracts",
                "calls one generic KLC runtime entrypoint without materialization-specific Runner branches",
                "publishes capabilities only from completed KLC results",
                "uses no Task, Suite or Core Profile semantics",
            ],
            "gaps": [],
            "typed_evidence_registry_status": "consumes_registered_typed_evidence",
            "foundation_identity_status": "not_applicable",
            "analyzer_execution_status": "consumes_registered_executions",
            "task_semantic_coupling": False,
            "target_compliance": "full",
        },
    ]


def _planning_conclusions() -> dict[str, Any]:
    return {
        "main_finding": (
            "Runner has one installed product runtime: knowledge_execution_plan/v1 drives typed Core evidence "
            "execution, artifact registration, KLC materialization dependencies and capability publication. "
            "Task/Suite orchestration has been removed; portfolio topology is parked outside the installed package."
        ),
        "what_this_contract_does_not_solve": [
            "Core remains the owner of analyzer-specific evidence contracts.",
            "KLC remains the owner of domain materialization handlers and query models.",
            "Parked portfolio topology is intentionally outside this runtime until the Islands track resumes.",
        ],
        "revised_sequence": [
            {"priority": 1, "step": "generic_knowledge_materialization_executor/v1", "status": "completed", "reason": "One generic KLC runtime executes registered materializations."},
            {"priority": 2, "step": "generic_core_evidence_runtime_and_executor", "status": "completed", "reason": "Typed Core evidence families execute without Runner family-specific branches."},
            {"priority": 3, "step": "knowledge_execution_plan/v1", "status": "completed", "reason": "Profiles and actual inputs compile into one validated DAG."},
            {"priority": 4, "step": "knowledge_execute_and_result/v1", "status": "completed", "reason": "The installed product runtime executes the DAG and emits one canonical result."},
            {"priority": 5, "step": "consumer_release_validation", "status": "next", "reason": "Validate API, Assistant, Reporting and UI against the consolidated typed runtime before release packaging."},
        ],
        "explicitly_deferred": [
            "portfolio topology and Islands v1",
            "caching and DAG optimization",
            "parallel evidence and materialization execution",
        ],
    }


def build_analysis_execution_result_catalog(
    core_target_contracts: Mapping[str, Any],
    klc_materialization_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic Runner-owned target execution-result contract.

    This is read-only architecture metadata. It does not execute or mutate product analysis runs.
    """
    _validate_core_target_contracts(core_target_contracts)
    _validate_klc_materialization_catalog(klc_materialization_catalog)

    current = _current_manifest_assessment()
    typed_present = sum(item["typed_evidence_registry_status"] not in {"missing", "indirect_missing"} for item in current)
    task_coupled = sum(bool(item["task_semantic_coupling"]) for item in current)
    foundation_present = sum(item["foundation_identity_status"] in {"present", "indirect"} for item in current)
    compliant = sum(item["target_compliance"] == "full" for item in current)

    payload: dict[str, Any] = {
        "schema_version": EXECUTION_RESULT_CATALOG_SCHEMA_VERSION,
        "runner_version": __version__,
        "execution_effect": "none",
        "purpose": "Runner-owned target execution-result contract and current runtime-manifest gap assessment.",
        "source": {
            "core_target_contracts_schema_version": core_target_contracts.get("schema_version"),
            "core_target_contracts_fingerprint": core_target_contracts.get("contracts_fingerprint"),
            "core_version": core_target_contracts.get("core_version"),
            "klc_materialization_catalog_schema_version": klc_materialization_catalog.get("schema_version"),
            "klc_materialization_catalog_fingerprint": klc_materialization_catalog.get("catalog_fingerprint"),
            "klc_version": klc_materialization_catalog.get("klc_version"),
        },
        "architecture_goal": {
            "core": "Core publishes self-describing typed evidence artifacts.",
            "runner": "Runner records execution, retries and artifact registrations without defining evidence or knowledge semantics.",
            "knowledge_layer": "KLC selects evidence by artifact_kind + schema_version and owns knowledge materialization outputs.",
        },
        "contract": _target_contract(),
        "current_manifest_assessment": current,
        "cross_contract_rules": {
            "evidence_artifact_contract": "core_evidence_artifact_contract/v1",
            "materialization_contract": "knowledge_materialization_contract/v3",
            "semantic_routing_contract": "evidence_semantic_routing/v1",
            "task_profile_suite_rule": "Task Suite and Core Profile are not part of canonical knowledge execution",
            "capability_rule": "capability_is_published_only_from_successful_KLC_materialization_output",
        },
        "planning_conclusions": _planning_conclusions(),
        "summary": {
            "current_manifest_variant_count": len(current),
            "fully_compliant_manifest_count": compliant,
            "manifest_variants_with_any_typed_registry_count": typed_present,
            "manifest_variants_with_direct_or_indirect_foundation_identity_count": foundation_present,
            "task_semantic_coupled_variant_count": task_coupled,
            "klc_materialization_count": int(
                (klc_materialization_catalog.get("summary") or {}).get("materialization_count") or 0
            ),
            "klc_runtime_registered_materialization_count": int(
                (klc_materialization_catalog.get("summary") or {}).get("runtime_registered_materialization_count") or 0
            ),
            "klc_runtime_unregistered_materialization_count": int(
                (klc_materialization_catalog.get("summary") or {}).get("runtime_unregistered_materialization_count") or 0
            ),
        },
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def write_analysis_execution_result_catalog(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def render_analysis_execution_result_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    conclusions = payload.get("planning_conclusions") or {}
    lines = [
        "# Analysis Execution Result Contract v1",
        "",
        f"- Runner version: `{payload.get('runner_version')}`",
        f"- Catalog schema: `{payload.get('schema_version')}`",
        f"- Contract: `{(payload.get('contract') or {}).get('contract_id')}`",
        f"- Execution effect: `{payload.get('execution_effect')}`",
        f"- Fingerprint: `{payload.get('catalog_fingerprint')}`",
        "",
        "## Target boundary",
        "",
        "- Core owns the meaning and schema of typed evidence artifacts.",
        "- Runner owns execution, retries, lifecycle and artifact registration.",
        "- KLC owns evidence selection and knowledge materialization.",
        "- Removed Task/Suite selectors are neither runtime inputs nor evidence provenance fields.",
        "",
        "## Current assessment",
        "",
        f"- Current manifest variants: **{summary.get('current_manifest_variant_count', 0)}**",
        f"- Fully compliant variants: **{summary.get('fully_compliant_manifest_count', 0)}**",
        f"- Variants with any typed artifact registry: **{summary.get('manifest_variants_with_any_typed_registry_count', 0)}**",
        f"- Variants with direct or indirect Foundation identity: **{summary.get('manifest_variants_with_direct_or_indirect_foundation_identity_count', 0)}**",
        f"- Task-semantic-coupled variants: **{summary.get('task_semantic_coupled_variant_count', 0)}**",
        f"- Current KLC task-semantic routes: **{summary.get('current_klc_task_semantic_route_count', 0)}**",
        "",
        "## Manifest gaps",
        "",
    ]
    for item in payload.get("current_manifest_assessment") or []:
        variant = f" ({item.get('variant')})" if item.get("variant") else ""
        lines.append(f"### `{item.get('schema_version')}`{variant}")
        lines.append("")
        lines.append(f"Scope: `{item.get('scope')}`. Target compliance: `{item.get('target_compliance')}`.")
        lines.append("")
        for gap in item.get("gaps") or []:
            lines.append(f"- {gap}")
        lines.append("")

    lines.extend([
        "## Main conclusion",
        "",
        str(conclusions.get("main_finding") or ""),
        "",
        "## Revised next steps",
        "",
    ])
    for item in conclusions.get("revised_sequence") or []:
        lines.append(f"{item.get('priority')}. **`{item.get('step')}`** — {item.get('reason')}")
    lines.extend(["", "## Explicitly deferred", ""])
    for item in conclusions.get("explicitly_deferred") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def write_analysis_execution_result_markdown(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_analysis_execution_result_markdown(payload), encoding="utf-8")
    return target


def load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid {label} JSON {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object: {source}")
    return payload
