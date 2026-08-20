from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from knowledge_control_plane.api.generic_v1.models import CommandPreview, JobCreateRequest

from .configuration import ConfigurationService
from .pipeline import PipelinePlan
from .repositories import RepositoryService
from .security import environment_secret_values, redact_text
from .settings import RuntimeSettings


@dataclass(frozen=True)
class CommandSpec:
    stage: str
    argv: list[str]
    cwd: Path
    environment: dict[str, str]
    output_path: Path

    def preview(self) -> CommandPreview:
        secrets = environment_secret_values(self.environment)
        return CommandPreview(
            executable=redact_text(self.argv[0], secrets=secrets),
            arguments=[redact_text(value, secrets=secrets) for value in self.argv[1:]],
            working_directory=str(self.cwd),
            environment_names=sorted(self.environment),
            secrets_redacted=True,
        )


class CommandBuilder:
    """Build commands for the canonical knowledge execution route only."""

    def __init__(
        self,
        *,
        settings: RuntimeSettings,
        configuration: ConfigurationService,
        repositories: RepositoryService,
        **_unused,
    ) -> None:
        self.settings = settings
        self.configuration = configuration
        self.repositories = repositories

    def input_prepare(
        self,
        *,
        plan: PipelinePlan,
        request: JobCreateRequest,
        repository_paths: tuple[Path, ...] = (),
        published_revision_snapshots: tuple[Path, ...] = (),
        physical_model_path: Path | None = None,
    ) -> CommandSpec:
        argv = [
            *self.configuration.command_parts("static_analysis_runner"),
            "knowledge-input-prepare",
            "--scope-kind",
            plan.scope_kind,
            "--scope-id",
            plan.system_id,
            "--core-evidence-catalog",
            str(plan.contract_paths.core_evidence_catalog),
            "--materialization-catalog",
            str(plan.contract_paths.materialization_catalog),
            "--preparation-root",
            str(plan.root / "inputs"),
            "--producer-cache-root",
            str(self.settings.producer_artifact_root),
            "--reuse-decision-output",
            str(plan.contracts_root / "producer-reuse-preparation.json"),
            "--output",
            str(plan.input_inventory_path),
        ]
        if request.reuse_policy.value == "force_rebuild":
            argv.append("--force-rebuild")
        if len(plan.repository_ids) != len(repository_paths):
            raise ValueError("repository IDs and resolved repository paths must have the same length")
        for repository_id, repository_path in zip(plan.repository_ids, repository_paths):
            argv.extend(["--repository", str(repository_path)])
            repository = self.repositories.get(repository_id)
            metadata = {
                "source_id": repository_path.name,
                "repository_id": repository.repository_id,
                "repository_name": repository.name,
                "source_kind": repository.source_kind.value,
                "default_branch": repository.default_branch,
            }
            if repository.source_kind.value == "bitbucket":
                metadata["repository_url"] = repository.location
            argv.extend([
                "--repository-metadata-json",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ])
        selected_physical_model = physical_model_path
        if selected_physical_model is None and request.target.physical_model_path:
            selected_physical_model = Path(request.target.physical_model_path).expanduser().resolve()
        if selected_physical_model is not None:
            argv.extend(["--physical-model", str(selected_physical_model)])
        for snapshot in published_revision_snapshots:
            argv.extend(["--published-revision", str(snapshot)])
        return CommandSpec(
            stage="prepare_inputs",
            argv=argv,
            cwd=Path.cwd().resolve(),
            environment={},
            output_path=plan.contracts_root,
        )

    def execution_plan(self, *, plan: PipelinePlan) -> CommandSpec:
        argv = [
            *self.configuration.command_parts("static_analysis_runner"),
            "knowledge-execution-plan",
            "--knowledge-catalog",
            str(plan.contract_paths.knowledge_catalog),
            "--profile",
            str(plan.profile_path),
            "--input-inventory",
            str(plan.input_inventory_path),
            "--core-evidence-catalog",
            str(plan.contract_paths.core_evidence_catalog),
            "--materialization-catalog",
            str(plan.contract_paths.materialization_catalog),
            "--output",
            str(plan.execution_plan_path),
        ]
        return CommandSpec(
            stage="runner_plan",
            argv=argv,
            cwd=Path.cwd().resolve(),
            environment={},
            output_path=plan.contracts_root,
        )

    def execute(self, *, plan: PipelinePlan, request: JobCreateRequest) -> CommandSpec:
        argv = [
            *self.configuration.command_parts("static_analysis_runner"),
            "knowledge-execute",
            "--execution-plan",
            str(plan.execution_plan_path),
            "--core-evidence-catalog",
            str(plan.contract_paths.core_evidence_catalog),
            "--materialization-catalog",
            str(plan.contract_paths.materialization_catalog),
            "--output",
            str(plan.execution_root),
            "--replace",
            "--producer-cache-root",
            str(self.settings.producer_artifact_root),
        ]
        if request.reuse_policy.value == "force_rebuild":
            argv.append("--force-rebuild")
        memory = request.parameters.get("duckdb_memory_limit", "1GB")
        threads = request.parameters.get("duckdb_threads", 1)
        argv.extend(["--duckdb-memory-limit", str(memory)])
        argv.extend(["--duckdb-threads", str(threads)])
        return CommandSpec(
            stage="runner_execution",
            argv=argv,
            cwd=Path.cwd().resolve(),
            environment={},
            output_path=plan.execution_root,
        )

