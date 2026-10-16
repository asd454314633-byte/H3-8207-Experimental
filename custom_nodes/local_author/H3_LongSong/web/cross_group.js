import {app} from '../../../scripts/app.js';
import {api} from '../../../scripts/api.js';
async function request(path,data){const r=await api.fetchApi('/h3/cross-group/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw Error(v.error||'跨组检查失败');return v}
function mount(){
 for(const node of app.graph?._nodes||[]){
  const root=node.__sixRoot;if(node.type!=='H3SixDirectorState'||!root||root.querySelector('.h3-cross-group'))continue;
  const cfg=node.properties.h3_cross_group||{enabled:false,source_project:'',contract:null};
  const box=document.createElement('section');box.className='h3-cross-group';box.style.cssText='padding:10px;border:1px solid #527281;margin:8px 0;display:flex;flex-wrap:wrap;gap:8px';
  box.innerHTML='<label><input class="cross-enabled" type="checkbox">接上一组六段继续生成</label><input class="cross-source" placeholder="上一组六段的真实存档项目ID" style="width:390px"><button class="cross-current">选用当前已完成组</button><button class="cross-bind">核验并绑定第6段</button><button class="cross-merge">跨组合并（CPU）</button><small class="cross-status" style="width:100%"></small>';
  const enabled=box.querySelector('.cross-enabled'),source=box.querySelector('.cross-source'),status=box.querySelector('.cross-status');enabled.checked=cfg.enabled===true;source.value=cfg.source_project||cfg.contract?.source_project||'';
  const show=()=>{const c=node.properties.h3_cross_group||cfg;status.textContent=!c.enabled?'默认关闭：沿用原六段生成路径。':c.contract?`已绑定 ${c.contract.source_project} 第6段；新内容从原曲${c.contract.global_boundary}秒接续。第1段继承39帧并仅裁一次。`:'已开启；请先核验并绑定上一组六段，尚不能提交。'};
  const save=()=>{node.properties.h3_cross_group={...cfg,...node.properties.h3_cross_group,enabled:enabled.checked,source_project:source.value.trim()};app.graph.setDirtyCanvas(true,true);show();root.dispatchEvent(new Event('sixchange'))};
  enabled.onchange=()=>{save();if(enabled.checked){for(const [selector,value] of [['.six-continuous','on'],['.six-start','0'],['.six-inheritance','resume']]){const el=root.querySelector(selector);el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}))}}};
  source.onchange=()=>{node.properties.h3_cross_group={...node.properties.h3_cross_group,contract:null};save()};
  const bind=async()=>{const selected=source.value.trim(),sequence=node.__crossBindSequence=(node.__crossBindSequence||0)+1;try{status.textContent='CPU校验真实回执、Native、视频SHA256及原曲全局时间轴…';const result=await request('bind',{source_project:selected});if(source.value.trim()!==selected||sequence!==node.__crossBindSequence){status.textContent='前驱选择已变化，请重新核验绑定';return}node.properties.h3_cross_group={enabled:enabled.checked,source_project:selected,contract:result.contract};app.graph.setDirtyCanvas(true,true);show();root.dispatchEvent(new Event('sixchange'))}catch(e){status.textContent=e.message}};
  box.querySelector('.cross-bind').onclick=bind;
  box.querySelector('.cross-current').onclick=()=>{source.value=node.properties.h3_prebake_binding?.project_id||root.querySelector('.six-project').value;source.dispatchEvent(new Event('change'));return bind()};
  box.querySelector('.cross-merge').onclick=async()=>{if(!enabled.checked){status.textContent='跨组开关未启用，沿用原组合并。';return}try{status.textContent='核验跨组成功链并进行CPU合并；不会再次裁剪39帧…';const result=await request('merge',{project_id:node.properties.h3_prebake_binding?.project_id});status.textContent=`跨组合并完成：${result.frames}帧，原曲${result.source_start}～${result.source_end}秒`;
    let video=box.querySelector('video');if(!video){video=document.createElement('video');video.controls=true;video.style.width='320px';box.append(video)}video.src=api.apiURL('/view?'+new URLSearchParams(result.output));
   }catch(e){status.textContent=e.message}};
  root.querySelector('.six-common')?.after(box);show();
 }
}
function attach(){let tries=0;const timer=setInterval(()=>{mount();if(++tries>=20)clearInterval(timer)},500)}
app.registerExtension({name:'H3.CrossGroup8207',afterConfigureGraph:attach,nodeCreated:attach});
