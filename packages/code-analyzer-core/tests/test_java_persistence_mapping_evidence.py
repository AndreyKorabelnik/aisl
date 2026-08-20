from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from code_analyzer_core.evidence_runtime import REQUEST_SCHEMA_VERSION, execute_evidence_request, registered_evidence_analyzers
from code_analyzer_core.prepared_artifacts.java_persistence_mapping_evidence import (
    ANALYZER_ID,
    ARTIFACT_KIND,
    SCHEMA_VERSION,
    build_java_persistence_mapping_evidence,
)
from code_analyzer_core.scanners.java_syntax import tree_sitter_available
from code_analyzer_core.scanners.repo_scanner import scan_files


def _require_tree_sitter() -> None:
    ok, detail = tree_sitter_available()
    if not ok:
        pytest.skip(detail)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/example/model"
    src.mkdir(parents=True)
    (src / "Customer.java").write_text(
        '''
package example.model;
import jakarta.persistence.*;
@Entity(name="CustomerEntity")
@Table(name="customer_tbl", schema="crm")
public class Customer {
  @Id @Column(name="customer_id", nullable=false) private String id;
  @Column(name="full_name") private String name;
  @ManyToOne(fetch=FetchType.LAZY)
  @JoinColumn(name="address_id", referencedColumnName="address_id")
  private Address address;
  @Transient private String computed;
}
@Entity @Table(name="address_tbl")
class Address { @Id @Column(name="address_id") String id; }
''',
        encoding="utf-8",
    )
    return repo


def _request(repo_id: str = "repo") -> dict:
    payload = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "source": {"source_kind": "repository", "source_id": repo_id},
        "evidence_requirements": [{
            "artifact_kind": ARTIFACT_KIND,
            "schema_version": SCHEMA_VERSION,
            "parameters": {},
            "required_by": ["logical-physical-mapping"],
        }],
        "orchestration": {"owner": "test"},
    }
    payload["request_fingerprint"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def test_builder_publishes_explicit_entity_table_and_field_column_mappings(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    artifact = build_java_persistence_mapping_evidence(repository=repo, files=scan_files(repo), repo_id="repo")

    assert artifact["artifact_kind"] == ARTIFACT_KIND
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["parameters"]["jpa_default_naming_inference"] is False
    types = {item["fully_qualified_name"]: item for item in artifact["payload"]["persistence_type_mappings"]}
    assert types["example.model.Customer"]["table_name_explicit"] == "customer_tbl"
    assert types["example.model.Customer"]["schema_name_explicit"] == "crm"
    fields = {(item["owner_fully_qualified_name"], item["field_name"]): item for item in artifact["payload"]["persistence_field_mappings"]}
    assert fields[("example.model.Customer", "id")]["column_name_explicit"] == "customer_id"
    assert fields[("example.model.Customer", "id")]["persistence_role"] == "id"
    assert fields[("example.model.Customer", "address")]["join_column_name_explicit"] == "address_id"
    assert fields[("example.model.Customer", "address")]["relationship_kind"] == "ManyToOne"
    assert fields[("example.model.Customer", "address")]["resolved_target_type_id"]
    assert fields[("example.model.Customer", "computed")]["persistence_role"] == "transient"
    assert len(artifact["payload"]["persistence_key_mappings"]) == 2
    assert len(artifact["payload"]["persistence_relationship_mappings"]) == 1


def test_builder_does_not_infer_default_physical_names(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = tmp_path / "repo"
    src = repo / "src/main/java/example"
    src.mkdir(parents=True)
    (src / "Implicit.java").write_text(
        "package example; import jakarta.persistence.*; @Entity class Implicit { @Id String id; }",
        encoding="utf-8",
    )
    artifact = build_java_persistence_mapping_evidence(repository=repo, files=scan_files(repo), repo_id="repo")
    type_mapping = artifact["payload"]["persistence_type_mappings"][0]
    field_mapping = artifact["payload"]["persistence_field_mappings"][0]
    assert type_mapping["table_name_explicit"] is None
    assert field_mapping["column_name_explicit"] is None
    assert {item["gap_code"] for item in artifact["payload"]["mapping_gaps"]} == {"explicit_table_name_absent"}
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert '"table_name_explicit": "Implicit"' not in serialized
    assert '"column_name_explicit": "id"' not in serialized


def test_generic_runtime_executes_second_registered_evidence_family(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    result = execute_evidence_request(repository=repo, request=_request(), output=tmp_path / "out", repo_id="repo")
    artifact = result["evidence_artifacts"][0]
    assert result["status"] == "completed"
    assert artifact["artifact_kind"] == ARTIFACT_KIND
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["location"]["path"] == "evidence/java-persistence-mapping-evidence.json"
    registrations = {(item.artifact_kind, item.schema_version): item for item in registered_evidence_analyzers()}
    assert registrations[(ARTIFACT_KIND, SCHEMA_VERSION)].analyzer_id == ANALYZER_ID


def test_builder_is_deterministic_and_repository_relative(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    files = scan_files(repo)
    first = build_java_persistence_mapping_evidence(repository=repo, files=files, repo_id="repo")
    second = build_java_persistence_mapping_evidence(repository=repo, files=list(reversed(files)), repo_id="repo")
    assert first == second
    assert str(repo) not in json.dumps(first, ensure_ascii=False)
