from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .observed_storage_usage_schema import (
    OBSERVED_STORAGE_DATABASE,
    OBSERVED_STORAGE_DDL,
    OBSERVED_STORAGE_SCHEMA_VERSION,
    OBSERVED_STORAGE_SOURCE_SCHEMA_VERSION,
    OBSERVED_STORAGE_TABLES,
)
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_envelope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("storage usage evidence must be a JSON object")
    if payload.get("contract_version") != "core_evidence_artifact_contract/v1":
        raise ValueError("unsupported storage usage evidence envelope")
    if (payload.get("artifact_kind"), payload.get("schema_version")) != (
        "storage-usage-evidence", "storage-usage-evidence/v1"
    ):
        raise ValueError("unexpected storage usage evidence semantic identity")
    material = {key: deepcopy(value) for key, value in payload.items() if key not in {"content_fingerprint", "artifact_id"}}
    if payload.get("content_fingerprint") != _fingerprint(material):
        raise ValueError("storage usage evidence fingerprint is invalid")
    if not str(payload.get("artifact_id") or ""):
        raise ValueError("storage usage evidence has no artifact_id")
    return payload


def _table_counts(connection: Any) -> dict[str, int]:
    return {table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]) for table in OBSERVED_STORAGE_TABLES}


def _insert_access(connection: Any, source_id: str, item: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT INTO observed_storage_access VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            item.get("storage_access_id"), source_id, item.get("repo_id"), item.get("operation"),
            item.get("operation_signature"), item.get("class_name"), item.get("method_name"),
            item.get("access_kind"), item.get("operation_kind"), item.get("write_kind"),
            item.get("mutation_kind"), item.get("storage_kind"), item.get("storage_target_expression"),
            item.get("target_resolution_level"), item.get("target_resolution_status"),
            item.get("receiver_expression"), item.get("receiver_declared_type"), item.get("storage_method"),
            item.get("payload_expression"), item.get("payload_role"), bool(item.get("writes_new_payload")),
            canonical_json(item.get("selected_fields") or []), canonical_json(item.get("selected_field_refs") or []),
            item.get("result_type"), item.get("sql_preview"), canonical_json(item.get("source_ref") or {}),
            canonical_json(dict(item)),
        ],
    )


def _insert_read(connection: Any, source_id: str, item: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT INTO observed_storage_read VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            item.get("storage_read_id"), item.get("storage_access_id"), source_id, item.get("repo_id"),
            item.get("operation"), item.get("storage_target_expression"), item.get("storage_kind"),
            item.get("storage_method"), canonical_json(item.get("selected_fields") or []), item.get("result_type"),
            item.get("target_resolution_status"), canonical_json(item.get("source_ref") or {}), canonical_json(dict(item)),
        ],
    )


def _insert_write(connection: Any, source_id: str, item: Mapping[str, Any]) -> None:
    connection.execute(
        "INSERT INTO observed_storage_write VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            item.get("storage_write_id"), item.get("storage_access_id"), source_id, item.get("repo_id"),
            item.get("operation"), item.get("storage_target_expression"), item.get("storage_kind"),
            item.get("storage_method"), item.get("write_kind"), item.get("mutation_kind"),
            item.get("payload_expression"), item.get("payload_role"), bool(item.get("writes_new_payload")),
            item.get("target_resolution_status"), canonical_json(item.get("source_ref") or {}), canonical_json(dict(item)),
        ],
    )


def _validate(connection: Any, *, sources: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    expected = {
        "observed_storage_access": sum(len(payload.get("storage_accesses") or []) for _, payload in sources),
        "observed_storage_read": sum(len(payload.get("storage_reads") or []) for _, payload in sources),
        "observed_storage_write": sum(len(payload.get("storage_writes") or []) for _, payload in sources),
        "observed_storage_usage_gap": sum(len(payload.get("storage_usage_gaps") or []) for _, payload in sources),
    }
    count_checks = {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]) == count
        for table, count in expected.items()
    }
    source_count = int(connection.execute("SELECT count(*) FROM observed_storage_source").fetchone()[0])
    source_ids = {row[0] for row in connection.execute("SELECT storage_usage_source_id FROM observed_storage_source").fetchall()}
    expected_source_ids = {source_id for source_id, _ in sources}
    orphan_reads = int(connection.execute("SELECT count(*) FROM observed_storage_read r LEFT JOIN observed_storage_access a ON a.storage_access_id=r.storage_access_id WHERE a.storage_access_id IS NULL").fetchone()[0])
    orphan_writes = int(connection.execute("SELECT count(*) FROM observed_storage_write w LEFT JOIN observed_storage_access a ON a.storage_access_id=w.storage_access_id WHERE a.storage_access_id IS NULL").fetchone()[0])
    checks = {
        "source_count_matches": source_count == len(sources),
        "source_ids_match": source_ids == expected_source_ids,
        "fact_counts_match": all(count_checks.values()),
        "fact_count_checks": count_checks,
        "orphan_reads": orphan_reads,
        "orphan_writes": orphan_writes,
    }
    if not checks["source_count_matches"] or not checks["source_ids_match"] or not all(count_checks.values()) or orphan_reads or orphan_writes:
        raise ValueError(f"observed storage usage validation failed: {checks}")
    return checks


