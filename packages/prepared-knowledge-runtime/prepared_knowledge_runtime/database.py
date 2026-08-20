from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import duckdb as _duckdb
except ModuleNotFoundError:  # contract and preflight remain importable without DuckDB
    _duckdb = None  # type: ignore[assignment]

_UNSET = object()
_DEFAULT_ERROR = (
    "DuckDB runtime is unavailable. Install the project dependency `duckdb>=1.1.0` "
    "to materialize or query a knowledge layer."
)


def require_duckdb(duckdb_module: Any = _UNSET, *, error_message: str = _DEFAULT_ERROR) -> Any:
    module = _duckdb if duckdb_module is _UNSET else duckdb_module
    if module is None:
        raise RuntimeError(error_message)
    return module


def connect_database(
    database_path: str | Path,
    *,
    read_only: bool = False,
    memory_limit: str | None = None,
    threads: int | None = None,
    preserve_insertion_order: bool | None = None,
    duckdb_module: Any = _UNSET,
    error_message: str = _DEFAULT_ERROR,
) -> Any:
    module = require_duckdb(duckdb_module, error_message=error_message)
    connection = module.connect(str(Path(database_path)), read_only=read_only)
    if memory_limit is not None:
        safe_limit = str(memory_limit).replace("'", "''")
        connection.execute(f"SET memory_limit='{safe_limit}'")
    if threads is not None:
        connection.execute(f"SET threads={max(1, int(threads))}")
    if preserve_insertion_order is not None:
        connection.execute(f"SET preserve_insertion_order={'true' if preserve_insertion_order else 'false'}")
    return connection


def initialize_schema(connection: Any, ddl: str) -> None:
    if not str(ddl or "").strip():
        raise ValueError("DDL must not be empty")
    connection.execute(ddl)
