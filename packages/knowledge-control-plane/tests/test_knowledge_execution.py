from __future__ import annotations

import hashlib
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from knowledge_control_plane.api.generic_v1.models import (
    ArtifactKind,
    ExecutionScope,
    JobCreateRequest,
    JobKind,
    JobTarget,
    KnowledgeRevisionInput,
    RepositoryDiscoverRequest,
    RepositorySourceKind,
    RepositoryStatus,
    RepositorySummary,
    ScenarioSourceMode,
)
from knowledge_control_plane.runtime.app import create_runtime_app
from knowledge_control_plane.runtime.artifacts import ArtifactRegistry
from knowledge_control_plane.runtime.context import build_runtime_context
from knowledge_control_plane.runtime.knowledge_contracts import discover_knowledge_contract_paths
from knowledge_control_plane.runtime.profiles import KnowledgeProfileService
from knowledge_control_plane.runtime.scenarios import ScenarioService
from knowledge_control_plane.runtime.settings import RuntimeSettings
from knowledge_control_plane.runtime.store import RuntimeStore


def _settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "runtime.sqlite3",
        jobs_root=tmp_path / "runtime" / "jobs",
        default_analysis_output_root=tmp_path / "outputs",
        knowledge_api_proxy_enabled=False,
    )


def _repository(context, tmp_path: Path, name: str) -> str:
    root = tmp_path / name
    root.mkdir()
    return context.repositories.discover(
        RepositoryDiscoverRequest(roots=[str(root)])
    ).repositories[0].repository_id





def test_bitbucket_repository_url_is_forwarded_as_runner_source_metadata(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    materialized = tmp_path / "checked-out-bitbucket"
    materialized.mkdir()
    (materialized / "pom.xml").write_text("<project/>", encoding="utf-8")
    repository = RepositorySummary(
        repository_id="bitbucket-profile-api",
        name="profile-api",
        source_kind=RepositorySourceKind.BITBUCKET,
        location="https://bitbucket.example/scm/team/profile-api.git",
        status=RepositoryStatus.AVAILABLE,
        default_branch="main",
        metadata={"materialized_path": str(materialized), "analysis_repository_id": "profile_api"},
    )
    context.repositories.store.upsert_repository(repository)
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository.repository_id], system_id="profile-system"),
        scenario_id="build-data-model-v1",
    )
    preview = context.jobs.preview(request)
    inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
    assert "--repository-metadata-json" in inventory
    assert "https://bitbucket.example/scm/team/profile-api.git" in inventory
    assert "repository_url" in inventory
    assert "source_kind" in inventory and "bitbucket" in inventory

def test_default_analysis_output_is_grouped_by_system_and_scenario(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "repo-layout")
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository_id], system_id="ucp-data-model"),
        scenario_id="build-data-model-v1",
    )
    created_at = datetime(2026, 8, 13, 7, 42, 31, tzinfo=timezone.utc)
    plan = context.pipeline_planner.build(
        job_id="job-a83f12c9deadbeef",
        request=request,
        preview=True,
        created_at=created_at,
    )
    expected = (
        tmp_path
        / "outputs"
        / "ucp-data-model"
        / "build-data-model-v1"
        / "2026-08-13T07-42-31Z__job-a83f12c9"
    ).resolve()
    assert plan.root == expected


