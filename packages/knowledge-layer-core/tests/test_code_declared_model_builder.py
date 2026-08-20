from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from knowledge_layer_core.code_declared_model_builder import build_code_declared_data_model_knowledge_layer
from knowledge_layer_core.code_declared_model_ingestion import resolve_java_type_structure_artifact
from knowledge_layer_core.version import __version__


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_runner_input(
    root: Path, repo_id: str, *, invalid_fingerprint: bool = False, include_evidence: bool = True,
    coverage_status: str = "complete", unsupported_declaration_count: int = 0,
) -> Path:
    run = root / repo_id
    artifact_path = run / "static-analysis-output/evidence/java-type-structure-evidence.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    source_unit_id = f"unit-{repo_id}"
    base_id = f"type-{repo_id}-base"
    child_id = f"type-{repo_id}-child"
    base_field_id = f"field-{repo_id}-id"
    child_field_id = f"field-{repo_id}-parent"
    inheritance_id = f"inheritance-{repo_id}"
    reference_id = f"ref-{repo_id}"
    source_ref = {"repository_relative_path": "src/main/java/example/Model.java", "line_start": 1, "line_end": 20, "extractor": "java_tree_sitter"}
    artifact = {
        "contract_version": "core_evidence_artifact_contract/v1",
        "artifact_kind": "java-type-structure-evidence",
        "schema_version": "java-type-structure-evidence/v1",
        "producer": {"component": "code-analyzer-core", "analyzer_id": "java-type-structure-analyzer", "analyzer_version": "0.43.26"},
        "source_snapshot": {"source_id": repo_id, "revision": "abc", "fingerprint": f"snapshot-{repo_id}", "scope": "java_source_files", "file_count": 1},
        "foundation": {"used": False, "contract_version": None, "fingerprint": None, "sections": []},
        "parameters": {"language": "java", "include_test_sources": False, "record_limit": None},
        "coverage": {
            "coverage_status": coverage_status, "java_files_discovered": 1, "java_files_in_scope": 1, "java_files_parsed": 1,
            "java_files_failed": 0, "java_files_with_parse_errors": 0, "type_declaration_count": 2,
            "field_declaration_count": 2, "inheritance_declaration_count": 1, "annotation_declaration_count": 1,
            "type_reference_count": 1, "unresolved_type_reference_count": 0, "ambiguous_type_reference_count": 0,
            "unsupported_declaration_count": unsupported_declaration_count,
        },
        "diagnostics": [],
        "provenance": {"semantic_routing": "artifact_kind_plus_schema_version"},
        "payload": {
            "source_units": [{
                "source_unit_id": source_unit_id, "repository_relative_path": "src/main/java/example/Model.java", "language": "java",
                "package_name": "example", "imports": [], "parse_status": "success", "parse_error_count": 0, "source_set": "main",
            }],
            "type_declarations": [
                {"type_id": base_id, "source_unit_id": source_unit_id, "fully_qualified_name": "example.Base", "simple_name": "Base", "package_name": "example", "type_kind": "class", "modifier_tokens": ["public"], "type_parameters": [], "source_set": "main", "source_ref": source_ref},
                {"type_id": child_id, "source_unit_id": source_unit_id, "fully_qualified_name": "example.Child", "simple_name": "Child", "package_name": "example", "type_kind": "class", "modifier_tokens": ["public"], "type_parameters": [], "source_set": "main", "source_ref": source_ref},
            ],
            "field_declarations": [
                {"field_id": base_field_id, "owner_type_id": base_id, "name": "id", "declared_type_expression": "String", "normalized_type_expression": "String", "modifier_tokens": ["private"], "is_static": False, "is_final": False, "initializer_present": False, "source_ref": source_ref},
                {"field_id": child_field_id, "owner_type_id": child_id, "name": "parent", "declared_type_expression": "Base", "normalized_type_expression": "Base", "modifier_tokens": ["private"], "is_static": False, "is_final": False, "initializer_present": False, "source_ref": source_ref},
            ],
            "inheritance_declarations": [{
                "inheritance_id": inheritance_id, "subtype_id": child_id, "relation_kind": "extends", "declared_supertype_expression": "Base",
                "resolution_status": "same_package", "resolved_supertype_id": base_id, "candidate_supertype_ids": [base_id],
                "resolved_fqcn": "example.Base", "candidate_fqcns": ["example.Base"], "type_arguments": [], "source_ref": source_ref,
            }],
            "annotation_declarations": [{
                "annotation_id": f"annotation-{repo_id}", "target_kind": "type", "target_id": child_id, "annotation_name": "Deprecated",
                "arguments_raw": None, "structured_arguments": [], "resolution_status": "java_lang", "resolved_annotation_type": "java.lang.Deprecated",
                "candidate_annotation_types": ["java.lang.Deprecated"], "source_ref": source_ref,
            }],
            "type_reference_observations": [{
                "type_reference_id": reference_id, "owner_kind": "field", "owner_id": child_field_id, "reference_role": "field_type",
                "declared_type_expression": "Base", "referenced_type_token": "Base", "resolution_status": "same_package",
                "resolved_type_id": base_id, "candidate_type_ids": [base_id], "resolved_fqcn": "example.Base", "candidate_fqcns": ["example.Base"], "source_ref": source_ref,
            }],
            "enum_constant_declarations": [],
        },
    }
    fingerprint = hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
    artifact["content_fingerprint"] = "invalid" if invalid_fingerprint else fingerprint
    artifact["artifact_id"] = "java_type_structure_" + artifact["content_fingerprint"][:24]
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    file_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    registration = {
        "artifact_id": artifact["artifact_id"], "artifact_kind": artifact["artifact_kind"], "schema_version": artifact["schema_version"],
        "contract_version": artifact["contract_version"], "semantic_identity": {"artifact_kind": artifact["artifact_kind"], "schema_version": artifact["schema_version"]},
        "content_fingerprint": artifact["content_fingerprint"], "status": "completed", "coverage": artifact["coverage"], "diagnostics": {"count": 0},
        "location": {"kind": "file", "path": "static-analysis-output/evidence/java-type-structure-evidence.json", "sha256": file_sha, "bytes": artifact_path.stat().st_size},
    }
    manifest = {
        "schema_version": "static_repository_analysis_run_manifest/v1",
        "runner": {"producer": "static-analysis-runner", "version": "0.9.46"},
        "repository": {"repo_id": repo_id, "requested_repo_id": repo_id, "source_path": str(root / "source")},
        "evidence_artifacts": [registration] if include_evidence else [],
        "status": "completed",
    }
    manifest_path = run / "repository_analysis_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_builds_code_declared_model_without_legacy(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a")
    output = tmp_path / "klc"
    manifest = build_code_declared_data_model_knowledge_layer([runner_manifest], output)

    assert manifest["producer_version"] == __version__
    assert set(manifest["capabilities"]) == {
        "common.code-declared-data-model", "common.code-declared-entities", "common.code-declared-fields",
        "common.code-declared-inheritance", "common.code-declared-relationships",
    }
    assert manifest["metadata"]["legacy_policy"] == "not_supported"
    assert manifest["metadata"]["coverage"]["analysis_status"] == "complete"
    assert manifest["metadata"]["coverage"]["repository_status_counts"] == {"complete": 1}
    assert manifest["metadata"]["coverage"]["model_gap_count"] == 0

    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from code_declared_type").fetchone()[0] == 2
        assert con.execute("select count(*) from code_declared_field").fetchone()[0] == 2
        effective = con.execute(
            "select field_name, is_inherited, inherited_depth from code_declared_effective_field order by field_name, is_inherited"
        ).fetchall()
        assert effective == [("id", False, 0), ("id", True, 1), ("parent", False, 0)]
        assert con.execute("select relationship_kind from code_declared_relationship").fetchall() == [("declared_field_type_reference",)]
    finally:
        con.close()


