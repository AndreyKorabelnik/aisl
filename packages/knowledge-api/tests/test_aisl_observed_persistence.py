from __future__ import annotations

import json
import shutil
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings, sha256_file
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_api.publication import stable_fingerprint
from knowledge_layer_core.code_declared_model_schema import CODE_DECLARED_MODEL_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _write_derived_model(path: Path) -> None:
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


def _write_observed_java(path: Path, *, source_id: str = "repo") -> dict:
    payload = {
        "artifact_id": "java_type_structure_pilot",
        "artifact_kind": "java-type-structure-evidence",
        "schema_version": "java-type-structure-evidence/v1",
        "contract_version": "core_evidence_artifact_contract/v1",
        "content_fingerprint": "a" * 64,
        "producer": {"component": "code-analyzer-core", "analyzer_id": "java-type-structure-analyzer", "analyzer_version": "pilot"},
        "source_snapshot": {"source_id": source_id, "scope": "java_source_files", "fingerprint": "b" * 64, "file_count": 1, "revision": None},
        "coverage": {"coverage_status": "complete", "java_files_discovered": 1, "java_files_parsed": 1, "type_declaration_count": 1, "field_declaration_count": 1},
        "diagnostics": [],
        "provenance": {"execution_runtime": "core_evidence_runtime/v1", "parser_provider": "tree_sitter", "semantic_routing": "artifact_kind_plus_schema_version"},
        "payload": {
            "source_units": [{"source_unit_id": "unit-customer", "repository_relative_path": "src/Customer.java", "language": "java", "package_name": "com.acme", "imports": [], "parse_status": "success", "parse_error_count": 0}],
            "type_declarations": [{"type_id": "type-customer", "source_unit_id": "unit-customer", "fully_qualified_name": "com.acme.Customer", "simple_name": "Customer", "package_name": "com.acme", "type_kind": "class", "modifier_tokens": ["public"], "type_parameters": [], "source_ref": {"repository_relative_path": "src/Customer.java", "line_start": 1, "line_end": 20, "extractor": "java_tree_sitter"}}],
            "field_declarations": [{"field_id": "field-id", "owner_type_id": "type-customer", "name": "id", "declared_type_expression": "String", "modifier_tokens": ["private"], "is_static": False, "is_final": False, "source_ref": {"repository_relative_path": "src/Customer.java", "line_start": 3, "line_end": 3, "extractor": "java_tree_sitter"}}],
            "inheritance_declarations": [],
            "annotation_declarations": [],
            "type_reference_observations": [],
            "enum_constant_declarations": [],
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload



def _execution_with_multiple_observed_java(
    root: Path,
    *,
    token: str,
    items: list[tuple[str, str, str]],
) -> Path:
    execution = write_execution_result(root, [], scope_id="demo-multi-observed", execution_token=token)
    payload = json.loads(execution.read_text(encoding="utf-8"))
    evidence = []
    for artifact_id, source_id, content_fingerprint in items:
        observed_path = root / f"{artifact_id}.json"
        observed_payload = _write_observed_java(observed_path, source_id=source_id)
        observed_payload["artifact_id"] = artifact_id
        observed_payload["content_fingerprint"] = content_fingerprint
        observed_path.write_text(json.dumps(observed_payload, indent=2, sort_keys=True), encoding="utf-8")
        evidence.append({
            "artifact_id": artifact_id,
            "artifact_kind": observed_payload["artifact_kind"],
            "schema_version": observed_payload["schema_version"],
            "contract_version": observed_payload["contract_version"],
            "content_fingerprint": content_fingerprint,
            "coverage": observed_payload["coverage"],
            "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
            "provenance": {"producer": observed_payload["producer"], "source_snapshot": observed_payload["source_snapshot"]},
            "status": "completed",
            "location": {"kind": "file", "path": str(observed_path), "sha256": sha256_file(observed_path), "bytes": observed_path.stat().st_size},
        })
    payload["evidence_artifacts"] = evidence
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return execution


def test_multi_repository_observed_products_of_same_kind_publish_in_distinct_slots(tmp_path: Path) -> None:
    producer = tmp_path / "producer"; producer.mkdir()
    execution = _execution_with_multiple_observed_java(
        producer,
        token="multi-repository",
        items=[
            ("java-repo-a-v1", "repo-a", "1" * 64),
            ("java-repo-b-v1", "repo-b", "2" * 64),
        ],
    )
    catalog_dir = tmp_path / "aisl"
    settings = KnowledgeApiSettings(
        database_path=catalog_dir / "catalog.sqlite3",
        allowed_roots=(producer,),
        artifact_store_path=catalog_dir / "artifact-store",
    )
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-multi-observed", "display_name": "Demo"}).status_code == 201
        response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-multi-observed/revisions",
            json=publication_payload(execution),
        )
        assert response.status_code == 201, response.text
        products = {item["artifact_id"]: item for item in response.json()["revision"]["knowledge_artifacts"]}
        assert products["java-repo-a-v1"]["product_slot_id"] == "core:repo-a:java-type-structure-evidence"
        assert products["java-repo-b-v1"]["product_slot_id"] == "core:repo-b:java-type-structure-evidence"


def test_incremental_observed_replacement_is_scoped_to_source_repository(tmp_path: Path) -> None:
    base_workspace = tmp_path / "base"; base_workspace.mkdir()
    base_execution = _execution_with_multiple_observed_java(
        base_workspace,
        token="base-multi-repository",
        items=[
            ("java-repo-a-v1", "repo-a", "1" * 64),
            ("java-repo-b-v1", "repo-b", "2" * 64),
        ],
    )
    catalog_dir = tmp_path / "aisl"
    settings = KnowledgeApiSettings(
        database_path=catalog_dir / "catalog.sqlite3",
        allowed_roots=(tmp_path,),
        artifact_store_path=catalog_dir / "artifact-store",
    )
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-multi-observed", "display_name": "Demo"}).status_code == 201
        base_response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-multi-observed/revisions",
            json=publication_payload(base_execution),
        )
        assert base_response.status_code == 201, base_response.text
        base_revision_id = base_response.json()["revision"]["revision_id"]

        delta_workspace = tmp_path / "delta"; delta_workspace.mkdir()
        delta_execution = _execution_with_multiple_observed_java(
            delta_workspace,
            token="delta-repo-a",
            items=[("java-repo-a-v2", "repo-a", "3" * 64)],
        )
        delta_response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-multi-observed/revisions",
            json=publication_payload(delta_execution, base_revision_id=base_revision_id),
        )
        assert delta_response.status_code == 201, delta_response.text
        revision = delta_response.json()["revision"]
        ids = {item["artifact_id"] for item in revision["knowledge_artifacts"]}
        assert ids == {"java-repo-a-v2", "java-repo-b-v1"}
        slots = {item["artifact_id"]: item["product_slot_id"] for item in revision["knowledge_artifacts"]}
        assert slots["java-repo-a-v2"] == "core:repo-a:java-type-structure-evidence"
        assert slots["java-repo-b-v1"] == "core:repo-b:java-type-structure-evidence"