def test_explicit_analysis_output_path_is_preserved(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "repo-explicit-output")
    explicit = tmp_path / "outputs" / "manual-name"
    request = JobCreateRequest.model_validate(
        {
            "target": {"repository_ids": [repository_id], "system_id": "system"},
            "scenario_id": "build-data-model-v1",
            "output": {"output_path": str(explicit)},
        }
    )
    plan = context.pipeline_planner.build(
        job_id="job-0123456789abcdef",
        request=request,
        preview=True,
        created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    assert plan.root == explicit.resolve()


def test_run_info_receipt_is_human_readable_and_not_identity(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    output = tmp_path / "outputs" / "system" / "scenario" / "run"
    output.mkdir(parents=True)
    created_at = datetime(2026, 8, 13, 7, 42, 31, tzinfo=timezone.utc)
    path = context.pipeline_planner.output_safety.write_run_info(
        output,
        job_id="job-a83f12c9deadbeef",
        system_id="ucp-data-model",
        scenario_id="build-effective-data-model-v1",
        display_name="UCP Data Model",
        created_at=created_at,
        started_at=created_at,
        finished_at=None,
        status="running",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "RUN_INFO.json"
    assert payload["schema_version"] == "knowledge_control_plane_run_info/v1"
    assert payload["job_id"] == "job-a83f12c9deadbeef"
    assert payload["system_id"] == "ucp-data-model"
    assert payload["scenario_id"] == "build-effective-data-model-v1"
    assert payload["status"] == "running"


def test_public_job_contract_accepts_scenario_not_profile_override() -> None:
    request = JobCreateRequest(
        target=JobTarget(repository_ids=["repo"], system_id="system"),
        scenario_id="build-data-model-v1",
    )
    assert request.kind is JobKind.KNOWLEDGE_EXECUTION
    assert request.scenario_id == "build-data-model-v1"
    assert not hasattr(request, "knowledge_ids")
    assert not hasattr(request, "report_profile")
    with pytest.raises(ValidationError):
        JobCreateRequest.model_validate(
            {
                "kind": "full_pipeline",
                "target": {"repository_id": "repo", "system_id": "system"},
                "scenario_id": "build-data-model-v1",
            }
        )


def test_profile_and_scenario_are_separate_contracts() -> None:
    profiles = KnowledgeProfileService()
    scenarios = ScenarioService()
    profile = profiles.get("data-model-v1")
    scenario = scenarios.get("build-data-model-v1")

    assert profile.execution_scope is ExecutionScope.WORKSPACE
    assert profile.knowledge_ids == ["code-declared-data-model"]
    for foreign_field in (
        "source_mode",
        "report_profile",
        "assistant_profile_id",
        "parameters",
        "supported_audiences",
        "supported_detail_levels",
    ):
        assert not hasattr(profile, foreign_field)

    assert scenario.knowledge_profile_id == profile.profile_id
    assert scenario.source_mode is ScenarioSourceMode.REPOSITORIES
    assert scenario.assistant_profile_id == "data-model/v1"
    assert not hasattr(scenario, "report_profile")
    assert not hasattr(scenario, "knowledge_ids")
    assert not hasattr(scenario, "execution_scope")
    assert not hasattr(scenario, "analysis_purposes")
    assert not hasattr(scenario, "requires_llm")


def test_effective_data_model_profile_and_scenario_are_builtin() -> None:
    profiles = KnowledgeProfileService()
    scenarios = ScenarioService()
    profile = profiles.get("effective-data-model-v1")
    scenario = scenarios.get("build-effective-data-model-v1")

    assert profile.execution_scope is ExecutionScope.WORKSPACE
    assert profile.knowledge_ids == ["effective-data-model"]
    assert scenario.knowledge_profile_id == profile.profile_id
    assert scenario.source_mode is ScenarioSourceMode.REPOSITORIES
    assert {item.name for item in scenario.parameters if item.required} == {"physical_model_path"}


def test_two_scenarios_can_reuse_one_knowledge_profile() -> None:
    scenarios = ScenarioService()
    source = scenarios.get("analyze-sql-source-inventory-v1")
    change = scenarios.get("analyze-sql-change-v1")
    assert source.knowledge_profile_id == "sql-source-inventory-v1"
    assert change.knowledge_profile_id == "sql-source-inventory-v1"
    assert not hasattr(source, "report_profile")
    assert not hasattr(change, "report_profile")
    assert {item.name for item in change.parameters if item.required} == {
        "target_relation",
        "target_column",
    }


def test_s2t_reconstruction_profile_and_scenario_use_only_datamart_sql_and_pdm() -> None:
    profiles = KnowledgeProfileService()
    scenarios = ScenarioService()
    profile = profiles.get("s2t-reconstruction-v1")
    scenario = scenarios.get("reconstruct-s2t-v1")

    assert profile.execution_scope is ExecutionScope.REPOSITORY
    assert profile.knowledge_ids == ["sql-source-inventory", "physical-data-model"]
    assert scenario.knowledge_profile_id == profile.profile_id
    assert scenario.source_mode is ScenarioSourceMode.REPOSITORY
    assert {item.name for item in scenario.parameters if item.required} == {"physical_model_path"}
    assert all("ucp" not in value.casefold() for value in [profile.profile_id, profile.description or "", scenario.scenario_id, scenario.description or ""])


def test_s2t_reconstruction_preview_passes_one_repository_and_pdm_to_runner(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "datamart-profile-fl")
    pdm = tmp_path / "model.pdm"
    pdm.write_text("<?xml version='1.0'?><Model/>", encoding="utf-8")
    request = JobCreateRequest(
        target=JobTarget(repository_id=repository_id, system_id="profile-fl-s2t", physical_model_path=str(pdm)),
        scenario_id="reconstruct-s2t-v1",
    )
    preview = context.jobs.preview(request)
    inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
    assert shlex.split(inventory).count("--repository") == 1
    assert "--physical-model" in inventory
    assert "ucp" not in inventory.casefold()
    plan = context.pipeline_planner.build(job_id="s2t-preview", request=request, preview=True)
    assert plan.knowledge_profile_id == "s2t-reconstruction-v1"
    assert plan.knowledge_ids == ("sql-source-inventory", "physical-data-model")


def test_contract_discovery_uses_current_generic_catalogs() -> None:
    paths = discover_knowledge_contract_paths()
    core = json.loads(paths.core_evidence_catalog.read_text())
    knowledge = json.loads(paths.knowledge_catalog.read_text())
    materializations = json.loads(paths.materialization_catalog.read_text())
    assert core["schema_version"] == "core_evidence_contract_catalog/v1"
    assert knowledge["schema_version"] == "knowledge_catalog/v2"
    assert materializations["schema_version"] == "knowledge_materialization_catalog/v3"
    assert materializations["klc_version"] == "0.61.0a39"
    assert knowledge["runner_version"] == "0.10.28"
    assert core["core_version"] == "0.44.23a7"
    assert knowledge["source"]["core_evidence_contract_catalog_fingerprint"] == core["catalog_fingerprint"]
    assert knowledge["source"]["klc_materialization_catalog_fingerprint"] == materializations["catalog_fingerprint"]
    data_model = next(item for item in knowledge["knowledge_types"] if item["knowledge_id"] == "code-declared-data-model")
    assert data_model["optional_internal_materializations"] == ["logical-storage-mapping"]


def test_bundled_runtime_contract_manifest_matches_catalogs() -> None:
    import knowledge_control_plane.runtime.knowledge_contracts as contracts

    root = Path(contracts.__file__).resolve().parents[1] / "resources" / "runtime_contracts"
    manifest = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "knowledge_control_plane_runtime_contract_bundle/v2"
    assert manifest["framework_baseline"] == {
        "code_analyzer_core": "0.44.23a7",
        "static_analysis_runner": "0.10.28",
        "knowledge_layer_core": "0.61.0a39",
    }
    for entry in manifest["catalogs"].values():
        target = root / entry["file"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]


def test_openapi_exposes_profiles_and_scenarios_as_distinct_resources(tmp_path: Path) -> None:
    app = create_runtime_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/knowledge-profiles" in paths
        assert "/api/v1/knowledge-profiles/{profile_id}" in paths
        assert "/api/v1/scenarios" in paths
        assert "/api/v1/scenarios/{scenario_id}" in paths
        assert "/api/v1/jobs" in paths
        assert "/api/v1/profiles" not in paths


def test_artifact_registry_classifies_execution_contracts(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    registry = ArtifactRegistry(store)
    cases = {
        "knowledge-profile.json": ArtifactKind.KNOWLEDGE_PROFILE,
        "external-physical-model.json": ArtifactKind.TYPED_INPUT_DESCRIPTOR,
        "knowledge-input-inventory.json": ArtifactKind.INPUT_INVENTORY,
        "knowledge-execution-plan.json": ArtifactKind.EXECUTION_PLAN,
        "knowledge_execution_result.json": ArtifactKind.EXECUTION_RESULT,
        "materializations/model.duckdb": ArtifactKind.KNOWLEDGE_ARTIFACT,
    }
    for relative, expected in cases.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        assert registry._classify(path, relative) is expected


def test_output_safety_uses_analysis_root_for_scenario_preview(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "repository")
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository_id], system_id="system"),
        scenario_id="build-data-model-v1",
    )
    preview = context.jobs.preview(request)
    assert str(context.settings.default_analysis_output_root) in preview.model_dump_json()


def test_knowledge_control_plane_has_no_direct_core_or_descriptor_materializers() -> None:
    from knowledge_control_plane.runtime import knowledge_contracts
    from knowledge_control_plane.runtime.commands import CommandBuilder

    assert not hasattr(knowledge_contracts, "materialize_physical_model_descriptor")
    assert not hasattr(knowledge_contracts, "materialize_knowledge_artifact_descriptor")
    assert not hasattr(CommandBuilder, "physical_model")


def test_fdp_profile_and_scenario_have_single_owners() -> None:
    profile = KnowledgeProfileService().get("foreign-data-persistence-v1")
    scenario = ScenarioService().get("analyze-foreign-data-persistence-v1")
    assert profile.execution_scope is ExecutionScope.REPOSITORY
    assert profile.knowledge_ids == ["persistence-lineage"]
    assert scenario.knowledge_profile_id == profile.profile_id
    assert scenario.source_mode is ScenarioSourceMode.REPOSITORY
    assert not hasattr(scenario, "report_profile")
    assert scenario.assistant_profile_id == "foreign-data-persistence/v1"


def test_workspace_revision_scenario_preview_has_no_checkout_or_internal_producer_stage(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    request = JobCreateRequest(
        target=JobTarget(
            system_id="workspace",
            knowledge_revisions=[
                KnowledgeRevisionInput(system_id="a", revision_id="rev-a"),
                KnowledgeRevisionInput(system_id="b", revision_id="rev-b"),
            ],
        ),
        scenario_id="compose-workspace-sql-catalog-v1",
    )
    preview = context.jobs.preview(request)
    lines = [item.command_line for item in preview.commands]
    assert not any("git clone" in line or " checkout " in line for line in lines)
    inventory = next(line for line in lines if "knowledge-input-prepare" in line)
    assert "--scope-kind workspace" in inventory
    assert inventory.count("--published-revision") == 2
    assert "--repository" not in inventory
    stages = context.pipeline_planner.stages(request)
    assert [item.stage_id for item in stages] == [
        "prepare_inputs",
        "runner_plan",
        "runner_execution",
        "bundle",
    ]


def test_sql_change_parameters_belong_to_scenario_without_presentation_semantics(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "repo")
    request = JobCreateRequest(
        target=JobTarget(repository_id=repository_id, system_id="system"),
        scenario_id="analyze-sql-change-v1",
        parameters={"target_relation": "dm.customer", "target_column": "segment_cd"},
    )
    plan = context.pipeline_planner.build(job_id="preview-sql-change", request=request, preview=True)
    assert plan.knowledge_profile_id == "sql-source-inventory-v1"
    assert not hasattr(plan, "report_profile")
    assert not hasattr(plan, "report_focus")
    scenario = context.pipeline_planner.scenarios.get("analyze-sql-change-v1")
    assert {item.name for item in scenario.parameters} >= {"target_relation", "target_column"}

def test_source_backed_workspace_preview_passes_all_repositories_to_runner(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_ids = [_repository(context, tmp_path, name) for name in ("system-a", "system-b")]
    request = JobCreateRequest(
        target=JobTarget(repository_ids=repository_ids, system_id="interaction-workspace"),
        scenario_id="analyze-system-interactions-v1",
    )
    preview = context.jobs.preview(request)
    inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
    assert "--scope-kind workspace" in inventory
    assert shlex.split(inventory).count("--repository") == 2
    assert all(str(context.repositories.planned_execution_path(repo_id)) in inventory for repo_id in repository_ids)
    stages = [item.stage_id for item in context.pipeline_planner.stages(request)]
    assert "checkout" in stages
    assert "runner_execution" in stages
    assert "core_evidence" not in stages
    assert "knowledge_materialization" not in stages


def test_data_model_extension_preview_uses_scenario_context_and_profile_composition(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_ids = [_repository(context, tmp_path, name) for name in ("ucp-model", "ucp-tsa", "datamart")]
    pdm = tmp_path / "model.pdm"
    pdm.write_text("<?xml version='1.0'?><Model/>", encoding="utf-8")
    request = JobCreateRequest(
        target=JobTarget(
            repository_ids=repository_ids,
            system_id="data-model-extension-workspace",
            physical_model_path=str(pdm),
        ),
        scenario_id="extend-data-model-attribute-v1",
    )
    preview = context.jobs.preview(request)
    inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
    assert shlex.split(inventory).count("--repository") == 3
    assert "--physical-model" in inventory
    assert not any("analyze-physical-model" in item.command_line for item in preview.commands)
    plan = context.pipeline_planner.build(job_id="extension-preview", request=request, preview=True)
    assert plan.knowledge_profile_id == "data-model-attribute-extension-v1"
    assert plan.knowledge_ids == ("data-model-attribute-extension",)
    assert plan.assistant_profile_id == "attribute-addition-plan/v1"


def test_job_target_rejects_mixed_source_modes() -> None:
    with pytest.raises(ValidationError):
        JobTarget(repository_id="a", repository_ids=["b"], system_id="system")
    with pytest.raises(ValidationError):
        JobTarget(
            repository_ids=["a"],
            system_id="system",
            knowledge_revisions=[{"system_id": "s", "revision_id": "r"}],
        )
    with pytest.raises(ValidationError):
        JobTarget(repository_ids=["a", "a"], system_id="system")


def test_default_configuration_exposes_runner_not_core(tmp_path: Path) -> None:
    from knowledge_control_plane.runtime.configuration import ConfigurationService

    service = ConfigurationService(RuntimeStore(tmp_path / "runtime.sqlite3"), _settings(tmp_path))
    commands = service.get().commands
    assert commands.static_analysis_runner == "static-analysis-runner"
    assert not hasattr(commands, "code_analyzer_core")


def test_system_description_scenario_uses_profile_without_reporting_stage(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "client-profile")
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository_id], system_id="client-profile"),
        scenario_id="describe-system-v1",
    )
    preview = context.jobs.preview(request)
    inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
    assert "--scope-kind workspace" in inventory
    assert shlex.split(inventory).count("--repository") == 1
    assert all(item.stage != "report_build" for item in preview.commands)
    scenario = context.pipeline_planner.scenarios.get("describe-system-v1")
    profile = context.pipeline_planner.profiles.get(scenario.knowledge_profile_id)
    assert scenario.assistant_profile_id == "system-description/v1"
    assert not hasattr(scenario, "report_profile")
    assert profile.knowledge_ids == ["system-description"]

def test_data_model_scenario_uses_same_exact_profile_for_one_or_many_repositories(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_ids = [_repository(context, tmp_path, name) for name in ("repo-a", "repo-b")]
    for selected in (repository_ids[:1], repository_ids):
        request = JobCreateRequest(
            target=JobTarget(repository_ids=selected, system_id="code-model-workspace"),
            scenario_id="build-data-model-v1",
            )
        preview = context.jobs.preview(request)
        inventory = next(item.command_line for item in preview.commands if "knowledge-input-prepare" in item.command_line)
        assert shlex.split(inventory).count("--repository") == len(selected)
        assert "physical-model" not in inventory
        plan = context.pipeline_planner.build(job_id=f"preview-{len(selected)}", request=request, preview=True)
        assert plan.knowledge_profile_id == "data-model-v1"
        assert plan.knowledge_ids == ("code-declared-data-model",)


def test_reference_data_profile_and_scenario_are_separate() -> None:
    profile = KnowledgeProfileService().get("reference-data-v1")
    scenario = ScenarioService().get("build-reference-data-v1")
    assert profile.execution_scope is ExecutionScope.WORKSPACE
    assert profile.knowledge_ids == ["reference-data"]
    assert scenario.source_mode is ScenarioSourceMode.REPOSITORIES
    assert not hasattr(scenario, "report_profile")
    assert scenario.assistant_profile_id == "reference-data/v1"


def test_control_plane_stage_model_does_not_reimplement_runner_internals(tmp_path: Path) -> None:
    context = build_runtime_context(_settings(tmp_path))
    repository_id = _repository(context, tmp_path, "repo")
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository_id], system_id="system"),
        scenario_id="build-data-model-v1",
    )
    stage_ids = [item.stage_id for item in context.pipeline_planner.stages(request)]
    assert stage_ids == [
        "checkout",
        "prepare_inputs",
        "runner_plan",
        "runner_execution",
        "bundle",
    ]
    assert not {"compile_plan", "core_evidence", "knowledge_materialization"} & set(stage_ids)
    preview = context.jobs.preview(request)
    assert {item.stage for item in preview.commands} >= {"prepare_inputs", "runner_plan", "runner_execution"}


