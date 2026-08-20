from __future__ import annotations

import json
from pathlib import Path

from code_evidence.commands import system_boundaries, data_model_relationships


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _minimal_analysis_out(tmp_path: Path) -> Path:
    out = tmp_path / "analysis-out"
    (out / "compact").mkdir(parents=True)
    _write_json(out / "manifest.json", {"repo_path": str(tmp_path / "repo")})
    _write_json(out / "compact" / "navigation.json", {
        "interfaces": [
            {"id": "interface_1", "kind": "rest", "direction": "inbound", "operation": "ProfileController.profile", "path": "/profiles", "method": "POST", "schema_ref": "ProfileRequest"},
            {"id": "interface_2", "kind": "kafka", "direction": "inbound", "operation": "ProfileConsumer.consume", "topic": "${profile.topic}", "schema_ref": "ProfileEvent"},
        ],
        "operations": [
            {"id": "operation_1", "operation": "ProfileController.profile", "interfaces": ["interface_1"]},
            {"id": "operation_2", "operation": "ProfileConsumer.consume", "interfaces": ["interface_2"]},
        ],
    })
    _write_json(out / "compact" / "attribute_occurrences.json", [])
    _write_json(out / "compact" / "db_schema_tables.json", [
        {"db_schema_table_id": "t_phone", "table_name": "PHONE", "description": "Phone table"},
        {"db_schema_table_id": "t_device", "table_name": "DEVICE_LINK", "description": "Device link"},
        {"db_schema_table_id": "t_hist", "table_name": "PHONE_HISTORY", "description": "History"},
    ])
    _write_json(out / "compact" / "db_schema_columns.json", [
        {"db_schema_column_id": "c_phone", "table_name": "PHONE", "column_name": "PHONENUMBER"},
        {"db_schema_column_id": "c_device", "table_name": "DEVICE_LINK", "column_name": "PHONE_NUMBER"},
        {"db_schema_column_id": "c_hist", "table_name": "PHONE_HISTORY", "column_name": "PHONEID"},
    ])
    _write_json(out / "compact" / "db_schema_keys.json", [
        {"db_schema_key_id": "k_phone", "constraint_kind": "unique_key", "table_name": "PHONE", "columns": ["PHONENUMBER"], "constraint_name": "uk_phone_number"},
        {"db_schema_key_id": "k_device", "constraint_kind": "unique_key", "table_name": "DEVICE_LINK", "columns": ["PHONE_NUMBER"], "constraint_name": "uk_device_phone"},
    ])
    _write_json(out / "compact" / "db_schema_indexes.json", [])
    _write_json(out / "compact" / "db_schema_relationships.json", [])
    _write_json(out / "compact" / "persistent_writes.json", [
        {"persistent_write_id": "pw_1", "storage_target": "PHONE", "write_kind": "update", "operation": "PhoneDao.update"}
    ])
    _write_json(out / "compact" / "read_from_storage.json", [
        {"read_from_storage_id": "read_1", "storage_object": "DEVICE_LINK", "operation": "ProfileDao.readDevice"}
    ])
    _write_json(out / "compact" / "access_boundaries.json", [
        {"access_boundary_id": "acc_1", "boundary_kind": "rest_response", "endpoint_or_topic": "/deviceIdList", "response_or_payload_type": "DeviceResponse"}
    ])
    _write_json(out / "compact" / "storage_to_access_lineage.json", [
        {"storage_to_access_lineage_id": "sta_1", "source_storage_object": "DEVICE_LINK", "read_evidence_ref": "read_1", "access_evidence_ref": "acc_1", "lineage_status": "confirmed"}
    ])
    return out


def test_system_boundaries_view_materializes_rest_kafka_and_storage(tmp_path: Path) -> None:
    out = _minimal_analysis_out(tmp_path)
    payload = system_boundaries(out)
    assert payload["kind"] == "system-boundaries"
    kinds = {(x.get("direction"), x.get("boundary_kind")) for x in payload["items"]}
    assert ("inbound", "rest") in kinds
    assert ("inbound", "kafka") in kinds
    assert ("local_persistence", "Database") in kinds
    assert any(x.get("storage_object") == "PHONE" for x in payload["items"])
    assert payload["policy"]["analyzer_role"] == "evidence_only_no_business_decision"


def test_data_model_relationships_returns_observed_relations_without_role_inference(tmp_path: Path) -> None:
    out = _minimal_analysis_out(tmp_path)
    payload = data_model_relationships(out)
    assert payload["kind"] == "data-model-relationships"
    assert payload["relationship_observations"] == []
    assert "table_roles" not in payload
    assert "relationships" not in payload
    assert any(x.get("table") == "DEVICE_LINK" and x.get("read_by_external_endpoint") for x in payload["access_exposure"])
    assert payload["policy"]["analyzer_role"] == "evidence_only_no_business_decision"
    assert payload["policy"]["semantic_classification_performed"] is False

