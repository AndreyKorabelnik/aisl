from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from .api_bindings import binding


@dataclass(frozen=True, slots=True)
class KnowledgeApiHttpRequest:
    method: str
    path: str
    query: Mapping[str, Any]
    body: Mapping[str, Any] | None
    expected_schema_versions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "query": dict(self.query),
            "body": None if self.body is None else deepcopy(dict(self.body)),
            "expected_schema_versions": list(self.expected_schema_versions),
        }


def _required_text(value: Any, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _transform(value: Any, transform: str, *, name: str) -> Any:
    if transform == "identity":
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value
    if transform == "url_segment":
        return quote(_required_text(value, name), safe="")
    if transform == "bool":
        if value is None:
            return None
        return bool(value)
    if transform == "bounded_int":
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc
    if transform == "list":
        if value is None:
            return None
        if not isinstance(value, (list, tuple, set)):
            raise ValueError(f"{name} must be an array")
        return [str(item).strip() for item in value if str(item).strip()]
    if transform == "csv":
        if value is None:
            return None
        if not isinstance(value, (list, tuple, set)):
            raise ValueError(f"{name} must be an array")
        return ",".join(str(item).strip() for item in value if str(item).strip()) or None
    raise ValueError(f"unsupported integration argument transform: {transform}")


def build_knowledge_api_http_request(
    tool_name: str,
    *,
    system_id: str,
    revision_id: str,
    arguments: Mapping[str, Any] | None = None,
) -> KnowledgeApiHttpRequest:
    spec = binding(tool_name)
    if spec.get("binding_kind") != "knowledge_api_http":
        raise ValueError(f"integration tool is not an external Knowledge API HTTP tool: {tool_name}")
    args = dict(arguments or {})
    if str(args.get("revision_id") or "").strip():
        raise ValueError("revision_id is pinned by the integration profile and cannot be overridden")

    path = str(spec["path_template"]).replace(
        "{system_id}", quote(_required_text(system_id, "system_id"), safe="")
    )
    query: dict[str, Any] = deepcopy(dict(spec.get("fixed_query") or {}))
    method = str(spec.get("method") or "GET").upper()
    body: dict[str, Any] | None = deepcopy(dict(spec.get("fixed_body") or {})) if method == "POST" else None

    for tool_arg, mapping in dict(spec.get("arguments") or {}).items():
        if tool_arg not in args:
            continue
        target_name = str(mapping.get("name") or tool_arg)
        value = _transform(args.get(tool_arg), str(mapping.get("transform") or "identity"), name=tool_arg)
        if value is None or value == "":
            continue
        location = str(mapping.get("location") or "")
        if location == "path":
            path = path.replace("{" + target_name + "}", str(value))
        elif location == "query":
            query[target_name] = value
        elif location == "body":
            if body is None:
                body = {}
            body[target_name] = value
        elif location == "body_filter":
            if body is None:
                body = {}
            filters = body.setdefault("filters", {})
            if not isinstance(filters, dict):
                raise ValueError("fixed body filters must be an object")
            filters[target_name] = value
        else:
            raise ValueError(f"unsupported integration argument location: {location}")

    unresolved = [part.split("}", 1)[0] for part in path.split("{")[1:] if "}" in part]
    if unresolved:
        raise ValueError(f"missing required path argument(s): {', '.join(sorted(unresolved))}")

    revision = _required_text(revision_id, "revision_id")
    revision_binding = dict(spec.get("revision_binding") or {})
    revision_location = str(revision_binding.get("location") or "")
    revision_name = str(revision_binding.get("name") or "revision_id")
    if revision_location == "query":
        query[revision_name] = revision
    elif revision_location == "body":
        if body is None:
            body = {}
        body[revision_name] = revision
    else:
        raise ValueError(f"unsupported revision binding location: {revision_location}")

    return KnowledgeApiHttpRequest(
        method=method,
        path=path,
        query=query,
        body=body,
        expected_schema_versions=tuple(spec.get("expected_schema_versions") or ("knowledge_api/v1",)),
    )
