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
        repo_id="write_binding",
    )
    return out


def test_explicit_insert_columns_bind_only_top_level_scope(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT c.id, upper(c.name) AS normalized_name
            FROM src.client c
        )
        INSERT INTO mart.client (client_id, client_name)
        SELECT p.id, p.normalized_name
        FROM prepared p;
        """,
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    targets = _read(out / "compact/sql_write_target.json")
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    root_scope = next(item for item in scopes if item["scope_kind"] == "statement")
    target = targets[0]
    assert target["target_relation_name"] == "mart.client"
    assert target["explicit_target_columns"] == ["client_id", "client_name"]
    assert target["source_scope_ids"] == [root_scope["sql_select_scope_id"]]
    assert target["field_mapping_status"] == "confirmed"
    assert [(item["target_column"], item["mapping_status"]) for item in bindings] == [
        ("client_id", "confirmed"),
        ("client_name", "confirmed"),
    ]
    assert all(item["source_scope_id"] == root_scope["sql_select_scope_id"] for item in bindings)


def test_insert_without_column_list_is_inferred_not_confirmed(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client SELECT c.id, upper(c.name) AS name FROM src.client c;",
    )
    target = _read(out / "facts/facts_by_type/sql_write_target.json")[0]
    bindings = _read(out / "facts/facts_by_type/sql_target_projection_binding.json")

    assert target["binding_mode"] == "projection_name_inferred"
    assert target["resolution_status"] == "partial"
    assert target["field_mapping_status"] == "inferred"
    assert [(item["target_column"], item["mapping_status"]) for item in bindings] == [
        ("id", "inferred"),
        ("name", "inferred"),
    ]


def test_ctas_projection_names_define_confirmed_target_schema(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client AS SELECT c.id, upper(c.name) AS name FROM src.client c;",
    )
    target = _read(out / "compact/sql_write_target.json")[0]
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert target["operation_kind"] == "create_table"
    assert target["binding_mode"] == "create_output_schema"
    assert target["field_mapping_status"] == "confirmed"
    assert target["evidence_maturity_level"] == "confirmed"
    assert [item["target_column"] for item in bindings] == ["id", "name"]
    assert all(item["mapping_status"] == "confirmed" for item in bindings)


def test_union_binds_every_branch_by_ordinal(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id) SELECT id FROM src.a UNION ALL SELECT id FROM src.b;",
    )
    target = _read(out / "compact/sql_write_target.json")[0]
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert len(target["source_scope_ids"]) == 2
    assert target["branch_projection_counts"] == [1, 1]
    assert [(item["branch_ordinal"], item["target_column"], item["mapping_status"]) for item in bindings] == [
        (1, "id", "confirmed"),
        (2, "id", "confirmed"),
    ]


def test_projection_count_mismatch_is_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id, name) SELECT id FROM src.a;",
    )
    target = _read(out / "compact/sql_write_target.json")[0]
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert target["count_mismatch"] is True
    assert target["field_mapping_status"] == "partial"
    assert target["resolution_status"] == "partial"
    assert bindings[0]["target_column"] == "id"
    assert bindings[0]["mapping_status"] == "partial"


def test_create_table_ddl_columns_are_not_treated_as_projection_mapping(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "CREATE TABLE mart.client (id BIGINT, name STRING);",
    )
    target = _read(out / "compact/sql_write_target.json")[0]
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert target["explicit_target_columns"] == ["id", "name"]
    assert target["source_scope_ids"] == []
    assert target["binding_mode"] == "no_select_source"
    assert target["field_mapping_status"] == "not_applicable"
    assert bindings == []


def test_missing_projection_preserves_unmapped_target_column(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id, name) SELECT id FROM src.a;",
    )
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert [(item["target_column"], item["projection_id"], item["mapping_status"]) for item in bindings] == [
        ("id", bindings[0]["projection_id"], "partial"),
        ("name", None, "partial"),
    ]
    assert bindings[0]["projection_id"] is not None


def test_explicit_columns_with_wildcard_have_unknown_arity_not_mismatch(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "INSERT INTO mart.client (id, name) SELECT * FROM src.a;",
    )
    target = _read(out / "compact/sql_write_target.json")[0]
    bindings = _read(out / "compact/sql_target_projection_binding.json")

    assert target["count_mismatch"] is False
    assert target["arity_status"] == "unknown_wildcard"
    assert target["field_mapping_status"] == "partial"
    assert [(item["target_column"], item["projection_id"], item["mapping_status"]) for item in bindings] == [
        ("id", None, "unresolved"),
        ("name", None, "unresolved"),
    ]
    assert all(item["mapping_basis"] == "explicit_columns_wildcard_unexpanded" for item in bindings)
