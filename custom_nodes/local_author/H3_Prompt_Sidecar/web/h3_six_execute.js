import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
import {prepareUserGuide,compileUnmanagedGuide,assertGuideSafe} from './h3_six_guides.js?v=20261017guide3';
import {prepareLongSong,finishLongSong} from './h3_long_song.js?v=20261020closeout1';
import {resolveSongStart} from '/extensions/H3_LongSong/start_contract.js?v=20261016origin1';
import {prepareProduction,cachedGraph,acceptProduction,submitProduction,productionStatus} from '/extensions/h3_conditioning_prebake/production.js?v=20261020recovery2';
import {compileForSubmission} from './h3_six_compiler.js?v=20261020strict6';
import {bindTaskWorkflow} from './h3_task_workflow.js?v=20261020snapshot1';

const flights=new Map();
let activeExecutions=0,submissionTail=Promise.resolve();
const continuityFlights=new Map();
// Websocket events wake the exact flight. History is the terminal source of truth:
// it also catches a missed event, reconnect, or an event preceding HTTP response.
const terminalEvents=new Map();
for(const name of ['execution_success','execution_error','execution_interrupted'])api.addEventListener(name,event=>{
  const id=event.detail?.prompt_id;if(!id)return;
  terminalEvents.set(id,{name,message:event.detail.exception_message});
  if(terminalEvents.size>128)terminalEvents.delete(terminalEvents.keys().next().value);
  flights.get(id)?.check();
});

function waitForCompletion(id,timeout){
  let checking=false,settled=false,interval,timer,resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no});promise.catch(()=>{});
  function cleanup(){clearInterval(interval);clearTimeout(timer);flights.delete(id);terminalEvents.delete(id)}
  function finish(error){if(settled)return;settled=true;cleanup();error?reject(error):resolve()}
  async function check(){
    if(checking||settled)return;checking=true;
    try{
      const response=await api.fetchApi(`/history/${encodeURIComponent(id)}`,{signal:AbortSignal.timeout(10000)});
      if(response.ok){const history=(await response.json())[id];
        const errors=history?.status?.messages?.filter(([name])=>['execution_error','execution_interrupted'].includes(name));
        if(errors?.length){finish(Error(errors[0][1]?.exception_message||'视频执行失败或被取消'));return}
        if(history?.status?.status_str==='error'){finish(Error('视频执行失败或被取消'));return}
        if(history?.status?.completed===true&&history.status.status_str==='success'){finish();return}
      }
      const terminal=terminalEvents.get(id);
      if(terminal&&terminal.name!=='execution_success')finish(Error(terminal.message||'视频执行失败或被中断'));
      // Generation has no wall-clock deadline. Exact history/events remain authoritative.
    }catch(error){
      // A transient HTTP disconnect is not SUCCESS; the bounded monitor retries.
    }finally{checking=false}
  }
  interval=setInterval(check,1500);
  flights.set(id,{check,cleanup});check();return {promise,cleanup};
}

export function sixExecutionState(){return {executing:activeExecutions>0,pendingPromptIds:[...flights.keys()]}}

