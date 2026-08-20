"""Production routes for the canonical Knowledge API v1."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from knowledge_api.version import __version__

from .models import (
    AislKnowledgeItemReadResponse,
    AnalysisCoverageResponse,
    AttributePathResolveRequest,
    AttributePathResolveResponse,
    ApiError,
    AttributeExtensionContextResponse,
    AttributeExtensionGuidanceResponse,
    CapabilitiesResponse,
    DataModelLineageResponse,
    DeclaredDataModelSummaryResponse,
    DeclaredDataObjectDetailResponse,
    DataModelObjectContextResponse,
    DeclaredDataObjectListResponse,
    HealthResponse,
    InteractionKnowledgePageResponse,
    SystemInteractionGuidanceResponse,
    SystemDescriptionGuidanceResponse,
    ForeignDataPersistenceGuidanceResponse,
    ForeignDataPersistenceQueryRequest,
    ReferenceDataQueryRequest,
    ReferenceDataGuidanceResponse,
    ReportingKnowledgeQueryRequest,
    ReportingKnowledgeQueryResponse,
    RepositoryInventorySummaryResponse,
    RepositoryInventoryCoverageResponse,
    RepositoryInventoryPageResponse,
    RepositorySourceOccurrenceResponse,
    PortfolioSystemInventory,
    PortfolioInventoryListResponse,
    PortfolioInventoryFacetsResponse,
    PortfolioInteractionGraphResponse,
    KnowledgeArtifactDetailResponse,
    KnowledgeArtifactListResponse,
    ObservedStorageAccessListResponse,
    ObservedStorageGapListResponse,
    PhysicalModelColumnListResponse,
    PhysicalModelGapListResponse,
    PhysicalModelKeyListResponse,
    PhysicalModelRelationshipListResponse,
    PhysicalModelSummaryResponse,
    PhysicalModelTableDetailResponse,
    PhysicalModelTableListResponse,
    RelationshipDetailResponse,
    SqlColumnUsageContextResponse,
    SqlRelationMaterializationListResponse,
    SqlQueryContextResponse,
    SqlRelationListResponse,
    SqlSourceInventoryExportResponse,
    SqlTargetColumnLineageResponse,
    SqlFieldCalculationResponse,
    WorkspaceSqlCatalogResponse,
    SqlTargetCandidatesResponse,
    SqlAttributeInsertionContextRequest,
    SqlAttributeInsertionContextResponse,
    RevisionCreateRequest,
    RevisionCreateResponse,
    RevisionListResponse,
    RevisionCapabilitiesResponse,
    SystemCreateRequest,
    SystemDeleteResponse,
    ArtifactStoreGcRequest,
    ArtifactStoreGcResponse,
    SystemDetails,
    SystemUpdateRequest,
    SystemListResponse,
    SystemRevision,
    TableDetailResponse,
    TableListResponse,
    VersionResponse,
)
from .runtime import KnowledgeApiRuntimeError, KnowledgeApiSettings
from .service import KnowledgeDomainService

KNOWLEDGE_API_PREFIX = "/api/knowledge/v1"
KNOWLEDGE_API_SCHEMA_VERSION = "knowledge_api/v1"

ERROR_RESPONSES = {
    400: {"model": ApiError, "description": "Invalid request"},
    404: {"model": ApiError, "description": "Resource not found"},
    409: {"model": ApiError, "description": "Resource or publication conflict"},
    413: {"model": ApiError, "description": "Published or returned artifact is too large"},
    422: {"model": ApiError, "description": "Payload validation failed"},
    500: {"model": ApiError, "description": "Internal knowledge service error"},
    503: {"model": ApiError, "description": "Knowledge artifact or backing service unavailable"},
}

router = APIRouter(prefix=KNOWLEDGE_API_PREFIX)


def _service(request: Request) -> KnowledgeDomainService:
    service = request.app.state.knowledge_domain
    if service is None:
        service = KnowledgeDomainService(request.app.state.knowledge_settings)
        request.app.state.knowledge_domain = service
    return service


@router.get("/health", response_model=HealthResponse, tags=["service"], responses=ERROR_RESPONSES)
def health(request: Request) -> HealthResponse:
    return _service(request).health()


@router.get("/version", response_model=VersionResponse, tags=["service"], responses=ERROR_RESPONSES)
def version(request: Request) -> VersionResponse:
    return _service(request).version()


@router.get("/capabilities", response_model=CapabilitiesResponse, tags=["service"], responses=ERROR_RESPONSES)
def capabilities(request: Request) -> CapabilitiesResponse:
    return _service(request).capabilities()


@router.post(
    "/artifact-store/gc",
    response_model=ArtifactStoreGcResponse,
    tags=["administration"],
    responses=ERROR_RESPONSES,
)
def artifact_store_gc(request: Request, payload: ArtifactStoreGcRequest) -> ArtifactStoreGcResponse:
    return _service(request).artifact_store_gc(payload)


@router.get(
    "/portfolio/inventory",
    response_model=PortfolioInventoryListResponse,
    response_model_exclude_none=True,
    tags=["portfolio-inventory"],
    responses=ERROR_RESPONSES,
)
def list_portfolio_inventory(
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    search: str | None = None,
    technology: str | None = None,
    protocol: str | None = None,
    has_sql: bool | None = None,
    has_unresolved_peers: bool | None = None,
    source_kind: str | None = None,
    include_unavailable: bool = False,
) -> PortfolioInventoryListResponse:
    return _service(request).list_portfolio_inventory(
        offset=offset, limit=limit, search=search,
        technology=technology, protocol=protocol, has_sql=has_sql,
        has_unresolved_peers=has_unresolved_peers, source_kind=source_kind,
        include_unavailable=include_unavailable,
    )


@router.get(
    "/portfolio/inventory/facets",
    response_model=PortfolioInventoryFacetsResponse,
    response_model_exclude_none=True,
    tags=["portfolio-inventory"],
    responses=ERROR_RESPONSES,
)
def portfolio_inventory_facets(request: Request) -> PortfolioInventoryFacetsResponse:
    return _service(request).portfolio_inventory_facets()


@router.get(
    "/portfolio/inventory/{system_id}",
    response_model=PortfolioSystemInventory,
    response_model_exclude_none=True,
    tags=["portfolio-inventory"],
    responses=ERROR_RESPONSES,
)
def get_portfolio_system_inventory(request: Request, system_id: str) -> PortfolioSystemInventory:
    return _service(request).get_portfolio_system_inventory(system_id)


@router.get(
    "/portfolio/interaction-graph",
    response_model=PortfolioInteractionGraphResponse,
    response_model_exclude_none=True,
    tags=["portfolio-inventory"],
    responses=ERROR_RESPONSES,
)
def portfolio_interaction_graph(request: Request) -> PortfolioInteractionGraphResponse:
    return _service(request).portfolio_interaction_graph()


@router.get(
    "/systems/{system_id}/repository-inventory",
    response_model=RepositoryInventorySummaryResponse,
    response_model_exclude_none=True,
    tags=["repository-inventory"],
    responses=ERROR_RESPONSES,
)
def get_repository_inventory(request: Request, system_id: str, revision_id: str | None = None) -> RepositoryInventorySummaryResponse:
    return _service(request).repository_inventory_summary(system_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/repository-inventory/coverage",
    response_model=RepositoryInventoryCoverageResponse,
    response_model_exclude_none=True,
    tags=["repository-inventory"],
    responses=ERROR_RESPONSES,
)
def get_repository_inventory_coverage(request: Request, system_id: str, revision_id: str | None = None) -> RepositoryInventoryCoverageResponse:
    return _service(request).repository_inventory_coverage(system_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/repository-inventory/technologies",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_technologies(request: Request, system_id: str, revision_id: str | None = None, category: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_technologies(system_id, revision_id=revision_id, category=category, search=search, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/interfaces",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_interfaces(request: Request, system_id: str, revision_id: str | None = None, direction: Literal["inbound", "outbound"] | None = None, protocol: str | None = None, peer_resolution_status: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_interfaces(system_id, revision_id=revision_id, direction=direction, protocol=protocol, peer_resolution_status=peer_resolution_status, search=search, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/inputs",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_inputs(request: Request, system_id: str, revision_id: str | None = None, protocol: str | None = None, peer_resolution_status: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_interfaces(system_id, revision_id=revision_id, direction="inbound", protocol=protocol, peer_resolution_status=peer_resolution_status, search=search, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/outputs",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_outputs(request: Request, system_id: str, revision_id: str | None = None, protocol: str | None = None, peer_resolution_status: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_interfaces(system_id, revision_id=revision_id, direction="outbound", protocol=protocol, peer_resolution_status=peer_resolution_status, search=search, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/structural-families",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_structural_families(request: Request, system_id: str, revision_id: str | None = None, family_kind: str | None = None, discovery_kind: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_structural_families(system_id, revision_id=revision_id, family_kind=family_kind, discovery_kind=discovery_kind, search=search, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/discovery",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_discovery(request: Request, system_id: str, revision_id: str | None = None, discovery_kind: str | None = None, min_salience_score: float = 0.0, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_discovery(system_id, revision_id=revision_id, discovery_kind=discovery_kind, min_salience_score=min_salience_score, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/coverage-gaps",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_coverage_gaps(request: Request, system_id: str, revision_id: str | None = None, gap_kind: str | None = None, discovery_kind: str | None = None, relevance_status: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_coverage_gaps(system_id, revision_id=revision_id, gap_kind=gap_kind, discovery_kind=discovery_kind, relevance_status=relevance_status, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/repository-inventory/source-occurrences",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_source_occurrences(
    request: Request, system_id: str, revision_id: str | None = None,
    object_kind: str | None = None, object_id: str | None = None,
    repository_relative_path: str | None = None, localization_kind: Literal["exact_span", "declaration", "statement", "section", "file"] | None = None,
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_source_occurrences(
        system_id, revision_id=revision_id, object_kind=object_kind, object_id=object_id,
        repository_relative_path=repository_relative_path, localization_kind=localization_kind, offset=offset, limit=limit,
    )


@router.get(
    "/systems/{system_id}/repository-inventory/source-occurrences/{occurrence_id}",
    response_model=RepositorySourceOccurrenceResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def get_repository_inventory_source_occurrence(request: Request, system_id: str, occurrence_id: str, revision_id: str | None = None) -> RepositorySourceOccurrenceResponse:
    return _service(request).get_repository_inventory_source_occurrence(system_id, occurrence_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/repository-inventory/diagnostics",
    response_model=RepositoryInventoryPageResponse, response_model_exclude_none=True, tags=["repository-inventory"], responses=ERROR_RESPONSES,
)
def list_repository_inventory_diagnostics(request: Request, system_id: str, revision_id: str | None = None, severity: str | None = None, code: str | None = None, search: str | None = None, offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RepositoryInventoryPageResponse:
    return _service(request).list_repository_inventory_diagnostics(system_id, revision_id=revision_id, severity=severity, code=code, search=search, offset=offset, limit=limit)




@router.get(
    "/systems/{system_id}/system-description/guidance",
    response_model=SystemDescriptionGuidanceResponse,
    response_model_exclude_none=True,
    tags=["system-description"],
    responses=ERROR_RESPONSES,
)
def get_system_description_guidance(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    technology_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    interface_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    integration_limit: Annotated[int, Query(ge=1, le=50)] = 8,
    event_limit: Annotated[int, Query(ge=1, le=50)] = 8,
    storage_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    journey_limit: Annotated[int, Query(ge=1, le=50)] = 8,
    gap_limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SystemDescriptionGuidanceResponse:
    return _service(request).get_system_description_guidance(
        system_id,
        revision_id=revision_id,
        technology_limit=technology_limit,
        interface_limit=interface_limit,
        integration_limit=integration_limit,
        event_limit=event_limit,
        storage_limit=storage_limit,
        journey_limit=journey_limit,
        gap_limit=gap_limit,
    )


@router.post(
    "/systems/{system_id}/system-description/query",
    response_model=ReportingKnowledgeQueryResponse,
    response_model_exclude_none=True,
    tags=["system-description"],
    responses=ERROR_RESPONSES,
)
def query_system_description(
    request: Request,
    system_id: str,
    body: ReportingKnowledgeQueryRequest,
) -> ReportingKnowledgeQueryResponse:
    return _service(request).query_system_description(system_id, body)




@router.post(
    "/systems/{system_id}/reference-data/query",
    response_model=ReportingKnowledgeQueryResponse,
    response_model_exclude_none=True,
    tags=["reference-data"],
    responses=ERROR_RESPONSES,
)
def query_reference_data(
    request: Request,
    system_id: str,
    body: ReferenceDataQueryRequest,
) -> ReportingKnowledgeQueryResponse:
    return _service(request).query_reference_data(system_id, body)


@router.get(
    "/systems/{system_id}/reference-data/guidance",
    response_model=ReferenceDataGuidanceResponse,
    response_model_exclude_none=True,
    tags=["reference-data"],
    responses=ERROR_RESPONSES,
)
def get_reference_data_guidance(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    token: str = "",
    candidate_limit: Annotated[int, Query(ge=1, le=500)] = 200,
    local_definition_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    literal_write_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    usage_limit: Annotated[int, Query(ge=1, le=50)] = 16,
    gap_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    evidence_limit: Annotated[int, Query(ge=1, le=100)] = 40,
) -> ReferenceDataGuidanceResponse:
    return _service(request).get_reference_data_guidance(
        system_id,
        revision_id=revision_id,
        token=token,
        candidate_limit=candidate_limit,
        local_definition_limit=local_definition_limit,
        literal_write_limit=literal_write_limit,
        usage_limit=usage_limit,
        gap_limit=gap_limit,
        evidence_limit=evidence_limit,
    )


@router.post(
    "/systems/{system_id}/foreign-data-persistence/query",
    response_model=ReportingKnowledgeQueryResponse,
    response_model_exclude_none=True,
    tags=["foreign-data-persistence"],
    responses=ERROR_RESPONSES,
)
def query_foreign_data_persistence(
    request: Request,
    system_id: str,
    body: ForeignDataPersistenceQueryRequest,
) -> ReportingKnowledgeQueryResponse:
    return _service(request).query_foreign_data_persistence(system_id, body)


@router.get(
    "/systems/{system_id}/foreign-data-persistence/guidance",
    response_model=ForeignDataPersistenceGuidanceResponse,
    response_model_exclude_none=True,
    tags=["foreign-data-persistence"],
    responses=ERROR_RESPONSES,
)
def get_foreign_data_persistence_guidance(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    token: str = "",
    path_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    case_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    storage_summary_limit: Annotated[int, Query(ge=1, le=50)] = 12,
    evidence_limit: Annotated[int, Query(ge=1, le=100)] = 40,
) -> ForeignDataPersistenceGuidanceResponse:
    return _service(request).get_foreign_data_persistence_guidance(
        system_id,
        revision_id=revision_id,
        token=token,
        path_limit=path_limit,
        case_limit=case_limit,
        storage_summary_limit=storage_summary_limit,
        evidence_limit=evidence_limit,
    )


@router.post(
    "/systems",
    response_model=SystemDetails,
    status_code=status.HTTP_201_CREATED,
    tags=["systems"],
    responses=ERROR_RESPONSES,
)
def create_system(request: Request, payload: SystemCreateRequest) -> SystemDetails:
    return _service(request).create_system(payload)


@router.get("/systems", response_model=SystemListResponse, tags=["systems"], responses=ERROR_RESPONSES)
def list_systems(
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    search: str | None = None,
) -> SystemListResponse:
    return _service(request).list_systems(offset=offset, limit=limit, search=search)


@router.get("/systems/{system_id}", response_model=SystemDetails, tags=["systems"], responses=ERROR_RESPONSES)
def get_system(request: Request, system_id: str) -> SystemDetails:
    return _service(request).get_system(system_id)


@router.patch(
    "/systems/{system_id}",
    response_model=SystemDetails,
    tags=["systems"],
    responses=ERROR_RESPONSES,
)
def update_system(request: Request, system_id: str, payload: SystemUpdateRequest) -> SystemDetails:
    return _service(request).update_system(system_id, payload)


@router.delete(
    "/systems/{system_id}",
    response_model=SystemDeleteResponse,
    tags=["systems"],
    responses=ERROR_RESPONSES,
)
def delete_system(request: Request, system_id: str) -> SystemDeleteResponse:
    return _service(request).delete_system(system_id)


@router.post(
    "/systems/{system_id}/revisions",
    response_model=RevisionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["revisions"],
    responses=ERROR_RESPONSES,
)
def publish_revision(request: Request, system_id: str, payload: RevisionCreateRequest) -> RevisionCreateResponse:
    return _service(request).publish_revision(system_id, payload)


@router.get(
    "/systems/{system_id}/revisions",
    response_model=RevisionListResponse,
    tags=["revisions"],
    responses=ERROR_RESPONSES,
)
def list_revisions(
    request: Request,
    system_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> RevisionListResponse:
    return _service(request).list_revisions(system_id, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/revisions/{revision_id}",
    response_model=SystemRevision,
    tags=["revisions"],
    responses=ERROR_RESPONSES,
)
def get_revision(request: Request, system_id: str, revision_id: str) -> SystemRevision:
    return _service(request).get_revision(system_id, revision_id)


@router.post(
    "/systems/{system_id}/revisions/{revision_id}/activate",
    response_model=SystemRevision,
    tags=["revisions"],
    responses=ERROR_RESPONSES,
)
def activate_revision(request: Request, system_id: str, revision_id: str) -> SystemRevision:
    return _service(request).activate_revision(system_id, revision_id)


@router.get(
    "/systems/{system_id}/knowledge-artifacts",
    response_model=KnowledgeArtifactListResponse,
    tags=["knowledge-artifacts"],
    responses=ERROR_RESPONSES,
)
def list_knowledge_artifacts(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    model_kind: str | None = None,
    capability: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> KnowledgeArtifactListResponse:
    return _service(request).list_knowledge_artifacts(
        system_id,
        revision_id=revision_id,
        model_kind=model_kind,
        capability=capability,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/knowledge-artifacts/{artifact_id}",
    response_model=KnowledgeArtifactDetailResponse,
    tags=["knowledge-artifacts"],
    responses=ERROR_RESPONSES,
)
def get_knowledge_artifact(
    request: Request,
    system_id: str,
    artifact_id: str,
    revision_id: str | None = None,
) -> KnowledgeArtifactDetailResponse:
    return _service(request).get_knowledge_artifact(
        system_id,
        artifact_id,
        revision_id=revision_id,
    )




@router.get(
    "/systems/{system_id}/knowledge-items/{artifact_id}/{item_kind}/{local_id}",
    response_model=AislKnowledgeItemReadResponse,
    response_model_exclude_none=True,
    tags=["aisl"],
    responses=ERROR_RESPONSES,
)
def get_aisl_knowledge_item(
    request: Request,
    system_id: str,
    artifact_id: str,
    item_kind: str,
    local_id: str,
    revision_id: str | None = None,
) -> AislKnowledgeItemReadResponse:
    return _service(request).get_aisl_knowledge_item(
        system_id,
        artifact_id,
        item_kind,
        local_id,
        revision_id=revision_id,
    )


@router.get(
    "/systems/{system_id}/llm-integration-profile",
    response_model=None,
    tags=["integration"],
    responses=ERROR_RESPONSES,
)
def get_llm_integration_profile(
    request: Request,
    system_id: str,
    profile_id: str,
    revision_id: str | None = None,
) -> dict:
    return _service(request).llm_integration_profile(
        system_id, revision_id=revision_id, profile_id=profile_id
    )


@router.get(
    "/systems/{system_id}/capabilities",
    response_model=RevisionCapabilitiesResponse,
    tags=["knowledge-artifacts"],
    responses=ERROR_RESPONSES,
)
def revision_capabilities(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
) -> RevisionCapabilitiesResponse:
    return _service(request).revision_capabilities(system_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/coverage",
    response_model=AnalysisCoverageResponse,
    tags=["coverage"],
    responses=ERROR_RESPONSES,
)
def analysis_coverage(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
) -> AnalysisCoverageResponse:
    return _service(request).analysis_coverage(system_id, revision_id=revision_id)


@router.post(
    "/systems/{system_id}/attribute-paths/resolve",
    response_model=AttributePathResolveResponse,
    response_model_exclude_none=True,
    tags=["lineage"],
    responses=ERROR_RESPONSES,
)
def resolve_attribute_paths(
    request: Request,
    system_id: str,
    payload: AttributePathResolveRequest,
    revision_id: str | None = None,
) -> AttributePathResolveResponse:
    return _service(request).resolve_attribute_paths(
        system_id, payload, revision_id=revision_id
    )


@router.get(
    "/systems/{system_id}/data-model/tables",
    response_model=TableListResponse,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def list_tables(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    search: str | None = None,
    table_kind: str | None = None,
    include_fields: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> TableListResponse:
    return _service(request).list_tables(
        system_id,
        revision_id=revision_id,
        search=search,
        table_kind=table_kind,
        include_fields=include_fields,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/data-model/tables/{table_id}",
    response_model=TableDetailResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def get_table(request: Request, system_id: str, table_id: str, revision_id: str | None = None) -> TableDetailResponse:
    return _service(request).get_table(system_id, table_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/data-model/tables/{table_id}/relationships/{relationship_id}",
    response_model=RelationshipDetailResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def get_relationship(
    request: Request,
    system_id: str,
    table_id: str,
    relationship_id: str,
    revision_id: str | None = None,
) -> RelationshipDetailResponse:
    return _service(request).get_relationship(
        system_id,
        table_id,
        relationship_id,
        revision_id=revision_id,
    )


@router.get(
    "/systems/{system_id}/physical-model",
    response_model=PhysicalModelSummaryResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def physical_model_summary(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
) -> PhysicalModelSummaryResponse:
    return _service(request).physical_model_summary(system_id, revision_id=revision_id)


@router.get(
    "/systems/{system_id}/physical-model/tables",
    response_model=PhysicalModelTableListResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def list_physical_model_tables(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    source_id: str | None = None,
    search: str | None = None,
    include_columns: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PhysicalModelTableListResponse:
    return _service(request).list_physical_model_tables(
        system_id,
        revision_id=revision_id,
        source_id=source_id,
        search=search,
        include_columns=include_columns,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/physical-model/tables/{table_id}",
    response_model=PhysicalModelTableDetailResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def get_physical_model_table(
    request: Request,
    system_id: str,
    table_id: str,
    revision_id: str | None = None,
) -> PhysicalModelTableDetailResponse:
    return _service(request).get_physical_model_table(
        system_id, table_id, revision_id=revision_id
    )


@router.get(
    "/systems/{system_id}/physical-model/columns",
    response_model=PhysicalModelColumnListResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def list_physical_model_columns(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    table_id: str | None = None,
    source_id: str | None = None,
    search: str | None = None,
    data_type: str | None = None,
    mandatory: bool | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PhysicalModelColumnListResponse:
    return _service(request).list_physical_model_columns(
        system_id,
        revision_id=revision_id,
        table_id=table_id,
        source_id=source_id,
        search=search,
        data_type=data_type,
        mandatory=mandatory,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/physical-model/keys",
    response_model=PhysicalModelKeyListResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def list_physical_model_keys(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    table_id: str | None = None,
    source_id: str | None = None,
    key_kind: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PhysicalModelKeyListResponse:
    return _service(request).list_physical_model_keys(
        system_id,
        revision_id=revision_id,
        table_id=table_id,
        source_id=source_id,
        key_kind=key_kind,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/physical-model/relationships",
    response_model=PhysicalModelRelationshipListResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def list_physical_model_relationships(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    table_id: str | None = None,
    direction: Literal["any", "parent", "child"] = "any",
    source_id: str | None = None,
    resolution_status: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PhysicalModelRelationshipListResponse:
    return _service(request).list_physical_model_relationships(
        system_id,
        revision_id=revision_id,
        table_id=table_id,
        direction=direction,
        source_id=source_id,
        resolution_status=resolution_status,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/physical-model/gaps",
    response_model=PhysicalModelGapListResponse,
    response_model_exclude_none=True,
    tags=["physical-model"],
    responses=ERROR_RESPONSES,
)
def list_physical_model_gaps(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    source_id: str | None = None,
    gap_kind: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> PhysicalModelGapListResponse:
    return _service(request).list_physical_model_gaps(
        system_id,
        revision_id=revision_id,
        source_id=source_id,
        gap_kind=gap_kind,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/storage-usage/accesses",
    response_model=ObservedStorageAccessListResponse,
    response_model_exclude_none=True,
    tags=["storage-usage"],
    responses=ERROR_RESPONSES,
)
def list_observed_storage_accesses(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    access_kind: Literal["read", "write"] | None = None,
    storage_kind: str | None = None,
    target_resolution_status: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ObservedStorageAccessListResponse:
    return _service(request).list_observed_storage_accesses(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        access_kind=access_kind,
        storage_kind=storage_kind,
        target_resolution_status=target_resolution_status,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/storage-usage/gaps",
    response_model=ObservedStorageGapListResponse,
    response_model_exclude_none=True,
    tags=["storage-usage"],
    responses=ERROR_RESPONSES,
)
def list_observed_storage_gaps(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    gap_code: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> ObservedStorageGapListResponse:
    return _service(request).list_observed_storage_gaps(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        gap_code=gap_code,
        severity=severity,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/sql/relations",
    response_model=SqlRelationListResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def list_sql_relations(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    relation_kind: str | None = None,
    usage_role: str | None = None,
    view: Literal["business_sources", "technical", "all"] = "business_sources",
    search: str | None = None,
    include_fields: bool = True,
    max_evidence_per_role: Annotated[int, Query(ge=1, le=20)] = 3,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> SqlRelationListResponse:
    return _service(request).list_sql_relations(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        relation_kind=relation_kind,
        usage_role=usage_role,
        view=view,
        search=search,
        include_fields=include_fields,
        max_evidence_per_role=max_evidence_per_role,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/sql/source-inventory",
    response_model=SqlSourceInventoryExportResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def export_sql_source_inventory(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    relation_kind: str | None = None,
    usage_role: str | None = None,
    view: Literal["business_sources", "technical", "all"] = "business_sources",
    search: str | None = None,
    max_evidence_per_role: Annotated[int, Query(ge=1, le=20)] = 3,
) -> SqlSourceInventoryExportResponse:
    return _service(request).export_sql_source_inventory(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        relation_kind=relation_kind,
        usage_role=usage_role,
        view=view,
        search=search,
        max_evidence_per_role=max_evidence_per_role,
    )


@router.get(
    "/systems/{system_id}/sql/source-inventory.jsonl",
    response_class=Response,
    response_model=None,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def export_sql_source_inventory_jsonl(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    relation_kind: str | None = None,
    usage_role: str | None = None,
    view: Literal["business_sources", "technical", "all"] = "business_sources",
    search: str | None = None,
    max_evidence_per_role: Annotated[int, Query(ge=1, le=20)] = 3,
) -> Response:
    export = _service(request).export_sql_source_inventory(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        relation_kind=relation_kind,
        usage_role=usage_role,
        view=view,
        search=search,
        max_evidence_per_role=max_evidence_per_role,
    )
    value = export.model_dump(mode="json", exclude_none=True)
    header = {
        "record_type": "inventory_metadata",
        "schema_version": value["inventory_schema_version"],
        "system_id": value["system_id"],
        "revision_id": value["revision_id"],
        "filters": value["filters"],
        "item_count": value["item_count"],
        "coverage": value["coverage"],
    }
    records = [header]
    records.extend({"record_type": "source_relation", "relation": item} for item in value["items"])
    content = b"".join(
        (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for record in records
    )
    digest = hashlib.sha256(content).hexdigest()
    filename = f"{system_id}-sql-source-inventory.jsonl"
    return Response(
        content=content,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": digest,
            "X-Record-Count": str(len(records)),
        },
    )


@router.get(
    "/systems/{system_id}/interactions",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_system_interactions(
    request: Request, system_id: str, revision_id: str | None = None,
    source_repo_id: str | None = None, target_repo_id: str | None = None, protocol: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_system_interactions(system_id, revision_id=revision_id, source_repo_id=source_repo_id, target_repo_id=target_repo_id, protocol=protocol, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/interactions/boundary-interactions",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_system_boundary_interactions(
    request: Request, system_id: str, revision_id: str | None = None, interaction_id: str | None = None,
    source_repo_id: str | None = None, target_repo_id: str | None = None, match_status: str | None = None,
    confidence: str | None = None, local_execution_status: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_system_boundary_interactions(
        system_id, revision_id=revision_id, interaction_id=interaction_id, source_repo_id=source_repo_id,
        target_repo_id=target_repo_id, match_status=match_status, confidence=confidence,
        local_execution_status=local_execution_status, offset=offset, limit=limit,
    )


@router.get(
    "/systems/{system_id}/interactions/{interaction_id}/guidance",
    response_model=SystemInteractionGuidanceResponse,
    response_model_exclude_none=True,
    tags=["interactions"],
    responses=ERROR_RESPONSES,
)
def get_system_interaction_guidance(
    request: Request,
    system_id: str,
    interaction_id: str,
    revision_id: str | None = None,
    context_limit: Annotated[int, Query(ge=1, le=20)] = 8,
    field_limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SystemInteractionGuidanceResponse:
    return _service(request).get_system_interaction_guidance(
        system_id,
        revision_id=revision_id,
        interaction_id=interaction_id,
        context_limit=context_limit,
        field_limit=field_limit,
    )


@router.get(
    "/systems/{system_id}/interactions/boundaries",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_repository_interaction_boundaries(
    request: Request, system_id: str, revision_id: str | None = None, repo_id: str | None = None,
    repository_system_id: str | None = None, project_id: str | None = None, direction: str | None = None,
    protocol: str | None = None, http_method: str | None = None, service_identity: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_repository_interaction_boundaries(system_id, revision_id=revision_id, repo_id=repo_id, repository_system_id=repository_system_id, project_id=project_id, direction=direction, protocol=protocol, http_method=http_method, service_identity=service_identity, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/interactions/execution-contexts",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_system_interaction_execution_contexts(
    request: Request, system_id: str, revision_id: str | None = None, boundary_interaction_id: str | None = None,
    interaction_id: str | None = None, source_repo_id: str | None = None, trigger_kind: str | None = None,
    path_status: str | None = None, offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_system_interaction_execution_contexts(system_id, revision_id=revision_id, boundary_interaction_id=boundary_interaction_id, interaction_id=interaction_id, source_repo_id=source_repo_id, trigger_kind=trigger_kind, path_status=path_status, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/interactions/field-contracts",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_system_interaction_field_contracts(
    request: Request, system_id: str, revision_id: str | None = None, boundary_interaction_id: str | None = None,
    interaction_id: str | None = None, source_repo_id: str | None = None, target_repo_id: str | None = None,
    wire_path: str | None = None, match_status: str | None = None, offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_system_interaction_field_contracts(system_id, revision_id=revision_id, boundary_interaction_id=boundary_interaction_id, interaction_id=interaction_id, source_repo_id=source_repo_id, target_repo_id=target_repo_id, wire_path=wire_path, match_status=match_status, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/interactions/diagnostics",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_system_interaction_diagnostics(
    request: Request, system_id: str, revision_id: str | None = None, source_repo_id: str | None = None,
    match_status: str | None = None, offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_system_interaction_diagnostics(system_id, revision_id=revision_id, source_repo_id=source_repo_id, match_status=match_status, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/interactions/coverage",
    response_model=InteractionKnowledgePageResponse, response_model_exclude_none=True,
    tags=["interactions"], responses=ERROR_RESPONSES,
)
def list_repository_interaction_coverage(
    request: Request, system_id: str, revision_id: str | None = None, repo_id: str | None = None,
    repository_system_id: str | None = None, project_id: str | None = None, coverage_status: str | None = None,
    matching_coverage_status: str | None = None, offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> InteractionKnowledgePageResponse:
    return _service(request).list_repository_interaction_coverage(system_id, revision_id=revision_id, repo_id=repo_id, repository_system_id=repository_system_id, project_id=project_id, coverage_status=coverage_status, matching_coverage_status=matching_coverage_status, offset=offset, limit=limit)


@router.get(
    "/systems/{system_id}/data-model/declared-summary",
    response_model=DeclaredDataModelSummaryResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def summarize_declared_data_model(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    type_annotations: str | None = None,
    exclude_field_annotations: str | None = None,
) -> DeclaredDataModelSummaryResponse:
    return _service(request).summarize_declared_data_model(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        type_annotations=type_annotations,
        exclude_field_annotations=exclude_field_annotations,
    )


@router.get(
    "/systems/{system_id}/data-model/declared-objects",
    response_model=DeclaredDataObjectListResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def list_declared_data_objects(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    search: str | None = None,
    type_annotations: str | None = None,
    include_fields: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> DeclaredDataObjectListResponse:
    return _service(request).list_declared_data_objects(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        search=search,
        type_annotations=type_annotations,
        include_fields=include_fields,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/data-model/declared-objects/{object_id}",
    response_model=DeclaredDataObjectDetailResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def get_declared_data_object(
    request: Request,
    system_id: str,
    object_id: str,
    revision_id: str | None = None,
) -> DeclaredDataObjectDetailResponse:
    return _service(request).get_declared_data_object(
        system_id,
        object_id,
        revision_id=revision_id,
    )


@router.get(
    "/systems/{system_id}/data-model/object-context/{object_id}",
    response_model=DataModelObjectContextResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def get_data_model_object_context(
    request: Request,
    system_id: str,
    object_id: str,
    revision_id: str | None = None,
) -> DataModelObjectContextResponse:
    return _service(request).get_data_model_object_context(
        system_id,
        object_id,
        revision_id=revision_id,
    )


@router.get(
    "/systems/{system_id}/data-model/attribute-extension-context",
    response_model=AttributeExtensionContextResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def list_attribute_extension_context(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    source_type: str | None = None,
    source_field: str | None = None,
    target_type: str | None = None,
    join_method: str | None = None,
    confidence: str | None = None,
    sql_generation_status: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AttributeExtensionContextResponse:
    return _service(request).list_attribute_extension_context(
        system_id,
        revision_id=revision_id,
        source_type=source_type,
        source_field=source_field,
        target_type=target_type,
        join_method=join_method,
        confidence=confidence,
        sql_generation_status=sql_generation_status,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/data-model/attribute-extension-guidance",
    response_model=AttributeExtensionGuidanceResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def get_attribute_extension_guidance(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    source_type: str | None = None,
    source_field: str | None = None,
    target_type: str | None = None,
    join_method: str | None = None,
    confidence: str | None = None,
    sql_generation_status: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AttributeExtensionGuidanceResponse:
    return _service(request).get_attribute_extension_guidance(
        system_id,
        revision_id=revision_id,
        source_type=source_type,
        source_field=source_field,
        target_type=target_type,
        join_method=join_method,
        confidence=confidence,
        sql_generation_status=sql_generation_status,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/data-model/lineage",
    response_model=DataModelLineageResponse,
    response_model_exclude_none=True,
    tags=["data-model"],
    responses=ERROR_RESPONSES,
)
def list_data_model_lineage(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    logical_type: str | None = None,
    logical_field: str | None = None,
    target_table: str | None = None,
    target_column: str | None = None,
    knowledge_class: str | None = None,
    search: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> DataModelLineageResponse:
    return _service(request).list_data_model_lineage(
        system_id,
        revision_id=revision_id,
        logical_type=logical_type,
        logical_field=logical_field,
        target_table=target_table,
        target_column=target_column,
        knowledge_class=knowledge_class,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/systems/{system_id}/sql/target-column-lineage",
    response_model=SqlTargetColumnLineageResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def list_sql_target_column_lineage(
    request: Request,
    system_id: str,
    target_relation: Annotated[str, Query(min_length=1, max_length=10000)],
    revision_id: str | None = None,
    target_column: Annotated[str | None, Query(min_length=1, max_length=10000)] = None,
    repo_id: str | None = None,
    lineage_status: str | None = None,
    include_gaps: bool = True,
    max_gaps: Annotated[int, Query(ge=1, le=500)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> SqlTargetColumnLineageResponse:
    return _service(request).list_sql_target_column_lineage(
        system_id,
        revision_id=revision_id,
        target_relation=target_relation,
        target_column=target_column,
        repo_id=repo_id,
        lineage_status=lineage_status,
        include_gaps=include_gaps,
        max_gaps=max_gaps,
        offset=offset,
        limit=limit,
    )

@router.get(
    "/systems/{system_id}/sql/field-calculation",
    response_model=SqlFieldCalculationResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def get_sql_field_calculation(
    request: Request,
    system_id: str,
    target_relation: Annotated[str, Query(min_length=1, max_length=10000)],
    target_column: Annotated[str, Query(min_length=1, max_length=10000)],
    revision_id: str | None = None,
    repo_id: str | None = None,
    include_gaps: bool = True,
    max_gaps: Annotated[int, Query(ge=1, le=500)] = 500,
) -> SqlFieldCalculationResponse:
    return _service(request).get_sql_field_calculation(
        system_id,
        revision_id=revision_id,
        target_relation=target_relation,
        target_column=target_column,
        repo_id=repo_id,
        include_gaps=include_gaps,
        max_gaps=max_gaps,
    )


@router.get(
    "/systems/{system_id}/sql/workspace-catalog",
    response_model=WorkspaceSqlCatalogResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def get_workspace_sql_catalog(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
) -> WorkspaceSqlCatalogResponse:
    return _service(request).get_workspace_sql_catalog(
        system_id, revision_id=revision_id
    )


@router.get(
    "/systems/{system_id}/sql/target-candidates",
    response_model=SqlTargetCandidatesResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def find_sql_target_candidates(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    repo_id: str | None = None,
    source_relation: Annotated[list[str] | None, Query()] = None,
    source_column: Annotated[list[str] | None, Query()] = None,
    business_entity: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SqlTargetCandidatesResponse:
    return _service(request).find_sql_target_candidates(
        system_id,
        revision_id=revision_id,
        repo_id=repo_id,
        source_relation_hints=source_relation,
        source_column_hints=source_column,
        business_entity_hints=business_entity,
        max_results=limit,
    )


@router.post(
    "/systems/{system_id}/sql/attribute-insertion-context",
    response_model=SqlAttributeInsertionContextResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def resolve_sql_attribute_insertion_context(
    request: Request,
    system_id: str,
    payload: SqlAttributeInsertionContextRequest,
    revision_id: str | None = None,
) -> SqlAttributeInsertionContextResponse:
    return _service(request).resolve_sql_attribute_insertion_context(
        system_id,
        payload,
        revision_id=revision_id,
    )


@router.get(
    "/systems/{system_id}/sql/relation-materializations",
    response_model=SqlRelationMaterializationListResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def list_sql_relation_materializations(
    request: Request,
    system_id: str,
    revision_id: str | None = None,
    output_table_name: Annotated[str | None, Query(min_length=1, max_length=10000)] = None,
    query_id: Annotated[str | None, Query(min_length=1, max_length=10000)] = None,
    workflow_context_file: Annotated[str | None, Query(min_length=1, max_length=10000)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SqlRelationMaterializationListResponse:
    return _service(request).list_sql_relation_materializations(
        system_id, revision_id=revision_id, output_table_name=output_table_name,
        query_id=query_id, workflow_context_file=workflow_context_file,
        offset=offset, limit=limit,
    )


@router.get(
    "/systems/{system_id}/sql/query-context",
    response_model=SqlQueryContextResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def get_sql_query_context(
    request: Request,
    system_id: str,
    repo_id: Annotated[str, Query(min_length=1, max_length=10000)],
    query_id: Annotated[str, Query(min_length=1, max_length=10000)],
    revision_id: str | None = None,
    scope_id: Annotated[str | None, Query(min_length=1, max_length=10000)] = None,
) -> SqlQueryContextResponse:
    return _service(request).get_sql_query_context(
        system_id, revision_id=revision_id, repo_id=repo_id, query_id=query_id, scope_id=scope_id
    )


@router.get(
    "/systems/{system_id}/sql/column-usages/{sql_column_usage_id}",
    response_model=SqlColumnUsageContextResponse,
    response_model_exclude_none=True,
    tags=["sql"],
    responses=ERROR_RESPONSES,
)
def get_sql_column_usage_context(
    request: Request,
    system_id: str,
    sql_column_usage_id: str,
    revision_id: str | None = None,
) -> SqlColumnUsageContextResponse:
    return _service(request).get_sql_column_usage_context(
        system_id,
        sql_column_usage_id,
        revision_id=revision_id,
    )




def create_contract_app(
    *,
    settings: KnowledgeApiSettings | None = None,
    service: KnowledgeDomainService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Knowledge API",
        version=__version__,
        description=(
            "Canonical producer-neutral HTTP API for publishing and consuming versioned knowledge artifacts. "
            "It contains no orchestration jobs, UI state, arbitrary SQL, or LLM execution endpoints."
        ),
    )
    app.state.knowledge_domain = service
    app.state.knowledge_settings = settings or KnowledgeApiSettings.from_environment()

    @app.exception_handler(KnowledgeApiRuntimeError)
    async def runtime_error_handler(_request: Request, exc: KnowledgeApiRuntimeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiError(code=exc.code, message=exc.message, details=exc.details).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ApiError(
                code="request_validation_failed",
                message="request payload or parameters are invalid",
                details={
                    "errors": [
                        {key: value for key, value in error.items() if key != "url"}
                        for error in jsonable_encoder(exc.errors())
                    ]
                },
            ).model_dump(mode="json"),
        )

    app.include_router(router)
    return app
