from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from knowledge_layer_core.materialization_runtime import (
    MATERIALIZATION_REQUEST_SCHEMA_VERSION,
    materialize,
)
from knowledge_layer_core.physical_model_schema import PHYSICAL_MODEL_FACT_TYPES
from test_code_declared_model_builder import _write_runner_input


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_persistence_evidence(
    run_manifest: Path, *, omit_explicit_names: bool = False, empty_mapping_evidence: bool = False
) -> dict:
    run = json.loads(run_manifest.read_text(encoding="utf-8"))
    repo_id = str(run["repository"]["repo_id"])
    base_id = f"type-{repo_id}-base"
    child_id = f"type-{repo_id}-child"
    base_field = f"field-{repo_id}-id"
    child_field = f"field-{repo_id}-parent"
    source_ref = {
        "repository_relative_path": "src/main/java/example/Model.java",
        "line_start": 1,
        "line_end": 20,
        "extractor": "java_tree_sitter",
    }
    artifact = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_kind": "java-persistence-mapping-evidence",
        "schema_version": "java-persistence-mapping-evidence/v1",
        "producer": {
            "component": "code-analyzer-core",
            "analyzer_id": "java-persistence-mapping-analyzer",
            "analyzer_version": "0.43.28",
        },
        "source_snapshot": {
            "source_id": repo_id,
            "revision": "abc",
            "fingerprint": f"snapshot-{repo_id}",
            "scope": "java_source_files",
            "file_count": 1,
        },
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {
            "language": "java",
            "mapping_policy": "explicit_persistence_annotations_only",
            "jpa_default_naming_inference": False,
        },
        "coverage": {"coverage_status": "complete", "mapping_gap_count": 0},
        "diagnostics": [],
        "provenance": {"semantic_routing": "artifact_kind_plus_schema_version"},
        "payload": {
            "persistence_type_mappings": [
                {
                    "persistence_type_mapping_id": "pt-base",
                    "type_id": base_id,
                    "fully_qualified_name": "example.Base",
                    "simple_name": "Base",
                    "persistence_kind": "entity",
                    "entity_name_explicit": None,
                    "table_name_explicit": None if omit_explicit_names else "base_tbl",
                    "schema_name_explicit": "crm",
                    "catalog_name_explicit": None,
                    "mapping_basis": "explicit_java_persistence_annotations",
                    "annotation_ids": ["a-base"],
                    "source_ref": source_ref,
                },
                {
                    "persistence_type_mapping_id": "pt-child",
                    "type_id": child_id,
                    "fully_qualified_name": "example.Child",
                    "simple_name": "Child",
                    "persistence_kind": "entity",
                    "entity_name_explicit": None,
                    "table_name_explicit": None if omit_explicit_names else "child_tbl",
                    "schema_name_explicit": "crm",
                    "catalog_name_explicit": None,
                    "mapping_basis": "explicit_java_persistence_annotations",
                    "annotation_ids": ["a-child"],
                    "source_ref": source_ref,
                },
            ],
            "persistence_field_mappings": [
                {
                    "persistence_field_mapping_id": "pf-base-id",
                    "field_id": base_field,
                    "owner_type_id": base_id,
                    "owner_fully_qualified_name": "example.Base",
                    "field_name": "id",
                    "declared_type_expression": "String",
                    "persistence_role": "id",
                    "column_name_explicit": None if omit_explicit_names else "base_id",
                    "column_table_name_explicit": None,
                    "join_column_name_explicit": None,
                    "referenced_column_name_explicit": None,
                    "relationship_kind": None,
                    "relationship_mapped_by_explicit": None,
                    "resolved_target_type_id": None,
                    "candidate_target_type_ids": [],
                    "nullable_declared": False,
                    "mapping_basis": "explicit_java_persistence_annotations",
                    "annotation_ids": ["a-id"],
                    "source_ref": source_ref,
                },
                {
                    "persistence_field_mapping_id": "pf-child-parent",
                    "field_id": child_field,
                    "owner_type_id": child_id,
                    "owner_fully_qualified_name": "example.Child",
                    "field_name": "parent",
                    "declared_type_expression": "Base",
                    "persistence_role": "relationship",
                    "column_name_explicit": None,
                    "column_table_name_explicit": None,
                    "join_column_name_explicit": None if omit_explicit_names else "parent_id",
                    "referenced_column_name_explicit": None if omit_explicit_names else "base_id",
                    "relationship_kind": "ManyToOne",
                    "relationship_mapped_by_explicit": None,
                    "resolved_target_type_id": base_id,
                    "candidate_target_type_ids": [base_id],
                    "nullable_declared": None,
                    "mapping_basis": "explicit_java_persistence_annotations",
                    "annotation_ids": ["a-rel"],
                    "source_ref": source_ref,
                },
            ],
            "persistence_key_mappings": [
                {
                    "persistence_key_mapping_id": "pk-base",
                    "owner_type_id": base_id,
                    "field_id": base_field,
                    "key_kind": "id",
                    "column_name_explicit": None if omit_explicit_names else "base_id",
                    "id_class_expression": None,
                    "annotation_ids": ["a-id"],
                    "source_ref": source_ref,
                }
            ],
            "persistence_relationship_mappings": [
                {
                    "persistence_relationship_mapping_id": "pr-child-parent",
                    "field_id": child_field,
                    "source_type_id": child_id,
                    "target_type_id": base_id,
                    "candidate_target_type_ids": [base_id],
                    "relationship_kind": "ManyToOne",
                    "join_column_name_explicit": None if omit_explicit_names else "parent_id",
                    "referenced_column_name_explicit": None if omit_explicit_names else "base_id",
                    "mapped_by_explicit": None,
                    "annotation_ids": ["a-rel"],
                    "source_ref": source_ref,
                }
            ],
            "persistence_inheritance_mappings": [],
            "mapping_gaps": [],
        },
    }
    if empty_mapping_evidence:
        for key in (
            "persistence_type_mappings", "persistence_field_mappings", "persistence_key_mappings",
            "persistence_relationship_mappings", "persistence_inheritance_mappings", "mapping_gaps",
        ):
            artifact["payload"][key] = []
    fingerprint = hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
    artifact["content_fingerprint"] = fingerprint
    artifact["artifact_id"] = f"java_persistence_mapping_{fingerprint[:24]}"
    artifact_path = run_manifest.parent / "static-analysis-output/evidence/java-persistence-mapping-evidence.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    registration = {
        "artifact_id": artifact["artifact_id"],
        "artifact_kind": artifact["artifact_kind"],
        "schema_version": artifact["schema_version"],
        "contract_version": artifact["contract_version"],
        "semantic_identity": {"artifact_kind": artifact["artifact_kind"], "schema_version": artifact["schema_version"]},
        "content_fingerprint": fingerprint,
        "status": "completed",
        "coverage": artifact["coverage"],
        "diagnostics": {"count": 0},
        "location": {
            "kind": "file",
            "path": "static-analysis-output/evidence/java-persistence-mapping-evidence.json",
            "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "bytes": artifact_path.stat().st_size,
        },
    }
    run["evidence_artifacts"].append(registration)
    run_manifest.write_text(json.dumps(run, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return registration


def _write_physical_artifact(root: Path, *, include_relationship: bool = True) -> Path:
    facts = root / "facts"
    facts.mkdir(parents=True)
    source_id = "fixture-pdm"
    records = {
        "physical_model_table": [
            {
                "physical_model_table_id": "table-base", "physical_model_source_id": source_id,
                "pdm_object_id": "tb", "object_uuid": None, "model_name": "Fixture", "model_code": "fixture",
                "package_path": ["CRM"], "package_code_path": ["crm"], "table_name": "Base", "table_code": "base_tbl",
                "logical_identity": "crm.base_tbl", "comment": None, "description": None, "stereotype": None,
                "dimensional_type": None, "owner_ref": None, "column_count": 1, "key_count": 1,
                "source_file": "fixture.pdm", "evidence": {},
            },
            {
                "physical_model_table_id": "table-child", "physical_model_source_id": source_id,
                "pdm_object_id": "tc", "object_uuid": None, "model_name": "Fixture", "model_code": "fixture",
                "package_path": ["CRM"], "package_code_path": ["crm"], "table_name": "Child", "table_code": "child_tbl",
                "logical_identity": "crm.child_tbl", "comment": None, "description": None, "stereotype": None,
                "dimensional_type": None, "owner_ref": None, "column_count": 1, "key_count": 0,
                "source_file": "fixture.pdm", "evidence": {},
            },
        ],
        "physical_model_column": [
            {
                "physical_model_column_id": "column-base-id", "physical_model_table_id": "table-base",
                "physical_model_source_id": source_id, "pdm_object_id": "cb", "object_uuid": None, "ordinal": 1,
                "column_name": "Base Id", "column_code": "base_id", "data_type": "string", "length": 64,
                "precision": None, "mandatory": True, "default_value": None, "comment": None, "domain_ref": None,
                "source_file": "fixture.pdm", "evidence": {},
            },
            {
                "physical_model_column_id": "column-child-parent", "physical_model_table_id": "table-child",
                "physical_model_source_id": source_id, "pdm_object_id": "cc", "object_uuid": None, "ordinal": 1,
                "column_name": "Parent Id", "column_code": "parent_id", "data_type": "string", "length": 64,
                "precision": None, "mandatory": False, "default_value": None, "comment": None, "domain_ref": None,
                "source_file": "fixture.pdm", "evidence": {},
            },
        ],
        "physical_model_key": [
            {
                "physical_model_key_id": "key-base", "physical_model_table_id": "table-base",
                "physical_model_source_id": source_id, "pdm_object_id": "kb", "object_uuid": None,
                "key_name": "PK Base", "key_code": "pk_base", "key_kind": "primary",
                "column_pdm_ids": ["cb"], "column_codes": ["base_id"], "unresolved_column_refs": [],
                "source_file": "fixture.pdm", "evidence": {},
            }
        ],
        "physical_model_relationship": ([
            {
                "physical_model_relationship_id": "rel-child-base", "physical_model_source_id": source_id,
                "pdm_object_id": "rb", "object_uuid": None, "relationship_name": "Child parent",
                "relationship_code": "fk_child_base", "cardinality": "*..1", "parent_table_ref": "tb",
                "parent_table_id": "table-base", "parent_table_code": "base_tbl", "child_table_ref": "tc",
                "child_table_id": "table-child", "child_table_code": "child_tbl", "parent_key_ref": "kb",
                "parent_key_id": "key-base", "joins": [{"parent_column_code": "base_id", "child_column_code": "parent_id"}],
                "resolution_status": "resolved", "source_file": "fixture.pdm", "evidence": {},
            }
        ] if include_relationship else []),
        "physical_model_gap": [],
    }
    id_fields = {
        "physical_model_table": "physical_model_table_id", "physical_model_column": "physical_model_column_id",
        "physical_model_key": "physical_model_key_id", "physical_model_relationship": "physical_model_relationship_id",
        "physical_model_gap": "physical_model_gap_id",
    }
    fingerprint = hashlib.sha256()
    entries = []
    for fact_type in PHYSICAL_MODEL_FACT_TYPES:
        path = facts / f"{fact_type}.jsonl"
        lines = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in records[fact_type]]
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        for line in lines:
            fingerprint.update(fact_type.encode("utf-8")); fingerprint.update(b"\0")
            fingerprint.update(line.encode("utf-8")); fingerprint.update(b"\n")
        entries.append({
            "fact_type": fact_type, "id_field": id_fields[fact_type], "path": f"facts/{fact_type}.jsonl",
            "record_count": len(lines), "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    source_sha = hashlib.sha256(b"fixture-pdm").hexdigest()
    (root / "metadata.json").write_text(json.dumps({
        "physical_model_source_id": source_id, "schema_version": "physical-model/v1", "core_version": "fixture",
        "source_file": "fixture.pdm", "source_sha256": source_sha, "model_object_id": "model-1",
        "model_name": "Fixture", "model_code": "fixture",
    }), encoding="utf-8")
    manifest = {
        "schema_version": "physical-model/v1", "physical_model_source_id": source_id,
        "core_version": "fixture", "content_fingerprint": fingerprint.hexdigest(),
        "source": {"file": "fixture.pdm", "sha256": source_sha, "metadata_path": "metadata.json"},
        "counts": {name: len(values) for name, values in records.items()}, "facts": entries,
        "coverage": {"status": "complete", "gap_count": 0},
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def _code_request(manifest: Path) -> dict:
    run = json.loads(manifest.read_text(encoding="utf-8"))
    item = next(value for value in run["evidence_artifacts"] if value["artifact_kind"] == "java-type-structure-evidence")
    return {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "code-declared-data-model",
        "scope_id": "scope-a",
        "inputs": {"evidence_artifacts": [{
            "artifact_id": item["artifact_id"], "artifact_kind": item["artifact_kind"],
            "schema_version": item["schema_version"], "content_fingerprint": item["content_fingerprint"],
            "registration_manifest_path": str(manifest),
        }], "knowledge_artifacts": []},
        "parameters": {},
    }


def _physical_request(manifest: Path) -> dict:
    source = json.loads(manifest.read_text(encoding="utf-8"))
    return {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "physical-model",
        "scope_id": "scope-a",
        "inputs": {"evidence_artifacts": [{
            "artifact_id": "physical-model-fixture", "artifact_kind": "physical-model",
            "schema_version": "physical-model/v1", "content_fingerprint": source["content_fingerprint"],
            "location": {"kind": "file", "path": str(manifest)},
        }], "knowledge_artifacts": []},
        "parameters": {},
    }


def test_generic_runtime_materializes_logical_physical_mapping(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    persistence = _write_persistence_evidence(runner_manifest)
    physical_manifest = _write_physical_artifact(tmp_path / "pdm")

    code = materialize(_code_request(runner_manifest), tmp_path / "code-model")
    physical = materialize(_physical_request(physical_manifest), tmp_path / "physical-model")
    request = {
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "logical-physical-mapping",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": persistence["artifact_id"], "artifact_kind": persistence["artifact_kind"],
                "schema_version": persistence["schema_version"], "content_fingerprint": persistence["content_fingerprint"],
                "registration_manifest_path": str(runner_manifest),
            }],
            "knowledge_artifacts": [code["knowledge_artifacts"][0], physical["knowledge_artifacts"][0]],
        },
        "parameters": {},
    }
    result = materialize(request, tmp_path / "mapping")

    assert result["status"] == "completed"
    assert result["published_capabilities"] == [
        "common.entity-table-mapping", "common.field-column-mapping", "common.logical-physical-mapping"
    ]
    assert result["knowledge_artifacts"][0]["schema_version"] == "logical-physical-model-mapping/v1"
    coverage = result["knowledge_artifacts"][0]["coverage"]
    assert coverage["analysis_status"] == "complete"
    assert coverage["mapping_coverage_status"] == "complete_for_observed_mapping_evidence"
    assert coverage["observed_mapping_count"] == 6
    assert coverage["matched_mapping_count"] == 6
    assert coverage["does_not_claim_all_logical_objects_are_mapped"] is True
    connection = duckdb.connect(str(tmp_path / "mapping/knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute(
            "SELECT logical_fully_qualified_name, physical_table_code, mapping_status FROM logical_physical_entity_mapping ORDER BY logical_fully_qualified_name"
        ).fetchall() == [
            ("example.Base", "base_tbl", "matched"),
            ("example.Child", "child_tbl", "matched"),
        ]
        assert connection.execute(
            "SELECT logical_field_name, physical_column_code, mapping_status FROM logical_physical_field_mapping ORDER BY logical_field_name"
        ).fetchall() == [
            ("id", "base_id", "matched"),
            ("parent", "parent_id", "matched"),
        ]
        assert connection.execute("SELECT mapping_status, physical_model_key_id FROM logical_physical_key_mapping").fetchall() == [
            ("matched", "key-base")
        ]
        assert connection.execute(
            "SELECT mapping_status, physical_model_relationship_id FROM logical_physical_relationship_mapping"
        ).fetchall() == [("matched", "rel-child-base")]
        assert connection.execute("SELECT count(*) FROM logical_physical_mapping_gap").fetchone()[0] == 0
    finally:
        connection.close()


def test_zero_observed_mapping_records_never_publish_complete_mapping_coverage(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    persistence = _write_persistence_evidence(runner_manifest, empty_mapping_evidence=True)
    physical_manifest = _write_physical_artifact(tmp_path / "pdm")
    code = materialize(_code_request(runner_manifest), tmp_path / "code-model")
    physical = materialize(_physical_request(physical_manifest), tmp_path / "physical-model")
    result = materialize({
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "logical-physical-mapping",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": persistence["artifact_id"], "artifact_kind": persistence["artifact_kind"],
                "schema_version": persistence["schema_version"], "content_fingerprint": persistence["content_fingerprint"],
                "registration_manifest_path": str(runner_manifest),
            }],
            "knowledge_artifacts": [code["knowledge_artifacts"][0], physical["knowledge_artifacts"][0]],
        },
        "parameters": {},
    }, tmp_path / "mapping")
    coverage = result["knowledge_artifacts"][0]["coverage"]
    assert coverage["analysis_status"] == "complete"
    assert coverage["mapping_coverage_status"] == "no_mapping_evidence"
    assert coverage["observed_mapping_count"] == 0
    assert coverage["matched_mapping_count"] == 0
    assert coverage["gap_count"] == 0


def test_no_default_name_inference_creates_explicit_gaps(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    persistence = _write_persistence_evidence(runner_manifest, omit_explicit_names=True)
    physical_manifest = _write_physical_artifact(tmp_path / "pdm")
    code = materialize(_code_request(runner_manifest), tmp_path / "code-model")
    physical = materialize(_physical_request(physical_manifest), tmp_path / "physical-model")
    result = materialize({
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "logical-physical-mapping",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": persistence["artifact_id"], "artifact_kind": persistence["artifact_kind"],
                "schema_version": persistence["schema_version"], "content_fingerprint": persistence["content_fingerprint"],
                "registration_manifest_path": str(runner_manifest),
            }],
            "knowledge_artifacts": [code["knowledge_artifacts"][0], physical["knowledge_artifacts"][0]],
        },
        "parameters": {},
    }, tmp_path / "mapping")
    assert result["status"] == "completed"
    connection = duckdb.connect(str(tmp_path / "mapping/knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute(
            "SELECT DISTINCT mapping_status FROM logical_physical_entity_mapping"
        ).fetchall() == [("unresolved",)]
        gap_kinds = {row[0] for row in connection.execute("SELECT gap_kind FROM logical_physical_mapping_gap").fetchall()}
        assert "explicit_table_name_absent" in gap_kinds
        assert "explicit_column_name_absent" in gap_kinds or "owner_entity_not_mapped" in gap_kinds
        checks = json.loads(connection.execute("SELECT checks_json FROM logical_physical_mapping_build").fetchone()[0])
        assert checks["jpa_default_naming_inference_used"] is False
        assert checks["name_similarity_matching_used"] is False
    finally:
        connection.close()


def test_missing_physical_relationship_is_explicit_gap(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    persistence = _write_persistence_evidence(runner_manifest)
    physical_manifest = _write_physical_artifact(tmp_path / "pdm", include_relationship=False)
    code = materialize(_code_request(runner_manifest), tmp_path / "code-model")
    physical = materialize(_physical_request(physical_manifest), tmp_path / "physical-model")
    result = materialize({
        "schema_version": MATERIALIZATION_REQUEST_SCHEMA_VERSION,
        "materialization_id": "logical-physical-mapping",
        "scope_id": "scope-a",
        "inputs": {
            "evidence_artifacts": [{
                "artifact_id": persistence["artifact_id"], "artifact_kind": persistence["artifact_kind"],
                "schema_version": persistence["schema_version"], "content_fingerprint": persistence["content_fingerprint"],
                "registration_manifest_path": str(runner_manifest),
            }],
            "knowledge_artifacts": [code["knowledge_artifacts"][0], physical["knowledge_artifacts"][0]],
        },
        "parameters": {},
    }, tmp_path / "mapping")
    assert result["status"] == "completed"
    coverage = result["knowledge_artifacts"][0]["coverage"]
    assert coverage["analysis_status"] == "partial"
    assert coverage["mapping_coverage_status"] == "partial"
    assert coverage["unresolved_mapping_count"] > 0
    connection = duckdb.connect(str(tmp_path / "mapping/knowledge-layer.duckdb"), read_only=True)
    try:
        assert connection.execute(
            "SELECT mapping_status, physical_model_relationship_id FROM logical_physical_relationship_mapping"
        ).fetchall() == [("unresolved", None)]
        assert connection.execute(
            "SELECT count(*) FROM logical_physical_mapping_gap WHERE gap_kind='physical_relationship_not_found'"
        ).fetchone()[0] == 1
    finally:
        connection.close()
