from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import static_analysis_runner.repository_batch as module
from static_analysis_runner.io_utils import read_json, write_json
from static_analysis_runner.repository_batch import run_repository_batch


def _git_repository(path: Path, name: str) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git", "-C", str(path), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "initial",
        ],
        check=True,
    )
    return path


def _write_inputs(tmp_path: Path, repos: list[Path]) -> tuple[Path, Path, Path, Path, Path]:
    sources = tmp_path / "sources.json"
    write_json(
        sources,
        {
            "schema_version": "portfolio_repository_sources/v1",
            "source": {"kind": "test"},
            "repositories": [
                {"repo_id": f"repo_{index}", "repository_url": repo.as_uri(), "ref": "main"}
                for index, repo in enumerate(repos, start=1)
            ],
        },
    )
    profile = tmp_path / "profile.json"
    write_json(
        profile,
        {
            "schema_version": "knowledge_profile/v2",
            "profile_id": "batch-test",
            "title": "Batch test",
            "scope": {"kind": "repository", "scope_id": "template"},
            "knowledge": [{"knowledge_id": "repository-inventory", "options": {}}],
            "presentation": {},
        },
    )
    knowledge_catalog = tmp_path / "knowledge-catalog.json"
    core_catalog = tmp_path / "core-catalog.json"
    materialization_catalog = tmp_path / "materialization-catalog.json"
    for path in (knowledge_catalog, core_catalog, materialization_catalog):
        write_json(path, {})
    return sources, profile, knowledge_catalog, core_catalog, materialization_catalog


def _install_fake_pipeline(monkeypatch: pytest.MonkeyPatch, observed_paths: list[Path]) -> None:
    monkeypatch.setattr(module, "resolve_knowledge_profile", lambda *_args, **_kwargs: {})

    def fake_prepare(*, scope_kind: str, scope_id: str, repositories, repository_metadata_by_source_id, **_kwargs):
        repository = Path(repositories[0])
        assert scope_kind == "repository"
        assert scope_id == repository.name
        assert repository.is_dir()
        assert (repository / ".git").is_dir()
        observed_paths.append(repository)
        # Sequential lifecycle invariant: there can be only the current checkout.
        slot = repository.parent
        active = [item for item in slot.iterdir() if item.is_dir()]
        assert active == [repository]
        metadata = repository_metadata_by_source_id[scope_id]
        assert metadata["resolved_commit"]
        return {
            "schema_version": "knowledge_input_inventory/v1",
            "scope": {"kind": "repository", "scope_id": scope_id},
            "source_snapshots": [{"source_id": scope_id, "source_metadata": metadata}],
            "inventory_fingerprint": f"inventory-{scope_id}",
        }

    def fake_compile(*, knowledge_profile, input_inventory, **_kwargs):
        repo_id = input_inventory["scope"]["scope_id"]
        assert knowledge_profile["scope"] == {"kind": "repository", "scope_id": repo_id}
        return {
            "schema_version": "knowledge_execution_plan/v1",
            "scope": {"kind": "repository", "scope_id": repo_id},
            "status": {"overall": "ready"},
            "graph": {"nodes": [], "edges": [], "execution_order": []},
            "plan_fingerprint": f"plan-{repo_id}",
        }

    def fake_execute(*, execution_plan: Path, output: Path, **_kwargs):
        repo_id = Path(execution_plan).parent.name
        target = Path(output)
        target.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "knowledge_execution_result/v2",
            "status": "completed",
            "scope": {"kind": "repository", "scope_id": repo_id},
            "result_fingerprint": f"result-{repo_id}",
            "published_capabilities": ["common.repository-inventory"],
            "knowledge_artifacts": [{"artifact_id": f"knowledge-{repo_id}"}],
        }
        write_json(target / "knowledge_execution_result.json", payload)
        return payload

    monkeypatch.setattr(module, "prepare_knowledge_input_inventory", fake_prepare)
    monkeypatch.setattr(module, "compile_knowledge_execution_plan", fake_compile)
    monkeypatch.setattr(module, "execute_knowledge_execution_plan", fake_execute)


