from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from prepared_knowledge_runtime.io import write_json
from .materialization_runtime import materialize_from_request_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute one registered KLC materialization through the generic runtime boundary.")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--no-replace", action="store_true")
    parser.add_argument("--duckdb-memory-limit", default="1GB")
    parser.add_argument("--duckdb-threads", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = materialize_from_request_file(
        args.request,
        args.output,
        replace=not args.no_replace,
        duckdb_memory_limit=args.duckdb_memory_limit,
        duckdb_threads=args.duckdb_threads,
    )
    write_json(args.result, result)
    print(json.dumps({
        "schema_version": result["schema_version"],
        "execution_id": result["execution_id"],
        "materialization_id": result["materialization_id"],
        "status": result["status"],
        "result": str(args.result),
        "output": str(args.output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