def build_observed_storage_usage_knowledge_layer(
    evidence_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    knowledge_items: Sequence[Mapping[str, Any]] = (),
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    if not evidence_items:
        raise ValueError("observed-storage-usage requires at least one storage-usage-evidence/v1 artifact")

    resolved_sources: list[dict[str, Any]] = []
    for raw_item in evidence_items:
        item = dict(raw_item)
        raw_location = item.get("location") or {}
        path = Path(str(raw_location.get("path") or "")).expanduser().resolve()
        envelope = _read_envelope(path)
        payload = envelope.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise ValueError("storage usage evidence payload must be an object")
        repo_id = str((envelope.get("source_snapshot") or {}).get("source_id") or scope_id)
        source_id = stable_id("observed_storage_source", envelope.get("artifact_id"), envelope.get("content_fingerprint"))
        resolved_sources.append({"path": path, "envelope": envelope, "payload": payload, "repo_id": repo_id, "source_id": source_id})

    resolved_sources.sort(key=lambda row: (row["repo_id"], str(row["envelope"].get("artifact_id") or "")))
    repo_ids = tuple(row["repo_id"] for row in resolved_sources)
    if len(repo_ids) != len(set(repo_ids)):
        raise ValueError("observed-storage-usage requires at most one storage-usage-evidence/v1 artifact per repository")
    fingerprints = [str(row["envelope"].get("content_fingerprint") or "") for row in resolved_sources]
    aggregate_fingerprint = _fingerprint(fingerprints)

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path)
    staging_path.mkdir(parents=True)
    database_path = staging_path / OBSERVED_STORAGE_DATABASE
    manifest_path = staging_path / "knowledge-layer-manifest.json"
    build_id = stable_id("observed_storage_usage_build", scope_id, aggregate_fingerprint, __version__)
    started_at = utc_now()
    connection = None
    try:
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, OBSERVED_STORAGE_DDL)
        connection.execute("INSERT INTO observed_storage_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)", [
            build_id, scope_id, __version__, OBSERVED_STORAGE_SCHEMA_VERSION, OBSERVED_STORAGE_SOURCE_SCHEMA_VERSION,
            aggregate_fingerprint, "building", started_at, canonical_json({}), canonical_json({}),
        ])
        source_payloads: list[tuple[str, Mapping[str, Any]]] = []
        for row in resolved_sources:
            envelope = row["envelope"]; payload = row["payload"]; source_id = row["source_id"]; repo_id = row["repo_id"]; path = row["path"]
            connection.execute("INSERT INTO observed_storage_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                source_id, repo_id, envelope.get("artifact_id"), str(path),
                canonical_json(envelope.get("source_snapshot") or {}), envelope.get("content_fingerprint"),
                canonical_json(envelope.get("coverage") or {}), canonical_json(envelope.get("diagnostics") or []),
                canonical_json(envelope.get("provenance") or {}),
            ])
            for item in payload.get("storage_accesses") or []: _insert_access(connection, source_id, item)
            for item in payload.get("storage_reads") or []: _insert_read(connection, source_id, item)
            for item in payload.get("storage_writes") or []: _insert_write(connection, source_id, item)
            for item in payload.get("storage_usage_gaps") or []:
                connection.execute("INSERT INTO observed_storage_usage_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                    item.get("storage_usage_gap_id"), source_id, item.get("gap_code"), item.get("severity"),
                    item.get("owner_kind"), item.get("owner_id"), item.get("message"),
                    canonical_json(item.get("details") or {}), canonical_json(item.get("source_refs") or []), canonical_json(dict(item)),
                ])
            source_payloads.append((source_id, payload))

        checks = _validate(connection, sources=source_payloads)
        counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute("UPDATE observed_storage_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?", [completed_at, canonical_json(counts), canonical_json(checks), build_id])
        connection.execute("CHECKPOINT")
        connection.close(); connection = None
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id, repository_ids=repo_ids, modes=("observed-storage-usage",), producer_version=__version__,
            build_id=build_id, build_status="complete", counts=counts,
            materialized_marts=("observed-storage-reads", "observed-storage-writes", "observed-storage-access-gaps"),
            capabilities=("common.observed-storage-usage", "common.storage-read-write-inventory", "common.storage-access-gaps"),
            artifacts={"database": OBSERVED_STORAGE_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple({
                "repo_id": row["repo_id"], "artifact_id": row["envelope"].get("artifact_id"),
                "artifact_kind": row["envelope"].get("artifact_kind"), "schema_version": row["envelope"].get("schema_version"),
                "content_fingerprint": row["envelope"].get("content_fingerprint"), "artifact_path": str(row["path"]),
            } for row in resolved_sources),
            validation_status="complete", validation=checks,
            metadata={
                "observed_storage_schema_version": OBSERVED_STORAGE_SCHEMA_VERSION,
                "source_storage_usage_schema_version": OBSERVED_STORAGE_SOURCE_SCHEMA_VERSION,
                "coverage_by_repository": {row["repo_id"]: row["envelope"].get("coverage") or {} for row in resolved_sources},
                "diagnostic_count": sum(len(row["envelope"].get("diagnostics") or []) for row in resolved_sources),
                "optional_knowledge_artifact_ids": sorted(str(value.get("artifact_id")) for value in knowledge_items if value.get("artifact_id")),
                "started_at": started_at, "completed_at": completed_at,
            },
        )
        write_manifest(manifest_path, manifest)
        publish_directory_atomic(staging_path, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None: connection.close()
        remove_path(staging_path)
        raise

