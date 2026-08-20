from pathlib import Path

import pytest

from knowledge_layer_core import BuildStats, SchemaDefinition, bulk_insert, publish_directory_atomic, remove_path
from prepared_knowledge_runtime import connect_database, normalize_db_identifier, normalize_field_correspondence_path, read_json, require_duckdb, stable_id, write_json


def test_stable_id_and_normalization_are_deterministic():
    assert stable_id("a", 1) == stable_id("a", 1)
    assert stable_id("a", 1) != stable_id("a", 2)
    assert normalize_db_identifier('"PUBLIC".[Client]') == "public.client"
    assert normalize_field_correspondence_path("items[17]. ClientId ") == "items17.clientid"


def test_json_io_supports_default_and_round_trip(tmp_path: Path):
    missing = tmp_path / "missing.json"
    assert read_json(missing, {"default": True}) == {"default": True}
    target = tmp_path / "value.json"
    write_json(target, {"b": 2, "a": 1})
    assert read_json(target) == {"a": 1, "b": 2}


def test_duckdb_runtime_can_fail_closed_when_explicitly_missing():
    with pytest.raises(RuntimeError, match="unavailable"):
        require_duckdb(None)


def test_schema_bootstrap_and_bulk_insert(tmp_path: Path):
    database = tmp_path / "test.duckdb"
    connection = connect_database(database, memory_limit="128MB", threads=1, preserve_insertion_order=False)
    schema = SchemaDefinition(
        schema_version="test/v1",
        ddl="CREATE TABLE items (id VARCHAR, payload JSON);",
        data_tables=("items",),
    )
    schema.initialize(connection)
    bulk_insert(connection, "INSERT INTO items VALUES (?, ?)", [("a", '{"x":1}'), ("b", '{"x":2}')])
    assert connection.execute("SELECT id FROM items ORDER BY id").fetchall() == [("a",), ("b",)]
    connection.close()


def test_bulk_insert_rejects_row_width_mismatch(tmp_path: Path):
    connection = connect_database(tmp_path / "test.duckdb")
    connection.execute("CREATE TABLE items (id VARCHAR, value VARCHAR)")
    with pytest.raises(ValueError, match="width"):
        bulk_insert(connection, "INSERT INTO items VALUES (?, ?)", [("a",)])
    connection.close()


def test_build_stats_preserves_phase_order():
    stats = BuildStats("build")
    with stats.phase("one") as phase:
        phase["row_count"] = 3
    with stats.phase("two", "repo") as phase:
        phase["row_count"] = 4
    assert [row[1] for row in stats.rows] == [1, 2]
    assert [row[2] for row in stats.rows] == ["one", "two"]
    assert [row[6] for row in stats.rows] == [3, 4]


def test_atomic_publication_preserves_previous_output_on_failure_free_replace(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "value.txt").write_text("old", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "value.txt").write_text("new", encoding="utf-8")
    publish_directory_atomic(staging, output, replace=True, existing_label="workspace output")
    assert (output / "value.txt").read_text(encoding="utf-8") == "new"
    assert not staging.exists()


def test_atomic_publication_rejects_existing_output_without_replace(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(FileExistsError, match="workspace output already exists"):
        publish_directory_atomic(staging, output, replace=False, existing_label="workspace output")


def test_remove_path_handles_directory_and_missing_path(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "x").write_text("x", encoding="utf-8")
    remove_path(target)
    assert not target.exists()
    remove_path(target)

