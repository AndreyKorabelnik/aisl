from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_analyzer_core.analysis_catalog import build_core_analysis_catalog
from code_analyzer_core.cli import app
from code_analyzer_core.evidence_contracts import build_core_evidence_contract_catalog
from code_analyzer_core.target_contracts import build_core_target_analysis_contracts


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "analysis-profiles"
FRAGMENTS = ROOT / "analysis-profile-fragments"


def _inputs() -> tuple[dict, dict]:
    catalog = build_core_analysis_catalog(profiles_root=PROFILES, fragments_root=FRAGMENTS)
    return catalog, build_core_target_analysis_contracts(catalog)


def _contract(payload: dict, artifact_kind: str) -> dict:
    return next(item for item in payload["contracts"] if item["artifact_kind"] == artifact_kind)


def _java_contract(payload: dict) -> dict:
    return _contract(payload, "java-type-structure-evidence")


def test_generic_catalog_defines_first_typed_evidence_contract() -> None:
    catalog, target = _inputs()
    payload = build_core_evidence_contract_catalog(catalog, target)

    assert payload["schema_version"] == "core_evidence_contract_catalog/v1"
    assert payload["execution_effect"] == "none"
    assert payload["summary"] == {
        "contract_count": 13,
        "defined_not_published_count": 0,
        "runtime_published_count": 13,
        "planning_execution_class_counts": {
            "always_on": 1,
            "bounded_preflight": 3,
            "full_analysis": 9,
        },
        "generic_preflight_contract_count": 2,
    }
    contract = _java_contract(payload)
    assert contract["schema_version"] == "java-type-structure-evidence/v1"
    assert contract["artifact_envelope_contract"] == "core_evidence_artifact_contract/v1"
    assert contract["publication_policy"]["record_limit"] is None
    assert contract["current_state_assessment"]["source_observations_available"] is True
    assert contract["current_state_assessment"]["typed_runtime_artifact_published"] is True
    assessment = contract["current_state_assessment"]
    assert assessment["runtime_contract_id"] == "core_evidence_runtime/v1"
    assert assessment["runtime_registration_present"] is True
    assert assessment["runtime_registration_valid"] is True
    assert assessment["runtime_status"] == "registered_in_generic_core_evidence_runtime"




def test_preflight_planning_metadata_is_core_owned_and_safe() -> None:
    payload = build_core_evidence_contract_catalog(*_inputs())
    by_kind = {item["artifact_kind"]: item for item in payload["contracts"]}

    repository = by_kind["repository-structure-evidence"]["preflight_planning"]
    assert repository["execution_class"] == "always_on"
    assert repository["preflight_phase"] == "p0"
    assert repository["discovery_role"] == "generic_structural"

    structured = by_kind["structured-file-shape-evidence"]["preflight_planning"]
    assert structured["execution_class"] == "bounded_preflight"
    assert structured["preflight_phase"] == "p1"
    assert structured["discovery_role"] == "generic_structural"
    assert structured["applicability"]["required_extensions_any_of"] == [".json", ".yaml", ".yml"]
    assert structured["budget"]["hard_bounds_declared"] is True

    candidate = by_kind["data-model-candidate-evidence"]["preflight_planning"]
    assert candidate["execution_class"] == "bounded_preflight"
    assert candidate["discovery_role"] == "specialized_candidate"
    assert candidate["applicability"]["status"] == "not_formalized"
    assert candidate["applicability"]["required_languages_any_of"] == []
    assert candidate["applicability"]["required_extensions_any_of"] == []
    assert any("mixed Java" in gap for gap in by_kind["data-model-candidate-evidence"]["current_state_gaps"])

    for contract in payload["contracts"]:
        safety = contract["preflight_planning"]["selection_safety"]
        assert safety["concept_inference_may_hard_skip"] is False
        assert safety["hard_skip_requires_observed_non_applicability"] is True
        assert safety["explicit_request_behavior"] == "execute_or_report_observed_blocking_precondition"


def test_invalid_preflight_planning_metadata_is_rejected(monkeypatch) -> None:
    import code_analyzer_core.evidence_contracts as module

    definitions = module._load_definitions()
    broken = deepcopy(definitions)
    broken["contracts"][0]["preflight_planning"]["selection_safety"]["concept_inference_may_hard_skip"] = True
    monkeypatch.setattr(module, "_load_definitions", lambda: broken)

    with pytest.raises(ValueError, match="must not allow concept inference to hard-skip"):
        module.build_core_evidence_contract_catalog(*_inputs())


