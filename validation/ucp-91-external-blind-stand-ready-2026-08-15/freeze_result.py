#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_STATUSES = {"confirmed", "strongly_supported", "probable", "ambiguous", "unresolved"}
REQUIRED_KEYS = {
    "input_index", "attribute", "object_fqcn", "field", "repo_id",
    "status", "basis", "alternatives", "analysis_gap",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> None:
    raise SystemExit(f"INVALID: {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and freeze a 91-attribute agent result before Gold is opened.")
    parser.add_argument("result", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    inputs_path = root / "blind" / "INPUTS_91.json"
    inputs_doc = json.loads(inputs_path.read_text(encoding="utf-8"))
    expected = {int(i["input_index"]): str(i["attribute"]) for i in inputs_doc["items"]}
    if sorted(expected) != list(range(1, 92)):
        fail("INPUTS_91.json is not the canonical 1..91 input set")

    result_path = args.result.expanduser().resolve()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "ucp-attribute-agent-result/v1":
        fail("schema_version must be ucp-attribute-agent-result/v1")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != 91:
        fail("results must contain exactly 91 items")

    seen: set[int] = set()
    status_counts = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    for pos, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            fail(f"result #{pos} is not an object")
        missing = sorted(REQUIRED_KEYS - set(item))
        if missing:
            fail(f"result #{pos} is missing keys: {missing}")
        idx = item.get("input_index")
        if not isinstance(idx, int) or idx not in expected:
            fail(f"result #{pos} has invalid input_index: {idx!r}")
        if idx in seen:
            fail(f"duplicate input_index: {idx}")
        seen.add(idx)
        if item.get("attribute") != expected[idx]:
            fail(f"attribute text for input_index={idx} was not copied verbatim")
        status = item.get("status")
        if status not in ALLOWED_STATUSES:
            fail(f"input_index={idx} has unsupported status: {status!r}")
        status_counts[status] += 1
        if not isinstance(item.get("basis"), str) or not item["basis"].strip():
            fail(f"input_index={idx} must contain a non-empty evidence-grounded basis")
        if not isinstance(item.get("alternatives"), list):
            fail(f"input_index={idx} alternatives must be a list")
        for nullable in ("object_fqcn", "field", "repo_id", "analysis_gap"):
            if item.get(nullable) is not None and not isinstance(item.get(nullable), str):
                fail(f"input_index={idx} {nullable} must be string or null")
    if seen != set(expected):
        fail("result input indexes do not exactly cover 1..91")

    digest = sha256(result_path)
    receipt_path = args.receipt or result_path.with_suffix(result_path.suffix + ".freeze.json")
    receipt = {
        "schema_version": "ucp-attribute-agent-result-freeze/v1",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "result_file": result_path.name,
        "result_bytes": result_path.stat().st_size,
        "result_sha256": digest,
        "input_file": inputs_path.name,
        "input_sha256": sha256(inputs_path),
        "result_count": 91,
        "status_counts": status_counts,
        "gold_accessed_by_validator": False,
        "next_step": "Only now provide the frozen result and its SHA-256 to the Gold evaluator.",
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
