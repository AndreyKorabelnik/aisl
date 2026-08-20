from pathlib import Path

import pytest

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "analysis-profiles"
FRAGMENT_DIR = ROOT / "analysis-profile-fragments"

def test_analysis_profiles_are_external_runtime_config_only():
    profile_dir = PROFILE_DIR
    fragment_dir = FRAGMENT_DIR
    assert profile_dir.is_dir()
    assert fragment_dir.is_dir()
    assert not (ROOT / "code_analyzer_core/profiles").exists()

    expected_tasks = {
        "repository-system-data-model.yaml",
        "repository-portfolio-topology.yaml",
    }
    present = {p.name for p in profile_dir.glob("repository-*.yaml") if p.name != "repository-data-model-static.yaml"}
    assert present == expected_tasks
    assert (fragment_dir / "repository-analysis-foundation.yaml").is_file()


def test_load_analysis_profile_requires_explicit_executable_yaml_path():
    with pytest.raises(ValueError, match="analysis profile path is required"):
        load_analysis_profile(None)
    with pytest.raises(ValueError, match="analysis profile file not found"):
        load_analysis_profile("missing-profile")
    with pytest.raises(ValueError, match="must contain profile_id"):
        load_analysis_profile(FRAGMENT_DIR / "repository-analysis-foundation.yaml")

    profile_path = PROFILE_DIR / "repository-system-data-model.yaml"
    profile = load_analysis_profile(profile_path)
    assert profile["profile_id"] == "repository-system-data-model"
    assert profile["_profile_source"].endswith("analysis-profiles/repository-system-data-model.yaml")
    assert profile_stage_ids(profile)
