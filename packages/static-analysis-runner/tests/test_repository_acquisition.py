from __future__ import annotations

import os
from pathlib import Path

import pytest

import static_analysis_runner.repository_acquisition as module
from static_analysis_runner.io_utils import write_json
from static_analysis_runner.repository_acquisition import (
    prepare_repository_acquisition_run,
    select_repository_sources,
)
from static_analysis_runner.repository_sources import (
    PortfolioRepositorySource,
    PortfolioRepositorySources,
)


def _selection_kwargs() -> dict[str, object]:
    return {
        "auth_mode": "none",
        "token_env": "BITBUCKET_TOKEN",
        "username_env": "BITBUCKET_USERNAME",
        "password_env": "BITBUCKET_PASSWORD",
        "api_base_path": "/rest/api/latest",
        "ca_bundle": None,
        "insecure_skip_tls_verify": False,
        "timeout_seconds": 1.0,
        "page_size": 100,
    }


def test_select_repository_sources_requires_exactly_one_membership_source(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.json"
    write_json(
        manifest,
        {
            "schema_version": "portfolio_repository_sources/v1",
            "source": {"kind": "test"},
            "repositories": [{"repo_id": "one", "repository_url": "https://example.invalid/one.git"}],
        },
    )
    with pytest.raises(ValueError, match="exactly one repository source"):
        select_repository_sources(
            bitbucket_project_url=None,
            repository_sources=None,
            max_repositories=None,
            **_selection_kwargs(),
        )
    with pytest.raises(ValueError, match="exactly one repository source"):
        select_repository_sources(
            bitbucket_project_url="https://example.invalid/projects/ABC",
            repository_sources=manifest,
            max_repositories=None,
            **_selection_kwargs(),
        )


def test_manifest_selection_is_bounded_operational_membership(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.json"
    write_json(
        manifest,
        {
            "schema_version": "portfolio_repository_sources/v1",
            "source": {"kind": "fixture"},
            "repositories": [
                {"repo_id": "one", "repository_url": "https://user:secret@example.invalid/one.git"},
                {"repo_id": "two", "repository_url": "https://example.invalid/two.git"},
            ],
        },
    )
    selected = select_repository_sources(
        bitbucket_project_url=None,
        repository_sources=manifest,
        max_repositories=1,
        **_selection_kwargs(),
    )
    assert [item.repo_id for item in selected.repositories] == ["one"]
    assert selected.repositories[0].clone_url == "https://example.invalid/one.git"
    assert selected.source["repository_selection"] == {
        "mode": "manifest_order_prefix",
        "limit": 1,
        "selected_count": 1,
        "source_count": 2,
        "limit_reached": True,
        "truncated": True,
    }


def test_bitbucket_selection_reuses_official_discovery_without_cloning(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_discover(**kwargs):
        calls.append(kwargs)
        return PortfolioRepositorySources(
            source={"kind": "bitbucket-data-center", "project_key": "ABC"},
            repositories=(
                PortfolioRepositorySource(
                    repo_id="service_a",
                    clone_url="https://user:password@example.invalid/scm/abc/service-a.git",
                    project_id="ABC",
                ),
            ),
        )

    monkeypatch.setattr(module, "discover_bitbucket_project_repositories", fake_discover)
    selected = select_repository_sources(
        bitbucket_project_url="https://example.invalid/projects/ABC",
        repository_sources=None,
        max_repositories=7,
        **_selection_kwargs(),
    )
    assert len(calls) == 1
    assert calls[0]["project_url"] == "https://example.invalid/projects/ABC"
    assert calls[0]["max_repositories"] == 7
    assert selected.repositories[0].clone_url == "https://example.invalid/scm/abc/service-a.git"


def test_prepare_repository_acquisition_run_removes_only_stale_owned_runs(tmp_path: Path) -> None:
    base = tmp_path / "work" / "repository-batch"
    stale = base / "stale"
    stale.mkdir(parents=True)
    write_json(
        stale / ".repository-acquisition-temporary",
        {
            "schema_version": "repository_acquisition_temporary/v1",
            "producer": "static-analysis-runner",
            "namespace": "repository-batch",
            "pid": 2**30,
        },
    )
    unowned = base / "keep-me"
    unowned.mkdir()

    run_root, removed = prepare_repository_acquisition_run(
        tmp_path / "work", namespace="repository-batch", run_id="current"
    )
    assert removed == ["stale"]
    assert not stale.exists()
    assert unowned.is_dir()
    assert run_root.is_dir()
    marker = run_root / ".repository-acquisition-temporary"
    assert marker.is_file()
