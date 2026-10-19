export function ensureSixExecutionState(value) {
  const state=value&&typeof value==='object'&&!Array.isArray(value)?value:{};
  return {continuous:state.continuous===true,start_index:Number.isInteger(state.start_index)&&state.start_index>=0&&state.start_index<6?state.start_index:0,start_mode:state.start_mode==='independent'?'independent':'resume',project_id:typeof state.project_id==='string'&&/^[\p{L}\p{N}_-]{1,64}$/u.test(state.project_id.trim())?state.project_id.trim():'H3_SIX_V288'};
}
export async function mountSixDirector(root, {execute=null, base='', executionState={},videoRefs=[],resolveVideo=null,mediaURL=null,storyId=null,guideConfigs=null,guideTools={}}={}) {
  executionState=ensureSixExecutionState(executionState);videoRefs=Array.isArray(videoRefs)?videoRefs:[];
  root.innerHTML=`<style>
  .h3-six{color:#edf2f7;background:#151b24;padding:24px;border:1px solid #364251;border-radius:12px;font:14px/1.6 system-ui,sans-serif;box-sizing:border-box;width:100%;height:100%;min-height:760px;display:flex;flex-direction:column}.h3-six h2,.h3-six h3{margin:0 0 10px}.h3-six textarea{box-sizing:border-box;width:100%;background:#10151d;color:#edf2f7;border:1px solid #465569;border-radius:7px;padding:12px;resize:none;min-height:60px;font:13px/1.7 system-ui,sans-serif}.h3-six .six-input{min-height:100px;height:110px}.h3-six .six-prompts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0;flex:1;min-height:340px}.h3-six .six-card{background:#1d2632;padding:14px;border:2px solid transparent;border-radius:10px;min-width:0;min-height:0;display:flex;flex-direction:column}.h3-six .six-card.six-selected{border-color:#a7d7c5;box-shadow:0 0 16px #a7d7c533}.h3-six .six-prompt{height:auto;flex:1;min-height:60px}.h3-six .six-actions{display:flex}.h3-six .six-common{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.h3-six .six-settings-fields{display:grid;grid-template-columns:1fr 1fr}.h3-six .six-project{background:#10151d;color:#fff;padding:8px;border:1px solid #527281;border-radius:7px;width:230px}.h3-six .six-card h3{margin:0}.h3-six .six-input{height:75px;min-height:60px}.h3-six .six-status{max-height:65px;overflow:auto}.h3-six button,.h3-six select{background:#2b4050;color:#fff;border:1px solid #527281;border-radius:7px;padding:9px 14px;margin:6px 8px 6px 0;font:inherit}.h3-six button{cursor:pointer}.h3-six button:disabled{opacity:.45;cursor:default}.h3-six small{display:block;color:#b8c9d6}.h3-six .six-status{color:#a7d7c5;white-space:pre-wrap;margin:10px 0}.h3-six .six-run-all{background:#a7d7c5;color:#10241d;font-weight:650}
  </style><section class="h3-six"><h2>H3 六段剧情提示词</h2><small>使用只选中；执行才提交视频任务 · 视频连续性：CORE_NATIVE_MASKED_AV · 前缀39帧 / 65音频步</small><div class="six-common"><label>连续生成：<select class="six-continuous" aria-label="连续生成"><option value="off">关</option><option value="on">开</option></select></label><label>起始段：<select class="six-start" aria-label="起始段"><option value="0">从第1段开始</option><option value="1">从第2段续跑</option><option value="2">从第3段续跑</option><option value="3">从第4段续跑</option><option value="4">从第5段续跑</option><option value="5">只跑第6段</option></select></label><label>起始方式：<select class="six-inheritance" aria-label="起始方式"><option value="resume">连续续跑（读取前段存档）</option><option value="independent">独立开始（起始段不继承运动）</option></select></label><label>存档项目：<input class="six-project" aria-label="存档项目" maxlength="64"></label></div><div class="six-common six-settings-fields"><label>全局设定 / Picture与Audio职责<textarea class="six-input six-settings" aria-label="六段全局设定"></textarea></label><label>剧情要求<textarea class="six-input six-goal" aria-label="六段剧情要求" placeholder="设计接下来一分钟的六段连续剧情"></textarea></label></div><div class="six-common"><label>导演模型：<select class="six-model" aria-label="六段导演模型"></select></label><button class="six-generate">生成六段剧情</button><button class="six-model-start" title="由唯一模型管理器预热；忙碌时保护当前请求">预热当前导演模型</button><small class="six-model-label"></small></div><div class="six-status" role="status"></div><div class="six-prompts"></div><div class="six-common"><button class="six-run-all">开始连续生成</button><button class="six-stop" disabled>停止连续生成</button><button class="six-memory-confirm" disabled>确认本组六段，作为下一组剧情基础</button></div><small>确认只更新剧情记忆，不提交视频。</small><small>修改自动保存。按所选起始段依次执行至第6段，上一段成功后才提交下一段；失败即停止。执行不调用导演、不自动确认剧情记忆。</small></section>`;
  const style=document.createElement('style');style.textContent='.h3-six .six-video-wrap{display:flex;flex-direction:column;flex:1;min-height:105px;min-width:0;margin-top:8px;overflow:hidden}.h3-six .six-video{width:100%;height:100%;min-height:75px;flex:1;object-fit:contain;background:#080c12;border-radius:6px}.h3-six .six-video-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.h3-six .six-prompt{flex:1;min-height:60px}.h3-six .six-prompts{min-height:680px}';root.append(style);
  const find=s=>root.querySelector(s),settings=find('.six-settings'),goal=find('.six-goal'),model=find('.six-model'),message=find('.six-status');
  let group=null,busy=false,selected=-1,stopping=false,inBatch=false,activeOperations=0,directorBusy=false,backendBusy=false;
  const chain={state:'IDLE',currentSegment:null,pendingPromptId:null,trace:[]};
  function chainEvent(type,detail={}){const event={type,at:Date.now(),...detail};chain.trace.push(event);root.dispatchEvent(new CustomEvent('sixchain',{detail:event}))}
  const continuous=find('.six-continuous'),start=find('.six-start'),inheritance=find('.six-inheritance'),project=find('.six-project');
  continuous.value=executionState.continuous===true?'on':'off';start.value=String(executionState.start_index||0);inheritance.value=executionState.start_mode||'resume';project.value=executionState.project_id||'H3_SIX_V288';
  const executionOptions=(index,first=index)=>({continuous:continuous.value==='on',project_id:project.value.trim(),independent:continuous.value!=='on'||inheritance.value==='independent'&&index===first,start_index:first,start_mode:inheritance.value});
  const executionSnapshot=()=>({continuous:continuous.value==='on',start_index:Number(start.value),start_mode:inheritance.value,project_id:project.value});
  function executionChanged(){root.dispatchEvent(new Event('sixchange'));find('.six-run-all').textContent='开始连续生成';};
  for(const element of [continuous,start,inheritance,project])element.addEventListener('change',executionChanged);
  project.addEventListener('input',()=>root.dispatchEvent(new Event('sixchange')));executionChanged();
  async function request(path,data){const r=await fetch(base+path.replace('/director/', '/api/h3-director/'),{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw Error(value.error||r.statusText);return value}
  function controls(){
    root.querySelectorAll('textarea,input,select,.six-use').forEach(e=>e.disabled=false);
    cards.forEach((c,i)=>c.run.disabled=selected!==i);
    find('.six-model-start').disabled=backendBusy;
    find('.six-generate').disabled=directorBusy;find('.six-run-all').disabled=inBatch;
    find('.six-stop').disabled=!inBatch;find('.six-memory-confirm').disabled=directorBusy||!group;
  }
  function select(index){selected=index;cards.forEach((c,i)=>{c.card.classList.toggle('six-selected',i===index);c.use.setAttribute('aria-pressed',String(i===index))});controls();if(!inBatch)message.textContent=`已使用第${index+1}段；其他段与本次执行隔离`}
  function persist(){root.dispatchEvent(new Event('sixchange'));localStorage.setItem('h3-six-'+(group?.id||storyId||'manual'),JSON.stringify(cards.map(c=>c.area.value)))}
  const cards=Array.from({length:6},(_,i)=>{
    const card=document.createElement('section');card.className='six-card';card.innerHTML=`<h3>第${i+1}段</h3><small class="six-card-status">未生成</small><textarea class="six-prompt" aria-label="第${i+1}段 Prompt" spellcheck="false"></textarea><div class="six-actions"><button class="six-use" aria-pressed="false">使用</button><button class="six-execute" disabled>执行</button></div><small class="six-count">本次会话执行：0次</small>`;find('.six-prompts').append(card);
    const wrap=document.createElement('div');wrap.className='six-video-wrap';wrap.innerHTML=`<video class="six-video" preload="metadata" controls playsinline aria-label="第${i+1}段视频" hidden></video><small class="six-video-label">暂无本段视频</small>`;card.querySelector('.six-actions').before(wrap);
    const video=wrap.querySelector('video'),videoLabel=wrap.querySelector('small');
    video.addEventListener('play',()=>cards.forEach(c=>{if(c.video!==video)c.video.pause()}));
    video.addEventListener('loadedmetadata',()=>{videoLabel.textContent=video.dataset.filename||''});
    video.addEventListener('error',()=>{videoLabel.textContent='视频加载失败：'+(video.dataset.filename||'')});
    const area=card.querySelector('textarea'),status=card.querySelector('.six-card-status'),use=card.querySelector('.six-use'),run=card.querySelector('.six-execute');
    let timer=null,save=Promise.resolve(),count=0;
    function saveEdit(){if(!group)return save;const payload={group_id:group.id,segment_index:i,english_prompt:area.value};save=save.catch(()=>{}).then(()=>request('/director/groups/save',payload)).catch(error=>{message.textContent='服务保存失败，修改仍保留在本页：'+error.message});return save}
    area.oninput=()=>{status.textContent='已修改';persist();clearTimeout(timer);timer=setTimeout(saveEdit,600)};
    use.onclick=()=>select(i);
    run.onclick=()=>operation(()=>runSegment(i));
    return {card,area,status,use,run,video,videoLabel,videoRef:null,accepted:()=>{count++;card.querySelector('.six-count').textContent=`本次会话执行：${count}次`}};
  });
  // Each controller owns only its card. Workflow state and immutable attempt state
  // are separate: a recovery never replaces an explicitly saved/edited draft.
  const guideStyle=document.createElement('style');guideStyle.textContent='.h3-six .six-card{overflow:auto}.h3-six .six-guide{flex:none}.h3-six .six-guide input[type=number]{width:85px;background:#10151d;color:#fff;border:1px solid #527281}.h3-six .six-guide select{max-width:100%;padding:4px}.h3-six .six-guide button{padding:4px 8px}';root.append(guideStyle);
  const guideControls=cards.map((card,index)=>{
    let pristine=!Array.isArray(guideConfigs)||guideConfigs[index]==null;
    let config={enabled:false,source:'',source_sha256:'',mode:'from_end',value:88,...structuredClone(guideConfigs?.[index]||{})};
    let sequence=0,uploadSequence=0,timer;
    const box=document.createElement('section');box.className='six-guide';box.dataset.segment=String(index);
    box.style.cssText='border:1px solid #527281;border-radius:6px;padding:6px;margin:6px 0';
    box.innerHTML=`<label><input class="six-guide-enabled" type="checkbox" aria-label="第${index+1}段本段关键帧"> 本段关键帧</label><details class="six-guide-details"><summary>图片与插入位置</summary><button class="six-guide-upload" type="button">上传图片</button><input class="six-guide-file" type="file" accept="image/*" hidden><img class="six-guide-thumb" alt="第${index+1}段关键帧缩略图" hidden style="width:72px;height:54px;object-fit:contain"><small class="six-guide-source"></small><label>插入位置 <select class="six-guide-mode" aria-label="第${index+1}段关键帧位置类型"><option value="frame">第N帧（可见索引从0计）</option><option value="from_end">倒数第N帧（从1计）</option><option value="seconds">第N秒（本段可见时间）</option></select></label><input class="six-guide-value" type="number" min="0" step="1" aria-label="第${index+1}段关键帧位置"><button class="six-guide-clear" type="button">清除本段关键帧</button></details><small class="six-guide-compiled"></small>`;
    card.card.querySelector('.six-actions').before(box);
    const find=s=>box.querySelector(s),enabled=find('.six-guide-enabled'),mode=find('.six-guide-mode'),value=find('.six-guide-value'),thumb=find('.six-guide-thumb'),label=find('.six-guide-compiled');
    function draw(){enabled.checked=config.enabled===true;mode.value=config.mode;value.value=config.value;value.step=config.mode==='seconds'?'0.001':'1';value.min=config.mode==='from_end'?'1':'0';find('.six-guide-source').textContent=config.source||'未上传图片';thumb.hidden=!config.source;if(config.source&&guideTools.mediaURL)thumb.src=guideTools.mediaURL(config.source);if(!config.enabled)label.textContent='关键帧：关闭；本段不新增用户Guide';}
    async function preview(){const own=++sequence,current=structuredClone(config);if(!current.enabled){draw();return}if(!current.source){label.textContent='请上传本段图片；不会提交生成';return}label.textContent='CPU计算实际帧号…';try{const result=await guideTools.preview?.(index,current);if(own!==sequence||!result)return;config.source_sha256=result.source_sha256;label.textContent=`实际编译：可见索引${result.visible_frame} → 模型索引${result.model_frame}｜生成${result.frames}帧，保护区${result.protected_frames}帧`;root.dispatchEvent(new Event('sixchange'));}catch(error){if(own===sequence)label.textContent='关键帧校验：'+error.message}}
    function edited(){if(card.videoRef)card.status.textContent='关键帧已修改（旧视频保留，需重新生成）'}
    function changed(){pristine=false;config={...config,enabled:enabled.checked,mode:mode.value,value:value.value};sequence++;draw();edited();root.dispatchEvent(new Event('sixchange'));clearTimeout(timer);timer=setTimeout(preview,200)}
    enabled.onchange=()=>{find('details').open=enabled.checked;changed()};mode.onchange=changed;value.oninput=changed;
    find('.six-guide-upload').onclick=()=>find('.six-guide-file').click();
    find('.six-guide-file').onchange=async event=>{const file=event.target.files?.[0];if(!file)return;const own=++uploadSequence;label.textContent='上传本段关键帧…';try{if(!guideTools.upload)throw Error('当前入口没有ComfyUI图片上传接口');const uploaded=await guideTools.upload(file);if(own!==uploadSequence)return;sequence++;config={...config,...uploaded,source_sha256:'',enabled:enabled.checked};pristine=false;draw();edited();root.dispatchEvent(new Event('sixchange'));await preview()}catch(error){if(own===uploadSequence)label.textContent=error.message}finally{event.target.value=''}};
    find('.six-guide-clear').onclick=()=>{sequence++;uploadSequence++;clearTimeout(timer);pristine=false;config={enabled:false,source:'',source_sha256:'',mode:'from_end',value:88};thumb.removeAttribute('src');draw();edited();root.dispatchEvent(new Event('sixchange'))};
    draw();if(config.enabled)queueMicrotask(preview);
    return {snapshot:()=>structuredClone(config),preview,restore:(saved,onlyPristine)=>{if(onlyPristine&&!pristine)return;sequence++;uploadSequence++;config={enabled:false,source:'',source_sha256:'',mode:'from_end',value:88,...structuredClone(saved)};pristine=false;draw();if(config.enabled)preview();root.dispatchEvent(new Event('sixchange'))}};
  });
  root.addEventListener('change',event=>{if(event.target.matches('.six-continuous,.six-start,.six-inheritance'))guideControls.forEach(c=>c.preview())});
  guideTools.watch?.(root,()=>guideControls.forEach(c=>c.preview()));
  function setSegmentVideo(index,ref){
    if(!Number.isInteger(index)||index<0||index>=6)throw Error('无效视频段号');
    if(!ref||typeof ref.filename!=='string'||!ref.filename||typeof ref.subfolder!=='string'||!['output','temp','input'].includes(ref.type)||typeof ref.prompt_id!=='string'||!ref.prompt_id)throw Error('视频引用缺少filename/subfolder/type/prompt_id');
    if(!mediaURL)throw Error('当前入口不支持ComfyUI媒体预览');
    const clean={filename:ref.filename,subfolder:ref.subfolder,type:ref.type,prompt_id:ref.prompt_id};
    const card=cards[index];card.video.pause();card.videoRef=clean;card.video.hidden=false;card.video.dataset.filename=clean.filename;card.videoLabel.textContent='加载视频：'+clean.filename;card.video.src=mediaURL(clean);card.video.load();root.dispatchEvent(new Event('sixchange'));
  }
  async function bindSegmentVideo(index,result){if(!resolveVideo)throw Error('没有视频结果解析器');const ref=await resolveVideo(index,result);setSegmentVideo(index,ref);return ref}
  for(let i=0;i<6;i++)if(videoRefs[i]){try{setSegmentVideo(i,videoRefs[i])}catch(error){cards[i].videoLabel.textContent=error.message}}
  async function operation(fn){
    activeOperations++;busy=true;controls();
    try{await fn()}catch(e){message.textContent=e.message}
    finally{activeOperations--;busy=activeOperations>0;if(!busy){chain.state='IDLE';chain.currentSegment=null;chain.pendingPromptId=null;chainEvent('IDLE')}controls()}
  }
  async function runSegment(index,text=cards[index].area.value,options=executionOptions(index)){
    if(!execute)throw Error('请从当前实例控制台的“六段提示词”入口打开本页');
    if(!text.trim())throw Error(`第${index+1}段Prompt为空`);
    if(selected!==index)throw Error('请先使用本段');
    const card=cards[index],sequence=card.requestSequence=(card.requestSequence||0)+1;let counted=false;
    try{const result=await execute(text,index,(state,detail)=>{if(card.requestSequence===sequence)card.status.textContent=state;if((state==='执行中'||state==='已加入队列')&&!counted){counted=true;card.accepted();if(card.requestSequence===sequence)chain.pendingPromptId=detail?.prompt_id||null;chainEvent('SUBMITTED',{segment:index+1,prompt_id:detail?.prompt_id})}},options);if(result.superseded||card.requestSequence!==sequence){chainEvent('HISTORICAL_SUCCESS',{segment:index+1,prompt_id:result.prompt_id});return}chainEvent('SUCCESS',{segment:index+1,prompt_id:result.prompt_id});chain.pendingPromptId=null;card.status.textContent='上次执行成功';if(resolveVideo){try{await bindSegmentVideo(index,result)}catch(error){card.videoLabel.textContent='执行成功，视频绑定失败：'+error.message}}}
    catch(error){if(card.requestSequence===sequence)card.status.textContent='上次执行失败';throw error}
  }
  function render(value){group=value;let edits=null;try{edits=JSON.parse(localStorage.getItem('h3-six-'+(group?.id||storyId||'manual'))||'null')}catch{}if(group){settings.value=group.global_settings;goal.value=group.goal}cards.forEach((c,i)=>{c.area.value=edits?.[i]??group?.segments[i].english_prompt??'';c.status.textContent=edits?.[i]!==undefined?'已修改':group?.segments[i].status??'未生成';c.card.classList.remove('six-selected');c.use.setAttribute('aria-pressed','false')});selected=-1;controls();root.dispatchEvent(new Event('sixchange'));message.textContent=group?'六段连续剧情草稿已就绪；可选一段执行，或连续执行六段':'可生成六段剧情，也可直接粘贴六段完整Prompt'}
  let runningLabel='未就绪';
  function modelDisplay(){find('.six-model-label').textContent='当前选择：'+(model.selectedOptions[0]?.textContent||model.value)+'；当前后台：'+runningLabel}
  async function updateBackend(){const status=await request('/director/status');runningLabel=status.running_model||status.error||'未就绪';modelDisplay()}
  model.addEventListener('h3-model-display',modelDisplay);
  let preferenceSave=Promise.resolve();
  model.onchange=()=>{modelDisplay();const selected=model.value;preferenceSave=preferenceSave.catch(()=>{}).then(()=>request('/director/preferences',{selected_model:selected})).catch(e=>{message.textContent=e.message})};
  find('.six-generate').onclick=()=>{if(directorBusy)return;directorBusy=true;controls();return operation(async()=>{try{
    const before=cards.map(c=>c.area.value),settingsBefore=settings.value,goalBefore=goal.value;
    message.textContent='正在依次设计第1至第6段…';
    const generated=await request('/director/groups/generate',{global_settings:settingsBefore,delta:goalBefore,model_key:model.value});
    const edited=cards.map((c,i)=>c.area.value!==before[i]?c.area.value:null),newSettings=settings.value,newGoal=goal.value;
    render(generated);
    cards.forEach((c,i)=>{if(edited[i]!==null){c.area.value=edited[i];c.status.textContent='已保留等待期间的手工修改'}});
    if(newSettings!==settingsBefore)settings.value=newSettings;if(newGoal!==goalBefore)goal.value=newGoal;
    persist();await updateBackend();
  }finally{directorBusy=false;controls()}})};
  find('.six-model-start').onclick=async()=>{
    if(backendBusy)return;backendBusy=true;controls();message.textContent='正在检查本地模型后台…';
    try{const result=await request('/director/model/warm',{model_key:model.value});message.textContent=result.message;await updateBackend()}
    catch(error){message.textContent='本地后台检查/唤醒失败：'+(error.message==='NOT_FOUND'?'导演接口尚未加载，请检查当前实例控制台':error.message)}
    finally{backendBusy=false;controls()}
  };
  async function startChain(){
    const first=Number(start.value);
    if(!cards[first].area.value.trim())throw Error(`第${first+1}段Prompt为空`);
    // This explicit batch action enables continuous mode; single-segment execution keeps its selected mode.
    if(!project.value.trim())project.value='H3_SIX_V288';
    if(!/^[\p{L}\p{N}_-]{1,64}$/u.test(project.value.trim()))throw Error('存档项目只能使用1～64位字母、数字、下划线或短横线');
    if(continuous.value!=='on'){continuous.value='on';executionChanged()}
    if(inBatch)return;stopping=false;inBatch=true;chain.state='RUNNING';chain.trace=[];chainEvent('START',{first:first+1});controls();
    try{
      for(let i=first;i<6;i++){
        if(!cards[i].area.value.trim()){start.value=String(i);executionChanged();message.textContent=`第${i+1}段尚未填写，已保留前段结果`;return}
        if(stopping){start.value=String(i);executionChanged();chainEvent('STOPPED',{nextSegment:i+1});message.textContent='连续生成已停止，可从所选起始段重新开始';return}
        chain.currentSegment=i+1;chain.state='RUNNING';
        message.textContent=`连续生成：正在执行第${i+1}/6段；上一段成功后自动推进`;select(i);
        // Freeze only the segment about to submit; later edits remain live.
        try{await runSegment(i,cards[i].area.value,executionOptions(i,first))}
        catch(error){start.value=String(i);executionChanged();chainEvent('FAILED',{segment:i+1,error:error.message});throw error}
      }
      chainEvent('COMPLETE');message.textContent=`第${first+1}～6段已自动连续完成；剧情记忆未自动确认`;
    }finally{inBatch=false;chain.currentSegment=null;chain.pendingPromptId=null}
  }
  find('.six-run-all').onclick=()=>operation(startChain);
  find('.six-memory-confirm').onclick=()=>operation(async()=>{if(!group)throw Error('请先生成一组六段草稿');await request('/director/groups/confirm',{group_id:group.id,prompts:cards.map(c=>c.area.value)});group.status='ACCEPTED';message.textContent='本组六段已手工确认；可输入“继续六段”生成下一组，不会提交视频'});
  find('.six-stop').onclick=()=>{stopping=true;chain.state='STOP_REQUESTED';chainEvent('STOP_REQUESTED');message.textContent='当前段完成后停止；不会提交下一段'};
  try{const catalog=await request('/director/models');for(const item of catalog.models){const option=document.createElement('option');option.value=item.model_key;option.textContent=item.model_label;model.append(option)}const prefs=await request('/director/preferences');model.value=prefs.selected_model||catalog.default_model;modelDisplay();await updateBackend();render(storyId?null:await request('/director/groups/latest'));controls()}catch(e){message.textContent=e.message}
  if(storyId){const layout=document.createElement('style');layout.textContent='.h3-prebake-six .six-prompts{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(3,minmax(0,1fr))}';root.classList.add('h3-prebake-six');root.append(layout)}
  return {cards,get group(){return group},select,runSegment,executionSnapshot,bindSegmentVideo,setSegmentVideo,guideSnapshot:()=>guideControls.map(c=>c.snapshot()),restoreGuide:(index,config,onlyPristine=true)=>guideControls[index]?.restore(config,onlyPristine),refreshGuideFrames:()=>Promise.all(guideControls.map(c=>c.preview())),videoSnapshot:()=>cards.map(c=>c.videoRef?{...c.videoRef}:null),chainSnapshot:()=>({...chain,busy,inBatch,abortRequested:stopping,trace:chain.trace.map(e=>({...e}))})};
}

