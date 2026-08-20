from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from knowledge_control_plane.runtime import RuntimeSettings, create_runtime_app


class _ProxyState:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []


def _start_upstream(state: _ProxyState, *, delay_seconds: float = 0.0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _record(self, body: bytes) -> None:
            state.requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "body": body,
                    "authorization": self.headers.get("Authorization"),
                    "content_type": self.headers.get("Content-Type"),
                    "forwarded_host": self.headers.get("X-Forwarded-Host"),
                    "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
                }
            )

        def _write(self, status: int, body: bytes, content_type: str, **headers: str) -> None:
            if delay_seconds:
                time.sleep(delay_seconds)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Upstream", "knowledge-api")
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            self._record(b"")
            if self.path == "/api/knowledge/v1/health?verbose=1&verbose=2":
                self._write(
                    200,
                    b'{"status":"ok","service":"knowledge-api"}',
                    "application/json",
                )
                return
            if self.path == "/api/knowledge/v1/systems/demo/reports/latest/content":
                self._write(
                    200,
                    b"# Published report\n",
                    "text/markdown; charset=utf-8",
                    Content_Disposition='inline; filename="report.md"',
                )
                return
            self._write(
                404,
                b'{"code":"system_not_found","message":"unknown system","details":{}}',
                "application/json",
            )

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self._record(body)
            self._write(201, body, self.headers.get("Content-Type", "application/octet-stream"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _settings(tmp_path: Path, base_url: str, *, timeout: float = 1.0, enabled: bool = True) -> RuntimeSettings:
    profiles = tmp_path / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "knowledge-control-plane.sqlite3",
        jobs_root=tmp_path / "runtime" / "jobs",
        default_analysis_output_root=tmp_path / "outputs" / "analysis",
        event_poll_interval_seconds=0.005,
        knowledge_api_base_url=base_url,
        knowledge_api_timeout_seconds=timeout,
        knowledge_api_proxy_enabled=enabled,
    )


def test_proxy_preserves_json_status_query_headers_and_body(tmp_path: Path) -> None:
    state = _ProxyState()
    server, thread = _start_upstream(state)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/knowledge/v1"
        with TestClient(create_runtime_app(_settings(tmp_path, base_url))) as client:
            response = client.get("/api/knowledge/v1/health?verbose=1&verbose=2")
        assert response.status_code == 200
        assert response.content == b'{"status":"ok","service":"knowledge-api"}'
        assert response.headers["content-type"] == "application/json"
        assert response.headers["x-upstream"] == "knowledge-api"
        assert state.requests[0]["path"] == "/api/knowledge/v1/health?verbose=1&verbose=2"
        assert state.requests[0]["forwarded_proto"] == "http"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_proxy_forwards_post_payload_and_authorization_without_transforming_response(tmp_path: Path) -> None:
    state = _ProxyState()
    server, thread = _start_upstream(state)
    payload = b'{"system_id":"ucp","display_name":"UCP"}'
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/knowledge/v1"
        with TestClient(create_runtime_app(_settings(tmp_path, base_url))) as client:
            response = client.post(
                "/api/knowledge/v1/systems",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer test-token",
                },
            )
        assert response.status_code == 201
        assert response.content == payload
        assert state.requests[0]["body"] == payload
        assert state.requests[0]["authorization"] == "Bearer test-token"
        assert state.requests[0]["content_type"] == "application/json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_proxy_streams_markdown_and_preserves_content_disposition(tmp_path: Path) -> None:
    state = _ProxyState()
    server, thread = _start_upstream(state)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/knowledge/v1"
        with TestClient(create_runtime_app(_settings(tmp_path, base_url))) as client:
            response = client.get("/api/knowledge/v1/systems/demo/reports/latest/content")
        assert response.status_code == 200
        assert response.text == "# Published report\n"
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert response.headers["content-disposition"] == 'inline; filename="report.md"'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_proxy_passes_upstream_error_status_and_payload_unchanged(tmp_path: Path) -> None:
    state = _ProxyState()
    server, thread = _start_upstream(state)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/knowledge/v1"
        with TestClient(create_runtime_app(_settings(tmp_path, base_url))) as client:
            response = client.get("/api/knowledge/v1/systems/missing")
        assert response.status_code == 404
        assert response.content == b'{"code":"system_not_found","message":"unknown system","details":{}}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_proxy_maps_unavailable_upstream_to_gateway_error(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_port
    server.server_close()
    base_url = f"http://127.0.0.1:{port}/api/knowledge/v1"
    with TestClient(create_runtime_app(_settings(tmp_path, base_url))) as client:
        response = client.get("/api/knowledge/v1/health")
    assert response.status_code == 502
    assert response.json()["code"] == "knowledge_api_proxy_unavailable"


def test_proxy_timeout_is_reported_without_faking_upstream_payload(tmp_path: Path) -> None:
    state = _ProxyState()
    server, thread = _start_upstream(state, delay_seconds=0.2)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/api/knowledge/v1"
        with TestClient(create_runtime_app(_settings(tmp_path, base_url, timeout=0.05))) as client:
            response = client.get("/api/knowledge/v1/health?verbose=1&verbose=2")
        assert response.status_code == 504
        assert response.json()["code"] == "knowledge_api_proxy_timeout"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_proxy_can_be_disabled_and_is_not_duplicated_in_orchestration_openapi(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "http://127.0.0.1:1/api/knowledge/v1", enabled=False)
    with TestClient(create_runtime_app(settings)) as client:
        response = client.get("/api/knowledge/v1/health")
        schema = client.get("/openapi.json").json()
    assert response.status_code == 404
    assert not any(path.startswith("/api/knowledge/v1") for path in schema["paths"])
    assert schema["x-knowledge-api-same-origin-proxy"] == {
        "enabled": False,
        "path": "/api/knowledge/v1/**",
        "transforms_responses": False,
    }


def test_proxy_source_has_no_knowledge_domain_models_or_duckdb_access() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "knowledge_control_plane" / "runtime" / "knowledge_proxy.py").read_text(encoding="utf-8")
    assert "knowledge_control_plane.domain.systems" not in text
    assert "knowledge_layer" not in text
    assert "duckdb" not in text.lower()
    assert "model_validate" not in text
