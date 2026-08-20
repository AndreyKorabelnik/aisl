from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from knowledge_api.contract_v1.contract import KNOWLEDGE_API_PREFIX, create_contract_app
from knowledge_api.contract_v1.runtime import KnowledgeApiSettings
from knowledge_api.contract_v1.service import KnowledgeDomainService
from knowledge_layer_core.code_declared_model_schema import CODE_DECLARED_MODEL_DDL
from tests.execution_fixtures import KnowledgeArtifactSpec, publication_payload, write_execution_result


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "code-declared.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(CODE_DECLARED_MODEL_DDL)
        con.execute(
            "INSERT INTO code_declared_model_build VALUES "
            "('b','scope','test','code-declared-data-model/v1','java-type-structure-evidence/v1','complete',now(),now(),'{}','{}')"
        )
        con.execute(
            "INSERT INTO code_declared_type VALUES "
            "('t-ind','s','repo','type-ind','u','com.acme.Individual','Individual','com.acme','class',NULL,'main','[]','[]',?, ?, '{}')",
            [
                json.dumps({"display_name": "Физическое лицо"}, ensure_ascii=False),
                json.dumps({"repository_relative_path": "Individual.java", "line_start": 1, "line_end": 50}),
            ],
        )
        con.execute(
            "INSERT INTO code_declared_type VALUES "
            "('t-country','s','repo','type-country','u','com.acme.Country','Country','com.acme','class',NULL,'main','[]','[]',?, ?, '{}')",
            [
                json.dumps({"display_name": "Страна"}, ensure_ascii=False),
                json.dumps({"repository_relative_path": "Country.java", "line_start": 1, "line_end": 20}),
            ],
        )
        con.execute(
            "INSERT INTO code_declared_type VALUES "
            "('t-segment','s','repo','type-segment','u','com.acme.Segment','Segment','com.acme','class',NULL,'main','[]','[]',?, ?, '{}')",
            [
                json.dumps({"summary": "Сегмент"}, ensure_ascii=False),
                json.dumps({"repository_relative_path": "Segment.java", "line_start": 1, "line_end": 20}),
            ],
        )
        con.execute(
            "INSERT INTO code_declared_field VALUES "
            "('f-service','s','repo','field-service','t-ind','serviceStartDate','LocalDate',NULL,false,false,false,'[]',?, ?, '{}')",
            [
                json.dumps({"description": "Дата начало обслуживания клиента"}, ensure_ascii=False),
                json.dumps({"repository_relative_path": "Individual.java", "line_start": 11, "line_end": 11}),
            ],
        )
        con.execute(
            "INSERT INTO code_declared_effective_field VALUES "
            "('ef-service','s','repo','t-ind','f-service','t-ind','serviceStartDate',0,false,'declared','{}')"
        )
        con.execute(
            "INSERT INTO code_declared_field VALUES "
            "('f-birth','s','repo','field-birth','t-ind','birthCountry','Country',NULL,false,false,false,'[]',?, ?, '{}')",
            [
                json.dumps({"description": "Страна рождения"}, ensure_ascii=False),
                json.dumps({"repository_relative_path": "Individual.java", "line_start": 10, "line_end": 10}),
            ],
        )
        con.execute(
            "INSERT INTO code_declared_effective_field VALUES "
            "('ef-birth','s','repo','t-ind','f-birth','t-ind','birthCountry',0,false,'declared','{}')"
        )
        con.execute(
            "INSERT INTO code_declared_relationship VALUES "
            "('r-country','s','repo','t-ind','t-country','f-birth','tr','declared_field_type_reference','resolved',?)",
            [json.dumps({"basis": "resolved_effective_field_type_reference", "does_not_imply_business_association": True})],
        )
        con.execute("""INSERT INTO code_declared_annotation
            (annotation_occurrence_id,source_occurrence_id,repo_id,annotation_id,target_kind,target_occurrence_id,annotation_name,arguments_raw,structured_arguments_json,resolution_status,resolved_annotation_type,candidate_annotation_types_json,source_ref_json,payload_json)
            VALUES ('a-root','s','repo','a1','type','t-ind','MetaRootEntity',NULL,'[]','unresolved',NULL,'[]','{}','{}')""")
        con.execute("""INSERT INTO code_declared_annotation
            (annotation_occurrence_id,source_occurrence_id,repo_id,annotation_id,target_kind,target_occurrence_id,annotation_name,arguments_raw,structured_arguments_json,resolution_status,resolved_annotation_type,candidate_annotation_types_json,source_ref_json,payload_json)
            VALUES ('a-dict','s','repo','a2','type','t-country','MetaDictionary',NULL,'[]','unresolved',NULL,'[]','{}','{}')""")
    finally:
        con.close()
    return path


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    artifact = _artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=artifact,
                model_kind="code-declared-data-model",
                schema_version="code-declared-data-model/v1",
                materialization_id="code-declared-data-model",
                capabilities=(
                    "common.code-declared-data-model",
                    "common.code-declared-entities",
                    "common.code-declared-fields",
                    "common.code-declared-relationships",
                ),
            )
        ],
        scope_id="ucp",
        execution_token="run-ucp",
    )
    settings = KnowledgeApiSettings(database_path=tmp_path / "api.sqlite3", allowed_roots=(tmp_path,))
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings)))
    client.__enter__()
    assert client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems",
        json={"system_id": "ucp", "display_name": "UCP"},
    ).status_code == 201
    pub = client.post(
        f"{KNOWLEDGE_API_PREFIX}/systems/ucp/revisions",
        json=publication_payload(result),
    )
    assert pub.status_code == 201, pub.text
    return client, pub.json()["revision"]["revision_id"]


