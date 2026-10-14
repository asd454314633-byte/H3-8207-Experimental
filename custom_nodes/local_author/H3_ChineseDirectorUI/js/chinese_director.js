import {app} from '/scripts/app.js';
import {api} from '/scripts/api.js';
// UI adapters only. Existing serializer, executor and generation chain are unchanged.
const GUIDE=[965,983,985,988,984,986,989],POSE=[1059,1060,1061,1062,1063];
const n=id=>app.graph.getNodeById(id);
const w=(node,name)=>{const widget=node?.widgets?.find(w=>w.name===name);if(!widget)throw Error('开关状态异常，请重新加载工作流');return widget};
const sub=()=>n(1056)?.subgraph?._nodes||[];
const plans=()=>sub().filter(x=>['H3ContinuationPrepare','H3ContinuationTrimOnce'].includes(x.type));
const active=()=>location.port==='8207'&&app.graph.extra?.h3_chinese_switches?.enabled===true;
let controls={},message;
const dirty=()=>app.graph.setDirtyCanvas(true,true);
function rememberFile(widget,filename){if(Array.isArray(widget.options?.values)&&filename&&!widget.options.values.includes(filename))widget.options.values.push(filename);widget.value=filename;}
function mediaParams(path){const parts=path.replaceAll('\\','/').split('/'),filename=parts.pop();return new URLSearchParams({filename,subfolder:parts.join('/'),type:'input'});}
async function refreshMediaChoices(){
 // Existing nested reference paths are accepted by the nodes' validators, but
 // their dropdowns only enumerate the input root. Confirm before restoring UI choices.
 for(const node of app.graph._nodes){if(!['LoadImage','LoadImageCrop','LoadVideo','LoadAudio'].includes(node.type))continue;
  const widget=node.widgets?.find(x=>['image','file','audio'].includes(x.name)),filename=String(widget?.value||'');if(!filename||!Array.isArray(widget.options?.values))continue;
  const q=mediaParams(filename),r=await api.fetchApi('/view?'+q,{headers:{Range:'bytes=0-31'}});if(r.ok){await r.body?.cancel();rememberFile(widget,filename);}
 }
}
function branch(ids,on){for(const id of ids){if(!n(id))throw Error('开关对应节点缺失，请重新加载工作流');n(id).mode=on?0:4}dirty()}
function modeState(ids){const modes=ids.map(id=>n(id)?.mode);if(modes.every(m=>m===0))return true;if(modes.every(m=>m===4))return false;throw Error('状态异常，请重新同步')}
function rebaseState(){const ns=plans();if(ns.length!==2||ns.some(x=>w(x,'clean_rebase_segment').value!==3))throw Error('连续增强策略异常，请重新加载工作流');const on=w(ns[0],'clean_rebase_enabled').value;if(ns.some(x=>w(x,'clean_rebase_enabled').value!==on))throw Error('状态异常，请重新同步');return on===true}
function guideState(){
 const on=n(965).mode===0;if(![0,4].includes(n(965).mode))throw Error('状态异常，请重新同步');
 const t=JSON.parse(w(n(965),'guides_json').value);
 for(let i=0;i<3;i++){const enabled=on&&t.guides[i]?.enabled!==false;for(const id of [[983,984],[985,986],[988,989]][i])if(n(id).mode!==(enabled?0:4))throw Error('状态异常，请重新同步')}
 return on;
}
export function actual(){return {guide:guideState(),pose:modeState(POSE),rebase:rebaseState(),pose_file:String(w(n(1061),'file').value||'')}}
function show(text=''){if(message)message.textContent=text;}
function render(){const a=actual();for(const key of ['guide','pose','rebase'])if(controls[key])controls[key].value=a[key]?'on':'off';return a}
export function setSwitch(key,on){
 if(key==='guide'){
  const t=JSON.parse(w(n(965),'guides_json').value);
  if(t.guides.length!==3)throw Error('关键画面配置异常，请重新加载工作流');
  let count=0;for(let i=0;i<3;i++){const image=String(w(n([983,985,988][i]),'image').value||'');const has=!!image.trim();t.guides[i].enabled=has;if(has)count++;w(n([984,986,989][i]),'image_name').value=image||'__H3_GUIDE_NOT_SET__.png';branch([[983,984],[985,986],[988,989]][i],on&&has)}
  w(n(965),'guides_json').value=JSON.stringify(t);n(965).mode=on&&count>0?0:4;dirty();
  render();show(on&&count===0?'未选择关键画面，关键画面已自动关闭。':'');return actual();
 }
 else if(key==='pose'){
  if(on&&!String(w(n(1061),'file').value||'').trim()){branch(POSE,false);render();show('未选择动作参考视频，动作控制已自动关闭。');return actual()}
  branch(POSE,on);
 }else if(key==='rebase'){
  for(const node of plans()){const widget=w(node,'clean_rebase_enabled');widget.value=on;widget.callback?.(on)}dirty();
 }else throw Error('未知开关');
 render();show();return actual();
}
function pathCheck(path,video){
 if(!path||!path.trim())throw Error(video?'未选择动作参考视频，动作控制已自动关闭。':'关键画面未配置图片，请先在现有图片节点中选择素材。');
 if(path!==path.trim()||path.includes('..')||/^[\\/]|:|[\\/]$/.test(path))throw Error('素材不能是目录或外部路径，请重新选择有效文件。');
 if(!(video?/\.(mp4|webm|mov|mkv|avi|m4v)$/i:/\.(png|jpe?g|webp|bmp)$/i).test(path))throw Error(video?'动作素材不是视频，请重新选择。':'关键画面不是图片，请重新选择。');
}
async function verify(path,video){
 pathCheck(path,video);const src=api.apiURL('/view?'+mediaParams(path));
 const r=await fetch(src,{headers:{Range:'bytes=0-511'},signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('素材不存在或无法读取，请重新选择。');await r.body?.cancel();
 const media=document.createElement(video?'video':'img');
 try{await new Promise((yes,no)=>{const timer=setTimeout(()=>no(Error('素材读取超时，请重新选择。')),15000);media.onload=media.onloadedmetadata=()=>{clearTimeout(timer);yes()};media.onerror=()=>{clearTimeout(timer);no(Error('素材无法解码，请更换文件。'))};media.src=src;});if(video&&(!media.videoWidth||!media.videoHeight||!Number.isFinite(media.duration)))throw Error('动作视频没有有效画面，请更换视频。');}finally{media.removeAttribute('src');media.load?.()}
}
export async function preflight(){
 if(n(965).mode===0&&! [983,985,988].some(id=>String(w(n(id),'image').value||'').trim()))setSwitch('guide',false);
 // Empty video cannot enter GetVideoComponents even after external graph edits.
 if(!String(w(n(1061),'file').value||'').trim()){branch(POSE,false);if(controls.pose)controls.pose.value='off';show('未选择动作参考视频，动作控制已自动关闭。');}
 const a=actual();for(const key of ['guide','pose','rebase'])if(controls[key]&&controls[key].value!==(a[key]?'on':'off'))throw Error('状态异常，请重新同步');
 if(a.pose)await verify(a.pose_file,true);
 if(a.guide){const timeline=JSON.parse(w(n(965),'guides_json').value);if(timeline.fps!==24||timeline.schema_version!==1)throw Error('关键画面时间配置异常，请重新加载工作流。');for(let i=0;i<timeline.guides.length;i++){const g=timeline.guides[i];if(g.enabled!==false){if(i>2)throw Error('当前只支持已有的三个关键画面槽。');await verify(String(w(n([983,985,988][i]),'image').value||''),false)}}}
 return a;
}
function control(label,key){
 const box=document.createElement('label');box.className='h3-cn-switch';box.style.cssText='display:inline-flex;align-items:center;gap:8px;margin:8px 16px 8px 0;color:inherit';box.append(document.createTextNode(label+'：'));
 const select=document.createElement('select');select.setAttribute('aria-label',label);for(const [v,t]of [['off','关'],['on','开']]){const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o)}
 select.style.cssText='background:#2b4050;color:#fff;border:1px solid #527281;border-radius:7px;padding:7px 12px';
 select.onchange=async()=>{const desired=select.value==='on';try{setSwitch(key,desired);if(key==='pose'&&desired&&actual().pose)await preflight()}catch(e){if(key==='pose')setSwitch('pose',false);show(e.message)}};box.append(select);controls[key]=select;return box;
}
async function attach(){
 if(!active())return;const director=app.graph._nodes.find(x=>x.type==='H3SixDirectorState');
 const root=director?.__sixRoot,panel=n(159)?.__h3DashboardV3Panel;
 if(!root?.querySelector('h2')||!panel){setTimeout(attach,150);return;}
 if(panel.querySelector('.h3-cn-switches'))return;
 controls={};
 const row=document.createElement('section');row.className='h3-cn-switches';row.style.cssText='padding:10px;border:1px solid #527281;border-radius:8px;margin-bottom:10px';
 const materials=(label,id,video=false)=>{
  const box=document.createElement('div');box.style.cssText='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:7px 0';
  const name=document.createElement('span');name.textContent=label+'：';const pick=document.createElement('input');pick.type='file';pick.accept=video?'video/mp4,video/webm,video/quicktime,.mkv,.avi,.m4v':'image/png,image/jpeg,image/webp,image/bmp';pick.setAttribute('aria-label',label);
  const status=document.createElement('span');status.textContent=w(n(id),video?'file':'image').value?'已选择':'未选择';
  const clear=document.createElement('button');clear.textContent='清除';clear.onclick=()=>{w(n(id),video?'file':'image').value='';if(video)setSwitch('pose',false);else setSwitch('guide',n(965).mode===0);status.textContent='未选择';dirty()};
  pick.onchange=async()=>{try{const file=pick.files[0];if(!file)return;pathCheck(file.name,video);const data=new FormData();data.append('image',file);data.append('type','input');data.append('overwrite','false');const r=await api.fetchApi('/upload/image',{method:'POST',body:data});if(!r.ok)throw Error('素材上传失败，请重试。');const result=await r.json(),filename=(result.subfolder?result.subfolder+'/':'')+result.name;await verify(filename,video);rememberFile(w(n(id),video?'file':'image'),filename);if(video)setSwitch('pose',true);else setSwitch('guide',true);status.textContent='已选择';dirty()}catch(e){show(e.message)}};
  box.append(name,pick,status,clear);return box;
 };
 const guide=document.createElement('div');guide.append(control('关键画面','guide'));for(let i=0;i<3;i++)guide.append(materials('关键画面'+(i+1),[983,985,988][i]));
 const motion=document.createElement('div');motion.append(control('动作控制','pose'),materials('动作视频',1061,true));row.append(guide,motion,control('连续增强','rebase'));
 message=document.createElement('div');message.className='h3-cn-switch-message';message.setAttribute('role','status');row.append(message);
 const references=[...panel.querySelectorAll('section')].find(x=>x.querySelector('.h3v14-section-title')?.textContent.includes('参考素材'));if(references)references.after(row);else panel.prepend(row);
 // Derive switches from the loaded graph; no localStorage state is used.
 if(!String(w(n(1061),'file').value||'').trim())branch(POSE,false);
 setSwitch('guide',n(965).mode===0);render();await refreshMediaChoices();
}
if(!app.__h3ChineseSwitchGuard){const original=app.graphToPrompt.bind(app);app.__h3ChineseSwitchGuard=true;app.graphToPrompt=async(...args)=>{if(active()){try{await preflight()}catch(e){show(e.message);throw e}}return original(...args)};}
app.registerExtension({name:'H3.ChineseSwitches.UIOnly',afterConfigureGraph:attach,setup(){setTimeout(attach,300)}});
