from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from knowledge_api.contract_v1.runtime import sha256_file
from knowledge_api.publication import build_publication_request, stable_fingerprint


@dataclass(frozen=True, slots=True)
class KnowledgeArtifactSpec:
    database: Path
    model_kind: str
    schema_version: str
    materialization_id: str
    capabilities: tuple[str, ...]
    artifact_id: str | None = None
    manifest_path: Path | None = None


def write_execution_result(
    root: Path,
    specs: Iterable[KnowledgeArtifactSpec],
    *,
    profile_id: str = "test-knowledge-profile",
    scope_id: str = "test-system",
    execution_token: str = "run-1",
) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict] = []
    materializations: list[dict] = []
    execution_order: list[str] = []
    node_executions: list[dict] = []
    capability_union: set[str] = set()

    for index, spec in enumerate(specs, start=1):
        database = spec.database.resolve()
        if not database.is_file():
            raise AssertionError(f"test knowledge database is unavailable: {database}")
        artifact_id = spec.artifact_id or f"knowledge_artifact_{index:02d}_{spec.model_kind.replace('-', '_')}"
        if spec.manifest_path is not None:
            manifest = spec.manifest_path.resolve()
            if not manifest.is_file():
                raise AssertionError(f"test knowledge manifest is unavailable: {manifest}")
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            if manifest_payload.get("schema_version") != "knowledge_layer/v1":
                raise AssertionError("test native manifest must declare knowledge_layer/v1")
            if manifest_payload.get("build_status") != "complete":
                raise AssertionError("test native manifest must be complete")
            if sorted({str(value) for value in manifest_payload.get("capabilities") or []}) != sorted(set(spec.capabilities)):
                raise AssertionError("test native manifest capabilities differ from artifact spec")
        else:
            manifest = database.parent / f"{artifact_id}-manifest.json"
            manifest_payload = {
                "schema_version": "knowledge_layer/v1",
                "artifact_id": artifact_id,
                "producer": "knowledge-layer-core",
                "producer_version": "test",
                "build_id": f"build-{artifact_id}",
                "build_status": "complete",
                "database_path": database.name,
                "manifest_path": manifest.name,
                "capabilities": sorted(set(spec.capabilities)),
                "validation": {"status": "complete"},
            }
            manifest.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
        content_fingerprint = sha256_file(database)
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "model_kind": spec.model_kind,
                "schema_version": spec.schema_version,
                "source_materialization_id": spec.materialization_id,
                "content_fingerprint": content_fingerprint,
                "coverage": {},
                "diagnostics": [],
                "status": "completed",
                "location": {
                    "kind": "knowledge-layer",
                    "output_path": str(database.parent),
                    "manifest_path": str(manifest),
                },
            }
        )
        node_id = f"materialization:{spec.materialization_id}"
        execution_order.append(node_id)
        node_executions.append(
            {
                "execution_node_id": node_id,
                "node_kind": "knowledge_materialization",
                "status": "completed",
            }
        )
        materializations.append(
            {
                "materialization_id": spec.materialization_id,
                "status": "completed",
                "knowledge_artifact_ids": [artifact_id],
                "published_capabilities": sorted(set(spec.capabilities)),
            }
        )
        capability_union.update(spec.capabilities)

    payload = {
        "schema_version": "knowledge_execution_result/v2",
        "status": "completed",
        "runner": {"producer": "static-analysis-runner", "version": "0.9.51"},
        "knowledge_execution_plan": {
            "path": "knowledge_execution_plan.json",
            "plan_fingerprint": "1" * 64,
        },
        "catalogs": {
            "core_evidence_contract_catalog_fingerprint": "2" * 64,
            "knowledge_materialization_catalog_fingerprint": "3" * 64,
        },
        "request": {
            "knowledge_profile_id": profile_id,
            "execution_token": execution_token,
        },
        "scope": {"kind": "repository", "scope_id": scope_id},
        "started_at": "2026-08-05T10:00:00+00:00",
        "completed_at": "2026-08-05T10:00:01+00:00",
        "execution_order": execution_order,
        "node_executions": node_executions,
        "analyzer_executions": [],
        "evidence_artifacts": [],
        "repository_run_manifests": [],
        "materialization_executions": materializations,
        "knowledge_artifacts": artifacts,
        "external_knowledge_artifacts": [],
        "published_capabilities": sorted(capability_union),
        "producer_reuse": {
            "schema_version": "producer_reuse_decisions/v1",
            "decisions": [],
            "summary": {"built": 0, "reused": 0},
        },
        "semantic_policy": {
            "plan_dispatch": "knowledge_execution_plan_topological_order",
            "capability_publication": "completed_materialization_results_only",
            "core_dispatch": "artifact_identity_to_core_owned_analyzer",
            "evidence_registration": "all_validated_core_result_artifacts",
            "klc_dispatch": "materialization_id_to_klc_owned_handler",
        },
        "diagnostics": [],
    }
    payload["result_fingerprint"] = stable_fingerprint(payload)
    path = root / f"knowledge-execution-result-{execution_token}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def publication_payload(
    execution_result: Path,
    *,
    base_revision_id: str | None = None,
    activate: bool = True,
    labels: Iterable[str] = (),
    metadata: dict | None = None,
) -> dict:
    request, warnings = build_publication_request(
        execution_result=execution_result,
        base_revision_id=base_revision_id,
        labels=labels,
        metadata=metadata or {},
        activate=activate,
    )
    assert warnings == []
    return request.model_dump(mode="json")
