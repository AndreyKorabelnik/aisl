from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from aisl_sdk import AislClient, ConsumerIntegration

from .providers import ChatProvider



def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_text(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _argument_schema(spec: str) -> dict[str, Any]:
    value = str(spec or "string").strip()
    nullable = value.endswith("|null")
    if nullable:
        value = value[:-5]
    if value == "string":
        schema: dict[str, Any] = {"type": "string"}
    elif value == "integer":
        schema = {"type": "integer"}
    elif value == "boolean":
        schema = {"type": "boolean"}
    elif value == "array[string]":
        schema = {"type": "array", "items": {"type": "string"}}
    else:
        schema = {"type": "string"}
    return {"anyOf": [schema, {"type": "null"}]} if nullable else schema


def _openai_tools(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in profile.get("tools") or ():
        tool = _require_mapping(raw, "tool")
        arguments = _require_mapping(tool.get("arguments") or {}, "tool.arguments")
        properties = {str(k): _argument_schema(str(v)) for k, v in arguments.items()}
        binding = _require_mapping(tool.get("api_binding") or {}, "tool.api_binding")
        bound_args = _require_mapping(binding.get("arguments") or {}, "tool.api_binding.arguments")
        required: list[str] = []
        for arg_name, arg_binding in bound_args.items():
            arg_binding = _require_mapping(arg_binding, "api argument binding")
            if arg_binding.get("location") == "path":
                required.append(str(arg_name))
        params: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            params["required"] = sorted(set(required))
        result.append({
            "type": "function",
            "function": {
                "name": _require_text(tool.get("name"), "tool.name"),
                "description": str(tool.get("description") or ""),
                "parameters": params,
            },
        })
    return result


def _render_system_prompt(profile: Mapping[str, Any]) -> str:
    """Mechanical rendering only; all policy/retrieval semantics come from the Integration Profile."""
    scope = _require_mapping(profile.get("scope"), "scope")
    policy = _require_mapping(profile.get("policy"), "policy")
    retrieval = _require_mapping(profile.get("retrieval_guidance"), "retrieval_guidance")
    compact_tools = []
    for raw in profile.get("tools") or ():
        tool = _require_mapping(raw, "tool")
        compact_tools.append({
            "name": tool.get("name"),
            "description": tool.get("description"),
            "arguments": copy.deepcopy(tool.get("arguments") or {}),
            "required_capabilities": copy.deepcopy(tool.get("required_capabilities") or []),
            "warnings": copy.deepcopy(tool.get("warnings") or []),
            "api_binding": copy.deepcopy(tool.get("api_binding") or {}),
        })
    return (
        "# Knowledge Consumer Integration Contract\n\n"
        "Use only the pinned Knowledge API revision and tools described below. Dialogue, agent-loop, "
        "provider and final-response mechanics belong to this external consumer runtime and are not AISL facts.\n\n"
        + str(policy.get("grounding") or "")
        + "\n\n# Integration scope\n\n```json\n"
        + json.dumps(dict(scope), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n\n# Retrieval guidance\n\n"
        + str(retrieval.get("content") or "")
        + "\n\n# Available HTTP tools\n\n```json\n"
        + json.dumps(compact_tools, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n"
    )



@dataclass(frozen=True, slots=True)
class ConsumerProfile:
    integration: ConsumerIntegration

    @classmethod
    def load(cls, client: AislClient, *, system_id: str, revision_id: str, profile_id: str) -> "ConsumerProfile":
        # Resolve the exact immutable revision, then delegate Integration Profile retrieval to the public SDK.
        pinned = client.revision(_require_text(system_id, "system_id"), _require_text(revision_id, "revision_id"))
        return cls(integration=pinned.integration(_require_text(profile_id, "profile_id")))

    @property
    def system_id(self) -> str:
        return self.integration.system_id

    @property
    def revision_id(self) -> str:
        return self.integration.revision_id

    @property
    def profile_id(self) -> str:
        return self.integration.profile_id

    @property
    def fingerprint(self) -> str:
        return self.integration.fingerprint

    @property
    def payload(self) -> Mapping[str, Any]:
        return self.integration.raw

    @property
    def system_prompt(self) -> str:
        return _render_system_prompt(self.payload)

    @property
    def openai_tools(self) -> list[dict[str, Any]]:
        return _openai_tools(self.payload)


@dataclass(slots=True)
class AgentSession:
    session_id: str
    profile: ConsumerProfile
    provider: ChatProvider
    max_tool_rounds: int = 16
    conversation: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0

    def ask(self, question: str) -> dict[str, Any]:
        text = _require_text(question, "question")
        self.turn_count += 1
        self.conversation.append({"role": "user", "content": text})
        working = [dict(v) for v in self.conversation]
        trace: list[dict[str, Any]] = []
        for round_index in range(1, self.max_tool_rounds + 1):
            started = time.perf_counter()
            completion = self.provider.complete(
                system_prompt=self.profile.system_prompt,
                messages=working,
                tools=self.profile.openai_tools,
            )
            provider_ms = int((time.perf_counter() - started) * 1000)
            message = _require_mapping(completion.get("message"), "provider.message")
            content = message.get("content")
            tool_calls = message.get("tool_calls") or []
            assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_message["tool_calls"] = copy.deepcopy(tool_calls)
            working.append(assistant_message)
            round_trace: dict[str, Any] = {
                "round": round_index,
                "provider_duration_ms": provider_ms,
                "finish_reason": completion.get("finish_reason"),
                "tool_calls": [],
            }
            if not tool_calls:
                answer = str(content or "")
                self.conversation.append({"role": "assistant", "content": answer})
                trace.append(round_trace)
                return {
                    "schema_version": "aisl_agent_turn/v1",
                    "session_id": self.session_id,
                    "turn": self.turn_count,
                    "scope": {
                        "system_id": self.profile.system_id,
                        "revision_id": self.profile.revision_id,
                        "profile_id": self.profile.profile_id,
                        "integration_profile_fingerprint": self.profile.fingerprint,
                    },
                    "answer": answer,
                    "trace": trace,
                }

            if not isinstance(tool_calls, list):
                raise RuntimeError("provider tool_calls must be an array")
            for raw_call in tool_calls:
                call = _require_mapping(raw_call, "tool_call")
                function = _require_mapping(call.get("function"), "tool_call.function")
                name = _require_text(function.get("name"), "tool_call.function.name")
                raw_args = function.get("arguments") or "{}"
                if isinstance(raw_args, str):
                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(f"provider returned invalid JSON arguments for {name}: {raw_args!r}") from exc
                else:
                    arguments = raw_args
                arguments = _require_mapping(arguments, "tool arguments")
                tool_result = self.profile.integration.execute_tool(name, arguments)
                round_trace["tool_calls"].append({
                    "tool_call_id": call.get("id"),
                    "tool_name": name,
                    "arguments": dict(arguments),
                    "duration_ms": tool_result.duration_ms,
                    "operation_id": tool_result.operation_id,
                    "expected_schema_versions": list(tool_result.expected_schema_versions),
                    "result": copy.deepcopy(dict(tool_result.result)),
                })
                working.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": json.dumps(tool_result.result, ensure_ascii=False, sort_keys=True),
                })
            trace.append(round_trace)
        raise RuntimeError(f"agent did not finish within {self.max_tool_rounds} tool rounds")


class AgentRuntime:
    def __init__(self, *, client: AislClient, provider: ChatProvider, max_tool_rounds: int = 16) -> None:
        self.client = client
        self.provider = provider
        self.max_tool_rounds = max_tool_rounds
        self._sessions: dict[str, AgentSession] = {}

    def create_session(self, *, system_id: str, revision_id: str, profile_id: str) -> AgentSession:
        profile = ConsumerProfile.load(
            self.client,
            system_id=system_id,
            revision_id=revision_id,
            profile_id=profile_id,
        )
        session_id = "agent-" + uuid.uuid4().hex
        session = AgentSession(
            session_id=session_id,
            profile=profile,
            provider=self.provider,
            max_tool_rounds=self.max_tool_rounds,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> AgentSession:
        sid = _require_text(session_id, "session_id")
        try:
            return self._sessions[sid]
        except KeyError as exc:
            raise KeyError(f"unknown agent session: {sid}") from exc
