from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_analyzer_core.analysis_profiles import load_analysis_profile
from code_analyzer_core.repository_contract import (
    repository_analysis_root_for_static_output,
    write_repository_analysis_manifest,
)
from code_analyzer_core.pipeline import run_analysis
from code_analyzer_core.evidence_runtime import execute_evidence_request
from code_analyzer_core.utils import normalize_name, write_json



def _write_git_change_repository_catalog(root: Path, repo_id: str, record: dict[str, Any], summary: dict[str, Any]) -> None:
    catalog = root / "repository-catalog"
    catalog.mkdir(parents=True, exist_ok=True)
    write_json(catalog / f"{repo_id}.json", record)
    write_json(root / "repository-catalog.json", {
        "artifact": "git_change_repository_catalog",
        "repositories": [record],
        "summary": summary,
    })


class GitChangeInputError(ValueError):
    """User-facing git-change input error with actionable diagnostics."""


def _short_git_stderr(stderr: str) -> str:
    value = (stderr or "").strip()
    return value or "git did not return a diagnostic message"


def _git_ref_resolution_hint(repo: Path, ref: str, option_name: str | None = None) -> str:
    label = f"{option_name} " if option_name else ""
    return (
        f"Invalid git revision for {label}{ref!r}. The ref must resolve to exactly one commit in the local repository {repo}. "
        "This usually means the commit was copied from another repository/fork, the remote branch was not fetched, "
        "the local clone is shallow, or the commit hash was copied incorrectly. "
        f"Check with: git -C {repo} rev-parse --verify {ref}^{{commit}} ; "
        f"git -C {repo} cat-file -t {ref}. "
        "If the commit exists remotely, run: git fetch --all --tags --prune. "
        "For a shallow clone, run: git fetch --unshallow --tags --prune."
    )




def _profile_snapshot_analyzer(profile: dict[str, Any]) -> str:
    """Select snapshot execution from typed evidence requirements only."""
    evidence_requirements = profile.get("evidence_requirements") or []
    uses_sql_analysis = any(
        isinstance(item, dict)
        and str(item.get("artifact_kind") or "") == "sql-analysis"
        and str(item.get("schema_version") or "") == "sql-analysis/v1"
        for item in evidence_requirements
    )
    return "sql" if uses_sql_analysis else "core"



def _snapshot_files_analyzed(result: Any) -> int | None:
    if hasattr(result, "files_analyzed"):
        return getattr(result, "files_analyzed")
    if isinstance(result, dict):
        counts = ((result.get("repo") or {}).get("counts") or {})
        value = counts.get("files_scanned") or counts.get("files_analyzed")
        try:
            return int(value) if value is not None else None
        except Exception:
            return None
    return None




def _canonical_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _sql_evidence_request(*, repo_id: str, project_code: str, system_name: str) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": "core_evidence_execution_request/v1",
        "source": {"source_kind": "repository", "source_id": repo_id},
        "evidence_requirements": [{
            "artifact_kind": "sql-analysis",
            "schema_version": "sql-analysis/v1",
            "parameters": {"project_code": project_code, "system_name": system_name},
            "required_by": ["git-change-analysis"],
        }],
    }
    request["request_fingerprint"] = _canonical_fingerprint(request)
    return request

def _run_snapshot_analysis(
    *,
    snapshot_analyzer: str,
    repo_path: Path,
    analysis_root: Path,
    run_id: str,
    analysis_profile: str | Path,
    repo_id: str,
    project_code: str,
    system_name: str,
    max_packages: int,
    max_fields_per_schema: int,
    verbose: bool,
) -> tuple[dict[str, Any], Path]:
    if snapshot_analyzer == "sql":
        execution = execute_evidence_request(
            repository=repo_path,
            request=_sql_evidence_request(
                repo_id=repo_id,
                project_code=project_code,
                system_name=system_name,
            ),
            output=analysis_root,
            repo_id=repo_id,
        )
        artifact = next(
            item for item in execution.get("evidence_artifacts") or []
            if item.get("artifact_kind") == "sql-analysis"
            and item.get("schema_version") == "sql-analysis/v1"
        )
        coverage = dict(artifact.get("coverage") or {})
        result = {
            "repo": {
                "repo_id": repo_id,
                "counts": {
                    "files_scanned": int(coverage.get("sql_files_scanned") or 0),
                    "sql_statements": int(coverage.get("sql_statement_count") or 0),
                },
            },
            "core_evidence_execution": execution,
            "analysis_out": str(analysis_root / "evidence"),
        }
        return result, analysis_root / "evidence"
    out_dir = analysis_root / "analysis-output"
    result = run_analysis(
        repo_path=repo_path,
        out_dir=out_dir,
        project_code=project_code,
        system_name=system_name,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
        analysis_profile=analysis_profile,
        repo_id=repo_id,
        fp_id=repo_id,
        fp_name=repo_id,
    )
    return result, out_dir

