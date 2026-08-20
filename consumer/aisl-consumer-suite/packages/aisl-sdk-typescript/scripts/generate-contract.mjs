import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const openapiPath = path.join(root, 'openapi', 'knowledge-api-v1.json');
const expectedSha = fs.readFileSync(path.join(root, 'openapi', 'knowledge-api-v1.sha256'), 'utf8').trim();
const bytes = fs.readFileSync(openapiPath);
const actualSha = crypto.createHash('sha256').update(bytes).digest('hex');
if (actualSha !== expectedSha) throw new Error(`OpenAPI SHA mismatch: ${actualSha} != ${expectedSha}`);
const doc = JSON.parse(bytes.toString('utf8'));
const schemas = doc.components?.schemas ?? {};
const roots = [
  'PageMeta', 'SystemSummary', 'SystemRevision', 'PublishedKnowledgeArtifact',
  'SystemListResponse', 'RevisionListResponse', 'RevisionCapabilitiesResponse',
  'KnowledgeArtifactListResponse', 'KnowledgeArtifactDetailResponse'
];
const needed = new Set();
function collect(schema) {
  if (!schema || typeof schema !== 'object') return;
  if (schema.$ref) {
    const name = schema.$ref.split('/').at(-1);
    if (!needed.has(name)) { needed.add(name); collect(schemas[name]); }
  }
  for (const value of Object.values(schema)) {
    if (Array.isArray(value)) value.forEach(collect); else collect(value);
  }
}
for (const name of roots) { needed.add(name); collect(schemas[name]); }

function refName(ref) { return ref.split('/').at(-1); }
function tsType(schema) {
  if (!schema || typeof schema !== 'object') return 'unknown';
  if (schema.$ref) return refName(schema.$ref);
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (Array.isArray(schema.enum)) return schema.enum.map(v => JSON.stringify(v)).join(' | ') || 'never';
  if (Array.isArray(schema.anyOf)) return schema.anyOf.map(tsType).join(' | ');
  if (Array.isArray(schema.oneOf)) return schema.oneOf.map(tsType).join(' | ');
  if (schema.type === 'array') return `Array<${tsType(schema.items)}>`;
  if (schema.type === 'string') return 'string';
  if (schema.type === 'integer' || schema.type === 'number') return 'number';
  if (schema.type === 'boolean') return 'boolean';
  if (schema.type === 'null') return 'null';
  if (schema.type === 'object' || schema.properties || schema.additionalProperties) {
    if (!schema.properties && schema.additionalProperties) {
      return `Record<string, ${schema.additionalProperties === true ? 'unknown' : tsType(schema.additionalProperties)}>`;
    }
    const required = new Set(schema.required ?? []);
    const fields = Object.entries(schema.properties ?? {}).map(([name, value]) => {
      const optional = required.has(name) ? '' : '?';
      return `${JSON.stringify(name)}${optional}: ${tsType(value)};`;
    });
    if (schema.additionalProperties && schema.additionalProperties !== false) {
      fields.push(`[key: string]: ${schema.additionalProperties === true ? 'unknown' : tsType(schema.additionalProperties)};`);
    }
    return `{ ${fields.join(' ')} }`;
  }
  return 'unknown';
}

const names = [...needed].sort();
const lines = [
  '// AUTO-GENERATED from openapi/knowledge-api-v1.json. Do not edit by hand.',
  `export const KNOWLEDGE_API_OPENAPI_SHA256 = ${JSON.stringify(actualSha)} as const;`,
  ''
];
for (const name of names) lines.push(`export type ${name} = ${tsType(schemas[name])};`, '');
fs.writeFileSync(path.join(root, 'src', 'generated', 'contract.ts'), lines.join('\n'));
console.log(`generated ${names.length} schema types from OpenAPI ${actualSha}`);