def test_declared_objects_search_and_detail_are_revision_bound_and_semantically_declared(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects",
            params={
                "revision_id": revision_id,
                "search": "Страна рождения",
                "include_fields": "true",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["revision_id"] == revision_id
        assert body["declared_model_schema_version"] == "code-declared-data-model/v1"
        assert body["page"]["total"] == 1
        item = body["items"][0]
        assert item["fqcn"] == "com.acme.Individual"
        assert [row["annotation_name"] for row in item["annotations"]] == ["MetaRootEntity"]
        assert item["fields"][0]["name"] == "birthCountry"
        assert item["fields"][0]["documentation"]["description"] == "Страна рождения"
        assert body["filters"]["search_scope"] == "all_declared_types"
        assert item["retrieval_score"] > 0
        assert item["match_evidence"][0]["target_kind"] == "field"
        assert item["match_evidence"][0]["field_name"] == "birthCountry"
        assert item["match_evidence"][0]["evidence_role"] == "direct_observed_field_match"

        detail = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects/{item['object_id']}",
            params={"revision_id": revision_id},
        )
        assert detail.status_code == 200, detail.text
        obj = detail.json()["object"]
        assert [row["annotation_name"] for row in obj["annotations"]] == ["MetaRootEntity"]
        assert obj["relationships"][0]["target_fqcn"] == "com.acme.Country"
        assert obj["relationships"][0]["cardinality_hint"] == "one"
        assert obj["relationships"][0]["provenance"]["does_not_imply_business_association"] is True
        assert "join_method" not in obj["relationships"][0]
        assert obj["binding_summary"]["incoming_relationship_count"] == 0
        assert obj["binding_summary"]["outgoing_relationship_count"] == 1
    finally:
        client.__exit__(None, None, None)


def test_declared_summary_and_annotation_filter_are_revision_bound(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        summary = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-summary",
            params={
                "revision_id": revision_id,
                "type_annotations": "MetaRootEntity,MetaDictionary",
            },
        )
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert body["revision_id"] == revision_id
        assert body["counts"]["type_count"] == 2
        assert {row["annotation_name"] for row in body["type_annotation_counts"]} == {"MetaRootEntity", "MetaDictionary"}

        objects = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects",
            params={"revision_id": revision_id, "type_annotations": "MetaRootEntity"},
        )
        assert objects.status_code == 200, objects.text
        assert objects.json()["page"]["total"] == 1
        assert objects.json()["items"][0]["fqcn"] == "com.acme.Individual"
    finally:
        client.__exit__(None, None, None)


