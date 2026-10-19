// H3 六段独立编译接线（8207侧最小适配，2026-10-19；收口修订 2026-10-19b）
//
// 链路：手写原稿 → 运行时参考中性枚举 → 8210 独立编译（尽力） → 官方校验（尽力）
//       → 编译成功用编译稿；编译不可用/失败/超时一律原稿直通 → PreBake → 生成提交。
//
// 收口原则（2026-10-19b，用户指令）：
//   * 编译器只负责改进与提示，不决定用户能否生成：
//       - 中文不规范 → 照常提交；
//       - 无人物角色定义 → 照常提交；
//       - 8210 离线/失败/超时 → 自动使用原稿提交（并显示真实原因）；
//       - 不重新引入任何 V28 式格式阻断。
//   * 参考图职责完全由用户决定：不预设人脸/服装/场景，不要求绑定 Subject，
//     不要求固定数量/顺序/组合；编号异常只提示，不阻断。
//   * 保留 8210 冻结源码零改动（仅 HTTP 调用，经 /h3/compiler 同源代理）。
//   * AI 自动导演不参与本链路（本模块不调用任何导演服务）。
//   * 系统级安全检查与真实执行依赖检查在执行链其它环节，保持不变。

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
  const refs = {pictures: [], videos: [], audios: [], frames: null, found: false, slots: []};
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
    }
    images.sort((a, b) => a[0] - b[0]);
    for (const [slot, nodeId] of images) { refs.pictures.push({slot, node: nodeId}); refs.slots.push(slot); }
  }
  for (const item of refs.pictures) {
    item.file = out[item.node]?.inputs?.image || '';
  }
  return refs;
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

