"""Public request and response models for the canonical Knowledge API v1.

The contract is producer-neutral.  It intentionally models published knowledge and
its provenance, not orchestration jobs, UI state, or pipeline execution controls.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

KNOWLEDGE_API_SCHEMA_VERSION = "knowledge_api/v1"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=240,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ArtifactUri = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ApiError(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    code: Identifier
    message: NonEmptyText
    details: dict[str, JsonValue] = Field(default_factory=dict)
    request_id: str | None = None


class PageMeta(ContractModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=500)
    total: int = Field(ge=0)


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    status: HealthStatus
    service: str = "knowledge-api"
    version: str


class VersionResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    service: str = "knowledge-api"
    service_version: str
    api_version: str = "v1"
    generated_at: datetime


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class Capability(ContractModel):
    id: Identifier
    status: CapabilityStatus
    description: NonEmptyText
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CapabilitiesResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    capabilities: list[Capability]


class SystemCreateRequest(ContractModel):
    system_id: Identifier
    display_name: NonEmptyText
    description: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SystemUpdateRequest(ContractModel):
    display_name: NonEmptyText | None = None
    description: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "SystemUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("system update must include at least one field")
        if self.display_name is None and "display_name" in self.model_fields_set:
            raise ValueError("display_name cannot be null")
        return self


class SystemDeleteResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    deleted_revision_count: int = Field(ge=0)


class ArtifactStoreGcMode(StrEnum):
    PLAN = "plan"
    SWEEP = "sweep"


class ArtifactStoreGcRequest(ContractModel):
    """Operational GC request; retention policy stays outside AISL semantics."""

    mode: ArtifactStoreGcMode = ArtifactStoreGcMode.PLAN
    grace_period_seconds: int = Field(ge=0)
    confirm_delete_unreferenced: bool = False
    max_details: int = Field(default=100, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_destructive_confirmation(self) -> "ArtifactStoreGcRequest":
        if self.mode == ArtifactStoreGcMode.SWEEP and not self.confirm_delete_unreferenced:
            raise ValueError("sweep mode requires confirm_delete_unreferenced=true")
        return self


class ArtifactStoreGcResponse(ContractModel):
    schema_version: str = "aisl_artifact_store_gc/v1"
    mode: ArtifactStoreGcMode
    grace_period_seconds: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime
    retained_revision_count: int = Field(ge=0)
    reachable_digest_count: int = Field(ge=0)
    store_blob_count: int = Field(ge=0)
    referenced_blob_count: int = Field(ge=0)
    unreferenced_blob_count: int = Field(ge=0)
    eligible_blob_count: int = Field(ge=0)
    deleted_blob_count: int = Field(ge=0)
    young_unreferenced_blob_count: int = Field(ge=0)
    missing_referenced_blob_count: int = Field(ge=0)
    staging_file_count: int = Field(ge=0)
    eligible_staging_file_count: int = Field(ge=0)
    deleted_staging_file_count: int = Field(ge=0)
    unmanaged_entry_count: int = Field(ge=0)
    eligible_blob_sha256: list[Sha256Digest] = Field(default_factory=list)
    missing_referenced_sha256: list[Sha256Digest] = Field(default_factory=list)
    eligible_staging_files: list[str] = Field(default_factory=list)
    unmanaged_entries: list[str] = Field(default_factory=list)
    details_truncated: bool = False


class SystemSummary(ContractModel):
    system_id: Identifier
    display_name: NonEmptyText
    description: str | None = None
    active_revision_id: Identifier | None = None
    revision_count: int = Field(0, ge=0)
    created_at: datetime
    updated_at: datetime


class SystemDetails(SystemSummary):
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SystemListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    items: list[SystemSummary]
    page: PageMeta


class KnowledgeExecutionSummary(ContractModel):
    schema_version: Literal["knowledge_execution_result/v2"] = "knowledge_execution_result/v2"
    status: Literal["completed"] = "completed"
    runner_version: NonEmptyText
    result_fingerprint: Sha256Digest
    plan_fingerprint: Sha256Digest
    knowledge_profile_id: Identifier
    scope_kind: Identifier
    scope_id: Identifier
    started_at: datetime
    completed_at: datetime
    semantic_policy: dict[str, JsonValue] = Field(default_factory=dict)


class PublishedArtifact(ContractModel):
    uri: ArtifactUri
    sha256: Sha256Digest
    media_type: NonEmptyText
    schema_version: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    filename: str | None = None

    @model_validator(mode="after")
    def validate_uri_scheme(self) -> "PublishedArtifact":
        if "://" not in self.uri:
            raise ValueError("artifact uri must be absolute and include a URI scheme")
        return self


class ProductOriginKind(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"


class ProductPhysicalArtifact(PublishedArtifact):
    """One immutable physical member of a published KnowledgeProduct.

    ``role`` is product-local addressing metadata (for example ``database``,
    ``manifest``, ``descriptor`` or ``fact:sql_statement``). Physical location
    and filename are not semantic product identity.
    """

    role: Identifier


class PublishedKnowledgeArtifact(ContractModel):
    """One published typed KnowledgeProduct in an immutable AISL revision.

    ``origin_kind`` identifies how knowledge was produced; it does not replace
    item-level confidence/ambiguity semantics owned by the typed product.
    ``product_slot_id`` is the generic copy-on-write replacement slot.
    ``physical_artifacts`` is the producer-neutral immutable byte set for the
    logical product. ``source_materialization_id`` remains derived-producer
    provenance only.
    """

    artifact_id: Identifier
    model_kind: Identifier
    schema_version: NonEmptyText
    product_slot_id: Identifier
    origin_kind: ProductOriginKind
    producer_ref: NonEmptyText
    producer_contract_ref: NonEmptyText
    content_fingerprint: Sha256Digest
    source_materialization_id: Identifier | None = None
    physical_artifacts: list[ProductPhysicalArtifact] = Field(min_length=1)
    capabilities: list[Identifier] = Field(default_factory=list)
    coverage: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    exact_dependency_product_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_physical_representation(self) -> "PublishedKnowledgeArtifact":
        roles = [str(item.role) for item in self.physical_artifacts]
        if len(roles) != len(set(roles)):
            raise ValueError("physical_artifacts roles must be unique within a KnowledgeProduct")
        if self.origin_kind == ProductOriginKind.DERIVED:
            if self.source_materialization_id is None:
                raise ValueError("derived KnowledgeProduct requires source_materialization_id provenance")
            missing = {"database", "manifest"} - set(roles)
            if missing:
                raise ValueError("derived KnowledgeProduct requires database and manifest physical roles")
        elif self.origin_kind == ProductOriginKind.OBSERVED:
            if "descriptor" not in roles:
                raise ValueError("observed KnowledgeProduct requires a descriptor physical role")
            if self.source_materialization_id is not None:
                raise ValueError("observed KnowledgeProduct must not claim KLC source_materialization_id")
        if len(self.exact_dependency_product_ids) != len(set(self.exact_dependency_product_ids)):
            raise ValueError("exact_dependency_product_ids must be unique")
        if self.artifact_id in self.exact_dependency_product_ids:
            raise ValueError("KnowledgeProduct cannot depend on itself")
        return self


class RevisionCreateRequest(ContractModel):
    execution_result: PublishedArtifact
    base_revision_id: Identifier | None = None
    activate: bool = True
    labels: list[Identifier] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifact_media_types(self) -> "RevisionCreateRequest":
        if self.execution_result.media_type.lower() not in {"application/json", "text/json"}:
            raise ValueError("execution_result media_type must be application/json")
        if self.execution_result.schema_version != "knowledge_execution_result/v2":
            raise ValueError("execution_result schema_version must be knowledge_execution_result/v2")
        return self


class RevisionState(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"


class SystemRevision(ContractModel):
    system_id: Identifier
    revision_id: Identifier
    base_revision_id: Identifier | None = None
    ordinal: int = Field(ge=1)
    state: RevisionState
    created_at: datetime
    execution: KnowledgeExecutionSummary
    execution_result: PublishedArtifact
    knowledge_artifacts: list[PublishedKnowledgeArtifact]
    capabilities: list[Identifier] = Field(default_factory=list)
    labels: list[Identifier] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RevisionCreateResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    revision: SystemRevision


class RevisionListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    items: list[SystemRevision]
    page: PageMeta


class KnowledgeArtifactListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    items: list[PublishedKnowledgeArtifact]
    page: PageMeta


class KnowledgeArtifactDetailResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    artifact: PublishedKnowledgeArtifact


class RevisionCapabilitiesResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    capabilities: list[Identifier]


class DeclaredDataField(ContractModel):
    effective_field_occurrence_id: NonEmptyText
    field_occurrence_id: NonEmptyText
    declaring_type_occurrence_id: NonEmptyText
    name: NonEmptyText
    inherited_depth: int = Field(ge=0)
    is_inherited: bool
    derivation_kind: NonEmptyText
    declared_type_expression: NonEmptyText
    normalized_type_expression: str | None = None
    is_static: bool
    is_final: bool
    documentation: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    annotations: list[dict[str, JsonValue]] = Field(default_factory=list)


class DeclaredDataRelationship(ContractModel):
    relationship_id: NonEmptyText
    field_occurrence_id: NonEmptyText
    source_field: NonEmptyText
    declared_type_expression: NonEmptyText
    target_type_occurrence_id: NonEmptyText
    target_fqcn: NonEmptyText
    target_name: NonEmptyText
    relationship_kind: NonEmptyText
    resolution_status: NonEmptyText
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)
    source_field_annotations: list[dict[str, JsonValue]] = Field(default_factory=list)
    is_inherited: bool = False
    inherited_depth: int = Field(0, ge=0)
    cardinality_hint: str | None = None
    cardinality_basis: str | None = None


class DeclaredDataInheritance(ContractModel):
    inheritance_occurrence_id: NonEmptyText
    relation_kind: NonEmptyText
    declared_supertype_expression: NonEmptyText
    resolution_status: NonEmptyText
    resolved_supertype_occurrence_id: str | None = None
    resolved_fqcn: str | None = None
    candidate_fqcns: list[JsonValue] = Field(default_factory=list)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)


class DeclaredDataMatchEvidence(ContractModel):
    target_kind: NonEmptyText
    match_kind: NonEmptyText
    score: int = Field(ge=0)
    field_occurrence_id: str | None = None
    effective_field_occurrence_id: str | None = None
    field_name: str | None = None
    declared_type_expression: str | None = None
    documentation: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)
    is_inherited: bool = False
    inherited_depth: int = Field(0, ge=0)
    evidence_role: NonEmptyText


class DeclaredDataBindingExample(ContractModel):
    relationship_id: NonEmptyText
    source_object_id: NonEmptyText
    source_fqcn: NonEmptyText
    source_name: NonEmptyText
    field_occurrence_id: NonEmptyText
    source_field: NonEmptyText
    declared_type_expression: NonEmptyText
    relationship_kind: NonEmptyText
    resolution_status: NonEmptyText
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)


class DeclaredDataBindingSummary(ContractModel):
    incoming_relationship_count: int = Field(ge=0)
    outgoing_relationship_count: int = Field(ge=0)
    has_observed_incoming_binding: bool
    incoming_examples: list[DeclaredDataBindingExample] = Field(default_factory=list)
    incoming_examples_truncated: bool = False


class DeclaredDataObjectSummary(ContractModel):
    object_id: NonEmptyText
    repo_id: NonEmptyText
    fqcn: NonEmptyText
    name: NonEmptyText
    package_name: str | None = None
    type_kind: NonEmptyText
    source_set: str | None = None
    documentation: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)
    annotations: list[dict[str, JsonValue]] = Field(default_factory=list)
    field_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    retrieval_score: int = Field(0, ge=0)
    score_basis: str | None = None
    match_evidence: list[DeclaredDataMatchEvidence] = Field(default_factory=list)
    match_evidence_truncated: bool = False
    binding_summary: DeclaredDataBindingSummary | None = None
    fields: list[DeclaredDataField] | None = None


class DeclaredDataObjectDetail(ContractModel):
    object_id: NonEmptyText
    repo_id: NonEmptyText
    fqcn: NonEmptyText
    name: NonEmptyText
    package_name: str | None = None
    type_kind: NonEmptyText
    source_set: str | None = None
    documentation: dict[str, JsonValue] = Field(default_factory=dict)
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)
    annotations: list[dict[str, JsonValue]] = Field(default_factory=list)
    modifier_tokens: list[JsonValue] = Field(default_factory=list)
    type_parameters: list[JsonValue] = Field(default_factory=list)
    fields: list[DeclaredDataField] = Field(default_factory=list)
    relationships: list[DeclaredDataRelationship] = Field(default_factory=list)
    binding_summary: DeclaredDataBindingSummary | None = None
    inheritance: list[DeclaredDataInheritance] = Field(default_factory=list)


class DeclaredDataModelSummaryResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    declared_model_query_schema_version: str = "code-declared-data-model-query/v2"
    declared_model_schema_version: str = "code-declared-data-model/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    build: dict[str, JsonValue] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    type_annotation_counts: list[dict[str, JsonValue]] = Field(default_factory=list)
    field_annotation_counts: list[dict[str, JsonValue]] = Field(default_factory=list)
    gap_counts: list[dict[str, JsonValue]] = Field(default_factory=list)


class DeclaredDataObjectListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    declared_model_query_schema_version: str = "code-declared-data-model-query/v2"
    declared_model_schema_version: str = "code-declared-data-model/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[DeclaredDataObjectSummary] = Field(default_factory=list)
    page: PageMeta


class DeclaredDataObjectDetailResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    declared_model_query_schema_version: str = "code-declared-data-model-query/v2"
    declared_model_schema_version: str = "code-declared-data-model/v1"
    system_id: Identifier
    revision_id: Identifier
    object: DeclaredDataObjectDetail


class DataModelObjectContextResponse(ContractModel):
    schema_version: str = "data_model_object_context/v2"
    system_id: Identifier
    revision_id: Identifier
    object: dict[str, JsonValue]
    fields: list[dict[str, JsonValue]] = Field(default_factory=list)
    relationships: list[dict[str, JsonValue]] = Field(default_factory=list)
    storage_identities: list[dict[str, JsonValue]] = Field(default_factory=list)
    storage_context: dict[str, JsonValue] = Field(default_factory=dict)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)


class FieldSummary(ContractModel):
    name: NonEmptyText
    type: str | None = None
    description: str | None = None
    nullable: bool | None = None
    inherited: bool = False


class TableSummary(ContractModel):
    table_id: NonEmptyText
    table_name: NonEmptyText
    table_kind: NonEmptyText
    display_name: str | None = None
    description: str | None = None
    field_count: int = Field(0, ge=0)
    relationship_count: int = Field(0, ge=0)
    fields: list[FieldSummary] | None = None


class TableListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    items: list[TableSummary]
    page: PageMeta


class DataObjectRef(ContractModel):
    id: NonEmptyText
    name: NonEmptyText
    kind: NonEmptyText
    display_name: str | None = None
    description: str | None = None


class TableFieldStorageEvidenceRef(ContractModel):
    evidence_id: str
    repo_id: str
    path: str
    line_start: int | None = None
    line_end: int | None = None
    extractor: str | None = None
    maturity: str
    role: str | None = None


class TableFieldStorageObservation(ContractModel):
    physical_field_name: str
    operation: str
    object_alias: str
    value_expression: str | None = None
    converter_owner_fqcn: str | None = None
    converter_method: str | None = None
    call_observation_id: str | None = None
    match_basis: str
    value_mapping_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[TableFieldStorageEvidenceRef] = Field(default_factory=list)


class TableField(ContractModel):
    name: NonEmptyText
    type: NonEmptyText
    target_object: str | None = None
    display_name: str | None = None
    description: str | None = None
    nullable: bool | None = None
    inherited: bool = False
    storage_observation_count: int = Field(default=0, ge=0)
    storage_observations: list[TableFieldStorageObservation] = Field(default_factory=list)
    storage_observations_truncated: bool = False


class TableKey(ContractModel):
    kind: NonEmptyText
    fields: list[NonEmptyText]
    version_field: str | None = None
    collocation_field: str | None = None
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class RelationshipSource(ContractModel):
    field: NonEmptyText
    inherited: bool = False
    cardinality: NonEmptyText


class RelationshipLogicalIdentity(ContractModel):
    status: NonEmptyText
    fields: list[NonEmptyText] = Field(default_factory=list)
    version_fields: list[NonEmptyText] = Field(default_factory=list)
    collocation_fields: list[NonEmptyText] = Field(default_factory=list)
    classification_basis: NonEmptyText


class RelationshipStorageKeyEvidence(ContractModel):
    storage_reference_id: str | None = None
    storage_lineage_id: str | None = None
    target_alias: str | None = None
    field: str | None = None
    expression: str | None = None
    composed_expression: str | None = None
    expression_tree: dict[str, JsonValue] = Field(default_factory=dict)
    input_symbols: list[str] = Field(default_factory=list)
    parameter_bindings: list[dict[str, JsonValue]] = Field(default_factory=list)
    reference_operation: str | None = None
    value_origin: str | None = None
    value_binding_resolution: str | None = None
    source_operation: str | None = None
    target_converter_operation: str | None = None
    physical_encoding: NonEmptyText
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class RelationshipStorageKey(ContractModel):
    status: NonEmptyText
    fields: list[NonEmptyText] = Field(default_factory=list)
    expressions: list[str] = Field(default_factory=list)
    evidence: list[RelationshipStorageKeyEvidence] = Field(default_factory=list)


class RelationshipTarget(ContractModel):
    object: DataObjectRef
    aliases: list[str] = Field(default_factory=list)
    logical_identity: RelationshipLogicalIdentity
    storage_key: RelationshipStorageKey


class RelationshipTypeEncodingInput(ContractModel):
    source: Literal["target_alias"]
    values: list[str] = Field(default_factory=list)


class RelationshipKeyEncodingInput(ContractModel):
    source: Literal["target_storage_key"]
    fields: list[str] = Field(default_factory=list)


class RelationshipEncodingInputs(ContractModel):
    type_component: RelationshipTypeEncodingInput
    key_component: RelationshipKeyEncodingInput


class RelationshipPhysicalEncoding(ContractModel):
    status: NonEmptyText


class RelationshipReference(ContractModel):
    assignment_operations: list[str] = Field(default_factory=list)
    value_origins: list[str] = Field(default_factory=list)
    encoding_inputs: RelationshipEncodingInputs
    physical_encoding: RelationshipPhysicalEncoding


class RelationshipJoinEndpoint(ContractModel):
    field: str | None = None
    kind: str | None = None
    fields: list[str] = Field(default_factory=list)
    expression: str | None = None
    expressions: list[str] = Field(default_factory=list)
    composed_expression: str | None = None


class RelationshipJoin(ContractModel):
    method: NonEmptyText
    source: RelationshipJoinEndpoint
    target: RelationshipJoinEndpoint
    requires_encoding_interpretation: bool
    physical_join_confirmed: bool
    match_basis: str | None = None
    parent_key_passed: bool | None = None
    collection_membership_semantics: str | None = None


class TableRelationship(ContractModel):
    relationship_id: NonEmptyText
    kind: NonEmptyText
    source: RelationshipSource
    target: RelationshipTarget
    reference: RelationshipReference
    join: RelationshipJoin
    polymorphic_targets: list[DataObjectRef] = Field(default_factory=list)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class CompactDataObjectRef(ContractModel):
    id: NonEmptyText
    name: NonEmptyText
    kind: NonEmptyText


class RelationshipTargetSummary(ContractModel):
    object: CompactDataObjectRef
    aliases: list[NonEmptyText] | None = None


class RelationshipJoinSummary(ContractModel):
    method: NonEmptyText
    source_fields: list[NonEmptyText]
    target_fields: list[NonEmptyText] | None = None
    target_kind: str | None = None
    source_expressions: list[str] | None = None
    target_expressions: list[str] | None = None
    requires_encoding_interpretation: bool
    physical_join_confirmed: bool
    match_basis: str | None = None
    parent_key_passed: bool | None = None
    collection_membership_semantics: str | None = None


class TableRelationshipSummary(ContractModel):
    relationship_id: NonEmptyText
    kind: NonEmptyText
    source_field: NonEmptyText
    cardinality: NonEmptyText
    target: RelationshipTargetSummary
    join: RelationshipJoinSummary
    polymorphic_targets: list[CompactDataObjectRef] | None = None


class RelationshipDetailResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    table_id: NonEmptyText
    relationship: TableRelationship


class AnalysisCoverageLimitation(ContractModel):
    source: NonEmptyText
    status: NonEmptyText
    repo_id: str | None = None
    category: NonEmptyText
    kind: NonEmptyText
    required_for_operation: str | None = None
    count: int = Field(ge=0)


class AnalysisCoverageSummary(ContractModel):
    repository_count: int = Field(ge=0)
    observed_fact_count: int = Field(ge=0)
    known_gap_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    conflicting_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    not_observed_count: int = Field(ge=0)
    requires_interpretation_count: int = Field(ge=0)
    physical_join_observation_count: int = Field(ge=0)


class AnalysisCoverageSourceFacts(ContractModel):
    status: NonEmptyText
    observed_fact_count: int = Field(ge=0)


class AnalysisCoverageDataModel(ContractModel):
    status: NonEmptyText
    relationship_count: int = Field(ge=0)
    unresolved_relationship_candidate_count: int = Field(ge=0)


class AnalysisCoveragePhysicalStorage(ContractModel):
    status: NonEmptyText
    storage_evidence_relationship_count: int = Field(ge=0)
    requires_interpretation_count: int = Field(ge=0)
    physical_join_observation_count: int = Field(ge=0)


class AnalysisCoverageGaps(ContractModel):
    status: NonEmptyText
    known_gap_count: int = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)


class AnalysisCoverageDomains(ContractModel):
    source_facts: AnalysisCoverageSourceFacts
    data_model: AnalysisCoverageDataModel
    physical_storage: AnalysisCoveragePhysicalStorage
    analysis_gaps: AnalysisCoverageGaps


class AnalysisCoverageResponse(ContractModel):
    schema_version: str = "analysis_coverage/v1"
    system_id: Identifier
    revision_id: Identifier
    status: NonEmptyText
    statement: NonEmptyText
    count_basis: NonEmptyText
    summary: AnalysisCoverageSummary
    domains: AnalysisCoverageDomains
    limitations: list[AnalysisCoverageLimitation] = Field(default_factory=list)
    limitations_total_groups: int = Field(ge=0)
    limitations_truncated: bool = False


class AttributePathResolveRequest(ContractModel):
    source: NonEmptyText
    target: str | None = None
    selected_repo_ids: list[Identifier] = Field(min_length=1)
    max_hops: int = Field(20, ge=1, le=100)
    max_paths: int = Field(20, ge=1, le=500)
    max_branching: int = Field(20, ge=1, le=500)
    allowed_edge_kinds: list[str] = Field(default_factory=list)
    minimum_confidence: Literal["unknown", "probable", "confirmed"] = "probable"
    knowledge_view: Literal["strict", "working", "exploratory"] = "working"


class AttributePathResolveResponse(ContractModel):
    schema_version: str = "knowledge_attribute_path_query/v1"
    system_id: Identifier
    revision_id: Identifier
    artifact_id: Identifier
    source_materialization_id: Identifier
    enriched_cross_repository: bool
    result: dict[str, JsonValue]


class TableDetailResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    workspace_id: str | None = None
    build_id: str | None = None
    generated_at: datetime | None = None
    object: DataObjectRef
    fields: list[TableField] = Field(default_factory=list)
    keys: list[TableKey] = Field(default_factory=list)
    relationships: list[TableRelationshipSummary] = Field(default_factory=list)
    embedded_objects: list[dict[str, Any]] = Field(default_factory=list)
    relationship_candidate_count: int = Field(0, ge=0)
    indexes: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    partitioning: list[dict[str, Any]] = Field(default_factory=list)
    triggers: list[dict[str, Any]] = Field(default_factory=list)


class PhysicalModelSource(ContractModel):
    physical_model_source_id: Identifier
    manifest_path: str | None = None
    source_schema_version: NonEmptyText
    content_fingerprint: NonEmptyText
    core_version: str | None = None
    source_file: str | None = None
    source_sha256: str | None = None
    model_object_id: str | None = None
    model_name: str | None = None
    model_code: str | None = None
    powerdesigner_version: str | None = None
    powerdesigner_target: str | None = None
    coverage_status: NonEmptyText
    gap_count: int = Field(ge=0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class PhysicalModelSummaryResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    sources: list[PhysicalModelSource] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    relationship_resolution: dict[str, int] = Field(default_factory=dict)
    key_kinds: dict[str, int] = Field(default_factory=dict)
    gap_kinds: dict[str, int] = Field(default_factory=dict)


class PhysicalModelColumn(ContractModel):
    physical_model_column_id: Identifier
    physical_model_table_id: Identifier | None = None
    physical_model_source_id: Identifier
    pdm_object_id: str | None = None
    object_uuid: str | None = None
    ordinal: int | None = Field(default=None, ge=0)
    column_name: str | None = None
    column_code: str | None = None
    data_type: str | None = None
    length: int | None = Field(default=None, ge=0)
    precision: int | None = Field(default=None, ge=0)
    mandatory: bool | None = None
    default_value: str | None = None
    comment: str | None = None
    domain_ref: str | None = None
    source_file: str | None = None
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class PhysicalModelKey(ContractModel):
    physical_model_key_id: Identifier
    physical_model_table_id: Identifier | None = None
    physical_model_source_id: Identifier
    pdm_object_id: str | None = None
    object_uuid: str | None = None
    key_name: str | None = None
    key_code: str | None = None
    key_kind: str | None = None
    column_pdm_ids: list[str] = Field(default_factory=list)
    column_codes: list[str] = Field(default_factory=list)
    unresolved_column_refs: list[str] = Field(default_factory=list)
    source_file: str | None = None
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class PhysicalModelRelationship(ContractModel):
    physical_model_relationship_id: Identifier
    physical_model_source_id: Identifier
    pdm_object_id: str | None = None
    object_uuid: str | None = None
    relationship_name: str | None = None
    relationship_code: str | None = None
    cardinality: str | None = None
    parent_table_ref: str | None = None
    parent_table_id: Identifier | None = None
    parent_table_code: str | None = None
    parent_table_name: str | None = None
    child_table_ref: str | None = None
    child_table_id: Identifier | None = None
    child_table_code: str | None = None
    child_table_name: str | None = None
    parent_key_ref: str | None = None
    parent_key_id: Identifier | None = None
    joins: list[dict[str, JsonValue]] = Field(default_factory=list)
    resolution_status: str | None = None
    source_file: str | None = None
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class PhysicalModelGap(ContractModel):
    physical_model_gap_id: Identifier
    physical_model_source_id: Identifier
    gap_kind: str | None = None
    owner_pdm_object_id: str | None = None
    unresolved_ref: str | None = None
    message: str | None = None


class PhysicalModelTableSummary(ContractModel):
    physical_model_table_id: Identifier
    physical_model_source_id: Identifier
    pdm_object_id: str | None = None
    object_uuid: str | None = None
    model_name: str | None = None
    model_code: str | None = None
    package_path: list[str] = Field(default_factory=list)
    package_code_path: list[str] = Field(default_factory=list)
    table_name: str | None = None
    table_code: str | None = None
    logical_identity: str | None = None
    comment: str | None = None
    description: str | None = None
    stereotype: str | None = None
    dimensional_type: str | None = None
    owner_ref: str | None = None
    column_count: int | None = Field(default=None, ge=0)
    key_count: int | None = Field(default=None, ge=0)
    inbound_relationship_count: int = Field(default=0, ge=0)
    outbound_relationship_count: int = Field(default=0, ge=0)
    source_file: str | None = None
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    columns: list[PhysicalModelColumn] | None = None


class PhysicalModelTableListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[PhysicalModelTableSummary] = Field(default_factory=list)
    page: PageMeta


class PhysicalModelTableDetailResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    table: PhysicalModelTableSummary
    columns: list[PhysicalModelColumn] = Field(default_factory=list)
    keys: list[PhysicalModelKey] = Field(default_factory=list)
    relationships: list[PhysicalModelRelationship] = Field(default_factory=list)


class PhysicalModelColumnListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[PhysicalModelColumn] = Field(default_factory=list)
    page: PageMeta


class PhysicalModelKeyListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[PhysicalModelKey] = Field(default_factory=list)
    page: PageMeta


class PhysicalModelRelationshipListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[PhysicalModelRelationship] = Field(default_factory=list)
    page: PageMeta


class PhysicalModelGapListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    physical_model_schema_version: str = "physical-model-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[PhysicalModelGap] = Field(default_factory=list)
    page: PageMeta


class SqlEvidenceRef(ContractModel):
    file: NonEmptyText
    line_start: int | None = Field(default=None, ge=1)
    usage_role: str | None = None
    query_id: str | None = None
    scope_id: str | None = None
    evidence_id: str | None = None


class SqlRelationFieldSummary(ContractModel):
    name: NonEmptyText
    usage_roles: list[NonEmptyText] = Field(default_factory=list)
    resolution_statuses: list[NonEmptyText] = Field(default_factory=list)
    resolution_bases: list[NonEmptyText] = Field(default_factory=list)
    occurrence_count: int = Field(ge=0)
    statement_count: int = Field(ge=0)
    evidence_count: int = Field(default=0, ge=0)
    evidence_count_by_role: dict[str, int] = Field(default_factory=dict)
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)
    evidence_truncated: bool = False


class SqlRelationSummary(ContractModel):
    relation_id: NonEmptyText
    repo_id: Identifier
    relation_kind: NonEmptyText
    relation_identity: NonEmptyText
    template_name: str | None = None
    logical_name: str | None = None
    resolved_names: list[str] = Field(default_factory=list)
    usage_roles: list[NonEmptyText] = Field(default_factory=list)
    definition_statuses: list[NonEmptyText] = Field(default_factory=list)
    semantic_role: NonEmptyText
    classification_status: NonEmptyText
    hidden_by_default: bool
    classification_reasons: list[NonEmptyText] = Field(default_factory=list)
    write_occurrence_count: int = Field(ge=0)
    downstream_target_count: int = Field(ge=0)
    owned_namespace: bool
    technical_name_signal: bool
    occurrence_count: int = Field(ge=0)
    statement_count: int = Field(ge=0)
    field_count: int | None = Field(default=None, ge=0)
    fields: list[SqlRelationFieldSummary] | None = None
    evidence_count: int = Field(default=0, ge=0)
    evidence_count_by_role: dict[str, int] = Field(default_factory=dict)
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)
    evidence_truncated: bool = False


class SqlColumnUsageContextUsage(ContractModel):
    sql_column_usage_id: NonEmptyText
    repo_id: Identifier
    query_id: NonEmptyText
    scope_id: NonEmptyText
    file: NonEmptyText
    line_start: int | None = Field(default=None, ge=1)
    column_name: NonEmptyText
    column_ordinal: int | None = Field(default=None, ge=0)
    usage_role: NonEmptyText
    table_or_alias: str | None = None
    relation_id: str | None = None
    relation_kind: str | None = None
    relation_name: str | None = None
    resolution_status: NonEmptyText
    resolution_basis: str | None = None
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlStatementContext(ContractModel):
    sql_statement_id: NonEmptyText
    query_id: NonEmptyText
    file: NonEmptyText
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    operation: str | None = None
    statement_type: str | None = None
    target_relation_name: str | None = None
    unit_kind: str | None = None
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlSelectScopeContext(ContractModel):
    sql_select_scope_id: NonEmptyText
    query_id: NonEmptyText
    file: NonEmptyText
    line_start: int | None = Field(default=None, ge=1)
    parent_scope_id: str | None = None
    scope_kind: str | None = None
    scope_name: str | None = None
    relation_count: int = Field(default=0, ge=0)
    projection_count: int = Field(default=0, ge=0)
    column_usage_count: int = Field(default=0, ge=0)
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlScopeRelationObservedField(ContractModel):
    name: NonEmptyText
    usage_roles: list[NonEmptyText] = Field(default_factory=list)


class SqlScopeRelationContext(ContractModel):
    sql_relation_id: NonEmptyText
    relation_kind: NonEmptyText
    relation_name: NonEmptyText
    template_name: str | None = None
    logical_name: str | None = None
    alias: str | None = None
    usage_role: str | None = None
    definition_status: str | None = None
    observed_fields: list[SqlScopeRelationObservedField] = Field(default_factory=list)
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlJoinContext(ContractModel):
    sql_join_edge_id: NonEmptyText
    join_ordinal: int | None = Field(default=None, ge=0)
    join_type: str | None = None
    condition_kind: str | None = None
    predicate: str | None = None
    left_relation_id: str | None = None
    left_relation_ids: list[str] = Field(default_factory=list)
    left_relation_names: list[str] = Field(default_factory=list)
    right_relation_id: str | None = None
    right_relation_kind: str | None = None
    right_relation_name: str | None = None
    participating_relation_ids: list[str] = Field(default_factory=list)
    column_pairs: list[dict[str, JsonValue]] = Field(default_factory=list)
    using_columns: list[str] = Field(default_factory=list)
    resolution_status: str | None = None
    physical_join_confirmed: bool = False
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlProjectionContext(ContractModel):
    sql_projection_id: NonEmptyText
    projection_ordinal: int | None = Field(default=None, ge=0)
    output_name: str | None = None
    expression: str | None = None
    expression_kind: str | None = None
    is_wildcard: bool = False
    source_column_usage_ids: list[str] = Field(default_factory=list)
    resolution_status: str | None = None
    resolution_basis: str | None = None
    evidence_refs: list[SqlEvidenceRef] = Field(default_factory=list)


class SqlColumnUsageContextCounts(ContractModel):
    scope_relations: int = Field(ge=0)
    joins: int = Field(ge=0)
    projections: int = Field(ge=0)


class SqlColumnUsageContextResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    usage: SqlColumnUsageContextUsage
    statement: SqlStatementContext | None = None
    scope: SqlSelectScopeContext | None = None
    scope_relations: list[SqlScopeRelationContext] = Field(default_factory=list)
    joins: list[SqlJoinContext] = Field(default_factory=list)
    projections: list[SqlProjectionContext] = Field(default_factory=list)
    counts: SqlColumnUsageContextCounts


class SqlRelationMaterialization(ContractModel):
    materialization_id: NonEmptyText
    workflow_context_file: NonEmptyText
    materialization_kind: NonEmptyText
    source_file: NonEmptyText
    source_fact_id: NonEmptyText
    source_symbol: str | None = None
    query_file: str | None = None
    query_id: str | None = None
    source_table_name: str | None = None
    output_table_name: NonEmptyText
    resolution_status: NonEmptyText
    knowledge_class: NonEmptyText
    mapping_basis: NonEmptyText
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class SqlRelationMaterializationListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    materialization_query_schema_version: str = "relation-materialization-query/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[SqlRelationMaterialization] = Field(default_factory=list)
    page: PageMeta


class SqlQueryContextCounts(ContractModel):
    child_scopes: int = Field(default=0, ge=0)
    scope_relations: int = Field(default=0, ge=0)
    joins: int = Field(default=0, ge=0)
    projections: int = Field(default=0, ge=0)


class SqlQueryContextResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    query_context_schema_version: str = "sql-query-context/v1"
    system_id: Identifier
    revision_id: Identifier
    repo_id: Identifier
    query_id: NonEmptyText
    scope_id: str | None = None
    selection_status: NonEmptyText
    statement: SqlStatementContext | None = None
    scope: SqlSelectScopeContext | None = None
    child_scopes: list[SqlSelectScopeContext] = Field(default_factory=list)
    scope_candidates: list[SqlSelectScopeContext] = Field(default_factory=list)
    scope_relations: list[SqlScopeRelationContext] = Field(default_factory=list)
    joins: list[SqlJoinContext] = Field(default_factory=list)
    projections: list[SqlProjectionContext] = Field(default_factory=list)
    counts: SqlQueryContextCounts = Field(default_factory=SqlQueryContextCounts)
    diagnostics: list[NonEmptyText] = Field(default_factory=list)


class SqlTargetColumnLineageResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    lineage_schema_version: str = "sql-target-column-lineage/v1"
    system_id: Identifier
    revision_id: Identifier
    target_relation_name: NonEmptyText
    target_column: str | None = None
    repo_id: Identifier | None = None
    lineage_status: str | None = None
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    page: PageMeta
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    gap_count: int = Field(ge=0)
    gaps_truncated: bool = False
    gaps_by_kind: dict[str, int] = Field(default_factory=dict)


class SqlFieldCalculationResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    calculation_schema_version: str = "sql-field-calculation/v1"
    system_id: Identifier
    revision_id: Identifier
    target_relation_name: NonEmptyText
    target_column: NonEmptyText
    repo_id: Identifier | None = None
    calculations: list[dict[str, JsonValue]] = Field(default_factory=list)
    calculation_count: int = Field(ge=0)
    terminal_sources: list[dict[str, JsonValue]] = Field(default_factory=list)
    terminal_source_count: int = Field(ge=0)
    lineage_paths: list[dict[str, JsonValue]] = Field(default_factory=list)
    lineage_path_count: int = Field(ge=0)
    lineage_statuses: list[str] = Field(default_factory=list)
    physical_origin_statuses: list[str] = Field(default_factory=list)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    gap_count: int = Field(ge=0)
    gaps_truncated: bool = False
    gaps_by_kind: dict[str, int] = Field(default_factory=dict)
    coverage_status: NonEmptyText


class WorkspaceSqlCatalogResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    catalog_schema_version: str = "workspace-sql-catalog/v1"
    system_id: Identifier
    revision_id: Identifier
    scope_id: str | None = None
    sources: list[dict[str, JsonValue]] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    repository_ids: list[Identifier] = Field(default_factory=list)
    repository_count: int = Field(ge=0)
    coverage: dict[str, JsonValue] = Field(default_factory=dict)


class SqlTargetCandidatesResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    candidate_schema_version: str = "sql-target-candidates/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    candidates: list[dict[str, JsonValue]] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    diagnostics: list[str] = Field(default_factory=list)


class SqlAttributeInsertionContextRequest(ContractModel):
    repo_id: Identifier | None = None
    target_relation: NonEmptyText
    source_relation_hints: list[NonEmptyText] = Field(min_length=1, max_length=100)
    source_column_hints: list[NonEmptyText] = Field(default_factory=list, max_length=100)
    max_results: int = Field(default=10, ge=1, le=100)


class SqlAttributeInsertionContextResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    insertion_schema_version: str = "sql-attribute-insertion-context/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    target: dict[str, JsonValue] | None = None
    recommended_insertion: dict[str, JsonValue] | None = None
    insertion_candidates: list[dict[str, JsonValue]] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    diagnostics: list[str] = Field(default_factory=list)


class SqlAnalysisRepositoryCoverage(ContractModel):
    repo_id: Identifier
    analysis_status: NonEmptyText
    source_schema_version: str | None = None
    source_content_fingerprint: str | None = None
    coverage_json: dict[str, JsonValue] = Field(default_factory=dict)


class SqlRelationClassificationCoverage(ContractModel):
    status: NonEmptyText = "not_available"
    total_relations: int = Field(default=0, ge=0)
    hidden_by_default: int = Field(default=0, ge=0)
    visible_by_default: int = Field(default=0, ge=0)
    by_role: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)


class SqlSourceFieldUsageCoverage(ContractModel):
    total: int = Field(default=0, ge=0)
    relation_field_candidates: int = Field(default=0, ge=0)
    resolved_relation_fields: int = Field(default=0, ge=0)
    unresolved_relation_fields: int = Field(default=0, ge=0)
    relation_field_resolution_rate: float = Field(default=1.0, ge=0.0, le=1.0)


class SqlSourceInventoryCoverage(ContractModel):
    status: NonEmptyText = "not_available"
    column_usages: SqlSourceFieldUsageCoverage = Field(default_factory=SqlSourceFieldUsageCoverage)
    resolved_by_relation_kind: dict[str, int] = Field(default_factory=dict)
    non_source_values: dict[str, int] = Field(default_factory=dict)
    limitations: dict[str, int] = Field(default_factory=dict)
    coverage_policy: str | None = None


class SqlAnalysisCoverage(ContractModel):
    analysis_status: NonEmptyText
    relation_classification: SqlRelationClassificationCoverage = Field(
        default_factory=SqlRelationClassificationCoverage
    )
    source_inventory: SqlSourceInventoryCoverage = Field(default_factory=SqlSourceInventoryCoverage)
    repositories: list[SqlAnalysisRepositoryCoverage] = Field(default_factory=list)


class SqlRelationListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    system_id: Identifier
    revision_id: Identifier
    items: list[SqlRelationSummary]
    page: PageMeta
    coverage: SqlAnalysisCoverage


class SqlSourceInventoryExportResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    inventory_schema_version: str = "sql-source-inventory/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    item_count: int = Field(ge=0)
    items: list[SqlRelationSummary]
    coverage: SqlAnalysisCoverage


class ObservedStorageAccess(ContractModel):
    storage_access_id: Identifier
    repo_id: Identifier
    operation: str | None = None
    operation_signature: str | None = None
    class_name: str | None = None
    method_name: str | None = None
    access_kind: NonEmptyText
    operation_kind: str | None = None
    write_kind: str | None = None
    mutation_kind: str | None = None
    storage_kind: str | None = None
    storage_target_expression: str | None = None
    target_resolution_level: str | None = None
    target_resolution_status: str | None = None
    receiver_expression: str | None = None
    receiver_declared_type: str | None = None
    storage_method: str | None = None
    payload_expression: str | None = None
    payload_role: str | None = None
    writes_new_payload: bool = False
    selected_fields: list[str] = Field(default_factory=list)
    result_type: str | None = None
    sql_preview: str | None = None
    source_ref: dict[str, JsonValue] = Field(default_factory=dict)


class ObservedStorageGap(ContractModel):
    storage_usage_gap_id: Identifier
    repo_id: Identifier
    gap_code: Identifier
    severity: NonEmptyText
    owner_kind: NonEmptyText
    owner_id: NonEmptyText
    message: NonEmptyText
    details: dict[str, JsonValue] = Field(default_factory=dict)
    source_refs: list[dict[str, JsonValue]] = Field(default_factory=list)


class ObservedStorageSummary(ContractModel):
    access_count: int = Field(ge=0)
    read_count: int = Field(ge=0)
    write_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    by_storage_kind: dict[str, int] = Field(default_factory=dict)
    by_resolution_status: dict[str, int] = Field(default_factory=dict)


class ObservedStorageAccessListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    observed_storage_schema_version: str = "observed-storage-usage-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[ObservedStorageAccess]
    page: PageMeta
    summary: ObservedStorageSummary


class ObservedStorageGapListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    observed_storage_schema_version: str = "observed-storage-usage-query/v1"
    system_id: Identifier
    revision_id: Identifier
    items: list[ObservedStorageGap]
    page: PageMeta
    summary: ObservedStorageSummary


class DataModelLineageItem(ContractModel):
    lineage_id: NonEmptyText
    origin_kind: NonEmptyText
    origin_identity: NonEmptyText
    logical_type_occurrence_id: str | None = None
    logical_fully_qualified_name: str | None = None
    effective_field_occurrence_id: str | None = None
    logical_field_name: str | None = None
    storage_alias: str | None = None
    storage_key_field: str | None = None
    storage_key_expression: str | None = None
    source_sql_column_usage_id: str | None = None
    source_sql_relation_id: str | None = None
    source_sql_file: NonEmptyText
    source_sql_column_name: NonEmptyText
    workflow_context_file: NonEmptyText
    target_table_code: NonEmptyText
    physical_model_table_id: NonEmptyText
    physical_model_column_id: NonEmptyText
    physical_column_code: NonEmptyText
    transform_sql_file: NonEmptyText
    transform_query_id: NonEmptyText
    target_projection_id: NonEmptyText
    target_projection_expression: str | None = None
    knowledge_class: NonEmptyText
    mapping_basis: NonEmptyText
    origin_semantics: dict[str, JsonValue] = Field(default_factory=dict)
    projection_path: list[JsonValue] = Field(default_factory=list)
    materialization_path: list[JsonValue] = Field(default_factory=list)
    workflow_dependency_path: list[JsonValue] = Field(default_factory=list)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)


class AttributeExtensionJoinSemantic(ContractModel):
    join_semantic_id: NonEmptyText
    source_repo_id: NonEmptyText
    source_type_occurrence_id: NonEmptyText
    source_fqcn: NonEmptyText
    source_field_occurrence_id: NonEmptyText
    source_field: NonEmptyText
    declared_type_expression: str | None = None
    target_type_occurrence_id: NonEmptyText
    target_fqcn: NonEmptyText
    relationship_kind: NonEmptyText
    cardinality: NonEmptyText
    target_alignment: NonEmptyText
    polymorphic: bool
    concrete_targets: list[JsonValue] = Field(default_factory=list)
    join_method: NonEmptyText
    confidence: NonEmptyText
    sql_generation_status: NonEmptyText
    source_reference_expressions: list[JsonValue] = Field(default_factory=list)
    target_key_fields: list[JsonValue] = Field(default_factory=list)
    target_key_expressions: list[JsonValue] = Field(default_factory=list)
    source_parent_key_expressions: list[JsonValue] = Field(default_factory=list)
    child_key_expressions: list[JsonValue] = Field(default_factory=list)
    structural_correspondences: list[JsonValue] = Field(default_factory=list)
    source_sql_anchor: dict[str, JsonValue] = Field(default_factory=dict)
    target_sql_anchor: dict[str, JsonValue] = Field(default_factory=dict)
    observed_sql_join_examples: list[JsonValue] = Field(default_factory=list)
    physical_candidates: list[JsonValue] = Field(default_factory=list)
    basis: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    diagnostics: list[JsonValue] = Field(default_factory=list)


class AttributeExtensionContextSummary(ContractModel):
    by_join_method: dict[str, int] = Field(default_factory=dict)
    by_confidence: dict[str, int] = Field(default_factory=dict)
    by_sql_generation_status: dict[str, int] = Field(default_factory=dict)


class AttributeExtensionContextResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    context_query_schema_version: str = "data-model-attribute-extension-query/v1"
    context_schema_version: str = "data-model-attribute-extension-context/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[AttributeExtensionJoinSemantic] = Field(default_factory=list)
    page: PageMeta
    summary: AttributeExtensionContextSummary
    object_anchors: list[dict[str, JsonValue]] = Field(default_factory=list)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    gap_count: int = Field(default=0, ge=0)
    gaps_truncated: bool = False


class AttributeExtensionGuidanceItem(ContractModel):
    # Consumer identity: keep one stable semantic id plus readable source/target.
    # Occurrence ids remain on the canonical detail endpoint and are intentionally
    # omitted from this action-oriented projection.
    join_semantic_id: NonEmptyText
    source_repo_id: NonEmptyText
    source_fqcn: NonEmptyText
    source_field: NonEmptyText
    target_fqcn: NonEmptyText

    # Actionability first. Values are copied from canonical KLC-owned knowledge;
    # this API model does not derive or upgrade them.
    usefulness: dict[str, JsonValue] | None = None
    confidence: NonEmptyText
    relationship_kind: NonEmptyText
    cardinality: NonEmptyText
    target_alignment: NonEmptyText
    polymorphic: bool
    concrete_targets: list[JsonValue] | None = None
    join_method: NonEmptyText
    sql_generation_status: NonEmptyText
    declared_type_expression: str | None = None
    basis_summary: dict[str, JsonValue] | None = None

    # Bounded evidence needed to construct/validate a JOIN. Empty sections are
    # omitted from the compact response rather than serialized as noise.
    source_reference_expressions: list[JsonValue] | None = None
    target_key_fields: list[JsonValue] | None = None
    target_key_expressions: list[JsonValue] | None = None
    source_parent_key_expressions: list[JsonValue] | None = None
    child_key_expressions: list[JsonValue] | None = None
    source_storage_field_observations: list[dict[str, JsonValue]] | None = None
    structural_correspondences: list[dict[str, JsonValue]] | None = None
    source_sql_anchor: dict[str, JsonValue] | None = None
    target_sql_anchor: dict[str, JsonValue] | None = None
    observed_sql_join_examples: list[dict[str, JsonValue]] | None = None
    physical_candidates: list[dict[str, JsonValue]] | None = None
    diagnostics: list[dict[str, JsonValue]] | None = None
    provenance: dict[str, JsonValue] | None = None
    projection: dict[str, JsonValue] | None = None


class AttributeExtensionGuidanceResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    guidance_schema_version: str = "data-model-attribute-extension-guidance/v1"
    context_schema_version: str = "data-model-attribute-extension-context/v1"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[AttributeExtensionGuidanceItem] = Field(default_factory=list)
    page: PageMeta
    gaps: list[dict[str, JsonValue]] | None = None
    gap_count: int = Field(default=0, ge=0)
    gaps_truncated: bool = False
    projection: dict[str, JsonValue] = Field(default_factory=dict)


class RepositoryInventorySummaryResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    repository_inventory_schema_version: str = "repository-inventory-query/v5"
    inventory_schema_version: str | None = None
    system_id: Identifier
    revision_id: Identifier
    evaluation_phase: str | None = None
    evaluation_basis: dict[str, JsonValue] = Field(default_factory=dict)
    identity: dict[str, JsonValue] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    discovery_counts: dict[str, int] = Field(default_factory=dict)
    source_evidence: list[dict[str, JsonValue]] = Field(default_factory=list)


class RepositoryInventoryCoverageResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    repository_inventory_schema_version: str = "repository-inventory-coverage-query/v5"
    system_id: Identifier
    revision_id: Identifier
    evaluation_phase: str | None = None
    analyzer_frontier: dict[str, int] = Field(default_factory=dict)
    completeness: list[dict[str, JsonValue]] = Field(default_factory=list)
    gap_counts: dict[str, int] = Field(default_factory=dict)
    discovery_gap_counts: dict[str, int] = Field(default_factory=dict)
    source_evidence: list[dict[str, JsonValue]] = Field(default_factory=list)


class RepositoryInventoryPageResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    repository_inventory_schema_version: str = "repository-inventory-query/v5"
    system_id: Identifier
    revision_id: Identifier
    query_kind: NonEmptyText
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    page: PageMeta


class RepositorySourceOccurrenceResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    repository_source_occurrence_schema_version: str = "repository-source-occurrence-query/v1"
    system_id: Identifier
    revision_id: Identifier
    occurrence: dict[str, JsonValue]
    object_links: list[dict[str, JsonValue]] = Field(default_factory=list)


class PortfolioSystemInventory(ContractModel):
    system_id: Identifier
    display_name: NonEmptyText
    inventory_status: str = "available"
    inventory_diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    description: str | None = None
    active_revision_id: str | None = None
    repository_membership_basis: NonEmptyText
    repositories: list[dict[str, JsonValue]] = Field(default_factory=list)
    repository_count: int = Field(ge=0)
    repository_urls: list[str] = Field(default_factory=list)
    source_kinds: dict[str, int] = Field(default_factory=dict)
    technologies: list[dict[str, JsonValue]] = Field(default_factory=list)
    discovery_candidates: list[dict[str, JsonValue]] = Field(default_factory=list)
    coverage_gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    protocols: dict[str, int] = Field(default_factory=dict)


class PortfolioInventoryListResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    portfolio_inventory_schema_version: str = "portfolio-inventory-query/v1"
    items: list[PortfolioSystemInventory] = Field(default_factory=list)
    page: PageMeta
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    source_of_truth: str = "published_repository_inventory_revisions"


class PortfolioInventoryFacetsResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    portfolio_inventory_schema_version: str = "portfolio-inventory-query/v1"
    system_count: int = Field(ge=0)
    facets: dict[str, JsonValue] = Field(default_factory=dict)
    source_of_truth: str = "published_repository_inventory_revisions"


class PortfolioInteractionGraphResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    portfolio_inventory_schema_version: str = "portfolio-interaction-observations/v1"
    nodes: list[dict[str, JsonValue]] = Field(default_factory=list)
    observations: list[dict[str, JsonValue]] = Field(default_factory=list)
    resolved_observation_count: int = Field(ge=0)
    unresolved_observation_count: int = Field(ge=0)
    source_of_truth: str = "published_repository_inventory_revisions"
    claim_boundary: str = "observed interface directions are preserved; unresolved peers are not guessed or clustered"


class InteractionKnowledgePageResponse(ContractModel):
    """Thin revision-bound projection of one canonical KLC interaction query page."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    interaction_query_schema_version: str = "system-interaction-query/v1"
    system_id: Identifier
    revision_id: Identifier
    query_kind: NonEmptyText
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    page: PageMeta


