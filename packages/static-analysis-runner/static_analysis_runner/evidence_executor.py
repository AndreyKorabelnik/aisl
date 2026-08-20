from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .execution import command_parts, display_command, run_process
from .io_utils import (
    now_utc,
    prepare_output,
    read_json,
    relative_or_absolute,
    sha256_file,
    stable_fingerprint,
    write_json,
)
from .runtime_support import repository_revision, validate_core_version
from .version import __version__

SUPPORTED_RESOLUTION_PLAN_SCHEMA = "knowledge_resolution_plan/v2"
SUPPORTED_CORE_EVIDENCE_CATALOG_SCHEMA = "core_evidence_contract_catalog/v1"
CORE_REQUEST_SCHEMA_VERSION = "core_evidence_execution_request/v1"
CORE_RESULT_SCHEMA_VERSION = "core_evidence_execution_result/v1"
CORE_RUNTIME_CONTRACT_ID = "core_evidence_runtime/v1"
RUN_MANIFEST_SCHEMA_VERSION = "static_repository_analysis_run_manifest/v1"
MIN_CORE_EVIDENCE_RUNTIME_VERSION = (0, 43, 27)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_fingerprinted_payload(
    payload: Mapping[str, Any],
    *,
    schema: str,
    fingerprint_field: str,
    label: str,
) -> None:
    if str(payload.get("schema_version") or "") != schema:
        raise ValueError(f"unsupported {label} schema: {payload.get('schema_version')!r}")
    actual = str(payload.get(fingerprint_field) or "")
    material = {
        str(key): deepcopy(value)
        for key, value in payload.items()
        if str(key) != fingerprint_field
    }
    if not actual or actual != _fingerprint(material):
        raise ValueError(f"{label} fingerprint is invalid")


