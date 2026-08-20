from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge_api.app import create_app
from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings


def test_application_exposes_only_canonical_knowledge_routes(tmp_path) -> None:
    app = create_app(settings=KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,)))
    paths = set(app.openapi()["paths"])
    assert paths
    assert all(path.startswith(KNOWLEDGE_API_PREFIX) for path in paths)
    assert not any(path == "/health" or path.startswith("/api/v1") for path in paths)


def test_removed_legacy_paths_return_not_found(tmp_path) -> None:
    app = create_app(settings=KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,)))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 404
        assert client.get("/api/v1/systems").status_code == 404
        assert client.get(f"{KNOWLEDGE_API_PREFIX}/health").status_code == 200
