from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .errors import RuntimeApiError


@dataclass(frozen=True, slots=True)
class KnowledgeApiClientSettings:
    base_url: str
    timeout_seconds: float = 30.0


class KnowledgeApiHttpClient:
    """Read-only client for published AISL inputs and health checks.

    Producer does not publish revisions. Publication is owned by aisl-server.
    """

    def __init__(self, settings: KnowledgeApiClientSettings) -> None:
        self.settings = settings
        self.base_url = self._canonical_api_base_url(settings.base_url)
        self._health_cache: tuple[float, dict[str, Any]] | None = None

    @staticmethod
    def _canonical_api_base_url(value: str) -> str:
        raw = value.strip().rstrip("/")
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"invalid Knowledge API base URL: {value!r}")
        path = parsed.path.rstrip("/")
        suffix = "/api/knowledge/v1"
        if not path:
            path = suffix
        elif not path.endswith(suffix):
            path = f"{path}{suffix}"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def health(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._health_cache and now - self._health_cache[0] < 5:
            return dict(self._health_cache[1])
        payload = self._request("GET", "/health", timeout_seconds=min(2, self.settings.timeout_seconds))
        self._health_cache = (now, dict(payload))
        return payload

    def get_revision(self, system_id: str, revision_id: str) -> dict[str, Any]:
        return self._request("GET", f"/systems/{quote(system_id, safe='')}/revisions/{quote(revision_id, safe='')}")

    def get_capabilities(self, system_id: str, revision_id: str) -> dict[str, Any]:
        return self._request("GET", f"/systems/{quote(system_id, safe='')}/capabilities?revision_id={quote(revision_id, safe='')}")

    def _request(self, method: str, path: str, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", method=method, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout_seconds or self.settings.timeout_seconds) as response:
                content = response.read()
        except HTTPError as exc:
            content = exc.read()
            code = "knowledge_api_http_error"
            message = f"Knowledge API returned HTTP {exc.code}"
            details: dict[str, Any] = {"status_code": exc.code, "path": path}
            try:
                parsed = json.loads(content.decode("utf-8"))
                code = str(parsed.get("code") or code)
                message = str(parsed.get("message") or message)
                if isinstance(parsed.get("details"), dict):
                    details.update(parsed["details"])
            except Exception:
                pass
            raise RuntimeApiError(exc.code, code, message, details=details) from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            timed_out = isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()
            raise RuntimeApiError(
                504 if timed_out else 503,
                "knowledge_api_timeout" if timed_out else "knowledge_api_unavailable",
                "Knowledge API request timed out" if timed_out else "Knowledge API is unavailable",
                details={"base_url": self.base_url, "path": path, "reason": str(reason)},
            ) from exc
        if not content:
            return {}
        try:
            decoded = json.loads(content.decode("utf-8"))
        except Exception as exc:
            raise RuntimeApiError(502, "knowledge_api_invalid_response", "Knowledge API returned a non-JSON response", details={"path": path}) from exc
        if not isinstance(decoded, dict):
            raise RuntimeApiError(502, "knowledge_api_invalid_response", "Knowledge API returned an unexpected response shape", details={"path": path})
        return decoded