def test_java_contract_contains_complete_raw_declaration_sections() -> None:
    contract = _java_contract(build_core_evidence_contract_catalog(*_inputs()))
    sections = {item["section"]: item for item in contract["payload"]["sections"]}
    assert set(sections) == {
        "source_units",
        "type_declarations",
        "field_declarations",
        "inheritance_declarations",
        "annotation_declarations",
        "type_reference_observations",
        "enum_constant_declarations",
    }
    assert "is_static" in sections["field_declarations"]["required_fields"]
    assert "parse_status" in sections["source_units"]["required_fields"]
    assert sections["inheritance_declarations"]["allowed_relation_kinds"] == ["extends", "implements"]
    assert sections["annotation_declarations"]["allowed_target_kinds"] == ["type", "field"]


def test_java_contract_does_not_freeze_other_knowledge_semantics() -> None:
    contract = _java_contract(build_core_evidence_contract_catalog(*_inputs()))
    forbidden = "\n".join(contract["forbidden_semantics"])
    for phrase in (
        "JPA entity",
        "logical-to-physical mapping",
        "SQL or storage usage",
        "effective inherited fields",
        "effective associations",
        "confidence score",
    ):
        assert phrase in forbidden
    payload_sections = {item["section"] for item in contract["payload"]["sections"]}
    assert "effective_entity_fields" not in payload_sections
    assert "effective_entity_associations" not in payload_sections



def test_persistence_mapping_contract_is_runtime_published_and_separate_from_matching() -> None:
    contract = _contract(build_core_evidence_contract_catalog(*_inputs()), "java-persistence-mapping-evidence")
    assert contract["schema_version"] == "java-persistence-mapping-evidence/v1"
    assert contract["current_state_assessment"]["typed_runtime_artifact_published"] is True
    assert contract["producer"]["target_analyzer_id"] == "java-persistence-mapping-analyzer"
    sections = {item["section"] for item in contract["payload"]["sections"]}
    assert sections == {
        "persistence_type_mappings",
        "persistence_field_mappings",
        "persistence_key_mappings",
        "persistence_relationship_mappings",
        "persistence_inheritance_mappings",
        "mapping_gaps",
    }
    forbidden = "\n".join(contract["forbidden_semantics"])
    assert "matching logical objects to physical tables or columns" in forbidden
    assert "JPA default table or column naming inference" in forbidden

def test_contract_is_deterministic() -> None:
    first = build_core_evidence_contract_catalog(*_inputs())
    second = build_core_evidence_contract_catalog(*_inputs())
    assert first == second
    assert first["catalog_fingerprint"] == second["catalog_fingerprint"]


def test_modified_input_contracts_are_rejected() -> None:
    catalog, target = _inputs()
    modified_catalog = deepcopy(catalog)
    modified_catalog["summary"]["profile_count"] = 999
    with pytest.raises(ValueError, match="fingerprint"):
        build_core_evidence_contract_catalog(modified_catalog, target)

    modified_target = deepcopy(target)
    modified_target["summary"]["foundation_violation_count"] = 999
    with pytest.raises(ValueError, match="fingerprint"):
        build_core_evidence_contract_catalog(catalog, modified_target)


def test_cli_exports_generic_catalog_and_markdown(tmp_path: Path) -> None:
    catalog, target = _inputs()
    catalog_path = tmp_path / "core-catalog.json"
    target_path = tmp_path / "target-contracts.json"
    output = tmp_path / "evidence-contracts.json"
    markdown = tmp_path / "evidence-contracts.md"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    target_path.write_text(json.dumps(target), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "evidence-contracts",
            "--core-catalog",
            str(catalog_path),
            "--core-target-contracts",
            str(target_path),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(result.stdout)
    assert summary["contract_count"] == 13
    assert summary["runtime_published_count"] == 13
    assert payload["catalog_fingerprint"] == summary["catalog_fingerprint"]
    assert "java-type-structure-evidence/v1" in markdown.read_text(encoding="utf-8")


def test_cli_has_one_generic_command_not_one_command_per_evidence_kind() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "evidence-contracts" in result.stdout
    assert "java-type-structure-evidence" not in result.stdout
