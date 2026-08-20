from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io_utils import stable_fingerprint

PORTFOLIO_REPOSITORY_SOURCES_SCHEMA_VERSION = "portfolio_repository_sources/v1"



def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _stable_texts(values: object, *, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f"{field_name} must be an array")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PortfolioRepositorySource:
    repo_id: str
    clone_url: str
    ref: str | None = None
    system_id: str | None = None
    project_id: str | None = None
    service_aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_id", _required_text(self.repo_id, "repo_id"))
        object.__setattr__(self, "clone_url", _required_text(self.clone_url, "clone_url"))
        object.__setattr__(self, "ref", _optional_text(self.ref))
        object.__setattr__(self, "system_id", _optional_text(self.system_id))
        object.__setattr__(self, "project_id", _optional_text(self.project_id))
        object.__setattr__(
            self,
            "service_aliases",
            _stable_texts(self.service_aliases, field_name="service_aliases"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "clone_url": self.clone_url,
            "ref": self.ref,
            "system_id": self.system_id,
            "project_id": self.project_id,
            "service_aliases": list(self.service_aliases),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortfolioRepositorySource":
        return cls(
            repo_id=str(payload.get("repo_id") or payload.get("repository_id") or ""),
            clone_url=str(payload.get("clone_url") or payload.get("repository_url") or ""),
            ref=_optional_text(payload.get("ref")),
            system_id=_optional_text(payload.get("system_id")),
            project_id=_optional_text(payload.get("project_id")),
            service_aliases=_stable_texts(
                payload.get("service_aliases"), field_name="service_aliases"
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class PortfolioRepositorySources:
    source: Mapping[str, Any]
    repositories: tuple[PortfolioRepositorySource, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", dict(self.source or {}))
        object.__setattr__(self, "repositories", tuple(self.repositories))
        if not self.repositories:
            raise ValueError("repositories must contain at least one repository")
        repo_ids = [item.repo_id for item in self.repositories]
        if len(repo_ids) != len(set(repo_ids)):
            raise ValueError("repositories must contain unique repo_id values")

    @property
    def portfolio_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "source": dict(self.source),
                "repositories": [item.to_dict() for item in self.repositories],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PORTFOLIO_REPOSITORY_SOURCES_SCHEMA_VERSION,
            "source": dict(self.source),
            "portfolio_fingerprint": self.portfolio_fingerprint,
            "repositories": [item.to_dict() for item in self.repositories],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortfolioRepositorySources":
        schema_version = payload.get("schema_version")
        if schema_version not in (None, PORTFOLIO_REPOSITORY_SOURCES_SCHEMA_VERSION):
            raise ValueError(f"unsupported schema_version: {schema_version!r}")
        rows = payload.get("repositories")
        if not isinstance(rows, list):
            raise ValueError("repositories must be an array")
        return cls(
            source=dict(payload.get("source") or {}),
            repositories=tuple(
                PortfolioRepositorySource.from_dict(item)
                for item in rows
                if isinstance(item, Mapping)
            ),
        )
