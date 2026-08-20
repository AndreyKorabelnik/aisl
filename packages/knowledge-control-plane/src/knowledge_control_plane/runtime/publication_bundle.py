from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from knowledge_control_plane import __version__

BUNDLE_SCHEMA_VERSION = "aisl_publication_bundle/v2"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    resolved = path.expanduser().resolve()
    candidate_root = root.expanduser().resolve()
    return resolved == candidate_root or candidate_root in resolved.parents


def _minimal_roots(roots: Iterable[Path], *, protected_root: Path) -> list[Path]:
    protected = protected_root.expanduser().resolve()
    unique = sorted({root.expanduser().resolve() for root in roots if root}, key=lambda p: (len(p.parts), str(p)))
    result: list[Path] = []
    for root in unique:
        if _is_within(root, protected):
            continue
        if any(_is_within(root, existing) for existing in result):
            continue
        result = [existing for existing in result if not _is_within(existing, root)]
        result.append(root)
    return sorted(result, key=str)


def _collect_external_publication_roots(payload: Mapping[str, Any], *, execution_root: Path) -> list[Path]:
    """Return bounded producer-local roots required by Server publication validation.

    The execution tree is always bundled separately. External roots are derived
    only from physical artifact locations that the Server publication engine may
    read: Core evidence descriptors/packages and Knowledge Layer output packages.
    Provenance-only paths are deliberately not copied.
    """
    candidates: list[Path] = []

    for raw in payload.get("evidence_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        location = raw.get("location") or {}
        if not isinstance(location, Mapping) or str(location.get("kind") or "") != "file":
            continue
        text = str(location.get("path") or "").strip()
        path = Path(text).expanduser() if text else None
        if path is not None and path.is_absolute() and path.exists():
            # Evidence packages may contain descriptor-relative manifests/shards,
            # therefore package the descriptor directory rather than one file.
            candidates.append(path.resolve().parent)

    for raw in payload.get("knowledge_artifacts") or []:
        if not isinstance(raw, Mapping):
            continue
        location = raw.get("location") or {}
        if not isinstance(location, Mapping) or str(location.get("kind") or "") != "knowledge-layer":
            continue
        output_text = str(location.get("output_path") or "").strip()
        manifest_text = str(location.get("manifest_path") or "").strip()
        output_path = Path(output_text).expanduser() if output_text else None
        manifest_path = Path(manifest_text).expanduser() if manifest_text else None
        if output_path is not None and output_path.is_absolute() and output_path.is_dir():
            candidates.append(output_path.resolve())
        elif manifest_path is not None and manifest_path.is_absolute() and manifest_path.is_file():
            candidates.append(manifest_path.resolve().parent)

    return _minimal_roots(candidates, protected_root=execution_root)


@dataclass(frozen=True, slots=True)
class PublicationBundleResult:
    path: Path
    sha256: str
    member_count: int
    schema_version: str = BUNDLE_SCHEMA_VERSION


def build_publication_bundle(
    *,
    job_id: str,
    system_id: str,
    display_name: str,
    execution_root: Path,
    execution_result_path: Path,
    output_path: Path,
    labels: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> PublicationBundleResult:
    """Create a self-contained, transportable Producer output.

    All physical artifact bytes that the Server publication engine may read are
    copied into the bundle. Producer-local absolute paths remain unchanged in
    knowledge/provenance bytes; source mappings let Server relocate validated
    artifact reads to verified bundle members without shared filesystem access.
    """
    root = execution_root.expanduser().resolve()
    result_path = execution_result_path.expanduser().resolve()
    if root not in result_path.parents or not result_path.is_file():
        raise ValueError("execution_result_path must be a file inside execution_root")

    try:
        execution_payload = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("execution_result_path must contain UTF-8 JSON") from exc
    if not isinstance(execution_payload, dict):
        raise ValueError("execution result root must be an object")

    source_mappings: list[dict[str, str]] = [
        {
            "source_root": str(root),
            "payload_prefix": "payload/execution",
            "role": "execution",
        }
    ]
    roots_with_prefixes: list[tuple[Path, str]] = [(root, "payload/execution")]
    for index, external_root in enumerate(_collect_external_publication_roots(execution_payload, execution_root=root), start=1):
        prefix = f"payload/external/{index:03d}-{hashlib.sha256(str(external_root).encode('utf-8')).hexdigest()[:16]}"
        source_mappings.append(
            {
                "source_root": str(external_root),
                "payload_prefix": prefix,
                "role": "publication-artifact-package",
            }
        )
        roots_with_prefixes.append((external_root, prefix))

    members: list[dict[str, Any]] = []
    files_to_archive: list[tuple[Path, str]] = []
    seen_archive_paths: set[str] = set()
    for source_root, prefix in roots_with_prefixes:
        for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
            rel = path.relative_to(source_root).as_posix()
            archive_path = f"{prefix}/{rel}"
            if archive_path in seen_archive_paths:
                raise ValueError(f"duplicate publication bundle member path: {archive_path}")
            seen_archive_paths.add(archive_path)
            files_to_archive.append((path, archive_path))
            members.append(
                {
                    "path": archive_path,
                    "source_path": str(path.resolve()),
                    "sha256": _sha256_file(path),
                    "byte_size": path.stat().st_size,
                }
            )

    execution_archive_path = f"payload/execution/{result_path.relative_to(root).as_posix()}"
    manifest: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "producer": {"component": "knowledge-control-plane", "version": __version__},
        "job_id": job_id,
        "system": {"system_id": system_id, "display_name": display_name},
        "source_mappings": source_mappings,
        "execution_result": {
            "path": execution_archive_path,
            "source_path": str(result_path),
            "sha256": _sha256_file(result_path),
            "schema_version": "knowledge_execution_result/v2",
        },
        "publication_defaults": {
            "activate": True,
            "labels": list(labels or ["automated-analysis"]),
            "metadata": dict(metadata or {}),
        },
        "members": members,
    }
    manifest["bundle_fingerprint"] = _stable_fingerprint(manifest)

    target = output_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "bundle-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        for path, archive_path in files_to_archive:
            archive.write(path, arcname=archive_path)
    tmp.replace(target)
    return PublicationBundleResult(
        path=target,
        sha256=_sha256_file(target),
        member_count=len(members),
    )
