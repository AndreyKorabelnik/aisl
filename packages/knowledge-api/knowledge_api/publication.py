from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .contract_v1.models import (
    KnowledgeExecutionSummary,
    PublishedArtifact,
    RevisionCreateRequest,
)
from .contract_v1.runtime import KnowledgeApiRuntimeError, sha256_file

DUCKDB_MEDIA_TYPE = "application/vnd.duckdb"
JSON_MEDIA_TYPE = "application/json"
KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION = "knowledge_execution_result/v2"
KNOWLEDGE_LAYER_MANIFEST_SCHEMA_VERSION = "knowledge_layer/v1"


@dataclass(frozen=True, slots=True)
class KnowledgeArtifactFiles:
    artifact: dict[str, Any]
    database_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedPhysicalFile:
    role: str
    path: Path
    schema_version: str | None
    media_type: str


@dataclass(frozen=True, slots=True)
class ObservedArtifactFiles:
    artifact: dict[str, Any]
    descriptor_path: Path
    payload: dict[str, Any]
    physical_files: tuple[ObservedPhysicalFile, ...]


# First two physical shapes proven by AISL persistence acceptance:
# - self-contained Core JSON descriptor/payload;
# - descriptor + canonical SQL manifest/coverage/JSONL fact shards.
PUBLISHABLE_OBSERVED_PRODUCTS = {
    ("java-type-structure-evidence", "java-type-structure-evidence/v1"),
    ("sql-analysis", "sql-analysis/v1"),
}


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeApiRuntimeError(
            400,
            "json_artifact_unavailable",
            f"JSON artifact is unavailable: {path}",
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeApiRuntimeError(
            400,
            "json_artifact_invalid",
            f"artifact must be readable UTF-8 JSON: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise KnowledgeApiRuntimeError(400, "json_artifact_invalid", "JSON artifact root must be an object")
    return value


def parse_metadata_values(values: Iterable[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in values:
        if "=" not in raw:
            raise KnowledgeApiRuntimeError(400, "metadata_invalid", f"metadata must use key=value syntax: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise KnowledgeApiRuntimeError(400, "metadata_invalid", "metadata key must not be empty")
        result[key] = _parse_scalar(value.strip())
    return result


def merge_metadata_file(values: dict[str, Any], path: Path | None) -> dict[str, Any]:
    if path is None:
        return values
    loaded = load_json_object(path)
    return {**loaded, **values}


def build_artifact(
    path: Path,
    *,
    schema_version: str | None = None,
    media_type: str | None = None,
) -> PublishedArtifact:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise KnowledgeApiRuntimeError(400, "artifact_unavailable", f"artifact file is unavailable: {resolved}")
    if media_type is None:
        if resolved.suffix.casefold() == ".json":
            media_type = JSON_MEDIA_TYPE
        else:
            media_type = DUCKDB_MEDIA_TYPE
    return PublishedArtifact(
        uri=resolved.as_uri(),
        sha256=sha256_file(resolved),
        media_type=media_type,
        schema_version=schema_version,
        byte_size=resolved.stat().st_size,
        filename=resolved.name,
    )


def build_publication_request(
    *,
    execution_result: Path,
    base_revision_id: str | None = None,
    labels: Iterable[str],
    metadata: dict[str, Any],
    activate: bool,
) -> tuple[RevisionCreateRequest, list[str]]:
    execution_path = execution_result.expanduser().resolve()
    payload = validate_knowledge_execution_result(load_json_object(execution_path))
    request = RevisionCreateRequest(
        base_revision_id=base_revision_id,
        execution_result=build_artifact(
            execution_path,
            schema_version=KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION,
            media_type=JSON_MEDIA_TYPE,
        ),
        activate=activate,
        labels=list(dict.fromkeys(labels)),
        metadata=metadata,
    )
    warnings: list[str] = []
    if not payload.get("knowledge_artifacts") and not payload.get("evidence_artifacts"):
        warnings.append("execution result contains no producer artifacts")
    return request, warnings


def stable_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _execution_result_validator() -> Draft202012Validator:
    schema_path = files("knowledge_api.schemas").joinpath("knowledge_execution_result_v2.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_execution_result_schema(payload: Mapping[str, Any]) -> None:
    errors = sorted(
        _execution_result_validator().iter_errors(dict(payload)),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    path = "/".join(str(item) for item in error.absolute_path)
    raise KnowledgeApiRuntimeError(
        400,
        "knowledge_execution_result_contract_invalid",
        "knowledge execution result does not satisfy knowledge_execution_result/v2",
        details={
            "path": path or "$",
            "validator": str(error.validator),
            "message": error.message,
            "error_count": len(errors),
        },
    )


def validate_knowledge_execution_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    _validate_execution_result_schema(payload)
    if str(payload.get("schema_version") or "") != KNOWLEDGE_EXECUTION_RESULT_SCHEMA_VERSION:
        raise KnowledgeApiRuntimeError(
            400,
            "knowledge_execution_result_schema_unsupported",
            f"unsupported execution result schema: {payload.get('schema_version')!r}",
        )
    actual_fingerprint = str(payload.get("result_fingerprint") or "")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != "result_fingerprint"}
    expected_fingerprint = stable_fingerprint(material)
    if not actual_fingerprint or actual_fingerprint != expected_fingerprint:
        raise KnowledgeApiRuntimeError(
            409,
            "knowledge_execution_result_fingerprint_invalid",
            "knowledge execution result fingerprint is invalid",
            details={"expected": expected_fingerprint, "actual": actual_fingerprint},
        )
    if str(payload.get("status") or "") != "completed":
        raise KnowledgeApiRuntimeError(
            400,
            "knowledge_execution_incomplete",
            "only completed knowledge executions can be published",
        )
    node_executions = payload.get("node_executions") or []
    if not isinstance(node_executions, list):
        raise KnowledgeApiRuntimeError(400, "knowledge_execution_result_invalid", "node_executions must be a list")
    execution_order = [str(value) for value in payload.get("execution_order") or []]
    actual_order = [
        str(item.get("execution_node_id") or "")
        for item in node_executions
        if isinstance(item, Mapping)
    ]
    if execution_order != actual_order:
        raise KnowledgeApiRuntimeError(
            409,
            "knowledge_execution_order_invalid",
            "node execution order does not match the execution plan",
        )
    if any(
        str(item.get("status") or "") != "completed"
        for item in node_executions
        if isinstance(item, Mapping)
    ):
        raise KnowledgeApiRuntimeError(400, "knowledge_execution_incomplete", "execution contains an incomplete node")

    policy = payload.get("semantic_policy") or {}
    required_policy = {
        "capability_publication": "completed_materialization_results_only",
    }
    invalid_policy = {
        key: policy.get(key)
        for key, expected in required_policy.items()
        if policy.get(key) != expected
    }
    if invalid_policy:
        raise KnowledgeApiRuntimeError(
            400,
            "knowledge_execution_policy_invalid",
            "knowledge execution result enables a forbidden or unsupported semantic policy",
            details={"invalid": invalid_policy, "required": required_policy},
        )

    artifacts = payload.get("knowledge_artifacts") or []
    if not isinstance(artifacts, list):
        raise KnowledgeApiRuntimeError(
            400,
            "knowledge_execution_result_invalid",
            "knowledge_artifacts must be a list",
        )
    artifact_ids: set[str] = set()
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise KnowledgeApiRuntimeError(400, "knowledge_artifact_invalid", "knowledge artifact must be an object")
        required = (
            "artifact_id",
            "model_kind",
            "schema_version",
            "source_materialization_id",
            "content_fingerprint",
        )
        missing = [key for key in required if not str(raw.get(key) or "")]
        if missing:
            raise KnowledgeApiRuntimeError(
                400,
                "knowledge_artifact_invalid",
                "knowledge artifact is incomplete",
                details={"missing": missing},
            )
        artifact_id = str(raw["artifact_id"])
        if artifact_id in artifact_ids:
            raise KnowledgeApiRuntimeError(409, "knowledge_artifact_duplicate", f"duplicate artifact id: {artifact_id}")
        artifact_ids.add(artifact_id)
        if str(raw.get("status") or "completed") != "completed":
            raise KnowledgeApiRuntimeError(400, "knowledge_artifact_incomplete", f"artifact is incomplete: {artifact_id}")

    external_artifacts = payload.get("external_knowledge_artifacts") or []
    if not isinstance(external_artifacts, list):
        raise KnowledgeApiRuntimeError(400, "knowledge_execution_result_invalid", "external_knowledge_artifacts must be a list")
    external_ids: set[str] = set()
    for raw in external_artifacts:
        if not isinstance(raw, Mapping):
            raise KnowledgeApiRuntimeError(400, "external_knowledge_artifact_invalid", "external knowledge artifact must be an object")
        required = (
            "artifact_id", "model_kind", "schema_version", "source_materialization_id",
            "content_fingerprint", "source_system_id", "source_revision_id",
        )
        missing = [key for key in required if not str(raw.get(key) or "").strip()]
        if missing:
            raise KnowledgeApiRuntimeError(
                400, "external_knowledge_artifact_invalid", "external knowledge artifact is incomplete",
                details={"missing": missing},
            )
        artifact_id = str(raw["artifact_id"])
        if artifact_id in artifact_ids or artifact_id in external_ids:
            raise KnowledgeApiRuntimeError(409, "knowledge_artifact_duplicate", f"duplicate knowledge artifact id: {artifact_id}")
        external_ids.add(artifact_id)

    materializations = payload.get("materialization_executions") or []
    if not isinstance(materializations, list):
        raise KnowledgeApiRuntimeError(400, "knowledge_execution_result_invalid", "materialization_executions must be a list")
    capability_union: set[str] = set()
    produced_artifact_ids: set[str] = set()
    input_knowledge_artifact_ids: set[str] = set()
    for raw in materializations:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("status") or "") != "completed":
            raise KnowledgeApiRuntimeError(400, "knowledge_execution_incomplete", "materialization is incomplete")
        capability_union.update(str(value) for value in raw.get("published_capabilities") or [] if str(value))
        produced_artifact_ids.update(str(value) for value in raw.get("knowledge_artifact_ids") or [] if str(value))
        input_knowledge_artifact_ids.update(
            str(value) for value in raw.get("input_knowledge_artifact_ids") or [] if str(value)
        )
    unresolved_inputs = sorted(input_knowledge_artifact_ids - artifact_ids - external_ids)
    if unresolved_inputs:
        raise KnowledgeApiRuntimeError(
            409, "knowledge_dependency_unresolved",
            "materialization references knowledge inputs absent from produced and external artifact registries",
            details={"artifact_ids": unresolved_inputs},
        )
    expected_external_ids = input_knowledge_artifact_ids - artifact_ids
    if external_ids != expected_external_ids:
        raise KnowledgeApiRuntimeError(
            409, "external_knowledge_artifact_registration_invalid",
            "external knowledge artifact registry must contain exactly the consumed prior-revision inputs",
            details={
                "missing": sorted(expected_external_ids - external_ids),
                "unexpected": sorted(external_ids - expected_external_ids),
            },
        )
    published_capabilities = {str(value) for value in payload.get("published_capabilities") or [] if str(value)}
    if published_capabilities != capability_union:
        raise KnowledgeApiRuntimeError(
            409,
            "published_capabilities_invalid",
            "execution-level capabilities do not equal completed materialization capabilities",
            details={
                "missing": sorted(capability_union - published_capabilities),
                "unexpected": sorted(published_capabilities - capability_union),
            },
        )
    if artifact_ids != produced_artifact_ids:
        raise KnowledgeApiRuntimeError(
            409,
            "knowledge_artifact_registration_invalid",
            "execution-level knowledge artifacts do not match completed materialization outputs",
            details={
                "missing": sorted(produced_artifact_ids - artifact_ids),
                "unexpected": sorted(artifact_ids - produced_artifact_ids),
            },
        )
    return deepcopy(dict(payload))


def execution_summary(payload: Mapping[str, Any]) -> KnowledgeExecutionSummary:
    runner = payload.get("runner") or {}
    plan = payload.get("knowledge_execution_plan") or {}
    request = payload.get("request") or {}
    scope = payload.get("scope") or {}
    return KnowledgeExecutionSummary(
        runner_version=str(runner.get("version") or ""),
        result_fingerprint=str(payload.get("result_fingerprint") or ""),
        plan_fingerprint=str(plan.get("plan_fingerprint") or ""),
        knowledge_profile_id=str(request.get("knowledge_profile_id") or ""),
        scope_kind=str(scope.get("kind") or ""),
        scope_id=str(scope.get("scope_id") or ""),
        started_at=payload.get("started_at"),
        completed_at=payload.get("completed_at"),
        semantic_policy=dict(payload.get("semantic_policy") or {}),
    )


def discover_knowledge_artifact_files(
    payload: Mapping[str, Any],
    *,
    execution_result_path: Path,
    path_guard: Callable[..., Path] | None = None,
) -> list[KnowledgeArtifactFiles]:
    base = execution_result_path.expanduser().resolve().parent
    capabilities_by_materialization: dict[str, tuple[str, ...]] = {}
    for raw in payload.get("materialization_executions") or []:
        if not isinstance(raw, Mapping):
            continue
        materialization_id = str(raw.get("materialization_id") or "")
        capabilities_by_materialization[materialization_id] = tuple(
            sorted({str(value) for value in raw.get("published_capabilities") or [] if str(value)})
        )

    result: list[KnowledgeArtifactFiles] = []
    for raw in payload.get("knowledge_artifacts") or []:
        artifact = deepcopy(dict(raw))
        location = artifact.get("location") or {}
        if not isinstance(location, Mapping) or str(location.get("kind") or "") != "knowledge-layer":
            raise KnowledgeApiRuntimeError(
                400,
                "knowledge_artifact_location_invalid",
                f"artifact {artifact.get('artifact_id')!r} has no knowledge-layer location",
            )
        output_path = _resolve_execution_path(location.get("output_path"), base)
        manifest_path = _resolve_execution_path(location.get("manifest_path"), base)
        if path_guard is not None:
            output_path = path_guard(output_path, directory=True)
            manifest_path = path_guard(manifest_path, directory=False)
        manifest = load_json_object(manifest_path)
        if str(manifest.get("schema_version") or "") != KNOWLEDGE_LAYER_MANIFEST_SCHEMA_VERSION:
            raise KnowledgeApiRuntimeError(
                400,
                "knowledge_artifact_manifest_schema_unsupported",
                f"unsupported Knowledge Layer manifest schema: {manifest.get('schema_version')!r}",
            )
        if str(manifest.get("build_status") or "") != "complete":
            raise KnowledgeApiRuntimeError(
                400,
                "knowledge_artifact_incomplete",
                f"Knowledge Layer build is incomplete: {artifact.get('artifact_id')}",
            )
        validation = manifest.get("validation") or {}
        if isinstance(validation, Mapping) and validation.get("status") not in {None, "complete"}:
            raise KnowledgeApiRuntimeError(
                400,
                "knowledge_artifact_invalid",
                f"Knowledge Layer validation is incomplete: {artifact.get('artifact_id')}",
            )
        database_value = manifest.get("database_path") or (manifest.get("artifacts") or {}).get("database")
        if not database_value:
            database_value = "knowledge-layer.duckdb"
        database_path = Path(str(database_value))
        if not database_path.is_absolute():
            database_path = (manifest_path.parent / database_path).resolve()
        else:
            database_path = database_path.expanduser().resolve()
        if path_guard is not None:
            database_path = path_guard(database_path, directory=False)
        if output_path != manifest_path.parent:
            raise KnowledgeApiRuntimeError(
                409,
                "knowledge_artifact_location_inconsistent",
                f"artifact output path and manifest parent differ: {artifact.get('artifact_id')}",
            )
        materialization_id = str(artifact.get("source_materialization_id") or "")
        capabilities = capabilities_by_materialization.get(materialization_id)
        if capabilities is None:
            raise KnowledgeApiRuntimeError(
                409,
                "knowledge_artifact_materialization_missing",
                f"artifact references unknown completed materialization: {materialization_id}",
            )
        manifest_capabilities = tuple(sorted({str(value) for value in manifest.get("capabilities") or [] if str(value)}))
        if manifest_capabilities != capabilities:
            raise KnowledgeApiRuntimeError(
                409,
                "knowledge_artifact_capabilities_invalid",
                f"manifest capabilities differ from materialization result: {artifact.get('artifact_id')}",
                details={"manifest": list(manifest_capabilities), "materialization": list(capabilities)},
            )
        result.append(
            KnowledgeArtifactFiles(
                artifact=artifact,
                database_path=database_path,
                manifest_path=manifest_path,
                manifest=manifest,
                capabilities=capabilities,
            )
        )
    return result




def _safe_observed_package_child(base: Path, relative: Any, *, artifact_id: str) -> Path:
    text = str(relative or "").strip()
    candidate = Path(text)
    if not text or candidate.is_absolute() or ".." in candidate.parts:
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_path_invalid",
            "observed product package member must be a safe descriptor-relative path",
            details={"artifact_id": artifact_id, "path": text},
        )
    root = base.expanduser().resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_path_invalid",
            "observed product package member escapes the descriptor root",
            details={"artifact_id": artifact_id, "path": text},
        ) from exc
    return resolved


def _verify_file_identity(
    path: Path,
    *,
    expected_sha256: str | None,
    expected_bytes: int | None,
    artifact_id: str,
    role: str,
) -> None:
    if not path.is_file():
        raise KnowledgeApiRuntimeError(
            400,
            "observed_artifact_package_member_unavailable",
            "observed product package member is unavailable",
            details={"artifact_id": artifact_id, "role": role, "path": str(path)},
        )
    actual_size = path.stat().st_size
    if expected_bytes is not None and actual_size != int(expected_bytes):
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_size_mismatch",
            "observed product package member size differs from its descriptor",
            details={"artifact_id": artifact_id, "role": role, "expected": int(expected_bytes), "actual": actual_size},
        )
    if expected_sha256:
        actual_sha = sha256_file(path)
        if actual_sha != str(expected_sha256):
            raise KnowledgeApiRuntimeError(
                409,
                "observed_artifact_digest_mismatch",
                "observed product package member digest differs from its descriptor",
                details={"artifact_id": artifact_id, "role": role, "expected": str(expected_sha256), "actual": actual_sha},
            )


def _discover_sql_analysis_physical_files(
    observed_payload: Mapping[str, Any],
    *,
    descriptor_path: Path,
    path_guard: Callable[..., Path] | None,
) -> tuple[ObservedPhysicalFile, ...]:
    artifact_id = str(observed_payload.get("artifact_id") or "")
    payload = observed_payload.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise KnowledgeApiRuntimeError(409, "observed_artifact_package_invalid", "sql-analysis evidence payload must be an object")
    manifest_path = _safe_observed_package_child(
        descriptor_path.parent,
        payload.get("canonical_manifest_path"),
        artifact_id=artifact_id,
    )
    if path_guard is not None:
        manifest_path = path_guard(manifest_path, directory=False)
    manifest = load_json_object(manifest_path)
    if str(manifest.get("artifact") or "") != "sql_analysis" or str(manifest.get("schema_version") or "") != "sql-analysis/v1":
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_manifest_invalid",
            "sql-analysis canonical manifest identity is invalid",
            details={"artifact_id": artifact_id},
        )
    expected_content = str(payload.get("canonical_content_fingerprint") or "")
    if not expected_content or str(manifest.get("content_fingerprint") or "") != expected_content:
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_identity_mismatch",
            "sql-analysis canonical manifest content identity differs from the Core evidence descriptor",
            details={"artifact_id": artifact_id, "descriptor": expected_content, "manifest": str(manifest.get("content_fingerprint") or "")},
        )

    descriptor_shards = payload.get("fact_shards") or []
    manifest_shards = manifest.get("facts") or []
    if not isinstance(descriptor_shards, list) or not isinstance(manifest_shards, list):
        raise KnowledgeApiRuntimeError(409, "observed_artifact_package_invalid", "sql-analysis fact shard descriptors must be arrays")
    descriptor_by_type = {str(item.get("fact_type") or ""): item for item in descriptor_shards if isinstance(item, Mapping)}
    if len(descriptor_by_type) != len(descriptor_shards) or not descriptor_by_type:
        raise KnowledgeApiRuntimeError(409, "observed_artifact_package_invalid", "sql-analysis fact shard identities must be unique and non-empty")
    manifest_by_type = {str(item.get("fact_type") or ""): item for item in manifest_shards if isinstance(item, Mapping)}
    if set(descriptor_by_type) != set(manifest_by_type) or len(manifest_by_type) != len(manifest_shards):
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_manifest_mismatch",
            "sql-analysis descriptor and canonical manifest enumerate different fact shards",
            details={"artifact_id": artifact_id},
        )

    physical: list[ObservedPhysicalFile] = [
        ObservedPhysicalFile("descriptor", descriptor_path, "sql-analysis/v1", JSON_MEDIA_TYPE),
        ObservedPhysicalFile("manifest", manifest_path, "sql-analysis/v1", JSON_MEDIA_TYPE),
    ]
    for fact_type in sorted(descriptor_by_type):
        descriptor_entry = descriptor_by_type[fact_type]
        manifest_entry = manifest_by_type[fact_type]
        descriptor_relative = str(descriptor_entry.get("path") or "")
        manifest_relative = str(Path("sql-analysis") / str(manifest_entry.get("path") or ""))
        comparable = ("sha256", "byte_size", "record_count", "id_field")
        mismatch = {
            key: {"descriptor": descriptor_entry.get(key), "manifest": manifest_entry.get(key)}
            for key in comparable
            if descriptor_entry.get(key) != manifest_entry.get(key)
        }
        if descriptor_relative != manifest_relative:
            mismatch["path"] = {"descriptor": descriptor_relative, "manifest": manifest_relative}
        if mismatch:
            raise KnowledgeApiRuntimeError(
                409,
                "observed_artifact_package_manifest_mismatch",
                "sql-analysis descriptor and canonical manifest disagree about a fact shard",
                details={"artifact_id": artifact_id, "fact_type": fact_type, "mismatch": mismatch},
            )
        shard_path = _safe_observed_package_child(descriptor_path.parent, descriptor_relative, artifact_id=artifact_id)
        if path_guard is not None:
            shard_path = path_guard(shard_path, directory=False)
        role = f"fact:{fact_type}"
        _verify_file_identity(
            shard_path,
            expected_sha256=str(descriptor_entry.get("sha256") or ""),
            expected_bytes=int(descriptor_entry.get("byte_size") or 0),
            artifact_id=artifact_id,
            role=role,
        )
        physical.append(ObservedPhysicalFile(role, shard_path, "sql-analysis/v1", "application/x-ndjson"))

    coverage_relative = str(payload.get("coverage_path") or "")
    manifest_coverage = manifest.get("coverage") or {}
    if not isinstance(manifest_coverage, Mapping):
        raise KnowledgeApiRuntimeError(409, "observed_artifact_package_manifest_invalid", "sql-analysis manifest coverage descriptor must be an object")
    expected_coverage_relative = str(Path("sql-analysis") / str(manifest_coverage.get("path") or ""))
    if coverage_relative != expected_coverage_relative:
        raise KnowledgeApiRuntimeError(
            409,
            "observed_artifact_package_manifest_mismatch",
            "sql-analysis descriptor and canonical manifest disagree about coverage path",
            details={"artifact_id": artifact_id, "descriptor": coverage_relative, "manifest": expected_coverage_relative},
        )
    coverage_path = _safe_observed_package_child(descriptor_path.parent, coverage_relative, artifact_id=artifact_id)
    if path_guard is not None:
        coverage_path = path_guard(coverage_path, directory=False)
    _verify_file_identity(
        coverage_path,
        expected_sha256=str(manifest_coverage.get("sha256") or ""),
        expected_bytes=int(manifest_coverage.get("byte_size") or 0),
        artifact_id=artifact_id,
        role="coverage",
    )
    physical.append(ObservedPhysicalFile("coverage", coverage_path, "sql-analysis/v1", JSON_MEDIA_TYPE))
    return tuple(sorted(physical, key=lambda item: item.role))

