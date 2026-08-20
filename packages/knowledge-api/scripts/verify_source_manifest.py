#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE_TREE_MANIFEST.sha256"
EXCLUDED = {".git", ".pytest_cache", "__pycache__"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        path.is_file()
        and path != MANIFEST
        and path.suffix != ".pyc"
        and not any(part in EXCLUDED for part in relative.parts)
    )


def main() -> None:
    expected = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line:
            digest, relative = line.split("  ", 1)
            expected[relative] = digest
    actual = {path.relative_to(ROOT).as_posix(): path for path in ROOT.rglob("*") if included(path)}
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    mismatched = sorted(
        relative for relative, path in actual.items()
        if relative in expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected[relative]
    )
    if missing or unexpected or mismatched:
        raise SystemExit(f"source manifest mismatch: missing={missing}, unexpected={unexpected}, mismatched={mismatched}")
    print(f"Source manifest verified: {len(actual)} files")


if __name__ == "__main__":
    main()
