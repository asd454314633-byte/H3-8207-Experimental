import { app } from '../../../scripts/app.js';

const node = id => app.graph?.getNodeById(id);
const widget = (id, name) => node(id)?.widgets?.find(w => w.name === name);
function set(id, name, value) {
  const w = widget(id, name);
  if (!w) return;
  if (w.value === value) return;
  w.value = value;
  w.callback?.(value);
  app.graph?.setDirtyCanvas(true, true);
}
function mirror() {
  if (!node(159)?.properties?.h3_audio_upgrade) return;
  const ref = String(widget(647, '生成模式')?.value || '').startsWith('多参考');
  for (let i = 1; i <= 2; i++) set(1042, `audio${i}_enabled`, ref && !!widget(150, `启用参考音频${i}`)?.value);
  const soundtrack = !!widget(1042, 'soundtrack_enabled')?.value;
  if (soundtrack && (!ref || !widget(150, '启用参考视频')?.value)) {
    throw new Error('视频音轨参考需要先开启多参考生成和参考视频。');
  }
  if (!ref && widget(1042, 'audio3_enabled')?.value) throw new Error('独立音色参考3仅用于多参考生成。');
  if (!ref && String(widget(1041, 'profile')?.value).includes('Stock20')) throw new Error('Stock20 音色档需要选择多参考生成。');
  if (widget(1043, 'enabled')?.value && widget(1045, 'mode')?.value !== '关闭') {
    throw new Error('指定音轨锁定与音频精修不能同时开启。');
  }
  if (widget(1043, 'enabled')?.value && String(widget(992, '接续生产')?.value || widget(992, '接续模式')?.value || node(992)?.widgets?.[0]?.value || '').startsWith('开启')) {
    throw new Error('指定音轨模式请关闭接续生产，避免接续裁头剪掉原音轨开头。');
  }
}
function el(tag, text) {
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  return e;
}
function bind(section, label, id, name) {
  const w = widget(id, name);
  if (!w) return;
  const row = el('label'); row.style.cssText = 'display:flex;gap:10px;align-items:center;margin:7px 0;';
  const title = el('span', label); title.style.minWidth = '150px'; row.append(title);
  let input;
  if (w.type === 'toggle') {
    input = el('input'); input.type = 'checkbox'; input.checked = !!w.value;
    input.onchange = () => set(id, name, input.checked);
  } else if (Array.isArray(w.options?.values)) {
    input = el('select');
    w.options.values.forEach(v => { const o = el('option', v); o.value = v; input.append(o); });
    input.value = w.value;
    input.onchange = () => set(id, name, input.value);
  } else {
    input = el('input'); input.type = typeof w.value === 'number' ? 'number' : 'text'; input.value = w.value;
    input.onchange = () => set(id, name, input.type === 'number' ? Number(input.value) : input.value);
    if (w.options?.min != null) input.min = w.options.min;
    if (w.options?.max != null) input.max = w.options.max;
    if (w.options?.step != null) input.step = w.options.step;
  }
  input.style.cssText = 'flex:1;min-width:0;background:#17362a;color:#f3f6f5;padding:6px;border:1px solid #47886d;';
  input.addEventListener('pointerdown', e => e.stopPropagation()); row.append(input); section.append(row);
}
function upload(section, label, id) {
  const row = el('div'); row.style.margin = '8px 0';
  const btn = el('button', label); const value = el('span', String(widget(id, 'audio')?.value || '未上传'));
  const file = el('input'); file.type = 'file'; file.accept = 'audio/*,.wav,.mp3,.flac,.ogg,.m4a'; file.hidden = true;
  btn.onclick = e => { e.stopPropagation(); file.click(); };
  file.onchange = async () => {
    const f = file.files?.[0]; if (!f) return;
    btn.disabled = true;
    try {
      const form = new FormData(); form.append('image', f); form.append('type', 'input');
      const response = await fetch('/upload/image', { method: 'POST', body: form });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); const path = (data.subfolder ? data.subfolder + '/' : '') + data.name;
      const w = widget(id, 'audio');
      if (w && Array.isArray(w.options?.values) && !w.options.values.includes(path)) w.options.values.push(path);
      set(id, 'audio', path); value.textContent = path;
    } catch (e) { value.textContent = '上传失败：' + e.message; }
    finally { btn.disabled = false; }
  };
  row.append(btn, file, value); section.append(row);
}
function install() {
  const dashboard = node(159);
  if (!dashboard?.properties?.h3_audio_upgrade) return;
  const panel = dashboard.__h3DashboardV3Panel;
  if (!panel || panel.querySelector('[data-h3-audio-upgrade]')) return;
  const section = el('section'); section.dataset.h3AudioUpgrade = '1';
  section.style.cssText = 'padding:12px;border:1px solid #47886d;border-radius:8px;margin:12px 0;color:#e9f4ee;';
  section.append(el('h3', '音频专项升级'));
  bind(section, '音频质量档', 1041, 'profile');
  bind(section, '音频精修（试验）', 1045, 'mode');
  bind(section, '追加精修步数', 1045, 'steps');
  bind(section, '精修去噪强度', 1045, 'denoise');
  section.append(el('p', '先生成满意画面，再选“仅精修已缓存一采”。读取本工作流最近一次一采缓存，不启动一采；保持原提示词和尺寸。缓存会由下一次一采覆盖。'));
  bind(section, '指定音轨驱动', 1043, 'enabled');
  upload(section, '上传最终 WAV / TTS', 1048);
  section.append(el('p', '此音轨与音色参考独立：原音保留，短于视频时仅补片尾静音，过长时报错。口型同步效果仍取决于模型。'));
  bind(section, '启用音色参考3', 1042, 'audio3_enabled');
  upload(section, '上传音色参考3', 1047);
  bind(section, '音色3的角色用途', 1042, 'role3');
  bind(section, '参考视频自带音轨', 1042, 'soundtrack_enabled');
  section.append(el('p', '独立音色单段2～15秒，启用参考音频合计≤15秒。提示词 <Audio 1/2/3> 对应独立音色槽位，系统自动映射实际编号；视频音轨写 <VideoSoundtrack>。'));
  const start = el('button', '使用当前音频设置生成 / 精修');
  start.onclick = async e => {
    e.stopPropagation();
    try { await app.queuePrompt(0, 1); }
    catch (err) { app.extensionManager?.toast?.add({severity:'error',summary:'音频设置',detail:err.message}); }
  };
  section.append(start);
  panel.insertBefore(section, panel.children[1] || null);
}
app.registerExtension({
  name: 'H3.AudioUpgrade.Candidate',
  setup() {
    // Preflight validation does not rewrite legacy routing modes.
    const original = app.queuePrompt;
    app.queuePrompt = async function (...args) { mirror(); return await original.apply(this, args); };
    const serialize = app.graphToPrompt;
    app.graphToPrompt = async function (...args) { mirror(); return await serialize.apply(this, args); };
  },
  afterConfigureGraph() {
    install();
    // Legacy dashboard mounts asynchronously; one bounded retry.
    setTimeout(install, 500);
  },
  nodeCreated(n) {
    if (n.id === 159) setTimeout(install, 500);
  }
});
