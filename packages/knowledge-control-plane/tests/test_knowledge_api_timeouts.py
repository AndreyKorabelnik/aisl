from __future__ import annotations

from pathlib import Path

from knowledge_control_plane.runtime.settings import RuntimeSettings


def test_knowledge_api_read_timeout_is_configurable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_API_TIMEOUT_SECONDS", "45")
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    assert settings.knowledge_api_timeout_seconds == 45.0
    assert not hasattr(settings, "knowledge_api_publication_timeout_seconds")


def test_producer_has_no_publication_timeout_setting(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_API_PUBLICATION_TIMEOUT_SECONDS", "345")
    settings = RuntimeSettings.from_environment(base_dir=tmp_path)
    assert not hasattr(settings, "knowledge_api_publication_timeout_seconds")
