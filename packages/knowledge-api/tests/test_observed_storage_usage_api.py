from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.app import create_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_api.publication import build_publication_request
from tests.execution_fixtures import KnowledgeArtifactSpec, write_execution_result

PREFIX = "/api/knowledge/v1"


def _database(path: Path) -> Path:
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE observed_storage_source(storage_usage_source_id VARCHAR, repo_id VARCHAR)")
        con.execute("""CREATE TABLE observed_storage_access(
            storage_access_id VARCHAR, storage_usage_source_id VARCHAR, repo_id VARCHAR,
            operation VARCHAR, operation_signature VARCHAR, class_name VARCHAR, method_name VARCHAR,
            access_kind VARCHAR, operation_kind VARCHAR, write_kind VARCHAR, mutation_kind VARCHAR,
            storage_kind VARCHAR, storage_target_expression VARCHAR, target_resolution_level VARCHAR,
            target_resolution_status VARCHAR, receiver_expression VARCHAR, receiver_declared_type VARCHAR,
            storage_method VARCHAR, payload_expression VARCHAR, payload_role VARCHAR, writes_new_payload BOOLEAN,
            selected_fields_json JSON, selected_field_refs_json JSON, result_type VARCHAR, sql_preview VARCHAR,
            source_ref_json JSON, payload_json JSON)""")
        con.execute("CREATE TABLE observed_storage_read(storage_read_id VARCHAR)")
        con.execute("CREATE TABLE observed_storage_write(storage_write_id VARCHAR)")
        con.execute("""CREATE TABLE observed_storage_usage_gap(
            storage_usage_gap_id VARCHAR, storage_usage_source_id VARCHAR, gap_code VARCHAR,
            severity VARCHAR, owner_kind VARCHAR, owner_id VARCHAR, message VARCHAR,
            details_json JSON, source_refs_json JSON, payload_json JSON)""")
        con.execute("INSERT INTO observed_storage_source VALUES ('source-1','repo-1')")
        con.execute("""INSERT INTO observed_storage_access VALUES (
            'access-1','source-1','repo-1','CustomerRepository.findById','sig','CustomerService','load',
            'read','read',NULL,NULL,'spring-data','customerRepository','receiver','unresolved',
            'customerRepository','CustomerRepository','findById',NULL,NULL,false,'["customer_id"]','[]',
            'Customer',NULL,'{"path":"src/CustomerService.java","line_start":10}','{}')""")
        con.execute("INSERT INTO observed_storage_read VALUES ('read-1')")
        con.execute("""INSERT INTO observed_storage_usage_gap VALUES (
            'gap-1','source-1','storage_target_unresolved','warning','storage_access','access-1',
            'Storage target is unresolved','{}','[]','{}')""")
    return path


def _client(tmp_path: Path) -> TestClient:
    database = _database(tmp_path / "storage.duckdb")
    result = write_execution_result(
        tmp_path,
        [KnowledgeArtifactSpec(
            database=database,
            model_kind="observed-storage-usage",
            schema_version="observed-storage-usage/v1",
            materialization_id="observed-storage-usage",
            capabilities=(
                "common.observed-storage-usage",
                "common.storage-read-write-inventory",
                "common.storage-access-gaps",
            ),
        )],
    )
    request, warnings = build_publication_request(execution_result=result, labels=(), metadata={}, activate=True)
    assert warnings == []
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite", allowed_roots=(tmp_path,))
    service = KnowledgeDomainService(settings)
    client = TestClient(create_app(service=service))
    client.__enter__()
    created = client.post(PREFIX + "/systems", json={"system_id":"storage","display_name":"Storage"})
    assert created.status_code == 201
    published = client.post(PREFIX + "/systems/storage/revisions", json=request.model_dump(mode="json"))
    assert published.status_code == 201, published.text
    return client


def test_observed_storage_accesses_are_capability_selected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        response = client.get(PREFIX + "/systems/storage/storage-usage/accesses", params={"access_kind":"read"})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["items"][0]["storage_access_id"] == "access-1"
        assert payload["items"][0]["selected_fields"] == ["customer_id"]
        assert payload["summary"] == {
            "access_count": 1,
            "read_count": 1,
            "write_count": 0,
            "gap_count": 1,
            "by_storage_kind": {"spring-data": 1},
            "by_resolution_status": {"unresolved": 1},
        }
    finally:
        client.__exit__(None, None, None)


def test_observed_storage_gaps_are_explicit(tmp_path: Path) -> None:
    client = _client(tmp_path)
    try:
        response = client.get(PREFIX + "/systems/storage/storage-usage/gaps")
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["gap_code"] == "storage_target_unresolved"
    finally:
        client.__exit__(None, None, None)