def test_user_profile_registry_is_persistent_and_runner_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from knowledge_control_plane.api.generic_v1.models import KnowledgeProfileCreateRequest, KnowledgeProfileCopyRequest, KnowledgeProfileOrigin, KnowledgeProfileUpdateRequest

    context = build_runtime_context(_settings(tmp_path))
    monkeypatch.setattr(
        context.configuration,
        "command_parts",
        lambda name: [sys.executable, "-m", "static_analysis_runner"] if name == "static_analysis_runner" else [name],
    )
    created = context.profiles.create(KnowledgeProfileCreateRequest(
        profile_id="my-data-model",
        name="My Data Model",
        execution_scope=ExecutionScope.WORKSPACE,
        knowledge_ids=["code-declared-data-model"],
    ))
    assert created.origin is KnowledgeProfileOrigin.USER
    assert context.profiles.get(created.profile_id).fingerprint == created.fingerprint
    resolution = context.profiles.resolve(created.profile_id)
    assert resolution.valid
    assert resolution.resolved_knowledge_ids == ["code-declared-data-model"]

    updated = context.profiles.update(created.profile_id, KnowledgeProfileUpdateRequest(
        expected_fingerprint=created.fingerprint,
        name="My Data Model v2",
        knowledge_ids=["data-model-attribute-extension"],
    ))
    assert updated.fingerprint != created.fingerprint
    assert "code-declared-data-model" in context.profiles.resolve(updated.profile_id).implicit_dependency_ids

    copied = context.profiles.copy(updated.profile_id, KnowledgeProfileCopyRequest(profile_id="my-data-model-copy"))
    assert copied.origin is KnowledgeProfileOrigin.USER
    assert copied.knowledge_ids == updated.knowledge_ids
    context.profiles.delete(copied.profile_id)
    with pytest.raises(Exception):
        context.profiles.get(copied.profile_id)

    reloaded = build_runtime_context(_settings(tmp_path)).profiles.get(updated.profile_id)
    assert reloaded.name == "My Data Model v2"


