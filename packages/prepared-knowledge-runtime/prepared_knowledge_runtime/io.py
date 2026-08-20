from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import KnowledgeLayerManifest

_MISSING = object()


def read_json(path: str | Path, default: Any = None) -> Any:
    candidate = Path(path)
    if not candidate.exists():
        return default
    try:
        return json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return default


def write_json(path: str | Path, value: Any) -> None:
    candidate = Path(path)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _read_object(path: Path) -> dict[str, Any]:
    payload = read_json(path, _MISSING)
    if payload is _MISSING:
        raise FileNotFoundError(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_manifest(path: Path) -> KnowledgeLayerManifest:
    return KnowledgeLayerManifest.from_dict(_read_object(path))


def write_manifest(path: Path, manifest: KnowledgeLayerManifest) -> None:
    write_json(path, manifest.to_dict())
