from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_layer_core.materialization_contracts import (
    MATERIALIZATION_CATALOG_SCHEMA_VERSION,
    MATERIALIZATION_CONTRACT_SCHEMA_VERSION,
    CURRENT_MATERIALIZATIONS,
    build_materialization_contract_catalog,
    main,
    render_materialization_contract_catalog_markdown,
)


def _canonical_fingerprint(payload: dict[str, object]) -> str:
    material = {key: deepcopy(value) for key, value in payload.items() if key != "catalog_fingerprint"}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "core_target_analysis_contracts/v1",
        "core_version": "test",
        "contracts": {
            "foundation": {"contract_id": "core_foundation_contract/v1"},
            "evidence_analyzer": {"contract_id": "core_evidence_analyzer_contract/v1"},
            "evidence_artifact": {"contract_id": "core_evidence_artifact_contract/v1"},
        },
        "purpose": "test fixture",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["contracts_fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return payload


def test_catalog_declares_only_installed_materializations() -> None:
    payload = build_materialization_contract_catalog(_source())
    assert payload["schema_version"] == MATERIALIZATION_CATALOG_SCHEMA_VERSION
    assert payload["summary"] == {
        "materialization_count": 22,
        "runtime_registered_materialization_count": 20,
        "runtime_unregistered_materialization_count": 2,
    }
    assert payload["catalog_fingerprint"] == _canonical_fingerprint(payload)
    current = {item["materialization_id"]: item for item in payload["materializations"]}
    assert set(current) == {
        "physical-model", "sql-analysis", "sql-target-source-mapping", "workspace-sql-catalog",
        "cross-artifact-data-model-mapping", "data-model-attribute-extension-context",
        "system-interactions", "interaction-coverage", "interaction-islands",
        "interaction-field-contracts", "cross-repository-value-flow", "repository-value-flow",
        "logical-physical-mapping", "logical-storage-mapping", "code-declared-data-model",
        "effective-data-model", "observed-storage-usage", "model-storage-semantics",
        "system-description", "reference-data", "persistence-lineage", "repository-inventory",
    }
    assert payload["current_state"]["runtime_unregistered_materialization_ids"] == [
        "interaction-coverage", "interaction-islands"
    ]
    assert all(item["schema_version"] == MATERIALIZATION_CONTRACT_SCHEMA_VERSION for item in current.values())
    for forbidden in (
        "planned_core_to_klc_materializations", "migration_sequence", "legacy_umbrella_decomposition",
        "current_task_id_routing", "current_state_assessment",
    ):
        assert forbidden not in payload


def test_materialization_contract_has_no_migration_metadata() -> None:
    payload = build_materialization_contract_catalog(_source())
    for item in payload["materializations"]:
        assert "migration" not in item
        assert "readiness" not in item
        contract = item["input_contract"]
        assert contract["semantic_identity"] == ["artifact_kind", "schema_version"]
        assert "task_id" in contract["forbidden_semantic_selectors"]
        for requirement in contract["required_evidence"] + contract["optional_evidence"]:
            assert requirement["semantic_selector"] == "artifact_kind_plus_schema_version"
        for requirement in contract["required_knowledge_models"] + contract["optional_knowledge_models"]:
            assert requirement["semantic_selector"] == "model_kind_plus_schema_version"


def test_system_and_reference_materializations_are_current_typed_runtime_entries() -> None:
    payload = build_materialization_contract_catalog(_source())
    current = {item["materialization_id"]: item for item in payload["materializations"]}
    assert current["system-description"]["current_implementation"]["runtime"]["registered"] is True
    assert current["reference-data"]["current_implementation"]["runtime"]["registered"] is True
    assert [item["artifact_kind"] for item in current["system-description"]["input_contract"]["required_evidence"]] == ["system-description-evidence"]
    assert [item["artifact_kind"] for item in current["reference-data"]["input_contract"]["required_evidence"]] == ["reference-data-evidence"]


def test_fingerprint_and_markdown_are_deterministic() -> None:
    first = build_materialization_contract_catalog(_source())
    second = build_materialization_contract_catalog(_source())
    assert first == second
    markdown = render_materialization_contract_catalog_markdown(first)
    assert markdown == render_materialization_contract_catalog_markdown(second)
    assert markdown.startswith("# Knowledge Materialization Contracts v3")
    assert "Historical Core→KLC migration planning is not part" in markdown
    assert "`code-declared-data-model`" in markdown
    assert "`artifact_kind + schema_version`" in markdown


def test_rejects_unsupported_or_modified_core_contracts() -> None:
    unsupported = _source()
    unsupported["schema_version"] = "core_target_analysis_contracts/v999"
    with pytest.raises(ValueError, match="unsupported Core target contracts schema"):
        build_materialization_contract_catalog(unsupported)
    modified = _source()
    modified["purpose"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        build_materialization_contract_catalog(modified)


def test_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    source = tmp_path / "core-target-contracts.json"
    source.write_text(json.dumps(_source(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "materializations.json"
    markdown = tmp_path / "materializations.md"
    assert main(["--core-target-contracts", str(source), "--output", str(output), "--markdown", str(markdown)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == MATERIALIZATION_CATALOG_SCHEMA_VERSION
    assert markdown.read_text(encoding="utf-8").startswith("# Knowledge Materialization Contracts v3")


def test_data_model_knowledge_is_decomposed_by_current_typed_contracts() -> None:
    payload = build_materialization_contract_catalog(_source())
    current = {item["materialization_id"]: item for item in payload["materializations"]}
    code_model = current["code-declared-data-model"]
    assert [item["artifact_kind"] for item in code_model["input_contract"]["required_evidence"]] == ["java-type-structure-evidence"]
    assert code_model["input_contract"]["required_knowledge_models"] == []
    mapping = current["logical-physical-mapping"]
    assert [item["artifact_kind"] for item in mapping["input_contract"]["required_evidence"]] == ["java-persistence-mapping-evidence"]
    assert {item["source_materialization_id"] for item in mapping["input_contract"]["required_knowledge_models"]} == {"code-declared-data-model", "physical-model"}
    effective = current["effective-data-model"]
    assert effective["input_contract"]["required_evidence"] == []
    assert {item["source_materialization_id"] for item in effective["input_contract"]["required_knowledge_models"]} == {"code-declared-data-model", "physical-model", "logical-physical-mapping"}


def test_repository_inventory_declares_bounded_optional_evidence_policy() -> None:
    payload = build_materialization_contract_catalog(_source())
    inventory = next(item for item in payload["materializations"] if item["materialization_id"] == "repository-inventory")
    optional = {item["artifact_kind"]: item for item in inventory["input_contract"]["optional_evidence"]}
    assert optional["data-model-candidate-evidence"]["production_policy"] == "produce_if_missing"
    assert optional["interaction-boundary-evidence"]["production_policy"] == "produce_if_missing"
    assert optional["reference-data-evidence"]["production_policy"] == "existing_only"
    assert optional["value-flow-evidence"]["production_policy"] == "existing_only"
    assert inventory["outputs"]["models"] == ["repository-inventory/v5"]
    assert "common.repository-coverage-gaps" in inventory["outputs"]["capabilities"]
    assert "common.repository-discovery" in inventory["outputs"]["capabilities"]
    assert "common.repository-structural-members" not in inventory["outputs"]["capabilities"]
    assert inventory["outputs"]["conditional_capabilities"] == ["common.repository-structural-members"]


def test_materialization_definition_rejects_guaranteed_conditional_capability_overlap() -> None:
    inventory = next(item for item in CURRENT_MATERIALIZATIONS if item.materialization_id == "repository-inventory")
    with pytest.raises(ValueError, match="both guaranteed and conditional"):
        replace(
            inventory,
            capabilities=inventory.capabilities + ("common.repository-structural-members",),
        )
