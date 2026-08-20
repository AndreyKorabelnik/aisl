from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.repo_scanner import scan_files


def _scan(repo: Path) -> dict:
    return scan_database_schema(
        repo,
        scan_files(repo),
        repo_id="scope_repo",
        project_code="UCP",
        system_name="ScopeFixture",
    )


def test_rollback_observations_do_not_mutate_forward_migration_state(tmp_path: Path) -> None:
    forward = tmp_path / "schema/src/main/resources/db/migration/V1__create.sql"
    forward.parent.mkdir(parents=True)
    forward.write_text(
        "CREATE TABLE active_table (id bigint primary key, payload text);",
        encoding="utf-8",
    )
    rollback = tmp_path / "schema/src/main/resources/db/rollback/V1__create.sql"
    rollback.parent.mkdir(parents=True)
    rollback.write_text("DROP TABLE active_table;", encoding="utf-8")

    schema = _scan(tmp_path)

    assert {row["table_name"] for row in schema["tables"]} == {"active_table"}
    assert schema["tables"][0]["source_scope"] == "forward_migration"
    assert schema["tables"][0]["effective_model_included"] is True
    excluded = schema["excluded_schema_changes"]
    assert len(excluded) == 1
    assert excluded[0]["schema_change_kind"] == "drop_table"
    assert excluded[0]["source_scope"] == "rollback"
    assert excluded[0]["effective_model_included"] is False
    assert excluded[0]["effective_model_exclusion_basis"] == "source_scope:rollback"


def test_test_demo_manual_and_fixture_tables_remain_observable_but_not_effective(tmp_path: Path) -> None:
    files = {
        "module/src/test/resources/schema.sql": "CREATE TABLE test_only (id bigint);",
        "costore-tests/costore-example-sql-entities/src/main/resources/demo.sql": "CREATE TABLE demo_only (id bigint);",
        "module/src/main/resources/db/manual/manual.sql": "CREATE TABLE manual_only (id bigint);",
        "module/src/main/resources/fixtures/fixture.sql": "CREATE TABLE fixture_only (id bigint);",
        "module/src/main/resources/db/migration/V1__prod.sql": "CREATE TABLE prod_table (id bigint);",
    }
    for rel, sql in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sql, encoding="utf-8")

    schema = _scan(tmp_path)

    assert {row["table_name"] for row in schema["tables"]} == {"prod_table"}
    excluded_tables = {
        row["table_name"]: row
        for row in schema["excluded_schema_facts"]
        if row.get("schema_fact_group") == "tables"
    }
    assert set(excluded_tables) == {"test_only", "demo_only", "manual_only", "fixture_only"}
    assert excluded_tables["test_only"]["source_scope"] == "test"
    assert excluded_tables["demo_only"]["source_scope"] == "test"  # test module marker is the strongest path fact
    assert excluded_tables["manual_only"]["source_scope"] == "manual"
    assert excluded_tables["fixture_only"]["source_scope"] == "fixture"
    assert all(row["effective_model_included"] is False for row in excluded_tables.values())
    summary = schema["sql_source_scope_summary"]
    assert summary["excluded_schema_fact_count"] >= 8  # table + column observations
    assert summary["counts_by_source_scope"]["forward_migration"] >= 2
