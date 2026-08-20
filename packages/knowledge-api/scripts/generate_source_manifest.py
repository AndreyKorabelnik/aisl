#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "SOURCE_TREE_MANIFEST.sha256"
EXCLUDED = {".git", ".pytest_cache", "__pycache__"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        path.is_file()
        and path != OUTPUT
        and path.suffix != ".pyc"
        and not any(part in EXCLUDED for part in relative.parts)
    )


def main() -> None:
    lines = []
    for path in sorted((item for item in ROOT.rglob("*") if included(item)), key=lambda item: item.as_posix()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} entries to {OUTPUT}")


if __name__ == "__main__":
    main()
