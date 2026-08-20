from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from static_analysis_runner.cli import app
import static_analysis_runner.knowledge_planning as kp

runner = CliRunner()


def _fingerprint(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _evidence(kind: str, *, status: str = "proposed", production_policy: str = "produce_if_missing") -> dict:
    version = {
        "physical-model": "physical-model/v1",
        "sql-analysis": "sql-analysis/v1",
        "analysis-execution-result": "analysis_execution_result_contract/v1",
        "core-foundation": "core_foundation_contract/v1",
        "repository-interaction-evidence": "workspace_system_interaction/v6",
        "interaction-coverage": "repository_interaction_coverage/v1",
        "repository-value-flow": "repository_value_flow/v6",
        "persistence-lineage-evidence": "persistence-lineage-evidence/v1",
    }.get(kind, f"{kind}/v1")
    return {
        "artifact_kind": kind,
        "schema_versions": [version],
        "contract_status": status,
        "purpose": f"Purpose for {kind}",
        "production_policy": production_policy,
        "semantic_selector": "artifact_kind_plus_schema_version",
    }


def _model(kind: str, version: str, source: str) -> dict:
    return {
        "model_kind": kind,
        "schema_versions": [version],
        "source_materialization_id": source,
        "purpose": f"Purpose for {kind}",
        "semantic_selector": "model_kind_plus_schema_version",
    }


def _materialization(mid: str) -> dict:
    required_by_mid = {
        "physical-model": ["physical-model"],
        "sql-analysis": ["sql-analysis"],
        "suite-evidence-registry": ["analysis-execution-result"],
        "system-interactions": ["interaction-boundary-evidence"],
        "interaction-coverage": ["interaction-boundary-evidence"],
        "interaction-islands": ["repository-interaction-evidence"],
        "interaction-field-contracts": [],
        "cross-repository-value-flow": [],
        "repository-value-flow": ["value-flow-evidence"],
        "persistence-lineage": ["persistence-lineage-evidence"],
        "portfolio-topology": ["repository-interface-catalog-evidence"],
        "code-declared-data-model": ["java-type-structure-evidence"],
        "logical-physical-mapping": ["java-persistence-mapping-evidence"],
        "observed-storage-usage": ["storage-usage-evidence"],
        "effective-data-model": [],
        "system-description": ["system-description-evidence"],
        "reference-data": ["reference-data-evidence"],
        "workspace-sql-catalog": [],
        "model-storage-semantics": ["model-storage-evidence"],
        "logical-storage-mapping": [],
        "sql-target-source-mapping": [],
        "cross-artifact-data-model-mapping": [],
        "data-model-attribute-extension-context": [],
        "repository-inventory": ["repository-structure-evidence"],
    }
    optional_by_mid = {
        "sql-analysis": ["physical-model"],
        "suite-evidence-registry": ["core-foundation"],
        "system-interactions": ["configuration-evidence", "execution-context-evidence"],
        "interaction-islands": ["interaction-coverage"],
        "repository-value-flow": ["persistence-lineage-evidence", "interaction-boundary-evidence"],
        "persistence-lineage": [],
        "portfolio-topology": ["repository-metadata"],
        "code-declared-data-model": ["model-evidence-gap"],
        "logical-physical-mapping": ["storage-usage-evidence", "model-evidence-gap"],
        "observed-storage-usage": ["model-evidence-gap"],
        "system-description": [],
        "reference-data": [],
        "workspace-sql-catalog": [],
        "model-storage-semantics": [],
        "logical-storage-mapping": [],
        "sql-target-source-mapping": [],
        "cross-artifact-data-model-mapping": [],
        "data-model-attribute-extension-context": [],
        "repository-inventory": [
            "data-model-candidate-evidence", "interaction-boundary-evidence",
            "java-persistence-mapping-evidence", "java-type-structure-evidence",
            "persistence-lineage-evidence", "reference-data-evidence", "sql-analysis",
            "storage-usage-evidence", "structured-file-shape-evidence",
            "system-description-evidence", "value-flow-evidence", "model-storage-evidence",
        ],
    }
    required_models = {
        "logical-physical-mapping": [
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
        ],
        "effective-data-model": [
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
            _model("logical-physical-model-mapping", "logical-physical-model-mapping/v1", "logical-physical-mapping"),
        ],
        "workspace-sql-catalog": [
            _model("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
        ],
        "interaction-field-contracts": [
            _model("repository-value-flow", "repository_value_flow/v6", "repository-value-flow"),
            _model("system-interactions", "workspace_system_interaction/v6", "system-interactions"),
        ],
        "cross-repository-value-flow": [
            _model("repository-value-flow", "repository_value_flow/v6", "repository-value-flow"),
            _model("system-interactions", "workspace_system_interaction/v6", "system-interactions"),
            _model("interaction-field-contracts", "workspace_system_interaction_field_contract/v2", "interaction-field-contracts"),
        ],
        "logical-storage-mapping": [
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics"),
        ],
        "sql-target-source-mapping": [
            _model("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
        ],
        "cross-artifact-data-model-mapping": [
            _model("logical-storage-model-mapping", "logical-storage-model-mapping/v2", "logical-storage-mapping"),
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
            _model("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
        ],
        "data-model-attribute-extension-context": [
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics"),
            _model("logical-storage-model-mapping", "logical-storage-model-mapping/v2", "logical-storage-mapping"),
            _model("cross-artifact-data-model-mapping", "cross-artifact-data-model-mapping/v6", "cross-artifact-data-model-mapping"),
            _model("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
        ],
    }
    optional_models = {
        "observed-storage-usage": [
            _model("code-declared-data-model", "code-declared-data-model/v1", "code-declared-data-model"),
            _model("physical-data-model", "knowledge_layer_physical_model/v1", "physical-model"),
        ],
        "effective-data-model": [
            _model("sql-observed-data-usage", "knowledge_layer_sql/v2", "sql-analysis"),
            _model("observed-storage-usage", "observed-storage-usage/v1", "observed-storage-usage"),
        ],
        "sql-target-source-mapping": [
            _model("model-storage-semantics", "model-storage-semantics/v1", "model-storage-semantics"),
        ],
    }
    lifecycle = {
        "physical-model": "current_typed_input",
        "sql-analysis": "current_typed_input",
        "interaction-coverage": "current",
        "interaction-islands": "current",
        "interaction-field-contracts": "current_typed_input",
        "cross-repository-value-flow": "current_typed_input",
        "system-interactions": "current_typed_input",
        "repository-value-flow": "current_typed_input",
        "persistence-lineage": "current_typed_input",
        "portfolio-topology": "current_profile_task_coupled",
        "suite-evidence-registry": "current_task_semantics_removal_required",
        "code-declared-data-model": "current_typed_input",
        "logical-physical-mapping": "current_typed_input",
        "observed-storage-usage": "current_typed_input",
        "effective-data-model": "current_typed_klc_composition",
        "workspace-sql-catalog": "current_typed_composition",
        "system-description": "current_typed_input",
        "reference-data": "current_typed_input",
        "model-storage-semantics": "current_typed_input",
        "logical-storage-mapping": "current_typed_klc_composition",
        "sql-target-source-mapping": "current_typed_klc_composition",
        "cross-artifact-data-model-mapping": "current_typed_klc_composition",
        "data-model-attribute-extension-context": "current_typed_klc_composition",
        "repository-inventory": "current_typed_input",
    }.get(mid, "planned_core_to_klc_migration")
    scope = {
        "physical-model": "physical_model_source",
        "sql-analysis": "repository_or_sql_source",
        "suite-evidence-registry": "suite",
        "system-interactions": "workspace",
        "interaction-coverage": "workspace",
        "interaction-islands": "workspace_or_portfolio",
        "interaction-field-contracts": "workspace",
        "cross-repository-value-flow": "workspace",
        "repository-value-flow": "workspace",
        "persistence-lineage": "repository",
        "repository-inventory": "repository",
        "portfolio-topology": "portfolio",
        "workspace-sql-catalog": "workspace",
        "cross-artifact-data-model-mapping": "workspace",
        "data-model-attribute-extension-context": "workspace",
    }.get(mid, "repository_or_workspace")
    current = not lifecycle.startswith("planned_")
    required = []
    for kind in required_by_mid[mid]:
        status = "current" if kind in {"physical-model", "sql-analysis"} else "proposed"
        if kind in {"repository-interaction-evidence", "interaction-coverage", "repository-value-flow"}:
            status = "current_output"
        required_policy = "produce_if_missing"
        required.append(_evidence(kind, status=status, production_policy=required_policy))
    optional = []
    for kind in optional_by_mid.get(mid, []):
        status = "current" if kind == "physical-model" else "proposed"
        if kind in {"interaction-coverage"}:
            status = "current_output"
        if kind == "core-foundation":
            status = "contract_only"
        optional_policy = "produce_if_missing"
        if mid == "repository-inventory" and kind not in {
            "data-model-candidate-evidence", "interaction-boundary-evidence", "structured-file-shape-evidence"
        }:
            optional_policy = "existing_only"
        optional.append(_evidence(kind, status=status, production_policy=optional_policy))
    return {
        "schema_version": "knowledge_materialization_contract/v3",
        "owner": "knowledge-layer-core",
        "materialization_id": mid,
        "definition": f"Definition for {mid}",
        "scope": scope,
        "lifecycle": lifecycle,
        "input_contract": {
            "required_evidence": required,
            "optional_evidence": optional,
            "required_knowledge_models": required_models.get(mid, []),
            "optional_knowledge_models": optional_models.get(mid, []),
            "semantic_identity": ["artifact_kind", "schema_version"],
        },
        "outputs": {
            "models": ({
                "workspace-sql-catalog": ["workspace-sql-catalog/v1"],
                "system-interactions": ["workspace_system_interaction/v6"],
                "repository-value-flow": ["repository_value_flow/v6", "repository_attribute_path/v2"],
                "interaction-field-contracts": ["workspace_system_interaction_field_contract/v2"],
                "cross-repository-value-flow": ["repository_value_flow/v6", "repository_attribute_path/v2"],
                "model-storage-semantics": ["model-storage-semantics/v1"],
                "logical-storage-mapping": ["logical-storage-model-mapping/v2"],
                "sql-target-source-mapping": ["sql-target-source-mapping/v1"],
                "cross-artifact-data-model-mapping": ["cross-artifact-data-model-mapping/v6"],
                "data-model-attribute-extension-context": ["data-model-attribute-extension-context/v1"],
            }.get(mid, [f"{mid}/v1"])),
            "capabilities": [f"knowledge.{mid}"],
            "materialized_marts": [mid],
        },
        "migration": {},
        "current_implementation": {
            "implementation_refs": [] if current else ["target"],
            "runtime": {
                "contract_id": "knowledge_materialization_runtime/v1",
                "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
                "registered": mid in {
                    "physical-model", "sql-analysis", "workspace-sql-catalog",
                    "system-interactions", "repository-value-flow", "interaction-field-contracts",
                    "cross-repository-value-flow",
                    "code-declared-data-model", "logical-physical-mapping",
                    "effective-data-model", "observed-storage-usage",
                    "system-description", "reference-data", "persistence-lineage",
                    "model-storage-semantics", "logical-storage-mapping", "sql-target-source-mapping",
                    "cross-artifact-data-model-mapping", "data-model-attribute-extension-context", "repository-inventory",
                },
                "handler_id": mid if mid in {
                    "physical-model", "sql-analysis", "workspace-sql-catalog",
                    "system-interactions", "repository-value-flow", "interaction-field-contracts",
                    "cross-repository-value-flow",
                    "code-declared-data-model", "logical-physical-mapping",
                    "effective-data-model", "observed-storage-usage",
                    "system-description", "reference-data", "persistence-lineage",
                    "model-storage-semantics", "logical-storage-mapping", "sql-target-source-mapping",
                    "cross-artifact-data-model-mapping", "data-model-attribute-extension-context", "repository-inventory",
                } else None,
            },
        },
    }


def _klc_payload() -> dict:
    current_ids = [
        "physical-model", "sql-analysis", "workspace-sql-catalog",
        "system-interactions", "interaction-coverage", "interaction-islands",
        "interaction-field-contracts", "cross-repository-value-flow", "repository-value-flow",
        "code-declared-data-model", "logical-physical-mapping", "effective-data-model",
        "observed-storage-usage", "system-description", "reference-data", "persistence-lineage",
        "model-storage-semantics", "logical-storage-mapping", "sql-target-source-mapping",
        "cross-artifact-data-model-mapping", "data-model-attribute-extension-context", "repository-inventory",
    ]
    payload = {
        "schema_version": "knowledge_materialization_catalog/v3",
        "klc_version": "0.59.6",
        "contract": {"contract_id": "knowledge_materialization_contract/v3"},
        "evidence_routing_contract": {"contract_id": "evidence_semantic_routing/v1"},
        "materializations": [_materialization(mid) for mid in current_ids],
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def _core_payload() -> dict:
    payload = {
        "schema_version": "core_target_analysis_contracts/v1",
        "core_version": "0.43.22",
        "contracts": {
            "foundation": {"contract_id": "core_foundation_contract/v1"},
            "evidence_analyzer": {"contract_id": "core_evidence_analyzer_contract/v1"},
            "evidence_artifact": {"contract_id": "core_evidence_artifact_contract/v1"},
        },
    }
    payload["contracts_fingerprint"] = _fingerprint(payload)
    return payload



def _core_evidence_payload() -> dict:
    def planning_for(kind: str) -> dict:
        execution_class = {
            "repository-structure-evidence": "always_on",
            "data-model-candidate-evidence": "bounded_preflight",
            "interaction-boundary-evidence": "bounded_preflight",
            "structured-file-shape-evidence": "bounded_preflight",
        }.get(kind, "full_analysis")
        phase = "p0" if execution_class == "always_on" else ("p1" if execution_class == "bounded_preflight" else None)
        role = {
            "repository-structure-evidence": "generic_structural",
            "structured-file-shape-evidence": "generic_structural",
            "data-model-candidate-evidence": "specialized_candidate",
            "interaction-boundary-evidence": "specialized_observation",
        }.get(kind, "domain_evidence")
        return {
            "execution_class": execution_class,
            "preflight_phase": phase,
            "discovery_role": role,
            "applicability": {
                "status": "not_formalized",
                "basis": "observed_source_landscape",
                "required_languages_any_of": [],
                "required_extensions_any_of": [],
                "when_unresolved": "execute_if_explicitly_requested_else_do_not_hard_skip",
            },
            "selection_safety": {
                "concept_inference_may_hard_skip": False,
                "hard_skip_requires_observed_non_applicability": True,
                "explicit_request_behavior": "execute_or_report_observed_blocking_precondition",
            },
            "budget": {
                "class": "full_analysis" if execution_class == "full_analysis" else "measured_bounded_current",
                "hard_bounds_declared": False,
            },
        }

    non_core = {
        "physical-model",
        "repository-metadata",
        "analysis-execution-result",
        "repository-interaction-evidence",
        "interaction-coverage",
        "repository-value-flow",
    }
    evidence_entries = [
        evidence
        for materialization_id in [
            "physical-model", "sql-analysis",
            "system-interactions", "interaction-coverage", "interaction-islands",
            "interaction-field-contracts", "cross-repository-value-flow", "repository-value-flow",
            "code-declared-data-model", "logical-physical-mapping", "observed-storage-usage",
            "effective-data-model", "system-description", "reference-data", "persistence-lineage", "workspace-sql-catalog",
            "model-storage-semantics", "logical-storage-mapping", "sql-target-source-mapping", "cross-artifact-data-model-mapping", "data-model-attribute-extension-context", "repository-inventory",
        ]
        for group in ("required_evidence", "optional_evidence")
        for evidence in (_materialization(materialization_id)["input_contract"].get(group) or [])
        if evidence["artifact_kind"] not in non_core
    ]
    contracts = []
    seen = set()
    for evidence in evidence_entries:
        kind = evidence["artifact_kind"]
        for version in evidence["schema_versions"]:
            identity = (kind, version)
            if identity in seen:
                continue
            seen.add(identity)
            published = kind in {"java-type-structure-evidence", "model-storage-evidence", "system-description-evidence", "reference-data-evidence", "persistence-lineage-evidence"}
            stages = {
                "java-type-structure-evidence": ["java_structural_scan", "java_source_observation_build"],
                "model-storage-evidence": ["java_model_storage_evidence"],
                "system-description-evidence": ["system_description_enrichment"],
                "reference-data-evidence": ["reference_data_fact_base"],
                "persistence-lineage-evidence": ["java_persistence_lineage_build"],
            }.get(kind, [])
            contract = {
                "artifact_kind": kind,
                "schema_version": version,
                "title": f"Contract for {kind}",
                "source_category": "source-code",
                "contract_status": "runtime_published" if published else "defined_not_published",
                "producer": {
                    "target_analyzer_id": kind.removesuffix("-evidence") + "-analyzer",
                    "current_source_stage_ids": stages,
                    "required_foundation_sections": ["repository-file-index"] if published else [],
                },
                "runtime_publication": {
                    "runtime_contract_id": "core_evidence_runtime/v1",
                    "registration_status": "registered" if published else "not_registered",
                },
                "current_state_assessment": {
                    "typed_runtime_artifact_published": published,
                },
                "preflight_planning": planning_for(kind),
            }
            contract["contract_fingerprint"] = _fingerprint(contract)
            contracts.append(contract)
    payload = {
        "schema_version": "core_evidence_contract_catalog/v1",
        "core_version": "0.43.27",
        "artifact_envelope_contract": "core_evidence_artifact_contract/v1",
        "contracts": sorted(contracts, key=lambda item: (item["artifact_kind"], item["schema_version"])),
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload

def _execution_payload() -> dict:
    payload = {
        "schema_version": "analysis_execution_result_catalog/v1",
        "runner_version": "0.9.42",
        "contract": {"contract_id": "analysis_execution_result_contract/v1"},
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def _catalog() -> dict:
    return kp.build_knowledge_catalog(
        _klc_payload(), _core_payload(), _core_evidence_payload(), _execution_payload()
    )


def _profile(*knowledge_ids: str, scope: str = "workspace") -> dict:
    return {
        "schema_version": "knowledge_profile/v2",
        "profile_id": "client-profile-knowledge",
        "title": "База знаний клиентского профиля",
        "scope": {"kind": scope, "scope_id": "client-profile"},
        "knowledge": [
            {"knowledge_id": value, "options": {"include_optional_sources": True, "minimum_coverage": None}}
            for value in knowledge_ids
        ],
        "presentation": {
            "include_evidence": True,
            "include_coverage": True,
            "include_gaps": True,
            "include_technical_details": False,
        },
    }


def test_catalog_exposes_user_knowledge_and_hides_internal_materializations():
    catalog = _catalog()

    assert catalog["schema_version"] == "knowledge_catalog/v2"
    assert catalog["summary"]["knowledge_type_count"] == 18
    assert catalog["summary"]["profile_v2_selectable_count"] == 18
    assert catalog["summary"]["internal_materialization_count"] == 4
    assert catalog["summary"]["uncatalogued_materialization_count"] == 0
    internal = {value["materialization_id"] for value in catalog["internal_materializations"]}
    assert internal == {"model-storage-semantics", "logical-storage-mapping", "sql-target-source-mapping", "cross-artifact-data-model-mapping"}
    visible = {value["knowledge_id"] for value in catalog["knowledge_types"]}
    assert {
        "code-declared-data-model", "physical-data-model", "logical-physical-mapping",
        "observed-storage-usage", "effective-data-model"
    }.issubset(visible)
    assert "conceptual-data-model" not in visible
    assert "common-data-model" not in visible
    assert "repository-inventory" in visible
    inventory = next(value for value in catalog["knowledge_types"] if value["knowledge_id"] == "repository-inventory")
    assert inventory["materialization"]["materialization_id"] == "repository-inventory"
    assert inventory["supported_scopes"] == ["repository"]
    required_policy = {item["artifact_kind"]: item["production_policy"] for item in inventory["sources"]["required"]}
    optional_policy = {item["artifact_kind"]: item["production_policy"] for item in inventory["sources"]["optional"]}
    assert required_policy == {"repository-structure-evidence": "produce_if_missing"}
    assert optional_policy["data-model-candidate-evidence"] == "produce_if_missing"
    assert optional_policy["interaction-boundary-evidence"] == "produce_if_missing"
    assert optional_policy["structured-file-shape-evidence"] == "produce_if_missing"
    assert optional_policy["java-type-structure-evidence"] == "existing_only"
    assert optional_policy["reference-data-evidence"] == "existing_only"
    assert optional_policy["system-description-evidence"] == "existing_only"


def test_catalog_separates_code_physical_mapping_usage_and_effective_knowledge():
    catalog = _catalog()
    by_id = {value["knowledge_id"]: value for value in catalog["knowledge_types"]}

    code_model = by_id["code-declared-data-model"]
    assert code_model["title"] == "Модель данных, объявленная в коде"
    assert [value["artifact_kind"] for value in code_model["sources"]["required"]] == [
        "java-type-structure-evidence"
    ]
    assert code_model["sources"]["required"][0]["analyzer_ids"] == ["java-type-structure-analyzer"]
    assert code_model["sources"]["required"][0]["producer_registration_status"] == "registered"
    assert "current_core_stage_ids" not in code_model["sources"]["required"][0]
    assert "future_analyzer_id" not in code_model["sources"]["required"][0]

    physical = by_id["physical-data-model"]
    assert [value["artifact_kind"] for value in physical["sources"]["required"]] == ["physical-model"]

    mapping = by_id["logical-physical-mapping"]
    assert [value["artifact_kind"] for value in mapping["sources"]["required"]] == [
        "java-persistence-mapping-evidence"
    ]
    assert set(mapping["required_knowledge_dependencies"]) == {
        "code-declared-data-model", "physical-data-model"
    }

    effective = by_id["effective-data-model"]
    assert effective["sources"]["required"] == []
    assert set(effective["required_knowledge_dependencies"]) == {
        "code-declared-data-model", "physical-data-model", "logical-physical-mapping"
    }
    assert effective["availability"]["status"] == "current_typed"
    assert effective["availability"]["can_execute_through_target_contracts"] is True
    workspace_sql = by_id["workspace-sql-source-inventory"]
    assert workspace_sql["availability"]["status"] == "current_typed"
    assert workspace_sql["availability"]["runtime_handler_id"] == "workspace-sql-catalog"
    assert catalog["data_model_knowledge_decomposition"]["rule"].startswith("Different source families")



def test_profile_resolver_expands_required_knowledge_and_builds_technical_preview():
    plan = kp.resolve_knowledge_profile(
        _catalog(),
        _profile("effective-data-model", "system-interactions"),
    )

    assert plan["schema_version"] == "knowledge_resolution_plan/v2"
    assert plan["execution_effect"] == "none"
    assert plan["status"]["overall"] == "current_typed"
    assert plan["status"]["requested_knowledge_count"] == 2
    assert plan["status"]["resolved_knowledge_count"] == 5
    assert set(plan["resolved_selection"]["implicit_required_knowledge_ids"]) == {
        "code-declared-data-model", "physical-data-model", "logical-physical-mapping"
    }
    materializations = {value["materialization_id"] for value in plan["technical_plan"]["materializations"]}
    assert materializations == {
        "effective-data-model", "code-declared-data-model", "physical-model",
        "logical-physical-mapping", "system-interactions"
    }
    evidence_keys = [(value["artifact_kind"], value["schema_version"]) for value in plan["technical_plan"]["evidence_requirements"]]
    assert len(evidence_keys) == len(set(evidence_keys))
    assert {value["model_kind"] for value in plan["technical_plan"]["knowledge_model_dependencies"]} >= {
        "code-declared-data-model", "physical-data-model", "logical-physical-model-mapping"
    }
    java_requirement = next(
        value for value in plan["technical_plan"]["evidence_requirements"]
        if value["artifact_kind"] == "java-type-structure-evidence"
    )
    assert java_requirement["analyzer_ids"] == ["java-type-structure-analyzer"]
    assert java_requirement["producer_registration_status"] == "registered"
    assert "core_stage_sources" not in plan["technical_plan"]
    assert all(
        source["actual_source_availability"] == "not_assessed"
        for knowledge in plan["knowledge_preview"]
        for source in knowledge["sources"]
    )



def test_repository_profile_rejects_workspace_only_knowledge():
    with pytest.raises(ValueError, match="does not support scope"):
        kp.resolve_knowledge_profile(_catalog(), _profile("system-interactions", scope="repository"))


def test_profile_rejects_internal_technical_fields():
    profile = _profile("code-declared-data-model")
    profile["task_id"] = "data-model"
    with pytest.raises(ValueError, match="forbidden technical fields"):
        kp.resolve_knowledge_profile(_catalog(), profile)


def test_profile_rejects_unknown_knowledge_and_duplicates():
    with pytest.raises(ValueError, match="unknown knowledge_id"):
        kp.resolve_knowledge_profile(_catalog(), _profile("unknown-knowledge"))
    profile = _profile("sql-source-inventory")
    profile["knowledge"].append(deepcopy(profile["knowledge"][0]))
    with pytest.raises(ValueError, match="duplicate knowledge_id"):
        kp.resolve_knowledge_profile(_catalog(), profile)


def test_interaction_field_contracts_expand_required_typed_dependencies():
    plan = kp.resolve_knowledge_profile(_catalog(), _profile("interaction-field-contracts"))
    assert plan["status"]["requested_knowledge_count"] == 1
    assert plan["status"]["resolved_knowledge_count"] == 3
    assert set(plan["resolved_selection"]["implicit_required_knowledge_ids"]) == {
        "system-interactions", "attribute-lineage"
    }
    assert {value["materialization_id"] for value in plan["technical_plan"]["materializations"]} == {
        "system-interactions", "repository-value-flow", "interaction-field-contracts"
    }


def test_cross_repository_attribute_lineage_expands_full_typed_chain():
    plan = kp.resolve_knowledge_profile(_catalog(), _profile("cross-repository-attribute-lineage"))
    assert plan["status"]["overall"] == "current_typed"
    assert plan["status"]["requested_knowledge_count"] == 1
    assert plan["status"]["resolved_knowledge_count"] == 4
    assert set(plan["resolved_selection"]["implicit_required_knowledge_ids"]) == {
        "attribute-lineage", "system-interactions", "interaction-field-contracts"
    }
    assert {value["materialization_id"] for value in plan["technical_plan"]["materializations"]} == {
        "repository-value-flow", "system-interactions", "interaction-field-contracts",
        "cross-repository-value-flow"
    }


def test_catalog_and_plan_are_deterministic_and_markdown_is_user_facing():
    first = _catalog()
    second = _catalog()
    assert first == second
    assert first["catalog_fingerprint"] == second["catalog_fingerprint"]
    catalog_md = kp.render_knowledge_catalog_markdown(first)
    assert "Пользователь выбирает знания" in catalog_md
    assert "Модель данных, объявленная в коде" in catalog_md

    plan = kp.resolve_knowledge_profile(first, _profile("code-declared-data-model"))
    plan2 = kp.resolve_knowledge_profile(first, _profile("code-declared-data-model"))
    assert plan == plan2
    plan_md = kp.render_knowledge_resolution_markdown(plan)
    assert "Что войдёт в базу знаний" in plan_md
    assert "фактическая доступность" in plan_md


def test_rejects_tampered_upstream_contracts():
    klc = _klc_payload()
    klc["klc_version"] = "tampered"
    with pytest.raises(ValueError, match="fingerprint"):
        kp.build_knowledge_catalog(klc, _core_payload(), _core_evidence_payload(), _execution_payload())


def test_rejects_legacy_materialization_catalog_v2():
    klc = _klc_payload()
    klc["schema_version"] = "knowledge_materialization_catalog/v2"
    with pytest.raises(ValueError, match="unsupported KLC materialization catalog schema"):
        kp.build_knowledge_catalog(klc, _core_payload(), _core_evidence_payload(), _execution_payload())


def test_unregistered_materialization_is_unavailable_without_legacy_route():
    catalog = _catalog()
    islands = next(
        item for item in catalog["knowledge_types"]
        if item["knowledge_id"] == "interaction-islands"
    )
    availability = islands["availability"]
    assert availability["status"] == "unavailable_unregistered"
    assert availability["business_knowledge_available_now"] is False
    assert availability["target_contract_status"] == "unavailable"
    assert "responsibility_map_schema" not in catalog["source"]


def test_cli_exports_catalog_and_resolves_yaml_profile(tmp_path: Path):
    files = {
        "klc.json": _klc_payload(),
        "core.json": _core_payload(),
        "core-evidence.json": _core_evidence_payload(),
        "execution.json": _execution_payload(),
    }
    for name, payload in files.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    catalog_path = tmp_path / "knowledge-catalog.json"
    catalog_md = tmp_path / "knowledge-catalog.md"
    result = runner.invoke(app, [
        "knowledge-catalog",
        "--klc-materialization-contracts", str(tmp_path / "klc.json"),
        "--core-target-contracts", str(tmp_path / "core.json"),
        "--core-evidence-contracts", str(tmp_path / "core-evidence.json"),
        "--execution-result-contracts", str(tmp_path / "execution.json"),
        "--output", str(catalog_path),
        "--markdown", str(catalog_md),
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["schema_version"] == "knowledge_catalog/v2"
    assert summary["profile_v2_selectable_count"] == 18

    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        """schema_version: knowledge_profile/v2
profile_id: customer-knowledge
 title: invalid
""".replace(" title", "title")
        + """scope:
  kind: workspace
  scope_id: customer-workspace
knowledge:
  - knowledge_id: effective-data-model
    options:
      include_optional_sources: true
      minimum_coverage: 0.75
  - knowledge_id: sql-source-inventory
    options: {}
presentation:
  include_evidence: true
  include_coverage: true
  include_gaps: true
  include_technical_details: false
""",
        encoding="utf-8",
    )
    plan_path = tmp_path / "plan.json"
    plan_md = tmp_path / "plan.md"
    result = runner.invoke(app, [
        "knowledge-profile-resolve",
        "--knowledge-catalog", str(catalog_path),
        "--profile", str(profile_path),
        "--output", str(plan_path),
        "--markdown", str(plan_md),
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["schema_version"] == "knowledge_resolution_plan/v2"
    assert summary["requested_knowledge_count"] == 2
    assert summary["resolved_knowledge_count"] == 5
    assert summary["implicit_required_dependency_count"] == 3
    assert summary["execution_effect"] == "none"
    assert plan_path.is_file()
    assert plan_md.is_file()


def _refingerprint_product_catalog(payload: dict) -> dict:
    payload = deepcopy(payload)
    payload.pop("catalog_fingerprint", None)
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def test_packaged_knowledge_product_catalog_is_versioned_fingerprinted_and_used_by_default():
    product_catalog = kp.load_knowledge_product_catalog()
    assert product_catalog["schema_version"] == "knowledge_product_catalog/v1"
    assert product_catalog["catalog_id"] == "default"
    assert len(product_catalog["knowledge_types"]) == 18
    assert not hasattr(kp, "_KNOWLEDGE_POLICY")

    catalog = _catalog()
    assert catalog["source"]["knowledge_product_catalog_schema"] == "knowledge_product_catalog/v1"
    assert catalog["source"]["knowledge_product_catalog_fingerprint"] == product_catalog["catalog_fingerprint"]
    assert catalog["source"]["knowledge_product_catalog_id"] == "default"
    assert catalog["source"]["knowledge_product_catalog_source"] == "packaged-default"


def test_knowledge_product_catalog_validation_rejects_unknown_dependencies_and_cycles():
    product_catalog = kp.load_knowledge_product_catalog()
    broken = deepcopy(product_catalog)
    broken["knowledge_types"][0]["required_knowledge_dependencies"] = ["missing-product"]
    broken = _refingerprint_product_catalog(broken)
    with pytest.raises(ValueError, match="unknown knowledge dependencies"):
        kp.validate_knowledge_product_catalog(broken)

    cyclic = deepcopy(product_catalog)
    by_id = {item["knowledge_id"]: item for item in cyclic["knowledge_types"]}
    by_id["code-declared-data-model"]["required_knowledge_dependencies"] = ["physical-data-model"]
    by_id["physical-data-model"]["required_knowledge_dependencies"] = ["code-declared-data-model"]
    cyclic = _refingerprint_product_catalog(cyclic)
    with pytest.raises(ValueError, match="dependency cycle"):
        kp.validate_knowledge_product_catalog(cyclic)


def test_new_user_facing_knowledge_can_be_added_only_in_product_catalog():
    product_catalog = kp.load_knowledge_product_catalog()
    product_catalog["knowledge_types"].append({
        "knowledge_id": "sql-source-inventory-alternate-view",
        "materialization_id": "sql-analysis",
        "title": "Альтернативное представление SQL-инвентаря",
        "summary": "Тестовое пользовательское представление уже существующей SQL materialization.",
        "contains": ["SQL source inventory"],
        "supported_scopes": ["repository", "workspace"],
        "category": "sql",
    })
    product_catalog = _refingerprint_product_catalog(product_catalog)

    catalog = kp.build_knowledge_catalog(
        _klc_payload(),
        _core_payload(),
        _core_evidence_payload(),
        _execution_payload(),
        product_catalog=product_catalog,
        product_catalog_source="external",
    )
    by_id = {item["knowledge_id"]: item for item in catalog["knowledge_types"]}
    added = by_id["sql-source-inventory-alternate-view"]
    assert added["materialization"]["materialization_id"] == "sql-analysis"
    assert catalog["summary"]["profile_v2_selectable_count"] == 19
    assert catalog["source"]["knowledge_product_catalog_source"] == "external"

    plan = kp.resolve_knowledge_profile(
        catalog,
        _profile("sql-source-inventory-alternate-view", scope="repository"),
    )
    assert plan["resolved_selection"]["requested_knowledge_ids"] == ["sql-source-inventory-alternate-view"]
    assert [item["materialization_id"] for item in plan["technical_plan"]["materializations"]] == ["sql-analysis"]


def test_cli_knowledge_catalog_accepts_external_product_catalog(tmp_path: Path):
    files = {
        "klc.json": _klc_payload(),
        "core.json": _core_payload(),
        "core-evidence.json": _core_evidence_payload(),
        "execution.json": _execution_payload(),
    }
    for name, payload in files.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    product_path = tmp_path / "products.json"
    product_path.write_text(
        json.dumps(kp.load_knowledge_product_catalog(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    catalog_path = tmp_path / "knowledge-catalog.json"
    result = runner.invoke(app, [
        "knowledge-catalog",
        "--klc-materialization-contracts", str(tmp_path / "klc.json"),
        "--core-target-contracts", str(tmp_path / "core.json"),
        "--core-evidence-contracts", str(tmp_path / "core-evidence.json"),
        "--execution-result-contracts", str(tmp_path / "execution.json"),
        "--knowledge-product-catalog", str(product_path),
        "--output", str(catalog_path),
    ])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["knowledge_product_catalog_source"] == "external"
    assert summary["knowledge_product_catalog_fingerprint"] == kp.load_knowledge_product_catalog()["catalog_fingerprint"]
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert payload["source"]["knowledge_product_catalog_source"] == "external"


def test_data_model_attribute_extension_adds_internal_materialization_closure():
    catalog = _catalog()
    plan = kp.resolve_knowledge_profile(
        catalog,
        _profile("data-model-attribute-extension", scope="workspace"),
    )

    assert plan["resolved_selection"]["requested_knowledge_ids"] == ["data-model-attribute-extension"]
    assert set(plan["resolved_selection"]["implicit_required_knowledge_ids"]) == {
        "code-declared-data-model",
        "physical-data-model",
        "sql-source-inventory",
    }
    assert plan["technical_plan"]["internal_materialization_ids"] == [
        "cross-artifact-data-model-mapping",
        "logical-storage-mapping",
        "model-storage-semantics",
        "sql-target-source-mapping",
    ]
    materializations = {
        value["materialization_id"]: value
        for value in plan["technical_plan"]["materializations"]
    }
    assert materializations["logical-storage-mapping"]["selection_origin"] == "internal_dependency"
    assert materializations["model-storage-semantics"]["selection_origin"] == "internal_dependency"
    assert materializations["cross-artifact-data-model-mapping"]["selection_origin"] == "internal_dependency"
    assert materializations["data-model-attribute-extension-context"]["knowledge_id"] == "data-model-attribute-extension"
    storage_evidence = [
        value for value in plan["technical_plan"]["evidence_requirements"]
        if value["artifact_kind"] == "model-storage-evidence"
    ]
    assert len(storage_evidence) == 1
    assert storage_evidence[0]["required_by"] == ["internal:model-storage-semantics"]
    assert plan["status"]["internal_materialization_dependency_count"] == 4
    assert any(
        value["diagnostic_id"] == "internal_materialization_dependencies_added"
        for value in plan["diagnostics"]
    )


def test_code_declared_data_model_adds_optional_storage_enrichment_closure():
    catalog = _catalog()
    plan = kp.resolve_knowledge_profile(
        catalog,
        _profile("code-declared-data-model", scope="repository"),
    )

    assert plan["technical_plan"]["internal_materialization_ids"] == [
        "logical-storage-mapping",
        "model-storage-semantics",
    ]
    assert plan["technical_plan"]["optional_internal_materialization_ids"] == [
        "logical-storage-mapping",
        "model-storage-semantics",
    ]
    materializations = {
        value["materialization_id"]: value
        for value in plan["technical_plan"]["materializations"]
    }
    assert materializations["logical-storage-mapping"]["selection_origin"] == "optional_internal_enrichment"
    assert materializations["logical-storage-mapping"]["execution_requirement"] == "optional"
    assert materializations["logical-storage-mapping"]["optional_by"] == ["code-declared-data-model"]
    assert materializations["model-storage-semantics"]["selection_origin"] == "optional_internal_enrichment"
    assert materializations["model-storage-semantics"]["execution_requirement"] == "optional"
    assert materializations["model-storage-semantics"]["optional_by"] == ["internal:logical-storage-mapping"]

    storage_evidence = [
        value for value in plan["technical_plan"]["evidence_requirements"]
        if value["artifact_kind"] == "model-storage-evidence"
    ]
    assert len(storage_evidence) == 1
    assert storage_evidence[0]["required_by"] == []
    assert storage_evidence[0]["optional_by"] == ["internal:model-storage-semantics"]
    assert plan["status"]["optional_internal_materialization_count"] == 2
    assert any(
        value["diagnostic_id"] == "optional_internal_materialization_enrichment_added"
        and value["materialization_ids"] == ["logical-storage-mapping", "model-storage-semantics"]
        for value in plan["diagnostics"]
    )


def test_code_declared_data_model_can_disable_optional_storage_enrichment():
    profile = _profile("code-declared-data-model", scope="repository")
    profile["knowledge"][0]["options"]["include_optional_sources"] = False
    plan = kp.resolve_knowledge_profile(_catalog(), profile)

    assert plan["technical_plan"]["internal_materialization_ids"] == []
    assert plan["technical_plan"]["optional_internal_materialization_ids"] == []
    assert plan["status"]["optional_internal_materialization_count"] == 0
    assert not any(
        value["artifact_kind"] == "model-storage-evidence"
        for value in plan["technical_plan"]["evidence_requirements"]
    )


def test_sql_source_inventory_adds_target_source_mapping_internal_dependency():
    catalog = _catalog()
    plan = kp.resolve_knowledge_profile(
        catalog,
        _profile("sql-source-inventory", scope="repository"),
    )
    assert plan["technical_plan"]["internal_materialization_ids"] == ["sql-target-source-mapping"]
    by_id = {item["materialization_id"]: item for item in plan["technical_plan"]["materializations"]}
    assert by_id["sql-target-source-mapping"]["selection_origin"] == "internal_dependency"
    assert by_id["sql-target-source-mapping"]["required_by"] == ["sql-source-inventory"]


def test_product_catalog_rejects_unknown_optional_internal_materialization():
    payload = kp.load_knowledge_product_catalog()
    payload.pop("catalog_fingerprint", None)
    for item in payload["knowledge_types"]:
        if item["knowledge_id"] == "code-declared-data-model":
            item["optional_internal_materializations"] = ["does-not-exist"]
            break
    payload["catalog_fingerprint"] = _fingerprint(payload)
    with pytest.raises(ValueError, match="unknown internal materializations"):
        kp.validate_knowledge_product_catalog(payload)


def test_product_catalog_rejects_required_optional_internal_overlap():
    payload = kp.load_knowledge_product_catalog()
    payload.pop("catalog_fingerprint", None)
    for item in payload["knowledge_types"]:
        if item["knowledge_id"] == "code-declared-data-model":
            item["required_internal_materializations"] = ["logical-storage-mapping"]
            item["optional_internal_materializations"] = ["logical-storage-mapping"]
            break
    payload["catalog_fingerprint"] = _fingerprint(payload)
    with pytest.raises(ValueError, match="both required and optional"):
        kp.validate_knowledge_product_catalog(payload)


def test_product_catalog_rejects_unknown_required_internal_materialization():
    payload = kp.load_knowledge_product_catalog()
    payload.pop("catalog_fingerprint", None)
    for item in payload["knowledge_types"]:
        if item["knowledge_id"] == "sql-source-inventory":
            item["required_internal_materializations"] = ["does-not-exist"]
            break
    payload["catalog_fingerprint"] = _fingerprint(payload)
    with pytest.raises(ValueError, match="unknown internal materializations"):
        kp.validate_knowledge_product_catalog(payload)
