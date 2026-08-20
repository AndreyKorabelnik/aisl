from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from .interaction_contracts import materialize_system_interaction_field_contracts
from .interaction_field_contract_knowledge_schema import (
    INTERACTION_FIELD_CONTRACT_DATABASE,
    INTERACTION_FIELD_CONTRACT_DDL,
    INTERACTION_FIELD_CONTRACT_SCHEMA_VERSION,
)
from prepared_knowledge_runtime.io import write_json
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _resolve_knowledge_source(
    item: Mapping[str, Any],
    *,
    model_kind: str,
    schema_version: str,
    source_materialization_id: str,
) -> tuple[Path, Path, dict[str, Any]]:
    identity = (
        str(item.get("model_kind") or ""),
        str(item.get("schema_version") or ""),
        str(item.get("source_materialization_id") or ""),
    )
    expected = (model_kind, schema_version, source_materialization_id)
    if identity != expected:
        raise ValueError(f"unexpected knowledge input identity: {identity}; expected {expected}")
    location = item.get("location") or {}
    if not isinstance(location, Mapping):
        raise ValueError("knowledge artifact location must be an object")
    manifest_path = Path(str(location.get("manifest_path") or "")).expanduser().resolve()
    if not manifest_path.is_file():
        raise ValueError(f"knowledge manifest is unavailable: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "knowledge_layer/v1":
        raise ValueError(f"unsupported knowledge manifest schema: {manifest.get('schema_version')!r}")
    database_name = str((manifest.get("artifacts") or {}).get("database") or "knowledge-layer.duckdb")
    if Path(database_name).is_absolute():
        raise ValueError("knowledge database path must be manifest-relative")
    database_path = (manifest_path.parent / database_name).resolve()
    try:
        database_path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("knowledge database path escapes artifact root") from exc
    if not database_path.is_file():
        raise ValueError(f"knowledge database is unavailable: {database_path}")
    return manifest_path, database_path, manifest


def build_system_interaction_field_contract_knowledge_layer(
    knowledge_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    selected: dict[str, tuple[Mapping[str, Any], Path, Path, dict[str, Any]]] = {}
    specs = {
        "value_flow": ("repository-value-flow", "repository_value_flow/v6", "repository-value-flow"),
        "interactions": ("system-interactions", "workspace_system_interaction/v6", "system-interactions"),
    }
    for role, (model_kind, schema_version, source_materialization_id) in specs.items():
        matches = [
            item for item in knowledge_items
            if (
                str(item.get("model_kind") or ""),
                str(item.get("schema_version") or ""),
                str(item.get("source_materialization_id") or ""),
            ) == (model_kind, schema_version, source_materialization_id)
        ]
        if len(matches) != 1:
            raise ValueError(f"interaction-field-contracts requires exactly one {role} knowledge artifact")
        manifest_path, database_path, manifest = _resolve_knowledge_source(
            matches[0],
            model_kind=model_kind,
            schema_version=schema_version,
            source_materialization_id=source_materialization_id,
        )
        selected[role] = (matches[0], manifest_path, database_path, manifest)

    repository_ids = sorted({
        str(repo_id)
        for _item, _manifest_path, _database_path, manifest in selected.values()
        for repo_id in (manifest.get("repository_ids") or [])
        if str(repo_id)
    })
    if not repository_ids:
        raise ValueError("interaction-field-contracts inputs publish no repository IDs")

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / INTERACTION_FIELD_CONTRACT_DATABASE
    started_at = utc_now()
    source_material = [
        {
            "role": role,
            "artifact_id": item.get("artifact_id"),
            "content_fingerprint": item.get("content_fingerprint"),
        }
        for role, (item, _manifest_path, _database_path, _manifest) in sorted(selected.items())
    ]
    build_id = stable_id("interaction_field_contract_build", scope_id, source_material, __version__)
    connection = None
    try:
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, INTERACTION_FIELD_CONTRACT_DDL)
        connection.execute(
            "INSERT INTO interaction_field_contract_build VALUES (?,?,?,?,? ,?,?,?,?)",
            [
                build_id,
                scope_id,
                __version__,
                INTERACTION_FIELD_CONTRACT_SCHEMA_VERSION,
                "building",
                started_at,
                None,
                canonical_json({}),
                canonical_json({}),
            ],
        )

        vf_path = selected["value_flow"][2]
        interactions_path = selected["interactions"][2]
        connection.execute(f"ATTACH '{str(vf_path).replace(chr(39), chr(39)*2)}' AS vf (READ_ONLY)")
        connection.execute(f"ATTACH '{str(interactions_path).replace(chr(39), chr(39)*2)}' AS si (READ_ONLY)")
        try:
            connection.execute(
                """CREATE TEMP TABLE system_boundary_interaction AS
                   SELECT * FROM si.system_boundary_interaction"""
            )
            connection.execute(
                """CREATE TEMP TABLE system_interaction_execution_context AS
                   SELECT * FROM si.system_interaction_execution_context"""
            )
            counts = materialize_system_interaction_field_contracts(
                connection,
                scope_id=scope_id,
                value_flow_evidence_relation="vf.value_flow_evidence_record",
            )
        finally:
            connection.execute("DETACH vf")
            connection.execute("DETACH si")

        field_contract_count = int(counts.get("system_interaction_field_contract") or 0)
        checks = {
            "typed_knowledge_inputs_only": True,
            "system_interactions_consumed": True,
            "repository_value_flow_consumed": True,
        }
        completed_at = utc_now()
        connection.execute(
            """UPDATE interaction_field_contract_build
               SET build_status='complete', completed_at=?, counts_json=?, checks_json=?
               WHERE build_id=?""",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=tuple(repository_ids),
            modes=("system-interactions",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("workspace-system-interaction-field-contracts",),
            capabilities=("workspace.system-interaction-field-contracts",),
            artifacts={"database": INTERACTION_FIELD_CONTRACT_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple(
                {
                    "artifact_id": item.get("artifact_id"),
                    "model_kind": item.get("model_kind"),
                    "schema_version": item.get("schema_version"),
                    "source_materialization_id": item.get("source_materialization_id"),
                    "content_fingerprint": item.get("content_fingerprint"),
                }
                for item, _manifest_path, _database_path, _manifest in selected.values()
            ),
            validation_status="complete",
            validation=checks,
            metadata={
                "produced_model": INTERACTION_FIELD_CONTRACT_SCHEMA_VERSION,
                "coverage": {"coverage_status": "complete"},
                "field_contract_count": field_contract_count,
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
