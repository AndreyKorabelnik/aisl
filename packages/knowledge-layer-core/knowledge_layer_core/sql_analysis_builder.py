from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .metrics import canonical_json, utc_now
from .progress import emit_progress, timed_phase
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .sql_analysis_ingestion import ingest_sql_analysis_artifact, resolve_sql_analysis_artifact
from .sql_relation_roles import materialize_sql_relation_semantic_roles
from .sql_workflow_context import materialize_sql_workflow_context
from .sql_workflow_target_lineage import materialize_sql_workflow_target_lineage
from .sql_analysis_schema import (
    SQL_ANALYSIS_DATABASE,
    SQL_ANALYSIS_DDL,
    SQL_ANALYSIS_FACT_TYPES,
    SQL_ANALYSIS_SCHEMA_VERSION,
    SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
    SQL_ANALYSIS_TABLES,
)
from .version import __version__


def _table_counts(connection: Any) -> dict[str, int]:
    return {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        for table in SQL_ANALYSIS_TABLES
    }


def _validate_sql_scope(connection: Any, *, repo_id: str, declared_counts: dict[str, int]) -> dict[str, Any]:
    repository_rows = int(
        connection.execute("SELECT count(*) FROM sql_analysis_repository WHERE repo_id=?", [repo_id]).fetchone()[0]
    )
    duplicate_ids: dict[str, int] = {}
    count_matches: dict[str, bool] = {}
    for fact_type in SQL_ANALYSIS_FACT_TYPES:
        id_field = connection.execute(f"PRAGMA table_info('{fact_type}')").fetchall()[0][1]
        duplicate_ids[fact_type] = int(
            connection.execute(
                f'SELECT count(*) FROM (SELECT "{id_field}" FROM "{fact_type}" '
                f'GROUP BY "{id_field}" HAVING count(*) > 1)'
            ).fetchone()[0]
        )
        actual = int(connection.execute(f'SELECT count(*) FROM "{fact_type}"').fetchone()[0])
        count_matches[fact_type] = actual == int(declared_counts[fact_type])
    orphan_column_relations = int(
        connection.execute(
            """SELECT count(*)
               FROM sql_column_usage u
               LEFT JOIN sql_relation r ON r.repo_id=u.repo_id AND r.sql_relation_id=u.relation_id
               WHERE u.relation_id IS NOT NULL AND r.sql_relation_id IS NULL"""
        ).fetchone()[0]
    )
    checks = {
        "repository_row_present": repository_rows == 1,
        "fact_counts_match_manifest": all(count_matches.values()),
        "fact_count_checks": count_matches,
        "duplicate_fact_ids": duplicate_ids,
        "orphan_column_relation_references": orphan_column_relations,
    }
    if repository_rows != 1 or not all(count_matches.values()) or any(duplicate_ids.values()) or orphan_column_relations:
        raise ValueError(f"SQL knowledge-layer validation failed: {checks}")
    return checks


def build_sql_knowledge_layer(
    sql_analysis_manifest: str | Path,
    output: str | Path,
    *,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    artifact = resolve_sql_analysis_artifact(sql_analysis_manifest)
    output_path = Path(output).resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path)
    staging_path.mkdir(parents=True)
    database_path = staging_path / SQL_ANALYSIS_DATABASE
    manifest_path = staging_path / "knowledge-layer-manifest.json"
    build_id = stable_id(
        "sql_knowledge_layer_build",
        artifact.repo_id,
        artifact.content_fingerprint,
        __version__,
    )
    started_at = utc_now()
    connection = None
    try:
        emit_progress(
            f"sql-analysis build repo={artifact.repo_id} memory_limit={duckdb_memory_limit} threads={duckdb_threads}"
        )
        with timed_phase("sql-analysis database initialize"):
            connection = connect_database(
                database_path,
                memory_limit=duckdb_memory_limit,
                threads=duckdb_threads,
                preserve_insertion_order=False,
            )
            initialize_schema(connection, SQL_ANALYSIS_DDL)
            connection.execute(
                "INSERT INTO sql_analysis_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                [
                    build_id,
                    artifact.repo_id,
                    __version__,
                    SQL_ANALYSIS_SCHEMA_VERSION,
                    SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
                    artifact.content_fingerprint,
                    "building",
                    started_at,
                    canonical_json({}),
                    canonical_json({}),
                ],
            )
        with timed_phase("sql-analysis ingest all facts"):
            imported_counts = ingest_sql_analysis_artifact(connection, artifact)
        with timed_phase("sql-analysis workflow_context"):
            workflow_context_summary = materialize_sql_workflow_context(connection, repo_id=artifact.repo_id)
        emit_progress(f"sql-analysis workflow_context summary={workflow_context_summary}")
        with timed_phase("sql-analysis workflow_target_lineage"):
            workflow_target_lineage_summary = materialize_sql_workflow_target_lineage(connection, repo_id=artifact.repo_id)
        emit_progress(f"sql-analysis workflow_target_lineage summary={workflow_target_lineage_summary}")
        with timed_phase("sql-analysis relation_semantic_roles"):
            relation_role_summary = materialize_sql_relation_semantic_roles(connection, repo_id=artifact.repo_id)
        emit_progress(f"sql-analysis relation_semantic_roles summary={relation_role_summary}")
        with timed_phase("sql-analysis validation"):
            checks = _validate_sql_scope(connection, repo_id=artifact.repo_id, declared_counts=imported_counts)
            checks["workflow_context"] = workflow_context_summary
            checks["workflow_target_column_lineage"] = workflow_target_lineage_summary
            checks["relation_semantic_roles"] = relation_role_summary
        with timed_phase("sql-analysis table counts"):
            counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute(
            """UPDATE sql_analysis_build
               SET completed_at=?, build_status='complete', counts_json=?, checks_json=?
               WHERE build_id=?""",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        with timed_phase("sql-analysis checkpoint"):
            connection.execute("CHECKPOINT")
        with timed_phase("sql-analysis database close"):
            connection.close()
            connection = None

        source_manifest = artifact.manifest
        manifest = KnowledgeLayerManifest(
            scope_id=artifact.repo_id,
            repository_ids=(artifact.repo_id,),
            modes=("sql",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("sql-relation-field-inventory", "sql-relation-semantic-roles"),
            capabilities=(
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
            ),
            artifacts={"database": SQL_ANALYSIS_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=(
                {
                    "repo_id": artifact.repo_id,
                    "sql_analysis_manifest": str(artifact.manifest_path),
                    "analysis_fingerprint": artifact.content_fingerprint,
                    "analysis_status": source_manifest.get("analysis_status"),
                    "imported_counts": imported_counts,
                },
            ),
            validation_status="complete",
            validation=checks,
            metadata={
                "sql_schema_version": SQL_ANALYSIS_SCHEMA_VERSION,
                "source_sql_schema_version": SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
                "source_content_fingerprint": artifact.content_fingerprint,
                "source_analysis_status": source_manifest.get("analysis_status"),
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )
        with timed_phase("sql-analysis manifest write"):
            write_manifest(manifest_path, manifest)
        with timed_phase("sql-analysis atomic publish"):
            publish_directory_atomic(
                staging_path,
                output_path,
                replace=replace,
                existing_label="knowledge-layer output",
            )
        emit_progress(
            "sql-analysis completed counts "
            + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        )
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging_path)
        raise
