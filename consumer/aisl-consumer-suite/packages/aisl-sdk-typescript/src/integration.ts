import {AislContractError} from './errors.js';
import type {JsonObject} from './client.js';

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

function object(value: unknown, name: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AislContractError(`${name} must be an object`);
  return value as JsonObject;
}
function required(value: unknown, name: string): string {
  const v=String(value ?? '').trim(); if(!v) throw new AislContractError(`${name} must not be empty`); return v;
}
function transform(value: unknown, kind: string): unknown {
  if (!kind || kind==='identity' || kind==='url_segment') return value;
  if (kind==='csv') return Array.isArray(value) ? value.map(String).join(',') : String(value);
  if (kind==='bool') return value ? 'true' : 'false';
  if (kind==='bounded_int' || kind==='integer') return String(Number.parseInt(String(value),10));
  throw new AislContractError(`unsupported api-binding transform: ${kind}`);
}

export class ConsumerIntegration {
  constructor(
    public readonly client: IntegrationHttpClient,
    public readonly systemId: string,
    public readonly revisionId: string,
    public readonly profileId: string,
    public readonly fingerprint: string,
    public readonly raw: JsonObject,
  ) {}

  static async load(client: IntegrationHttpClient, systemId: string, revisionId: string, profileId: string): Promise<ConsumerIntegration> {
    const sid=required(systemId,'system_id'), rid=required(revisionId,'revision_id'), pid=required(profileId,'profile_id');
    const payload=await client.getJson<JsonObject>(`/api/knowledge/v1/systems/${encodeURIComponent(sid)}/llm-integration-profile`,{revision_id:rid,profile_id:pid});
    const scope=object(payload.scope,'Integration Profile scope');
    if(scope.system_id!==sid || scope.revision_id!==rid || scope.revision_binding!=='pinned') throw new AislContractError('Integration Profile scope does not match the pinned revision');
    const integration=object(payload.integration_profile,'integration_profile');
    const actual=required(integration.profile_id,'integration_profile.profile_id');
    if(actual!==pid) throw new AislContractError(`Integration Profile id mismatch: requested ${pid}, got ${actual}`);
    return new ConsumerIntegration(client,sid,rid,pid,String(integration.fingerprint ?? ''),structuredClone(payload));
  }

  get tools(): JsonObject[] {
    if(!Array.isArray(this.raw.tools)) throw new AislContractError('Integration Profile tools must be an array');
    return this.raw.tools.map((v,i)=>structuredClone(object(v,`tool[${i}]`)));
  }

  tool(name: string): JsonObject {
    const n=required(name,'tool name'); const found=this.tools.find(v=>v.name===n);
    if(!found) throw new AislContractError(`tool ${n} is not allowed by the pinned Integration Profile`);
    return found;
  }

  async executeTool(name: string, args: JsonObject): Promise<ToolExecutionResult> {
    const tool=this.tool(name), binding=object(tool.api_binding ?? {},'api_binding');
    if(binding.binding_kind!=='knowledge_api_http') throw new AislContractError(`unsupported binding_kind for ${name}: ${String(binding.binding_kind)}`);
    const method=String(binding.method ?? 'GET').toUpperCase();
    let path=required(binding.path_template,'path_template').replace('{system_id}',encodeURIComponent(this.systemId));
    const query:Record<string,unknown>={...object(binding.fixed_query ?? {},'fixed_query')};
    const body:Record<string,unknown>={...object(binding.fixed_body ?? {},'fixed_body')};
    const rev=object(binding.revision_binding ?? {},'revision_binding');
    const revName=String(rev.name ?? 'revision_id');
    if(rev.location==='query') query[revName]=this.revisionId; else if(rev.location==='body') body[revName]=this.revisionId; else throw new AislContractError(`unsupported revision binding location: ${String(rev.location)}`);
    const bindings=object(binding.arguments ?? {},'api_binding.arguments');
    for(const [argName,raw] of Object.entries(bindings)) {
      if(!(argName in args) || args[argName]===null || args[argName]===undefined) continue;
      const b=object(raw,`binding for ${argName}`), apiName=String(b.name ?? argName), value=transform(args[argName],String(b.transform ?? 'identity'));
      if(b.location==='path') path=path.replace(`{${apiName}}`,encodeURIComponent(String(value)));
      else if(b.location==='query') query[apiName]=value;
      else if(b.location==='body') body[apiName]=value;
      else throw new AislContractError(`unsupported argument location for ${argName}: ${String(b.location)}`);
    }
    if(path.includes('{') || path.includes('}')) throw new AislContractError(`tool ${name} is missing a required path argument: ${path}`);
    const started=performance.now();
    let result:JsonObject;
    if(method==='GET') result=await this.client.getJson<JsonObject>(path,query);
    else if(method==='POST') result=await this.client.postJson<JsonObject>(path,body,query);
    else throw new AislContractError(`unsupported HTTP method for ${name}: ${method}`);
    return {
      toolName:name, arguments:structuredClone(args), operationId:binding.operation_id ? String(binding.operation_id) : undefined,
      expectedSchemaVersions:Array.isArray(binding.expected_schema_versions)?binding.expected_schema_versions.map(String):[],
      durationMs:Math.max(0,Math.round(performance.now()-started)), result:structuredClone(result),
    };
  }
}
