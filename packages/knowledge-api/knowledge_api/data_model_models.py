from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .version import API_SCHEMA_VERSION


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemSummary(StrictModel):
    system_id: str
    display_name: str
    description: str | None = None
    enabled: bool = True


class SystemsResponse(StrictModel):
    schema_version: Literal["data_model_api/v4"] = API_SCHEMA_VERSION
    systems: list[SystemSummary]


class FieldCatalogField(StrictModel):
    field_name: str
    description: str | None = None


class FieldCatalogTable(StrictModel):
    table_id: str
    table_name: str
    description: str | None = None
    fields: list[FieldCatalogField] = Field(default_factory=list)


class FieldCatalogResponse(StrictModel):
    system_id: str
    tables: list[FieldCatalogTable]


class DataObjectRef(StrictModel):
    id: str
    name: str
    kind: str
    display_name: str | None = None
    description: str | None = None


class TableFieldStorageEvidenceRef(StrictModel):
    evidence_id: str
    repo_id: str
    path: str
    line_start: int | None = None
    line_end: int | None = None
    extractor: str | None = None
    maturity: str
    role: str | None = None


class TableFieldStorageObservation(StrictModel):
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


class TableField(StrictModel):
    name: str
    type: str
    target_object: str | None = None
    display_name: str | None = None
    description: str | None = None
    nullable: bool | None = None
    inherited: bool = False
    storage_observation_count: int = Field(default=0, ge=0)
    storage_observations: list[TableFieldStorageObservation] = Field(default_factory=list)
    storage_observations_truncated: bool = False


class TableKey(StrictModel):
    kind: str
    fields: list[str]
    version_field: str | None = None
    collocation_field: str | None = None


class RelationshipSource(StrictModel):
    field: str
    inherited: bool = False
    cardinality: str


class RelationshipLogicalIdentity(StrictModel):
    status: str
    fields: list[str] = Field(default_factory=list)
    version_fields: list[str] = Field(default_factory=list)
    collocation_fields: list[str] = Field(default_factory=list)
    classification_basis: str


class RelationshipStorageKeyEvidence(StrictModel):
    storage_reference_id: str | None = None
    storage_lineage_id: str | None = None
    target_alias: str | None = None
    field: str | None = None
    expression: str | None = None
    composed_expression: str | None = None
    expression_tree: dict[str, Any] = Field(default_factory=dict)
    input_symbols: list[str] = Field(default_factory=list)
    parameter_bindings: list[dict[str, Any]] = Field(default_factory=list)
    reference_operation: str | None = None
    value_origin: str | None = None
    value_binding_resolution: str | None = None
    source_operation: str | None = None
    target_converter_operation: str | None = None
    physical_encoding: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class RelationshipStorageKey(StrictModel):
    status: str
    fields: list[str] = Field(default_factory=list)
    expressions: list[str] = Field(default_factory=list)
    evidence: list[RelationshipStorageKeyEvidence] = Field(default_factory=list)


class RelationshipTarget(StrictModel):
    object: DataObjectRef
    aliases: list[str] = Field(default_factory=list)
    logical_identity: RelationshipLogicalIdentity
    storage_key: RelationshipStorageKey


class RelationshipTypeEncodingInput(StrictModel):
    source: Literal["target_alias"]
    values: list[str] = Field(default_factory=list)


class RelationshipKeyEncodingInput(StrictModel):
    source: Literal["target_storage_key"]
    fields: list[str] = Field(default_factory=list)


class RelationshipEncodingInputs(StrictModel):
    type_component: RelationshipTypeEncodingInput
    key_component: RelationshipKeyEncodingInput


class RelationshipPhysicalEncoding(StrictModel):
    status: str


class RelationshipReference(StrictModel):
    assignment_operations: list[str] = Field(default_factory=list)
    value_origins: list[str] = Field(default_factory=list)
    encoding_inputs: RelationshipEncodingInputs
    physical_encoding: RelationshipPhysicalEncoding


class RelationshipJoinEndpoint(StrictModel):
    field: str | None = None
    kind: str | None = None
    fields: list[str] = Field(default_factory=list)
    expression: str | None = None
    expressions: list[str] = Field(default_factory=list)
    composed_expression: str | None = None


class RelationshipJoin(StrictModel):
    method: str
    source: RelationshipJoinEndpoint
    target: RelationshipJoinEndpoint
    requires_encoding_interpretation: bool
    physical_join_confirmed: bool
    match_basis: str | None = None
    parent_key_passed: bool | None = None
    collection_membership_semantics: str | None = None


class TableRelationship(StrictModel):
    relationship_id: str
    kind: str
    source: RelationshipSource
    target: RelationshipTarget
    reference: RelationshipReference
    join: RelationshipJoin
    polymorphic_targets: list[DataObjectRef] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class CompactDataObjectRef(StrictModel):
    id: str
    name: str
    kind: str


class RelationshipTargetSummary(StrictModel):
    object: CompactDataObjectRef
    aliases: list[str] | None = None


class RelationshipJoinSummary(StrictModel):
    method: str
    source_fields: list[str]
    target_fields: list[str] | None = None
    target_kind: str | None = None
    source_expressions: list[str] | None = None
    target_expressions: list[str] | None = None
    requires_encoding_interpretation: bool
    physical_join_confirmed: bool
    match_basis: str | None = None
    parent_key_passed: bool | None = None
    collection_membership_semantics: str | None = None


class TableRelationshipSummary(StrictModel):
    relationship_id: str
    kind: str
    source_field: str
    cardinality: str
    target: RelationshipTargetSummary
    join: RelationshipJoinSummary
    polymorphic_targets: list[CompactDataObjectRef] | None = None


class TableDetailResponse(StrictModel):
    schema_version: Literal["data_model_api/v4"]
    system_id: str
    workspace_id: str | None = None
    build_id: str | None = None
    generated_at: str | None = None
    object: DataObjectRef
    fields: list[TableField] = Field(default_factory=list)
    keys: list[TableKey] = Field(default_factory=list)
    relationships: list[TableRelationshipSummary] = Field(default_factory=list)
    embedded_objects: list[Any] = Field(default_factory=list)
    relationship_candidate_count: int = 0
    indexes: list[Any] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)
    partitioning: list[Any] = Field(default_factory=list)
    triggers: list[Any] = Field(default_factory=list)


class ErrorDetail(StrictModel):
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    error: ErrorDetail
