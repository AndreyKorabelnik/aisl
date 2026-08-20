from prepared_knowledge_runtime.analysis_coverage import ANALYSIS_COVERAGE_SCHEMA_VERSION, build_analysis_coverage
from prepared_knowledge_runtime.attribute_paths import ATTRIBUTE_PATH_SCHEMA_VERSION, resolve_attribute_paths
from prepared_knowledge_runtime.consumer_contracts import (
    CONSUMER_SCHEMA_VERSION, EvidenceRef, Gap, Page, QueryRequest, QueryResult, ScopeRef, evidence_index,
)
from prepared_knowledge_runtime.reporting_queries import ReportingQueryService
from .bulk import bulk_insert
from prepared_knowledge_runtime.contracts import (
    ARTIFACT_ID,
    SCHEMA_VERSION,
    SUPPORTED_MODES,
    KnowledgeLayerManifest,
    derive_scope_type,
)
from prepared_knowledge_runtime.database import connect_database, initialize_schema, require_duckdb

from .code_declared_model_builder import build_code_declared_data_model_knowledge_layer
from .code_declared_model_ingestion import (
    ResolvedJavaTypeStructureArtifact, ingest_java_type_structure_artifact, resolve_java_type_structure_artifact,
)
from .code_declared_model_schema import (
    CODE_DECLARED_MODEL_DATABASE, CODE_DECLARED_MODEL_DDL, CODE_DECLARED_MODEL_SCHEMA_VERSION,
    CODE_DECLARED_MODEL_SOURCE_SCHEMA_VERSION, CODE_DECLARED_MODEL_RUN_MANIFEST_SCHEMA_VERSION,
    CODE_DECLARED_MODEL_TABLES,
)
from .data_model_schema import (
    CORE_DATA_TABLES,
    CORE_DDL,
    CORE_SCHEMA_VERSION,
    CORE_TABLES,
    CORE_TABLE_DDL,
    CORE_VIEWS,
    CORE_VIEW_DDL,
)
from prepared_knowledge_runtime.errors import KnowledgeLayerContractError
from .evidence import TOOLS as EVIDENCE_TOOLS, execute_evidence_request, load_evidence_tool_catalog
from .interaction_contracts import FIELD_CONTRACT_SCHEMA_VERSION, materialize_system_interaction_field_contracts, normalize_wire_path
from .value_flow import VALUE_FLOW_SCHEMA_VERSION, materialize_repository_value_flow
from prepared_knowledge_runtime.io import load_manifest, read_json, write_json, write_manifest
from .metrics import BuildStats, canonical_json, utc_now
from .materialization_runtime import (
    MATERIALIZATION_EXECUTION_RESULT_SCHEMA_VERSION, MATERIALIZATION_REQUEST_SCHEMA_VERSION,
    MATERIALIZATION_RUNTIME_CONTRACT_ID, materialize, materialize_from_request_file, registered_materialization_ids,
)
from .materialization_contracts import (
    MATERIALIZATION_CATALOG_SCHEMA_VERSION, MATERIALIZATION_CONTRACT_SCHEMA_VERSION,
    EVIDENCE_ROUTING_CONTRACT_ID, build_materialization_contract_catalog,
    render_materialization_contract_catalog_markdown, write_materialization_contract_catalog,
    write_materialization_contract_catalog_markdown,
)
from prepared_knowledge_runtime.normalization import normalize_db_identifier, normalize_field_correspondence_path, normalize_text, stable_id
from .publication import publish_directory_atomic, remove_path
from prepared_knowledge_runtime.query import KnowledgeLayerQuery
from .sql_analysis_builder import build_sql_knowledge_layer
from .sql_analysis_ingestion import ResolvedSqlAnalysisArtifact, ingest_sql_analysis_artifact, resolve_sql_analysis_artifact
from .sql_analysis_schema import (
    SQL_ANALYSIS_DATABASE, SQL_ANALYSIS_DDL, SQL_ANALYSIS_FACT_TYPES, SQL_ANALYSIS_SCHEMA_VERSION,
    SQL_ANALYSIS_SOURCE_SCHEMA_VERSION, SQL_ANALYSIS_TABLES, SQL_ANALYSIS_VIEWS, SQL_FACT_SCHEMAS,
)

from .effective_data_model_builder import build_effective_data_model_knowledge_layer
from .effective_data_model_schema import (
    EFFECTIVE_DATA_MODEL_DATABASE, EFFECTIVE_DATA_MODEL_DDL, EFFECTIVE_DATA_MODEL_SCHEMA_VERSION,
    EFFECTIVE_DATA_MODEL_TABLES, MODEL_DOMAIN_CLUSTER_VIEW_SCHEMA_VERSION,
)

from .logical_physical_mapping_builder import build_logical_physical_mapping_knowledge_layer
from .logical_physical_mapping_ingestion import (
    ResolvedKnowledgeLayerInput, ResolvedPersistenceMappingEvidence,
    resolve_knowledge_layer_input, resolve_persistence_mapping_evidence,
)
from .logical_physical_mapping_schema import (
    LOGICAL_PHYSICAL_MAPPING_DATABASE, LOGICAL_PHYSICAL_MAPPING_DDL,
    LOGICAL_PHYSICAL_MAPPING_EVIDENCE_SCHEMA_VERSION, LOGICAL_PHYSICAL_MAPPING_SCHEMA_VERSION,
    LOGICAL_PHYSICAL_MAPPING_TABLES,
)

from .physical_model_builder import build_physical_model_knowledge_layer
from .physical_model_ingestion import (
    ResolvedPhysicalModelArtifact, ingest_physical_model_artifact, resolve_physical_model_artifact,
)
from .physical_model_schema import (
    PHYSICAL_MODEL_DATABASE, PHYSICAL_MODEL_DDL, PHYSICAL_MODEL_FACT_TYPES,
    PHYSICAL_MODEL_SCHEMA_VERSION, PHYSICAL_MODEL_SOURCE_SCHEMA_VERSION, PHYSICAL_MODEL_TABLES,
)

from .schema import SchemaDefinition
from .version import __version__
from prepared_knowledge_runtime.workspace_query import WorkspaceKnowledgeQuery
from prepared_knowledge_runtime.data_model_queries import DataModelQueryService
from prepared_knowledge_runtime.reference_data_queries import ReferenceDataQueryService
from prepared_knowledge_runtime.foreign_data_queries import ForeignDataPersistenceQueryService

from .observed_storage_usage_builder import build_observed_storage_usage_knowledge_layer

from .model_storage_semantics_builder import build_model_storage_semantics_knowledge_layer

from .logical_storage_mapping_builder import build_logical_storage_mapping_knowledge_layer
from .cross_artifact_data_model_builder import build_cross_artifact_data_model_mapping_knowledge_layer
