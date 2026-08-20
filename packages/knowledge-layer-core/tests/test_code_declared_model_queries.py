from __future__ import annotations

import json
from pathlib import Path

import duckdb

from knowledge_layer_core.code_declared_model_schema import CODE_DECLARED_MODEL_DDL
from prepared_knowledge_runtime.query import KnowledgeLayerQuery


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "declared.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(CODE_DECLARED_MODEL_DDL)
        con.execute("INSERT INTO code_declared_model_build VALUES ('b','scope','test','code-declared-data-model/v1','java-type-structure-evidence/v1','complete',now(),now(),'{}','{}')")
        con.execute("INSERT INTO code_declared_type VALUES ('t-ind','s','repo','type-ind','u','com.acme.Individual','Individual','com.acme','class',NULL,'main','[]','[]',?, ?, '{}')", [json.dumps({'display_name':'Физическое лицо'}), json.dumps({'repository_relative_path':'Individual.java','line_start':1,'line_end':50})])
        con.execute("INSERT INTO code_declared_type VALUES ('t-country','s','repo','type-country','u','com.acme.Country','Country','com.acme','class',NULL,'main','[]','[]',?, ?, '{}')", [json.dumps({'display_name':'Страна'}), json.dumps({'repository_relative_path':'Country.java','line_start':1,'line_end':20})])
        con.execute("INSERT INTO code_declared_field VALUES ('f-birth','s','repo','field-birth','t-ind','birthCountry','Country',NULL,false,false,false,'[]',?, ?, '{}')", [json.dumps({'description':'Страна рождения'}), json.dumps({'repository_relative_path':'Individual.java','line_start':10,'line_end':10})])
        con.execute("INSERT INTO code_declared_field VALUES ('f-name','s','repo','field-name','t-country','name','String',NULL,false,false,false,'[]',?, ?, '{}')", [json.dumps({'description':'Наименование страны'}), json.dumps({'repository_relative_path':'Country.java','line_start':5,'line_end':5})])
        con.execute("INSERT INTO code_declared_effective_field VALUES ('ef-birth','s','repo','t-ind','f-birth','t-ind','birthCountry',0,false,'declared','{}')")
        con.execute("INSERT INTO code_declared_effective_field VALUES ('ef-name','s','repo','t-country','f-name','t-country','name',0,false,'declared','{}')")
        con.execute("INSERT INTO code_declared_relationship VALUES ('r-country','s','repo','t-ind','t-country','f-birth','tr','declared_field_type_reference','resolved',?)", [json.dumps({'basis':'resolved_effective_field_type_reference','is_inherited':False,'inherited_depth':0})])
        con.execute("""INSERT INTO code_declared_annotation
            (annotation_occurrence_id,source_occurrence_id,repo_id,annotation_id,target_kind,target_occurrence_id,annotation_name,arguments_raw,structured_arguments_json,resolution_status,resolved_annotation_type,candidate_annotation_types_json,source_ref_json,payload_json)
            VALUES ('a-root','s','repo','a1','type','t-ind','MetaRootEntity',NULL,'[]','unresolved',NULL,'[]','{}','{}')""")
        con.execute("""INSERT INTO code_declared_annotation
            (annotation_occurrence_id,source_occurrence_id,repo_id,annotation_id,target_kind,target_occurrence_id,annotation_name,arguments_raw,structured_arguments_json,resolution_status,resolved_annotation_type,candidate_annotation_types_json,source_ref_json,payload_json)
            VALUES ('a-dict','s','repo','a2','type','t-country','MetaDictionary',NULL,'[]','unresolved',NULL,'[]','{}','{}')""")
        con.execute("""INSERT INTO code_declared_annotation
            (annotation_occurrence_id,source_occurrence_id,repo_id,annotation_id,target_kind,target_occurrence_id,annotation_name,arguments_raw,structured_arguments_json,resolution_status,resolved_annotation_type,candidate_annotation_types_json,source_ref_json,payload_json)
            VALUES ('a-ignore','s','repo','a3','field','f-name','MetaIgnore',NULL,'[]','unresolved',NULL,'[]','{}','{}')""")
    finally:
        con.close()
    return path


