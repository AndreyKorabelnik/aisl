from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generator_has_no_chat_runtime_dependency_or_surface() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "knowledge-assistant" not in pyproject
    assert not (ROOT / "src/knowledge_control_plane/runtime/assistant.py").exists()
    assert not (ROOT / "src/knowledge_control_plane/runtime/assistant_contexts.py").exists()
    assert not (ROOT / "frontend").exists()
    routes = (ROOT / "src/knowledge_control_plane/runtime/routes.py").read_text(encoding="utf-8")
    assert "/assistant-contexts" not in routes


def test_production_pipeline_ends_at_transportable_bundle() -> None:
    pipeline = (ROOT / "src/knowledge_control_plane/runtime/pipeline.py").read_text(encoding="utf-8")
    jobs = (ROOT / "src/knowledge_control_plane/runtime/jobs.py").read_text(encoding="utf-8")
    assert "assistant_ready" not in pipeline
    assert "assistant_context_id" not in jobs
    assert "publication_bundle" in jobs
    assert "publish_revision" not in jobs


def test_bundle_exposes_neutral_consumer_profile_hint() -> None:
    jobs = (ROOT / "src/knowledge_control_plane/runtime/jobs.py").read_text(encoding="utf-8")
    assert 'metadata["integration_profile_id"] = plan.assistant_profile_id' in jobs
    assert 'assistant_context_id' not in jobs


def test_headless_runtime_serves_api_without_web_frontend(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from knowledge_control_plane.runtime.app import create_runtime_app
    from knowledge_control_plane.runtime.settings import RuntimeSettings

    settings = RuntimeSettings(
        runtime_root=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "runtime.sqlite3",
        jobs_root=tmp_path / "runtime" / "jobs",
        default_analysis_output_root=tmp_path / "outputs",
        knowledge_api_proxy_enabled=False,
    )
    with TestClient(create_runtime_app(settings)) as client:
        root = client.get("/")
        capabilities = client.get("/api/v1/capabilities")
    assert root.status_code == 404
    assert root.json()["code"] == "resource_not_found"
    assert capabilities.status_code == 200
