from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi import Request
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

from .errors import RuntimeApiError


_HOP_BY_HOP_HEADERS = {
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailer",
    b"transfer-encoding",
    b"upgrade",
}


@dataclass(frozen=True)
class KnowledgeApiProxySettings:
    base_url: str
    timeout_seconds: float


class KnowledgeApiReverseProxy:
    """Transparent transport proxy for the canonical knowledge-api.

    This component deliberately owns no knowledge-domain models and performs no
    response transformation. It forwards HTTP requests and streams the upstream
    response back to the browser while preserving status, body and end-to-end
    headers.
    """

    def __init__(self, settings: KnowledgeApiProxySettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self._timeout = httpx.Timeout(settings.timeout_seconds)
        self._client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
            )
        return self._client

    async def forward(self, request: Request) -> Response:
        raw_path = request.scope.get("raw_path") or request.url.path.encode("ascii")
        prefix = b"/api/knowledge/v1"
        suffix = raw_path[len(prefix) :] if raw_path.startswith(prefix) else b""
        target = httpx.URL(self.base_url + suffix.decode("ascii"))
        if request.url.query:
            target = target.copy_with(query=request.url.query.encode("utf-8"))

        headers = self._forward_request_headers(request)
        body = await request.body()
        client = self._http_client()
        upstream_request = client.build_request(
            request.method,
            target,
            headers=headers,
            content=body,
        )
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.TimeoutException as exc:
            raise RuntimeApiError(
                504,
                "knowledge_api_proxy_timeout",
                "knowledge-api proxy request timed out",
                details={"upstream": self.base_url},
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeApiError(
                502,
                "knowledge_api_proxy_unavailable",
                "knowledge-api is unavailable",
                details={"upstream": self.base_url},
            ) from exc

        response = StreamingResponse(
            self._stream_body(upstream),
            status_code=upstream.status_code,
            background=BackgroundTask(upstream.aclose),
        )
        response.raw_headers = self._forward_response_headers(upstream)
        return response

    @staticmethod
    def _connection_tokens(raw_headers: list[tuple[bytes, bytes]]) -> set[bytes]:
        tokens: set[bytes] = set()
        for name, value in raw_headers:
            if name.lower() == b"connection":
                tokens.update(part.strip().lower() for part in value.split(b",") if part.strip())
        return tokens

    @classmethod
    def _forward_request_headers(cls, request: Request) -> list[tuple[bytes, bytes]]:
        raw_headers = list(request.headers.raw)
        blocked = _HOP_BY_HOP_HEADERS | cls._connection_tokens(raw_headers) | {
            b"host",
            b"content-length",
            b"x-forwarded-for",
            b"x-forwarded-host",
            b"x-forwarded-proto",
        }
        result = [(name, value) for name, value in raw_headers if name.lower() not in blocked]
        result.extend(
            [
                (b"x-forwarded-host", request.url.netloc.encode("latin-1")),
                (b"x-forwarded-proto", request.url.scheme.encode("ascii")),
            ]
        )
        client = request.client
        if client is not None:
            result.append((b"x-forwarded-for", client.host.encode("latin-1")))
        return result

    @classmethod
    def _forward_response_headers(cls, response: httpx.Response) -> list[tuple[bytes, bytes]]:
        raw_headers = list(response.headers.raw)
        blocked = _HOP_BY_HOP_HEADERS | cls._connection_tokens(raw_headers)
        return [(name, value) for name, value in raw_headers if name.lower() not in blocked]

    @staticmethod
    async def _stream_body(response: httpx.Response) -> AsyncIterator[bytes]:
        async for chunk in response.aiter_raw():
            yield chunk
