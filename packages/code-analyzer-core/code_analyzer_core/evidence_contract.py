from __future__ import annotations

from typing import Any

STRICT_LEVELS = {"confirmed", "unresolved", "not_applicable"}
GAP_ACTIONABILITY_VALUES = {"actionable", "not_actionable", "exhausted", "not_relevant"}
SOURCE_INSPECTION_REQUEST_STATUS_VALUES = {
    "emitted",
    "required_but_not_emitted",
    "required_pending_request_link",
    "not_required",
    "not_required_exhausted_in_workspace",
    "not_created_no_concrete_target",
    "not_required_not_decision_blocking",
}
DECISION_BLOCKING_DIMENSIONS = {
    "persistence_write", "source_boundary", "field_mapping", "physical_storage",
    "end_to_end_trace", "sql_statement", "python_storage_boundary",
}
DEFAULT_ACTIONABLE_DIMENSIONS = {"persistence_write", "source_boundary", "field_mapping", "physical_storage", "end_to_end_trace"}


def strict_level(value: str | None) -> str:
    if value == "confirmed":
        return "confirmed"
    if value == "not_applicable":
        return "not_applicable"
    return "unresolved"


def maturity_props(
    dimensions: dict[str, str | None],
    *,
    notes: list[str] | None = None,
    actionable_dimensions: set[str] | None = None,
    decision_blocking_dimensions: set[str] | None = None,
    inspection_target_available: bool = True,
    not_actionable_reason: str | None = None,
    exhausted_dimensions: set[str] | None = None,
) -> dict[str, Any]:
    normalized = {k: strict_level(v) for k, v in dimensions.items()}
    applicable = [v for v in normalized.values() if v != "not_applicable"]
    overall = "not_applicable" if not applicable else ("unresolved" if "unresolved" in applicable else "confirmed")
    blockers = [f"{k}:unresolved" for k, v in normalized.items() if v == "unresolved"]
    actionable = actionable_dimensions if actionable_dimensions is not None else DEFAULT_ACTIONABLE_DIMENSIONS
    decision_blocking = decision_blocking_dimensions if decision_blocking_dimensions is not None else DECISION_BLOCKING_DIMENSIONS
    exhausted = exhausted_dimensions or set()
    lifecycle: list[dict[str, Any]] = []
    for dimension, level in normalized.items():
        if level != "unresolved":
            continue
        is_blocking = dimension in decision_blocking
        if is_blocking and dimension in exhausted:
            lifecycle.append({
                "dimension": dimension, "gap_type": f"{dimension}_unresolved",
                "decision_blocking": True, "actionability": "exhausted",
                "source_inspection_required": False,
                "source_inspection_request_status": "not_required_exhausted_in_workspace",
                "source_inspection_request_ids": [],
                "reason": "analyzer already exhausted supported in-workspace checks",
                "allowed_resolution": "report_gap_with_reason",
            })
        elif is_blocking and dimension in actionable and inspection_target_available:
            lifecycle.append({
                "dimension": dimension, "gap_type": f"{dimension}_unresolved",
                "decision_blocking": True, "actionability": "actionable",
                "source_inspection_required": True,
                "source_inspection_request_status": "required_pending_request_link",
                "source_inspection_request_ids": [],
                "reason": "decision-blocking unresolved gap has a concrete source inspection target",
                "allowed_resolution": "targeted_source_inspection_or_external_evidence",
            })
        elif is_blocking:
            lifecycle.append({
                "dimension": dimension,
                "gap_type": f"{dimension}_unresolved",
                "decision_blocking": True,
                "actionability": "not_actionable",
                "source_inspection_required": False,
                "source_inspection_request_status": "not_created_no_concrete_target",
                "source_inspection_request_ids": [],
                "reason": not_actionable_reason or "no concrete targeted inspection location is known",
                "allowed_resolution": "report_gap_with_reason",
            })
        else:
            lifecycle.append({
                "dimension": dimension,
                "gap_type": f"{dimension}_unresolved",
                "decision_blocking": False,
                "actionability": "not_relevant",
                "source_inspection_required": False,
                "source_inspection_request_status": "not_required_not_decision_blocking",
                "source_inspection_request_ids": [],
                "reason": "unresolved dimension does not block this profile decision",
                "allowed_resolution": "report_gap_with_reason",
            })
    return {
        "evidence_maturity_level": overall,
        "evidence_maturity_dimensions": normalized,
        "evidence_maturity_blockers": blockers,
        "evidence_maturity_notes": notes or [],
        "evidence_maturity_policy": "strict_confirmed_vs_unresolved_candidate_signals_are_navigation_only",
        "unresolved_gap_lifecycle": lifecycle,
        "source_inspection_required": any(x.get("source_inspection_required") for x in lifecycle),
    }


def candidate_signal(
    *,
    signal_type: str,
    target: str | None,
    basis: str,
    recommended_action: str,
    related_evidence_refs: list[str] | None = None,
    requires_source_inspection: bool = True,
) -> dict[str, Any]:
    return {
        "signal_type": signal_type,
        "target": target,
        "basis": basis,
        "is_evidence": False,
        "allowed_use": "navigation_only",
        "requires_source_inspection": requires_source_inspection,
        "recommended_action": recommended_action,
        "related_evidence_refs": [x for x in (related_evidence_refs or []) if x],
    }