def test_product_coverage_preserves_partial_source_coverage(tmp_path: Path) -> None:
    first = _write_runner_input(tmp_path, "repo-a")
    second = _write_runner_input(
        tmp_path, "repo-b", coverage_status="partial", unsupported_declaration_count=3
    )
    output = tmp_path / "coverage-klc"
    manifest = build_code_declared_data_model_knowledge_layer([first, second], output, scope_id="workspace-x")
    coverage = manifest["metadata"]["coverage"]
    assert coverage["analysis_status"] == "partial"
    assert coverage["repository_status_counts"] == {"complete": 1, "partial": 1}
    assert coverage["unsupported_declaration_count"] == 3
    assert coverage["source_coverage_by_repository"]["repo-b"]["coverage_status"] == "partial"


def test_workspace_materialization_keeps_repository_occurrences_distinct(tmp_path: Path) -> None:
    first = _write_runner_input(tmp_path, "repo-a")
    second = _write_runner_input(tmp_path, "repo-b")
    output = tmp_path / "workspace-klc"
    manifest = build_code_declared_data_model_knowledge_layer([first, second], output, scope_id="workspace-x")
    assert manifest["scope_type"] == "workspace"
    assert manifest["repository_ids"] == ["repo-a", "repo-b"]
    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        assert con.execute("select count(*) from code_declared_model_source").fetchone()[0] == 2
        assert con.execute("select count(*) from code_declared_type").fetchone()[0] == 4
    finally:
        con.close()


