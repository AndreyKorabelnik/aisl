from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    JobCreateRequest,
    JobKind,
    JobStage,
    ScenarioSourceMode,
    StageProgressMode,
)

from .artifacts import ArtifactRegistry
from .knowledge_contracts import (
    KnowledgeContractPaths,
    build_knowledge_profile_payload,
    discover_knowledge_contract_paths,
)
from .output_safety import OutputSafety
from .profiles import KnowledgeProfileService
from .repositories import RepositoryService
from .scenarios import ScenarioService
from .workspaces import WorkspaceService


PIPELINE_STAGE_ORDER = (
    "checkout",
    "prepare_inputs",
    "runner_plan",
    "runner_execution",
    "bundle",
)


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    root: Path
    contracts_root: Path
    physical_input_root: Path
    knowledge_input_root: Path
    execution_root: Path
    profile_path: Path
    input_inventory_path: Path
    execution_plan_path: Path
    execution_result_path: Path
    scenario_id: str
    knowledge_profile_id: str
    knowledge_ids: tuple[str, ...]
    system_id: str
    scope_kind: str
    source_mode: str
    repository_ids: tuple[str, ...]
    assistant_profile_id: str | None
    contract_paths: KnowledgeContractPaths


class PipelinePlanner:
    """Compile control-plane Scenario + Context into one Runner execution request.

    Knowledge Control Plane owns user workflow only. Knowledge composition lives in a reusable
    KnowledgeProfileDefinition; source/consumer guidance lives in ScenarioDefinition;
    Runner owns validation, dependency resolution and the execution DAG.
    """

    def __init__(
        self,
        *,
        profiles: KnowledgeProfileService,
        scenarios: ScenarioService,
        repositories: RepositoryService,
        workspaces: WorkspaceService,
        output_safety: OutputSafety,
        artifacts: ArtifactRegistry,
    ) -> None:
        self.profiles = profiles
        self.scenarios = scenarios
        self.repositories = repositories
        self.workspaces = workspaces
        self.output_safety = output_safety
        self.artifacts = artifacts

    def stages(self, request: JobCreateRequest) -> list[JobStage]:
        scenario = self.scenarios.get(request.scenario_id)
        stages: list[JobStage] = []
        if scenario.source_mode in {ScenarioSourceMode.REPOSITORY, ScenarioSourceMode.REPOSITORIES}:
            stages.append(
                JobStage(
                    stage_id="checkout",
                    name="Подготовка репозитория",
                    description="Проверка или загрузка выбранной ревизии исходников",
                    progress_mode=StageProgressMode.INDETERMINATE,
                )
            )
        stages.extend([
            JobStage(
                stage_id="prepare_inputs",
                name="Подготовка входов",
                description="Формирование immutable Knowledge Profile snapshot и декларативного context",
                progress_mode=StageProgressMode.INDETERMINATE,
            ),
            JobStage(
                stage_id="runner_plan",
                name="Построение плана Runner",
                description="Runner валидирует профиль, нормализует входы и компилирует execution DAG",
                progress_mode=StageProgressMode.INDETERMINATE,
            ),
            JobStage(
                stage_id="runner_execution",
                name="Выполнение Runner",
                description="Runner выполняет канонический Producer plan и публикует Prepared Knowledge artifacts",
                progress_mode=StageProgressMode.INDETERMINATE,
            ),
            JobStage(
                stage_id="bundle",
                name="Подготовка AISL bundle",
                description="Формирование переносимого self-contained bundle для последующей публикации на AISL Server",
                progress_mode=StageProgressMode.INDETERMINATE,
            ),
        ])
        return stages

    def build(
        self,
        *,
        job_id: str,
        request: JobCreateRequest,
        preview: bool = False,
        created_at: datetime | None = None,
    ) -> PipelinePlan:
        if request.kind is not JobKind.KNOWLEDGE_EXECUTION:
            raise ValueError("PipelinePlanner supports only knowledge_execution")
        scenario = self.scenarios.get(request.scenario_id)
        pinned_source_ids = {item.source_id for item in request.source_snapshots}

        def selected_repository_path(repository_id: str) -> Path:
            if repository_id in pinned_source_ids:
                return self.repositories.pinned_execution_path(repository_id, job_id=job_id)
            return (
                self.repositories.planned_execution_path(repository_id)
                if preview
                else self.repositories.execution_path(repository_id)
            )
        profile = self.profiles.get(request.knowledge_profile_id or scenario.knowledge_profile_id)
        scenario_default_profile = profile.profile_id == scenario.knowledge_profile_id
        if scenario_default_profile:
            for parameter in scenario.parameters:
                if parameter.name == "physical_model_path":
                    continue
                value = request.parameters.get(parameter.name, parameter.default)
                if parameter.required and (value is None or not str(value).strip()):
                    raise ValueError(f"scenario parameter is required: {parameter.name}")
        repository_paths: list[Path] = []
        repository_ids: list[str] = []
        if scenario.source_mode is ScenarioSourceMode.REPOSITORY:
            if profile.execution_scope is not ExecutionScope.REPOSITORY:
                raise ValueError("repository scenario requires repository-scoped Knowledge Profile")
            if not request.target.repository_id:
                raise ValueError("repository scenario requires repository_id")
            if request.target.repository_ids or request.target.knowledge_revisions:
                raise ValueError("repository scenario accepts only repository_id")
            repository_ids = [request.target.repository_id]
            repository = self.repositories.get(request.target.repository_id)
            repository_paths = [selected_repository_path(repository.repository_id)]
        elif scenario.source_mode is ScenarioSourceMode.REPOSITORIES:
            if profile.execution_scope is not ExecutionScope.WORKSPACE:
                raise ValueError("repositories scenario requires workspace-scoped Knowledge Profile")
            if request.target.repository_id or request.target.knowledge_revisions:
                raise ValueError("workspace repository scenario accepts only repository_ids")
            if not request.target.repository_ids:
                raise ValueError("workspace repository scenario requires repository_ids")
            repository_ids = list(request.target.repository_ids)
            for repository_id in repository_ids:
                repository = self.repositories.get(repository_id)
                repository_paths.append(selected_repository_path(repository.repository_id))
        elif scenario.source_mode is ScenarioSourceMode.KNOWLEDGE_REVISIONS:
            if profile.execution_scope is not ExecutionScope.WORKSPACE:
                raise ValueError("knowledge-revisions scenario requires workspace-scoped Knowledge Profile")
            if request.target.repository_id or request.target.repository_ids:
                raise ValueError("knowledge-revisions scenario does not accept repositories")
            if not request.target.knowledge_revisions:
                raise ValueError("knowledge-revisions scenario requires existing knowledge revisions")
        else:  # pragma: no cover
            raise ValueError(f"unsupported scenario source mode: {scenario.source_mode}")

        resolver = self.output_safety.preview if preview else self.output_safety.resolve
        root = resolver(
            job_id=job_id,
            kind=JobKind.KNOWLEDGE_EXECUTION,
            options=request.output,
            protected_paths=repository_paths,
            system_id=request.target.system_id,
            scenario_id=request.scenario_id,
            created_at=created_at,
        )
        contracts_root = root / "contracts"
        return PipelinePlan(
            root=root,
            contracts_root=contracts_root,
            physical_input_root=root / "inputs" / "physical-model",
            knowledge_input_root=root / "inputs" / "knowledge-artifacts",
            execution_root=root / "knowledge-execution",
            profile_path=contracts_root / "knowledge-profile.json",
            input_inventory_path=contracts_root / "knowledge-input-inventory.json",
            execution_plan_path=contracts_root / "knowledge-execution-plan.json",
            execution_result_path=root / "knowledge-execution" / "knowledge_execution_result.json",
            scenario_id=scenario.scenario_id,
            knowledge_profile_id=profile.profile_id,
            knowledge_ids=tuple(profile.knowledge_ids),
            system_id=request.target.system_id,
            scope_kind=profile.execution_scope.value,
            source_mode=scenario.source_mode.value,
            repository_ids=tuple(repository_ids),
            assistant_profile_id=scenario.assistant_profile_id if scenario_default_profile else None,
            contract_paths=discover_knowledge_contract_paths(),
        )

    def materialize_profile(self, plan: PipelinePlan, request: JobCreateRequest) -> Path:
        profile = self.profiles.get(plan.knowledge_profile_id)
        payload = build_knowledge_profile_payload(request=request, profile=profile)
        plan.profile_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        plan.profile_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return plan.profile_path
