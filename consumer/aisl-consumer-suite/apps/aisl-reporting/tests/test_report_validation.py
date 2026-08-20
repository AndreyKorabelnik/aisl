from aisl_reporting.validation import validate_markdown_report


def test_report_validation_warns_about_unknown_evidence():
    dataset = {"request": {"include_evidence": True}, "evidence_index": {"evidence_aaaaaaaaaaaaaaaaaaaa": {}}}
    result = validate_markdown_report("## A\n[evidence_bbbbbbbbbbbbbbbbbbbb]", dataset, ["A"])
    assert result["valid"]
    assert not result["conforms"]
    assert result["errors"] == []
    assert {item["code"] for item in result["warnings"]} == {"unknown_evidence_ids"}


def test_report_validation_accepts_known_evidence():
    dataset = {"request": {"include_evidence": True}, "evidence_index": {"evidence_aaaaaaaaaaaaaaaaaaaa": {}}}
    result = validate_markdown_report("## A\n[evidence_aaaaaaaaaaaaaaaaaaaa]", dataset, ["A"])
    assert result["valid"]


def test_report_validation_accepts_any_markdown_heading_level_and_numbering():
    dataset = {"request": {"include_evidence": False}, "evidence_index": {}}
    result = validate_markdown_report(
        "# 1. Область отчёта\n### 2) Резюме\n",
        dataset,
        ["Область отчёта", "Резюме"],
    )
    assert result["conforms"]
    assert result["missing_required_headings"] == []


def test_report_validation_soft_mode_does_not_require_unavailable_evidence():
    dataset = {"request": {"include_evidence": True}, "evidence_index": {}}
    result = validate_markdown_report("# Отчёт\nТекст без обязательных разделов.\n", dataset, ["Резюме"])
    assert result["valid"]
    assert not result["conforms"]
    assert {item["code"] for item in result["warnings"]} == {"missing_required_headings"}


def test_report_validation_does_not_score_narrative_richness():
    dataset = {
        "request": {"include_evidence": False},
        "evidence_index": {},
        # Kept here to prove that legacy callers cannot reactivate subjective
        # word/table/diagram thresholds through dataset metadata.
        "quality_expectations": {"min_words": 10000, "legacy_baseline": "old"},
    }
    result = validate_markdown_report("## Резюме\nКраткий факт.\n", dataset, ["Резюме"])
    assert result["conforms"]
    assert result["warnings"] == []
    assert "quality_shortfalls" not in result


def test_report_validation_accepts_canonical_sql_inventory_evidence_ids():
    from aisl_reporting.validation import validate_markdown_report

    evidence_id = "sql_column_usage_repo_a_0123456789abcdef"
    result = validate_markdown_report(
        f"## Краткий вывод\nНаблюдение [{evidence_id}]\n",
        {
            "request": {"include_evidence": True},
            "evidence_index": {evidence_id: {"evidence_id": evidence_id}},
            "sections": {},
        },
        ["Краткий вывод"],
    )
    assert result["conforms"] is True
    assert result["evidence_citation_count"] == 1
    assert result["unknown_evidence_ids"] == []


def _data_model_dataset(*, logical: bool, physical: bool) -> dict:
    return {
        "profile_id": "data-model-report/v1",
        "request": {"include_evidence": False},
        "coverage": {"report_mode": "logical_and_physical" if logical and physical else ("logical_only" if logical else "physical_only")},
        "evidence_index": {},
        "sections": {
            "diagrams": {
                "logical_er": {
                    "status": "observed" if logical else "not_observed",
                    "entities": [{"name": "Customer"}] if logical else [],
                    "relationships": [],
                },
                "physical_er": {
                    "status": "observed" if physical else "not_observed",
                    "tables": [{"name": "customer"}] if physical else [],
                    "relationships": [],
                },
                "observed_usage": {"status": "not_observed", "relationships": []},
            }
        },
    }


def test_data_model_validation_warns_when_physical_er_is_missing() -> None:
    result = validate_markdown_report(
        "## ER-диаграммы\nОписание без Mermaid.\n",
        _data_model_dataset(logical=False, physical=True),
        ["ER-диаграммы"],
    )
    assert result["required_er_diagram_layers"] == ["physical_er"]
    assert result["required_er_diagram_count"] == 1
    assert result["observed_er_diagram_count"] == 0
    assert "missing_required_er_diagram" in {item["code"] for item in result["warnings"]}


def test_data_model_validation_accepts_non_empty_entity_only_er() -> None:
    report = """## ER-диаграммы

```mermaid
erDiagram
    CUSTOMER {
        bigint id PK
    }
```
"""
    result = validate_markdown_report(
        report,
        _data_model_dataset(logical=False, physical=True),
        ["ER-диаграммы"],
    )
    assert result["observed_er_diagram_count"] == 1
    assert "missing_required_er_diagram" not in {item["code"] for item in result["warnings"]}


def test_mixed_data_model_requires_two_er_blocks() -> None:
    one_block = """## ER-диаграммы

```mermaid
erDiagram
    CUSTOMER {
        string id
    }
```
"""
    result = validate_markdown_report(
        one_block,
        _data_model_dataset(logical=True, physical=True),
        ["ER-диаграммы"],
    )
    assert result["required_er_diagram_layers"] == ["logical_er", "physical_er"]
    assert result["required_er_diagram_count"] == 2
    assert result["observed_er_diagram_count"] == 1
    assert "missing_required_er_diagram" in {item["code"] for item in result["warnings"]}
