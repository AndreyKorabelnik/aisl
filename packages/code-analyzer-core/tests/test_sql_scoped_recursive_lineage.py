import json
from pathlib import Path

from code_analyzer_core.sql_profile import _build_scoped_recursive_lineage
from tests.sql_evidence_test_support import run_sql_evidence


from tests.sql_evidence_test_support import read_sql_output


def _read(path: Path):
    return read_sql_output(path)


def _analyze(tmp_path: Path, sql: str):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.sql").write_text(sql, encoding="utf-8")
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="recursive_lineage",
    )
    return out


def test_recursive_lineage_resolves_cte_expression_to_physical_column(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH prepared AS (
            SELECT upper(c.name) AS normalized_name
            FROM src.client c
        )
        SELECT p.normalized_name
        FROM prepared p;
        """,
    )
    paths = _read(out / "compact/sql_recursive_column_lineage.json")

    assert len(paths) == 1
    path = paths[0]
    assert path["target_column"] == "normalized_name"
    assert path["terminal_relation_name"] == "src.client"
    assert path["terminal_column"] == "name"
    assert path["recursion_depth"] == 1
    assert path["lineage_status"] == "confirmed"
    assert path["physical_origin_status"] == "confirmed"
    assert path["branch_path"][0]["intermediate_relation_name"] == "prepared"
    assert [item["expression_kind"] for item in path["transformation_path"]] == [
        "direct_column",
        "normalization_or_cast",
    ]


def test_recursive_lineage_traverses_multiple_cte_levels(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH first_step AS (
            SELECT c.id FROM src.client c
        ), second_step AS (
            SELECT f.id FROM first_step f
        )
        SELECT s.id FROM second_step s;
        """,
    )
    path = _read(out / "facts/facts_by_type/sql_recursive_column_lineage.json")[0]

    assert path["terminal_relation_name"] == "src.client"
    assert path["terminal_column"] == "id"
    assert path["recursion_depth"] == 2
    assert [item["intermediate_relation_name"] for item in path["branch_path"]] == [
        "second_step",
        "first_step",
    ]


def test_union_lineage_preserves_every_branch_by_output_ordinal(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH combined AS (
            SELECT a.id AS id FROM src.a a
            UNION ALL
            SELECT b.customer_id AS customer_id FROM src.b b
        )
        SELECT c.id FROM combined c;
        """,
    )
    paths = _read(out / "compact/sql_recursive_column_lineage.json")

    assert {(item["terminal_relation_name"], item["terminal_column"]) for item in paths} == {
        ("src.a", "id"),
        ("src.b", "customer_id"),
    }
    assert {item["branch_path"][0]["definition_branch_ordinal"] for item in paths} == {1, 2}
    second = next(item for item in paths if item["terminal_relation_name"] == "src.b")
    assert second["branch_path"][0]["projection_mapping_basis"] == "output_name"
    assert second["branch_path"][0]["projection_output_name"] == "customer_id"


def test_recursive_lineage_preserves_terminal_expression_inside_cte(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.snapshot AS
        WITH prepared AS (
            SELECT current_timestamp() AS loaded_at
        )
        SELECT p.loaded_at FROM prepared p;
        """,
    )
    path = _read(out / "compact/sql_recursive_column_lineage.json")[0]

    assert path["terminal_source_kind"] == "expression_without_column"
    assert path["terminal_relation_name"] is None
    assert path["recursive_resolution_status"] == "not_applicable"
    assert path["physical_origin_status"] == "not_applicable"
    assert path["recursion_depth"] == 1


def _synthetic_direct(relation_id: str) -> dict:
    return {
        "sql_direct_column_lineage_id": "direct_1",
        "query_id": "q1",
        "write_target_id": "w1",
        "target_projection_binding_id": "b1",
        "target_relation_name": "mart.target",
        "target_relation_kind": "physical",
        "target_column": "id",
        "target_mapping_status": "confirmed",
        "projection_id": "root_projection",
        "source_scope_id": "root_scope",
        "expression": "x.id",
        "expression_kind": "direct_column",
        "source_kind": "column",
        "source_relation_id": relation_id,
        "source_column_usage_id": "root_usage",
        "source_column": "id",
        "direct_lineage_status": "confirmed_direct",
        "file": "model.sql",
        "line_start": 1,
        "evidence": [],
    }


