// 2026-10-20: validated official prompt or validated 8210 compilation only.
const PROXY = '/h3/compiler';
let stateCache = null, stateAt = 0;

async function cfetch(path, data, timeoutMs) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs || 30000);
  try {
    const response = await fetch(PROXY + path, {
      method: data === undefined ? 'GET' : 'POST',
      headers: {'Content-Type': 'application/json'},
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: ctl.signal,
    });
    const value = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(value.error || ('HTTP ' + response.status));
    return value;
  } catch (error) {
    const reason = error.name === 'AbortError' ? '请求超时' : error.message;
    throw Error(`8210调用失败：${reason}`);
  } finally { clearTimeout(timer); }
}

async function compilerState() {
  if (stateCache && Date.now() - stateAt < 15000) return stateCache;
  stateCache = await cfetch('/api/state', undefined, 8000);
  stateAt = Date.now();
  return stateCache;
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
}

// 从真实提交图快照枚举 Node136 运行时参考（不写死：槽数、文件名都来自快照）。
// 只枚举与计数，不解释用途、不创造职责。
function runtimeRefs(snapshot) {
  const out = snapshot?.output || {};
  const refs = {pictures: [], videos: [], audios: [], soundtracks: [], frames: null, found: false, slots: []};
  for (const node of Object.values(out)) {
    if (node.class_type !== 'MiniMaxH3ReferenceToVideo') continue;
    refs.found = true;
    const inputs = node.inputs || {};
    refs.frames = inputs.length ?? refs.frames;
    const images = [];
    for (const [key, value] of Object.entries(inputs)) {
      let m = key.match(/^ref_images\.ref_image_(\d+)$/);
      if (m && Array.isArray(value)) { images.push([Number(m[1]), String(value[0])]); continue; }
      m = key.match(/^ref_videos\.ref_video_(\d+)$/);
      if (m && Array.isArray(value)) refs.videos.push({slot: Number(m[1]), node: String(value[0])});
      m = key.match(/^ref_audios\.ref_audio_(\d+)$/);
      if (m && Array.isArray(value)) refs.audios.push({slot: Number(m[1]), node: String(value[0])});
      m = key.match(/^ref_video_audios\.ref_video_audio_(\d+)$/);
      if (m && Array.isArray(value)) refs.soundtracks.push({slot: Number(m[1]), node: String(value[0])});
    }
    images.sort((a, b) => a[0] - b[0]);
    for (const [slot, nodeId] of images) { refs.pictures.push({slot, node: nodeId}); refs.slots.push(slot); }
  }
  for (const item of refs.pictures) {
    item.file = out[item.node]?.inputs?.image || '';
  }
  // Core emits index-paired video soundtracks before standalone audio labels.
  refs.audios=[...refs.videos.flatMap(v=>refs.soundtracks.filter(a=>a.slot===v.slot)),...refs.audios];
  function scalar(value,seen=new Set()) {
    if(typeof value==='number'&&Number.isFinite(value))return value;
    if(!Array.isArray(value)||seen.has(String(value[0])))return null;
    const id=String(value[0]),node=out[id];if(!node)return null;seen=new Set([...seen,id]);
    if(node.class_type.startsWith('Primitive'))return Number(node.inputs.value);
    if(node.class_type==='Any Switch (rgthree)')return scalar(Object.entries(node.inputs).sort().find(([,v])=>v!=null)?.[1],seen);
    if(node.class_type==='ComfyMathExpression'&&node.inputs.expression.replace(/\s/g,'')==='max(5,round(a*24))+(5-(max(5,round(a*24))%17))%17') {
      const a=scalar(node.inputs['values.a'],seen);if(a===null)return null;const n=Math.max(5,Math.round(a*24));return n+(5-(n%17)+17)%17;
    }
    return null;
  }
  refs.frames=scalar(refs.frames);
  return refs;
}

function runtimeAssets(refs) {
  const neutral=(kind,label)=>({kind,label,connected:true,role_id:'',purpose:'',note:''});
  return [...refs.pictures.map(r=>neutral('Picture',`ref_image_${r.slot}:${r.file}`)),...refs.videos.map(r=>neutral('Video',`ref_video_${r.slot}:node_${r.node}`)),...refs.audios.map((r,i)=>neutral('Audio',`model_audio_${i+1}:node_${r.node}`))];
}

function validateConnectedReferences(prompt,refs) {
  if(!refs.found)return;
  const caps={Picture:refs.pictures.length,Video:refs.videos.length,Audio:refs.audios.length};
  for(const match of prompt.matchAll(/<(Picture|Video|Audio)\s+(\d+)>/g)) {
    const n=Number(match[2]);
    if(n<1||n>caps[match[1]])throw Error(`提示词引用 <${match[1]} ${n}>，但没有对应实际接线；未提交GPU`);
  }
}

