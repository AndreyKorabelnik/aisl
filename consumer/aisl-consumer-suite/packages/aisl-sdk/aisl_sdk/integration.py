from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from .errors import AislContractError


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AislContractError(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise AislContractError(f"{name} must not be empty")
    return result


def _transform(value: Any, transform: str) -> Any:
    if transform in {"", "identity", "url_segment"}:
        return value
    if transform == "csv":
        if isinstance(value, (list, tuple)):
            return ",".join(str(v) for v in value)
        return str(value)
    if transform == "bool":
        return "true" if bool(value) else "false"
    if transform in {"bounded_int", "integer"}:
        return str(int(value))
    raise AislContractError(f"unsupported api-binding transform: {transform}")


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool_name: str
    arguments: Mapping[str, Any]
    operation_id: str | None
    expected_schema_versions: tuple[str, ...]
    duration_ms: int
    result: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ConsumerIntegration:
    """Revision-pinned public Integration Profile plus declarative tool executor.

    The caller/LLM chooses a tool. This class only validates membership and executes
    the canonical Knowledge API binding from the profile. It adds no knowledge or
    tool-selection semantics.
    """

    client: Any
    system_id: str
    revision_id: str
    profile_id: str
    fingerprint: str
    raw: Mapping[str, Any]

    @classmethod
    def load(cls, client: Any, *, system_id: str, revision_id: str, profile_id: str) -> "ConsumerIntegration":
        sid = _text(system_id, "system_id")
        rid = _text(revision_id, "revision_id")
        pid = _text(profile_id, "profile_id")
        path = f"/api/knowledge/v1/systems/{quote(sid, safe='')}/llm-integration-profile"
        payload = client.get_json(path, params={"revision_id": rid, "profile_id": pid})
        scope = _mapping(payload.get("scope"), "Integration Profile scope")
        if scope.get("system_id") != sid or scope.get("revision_id") != rid or scope.get("revision_binding") != "pinned":
            raise AislContractError("Integration Profile scope does not match the pinned revision")
        integration = _mapping(payload.get("integration_profile"), "integration_profile")
        actual_profile_id = _text(integration.get("profile_id"), "integration_profile.profile_id")
        if actual_profile_id != pid:
            raise AislContractError(f"Integration Profile id mismatch: requested {pid!r}, got {actual_profile_id!r}")
        return cls(
            client=client,
            system_id=sid,
            revision_id=rid,
            profile_id=pid,
            fingerprint=str(integration.get("fingerprint") or ""),
            raw=copy.deepcopy(payload),
        )

    @property
    def tools(self) -> tuple[Mapping[str, Any], ...]:
        value = self.raw.get("tools")
        if value is None:
            value = []
        if not isinstance(value, list):
            raise AislContractError("Integration Profile tools must be an array")
        return tuple(copy.deepcopy(dict(item)) for item in value if isinstance(item, Mapping))

    def tool(self, name: str) -> Mapping[str, Any]:
        tool_name = _text(name, "tool name")
        for tool in self.tools:
            if tool.get("name") == tool_name:
                return tool
        raise AislContractError(f"tool {tool_name!r} is not allowed by the pinned Integration Profile")

    def execute_tool(self, name: str, arguments: Mapping[str, Any]) -> ToolExecutionResult:
        tool = self.tool(name)
        binding = _mapping(tool.get("api_binding") or {}, "api_binding")
        if binding.get("binding_kind") != "knowledge_api_http":
            raise AislContractError(f"unsupported binding_kind for {name}: {binding.get('binding_kind')!r}")
        method = str(binding.get("method") or "GET").upper()
        path = _text(binding.get("path_template"), "path_template").replace("{system_id}", quote(self.system_id, safe=""))
        query = {str(k): v for k, v in _mapping(binding.get("fixed_query") or {}, "fixed_query").items()}
        body = {str(k): v for k, v in _mapping(binding.get("fixed_body") or {}, "fixed_body").items()}
        revision_binding = _mapping(binding.get("revision_binding") or {}, "revision_binding")
        revision_location = revision_binding.get("location")
        revision_name = str(revision_binding.get("name") or "revision_id")
        if revision_location == "query":
            query[revision_name] = self.revision_id
        elif revision_location == "body":
            body[revision_name] = self.revision_id
        else:
            raise AislContractError(f"unsupported revision binding location: {revision_location!r}")

        bound_args = _mapping(binding.get("arguments") or {}, "api_binding.arguments")
        for arg_name, raw_binding in bound_args.items():
            if arg_name not in arguments or arguments[arg_name] is None:
                continue
            arg_binding = _mapping(raw_binding, f"binding for {arg_name}")
            location = str(arg_binding.get("location") or "")
            api_name = str(arg_binding.get("name") or arg_name)
            value = _transform(arguments[arg_name], str(arg_binding.get("transform") or "identity"))
            if location == "path":
                path = path.replace("{" + api_name + "}", quote(str(value), safe=""))
            elif location == "query":
                query[api_name] = value
            elif location == "body":
                body[api_name] = value
            else:
                raise AislContractError(f"unsupported argument location for {arg_name}: {location!r}")
        if "{" in path or "}" in path:
            raise AislContractError(f"tool {name!r} is missing a required path argument: {path}")

        started = time.perf_counter()
        if method == "GET":
            result = self.client.get_json(path, params=query)
        elif method == "POST":
            result = self.client.post_json(path, body, params=query)
        else:
            raise AislContractError(f"unsupported HTTP method for {name}: {method}")
        return ToolExecutionResult(
            tool_name=name,
            arguments=copy.deepcopy(dict(arguments)),
            operation_id=(str(binding.get("operation_id")) if binding.get("operation_id") else None),
            expected_schema_versions=tuple(str(v) for v in binding.get("expected_schema_versions") or () if str(v)),
            duration_ms=int((time.perf_counter() - started) * 1000),
            result=copy.deepcopy(result),
        )
