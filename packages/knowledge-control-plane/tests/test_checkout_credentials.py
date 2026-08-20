from __future__ import annotations

from pathlib import Path

from knowledge_control_plane.api.generic_v1.models import RemoteRepositoryCandidate, RepositoryDiscoverRequest
from knowledge_control_plane.runtime.repositories import RepositoryService
from knowledge_control_plane.runtime.settings import RuntimeSettings
from knowledge_control_plane.runtime.store import RuntimeStore


def _service(tmp_path: Path) -> RepositoryService:
    settings = RuntimeSettings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "knowledge-control-plane.sqlite3",
        jobs_root=tmp_path / "runtime" / "jobs",
        default_analysis_output_root=tmp_path / "outputs" / "analysis",
    )
    settings.ensure_directories()
    return RepositoryService(RuntimeStore(settings.database_path), settings)


def test_server_environment_credentials_are_used_noninteractively(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BITBUCKET_USERNAME", "user")
    monkeypatch.setenv("BITBUCKET_TOKEN", "secret-token")
    service = _service(tmp_path)
    repository = service.discover(
        RepositoryDiscoverRequest(
            remotes=[
                RemoteRepositoryCandidate(
                    location="https://stash.example.test/scm/demo/repository.git"
                )
            ],
            defer_checkout=True,
        )
    ).repositories[0]

    assert repository.status.value == "unavailable"
    assert "secret-token" not in repository.model_dump_json()

    command = service.checkout_command(repository.repository_id)
    assert command is not None
    assert command.argv[:4] == ["git", "-c", "credential.helper=", "clone"]
    assert command.environment["GIT_TERMINAL_PROMPT"] == "0"
    assert command.environment["GCM_INTERACTIVE"] == "Never"
    assert command.environment["KNOWLEDGE_CONTROL_PLANE_GIT_USERNAME"] == "user"
    assert command.environment["KNOWLEDGE_CONTROL_PLANE_GIT_TOKEN"] == "secret-token"
    assert command.environment["GIT_ASKPASS"].endswith("git-askpass.py")


def test_checkout_without_server_credentials_disables_vscode_and_terminal_prompts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    service = _service(tmp_path)
    repository = service.discover(
        RepositoryDiscoverRequest(
            remotes=[
                RemoteRepositoryCandidate(
                    location="https://stash.example.test/scm/demo/repository.git"
                )
            ],
            defer_checkout=True,
        )
    ).repositories[0]
    command = service.checkout_command(repository.repository_id)
    assert command is not None
    assert command.environment == {
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "Never",
        "SSH_ASKPASS_REQUIRE": "never",
        "SSH_ASKPASS": "/bin/false",
        "GIT_ASKPASS": "/bin/false",
    }
