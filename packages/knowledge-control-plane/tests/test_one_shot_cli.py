from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    JobStatus,
    KnowledgeProfileDefinition,
    KnowledgeRevisionInput,
    RepositoryDiscoverResponse,
    RepositorySourceKind,
    RepositoryStatus,
    RepositorySummary,
    ScenarioDefinition,
    ScenarioSourceMode,
)
from knowledge_control_plane.runtime.errors import RuntimeApiError
from knowledge_control_plane.runtime.profiles import KnowledgeProfileService
from knowledge_control_plane.runtime.scenarios import ScenarioService
from knowledge_control_plane.runtime.one_shot import (
    OneShotRunOptions,
    build_job_request,
    parse_knowledge_revision,
    parse_parameters,
    run_one_shot,
)


class _Profiles:
    def __init__(self, scope: ExecutionScope) -> None:
        self.profile = KnowledgeProfileDefinition(
            profile_id="profile-v1",
            name="Profile",
            execution_scope=scope,
            knowledge_ids=["knowledge-a"],
            fingerprint="0" * 64,
        )

    def get(self, profile_id: str) -> KnowledgeProfileDefinition:
        assert profile_id == self.profile.profile_id
        return self.profile


class _Scenarios:
    def __init__(self, source_mode: ScenarioSourceMode) -> None:
        self.scenario = ScenarioDefinition(
            scenario_id="scenario-v1",
            name="Scenario",
            knowledge_profile_id="profile-v1",
            source_mode=source_mode,
        )

    def get(self, scenario_id: str) -> ScenarioDefinition:
        assert scenario_id == self.scenario.scenario_id
        return self.scenario


class _Repositories:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def discover(self, _request):
        return RepositoryDiscoverResponse(
            repositories=[
                RepositorySummary(
                    repository_id="repo-1",
                    name=self.path.name,
                    source_kind=RepositorySourceKind.LOCAL,
                    location=str(self.path),
                    status=RepositoryStatus.AVAILABLE,
                )
            ],
            discovered_count=1,
        )


def test_build_repository_job_request_uses_scenario_and_profile(tmp_path: Path) -> None:
    context = SimpleNamespace(
        profiles=_Profiles(ExecutionScope.REPOSITORY),
        scenarios=_Scenarios(ScenarioSourceMode.REPOSITORY),
        repositories=_Repositories(tmp_path),
    )
    request = build_job_request(
        context,
        OneShotRunOptions(
            scenario_id="scenario-v1",
            system_id="system-a",
            repositories=(str(tmp_path),),
        ),
    )
    assert request.target.repository_id == "repo-1"
    assert request.target.system_id == "system-a"
    assert request.scenario_id == "scenario-v1"
    assert not hasattr(request, "knowledge_ids")
    assert not hasattr(request, "build_report")


def test_build_workspace_job_request_accepts_published_revisions(tmp_path: Path) -> None:
    context = SimpleNamespace(
        profiles=_Profiles(ExecutionScope.WORKSPACE),
        scenarios=_Scenarios(ScenarioSourceMode.KNOWLEDGE_REVISIONS),
        repositories=_Repositories(tmp_path),
    )
    request = build_job_request(
        context,
        OneShotRunOptions(
            scenario_id="scenario-v1",
            system_id="workspace-a",
            knowledge_revisions=(KnowledgeRevisionInput(system_id="source", revision_id="rev-1"),),
        ),
    )
    assert request.target.repository_id is None
    assert request.target.knowledge_revisions[0].revision_id == "rev-1"


def test_build_source_backed_workspace_job_accepts_multiple_repositories(tmp_path: Path) -> None:
    first = tmp_path / "a"; second = tmp_path / "b"
    first.mkdir(); second.mkdir()

    class Repositories:
        def discover(self, request):
            path = Path(request.roots[0]).resolve()
            return RepositoryDiscoverResponse(
                repositories=[RepositorySummary(
                    repository_id=f"repo-{path.name}",
                    name=path.name,
                    source_kind=RepositorySourceKind.LOCAL,
                    location=str(path),
                    status=RepositoryStatus.AVAILABLE,
                )],
                discovered_count=1,
            )

    context = SimpleNamespace(
        profiles=_Profiles(ExecutionScope.WORKSPACE),
        scenarios=_Scenarios(ScenarioSourceMode.REPOSITORIES),
        repositories=Repositories(),
    )
    request = build_job_request(
        context,
        OneShotRunOptions(
            scenario_id="scenario-v1",
            system_id="workspace",
            repositories=(str(first), str(second)),
        ),
    )
    assert request.target.repository_id is None
    assert request.target.repository_ids == ["repo-a", "repo-b"]
    assert request.target.knowledge_revisions == []