def test_duplicate_observed_product_for_same_source_and_kind_is_rejected(tmp_path: Path) -> None:
    producer = tmp_path / "producer"; producer.mkdir()
    execution = _execution_with_multiple_observed_java(
        producer,
        token="duplicate-source-slot",
        items=[
            ("java-repo-a-1", "repo-a", "1" * 64),
            ("java-repo-a-2", "repo-a", "2" * 64),
        ],
    )
    catalog_dir = tmp_path / "aisl"
    settings = KnowledgeApiSettings(
        database_path=catalog_dir / "catalog.sqlite3",
        allowed_roots=(producer,),
        artifact_store_path=catalog_dir / "artifact-store",
    )
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-multi-observed", "display_name": "Demo"}).status_code == 201
        response = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-multi-observed/revisions",
            json=publication_payload(execution),
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "observed_product_slot_ambiguous"
        assert response.json()["details"]["product_slot_id"] == "core:repo-a:java-type-structure-evidence"

def test_observed_and_derived_products_survive_producer_workspace_deletion(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    derived = producer / "code.duckdb"
    _write_derived_model(derived)
    execution = write_execution_result(
        producer,
        [KnowledgeArtifactSpec(derived, "code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model", ("common.code-declared-data-model",), artifact_id="code-product")],
        scope_id="demo",
        execution_token="observed-persistence",
    )
    observed_path = producer / "java-type-structure-evidence.json"
    observed_payload = _write_observed_java(observed_path)
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    execution_payload["evidence_artifacts"] = [{
        "artifact_id": observed_payload["artifact_id"],
        "artifact_kind": observed_payload["artifact_kind"],
        "schema_version": observed_payload["schema_version"],
        "contract_version": observed_payload["contract_version"],
        "content_fingerprint": observed_payload["content_fingerprint"],
        "coverage": observed_payload["coverage"],
        "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
        "provenance": {"producer": observed_payload["producer"], "source_snapshot": observed_payload["source_snapshot"]},
        "status": "completed",
        "location": {"kind": "file", "path": str(observed_path), "sha256": sha256_file(observed_path), "bytes": observed_path.stat().st_size},
    }]
    execution_payload["materialization_executions"][0]["input_artifact_ids"] = [observed_payload["artifact_id"]]
    execution_payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in execution_payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(execution_payload, indent=2, sort_keys=True), encoding="utf-8")

    catalog_dir = tmp_path / "aisl"
    store_dir = catalog_dir / "artifact-store"
    settings = KnowledgeApiSettings(database_path=catalog_dir / "catalog.sqlite3", allowed_roots=(producer,), artifact_store_path=store_dir)
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings)))
    with client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo", "display_name": "Demo"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo/revisions", json=publication_payload(execution))
        assert response.status_code == 201, response.text
        revision = response.json()["revision"]
        revision_id = revision["revision_id"]
        products = {item["artifact_id"]: item for item in revision["knowledge_artifacts"]}
        observed = products["java_type_structure_pilot"]
        derived_product = products["code-product"]
        assert observed["origin_kind"] == "observed"
        assert observed["product_slot_id"] == "core:repo:java-type-structure-evidence"
        assert derived_product["origin_kind"] == "derived"
        assert derived_product["product_slot_id"] == "klc:code-declared-data-model"
        assert derived_product["exact_dependency_product_ids"] == ["java_type_structure_pilot"]
        observed_roles = {item["role"]: item for item in observed["physical_artifacts"]}
        derived_roles = {item["role"]: item for item in derived_product["physical_artifacts"]}
        assert set(observed_roles) == {"descriptor"}
        assert {"database", "manifest"}.issubset(derived_roles)
        assert observed_roles["descriptor"]["uri"] == f"aisl+sha256://{observed_roles['descriptor']['sha256']}"
        assert derived_roles["database"]["uri"] == f"aisl+sha256://{derived_roles['database']['sha256']}"
        assert revision["execution_result"]["uri"] == f"aisl+sha256://{revision['execution_result']['sha256']}"

        observed_read = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/java_type_structure_pilot/type_declaration/type-customer", params={"revision_id": revision_id})
        assert observed_read.status_code == 200, observed_read.text
        assert observed_read.json()["item"]["fully_qualified_name"] == "com.acme.Customer"
        assert observed_read.json()["evidence_state"]["availability"] == "available"
        assert observed_read.json()["coverage_state"]["availability"] == "available"

        derived_read = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/code-product/declared_object/type-customer-occ", params={"revision_id": revision_id})
        assert derived_read.status_code == 200, derived_read.text
        assert derived_read.json()["item"]["fqcn"] == "com.acme.Customer"

        shutil.rmtree(producer)
        assert not producer.exists()

        observed_after = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/java_type_structure_pilot/type_declaration/type-customer", params={"revision_id": revision_id})
        derived_after = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo/knowledge-items/code-product/declared_object/type-customer-occ", params={"revision_id": revision_id})
        revision_after = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo/revisions/{revision_id}")
        assert observed_after.status_code == 200, observed_after.text
        assert derived_after.status_code == 200, derived_after.text
        assert revision_after.status_code == 200, revision_after.text
        assert observed_after.json()["item"] == observed_read.json()["item"]
        assert derived_after.json()["item"] == derived_read.json()["item"]



