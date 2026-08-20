from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.code_declared_model_schema import CODE_DECLARED_MODEL_DDL
from knowledge_layer_core.logical_physical_mapping_schema import LOGICAL_PHYSICAL_MAPPING_DDL
from knowledge_layer_core.physical_model_schema import PHYSICAL_MODEL_DDL
from knowledge_layer_core.subject_knowledge_schema import SUBJECT_KNOWLEDGE_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _write_code(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(CODE_DECLARED_MODEL_DDL)
        con.execute("INSERT INTO code_declared_model_build VALUES ('b','scope','test','code-declared-data-model/v1','java-type-structure-evidence/v1','complete',now(),now(),'{}','{}')")
        con.execute(
            "INSERT INTO code_declared_type VALUES ('type-customer-occ','src','repo','type-customer','uuid','com.acme.Customer','Customer','com.acme','class',NULL,'main','[]','[]','{}',?, '{}')",
            [json.dumps({"repository_relative_path": "src/Customer.java", "line_start": 1, "line_end": 20})],
        )
    finally:
        con.close()


def _write_physical(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(PHYSICAL_MODEL_DDL)
        con.execute("INSERT INTO physical_model_build VALUES ('b','scope','test','knowledge_layer_physical_model/v1','physical-model/v1','f','complete',now(),now(),'{}','{}')")
        con.execute("INSERT INTO physical_model_source VALUES ('pdm-src','manifest','physical-model/v1','f','test','model.pdm','sha','m','Model','M','16','DBMS','complete',0,'{}','{}')")
        con.execute(
            "INSERT INTO physical_model_table (physical_model_table_id,physical_model_source_id,pdm_object_id,table_name,table_code,source_file,evidence_json,payload_json) VALUES ('table-client','pdm-src','pdm-table-1','CLIENT','CLIENT','model.pdm','{}','{}')"
        )
    finally:
        con.close()


def _write_persistence(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(SUBJECT_KNOWLEDGE_DDL)
        con.execute("INSERT INTO subject_knowledge_build VALUES ('b','scope','persistence-lineage','test','subject-knowledge-records/v1','persistence-lineage-evidence/v1','f','complete',now(),now(),'{}','{}')")
        con.execute("INSERT INTO subject_knowledge_source VALUES ('src','scope','repo','persistence-lineage','ev','persistence-lineage-evidence','persistence-lineage-evidence/v1','ev.json','f','{}','{}','[]','{}')")
        payload = json.dumps({
            "source_to_storage_lineage_id": "s2s-1",
            "source_operation": "CustomerService.save",
            "source_payload": "CustomerRequest",
            "source_field": "clientId",
            "storage_target": "DEVICE_LINK",
            "storage_field": "CLIENT_ID",
            "lineage_status": "confirmed",
            "evidence_maturity_level": "confirmed",
            "evidence": [{"file": "src/CustomerService.java", "line_start": 20, "line_end": 22, "extractor": "test"}],
        })
        gap = json.dumps({
            "storage_lineage_gap_id": "gap-1",
            "gap_kind": "storage_target_unresolved",
            "reason": "storage target was not resolved",
            "missing_links": ["physical storage"],
            "source_inspection_required": True,
            "source_inspection_request_ids": ["inspect-1"],
            "evidence": [{"file": "src/Gap.java", "line_start": 7, "line_end": 7}],
        })
        con.execute("INSERT INTO subject_knowledge_record VALUES ('occ-s2s','src','scope','repo','persistence-lineage','source_to_storage_lineage.json','source_to_storage_lineage','s2s-1',1,'clientId DEVICE_LINK CLIENT_ID',?)", [payload])
        con.execute("INSERT INTO subject_knowledge_record VALUES ('occ-gap','src','scope','repo','persistence-lineage','storage_lineage_gaps.json','storage_lineage_gaps','gap-1',2,'unresolved storage',?)", [gap])
    finally:
        con.close()


def _write_mapping(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(LOGICAL_PHYSICAL_MAPPING_DDL)
        con.execute("INSERT INTO logical_physical_mapping_build VALUES ('b','scope','test','logical-physical-model-mapping/v1','java-persistence-mapping-evidence/v1','complete',now(),now(),'{}','{}')")
        con.execute(
            """INSERT INTO logical_physical_mapping_source
               (mapping_source_id,scope_id,evidence_artifact_id,evidence_content_fingerprint,evidence_path,
                code_declared_artifact_id,code_declared_content_fingerprint,code_declared_output_path,
                physical_model_artifact_id,physical_model_content_fingerprint,physical_model_output_path,
                evidence_coverage_json,evidence_diagnostics_json,source_snapshot_json,payload_json)
               VALUES ('src-map','scope','ev','e','ev.json','code-product','c','code','physical-product','p','physical','{}','[]','{}','{}')"""
        )
        con.execute(
            """INSERT INTO logical_physical_entity_mapping
               (entity_mapping_id,mapping_source_id,repo_id,persistence_type_mapping_id,logical_type_id,
                logical_type_occurrence_id,logical_fully_qualified_name,persistence_kind,declared_table_name,
                physical_model_table_id,physical_table_name,physical_table_code,mapping_status,mapping_basis,
                candidate_physical_table_ids_json,diagnostics_json,source_ref_json,payload_json)
               VALUES ('map-entity-1','src-map','repo','persist-1','type-customer','type-customer-occ','com.acme.Customer',
                       'entity','CLIENT','table-client','CLIENT','CLIENT','matched','explicit_table_annotation',
                       '[]','[]',?, '{}')""",
            [json.dumps({"repository_relative_path": "src/Customer.java", "line_start": 5, "line_end": 5})],
        )
    finally:
        con.close()


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    code = tmp_path / "code.duckdb"; _write_code(code)
    physical = tmp_path / "physical.duckdb"; _write_physical(physical)
    mapping = tmp_path / "mapping.duckdb"; _write_mapping(mapping)
    persistence = tmp_path / "persistence.duckdb"; _write_persistence(persistence)
    result = write_execution_result(tmp_path, [
        KnowledgeArtifactSpec(code, "code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model", ("common.code-declared-data-model",), artifact_id="code-product"),
        KnowledgeArtifactSpec(physical, "physical-data-model", "knowledge_layer_physical_model/v1", "physical-model", ("common.physical-model",), artifact_id="physical-product"),
        KnowledgeArtifactSpec(mapping, "logical-physical-model-mapping", "logical-physical-model-mapping/v1", "logical-physical-mapping", ("common.logical-physical-mapping",), artifact_id="mapping-product"),
        KnowledgeArtifactSpec(persistence, "persistence-lineage", "persistence-lineage/v1", "persistence-lineage", ("workspace.persistence-lineage",), artifact_id="persistence-product"),
    ], scope_id="demo", execution_token="aisl-read")
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings))); client.__enter__()
    assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo", "display_name": "Demo"}).status_code == 201
    pub = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/revisions", json=publication_payload(result))
    assert pub.status_code == 201, pub.text
    return client, pub.json()["revision"]["revision_id"]


def test_mapping_item_projects_exact_cross_product_correspondence(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/mapping-product/entity_mapping/map-entity-1",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["projection_status"] == "available"
        assert body["correspondences_state"]["availability"] == "available"
        corr = body["correspondences"][0]
        assert corr["relation_kind"] == "maps_to"
        assert corr["resolution_status"] == "resolved"
        assert corr["source_ref"]["product_id"] == "code-product"
        assert corr["source_ref"]["item_kind"] == "declared_object"
        assert corr["source_ref"]["local_id"] == "type-customer-occ"
        assert corr["target_ref"]["product_id"] == "physical-product"
        assert corr["target_ref"]["item_kind"] == "physical_table"
        assert corr["target_ref"]["local_id"] == "table-client"
        assert body["evidence_state"]["availability"] == "available"
    finally:
        client.__exit__(None, None, None)


def test_unknown_product_kind_returns_explicit_unsupported_projection(tmp_path: Path) -> None:
    # Reuse a valid revision, but request a product whose model kind has no universal projector.
    client, revision_id = _client(tmp_path)
    try:
        # code product is supported, so use an unsupported item kind to verify explicit projection state.
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/code-product/invented_kind/x",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["projection_status"] == "unsupported"
        assert body["evidence_state"]["availability"] == "unsupported"
        assert body["item"] is None if "item" in body else True
    finally:
        client.__exit__(None, None, None)


def test_physical_table_item_is_addressable_without_cross_product_guessing(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/physical-product/physical_table/table-client",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["item"]["table_code"] == "CLIENT"
        assert body["item_ref"]["product_id"] == "physical-product"
        assert body["correspondences_state"]["availability"] == "unsupported"
        assert body["correspondences"] == []
    finally:
        client.__exit__(None, None, None)


def test_persistence_lineage_item_is_exactly_addressable_without_maps_to_guess(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/persistence-product/source_to_storage_lineage/s2s-1",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["projection_status"] == "available"
        assert body["item"]["source_field"] == "clientId"
        assert body["item"]["storage_target"] == "DEVICE_LINK"
        assert body["item"]["storage_field"] == "CLIENT_ID"
        assert body["evidence_state"]["availability"] == "available"
        assert body["source_fragments"][0]["locator"] == "src/CustomerService.java:20-22"
        assert body["correspondences_state"]["availability"] == "unsupported"
        assert body["correspondences"] == []
    finally:
        client.__exit__(None, None, None)


def test_persistence_lineage_gap_is_visible_as_issue(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/persistence-product/storage_lineage_gap/gap-1",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["issues_state"]["availability"] == "available"
        assert body["issues"][0]["kind"] == "missing_information"
        assert body["issues"][0]["details"]["missing_links"] == ["physical storage"]
    finally:
        client.__exit__(None, None, None)