def test_missing_typed_evidence_has_no_legacy_fallback(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a", include_evidence=False)
    with pytest.raises(ValueError, match="exactly one java-type-structure-evidence"):
        build_code_declared_data_model_knowledge_layer([runner_manifest], tmp_path / "klc")


def test_invalid_content_fingerprint_is_rejected(tmp_path: Path) -> None:
    runner_manifest = _write_runner_input(tmp_path, "repo-a", invalid_fingerprint=True)
    with pytest.raises(ValueError, match="content_fingerprint is invalid"):
        resolve_java_type_structure_artifact(runner_manifest)


def _write_inherited_relationship_input(root: Path, repo_id: str) -> Path:
    manifest_path = _write_runner_input(root, repo_id)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registration = manifest["evidence_artifacts"][0]
    artifact_path = manifest_path.parent / registration["location"]["path"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload = artifact["payload"]

    target_id = f"type-{repo_id}-target"
    target_field_id = f"field-{repo_id}-target"
    target_ref_id = f"ref-{repo_id}-inherited-target"
    source_unit_id = payload["source_units"][0]["source_unit_id"]
    source_ref = payload["type_declarations"][0]["source_ref"]
    base_id = f"type-{repo_id}-base"

    payload["type_declarations"].append({
        "type_id": target_id, "source_unit_id": source_unit_id,
        "fully_qualified_name": "example.Target", "simple_name": "Target", "package_name": "example",
        "type_kind": "class", "modifier_tokens": ["public"], "type_parameters": [], "source_set": "main", "source_ref": source_ref,
    })
    payload["field_declarations"].append({
        "field_id": target_field_id, "owner_type_id": base_id, "name": "target",
        "declared_type_expression": "Target", "normalized_type_expression": "Target",
        "modifier_tokens": ["private"], "is_static": False, "is_final": False,
        "initializer_present": False, "source_ref": source_ref,
    })
    payload["type_reference_observations"].append({
        "type_reference_id": target_ref_id, "owner_kind": "field", "owner_id": target_field_id,
        "reference_role": "field_type", "declared_type_expression": "Target", "referenced_type_token": "Target",
        "resolution_status": "same_package", "resolved_type_id": target_id, "candidate_type_ids": [target_id],
        "resolved_fqcn": "example.Target", "candidate_fqcns": ["example.Target"], "source_ref": source_ref,
    })
    coverage = artifact["coverage"]
    coverage["type_declaration_count"] += 1
    coverage["field_declaration_count"] += 1
    coverage["type_reference_count"] += 1

    artifact.pop("content_fingerprint", None)
    artifact.pop("artifact_id", None)
    fingerprint = hashlib.sha256(_canonical_bytes(artifact)).hexdigest()
    artifact["content_fingerprint"] = fingerprint
    artifact["artifact_id"] = "java_type_structure_" + fingerprint[:24]
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    registration["artifact_id"] = artifact["artifact_id"]
    registration["content_fingerprint"] = fingerprint
    registration["coverage"] = coverage
    registration["location"]["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    registration["location"]["bytes"] = artifact_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_inherited_field_type_reference_becomes_effective_relationship(tmp_path: Path) -> None:
    runner_manifest = _write_inherited_relationship_input(tmp_path, "repo-a")
    output = tmp_path / "klc-inherited"
    build_code_declared_data_model_knowledge_layer([runner_manifest], output)

    con = duckdb.connect(str(output / "knowledge-layer.duckdb"), read_only=True)
    try:
        relationships = con.execute(
            "select source.fully_qualified_name, target.fully_qualified_name, f.name, r.relationship_kind "
            "from code_declared_relationship r "
            "join code_declared_type source on source.type_occurrence_id=r.source_type_occurrence_id "
            "join code_declared_type target on target.type_occurrence_id=r.target_type_occurrence_id "
            "join code_declared_field f on f.field_occurrence_id=r.field_occurrence_id "
            "where f.name='target' order by source.fully_qualified_name"
        ).fetchall()
        assert relationships == [
            ("example.Base", "example.Target", "target", "declared_field_type_reference"),
            ("example.Child", "example.Target", "target", "inherited_field_type_reference"),
        ]
    finally:
        con.close()
