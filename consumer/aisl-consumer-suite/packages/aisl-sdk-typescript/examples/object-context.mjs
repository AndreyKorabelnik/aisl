import {AislClient} from '../dist/index.js';
const [apiUrl, systemId, objectId, revisionId] = process.argv.slice(2);
if (!apiUrl || !systemId || !objectId) throw new Error('usage: node examples/object-context.mjs <api-url> <system-id> <object-id> [revision-id]');
const client = new AislClient(apiUrl);
const revision = revisionId ? await client.revision(systemId, revisionId) : await client.activeRevision(systemId);
console.log(JSON.stringify(await revision.getDataModelObjectContext(objectId), null, 2));
