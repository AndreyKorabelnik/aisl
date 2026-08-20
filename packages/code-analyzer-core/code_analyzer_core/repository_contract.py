from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_analyzer_core.utils import normalize_name, write_json

REPOSITORY_ANALYSIS_CONTRACT_VERSION = "1.0"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_id_from_path(repo_path: str | Path, given: str | None = None) -> str:
    if given:
        return normalize_name(given) or "repo"
    return normalize_name(Path(repo_path).name) or "repo"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def write_repository_analysis_manifest(
    *,
    repository_analysis_root: str | Path,
    repo_id: str,
    source_repository_path: str | Path,
    static_analysis_output: str | Path,
    llm_analysis_output: str | Path | None = None,
    analysis_scope: str = "repository",
    static_profile: str | None = None,
    run_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repository_analysis_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    static_path = Path(static_analysis_output).resolve()
    llm_path = Path(llm_analysis_output).resolve() if llm_analysis_output else root / "llm-analysis-output"
    try:
        static_rel = static_path.relative_to(root).as_posix()
    except Exception:
        static_rel = str(static_path)
    try:
        llm_rel = llm_path.relative_to(root).as_posix()
    except Exception:
        llm_rel = str(llm_path)
    payload = {
        "format": "repository_analysis_manifest",
        "format_version": REPOSITORY_ANALYSIS_CONTRACT_VERSION,
        "analysis_scope": analysis_scope,
        "repo_id": repo_id,
        "source_repository_path": str(Path(source_repository_path).resolve()),
        "static_analysis_output": static_rel,
        "llm_analysis_output": llm_rel,
        "analysis_bundle_manifest": f"{llm_rel}/analysis_bundle_manifest.json",
        "static_profile": static_profile,
        "run_id": run_id,
        "project_code": project_code,
        "system_name": system_name,
        "counts": counts or {},
        "updated_at": now_utc(),
    }
    write_json(root / "repository-analysis-manifest.json", payload)
    return payload


def repository_analysis_root_for_static_output(static_analysis_output: str | Path) -> Path:
    out = Path(static_analysis_output).resolve()
    return out.parent


def safe_run_id(run_id: str | None = None) -> str:
    if run_id:
        cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", run_id).strip("._-")
        if cleaned:
            return cleaned
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def analysis_output_type(analysis_output: str | Path) -> str:
    root = Path(analysis_output).resolve()
    manifest = read_json(root / "manifest.json", {}) or {}
    value = manifest.get("workspace_type") or manifest.get("profile") or manifest.get("source_type")
    if not value:
        raise ValueError(f"Repository analysis output type is not set in {root / 'manifest.json'}")
    return str(value)


def require_analysis_output_type(analysis_output: str | Path, expected: str) -> Path:
    root = Path(analysis_output).resolve()
    actual = analysis_output_type(root)
    if actual != expected:
        raise ValueError(f"Repository analysis output {root} has type {actual!r}; expected {expected!r}")
    return root


