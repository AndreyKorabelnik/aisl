from code_analyzer_core.framework_pattern_interpreter import apply_framework_pattern_rules, fact_matches_rule
from code_analyzer_core.models import EvidenceRef, Fact


def _call(name: str, method: str, receiver: str, observation_id: str = "call-1") -> Fact:
    return Fact(
        fact_type="java_method_call_observation",
        name=name,
        properties={
            "observation_id": observation_id,
            "method_name": method,
            "receiver_expression": receiver,
            "owner_fqcn": "sample.Converter",
        },
        evidence=[EvidenceRef(file_path="src/Converter.java", line_start=10, line_end=10, extractor="tree_sitter")],
    )


def test_rule_matches_nested_properties_and_regex():
    fact = _call("Converter.convert", "convert", "converter")
    assert fact_matches_rule(fact, {
        "fact_type": "java_method_call_observation",
        "properties": {
            "method_name": {"regex": "^conv"},
            "receiver_expression": {"equals": "converter"},
        },
    })


def test_interpreter_emits_provenance_preserving_observation():
    source = _call("Builder.key", "key", "builder", "call-key")
    emitted, status = apply_framework_pattern_rules([source], [{
        "rule_id": "builder-key-call",
        "output_kind": "builder_assignment_candidate",
        "match": {
            "fact_type": "java_method_call_observation",
            "properties": {"method_name": {"equals": "key"}},
        },
        "capture": {
            "method": "method_name",
            "receiver": "receiver_expression",
            "owner": "owner_fqcn",
        },
        "metadata": {"framework_family": "declarative-test"},
    }])

    assert status["observations_emitted"] == 1
    item = emitted[0]
    assert item.fact_type == "framework_pattern_observation"
    assert item.properties["source_observation_id"] == "call-key"
    assert item.properties["captured_properties"] == {
        "method": "key",
        "receiver": "builder",
        "owner": "sample.Converter",
    }
    assert item.evidence[0].file_path == "src/Converter.java"
    assert "confidence" not in item.properties


def test_interpreter_reports_zero_matches_without_guessing():
    emitted, status = apply_framework_pattern_rules([_call("A.run", "run", "a")], [{
        "rule_id": "missing",
        "match": {"fact_type": "java_method_reference_observation"},
    }])
    assert emitted == []
    assert status["matches_by_rule"] == {"missing": 0}
