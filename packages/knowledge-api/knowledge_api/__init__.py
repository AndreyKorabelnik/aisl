from __future__ import annotations

from .app import create_app
from .contract_v1 import KNOWLEDGE_API_PREFIX, KNOWLEDGE_API_SCHEMA_VERSION, create_contract_app
from .version import API_SCHEMA_VERSION, __version__

__all__ = [
    "API_SCHEMA_VERSION",
    "KNOWLEDGE_API_PREFIX",
    "KNOWLEDGE_API_SCHEMA_VERSION",
    "create_app",
    "create_contract_app",
    "__version__",
]
