from __future__ import annotations

from knowledge_layer_core.sql_inventory_quality import evaluate_inventory, normalize_identifier


def _fixture() -> dict:
    return {
        "schema_version": "sql-source-inventory-quality/v1",
        "fixture_id": "synthetic",
        "repo_id": "repo",
        "cases": [
            {
                "file": "a.sql",
                "tags": [],
                "expected_relations": [
                    {
                        "identity": "${Schema}.Customer",
                        "relation_kind": "physical_template",
                        "expected_view": "business_sources",
                    },
                    {
                        "identity": "work.tmp_customer",
                        "relation_kind": "physical",
                        "expected_view": "technical",
                    },
                ],
                "field_expectations": [
                    {
                        "relation_identity": "${Schema}.Customer",
                        "mode": "exact",
                        "fields": [
                            {"name": "id", "roles": ["join", "projection"]},
                            {"name": "status", "roles": ["filter"]},
                        ],
                    }
                ],
            }
        ],
    }


def test_normalize_identifier_preserves_placeholder_identity_case_insensitively() -> None:
    assert normalize_identifier('  `${Schema}` . "Customer" ') == "${schema}.customer"


def test_quality_report_counts_relation_classification_and_fields() -> None:
    actual = {
        "a.sql": {
            "relations": {
                ("physical_template", "${schema}.customer"): {
                    "identity": "${Schema}.Customer",
                    "view": "business_sources",
                    "fields": {
                        "id": ["join", "projection"],
                        "status": ["filter"],
                    },
                },
                ("physical", "work.tmp_customer"): {
                    "identity": "work.tmp_customer",
                    "view": "technical",
                    "fields": {},
                },
            },
            "column_usages": 3,
            "unresolved_column_usages": 0,
        }
    }
    report = evaluate_inventory(_fixture(), actual)
    metrics = report["metrics"]
    assert metrics["relation_precision"] == 1.0
    assert metrics["relation_recall"] == 1.0
    assert metrics["classification_accuracy"] == 1.0
    assert metrics["field_precision"] == 1.0
    assert metrics["field_recall"] == 1.0
    assert metrics["field_role_accuracy"] == 1.0
    assert report["cases"][0]["status"] == "passed"


def test_quality_report_exposes_missing_extra_and_wrong_visibility() -> None:
    actual = {
        "a.sql": {
            "relations": {
                ("physical_template", "${schema}.customer"): {
                    "identity": "${Schema}.Customer",
                    "view": "technical",
                    "fields": {"id": ["projection"], "extra": ["filter"]},
                },
                ("physical", "other.unexpected"): {
                    "identity": "other.unexpected",
                    "view": "business_sources",
                    "fields": {},
                },
            },
            "column_usages": 3,
            "unresolved_column_usages": 1,
        }
    }
    report = evaluate_inventory(_fixture(), actual)
    case = report["cases"][0]
    assert report["metrics"]["relation_false_positive"] == 1
    assert report["metrics"]["relation_false_negative"] == 1
    assert case["classification_mismatches"]
    assert case["field_mismatches"][0]["missing_fields"] == ["status"]
    assert case["field_mismatches"][0]["unexpected_fields"] == ["extra"]
    assert case["field_mismatches"][0]["role_mismatches"]
