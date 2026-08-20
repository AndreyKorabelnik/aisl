from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class InterfaceKind(str, Enum):
    REST = "rest"
    KAFKA = "kafka"
    GRPC = "grpc"
    CALLBACK = "callback"
    DB = "db"
    BATCH = "batch"
    FILE = "file"
    UNKNOWN = "unknown"


class EvidenceRef(BaseModel):
    file_path: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    snippet: Optional[str] = None
    extractor: Optional[str] = None


class Fact(BaseModel):
    fact_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FieldInfo(BaseModel):
    name: str
    type: Optional[str] = None
    description: Optional[str] = None
    annotations: list[str] = Field(default_factory=list)
    nested_type: Optional[str] = None
    serialized_name: Optional[str] = None
    serialized_name_basis: Optional[str] = None
    serialization_library: Optional[str] = None
    serialization_aliases: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class SchemaInfo(BaseModel):
    name: str
    source_type: str = "unknown"
    fields: list[FieldInfo] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)


class InterfaceInfo(BaseModel):
    name: str
    direction: Direction = Direction.UNKNOWN
    kind: InterfaceKind = InterfaceKind.UNKNOWN
    schema_ref: Optional[str] = None
    operation: Optional[str] = None
    path: Optional[str] = None
    method: Optional[str] = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class RelationInfo(BaseModel):
    source: str
    target: str
    relation_type: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    system_name: str
    project_code: str
    repo_path: str
    stack: list[str] = Field(default_factory=list)
    files_analyzed: int = 0
    facts: list[Fact] = Field(default_factory=list)
    interfaces: list[InterfaceInfo] = Field(default_factory=list)
    schemas: list[SchemaInfo] = Field(default_factory=list)
    relations: list[RelationInfo] = Field(default_factory=list)
    mapper_facts: list[Fact] = Field(default_factory=list)
    config_facts: list[Fact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
