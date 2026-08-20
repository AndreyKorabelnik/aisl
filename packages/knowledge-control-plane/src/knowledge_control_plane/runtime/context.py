from __future__ import annotations

from dataclasses import dataclass

from .artifacts import ArtifactRegistry
from .commands import CommandBuilder
from .configuration import ConfigurationService
from .diagnostics import DiagnosticsService
from .jobs import JobManager
from .knowledge_products import KnowledgeProductCatalogService
from .knowledge_api_client import KnowledgeApiClientSettings, KnowledgeApiHttpClient
from .output_safety import OutputSafety
from .pipeline import PipelinePlanner
from .process import ProcessExecutor
from .production_structure import ProductionStructureService
from .productions import ProductionService
from .freshness import FreshnessService
from .profiles import KnowledgeProfileService
from .scenarios import ScenarioService
from .repositories import RepositoryService
from .settings import RuntimeSettings
from .store import RuntimeStore
from .workspaces import WorkspaceService


@dataclass
class RuntimeContext:
    settings: RuntimeSettings
    store: RuntimeStore
    configuration: ConfigurationService
    repositories: RepositoryService
    workspaces: WorkspaceService
    profiles: KnowledgeProfileService
    scenarios: ScenarioService
    knowledge_products: KnowledgeProductCatalogService
    output_safety: OutputSafety
    artifacts: ArtifactRegistry
    knowledge_api: KnowledgeApiHttpClient
    executor: ProcessExecutor
    command_builder: CommandBuilder
    pipeline_planner: PipelinePlanner
    jobs: JobManager
    diagnostics: DiagnosticsService
    production_structure: ProductionStructureService
    productions: ProductionService
    freshness: FreshnessService


def build_runtime_context(settings: RuntimeSettings) -> RuntimeContext:
    settings.ensure_directories()
    store = RuntimeStore(settings.database_path)
    configuration = ConfigurationService(store, settings)
    repositories = RepositoryService(store, settings)
    workspaces = WorkspaceService(store, repositories)
    scenarios = ScenarioService()
    knowledge_products = KnowledgeProductCatalogService()
    profiles = KnowledgeProfileService(store=store, products=knowledge_products, configuration=configuration, settings=settings)
    output_safety = OutputSafety(configuration)
    artifacts = ArtifactRegistry(store)
    knowledge_api = KnowledgeApiHttpClient(
        KnowledgeApiClientSettings(
            base_url=settings.knowledge_api_base_url,
            timeout_seconds=settings.knowledge_api_timeout_seconds,
        )
    )
    executor = ProcessExecutor()
    command_builder = CommandBuilder(settings=settings, configuration=configuration, repositories=repositories)
    pipeline_planner = PipelinePlanner(
        profiles=profiles,
        scenarios=scenarios,
        repositories=repositories,
        workspaces=workspaces,
        output_safety=output_safety,
        artifacts=artifacts,
    )
    jobs = JobManager(
        settings=settings,
        store=store,
        command_builder=command_builder,
        executor=executor,
        artifacts=artifacts,
        repositories=repositories,
        pipeline_planner=pipeline_planner,
        knowledge_api=knowledge_api,
    )
    production_structure = ProductionStructureService(jobs=jobs, artifacts=artifacts)
    productions = ProductionService(
        store=store,
        repositories=repositories,
        profiles=profiles,
        scenarios=scenarios,
    )
    freshness = FreshnessService(
        store=store,
        productions=productions,
        repositories=repositories,
        jobs=jobs,
    )
    diagnostics = DiagnosticsService(
        settings=settings,
        store=store,
        configuration=configuration,
        artifacts=artifacts,
        knowledge_api=knowledge_api,
    )
    return RuntimeContext(
        settings=settings,
        store=store,
        configuration=configuration,
        repositories=repositories,
        workspaces=workspaces,
        profiles=profiles,
        scenarios=scenarios,
        knowledge_products=knowledge_products,
        output_safety=output_safety,
        artifacts=artifacts,
        knowledge_api=knowledge_api,
        executor=executor,
        command_builder=command_builder,
        pipeline_planner=pipeline_planner,
        jobs=jobs,
        diagnostics=diagnostics,
        production_structure=production_structure,
        productions=productions,
        freshness=freshness,
    )
