from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import re

from code_analyzer_core.models import AnalysisResult
from code_analyzer_core.scanners.repo_scanner import scan_files, detect_stack
from code_analyzer_core.scanners.config_scanner import scan_config_files
from code_analyzer_core.scanners.sql_scanner import scan_sql_files
from code_analyzer_core.scanners.python_scanner import scan_python_files
from code_analyzer_core.scanners.declared_value_scanner import scan_declared_values
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.prepared_artifacts.reference_data_fact_base import build_reference_data_fact_base
from code_analyzer_core.evidence_kernel import apply_strict_evidence_kernel
from code_analyzer_core.logging_utils import RunLogger
from code_analyzer_core.utils import normalize_name, write_json, read_text, line_number_for_offset
from code_analyzer_core.repository_contract import (
    now_utc,
    repo_id_from_path,
    safe_run_id,
    write_repository_analysis_manifest,
    repository_analysis_root_for_static_output,
)

CORE_VERSION = "0.23.7"
ANALYSIS_CONTRACT_VERSION = "1.0"
EVIDENCE_TOOL_CONTRACT_VERSION = "1.0"

COMMENT_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".properties", ".conf", ".sh"}
LINE_COMMENT_RE = re.compile(r"#(?P<shelltext>.*)$|--(?P<sqltext>.*)$", re.MULTILINE)
TRIPLE_STRING_RE = re.compile(r'(?P<q>"""|\'\'\')(?P<text>.*?)(?P=q)', re.DOTALL)


