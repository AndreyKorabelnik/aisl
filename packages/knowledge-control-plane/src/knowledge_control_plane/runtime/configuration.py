from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

from knowledge_control_plane.api.generic_v1.models import (
    AvailabilityStatus,
    ConfigurationPatch,
    ConfigurationResponse,
    ConfigurationUpdateRequest,
    ConfigurationValidationRequest,
    ConfigurationValidationResponse,
    PathStatus,
    ResolvedTool,
    RuntimePaths,
    ToolCommands,
    ValidationIssue,
    ValidationSeverity,
)

from .errors import RevisionConflict
from .settings import RuntimeSettings
from .store import RuntimeStore


def _path_status(value: str | None, *, writable: bool = False) -> PathStatus:
    if not value:
        return PathStatus(value=None, configured=False)
    path = Path(value).expanduser()
    exists = path.exists()
    return PathStatus(
        value=str(path),
        configured=True,
        exists=exists,
        readable=os.access(path, os.R_OK) if exists else False,
        writable=os.access(path, os.W_OK) if exists else (os.access(path.parent, os.W_OK) if path.parent.exists() else False)
        if writable
        else None,
    )


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(target)
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigurationService:
    def __init__(self, store: RuntimeStore, settings: RuntimeSettings) -> None:
        self.store = store
        self.settings = settings
        self._tool_probe_cache: dict[tuple[str, tuple[str, ...], int, int], tuple[str | None, AvailabilityStatus]] = {}
        existing = self.store.load_configuration()
        if existing is None:
            self.store.save_configuration(1, self._default_payload())

    def _default_payload(self) -> dict[str, Any]:
        return {
            "paths": {
                "repository_roots": [],
                "analysis_output_root": str(self.settings.default_analysis_output_root),
                "runtime_root": str(self.settings.runtime_root),
                "allowed_output_roots": [
                    str(self.settings.default_analysis_output_root),
                ],
            },
            "commands": {
                "static_analysis_runner": os.getenv("STATIC_ANALYSIS_RUNNER_COMMAND", "static-analysis-runner"),
            },
        }

    def raw(self) -> tuple[int, dict[str, Any]]:
        loaded = self.store.load_configuration()
        assert loaded is not None
        return loaded

    def get(self) -> ConfigurationResponse:
        revision, payload = self.raw()
        paths = payload["paths"]
        return ConfigurationResponse(
            revision=revision,
            paths=RuntimePaths(
                repository_roots=list(paths.get("repository_roots") or []),
                analysis_output_root=_path_status(paths.get("analysis_output_root"), writable=True),
                runtime_root=_path_status(paths.get("runtime_root"), writable=True),
                allowed_output_roots=list(paths.get("allowed_output_roots") or []),
            ),
            commands=ToolCommands.model_validate(payload["commands"]),
        )

    def update(self, request: ConfigurationUpdateRequest) -> ConfigurationResponse:
        revision, payload = self.raw()
        if revision != request.expected_revision:
            raise RevisionConflict("configuration", request.expected_revision, revision)
        patch = request.configuration.model_dump(exclude_none=True)
        updated = _deep_merge(payload, patch)
        self.store.save_configuration(revision + 1, updated)
        return self.get()

    def validate(self, request: ConfigurationValidationRequest) -> ConfigurationValidationResponse:
        _, current = self.raw()
        patch = request.configuration.model_dump(exclude_none=True) if request.configuration else {}
        candidate = _deep_merge(current, patch)
        issues: list[ValidationIssue] = []
        paths = candidate["paths"]
        for field in ("analysis_output_root", "runtime_root"):
            value = paths.get(field)
            if not value:
                issues.append(
                    ValidationIssue(
                        code="path_not_configured",
                        severity=ValidationSeverity.ERROR,
                        field=f"paths.{field}",
                        message=f"path is not configured: {field}",
                    )
                )
                continue
            path = Path(value).expanduser()
            parent = path if path.exists() else path.parent
            if not parent.exists() or not os.access(parent, os.W_OK):
                issues.append(
                    ValidationIssue(
                        code="path_not_writable",
                        severity=ValidationSeverity.ERROR,
                        field=f"paths.{field}",
                        message=f"path is not writable: {path}",
                    )
                )

        tools = [
            self._resolve_tool(name, command)
            for name, command in candidate["commands"].items()
        ]
        for tool in tools:
            if tool.status is AvailabilityStatus.UNAVAILABLE:
                issues.append(
                    ValidationIssue(
                        code="tool_unavailable",
                        severity=ValidationSeverity.WARNING,
                        field=f"commands.{tool.tool}",
                        message=f"tool is unavailable: {tool.command}",
                    )
                )

        return ConfigurationValidationResponse(
            valid=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
            issues=issues,
            tools=tools,
        )

    def _resolve_tool(self, name: str, command: str) -> ResolvedTool:
        parts = shlex.split(command)
        executable = parts[0] if parts else command
        resolved = shutil.which(executable)
        version: str | None = None
        status = AvailabilityStatus.UNAVAILABLE
        if resolved:
            try:
                stat = Path(resolved).stat()
                cache_key = (resolved, tuple(parts[1:]), stat.st_mtime_ns, stat.st_size)
            except OSError:
                cache_key = (resolved, tuple(parts[1:]), 0, 0)
            cached = self._tool_probe_cache.get(cache_key)
            if cached is None:
                for version_args in (["--version"], ["version"]):
                    try:
                        completed = subprocess.run(
                            [resolved, *parts[1:], *version_args],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        text = (completed.stdout or completed.stderr).strip()
                        if text:
                            version = text.splitlines()[0][:200]
                            break
                    except (OSError, subprocess.SubprocessError):
                        break
                status = AvailabilityStatus.AVAILABLE
                self._tool_probe_cache[cache_key] = (version, status)
            else:
                version, status = cached
        return ResolvedTool(
            tool=name,
            command=command,
            resolved_path=resolved,
            version=version,
            status=status,
        )

    def resolve_configured_tool(self, command_name: str) -> ResolvedTool:
        _, payload = self.raw()
        return self._resolve_tool(command_name, str(payload["commands"][command_name]))

    def command_parts(self, command_name: str) -> list[str]:
        _, payload = self.raw()
        command = str(payload["commands"][command_name])
        parts = shlex.split(command)
        if not parts:
            raise ValueError(f"empty command: {command_name}")
        return parts

    def path_value(self, name: str) -> Path:
        _, payload = self.raw()
        return Path(payload["paths"][name]).expanduser().resolve()

    def allowed_output_roots(self) -> list[Path]:
        _, payload = self.raw()
        return [Path(value).expanduser().resolve() for value in payload["paths"].get("allowed_output_roots") or []]
