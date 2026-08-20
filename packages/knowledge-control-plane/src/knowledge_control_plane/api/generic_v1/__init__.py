"""Canonical unified API v1 contract."""

from .contract import (
    GENERIC_API_PREFIX,
    GENERIC_API_SCHEMA_VERSION,
    create_contract_app,
    router,
)

__all__ = [
    "GENERIC_API_PREFIX",
    "GENERIC_API_SCHEMA_VERSION",
    "create_contract_app",
    "router",
]
