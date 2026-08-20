from __future__ import annotations

import json
from typing import Any

from knowledge_control_plane.api.generic_v1.models import ProductionArtifactNode, ProductionStructureResponse

from .artifacts import ArtifactRegistry
from .jobs import JobManager


class ProductionStructureService:
    """Read-only projection of immutable Runner execution artifacts for the frontend."""

    def __init__(self, *, jobs: JobManager, artifacts: ArtifactRegistry) -> None:
        self.jobs = jobs
        self.artifacts = artifacts

    def for_job(self, job_id: str) -> ProductionStructureResponse:
        job = self.jobs.get(job_id)
        registered = self.artifacts.list_for_job(job_id).items
        profile = self._load_json(registered, "knowledge_profile")
        plan = self._load_json(registered, "execution_plan")
        result = self._load_json(registered, "execution_result")
        nodes: list[ProductionArtifactNode] = []
        diagnostics: list[dict[str, Any]] = []
        capabilities: list[str] = []
        if result:
            diagnostics = [item for item in result.get("diagnostics") or [] if isinstance(item, dict)]
            capabilities = [str(item) for item in result.get("published_capabilities") or []]
            knowledge_by_id = {
                str(item.get("artifact_id")): item
                for item in result.get("knowledge_artifacts") or []
                if isinstance(item, dict) and item.get("artifact_id")
            }
            for item in result.get("evidence_artifacts") or []:
                if not isinstance(item, dict):
                    continue
                producer = item.get("provenance", {}).get("producer", {}) if isinstance(item.get("provenance"), dict) else {}
                diag = item.get("diagnostics") if isinstance(item.get("diagnostics"), dict) else {}
                nodes.append(ProductionArtifactNode(
                    node_id=str(item.get("artifact_id") or item.get("artifact_kind") or "evidence"),
                    node_kind="core_evidence",
                    title=str(item.get("artifact_kind") or "Core evidence"),
                    status=str(item.get("status") or item.get("availability") or "") or None,
                    model_kind=str(item.get("artifact_kind") or "") or None,
                    schema_version=str(item.get("schema_version") or "") or None,
                    producer_id=str(producer.get("analyzer_id") or "") or None,
                    fingerprint=str(item.get("content_fingerprint") or "") or None,
                    coverage=item.get("coverage") if isinstance(item.get("coverage"), dict) else {},
                    diagnostics=[{"summary": diag}] if diag else [],
                    metadata={
                        "scope_id": item.get("scope_id"),
                        "producer_kind": item.get("producer_kind"),
                        "location": item.get("location") if isinstance(item.get("location"), dict) else {},
                        "provenance": item.get("provenance") if isinstance(item.get("provenance"), dict) else {},
                    },
                ))
            for item in result.get("materialization_executions") or []:
                if not isinstance(item, dict):
                    continue
                output_ids = [str(value) for value in item.get("knowledge_artifact_ids") or []]
                output = next((knowledge_by_id.get(value) for value in output_ids if knowledge_by_id.get(value)), {})
                output = output if isinstance(output, dict) else {}
                nodes.append(ProductionArtifactNode(
                    node_id=str(item.get("execution_node_id") or item.get("materialization_id") or "materialization"),
                    node_kind="klc_materialization",
                    title=str(item.get("materialization_id") or "KLC materialization"),
                    status=str(item.get("status") or output.get("status") or "") or None,
                    model_kind=str(output.get("model_kind") or item.get("output_model_kind") or "") or None,
                    schema_version=str(output.get("schema_version") or "") or None,
                    producer_id=str(item.get("materialization_id") or "") or None,
                    fingerprint=str(output.get("content_fingerprint") or item.get("result_fingerprint") or item.get("content_fingerprint") or "") or None,
                    coverage=output.get("coverage") if isinstance(output.get("coverage"), dict) else {},
                    diagnostics=(
                        [d for d in output.get("diagnostics") or [] if isinstance(d, dict)]
                        or [d for d in item.get("diagnostics") or [] if isinstance(d, dict)]
                    ),
                    metadata={
                        "started_at": item.get("started_at"),
                        "completed_at": item.get("completed_at"),
                        "duration_ms": item.get("duration_ms"),
                        "input_artifact_ids": item.get("input_artifact_ids") or [],
                        "input_knowledge_artifact_ids": item.get("input_knowledge_artifact_ids") or [],
                        "knowledge_artifact_ids": output_ids,
                        "published_capabilities": item.get("published_capabilities") or [],
                        "producer": item.get("producer") if isinstance(item.get("producer"), dict) else {},
                        "request": item.get("request"),
                        "result": item.get("result"),
                    },
                ))
            for item in result.get("knowledge_artifacts") or []:
                if not isinstance(item, dict):
                    continue
                nodes.append(ProductionArtifactNode(
                    node_id=str(item.get("artifact_id") or item.get("model_kind") or "knowledge"),
                    node_kind="prepared_knowledge",
                    title=str(item.get("model_kind") or "Prepared Knowledge"),
                    status=str(item.get("status") or "completed") or None,
                    model_kind=str(item.get("model_kind") or "") or None,
                    schema_version=str(item.get("schema_version") or "") or None,
                    producer_id=str(item.get("source_materialization_id") or "") or None,
                    fingerprint=str(item.get("content_fingerprint") or "") or None,
                    coverage=item.get("coverage") if isinstance(item.get("coverage"), dict) else {},
                    diagnostics=[d for d in item.get("diagnostics") or [] if isinstance(d, dict)],
                    metadata={
                        "capabilities": item.get("capabilities") or [],
                        "location": item.get("location") if isinstance(item.get("location"), dict) else {},
                        "materialization_result_path": item.get("materialization_result_path"),
                    },
                ))
        return ProductionStructureResponse(
            job_id=job_id,
            scenario_id=job.scenario_id,
            knowledge_profile_id=job.knowledge_profile_id,
            profile_snapshot=profile,
            execution_plan=plan,
            execution_result=result,
            nodes=nodes,
            capabilities=capabilities,
            diagnostics=diagnostics,
        )

    def _load_json(self, artifacts, kind: str) -> dict[str, Any]:
        match = next((item for item in artifacts if item.kind.value == kind and item.content_available), None)
        if match is None:
            return {}
        _summary, path = self.artifacts.get(match.artifact_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
