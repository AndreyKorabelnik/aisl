from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .version import __version__

MATERIALIZATION_CONTRACT_SCHEMA_VERSION = "knowledge_materialization_contract/v3"
MATERIALIZATION_CATALOG_SCHEMA_VERSION = "knowledge_materialization_catalog/v3"
SUPPORTED_CORE_TARGET_CONTRACTS_SCHEMA = "core_target_analysis_contracts/v1"
EVIDENCE_ROUTING_CONTRACT_ID = "evidence_semantic_routing/v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _unique(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values if str(value).strip())
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must contain unique values")
    return normalized


def _validate_core_target_contracts(payload: Mapping[str, Any]) -> None:
    schema = str(payload.get("schema_version") or "")
    if schema != SUPPORTED_CORE_TARGET_CONTRACTS_SCHEMA:
        raise ValueError(
            f"unsupported Core target contracts schema: {schema!r}; "
            f"expected {SUPPORTED_CORE_TARGET_CONTRACTS_SCHEMA!r}"
        )
    actual = str(payload.get("contracts_fingerprint") or "")
    if not actual:
        raise ValueError("Core target contracts have no contracts_fingerprint")
    material = {str(key): deepcopy(value) for key, value in payload.items() if str(key) != "contracts_fingerprint"}
    expected = _fingerprint(material)
    if actual != expected:
        raise ValueError("Core target contracts fingerprint does not match canonical content")
    contracts = payload.get("contracts") or {}
    if not isinstance(contracts, Mapping):
        raise ValueError("Core target contracts have no contracts object")
    required = {
        "foundation": "core_foundation_contract/v1",
        "evidence_analyzer": "core_evidence_analyzer_contract/v1",
        "evidence_artifact": "core_evidence_artifact_contract/v1",
    }
    for key, contract_id in required.items():
        item = contracts.get(key) or {}
        if not isinstance(item, Mapping) or str(item.get("contract_id") or "") != contract_id:
            raise ValueError(f"Core target contracts are missing {contract_id}")


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    artifact_kind: str
    schema_versions: tuple[str, ...]
    contract_status: str = "proposed"
    purpose: str = ""
    production_policy: str = "produce_if_missing"

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_kind", str(self.artifact_kind).strip())
        object.__setattr__(self, "schema_versions", _unique(self.schema_versions, field_name="schema_versions"))
        object.__setattr__(self, "contract_status", str(self.contract_status).strip())
        object.__setattr__(self, "purpose", str(self.purpose).strip())
        object.__setattr__(self, "production_policy", str(self.production_policy).strip())
        if not self.artifact_kind:
            raise ValueError("artifact_kind must not be empty")
        if not self.schema_versions:
            raise ValueError("schema_versions must not be empty")
        if self.production_policy not in {"produce_if_missing", "existing_only"}:
            raise ValueError("production_policy must be produce_if_missing or existing_only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_kind": self.artifact_kind,
            "schema_versions": list(self.schema_versions),
            "contract_status": self.contract_status,
            "purpose": self.purpose,
            "production_policy": self.production_policy,
            "semantic_selector": "artifact_kind_plus_schema_version",
        }


@dataclass(frozen=True, slots=True)
class KnowledgeModelRequirement:
    model_kind: str
    schema_versions: tuple[str, ...]
    source_materialization_id: str
    purpose: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_kind", str(self.model_kind).strip())
        object.__setattr__(self, "schema_versions", _unique(self.schema_versions, field_name="knowledge_model_schema_versions"))
        object.__setattr__(self, "source_materialization_id", str(self.source_materialization_id).strip())
        object.__setattr__(self, "purpose", str(self.purpose).strip())
        if not self.model_kind:
            raise ValueError("model_kind must not be empty")
        if not self.schema_versions:
            raise ValueError("knowledge model schema_versions must not be empty")
        if not self.source_materialization_id:
            raise ValueError("source_materialization_id must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_kind": self.model_kind,
            "schema_versions": list(self.schema_versions),
            "source_materialization_id": self.source_materialization_id,
            "purpose": self.purpose,
            "semantic_selector": "model_kind_plus_schema_version",
        }


