from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from knowledge_layer_core import (
    PHYSICAL_MODEL_FACT_TYPES,
    build_physical_model_knowledge_layer,
    resolve_physical_model_artifact,
)


def _json_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_artifact(root: Path, *, with_gap: bool = False) -> Path:
    root.mkdir(parents=True)
    facts = root / "facts"
    facts.mkdir()
    source_id = "fixture-pdm"
    records = {
        "physical_model_table": [
            {
                "physical_model_table_id": "table_customer",
                "physical_model_source_id": source_id,
                "pdm_object_id": "t1",
                "object_uuid": "table-uuid",
                "model_name": "Fixture",
                "model_code": "fixture",
                "package_path": ["Business"],
                "package_code_path": ["business"],
                "table_name": "Customer",
                "table_code": "customer",
                "logical_identity": "business.customer",
                "comment": None,
                "description": None,
                "stereotype": None,
                "dimensional_type": None,
                "owner_ref": None,
                "column_count": 1,
                "key_count": 1,
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "t1"},
            },
            {
                "physical_model_table_id": "table_order",
                "physical_model_source_id": source_id,
                "pdm_object_id": "t2",
                "object_uuid": "order-uuid",
                "model_name": "Fixture",
                "model_code": "fixture",
                "package_path": ["Business"],
                "package_code_path": ["business"],
                "table_name": "Order",
                "table_code": "orders",
                "logical_identity": "business.orders",
                "comment": None,
                "description": None,
                "stereotype": None,
                "dimensional_type": None,
                "owner_ref": None,
                "column_count": 1,
                "key_count": 0,
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "t2"},
            },
        ],
        "physical_model_column": [
            {
                "physical_model_column_id": "column_customer_id",
                "physical_model_table_id": "table_customer",
                "physical_model_source_id": source_id,
                "pdm_object_id": "c1",
                "object_uuid": None,
                "ordinal": 1,
                "column_name": "Id",
                "column_code": "id",
                "data_type": "string",
                "length": 64,
                "precision": None,
                "mandatory": True,
                "default_value": None,
                "comment": None,
                "domain_ref": None,
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "c1"},
            },
            {
                "physical_model_column_id": "column_order_customer_id",
                "physical_model_table_id": "table_order",
                "physical_model_source_id": source_id,
                "pdm_object_id": "c2",
                "object_uuid": None,
                "ordinal": 1,
                "column_name": "Customer Id",
                "column_code": "customer_id",
                "data_type": "string",
                "length": 64,
                "precision": None,
                "mandatory": False,
                "default_value": None,
                "comment": None,
                "domain_ref": None,
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "c2"},
            },
        ],
        "physical_model_key": [
            {
                "physical_model_key_id": "key_customer",
                "physical_model_table_id": "table_customer",
                "physical_model_source_id": source_id,
                "pdm_object_id": "k1",
                "object_uuid": None,
                "key_name": "PK Customer",
                "key_code": "pk_customer",
                "key_kind": "primary",
                "column_pdm_ids": ["c1"],
                "column_codes": ["id"],
                "unresolved_column_refs": [],
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "k1"},
            }
        ],
        "physical_model_relationship": [
            {
                "physical_model_relationship_id": "rel_order_customer",
                "physical_model_source_id": source_id,
                "pdm_object_id": "r1",
                "object_uuid": None,
                "relationship_name": "Order customer",
                "relationship_code": "fk_order_customer",
                "cardinality": "0..*",
                "parent_table_ref": "t1",
                "parent_table_id": "table_customer",
                "parent_table_code": "customer",
                "child_table_ref": "t2",
                "child_table_id": "table_order",
                "child_table_code": "orders",
                "parent_key_ref": "k1",
                "parent_key_id": "key_customer",
                "joins": [{
                    "pdm_reference_join_id": "j1",
                    "parent_column_ref": "c1",
                    "parent_column_code": "id",
                    "child_column_ref": "c2",
                    "child_column_code": "customer_id",
                }],
                "resolution_status": "resolved",
                "source_file": "fixture.pdm",
                "evidence": {"file": "fixture.pdm", "pdm_object_id": "r1"},
            }
        ],
        "physical_model_gap": ([{
            "physical_model_gap_id": "gap-1",
            "physical_model_source_id": source_id,
            "gap_kind": "relationship_ref_unresolved",
            "owner_pdm_object_id": "r2",
            "unresolved_ref": "missing",
            "message": "Relationship references an object definition that was not found",
        }] if with_gap else []),
    }
    id_fields = {
        "physical_model_table": "physical_model_table_id",
        "physical_model_column": "physical_model_column_id",
        "physical_model_key": "physical_model_key_id",
        "physical_model_relationship": "physical_model_relationship_id",
        "physical_model_gap": "physical_model_gap_id",
    }
    fingerprint = hashlib.sha256()
    entries = []
    for fact_type in PHYSICAL_MODEL_FACT_TYPES:
        path = facts / f"{fact_type}.jsonl"
        lines = [_json_line(record) for record in records[fact_type]]
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        for line in lines:
            fingerprint.update(fact_type.encode("utf-8"))
            fingerprint.update(b"\0")
            fingerprint.update(line.encode("utf-8"))
            fingerprint.update(b"\n")
        entries.append({
            "fact_type": fact_type,
            "id_field": id_fields[fact_type],
            "path": f"facts/{fact_type}.jsonl",
            "record_count": len(records[fact_type]),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    source_sha = hashlib.sha256(b"fixture-pdm").hexdigest()
    metadata = {
        "physical_model_source_id": source_id,
        "schema_version": "physical-model/v1",
        "core_version": "0.43.7",
        "source_file": "fixture.pdm",
        "source_sha256": source_sha,
        "model_object_id": "model-1",
        "model_name": "Fixture",
        "model_code": "fixture",
        "powerdesigner_version": "16.6",
        "powerdesigner_target": "Hadoop Hive 1.0",
    }
    (root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    manifest = {
        "schema_version": "physical-model/v1",
        "physical_model_source_id": source_id,
        "core_version": "0.43.7",
        "content_fingerprint": fingerprint.hexdigest(),
        "source": {
            "file": "fixture.pdm",
            "sha256": source_sha,
            "metadata_path": "metadata.json",
        },
        "counts": {name: len(values) for name, values in records.items()},
        "facts": entries,
        "coverage": {"status": "partial" if with_gap else "complete", "gap_count": int(with_gap)},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_build_physical_model_knowledge_layer_materializes_typed_tables(tmp_path: Path) -> None:
    source_manifest = _write_artifact(tmp_path / "source")
    output = tmp_path / "klc"

    manifest = build_physical_model_knowledge_layer(source_manifest, output)

    assert "common.physical-model.pdm" in manifest["capabilities"]
    assert manifest["counts"]["physical_model_table"] == 2
    assert manifest["counts"]["physical_model_column"] == 2
    assert manifest["metadata"]["coverage"] == {
        "analysis_status": "complete",
        "coverage_basis": "physical_model_parser_contract",
        "physical_model_source_id": "fixture-pdm",
        "table_count": 2,
        "column_count": 2,
        "key_count": 1,
        "relationship_count": 1,
        "gap_count": 0,
        "does_not_claim_business_semantic_completeness": True,
    }
    connection = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    assert connection.execute(
        "SELECT table_code, logical_identity FROM physical_model_table ORDER BY table_code"
    ).fetchall() == [("customer", "business.customer"), ("orders", "business.orders")]
    assert connection.execute(
        "SELECT column_code, mandatory FROM physical_model_column WHERE physical_model_table_id='table_customer'"
    ).fetchall() == [("id", True)]
    assert json.loads(connection.execute(
        "SELECT joins_json FROM physical_model_relationship"
    ).fetchone()[0])[0]["child_column_code"] == "customer_id"
    connection.close()


def test_partial_physical_model_keeps_gaps_without_failing_build(tmp_path: Path) -> None:
    source_manifest = _write_artifact(tmp_path / "source", with_gap=True)
    output = tmp_path / "klc"

    manifest = build_physical_model_knowledge_layer(source_manifest, output)

    assert manifest["metadata"]["source_coverage_status"] == "partial"
    assert manifest["metadata"]["coverage"]["analysis_status"] == "partial"
    assert manifest["metadata"]["coverage"]["gap_count"] == 1
    assert manifest["metadata"]["coverage"]["does_not_claim_business_semantic_completeness"] is True
    assert manifest["counts"]["physical_model_gap"] == 1
    assert manifest["validation"]["gap_count_matches_manifest"] is True


def test_resolver_rejects_tampered_fact_shard(tmp_path: Path) -> None:
    source_manifest = _write_artifact(tmp_path / "source")
    shard = source_manifest.parent / "facts/physical_model_table.jsonl"
    shard.write_text(shard.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        resolve_physical_model_artifact(source_manifest)


def test_build_does_not_replace_existing_output_without_permission(tmp_path: Path) -> None:
    source_manifest = _write_artifact(tmp_path / "source")
    output = tmp_path / "klc"
    build_physical_model_knowledge_layer(source_manifest, output)

    with pytest.raises(FileExistsError):
        build_physical_model_knowledge_layer(source_manifest, output, replace=False)
