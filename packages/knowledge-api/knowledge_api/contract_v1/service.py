from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from knowledge_integration import RevisionContext, generate_integration_profile
from prepared_knowledge_runtime import JavaTypeStructureEvidenceQuery, SqlAnalysisEvidenceQuery

from knowledge_api.query_source import KnowledgeArtifactSource
from knowledge_api.artifact_store import AislArtifactStore
from knowledge_api.data_model_lineage_query import (
    CachedDataModelLineageQueryFactory,
    DataModelLineageQueryFactory,
    DataModelLineageUnavailableError,
)
from knowledge_api.effective_data_model_query import (
    DataObjectNotFoundError,
    RelationshipNotFoundError,
    EffectiveDataModelUnavailableError,
    CachedEffectiveDataModelQueryFactory,
    EffectiveDataModelQueryFactory,
)
from knowledge_api.version import __version__
from knowledge_api.portfolio_inventory import (
    aggregate_system_inventory, build_facets, build_interaction_graph, matches_portfolio_filters,
)
from knowledge_api.publication import (
    build_artifact,
    discover_knowledge_artifact_files,
    discover_observed_artifact_files,
    execution_summary,
    load_json_object,
    observed_product_slot_id,
    validate_knowledge_execution_result,
)
from knowledge_api.storage_usage_query import (
    CachedStorageUsageQueryFactory,
    ObservedStorageUsageUnavailableError,
    StorageUsageQueryFactory,
)
from knowledge_api.reporting_query import (
    CachedReportingKnowledgeQueryFactory,
    ReportingKnowledgeQueryFactory,
    ReportingKnowledgeUnavailableError,
)
from knowledge_api.foreign_data_persistence_query import (
    CachedForeignDataPersistenceQueryFactory,
    ForeignDataPersistenceQueryFactory,
    ForeignDataPersistenceKnowledgeUnavailableError,
)
from knowledge_api.reference_data_query import (
    CachedReferenceDataQueryFactory,
    ReferenceDataQueryFactory,
    ReferenceDataKnowledgeUnavailableError,
)
from knowledge_api.sql_query import (
    CachedKnowledgeQueryFactory,
    KnowledgeArtifactUnavailableError,
    KnowledgeQueryFactory,
    SqlAnalysisUnavailableError,
    SqlColumnUsageNotFoundError,
    PhysicalModelUnavailableError,
    PhysicalModelTableNotFoundError,
    AttributeExtensionContextUnavailableError,
)

from knowledge_api.data_model_object_context import build_data_model_object_context

from .consumer_projections import (
    project_attribute_extension_guidance,
    project_foreign_data_persistence_guidance,
    project_reference_data_guidance,
    project_system_interaction_guidance,
    project_system_description_guidance,
)
from .models import (
    AislCrossProductCorrespondence,
    AislCorrespondenceEndpoint,
    AislEvidence,
    AislEvidenceBinding,
    AislKnowledgeIssue,
    AislKnowledgeItemReadResponse,
    AislKnowledgeItemRef,
    AislReadFacetAvailability,
    AislReadFacetState,
    AislSourceFragment,
    AnalysisCoverageResponse,
    AttributePathResolveRequest,
    AttributePathResolveResponse,
    CapabilitiesResponse,
    AttributeExtensionContextResponse,
    AttributeExtensionGuidanceResponse,
    AttributeExtensionContextSummary,
    AttributeExtensionJoinSemantic,
    Capability,
    CapabilityStatus,
    DataObjectRef,
    DeclaredDataObjectDetail,
    DeclaredDataModelSummaryResponse,
    DeclaredDataObjectDetailResponse,
    DataModelObjectContextResponse,
    DeclaredDataObjectListResponse,
    DeclaredDataObjectSummary,
    DataModelLineageItem,
    DataModelLineageResponse,
    DataModelLineageSummary,
    FieldSummary,
    HealthResponse,
    HealthStatus,
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
    ObservedStorageAccess,
    ObservedStorageAccessListResponse,
    ObservedStorageGap,
    ObservedStorageGapListResponse,
    ObservedStorageSummary,
    PageMeta,
    PublishedArtifact,
    ProductPhysicalArtifact,
    PublishedKnowledgeArtifact,
    ProductOriginKind,
    RevisionCapabilitiesResponse,
    PhysicalModelColumn,
    PhysicalModelColumnListResponse,
    PhysicalModelGap,
    PhysicalModelGapListResponse,
    PhysicalModelKey,
    PhysicalModelKeyListResponse,
    PhysicalModelRelationship,
    PhysicalModelRelationshipListResponse,
    PhysicalModelSource,
    PhysicalModelSummaryResponse,
    PhysicalModelTableDetailResponse,
    PhysicalModelTableListResponse,
    PhysicalModelTableSummary,
    RelationshipDetailResponse,
    SqlAnalysisCoverage,
    SqlColumnUsageContextCounts,
    SqlColumnUsageContextResponse,
    SqlColumnUsageContextUsage,
    SqlRelationMaterialization,
    SqlRelationMaterializationListResponse,
    SqlQueryContextCounts,
    SqlQueryContextResponse,
    SqlJoinContext,
    SqlProjectionContext,
    SqlScopeRelationContext,
    SqlScopeRelationObservedField,
    SqlSelectScopeContext,
    SqlStatementContext,
    SqlTargetColumnLineageResponse,
    SqlFieldCalculationResponse,
    WorkspaceSqlCatalogResponse,
    SqlTargetCandidatesResponse,
    SqlAttributeInsertionContextRequest,
    SqlAttributeInsertionContextResponse,
    SqlAnalysisRepositoryCoverage,
    SqlEvidenceRef,
    SqlRelationFieldSummary,
    SqlRelationClassificationCoverage,
    SqlSourceInventoryCoverage,
    SqlRelationListResponse,
    SqlRelationSummary,
    SqlSourceInventoryExportResponse,
    RevisionCreateRequest,
    RevisionCreateResponse,
    RevisionListResponse,
    RevisionState,
    SystemCreateRequest,
    SystemDeleteResponse,
    ArtifactStoreGcMode,
    ArtifactStoreGcRequest,
    ArtifactStoreGcResponse,
    SystemDetails,
    SystemUpdateRequest,
    SystemListResponse,
    SystemRevision,
    SystemSummary,
    TableDetailResponse,
    TableField,
    TableKey,
    TableListResponse,
    TableRelationship,
    TableRelationshipSummary,
    TableSummary,
    VersionResponse,
)
from .runtime import ArtifactValidator, KnowledgeApiRuntimeError, KnowledgeApiSettings
from .store import KnowledgeStore, utc_now


def _product_artifact_by_role(product: PublishedKnowledgeArtifact, role: str) -> ProductPhysicalArtifact | None:
    matches = [item for item in product.physical_artifacts if str(item.role) == role]
    if len(matches) > 1:
        raise KnowledgeApiRuntimeError(500, "published_product_role_ambiguous", "published KnowledgeProduct contains duplicate physical role", details={"artifact_id": str(product.artifact_id), "role": role})
    return matches[0] if matches else None


def _product_artifact_dict_by_role(product: Mapping[str, Any], role: str) -> dict[str, Any] | None:
    matches = [dict(item) for item in product.get("physical_artifacts") or () if isinstance(item, Mapping) and str(item.get("role") or "") == role]
    if len(matches) > 1:
        raise KnowledgeApiRuntimeError(500, "published_product_role_ambiguous", "published KnowledgeProduct contains duplicate physical role", details={"artifact_id": str(product.get("artifact_id") or ""), "role": role})
    return matches[0] if matches else None


