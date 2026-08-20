from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.resources as resources
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.analysis_profiles import (
    load_analysis_fragment,
    load_analysis_profile,
    profile_stage_entries,
)

CATALOG_SCHEMA_VERSION = "core_analysis_catalog/v1"

# Current Java runtime order is owned by Core pipeline.py.  This catalog makes
# the existing order visible; it does not alter or replace pipeline execution.
JAVA_RUNTIME_STAGE_ORDER: tuple[str, ...] = (
    "scan_files",
    "config_scan",
    "maven_dependency_scan",
    "gradle_dependency_scan",
    "openapi_scan",
    "java_structural_scan",
    "java_source_observation_build",
    "java_data_model_candidate_scan",
    "java_system_interaction_enrichment",
    "sql_scan",
    "db_schema_scan",
    "java_data_flow_build",
    "java_field_flow_build",
    "java_traceability_build",
    "java_persistence_lineage_build",
    "java_data_model_lineage_build",
    "java_table_observation_build",
    "declared_value_scan",
    "declared_value_summary_scan",
    "system_description_enrichment",
    "reference_data_fact_base",
    "core_output",
    "normalize_facts",
    "normalized_fact_store",
    "compact_package",
    "compact_navigation",
)



def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_stage_catalog() -> dict[str, Any]:
    resource = resources.files("code_analyzer_core").joinpath("resources/core_analysis_stage_catalog_v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _stage_id(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, Mapping):
        return str(entry.get("id") or "").strip()
    return ""


def _clean_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): deepcopy(v) for k, v in value.items() if not str(k).startswith("_")}


