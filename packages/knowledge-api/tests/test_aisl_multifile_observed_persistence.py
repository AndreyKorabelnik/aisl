from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings, sha256_file
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_api.publication import build_publication_request, stable_fingerprint
from tests.execution_fixtures import write_execution_result


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_sql_observed_package(root: Path) -> tuple[Path, dict[str, object], dict[str, dict[str, object]]]:
    evidence = root / "evidence"
    package = evidence / "sql-analysis"
    facts = package / "facts"
    facts.mkdir(parents=True)
    statement = {
        "fact_type": "sql_statement",
        "sql_statement_id": "query-demo-1",
        "repo_id": "repo-sql",
        "file": "model.sql",
        "line_start": 1,
        "line_end": 4,
        "operation": "select",
        "evidence_maturity_level": "confirmed",
        "evidence": [{"extractor": "sql_profile", "relative_file": "model.sql", "line_start": 1, "line_end": 4}],
    }
    join = {
        "fact_type": "sql_join_edge",
        "sql_join_edge_id": "join-demo-1",
        "repo_id": "repo-sql",
        "file": "model.sql",
        "line_start": 3,
        "predicate": "a.id = b.id",
        "resolution_status": "confirmed",
        "evidence_maturity_level": "confirmed",
        "evidence": [{"extractor": "sql_profile_scoped_ast", "relative_file": "model.sql", "line_start": 3}],
    }
    rows = {"sql_statement": statement, "sql_join_edge": join}
    entries = []
    descriptor_entries = []
    for fact_type, id_field in (("sql_statement", "sql_statement_id"), ("sql_join_edge", "sql_join_edge_id")):
        path = facts / f"{fact_type}.jsonl"
        payload = (json.dumps(rows[fact_type], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        entry = {"fact_type": fact_type, "id_field": id_field, "path": f"facts/{fact_type}.jsonl", "record_count": 1, "sha256": digest, "byte_size": len(payload)}
        entries.append(entry)
        descriptor_entries.append({**entry, "path": f"sql-analysis/facts/{fact_type}.jsonl"})
    coverage = {"schema_version": "sql-analysis/v1", "analysis_status": "complete", "source_inventory": {"files_scanned": 1, "sql_units": 1, "sql_statements": 1}}
    coverage_bytes = _json_bytes(coverage)
    coverage_path = package / "coverage.json"
    coverage_path.write_bytes(coverage_bytes)
    coverage_sha = hashlib.sha256(coverage_bytes).hexdigest()
    canonical_fingerprint = "c" * 64
    manifest = {
        "artifact": "sql_analysis",
        "contract_version": "1.0",
        "schema_version": "sql-analysis/v1",
        "analysis_status": "complete",
        "repository": {"repo_id": "repo-sql", "system_name": "demo", "project_code": "UNKNOWN"},
        "producer": {"name": "code-analyzer-core", "version": "test"},
        "facts": entries,
        "coverage": {"path": "coverage.json", "sha256": coverage_sha, "byte_size": len(coverage_bytes)},
        "content_fingerprint": canonical_fingerprint,
    }
    (package / "manifest.json").write_bytes(_json_bytes(manifest))
    envelope = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_kind": "sql-analysis",
        "schema_version": "sql-analysis/v1",
        "producer": {"component": "code-analyzer-core", "analyzer_id": "sql-analysis-analyzer", "analyzer_version": "test"},
        "source_snapshot": {"source_id": "repo-sql", "revision": None, "fingerprint": "b" * 64, "scope": "sql_analysis_sources", "file_count": 1},
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {},
        "coverage": {"coverage_status": "complete", "sql_files_scanned": 1, "sql_unit_count": 1, "sql_statement_count": 1, "lineage_gap_count": 0},
        "diagnostics": [],
        "provenance": {"execution_runtime": "core_evidence_runtime/v1", "semantic_routing": "artifact_kind_plus_schema_version", "canonical_payload_contract": "sql-analysis/v1-jsonl-shards"},
        "payload": {"canonical_manifest_path": "sql-analysis/manifest.json", "canonical_content_fingerprint": canonical_fingerprint, "analysis_status": "complete", "fact_shards": descriptor_entries, "coverage_path": "sql-analysis/coverage.json"},
        "content_fingerprint": "a" * 64,
        "artifact_id": "sql_analysis_multifile_pilot",
    }
    descriptor = evidence / "sql-analysis-evidence.json"
    descriptor.write_bytes(_json_bytes(envelope))
    return descriptor, envelope, rows


def _execution_with_sql_observed(root: Path, *, observed_status: str = "completed") -> tuple[Path, dict[str, dict[str, object]]]:
    execution = write_execution_result(root, [], scope_id="demo-sql", execution_token="sql-multifile")
    descriptor, envelope, rows = _write_sql_observed_package(root)
    if observed_status == "partial":
        envelope["coverage"]["coverage_status"] = "partial"
        envelope["coverage"]["lineage_gap_count"] = 1
        descriptor.write_bytes(_json_bytes(envelope))
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["evidence_artifacts"] = [{
        "artifact_id": envelope["artifact_id"],
        "artifact_kind": envelope["artifact_kind"],
        "schema_version": envelope["schema_version"],
        "contract_version": envelope["contract_version"],
        "content_fingerprint": envelope["content_fingerprint"],
        "coverage": envelope["coverage"],
        "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
        "provenance": {"producer": envelope["producer"], "source_snapshot": envelope["source_snapshot"]},
        "status": observed_status,
        "location": {"kind": "file", "path": str(descriptor), "sha256": sha256_file(descriptor), "bytes": descriptor.stat().st_size},
    }]
    payload["result_fingerprint"] = stable_fingerprint({key: value for key, value in payload.items() if key != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return execution, rows


def _publication_json(execution: Path) -> dict:
    request, warnings = build_publication_request(execution_result=execution, labels=(), metadata={}, activate=True)
    assert warnings == []
    return request.model_dump(mode="json")


def test_sql_multifile_observed_product_survives_producer_deletion(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    execution, rows = _execution_with_sql_observed(producer)
    aisl = tmp_path / "aisl"
    store = aisl / "artifact-store"
    settings = KnowledgeApiSettings(database_path=aisl / "catalog.sqlite3", allowed_roots=(producer,), artifact_store_path=store)
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-sql", "display_name": "Demo SQL"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/revisions", json=_publication_json(execution))
        assert response.status_code == 201, response.text
        revision = response.json()["revision"]
        revision_id = revision["revision_id"]
        product = revision["knowledge_artifacts"][0]
        assert product["artifact_id"] == "sql_analysis_multifile_pilot"
        assert product["origin_kind"] == "observed"
        assert product["product_slot_id"] == "core:repo-sql:sql-analysis"
        roles = {item["role"]: item for item in product["physical_artifacts"]}
        assert set(roles) == {"descriptor", "manifest", "coverage", "fact:sql_statement", "fact:sql_join_edge"}
        assert all(item["uri"] == f"aisl+sha256://{item['sha256']}" for item in roles.values())
        assert len({item["sha256"] for item in roles.values()}) == len(roles)

        statement = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/knowledge-items/sql_analysis_multifile_pilot/sql_statement/query-demo-1", params={"revision_id": revision_id})
        join = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/knowledge-items/sql_analysis_multifile_pilot/sql_join_edge/join-demo-1", params={"revision_id": revision_id})
        assert statement.status_code == 200, statement.text
        assert join.status_code == 200, join.text
        assert statement.json()["item"] == rows["sql_statement"]
        assert join.json()["item"] == rows["sql_join_edge"]
        assert statement.json()["evidence_state"]["availability"] == "available"
        assert statement.json()["coverage_state"]["availability"] == "available"

        shutil.rmtree(producer)
        assert not producer.exists()
        statement_after = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/knowledge-items/sql_analysis_multifile_pilot/sql_statement/query-demo-1", params={"revision_id": revision_id})
        join_after = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/knowledge-items/sql_analysis_multifile_pilot/sql_join_edge/join-demo-1", params={"revision_id": revision_id})
        assert statement_after.status_code == 200, statement_after.text
        assert join_after.status_code == 200, join_after.text
        assert statement_after.json()["item"] == rows["sql_statement"]
        assert join_after.json()["item"] == rows["sql_join_edge"]


def test_sql_multifile_publication_rejects_tampered_shard(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    execution, _ = _execution_with_sql_observed(producer)
    shard = producer / "evidence/sql-analysis/facts/sql_join_edge.jsonl"
    shard.write_text(shard.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    aisl = tmp_path / "aisl"
    settings = KnowledgeApiSettings(database_path=aisl / "catalog.sqlite3", allowed_roots=(producer,), artifact_store_path=aisl / "artifact-store")
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-sql", "display_name": "Demo SQL"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/revisions", json=_publication_json(execution))
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "observed_artifact_size_mismatch"


def test_partial_sql_observed_product_is_published_without_status_promotion(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    execution, _ = _execution_with_sql_observed(producer, observed_status="partial")
    aisl = tmp_path / "aisl"
    settings = KnowledgeApiSettings(database_path=aisl / "catalog.sqlite3", allowed_roots=(producer,), artifact_store_path=aisl / "artifact-store")
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-sql", "display_name": "Demo SQL"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/revisions", json=_publication_json(execution))
        assert response.status_code == 201, response.text
        product = response.json()["revision"]["knowledge_artifacts"][0]
        assert product["origin_kind"] == "observed"
        # Publication does not turn partial evidence into a stronger semantic status.
        assert product["coverage"]["coverage_status"] == "partial"
        assert product["coverage"]["lineage_gap_count"] == 1


def test_failed_sql_observed_product_is_not_publishable(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    execution, _ = _execution_with_sql_observed(producer, observed_status="failed")
    aisl = tmp_path / "aisl"
    settings = KnowledgeApiSettings(database_path=aisl / "catalog.sqlite3", allowed_roots=(producer,), artifact_store_path=aisl / "artifact-store")
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-sql", "display_name": "Demo SQL"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-sql/revisions", json=_publication_json(execution))
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "observed_artifact_incomplete"
