from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_manifest
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .physical_model_ingestion import ingest_physical_model_artifact, resolve_physical_model_artifact
from .physical_model_schema import (
    PHYSICAL_MODEL_DATABASE,
    PHYSICAL_MODEL_DDL,
    PHYSICAL_MODEL_FACT_TYPES,
    PHYSICAL_MODEL_SCHEMA_VERSION,
    PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION,
    PHYSICAL_MODEL_TABLES,
)
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _table_counts(connection: Any) -> dict[str, int]:
    return {
        table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
        for table in PHYSICAL_MODEL_TABLES
    }


def _product_coverage(artifact: Any, counts: dict[str, int]) -> dict[str, Any]:
    source_status = str((artifact.coverage or {}).get("status") or "unknown")
    gap_count = int(counts.get("physical_model_gap") or 0)
    return {
        "analysis_status": source_status,
        "coverage_basis": "physical_model_parser_contract",
        "physical_model_source_id": artifact.physical_model_source_id,
        "table_count": int(counts.get("physical_model_table") or 0),
        "column_count": int(counts.get("physical_model_column") or 0),
        "key_count": int(counts.get("physical_model_key") or 0),
        "relationship_count": int(counts.get("physical_model_relationship") or 0),
        "gap_count": gap_count,
        "does_not_claim_business_semantic_completeness": True,
    }


def _validate_physical_model(connection: Any, *, source_id: str, declared_counts: dict[str, int]) -> dict[str, Any]:
    source_rows = int(
        connection.execute(
            "SELECT count(*) FROM physical_model_source WHERE physical_model_source_id=?", [source_id]
        ).fetchone()[0]
    )
    duplicate_ids: dict[str, int] = {}
    count_matches: dict[str, bool] = {}
    for fact_type in PHYSICAL_MODEL_FACT_TYPES:
        id_field = str(connection.execute(f"PRAGMA table_info('{fact_type}')").fetchall()[0][1])
        duplicate_ids[fact_type] = int(
            connection.execute(
                f'SELECT count(*) FROM (SELECT "{id_field}" FROM "{fact_type}" '
                f'GROUP BY "{id_field}" HAVING count(*) > 1)'
            ).fetchone()[0]
        )
        actual = int(connection.execute(f'SELECT count(*) FROM "{fact_type}"').fetchone()[0])
        count_matches[fact_type] = actual == int(declared_counts[fact_type])

    orphan_columns = int(connection.execute(
        """SELECT count(*) FROM physical_model_column c
           LEFT JOIN physical_model_table t ON t.physical_model_table_id=c.physical_model_table_id
           WHERE t.physical_model_table_id IS NULL"""
    ).fetchone()[0])
    orphan_keys = int(connection.execute(
        """SELECT count(*) FROM physical_model_key k
           LEFT JOIN physical_model_table t ON t.physical_model_table_id=k.physical_model_table_id
           WHERE t.physical_model_table_id IS NULL"""
    ).fetchone()[0])
    orphan_relationship_tables = int(connection.execute(
        """SELECT count(*) FROM physical_model_relationship r
           LEFT JOIN physical_model_table p ON p.physical_model_table_id=r.parent_table_id
           LEFT JOIN physical_model_table c ON c.physical_model_table_id=r.child_table_id
           WHERE (r.parent_table_id IS NOT NULL AND p.physical_model_table_id IS NULL)
              OR (r.child_table_id IS NOT NULL AND c.physical_model_table_id IS NULL)"""
    ).fetchone()[0])
    orphan_relationship_keys = int(connection.execute(
        """SELECT count(*) FROM physical_model_relationship r
           LEFT JOIN physical_model_key k ON k.physical_model_key_id=r.parent_key_id
           WHERE r.parent_key_id IS NOT NULL AND k.physical_model_key_id IS NULL"""
    ).fetchone()[0])
    gap_count = int(connection.execute(
        "SELECT count(*) FROM physical_model_gap WHERE physical_model_source_id=?", [source_id]
    ).fetchone()[0])
    declared_gap_count = int(declared_counts.get("physical_model_gap") or 0)
    checks = {
        "source_row_present": source_rows == 1,
        "fact_counts_match_manifest": all(count_matches.values()),
        "fact_count_checks": count_matches,
        "duplicate_fact_ids": duplicate_ids,
        "orphan_columns": orphan_columns,
        "orphan_keys": orphan_keys,
        "orphan_relationship_tables": orphan_relationship_tables,
        "orphan_relationship_keys": orphan_relationship_keys,
        "gap_count_matches_manifest": gap_count == declared_gap_count,
    }
    if (
        source_rows != 1
        or not all(count_matches.values())
        or any(duplicate_ids.values())
        or orphan_columns
        or orphan_keys
        or orphan_relationship_tables
        or orphan_relationship_keys
        or gap_count != declared_gap_count
    ):
        raise ValueError(f"physical model knowledge-layer validation failed: {checks}")
    return checks


