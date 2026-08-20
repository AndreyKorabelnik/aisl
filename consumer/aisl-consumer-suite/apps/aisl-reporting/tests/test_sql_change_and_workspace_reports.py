from types import SimpleNamespace

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profiles.sql_change_analysis.v1.builder import build_dataset as build_change
from aisl_reporting.profiles.workspace_sql_catalog_report.v1.builder import (
    build_dataset as build_workspace,
)


class Client:
    def get_json(self, path, *, params=None):
        if path.endswith("/field-calculation"):
            return {
                "coverage_status": "complete",
                "terminal_sources": [
                    {"relation_name": "src.customer", "column_name": "name"}
                ],
                "gap_count": 0,
            }
        if path.endswith("/target-column-lineage"):
            return {
                "items": [
                    {
                        "target_column": "name",
                        "terminal_relation_name": "src.customer",
                    }
                ],
                "gaps": [],
                "gap_count": 0,
            }
        if path.endswith("/target-candidates"):
            return {
                "candidates": [
                    {"recommended_target_relation": "dm.customer", "score": 100}
                ],
                "candidate_count": 1,
            }
        if path.endswith("/workspace-catalog"):
            return {
                "repository_ids": ["repo-a", "repo-b"],
                "repository_count": 2,
                "source_count": 2,
                "sources": [{"artifact_id": "a"}, {"artifact_id": "b"}],
                "coverage": {"coverage_status": "complete"},
            }
        if path.endswith("/source-inventory"):
            assert params["max_evidence_per_role"] == 1
            return {
                "item_count": 2,
                "coverage": {"analysis_status": "partial"},
                "items": [
                    {
                        "relation_id": "relation-a",
                        "repo_id": "repo-a",
                        "relation_kind": "physical",
                        "relation_identity": "src.a",
                        "usage_roles": ["projection"],
                        "semantic_role": "external_source",
                        "classification_status": "confirmed",
                        "occurrence_count": 2,
                        "statement_count": 1,
                        "field_count": 1,
                        "fields": [
                            {
                                "name": "id",
                                "usage_roles": ["projection"],
                                "resolution_statuses": ["resolved"],
                                "resolution_bases": ["alias"],
                                "occurrence_count": 2,
                                "statement_count": 1,
                                "evidence_count": 2,
                                "evidence_count_by_role": {"projection": 2},
                                "evidence_refs": [
                                    {
                                        "file": "sql/a.sql",
                                        "line_start": 10,
                                        "usage_role": "projection",
                                        "query_id": "query-a",
                                        "scope_id": "scope-a",
                                        "evidence_id": "column-evidence-a",
                                    }
                                ],
                                "evidence_truncated": True,
                            }
                        ],
                        "evidence_count": 2,
                        "evidence_count_by_role": {"projection": 2},
                        "evidence_refs": [
                            {
                                "file": "sql/a.sql",
                                "line_start": 10,
                                "usage_role": "projection",
                                "query_id": "query-a",
                                "scope_id": "scope-a",
                                "evidence_id": "relation-evidence-a",
                            }
                        ],
                        "evidence_truncated": True,
                    },
                    {
                        "relation_id": "relation-b",
                        "repo_id": "repo-b",
                        "relation_kind": "physical_template",
                        "relation_identity": "${schema}.src_b",
                        "usage_roles": ["join"],
                        "semantic_role": "external_source",
                        "classification_status": "confirmed",
                        "occurrence_count": 1,
                        "statement_count": 1,
                        "field_count": 0,
                        "fields": [],
                        "evidence_count": 1,
                        "evidence_count_by_role": {"join": 1},
                        "evidence_refs": [
                            {
                                "file": "sql/b.sql",
                                "line_start": 1,
                                "usage_role": "join",
                                "query_id": "query-b",
                                "scope_id": "scope-b",
                                "evidence_id": "relation-evidence-b",
                            }
                        ],
                    },
                ],
            }
        raise AssertionError(path)

    def post_json(self, path, payload, *, params=None):
        assert path.endswith("/attribute-insertion-context")
        return {
            "target": {"logical_target_name": "customer"},
            "recommended_insertion": {"file": "sql/load.sql"},
        }


def test_sql_change_report_combines_all_product_queries():
    source = SimpleNamespace(
        system_id="demo",
        revision_id="rev-1",
        client=Client(),
        revision={"execution": {"scope_kind": "repository"}},
        selected_artifact={"artifact_id": "sql"},
        capabilities=(
            "common.sql-field-calculation",
            "common.sql-target-resolution",
            "common.sql-attribute-insertion-context",
            "common.sql-target-column-lineage",
        ),
    )
    request = ReportRequest(
        report_type="sql-change-analysis-report",
        report_version="v1",
        api_url="http://api",
        system_id="demo",
        knowledge_source=source,
        focus=(
            "target_relation=dm.customer",
            "target_column=name",
            "source_relation=src.customer",
            "source_column=name",
        ),
    )
    dataset = build_change(request)
    assert (
        dataset["sections"]["field_calculation"]["terminal_sources"][0][
            "relation_name"
        ]
        == "src.customer"
    )
    assert dataset["sections"]["target_candidates"]["candidate_count"] == 1
    assert (
        dataset["sections"]["attribute_insertion_context"]["recommended_insertion"][
            "file"
        ]
        == "sql/load.sql"
    )
    assert dataset["sections"]["target_column_lineage"]["gap_count"] == 0


def test_workspace_report_preserves_all_relations_and_fields_in_compact_projection():
    source = SimpleNamespace(
        system_id="workspace",
        revision_id="rev-w",
        client=Client(),
        revision={"execution": {"scope_kind": "workspace"}},
        selected_artifact={"artifact_id": "workspace-sql"},
        capabilities=("common.workspace-sql-catalog",),
    )
    request = ReportRequest(
        report_type="workspace-sql-catalog-report",
        report_version="v1",
        api_url="http://api",
        system_id="workspace",
        knowledge_source=source,
    )

    dataset = build_workspace(request)

    assert dataset["scope"]["repository_ids"] == ["repo-a", "repo-b"]
    assert dataset["sections"]["summary"] == {
        "repository_count": 2,
        "source_artifact_count": 2,
        "inventory_item_count": 2,
        "inventory_field_count": 1,
    }
    assert len(dataset["sections"]["source_inventory"]) == 2
    assert dataset["sections"]["source_inventory_coverage"] == {
        "analysis_status": "partial"
    }
    projection = dataset["sections"]["inventory_projection"]
    assert projection["source_relation_count"] == 2
    assert projection["projected_relation_count"] == 2
    assert projection["source_field_count"] == 1
    assert projection["projected_field_count"] == 1

    relation = dataset["sections"]["source_inventory"][0]
    assert relation["evidence_refs"] == [
        {"file": "sql/a.sql", "line_start": 10, "usage_role": "projection"}
    ]
    field = relation["fields"][0]
    assert field["evidence_count"] == 2
    assert "evidence_refs" not in field
    assert "resolution_bases" not in field
