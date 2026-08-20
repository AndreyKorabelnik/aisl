from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def workspace_type(workspace: str | Path) -> str:
    """Return workspace_type from workspace_manifest.json.

    This helper is intentionally independent from code-analyzer-core so pipeline
    and report can run in workspace mode without importing analyzer internals.
    """
    ws = Path(workspace).resolve()
    manifest_path = ws / "workspace_manifest.json"
    manifest = read_json(manifest_path, {}) or {}
    wtype = manifest.get("workspace_type")
    if not wtype:
        raise ValueError(f"Workspace type is not set in {manifest_path}")
    return str(wtype)


def latest_repo(workspace: str | Path, repo_id: str, *, expected_type: str | None = None) -> dict[str, Any]:
    ws = Path(workspace).resolve()
    if expected_type is not None:
        actual = workspace_type(ws)
        if actual != expected_type:
            raise ValueError(f"Workspace {ws} has type {actual!r}; expected {expected_type!r}")
    latest_path = ws / "repositories" / repo_id / "latest.json"
    latest = read_json(latest_path, {}) or {}
    if not latest:
        raise FileNotFoundError(f"Repository {repo_id!r} not found in workspace {ws}; missing {latest_path}")
    return latest


def latest_analysis_out(workspace: str | Path, repo_id: str, *, expected_type: str | None = None) -> Path:
    latest = latest_repo(workspace, repo_id, expected_type=expected_type)
    raw = latest.get("analysis_out")
    if not raw:
        raise FileNotFoundError(f"Latest analysis output is not recorded for repo {repo_id!r}")
    out = Path(str(raw))
    if not out.is_absolute():
        # latest.json should normally contain an absolute path, but support old
        # or manually edited workspaces by resolving relative to workspace root.
        out = Path(workspace).resolve() / out
    if not out.exists():
        raise FileNotFoundError(f"Latest analysis output for repo {repo_id!r} does not exist: {out}")
    return out