def test_platform_profile_is_read_only_and_custom_profile_runs_through_same_planner(tmp_path: Path) -> None:
    from knowledge_control_plane.api.generic_v1.models import KnowledgeProfileDefinition, KnowledgeProfileOrigin

    context = build_runtime_context(_settings(tmp_path))
    profile = KnowledgeProfileDefinition(
        profile_id="custom-workspace-profile",
        name="Custom Workspace",
        execution_scope=ExecutionScope.WORKSPACE,
        origin=KnowledgeProfileOrigin.USER,
        version="v1",
        source_path="test",
        knowledge_ids=["code-declared-data-model"],
        fingerprint="0" * 64,
    )
    context.store.upsert_knowledge_profile(profile)
    repository_id = _repository(context, tmp_path, "custom-repo")
    request = JobCreateRequest(
        target=JobTarget(repository_ids=[repository_id], system_id="system"),
        scenario_id="build-data-model-v1",
        knowledge_profile_id=profile.profile_id,
    )
    plan = context.pipeline_planner.build(job_id="preview-custom", request=request, preview=True)
    assert plan.knowledge_profile_id == profile.profile_id
    assert plan.knowledge_ids == ("code-declared-data-model",)
    assert not hasattr(plan, "report_profile")
    assert plan.assistant_profile_id is None


