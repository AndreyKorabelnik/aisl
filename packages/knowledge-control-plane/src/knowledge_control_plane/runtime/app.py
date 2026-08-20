from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from knowledge_control_plane import __version__
from knowledge_control_plane.api.generic_v1.contract import GENERIC_API_SCHEMA_VERSION
from knowledge_control_plane.api.generic_v1.models import ApiError

from .context import build_runtime_context
from .errors import RuntimeApiError
from .knowledge_proxy import KnowledgeApiProxySettings, KnowledgeApiReverseProxy
from .observability import (
    configure_runtime_logging,
    get_request_id,
    log_details,
    reset_request_id,
    sanitize_for_log,
    set_request_id,
)
from .routes import router
from .settings import RuntimeSettings

logger = logging.getLogger(__name__)


def _error_response(
    *, status_code: int, code: str, message: str, details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    payload = ApiError(code=code, message=message, details=details or {}, request_id=request_id)
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def create_runtime_app(
    settings: RuntimeSettings | None = None,
) -> FastAPI:
    resolved_settings = settings or RuntimeSettings.from_environment()
    configure_runtime_logging(resolved_settings)
    context = build_runtime_context(resolved_settings)
    knowledge_proxy = KnowledgeApiReverseProxy(
        KnowledgeApiProxySettings(
            base_url=resolved_settings.knowledge_api_base_url,
            timeout_seconds=resolved_settings.knowledge_api_timeout_seconds,
        )
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await context.jobs.start()
        try:
            yield
        finally:
            await context.jobs.stop()
            await knowledge_proxy.close()

    app = FastAPI(
        title="Knowledge Control Plane Generic Orchestration API",
        version=__version__,
        description=(
            "Knowledge base production orchestration for repositories and self-contained AISL publication bundles."
        ),
        lifespan=lifespan,
    )
    app.state.knowledge_control_plane_runtime = context
    app.state.knowledge_api_proxy = knowledge_proxy

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        supplied_request_id = request.headers.get("X-Request-ID", "").strip()
        request_id = (
            supplied_request_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", supplied_request_id)
            else f"request-{uuid.uuid4().hex}"
        )
        token = set_request_id(request_id)
        started = time.monotonic()
        logger.info(
            "request_started method=%s path=%s client=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                int((time.monotonic() - started) * 1000),
            )
            return response
        except Exception:
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%s",
                request.method,
                request.url.path,
                int((time.monotonic() - started) * 1000),
            )
            raise
        finally:
            reset_request_id(token)

    app.include_router(router)

    if resolved_settings.knowledge_api_proxy_enabled:
        proxy_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

        @app.api_route(
            "/api/knowledge/v1",
            methods=proxy_methods,
            include_in_schema=False,
        )
        async def proxy_knowledge_root(request: Request) -> Response:
            return await knowledge_proxy.forward(request)

        @app.api_route(
            "/api/knowledge/v1/{proxy_path:path}",
            methods=proxy_methods,
            include_in_schema=False,
        )
        async def proxy_knowledge_path(request: Request, proxy_path: str) -> Response:
            return await knowledge_proxy.forward(request)

    @app.exception_handler(RuntimeApiError)
    async def runtime_error_handler(_request: Request, exc: RuntimeApiError) -> JSONResponse:
        request_id = get_request_id()
        safe_details = sanitize_for_log(exc.details)
        log = logger.error if exc.status_code >= 500 else logger.warning
        log(
            "runtime_api_error status=%s code=%s message=%s details=%s",
            exc.status_code,
            exc.code,
            exc.message,
            log_details(safe_details if isinstance(safe_details, dict) else {}),
        )
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=safe_details if isinstance(safe_details, dict) else {},
            request_id=request_id,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="request_validation_failed",
            message="request validation failed",
            request_id=get_request_id(),
            details={
                "errors": [
                    {
                        "loc": list(item.get("loc") or []),
                        "msg": str(item.get("msg") or "validation error"),
                        "type": str(item.get("type") or "value_error"),
                    }
                    for item in exc.errors()
                ]
            },
        )


    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "resource_not_found" if exc.status_code == 404 else "http_error"
        return _error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=get_request_id(),
        )


    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled knowledge-control-plane runtime error", exc_info=exc)
        return _error_response(
            status_code=500,
            code="internal_backend_error",
            message="internal backend error",
            request_id=get_request_id(),
        )

    original_openapi = app.openapi

    def custom_openapi() -> dict:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original_openapi()
        schema["x-knowledge-control-plane-schema-version"] = GENERIC_API_SCHEMA_VERSION
        schema["x-canonical-knowledge-owner"] = "knowledge-api"
        schema["x-orchestration-domain-resources"] = [
            "repositories", "productions", "workspaces", "knowledge_products", "knowledge_profiles", "jobs", "artifacts", "diagnostics"
        ]
        schema["x-local-knowledge-routes"] = False
        schema["x-knowledge-api-same-origin-proxy"] = {
            "enabled": resolved_settings.knowledge_api_proxy_enabled,
            "path": "/api/knowledge/v1/**",
            "transforms_responses": False,
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
    return app
