from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .bulk import bulk_insert
from .metrics import canonical_json
from .progress import emit_progress, timed_phase
from .sql_analysis_schema import (
    SQL_ANALYSIS_FACT_TYPES,
    SQL_ANALYSIS_SOURCE_SCHEMA_VERSION,
    SQL_FACT_SCHEMA_BY_TYPE,
    SqlFactSchema,
    database_column_name,
)


@dataclass(frozen=True, slots=True)
class ResolvedSqlAnalysisArtifact:
    manifest_path: Path
    root: Path
    manifest: Mapping[str, Any]
    coverage: Mapping[str, Any]
    repo_id: str
    content_fingerprint: str
    fact_entries: Mapping[str, Mapping[str, Any]]


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def _safe_child(root: Path, raw_path: Any, *, label: str) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError(f"{label} path must not be empty")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} path must be repository-local: {value!r}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} path escapes artifact root: {value!r}") from exc
    return candidate


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def resolve_sql_analysis_artifact(sql_analysis_manifest: str | Path) -> ResolvedSqlAnalysisArtifact:
    manifest_path = Path(sql_analysis_manifest).resolve()
    manifest = _read_json_object(manifest_path, label="SQL analysis manifest")
    if manifest.get("schema_version") != SQL_ANALYSIS_SOURCE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported SQL analysis schema: {manifest.get('schema_version')!r}; "
            f"expected={SQL_ANALYSIS_SOURCE_SCHEMA_VERSION!r}"
        )
    if manifest.get("artifact") != "sql_analysis":
        raise ValueError(f"not a SQL analysis artifact: {manifest_path}")
    repository = manifest.get("repository")
    if not isinstance(repository, dict):
        raise ValueError("SQL analysis manifest.repository must be an object")
    repo_id = str(repository.get("repo_id") or "").strip()
    if not repo_id:
        raise ValueError("SQL analysis manifest has no repository.repo_id")
    content_fingerprint = str(manifest.get("content_fingerprint") or "").strip()
    if not content_fingerprint:
        raise ValueError("SQL analysis manifest has no content_fingerprint")

    raw_facts = manifest.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("SQL analysis manifest.facts must be an array")
    fact_entries: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(raw_facts):
        if not isinstance(entry, dict):
            raise ValueError(f"SQL analysis manifest.facts[{index}] must be an object")
        fact_type = str(entry.get("fact_type") or "").strip()
        if fact_type in fact_entries:
            raise ValueError(f"duplicate SQL fact manifest entry: {fact_type!r}")
        fact_entries[fact_type] = entry
    expected = set(SQL_ANALYSIS_FACT_TYPES)
    actual = set(fact_entries)
    if actual != expected:
        raise ValueError(
            "SQL analysis fact set mismatch: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    fact_order = tuple(str(entry.get("fact_type") or "") for entry in raw_facts)
    if fact_order != SQL_ANALYSIS_FACT_TYPES:
        raise ValueError(
            "SQL analysis fact order mismatch: "
            f"declared={list(fact_order)}, expected={list(SQL_ANALYSIS_FACT_TYPES)}"
        )

    root = manifest_path.parent
    for fact_type in SQL_ANALYSIS_FACT_TYPES:
        entry = fact_entries[fact_type]
        schema = SQL_FACT_SCHEMA_BY_TYPE[fact_type]
        if str(entry.get("id_field") or "") != schema.id_field:
            raise ValueError(
                f"SQL fact id_field mismatch for {fact_type}: "
                f"declared={entry.get('id_field')!r}, expected={schema.id_field!r}"
            )
        path = _safe_child(root, entry.get("path"), label=f"SQL fact {fact_type}")
        if not path.is_file():
            raise ValueError(f"SQL fact shard is missing: {path}")
        actual_sha, actual_size = _hash_file(path)
        declared_sha = str(entry.get("sha256") or "").strip()
        declared_size = int(entry.get("byte_size") or 0)
        if actual_sha != declared_sha:
            raise ValueError(
                f"SQL fact shard hash mismatch for {fact_type}: declared={declared_sha}, actual={actual_sha}"
            )
        if actual_size != declared_size:
            raise ValueError(
                f"SQL fact shard size mismatch for {fact_type}: declared={declared_size}, actual={actual_size}"
            )

    coverage_entry = manifest.get("coverage")
    if not isinstance(coverage_entry, dict):
        raise ValueError("SQL analysis manifest.coverage must be an object")
    coverage_path = _safe_child(root, coverage_entry.get("path"), label="SQL analysis coverage")
    actual_sha, actual_size = _hash_file(coverage_path)
    if actual_sha != str(coverage_entry.get("sha256") or ""):
        raise ValueError("SQL analysis coverage hash mismatch")
    if actual_size != int(coverage_entry.get("byte_size") or 0):
        raise ValueError("SQL analysis coverage size mismatch")
    coverage = _read_json_object(coverage_path, label="SQL analysis coverage")
    if coverage.get("schema_version") != SQL_ANALYSIS_SOURCE_SCHEMA_VERSION:
        raise ValueError("SQL analysis coverage schema_version does not match the manifest")
    fingerprint_input = "\n".join(
        f"{entry['fact_type']}:{int(entry.get('record_count') or 0)}:{entry.get('sha256')}"
        for entry in raw_facts
    ) + f"\ncoverage:{actual_sha}"
    recalculated_fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    if recalculated_fingerprint != content_fingerprint:
        raise ValueError(
            "SQL analysis content fingerprint mismatch: "
            f"declared={content_fingerprint}, actual={recalculated_fingerprint}"
        )
    return ResolvedSqlAnalysisArtifact(
        manifest_path=manifest_path,
        root=root,
        manifest=manifest,
        coverage=coverage,
        repo_id=repo_id,
        content_fingerprint=content_fingerprint,
        fact_entries=fact_entries,
    )


def _iter_jsonl_objects(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL record at {path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"SQL fact record must be an object: {path}:{line_number}")
            yield line_number, payload



def _is_absolute_path_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text.startswith(("/", "\\")) or (len(text) >= 3 and text[1] == ":" and text[2] in {"/", "\\"})


def _nonportable_locations(value: Any, path: str = "$") -> list[str]:
    issues: list[str] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_nonportable_locations(item, f"{path}[{index}]"))
        return issues
    if not isinstance(value, Mapping):
        return issues
    for key, item in value.items():
        location = f"{path}.{key}"
        if key in {"absolute_file", "repo_path", "analysis_out", "static_analysis_output"}:
            issues.append(location)
        if key in {"file", "relative_file"} and isinstance(item, str) and _is_absolute_path_text(item):
            issues.append(location)
        issues.extend(_nonportable_locations(item, location))
    return issues

def _row_for_fact(schema: SqlFactSchema, payload: Mapping[str, Any], *, repo_id: str) -> tuple[Any, ...]:
    if payload.get("fact_type") != schema.fact_type:
        raise ValueError(
            f"SQL fact_type mismatch in {schema.fact_type}: observed={payload.get('fact_type')!r}"
        )
    fact_id = str(payload.get(schema.id_field) or "").strip()
    if not fact_id:
        raise ValueError(f"SQL fact {schema.fact_type} has no {schema.id_field}")
    observed_repo_id = str(payload.get("repo_id") or "").strip()
    if observed_repo_id != repo_id:
        raise ValueError(
            f"SQL fact repo_id mismatch in {schema.fact_type}/{fact_id}: "
            f"manifest={repo_id!r}, record={observed_repo_id!r}"
        )
    nonportable = _nonportable_locations(payload)
    if nonportable:
        raise ValueError(
            f"SQL fact contains nonportable evidence paths in {schema.fact_type}/{fact_id}: {nonportable[:10]}"
        )
    row: list[Any] = []
    for field in schema.fields:
        value = payload.get(field)
        if schema.fact_type == "sql_workflow_binding" and field == "scalar_value":
            if value is None:
                value = ""
            elif isinstance(value, bool):
                value = "true" if value else "false"
            else:
                value = str(value)
        if database_column_name(field).endswith("_json"):
            value = canonical_json(value if value is not None else [])
        row.append(value)
    row.append(canonical_json(payload))
    return tuple(row)


def ingest_sql_analysis_artifact(
    connection: Any,
    artifact: ResolvedSqlAnalysisArtifact,
    *,
    batch_size: int = 1000,
) -> dict[str, int]:
    manifest = artifact.manifest
    repository = manifest.get("repository") or {}
    producer = manifest.get("producer") or {}
    connection.execute(
        "INSERT INTO sql_analysis_repository VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            artifact.repo_id,
            str(artifact.manifest_path),
            manifest.get("schema_version"),
            artifact.content_fingerprint,
            manifest.get("analysis_status"),
            repository.get("system_name"),
            repository.get("project_code"),
            repository.get("analysis_profile"),
            producer.get("name"),
            producer.get("version"),
            manifest.get("created_at"),
            canonical_json(artifact.coverage),
            canonical_json(manifest),
        ],
    )

    counts: dict[str, int] = {}
    for fact_type in SQL_ANALYSIS_FACT_TYPES:
        schema = SQL_FACT_SCHEMA_BY_TYPE[fact_type]
        entry = artifact.fact_entries[fact_type]
        path = _safe_child(artifact.root, entry.get("path"), label=f"SQL fact {fact_type}")
        declared_count = int(entry.get("record_count") or 0)
        with timed_phase(f"sql-analysis ingest {fact_type} records={declared_count}"):
            count = 0
            batch: list[tuple[Any, ...]] = []
            for _, payload in _iter_jsonl_objects(path):
                batch.append(_row_for_fact(schema, payload, repo_id=artifact.repo_id))
                count += 1
                if len(batch) >= batch_size:
                    bulk_insert(connection, f"INSERT INTO {fact_type} VALUES ({','.join('?' for _ in batch[0])})", batch)
                    batch.clear()
            if batch:
                bulk_insert(connection, f"INSERT INTO {fact_type} VALUES ({','.join('?' for _ in batch[0])})", batch)
            if count != declared_count:
                raise ValueError(
                    f"SQL fact record count mismatch for {fact_type}: declared={declared_count}, imported={count}"
                )
            counts[fact_type] = count
    emit_progress(
        "sql-analysis ingest summary "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    return counts
