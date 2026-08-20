from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable

from .contracts import ReportRequest
from .knowledge_api import KnowledgeRequirement

Builder = Callable[[ReportRequest], dict[str, Any]]


SUPPORTED_PROFILE_IDS: tuple[str, ...] = (
    "system-description/v1",
    "data-model-report/v1",
    "declared-data-model-report/v1",
    "reference-data-report/v1",
    "foreign-data-persistence-report/v1",
    "workspace-interaction/v1",
    "sql-source-inventory-report/v1",
    "sql-change-analysis-report/v1",
    "workspace-sql-catalog-report/v1",
    "observed-storage-usage-report/v1",
)


@dataclass(frozen=True, slots=True)
class ReportProfile:
    profile_id: str
    builder: Builder
    resource_dir: Any
    knowledge_requirement: KnowledgeRequirement | None = None

    def text(self, name: str) -> str:
        return self.resource_dir.joinpath(name).read_text(encoding="utf-8")

    def path_hint(self) -> Path:
        return Path(str(self.resource_dir))


def _profile(
    profile_id: str,
    package: str,
    builder: Builder,
    *,
    requirement: KnowledgeRequirement | None = None,
) -> ReportProfile:
    return ReportProfile(
        profile_id=profile_id,
        builder=builder,
        resource_dir=files(package),
        knowledge_requirement=requirement,
    )


def load_profile(profile_id: str) -> ReportProfile:
    if profile_id == "system-description/v1":
        from .profiles.system_description.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.system_description.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="system-description",
                required_capabilities=("common.system-description",),
            ),
        )
    if profile_id == "data-model-report/v1":
        from .profiles.data_model_report.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.data_model_report.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="effective-data-model",
                required_capabilities=("common.effective-data-model",),
                optional_model_kinds=("physical-data-model", "logical-physical-model-mapping", "cross-artifact-data-model-mapping"),
                optional_capabilities=("common.physical-model", "common.logical-physical-mapping", "common.logical-field-physical-lineage"),
            ),
        )
    if profile_id == "declared-data-model-report/v1":
        from .profiles.declared_data_model_report.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.declared_data_model_report.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="code-declared-data-model",
                required_capabilities=("common.code-declared-data-model",),
                optional_model_kinds=("model-storage-semantics", "logical-storage-mapping"),
                optional_capabilities=("common.model-storage-semantics", "common.logical-storage-mapping"),
            ),
        )
    if profile_id == "reference-data-report/v1":
        from .profiles.reference_data.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.reference_data.v1",
            build_dataset,
            requirement=KnowledgeRequirement(required_capabilities=("common.reference-data",)),
        )
    if profile_id == "foreign-data-persistence-report/v1":
        from .profiles.foreign_data_persistence.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.foreign_data_persistence.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="persistence-lineage",
                required_capabilities=("workspace.fdp-paths", "workspace.persistence-lineage"),
            ),
        )
    if profile_id == "workspace-interaction/v1":
        from .profiles.workspace_interaction.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.workspace_interaction.v1",
            build_dataset,
            requirement=KnowledgeRequirement(required_capabilities=("workspace.system-interactions",)),
        )
    if profile_id == "sql-source-inventory-report/v1":
        from .profiles.sql_source_inventory_report.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.sql_source_inventory_report.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="sql-observed-data-usage",
                required_capabilities=("common.sql-source-inventory",),
            ),
        )
    if profile_id == "sql-change-analysis-report/v1":
        from .profiles.sql_change_analysis.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.sql_change_analysis.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                required_capabilities=(
                    "common.sql-field-calculation",
                    "common.sql-target-resolution",
                    "common.sql-attribute-insertion-context",
                    "common.sql-target-column-lineage",
                ),
            ),
        )
    if profile_id == "workspace-sql-catalog-report/v1":
        from .profiles.workspace_sql_catalog_report.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.workspace_sql_catalog_report.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="workspace-sql-catalog",
                required_capabilities=("common.workspace-sql-catalog",),
            ),
        )
    if profile_id == "observed-storage-usage-report/v1":
        from .profiles.observed_storage_usage_report.v1.builder import build_dataset
        return _profile(
            profile_id,
            "aisl_reporting.profiles.observed_storage_usage_report.v1",
            build_dataset,
            requirement=KnowledgeRequirement(
                model_kind="observed-storage-usage",
                required_capabilities=("common.observed-storage-usage",),
            ),
        )
    raise ValueError(f"unknown report profile: {profile_id}")
