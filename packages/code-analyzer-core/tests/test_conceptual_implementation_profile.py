from __future__ import annotations

import json
from pathlib import Path

from evidence_access_test_utils import assert_evidence_tool_registered, run_evidence_tool
from code_evidence.commands import conceptual_implementation_profile


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_conceptual_implementation_profile_groups_existing_evidence(tmp_path: Path):
    out = tmp_path / "analysis-output"
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo", "project_code": "DEMO", "system_name": "demo-system"})
    _write(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_000001", "kind": "rest", "direction": "inbound", "operation": "BookingController.add", "path": "POST /favorites/add", "schema_ref": "FavoriteZoneRequest"}
        ],
        "operations": [
            {"id": "operation_000001", "operation": "BookingController.add", "interfaces": ["interface_000001"]}
        ],
    })
    _write(out / "compact" / "db_schema_tables.json", [
        {"db_schema_table_id": "db_schema_table_000001", "table_name": "favorites.favorite_zone", "schema_name": "favorites"}
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_occurrence.json", [
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000001", "container_name": "FavoriteZoneRequest", "container_kind": "request", "attribute_name": "clientId"}},
        {"properties": {"attribute_occurrence_id": "attribute_occurrence_000002", "container_name": "FavoriteZoneEntity", "container_kind": "entity", "attribute_name": "clientId"}},
    ])
    _write(out / "facts" / "facts_by_type" / "attribute_mapping.json", [
        {"properties": {"attribute_mapping_id": "attribute_mapping_000001", "source_container": "FavoriteZoneRequest", "source_field": "clientId", "target_container": "FavoriteZoneEntity", "target_field": "clientId", "mapping_kind": "direct"}}
    ])
    _write(out / "facts" / "facts_by_type" / "persistent_write.json", [
        {"properties": {"persistent_write_id": "persistent_write_000001", "operation": "FavoriteZoneService.add", "write_kind": "insert", "storage_target": "favorites.favorite_zone", "saved_object": "FavoriteZoneEntity", "lineage_status": "confirmed"}}
    ])
    _write(out / "facts" / "facts_by_type" / "source_to_storage_lineage.json", [
        {"properties": {"source_to_storage_lineage_id": "source_to_storage_lineage_000001", "operation": "FavoriteZoneService.add", "source_payload": "FavoriteZoneRequest", "saved_object": "FavoriteZoneEntity", "storage_target": "favorites.favorite_zone", "lineage_status": "confirmed"}}
    ])
    _write(out / "facts" / "facts_by_type" / "access_boundary.json", [
        {"properties": {"access_boundary_id": "access_boundary_000001", "boundary_kind": "http_client", "direction": "outbound", "operation": "PermissionsClient.check", "client_class": "PermissionsClient", "endpoint_or_topic": "permissions-service-v3", "base_url_property": "permissions.url", "resolution_status": "config_property"}}
    ])
    _write(out / "facts" / "facts_by_type" / "storage_access.json", [
        {"properties": {"storage_access_id": "storage_access_000001", "access_kind": "cache_write", "receiver": "redisCache", "storage_target": "cache.pro_wp_search", "method_name": "put"}}
    ])

    view = conceptual_implementation_profile(out, max_results=100)

    assert view["kind"] == "conceptual-implementation-profile"
    assert "sensitive_data_signals" not in view
    assert any(x["name"] == "favorites.favorite_zone" and x["kind"] == "db_table" for x in view["asset_inventory"])
    assert any(x["operation_kind"] == "INSERT" and x["target_asset"] == "favorites.favorite_zone" for x in view["io_points"])
    assert any(x["source_object"] == "FavoriteZoneRequest" and x["target_object"] == "FavoriteZoneEntity" for x in view["mapper_mappings"])
    assert any(x["service_name_candidate"] == "permissions-service-v3" for x in view["external_dependencies"])
    assert any(x["trigger_kind"] == "pump_endpoint" or x["endpoint_or_schedule_or_topic"] == "POST /favorites/add" for x in view["triggers"])
    assert any(x["asset_name"] == "cache.pro_wp_search" for x in view["cache_assets"])
    assert any(x["link_type"] == "source_payload_to_storage" for x in view["concept_implementation_links"])
    assert "concept_implementation_cards" in view
    favorite_card = next(x for x in view["concept_implementation_cards"] if x["concept_family"] == "favorite_zone")
    assert favorite_card["canonical_name_candidate"] == "Favorite Zone"
    assert favorite_card["concept_confirmation_status"] == "confirmed_by_code"
    assert favorite_card["physical_confirmation_status"] == "confirmed_schema_table"
    assert favorite_card["evidence_status"] == "confirmed_by_code"
    assert any(x["name"] == "favorites.favorite_zone" for x in favorite_card["assets"]["db_tables"])
    assert any(x["name"] == "FavoriteZoneEntity" for x in favorite_card["assets"]["java_entities"])
    assert favorite_card["io_summary"]["insert_count"] >= 1
    assert favorite_card["mapper_mapping_refs"]
    assert favorite_card["concept_implementation_link_refs"]
    assert "aggregate" in favorite_card["implementation_patterns"]
    assert "transaction" in favorite_card["implementation_patterns"]
    permissions_card = next(x for x in view["concept_implementation_cards"] if x["concept_family"] == "permission")
    assert permissions_card["physical_confirmation_status"] == "external_dependency_only"
    cache_card = next(x for x in view["concept_implementation_cards"] if x["concept_family"] == "pro_wp_search")
    assert cache_card["physical_confirmation_status"] == "cache_or_view_only"
    assert "cache_projection" in cache_card["implementation_patterns"]
    assert not any(x["concept_family"] in {"add", "check", "put"} for x in view["concept_implementation_cards"])
    assert view["coverage"]["asset_inventory_count"] >= 3
    assert view["coverage"]["concept_implementation_cards_count"] >= 3
    assert any("Sensitive/PII" in x for x in view["limitations"])


def test_conceptual_implementation_profile_cli_and_contract(tmp_path: Path):
    out = tmp_path / "analysis-output"
    (out / "compact").mkdir(parents=True)
    (out / "facts" / "facts_by_type").mkdir(parents=True)
    _write(out / "manifest.json", {"repo_id": "demo"})
    assert_evidence_tool_registered("conceptual_implementation_profile")

    payload = run_evidence_tool("conceptual_implementation_profile", analysis_out=out, max_results=10)
    assert payload["kind"] == "conceptual-implementation-profile"
