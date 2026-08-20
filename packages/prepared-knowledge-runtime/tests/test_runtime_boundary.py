from __future__ import annotations

from pathlib import Path

import duckdb

import prepared_knowledge_runtime
from prepared_knowledge_runtime import KnowledgeLayerQuery


def test_runtime_package_does_not_import_knowledge_layer_core() -> None:
    root = Path(prepared_knowledge_runtime.__file__).resolve().parent
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "knowledge_layer_core" not in sources


def test_query_opens_prepared_duckdb_read_only(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-layer.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("create table demo(id integer)")
        connection.execute("insert into demo values (1)")
    query = KnowledgeLayerQuery(database)
    assert "demo" in query.relation_names()
    with query._connect() as connection:
        assert connection.execute("select count(*) from demo").fetchone()[0] == 1
        try:
            connection.execute("insert into demo values (2)")
        except duckdb.InvalidInputException:
            pass
        else:
            raise AssertionError("Prepared Knowledge query connection must be read-only")


def test_explicit_database_read_does_not_require_filename_suffix(tmp_path):
    database = tmp_path / "blob"
    import duckdb
    con = duckdb.connect(str(database))
    try:
        con.execute("create table pilot(x integer)")
    finally:
        con.close()
    query = KnowledgeLayerQuery.from_database(database)
    assert query.database_path == database.resolve()
