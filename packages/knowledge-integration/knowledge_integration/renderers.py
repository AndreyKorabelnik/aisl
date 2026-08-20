from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import LlmIntegrationProfile


def canonical_json(profile: LlmIntegrationProfile | Mapping[str, Any]) -> str:
    payload = profile.to_dict() if isinstance(profile, LlmIntegrationProfile) else dict(profile)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def system_prompt(profile: LlmIntegrationProfile | Mapping[str, Any]) -> str:
    payload = profile.to_dict() if isinstance(profile, LlmIntegrationProfile) else dict(profile)
    scope = payload["scope"]
    tools = payload["tools"]
    policy = payload["policy"]["grounding"]
    guidance = payload["retrieval_guidance"]["content"]
    compact_tools = [
        {
            "name": t["name"],
            "description": t["description"],
            "arguments": t["arguments"],
            "required_capabilities": t["required_capabilities"],
            "warnings": t.get("warnings") or [],
            "api_binding": t["api_binding"],
        }
        for t in tools
    ]
    return (
        "# Knowledge Consumer Integration Contract\n\n"
        "Use only the pinned Knowledge API revision and tools described below. Dialogue, agent-loop, "
        "provider and final-response mechanics belong to the consumer runtime and are outside this integration contract.\n\n"
        + policy
        + "\n\n# Integration scope\n\n```json\n"
        + json.dumps(scope, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n\n# Retrieval guidance\n\n"
        + guidance
        + "\n\n# Available HTTP tools\n\n```json\n"
        + json.dumps(compact_tools, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n```\n"
    )


def api_usage(profile: LlmIntegrationProfile | Mapping[str, Any]) -> str:
    payload = profile.to_dict() if isinstance(profile, LlmIntegrationProfile) else dict(profile)
    scope = payload["scope"]
    return (
        "# Knowledge API usage\n\n"
        f"System: `{scope['system_id']}`  \nRevision: `{scope['revision_id']}` (pinned)\n\n"
        "For each tool use its `api_binding`. Replace `{system_id}` with the pinned system id. "
        "Inject the pinned revision exactly where `revision_binding` specifies. Map tool arguments "
        "according to `arguments`; `fixed_query` and `fixed_body` are mandatory constants. "
        "Never replace the pinned revision with active/latest during a session.\n"
    )


def export_consumer_kit(profile: LlmIntegrationProfile | Mapping[str, Any], output_dir: str | Path) -> Path:
    payload = profile.to_dict() if isinstance(profile, LlmIntegrationProfile) else dict(profile)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "llm_integration_profile.json").write_text(canonical_json(payload), encoding="utf-8")
    (root / "SYSTEM_PROMPT.md").write_text(system_prompt(payload), encoding="utf-8")
    (root / "TOOL_CATALOG.json").write_text(json.dumps(payload["tools"], ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    (root / "CAPABILITIES.json").write_text(json.dumps({"scope": payload["scope"], "capabilities": payload["capabilities"], "knowledge_artifacts": payload.get("knowledge_artifacts", [])}, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    (root / "RETRIEVAL_GUIDE.md").write_text(payload["retrieval_guidance"]["content"].rstrip()+"\n", encoding="utf-8")
    (root / "API_USAGE.md").write_text(api_usage(payload), encoding="utf-8")
    return root
