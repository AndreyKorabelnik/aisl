from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .metrics import canonical_json
from .logical_physical_mapping_schema import LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION

_EVIDENCE_ARTIFACT_KIND = "java-persistence-mapping-evidence"
_EVIDENCE_CONTRACT = "core_evidence_artifact_contract/v1"
_EVIDENCE_SECTIONS = (
    "persistence_type_mappings",
    "persistence_field_mappings",
    "persistence_key_mappings",
    "persistence_relationship_mappings",
    "persistence_inheritance_mappings",
    "mapping_gaps",
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(value: Mapping[str, Any], *, excluded: set[str] | None = None) -> str:
    ignored = excluded or set()
    material = {str(key): item for key, item in value.items() if str(key) not in ignored}
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _safe_child(root: Path, raw: object, *, field: str) -> Path:
    text = str(raw or "").strip()
    if not text or Path(text).is_absolute():
        raise ValueError(f"{field} must be relative to its manifest")
    path = (root / text).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{field} escapes its manifest root: {text}") from exc
    return path


def _artifact_path(item: Mapping[str, Any]) -> tuple[Path, Path | None, dict[str, Any] | None]:
    location = item.get("location") or {}
    if isinstance(location, Mapping) and str(location.get("kind") or "") == "file" and location.get("path"):
        path = Path(str(location["path"])).expanduser().resolve()
        return path, None, None

    raw_manifest = item.get("registration_manifest_path")
    if raw_manifest is None:
        raise ValueError("evidence input has neither absolute file location nor registration_manifest_path")
    manifest_path = Path(str(raw_manifest)).expanduser().resolve()
    manifest = _read_object(manifest_path)
    if manifest.get("schema_version") != "static_repository_analysis_run_manifest/v1":
        raise ValueError(f"unsupported Runner registration manifest schema: {manifest.get('schema_version')!r}")
    matches = [
        dict(entry)
        for entry in (manifest.get("evidence_artifacts") or [])
        if isinstance(entry, Mapping)
        and str(entry.get("artifact_kind") or "") == str(item.get("artifact_kind") or "")
        and str(entry.get("schema_version") or "") == str(item.get("schema_version") or "")
    ]
    if len(matches) != 1:
        raise ValueError("Runner registration manifest must contain exactly one matching persistence evidence artifact")
    registration = matches[0]
    location = registration.get("location") or {}
    if not isinstance(location, Mapping) or str(location.get("kind") or "") != "file":
        raise ValueError("Runner evidence registration location.kind must be 'file'")
    path = _safe_child(manifest_path.parent.resolve(), location.get("path"), field="evidence location.path")
    expected_sha = str(location.get("sha256") or "")
    if expected_sha and _sha256_file(path) != expected_sha:
        raise ValueError("persistence evidence file SHA-256 does not match Runner registration")
    return path, manifest_path, registration


def _require_rows(payload: Mapping[str, Any], section: str, id_field: str) -> list[dict[str, Any]]:
    raw = payload.get(section)
    if not isinstance(raw, list):
        raise ValueError(f"persistence mapping evidence payload section {section!r} must be a list")
    rows = [dict(item) for item in raw if isinstance(item, Mapping)]
    if len(rows) != len(raw):
        raise ValueError(f"persistence mapping evidence payload section {section!r} contains a non-object")
    ids = [str(item.get(id_field) or "").strip() for item in rows]
    if any(not value for value in ids):
        raise ValueError(f"persistence mapping evidence section {section!r} contains a record without {id_field}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"persistence mapping evidence section {section!r} contains duplicate {id_field}")
    return rows


@dataclass(frozen=True, slots=True)
class ResolvedPersistenceMappingEvidence:
    input_item: dict[str, Any]
    artifact_path: Path
    registration_manifest_path: Path | None
    registration: dict[str, Any] | None
    artifact: dict[str, Any]
    payload: dict[str, list[dict[str, Any]]]
    source_id: str
    content_fingerprint: str


def resolve_persistence_mapping_evidence(item: Mapping[str, Any]) -> ResolvedPersistenceMappingEvidence:
    if str(item.get("artifact_kind") or "") != _EVIDENCE_ARTIFACT_KIND:
        raise ValueError("unexpected evidence artifact_kind for logical-physical mapping")
    if str(item.get("schema_version") or "") != LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unexpected evidence schema_version for logical-physical mapping")
    artifact_path, manifest_path, registration = _artifact_path(item)
    if not artifact_path.is_file():
        raise FileNotFoundError(artifact_path)
    artifact = _read_object(artifact_path)
    if artifact.get("contract_version") != _EVIDENCE_CONTRACT:
        raise ValueError("unsupported Core evidence artifact contract")
    if artifact.get("artifact_kind") != _EVIDENCE_ARTIFACT_KIND:
        raise ValueError("unexpected persistence evidence artifact_kind")
    if artifact.get("schema_version") != LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unexpected persistence evidence schema_version")
    producer = artifact.get("producer") or {}
    if str(producer.get("analyzer_id") or "") != "java-persistence-mapping-analyzer":
        raise ValueError("unexpected Core analyzer_id for persistence mapping evidence")
    expected_fingerprint = _fingerprint(artifact, excluded={"content_fingerprint", "artifact_id"})
    content_fingerprint = str(artifact.get("content_fingerprint") or "")
    if content_fingerprint != expected_fingerprint:
        raise ValueError("Core persistence evidence content_fingerprint is invalid")
    if str(item.get("content_fingerprint") or "") != content_fingerprint:
        raise ValueError("materialization request fingerprint does not match persistence evidence")
    if str(item.get("artifact_id") or "") != str(artifact.get("artifact_id") or ""):
        raise ValueError("materialization request artifact_id does not match persistence evidence")
    if registration is not None:
        for field in ("artifact_id", "content_fingerprint"):
            if str(registration.get(field) or "") != str(item.get(field) or ""):
                raise ValueError(f"Runner registration {field} does not match persistence evidence request")
    source_snapshot = artifact.get("source_snapshot") or {}
    source_id = str(source_snapshot.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("persistence evidence has no source_snapshot.source_id")
    raw_payload = artifact.get("payload")
    if not isinstance(raw_payload, Mapping):
        raise ValueError("persistence mapping evidence payload must be an object")
    id_fields = {
        "persistence_type_mappings": "persistence_type_mapping_id",
        "persistence_field_mappings": "persistence_field_mapping_id",
        "persistence_key_mappings": "persistence_key_mapping_id",
        "persistence_relationship_mappings": "persistence_relationship_mapping_id",
        "persistence_inheritance_mappings": "persistence_inheritance_mapping_id",
        "mapping_gaps": "mapping_gap_id",
    }
    payload = {
        section: _require_rows(raw_payload, section, id_fields[section])
        for section in _EVIDENCE_SECTIONS
    }
    return ResolvedPersistenceMappingEvidence(
        input_item=dict(item),
        artifact_path=artifact_path,
        registration_manifest_path=manifest_path,
        registration=registration,
        artifact=artifact,
        payload=payload,
        source_id=source_id,
        content_fingerprint=content_fingerprint,
    )


@dataclass(frozen=True, slots=True)
class ResolvedKnowledgeLayerInput:
    input_item: dict[str, Any]
    output_path: Path
    manifest_path: Path
    database_path: Path
    manifest: dict[str, Any]


def resolve_knowledge_layer_input(
    item: Mapping[str, Any],
    *,
    model_kind: str,
    schema_version: str,
    source_materialization_id: str,
) -> ResolvedKnowledgeLayerInput:
    identity = (
        str(item.get("model_kind") or ""),
        str(item.get("schema_version") or ""),
        str(item.get("source_materialization_id") or ""),
    )
    expected = (model_kind, schema_version, source_materialization_id)
    if identity != expected:
        raise ValueError(f"unexpected knowledge input identity: {identity}; expected={expected}")
    location = item.get("location") or {}
    if not isinstance(location, Mapping) or str(location.get("kind") or "") != "knowledge-layer":
        raise ValueError("knowledge input location.kind must be 'knowledge-layer'")
    output_path = Path(str(location.get("output_path") or "")).expanduser().resolve()
    manifest_path = Path(str(location.get("manifest_path") or output_path / "knowledge-layer-manifest.json")).expanduser().resolve()
    manifest = _read_object(manifest_path)
    if manifest.get("schema_version") != "knowledge_layer/v1":
        raise ValueError(f"unsupported knowledge-layer manifest schema: {manifest.get('schema_version')!r}")
    actual_fingerprint = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    if str(item.get("content_fingerprint") or "") != actual_fingerprint:
        raise ValueError("knowledge input content_fingerprint does not match manifest")
    database_rel = str(manifest.get("database_path") or "knowledge-layer.duckdb")
    if Path(database_rel).is_absolute():
        raise ValueError("knowledge-layer manifest database_path must be output-relative")
    database_path = (output_path / database_rel).resolve()
    try:
        database_path.relative_to(output_path)
    except ValueError as exc:
        raise ValueError("knowledge-layer database_path escapes output root") from exc
    if not database_path.is_file():
        raise FileNotFoundError(database_path)
    return ResolvedKnowledgeLayerInput(
        input_item=dict(item),
        output_path=output_path,
        manifest_path=manifest_path,
        database_path=database_path,
        manifest=manifest,
    )