class SystemInteractionGuidanceResponse(ContractModel):
    """Compact consumer projection over one exact published system interaction."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    guidance_schema_version: str = "system-interaction-guidance/v1"
    system_id: Identifier
    revision_id: Identifier
    interaction_id: Identifier
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    projection: dict[str, JsonValue] = Field(default_factory=dict)


class SystemDescriptionGuidanceResponse(ContractModel):
    """Compact consumer projection over canonical System Description reads."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    guidance_schema_version: str = "system-description-guidance/v1"
    system_id: Identifier
    revision_id: Identifier
    scope: dict[str, JsonValue] = Field(default_factory=dict)
    composition: dict[str, JsonValue] = Field(default_factory=dict)
    observed_inventory: dict[str, JsonValue] = Field(default_factory=dict)
    representative_journeys: dict[str, JsonValue] = Field(default_factory=dict)
    coverage: dict[str, JsonValue] = Field(default_factory=dict)
    gaps: dict[str, JsonValue] = Field(default_factory=dict)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    projection: dict[str, JsonValue] = Field(default_factory=dict)


class ReferenceDataGuidanceResponse(ContractModel):
    """Compact facts-only consumer projection over canonical Reference Data reads."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    guidance_schema_version: str = "reference-data-guidance/v1"
    system_id: Identifier
    revision_id: Identifier
    token: str = ""
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    candidate_representations: list[dict[str, JsonValue]] = Field(default_factory=list)
    local_definition_evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    literal_writes: list[dict[str, JsonValue]] = Field(default_factory=list)
    usage_summary: dict[str, JsonValue] = Field(default_factory=dict)
    usage_observations: list[dict[str, JsonValue]] = Field(default_factory=list)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    interpretation_policy: dict[str, JsonValue] = Field(default_factory=dict)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    projection: dict[str, JsonValue] = Field(default_factory=dict)


class ForeignDataPersistenceGuidanceResponse(ContractModel):
    """Compact consumer projection over canonical KLC FDP paths/cases."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    guidance_schema_version: str = "foreign-data-persistence-guidance/v1"
    system_id: Identifier
    revision_id: Identifier
    token: str = ""
    path_summary: dict[str, JsonValue] = Field(default_factory=dict)
    case_summary: dict[str, JsonValue] = Field(default_factory=dict)
    paths: list[dict[str, JsonValue]] = Field(default_factory=list)
    cases: list[dict[str, JsonValue]] = Field(default_factory=list)
    storage_summaries: list[dict[str, JsonValue]] = Field(default_factory=list)
    interpretation_policy: dict[str, JsonValue] = Field(default_factory=dict)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    projection: dict[str, JsonValue] = Field(default_factory=dict)


