from __future__ import annotations

import ssl
from pathlib import Path

import pytest

from aisl_reporting import renderer as renderer_module
from aisl_reporting.renderer import ModelRenderer


class _FakeSSLContext:
    def __init__(self, cafile: str | None = None) -> None:
        self.cafile = cafile
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED
        self.cert_chain: tuple[str, str] | None = None

    def load_cert_chain(self, certfile: str, keyfile: str) -> None:
        self.cert_chain = (certfile, keyfile)


class _FakeRequest:
    url = "https://llm.example/v1/chat/completions"


class _FakeResponse:
    status_code = 200
    request = _FakeRequest()
    http_version = "HTTP/2"
    headers = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


class _FakeClient:
    captured: dict[str, object] = {}

    def __init__(self, **kwargs) -> None:
        type(self).captured = dict(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, *, json):
        type(self).captured["url"] = url
        type(self).captured["json"] = json
        return _FakeResponse()


def test_model_renderer_passes_mtls_insecure_and_http2(monkeypatch, tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"; cert.write_text("cert", encoding="utf-8")
    key = tmp_path / "key.pem"; key.write_text("key", encoding="utf-8")
    contexts: list[_FakeSSLContext] = []

    def _context(*, cafile=None):
        value = _FakeSSLContext(cafile)
        contexts.append(value)
        return value

    monkeypatch.setattr(renderer_module.ssl, "create_default_context", _context)
    monkeypatch.setattr(renderer_module.httpx, "Client", _FakeClient)

    renderer = ModelRenderer(
        endpoint="https://llm.example/v1/chat/completions",
        model="test-model",
        cert_file=cert,
        key_file=key,
        verify_tls=False,
        http2=True,
    )
    assert renderer.render(prompt="prompt", dataset={"x": 1}) == "ok\n"

    context = contexts[-1]
    assert context.cert_chain == (str(cert), str(key))
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE
    assert _FakeClient.captured["verify"] is context
    assert _FakeClient.captured["http2"] is True
    assert _FakeClient.captured["follow_redirects"] is True
    assert _FakeClient.captured["headers"] == {"Content-Type": "application/json", "Accept": "application/json"}
    assert _FakeClient.captured["url"] == "https://llm.example/v1/chat/completions"


def test_model_renderer_uses_ca_and_verification_by_default(monkeypatch, tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"; ca.write_text("ca", encoding="utf-8")
    contexts: list[_FakeSSLContext] = []

    def _context(*, cafile=None):
        value = _FakeSSLContext(cafile)
        contexts.append(value)
        return value

    monkeypatch.setattr(renderer_module.ssl, "create_default_context", _context)
    monkeypatch.setattr(renderer_module.httpx, "Client", _FakeClient)
    monkeypatch.delenv("LLM_TLS_VERIFY", raising=False)
    monkeypatch.delenv("LLM_HTTP2", raising=False)

    renderer = ModelRenderer(endpoint="https://llm.example", model="test", ca_file=ca)
    assert renderer.render(prompt="prompt", dataset={}) == "ok\n"
    context = contexts[-1]
    assert context.cafile == str(ca)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert _FakeClient.captured["http2"] is False


def test_model_renderer_rejects_partial_mtls(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"; cert.write_text("cert", encoding="utf-8")
    renderer = ModelRenderer(endpoint="https://llm.example", model="test", cert_file=cert)
    with pytest.raises(RuntimeError, match="Both LLM_CERT_FILE/--cert and LLM_KEY_FILE/--key"):
        renderer.render(prompt="prompt", dataset={})


def test_model_renderer_rejects_ca_with_insecure(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"; ca.write_text("ca", encoding="utf-8")
    renderer = ModelRenderer(endpoint="https://llm.example", model="test", ca_file=ca, verify_tls=False)
    with pytest.raises(RuntimeError, match="cannot be combined"):
        renderer.render(prompt="prompt", dataset={})


def test_model_renderer_reads_tls_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TLS_VERIFY", "false")
    monkeypatch.setenv("LLM_HTTP2", "true")
    value = ModelRenderer(endpoint="https://llm.example", model="test")
    assert "tls_verify=off" in value.description
    assert "http2=on" in value.description


def test_model_renderer_error_includes_transport_diagnostics(monkeypatch) -> None:
    class ErrorResponse:
        status_code = 404
        request = _FakeRequest()
        http_version = "HTTP/2"
        headers = {"x-request-id": "req-123"}
        text = '{"message":"route not found"}'

    class ErrorClient(_FakeClient):
        def post(self, url: str, *, json):
            type(self).captured["url"] = url
            type(self).captured["json"] = json
            return ErrorResponse()

    monkeypatch.setattr(renderer_module.httpx, "Client", ErrorClient)
    renderer = ModelRenderer(endpoint="https://llm.example/v1/chat/completions", model="test")
    with pytest.raises(RuntimeError) as caught:
        renderer.render(prompt="prompt", dataset={"x": 1})
    message = str(caught.value)
    assert "HTTP 404" in message
    assert "url=https://llm.example/v1/chat/completions" in message
    assert "http_version=HTTP/2" in message
    assert "request_bytes=" in message
    assert "x-request-id=req-123" in message
    assert 'body={"message":"route not found"}' in message
