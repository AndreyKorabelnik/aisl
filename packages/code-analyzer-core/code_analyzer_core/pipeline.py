from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from datetime import datetime, timezone
import gc
import shutil
import time

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.models import AnalysisResult, Fact, EvidenceRef
from code_analyzer_core.scanners.repo_scanner import scan_files, detect_stack
from code_analyzer_core.scanners.config_scanner import scan_config_files
from code_analyzer_core.scanners.openapi_scanner import scan_openapi_files
from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.scanners.java_interaction_enrichment import scan_java_system_interaction_evidence, scan_maven_dependencies
from code_analyzer_core.scanners.gradle_scanner import scan_gradle_dependencies
from code_analyzer_core.scanners.java_syntax import tree_sitter_available, JAVA_SYNTAX_PROVIDER, clear_java_syntax_cache, java_syntax_cache_stats
from code_analyzer_core.scanners.data_model_candidate_scanner import scan_data_model_candidate
from code_analyzer_core.scanners.java_source_observations import build_java_source_observation_facts
from code_analyzer_core.scanners.java_module_resolution import build_java_module_resolution_facts
from code_analyzer_core.tsa_interpreter import interpret_tsa_facts
from code_analyzer_core.scanners.sql_scanner import scan_sql_files
from code_analyzer_core.scanners.db_schema_scanner import scan_database_schema
from code_analyzer_core.scanners.sql_table_observations import scan_sql_table_observations
from code_analyzer_core.scanners.java_table_observations import scan_java_table_observations
from code_analyzer_core.scanners.java_flow_builder import build_java_data_flow_facts
from code_analyzer_core.scanners.java_field_flow_builder import build_java_field_flow_facts
from code_analyzer_core.scanners.java_trace_builder import build_java_traceability_facts, build_java_persistence_lineage_facts, build_java_data_model_lineage_facts
from code_analyzer_core.scanners.declared_value_scanner import scan_declared_values, scan_declared_value_summaries, summarize_declared_value_facts
from code_analyzer_core.scanners.system_description_enrichment import build_system_description_enrichment_facts
from code_analyzer_core.normalizer import write_normalized_fact_store
from code_analyzer_core.navigation import build_navigation
from code_analyzer_core.evidence_kernel import apply_strict_evidence_kernel
from code_analyzer_core.logging_utils import RunLogger
from code_analyzer_core.utils import write_json
from code_analyzer_core.determinism import canonicalize_fact_order
from code_analyzer_core.analysis_profiles import (
    load_analysis_fragment,
    load_analysis_profile,
    profile_stage_entries,
    profile_stage_ids,
)
from code_analyzer_core.prepared_artifacts.reference_data_fact_base import build_reference_data_fact_base
from code_analyzer_core.foundation_artifact import (
    hydrate_foundation_result,
    load_foundation_artifact,
    load_foundation_optional_sections,
    write_foundation_artifact,
)
from code_analyzer_core.prepared_artifacts.source_observation_fact_store import (
    bounded_source_observation_preview,
    write_source_observation_fact_store,
)

ANALYSIS_CONTRACT_VERSION = "1.0"
EVIDENCE_TOOL_CONTRACT_VERSION = "1.0"


def _db_schema_item_name(item: dict[str, Any]) -> str:
    for key in ("qualified_table_name", "source_qualified_table_name", "table_name", "column_name", "constraint_name", "index_name", "sequence_name", "relationship_constant"):
        value = item.get(key)
        if value:
            if key == "column_name" and item.get("table_name"):
                return f"{item.get('table_name')}.{value}"
            return str(value)
    return str(item.get("fact_type") or "db_schema_fact")


