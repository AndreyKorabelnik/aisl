from __future__ import annotations

import hashlib
import json
from typing import Any

from code_analyzer_core.models import AnalysisResult, Fact


def _json_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_fact_sort_key(fact: Fact) -> tuple[str, str, str, str]:
    """Return an order key independent of scanner execution or hydration order.

    Facts are observations, so their list position is not semantic.  A stable
    ordering is nevertheless required for reproducible stores, bounded compact
    projections and evidence selection when the same fact set is supplied by a
    direct scan or by a reusable foundation artifact.
    """

    evidence_payload = [item.model_dump(mode="json") for item in fact.evidence]
    return (
        str(fact.fact_type or ""),
        str(fact.name or ""),
        _json_digest(fact.properties or {}),
        _json_digest(evidence_payload),
    )


def canonicalize_fact_order(result: AnalysisResult) -> dict[str, int]:
    result.facts.sort(key=canonical_fact_sort_key)
    result.mapper_facts.sort(key=canonical_fact_sort_key)
    result.config_facts.sort(key=canonical_fact_sort_key)
    return {
        "facts": len(result.facts),
        "mapper_facts": len(result.mapper_facts),
        "config_facts": len(result.config_facts),
    }
