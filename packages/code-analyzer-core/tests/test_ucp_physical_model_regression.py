from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.repo_scanner import scan_files


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_ucp_physical_model_regression_contract(tmp_path: Path) -> None:
    """Keep the four real-UCP failure modes covered by one compact fixture."""
    _write(
        tmp_path,
        "ucp-shard-db-schema/src/main/resources/db/migration/V1__entities.sql",
        """
CREATE TABLE galorealestateentity_flat_data (id bigint primary key, data jsonb);
CREATE TABLE omnimemoryindividualfacts_flat_data (id bigint primary key, data jsonb);
""",
    )
    _write(
        tmp_path,
        "ucp-shard-db-schema/src/main/resources/db/rollback/V1__entities.sql",
        """
DROP TABLE galorealestateentity_flat_data;
DROP TABLE omnimemoryindividualfacts_flat_data;
""",
    )
    _write(
        tmp_path,
        "costore-tests/costore-example-sql-entities/src/main/resources/demo.sql",
        "CREATE TABLE client (id bigint); CREATE TABLE client_phones (client_id bigint, phone text);",
    )
    _write(
        tmp_path,
        "source/shard-db-schema/src/main/resources/db/migration/V2__storage.sql",
        "CREATE TABLE partitions (id bigint); CREATE TABLE cron.job (jobid bigint);",
    )
    _write(
        tmp_path,
        "replica/src/main/resources/db/migration/V3__partitions.sql",
        """
CREATE TABLE init_key_batch (
    batch_num numeric(32),
    keys text,
    model_code numeric(4),
    task_seq_num numeric(32)
) PARTITION BY RANGE (batch_num);
CREATE TABLE init_key_batch_0 PARTITION OF init_key_batch
FOR VALUES FROM (MINVALUE) TO (1);
CREATE TABLE init_key_batch_1 PARTITION OF init_key_batch
FOR VALUES FROM (1) TO (2);
DO $$ BEGIN
  EXECUTE 'CREATE TABLE init_key_batch_' || dynamic_id || ' PARTITION OF init_key_batch';
END $$;
""",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_regression",
        project_code="UCP",
        system_name="UCPRegressionFixture",
    )

    tables = {row["table_name"]: row for row in schema["tables"]}
    assert {
        "galorealestateentity_flat_data",
        "omnimemoryindividualfacts_flat_data",
        "partitions",
        "job",
        "init_key_batch",
        "init_key_batch_0",
        "init_key_batch_1",
    } <= set(tables)
    assert "client" not in tables
    assert "client_phones" not in tables

    assert tables["galorealestateentity_flat_data"]["migration_state"] == "active"
    assert tables["omnimemoryindividualfacts_flat_data"]["migration_state"] == "active"
    assert tables["partitions"]["schema_name"] is None
    assert tables["partitions"]["schema_name_basis"] == "unresolved_unqualified_sql"
    assert tables["job"]["schema_name"] == "cron"

    partition_children = [
        row for row in schema["tables"] if row.get("table_kind") == "partition"
    ]
    assert {row["table_name"] for row in partition_children} == {
        "init_key_batch_0",
        "init_key_batch_1",
    }
    assert all(row["inherited_column_count"] == 4 for row in partition_children)
    inherited = [
        row
        for row in schema["columns"]
        if row.get("table_name") in {"init_key_batch_0", "init_key_batch_1"}
    ]
    assert len(inherited) == 8
    assert all(row["column_origin"] == "inherited_from_partition_parent" for row in inherited)
    assert all(row.get("inherited_from_column_id") for row in inherited)

    excluded_tables = {
        row.get("table_name")
        for row in schema["excluded_schema_facts"]
        if row.get("schema_fact_group") == "tables"
    }
    assert {"client", "client_phones"} <= excluded_tables
    excluded_drops = [
        row
        for row in schema["excluded_schema_changes"]
        if row.get("schema_change_kind") == "drop_table"
    ]
    assert {row["table_name"] for row in excluded_drops} == {
        "galorealestateentity_flat_data",
        "omnimemoryindividualfacts_flat_data",
    }
