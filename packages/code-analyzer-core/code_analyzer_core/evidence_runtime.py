from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from code_analyzer_core import __version__ as CORE_VERSION
from code_analyzer_core.scanners.repo_scanner import scan_all_files, filter_analyzer_files
from code_analyzer_core.prepared_artifacts.java_type_structure_evidence import (
    ANALYZER_ID as JAVA_TYPE_STRUCTURE_ANALYZER_ID,
    ARTIFACT_KIND as JAVA_TYPE_STRUCTURE_ARTIFACT_KIND,
    RELATIVE_PATH as JAVA_TYPE_STRUCTURE_RELATIVE_PATH,
    SCHEMA_VERSION as JAVA_TYPE_STRUCTURE_SCHEMA_VERSION,
    build_java_type_structure_evidence,
)
from code_analyzer_core.prepared_artifacts.java_persistence_mapping_evidence import (
    ANALYZER_ID as JAVA_PERSISTENCE_MAPPING_ANALYZER_ID,
    ARTIFACT_KIND as JAVA_PERSISTENCE_MAPPING_ARTIFACT_KIND,
    RELATIVE_PATH as JAVA_PERSISTENCE_MAPPING_RELATIVE_PATH,
    SCHEMA_VERSION as JAVA_PERSISTENCE_MAPPING_SCHEMA_VERSION,
    build_java_persistence_mapping_evidence,
)

from code_analyzer_core.prepared_artifacts.model_storage_evidence import (
    ANALYZER_ID as MODEL_STORAGE_ANALYZER_ID,
    ARTIFACT_KIND as MODEL_STORAGE_ARTIFACT_KIND,
    RELATIVE_PATH as MODEL_STORAGE_RELATIVE_PATH,
    SCHEMA_VERSION as MODEL_STORAGE_SCHEMA_VERSION,
    build_model_storage_evidence,
)

from code_analyzer_core.prepared_artifacts.storage_usage_evidence import (
    ANALYZER_ID as STORAGE_USAGE_ANALYZER_ID,
    ARTIFACT_KIND as STORAGE_USAGE_ARTIFACT_KIND,
    RELATIVE_PATH as STORAGE_USAGE_RELATIVE_PATH,
    SCHEMA_VERSION as STORAGE_USAGE_SCHEMA_VERSION,
    build_storage_usage_evidence,
)
from code_analyzer_core.prepared_artifacts.system_reference_evidence import (
    SYSTEM_DESCRIPTION_ANALYZER_ID,
    SYSTEM_DESCRIPTION_ARTIFACT_KIND,
    SYSTEM_DESCRIPTION_RELATIVE_PATH,
    SYSTEM_DESCRIPTION_SCHEMA_VERSION,
    REFERENCE_DATA_ANALYZER_ID,
    REFERENCE_DATA_ARTIFACT_KIND,
    REFERENCE_DATA_RELATIVE_PATH,
    REFERENCE_DATA_SCHEMA_VERSION,
    build_system_description_evidence,
    build_reference_data_evidence,
)
from code_analyzer_core.prepared_artifacts.interaction_boundary_evidence import (
    ANALYZER_ID as INTERACTION_BOUNDARY_ANALYZER_ID,
    ARTIFACT_KIND as INTERACTION_BOUNDARY_ARTIFACT_KIND,
    RELATIVE_PATH as INTERACTION_BOUNDARY_RELATIVE_PATH,
    SCHEMA_VERSION as INTERACTION_BOUNDARY_SCHEMA_VERSION,
    build_interaction_boundary_evidence,
)
from code_analyzer_core.prepared_artifacts.data_model_candidate_evidence import (
    ANALYZER_ID as DATA_MODEL_CANDIDATE_ANALYZER_ID,
    ARTIFACT_KIND as DATA_MODEL_CANDIDATE_ARTIFACT_KIND,
    RELATIVE_PATH as DATA_MODEL_CANDIDATE_RELATIVE_PATH,
    SCHEMA_VERSION as DATA_MODEL_CANDIDATE_SCHEMA_VERSION,
    build_data_model_candidate_evidence,
)
from code_analyzer_core.prepared_artifacts.persistence_lineage_evidence import (
    ANALYZER_ID as PERSISTENCE_LINEAGE_ANALYZER_ID,
    ARTIFACT_KIND as PERSISTENCE_LINEAGE_ARTIFACT_KIND,
    RELATIVE_PATH as PERSISTENCE_LINEAGE_RELATIVE_PATH,
    SCHEMA_VERSION as PERSISTENCE_LINEAGE_SCHEMA_VERSION,
    build_persistence_lineage_evidence,
)
from code_analyzer_core.prepared_artifacts.value_flow_evidence import (
    ANALYZER_ID as VALUE_FLOW_ANALYZER_ID,
    ARTIFACT_KIND as VALUE_FLOW_ARTIFACT_KIND,
    RELATIVE_PATH as VALUE_FLOW_RELATIVE_PATH,
    SCHEMA_VERSION as VALUE_FLOW_SCHEMA_VERSION,
    build_value_flow_evidence,
)
from code_analyzer_core.prepared_artifacts.repository_structure_evidence import (
    ANALYZER_ID as REPOSITORY_STRUCTURE_ANALYZER_ID,
    ARTIFACT_KIND as REPOSITORY_STRUCTURE_ARTIFACT_KIND,
    RELATIVE_PATH as REPOSITORY_STRUCTURE_RELATIVE_PATH,
    SCHEMA_VERSION as REPOSITORY_STRUCTURE_SCHEMA_VERSION,
    build_repository_structure_evidence,
)
from code_analyzer_core.prepared_artifacts.structured_file_shape_evidence import (
    ANALYZER_ID as STRUCTURED_FILE_SHAPE_ANALYZER_ID,
    ARTIFACT_KIND as STRUCTURED_FILE_SHAPE_ARTIFACT_KIND,
    RELATIVE_PATH as STRUCTURED_FILE_SHAPE_RELATIVE_PATH,
    SCHEMA_VERSION as STRUCTURED_FILE_SHAPE_SCHEMA_VERSION,
    build_structured_file_shape_evidence,
)
from code_analyzer_core.prepared_artifacts.sql_analysis_evidence import (
    ANALYZER_ID as SQL_ANALYSIS_ANALYZER_ID,
    ARTIFACT_KIND as SQL_ANALYSIS_ARTIFACT_KIND,
    RELATIVE_PATH as SQL_ANALYSIS_RELATIVE_PATH,
    SCHEMA_VERSION as SQL_ANALYSIS_SCHEMA_VERSION,
    build_sql_analysis_evidence,
)

