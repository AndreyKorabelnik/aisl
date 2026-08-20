from __future__ import annotations

from copy import deepcopy
from typing import Any

from code_analyzer_core.models import AnalysisResult, Fact, InterfaceInfo, RelationInfo

STRICT_EVIDENCE_CONTRACT_VERSION = "3.0"
STRICT_EVIDENCE_POLICY = "hard_evidence_only_navigation_signals_and_gap_lifecycle"
STRICT_LEVELS = {"confirmed", "unresolved", "not_applicable"}


def strict_level(value: Any) -> str:
    return str(value) if value in STRICT_LEVELS else "unresolved"


def normalize_strict_payload(value: Any) -> Any:
    if isinstance(value, list):
        return [normalize_strict_payload(x) for x in value]
    if not isinstance(value, dict):
        return value

    out: dict[str, Any] = {}
    for key, item in value.items():
        if key == "evidence_maturity_level":
            out[key] = strict_level(item)
        elif key == "evidence_maturity_dimensions" and isinstance(item, dict):
            out[key] = {str(k): strict_level(v) for k, v in item.items()}
        elif key == "candidate_signals" and isinstance(item, list):
            out[key] = [_candidate_signal(x) for x in item]
        else:
            out[key] = normalize_strict_payload(item)

    if any(k in out for k in ("evidence_maturity_level", "candidate_signals", "unresolved_gap_lifecycle", "source_inspection_request_id")):
        out.setdefault("strict_evidence_contract", STRICT_EVIDENCE_CONTRACT_VERSION)
        out.setdefault("strict_evidence_policy", STRICT_EVIDENCE_POLICY)
    return out


# Backward import alias for callers that only need the strict boundary function.
sanitize_public_payload = normalize_strict_payload


def _candidate_signal(signal: Any) -> Any:
    if not isinstance(signal, dict):
        return signal
    out = {k: normalize_strict_payload(v) for k, v in signal.items()}
    out["is_evidence"] = False
    out["allowed_use"] = "navigation_only"
    out.setdefault("requires_source_inspection", True)
    return out


def apply_strict_evidence_kernel(result: AnalysisResult) -> AnalysisResult:
    """Normalize strict-evidence metadata in-place.

    Older versions rebuilt every Pydantic model with a deep-copied properties
    dict. On large real-app workspaces this was unnecessarily expensive and could
    dominate fast profiles. Scanner facts are already owned by this AnalysisResult,
    so an in-place bounded properties normalization is safe and preserves the
    public contract.
    """
    for collection in (result.facts, result.mapper_facts, result.config_facts):
        for f in collection:
            f.properties = normalize_strict_payload(f.properties or {})
    for r in result.relations:
        r.properties = normalize_strict_payload(r.properties or {})
    for i in result.interfaces:
        i.properties = normalize_strict_payload(i.properties or {})
    result.coverage["strict_evidence_contract"] = {
        "version": STRICT_EVIDENCE_CONTRACT_VERSION,
        "policy": STRICT_EVIDENCE_POLICY,
        "public_maturity_levels": ["confirmed", "unresolved", "not_applicable"],
        "candidate_signals_are_evidence": False,
    }
    return result
