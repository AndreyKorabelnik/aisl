import {AislClient} from '../dist/index.js';
const apiUrl = process.argv[2];
if (!apiUrl) throw new Error('usage: node examples/list-systems.mjs <api-url>');
const client = new AislClient(apiUrl);
for (const system of await client.listSystems()) console.log(system.system_id, system.active_revision_id);
