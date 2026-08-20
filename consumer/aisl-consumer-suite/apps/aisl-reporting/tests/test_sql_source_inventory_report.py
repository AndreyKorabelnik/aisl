from pathlib import Path
from types import SimpleNamespace

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profiles.sql_source_inventory_report.v1 import builder


class _Client:
    def get_json(self, path, *, params=None):
        assert path == "/api/knowledge/v1/systems/fixture/sql/source-inventory"
        assert params == {
            "revision_id": "revision-1",
            "view": "business_sources",
            "max_evidence_per_role": 3,
        }
        return {
            "inventory_schema_version": "sql-source-inventory/v1",
            "filters": {"view": "business_sources"},
            "items": [{
                "repo_id": "mart",
                "relation_id": "relation-1",
                "relation_identity": "source.customer",
                "relation_kind": "physical",
                "usage_roles": ["join"],
                "occurrence_count": 3,
                "statement_count": 2,
                "field_count": 1,
                "evidence_count": 2,
                "evidence_refs": [{"evidence_id": "rel-ev", "file": "sql/load.sql", "line_start": 10}],
                "fields": [{
                    "name": "customer_id",
                    "usage_roles": ["join"],
                    "occurrence_count": 3,
                    "statement_count": 2,
                    "evidence_count": 3,
                    "evidence_count_by_role": {"join": 3},
                    "evidence_refs": [{"evidence_id": "field-ev", "file": "sql/load.sql", "line_start": 12}],
                }],
            }],
            "coverage": {
                "analysis_status": "partial",
                "repositories": [{
                    "repo_id": "mart",
                    "analysis_status": "partial",
                    "source_content_fingerprint": "a" * 64,
                    "coverage_json": {
                        "column_usages": {"source_inventory": {
                            "resolved_source_field_usages": 10,
                            "unresolved_source_field_usages": 1,
                            "source_field_resolution_rate": 0.9,
                            "unresolved_by_basis": {"ambiguous_unqualified": 1},
                        }},
                        "gaps": {"total": 1, "by_kind": {"source_relation_ambiguous": 1}},
                    },
                }],
            },
        }


def _source():
    return SimpleNamespace(
        system_id="fixture",
        revision_id="revision-1",
        client=_Client(),
        revision={"execution": {"scope_kind": "repository"}},
        selected_artifact={"artifact_id": "sql-artifact"},
        capabilities=("common.sql-source-inventory",),
    )


def test_sql_source_inventory_report_dataset_is_complete_and_conservative():
    request = ReportRequest(
        report_type="sql-source-inventory-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        knowledge_source=_source(),
        audience="business",
        detail_level="standard",
    )

    dataset = builder.build_dataset(request)

    assert dataset["profile_id"] == "sql-source-inventory-report/v1"
    assert dataset["coverage"]["source_count"] == 1
    assert dataset["coverage"]["used_field_count"] == 1
    assert dataset["scope"] == {"kind": "repository", "id": "fixture", "repository_ids": ["mart"]}
    item = dataset["sections"]["source_inventory"]["items"][0]
    assert item["relation_identity"] == "source.customer"
    assert item["fields"][0]["name"] == "customer_id"
    assert dataset["sections"]["limitations"]["coverage"]["repositories"][0]["source_inventory"]["unresolved_by_basis"]["ambiguous_unqualified"] == 1
    assert set(dataset["evidence_index"]) == {"rel-ev", "field-ev"}
    assert dataset["sections"]["technical_appendix"]["revision_id"] == "revision-1"
    assert "must not be assigned" in dataset["interpretation_policy"]["unmapped_fields"].lower()


def test_sql_source_inventory_report_requires_published_capability():
    source = _source()
    source.capabilities = ()
    request = ReportRequest(
        report_type="sql-source-inventory-report",
        report_version="v1",
        api_url="http://knowledge-api.test",
        system_id="fixture",
        knowledge_source=source,
    )
    try:
        builder.build_dataset(request)
    except ValueError as exc:
        assert "common.sql-source-inventory" in str(exc)
    else:
        raise AssertionError("missing SQL capability must be rejected")


def test_sql_source_inventory_prompt_forbids_unmapped_assignment():
    prompt = Path(builder.__file__).with_name("renderer-prompt.md").read_text(encoding="utf-8")
    assert "Не назначай их таблицам" in prompt
    assert "полный каталог" in prompt
    assert "Не читай DuckDB" in prompt
