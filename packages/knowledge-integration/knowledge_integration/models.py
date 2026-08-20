from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_VERSION = "llm_integration_profile/v1"

@dataclass(frozen=True, slots=True)
class RevisionContext:
    system_id: str
    revision_id: str
    capabilities: tuple[str, ...]
    knowledge_artifacts: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RevisionContext":
        return cls(
            system_id=str(value.get("system_id") or "").strip(),
            revision_id=str(value.get("revision_id") or "").strip(),
            capabilities=tuple(sorted({str(v) for v in value.get("capabilities") or () if str(v)})),
            knowledge_artifacts=tuple(dict(v) for v in value.get("knowledge_artifacts") or () if isinstance(v, Mapping)),
        )

@dataclass(frozen=True, slots=True)
class LlmIntegrationProfile:
    payload: Mapping[str, Any]

    @property
    def fingerprint(self) -> str:
        return str(self.payload.get("integration_profile", {}).get("fingerprint") or "")

    def to_dict(self) -> dict[str, Any]:
        import copy
        return copy.deepcopy(dict(self.payload))