REQUEST_SCHEMA_VERSION = "core_evidence_execution_request/v1"
RESULT_SCHEMA_VERSION = "core_evidence_execution_result/v1"
RUNTIME_CONTRACT_ID = "core_evidence_runtime/v1"
ARTIFACT_CONTRACT_VERSION = "core_evidence_artifact_contract/v1"


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


def _fingerprinted_payload(payload: Mapping[str, Any], *, field: str) -> str:
    material = {
        str(key): deepcopy(value)
        for key, value in payload.items()
        if str(key) != field
    }
    return _fingerprint(material)


def _safe_output_path(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if not relative_path or candidate.is_absolute():
        raise ValueError("evidence artifact path must be output-relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"evidence artifact path escapes output root: {relative_path}") from exc
    return resolved


def _diagnostic_summary(diagnostics: list[Mapping[str, Any]]) -> dict[str, Any]:
    severities = Counter(str(item.get("severity") or "unknown") for item in diagnostics)
    codes = Counter(str(item.get("code") or "unknown") for item in diagnostics)
    return {
        "count": len(diagnostics),
        "severity_counts": {key: severities[key] for key in sorted(severities)},
        "code_counts": {key: codes[key] for key in sorted(codes)},
    }


@dataclass(frozen=True, slots=True)
class EvidenceAnalyzerContext:
    repository: Path
    output: Path
    repo_id: str
    files: tuple[Path, ...]
    all_files: tuple[Path, ...]


EvidenceAnalyzerHandler = Callable[[EvidenceAnalyzerContext, Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class EvidenceAnalyzerRegistration:
    analyzer_id: str
    analyzer_version: str
    artifact_kind: str
    schema_version: str
    artifact_relative_path: str
    handler: EvidenceAnalyzerHandler

    @property
    def semantic_identity(self) -> tuple[str, str]:
        return (self.artifact_kind, self.schema_version)


_ANALYZERS: dict[tuple[str, str], EvidenceAnalyzerRegistration] = {}


def register_evidence_analyzer(registration: EvidenceAnalyzerRegistration) -> None:
    key = registration.semantic_identity
    if not all((registration.analyzer_id, registration.analyzer_version, *key)):
        raise ValueError("evidence analyzer registration contains empty identity fields")
    if key in _ANALYZERS:
        raise ValueError(f"duplicate evidence analyzer registration: {key[0]}/{key[1]}")
    _ANALYZERS[key] = registration


def registered_evidence_analyzers() -> tuple[EvidenceAnalyzerRegistration, ...]:
    return tuple(_ANALYZERS[key] for key in sorted(_ANALYZERS))


def _repository_structure_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_repository_structure_evidence(
        repository=context.repository,
        all_files=context.all_files,
        repo_id=context.repo_id,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=REPOSITORY_STRUCTURE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=REPOSITORY_STRUCTURE_ARTIFACT_KIND,
        schema_version=REPOSITORY_STRUCTURE_SCHEMA_VERSION,
        artifact_relative_path=REPOSITORY_STRUCTURE_RELATIVE_PATH,
        handler=_repository_structure_handler,
    )
)


def _structured_file_shape_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_structured_file_shape_evidence(
        repository=context.repository,
        all_files=context.all_files,
        repo_id=context.repo_id,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=STRUCTURED_FILE_SHAPE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=STRUCTURED_FILE_SHAPE_ARTIFACT_KIND,
        schema_version=STRUCTURED_FILE_SHAPE_SCHEMA_VERSION,
        artifact_relative_path=STRUCTURED_FILE_SHAPE_RELATIVE_PATH,
        handler=_structured_file_shape_handler,
    )
)


def _java_type_structure_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        unsupported = sorted(str(key) for key in parameters)
        raise ValueError(
            "java-type-structure-evidence/v1 does not accept runtime parameters: "
            + ", ".join(unsupported)
        )
    return build_java_type_structure_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=JAVA_TYPE_STRUCTURE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=JAVA_TYPE_STRUCTURE_ARTIFACT_KIND,
        schema_version=JAVA_TYPE_STRUCTURE_SCHEMA_VERSION,
        artifact_relative_path=JAVA_TYPE_STRUCTURE_RELATIVE_PATH,
        handler=_java_type_structure_handler,
    )
)


