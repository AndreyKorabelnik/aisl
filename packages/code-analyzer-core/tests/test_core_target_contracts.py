from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from typer.testing import CliRunner

from code_analyzer_core.analysis_catalog import build_core_analysis_catalog
from code_analyzer_core.cli import app
from code_analyzer_core.target_contracts import build_core_target_analysis_contracts


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"
FRAGMENTS = ROOT / "analysis-profile-fragments"


def _catalog() -> dict:
    return build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)


def test_target_contracts_define_core_owned_boundaries() -> None:
    payload = build_core_target_analysis_contracts(_catalog())

    assert payload["schema_version"] == "core_target_analysis_contracts/v1"
    assert payload["execution_effect"] == "none"
    assert payload["contracts"]["foundation"]["contract_id"] == "core_foundation_contract/v1"
    assert payload["contracts"]["evidence_analyzer"]["contract_id"] == "core_evidence_analyzer_contract/v1"
    runtime = payload["contracts"]["evidence_runtime"]
    assert runtime["contract_id"] == "core_evidence_runtime/v1"
    assert runtime["semantic_identity"] == ["artifact_kind", "schema_version"]
    assert "implicit publication from the monolithic analyze-java pipeline" in runtime["forbidden_behaviors"]
    evidence = payload["contracts"]["evidence_artifact"]
    assert evidence["contract_id"] == "core_evidence_artifact_contract/v1"
    assert evidence["semantic_identity"] == ["artifact_kind", "schema_version"]
    assert "task_id" in evidence["forbidden_semantic_selectors"]
    runtime_assessment = payload["current_state_assessment"]["evidence_runtime"]
    assert runtime_assessment["registered_analyzer_count"] == 13
    assert {
        item["artifact_kind"]
        for item in runtime_assessment["registered_analyzers"]
    } == {
        "java-persistence-mapping-evidence",
        "java-type-structure-evidence",
        "sql-analysis",
        "storage-usage-evidence",
        "model-storage-evidence",
        "system-description-evidence",
        "reference-data-evidence",
        "repository-structure-evidence",
        "structured-file-shape-evidence",
        "data-model-candidate-evidence",
        "interaction-boundary-evidence",
        "value-flow-evidence",
        "persistence-lineage-evidence",
    }
    assert runtime_assessment["implicit_monolithic_publication"] is False
    assert "legacy_fallback" not in runtime_assessment
    assert "dual_write" not in runtime_assessment
    assert payload["current_state_assessment"]["evidence_artifacts"]["current_status"] == (
        "canonical_envelope_enforced_for_registered_runtime_artifacts"
    )
    assert "next_required_contracts" not in payload


def test_foundation_contains_only_base_source_indexes() -> None:
    payload = build_core_target_analysis_contracts(_catalog())
    assessment = payload["current_state_assessment"]["foundation"]

    assert assessment["current_stage_ids"] == [
        "scan_files",
        "config_scan",
        "maven_dependency_scan",
        "gradle_dependency_scan",
        "openapi_scan",
        "java_structural_scan",
        "java_source_observation_build",
        "sql_scan",
        "db_schema_scan",
    ]
    assert assessment["current_stage_ids"] == assessment["target_stage_ids_under_current_classification"]
    assert assessment["violations"] == []


def test_target_contracts_distinguish_internal_stage_coupling_from_public_boundaries() -> None:
    payload = build_core_target_analysis_contracts(_catalog())
    assessment = payload["current_state_assessment"]["evidence_analyzers"]

    dependency_ids = {item["stage_id"] for item in assessment["observed_internal_stage_dependency_findings"]}
    shared_ids = {item["stage_id"] for item in assessment["observed_internal_pipeline_state_findings"]}
    materialization_ids = {item["stage_id"] for item in assessment["knowledge_materializations_inside_core"]}

    assert dependency_ids == {
        "declared_value_summary_scan",
        "java_data_model_lineage_build",
        "java_field_flow_build",
        "java_system_interaction_enrichment",
        "java_table_observation_build",
        "java_traceability_build",
    }
    assert shared_ids == {
        "java_field_flow_build",
        "java_system_interaction_enrichment",
        "java_table_observation_build",
    }
    assert materialization_ids == set()
    assert assessment["compliant"] is True
    assert assessment["boundary_assessment"]["internal_stage_dependencies_are_allowed"] is True
    assert payload["summary"]["foundation_violation_count"] == 0
    assert payload["summary"]["observed_internal_stage_dependency_count"] == 6
    assert payload["summary"]["observed_internal_pipeline_state_read_count"] == 3
    assert payload["summary"]["knowledge_materialization_inside_core_count"] == 0


def test_target_contracts_fingerprint_is_deterministic() -> None:
    first = build_core_target_analysis_contracts(_catalog())
    second = build_core_target_analysis_contracts(_catalog())
    assert first == second
    assert first["contracts_fingerprint"] == second["contracts_fingerprint"]


def test_target_contracts_reject_modified_core_catalog() -> None:
    catalog = deepcopy(_catalog())
    catalog["summary"]["profile_count"] = 999

    try:
        build_core_target_analysis_contracts(catalog)
    except ValueError as exc:
        assert "fingerprint" in str(exc)
    else:
        raise AssertionError("modified catalog was accepted")


def test_target_contracts_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    source = tmp_path / "core-catalog.json"
    output = tmp_path / "target-contracts.json"
    markdown = tmp_path / "target-contracts.md"
    source.write_text(json.dumps(_catalog(), ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "target-contracts",
            "--core-catalog",
            str(source),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert payload["schema_version"] == "core_target_analysis_contracts/v1"
    assert summary["foundation_violation_count"] == 0
    assert summary["knowledge_materialization_inside_core_count"] == 0
    text = markdown.read_text(encoding="utf-8")
    assert "artifact_kind + schema_version" in text
    assert "java_system_interaction_enrichment" in text
