from __future__ import annotations

"""Facts-only contracts for observable table relationships and key usage.

These models define exchange contracts only. They intentionally do not assign
confidence, cardinality, semantic equivalence, business meaning, or verdicts.
Extractors may publish unresolved names when a physical object cannot be
mechanically resolved, but they must retain concrete provenance.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION = "table_relationship_observation/v1"
TABLE_KEY_OBSERVATION_SCHEMA_VERSION = "table_key_observation/v1"


class RelationshipKind(str, Enum):
    DECLARED_FOREIGN_KEY = "declared_foreign_key"
    ORM_MAPPING = "orm_mapping"
    SQL_JOIN_PREDICATE = "sql_join_predicate"
    CORRELATED_SUBQUERY_PREDICATE = "correlated_subquery_predicate"
    DATA_MOVEMENT = "data_movement"
    VIEW_DEPENDENCY = "view_dependency"
    PARTITION_PARENT = "partition_parent"
    SHARED_KEY_USAGE = "shared_key_usage"


class RelationshipSourceKind(str, Enum):
    DDL = "ddl"
    SQL = "sql"
    ORM = "orm"
    JOOQ = "jooq"
    GENERATED_SCHEMA = "generated_schema"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class KeyObservationKind(str, Enum):
    DECLARED_PRIMARY_KEY = "declared_primary_key"
    DECLARED_UNIQUE_KEY = "declared_unique_key"
    DECLARED_UNIQUE_INDEX = "declared_unique_index"
    ORM_IDENTITY = "orm_identity"
    MERGE_MATCH_KEY = "merge_match_key"
    UPSERT_CONFLICT_KEY = "upsert_conflict_key"
    DEDUPLICATION_PARTITION_KEY = "deduplication_partition_key"
    LOOKUP_KEY_USAGE = "lookup_key_usage"
    PARTITION_KEY = "partition_key"
    KEY_CANDIDATE_OBSERVATION = "key_candidate_observation"
    UNRESOLVED_KEY_MAPPING = "unresolved_key_mapping"


class ObservationEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    kind: str
    snippet: str | None = None

    @model_validator(mode="after")
    def validate_line_range(self) -> "ObservationEvidenceRef":
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class TableRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str | None = None
    table_name: str | None = None
    schema_name: str | None = None
    qualified_table_name: str | None = None
    unresolved_name: str | None = None

    @model_validator(mode="after")
    def require_observable_identity(self) -> "TableRef":
        if not any((self.table_id, self.table_name, self.qualified_table_name, self.unresolved_name)):
            raise ValueError("table reference requires an observed or unresolved identity")
        return self


class TableColumnRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_id: str | None = None
    column_name: str | None = None
    unresolved_name: str | None = None

    @model_validator(mode="after")
    def require_observable_identity(self) -> "TableColumnRef":
        if not any((self.column_id, self.column_name, self.unresolved_name)):
            raise ValueError("column reference requires an observed or unresolved identity")
        return self


class TableColumnPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: TableColumnRef
    operator: str = "="
    right: TableColumnRef
    predicate_ordinal: int | None = Field(default=None, ge=0)


class MatchedDeclaredKeyRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: str
    key_id: str
    key_kind: str
    matched_columns: list[str] = Field(min_length=1)


class TableRelationshipObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION
    observation_id: str
    fact_type: str = "table_relationship_observation"
    repo_id: str
    relation_kind: RelationshipKind
    left_table: TableRef
    right_table: TableRef
    column_pairs: list[TableColumnPair] = Field(default_factory=list)
    source_kind: RelationshipSourceKind
    statement_id: str | None = None
    query_id: str | None = None
    join_type: str | None = None
    direction: str | None = None
    matched_declared_keys: list[MatchedDeclaredKeyRef] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[ObservationEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "TableRelationshipObservation":
        if self.schema_version != TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TABLE_RELATIONSHIP_OBSERVATION_SCHEMA_VERSION!r}")
        forbidden = {"confidence", "score", "verdict", "cardinality", "business_meaning", "source_of_truth"}
        present = forbidden.intersection(self.properties)
        if present:
            raise ValueError(f"facts-only relationship observation cannot contain: {sorted(present)}")
        if self.relation_kind in {
            RelationshipKind.SQL_JOIN_PREDICATE,
            RelationshipKind.CORRELATED_SUBQUERY_PREDICATE,
        } and not self.column_pairs:
            raise ValueError(f"{self.relation_kind.value} requires at least one column pair")
        return self


class TableKeyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = TABLE_KEY_OBSERVATION_SCHEMA_VERSION
    observation_id: str
    fact_type: str = "table_key_observation"
    repo_id: str
    key_kind: KeyObservationKind
    table: TableRef
    columns: list[TableColumnRef] = Field(min_length=1)
    constraint_name: str | None = None
    index_name: str | None = None
    entity_name: str | None = None
    source_kind: RelationshipSourceKind
    observation_basis: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[ObservationEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "TableKeyObservation":
        if self.schema_version != TABLE_KEY_OBSERVATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TABLE_KEY_OBSERVATION_SCHEMA_VERSION!r}")
        forbidden = {"confidence", "score", "verdict", "is_primary_key", "business_grain"}
        present = forbidden.intersection(self.properties)
        if present:
            raise ValueError(f"facts-only key observation cannot contain: {sorted(present)}")
        candidate_kinds = {
            KeyObservationKind.MERGE_MATCH_KEY,
            KeyObservationKind.UPSERT_CONFLICT_KEY,
            KeyObservationKind.DEDUPLICATION_PARTITION_KEY,
            KeyObservationKind.LOOKUP_KEY_USAGE,
            KeyObservationKind.KEY_CANDIDATE_OBSERVATION,
        }
        if self.key_kind in candidate_kinds and not self.observation_basis:
            raise ValueError(f"{self.key_kind.value} requires observation_basis")
        return self


def relationship_observation_json_schema() -> dict[str, Any]:
    return TableRelationshipObservation.model_json_schema()


def key_observation_json_schema() -> dict[str, Any]:
    return TableKeyObservation.model_json_schema()


def validate_relationship_observation(payload: dict[str, Any]) -> dict[str, Any]:
    return TableRelationshipObservation.model_validate(payload).model_dump(mode="json", exclude_none=True)


def validate_key_observation(payload: dict[str, Any]) -> dict[str, Any]:
    return TableKeyObservation.model_validate(payload).model_dump(mode="json", exclude_none=True)
