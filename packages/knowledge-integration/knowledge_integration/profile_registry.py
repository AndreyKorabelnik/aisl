from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files

ATTRIBUTE_ADDITION_PROFILE_ID = "attribute-addition-plan/v1"
SYSTEM_INTERACTIONS_PROFILE_ID = "system-interactions/v1"
SYSTEM_DESCRIPTION_PROFILE_ID = "system-description/v1"
DATA_MODEL_PROFILE_ID = "data-model/v1"
FOREIGN_DATA_PERSISTENCE_PROFILE_ID = "foreign-data-persistence/v1"
REFERENCE_DATA_PROFILE_ID = "reference-data/v1"

_PROFILE_RESOURCES: dict[str, tuple[str, str]] = {
    ATTRIBUTE_ADDITION_PROFILE_ID: ("13", "profiles/attribute-addition-plan.md"),
    SYSTEM_INTERACTIONS_PROFILE_ID: ("2", "profiles/system-interactions.md"),
    SYSTEM_DESCRIPTION_PROFILE_ID: ("2", "profiles/system-description.md"),
    DATA_MODEL_PROFILE_ID: ("2", "profiles/data-model.md"),
    FOREIGN_DATA_PERSISTENCE_PROFILE_ID: ("2", "profiles/foreign-data-persistence.md"),
    REFERENCE_DATA_PROFILE_ID: ("2", "profiles/reference-data.md"),
}

@dataclass(frozen=True, slots=True)
class IntegrationRetrievalProfile:
    profile_id: str
    version: str
    content: str
    fingerprint: str

def available_profile_ids() -> tuple[str, ...]:
    return tuple(sorted(_PROFILE_RESOURCES))

def load_profile(profile_id: str) -> IntegrationRetrievalProfile:
    normalized = str(profile_id or "").strip()
    if normalized not in _PROFILE_RESOURCES:
        raise KeyError(f"unknown integration profile: {normalized}")
    version, resource_name = _PROFILE_RESOURCES[normalized]
    content = files("knowledge_integration").joinpath(resource_name).read_text(encoding="utf-8").strip()
    if not content:
        raise RuntimeError(f"packaged integration profile must not be empty: {resource_name}")
    return IntegrationRetrievalProfile(
        profile_id=normalized,
        version=version,
        content=content,
        fingerprint=sha256(content.encode("utf-8")).hexdigest(),
    )
