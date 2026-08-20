import type { SystemSummary, SystemRevision, PublishedKnowledgeArtifact } from './generated/contract.js';
import { ConsumerIntegration } from './integration.js';
export type JsonObject = Record<string, unknown>;
export type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;
export interface AislClientOptions {
    headers?: Record<string, string>;
    timeoutMs?: number;
    fetch?: FetchLike;
}
export declare class PinnedRevision {
    readonly client: AislClient;
    readonly summary: SystemRevision;
    constructor(client: AislClient, summary: SystemRevision);
    get systemId(): string;
    get revisionId(): string;
    get capabilities(): readonly string[];
    get products(): readonly PublishedKnowledgeArtifact[];
    refreshMetadata(): Promise<PinnedRevision>;
    listProducts(options?: {
        modelKind?: string;
        capability?: string;
        pageSize?: number;
        maxResults?: number;
    }): Promise<PublishedKnowledgeArtifact[]>;
    getProduct(artifactId: string): Promise<PublishedKnowledgeArtifact>;
    getCapabilities(): Promise<string[]>;
    declaredDataModelSummary(params?: Record<string, string>): Promise<JsonObject>;
    searchDeclaredDataObjects(options?: {
        search?: string;
        repoId?: string;
        typeAnnotations?: string;
        includeFields?: boolean;
        pageSize?: number;
        maxResults?: number;
    }): Promise<JsonObject[]>;
    getDeclaredDataObject(objectId: string): Promise<JsonObject>;
    integration(profileId: string): Promise<ConsumerIntegration>;
    getDataModelObjectContext(objectId: string): Promise<JsonObject>;
}
export declare class AislClient {
    readonly baseUrl: string;
    private readonly headers;
    private readonly timeoutMs;
    private readonly fetchImpl;
    constructor(baseUrl: string, options?: AislClientOptions);
    private request;
    getJson<T = JsonObject>(path: string, params?: Record<string, unknown>): Promise<T>;
    postJson<T = JsonObject>(path: string, body: unknown, params?: Record<string, unknown>): Promise<T>;
    collectPages<T = JsonObject>(path: string, params?: Record<string, unknown>, pageSize?: number, maxResults?: number): Promise<T[]>;
    listSystems(options?: {
        search?: string;
        pageSize?: number;
        maxResults?: number;
    }): Promise<SystemSummary[]>;
    getSystem(systemId: string): Promise<SystemSummary>;
    listRevisions(systemId: string, pageSize?: number, maxResults?: number): Promise<SystemRevision[]>;
    revision(systemId: string, revisionId: string): Promise<PinnedRevision>;
    activeRevision(systemId: string): Promise<PinnedRevision>;
}