@dataclass(frozen=True, slots=True)
class MaterializationDefinition:
    materialization_id: str
    lifecycle: str
    scope: str
    definition: str
    required_evidence: tuple[EvidenceRequirement, ...]
    optional_evidence: tuple[EvidenceRequirement, ...]
    produced_models: tuple[str, ...]
    capabilities: tuple[str, ...]
    materialized_marts: tuple[str, ...]
    implementation_refs: tuple[str, ...]
    conditional_capabilities: tuple[str, ...] = ()
    required_knowledge_models: tuple[KnowledgeModelRequirement, ...] = ()
    optional_knowledge_models: tuple[KnowledgeModelRequirement, ...] = ()
    current_inputs: tuple[str, ...] = ()
    runtime_handler_id: str | None = None
    evidence_gaps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "materialization_id", str(self.materialization_id).strip())
        object.__setattr__(self, "lifecycle", str(self.lifecycle).strip())
        object.__setattr__(self, "scope", str(self.scope).strip())
        object.__setattr__(self, "definition", str(self.definition).strip())
        object.__setattr__(self, "required_evidence", tuple(self.required_evidence))
        object.__setattr__(self, "optional_evidence", tuple(self.optional_evidence))
        object.__setattr__(self, "produced_models", _unique(self.produced_models, field_name="produced_models"))
        object.__setattr__(self, "capabilities", _unique(self.capabilities, field_name="capabilities"))
        object.__setattr__(
            self,
            "conditional_capabilities",
            _unique(self.conditional_capabilities, field_name="conditional_capabilities"),
        )
        object.__setattr__(self, "materialized_marts", _unique(self.materialized_marts, field_name="materialized_marts"))
        object.__setattr__(self, "implementation_refs", _unique(self.implementation_refs, field_name="implementation_refs"))
        object.__setattr__(self, "required_knowledge_models", tuple(self.required_knowledge_models))
        object.__setattr__(self, "optional_knowledge_models", tuple(self.optional_knowledge_models))
        object.__setattr__(self, "current_inputs", _unique(self.current_inputs, field_name="current_inputs"))
        object.__setattr__(self, "runtime_handler_id", str(self.runtime_handler_id).strip() if self.runtime_handler_id else None)
        object.__setattr__(self, "evidence_gaps", _unique(self.evidence_gaps, field_name="evidence_gaps"))
        object.__setattr__(self, "notes", _unique(self.notes, field_name="notes"))
        if not self.materialization_id:
            raise ValueError("materialization_id must not be empty")
        required_kinds = [item.artifact_kind for item in self.required_evidence]
        optional_kinds = [item.artifact_kind for item in self.optional_evidence]
        if len(set(required_kinds)) != len(required_kinds):
            raise ValueError(f"duplicate required evidence kind for {self.materialization_id}")
        if len(set(optional_kinds)) != len(optional_kinds):
            raise ValueError(f"duplicate optional evidence kind for {self.materialization_id}")
        overlap = sorted(set(required_kinds) & set(optional_kinds))
        if overlap:
            raise ValueError(f"evidence kind cannot be both required and optional for {self.materialization_id}: {overlap}")
        required_models = [(item.model_kind, item.source_materialization_id) for item in self.required_knowledge_models]
        optional_models = [(item.model_kind, item.source_materialization_id) for item in self.optional_knowledge_models]
        if len(set(required_models)) != len(required_models):
            raise ValueError(f"duplicate required knowledge model for {self.materialization_id}")
        if len(set(optional_models)) != len(optional_models):
            raise ValueError(f"duplicate optional knowledge model for {self.materialization_id}")
        model_overlap = sorted(set(required_models) & set(optional_models))
        if model_overlap:
            raise ValueError(f"knowledge model cannot be both required and optional for {self.materialization_id}: {model_overlap}")
        capability_overlap = sorted(set(self.capabilities) & set(self.conditional_capabilities))
        if capability_overlap:
            raise ValueError(
                f"capability cannot be both guaranteed and conditional for {self.materialization_id}: "
                f"{capability_overlap}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MATERIALIZATION_CONTRACT_SCHEMA_VERSION,
            "materialization_id": self.materialization_id,
            "owner": "knowledge-layer-core",
            "lifecycle": self.lifecycle,
            "scope": self.scope,
            "definition": self.definition,
            "input_contract": {
                "routing_contract": EVIDENCE_ROUTING_CONTRACT_ID,
                "semantic_identity": ["artifact_kind", "schema_version"],
                "forbidden_semantic_selectors": ["task_id", "suite_id", "profile_id", "report_profile_id"],
                "required_evidence": [item.to_dict() for item in self.required_evidence],
                "optional_evidence": [item.to_dict() for item in self.optional_evidence],
                "required_knowledge_models": [item.to_dict() for item in self.required_knowledge_models],
                "optional_knowledge_models": [item.to_dict() for item in self.optional_knowledge_models],
                "missing_required_evidence_policy": "explicit_failure_or_materialization_gap_no_hidden_fallback",
                "missing_required_knowledge_model_policy": "explicit_failure_or_materialization_gap_no_hidden_fallback",
                "unsupported_schema_policy": "explicit_failure_no_silent_reinterpretation",
            },
            "outputs": {
                "models": list(self.produced_models),
                "capabilities": list(self.capabilities),
                "conditional_capabilities": list(self.conditional_capabilities),
                "materialized_marts": list(self.materialized_marts),
                "required_metadata": ["coverage", "diagnostics", "provenance", "content_fingerprint"],
            },
            "current_implementation": {
                "implementation_refs": list(self.implementation_refs),
                "current_inputs": list(self.current_inputs),
                "runtime": {
                    "contract_id": "knowledge_materialization_runtime/v1",
                    "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
                    "registered": self.runtime_handler_id is not None,
                    "handler_id": self.runtime_handler_id,
                },
            },
            "evidence_gaps": list(self.evidence_gaps),
            "notes": list(self.notes),
        }


def _evidence(
    artifact_kind: str,
    *schema_versions: str,
    status: str = "proposed",
    purpose: str = "",
    production_policy: str = "produce_if_missing",
) -> EvidenceRequirement:
    return EvidenceRequirement(
        artifact_kind=artifact_kind,
        schema_versions=tuple(schema_versions),
        contract_status=status,
        purpose=purpose,
        production_policy=production_policy,
    )


def _knowledge_model(
    model_kind: str,
    *schema_versions: str,
    source_materialization_id: str,
    purpose: str = "",
) -> KnowledgeModelRequirement:
    return KnowledgeModelRequirement(
        model_kind=model_kind,
        schema_versions=tuple(schema_versions),
        source_materialization_id=source_materialization_id,
        purpose=purpose,
    )


