from __future__ import annotations

import sqlite3
from pathlib import Path

from knowledge_api.contract_v1.contract import create_contract_app
from knowledge_api.contract_v1.models import RevisionCreateRequest, SystemRevision
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService


def test_report_is_not_a_revision_or_http_contract() -> None:
    assert "report" not in RevisionCreateRequest.model_fields
    assert "report" not in SystemRevision.model_fields
    schema = create_contract_app().openapi()
    assert all("/reports" not in path for path in schema["paths"])
    assert "prepared_reports" not in str(schema)


def test_fresh_catalog_has_no_report_storage_slot(tmp_path: Path) -> None:
    database = tmp_path / "knowledge-api.sqlite3"
    KnowledgeDomainService(KnowledgeApiSettings(database_path=database, allowed_roots=(tmp_path,)))
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(revisions)")}
    assert "report_json" not in columns
