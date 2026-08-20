from __future__ import annotations

import hashlib
from pathlib import Path

from code_analyzer_core.evidence_runtime import execute_evidence_request
from code_analyzer_core.scanners.repo_scanner import scan_all_files, scan_files


def _request(repo_id: str) -> dict[str, object]:
    request: dict[str, object] = {
        "schema_version": "core_evidence_execution_request/v1",
        "source": {"source_kind": "repository", "source_id": repo_id},
        "evidence_requirements": [{
            "artifact_kind": "repository-structure-evidence",
            "schema_version": "repository-structure-evidence/v1",
            "parameters": {},
        }],
    }
    import json
    material = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    request["request_fingerprint"] = hashlib.sha256(material).hexdigest()
    return request


def test_universal_inventory_does_not_broaden_analyzer_files(tmp_path: Path) -> None:
    (tmp_path / "Main.java").write_text("class Main {}", encoding="utf-8")
    (tmp_path / "mystery.xyz").write_text("opaque", encoding="utf-8")
    (tmp_path / "README").write_text("notes", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "ignored.xyz").write_text("ignored", encoding="utf-8")

    assert [p.name for p in scan_all_files(tmp_path)] == ["Main.java", "README", "mystery.xyz"]
    assert [p.name for p in scan_files(tmp_path)] == ["Main.java"]


def test_repository_structure_evidence_exposes_unknown_frontier(tmp_path: Path) -> None:
    (tmp_path / "Main.java").write_text("class Main {}", encoding="utf-8")
    (tmp_path / "mystery.xyz").write_text("opaque", encoding="utf-8")
    out = tmp_path / "out"
    result = execute_evidence_request(
        repository=tmp_path,
        request=_request("repo-a"),
        output=out,
        repo_id="repo-a",
    )
    artifact = result["evidence_artifacts"][0]
    assert artifact["artifact_kind"] == "repository-structure-evidence"
    assert artifact["schema_version"] == "repository-structure-evidence/v1"
    payload = __import__("json").loads((out / "evidence" / "repository-structure-evidence.json").read_text())
    assert payload["coverage"]["all_file_count"] == 2
    assert payload["coverage"]["analyzer_eligible_file_count"] == 1
    assert payload["coverage"]["outside_analyzer_frontier_file_count"] == 1
    assert {item["repository_relative_path"] for item in payload["files"]} == {"Main.java", "mystery.xyz"}
    unknown = next(item for item in payload["files"] if item["repository_relative_path"] == "mystery.xyz")
    assert unknown["analyzer_frontier_status"] == "outside_frontier"
    assert unknown["sha256"]
    assert payload["outside_analyzer_frontier_extension_families"] == [{"extension": ".xyz", "file_count": 1, "status": "outside_analyzer_frontier"}]
