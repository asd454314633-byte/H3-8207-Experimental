import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
export const GUIDE_SPEC='SIX_USER_GUIDE_SPEC';
async function request(path,data){const response=await api.fetchApi('/h3/six-guide/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'本段关键帧校验失败');return result}
export async function uploadGuide(file){
 const form=new FormData();form.append('image',file);form.append('subfolder','h3_six_guides');form.append('overwrite','false');
 const r=await api.fetchApi('/upload/image',{method:'POST',body:form});const value=await r.json();if(!r.ok)throw Error(value.error||'关键帧上传失败');
 return {source:[value.subfolder,value.name].filter(Boolean).join('/')};
}
export function guideImageURL(source){const cut=source.lastIndexOf('/');return api.apiURL('/view?'+new URLSearchParams({filename:source.slice(cut+1),subfolder:source.slice(0,Math.max(0,cut)),type:'input'}))}
function checkLegacy(){const old=app.graph.getNodeById(965);if(old?.type==='H3GuideTimeline'&&old.mode!==4)throw Error('旧965关键帧时间线与1056存在双向依赖；请保持965旁路，用本段关键帧控件指定图片，未提交GPU')}
export function assertGuideSafe(config){if(config?.enabled)checkLegacy()}
export function watchGuideFrames(root,onChange){
 let previous='';
 const timer=setInterval(()=>{
  if(!app.graph?._nodes?.some(n=>n.__sixRoot===root)){clearInterval(timer);return}
  const seen=new Set(),rows=[];
  function visit(graph){if(!graph||seen.has(graph))return;seen.add(graph);for(const n of graph._nodes||[]){rows.push([n.id,n.mode,...(n.widgets||[]).filter(w=>(typeof w.value==='number'||typeof w.value==='boolean')&&/^(value|fps|length|frames|clean_rebase_enabled|clean_rebase_segment)$/.test(w.name)).map(w=>[w.name,w.value])]);visit(n.subgraph)}}
  visit(app.graph);const signature=JSON.stringify(rows);
  if(previous&&previous!==signature)onChange();previous=signature;
 },750);
 return ()=>clearInterval(timer);
}
export async function previewGuide(index,config){
 if(!config?.enabled)return null;
 checkLegacy();
 const host=app.graph._nodes.find(n=>n.type==='H3SixDirectorState'&&n.properties.h3_six_director),root=host?.__sixRoot;
 const continuous=root?.querySelector('.six-continuous').value==='on';
 const independent=!continuous||(root?.querySelector('.six-inheritance').value==='independent'&&Number(root?.querySelector('.six-start').value)===index);
 const cross=host?.properties.h3_cross_group?.enabled===true;
 const snapshot=await app.graphToPrompt();
 return (await request('preflight',{graph:snapshot.output,index,config,inherit:continuous&&(index>0||cross)&&!independent,snapshot_id:'UI_PREVIEW_'+index})).guide;
}
export async function prepareUserGuide(snapshot,index,options){
 const config=options.user_guide;
 if(!config?.enabled)return null;
 checkLegacy();
 const inherit=options.continuous===true&&(index>0||options.cross_group?.enabled===true)&&options.independent!==true;
 const value=(await request('preflight',{graph:snapshot.output,index,config,inherit,snapshot_id:options.submission_id})).guide;
 if(!value)throw Error('当前段关键帧没有编译结果');
 if(snapshot.output[GUIDE_SPEC])throw Error('当前段关键帧快照重复');
 snapshot.output[GUIDE_SPEC]={class_type:'PrimitiveStringMultiline',inputs:{value:JSON.stringify(value)}};
 return value;
}
export async function compileUnmanagedGuide(graph,index,options,project){
 if(!options.user_guide?.enabled)return graph;
 const context={project_id:project,group_id:options.submission_id,execution_version:options.submission_id};
 return (await request('compile',{graph,index,context,attempt_id:options.submission_id})).graph;
}
