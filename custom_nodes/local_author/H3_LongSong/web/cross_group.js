import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
async function request(path,data){const r=await api.fetchApi('/h3/cross-group/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw Error(v.error||'跨组检查失败');return v}
function mount(nodes=app.graph?._nodes||[]){
 for(const node of nodes){
  const root=node.__sixRoot;if(node.type!=='H3SixDirectorState'||!root||root.querySelector('.h3-cross-group'))continue;
  const cfg=node.properties.h3_cross_group||{enabled:false,source_project:'',contract:null};
  const box=document.createElement('section');box.className='h3-cross-group';box.style.cssText='padding:10px;border:1px solid #527281;margin:8px 0;display:flex;flex-wrap:wrap;gap:8px';
  box.innerHTML='<label><input class="cross-enabled" type="checkbox">接上一组六段继续生成</label><input class="cross-source" readonly placeholder="自动查找并核验真实前驱" style="width:390px"><button class="cross-bind">自动发现并绑定真实第6段</button><button class="cross-merge">跨组合并（CPU）</button><small class="cross-status" style="width:100%"></small>';
  const enabled=box.querySelector('.cross-enabled'),source=box.querySelector('.cross-source'),status=box.querySelector('.cross-status');enabled.checked=cfg.enabled===true;source.value=cfg.source_project||cfg.contract?.source_project||'';
  const show=()=>{const c=node.properties.h3_cross_group||cfg;status.textContent=!c.enabled?'默认关闭：沿用原六段生成路径。':c.contract?`已绑定 ${c.contract.source_project} 第6段；新内容从原曲${c.contract.global_boundary}秒接续。第1段继承39帧并仅裁一次。`:'已开启；请先核验并绑定上一组六段，尚不能提交。'};
  const save=()=>{node.properties.h3_cross_group={...cfg,...node.properties.h3_cross_group,enabled:enabled.checked,source_project:source.value.trim()};app.graph.setDirtyCanvas(true,true);show();root.dispatchEvent(new Event('sixchange'))};
  const bind=async()=>{const state=node.properties.h3_cross_group||{};const song=node.properties.h3_long_song||{};const target=node.properties.h3_prebake_binding?.project_id||root.querySelector('.six-project')?.value||'';const preferred=state.contract?.source_project||'';const story=node.properties.h3_prebake_binding?.story_id||node.properties.h3_prebake_binding?.group_id||'';const sequence=node.__crossBindSequence=(node.__crossBindSequence||0)+1;try{status.textContent='自动查找真实完成组；核验六段回执、Native、视频SHA及原曲时间轴…';const result=await request('discover',{target_project:'H3_NEXT_'+crypto.randomUUID().replaceAll('-',''),source:song.source,song_start:Number(song.start_seconds||0),preferred_project:preferred,story_id:story});if(sequence!==node.__crossBindSequence){status.textContent='续接状态已变化，请重新自动核验';return}const selected=result.contract.source_project;node.properties.h3_cross_group={...state,enabled:enabled.checked,source_project:selected,contract:result.contract};source.value=selected;app.graph.setDirtyCanvas(true,true);show();status.textContent=`已自动绑定真实前驱 ${selected} 第6段；结束于原曲${result.contract.global_boundary}秒。${result.discovery.method==='latest_verified_s6_completion'?'按经核验的S6完成时间选出。':'已复核画布中保留的前驱合同。'}`;root.dispatchEvent(new Event('sixchange'))}catch(e){status.textContent=e.message}};
  enabled.onchange=()=>{save();if(enabled.checked){for(const [selector,value] of [['.six-continuous','on'],['.six-start','0'],['.six-inheritance','resume']]){const el=root.querySelector(selector);if(el){el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}))}}bind()}};
  box.querySelector('.cross-bind').onclick=bind;
  box.querySelector('.cross-merge').onclick=async()=>{if(!enabled.checked){status.textContent='跨组开关未启用，沿用原组合并。';return}try{status.textContent='核验跨组成功链并进行CPU合并；不会再次裁剪39帧…';const result=await request('merge',{project_id:node.properties.h3_prebake_binding?.project_id});status.textContent=`跨组合并完成：${result.frames}帧，原曲${result.source_start}～${result.source_end}秒`;
    let video=box.querySelector('video');if(!video){video=document.createElement('video');video.controls=true;video.style.width='320px';box.append(video)}video.src=api.apiURL('/view?'+new URLSearchParams(result.output));
   }catch(e){status.textContent=e.message}};
  root.querySelector('.six-common')?.after(box);show();
  if(enabled.checked&&!cfg.contract)bind();
 }
}
let mountTimer=null,fullGraphScan=false;const pendingNodes=new Set();
function scheduleMount(node,scanGraph=false){
 if(node)pendingNodes.add(node);if(scanGraph)fullGraphScan=true;if(mountTimer)return;
 let tries=0;mountTimer=setInterval(()=>{if(fullGraphScan)mount();else if(pendingNodes.size)mount([...pendingNodes]);if(++tries>=20){clearInterval(mountTimer);mountTimer=null;fullGraphScan=false;pendingNodes.clear()}},500)
}
app.registerExtension({name:'H3.CrossGroup8207',afterConfigureGraph:()=>scheduleMount(null,true),nodeCreated:node=>scheduleMount(node)});