function completeConnectedDefinitions(prompt,refs) {
  const caps={Picture:refs.pictures.length,Video:refs.videos.length,Audio:refs.audios.length};
  const headers=['subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music'];
  if(!headers.every(h=>prompt.includes(h+':')))return prompt;
  const sections={};
  for(let i=0;i<headers.length;i++)sections[headers[i]]=prompt.split(headers[i]+':',2)[1].split(i+1<headers.length?headers[i+1]+':':'\u0000',1)[0].trim();
  const used=Object.entries(sections).filter(([key])=>key!=='subject_definitions').map(([,v])=>v).join('\n');
  const labels=[...new Set([...used.matchAll(/<(Picture|Video|Audio)\s+(\d+)>/g)].map(m=>`${m[1]} ${m[2]}`))];
  let changed=false;
  for(const label of labels){
    const [kind,n]=label.split(' ');if(Number(n)<1||Number(n)>caps[kind])throw Error(`编译稿引用 <${label}>，但没有对应实际接线；未提交GPU`);
    const pattern=new RegExp(`^\\s*<${kind} ${n}>\\s+(?:is|are)\\b`,'m');
    if(!pattern.test(sections.subject_definitions)){
      sections.subject_definitions+=`\n<${label}> is the ${kind.toLowerCase()} reference connected to the model, used as described in the target instructions.`;changed=true;
    }
    if(!sections.retention_analysis.includes(`<${label}>`)){
      sections.retention_analysis+=`\n<${label}>: ${kind==='Audio'?'reference':'fully_preserved'} - the connected reference is used as described in the target instructions.`;changed=true;
    }
  }
  return changed?headers.map(h=>h+':\n'+sections[h]).join('\n\n'):prompt;
}

function durationOf(refs) {
  const frames = Number(refs.frames) || 0;
  if (frames <= 0) return null;
  return Math.max(4, Math.min(15, Math.round(frames / 24)));
}

// 角色匹配：按角色名/英文名/别名在文本中的出现顺序（确定性，不猜测）。仅用于编译，不用于拦截。
function matchRoles(text, roles) {
  const hits = [];
  for (const role of roles) {
    const names = [role.name, role.name_en, ...(role.aliases || [])].filter(Boolean);
    let best = -1;
    for (const name of names) {
      const at = text.indexOf(name);
      if (at >= 0 && (best < 0 || at < best)) best = at;
    }
    if (best >= 0) hits.push({id: role.id, at: best});
  }
  hits.sort((a, b) => a.at - b.at);
  return hits.map(h => h.id);
}

// Only explicit dialogue markup is lifted into the frozen compiler's dialogue
// fields. Speaker identity comes from a real named role in the preceding text.
function dialogueFields(text, roles) {
  const dialogues=[];
  const action=text.replace(/<d>\[([^\]]+)\]([\s\S]*?)<\/d>/g,(block,language,words,offset)=>{
    const before=text.slice(0,offset);
    const candidates=roles.map(role=>({role,at:Math.max(...[role.name,role.name_en,...(role.aliases||[])].filter(Boolean).map(name=>before.lastIndexOf(name)))})).filter(r=>r.at>=0).sort((a,b)=>b.at-a.at);
    if(!candidates.length || (candidates[1]&&candidates[0].at===candidates[1].at))throw Error('台词说话人不明确，请在台词前写出真实角色名；未提交GPU');
    dialogues.push({id:`D${dialogues.length+1}`,speaker_role_id:candidates[0].role.id,zh_text:words.trim(),language:language.trim(),shot_index:1});
    return '';
  });
  if(/<\/?d>/.test(action))throw Error('台词必须使用完整 <d>[Chinese] 原文</d> 标签；未提交GPU');
  return {action_zh:action,dialogues};
}

