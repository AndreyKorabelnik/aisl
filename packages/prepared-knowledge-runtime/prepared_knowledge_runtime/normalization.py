from __future__ import annotations

import hashlib
import re
from typing import Any

_QUOTED_IDENTIFIER_RE = re.compile(r'^[`"\[]?(.*?)[`"\]]?$')
_SQL_ALIAS_RE = re.compile(r"\s+(?:as\s+)?[a-zA-Z_][\w$]*\s*$", re.IGNORECASE)


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join("" if value is None else str(value) for value in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def normalize_db_identifier(value: Any) -> str:
    raw = str(value or "").strip().rstrip(";,)" )
    if not raw:
        return ""
    raw = _SQL_ALIAS_RE.sub("", raw)
    parts: list[str] = []
    for part in raw.split("."):
        part = part.strip()
        match = _QUOTED_IDENTIFIER_RE.match(part)
        cleaned = (match.group(1) if match else part).strip().lower()
        if cleaned:
            parts.append(cleaned)
    return ".".join(parts)


def normalize_field_correspondence_path(value: Any) -> str:
    """Normalize technical field names for correspondence observations only.

    The result never represents semantic equivalence, a wire binding or a causal
    field-flow relation.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts: list[str] = []
    for part in raw.split("."):
        canonical = re.sub(r"[^0-9a-z]+", "", part.casefold())
        if canonical:
            parts.append(canonical)
    return ".".join(parts)