def test_declared_object_detail_returns_404_for_unknown_occurrence(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects/missing",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "declared_data_object_not_found"
    finally:
        client.__exit__(None, None, None)


def test_declared_search_ranks_exact_type_and_exposes_observed_incoming_binding(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects",
            params={"revision_id": revision_id, "search": "Country", "limit": 10},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert [item["fqcn"] for item in body["items"]] == ["com.acme.Country", "com.acme.Individual"]
        country = body["items"][0]
        assert country["score_basis"] == "type_name_exact"
        assert country["retrieval_score"] == 1000
        assert country["binding_summary"]["has_observed_incoming_binding"] is True
        assert country["binding_summary"]["incoming_relationship_count"] == 1
        incoming = country["binding_summary"]["incoming_examples"][0]
        assert incoming["source_fqcn"] == "com.acme.Individual"
        assert incoming["source_field"] == "birthCountry"

        individual = body["items"][1]
        assert individual["match_evidence"][0]["target_kind"] == "field"
        assert individual["match_evidence"][0]["field_name"] == "birthCountry"
        assert individual["match_evidence"][0]["match_kind"] in {"field_type_exact", "field_name_substring"}
    finally:
        client.__exit__(None, None, None)


def test_declared_search_surfaces_field_documentation_match_without_full_field_dump(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects",
            params={"revision_id": revision_id, "search": "обслуживания", "include_fields": "false"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["page"]["total"] == 1
        item = body["items"][0]
        assert item["fqcn"] == "com.acme.Individual"
        assert "fields" not in item
        evidence = item["match_evidence"][0]
        assert evidence["target_kind"] == "field"
        assert evidence["field_name"] == "serviceStartDate"
        assert evidence["documentation"]["description"] == "Дата начало обслуживания клиента"
        assert evidence["match_kind"].startswith("field_documentation_")
    finally:
        client.__exit__(None, None, None)


def test_unbound_declared_type_is_explicit_in_binding_summary(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/declared-objects",
            params={"revision_id": revision_id, "search": "Segment"},
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["fqcn"] == "com.acme.Segment"
        assert item["score_basis"] == "type_name_exact"
        assert item["binding_summary"]["incoming_relationship_count"] == 0
        assert item["binding_summary"]["has_observed_incoming_binding"] is False
    finally:
        client.__exit__(None, None, None)


def test_universal_aisl_item_read_exposes_exact_declared_field_evidence(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        artifacts = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/knowledge-artifacts",
            params={"revision_id": revision_id},
        )
        assert artifacts.status_code == 200, artifacts.text
        artifact_id = artifacts.json()["items"][0]["artifact_id"]
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/knowledge-items/{artifact_id}/declared_field/f-service",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["schema_version"] == "aisl-knowledge-item-read/v1"
        assert body["item_ref"] == {
            "scope_id": "ucp",
            "revision_id": revision_id,
            "product_id": artifact_id,
            "item_kind": "declared_field",
            "local_id": "f-service",
        }
        assert body["item"]["name"] == "serviceStartDate"
        assert body["item"]["documentation"]["description"] == "Дата начало обслуживания клиента"
        assert body["evidence_state"]["availability"] == "available"
        assert body["evidence"][0]["evidence_kind"] == "observed_source"
        assert body["source_fragments"][0]["path"] == "Individual.java"
        assert body["source_fragments"][0]["line_start"] == 11
        assert body["coverage_state"] == {
            "availability": "not_available",
            "basis": "item_level_coverage_fact_not_published_by_typed_product",
        }
        assert body["correspondences_state"]["availability"] == "unsupported"
    finally:
        client.__exit__(None, None, None)


def test_data_model_object_context_is_available_without_storage_products_and_keeps_gap_explicit(tmp_path: Path) -> None:
    client, revision_id = _client(tmp_path)
    try:
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp/data-model/object-context/t-ind",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["schema_version"] == "data_model_object_context/v2"
        assert body["object"]["fqcn"] == "com.acme.Individual"
        assert [row["name"] for row in body["fields"]] == ["birthCountry", "serviceStartDate"]
        relationship = body["relationships"][0]
        assert relationship["source_field"] == "birthCountry"
        assert relationship["target"]["fqcn"] == "com.acme.Country"
        assert relationship["storage_semantics"]["status"] == "not_available"
        assert relationship["storage_semantics"]["observations"] == []
        assert relationship["physical_mapping"] == {
            "status": "not_observed",
            "physical_join_confirmed": False,
            "basis": "this read model contains declared-model and model-storage knowledge only; no physical SQL/PDM join is asserted",
        }
        assert body["storage_context"]["status"] == "not_available"
        assert body["storage_context"]["published_optional_capabilities"] == []
    finally:
        client.__exit__(None, None, None)


def _storage_semantics_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "model-storage.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute("create table model_storage_record(observation_id varchar,repo_id varchar,api_framework varchar,owner_fqcn varchar,owner_operation varchar,storage_alias varchar,storage_key_field varchar,storage_key_expression varchar,source_refs_json json,payload_json json)")
        con.execute("create table model_storage_reference(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,source_field varchar,reference_operation varchar,target_converter_operation varchar,target_alias varchar,target_storage_key_field varchar,target_storage_key_expression varchar,source_refs_json json,payload_json json)")
        con.execute("create table model_storage_key_lineage(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,relationship_field varchar,reference_operation varchar,target_alias varchar,source_key_expression varchar,target_key_expression_template varchar,composed_target_key_expression varchar,source_key_passed_into_target_key boolean,source_refs_json json,payload_json json)")
        con.execute("create table model_storage_reference_derivation(observation_id varchar,repo_id varchar,api_framework varchar,source_owner_fqcn varchar,source_operation varchar,source_alias varchar,relationship_field varchar,reference_operation varchar,value_converter_operation varchar,composed_reference_value_expression varchar,source_refs_json json,payload_json json)")
        con.execute("insert into model_storage_record values (?,?,?,?,?,?,?,?,?,?)", [
            "record-ind", "tsa", "tsa_change_vector", "IndividualConverter", "convert",
            "com.acme.Individual", "key", '"Individual_" + individual.id', "[]", "{}",
        ])
        con.execute("insert into model_storage_reference values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            "ref-country", "tsa", "tsa_change_vector", "IndividualConverter", "convert",
            "com.acme.Individual", "birthCountry", "referenceField", "CountryConverter.convert",
            "com.acme.Country", "key", '"Country_" + country.code', "[]",
            json.dumps({"properties": {"reference_value_expression": "convertCountry(individual.birthCountry)"}}),
        ])
        con.execute("insert into model_storage_reference_derivation values (?,?,?,?,?,?,?,?,?,?,?,?)", [
            "drv-country", "tsa", "tsa_change_vector", "IndividualConverter", "convert",
            "com.acme.Individual", "birthCountry", "referenceField", "convertCountry",
            '"Country_" + individual.birthCountry.code', "[]",
            json.dumps({"properties": {"composed_reference_value_expression_tree": {"kind": "concat"}}}),
        ])
    finally:
        con.close()
    return path


def _logical_storage_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "logical-storage.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute("create table logical_storage_entity_mapping(entity_mapping_id varchar,mapping_source_id varchar,storage_observation_id varchar,storage_repo_id varchar,storage_alias varchar,storage_key_expression varchar,logical_repo_id varchar,logical_type_occurrence_id varchar,logical_fully_qualified_name varchar,mapping_status varchar,mapping_basis varchar,candidate_logical_type_ids_json json,payload_json json)")
        con.execute("create table logical_storage_relationship_mapping(relationship_mapping_id varchar,mapping_source_id varchar,storage_observation_id varchar,storage_repo_id varchar,storage_relation_kind varchar,source_alias varchar,source_field varchar,target_alias varchar,source_logical_repo_id varchar,source_logical_type_occurrence_id varchar,effective_field_occurrence_id varchar,field_is_inherited boolean,declared_target_type_occurrence_id varchar,declared_target_fqcn varchar,observed_target_type_occurrence_id varchar,observed_target_fqcn varchar,target_alignment varchar,knowledge_class varchar,storage_key_expression varchar,mapping_status varchar,mapping_basis varchar,payload_json json)")
        con.execute("create table logical_storage_join_semantic(join_semantic_id varchar,mapping_source_id varchar,relationship_occurrence_id varchar,source_logical_repo_id varchar,source_logical_type_occurrence_id varchar,source_fqcn varchar,source_field_occurrence_id varchar,source_field varchar,declared_target_type_occurrence_id varchar,declared_target_fqcn varchar,join_kind varchar,status varchar,join_readiness varchar,source_reference_expressions_json json,target_identity_expressions_json json,target_key_fields_json json,structural_correspondences_json json,candidate_count bigint,basis_json json,provenance_json json,diagnostics_json json)")
        con.execute("create table logical_storage_mapping_gap(mapping_gap_id varchar,mapping_source_id varchar,gap_kind varchar,severity varchar,owner_kind varchar,owner_id varchar,message varchar,details_json json)")
        con.execute("insert into logical_storage_entity_mapping values (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            "em-ind", "src", "record-ind", "tsa", "com.acme.Individual", '"Individual_" + individual.id',
            "repo", "t-ind", "com.acme.Individual", "matched", "exact_storage_alias_to_fqcn", "[]", "{}",
        ])
        con.execute("insert into logical_storage_relationship_mapping values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            "rm-country", "src", "ref-country", "tsa", "single_reference", "com.acme.Individual",
            "birthCountry", "com.acme.Country", "repo", "t-ind", "ef-birth", False,
            "t-country", "com.acme.Country", "t-country", "com.acme.Country",
            "exact_declared_target", "confirmed", '"Country_" + country.code', "matched",
            "exact_fqcn_plus_effective_field", "{}",
        ])
        con.execute("insert into logical_storage_join_semantic values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            "js-country", "src", "r-country", "repo", "t-ind", "com.acme.Individual",
            "f-birth", "birthCountry", "t-country", "com.acme.Country",
            "reference_value_to_target_identity", "strongly_supported", "executable_storage_join",
            json.dumps(['"Country_" + individual.birthCountry.code']), json.dumps(['"Country_" + country.code']),
            json.dumps(["code"]), json.dumps([{"match_basis":"exact_structural_expression_signature","target_key_fields":["code"]}]),
            1, json.dumps({"match_basis":"exact_structural_expression_signature","physical_join_claimed":False}),
            json.dumps({"evidence_ids":["drv-country","record-country"]}), json.dumps([]),
        ])
    finally:
        con.close()
    return path


def test_data_model_object_context_merges_exact_published_storage_semantics(tmp_path: Path) -> None:
    declared = _artifact(tmp_path)
    storage = _storage_semantics_artifact(tmp_path)
    logical = _logical_storage_artifact(tmp_path)
    result = write_execution_result(
        tmp_path,
        [
            KnowledgeArtifactSpec(
                database=declared,
                model_kind="code-declared-data-model",
                schema_version="code-declared-data-model/v1",
                materialization_id="code-declared-data-model",
                capabilities=("common.code-declared-data-model",),
            ),
            KnowledgeArtifactSpec(
                database=storage,
                model_kind="model-storage-semantics",
                schema_version="model-storage-semantics/v1",
                materialization_id="model-storage-semantics",
                capabilities=("common.model-storage-semantics",),
            ),
            KnowledgeArtifactSpec(
                database=logical,
                model_kind="logical-storage-model-mapping",
                schema_version="logical-storage-model-mapping/v2",
                materialization_id="logical-storage-mapping",
                capabilities=("common.logical-storage-mapping", "common.logical-storage-join-semantics"),
            ),
        ],
        scope_id="ucp-rich",
        execution_token="run-ucp-rich",
    )
    settings = KnowledgeApiSettings(database_path=tmp_path / "rich-api.sqlite3", allowed_roots=(tmp_path,))
    client = TestClient(create_contract_app(service=KnowledgeDomainService(settings)))
    with client:
        assert client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems",
            json={"system_id": "ucp-rich", "display_name": "UCP Rich"},
        ).status_code == 201
        pub = client.post(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp-rich/revisions",
            json=publication_payload(result),
        )
        assert pub.status_code == 201, pub.text
        revision_id = pub.json()["revision"]["revision_id"]
        response = client.get(
            f"{KNOWLEDGE_API_PREFIX}/systems/ucp-rich/data-model/object-context/t-ind",
            params={"revision_id": revision_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["storage_context"]["status"] == "available"
        rel = next(row for row in body["relationships"] if row["source_field"] == "birthCountry")
        assert rel["storage_semantics"]["status"] == "matched"
        assert rel["storage_semantics"]["mapping"]["knowledge_class"] == "confirmed"
        assert rel["storage_semantics"]["mapping"]["target_alignment"] == "exact_declared_target"
        assert rel["storage_semantics"]["observations"][0]["target_storage_key_field"] == "key"
        assert rel["storage_semantics"]["reference_value_derivations"][0]["composed_reference_value_expression"] == '"Country_" + individual.birthCountry.code'
        assert rel["storage_join"]["status"] == "strongly_supported"
        assert rel["storage_join"]["join_readiness"] == "executable_storage_join"
        assert rel["storage_join"]["target_key_fields"] == ["code"]
        assert rel["storage_join"]["basis"]["physical_join_claimed"] is False
        assert rel["physical_mapping"]["status"] == "not_observed"
        assert rel["physical_mapping"]["physical_join_confirmed"] is False