ReportingQueryKind = Literal[
    "get_scope_overview",
    "get_repository_composition",
    "get_technologies",
    "list_interfaces",
    "list_integrations",
    "list_events",
    "list_data_objects",
    "list_relationships",
    "get_analysis_coverage",
    "get_gap_summary",
    "get_representative_journeys",
]


ForeignDataPersistenceQueryKind = Literal[
    "list_paths",
    "get_path",
    "list_mechanical_cases",
    "get_landscape",
]

ReferenceDataQueryKind = Literal[
    "search_reference_data",
    "get_reference_data_object",
    "get_candidate_context",
    "list_declared_value_sets",
    "list_literal_writes",
    "get_usage_observations",
    "get_gap_summary",
    "get_landscape",
]


class ReferenceDataQueryRequest(ContractModel):
    """Request for one canonical KLC ReferenceDataQueryService operation."""

    revision_id: Identifier | None = None
    query_kind: ReferenceDataQueryKind
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    max_results: int = Field(default=100, ge=1, le=10000)


class ForeignDataPersistenceQueryRequest(ContractModel):
    """Request for one canonical KLC ForeignDataPersistenceQueryService operation."""

    revision_id: Identifier | None = None
    query_kind: ForeignDataPersistenceQueryKind
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    max_results: int = Field(default=100, ge=1, le=10000)


