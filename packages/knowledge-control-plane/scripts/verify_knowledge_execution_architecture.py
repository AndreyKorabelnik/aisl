#!/usr/bin/env python3
"""Verify the canonical Knowledge Control Plane knowledge-execution product boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "validation" / "knowledge-control-plane-1.2.0a10" / "architecture-audit.json"


def main() -> None:
    errors: list[str] = []
    checks: dict[str, object] = {}

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks["version"] = version
    if version != "1.2.0a10":
        errors.append(f"unexpected version: {version}")

    production_paths = [ROOT / "src", ROOT / "frontend" / "src"]
    production_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for base in production_paths
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".ts", ".vue", ".js"}
    )
    forbidden_tokens = {
        "full_pipeline": "removed legacy job kind",
        "repository_analysis": "removed legacy job kind",
        "workspace_analysis": "removed legacy job kind",
        "knowledge_layer.duckdb": "removed combined knowledge database",
        "analysis_profile_id": "removed Core Profile routing",
        "suite_id": "removed Suite routing",
        "task_id": "removed Task routing",
        "/api/v1/profiles": "removed legacy profile endpoint",
        "analysis_artifact": "removed analysis-artifact product registry",
    }
    found = {token: reason for token, reason in forbidden_tokens.items() if token in production_text}
    checks["forbidden_production_tokens"] = found
    if found:
        errors.extend(f"{reason}: {token}" for token, reason in found.items())

    deleted_paths = [
        "src/knowledge_control_plane/runtime/analysis_artifacts.py",
        "src/knowledge_control_plane/runtime/cache.py",
        "frontend/src/components/AttributeAdditionWizard.vue",
        "frontend/src/components/AnalysisForm.vue",
        "frontend/src/components/WorkspaceForm.vue",
        "frontend/src/components/TaskHistory.vue",
        "frontend/src/components/AssistantContextRepositoryPreparation.vue",
        "frontend/src/components/CommandPreview.vue",
    ]
    existing_deleted = [relative for relative in deleted_paths if (ROOT / relative).exists()]
    checks["removed_files_absent"] = not existing_deleted
    if existing_deleted:
        errors.extend(f"removed file still exists: {path}" for path in existing_deleted)

    required_files = [
        "src/knowledge_control_plane/runtime/knowledge_contracts.py",
        "src/knowledge_control_plane/runtime/knowledge_publication.py",
        "src/knowledge_control_plane/runtime/productions.py",
        "src/knowledge_control_plane/runtime/freshness.py",
        "frontend/src/views/ScenarioWizard.vue",
        "frontend/src/views/KnowledgeProfiles.vue",
        "frontend/src/views/KnowledgeProfileDetail.vue",
        "frontend/src/views/KnowledgeProducts.vue",
        "frontend/src/views/Productions.vue",
        "frontend/src/components/ProductionStructure.vue",
        "frontend/src/views/Analysis.vue",
        "frontend/src/views/RevisionDetail.vue",
        "frontend/src/components/ExecutionHistory.vue",
    ]
    missing = [relative for relative in required_files if not (ROOT / relative).is_file()]
    checks["required_files_present"] = not missing
    if missing:
        errors.extend(f"required file missing: {path}" for path in missing)

    openapi = json.loads((ROOT / "docs/api/generic-v1.openapi.json").read_text(encoding="utf-8"))
    paths = set(openapi.get("paths", {}))
    checks["openapi_path_count"] = len(paths)
    required_routes = {
        "/api/v1/knowledge-profiles",
        "/api/v1/knowledge-profiles/{profile_id}/resolution",
        "/api/v1/knowledge-products",
        "/api/v1/scenarios",
        "/api/v1/productions",
        "/api/v1/productions/{production_id}",
        "/api/v1/productions/{production_id}/refresh-check",
        "/api/v1/productions/refresh-check-due",
        "/api/v1/jobs/{job_id}/production-structure",
        "/api/v1/jobs",
        "/api/v1/assistant-contexts/{context_id}/questions",
    }
    missing_routes = sorted(required_routes - paths)
    forbidden_routes = sorted(
        route for route in paths
        if route.startswith("/api/v1/profiles")
        or "analysis-artifacts" in route
        or route.endswith("/conversation/questions")
    )
    checks["openapi_missing_required_routes"] = missing_routes
    checks["openapi_forbidden_routes"] = forbidden_routes
    if missing_routes:
        errors.extend(f"required OpenAPI route missing: {route}" for route in missing_routes)
    if forbidden_routes:
        errors.extend(f"legacy OpenAPI route remains: {route}" for route in forbidden_routes)

    profiles_text = (ROOT / "src/knowledge_control_plane/runtime/profiles.py").read_text(encoding="utf-8")
    scenarios_text = (ROOT / "src/knowledge_control_plane/runtime/scenarios.py").read_text(encoding="utf-8")
    models = (ROOT / "src/knowledge_control_plane/api/generic_v1/models.py").read_text(encoding="utf-8")
    app_text = (ROOT / "src/knowledge_control_plane/runtime/app.py").read_text(encoding="utf-8")
    checks["profile_scenario_split"] = (
        "class KnowledgeProfileDefinition" in models
        and "class ScenarioDefinition" in models
        and "ProfileInfo" not in production_text
        and "ScenarioService" in scenarios_text
        and "KnowledgeProfileService" in profiles_text
    )
    if not checks["profile_scenario_split"]:
        errors.append("Knowledge Profile and Scenario responsibilities are not cleanly separated")
    profile_forbidden = ("source_mode=", "report_profile=", "assistant_profile_id=", "parameters=")
    checks["profile_has_no_scenario_semantics"] = not any(token in profiles_text for token in profile_forbidden)
    if not checks["profile_has_no_scenario_semantics"]:
        errors.append("Knowledge Profile registry contains Scenario orchestration semantics")
    checks["dead_scenario_selectors_absent"] = "AnalysisPurpose" not in production_text and "analysis_purposes" not in production_text and "requires_llm" not in production_text
    if not checks["dead_scenario_selectors_absent"]:
        errors.append("unused Scenario semantic selectors remain in active runtime")
    checks["scenario_route_only"] = "/masters/{master_id}" not in app_text and "/scenarios/{scenario_id}" in app_text
    if not checks["scenario_route_only"]:
        errors.append("legacy /masters SPA route remains or /scenarios route is missing")
    checks["control_plane_does_not_model_core_klc_stages"] = all(
        token not in (ROOT / "src/knowledge_control_plane/runtime/pipeline.py").read_text(encoding="utf-8")
        for token in ("compile_plan", "core_evidence", "knowledge_materialization")
    )
    if not checks["control_plane_does_not_model_core_klc_stages"]:
        errors.append("Knowledge Control Plane still models Runner-internal Core/KLC stages")
    checks["knowledge_execution_only"] = 'KNOWLEDGE_EXECUTION = "knowledge_execution"' in models
    if not checks["knowledge_execution_only"]:
        errors.append("knowledge_execution job kind is missing")

    store = (ROOT / "src/knowledge_control_plane/runtime/store.py").read_text(encoding="utf-8")
    checks["runtime_schema_v3"] = "VALUES('schema_version', '3')" in store
    checks["legacy_database_rejected"] = "legacy Knowledge Control Plane runtime database is not supported" in store
    if not checks["runtime_schema_v3"]:
        errors.append("runtime schema v3 marker missing")
    if not checks["legacy_database_rejected"]:
        errors.append("legacy runtime database rejection missing")

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    forbidden_dependencies = [name for name in ("knowledge-layer-core", "knowledge-reporting") if name in pyproject]
    checks["forbidden_direct_dependencies"] = forbidden_dependencies
    if forbidden_dependencies:
        errors.extend(f"forbidden direct dependency: {name}" for name in forbidden_dependencies)

    result = {
        "schema_version": "knowledge_control_plane_architecture_audit/v1",
        "status": "passed" if not errors else "failed",
        "checks": checks,
        "errors": errors,
        "policies": {
            "job_route": "knowledge_execution_only",
            "semantic_owner": "knowledge-api",
            "runner_dispatch": "generic_contract_driven",
            "assistant_dispatch": "published_capabilities_only",
            "runtime_database_migration": "not_supported",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("Architecture audit failed:\n- " + "\n- ".join(errors))
    print(f"Architecture audit passed: {OUTPUT}")


if __name__ == "__main__":
    main()
