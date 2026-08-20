from __future__ import annotations

import os
import uuid
from contextlib import suppress
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .code_declared_model_ingestion import (
    ResolvedJavaTypeStructureArtifact,
    ingest_java_type_structure_artifact,
    resolve_java_type_structure_artifact,
)
from .code_declared_model_schema import (
    CODE_DECLARED_MODEL_DATABASE,
    CODE_DECLARED_MODEL_DDL,
    CODE_DECLARED_MODEL_SCHEMA_VERSION,
    CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION,
    CODE_DECLARED_MODEL_TABLES,
)
from prepared_knowledge_runtime.contracts import KnowledgeLayerManifest
from prepared_knowledge_runtime.database import connect_database, initialize_schema
from prepared_knowledge_runtime.io import write_json, write_manifest
from .metrics import canonical_json, utc_now
from prepared_knowledge_runtime.normalization import stable_id
from .publication import publish_directory_atomic, remove_path
from .version import __version__


def _counts(connection: Any) -> dict[str, int]:
    return {table: int(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]) for table in CODE_DECLARED_MODEL_TABLES}


def _insert_gap(
    connection: Any,
    *,
    source_occurrence_id: str,
    repo_id: str,
    code: str,
    message: str,
    owner_kind: str | None = None,
    owner_occurrence_id: str | None = None,
    severity: str = "warning",
    payload: Mapping[str, Any] | None = None,
) -> None:
    payload_value = dict(payload or {})
    gap_id = stable_id("code_declared_gap", repo_id, code, owner_kind, owner_occurrence_id, message, payload_value)
    connection.execute(
        "INSERT OR IGNORE INTO code_declared_model_gap VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [gap_id, source_occurrence_id, repo_id, code, severity, owner_kind, owner_occurrence_id, message, canonical_json([]), canonical_json(payload_value)],
    )


def _materialize_effective_fields(connection: Any, artifact: ResolvedJavaTypeStructureArtifact) -> int:
    repo_id = artifact.repo_id
    source_id = artifact.source_occurrence_id
    type_rows = connection.execute(
        "SELECT type_occurrence_id FROM code_declared_type WHERE source_occurrence_id=? ORDER BY type_occurrence_id", [source_id]
    ).fetchall()
    type_ids = [row[0] for row in type_rows]
    direct_fields: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for owner, field_id, name in connection.execute(
        "SELECT owner_type_occurrence_id, field_occurrence_id, name FROM code_declared_field WHERE source_occurrence_id=? AND is_static=false ORDER BY owner_type_occurrence_id, name, field_occurrence_id",
        [source_id],
    ).fetchall():
        direct_fields[owner].append((field_id, name))
    parents: dict[str, list[str]] = defaultdict(list)
    for subtype, parent in connection.execute(
        "SELECT subtype_occurrence_id, resolved_supertype_occurrence_id FROM code_declared_inheritance WHERE source_occurrence_id=? AND resolved_supertype_occurrence_id IS NOT NULL ORDER BY subtype_occurrence_id, resolved_supertype_occurrence_id",
        [source_id],
    ).fetchall():
        parents[subtype].append(parent)

    memo: dict[str, dict[str, tuple[str, str, int]]] = {}
    visiting: set[str] = set()

    def collect(type_id: str) -> dict[str, tuple[str, str, int]]:
        if type_id in memo:
            return memo[type_id]
        if type_id in visiting:
            _insert_gap(connection, source_occurrence_id=source_id, repo_id=repo_id, code="inheritance_cycle", message="Inheritance cycle prevents effective-field expansion.", owner_kind="type", owner_occurrence_id=type_id)
            return {}
        visiting.add(type_id)
        inherited_candidates: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
        for parent in parents.get(type_id, []):
            for name, (field_id, declaring_type, depth) in collect(parent).items():
                inherited_candidates[name].append((field_id, declaring_type, depth + 1))
        result: dict[str, tuple[str, str, int]] = {}
        direct_names = {name for _, name in direct_fields.get(type_id, [])}
        for name, candidates in inherited_candidates.items():
            if name in direct_names:
                continue
            unique = {(field_id, declaring_type) for field_id, declaring_type, _ in candidates}
            if len(unique) > 1:
                _insert_gap(
                    connection,
                    source_occurrence_id=source_id,
                    repo_id=repo_id,
                    code="ambiguous_inherited_field",
                    message=f"Multiple inherited declarations compete for field {name!r}; no effective field was invented.",
                    owner_kind="type",
                    owner_occurrence_id=type_id,
                    payload={"field_name": name, "candidates": sorted([list(item) for item in unique])},
                )
                continue
            result[name] = sorted(candidates, key=lambda item: (item[2], item[1], item[0]))[0]
        for field_id, name in direct_fields.get(type_id, []):
            result[name] = (field_id, type_id, 0)
        visiting.remove(type_id)
        memo[type_id] = result
        return result

    count = 0
    for type_id in type_ids:
        for name, (field_id, declaring_type, depth) in sorted(collect(type_id).items()):
            occurrence_id = stable_id("code_declared_effective_field", repo_id, type_id, name, field_id)
            connection.execute(
                "INSERT INTO code_declared_effective_field VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [occurrence_id, source_id, repo_id, type_id, field_id, declaring_type, name, depth, depth > 0,
                 "direct_declaration" if depth == 0 else "resolved_inheritance", canonical_json({"source_field_occurrence_id": field_id, "declaring_type_occurrence_id": declaring_type})],
            )
            count += 1
    return count


