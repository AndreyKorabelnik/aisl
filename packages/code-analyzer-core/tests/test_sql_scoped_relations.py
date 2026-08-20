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
        repo_id="scoped",
    )
    return out


def test_cte_and_physical_relations_are_separate_scoped_facts(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT c.id FROM src.client c
        )
        INSERT INTO mart.target (id)
        SELECT p.id FROM prepared p;
        """,
    )
    scopes = _read(out / "facts/facts_by_type/sql_select_scope.json")
    relations = _read(out / "facts/facts_by_type/sql_relation.json")

    assert {item["scope_kind"] for item in scopes} == {"statement", "cte"}
    cte_scope = next(item for item in scopes if item["scope_kind"] == "cte")
    root_scope = next(item for item in scopes if item["scope_kind"] == "statement")
    assert cte_scope["scope_name"] == "prepared"

    physical = next(item for item in relations if item["relation_name"] == "src.client")
    assert physical["relation_kind"] == "physical"
    assert physical["alias"] == "c"
    assert physical["scope_id"] == cte_scope["sql_select_scope_id"]

    cte_reference = next(item for item in relations if item["relation_name"] == "prepared")
    assert cte_reference["relation_kind"] == "cte"
    assert cte_reference["alias"] == "p"
    assert cte_reference["scope_id"] == root_scope["sql_select_scope_id"]
    assert cte_reference["source_scope_ids"] == [cte_scope["sql_select_scope_id"]]
    assert cte_reference["definition_status"] == "resolved"
    assert "source_scope_id" not in cte_reference
    assert not any(item["relation_name"] == "mart.target" for item in relations)


def test_derived_relation_points_to_child_scope(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT o.id FROM (SELECT id FROM src.other) o;",
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    relations = _read(out / "compact/sql_relation.json")

    derived_scope = next(item for item in scopes if item["scope_kind"] == "derived")
    derived_relation = next(item for item in relations if item["relation_kind"] == "derived")
    source = next(item for item in relations if item["relation_name"] == "src.other")

    assert derived_relation["relation_name"] == "o"
    assert derived_relation["source_scope_ids"] == [derived_scope["sql_select_scope_id"]]
    assert derived_relation["definition_status"] == "resolved"
    assert "source_scope_id" not in derived_relation
    assert source["scope_id"] == derived_scope["sql_select_scope_id"]


def test_schema_placeholder_is_physical_template_relation(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT c.id FROM ${$source_schema}.client c;",
    )
    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    relation = next(item for item in relations if item["relation_name"] == "${$source_schema}.client")

    assert relation["relation_kind"] == "physical_template"
    assert relation["logical_name"] == "client"
    assert relation["placeholder_refs"] == ["source_schema"]


def test_relation_aliases_are_scoped_independently(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH left_side AS (SELECT x.id FROM src.one x),
             right_side AS (SELECT x.id FROM src.two x)
        SELECT l.id
        FROM left_side l
        JOIN right_side r ON l.id = r.id;
        """,
    )
    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    physical = [item for item in relations if item["relation_kind"] == "physical"]
    assert {(item["relation_name"], item["alias"], item["scope_id"]) for item in physical} == {
        ("src.one", "x", next(item["scope_id"] for item in physical if item["relation_name"] == "src.one")),
        ("src.two", "x", next(item["scope_id"] for item in physical if item["relation_name"] == "src.two")),
    }
    assert len({item["scope_id"] for item in physical}) == 2