class ReportingKnowledgeQueryRequest(ContractModel):
    """Request for one canonical KLC ReportingQueryService operation."""

    revision_id: Identifier | None = None
    query_kind: ReportingQueryKind
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    max_results: int = Field(default=100, ge=1, le=2000)


class ReportingKnowledgeQueryResponse(ContractModel):
    """Revision-bound pass-through of KLC knowledge_query/v1."""

    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    knowledge_query_schema_version: str = "knowledge_query/v1"
    system_id: Identifier
    revision_id: Identifier
    query: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[dict[str, JsonValue]] = Field(default_factory=list)
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)
    gaps: list[dict[str, JsonValue]] = Field(default_factory=list)
    pagination: dict[str, JsonValue] | None = None


class DataModelLineageSummary(ContractModel):
    path_count: int = Field(ge=0)
    origin_count: int = Field(ge=0)
    target_table_count: int = Field(ge=0)
    target_column_count: int = Field(ge=0)
    source_sql_file_count: int = Field(ge=0)
    transform_sql_file_count: int = Field(ge=0)
    by_origin_kind: dict[str, int] = Field(default_factory=dict)
    by_knowledge_class: dict[str, int] = Field(default_factory=dict)
    by_lineage_role: dict[str, int] = Field(default_factory=dict)


