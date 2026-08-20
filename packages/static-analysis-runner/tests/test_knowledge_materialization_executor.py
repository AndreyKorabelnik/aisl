from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from static_analysis_runner.cli import app
from static_analysis_runner.io_utils import stable_fingerprint, write_json
from static_analysis_runner.knowledge_materialization_executor import (
    KNOWLEDGE_MATERIALIZATION_RUN_SCHEMA_VERSION,
    _materialization_reuse_material,
    _topological_order,
    execute_knowledge_materialization_plan,
)
from static_analysis_runner.evidence_executor import execute_core_evidence_plan
from static_analysis_runner import knowledge_materialization_executor as executor_module
from test_evidence_executor import _catalog as _evidence_catalog, _fake_core, _plan as _evidence_plan

runner = CliRunner()


def _catalog(path: Path, *, registered: bool = True) -> Path:
    contract = {
        "schema_version": "knowledge_materialization_contract/v3",
        "materialization_id": "code-declared-data-model",
        "input_contract": {
            "required_evidence": [{
                "artifact_kind": "java-type-structure-evidence",
                "schema_versions": ["java-type-structure-evidence/v1"],
            }],
            "optional_evidence": [],
            "required_knowledge_models": [],
            "optional_knowledge_models": [],
        },
        "current_implementation": {
            "runtime": {
                "contract_id": "knowledge_materialization_runtime/v1",
                "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
                "registered": registered,
                "handler_id": "code-declared-data-model" if registered else None,
            }
        },
        "outputs": {
            "models": ["code-declared-data-model/v1"],
            "capabilities": [
                "common.code-declared-data-model",
                "common.code-declared-entities",
                "common.code-declared-fields",
                "common.code-declared-inheritance",
                "common.code-declared-relationships",
            ],
        },
    }
    payload = {
        "schema_version": "knowledge_materialization_catalog/v3",
        "klc_version": "0.54.1",
        "runtime_contract": {
            "contract_id": "knowledge_materialization_runtime/v1",
            "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
            "registered_materialization_ids": ["code-declared-data-model"] if registered else [],
        },
        "materializations": [contract],
    }
    payload["catalog_fingerprint"] = stable_fingerprint(payload)
    write_json(path, payload)
    return path


def _plan(path: Path) -> Path:
    payload = {
        "schema_version": "knowledge_resolution_plan/v2",
        "profile": {
            "profile_id": "profile-a",
            "scope": {"kind": "repository", "scope_id": "repo-a"},
        },
        "technical_plan": {
            "materializations": [{"materialization_id": "code-declared-data-model"}],
        },
        "resolved_selection": {"resolved_knowledge_ids": ["code-declared-data-model"]},
    }
    payload["plan_fingerprint"] = stable_fingerprint(payload)
    write_json(path, payload)
    return path


def _repository_run(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "A.java").write_text("class A {}", encoding="utf-8")
    execute_core_evidence_plan(
        repository=repository,
        resolution_plan=_evidence_plan(
            tmp_path / "evidence-plan.json",
            ("java-type-structure-evidence", "java-type-structure-evidence/v1"),
        ),
        core_evidence_catalog=_evidence_catalog(
            tmp_path / "evidence-catalog.json",
            ("java-type-structure-evidence", "java-type-structure-evidence/v1"),
        ),
        output=tmp_path / "analysis",
        core_command=str(_fake_core(tmp_path / "fake-core")),
        repo_id="repo-a",
        replace=True,
    )
    return tmp_path / "analysis/repository_analysis_run_manifest.json"


def test_generic_executor_runs_registered_klc_materialization(tmp_path: Path) -> None:
    run_manifest = _repository_run(tmp_path)
    progress_messages: list[str] = []
    result = execute_knowledge_materialization_plan(
        resolution_plan=_plan(tmp_path / "plan.json"),
        materialization_catalog=_catalog(tmp_path / "catalog.json"),
        repository_run_manifests=[run_manifest],
        output=tmp_path / "knowledge-run",
        progress=progress_messages.append,
    )

    assert result["schema_version"] == KNOWLEDGE_MATERIALIZATION_RUN_SCHEMA_VERSION
    assert result["knowledge_layer_core"]["execution_isolation"] == "one_process_per_materialization"
    assert result["execution_order"] == ["code-declared-data-model"]
    assert len(result["materialization_executions"]) == 1
    assert len(result["knowledge_artifacts"]) == 1
    assert "common.code-declared-data-model" in result["published_capabilities"]
    assert result["semantic_policy"] == {
        "runner_dispatch": "generic_contract_driven",
        "klc_dispatch": "materialization_id_to_klc_owned_handler",
        "capability_publication": "completed_materialization_results_only",
    }
    assert "task_suite_profile_semantics" not in result["semantic_policy"]
    assert "legacy_fallback" not in result["semantic_policy"]
    assert (tmp_path / "knowledge-run/knowledge_materialization_execution_run.json").is_file()
    assert any("[materialization:code-declared-data-model] started" in item for item in progress_messages)
    assert any("materialization code-declared-data-model handler started" in item for item in progress_messages)
    assert any("[materialization:code-declared-data-model] completed" in item for item in progress_messages)


