from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import static_analysis_runner.data_model_discovery as module
from static_analysis_runner.data_model_discovery import run_data_model_discovery
from static_analysis_runner.io_utils import read_json, write_json


def _git_repository(path: Path, name: str) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "initial"],
        check=True,
    )
    return path


def _fake_evidence_execution(*, output: Path, repo_id: str, score: int, status: str) -> dict:
    root = Path(output)
    evidence_path = root / "core-evidence" / "evidence" / "data-model-candidate-evidence.json"
    write_json(
        evidence_path,
        {
            "contract_version": "core_evidence_artifact_contract/v1",
            "artifact_id": f"candidate-{repo_id}",
            "artifact_kind": "data-model-candidate-evidence",
            "schema_version": "data-model-candidate-evidence/v1",
            "content_fingerprint": f"fingerprint-{repo_id}",
            "candidate_profile": {
                "artifact": "data_model_candidate_profile",
                "schema_version": "data_model_candidate_profile/v1",
                "repo_id": repo_id,
                "candidate_status": status,
                "score": score,
                "signals": {"java_class_count": 10},
                "score_components": [{"component": "fixture", "points": score, "basis": "test"}],
                "evidence": [{"kind": "fixture", "path": "src/main/java/Model.java"}],
                "coverage": {"status": "complete", "full_data_model_analysis_performed": False},
            },
        },
    )
    return {
        "status": "completed",
        "evidence_artifacts": [
            {
                "artifact_id": f"candidate-{repo_id}",
                "artifact_kind": "data-model-candidate-evidence",
                "schema_version": "data-model-candidate-evidence/v1",
                "content_fingerprint": f"fingerprint-{repo_id}",
                "location": {"kind": "file", "path": "core-evidence/evidence/data-model-candidate-evidence.json"},
            }
        ],
    }


def test_discovery_limits_repository_prefix_ranks_candidates_and_cleans_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repos = [_git_repository(tmp_path / f"repo-{index}", f"repo-{index}") for index in range(1, 4)]
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
    monkeypatch.setattr(module, "validate_core_version", lambda **_kwargs: "0.44.6")

    def fake_execute(*, output: Path, repo_id: str, **_kwargs):
        scores = {"repo_1": (40, "possible"), "repo_2": (80, "strong")}
        score, status = scores[repo_id]
        return _fake_evidence_execution(output=Path(output), repo_id=repo_id, score=score, status=status)

    monkeypatch.setattr(module, "execute_core_evidence_request", fake_execute)
    result = run_data_model_discovery(
        output=tmp_path / "out",
        work_dir=tmp_path / "work",
        repository_sources=sources,
        auth_mode="none",
        max_repositories=2,
        replace=True,
    )
    inventory = read_json(result.inventory_path)
    assert [item["repo_id"] for item in inventory["candidates"]] == ["repo_2", "repo_1"]
    assert inventory["repository_summary"] == {
        "total": 2,
        "completed": 2,
        "failed": 0,
        "not_candidate": 0,
        "strong": 1,
        "possible": 1,
        "weak": 0,
    }
    assert inventory["repository_selection"]["limit"] == 2
    assert inventory["repository_selection"]["truncated"] is True
    assert not any((tmp_path / "work" / "data-model-discovery").iterdir())
    assert not (tmp_path / "out" / "repository-results" / "repo_3").exists()
    assert inventory["coverage"]["workspace_created"] is False
    assert inventory["coverage"]["full_data_model_analysis_performed"] is False
    profile = read_json(tmp_path / "out" / "repository-results" / "repo_2" / "data-model-candidate-profile.json")
    assert "task_suite_profile_semantics" not in profile["producer"]
    assert profile["evidence_artifact"]["schema_version"] == "data-model-candidate-evidence/v1"


def test_discovery_continues_after_repository_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repos = [_git_repository(tmp_path / f"repo-{index}", f"repo-{index}") for index in range(1, 3)]
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
    monkeypatch.setattr(module, "validate_core_version", lambda **_kwargs: "0.44.6")

    def fake_execute(*, output: Path, repo_id: str, **_kwargs):
        if repo_id == "repo_1":
            raise RuntimeError("broken analysis")
        return _fake_evidence_execution(output=Path(output), repo_id=repo_id, score=75, status="strong")

    monkeypatch.setattr(module, "execute_core_evidence_request", fake_execute)
    result = run_data_model_discovery(
        output=tmp_path / "out",
        work_dir=tmp_path / "work",
        repository_sources=sources,
        auth_mode="none",
        replace=True,
    )
    inventory = read_json(result.inventory_path)
    assert inventory["status"] == "partial"
    assert inventory["repository_summary"]["completed"] == 1
    assert inventory["repository_summary"]["failed"] == 1
    assert inventory["candidates"][0]["repo_id"] == "repo_2"
    assert inventory["repositories"][0]["status"] == "analysis_failed"