def _java_persistence_mapping_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        unsupported = sorted(str(key) for key in parameters)
        raise ValueError(
            "java-persistence-mapping-evidence/v1 does not accept runtime parameters: "
            + ", ".join(unsupported)
        )
    return build_java_persistence_mapping_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=JAVA_PERSISTENCE_MAPPING_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=JAVA_PERSISTENCE_MAPPING_ARTIFACT_KIND,
        schema_version=JAVA_PERSISTENCE_MAPPING_SCHEMA_VERSION,
        artifact_relative_path=JAVA_PERSISTENCE_MAPPING_RELATIVE_PATH,
        handler=_java_persistence_mapping_handler,
    )
)



def _model_storage_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        unsupported = sorted(str(key) for key in parameters)
        raise ValueError(
            "model-storage-evidence/v1 does not accept runtime parameters: "
            + ", ".join(unsupported)
        )
    return build_model_storage_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=MODEL_STORAGE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=MODEL_STORAGE_ARTIFACT_KIND,
        schema_version=MODEL_STORAGE_SCHEMA_VERSION,
        artifact_relative_path=MODEL_STORAGE_RELATIVE_PATH,
        handler=_model_storage_handler,
    )
)


def _storage_usage_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        unsupported = sorted(str(key) for key in parameters)
        raise ValueError(
            "storage-usage-evidence/v1 does not accept runtime parameters: "
            + ", ".join(unsupported)
        )
    return build_storage_usage_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=STORAGE_USAGE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=STORAGE_USAGE_ARTIFACT_KIND,
        schema_version=STORAGE_USAGE_SCHEMA_VERSION,
        artifact_relative_path=STORAGE_USAGE_RELATIVE_PATH,
        handler=_storage_usage_handler,
    )
)


def _sql_analysis_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_sql_analysis_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
        output_root=context.output,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=SQL_ANALYSIS_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=SQL_ANALYSIS_ARTIFACT_KIND,
        schema_version=SQL_ANALYSIS_SCHEMA_VERSION,
        artifact_relative_path=SQL_ANALYSIS_RELATIVE_PATH,
        handler=_sql_analysis_handler,
    )
)