def _materialize_relationships(connection: Any, artifact: ResolvedJavaTypeStructureArtifact) -> int:
    source_id = artifact.source_occurrence_id
    repo_id = artifact.repo_id
    # Relationships are an effective-model fact just like effective fields.  A field
    # declared on a base type remains the same declaration/evidence, but its effective
    # owner can be every subtype that inherits it (unless shadowed/ambiguous, which the
    # effective-field expansion has already resolved).
    rows = connection.execute(
        """
        SELECT e.effective_owner_type_occurrence_id, r.resolved_type_occurrence_id,
               f.field_occurrence_id, r.type_reference_occurrence_id, r.resolution_status,
               e.declaring_type_occurrence_id, e.is_inherited, e.inherited_depth
        FROM code_declared_effective_field e
        JOIN code_declared_field f ON f.field_occurrence_id=e.field_occurrence_id
        JOIN code_declared_type_reference r ON r.owner_occurrence_id=f.field_occurrence_id
        WHERE e.source_occurrence_id=? AND r.source_occurrence_id=?
          AND r.owner_kind='field' AND r.reference_role='field_type'
          AND r.resolved_type_occurrence_id IS NOT NULL AND f.is_static=false
        ORDER BY e.effective_owner_type_occurrence_id, f.field_occurrence_id, r.type_reference_occurrence_id
        """,
        [source_id, source_id],
    ).fetchall()
    for source_type, target_type, field_id, ref_id, resolution_status, declaring_type, is_inherited, inherited_depth in rows:
        relationship_id = stable_id("code_declared_relationship", repo_id, source_type, field_id, target_type, ref_id)
        relationship_kind = "inherited_field_type_reference" if is_inherited else "declared_field_type_reference"
        connection.execute(
            "INSERT INTO code_declared_relationship VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [relationship_id, source_id, repo_id, source_type, target_type, field_id, ref_id,
             relationship_kind, resolution_status, canonical_json({
                 "basis": "resolved_effective_field_type_reference",
                 "declaration_owner_type_occurrence_id": declaring_type,
                 "is_inherited": bool(is_inherited),
                 "inherited_depth": int(inherited_depth or 0),
                 "does_not_imply_business_association": True,
             })],
        )
    return len(rows)


