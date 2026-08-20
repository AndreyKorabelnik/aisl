from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

from .evidence_executor import (
    _validate_core_request,
    _validate_core_result,
    compile_core_evidence_request_from_execution_node,
    execute_core_evidence_request,
)
from .io_utils import now_utc, prepare_output, read_json, relative_or_absolute, stable_fingerprint, write_json
from .producer_reuse import ProducerArtifactStore, build_reuse_decision
from .runtime_support import validate_core_version
from .knowledge_execution_planning import inspect_repository_source, validate_knowledge_execution_plan
from .knowledge_materialization_executor import execute_materialization_execution_plan
from .version import __version__

KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION = "knowledge_execution_result/v2"

_REPOSITORY_PRODUCER_KIND = "core-repository-evidence"
_REPOSITORY_PRODUCER_ID = "code-analyzer-core:evidence-execute"
_SAFE_NODE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def _core_contracts_by_identity(catalog: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in catalog.get("contracts") or []:
        if not isinstance(raw, Mapping):
            continue
        key = (str(raw.get("artifact_kind") or ""), str(raw.get("schema_version") or ""))
        if all(key):
            result[key] = deepcopy(dict(raw))
    return result


def _node_reuse_material(
    *,
    snapshot: Mapping[str, Any],
    node: Mapping[str, Any],
    core_version: str,
    core_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    contracts = _core_contracts_by_identity(core_catalog)
    requirements: list[dict[str, Any]] = []
    output_contracts: list[dict[str, Any]] = []
    for raw in node.get("evidence_requirements") or []:
        if not isinstance(raw, Mapping):
            continue
        identity = (str(raw.get("artifact_kind") or ""), str(raw.get("schema_version") or ""))
        contract = contracts.get(identity)
        if contract is None:
            raise ValueError(f"Core evidence contract is unavailable for reuse key: {identity}")
        runtime = contract.get("runtime_publication") or {}
        requirements.append({
            "artifact_kind": identity[0],
            "schema_version": identity[1],
            "parameters": deepcopy(dict(raw.get("parameters") or {})),
        })
        output_contracts.append({
            "artifact_kind": identity[0],
            "schema_version": identity[1],
            "contract_fingerprint": str(contract.get("contract_fingerprint") or ""),
            "runtime_contract_id": str(runtime.get("runtime_contract_id") or ""),
            "producer_analyzer_id": str(runtime.get("producer_analyzer_id") or ""),
        })
    requirements.sort(key=lambda item: (item["artifact_kind"], item["schema_version"]))
    output_contracts.sort(key=lambda item: (item["artifact_kind"], item["schema_version"]))
    analyzer_id = str(node.get("analyzer_id") or "").strip()
    return {
        "producer": {
            "id": f"code-analyzer-core:{analyzer_id or 'evidence-execute'}",
            "version": core_version,
        },
        "input": {
            "source_id": str(snapshot.get("source_id") or ""),
            "source_snapshot_fingerprint": str(snapshot.get("snapshot_fingerprint") or ""),
        },
        "output_contracts": output_contracts,
        "semantic_parameters": requirements,
    }


def _expected_node_outputs(node: Mapping[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
        for item in node.get("expected_outputs") or []
        if isinstance(item, Mapping)
    }


def _validate_cached_repository_execution(
    payload_root: Path,
    entry: Mapping[str, Any],
    *,
    expected_reuse_material: Mapping[str, Any],
    expected_outputs: set[tuple[str, str]],
) -> dict[str, Any]:
    metadata = entry.get("metadata") or {}
    if metadata.get("reuse_material") != expected_reuse_material:
        raise ValueError("cached Core producer reuse material mismatch")
    manifest_path = payload_root / "repository_analysis_run_manifest.json"
    request_path = payload_root / "core-evidence-execution-request.json"
    result_path = payload_root / "core-evidence" / "core-evidence-execution-result.json"
    for candidate in (manifest_path, request_path, result_path):
        if not candidate.is_file():
            raise FileNotFoundError(f"cached Core producer artifact is incomplete: {candidate}")
    cached_request = read_json(request_path)
    _validate_core_request(cached_request)
    result = read_json(result_path)
    _validate_core_result(result=result, request=cached_request, core_output=payload_root / "core-evidence")
    manifest = read_json(manifest_path)
    if str(manifest.get("schema_version") or "") != "static_repository_analysis_run_manifest/v1":
        raise ValueError("cached Core producer manifest schema mismatch")
    if str(manifest.get("status") or "") != "completed":
        raise ValueError("cached Core producer manifest is not completed")
    registered = _registered_evidence(manifest=manifest, manifest_path=manifest_path)
    actual = {
        (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
        for item in registered
    }
    if not expected_outputs or not expected_outputs.issubset(actual):
        raise ValueError(
            f"cached Core producer output mismatch: expected={sorted(expected_outputs)}, actual={sorted(actual)}"
        )
    return manifest


def _semantic_artifact_fingerprints(
    manifest: Mapping[str, Any],
    *,
    identities: set[tuple[str, str]] | None = None,
) -> dict[tuple[str, str], str]:
    result = {
        (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or "")):
            str(item.get("content_fingerprint") or "")
        for item in manifest.get("evidence_artifacts") or []
        if isinstance(item, Mapping)
    }
    if identities is None:
        return result
    return {key: value for key, value in result.items() if key in identities}


def _safe_node_name(node_id: str) -> str:
    value = _SAFE_NODE_PATTERN.sub("-", node_id).strip("-._")
    if not value:
        raise ValueError(f"execution node has no safe filesystem identity: {node_id!r}")
    return value[:120]


def _catalog_fingerprint(payload: Mapping[str, Any], *, schema_version: str, label: str) -> str:
    if str(payload.get("schema_version") or "") != schema_version:
        raise ValueError(f"unsupported {label} schema: {payload.get('schema_version')!r}")
    actual = str(payload.get("catalog_fingerprint") or "")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != "catalog_fingerprint"}
    if not actual or actual != stable_fingerprint(material):
        raise ValueError(f"{label} fingerprint is invalid")
    return actual


def _compile_batched_core_request(
    *,
    execution_plan: Mapping[str, Any],
    analyzer_nodes: list[Mapping[str, Any]],
    core_evidence_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile one generic Core request for all analyzer nodes of one source snapshot."""
    if not analyzer_nodes:
        raise ValueError("Core analyzer batch is empty")
    compiled = [
        compile_core_evidence_request_from_execution_node(
            execution_plan=execution_plan,
            analyzer_node=node,
            core_evidence_catalog=core_evidence_catalog,
        )
        for node in analyzer_nodes
    ]
    sources = {
        (
            str((request.get("source") or {}).get("source_kind") or ""),
            str((request.get("source") or {}).get("source_id") or ""),
        )
        for request in compiled
    }
    if len(sources) != 1:
        raise ValueError("Core analyzer batch contains different source snapshots")

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    expected_owners: dict[tuple[str, str], str] = {}
    for node, request in zip(analyzer_nodes, compiled, strict=True):
        node_id = str(node.get("node_id") or "")
        for raw in request.get("evidence_requirements") or []:
            identity = (str(raw.get("artifact_kind") or ""), str(raw.get("schema_version") or ""))
            previous_owner = expected_owners.get(identity)
            if previous_owner is not None and previous_owner != node_id:
                raise ValueError(
                    f"Core analyzer batch contains duplicate evidence ownership for {identity}: "
                    f"{previous_owner!r}, {node_id!r}"
                )
            expected_owners[identity] = node_id
            parameters = deepcopy(dict(raw.get("parameters") or {}))
            existing = merged.get(identity)
            if existing is None:
                merged[identity] = {
                    "artifact_kind": identity[0],
                    "schema_version": identity[1],
                    "parameters": parameters,
                    "required_by": sorted({str(value) for value in raw.get("required_by") or [] if str(value)}),
                }
                continue
            if existing["parameters"] != parameters:
                raise ValueError(f"Core analyzer batch has conflicting parameters for {identity}")
            existing["required_by"] = sorted({
                *existing["required_by"],
                *(str(value) for value in raw.get("required_by") or [] if str(value)),
            })

    first = deepcopy(compiled[0])
    first["evidence_requirements"] = sorted(
        merged.values(),
        key=lambda item: (item["artifact_kind"], item["schema_version"]),
    )
    node_ids = [str(node.get("node_id") or "") for node in analyzer_nodes]
    orchestration = deepcopy(dict(first.get("orchestration") or {}))
    orchestration.update({
        "execution_node_id": node_ids[0],
        "execution_node_ids": node_ids,
        "batching_policy": "same_source_snapshot_single_core_request",
    })
    first["orchestration"] = orchestration
    first.pop("request_fingerprint", None)
    first["request_fingerprint"] = stable_fingerprint(first)
    return first


def _existing_artifacts(plan: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    knowledge: list[dict[str, Any]] = []
    for raw in (plan.get("graph") or {}).get("nodes") or []:
        if not isinstance(raw, Mapping):
            continue
        mode = str(raw.get("satisfaction_mode") or "")
        artifact = raw.get("artifact") or {}
        if not isinstance(artifact, Mapping):
            continue
        if mode == "existing_typed_artifact":
            item = deepcopy(dict(artifact))
            if str(item.get("availability") or "") != "available":
                raise ValueError(f"execution plan references unavailable evidence artifact: {item.get('artifact_id')!r}")
            status = str(item.get("status") or "completed")
            if status not in {"completed", "partial"}:
                raise ValueError(f"execution plan references unusable evidence artifact status: {status!r}")
            item["status"] = status
            evidence.append(item)
        elif mode == "existing_knowledge_artifact":
            item = deepcopy(dict(artifact))
            if str(item.get("availability") or "") != "available":
                raise ValueError(f"execution plan references unavailable knowledge artifact: {item.get('artifact_id')!r}")
            item["status"] = "completed"
            knowledge.append(item)
    return evidence, knowledge


def _source_nodes(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in (plan.get("graph") or {}).get("nodes") or []:
        if not isinstance(raw, Mapping) or str(raw.get("node_kind") or "") != "source_snapshot":
            continue
        snapshot = raw.get("source_snapshot") or {}
        if not isinstance(snapshot, Mapping):
            raise ValueError("source_snapshot node has no source snapshot object")
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        if not snapshot_id or snapshot_id in result:
            raise ValueError(f"invalid or duplicate source snapshot identity: {snapshot_id!r}")
        result[snapshot_id] = deepcopy(dict(snapshot))
    return result


def _validate_source_snapshot(snapshot: Mapping[str, Any]) -> Path:
    if str(snapshot.get("source_kind") or "") != "repository":
        raise ValueError(f"unsupported executable source kind: {snapshot.get('source_kind')!r}")
    location = snapshot.get("location") or {}
    if not isinstance(location, Mapping) or str(location.get("kind") or "") != "directory":
        raise ValueError("repository source snapshot has no directory location")
    repository = Path(str(location.get("path") or "")).expanduser().resolve()
    actual = inspect_repository_source(repository, source_id=str(snapshot.get("source_id") or ""))
    expected_fingerprint = str(snapshot.get("snapshot_fingerprint") or "")
    if expected_fingerprint != str(actual.get("snapshot_fingerprint") or ""):
        raise ValueError(
            f"source snapshot changed after execution-plan compilation: {snapshot.get('source_id')!r}"
        )
    return repository


def _registered_evidence(
    *,
    manifest: Mapping[str, Any],
    manifest_path: Path,
    source_metadata: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if str(manifest.get("schema_version") or "") != "static_repository_analysis_run_manifest/v1":
        raise ValueError("Core execution returned an unsupported Runner registration manifest")
    if str(manifest.get("status") or "") != "completed":
        raise ValueError("Core execution registration manifest is not completed")
    result: list[dict[str, Any]] = []
    repo_id = str((manifest.get("repository") or {}).get("repo_id") or "")
    for raw in manifest.get("evidence_artifacts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core execution manifest contains a non-object evidence artifact")
        item = deepcopy(dict(raw))
        if not all(str(item.get(field) or "") for field in ("artifact_id", "artifact_kind", "schema_version", "content_fingerprint")):
            raise ValueError("Core execution manifest contains an incomplete evidence registration")
        location = deepcopy(dict(item.get("location") or {}))
        raw_path = str(location.get("path") or "").strip()
        if raw_path:
            artifact_path = Path(raw_path)
            if not artifact_path.is_absolute():
                artifact_path = (manifest_path.parent / artifact_path).resolve()
            else:
                artifact_path = artifact_path.expanduser().resolve()
            location["path"] = str(artifact_path)
        item["location"] = location
        item["registration_manifest_path"] = str(manifest_path)
        item["repo_id"] = repo_id
        if source_metadata and str(item.get("artifact_kind") or "") == "repository-structure-evidence":
            item["source_metadata"] = deepcopy(dict(source_metadata))
        status = str(item.get("status") or "completed")
        if status not in {"completed", "partial"}:
            raise ValueError(f"Core execution manifest contains unusable evidence status: {status!r}")
        item["status"] = status
        result.append(item)
    return result


def _external_knowledge_artifacts_used_by_execution(
    *,
    existing_knowledge: list[dict[str, Any]],
    produced_knowledge: list[dict[str, Any]],
    materialization_executions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project only actually consumed previously-published KnowledgeProducts.

    These descriptors make the producer handoff self-contained for dependency
    provenance. They deliberately exclude local file locations: the published
    scope/revision/product identity and content identity are the durable facts.
    """
    produced_ids = {str(item.get("artifact_id") or "") for item in produced_knowledge}
    used_ids = {
        str(value)
        for execution in materialization_executions
        for value in (execution.get("input_knowledge_artifact_ids") or [])
        if str(value) and str(value) not in produced_ids
    }
    by_id = {str(item.get("artifact_id") or ""): item for item in existing_knowledge}
    missing = sorted(used_ids - set(by_id))
    if missing:
        raise ValueError(
            "knowledge execution external dependency cannot be resolved from prepared inputs: "
            + ", ".join(missing)
        )

    result: list[dict[str, Any]] = []
    for artifact_id in sorted(used_ids):
        artifact = by_id[artifact_id]
        provenance = artifact.get("provenance") or {}
        if not isinstance(provenance, Mapping) or str(provenance.get("source") or "") != "knowledge-api-revision":
            raise ValueError(
                f"external knowledge artifact {artifact_id!r} has no published-revision provenance"
            )
        required = {
            "model_kind": str(artifact.get("model_kind") or "").strip(),
            "schema_version": str(artifact.get("schema_version") or "").strip(),
            "source_materialization_id": str(artifact.get("source_materialization_id") or "").strip(),
            "content_fingerprint": str(artifact.get("content_fingerprint") or "").strip(),
            "source_system_id": str(provenance.get("source_system_id") or "").strip(),
            "source_revision_id": str(provenance.get("source_revision_id") or "").strip(),
        }
        missing_fields = [name for name, value in required.items() if not value]
        if missing_fields:
            raise ValueError(
                f"external knowledge artifact {artifact_id!r} has incomplete published identity: {missing_fields}"
            )
        result.append({
            "artifact_id": artifact_id,
            **required,
            "published_capabilities": sorted({
                str(value) for value in provenance.get("published_capabilities") or [] if str(value)
            }),
        })
    return result


def _validate_knowledge_dependency_registration(payload: Mapping[str, Any]) -> None:
    local = payload.get("knowledge_artifacts") or []
    external = payload.get("external_knowledge_artifacts") or []
    materializations = payload.get("materialization_executions") or []
    if not isinstance(local, list) or not isinstance(external, list) or not isinstance(materializations, list):
        raise ValueError("knowledge execution dependency collections must be lists")

    local_ids = {str(item.get("artifact_id") or "") for item in local if isinstance(item, Mapping)}
    external_ids: set[str] = set()
    for raw in external:
        if not isinstance(raw, Mapping):
            raise ValueError("external knowledge artifact must be an object")
        required = (
            "artifact_id", "model_kind", "schema_version", "source_materialization_id",
            "content_fingerprint", "source_system_id", "source_revision_id",
        )
        missing = [field for field in required if not str(raw.get(field) or "").strip()]
        if missing:
            raise ValueError(f"external knowledge artifact is incomplete: {missing}")
        artifact_id = str(raw["artifact_id"])
        if artifact_id in external_ids:
            raise ValueError(f"duplicate external knowledge artifact id: {artifact_id}")
        external_ids.add(artifact_id)
    overlap = sorted(local_ids & external_ids)
    if overlap:
        raise ValueError(f"knowledge artifact ids cannot be both produced and external: {overlap}")

    input_ids = {
        str(value)
        for execution in materializations
        if isinstance(execution, Mapping)
        for value in (execution.get("input_knowledge_artifact_ids") or [])
        if str(value)
    }
    unresolved = sorted(input_ids - local_ids - external_ids)
    if unresolved:
        raise ValueError(f"knowledge execution contains unresolved knowledge input ids: {unresolved}")
    unused_external = sorted(external_ids - input_ids)
    if unused_external:
        raise ValueError(f"knowledge execution contains unused external knowledge artifacts: {unused_external}")
    expected_external = input_ids - local_ids
    if external_ids != expected_external:
        raise ValueError("knowledge execution external dependency registration is inconsistent")


def _validate_expected_outputs(
    *,
    plan: Mapping[str, Any],
    knowledge_artifacts: list[dict[str, Any]],
    capabilities: list[str],
) -> None:
    expected = plan.get("expected_outputs") or {}
    expected_models = {str(value) for value in expected.get("knowledge_models") or [] if str(value)}
    actual_models = {str(item.get("schema_version") or "") for item in knowledge_artifacts}
    missing_models = sorted(expected_models - actual_models)
    if missing_models:
        raise RuntimeError(f"knowledge execution did not produce expected models: {missing_models}")
    expected_capabilities = {str(value) for value in expected.get("capabilities") or [] if str(value)}
    missing_capabilities = sorted(expected_capabilities - set(capabilities))
    if missing_capabilities:
        raise RuntimeError(f"knowledge execution did not publish expected capabilities: {missing_capabilities}")


def validate_knowledge_execution_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    if str(payload.get("schema_version") or "") != KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION:
        raise ValueError(f"unsupported knowledge execution result schema: {payload.get('schema_version')!r}")
    actual = str(payload.get("result_fingerprint") or "")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != "result_fingerprint"}
    if not actual or actual != stable_fingerprint(material):
        raise ValueError("knowledge execution result fingerprint is invalid")
    if str(payload.get("status") or "") != "completed":
        raise ValueError("knowledge execution result is not completed")
    node_executions = payload.get("node_executions") or []
    if not isinstance(node_executions, list):
        raise ValueError("knowledge execution result node_executions must be a list")
    execution_order = [str(value) for value in payload.get("execution_order") or []]
    actual_order = [str(item.get("execution_node_id") or "") for item in node_executions if isinstance(item, Mapping)]
    if execution_order != actual_order:
        raise ValueError("knowledge execution result node execution order does not match the plan")
    if any(str(item.get("status") or "") != "completed" for item in node_executions if isinstance(item, Mapping)):
        raise ValueError("knowledge execution result contains an incomplete node")
    policy = payload.get("semantic_policy") or {}
    expected_policy = {
        "plan_dispatch": "knowledge_execution_plan_topological_order",
        "core_dispatch": "artifact_identity_to_core_owned_analyzer",
        "evidence_registration": "all_validated_core_result_artifacts",
        "klc_dispatch": "materialization_id_to_klc_owned_handler",
        "capability_publication": "completed_materialization_results_only",
    }
    if policy != expected_policy:
        raise ValueError("knowledge execution result semantic policy is invalid")
    _validate_knowledge_dependency_registration(payload)
    return deepcopy(dict(payload))


def execute_knowledge_execution_plan(
    *,
    execution_plan: str | Path,
    core_evidence_catalog: str | Path,
    materialization_catalog: str | Path,
    output: str | Path,
    core_command: str = "code-analyzer-core",
    replace: bool = False,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    producer_cache_root: str | Path | None = None,
    force_rebuild: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute one knowledge_execution_plan/v1 without Task, Suite or Core Profile semantics."""
    plan_path = Path(execution_plan).expanduser().resolve()
    core_catalog_path = Path(core_evidence_catalog).expanduser().resolve()
    materialization_catalog_path = Path(materialization_catalog).expanduser().resolve()
    plan = validate_knowledge_execution_plan(read_json(plan_path))
    core_catalog = read_json(core_catalog_path)
    klc_catalog = read_json(materialization_catalog_path)
    core_fingerprint = _catalog_fingerprint(
        core_catalog,
        schema_version="core_evidence_contract_catalog/v1",
        label="Core evidence contract catalog",
    )
    klc_fingerprint = _catalog_fingerprint(
        klc_catalog,
        schema_version="knowledge_materialization_catalog/v3",
        label="KLC materialization catalog",
    )
    plan_inputs = plan.get("inputs") or {}
    if str(plan_inputs.get("core_evidence_contract_catalog_fingerprint") or "") != core_fingerprint:
        raise ValueError("execution plan does not bind the supplied Core evidence catalog")
    if str(plan_inputs.get("knowledge_materialization_catalog_fingerprint") or "") != klc_fingerprint:
        raise ValueError("execution plan does not bind the supplied KLC materialization catalog")
    if str((plan.get("status") or {}).get("overall") or "") != "ready":
        raise ValueError("knowledge execution plan is blocked")
    if duckdb_threads < 1:
        raise ValueError("duckdb_threads must be at least 1")

    root = prepare_output(
        output,
        replace=replace,
        protected_paths=(plan_path, core_catalog_path, materialization_catalog_path),
    )
    contracts_root = root / "contracts"
    write_json(contracts_root / "knowledge-execution-plan.json", plan)
    write_json(contracts_root / "core-evidence-contract-catalog.json", core_catalog)
    write_json(contracts_root / "knowledge-materialization-catalog.json", klc_catalog)

    nodes = {
        str(item.get("node_id") or ""): deepcopy(dict(item))
        for item in (plan.get("graph") or {}).get("nodes") or []
        if isinstance(item, Mapping)
    }
    execution_order = [str(value) for value in (plan.get("graph") or {}).get("execution_order") or []]
    sources = _source_nodes(plan)
    evidence_artifacts, existing_knowledge = _existing_artifacts(plan)
    analyzer_node_executions: list[dict[str, Any]] = []
    all_analyzer_executions: list[dict[str, Any]] = []
    repository_manifests: list[str] = []
    started_at = now_utc()

    materialization_seen = False
    analyzer_groups: dict[str, list[dict[str, Any]]] = {}
    analyzer_group_order: list[str] = []
    for node_id in execution_order:
        node = nodes[node_id]
        node_kind = str(node.get("node_kind") or "")
        if node_kind == "knowledge_materialization":
            materialization_seen = True
            continue
        if node_kind != "core_evidence_analyzer":
            raise ValueError(f"unsupported executable knowledge node kind: {node_kind!r}")
        if materialization_seen:
            raise ValueError("Core evidence analyzer cannot execute after a materialization node")
        snapshot_id = str(node.get("source_snapshot_id") or "")
        if snapshot_id not in sources:
            raise ValueError(f"Core analyzer node references an unknown source snapshot: {snapshot_id!r}")
        if snapshot_id not in analyzer_groups:
            analyzer_groups[snapshot_id] = []
            analyzer_group_order.append(snapshot_id)
        analyzer_groups[snapshot_id].append(node)

    producer_store = ProducerArtifactStore(producer_cache_root) if producer_cache_root is not None else None
    producer_reuse_decisions: list[dict[str, Any]] = []
    validated_core_version: str | None = None
    if producer_store is not None and analyzer_group_order:
        validated_core_version = validate_core_version(
            core_command=core_command,
            log_path=root / "contracts" / "core-version.log",
            progress=progress,
        )

    for ordinal, snapshot_id in enumerate(analyzer_group_order, start=1):
        group_nodes = analyzer_groups[snapshot_id]
        snapshot = sources[snapshot_id]
        repository = _validate_source_snapshot(snapshot)
        expected_by_node = {
            str(node.get("node_id") or ""): _expected_node_outputs(node)
            for node in group_nodes
        }
        expected_union: set[tuple[str, str]] = set()
        for node_id, expected in expected_by_node.items():
            if not expected:
                raise RuntimeError(f"Core analyzer node has no expected outputs: {node_id}")
            overlap = expected_union.intersection(expected)
            if overlap:
                raise RuntimeError(
                    f"Core analyzer nodes have overlapping expected outputs in batch: {sorted(overlap)}"
                )
            expected_union.update(expected)

        missing_nodes: list[dict[str, Any]] = []
        reuse_state: dict[str, dict[str, Any]] = {}
        for node in group_nodes:
            node_id = str(node.get("node_id") or "")
            state: dict[str, Any] = {
                "node": node,
                "reuse_key": None,
                "reuse_material": None,
                "lookup": None,
                "invalid_diagnostic": None,
            }
            if producer_store is not None:
                assert validated_core_version is not None
                material = _node_reuse_material(
                    snapshot=snapshot,
                    node=node,
                    core_version=validated_core_version,
                    core_catalog=core_catalog,
                )
                reuse_key = producer_store.reuse_key(material)
                lookup = producer_store.lookup(
                    producer_kind=_REPOSITORY_PRODUCER_KIND,
                    reuse_key=reuse_key,
                    validator=lambda payload, entry, material=material, expected=expected_by_node[node_id]:
                        _validate_cached_repository_execution(
                            payload,
                            entry,
                            expected_reuse_material=material,
                            expected_outputs=expected,
                        ),
                )
                state.update({"reuse_key": reuse_key, "reuse_material": material, "lookup": lookup})
                if lookup.status == "invalid":
                    state["invalid_diagnostic"] = lookup.diagnostic or "reuse artifact validation failed"
                    producer_store.quarantine(
                        producer_kind=_REPOSITORY_PRODUCER_KIND,
                        reuse_key=reuse_key,
                        diagnostic=state["invalid_diagnostic"],
                    )
                if lookup.status == "hit" and not force_rebuild:
                    assert lookup.payload_root is not None
                    manifest_path = lookup.payload_root / "repository_analysis_run_manifest.json"
                    manifest = read_json(manifest_path)
                    registered = _registered_evidence(
                        manifest=manifest,
                        manifest_path=manifest_path,
                        source_metadata=snapshot.get("source_metadata") or {},
                    )
                    selected = [
                        item for item in registered
                        if (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
                        in expected_by_node[node_id]
                    ]
                    evidence_artifacts.extend(selected)
                    repository_manifests.append(str(manifest_path))
                    original_elapsed = ((lookup.entry or {}).get("metadata") or {}).get("build_elapsed_seconds")
                    producer_reuse_decisions.append(build_reuse_decision(
                        node_id=node_id,
                        producer_kind=_REPOSITORY_PRODUCER_KIND,
                        producer_id=str((material.get("producer") or {}).get("id") or _REPOSITORY_PRODUCER_ID),
                        producer_version=validated_core_version,
                        action="reused",
                        reuse_key=reuse_key,
                        basis="content_addressed_completed_artifact",
                        source_id=str(snapshot.get("source_id") or ""),
                        artifact_reference=str(manifest_path),
                        saved_seconds=(float(original_elapsed) if original_elapsed is not None else None),
                    ))
                    if progress:
                        progress(
                            f"REUSE {node_id} key={reuse_key[:16]} "
                            "basis=content_addressed_completed_artifact"
                        )
                    analyzer_node_executions.append({
                        "execution_node_id": node_id,
                        "node_kind": "core_evidence_analyzer",
                        "status": "completed",
                        "execution_action": "reused",
                        "reuse_key": reuse_key,
                        "source_snapshot_id": snapshot_id,
                        "repository_run_manifest": str(manifest_path),
                        "evidence_artifact_ids": [str(item.get("artifact_id") or "") for item in selected],
                        "run_fingerprint": manifest.get("run_fingerprint"),
                    })
                    reuse_state[node_id] = state
                    continue
            missing_nodes.append(node)
            reuse_state[node_id] = state

        if not missing_nodes:
            continue

        missing_ids = [str(node.get("node_id") or "") for node in missing_nodes]
        for node in missing_nodes:
            node_id = str(node.get("node_id") or "")
            state = reuse_state[node_id]
            if producer_store is None:
                reason = "reuse_disabled"
            elif force_rebuild:
                reason = "force_rebuild"
            elif state.get("invalid_diagnostic"):
                reason = "cache_invalid"
            else:
                reason = "cache_miss"
            state["reason"] = reason
            if progress:
                progress(f"BUILD {node_id} reason={reason}")

        request = _compile_batched_core_request(
            execution_plan=plan,
            analyzer_nodes=missing_nodes,
            core_evidence_catalog=core_catalog,
        )
        node_root = root / "execution-nodes" / f"{ordinal:03d}-source-{_safe_node_name(snapshot_id)}"
        started = time.monotonic()
        manifest = execute_core_evidence_request(
            repository=repository,
            request=request,
            output=node_root,
            core_command=core_command,
            repo_id=str(missing_nodes[0].get("source_id") or ""),
            replace=True,
            progress=progress,
            request_provenance={
                "knowledge_execution_plan_fingerprint": plan.get("plan_fingerprint"),
                "execution_node_ids": missing_ids,
                "knowledge_profile_id": (plan.get("request") or {}).get("knowledge_profile_id"),
                "batching_policy": "same_source_snapshot_missing_nodes_single_core_request",
            },
            validated_core_version=validated_core_version,
        )
        elapsed = time.monotonic() - started
        manifest_path = node_root / "repository_analysis_run_manifest.json"
        registered = _registered_evidence(
            manifest=manifest,
            manifest_path=manifest_path,
            source_metadata=snapshot.get("source_metadata") or {},
        )
        actual = {
            (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
            for item in registered
        }
        missing_expected = set().union(*(expected_by_node[node_id] for node_id in missing_ids))
        if actual != missing_expected:
            raise RuntimeError(
                f"Core analyzer batch output mismatch; missing={sorted(missing_expected-actual)}, "
                f"unexpected={sorted(actual-missing_expected)}"
            )
        all_analyzer_executions.extend(
            deepcopy(dict(item)) for item in manifest.get("analyzer_executions") or [] if isinstance(item, Mapping)
        )

        independently_measured_elapsed = elapsed if len(missing_nodes) == 1 else None
        for node in missing_nodes:
            node_id = str(node.get("node_id") or "")
            state = reuse_state[node_id]
            expected = expected_by_node[node_id]
            selected = [
                item for item in registered
                if (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or "")) in expected
            ]
            effective_manifest = manifest
            effective_manifest_path = manifest_path
            reuse_key = state.get("reuse_key")
            material = state.get("reuse_material")
            lookup = state.get("lookup")

            if producer_store is not None and reuse_key is not None and force_rebuild and lookup is not None and lookup.status == "hit":
                assert lookup.payload_root is not None
                cached_manifest = read_json(lookup.payload_root / "repository_analysis_run_manifest.json")
                if _semantic_artifact_fingerprints(cached_manifest, identities=expected) != _semantic_artifact_fingerprints(manifest, identities=expected):
                    raise RuntimeError(
                        f"force rebuild produced different Core evidence fingerprints for the same reuse key: {node_id}"
                    )

            should_publish = producer_store is not None and reuse_key is not None and (
                not force_rebuild or lookup is None or lookup.status != "hit"
            )
            if should_publish:
                assert producer_store is not None and reuse_key is not None
                payload_root, entry = producer_store.publish_directory(
                    producer_kind=_REPOSITORY_PRODUCER_KIND,
                    reuse_key=reuse_key,
                    source_root=node_root,
                    metadata={
                        "reuse_material": material,
                        "producer_id": str(((material or {}).get("producer") or {}).get("id") or _REPOSITORY_PRODUCER_ID),
                        "producer_version": validated_core_version,
                        "source_id": str(snapshot.get("source_id") or ""),
                        "source_snapshot_fingerprint": str(snapshot.get("snapshot_fingerprint") or ""),
                        "build_elapsed_seconds": independently_measured_elapsed,
                        "batch_elapsed_seconds": elapsed,
                        "batch_node_count": len(missing_nodes),
                    },
                )
                _validate_cached_repository_execution(
                    payload_root,
                    entry,
                    expected_reuse_material=material or {},
                    expected_outputs=expected,
                )
                effective_manifest_path = payload_root / "repository_analysis_run_manifest.json"
                effective_manifest = read_json(effective_manifest_path)
                cached_registered = _registered_evidence(
                    manifest=effective_manifest,
                    manifest_path=effective_manifest_path,
                    source_metadata=snapshot.get("source_metadata") or {},
                )
                selected = [
                    item for item in cached_registered
                    if (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or "")) in expected
                ]

            evidence_artifacts.extend(selected)
            repository_manifests.append(str(effective_manifest_path))
            if producer_store is not None and reuse_key is not None:
                producer_reuse_decisions.append(build_reuse_decision(
                    node_id=node_id,
                    producer_kind=_REPOSITORY_PRODUCER_KIND,
                    producer_id=str(((material or {}).get("producer") or {}).get("id") or _REPOSITORY_PRODUCER_ID),
                    producer_version=validated_core_version or str((manifest.get("tool") or {}).get("version") or "unknown"),
                    action="built",
                    reuse_key=reuse_key,
                    basis="canonical_producer_execution",
                    source_id=str(snapshot.get("source_id") or ""),
                    invalidation_reason=str(state.get("reason") or "cache_miss"),
                    artifact_reference=str(effective_manifest_path),
                    elapsed_seconds=independently_measured_elapsed,
                    diagnostics=([str(state["invalid_diagnostic"])] if state.get("invalid_diagnostic") else []),
                ))
            analyzer_node_executions.append({
                "execution_node_id": node_id,
                "node_kind": "core_evidence_analyzer",
                "status": "completed",
                "execution_action": "built",
                **({"reuse_key": reuse_key} if reuse_key is not None else {}),
                "source_snapshot_id": snapshot_id,
                "repository_run_manifest": relative_or_absolute(effective_manifest_path, root),
                "evidence_artifact_ids": [str(item.get("artifact_id") or "") for item in selected],
                "run_fingerprint": effective_manifest.get("run_fingerprint"),
            })

    materialization_run = execute_materialization_execution_plan(
        execution_plan=plan,
        materialization_catalog=klc_catalog,
        evidence_artifacts=evidence_artifacts,
        knowledge_artifacts=existing_knowledge,
        output=root / "materialization-execution",
        replace=True,
        duckdb_memory_limit=duckdb_memory_limit,
        duckdb_threads=duckdb_threads,
        producer_cache_root=producer_cache_root,
        force_rebuild=force_rebuild,
        progress=progress,
    )
    producer_reuse_decisions.extend(
        deepcopy(dict(item))
        for item in (materialization_run.get("producer_reuse_decisions") or [])
        if isinstance(item, Mapping)
    )
    top_materialization_executions: list[dict[str, Any]] = []
    for raw in materialization_run.get("materialization_executions") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        for field in ("request", "result", "output_manifest"):
            value = str(item.get(field) or "").strip()
            if value and not Path(value).is_absolute():
                item[field] = str(Path("materialization-execution") / value)
        top_materialization_executions.append(item)
    materialization_node_executions = [
        {
            "execution_node_id": str(item.get("execution_node_id") or ""),
            "node_kind": "knowledge_materialization",
            "status": str(item.get("status") or ""),
            "materialization_id": item.get("materialization_id"),
            "materialization_execution_id": item.get("materialization_execution_id"),
            "execution_action": item.get("execution_action"),
            **({"reuse_key": item.get("reuse_key")} if item.get("reuse_key") else {}),
            "input_artifact_ids": list(item.get("input_artifact_ids") or []),
            "input_knowledge_artifact_ids": list(item.get("input_knowledge_artifact_ids") or []),
            "knowledge_artifact_ids": list(item.get("knowledge_artifact_ids") or []),
            "published_capabilities": list(item.get("published_capabilities") or []),
            "result": item.get("result"),
        }
        for item in top_materialization_executions
    ]
    executions_by_id = {
        str(item.get("execution_node_id") or ""): item
        for item in (*analyzer_node_executions, *materialization_node_executions)
    }
    node_executions = [executions_by_id[node_id] for node_id in execution_order]
    produced_knowledge: list[dict[str, Any]] = []
    for raw in materialization_run.get("produced_knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        location = item.get("location")
        if isinstance(location, Mapping):
            normalized_location = deepcopy(dict(location))
            for field in ("output_path", "manifest_path"):
                value = str(normalized_location.get(field) or "").strip()
                if value:
                    normalized_location[field] = relative_or_absolute(value, root)
            item["location"] = normalized_location
        produced_knowledge.append(item)
    external_knowledge = _external_knowledge_artifacts_used_by_execution(
        existing_knowledge=existing_knowledge,
        produced_knowledge=produced_knowledge,
        materialization_executions=top_materialization_executions,
    )
    capabilities = sorted({str(value) for value in materialization_run.get("published_capabilities") or [] if str(value)})
    _validate_expected_outputs(
        plan=plan,
        knowledge_artifacts=produced_knowledge,
        capabilities=capabilities,
    )
    completed_at = now_utc()
    all_repository_manifests = sorted({
        str(item.get("registration_manifest_path") or "")
        for item in evidence_artifacts
        if str(item.get("registration_manifest_path") or "")
    })
    result: dict[str, Any] = {
        "schema_version": KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION,
        "runner": {"producer": "static-analysis-runner", "version": __version__},
        "scope": deepcopy(plan.get("scope") or {}),
        "request": deepcopy(plan.get("request") or {}),
        "knowledge_execution_plan": {
            "path": str(plan_path),
            "plan_fingerprint": plan.get("plan_fingerprint"),
        },
        "catalogs": {
            "core_evidence_contract_catalog_fingerprint": core_fingerprint,
            "knowledge_materialization_catalog_fingerprint": klc_fingerprint,
        },
        "execution_order": execution_order,
        "node_executions": node_executions,
        "analyzer_executions": all_analyzer_executions,
        "evidence_artifacts": evidence_artifacts,
        "repository_run_manifests": all_repository_manifests,
        "materialization_executions": top_materialization_executions,
        "knowledge_artifacts": produced_knowledge,
        "external_knowledge_artifacts": external_knowledge,
        "published_capabilities": capabilities,
        "producer_reuse": {
            "schema_version": "producer_reuse_decisions/v1",
            "decisions": producer_reuse_decisions,
            "summary": {
                "built": sum(1 for item in producer_reuse_decisions if item.get("action") == "built"),
                "reused": sum(1 for item in producer_reuse_decisions if item.get("action") == "reused"),
            },
        },
        "semantic_policy": {
            "plan_dispatch": "knowledge_execution_plan_topological_order",
            "core_dispatch": "artifact_identity_to_core_owned_analyzer",
            "evidence_registration": "all_validated_core_result_artifacts",
            "klc_dispatch": "materialization_id_to_klc_owned_handler",
            "capability_publication": "completed_materialization_results_only",
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
        "diagnostics": [],
    }
    result["result_fingerprint"] = stable_fingerprint(result)
    validate_knowledge_execution_result(result)
    write_json(root / "knowledge_execution_result.json", result)
    write_json(root / "knowledge_execution_summary.json", {
        "schema_version": "knowledge_execution_summary/v1",
        "scope": result["scope"],
        "status": "completed",
        "execution_node_count": len(node_executions),
        "analyzer_execution_count": len(all_analyzer_executions),
        "producer_build_count": result["producer_reuse"]["summary"]["built"],
        "producer_reuse_count": result["producer_reuse"]["summary"]["reused"],
        "evidence_artifact_count": len(evidence_artifacts),
        "materialization_execution_count": len(result["materialization_executions"]),
        "knowledge_artifact_count": len(produced_knowledge),
        "published_capabilities": capabilities,
        "result_fingerprint": result["result_fingerprint"],
    })
    return result
