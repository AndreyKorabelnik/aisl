from __future__ import annotations

from dataclasses import dataclass

PHYSICAL_MODEL_DATABASE = "knowledge-layer.duckdb"
PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION = "physical-model/v1"
PHYSICAL_MODEL_SCHEMA_VERSION = "knowledge_layer_physical_model/v1"


@dataclass(frozen=True, slots=True)
class PhysicalModelFactSchema:
    fact_type: str
    id_field: str
    fields: tuple[str, ...]


PHYSICAL_MODEL_FACT_SCHEMAS = (
    PhysicalModelFactSchema("physical_model_table", "physical_model_table_id", (
        "physical_model_table_id", "physical_model_source_id", "pdm_object_id", "object_uuid",
        "model_name", "model_code", "package_path", "package_code_path", "table_name", "table_code",
        "logical_identity", "comment", "description", "stereotype", "dimensional_type", "owner_ref",
        "column_count", "key_count", "source_file", "evidence",
    )),
    PhysicalModelFactSchema("physical_model_column", "physical_model_column_id", (
        "physical_model_column_id", "physical_model_table_id", "physical_model_source_id", "pdm_object_id",
        "object_uuid", "ordinal", "column_name", "column_code", "data_type", "length", "precision",
        "mandatory", "default_value", "comment", "domain_ref", "source_file", "evidence",
    )),
    PhysicalModelFactSchema("physical_model_key", "physical_model_key_id", (
        "physical_model_key_id", "physical_model_table_id", "physical_model_source_id", "pdm_object_id",
        "object_uuid", "key_name", "key_code", "key_kind", "column_pdm_ids", "column_codes",
        "unresolved_column_refs", "source_file", "evidence",
    )),
    PhysicalModelFactSchema("physical_model_relationship", "physical_model_relationship_id", (
        "physical_model_relationship_id", "physical_model_source_id", "pdm_object_id", "object_uuid",
        "relationship_name", "relationship_code", "cardinality", "parent_table_ref", "parent_table_id",
        "parent_table_code", "child_table_ref", "child_table_id", "child_table_code", "parent_key_ref",
        "parent_key_id", "joins", "resolution_status", "source_file", "evidence",
    )),
    PhysicalModelFactSchema("physical_model_gap", "physical_model_gap_id", (
        "physical_model_gap_id", "physical_model_source_id", "gap_kind", "owner_pdm_object_id",
        "unresolved_ref", "message",
    )),
)

PHYSICAL_MODEL_FACT_SCHEMA_BY_TYPE = {schema.fact_type: schema for schema in PHYSICAL_MODEL_FACT_SCHEMAS}
PHYSICAL_MODEL_FACT_TYPES = tuple(schema.fact_type for schema in PHYSICAL_MODEL_FACT_SCHEMAS)

_INTEGER_FIELDS = {"ordinal", "length", "precision", "column_count", "key_count"}
_BOOLEAN_FIELDS = {"mandatory"}
_JSON_FIELDS = {
    "package_path", "package_code_path", "column_pdm_ids", "column_codes", "unresolved_column_refs",
    "joins", "evidence",
}


def database_column_name(source_field: str) -> str:
    return f"{source_field}_json" if source_field in _JSON_FIELDS else source_field


def database_column_type(source_field: str) -> str:
    if source_field in _JSON_FIELDS:
        return "JSON"
    if source_field in _INTEGER_FIELDS:
        return "BIGINT"
    if source_field in _BOOLEAN_FIELDS:
        return "BOOLEAN"
    return "VARCHAR"


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _fact_table_ddl(schema: PhysicalModelFactSchema) -> str:
    columns: list[str] = []
    for field in schema.fields:
        name = database_column_name(field)
        constraints: list[str] = []
        if field == schema.id_field:
            constraints.append("PRIMARY KEY")
        if field in {schema.id_field, "physical_model_source_id"}:
            constraints.append("NOT NULL")
        suffix = " " + " ".join(constraints) if constraints else ""
        columns.append(f"    {_quoted(name)} {database_column_type(field)}{suffix}")
    columns.append("    payload_json JSON NOT NULL")
    return f"CREATE TABLE {_quoted(schema.fact_type)} (\n" + ",\n".join(columns) + "\n);"


PHYSICAL_MODEL_TABLE_DDL = """
CREATE TABLE physical_model_build (
    build_id VARCHAR PRIMARY KEY,
    scope_id VARCHAR NOT NULL,
    builder_version VARCHAR NOT NULL,
    schema_version VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    source_content_fingerprint VARCHAR NOT NULL,
    build_status VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    counts_json JSON,
    checks_json JSON
);

CREATE TABLE physical_model_source (
    physical_model_source_id VARCHAR PRIMARY KEY,
    manifest_path VARCHAR NOT NULL,
    source_schema_version VARCHAR NOT NULL,
    content_fingerprint VARCHAR NOT NULL,
    core_version VARCHAR,
    source_file VARCHAR,
    source_sha256 VARCHAR,
    model_object_id VARCHAR,
    model_name VARCHAR,
    model_code VARCHAR,
    powerdesigner_version VARCHAR,
    powerdesigner_target VARCHAR,
    coverage_status VARCHAR NOT NULL,
    gap_count BIGINT NOT NULL,
    metadata_json JSON NOT NULL,
    manifest_json JSON NOT NULL
);
""" + "\n\n".join(_fact_table_ddl(schema) for schema in PHYSICAL_MODEL_FACT_SCHEMAS) + """

CREATE INDEX idx_physical_model_table_source_code
    ON physical_model_table(physical_model_source_id, table_code);
CREATE INDEX idx_physical_model_column_table_code
    ON physical_model_column(physical_model_table_id, column_code);
CREATE INDEX idx_physical_model_key_table
    ON physical_model_key(physical_model_table_id, key_kind);
CREATE INDEX idx_physical_model_relationship_parent
    ON physical_model_relationship(parent_table_id);
CREATE INDEX idx_physical_model_relationship_child
    ON physical_model_relationship(child_table_id);
CREATE INDEX idx_physical_model_gap_source
    ON physical_model_gap(physical_model_source_id, gap_kind);
"""

PHYSICAL_MODEL_TABLES = (
    "physical_model_build",
    "physical_model_source",
    *PHYSICAL_MODEL_FACT_TYPES,
)
PHYSICAL_MODEL_DDL = PHYSICAL_MODEL_TABLE_DDL
