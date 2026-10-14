import {app} from '../../../scripts/app.js';
const N=id=>app.graph?.getNodeById(id);
const W=(id,name)=>N(id)?.widgets?.find(w=>w.name===name);
const enabled=()=>N(159)?.properties?.h3_audio_8step_converged===true;
function configureOutput(result){
  if(!enabled())return result;
  const p=result.output,c=p['136'];if(!c)return result;
  const multi=String(W(647,'生成模式')?.value).startsWith('多参考');
  if(multi&&!['稳定多参考8步','PDD多参考8步'].includes(W(931,'Ref2VA 后端')?.value))throw Error('本候选仅允许现有 Stable8 / PDD8，不提供20步生产入口');
  const flags=[1,2].map(i=>multi&&!!W(1042,`audio${i}_enabled`)?.value);
  flags.push(multi&&!!W(1042,'audio3_enabled')?.value);
  const track=!!W(1042,'soundtrack_enabled')?.value;
  if(track&&(!multi||!W(150,'启用参考视频')?.value))throw Error('视频音轨参考需要启用多参考生成与参考视频');
  for(const k of Object.keys(c.inputs))if(k.startsWith('ref_audios.')||k.startsWith('ref_video_audios.'))delete c.inputs[k];
  if(!flags.some(Boolean)&&!track){delete p['1042'];return result;}
  const originalPrompt=c.inputs.prompt;
  const check={class_type:'H3Audio8ReferencePreflight',inputs:{prompt:originalPrompt,audio1_enabled:flags[0],audio2_enabled:flags[1],audio3_enabled:flags[2],soundtrack_enabled:track,role3:W(1042,'role3')?.value||''}};
  flags.forEach((on,i)=>{if(on){const id=[143,685,1047][i];check.inputs['audio'+(i+1)]=[String(id),0];c.inputs['ref_audios.ref_audio_'+i]=['1042',i];}});
  if(track){check.inputs.soundtrack=['960',1];c.inputs['ref_video_audios.ref_video_audio_0']=['1042',3];}
  p['1042']=check;c.inputs.prompt=['1042',4];
  return result;
}
function install(){
  if(!enabled())return;
  const backend=W(931,'Ref2VA 后端');
  if(backend?.options)backend.options.values=['稳定多参考8步','PDD多参考8步'];
  if(!app.__h3Audio8Wrapped){
    const original=app.graphToPrompt;
    app.graphToPrompt=async function(...args){
      if(enabled())for(const i of [1,2]){
        const w=W(150,`启用参考音频${i}`),v=!!W(1042,`audio${i}_enabled`)?.value;
        if(w){w.value=v;w.callback?.(v);}
      }
      return configureOutput(await original.apply(this,args));
    };
    app.__h3Audio8Wrapped=true;
  }
  const panel=N(159)?.__h3DashboardV3Panel;
  if(!panel||panel.querySelector('[data-h3-audio8]'))return;
  const section=document.createElement('section');section.dataset.h3Audio8='1';section.style.cssText='padding:12px;border:1px solid #47886d;margin:12px 0';
  const title=document.createElement('h3');title.textContent='8步音频参考';section.append(title);
  for(const [name,label] of [['audio1_enabled','启用音色参考1'],['audio2_enabled','启用音色参考2'],['audio3_enabled','启用音色参考3'],['soundtrack_enabled','参考视频自带音轨']]){
    const row=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=!!W(1042,name)?.value;
    input.onchange=()=>{W(1042,name).value=input.checked;};row.append(input,document.createTextNode(label));section.append(row,document.createElement('br'));
  }
  const file=document.createElement('input');file.type='file';file.accept='audio/*';file.setAttribute('aria-label','上传音色参考3');
  file.onchange=async()=>{const f=file.files?.[0];if(!f)return;const form=new FormData();form.append('image',f);form.append('type','input');const r=await fetch('/upload/image',{method:'POST',body:form});if(!r.ok)throw Error(await r.text());const d=await r.json();W(1047,'audio').value=(d.subfolder?d.subfolder+'/':'')+d.name;};section.append(file);
  const info=document.createElement('p');info.textContent='保留现有8步模式。上传与启用独立，以上音色开关决定是否提交。预检只检查，不重采样、不裁切、不补静音。';section.append(info);panel.append(section);
}
app.registerExtension({name:'H3.Audio8Step.ConvergedCandidate',afterConfigureGraph(){install();setTimeout(install,500);}});
