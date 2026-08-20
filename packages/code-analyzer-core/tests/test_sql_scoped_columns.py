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
        repo_id="scoped_columns",
    )
    return out


def test_column_usages_are_bound_to_relation_and_semantic_role(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT
            a.id,
            CASE WHEN b.flag = 1 THEN b.value ELSE a.value END AS result,
            row_number() OVER (PARTITION BY a.id ORDER BY a.ts) AS rn
        FROM src.a a
        LEFT JOIN src.b b ON a.id = b.id
        WHERE a.active = 1
        GROUP BY a.id, a.value, b.flag, b.value, a.ts
        ORDER BY result;
        """,
    )
    usages = _read(out / "facts/facts_by_type/sql_column_usage.json")

    def find(column: str, alias: str | None, role: str):
        return next(
            item for item in usages
            if item["column_name"] == column
            and item.get("table_or_alias") == alias
            and item["usage_role"] == role
        )

    assert find("id", "a", "projection")["relation_name"] == "src.a"
    assert find("id", "a", "join")["relation_name"] == "src.a"
    assert find("id", "b", "join")["relation_name"] == "src.b"
    assert find("active", "a", "filter")["relation_name"] == "src.a"
    assert find("id", "a", "window_partition")["relation_name"] == "src.a"
    assert find("ts", "a", "window_order")["relation_name"] == "src.a"
    assert find("result", None, "order_by")["resolution_status"] == "projection_output"


def test_projection_references_only_column_usages_from_its_scope(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT c.id, upper(c.name) AS normalized_name
            FROM src.client c
        )
        SELECT p.id, p.normalized_name
        FROM prepared p;
        """,
    )
    scopes = _read(out / "compact/sql_select_scope.json")
    projections = _read(out / "compact/sql_projection.json")
    usages = _read(out / "compact/sql_column_usage.json")

    cte_scope = next(item for item in scopes if item["scope_kind"] == "cte")
    root_scope = next(item for item in scopes if item["scope_kind"] == "statement")
    cte_projections = [item for item in projections if item["scope_id"] == cte_scope["sql_select_scope_id"]]
    root_projections = [item for item in projections if item["scope_id"] == root_scope["sql_select_scope_id"]]

    assert {item["output_name"] for item in cte_projections} == {"id", "normalized_name"}
    assert {item["output_name"] for item in root_projections} == {"id", "normalized_name"}
    assert all(item["source_column_count"] == 1 for item in root_projections)

    usage_by_id = {item["sql_column_usage_id"]: item for item in usages}
    for projection in root_projections:
        linked = [usage_by_id[item] for item in projection["source_column_usage_ids"]]
        assert all(item["scope_id"] == root_scope["sql_select_scope_id"] for item in linked)
        assert all(item["relation_kind"] == "cte" for item in linked)


def test_unqualified_column_with_multiple_relations_is_ambiguous(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT id FROM src.a a JOIN src.b b ON a.id = b.id;",
    )
    usages = _read(out / "facts/facts_by_type/sql_column_usage.json")
    projection = next(
        item for item in usages
        if item["column_name"] == "id" and item["usage_role"] == "projection"
    )
    assert projection["relation_id"] is None
    assert projection["resolution_status"] == "ambiguous"
    assert projection["resolution_basis"] == "ambiguous_unqualified"


def test_unqualified_column_with_single_relation_is_resolved(tmp_path: Path) -> None:
    out = _analyze(tmp_path, "SELECT id, name FROM src.client;")
    usages = _read(out / "facts/facts_by_type/sql_column_usage.json")
    projections = [item for item in usages if item["usage_role"] == "projection"]
    assert {item["column_name"] for item in projections} == {"id", "name"}
    assert all(item["relation_name"] == "src.client" for item in projections)
    assert all(item["resolution_basis"] == "single_relation_in_scope" for item in projections)


