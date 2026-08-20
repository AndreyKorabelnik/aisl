#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a WKL DuckDB workspace against the real ten-repository UCP physical-model gold assertions."
    )
    parser.add_argument("workspace_duckdb", type=Path)
    parser.add_argument(
        "--expectations",
        type=Path,
        default=Path(__file__).with_name("expectations.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - validation environment concern
        raise SystemExit("duckdb is required to run this validator") from exc

    expected = _load(args.expectations)
    con = duckdb.connect(str(args.workspace_duckdb), read_only=True)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected_value: Any) -> None:
        checks.append({
            "check": name,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected_value,
        })

    observed_counts = dict(
        con.execute(
            "SELECT repo_id, count(*) FROM db_schema_table GROUP BY repo_id ORDER BY repo_id"
        ).fetchall()
    )
    wanted_counts = expected["expected_table_counts_by_repository"]
    add("table_counts_by_repository", observed_counts == wanted_counts, observed_counts, wanted_counts)

    restored = expected["expected_restored_tables"]
    found_restored = [
        name
        for name in restored
        if con.execute(
            "SELECT count(*) FROM db_schema_table WHERE repo_id='ucpucp_shard_flyway' AND lower(table_name)=lower(?)",
            [name],
        ).fetchone()[0]
    ]
    add("all_restored_tables_present", len(found_restored) == len(restored), found_restored, restored)

    demo = expected["excluded_demo_tables"]
    found_demo = [
        row[0]
        for row in con.execute(
            "SELECT DISTINCT table_name FROM db_schema_table WHERE lower(table_name) IN (?, ?) ORDER BY table_name",
            demo,
        ).fetchall()
    ]
    add("demo_tables_absent", not found_demo, found_demo, [])

    forbidden = [str(value).lower() for value in expected["forbidden_schema_names"]]
    placeholders = ",".join("?" for _ in forbidden)
    found_forbidden = con.execute(
        f"SELECT repo_id, table_name, schema_name FROM db_schema_table WHERE lower(coalesce(schema_name,'')) IN ({placeholders}) ORDER BY repo_id, table_name",
        forbidden,
    ).fetchall()
    add("forbidden_schemas_absent", not found_forbidden, found_forbidden, [])

    for item in expected["required_exact_tables"]:
        observed = con.execute(
            "SELECT count(*) FROM db_schema_table WHERE repo_id=? AND schema_name=? AND table_name=?",
            [item["repository_id"], item["schema_name"], item["table_name"]],
        ).fetchone()[0]
        add(
            f"exact_table:{item['repository_id']}:{item['schema_name']}.{item['table_name']}",
            observed == 1,
            observed,
            1,
        )

    partition = expected["expected_explicit_partition_tables"]
    partition_count = con.execute(
        "SELECT count(*) FROM db_schema_table WHERE repo_id=? AND json_extract_string(payload_json,'$.table_kind')='partition'",
        [partition["repository_id"]],
    ).fetchone()[0]
    add("explicit_partition_count", partition_count == partition["count"], partition_count, partition["count"])

    bad_partition_columns = con.execute(
        """
        SELECT count(*)
        FROM db_schema_column c
        JOIN db_schema_table t ON t.db_table_occurrence_id=c.db_table_occurrence_id
        WHERE t.repo_id=?
          AND json_extract_string(t.payload_json,'$.table_kind')='partition'
          AND (
            json_extract_string(c.payload_json,'$.column_origin')<>?
            OR nullif(json_extract_string(c.payload_json,'$.inherited_from_column_id'),'') IS NULL
          )
        """,
        [partition["repository_id"], partition["required_column_origin"]],
    ).fetchone()[0]
    add("partition_column_provenance", bad_partition_columns == 0, bad_partition_columns, 0)

    con.close()
    result = {
        "schema_version": "ucp_physical_model_gold_result/v1",
        "workspace_duckdb": str(args.workspace_duckdb.resolve()),
        "expectations": str(args.expectations.resolve()),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