class KnowledgeDomainService:
    def __init__(
        self,
        settings: KnowledgeApiSettings,
        *,
        store: KnowledgeStore | None = None,
        query_factory: EffectiveDataModelQueryFactory | None = None,
        knowledge_query_factory: KnowledgeQueryFactory | None = None,
        storage_query_factory: StorageUsageQueryFactory | None = None,
        data_model_lineage_query_factory: DataModelLineageQueryFactory | None = None,
        reporting_query_factory: ReportingKnowledgeQueryFactory | None = None,
        foreign_data_persistence_query_factory: ForeignDataPersistenceQueryFactory | None = None,
        reference_data_query_factory: ReferenceDataQueryFactory | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or KnowledgeStore(settings.database_path)
        self.validator = ArtifactValidator(settings)
        assert settings.artifact_store_path is not None
        self.artifact_store = AislArtifactStore(settings.artifact_store_path)
        self.query_factory = query_factory or CachedEffectiveDataModelQueryFactory()
        self.knowledge_query_factory = knowledge_query_factory or CachedKnowledgeQueryFactory()
        self.storage_query_factory = storage_query_factory or CachedStorageUsageQueryFactory()
        self.data_model_lineage_query_factory = data_model_lineage_query_factory or CachedDataModelLineageQueryFactory()
        self.reporting_query_factory = reporting_query_factory or CachedReportingKnowledgeQueryFactory()
        self.foreign_data_persistence_query_factory = (
            foreign_data_persistence_query_factory or CachedForeignDataPersistenceQueryFactory()
        )
        self.reference_data_query_factory = reference_data_query_factory or CachedReferenceDataQueryFactory()
        self._portfolio_repository_snapshot_cache: dict[str, tuple[str, int, int, dict[str, Any]]] = {}

    def health(self) -> HealthResponse:
        return HealthResponse(status=HealthStatus.OK, version=__version__)

    def version(self) -> VersionResponse:
        return VersionResponse(service_version=__version__, generated_at=datetime.now(timezone.utc))

    def capabilities(self) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            capabilities=[
                Capability(id="system_publication", status=CapabilityStatus.AVAILABLE, description="Publish completed knowledge_execution_result/v2 revisions."),
                Capability(id="artifact_store_gc", status=CapabilityStatus.AVAILABLE, description="Plan or sweep unreachable AISL Artifact Store blobs from retained revision reachability without refcount state."),
                Capability(id="typed_knowledge_artifacts", status=CapabilityStatus.AVAILABLE, description="List typed knowledge artifacts and revision capabilities."),
                Capability(id="aisl_universal_item_read", status=CapabilityStatus.AVAILABLE, description="Read one published typed knowledge item through the universal AISL address/evidence/quality envelope when its product kind exposes an official projection."),
                Capability(id="revision_history", status=CapabilityStatus.AVAILABLE, description="Read active and historical revisions."),
                Capability(id="portfolio_inventory", status=CapabilityStatus.AVAILABLE, description="Aggregate published Repository Inventory revisions into a read-only system portfolio projection with filters, facets and interaction observations."),
                Capability(id="data_model", status=CapabilityStatus.AVAILABLE, description="Query logical data-model tables, fields, keys and relationships."),
                Capability(id="declared_data_model", status=CapabilityStatus.AVAILABLE, description="Search and inspect code-declared data objects, effective inherited fields, relationships and source provenance from prepared knowledge."),
                Capability(id="data_model_lineage", status=CapabilityStatus.AVAILABLE, description="Query canonical value-origin to physical-target lineage with SQL transformations and provenance."),
                Capability(id="data_model_attribute_extension", status=CapabilityStatus.AVAILABLE, description="Query KLC-materialized agent-ready relationship JOIN semantics, SQL anchors, provenance and gaps for extending data products."),
                Capability(id="target_source_mapping", status=CapabilityStatus.AVAILABLE, description="Query compact target-column to ultimate-source mappings from canonical product S2T knowledge."),
                Capability(id="physical_model", status=CapabilityStatus.AVAILABLE, description="Query PDM physical tables, columns, keys, relationships and gaps."),
                Capability(id="sql_analysis", status=CapabilityStatus.AVAILABLE, description="Query SQL relations with actually used fields, roles, coverage and evidence."),
                Capability(id="observed_storage_usage", status=CapabilityStatus.AVAILABLE, description="Query observed storage reads, writes and unresolved access gaps."),
                Capability(id="foreign_data_persistence", status=CapabilityStatus.AVAILABLE, description="Query KLC-produced source-to-storage, storage-to-access and exact-field mechanical FDP paths without assigning a business risk verdict."),
                Capability(id="reference_data", status=CapabilityStatus.AVAILABLE, description="Query KLC-produced declared value sets, literal population targets, usage evidence and unresolved gaps without declaring official NSI status or ownership."),
                Capability(id="attribute_paths", status=CapabilityStatus.AVAILABLE, description="Resolve local or enriched cross-repository attribute paths with deterministic knowledge views."),
                Capability(id="reporting_queries", status=CapabilityStatus.AVAILABLE, description="Execute canonical KLC ReportingQueryService reads against a prepared revision, including System Description knowledge."),
            ]
        )

    def create_system(self, request: SystemCreateRequest) -> SystemDetails:
        created = utc_now()
        if not self.store.create_system(
            system_id=request.system_id,
            display_name=request.display_name,
            description=request.description,
            metadata=request.metadata,
            created_at=created,
        ):
            raise KnowledgeApiRuntimeError(409, "system_exists", f"system already exists: {request.system_id}")
        return self.get_system(request.system_id)

    def list_systems(self, *, offset: int, limit: int, search: str | None) -> SystemListResponse:
        rows = self.store.list_systems(search=search)
        return SystemListResponse(
            items=[self._system_summary(row) for row in rows[offset : offset + limit]],
            page=PageMeta(offset=offset, limit=limit, total=len(rows)),
        )

    def get_system(self, system_id: str) -> SystemDetails:
        row = self.store.get_system(system_id)
        if row is None:
            raise KnowledgeApiRuntimeError(404, "system_not_found", f"unknown system: {system_id}")
        return SystemDetails(**self._system_summary(row).model_dump(), metadata=row["metadata"])

    def update_system(self, system_id: str, request: SystemUpdateRequest) -> SystemDetails:
        updated = self.store.update_system(
            system_id,
            display_name_set="display_name" in request.model_fields_set,
            display_name=request.display_name,
            description_set="description" in request.model_fields_set,
            description=request.description,
            metadata_patch=request.metadata,
            updated_at=utc_now(),
        )
        if not updated:
            raise KnowledgeApiRuntimeError(404, "system_not_found", f"unknown system: {system_id}")
        return self.get_system(system_id)

    def delete_system(self, system_id: str) -> SystemDeleteResponse:
        deleted_revision_count = self.store.delete_system(system_id)
        if deleted_revision_count is None:
            raise KnowledgeApiRuntimeError(404, "system_not_found", f"unknown system: {system_id}")
        return SystemDeleteResponse(
            system_id=system_id,
            deleted_revision_count=deleted_revision_count,
        )

    def artifact_store_gc(self, request: ArtifactStoreGcRequest) -> ArtifactStoreGcResponse:
        """Plan or sweep CAS blobs unreachable from every retained revision."""
        started = utc_now()
        cutoff = started - timedelta(seconds=request.grace_period_seconds)
        with self.artifact_store.lifecycle_lock():
            revisions = self.store.list_all_revisions()
            reachable: set[str] = set()
            for row in revisions:
                try:
                    revision = SystemRevision.model_validate(row)
                except ValidationError as exc:
                    raise KnowledgeApiRuntimeError(
                        500,
                        "artifact_gc_catalog_revision_invalid",
                        "cannot compute Artifact Store reachability from an invalid retained revision",
                        details={"revision_id": str(row.get("revision_id") or "")},
                    ) from exc
                reachable.add(str(revision.execution_result.sha256))
                for product in revision.knowledge_artifacts:
                    reachable.update(str(item.sha256) for item in product.physical_artifacts)

            inventory = self.artifact_store.inventory()
            by_digest = {item.sha256: item for item in inventory.blobs}
            referenced_present = reachable.intersection(by_digest)
            missing_referenced = sorted(reachable.difference(by_digest))
            unreferenced = [item for item in inventory.blobs if item.sha256 not in reachable]
            eligible = [item for item in unreferenced if item.modified_at <= cutoff]
            young = [item for item in unreferenced if item.modified_at > cutoff]

            eligible_staging = []
            for path in inventory.staging_files:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if modified <= cutoff:
                    eligible_staging.append(path)

            deleted_blobs = 0
            deleted_staging = 0
            if request.mode == ArtifactStoreGcMode.SWEEP:
                for item in eligible:
                    deleted_blobs += int(self.artifact_store.delete_blob(item.sha256))
                for path in eligible_staging:
                    deleted_staging += int(self.artifact_store.delete_staging_file(path))

        detail_limit = request.max_details
        eligible_digests = sorted(item.sha256 for item in eligible)
        staging_names = sorted(path.name for path in eligible_staging)
        unmanaged_names = sorted(str(path.relative_to(self.artifact_store.root)) for path in inventory.unmanaged_entries)
        all_detail_lengths = [len(eligible_digests), len(missing_referenced), len(staging_names), len(unmanaged_names)]
        return ArtifactStoreGcResponse(
            mode=request.mode,
            grace_period_seconds=request.grace_period_seconds,
            started_at=started,
            completed_at=utc_now(),
            retained_revision_count=len(revisions),
            reachable_digest_count=len(reachable),
            store_blob_count=len(inventory.blobs),
            referenced_blob_count=len(referenced_present),
            unreferenced_blob_count=len(unreferenced),
            eligible_blob_count=len(eligible),
            deleted_blob_count=deleted_blobs,
            young_unreferenced_blob_count=len(young),
            missing_referenced_blob_count=len(missing_referenced),
            staging_file_count=len(inventory.staging_files),
            eligible_staging_file_count=len(eligible_staging),
            deleted_staging_file_count=deleted_staging,
            unmanaged_entry_count=len(inventory.unmanaged_entries),
            eligible_blob_sha256=eligible_digests[:detail_limit],
            missing_referenced_sha256=missing_referenced[:detail_limit],
            eligible_staging_files=staging_names[:detail_limit],
            unmanaged_entries=unmanaged_names[:detail_limit],
            details_truncated=any(length > detail_limit for length in all_detail_lengths),
        )

    def validate_publication(self, system_id: str, request: RevisionCreateRequest) -> dict[str, Any]:
        prepared = self._prepare_publication(system_id, request)
        return {
            **prepared["summary"],
            "system_id": system_id,
            "revision_id": self._revision_id(system_id, request, prepared["execution"].result_fingerprint),
            "execution_result_path": str(prepared["execution_result_path"]),
            "execution_result_sha256": request.execution_result.sha256,
        }

    def publish_revision(
        self,
        system_id: str,
        request: RevisionCreateRequest,
        *,
        validated: dict[str, Any] | None = None,
    ) -> RevisionCreateResponse:
        if self.store.get_system(system_id) is None:
            raise KnowledgeApiRuntimeError(404, "system_not_found", f"unknown system: {system_id}")

        prepared = self._prepare_publication(system_id, request)
        expected_revision_id = self._revision_id(
            system_id,
            request,
            prepared["execution"].result_fingerprint,
        )
        if validated is not None and str(validated.get("revision_id") or "") != expected_revision_id:
            raise KnowledgeApiRuntimeError(
                409,
                "publication_validation_stale",
                "validated publication does not match request",
            )
        revision_id = expected_revision_id
        existing = self.store.get_revision(system_id, revision_id)
        if existing is None:
            with self.artifact_store.lifecycle_lock():
                # Re-check after acquiring the cross-process Artifact Store lock.
                existing = self.store.get_revision(system_id, revision_id)
                if existing is None:
                    durable_execution_result, durable_products = self._import_publication_artifacts(prepared, request)
                    row = self.store.publish_revision(
                        revision_id=revision_id,
                        system_id=system_id,
                        ordinal=self.store.next_ordinal(system_id),
                        base_revision_id=request.base_revision_id,
                        execution=prepared["execution"].model_dump(mode="json"),
                        execution_result=durable_execution_result.model_dump(mode="json"),
                        knowledge_artifacts=[item.model_dump(mode="json") for item in durable_products],
                        capabilities=list(prepared["capabilities"]),
                        labels=list(request.labels),
                        metadata=request.metadata,
                        activate=request.activate,
                        created_at=utc_now(),
                    )
                else:
                    row = existing
        else:
            if request.activate and existing["state"] != "active":
                self.store.activate_revision(system_id, revision_id, activated_at=utc_now())
                row = self.store.get_revision(system_id, revision_id)
                assert row is not None
            else:
                row = existing
        return RevisionCreateResponse(revision=self._revision(row))

    def activate_revision(self, system_id: str, revision_id: str) -> SystemRevision:
        self.get_system(system_id)
        if self.store.get_revision(system_id, revision_id) is None:
            raise KnowledgeApiRuntimeError(404, "revision_not_found", f"unknown revision: {revision_id}")
        self.store.activate_revision(system_id, revision_id, activated_at=utc_now())
        row = self.store.get_revision(system_id, revision_id)
        assert row is not None
        return self._revision(row)

    def list_revisions(self, system_id: str, *, offset: int, limit: int) -> RevisionListResponse:
        self.get_system(system_id)
        rows = self.store.list_revisions(system_id)
        return RevisionListResponse(
            system_id=system_id,
            items=[self._revision(row) for row in rows[offset : offset + limit]],
            page=PageMeta(offset=offset, limit=limit, total=len(rows)),
        )

    def get_revision(self, system_id: str, revision_id: str) -> SystemRevision:
        self.get_system(system_id)
        row = self.store.get_revision(system_id, revision_id)
        if row is None:
            raise KnowledgeApiRuntimeError(404, "revision_not_found", f"unknown revision: {revision_id}")
        return self._revision(row)

    def list_knowledge_artifacts(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        model_kind: str | None,
        capability: str | None,
        offset: int,
        limit: int,
    ) -> KnowledgeArtifactListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        items = [PublishedKnowledgeArtifact.model_validate(item) for item in revision["knowledge_artifacts"]]
        if model_kind:
            items = [item for item in items if item.model_kind == model_kind]
        if capability:
            items = [item for item in items if capability in item.capabilities]
        items.sort(key=lambda item: (item.model_kind, item.schema_version, item.artifact_id))
        return KnowledgeArtifactListResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )

    def get_knowledge_artifact(
        self,
        system_id: str,
        artifact_id: str,
        *,
        revision_id: str | None,
    ) -> KnowledgeArtifactDetailResponse:
        revision = self._resolve_revision(system_id, revision_id)
        for raw in revision["knowledge_artifacts"]:
            if str(raw.get("artifact_id") or "") == artifact_id:
                return KnowledgeArtifactDetailResponse(
                    system_id=system_id,
                    revision_id=revision["revision_id"],
                    artifact=PublishedKnowledgeArtifact.model_validate(raw),
                )
        raise KnowledgeApiRuntimeError(404, "knowledge_artifact_not_found", f"unknown knowledge artifact: {artifact_id}")

    def get_aisl_knowledge_item(
        self,
        system_id: str,
        artifact_id: str,
        item_kind: str,
        local_id: str,
        *,
        revision_id: str | None,
    ) -> AislKnowledgeItemReadResponse:
        revision = self._resolve_revision(system_id, revision_id)
        artifact = self._artifact_record_by_id(revision, artifact_id)
        published = PublishedKnowledgeArtifact.model_validate(artifact)
        try:
            if published.origin_kind == ProductOriginKind.OBSERVED:
                descriptor = _product_artifact_by_role(published, "descriptor")
                if published.model_kind == "java-type-structure-evidence" and descriptor is not None:
                    path = self.validator.validate(descriptor)
                    raw = JavaTypeStructureEvidenceQuery(path).get_aisl_knowledge_item(
                        item_kind=item_kind,
                        local_id=local_id,
                    )
                elif published.model_kind == "sql-analysis":
                    manifest = _product_artifact_by_role(published, "manifest")
                    coverage = _product_artifact_by_role(published, "coverage")
                    fact_members = {
                        str(item.role).split(":", 1)[1]: self.validator.validate(item)
                        for item in published.physical_artifacts
                        if str(item.role).startswith("fact:")
                    }
                    if manifest is None or coverage is None or not fact_members:
                        raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", "published sql-analysis package is incomplete")
                    raw = SqlAnalysisEvidenceQuery(
                        manifest_path=self.validator.validate(manifest),
                        coverage_path=self.validator.validate(coverage),
                        fact_paths=fact_members,
                    ).get_aisl_knowledge_item(item_kind=item_kind, local_id=local_id)
                else:
                    raw = {
                        "schema_version": "aisl-item-read-projection/v1",
                        "unsupported": True,
                        "model_kind": published.model_kind,
                    }
            else:
                database = _product_artifact_by_role(published, "database")
                manifest = _product_artifact_by_role(published, "manifest")
                if database is None:
                    raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", "derived product database is unavailable")
                path = self.validator.validate(database)
                manifest_path = self._published_manifest_path_for_query(manifest)
                config = KnowledgeArtifactSource(
                    system_id=system_id,
                    database_path=path,
                    manifest_path=manifest_path,
                )
                query = self.knowledge_query_factory.get(config)
                raw = query.get_aisl_knowledge_item(
                    model_kind=published.model_kind,
                    item_kind=item_kind,
                    local_id=local_id,
                )
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc
        except KnowledgeApiRuntimeError:
            raise
        except Exception as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc

        item_ref = AislKnowledgeItemRef(
            scope_id=system_id,
            revision_id=str(revision["revision_id"]),
            product_id=artifact_id,
            item_kind=item_kind,
            local_id=local_id,
        )
        if raw.get("unsupported"):
            basis = "typed_product_universal_projection_not_supported"
            return AislKnowledgeItemReadResponse(
                system_id=system_id,
                revision_id=str(revision["revision_id"]),
                product=published,
                item_ref=item_ref,
                projection_status=AislReadFacetAvailability.UNSUPPORTED,
                projection_basis=basis,
                evidence_state=AislReadFacetState(availability=AislReadFacetAvailability.UNSUPPORTED, basis=basis),
                coverage_state=AislReadFacetState(availability=AislReadFacetAvailability.UNSUPPORTED, basis=basis),
                issues_state=AislReadFacetState(availability=AislReadFacetAvailability.UNSUPPORTED, basis=basis),
                correspondences_state=AislReadFacetState(availability=AislReadFacetAvailability.UNSUPPORTED, basis=basis),
            )
        if raw.get("not_found"):
            raise KnowledgeApiRuntimeError(
                404,
                "knowledge_item_not_found",
                f"knowledge item not found: {artifact_id}/{item_kind}/{local_id}",
            )

        evidence = [AislEvidence.model_validate(v) for v in raw.get("evidence") or ()]
        source_fragments = [AislSourceFragment.model_validate(v) for v in raw.get("source_fragments") or ()]
        issues = [AislKnowledgeIssue.model_validate(v) for v in raw.get("issues") or ()]
        bindings = [
            AislEvidenceBinding(
                binding_id=f"{artifact_id}:{item_kind}:{local_id}:{ev.evidence_id}",
                evidence_id=ev.evidence_id,
                role="direct_observation",
                basis="universal_item_read_context",
            )
            for ev in evidence
        ]
        correspondence_rows: list[AislCrossProductCorrespondence] = []
        corr = raw.get("correspondence")
        if isinstance(corr, dict):
            def endpoint(value: dict[str, Any] | None) -> AislCorrespondenceEndpoint | None:
                if not value:
                    return None
                return AislCorrespondenceEndpoint(
                    scope_id=system_id,
                    revision_id=str(revision["revision_id"]),
                    product_id=str(value["product_id"]),
                    item_kind=str(value["item_kind"]),
                    local_id=str(value["local_id"]),
                )
            source_ref = endpoint(dict(corr.get("source") or {}))
            if source_ref is not None:
                correspondence_rows.append(AislCrossProductCorrespondence(
                    correspondence_id=str(corr.get("correspondence_id") or local_id),
                    relation_kind=str(corr.get("relation_kind") or "maps_to"),
                    source_ref=source_ref,
                    target_ref=endpoint(dict(corr.get("target") or {})) if corr.get("target") else None,
                    candidate_target_refs=[endpoint(dict(v)) for v in corr.get("candidate_targets") or () if endpoint(dict(v)) is not None],
                    resolution_status=str(corr.get("resolution_status") or "unresolved"),
                    basis=str(corr.get("basis") or "typed_product_correspondence"),
                    evidence_ids=[str(v) for v in corr.get("evidence_ids") or ()],
                ))

        evidence_state = AislReadFacetState(
            availability=AislReadFacetAvailability.AVAILABLE if evidence else AislReadFacetAvailability.NOT_AVAILABLE,
            basis="typed_product_evidence_projection" if evidence else "no_addressable_item_evidence_published",
        )
        issues_state = AislReadFacetState(
            availability=AislReadFacetAvailability.AVAILABLE if issues else AislReadFacetAvailability.NOT_AVAILABLE,
            basis="typed_product_issue_projection" if issues else "no_item_specific_issue_published",
        )
        correspondence_state = AislReadFacetState(
            availability=AislReadFacetAvailability.AVAILABLE if correspondence_rows else AislReadFacetAvailability.UNSUPPORTED,
            basis="typed_cross_product_mapping_projection" if correspondence_rows else "revision_wide_cross_product_lookup_not_yet_supported_for_this_item",
        )
        return AislKnowledgeItemReadResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            product=published,
            item_ref=item_ref,
            projection_status=AislReadFacetAvailability.AVAILABLE,
            projection_basis="typed_product_universal_projection",
            item=dict(raw.get("item") or {}),
            evidence=evidence,
            evidence_bindings=bindings,
            source_fragments=source_fragments,
            issues=issues,
            correspondences=correspondence_rows,
            evidence_state=evidence_state,
            coverage_state=AislReadFacetState(
                availability=AislReadFacetAvailability.AVAILABLE if raw.get("coverage") else AislReadFacetAvailability.NOT_AVAILABLE,
                basis="product_coverage_published_for_observed_item" if raw.get("coverage") else "item_level_coverage_fact_not_published_by_typed_product",
            ),
            issues_state=issues_state,
            correspondences_state=correspondence_state,
        )

    def revision_capabilities(
        self,
        system_id: str,
        *,
        revision_id: str | None,
    ) -> RevisionCapabilitiesResponse:
        revision = self._resolve_revision(system_id, revision_id)
        return RevisionCapabilitiesResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            capabilities=sorted({str(value) for value in revision["capabilities"]}),
        )

    def llm_integration_profile(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        profile_id: str,
    ) -> dict[str, Any]:
        revision = self._resolve_revision(system_id, revision_id)
        try:
            profile = generate_integration_profile(
                RevisionContext(
                    system_id=system_id,
                    revision_id=str(revision["revision_id"]),
                    capabilities=tuple(sorted({str(v) for v in revision.get("capabilities") or ()})),
                    knowledge_artifacts=tuple(
                        dict(v) for v in revision.get("knowledge_artifacts") or () if isinstance(v, dict)
                    ),
                ),
                profile_id=profile_id,
            )
        except KeyError as exc:
            raise KnowledgeApiRuntimeError(404, "integration_profile_not_found", str(exc)) from exc
        return profile.to_dict()


    def analysis_coverage(self, system_id: str, *, revision_id: str | None) -> AnalysisCoverageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._query_service(system_id, revision)
        coverage = service.analysis_coverage(system_id)
        return AnalysisCoverageResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            **coverage,
        )

    def resolve_attribute_paths(
        self,
        system_id: str,
        payload: AttributePathResolveRequest,
        *,
        revision_id: str | None,
    ) -> AttributePathResolveResponse:
        revision = self._resolve_revision(system_id, revision_id)
        artifact = self._value_flow_artifact_record(revision)
        config = self._knowledge_artifact_source(system_id, artifact)
        service = self.knowledge_query_factory.get(config)
        result = service.resolve_attribute_paths(**payload.model_dump())
        source_materialization_id = str(artifact.get("source_materialization_id") or "")
        return AttributePathResolveResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            artifact_id=str(artifact.get("artifact_id") or ""),
            source_materialization_id=source_materialization_id,
            enriched_cross_repository=(source_materialization_id == "cross-repository-value-flow"),
            result=result,
        )

    def list_tables(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        search: str | None,
        table_kind: str | None,
        include_fields: bool,
        offset: int,
        limit: int,
    ) -> TableListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._query_service(system_id, revision)
        catalog = service.field_catalog(system_id)
        count_method = getattr(service, "relationship_counts", None)
        relationship_counts = count_method() if callable(count_method) else {}
        token = search.casefold() if search else None
        items: list[TableSummary] = []
        for table in catalog.tables:
            kind = table.table_id.split(":", 1)[0] if ":" in table.table_id else "table"
            fields = [FieldSummary(name=item.field_name, description=item.description) for item in table.fields]
            searchable = " ".join(
                [table.table_id, table.table_name, table.description or "", *(item.field_name for item in table.fields)]
            ).casefold()
            if token and token not in searchable:
                continue
            if table_kind and kind != table_kind:
                continue
            items.append(
                TableSummary(
                    table_id=table.table_id,
                    table_name=table.table_name,
                    table_kind=kind,
                    description=table.description,
                    field_count=len(fields),
                    relationship_count=int(relationship_counts.get(table.table_id, 0)),
                    fields=fields if include_fields else None,
                )
            )
        return TableListResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=items[offset : offset + limit],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
        )

    def get_table(self, system_id: str, table_id: str, *, revision_id: str | None) -> TableDetailResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._query_service(system_id, revision)
        try:
            detail = service.table_detail(system_id, table_id)
        except DataObjectNotFoundError as exc:
            raise KnowledgeApiRuntimeError(404, "table_not_found", f"unknown table: {table_id}") from exc
        return TableDetailResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            workspace_id=detail.workspace_id,
            build_id=detail.build_id,
            generated_at=detail.generated_at,
            object=DataObjectRef.model_validate(detail.object.model_dump()),
            fields=[TableField.model_validate(item.model_dump()) for item in detail.fields],
            keys=[TableKey.model_validate(item.model_dump()) for item in detail.keys],
            relationships=[TableRelationshipSummary.model_validate(item.model_dump()) for item in detail.relationships],
            embedded_objects=list(detail.embedded_objects),
            relationship_candidate_count=detail.relationship_candidate_count,
            indexes=list(detail.indexes),
            constraints=list(detail.constraints),
            partitioning=list(detail.partitioning),
            triggers=list(detail.triggers),
        )

    def get_relationship(
        self,
        system_id: str,
        table_id: str,
        relationship_id: str,
        *,
        revision_id: str | None,
    ) -> RelationshipDetailResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._query_service(system_id, revision)
        try:
            relationship = service.relationship_detail(table_id, relationship_id)
        except DataObjectNotFoundError as exc:
            raise KnowledgeApiRuntimeError(404, "table_not_found", f"unknown table: {table_id}") from exc
        except RelationshipNotFoundError as exc:
            raise KnowledgeApiRuntimeError(
                404,
                "relationship_not_found",
                f"unknown relationship for table {table_id}: {relationship_id}",
            ) from exc
        return RelationshipDetailResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            table_id=table_id,
            relationship=TableRelationship.model_validate(relationship.model_dump()),
        )

    @staticmethod
    def _physical_table_summary(item: dict[str, Any]) -> PhysicalModelTableSummary:
        return PhysicalModelTableSummary.model_validate(item)

    def _portfolio_repository_snapshot(self, system_id: str, revision: dict[str, Any]) -> dict[str, Any] | None:
        artifacts = [
            dict(raw) for raw in revision.get("knowledge_artifacts") or ()
            if isinstance(raw, dict) and str(raw.get("model_kind") or "") == "repository-inventory"
        ]
        if not artifacts:
            return None
        digests = {str((_product_artifact_dict_by_role(raw, "database") or {}).get("sha256") or "") for raw in artifacts}
        if len(digests) > 1:
            raise KnowledgeApiRuntimeError(
                409, "portfolio_repository_inventory_ambiguous",
                "multiple repository-inventory artifacts with different database digests exist in one revision",
                details={"system_id": system_id, "revision_id": revision.get("revision_id")},
            )
        artifact = artifacts[0]
        database = dict(_product_artifact_dict_by_role(artifact, "database") or {})
        digest = str(database.get("sha256") or "")
        resolved = self.validator.resolve_file_uri(str(database.get("uri") or ""))
        if resolved.is_file():
            stat = resolved.stat()
            cached = self._portfolio_repository_snapshot_cache.get(digest)
            if cached is not None and cached[0] == str(resolved) and cached[1] == stat.st_mtime_ns and cached[2] == stat.st_size:
                return dict(cached[3])
        path = self.validator.validate_dict(database)
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            service = self.knowledge_query_factory.get(config)
            snapshot = dict(service.repository_inventory_portfolio_snapshot())
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        except Exception as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        stat = path.stat()
        self._portfolio_repository_snapshot_cache[digest] = (str(path), stat.st_mtime_ns, stat.st_size, snapshot)
        return dict(snapshot)

    def _portfolio_system_projection(self, system: dict[str, Any]) -> dict[str, Any]:
        seen_repositories: set[str] = set()
        repository_records: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for revision in self.store.list_revisions(system["system_id"]):
            scope_hint = str((revision.get("execution") or {}).get("scope_id") or "").strip()
            if scope_hint and scope_hint in seen_repositories:
                continue
            if not any(
                isinstance(raw, dict) and str(raw.get("model_kind") or "") == "repository-inventory"
                for raw in revision.get("knowledge_artifacts") or ()
            ):
                continue
            try:
                snapshot = self._portfolio_repository_snapshot(system["system_id"], revision)
            except KnowledgeApiRuntimeError as exc:
                diagnostics.append({
                    "revision_id": revision.get("revision_id"), "code": exc.code,
                    "message": exc.message, "details": exc.details,
                })
                continue
            if snapshot is None:
                continue
            identity = dict(snapshot.get("identity") or {})
            repo_id = str(identity.get("repo_id") or "").strip()
            if not repo_id:
                diagnostics.append({
                    "revision_id": revision.get("revision_id"),
                    "code": "portfolio_repository_identity_missing",
                    "message": "repository-inventory snapshot has no repo_id and cannot participate in system aggregation",
                })
                continue
            if repo_id in seen_repositories:
                continue
            seen_repositories.add(repo_id)
            repository_records.append({
                "repo_id": repo_id, "revision_id": revision.get("revision_id"),
                "revision_ordinal": revision.get("ordinal"), "revision_state": revision.get("state"),
                "revision_created_at": revision.get("created_at"), "snapshot": snapshot,
            })
        projection = aggregate_system_inventory(system, repository_records)
        projection["inventory_diagnostics"] = diagnostics
        if repository_records and diagnostics:
            projection["inventory_status"] = "partial"
        elif repository_records:
            projection["inventory_status"] = "available"
        elif diagnostics:
            projection["inventory_status"] = "unavailable"
        else:
            projection["inventory_status"] = "not_available"
        return projection

    def _portfolio_inventory_items(self, *, include_unavailable: bool = False) -> list[dict[str, Any]]:
        items = [self._portfolio_system_projection(system) for system in self.store.list_systems()]
        if not include_unavailable:
            items = [item for item in items if item["inventory_status"] in {"available", "partial"}]
        return sorted(items, key=lambda row: (str(row.get("display_name") or "").casefold(), row["system_id"]))

    @staticmethod
    def _portfolio_public_item(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if key != "interfaces"}

    def list_portfolio_inventory(
        self, *, offset: int, limit: int, search: str | None,
        technology: str | None, protocol: str | None,
        has_sql: bool | None, has_unresolved_peers: bool | None, source_kind: str | None,
        include_unavailable: bool,
    ) -> PortfolioInventoryListResponse:
        filters = {
            "search": search,
            "technology": technology, "protocol": protocol, "has_sql": has_sql,
            "has_unresolved_peers": has_unresolved_peers, "source_kind": source_kind,
            "include_unavailable": include_unavailable,
        }
        items = [
            item for item in self._portfolio_inventory_items(include_unavailable=include_unavailable)
            if matches_portfolio_filters(item, search=search, technology=technology, protocol=protocol, has_sql=has_sql,
                has_unresolved_peers=has_unresolved_peers, source_kind=source_kind)
        ]
        return PortfolioInventoryListResponse(
            items=[PortfolioSystemInventory.model_validate(self._portfolio_public_item(item)) for item in items[offset:offset + limit]],
            page=PageMeta(offset=offset, limit=limit, total=len(items)),
            filters={key: value for key, value in filters.items() if value is not None and value is not False},
        )

    def get_portfolio_system_inventory(self, system_id: str) -> PortfolioSystemInventory:
        system = self.store.get_system(system_id)
        if system is None:
            raise KnowledgeApiRuntimeError(404, "system_not_found", f"unknown system: {system_id}")
        return PortfolioSystemInventory.model_validate(self._portfolio_public_item(self._portfolio_system_projection(system)))

    def portfolio_inventory_facets(self) -> PortfolioInventoryFacetsResponse:
        items = self._portfolio_inventory_items(include_unavailable=False)
        return PortfolioInventoryFacetsResponse(system_count=len(items), facets=build_facets(items))

    def portfolio_interaction_graph(self) -> PortfolioInteractionGraphResponse:
        items = self._portfolio_inventory_items(include_unavailable=False)
        return PortfolioInteractionGraphResponse.model_validate(build_interaction_graph(items))

    def repository_inventory_summary(self, system_id: str, *, revision_id: str | None) -> RepositoryInventorySummaryResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="repository-inventory")
        try:
            result = service.repository_inventory_summary()
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        return RepositoryInventorySummaryResponse(
            repository_inventory_schema_version=str(result.get("schema_version") or "repository-inventory-query/v5"),
            inventory_schema_version=(str(result.get("inventory_schema_version")) if result.get("inventory_schema_version") else None),
            system_id=system_id, revision_id=revision["revision_id"],
            evaluation_phase=(str(result.get("evaluation_phase")) if result.get("evaluation_phase") else None),
            evaluation_basis=dict(result.get("evaluation_basis") or {}),
            identity=dict(result.get("identity") or {}),
            counts={str(k): int(v) for k, v in (result.get("counts") or {}).items()},
            discovery_counts={str(k): int(v) for k, v in (result.get("discovery_counts") or {}).items()},
            source_evidence=[dict(item) for item in result.get("source_evidence") or ()],
        )

    def repository_inventory_coverage(self, system_id: str, *, revision_id: str | None) -> RepositoryInventoryCoverageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="repository-inventory")
        try:
            result = service.repository_inventory_coverage()
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        return RepositoryInventoryCoverageResponse(
            repository_inventory_schema_version=str(result.get("schema_version") or "repository-inventory-coverage-query/v5"),
            system_id=system_id, revision_id=revision["revision_id"],
            evaluation_phase=(str(result.get("evaluation_phase")) if result.get("evaluation_phase") else None),
            analyzer_frontier={str(k): int(v) for k, v in (result.get("analyzer_frontier") or {}).items()},
            completeness=[dict(item) for item in result.get("completeness") or ()],
            gap_counts={str(k): int(v) for k, v in (result.get("gap_counts") or {}).items()},
            discovery_gap_counts={str(k): int(v) for k, v in (result.get("discovery_gap_counts") or {}).items()},
            source_evidence=[dict(item) for item in result.get("source_evidence") or ()],
        )

    def _repository_inventory_page(self, system_id: str, *, revision_id: str | None, method_name: str, filters: dict[str, Any], offset: int, limit: int) -> RepositoryInventoryPageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="repository-inventory")
        try:
            result = getattr(service, method_name)(offset=offset, limit=limit, **filters)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        return RepositoryInventoryPageResponse(
            system_id=system_id, revision_id=revision["revision_id"],
            query_kind=str(result.get("query_kind") or method_name), filters={k: v for k, v in filters.items() if v is not None and v != ""},
            items=[dict(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def list_repository_inventory_technologies(self, system_id: str, *, revision_id: str | None, category: str | None, search: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_technologies", filters={"category": category, "token": search or ""}, offset=offset, limit=limit)

    def list_repository_inventory_interfaces(self, system_id: str, *, revision_id: str | None, direction: str | None, protocol: str | None, peer_resolution_status: str | None, search: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_interfaces", filters={"direction": direction, "protocol": protocol, "peer_resolution_status": peer_resolution_status, "token": search or ""}, offset=offset, limit=limit)

    def list_repository_inventory_structural_families(self, system_id: str, *, revision_id: str | None, family_kind: str | None, discovery_kind: str | None, search: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_structural_families", filters={"family_kind": family_kind, "discovery_kind": discovery_kind, "token": search or ""}, offset=offset, limit=limit)

    def list_repository_inventory_discovery(self, system_id: str, *, revision_id: str | None, discovery_kind: str | None, min_salience_score: float, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_discovery", filters={"discovery_kind": discovery_kind, "min_salience_score": min_salience_score}, offset=offset, limit=limit)

    def list_repository_inventory_coverage_gaps(self, system_id: str, *, revision_id: str | None, gap_kind: str | None, discovery_kind: str | None, relevance_status: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_coverage_gaps", filters={"gap_kind": gap_kind, "discovery_kind": discovery_kind, "relevance_status": relevance_status}, offset=offset, limit=limit)

    def list_repository_inventory_source_occurrences(self, system_id: str, *, revision_id: str | None, object_kind: str | None, object_id: str | None, repository_relative_path: str | None, localization_kind: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_source_occurrences", filters={"object_kind": object_kind, "object_id": object_id, "repository_relative_path": repository_relative_path, "localization_kind": localization_kind}, offset=offset, limit=limit)

    def get_repository_inventory_source_occurrence(self, system_id: str, occurrence_id: str, *, revision_id: str | None) -> RepositorySourceOccurrenceResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="repository-inventory")
        try:
            result = service.get_repository_inventory_source_occurrence(occurrence_id)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "repository_inventory_unavailable", str(exc)) from exc
        if result is None:
            raise KnowledgeApiRuntimeError(404, "source_occurrence_not_found", f"repository source occurrence not found: {occurrence_id}")
        return RepositorySourceOccurrenceResponse(
            repository_source_occurrence_schema_version=str(result.get("schema_version") or "repository-source-occurrence-query/v1"),
            system_id=system_id, revision_id=revision["revision_id"],
            occurrence=dict(result.get("occurrence") or {}),
            object_links=[dict(item) for item in result.get("object_links") or ()],
        )

    def list_repository_inventory_diagnostics(self, system_id: str, *, revision_id: str | None, severity: str | None, code: str | None, search: str | None, offset: int, limit: int) -> RepositoryInventoryPageResponse:
        return self._repository_inventory_page(system_id, revision_id=revision_id, method_name="list_repository_inventory_diagnostics", filters={"severity": severity, "code": code, "token": search or ""}, offset=offset, limit=limit)

    def physical_model_summary(
        self,
        system_id: str,
        *,
        revision_id: str | None,
    ) -> PhysicalModelSummaryResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.physical_model_summary()
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelSummaryResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            sources=[PhysicalModelSource.model_validate(item) for item in result.get("sources") or ()],
            counts={str(key): int(value) for key, value in (result.get("counts") or {}).items()},
            relationship_resolution={str(key): int(value) for key, value in (result.get("relationship_resolution") or {}).items()},
            key_kinds={str(key): int(value) for key, value in (result.get("key_kinds") or {}).items()},
            gap_kinds={str(key): int(value) for key, value in (result.get("gap_kinds") or {}).items()},
        )

    def list_physical_model_tables(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        source_id: str | None,
        search: str | None,
        include_columns: bool,
        offset: int,
        limit: int,
    ) -> PhysicalModelTableListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.list_physical_model_tables(
                source_id=source_id,
                search=search or "",
                include_columns=include_columns,
                offset=offset,
                limit=limit,
            )
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelTableListResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=[self._physical_table_summary(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def get_physical_model_table(
        self,
        system_id: str,
        table_id: str,
        *,
        revision_id: str | None,
    ) -> PhysicalModelTableDetailResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.get_physical_model_table(table_id)
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        except PhysicalModelTableNotFoundError as exc:
            raise KnowledgeApiRuntimeError(404, "physical_model_table_not_found", f"unknown physical table: {table_id}") from exc
        return PhysicalModelTableDetailResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            table=self._physical_table_summary(dict(result.get("table") or {})),
            columns=[PhysicalModelColumn.model_validate(item) for item in result.get("columns") or ()],
            keys=[PhysicalModelKey.model_validate(item) for item in result.get("keys") or ()],
            relationships=[PhysicalModelRelationship.model_validate(item) for item in result.get("relationships") or ()],
        )

    def list_physical_model_columns(
        self, system_id: str, *, revision_id: str | None, table_id: str | None,
        source_id: str | None, search: str | None, data_type: str | None,
        mandatory: bool | None, offset: int, limit: int,
    ) -> PhysicalModelColumnListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.list_physical_model_columns(
                table_id=table_id, source_id=source_id, search=search or "", data_type=data_type,
                mandatory=mandatory, offset=offset, limit=limit,
            )
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelColumnListResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id, revision_id=revision["revision_id"],
            items=[PhysicalModelColumn.model_validate(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def list_physical_model_keys(
        self, system_id: str, *, revision_id: str | None, table_id: str | None,
        source_id: str | None, key_kind: str | None, search: str | None,
        offset: int, limit: int,
    ) -> PhysicalModelKeyListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.list_physical_model_keys(
                table_id=table_id, source_id=source_id, key_kind=key_kind, search=search or "",
                offset=offset, limit=limit,
            )
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelKeyListResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id, revision_id=revision["revision_id"],
            items=[PhysicalModelKey.model_validate(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def list_physical_model_relationships(
        self, system_id: str, *, revision_id: str | None, table_id: str | None,
        direction: str, source_id: str | None, resolution_status: str | None,
        search: str | None, offset: int, limit: int,
    ) -> PhysicalModelRelationshipListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.list_physical_model_relationships(
                table_id=table_id, direction=direction, source_id=source_id,
                resolution_status=resolution_status, search=search or "", offset=offset, limit=limit,
            )
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "physical_model_filter_invalid", str(exc)) from exc
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelRelationshipListResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id, revision_id=revision["revision_id"],
            items=[PhysicalModelRelationship.model_validate(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def list_physical_model_gaps(
        self, system_id: str, *, revision_id: str | None, source_id: str | None,
        gap_kind: str | None, search: str | None, offset: int, limit: int,
    ) -> PhysicalModelGapListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(system_id, revision, model_kind="physical-data-model")
        try:
            result = service.list_physical_model_gaps(
                source_id=source_id, gap_kind=gap_kind, search=search or "", offset=offset, limit=limit,
            )
        except PhysicalModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "physical_model_unavailable", str(exc)) from exc
        return PhysicalModelGapListResponse(
            physical_model_schema_version=str(result.get("schema_version") or "physical-model-query/v1"),
            system_id=system_id, revision_id=revision["revision_id"],
            items=[PhysicalModelGap.model_validate(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    @staticmethod
    def _sql_relation_summary(item: dict[str, Any], *, include_fields: bool = True) -> SqlRelationSummary:
        fields = None
        if include_fields:
            fields = [
                SqlRelationFieldSummary(
                    name=str(field.get("name") or ""),
                    usage_roles=[str(value) for value in field.get("usage_roles") or ()],
                    resolution_statuses=[str(value) for value in field.get("resolution_statuses") or ()],
                    resolution_bases=[str(value) for value in field.get("resolution_bases") or ()],
                    occurrence_count=int(field.get("occurrence_count") or 0),
                    statement_count=int(field.get("statement_count") or 0),
                    evidence_count=int(field.get("evidence_count") or 0),
                    evidence_count_by_role={
                        str(key): int(value) for key, value in (field.get("evidence_count_by_role") or {}).items()
                    },
                    evidence_refs=[SqlEvidenceRef.model_validate(ref) for ref in field.get("evidence_refs") or ()],
                    evidence_truncated=bool(field.get("evidence_truncated")),
                )
                for field in item.get("fields") or ()
                if field.get("name")
            ]
        return SqlRelationSummary(
            relation_id=str(item.get("relation_id") or ""),
            repo_id=str(item.get("repo_id") or ""),
            relation_kind=str(item.get("relation_kind") or ""),
            relation_identity=str(item.get("relation_identity") or ""),
            template_name=item.get("template_name"),
            logical_name=item.get("logical_name"),
            resolved_names=[str(value) for value in item.get("resolved_names") or ()],
            usage_roles=[str(value) for value in item.get("usage_roles") or ()],
            definition_statuses=[str(value) for value in item.get("definition_statuses") or ()],
            semantic_role=str(item.get("semantic_role") or "unknown"),
            classification_status=str(item.get("classification_status") or "unresolved"),
            hidden_by_default=bool(item.get("hidden_by_default")),
            classification_reasons=[str(value) for value in item.get("classification_reasons") or ()],
            write_occurrence_count=int(item.get("write_occurrence_count") or 0),
            downstream_target_count=int(item.get("downstream_target_count") or 0),
            owned_namespace=bool(item.get("owned_namespace")),
            technical_name_signal=bool(item.get("technical_name_signal")),
            occurrence_count=int(item.get("occurrence_count") or 0),
            statement_count=int(item.get("statement_count") or 0),
            field_count=(len(fields) if include_fields else None),
            fields=fields,
            evidence_count=int(item.get("evidence_count") or 0),
            evidence_count_by_role={
                str(key): int(value) for key, value in (item.get("evidence_count_by_role") or {}).items()
            },
            evidence_refs=[SqlEvidenceRef.model_validate(ref) for ref in item.get("evidence_refs") or ()],
            evidence_truncated=bool(item.get("evidence_truncated")),
        )

    @staticmethod
    def _sql_analysis_coverage(raw_coverage: dict[str, Any]) -> SqlAnalysisCoverage:
        return SqlAnalysisCoverage(
            analysis_status=str(raw_coverage.get("analysis_status") or "not_available"),
            relation_classification=SqlRelationClassificationCoverage.model_validate(
                raw_coverage.get("relation_classification") or {}
            ),
            source_inventory=SqlSourceInventoryCoverage.model_validate(
                raw_coverage.get("source_inventory") or {}
            ),
            repositories=[
                SqlAnalysisRepositoryCoverage.model_validate(row)
                for row in raw_coverage.get("repositories") or ()
            ],
        )

    def list_sql_relations(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        relation_kind: str | None,
        usage_role: str | None,
        view: str,
        search: str | None,
        include_fields: bool,
        max_evidence_per_role: int,
        offset: int,
        limit: int,
    ) -> SqlRelationListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-analysis")
        try:
            result = service.list_sql_relations(
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
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc

        items = [
            self._sql_relation_summary(dict(item), include_fields=include_fields)
            for item in result.get("items") or ()
        ]
        coverage = self._sql_analysis_coverage(dict(result.get("coverage") or {}))
        return SqlRelationListResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=items,
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
            coverage=coverage,
        )

    def export_sql_source_inventory(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        relation_kind: str | None,
        usage_role: str | None,
        view: str,
        search: str | None,
        max_evidence_per_role: int,
    ) -> SqlSourceInventoryExportResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-source-inventory")
        try:
            result = service.export_sql_source_inventory(
                repo_id=repo_id,
                relation_kind=relation_kind,
                usage_role=usage_role,
                view=view,
                search=search,
                max_evidence_per_role=max_evidence_per_role,
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        items = [
            self._sql_relation_summary(dict(item), include_fields=True)
            for item in result.get("items") or ()
        ]
        return SqlSourceInventoryExportResponse(
            inventory_schema_version=str(result.get("schema_version") or "sql-source-inventory/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            filters=dict(result.get("filters") or {}),
            item_count=len(items),
            items=items,
            coverage=self._sql_analysis_coverage(dict(result.get("coverage") or {})),
        )


    @staticmethod
    def _sql_evidence_refs(raw: Any, *, fallback_file: str | None = None, fallback_line: int | None = None) -> list[SqlEvidenceRef]:
        refs: list[SqlEvidenceRef] = []
        for item in raw or ():
            if not isinstance(item, dict):
                continue
            file_name = str(item.get("file") or item.get("relative_file") or "").strip()
            if not file_name:
                continue
            line = item.get("line_start")
            refs.append(SqlEvidenceRef(file=file_name, line_start=int(line) if line else None))
        if not refs and fallback_file:
            refs.append(SqlEvidenceRef(file=fallback_file, line_start=fallback_line))
        return refs

    def list_sql_target_column_lineage(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        target_relation: str,
        target_column: str | None,
        repo_id: str | None,
        lineage_status: str | None,
        include_gaps: bool,
        max_gaps: int,
        offset: int,
        limit: int,
    ) -> SqlTargetColumnLineageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(
            system_id, revision, required_capability="common.sql-target-column-lineage"
        )
        try:
            result = service.list_sql_target_column_lineage(
                target_relation=target_relation,
                target_column=target_column,
                repo_id=repo_id,
                lineage_status=lineage_status,
                include_gaps=include_gaps,
                max_gaps=max_gaps,
                offset=offset,
                limit=limit,
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc

        return SqlTargetColumnLineageResponse(
            lineage_schema_version=str(result.get("schema_version") or "sql-target-column-lineage/v1"),
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            target_relation_name=target_relation,
            target_column=target_column,
            repo_id=repo_id,
            lineage_status=lineage_status,
            filters={
                str(key): value
                for key, value in dict(result.get("filters") or {}).items()
                if value is not None
            },
            items=[dict(item) for item in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
            summary=dict(result.get("summary") or {}),
            gaps=[dict(item) for item in result.get("gaps") or ()],
            gap_count=int(result.get("gap_count") or 0),
            gaps_truncated=bool(result.get("gaps_truncated")),
            gaps_by_kind={
                str(key): int(value)
                for key, value in (result.get("gaps_by_kind") or {}).items()
            },
        )

    def get_sql_field_calculation(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        target_relation: str,
        target_column: str,
        repo_id: str | None,
        include_gaps: bool,
        max_gaps: int,
    ) -> SqlFieldCalculationResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(
            system_id, revision, required_capability="common.sql-field-calculation"
        )
        try:
            result = service.get_sql_field_calculation(
                target_relation=target_relation,
                target_column=target_column,
                repo_id=repo_id,
                include_gaps=include_gaps,
                max_gaps=max_gaps,
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        return SqlFieldCalculationResponse(
            calculation_schema_version=str(result.get("schema_version") or "sql-field-calculation/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            target_relation_name=str(result.get("target_relation_name") or target_relation),
            target_column=str(result.get("target_column") or target_column),
            repo_id=result.get("repo_id"),
            calculations=[dict(item) for item in result.get("calculations") or ()],
            calculation_count=int(result.get("calculation_count") or 0),
            terminal_sources=[dict(item) for item in result.get("terminal_sources") or ()],
            terminal_source_count=int(result.get("terminal_source_count") or 0),
            lineage_paths=[dict(item) for item in result.get("lineage_paths") or ()],
            lineage_path_count=int(result.get("lineage_path_count") or 0),
            lineage_statuses=[str(item) for item in result.get("lineage_statuses") or ()],
            physical_origin_statuses=[str(item) for item in result.get("physical_origin_statuses") or ()],
            gaps=[dict(item) for item in result.get("gaps") or ()],
            gap_count=int(result.get("gap_count") or 0),
            gaps_truncated=bool(result.get("gaps_truncated")),
            gaps_by_kind={str(key): int(value) for key, value in (result.get("gaps_by_kind") or {}).items()},
            coverage_status=str(result.get("coverage_status") or "unknown"),
        )

    def get_workspace_sql_catalog(
        self,
        system_id: str,
        *,
        revision_id: str | None,
    ) -> WorkspaceSqlCatalogResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="workspace-sql-catalog",
            capability_prefix="common.workspace-sql-catalog",
        )
        try:
            result = service.get_workspace_sql_catalog()
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "workspace_sql_catalog_unavailable", str(exc)) from exc
        return WorkspaceSqlCatalogResponse(
            catalog_schema_version=str(result.get("schema_version") or "workspace-sql-catalog/v1"),
            system_id=system_id,
            revision_id=revision["revision_id"],
            scope_id=result.get("scope_id"),
            sources=[dict(item) for item in result.get("sources") or ()],
            source_count=int(result.get("source_count") or 0),
            repository_ids=[str(item) for item in result.get("repository_ids") or ()],
            repository_count=int(result.get("repository_count") or 0),
            coverage=dict(result.get("coverage") or {}),
        )

    def find_sql_target_candidates(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        source_relation_hints: list[str] | None,
        source_column_hints: list[str] | None,
        business_entity_hints: list[str] | None,
        max_results: int,
    ) -> SqlTargetCandidatesResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-target-resolution")
        try:
            result = service.find_sql_target_candidates(
                repo_id=repo_id,
                source_relation_hints=source_relation_hints,
                source_column_hints=source_column_hints,
                business_entity_hints=business_entity_hints,
                max_results=max_results,
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        return SqlTargetCandidatesResponse(
            candidate_schema_version=str(
                result.get("schema_version") or "sql-target-candidates/v1"
            ),
            system_id=system_id,
            revision_id=revision["revision_id"],
            filters=dict(result.get("filters") or {}),
            candidates=[dict(item) for item in result.get("candidates") or ()],
            candidate_count=int(result.get("candidate_count") or 0),
            returned_count=int(result.get("returned_count") or 0),
            diagnostics=[str(item) for item in result.get("diagnostics") or ()],
        )

    def resolve_sql_attribute_insertion_context(
        self,
        system_id: str,
        payload: SqlAttributeInsertionContextRequest,
        *,
        revision_id: str | None,
    ) -> SqlAttributeInsertionContextResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-attribute-insertion-context")
        try:
            result = service.resolve_sql_attribute_insertion_context(
                target_relation=payload.target_relation,
                repo_id=payload.repo_id,
                source_relation_hints=list(payload.source_relation_hints),
                source_column_hints=list(payload.source_column_hints),
                max_results=payload.max_results,
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        return SqlAttributeInsertionContextResponse(
            insertion_schema_version=str(
                result.get("schema_version") or "sql-attribute-insertion-context/v1"
            ),
            system_id=system_id,
            revision_id=revision["revision_id"],
            filters=dict(result.get("filters") or {}),
            target=dict(result["target"]) if isinstance(result.get("target"), dict) else None,
            recommended_insertion=(
                dict(result["recommended_insertion"])
                if isinstance(result.get("recommended_insertion"), dict)
                else None
            ),
            insertion_candidates=[
                dict(item) for item in result.get("insertion_candidates") or ()
            ],
            candidate_count=int(result.get("candidate_count") or 0),
            returned_count=int(result.get("returned_count") or 0),
            diagnostics=[str(item) for item in result.get("diagnostics") or ()],
        )

    def list_sql_relation_materializations(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        output_table_name: str | None,
        query_id: str | None,
        workflow_context_file: str | None,
        offset: int,
        limit: int,
    ) -> SqlRelationMaterializationListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="cross-artifact-data-model-mapping",
            capability_prefix="common.relation-materialization",
        )
        try:
            result = service.list_relation_materializations(
                output_table_name=output_table_name,
                query_id=query_id,
                workflow_context_file=workflow_context_file,
                offset=offset,
                limit=limit,
            )
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "relation_materialization_unavailable", str(exc)) from exc
        items = []
        for raw in result.get("items") or ():
            item = dict(raw)
            provenance = item.pop("provenance_json", {})
            items.append(SqlRelationMaterialization(
                **item,
                provenance=dict(provenance) if isinstance(provenance, dict) else {},
            ))
        return SqlRelationMaterializationListResponse(
            materialization_query_schema_version=str(
                result.get("schema_version") or "relation-materialization-query/v1"
            ),
            system_id=system_id,
            revision_id=revision["revision_id"],
            filters=dict(result.get("filters") or {}),
            items=items,
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def get_sql_query_context(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str,
        query_id: str,
        scope_id: str | None,
    ) -> SqlQueryContextResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-analysis")
        try:
            result = service.get_sql_query_context(
                repo_id=repo_id, query_id=query_id, scope_id=scope_id
            )
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        if result.get("not_found"):
            raise KnowledgeApiRuntimeError(404, "sql_query_not_found", f"unknown SQL query: {query_id}")

        def statement_of(raw: Any) -> SqlStatementContext | None:
            if not isinstance(raw, dict):
                return None
            return SqlStatementContext(
                sql_statement_id=str(raw.get("sql_statement_id") or ""),
                query_id=str(raw.get("query_id") or query_id),
                file=str(raw.get("file") or ""),
                line_start=raw.get("line_start"), line_end=raw.get("line_end"),
                operation=raw.get("operation"), statement_type=raw.get("statement_type"),
                target_relation_name=raw.get("target_relation_name"), unit_kind=raw.get("unit_kind"),
                evidence_refs=self._sql_evidence_refs(raw.get("evidence_json"), fallback_file=raw.get("file"), fallback_line=raw.get("line_start")),
            )

        def scope_of(raw: Any) -> SqlSelectScopeContext | None:
            if not isinstance(raw, dict):
                return None
            return SqlSelectScopeContext(
                sql_select_scope_id=str(raw.get("sql_select_scope_id") or ""),
                query_id=str(raw.get("query_id") or query_id), file=str(raw.get("file") or ""),
                line_start=raw.get("line_start"), parent_scope_id=raw.get("parent_scope_id"),
                scope_kind=raw.get("scope_kind"), scope_name=raw.get("scope_name"),
                relation_count=int(raw.get("relation_count") or 0),
                projection_count=int(raw.get("projection_count") or 0),
                column_usage_count=int(raw.get("column_usage_count") or 0),
                evidence_refs=self._sql_evidence_refs(raw.get("evidence_json"), fallback_file=raw.get("file"), fallback_line=raw.get("line_start")),
            )

        relations = [
            SqlScopeRelationContext(
                sql_relation_id=str(row.get("sql_relation_id") or ""),
                relation_kind=str(row.get("relation_kind") or "unknown"),
                relation_name=str(row.get("relation_name") or ""), template_name=row.get("template_name"),
                logical_name=row.get("logical_name"), alias=row.get("alias"), usage_role=row.get("usage_role"),
                definition_status=row.get("definition_status"),
                observed_fields=[
                    SqlScopeRelationObservedField(name=str(field.get("name") or ""), usage_roles=[str(v) for v in field.get("usage_roles") or ()])
                    for field in row.get("observed_fields") or () if field.get("name")
                ],
                evidence_refs=self._sql_evidence_refs(row.get("evidence_json"), fallback_file=row.get("file"), fallback_line=row.get("line_start")),
            ) for row in result.get("scope_relations") or ()
        ]
        joins = [
            SqlJoinContext(
                sql_join_edge_id=str(row.get("sql_join_edge_id") or ""), join_ordinal=row.get("join_ordinal"),
                join_type=row.get("join_type"), condition_kind=row.get("condition_kind"), predicate=row.get("predicate"),
                left_relation_id=row.get("left_relation_id"), left_relation_ids=[str(v) for v in row.get("left_relation_ids_json") or ()],
                left_relation_names=[str(v) for v in row.get("left_relation_names_json") or ()],
                right_relation_id=row.get("right_relation_id"), right_relation_kind=row.get("right_relation_kind"),
                right_relation_name=row.get("right_relation_name"),
                participating_relation_ids=[str(v) for v in row.get("participating_relation_ids_json") or ()],
                column_pairs=[dict(v) for v in row.get("column_pairs_json") or () if isinstance(v, dict)],
                using_columns=[str(v) for v in row.get("using_columns_json") or ()],
                resolution_status=row.get("resolution_status"), physical_join_confirmed=bool(row.get("physical_join_confirmed")),
                evidence_refs=self._sql_evidence_refs(row.get("evidence_json"), fallback_file=row.get("file"), fallback_line=row.get("line_start")),
            ) for row in result.get("joins") or ()
        ]
        projections = [
            SqlProjectionContext(
                sql_projection_id=str(row.get("sql_projection_id") or ""), projection_ordinal=row.get("projection_ordinal"),
                output_name=row.get("output_name"), expression=row.get("expression"), expression_kind=row.get("expression_kind"),
                is_wildcard=bool(row.get("is_wildcard")), source_column_usage_ids=[str(v) for v in row.get("source_column_usage_ids_json") or ()],
                resolution_status=row.get("resolution_status"), resolution_basis=row.get("resolution_basis"),
                evidence_refs=self._sql_evidence_refs(row.get("evidence_json"), fallback_file=row.get("file"), fallback_line=row.get("line_start")),
            ) for row in result.get("projections") or ()
        ]
        return SqlQueryContextResponse(
            system_id=system_id, revision_id=revision["revision_id"], repo_id=repo_id, query_id=query_id,
            scope_id=result.get("scope_id") or scope_id,
            selection_status=str(result.get("selection_status") or ("not_found" if result.get("not_found") else "unknown")),
            statement=statement_of(result.get("statement")), scope=scope_of(result.get("scope")),
            child_scopes=[scope for raw in result.get("child_scopes") or () if (scope := scope_of(raw)) is not None],
            scope_candidates=[scope for raw in result.get("scope_candidates") or () if (scope := scope_of(raw)) is not None],
            scope_relations=relations, joins=joins, projections=projections,
            counts=SqlQueryContextCounts.model_validate(result.get("counts") or {}),
            diagnostics=[str(v) for v in result.get("diagnostics") or ()],
        )

    def get_sql_column_usage_context(
        self,
        system_id: str,
        sql_column_usage_id: str,
        *,
        revision_id: str | None,
    ) -> SqlColumnUsageContextResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._sql_query_service(system_id, revision, required_capability="common.sql-analysis")
        try:
            result = service.get_sql_column_usage_context(sql_column_usage_id)
        except SqlAnalysisUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "sql_analysis_unavailable", str(exc)) from exc
        except SqlColumnUsageNotFoundError as exc:
            raise KnowledgeApiRuntimeError(
                404,
                "sql_column_usage_not_found",
                f"unknown SQL column usage: {sql_column_usage_id}",
            ) from exc

        usage_raw = dict(result.get("usage") or {})
        usage = SqlColumnUsageContextUsage(
            sql_column_usage_id=str(usage_raw.get("sql_column_usage_id") or ""),
            repo_id=str(usage_raw.get("repo_id") or ""),
            query_id=str(usage_raw.get("query_id") or ""),
            scope_id=str(usage_raw.get("scope_id") or ""),
            file=str(usage_raw.get("file") or ""),
            line_start=usage_raw.get("line_start"),
            column_name=str(usage_raw.get("column_name") or ""),
            column_ordinal=usage_raw.get("column_ordinal"),
            usage_role=str(usage_raw.get("usage_role") or "unknown"),
            table_or_alias=usage_raw.get("table_or_alias"),
            relation_id=usage_raw.get("relation_id"),
            relation_kind=usage_raw.get("relation_kind"),
            relation_name=usage_raw.get("relation_name"),
            resolution_status=str(usage_raw.get("resolution_status") or "unknown"),
            resolution_basis=usage_raw.get("resolution_basis"),
            evidence_refs=self._sql_evidence_refs(
                usage_raw.get("evidence_json"),
                fallback_file=usage_raw.get("file"),
                fallback_line=usage_raw.get("line_start"),
            ),
        )

        statement_raw = result.get("statement")
        statement = None
        if isinstance(statement_raw, dict):
            statement = SqlStatementContext(
                sql_statement_id=str(statement_raw.get("sql_statement_id") or ""),
                query_id=str(statement_raw.get("query_id") or ""),
                file=str(statement_raw.get("file") or ""),
                line_start=statement_raw.get("line_start"),
                line_end=statement_raw.get("line_end"),
                operation=statement_raw.get("operation"),
                statement_type=statement_raw.get("statement_type"),
                target_relation_name=statement_raw.get("target_relation_name"),
                unit_kind=statement_raw.get("unit_kind"),
                evidence_refs=self._sql_evidence_refs(
                    statement_raw.get("evidence_json"),
                    fallback_file=statement_raw.get("file"),
                    fallback_line=statement_raw.get("line_start"),
                ),
            )

        scope_raw = result.get("scope")
        scope = None
        if isinstance(scope_raw, dict):
            scope = SqlSelectScopeContext(
                sql_select_scope_id=str(scope_raw.get("sql_select_scope_id") or ""),
                query_id=str(scope_raw.get("query_id") or ""),
                file=str(scope_raw.get("file") or ""),
                line_start=scope_raw.get("line_start"),
                parent_scope_id=scope_raw.get("parent_scope_id"),
                scope_kind=scope_raw.get("scope_kind"),
                scope_name=scope_raw.get("scope_name"),
                relation_count=int(scope_raw.get("relation_count") or 0),
                projection_count=int(scope_raw.get("projection_count") or 0),
                column_usage_count=int(scope_raw.get("column_usage_count") or 0),
                evidence_refs=self._sql_evidence_refs(
                    scope_raw.get("evidence_json"),
                    fallback_file=scope_raw.get("file"),
                    fallback_line=scope_raw.get("line_start"),
                ),
            )

        relations = [
            SqlScopeRelationContext(
                sql_relation_id=str(row.get("sql_relation_id") or ""),
                relation_kind=str(row.get("relation_kind") or "unknown"),
                relation_name=str(row.get("relation_name") or ""),
                template_name=row.get("template_name"),
                logical_name=row.get("logical_name"),
                alias=row.get("alias"),
                usage_role=row.get("usage_role"),
                definition_status=row.get("definition_status"),
                observed_fields=[
                    SqlScopeRelationObservedField(
                        name=str(field.get("name") or ""),
                        usage_roles=[str(value) for value in field.get("usage_roles") or ()],
                    )
                    for field in row.get("observed_fields") or ()
                    if field.get("name")
                ],
                evidence_refs=self._sql_evidence_refs(
                    row.get("evidence_json"),
                    fallback_file=row.get("file"),
                    fallback_line=row.get("line_start"),
                ),
            )
            for row in result.get("scope_relations") or ()
        ]
        joins = [
            SqlJoinContext(
                sql_join_edge_id=str(row.get("sql_join_edge_id") or ""),
                join_ordinal=row.get("join_ordinal"),
                join_type=row.get("join_type"),
                condition_kind=row.get("condition_kind"),
                predicate=row.get("predicate"),
                left_relation_id=row.get("left_relation_id"),
                left_relation_ids=[str(value) for value in row.get("left_relation_ids_json") or ()],
                left_relation_names=[str(value) for value in row.get("left_relation_names_json") or ()],
                right_relation_id=row.get("right_relation_id"),
                right_relation_kind=row.get("right_relation_kind"),
                right_relation_name=row.get("right_relation_name"),
                participating_relation_ids=[str(value) for value in row.get("participating_relation_ids_json") or ()],
                column_pairs=[dict(value) for value in row.get("column_pairs_json") or () if isinstance(value, dict)],
                using_columns=[str(value) for value in row.get("using_columns_json") or ()],
                resolution_status=row.get("resolution_status"),
                physical_join_confirmed=bool(row.get("physical_join_confirmed")),
                evidence_refs=self._sql_evidence_refs(
                    row.get("evidence_json"),
                    fallback_file=row.get("file"),
                    fallback_line=row.get("line_start"),
                ),
            )
            for row in result.get("joins") or ()
        ]
        projections = [
            SqlProjectionContext(
                sql_projection_id=str(row.get("sql_projection_id") or ""),
                projection_ordinal=row.get("projection_ordinal"),
                output_name=row.get("output_name"),
                expression=row.get("expression"),
                expression_kind=row.get("expression_kind"),
                is_wildcard=bool(row.get("is_wildcard")),
                source_column_usage_ids=[str(value) for value in row.get("source_column_usage_ids_json") or ()],
                resolution_status=row.get("resolution_status"),
                resolution_basis=row.get("resolution_basis"),
                evidence_refs=self._sql_evidence_refs(
                    row.get("evidence_json"),
                    fallback_file=row.get("file"),
                    fallback_line=row.get("line_start"),
                ),
            )
            for row in result.get("projections") or ()
        ]
        return SqlColumnUsageContextResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            usage=usage,
            statement=statement,
            scope=scope,
            scope_relations=relations,
            joins=joins,
            projections=projections,
            counts=SqlColumnUsageContextCounts.model_validate(result.get("counts") or {}),
        )


    def list_observed_storage_accesses(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        access_kind: str | None,
        storage_kind: str | None,
        target_resolution_status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> ObservedStorageAccessListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._storage_query_service(system_id, revision)
        try:
            result = service.list_accesses(
                repo_id=repo_id,
                access_kind=access_kind,
                storage_kind=storage_kind,
                target_resolution_status=target_resolution_status,
                search=search,
                offset=offset,
                limit=limit,
            )
        except ObservedStorageUsageUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "observed_storage_usage_unavailable", str(exc)) from exc
        return ObservedStorageAccessListResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=[ObservedStorageAccess.model_validate(item) for item in result["items"]],
            page=PageMeta(offset=offset, limit=limit, total=int(result["total_count"])),
            summary=ObservedStorageSummary.model_validate(result["summary"]),
        )

    def list_observed_storage_gaps(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        gap_code: str | None,
        severity: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> ObservedStorageGapListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        service = self._storage_query_service(system_id, revision)
        try:
            result = service.list_gaps(
                repo_id=repo_id,
                gap_code=gap_code,
                severity=severity,
                search=search,
                offset=offset,
                limit=limit,
            )
        except ObservedStorageUsageUnavailableError as exc:
            raise KnowledgeApiRuntimeError(409, "observed_storage_usage_unavailable", str(exc)) from exc
        return ObservedStorageGapListResponse(
            system_id=system_id,
            revision_id=revision["revision_id"],
            items=[ObservedStorageGap.model_validate(item) for item in result["items"]],
            page=PageMeta(offset=offset, limit=limit, total=int(result["total_count"])),
            summary=ObservedStorageSummary.model_validate(result["summary"]),
        )

    def _prepare_publication(self, system_id: str, request: RevisionCreateRequest) -> dict[str, Any]:
        execution_result_path = self.validator.validate(request.execution_result)
        payload = validate_knowledge_execution_result(load_json_object(execution_result_path))
        base_revision = self._resolve_publication_base(system_id, request.base_revision_id, payload)
        execution = execution_summary(payload)
        discovered = discover_knowledge_artifact_files(
            payload,
            execution_result_path=execution_result_path,
            path_guard=self.validator.validate_path,
        )
        observed_discovered = discover_observed_artifact_files(
            payload,
            execution_result_path=execution_result_path,
            path_guard=self.validator.validate_path,
        )
        publishable_observed_ids = {str(item.artifact.get("artifact_id") or "") for item in observed_discovered}
        produced_knowledge_ids = {
            str(item.get("artifact_id") or "")
            for item in payload.get("knowledge_artifacts") or ()
            if isinstance(item, Mapping)
        }
        same_system_external_ids = {
            str(item.get("artifact_id") or "")
            for item in payload.get("external_knowledge_artifacts") or ()
            if isinstance(item, Mapping) and str(item.get("source_system_id") or "") == system_id
        }
        exact_dependencies_by_product: dict[str, list[str]] = {}
        for materialization in payload.get("materialization_executions") or ():
            if not isinstance(materialization, Mapping):
                continue
            observed_inputs = {str(v) for v in materialization.get("input_artifact_ids") or () if str(v)}
            knowledge_inputs = {str(v) for v in materialization.get("input_knowledge_artifact_ids") or () if str(v)}
            exact_inputs = sorted(
                (observed_inputs & publishable_observed_ids)
                | (knowledge_inputs & produced_knowledge_ids)
                | (knowledge_inputs & same_system_external_ids)
            )
            for output_id in materialization.get("knowledge_artifact_ids") or ():
                exact_dependencies_by_product[str(output_id)] = exact_inputs

        published: list[PublishedKnowledgeArtifact] = []
        summary: dict[str, Any] = {
            "knowledge_artifact_count": 0,
            "model_kinds": [],
            "capabilities": sorted({str(value) for value in payload.get("published_capabilities") or []}),
            "effective_entity_count": 0,
            "effective_field_count": 0,
            "effective_relationship_count": 0,
            "physical_model_table_count": 0,
            "sql_relation_count": 0,
            "observed_storage_access_count": 0,
        }
        for item in discovered:
            database = build_artifact(
                item.database_path,
                schema_version=str(item.artifact.get("schema_version") or ""),
            )
            manifest = build_artifact(
                item.manifest_path,
                schema_version="knowledge_layer/v1",
                media_type="application/json",
            )
            self.validator.validate(database)
            self.validator.validate(manifest)
            materialization_id = str(item.artifact["source_materialization_id"])
            published_item = PublishedKnowledgeArtifact(
                artifact_id=str(item.artifact["artifact_id"]),
                model_kind=str(item.artifact["model_kind"]),
                schema_version=str(item.artifact["schema_version"]),
                product_slot_id=f"klc:{materialization_id}",
                origin_kind=ProductOriginKind.DERIVED,
                producer_ref="knowledge-layer-core",
                producer_contract_ref="knowledge_layer/v1",
                source_materialization_id=materialization_id,
                content_fingerprint=str(item.artifact["content_fingerprint"]),
                physical_artifacts=[
                    ProductPhysicalArtifact(role="database", **database.model_dump()),
                    ProductPhysicalArtifact(role="manifest", **manifest.model_dump()),
                ],
                capabilities=list(item.capabilities),
                coverage=dict(item.artifact.get("coverage") or {}),
                diagnostics=[dict(value) for value in item.artifact.get("diagnostics") or [] if isinstance(value, dict)],
                provenance={"materialization_id": materialization_id},
                exact_dependency_product_ids=list(exact_dependencies_by_product.get(str(item.artifact["artifact_id"]), [])),
            )
            published.append(published_item)

            config = KnowledgeArtifactSource(
                system_id=system_id,
                database_path=item.database_path,
                manifest_path=item.manifest_path,
            )
            try:
                if published_item.model_kind == "effective-data-model":
                    service = self.query_factory.get(config)
                    catalog = service.field_catalog(system_id)
                    summary["effective_entity_count"] = len(catalog.tables)
                    summary["effective_field_count"] = sum(len(table.fields) for table in catalog.tables)
                    summary["effective_relationship_count"] = sum(service.relationship_counts().values())
                elif published_item.model_kind == "physical-data-model":
                    service = self.knowledge_query_factory.get(config)
                    physical = service.physical_model_summary()
                    summary["physical_model_table_count"] = int((physical.get("counts") or {}).get("tables") or 0)
                elif "common.observed-storage-usage" in published_item.capabilities:
                    service = self.storage_query_factory.get(config)
                    summary["observed_storage_access_count"] = int(service.summary()["access_count"])
                elif any(capability.startswith("common.sql") for capability in published_item.capabilities):
                    service = self.knowledge_query_factory.get(config)
                    summary["sql_relation_count"] = service.sql_relation_count()
            except Exception as exc:
                raise KnowledgeApiRuntimeError(
                    400,
                    "knowledge_artifact_query_validation_failed",
                    f"published knowledge artifact cannot be queried: {published_item.artifact_id}",
                    details={"model_kind": published_item.model_kind, "error": str(exc)},
                ) from exc

        for item in observed_discovered:
            raw = item.artifact
            physical_artifacts: list[ProductPhysicalArtifact] = []
            for member in item.physical_files:
                built = build_artifact(
                    member.path,
                    schema_version=member.schema_version,
                    media_type=member.media_type,
                )
                physical_artifacts.append(ProductPhysicalArtifact(role=member.role, **built.model_dump()))
            descriptor = next(value for value in physical_artifacts if value.role == "descriptor")
            location = raw.get("location") or {}
            expected_sha = str(location.get("sha256") or "")
            if expected_sha and descriptor.sha256 != expected_sha:
                raise KnowledgeApiRuntimeError(409, "observed_artifact_digest_mismatch", "Core evidence descriptor digest differs from published artifact digest")
            producer = (raw.get("provenance") or {}).get("producer") or item.payload.get("producer") or {}
            analyzer_id = str(producer.get("analyzer_id") or "core-evidence-runtime")
            component = str(producer.get("component") or "code-analyzer-core")
            diagnostics_raw = item.payload.get("diagnostics")
            diagnostics = [dict(v) for v in diagnostics_raw if isinstance(v, dict)] if isinstance(diagnostics_raw, list) else []
            published.append(PublishedKnowledgeArtifact(
                artifact_id=str(raw["artifact_id"]),
                model_kind=str(raw["artifact_kind"]),
                schema_version=str(raw["schema_version"]),
                product_slot_id=observed_product_slot_id(raw, payload=item.payload),
                origin_kind=ProductOriginKind.OBSERVED,
                producer_ref=f"{component}:{analyzer_id}",
                producer_contract_ref=str(raw.get("contract_version") or "core_evidence_artifact_contract/v1"),
                content_fingerprint=str(raw["content_fingerprint"]),
                physical_artifacts=physical_artifacts,
                capabilities=[],
                coverage=dict(raw.get("coverage") or item.payload.get("coverage") or {}),
                diagnostics=diagnostics,
                provenance=dict(raw.get("provenance") or item.payload.get("provenance") or {}),
            ))

        if not published:
            raise KnowledgeApiRuntimeError(400, "knowledge_artifacts_missing", "execution produced no publishable artifacts")

        produced = list(published)
        retained: list[PublishedKnowledgeArtifact] = []
        if base_revision is not None:
            produced_slots = {str(item.product_slot_id) for item in produced}
            base_slots: set[str] = set()
            for raw in base_revision.get("knowledge_artifacts") or ():
                item = PublishedKnowledgeArtifact.model_validate(raw)
                slot = str(item.product_slot_id)
                if slot in base_slots:
                    raise KnowledgeApiRuntimeError(
                        409,
                        "base_revision_product_slot_ambiguous",
                        "base revision contains multiple products for one replacement slot",
                        details={"product_slot_id": slot},
                    )
                base_slots.add(slot)
                if slot in produced_slots:
                    continue
                # Retained products are exact immutable AISL-managed products.
                self._validate_published_product_bytes(item)
                retained.append(item)

        published = sorted(
            retained + produced,
            key=lambda item: (str(item.product_slot_id), str(item.artifact_id)),
        )
        artifact_ids = [str(item.artifact_id) for item in published]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise KnowledgeApiRuntimeError(
                409,
                "revision_artifact_identity_conflict",
                "composed revision contains duplicate artifact ids",
            )
        artifact_id_set = set(artifact_ids)
        unresolved_dependencies = {
            str(item.artifact_id): sorted(set(item.exact_dependency_product_ids) - artifact_id_set)
            for item in published
            if set(item.exact_dependency_product_ids) - artifact_id_set
        }
        if unresolved_dependencies:
            raise KnowledgeApiRuntimeError(
                409,
                "revision_exact_dependency_unresolved",
                "composed revision would contain products whose exact dependencies are absent",
                details={"products": unresolved_dependencies},
            )
        snapshot_capabilities = sorted(
            {str(capability) for item in published for capability in item.capabilities if str(capability)}
        )
        summary["knowledge_artifact_count"] = len(published)
        summary["produced_knowledge_artifact_count"] = len(produced)
        summary["retained_knowledge_artifact_count"] = len(retained)
        summary["base_revision_id"] = request.base_revision_id
        summary["model_kinds"] = sorted({item.model_kind for item in published})
        summary["capabilities"] = snapshot_capabilities
        return {
            "execution": execution,
            "execution_result_path": execution_result_path,
            "knowledge_artifacts": published,
            "capabilities": tuple(snapshot_capabilities),
            "summary": summary,
        }

    def _validate_published_product_bytes(self, item: PublishedKnowledgeArtifact) -> None:
        for physical in item.physical_artifacts:
            self.validator.validate(physical)

    def _import_publication_artifacts(
        self,
        prepared: dict[str, Any],
        request: RevisionCreateRequest,
    ) -> tuple[PublishedArtifact, list[PublishedKnowledgeArtifact]]:
        execution_source = self.validator.validate(request.execution_result)
        execution_result = self.artifact_store.import_artifact(request.execution_result, execution_source)
        imported_products: list[PublishedKnowledgeArtifact] = []
        for item in prepared["knowledge_artifacts"]:
            imported_members: list[ProductPhysicalArtifact] = []
            for physical in item.physical_artifacts:
                source = self.validator.validate(physical)
                imported_physical = self.artifact_store.import_artifact(physical, source)
                imported_members.append(ProductPhysicalArtifact.model_validate(imported_physical.model_dump()))
            imported = item.model_copy(update={"physical_artifacts": imported_members})
            self._validate_published_product_bytes(imported)
            imported_products.append(imported)
        return execution_result, imported_products

    def _resolve_publication_base(
        self,
        system_id: str,
        base_revision_id: str | None,
        payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        external = [
            raw for raw in payload.get("external_knowledge_artifacts") or ()
            if isinstance(raw, Mapping) and str(raw.get("source_system_id") or "") == system_id
        ]
        if external and not base_revision_id:
            raise KnowledgeApiRuntimeError(
                409,
                "publication_base_revision_required",
                "same-system prior-revision dependencies require an explicit base_revision_id",
                details={
                    "source_revision_ids": sorted({str(raw.get("source_revision_id") or "") for raw in external}),
                },
            )
        if not base_revision_id:
            return None
        base = self.store.get_revision(system_id, base_revision_id)
        if base is None:
            raise KnowledgeApiRuntimeError(
                404,
                "base_revision_not_found",
                f"unknown base revision: {base_revision_id}",
            )
        base_by_id = {
            str(raw.get("artifact_id") or ""): raw
            for raw in base.get("knowledge_artifacts") or ()
            if isinstance(raw, dict)
        }
        for raw in external:
            source_revision_id = str(raw.get("source_revision_id") or "")
            if source_revision_id != base_revision_id:
                raise KnowledgeApiRuntimeError(
                    409,
                    "publication_base_revision_mismatch",
                    "same-system external dependency does not belong to the explicit base revision",
                    details={
                        "artifact_id": str(raw.get("artifact_id") or ""),
                        "expected_revision_id": base_revision_id,
                        "actual_revision_id": source_revision_id,
                    },
                )
            artifact_id = str(raw.get("artifact_id") or "")
            candidate = base_by_id.get(artifact_id)
            if candidate is None:
                raise KnowledgeApiRuntimeError(
                    409,
                    "publication_base_dependency_missing",
                    "same-system external dependency is absent from the explicit base revision",
                    details={"artifact_id": artifact_id, "base_revision_id": base_revision_id},
                )
            comparable = ("artifact_id", "model_kind", "schema_version", "source_materialization_id", "content_fingerprint")
            mismatched = {
                key: {"expected": str(candidate.get(key) or ""), "actual": str(raw.get(key) or "")}
                for key in comparable
                if str(candidate.get(key) or "") != str(raw.get(key) or "")
            }
            expected_capabilities = sorted(str(value) for value in candidate.get("capabilities") or ())
            actual_capabilities = sorted(str(value) for value in raw.get("published_capabilities") or ())
            if expected_capabilities != actual_capabilities:
                mismatched["published_capabilities"] = {
                    "expected": expected_capabilities,
                    "actual": actual_capabilities,
                }
            if mismatched:
                raise KnowledgeApiRuntimeError(
                    409,
                    "publication_base_dependency_identity_mismatch",
                    "same-system external dependency identity does not match the base revision",
                    details={"artifact_id": artifact_id, "mismatched": mismatched},
                )
        return base

    @staticmethod
    def _artifact_record_by_id(revision: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        for raw in revision.get("knowledge_artifacts") or ():
            if isinstance(raw, dict) and str(raw.get("artifact_id") or "") == artifact_id:
                return raw
        raise KnowledgeApiRuntimeError(404, "knowledge_artifact_not_found", f"unknown knowledge artifact: {artifact_id}")

    def _artifact_record(
        self,
        revision: dict[str, Any],
        *,
        model_kind: str | None = None,
        capability_prefix: str | None = None,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for raw in revision.get("knowledge_artifacts") or []:
            if not isinstance(raw, dict):
                continue
            if model_kind is not None and str(raw.get("model_kind") or "") != model_kind:
                continue
            capabilities = [str(value) for value in raw.get("capabilities") or []]
            if capability_prefix is not None and not any(value.startswith(capability_prefix) for value in capabilities):
                continue
            candidates.append(raw)
        if not candidates:
            detail = model_kind or capability_prefix or "requested"
            raise KnowledgeApiRuntimeError(
                409,
                "knowledge_artifact_unavailable",
                f"revision does not contain a knowledge artifact for {detail}",
            )
        locations = {
            str((_product_artifact_dict_by_role(item, "database") or {}).get("sha256") or "") for item in candidates
        }
        if len(locations) > 1:
            raise KnowledgeApiRuntimeError(
                409,
                "knowledge_artifact_ambiguous",
                "multiple knowledge artifacts satisfy the requested query capability",
                details={"artifact_ids": sorted(str(item.get("artifact_id") or "") for item in candidates)},
            )
        return candidates[0]

    def list_attribute_extension_context(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        source_type: str | None,
        source_field: str | None,
        target_type: str | None,
        join_method: str | None,
        confidence: str | None,
        sql_generation_status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> AttributeExtensionContextResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="data-model-attribute-extension-context",
            capability_prefix="common.data-model-agent-join-semantics",
        )
        try:
            result = query.list_attribute_extension_join_semantics(
                source_type=source_type,
                source_field=source_field,
                target_type=target_type,
                join_method=join_method,
                confidence=confidence,
                sql_generation_status=sql_generation_status,
                search=search,
                offset=offset,
                limit=limit,
                include_gaps=True,
                max_gaps=min(500, max(100, limit * 2)),
            )
        except AttributeExtensionContextUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "data_model_attribute_extension_unavailable", str(exc)) from exc
        return AttributeExtensionContextResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            filters={key: value for key, value in dict(result.get("filters") or {}).items() if value is not None},
            items=[AttributeExtensionJoinSemantic(**dict(row)) for row in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
            summary=AttributeExtensionContextSummary(**dict(result.get("summary") or {})),
            object_anchors=[dict(row) for row in result.get("object_anchors") or ()],
            gaps=[dict(row) for row in result.get("gaps") or ()],
            gap_count=int(result.get("gap_count") or 0),
            gaps_truncated=bool(result.get("gaps_truncated")),
        )


    def get_attribute_extension_guidance(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        source_type: str | None,
        source_field: str | None,
        target_type: str | None,
        join_method: str | None,
        confidence: str | None,
        sql_generation_status: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> AttributeExtensionGuidanceResponse:
        canonical = self.list_attribute_extension_context(
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
        projected = project_attribute_extension_guidance(
            canonical.model_dump(mode="json", exclude_none=True)
        )
        return AttributeExtensionGuidanceResponse(**projected)

    @staticmethod
    def _annotation_names(value: str | None) -> list[str]:
        if value is None:
            return []
        result: list[str] = []
        seen: set[str] = set()
        for raw in value.split(","):
            name = raw.strip()
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def summarize_declared_data_model(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        type_annotations: str | None,
        exclude_field_annotations: str | None,
    ) -> DeclaredDataModelSummaryResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="code-declared-data-model",
            capability_prefix="common.code-declared-data-model",
        )
        try:
            result = query.summarize_code_declared_model(
                repo_id=repo_id,
                type_annotations=self._annotation_names(type_annotations),
                exclude_field_annotations=self._annotation_names(exclude_field_annotations),
            )
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "declared_data_model_unavailable", str(exc)) from exc
        return DeclaredDataModelSummaryResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            filters=dict(result.get("filters") or {}),
            build=dict(result.get("build") or {}),
            counts={str(key): int(value) for key, value in dict(result.get("counts") or {}).items()},
            type_annotation_counts=[dict(row) for row in result.get("type_annotation_counts") or ()],
            field_annotation_counts=[dict(row) for row in result.get("field_annotation_counts") or ()],
            gap_counts=[dict(row) for row in result.get("gap_counts") or ()],
        )

    def list_declared_data_objects(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        repo_id: str | None,
        search: str | None,
        type_annotations: str | None,
        include_fields: bool,
        offset: int,
        limit: int,
    ) -> DeclaredDataObjectListResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="code-declared-data-model",
            capability_prefix="common.code-declared-data-model",
        )
        try:
            result = query.list_code_declared_objects(
                repo_id=repo_id,
                search=search,
                type_annotations=self._annotation_names(type_annotations),
                include_fields=include_fields,
                offset=offset,
                limit=limit,
            )
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "declared_data_model_unavailable", str(exc)) from exc
        return DeclaredDataObjectListResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            filters={key: value for key, value in dict(result.get("filters") or {}).items() if value is not None},
            items=[DeclaredDataObjectSummary(**dict(row)) for row in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def get_declared_data_object(
        self,
        system_id: str,
        object_id: str,
        *,
        revision_id: str | None,
    ) -> DeclaredDataObjectDetailResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="code-declared-data-model",
            capability_prefix="common.code-declared-data-model",
        )
        try:
            result = query.get_code_declared_object(object_id)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "declared_data_model_unavailable", str(exc)) from exc
        raw_object = result.get("object")
        if not isinstance(raw_object, dict):
            raise KnowledgeApiRuntimeError(
                404,
                "declared_data_object_not_found",
                f"declared data object {object_id!r} was not found in the selected revision",
            )
        return DeclaredDataObjectDetailResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            object=DeclaredDataObjectDetail(**dict(raw_object)),
        )

    def get_data_model_object_context(
        self,
        system_id: str,
        object_id: str,
        *,
        revision_id: str | None,
    ) -> DataModelObjectContextResponse:
        revision = self._resolve_revision(system_id, revision_id)
        declared_query = self._knowledge_query_service(
            system_id,
            revision,
            model_kind="code-declared-data-model",
            capability_prefix="common.code-declared-data-model",
        )
        try:
            declared_result = declared_query.get_code_declared_object(object_id)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "declared_data_model_unavailable", str(exc)) from exc
        raw_object = declared_result.get("object")
        if not isinstance(raw_object, dict):
            raise KnowledgeApiRuntimeError(
                404,
                "declared_data_object_not_found",
                f"declared data object {object_id!r} was not found in the selected revision",
            )

        capabilities = {str(value) for value in revision.get("capabilities") or ()}
        logical_storage = None
        model_storage = None
        if "common.logical-storage-mapping" in capabilities:
            logical_query = self._knowledge_query_service(
                system_id,
                revision,
                model_kind="logical-storage-model-mapping",
                capability_prefix="common.logical-storage-mapping",
            )
            logical_storage = logical_query.get_logical_storage_object_context(object_id)
        if "common.model-storage-semantics" in capabilities:
            storage_query = self._knowledge_query_service(
                system_id,
                revision,
                model_kind="model-storage-semantics",
                capability_prefix="common.model-storage-semantics",
            )
            model_storage = storage_query.get_model_storage_object_context(str(raw_object.get("fqcn") or ""))

        projected = build_data_model_object_context(
            raw_object,
            logical_storage=logical_storage,
            model_storage=model_storage,
            published_capabilities=capabilities,
        )
        return DataModelObjectContextResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            **projected,
        )

    def list_data_model_lineage(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        logical_type: str | None,
        logical_field: str | None,
        target_table: str | None,
        target_column: str | None,
        knowledge_class: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> DataModelLineageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        artifact = self._artifact_record(
            revision,
            model_kind="cross-artifact-data-model-mapping",
            capability_prefix="common.value-origin-physical-lineage",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            query = self.data_model_lineage_query_factory.get(config)
            result = query.list_lineage(
                logical_type=logical_type,
                logical_field=logical_field,
                target_table=target_table,
                target_column=target_column,
                knowledge_class=knowledge_class,
                search=search,
                offset=offset,
                limit=limit,
            )
        except DataModelLineageUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "data_model_lineage_unavailable", str(exc)) from exc
        return DataModelLineageResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            filters={key: value for key, value in dict(result.get("filters") or {}).items() if value is not None},
            items=[DataModelLineageItem(**dict(row)) for row in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
            summary=DataModelLineageSummary(**dict(result.get("summary") or {})),
        )

    @staticmethod
    def _interaction_page_response(
        *,
        system_id: str,
        revision_id: str,
        result: dict[str, Any],
        filters: dict[str, Any],
        offset: int,
        limit: int,
    ) -> InteractionKnowledgePageResponse:
        return InteractionKnowledgePageResponse(
            system_id=system_id,
            revision_id=revision_id,
            query_kind=str(result.get("query_kind") or "interaction-query"),
            filters={key: value for key, value in filters.items() if value is not None},
            items=[dict(row) for row in result.get("items") or ()],
            page=PageMeta(offset=offset, limit=limit, total=int(result.get("total_count") or 0)),
        )

    def list_system_interactions(
        self, system_id: str, *, revision_id: str | None, source_repo_id: str | None,
        target_repo_id: str | None, protocol: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.system-interactions")
        filters = {"source_repo_id": source_repo_id, "target_repo_id": target_repo_id, "protocol": protocol}
        result = query.list_system_interactions(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)

    def list_system_boundary_interactions(
        self, system_id: str, *, revision_id: str | None, interaction_id: str | None,
        source_repo_id: str | None, target_repo_id: str | None, match_status: str | None,
        confidence: str | None, local_execution_status: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.system-interactions")
        filters = {
            "interaction_id": interaction_id,
            "source_repo_id": source_repo_id,
            "target_repo_id": target_repo_id,
            "match_status": match_status,
            "confidence": confidence,
            "local_execution_status": local_execution_status,
        }
        result = query.list_system_boundary_interactions(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(
            system_id=system_id, revision_id=str(revision["revision_id"]), result=result,
            filters=filters, offset=offset, limit=limit,
        )

    def get_system_interaction_guidance(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        interaction_id: str,
        context_limit: int,
        field_limit: int,
    ) -> SystemInteractionGuidanceResponse:
        revision = self._resolve_revision(system_id, revision_id)
        resolved_revision_id = str(revision["revision_id"])
        interaction_query = self._knowledge_query_service(
            system_id,
            revision,
            capability_prefix="workspace.system-interactions",
        )
        boundary_result = interaction_query.list_system_boundary_interactions(
            interaction_id=interaction_id,
            offset=0,
            limit=50,
        )
        boundary_items = [
            dict(value)
            for value in boundary_result.get("items") or ()
            if isinstance(value, Mapping)
        ]
        if not boundary_items:
            raise KnowledgeApiRuntimeError(
                404,
                "system_interaction_not_found",
                f"unknown system interaction in revision {resolved_revision_id}: {interaction_id}",
            )

        context_items: list[dict[str, Any]] = []
        context_totals: dict[str, int] = {}
        for boundary in boundary_items:
            boundary_id = str(boundary.get("boundary_interaction_id") or "")
            page = interaction_query.list_system_interaction_execution_contexts(
                boundary_interaction_id=boundary_id,
                interaction_id=interaction_id,
                offset=0,
                limit=context_limit,
            )
            context_items.extend(
                dict(value)
                for value in page.get("items") or ()
                if isinstance(value, Mapping)
            )
            context_totals[boundary_id] = int(page.get("total_count") or 0)
        context_result: dict[str, Any] = {
            "items": context_items,
            "total_count": sum(context_totals.values()),
            "total_count_by_boundary": context_totals,
        }

        published_capabilities = {
            str(capability)
            for artifact in revision.get("knowledge_artifacts") or ()
            if isinstance(artifact, Mapping)
            for capability in artifact.get("capabilities") or ()
            if str(capability)
        }
        field_result: dict[str, Any] | None = None
        if "workspace.system-interaction-field-contracts" in published_capabilities:
            field_query = self._knowledge_query_service(
                system_id,
                revision,
                capability_prefix="workspace.system-interaction-field-contracts",
            )
            field_items: list[dict[str, Any]] = []
            field_totals: dict[str, int] = {}
            for boundary in boundary_items:
                boundary_id = str(boundary.get("boundary_interaction_id") or "")
                page = field_query.list_system_interaction_field_contracts(
                    boundary_interaction_id=boundary_id,
                    interaction_id=interaction_id,
                    offset=0,
                    limit=field_limit,
                )
                field_items.extend(
                    dict(value)
                    for value in page.get("items") or ()
                    if isinstance(value, Mapping)
                )
                field_totals[boundary_id] = int(page.get("total_count") or 0)
            field_result = {
                "items": field_items,
                "total_count": sum(field_totals.values()),
                "total_count_by_boundary": field_totals,
            }

        projected = project_system_interaction_guidance(
            system_id=system_id,
            revision_id=resolved_revision_id,
            interaction_id=interaction_id,
            boundary_result=boundary_result,
            execution_context_result=context_result,
            field_contract_result=field_result,
            context_limit=context_limit,
            field_limit=field_limit,
        )
        return SystemInteractionGuidanceResponse(**projected)

    def list_repository_interaction_boundaries(
        self, system_id: str, *, revision_id: str | None, repo_id: str | None, repository_system_id: str | None,
        project_id: str | None, direction: str | None, protocol: str | None, http_method: str | None,
        service_identity: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.repository-interaction-boundaries")
        filters = {"repo_id": repo_id, "system_id": repository_system_id, "project_id": project_id, "direction": direction, "protocol": protocol, "http_method": http_method, "service_identity": service_identity}
        result = query.list_repository_interaction_boundaries(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)

    def list_system_interaction_execution_contexts(
        self, system_id: str, *, revision_id: str | None, boundary_interaction_id: str | None,
        interaction_id: str | None, source_repo_id: str | None, trigger_kind: str | None,
        path_status: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.system-interactions")
        filters = {"boundary_interaction_id": boundary_interaction_id, "interaction_id": interaction_id, "source_repo_id": source_repo_id, "trigger_kind": trigger_kind, "path_status": path_status}
        result = query.list_system_interaction_execution_contexts(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)

    def list_system_interaction_field_contracts(
        self, system_id: str, *, revision_id: str | None, boundary_interaction_id: str | None,
        interaction_id: str | None, source_repo_id: str | None, target_repo_id: str | None,
        wire_path: str | None, match_status: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.system-interaction-field-contracts")
        filters = {"boundary_interaction_id": boundary_interaction_id, "interaction_id": interaction_id, "source_repo_id": source_repo_id, "target_repo_id": target_repo_id, "wire_path": wire_path, "match_status": match_status}
        result = query.list_system_interaction_field_contracts(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)

    def list_system_interaction_diagnostics(
        self, system_id: str, *, revision_id: str | None, source_repo_id: str | None,
        match_status: str | None, offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.system-interactions")
        filters = {"source_repo_id": source_repo_id, "match_status": match_status}
        result = query.list_system_interaction_diagnostics(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)

    def list_repository_interaction_coverage(
        self, system_id: str, *, revision_id: str | None, repo_id: str | None, repository_system_id: str | None,
        project_id: str | None, coverage_status: str | None, matching_coverage_status: str | None,
        offset: int, limit: int,
    ) -> InteractionKnowledgePageResponse:
        revision = self._resolve_revision(system_id, revision_id)
        query = self._knowledge_query_service(system_id, revision, capability_prefix="workspace.repository-interaction-coverage")
        filters = {"repo_id": repo_id, "system_id": repository_system_id, "project_id": project_id, "coverage_status": coverage_status, "matching_coverage_status": matching_coverage_status}
        result = query.list_repository_interaction_coverage(offset=offset, limit=limit, **filters)
        return self._interaction_page_response(system_id=system_id, revision_id=str(revision["revision_id"]), result=result, filters=filters, offset=offset, limit=limit)


    def get_system_description_guidance(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        technology_limit: int,
        interface_limit: int,
        integration_limit: int,
        event_limit: int,
        storage_limit: int,
        journey_limit: int,
        gap_limit: int,
    ) -> SystemDescriptionGuidanceResponse:
        revision = self._resolve_revision(system_id, revision_id)
        resolved_revision_id = str(revision["revision_id"])
        artifact = self._artifact_record(
            revision,
            model_kind="system-description",
            capability_prefix="common.system-description",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            query = self.reporting_query_factory.get(config)
            scope = query.call("get_scope_overview", max_results=1)
            composition = query.call("get_repository_composition", max_results=100)
            # Read the canonical bounded reporting set so KLC-owned summaries/counts
            # remain exact; the consumer projection applies the much smaller
            # presentation limits below.
            technologies = query.call("get_technologies", max_results=500)
            interfaces = query.call("list_interfaces", max_results=500)
            integrations = query.call("list_integrations", max_results=500)
            events = query.call("list_events", max_results=500)
            storage = query.call(
                "list_data_objects",
                filters={"representative": True},
                max_results=500,
            )
            journeys = query.call("get_representative_journeys", max_results=500)
            gaps = query.call("get_gap_summary", max_results=500)
            coverage = query.call("get_analysis_coverage", max_results=10)
        except ReportingKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "system_description_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_system_description_query", str(exc)) from exc

        projected = project_system_description_guidance(
            system_id=system_id,
            revision_id=resolved_revision_id,
            scope_result=scope,
            composition_result=composition,
            technologies_result=technologies,
            interfaces_result=interfaces,
            integrations_result=integrations,
            events_result=events,
            storage_result=storage,
            journeys_result=journeys,
            gaps_result=gaps,
            coverage_result=coverage,
            limits={
                "technology_limit": technology_limit,
                "interface_limit": interface_limit,
                "integration_limit": integration_limit,
                "event_limit": event_limit,
                "storage_limit": storage_limit,
                "journey_limit": journey_limit,
                "gap_limit": gap_limit,
            },
        )
        return SystemDescriptionGuidanceResponse(**projected)

    def query_system_description(
        self,
        system_id: str,
        request: ReportingKnowledgeQueryRequest,
    ) -> ReportingKnowledgeQueryResponse:
        revision = self._resolve_revision(system_id, request.revision_id)
        artifact = self._artifact_record(
            revision,
            model_kind="system-description",
            capability_prefix="common.system-description",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            query = self.reporting_query_factory.get(config)
            result = query.call(
                request.query_kind,
                filters=request.filters,
                max_results=request.max_results,
            )
        except ReportingKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "system_description_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_system_description_query", str(exc)) from exc
        return ReportingKnowledgeQueryResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            query=dict(result.get("query") or {}),
            items=[dict(item) for item in result.get("items") or ()],
            summary=dict(result.get("summary") or {}),
            evidence=[dict(item) for item in result.get("evidence") or ()],
            gaps=[dict(item) for item in result.get("gaps") or ()],
            pagination=dict(result.get("pagination") or {}) if result.get("pagination") is not None else None,
        )


    def query_reference_data(
        self,
        system_id: str,
        request: ReferenceDataQueryRequest,
    ) -> ReportingKnowledgeQueryResponse:
        revision = self._resolve_revision(system_id, request.revision_id)
        artifact = self._artifact_record(
            revision,
            model_kind="reference-data",
            capability_prefix="common.reference-data",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            query = self.reference_data_query_factory.get(config)
            result = query.call(
                request.query_kind,
                filters=request.filters,
                max_results=request.max_results,
            )
        except ReferenceDataKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "reference_data_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_reference_data_query", str(exc)) from exc
        return ReportingKnowledgeQueryResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            query=dict(result.get("query") or {}),
            items=[dict(item) for item in result.get("items") or ()],
            summary=dict(result.get("summary") or {}),
            evidence=[dict(item) for item in result.get("evidence") or ()],
            gaps=[dict(item) for item in result.get("gaps") or ()],
            pagination=dict(result.get("pagination") or {}) if result.get("pagination") is not None else None,
        )

    def get_reference_data_guidance(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        token: str,
        candidate_limit: int,
        local_definition_limit: int,
        literal_write_limit: int,
        usage_limit: int,
        gap_limit: int,
        evidence_limit: int,
    ) -> ReferenceDataGuidanceResponse:
        revision = self._resolve_revision(system_id, revision_id)
        resolved_revision_id = str(revision["revision_id"])
        artifact = self._artifact_record(
            revision,
            model_kind="reference-data",
            capability_prefix="common.reference-data",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        normalized_token = str(token or "").strip()
        try:
            query = self.reference_data_query_factory.get(config)
            discovery = None
            context = None
            semantic_policy: dict[str, Any] = {
                "facts_only": True,
                "official_nsi_status_established": False,
                "ownership_established": False,
                "source_of_truth_established": False,
                "human_validation_required": True,
                "absence_is_not_proof": True,
            }
            if normalized_token:
                # Keep KLC-owned totals exact; presentation is bounded only afterwards.
                context = query.call(
                    "get_candidate_context",
                    filters={"token": normalized_token, "include_non_production": True},
                    max_results=10000,
                )
                context_items = [item for item in context.get("items") or () if isinstance(item, Mapping)]
                if context_items:
                    policy = context_items[0].get("interpretation_policy")
                    if isinstance(policy, Mapping):
                        semantic_policy.update(dict(policy))
            else:
                discovery = query.call(
                    "search_reference_data",
                    filters={"include_non_production": True},
                    max_results=10000,
                )
        except ReferenceDataKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "reference_data_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_reference_data_query", str(exc)) from exc

        projected = project_reference_data_guidance(
            system_id=system_id,
            revision_id=resolved_revision_id,
            token=normalized_token,
            discovery_result=discovery,
            context_result=context,
            semantic_policy=semantic_policy,
            limits={
                "candidate_limit": candidate_limit,
                "local_definition_limit": local_definition_limit,
                "literal_write_limit": literal_write_limit,
                "usage_limit": usage_limit,
                "gap_limit": gap_limit,
                "evidence_limit": evidence_limit,
            },
        )
        return ReferenceDataGuidanceResponse(**projected)


    def query_foreign_data_persistence(
        self,
        system_id: str,
        request: ForeignDataPersistenceQueryRequest,
    ) -> ReportingKnowledgeQueryResponse:
        revision = self._resolve_revision(system_id, request.revision_id)
        artifact = self._artifact_record(
            revision,
            model_kind="persistence-lineage",
            capability_prefix="workspace.fdp-paths",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            query = self.foreign_data_persistence_query_factory.get(config)
            result = query.call(
                request.query_kind,
                filters=request.filters,
                max_results=request.max_results,
            )
        except ForeignDataPersistenceKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "foreign_data_persistence_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_foreign_data_persistence_query", str(exc)) from exc
        return ReportingKnowledgeQueryResponse(
            system_id=system_id,
            revision_id=str(revision["revision_id"]),
            query=dict(result.get("query") or {}),
            items=[dict(item) for item in result.get("items") or ()],
            summary=dict(result.get("summary") or {}),
            evidence=[dict(item) for item in result.get("evidence") or ()],
            gaps=[dict(item) for item in result.get("gaps") or ()],
            pagination=dict(result.get("pagination") or {}) if result.get("pagination") is not None else None,
        )

    def get_foreign_data_persistence_guidance(
        self,
        system_id: str,
        *,
        revision_id: str | None,
        token: str,
        path_limit: int,
        case_limit: int,
        storage_summary_limit: int,
        evidence_limit: int,
    ) -> ForeignDataPersistenceGuidanceResponse:
        revision = self._resolve_revision(system_id, revision_id)
        resolved_revision_id = str(revision["revision_id"])
        artifact = self._artifact_record(
            revision,
            model_kind="persistence-lineage",
            capability_prefix="workspace.fdp-paths",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        normalized_token = str(token or "").strip()
        try:
            query = self.foreign_data_persistence_query_factory.get(config)
            # Internal read ceiling is intentionally much larger than the presentation
            # limits so KLC-owned path/case summaries remain exact for normal products.
            # If a product exceeds the ceiling, pagination/truncation remains visible.
            paths = query.call(
                "list_paths",
                filters={"token": normalized_token},
                max_results=10000,
            )
            cases = query.call(
                "list_mechanical_cases",
                filters={"token": normalized_token},
                max_results=10000,
            )
            policy_result = query.call(
                "get_landscape",
                filters={"token": normalized_token},
                max_results=1,
            )
        except ForeignDataPersistenceKnowledgeUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "foreign_data_persistence_unavailable", str(exc)) from exc
        except ValueError as exc:
            raise KnowledgeApiRuntimeError(422, "invalid_foreign_data_persistence_query", str(exc)) from exc

        policy_items = [item for item in policy_result.get("items") or () if isinstance(item, Mapping)]
        interpretation_policy = dict(policy_items[0].get("interpretation_policy") or {}) if policy_items else {}
        projected = project_foreign_data_persistence_guidance(
            system_id=system_id,
            revision_id=resolved_revision_id,
            token=normalized_token,
            paths_result=paths,
            cases_result=cases,
            interpretation_policy=interpretation_policy,
            limits={
                "path_limit": path_limit,
                "case_limit": case_limit,
                "storage_summary_limit": storage_summary_limit,
                "evidence_limit": evidence_limit,
            },
        )
        return ForeignDataPersistenceGuidanceResponse(**projected)

    def _value_flow_artifact_record(self, revision: dict[str, Any]) -> dict[str, Any]:
        artifacts = [raw for raw in revision.get("knowledge_artifacts") or () if isinstance(raw, dict)]
        capable = [
            raw for raw in artifacts
            if "workspace.attribute-path-resolver" in {str(value) for value in raw.get("capabilities") or ()}
        ]
        for source_materialization_id in ("cross-repository-value-flow", "repository-value-flow"):
            candidates = [
                raw for raw in capable
                if str(raw.get("source_materialization_id") or "") == source_materialization_id
            ]
            if not candidates:
                continue
            locations = {str((_product_artifact_dict_by_role(item, "database") or {}).get("sha256") or "") for item in candidates}
            if len(locations) > 1:
                raise KnowledgeApiRuntimeError(
                    409,
                    "knowledge_artifact_ambiguous",
                    "multiple value-flow artifacts satisfy the canonical source materialization",
                    details={"source_materialization_id": source_materialization_id, "artifact_ids": sorted(str(item.get("artifact_id") or "") for item in candidates)},
                )
            return candidates[0]
        raise KnowledgeApiRuntimeError(409, "knowledge_artifact_unavailable", "revision does not contain an attribute-path resolver artifact")

    def _published_manifest_path_for_query(
        self,
        manifest: PublishedArtifact | None,
    ) -> Path | None:
        if manifest is None:
            return None
        # The published manifest is part of the immutable KnowledgeProduct.
        # Querying must follow that exact artifact after CAS relocation rather
        # than re-discovering a producer-local sibling by filename.
        return self.validator.validate(manifest)

    def _knowledge_artifact_source(
        self,
        system_id: str,
        artifact: dict[str, Any],
    ) -> KnowledgeArtifactSource:
        database = _product_artifact_dict_by_role(artifact, "database")
        if not isinstance(database, dict):
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", "derived product database is unavailable")
        database_path = self.validator.validate_dict(database)
        manifest = _product_artifact_dict_by_role(artifact, "manifest")
        published_manifest = ProductPhysicalArtifact.model_validate(manifest) if isinstance(manifest, dict) else None
        manifest_path = self._published_manifest_path_for_query(published_manifest)
        return KnowledgeArtifactSource(
            system_id=system_id,
            database_path=database_path,
            manifest_path=manifest_path,
        )

    def _storage_query_service(self, system_id: str, revision: dict[str, Any]):
        artifact = self._artifact_record(
            revision,
            model_kind="observed-storage-usage",
            capability_prefix="common.observed-storage-usage",
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            return self.storage_query_factory.get(config)
        except ObservedStorageUsageUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "observed_storage_usage_unavailable", str(exc)) from exc

    def _query_service(self, system_id: str, revision: dict[str, Any]):
        artifact = self._artifact_record(revision, model_kind="effective-data-model")
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            return self.query_factory.get(config)
        except EffectiveDataModelUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "effective_data_model_unavailable", str(exc)) from exc

    def _knowledge_query_service(
        self,
        system_id: str,
        revision: dict[str, Any],
        *,
        model_kind: str | None = None,
        capability_prefix: str | None = None,
    ):
        artifact = self._artifact_record(
            revision,
            model_kind=model_kind,
            capability_prefix=capability_prefix,
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            return self.knowledge_query_factory.get(config)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc
        except Exception as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc

    def _sql_artifact_record(
        self,
        revision: dict[str, Any],
        *,
        required_capability: str,
    ) -> dict[str, Any]:
        """Select the canonical SQL query artifact for a revision.

        Workspace SQL composition is authoritative when present because it contains
        the union of repository SQL artifacts with preserved repo_id provenance. A
        repository SQL artifact is selected only when the revision has no workspace
        catalog. This is an explicit typed-model priority, not a legacy fallback.
        """
        model_priority = ("workspace-sql-catalog", "sql-observed-data-usage")
        artifacts = [raw for raw in revision.get("knowledge_artifacts") or () if isinstance(raw, dict)]
        capable = [
            raw
            for raw in artifacts
            if required_capability in {str(value) for value in raw.get("capabilities") or ()}
        ]
        for model_kind in model_priority:
            candidates = [
                raw for raw in capable if str(raw.get("model_kind") or "") == model_kind
            ]
            if not candidates:
                continue
            locations = {
                str((_product_artifact_dict_by_role(item, "database") or {}).get("sha256") or "") for item in candidates
            }
            if len(locations) > 1:
                raise KnowledgeApiRuntimeError(
                    409,
                    "knowledge_artifact_ambiguous",
                    "multiple knowledge artifacts of the canonical SQL model satisfy the requested capability",
                    details={
                        "required_capability": required_capability,
                        "model_kind": model_kind,
                        "artifact_ids": sorted(str(item.get("artifact_id") or "") for item in candidates),
                    },
                )
            return candidates[0]
        if capable:
            raise KnowledgeApiRuntimeError(
                409,
                "sql_knowledge_artifact_model_unsupported",
                "SQL capability is published only by unsupported knowledge artifact model kinds",
                details={
                    "required_capability": required_capability,
                    "model_kinds": sorted({str(item.get("model_kind") or "") for item in capable}),
                    "artifact_ids": sorted(str(item.get("artifact_id") or "") for item in capable),
                },
            )
        raise KnowledgeApiRuntimeError(
            409,
            "knowledge_artifact_unavailable",
            f"revision does not contain a knowledge artifact for {required_capability}",
        )

    def _sql_query_service(
        self,
        system_id: str,
        revision: dict[str, Any],
        *,
        required_capability: str,
    ):
        artifact = self._sql_artifact_record(
            revision,
            required_capability=required_capability,
        )
        config = self._knowledge_artifact_source(system_id, artifact)
        try:
            return self.knowledge_query_factory.get(config)
        except KnowledgeArtifactUnavailableError as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc
        except Exception as exc:
            raise KnowledgeApiRuntimeError(503, "knowledge_artifact_unavailable", str(exc)) from exc

    def _resolve_revision(self, system_id: str, revision_id: str | None) -> dict[str, Any]:
        self.get_system(system_id)
        row = self.store.get_revision(system_id, revision_id) if revision_id else self.store.active_revision(system_id)
        if row is None:
            code = "revision_not_found" if revision_id else "active_revision_not_found"
            raise KnowledgeApiRuntimeError(404, code, "requested system revision is unavailable")
        return row

    @staticmethod
    def _revision_id(
        system_id: str,
        request: RevisionCreateRequest,
        result_fingerprint: str,
    ) -> str:
        canonical_payload = {
            "system_id": system_id,
            "knowledge_execution_result": {
                "result_fingerprint": result_fingerprint,
                "sha256": request.execution_result.sha256,
                "schema_version": request.execution_result.schema_version,
            },
            "labels": sorted(set(request.labels)),
            "metadata": request.metadata,
        }
        if request.base_revision_id is not None:
            canonical_payload["base_revision_id"] = request.base_revision_id
        canonical = json.dumps(
            canonical_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"rev-{hashlib.sha256(canonical).hexdigest()[:24]}"

    @staticmethod
    def _system_summary(row: dict[str, Any]) -> SystemSummary:
        return SystemSummary(
            system_id=row["system_id"],
            display_name=row["display_name"],
            description=row["description"],
            active_revision_id=row["active_revision_id"],
            revision_count=row["revision_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision(row: dict[str, Any]) -> SystemRevision:
        return SystemRevision.model_validate(row)
