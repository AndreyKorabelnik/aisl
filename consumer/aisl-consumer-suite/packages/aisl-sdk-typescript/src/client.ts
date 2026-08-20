import type {
  SystemSummary, SystemRevision, PublishedKnowledgeArtifact, PageMeta,
  SystemListResponse, RevisionListResponse, RevisionCapabilitiesResponse,
  KnowledgeArtifactListResponse, KnowledgeArtifactDetailResponse,
} from './generated/contract.js';
import {AislApiError, AislContractError, AislTransportError} from './errors.js';
import {ConsumerIntegration} from './integration.js';

export type JsonObject = Record<string, unknown>;
export type FetchLike = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

function required(value: string, name: string): string {
  const v = String(value ?? '').trim();
  if (!v) throw new Error(`${name} must not be empty`);
  return v;
}
function seg(value: string, name: string): string { return encodeURIComponent(required(value, name)); }
function asObject(value: unknown, context: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AislContractError(`${context} must be a JSON object`);
  return value as JsonObject;
}

export interface AislClientOptions {
  headers?: Record<string, string>;
  timeoutMs?: number;
  fetch?: FetchLike;
}

export class PinnedRevision {
  constructor(public readonly client: AislClient, public readonly summary: SystemRevision) {}
  get systemId(): string { return this.summary.system_id; }
  get revisionId(): string { return this.summary.revision_id; }
  get capabilities(): readonly string[] { return this.summary.capabilities ?? []; }
  get products(): readonly PublishedKnowledgeArtifact[] { return this.summary.knowledge_artifacts ?? []; }

  refreshMetadata(): Promise<PinnedRevision> { return this.client.revision(this.systemId, this.revisionId); }

  async listProducts(options: {modelKind?: string; capability?: string; pageSize?: number; maxResults?: number} = {}): Promise<PublishedKnowledgeArtifact[]> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/knowledge-artifacts`;
    return this.client.collectPages<PublishedKnowledgeArtifact>(path, {
      revision_id: this.revisionId,
      ...(options.modelKind ? {model_kind: options.modelKind} : {}),
      ...(options.capability ? {capability: options.capability} : {}),
    }, options.pageSize ?? 100, options.maxResults ?? 10000);
  }

  async getProduct(artifactId: string): Promise<PublishedKnowledgeArtifact> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/knowledge-artifacts/${seg(artifactId,'artifact_id')}`;
    const body = await this.client.getJson<KnowledgeArtifactDetailResponse>(path, {revision_id: this.revisionId});
    return body.artifact;
  }

  async getCapabilities(): Promise<string[]> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/capabilities`;
    const body = await this.client.getJson<RevisionCapabilitiesResponse>(path, {revision_id: this.revisionId});
    return [...body.capabilities];
  }

  declaredDataModelSummary(params: Record<string, string> = {}): Promise<JsonObject> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/data-model/declared-summary`;
    return this.client.getJson<JsonObject>(path, {revision_id: this.revisionId, ...params});
  }

  searchDeclaredDataObjects(options: {search?: string; repoId?: string; typeAnnotations?: string; includeFields?: boolean; pageSize?: number; maxResults?: number} = {}): Promise<JsonObject[]> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/data-model/declared-objects`;
    return this.client.collectPages<JsonObject>(path, {
      revision_id: this.revisionId,
      include_fields: options.includeFields ?? false,
      ...(options.search ? {search: options.search} : {}),
      ...(options.repoId ? {repo_id: options.repoId} : {}),
      ...(options.typeAnnotations ? {type_annotations: options.typeAnnotations} : {}),
    }, options.pageSize ?? 100, options.maxResults ?? 1000);
  }

  getDeclaredDataObject(objectId: string): Promise<JsonObject> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/data-model/declared-objects/${seg(objectId,'object_id')}`;
    return this.client.getJson<JsonObject>(path, {revision_id: this.revisionId});
  }

  integration(profileId: string): Promise<ConsumerIntegration> { return ConsumerIntegration.load(this.client, this.systemId, this.revisionId, profileId); }

  getDataModelObjectContext(objectId: string): Promise<JsonObject> {
    const path = `/api/knowledge/v1/systems/${seg(this.systemId,'system_id')}/data-model/object-context/${seg(objectId,'object_id')}`;
    return this.client.getJson<JsonObject>(path, {revision_id: this.revisionId});
  }
}

