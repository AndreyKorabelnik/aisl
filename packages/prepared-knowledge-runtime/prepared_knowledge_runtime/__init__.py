from .analysis_coverage import ANALYSIS_COVERAGE_SCHEMA_VERSION, build_analysis_coverage
from .attribute_paths import ATTRIBUTE_PATH_SCHEMA_VERSION, resolve_attribute_paths
from .consumer_contracts import (
    CONSUMER_SCHEMA_VERSION, EvidenceRef, Gap, Page, QueryRequest, QueryResult, ScopeRef, evidence_index,
)
from .contracts import ARTIFACT_ID, SCHEMA_VERSION, SUPPORTED_MODES, KnowledgeLayerManifest, derive_scope_type
from .database import connect_database, initialize_schema, require_duckdb
from .errors import KnowledgeLayerContractError
from .foreign_data_queries import ForeignDataPersistenceQueryService
from .io import load_manifest, read_json, write_json, write_manifest
from .normalization import normalize_db_identifier, normalize_field_correspondence_path, normalize_text, stable_id
from .query import KnowledgeLayerQuery
from .reference_data_queries import ReferenceDataQueryService
from .reporting_queries import ReportingQueryService
from .workspace_query import WorkspaceKnowledgeQuery
from .data_model_queries import DataModelQueryService
from .version import __version__

__all__ = [
    "ANALYSIS_COVERAGE_SCHEMA_VERSION", "ATTRIBUTE_PATH_SCHEMA_VERSION", "ARTIFACT_ID", "SCHEMA_VERSION",
    "SUPPORTED_MODES", "CONSUMER_SCHEMA_VERSION", "EvidenceRef", "Gap", "Page", "QueryRequest",
    "QueryResult", "ScopeRef", "KnowledgeLayerManifest", "KnowledgeLayerContractError", "KnowledgeLayerQuery",
    "WorkspaceKnowledgeQuery", "DataModelQueryService", "ReferenceDataQueryService", "JavaTypeStructureEvidenceQuery", "SqlAnalysisEvidenceQuery",
    "ForeignDataPersistenceQueryService", "ReportingQueryService", "build_analysis_coverage",
    "connect_database", "derive_scope_type", "evidence_index", "initialize_schema", "load_manifest",
    "normalize_db_identifier", "normalize_field_correspondence_path", "normalize_text", "read_json",
    "require_duckdb", "resolve_attribute_paths", "stable_id", "write_json", "write_manifest", "__version__",
]

from .java_type_structure_queries import JavaTypeStructureEvidenceQuery
from .sql_analysis_evidence_queries import SqlAnalysisEvidenceQuery
