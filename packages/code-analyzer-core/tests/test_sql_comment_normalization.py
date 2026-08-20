from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.sql_profile import (
    _normalize_sql_for_profile,
    _strip_sql_comments_preserving_literals,
)


from tests.sql_evidence_test_support import read_sql_output, run_sql_evidence


def _read(path: Path):
    return read_sql_output(path)


def test_real_comments_are_removed_but_line_offsets_are_preserved() -> None:
    sql = "select id /* block\ncomment */ from src.client -- trailing\nwhere active = 1"
    rendered = _strip_sql_comments_preserving_literals(sql)

    assert len(rendered) == len(sql)
    assert rendered.count("\n") == sql.count("\n")
    assert "block" not in rendered
    assert "trailing" not in rendered
    assert "from src.client" in rendered
    assert "where active = 1" in rendered


def test_comment_markers_inside_literals_and_quoted_identifiers_are_preserved() -> None:
    sql = """select '--' as dash, '/* literal */' as block, "--quoted" as q, `/*name*/` as b
from src.client
where doc_full <> '--' -- real comment
  and note = 'value -- still literal'"""
    rendered = _strip_sql_comments_preserving_literals(sql)

    assert "'--' as dash" in rendered
    assert "'/* literal */' as block" in rendered
    assert '"--quoted" as q' in rendered
    assert "`/*name*/` as b" in rendered
    assert "doc_full <> '--'" in rendered
    assert "'value -- still literal'" in rendered
    assert "real comment" not in rendered


def test_dollar_quoted_text_is_not_treated_as_comment() -> None:
    sql = "select $$-- not a comment /* either */$$ as body -- actual\nfrom src.client"
    rendered = _strip_sql_comments_preserving_literals(sql)

    assert "$$-- not a comment /* either */$$" in rendered
    assert "actual" not in rendered
    assert "from src.client" in rendered


def test_normalization_keeps_literal_double_dash_parseable() -> None:
    sql = "select id from src.client where trim(doc_full) <> '--' -- comment"
    rendered, replacements = _normalize_sql_for_profile(sql)

    assert replacements == {}
    assert "trim(doc_full) <> '--'" in rendered
    assert "comment" not in rendered


def test_literal_double_dash_query_produces_scoped_relation_and_columns(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "query.sql").write_text(
        """
        WITH docs AS (
          SELECT client_id, doc_full
          FROM src.client_doc
          WHERE trim(doc_full) <> '--'
        )
        SELECT d.client_id
        FROM docs d
        JOIN src.client c ON c.client_id = d.client_id;
        """,
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="literal_comment_markers",
    )

    relations = _read(out / "facts/facts_by_type/sql_relation.json")
    assert {item["relation_name"] for item in relations if item["relation_kind"] == "physical"} == {
        "src.client_doc",
        "src.client",
    }
    usages = _read(out / "facts/facts_by_type/sql_column_usage.json")
    assert any(item["column_name"] == "doc_full" and item["usage_role"] == "filter" for item in usages)
