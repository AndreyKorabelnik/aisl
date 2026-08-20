from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON file {candidate}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {candidate}")
    return payload


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, target)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temp, target)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def relative_or_absolute(path: str | Path, base: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return str(resolved)


_OUTPUT_MARKER_NAME = ".static-analysis-runner-output.json"
_OUTPUT_MARKER_SCHEMA = "static_analysis_runner_output_marker/v1"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _project_roots(start: Path) -> tuple[Path, ...]:
    roots: list[Path] = []
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").is_file():
            roots.append(candidate)
    return tuple(roots)


def _validate_output_path(path: str | Path, *, protected_paths: tuple[Path, ...]) -> Path:
    raw = str(path)
    if not raw.strip():
        raise ValueError("refuse to use an empty output directory")

    output = Path(path).expanduser().resolve()
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()

    if output == Path(output.anchor):
        raise ValueError(f"refuse to use filesystem root as output directory: {output}")
    if output == home:
        raise ValueError(f"refuse to use home directory as output directory: {output}")
    if output == cwd or _is_relative_to(cwd, output):
        raise ValueError(
            f"refuse to use the current working directory or one of its parents as output: {output}"
        )
    for project_root in _project_roots(cwd):
        if output == project_root:
            raise ValueError(f"refuse to use project root as output directory: {output}")

    for protected in protected_paths:
        protected_resolved = Path(protected).expanduser().resolve()
        if output == protected_resolved:
            raise ValueError(f"output must not equal protected input path: {protected_resolved}")
        if _is_relative_to(protected_resolved, output):
            raise ValueError(f"output must not be a parent of protected input path: {protected_resolved}")
        if _is_relative_to(output, protected_resolved):
            raise ValueError(f"output must not be inside protected input path: {protected_resolved}")
    return output


def validate_output_path(path: str | Path, *, protected_paths: tuple[Path, ...] = ()) -> Path:
    """Validate an output target without creating, deleting, or modifying anything."""
    return _validate_output_path(path, protected_paths=protected_paths)


def _valid_output_marker(output: Path) -> bool:
    marker = output / _OUTPUT_MARKER_NAME
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == _OUTPUT_MARKER_SCHEMA
        and payload.get("producer") == "static-analysis-runner"
    )


def _write_output_marker(output: Path) -> None:
    write_json(
        output / _OUTPUT_MARKER_NAME,
        {
            "schema_version": _OUTPUT_MARKER_SCHEMA,
            "producer": "static-analysis-runner",
            "created_at": now_utc(),
        },
    )


def prepare_output(path: str | Path, *, replace: bool, protected_paths: tuple[Path, ...] = ()) -> Path:
    """Create a runner-owned output directory without deleting arbitrary user data.

    A non-empty directory can be replaced only when it contains a valid runner ownership marker.
    Dangerous targets (blank path, filesystem root, home, cwd/ancestor, project root, or input paths)
    are rejected before any filesystem mutation.
    """
    output = _validate_output_path(path, protected_paths=protected_paths)
    if output.exists() and any(output.iterdir()):
        if not replace:
            raise ValueError(f"output directory is not empty: {output}; pass --replace to rebuild it")
        if not _valid_output_marker(output):
            raise ValueError(
                "refuse to replace non-empty directory not owned by static-analysis-runner: "
                f"{output}; choose a dedicated output directory or remove it manually after verification"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    _write_output_marker(output)
    return output
