import http from 'node:http';
const host=process.env.HOST||'127.0.0.1'; const port=Number(process.env.PORT||18480);
const systemId=process.env.SYSTEM_ID||'sdk-acceptance-rich'; const revisionId=process.env.REVISION_ID||'rev-c7a2eb14abb63c48ad4bc8b4';
let repos=[{repository_id:'repo-a',name:'Repository A',source_kind:'local',location:'/tmp/repo-a',status:'available'}];
let jobs=[];
const json=(res,status,body)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(body));};
async function body(req){const chunks=[];for await(const c of req)chunks.push(c);return chunks.length?JSON.parse(Buffer.concat(chunks).toString('utf8')):{};}
const scenario={scenario_id:'build-data-model-v1',name:'Модель данных из кода',knowledge_profile_id:'data-model-v1',source_mode:'repositories',version:'v1',description:'Build logical model',parameters:[]};
const server=http.createServer(async(req,res)=>{const u=new URL(req.url,'http://x'); const p=u.pathname;
 if(req.method==='GET'&&p==='/api/v1/version')return json(res,200,{schema_version:'generic_api/v1',version:'1.2.0a32'});
 if(req.method==='GET'&&p==='/api/v1/capabilities')return json(res,200,{schema_version:'generic_api/v1',capabilities:['jobs','repositories','scenarios']});
 if(req.method==='GET'&&p==='/api/v1/scenarios')return json(res,200,{schema_version:'generic_api/v1',items:[scenario],page:{offset:0,limit:500,total:1}});
 if(req.method==='GET'&&p==='/api/v1/repositories')return json(res,200,{schema_version:'generic_api/v1',items:repos,page:{offset:0,limit:500,total:repos.length}});
 if(req.method==='POST'&&p==='/api/v1/repositories/discover'){const b=await body(req);for(const root of b.roots||[]){const id='repo-'+(repos.length+1);repos.push({repository_id:id,name:id,source_kind:'local',location:root,status:'available'});}return json(res,200,{schema_version:'generic_api/v1',repositories:repos,discovered_count:repos.length,warnings:[]});}
 if(req.method==='POST'&&p==='/api/v1/jobs/preview'){const b=await body(req);return json(res,200,{schema_version:'generic_api/v1',kind:'knowledge_execution',scenario_id:b.scenario_id,knowledge_profile_id:'data-model-v1',target:b.target,parameters:b.parameters||{},commands:[{stage:'runner',argv:['static-analysis-runner','knowledge-run']} ]});}
 if(req.method==='POST'&&p==='/api/v1/jobs'){const b=await body(req);const job={schema_version:'generic_api/v1',job_id:'job-ui-001',status:'succeeded',kind:'knowledge_execution',scenario_id:b.scenario_id,display_name:b.display_name||null,target:b.target,parameters:b.parameters||{},output:b.output||{replace:false},progress:{message:'published'},created_at:new Date().toISOString(),knowledge_ids:['code-declared-data-model'],source_snapshots:[],reuse:{policy:b.reuse_policy||'reuse_if_unchanged',producer_nodes:[]},stages:[],artifact_count:1,event_cursor:1,publication:{system_id:systemId,revision_id:revisionId,knowledge_api_url:'http://127.0.0.1:18080'}};jobs=[job];return json(res,202,job);}
 if(req.method==='GET'&&p==='/api/v1/jobs')return json(res,200,{schema_version:'generic_api/v1',items:jobs,page:{offset:0,limit:50,total:jobs.length}});
 if(req.method==='GET'&&p==='/api/v1/jobs/job-ui-001')return jobs.length?json(res,200,jobs[0]):json(res,404,{code:'resource_not_found'});
 if(req.method==='GET'&&p==='/api/v1/jobs/job-ui-001/logs')return json(res,200,{schema_version:'generic_api/v1',job_id:'job-ui-001',entries:[],next_cursor:null,complete:true});
 return json(res,404,{code:'resource_not_found',path:p});
});
server.listen(port,host,()=>console.log(`mock KCP http://${host}:${port}`));
