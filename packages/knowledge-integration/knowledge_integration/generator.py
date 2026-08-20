from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from .api_bindings import binding, external_tool_names
from .models import LlmIntegrationProfile, RevisionContext, SCHEMA_VERSION
from .policy import consumer_policy, consumer_policy_fingerprint
from .profile_registry import load_profile
from .tool_catalog import (
    TOOL_CAPABILITY_REQUIREMENTS,
    TOOL_CATALOG,
    TOOL_CATALOG_VERSION,
    tool_warnings,
    tools_for_capabilities,
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _artifact_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = value.get("diagnostics")
    return {
        "artifact_id": value.get("artifact_id"),
        "model_kind": value.get("model_kind"),
        "schema_version": value.get("schema_version"),
        "source_materialization_id": value.get("source_materialization_id"),
        "content_fingerprint": value.get("content_fingerprint"),
        "capabilities": sorted(str(v) for v in value.get("capabilities") or () if str(v)),
        "coverage": deepcopy(dict(value.get("coverage") or {})),
        "diagnostic_count": len(diagnostics) if isinstance(diagnostics, list) else 0,
    }


def canonical_tool_definitions() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted(TOOL_CATALOG):
        definition = deepcopy(TOOL_CATALOG[name])
        definition["required_capabilities"] = list(TOOL_CAPABILITY_REQUIREMENTS[name])
        definition["warnings"] = list(tool_warnings(name, {}))
        definition["api_binding"] = binding(name)
        result[name] = definition
    return result


def tool_catalog_fingerprint() -> str:
    return _fingerprint({"version": TOOL_CATALOG_VERSION, "tools": canonical_tool_definitions()})


def generate_integration_profile(
    context: RevisionContext | Mapping[str, Any],
    *,
    profile_id: str,
) -> LlmIntegrationProfile:
    if not isinstance(context, RevisionContext):
        context = RevisionContext.from_mapping(context)
    if not context.system_id:
        raise ValueError("system_id must not be empty")
    if not context.revision_id:
        raise ValueError("revision_id must not be empty")
    retrieval = load_profile(profile_id)
    allowed = tools_for_capabilities(context.capabilities) & external_tool_names()
    tools: list[dict[str, Any]] = []
    for name in sorted(allowed):
        definition = deepcopy(TOOL_CATALOG[name])
        tools.append({
            "name": name,
            "description": definition.get("description"),
            "arguments": deepcopy(definition.get("arguments") or {}),
            "required_capabilities": list(TOOL_CAPABILITY_REQUIREMENTS[name]),
            "warnings": list(tool_warnings(name, {})),
            "api_binding": binding(name),
        })
    capabilities = list(context.capabilities)
    policy = consumer_policy()
    artifacts = sorted(
        (_artifact_summary(v) for v in context.knowledge_artifacts),
        key=lambda v: (str(v.get("artifact_id") or ""), str(v.get("content_fingerprint") or ""), str(v.get("model_kind") or "")),
    )
    generated_from = {
        "revision_id": context.revision_id,
        "capabilities_fingerprint": _fingerprint(capabilities),
        "tool_catalog_version": TOOL_CATALOG_VERSION,
        "tool_catalog_fingerprint": tool_catalog_fingerprint(),
        "consumer_policy_fingerprint": consumer_policy_fingerprint(),
        "retrieval_profile_fingerprint": retrieval.fingerprint,
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "system_id": context.system_id,
            "revision_id": context.revision_id,
            "revision_binding": "pinned",
        },
        "capabilities": capabilities,
        "knowledge_artifacts": artifacts,
        "integration_profile": {
            "profile_id": retrieval.profile_id,
            "profile_version": retrieval.version,
            "profile_fingerprint": retrieval.fingerprint,
            "fingerprint": "",
        },
        "policy": {
            "grounding": policy,
            "evidence_statuses": [
                "observed",
                "strongly_supported",
                "probable",
                "ambiguity",
                "unresolved",
                "gap",
            ],
            "rules": {
                "no_schema_guessing": True,
                "no_relation_or_join_guessing": True,
                "preserve_confidence_and_basis": True,
                "preserve_diagnostics_and_gaps": True,
                "facts_require_tool_results": True,
            },
        },
        "tools": tools,
        "retrieval_guidance": {
            "profile_id": retrieval.profile_id,
            "profile_version": retrieval.version,
            "content": retrieval.content,
        },
        "generated_from": generated_from,
    }
    fingerprint_payload = deepcopy(payload)
    fingerprint_payload["integration_profile"]["fingerprint"] = ""
    payload["integration_profile"]["fingerprint"] = _fingerprint(fingerprint_payload)
    return LlmIntegrationProfile(payload)
