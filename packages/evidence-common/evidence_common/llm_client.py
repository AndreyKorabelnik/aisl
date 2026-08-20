from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value) if value else None


def resolve_endpoint(endpoint: str | None) -> str:
    value = endpoint or os.getenv("LLM_BASE_URL")
    if not value:
        raise ValueError("LLM endpoint is not set. Use --endpoint or LLM_BASE_URL.")
    value = value.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def resolve_tls_files(
    cert_file: Path | None,
    key_file: Path | None,
    ca_file: Path | None,
) -> tuple[Path | None, Path | None, Path | None]:
    cert = cert_file or _env_path("LLM_CERT_FILE")
    key = key_file or _env_path("LLM_KEY_FILE")
    ca = ca_file or _env_path("LLM_CA_FILE")
    return cert, key, ca


def extract_message_content(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        return ""
    choices = response_json.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


def finish_reason(api_response: dict[str, Any]) -> str | None:
    data = api_response.get("json")
    if not isinstance(data, dict):
        return None
    try:
        value = data["choices"][0].get("finish_reason")
        return str(value) if value is not None else None
    except Exception:
        return None


def response_http_meta(api_response: dict[str, Any]) -> dict[str, Any]:
    data = api_response.get("json")
    usage = data.get("usage") if isinstance(data, dict) else None
    return {
        "ok": api_response.get("ok"),
        "status_code": api_response.get("status_code"),
        "headers": api_response.get("headers") or {},
        "duration_ms": api_response.get("duration_ms"),
        "finish_reason": finish_reason(api_response),
        "usage": usage,
        "error": api_response.get("error"),
    }


def response_raw_payload(api_response: dict[str, Any], content: str) -> dict[str, Any]:
    return {
        "response_json": api_response.get("json") if isinstance(api_response, dict) else None,
        "content": content,
    }


def call_chat_endpoint(
    *,
    endpoint: str | None,
    model: str,
    messages: list[dict[str, str]],
    timeout_sec: int,
    cert_file: Path | None = None,
    key_file: Path | None = None,
    ca_file: Path | None = None,
) -> tuple[dict[str, Any], str]:
    started = time.perf_counter()
    try:
        final_endpoint = resolve_endpoint(endpoint)
    except Exception as exc:
        return {"ok": False, "status_code": None, "error": str(exc), "duration_ms": 0}, ""

    cert_path, key_path, ca_path = resolve_tls_files(cert_file, key_file, ca_file)
    cert = None
    if cert_path and key_path:
        cert = (str(cert_path), str(key_path))
    elif cert_path or key_path:
        return {
            "ok": False,
            "status_code": None,
            "error": "Both --cert and --key are required for mTLS",
            "duration_ms": 0,
        }, ""

    verify: bool | str = str(ca_path) if ca_path else True
    payload = {"model": model, "messages": messages}
    try:
        response = requests.post(final_endpoint, json=payload, cert=cert, verify=verify, timeout=timeout_sec)
        duration_ms = int((time.perf_counter() - started) * 1000)
        body = response.text
        try:
            parsed = response.json()
        except Exception:
            parsed = None
        content = extract_message_content(parsed)
        return {
            "ok": 200 <= response.status_code < 300,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
            "json": parsed,
            "duration_ms": duration_ms,
        }, content
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "error": str(exc),
            "body": "",
            "json": None,
            "duration_ms": duration_ms,
        }, ""
