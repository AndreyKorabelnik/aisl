from __future__ import annotations

import json
from pathlib import Path

from aisl_reporting.deterministic_er import (
    apply_deterministic_er_section,
    build_deterministic_er_section,
)


def _dataset() -> dict:
    return {
        "profile_id": "data-model-report/v1",
        "sections": {
            "diagrams": {
                "logical_er": {"status": "not_observed", "entities": [], "relationships": []},
                "physical_er": {
                    "status": "observed",
                    "mode": "complete",
                    "tables": [
                        {
                            "qualified_name": "mbk_cache.phone",
                            "name": "phone",
                            "attributes": [
                                {"name": "phoneid", "type": "BIGINT", "primary_key": True},
                                {"name": "operator.id", "type": "VARCHAR(1)", "primary_key": False},
                            ],
                            "primary_key_columns": ["phoneid"],
                        },
                        {
                            "qualified_name": "mbk_cache.link",
                            "name": "link",
                            "attributes": [
                                {"name": "linkid", "type": "BIGINT", "primary_key": True},
                                {"name": "phoneid", "type": "BIGINT", "primary_key": False},
                            ],
                            "primary_key_columns": ["linkid"],
                        },
                    ],
                    "relationships": [
                        {
                            "from_table": "mbk_cache.link",
                            "from_columns": ["phoneid"],
                            "to_table": "mbk_cache.phone",
                            "to_columns": ["phoneid"],
                            "column_pairs": [{"from_column": "phoneid", "to_column": "phoneid"}],
                            "constraint_name": "fk_link_phone",
                        }
                    ],
                },
                "observed_usage": {
                    "status": "observed",
                    "relationships": [
                        {
                            "left_table": "mbk_cache.link",
                            "right_table": "mbk_cache.phone",
                            "relation_kind": "jooq_join",
                            "column_pairs": [{"left_column": "phoneid", "right_column": "phoneid"}],
                        }
                    ],
                },
            }
        },
    }


def test_builds_safe_deterministic_physical_er_and_observed_usage() -> None:
    fragment = build_deterministic_er_section(_dataset())
    assert fragment.count("```mermaid") == 2
    assert "erDiagram" in fragment
    assert "flowchart LR" in fragment
    assert "mbk_cache.phone" in fragment  # exact names remain in the mapping/flowchart label
    assert "operator.id" not in fragment  # invalid attribute token is sanitized
    assert "operator_id" in fragment
    assert "PK" in fragment
    assert "FK" in fragment
    assert "}o--o|" in fragment
    assert "schemaname_" not in fragment


def test_replaces_only_er_section_and_preserves_report_body() -> None:
    report = """# Report\n\n## ER-диаграммы\n\n```mermaid\nerDiagram\n    broken\n```\n\n## Каталог объектов\n\nUseful catalog.\n"""
    result, metadata = apply_deterministic_er_section(report, _dataset())
    assert metadata["applied"] is True
    assert result.count("## ER-диаграммы") == 1
    assert "broken" not in result
    assert "Useful catalog." in result
    assert "deterministic-data-model-mermaid/v1" == metadata["generator"]


def test_not_applicable_to_other_profiles() -> None:
    report = "# SQL report\n"
    result, metadata = apply_deterministic_er_section(report, {"profile_id": "sql-source-inventory-report/v1"})
    assert result == report
    assert metadata["applied"] is False


def test_regression_dataset_from_release_can_be_rendered() -> None:
    candidate = Path("/mnt/data/reporting_llm_regression_0139/datasets/data-model-physical-only.json")
    if not candidate.is_file():
        return
    dataset = json.loads(candidate.read_text(encoding="utf-8"))
    fragment = build_deterministic_er_section(dataset)
    assert "```mermaid\nerDiagram" in fragment
    assert "physical-model" not in fragment
    assert fragment.count("```mermaid") >= 1


def test_sanitizes_mermaid_delimiters_and_multiline_labels() -> None:
    dataset = _dataset()
    physical = dataset["sections"]["diagrams"]["physical_er"]
    physical["relationships"][0]["column_pairs"] = [
        {"from_column": 'phone|id\n"unsafe"', "to_column": "phone\\id"}
    ]
    physical["tables"][0]["attributes"][1]["type"] = "VARCHAR(20)[]"
    observed = dataset["sections"]["diagrams"]["observed_usage"]
    observed["relationships"][0]["column_pairs"] = [
        {"left_column": "a|b", "right_column": 'c"d'}
    ]
    fragment = build_deterministic_er_section(dataset)
    assert "phone/id 'unsafe' = phone/id" in fragment
    assert '-->|"a/b = c\'d"|' in fragment
    assert "VARCHAR_20" in fragment
    assert "VARCHAR(20)[]" not in fragment
