from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.physical_model_schema import PHYSICAL_MODEL_DDL


def _physical_model_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "pdm-klc"
    root.mkdir()
    database = root / "knowledge-layer.duckdb"
    con = duckdb.connect(str(database))
    try:
        con.execute(PHYSICAL_MODEL_DDL)
        con.execute(
            "INSERT INTO physical_model_source VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "pdm-test", str(root / "source-manifest.json"), "physical-model/v1", "fingerprint",
                "0.43.7", "model.pdm", "a" * 64, "model-object", "Test model", "TEST_MODEL",
                "16.6", "Hive", "partial", 1,
                json.dumps({"owner": "test"}), json.dumps({"schema_version": "physical-model/v1"}),
            ],
        )
        con.execute(
            "INSERT INTO physical_model_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "table-client", "pdm-test", "o1", "uuid-1", "Test model", "TEST_MODEL",
                json.dumps(["Business"]), json.dumps(["BUSINESS"]), "Клиент", "t_client",
                "Business.t_client", None, "Client", None, None, None, 2, 1,
                "model.pdm", json.dumps({"file": "model.pdm", "pdm_object_id": "o1"}), json.dumps({}),
            ],
        )
        con.executemany(
            "INSERT INTO physical_model_column VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("column-id", "table-client", "pdm-test", "c1", "uuid-c1", 1, "ID", "client_id", "bigint", None, None, True, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c1"}), json.dumps({})),
                ("column-country", "table-client", "pdm-test", "c2", "uuid-c2", 2, "Страна", "country_code", "string", 3, None, False, None, None, None, "model.pdm", json.dumps({"pdm_object_id": "c2"}), json.dumps({})),
            ],
        )
        con.execute(
            "INSERT INTO physical_model_key VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["key-client", "table-client", "pdm-test", "k1", "uuid-k1", "PK", "pk_client", "primary", json.dumps(["c1"]), json.dumps(["client_id"]), json.dumps([]), "model.pdm", json.dumps({}), json.dumps({})],
        )
        con.execute(
            "INSERT INTO physical_model_relationship VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["rel-self", "pdm-test", "r1", "uuid-r1", "Parent", "parent", "0..1", "o1", "table-client", "t_client", "o1", "table-client", "t_client", "k1", "key-client", json.dumps([{"parent_column_code": "client_id", "child_column_code": "client_id"}]), "resolved", "model.pdm", json.dumps({}), json.dumps({})],
        )
        con.execute(
            "INSERT INTO physical_model_gap VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["gap-1", "pdm-test", "unresolved_domain", "c2", "domain-x", "Domain missing", json.dumps({})],
        )
    finally:
        con.close()
    return database


def _publish(client: TestClient, artifact: Path) -> str:
    from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

    created = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "pdm", "display_name": "Physical model"},
    )
    assert created.status_code == 201, created.text
    execution_result = write_execution_result(
        artifact.parent,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="physical-data-model",
                schema_version="knowledge_layer_physical_model/v1",
                materialization_id="physical-model",
                capabilities=(
                    "common.physical-model",
                    "common.physical-model.pdm",
                    "common.physical-model.tables",
                    "common.physical-model.columns",
                    "common.physical-model.keys",
                    "common.physical-model.relationships",
                    "common.physical-model.gaps",
                ),
            )
        ],
        scope_id="pdm",
        execution_token="run-pdm",
    )
    response = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/pdm/revisions",
        json=publication_payload(execution_result),
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def test_physical_model_http_contract(tmp_path: Path) -> None:
    artifact = _physical_model_artifact(tmp_path)
    settings = KnowledgeApiSettings(
        database_path=tmp_path / "knowledge-api.sqlite3",
        allowed_roots=(tmp_path,),
    )
    service = KnowledgeDomainService(settings)
    with TestClient(create_contract_app(service=service)) as client:
        revision_id = _publish(client, artifact)
        summary = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model",
            params={"revision_id": revision_id},
        )
        tables = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/tables",
            params={"revision_id": revision_id, "search": "country_code", "include_columns": "true"},
        )
        detail = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/tables/table-client",
            params={"revision_id": revision_id},
        )
        columns = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/columns",
            params={"revision_id": revision_id, "table_id": "table-client", "search": "country"},
        )
        keys = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/keys",
            params={"revision_id": revision_id, "table_id": "table-client", "key_kind": "primary"},
        )
        relationships = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/relationships",
            params={"revision_id": revision_id, "table_id": "table-client", "direction": "any"},
        )
        gaps = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/gaps",
            params={"revision_id": revision_id, "gap_kind": "unresolved_domain"},
        )
        missing = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/pdm/physical-model/tables/missing",
            params={"revision_id": revision_id},
        )

    assert summary.status_code == 200, summary.text
    assert summary.json()["counts"] == {"tables": 1, "columns": 2, "keys": 1, "relationships": 1, "gaps": 1}
    assert tables.status_code == 200, tables.text
    assert tables.json()["page"]["total"] == 1
    assert tables.json()["items"][0]["columns"][1]["column_code"] == "country_code"
    assert detail.status_code == 200, detail.text
    assert detail.json()["table"]["table_code"] == "t_client"
    assert detail.json()["keys"][0]["column_codes"] == ["client_id"]
    assert detail.json()["relationships"][0]["joins"][0]["parent_column_code"] == "client_id"
    assert columns.status_code == 200 and columns.json()["items"][0]["column_code"] == "country_code"
    assert keys.status_code == 200 and keys.json()["page"]["total"] == 1
    assert relationships.status_code == 200 and relationships.json()["page"]["total"] == 1
    assert gaps.status_code == 200 and gaps.json()["items"][0]["message"] == "Domain missing"
    assert missing.status_code == 404
    assert missing.json()["code"] == "physical_model_table_not_found"


def test_physical_model_rejects_invalid_direction_before_service(tmp_path: Path) -> None:
    settings = KnowledgeApiSettings(database_path=tmp_path / "knowledge-api.sqlite3", allowed_roots=(tmp_path,))
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/unknown/physical-model/relationships",
            params={"direction": "sideways"},
        )
    assert response.status_code == 422
