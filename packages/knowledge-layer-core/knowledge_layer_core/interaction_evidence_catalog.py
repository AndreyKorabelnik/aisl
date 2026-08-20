from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def safe_envelope_relative_path(envelope_path: Path, relative: str) -> Path:
    candidate = Path(str(relative or ""))
    if not relative or candidate.is_absolute():
        raise ValueError("interaction boundary payload path must be envelope-relative")
    root = envelope_path.parent.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("interaction boundary payload path escapes envelope root") from exc
    return resolved


def interaction_boundary_records(envelope_path: Path, envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    payload = envelope.get("payload") or {}
    descriptor = payload.get("boundary_catalog") or {}
    if not isinstance(descriptor, Mapping):
        return []
    relative_path = str(descriptor.get("relative_path") or "")
    if not relative_path:
        # Tests/reference fixtures can legitimately provide only coverage without the typed sidecar.
        return []
    path = safe_envelope_relative_path(envelope_path, relative_path)
    raw = read_json_object(path)
    section = str(descriptor.get("section") or "boundaries")
    return [dict(item) for item in (raw.get(section) or []) if isinstance(item, Mapping)]
