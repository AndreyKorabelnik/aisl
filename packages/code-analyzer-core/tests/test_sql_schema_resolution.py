from __future__ import annotations

from pathlib import Path

from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.repo_scanner import scan_files


def _scan(repo: Path) -> dict:
    return scan_database_schema(
        repo,
        scan_files(repo),
        repo_id="schema_repo",
        project_code="UCP",
        system_name="SchemaFixture",
    )


def test_exact_flyway_placeholder_value_resolves_schema(tmp_path: Path) -> None:
    migration = tmp_path / "module/src/main/resources/db/migration/V1__account.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE ${userOwner}.account (id bigint);", encoding="utf-8")
    config = tmp_path / "module/flyway.conf"
    config.write_text("-placeholders.userOwner=business_schema\n", encoding="utf-8")

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "account")
    assert table["schema_name"] == "business_schema"
    assert table["qualified_table_name"] == "business_schema.account"
    assert table["schema_name_basis"] == "flyway_placeholder_exact_config"
    assert table["declared_schema_reference"] == "${userowner}"
    assert table["schema_resolution_status"] == "resolved_exact"


def test_ambiguous_placeholder_values_remain_unresolved(tmp_path: Path) -> None:
    migration = tmp_path / "module/src/main/resources/db/migration/V1__account.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE ${userOwner}.account (id bigint);", encoding="utf-8")
    (tmp_path / "one.conf").write_text("-placeholders.userOwner=schema_one\n", encoding="utf-8")
    (tmp_path / "two.conf").write_text("-placeholders.userOwner=schema_two\n", encoding="utf-8")

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "account")
    assert table["schema_name"] is None
    assert table["qualified_table_name"] == "account"
    assert table["schema_name_basis"] == "unresolved_placeholder_reference"
    assert table["schema_resolution_status"] == "ambiguous"
    assert table["schema_resolution_candidates"] == ["schema_one", "schema_two"]


def test_unique_exact_default_schema_resolves_unqualified_sql(tmp_path: Path) -> None:
    migration = tmp_path / "module/src/main/resources/db/migration/V1__event.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE event_log (id bigint);", encoding="utf-8")
    (tmp_path / "module/application.properties").write_text(
        "spring.flyway.default-schema=audit_schema\n",
        encoding="utf-8",
    )

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "event_log")
    assert table["schema_name"] == "audit_schema"
    assert table["schema_name_basis"] == "exact_default_schema_config"
    assert table["qualified_table_name"] == "audit_schema.event_log"


def test_module_directory_is_not_used_as_schema_identity(tmp_path: Path) -> None:
    migration = tmp_path / "source/shard-db-schema/src/main/resources/sql/migration/V1__table.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE partitions (id bigint);", encoding="utf-8")

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "partitions")
    assert table["module_name"] == "source"
    assert table["schema_name"] is None
    assert table["qualified_table_name"] == "partitions"
    assert table["schema_name_basis"] == "unresolved_unqualified_sql"
    assert table["schema_resolution_status"] == "unresolved"


def test_explicit_sql_schema_wins_over_default_config(tmp_path: Path) -> None:
    migration = tmp_path / "module/src/main/resources/db/migration/V1__explicit.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE cron.job (id bigint);", encoding="utf-8")
    (tmp_path / "module/flyway.properties").write_text("flyway.defaultSchema=other_schema\n", encoding="utf-8")

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "job")
    assert table["schema_name"] == "cron"
    assert table["qualified_table_name"] == "cron.job"
    assert table["schema_name_basis"] == "explicit_sql_schema"
    assert table["schema_resolution_status"] == "declared_explicit"


def test_templated_default_schema_is_observed_but_not_treated_as_exact(tmp_path: Path) -> None:
    migration = tmp_path / "module/src/main/resources/db/migration/V1__table.sql"
    migration.parent.mkdir(parents=True)
    migration.write_text("CREATE TABLE data_table (id bigint);", encoding="utf-8")
    (tmp_path / "module/flyway.conf").write_text(
        'flyway_default_schema: "{{ db.schema | default(db.user) }}"\n',
        encoding="utf-8",
    )

    schema = _scan(tmp_path)
    table = next(row for row in schema["tables"] if row["table_name"] == "data_table")
    assert table["schema_name"] is None
    observations = schema["schema_resolution_observations"]
    assert any(row["observation_kind"] == "flyway_default_schema" for row in observations)
    assert not any(row["resolved_schema_name"] for row in observations if row["observation_kind"] == "flyway_default_schema")
