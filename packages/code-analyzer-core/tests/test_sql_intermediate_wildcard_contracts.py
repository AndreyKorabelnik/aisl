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
        repo_id="wildcard_contracts",
    )
    return out


def _usage(out: Path, column: str):
    return next(
        item for item in _read(out / "compact/sql_column_usage.json")
        if item["column_name"] == column and item.get("table_or_alias") is None
    )


def _relation(out: Path, name: str):
    return next(
        item for item in _read(out / "compact/sql_relation.json")
        if item["relation_name"] == name
    )


def test_qualified_wildcard_propagates_complete_cte_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH base AS (
            SELECT c.customer_id, c.status FROM raw.customer c
        ), forwarded AS (
            SELECT b.* FROM base b
        ), other AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT status
        FROM forwarded f
        CROSS JOIN other o;
        """,
    )

    forwarded = _relation(out, "forwarded")
    assert forwarded["output_contract_status"] == "complete"
    assert forwarded["output_contract_basis"] == "expanded_intermediate_wildcard"
    assert forwarded["output_columns"] == ["customer_id", "status"]
    assert forwarded["output_contract_wildcard_provenance"][0]["source_relation_name"] == "base"

    usage = _usage(out, "status")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "forwarded"
    assert usage["resolution_basis"] == "unique_complete_intermediate_output_contract"


def test_single_source_unqualified_wildcard_propagates_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH base AS (
            SELECT c.customer_id, c.status FROM raw.customer c
        ), forwarded AS (
            SELECT * FROM base
        ), other AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT status
        FROM forwarded f
        CROSS JOIN other o;
        """,
    )

    forwarded = _relation(out, "forwarded")
    assert forwarded["output_contract_status"] == "complete"
    assert forwarded["output_columns"] == ["customer_id", "status"]
    assert _usage(out, "status")["relation_name"] == "forwarded"


def test_wildcard_contract_propagates_through_multiple_cte_levels(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH base AS (
            SELECT c.customer_id, c.status FROM raw.customer c
        ), middle AS (
            SELECT b.* FROM base b
        ), final_view AS (
            SELECT m.* FROM middle m
        ), other AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT status
        FROM final_view f
        CROSS JOIN other o;
        """,
    )

    assert _relation(out, "middle")["output_contract_status"] == "complete"
    assert _relation(out, "final_view")["output_contract_status"] == "complete"
    assert _usage(out, "status")["relation_name"] == "final_view"


def test_physical_wildcard_remains_partial_without_external_schema(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH unknown_contract AS (
            SELECT p.* FROM raw.customer p
        ), known_contract AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT account_id
        FROM unknown_contract u
        CROSS JOIN known_contract k;
        """,
    )

    unknown = _relation(out, "unknown_contract")
    assert unknown["output_contract_status"] == "partial"
    assert unknown["output_contract_wildcard_provenance"][0]["resolution_basis"] == "source_output_contract_incomplete"

    usage = _usage(out, "account_id")
    assert usage["relation_id"] is None
    assert usage["resolution_basis"] == "ambiguous_unqualified"


def test_unqualified_wildcard_over_multiple_relations_remains_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH left_contract AS (
            SELECT l.left_id FROM raw.left_source l
        ), right_contract AS (
            SELECT r.right_id FROM raw.right_source r
        ), combined AS (
            SELECT *
            FROM left_contract l
            CROSS JOIN right_contract r
        ), other AS (
            SELECT o.other_id FROM raw.other o
        )
        SELECT left_id
        FROM combined c
        CROSS JOIN other o;
        """,
    )

    combined = _relation(out, "combined")
    assert combined["output_contract_status"] == "partial"
    assert combined["output_contract_wildcard_provenance"][0]["resolution_basis"] == "wildcard_source_not_unique"
    assert _usage(out, "left_id")["resolution_status"] == "ambiguous"


def test_wildcard_and_explicit_duplicate_output_name_remain_partial(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH base AS (
            SELECT c.customer_id, c.status FROM raw.customer c
        ), duplicated AS (
            SELECT b.*, b.status AS status FROM base b
        ), other AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT status
        FROM duplicated d
        CROSS JOIN other o;
        """,
    )

    duplicated = _relation(out, "duplicated")
    assert duplicated["output_contract_status"] == "partial"
    assert _usage(out, "status")["resolution_status"] == "ambiguous"


def test_explicit_cte_column_list_does_not_make_unknown_physical_wildcard_complete(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH renamed(customer_value) AS (
            SELECT * FROM raw.customer
        ), other(other_id) AS (
            SELECT o.id FROM raw.other o
        )
        SELECT customer_value
        FROM renamed r
        CROSS JOIN other o;
        """,
    )

    renamed = _relation(out, "renamed")
    assert renamed["output_contract_status"] == "partial"
    assert _usage(out, "customer_value")["resolution_status"] == "ambiguous"


def test_derived_wildcard_uses_same_contract_provenance(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        WITH base AS (
            SELECT c.customer_id, c.status FROM raw.customer c
        ), other AS (
            SELECT a.account_id FROM raw.account a
        )
        SELECT status
        FROM (
            SELECT b.* FROM base b
        ) forwarded
        CROSS JOIN other o;
        """,
    )

    forwarded = _relation(out, "forwarded")
    assert forwarded["relation_kind"] == "derived"
    assert forwarded["output_contract_status"] == "complete"
    assert _usage(out, "status")["relation_name"] == "forwarded"