def test_repository_batch_executes_each_repo_independently_and_removes_checkouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repos = [_git_repository(tmp_path / f"source-{index}", f"repo-{index}") for index in range(1, 4)]
    sources, profile, knowledge_catalog, core_catalog, materialization_catalog = _write_inputs(tmp_path, repos)
    observed_paths: list[Path] = []
    _install_fake_pipeline(monkeypatch, observed_paths)

    result = run_repository_batch(
        output=tmp_path / "out",
        work_dir=tmp_path / "work",
        knowledge_profile=profile,
        knowledge_catalog=knowledge_catalog,
        core_evidence_catalog=core_catalog,
        materialization_catalog=materialization_catalog,
        repository_sources=sources,
        auth_mode="none",
        replace=True,
    )

    assert result.summary["status"] == "completed"
    assert result.summary["repositories_completed"] == 3
    assert result.summary["max_concurrent_checkouts"] == 1
    assert result.summary["persistent_repository_checkout_count"] == 0
    assert len(observed_paths) == 3
    assert all(not path.exists() for path in observed_paths)
    assert not any((tmp_path / "work" / "repository-batch").iterdir())

    manifest = read_json(tmp_path / "out" / "repository-batch-run-manifest.json")
    assert manifest["execution_semantics"] == "independent_repository_knowledge_execution"
    assert manifest["temporary_work"]["repository_checkout_removed_after_each_repository"] is True
    assert manifest["temporary_work"]["max_concurrent_checkouts"] == 1
    assert [item["repo_id"] for item in manifest["repository_results"]] == ["repo_1", "repo_2", "repo_3"]
    assert all(item["temporary_checkout_removed"] is True for item in manifest["repository_results"])
    assert [
        read_json(tmp_path / "out" / "repositories" / f"repo_{index}" / "knowledge-profile.json")["scope"]
        for index in range(1, 4)
    ] == [
        {"kind": "repository", "scope_id": "repo_1"},
        {"kind": "repository", "scope_id": "repo_2"},
        {"kind": "repository", "scope_id": "repo_3"},
    ]


def test_repository_batch_continues_after_repository_execution_failure_and_cleans_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repos = [_git_repository(tmp_path / f"source-{index}", f"repo-{index}") for index in range(1, 3)]
    sources, profile, knowledge_catalog, core_catalog, materialization_catalog = _write_inputs(tmp_path, repos)
    observed_paths: list[Path] = []
    _install_fake_pipeline(monkeypatch, observed_paths)
    original_execute = module.execute_knowledge_execution_plan

    def fail_first(*, execution_plan: Path, **kwargs):
        if Path(execution_plan).parent.name == "repo_1":
            raise RuntimeError("fixture execution failure")
        return original_execute(execution_plan=execution_plan, **kwargs)

    monkeypatch.setattr(module, "execute_knowledge_execution_plan", fail_first)

    result = run_repository_batch(
        output=tmp_path / "out",
        work_dir=tmp_path / "work",
        knowledge_profile=profile,
        knowledge_catalog=knowledge_catalog,
        core_evidence_catalog=core_catalog,
        materialization_catalog=materialization_catalog,
        repository_sources=sources,
        auth_mode="none",
        replace=True,
    )

    assert result.summary["status"] == "partial"
    assert result.summary["repositories_completed"] == 1
    assert result.summary["repositories_failed"] == 1
    assert all(not path.exists() for path in observed_paths)
    first = read_json(tmp_path / "out" / "repositories" / "repo_1" / "repository-batch-result.json")
    second = read_json(tmp_path / "out" / "repositories" / "repo_2" / "repository-batch-result.json")
    assert first["status"] == "production_failed"
    assert first["failure_stage"] == "execution"
    assert first["failure_code"] == "repository_knowledge_execution_failed"
    assert first["temporary_checkout_removed"] is True
    assert second["status"] == "completed"


def test_repository_batch_rejects_non_repository_profile_before_source_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repository(tmp_path / "source", "repo")
    sources, profile, knowledge_catalog, core_catalog, materialization_catalog = _write_inputs(tmp_path, [repo])
    payload = read_json(profile)
    payload["scope"] = {"kind": "workspace", "scope_id": "wrong"}
    write_json(profile, payload)

    called = False

    def fail_if_selected(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("repository selection must not run")

    monkeypatch.setattr(module, "select_repository_sources", fail_if_selected)
    with pytest.raises(ValueError, match="repository-scoped"):
        run_repository_batch(
            output=tmp_path / "out",
            work_dir=tmp_path / "work",
            knowledge_profile=profile,
            knowledge_catalog=knowledge_catalog,
            core_evidence_catalog=core_catalog,
            materialization_catalog=materialization_catalog,
            repository_sources=sources,
            auth_mode="none",
            replace=True,
        )
    assert called is False
