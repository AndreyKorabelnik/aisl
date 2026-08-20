from __future__ import annotations

from pathlib import Path



def _make_jooq_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    table_dir = repo / "src/main/java/com/acme/db/generated/tables"
    table_dir.mkdir(parents=True)
    (table_dir / "SampleObject.java").write_text(
        '''
package com.acme.db.generated.tables;
import org.jooq.*;
import org.jooq.impl.*;
import com.acme.db.generated.Keys;
import com.acme.db.generated.Indexes;
import com.acme.db.generated.tables.records.SampleObjectRecord;
/** Sample object table */
public class SampleObject extends TableImpl<SampleObjectRecord> {
  public static final SampleObject SAMPLE_OBJECT = new SampleObject();
  public final TableField<SampleObjectRecord, Long> ID = createField(DSL.name("id"), SQLDataType.BIGINT.nullable(false), this, "Primary id");
  public final TableField<SampleObjectRecord, String> NAME = createField(DSL.name("name"), SQLDataType.VARCHAR(100), this, "Object name");
  public SampleObject() { this(DSL.name("sample_object"), null); }
  private SampleObject(Name alias, Table<SampleObjectRecord> aliased) { super(alias, null, aliased, null, DSL.comment("Sample object table"), TableOptions.table()); }
  public Schema getSchema() { return Public.PUBLIC; }
  public UniqueKey<SampleObjectRecord> getPrimaryKey() { return Keys.PK_SAMPLE_OBJECT; }
  public java.util.List<Index> getIndexes() { return java.util.Arrays.<Index>asList(Indexes.SAMPLE_OBJECT_NAME_IDX); }
}
''',
        encoding="utf-8",
    )
    gen = repo / "src/main/java/com/acme/db/generated"
    (gen / "Keys.java").write_text(
        '''
package com.acme.db.generated;
import org.jooq.*; import org.jooq.impl.*;
import com.acme.db.generated.tables.SampleObject;
public class Keys {
  public static final UniqueKey<SampleObjectRecord> PK_SAMPLE_OBJECT = UniqueKeys0.PK_SAMPLE_OBJECT;
  private static class UniqueKeys0 {
    public static final UniqueKey<SampleObjectRecord> PK_SAMPLE_OBJECT = Internal.createUniqueKey(SampleObject.SAMPLE_OBJECT, "pk_sample_object", new TableField[] { SampleObject.SAMPLE_OBJECT.ID }, true);
  }
}
''',
        encoding="utf-8",
    )
    (gen / "Indexes.java").write_text(
        '''
package com.acme.db.generated;
import org.jooq.*; import org.jooq.impl.*;
import com.acme.db.generated.tables.SampleObject;
public class Indexes {
  public static final Index SAMPLE_OBJECT_NAME_IDX = Indexes0.SAMPLE_OBJECT_NAME_IDX;
  private static class Indexes0 {
    public static Index SAMPLE_OBJECT_NAME_IDX = Internal.createIndex("sample_object_name_idx", SampleObject.SAMPLE_OBJECT, new OrderField[] { SampleObject.SAMPLE_OBJECT.NAME }, false);
  }
}
''',
        encoding="utf-8",
    )
    (repo / "schema.sql").write_text("create table sample_object (id bigint not null, name varchar(100));", encoding="utf-8")
    return repo