def test_effective_data_model_one_shot_uses_builtin_profile_repositories_and_pdm(tmp_path: Path) -> None:
    first = tmp_path / "ucp-api"
    second = tmp_path / "ucp-tsa-v4"
    first.mkdir(); second.mkdir()
    pdm = tmp_path / "ucp.pdm"
    pdm.write_text("<Model/>", encoding="utf-8")

    class Repositories:
        def discover(self, request):
            path = Path(request.roots[0]).resolve()
            return RepositoryDiscoverResponse(
                repositories=[RepositorySummary(
                    repository_id=f"repo-{path.name}",
                    name=path.name,
                    source_kind=RepositorySourceKind.LOCAL,
                    location=str(path),
                    status=RepositoryStatus.AVAILABLE,
                )],
                discovered_count=1,
            )

    context = SimpleNamespace(
        profiles=KnowledgeProfileService(),
        scenarios=ScenarioService(),
        repositories=Repositories(),
    )
    request = build_job_request(
        context,
        OneShotRunOptions(
            scenario_id="build-effective-data-model-v1",
            system_id="ucp-data-model",
            repositories=(str(first), str(second)),
            physical_model_path=str(pdm),
        ),
    )

    assert request.scenario_id == "build-effective-data-model-v1"
    assert request.knowledge_profile_id == "effective-data-model-v1"
    assert request.target.repository_ids == ["repo-ucp-api", "repo-ucp-tsa-v4"]
    assert request.target.physical_model_path == str(pdm)


def test_repository_inventory_one_shot_uses_builtin_profile(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    context = SimpleNamespace(
        profiles=KnowledgeProfileService(),
        scenarios=ScenarioService(),
        repositories=_Repositories(repo),
    )
    request = build_job_request(
        context,
        OneShotRunOptions(
            scenario_id="build-repository-inventory-v1",
            system_id="inventory-system",
            repositories=(str(repo),),
        ),
    )
    assert request.scenario_id == "build-repository-inventory-v1"
    assert request.knowledge_profile_id == "repository-inventory-v1"
    assert request.target.repository_id == "repo-1"
    assert request.target.system_id == "inventory-system"


def test_repository_scenario_rejects_missing_repository(tmp_path: Path) -> None:
    context = SimpleNamespace(
        profiles=_Profiles(ExecutionScope.REPOSITORY),
        scenarios=_Scenarios(ScenarioSourceMode.REPOSITORY),
        repositories=_Repositories(tmp_path),
    )
    with pytest.raises(RuntimeApiError, match="requires --repository"):
        build_job_request(
            context,
            OneShotRunOptions(scenario_id="scenario-v1", system_id="system-a"),
        )


def test_cli_value_parsers() -> None:
    revision = parse_knowledge_revision("system-a:rev-17")
    assert revision.system_id == "system-a"
    assert revision.revision_id == "rev-17"
    assert parse_parameters(["target_relation=T", "target_column=C"]) == {
        "target_relation": "T",
        "target_column": "C",
    }
    with pytest.raises(ValueError):
        parse_knowledge_revision("broken")
    with pytest.raises(ValueError):
        parse_parameters(["broken"])


def test_run_one_shot_starts_and_stops_same_job_manager(monkeypatch) -> None:
    result = SimpleNamespace(status=JobStatus.SUCCEEDED, job_id="job-1")

    class Jobs:
        def __init__(self) -> None:
            self.started = 0
            self.stopped = 0

        async def start(self): self.started += 1
        async def create(self, _request): return result
        def logs(self, **_kwargs): return SimpleNamespace(entries=[])
        def get(self, _job_id): return result
        async def stop(self): self.stopped += 1
        async def cancel(self, _job_id): raise AssertionError("cancel should not be called")

    jobs = Jobs()
    context = SimpleNamespace(jobs=jobs, settings=SimpleNamespace(event_poll_interval_seconds=0.001))
    monkeypatch.setattr("knowledge_control_plane.runtime.one_shot.build_job_request", lambda _context, _options: object())
    completed = asyncio.run(
        run_one_shot(context, OneShotRunOptions(scenario_id="scenario-v1", system_id="system-a"))
    )
    assert completed is result
    assert jobs.started == 1
    assert jobs.stopped == 1
