from pathlib import Path

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"
FRAGMENTS = ROOT / "analysis-profile-fragments"
REMAINING_PROFILE_WORKFLOWS = (
    "repository-system-data-model.yaml",
    "repository-portfolio-topology.yaml",
)

def test_retired_routing_profiles_are_removed_from_core():
    for name in (
        "system-evidence.yaml", "system-evidence-deep.yaml", "system-evidence-lineage.yaml",
        "repository-flow-lineage.yaml", "repository-persistence-lineage.yaml",
    ):
        assert not (PROFILES / name).exists()

def test_remaining_profile_workflows_are_explicit_and_deterministic():
    assert (FRAGMENTS / "repository-analysis-foundation.yaml").is_file()
    for name in REMAINING_PROFILE_WORKFLOWS:
        profile = load_analysis_profile(PROFILES / name)
        stages = profile_stage_ids(profile)
        assert stages
        assert stages.index("maven_dependency_scan") < stages.index("java_structural_scan")
    system_model = load_analysis_profile(PROFILES / "repository-system-data-model.yaml")
    assert system_model["_profile_inheritance"] == ["repository-analysis-foundation"]