CURRENT_MATERIALIZATIONS: tuple[MaterializationDefinition, ...] = (
    MaterializationDefinition(
        materialization_id="repository-inventory",
        lifecycle="current_typed_input",
        scope="repository",
        definition="Compose official Core observed evidence into one phased repository inventory with independent coverage/completeness, structural discovery and bounded concept-classification axes.",
        required_evidence=(
            _evidence("repository-structure-evidence", "repository-structure-evidence/v1", status="current", purpose="Complete concept-agnostic repository file frontier and analyzer coverage."),
        ),
        optional_evidence=(
            _evidence("data-model-candidate-evidence", "data-model-candidate-evidence/v1", status="current", purpose="Official observed candidate signals for data-model classification.", production_policy="produce_if_missing"),
            _evidence("interaction-boundary-evidence", "interaction-boundary-evidence/v1", status="current", purpose="Official interaction boundary observations.", production_policy="produce_if_missing"),
            _evidence("java-persistence-mapping-evidence", "java-persistence-mapping-evidence/v1", status="current", purpose="Official Java persistence mapping observations.", production_policy="existing_only"),
            _evidence("java-type-structure-evidence", "java-type-structure-evidence/v1", status="current", purpose="Official Java structural observations.", production_policy="existing_only"),
            _evidence("persistence-lineage-evidence", "persistence-lineage-evidence/v1", status="current", purpose="Official persistence path observations.", production_policy="existing_only"),
            _evidence("reference-data-evidence", "reference-data-evidence/v1", status="current", purpose="Official declared/reference value observations.", production_policy="existing_only"),
            _evidence("sql-analysis", "sql-analysis/v1", status="current", purpose="Official SQL structural/data-flow observations.", production_policy="existing_only"),
            _evidence("storage-usage-evidence", "storage-usage-evidence/v1", status="current", purpose="Official storage usage observations.", production_policy="existing_only"),
            _evidence("structured-file-shape-evidence", "structured-file-shape-evidence/v1", status="current", purpose="Official bounded generic structured-file member descriptors for preflight family membership/variant enrichment.", production_policy="produce_if_missing"),
            _evidence("system-description-evidence", "system-description-evidence/v1", status="current", purpose="Official system/scenario observations.", production_policy="existing_only"),
            _evidence("value-flow-evidence", "value-flow-evidence/v1", status="current", purpose="Official value-flow observations.", production_policy="existing_only"),
            _evidence("model-storage-evidence", "model-storage-evidence/v1", status="current", purpose="Official model-to-storage observations.", production_policy="existing_only"),
        ),
        produced_models=("repository-inventory/v5",),
        capabilities=("common.repository-inventory", "common.repository-identity", "common.repository-technologies", "common.repository-interfaces", "common.repository-inputs-outputs", "common.repository-data-footprint", "common.repository-storage-footprint", "common.repository-coverage", "common.repository-coverage-gaps", "common.repository-structural-families", "common.repository-unknown-primitives", "common.repository-discovery", "common.repository-source-occurrences"),
        conditional_capabilities=("common.repository-structural-members",),
        materialized_marts=("repository-inventory", "repository-coverage-frontier", "repository-discovery"),
        implementation_refs=("knowledge_layer_core.repository_inventory_builder.build_repository_inventory_knowledge_layer",),
        current_inputs=("repository-structure-evidence/v1 plus bounded preflight data-model-candidate, interaction-boundary and structured-file-shape evidence; deeper official Core evidence remains existing-only",),
        runtime_handler_id="repository-inventory",
        notes=(
            "The materializer never scans source repositories and never invokes Java/SQL/config parsers.",
            "Repository Inventory is Core-level structural metadata only: it publishes observed families, salience, analyzer-frontier unknowns, coverage and provenance; it does not produce KLC concept labels or repository-local novelty claims.",
            "Family-level concept classifications are stored sparsely only for detector/evidence-kind pairs covered by the detector registry; repository-level concept status remains dense for every registered concept.",
            "SourceOccurrence is normalized observed provenance only; it does not assert concept semantics or benchmark representativeness.",
        ),
    ),
    MaterializationDefinition(
        materialization_id="physical-model",
        lifecycle="current_typed_input",
        scope="physical_model_source",
        definition="Materialize a supplied physical-model/v1 artifact into typed table, column, key, relationship and gap structures.",
        required_evidence=(
            _evidence("physical-model", "physical-model/v1", status="current", purpose="Canonical physical model source artifact."),
        ),
        optional_evidence=(),
        produced_models=("knowledge_layer_physical_model/v1",),
        capabilities=(
            "common.physical-model", "common.physical-model.pdm", "common.physical-model.tables",
            "common.physical-model.columns", "common.physical-model.keys",
            "common.physical-model.relationships", "common.physical-model.gaps",
        ),
        materialized_marts=("physical-model-inventory", "physical-model-keys-and-relationships"),
        implementation_refs=("knowledge_layer_core.physical_model_builder.build_physical_model_knowledge_layer",),
        current_inputs=("physical-model/v1 manifest and fact files",),
        runtime_handler_id="physical-model",
    ),
    MaterializationDefinition(
        materialization_id="sql-analysis",
        lifecycle="current_typed_input",
        scope="repository_or_sql_source",
        definition="Materialize repository SQL statements, relations, field use, semantic roles and source-to-target evidence.",
        required_evidence=(
            _evidence("sql-analysis", "sql-analysis/v1", status="current", purpose="Repository-level SQL evidence artifact."),
        ),
        optional_evidence=(
            _evidence("physical-model", "physical-model/v1", status="current", purpose="Optional physical-model correspondence and target resolution."),
        ),
        produced_models=("knowledge_layer_sql/v2",),
        capabilities=(
            "common.sql-analysis", "common.sql-relation-fields", "common.sql-source-inventory",
            "common.sql-source-inventory-export", "common.sql-relation-semantic-roles",
            "common.sql-target-column-lineage", "common.sql-field-calculation", "common.sql-workflow-bindings",
            "common.sql-workflow-context", "common.sql-target-resolution",
            "common.sql-attribute-insertion-context",
        ),
        materialized_marts=("sql-relation-field-inventory", "sql-relation-semantic-roles"),
        implementation_refs=("knowledge_layer_core.sql_analysis_builder.build_sql_knowledge_layer",),
        current_inputs=("sql-analysis/v1 artifact",),
        runtime_handler_id="sql-analysis",
    ),
    MaterializationDefinition(
        materialization_id="workspace-sql-catalog",
        lifecycle="current_typed_composition",
        scope="workspace",
        definition="Compose one or more repository SQL knowledge artifacts into a workspace-wide SQL catalog without re-analyzing source code.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model(
                "sql-observed-data-usage",
                "knowledge_layer_sql/v2",
                source_materialization_id="sql-analysis",
                purpose="Repository SQL knowledge artifacts to combine. Multiple matching artifacts are preserved.",
            ),
        ),
        optional_knowledge_models=(),
        produced_models=("workspace-sql-catalog/v1",),
        capabilities=(
            "common.workspace-sql-catalog",
            "common.sql-analysis", "common.sql-relation-fields", "common.sql-source-inventory",
            "common.sql-source-inventory-export", "common.sql-relation-semantic-roles",
            "common.sql-target-column-lineage", "common.sql-field-calculation",
            "common.sql-workflow-bindings", "common.sql-workflow-context",
            "common.sql-target-resolution", "common.sql-attribute-insertion-context",
        ),
        materialized_marts=("workspace-sql-catalog", "sql-relation-field-inventory", "sql-relation-semantic-roles"),
        implementation_refs=("knowledge_layer_core.workspace_sql_catalog_builder.build_workspace_sql_catalog",),
        current_inputs=("one or more knowledge_layer_sql/v2 artifacts",),
        runtime_handler_id="workspace-sql-catalog",
        notes=(
            "Repository facts retain repo_id and provenance; duplicate repository IDs are rejected.",
            "The composition does not infer cross-repository lineage or merge ambiguous relation identities.",
        ),
    ),
    MaterializationDefinition(
        materialization_id="system-description",
        lifecycle="current_typed_input",
        scope="repository",
        definition="Materialize typed system interface, scenario, dependency, storage and access-boundary records without Task/Suite routing.",
        required_evidence=(
            _evidence("system-description-evidence", "system-description-evidence/v1", status="current", purpose="Core-owned deterministic compact system-description evidence."),
        ),
        optional_evidence=(),
        produced_models=("system-description/v1",),
        capabilities=("common.system-description", "common.system-interfaces", "common.system-scenarios", "common.system-dependencies"),
        materialized_marts=("system-description",),
        implementation_refs=("knowledge_layer_core.subject_knowledge_builder.build_subject_knowledge_layer",),
        current_inputs=("system-description-evidence/v1 generic Core evidence artifact",),
        runtime_handler_id="system-description",
        notes=("The materialization preserves observed records and does not introduce business interpretation.",),
    ),
    MaterializationDefinition(
        materialization_id="reference-data",
        lifecycle="current_typed_input",
        scope="repository",
        definition="Materialize a facts-only reference-data knowledge base from typed declared-value and contextual evidence without classifying NSI ownership or semantics.",
        required_evidence=(
            _evidence("reference-data-evidence", "reference-data-evidence/v1", status="current", purpose="Core-owned facts-only reference-data sections and unresolved gaps."),
        ),
        optional_evidence=(),
        produced_models=("reference-data/v1",),
        capabilities=("common.reference-data", "common.declared-value-sets", "common.reference-data-facts"),
        materialized_marts=("reference-data",),
        implementation_refs=("knowledge_layer_core.subject_knowledge_builder.build_subject_knowledge_layer",),
        current_inputs=("reference-data-evidence/v1 generic Core evidence artifact",),
        runtime_handler_id="reference-data",
        notes=("No reference-data classification is performed; observed alternatives and gaps are preserved.",),
    ),
    MaterializationDefinition(
        materialization_id="persistence-lineage",
        lifecycle="current_typed_input",
        scope="repository",
        definition="Materialize factual source-to-storage and storage-to-access persistence paths, writes, reads, field mappings and explicit gaps.",
        required_evidence=(
            _evidence("persistence-lineage-evidence", "persistence-lineage-evidence/v1", status="current", purpose="Core-owned deterministic persistence lineage observations."),
        ),
        optional_evidence=(),
        produced_models=("persistence-lineage/v1",),
        capabilities=("workspace.persistence-lineage", "workspace.fdp-paths"),
        materialized_marts=("persistence-lineage",),
        implementation_refs=("knowledge_layer_core.subject_knowledge_builder.build_subject_knowledge_layer",),
        current_inputs=("persistence-lineage-evidence/v1 generic Core evidence artifact",),
        runtime_handler_id="persistence-lineage",
        notes=("No FDP verdict is assigned; incomplete paths remain explicit records or gaps.",),
    ),
    MaterializationDefinition(
        materialization_id="system-interactions",
        lifecycle="current_typed_input",
        scope="workspace",
        definition="Match repository interaction boundaries into inter-repository and inter-system interaction facts.",
        required_evidence=(
            _evidence("interaction-boundary-evidence", "interaction-boundary-evidence/v1", purpose="Inbound and outbound protocol boundary observations."),
        ),
        optional_evidence=(
            _evidence("configuration-evidence", "configuration-evidence/v1", purpose="Resolved endpoint/topic properties and aliases."),
            _evidence("execution-context-evidence", "execution-context-evidence/v1", purpose="Optional path from ingress to outbound operation."),
        ),
        produced_models=("workspace_system_interaction/v6",),
        capabilities=("workspace.system-interactions", "workspace.repository-interaction-boundaries"),
        materialized_marts=("workspace-repository-interaction-boundaries", "workspace-system-interactions"),
        implementation_refs=("knowledge_layer_core.interaction_knowledge_builder.build_system_interactions_knowledge_layer",),
        current_inputs=("interaction-boundary-evidence/v1 generic Core evidence artifacts",),
        runtime_handler_id="system-interactions",
    ),
    MaterializationDefinition(
        materialization_id="interaction-coverage",
        lifecycle="current",
        scope="workspace",
        definition="Materialize coverage and diagnostics over repository interaction boundaries.",
        required_evidence=(
            _evidence("interaction-boundary-evidence", "interaction-boundary-evidence/v1", purpose="Repository interaction boundaries."),
        ),
        optional_evidence=(),
        produced_models=("repository_interaction_coverage/v1",),
        capabilities=("workspace.repository-interaction-coverage",),
        materialized_marts=("workspace-repository-interaction-coverage",),
        implementation_refs=("knowledge_layer_core.interaction_coverage.materialize_repository_interaction_coverage",),
    ),
    MaterializationDefinition(
        materialization_id="interaction-islands",
        lifecycle="current",
        scope="workspace_or_portfolio",
        definition="Build strict and extended connected repository islands from confirmed/probable interaction evidence.",
        required_evidence=(
            _evidence("repository-interaction-evidence", "workspace_system_interaction/v6", status="current_output", purpose="Resolved interaction edges."),
        ),
        optional_evidence=(
            _evidence("interaction-coverage", "repository_interaction_coverage/v1", status="current_output", purpose="Coverage and diagnostic context."),
        ),
        produced_models=("repository_interaction_island/v2",),
        capabilities=("workspace.repository-interaction-islands",),
        materialized_marts=("workspace-repository-interaction-islands",),
        implementation_refs=("knowledge_layer_core.interaction_islands.materialize_repository_interaction_islands",),
        notes=("This is a KLC-internal materialization dependency, not a dependency between public Core analyzers.",),
    ),
    MaterializationDefinition(
        materialization_id="interaction-field-contracts",
        lifecycle="current_typed_input",
        scope="workspace",
        definition="Materialize field-level contracts over matched system interactions.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("repository-value-flow", "repository_value_flow/v6", source_materialization_id="repository-value-flow", purpose="Repository-local value nodes, wire observations and direct edges."),
            _knowledge_model("system-interactions", "workspace_system_interaction/v6", source_materialization_id="system-interactions", purpose="Matched repository boundaries and execution context."),
        ),
        produced_models=("workspace_system_interaction_field_contract/v2",),
        capabilities=("workspace.system-interaction-field-contracts",),
        materialized_marts=("workspace-system-interaction-field-contracts",),
        implementation_refs=("knowledge_layer_core.interaction_field_contract_knowledge_builder.build_system_interaction_field_contract_knowledge_layer",),
        current_inputs=("repository_value_flow/v6 and workspace_system_interaction/v6 typed KLC knowledge artifacts",),
        runtime_handler_id="interaction-field-contracts",
    ),
    MaterializationDefinition(
        materialization_id="cross-repository-value-flow",
        lifecycle="current_typed_input",
        scope="workspace",
        definition="Enrich repository-local value flow with transport edges over matched system interactions and field contracts.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("repository-value-flow", "repository_value_flow/v6", source_materialization_id="repository-value-flow", purpose="Repository-local value graph and typed value-flow observations."),
            _knowledge_model("system-interactions", "workspace_system_interaction/v6", source_materialization_id="system-interactions", purpose="Matched HTTP repository boundaries."),
            _knowledge_model("interaction-field-contracts", "workspace_system_interaction_field_contract/v2", source_materialization_id="interaction-field-contracts", purpose="Field-level wire correspondences over matched interactions."),
        ),
        produced_models=("repository_value_flow/v6", "repository_attribute_path/v2"),
        capabilities=("workspace.repository-value-flow", "workspace.attribute-path-resolver", "workspace.cross-repository-value-flow"),
        materialized_marts=("workspace-repository-value-flow", "workspace-cross-repository-value-flow"),
        implementation_refs=("knowledge_layer_core.cross_repository_value_flow_builder.build_cross_repository_value_flow_knowledge_layer",),
        current_inputs=("repository-value-flow, system-interactions and interaction-field-contracts typed KLC knowledge artifacts",),
        runtime_handler_id="cross-repository-value-flow",
    ),
    MaterializationDefinition(
        materialization_id="repository-value-flow",
        lifecycle="current_typed_input",
        scope="workspace",
        definition="Compose repository-local flow facts into a queryable repository value-flow graph.",
        required_evidence=(
            _evidence("value-flow-evidence", "value-flow-evidence/v1", purpose="Atomic value-flow nodes, edges, bindings and gaps."),
        ),
        optional_evidence=(
            _evidence("persistence-lineage-evidence", "persistence-lineage-evidence/v1", purpose="Storage endpoints and persistent field correspondence."),
            _evidence("interaction-boundary-evidence", "interaction-boundary-evidence/v1", purpose="Boundary inputs and outputs."),
        ),
        produced_models=("repository_value_flow/v6", "repository_attribute_path/v2"),
        capabilities=("workspace.repository-value-flow", "workspace.attribute-path-resolver"),
        materialized_marts=("workspace-repository-value-flow",),
        implementation_refs=("knowledge_layer_core.value_flow.materialize_repository_value_flow",),
        current_inputs=("value-flow-evidence/v1 generic Core evidence artifacts",),
        runtime_handler_id="repository-value-flow",
    ),
    MaterializationDefinition(
        materialization_id="logical-physical-mapping",
        lifecycle="current_typed_input",
        scope="repository_or_workspace",
        definition="Compose explicit persistence mappings between the code-declared model and the physical model; do not infer JPA default names or conceptual identity from physical names alone.",
        required_evidence=(
            _evidence("java-persistence-mapping-evidence", "java-persistence-mapping-evidence/v1", status="current", purpose="Explicit entity/table, field/column, key and relationship declarations."),
        ),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Logical objects and members to map."),
            _knowledge_model("physical-data-model", "knowledge_layer_physical_model/v1", source_materialization_id="physical-model", purpose="Physical tables, columns, keys and relationships to map."),
        ),
        produced_models=("logical-physical-model-mapping/v1",),
        capabilities=("common.logical-physical-mapping", "common.entity-table-mapping", "common.field-column-mapping"),
        materialized_marts=("logical-physical-entity-mapping", "logical-physical-field-mapping", "mapping-gaps"),
        implementation_refs=("knowledge_layer_core.logical_physical_mapping_builder.build_logical_physical_mapping_knowledge_layer",),
        current_inputs=("java-persistence-mapping-evidence/v1 plus code-declared-data-model/v1 and knowledge_layer_physical_model/v1",),
        runtime_handler_id="logical-physical-mapping",
        evidence_gaps=(
            "Method/property access and composite mapping annotations remain explicit evidence gaps in java-persistence-mapping-evidence/v1.",
            "The physical-model/v1 contract has no dedicated schema/catalog fields; qualifiers are preserved without inferred correspondence.",
        ),
        notes=("Only unique exact matches of explicitly declared identifiers create mappings; JPA defaults and name similarity are not used.",),
    ),
    MaterializationDefinition(
        materialization_id="code-declared-data-model",
        lifecycle="current_typed_input",
        scope="repository_or_workspace",
        definition="Compose observed source-code type, field, relationship and inheritance declarations into a code-declared data model without physical-schema substitution.",
        required_evidence=(
            _evidence("java-type-structure-evidence", "java-type-structure-evidence/v1", status="current", purpose="Observed model type, field, relationship and inheritance declarations from source code."),
        ),
        optional_evidence=(),
        produced_models=("code-declared-data-model/v1",),
        capabilities=("common.code-declared-data-model", "common.code-declared-entities", "common.code-declared-fields", "common.code-declared-relationships", "common.code-declared-inheritance"),
        materialized_marts=("code-declared-entities", "code-declared-fields", "code-declared-relationships", "code-declared-inheritance"),
        implementation_refs=("knowledge_layer_core.code_declared_model_builder.build_code_declared_data_model_knowledge_layer",),
        current_inputs=("Runner-registered java-type-structure-evidence/v1 artifacts",),
        runtime_handler_id="code-declared-data-model",
        evidence_gaps=(),
    ),

    MaterializationDefinition(
        materialization_id="logical-storage-mapping",
        lifecycle="current_typed_klc_composition",
        scope="repository_or_workspace",
        definition="Bind observed storage aliases and storage-reference fields to the code-declared model and derive evidence-backed storage-level join semantics from exact reference-value/target-identity correspondence without requiring PDM or SQL.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Declared types, effective fields, relationships and inheritance."),
            _knowledge_model("model-storage-semantics", "model-storage-semantics/v1", source_materialization_id="model-storage-semantics", purpose="Observed storage aliases, keys and references."),
        ),
        produced_models=("logical-storage-model-mapping/v2",),
        capabilities=("common.logical-storage-mapping", "common.logical-storage-identity", "common.logical-storage-relationship", "common.logical-storage-join-semantics"),
        materialized_marts=("logical-storage-entity-mapping", "logical-storage-relationship-mapping", "logical-storage-join-semantics"),
        implementation_refs=("knowledge_layer_core.logical_storage_mapping_builder.build_logical_storage_mapping_knowledge_layer",),
        current_inputs=("code-declared-data-model/v1 plus model-storage-semantics/v1",),
        runtime_handler_id="logical-storage-mapping",
        notes=("No case folding, naming similarity or SQL/PDM normalization is used; ambiguous candidates remain explicit. Storage join semantics are not physical SQL join claims.",),
    ),

    MaterializationDefinition(
        materialization_id="sql-target-source-mapping",
        lifecycle="current_typed_klc_composition",
        scope="repository_or_workspace",
        definition="Compose workflow target-column lineage through observed SQL relation producers into raw ultimate SQL origins and, when model-storage semantics are supplied, evidence-backed value origins.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("sql-observed-data-usage", "knowledge_layer_sql/v2", source_materialization_id="sql-analysis", purpose="Observed SQL lineage, workflow bindings and script calls used to derive relation producers."),
        ),
        optional_knowledge_models=(
            _knowledge_model("model-storage-semantics", "model-storage-semantics/v1", source_materialization_id="model-storage-semantics", purpose="Optional typed storage-key semantics used to distinguish encoded parent-key dependencies from value origins."),
        ),
        produced_models=("sql-target-source-mapping/v2",),
        capabilities=("common.sql-target-source-mapping", "common.sql-target-value-source-mapping", "common.sql-relation-materialization", "common.sql-workflow-dependency"),
        materialized_marts=("sql-observed-relation-materialization", "sql-observed-workflow-dependency", "sql-target-source-mapping", "sql-target-value-source-mapping"),
        implementation_refs=("knowledge_layer_core.sql_target_source_mapping_builder.build_sql_target_source_mapping_knowledge_layer",),
        current_inputs=("knowledge_layer_sql/v2 plus optional model-storage-semantics/v1",),
        runtime_handler_id="sql-target-source-mapping",
        notes=(
            "Raw recursive SQL origins are preserved separately from semantically normalised value origins.",
            "Storage-key semantic collapse requires structured SQL expression-path evidence plus exact observed storage parent-key evidence; unresolved cases remain explicit gaps.",
            "No staging-name, semantic-role, Gold-data, fuzzy class/table or API-side lineage heuristics are used.",
        ),
    ),

    MaterializationDefinition(
        materialization_id="cross-artifact-data-model-mapping",
        lifecycle="current_typed_klc_composition",
        scope="workspace",
        definition="Compose logical/storage identities with observed SQL physical relations and the declared physical model using explicit, provenance-preserving identity rules.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("logical-storage-model-mapping", "logical-storage-model-mapping/v2", source_materialization_id="logical-storage-mapping", purpose="Logical objects bound to observed storage identities."),
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Effective logical fields used for exact source-column correspondence."),
            _knowledge_model("sql-observed-data-usage", "knowledge_layer_sql/v2", source_materialization_id="sql-analysis", purpose="Observed SQL relations, writes and resolved workflow bindings."),
            _knowledge_model("physical-data-model", "knowledge_layer_physical_model/v1", source_materialization_id="physical-model", purpose="Declared physical tables and columns."),
        ),
        produced_models=("cross-artifact-data-model-mapping/v6",),
        capabilities=("common.cross-artifact-data-model-mapping", "common.storage-sql-correspondence", "common.logical-field-sql-usage", "common.workflow-dependency", "common.relation-materialization", "common.value-origin-physical-lineage", "common.sql-target-source-mapping", "common.workflow-projection-physical-correspondence", "common.sql-physical-correspondence"),
        materialized_marts=("cross-artifact-storage-sql-mapping", "cross-artifact-logical-field-sql-usage", "cross-artifact-relation-materialization", "cross-artifact-workflow-dependency", "cross-artifact-value-origin-physical-lineage", "cross-artifact-target-source-mapping", "cross-artifact-workflow-projection-physical-mapping", "cross-artifact-sql-physical-mapping"),
        implementation_refs=("knowledge_layer_core.cross_artifact_data_model_builder.build_cross_artifact_data_model_mapping_knowledge_layer",),
        current_inputs=("logical-storage-model-mapping/v2 + code-declared-data-model/v1 + knowledge_layer_sql/v2 + knowledge_layer_physical_model/v1",),
        runtime_handler_id="cross-artifact-data-model-mapping",
        notes=(
            "Storage-to-SQL correspondence is knowledge-level derived identity, not Core evidence.",
            "SQL-to-PDM correspondence requires a unique exact PDM table code; unresolved or ambiguous names are not silently matched.",
            "No UCP or datamart-specific class/table names are encoded in the materialization.",
        ),
    ),

    MaterializationDefinition(
        materialization_id="data-model-attribute-extension-context",
        lifecycle="current_typed_klc_composition",
        scope="workspace",
        definition="Compose declared relationships, storage-key semantics, cross-artifact SQL/PDM correspondence and observed SQL anchors into agent-ready technical join semantics for extending existing data products without generating SQL or business meaning.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Declared source/target relationship identity."),
            _knowledge_model("model-storage-semantics", "model-storage-semantics/v1", source_materialization_id="model-storage-semantics", purpose="Observed storage keys and reference-value derivations."),
            _knowledge_model("logical-storage-model-mapping", "logical-storage-model-mapping/v2", source_materialization_id="logical-storage-mapping", purpose="Exact logical-to-storage relationship binding and collection lineage."),
            _knowledge_model("cross-artifact-data-model-mapping", "cross-artifact-data-model-mapping/v6", source_materialization_id="cross-artifact-data-model-mapping", purpose="Observed storage-to-SQL, logical-field-to-SQL and SQL-to-PDM correspondence."),
            _knowledge_model("sql-observed-data-usage", "knowledge_layer_sql/v2", source_materialization_id="sql-analysis", purpose="Observed SQL projections and joins used only as execution-context anchors."),
        ),
        produced_models=("data-model-attribute-extension-context/v1",),
        capabilities=("common.data-model-attribute-extension-context", "common.data-model-agent-join-semantics", "common.data-model-sql-anchor-context"),
        materialized_marts=("data-model-attribute-object-anchor", "data-model-attribute-join-semantics", "data-model-attribute-extension-gap"),
        implementation_refs=("knowledge_layer_core.attribute_extension_context_builder.build_attribute_extension_context_knowledge_layer",),
        current_inputs=("code-declared-data-model/v1 + model-storage-semantics/v1 + logical-storage-model-mapping/v2 + cross-artifact-data-model-mapping/v6 + knowledge_layer_sql/v2",),
        runtime_handler_id="data-model-attribute-extension-context",
        notes=(
            "Join methods classify technical representation from observed evidence; they are not generated SQL and do not imply business semantics.",
            "Physical names come from cross-artifact/PDM correspondence; FQCN-derived table names are not invented.",
            "Polymorphic/reference collections remain explicitly unresolved for SQL until subtype and physical representation evidence is sufficient.",
        ),
    ),

    MaterializationDefinition(
        materialization_id="effective-data-model",
        lifecycle="current_typed_klc_composition",
        scope="repository_or_workspace",
        definition="Build an explicit cross-layer view from independently materialized code-declared, physical and mapping knowledge while preserving the origin and semantics of every layer.",
        required_evidence=(),
        optional_evidence=(),
        required_knowledge_models=(
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Declared logical model layer."),
            _knowledge_model("physical-data-model", "knowledge_layer_physical_model/v1", source_materialization_id="physical-model", purpose="Physical model layer."),
            _knowledge_model("logical-physical-model-mapping", "logical-physical-model-mapping/v1", source_materialization_id="logical-physical-mapping", purpose="Evidence-backed correspondence between logical and physical layers."),
        ),
        optional_knowledge_models=(
            _knowledge_model("sql-observed-data-usage", "knowledge_layer_sql/v2", source_materialization_id="sql-analysis", purpose="Observed SQL usage kept distinct from declared constraints."),
            _knowledge_model("observed-storage-usage", "observed-storage-usage/v1", source_materialization_id="observed-storage-usage", purpose="Observed code-level storage use."),
        ),
        produced_models=("effective-data-model/v1", "model-domain-cluster-view/v1"),
        capabilities=("common.effective-data-model", "common.cross-layer-data-model"),
        materialized_marts=("effective-data-model", "model-domains", "entity-clusters", "cross-layer-model-coverage"),
        implementation_refs=("knowledge_layer_core.effective_data_model_builder.build_effective_data_model_knowledge_layer",),
        current_inputs=("code-declared-data-model/v1, knowledge_layer_physical_model/v1 and logical-physical-model-mapping/v1",),
        runtime_handler_id="effective-data-model",
        evidence_gaps=(
            "Persistence inheritance mappings remain an explicit gap where inherited fields cannot be attached to a different physical owner.",
        ),
        notes=("Logical objects remain primary; unmatched physical objects are published separately and are never promoted to logical entities.",),
    ),


    MaterializationDefinition(
        materialization_id="model-storage-semantics",
        lifecycle="current_typed_input",
        scope="repository_or_workspace",
        definition="Materialize observed model-to-storage record identities, references and composed key lineage without physical-table, PK/FK or business interpretation.",
        required_evidence=(
            _evidence("model-storage-evidence", "model-storage-evidence/v1", purpose="Observed storage records, reference values and key-expression lineage from framework API bindings."),
        ),
        optional_evidence=(),
        produced_models=("model-storage-semantics/v1",),
        capabilities=("common.model-storage-semantics", "common.storage-identities", "common.storage-reference-lineage"),
        materialized_marts=("model-storage-records", "model-storage-references", "model-storage-key-lineage"),
        implementation_refs=("knowledge_layer_core.model_storage_semantics_builder.build_model_storage_semantics_knowledge_layer",),
        current_inputs=("model-storage-evidence/v1 generic Core evidence artifact",),
        runtime_handler_id="model-storage-semantics",
        notes=("Framework interpreter provenance is retained; KLC does not normalize aliases to SQL/PDM names in this materialization.",),
    ),


    MaterializationDefinition(
        materialization_id="observed-storage-usage",
        lifecycle="current_typed_input",
        scope="repository_or_workspace",
        definition="Materialize observed code-level reads, writes and storage access without reclassifying them as declared model or persistence mapping.",
        required_evidence=(
            _evidence("storage-usage-evidence", "storage-usage-evidence/v1", purpose="Observed reads, writes, storage calls and referenced objects or fields."),
        ),
        optional_evidence=(
            _evidence("model-evidence-gap", "model-evidence-gap/v1", purpose="Unresolved storage targets and incomplete value bindings."),
        ),
        optional_knowledge_models=(
            _knowledge_model("code-declared-data-model", "code-declared-data-model/v1", source_materialization_id="code-declared-data-model", purpose="Optional correspondence to code-declared objects."),
            _knowledge_model("physical-data-model", "knowledge_layer_physical_model/v1", source_materialization_id="physical-model", purpose="Optional correspondence to physical objects."),
        ),
        produced_models=("observed-storage-usage/v1",),
        capabilities=("common.observed-storage-usage", "common.storage-read-write-inventory", "common.storage-access-gaps"),
        materialized_marts=("observed-storage-reads", "observed-storage-writes", "observed-storage-access-gaps"),
        implementation_refs=("knowledge_layer_core.observed_storage_usage_builder.build_observed_storage_usage_knowledge_layer",),
        current_inputs=("storage-usage-evidence/v1 generic Core evidence artifact",),
        runtime_handler_id="observed-storage-usage",
    ),

)