def test_window_function_value_is_projection_not_partition_key(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT sum(a.value) OVER (
            PARTITION BY a.account_id
            ORDER BY a.event_ts
        ) AS rolling_value
        FROM src.activity a;
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    role_by_column = {
        item["column_name"]: item["usage_role"]
        for item in usages
        if item.get("table_or_alias") == "a"
    }
    assert role_by_column["value"] == "projection"
    assert role_by_column["account_id"] == "window_partition"
    assert role_by_column["event_ts"] == "window_order"


def test_projection_wildcard_is_partial_but_count_star_is_not(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT *, a.*, count(*) AS row_count FROM src.activity a;",
    )
    projections = _read(out / "compact/sql_projection.json")
    by_expression = {item["expression"]: item for item in projections}

    assert by_expression["*"]["is_wildcard"] is True
    assert by_expression["*"]["resolution_status"] == "partial"
    assert by_expression["a.*"]["is_wildcard"] is True
    assert by_expression["a.*"]["resolution_basis"] == "wildcard_requires_schema"
    count_projection = next(item for item in projections if item["output_name"] == "row_count")
    assert count_projection["is_wildcard"] is False
    assert count_projection["resolution_status"] == "resolved"


def test_lateral_view_outputs_are_generated_relations_not_physical_sources(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT participant.dateOfCalc, liability.sourceCB
        FROM src.credit_json c
        LATERAL VIEW EXPLODE(c.parsed_data.participantResults) participant_table AS participant
        LATERAL VIEW EXPLODE(participant.liabilities) liability_table AS liability;
        """,
    )
    relations = _read(out / "compact/sql_relation.json")
    usages = _read(out / "compact/sql_column_usage.json")

    physical = next(item for item in relations if item["relation_kind"] == "physical")
    assert physical["relation_name"] == "src.credit_json"
    generated = {item["relation_name"]: item for item in relations if item["relation_kind"] == "generated"}
    assert set(generated) == {"participant", "liability"}
    assert generated["participant"]["usage_role"] == "generated_source"
    assert "EXPLODE" in generated["participant"]["generator_expression"].upper()

    participant = next(item for item in usages if item["column_name"] == "dateOfCalc")
    liability = next(item for item in usages if item["column_name"] == "sourceCB")
    assert participant["relation_kind"] == "generated"
    assert participant["relation_name"] == "participant"
    assert participant["resolution_basis"] == "generated_alias"
    assert liability["relation_kind"] == "generated"
    assert liability["relation_name"] == "liability"

    # The input nested path belongs to the only physical source; generated
    # output relations must not make it artificially ambiguous.
    input_usage = next(item for item in usages if item["column_name"] == "parsed_data.participantResults")
    assert input_usage["relation_id"] == physical["sql_relation_id"]
    assert input_usage["resolution_basis"] == "alias"


def test_unqualified_lateral_output_and_physical_fields_resolve_separately(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT id, addresses, address_dirty_key
        FROM src.client
        LATERAL VIEW EXPLODE(split(addresses, ';')) addresses_view AS address_dirty_key
        WHERE address_dirty_key != 'D';
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    id_usage = next(item for item in usages if item["column_name"] == "id")
    addresses = [item for item in usages if item["column_name"] == "addresses"]
    dirty = [item for item in usages if item["column_name"] == "address_dirty_key"]

    assert id_usage["relation_name"] == "src.client"
    assert id_usage["resolution_basis"] == "single_primary_relation_in_scope"
    assert all(item["relation_name"] == "src.client" for item in addresses)
    assert all(item["relation_kind"] == "generated" for item in dirty)
    assert all(item["resolution_basis"] == "generated_alias_unqualified" for item in dirty)


def test_nested_cte_field_path_uses_leftmost_relation_alias(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH parsed_array_data AS (
            SELECT explode(cp.parsed_data.participantResults) AS pr
            FROM src.credit_json cp
        )
        SELECT pad.pr.status, pad.pr.details.category
        FROM parsed_array_data pad;
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    status = next(item for item in usages if item["column_name"] == "pr.status")
    category = next(item for item in usages if item["column_name"] == "pr.details.category")
    assert status["table_or_alias"] == "pad"
    assert status["relation_kind"] == "cte"
    assert status["resolution_status"] == "resolved"
    assert category["table_or_alias"] == "pad"
    assert category["relation_kind"] == "cte"


def test_nested_field_on_single_physical_relation_is_resolved_without_guessing_alias(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT parsed_data.participantResults.status FROM src.credit_json;",
    )
    usages = _read(out / "compact/sql_column_usage.json")
    usage = next(item for item in usages if item["usage_role"] == "projection")
    assert usage["column_name"] == "parsed_data.participantResults.status"
    assert usage["table_or_alias"] is None
    assert usage["relation_name"] == "src.credit_json"
    assert usage["resolution_basis"] == "single_primary_relation_in_scope"


def test_nested_field_without_matching_alias_remains_unresolved_with_multiple_sources(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        "SELECT payload.customer.id FROM src.a a JOIN src.b b ON a.id = b.id;",
    )
    usages = _read(out / "compact/sql_column_usage.json")
    usage = next(item for item in usages if item["column_name"] == "customer.id")
    assert usage["table_or_alias"] == "payload"
    assert usage["relation_id"] is None
    assert usage["resolution_status"] == "unresolved"
    assert usage["resolution_basis"] == "alias_unresolved"


def test_prior_direct_projection_alias_resolves_later_unqualified_usage(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT
            a.active_flag AS active_flag,
            md5(concat_ws('#', active_flag)) AS hashf
        FROM src.a a
        JOIN src.b b ON a.id = b.id;
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    qualified = next(
        item for item in usages
        if item["column_name"] == "active_flag" and item.get("table_or_alias") == "a"
    )
    reused = next(
        item for item in usages
        if item["column_name"] == "active_flag" and item.get("table_or_alias") is None
    )

    assert reused["resolution_status"] == "resolved"
    assert reused["resolution_basis"] == "prior_direct_projection_alias"
    assert reused["relation_name"] == "src.a"
    assert reused["resolution_source_column_usage_id"] == qualified["sql_column_usage_id"]
    assert reused["resolution_source_projection_id"]


def test_non_direct_projection_alias_does_not_resolve_unqualified_usage(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT
            coalesce(a.active_flag, 0) AS active_flag,
            md5(concat_ws('#', active_flag)) AS hashf
        FROM src.a a
        JOIN src.b b ON a.id = b.id;
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    reused = next(
        item for item in usages
        if item["column_name"] == "active_flag" and item.get("table_or_alias") is None
    )

    assert reused["relation_id"] is None
    assert reused["resolution_status"] == "ambiguous"
    assert reused["resolution_basis"] == "ambiguous_unqualified"


def test_later_projection_alias_does_not_resolve_earlier_unqualified_usage(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT
            md5(concat_ws('#', active_flag)) AS hashf,
            a.active_flag AS active_flag
        FROM src.a a
        JOIN src.b b ON a.id = b.id;
        """,
    )
    usages = _read(out / "compact/sql_column_usage.json")
    reused = next(
        item for item in usages
        if item["column_name"] == "active_flag" and item.get("table_or_alias") is None
    )

    assert reused["relation_id"] is None
    assert reused["resolution_status"] == "ambiguous"
    assert reused["resolution_basis"] == "ambiguous_unqualified"


def test_projection_column_usage_keeps_structured_expression_path(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        r"SELECT CAST(SPLIT(SPLIT(key, '\\.' )[0], '_')[1] AS BIGINT) AS entity_id FROM src.child;",
    )
    usages = _read(out / "compact/sql_column_usage.json")
    usage = next(
        item for item in usages
        if item["column_name"] == "key" and item["usage_role"] == "projection"
    )

    path = usage["projection_expression_path"]
    assert [item["operation"] for item in path] == [
        "regexpsplit",
        "bracket",
        "regexpsplit",
        "bracket",
        "trycast",
        "alias",
    ]
    assert path[0]["argument_role"] == "this"
    assert path[0]["secondary_expression"] in {"'\\\\.'", "'\\.'"}
    assert path[1]["index_expressions"] == ["0"]
    assert path[2]["secondary_expression"] == "'_'"
    assert path[3]["index_expressions"] == ["1"]
    assert path[4]["target_type"].upper() == "BIGINT"
    assert path[5]["output_name"] == "entity_id"
