from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.evidence_runtime import registered_evidence_analyzers
from code_analyzer_core.prepared_artifacts.structured_file_shape_evidence import build_structured_file_shape_evidence


def test_structured_file_shape_evidence_preserves_variants_without_scalar_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    dominant = repo / "dominant.json"
    dominant.write_text(json.dumps({
        "schema": "SECRET_SCHEMA_VALUE",
        "columns": [{"name": "SECRET_COLUMN", "deleted": False}],
        "optional": None,
    }))
    minority = repo / "minority.json"
    minority.write_text(json.dumps({
        "schema": "ANOTHER_SECRET_VALUE",
        "columns": [],
        "deleted": True,
    }))
    broken = repo / "broken.json"
    broken.write_text("{not-json")

    artifact = build_structured_file_shape_evidence(
        repository=repo,
        all_files=(minority, broken, dominant),
        repo_id="repo-a",
        parameters={},
    )

    assert artifact["artifact_kind"] == "structured-file-shape-evidence"
    assert artifact["schema_version"] == "structured-file-shape-evidence/v1"
    assert artifact["coverage"]["candidate_file_count"] == 3
    assert artifact["coverage"]["parsed_file_count"] == 2
    assert artifact["coverage"]["parse_failed_file_count"] == 1
    assert artifact["coverage"]["coverage_status"] == "partial"
    members = {item["repository_relative_path"]: item for item in artifact["members"]}
    assert set(members) == {"dominant.json", "minority.json"}
    assert members["dominant.json"]["structure_signature"] != members["minority.json"]["structure_signature"]
    minority_states = {(x["path"], x["value_type"], x["state"]) for x in members["minority.json"]["state_observations"]}
    assert ("/deleted", "boolean", "true") in minority_states
    minority_cards = {(x["path"], x["length"]) for x in members["minority.json"]["cardinality_observations"]}
    assert ("/columns", 0) in minority_cards
    serialized = json.dumps(artifact, ensure_ascii=False)
    assert "SECRET_SCHEMA_VALUE" not in serialized
    assert "SECRET_COLUMN" not in serialized
    assert "ANOTHER_SECRET_VALUE" not in serialized
    assert any(d["code"] == "structured_file_parse_failed" for d in artifact["diagnostics"])


def test_structured_file_shape_evidence_is_deterministic_and_registered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    a = repo / "a.yaml"
    a.write_text("root:\n  enabled: true\n  values: [1, 2, 3]\n")
    b = repo / "b.json"
    b.write_text('{"root":{"enabled":false,"values":[1]}}')
    first = build_structured_file_shape_evidence(repository=repo, all_files=(b, a), repo_id="repo-a", parameters={})
    second = build_structured_file_shape_evidence(repository=repo, all_files=(a, b), repo_id="repo-a", parameters={})
    assert first == second
    identities = {item.semantic_identity for item in registered_evidence_analyzers()}
    assert ("structured-file-shape-evidence", "structured-file-shape-evidence/v1") in identities


def test_structured_file_shape_evidence_rejects_runtime_parameters(tmp_path: Path) -> None:
    repo = tmp_path / "repo"; repo.mkdir()
    try:
        build_structured_file_shape_evidence(repository=repo, all_files=(), repo_id="repo-a", parameters={"guess": True})
    except ValueError as exc:
        assert "does not accept runtime parameters" in str(exc)
    else:
        raise AssertionError("runtime parameters must be rejected")
