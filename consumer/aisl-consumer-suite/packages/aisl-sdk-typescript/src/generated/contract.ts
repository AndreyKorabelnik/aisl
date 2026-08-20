// AUTO-GENERATED from openapi/knowledge-api-v1.json. Do not edit by hand.
export const KNOWLEDGE_API_OPENAPI_SHA256 = "2e6d5238960b924e51773ef66c1e60353ed3289d9d69c6f68c36fe4d2b169526" as const;

export type JsonValue = unknown;

export type KnowledgeArtifactDetailResponse = { "artifact": PublishedKnowledgeArtifact; "revision_id": string; "schema_version"?: string; "system_id": string; };

export type KnowledgeArtifactListResponse = { "items": Array<PublishedKnowledgeArtifact>; "page": PageMeta; "revision_id": string; "schema_version"?: string; "system_id": string; };

export type KnowledgeExecutionSummary = { "completed_at": string; "knowledge_profile_id": string; "plan_fingerprint": string; "result_fingerprint": string; "runner_version": string; "schema_version"?: "knowledge_execution_result/v2"; "scope_id": string; "scope_kind": string; "semantic_policy"?: Record<string, JsonValue>; "started_at": string; "status"?: "completed"; };

export type PageMeta = { "limit"?: number; "offset"?: number; "total": number; };

export type ProductOriginKind = "observed" | "derived";

export type ProductPhysicalArtifact = { "byte_size"?: number | null; "filename"?: string | null; "media_type": string; "role": string; "schema_version"?: string | null; "sha256": string; "uri": string; };

export type PublishedArtifact = { "byte_size"?: number | null; "filename"?: string | null; "media_type": string; "schema_version"?: string | null; "sha256": string; "uri": string; };

export type PublishedKnowledgeArtifact = { "artifact_id": string; "capabilities"?: Array<string>; "content_fingerprint": string; "coverage"?: Record<string, JsonValue>; "diagnostics"?: Array<Record<string, JsonValue>>; "exact_dependency_product_ids"?: Array<string>; "model_kind": string; "origin_kind": ProductOriginKind; "physical_artifacts": Array<ProductPhysicalArtifact>; "producer_contract_ref": string; "producer_ref": string; "product_slot_id": string; "provenance"?: Record<string, JsonValue>; "schema_version": string; "source_materialization_id"?: string | null; };

export type RevisionCapabilitiesResponse = { "capabilities": Array<string>; "revision_id": string; "schema_version"?: string; "system_id": string; };

export type RevisionListResponse = { "items": Array<SystemRevision>; "page": PageMeta; "schema_version"?: string; "system_id": string; };

export type RevisionState = "active" | "superseded" | "inactive";

export type SystemListResponse = { "items": Array<SystemSummary>; "page": PageMeta; "schema_version"?: string; };

export type SystemRevision = { "base_revision_id"?: string | null; "capabilities"?: Array<string>; "created_at": string; "execution": KnowledgeExecutionSummary; "execution_result": PublishedArtifact; "knowledge_artifacts": Array<PublishedKnowledgeArtifact>; "labels"?: Array<string>; "metadata"?: Record<string, JsonValue>; "ordinal": number; "revision_id": string; "state": RevisionState; "system_id": string; };

export type SystemSummary = { "active_revision_id"?: string | null; "created_at": string; "description"?: string | null; "display_name": string; "revision_count"?: number; "system_id": string; "updated_at": string; };
