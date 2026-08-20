from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlsplit

from .runtime import AgentRuntime


@dataclass(slots=True)
class AgentHttpService:
    runtime: AgentRuntime
    host: str = "127.0.0.1"
    port: int = 18220

    def serve_forever(self) -> None:
        runtime = self.runtime

        class Handler(BaseHTTPRequestHandler):
            server_version = "aisl-agent-runtime/0.1.0"

            def _json(self, status: int, payload: Mapping[str, Any]) -> None:
                body = (json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("content-length") or 0)
                data = self.rfile.read(length) if length else b"{}"
                value = json.loads(data.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("request body must be a JSON object")
                return value

            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                if path == "/healthz":
                    self._json(200, {"status": "ok", "service": "aisl-agent-runtime"})
                    return
                if path.startswith("/api/agent/v1/sessions/"):
                    session_id = path.rsplit("/", 1)[-1]
                    try:
                        session = runtime.get_session(session_id)
                    except KeyError as exc:
                        self._json(404, {"error": "session_not_found", "detail": str(exc)})
                        return
                    self._json(200, {
                        "schema_version": "aisl_agent_session/v1",
                        "session_id": session.session_id,
                        "scope": {
                            "system_id": session.profile.system_id,
                            "revision_id": session.profile.revision_id,
                            "profile_id": session.profile.profile_id,
                            "integration_profile_fingerprint": session.profile.fingerprint,
                        },
                        "turn_count": session.turn_count,
                    })
                    return
                self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlsplit(self.path).path
                try:
                    payload = self._body()
                    if path == "/api/agent/v1/sessions":
                        session = runtime.create_session(
                            system_id=str(payload.get("system_id") or ""),
                            revision_id=str(payload.get("revision_id") or ""),
                            profile_id=str(payload.get("profile_id") or ""),
                        )
                        self._json(201, {
                            "schema_version": "aisl_agent_session/v1",
                            "session_id": session.session_id,
                            "scope": {
                                "system_id": session.profile.system_id,
                                "revision_id": session.profile.revision_id,
                                "profile_id": session.profile.profile_id,
                                "integration_profile_fingerprint": session.profile.fingerprint,
                            },
                            "turn_count": 0,
                        })
                        return
                    prefix = "/api/agent/v1/sessions/"
                    suffix = "/messages"
                    if path.startswith(prefix) and path.endswith(suffix):
                        session_id = path[len(prefix):-len(suffix)].strip("/")
                        session = runtime.get_session(session_id)
                        self._json(200, session.ask(str(payload.get("question") or "")))
                        return
                    self._json(404, {"error": "not_found"})
                except KeyError as exc:
                    self._json(404, {"error": "session_not_found", "detail": str(exc)})
                except Exception as exc:
                    self._json(400, {"error": type(exc).__name__, "detail": str(exc)})

            def log_message(self, fmt: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer((self.host, int(self.port)), Handler)
        server.serve_forever()
