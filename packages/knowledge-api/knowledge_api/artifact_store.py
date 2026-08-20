from __future__ import annotations

import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .artifact_locator import artifact_store_blob_path, logical_artifact_uri
from .contract_v1.models import PublishedArtifact
from .contract_v1.runtime import KnowledgeApiRuntimeError, sha256_file

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class StoredArtifactBlob:
    sha256: str
    path: Path
    byte_size: int
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactStoreInventory:
    blobs: tuple[StoredArtifactBlob, ...]
    staging_files: tuple[Path, ...]
    unmanaged_entries: tuple[Path, ...]



class AislArtifactStore:
    """Filesystem-backed immutable artifact store for published AISL bytes.

    The catalog remains the source of truth for revision/product membership. This
    store owns only durable immutable bytes addressed by their SHA-256 digest.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".staging").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def logical_uri(sha256: str) -> str:
        return logical_artifact_uri(sha256)

    def path_for_digest(self, sha256: str) -> Path:
        return artifact_store_blob_path(self.root, sha256)

    @contextmanager
    def lifecycle_lock(self) -> Iterator[None]:
        """Serialize publication finalization and destructive store maintenance.

        Catalog membership is committed only while this lock is held by the
        publisher. GC takes the same lock before deriving reachability and
        deleting blobs, so a finalized-but-not-yet-catalogued publication blob
        cannot be collected by a concurrent sweep.
        """
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - current runtime is Linux
            raise KnowledgeApiRuntimeError(
                500,
                "artifact_store_lock_unsupported",
                "filesystem Artifact Store lifecycle locking requires POSIX flock support",
            ) from exc
        lock_path = self.root / ".lifecycle.lock"
        with lock_path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def inventory(self) -> ArtifactStoreInventory:
        """Inspect only official CAS blobs and crash-staging files.

        Unknown store entries are reported but never inferred to be deletable.
        """
        blobs: list[StoredArtifactBlob] = []
        unmanaged: list[Path] = []
        sha_root = self.root / "sha256"
        if sha_root.exists():
            for path in sorted(sha_root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.root)
                parts = rel.parts
                if (
                    len(parts) == 4
                    and parts[0] == "sha256"
                    and len(parts[1]) == 2
                    and _SHA256_RE.fullmatch(parts[2])
                    and parts[1] == parts[2][:2]
                    and parts[3] == "blob"
                ):
                    stat = path.stat()
                    blobs.append(StoredArtifactBlob(
                        sha256=parts[2],
                        path=path,
                        byte_size=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    ))
                else:
                    unmanaged.append(path)
        staging_root = self.root / ".staging"
        staging = tuple(sorted(path for path in staging_root.rglob("*") if path.is_file())) if staging_root.exists() else ()
        return ArtifactStoreInventory(tuple(blobs), staging, tuple(unmanaged))

    def delete_blob(self, sha256: str) -> bool:
        path = self.path_for_digest(sha256)
        if not path.is_file():
            return False
        path.unlink()
        for directory in (path.parent, path.parent.parent):
            try:
                directory.rmdir()
            except OSError:
                break
        return True

    def delete_staging_file(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        staging_root = (self.root / ".staging").resolve()
        if staging_root not in resolved.parents:
            raise KnowledgeApiRuntimeError(
                400,
                "artifact_gc_invalid_staging_path",
                "refusing to delete a path outside the AISL Artifact Store staging area",
                details={"path": str(resolved)},
            )
        try:
            resolved.unlink()
        except FileNotFoundError:
            return False
        return True

    def import_artifact(self, artifact: PublishedArtifact, source: str | Path) -> PublishedArtifact:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise KnowledgeApiRuntimeError(
                503,
                "artifact_unavailable",
                "artifact disappeared before AISL import",
                details={"path": str(source_path)},
            )
        source_size = source_path.stat().st_size
        if artifact.byte_size is not None and source_size != artifact.byte_size:
            raise KnowledgeApiRuntimeError(
                409,
                "artifact_size_mismatch",
                "artifact size changed before AISL import",
                details={"expected": artifact.byte_size, "actual": source_size},
            )
        source_digest = sha256_file(source_path)
        if source_digest != artifact.sha256:
            raise KnowledgeApiRuntimeError(
                409,
                "artifact_digest_mismatch",
                "artifact digest changed before AISL import",
                details={"expected": artifact.sha256, "actual": source_digest},
            )

        target = self.path_for_digest(artifact.sha256)
        target_dir = target.parent
        # One physical blob per digest. Original filename/media type remain
        # descriptor metadata and are not part of physical or semantic identity.
        if target.is_file():
            if target.stat().st_size != source_size or sha256_file(target) != artifact.sha256:
                raise KnowledgeApiRuntimeError(
                    500,
                    "aisl_artifact_store_corrupt",
                    "existing AISL artifact-store blob does not match its content identity",
                    details={"sha256": artifact.sha256, "path": str(target)},
                )
            return artifact.model_copy(update={"uri": self.logical_uri(artifact.sha256), "byte_size": source_size})

        target_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = self.root / ".staging"
        fd, staging_name = tempfile.mkstemp(prefix=f"{artifact.sha256}.", suffix=".tmp", dir=staging_dir)
        staging = Path(staging_name)
        try:
            with os.fdopen(fd, "wb") as out, source_path.open("rb") as src:
                shutil.copyfileobj(src, out, length=1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            if staging.stat().st_size != source_size or sha256_file(staging) != artifact.sha256:
                raise KnowledgeApiRuntimeError(
                    409,
                    "aisl_artifact_import_verification_failed",
                    "staged AISL artifact does not match source content identity",
                    details={"sha256": artifact.sha256},
                )
            try:
                os.replace(staging, target)
            except OSError:
                # A concurrent equivalent publication may have finalized the same
                # content-addressed blob. Exact identity is revalidated below.
                if not target.is_file():
                    raise
            if target.stat().st_size != source_size or sha256_file(target) != artifact.sha256:
                raise KnowledgeApiRuntimeError(
                    500,
                    "aisl_artifact_store_corrupt",
                    "finalized AISL artifact-store blob failed verification",
                    details={"sha256": artifact.sha256, "path": str(target)},
                )
            try:
                target.chmod(0o444)
            except OSError:
                pass
        finally:
            try:
                staging.unlink()
            except FileNotFoundError:
                pass

        return artifact.model_copy(update={"uri": self.logical_uri(artifact.sha256), "byte_size": source_size})
