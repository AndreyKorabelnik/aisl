from pathlib import Path

import pytest

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_entries, profile_stage_ids


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"
FRAGMENTS = ROOT / "analysis-profile-fragments"


def _load(name: str):
    return load_analysis_profile(PROFILES / name)


def test_foundation_fragment_resolves_for_children_but_is_not_an_executable_profile():
    with pytest.raises(ValueError, match="must contain profile_id"):
        load_analysis_profile(FRAGMENTS / "repository-analysis-foundation.yaml")
    model = _load("repository-system-data-model.yaml")
    assert model["_profile_inheritance"] == ["repository-analysis-foundation"]
    assert model["_profile_sources"][-1].endswith("repository-system-data-model.yaml")


def test_data_model_profile_uses_foundation_and_excludes_expensive_task_extensions():
    profile = _load("repository-system-data-model.yaml")
    stages = profile_stage_ids(profile)
    assert stages[:5] == ["scan_files", "config_scan", "maven_dependency_scan", "gradle_dependency_scan", "openapi_scan"]
    assert stages[-3:] == ["core_output", "normalize_facts", "compact_package"]
    assert "java_persistence_lineage_build" in stages
    assert "java_data_model_lineage_build" in stages
    assert "code_conceptual_model_build" not in stages
    assert stages.index("java_data_model_lineage_build") < stages.index("core_output")
    assert "java_field_flow_build" not in stages
    assert "java_traceability_build" not in stages
    assert "declared_value_scan" not in stages
    opts = {item["id"]: item.get("options", {}) for item in profile_stage_entries(profile) if isinstance(item, dict)}
    assert opts["java_persistence_lineage_build"]["deep"] is True
    assert profile["analysis_parameters"]["persistence_depth"] == "deep"
    assert "data-model.persistence-deep" not in profile["capabilities"]




def test_child_can_override_inherited_stage_options_without_duplication(tmp_path: Path):
    (tmp_path / "base.yaml").write_text(
        "fragment_id: base\npipeline:\n  stages:\n    - id: scan_files\n    - id: x\n      options: {deep: false, max_depth: 4}\n",
        encoding="utf-8",
    )
    (tmp_path / "child.yaml").write_text(
        "profile_id: child\nextends: base\npipeline:\n  stages:\n    - id: x\n      options: {deep: true}\n    - id: core_output\n",
        encoding="utf-8",
    )
    profile = load_analysis_profile(tmp_path / "child.yaml")
    assert profile_stage_ids(profile) == ["scan_files", "x", "core_output"]
    stage = next(item for item in profile_stage_entries(profile) if isinstance(item, dict) and item["id"] == "x")
    assert stage["options"] == {"deep": True, "max_depth": 4}


def test_profile_inheritance_cycle_is_rejected(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("profile_id: a\nextends: b\npipeline: {stages: [scan_files]}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("profile_id: b\nextends: a\npipeline: {stages: [scan_files]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inheritance cycle"):
        load_analysis_profile(tmp_path / "a.yaml")
