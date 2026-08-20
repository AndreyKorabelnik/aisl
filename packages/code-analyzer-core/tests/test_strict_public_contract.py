import json

from code_analyzer_core.evidence_kernel import normalize_strict_payload


def test_strict_payload_keeps_only_strict_maturity_levels_and_navigation_signals():
    payload = {
        "candidate_signals": [{"signal_type": "dao", "target": "x", "basis": "name", "recommended_action": "inspect"}],
        "evidence_maturity_dimensions": {"persistence_write": "not_a_strict_level", "field_mapping": "confirmed"},
    }
    sanitized = normalize_strict_payload(payload)
    text = json.dumps(sanitized)
    assert sanitized["evidence_maturity_dimensions"]["persistence_write"] == "unresolved"
    assert sanitized["evidence_maturity_dimensions"]["field_mapping"] == "confirmed"
    assert sanitized["candidate_signals"][0]["is_evidence"] is False
    assert sanitized["candidate_signals"][0]["allowed_use"] == "navigation_only"
    assert "strict_evidence_contract" in text