def _validate(connection: Any, artifacts: Sequence[ResolvedJavaTypeStructureArtifact]) -> dict[str, Any]:
    orphan_fields = int(connection.execute(
        "SELECT count(*) FROM code_declared_field f LEFT JOIN code_declared_type t ON t.type_occurrence_id=f.owner_type_occurrence_id WHERE t.type_occurrence_id IS NULL"
    ).fetchone()[0])
    orphan_effective = int(connection.execute(
        """SELECT count(*) FROM code_declared_effective_field e
           LEFT JOIN code_declared_type t ON t.type_occurrence_id=e.effective_owner_type_occurrence_id
           LEFT JOIN code_declared_field f ON f.field_occurrence_id=e.field_occurrence_id
           WHERE t.type_occurrence_id IS NULL OR f.field_occurrence_id IS NULL"""
    ).fetchone()[0])
    duplicate_effective = int(connection.execute(
        """SELECT count(*) FROM (
               SELECT repo_id, effective_owner_type_occurrence_id, field_name
               FROM code_declared_effective_field
               GROUP BY repo_id, effective_owner_type_occurrence_id, field_name
               HAVING count(*) > 1
           )"""
    ).fetchone()[0])
    sources = int(connection.execute("SELECT count(*) FROM code_declared_model_source").fetchone()[0])
    checks = {
        "source_count_matches": sources == len(artifacts),
        "orphan_fields": orphan_fields,
        "orphan_effective_fields": orphan_effective,
        "duplicate_effective_field_names": duplicate_effective,
        "semantic_routing": "artifact_kind_plus_schema_version",
    }
    if sources != len(artifacts) or orphan_fields or orphan_effective or duplicate_effective:
        raise ValueError(f"code-declared data-model validation failed: {checks}")
    return checks


def _product_coverage(artifacts: Sequence[ResolvedJavaTypeStructureArtifact], counts: Mapping[str, int]) -> dict[str, Any]:
    by_repository = {
        artifact.repo_id: dict(artifact.artifact.get("coverage") or {})
        for artifact in artifacts
    }
    statuses = [str(item.get("coverage_status") or "unknown") for item in by_repository.values()]
    if any(status in {"partial", "unsupported", "failed"} for status in statuses):
        analysis_status = "partial"
    elif statuses and all(status == "complete" for status in statuses):
        analysis_status = "complete"
    else:
        analysis_status = "unknown"

    def total(name: str) -> int:
        return sum(int(item.get(name) or 0) for item in by_repository.values())

    status_counts: dict[str, int] = {}
    for status in statuses:
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "analysis_status": analysis_status,
        "repository_count": len(by_repository),
        "repository_status_counts": dict(sorted(status_counts.items())),
        "java_files_in_scope": total("java_files_in_scope"),
        "java_files_parsed": total("java_files_parsed"),
        "java_files_failed": total("java_files_failed"),
        "java_files_with_parse_errors": total("java_files_with_parse_errors"),
        "unresolved_type_reference_count": total("unresolved_type_reference_count"),
        "ambiguous_type_reference_count": total("ambiguous_type_reference_count"),
        "unsupported_declaration_count": total("unsupported_declaration_count"),
        "model_gap_count": int(counts.get("code_declared_model_gap") or 0),
        "source_coverage_by_repository": by_repository,
    }


