from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from knowledge_layer_core import EFFECTIVE_DATA_MODEL_DDL

from knowledge_api.effective_data_model_query import (
    DataObjectNotFoundError,
    EffectiveDataModelQueryService,
    RelationshipNotFoundError,
)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "effective-data-model.duckdb"
    con = duckdb.connect(str(path))
    try:
        con.execute(EFFECTIVE_DATA_MODEL_DDL)
        con.execute(
            """INSERT INTO effective_data_model_build
               (build_id, scope_id, builder_version, schema_version, domain_cluster_schema_version,
                build_status, started_at, completed_at, counts_json, checks_json)
               VALUES ('build-1','ucp','0.56.0','effective-data-model/v1','model-domain-cluster-view/v1',
                       'complete', TIMESTAMP '2026-08-05 10:00:00', TIMESTAMP '2026-08-05 10:00:01','{}','{}')"""
        )
        con.executemany(
            """INSERT INTO effective_data_model_entity
               (effective_entity_id, scope_id, repo_id, logical_type_id, logical_type_occurrence_id,
                logical_fully_qualified_name, logical_name, logical_package_name, logical_type_kind,
                persistence_kind, entity_mapping_id, mapping_status, mapping_basis,
                physical_model_table_id, physical_table_name, physical_table_code, layer_status,
                source_layers_json, diagnostics_json, provenance_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("entity-customer","ucp","repo-a","type-customer","occ-customer","example.Customer","Customer","example","class","entity","map-customer","matched","explicit_table_name","table-customer","customer_tbl","customer_tbl","cross_layer","[]","[]",'{"source":"java"}'),
                ("entity-address","ucp","repo-a","type-address","occ-address","example.Address","Address","example","class","entity","map-address","matched","explicit_table_name","table-address","address_tbl","address_tbl","cross_layer","[]","[]",'{"source":"java"}'),
            ],
        )
        con.executemany(
            """INSERT INTO effective_data_model_field
               (effective_field_id, effective_entity_id, repo_id, logical_field_id, logical_field_occurrence_id,
                logical_field_name, declared_type_expression, normalized_type_expression, is_inherited,
                inherited_depth, persistence_role, field_mapping_id, mapping_status, mapping_basis,
                physical_model_column_id, physical_column_name, physical_column_code, physical_data_type,
                physical_mandatory, layer_status, source_layers_json, diagnostics_json, provenance_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("field-customer-id","entity-customer","repo-a","logical-customer-id","field-occ-1","id","Long","java.lang.Long",False,0,"id","field-map-1","matched","explicit_column_name","column-customer-id","id","id","bigint",True,"cross_layer","[]","[]","{}"),
                ("field-customer-address","entity-customer","repo-a","logical-address","field-occ-2","address","Address","example.Address",False,0,"relationship","field-map-2","matched","explicit_join_column","column-address-id","address_id","address_id","bigint",False,"cross_layer","[]","[]","{}"),
                ("field-address-id","entity-address","repo-a","logical-address-id","field-occ-3","id","Long","java.lang.Long",False,0,"id","field-map-3","matched","explicit_column_name","column-address-pk","id","id","bigint",True,"cross_layer","[]","[]","{}"),
            ],
        )
        con.executemany(
            """INSERT INTO effective_data_model_key
               (effective_key_id, effective_entity_id, repo_id, logical_type_id, logical_field_id,
                key_kind, key_mapping_id, mapping_status, mapping_basis, physical_model_table_id,
                physical_model_column_id, physical_model_key_id, diagnostics_json, provenance_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                ("key-customer","entity-customer","repo-a","type-customer","logical-customer-id","primary","key-map-1","matched","explicit_id","table-customer","column-customer-id","pk-customer","[]","{}"),
                ("key-address","entity-address","repo-a","type-address","logical-address-id","primary","key-map-2","matched","explicit_id","table-address","column-address-pk","pk-address","[]","{}"),
            ],
        )
        con.execute(
            """INSERT INTO effective_data_model_relationship
               (effective_relationship_id, repo_id, logical_relationship_occurrence_id,
                source_effective_entity_id, target_effective_entity_id, logical_field_id,
                logical_field_occurrence_id, relationship_kind, relationship_mapping_id,
                mapping_status, mapping_basis, source_physical_table_id, target_physical_table_id,
                source_physical_column_id, target_physical_column_id, physical_model_relationship_id,
                layer_status, diagnostics_json, provenance_json)
               VALUES ('relationship-address','repo-a','rel-occ-1','entity-customer','entity-address',
                       'logical-address','field-occ-2','many-to-one','rel-map-1','matched',
                       'explicit_join_column','table-customer','table-address','column-address-id',
                       'column-address-pk','physical-rel-1','cross_layer','[]','{"evidence":"explicit"}')"""
        )
        for name, value in {
            "logical_entities": 2,
            "logical_fields": 3,
            "logical_relationships": 1,
            "matched_keys": 2,
            "matched_relationships": 1,
            "physical_tables": 2,
        }.items():
            con.execute(
                "INSERT INTO effective_data_model_coverage VALUES (?,?,?,?,?,?)",
                [f"coverage-{name}", "ucp", "summary", name, value, "{}"],
            )
    finally:
        con.close()
    return path


def test_effective_model_query_projects_materialized_cross_layer_facts(tmp_path: Path) -> None:
    service = EffectiveDataModelQueryService(_database(tmp_path))
    catalog = service.field_catalog("ucp")
    assert [(item.table_name, len(item.fields)) for item in catalog.tables] == [("Address", 1), ("Customer", 2)]
    assert "mapping status matched" in catalog.tables[0].description

    detail = service.table_detail("ucp", "entity-customer")
    assert detail.object.display_name == "customer_tbl"
    assert [field.name for field in detail.fields] == ["address", "id"]
    assert detail.keys[0].fields == ["id"]
    assert detail.relationships[0].join.physical_join_confirmed is True

    relationship = service.relationship_detail("entity-customer", "relationship-address")
    assert relationship.target.object.id == "entity-address"
    assert relationship.reference.encoding_inputs.key_component.source == "target_storage_key"
    assert relationship.join.source.fields == ["column-address-id"]
    assert relationship.join.target.fields == ["column-address-pk"]
    assert relationship.provenance == {"evidence": "explicit"}
    assert service.analysis_coverage("ucp")["status"] == "complete"


def test_effective_model_query_reports_missing_objects(tmp_path: Path) -> None:
    service = EffectiveDataModelQueryService(_database(tmp_path))
    with pytest.raises(DataObjectNotFoundError):
        service.table_detail("ucp", "missing")
    with pytest.raises(RelationshipNotFoundError):
        service.relationship_detail("entity-customer", "missing")
