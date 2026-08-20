from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from knowledge_api.artifact_locator import AISL_SHA256_URI_SCHEME, artifact_store_blob_path, parse_aisl_sha256_uri

from .models import PublishedArtifact


class KnowledgeApiRuntimeError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class KnowledgeApiSettings:
    database_path: Path
    allowed_roots: tuple[Path, ...]
    artifact_store_path: Path | None = None

    def __post_init__(self) -> None:
        database = self.database_path.expanduser().resolve()
        object.__setattr__(self, "database_path", database)
        object.__setattr__(self, "allowed_roots", tuple(root.expanduser().resolve() for root in self.allowed_roots))
        store = self.artifact_store_path
        if store is None:
            store = database.parent / "artifact-store"
        object.__setattr__(self, "artifact_store_path", store.expanduser().resolve())

    @classmethod
    def from_environment(cls) -> "KnowledgeApiSettings":
        database = Path(
            os.environ.get("KNOWLEDGE_API_DATABASE", "outputs/knowledge-api/knowledge-api.sqlite3")
        ).expanduser().resolve()
        configured = os.environ.get("KNOWLEDGE_API_ALLOWED_ROOTS", "outputs")
        roots = tuple(
            Path(value.strip()).expanduser().resolve()
            for value in configured.split(os.pathsep)
            if value.strip()
        )
        artifact_store = Path(
            os.environ.get("KNOWLEDGE_API_ARTIFACT_STORE", str(database.parent / "artifact-store"))
        ).expanduser().resolve()
        return cls(
            database_path=database,
            allowed_roots=roots or (Path("outputs").resolve(),),
            artifact_store_path=artifact_store,
        )


class ArtifactValidator:
    def __init__(self, settings: KnowledgeApiSettings) -> None:
        self.settings = settings

    def validate(self, artifact: PublishedArtifact) -> Path:
        parsed = urlparse(artifact.uri)
        if parsed.scheme == AISL_SHA256_URI_SCHEME:
            try:
                locator_digest = parse_aisl_sha256_uri(artifact.uri)
            except ValueError as exc:
                raise KnowledgeApiRuntimeError(400, "invalid_aisl_artifact_uri", str(exc), details={"uri": artifact.uri}) from exc
            assert locator_digest is not None
            if locator_digest != artifact.sha256:
                raise KnowledgeApiRuntimeError(
                    409,
                    "artifact_locator_digest_mismatch",
                    "AISL content locator does not match published artifact content identity",
                    details={"locator_sha256": locator_digest, "artifact_sha256": artifact.sha256},
                )
        path = self.resolve_file_uri(artifact.uri)
        if not self._is_allowed(path):
            raise KnowledgeApiRuntimeError(
                400,
                "artifact_path_not_allowed",
                "published artifact is outside configured allowed roots",
                details={"uri": artifact.uri},
            )
        if not path.is_file():
            raise KnowledgeApiRuntimeError(
                503,
                "artifact_unavailable",
                "published artifact file is unavailable",
                details={"uri": artifact.uri},
            )
        size = path.stat().st_size
        if artifact.byte_size is not None and size != artifact.byte_size:
            raise KnowledgeApiRuntimeError(
                409,
                "artifact_size_mismatch",
                "published artifact size does not match the supplied metadata",
                details={"expected": artifact.byte_size, "actual": size},
            )
        actual = sha256_file(path)
        if actual != artifact.sha256:
            raise KnowledgeApiRuntimeError(
                409,
                "artifact_digest_mismatch",
                "published artifact SHA-256 does not match",
                details={"expected": artifact.sha256, "actual": actual},
            )
        return path


    def validate_path(self, path: str | Path, *, directory: bool = False) -> Path:
        resolved = Path(path).expanduser().resolve()
        if not self._is_allowed(resolved):
            raise KnowledgeApiRuntimeError(
                400,
                "artifact_path_not_allowed",
                "published artifact is outside configured allowed roots",
                details={"path": str(resolved)},
            )
        available = resolved.is_dir() if directory else resolved.is_file()
        if not available:
            kind = "directory" if directory else "file"
            raise KnowledgeApiRuntimeError(
                503,
                "artifact_unavailable",
                f"published artifact {kind} is unavailable",
                details={"path": str(resolved)},
            )
        return resolved

    def validate_dict(self, artifact: dict[str, Any]) -> Path:
        payload = dict(artifact)
        payload.pop("role", None)
        return self.validate(PublishedArtifact.model_validate(payload))


    def resolve_file_uri(self, uri: str) -> Path:
        """Resolve producer-local file URIs or AISL content locators.

        Published catalog state stores ``aisl+sha256://<digest>``. The current
        Artifact Store root is deployment configuration, so moving immutable
        bytes does not rewrite KnowledgeRevision or KnowledgeProduct identity.
        """
        parsed = urlparse(uri)
        if parsed.scheme == "file" and parsed.netloc in {"", "localhost"}:
            return Path(unquote(parsed.path)).expanduser().resolve()
        if parsed.scheme == AISL_SHA256_URI_SCHEME:
            try:
                digest = parse_aisl_sha256_uri(uri)
            except ValueError as exc:
                raise KnowledgeApiRuntimeError(400, "invalid_aisl_artifact_uri", str(exc), details={"uri": uri}) from exc
            assert digest is not None
            store = self.settings.artifact_store_path
            if store is None:
                raise KnowledgeApiRuntimeError(500, "artifact_store_unconfigured", "AISL Artifact Store is not configured")
            return artifact_store_blob_path(store, digest)
        raise KnowledgeApiRuntimeError(
            400,
            "unsupported_artifact_uri",
            "artifact URI must use file:// for producer input or aisl+sha256:// for published AISL bytes",
            details={"uri": uri},
        )

    def _is_allowed(self, path: Path) -> bool:
        roots = self.settings.allowed_roots
        artifact_store = self.settings.artifact_store_path
        if artifact_store is not None:
            roots = roots + (artifact_store,)
        return any(path == root or root in path.parents for root in roots)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