def test_production_structure_reads_immutable_execution_snapshots(tmp_path: Path) -> None:
    from knowledge_control_plane.api.generic_v1.models import JobDetails, JobOutputOptions, JobProgress, JobStatus
    from knowledge_control_plane.runtime.store import utc_now

    context = build_runtime_context(_settings(tmp_path))
    job_id = "job-production-structure"
    job = JobDetails(
        job_id=job_id,
        kind=JobKind.KNOWLEDGE_EXECUTION,
        status=JobStatus.SUCCEEDED,
        scenario_id="build-data-model-v1",
        knowledge_profile_id="data-model-v1",
        target=JobTarget(repository_ids=["repo-a"], system_id="system-a"),
        progress=JobProgress(message="Done"),
        created_at=utc_now(),
        knowledge_ids=["code-declared-data-model"],
        output=JobOutputOptions(),
    )
    context.store.insert_job(
        job,
        request_json=JobCreateRequest(
            target=JobTarget(repository_ids=["repo-a"], system_id="system-a"),
            scenario_id="build-data-model-v1",
            ).model_dump_json(),
        idempotency_key=None,
    )
    artifact_dir = tmp_path / "snapshots"
    artifact_dir.mkdir()
    payloads = {
        ArtifactKind.KNOWLEDGE_PROFILE: {
            "schema_version": "knowledge_profile/v2",
            "profile_id": "data-model-v1",
            "knowledge": [{"knowledge_id": "code-declared-data-model"}],
        },
        ArtifactKind.EXECUTION_PLAN: {
            "schema_version": "knowledge_execution_plan/v1",
            "nodes": [{"node_id": "core-a", "node_kind": "evidence"}],
            "edges": [],
        },
        ArtifactKind.EXECUTION_RESULT: {
            "schema_version": "knowledge_execution_result/v2",
            "status": "completed",
            "evidence_artifacts": [{
                "artifact_id": "evidence-a",
                "artifact_kind": "java-type-structure",
                "schema_version": "java_type_structure/v1",
                "status": "complete",
                "content_fingerprint": "a" * 64,
                "provenance": {"producer": {"analyzer_id": "java-type-structure"}},
                "coverage": {"status": "complete"},
                "diagnostics": {},
            }],
            "materialization_executions": [{
                "execution_node_id": "mat-a",
                "materialization_id": "code-declared-data-model",
                "status": "completed",
                "result_fingerprint": "b" * 64,
                "knowledge_artifact_ids": ["knowledge-a"],
            }],
            "knowledge_artifacts": [{
                "artifact_id": "knowledge-a",
                "model_kind": "code-declared-data-model",
                "schema_version": "code_declared_data_model/v1",
                "source_materialization_id": "code-declared-data-model",
                "content_fingerprint": "c" * 64,
                "coverage": {"status": "complete"},
                "diagnostics": [],
                "capabilities": ["common.code-declared-data-model"],
            }],
            "published_capabilities": ["common.code-declared-data-model"],
            "diagnostics": [],
        },
    }
    for index, (kind, payload) in enumerate(payloads.items(), start=1):
        path = artifact_dir / f"snapshot-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        context.artifacts.register_file(job_id=job_id, path=path, kind=kind)

    structure = context.production_structure.for_job(job_id)
    assert structure.profile_snapshot["profile_id"] == "data-model-v1"
    assert structure.execution_plan["schema_version"] == "knowledge_execution_plan/v1"
    assert {item.node_kind for item in structure.nodes} == {
        "core_evidence", "klc_materialization", "prepared_knowledge"
    }
    assert structure.capabilities == ["common.code-declared-data-model"]
    assert next(item for item in structure.nodes if item.node_kind == "core_evidence").producer_id == "java-type-structure"
    materialization = next(item for item in structure.nodes if item.node_kind == "klc_materialization")
    assert materialization.model_kind == "code-declared-data-model"
    assert materialization.schema_version == "code_declared_data_model/v1"
    assert materialization.fingerprint == "c" * 64
    assert next(item for item in structure.nodes if item.node_kind == "prepared_knowledge").producer_id == "code-declared-data-model"


