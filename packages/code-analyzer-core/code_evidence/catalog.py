from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any

from code_analyzer_core import __version__ as ANALYZER_VERSION

CATALOG_RESOURCE_PACKAGE = "code_evidence.resources"
CATALOG_RESOURCE_NAME = "evidence_tool_catalog.json"


def load_evidence_tool_catalog(*, include_analyzer_version: bool = True) -> dict[str, Any]:
    """Load the packaged evidence tool catalog.

    The catalog is a static, versioned evidence tool contract. The analyzer version is
    injected from code_analyzer_core.__version__ at read time to avoid keeping
    duplicated version strings in the resource file.
    """
    text = resources.files(CATALOG_RESOURCE_PACKAGE).joinpath(CATALOG_RESOURCE_NAME).read_text(encoding="utf-8")
    payload = json.loads(text)
    if include_analyzer_version:
        payload = copy.deepcopy(payload)
        payload["analyzer_version"] = ANALYZER_VERSION
    return payload


def _matches_all(required: list[str] | None, available: set[str]) -> bool:
    if not required:
        return True
    return set(required).issubset(available)


def filter_evidence_tool_catalog(
    catalog: dict[str, Any],
    *,
    workspace_type: str | None = None,
    analysis_profile: str | None = None,
    capabilities: list[str] | set[str] | None = None,
    agent_visible_only: bool = False,
    include_deprecated: bool = False,
) -> dict[str, Any]:
    """Return a runtime-applicable subset of the static catalog.

    This helper is intended for evidence-llm-pipeline or any other runtime
    component that needs to pass only enabled evidence tools to an LLM. It does
    not add runtime paths to templates. Materialising placeholders remains the
    responsibility of the caller.
    """
    caps = set(capabilities or [])
    selected: list[dict[str, Any]] = []
    for command in catalog.get("tools") or catalog.get("commands", []):
        if agent_visible_only and not command.get("agent_visible", False):
            continue
        if not include_deprecated and command.get("stability") == "deprecated":
            continue
        workspace_types = command.get("workspace_types") or []
        if workspace_type and workspace_types and workspace_type not in workspace_types:
            continue
        profiles = command.get("requires_analysis_profile") or []
        if analysis_profile and profiles and analysis_profile not in profiles:
            continue
        if profiles and not analysis_profile:
            continue
        if not _matches_all(command.get("requires_capability"), caps):
            continue
        selected.append(copy.deepcopy(command))

    result = copy.deepcopy(catalog)
    result["tools"] = selected
    result["commands"] = selected
    result["tool_count"] = len(selected)
    result["command_count"] = len(selected)
    result["filtered"] = True
    result["filter"] = {
        "workspace_type": workspace_type,
        "analysis_profile": analysis_profile,
        "capabilities": sorted(caps),
        "agent_visible_only": agent_visible_only,
        "include_deprecated": include_deprecated,
    }
    return result


def load_enabled_evidence_tool_catalog(
    *,
    workspace_type: str | None = None,
    analysis_profile: str | None = None,
    capabilities: list[str] | set[str] | None = None,
    agent_visible_only: bool = True,
) -> dict[str, Any]:
    return filter_evidence_tool_catalog(
        load_evidence_tool_catalog(),
        workspace_type=workspace_type,
        analysis_profile=analysis_profile,
        capabilities=capabilities,
        agent_visible_only=agent_visible_only,
    )
