from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

import httpx


class ChatProvider(Protocol):
    def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...


def _chat_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("base_url must not be empty")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


@dataclass(slots=True)
class OpenAICompatibleProvider:
    """Thin provider adapter. Tool choice and final reasoning stay in the external LLM."""

    base_url: str
    model: str
    api_key: str | None = None
    timeout_sec: float = 300.0
    verify: bool | str | ssl.SSLContext = True
    cert: str | tuple[str, str] | None = None
    extra_headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        self.model = str(self.model or "").strip()
        if not self.model:
            raise ValueError("model must not be empty")
        headers = {"content-type": "application/json", **dict(self.extra_headers or {})}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        self._client = httpx.Client(
            timeout=float(self.timeout_sec),
            verify=self.verify,
            cert=self.cert,
            headers=headers,
        )
        self._url = _chat_url(self.base_url)

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *[dict(v) for v in messages]],
            "tools": [dict(v) for v in tools],
            "tool_choice": "auto",
        }
        response = self._client.post(self._url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {response.status_code}: {response.text[:4000]}")
        body = response.json()
        choices = body.get("choices") if isinstance(body, Mapping) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI-compatible response has no choices")
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, Mapping) else None
        if not isinstance(message, Mapping):
            raise RuntimeError("OpenAI-compatible response has no assistant message")
        return {
            "message": dict(message),
            "finish_reason": choice.get("finish_reason"),
            "provider_response_id": body.get("id") if isinstance(body, Mapping) else None,
        }


class ScriptedProvider:
    """Deterministic test provider. It proves the tool loop, not LLM behavioral quality."""

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        self._responses = [dict(v) for v in responses]
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system_prompt: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        self.calls.append({
            "system_prompt": system_prompt,
            "messages": [dict(v) for v in messages],
            "tools": [dict(v) for v in tools],
        })
        if not self._responses:
            raise RuntimeError("ScriptedProvider has no response left")
        return self._responses.pop(0)


def fixture_provider(*, object_id: str = "t-ind") -> ScriptedProvider:
    """Live-acceptance fixture provider. Never used unless explicitly selected."""
    return ScriptedProvider([
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-search",
                    "type": "function",
                    "function": {
                        "name": "search_declared_data_objects",
                        "arguments": json.dumps({"search": "Individual", "include_fields": False, "offset": 0, "limit": 20}),
                    },
                }],
            },
            "finish_reason": "tool_calls",
        },
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-context",
                    "type": "function",
                    "function": {
                        "name": "get_data_model_object_context",
                        "arguments": json.dumps({"object_id": object_id}),
                    },
                }],
            },
            "finish_reason": "tool_calls",
        },
        {
            "message": {
                "role": "assistant",
                "content": (
                    "The pinned AISL revision reports the Individual relationship storage semantics as ambiguous: "
                    "two candidate mappings are published. A physical JOIN is not confirmed, so no JOIN condition "
                    "should be invented from the declared-model relationship."
                ),
            },
            "finish_reason": "stop",
        },
    ])
