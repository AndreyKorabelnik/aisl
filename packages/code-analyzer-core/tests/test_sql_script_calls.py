from __future__ import annotations

from pathlib import Path

from tests.sql_evidence_test_support import read_fact, run_sql_evidence


def test_script_call_preserves_named_arguments_without_assigning_semantics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prep.sql").write_text(
        """
let prep_src_table = "stg_phone";
let query_path = "$root/${$main_table_name}/${$prep_src_table}.sql";
try runAndSaveSqlHdfs(
    queryPath=$query_path,
    queryMapping=$query_mapping,
    tableSchema=$app.stg.schema.name,
    tableName=$prep_src_table,
    orderBy="id"
);
""",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="script_calls")
    rows = read_fact(out, "sql_script_call")
    calls = [row for row in rows if str(row.get("call_symbol") or "").lower() == "runandsavesqlhdfs"]
    assert len(calls) == 1
    call = calls[0]
    assert call["named_arguments"]["queryPath"] == "$query_path"
    assert call["named_arguments"]["tableName"] == "$prep_src_table"
    assert call["named_arguments"]["tableSchema"] == "$app.stg.schema.name"
    assert call["positional_arguments"] == []
    assert set(call["referenced_placeholders"]) >= {"query_path", "prep_src_table", "app.stg.schema.name"}
    assert "material" not in str(call).lower()  # syntax fact only; no persistence semantics assigned


def test_commented_repeated_bindings_are_preserved_as_separate_occurrences(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prep.sql").write_text(
        """
-- first stage
let prep_src_table = "stg_current";
runAndSaveSqlHdfs(queryPath=$query_path, tableName=$prep_src_table);
let prep_src_table = "stg_history";
runAndSaveSqlHdfs(queryPath=$query_path, tableName=$prep_src_table);
-- final stage
let prep_src_table = "stg_business_view";
runAndSaveSqlHdfs(queryPath=$query_path, tableName=$prep_src_table);
""",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="script_binding_occurrences")
    bindings = [
        row for row in read_fact(out, "sql_script_binding")
        if row.get("binding_name") == "prep_src_table"
    ]
    assert [row.get("scalar_value") for row in bindings] == [
        "stg_current", "stg_history", "stg_business_view"
    ]
    assert len({row.get("sql_script_binding_id") for row in bindings}) == 3


def test_binding_after_unterminated_control_flow_block_is_preserved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "prep.sql").write_text(
        """
for partition in partitions loop
    try
        runAndSaveSqlHdfs(queryPath=$query_path, tableName=$prep_src_table);
    catch ex then
        log_info("failed");
    end
end loop

let prep_src_table = "stg_individual";
let query_path = "$root/${$main_table_name}/${$prep_src_table}.sql";
runAndSaveSqlHdfs(queryPath=$query_path, tableName=$prep_src_table);
""",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="control_tail_binding")
    bindings = [
        row for row in read_fact(out, "sql_script_binding")
        if row.get("binding_name") == "prep_src_table"
    ]
    assert [row.get("scalar_value") for row in bindings] == ["stg_individual"]
    assert bindings[0]["line_start"] == 10


def test_nested_call_inside_control_flow_is_preserved_as_typed_call_syntax(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        '''
let load_type = "inc";
if $load_type = 'inc' then
    historicity("$root/wf/model_historicity.json");
end if;
''',
        encoding="utf-8",
    )
    (repo / "model_historicity.json").write_text(
        '{"params":{"increment":{"tableName":"target_prestg"},"output":{"tableNameSnp":"target_stg"}}}',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="nested_call")
    calls = [
        row for row in read_fact(out, "sql_script_call")
        if str(row.get("call_symbol") or "").lower() == "historicity"
    ]
    assert len(calls) == 1
    assert calls[0]["positional_arguments"] == ['"$root/wf/model_historicity.json"']
    assert calls[0]["referenced_placeholders"] == ["root"]


def test_file_local_literal_sql_fragment_binding_expands_before_sql_analysis(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        '''
let selectExpr = "" ||
    "id, " ||
    "cast(name as string) as customer_name, " ||
    "$runtime_value as runtime_value";

INSERT INTO mart.target_stg
SELECT $selectExpr
FROM src.people;
''',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="local_sql_fragment")

    bindings = [
        row for row in read_fact(out, "sql_script_binding")
        if row.get("binding_name") == "selectExpr"
    ]
    assert len(bindings) == 1
    assert bindings[0]["scalar_value"] == (
        "id, cast(name as string) as customer_name, $runtime_value as runtime_value"
    )
    assert bindings[0].get("scalar_resolution_basis") == "file_local_literal_string_concatenation"

    projections = read_fact(out, "sql_projection")
    named = {str(row.get("output_name") or ""): row for row in projections}
    assert {"id", "customer_name", "runtime_value"} <= set(named)
    assert "$selectExpr" not in named
    assert named["customer_name"]["expression"].lower().startswith("cast(name as")

    statements = read_fact(out, "sql_statement")
    insert = next(row for row in statements if str(row.get("operation") or "").lower() == "insert")
    assert any(
        item.get("extractor") == "sql_profile_file_local_binding_resolution"
        and item.get("binding_name") == "selectExpr"
        and item.get("sql_script_binding_id") == bindings[0]["sql_script_binding_id"]
        for item in insert.get("evidence") or []
    )


def test_leading_comment_does_not_hide_observed_dsl_call(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "load.sql").write_text(
        """
-- observed platform transform
versionedJoin(
    tablesString=$joinedTables,
    outputTable="stg.target_joined"
);
""",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_sql_evidence(repo, out, repo_id="leading_comment_call")

    calls = [
        row for row in read_fact(out, "sql_script_call")
        if str(row.get("call_symbol") or "").lower() == "versionedjoin"
    ]
    assert len(calls) == 1
    assert calls[0]["named_arguments"]["tablesString"] == "$joinedTables"
    assert calls[0]["named_arguments"]["outputTable"] == '"stg.target_joined"'
