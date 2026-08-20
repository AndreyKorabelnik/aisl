"""Canonical public contract constants for Knowledge Control Plane knowledge execution API."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

GENERIC_API_PREFIX = "/api/v1"
GENERIC_API_SCHEMA_VERSION = "generic_api/v1"
router = APIRouter(prefix=GENERIC_API_PREFIX)

ERROR_RESPONSES = {
    400: {"description": "Invalid request"},
    404: {"description": "Resource not found"},
    409: {"description": "Resource state conflict"},
    422: {"description": "Request validation failed"},
    500: {"description": "Internal backend error"},
    502: {"description": "Invalid upstream response"},
    503: {"description": "Required capability unavailable"},
    504: {"description": "Upstream timeout"},
}


def create_generic_contract_app() -> FastAPI:
    """Create a deterministic design-time app from the executable public router."""
    from knowledge_control_plane.runtime.routes import router

    app = FastAPI(
        title="Knowledge Control Plane Knowledge Execution API",
        version=GENERIC_API_SCHEMA_VERSION,
        description=(
            "Knowledge Profile execution, self-contained AISL publication bundle creation, "
            "and typed Producer artifacts."
        ),
    )
    app.include_router(router)
    original_openapi = app.openapi

    def customized_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        schema["x-knowledge-control-plane-schema-version"] = GENERIC_API_SCHEMA_VERSION
        schema["x-canonical-knowledge-owner"] = "knowledge-api"
        schema["x-orchestration-domain-resources"] = [
            "repositories", "productions", "workspaces", "knowledge_products", "knowledge_profiles", "scenarios", "jobs", "artifacts", "diagnostics"
        ]
        app.openapi_schema = schema
        return schema

    app.openapi = customized_openapi
    return app


create_contract_app = create_generic_contract_app
