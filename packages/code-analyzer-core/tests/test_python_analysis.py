from __future__ import annotations

import json
from pathlib import Path

from code_analyzer_core.python_analysis import run_python_repository_analysis


def _write_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "pyrepo"
    repo.mkdir()
    (repo / "app.py").write_text(
        '''
from pydantic import BaseModel
from fastapi import APIRouter
import requests

router = APIRouter()

class ProfileRequest(BaseModel):
    card_numbers: list[str]
    block_code: bool | None = None

class ProfileResponse(BaseModel):
    profiles: list[dict]

@router.post("/profilesByCard")
def profile_by_card(request: ProfileRequest) -> ProfileResponse:
    payload = {"cards": request.card_numbers, "block": request.block_code}
    requests.post("https://external.example/profile", json=payload)
    db.session.add(payload)
    return ProfileResponse(profiles=[])
''',
        encoding="utf-8",
    )
    return repo


def test_python_analysis_builds_ingress_flow_storage_and_trace(tmp_path: Path):
    repo = _write_repo(tmp_path)
    ws = tmp_path / "workspace"
    result = run_python_repository_analysis(
        repo_path=repo,
        analysis_out=ws,
        repo_id="pyrepo",
        project_code="PY",
        system_name="py-system",
        run_id="test-run",
    )
    out = Path(result["analysis_out"])
    nav = json.loads((out / "compact" / "navigation.json").read_text(encoding="utf-8"))
    assert nav["repository"]["stack"]
    assert "python" in nav["repository"]["stack"]
    assert nav["counts"]["ingress"] >= 1
    assert nav["counts"]["data_flows"] >= 1
    assert nav["counts"]["storage_accesses"] >= 1
    assert nav["counts"]["field_flows"] >= 1
    assert nav["counts"]["traces"] >= 1
    assert any(i.get("schema_ref") == "ProfileRequest" for i in nav["interfaces"])
    assert any(s.get("name") == "ProfileRequest" for s in nav["schemas"])
    assert any(t.get("trace_status") == "unresolved" for t in nav["traces"])


def test_python_workspace_manifest_type(tmp_path: Path):
    repo = _write_repo(tmp_path)
    result_root = tmp_path / "repository-result"
    static_out = result_root / "static-analysis-output"
    result = run_python_repository_analysis(repo, static_out, repo_id="pyrepo", run_id="test-run")
    manifest = json.loads((result_root / "repository-analysis-manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_scope"] == "repository"
    assert manifest["repo_id"] == "pyrepo"
    assert manifest["static_analysis_output"] == "static-analysis-output"
    assert "workspace_summary" not in result


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def test_python_public_output_uses_strict_contract_no_legacy_evidence_fields(tmp_path: Path):
    repo = _write_repo(tmp_path)
    ws = tmp_path / "workspace"
    result = run_python_repository_analysis(repo, ws, repo_id="pyrepo", project_code="PY", system_name="py-system", run_id="test-run")
    out = Path(result["analysis_out"])
    nav = json.loads((out / "compact" / "navigation.json").read_text(encoding="utf-8"))
    forbidden = {"con" + "fidence", "assess" + "ment", "propagation_" + "assess" + "ment", "assess" + "ment_hint", "risk_" + "relevance", "persistent_" + "storage", "lineage_" + "assess" + "ment"}
    for obj in _walk_json(nav):
        assert not (forbidden & set(obj.keys()))
    storage = nav["storage_accesses"][0]
    signals = storage.get("candidate_signals") or []
    assert signals
    assert all(s.get("is_evidence") is False for s in signals)
    assert all(s.get("allowed_use") == "navigation_only" for s in signals)
    assert storage["evidence_maturity_dimensions"]["persistence_write"] == "unresolved"