def build_code_declared_data_model_knowledge_layer(
    repository_run_manifests: Iterable[str | Path],
    output: str | Path,
    *,
    scope_id: str | None = None,
    replace: bool = True,
    duckdb_memory_limit: str = "1GB",
    duckdb_threads: int = 1,
) -> dict[str, Any]:
    artifacts = tuple(resolve_java_type_structure_artifact(path) for path in repository_run_manifests)
    if not artifacts:
        raise ValueError("at least one Runner repository run manifest is required")
    repo_ids = tuple(item.repo_id for item in artifacts)
    if len(repo_ids) != len(set(repo_ids)):
        raise ValueError("repository_run_manifests must contain unique repository IDs")
    resolved_scope_id = str(scope_id or (repo_ids[0] if len(repo_ids) == 1 else stable_id("code_declared_scope", *repo_ids))).strip()
    output_path = Path(output).expanduser().resolve()
    if (output_path.exists() or output_path.is_symlink()) and not replace:
        raise FileExistsError(f"knowledge-layer output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_name(f".{output_path.name}.building-{os.getpid()}-{uuid.uuid4().hex[:12]}")
    remove_path(staging)
    staging.mkdir(parents=True)
    database_path = staging / CODE_DECLARED_MODEL_DATABASE
    build_id = stable_id("code_declared_data_model_build", resolved_scope_id, *(item.artifact.get("content_fingerprint") for item in artifacts), __version__)
    started_at = utc_now()
    connection = None
    transaction_started = False
    try:
        connection = connect_database(database_path, memory_limit=duckdb_memory_limit, threads=duckdb_threads, preserve_insertion_order=False)
        initialize_schema(connection, CODE_DECLARED_MODEL_DDL)
        # Real repositories contain thousands of declarations. Without one explicit
        # transaction DuckDB commits every row-level INSERT separately, making the
        # typed materialization I/O-bound while preserving exactly the same model.
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        connection.execute(
            "INSERT INTO code_declared_model_build VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            [build_id, resolved_scope_id, __version__, CODE_DECLARED_MODEL_SCHEMA_VERSION, CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION, "building", started_at, canonical_json({}), canonical_json({})],
        )
        imported: dict[str, dict[str, int]] = {}
        for artifact in artifacts:
            imported[artifact.repo_id] = ingest_java_type_structure_artifact(connection, artifact, scope_id=resolved_scope_id)
            imported[artifact.repo_id]["code_declared_effective_field"] = _materialize_effective_fields(connection, artifact)
            imported[artifact.repo_id]["code_declared_relationship"] = _materialize_relationships(connection, artifact)
        checks = _validate(connection, artifacts)
        counts = _counts(connection)
        completed_at = utc_now()
        connection.execute(
            "UPDATE code_declared_model_build SET completed_at=?, build_status='complete', counts_json=?, checks_json=? WHERE build_id=?",
            [completed_at, canonical_json(counts), canonical_json(checks), build_id],
        )
        connection.execute("COMMIT")
        transaction_started = False
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None

        product_coverage = _product_coverage(artifacts, counts)
        summary = {
            "schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
            "scope_id": resolved_scope_id,
            "repository_ids": list(repo_ids),
            "source_schema_version": CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION,
            "counts": counts,
            "coverage": product_coverage,
            "semantic_notes": {
                "physical_schema_substitution": False,
                "persistence_interpretation": False,
                "business_association_inference": False,
            },
        }
        write_json(staging / "code-declared-data-model.json", summary)
        manifest = KnowledgeLayerManifest(
            scope_id=resolved_scope_id,
            repository_ids=repo_ids,
            modes=("data-model",),
            producer_version=__version__,
            build_id=build_id,
            build_status="complete",
            counts=counts,
            materialized_marts=("code-declared-types", "code-declared-fields", "code-declared-inheritance", "code-declared-effective-fields", "code-declared-relationships", "code-declared-model-gaps"),
            capabilities=("common.code-declared-data-model", "common.code-declared-entities", "common.code-declared-fields", "common.code-declared-relationships", "common.code-declared-inheritance"),
            artifacts={"database": CODE_DECLARED_MODEL_DATABASE, "model_summary": "code-declared-data-model.json"},
            source_evidence=tuple({
                "repo_id": artifact.repo_id,
                "runner_manifest": str(artifact.runner_manifest_path),
                "artifact_id": artifact.artifact.get("artifact_id"),
                "artifact_kind": artifact.artifact.get("artifact_kind"),
                "schema_version": artifact.artifact.get("schema_version"),
                "content_fingerprint": artifact.artifact.get("content_fingerprint"),
                "source_snapshot_fingerprint": (artifact.artifact.get("source_snapshot") or {}).get("fingerprint"),
                "imported_counts": imported[artifact.repo_id],
            } for artifact in artifacts),
            validation_status="complete",
            validation=checks,
            metadata={
                "model_schema_version": CODE_DECLARED_MODEL_SCHEMA_VERSION,
                "source_schema_version": CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION,
                "semantic_routing": "artifact_kind_plus_schema_version",
                "legacy_policy": "not_supported",
                "coverage": product_coverage,
                "started_at": started_at,
                "completed_at": completed_at,
            },
        )
        write_manifest(staging / "knowledge-layer-manifest.json", manifest)
        publish_directory_atomic(staging, output_path, replace=replace, existing_label="knowledge-layer output")
        return manifest.to_dict()
    except Exception:
        if connection is not None:
            if transaction_started:
                with suppress(Exception):
                    connection.execute("ROLLBACK")
            connection.close()
        remove_path(staging)
        raise