def _execution_with_observed(
    root: Path,
    *,
    token: str,
    observed_id: str,
    observed_content_identity: str,
    derived_model_kind: str,
    derived_schema: str,
    materialization_id: str,
    derived_artifact_id: str,
    derived_database: Path,
    derived_capabilities: tuple[str, ...],
    depends_on_observed: bool,
) -> Path:
    execution = write_execution_result(
        root,
        [KnowledgeArtifactSpec(
            derived_database,
            derived_model_kind,
            derived_schema,
            materialization_id,
            derived_capabilities,
            artifact_id=derived_artifact_id,
        )],
        scope_id="demo-cow",
        execution_token=token,
    )
    observed_path = root / f"{observed_id}.json"
    observed_payload = _write_observed_java(observed_path)
    observed_payload["artifact_id"] = observed_id
    observed_payload["content_fingerprint"] = observed_content_identity
    observed_path.write_text(json.dumps(observed_payload, indent=2, sort_keys=True), encoding="utf-8")
    payload = json.loads(execution.read_text(encoding="utf-8"))
    payload["evidence_artifacts"] = [{
        "artifact_id": observed_id,
        "artifact_kind": observed_payload["artifact_kind"],
        "schema_version": observed_payload["schema_version"],
        "contract_version": observed_payload["contract_version"],
        "content_fingerprint": observed_content_identity,
        "coverage": observed_payload["coverage"],
        "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
        "provenance": {"producer": observed_payload["producer"], "source_snapshot": observed_payload["source_snapshot"]},
        "status": "completed",
        "location": {"kind": "file", "path": str(observed_path), "sha256": sha256_file(observed_path), "bytes": observed_path.stat().st_size},
    }]
    if depends_on_observed:
        payload["materialization_executions"][0]["input_artifact_ids"] = [observed_id]
    payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return execution