class DataModelLineageResponse(ContractModel):
    schema_version: str = KNOWLEDGE_API_SCHEMA_VERSION
    lineage_schema_version: str = "data-model-lineage-query/v2"
    system_id: Identifier
    revision_id: Identifier
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[DataModelLineageItem] = Field(default_factory=list)
    page: PageMeta
    summary: DataModelLineageSummary


# AISL universal read projection. Typed KnowledgeProduct payloads remain authoritative;
# these models only provide a uniform address/evidence/quality envelope for agents.
class AislReadFacetAvailability(StrEnum):
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    UNSUPPORTED = "unsupported"


class AislReadFacetState(ContractModel):
    availability: AislReadFacetAvailability
    basis: NonEmptyText


class AislKnowledgeItemRef(ContractModel):
    scope_id: Identifier
    revision_id: Identifier
    product_id: Identifier
    item_kind: Identifier
    local_id: NonEmptyText


class AislSourceFragment(ContractModel):
    fragment_id: NonEmptyText
    source_id: NonEmptyText
    fragment_kind: NonEmptyText
    locator: NonEmptyText
    content_identity: str | None = None
    path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    extractor: str | None = None


class AislEvidence(ContractModel):
    evidence_id: NonEmptyText
    evidence_kind: NonEmptyText
    source_fragment_ids: list[NonEmptyText] = Field(default_factory=list)
    basis: NonEmptyText


