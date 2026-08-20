from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prepared_knowledge_runtime.database import initialize_schema


@dataclass(frozen=True, slots=True)
class SchemaDefinition:
    schema_version: str
    ddl: str
    data_tables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.schema_version or "").strip():
            raise ValueError("schema_version must not be empty")
        if not str(self.ddl or "").strip():
            raise ValueError("ddl must not be empty")

    def initialize(self, connection: Any) -> None:
        initialize_schema(connection, self.ddl)
