import assert from 'node:assert/strict';
import {AislClient} from '../dist/index.js';

const baseUrl = process.env.AISL_TEST_API_URL ?? 'http://127.0.0.1:18080';
const client = new AislClient(baseUrl);
const systems = await client.listSystems({search:'sdk-acceptance-rich'});
assert.ok(systems.some(s => s.system_id === 'sdk-acceptance-rich'));
const rev = await client.activeRevision('sdk-acceptance-rich');
assert.match(rev.revisionId, /^rev-/);
const products = await rev.listProducts();
assert.deepEqual(new Set(products.map(p => p.model_kind)), new Set(['code-declared-data-model','logical-storage-model-mapping','model-storage-semantics']));
const caps = new Set(await rev.getCapabilities());
assert.ok(caps.has('common.code-declared-data-model'));
assert.ok(caps.has('common.logical-storage-mapping'));
const found = await rev.searchDeclaredDataObjects({search:'Страна рождения', includeFields:true});
assert.equal(found.length, 1);
assert.equal(found[0].fqcn, 'com.acme.Individual');
const objectId = String(found[0].object_id);
const context = await rev.getDataModelObjectContext(objectId);
assert.equal(context.storage_context.status, 'available');
const rel = context.relationships.find(r => r.source_field === 'birthCountry');
assert.ok(rel);
assert.equal(rel.storage_semantics.status, 'ambiguous');
assert.equal(rel.storage_semantics.candidate_mappings.length, 2);
assert.equal(rel.physical_mapping.physical_join_confirmed, false);
console.log(JSON.stringify({
 status:'PASS',system_id:rev.systemId,revision_id:rev.revisionId,
 product_count:products.length,capability_count:caps.size,
 storage_status:rel.storage_semantics.status,
 candidate_mapping_count:rel.storage_semantics.candidate_mappings.length,
 physical_join_confirmed:rel.physical_mapping.physical_join_confirmed
},null,2));
const integration=await rev.integration('data-model/v1');
assert.equal(integration.raw.scope.revision_id,rev.revisionId);
assert.ok(integration.tools.some(t=>t.name==='get_data_model_object_context'));
const viaTool=await integration.executeTool('get_data_model_object_context',{object_id:objectId});
assert.equal(viaTool.result.storage_context.status,'available');
const viaRel=viaTool.result.relationships.find(r=>r.source_field==='birthCountry');
assert.equal(viaRel.storage_semantics.status,'ambiguous');
assert.equal(viaRel.physical_mapping.physical_join_confirmed,false);
console.log(JSON.stringify({integration_status:'PASS',profile_id:integration.profileId,tool:'get_data_model_object_context',revision_id:integration.revisionId},null,2));
