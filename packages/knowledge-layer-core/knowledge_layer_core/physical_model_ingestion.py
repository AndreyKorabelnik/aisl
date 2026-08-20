from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .bulk import bulk_insert
from .metrics import canonical_json
from .physical_model_schema import (
    PHYSICAL_MODEL_FACT_SCHEMA_BY_TYPE,
    PHYSICAL_MODEL_FACT_TYPES,
    PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION,
    PhysicalModelFactSchema,
    database_column_name,
)


@dataclass(frozen=True, slots=True)
class ResolvedPhysicalModelArtifact:
    manifest_path: Path
    root: Path
    manifest: Mapping[str, Any]
    metadata: Mapping[str, Any]
    coverage: Mapping[str, Any]
    physical_model_source_id: str
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
        raise ValueError(f"{label} path must be artifact-local: {value!r}")
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


def resolve_physical_model_artifact(manifest_path: str | Path) -> ResolvedPhysicalModelArtifact:
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = _read_json_object(resolved_manifest_path, label="physical model manifest")
    if manifest.get("schema_version") != PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported physical model schema: {manifest.get('schema_version')!r}; "
            f"expected={PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION!r}"
        )
    source_id = str(manifest.get("physical_model_source_id") or "").strip()
    if not source_id:
        raise ValueError("physical model manifest has no physical_model_source_id")
    content_fingerprint = str(manifest.get("content_fingerprint") or "").strip()
    if not content_fingerprint:
        raise ValueError("physical model manifest has no content_fingerprint")

    raw_facts = manifest.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("physical model manifest.facts must be an array")
    fact_entries: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(raw_facts):
        if not isinstance(entry, dict):
            raise ValueError(f"physical model manifest.facts[{index}] must be an object")
        fact_type = str(entry.get("fact_type") or "").strip()
        if fact_type in fact_entries:
            raise ValueError(f"duplicate physical model fact manifest entry: {fact_type!r}")
        fact_entries[fact_type] = entry
    expected = set(PHYSICAL_MODEL_FACT_TYPES)
    actual = set(fact_entries)
    if actual != expected:
        raise ValueError(
            "physical model fact set mismatch: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    fact_order = tuple(str(entry.get("fact_type") or "") for entry in raw_facts)
    if fact_order != PHYSICAL_MODEL_FACT_TYPES:
        raise ValueError(
            "physical model fact order mismatch: "
            f"declared={list(fact_order)}, expected={list(PHYSICAL_MODEL_FACT_TYPES)}"
        )

    root = resolved_manifest_path.parent
    fingerprint = hashlib.sha256()
    for fact_type in PHYSICAL_MODEL_FACT_TYPES:
        entry = fact_entries[fact_type]
        schema = PHYSICAL_MODEL_FACT_SCHEMA_BY_TYPE[fact_type]
        if str(entry.get("id_field") or "") != schema.id_field:
            raise ValueError(
                f"physical model fact id_field mismatch for {fact_type}: "
                f"declared={entry.get('id_field')!r}, expected={schema.id_field!r}"
            )
        path = _safe_child(root, entry.get("path"), label=f"physical model fact {fact_type}")
        if not path.is_file():
            raise ValueError(f"physical model fact shard is missing: {path}")
        actual_sha, actual_size = _hash_file(path)
        if actual_sha != str(entry.get("sha256") or ""):
            raise ValueError(f"physical model fact shard hash mismatch for {fact_type}")
        if actual_size != int(entry.get("size_bytes") or 0):
            raise ValueError(f"physical model fact shard size mismatch for {fact_type}")
        for _, payload, raw_line in _iter_jsonl_objects(path):
            fact_id = str(payload.get(schema.id_field) or "").strip()
            if not fact_id:
                raise ValueError(f"physical model fact {fact_type} has no {schema.id_field}")
            observed_source_id = str(payload.get("physical_model_source_id") or "").strip()
            if observed_source_id != source_id:
                raise ValueError(
                    f"physical model source mismatch in {fact_type}/{fact_id}: "
                    f"manifest={source_id!r}, record={observed_source_id!r}"
                )
            fingerprint.update(fact_type.encode("utf-8"))
            fingerprint.update(b"\0")
            fingerprint.update(raw_line.encode("utf-8"))
            fingerprint.update(b"\n")
        declared_count = int(entry.get("record_count") or 0)
        actual_count = sum(1 for _ in _iter_jsonl_objects(path))
        if actual_count != declared_count:
            raise ValueError(
                f"physical model fact count mismatch for {fact_type}: "
                f"declared={declared_count}, actual={actual_count}"
            )
    recalculated = fingerprint.hexdigest()
    if recalculated != content_fingerprint:
        raise ValueError(
            "physical model content fingerprint mismatch: "
            f"declared={content_fingerprint}, actual={recalculated}"
        )

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("physical model manifest.source must be an object")
    metadata_path = _safe_child(root, source.get("metadata_path"), label="physical model metadata")
    metadata = _read_json_object(metadata_path, label="physical model metadata")
    if metadata.get("schema_version") != PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION:
        raise ValueError("physical model metadata schema_version does not match the manifest")
    if str(metadata.get("physical_model_source_id") or "") != source_id:
        raise ValueError("physical model metadata source id does not match the manifest")
    if str(metadata.get("source_sha256") or "") != str(source.get("sha256") or ""):
        raise ValueError("physical model source sha256 differs between metadata and manifest")

    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("physical model manifest.coverage must be an object")
    if str(coverage.get("status") or "") not in {"complete", "partial"}:
        raise ValueError(f"unsupported physical model coverage status: {coverage.get('status')!r}")
    if int(coverage.get("gap_count") or 0) != int(manifest.get("counts", {}).get("physical_model_gap") or 0):
        raise ValueError("physical model coverage gap_count does not match manifest counts")

    return ResolvedPhysicalModelArtifact(
        manifest_path=resolved_manifest_path,
        root=root,
        manifest=manifest,
        metadata=metadata,
        coverage=coverage,
        physical_model_source_id=source_id,
        content_fingerprint=content_fingerprint,
        fact_entries=fact_entries,
    )


def _iter_jsonl_objects(path: Path) -> Iterator[tuple[int, dict[str, Any], str]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL record at {path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"physical model fact must be an object: {path}:{line_number}")
            yield line_number, payload, line


def _row_for_fact(schema: PhysicalModelFactSchema, payload: Mapping[str, Any]) -> tuple[Any, ...]:
    fact_id = str(payload.get(schema.id_field) or "").strip()
    if not fact_id:
        raise ValueError(f"physical model fact {schema.fact_type} has no {schema.id_field}")
    row: list[Any] = []
    for field in schema.fields:
        value = payload.get(field)
        if database_column_name(field).endswith("_json"):
            default = {} if field == "evidence" else []
            value = canonical_json(value if value is not None else default)
        row.append(value)
    row.append(canonical_json(payload))
    return tuple(row)


def ingest_physical_model_artifact(
    connection: Any,
    artifact: ResolvedPhysicalModelArtifact,
    *,
    batch_size: int = 1000,
) -> dict[str, int]:
    metadata = artifact.metadata
    source = artifact.manifest.get("source") or {}
    coverage = artifact.coverage
    connection.execute(
        "INSERT INTO physical_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            artifact.physical_model_source_id,
            str(artifact.manifest_path),
            artifact.manifest.get("schema_version"),
            artifact.content_fingerprint,
            artifact.manifest.get("core_version"),
            source.get("file"),
            source.get("sha256"),
            metadata.get("model_object_id"),
            metadata.get("model_name"),
            metadata.get("model_code"),
            metadata.get("powerdesigner_version"),
            metadata.get("powerdesigner_target"),
            coverage.get("status"),
            int(coverage.get("gap_count") or 0),
            canonical_json(metadata),
            canonical_json(artifact.manifest),
        ],
    )

    counts: dict[str, int] = {}
    for fact_type in PHYSICAL_MODEL_FACT_TYPES:
        schema = PHYSICAL_MODEL_FACT_SCHEMA_BY_TYPE[fact_type]
        entry = artifact.fact_entries[fact_type]
        path = _safe_child(artifact.root, entry.get("path"), label=f"physical model fact {fact_type}")
        declared_count = int(entry.get("record_count") or 0)
        count = 0
        batch: list[tuple[Any, ...]] = []
        for _, payload, _ in _iter_jsonl_objects(path):
            batch.append(_row_for_fact(schema, payload))
            count += 1
            if len(batch) >= batch_size:
                bulk_insert(connection, f"INSERT INTO {fact_type} VALUES ({','.join('?' for _ in batch[0])})", batch)
                batch.clear()
        if batch:
            bulk_insert(connection, f"INSERT INTO {fact_type} VALUES ({','.join('?' for _ in batch[0])})", batch)
        if count != declared_count:
            raise ValueError(
                f"physical model fact record count mismatch for {fact_type}: "
                f"declared={declared_count}, imported={count}"
            )
        counts[fact_type] = count
    return counts
