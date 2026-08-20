from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analyzer_core.analysis_profiles import load_analysis_fragment, load_analysis_profile
from code_analyzer_core.foundation_artifact import (
    FOUNDATION_SCHEMA_VERSION,
    foundation_stage_signature,
    load_foundation_artifact,
    repository_state_fingerprint,
    write_foundation_artifact,
)
from code_analyzer_core.models import AnalysisResult, Fact


ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / "analysis-profile-fragments" / "repository-analysis-foundation.yaml"
PROFILE = ROOT / "analysis-profiles" / "repository-system-data-model.yaml"


def test_internal_foundation_fragment_has_same_signature_as_task_profile():
    fragment = load_analysis_fragment(FRAGMENT)
    profile = load_analysis_profile(PROFILE)
    assert foundation_stage_signature(fragment)["sha256"] == foundation_stage_signature(profile)["sha256"]


def test_foundation_round_trip_and_repository_validation(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    java = repo / "A.java"
    java.write_text("class A {}", encoding="utf-8")
    output = tmp_path / "foundation"
    (output / "facts" / "full_by_type").mkdir(parents=True)
    (output / "facts" / "full_by_type" / "code_annotation.jsonl").write_text("{}\n", encoding="utf-8")
    (output / "facts" / "full_fact_manifest.json").write_text("{}", encoding="utf-8")
    profile = load_analysis_fragment(FRAGMENT)
    result = AnalysisResult(
        system_name="system",
        project_code="P",
        repo_path=str(repo),
        stack=["java"],
        files_analyzed=1,
        facts=[Fact(fact_type="x", name="n")],
    )
    manifest = write_foundation_artifact(
        artifact_root=output,
        repository=repo,
        files=[java],
        profile=profile,
        result=result,
        db_schema={"tables": []},
        table_observations={"relationships": [], "keys": [], "overview": {}},
        statuses={"source_observation_fact_store_status": {"status": "success"}},
        optional_sections={"declared_values": {"facts": [], "status": {"requested": True}}},
        source_output_root=output,
        repo_id="repo",
        project_code="P",
        system_name="system",
    )
    assert manifest["schema_version"] == FOUNDATION_SCHEMA_VERSION
    task_output = tmp_path / "task"
    restored, db_schema, observations, statuses, deferred_sections, optional_sections, reuse = load_foundation_artifact(
        artifact_root=output,
        repository=repo,
        files=[java],
        profile=load_analysis_profile(PROFILE),
        output_root=task_output,
        repo_id="repo",
        project_code="P",
        system_name="system",
    )
    assert restored.facts == []
    from code_analyzer_core.foundation_artifact import hydrate_foundation_result, load_foundation_optional_sections
    hydrate_foundation_result(restored, deferred_sections)
    assert restored.facts[0].fact_type == "x"
    assert db_schema == {"tables": []}
    assert observations["relationships"] == []
    assert statuses["source_observation_fact_store_status"]["manifest_path"].endswith("full_fact_manifest.json")
    assert load_foundation_optional_sections(optional_sections)["declared_values"]["facts"] == []
    assert reuse["status"] == "reused"
    assert (task_output / "facts" / "full_by_type" / "code_annotation.jsonl").is_file()

    java.write_text("class A { int x; }", encoding="utf-8")
    with pytest.raises(ValueError, match="repository state"):
        load_foundation_artifact(
            artifact_root=output,
            repository=repo,
            files=[java],
            profile=load_analysis_profile(PROFILE),
            output_root=tmp_path / "other",
            repo_id="repo",
            project_code="P",
            system_name="system",
        )


def test_repository_state_fingerprint_is_order_independent(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    first = repo / "a.txt"
    second = repo / "b.txt"
    first.write_text("a")
    second.write_text("b")
    assert repository_state_fingerprint(repo, [first, second]) == repository_state_fingerprint(repo, [second, first])


