from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aisl_reporting.contracts import ReportRequest
from aisl_reporting.profiles.data_model_report.v1 import builder
from aisl_reporting.profiles.data_model_report.v1.er_dataset import (
    build_logical_er,
    build_observed_usage,
    build_physical_er,
)


class _Query:
    def __init__(self, declared: list[dict] | None = None) -> None:
        self.declared = declared or []

    def declared_table_relationships(self, *, max_results: int, page_token: str = "") -> dict:
        offset = int(page_token or 0)
        page = self.declared[offset : offset + max_results]
        next_offset = offset + len(page)
        return {
            "items": page,
            "total_count": len(self.declared),
            "next_token": str(next_offset) if next_offset < len(self.declared) else None,
        }

    def get_table(self, table_id: str) -> dict:
        name = table_id if "." in table_id else f"schema.{table_id}"
        short = name.rsplit(".", 1)[-1]
        return {
            "db_schema_tables": [
                {
                    "db_table_occurrence_id": table_id,
                    "repo_id": "repo",
                    "table_name": short,
                    "schema_name": name.rsplit(".", 1)[0],
                    "qualified_table_name": name,
                    "description": f"Table {name}",
                    "source_type": "ddl",
                }
            ],
            "columns": [
                {
                    "db_table_occurrence_id": table_id,
                    "column_name": "id",
                    "sql_type": "bigint",
                    "nullable": False,
                },
                {
                    "db_table_occurrence_id": table_id,
                    "column_name": "name",
                    "sql_type": "varchar",
                    "nullable": True,
                },
            ],
            "keys": [
                {
                    "db_table_occurrence_id": table_id,
                    "db_key_occurrence_id": f"pk:{table_id}",
                    "constraint_name": f"pk_{short}",
                    "constraint_kind": "primary_key",
                    "columns_json": ["id"],
                }
            ],
        }


class _ReportingService:
    def __init__(self, declared: list[dict] | None = None) -> None:
        self.query = _Query(declared)


class _Result:
    def __init__(self, items=(), summary=None, evidence=()) -> None:
        self.items = tuple(items)
        self.summary = dict(summary or {})
        self.evidence = tuple(evidence)

    def to_dict(self) -> dict:
        return {"summary": self.summary, "items": list(self.items)}


class _Scope:
    def to_dict(self) -> dict:
        return {"kind": "repository", "id": "repo", "repository_ids": ["repo"]}


def _declared(index: int, schema: str = "s1") -> dict:
    return {
        "db_relationship_occurrence_id": f"rel-{index}",
        "repo_id": "repo",
        "constraint_name": f"fk_{index}",
        "relationship_kind": "foreign_key",
        "source_table": f"a_{index}",
        "source_qualified_table_name": f"{schema}.a_{index}",
        "source_columns_json": ["target_id"],
        "target_table": f"b_{index}",
        "target_qualified_table_name": f"{schema}.b_{index}",
        "target_columns_json": ["id"],
        "source_db_table_occurrence_id": f"{schema}.a_{index}",
        "target_db_table_occurrence_id": f"{schema}.b_{index}",
        "source_set": "ddl",
        "module_name": "module",
    }


def test_logical_er_keeps_all_small_relationship_sets() -> None:
    inventory = [
        {"object_id": "A", "fqcn": "domain.A", "name": "A", "package_name": "domain", "object_kind": "root_entity", "direct_field_count": 2},
        {"object_id": "B", "fqcn": "domain.B", "name": "B", "package_name": "domain", "object_kind": "entity", "direct_field_count": 1},
    ]
    relationships = [
        {
            "relationship_id": "r1",
            "relationship_kind": "effective_association",
            "source": {"object_fqcn": "domain.A", "field": "b", "cardinality": "one"},
            "target": {"type_fqcn": "domain.B"},
            "evidence_ids": ["e1"],
        }
    ]
    result = build_logical_er(inventory, relationships, [])
    assert result["mode"] == "complete"
    assert result["relationships_truncated"] is False
    assert result["relationships"] == [
        {
            "relationship_id": "r1",
            "from": "domain.A",
            "to": "domain.B",
            "field": "b",
            "relation_kind": "effective_association",
            "cardinality": "one",
            "inherited": False,
            "polymorphic_targets": [],
            "evidence_ids": ["e1"],
            "basis": "logical_relationship_evidence",
        }
    ]


def test_physical_er_uses_only_declared_relationships_and_groups_large_models() -> None:
    declared = [_declared(index, "s1" if index % 2 == 0 else "s2") for index in range(35)]
    service = _ReportingService(declared)
    representatives = [
        {"object_id": "s1.a_0", "qualified_name": "s1.a_0", "name": "a_0", "schema": "s1", "column_count": 2},
        {"object_id": "standalone", "qualified_name": "s3.standalone", "name": "standalone", "schema": "s3", "column_count": 2},
    ]
    result = build_physical_er(
        service,
        representatives,
        declared,
        table_total=80,
        declared_total=35,
        declared_collection_truncated=False,
    )
    assert result["mode"] == "overview"
    assert result["table_count"] == 80
    assert result["declared_relationship_count"] == 35
    assert result["selected_relationship_count"] == 30
    assert result["relationships_truncated"] is True
    assert {item["basis"] for item in result["relationships"]} == {"declared_schema_relationship"}
    assert {item["status"] for item in result["relationships"]} == {"confirmed"}
    assert {item["schema"] for item in result["domain_groups"]} == {"s1", "s2"}
    assert any(table["primary_key_columns"] == ["id"] for table in result["tables"])


def test_observed_usage_is_explicitly_not_physical_er() -> None:
    result = build_observed_usage(
        [
            {
                "relationship_id": "join-1",
                "relation_kind": "join",
                "source_kind": "sql",
                "left_table": "a",
                "right_table": "b",
                "matched_declared_keys": [],
            }
        ],
        total=4,
    )
    assert result["relationship_count"] == 4
    assert result["selected_relationship_count"] == 1
    assert result["relationships_truncated"] is True
    assert "not a declared FK" in result["semantics"]


def test_physical_er_and_observed_usage_remain_separate() -> None:
    tables = [
        {
            "physical_model_table_id": "table-a",
            "table_code": "schema.a",
            "columns": [{"column_code": "id", "data_type": "bigint"}],
        },
        {
            "physical_model_table_id": "table-b",
            "table_code": "schema.b",
            "columns": [{"column_code": "id", "data_type": "bigint"}],
        },
    ]
    physical = builder._physical_er(
        tables,
        [
            {
                "physical_model_relationship_id": "fk-1",
                "child_table_code": "schema.a",
                "parent_table_code": "schema.b",
                "joins": [{"child_column_code": "b_id", "parent_column_code": "id"}],
                "resolution_status": "matched",
            }
        ],
        1,
    )
    observed = {
        "status": "not_observed",
        "diagram_kind": "observed_usage",
        "relationships": [],
        "semantics": "Observed usage is a separate knowledge layer.",
    }

    assert physical["declared_relationship_count"] == 1
    assert physical["relationships"][0]["basis"] == "physical_model_relationship"
    assert observed["relationships"] == []
    assert observed["diagram_kind"] == "observed_usage"