export async function compileForSubmission(rawText, index, options, update, snapshot) {
  const text = String(rawText ?? '');
  if (!text.trim()) return text;
  const refs = runtimeRefs(snapshot);
  const tag = `H3_8207_S${index + 1}_${String(options.submission_id || '').slice(0, 8)}`;
  const head = `第${index + 1}段`;
  // 参考编号只提示、不阻断：槽位不连续/重复仅作中性提示。
  const slots = [...refs.slots].sort((a, b) => a - b);
  if (slots.some((s, i) => s !== i + 1)) {
    update(`${head}提示：参考图槽位编号为 [${slots.join(',')}]（非连续），按实际接线送达模型，不影响提交`);
  }
  update(`${head}：运行时参考（实际接线）图${refs.pictures.length}张/视频${refs.videos.length}路/音频${refs.audios.length}路——用途由您决定，编译器不做强制解释`);

  // 8210 不可达（离线/超时）→ 原稿直通
  let state = null;
  try {
    state = await compilerState();
  } catch (error) {
    update(`${head}提示：独立编译器8210不可达（${error.message}），按原稿提交（编译器只提示，不拦截）`);
    return text;
  }
  const project = state.project || state;
  const roles = project.roles || [];
  const version = project.compiler_version || 'unknown';
  const activeId = project.active_segment_id;
  const duration = durationOf(refs) ?? 8;

  let segmentId = null;
  try {
    const added = await cfetch('/api/segment/add', {title: tag, mode: 'Ref2VA', duration}, 15000);
    segmentId = added.segment.id;
    // 中性入档：purpose 留空，不预设任何人脸/服装/场景解释
    const assets = refs.pictures.map(r => ({
      kind: 'Picture', label: `ref_image_${r.slot}:${r.file}`,
      connected: true, role_id: '', purpose: '', note: '',
    }));
    await cfetch('/api/segment/update', {id: segmentId, assets}, 15000);
  } catch (error) {
    update(`${head}提示：编译器留档不可用（${error.message}），按原稿提交`);
    return text;
  }

  try {
    // 1) 原样放行：原文已通过官方确定性校验 → 不重复编译，保留原哈希
    let pass = null;
    try { pass = await cfetch('/api/validate', {id: segmentId, prompt: text}, 30000); } catch (error) { pass = null; }
    if (pass?.report?.valid) {
      try { await cfetch('/api/segment/update', {id: segmentId, action_zh: text, final_edited_prompt: text}, 15000); } catch { /* 留档尽力 */ }
      const sha = await sha256Hex(text);
      update(`${head}：原文已符合官方格式，原样提交（SHA256 ${sha.slice(0, 12)}…，留档段：${tag}）`);
      return text;
    }
    // 2) 独立编译（尽力）：无角色/编译失败/校验失败 → 原稿直通，只提示原因
    const roleIds = matchRoles(text, roles);
    if (!roleIds.length) {
      try { await cfetch('/api/segment/update', {id: segmentId, action_zh: text, final_edited_prompt: text}, 15000); } catch { /* 留档尽力 */ }
      const sha = await sha256Hex(text);
      update(`${head}提示：文本未匹配到编译器角色档案，编译器无法改写——按原稿提交（SHA256 ${sha.slice(0, 12)}…，留档段：${tag}）`);
      return text;
    }
    update(`${head}：调用独立编译器${version}（Ref2VA/${duration}s）`);
    let compiled = null, compileError = '';
    try {
      compiled = await cfetch('/api/compile', {
        id: segmentId, action_zh: text, role_ids: roleIds,
        task_types: ['reference generation'], assets: refs.pictures.map(r => ({
          kind: 'Picture', label: `ref_image_${r.slot}:${r.file}`,
          connected: true, role_id: '', purpose: '', note: '',
        })),
      }, 240000);
    } catch (error) { compileError = error.message; }
    const upstreamErrors = (compiled?.report?.checks || [])
      .filter(c => c.severity === 'error').map(c => c.message);
    const failures = [...(compiled?.errors || []), ...upstreamErrors];
    if (!(compiled?.ok && compiled?.report?.valid)) {
      const reason = compileError || failures.join('；') || '未知原因';
      try { await cfetch('/api/segment/update', {id: segmentId, action_zh: text, final_edited_prompt: text}, 15000); } catch { /* 留档尽力 */ }
      const sha = await sha256Hex(text);
      update(`${head}提示：编译或官方校验未通过（${reason}）——按原稿提交（SHA256 ${sha.slice(0, 12)}…，留档段：${tag}）`);
      return text;
    }
    // 3) 编译成功 → 编译稿提交；运行时参考中性留痕（不写入文本的参考仅提示）
    const notes = [];
    if (refs.videos.length) notes.push(`参考视频${refs.videos.length}路未写入编译稿文本（参考仍经工作流节点送达模型）`);
    if (refs.audios.length) notes.push(`参考音频${refs.audios.length}路未写入编译稿文本（同上）`);
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
  const raw = String(rawText ?? '');
  const state = await cfetch('/api/state', undefined, 8000);
  const project = state.project || state;
  const roles = project.roles || [];
  const roleIds = matchRoles(raw, roles);
  const refs = runtimeRefs(snapshot);
  const assets = refs.pictures.map(r => ({kind: 'Picture', label: `ref_image_${r.slot}:${r.file}`, connected: true, role_id: '', purpose: '', note: ''}));
  if (!roleIds.length) {
    return {
      status: 'UNCHANGED', raw, used: raw, compiled: '', refSummary: {pictures: refs.pictures.length, videos: refs.videos.length, audios: refs.audios.length},
      reason: '8210已响应 /api/state，但原稿没有明确匹配到角色档案；未调用 /api/compile。没有结构化角色信息可供编译，预览拟按原稿直通。',
      compilerResponse: {ok: state.ok === true, endpoint: '/api/state', compiler_version: project.compiler_version || 'unknown'},
    };
  }

  const previousActive = project.active_segment_id || null;
  let previewId = null;
  try {
    const added = await cfetch('/api/segment/add', {
      title: `H3_8207_PREVIEW_S${index + 1}_${crypto.randomUUID().slice(0, 8)}`,
      mode: 'Ref2VA', duration: 8,
    }, 15000);
    previewId = added.segment?.id;
    if (!previewId) throw Error('8210未返回预览段ID');
    await cfetch('/api/segment/update', {
      id: previewId, action_zh: raw, role_ids: roleIds,
      task_types: ['reference generation'], assets,
    }, 15000);
    const result = await cfetch('/api/compile', {
      id: previewId, action_zh: raw, role_ids: roleIds,
      task_types: ['reference generation'], assets,
    }, 240000);
    const checks = (result.report?.checks || []).filter(c => c.severity === 'error').map(c => c.message);
    const errors = [...(result.errors || []), ...checks];
    if (result.ok && result.report?.valid && typeof result.prompt === 'string' && result.prompt.length) {
      return {
        status: 'COMPILED', raw, compiled: result.prompt, used: result.prompt, refSummary: {pictures: refs.pictures.length, videos: refs.videos.length, audios: refs.audios.length},
        reason: `8210 /api/compile 与官方格式校验通过；预览拟用编译稿（尚未提交生成）。角色依据来自原稿显式点名：${roleIds.join(', ')}。`,
        compilerResponse: result,
      };
    }
    return {
      status: 'RAW_FALLBACK', raw, compiled: result.prompt || '', used: raw, refSummary: {pictures: refs.pictures.length, videos: refs.videos.length, audios: refs.audios.length},
      reason: errors.join('；') || '8210返回编译失败或官方格式校验未通过，按原稿直通。',
      compilerResponse: result,
    };
  } catch (error) {
    return {
      status: 'RAW_FALLBACK', raw, compiled: '', used: raw, refSummary: {pictures: refs.pictures.length, videos: refs.videos.length, audios: refs.audios.length},
      reason: `8210预览调用/编译失败：${error.message}；按原稿直通。`,
      compilerResponse: {ok: false, error: error.message},
    };
  } finally {
    if (previewId) {
      try { await cfetch('/api/segment/delete', {id: previewId}, 15000); } catch { /* retain response; report cleanup failure in server logs */ }
    }
    if (previousActive) {
      try { await cfetch('/api/segment/select', {id: previousActive}, 15000); } catch { /* do not affect caller */ }
    }
  }
}
