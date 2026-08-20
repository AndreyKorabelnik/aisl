from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .sql_analysis_schema import (
    SQL_ANALYSIS_DATABASE,
    SQL_ANALYSIS_DDL,
    SQL_ANALYSIS_SCHEMA_VERSION,
    SQL_ANALYSIS_TABLES,
)
from .version import __version__

WORKSPACE_SQL_CATALOG_SCHEMA_VERSION = "workspace-sql-catalog/v1"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _resolve_source(item: Mapping[str, Any]) -> tuple[Path, Path, dict[str, Any]]:
    if (
        str(item.get("model_kind") or "") != "sql-observed-data-usage"
        or str(item.get("schema_version") or "") != SQL_ANALYSIS_SCHEMA_VERSION
        or str(item.get("source_materialization_id") or "") != "sql-analysis"
    ):
        raise ValueError("workspace SQL catalog accepts only sql-observed-data-usage / knowledge_layer_sql/v2 inputs")
    location = item.get("location") or {}
    if not isinstance(location, Mapping):
        raise ValueError("knowledge artifact location must be an object")
    manifest_path = Path(str(location.get("manifest_path") or "")).expanduser().resolve()
    if not manifest_path.is_file():
        raise ValueError(f"SQL knowledge manifest is unavailable: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "knowledge_layer/v1":
        raise ValueError(f"unsupported SQL knowledge manifest schema: {manifest.get('schema_version')!r}")
    if "common.sql-analysis" not in set(str(value) for value in manifest.get("capabilities") or []):
        raise ValueError("input knowledge artifact does not publish common.sql-analysis")
    database_name = str((manifest.get("artifacts") or {}).get("database") or SQL_ANALYSIS_DATABASE)
    if Path(database_name).is_absolute():
        raise ValueError("SQL knowledge database path must be manifest-relative")
    database_path = (manifest_path.parent / database_name).resolve()
    try:
        database_path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("SQL knowledge database path escapes artifact root") from exc
    if not database_path.is_file():
        raise ValueError(f"SQL knowledge database is unavailable: {database_path}")
    return manifest_path, database_path, manifest


def _table_counts(connection: Any) -> dict[str, int]:
    counts = {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        for table in SQL_ANALYSIS_TABLES
    }
    counts["workspace_sql_catalog_source"] = int(
        connection.execute("SELECT count(*) FROM workspace_sql_catalog_source").fetchone()[0]
    )
    return counts


def build_workspace_sql_catalog(
    knowledge_items: Sequence[Mapping[str, Any]],
    output: str | Path,
    *,
    scope_id: str,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    if not str(scope_id or "").strip():
        raise ValueError("scope_id is required")
    if len(knowledge_items) < 1:
        raise ValueError("workspace SQL catalog requires at least one repository SQL knowledge artifact")

    resolved = []
    seen_artifacts: set[str] = set()
    seen_repositories: set[str] = set()
    for item in knowledge_items:
        artifact_id = str(item.get("artifact_id") or "").strip()
        if not artifact_id or artifact_id in seen_artifacts:
            raise ValueError(f"invalid or duplicate SQL knowledge artifact_id: {artifact_id!r}")
        seen_artifacts.add(artifact_id)
        manifest_path, database_path, manifest = _resolve_source(item)
        repository_ids = tuple(str(value) for value in manifest.get("repository_ids") or [] if str(value))
        if not repository_ids:
            raise ValueError(f"SQL knowledge artifact has no repository_ids: {artifact_id}")
        overlap = seen_repositories.intersection(repository_ids)
        if overlap:
            raise ValueError(f"workspace SQL catalog contains duplicate repository IDs: {sorted(overlap)}")
        seen_repositories.update(repository_ids)
        resolved.append((dict(item), manifest_path, database_path, manifest, repository_ids))

    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / SQL_ANALYSIS_DATABASE
    manifest_path = staging / "knowledge-layer-manifest.json"
    source_fingerprint_material = [
        {
            "artifact_id": item.get("artifact_id"),
            "content_fingerprint": item.get("content_fingerprint"),
            "repository_ids": list(repo_ids),
        }
        for item, _manifest_path, _database_path, _manifest, repo_ids in resolved
    ]
    build_id = stable_id("workspace_sql_catalog_build", scope_id, source_fingerprint_material, __version__)
    started_at = utc_now()
    connection = None
    try:
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, SQL_ANALYSIS_DDL)
        connection.execute(
            """CREATE TABLE workspace_sql_catalog_source (
                   artifact_id VARCHAR PRIMARY KEY,
                   content_fingerprint VARCHAR NOT NULL,
                   manifest_path VARCHAR NOT NULL,
                   repository_ids_json JSON NOT NULL,
                   source_build_id VARCHAR,
                   source_schema_version VARCHAR NOT NULL
               )"""
        )
        for ordinal, (item, source_manifest_path, source_database_path, source_manifest, repository_ids) in enumerate(resolved):
            alias = f"source_{ordinal}"
            source_sql_path = str(source_database_path).replace("\'", "\'\'")
            connection.execute(f"ATTACH '{source_sql_path}' AS {alias} (READ_ONLY)")
            try:
                for table in SQL_ANALYSIS_TABLES:
                    connection.execute(f'INSERT INTO main."{table}" SELECT * FROM {alias}."{table}"')
            finally:
                connection.execute(f"DETACH {alias}")
            connection.execute(
                "INSERT INTO workspace_sql_catalog_source VALUES (?, ?, ?, ?, ?, ?)",
                [
                    item.get("artifact_id"),
                    item.get("content_fingerprint"),
                    str(source_manifest_path),
                    canonical_json(list(repository_ids)),
                    source_manifest.get("build_id"),
                    str((source_manifest.get("metadata") or {}).get("sql_schema_version") or SQL_ANALYSIS_SCHEMA_VERSION),
                ],
            )

        duplicate_repos = connection.execute(
            "SELECT repo_id, count(*) FROM sql_analysis_repository GROUP BY repo_id HAVING count(*) > 1"
        ).fetchall()
        if duplicate_repos:
            raise ValueError(f"workspace SQL catalog has duplicate repository rows: {duplicate_repos}")
        duplicate_fact_ids: dict[str, int] = {}
        for table in SQL_ANALYSIS_TABLES:
            if table in {"sql_analysis_build", "sql_analysis_repository"}:
                continue
            info = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
            if not info:
                continue
            id_field = str(info[0][1])
            duplicate_fact_ids[table] = int(
                connection.execute(
                    f'SELECT count(*) FROM (SELECT "{id_field}" FROM "{table}" GROUP BY "{id_field}" HAVING count(*) > 1)'
                ).fetchone()[0]
            )
        if any(duplicate_fact_ids.values()):
            raise ValueError(f"workspace SQL catalog has duplicate fact identities: {duplicate_fact_ids}")

        counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        capabilities = (
            "common.sql-analysis",
            "common.sql-relation-fields",
            "common.sql-source-inventory",
            "common.sql-source-inventory-export",
            "common.sql-relation-semantic-roles",
            "common.sql-target-column-lineage",
            "common.sql-field-calculation",
            "common.sql-workflow-bindings",
            "common.sql-workflow-context",
            "common.sql-target-resolution",
            "common.sql-attribute-insertion-context",
            "common.workspace-sql-catalog",
        )
        validation = {
            "source_artifact_count": len(resolved),
            "repository_count": len(seen_repositories),
            "duplicate_fact_ids": duplicate_fact_ids,
            "repository_ids_unique": True,
        }
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id,
            repository_ids=tuple(sorted(seen_repositories)),
            modes=("sql",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("workspace-sql-catalog", "sql-relation-field-inventory", "sql-relation-semantic-roles"),
            capabilities=capabilities,
            artifacts={"database": SQL_ANALYSIS_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=tuple(
                {
                    "artifact_id": item.get("artifact_id"),
                    "content_fingerprint": item.get("content_fingerprint"),
                    "manifest_path": str(source_manifest_path),
                    "repository_ids": list(repository_ids),
                }
                for item, source_manifest_path, _source_database_path, _source_manifest, repository_ids in resolved
            ),
            validation_status="complete",
            validation=validation,
            metadata={
                "workspace_sql_catalog_schema_version": WORKSPACE_SQL_CATALOG_SCHEMA_VERSION,
                "sql_schema_version": SQL_ANALYSIS_SCHEMA_VERSION,
                "source_artifact_count": len(resolved),
                "repository_count": len(seen_repositories),
                "started_at": started_at,
                "completed_at": completed_at,
                "coverage": {
                    "coverage_status": "complete",
                    "repository_count": len(seen_repositories),
                    "source_artifact_count": len(resolved),
                },
            },
        )
        write_manifest(manifest_path, manifest)
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging)
        raise