export class AislClient {
  public readonly baseUrl: string;
  private readonly headers: Record<string,string>;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;

  constructor(baseUrl: string, options: AislClientOptions = {}) {
    this.baseUrl = required(baseUrl,'base_url').replace(/\/+$/, '');
    this.headers = {...(options.headers ?? {})};
    this.timeoutMs = options.timeoutMs ?? 30000;
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(method: string, path: string, params?: Record<string, unknown>, body?: unknown): Promise<T> {
    const url = new URL(this.baseUrl + path);
    for (const [k,v] of Object.entries(params ?? {})) if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      let response: Response;
      try {
        response = await this.fetchImpl(url, {
          method,
          headers: {'accept':'application/json', ...(body !== undefined ? {'content-type':'application/json'} : {}), ...this.headers},
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });
      } catch (err) {
        throw new AislTransportError(`Knowledge API request failed: ${String(err)}`);
      }
      let payload: unknown;
      try { payload = await response.json(); } catch { throw new AislContractError(`Knowledge API returned non-JSON response for ${method} ${path}`); }
      if (!response.ok) throw new AislApiError(response.status, method, path, payload);
      return payload as T;
    } finally { clearTimeout(timer); }
  }

  getJson<T = JsonObject>(path: string, params?: Record<string, unknown>): Promise<T> { return this.request<T>('GET', path, params); }
  postJson<T = JsonObject>(path: string, body: unknown, params?: Record<string, unknown>): Promise<T> { return this.request<T>('POST', path, params, body); }

  async collectPages<T = JsonObject>(path: string, params: Record<string, unknown> = {}, pageSize = 100, maxResults = 10000): Promise<T[]> {
    if (pageSize < 1 || pageSize > 500) throw new Error('pageSize must be between 1 and 500');
    if (maxResults < 0) throw new Error('maxResults must be >= 0');
    const out: T[] = []; let offset = 0;
    while (out.length < maxResults) {
      const limit = Math.min(pageSize, maxResults - out.length);
      const body = await this.getJson<{items: T[]; page: PageMeta}>(path, {...params, offset, limit});
      if (!Array.isArray(body.items)) throw new AislContractError(`Knowledge API paged response must contain items array for GET ${path}`);
      out.push(...body.items.slice(0, maxResults - out.length));
      const consumed = body.items.length; offset += consumed;
      if (!consumed || offset >= Number(body.page?.total ?? 0)) break;
    }
    return out;
  }

  listSystems(options: {search?: string; pageSize?: number; maxResults?: number} = {}): Promise<SystemSummary[]> {
    return this.collectPages<SystemSummary>('/api/knowledge/v1/systems', options.search ? {search: options.search} : {}, options.pageSize ?? 100, options.maxResults ?? 10000);
  }
  getSystem(systemId: string): Promise<SystemSummary> { return this.getJson<SystemSummary>(`/api/knowledge/v1/systems/${seg(systemId,'system_id')}`); }
  listRevisions(systemId: string, pageSize = 100, maxResults = 10000): Promise<SystemRevision[]> {
    return this.collectPages<SystemRevision>(`/api/knowledge/v1/systems/${seg(systemId,'system_id')}/revisions`, {}, pageSize, maxResults);
  }
  async revision(systemId: string, revisionId: string): Promise<PinnedRevision> {
    const sid = required(systemId,'system_id'), rid = required(revisionId,'revision_id');
    const body = await this.getJson<SystemRevision>(`/api/knowledge/v1/systems/${seg(sid,'system_id')}/revisions/${seg(rid,'revision_id')}`);
    if (body.system_id !== sid || body.revision_id !== rid) throw new AislContractError(`Knowledge API revision identity mismatch: requested ${sid}/${rid}, received ${body.system_id}/${body.revision_id}`);
    return new PinnedRevision(this, body);
  }
  async activeRevision(systemId: string): Promise<PinnedRevision> {
    const system = await this.getSystem(systemId);
    if (!system.active_revision_id) throw new AislContractError(`system ${system.system_id} has no active Knowledge API revision`);
    return this.revision(system.system_id, system.active_revision_id);
  }
}