def _contracts_by_identity(catalog: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in catalog.get("contracts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core evidence catalog contains a non-object contract")
        item = dict(raw)
        key = (
            str(item.get("artifact_kind") or "").strip(),
            str(item.get("schema_version") or "").strip(),
        )
        if not all(key) or key in result:
            raise ValueError(f"invalid or duplicate Core evidence contract identity: {key}")
        result[key] = item
    return result


def compile_core_evidence_request(
    *,
    resolution_plan: Mapping[str, Any],
    core_evidence_catalog: Mapping[str, Any],
    source_id: str,
) -> dict[str, Any]:
    """Compile selected Core evidence requirements without evidence-specific Runner code."""
    _validate_fingerprinted_payload(
        resolution_plan,
        schema=SUPPORTED_RESOLUTION_PLAN_SCHEMA,
        fingerprint_field="plan_fingerprint",
        label="knowledge resolution plan",
    )
    _validate_fingerprinted_payload(
        core_evidence_catalog,
        schema=SUPPORTED_CORE_EVIDENCE_CATALOG_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="Core evidence contract catalog",
    )
    contracts = _contracts_by_identity(core_evidence_catalog)
    technical = resolution_plan.get("technical_plan") or {}
    raw_requirements = technical.get("evidence_requirements") or []
    if not isinstance(raw_requirements, list):
        raise ValueError("knowledge resolution plan technical_plan.evidence_requirements must be a list")

    requirements: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_requirements:
        if not isinstance(raw, Mapping):
            raise ValueError("knowledge resolution plan contains a non-object evidence requirement")
        if str(raw.get("producer_kind") or "") != "core":
            continue
        kind = str(raw.get("artifact_kind") or "").strip()
        version = str(raw.get("schema_version") or "").strip()
        key = (kind, version)
        if not all(key):
            raise ValueError("Core evidence requirement has no artifact_kind/schema_version")
        if key in seen:
            raise ValueError(f"duplicate Core evidence requirement: {kind}/{version}")
        seen.add(key)
        contract = contracts.get(key)
        if contract is None:
            raise ValueError(f"Core evidence contract is not available: {kind}/{version}")
        assessment = contract.get("current_state_assessment") or {}
        runtime = contract.get("runtime_publication") or {}
        if contract.get("contract_status") != "runtime_published":
            raise ValueError(f"Core evidence contract is not runtime-published: {kind}/{version}")
        if assessment.get("typed_runtime_artifact_published") is not True:
            raise ValueError(f"Core evidence runtime is not ready for: {kind}/{version}")
        if str(runtime.get("runtime_contract_id") or "") != CORE_RUNTIME_CONTRACT_ID:
            raise ValueError(f"Core evidence contract declares unsupported runtime: {kind}/{version}")
        parameters = raw.get("parameters") or {}
        if not isinstance(parameters, Mapping):
            raise ValueError(f"Core evidence parameters must be an object: {kind}/{version}")
        requirements.append({
            "artifact_kind": kind,
            "schema_version": version,
            "parameters": dict(parameters),
            "required_by": sorted({str(value) for value in (raw.get("required_by") or []) if str(value)}),
        })
    if not requirements:
        raise ValueError("knowledge resolution plan has no Core evidence requirements")
    requirements.sort(key=lambda item: (item["artifact_kind"], item["schema_version"]))
    request: dict[str, Any] = {
        "schema_version": CORE_REQUEST_SCHEMA_VERSION,
        "source": {"source_kind": "repository", "source_id": source_id},
        "evidence_requirements": requirements,
        "orchestration": {
            "producer": "static-analysis-runner",
            "runner_version": __version__,
            "resolution_plan_fingerprint": resolution_plan.get("plan_fingerprint"),
            "core_evidence_catalog_fingerprint": core_evidence_catalog.get("catalog_fingerprint"),
            "semantic_routing": "artifact_kind_plus_schema_version",
        },
    }
    request["request_fingerprint"] = _fingerprint(request)
    return request


def _safe_child(root: Path, relative_path: str, *, label: str) -> Path:
    candidate = Path(relative_path)
    if not relative_path or candidate.is_absolute():
        raise ValueError(f"{label} must be output-relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes Core evidence output: {relative_path}") from exc
    return resolved


def _artifact_content_fingerprint(artifact: Mapping[str, Any]) -> str:
    material = {
        str(key): deepcopy(value)
        for key, value in artifact.items()
        if str(key) not in {"content_fingerprint", "artifact_id"}
    }
    return _fingerprint(material)


def _validate_core_result(
    *,
    result: Mapping[str, Any],
    request: Mapping[str, Any],
    core_output: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_fingerprinted_payload(
        result,
        schema=CORE_RESULT_SCHEMA_VERSION,
        fingerprint_field="result_fingerprint",
        label="Core evidence execution result",
    )
    if str(result.get("runtime_contract_id") or "") != CORE_RUNTIME_CONTRACT_ID:
        raise ValueError("Core evidence execution result declares an unsupported runtime")
    if str(result.get("request_fingerprint") or "") != str(request.get("request_fingerprint") or ""):
        raise ValueError("Core evidence result does not match the execution request")
    if str(result.get("status") or "") not in {"completed", "partial"}:
        raise ValueError(f"Core evidence execution did not complete: {result.get('status')!r}")
    expected = {
        (str(item.get("artifact_kind") or ""), str(item.get("schema_version") or ""))
        for item in request.get("evidence_requirements") or []
        if isinstance(item, Mapping)
    }
    analyzer_executions = [
        dict(item)
        for item in result.get("analyzer_executions") or []
        if isinstance(item, Mapping)
    ]
    execution_ids = {
        str(item.get("analyzer_execution_id") or "")
        for item in analyzer_executions
        if str(item.get("analyzer_execution_id") or "")
    }
    if len(execution_ids) != len(analyzer_executions):
        raise ValueError("Core evidence result has missing or duplicate analyzer execution ids")

    registrations: list[dict[str, Any]] = []
    actual: set[tuple[str, str]] = set()
    for raw in result.get("evidence_artifacts") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core evidence result contains a non-object artifact registration")
        item = dict(raw)
        kind = str(item.get("artifact_kind") or "").strip()
        version = str(item.get("schema_version") or "").strip()
        identity = (kind, version)
        if identity in actual:
            raise ValueError(f"Core evidence result contains duplicate artifact identity: {kind}/{version}")
        actual.add(identity)
        producer_execution_id = str(item.get("producer_analyzer_execution_id") or "")
        if producer_execution_id not in execution_ids:
            raise ValueError("Core evidence registration references an unknown analyzer execution")
        location = item.get("location") or {}
        if not isinstance(location, Mapping) or str(location.get("kind") or "") != "file":
            raise ValueError("Core evidence artifact location must be a file")
        artifact_path = _safe_child(core_output, str(location.get("path") or ""), label="artifact location.path")
        if not artifact_path.is_file():
            raise ValueError(f"Core evidence artifact file is missing: {artifact_path}")
        if str(location.get("sha256") or "") != sha256_file(artifact_path):
            raise ValueError("Core evidence artifact file SHA-256 is invalid")
        artifact = read_json(artifact_path)
        if str(artifact.get("contract_version") or "") != "core_evidence_artifact_contract/v1":
            raise ValueError("Core evidence artifact contract is unsupported")
        if (
            str(artifact.get("artifact_kind") or ""),
            str(artifact.get("schema_version") or ""),
        ) != identity:
            raise ValueError("Core evidence artifact identity does not match result registration")
        fingerprint = str(artifact.get("content_fingerprint") or "")
        if not fingerprint or fingerprint != _artifact_content_fingerprint(artifact):
            raise ValueError("Core evidence artifact content_fingerprint is invalid")
        if fingerprint != str(item.get("content_fingerprint") or ""):
            raise ValueError("Core evidence result fingerprint does not match artifact")
        if str(artifact.get("artifact_id") or "") != str(item.get("artifact_id") or ""):
            raise ValueError("Core evidence result artifact_id does not match artifact")
        registrations.append({**item, "_artifact_path": artifact_path, "_artifact": artifact})
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"Core evidence result identity mismatch; missing={missing}, unexpected={unexpected}")
    return analyzer_executions, registrations



def compile_core_evidence_request_from_execution_node(
    *,
    execution_plan: Mapping[str, Any],
    analyzer_node: Mapping[str, Any],
    core_evidence_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile one generic Core request directly from knowledge_execution_plan/v1."""
    from .knowledge_execution_planning import validate_knowledge_execution_plan

    plan = validate_knowledge_execution_plan(execution_plan)
    _validate_fingerprinted_payload(
        core_evidence_catalog,
        schema=SUPPORTED_CORE_EVIDENCE_CATALOG_SCHEMA,
        fingerprint_field="catalog_fingerprint",
        label="Core evidence contract catalog",
    )
    expected_catalog_fingerprint = str(
        (plan.get("inputs") or {}).get("core_evidence_contract_catalog_fingerprint") or ""
    )
    actual_catalog_fingerprint = str(core_evidence_catalog.get("catalog_fingerprint") or "")
    if expected_catalog_fingerprint != actual_catalog_fingerprint:
        raise ValueError("knowledge execution plan Core evidence catalog fingerprint does not match")
    if str(analyzer_node.get("node_kind") or "") != "core_evidence_analyzer":
        raise ValueError("execution node is not a Core evidence analyzer")
    if analyzer_node.get("execution_required") is not True:
        raise ValueError("Core evidence analyzer node is not executable")
    if str(analyzer_node.get("runtime_contract_id") or "") != CORE_RUNTIME_CONTRACT_ID:
        raise ValueError("Core evidence analyzer node declares an unsupported runtime")

    contracts = _contracts_by_identity(core_evidence_catalog)
    requirements: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in analyzer_node.get("evidence_requirements") or []:
        if not isinstance(raw, Mapping):
            raise ValueError("Core evidence analyzer node contains a non-object evidence requirement")
        kind = str(raw.get("artifact_kind") or "").strip()
        version = str(raw.get("schema_version") or "").strip()
        identity = (kind, version)
        if not all(identity) or identity in seen:
            raise ValueError(f"invalid or duplicate Core evidence requirement: {identity}")
        seen.add(identity)
        contract = contracts.get(identity)
        if contract is None:
            raise ValueError(f"Core evidence contract is not available: {kind}/{version}")
        assessment = contract.get("current_state_assessment") or {}
        runtime = contract.get("runtime_publication") or {}
        if contract.get("contract_status") != "runtime_published":
            raise ValueError(f"Core evidence contract is not runtime-published: {kind}/{version}")
        if assessment.get("typed_runtime_artifact_published") is not True:
            raise ValueError(f"Core evidence runtime is not ready for: {kind}/{version}")
        if str(runtime.get("runtime_contract_id") or "") != CORE_RUNTIME_CONTRACT_ID:
            raise ValueError(f"Core evidence contract declares unsupported runtime: {kind}/{version}")
        expected_analyzer = str(runtime.get("producer_analyzer_id") or "").strip()
        actual_analyzer = str(analyzer_node.get("analyzer_id") or "").strip()
        if expected_analyzer and actual_analyzer and expected_analyzer != actual_analyzer:
            raise ValueError(
                f"Core analyzer registration mismatch for {kind}/{version}: "
                f"plan={actual_analyzer!r}, catalog={expected_analyzer!r}"
            )
        parameters = raw.get("parameters") or {}
        if not isinstance(parameters, Mapping):
            raise ValueError(f"Core evidence parameters must be an object: {kind}/{version}")
        requirements.append({
            "artifact_kind": kind,
            "schema_version": version,
            "parameters": dict(parameters),
            "required_by": sorted({str(value) for value in (raw.get("required_by") or []) if str(value)}),
        })
    if not requirements:
        raise ValueError("Core evidence analyzer node has no evidence requirements")
    requirements.sort(key=lambda item: (item["artifact_kind"], item["schema_version"]))
    source_id = str(analyzer_node.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("Core evidence analyzer node has no source_id")
    request: dict[str, Any] = {
        "schema_version": CORE_REQUEST_SCHEMA_VERSION,
        "source": {"source_kind": "repository", "source_id": source_id},
        "evidence_requirements": requirements,
        "orchestration": {
            "producer": "static-analysis-runner",
            "runner_version": __version__,
            "knowledge_execution_plan_fingerprint": plan.get("plan_fingerprint"),
            "execution_node_id": analyzer_node.get("node_id"),
            "core_evidence_catalog_fingerprint": core_evidence_catalog.get("catalog_fingerprint"),
            "semantic_routing": "artifact_kind_plus_schema_version",
        },
    }
    request["request_fingerprint"] = _fingerprint(request)
    return request


def _validate_core_request(request: Mapping[str, Any]) -> None:
    if str(request.get("schema_version") or "") != CORE_REQUEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported Core evidence request schema: {request.get('schema_version')!r}")
    actual = str(request.get("request_fingerprint") or "")
    material = {str(key): deepcopy(value) for key, value in request.items() if str(key) != "request_fingerprint"}
    if not actual or actual != _fingerprint(material):
        raise ValueError("Core evidence request fingerprint is invalid")
    source = request.get("source") or {}
    if str(source.get("source_kind") or "") != "repository" or not str(source.get("source_id") or ""):
        raise ValueError("Core evidence request source must identify a repository")
    requirements = request.get("evidence_requirements") or []
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("Core evidence request has no evidence requirements")


def execute_core_evidence_request(
    *,
    repository: str | Path,
    request: Mapping[str, Any],
    output: str | Path,
    core_command: str = "code-analyzer-core",
    repo_id: str | None = None,
    replace: bool = False,
    progress: Callable[[str], None] | None = None,
    request_provenance: Mapping[str, Any] | None = None,
    protected_paths: tuple[Path, ...] = (),
    validated_core_version: str | None = None,
) -> dict[str, Any]:
    """Execute one generic Core request and register every returned typed artifact."""
    repository_path = Path(repository).expanduser().resolve()
    if not repository_path.is_dir():
        raise ValueError(f"repository does not exist or is not a directory: {repository_path}")
    request_payload = deepcopy(dict(request))
    _validate_core_request(request_payload)
    source = request_payload.get("source") or {}
    source_id = str(repo_id or source.get("source_id") or repository_path.name).strip()
    if not source_id:
        raise ValueError("repository source_id could not be resolved")
    if str(source.get("source_id") or "") != source_id:
        raise ValueError("Core evidence request source_id does not match requested repository identity")

    root = prepare_output(
        output,
        replace=replace,
        protected_paths=(repository_path, *protected_paths),
    )
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    core_output = root / "core-evidence"
    request_path = root / "core-evidence-execution-request.json"
    result_path = core_output / "core-evidence-execution-result.json"
    write_json(request_path, request_payload)
    core_version = validated_core_version or validate_core_version(
        core_command=core_command,
        log_path=logs / "core-version.log",
        progress=progress,
        minimum_version=MIN_CORE_EVIDENCE_RUNTIME_VERSION,
    )
    command = command_parts(core_command) + [
        "evidence-execute",
        "--repository",
        str(repository_path),
        "--request",
        str(request_path),
        "--output",
        str(core_output),
        "--repo-id",
        source_id,
    ]
    started_at = now_utc()
    if progress:
        progress(f"Executing Core evidence analyzers for {source_id}")
    process = run_process(command, log_path=logs / "core-evidence.log", echo=progress)
    failure: str | None = None
    core_result: dict[str, Any] = {}
    analyzer_executions: list[dict[str, Any]] = []
    core_registrations: list[dict[str, Any]] = []
    if process.returncode != 0:
        failure = f"code-analyzer-core evidence-execute exited with code {process.returncode}"
    elif not result_path.is_file():
        failure = f"code-analyzer-core did not publish {result_path}"
    else:
        try:
            core_result = read_json(result_path)
            analyzer_executions, core_registrations = _validate_core_result(
                result=core_result,
                request=request_payload,
                core_output=core_output,
            )
        except Exception as exc:
            failure = f"Core evidence result validation failed: {exc}"

    process_attempt = {
        "attempt": 1,
        "status": "completed" if failure is None else "failed",
        "process": {
            "command": list(process.command),
            "command_display": display_command(process.command),
            "returncode": process.returncode,
            "elapsed_seconds": process.elapsed_seconds,
            "max_rss_kb": process.max_rss_kb,
            "stack_dump_requests": process.stack_dump_requests,
            "timed_out": process.timed_out,
            "log": relative_or_absolute(process.log_path, root),
        },
    }
    provenance = {
        **dict(request_provenance or {}),
        "core_evidence_catalog_fingerprint": (request_payload.get("orchestration") or {}).get(
            "core_evidence_catalog_fingerprint"
        ),
        "semantic_role": "execution_request_provenance_only",
    }
    registered_executions = [
        {**item, "attempts": [process_attempt], "request_provenance": provenance}
        for item in analyzer_executions
    ]
    evidence_artifacts: list[dict[str, Any]] = []
    for raw in core_registrations:
        item = dict(raw)
        artifact_path = Path(item.pop("_artifact_path"))
        artifact = dict(item.pop("_artifact"))
        evidence_artifacts.append({
            **item,
            "semantic_identity": {
                "artifact_kind": item.get("artifact_kind"),
                "schema_version": item.get("schema_version"),
            },
            "provenance": {
                **dict(item.get("provenance") or {}),
                "request": provenance,
                "core_execution_result": relative_or_absolute(result_path, root),
            },
            "location": {
                "kind": "file",
                "path": relative_or_absolute(artifact_path, root),
                "sha256": sha256_file(artifact_path),
                "bytes": artifact_path.stat().st_size,
            },
        })
        if str(artifact.get("artifact_id") or "") != str(item.get("artifact_id") or ""):
            failure = "Runner evidence registration artifact_id mismatch"

    completed_at = now_utc()
    status = "completed" if failure is None else "failed"
    manifest: dict[str, Any] = {
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "runner": {"producer": "static-analysis-runner", "version": __version__},
        "repository": {
            "repo_id": source_id,
            "requested_repo_id": repo_id,
            "source_path": str(repository_path),
            "revision": repository_revision(repository_path),
        },
        "analysis_profile": None,
        "foundation": {"requested": False, "artifacts": []},
        "evidence_execution": {
            "runtime_contract_id": CORE_RUNTIME_CONTRACT_ID,
            "request_provenance": provenance,
            "request": relative_or_absolute(request_path, root),
            "core_result": relative_or_absolute(result_path, root) if result_path.is_file() else None,
        },
        "analyzer_executions": registered_executions,
        "evidence_artifacts": evidence_artifacts,
        "materialization_executions": [],
        "knowledge_artifacts": [],
        "published_capabilities": [],
        "knowledge_layer": {"requested": False, "status": "not-requested"},
        "tool": {
            "producer": "code-analyzer-core",
            "version": core_version,
            "minimum_version": ".".join(str(value) for value in MIN_CORE_EVIDENCE_RUNTIME_VERSION),
        },
        "lifecycle": {
            "started_at": started_at,
            "completed_at": completed_at,
            "attempts": [process_attempt],
            "diagnostics": ([{"code": "core_evidence_execution_failed", "severity": "error", "message": failure}] if failure else []),
        },
        "semantic_policy": {
            "evidence_dispatch": "generic_contract_driven",
            "semantic_identity": ["artifact_kind", "schema_version"],
        },
        "status": status,
        "failure": failure,
    }
    manifest["run_fingerprint"] = stable_fingerprint({
        "repo_id": source_id,
        "revision": manifest["repository"]["revision"],
        "request_fingerprint": request_payload.get("request_fingerprint"),
        "core_result_fingerprint": core_result.get("result_fingerprint"),
        "evidence_artifacts": [
            (
                item.get("artifact_id"),
                item.get("artifact_kind"),
                item.get("schema_version"),
                item.get("content_fingerprint"),
            )
            for item in evidence_artifacts
        ],
    })
    manifest_path = root / "repository_analysis_run_manifest.json"
    summary_path = root / "repository_analysis_run_summary.json"
    write_json(manifest_path, manifest)
    write_json(summary_path, {
        "schema_version": "static_repository_analysis_run_summary/v1",
        "repo_id": source_id,
        "status": status,
        "evidence_artifact_count": len(evidence_artifacts),
        "analyzer_execution_count": len(registered_executions),
        "artifact_kinds": sorted({str(item.get("artifact_kind")) for item in evidence_artifacts}),
        "run_fingerprint": manifest["run_fingerprint"],
        "failure": failure,
    })
    if failure is not None:
        raise RuntimeError(failure)
    return manifest


def execute_core_evidence_plan(
    *,
    repository: str | Path,
    resolution_plan: str | Path,
    core_evidence_catalog: str | Path,
    output: str | Path,
    core_command: str = "code-analyzer-core",
    repo_id: str | None = None,
    replace: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Low-level diagnostic execution of Core evidence from a resolution plan."""
    repository_path = Path(repository).expanduser().resolve()
    plan_path = Path(resolution_plan).expanduser().resolve()
    catalog_path = Path(core_evidence_catalog).expanduser().resolve()
    plan = read_json(plan_path)
    catalog = read_json(catalog_path)
    profile = plan.get("profile") or {}
    scope = profile.get("scope") or {}
    source_id = str(
        repo_id
        or (scope.get("scope_id") if scope.get("kind") == "repository" else None)
        or repository_path.name
    ).strip()
    if not source_id:
        raise ValueError("repository source_id could not be resolved")
    request = compile_core_evidence_request(
        resolution_plan=plan,
        core_evidence_catalog=catalog,
        source_id=source_id,
    )
    return execute_core_evidence_request(
        repository=repository_path,
        request=request,
        output=output,
        core_command=core_command,
        repo_id=source_id,
        replace=replace,
        progress=progress,
        request_provenance={
            "knowledge_profile_id": (plan.get("profile") or {}).get("profile_id"),
            "knowledge_resolution_plan_fingerprint": plan.get("plan_fingerprint"),
        },
        protected_paths=(plan_path, catalog_path),
    )
