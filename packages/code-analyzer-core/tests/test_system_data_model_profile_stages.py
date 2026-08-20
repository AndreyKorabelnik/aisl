from pathlib import Path

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"


def test_repository_analysis_surface_contains_executable_task_profiles():
    names = sorted(path.name for path in PROFILES.glob("repository-*.yaml") if path.name != "repository-data-model-static.yaml")
    assert names == [
        "repository-portfolio-topology.yaml",
        "repository-system-data-model.yaml",
    ]
    for name in names:
        profile = load_analysis_profile(PROFILES / name)
        assert profile["profile_id"] == name.removesuffix(".yaml")
        assert profile_stage_ids(profile)

