from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from knowledge_control_plane.api.generic_v1.models import (
    ArtifactContentResponse,
    ArtifactKind,
    ArtifactListResponse,
    ArtifactSummary,
)

from .errors import ResourceNotFound, RuntimeApiError
from .store import RuntimeStore, utc_now

_TEXT_MEDIA_TYPES = {
    "application/json",
    "application/yaml",
    "application/x-yaml",
    "application/xml",
    "application/sql",
}
_TEXT_SUFFIXES = {".txt", ".log", ".md", ".json", ".yaml", ".yml", ".xml", ".sql", ".csv"}
_INTERNAL_ARTIFACT_NAMES = {".knowledge-control-plane-output.json", ".static-analysis-runner-output.json"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    @staticmethod
    def _is_deep_core_evidence_payload(path: Path, output_path: Path) -> bool:
        """Return True for producer-internal files below ``core-evidence/evidence/<payload>/``.

        KCP is an orchestration/artifact surface, not a second Core evidence catalog.
        The immediate typed evidence descriptor under ``core-evidence/evidence`` stays
        indexable, while its potentially very large internal payload package remains
        on disk and is reached through the official Core/Runner provenance contract.
        Recursively hashing every payload shard can dominate or stall one-shot
        publication without adding a new canonical source of truth.
        """
        try:
            parts = path.relative_to(output_path).parts
        except ValueError:
            return False
        for index in range(len(parts) - 1):
            if parts[index : index + 2] == ("core-evidence", "evidence"):
                # One component after `evidence` is the typed evidence descriptor
                # itself. Two or more components means a producer-internal payload
                # subtree (for example `<artifact>-payload/facts/...`).
                return len(parts) - (index + 2) >= 2
        return False

    def scan(self, *, job_id: str, output_path: Path, relative_prefix: str | None = None) -> list[ArtifactSummary]:
        if not output_path.exists() or not output_path.is_dir():
            return []
        registered: list[ArtifactSummary] = []
        for path in sorted(
            item
            for item in output_path.rglob("*")
            if item.is_file()
            and item.name not in _INTERNAL_ARTIFACT_NAMES
            and not self._is_deep_core_evidence_payload(item, output_path)
        ):
            try:
                relative = path.relative_to(output_path).as_posix()
            except ValueError:
                continue
            if relative_prefix:
                relative = f"{relative_prefix.strip('/')}/{relative}"
            summary = self._summary(job_id=job_id, path=path, relative=relative)
            self.store.upsert_artifact(summary, path.resolve())
            registered.append(summary)
        return registered

    def register_file(
        self,
        *,
        job_id: str,
        path: Path,
        relative_path: str | None = None,
        kind: ArtifactKind | None = None,
    ) -> ArtifactSummary:
        path = path.resolve()
        summary = self._summary(
            job_id=job_id,
            path=path,
            relative=relative_path or path.name,
            kind_override=kind,
        )
        self.store.upsert_artifact(summary, path)
        return summary

    def _summary(
        self,
        *,
        job_id: str,
        path: Path,
        relative: str,
        kind_override: ArtifactKind | None = None,
    ) -> ArtifactSummary:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        kind = kind_override or self._classify(path, relative)
        size = path.stat().st_size
        sha = _sha256_file(path)
        content_available = media_type.startswith("text/") or media_type in _TEXT_MEDIA_TYPES or path.suffix.lower() in _TEXT_SUFFIXES
        stable = hashlib.sha256(f"{job_id}\0{relative}".encode("utf-8")).hexdigest()[:20]
        return ArtifactSummary(
            artifact_id=f"artifact-{stable}",
            job_id=job_id,
            kind=kind,
            name=path.name,
            media_type=media_type,
            size_bytes=size,
            created_at=utc_now(),
            relative_path=relative,
            content_available=content_available,
            downloadable=True,
            sha256=sha,
        )

    def _classify(self, path: Path, relative: str) -> ArtifactKind:
        lower = relative.casefold()
        name = path.name.casefold()
        if name in {"knowledge-profile.json", "knowledge_profile.json"}:
            return ArtifactKind.KNOWLEDGE_PROFILE
        if name == "external-physical-model.json":
            return ArtifactKind.TYPED_INPUT_DESCRIPTOR
        if "knowledge-input-inventory" in lower or "knowledge_input_inventory" in lower:
            return ArtifactKind.INPUT_INVENTORY
        if "knowledge-execution-plan" in lower or "knowledge_execution_plan" in lower:
            return ArtifactKind.EXECUTION_PLAN
        if "knowledge-execution-result" in lower or "knowledge_execution_result" in lower:
            return ArtifactKind.EXECUTION_RESULT
        if path.suffix.lower() == ".duckdb" and ("materialization" in lower or "knowledge-execution" in lower):
            return ArtifactKind.KNOWLEDGE_ARTIFACT
        if path.suffix.lower() == ".md" and "report" in lower:
            return ArtifactKind.REPORT_MARKDOWN
        if "dataset" in lower and path.suffix.lower() == ".json":
            return ArtifactKind.REPORT_DATASET
        if path.suffix.lower() == ".log" or lower.endswith("run.log"):
            return ArtifactKind.RUN_LOG
        if "manifest" in lower:
            return ArtifactKind.MANIFEST
        if "evidence" in lower:
            return ArtifactKind.EVIDENCE
        if "diagnostic" in lower:
            return ArtifactKind.DIAGNOSTICS_BUNDLE
        return ArtifactKind.OTHER

    def list_for_job(self, job_id: str) -> ArtifactListResponse:
        return ArtifactListResponse(items=self.store.list_artifacts(job_id))

    def get(self, artifact_id: str) -> tuple[ArtifactSummary, Path]:
        artifact = self.store.get_artifact(artifact_id)
        if artifact is None:
            raise ResourceNotFound("artifact", artifact_id)
        summary, path = artifact
        if not path.is_file():
            raise ResourceNotFound("artifact file", artifact_id)
        return summary, path

    def content(self, artifact_id: str, *, offset: int, limit: int) -> ArtifactContentResponse:
        summary, path = self.get(artifact_id)
        if not summary.content_available:
            raise RuntimeApiError(409, "content_unavailable", f"artifact is not text-readable: {artifact_id}")
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(limit)
        text = chunk.decode("utf-8", errors="replace")
        next_offset = offset + len(chunk) if offset + len(chunk) < size else None
        return ArtifactContentResponse(
            artifact=summary,
            content=text,
            truncated=next_offset is not None,
            next_offset=next_offset,
        )