def test_executor_source_has_no_materialization_specific_branch() -> None:
    source = inspect.getsource(executor_module)
    assert "code-declared-data-model" not in source
    assert "if knowledge_id" not in source
    assert "if materialization_id ==" not in source


def test_unregistered_materialization_fails_before_klc(tmp_path: Path) -> None:
    run_manifest = _repository_run(tmp_path)
    with pytest.raises(ValueError, match="not registered in KLC runtime"):
        execute_knowledge_materialization_plan(
            resolution_plan=_plan(tmp_path / "plan.json"),
            materialization_catalog=_catalog(tmp_path / "catalog.json", registered=False),
            repository_run_manifests=[run_manifest],
            output=tmp_path / "knowledge-run",
        )


def test_missing_required_evidence_fails_without_fallback(tmp_path: Path) -> None:
    run_manifest = tmp_path / "repository-run.json"
    payload = {
        "schema_version": "static_repository_analysis_run_manifest/v1",
        "repository": {"repo_id": "repo-a"},
        "evidence_artifacts": [],
        "status": "completed",
    }
    write_json(run_manifest, payload)
    with pytest.raises(ValueError, match="has no required evidence"):
        execute_knowledge_materialization_plan(
            resolution_plan=_plan(tmp_path / "plan.json"),
            materialization_catalog=_catalog(tmp_path / "catalog.json"),
            repository_run_manifests=[run_manifest],
            output=tmp_path / "knowledge-run",
        )


def test_topological_order_is_generic() -> None:
    contracts = {
        "source-a": {"input_contract": {"required_knowledge_models": [], "optional_knowledge_models": []}},
        "source-b": {"input_contract": {"required_knowledge_models": [], "optional_knowledge_models": []}},
        "composite": {"input_contract": {"required_knowledge_models": [
            {"source_materialization_id": "source-a"},
            {"source_materialization_id": "source-b"},
        ], "optional_knowledge_models": []}},
    }
    assert _topological_order(("composite", "source-b", "source-a"), contracts) == (
        "source-b", "source-a", "composite"
    )


def test_materialization_reuse_identity_uses_upstream_stable_key_not_build_local_fingerprint() -> None:
    common = {
        "materialization_id": "downstream",
        "scope_id": "system-a",
        "klc_version": "0.61.0a23",
        "request_schema_version": "knowledge_materialization_request/v1",
        "contract": {"materialization_id": "downstream", "outputs": {"models": ["downstream/v1"]}},
        "runtime_contract": {"contract_id": "knowledge_materialization_runtime/v1"},
        "evidence_artifacts": [],
        "parameters": {"mode": "semantic"},
    }
    first = _materialization_reuse_material(
        **common,
        knowledge_artifacts=[{
            "artifact_id": "build-local-a",
            "model_kind": "upstream-model",
            "schema_version": "upstream/v1",
            "source_materialization_id": "upstream",
            "content_fingerprint": "a" * 64,
            "producer_reuse_key": "1" * 64,
        }],
    )
    second = _materialization_reuse_material(
        **common,
        knowledge_artifacts=[{
            "artifact_id": "build-local-b",
            "model_kind": "upstream-model",
            "schema_version": "upstream/v1",
            "source_materialization_id": "upstream",
            "content_fingerprint": "b" * 64,
            "producer_reuse_key": "1" * 64,
        }],
    )
    changed = _materialization_reuse_material(
        **common,
        knowledge_artifacts=[{
            "artifact_id": "build-local-c",
            "model_kind": "upstream-model",
            "schema_version": "upstream/v1",
            "source_materialization_id": "upstream",
            "content_fingerprint": "b" * 64,
            "producer_reuse_key": "2" * 64,
        }],
    )
    assert stable_fingerprint(first) == stable_fingerprint(second)
    assert stable_fingerprint(first) != stable_fingerprint(changed)


