from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.sql_profile import (
    _classify_script_fragment,
    _split_sql_script_fragments,
)


from tests.sql_evidence_test_support import read_sql_output, run_sql_evidence


def _read(path: Path):
    return read_sql_output(path)


def test_mixed_dsl_file_publishes_only_top_level_sql_as_query(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        """
let source_table = 'src.client'; log_info('start');
insert into mart.client select id from src.client;
run_sql_hdfs("common/prepare.sql");
""".strip(),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    result = run_sql_evidence(
        repo,
        out,
        repo_id="mixed_sql",
    )

    queries = _read(out / "sql" / "queries.json")
    scripts = _read(out / "sql" / "script_statements.json")
    assert result["coverage"]["sql_statement_count"] == 1
    assert queries[0]["operation"] == "insert"
    assert {item["statement_kind"] for item in scripts} == {"assignment", "logging", "invocation"}
    invocation = next(item for item in scripts if item["statement_kind"] == "invocation")
    assert invocation["referenced_sql_paths"] == ["common/prepare.sql"]


def test_splitter_handles_multiple_semicolon_terminated_fragments_on_one_line() -> None:
    fragments = _split_sql_script_fragments(
        "let a = 1; let b = 'x;y'; drop table if exists tmp_table;"
    )
    assert [statement for _, statement in fragments] == [
        "let a = 1",
        "let b = 'x;y'",
        "drop table if exists tmp_table",
    ]


def test_assignment_with_nested_select_is_script_evidence_not_top_level_query(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "stats.sql").write_text(
        "let max_loading = (select max(ctl_loading) from src.control)[0][0];",
        encoding="utf-8",
    )
    out = tmp_path / "out"

    run_sql_evidence(
        repo,
        out,
        repo_id="nested_select",
    )

    assert _read(out / "sql" / "queries.json") == []
    scripts = _read(out / "sql" / "script_statements.json")
    assert len(scripts) == 1
    assert scripts[0]["statement_kind"] == "assignment"
    assert scripts[0]["contains_embedded_sql"] is True
    assert scripts[0]["embedded_sql_keywords"] == ["select"]


def test_with_query_is_classified_as_sql() -> None:
    item = _classify_script_fragment(
        "with prepared as (select id from src.client) select id from prepared"
    )
    assert item["classification"] == "sql"
    assert item["leading_token"] == "with"


def test_comments_and_semicolons_inside_strings_do_not_break_statement_boundaries() -> None:
    text = """
-- comment with ;
select 'a;b' as value from src.one;
/* comment ; */
let x = \"c;d\";
"""
    fragments = _split_sql_script_fragments(text)
    assert len(fragments) == 2
    assert fragments[0][0] == 2
    assert "select 'a;b'" in fragments[0][1]
    assert fragments[1][1].endswith('let x = "c;d"')


def test_sql_keyword_inside_logging_string_is_not_embedded_sql(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "log.sql").write_text(
        'log_info("Executing query with load_month = $load_month");',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="logging",
    )
    scripts = _read(out / "sql" / "script_statements.json")
    assert scripts[0]["contains_embedded_sql"] is False
    assert _read(out / "sql" / "script_embedded_sql.json") == []


def test_conditional_create_is_preserved_as_graph_changing_embedded_sql(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ddl.sql").write_text(
        "if $partitioned then create external table $target (id bigint);",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="dynamic_ddl",
    )
    embedded = _read(out / "sql" / "script_embedded_sql.json")
    assert len(embedded) == 1
    assert embedded[0]["sql_role"] == "schema_definition_or_change"
    assert embedded[0]["affects_logical_sql_graph"] is True
    assert embedded[0]["canonical_lineage_inclusion"] == "deferred"


def test_script_sql_path_is_resolved_by_static_suffix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "wf/dml/common/calc_stg.sql"
    target.parent.mkdir(parents=True)
    target.write_text("select id from src.client;", encoding="utf-8")
    (repo / "driver.sql").write_text(
        'run_sql_hdfs("$datamart_dir/wf/dml/common/calc_stg.sql");',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="invocation",
    )
    invocations = _read(out / "sql" / "script_invocations.json")
    assert len(invocations) == 1
    assert invocations[0]["resolution_status"] == "resolved"
    assert invocations[0]["resolved_file"] == "wf/dml/common/calc_stg.sql"
    assert invocations[0]["resolution_basis"] == "static_suffix_after_dynamic_prefix"


def test_logging_message_ending_with_sql_filename_is_not_path_reference(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "log.sql").write_text(
        'log_info("diff_mode enabled. Running prep_stg_diff_keys.sql");',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(
        repo,
        out,
        repo_id="log_path",
    )
    assert _read(out / "sql" / "script_invocations.json") == []


def test_splitter_preserves_start_line_after_previous_statement() -> None:
    fragments = _split_sql_script_fragments("let a = 1;\n\nselect id from src.client;\n")
    assert fragments == [(1, "let a = 1"), (3, "select id from src.client")]
