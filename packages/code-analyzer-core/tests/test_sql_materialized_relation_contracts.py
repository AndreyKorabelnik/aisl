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
        repo_id="materialized_contracts",
    )
    return out


def _relation(out: Path, name: str):
    return next(
        item for item in _read(out / "compact/sql_relation.json")
        if item["relation_name"] == name
    )


def _target(out: Path, operation: str, name: str):
    return next(
        item for item in _read(out / "compact/sql_write_target.json")
        if item["operation_kind"] == operation
        and item.get("resolved_target_relation_name") == name
    )


def _unqualified_usage(out: Path, column: str):
    return next(
        item for item in _read(out / "compact/sql_column_usage.json")
        if item["column_name"] == column and item.get("table_or_alias") is None
    )


def test_create_like_contract_propagates_through_later_wildcard_cte(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.customer_template (customer_id BIGINT, status STRING);
        let base_name = 'prepared_customer';
        let stage_name = '${$base_name}_stage';
        CREATE TABLE local.${$stage_name} LIKE local.customer_template;
        INSERT INTO local.${$stage_name}
        SELECT src.customer_id, src.status FROM raw.customer src;

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    target = _target(out, "create_table", "local.prepared_customer_stage")
    assert target["target_name_resolution_basis"] == "file_local_script_bindings"
    assert target["materialized_output_columns"] == ["customer_id", "status"]
    assert target["materialized_output_contract_status"] == "complete"
    assert target["materialized_output_contract_basis"] == "create_table_like_complete_relation"

    physical = _relation(out, "local.prepared_customer_stage")
    assert physical["output_columns"] == ["customer_id", "status"]
    assert physical["output_contract_status"] == "complete"
    assert physical["output_contract_basis"] == "repository_write_target_contract"

    forwarded = _relation(out, "forwarded")
    assert forwarded["output_columns"] == ["customer_id", "status"]
    assert forwarded["output_contract_status"] == "complete"
    assert forwarded["output_contract_basis"] == "expanded_repository_materialized_wildcard"

    usage = _unqualified_usage(out, "status")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "forwarded"
    assert usage["resolution_basis"] == "unique_complete_relation_output_contract"


def test_plain_insert_is_observed_write_not_complete_physical_schema(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        INSERT INTO local.prepared_customer_stage (customer_id, status)
        SELECT src.customer_id, src.status FROM raw.customer src;

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    target = _target(out, "insert", "local.prepared_customer_stage")
    assert target["observed_write_columns"] == ["customer_id", "status"]
    assert target["materialized_output_contract_status"] == "observed_write_only"
    assert _relation(out, "local.prepared_customer_stage")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_unresolved_create_target_placeholder_does_not_publish_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.customer_template (customer_id BIGINT, status STRING);
        CREATE TABLE local.${$unknown_target} LIKE local.customer_template;

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    unresolved = next(
        item for item in _read(out / "compact/sql_write_target.json")
        if item["target_relation_name"] == "local.${$unknown_target}"
    )
    assert unresolved["resolved_target_relation_name"] is None
    assert unresolved["materialized_output_contract_status"] == "unavailable"
    assert _relation(out, "local.prepared_customer_stage")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_conflicting_ddl_definitions_do_not_define_physical_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.prepared_customer_stage (customer_id BIGINT, status STRING);
        CREATE TABLE local.prepared_customer_stage (customer_id BIGINT, segment STRING);

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    targets = _read(out / "compact/sql_write_target.json")
    assert {item["materialized_output_contract_status"] for item in targets} == {"conflict"}
    assert _relation(out, "local.prepared_customer_stage")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_incomplete_ctas_wildcard_does_not_define_materialized_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.prepared_customer_stage AS SELECT p.* FROM raw.customer p;

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    target = _target(out, "create_table", "local.prepared_customer_stage")
    assert target["materialized_output_contract_status"] == "unavailable"
    assert _relation(out, "local.prepared_customer_stage")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_similar_but_nonidentical_read_name_is_not_enriched(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.prepared_customer_stage (customer_id BIGINT, status STRING);

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage_v2 s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    assert _relation(out, "local.prepared_customer_stage_v2")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"



def test_partition_columns_are_part_of_explicit_ddl_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.customer_template (customer_id BIGINT)
        PARTITIONED BY (batch_date STRING);
        CREATE TABLE local.prepared_customer_stage LIKE local.customer_template;

        WITH other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT batch_date
        FROM local.prepared_customer_stage s
        CROSS JOIN other o;
        """,
    )

    physical = _relation(out, "local.prepared_customer_stage")
    assert physical["output_columns"] == ["customer_id", "batch_date"]
    usage = _unqualified_usage(out, "batch_date")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "local.prepared_customer_stage"
    assert usage["resolution_contract_basis"] == "repository_write_target_contract"

def test_binding_declared_after_create_target_is_not_used_retroactively(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.customer_template (customer_id BIGINT, status STRING);
        CREATE TABLE local.${$stage_name} LIKE local.customer_template;
        let stage_name = 'prepared_customer_stage';

        WITH forwarded AS (
          SELECT s.* FROM local.prepared_customer_stage s
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT status FROM forwarded f CROSS JOIN other o;
        """,
    )

    unresolved = next(
        item for item in _read(out / "compact/sql_write_target.json")
        if item["target_relation_name"] == "local.${$stage_name}"
    )
    assert unresolved["resolved_target_relation_name"] is None
    assert _relation(out, "local.prepared_customer_stage")["output_contract_status"] == "not_applicable"
    assert _unqualified_usage(out, "status")["resolution_status"] == "ambiguous"


def test_partition_columns_are_part_of_explicit_ddl_contract(tmp_path: Path) -> None:
    out = _analyze(
        tmp_path,
        """
        CREATE TABLE local.event_stage (event_id BIGINT)
        PARTITIONED BY (business_dt DATE);

        WITH forwarded AS (
          SELECT e.* FROM local.event_stage e
        ), other AS (
          SELECT a.account_id FROM raw.account a
        )
        SELECT business_dt FROM forwarded f CROSS JOIN other o;
        """,
    )

    target = _target(out, "create_table", "local.event_stage")
    assert target["materialized_output_columns"] == ["event_id", "business_dt"]
    assert target["materialized_output_contract_status"] == "complete"
    assert target["materialized_output_contract_basis"] == "explicit_ddl_columns"

    physical = _relation(out, "local.event_stage")
    assert physical["output_columns"] == ["event_id", "business_dt"]
    assert physical["output_contract_status"] == "complete"

    forwarded = _relation(out, "forwarded")
    assert forwarded["output_columns"] == ["event_id", "business_dt"]
    assert forwarded["output_contract_status"] == "complete"

    usage = _unqualified_usage(out, "business_dt")
    assert usage["resolution_status"] == "resolved"
    assert usage["relation_name"] == "forwarded"
