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
        repo_id="intermediate_contracts",
    )
    return out


def _unqualified_usage(out: Path, column: str):
    usages = _read(out / "compact/sql_column_usage.json")
    return next(
        item for item in usages
        if item["column_name"] == column and item.get("table_or_alias") is None
    )


def test_unique_complete_cte_output_contract_resolves_unqualified_column(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH customer_contract AS (
            SELECT c.customer_id, upper(c.status) AS normalized_status
            FROM raw.customer c
        ), account_contract AS (
            SELECT a.account_id, a.balance
            FROM raw.account a
        )
        SELECT normalized_status
        FROM customer_contract c
        CROSS JOIN account_contract a;
        """,
    )

    usage = _unqualified_usage(out, "normalized_status")
    assert usage["resolution_status"] == "resolved"
    assert usage["resolution_basis"] == "unique_complete_intermediate_output_contract"
    assert usage["relation_name"] == "customer_contract"
    assert usage["resolution_contract_status"] == "complete"
    assert usage["resolution_contract_basis"] == "explicit_select_projections"

    relations = _read(out / "compact/sql_relation.json")
    customer = next(item for item in relations if item["relation_name"] == "customer_contract")
    assert customer["output_contract_status"] == "complete"
    assert customer["output_columns"] == ["customer_id", "normalized_status"]


def test_same_column_in_two_complete_cte_contracts_remains_ambiguous(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH left_contract AS (
            SELECT l.id, l.status FROM raw.left_source l
        ), right_contract AS (
            SELECT r.id, r.status FROM raw.right_source r
        )
        SELECT status
        FROM left_contract l
        JOIN right_contract r ON l.id = r.id;
        """,
    )

    usage = _unqualified_usage(out, "status")
    assert usage["relation_id"] is None
    assert usage["resolution_status"] == "ambiguous"
    assert usage["resolution_basis"] == "ambiguous_intermediate_output_contract"


def test_cte_contract_does_not_exclude_unknown_physical_table_schema(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT s.id, s.status FROM raw.source s
        )
        SELECT status
        FROM prepared p
        JOIN external.dictionary d ON p.id = d.id;
        """,
    )

    usage = _unqualified_usage(out, "status")
    assert usage["relation_id"] is None
    assert usage["resolution_status"] == "ambiguous"
    assert usage["resolution_basis"] == "ambiguous_unqualified"


def test_wildcard_makes_cte_contract_partial_and_prevents_resolution(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH prepared AS (
            SELECT s.*, s.status AS normalized_status FROM raw.source s
        ), other AS (
            SELECT o.id FROM raw.other o
        )
        SELECT normalized_status
        FROM prepared p
        CROSS JOIN other o;
        """,
    )

    usage = _unqualified_usage(out, "normalized_status")
    assert usage["relation_id"] is None
    assert usage["resolution_basis"] == "ambiguous_unqualified"

    relations = _read(out / "compact/sql_relation.json")
    prepared = next(item for item in relations if item["relation_name"] == "prepared")
    assert prepared["output_contract_status"] == "partial"
    assert prepared["output_columns"] == ["normalized_status"]


def test_explicit_cte_column_list_defines_external_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH renamed(customer_key, customer_state) AS (
            SELECT s.id, s.status FROM raw.source s
        ), other(other_key) AS (
            SELECT o.id FROM raw.other o
        )
        SELECT customer_state
        FROM renamed r
        CROSS JOIN other o;
        """,
    )

    usage = _unqualified_usage(out, "customer_state")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "renamed"
    assert usage["resolution_contract_basis"] == "explicit_cte_column_list"

    relations = _read(out / "compact/sql_relation.json")
    renamed = next(item for item in relations if item["relation_name"] == "renamed")
    assert renamed["output_columns"] == ["customer_key", "customer_state"]
    assert renamed["output_contract_status"] == "complete"


def test_complete_derived_contract_uses_same_universal_resolution_rule(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        SELECT normalized_name
        FROM (
            SELECT upper(c.name) AS normalized_name
            FROM raw.customer c
        ) customer_view
        CROSS JOIN (
            SELECT a.account_id
            FROM raw.account a
        ) account_view;
        """,
    )

    usage = _unqualified_usage(out, "normalized_name")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_kind"] == "derived"
    assert usage["relation_name"] == "customer_view"
    assert usage["resolution_basis"] == "unique_complete_intermediate_output_contract"


def test_duplicate_cte_output_names_make_contract_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH duplicated AS (
            SELECT l.status, r.status
            FROM raw.left_source l
            JOIN raw.right_source r ON l.id = r.id
        ), other AS (
            SELECT o.id FROM raw.other o
        )
        SELECT status
        FROM duplicated d
        CROSS JOIN other o;
        """,
    )

    usage = _unqualified_usage(out, "status")
    assert usage["relation_id"] is None
    assert usage["resolution_basis"] == "ambiguous_unqualified"

    relations = _read(out / "compact/sql_relation.json")
    duplicated = next(item for item in relations if item["relation_name"] == "duplicated")
    assert duplicated["output_contract_status"] == "partial"
