from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from .interaction_graph import materialize_system_interactions
from .interaction_evidence_catalog import interaction_boundary_records, read_json_object
from .interaction_knowledge_schema import (
    INTERACTION_KNOWLEDGE_DATABASE,
    INTERACTION_KNOWLEDGE_DDL,
    INTERACTION_KNOWLEDGE_SCHEMA_VERSION,
)
from prepared_knowledge_runtime.io import write_json
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _evidence_source(item: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    location = item.get("location") or {}
    envelope_path = Path(str(location.get("path") or "")).expanduser().resolve()
    envelope = read_json_object(envelope_path)
    identity = (str(envelope.get("artifact_kind") or ""), str(envelope.get("schema_version") or ""))
    if identity != ("interaction-boundary-evidence", "interaction-boundary-evidence/v1"):
        raise ValueError(f"unexpected interaction evidence identity: {identity}")
    return envelope_path, envelope


def build_system_interactions_knowledge_layer(
    evidence_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    if not evidence_items:
        raise ValueError("system-interactions requires at least one interaction-boundary-evidence artifact")
    sources = [_evidence_source(item) for item in evidence_items]
    repo_ids = [str((envelope.get("source_snapshot") or {}).get("source_id") or "").strip() for _, envelope in sources]
    if any(not value for value in repo_ids) or len(set(repo_ids)) != len(repo_ids):
        raise ValueError("interaction boundary evidence must contain unique non-empty repository IDs")
    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / INTERACTION_KNOWLEDGE_DATABASE
    input_fingerprint = hashlib.sha256(canonical_json([
        {
            "artifact_id": envelope.get("artifact_id"),
            "content_fingerprint": envelope.get("content_fingerprint"),
            "repo_id": repo_id,
        }
        for repo_id, (_, envelope) in sorted(zip(repo_ids, sources), key=lambda item: item[0])
    ]).encode("utf-8")).hexdigest()
    build_id = stable_id("interaction_knowledge_build", scope_id, input_fingerprint, __version__)
    started_at = utc_now()
    connection = None
    try:
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, INTERACTION_KNOWLEDGE_DDL)
        connection.execute(
            "INSERT INTO interaction_knowledge_build VALUES (?, ?, ?, ?, ?, 'building', ?, NULL, ?, ?)",
            [build_id, scope_id, __version__, INTERACTION_KNOWLEDGE_SCHEMA_VERSION, "interaction-boundary-evidence/v1", started_at, canonical_json({}), canonical_json({})],
        )
        record_count = 0
        for repo_id, (envelope_path, envelope) in sorted(zip(repo_ids, sources), key=lambda item: item[0]):
            payload = envelope.get("payload") or {}
            identity = payload.get("repository_identity") or {}
            aliases = sorted({str(value).strip() for value in (identity.get("service_aliases") or []) if str(value).strip()})
            connection.execute(
                "INSERT INTO interaction_repository_identity VALUES (?, ?, ?, ?, ?, ?, ?)",
                [scope_id, repo_id, identity.get("system_id"), identity.get("project_id"), canonical_json(aliases), envelope.get("artifact_id"), canonical_json(identity)],
            )
            for ordinal, record in enumerate(interaction_boundary_records(envelope_path, envelope), start=1):
                local_id = str(record.get("interface_id") or "").strip() or None
                record_id = stable_id("interaction_boundary_evidence_record", scope_id, repo_id, local_id or "", ordinal, hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest())
                connection.execute(
                    "INSERT INTO interaction_boundary_evidence_record VALUES (?, ?, ?, ?, ?, ?)",
                    [record_id, scope_id, repo_id, local_id, ordinal, canonical_json(record)],
                )
                record_count += 1
        interaction_counts = materialize_system_interactions(connection, scope_id=scope_id)
        counts = {
            "interaction_repository_identity": len(repo_ids),
            "interaction_boundary_evidence_record": record_count,
            **interaction_counts,
        }
        checks = {
            "typed_evidence_only": True,
            "http_only": True,
        }
        completed_at = utc_now()
        connection.execute(
            "UPDATE interaction_knowledge_build SET build_status='complete', completed_at=?, counts_json=?, checks_json=? WHERE build_id=?",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("CHECKPOINT")
        connection.close(); connection = None
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=tuple(sorted(repo_ids)),
            modes=("system-interactions",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("workspace-repository-interaction-boundaries", "workspace-system-interactions"),
            capabilities=("workspace.system-interactions", "workspace.repository-interaction-boundaries"),
            artifacts={"database": INTERACTION_KNOWLEDGE_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple({
                "artifact_id": envelope.get("artifact_id"),
                "artifact_kind": envelope.get("artifact_kind"),
                "schema_version": envelope.get("schema_version"),
                "content_fingerprint": envelope.get("content_fingerprint"),
                "artifact_path": str(path),
            } for path, envelope in sources),
            validation_status="complete",
            validation=checks,
            metadata={
                "interaction_schema_version": INTERACTION_KNOWLEDGE_SCHEMA_VERSION,
                "produced_model": "workspace_system_interaction/v6",
                "coverage": {"coverage_status": "complete"},
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
