from __future__ import annotations

import json

import duckdb

from prepared_knowledge_runtime.evidence_layout import SOURCE_OBSERVATION_FILES
from knowledge_layer_core.workspace_schema import DDL, SCHEMA_VERSION


def _insert_source_observation(con: duckdb.DuckDBPyConnection, *, occurrence_id: str, fact_type: str, payload: dict) -> None:
    con.execute(
        """INSERT INTO source_observation (
               source_observation_occurrence_id, repo_id, local_observation_id,
               occurrence_ordinal, fact_type, name, payload_json
           ) VALUES (?, 'repo-a', ?, 0, ?, ?, ?)""",
        [occurrence_id, occurrence_id, fact_type, occurrence_id, json.dumps(payload)],
    )


def test_storage_record_and_reference_views_preserve_generic_evidence() -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute(DDL)
        _insert_source_observation(
            con,
            occurrence_id="storage-record-1",
            fact_type="storage_record_observation",
            payload={
                "properties": {
                    "api_framework": "example_writer",
                    "observation_kind": "builder_storage_record",
                    "builder_receiver_expression": "writer",
                    "owner_fqcn": "example.GenericConverter",
                    "owner_operation": "GenericConverter.makeChild",
                    "storage_alias": "example.Child",
                    "storage_key_field": "record_key",
                    "storage_key_expression": "parentKey + '.' + segment",
                    "storage_key_local_variable": "recordKey",
                    "physical_reference_encoding": "downstream_interpretation_required",
                    "storage_key_input_symbols": ["parentKey", "segment"],
                    "storage_key_expression_tree": {"node_type": "binary_expression"},
                }
            },
        )
        _insert_source_observation(
            con,
            occurrence_id="storage-reference-1",
            fact_type="storage_reference_observation",
            payload={
                "properties": {
                    "api_framework": "example_writer",
                    "observation_kind": "reference_value_from_target_storage_record",
                    "source_owner_fqcn": "example.GenericConverter",
                    "source_operation": "GenericConverter.convert",
                    "source_alias": "example.Parent",
                    "source_field": "child",
                    "reference_operation": "linkField",
                    "target_converter_operation": "GenericConverter.makeChild",
                    "target_storage_record_observation_id": "storage-record-local",
                    "target_alias": "example.Child",
                    "target_storage_key_field": "record_key",
                    "target_storage_key_expression": "parentKey + '.' + segment",
                    "target_storage_key_local_variable": "recordKey",
                    "value_origin": "returned_target_storage_key",
                    "type_source": "target_storage_record.alias",
                    "key_source": "target_storage_record.storage_key",
                    "physical_encoding": "downstream_interpretation_required",
                }
            },
        )

        record = con.execute(
            "SELECT api_framework, storage_owner_fqcn, storage_owner_operation, storage_alias, storage_key_field, "
            "storage_key_expression, physical_reference_encoding FROM v_storage_records"
        ).fetchone()
        assert record == (
            "example_writer",
            "example.GenericConverter",
            "GenericConverter.makeChild",
            "example.Child",
            "record_key",
            "parentKey + '.' + segment",
            "downstream_interpretation_required",
        )

        reference = con.execute(
            "SELECT source_owner_fqcn, source_operation, source_alias, source_field, target_alias, target_storage_key_field, "
            "target_storage_key_expression, value_origin, physical_encoding "
            "FROM v_storage_references"
        ).fetchone()
        assert reference == (
            "example.GenericConverter",
            "GenericConverter.convert",
            "example.Parent",
            "child",
            "example.Child",
            "record_key",
            "parentKey + '.' + segment",
            "returned_target_storage_key",
            "downstream_interpretation_required",
        )
    finally:
        con.close()


def test_storage_evidence_files_are_part_of_repository_contract() -> None:
    assert SCHEMA_VERSION == "workspace_data_model/v16"
    assert {
        "storage_alias_assignment_observation.jsonl",
        "storage_record_observation.jsonl",
        "storage_reference_observation.jsonl",
    }.issubset(set(SOURCE_OBSERVATION_FILES))
