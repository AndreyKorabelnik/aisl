from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

AISL_SHA256_URI_SCHEME = "aisl+sha256"
_HEX = frozenset("0123456789abcdef")


def logical_artifact_uri(sha256: str) -> str:
    return f"{AISL_SHA256_URI_SCHEME}://{sha256}"


def parse_aisl_sha256_uri(uri: str) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme != AISL_SHA256_URI_SCHEME:
        return None
    digest = (parsed.netloc or parsed.path.lstrip("/")).strip()
    if len(digest) != 64 or any(ch not in _HEX for ch in digest):
        raise ValueError("AISL artifact URI must contain one lowercase SHA-256 digest")
    return digest


def artifact_store_blob_path(root: str | Path, sha256: str) -> Path:
    base = Path(root).expanduser().resolve()
    return base / "sha256" / sha256[:2] / sha256 / "blob"
