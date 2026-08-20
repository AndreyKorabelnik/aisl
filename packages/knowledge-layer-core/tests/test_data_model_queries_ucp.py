import os
from pathlib import Path
import pytest

from prepared_knowledge_runtime import DataModelQueryService
from prepared_knowledge_runtime import ReportingQueryService

DB_ENV = "UCP_KNOWLEDGE_LAYER"


def _service():
    value = os.environ.get(DB_ENV)
    if not value or not Path(value).is_file():
        pytest.skip(f"set {DB_ENV} to run the real UCP contract test")
    return DataModelQueryService(value)


def _individual(service):
    result = service.search_objects(token="Individual", object_kinds=("root_entity",), max_results=100).to_dict()
    return next(item for item in result["items"] if item["fqcn"].endswith(".Individual"))


def test_ucp_individual_fields_keys_relationships_and_join_guidance():
    service = _service()
    individual = _individual(service)
    assert individual["object_kind"] == "root_entity"

    fields = service.get_fields(individual["object_id"]).to_dict()
    by_name = {item["name"]: item for item in fields["items"]}
    assert by_name["birthDate"]["effective_type"] == "BirthDate"
    assert by_name["birthPlace"]["description"] == "Место рождения"
    assert by_name["addresses"]["container_kind"] == "collection"
    assert fields["evidence"]

    keys = service.get_keys(individual["object_id"]).to_dict()
    assert [item["field_name"] for item in keys["items"][0]["members"]] == ["id", "id", "version"]

    relationships = service.get_relationships(source_object_id=individual["object_id"]).to_dict()
    assert relationships["summary"]["relationship_count"] == 40
    rel_by_field = {item["source"]["field"]: item for item in relationships["items"]}
    assert rel_by_field["birthCountry"]["target"]["logical_identity"]["fields"] == ["code"]
    assert rel_by_field["birthPlace"]["join"]["method"] in {"storage_reference_requires_encoding", "derived_key_evidence"}
    assert len(rel_by_field["identifications"]["polymorphic_targets"]) == 8

    join = service.get_join_guidance(source_object_id=individual["object_id"], target_name="BirthPlace").to_dict()
    assert join["items"][0]["source"]["field"] == "birthPlace"
    assert join["items"][0]["join"]["physical_join_confirmed"] is False
    assert join["evidence"]


def test_ucp_cross_repository_correspondences_are_evidence_backed():
    service = _service()
    result = service.get_cross_repository_correspondences(token="Individual", max_results=50).to_dict()
    assert result["summary"]["correspondence_count"] >= 10
    assert any(item["source_repo_id"] == "ucp_tsa_v4" and item["target_repo_id"] == "ucp_api" for item in result["items"])
    assert result["evidence"]


def test_ucp_cross_repository_catalog_is_complete_and_excludes_local_matches():
    service = _service()
    result = service.get_cross_repository_correspondences(max_results=2000).to_dict()
    assert result["summary"]["selection_scope"] == "cross_repository_only"
    assert result["summary"]["correspondence_count"] == 1186
    assert result["summary"]["returned_count"] == 1186
    assert result["summary"]["returned_kind_counts"] == {"configuration_type": 324, "type_reference": 862}
    assert all(item["source_repo_id"] != item["target_repo_id"] for item in result["items"])


def test_ucp_reporting_evidence_paths_are_portable():

    value = os.environ.get(DB_ENV)
    if not value or not Path(value).is_file():
        pytest.skip(f"set {DB_ENV} to run the real UCP contract test")
    result = ReportingQueryService(value).get_technologies(max_results=30).to_dict()
    assert result["evidence"]
    assert all(not str(item["path"]).startswith("/") for item in result["evidence"])
    assert any(str(item["path"]).endswith("pom.xml") for item in result["evidence"])
