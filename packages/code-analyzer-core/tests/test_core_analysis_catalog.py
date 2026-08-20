from __future__ import annotations

import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

from code_analyzer_core.analysis_catalog import build_core_analysis_catalog
from code_analyzer_core.cli import app


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"
FRAGMENTS = ROOT / "analysis-profile-fragments"


def _profile(catalog: dict, profile_id: str) -> dict:
    return next(item for item in catalog["profiles"] if item["profile_id"] == profile_id)


def test_core_analysis_catalog_describes_all_builtin_profiles_and_stages() -> None:
    catalog = build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)

    assert catalog["schema_version"] == "core_analysis_catalog/v1"
    assert catalog["execution_effect"] == "none"
    assert catalog["summary"]["profile_count"] == 7
    assert catalog["summary"]["fragment_count"] == 1
    assert catalog["summary"]["stage_definition_count"] == 28
    assert catalog["summary"]["java_derived_contract_count"] == 9
    assert catalog["summary"]["execution_model_counts"] == {
        "generic_evidence_runtime": 1,
        "java_stage_controlled_pipeline": 5,
        "spec_fixed_pipeline": 1,
    }

    declared = {
        stage_id
        for profile in catalog["profiles"]
        for stage_id in profile["resolved_stage_ids"]
    }
    described = {item["stage_id"] for item in catalog["stage_catalog"]["stages"]}
    assert declared <= described
    assert catalog["stage_catalog"]["summary"]["unclassified_stage_ids"] == []


def test_catalog_distinguishes_runtime_controlled_and_declarative_profiles() -> None:
    catalog = build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)

    profile_ids = {item["profile_id"] for item in catalog["profiles"]}
    assert "repository-system-description" not in profile_ids
    assert "repository-reference-data" not in profile_ids

    java_profile = _profile(catalog, "repository-portfolio-topology")
    assert java_profile["execution_plan"]["execution_model"]["engine"] == "java_stage_controlled_pipeline"
    assert java_profile["execution_plan"]["declarative_only_stage_ids"] == []
    assert "java_system_interaction_enrichment" in java_profile["execution_plan"]["runtime_stage_ids"]

    stage_index = {item["stage_id"]: item for item in catalog["stage_catalog"]["stages"]}
    for stage_id in ("system_description_enrichment", "reference_data_fact_base"):
        stage = stage_index[stage_id]
        assert stage["category"] == "derived_evidence"
        assert stage["recommended_boundary"] == "core_typed_evidence_preparation"
        assert {item["profile_id"] for item in stage["profile_occurrences"]} == {
            "internal-reference-data-evidence-v1"
        }

    sql_profile = _profile(catalog, "git-change-sql-spark-complexity-assessment")
    assert sql_profile["execution_plan"]["execution_model"]["engine"] == "generic_evidence_runtime"
    assert sql_profile["execution_plan"]["runtime_stage_ids"] == []
    assert sql_profile["execution_plan"]["declarative_only_stage_ids"] == []
    assert sql_profile["resolved_stage_ids"] == []
    assert sql_profile["declared_profile"]["evidence_requirements"][0] == {
        "artifact_kind": "sql-analysis",
        "schema_version": "sql-analysis/v1",
        "parameters": {"project_code": "inherited", "system_name": "inherited"},
    }

    spec_profile = _profile(catalog, "spec-evidence-workspace")
    assert spec_profile["execution_plan"]["execution_model"]["engine"] == "spec_fixed_pipeline"
    assert spec_profile["execution_plan"]["declarative_only_stage_ids"] == spec_profile["resolved_stage_ids"]


def test_catalog_makes_foundation_ownership_and_non_base_content_visible() -> None:
    catalog = build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)

    assert catalog["known_boundaries"]["foundation_owner"] == "code_analyzer_core"
    foundation = catalog["foundation_fragments"][0]
    assert foundation["fragment_id"] == "repository-analysis-foundation"
    assert "java_system_interaction_enrichment" not in foundation["resolved_stage_ids"]
    assert foundation["architecture_diagnostics"] == []


def test_catalog_fingerprint_is_independent_of_checkout_location(tmp_path: Path) -> None:
    first = build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)

    copied_root = tmp_path / "copy"
    shutil.copytree(PROFILES, copied_root / "analysis-profiles")
    shutil.copytree(FRAGMENTS, copied_root / "analysis-profile-fragments")
    second = build_core_analysis_catalog(
        profiles_root=copied_root / "analysis-profiles",
        fragments_root=copied_root / "analysis-profile-fragments",
    )

    assert first["catalog_fingerprint"] == second["catalog_fingerprint"]


def test_analysis_catalog_cli_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "catalog.json"
    result = CliRunner().invoke(
        app,
        [
            "analysis-catalog",
            "--profiles-root",
            str(PROFILES),
            "--fragments-root",
            str(FRAGMENTS),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert payload["schema_version"] == "core_analysis_catalog/v1"
    assert summary["profile_count"] == 7
    assert summary["catalog_fingerprint"] == payload["catalog_fingerprint"]
