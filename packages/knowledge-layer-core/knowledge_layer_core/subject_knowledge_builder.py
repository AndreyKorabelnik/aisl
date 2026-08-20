from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_json
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .subject_knowledge_schema import (
    SUBJECT_KNOWLEDGE_DATABASE,
    SUBJECT_KNOWLEDGE_DDL,
    SUBJECT_KNOWLEDGE_SCHEMA_VERSION,
)
from .version import __version__


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _search_text(payload: Any, *, max_chars: int = 12000) -> str:
    values: list[str] = []
    size = 0

    def visit(value: Any) -> None:
        nonlocal size
        if size >= max_chars:
            return
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, (str, int, float)):
            text = str(value)
            values.append(text)
            size += len(text)
            return
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                values.append(key_text)
                size += len(key_text)
                visit(child)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(payload)
    return " ".join(values)[:max_chars]


def _local_record_id(payload: Mapping[str, Any]) -> str | None:
    preferred = (
        "fact_id", "observation_id", "interface_id", "scenario_id",
        "scenario_storage_summary_id", "declared_value_set_id", "declared_value_id",
        "literal_data_write_id", "storage_access_id", "gap_id", "record_id", "id",
    )
    for key in preferred:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value)
    for key, value in payload.items():
        if str(key).endswith("_id") and value is not None and str(value).strip():
            return str(value)
    return None


def _persistence_lineage_local_record_id(artifact_name: str, payload: Mapping[str, Any]) -> str:
    identity_fields = {
        "source_to_storage_lineage.json": "source_to_storage_lineage_id",
        "storage_to_access_lineage.json": "storage_to_access_lineage_id",
        "persistent_writes.json": "persistent_write_id",
        "storage_accesses.json": "storage_access_id",
        "storage_lineage_gaps.json": "storage_lineage_gap_id",
        "stored_field_to_response_field_mappings.json": "stored_field_to_response_field_mapping_id",
    }
    identity_field = identity_fields.get(artifact_name)
    if identity_field is None:
        raise ValueError(f"unsupported persistence-lineage payload artifact: {artifact_name}")
    value = payload.get(identity_field)
    if value is None or not str(value).strip():
        raise ValueError(
            f"persistence-lineage record in {artifact_name} has no required {identity_field}"
        )
    return str(value)


def _safe_payload_path(envelope_path: Path, relative: str) -> Path:
    candidate = Path(str(relative or ""))
    if not relative or candidate.is_absolute():
        raise ValueError("typed evidence payload path must be envelope-relative")
    root = envelope_path.parent.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("typed evidence payload path escapes envelope root") from exc
    return resolved