def test_copy_on_write_rejects_stale_derived_product_after_observed_replacement(tmp_path: Path) -> None:
    base_workspace = tmp_path / "base-producer"; base_workspace.mkdir()
    base_db = base_workspace / "code-v1.duckdb"; _write_derived_model(base_db)
    base_execution = _execution_with_observed(
        base_workspace,
        token="base",
        observed_id="java-observed-a1",
        observed_content_identity="1" * 64,
        derived_model_kind="code-declared-data-model",
        derived_schema="code-declared-data-model/v1",
        materialization_id="code-declared-data-model",
        derived_artifact_id="code-derived-c1",
        derived_database=base_db,
        derived_capabilities=("common.code-declared-data-model",),
        depends_on_observed=True,
    )
    catalog_dir = tmp_path / "aisl"
    settings = KnowledgeApiSettings(
        database_path=catalog_dir / "catalog.sqlite3",
        allowed_roots=(tmp_path,),
        artifact_store_path=catalog_dir / "artifact-store",
    )
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-cow", "display_name": "Demo COW"}).status_code == 201
        base_response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-cow/revisions", json=publication_payload(base_execution))
        assert base_response.status_code == 201, base_response.text
        base_revision_id = base_response.json()["revision"]["revision_id"]

        invalid_workspace = tmp_path / "invalid-producer"; invalid_workspace.mkdir()
        unrelated_db = invalid_workspace / "unrelated.duckdb"; unrelated_db.write_bytes(b"unrelated-derived")
        invalid_execution = _execution_with_observed(
            invalid_workspace,
            token="invalid",
            observed_id="java-observed-a2",
            observed_content_identity="2" * 64,
            derived_model_kind="unrelated-derived",
            derived_schema="unrelated-derived/v1",
            materialization_id="unrelated-derived",
            derived_artifact_id="unrelated-d2",
            derived_database=unrelated_db,
            derived_capabilities=("common.unrelated",),
            depends_on_observed=False,
        )
        rejected = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-cow/revisions",
            json=publication_payload(invalid_execution, base_revision_id=base_revision_id),
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["code"] == "revision_exact_dependency_unresolved"
        assert rejected.json()["details"]["products"]["code-derived-c1"] == ["java-observed-a1"]

        valid_workspace = tmp_path / "valid-producer"; valid_workspace.mkdir()
        valid_db = valid_workspace / "code-v2.duckdb"; _write_derived_model(valid_db)
        valid_execution = _execution_with_observed(
            valid_workspace,
            token="valid",
            observed_id="java-observed-a2",
            observed_content_identity="2" * 64,
            derived_model_kind="code-declared-data-model",
            derived_schema="code-declared-data-model/v1",
            materialization_id="code-declared-data-model",
            derived_artifact_id="code-derived-c2",
            derived_database=valid_db,
            derived_capabilities=("common.code-declared-data-model",),
            depends_on_observed=True,
        )
        accepted = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/demo-cow/revisions",
            json=publication_payload(valid_execution, base_revision_id=base_revision_id),
        )
        assert accepted.status_code == 201, accepted.text
        revision = accepted.json()["revision"]
        ids = {item["artifact_id"] for item in revision["knowledge_artifacts"]}
        assert "java-observed-a1" not in ids
        assert "code-derived-c1" not in ids
        assert {"java-observed-a2", "code-derived-c2"}.issubset(ids)
        c2 = next(item for item in revision["knowledge_artifacts"] if item["artifact_id"] == "code-derived-c2")
        assert c2["exact_dependency_product_ids"] == ["java-observed-a2"]


