import { AislApiError, AislContractError, AislTransportError } from './errors.js';
function required(value, name) {
    const v = String(value ?? '').trim();
    if (!v)
        throw new Error(`${name} must not be empty`);
    return v;
}
function seg(value, name) { return encodeURIComponent(required(value, name)); }
function asObject(value, context) {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        throw new AislContractError(`${context} must be a JSON object`);
    return value;
}
export class PinnedRevision {
    client;
    summary;
    constructor(client, summary) {
        this.client = client;
        this.summary = summary;
    }
    get systemId() { return this.summary.system_id; }
    get revisionId() { return this.summary.revision_id; }
    get capabilities() { return this.summary.capabilities ?? []; }
    get products() { return this.summary.knowledge_artifacts ?? []; }
    refreshMetadata() { return this.client.revision(this.systemId, this.revisionId); }
    async listProducts(options = {}) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/knowledge-artifacts`;
        return this.client.collectPages(path, {
            revision_id: this.revisionId,
            ...(options.modelKind ? { model_kind: options.modelKind } : {}),
            ...(options.capability ? { capability: options.capability } : {}),
        }, options.pageSize ?? 100, options.maxResults ?? 10000);
    }
    async getProduct(artifactId) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/knowledge-artifacts/${seg(artifactId, 'artifact_id')}`;
        const body = await this.client.getJson(path, { revision_id: this.revisionId });
        return body.artifact;
    }
    async getCapabilities() {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/capabilities`;
        const body = await this.client.getJson(path, { revision_id: this.revisionId });
        return [...body.capabilities];
    }
    declaredDataModelSummary(params = {}) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/data-model/declared-summary`;
        return this.client.getJson(path, { revision_id: this.revisionId, ...params });
    }
    searchDeclaredDataObjects(options = {}) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/data-model/declared-objects`;
        return this.client.collectPages(path, {
            revision_id: this.revisionId,
            include_fields: options.includeFields ?? false,
            ...(options.search ? { search: options.search } : {}),
            ...(options.repoId ? { repo_id: options.repoId } : {}),
            ...(options.typeAnnotations ? { type_annotations: options.typeAnnotations } : {}),
        }, options.pageSize ?? 100, options.maxResults ?? 1000);
    }
    getDeclaredDataObject(objectId) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/data-model/declared-objects/${seg(objectId, 'object_id')}`;
        return this.client.getJson(path, { revision_id: this.revisionId });
    }
    getDataModelObjectContext(objectId) {
        const path = `/api/knowledge/v1/systems/${seg(this.systemId, 'system_id')}/data-model/object-context/${seg(objectId, 'object_id')}`;
        return this.client.getJson(path, { revision_id: this.revisionId });
    }
}
export class AislClient {
    baseUrl;
    headers;
    timeoutMs;
    fetchImpl;
    constructor(baseUrl, options = {}) {
        this.baseUrl = required(baseUrl, 'base_url').replace(/\/+$/, '');
        this.headers = { ...(options.headers ?? {}) };
        this.timeoutMs = options.timeoutMs ?? 30000;
        this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
    }
    async request(method, path, params, body) {
        const url = new URL(this.baseUrl + path);
        for (const [k, v] of Object.entries(params ?? {}))
            if (v !== undefined && v !== null)
                url.searchParams.set(k, String(v));
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            let response;
            try {
                response = await this.fetchImpl(url, {
                    method,
                    headers: { 'accept': 'application/json', ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...this.headers },
                    body: body === undefined ? undefined : JSON.stringify(body),
                    signal: controller.signal,
                });
            }
            catch (err) {
                throw new AislTransportError(`Knowledge API request failed: ${String(err)}`);
            }
            let payload;
            try {
                payload = await response.json();
            }
            catch {
                throw new AislContractError(`Knowledge API returned non-JSON response for ${method} ${path}`);
            }
            if (!response.ok)
                throw new AislApiError(response.status, method, path, payload);
            return payload;
        }
        finally {
            clearTimeout(timer);
        }
    }
    getJson(path, params) { return this.request('GET', path, params); }
    postJson(path, body, params) { return this.request('POST', path, params, body); }
    async collectPages(path, params = {}, pageSize = 100, maxResults = 10000) {
        if (pageSize < 1 || pageSize > 500)
            throw new Error('pageSize must be between 1 and 500');
        if (maxResults < 0)
            throw new Error('maxResults must be >= 0');
        const out = [];
        let offset = 0;
        while (out.length < maxResults) {
            const limit = Math.min(pageSize, maxResults - out.length);
            const body = await this.getJson(path, { ...params, offset, limit });
            if (!Array.isArray(body.items))
                throw new AislContractError(`Knowledge API paged response must contain items array for GET ${path}`);
            out.push(...body.items.slice(0, maxResults - out.length));
            const consumed = body.items.length;
            offset += consumed;
            if (!consumed || offset >= Number(body.page?.total ?? 0))
                break;
        }
        return out;
    }
    listSystems(options = {}) {
        return this.collectPages('/api/knowledge/v1/systems', options.search ? { search: options.search } : {}, options.pageSize ?? 100, options.maxResults ?? 10000);
    }
    getSystem(systemId) { return this.getJson(`/api/knowledge/v1/systems/${seg(systemId, 'system_id')}`); }
    listRevisions(systemId, pageSize = 100, maxResults = 10000) {
        return this.collectPages(`/api/knowledge/v1/systems/${seg(systemId, 'system_id')}/revisions`, {}, pageSize, maxResults);
    }
    async revision(systemId, revisionId) {
        const sid = required(systemId, 'system_id'), rid = required(revisionId, 'revision_id');
        const body = await this.getJson(`/api/knowledge/v1/systems/${seg(sid, 'system_id')}/revisions/${seg(rid, 'revision_id')}`);
        if (body.system_id !== sid || body.revision_id !== rid)
            throw new AislContractError(`Knowledge API revision identity mismatch: requested ${sid}/${rid}, received ${body.system_id}/${body.revision_id}`);
        return new PinnedRevision(this, body);
    }
    async activeRevision(systemId) {
        const system = await this.getSystem(systemId);
        if (!system.active_revision_id)
            throw new AislContractError(`system ${system.system_id} has no active Knowledge API revision`);
        return this.revision(system.system_id, system.active_revision_id);
    }
}