def observed_product_slot_id(artifact: Mapping[str, Any], *, payload: Mapping[str, Any] | None = None) -> str:
    """Return the stable copy-on-write slot for one observed Core product.

    Observed products are source-scoped: two repositories may legitimately
    publish the same artifact kind into one system revision.  The slot must
    therefore include stable source identity, while deliberately excluding
    snapshot fingerprint/revision because those change when the source changes.
    """
    artifact_kind = str(artifact.get("artifact_kind") or "").strip()
    provenance = artifact.get("provenance") or {}
    source_snapshot = provenance.get("source_snapshot") if isinstance(provenance, Mapping) else None
    if not isinstance(source_snapshot, Mapping) and payload is not None:
        candidate = payload.get("source_snapshot")
        source_snapshot = candidate if isinstance(candidate, Mapping) else None
    source_id = str((source_snapshot or {}).get("source_id") or "").strip()
    if not artifact_kind:
        raise KnowledgeApiRuntimeError(400, "observed_artifact_kind_missing", "observed artifact kind is required for product slot identity")
    if not source_id:
        raise KnowledgeApiRuntimeError(400, "observed_artifact_source_identity_missing", "observed artifact source_id is required for product slot identity", details={"artifact_kind": artifact_kind, "artifact_id": str(artifact.get("artifact_id") or "")})
    safe_source_id = source_id
    if len(source_id) > 120 or not source_id[0].isalnum() or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-" for ch in source_id):
        safe_source_id = "source-" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    slot = f"core:{safe_source_id}:{artifact_kind}"
    if len(slot) > 240:
        raise KnowledgeApiRuntimeError(400, "observed_product_slot_identity_too_long", "observed product slot identity exceeds contract limit", details={"source_id": source_id, "artifact_kind": artifact_kind})
    return slot