def _db_schema_evidence_refs(item: dict[str, Any]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for raw in item.get("evidence") or []:
        if not isinstance(raw, dict):
            continue
        file_path = raw.get("file") or raw.get("file_path") or item.get("file")
        if not file_path:
            continue
        refs.append(EvidenceRef(
            file_path=str(file_path),
            line_start=raw.get("line_start") or item.get("line_start"),
            line_end=raw.get("line_end") or item.get("line_end"),
            extractor=str(raw.get("kind") or item.get("source_type") or "db_schema_scanner"),
        ))
    if not refs and item.get("file"):
        refs.append(EvidenceRef(
            file_path=str(item.get("file")),
            line_start=item.get("line_start"),
            extractor=str(item.get("source_type") or "db_schema_scanner"),
        ))
    return refs


def _db_schema_items_to_facts(db_schema: dict[str, Any]) -> list[Fact]:
    facts: list[Fact] = []
    for group in (
        "tables", "columns", "keys", "relationships", "indexes", "sequences",
        "constraints", "partitioning", "triggers", "schema_changes",
        "historical_schema_facts", "literal_data_writes",
    ):
        for item in db_schema.get(group) or []:
            if not isinstance(item, dict):
                continue
            if group == "historical_schema_facts":
                fact_type = "db_schema_historical_fact"
            else:
                fact_type = str(item.get("fact_type") or f"db_schema_{group[:-1]}")
            props = dict(item)
            if group == "historical_schema_facts":
                props.setdefault("original_fact_type", item.get("fact_type"))
            props.pop("evidence", None)
            facts.append(Fact(
                fact_type=fact_type,
                name=_db_schema_item_name(item),
                properties=props,
                evidence=_db_schema_evidence_refs(item),
            ))
    return facts


def _write_db_schema_artifacts(out: Path, db_schema: dict[str, Any]) -> None:
    sql_dir = out / "sql"
    compact_dir = out / "compact"
    sql_dir.mkdir(parents=True, exist_ok=True)
    compact_dir.mkdir(parents=True, exist_ok=True)
    write_json(sql_dir / "db_schema_overview.json", db_schema.get("overview") or {})
    write_json(sql_dir / "db_schema_tables.json", db_schema.get("tables") or [])
    write_json(sql_dir / "db_schema_columns.json", db_schema.get("columns") or [])
    write_json(sql_dir / "db_schema_keys.json", db_schema.get("keys") or [])
    write_json(sql_dir / "db_schema_relationships.json", db_schema.get("relationships") or [])
    write_json(sql_dir / "db_schema_indexes.json", db_schema.get("indexes") or [])
    write_json(sql_dir / "db_schema_sequences.json", db_schema.get("sequences") or [])
    write_json(sql_dir / "db_schema_constraints.json", db_schema.get("constraints") or [])
    write_json(sql_dir / "db_schema_partitioning.json", db_schema.get("partitioning") or [])
    write_json(sql_dir / "db_schema_triggers.json", db_schema.get("triggers") or [])
    write_json(sql_dir / "db_schema_changes.json", db_schema.get("schema_changes") or [])
    write_json(sql_dir / "db_schema_historical_tables.json", db_schema.get("historical_tables") or [])
    write_json(sql_dir / "db_schema_historical_facts.json", db_schema.get("historical_schema_facts") or [])
    write_json(sql_dir / "literal_data_writes.json", db_schema.get("literal_data_writes") or [])
    write_json(compact_dir / "db_schema_overview.json", db_schema.get("overview") or {})
    write_json(compact_dir / "db_schema_tables.json", db_schema.get("tables") or [])
    write_json(compact_dir / "db_schema_columns.json", db_schema.get("columns") or [])
    write_json(compact_dir / "db_schema_keys.json", db_schema.get("keys") or [])
    write_json(compact_dir / "db_schema_relationships.json", db_schema.get("relationships") or [])
    write_json(compact_dir / "db_schema_indexes.json", db_schema.get("indexes") or [])
    write_json(compact_dir / "db_schema_sequences.json", db_schema.get("sequences") or [])
    write_json(compact_dir / "db_schema_constraints.json", db_schema.get("constraints") or [])
    write_json(compact_dir / "db_schema_partitioning.json", db_schema.get("partitioning") or [])
    write_json(compact_dir / "db_schema_triggers.json", db_schema.get("triggers") or [])
    write_json(compact_dir / "db_schema_changes.json", db_schema.get("schema_changes") or [])
    write_json(compact_dir / "db_schema_historical_tables.json", db_schema.get("historical_tables") or [])
    write_json(compact_dir / "db_schema_historical_facts.json", db_schema.get("historical_schema_facts") or [])
    write_json(compact_dir / "literal_data_writes.json", db_schema.get("literal_data_writes") or [])


def _merge_data_model_observations(*parts: dict[str, Any]) -> dict[str, Any]:
    relationships: dict[str, dict[str, Any]] = {}
    keys: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    for part in parts:
        for item in part.get("relationships") or []:
            if isinstance(item, dict) and item.get("observation_id"):
                relationships[str(item["observation_id"])] = item
        for item in part.get("keys") or []:
            if isinstance(item, dict) and item.get("observation_id"):
                keys[str(item["observation_id"])] = item
        warnings.extend(item for item in (part.get("warnings") or []) if isinstance(item, dict))
    relationship_counts: dict[str, int] = {}
    relationship_source_counts: dict[str, int] = {}
    for item in relationships.values():
        kind = str(item.get("relation_kind") or "unknown")
        source = str(item.get("source_kind") or "unknown")
        relationship_counts[kind] = relationship_counts.get(kind, 0) + 1
        relationship_source_counts[source] = relationship_source_counts.get(source, 0) + 1
    key_counts: dict[str, int] = {}
    for item in keys.values():
        kind = str(item.get("key_kind") or "unknown")
        key_counts[kind] = key_counts.get(kind, 0) + 1
    return {
        "relationships": list(relationships.values()),
        "keys": list(keys.values()),
        "overview": {
            "status": "completed",
            "relationship_observations": len(relationships),
            "key_observations": len(keys),
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "relationship_source_counts": dict(sorted(relationship_source_counts.items())),
            "key_counts": dict(sorted(key_counts.items())),
            "facts_only_policy": "declared and observed relationship/key facts remain separate; no confidence, cardinality, semantic equivalence, or verdict",
        },
        "warnings": warnings,
    }


def _write_data_model_observation_artifacts(out: Path, observations: dict[str, Any]) -> None:
    sql_dir = out / "sql"
    compact_dir = out / "compact"
    sql_dir.mkdir(parents=True, exist_ok=True)
    compact_dir.mkdir(parents=True, exist_ok=True)
    for directory in (sql_dir, compact_dir):
        write_json(directory / "table_relationship_observations.json", observations.get("relationships") or [])
        write_json(directory / "table_key_observations.json", observations.get("keys") or [])
        write_json(directory / "table_observation_overview.json", observations.get("overview") or {})
    write_json(out / "diagnostics" / "table_observation_warnings.json", observations.get("warnings") or [])


def _ensure_dirs(out: Path) -> dict[str, Path]:
    dirs = {
        "core": out / "core",
        "compact": out / "compact",
        "facts": out / "facts",
        "diagnostics": out / "diagnostics",
        "lazy": out / "lazy",
        "sql": out / "sql",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    (dirs["facts"] / "facts_by_type").mkdir(parents=True, exist_ok=True)
    return dirs


def _status_has_failure(status: dict[str, Any], *, strict_warnings: bool = True) -> bool:
    if not isinstance(status, dict):
        return True
    if status.get("errors") or status.get("invalid_rule_files"):
        return True
    if strict_warnings and (status.get("run_warnings") or status.get("environment_warnings")):
        return True
    if status.get("exit_code") not in (None, 0, 1):
        return True
    return False


def _fail(stage: str, status: dict[str, Any], diagnostics_dir: Path) -> None:
    write_json(diagnostics_dir / f"{stage}_failure.json", status)
    errors = status.get("errors") or status.get("invalid_rule_files") or status.get("run_warnings") or status.get("environment_warnings") or []
    raise RuntimeError(f"{stage} failed; see diagnostics/{stage}_status.json and diagnostics/{stage}_failure.json. First error: {errors[:1]}")



def _stage_status(stage_id: str, stage_set: set[str], coverage: dict[str, Any], *, key: str | None = None) -> dict[str, Any]:
    cov_key = key or stage_id
    data = coverage.get(cov_key)
    requested = stage_id in stage_set
    if isinstance(data, dict):
        status = "success"
        if data.get("status"):
            status = str(data.get("status"))
        elif data.get("coverage_status"):
            status = str(data.get("coverage_status"))
        elif data.get("errors"):
            status = "failed"
        return {"requested_by_profile": requested, "status": status, **data}
    return {"requested_by_profile": requested, "status": "not_run_by_profile"}


def _build_evidence_coverage(
    *,
    stage_set: set[str],
    result: AnalysisResult,
    sql_summary: dict[str, Any],
    db_schema_status: dict[str, Any],
    openapi_status: dict[str, Any],
    interaction_status: dict[str, Any],
    maven_dependency_status: dict[str, Any],
    gradle_dependency_status: dict[str, Any],
    java_source_observation_status: dict[str, Any],
    source_observation_fact_store_status: dict[str, Any],
    flow_status: dict[str, Any],
    field_flow_status: dict[str, Any],
    trace_status: dict[str, Any],
    persistence_lineage_status: dict[str, Any],
    data_model_lineage_status: dict[str, Any],
    declared_value_status: dict[str, Any],
    declared_value_summary_status: dict[str, Any],
    counts: dict[str, Any],
) -> dict[str, Any]:
    coverage = result.coverage or {}
    stages = {
        "scan_files": {"requested_by_profile": True, "status": "success", "files_analyzed": result.files_analyzed},
        "config_scan": {"requested_by_profile": "config_scan" in stage_set, "status": "success" if "config_scan" in stage_set else "not_run_by_profile", "facts_extracted": len(result.config_facts)},
        "maven_dependency_scan": {"requested_by_profile": "maven_dependency_scan" in stage_set, "status": str(maven_dependency_status.get("status") or ("success" if maven_dependency_status.get("requested") else "not_run_by_profile")), **(maven_dependency_status or {})},
        "gradle_dependency_scan": {"requested_by_profile": "gradle_dependency_scan" in stage_set, "status": str(gradle_dependency_status.get("status") or ("success" if gradle_dependency_status.get("requested") else "not_run_by_profile")), **(gradle_dependency_status or {})},
        "java_structural_scan": {"requested_by_profile": "java_structural_scan" in stage_set, "status": "success" if "java_structural_scan" in stage_set else "not_run_by_profile", "syntax_provider": coverage.get("java_syntax_provider") or JAVA_SYNTAX_PROVIDER, "syntax_cache": coverage.get("java_syntax_cache") or {}},
        "java_system_interaction_enrichment": {"requested_by_profile": "java_system_interaction_enrichment" in stage_set, "status": "success" if interaction_status.get("requested") else "not_run_by_profile", **(interaction_status or {})},
        "java_source_observation_build": {"requested_by_profile": "java_source_observation_build" in stage_set, "status": str(java_source_observation_status.get("status") or ("success" if java_source_observation_status.get("requested") else "not_run_by_profile")), **(java_source_observation_status or {})},
        "source_observation_fact_store": {"requested_by_profile": "java_source_observation_build" in stage_set or "maven_dependency_scan" in stage_set or "gradle_dependency_scan" in stage_set or "config_scan" in stage_set, "status": str(source_observation_fact_store_status.get("status") or "not_run_by_profile"), **(source_observation_fact_store_status or {})},
        "sql_scan": {"requested_by_profile": "sql_scan" in stage_set, "status": "success" if "sql_scan" in stage_set else "not_run_by_profile", **(sql_summary or {})},
        "openapi_scan": {"requested_by_profile": "openapi_scan" in stage_set, "status": "success" if openapi_status.get("requested") else "not_run_by_profile", **(openapi_status or {})},
        "db_schema_scan": _stage_status("db_schema_scan", stage_set, coverage, key="db_schema"),
        "java_data_flow_build": {"requested_by_profile": "java_data_flow_build" in stage_set, "status": "success" if flow_status.get("requested") else "not_run_by_profile", **(flow_status or {})},
        "java_field_flow_build": {"requested_by_profile": "java_field_flow_build" in stage_set, "status": "success" if field_flow_status.get("requested") else "not_run_by_profile", **(field_flow_status or {})},
        "java_traceability_build": {"requested_by_profile": "java_traceability_build" in stage_set, "status": "success" if trace_status.get("requested") else "not_run_by_profile", **(trace_status or {})},
        "java_persistence_lineage_build": {"requested_by_profile": "java_persistence_lineage_build" in stage_set, "status": "success" if persistence_lineage_status.get("requested") else "not_run_by_profile", **(persistence_lineage_status or {})},
        "java_data_model_lineage_build": {"requested_by_profile": "java_data_model_lineage_build" in stage_set, "status": "success" if data_model_lineage_status.get("requested") else "not_run_by_profile", **(data_model_lineage_status or {})},
        "declared_value_scan": {"requested_by_profile": "declared_value_scan" in stage_set, "status": "success" if declared_value_status.get("requested") else "not_run_by_profile", **(declared_value_status or {})},
        "declared_value_summary_scan": {"requested_by_profile": "declared_value_summary_scan" in stage_set, "status": "success" if declared_value_summary_status.get("requested") else "not_run_by_profile", **(declared_value_summary_status or {})},
        "reference_data_fact_base": {"requested_by_profile": True, "status": str((result.coverage.get("reference_data_fact_base") or {}).get("status") or "success"), **(result.coverage.get("reference_data_fact_base") or {})},
    }
    heavy = coverage.get("heavy_tools") or {
        "spoon_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
        "semgrep_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
        "targeted_semgrep_scan": {"status": "removed_from_fast_core", "requested_by_profile": False},
    }
    limitations = []
    for tool_id, info in heavy.items():
        limitations.append({
            "component": tool_id,
            "status": info.get("status"),
            "impact": info.get("impact"),
            "gap_type": "analysis_method_removed_from_fast_core",
        })
    if db_schema_status.get("requested") and not db_schema_status.get("tables_extracted"):
        limitations.append({
            "component": "db_schema_scan",
            "status": "success_no_schema_sources",
            "gap_type": "physical_schema_not_observed",
            "impact": "No schema-bearing sources were detected; physical model may rely on SQL/Java inference only",
        })
    return {
        "artifact": "evidence_coverage",
        "format_version": "1.0",
        "policy": "fast_evidence_core_no_spoon_no_semgrep",
        "heavy_tools": heavy,
        "stages": stages,
        "counts": counts,
        "limitations": limitations,
        "llm_guidance": [
            "Do not assume Spoon/Semgrep evidence exists; they are removed from the fast core.",
            "Use SQL, DB schema, config, lightweight Java, custom lineage and compact prepared artifacts as primary evidence.",
            "When deep Java AST details are missing, return explicit gaps or request source-inspect drilldown instead of inventing details.",
        ],
    }



def _run_analysis_impl(
    repo_path: str | Path,
    out_dir: str | Path,
    project_code: str,
    system_name: str,
    max_packages: int = 500,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
    analysis_profile: str | Path | Mapping[str, Any] | None = None,
    repo_id: str | None = None,
    fp_id: str | None = None,
    fp_name: str | None = None,
    foundation_input: str | Path | None = None,
    foundation_output: str | Path | None = None,
    foundation_only: bool = False,
) -> AnalysisResult:
    """Run the machine-first static analysis pipeline.

    Clean policy:
    - no human-readable markdown output is generated by default;
    - no global low-level/eager fact extraction;
    - no LLM prompts or business interpretation;
    - output is JSON/JSONL-oriented and evidence is retrieved lazily through the evidence access API.
    """
    repo = Path(repo_path).resolve()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    dirs = _ensure_dirs(out)
    diagnostics_dir = dirs["diagnostics"]
    scanner_tmp_dir = out / ".scanner-tmp"
    scanner_tmp_dir.mkdir(parents=True, exist_ok=True)
    core_dir = dirs["core"]
    facts_dir = dirs["facts"]

    logger = RunLogger(diagnostics_dir, verbose=verbose)
    started_at = datetime.now(timezone.utc).isoformat()
    logger.start("profile_load", "Loading analysis profile")
    if isinstance(analysis_profile, Mapping):
        profile = dict(analysis_profile)
        profile.setdefault("_profile_source", "internal-evidence-analyzer")
    else:
        profile = (
            load_analysis_fragment(analysis_profile)
            if foundation_only
            else load_analysis_profile(analysis_profile)
        )
    stage_ids = profile_stage_ids(profile)
    logger.done(
        "profile_load",
        "Analysis profile loaded",
        profile_id=profile.get("profile_id"),
        stages_count=len(stage_ids),
    )
    stage_set = set(stage_ids)
    stage_options = {
        str(item.get("id")): (item.get("options") or {})
        for item in profile_stage_entries(profile)
        if isinstance(item, dict) and item.get("id")
    }
    if "scan_files" not in stage_set:
        raise RuntimeError("analysis profile must include scan_files as the first technical stage")

    logger.start(
        "analysis",
        "Static analysis started",
        repo_id=repo_id or repo.name,
        profile_id=profile.get("profile_id"),
        stages_count=len(stage_ids),
    )

    status: dict[str, Any] = {
        "started_at": started_at,
        "system_name": system_name,
        "project_code": project_code,
        "repo_path": str(repo),
        "repo_id": repo_id or repo.name,
        "core_version": CORE_VERSION,
        "analysis_profile": {
            "profile_id": profile.get("profile_id"),
            "profile_version": profile.get("profile_version"),
            "name": profile.get("name"),
            "stages": stage_ids,
            "profile_source": profile.get("_profile_source"),
        },
        "policy": "strict_evidence_contract_no_business_risk_decision",
        "stages": [],
    }

    logger.start("scan_files", f"Scanning repository {repo}")
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

    sql_summary: dict[str, Any] = {}
    sql_warnings: list[Any] = []
    flow_status: dict[str, Any] = {"requested": False}
    field_flow_status: dict[str, Any] = {"requested": False}
    trace_status: dict[str, Any] = {"requested": False}
    persistence_lineage_status: dict[str, Any] = {"requested": False}
    data_model_lineage_status: dict[str, Any] = {"requested": False}
    declared_value_status: dict[str, Any] = {"requested": False}
    declared_value_summary_status: dict[str, Any] = {"requested": False}
    system_description_status: dict[str, Any] = {"requested": False, "status": "not_run_by_profile"}
    reference_data_fact_base_status: dict[str, Any] = {"requested": False, "status": "not_run_by_profile"}
    db_schema_status: dict[str, Any] = {"requested": False}
    openapi_status: dict[str, Any] = {"requested": False}
    interaction_status: dict[str, Any] = {"requested": False}
    maven_dependency_status: dict[str, Any] = {"requested": False}
    gradle_dependency_status: dict[str, Any] = {"requested": False}
    gradle_facts: list[Fact] = []
    java_source_observation_status: dict[str, Any] = {"requested": False}
    tsa_interpreter_status: dict[str, Any] = {"requested": False, "status": "not_run_by_profile"}
    source_observation_fact_store_status: dict[str, Any] = {"requested": False, "status": "not_run_by_profile"}
    db_schema: dict[str, Any] = {}
    table_observations: dict[str, Any] = {"relationships": [], "keys": [], "overview": {}, "warnings": []}
    flow_facts: list[Any] = []
    foundation_reuse_status: dict[str, Any] = {"status": "not_requested"}
    foundation_deferred_sections: dict[str, Any] = {"loaded": True}
    foundation_optional_sections: dict[str, Any] = {"loaded": True, "payload": {}}
    foundation_reused = foundation_input is not None

    if foundation_reused:
        logger.start("foundation_reuse", "Loading reusable foundation artifact")
        (
            result,
            db_schema,
            table_observations,
            foundation_statuses,
            foundation_deferred_sections,
            foundation_optional_sections,
            foundation_reuse_status,
        ) = load_foundation_artifact(
            artifact_root=Path(foundation_input),
            repository=repo,
            files=files,
            profile=profile,
            output_root=out,
            repo_id=repo_id or repo.name,
            project_code=project_code,
            system_name=system_name,
        )
        sql_summary = dict(foundation_statuses.get("sql_summary") or {})
        sql_warnings = list(foundation_statuses.get("sql_warnings") or [])
        db_schema_status = dict(foundation_statuses.get("db_schema_status") or {})
        openapi_status = dict(foundation_statuses.get("openapi_status") or {})
        interaction_status = dict(foundation_statuses.get("interaction_status") or {})
        maven_dependency_status = dict(foundation_statuses.get("maven_dependency_status") or {})
        gradle_dependency_status = dict(foundation_statuses.get("gradle_dependency_status") or {})
        java_source_observation_status = dict(foundation_statuses.get("java_source_observation_status") or {})
        tsa_interpreter_status = dict(foundation_statuses.get("tsa_interpreter_status") or {})
        source_observation_fact_store_status = dict(foundation_statuses.get("source_observation_fact_store_status") or {})
        result.coverage["foundation_artifact"] = foundation_reuse_status
        _write_db_schema_artifacts(out, db_schema)
        _write_data_model_observation_artifacts(out, table_observations)
        for filename, payload in {
            "sql_parse_summary.json": sql_summary,
            "sql_parse_warnings.json": sql_warnings,
            "db_schema_status.json": db_schema_status,
            "openapi_status.json": openapi_status,
            "java_system_interaction_enrichment_status.json": interaction_status,
            "maven_dependency_status.json": maven_dependency_status,
            "gradle_dependency_status.json": gradle_dependency_status,
            "java_source_observation_status.json": java_source_observation_status,
            "java_module_resolution_status.json": (java_source_observation_status.get("module_resolution") or {}),
            "tsa_interpreter_status.json": tsa_interpreter_status,
            "source_observation_fact_store_status.json": source_observation_fact_store_status,
            "data_model_table_observation_status.json": table_observations.get("overview") or {},
            "foundation_reuse_status.json": foundation_reuse_status,
        }.items():
            write_json(diagnostics_dir / filename, payload)
        logger.done(
            "foundation_reuse",
            "Reusable foundation artifact loaded",
            artifact_fingerprint=foundation_reuse_status.get("artifact_fingerprint"),
        )

    # One shared Tree-sitter Java syntax cache is used across all Java stages in this run.
    # This keeps the analyzer fast without changing scanner contracts.
    logger.start("syntax_runtime_initialization", "Initializing Java syntax runtime")
    clear_java_syntax_cache()
    syntax_available, syntax_detail = tree_sitter_available()
    logger.done(
        "syntax_runtime_initialization",
        "Java syntax runtime initialized",
        provider=JAVA_SYNTAX_PROVIDER,
        available=syntax_available,
        detail=syntax_detail,
    )

    if not foundation_reused and "config_scan" in stage_set:
        logger.start("config_scan", "Extracting config facts")
        result.config_facts = scan_config_files(files)
        logger.done("config_scan", f"Config facts: {len(result.config_facts)}")

    if not foundation_reused and "maven_dependency_scan" in stage_set:
        logger.start("maven_dependency_scan", "Extracting source-declared Maven dependencies")
        dependency_facts, maven_dependency_status = scan_maven_dependencies(files)
        result.facts.extend(dependency_facts)
        result.coverage["maven_dependencies"] = maven_dependency_status
        write_json(diagnostics_dir / "maven_dependency_status.json", maven_dependency_status)
        logger.done("maven_dependency_scan", f"dependencies={len(dependency_facts)}")

    if not foundation_reused and "gradle_dependency_scan" in stage_set:
        logger.start("gradle_dependency_scan", "Extracting source-declared Gradle modules and dependencies")
        gradle_facts, gradle_dependency_status = scan_gradle_dependencies(files)
        result.facts.extend(gradle_facts)
        result.coverage["gradle_dependencies"] = gradle_dependency_status
        write_json(diagnostics_dir / "gradle_dependency_status.json", gradle_dependency_status)
        logger.done(
            "gradle_dependency_scan",
            f"modules={gradle_dependency_status.get('modules_observed', 0)}, "
            f"module_dependencies={gradle_dependency_status.get('module_dependencies_extracted', 0)}, "
            f"external_dependencies={gradle_dependency_status.get('external_dependencies_extracted', 0)}",
        )

    if not foundation_reused and "openapi_scan" in stage_set:
        logger.start("openapi_scan", "Extracting OpenAPI/Swagger contract facts")
        openapi_facts, openapi_schemas, openapi_interfaces, openapi_warnings = scan_openapi_files(files)
        result.facts.extend(openapi_facts)
        result.schemas.extend(openapi_schemas)
        result.interfaces.extend(openapi_interfaces)
        result.warnings.extend(openapi_warnings)
        openapi_status = {
            "requested": True,
            "contracts_extracted": len(openapi_facts),
            "schemas_extracted": len(openapi_schemas),
            "interfaces_extracted": len(openapi_interfaces),
            "source_policy": "OpenAPI/Swagger files are treated as declared API contract evidence; they do not override Java runtime implementation evidence.",
        }
        result.coverage["openapi"] = openapi_status
        write_json(diagnostics_dir / "openapi_status.json", openapi_status)
        logger.done("openapi_scan", f"contracts={len(openapi_facts)}, schemas={len(openapi_schemas)}, interfaces={len(openapi_interfaces)}")

    if not foundation_reused and "java_structural_scan" in stage_set:
        logger.start("java_structural_scan", "Extracting Tree-sitter Java structural facts")
        ok, detail = tree_sitter_available()
        if not ok:
            raise RuntimeError(f"Tree-sitter Java syntax provider is required but unavailable: {detail}")
        result.coverage["java_syntax_provider"] = JAVA_SYNTAX_PROVIDER
        facts, schemas, interfaces, relations, mapper_facts, java_warnings = scan_java_files(files)
        result.facts.extend(facts)
        result.schemas.extend(schemas)
        result.interfaces.extend(interfaces)
        result.relations.extend(relations)
        result.mapper_facts.extend(mapper_facts)
        result.warnings.extend(java_warnings)
        result.coverage.setdefault("java_syntax_cache", java_syntax_cache_stats())
        logger.done("java_structural_scan", f"facts={len(facts)}, schemas={len(schemas)}, interfaces={len(interfaces)}, relations={len(relations)}, mappers={len(mapper_facts)}")

    if not foundation_reused and "java_source_observation_build" in stage_set:
        logger.start("java_source_observation_build", "Publishing universal Tree-sitter Java source observations")
        source_observation_facts, java_source_observation_status = build_java_source_observation_facts(files)
        module_resolution_facts, java_module_resolution_status = build_java_module_resolution_facts(files, gradle_facts)
        source_observation_facts.extend(module_resolution_facts)
        java_source_observation_status["module_resolution"] = java_module_resolution_status
        source_observation_options = stage_options.get("java_source_observation_build") or {}
        configured_interpreters = source_observation_options.get("framework_interpreters")
        if configured_interpreters is None:
            # Universal observations stay framework-neutral unless a profile
            # explicitly enables a framework interpreter.
            enabled_interpreters = set()
        elif isinstance(configured_interpreters, list):
            enabled_interpreters = {
                str(item).strip().lower()
                for item in configured_interpreters
                if str(item).strip()
            }
        else:
            raise RuntimeError(
                "java_source_observation_build.options.framework_interpreters must be a list"
            )
        unsupported_interpreters = enabled_interpreters - {"tsa"}
        if unsupported_interpreters:
            raise RuntimeError(
                "Unsupported java source framework interpreters: "
                + ", ".join(sorted(unsupported_interpreters))
            )
        framework_api_roles = source_observation_options.get("framework_api_roles") or {}
        if not isinstance(framework_api_roles, dict):
            raise RuntimeError(
                "java_source_observation_build.options.framework_api_roles must be a mapping"
            )
        if "tsa" in enabled_interpreters:
            tsa_roles = framework_api_roles.get("tsa")
            if tsa_roles is not None and not isinstance(tsa_roles, dict):
                raise RuntimeError(
                    "java_source_observation_build.options.framework_api_roles.tsa must be a mapping"
                )
            tsa_facts, tsa_interpreter_status = interpret_tsa_facts(
                [*result.config_facts, *source_observation_facts],
                api_roles=tsa_roles,
            )
            tsa_interpreter_status = {"requested": True, **tsa_interpreter_status}
        else:
            tsa_facts = []
            tsa_interpreter_status = {
                "requested": False,
                "status": "not_run_by_profile",
                "reason": "framework_interpreter_not_enabled",
                "observations_emitted": 0,
            }
        full_source_facts = [*source_observation_facts, *tsa_facts]
        source_observation_fact_store_status = write_source_observation_fact_store(
            result=result,
            facts_dir=facts_dir,
            additional_facts=full_source_facts,
        )
        preview_facts = bounded_source_observation_preview(full_source_facts)
        result.facts.extend(preview_facts)
        java_source_observation_status["framework_interpreters"] = sorted(enabled_interpreters)
        java_source_observation_status["preview_facts_published"] = len(preview_facts)
        java_source_observation_status["tsa_observations_emitted"] = len(tsa_facts)
        java_source_observation_status["full_store_records"] = source_observation_fact_store_status.get("records_count")
        java_source_observation_status["full_store_bytes"] = source_observation_fact_store_status.get("bytes")
        result.coverage["java_source_observations"] = java_source_observation_status
        result.coverage["tsa_interpreter"] = tsa_interpreter_status
        result.coverage["source_observation_fact_store"] = source_observation_fact_store_status
        write_json(diagnostics_dir / "java_source_observation_status.json", java_source_observation_status)
        write_json(diagnostics_dir / "java_module_resolution_status.json", java_module_resolution_status)
        write_json(diagnostics_dir / "tsa_interpreter_status.json", tsa_interpreter_status)
        write_json(diagnostics_dir / "source_observation_fact_store_status.json", source_observation_fact_store_status)
        logger.done(
            "java_source_observation_build",
            f"facts={len(source_observation_facts)}, preview={len(preview_facts)}, unresolved_type_refs={java_source_observation_status.get('unresolved_type_references')}",
        )
        del source_observation_facts, tsa_facts, full_source_facts

    if not foundation_reused and "java_data_model_candidate_scan" in stage_set:
        logger.start("java_data_model_candidate_scan", "Detecting repository-level data model candidate signals")
        candidate_profile, candidate_facts, candidate_status = scan_data_model_candidate(
            repo,
            files,
            repo_id=repo_id or repo.name,
            project_code=project_code,
            system_name=system_name,
            core_version=CORE_VERSION,
        )
        result.facts.extend(candidate_facts)
        result.coverage["data_model_candidate_scan"] = candidate_status
        write_json(out / "compact" / "data_model_candidate_profile.json", candidate_profile)
        write_json(diagnostics_dir / "data_model_candidate_scan_status.json", candidate_status)
        logger.done(
            "java_data_model_candidate_scan",
            f"status={candidate_status.get('candidate_status')}, score={candidate_status.get('score')}",
        )

    if not foundation_reused and "java_system_interaction_enrichment" in stage_set:
        logger.start("java_system_interaction_enrichment", "Composing local HTTP/configuration boundary evidence")
        interaction_facts, interaction_interfaces, interaction_warnings, interaction_status = scan_java_system_interaction_evidence(
            files,
            config_facts=result.config_facts,
            schemas=result.schemas,
            interfaces=result.interfaces,
        )
        result.facts.extend(interaction_facts)
        # The scanner merges directly enriched interfaces into result.interfaces and
        # returns only newly added items for diagnostics.
        result.warnings.extend(interaction_warnings)
        result.coverage["java_system_interaction_enrichment"] = interaction_status
        write_json(diagnostics_dir / "java_system_interaction_enrichment_status.json", interaction_status)
        logger.done(
            "java_system_interaction_enrichment",
            f"facts={len(interaction_facts)}, interfaces_added={len(interaction_interfaces)}, composed_calls={interaction_status.get('http_outbound_composed_calls')}",
        )

    if not foundation_reused and "sql_scan" in stage_set:
        logger.start("sql_scan", "Extracting SQL facts")
        sql_facts, sql_summary, sql_warnings = scan_sql_files(files)
        result.facts.extend(sql_facts)
        result.coverage["sql"] = sql_summary
        write_json(diagnostics_dir / "sql_parse_summary.json", sql_summary)
        write_json(diagnostics_dir / "sql_parse_warnings.json", sql_warnings)
        logger.done("sql_scan", f"sql_facts={len(sql_facts)}, failed={sql_summary.get('failed')}, fallback={sql_summary.get('regex_fallback')}")

    if not foundation_reused and "db_schema_scan" in stage_set:
        logger.start("db_schema_scan", "Extracting physical DB schema from schema-bearing sources")
        db_schema = scan_database_schema(repo, files, repo_id=repo_id or repo.name, project_code=project_code, system_name=system_name)
        db_schema_facts = _db_schema_items_to_facts(db_schema)
        result.facts.extend(db_schema_facts)
        _write_db_schema_artifacts(out, db_schema)
        db_schema_counts = ((db_schema.get("overview") or {}).get("counts") or {})
        db_schema_status = {
            "requested": True,
            "source_policy": (db_schema.get("overview") or {}).get("source_policy") or "schema-bearing generated Java classes such as jOOQ are treated as confirmed physical DB model evidence",
            "tables_extracted": len(db_schema.get("tables") or []),
            "columns_extracted": len(db_schema.get("columns") or []),
            "keys_extracted": len(db_schema.get("keys") or []),
            "relationships_extracted": len(db_schema.get("relationships") or []),
            "indexes_extracted": len(db_schema.get("indexes") or []),
            "sequences_extracted": len(db_schema.get("sequences") or []),
            "constraints_extracted": len(db_schema.get("constraints") or []),
            "partitioning_extracted": len(db_schema.get("partitioning") or []),
            "jooq_table_files": db_schema_counts.get("jooq_table_files", 0),
            "liquibase_sql_files": db_schema_counts.get("liquibase_sql_files", 0),
            "source_mix": (db_schema.get("overview") or {}).get("source_mix") or {},
        }
        result.coverage["db_schema"] = db_schema_status
        write_json(diagnostics_dir / "db_schema_status.json", db_schema_status)

        table_observations = scan_sql_table_observations(
            repo,
            files,
            repo_id=repo_id or repo.name,
            db_schema=db_schema,
        )
        result.facts.extend(table_observations.get("facts") or [])
        _write_data_model_observation_artifacts(out, table_observations)
        result.coverage["data_model_table_observations"] = table_observations.get("overview") or {}
        write_json(diagnostics_dir / "data_model_table_observation_status.json", table_observations.get("overview") or {})
        logger.done(
            "db_schema_scan",
            f"tables={db_schema_status['tables_extracted']}, columns={db_schema_status['columns_extracted']}, "
            f"declared_relationships={db_schema_status['relationships_extracted']}, "
            f"observed_relationships={(table_observations.get('overview') or {}).get('relationship_observations', 0)}, "
            f"key_observations={(table_observations.get('overview') or {}).get('key_observations', 0)}",
        )

    if foundation_output is not None:
        foundation_declared_gc_enabled = gc.isenabled()
        if foundation_declared_gc_enabled:
            gc.disable()
        try:
            foundation_declared_facts, foundation_declared_status = scan_declared_values(files)
        finally:
            if foundation_declared_gc_enabled:
                gc.enable()
        foundation_optional_sections = {
            "declared_values": {
                "facts": [fact.model_dump(mode="json") for fact in foundation_declared_facts],
                "status": foundation_declared_status,
            }
        }
        foundation_statuses = {
            "sql_summary": sql_summary,
            "sql_warnings": sql_warnings,
            "db_schema_status": db_schema_status,
            "openapi_status": openapi_status,
            "interaction_status": interaction_status,
            "maven_dependency_status": maven_dependency_status,
            "gradle_dependency_status": gradle_dependency_status,
            "java_source_observation_status": java_source_observation_status,
            "tsa_interpreter_status": tsa_interpreter_status,
            "source_observation_fact_store_status": source_observation_fact_store_status,
        }
        foundation_manifest = write_foundation_artifact(
            artifact_root=Path(foundation_output).expanduser().resolve(),
            repository=repo,
            files=files,
            profile=profile,
            result=result,
            db_schema=db_schema,
            table_observations=table_observations,
            statuses=foundation_statuses,
            optional_sections=foundation_optional_sections,
            source_output_root=out,
            repo_id=repo_id or repo.name,
            project_code=project_code,
            system_name=system_name,
        )
        result.coverage["foundation_artifact"] = {
            "status": "published",
            "artifact_root": str(Path(foundation_output).expanduser().resolve()),
            "artifact_fingerprint": foundation_manifest.get("artifact_fingerprint"),
        }
        write_json(diagnostics_dir / "foundation_artifact_status.json", result.coverage["foundation_artifact"])

    if foundation_only:
        cache_before = java_syntax_cache_stats()
        clear_java_syntax_cache()
        write_json(diagnostics_dir / "java_syntax_cache_release_status.json", {
            "artifact": "java_syntax_cache_release",
            "release_point": "foundation_artifact_published",
            "cache_before": cache_before,
            "cache_after": java_syntax_cache_stats(),
        })
        logger.done("analysis", "Foundation artifact completed", out_dir=str(out))
        return result

    removed_heavy_stages = sorted(stage_set & {"spoon_scan", "semgrep_scan", "targeted_semgrep_scan"})
    if removed_heavy_stages:
        raise RuntimeError(
            "Removed heavy analysis stages are present in the selected profile: "
            + ", ".join(removed_heavy_stages)
            + ". Spoon/Semgrep have been removed from the fast evidence-oriented core; "
            + "use updated analysis profiles without these stages."
        )

    # Historical heavy analyzers are intentionally not run in the fast evidence-oriented core.
    # They are reported explicitly in coverage so LLM profiles do not assume deep Java AST
    # or Semgrep pattern evidence was collected.
    result.coverage["heavy_tools"] = {
        "spoon_scan": {
            "status": "removed_from_fast_core",
            "requested_by_profile": False,
            "impact": "deep Java AST evidence is not collected; use lightweight Java/SQL/config/custom lineage evidence and explicit gaps",
        },
        "semgrep_scan": {
            "status": "removed_from_fast_core",
            "requested_by_profile": False,
            "impact": "Semgrep pattern evidence is not collected; analyzer relies on built-in scanners and prepared compact evidence",
        },
        "targeted_semgrep_scan": {
            "status": "removed_from_fast_core",
            "requested_by_profile": False,
            "impact": "targeted Semgrep evidence is not collected",
        },
    }

    if "java_data_flow_build" in stage_set:
        logger.start("java_data_flow_build", "Building Java source-to-sink flow evidence")
        flow_facts, flow_status = build_java_data_flow_facts(files)
        result.facts.extend(flow_facts)
        result.coverage["java_data_flows"] = flow_status
        write_json(diagnostics_dir / "java_data_flow_status.json", flow_status)
        logger.done("java_data_flow_build", f"flows={len(flow_facts)}")

    if "java_field_flow_build" in stage_set:
        logger.start("java_field_flow_build", "Building Tree-sitter-backed local and interprocedural field-flow evidence")
        field_flow_facts, field_flow_status = build_java_field_flow_facts(
            files,
            interfaces=result.interfaces,
            schemas=result.schemas,
            repository_id=repo_id or repo.name,
            repository_root=repo,
        )
        result.facts.extend(field_flow_facts)
        result.coverage["java_field_flow"] = field_flow_status
        write_json(diagnostics_dir / "java_field_flow_status.json", field_flow_status)
        logger.done(
            "java_field_flow_build",
            f"occurrences={field_flow_status.get('field_occurrences_extracted')}, edges={field_flow_status.get('field_flow_edges_extracted')}",
        )

    if "java_traceability_build" in stage_set:
        logger.start("java_traceability_build", "Building Java ingress/call/persistence trace evidence")
        trace_facts, trace_status = build_java_traceability_facts(files, flow_facts)
        result.facts.extend(trace_facts)
        result.coverage["java_traceability"] = trace_status
        write_json(diagnostics_dir / "java_traceability_status.json", trace_status)
        logger.done("java_traceability_build", f"traceability facts={len(trace_facts)}, traces={trace_status.get('traces_extracted')}")

    if "java_persistence_lineage_build" in stage_set:
        # When traceability and deep persistence are both enabled, the previous Java
        # stages may leave hundreds of parsed syntax trees and large transient call
        # graph objects alive.  Rebuilding the lightweight syntax cache is cheaper
        # than carrying that memory into persistence on real applications.  This is
        # a performance/memory guard only; it does not change extracted evidence.
        if "java_traceability_build" in stage_set:
            result.coverage["java_syntax_cache_before_persistence_reset"] = java_syntax_cache_stats()
            clear_java_syntax_cache()
            # The profile-level runtime guard may already have suspended automatic
            # collection.  A young-generation collection is sufficient after
            # dropping the syntax cache; a full collection would scan the complete
            # live repository evidence graph accumulated by previous stages.
            gc.collect(0)
        logger.start("java_persistence_lineage_build", "Building neutral source-to-storage lineage evidence")
        opts = stage_options.get("java_persistence_lineage_build") or {}
        persistence_progress_path = diagnostics_dir / "java_persistence_lineage_progress.json"
        suspend_automatic_gc = bool(opts.get("suspend_automatic_gc", bool(opts.get("deep") or False)))
        gc_was_enabled = gc.isenabled()
        gc_counts_before = list(gc.get_count())
        freeze_count_before = int(gc.get_freeze_count()) if hasattr(gc, "get_freeze_count") else 0
        freeze_owned = False
        persistence_started = time.perf_counter()
        if suspend_automatic_gc and gc_was_enabled:
            # Keep the already materialized repository evidence graph out of the
            # resolver's young-generation collection.  This makes an explicit
            # post-stage gen-0 collection proportional to resolver churn instead of
            # the complete repository graph.  Never unfreeze a caller-owned frozen
            # heap: if one already exists, simply avoid the explicit collection.
            if freeze_count_before == 0 and hasattr(gc, "freeze"):
                gc.freeze()
                freeze_owned = True
            gc.disable()
        try:
            persistence_facts, persistence_lineage_status = build_java_persistence_lineage_facts(
                files,
                max_depth=int(opts.get("max_depth") or 4),
                deep=bool(opts.get("deep") or False),
                progress_path=persistence_progress_path,
                progress_interval=int(opts.get("progress_interval") or 25),
            )
        finally:
            gc_counts_while_suspended = list(gc.get_count())
            young_generation_collected = 0
            if suspend_automatic_gc and gc_was_enabled:
                try:
                    if freeze_owned:
                        # The pre-existing evidence graph is frozen, so only objects
                        # allocated by the resolver participate in this collection.
                        young_generation_collected = int(gc.collect(0))
                finally:
                    if freeze_owned:
                        gc.unfreeze()
                    gc.enable()
            persistence_runtime_guard = {
                "artifact": "java_persistence_runtime_guard",
                "guard_scope": "java_persistence_lineage_build",
                "pipeline_wide_gc_suspension": False,
                "suspend_automatic_gc": suspend_automatic_gc,
                "gc_was_enabled": gc_was_enabled,
                "gc_enabled_after_stage": gc.isenabled(),
                "gc_counts_before": gc_counts_before,
                "gc_counts_before_restore": gc_counts_while_suspended,
                "freeze_count_before": freeze_count_before,
                "freeze_owned": freeze_owned,
                "young_generation_collected": young_generation_collected,
                "elapsed_ms": int((time.perf_counter() - persistence_started) * 1000),
                "progress_interval": int(opts.get("progress_interval") or 25),
            }
            result.coverage["java_persistence_runtime_guard"] = persistence_runtime_guard
            write_json(diagnostics_dir / "java_persistence_runtime_guard.json", persistence_runtime_guard)
        result.facts.extend(persistence_facts)
        result.coverage["java_persistence_lineage"] = persistence_lineage_status
        write_json(diagnostics_dir / "java_persistence_lineage_status.json", persistence_lineage_status)
        logger.done("java_persistence_lineage_build", f"persistence facts={len(persistence_facts)}, lineages={persistence_lineage_status.get('source_to_storage_lineages_extracted')}")

    if "java_data_model_lineage_build" in stage_set:
        logger.start("java_data_model_lineage_build", "Building fast data model and attribute lineage evidence")
        opts = stage_options.get("java_data_model_lineage_build") or {}
        data_model_progress_path = diagnostics_dir / "java_data_model_lineage_progress.json"
        data_model_facts, data_model_lineage_status = build_java_data_model_lineage_facts(
            files,
            project_code=project_code,
            system_name=system_name,
            repo_id=repo_id or repo.name,
            repo_path=str(repo),
            fp_id=fp_id,
            fp_name=fp_name,
            max_depth=int(opts.get("max_depth") or 2),
            persistence_facts=persistence_facts if persistence_lineage_status.get("requested") else None,
            persistence_status=persistence_lineage_status if persistence_lineage_status.get("requested") else None,
            include_persistence_facts=not persistence_lineage_status.get("requested"),
            progress_path=data_model_progress_path,
            model_annotation_contracts=opts.get("model_annotation_contracts"),
        )
        result.facts.extend(data_model_facts)
        result.coverage["java_data_model_lineage"] = data_model_lineage_status
        write_json(diagnostics_dir / "java_data_model_lineage_status.json", data_model_lineage_status)
        logger.done(
            "java_data_model_lineage_build",
            f"data model facts={len(data_model_facts)}, attributes={data_model_lineage_status.get('attribute_occurrences_extracted')}, mappings={data_model_lineage_status.get('attribute_mappings_extracted')}",
        )


    if "java_table_observation_build" in stage_set:
        if foundation_reused:
            hydrate_foundation_result(result, foundation_deferred_sections)
        logger.start("java_table_observation_build", "Building Tree-sitter JPA and jOOQ relationship/key observations")
        java_table_observations = scan_java_table_observations(
            repo,
            files,
            repo_id=repo_id or repo.name,
            facts=result.facts,
            db_schema=db_schema,
        )
        result.facts.extend(java_table_observations.get("facts") or [])
        table_observations = _merge_data_model_observations(table_observations, java_table_observations)
        _write_data_model_observation_artifacts(out, table_observations)
        result.coverage["java_table_observations"] = java_table_observations.get("overview") or {}
        result.coverage["data_model_table_observations"] = table_observations.get("overview") or {}
        write_json(diagnostics_dir / "java_table_observation_status.json", java_table_observations.get("overview") or {})
        write_json(diagnostics_dir / "data_model_table_observation_status.json", table_observations.get("overview") or {})
        logger.done(
            "java_table_observation_build",
            f"relationships={(java_table_observations.get('overview') or {}).get('relationship_observations', 0)}, "
            f"keys={(java_table_observations.get('overview') or {}).get('key_observations', 0)}",
        )

    if foundation_reused and not foundation_deferred_sections.get("loaded"):
        hydrate_foundation_result(result, foundation_deferred_sections)

    # All stages that require native Tree-sitter roots have completed by this
    # point.  Later materializers operate only on extracted immutable facts and
    # syntax DTOs.  Release repository-scale native trees and UTF-8 buffers now,
    # rather than deferring their destruction to compact packaging or interpreter
    # shutdown where cleanup latency is difficult to observe and control.
    syntax_release_before_materialization = java_syntax_cache_stats()
    syntax_release_started = time.perf_counter()
    clear_java_syntax_cache(reset_stats=False)
    syntax_release_young_collected = int(gc.collect(0))
    syntax_release_status = {
        "artifact": "java_syntax_runtime_release",
        "release_point": "before_task_specific_materialization",
        "cache_before": syntax_release_before_materialization,
        "cache_after": java_syntax_cache_stats(),
        "young_generation_collected": syntax_release_young_collected,
        "elapsed_ms": int((time.perf_counter() - syntax_release_started) * 1000),
    }
    result.coverage["java_syntax_runtime_release"] = syntax_release_status
    write_json(diagnostics_dir / "java_syntax_runtime_release_status.json", syntax_release_status)

    if "declared_value_scan" in stage_set:
        logger.start("declared_value_scan", "Extracting explicitly declared value sets without semantic classification")
        foundation_optional_payload = load_foundation_optional_sections(foundation_optional_sections) if foundation_reused else foundation_optional_sections
        foundation_declared = foundation_optional_payload.get("declared_values") or {}
        if foundation_declared.get("facts") is not None:
            declared_value_facts = [Fact.model_validate(item) for item in foundation_declared.get("facts") or []]
            declared_value_status = dict(foundation_declared.get("status") or {})
        else:
            declared_gc_enabled = gc.isenabled()
            if declared_gc_enabled:
                gc.disable()
            try:
                declared_value_facts, declared_value_status = scan_declared_values(files)
            finally:
                if declared_gc_enabled:
                    gc.enable()
        result.facts.extend(declared_value_facts)
        result.coverage["declared_value_scan"] = declared_value_status
        write_json(diagnostics_dir / "declared_value_scan_status.json", declared_value_status)
        logger.done("declared_value_scan", f"declared value facts={len(declared_value_facts)}, sets={declared_value_status.get('value_sets_extracted')}")

    if "declared_value_summary_scan" in stage_set:
        logger.start("declared_value_summary_scan", "Materializing bounded declared-value-set summaries")
        if declared_value_status.get("requested"):
            declared_value_summary_facts, declared_value_summary_status = summarize_declared_value_facts(
                declared_value_facts,
                base_status=declared_value_status,
            )
        else:
            foundation_optional_payload = load_foundation_optional_sections(foundation_optional_sections) if foundation_reused else foundation_optional_sections
            foundation_declared = foundation_optional_payload.get("declared_values") or {}
            if foundation_declared.get("facts") is not None:
                foundation_declared_facts = [Fact.model_validate(item) for item in foundation_declared.get("facts") or []]
                declared_value_summary_facts, declared_value_summary_status = summarize_declared_value_facts(
                    foundation_declared_facts,
                    base_status=dict(foundation_declared.get("status") or {}),
                )
            else:
                summary_gc_enabled = gc.isenabled()
                if summary_gc_enabled:
                    gc.disable()
                try:
                    declared_value_summary_facts, declared_value_summary_status = scan_declared_value_summaries(files)
                finally:
                    if summary_gc_enabled:
                        gc.enable()
        result.facts.extend(declared_value_summary_facts)
        result.coverage["declared_value_set_summary"] = declared_value_summary_status
        write_json(diagnostics_dir / "declared_value_set_summary_status.json", declared_value_summary_status)
        logger.done("declared_value_summary_scan", f"declared value set summaries={len(declared_value_summary_facts)}, raw_sets={declared_value_summary_status.get('raw_value_sets_extracted')}")

    # Scanner and foundation-hydration order is an execution detail, not evidence
    # semantics.  Canonicalize before any bounded or first-evidence projection so
    # direct and foundation-reused task runs produce the same artifacts.
    canonical_order_before_enrichment = canonicalize_fact_order(result)
    result.coverage["canonical_fact_order_before_enrichment"] = canonical_order_before_enrichment

    if "system_description_enrichment" in stage_set:
        logger.start("system_description_enrichment", "Building system-description compact evidence")
        system_description_facts, system_description_status = build_system_description_enrichment_facts(result)
        system_description_status = {"requested": True, **system_description_status}
        result.facts.extend(system_description_facts)
        result.coverage["system_description_enrichment"] = system_description_status
        write_json(diagnostics_dir / "system_description_enrichment_status.json", system_description_status)
        logger.done("system_description_enrichment", f"facts={len(system_description_facts)}")

    canonical_order_final = canonicalize_fact_order(result)
    result.coverage["canonical_fact_order_final"] = canonical_order_final
    apply_strict_evidence_kernel(result)

    if source_observation_fact_store_status.get("status") != "success" and (
        "config_scan" in stage_set or "maven_dependency_scan" in stage_set
    ):
        source_observation_fact_store_status = write_source_observation_fact_store(result=result, facts_dir=facts_dir)
        result.coverage["source_observation_fact_store"] = source_observation_fact_store_status
        write_json(diagnostics_dir / "source_observation_fact_store_status.json", source_observation_fact_store_status)

    if "reference_data_fact_base" in stage_set:
        logger.start("reference_data_fact_base", "Building declared-value and storage fact base")
        reference_data_fact_base_status = build_reference_data_fact_base(result=result, out_dir=out)
        reference_data_fact_base_status = {"requested": True, **reference_data_fact_base_status}
        result.coverage["reference_data_fact_base"] = reference_data_fact_base_status
        write_json(diagnostics_dir / "reference_data_fact_base_status.json", reference_data_fact_base_status)
        logger.done(
            "reference_data_fact_base",
            f"declared_sets={reference_data_fact_base_status.get('declared_value_sets_count')}, records={reference_data_fact_base_status.get('records_count')}",
        )

    result.coverage["low_level_facts"] = {
        "mode": "lazy_only",
        "global_extraction": False,
        "message": "Detailed/low-level evidence is produced only by explicit evidence tools API requests.",
    }

    if "core_output" in stage_set:
        logger.start("core_output", "Writing slim machine-first core output")
        write_json(core_dir / "repository.json", {
            "system_name": result.system_name,
            "project_code": result.project_code,
            "repo_path": result.repo_path,
            "stack": result.stack,
            "files_analyzed": result.files_analyzed,
        })
        logger.done("core_output", "Slim core JSON output written")

    normalized_summary: dict[str, Any] = {"fact_count": 0, "evidence_count": 0, "persisted_fact_count": 0}
    if "normalize_facts" in stage_set or "normalized_fact_store" in stage_set:
        logger.start("normalize_facts", "Writing slim normalized fact indexes")
        normalized_summary = write_normalized_fact_store(result, facts_dir)
        result.coverage["normalized_facts"] = normalized_summary
        logger.done("normalize_facts", f"normalized facts={normalized_summary.get('fact_count')}, persisted={normalized_summary.get('persisted_fact_count')}")

    navigation: dict[str, Any] = {}
    if "compact_package" in stage_set or "compact_navigation" in stage_set:
        # Compact packaging operates only on already materialized facts.  Parsed Java
        # trees and scanner-local cycles are no longer needed and can otherwise make
        # allocation of compact indexes compete with hundreds of megabytes of dead
        # syntax state on real repositories.
        compact_cache_stats_before = java_syntax_cache_stats()
        compact_cleanup_started = time.perf_counter()
        clear_java_syntax_cache(reset_stats=False)
        compact_young_collected = int(gc.collect(0))
        result.coverage["java_syntax_cache"] = compact_cache_stats_before
        compact_runtime_guard = {
            "artifact": "compact_package_runtime_guard",
            "cache_before": compact_cache_stats_before,
            "cache_after": java_syntax_cache_stats(),
            "young_generation_collected": compact_young_collected,
            "elapsed_ms": int((time.perf_counter() - compact_cleanup_started) * 1000),
        }
        result.coverage["compact_package_runtime_guard"] = compact_runtime_guard
        write_json(diagnostics_dir / "compact_package_runtime_guard.json", compact_runtime_guard)
        logger.start("compact_package", "Writing compact machine-first navigation")
        compact_progress_path = diagnostics_dir / "compact_package_progress.json"
        compact_gc_was_enabled = gc.isenabled()
        compact_gc_counts_before = list(gc.get_count())
        compact_started = time.perf_counter()
        if compact_gc_was_enabled:
            gc.disable()
        try:
            navigation = build_navigation(
                result,
                out,
                max_items=max_packages,
                max_fields_per_schema=max_fields_per_schema,
                progress_path=compact_progress_path,
            )
            logger.done("compact_package", "Navigation JSON written")
        finally:
            compact_gc_counts_before_restore = list(gc.get_count())
            if compact_gc_was_enabled:
                gc.enable()
            compact_materialization_guard = {
                "artifact": "compact_materialization_runtime_guard",
                "guard_scope": "compact_package",
                "suspend_automatic_gc": compact_gc_was_enabled,
                "gc_enabled_after_stage": gc.isenabled(),
                "gc_counts_before": compact_gc_counts_before,
                "gc_counts_before_restore": compact_gc_counts_before_restore,
                "explicit_collection": False,
                "elapsed_ms": int((time.perf_counter() - compact_started) * 1000),
            }
            result.coverage["compact_materialization_runtime_guard"] = compact_materialization_guard
            write_json(diagnostics_dir / "compact_materialization_runtime_guard.json", compact_materialization_guard)

    result.coverage["java_syntax_cache"] = java_syntax_cache_stats()

    counts = {
        "config_facts": len(result.config_facts),
        "facts": len(result.facts),
        "interfaces": len(result.interfaces),
        "schemas": len(result.schemas),
        "mapper_facts": len(result.mapper_facts),
        "relations": len(result.relations),
        "normalized_facts": normalized_summary.get("fact_count"),
        "evidence": normalized_summary.get("evidence_count"),
        "java_data_flows": flow_status.get("flows_extracted"),
        "java_field_flows": flow_status.get("field_flows_extracted"),
        "java_field_occurrences": field_flow_status.get("field_occurrences_extracted"),
        "java_field_flow_edges": field_flow_status.get("field_flow_edges_extracted"),
        "java_field_lineages": trace_status.get("field_lineages_extracted"),
        "java_field_lineage_role_counts": trace_status.get("field_lineage_role_counts"),
        "java_field_lineage_target_boundary_counts": trace_status.get("field_lineage_target_boundary_counts"),
        "java_ingress": trace_status.get("ingress_extracted"),
        "java_method_calls": trace_status.get("method_calls_extracted"),
        "java_storage_accesses": trace_status.get("storage_accesses_extracted"),
        "java_traces": trace_status.get("traces_extracted"),
        "java_trace_status_counts": trace_status.get("trace_status_counts"),
        "java_trace_type_counts": trace_status.get("trace_type_counts"),
        "data_sources": persistence_lineage_status.get("data_sources_extracted"),
        "persistent_writes": persistence_lineage_status.get("persistent_writes_extracted"),
        "source_to_storage_lineages": persistence_lineage_status.get("source_to_storage_lineages_extracted"),
        "storage_lineage_gaps": persistence_lineage_status.get("storage_lineage_gaps_extracted"),
        "read_from_storage": persistence_lineage_status.get("read_from_storage_extracted"),
        "access_boundaries": persistence_lineage_status.get("access_boundaries_extracted"),
        "storage_to_access_lineages": persistence_lineage_status.get("storage_to_access_lineages_extracted"),
        "stored_field_to_response_field_mappings": persistence_lineage_status.get("stored_field_to_response_field_mappings_extracted"),
        "jooq_batch_bind_mappings": persistence_lineage_status.get("jooq_batch_bind_mappings_extracted"),
        "jooq_parameterized_sql_mappings": persistence_lineage_status.get("jooq_parameterized_sql_mappings_extracted"),
        "java_lineage_patterns": persistence_lineage_status.get("java_lineage_patterns_extracted"),
        "spring_component_dependencies": persistence_lineage_status.get("spring_component_dependencies_extracted"),
        "template_method_dispatches": persistence_lineage_status.get("template_method_dispatches_extracted"),
        "factory_method_mappings": persistence_lineage_status.get("factory_method_mappings_extracted"),
        "builder_field_mappings": persistence_lineage_status.get("builder_field_mappings_extracted"),
        "stream_collection_lineages": persistence_lineage_status.get("stream_collection_lineages_extracted"),
        "mapstruct_mapper_signatures": persistence_lineage_status.get("mapstruct_mapper_signatures_extracted"),
        "persistent_structures": data_model_lineage_status.get("persistent_structures_extracted"),
        "attribute_occurrences": data_model_lineage_status.get("attribute_occurrences_extracted"),
        "attribute_mappings": data_model_lineage_status.get("attribute_mappings_extracted"),
        "attribute_derivations": data_model_lineage_status.get("attribute_derivations_extracted"),
        "data_model_lineage_gaps": data_model_lineage_status.get("data_model_lineage_gaps_extracted"),
        "declared_value_sets": declared_value_status.get("value_sets_extracted"),
        "declared_values": declared_value_status.get("values_extracted"),
        "declared_value_sets_by_syntax_kind": declared_value_status.get("by_syntax_kind"),
        "declared_value_set_summaries": declared_value_summary_status.get("summary_value_sets_emitted"),
        "declared_value_set_summary_raw_sets": declared_value_summary_status.get("raw_value_sets_extracted"),
        "openapi_contracts": openapi_status.get("contracts_extracted"),
        "openapi_schemas": openapi_status.get("schemas_extracted"),
        "openapi_interfaces": openapi_status.get("interfaces_extracted"),
        "interaction_configuration_bindings": interaction_status.get("configuration_value_bindings"),
        "interaction_http_outbound_bindings": interaction_status.get("http_outbound_bindings"),
        "interaction_http_outbound_composed_calls": interaction_status.get("http_outbound_composed_calls"),
        "interaction_http_service_registrations": interaction_status.get("http_service_registrations"),
        "interaction_http_inbound_endpoints": interaction_status.get("http_inbound_endpoint_registrations"),
        "interaction_maven_dependencies": interaction_status.get("maven_dependencies"),
        "maven_dependencies": maven_dependency_status.get("dependencies_extracted"),
        "gradle_modules": gradle_dependency_status.get("modules_observed"),
        "gradle_module_dependencies": gradle_dependency_status.get("module_dependencies_extracted"),
        "gradle_external_dependencies": gradle_dependency_status.get("external_dependencies_extracted"),
        "java_source_observations": java_source_observation_status.get("facts_extracted"),
        "java_source_observation_fact_type_counts": java_source_observation_status.get("fact_type_counts"),
        "tsa_observations": tsa_interpreter_status.get("observations_emitted"),
        "tsa_observation_counts_by_kind": tsa_interpreter_status.get("counts_by_kind"),
        "source_observation_full_records": source_observation_fact_store_status.get("records_count"),
        "source_observation_full_bytes": source_observation_fact_store_status.get("bytes"),
        "source_observation_full_fact_type_counts": source_observation_fact_store_status.get("fact_type_counts"),
        "db_schema_tables": db_schema_status.get("tables_extracted"),
        "db_schema_columns": db_schema_status.get("columns_extracted"),
        "db_schema_keys": db_schema_status.get("keys_extracted"),
        "db_schema_relationships": db_schema_status.get("relationships_extracted"),
        "db_schema_indexes": db_schema_status.get("indexes_extracted"),
        "db_schema_sequences": db_schema_status.get("sequences_extracted"),
        "db_schema_constraints": db_schema_status.get("constraints_extracted"),
        "db_schema_partitioning": db_schema_status.get("partitioning_extracted"),
        "system_description_enrichment_facts": system_description_status.get("facts_extracted"),
    }
    evidence_coverage = _build_evidence_coverage(
        stage_set=stage_set,
        result=result,
        sql_summary=sql_summary,
        db_schema_status=db_schema_status,
        openapi_status=openapi_status,
        interaction_status=interaction_status,
        maven_dependency_status=maven_dependency_status,
        gradle_dependency_status=gradle_dependency_status,
        java_source_observation_status=java_source_observation_status,
        source_observation_fact_store_status=source_observation_fact_store_status,
        flow_status=flow_status,
        field_flow_status=field_flow_status,
        trace_status=trace_status,
        persistence_lineage_status=persistence_lineage_status,
        data_model_lineage_status=data_model_lineage_status,
        declared_value_status=declared_value_status,
        declared_value_summary_status=declared_value_summary_status,
        counts=counts,
    )
    result.coverage["evidence_coverage"] = evidence_coverage
    write_json(out / "evidence_coverage.json", evidence_coverage)
    write_json(diagnostics_dir / "evidence_coverage.json", evidence_coverage)

    status.update({
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "counts": counts,
        "stack": stack,
        "files_analyzed": len(files),
    })
    write_json(diagnostics_dir / "run.json", status)
    write_json(diagnostics_dir / "scanner_status.json", {
        "heavy_tools": result.coverage.get("heavy_tools"),
        "java_data_flows": flow_status,
        "java_traceability": trace_status,
        "java_persistence_lineage": persistence_lineage_status,
        "java_data_model_lineage": data_model_lineage_status,
        "declared_value_scan": declared_value_status,
        "declared_value_set_summary": declared_value_summary_status,
        "reference_data_fact_base": reference_data_fact_base_status,
        "db_schema": db_schema_status,
        "system_description_enrichment": system_description_status,
        "openapi": openapi_status,
        "java_system_interaction_enrichment": interaction_status,
        "maven_dependencies": maven_dependency_status,
        "gradle_dependencies": gradle_dependency_status,
        "java_source_observations": java_source_observation_status,
        "source_observation_fact_store": source_observation_fact_store_status,
        "sql": sql_summary,
        "low_level_facts": result.coverage["low_level_facts"],
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
        "repo_id": repo_id,
        "static_analysis_output": str(out),
        "workspace_type": "java",
        "system_name": system_name,
        "project_code": project_code,
        "analysis_profile": status["analysis_profile"],
        "output_policy": "strict_evidence_contract_json_lazy_evidence_human_views_external",
        "evidence_provider": {
            "access_api": "code_evidence.access",
            "capabilities": ["operation", "interface", "schema", "symbol", "callable", "field", "search", "relation", "query", "lineage", "show", "flow", "field-flow", "field-lineage", "output-field-provenance", "call-chain-diagnostic", "confirmed-evidence", "candidate-signal", "unresolved-gap", "ingress", "call", "trace", "storage-access", "read-from-storage", "access-boundary", "storage-to-access-lineage", "stored-field-to-response-field-mapping", "stored-data-access", "system-data-model-overview", "system-table-catalog", "event-source-catalog", "system-scenario-catalog", "system-boundaries", "data-model-relationships", "data-source", "persistent-write", "source-to-storage-lineage", "storage-lineage-gap", "persistent-structure", "attribute-occurrence", "attribute-mapping", "attribute-derivation", "data-model-lineage-gap", "declared-value-set", "declared-value-set-summary", "literal-data-write", "reference-data-fact-base", "db-schema-overview", "db-table-catalog", "db-table-detail", "db-column-catalog", "db-relationship-catalog", "db-index-catalog", "source-inspection-request", "source-inspect", "source-open", "find-implementations", "traces-for-operation", "traces-for-payload", "facts-by-type", "workspace-persistent-model", "workspace-attribute-catalog", "cross-repo-attribute-flow-candidates", "workspace-table-catalog", "workspace-table-attribute-catalog", "workspace-attribute-graph", "attribute-origin-candidates", "attribute-rename-chains", "attribute-journey-by-fp", "attribute-lineage-breaks", "workspace-source-to-storage-lineage", "workspace-data-model-lineage-gaps", "workspace-table-detail", "workspace-attribute-detail", "workspace-er-view", "workspace-er-model-candidates", "workspace-table-relationship-candidates", "workspace-key-candidates", "evidence-coverage", "transformation-catalog", "foreign-data-persistence-cases", "openspec-data-evidence-context", "openspec-data-evidence-full"],
        },
        "counts": counts,
        "prepared_artifacts": {
            "reference_data_fact_base": reference_data_fact_base_status,
            "source_observation_fact_store": source_observation_fact_store_status,
        },
    })

    if scanner_tmp_dir.exists():
        shutil.rmtree(scanner_tmp_dir, ignore_errors=True)
    # Keep cache stats in coverage/diagnostics, but release parsed Java AST/text
    # cache before returning to the workspace wrapper. Otherwise large real-app
    # runs may finish writing artifacts but spend a long time during interpreter
    # shutdown cleaning cached syntax trees.
    final_cache_stats_before = java_syntax_cache_stats()
    logger.start(
        "syntax_runtime_release",
        "Releasing Java syntax runtime",
        cache_before=final_cache_stats_before,
    )
    final_cache_release_started = time.perf_counter()
    clear_java_syntax_cache()
    final_cache_release_status = {
        "artifact": "java_syntax_cache_release",
        "cache_before": final_cache_stats_before,
        "cache_after": java_syntax_cache_stats(),
        "elapsed_ms": int((time.perf_counter() - final_cache_release_started) * 1000),
    }
    write_json(diagnostics_dir / "java_syntax_cache_release_status.json", final_cache_release_status)
    logger.done(
        "syntax_runtime_release",
        "Java syntax runtime released",
        cache_after=final_cache_release_status["cache_after"],
        release_elapsed_ms=final_cache_release_status["elapsed_ms"],
    )
    logger.done("analysis", "Analysis completed", out_dir=str(out))
    return result


def run_analysis(
    repo_path: str | Path,
    out_dir: str | Path,
    project_code: str,
    system_name: str,
    max_packages: int = 500,
    max_fields_per_schema: int = 16,
    verbose: bool = False,
    analysis_profile: str | Path | Mapping[str, Any] | None = None,
    repo_id: str | None = None,
    fp_id: str | None = None,
    fp_name: str | None = None,
    foundation_input: str | Path | None = None,
    foundation_output: str | Path | None = None,
    foundation_only: bool = False,
) -> AnalysisResult:
    """Run analysis. Expensive runtime guards are scoped to their owning stage.

    In particular, deep persistence may suspend automatic cyclic GC while its
    high-churn resolver is active. The rest of the pipeline (normalization,
    packaging and artifact publication) always runs with the caller's normal GC
    state. This avoids turning a local resolver guard into an unbounded
    whole-analysis memory/latency policy.
    """
    return _run_analysis_impl(
        repo_path=repo_path,
        out_dir=out_dir,
        project_code=project_code,
        system_name=system_name,
        max_packages=max_packages,
        max_fields_per_schema=max_fields_per_schema,
        verbose=verbose,
        analysis_profile=analysis_profile,
        repo_id=repo_id,
        fp_id=fp_id,
        fp_name=fp_name,
        foundation_input=foundation_input,
        foundation_output=foundation_output,
        foundation_only=foundation_only,
    )
