from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analyzer_core.evidence_runtime import (
    REQUEST_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    execute_evidence_request,
    registered_evidence_analyzers,
)
from code_analyzer_core.pipeline import run_analysis
from code_analyzer_core.prepared_artifacts.java_type_structure_evidence import (
    ARTIFACT_KIND,
    SCHEMA_VERSION,
    build_java_type_structure_evidence,
)
from code_analyzer_core.scanners.java_syntax import tree_sitter_available
from code_analyzer_core.scanners.repo_scanner import scan_files


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "analysis-profile-fragments" / "repository-analysis-foundation.yaml"


def _require_tree_sitter() -> None:
    ok, detail = tree_sitter_available()
    if not ok:
        pytest.skip(detail)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    src = repo / "src/main/java/example/model"
    src.mkdir(parents=True)
    (src / "Base.java").write_text(
        "package example.model; public class Base { protected String inherited; }\n",
        encoding="utf-8",
    )
    (src / "Customer.java").write_text(
        """
package example.model;
import java.util.List;
@Entity
public class Customer extends Base implements Comparable<Customer> {
  public static final String KIND = "customer";
  @Deprecated private String id;
  private List<Address> addresses;
  public int compareTo(Customer other) { return 0; }
}
class Address { String city; }
""",
        encoding="utf-8",
    )
    (src / "Status.java").write_text(
        "package example.model; public enum Status { ACTIVE, INACTIVE }\n",
        encoding="utf-8",
    )
    (src / "Point.java").write_text(
        "package example.model; public record Point(int x, int y) {}\n",
        encoding="utf-8",
    )
    return repo


def test_builder_publishes_complete_raw_declarations(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    artifact = build_java_type_structure_evidence(
        repository=repo,
        files=scan_files(repo),
        repo_id="repo",
    )

    assert artifact["contract_version"] == "core_evidence_artifact_contract/v1"
    assert artifact["artifact_kind"] == ARTIFACT_KIND
    assert artifact["schema_version"] == SCHEMA_VERSION
    assert artifact["foundation"]["used"] is False
    assert artifact["parameters"]["record_limit"] is None
    assert artifact["coverage"]["coverage_status"] == "complete"

    payload = artifact["payload"]
    names = {item["fully_qualified_name"] for item in payload["type_declarations"]}
    assert {"example.model.Base", "example.model.Customer", "example.model.Address", "example.model.Status", "example.model.Point"} <= names
    fields = {(item["name"], item["is_static"]) for item in payload["field_declarations"]}
    assert ("KIND", True) in fields
    assert ("id", False) in fields
    assert {item["name"] for item in payload["enum_constant_declarations"]} == {"ACTIVE", "INACTIVE"}
    assert {item["name"] for item in payload["field_declarations"] if item["owner_type_id"] == next(t["type_id"] for t in payload["type_declarations"] if t["simple_name"] == "Point")} == {"x", "y"}


def test_builder_keeps_annotations_raw_and_does_not_publish_effective_semantics(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    artifact = build_java_type_structure_evidence(repository=repo, files=scan_files(repo), repo_id="repo")
    payload = artifact["payload"]

    annotations = {item["annotation_name"] for item in payload["annotation_declarations"]}
    assert {"Entity", "Deprecated"} <= annotations
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "jpa_entity" not in serialized
    assert "logical_physical" not in serialized
    assert "effective_entity_field" not in serialized
    assert "effective_entity_association" not in serialized


def test_builder_is_deterministic_and_repository_relative(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    files = scan_files(repo)
    first = build_java_type_structure_evidence(repository=repo, files=files, repo_id="repo")
    second = build_java_type_structure_evidence(repository=repo, files=list(reversed(files)), repo_id="repo")
    assert first == second
    assert first["content_fingerprint"] == second["content_fingerprint"]
    serialized = json.dumps(first, ensure_ascii=False)
    assert str(repo) not in serialized


def _request(repo_id: str = "repo") -> dict:
    import hashlib

    payload = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "source": {"source_kind": "repository", "source_id": repo_id},
        "evidence_requirements": [
            {
                "artifact_kind": ARTIFACT_KIND,
                "schema_version": SCHEMA_VERSION,
                "parameters": {},
                "required_by": ["code-declared-data-model"],
            }
        ],
        "orchestration": {"owner": "test"},
    }
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["request_fingerprint"] = hashlib.sha256(material).hexdigest()
    return payload


def test_generic_runtime_executes_registered_analyzer(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    out = tmp_path / "evidence-out"
    result = execute_evidence_request(
        repository=repo,
        request=_request(),
        output=out,
        repo_id="repo",
    )

    assert result["schema_version"] == RESULT_SCHEMA_VERSION
    assert result["runtime_contract_id"] == "core_evidence_runtime/v1"
    assert result["status"] == "completed"
    assert len(result["analyzer_executions"]) == 1
    registration = result["evidence_artifacts"][0]
    assert registration["artifact_kind"] == ARTIFACT_KIND
    assert registration["schema_version"] == SCHEMA_VERSION
    assert registration["status"] == "completed"
    assert registration["location"]["path"] == "evidence/java-type-structure-evidence.json"
    assert (out / registration["location"]["path"]).is_file()
    assert (out / "core-evidence-execution-result.json").is_file()
    assert (ARTIFACT_KIND, SCHEMA_VERSION) in {
        item.semantic_identity for item in registered_evidence_analyzers()
    }


def test_generic_runtime_rejects_unregistered_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    request = _request()
    request["evidence_requirements"][0]["artifact_kind"] = "unknown-evidence"
    material = {key: value for key, value in request.items() if key != "request_fingerprint"}
    import hashlib
    request["request_fingerprint"] = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="no Core evidence analyzer registered"):
        execute_evidence_request(repository=repo, request=request, output=tmp_path / "out")


def test_analysis_pipeline_no_longer_publishes_typed_evidence(tmp_path: Path) -> None:
    _require_tree_sitter()
    repo = _repo(tmp_path)
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "\n".join([
            "profile_id: no-legacy-typed-evidence",
            "pipeline:",
            "  stages:",
            "    - id: scan_files",
            "    - id: java_source_observation_build",
            "    - id: core_output",
            "",
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "analysis-out"
    run_analysis(repo, out, project_code="P", system_name="S", repo_id="repo", analysis_profile=profile)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert not (out / "evidence/java-type-structure-evidence.json").exists()
    assert "java_type_structure_evidence" not in (manifest.get("prepared_artifacts") or {})
    assert "java_type_structure_evidence" not in json.dumps(manifest, ensure_ascii=False)
