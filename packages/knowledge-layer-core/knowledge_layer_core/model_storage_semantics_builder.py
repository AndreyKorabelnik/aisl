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
from .publication import publish_directory_atomic, remove_path
from .model_storage_semantics_schema import (
    MODEL_STORAGE_DATABASE,
    MODEL_STORAGE_DDL,
    MODEL_STORAGE_SCHEMA_VERSION,
    MODEL_STORAGE_SOURCE_SCHEMA_VERSION,
    MODEL_STORAGE_TABLES,
)
from .version import __version__


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_envelope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model storage evidence must be a JSON object")
    if payload.get("contract_version") != "core_evidence_artifact_contract/v1":
        raise ValueError("unsupported model storage evidence envelope")
    if (payload.get("artifact_kind"), payload.get("schema_version")) != (
        "model-storage-evidence", MODEL_STORAGE_SOURCE_SCHEMA_VERSION
    ):
        raise ValueError("unexpected model storage evidence semantic identity")
    material = {key: deepcopy(value) for key, value in payload.items() if key not in {"content_fingerprint", "artifact_id"}}
    if payload.get("content_fingerprint") != _fingerprint(material):
        raise ValueError("model storage evidence fingerprint is invalid")
    if not str(payload.get("artifact_id") or ""):
        raise ValueError("model storage evidence has no artifact_id")
    return payload


def _table_counts(connection: Any) -> dict[str, int]:
    return {table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]) for table in MODEL_STORAGE_TABLES}


def _props(item: Mapping[str, Any]) -> dict[str, Any]:
    value = item.get("properties") or {}
    return dict(value) if isinstance(value, Mapping) else {}


def _insert_record(connection: Any, source_id: str, repo_id: str, item: Mapping[str, Any]) -> None:
    p = _props(item)
    connection.execute("INSERT INTO model_storage_record VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        item.get("observation_id"), source_id, repo_id, item.get("api_framework"), p.get("owner_fqcn"),
        p.get("owner_operation"), p.get("storage_alias"), p.get("storage_key_field"), p.get("storage_key_expression"),
        canonical_json(item.get("source_refs") or []), canonical_json(dict(item)),
    ])


def _insert_reference(connection: Any, source_id: str, repo_id: str, item: Mapping[str, Any]) -> None:
    p = _props(item)
    connection.execute("INSERT INTO model_storage_reference VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        item.get("observation_id"), source_id, repo_id, item.get("api_framework"), p.get("source_owner_fqcn"),
        p.get("source_operation"), p.get("source_alias"), p.get("source_field"), p.get("reference_operation"),
        p.get("target_converter_operation"), p.get("target_alias"), p.get("target_storage_key_field"),
        p.get("target_storage_key_expression"), canonical_json(item.get("source_refs") or []), canonical_json(dict(item)),
    ])


def _insert_lineage(connection: Any, source_id: str, repo_id: str, item: Mapping[str, Any]) -> None:
    p = _props(item)
    connection.execute("INSERT INTO model_storage_key_lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        item.get("observation_id"), source_id, repo_id, item.get("api_framework"), p.get("source_owner_fqcn"),
        p.get("source_operation"), p.get("source_alias"), p.get("relationship_field"), p.get("reference_operation"),
        p.get("target_alias"), p.get("source_key_expression"), p.get("target_key_expression_template"),
        p.get("composed_target_key_expression"), bool(p.get("source_key_passed_into_target_key")),
        canonical_json(item.get("source_refs") or []), canonical_json(dict(item)),
    ])


def _insert_derivation(connection: Any, source_id: str, repo_id: str, item: Mapping[str, Any]) -> None:
    p = _props(item)
    connection.execute("INSERT INTO model_storage_reference_derivation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        item.get("observation_id"), source_id, repo_id, item.get("api_framework"), p.get("source_owner_fqcn"),
        p.get("source_operation"), p.get("source_alias"), p.get("relationship_field"), p.get("reference_operation"),
        p.get("value_converter_operation"), p.get("composed_reference_value_expression"),
        canonical_json(item.get("source_refs") or []), canonical_json(dict(item)),
    ])


