from __future__ import annotations

from pathlib import Path
from typing import Any

from code_analyzer_core.pipeline import run_analysis
from code_analyzer_core.utils import write_json
from code_analyzer_core.repository_contract import (
    now_utc,
    repo_id_from_path,
    safe_run_id,
    write_repository_analysis_manifest,
    repository_analysis_root_for_static_output,
)


def _extract_source_comments(repo: Path, repo_id: str, out: Path) -> list[dict[str, Any]]:
    """Publish an empty auxiliary catalog; comments are not hard lineage evidence."""
    comments: list[dict[str, Any]] = []
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True, exist_ok=True)
    write_json(facts_dir / "source_comment.json", comments)
    write_json(out / "diagnostics" / "source_comment_status.json", {
        "comments_extracted": 0,
        "mode": "disabled_by_default_for_lineage_profiles",
        "reason": "source comments are auxiliary navigation data and are not hard FDP/lineage evidence",
    })
    return comments


def run_java_analysis(
    repo_path: str | Path,
    analysis_out: str | Path,
    repo_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    run_id: str | None = None,
    max_packages: int = 80,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
    analysis_profile: str | Path | None = None,
    fp_id: str | None = None,
    fp_name: str | None = None,
    foundation_input: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    rid = repo_id_from_path(repo, repo_id)
    rid_run = safe_run_id(run_id)
    out = Path(analysis_out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = run_analysis(
        repo_path=repo,
        out_dir=out,
        project_code=project_code,
        system_name=system_name,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
        analysis_profile=analysis_profile,
        repo_id=rid,
        fp_id=fp_id or rid,
        fp_name=fp_name or fp_id or rid,
        foundation_input=foundation_input,
    )
    source_comments = _extract_source_comments(repo, rid, out)
    counts = {
        "comments": len(source_comments),
        "interfaces": len(result.interfaces),
        "schemas": len(result.schemas),
        "facts": len(result.facts),
        "relations": len(result.relations),
        "files_analyzed": result.files_analyzed,
    }
    # Counts are now materialized; release the large in-memory AnalysisResult
    # before rebuilding workspace summaries and returning to the CLI.
    del result
    latest = {
        "repo_id": rid,
        "repo_path": str(repo),
        "system_name": system_name,
        "project_code": project_code,
        "fp_id": fp_id or rid,
        "fp_name": fp_name or fp_id or rid,
        "profile": "java",
        "workspace_type": "java",
        "run_id": rid_run,
        "static_analysis_output": str(out),
        "analysis_out": str(out),
        "updated_at": now_utc(),
        "counts": counts,
    }
    repo_manifest = write_repository_analysis_manifest(
        repository_analysis_root=repository_analysis_root_for_static_output(out),
        repo_id=rid,
        source_repository_path=repo,
        static_analysis_output=out,
        static_profile=str(analysis_profile) if analysis_profile else None,
        run_id=rid_run,
        project_code=project_code,
        system_name=system_name,
        counts=counts,
    )
    return {"repo": latest, "repository_analysis_manifest": repo_manifest, "analysis_out": str(out), "static_analysis_output": str(out)}



def build_java_foundation(
    repo_path: str | Path,
    foundation_out: str | Path,
    foundation_fragment: str | Path,
    repo_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    verbose: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    rid = repo_id_from_path(repo, repo_id)
    out = Path(foundation_out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = run_analysis(
        repo_path=repo,
        out_dir=out,
        project_code=project_code,
        system_name=system_name,
        verbose=verbose,
        analysis_profile=foundation_fragment,
        repo_id=rid,
        fp_id=rid,
        fp_name=rid,
        foundation_output=out,
        foundation_only=True,
    )
    manifest_path = out / "foundation-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"foundation artifact was not published: {manifest_path}")
    counts = {
        "files_analyzed": result.files_analyzed,
        "facts": len(result.facts),
        "interfaces": len(result.interfaces),
        "schemas": len(result.schemas),
        "relations": len(result.relations),
    }
    del result
    return {
        "foundation_manifest": str(manifest_path),
        "foundation_out": str(out),
        "repo_id": rid,
        "counts": counts,
    }