def _system_description_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        raise ValueError("system-description-evidence/v1 does not accept runtime parameters")
    return build_system_description_evidence(
        repository=context.repository, files=list(context.files), repo_id=context.repo_id, output_root=context.output
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=SYSTEM_DESCRIPTION_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=SYSTEM_DESCRIPTION_ARTIFACT_KIND,
        schema_version=SYSTEM_DESCRIPTION_SCHEMA_VERSION,
        artifact_relative_path=SYSTEM_DESCRIPTION_RELATIVE_PATH,
        handler=_system_description_handler,
    )
)


def _reference_data_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    if parameters:
        raise ValueError("reference-data-evidence/v1 does not accept runtime parameters")
    return build_reference_data_evidence(
        repository=context.repository, files=list(context.files), repo_id=context.repo_id, output_root=context.output
    )


def _interaction_boundary_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    allowed = {"system_id", "project_id", "service_aliases"}
    unsupported = sorted(str(key) for key in parameters if str(key) not in allowed)
    if unsupported:
        raise ValueError("interaction-boundary-evidence/v1 unsupported runtime parameters: " + ", ".join(unsupported))
    return build_interaction_boundary_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
        output_root=context.output,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=INTERACTION_BOUNDARY_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=INTERACTION_BOUNDARY_ARTIFACT_KIND,
        schema_version=INTERACTION_BOUNDARY_SCHEMA_VERSION,
        artifact_relative_path=INTERACTION_BOUNDARY_RELATIVE_PATH,
        handler=_interaction_boundary_handler,
    )
)


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=REFERENCE_DATA_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=REFERENCE_DATA_ARTIFACT_KIND,
        schema_version=REFERENCE_DATA_SCHEMA_VERSION,
        artifact_relative_path=REFERENCE_DATA_RELATIVE_PATH,
        handler=_reference_data_handler,
    )
)

def _data_model_candidate_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_data_model_candidate_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
        output_root=context.output,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=DATA_MODEL_CANDIDATE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=DATA_MODEL_CANDIDATE_ARTIFACT_KIND,
        schema_version=DATA_MODEL_CANDIDATE_SCHEMA_VERSION,
        artifact_relative_path=DATA_MODEL_CANDIDATE_RELATIVE_PATH,
        handler=_data_model_candidate_handler,
    )
)


def _persistence_lineage_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_persistence_lineage_evidence(
        repository=context.repository,
        files=list(context.files),
        repo_id=context.repo_id,
        output_root=context.output,
        parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=PERSISTENCE_LINEAGE_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=PERSISTENCE_LINEAGE_ARTIFACT_KIND,
        schema_version=PERSISTENCE_LINEAGE_SCHEMA_VERSION,
        artifact_relative_path=PERSISTENCE_LINEAGE_RELATIVE_PATH,
        handler=_persistence_lineage_handler,
    )
)


