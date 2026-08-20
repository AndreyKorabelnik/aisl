from code_analyzer_core.determinism import canonicalize_fact_order
from code_analyzer_core.models import AnalysisResult, EvidenceRef, Fact
from code_analyzer_core.scanners.system_description_enrichment import _best_evidence


def _result(facts):
    return AnalysisResult(system_name="s", project_code="p", repo_path="/tmp/r", facts=facts)


def test_fact_order_is_independent_of_hydration_order():
    first = Fact(fact_type="z", name="b", properties={"id": 2})
    second = Fact(fact_type="a", name="c", properties={"id": 1})
    third = Fact(fact_type="a", name="b", properties={"id": 3})
    left = _result([first, second, third])
    right = _result([third, first, second])
    canonicalize_fact_order(left)
    canonicalize_fact_order(right)
    assert left.facts == right.facts


def test_best_evidence_prefers_precise_trace_over_generic_tree_sitter():
    generic = EvidenceRef(file_path="A.java", line_start=32, extractor="java_tree_sitter")
    trace = EvidenceRef(file_path="A.java", line_start=28, line_end=33, extractor="java_trace_builder_trace")
    assert _best_evidence([generic], [trace], limit=1) == [trace]
