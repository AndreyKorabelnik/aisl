from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_module_versions_are_explicit_and_aligned() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.2.0a33"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.2.0a33"' in pyproject
    assert "knowledge-assistant" not in pyproject
    assert '__version__ = "1.2.0a33"' in (ROOT / "src/knowledge_control_plane/__init__.py").read_text(encoding="utf-8")


def test_supported_module_layout_is_headless() -> None:
    required = (
        "src/knowledge_control_plane/runtime/knowledge_contracts.py",
        "src/knowledge_control_plane/runtime/knowledge_api_client.py",
        "src/knowledge_control_plane/runtime/publication_bundle.py",
        "src/knowledge_control_plane/runtime/app.py",
        "src/knowledge_control_plane/runtime/routes.py",
        "docs/architecture/KNOWLEDGE_API_BOUNDARY.md",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative

    removed = (
        "frontend",
        "src/knowledge_control_plane/runtime/assistant.py",
        "src/knowledge_control_plane/runtime/assistant_contexts.py",
        "src/knowledge_control_plane/runtime/reporting.py",
        "src/knowledge_control_plane/runtime/knowledge_publication.py",
    )
    for relative in removed:
        assert not (ROOT / relative).exists(), relative


def test_runtime_has_no_frontend_serving_contract() -> None:
    app = (ROOT / "src/knowledge_control_plane/runtime/app.py").read_text(encoding="utf-8")
    settings = (ROOT / "src/knowledge_control_plane/runtime/settings.py").read_text(encoding="utf-8")
    diagnostics = (ROOT / "src/knowledge_control_plane/runtime/diagnostics.py").read_text(encoding="utf-8")
    combined = "\n".join((app, settings, diagnostics))
    for forbidden in ("StaticFiles", "frontend_dist", "KNOWLEDGE_CONTROL_PLANE_FRONTEND_DIST", "frontend.production_build"):
        assert forbidden not in combined