def build_physical_model_knowledge_layer(
    physical_model_manifest: str | Path,
    output: str | Path,
    *,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
    scope_id: str | None = None,
) -> dict[str, Any]:
    artifact = resolve_physical_model_artifact(physical_model_manifest)
    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging_path)
    staging_path.mkdir(parents=True)
    database_path = staging_path / PHYSICAL_MODEL_DATABASE
    manifest_path = staging_path / "knowledge-layer-manifest.json"
    build_id = stable_id(
        "physical_model_knowledge_layer_build",
        scope_id or artifact.physical_model_source_id,
        artifact.content_fingerprint,
        __version__,
    )
    started_at = utc_now()
    connection = None
    try:
        connection = connect_database(
            database_path,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            preserve_insertion_order=False,
        )
        initialize_schema(connection, PHYSICAL_MODEL_DDL)
        connection.execute(
            "INSERT INTO physical_model_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [
                build_id,
                artifact.physical_model_source_id,
                __version__,
                PHYSICAL_MODEL_SCHEMA_VERSION,
                PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION,
                artifact.content_fingerprint,
                "building",
                started_at,
                canonical_json({}),
                canonical_json({}),
            ],
        )
        imported_counts = ingest_physical_model_artifact(connection, artifact)
        checks = _validate_physical_model(
            connection,
            source_id=artifact.physical_model_source_id,
            declared_counts=imported_counts,
        )
        counts = _table_counts(connection)
        completed_at = utc_now()
        connection.execute(
            """UPDATE physical_model_build
               SET completed_at=?, build_status='complete', counts_json=?, checks_json=?
               WHERE build_id=?""",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        metadata = artifact.metadata
        source = artifact.manifest.get("source") or {}
        manifest = KnowledgeLayerManifest(
            scope_id=scope_id or artifact.physical_model_source_id,
            repository_ids=(artifact.physical_model_source_id,),
            modes=("data-model",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("physical-model-inventory", "physical-model-keys-and-relationships"),
            capabilities=(
                "common.physical-model",
                "common.physical-model.pdm",
                "common.physical-model.tables",
                "common.physical-model.columns",
                "common.physical-model.keys",
                "common.physical-model.relationships",
                "common.physical-model.gaps",
            ),
            artifacts={"database": PHYSICAL_MODEL_DATABASE, "manifest": "knowledge-layer-manifest.json"},
            source_evidence=(
                {
                    "physical_model_source_id": artifact.physical_model_source_id,
                    "physical_model_manifest": str(artifact.manifest_path),
                    "source_file": source.get("file"),
                    "source_sha256": source.get("sha256"),
                    "analysis_fingerprint": artifact.content_fingerprint,
                    "imported_counts": imported_counts,
                },
            ),
            validation_status="complete",
            validation=checks,
            metadata={
                "physical_model_schema_version": PHYSICAL_MODEL_SCHEMA_VERSION,
                "source_physical_model_schema_version": PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION,
                "source_content_fingerprint": artifact.content_fingerprint,
                "source_coverage_status": artifact.coverage.get("status"),
                "coverage": _product_coverage(artifact, counts),
                "model_name": metadata.get("model_name"),
                "model_code": metadata.get("model_code"),
                "powerdesigner_version": metadata.get("powerdesigner_version"),
                "powerdesigner_target": metadata.get("powerdesigner_target"),
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )
        write_manifest(manifest_path, manifest)
        publish_directory_atomic(
            staging_path,
            output_path,
            replace=replace,
            existing_label="knowledge-layer output",
        )
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            connection.close()
        remove_path(staging_path)
        raise