def build_model_storage_semantics_knowledge_layer(
    evidence_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    resolved = []
    seen_repos: set[str] = set()
    for item in evidence_items:
        path = Path(str(((item.get("location") or {}).get("path") or ""))).expanduser().resolve()
        envelope = _read_envelope(path)
        repo_id = str((envelope.get("source_snapshot") or {}).get("source_id") or "").strip()
        if not repo_id:
            raise ValueError("model storage evidence has no source repo_id")
        if repo_id in seen_repos:
            raise ValueError("model-storage-semantics requires at most one model-storage-evidence/v1 artifact per repository")
        seen_repos.add(repo_id)
        resolved.append({"path": path, "envelope": envelope, "repo_id": repo_id})
    if not resolved:
        raise ValueError("model-storage-semantics requires at least one model-storage-evidence/v1 artifact")
    resolved.sort(key=lambda row: row["repo_id"])

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path); staging_path.mkdir(parents=True)
    database_path = staging_path / MODEL_STORAGE_DATABASE
    manifest_path = staging_path / "knowledge-layer-manifest.json"
    started_at = utc_now()
    aggregate_fp = _fingerprint([(row["repo_id"], row["envelope"].get("content_fingerprint")) for row in resolved])
    build_id = stable_id("model_storage_semantics_build", scope_id, aggregate_fp, __version__)
    connection = None
    try:
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, MODEL_STORAGE_DDL)
        connection.execute("INSERT INTO model_storage_build VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)", [
            build_id, scope_id, __version__, MODEL_STORAGE_SCHEMA_VERSION, MODEL_STORAGE_SOURCE_SCHEMA_VERSION,
            "building", started_at, canonical_json({}), canonical_json({}),
        ])
        expected = {"model_storage_record":0,"model_storage_reference":0,"model_storage_key_lineage":0,"model_storage_reference_derivation":0}
        for row in resolved:
            env=row["envelope"]; payload=env.get("payload") or {}; source_id=stable_id("model_storage_source", row["repo_id"], env.get("artifact_id"))
            connection.execute("INSERT INTO model_storage_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                source_id, row["repo_id"], env.get("artifact_id"), str(row["path"]), canonical_json(env.get("source_snapshot") or {}),
                env.get("content_fingerprint"), canonical_json(env.get("coverage") or {}), canonical_json(env.get("diagnostics") or []), canonical_json(env.get("provenance") or {}),
            ])
            for item in payload.get("storage_records") or []: _insert_record(connection, source_id, row["repo_id"], item); expected["model_storage_record"]+=1
            for item in payload.get("storage_references") or []: _insert_reference(connection, source_id, row["repo_id"], item); expected["model_storage_reference"]+=1
            for item in payload.get("storage_key_lineage") or []: _insert_lineage(connection, source_id, row["repo_id"], item); expected["model_storage_key_lineage"]+=1
            for item in payload.get("reference_value_derivations") or []: _insert_derivation(connection, source_id, row["repo_id"], item); expected["model_storage_reference_derivation"]+=1
        counts = _table_counts(connection)
        checks = {
            "source_count_matches": counts["model_storage_source"] == len(resolved),
            "record_count_matches": counts["model_storage_record"] == expected["model_storage_record"],
            "reference_count_matches": counts["model_storage_reference"] == expected["model_storage_reference"],
            "key_lineage_count_matches": counts["model_storage_key_lineage"] == expected["model_storage_key_lineage"],
            "reference_derivation_count_matches": counts["model_storage_reference_derivation"] == expected["model_storage_reference_derivation"],
            "physical_mapping_inference_used": False,
        }
        if not all(value is True or value is False and key == "physical_mapping_inference_used" for key, value in checks.items()):
            raise ValueError(f"model storage semantics validation failed: {checks}")
        completed_at=utc_now()
        connection.execute("UPDATE model_storage_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?", [completed_at,canonical_json(counts),canonical_json(checks),build_id])
        connection.execute("CHECKPOINT"); connection.close(); connection=None
        repo_ids=tuple(row["repo_id"] for row in resolved)
        manifest=KnowledgeLayerManifest(
            scope_id=scope_id, repository_ids=repo_ids, modes=("model-storage-semantics",), producer_version=__version__,
            build_id=build_id, build_status="complete", counts=counts,
            materialized_marts=("model-storage-records","model-storage-references","model-storage-key-lineage"),
            capabilities=("common.model-storage-semantics","common.storage-identities","common.storage-reference-lineage"),
            artifacts={"database":MODEL_STORAGE_DATABASE,"manifest":"knowledge-layer-manifest.json"},
            source_evidence=tuple({"repo_id":row["repo_id"],"artifact_id":row["envelope"].get("artifact_id"),"artifact_kind":"model-storage-evidence","schema_version":MODEL_STORAGE_SOURCE_SCHEMA_VERSION,"content_fingerprint":row["envelope"].get("content_fingerprint"),"artifact_path":str(row["path"])} for row in resolved),
            validation_status="complete", validation=checks,
            metadata={"model_storage_schema_version":MODEL_STORAGE_SCHEMA_VERSION,"source_model_storage_schema_version":MODEL_STORAGE_SOURCE_SCHEMA_VERSION,"coverage_by_repository":{row["repo_id"]:row["envelope"].get("coverage") or {} for row in resolved},"started_at":started_at,"completed_at":completed_at},
        )
        write_manifest(manifest_path, manifest)
        publish_directory_atomic(staging_path, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None: connection.close()
        remove_path(staging_path)
        raise
