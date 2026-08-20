from aisl_reporting.regression import compare_reports


def test_regression_detects_required_features(tmp_path):
    expectations = tmp_path / "expectations.yaml"
    expectations.write_text("required_capabilities: [executive_summary, exact_evidence_refs, diagram_ready_relations]\n")
    dataset = {"schema_version": "report_dataset/v1", "evidence_index": {"evidence_aaaaaaaaaaaaaaaaaaaa": {}}, "sections": {"diagrams": {"architecture": {}}}}
    result = compare_reports(old_report="# old", new_report="## Резюме\n[evidence_aaaaaaaaaaaaaaaaaaaa]", dataset=dataset, expectations_path=expectations)
    assert result["passed"]
