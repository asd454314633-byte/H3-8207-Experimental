import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
export function enabled(){return app.graph?.extra?.h3_prebake_production?.enabled===true}
export function storyId(node){
 if(!enabled())return null;
 return node.properties.h3_prebake_story_id ||= 'H3_PREBAKE_'+crypto.randomUUID().replaceAll('-','');
}
async function request(name,data){
 const response=await api.fetchApi('/h3/prebake/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const result=await response.json();if(!response.ok)throw Error('PreBake '+(result.error||response.status));return result;
}
export async function restoreProductionIdentity(node){
 if(!enabled())return null;
 const result=await request('story',{action:'restore',story_id:storyId(node),context:node.properties.h3_prebake_binding||null});
 if(result.binding){node.properties.h3_prebake_binding=result.binding;node.properties.h3_prebake_revisions=[...result.binding.revisions]}
 // An older workflow can restore its explicit identity when preparing its next execution.
 return result.binding;
}
export async function syncProductionTexts(node){
 if(!enabled()||!node.__sixRoot)return;
 const binding=node.properties.h3_prebake_binding;if(!binding)return;
 const texts=[...node.__sixRoot.querySelectorAll('.six-prompt')].map(a=>a.value);
 if(texts.length!==6)return;
 const identity=storyId(node),sequence=node.__h3DraftSequence=(node.__h3DraftSequence||0)+1;
 const result=await request('draft',{context:binding,texts});
 if(storyId(node)!==identity||node.__h3DraftSequence!==sequence)return;
 if(node.properties.h3_prebake_binding?.execution_version===binding.execution_version)node.properties.h3_prebake_texts=[...texts];
}
export async function restoreProductionExecution(node){
 if(!enabled()||!node.__sixUI)return;
 const root=node.__sixRoot,ui=node.__sixUI;
 const result=await request('story',{action:'restore',story_id:storyId(node),context:node.properties.h3_prebake_binding||null});
 if(!result.binding)return;
 const binding=node.properties.h3_prebake_binding;
 if(!binding||['story_id','group_id','project_id','execution_version'].some(k=>binding[k]!==result.binding[k]))return;
 let pending=false,blocked=false;
 for(let i=0;i<6;i++){
  const state=result.segments?.[i],card=ui.cards[i];if(!state)continue;
  const liveAttempt=state.attempt||{},a=liveAttempt.attempt_id?liveAttempt:(state.inherited_attempt||{}),receipt=state.receipt||{};
  // Restore only a missing/pristine editor from its own immutable segment snapshot.
  // A newer saved workflow draft always remains authoritative.
  const guide=a.snapshot?.user_guide;
  if(guide?.segment_index===i)ui.restoreGuide?.(i,guide.config,true);
  const adaptive=state.adaptive_recovery;
  if(adaptive?.output_status==='RECOVERED'&&adaptive.prompt_id===a.prompt_id&&adaptive.segment_index===i){
   // Bind only this story-owned immutable task; never rewrite old Native receipts.
   ui.setSegmentVideo(i,{...adaptive.output.ref,prompt_id:adaptive.prompt_id});
   card.status.textContent='GPU已成功｜自适应V1历史恢复';
   card.videoLabel.textContent+='｜原任务 '+adaptive.prompt_id;
   continue;
  }
  const active=['PREPARED','PENDING','CANCELLING','BLOCKED'].includes(liveAttempt.status);pending ||= active;blocked ||= liveAttempt.status==='BLOCKED';
  const label=active?'后台任务恢复中：'+a.status:state.video_status;
  card.status.textContent=label||'未生成';
  if(state.video_status==='SUCCESS'&&receipt.status==='SUCCESS'&&receipt.prompt_id===a.prompt_id&&receipt.group_id===binding.group_id&&(receipt.project_id===binding.project_id||receipt.inherited_from?.project_id===receipt.project_id)&&receipt.revision===state.revision&&receipt.cache_key===state.cache_key){
   if(card.videoRef?.prompt_id!==receipt.prompt_id){
    if(receipt.video_output_ref)ui.setSegmentVideo(i,receipt.video_output_ref);
    else try{await ui.bindSegmentVideo(i,{prompt_id:receipt.prompt_id})}catch(error){card.videoLabel.textContent='已接受的历史任务；服务器history已不可用，无法恢复视频预览';}
   }
   card.status.textContent='上次执行成功（服务端恢复）';
  }else if(!active){
   if(card.videoRef)card.videoLabel.textContent='保留的历史视频；本次执行尚未选择该结果';
   if(state.video_status==='SUCCESS'){card.status.textContent='恢复阻断：成功回执不完整';pending=true;blocked=true}
  }
 }
 node.__h3RecoveredPending=pending;
 root.dispatchEvent(new Event('sixchange'));
 if(pending){
  root.querySelector('.six-status').textContent='后台任务仍在运行或等待确认；不重复提交。终态后自动恢复结果。';
  clearTimeout(node.__h3RecoveryTimer);
  node.__h3RecoveryStarted ||= performance.now();
  if(!blocked&&performance.now()-node.__h3RecoveryStarted<335000)node.__h3RecoveryTimer=setTimeout(()=>{if(node.__sixRoot===root&&app.graph._nodes.includes(node))restoreProductionExecution(node).catch(error=>{node.__h3RecoveredPending=true;root.querySelector('.six-status').textContent='恢复阻断：'+error.message})},1000);
  else root.querySelector('.six-status').textContent='恢复阻断：任务未确认结束或回执不完整。未提交任何新任务。';
 }
 return result;
}
function setState(root,index,state){
 if(!root)return;
 const cards=root.querySelectorAll('.six-card');
 let label=cards[index]?.querySelector('.six-prebake-state');
 if(!label){label=document.createElement('small');label.className='six-prebake-state';cards[index]?.querySelector('h3')?.after(label)}
 if(label)label.textContent='PreBake: '+state;
}
function contextFor(index,options,text){
 const node=app.graph._nodes.find(n=>n.type==='H3SixDirectorState'&&n.properties.h3_six_director);
 if(!node?.__sixRoot)throw Error('PreBake requires real six-panel UI');
 const root=node.__sixRoot,areas=[...root.querySelectorAll('.six-prompt')];
 if(areas.length!==6)throw Error('Six final text mapping missing');
 const texts=options.production_selection?[...options.production_selection.texts]:areas.map(a=>a.value);texts[index]=text;
 const revisions=options.production_selection?[...options.production_selection.revisions]:(node.properties.h3_prebake_revisions ||= [0,0,0,0,0,0]);
 const previous=options.production_selection?[...options.production_selection.previous]:(node.properties.h3_prebake_texts ||= ['','','','','','']);
 texts.forEach((t,i)=>{if(t!==previous[i]){revisions[i]++;previous[i]=t;if(!options.production_selection||options.production_selection.story_id===storyId(node))setState(root,i,'STALE')}});
 const selection=options.production_selection;
 const gid=selection?(selection.binding?.group_id||selection.generated_group_id||selection.story_id):(node.properties.h3_prebake_binding?.group_id||node.__sixUI?.group?.id||node.properties.h3_prebake_last_plan?.group_id||storyId(node));
 if(!gid||gid.length>160||!/^[A-Za-z0-9_-]+$/.test(gid))throw Error('Invalid isolated PreBake story identity');
 return {root,texts,context:{project_id:node.properties.h3_prebake_binding?.project_id||null,group_id:gid,revisions:[...revisions],fps:24},node};
}
export async function prepareProduction(snapshot,text,index,options,update,waitForCompletion){
 if(!enabled())return null;
 // Single-segment and batch submissions share the same snapshot and cache path.
 const {root,texts,context,node}=contextFor(index,options,text);
 const resolveFps=(value)=>{if(!Array.isArray(value))return Number(value);const n=snapshot.output[value[0]];if(n?.class_type?.startsWith('Primitive'))return Number(n.inputs.value);if(n?.class_type==='Any Switch (rgthree)')return resolveFps(Object.entries(n.inputs).sort().find(([,v])=>v!=null)?.[1]);throw Error('PreBake cannot resolve actual output fps')};
 const fpsInput=snapshot.output['764']?.inputs?.fps;context.fps=resolveFps(fpsInput);if(!Number.isFinite(context.fps)||context.fps<=0)throw Error('Invalid actual output fps');
 await node.__h3EditSync?.catch(()=>{});
 const bound=options.predecessor_binding||options.production_selection?.binding||node.properties.h3_prebake_binding;
 const generated=options.production_selection?options.production_selection.generated_group_id:node.__sixUI?.group?.id;
 const newStory=bound&&generated&&generated!==bound.group_id;
 const originalIdentity=options.production_selection?.story_id||storyId(node);
 const identity=newStory?'H3_PREBAKE_'+crypto.randomUUID().replaceAll('-',''):originalIdentity;
 const selectedStart=options.start_index??index;
 const selectedMode=options.continuous===true?(options.start_mode||root.querySelector('.six-inheritance').value):'independent';
 const result=await request('execution',{submission_id:options.submission_id||crypto.randomUUID(),context:{...context,story_id:identity,group_id:newStory?generated:context.group_id,project_id:newStory?generated:(bound?.project_id||options.project_id||'H3_SIX_V288'),execution_version:newStory?null:bound?.execution_version},start_index:selectedStart,start_mode:selectedMode,requested_index:index,texts,graph:snapshot.output});
 if(storyId(node)===originalIdentity){node.properties.h3_prebake_story_id=identity;node.properties.h3_prebake_binding=result.binding}
 // A fork preserves old media, but its invalidated descendants must not keep
 // the previous execution's success labels in the current six-panel UI.
 if(bound?.execution_version!==result.binding.execution_version&&storyId(node)===identity)await restoreProductionExecution(node);
 Object.assign(context,result.binding,{fps:context.fps});
 // Server revisions survive refresh; local values describe only newly edited texts.
 context.revisions=[...result.binding.revisions];
 const prepareNode=Object.values(snapshot.output).find(n=>n.class_type==='H3ContinuationPrepare')?.inputs||{};
 const cleanRebase=prepareNode.clean_rebase_enabled===true&&Number(prepareNode.clean_rebase_segment)===index;
 const requirePredecessor=index>0&&options.continuous===true&&!options.independent&&!cleanRebase;
 const planned=await request('plan',{graph:snapshot.output,texts,context,requested_index:index,require_predecessor:requirePredecessor});
 Object.assign(context,planned.binding);
 if(storyId(node)===identity){node.properties.h3_prebake_binding=planned.binding;node.properties.h3_prebake_revisions=[...planned.binding.revisions]}
 if(storyId(node)===identity)for(const p of planned.plans)setState(root,p.index,p.draft_differs&&p.status==='SNAPSHOT_PRESERVED'?'已提交快照保留（编辑尚未生成）':p.status);
 const current=planned.plans[index];
 if(current.status==='DYNAMIC_FALLBACK'){update('PreBake FALLBACK：'+current.reason);return {fallback:true,context,reason:current.reason,index,text,cache_key:current.cache_key}}
 if(current.status==='ERROR')throw Error(current.reason);
 if(index>0&&options.continuous===true&&!options.independent&&!cleanRebase){
  const response=await api.fetchApi('/h3/six/store?project_id='+encodeURIComponent(context.project_id)+'&segment_index='+(index-1));
  const state=await response.json();if(!response.ok)throw Error('PreBake predecessor is not eligible: '+(state.error||response.status));
 }
 // Bind real video receipts to one stable story across manual 1/2 acceptance and later 3..6 batch.
 const state=await api.fetchApi('/h3/six/native-merge?project_id='+encodeURIComponent(context.project_id));const merge=await state.json();
 if(merge.group_id!==context.group_id){
  if(index>0&&!options.independent)throw Error('Current story has no accepted predecessor group');
  const response=await api.fetchApi('/h3/six/native-merge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:context.project_id,action:'begin',group_id:context.group_id})});if(!response.ok)throw Error('Unable to begin exact Native group');
 }
 const missing=planned.plans.filter(p=>p.index===index&&['STATIC_ELIGIBLE','CACHE_STALE'].includes(p.status));
 for(let j=0;j<missing.length;j++){
  const p=missing[j];if(storyId(node)===identity)setState(root,p.index,'BAKING');update('PreBake：烘焙第'+(p.index+1)+'段');
  const graph=structuredClone(p.bake_graph);
  if(j===missing.length-1){graph.PREBAKE_TE={class_type:'H3SelectiveTEUnload',inputs:{conditioning:['136',0]}};graph.PREBAKE_BAKE.inputs.conditioning=['PREBAKE_TE',0];graph.PREBAKE_BAKE.inputs.require_te_released=true}
  const submitted=await api.queuePrompt(0,{output:graph,workflow:snapshot.workflow});
  if(!submitted?.prompt_id)throw Error('No Bake prompt_id; no retry');
  const monitor=waitForCompletion(submitted.prompt_id);try{await monitor.promise}finally{monitor.cleanup()}
  if(storyId(node)===identity){setState(root,p.index,'CACHED');(node.properties.h3_prebake_bake_receipts ||= []).push({segment:p.index,prompt_id:submitted.prompt_id,cache_key:p.cache_key})}
 }
 // Later textarea edits remain authoritative. Never generate this segment from a superseded Bake.
 // The frozen text belongs to this task; edits remain in the next draft.
 const prepared={context,contract_json:current.contract_json,cache_key:current.cache_key,index,text,root,require_predecessor:requirePredecessor};
 if(storyId(node)===identity)node.properties.h3_prebake_last_plan={group_id:context.group_id,plans:planned.plans.map(p=>({index:p.index,status:p.status,cache_key:p.cache_key,reason:p.reason}))};
 update('PreBake CACHED；TE已释放，准备生成');return prepared;
}
function revisionsFor(node,index,text){return node.properties.h3_prebake_revisions?.[index]||0}
export async function cachedGraph(graph,p){if(!p)return graph;const result=await request(p.fallback?'fallback':'generate',{graph,context:p.context,index:p.index,text:p.text,cache_key:p.cache_key,contract_json:p.contract_json,require_predecessor:p.require_predecessor,anchor_clean_rebase:true});p.attempt_id=result.attempt_id;return result.graph}
export async function acceptProduction(p,prompt_id){
 if(!p)return;
 await request('accepted',{context:p.context,index:p.index,prompt_id,cache_key:p.cache_key});
 const node=app.graph._nodes.find(n=>n.__sixRoot===p.root);
 if(node?.properties.h3_prebake_binding?.execution_version===p.context.execution_version)setState(p.root,p.index,'CACHED / VIDEO_SUCCESS');
}

export async function submitProduction(p,graph,workflow,client_id){return request('submit',{context:p.context,index:p.index,attempt_id:p.attempt_id,graph,workflow,client_id})}
export async function productionStatus(p,prompt_id,cancel=false){return request(cancel?'cancel':'attempt-status',{context:p.context,index:p.index,attempt_id:p.attempt_id,prompt_id})}

