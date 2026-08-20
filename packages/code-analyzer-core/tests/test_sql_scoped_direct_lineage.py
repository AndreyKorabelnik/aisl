import json
from pathlib import Path

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
        repo_id="direct_lineage",
    )
    return out


def test_ctas_builds_confirmed_direct_physical_lineage(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        SELECT
            c.id,
            upper(c.name) AS normalized_name,
            current_timestamp() AS loaded_at
        FROM src.client c;
        """,
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    by_target = {}
    for edge in edges:
        by_target.setdefault(edge["target_column"], []).append(edge)

    id_edge = by_target["id"][0]
    assert id_edge["source_relation_name"] == "src.client"
    assert id_edge["source_column"] == "id"
    assert id_edge["direct_lineage_status"] == "confirmed_direct"
    assert id_edge["physical_origin_status"] == "confirmed"

    name_edge = by_target["normalized_name"][0]
    assert name_edge["source_column"] == "name"
    assert name_edge["expression_kind"] == "normalization_or_cast"

    loaded = by_target["loaded_at"][0]
    assert loaded["source_kind"] == "expression_without_column"
    assert loaded["source_relation_name"] is None
    assert loaded["physical_origin_status"] == "not_applicable"


def test_direct_lineage_stops_at_cte_until_recursive_iteration(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT c.id FROM src.client c
        )
        CREATE TABLE mart.client AS
        SELECT p.id FROM prepared p;
        """,
    )
    edge = _read(out / "facts/facts_by_type/sql_direct_column_lineage.json")[0]
    assert edge["source_relation_name"] == "prepared"
    assert edge["source_relation_kind"] == "cte"
    assert edge["physical_origin_status"] == "intermediate_not_traced"
    assert edge["direct_lineage_status"] == "confirmed_direct"


def test_insert_without_target_columns_is_inferred_target_lineage(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client SELECT c.id FROM src.client c;",
    )
    edge = _read(out / "compact/sql_direct_column_lineage.json")[0]
    assert edge["target_column"] == "id"
    assert edge["target_mapping_status"] == "inferred"
    assert edge["direct_lineage_status"] == "inferred_target"
    assert edge["source_relation_name"] == "src.client"


def test_ambiguous_unqualified_source_creates_partial_edge_and_gap(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client AS SELECT id FROM src.a a JOIN src.b b ON a.id = b.id;",
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")
    projection_edge = next(edge for edge in edges if edge["source_usage_role"] == "projection")

    assert projection_edge["source_relation_id"] is None
    assert projection_edge["source_column"] == "id"
    assert projection_edge["direct_lineage_status"] == "partial"
    assert any(gap["gap_kind"] == "source_relation_ambiguous" for gap in gaps)


def test_wildcard_binding_creates_target_column_gap_without_false_edge(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client AS SELECT * FROM src.client;",
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    assert edges == []
    assert len(gaps) == 1
    assert gaps[0]["gap_kind"] == "target_column_unresolved"


def test_unqualified_semantic_parameter_is_not_bound_to_only_relation(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client AS SELECT c.id, $app.ctl.loading AS ctl_loading FROM src.client c;",
    )
    usages = _read(out / "compact/sql_column_usage.json")
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    parameter_usage = next(item for item in usages if item["column_name"] == "$app.ctl.loading")
    assert parameter_usage["relation_id"] is None
    assert parameter_usage["resolution_status"] == "semantic_parameter"
    assert parameter_usage["resolution_basis"] == "semantic_parameter"

    parameter_edge = next(item for item in edges if item["target_column"] == "ctl_loading")
    assert parameter_edge["source_kind"] == "semantic_parameter"
    assert parameter_edge["source_relation_name"] is None
    assert parameter_edge["source_column"] == "$app.ctl.loading"
    assert parameter_edge["physical_origin_status"] == "not_applicable"
    assert parameter_edge["direct_lineage_status"] == "confirmed_direct"
    assert not any(gap.get("source_column") == "$app.ctl.loading" for gap in gaps)


def test_multi_input_expression_emits_one_edge_per_source_column(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.client AS
        SELECT coalesce(a.value, b.value) AS effective_value
        FROM src.a a
        LEFT JOIN src.b b ON a.id = b.id;
        """,
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    target_edges = [item for item in edges if item["target_column"] == "effective_value"]

    assert {(item["source_relation_name"], item["source_column"]) for item in target_edges} == {
        ("src.a", "value"),
        ("src.b", "value"),
    }
    assert all(item["expression_kind"] == "null_defaulting" for item in target_edges)
    assert all(item["direct_lineage_status"] == "confirmed_direct" for item in target_edges)


def test_explicit_wildcard_target_creates_specific_unexpanded_gap(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id, name) SELECT * FROM src.client;",
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    assert edges == []
    assert {(item["target_column"], item["gap_kind"]) for item in gaps} == {
        ("id", "wildcard_projection_unexpanded"),
        ("name", "wildcard_projection_unexpanded"),
    }


def test_partial_target_mapping_has_localized_gap(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id) SELECT a.id, a.name FROM src.a a;",
    )
    edges = _read(out / "compact/sql_direct_column_lineage.json")
    gaps = _read(out / "compact/sql_scoped_lineage_gap.json")

    id_edge = next(item for item in edges if item["target_column"] == "id")
    assert id_edge["direct_lineage_status"] == "partial"
    assert any(
        item["target_column"] == "id" and item["gap_kind"] == "target_projection_mapping_partial"
        for item in gaps
    )
    assert any(item["gap_kind"] == "target_column_unresolved" for item in gaps)


def test_physical_template_origin_stays_logical_template(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client AS SELECT c.id FROM ${source_schema}.client c;",
    )
    edge = _read(out / "compact/sql_direct_column_lineage.json")[0]

    assert edge["source_relation_name"] == "${source_schema}.client"
    assert edge["source_relation_kind"] == "physical_template"
    assert edge["physical_origin_status"] == "logical_template"
