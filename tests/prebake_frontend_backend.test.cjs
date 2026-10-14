// Executes the real frontend module against real Python state/attempt functions over JSON pipes.
// DOM and queue transport are fixtures. This is dynamic CPU integration, not browser/GPU E2E acceptance.
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const assert=require('node:assert/strict');
const test=require('node:test');
test('six frontend binds, plans, submits once, recovers and retains a submitted snapshot while drafts change',async()=>{
 const python=process.env.H3_TEST_PYTHON,host=process.env.H3_TEST_HOST;
 assert.ok(python&&host,'Set H3_TEST_PYTHON and H3_TEST_HOST to a CPU-capable interpreter and reconstructed host');
 const child=spawn(python,['-u','-B',join(__dirname,'test_prebake_runtime_contract.py'),'--host',host,'--rpc'],{stdio:['pipe','pipe','pipe'],env:{...process.env,CUDA_VISIBLE_DEVICES:'-1'}});
 const lines=createInterface({input:child.stdout});let serial=0;const pending=new Map();let stderr='';child.stderr.on('data',x=>stderr+=x);
 let readyResolve;const ready=new Promise(r=>readyResolve=r);
 lines.on('line',line=>{const x=JSON.parse(line);if(x.ready)return readyResolve();const item=pending.get(x.id);if(item){pending.delete(x.id);clearTimeout(item.timer);x.ok?item.resolve(x.result):item.reject(Error(x.error));}});
 function rpc(cmd,payload={}){return new Promise((resolve,reject)=>{const id=++serial;const timer=setTimeout(()=>reject(Error('CPU RPC timeout: '+cmd)),10000);pending.set(id,{resolve,reject,timer});child.stdin.write(JSON.stringify({id,cmd,payload})+'\n');});}
 try{
  let readyTimer;await Promise.race([ready,new Promise((_,reject)=>{readyTimer=setTimeout(()=>reject(Error('CPU bridge unavailable '+stderr)),15000)})]);clearTimeout(readyTimer);
  const areas=Array.from({length:6},(_,i)=>({value:'Synthetic daylight scene '+i}));const label={textContent:''};const root={querySelectorAll:s=>s==='.six-prompt'?areas:s==='.six-card'?Array.from({length:6},()=>({querySelector:()=>label})):[],querySelector:s=>({value:s==='.six-start'?'0':s==='.six-inheritance'?'independent':''})};
  const node={type:'H3SixDirectorState',properties:{h3_six_director:true},__sixRoot:root,__sixUI:{group:{id:'FRONTEND_GROUP'}},__h3EditSync:Promise.resolve()};
  const app={graph:{extra:{h3_prebake_production:{enabled:true}},_nodes:[node]}};
  const api={queuePrompt:()=>{throw Error('No bake/model/video generation allowed in CPU contract test')}};
  // The asynchronous JSON result must be resolved before constructing the response, as real HTTP does.
  api.fetchApi=async(path,options)=>{try{const result=await rpc(path.split('/').pop(),JSON.parse(options.body));return {ok:true,status:200,json:async()=>result}}catch(error){return {ok:false,status:409,json:async()=>({error:error.message})}}};
  globalThis.__H3_CPU_PORTS={app,api};
  const file=join(__dirname,'../custom_nodes/local_author/h3_conditioning_prebake/web/production.js');const source=readFileSync(file,'utf8').replace(/^import .*$/gm,'')+'\n';
  const module=await import('data:text/javascript;base64,'+Buffer.from('const {app,api}=globalThis.__H3_CPU_PORTS;\n'+source).toString('base64'));
  const graph={'136':{class_type:'MiniMaxH3ReferenceToVideo',inputs:{prompt:['138',0]}},'138':{class_type:'PrimitiveStringMultiline',inputs:{value:areas[0].value}},'125':{class_type:'SamplerCustomAdvanced',inputs:{}},PREP:{class_type:'H3ContinuationPrepare',inputs:{enabled:false}},'764':{class_type:'CreateVideo',inputs:{fps:24,images:['136',0]}}};
  const prepared=await module.prepareProduction({output:graph,workflow:{}},areas[0].value,0,{continuous:true,project_id:'CPU_PROJECT'},()=>{},()=>{throw Error('No generation expected')});
  assert.equal(prepared.fallback,true);assert.ok(prepared.context.execution_version);assert.ok(prepared.context.story_id);
  const guarded=await module.cachedGraph(graph,prepared);assert.ok(guarded.ATTEMPT_GUARD);assert.ok(prepared.attempt_id);
  const result=await module.submitProduction(prepared,guarded,{},'cpu-test');assert.ok(result.prompt_id);
  await assert.rejects(module.submitProduction(prepared,guarded,{},'cpu-test'),/already dispatched/);
  await rpc('restart');const recovered=await module.productionStatus(prepared,result.prompt_id);assert.equal(recovered.status,'PENDING');assert.equal(recovered.prompt_id,result.prompt_id);
  await assert.rejects(rpc('story',{action:'bind',story_id:'OTHER_STORY',previous_story_id:prepared.context.story_id,group_id:'OTHER_GROUP',project_id:'OTHER_PROJECT',start_index:0,start_mode:'independent'}),/pending/);
  areas[0].value='Edited synthetic daylight scene';await module.syncProductionTexts(node);
  const stats=await rpc('stats');assert.equal(stats.submissions,1);assert.equal(stats.queued,1);assert.deepEqual(stats.cancelled,[]);assert.equal(stats.gpu_initialized,false);
 }finally{
  child.stdin.end();await new Promise(resolve=>child.once('exit',resolve));lines.close();delete globalThis.__H3_CPU_PORTS;
 }
});