def test_cycle_detection_emits_partial_path_and_gap() -> None:
    direct = [_synthetic_direct("relation_cycle")]
    relations = [{
        "sql_relation_id": "relation_cycle",
        "relation_kind": "cte",
        "relation_name": "cycle_cte",
        "source_scope_ids": ["scope_cycle"],
        "definition_status": "resolved",
    }]
    projections = [{
        "sql_projection_id": "projection_cycle",
        "scope_id": "scope_cycle",
        "projection_ordinal": 1,
        "output_name": "id",
        "expression": "c.id",
        "expression_kind": "direct_column",
        "is_wildcard": False,
        "source_column_usage_ids": ["usage_cycle"],
        "evidence": [],
    }]
    usages = [{
        "sql_column_usage_id": "usage_cycle",
        "column_name": "id",
        "relation_id": "relation_cycle",
        "resolution_status": "resolved",
    }]

    paths, gaps = _build_scoped_recursive_lineage(
        repo_id="cycle",
        direct_lineage=direct,
        projections=projections,
        column_usages=usages,
        relations=relations,
    )

    assert len(paths) == 1
    assert paths[0]["lineage_status"] == "partial"
    assert paths[0]["terminal_relation_name"] == "cycle_cte"
    assert any(item["gap_kind"] == "recursive_lineage_cycle" for item in gaps)


def test_depth_limit_emits_partial_path_and_gap() -> None:
    direct = [_synthetic_direct("relation_one")]
    relations = [
        {
            "sql_relation_id": "relation_one",
            "relation_kind": "cte",
            "relation_name": "one",
            "source_scope_ids": ["scope_one"],
            "definition_status": "resolved",
        },
        {
            "sql_relation_id": "relation_two",
            "relation_kind": "cte",
            "relation_name": "two",
            "source_scope_ids": ["scope_two"],
            "definition_status": "resolved",
        },
    ]
    projections = [
        {
            "sql_projection_id": "projection_one",
            "scope_id": "scope_one",
            "projection_ordinal": 1,
            "output_name": "id",
            "expression": "two.id",
            "expression_kind": "direct_column",
            "is_wildcard": False,
            "source_column_usage_ids": ["usage_one"],
            "evidence": [],
        },
        {
            "sql_projection_id": "projection_two",
            "scope_id": "scope_two",
            "projection_ordinal": 1,
            "output_name": "id",
            "expression": "src.id",
            "expression_kind": "direct_column",
            "is_wildcard": False,
            "source_column_usage_ids": [],
            "evidence": [],
        },
    ]
    usages = [{
        "sql_column_usage_id": "usage_one",
        "column_name": "id",
        "relation_id": "relation_two",
        "resolution_status": "resolved",
    }]

    paths, gaps = _build_scoped_recursive_lineage(
        repo_id="depth",
        direct_lineage=direct,
        projections=projections,
        column_usages=usages,
        relations=relations,
        max_depth=1,
    )

    assert len(paths) == 1
    assert paths[0]["lineage_status"] == "partial"
    assert any(item["gap_kind"] == "recursive_lineage_depth_exceeded" for item in gaps)


def test_single_source_wildcard_is_traced_on_demand_without_schema_expansion(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH prepared AS (
            SELECT * FROM src.client
        )
        SELECT p.id FROM prepared p;
        """,
    )
    paths = _read(out / "compact/sql_recursive_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    assert len(paths) == 1
    assert paths[0]["terminal_relation_name"] == "src.client"
    assert paths[0]["terminal_column"] == "id"
    assert paths[0]["branch_path"][0]["projection_mapping_basis"] == "wildcard_passthrough"
    assert not any(item["gap_kind"] == "intermediate_wildcard_unexpanded" for item in gaps)


def test_qualified_wildcard_is_traced_to_its_relation_with_multiple_sources(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH prepared AS (
            SELECT a.*
            FROM src.a a
            JOIN src.b b ON a.id = b.id
        )
        SELECT p.name FROM prepared p;
        """,
    )
    path = _read(out / "compact/sql_recursive_column_lineage.json")[0]

    assert path["terminal_relation_name"] == "src.a"
    assert path["terminal_column"] == "name"
    assert path["lineage_status"] == "confirmed"


def test_unqualified_wildcard_with_multiple_sources_remains_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        WITH prepared AS (
            SELECT *
            FROM src.a a
            JOIN src.b b ON a.id = b.id
        )
        SELECT p.name FROM prepared p;
        """,
    )
    path = _read(out / "compact/sql_recursive_column_lineage.json")[0]
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    assert path["lineage_status"] == "partial"
    assert path["physical_origin_status"] == "unresolved"
    assert any(item["gap_kind"] == "intermediate_wildcard_unexpanded" for item in gaps)
