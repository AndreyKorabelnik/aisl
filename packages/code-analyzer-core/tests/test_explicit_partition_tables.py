from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.repo_scanner import scan_files


def _scan(repo: Path) -> dict:
    return scan_database_schema(
        repo, scan_files(repo), repo_id="partition_repo", project_code="UCP", system_name="PartitionFixture"
    )


def test_explicit_schema_partition_inherits_parent_columns(tmp_path: Path) -> None:
    migration = tmp_path / "src/main/resources/db/migration/V1__partition.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        """
CREATE TABLE archive.event (
    event_id bigint not null,
    model_code integer not null,
    payload jsonb
) PARTITION BY RANGE (model_code);
CREATE TABLE archive.event_0 PARTITION OF archive.event
FOR VALUES FROM (MINVALUE) TO (1);
""",
        encoding="utf-8",
    )

    schema = _scan(tmp_path)
    child = next(t for t in schema["tables"] if t["table_name"] == "event_0")
    assert child["qualified_table_name"] == "archive.event_0"
    assert child["table_kind"] == "partition"
    assert child["partition_parent_qualified_table_name"] == "archive.event"
    assert child["partition_parent_resolution_status"] == "observed_exact"
    assert child["inherited_column_count"] == 3

    columns = [c for c in schema["columns"] if c.get("qualified_table_name") == "archive.event_0"]
    assert {c["column_name"] for c in columns} == {"event_id", "model_code", "payload"}
    assert all(c["column_origin"] == "inherited_from_partition_parent" for c in columns)
    assert schema["overview"]["counts"]["explicit_partition_tables"] == 1
    assert schema["overview"]["counts"]["inherited_partition_columns"] == 3


def test_partition_without_observed_parent_is_materialized_without_invented_columns(tmp_path: Path) -> None:
    migration = tmp_path / "src/main/resources/db/migration/V1__external_parent.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        "CREATE TABLE archive.external_0 PARTITION OF archive.external FOR VALUES IN (0);",
        encoding="utf-8",
    )

    schema = _scan(tmp_path)
    child = next(t for t in schema["tables"] if t["table_name"] == "external_0")
    assert child["partition_parent_resolution_status"] == "missing_parent_table_fact"
    assert child.get("inherited_column_count", 0) == 0
    assert not [c for c in schema["columns"] if c.get("table_name") == "external_0"]
