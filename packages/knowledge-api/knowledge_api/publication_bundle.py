from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .contract_v1.models import SystemCreateRequest
from .contract_v1.runtime import ArtifactValidator, KnowledgeApiRuntimeError, KnowledgeApiSettings, sha256_file
from .contract_v1.service import KnowledgeDomainService
from .publication import build_publication_request, stable_fingerprint

BUNDLE_SCHEMA_VERSION = "aisl_publication_bundle/v2"


class RelocatingArtifactValidator(ArtifactValidator):
    """Resolve Producer-local physical paths through verified bundle mappings."""

    def __init__(
        self,
        settings: KnowledgeApiSettings,
        *,
        source_mappings: Iterable[tuple[Path, Path]],
    ) -> None:
        super().__init__(settings)
        mappings = [
            (source.expanduser().resolve(), payload.expanduser().resolve())
            for source, payload in source_mappings
        ]
        # Most-specific root wins when mappings overlap.
        self.source_mappings = tuple(sorted(mappings, key=lambda pair: len(pair[0].parts), reverse=True))

    def _relocate(self, path: Path) -> Path:
        candidate = path.expanduser()
        if not candidate.is_absolute():
            return candidate.resolve()
        resolved_candidate = candidate.resolve()
        for source_root, payload_root in self.source_mappings:
            try:
                relative = resolved_candidate.relative_to(source_root)
            except ValueError:
                continue
            relocated = (payload_root / relative).resolve()
            try:
                relocated.relative_to(payload_root)
            except ValueError as exc:  # pragma: no cover - defensive
                raise KnowledgeApiRuntimeError(400, "bundle_path_escape", "bundle relocation escaped payload root") from exc
            return relocated
        return resolved_candidate

    def resolve_file_uri(self, uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme == "file" and parsed.netloc in {"", "localhost"}:
            return self._relocate(Path(unquote(parsed.path)))
        return super().resolve_file_uri(uri)

    def validate_path(self, path: str | Path, *, directory: bool = False) -> Path:
        candidate = self._relocate(Path(path))
        return super().validate_path(candidate, directory=directory)


def _load_manifest(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = archive.read("bundle-manifest.json")
    except KeyError as exc:
        raise KnowledgeApiRuntimeError(400, "publication_bundle_manifest_missing", "bundle-manifest.json is missing") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise KnowledgeApiRuntimeError(400, "publication_bundle_manifest_invalid", "bundle manifest must be UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise KnowledgeApiRuntimeError(400, "publication_bundle_manifest_invalid", "bundle manifest root must be an object")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise KnowledgeApiRuntimeError(400, "publication_bundle_schema_unsupported", f"unsupported publication bundle schema: {manifest.get('schema_version')!r}")
    actual = str(manifest.get("bundle_fingerprint") or "")
    material = {k: v for k, v in manifest.items() if k != "bundle_fingerprint"}
    expected = stable_fingerprint(material)
    if actual != expected:
        raise KnowledgeApiRuntimeError(409, "publication_bundle_fingerprint_invalid", "publication bundle fingerprint is invalid", details={"expected": expected, "actual": actual})
    return manifest


def _safe_member_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and not name.startswith("/")


def _verify_and_extract(archive: zipfile.ZipFile, manifest: dict[str, Any], target: Path) -> None:
    members = manifest.get("members")
    if not isinstance(members, list) or not members:
        raise KnowledgeApiRuntimeError(400, "publication_bundle_members_invalid", "publication bundle must list payload members")
    expected_names = {"bundle-manifest.json"}
    by_name: dict[str, dict[str, Any]] = {}
    for raw in members:
        if not isinstance(raw, dict):
            raise KnowledgeApiRuntimeError(400, "publication_bundle_members_invalid", "bundle member must be an object")
        name = str(raw.get("path") or "")
        if not _safe_member_name(name) or not name.startswith("payload/"):
            raise KnowledgeApiRuntimeError(400, "publication_bundle_member_path_invalid", "bundle member path is unsafe", details={"path": name})
        if name in by_name:
            raise KnowledgeApiRuntimeError(409, "publication_bundle_member_duplicate", "bundle contains duplicate member metadata", details={"path": name})
        by_name[name] = raw
        expected_names.add(name)
    actual_names = {info.filename for info in archive.infolist() if not info.is_dir()}
    if actual_names != expected_names:
        raise KnowledgeApiRuntimeError(409, "publication_bundle_members_mismatch", "bundle ZIP members do not match manifest", details={"missing": sorted(expected_names - actual_names), "unexpected": sorted(actual_names - expected_names)})

    for name, raw in by_name.items():
        info = archive.getinfo(name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise KnowledgeApiRuntimeError(400, "publication_bundle_symlink_forbidden", "bundle symlinks are not allowed", details={"path": name})
        destination = (target / name).resolve()
        try:
            destination.relative_to(target.resolve())
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(400, "publication_bundle_member_path_invalid", "bundle member escapes extraction root", details={"path": name}) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with archive.open(info, "r") as source, destination.open("wb") as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        expected_sha = str(raw.get("sha256") or "")
        expected_size_raw = raw.get("byte_size")
        expected_size = -1 if expected_size_raw is None else int(expected_size_raw)
        if digest.hexdigest() != expected_sha or size != expected_size:
            raise KnowledgeApiRuntimeError(409, "publication_bundle_member_identity_invalid", "bundle member identity verification failed", details={"path": name, "expected_sha256": expected_sha, "actual_sha256": digest.hexdigest(), "expected_bytes": expected_size, "actual_bytes": size})


def _parse_source_mappings(manifest: dict[str, Any], *, staging: Path) -> tuple[tuple[Path, Path], ...]:
    raw_mappings = manifest.get("source_mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise KnowledgeApiRuntimeError(400, "publication_bundle_source_mappings_invalid", "publication bundle source_mappings must be a non-empty array")
    mappings: list[tuple[Path, Path]] = []
    seen_source: set[Path] = set()
    seen_payload: set[Path] = set()
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            raise KnowledgeApiRuntimeError(400, "publication_bundle_source_mappings_invalid", "source mapping must be an object")
        source_text = str(raw.get("source_root") or "").strip()
        prefix = str(raw.get("payload_prefix") or "").strip()
        source_root = Path(source_text).expanduser()
        if not source_text or not source_root.is_absolute():
            raise KnowledgeApiRuntimeError(400, "publication_bundle_source_root_invalid", "source mapping source_root must be absolute provenance")
        if not _safe_member_name(prefix) or not prefix.startswith("payload/"):
            raise KnowledgeApiRuntimeError(400, "publication_bundle_source_mapping_prefix_invalid", "source mapping payload_prefix is unsafe", details={"payload_prefix": prefix})
        payload_root = (staging / prefix).resolve()
        try:
            payload_root.relative_to(staging.resolve())
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(400, "publication_bundle_source_mapping_prefix_invalid", "source mapping payload_prefix escapes staging root") from exc
        source_resolved = source_root.resolve()
        if source_resolved in seen_source or payload_root in seen_payload:
            raise KnowledgeApiRuntimeError(409, "publication_bundle_source_mapping_duplicate", "publication bundle source mapping is duplicated")
        seen_source.add(source_resolved)
        seen_payload.add(payload_root)
        if not payload_root.exists():
            raise KnowledgeApiRuntimeError(400, "publication_bundle_source_mapping_unavailable", "source mapping payload root is absent from bundle", details={"payload_prefix": prefix})
        mappings.append((source_resolved, payload_root))
    return tuple(mappings)


def import_publication_bundle(
    *,
    settings: KnowledgeApiSettings,
    bundle_path: Path,
    activate: bool | None = None,
    base_revision_id: str | None = None,
) -> dict[str, Any]:
    bundle = bundle_path.expanduser().resolve()
    if not bundle.is_file():
        raise KnowledgeApiRuntimeError(400, "publication_bundle_unavailable", f"publication bundle is unavailable: {bundle}")
    with zipfile.ZipFile(bundle, "r") as archive:
        manifest = _load_manifest(archive)
        system = manifest.get("system") or {}
        system_id = str(system.get("system_id") or "").strip()
        display_name = str(system.get("display_name") or system_id).strip()
        execution = manifest.get("execution_result") or {}
        execution_member = str(execution.get("path") or "").strip()
        if not system_id or not execution_member:
            raise KnowledgeApiRuntimeError(400, "publication_bundle_manifest_invalid", "bundle system/execution_result is incomplete")

        with tempfile.TemporaryDirectory(prefix="aisl-import-") as temp_name:
            staging = Path(temp_name).resolve()
            _verify_and_extract(archive, manifest, staging)
            execution_path = (staging / execution_member).resolve()
            try:
                execution_path.relative_to(staging)
            except ValueError as exc:
                raise KnowledgeApiRuntimeError(400, "publication_bundle_execution_result_invalid", "bundle execution result escapes staging root") from exc
            if not execution_path.is_file():
                raise KnowledgeApiRuntimeError(400, "publication_bundle_execution_result_invalid", "bundle execution result is unavailable")
            if sha256_file(execution_path) != str(execution.get("sha256") or ""):
                raise KnowledgeApiRuntimeError(409, "publication_bundle_execution_result_identity_invalid", "execution result SHA-256 differs from bundle manifest")

            source_mappings = _parse_source_mappings(manifest, staging=staging)
            import_settings = KnowledgeApiSettings(
                database_path=settings.database_path,
                allowed_roots=(staging,),
                artifact_store_path=settings.artifact_store_path,
            )
            service = KnowledgeDomainService(import_settings)
            service.validator = RelocatingArtifactValidator(import_settings, source_mappings=source_mappings)

            defaults = manifest.get("publication_defaults") or {}
            request, warnings = build_publication_request(
                execution_result=execution_path,
                base_revision_id=base_revision_id,
                labels=[str(v) for v in defaults.get("labels") or []],
                metadata=dict(defaults.get("metadata") or {}),
                activate=bool(defaults.get("activate", True) if activate is None else activate),
            )
            validation = service.validate_publication(system_id, request)
            existing_system = service.store.get_system(system_id)
            if existing_system is None:
                service.create_system(SystemCreateRequest(system_id=system_id, display_name=display_name))
            existing_revision = service.store.get_revision(system_id, str(validation["revision_id"]))
            response = service.publish_revision(system_id, request, validated=validation)
            return {
                "status": "already_published" if existing_revision is not None else "published",
                "system_id": system_id,
                "revision_id": response.revision.revision_id,
                "state": response.revision.state.value,
                "active": response.revision.state.value == "active",
                "bundle": str(bundle),
                "bundle_sha256": sha256_file(bundle),
                "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
                "warnings": warnings,
                **validation,
            }
