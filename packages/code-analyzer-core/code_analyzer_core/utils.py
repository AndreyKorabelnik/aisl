from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    value = value.replace("-", "_").replace(" ", "_")
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def snippet_around(text: str, line: int, radius: int = 2) -> str:
    lines = text.splitlines()
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(lines[start - 1:end])