def test_artifact_registry_skips_deep_core_evidence_payload_but_keeps_descriptor(tmp_path: Path) -> None:
    class CaptureStore:
        def __init__(self) -> None:
            self.paths = []
        def upsert_artifact(self, summary, absolute_path) -> None:
            self.paths.append((summary.relative_path, Path(absolute_path)))

    output = tmp_path / "knowledge-execution"
    evidence = output / "execution-nodes" / "001-source" / "core-evidence" / "evidence"
    descriptor = evidence / "system-description-evidence.json"
    payload = evidence / "system-description-payload" / "facts" / "full.jsonl"
    materialized = output / "materialization-execution" / "materializations" / "001" / "knowledge-layer.duckdb"
    for path in (descriptor, payload, materialized):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")

    store = CaptureStore()
    registry = ArtifactRegistry(store)
    items = registry.scan(job_id="job-1", output_path=output, relative_prefix="knowledge-execution")
    paths = {item.relative_path for item in items}
    assert "knowledge-execution/execution-nodes/001-source/core-evidence/evidence/system-description-evidence.json" in paths
    assert "knowledge-execution/execution-nodes/001-source/core-evidence/evidence/system-description-payload/facts/full.jsonl" not in paths
    assert "knowledge-execution/materialization-execution/materializations/001/knowledge-layer.duckdb" in paths
