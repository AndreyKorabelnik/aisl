from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any


def bulk_insert(
    connection: Any,
    sql: str,
    rows: list[tuple[Any, ...]],
    batch_size: int = 1000,
) -> None:
    if not rows:
        return
    match = re.search(r"INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
    if not match:
        raise ValueError(f"cannot resolve target table from bulk insert SQL: {sql}")
    table = match.group(1)
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()]
    if len(columns) != len(rows[0]):
        raise ValueError(f"bulk row width mismatch for {table}: columns={len(columns)} row={len(rows[0])}")
    fd, raw_path = tempfile.mkstemp(prefix=f"wkl_{table}_", suffix=".jsonl")
    path = Path(raw_path)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            for row in rows:
                handle.write(json.dumps(dict(zip(columns, row)), ensure_ascii=False, default=str, separators=(",", ":")))
                handle.write("\n")
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        connection.execute(
            f"INSERT INTO {table} ({quoted_columns}) SELECT {quoted_columns} FROM read_json_auto(?, format='newline_delimited')",
            [str(path)],
        )
    finally:
        path.unlink(missing_ok=True)
