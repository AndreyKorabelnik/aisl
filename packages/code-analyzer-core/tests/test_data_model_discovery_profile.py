from pathlib import Path

from code_analyzer_core.evidence_runtime import registered_evidence_analyzers
from code_analyzer_core.prepared_artifacts.data_model_candidate_evidence import _profile


def test_data_model_candidate_analyzer_owns_lightweight_internal_pipeline() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "analysis-profiles" / "repository-data-model-discovery.yaml").exists()
    registrations = {item.analyzer_id: item for item in registered_evidence_analyzers()}
    registration = registrations["data-model-candidate-analyzer"]
    assert registration.artifact_kind == "data-model-candidate-evidence"
    assert registration.schema_version == "data-model-candidate-evidence/v1"
    stages = [
        str(item.get("id")) if isinstance(item, dict) else str(item)
        for item in [*_profile()["pipeline"]["stages"], *_profile()["pipeline"]["final_stages"]]
    ]
    assert stages == [
        "scan_files",
        "maven_dependency_scan",
        "gradle_dependency_scan",
        "java_structural_scan",
        "java_data_model_candidate_scan",
        "core_output",
        "normalize_facts",
        "compact_package",
    ]
    for excluded in (
        "java_system_interaction_enrichment",
        "java_source_observation_build",
        "db_schema_scan",
        "java_data_flow_build",
        "java_field_flow_build",
        "java_traceability_build",
        "java_persistence_lineage_build",
        "java_data_model_lineage_build",
    ):
        assert excluded not in stages
    policy = _profile()["output_contract"]["policy"]
    assert "task_suite_profile_semantics" not in policy
    assert "legacy_fallback" not in policy
    assert policy["full_data_model_analysis_not_requested"] is True
