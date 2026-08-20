from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from typing import Any, Mapping, Protocol

import httpx


class Renderer(Protocol):
    @property
    def description(self) -> str: ...

    def render(self, *, prompt: str, dataset: Mapping[str, Any]) -> str: ...


def renderer_messages(prompt: str, dataset: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prompt.strip()},
        {"role": "user", "content": "REPORT_DATASET_JSON\n" + json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)},
    ]


def _endpoint(value: str | None) -> str:
    resolved = str(value or os.getenv("LLM_BASE_URL") or "").strip().rstrip("/")
    if not resolved:
        raise ValueError("LLM endpoint is not set. Use --endpoint or LLM_BASE_URL.")
    if resolved.endswith("/chat/completions"):
        return resolved
    if resolved.endswith("/v1"):
        return resolved + "/chat/completions"
    return resolved + "/v1/chat/completions"


def _path(value: Path | None, env_name: str) -> Path | None:
    return value or (Path(os.environ[env_name]) if os.getenv(env_name) else None)


def _env_flag(env_name: str, default: bool) -> bool:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{env_name} must be one of: 1/0, true/false, yes/no, on/off")


def _extract_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str))
    return ""


class ModelRenderer:
    def __init__(
        self,
        *,
        endpoint: str | None,
        model: str,
        timeout_sec: int = 600,
        cert_file: Path | None = None,
        key_file: Path | None = None,
        ca_file: Path | None = None,
        verify_tls: bool | None = None,
        http2: bool | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_sec = timeout_sec
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        self.verify_tls = verify_tls
        self.http2 = http2

    @property
    def description(self) -> str:
        endpoint = self.endpoint or "configured/default endpoint"
        verify_tls = self.verify_tls if self.verify_tls is not None else _env_flag("LLM_TLS_VERIFY", True)
        http2 = self.http2 if self.http2 is not None else _env_flag("LLM_HTTP2", False)
        mtls = bool(_path(self.cert_file, "LLM_CERT_FILE") or _path(self.key_file, "LLM_KEY_FILE"))
        return (
            f"LLM model={self.model}, endpoint={endpoint}, timeout={self.timeout_sec}s, "
            f"mTLS={'on' if mtls else 'off'}, tls_verify={'on' if verify_tls else 'off'}, http2={'on' if http2 else 'off'}"
        )

    @property
    def supports_correction(self) -> bool:
        return True

    def render(self, *, prompt: str, dataset: Mapping[str, Any]) -> str:
        cert_file = _path(self.cert_file, "LLM_CERT_FILE")
        key_file = _path(self.key_file, "LLM_KEY_FILE")
        ca_file = _path(self.ca_file, "LLM_CA_FILE")
        if bool(cert_file) ^ bool(key_file):
            raise RuntimeError("Both LLM_CERT_FILE/--cert and LLM_KEY_FILE/--key are required for mTLS")
        verify_tls = self.verify_tls if self.verify_tls is not None else _env_flag("LLM_TLS_VERIFY", True)
        http2 = self.http2 if self.http2 is not None else _env_flag("LLM_HTTP2", False)
        if ca_file and not verify_tls:
            raise RuntimeError("LLM CA file cannot be combined with disabled TLS verification")
        ssl_context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        if not verify_tls:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        if cert_file and key_file:
            ssl_context.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
        url = _endpoint(self.endpoint)
        request_payload = {"model": self.model, "messages": renderer_messages(prompt, dataset)}
        request_bytes = len(json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        with httpx.Client(
            timeout=self.timeout_sec,
            verify=ssl_context,
            http2=http2,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = client.post(url, json=request_payload)
        if response.status_code < 200 or response.status_code >= 300:
            request_url = str(getattr(getattr(response, "request", None), "url", None) or url)
            http_version = str(getattr(response, "http_version", "") or "unknown")
            request_id = str(getattr(response, "headers", {}).get("x-request-id") or "")
            try:
                response_text = str(response.text or "").strip().replace("\n", " ")[:4000]
            except Exception:
                response_text = ""
            details = [
                f"HTTP {response.status_code}",
                f"url={request_url}",
                f"http_version={http_version}",
                f"request_bytes={request_bytes}",
            ]
            if request_id:
                details.append(f"x-request-id={request_id}")
            if response_text:
                details.append(f"body={response_text}")
            raise RuntimeError("LLM rendering failed: " + "; ".join(details))
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("LLM rendering failed: response is not JSON") from exc
        content = _extract_content(payload).strip()
        if not content:
            raise RuntimeError("LLM rendering failed: empty assistant content")
        return content + "\n"


class FileRenderer:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def description(self) -> str:
        return f"response file={self.path}"

    @property
    def supports_correction(self) -> bool:
        return False

    def render(self, *, prompt: str, dataset: Mapping[str, Any]) -> str:
        value = self.path.read_text(encoding="utf-8")
        if not value.strip():
            raise ValueError("rendered report file is empty")
        return value.rstrip() + "\n"
