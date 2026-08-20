from pathlib import Path

from code_analyzer_core.analysis_profiles import load_analysis_profile, profile_stage_ids


def test_portfolio_topology_profile_is_minimal_and_boundary_complete() -> None:
    profile = load_analysis_profile(
        Path(__file__).resolve().parents[1]
        / "analysis-profiles"
        / "repository-portfolio-topology.yaml"
    )
    stages = profile_stage_ids(profile)
    assert stages == [
        "scan_files",
        "config_scan",
        "maven_dependency_scan",
        "gradle_dependency_scan",
        "openapi_scan",
        "java_structural_scan",
        "java_system_interaction_enrichment",
        "core_output",
        "normalize_facts",
        "compact_package",
    ]
    for excluded in (
        "java_source_observation_build",
        "sql_scan",
        "db_schema_scan",
        "java_data_flow_build",
        "java_field_flow_build",
        "java_traceability_build",
        "java_persistence_lineage_build",
    ):
        assert excluded not in stages
    assert profile["output_contract"]["policy"]["system_interface_catalog_available"] is True
