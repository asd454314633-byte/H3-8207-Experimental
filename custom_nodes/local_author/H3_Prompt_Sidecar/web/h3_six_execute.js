import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
import {prepareProduction,cachedGraph,acceptProduction,submitProduction,productionStatus} from '/extensions/h3_conditioning_prebake/production.js?v=20261014queue';

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

function waitForCompletion(id,timeout=300000){
  timeout=Math.min(Number.isFinite(timeout)&&timeout>0?timeout:300000,300000);
  let checking=false,settled=false,interval,timer,resolve,reject;
  const startTimer=()=>{timer ||= setTimeout(()=>finish(Error('等待执行结果超时，请检查ComfyUI任务历史')),timeout)};
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
      // Queue waiting does not consume a video's 300-second execution budget.
      if(!timer){const q=await api.fetchApi('/queue',{signal:AbortSignal.timeout(10000)});if(q.ok&&(await q.json()).queue_running?.some(item=>item[1]===id))startTimer()}
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
  const value=await response.json();if(!response.ok)throw Error(value.error||'连续存档检查失败');return value;
}

export function executeVisiblePrompt(text,index,update,options={}) {
  const host=app.graph._nodes.find(n=>n.type==='H3SixDirectorState'&&n.properties.h3_six_director);
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
    const inherit=continuous&&index>0&&options.independent!==true;
    const prebake=await prepareProduction(snapshot,text,index,options,update,waitForCompletion);
    const generationProject=prebake?.context?.project_id||project;
    if(inherit){
      try{await storeRequest(`/h3/six/store?project_id=${encodeURIComponent(generationProject)}&segment_index=${index-1}`)}
      catch(error){throw Error(`无法从第${index+1}段连续续跑：${error.message}`)}
    }
    const node=app.graph.getNodeById(138),widget=node?.widgets?.find(w=>w.name==='value');
    if(node?.type!=='PrimitiveStringMultiline'||!widget)throw Error('缺少原H3工作流的最终Prompt文本字段');
    widget.value=text;widget.callback?.(text);app.graph.setDirtyCanvas(true,true);
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
      if(output?.['136']?.inputs)output['136'].inputs.prompt=['138',0];
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
      args[1].output=await cachedGraph(output,prebake);
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
    try{await completion}catch(error){if(prebake&&submitted){const status=await productionStatus(prebake,submitted);if(['PENDING','CANCELLING','BLOCKED'].includes(status.status)&&status.deadline_epoch&&Date.now()/1000>=status.deadline_epoch)await productionStatus(prebake,submitted,true);}throw error;}
    if(prebake){const status=await productionStatus(prebake,submitted);if(status.status!=='SUCCESS')throw Error('本次任务未通过后台验收：'+status.status);await acceptProduction(prebake,submitted);}
    else if(continuous)await storeRequest('/h3/six/acceptance',{project_id:generationProject,segment_index:index,status:'SUCCESS',prompt_id:submitted,group_id:prebake?.context?.group_id});
    return {prompt_id:submitted,execution_version:prebake?.context.execution_version,story_id:prebake?.context.story_id,binding:prebake?.context};
  }finally{release?.();monitor?.cleanup();activeExecutions--}
}


