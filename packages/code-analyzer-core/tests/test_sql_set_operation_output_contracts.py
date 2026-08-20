import json
from pathlib import Path

import pytest

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
        repo_id="set_contracts",
    )
    return out


def _relation(out: Path, name: str):
    return next(
        item for item in _read(out / "compact/sql_relation.json")
        if item["relation_name"] == name
    )


def _unqualified_usage(out: Path, column: str):
    return next(
        item for item in _read(out / "compact/sql_column_usage.json")
        if item["column_name"] == column and item.get("table_or_alias") is None
    )


def test_union_contract_uses_first_branch_names_and_all_branch_ordinals(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined AS (
            SELECT a.customer_id AS id, a.status AS state FROM raw.a a
            UNION ALL
            SELECT b.client_key AS customer_key, b.client_state AS status_text FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT state
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "complete"
    assert combined["output_contract_basis"] == "set_operation_ordinal"
    assert combined["output_columns"] == ["id", "state"]
    assert [item["output_columns"] for item in combined["output_contract_branches"]] == [
        ["id", "state"],
        ["customer_key", "status_text"],
    ]
    assert combined["output_contract_diagnostics"] == []

    usage = _unqualified_usage(out, "state")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "combined"
    assert usage["resolution_basis"] == "unique_complete_intermediate_output_contract"


def test_union_recursive_lineage_preserves_sources_from_every_branch(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE mart.customer AS
        WITH combined AS (
            SELECT a.customer_id AS id, a.status AS state FROM raw.a a
            UNION ALL
            SELECT b.client_key AS customer_key, b.client_state AS status_text FROM raw.b b
        )
        SELECT c.state FROM combined c;
        """,
    )

    paths = _read(out / "compact/sql_recursive_column_lineage.json")
    state_paths = [item for item in paths if item["target_column"] == "state"]
    assert {(item["terminal_relation_name"], item["terminal_column"]) for item in state_paths} == {
        ("raw.a", "status"),
        ("raw.b", "client_state"),
    }
    assert {item["branch_path"][0]["definition_branch_ordinal"] for item in state_paths} == {1, 2}


def test_set_operation_cardinality_mismatch_is_partial_with_diagnostic(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined AS (
            SELECT a.id, a.status FROM raw.a a
            UNION ALL
            SELECT b.id FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT status
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "partial"
    assert combined["output_contract_basis"] == "set_operation_cardinality_mismatch"
    assert combined["output_contract_diagnostics"] == [
        {
            "code": "set_operation_cardinality_mismatch",
            "branch_ordinal": None,
            "details": "1,2",
        }
    ]
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_incomplete_union_branch_keeps_contract_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined AS (
            SELECT a.id, a.status FROM raw.a a
            UNION ALL
            SELECT b.* FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT status
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "partial"
    assert combined["output_contract_basis"] == "set_operation_branch_incomplete"
    assert any(item["code"] == "set_operation_branch_incomplete" for item in combined["output_contract_diagnostics"])
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_explicit_cte_column_list_renames_complete_union_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined(entity_id, entity_state) AS (
            SELECT a.customer_id, a.status FROM raw.a a
            UNION ALL
            SELECT b.client_key, b.client_state FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT entity_state
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "complete"
    assert combined["output_contract_basis"] == "explicit_cte_column_list"
    assert combined["output_columns"] == ["entity_id", "entity_state"]
    assert _unqualified_usage(out, "entity_state")["relation_name"] == "combined"


@pytest.mark.parametrize("operator", ["INTERSECT", "EXCEPT"])
def test_other_set_operations_use_same_ordinal_contract(operator: str, tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        f"""
        WITH combined AS (
            SELECT a.id AS entity_id FROM raw.a a
            {operator}
            SELECT b.key AS source_key FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT entity_id
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "complete"
    assert combined["output_contract_basis"] == "set_operation_ordinal"
    assert combined["output_columns"] == ["entity_id"]
    assert _unqualified_usage(out, "entity_id")["relation_name"] == "combined"


def test_union_contract_can_seed_later_wildcard_propagation(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined AS (
            SELECT a.id, a.status FROM raw.a a
            UNION ALL
            SELECT b.key, b.state FROM raw.b b
        ), forwarded AS (
            SELECT c.* FROM combined c
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT status
        FROM forwarded f
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    forwarded = _relation(out, "forwarded")
    assert combined["output_contract_status"] == "complete"
    assert forwarded["output_contract_status"] == "complete"
    assert forwarded["output_contract_basis"] == "expanded_intermediate_wildcard"
    assert _unqualified_usage(out, "status")["relation_name"] == "forwarded"


def test_explicit_column_count_mismatch_remains_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH combined(only_one_name) AS (
            SELECT a.id, a.status FROM raw.a a
            UNION ALL
            SELECT b.key, b.state FROM raw.b b
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT only_one_name
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "partial"
    assert combined["output_contract_basis"] == "explicit_output_column_count_mismatch"
    assert any(item["code"] == "explicit_output_column_count_mismatch" for item in combined["output_contract_diagnostics"])
    assert _unqualified_usage(out, "only_one_name")["resolution_status"] == "ambiguous"
