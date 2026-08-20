#!/usr/bin/env python3
"""Verify the distributable source tree against SOURCE_TREE_MANIFEST.sha256."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE_TREE_MANIFEST.sha256"
EXCLUDED_PARTS = {".pytest_cache", "__pycache__", "node_modules", "dist", ".git"}
EXCLUDED_NAMES = {"SOURCE_TREE_MANIFEST.sha256"}
EXCLUDED_PREFIXES = {"logs"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    relative_text = relative.as_posix()
    return (
        path.is_file()
        and path.name not in EXCLUDED_NAMES
        and path.suffix != ".pyc"
        and not any(part in EXCLUDED_PARTS for part in relative.parts)
        and not any(relative_text == prefix or relative_text.startswith(prefix + "/") for prefix in EXCLUDED_PREFIXES)
    )


def main() -> None:
    expected: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative = line.split("  ", 1)
        expected[relative] = digest

    actual_files = {
        path.relative_to(ROOT).as_posix(): path
        for path in ROOT.rglob("*")
        if included(path)
    }
    missing = sorted(set(expected) - set(actual_files))
    unexpected = sorted(set(actual_files) - set(expected))
    mismatched = sorted(
        relative
        for relative, path in actual_files.items()
        if relative in expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected[relative]
    )
    if missing or unexpected or mismatched:
        raise SystemExit(
            f"source manifest verification failed: missing={missing}, unexpected={unexpected}, mismatched={mismatched}"
        )
    print(f"Source manifest verification passed: {len(expected)} files")


if __name__ == "__main__":
    main()
