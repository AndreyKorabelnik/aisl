from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence

from knowledge_layer_core.materialization_runtime import materialize_from_request_file

from .io_utils import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute one generic KLC materialization in an isolated Runner worker process."
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--duckdb-memory-limit", default="1GB")
    parser.add_argument("--duckdb-threads", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.duckdb_threads < 1:
        raise ValueError("duckdb_threads must be at least 1")
    def progress(message: str) -> None:
        print(str(message), file=sys.stderr, flush=True)

    result = materialize_from_request_file(
        args.request,
        args.output,
        replace=True,
        duckdb_memory_limit=args.duckdb_memory_limit,
        duckdb_threads=args.duckdb_threads,
        progress=progress,
    )
    write_json(args.result, result)
    return 0


if __name__ == "__main__":
    # This module is intentionally a disposable process boundary around DuckDB-heavy
    # KLC materializations. Some large DuckDB artifacts leave interpreter-shutdown
    # finalizers waiting long after the typed result has been durably written.
    # main() remains normally callable for tests; only the real worker process
    # bypasses interpreter finalization after flushing its text streams.
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
