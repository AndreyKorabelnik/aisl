from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(read_text(path))


def print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def safe_name(value: str, fallback: str = "item") -> str:
    value = str(value or fallback).strip() or fallback
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value[:160] or fallback


def load_manifest(analysis_out: Path) -> dict[str, Any]:
    return read_json(analysis_out / "manifest.json", {}) or {}


def repo_from_analysis(analysis_out: Path) -> Path:
    manifest = load_manifest(analysis_out)
    repo_path = manifest.get("repo_path")
    if not repo_path:
        repo = read_json(analysis_out / "core" / "repository.json", {}) or {}
        repo_path = repo.get("repo_path")
    if not repo_path:
        raise FileNotFoundError("Repository path is not available in analysis-output manifest/core repository")
    repo = Path(repo_path)
    if not repo.exists():
        raise FileNotFoundError(f"Repository path from analysis-output does not exist: {repo}")
    return repo


def load_navigation(analysis_out: Path) -> dict[str, Any]:
    return read_json(analysis_out / "compact" / "navigation.json", {}) or {}


def load_core(analysis_out: Path, name: str) -> list[dict[str, Any]]:
    data = read_json(analysis_out / "core" / f"{name}.json", [])
    return data if isinstance(data, list) else []


def write_lazy(analysis_out: Path, kind: str, name: str, obj: Any) -> Path:
    path = analysis_out / "lazy" / kind / f"{safe_name(name)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def snippet_lines(text: str, line: int, radius: int = 2) -> str:
    lines = text.splitlines()
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(lines[start - 1:end])