def _run_git(repo: Path, args: list[str], *, text: bool = True, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout if text else result.stdout  # type: ignore[return-value]


def _rev_parse(repo: Path, ref: str, *, option_name: str | None = None) -> str:
    ref_value = (ref or "").strip()
    if not ref_value:
        raise GitChangeInputError(f"Empty git revision was provided for {option_name or 'git ref'}.")
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref_value}^{{commit}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitChangeInputError(
            _git_ref_resolution_hint(repo, ref_value, option_name)
            + f" Git error: {_short_git_stderr(result.stderr)}"
        )
    return result.stdout.strip()


def _commit_parent(repo: Path, commit: str) -> str:
    return _run_git(repo, ["rev-parse", f"{commit}^"], check=True).strip()


def _merge_base(repo: Path, left: str, right: str) -> str | None:
    out = _run_git(repo, ["merge-base", left, right], check=False).strip()
    return out or None


def _commit_meta(repo: Path, commit: str) -> dict[str, Any]:
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%s"
    out = _run_git(repo, ["show", "-s", f"--format={fmt}", commit]).strip()
    parts = out.split("\x1f")
    keys = ["commit", "author_name", "author_email", "author_date", "committer_name", "committer_email", "committer_date", "subject"]
    return {k: parts[i] if i < len(parts) else "" for i, k in enumerate(keys)}



def _email_hash(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _login_from_email(email: str | None) -> str | None:
    value = (email or "").strip()
    if "@" not in value:
        return None
    login = value.split("@", 1)[0].strip()
    return login or None


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _split_people(value: str | list[str] | tuple[str, ...] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    raw_items: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            raw_items.extend(str(item).split(","))
    else:
        raw_items = str(value).split(",")
    people: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        token = raw.strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        if "@" in token:
            people.append({
                "name": None,
                "login": _login_from_email(token),
                "email": token,
                "email_hash": _email_hash(token),
            })
        else:
            people.append({"name": token, "login": token, "email": None, "email_hash": None})
    return people


def _collect_commit_records(repo: Path, base: str, target: str) -> list[dict[str, Any]]:
    fmt = "%H%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%s"
    out = _run_git(repo, ["log", "--reverse", f"--format={fmt}", f"{base}..{target}"], check=False).strip()
    records: list[dict[str, Any]] = []
    if not out:
        return records
    keys = ["commit", "author_name", "author_email", "author_date", "committer_name", "committer_email", "committer_date", "subject"]
    for line in out.splitlines():
        parts = line.split("\x1f")
        item = {k: parts[i] if i < len(parts) else "" for i, k in enumerate(keys)}
        item["author_email_hash"] = _email_hash(item.get("author_email"))
        item["committer_email_hash"] = _email_hash(item.get("committer_email"))
        records.append(item)
    return records


def _aggregate_people(records: list[dict[str, Any]], *, role: str) -> list[dict[str, Any]]:
    name_key = f"{role}_name"
    email_key = f"{role}_email"
    date_key = f"{role}_date"
    grouped: dict[str, dict[str, Any]] = {}
    for rec in records:
        email = str(rec.get(email_key) or "").strip()
        name = str(rec.get(name_key) or "").strip()
        person_key = _email_hash(email) or normalize_name(name) or "unknown"
        item = grouped.setdefault(person_key, {
            "name": name or None,
            "login": _login_from_email(email),
            "email": email or None,
            "email_hash": _email_hash(email),
            "commit_count": 0,
            "first_commit": None,
            "last_commit": None,
            "first_commit_date": None,
            "last_commit_date": None,
        })
        item["commit_count"] += 1
        commit = rec.get("commit") or None
        date = rec.get(date_key) or None
        if item["first_commit"] is None:
            item["first_commit"] = commit
            item["first_commit_date"] = date
        item["last_commit"] = commit
        item["last_commit_date"] = date
    return sorted(grouped.values(), key=lambda x: (-int(x.get("commit_count") or 0), str(x.get("name") or ""), str(x.get("email_hash") or "")))


def _build_change_metadata(
    *,
    repo: Path,
    repo_id: str,
    range_kind: str,
    base_ref: str,
    target_ref: str,
    base_commit: str,
    target_commit: str,
    change_id: str | None = None,
    change_type: str | None = None,
    source_branch: str | None = None,
    target_branch: str | None = None,
    reviewers: str | list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    limitations: list[str] = []
    sources: list[str] = ["git_log", "git_range_parameters"]
    if change_id or source_branch or target_branch or reviewers:
        sources.append("merge_request_metadata")
    env_change_id = _env_first("CI_MERGE_REQUEST_IID", "CI_MERGE_REQUEST_ID", "CHANGE_ID", "MR_ID")
    env_source_branch = _env_first("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "CHANGE_BRANCH", "SOURCE_BRANCH")
    env_target_branch = _env_first("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "CI_DEFAULT_BRANCH", "TARGET_BRANCH")
    env_reviewers = _env_first("CI_MERGE_REQUEST_REVIEWERS", "CI_MERGE_REQUEST_APPROVED_BY", "REVIEWERS")
    if env_change_id or env_source_branch or env_target_branch or env_reviewers:
        sources.append("ci_environment")

    resolved_change_id = change_id or env_change_id
    resolved_source_branch = source_branch or env_source_branch
    resolved_target_branch = target_branch or env_target_branch
    resolved_reviewers = reviewers or env_reviewers
    resolved_change_type = change_type or ("mr" if resolved_change_id else ("commit" if range_kind == "commit" else "range"))
    if resolved_change_type not in {"commit", "range", "mr", "branch_diff", "unknown"}:
        limitations.append(f"Unsupported change_type '{resolved_change_type}' was preserved as unknown.")
        resolved_change_type = "unknown"

    records = _collect_commit_records(repo, base_commit, target_commit)
    if not records:
        limitations.append("No commit records were returned by git log for the analyzed range.")
    if not resolved_change_id:
        limitations.append("MR/change id was not provided and was not found in supported CI environment variables.")
    if not resolved_source_branch:
        limitations.append("Source branch was not provided and was not found in supported CI environment variables.")
    if not resolved_target_branch:
        limitations.append("Target branch was not provided and was not found in supported CI environment variables.")
    reviewer_items = _split_people(resolved_reviewers)
    if not reviewer_items:
        limitations.append("Reviewer metadata was not provided; analyzer does not query GitLab/Jira/network services.")

    return {
        "repo_id": repo_id,
        "change_id": resolved_change_id,
        "change_type": resolved_change_type,
        "source_branch": resolved_source_branch,
        "target_branch": resolved_target_branch,
        "commit_range": {
            "before": base_commit,
            "after": target_commit,
            "before_ref": base_ref,
            "after_ref": target_ref,
            "range_kind": range_kind,
        },
        "commit_count": len(records),
        "authors": _aggregate_people(records, role="author"),
        "committers": _aggregate_people(records, role="committer"),
        "reviewers": reviewer_items,
        "metadata_sources": sorted(set(sources)),
        "metadata_limitations": limitations,
        "authoring_note": "Author/committer metadata is recorded only for traceability and is not used for scoring or personal evaluation.",
    }


def _safe_rel(path: str) -> str:
    return path.replace("\\", "/").strip()


def _language_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".sql", ".hql"}:
        return "sql"
    if suffix == ".java":
        return "java"
    if suffix in {".py"}:
        return "python"
    if suffix in {".yml", ".yaml"}:
        return "yaml"
    if suffix in {".json"}:
        return "json"
    if suffix in {".xml"}:
        return "xml"
    if suffix in {".properties", ".conf", ".ini"}:
        return "config"
    if suffix in {".md", ".adoc", ".rst"}:
        return "documentation"
    return suffix.removeprefix(".") or "unknown"


def _is_test_path(path: str) -> bool:
    p = path.lower().replace("\\", "/")
    name = Path(p).name
    return (
        "/test/" in f"/{p}/"
        or p.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("test.java")
        or "src/test" in p
    )


def _is_doc_path(path: str) -> bool:
    p = path.lower()
    return Path(p).suffix in {".md", ".adoc", ".rst"} or "docs/" in p or p.startswith("doc/")


def _is_config_path(path: str) -> bool:
    p = path.lower()
    return Path(p).suffix in {".yml", ".yaml", ".json", ".xml", ".properties", ".conf", ".ini"} or "config" in p


def _collect_changed_files(repo: Path, base: str, target: str) -> list[dict[str, Any]]:
    name_status = _run_git(repo, ["diff", "--name-status", "-M", base, target]).splitlines()
    numstat = _run_git(repo, ["diff", "--numstat", "-M", base, target]).splitlines()
    stats: dict[str, dict[str, Any]] = {}
    for line in numstat:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], _safe_rel(parts[-1])
        def n(v: str) -> int | None:
            try:
                return int(v)
            except Exception:
                return None
        stats[path] = {"lines_added": n(added), "lines_deleted": n(deleted)}

    items: list[dict[str, Any]] = []
    for idx, line in enumerate(name_status, start=1):
        parts = line.split("\t")
        if not parts:
            continue
        raw_status = parts[0]
        status = raw_status[0]
        old_path = None
        new_path = None
        if status == "R" and len(parts) >= 3:
            old_path, new_path = _safe_rel(parts[1]), _safe_rel(parts[2])
            path = new_path
            change_kind = "renamed"
        else:
            path = _safe_rel(parts[1] if len(parts) > 1 else "")
            change_kind = {"A": "added", "M": "modified", "D": "deleted", "C": "copied"}.get(status, "changed")
        stat = stats.get(path) or stats.get(new_path or "") or {}
        items.append({
            "changed_file_id": f"changed_file_{idx:06d}",
            "path": path,
            "old_path": old_path,
            "new_path": new_path,
            "git_status": raw_status,
            "change_kind": change_kind,
            "language": _language_for_path(path),
            "lines_added": stat.get("lines_added"),
            "lines_deleted": stat.get("lines_deleted"),
            "is_test": _is_test_path(path),
            "is_documentation": _is_doc_path(path),
            "is_config": _is_config_path(path),
        })
    return items


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?P<context>.*)$")


def _collect_hunks(repo: Path, base: str, target: str, *, max_hunks: int = 5000) -> list[dict[str, Any]]:
    diff = _run_git(repo, ["diff", "--unified=0", "--no-ext-diff", base, target], check=True)
    hunks: list[dict[str, Any]] = []
    current_file = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = _safe_rel(line.removeprefix("+++ b/"))
            continue
        m = HUNK_RE.match(line)
        if m and current_file and current_file != "/dev/null":
            hunks.append({
                "changed_hunk_id": f"changed_hunk_{len(hunks)+1:06d}",
                "file": current_file,
                "old_line_start": int(m.group(1)),
                "old_line_count": int(m.group(2) or 1),
                "new_line_start": int(m.group(3)),
                "new_line_count": int(m.group(4) or 1),
                "context": (m.group("context") or "").strip()[:300],
            })
            if len(hunks) >= max_hunks:
                break
    return hunks


def _export_snapshot(repo: Path, commit: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archive_path = dest.parent / f"{dest.name}.tar"
    try:
        subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", "-o", str(archive_path), commit], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with tarfile.open(archive_path, "r") as tf:
            tf.extractall(dest, filter="data")
    finally:
        archive_path.unlink(missing_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def _list_json(analysis_out: Path, *rel_paths: str) -> list[dict[str, Any]]:
    for rel in rel_paths:
        path = analysis_out / rel
        if path.suffix == ".jsonl" and path.is_file():
            records: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    records.append(item)
            return records
        data = _read_json(path, None)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    return []


def _item_key(item: dict[str, Any], keys: list[str]) -> str:
    vals: list[str] = []
    for key in keys:
        vals.append(normalize_name(str(item.get(key) or "")))
    return "|".join(vals)


def _fingerprint(item: dict[str, Any], *, ignore_keys: set[str] | None = None) -> str:
    ignore = ignore_keys or set()
    clean = {k: v for k, v in item.items() if k not in ignore and not k.endswith("_id") and k not in {"file", "line_start", "line_end", "evidence", "repo_id", "fp_id"}}
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _delta(before: list[dict[str, Any]], after: list[dict[str, Any]], *, id_prefix: str, key_fields: list[str]) -> list[dict[str, Any]]:
    b = {_item_key(x, key_fields): x for x in before if _item_key(x, key_fields).strip("|")}
    a = {_item_key(x, key_fields): x for x in after if _item_key(x, key_fields).strip("|")}
    keys = sorted(set(b) | set(a))
    out: list[dict[str, Any]] = []
    for key in keys:
        bi = b.get(key)
        ai = a.get(key)
        if bi is None and ai is not None:
            kind = "added"
        elif bi is not None and ai is None:
            kind = "removed"
        elif bi is not None and ai is not None and _fingerprint(bi) != _fingerprint(ai):
            kind = "changed"
        else:
            continue
        out.append({
            "delta_id": f"{id_prefix}_{len(out)+1:06d}",
            "change_kind": kind,
            "stable_key": key,
            "key_fields": {field: (ai or bi or {}).get(field) for field in key_fields},
            "before": bi,
            "after": ai,
        })
    return out


def _coverage_stage_map(analysis_out: Path) -> dict[str, Any]:
    cov = _read_json(analysis_out / "evidence_coverage.json", {}) or _read_json(analysis_out / "diagnostics" / "evidence_coverage.json", {}) or {}
    if not isinstance(cov, dict):
        return {}
    return cov.get("stages") or {}


def _build_coverage_delta(before_out: Path, after_out: Path) -> dict[str, Any]:
    before = _coverage_stage_map(before_out)
    after = _coverage_stage_map(after_out)
    stage_deltas: list[dict[str, Any]] = []
    for stage in sorted(set(before) | set(after)):
        b = before.get(stage) or {}
        a = after.get(stage) or {}
        b_status = b.get("status")
        a_status = a.get("status")
        if b_status != a_status or b.get("requested_by_profile") != a.get("requested_by_profile"):
            stage_deltas.append({
                "stage": stage,
                "before_status": b_status,
                "after_status": a_status,
                "before_requested": b.get("requested_by_profile"),
                "after_requested": a.get("requested_by_profile"),
                "impact": "coverage_changed_between_before_after",
            })
    before_heavy = (_read_json(before_out / "evidence_coverage.json", {}) or {}).get("heavy_tools") or {}
    after_heavy = (_read_json(after_out / "evidence_coverage.json", {}) or {}).get("heavy_tools") or {}
    return {
        "artifact": "before_after_coverage_delta",
        "format_version": "1.0",
        "stage_deltas": stage_deltas,
        "before_heavy_tools": before_heavy,
        "after_heavy_tools": after_heavy,
        "coverage_changed": bool(stage_deltas),
        "policy": "Coverage changes are evidence quality signals, not change complexity by themselves.",
    }


def _renumber_deltas(id_prefix: str, parts: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in parts:
        for item in part:
            out.append({**item, "delta_id": f"{id_prefix}_{len(out)+1:06d}"})
    return out


def _build_deltas(before_out: Path, after_out: Path) -> dict[str, list[dict[str, Any]]]:
    tables_before = _list_json(before_out, "compact/db_schema_tables.json", "sql/db_schema_tables.json")
    tables_after = _list_json(after_out, "compact/db_schema_tables.json", "sql/db_schema_tables.json")
    columns_before = _list_json(before_out, "compact/db_schema_columns.json", "sql/db_schema_columns.json")
    columns_after = _list_json(after_out, "compact/db_schema_columns.json", "sql/db_schema_columns.json")
    rel_before = _list_json(before_out, "compact/db_schema_relationships.json", "sql/db_schema_relationships.json")
    rel_after = _list_json(after_out, "compact/db_schema_relationships.json", "sql/db_schema_relationships.json")

    java_lineage_before = _list_json(before_out, "compact/source_to_storage_lineage.json", "facts/facts_by_type/source_to_storage_lineage.json")
    java_lineage_after = _list_json(after_out, "compact/source_to_storage_lineage.json", "facts/facts_by_type/source_to_storage_lineage.json")
    canonical_sql_dependency_before = _list_json(before_out, "sql-analysis/facts/sql_object_dependency.jsonl")
    canonical_sql_dependency_after = _list_json(after_out, "sql-analysis/facts/sql_object_dependency.jsonl")

    mapping_before = _list_json(before_out, "compact/attribute_mappings.json", "facts/facts_by_type/attribute_mapping.json")
    mapping_after = _list_json(after_out, "compact/attribute_mappings.json", "facts/facts_by_type/attribute_mapping.json")
    deriv_before = _list_json(before_out, "compact/attribute_derivations.json", "facts/facts_by_type/attribute_derivation.json")
    deriv_after = _list_json(after_out, "compact/attribute_derivations.json", "facts/facts_by_type/attribute_derivation.json")
    canonical_sql_column_lineage_before = _list_json(before_out, "sql-analysis/facts/sql_direct_column_lineage.jsonl")
    canonical_sql_column_lineage_after = _list_json(after_out, "sql-analysis/facts/sql_direct_column_lineage.jsonl")

    flow_before = _list_json(before_out, "compact/data_flows.json", "facts/facts_by_type/data_flow.json")
    flow_after = _list_json(after_out, "compact/data_flows.json", "facts/facts_by_type/data_flow.json")
    event_before = _list_json(before_out, "compact/event_sources.json")
    event_after = _list_json(after_out, "compact/event_sources.json")

    lineage_delta = _renumber_deltas("lineage_delta", [
        _delta(java_lineage_before, java_lineage_after, id_prefix="lineage_delta", key_fields=["source_kind", "source_container", "source_field", "storage_target", "storage_field"]),
        _delta(canonical_sql_dependency_before, canonical_sql_dependency_after, id_prefix="lineage_delta", key_fields=["source_relation_name", "target_relation_name", "dependency_kind", "operation", "query_id"]),
    ])
    transformation_delta = _renumber_deltas("transformation_delta", [
        _delta(mapping_before + deriv_before, mapping_after + deriv_after, id_prefix="transformation_delta", key_fields=["source_container", "source_field", "target_container", "target_field", "expression_kind"]),
        _delta(canonical_sql_column_lineage_before, canonical_sql_column_lineage_after, id_prefix="transformation_delta", key_fields=["target_relation_name", "target_column", "source_relation_name", "source_column", "expression_kind", "query_id"]),
    ])

    return {
        "table_delta": _delta(tables_before, tables_after, id_prefix="table_delta", key_fields=["schema_name", "table_name"]),
        "column_delta": _delta(columns_before, columns_after, id_prefix="column_delta", key_fields=["schema_name", "table_name", "column_name"]),
        "relationship_delta": _delta(rel_before, rel_after, id_prefix="relationship_delta", key_fields=["source_table", "source_columns", "target_table", "target_columns", "constraint_name"]),
        "lineage_delta": lineage_delta,
        "transformation_delta": transformation_delta,
        "flow_delta": _delta(flow_before, flow_after, id_prefix="flow_delta", key_fields=["flow_kind", "source", "target", "entrypoint", "storage_target"]),
        "event_source_delta": _delta(event_before, event_after, id_prefix="event_source_delta", key_fields=["direction", "kind", "endpoint_path", "topic_name", "class_name", "method_name"]),
    }


def _summarize(changed_files: list[dict[str, Any]], deltas: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    file_lang = Counter(str(x.get("language") or "unknown") for x in changed_files)
    file_kind = Counter(str(x.get("change_kind") or "changed") for x in changed_files)
    delta_counts = {name: len(items) for name, items in deltas.items()}
    changed_semantic = sum(delta_counts.values())
    tests_changed = sum(1 for x in changed_files if x.get("is_test"))
    docs_changed = sum(1 for x in changed_files if x.get("is_documentation"))
    config_changed = sum(1 for x in changed_files if x.get("is_config"))
    sql_files_changed = sum(1 for x in changed_files if x.get("language") == "sql")

    complexity = min(100, 10 + len(changed_files) * 2 + delta_counts.get("lineage_delta", 0) * 8 + delta_counts.get("transformation_delta", 0) * 6 + delta_counts.get("column_delta", 0) * 3 + delta_counts.get("table_delta", 0) * 8)
    data_impact = min(100, delta_counts.get("table_delta", 0) * 15 + delta_counts.get("column_delta", 0) * 6 + delta_counts.get("lineage_delta", 0) * 10 + delta_counts.get("flow_delta", 0) * 8)
    risk = min(100, data_impact // 2 + delta_counts.get("relationship_delta", 0) * 10 + config_changed * 5 + (15 if sql_files_changed and not tests_changed else 0))

    complexity_metrics = {
        "changed_files": len(changed_files),
        "changed_files_by_language": dict(sorted(file_lang.items())),
        "changed_files_by_kind": dict(sorted(file_kind.items())),
        "delta_counts": delta_counts,
        "technical_complexity_score_hint": complexity,
        "data_impact_score_hint": data_impact,
        "risk_score_hint": risk,
        "score_policy": "Deterministic hints only; LLM profile must explain and may classify, but must not evaluate people.",
    }
    risk_signals = {
        "schema_changed": bool(delta_counts.get("table_delta") or delta_counts.get("column_delta") or delta_counts.get("relationship_delta")),
        "lineage_changed": bool(delta_counts.get("lineage_delta")),
        "transformation_changed": bool(delta_counts.get("transformation_delta")),
        "flow_changed": bool(delta_counts.get("flow_delta")),
        "config_changed": bool(config_changed),
        "tests_changed": bool(tests_changed),
        "docs_changed": bool(docs_changed),
        "missing_test_change_for_data_logic": bool((delta_counts.get("lineage_delta") or delta_counts.get("transformation_delta") or sql_files_changed) and not tests_changed),
        "review_attention_recommended": bool(risk >= 50 or data_impact >= 50 or complexity >= 70),
    }
    data_impact_summary = {
        "semantic_delta_items": changed_semantic,
        "tables_changed": delta_counts.get("table_delta", 0),
        "columns_changed": delta_counts.get("column_delta", 0),
        "relationships_changed": delta_counts.get("relationship_delta", 0),
        "lineage_edges_changed": delta_counts.get("lineage_delta", 0),
        "transformations_changed": delta_counts.get("transformation_delta", 0),
        "flows_changed": delta_counts.get("flow_delta", 0),
        "event_sources_changed": delta_counts.get("event_source_delta", 0),
    }
    test_doc_delta = {
        "tests_changed_count": tests_changed,
        "documentation_changed_count": docs_changed,
        "config_changed_count": config_changed,
        "test_files": [x for x in changed_files if x.get("is_test")][:200],
        "documentation_files": [x for x in changed_files if x.get("is_documentation")][:200],
        "config_files": [x for x in changed_files if x.get("is_config")][:200],
    }
    return complexity_metrics, risk_signals, data_impact_summary, test_doc_delta





def _write_standard_git_change_first_pass(
    *,
    out: Path,
    repo: Path,
    repo_id: str,
    project_code: str,
    system_name: str,
    metadata: dict[str, Any],
    diff_summary: dict[str, Any],
    complexity_metrics: dict[str, Any],
    risk_signals: dict[str, Any],
    data_impact_summary: dict[str, Any],
    coverage_delta: dict[str, Any],
    test_doc_delta: dict[str, Any],
    changed_files: list[dict[str, Any]],
    deltas: dict[str, list[dict[str, Any]]],
    change_metadata: dict[str, Any],
    evidence_views: list[str],
    snapshot_analyzer: str,
    static_profile_id: str | None,
) -> None:
    """Write the common repository analysis-output contract for git-change workspaces.

    Git-change is an analyzer frontend just like Java/SQL/spec.  The LLM pipeline
    should not need a special prompt path for it: every repo-scoped analysis_out
    must have a compact/first_pass.json and the usual manifest/core/diagnostics
    files.  Git-specific details remain accessible through the regular
    git_change_* evidence API views.
    """
    core_dir = out / "core"
    compact_dir = out / "compact"
    diagnostics_dir = out / "diagnostics"
    core_dir.mkdir(parents=True, exist_ok=True)
    compact_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    change_counts = complexity_metrics.get("delta_counts") or {}
    first_pass = {
        "artifact": "llm_first_pass_package",
        "format_version": "1.0",
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "capabilities": ["git_change_analysis"],
        "repo_id": repo_id,
        "project_code": project_code,
        "system_name": system_name,
        "change_metadata": change_metadata,
        "diff_summary": diff_summary,
        "complexity_metrics": complexity_metrics,
        "risk_signals": risk_signals,
        "data_impact_summary": data_impact_summary,
        "coverage_delta_summary": {
            "coverage_changed": bool(coverage_delta.get("coverage_changed")),
            "stage_delta_count": len(coverage_delta.get("stage_deltas") or []),
            "policy": coverage_delta.get("policy"),
        },
        "test_doc_config_summary": {k: v for k, v in test_doc_delta.items() if not k.endswith("files")},
        "representative_changed_files": changed_files[:100],
        "representative_deltas": {name: items[:50] for name, items in deltas.items()},
        "available_evidence_views": evidence_views,
        "analysis_contract": {
            "same_contract_as_repo_analysis": True,
            "first_pass_path": "compact/first_pass.json",
            "evidence_tool_mode": "runtime_views",
            "do_not_load_full_git_change_artifacts_into_prompt": True,
        },
        "policy": {
            "assess_change_not_person": True,
            "author_metadata_use": "traceability_only_not_scoring",
            "line_count_policy": "line_count_is_not_primary_complexity_measure",
            "primary_evidence": ["schema_delta", "lineage_delta", "transformation_delta", "flow_delta", "data_impact", "risk_signals"],
        },
        "limits": {
            "representative_changed_files": 100,
            "representative_deltas_per_kind": 50,
            "full_details_available_via_tools": True,
        },
    }
    navigation = {
        "artifact": "navigation",
        "format_version": "1.0",
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "repo_id": repo_id,
        "recommended_entrypoints": [
            {"command_id": "git_change_summary", "reason": "compact overview of change complexity/data impact evidence"},
            {"command_id": "git_change_metadata", "reason": "neutral author/committer/branch/MR traceability metadata"},
            {"command_id": "git_change_file_catalog", "reason": "changed file inventory"},
            {"command_id": "git_change_lineage_delta", "reason": "lineage changes"},
            {"command_id": "git_change_transformation_delta", "reason": "transformation changes"},
            {"command_id": "git_change_data_impact", "reason": "schema/table/column/data-impact deltas"},
            {"command_id": "git_change_risk_signals", "reason": "deterministic review-attention signals"},
            {"command_id": "git_change_coverage_delta", "reason": "evidence quality/coverage changes"},
        ],
        "evidence_views": evidence_views,
        "counts": {"changed_files": len(changed_files), **change_counts},
    }
    repository = {
        "artifact": "repository",
        "format_version": "1.0",
        "repo_id": repo_id,
        "repo_path": str(repo),
        "project_code": project_code,
        "system_name": system_name,
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "capabilities": ["git_change_analysis"],
        "snapshot_analyzer": snapshot_analyzer,
        "static_analysis_profile": static_profile_id,
        "change_metadata": change_metadata,
        "counts": {"changed_files": len(changed_files), **change_counts},
    }
    coverage = {
        "artifact": "evidence_coverage",
        "format_version": "1.0",
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "code_evidence_included": True,
        "source_inspection_available": False,
        "snapshot_analyzer": snapshot_analyzer,
        "static_analysis_profile": static_profile_id,
        "policy": "git_change_first_class_workspace_contract",
        "stages": {
            "git_change_analysis": {"status": "completed", "requested_by_profile": True},
            "before_snapshot_analysis": {"status": "completed", "requested_by_profile": True},
            "after_snapshot_analysis": {"status": "completed", "requested_by_profile": True},
            "before_after_delta_build": {"status": "completed", "requested_by_profile": True},
            "git_author_metadata": {"status": "completed", "requested_by_profile": True, "purpose": "traceability_only_not_scoring"},
        },
        "counts": {"changed_files": len(changed_files), **change_counts},
        "limitations": [
            {
                "limitation_type": "source_inspection_not_available_at_change_workspace_root",
                "description": "Git-change workspace exposes before/after snapshots and delta evidence views; root source inspection is not a primary evidence route.",
            }
        ],
        "coverage_delta": coverage_delta,
    }
    scanner_status = {
        "artifact": "scanner_status_summary",
        "format_version": "1.0",
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "status": "completed",
        "snapshot_analyzer": snapshot_analyzer,
        "stages": coverage["stages"],
    }

    write_json(compact_dir / "first_pass.json", first_pass)
    write_json(compact_dir / "navigation.json", navigation)
    write_json(core_dir / "repository.json", repository)
    write_json(out / "evidence_coverage.json", coverage)
    write_json(diagnostics_dir / "evidence_coverage.json", coverage)
    write_json(diagnostics_dir / "scanner_status_summary.json", scanner_status)
    write_json(diagnostics_dir / "scanner_status.json", scanner_status)


def _write_git_change_repository_index(
    *,
    workspace: Path,
    repo_id: str,
    repo_path: Path,
    project_code: str,
    system_name: str,
    run_id: str,
    counts: dict[str, Any],
    analysis_out: Path,
    change_metadata: dict[str, Any] | None = None,
    snapshot_analyzer: str | None = None,
    static_profile_id: str | None = None,
) -> None:
    record = {
        "repo_id": repo_id,
        "repo_path": str(repo_path),
        "system_name": system_name,
        "project_code": project_code,
        "profile": "git_change",
        "run_id": run_id,
        "analysis_out": str(analysis_out),
        "counts": counts,
        "change_metadata": change_metadata or {},
        "snapshot_analyzer": snapshot_analyzer,
        "static_profile_id": static_profile_id,
    }
    summary = {"repository_count": 1, "git_change_analyses_count": 1, "counts": counts}
    _write_git_change_repository_catalog(workspace, repo_id, record, summary)


def run_git_change_analysis(
    *,
    repo_path: str | Path,
    analysis_out: str | Path,
    from_ref: str | None = None,
    to_ref: str | None = None,
    commit: str | None = None,
    repo_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    analysis_profile: str | Path | None = None,
    change_id: str | None = None,
    change_type: str | None = None,
    source_branch: str | None = None,
    target_branch: str | None = None,
    reviewers: str | list[str] | tuple[str, ...] | None = None,
    max_packages: int = 80,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    out = Path(analysis_out).resolve()
    if not (repo / ".git").exists():
        # Support worktrees: ask git instead of requiring .git directory.
        _run_git(repo, ["rev-parse", "--git-dir"])
    if not analysis_profile:
        raise ValueError("analysis_profile is required for analyze-git-change")
    if commit:
        target_commit = _rev_parse(repo, commit, option_name="--commit")
        base_commit = _commit_parent(repo, target_commit)
        range_kind = "commit"
        base_ref = f"{commit}^"
        target_ref = commit
    else:
        if not from_ref or not to_ref:
            raise ValueError("Provide either --commit or both --from and --to")
        target_commit = _rev_parse(repo, to_ref, option_name="--to")
        base_commit = _rev_parse(repo, from_ref, option_name="--from")
        merge_base = _merge_base(repo, base_commit, target_commit)
        if merge_base and merge_base != base_commit:
            base_commit = merge_base
            range_kind = "merge_base_range"
        else:
            range_kind = "explicit_range"
        base_ref = from_ref
        target_ref = to_ref

    rid = normalize_name(repo_id or repo.name) or "repo"
    out.mkdir(parents=True, exist_ok=True)
    snapshots = out / "snapshots"
    before_snapshot = snapshots / "before"
    after_snapshot = snapshots / "after"
    _export_snapshot(repo, base_commit, before_snapshot)
    _export_snapshot(repo, target_commit, after_snapshot)

    git_dir = out / "git-change-evidence"
    git_dir.mkdir(parents=True, exist_ok=True)
    profile = load_analysis_profile(analysis_profile)
    snapshot_analyzer = _profile_snapshot_analyzer(profile)
    before_result, before_analysis_out = _run_snapshot_analysis(
        snapshot_analyzer=snapshot_analyzer,
        repo_path=before_snapshot,
        analysis_root=out / "before-analysis",
        run_id="before",
        analysis_profile=analysis_profile,
        repo_id=rid,
        project_code=project_code,
        system_name=system_name,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
    )
    after_result, after_analysis_out = _run_snapshot_analysis(
        snapshot_analyzer=snapshot_analyzer,
        repo_path=after_snapshot,
        analysis_root=out / "after-analysis",
        run_id="after",
        analysis_profile=analysis_profile,
        repo_id=rid,
        project_code=project_code,
        system_name=system_name,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
    )

    changed_files = _collect_changed_files(repo, base_commit, target_commit)
    hunks = _collect_hunks(repo, base_commit, target_commit)
    deltas = _build_deltas(before_analysis_out, after_analysis_out)
    coverage_delta = _build_coverage_delta(before_analysis_out, after_analysis_out)
    complexity_metrics, risk_signals, data_impact_summary, test_doc_delta = _summarize(changed_files, deltas)
    risk_signals["coverage_changed"] = bool(coverage_delta.get("coverage_changed"))
    change_metadata = _build_change_metadata(
        repo=repo,
        repo_id=rid,
        range_kind=range_kind,
        base_ref=base_ref,
        target_ref=target_ref,
        base_commit=base_commit,
        target_commit=target_commit,
        change_id=change_id,
        change_type=change_type,
        source_branch=source_branch,
        target_branch=target_branch,
        reviewers=reviewers,
    )

    metadata = {
        "artifact": "git_change_metadata",
        "artifact_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_id": rid,
        "repo_path": str(repo),
        "project_code": project_code,
        "system_name": system_name,
        "change_metadata": change_metadata,
        "snapshot_analyzer": snapshot_analyzer,
        "analysis_profile": {
            "profile_id": profile.get("profile_id"),
            "profile_version": profile.get("profile_version"),
            "profile_source": profile.get("_profile_source"),
        },
        "range": {
            "range_kind": range_kind,
            "base_ref": base_ref,
            "target_ref": target_ref,
            "base_commit": base_commit,
            "target_commit": target_commit,
            "base_commit_metadata": _commit_meta(repo, base_commit),
            "target_commit_metadata": _commit_meta(repo, target_commit),
        },
        "policy": {
            "purpose": "Assess complexity, risk, data impact and quality evidence of a code change, not engineer effectiveness.",
            "person_evaluation": "forbidden",
            "author_metadata_use": "metadata_only_not_scoring",
        },
        "analysis_outputs": {
            "before_analysis_out": str(before_analysis_out),
            "after_analysis_out": str(after_analysis_out),
            "git_change_evidence": str(git_dir),
        },
        "analysis_profile": str(Path(analysis_profile).resolve()),
    }

    diff_summary = {
        "artifact": "git_change_diff_summary",
        "change_metadata": change_metadata,
        "changed_files_count": len(changed_files),
        "changed_hunks_count": len(hunks),
        "changed_files_by_language": complexity_metrics["changed_files_by_language"],
        "changed_files_by_kind": complexity_metrics["changed_files_by_kind"],
        "semantic_delta_counts": complexity_metrics["delta_counts"],
    }

    llm_input = {
        "artifact": "llm_change_assessment_input",
        "metadata": metadata,
        "diff_summary": diff_summary,
        "complexity_metrics": complexity_metrics,
        "risk_signals": risk_signals,
        "data_impact_summary": data_impact_summary,
        "coverage_delta": coverage_delta,
        "test_doc_delta": {k: v for k, v in test_doc_delta.items() if not k.endswith("files")},
        "representative_changed_files": changed_files[:200],
        "representative_deltas": {name: items[:100] for name, items in deltas.items()},
        "rules_for_llm": [
            "Assess the change, not the person or author.",
            "Do not use line count as the primary complexity measure.",
            "Use before/after lineage, schema, transformation and flow deltas as primary data engineering evidence.",
            "If evidence is insufficient, request concrete git-change evidence views rather than inventing conclusions.",
        ],
    }

    write_json(git_dir / "git_change_metadata.json", metadata)
    facts_dir = out / "facts" / "facts_by_type"
    compact_dir = out / "compact"
    facts_dir.mkdir(parents=True, exist_ok=True)
    compact_dir.mkdir(parents=True, exist_ok=True)
    write_json(facts_dir / "git_change_metadata.json", change_metadata)
    write_json(compact_dir / "git_change_metadata.json", {"change_metadata": change_metadata})
    write_json(git_dir / "changed_file_catalog.json", changed_files)
    write_json(git_dir / "changed_hunk_catalog.json", hunks)
    write_json(git_dir / "diff_summary.json", diff_summary)
    write_json(git_dir / "before_after_analysis_refs.json", metadata["analysis_outputs"])
    for name, items in deltas.items():
        write_json(git_dir / f"{name}.json", items)
    write_json(git_dir / "test_doc_delta.json", test_doc_delta)
    write_json(git_dir / "before_after_coverage_delta.json", coverage_delta)
    write_json(git_dir / "complexity_metrics.json", complexity_metrics)
    write_json(git_dir / "risk_signals.json", risk_signals)
    write_json(git_dir / "data_impact_summary.json", data_impact_summary)
    write_json(git_dir / "llm_change_assessment_input.json", llm_input)
    counts = {
        "changed_files": len(changed_files),
        "changed_hunks": len(hunks),
        **complexity_metrics["delta_counts"],
    }
    evidence_views = [
        "git_change_metadata",
        "git_change_summary",
        "git_change_file_catalog",
        "git_change_file_detail",
        "git_change_lineage_delta",
        "git_change_transformation_delta",
        "git_change_data_impact",
        "git_change_coverage_delta",
        "git_change_risk_signals",
        "git_change_object_detail",
    ]
    write_json(out / "git_change_manifest.json", {
        "artifact": "git_change_manifest",
        "repo_id": rid,
        "range": metadata["range"],
        "change_metadata": change_metadata,
        "git_change_evidence": str(git_dir),
        "before_analysis_out": str(before_analysis_out),
        "after_analysis_out": str(after_analysis_out),
        "evidence_views": evidence_views,
        "counts": counts,
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "capabilities": ["git_change_analysis"],
    })
    _write_standard_git_change_first_pass(
        out=out,
        repo=repo,
        repo_id=rid,
        project_code=project_code,
        system_name=system_name,
        metadata=metadata,
        diff_summary=diff_summary,
        complexity_metrics=complexity_metrics,
        risk_signals=risk_signals,
        data_impact_summary=data_impact_summary,
        coverage_delta=coverage_delta,
        test_doc_delta=test_doc_delta,
        changed_files=changed_files,
        deltas=deltas,
        change_metadata=change_metadata,
        evidence_views=evidence_views,
        snapshot_analyzer=snapshot_analyzer,
        static_profile_id=profile.get("profile_id"),
    )

    repository_analysis_root = repository_analysis_root_for_static_output(out)
    repository_manifest = write_repository_analysis_manifest(
        repository_analysis_root=repository_analysis_root,
        repo_id=rid,
        source_repository_path=repo,
        static_analysis_output=out,
        analysis_scope="repository",
        static_profile=str(profile.get("profile_id") or "git-change-complexity-assessment"),
        run_id=str(change_id or target_commit or "git-change"),
        project_code=project_code,
        system_name=system_name,
        counts=counts,
    )
    repository_manifest_path = repository_analysis_root / "repository-analysis-manifest.json"

    write_json(out / "manifest.json", {
        "artifact": "analysis_output_manifest",
        "format_version": "1.0",
        "workspace_type": "git_change",
        "source_type": "git_change_analysis",
        "capabilities": ["git_change_analysis"],
        "analysis_profile": "git-change-complexity-assessment",
        "static_analysis_profile": profile.get("profile_id"),
        "repo_id": rid,
        "analysis_out": str(out),
        "repository_analysis_manifest": str(repository_manifest_path),
        "repository_manifest": repository_manifest,
        "git_change_evidence": str(git_dir),
        "evidence_views": evidence_views,
        "counts": counts,
        "change_metadata": change_metadata,
    })
    _write_git_change_repository_index(
        workspace=out,
        repo_id=rid,
        repo_path=repo,
        analysis_out=out,
        run_id="git-change",
        project_code=project_code,
        system_name=system_name,
        counts=counts,
        change_metadata=change_metadata,
        snapshot_analyzer=snapshot_analyzer,
        static_profile_id=profile.get("profile_id"),
    )
    return {
        "status": "ok",
        "analysis_out": str(out),
        "git_change_evidence": str(git_dir),
        "before_analysis_out": str(before_analysis_out),
        "after_analysis_out": str(after_analysis_out),
        "evidence_views": [
            "git_change_metadata",
            "git_change_summary",
            "git_change_file_catalog",
            "git_change_file_detail",
            "git_change_lineage_delta",
            "git_change_transformation_delta",
            "git_change_data_impact",
            "git_change_coverage_delta",
            "git_change_risk_signals",
            "git_change_object_detail",
        ],
        "counts": {
            "changed_files": len(changed_files),
            "changed_hunks": len(hunks),
            **complexity_metrics["delta_counts"],
        },
        "before_files_analyzed": _snapshot_files_analyzed(before_result),
        "after_files_analyzed": _snapshot_files_analyzed(after_result),
        "repository_analysis_manifest": str(repository_manifest_path),
        "repository_manifest": repository_manifest,
    }
