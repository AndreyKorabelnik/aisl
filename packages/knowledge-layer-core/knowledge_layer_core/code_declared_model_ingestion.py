from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .metrics import canonical_json
from prepared_knowledge_runtime.normalization import stable_id
from .code_declared_model_schema import (
    CODE_DECLARED_MODEL_RUN_MANIFEST_SCHEMA_VERSION,
    CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION,
)

_ARTIFACT_KIND = "java-type-structure-evidence"
_ARTIFACT_CONTRACT = "core_evidence_artifact_contract/v1"
_PAYLOAD_SECTIONS = (
    "source_units",
    "type_declarations",
    "field_declarations",
    "inheritance_declarations",
    "annotation_declarations",
    "type_reference_observations",
    "enum_constant_declarations",
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValueError(f"invalid JSON object: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _content_fingerprint(artifact: Mapping[str, Any]) -> str:
    material = {
        str(key): value
        for key, value in artifact.items()
        if str(key) not in {"content_fingerprint", "artifact_id"}
    }
    data = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _safe_child(root: Path, value: object, *, label: str) -> Path:
    text = str(value or "").strip()
    if not text or Path(text).is_absolute():
        raise ValueError(f"{label} must be run-root-relative")
    candidate = (root / text).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes run root: {text}") from exc
    return candidate


def _require_list(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"java type structure payload section {key!r} must be a list")
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _unique_ids(rows: Sequence[Mapping[str, Any]], key: str, section: str) -> None:
    values = [str(item.get(key) or "").strip() for item in rows]
    if any(not value for value in values):
        raise ValueError(f"{section} contains a record without {key}")
    if len(values) != len(set(values)):
        raise ValueError(f"{section} contains duplicate {key} values")


@dataclass(frozen=True, slots=True)
class ResolvedJavaTypeStructureArtifact:
    runner_manifest_path: Path
    run_root: Path
    runner_manifest: dict[str, Any]
    repo_id: str
    runner_version: str | None
    registration: dict[str, Any]
    artifact_path: Path
    artifact_sha256: str
    artifact: dict[str, Any]
    payload: dict[str, list[dict[str, Any]]]
    source_occurrence_id: str


def resolve_java_type_structure_artifact(runner_manifest: str | Path) -> ResolvedJavaTypeStructureArtifact:
    manifest_path = Path(runner_manifest).expanduser().resolve()
    manifest = _read_object(manifest_path)
    if manifest.get("schema_version") != CODE_DECLARED_MODEL_RUN_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported Runner manifest schema: {manifest.get('schema_version')!r}")
    repository = manifest.get("repository") or {}
    repo_id = str(repository.get("repo_id") or "").strip()
    if not repo_id:
        raise ValueError("Runner manifest has no repository.repo_id")
    registrations = [
        dict(item)
        for item in (manifest.get("evidence_artifacts") or [])
        if isinstance(item, Mapping)
        and str(item.get("artifact_kind") or "") == _ARTIFACT_KIND
        and str(item.get("schema_version") or "") == CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION
    ]
    if len(registrations) != 1:
        raise ValueError(
            f"Runner manifest must register exactly one {_ARTIFACT_KIND}/{CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION}; found={len(registrations)}"
        )
    registration = registrations[0]
    if str(registration.get("status") or "") not in {"completed", "partial"}:
        raise ValueError(f"typed evidence registration is not usable: {registration.get('status')!r}")
    semantic = registration.get("semantic_identity") or {}
    if semantic != {"artifact_kind": _ARTIFACT_KIND, "schema_version": CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION}:
        raise ValueError("typed evidence semantic_identity is invalid")
    location = registration.get("location") or {}
    if str(location.get("kind") or "") != "file":
        raise ValueError("typed evidence location.kind must be 'file'")
    run_root = manifest_path.parent.resolve()
    artifact_path = _safe_child(run_root, location.get("path"), label="typed evidence location.path")
    if not artifact_path.is_file():
        raise FileNotFoundError(artifact_path)
    actual_sha = _sha256_file(artifact_path)
    if str(location.get("sha256") or "") != actual_sha:
        raise ValueError("typed evidence file SHA-256 does not match Runner registration")
    artifact = _read_object(artifact_path)
    if artifact.get("contract_version") != _ARTIFACT_CONTRACT:
        raise ValueError("unsupported Core evidence artifact contract")
    if artifact.get("artifact_kind") != _ARTIFACT_KIND or artifact.get("schema_version") != CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION:
        raise ValueError("unexpected Core evidence semantic identity")
    expected_fingerprint = _content_fingerprint(artifact)
    content_fingerprint = str(artifact.get("content_fingerprint") or "")
    if content_fingerprint != expected_fingerprint:
        raise ValueError("Core evidence content_fingerprint is invalid")
    if str(registration.get("content_fingerprint") or "") != content_fingerprint:
        raise ValueError("Runner registration fingerprint does not match Core artifact")
    if str(registration.get("artifact_id") or "") != str(artifact.get("artifact_id") or ""):
        raise ValueError("Runner registration artifact_id does not match Core artifact")
    producer = artifact.get("producer") or {}
    if str(producer.get("analyzer_id") or "") != "java-type-structure-analyzer":
        raise ValueError("unexpected Core analyzer_id")
    source_snapshot = artifact.get("source_snapshot") or {}
    if str(source_snapshot.get("source_id") or "") != repo_id:
        raise ValueError("Core source_snapshot.source_id does not match Runner repository.repo_id")
    if not str(source_snapshot.get("fingerprint") or ""):
        raise ValueError("Core source snapshot has no fingerprint")
    if not isinstance(artifact.get("coverage"), Mapping):
        raise ValueError("Core evidence has no coverage object")
    if not isinstance(artifact.get("diagnostics"), list):
        raise ValueError("Core evidence diagnostics must be a list")
    raw_payload = artifact.get("payload")
    if not isinstance(raw_payload, Mapping):
        raise ValueError("Core evidence payload must be an object")
    payload = {section: _require_list(raw_payload, section) for section in _PAYLOAD_SECTIONS}
    identities = {
        "source_units": "source_unit_id",
        "type_declarations": "type_id",
        "field_declarations": "field_id",
        "inheritance_declarations": "inheritance_id",
        "annotation_declarations": "annotation_id",
        "type_reference_observations": "type_reference_id",
        "enum_constant_declarations": "enum_constant_id",
    }
    for section, id_key in identities.items():
        _unique_ids(payload[section], id_key, section)
    source_occurrence_id = stable_id("code_declared_model_source", repo_id, content_fingerprint)
    return ResolvedJavaTypeStructureArtifact(
        runner_manifest_path=manifest_path,
        run_root=run_root,
        runner_manifest=manifest,
        repo_id=repo_id,
        runner_version=(str((manifest.get("runner") or {}).get("version")) if (manifest.get("runner") or {}).get("version") else None),
        registration=registration,
        artifact_path=artifact_path,
        artifact_sha256=actual_sha,
        artifact=artifact,
        payload=payload,
        source_occurrence_id=source_occurrence_id,
    )


def ingest_java_type_structure_artifact(connection: Any, artifact: ResolvedJavaTypeStructureArtifact, *, scope_id: str) -> dict[str, int]:
    core = artifact.artifact
    snapshot = core.get("source_snapshot") or {}
    coverage = dict(core.get("coverage") or {})
    diagnostics = [dict(item) for item in (core.get("diagnostics") or []) if isinstance(item, Mapping)]
    connection.execute(
        "INSERT INTO code_declared_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            artifact.source_occurrence_id,
            scope_id,
            artifact.repo_id,
            str(artifact.runner_manifest_path),
            artifact.runner_version,
            core.get("artifact_id"),
            core.get("artifact_kind"),
            core.get("schema_version"),
            core.get("content_fingerprint"),
            snapshot.get("source_id"),
            snapshot.get("fingerprint"),
            snapshot.get("revision"),
            coverage.get("coverage_status") or "unknown",
            canonical_json(coverage),
            canonical_json(diagnostics),
            canonical_json(core),
        ],
    )

    source_unit_map: dict[str, str] = {}
    type_map: dict[str, str] = {}
    field_map: dict[str, str] = {}
    counts: dict[str, int] = {}

    for row in artifact.payload["source_units"]:
        source_unit_id = str(row["source_unit_id"])
        occurrence_id = stable_id("code_declared_source_unit", artifact.repo_id, source_unit_id)
        source_unit_map[source_unit_id] = occurrence_id
        connection.execute(
            "INSERT INTO code_declared_source_unit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, artifact.source_occurrence_id, artifact.repo_id, source_unit_id,
             row.get("repository_relative_path"), row.get("source_set"), row.get("package_name"), row.get("language"),
             row.get("parse_status"), int(row.get("parse_error_count") or 0), canonical_json(row.get("imports") or []), canonical_json(row)],
        )
    counts["code_declared_source_unit"] = len(source_unit_map)

    for row in artifact.payload["type_declarations"]:
        type_id = str(row["type_id"])
        occurrence_id = stable_id("code_declared_type", artifact.repo_id, type_id)
        type_map[type_id] = occurrence_id
    for row in artifact.payload["type_declarations"]:
        type_id = str(row["type_id"])
        source_unit_id = str(row.get("source_unit_id") or "")
        if source_unit_id not in source_unit_map:
            raise ValueError(f"type {type_id} references unknown source_unit_id {source_unit_id!r}")
        enclosing_id = str(row.get("enclosing_type_id") or "")
        connection.execute(
            "INSERT INTO code_declared_type VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [type_map[type_id], artifact.source_occurrence_id, artifact.repo_id, type_id, source_unit_map[source_unit_id],
             row.get("fully_qualified_name"), row.get("simple_name"), row.get("package_name"), row.get("type_kind"),
             type_map.get(enclosing_id), row.get("source_set"), canonical_json(row.get("modifier_tokens") or []),
             canonical_json(row.get("type_parameters") or []), canonical_json(row.get("documentation")) if row.get("documentation") is not None else None,
             canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
    counts["code_declared_type"] = len(type_map)

    for row in artifact.payload["field_declarations"]:
        field_id = str(row["field_id"])
        occurrence_id = stable_id("code_declared_field", artifact.repo_id, field_id)
        field_map[field_id] = occurrence_id
    for row in artifact.payload["field_declarations"]:
        field_id = str(row["field_id"])
        owner_type_id = str(row.get("owner_type_id") or "")
        if owner_type_id not in type_map:
            raise ValueError(f"field {field_id} references unknown owner_type_id {owner_type_id!r}")
        connection.execute(
            "INSERT INTO code_declared_field VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [field_map[field_id], artifact.source_occurrence_id, artifact.repo_id, field_id, type_map[owner_type_id], row.get("name"),
             row.get("declared_type_expression"), row.get("normalized_type_expression"), bool(row.get("is_static")), bool(row.get("is_final")),
             row.get("initializer_present"), canonical_json(row.get("modifier_tokens") or []),
             canonical_json(row.get("documentation")) if row.get("documentation") is not None else None,
             canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
    counts["code_declared_field"] = len(field_map)

    inheritance_map: dict[str, str] = {}
    for row in artifact.payload["inheritance_declarations"]:
        inheritance_id = str(row["inheritance_id"])
        subtype_id = str(row.get("subtype_id") or "")
        if subtype_id not in type_map:
            raise ValueError(f"inheritance {inheritance_id} references unknown subtype_id {subtype_id!r}")
        occurrence_id = stable_id("code_declared_inheritance", artifact.repo_id, inheritance_id)
        inheritance_map[inheritance_id] = occurrence_id
        resolved_supertype_id = str(row.get("resolved_supertype_id") or "")
        connection.execute(
            "INSERT INTO code_declared_inheritance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, artifact.source_occurrence_id, artifact.repo_id, inheritance_id, type_map[subtype_id], type_map.get(resolved_supertype_id),
             row.get("relation_kind"), row.get("declared_supertype_expression"), row.get("resolution_status"), row.get("resolved_fqcn"),
             canonical_json(row.get("candidate_supertype_ids") or []), canonical_json(row.get("candidate_fqcns") or []),
             canonical_json(row.get("type_arguments") or []), canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
    counts["code_declared_inheritance"] = len(inheritance_map)

    ref_map: dict[str, str] = {}
    for row in artifact.payload["type_reference_observations"]:
        ref_id = str(row["type_reference_id"])
        owner_kind = str(row.get("owner_kind") or "")
        owner_id = str(row.get("owner_id") or "")
        owner_occurrence_id = field_map.get(owner_id) if owner_kind == "field" else type_map.get(owner_id)
        if owner_occurrence_id is None:
            raise ValueError(f"type reference {ref_id} has unknown {owner_kind} owner {owner_id!r}")
        occurrence_id = stable_id("code_declared_type_reference", artifact.repo_id, ref_id)
        ref_map[ref_id] = occurrence_id
        resolved_type_id = str(row.get("resolved_type_id") or "")
        connection.execute(
            "INSERT INTO code_declared_type_reference VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, artifact.source_occurrence_id, artifact.repo_id, ref_id, owner_kind, owner_occurrence_id,
             row.get("reference_role"), row.get("declared_type_expression"), row.get("referenced_type_token"), row.get("resolution_status"),
             type_map.get(resolved_type_id), row.get("resolved_fqcn"), canonical_json(row.get("candidate_type_ids") or []),
             canonical_json(row.get("candidate_fqcns") or []), canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
    counts["code_declared_type_reference"] = len(ref_map)

    annotation_count = 0
    for row in artifact.payload["annotation_declarations"]:
        annotation_id = str(row["annotation_id"])
        target_kind = str(row.get("target_kind") or "")
        target_id = str(row.get("target_id") or "")
        target_occurrence_id = type_map.get(target_id) if target_kind == "type" else field_map.get(target_id)
        if target_occurrence_id is None:
            raise ValueError(f"annotation {annotation_id} has unknown {target_kind} target {target_id!r}")
        occurrence_id = stable_id("code_declared_annotation", artifact.repo_id, annotation_id)
        connection.execute(
            "INSERT INTO code_declared_annotation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, artifact.source_occurrence_id, artifact.repo_id, annotation_id, target_kind, target_occurrence_id,
             row.get("annotation_name"), row.get("arguments_raw"), canonical_json(row.get("structured_arguments") or []),
             row.get("resolution_status"), row.get("resolved_annotation_type"), canonical_json(row.get("candidate_annotation_types") or []),
             canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
        annotation_count += 1
    counts["code_declared_annotation"] = annotation_count

    enum_count = 0
    for row in artifact.payload["enum_constant_declarations"]:
        constant_id = str(row["enum_constant_id"])
        owner_type_id = str(row.get("owner_type_id") or "")
        if owner_type_id not in type_map:
            raise ValueError(f"enum constant {constant_id} references unknown owner_type_id {owner_type_id!r}")
        occurrence_id = stable_id("code_declared_enum_constant", artifact.repo_id, constant_id)
        connection.execute(
            "INSERT INTO code_declared_enum_constant VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [occurrence_id, artifact.source_occurrence_id, artifact.repo_id, constant_id, type_map[owner_type_id], row.get("name"),
             canonical_json(row.get("arguments_raw") or []), canonical_json(row.get("source_ref") or {}), canonical_json(row)],
        )
        enum_count += 1
    counts["code_declared_enum_constant"] = enum_count

    gap_count = 0
    for index, diagnostic in enumerate(diagnostics):
        gap_id = stable_id("code_declared_gap", artifact.repo_id, diagnostic.get("code"), index, diagnostic)
        connection.execute(
            "INSERT INTO code_declared_model_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [gap_id, artifact.source_occurrence_id, artifact.repo_id, diagnostic.get("code") or "core_diagnostic",
             diagnostic.get("severity") or "warning", None, None, diagnostic.get("message") or "Core evidence diagnostic",
             canonical_json(diagnostic.get("source_refs") or []), canonical_json(diagnostic)],
        )
        gap_count += 1
    counts["code_declared_model_gap"] = gap_count
    return counts
