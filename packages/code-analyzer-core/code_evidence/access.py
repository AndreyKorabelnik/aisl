from __future__ import annotations

import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import commands
from .catalog import load_evidence_tool_catalog

_RUNTIME_PATH_ARG_NAMES = {
    "analysis_output_path",
    "static_analysis_output_path",
    "llm_output_path",
    "llm_analysis_output_path",
}

_ARGUMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "analysis_out": ("static_analysis_output_path", "analysis_output_path"),
    "llm_out": ("llm_analysis_output_path", "llm_output_path"),
    "symbol_name": ("symbol", "token"),
    "schema_id_or_name": ("schema_id", "schema", "schema_name", "token"),
    "file_or_token": ("file_path", "file", "token"),
    "operation_id": ("operation_id", "operation", "token"),
    "interface_id": ("interface_id", "interface", "token"),
    "evidence_id": ("evidence_id", "id", "ref_id", "token"),
    "occurrence_id": ("occurrence_id", "id", "token"),
    "edge_id": ("edge_id", "id", "token"),
    "fact_type": ("fact_type", "type"),
    "callable_name": ("callable", "callable_name"),
    "object_id": ("object_id", "id", "token"),
    "token": ("token", "symbol"),
}

_INT_ARGS = {"max_results", "max_items", "max_chars", "context", "line", "start_line", "end_line", "depth", "limit", "max_depth", "max_nodes"}
_BOOL_ARGS = {"with_persistent_write_refs", "with_saved_attributes", "matched"}


class EvidenceAccessError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _command_function_name(command_id: str) -> str:
    return command_id.strip().replace("-", "_")


def _catalog_commands() -> dict[str, dict[str, Any]]:
    catalog = load_evidence_tool_catalog()
    out: dict[str, dict[str, Any]] = {}
    for item in catalog.get("tools") or catalog.get("commands") or []:
        if isinstance(item, dict) and item.get("command_id"):
            out[str(item["command_id"])] = item
    return out


def _normalize_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name in _INT_ARGS and isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        try:
            return int(value.strip())
        except ValueError:
            return value
    if name in _BOOL_ARGS and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return value


def _get_arg(arguments: dict[str, Any], name: str) -> tuple[bool, Any]:
    if name in arguments:
        return True, arguments[name]
    for alias in _ARGUMENT_ALIASES.get(name, ()):  # noqa: SIM118
        if alias in arguments:
            return True, arguments[alias]
    return False, None


def _build_call_kwargs(
    func: Any,
    *,
    command_id: str,
    arguments: dict[str, Any],
    static_analysis_output: Path | None,
    llm_analysis_output: Path | None,
    repo_id: str | None,
) -> dict[str, Any]:
    sig = inspect.signature(func)
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "analysis_out":
            raw = arguments.get("static_analysis_output_path") or arguments.get("analysis_output_path") or static_analysis_output
            if raw is None:
                raise EvidenceAccessError(f"{command_id}: missing static_analysis_output_path")
            kwargs[name] = Path(raw)
            continue
        if name == "llm_out":
            raw = arguments.get("llm_analysis_output_path") or arguments.get("llm_output_path") or llm_analysis_output
            if raw is None:
                raise EvidenceAccessError(f"{command_id}: missing llm_analysis_output_path")
            kwargs[name] = Path(raw)
            continue
        if name == "repo_id" and repo_id is not None and name not in arguments:
            kwargs[name] = repo_id
            continue
        found, value = _get_arg(arguments, name)
        if found:
            kwargs[name] = _normalize_value(name, value)
            continue
        if param.default is inspect.Parameter.empty:
            raise EvidenceAccessError(f"{command_id}: missing required argument: {name}")
    return kwargs


def execute_evidence_request(
    request: dict[str, Any],
    *,
    static_analysis_output: Path | None = None,
    llm_analysis_output: Path | None = None,
    repo_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise EvidenceAccessError("evidence request must be an object")
    command_id = str(request.get("command_id") or "").strip()
    if not command_id:
        raise EvidenceAccessError("evidence request command_id is required")
    catalog = _catalog_commands()
    if command_id not in catalog:
        raise EvidenceAccessError(f"unknown evidence tool: {command_id}")
    func_name = _command_function_name(command_id)
    func = getattr(commands, func_name, None)
    if func is None:
        raise EvidenceAccessError(f"evidence tool has no backend implementation: {command_id}")
    arguments = request.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise EvidenceAccessError(f"{command_id}: arguments must be an object")
    kwargs = _build_call_kwargs(
        func,
        command_id=command_id,
        arguments=arguments,
        static_analysis_output=static_analysis_output,
        llm_analysis_output=llm_analysis_output,
        repo_id=repo_id,
    )
    return func(**kwargs)


def _preview_payload(payload: Any, max_chars: int) -> tuple[str, bool]:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return text[:max_chars], len(text) > max_chars


def execute_evidence_requests(
    requests: list[dict[str, Any]],
    *,
    static_analysis_output: Path | None = None,
    llm_analysis_output: Path | None = None,
    repo_id: str | None = None,
    max_output_chars: int = 20000,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for idx, item in enumerate(requests, 1):
        request_id = str(item.get("request_id") or f"req_{idx:03d}")
        started = time.perf_counter()
        status = "success"
        error: str | None = None
        payload: Any = None
        try:
            payload = execute_evidence_request(
                item,
                static_analysis_output=static_analysis_output,
                        llm_analysis_output=llm_analysis_output,
                repo_id=repo_id,
            )
        except Exception as exc:  # deliberately captured as evidence result, not raised
            status = "failed"
            error = str(exc)
            payload = {"error": error}
        duration_ms = int((time.perf_counter() - started) * 1000)
        preview, truncated = _preview_payload(payload, max_output_chars)
        results.append({
            "request_id": request_id,
            "reason": item.get("reason") or "",
            "command_id": item.get("command_id"),
            "arguments": item.get("arguments") or {},
            "status": status,
            "execution_error": error,
            "duration_ms": duration_ms,
            "payload": payload,
            "stdout_preview": preview,
            "stdout_truncated": truncated,
            "backend": "evidence_access_api",
        })
    return {
        "generated_at": _now(),
        "total_requests": len(results),
        "results": results,
    }
