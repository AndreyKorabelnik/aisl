from __future__ import annotations

from pathlib import Path

from knowledge_api.app import create_app
from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX

ROOT = Path(__file__).resolve().parents[1]


def test_removed_runtime_modules_are_not_distributed() -> None:
    for relative in (
        "knowledge_api/registry.py",
        "knowledge_api/data_model_query.py",
        "knowledge_api/settings.py",
        "knowledge_api/openapi_export.py",
        "schemas/openapi.json",
        "config/systems.example.json",
    ):
        assert not (ROOT / relative).exists(), relative


def test_package_declares_one_openapi_exporter() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert pyproject.count("knowledge-api-export-openapi") == 1
    assert "knowledge-api-export-contract-openapi" not in pyproject
    assert "--registry" not in (ROOT / "knowledge_api" / "cli.py").read_text(encoding="utf-8")
    assert "--no-legacy" not in (ROOT / "knowledge_api" / "cli.py").read_text(encoding="utf-8")


def test_application_has_one_public_route_prefix() -> None:
    paths = set(create_app().openapi()["paths"])
    assert paths
    assert all(path.startswith(KNOWLEDGE_API_PREFIX) for path in paths)
