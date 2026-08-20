from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_json
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .value_flow import materialize_repository_value_flow
from .value_flow_knowledge_schema import VALUE_FLOW_KNOWLEDGE_DATABASE, VALUE_FLOW_KNOWLEDGE_DDL
from .version import __version__


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _resolve(
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
    database_name = str((manifest.get("artifacts") or {}).get("database") or VALUE_FLOW_KNOWLEDGE_DATABASE)
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


def build_cross_repository_value_flow_knowledge_layer(
    knowledge_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    specs = {
        "value_flow": ("repository-value-flow", "repository_value_flow/v6", "repository-value-flow"),
        "interactions": ("system-interactions", "workspace_system_interaction/v6", "system-interactions"),
        "field_contracts": (
            "interaction-field-contracts",
            "workspace_system_interaction_field_contract/v2",
            "interaction-field-contracts",
        ),
    }
    selected: dict[str, tuple[Mapping[str, Any], Path, Path, dict[str, Any]]] = {}
    for role, expected in specs.items():
        matches = [
            item for item in knowledge_items
            if (
                str(item.get("model_kind") or ""),
                str(item.get("schema_version") or ""),
                str(item.get("source_materialization_id") or ""),
            ) == expected
        ]
        if len(matches) != 1:
            raise ValueError(f"cross-repository-value-flow requires exactly one {role} knowledge artifact")
        selected[role] = (matches[0], *_resolve(
            matches[0],
            model_kind=expected[0],
            schema_version=expected[1],
            source_materialization_id=expected[2],
        ))

    source_value_flow_db = selected["value_flow"][2]
    source_manifest = selected["value_flow"][3]
    repository_ids = tuple(str(value) for value in (source_manifest.get("repository_ids") or []) if str(value))
    if not repository_ids:
        raise ValueError("repository-value-flow source publishes no repository IDs")

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / VALUE_FLOW_KNOWLEDGE_DATABASE
    shutil.copy2(source_value_flow_db, database_path)

    source_material = [
        {
            "role": role,
            "artifact_id": item.get("artifact_id"),
            "content_fingerprint": item.get("content_fingerprint"),
        }
        for role, (item, _manifest_path, _database_path, _manifest) in sorted(selected.items())
    ]
    build_id = stable_id("cross_repository_value_flow_build", scope_id, source_material, __version__)
    started_at = utc_now()
    connection = None
    try:
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, VALUE_FLOW_KNOWLEDGE_DDL)
        interactions_db = selected["interactions"][2]
        contracts_db = selected["field_contracts"][2]
        connection.execute(f"ATTACH '{str(interactions_db).replace(chr(39), chr(39)*2)}' AS si (READ_ONLY)")
        connection.execute(f"ATTACH '{str(contracts_db).replace(chr(39), chr(39)*2)}' AS fc (READ_ONLY)")
        try:
            connection.execute("CREATE TEMP TABLE system_boundary_interaction AS SELECT * FROM si.system_boundary_interaction")
            connection.execute("CREATE TEMP TABLE system_interaction_execution_context AS SELECT * FROM si.system_interaction_execution_context")
            connection.execute("CREATE TEMP TABLE system_interaction_field_contract AS SELECT * FROM fc.system_interaction_field_contract")
            counts = materialize_repository_value_flow(connection, scope_id=scope_id)
            transport_edge_count = int(connection.execute(
                """SELECT count(*) FROM repository_value_flow_edge
                   WHERE scope_id=? AND source_repo_id<>target_repo_id AND flow_kind='transport'""",
                [scope_id],
            ).fetchone()[0])
        finally:
            connection.execute("DETACH si")
            connection.execute("DETACH fc")
        counts = {**counts, "cross_repository_transport_edge": transport_edge_count}
        completed_at = utc_now()
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        checks = {
            "typed_knowledge_inputs_only": True,
            "transport_edges_materialized": transport_edge_count > 0,
        }
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=repository_ids,
            modes=("repository-value-flow",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("workspace-repository-value-flow", "workspace-cross-repository-value-flow"),
            capabilities=(
                "workspace.repository-value-flow",
                "workspace.attribute-path-resolver",
                "workspace.cross-repository-value-flow",
            ),
            artifacts={"database": VALUE_FLOW_KNOWLEDGE_DATABASE, "manifest": "knowledge-layer-manifest.json"},
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
                "produced_model": "repository_value_flow/v6",
                "coverage": {"coverage_status": "complete"},
                "transport_edge_count": transport_edge_count,
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