def test_materialization_reuse_identity_invalidates_on_semantic_contract_inputs() -> None:
    common = {
        "materialization_id": "materialization-a",
        "scope_id": "system-a",
        "klc_version": "0.61.0a23",
        "request_schema_version": "knowledge_materialization_request/v1",
        "contract": {
            "materialization_id": "materialization-a",
            "outputs": {"models": ["model-a/v1"]},
        },
        "runtime_contract": {
            "contract_id": "knowledge_materialization_runtime/v1",
            "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
        },
        "evidence_artifacts": [{
            "artifact_id": "build-local-evidence-a",
            "artifact_kind": "evidence-a",
            "schema_version": "evidence-a/v1",
            "content_fingerprint": "a" * 64,
        }],
        "knowledge_artifacts": [],
        "parameters": {"semantic_mode": "strict"},
    }
    baseline = _materialization_reuse_material(**common)
    baseline_fp = stable_fingerprint(baseline)

    variants = []
    for field, value in (
        ("klc_version", "0.61.0a25"),
        ("request_schema_version", "knowledge_materialization_request/v2"),
        ("parameters", {"semantic_mode": "expanded"}),
        ("contract", {
            "materialization_id": "materialization-a",
            "outputs": {"models": ["model-a/v2"]},
        }),
        ("runtime_contract", {
            "contract_id": "knowledge_materialization_runtime/v2",
            "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
        }),
        ("evidence_artifacts", [{
            "artifact_id": "different-build-local-id",
            "artifact_kind": "evidence-a",
            "schema_version": "evidence-a/v1",
            "content_fingerprint": "b" * 64,
        }]),
    ):
        changed = dict(common)
        changed[field] = value
        variants.append(_materialization_reuse_material(**changed))

    assert all(stable_fingerprint(item) != baseline_fp for item in variants)


def test_topological_order_preserves_valid_plan_order_across_independent_branches() -> None:
    contracts = {
        "source-a": {"input_contract": {"required_knowledge_models": [], "optional_knowledge_models": []}},
        "source-b": {"input_contract": {"required_knowledge_models": [], "optional_knowledge_models": []}},
        "source-c": {"input_contract": {"required_knowledge_models": [], "optional_knowledge_models": []}},
        "branch-a": {"input_contract": {"required_knowledge_models": [
            {"source_materialization_id": "source-a"},
            {"source_materialization_id": "source-b"},
        ], "optional_knowledge_models": []}},
        "branch-a-final": {"input_contract": {"required_knowledge_models": [
            {"source_materialization_id": "branch-a"},
        ], "optional_knowledge_models": []}},
        "branch-b": {"input_contract": {"required_knowledge_models": [
            {"source_materialization_id": "source-c"},
        ], "optional_knowledge_models": []}},
    }
    selected = ("source-a", "source-b", "source-c", "branch-a", "branch-a-final", "branch-b")
    assert _topological_order(selected, contracts) == selected


def test_topological_order_accepts_existing_required_knowledge() -> None:
    contracts = {
        "composite": {"input_contract": {"required_knowledge_models": [{
            "model_kind": "sql-observed-data-usage",
            "schema_versions": ["knowledge_layer_sql/v2"],
            "source_materialization_id": "sql-analysis",
        }], "optional_knowledge_models": []}},
    }
    existing = [{
        "artifact_id": "sql-a",
        "model_kind": "sql-observed-data-usage",
        "schema_version": "knowledge_layer_sql/v2",
        "source_materialization_id": "sql-analysis",
    }]
    assert _topological_order(("composite",), contracts, existing) == ("composite",)


def test_topological_order_rejects_missing_required_existing_knowledge() -> None:
    contracts = {
        "composite": {"input_contract": {"required_knowledge_models": [{
            "model_kind": "sql-observed-data-usage",
            "schema_versions": ["knowledge_layer_sql/v2"],
            "source_materialization_id": "sql-analysis",
        }], "optional_knowledge_models": []}},
    }
    with pytest.raises(ValueError, match="requires unavailable knowledge materialization"):
        _topological_order(("composite",), contracts, ())


def test_cli_executes_generic_materialization_plan(tmp_path: Path) -> None:
    run_manifest = _repository_run(tmp_path)
    plan = _plan(tmp_path / "plan.json")
    catalog = _catalog(tmp_path / "catalog.json")
    output = tmp_path / "cli-knowledge-run"
    result = runner.invoke(app, [
        "knowledge-materialize",
        "--resolution-plan", str(plan),
        "--materialization-catalog", str(catalog),
        "--repository-run-manifest", str(run_manifest),
        "--output", str(output),
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["execution_order"] == ["code-declared-data-model"]
    assert summary["materialization_count"] == 1
    assert (output / "knowledge_materialization_execution_run.json").is_file()
