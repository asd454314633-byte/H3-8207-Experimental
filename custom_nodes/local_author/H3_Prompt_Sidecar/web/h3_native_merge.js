// Settings/status only. All gates, submission and completion live in 8197.
const labels={NOT_STARTED:'等待六段完成',DISABLED:'自动合并已关闭',WAITING_6_OF_6:'等待六段完成',SUBMITTED:'正在合并',SUCCESS:'合并完成',ERROR:'合并失败'};
export async function beforeSixExecution(root){await root.__nativeMergeBegin;}
export async function installNativeMerge(root,getContext){
  if(root.__h3NativeMergeSwitch)return;
  root.__h3NativeMergeSwitch=true;
  const {api}=await import('../../../scripts/api.js');
  const box=document.createElement('section');box.className='h3-native-merge-controls';box.style.cssText='padding:10px 12px;margin:8px 0;border:1px solid #527281;border-radius:7px;color:inherit';
  const title=document.createElement('strong');title.textContent='六段视频合并';
  const label=document.createElement('label');label.style.marginLeft='14px';
  const check=document.createElement('input');check.type='checkbox';check.setAttribute('role','switch');check.setAttribute('aria-label','六段完成后自动合并');check.disabled=true;
  label.append(check,document.createTextNode(' 六段完成后自动合并'));
  const status=document.createElement('span');status.style.marginLeft='14px';status.textContent='读取设置…';box.append(title,label,status);
  root.querySelector('.six-common')?.after(box);
  const show=s=>{check.checked=s.auto_merge_enabled;status.textContent=(labels[s.merge_status]||s.merge_status)+(s.merge_output?' · '+s.merge_output.filename:'');};
  const request=async data=>{
    const project=getContext().project_id;
    const response=await api.fetchApi('/h3/six/native-merge'+(data?'':'?project_id='+encodeURIComponent(project)),data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:project,...data})}:{});
    const result=await response.json();if(!response.ok)throw Error(result.error||'读取自动合并设置失败');show(result);return result;
  };
  check.onchange=async()=>{check.disabled=true;try{await request({action:'settings',auto_merge_enabled:check.checked})}catch(error){status.textContent=error.message}finally{check.disabled=false}};
  root.addEventListener('sixchain',event=>{
    if(event.detail.type==='START'){
      const context=getContext();
      root.__nativeMergeBegin=request({action:'begin',group_id:context.group_id||null}).catch(error=>{status.textContent='自动合并未就绪：'+error.message;});
    }
  });
  api.addEventListener('h3_native_merge_state',event=>{if(event.detail.project_id===getContext().project_id)show(event.detail)});
  root.querySelector('.six-project')?.addEventListener('change',()=>{void request().catch(error=>{status.textContent=error.message})});
  try{await request();check.disabled=false}catch(error){status.textContent=error.message}
}
export function activateNativeMergeHooks(app){
  const attach=async()=>{for(let i=0;i<25;i++){const node=app.graph?._nodes.find(n=>n.type==='H3SixDirectorState');if(!node)return;if(node.__sixUI&&node.__sixRoot){await installNativeMerge(node.__sixRoot,()=>({group_id:node.__sixUI.group?.id||null,project_id:node.__sixUI.executionSnapshot().project_id}));return;}await new Promise(r=>setTimeout(r,100));}};
  if(!app.__h3NativeMergeSwitchHooks){app.__h3NativeMergeSwitchHooks=true;app.registerExtension({name:'H3.NativeMergeSwitch',afterConfigureGraph:attach});}return attach();
}