def _value_flow_handler(
    context: EvidenceAnalyzerContext,
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return build_value_flow_evidence(
        repository=context.repository, files=list(context.files), repo_id=context.repo_id,
        output_root=context.output, parameters=parameters,
    )


register_evidence_analyzer(
    EvidenceAnalyzerRegistration(
        analyzer_id=VALUE_FLOW_ANALYZER_ID,
        analyzer_version=CORE_VERSION,
        artifact_kind=VALUE_FLOW_ARTIFACT_KIND,
        schema_version=VALUE_FLOW_SCHEMA_VERSION,
        artifact_relative_path=VALUE_FLOW_RELATIVE_PATH,
        handler=_value_flow_handler,
    )
)


def _validate_request(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if payload.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported Core evidence execution request schema: {payload.get('schema_version')!r}"
        )
    actual = str(payload.get("request_fingerprint") or "")
    if not actual or actual != _fingerprinted_payload(payload, field="request_fingerprint"):
        raise ValueError("Core evidence execution request fingerprint is invalid")
    source = payload.get("source") or {}
    if not isinstance(source, Mapping):
        raise ValueError("request.source must be an object")
    if str(source.get("source_kind") or "") != "repository":
        raise ValueError("request.source.source_kind must be 'repository'")
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("request.source.source_id is required")
    raw_requirements = payload.get("evidence_requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise ValueError("request.evidence_requirements must be a non-empty list")
    requirements: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_requirements:
        if not isinstance(raw, Mapping):
            raise ValueError("request.evidence_requirements contains a non-object item")
        item = dict(raw)
        kind = str(item.get("artifact_kind") or "").strip()
        version = str(item.get("schema_version") or "").strip()
        if not kind or not version:
            raise ValueError("evidence requirement must contain artifact_kind and schema_version")
        key = (kind, version)
        if key in seen:
            raise ValueError(f"duplicate evidence requirement: {kind}/{version}")
        seen.add(key)
        parameters = item.get("parameters") or {}
        if not isinstance(parameters, Mapping):
            raise ValueError(f"evidence requirement parameters must be an object: {kind}/{version}")
        required_by = item.get("required_by") or []
        if not isinstance(required_by, list):
            raise ValueError(f"evidence requirement required_by must be a list: {kind}/{version}")
        requirements.append({
            "artifact_kind": kind,
            "schema_version": version,
            "parameters": dict(parameters),
            "required_by": sorted({str(value) for value in required_by if str(value)}),
        })
    requirements.sort(key=lambda item: (item["artifact_kind"], item["schema_version"]))
    return source_id, requirements


def _validate_artifact(
    artifact: Mapping[str, Any],
    *,
    registration: EvidenceAnalyzerRegistration,
    source_id: str,
) -> None:
    if str(artifact.get("contract_version") or "") != ARTIFACT_CONTRACT_VERSION:
        raise ValueError("Core analyzer returned an unsupported evidence artifact contract")
    if str(artifact.get("artifact_kind") or "") != registration.artifact_kind:
        raise ValueError("Core analyzer returned an unexpected artifact_kind")
    if str(artifact.get("schema_version") or "") != registration.schema_version:
        raise ValueError("Core analyzer returned an unexpected schema_version")
    producer = artifact.get("producer") or {}
    if not isinstance(producer, Mapping):
        raise ValueError("Core evidence artifact producer must be an object")
    if str(producer.get("component") or "") != "code-analyzer-core":
        raise ValueError("Core evidence artifact producer.component is invalid")
    if str(producer.get("analyzer_id") or "") != registration.analyzer_id:
        raise ValueError("Core evidence artifact analyzer_id does not match runtime registration")
    if str(producer.get("analyzer_version") or "") != registration.analyzer_version:
        raise ValueError("Core evidence artifact analyzer_version does not match runtime registration")
    source_snapshot = artifact.get("source_snapshot") or {}
    if not isinstance(source_snapshot, Mapping):
        raise ValueError("Core evidence artifact source_snapshot must be an object")
    if str(source_snapshot.get("source_id") or "") != source_id:
        raise ValueError("Core evidence artifact source_snapshot.source_id does not match request")
    if not str(source_snapshot.get("fingerprint") or ""):
        raise ValueError("Core evidence artifact source_snapshot has no fingerprint")
    if not isinstance(artifact.get("coverage"), Mapping):
        raise ValueError("Core evidence artifact coverage must be an object")
    if not isinstance(artifact.get("diagnostics"), list):
        raise ValueError("Core evidence artifact diagnostics must be a list")
    actual = str(artifact.get("content_fingerprint") or "")
    fingerprint_material = {
        str(key): deepcopy(value)
        for key, value in artifact.items()
        if str(key) not in {"content_fingerprint", "artifact_id"}
    }
    if not actual or actual != _fingerprint(fingerprint_material):
        raise ValueError("Core evidence artifact content_fingerprint is invalid")
    if not str(artifact.get("artifact_id") or ""):
        raise ValueError("Core evidence artifact has no artifact_id")


def execute_evidence_request(
    *,
    repository: str | Path,
    request: Mapping[str, Any],
    output: str | Path,
    repo_id: str | None = None,
) -> dict[str, Any]:
    repository_path = Path(repository).expanduser().resolve()
    if not repository_path.is_dir():
        raise ValueError(f"repository does not exist or is not a directory: {repository_path}")
    output_path = Path(output).expanduser().resolve()
    if output_path == repository_path:
        raise ValueError("Core evidence output must not be the repository directory")
    source_id, requirements = _validate_request(request)
    if repo_id is not None and str(repo_id).strip() != source_id:
        raise ValueError("--repo-id does not match request.source.source_id")
    output_path.mkdir(parents=True, exist_ok=True)
    all_files = tuple(scan_all_files(repository_path))
    files = tuple(filter_analyzer_files(all_files))
    context = EvidenceAnalyzerContext(
        repository=repository_path,
        output=output_path,
        repo_id=source_id,
        files=files,
        all_files=all_files,
    )

    executions: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for requirement in requirements:
        key = (requirement["artifact_kind"], requirement["schema_version"])
        registration = _ANALYZERS.get(key)
        if registration is None:
            raise ValueError(
                f"no Core evidence analyzer registered for {key[0]}/{key[1]}"
            )
        artifact = registration.handler(context, requirement["parameters"])
        _validate_artifact(artifact, registration=registration, source_id=source_id)
        target = _safe_output_path(output_path, registration.artifact_relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        file_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        diagnostics = [
            dict(item)
            for item in artifact.get("diagnostics") or []
            if isinstance(item, Mapping)
        ]
        coverage = dict(artifact.get("coverage") or {})
        coverage_status = str(coverage.get("coverage_status") or "unknown")
        status = (
            "completed"
            if coverage_status in {"complete", "not_applicable"}
            else "partial"
            if coverage_status == "partial"
            else "failed"
        )
        execution_id = "core_analyzer_execution_" + _fingerprint({
            "request_fingerprint": request.get("request_fingerprint"),
            "source_id": source_id,
            "analyzer_id": registration.analyzer_id,
            "analyzer_version": registration.analyzer_version,
            "artifact_id": artifact.get("artifact_id"),
            "parameters": requirement["parameters"],
        })[:24]
        executions.append({
            "analyzer_execution_id": execution_id,
            "analyzer_id": registration.analyzer_id,
            "analyzer_version": registration.analyzer_version,
            "semantic_outputs": [{
                "artifact_kind": registration.artifact_kind,
                "schema_version": registration.schema_version,
            }],
            "source_snapshot_ids": [source_id],
            "source_snapshot_fingerprints": [str((artifact.get("source_snapshot") or {}).get("fingerprint"))],
            "parameters": requirement["parameters"],
            "required_by": requirement["required_by"],
            "status": status,
            "artifact_ids": [artifact.get("artifact_id")],
        })
        artifacts.append({
            "artifact_id": artifact.get("artifact_id"),
            "artifact_kind": registration.artifact_kind,
            "schema_version": registration.schema_version,
            "contract_version": artifact.get("contract_version"),
            "producer_analyzer_execution_id": execution_id,
            "content_fingerprint": artifact.get("content_fingerprint"),
            "status": status,
            "coverage": coverage,
            "diagnostics": _diagnostic_summary(diagnostics),
            "provenance": {
                "source_snapshot": dict(artifact.get("source_snapshot") or {}),
                "foundation": dict(artifact.get("foundation") or {}),
                "producer": dict(artifact.get("producer") or {}),
                "core_artifact_provenance": dict(artifact.get("provenance") or {}),
                "required_by": requirement["required_by"],
            },
            "location": {
                "kind": "file",
                "path": registration.artifact_relative_path,
                "sha256": file_sha256,
                "bytes": target.stat().st_size,
            },
        })

    source_snapshots_by_fp: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        snapshot = dict((artifact.get("provenance") or {}).get("source_snapshot") or {})
        fingerprint = str(snapshot.get("fingerprint") or "")
        if fingerprint:
            source_snapshots_by_fp[fingerprint] = snapshot
    status = "completed"
    if any(item["status"] == "failed" for item in artifacts):
        status = "failed"
    elif any(item["status"] == "partial" for item in artifacts):
        status = "partial"
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "runtime_contract_id": RUNTIME_CONTRACT_ID,
        "producer": {"component": "code-analyzer-core", "version": CORE_VERSION},
        "request_fingerprint": request.get("request_fingerprint"),
        "source": {"source_kind": "repository", "source_id": source_id},
        "source_snapshots": [source_snapshots_by_fp[key] for key in sorted(source_snapshots_by_fp)],
        "analyzer_executions": executions,
        "evidence_artifacts": artifacts,
        "status": status,
        "diagnostics": [],
    }
    result["execution_id"] = "core_evidence_execution_" + _fingerprint({
        "request_fingerprint": request.get("request_fingerprint"),
        "source_id": source_id,
        "analyzers": [
            (item["analyzer_id"], item["analyzer_version"], tuple(item["artifact_ids"]))
            for item in executions
        ],
    })[:24]
    result["result_fingerprint"] = _fingerprinted_payload(result, field="result_fingerprint")
    result_path = output_path / "core-evidence-execution-result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result
