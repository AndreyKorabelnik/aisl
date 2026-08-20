#!/usr/bin/env python3
"""Write a deterministic SHA-256 manifest for distributable source files."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "SOURCE_TREE_MANIFEST.sha256"
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
    lines = []
    for path in sorted((path for path in ROOT.rglob("*") if included(path)), key=lambda item: item.as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} entries to {OUTPUT}")


if __name__ == "__main__":
    main()
