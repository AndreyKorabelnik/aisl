from __future__ import annotations

import json
from pathlib import Path

from tests.sql_evidence_test_support import read_fact, read_sql_output, run_sql_evidence


def _read(path: Path):
    return read_sql_output(path)


def test_schema_placeholder_identity_is_preserved_without_blocking_lineage(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        "insert into ${$target_schema}.mart_client select s.id from ${$source_schema}.client s;",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="placeholder_schema",
    )

    statements = read_fact(out, "sql_statement")
    assert statements[0]["target_relation_name"] == "${$target_schema}.mart_client"
    relations = read_fact(out, "sql_relation")
    assert [item["relation_name"] for item in relations] == ["${$source_schema}.client"]

    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    assert {item["placeholder"] for item in placeholders} == {"source_schema", "target_schema"}
    assert all(item["resolution_status"] == "logical_template" for item in placeholders)
    assert all(item["usage_roles"] == ["relation_schema"] for item in placeholders)

    assert read_fact(out, "sql_scoped_lineage_gap") == []
    lineage = read_fact(out, "sql_recursive_column_lineage")
    assert any(item["target_relation_name"] == "${$target_schema}.mart_client" for item in lineage)


def test_whole_relation_placeholder_is_explicitly_unbound_and_partial_lineage_is_retained(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        "insert into mart_client select s.id from ${source_table} s;",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="dynamic_relation",
    )

    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    assert placeholders[0]["resolution_status"] == "unbound_semantic"
    assert placeholders[0]["usage_roles"] == ["source_relation"]
    assert read_fact(out, "sql_scoped_lineage_gap") == []
    lineage = read_fact(out, "sql_recursive_column_lineage")
    assert lineage
    assert lineage[0]["evidence_maturity_level"] == "unresolved"
    assert lineage[0]["physical_origin_status"] == "logical_template"


def test_simple_local_let_binding_is_published_and_linked_to_placeholder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        "let source_table = 'src.client';\nselect id from ${source_table};",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="local_binding",
    )

    bindings = _read(out / "sql/script_bindings.json")
    assert len(bindings) == 1
    assert bindings[0]["binding_name"] == "source_table"
    assert bindings[0]["binding_kind"] == "literal"
    assert bindings[0]["scalar_value"] == "src.client"

    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    assert placeholders[0]["resolution_status"] == "locally_bound"
    assert placeholders[0]["resolved_variants"] == ["src.client"]
    assert placeholders[0]["binding_ids"] == [bindings[0]["sql_script_binding_id"]]


def test_source_usage_describes_logical_template_relation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "query.sql").write_text(
        "select c.id from ${$source_schema}.client c;",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="template_relation",
    )

    relations = read_fact(out, "sql_relation")
    source = relations[0]
    assert source["relation_name"] == "${$source_schema}.client"
    assert source["relation_kind"] == "physical_template"
    assert source["logical_name"] == "client"
    assert source["placeholder_refs"] == ["source_schema"]


def test_select_prefix_hint_placeholder_does_not_truncate_following_query(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "query.sql").write_text(
        """
        WITH source_rows AS (
          SELECT
            ${broadcast_hint}
            a.id,
            b.status
          FROM src.account a
          LEFT JOIN src.balance b ON b.account_id = a.id
          LEFT JOIN src.segment s ON s.segment_id = b.segment_id
        )
        SELECT id, status FROM source_rows;
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="select_hint_placeholder",
    )

    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    assert {
        item["relation_name"]
        for item in relations
        if item["relation_kind"] == "physical"
    } == {"src.account", "src.balance", "src.segment"}

    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    placeholder = next(item for item in placeholders if item["placeholder"] == "broadcast_hint")
    assert placeholder["usage_roles"] == ["select_modifier_or_projection_fragment"]
    assert placeholder["resolution_status"] == "unbound_semantic"


def test_whole_select_list_placeholder_remains_parser_safe(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "query.sql").write_text(
        "SELECT ${selected_columns} FROM src.account;",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="select_list_placeholder",
    )

    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    assert any(item["relation_name"] == "src.account" for item in relations)
    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    assert placeholders[0]["placeholder"] == "selected_columns"


def test_standalone_relation_suffix_fragment_does_not_truncate_cte_graph(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "query.sql").write_text(
        """
        WITH pre_u AS (
          SELECT
            ${broadcast_hint}
            u.*,
            row_number() OVER (PARTITION BY id ORDER BY version DESC) AS rn
          FROM src.education_union u
          ${diff_filter}
        ), enriched AS (
          SELECT pre_u.*, d.code AS education_cd, d.name AS education_name
          FROM pre_u
          LEFT JOIN src.education_type d ON d.key = pre_u.education_ref
          WHERE pre_u.rn = 1
        )
        SELECT id, education_cd, education_name FROM enriched;
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="standalone_relation_fragment")

    scopes = _read(out / "facts/facts_by_type/sql_select_scope.json")
    assert len(scopes) == 3
    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    assert {item["relation_name"] for item in relations if item["relation_kind"] == "physical"} == {
        "src.education_union",
        "src.education_type",
    }
    projections = _read(out / "facts/facts_by_type/sql_projection.json")
    assert any(item["output_name"] == "education_name" for item in projections)
    placeholders = _read(out / "facts/facts_by_type/sql_semantic_placeholder.json")
    assert {item["placeholder"] for item in placeholders} >= {"broadcast_hint", "diff_filter"}


def test_local_concatenated_select_fragment_is_resolved_before_sql_structure_extraction(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        """
        let selectExpr = "" ||
            "customer_id, " ||
            "upper(customer_name) as customer_name_upper";
        INSERT INTO mart.customer
        SELECT $selectExpr
        FROM raw.customer;
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="local_select_fragment")

    bindings = read_fact(out, "sql_script_binding")
    select_binding = next(item for item in bindings if item["binding_name"] == "selectExpr")
    assert select_binding["scalar_value"] == "customer_id, upper(customer_name) as customer_name_upper"
    assert select_binding["scalar_resolution_basis"] == "file_local_literal_string_concatenation"

    projections = read_fact(out, "sql_projection")
    root_outputs = {
        item["output_name"]
        for item in projections
        if item.get("output_name")
    }
    assert {"customer_id", "customer_name_upper"} <= root_outputs
    assert "$selectExpr" not in root_outputs

    lineage = read_fact(out, "sql_recursive_column_lineage")
    assert any(
        item.get("target_column") == "customer_name_upper"
        and item.get("terminal_column") == "customer_name"
        for item in lineage
    )
