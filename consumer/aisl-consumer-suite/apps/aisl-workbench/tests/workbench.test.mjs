import assert from 'node:assert/strict';
import {AislClient} from '../public/vendor/aisl-sdk/index.js';

const base=process.env.WORKBENCH_URL || 'http://127.0.0.1:18184';
const systemId='sdk-acceptance-rich';
const revisionId='rev-c7a2eb14abb63c48ad4bc8b4';

const root=await fetch(base+'/'); assert.equal(root.status,200); const html=await root.text(); assert.match(html,/AISL Platform/); assert.match(html,/data-tab="build"/); assert.match(html,/Build → KCP/);
const app=await fetch(base+'/app.js'); assert.equal(app.status,200); const appText=await app.text(); assert.match(appText,/\/api\/kcp\/v1\/jobs/); assert.match(appText,/source_mode/);
const health=await fetch(base+'/healthz'); assert.equal(health.status,200); const h=await health.json(); assert.ok(h.kcp);

const scenarios=await fetch(base+'/api/kcp/v1/scenarios?limit=500'); assert.equal(scenarios.status,200); const sc=await scenarios.json(); assert.equal(sc.items[0].scenario_id,'build-data-model-v1');
const repositories=await fetch(base+'/api/kcp/v1/repositories?limit=500'); assert.equal(repositories.status,200); const rp=await repositories.json(); assert.equal(rp.items[0].repository_id,'repo-a');
const discovered=await fetch(base+'/api/kcp/v1/repositories/discover',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({roots:['/tmp/repo-b'],refresh:true})}); assert.equal(discovered.status,200); assert.equal((await discovered.json()).discovered_count,2);
const payload={kind:'knowledge_execution',target:{system_id:systemId,repository_ids:['repo-a']},scenario_id:'build-data-model-v1',parameters:{},output:{replace:false},reuse_policy:'reuse_if_unchanged'};
const preview=await fetch(base+'/api/kcp/v1/jobs/preview',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); assert.equal(preview.status,200); assert.equal((await preview.json()).scenario_id,'build-data-model-v1');
const created=await fetch(base+'/api/kcp/v1/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)}); assert.equal(created.status,202); const job=await created.json(); assert.equal(job.status,'succeeded'); assert.equal(job.publication.system_id,systemId); assert.equal(job.publication.revision_id,revisionId);
const fetched=await fetch(base+'/api/kcp/v1/jobs/job-ui-001'); assert.equal(fetched.status,200); assert.equal((await fetched.json()).publication.revision_id,revisionId);

const client=new AislClient(base); const revision=await client.revision(job.publication.system_id,job.publication.revision_id); const products=await revision.listProducts(); assert.equal(products.length,3); const context=await revision.getDataModelObjectContext('t-ind'); const relation=context.relationships[0]; assert.equal(relation.storage_semantics.status,'ambiguous'); assert.equal(relation.storage_semantics.candidate_mappings.length,2); assert.equal(relation.physical_mapping.physical_join_confirmed,false);

const deniedKnowledge=await fetch(base+`/api/knowledge/v1/systems/${systemId}/revisions/${revisionId}/activate`,{method:'POST'}); assert.equal(deniedKnowledge.status,405);
const deniedKcp=await fetch(base+'/api/kcp/v1/configuration',{method:'PUT',headers:{'content-type':'application/json'},body:'{}'}); assert.equal(deniedKcp.status,405);

console.log(JSON.stringify({status:'PASS',build_proxy:true,scenario:sc.items[0].scenario_id,repositories_after_discovery:2,job_id:job.job_id,publication:job.publication,pinned_products:products.length,storage_status:relation.storage_semantics.status,candidate_mappings:relation.storage_semantics.candidate_mappings.length,physical_join_confirmed:relation.physical_mapping.physical_join_confirmed,knowledge_write_status:deniedKnowledge.status,kcp_unneeded_write_status:deniedKcp.status},null,2));