def test_db_schema_scanner_extracts_jooq_schema(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    repo = _make_jooq_repo(tmp_path)
    schema = scan_database_schema(
        repo,
        scan_files(repo),
        repo_id="repo_a",
        project_code="UNKNOWN",
        system_name="repo_a",
    )

    assert schema["tables"][0]["table_name"] == "sample_object"
    assert {item["column_name"] for item in schema["columns"]} == {"id", "name"}
    assert schema["indexes"][0]["index_name"] == "sample_object_name_idx"


def test_db_schema_scanner_merges_liquibase_sql_ddl_schema_evidence(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    repo = _make_jooq_repo(tmp_path)
    ddl_dir = repo / "src/main/resources/db/changelog"
    ddl_dir.mkdir(parents=True, exist_ok=True)
    (ddl_dir / "extra_schema.sql").write_text(
        """
--liquibase formatted sql
CREATE TABLE ${db.schemaName}.EXTRA_PARENT (
    ID BIGINT NOT NULL,
    CODE VARCHAR(32) NOT NULL UNIQUE,
    CONSTRAINT PK_EXTRA_PARENT PRIMARY KEY (ID)
);
COMMENT ON TABLE ${db.schemaName}.EXTRA_PARENT IS 'Extra parent table';
COMMENT ON COLUMN ${db.schemaName}.EXTRA_PARENT.CODE IS 'External code';

CREATE TABLE ${db.schemaName}.EXTRA_CHILD (
    ID BIGINT NOT NULL,
    PARENT_ID BIGINT NOT NULL,
    CONSTRAINT PK_EXTRA_CHILD PRIMARY KEY (ID),
    CONSTRAINT FK_EXTRA_CHILD_PARENT FOREIGN KEY (PARENT_ID)
        REFERENCES ${db.schemaName}.EXTRA_PARENT (ID)
);
CREATE INDEX EXTRA_CHILD_PARENT_ID_IDX ON ${db.schemaName}.EXTRA_CHILD (PARENT_ID);
""",
        encoding="utf-8",
    )

    db_schema = scan_database_schema(
        repo,
        scan_files(repo),
        repo_id="repo_a",
        project_code="PRJ",
        system_name="sample-system",
    )

    tables = {t["table_name"]: t for t in db_schema["tables"]}
    assert "sample_object" in tables
    assert tables["sample_object"]["source_type"] == "jooq_generated_table_class"
    assert tables["extra_parent"]["source_type"] == "liquibase_sql_ddl"
    assert tables["extra_parent"]["description"] == "Extra parent table"

    extra_columns = {(c["table_name"], c["column_name"]): c for c in db_schema["columns"]}
    assert extra_columns[("extra_parent", "code")]["description"] == "External code"
    assert extra_columns[("extra_child", "parent_id")]["nullable"] is False

    keys = {(k["table_name"], k["constraint_name"]): k for k in db_schema["keys"]}
    assert keys[("extra_parent", "pk_extra_parent")]["columns"] == ["id"]
    assert keys[("extra_parent", "uk_extra_parent_code")]["constraint_kind"] == "unique_key"

    rels = {r["constraint_name"]: r for r in db_schema["relationships"]}
    assert rels["fk_extra_child_parent"]["source_table"] == "extra_child"
    assert rels["fk_extra_child_parent"]["target_table"] == "extra_parent"
    assert rels["fk_extra_child_parent"]["relationship_evidence_kind"] == "declared_foreign_key"
    assert "cardinality" not in rels["fk_extra_child_parent"]
    assert "relationship_type" not in rels["fk_extra_child_parent"]
    assert "relationship_confidence" not in rels["fk_extra_child_parent"]

    indexes = {(i["table_name"], i["index_name"]): i for i in db_schema["indexes"]}
    assert indexes[("extra_child", "extra_child_parent_id_idx")]["columns"] == ["parent_id"]
    assert db_schema["overview"]["source_mix"]["tables_added_from_liquibase_sql_ddl"] >= 2


def test_liquibase_trigger_catalog_extracts_source_and_target_tables(tmp_path):
    from code_analyzer_core.scanners.repo_scanner import scan_files
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema

    sql = tmp_path / "src/main/resources/db/changelog/01.sql"
    sql.parent.mkdir(parents=True, exist_ok=True)
    sql.write_text("""
CREATE TABLE LINK (LINKID BIGINT);
CREATE TABLE LINK_HISTORY (ID BIGINT, LINK_ID BIGINT);
DO '
BEGIN
  CREATE OR REPLACE FUNCTION ${db.schemaName}.LINK_TRG_PROC() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO ${db.schemaName}.LINK_HISTORY(ID, LINK_ID) VALUES (1, NEW.LINKID);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
END';
CREATE TRIGGER LINK_TRG
    AFTER INSERT OR UPDATE OR DELETE
    ON ${db.schemaName}.LINK
    FOR EACH ROW
EXECUTE PROCEDURE ${db.schemaName}.LINK_TRG_PROC();
""", encoding="utf-8")

    schema = scan_database_schema(tmp_path, scan_files(tmp_path), repo_id="r", project_code="P", system_name="S")
    triggers = schema["triggers"]
    assert len(triggers) == 1
    trig = triggers[0]
    assert trig["trigger_name"] == "link_trg"
    assert trig["source_table"] == "link"
    assert trig["trigger_events"] == ["insert", "update", "delete"]
    assert "link_history" in trig["target_tables"]


def test_production_table_is_not_hidden_by_same_named_test_fixture(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    test_sql = tmp_path / "module-internal/src/test/resources/h2/schema.sql"
    test_sql.parent.mkdir(parents=True, exist_ok=True)
    test_sql.write_text(
        "CREATE TABLE UCP_FD.entity_task (id bigint not null, state varchar(32));",
        encoding="utf-8",
    )
    production_sql = tmp_path / "module-openshift/scripts/db/ucp/migration_fd_postgres/V1.2.7__entity_task.sql"
    production_sql.parent.mkdir(parents=True, exist_ok=True)
    production_sql.write_text(
        "CREATE TABLE entity_task (id bigint not null, payload text);",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_replica",
        project_code="UCP",
        system_name="UCPReplica",
    )

    matching = [t for t in schema["tables"] if t.get("table_name") == "entity_task"]
    assert len(matching) == 1
    production = matching[0]
    assert production["file"].endswith("V1.2.7__entity_task.sql")
    assert production["source_set"] != "test"
    assert production["has_non_test_source"] is True
    excluded_test = next(
        item for item in schema["excluded_schema_facts"]
        if item.get("schema_fact_group") == "tables" and item.get("table_name") == "entity_task"
    )
    assert excluded_test["source_scope"] == "test"
    assert excluded_test["effective_model_included"] is False
    assert {c["column_name"] for c in schema["columns"] if c.get("qualified_table_name") == production.get("qualified_table_name")} == {"id", "payload"}


def test_postgres_child_partitions_are_published_as_physical_partition_facts(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration = tmp_path / "replica-openshift/scripts/db/ucp/migration_fd_postgres/V1__partitions.sql"
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text(
        """
CREATE TABLE ${userowner}.task (
    id bigint not null,
    model_code integer not null
) PARTITION BY RANGE (model_code);

CREATE TABLE ${userowner}.task_0 PARTITION OF ${userowner}.task
FOR VALUES FROM (MINVALUE) TO (1)
TABLESPACE ${tbsTables};

CREATE TABLE task_1 PARTITION OF task
FOR VALUES FROM (1) TO (2);

DO $$
BEGIN
    EXECUTE format('CREATE TABLE task_dynamic PARTITION OF task FOR VALUES FROM (2) TO (3)');
END
$$;
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_replica",
        project_code="UCP",
        system_name="UCPReplica",
    )

    partitioning = schema["partitioning"]
    parent = [p for p in partitioning if p.get("partition_fact_kind") == "parent_partitioning"]
    children = [p for p in partitioning if p.get("partition_fact_kind") == "child_partition"]

    assert len(parent) == 1
    assert parent[0]["table_name"] == "task"
    assert parent[0]["partition_strategy"] == "range"
    assert parent[0]["partition_columns"] == ["model_code"]

    assert {p["partition_table_name"] for p in children} == {"task_0", "task_1"}
    assert "task_dynamic" not in {p["partition_table_name"] for p in children}
    task_0 = next(p for p in children if p["partition_table_name"] == "task_0")
    assert task_0["parent_table_name"] == "task"
    assert task_0["partition_bound_kind"] == "range"
    assert task_0["partition_bound_expression"].lower() == "from (minvalue) to (1)"
    assert task_0["tablespace"] == "${tbsTables}"
    assert task_0["qualified_partition_table_name"] == "task_0"
    assert task_0["parent_qualified_table_name"] == "task"
    assert task_0["partition_schema_name"] is None
    assert task_0["partition_schema_name_basis"] == "unresolved_placeholder_reference"
    assert task_0["source_set"] == "migration"
    assert task_0["evidence"][0]["kind"] == "sql_create_partition_of"
    assert "confidence" not in task_0
    assert "relationship_type" not in task_0

    # Directly declared children are physical table objects; dynamic SQL is not materialized.
    tables = {t["table_name"]: t for t in schema["tables"]}
    assert set(tables) == {"task", "task_0", "task_1"}
    assert tables["task_0"]["table_kind"] == "partition"
    assert tables["task_0"]["partition_parent_qualified_table_name"] == "task"
    assert tables["task_0"]["partition_bound_expression"].lower() == "from (minvalue) to (1)"
    assert tables["task_0"]["inherited_column_count"] == 2
    assert "task_dynamic" not in tables

    inherited = [c for c in schema["columns"] if c.get("table_name") == "task_0"]
    assert {c["column_name"] for c in inherited} == {"id", "model_code"}
    assert {c["column_origin"] for c in inherited} == {"inherited_from_partition_parent"}
    assert {c["inherited_from_qualified_table_name"] for c in inherited} == {"task"}


def test_unnamed_alter_primary_key_and_fk_without_target_columns_are_preserved(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration = tmp_path / "storage/scripts/db/migration/V1__constraints.sql"
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text(
        """
CREATE TABLE partitions (
    partition_id numeric,
    namespace varchar,
    PRIMARY KEY (partition_id, namespace)
);
CREATE TABLE shards (
    partition_id numeric,
    namespace varchar,
    shard varchar,
    PRIMARY KEY (partition_id, namespace, shard),
    FOREIGN KEY (partition_id, namespace) REFERENCES partitions
);
CREATE TABLE wal_log (
    wal_id bigint,
    wal_entry_number bigint
);
ALTER TABLE wal_log ADD PRIMARY KEY (wal_id, wal_entry_number);
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_storage",
        project_code="UCP",
        system_name="UCPDBStorage",
    )

    wal_pk = next(
        item
        for item in schema["keys"]
        if item["table_name"] == "wal_log" and item["constraint_kind"] == "primary_key"
    )
    assert wal_pk["columns"] == ["wal_id", "wal_entry_number"]
    assert wal_pk["constraint_name_basis"] == "generated_from_unnamed_declaration"
    assert wal_pk["evidence"][0]["kind"] == "sql_alter_table_add_unnamed_constraint"

    shard_fk = next(item for item in schema["relationships"] if item["source_table"] == "shards")
    assert shard_fk["source_columns"] == ["partition_id", "namespace"]
    assert shard_fk["target_table"] == "partitions"
    assert shard_fk["target_columns"] == []
    assert shard_fk["target_columns_declared"] is False
    assert shard_fk["relationship_evidence_kind"] == "declared_foreign_key"
    assert "confidence" not in shard_fk

    # ADD PRIMARY KEY must not be misread as an added column named "primary".
    assert not any(item["table_name"] == "wal_log" and item["column_name"] == "primary" for item in schema["columns"])


def test_alter_add_column_if_not_exists_uses_declared_column_name(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration = tmp_path / "storage/scripts/db/migration/V2__columns.sql"
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text(
        """
CREATE TABLE schema_storage_query (id bigint);
ALTER TABLE schema_storage_query
    ADD COLUMN IF NOT EXISTS db_column_names varchar(1024);
""",
        encoding="utf-8",
    )
    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_storage",
        project_code="UCP",
        system_name="UCPDBStorage",
    )
    names = {item["column_name"] for item in schema["columns"] if item["table_name"] == "schema_storage_query"}
    assert names == {"id", "db_column_names"}
    assert "if" not in names


def test_latest_migration_definition_is_representative_and_prior_definition_is_preserved(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration_dir = tmp_path / "replica/scripts/db/migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "V1.0.1__create.sql").write_text(
        "CREATE TABLE task (task_type varchar, parent_uid uuid);\n"
        "CREATE INDEX task_parent_uid_idx ON task (task_type, parent_uid);",
        encoding="utf-8",
    )
    (migration_dir / "V1.2.6__recreate.sql").write_text(
        "DROP INDEX task_parent_uid_idx;\n"
        "CREATE INDEX task_parent_uid_idx ON task (parent_uid);",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_replica",
        project_code="UCP",
        system_name="UCPReplica",
    )
    index = next(item for item in schema["indexes"] if item["index_name"] == "task_parent_uid_idx")
    assert index["columns"] == ["parent_uid"]
    assert index["file"].endswith("V1.2.6__recreate.sql")
    assert index["representative_source_basis"] == "latest_observed_source_order"
    definitions = [item["definition"].get("columns") for item in index["source_occurrences"]]
    assert definitions == [["task_type", "parent_uid"], ["parent_uid"]]


def test_ctas_drop_rename_replaces_table_generation_and_preserves_history(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration_dir = tmp_path / "storage/shard-db-schema/src/main/resources/sql/migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "V0.1.12__Wal_cursor.sql").write_text(
        """
CREATE TABLE wal_cursor (
    cursor_id VARCHAR(100) PRIMARY KEY,
    position NUMERIC(32),
    holder_name VARCHAR(100),
    change_date TIMESTAMP,
    entry_number NUMERIC(7) DEFAULT -1
);
""",
        encoding="utf-8",
    )
    (migration_dir / "V23.41.0__new_wal_cursors_tbl.sql").write_text(
        """
CREATE TABLE new_wal_cursor AS
    SELECT cursor_id, cursor_id AS cursor_type, position, holder_name, change_date, entry_number
    FROM wal_cursor;
DROP TABLE wal_cursor;
ALTER TABLE new_wal_cursor RENAME TO wal_cursor;
ALTER TABLE wal_cursor ADD CONSTRAINT wal_cursor_pk PRIMARY KEY (cursor_id);
ALTER TABLE wal_cursor ALTER COLUMN entry_number SET DEFAULT -1;
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_storage",
        project_code="UCP",
        system_name="UCPDBStorage",
    )

    assert {item["table_name"] for item in schema["tables"]} == {"wal_cursor"}
    assert not any(item["table_name"] == "new_wal_cursor" for item in schema["tables"])
    table = schema["tables"][0]
    assert table["migration_state"] == "active"
    assert table["table_creation_kind"] == "create_table_as_select"
    assert table["renamed_from_qualified_table_name"].endswith("new_wal_cursor")

    columns = {item["column_name"]: item for item in schema["columns"] if item["table_name"] == "wal_cursor"}
    assert set(columns) == {"cursor_id", "cursor_type", "position", "holder_name", "change_date", "entry_number"}
    assert columns["cursor_type"]["derived_source_column"] == "cursor_id"
    assert columns["cursor_type"]["sql_type"].lower() == "varchar(100)"
    assert columns["entry_number"]["default_value"] == "-1"
    assert columns["entry_number"]["sql_type"].lower() == "numeric(7)"

    pk = next(item for item in schema["keys"] if item["table_name"] == "wal_cursor")
    assert pk["constraint_name"] == "wal_cursor_pk"
    assert pk["columns"] == ["cursor_id"]

    change_kinds = [item["schema_change_kind"] for item in schema["schema_changes"]]
    assert change_kinds == ["create_table", "create_table_as_select", "drop_table", "rename_table"]
    assert any(item["table_name"] == "wal_cursor" for item in schema["historical_tables"])
    assert any(
        item.get("schema_fact_group") == "columns" and item.get("column_name") == "position"
        for item in schema["historical_schema_facts"]
    )


def test_placeholder_redeclarations_merge_into_one_active_key_and_index(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration_dir = tmp_path / "shard-db-schema/src/main/resources/sql/migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "V1__create.sql").write_text(
        """
CREATE TABLE replication_reports (
    namespace varchar(64) not null,
    entity_id varchar(64) not null,
    PRIMARY KEY (namespace, entity_id)
);
CREATE INDEX repl_rept_result_idx ON replication_reports (namespace, entity_id);
""",
        encoding="utf-8",
    )
    (migration_dir / "V2__guarded_redeclare.sql").write_text(
        """
ALTER TABLE ${userowner}.replication_reports
    ADD CONSTRAINT replication_reports_pk PRIMARY KEY (namespace, entity_id);
CREATE INDEX IF NOT EXISTS repl_rept_result_idx
    ON ${userowner}.replication_reports (namespace, entity_id);
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_db_storage",
        project_code="UCP",
        system_name="UCPDBStorage",
    )

    keys = [item for item in schema["keys"] if item.get("table_name") == "replication_reports" and item.get("constraint_kind") == "primary_key"]
    indexes = [item for item in schema["indexes"] if item.get("index_name") == "repl_rept_result_idx"]
    assert len(keys) == 1
    assert len(indexes) == 1
    assert keys[0]["qualified_table_name"] == "replication_reports"
    assert indexes[0]["qualified_table_name"] == "replication_reports"
    assert len(keys[0]["source_occurrences"]) == 2
    assert len(indexes[0]["source_occurrences"]) == 2
    assert keys[0]["placeholder_schema_references"] == ["userowner"]
    assert indexes[0]["placeholder_schema_references"] == ["userowner"]


def test_alter_add_column_splits_default_and_inline_check_constraint(tmp_path: Path) -> None:
    from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
    from code_analyzer_core.scanners.repo_scanner import scan_files

    migration = tmp_path / "shard-db-schema/src/main/resources/sql/migration/V1__flags.sql"
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text(
        """
CREATE TABLE schema_storage_indexes_default (id bigint primary key);
ALTER TABLE schema_storage_indexes_default
    ADD COLUMN is_key smallint DEFAULT 0 CHECK (is_key IN (0, 1));
ALTER TABLE schema_storage_indexes_default
    ADD COLUMN is_version smallint NOT NULL DEFAULT 0 CHECK (is_version IN (0, 1));
""",
        encoding="utf-8",
    )

    schema = scan_database_schema(
        tmp_path,
        scan_files(tmp_path),
        repo_id="ucp_db_storage",
        project_code="UCP",
        system_name="UCPDBStorage",
    )

    columns = {item["column_name"]: item for item in schema["columns"] if item.get("table_name") == "schema_storage_indexes_default"}
    assert columns["is_key"]["default_value"] == "0"
    assert columns["is_version"]["default_value"] == "0"
    checks = {tuple(item.get("columns") or []): item for item in schema["constraints"] if item.get("constraint_kind") == "check"}
    assert checks[("is_key",)]["expression"] == "is_key IN (0, 1)"
    assert checks[("is_version",)]["expression"] == "is_version IN (0, 1)"
    assert checks[("is_key",)]["literal_values"] == [
        {"value": 0, "literal_kind": "integer"},
        {"value": 1, "literal_kind": "integer"},
    ]
