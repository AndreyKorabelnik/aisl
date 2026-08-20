"""Canonical Knowledge API v1 runtime and public contract."""

from .contract import (
    KNOWLEDGE_API_PREFIX,
    KNOWLEDGE_API_SCHEMA_VERSION,
    create_contract_app,
    router,
)

__all__ = [
    "KNOWLEDGE_API_PREFIX",
    "KNOWLEDGE_API_SCHEMA_VERSION",
    "create_contract_app",
    "router",
]
