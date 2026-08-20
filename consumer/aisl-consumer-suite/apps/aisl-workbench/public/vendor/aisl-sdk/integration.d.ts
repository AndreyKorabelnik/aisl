import type { JsonObject } from './client.js';
export interface IntegrationHttpClient {
    getJson<T = JsonObject>(path: string, params?: Record<string, unknown>): Promise<T>;
    postJson<T = JsonObject>(path: string, body: unknown, params?: Record<string, unknown>): Promise<T>;
}
export interface ToolExecutionResult {
    toolName: string;
    arguments: JsonObject;
    operationId?: string;
    expectedSchemaVersions: string[];
    durationMs: number;
    result: JsonObject;
}
export declare class ConsumerIntegration {
    readonly client: IntegrationHttpClient;
    readonly systemId: string;
    readonly revisionId: string;
    readonly profileId: string;
    readonly fingerprint: string;
    readonly raw: JsonObject;
    constructor(client: IntegrationHttpClient, systemId: string, revisionId: string, profileId: string, fingerprint: string, raw: JsonObject);
    static load(client: IntegrationHttpClient, systemId: string, revisionId: string, profileId: string): Promise<ConsumerIntegration>;
    get tools(): JsonObject[];
    tool(name: string): JsonObject;
    executeTool(name: string, args: JsonObject): Promise<ToolExecutionResult>;
}