def _ensure_dirs(out: Path) -> dict[str, Path]:
    dirs = {
        "core": out / "core",
        "compact": out / "compact",
        "facts": out / "facts",
        "diagnostics": out / "diagnostics",
        "lazy": out / "lazy",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    (dirs["facts"] / "facts_by_type").mkdir(parents=True, exist_ok=True)
    return dirs


def _extract_source_comments(repo: Path, repo_id: str, out: Path) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for p in scan_files(repo):
        if p.suffix.lower() not in COMMENT_SUFFIXES:
            continue
        try:
            text = read_text(p)
        except Exception:
            continue
        try:
            rel = str(p.relative_to(repo)).replace("\\", "/")
        except Exception:
            rel = str(p)
        for m in LINE_COMMENT_RE.finditer(text):
            body = (m.group("shelltext") or m.group("sqltext") or "").strip()
            if not body or body.startswith(("type:", "noqa", "pylint")):
                continue
            line = line_number_for_offset(text, m.start())
            comments.append({
                "repo_id": repo_id,
                "comment_id": f"comment_{repo_id}_{len(comments)+1:06d}",
                "file": str(p),
                "relative_file": rel,
                "line_start": line,
                "line_end": line,
                "comment_type": "line",
                "comment_text": body[:2000],
                "attached_to": "nearby_code",
            })
        if p.suffix.lower() == ".py":
            for m in TRIPLE_STRING_RE.finditer(text):
                body = " ".join((m.group("text") or "").strip().split())
                if not body:
                    continue
                line = line_number_for_offset(text, m.start())
                comments.append({
                    "repo_id": repo_id,
                    "comment_id": f"comment_{repo_id}_{len(comments)+1:06d}",
                    "file": str(p),
                    "relative_file": rel,
                    "line_start": line,
                    "line_end": line + m.group(0).count("\n"),
                    "comment_type": "docstring_or_triple_string",
                    "comment_text": body[:2000],
                    "attached_to": "nearby_code",
                    })
    facts_dir = out / "facts" / "facts_by_type"
    facts_dir.mkdir(parents=True, exist_ok=True)
    write_json(facts_dir / "source_comment.json", comments)
    return comments


def run_python_analysis(
    repo_path: str | Path,
    out_dir: str | Path,
    project_code: str,
    system_name: str,
    max_packages: int = 500,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
) -> AnalysisResult:
    repo = Path(repo_path).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    dirs = _ensure_dirs(out)
    diagnostics_dir = dirs["diagnostics"]
    core_dir = dirs["core"]
    facts_dir = dirs["facts"]
    logger = RunLogger(diagnostics_dir, verbose=verbose)
    started_at = now_utc()

    logger.start("scan_files", f"Scanning Python repository {repo}")
    files = scan_files(repo)
    stack = detect_stack(files)
    logger.done("scan_files", f"Files found: {len(files)}", stack=stack)

    result = AnalysisResult(
        system_name=system_name,
        project_code=project_code,
        repo_path=str(repo),
        stack=stack,
        files_analyzed=len(files),
    )

    logger.start("config_scan", "Extracting config facts")
    result.config_facts = scan_config_files(files)
    logger.done("config_scan", f"Config facts: {len(result.config_facts)}")

    logger.start("python_ast_scan", "Extracting Python source evidence")
    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_python_files(files)
    result.facts.extend(facts)
    result.schemas.extend(schemas)
    result.interfaces.extend(interfaces)
    result.relations.extend(relations)
    result.mapper_facts.extend(mapper_facts)
    result.warnings.extend(warnings)
    write_json(diagnostics_dir / "python_parse_warnings.json", warnings)
    logger.done("python_ast_scan", f"facts={len(facts)}, schemas={len(schemas)}, interfaces={len(interfaces)}, relations={len(relations)}")

    logger.start("sql_scan", "Extracting embedded SQL facts")
    sql_facts, sql_summary, sql_warnings = scan_sql_files(files)
    result.facts.extend(sql_facts)
    write_json(diagnostics_dir / "sql_parse_summary.json", sql_summary)
    write_json(diagnostics_dir / "sql_parse_warnings.json", sql_warnings)
    logger.done("sql_scan", f"sql_facts={len(sql_facts)}, failed={sql_summary.get('failed')}, fallback={sql_summary.get('regex_fallback')}")

    logger.start("declared_value_scan", "Extracting explicitly declared value sets without semantic classification")
    declared_value_facts, declared_value_status = scan_declared_values(files)
    result.facts.extend(declared_value_facts)
    result.coverage["declared_value_scan"] = declared_value_status
    write_json(diagnostics_dir / "declared_value_scan_status.json", declared_value_status)
    logger.done("declared_value_scan", f"declared value facts={len(declared_value_facts)}, sets={declared_value_status.get('value_sets_extracted')}")

    result.coverage["python_ast"] = {
        "enabled": True,
        "mode": "source_only_no_build_required",
        "warnings": len(warnings),
    }
    result.coverage["low_level_facts"] = {
        "mode": "lazy_only",
        "global_extraction": False,
        "message": "Detailed/low-level evidence is produced only by explicit evidence tools API requests.",
    }

    logger.start("core_output", "Writing slim machine-first core output")
    write_json(core_dir / "repository.json", {
        "system_name": result.system_name,
        "project_code": result.project_code,
        "repo_path": result.repo_path,
        "stack": result.stack,
        "files_analyzed": result.files_analyzed,
    })
    logger.done("core_output", "Slim core JSON output written")

    logger.start("normalized_fact_store", "Writing slim normalized fact indexes")
    apply_strict_evidence_kernel(result)
    normalized_summary = write_normalized_fact_store(result, facts_dir)
    result.coverage["normalized_facts"] = normalized_summary
    logger.done("normalized_fact_store", f"normalized facts={normalized_summary.get('fact_count')}, persisted={normalized_summary.get('persisted_fact_count')}")

    logger.start("reference_data_fact_base", "Writing facts-only declared-value and storage evidence package")
    reference_data_fact_base_status = build_reference_data_fact_base(result=result, out_dir=out)
    result.coverage["reference_data_fact_base"] = reference_data_fact_base_status
    write_json(diagnostics_dir / "reference_data_fact_base_status.json", reference_data_fact_base_status)
    logger.done("reference_data_fact_base", "Facts-only declared-value and storage evidence package written")

    logger.start("compact_navigation", "Writing compact machine-first navigation")
    navigation = build_navigation(result, out, max_items=max_packages, max_fields_per_schema=max_fields_per_schema)
    logger.done("compact_navigation", "Navigation JSON written")

    trace_items = navigation.get("traces") or []
    counts = {
        "config_facts": len(result.config_facts),
        "facts": len(result.facts),
        "interfaces": len(result.interfaces),
        "schemas": len(result.schemas),
        "mapper_facts": len(result.mapper_facts),
        "relations": len(result.relations),
        "normalized_facts": normalized_summary.get("fact_count"),
        "evidence": normalized_summary.get("evidence_count"),
        "python_ingress": len(navigation.get("ingress") or []),
        "python_data_flows": len(navigation.get("data_flows") or []),
        "python_storage_accesses": len(navigation.get("storage_accesses") or []),
        "python_traces": len(trace_items),
        "trace_status_counts": navigation.get("counts", {}).get("trace_status_counts"),
        "trace_type_counts": navigation.get("counts", {}).get("trace_type_counts"),
        "declared_value_sets": declared_value_status.get("value_sets_extracted"),
        "declared_values": declared_value_status.get("values_extracted"),
        "declared_value_sets_by_syntax_kind": declared_value_status.get("by_syntax_kind"),
        "reference_data_fact_base": reference_data_fact_base_status.get("summary"),
    }
    write_json(diagnostics_dir / "run.json", {
        "started_at": started_at,
        "finished_at": now_utc(),
        "status": "success",
        "system_name": system_name,
        "project_code": project_code,
        "repo_path": str(repo),
        "core_version": CORE_VERSION,
        "stack": stack,
        "files_analyzed": len(files),
        "counts": counts,
        "prepared_artifacts": {
            "reference_data_fact_base": reference_data_fact_base_status,
        },
    })
    write_json(diagnostics_dir / "scanner_status.json", {
        "python_ast": result.coverage["python_ast"],
        "sql": sql_summary,
        "low_level_facts": result.coverage["low_level_facts"],
        "reference_data_fact_base": reference_data_fact_base_status,
    })
    write_json(out / "manifest.json", {
        "artifact": "analysis-output",
        "analysis_output_contract_version": ANALYSIS_CONTRACT_VERSION,
        "evidence_tool_contract_version": EVIDENCE_TOOL_CONTRACT_VERSION,
        "core_version": CORE_VERSION,
        "created_by": "code-analyzer-core",
        "created_at": started_at,
        "analysis_scope": "repository",
        "repo_path": str(repo),
        "repo_id": repo_id_from_path(repo, None),
        "static_analysis_output": str(out),
        "workspace_type": "python",
        "system_name": system_name,
        "project_code": project_code,
        "output_policy": "machine_first_slim_json_lazy_evidence_human_views_external",
        "evidence_provider": {
            "access_api": "code_evidence.access",
            "capabilities": ["operation", "interface", "schema", "symbol", "callable", "field", "search", "relation", "query", "lineage", "show", "flow", "ingress", "trace", "storage-access", "declared-value-set", "declared-value-set-summary", "literal-data-write", "reference-data-fact-base", "facts-by-type"],
        },
        "counts": counts,
        "prepared_artifacts": {
            "reference_data_fact_base": reference_data_fact_base_status,
        },
    })
    logger.done("analysis", "Python analysis completed", out_dir=str(out))
    return result

def run_python_repository_analysis(
    repo_path: str | Path,
    analysis_out: str | Path,
    repo_id: str | None = None,
    project_code: str = "UNKNOWN",
    system_name: str = "unknown-system",
    run_id: str | None = None,
    max_packages: int = 80,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_path).resolve()
    rid = repo_id_from_path(repo, repo_id)
    rid_run = safe_run_id(run_id)
    out = Path(analysis_out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = run_python_analysis(repo, out, project_code, system_name, max_packages=max_packages, max_fields_per_schema=max_fields_per_schema, verbose=verbose)
    source_comments = _extract_source_comments(repo, rid, out)
    counts = {"comments": len(source_comments), "interfaces": len(result.interfaces), "schemas": len(result.schemas), "facts": len(result.facts), "relations": len(result.relations), "files_analyzed": result.files_analyzed}
    latest = {"repo_id": rid, "repo_path": str(repo), "system_name": system_name, "project_code": project_code, "profile": "python", "workspace_type": "python", "run_id": rid_run, "static_analysis_output": str(out), "analysis_out": str(out), "updated_at": now_utc(), "counts": counts}
    repo_manifest = write_repository_analysis_manifest(repository_analysis_root=repository_analysis_root_for_static_output(out), repo_id=rid, source_repository_path=repo, static_analysis_output=out, static_profile="python", run_id=rid_run, project_code=project_code, system_name=system_name, counts=counts)
    return {"repo": latest, "repository_analysis_manifest": repo_manifest, "analysis_out": str(out), "static_analysis_output": str(out)}