def _source_ref(path: Path, *, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(root.resolve())
        display = rel.as_posix()
    except ValueError:
        display = resolved.as_posix()
    return {"path": display, "sha256": _sha256_file(resolved)}


def _source_chain(profile: Mapping[str, Any], *, root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in profile.get("_profile_sources") or []:
        path = Path(str(raw))
        if path.exists() and path.is_file():
            out.append(_source_ref(path, root=root))
    return out


def _stage_index(stage_catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("stage_id")): dict(item)
        for item in stage_catalog.get("stages") or []
        if isinstance(item, Mapping) and item.get("stage_id")
    }


def _derived_contract_index(stage_catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    payload = stage_catalog.get("java_derived_stage_contracts") or {}
    return {
        str(item.get("stage_id")): dict(item)
        for item in payload.get("contracts") or []
        if isinstance(item, Mapping) and item.get("stage_id")
    }


def _execution_model(profile_id: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    source_type = str(profile.get("source_type") or "").strip().lower()
    if source_type == "spec_artifacts" or profile_id == "spec-evidence-workspace":
        return {
            "engine": "spec_fixed_pipeline",
            "profile_stage_binding": "declarative_not_runtime_enforced",
            "runtime_entrypoint": "code_analyzer_core.spec_analysis.run_spec_analysis",
            "detail": "The profile stage list documents the fixed specification-normalization algorithm; individual labels do not enable or disable runtime phases.",
        }
    evidence_requirements = profile.get("evidence_requirements") or []
    uses_generic_evidence_runtime = any(
        isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == "sql-analysis"
        and str(item.get("schema_version") or "") == "sql-analysis/v1"
        for item in evidence_requirements
    )
    if uses_generic_evidence_runtime:
        return {
            "engine": "generic_evidence_runtime",
            "profile_stage_binding": "not_applicable",
            "runtime_entrypoint": "code_analyzer_core.evidence_runtime.execute_evidence_request",
            "detail": "SQL execution is selected only by the typed sql-analysis/v1 evidence requirement and the Core-owned analyzer registry; profile stage labels are not part of the contract.",
        }
    return {
        "engine": "java_stage_controlled_pipeline",
        "profile_stage_binding": "runtime_enforced_by_stage_set",
        "runtime_entrypoint": "code_analyzer_core.pipeline.run_analysis",
        "detail": "The resolved profile stage set controls explicit branches in the Java pipeline. Dependency order and data passing remain encoded in pipeline.py.",
    }


def _resolved_execution_plan(
    resolved_stage_entries: list[Any],
    *,
    runtime_enforced: bool,
) -> dict[str, Any]:
    declared_ids = [_stage_id(item) for item in resolved_stage_entries if _stage_id(item)]
    if not runtime_enforced:
        return {
            "declared_stage_ids": declared_ids,
            "runtime_stage_ids": [],
            "declarative_only_stage_ids": list(declared_ids),
        }
    declared_set = set(declared_ids)
    return {
        "declared_stage_ids": declared_ids,
        "runtime_stage_ids": [sid for sid in JAVA_RUNTIME_STAGE_ORDER if sid in declared_set],
        "declarative_only_stage_ids": [sid for sid in declared_ids if sid not in JAVA_RUNTIME_STAGE_ORDER],
    }


def _profile_diagnostics(
    *,
    profile_id: str,
    execution: Mapping[str, Any],
    resolved_stage_ids: list[str],
    stage_index: Mapping[str, Mapping[str, Any]],
    derived_contracts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if execution.get("profile_stage_binding") == "declarative_not_runtime_enforced":
        diagnostics.append({
            "code": "profile_stage_labels_not_runtime_controls",
            "severity": "warning",
            "message": "pipeline.stages describes intended phases but does not control individual runtime execution for this profile engine.",
        })
    for sid in resolved_stage_ids:
        item = stage_index.get(sid) or {}
        if item.get("category") == "knowledge_materialization_candidate":
            diagnostics.append({
                "code": "knowledge_materialization_inside_core",
                "severity": "architecture",
                "stage_id": sid,
                "message": str(item.get("rationale") or "Stage combines existing evidence into a higher-level knowledge view."),
                "recommended_boundary": item.get("recommended_boundary"),
            })
        contract = derived_contracts.get(sid) or {}
        if contract.get("reads_analysis_result") not in {None, "none"}:
            diagnostics.append({
                "code": "stage_reads_shared_analysis_result",
                "severity": "architecture",
                "stage_id": sid,
                "reads_analysis_result": contract.get("reads_analysis_result"),
                "analysis_result_reads": contract.get("analysis_result_reads") or [],
            })
        dependencies = contract.get("upstream_stage_dependencies") or []
        if dependencies:
            diagnostics.append({
                "code": "public_stage_dependency_observed",
                "severity": "architecture",
                "stage_id": sid,
                "dependencies": dependencies,
            })
    return diagnostics


def _profile_entry(path: Path, *, profiles_root: Path, catalog_root: Path, stage_catalog: Mapping[str, Any]) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid analysis profile file: {path}")
    resolved = load_analysis_profile(path)
    profile_id = str(resolved.get("profile_id") or "").strip()
    resolved_entries = profile_stage_entries(resolved)
    resolved_ids = [_stage_id(item) for item in resolved_entries]
    declared_pipeline = raw.get("pipeline") or {}
    declared_entries = [
        *list(declared_pipeline.get("stages") or []),
        *list(declared_pipeline.get("final_stages") or []),
    ]
    stage_catalog_index = _stage_index(stage_catalog)
    contract_index = _derived_contract_index(stage_catalog)
    execution = _execution_model(profile_id, resolved)
    basic_plan = _resolved_execution_plan(
        resolved_entries,
        runtime_enforced=execution["profile_stage_binding"] == "runtime_enforced_by_stage_set",
    )
    basic_plan["execution_model"] = execution

    stage_details: list[dict[str, Any]] = []
    evidence_families: set[str] = set()
    direct_artifacts: set[str] = set()
    for entry in resolved_entries:
        sid = _stage_id(entry)
        descriptor = deepcopy(stage_catalog_index.get(sid) or {})
        contract = deepcopy(contract_index.get(sid) or {})
        detail = {
            "stage_id": sid,
            "options": deepcopy(entry.get("options") or {}) if isinstance(entry, Mapping) else {},
            "descriptor": descriptor or None,
            "observed_contract": contract or None,
        }
        stage_details.append(detail)
        evidence_families.update(str(x) for x in descriptor.get("produces") or [] if x)
        evidence_families.update(str(x) for x in contract.get("produced_fact_types") or [] if x)
        direct_artifacts.update(str(x) for x in contract.get("direct_artifacts") or [] if x)

    return {
        "profile_id": profile_id,
        "profile_version": resolved.get("profile_version"),
        "name": resolved.get("name"),
        "description": resolved.get("description"),
        "source_type": resolved.get("source_type") or "source_repository",
        "workspace_types": list(resolved.get("workspace_types") or []),
        "capabilities": list(resolved.get("capabilities") or []),
        "analysis_parameters": deepcopy(resolved.get("analysis_parameters") or {}),
        "goal": deepcopy(resolved.get("goal") or {}),
        "output_contract": deepcopy(resolved.get("output_contract") or {}),
        "declared_profile": _clean_profile(raw),
        "resolved_profile": _clean_profile(resolved),
        "inheritance": {
            "declared_extends": deepcopy(raw.get("extends")),
            "resolved_parent_ids": list(resolved.get("_profile_inheritance") or []),
            "source_chain": _source_chain(resolved, root=catalog_root),
        },
        "source": _source_ref(path, root=catalog_root),
        "declared_stage_ids": [_stage_id(item) for item in declared_entries if _stage_id(item)],
        "resolved_stage_ids": resolved_ids,
        "execution_plan": basic_plan,
        "stage_details": stage_details,
        "evidence_outputs": {
            "observed_evidence_families": sorted(evidence_families),
            "direct_artifacts": sorted(direct_artifacts),
            "profile_output_contract": deepcopy(resolved.get("output_contract") or {}),
            "status": "descriptive_current_behavior_not_runtime_validated",
        },
        "architecture_diagnostics": _profile_diagnostics(
            profile_id=profile_id,
            execution=execution,
            resolved_stage_ids=resolved_ids,
            stage_index=stage_catalog_index,
            derived_contracts=contract_index,
        ),
    }


def _fragment_entry(path: Path, *, catalog_root: Path, stage_catalog: Mapping[str, Any]) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    resolved = load_analysis_fragment(path)
    entries = profile_stage_entries(resolved)
    ids = [_stage_id(item) for item in entries]
    stage_index = _stage_index(stage_catalog)
    return {
        "fragment_id": resolved.get("fragment_id"),
        "profile_version": resolved.get("profile_version"),
        "name": resolved.get("name"),
        "description": resolved.get("description"),
        "capabilities": list(resolved.get("capabilities") or []),
        "output_contract": deepcopy(resolved.get("output_contract") or {}),
        "declared_fragment": _clean_profile(raw),
        "resolved_fragment": _clean_profile(resolved),
        "source": _source_ref(path, root=catalog_root),
        "resolved_stage_ids": ids,
        "stage_categories": {
            sid: (stage_index.get(sid) or {}).get("category")
            for sid in ids
        },
        "architecture_diagnostics": [
            {
                "code": "foundation_contains_non_base_stage",
                "severity": "architecture",
                "stage_id": sid,
                "category": (stage_index.get(sid) or {}).get("category"),
            }
            for sid in ids
            if (stage_index.get(sid) or {}).get("category") not in {"base_evidence", "technical_packaging"}
        ],
    }


def build_core_analysis_catalog(
    *,
    profiles_root: str | Path,
    fragments_root: str | Path | None = None,
) -> dict[str, Any]:
    profiles_dir = Path(profiles_root).expanduser().resolve()
    if not profiles_dir.exists() or not profiles_dir.is_dir():
        raise ValueError(f"analysis profiles root not found: {profiles_dir}")
    fragments_dir = (
        Path(fragments_root).expanduser().resolve()
        if fragments_root is not None
        else (profiles_dir.parent / "analysis-profile-fragments").resolve()
    )
    catalog_root = profiles_dir.parent
    stage_catalog = _load_stage_catalog()

    profiles = [
        _profile_entry(path, profiles_root=profiles_dir, catalog_root=catalog_root, stage_catalog=stage_catalog)
        for path in sorted(profiles_dir.glob("*.yaml"))
    ]
    fragments = []
    if fragments_dir.exists() and fragments_dir.is_dir():
        fragments = [
            _fragment_entry(path, catalog_root=catalog_root, stage_catalog=stage_catalog)
            for path in sorted(fragments_dir.glob("*.yaml"))
        ]

    all_diagnostics = [
        item
        for profile in profiles
        for item in profile.get("architecture_diagnostics") or []
    ] + [
        item
        for fragment in fragments
        for item in fragment.get("architecture_diagnostics") or []
    ]
    payload: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "core_version": CORE_VERSION,
        "catalog_purpose": "Official read-only description of current Core profiles, Foundation fragments, runtime binding, evidence outputs and observed architecture dependencies.",
        "execution_effect": "none",
        "source_layout": {
            "profiles_directory": profiles_dir.name,
            "fragments_directory": fragments_dir.name if fragments_dir.exists() else None,
        },
        "summary": {
            "profile_count": len(profiles),
            "fragment_count": len(fragments),
            "stage_definition_count": len(stage_catalog.get("stages") or []),
            "java_derived_contract_count": int(((stage_catalog.get("java_derived_stage_contracts") or {}).get("contract_count") or 0)),
            "execution_model_counts": {},
            "architecture_diagnostic_count": len(all_diagnostics),
        },
        "profiles": profiles,
        "foundation_fragments": fragments,
        "stage_catalog": stage_catalog,
        "global_architecture_diagnostics": list(stage_catalog.get("architecture_findings") or []),
        "known_boundaries": {
            "foundation_owner": "code_analyzer_core",
            "foundation_current_role": "reusable repository analysis artifact built by Core and lifecycle-managed by external orchestration",
            "profile_owner": "code_analyzer_core",
            "task_and_suite_owner": "static_analysis_runner",
            "knowledge_materialization_owner_target": "knowledge_layer_core",
        },
    }
    counts: dict[str, int] = {}
    for profile in profiles:
        engine = str(((profile.get("execution_plan") or {}).get("execution_model") or {}).get("engine") or "unknown")
        counts[engine] = counts.get(engine, 0) + 1
    payload["summary"]["execution_model_counts"] = dict(sorted(counts.items()))
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def write_core_analysis_catalog(path: str | Path, catalog: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target