def build_materialization_contract_catalog(core_target_contracts: Mapping[str, Any]) -> dict[str, Any]:
    """Build the deterministic catalog of installed KLC materializations.

    The catalog describes the current typed materialization boundary only. Historical
    Core→KLC migration planning is intentionally not part of the installed runtime contract.
    """
    _validate_core_target_contracts(core_target_contracts)
    materializations = [item.to_dict() for item in CURRENT_MATERIALIZATIONS]
    ids = [item["materialization_id"] for item in materializations]
    if len(set(ids)) != len(ids):
        raise ValueError("materialization_id values must be unique")

    registered_ids = sorted(
        item.materialization_id for item in CURRENT_MATERIALIZATIONS if item.runtime_handler_id is not None
    )
    unregistered_ids = sorted(
        item.materialization_id for item in CURRENT_MATERIALIZATIONS if item.runtime_handler_id is None
    )
    payload: dict[str, Any] = {
        "schema_version": MATERIALIZATION_CATALOG_SCHEMA_VERSION,
        "klc_version": __version__,
        "execution_effect": "read_only_contract_catalog",
        "runtime_contract": {
            "contract_id": "knowledge_materialization_runtime/v1",
            "request_schema_version": "knowledge_materialization_request/v1",
            "result_schema_version": "knowledge_materialization_execution_result/v1",
            "generic_entrypoint": "knowledge_layer_core.materialization_runtime.materialize",
            "registered_materialization_ids": registered_ids,
            "dispatch_rule": "materialization_id_to_klc_owned_handler",
            "runner_policy": "Runner resolves inputs and records lifecycle; it never selects a materializer implementation function.",
        },
        "purpose": "KLC-owned contracts for deterministic knowledge materialization from typed Core evidence and KLC knowledge artifacts.",
        "architecture_goal": "Core produces independent typed evidence; KLC composes evidence into knowledge; Runner orchestrates execution without defining evidence semantics.",
        "source": {
            "core_target_contracts_schema_version": core_target_contracts.get("schema_version"),
            "core_target_contracts_fingerprint": core_target_contracts.get("contracts_fingerprint"),
            "core_version": core_target_contracts.get("core_version"),
        },
        "contract": {
            "contract_id": MATERIALIZATION_CONTRACT_SCHEMA_VERSION,
            "owner": "knowledge-layer-core",
            "definition": "Deterministic KLC composition from declared required and optional typed evidence or KLC model artifacts into versioned knowledge models.",
            "invariants": [
                "Inputs are selected by artifact_kind and schema_version, never by task_id or profile_id.",
                "Required evidence is explicit; missing required evidence produces failure or a declared materialization gap.",
                "Optional evidence enriches results but absence is reflected in coverage.",
                "Unsupported evidence schema versions fail explicitly; no hidden fallback or reinterpretation.",
                "Outputs include coverage, diagnostics, provenance and a deterministic content fingerprint.",
                "KLC-to-KLC materialization dependencies are explicit versioned model inputs and do not create Core analyzer dependencies.",
                "Different evidence source families produce distinct knowledge; no source is silently substituted for another.",
                "Composite knowledge is built only from explicit KLC model dependencies and preserves each source layer.",
                "Published capabilities come from completed materializations, not merely requested work.",
            ],
            "required_fields": [
                "materialization_id", "required_evidence", "optional_evidence", "required_knowledge_models",
                "optional_knowledge_models", "produced_models", "capabilities", "coverage_policy", "diagnostics_policy", "provenance_policy",
            ],
        },
        "evidence_routing_contract": {
            "contract_id": EVIDENCE_ROUTING_CONTRACT_ID,
            "semantic_identity": ["artifact_kind", "schema_version"],
            "execution_provenance_only_fields": ["process_id", "retry_ordinal"],
            "forbidden_meaning_selection": ["task_id", "suite_id", "profile_id", "report_profile_id", "directory_name"],
        },
        "materializations": materializations,
        "current_state": {
            "runtime_registered_materialization_ids": registered_ids,
            "runtime_unregistered_materialization_ids": unregistered_ids,
        },
        "summary": {
            "materialization_count": len(materializations),
            "runtime_registered_materialization_count": len(registered_ids),
            "runtime_unregistered_materialization_count": len(unregistered_ids),
        },
        "next_steps": [
            "Keep parked portfolio topology outside the installed runtime until the Islands track resumes.",
            "Use typed artifact and KLC model routing for every installed runtime materialization.",
            "Treat an unregistered materialization as unavailable instead of routing through an older implementation path.",
        ],
    }
    payload["catalog_fingerprint"] = _fingerprint(payload)
    return payload


