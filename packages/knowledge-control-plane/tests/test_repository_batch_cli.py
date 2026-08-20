from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_control_plane.api.generic_v1.models import (
    ExecutionScope,
    KnowledgeProfileDefinition,
    ScenarioDefinition,
    ScenarioSourceMode,
)
from knowledge_control_plane.runtime.errors import RuntimeApiError
from knowledge_control_plane.runtime.repository_batch_run import (
    RepositoryBatchScenarioOptions,
    run_repository_batch_scenario,
)


class _Scenarios:
    def __init__(self, source_mode: ScenarioSourceMode = ScenarioSourceMode.REPOSITORY, *, required: bool = False) -> None:
        parameters = []
        if required:
            from knowledge_control_plane.api.generic_v1.models import ScenarioParameter
            parameters = [ScenarioParameter(name="required_input", value_type="path", required=True)]
        self.value = ScenarioDefinition(
            scenario_id="scenario-v1",
            name="Scenario",
            knowledge_profile_id="profile-v1",
            source_mode=source_mode,
            parameters=parameters,
        )

    def get(self, scenario_id: str):
        assert scenario_id == "scenario-v1"
        return self.value


class _Profiles:
    def __init__(self, scope: ExecutionScope = ExecutionScope.REPOSITORY) -> None:
        self.value = KnowledgeProfileDefinition(
            profile_id="profile-v1",
            name="Profile",
            execution_scope=scope,
            knowledge_ids=["repository-inventory"],
            fingerprint="0" * 64,
        )

    def get(self, profile_id: str):
        assert profile_id == "profile-v1"
        return self.value


class _Configuration:
    def command_parts(self, name: str) -> list[str]:
        assert name == "static_analysis_runner"
        return ["static-analysis-runner"]


def _context(tmp_path: Path, *, source_mode=ScenarioSourceMode.REPOSITORY, scope=ExecutionScope.REPOSITORY, required=False):
    return SimpleNamespace(
        scenarios=_Scenarios(source_mode, required=required),
        profiles=_Profiles(scope),
        configuration=_Configuration(),
        settings=SimpleNamespace(
            runtime_root=tmp_path / "runtime",
            default_analysis_output_root=tmp_path / "outputs",
        ),
    )


def test_high_level_batch_resolves_scenario_profile_and_pinned_contracts(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.settings.runtime_root.mkdir(parents=True)
    contracts = SimpleNamespace(
        knowledge_catalog=tmp_path / "knowledge.json",
        core_evidence_catalog=tmp_path / "core.json",
        materialization_catalog=tmp_path / "materialization.json",
    )
    for path in (contracts.knowledge_catalog, contracts.core_evidence_catalog, contracts.materialization_catalog):
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "knowledge_control_plane.runtime.repository_batch_run.discover_knowledge_contract_paths",
        lambda: contracts,
    )

    seen: dict[str, object] = {}

    class Process:
        returncode = 0
        def communicate(self):
            return (json.dumps({
                "schema_version": "repository_batch_run_summary/v1",
                "status": "completed",
                "repository_count": 3,
                "repositories_completed": 3,
                "repositories_failed": 0,
                "max_concurrent_checkouts": 1,
                "persistent_repository_checkout_count": 0,
            }), None)

    def popen(command, **kwargs):
        seen["command"] = list(command)
        seen["kwargs"] = kwargs
        profile_path = Path(command[command.index("--knowledge-profile") + 1])
        seen["profile_path"] = profile_path
        seen["profile"] = json.loads(profile_path.read_text(encoding="utf-8"))
        return Process()

    monkeypatch.setattr("knowledge_control_plane.runtime.repository_batch_run.subprocess.Popen", popen)
    result = run_repository_batch_scenario(
        context,
        RepositoryBatchScenarioOptions(
            scenario_id="scenario-v1",
            bitbucket_project_url="https://bitbucket.example/projects/ABC",
            repository_limit=3,
        ),
    )

    command = seen["command"]
    assert command[:2] == ["static-analysis-runner", "repository-batch-run"]
    assert "--bitbucket-project-url" in command
    assert "--repository-limit" in command
    assert command[command.index("--repository-limit") + 1] == "3"
    assert command[command.index("--knowledge-catalog") + 1] == str(contracts.knowledge_catalog)
    assert command[command.index("--core-evidence-catalog") + 1] == str(contracts.core_evidence_catalog)
    assert command[command.index("--materialization-catalog") + 1] == str(contracts.materialization_catalog)
    assert command[command.index("--work-dir") + 1] == str(context.settings.runtime_root / "repository-batch-work")
    assert seen["profile"] == {
        "schema_version": "knowledge_profile/v2",
        "profile_id": "profile-v1",
        "title": "Profile",
        "scope": {"kind": "repository", "scope_id": "repository-batch-template"},
        "knowledge": [{"knowledge_id": "repository-inventory"}],
        "presentation": {
            "include_coverage": True,
            "include_evidence": True,
            "include_gaps": True,
            "include_technical_details": True,
        },
    }
    assert not Path(seen["profile_path"]).exists()
    assert result["scenario_id"] == "scenario-v1"
    assert result["knowledge_profile_id"] == "profile-v1"
    assert result["repository_count"] == 3


def test_high_level_batch_rejects_workspace_scenario_before_runner(tmp_path: Path) -> None:
    context = _context(tmp_path, source_mode=ScenarioSourceMode.REPOSITORIES, scope=ExecutionScope.WORKSPACE)
    with pytest.raises(RuntimeApiError) as exc:
        run_repository_batch_scenario(
            context,
            RepositoryBatchScenarioOptions(
                scenario_id="scenario-v1",
                bitbucket_project_url="https://bitbucket.example/projects/ABC",
            ),
        )
    assert exc.value.code == "repository_batch_scenario_scope_mismatch"


def test_high_level_batch_rejects_scenario_with_required_external_inputs(tmp_path: Path) -> None:
    context = _context(tmp_path, required=True)
    with pytest.raises(RuntimeApiError) as exc:
        run_repository_batch_scenario(
            context,
            RepositoryBatchScenarioOptions(
                scenario_id="scenario-v1",
                bitbucket_project_url="https://bitbucket.example/projects/ABC",
            ),
        )
    assert exc.value.code == "repository_batch_required_inputs_unsupported"
