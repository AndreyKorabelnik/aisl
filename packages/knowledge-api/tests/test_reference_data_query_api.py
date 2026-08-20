from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.materialization_runtime import materialize
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result

CAPABILITIES = ("common.reference-data", "common.declared-value-sets", "common.reference-data-facts")


def _artifact(tmp_path: Path) -> Path:
    evidence_root = tmp_path / "evidence"
    detail = evidence_root / "subject-knowledge-payload" / "compact" / "reference_data_fact_base"
    detail.mkdir(parents=True)
    rows = {
        "declared_value_sets.jsonl": [{"fact_id":"set-status","fact_type":"declared_value_set","name":"Status","properties":{"declared_value_set_id":"status-values","syntax_kind":"java_enum","entries_count":2,"sample_entries":[{"key":"A","value":"ACTIVE"},{"key":"B","value":"BLOCKED"}],"source_set":"production"},"evidence":[{"file_path":"src/Status.java","line_start":1,"line_end":4,"extractor":"declared_value_scan"}]}],
        "literal_data_writes.jsonl": [{"fact_id":"write-country","fact_type":"literal_data_write","name":"COUNTRY","properties":{"literal_data_write_id":"write-country","target_table":"COUNTRY","qualified_table_name":"COUNTRY","operation":"insert","columns":["CODE","NAME"],"source_set":"production"},"evidence":[{"file_path":"db/country.sql","line_start":1,"line_end":3,"extractor":"literal_write"}]}],
        "physical_assets.jsonl": [{"fact_id":"table-country","fact_type":"db_schema_table","name":"COUNTRY","properties":{"table_name":"COUNTRY","qualified_table_name":"COUNTRY","description":"Country codes","source_set":"production"},"evidence":[{"file_path":"db/country-ddl.sql","line_start":1,"line_end":3,"extractor":"sql_create_table"}]}],
    }
    sections=[]
    for name, values in rows.items():
        p=detail/name
        p.write_text("".join(json.dumps(v)+"\n" for v in values),encoding="utf-8")
        sections.append({"section":name[:-6],"relative_path":p.relative_to(evidence_root).as_posix(),"records_count":len(values),"format":"jsonl"})
    envelope=evidence_root/"reference-data-evidence.json"
    content={"contract_version":"core_evidence_artifact_contract/v1","artifact_id":"ref-demo","artifact_kind":"reference-data-evidence","schema_version":"reference-data-evidence/v1","content_fingerprint":"ref-fp","source_snapshot":{"source_id":"demo","fingerprint":"source-fp"},"coverage":{"coverage_status":"complete"},"diagnostics":[],"provenance":{},"payload":{"sections":sections}}
    envelope.write_text(json.dumps(content),encoding="utf-8")
    result=materialize({"schema_version":"knowledge_materialization_request/v1","materialization_id":"reference-data","scope_id":"demo","inputs":{"evidence_artifacts":[{"artifact_id":"ref-demo","artifact_kind":"reference-data-evidence","schema_version":"reference-data-evidence/v1","content_fingerprint":"ref-fp","location":{"kind":"file","path":str(envelope)}}],"knowledge_artifacts":[]},"parameters":{}},tmp_path/"knowledge")
    assert result["status"]=="completed"
    return tmp_path/"knowledge"/"knowledge-layer.duckdb"


def _client(tmp_path: Path, capabilities=CAPABILITIES):
    artifact=_artifact(tmp_path)
    result=write_execution_result(tmp_path,[KnowledgeArtifactSpec(database=artifact,model_kind="reference-data",schema_version="reference-data/v1",materialization_id="reference-data",capabilities=capabilities)],profile_id="reference-data",scope_id="demo",execution_token="run-ref")
    settings=KnowledgeApiSettings(database_path=tmp_path/"api.sqlite3",allowed_roots=(tmp_path,))
    c=TestClient(create_contract_app(service=KnowledgeDomainService(settings))); c.__enter__()
    assert c.post(f"{KNOWLEDGE_API_PREFIX}/systems",json={"system_id":"demo","display_name":"Demo"}).status_code==201
    pub=c.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/revisions",json=publication_payload(result)); assert pub.status_code==201,pub.text
    return c,pub.json()["revision"]["revision_id"]


def test_reference_data_query_is_standalone_and_facts_only(tmp_path: Path):
    c,rid=_client(tmp_path)
    try:
        r=c.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/query",json={"revision_id":rid,"query_kind":"search_reference_data","filters":{"token":"COUNTRY"},"max_results":20})
        assert r.status_code==200,r.text
        p=r.json(); assert p["summary"]["official_nsi_status_established"] is False
        assert p["summary"]["dictionary_object_enrichment_available"] is False
        assert any(x["representation_kind"]=="literal_populated_storage_target" for x in p["items"])
        ctx=c.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/query",json={"revision_id":rid,"query_kind":"get_candidate_context","filters":{"token":"COUNTRY"},"max_results":20})
        assert ctx.status_code==200,ctx.text
        cp=ctx.json(); assert cp["summary"]["own_nsi_status_established"] is False
        assert cp["summary"]["local_definition_evidence_count"] >= 1
        assert cp["items"][0]["interpretation_policy"]["local_definition_evidence_is_context_local"] is True
        assert any(x["observation_kind"]=="physical_assets" for x in cp["items"][0]["usage_observations"])
        bad=c.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/query",json={"revision_id":rid,"query_kind":"search_reference_data","filters":{"official_nsi":True},"max_results":20})
        assert bad.status_code==422
    finally: c.__exit__(None,None,None)



def test_reference_data_guidance_is_compact_and_never_assigns_nsi_semantics(tmp_path: Path):
    c, rid = _client(tmp_path)
    try:
        discovery = c.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/guidance",
            params={"revision_id": rid},
        )
        assert discovery.status_code == 200, discovery.text
        payload = discovery.json()
        assert payload["guidance_schema_version"] == "reference-data-guidance/v1"
        assert payload["revision_id"] == rid
        assert payload["projection"]["semantic_derivation"] == "none"
        assert payload["summary"]["official_nsi_status_established"] is False
        assert payload["candidate_representations"]
        assert all(item.get("own_nsi_status") != "confirmed" for item in payload["candidate_representations"])
        assert all("declared_values" not in item for item in payload["candidate_representations"])

        exact = c.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/guidance",
            params={"revision_id": rid, "token": "COUNTRY", "usage_limit": 1, "gap_limit": 1},
        )
        assert exact.status_code == 200, exact.text
        context = exact.json()
        assert context["token"] == "COUNTRY"
        assert context["summary"]["own_nsi_status_established"] is False
        assert context["interpretation_policy"]["reference_semantics_assigned"] is False
        assert context["interpretation_policy"]["own_nsi_status_assigned"] is False
        assert context["interpretation_policy"]["global_definition_authority_established"] is False
        assert context["local_definition_evidence"]
        assert context["projection"]["semantic_derivation"] == "none"
    finally:
        c.__exit__(None, None, None)


def test_reference_data_guidance_control_value_set_is_not_promoted(tmp_path: Path):
    c, rid = _client(tmp_path)
    try:
        response = c.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo/reference-data/guidance",
            params={"revision_id": rid, "token": "Status"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["summary"]["semantic_classification_performed"] is False
        assert payload["summary"]["own_nsi_status_established"] is False
        assert payload["candidate_representations"]
        assert payload["candidate_representations"][0]["representation_kind"] == "declared_value_set"
        assert payload["candidate_representations"][0]["own_nsi_status"] == "not_assigned"
    finally:
        c.__exit__(None, None, None)