def discover_observed_artifact_files(
    payload: Mapping[str, Any],
    *,
    execution_result_path: Path,
    path_guard: Callable[..., Path] | None = None,
) -> list[ObservedArtifactFiles]:
    base = execution_result_path.expanduser().resolve().parent
    result: list[ObservedArtifactFiles] = []
    seen_slots: set[str] = set()
    for raw in payload.get("evidence_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        artifact = deepcopy(dict(raw))
        artifact_kind = str(artifact.get("artifact_kind") or "")
        schema_version = str(artifact.get("schema_version") or "")
        if (artifact_kind, schema_version) not in PUBLISHABLE_OBSERVED_PRODUCTS:
            continue
        observed_status = str(artifact.get("status") or "")
        if observed_status not in {"completed", "partial"}:
            raise KnowledgeApiRuntimeError(400, "observed_artifact_incomplete", f"observed artifact is not publishable: {artifact.get('artifact_id')}")
        if str(artifact.get("contract_version") or "") != "core_evidence_artifact_contract/v1":
            raise KnowledgeApiRuntimeError(400, "observed_artifact_contract_unsupported", f"unsupported Core evidence envelope: {artifact.get('contract_version')!r}")
        location = artifact.get("location") or {}
        if not isinstance(location, Mapping) or str(location.get("kind") or "") != "file":
            raise KnowledgeApiRuntimeError(400, "observed_artifact_location_invalid", f"observed artifact {artifact.get('artifact_id')!r} is not a self-contained file")
        artifact_path = _resolve_execution_path(location.get("path"), base)
        if path_guard is not None:
            artifact_path = path_guard(artifact_path, directory=False)
        expected_sha = str(location.get("sha256") or "")
        expected_bytes = location.get("bytes")
        if expected_sha and sha256_file(artifact_path) != expected_sha:
            raise KnowledgeApiRuntimeError(409, "observed_artifact_digest_mismatch", "Core evidence descriptor digest does not match artifact bytes", details={"artifact_id": str(artifact.get("artifact_id") or "")})
        if expected_bytes is not None and artifact_path.stat().st_size != int(expected_bytes):
            raise KnowledgeApiRuntimeError(409, "observed_artifact_size_mismatch", "Core evidence descriptor size does not match artifact bytes", details={"artifact_id": str(artifact.get("artifact_id") or "")})
        observed_payload = load_json_object(artifact_path)
        comparable = {
            "artifact_id": str(artifact.get("artifact_id") or ""),
            "artifact_kind": artifact_kind,
            "schema_version": schema_version,
            "content_fingerprint": str(artifact.get("content_fingerprint") or ""),
        }
        mismatched = {key: {"descriptor": value, "payload": str(observed_payload.get(key) or "")} for key, value in comparable.items() if value != str(observed_payload.get(key) or "")}
        if mismatched:
            raise KnowledgeApiRuntimeError(409, "observed_artifact_identity_mismatch", "Core evidence descriptor and payload identities differ", details={"mismatched": mismatched})
        slot = observed_product_slot_id(artifact, payload=observed_payload)
        if slot in seen_slots:
            raise KnowledgeApiRuntimeError(409, "observed_product_slot_ambiguous", "execution contains multiple observed artifacts for one Core product slot", details={"product_slot_id": slot})
        seen_slots.add(slot)
        if artifact_kind == "sql-analysis":
            physical_files = _discover_sql_analysis_physical_files(
                observed_payload,
                descriptor_path=artifact_path,
                path_guard=path_guard,
            )
        else:
            physical_files = (ObservedPhysicalFile("descriptor", artifact_path, schema_version, JSON_MEDIA_TYPE),)
        result.append(ObservedArtifactFiles(artifact=artifact, descriptor_path=artifact_path, payload=observed_payload, physical_files=physical_files))
    return result

def _resolve_execution_path(value: Any, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise KnowledgeApiRuntimeError(400, "knowledge_artifact_location_invalid", "artifact path is empty")
    candidate = Path(text).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _parse_scalar(value: str) -> Any:
    if value.lower() == "null":
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