def test_declared_object_search_matches_field_documentation_and_returns_fields(tmp_path: Path) -> None:
    q = KnowledgeLayerQuery(_db(tmp_path))
    result = q.list_code_declared_objects(search="Страна рождения", include_fields=True)
    assert result["not_available"] is False
    assert result["total_count"] == 1
    item = result["items"][0]
    assert item["fqcn"] == "com.acme.Individual"
    assert item["fields"][0]["name"] == "birthCountry"
    assert item["fields"][0]["documentation"]["description"] == "Страна рождения"
    assert item["fields"][0]["source_ref"]["repository_relative_path"] == "Individual.java"


def test_declared_object_detail_keeps_relationship_observed_and_separate(tmp_path: Path) -> None:
    q = KnowledgeLayerQuery(_db(tmp_path))
    result = q.get_code_declared_object("t-ind")
    obj = result["object"]
    assert obj["fqcn"] == "com.acme.Individual"
    assert obj["relationships"] == [{
        "relationship_id": "r-country",
        "field_occurrence_id": "f-birth",
        "source_field": "birthCountry",
        "declared_type_expression": "Country",
        "target_type_occurrence_id": "t-country",
        "target_fqcn": "com.acme.Country",
        "target_name": "Country",
        "relationship_kind": "declared_field_type_reference",
        "resolution_status": "resolved",
        "provenance": {"basis": "resolved_effective_field_type_reference", "is_inherited": False, "inherited_depth": 0},
        "source_ref": {"repository_relative_path": "Individual.java", "line_start": 10, "line_end": 10},
        "source_field_annotations": [],
        "is_inherited": False,
        "inherited_depth": 0,
        "cardinality_hint": "one",
        "cardinality_basis": "declared_non_collection_type",
    }]
    assert "join_method" not in obj["relationships"][0]


def test_declared_model_query_capabilities_are_derived_from_materialized_tables(tmp_path: Path) -> None:
    q = KnowledgeLayerQuery(_db(tmp_path))
    capabilities = set(q.capabilities())
    assert "common.code-declared-data-model" in capabilities
    assert "common.code-declared-fields" in capabilities
    assert "common.code-declared-relationships" in capabilities


def test_declared_model_summary_supports_exact_observed_annotation_filters(tmp_path: Path) -> None:
    q = KnowledgeLayerQuery(_db(tmp_path))
    raw = q.summarize_code_declared_model()
    assert raw["counts"]["type_count"] == 2
    assert raw["counts"]["effective_field_count"] == 2
    assert {row["annotation_name"] for row in raw["type_annotation_counts"]} == {"MetaRootEntity", "MetaDictionary"}

    filtered = q.summarize_code_declared_model(
        type_annotations=["MetaRootEntity", "MetaDictionary"],
        exclude_field_annotations=["MetaIgnore"],
    )
    assert filtered["counts"]["type_count"] == 2
    assert filtered["counts"]["effective_field_count"] == 1
    assert filtered["counts"]["relationship_count"] == 1
    assert filtered["counts"]["collection_relationship_count"] == 0
    assert filtered["filters"]["exclude_field_annotations"] == ["MetaIgnore"]


def test_declared_model_read_surface_exposes_annotations_and_relationship_shape(tmp_path: Path) -> None:
    q = KnowledgeLayerQuery(_db(tmp_path))
    listed = q.list_code_declared_objects(type_annotations=["MetaRootEntity"])
    assert listed["total_count"] == 1
    assert [row["annotation_name"] for row in listed["items"][0]["annotations"]] == ["MetaRootEntity"]

    detail = q.get_code_declared_object("t-ind")["object"]
    assert [row["annotation_name"] for row in detail["annotations"]] == ["MetaRootEntity"]
    relationship = detail["relationships"][0]
    assert relationship["cardinality_hint"] == "one"
    assert relationship["cardinality_basis"] == "declared_non_collection_type"
    assert relationship["is_inherited"] is False
    assert relationship["inherited_depth"] == 0
    country = q.get_code_declared_object("t-country")["object"]
    name_field = country["fields"][0]
    assert [row["annotation_name"] for row in name_field["annotations"]] == ["MetaIgnore"]