def write_materialization_contract_catalog(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def render_materialization_contract_catalog_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    state = payload.get("current_state") or {}
    lines = [
        "# Knowledge Materialization Contracts v3",
        "",
        f"- KLC: `{payload.get('klc_version')}`",
        f"- Schema: `{payload.get('schema_version')}`",
        f"- Fingerprint: `{payload.get('catalog_fingerprint')}`",
        "",
        "## Architecture",
        "",
        "- Core publishes independent typed evidence artifacts.",
        "- KLC materializations declare required/optional evidence and KLC-model dependencies.",
        "- Evidence meaning is selected by `artifact_kind + schema_version`.",
        "- Task/Suite/profile selectors are not runtime inputs or query selectors.",
        "- Historical Core→KLC migration planning is not part of the installed runtime contract.",
        "",
        "## Current state",
        "",
        f"- Materializations: **{summary.get('materialization_count', 0)}**",
        f"- Runtime registered: **{summary.get('runtime_registered_materialization_count', 0)}**",
        f"- Runtime unavailable/unregistered: **{summary.get('runtime_unregistered_materialization_count', 0)}**",
    ]
    for item in state.get("runtime_unregistered_materialization_ids") or []:
        lines.append(f"  - `{item}`")
    lines.extend(["", "## Materialization contracts", ""])
    for item in payload.get("materializations") or []:
        required = ", ".join(
            f"`{entry.get('artifact_kind')}`" for entry in (item.get("input_contract") or {}).get("required_evidence") or []
        ) or "—"
        optional = ", ".join(
            f"`{entry.get('artifact_kind')}`" for entry in (item.get("input_contract") or {}).get("optional_evidence") or []
        ) or "—"
        required_models = ", ".join(
            f"`{entry.get('model_kind')}` from `{entry.get('source_materialization_id')}`"
            for entry in (item.get("input_contract") or {}).get("required_knowledge_models") or []
        ) or "—"
        optional_models = ", ".join(
            f"`{entry.get('model_kind')}` from `{entry.get('source_materialization_id')}`"
            for entry in (item.get("input_contract") or {}).get("optional_knowledge_models") or []
        ) or "—"
        models = ", ".join(f"`{model}`" for model in (item.get("outputs") or {}).get("models") or []) or "—"
        runtime = ((item.get("current_implementation") or {}).get("runtime") or {})
        lines.extend([
            f"### `{item.get('materialization_id')}`",
            "",
            f"- Lifecycle: `{item.get('lifecycle')}`",
            f"- Scope: `{item.get('scope')}`",
            f"- Runtime registered: `{runtime.get('registered')}`",
            f"- Required evidence: {required}",
            f"- Optional evidence: {optional}",
            f"- Required KLC models: {required_models}",
            f"- Optional KLC models: {optional_models}",
            f"- Produced models: {models}",
            "",
        ])
    lines.extend(["## Next steps", ""])
    for item in payload.get("next_steps") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_materialization_contract_catalog_markdown(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_materialization_contract_catalog_markdown(payload), encoding="utf-8")
    return target


def _read_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {source}")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build read-only KLC knowledge materialization contracts from official Core target contracts."
    )
    parser.add_argument("--core-target-contracts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)

    source = _read_json_object(args.core_target_contracts)
    payload = build_materialization_contract_catalog(source)
    output = write_materialization_contract_catalog(args.output, payload)
    if args.markdown:
        write_materialization_contract_catalog_markdown(args.markdown, payload)
    print(json.dumps({
        "schema_version": payload["schema_version"],
        "klc_version": payload["klc_version"],
        "catalog_fingerprint": payload["catalog_fingerprint"],
        "materialization_count": payload["summary"]["materialization_count"],
        "runtime_registered_materialization_count": payload["summary"]["runtime_registered_materialization_count"],
        "runtime_unregistered_materialization_count": payload["summary"]["runtime_unregistered_materialization_count"],
        "output": str(output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