def test_published_revision_survives_artifact_store_root_relocation_without_republication(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    producer.mkdir()
    derived = producer / "code.duckdb"
    _write_derived_model(derived)
    execution = write_execution_result(
        producer,
        [KnowledgeArtifactSpec(derived, "code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model", ("common.code-declared-data-model",), artifact_id="code-product")],
        scope_id="demo-mobility",
        execution_token="storage-mobility",
    )
    observed_path = producer / "java-type-structure-evidence.json"
    observed_payload = _write_observed_java(observed_path)
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    execution_payload["evidence_artifacts"] = [{
        "artifact_id": observed_payload["artifact_id"],
        "artifact_kind": observed_payload["artifact_kind"],
        "schema_version": observed_payload["schema_version"],
        "contract_version": observed_payload["contract_version"],
        "content_fingerprint": observed_payload["content_fingerprint"],
        "coverage": observed_payload["coverage"],
        "diagnostics": {"count": 0, "code_counts": {}, "severity_counts": {}},
        "provenance": {"producer": observed_payload["producer"], "source_snapshot": observed_payload["source_snapshot"]},
        "status": "completed",
        "location": {"kind": "file", "path": str(observed_path), "sha256": sha256_file(observed_path), "bytes": observed_path.stat().st_size},
    }]
    execution_payload["materialization_executions"][0]["input_artifact_ids"] = [observed_payload["artifact_id"]]
    execution_payload["result_fingerprint"] = stable_fingerprint({k: v for k, v in execution_payload.items() if k != "result_fingerprint"})
    execution.write_text(json.dumps(execution_payload, indent=2, sort_keys=True), encoding="utf-8")

    catalog = tmp_path / "aisl" / "catalog.sqlite3"
    old_store = tmp_path / "aisl" / "artifact-store-a"
    settings_a = KnowledgeApiSettings(database_path=catalog, allowed_roots=(producer,), artifact_store_path=old_store)
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings_a))) as client:
        assert client.post(f"{KNOWLEDGE_API_PREFIX}/systems", json={"system_id": "demo-mobility", "display_name": "Demo Mobility"}).status_code == 201
        response = client.post(f"{KNOWLEDGE_API_PREFIX}/systems/demo-mobility/revisions", json=publication_payload(execution))
        assert response.status_code == 201, response.text
        before = response.json()["revision"]
        revision_id = before["revision_id"]
        product_identities = {
            item["artifact_id"]: (item["content_fingerprint"], tuple((p["role"], p["sha256"], p["uri"]) for p in item["physical_artifacts"]))
            for item in before["knowledge_artifacts"]
        }
        assert all(uri.startswith("aisl+sha256://") for _, members in product_identities.values() for _, _, uri in members)

    # Producer is gone before storage relocation. Only AISL Catalog + Store remain.
    shutil.rmtree(producer)
    assert not producer.exists()
    new_store = tmp_path / "relocated" / "artifact-store-b"
    new_store.parent.mkdir(parents=True)
    old_store.rename(new_store)
    assert not old_store.exists()

    settings_b = KnowledgeApiSettings(database_path=catalog, allowed_roots=(tmp_path / "unused-producer-root",), artifact_store_path=new_store)
    with TestClient(create_contract_app(service=KnowledgeDomainService(settings_b))) as client:
        revision_response = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-mobility/revisions/{revision_id}")
        assert revision_response.status_code == 200, revision_response.text
        after = revision_response.json()
        assert after["revision_id"] == revision_id
        assert after["knowledge_artifacts"] == before["knowledge_artifacts"]
        after_identities = {
            item["artifact_id"]: (item["content_fingerprint"], tuple((p["role"], p["sha256"], p["uri"]) for p in item["physical_artifacts"]))
            for item in after["knowledge_artifacts"]
        }
        assert after_identities == product_identities

        observed_read = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-mobility/knowledge-items/java_type_structure_pilot/type_declaration/type-customer", params={"revision_id": revision_id})
        derived_read = client.get(f"{KNOWLEDGE_API_PREFIX}/systems/demo-mobility/knowledge-items/code-product/declared_object/type-customer-occ", params={"revision_id": revision_id})
        assert observed_read.status_code == 200, observed_read.text
        assert derived_read.status_code == 200, derived_read.text
        assert observed_read.json()["item"]["fully_qualified_name"] == "com.acme.Customer"
        assert derived_read.json()["item"]["fqcn"] == "com.acme.Customer"