def _iter_json(path: Path, sections: Sequence[str]) -> Iterable[tuple[str, dict[str, Any]]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield path.stem, item
        return
    if not isinstance(value, dict):
        return
    if sections:
        for section in sections:
            records = value.get(section)
            if isinstance(records, list):
                for item in records:
                    if isinstance(item, dict):
                        yield section, item
        return
    list_sections = [(str(key), child) for key, child in value.items() if isinstance(child, list)]
    if len(list_sections) == 1:
        section, records = list_sections[0]
        for item in records:
            if isinstance(item, dict):
                yield section, item


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            value = json.loads(text)
            if isinstance(value, dict):
                yield value


def _source_item(evidence_items: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    if len(evidence_items) != 1:
        raise ValueError("subject knowledge materialization requires exactly one typed evidence artifact")
    item = dict(evidence_items[0])
    location = item.get("location") or {}
    envelope_path = Path(str(location.get("path") or "")).expanduser().resolve()
    envelope = _read_json_object(envelope_path)
    return item, envelope_path, envelope


def build_subject_knowledge_layer(
    evidence_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    materialization_id: str,
    expected_artifact_kind: str,
    expected_schema_version: str,
    produced_model: str,
    capabilities: Sequence[str],
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    item, envelope_path, envelope = _source_item(evidence_items)
    identity = (str(envelope.get("artifact_kind") or ""), str(envelope.get("schema_version") or ""))
    if identity != (expected_artifact_kind, expected_schema_version):
        raise ValueError(f"unexpected typed evidence identity: {identity}")
    payload = envelope.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise ValueError("typed evidence payload must be an object")
    repo_id = str((envelope.get("source_snapshot") or {}).get("source_id") or scope_id)
    source_id = stable_id("subject_knowledge_source", materialization_id, envelope.get("artifact_id"), envelope.get("content_fingerprint"))
    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / SUBJECT_KNOWLEDGE_DATABASE
    build_id = stable_id("subject_knowledge_build", materialization_id, scope_id, envelope.get("content_fingerprint"), __version__)
    started_at = utc_now()
    connection = None
    rows: list[tuple[Any, ...]] = []
    artifact_count = 0
    if materialization_id == "system-description":
        for descriptor in payload.get("artifacts") or []:
            if not isinstance(descriptor, Mapping):
                continue
            artifact_name = str(descriptor.get("artifact_name") or "").strip()
            path = _safe_payload_path(envelope_path, str(descriptor.get("relative_path") or ""))
            if not path.is_file():
                raise ValueError(f"system-description payload file is missing: {path}")
            artifact_count += 1
            sections = [str(value) for value in (descriptor.get("sections") or [])]
            for record_kind, record in _iter_json(path, sections):
                ordinal = len(rows) + 1
                local_id = _local_record_id(record)
                record_id = stable_id(
                    "subject_record", materialization_id, repo_id, artifact_name,
                    record_kind, local_id or "", ordinal, hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest(),
                )
                rows.append((
                    record_id, source_id, scope_id, repo_id, materialization_id,
                    artifact_name, record_kind, local_id, ordinal, _search_text(record), canonical_json(record),
                ))
    elif materialization_id == "reference-data":
        for descriptor in payload.get("sections") or []:
            if not isinstance(descriptor, Mapping):
                continue
            section = str(descriptor.get("section") or "").strip()
            path = _safe_payload_path(envelope_path, str(descriptor.get("relative_path") or ""))
            if not path.is_file():
                raise ValueError(f"reference-data payload file is missing: {path}")
            artifact_count += 1
            artifact_name = f"reference_data_fact_base/{path.name}"
            for record in _iter_jsonl(path):
                ordinal = len(rows) + 1
                local_id = _local_record_id(record)
                record_id = stable_id(
                    "subject_record", materialization_id, repo_id, artifact_name,
                    section, local_id or "", ordinal, hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest(),
                )
                rows.append((
                    record_id, source_id, scope_id, repo_id, materialization_id,
                    artifact_name, section, local_id, ordinal, _search_text(record), canonical_json(record),
                ))
    elif materialization_id == "persistence-lineage":
        for descriptor in payload.get("artifacts") or []:
            if not isinstance(descriptor, Mapping):
                continue
            artifact_name = str(descriptor.get("artifact_name") or "").strip()
            path = _safe_payload_path(envelope_path, str(descriptor.get("relative_path") or ""))
            if not path.is_file():
                raise ValueError(f"persistence-lineage payload file is missing: {path}")
            artifact_count += 1
            for record_kind, record in _iter_json(path, ()):
                ordinal = len(rows) + 1
                local_id = _persistence_lineage_local_record_id(artifact_name, record)
                record_id = stable_id(
                    "subject_record", materialization_id, repo_id, artifact_name,
                    record_kind, local_id, ordinal,
                    hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest(),
                )
                rows.append((
                    record_id, source_id, scope_id, repo_id, materialization_id,
                    artifact_name, record_kind, local_id, ordinal,
                    _search_text(record), canonical_json(record),
                ))
    else:
        raise ValueError(f"unsupported subject knowledge materialization: {materialization_id}")
    try:
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, SUBJECT_KNOWLEDGE_DDL)
        connection.execute(
            "INSERT INTO subject_knowledge_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [
                build_id, scope_id, materialization_id, __version__, SUBJECT_KNOWLEDGE_SCHEMA_VERSION,
                expected_schema_version, envelope.get("content_fingerprint"), "building", started_at,
                canonical_json({}), canonical_json({}),
            ],
        )
        connection.execute(
            "INSERT INTO subject_knowledge_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                source_id, scope_id, repo_id, materialization_id, envelope.get("artifact_id"),
                envelope.get("artifact_kind"), envelope.get("schema_version"), str(envelope_path),
                envelope.get("content_fingerprint"), canonical_json(envelope.get("source_snapshot") or {}),
                canonical_json(envelope.get("coverage") or {}), canonical_json(envelope.get("diagnostics") or []),
                canonical_json(envelope.get("provenance") or {}),
            ],
        )
        if rows:
            connection.executemany(
                "INSERT INTO subject_knowledge_record VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        counts = {
            "subject_knowledge_source": 1,
            "subject_knowledge_record": len(rows),
            "payload_artifact": artifact_count,
        }
        checks = {
            "source_registered": True,
            "record_count_matches": int(connection.execute("SELECT count(*) FROM subject_knowledge_record").fetchone()[0]) == len(rows),
        }
        completed_at = utc_now()
        connection.execute(
            "UPDATE subject_knowledge_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("CHECKPOINT")
        connection.close(); connection = None
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=(repo_id,),
            modes=(materialization_id,),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=(materialization_id,),
            capabilities=tuple(capabilities),
            artifacts={"database": SUBJECT_KNOWLEDGE_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=({
                "artifact_id": envelope.get("artifact_id"),
                "artifact_kind": envelope.get("artifact_kind"),
                "schema_version": envelope.get("schema_version"),
                "content_fingerprint": envelope.get("content_fingerprint"),
                "artifact_path": str(envelope_path),
            },),
            validation_status="complete",
            validation=checks,
            metadata={
                "subject_knowledge_schema_version": SUBJECT_KNOWLEDGE_SCHEMA_VERSION,
                "produced_model": produced_model,
                "coverage": envelope.get("coverage") or {},
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )
        write_json(staging / "knowledge-layer-manifest.json", manifest.to_dict())
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging)
        raise