async function storeRequest(path,data) {
  const response=await api.fetchApi(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value=await response.json();if(!response.ok)throw Error((path.startsWith('/h3/cross-group/')?'跨组校验失败：':path==='/h3/long-song/validate-start'?'音频起点校验失败：':'')+(value.error||'连续存档检查失败'));return value;
}

export function executeVisiblePrompt(text,index,update,options={}) {
  const host=app.graph._nodes.find(n=>n.type==='H3SixDirectorState'&&n.properties.h3_six_director);
  options={...options,long_song:structuredClone(host?.properties.h3_long_song||null)};
  options={...options,user_guide:structuredClone(host?.__sixUI?.guideSnapshot?.()[index]||host?.properties.six_prompt_state?.guides?.[index]||null)};
  assertGuideSafe(options.user_guide);
  if(host?.properties.h3_cross_group?.enabled===true)options={...options,cross_group:structuredClone(host.properties.h3_cross_group)};
  options={...options,submission_id:crypto.randomUUID(),production_selection:host?structuredClone({story_id:host.properties.h3_prebake_story_id,binding:host.properties.h3_prebake_binding,generated_group_id:host.__sixUI?.group?.id||null,texts:[...host.__sixRoot.querySelectorAll('.six-prompt')].map(a=>a.value),revisions:host.properties.h3_prebake_revisions||[0,0,0,0,0,0],previous:host.properties.h3_prebake_texts||['','','','','','']}):null};
  const key=(options.project_id||'H3_SIX_V288')+':'+index;
  const dependencies=options.continuous===true&&index>0&&options.independent!==true?[continuityFlights.get((options.project_id||'H3_SIX_V288')+':'+(index-1))].filter(Boolean):[];
  const promise=runVisiblePrompt(text,index,update,options,dependencies);
  if(options.continuous===true){continuityFlights.set(key,promise);const remove=()=>{if(continuityFlights.get(key)===promise)continuityFlights.delete(key)};promise.then(remove,remove)}
  return promise;
}
async function runVisiblePrompt(text,index,update,options,dependencies) {
  activeExecutions++;
  let monitor=null,release=null;
  try{
    const snapshot=structuredClone(await app.graphToPrompt());
    if(dependencies.length){update('已接受续接请求，等待前段真实存档');const parents=await Promise.all(dependencies);options={...options,predecessor_binding:parents.at(-1)?.binding}}
    const previous=submissionTail;submissionTail=new Promise(resolve=>release=resolve);await previous;
    const project=options.project_id||'H3_SIX_V288';
    const continuous=options.continuous===true;
    const cross=options.cross_group?.enabled===true;
    const inherit=continuous&&(index>0||cross)&&options.independent!==true;
    if(cross&&(!options.long_song?.enabled||app.graph.extra?.h3_prebake_production?.enabled!==true))throw Error('跨组续接需要现有完整歌曲适配和PreBake受控提交链');
    if(options.long_song?.enabled){
      const firstText=index===0?text:options.production_selection?.texts?.[0];
      options={...options,long_song:resolveSongStart(options.long_song,firstText)};
      let selectedProject=options.predecessor_binding?.project_id||options.production_selection?.binding?.project_id||project;
      if(cross){
        if(!options.cross_group.contract)throw Error('请先核验并绑定上一组六段；未提交GPU');
        // The current canvas can still point at the completed source group.
        // Discovery is read-only; the actual immutable target is allocated by
        // prepareProduction's fork and checked again by the submission gate.
        if(selectedProject===options.cross_group.contract.source_project)selectedProject='H3_NEXT_'+options.submission_id.replaceAll('-','');
        if(options.cross_group.source_project!==options.cross_group.contract.source_project)throw Error('跨组前驱选择与绑定身份不一致，请重新核验');
        const checked=await storeRequest('/h3/cross-group/validate',{contract:options.cross_group.contract,target_project:selectedProject,source:options.long_song.source,requested_start:options.long_song.start_seconds,requested_origin:options.long_song.start_origin,continuous,independent:options.independent===true});
        options={...options,cross_group:{enabled:true,contract:checked.contract},long_song:{...options.long_song,start_seconds:checked.contract.song_start,start_origin:'跨组原曲边界 '+checked.contract.global_boundary+'秒'}};
      }
      const prepare=Object.values(snapshot.output).find(n=>n.class_type==='H3ContinuationPrepare')?.inputs;
      const verified=await storeRequest('/h3/long-song/validate-start',{...options.long_song,project_id:selectedProject,segment_index:index,inherit,...(cross?{cross_group:options.cross_group.contract,graph:snapshot.output,clean_rebase:prepare?.clean_rebase_enabled===true&&Number(prepare.clean_rebase_segment)===index}:{})});
      update(cross?`接上一组：新增内容从${options.cross_group.contract.global_boundary}秒接续，首段保护并仅裁剪39帧`:`原曲起点 ${verified.start_seconds}秒（${options.long_song.start_origin}）；后续段按实际保存帧数自动接续`);
    }
    prepareLongSong(snapshot,index,options);
    const userGuide=await prepareUserGuide(snapshot,index,options);
    if(userGuide)update(`第${index+1}段关键帧：可见索引${userGuide.visible_frame} → 模型索引${userGuide.model_frame}（保护区${userGuide.protected_frames}帧）`);
    // 独立编译接线（2026-10-19）：手写原稿先经8210独立编译/官方校验，编译稿作为唯一最终文本
    // 进入 N138、PreBake 缓存与真实提交；失败则显示真实原因并阻断，不回退原稿。
    if(continuous&&options.production_selection?.texts?.length===6){
      // Plan one consistent compiled six-text revision. Keeping raw text for
      // earlier segments here would invalidate their accepted cache identities
      // when the next segment is prepared.
      const compiled=[];
      for(let i=0;i<6;i++)compiled.push(await compileForSubmission(i===index?text:options.production_selection.texts[i],i,options,update,snapshot));
      options={...options,production_selection:{...options.production_selection,texts:compiled}};
      text=compiled[index];
    }else text=await compileForSubmission(text,index,options,update,snapshot);
    const prebake=await prepareProduction(snapshot,text,index,options,update,waitForCompletion);
    const generationProject=prebake?.context?.project_id||project;
    if(inherit&&index>0){
      try{await storeRequest(`/h3/six/store?project_id=${encodeURIComponent(generationProject)}&segment_index=${index-1}`)}
      catch(error){throw Error(`无法从第${index+1}段连续续跑：${error.message}`)}
    }
    const node=app.graph.getNodeById(138),widget=node?.widgets?.find(w=>w.name==='value');
    if(node?.type!=='PrimitiveStringMultiline'||!widget)throw Error('缺少原H3工作流的最终Prompt文本字段');
    widget.value=text;widget.callback?.(text);app.graph.setDirtyCanvas(true,true);
    snapshot.workflow=bindTaskWorkflow(snapshot.workflow,{nodeId:node.id,widgetIndex:node.widgets.indexOf(widget),widgetName:widget.name,text,context:prebake?.context});
    const original=api.queuePrompt;let submitted=null,completion=null;
    // Preserve the native UI graph snapshot; managed attempts submit once via the backend.
    // The backend reserves the exact prompt_id and owns recovery/stop loss.
    const capture=async function(...args){
      args[1]={...args[1],...structuredClone(snapshot)};
      const output=args[1]?.output;
      // The legacy role node supplies console widgets only.
      if(output)delete output['915'];
      // Keep audio outputs, but use the selected literal as final H3 text.
      if(output?.['138']?.inputs)output['138'].inputs.value=text;
      if(output?.['136']?.inputs&&!options.long_song?.enabled)output['136'].inputs.prompt=['138',0];
      const native=Object.values(output||{}).filter(n=>n.class_type?.startsWith('H3Continuation'));
      for(const type of ['Prepare','Guides','Save','TrimOnce','Assemble']){
        const nodes=native.filter(n=>n.class_type==='H3Continuation'+type);
        if(nodes.length!==1)throw Error('缺少或重复Native连续节点：'+type);
        const inputs=nodes[0].inputs;
        if(type!=='Guides')inputs.project_id=generationProject;
        if(['Prepare','Save','TrimOnce'].includes(type))inputs.segment_index=index;
        if(type==='Save')inputs.enabled=Boolean(prebake)||continuous;
        if(['Prepare','Guides','TrimOnce'].includes(type))inputs.enabled=inherit;
        if(type==='Prepare')delete inputs.prev_latent; // Resume uses this exact project's index-1 store.
      }
      args[1].output=await cachedGraph(finishLongSong(output,options,generationProject),prebake);
      if(!prebake)args[1].output=await compileUnmanagedGuide(args[1].output,index,options,generationProject);
      if(continuous)await storeRequest('/h3/six/acceptance',{project_id:generationProject,segment_index:index,status:'PENDING',group_id:prebake?.context?.group_id});
      const result=prebake?await submitProduction(prebake,args[1].output,args[1].workflow,api.clientId):await original.apply(this,args);
      if(!submitted&&result?.prompt_id){
        submitted=result.prompt_id;
        monitor=waitForCompletion(submitted,options.timeout_ms);completion=monitor.promise;
        // Keep an early websocket error handled while native Queue finishes.
        completion.catch(()=>{});update('已加入队列',{prompt_id:submitted});
      }
      return result;
    };
    api.queuePrompt=capture;
    try{const result=await app.queuePrompt(0,1);if(result===false&&!submitted)throw Error('Queue未成功，请查看ComfyUI错误')}
    finally{if(api.queuePrompt===capture)api.queuePrompt=original}
    if(!submitted)throw Error('未收到本次Queue的prompt_id；没有继续提交后续段落');
    release();release=null;
    await completion;
    if(prebake){const status=await productionStatus(prebake,submitted);if(status.status!=='SUCCESS')throw Error('本次任务未通过后台验收：'+status.status);await acceptProduction(prebake,submitted);}
    else if(continuous)await storeRequest('/h3/six/acceptance',{project_id:generationProject,segment_index:index,status:'SUCCESS',prompt_id:submitted,group_id:prebake?.context?.group_id});
    return {prompt_id:submitted,execution_version:prebake?.context.execution_version,story_id:prebake?.context.story_id,binding:prebake?.context};
  }finally{release?.();monitor?.cleanup();activeExecutions--}
}