def test_cte_union_preserves_all_definition_branches(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined AS (
            SELECT id FROM src.a
            UNION ALL
            SELECT id FROM src.b
        )
        SELECT c.id FROM combined c;
        """,
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    relations = _read(out / "compact/sql_relation.json")

    branch_ids = {
        item["sql_select_scope_id"]
        for item in scopes
        if item["scope_kind"] == "set_branch"
    }
    cte_reference = next(item for item in relations if item["relation_kind"] == "cte")
    assert set(cte_reference["source_scope_ids"]) == branch_ids
    assert len(cte_reference["source_scope_ids"]) == 2
    assert cte_reference["definition_status"] == "resolved"


def test_derived_union_preserves_all_definition_branches(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT d.id
        FROM (
            SELECT id FROM src.a
            UNION ALL
            SELECT id FROM src.b
        ) d;
        """,
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    relations = _read(out / "compact/sql_relation.json")

    branch_ids = {
        item["sql_select_scope_id"]
        for item in scopes
        if item["scope_kind"] == "set_branch"
    }
    derived = next(item for item in relations if item["relation_kind"] == "derived")
    assert set(derived["source_scope_ids"]) == branch_ids
    assert len(derived["source_scope_ids"]) == 2


def test_nested_cte_shadowing_uses_lexically_visible_definition(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH x AS (
            SELECT id FROM src.outer_source
        ), nested AS (
            WITH x AS (
                SELECT id FROM src.inner_source
            )
            SELECT id FROM x
        )
        SELECT o.id
        FROM x o
        JOIN nested n ON o.id = n.id;
        """,
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    relations = _read(out / "compact/sql_relation.json")

    cte_scopes = [item for item in scopes if item["scope_kind"] == "cte" and item["scope_name"] == "x"]
    assert len(cte_scopes) == 2
    source_scope_by_physical = {
        item["relation_name"]: item["scope_id"]
        for item in relations
        if item["relation_name"] in {"src.outer_source", "src.inner_source"}
    }
    outer_scope_id = source_scope_by_physical["src.outer_source"]
    inner_scope_id = source_scope_by_physical["src.inner_source"]
    x_references = [item for item in relations if item["relation_kind"] == "cte" and item["relation_name"] == "x"]

    assert any(item["source_scope_ids"] == [outer_scope_id] and item.get("alias") == "o" for item in x_references)
    assert any(item["source_scope_ids"] == [inner_scope_id] and item.get("alias") is None for item in x_references)


def test_unique_cte_name_fallback_resolves_when_scope_analysis_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    import code_analyzer_core.sql_profile as sql_profile

    monkeypatch.setattr(sql_profile, "traverse_scope", None)
    out = _analyze(
        tmp_path,
        "WITH prepared AS (SELECT id FROM src.client) SELECT id FROM prepared;",
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    relations = _read(out / "compact/sql_relation.json")

    cte_scope = next(item for item in scopes if item["scope_kind"] == "cte")
    cte_reference = next(item for item in relations if item["relation_kind"] == "cte")
    assert cte_reference["source_scope_ids"] == [cte_scope["sql_select_scope_id"]]
    assert cte_reference["definition_status"] == "resolved"


def test_scoped_source_coverage_reports_lexical_sources_missing_from_ast() -> None:
    from code_analyzer_core.sql_profile import _scoped_source_coverage

    coverage = _scoped_source_coverage(
        [
            {"table": "src.account"},
            {"table": "src.balance"},
            {"table": "mart.target"},
        ],
        [
            {"relation_name": "src.account", "relation_kind": "physical"},
        ],
        target="mart.target",
    )

    assert coverage == {
        "status": "partial",
        "lexical_source_candidate_count": 2,
        "scoped_source_count": 1,
        "missing_source_candidates": ["src.balance"],
    }

def test_duplicate_relation_alias_does_not_abort_repository_analysis(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT a.id FROM src.left_table a JOIN src.right_table a ON a.id = a.id;",
    )
    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    usages = _read(out / "facts/facts_by_type/sql_column_usage.json")

    assert {item["relation_name"] for item in relations} == {"src.left_table", "src.right_table"}
    assert usages
    assert all(item["resolution_status"] == "ambiguous" for item in usages)
    assert all(item["resolution_basis"] == "ambiguous_alias" for item in usages)

