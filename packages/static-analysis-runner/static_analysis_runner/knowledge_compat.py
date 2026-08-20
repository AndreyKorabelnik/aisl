from __future__ import annotations

from importlib import import_module
import re
from types import ModuleType
from typing import Iterable

from .version import (
    KNOWLEDGE_LAYER_CORE_REQUIREMENT,
    MAX_KNOWLEDGE_LAYER_CORE_VERSION_EXCLUSIVE,
    MIN_KNOWLEDGE_LAYER_CORE_VERSION,
)


def _parse_version(value: str) -> tuple[int, int, int]:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", str(value or ""))
    if not match:
        raise RuntimeError(f"cannot parse knowledge-layer-core version: {value!r}")
    return tuple(int(part) for part in match.groups())


def require_knowledge_layer_core(
    *,
    context: str,
    required_symbols: Iterable[str],
) -> tuple[ModuleType, str]:
    """Load a compatible Knowledge Layer producer by version floor and API surface.

    Runner no longer pins one exact producer patch/minor. A newer 0.x producer is
    accepted when it satisfies the supported package range and still exports every
    API symbol required by the requested operation. This keeps failures explicit
    without forcing a runner release for metadata-only Knowledge Layer changes.
    """
    try:
        module = import_module("knowledge_layer_core")
    except ImportError as exc:
        raise RuntimeError(
            f"knowledge-layer-core{KNOWLEDGE_LAYER_CORE_REQUIREMENT} is required for {context}; "
            "install static-analysis-runner[knowledge]"
        ) from exc

    version = str(getattr(module, "__version__", "") or "")
    actual = _parse_version(version)
    if actual < MIN_KNOWLEDGE_LAYER_CORE_VERSION:
        minimum = ".".join(str(part) for part in MIN_KNOWLEDGE_LAYER_CORE_VERSION)
        raise RuntimeError(
            f"knowledge-layer-core is too old for {context}: found {version}, required >= {minimum}"
        )
    if actual >= MAX_KNOWLEDGE_LAYER_CORE_VERSION_EXCLUSIVE:
        maximum = ".".join(
            str(part) for part in MAX_KNOWLEDGE_LAYER_CORE_VERSION_EXCLUSIVE
        )
        raise RuntimeError(
            f"knowledge-layer-core major version is unsupported for {context}: "
            f"found {version}, required < {maximum}"
        )

    missing = sorted(name for name in required_symbols if not hasattr(module, name))
    if missing:
        raise RuntimeError(
            f"knowledge-layer-core {version} is API-incompatible with {context}; "
            f"missing required symbols: {', '.join(missing)}"
        )
    return module, version
