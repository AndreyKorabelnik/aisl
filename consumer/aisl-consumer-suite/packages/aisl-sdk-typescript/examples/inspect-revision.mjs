import {AislClient} from '../dist/index.js';
const [apiUrl, systemId, revisionId] = process.argv.slice(2);
if (!apiUrl || !systemId) throw new Error('usage: node examples/inspect-revision.mjs <api-url> <system-id> [revision-id]');
const client = new AislClient(apiUrl);
const revision = revisionId ? await client.revision(systemId, revisionId) : await client.activeRevision(systemId);
console.log(JSON.stringify({system_id:revision.systemId, revision_id:revision.revisionId, capabilities:await revision.getCapabilities(), products:await revision.listProducts()}, null, 2));