export async function compileForSubmission(rawText, index, options, update, snapshot) {
  const text = String(rawText ?? '');
  if (!text.trim()) throw Error('提示词为空，未提交GPU');
  const refs = runtimeRefs(snapshot);
  const tag = `H3_8207_S${index + 1}_${String(options.submission_id || '').slice(0, 8)}`;
  const head = `第${index + 1}段`;
  // 参考编号只提示、不阻断：槽位不连续/重复仅作中性提示。
  const slots = [...refs.slots].sort((a, b) => a - b);
  if (slots.some((s, i) => s !== i)) {
    update(`${head}提示：参考图槽位编号为 [${slots.join(',')}]（非连续），按实际接线送达模型，不影响提交`);
  }
  update(`${head}：运行时参考（实际接线）图${refs.pictures.length}张/视频${refs.videos.length}路/音频${refs.audios.length}路——用途由您决定，编译器不做强制解释`);

  let state = null;
  try {
    state = await compilerState();
  } catch (error) {
    throw Error(`${head}：独立编译器8210不可达（${error.message}），未提交GPU`);
  }
  const project = state.project || state;
  const roles = project.roles || [];
  const version = project.compiler_version || 'unknown';
  const activeId = project.active_segment_id;
  const duration = durationOf(refs) ?? (refs.found?null:8);
  if(duration===null)throw Error(`${head}：无法解析当前工作流的实际帧数，未提交GPU`);

  let segmentId = null;
  try {
    const added = await cfetch('/api/segment/add', {title: tag, mode: 'Ref2VA', duration}, 15000);
    segmentId = added.segment.id;
    // 中性入档：purpose 留空，不预设任何人脸/服装/场景解释
    const assets = runtimeAssets(refs);
    await cfetch('/api/segment/update', {id: segmentId, assets}, 15000);
  } catch (error) {
    throw Error(`${head}：编译器留档不可用（${error.message}），未提交GPU`);
  }

  try {
    // 1) 原样放行：原文已通过官方确定性校验 → 不重复编译，保留原哈希
    let pass = null;
    try { pass = await cfetch('/api/validate', {id: segmentId, prompt: text}, 30000); } catch (error) { pass = null; }
    if (pass?.report?.valid) {
      validateConnectedReferences(text,refs);
      try { await cfetch('/api/segment/update', {id: segmentId, action_zh: text, final_edited_prompt: text}, 15000); } catch { /* 留档尽力 */ }
      const sha = await sha256Hex(text);
      update(`${head}：原文已符合官方格式，原样提交（SHA256 ${sha.slice(0, 12)}…，留档段：${tag}）`);
      return text;
    }
    const roleIds = matchRoles(text, roles);
    if (!roleIds.length) throw Error(`${head}：未匹配到真实角色档案，请明确角色名；未提交GPU`);
    update(`${head}：调用独立编译器${version}（Ref2VA/${duration}s）`);
    const fields=dialogueFields(text,roles);
    let compiled = null, compileError = '';
    try {
      compiled = await cfetch('/api/compile', {
        id: segmentId, ...fields, role_ids: roleIds,
        task_types: ['reference generation'], assets: runtimeAssets(refs),
      }, 240000);
    } catch (error) { compileError = error.message; }
    if(compiled?.ok&&typeof compiled.prompt==='string'){
      validateConnectedReferences(compiled.prompt,refs);
      const completed=completeConnectedDefinitions(compiled.prompt,refs);
      if(completed!==compiled.prompt){
        const checked=await cfetch('/api/validate',{id:segmentId,prompt:completed},30000);
        compiled={...compiled,prompt:completed,report:checked.report};
        if(checked.report?.valid){
          await cfetch('/api/segment/update',{id:segmentId,final_edited_prompt:completed},15000);
          update(`${head}：8207已补齐实际参考声明，8210再次官方校验通过`);
        }
      }
    }
    const upstreamErrors = (compiled?.report?.checks || [])
      .filter(c => c.severity === 'error').map(c => c.message);
    const failures = [...(compiled?.errors || []), ...upstreamErrors];
    if (!(compiled?.ok && compiled?.report?.valid)) {
      const reason = compileError || failures.join('；') || '未知原因';
      throw Error(`${head}：编译或官方校验未通过（${reason}），未提交GPU`);
    }
    for(const line of fields.dialogues){
      if(!compiled.prompt.includes(`<d>[${line.language}] ${line.zh_text}</d>`))throw Error(`${head}：编译稿未逐字保留台词，未提交GPU`);
    }
    // 3) 编译成功 → 编译稿提交；运行时参考中性留痕（不写入文本的参考仅提示）
    const notes = [];
    if (refs.videos.length) notes.push(`已登记实际参考视频${refs.videos.length}路；用途按您的描述`);
    if (refs.audios.length) notes.push(`已登记实际参考音频${refs.audios.length}路；用途按您的描述`);
    for (const note of notes) update(`${head}提示：${note}`);
    const sha = await sha256Hex(compiled.prompt);
    update(`${head}：已采用编译稿提交（SHA256 ${sha.slice(0, 12)}…，编译器${version}，留档段：${tag}）`);
    return compiled.prompt;
  } finally {
    try { if (activeId) await cfetch('/api/segment/select', {id: activeId}, 15000); } catch { /* 恢复激活段失败不影响提交 */ }
    // 临时段保留作为原稿/编译稿双存留档（标题含提交标识），不删除。
  }
}

// Explicit, non-GPU preview. The six-prompt source textarea is never changed.
// Only roles named in the user's raw prompt are passed to the frozen compiler.
// Real connected pictures are forwarded neutrally; no duty or Subject binding is inferred.
export async function previewCompilePrompt(rawText, index, snapshot = null) {
  const raw = String(rawText ?? ''), messages = [];
  const refs = runtimeRefs(snapshot);
  const refSummary = {pictures: refs.pictures.length, videos: refs.videos.length, audios: refs.audios.length};
  try {
    const used = await compileForSubmission(raw,index,{submission_id:crypto.randomUUID()},message=>messages.push(message),snapshot);
    return {status:used===raw?'VALIDATED':'COMPILED',raw,used,compiled:used===raw?'':used,refSummary,reason:messages.join('\n')+'\n仅预览，未提交GPU'};
  } catch(error) {
    return {status:'BLOCKED',raw,used:'',compiled:'',refSummary,reason:error.message};
  }
}