class AislEvidenceBinding(ContractModel):
    binding_id: NonEmptyText
    evidence_id: NonEmptyText
    role: NonEmptyText = "direct_observation"
    basis: NonEmptyText


class AislKnowledgeIssue(ContractModel):
    issue_id: NonEmptyText
    kind: NonEmptyText
    message: NonEmptyText
    basis: NonEmptyText
    details: dict[str, JsonValue] = Field(default_factory=dict)


class AislCorrespondenceEndpoint(ContractModel):
    scope_id: Identifier
    revision_id: Identifier
    product_id: Identifier
    item_kind: Identifier
    local_id: NonEmptyText


class AislCrossProductCorrespondence(ContractModel):
    correspondence_id: NonEmptyText
    relation_kind: NonEmptyText
    source_ref: AislCorrespondenceEndpoint
    target_ref: AislCorrespondenceEndpoint | None = None
    candidate_target_refs: list[AislCorrespondenceEndpoint] = Field(default_factory=list)
    resolution_status: NonEmptyText
    basis: NonEmptyText
    evidence_ids: list[NonEmptyText] = Field(default_factory=list)


class AislKnowledgeItemReadResponse(ContractModel):
    schema_version: str = "aisl-knowledge-item-read/v1"
    system_id: Identifier
    revision_id: Identifier
    product: PublishedKnowledgeArtifact
    item_ref: AislKnowledgeItemRef
    projection_status: AislReadFacetAvailability
    projection_basis: NonEmptyText
    item: dict[str, JsonValue] | None = None
    evidence: list[AislEvidence] = Field(default_factory=list)
    evidence_bindings: list[AislEvidenceBinding] = Field(default_factory=list)
    source_fragments: list[AislSourceFragment] = Field(default_factory=list)
    issues: list[AislKnowledgeIssue] = Field(default_factory=list)
    correspondences: list[AislCrossProductCorrespondence] = Field(default_factory=list)
    evidence_state: AislReadFacetState
    coverage_state: AislReadFacetState
    issues_state: AislReadFacetState
    correspondences_state: AislReadFacetState
