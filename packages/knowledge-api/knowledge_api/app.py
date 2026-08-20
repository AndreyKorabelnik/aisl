from __future__ import annotations

from fastapi import FastAPI

from .contract_v1.contract import create_contract_app
from .contract_v1.runtime import KnowledgeApiSettings
from .contract_v1.service import KnowledgeDomainService


def create_app(
    *,
    settings: KnowledgeApiSettings | None = None,
    service: KnowledgeDomainService | None = None,
) -> FastAPI:
    """Create the only supported Knowledge API application."""

    return create_contract_app(settings=settings, service=service)


app = create_app()
