from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KnowledgeArtifactSource:
    """Resolved typed knowledge artifact used by an internal query adapter."""

    system_id: str
    database_path: Path
    manifest_path: Path | None = None
