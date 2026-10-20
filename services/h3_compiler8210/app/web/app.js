/* H3 官方中文提示词编译器 —— 前端逻辑（原生 JS，无外部依赖） */
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let ST = { project: null, spec: null, translation: null, presets: [], perf: {} };
let LAST = { prompt: "", report: null, ambiguous: [] };

/* ------------------------------------------------------------------ 工具 */
async function api(path, body) {
  const opt = body === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) };
  const res = await fetch(path, opt);
  const data = await res.json().catch(() => ({ ok: false, error: "响应不是合法 JSON" }));
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
let toastTimer = null;
function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.style.background = isErr ? "#b3261e" : "#1b2430";
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), isErr ? 5200 : 2600);
}
const seg = () => (ST.project.segments.find((s) => s.id === ST.project.active_segment_id) || ST.project.segments[0]);

/* ------------------------------------------------------------------ 初始化 */
async function init() {
  try {
    const st = await api("/api/state");
    ST = st;
    renderEngine();
    renderTabs();
    renderPreset();
    renderRoles();
    renderSegment();
    await refreshVersions();
    await refreshPrompts();
  } catch (e) { toast("初始化失败：" + e.message, true); }
}

function renderEngine() {
  const t = ST.translation || {};
  const ok = !!t.available;
  $("#engineDot").className = "dot " + (ok ? "ok" : "bad");
  $("#engineText").textContent = ok
    ? `离线翻译引擎：${t.provider}（CPU，就绪）`
    : `翻译引擎不可用：${t.error || "未安装离线模型"}（仍可编译，未翻译字段将保留中文）`;
}

/* ------------------------------------------------------------------ 段标签 */
function renderTabs() {
  const box = $("#segmentTabs");
  box.innerHTML = ST.project.segments.map((s, i) =>
    `<button class="tab${s.id === ST.project.active_segment_id ? " active" : ""}" data-seg="${esc(s.id)}">`
    + `${esc(s.title || "第" + (i + 1) + "段")}<span style="opacity:.6;margin-left:6px">${esc(s.mode)}</span></button>`
  ).join("") + `<button class="tab" id="tabAdd">+ 新建一段</button>`;
  $$("#segmentTabs .tab[data-seg]").forEach((b) => b.onclick = async () => {
    const st = await api("/api/segment/select", { id: b.dataset.seg });
    ST.project = st.project;
    renderTabs(); renderPreset(); renderRoles(); renderSegment();
  });
  $("#tabAdd").onclick = async () => {
    const st = await api("/api/segment/add", { mode: seg().mode, duration: seg().duration });
    ST.project = st.project;
    renderTabs(); renderPreset(); renderRoles(); renderSegment(); renderOutput(null);
    toast("已新建一段（共用当前参考预设）");
  };
}

/* ------------------------------------------------------------------ A 预设 */
function renderPreset() {
  const p = ST.project.preset || {};
  $("#preset-name").value = p.name || "";
  $("#preset-style").value = p.style_terms || "";
  $("#preset-scene").value = p.scene || "";
  $("#preset-people").value = p.people_ref || "";
  $("#preset-body").value = p.body_costume_ref || "";
  $("#preset-voice").value = p.voice_ref || "";
  $("#preset-camera").value = p.camera_style || "";
  $("#preset-sound").value = p.sound_style || "";
  $("#preset-list").innerHTML = `<option value="">— 读取已保存预设 —</option>`
    + (ST.presets || []).map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
}
function presetPayload() {
  return {
    name: $("#preset-name").value.trim() || "默认参考预设",
    style_terms: $("#preset-style").value.trim(),
    scene: $("#preset-scene").value.trim(),
    people_ref: $("#preset-people").value.trim(),
    body_costume_ref: $("#preset-body").value.trim(),
    voice_ref: $("#preset-voice").value.trim(),
    camera_style: $("#preset-camera").value.trim(),
    sound_style: $("#preset-sound").value.trim(),
  };
}
async function savePreset(silent) {
  const st = await api("/api/preset/save", { preset: presetPayload() });
  ST.presets = st.presets;
  ST.project.preset = presetPayload();
  renderPreset();
  if (!silent) toast("预设已保存：" + st.name);
}

/* ------------------------------------------------------------------ B 角色 */
function renderRoles() {
  const box = $("#roleList");
  if (!ST.project.roles.length) { box.innerHTML = `<div class="empty">还没有角色，点右上「+ 添加角色」。</div>`; return; }
  const cur = seg();
  box.innerHTML = ST.project.roles.map((r) => {
    const present = cur.role_ids.includes(r.id);
    const v = r.default_voice || {};
    return `<div class="role${present ? " present" : ""}" data-role="${esc(r.id)}">
      <div class="rolehead">
        <label class="check"><input type="checkbox" data-presence="${esc(r.id)}" ${present ? "checked" : ""}>本段出场</label>
        <span class="rid">${esc(r.id)}</span>
        <span class="rolesum">${esc(r.name || "（未命名）")}${r.name_en ? " / " + esc(r.name_en) : ""}
          ${resumen(r, present, cur)}</span>
        <button class="mini" data-expand="${esc(r.id)}">编辑</button>
        <button class="mini danger" data-delrole="${esc(r.id)}">删除档案</button>
      </div>
      <div class="rolemore">
        <div class="row2">
          <label>姓名<input data-f="name" value="${esc(r.name)}"></label>
          <label>英文名（留空则中文名逐字保留）<input data-f="name_en" value="${esc(r.name_en)}"></label>
        </div>
        <label>别名（逗号分隔，用于确定性指代匹配）<input data-f="aliases" value="${esc((r.aliases || []).join("，"))}"></label>
        <label>外观描述（中文）<textarea data-f="appearance" rows="2">${esc(r.appearance)}</textarea></label>
        <div class="row2">
          <label>容貌参考<input data-f="face_ref" value="${esc(r.face_ref)}"></label>
          <label>身体及服装参考<input data-f="body_ref" value="${esc(r.body_ref)}"></label>
        </div>
        <h4>默认音色（永久声音身份，情绪变化不会修改它）</h4>
        <div class="grid4">
          <label>音高<input data-v="pitch" value="${esc(v.pitch || "")}"></label>
          <label>音色<input data-v="timbre" value="${esc(v.timbre || "")}"></label>
          <label>质感<input data-v="texture" value="${esc(v.texture || "")}"></label>
          <label>口音<input data-v="accent" value="${esc(v.accent || "")}"></label>
        </div>
        <div class="row2">
          <label>默认语速<input data-v="rate" value="${esc(v.rate || "")}"></label>
          <label>默认音量<input data-v="volume" value="${esc(v.volume || "")}"></label>
        </div>
        <label>可选声音参考文件<input data-f="audio_ref" value="${esc(r.audio_ref)}"></label>
      </div>
    </div>`;
  }).join("");

  $$("[data-presence]").forEach((cb) => cb.onchange = async () => {
    const id = cb.dataset.presence;
    const ids = new Set(seg().role_ids);
    cb.checked ? ids.add(id) : ids.delete(id);
    // 保持永久编号顺序，避免出场顺序影响 Subject 映射
    const ordered = ST.project.roles.map((r) => r.id).filter((x) => ids.has(x));
    const st = await api("/api/segment/update", { id: seg().id, role_ids: ordered });
    ST.project = st.project; renderRoles(); renderSegment();
  });
  $$("[data-expand]").forEach((b) => b.onclick = () => {
    b.closest(".role").classList.toggle("open");
  });
  $$("[data-delrole]").forEach((b) => b.onclick = async () => {
    if (!confirm("确定从角色库删除该角色档案？会同时从各段出场名单移除。")) return;
    const st = await api("/api/role/delete", { id: b.dataset.delrole });
    ST.project = st.project; renderRoles(); renderSegment(); renderTabs();
    toast("角色档案已删除");
  });
  $$("#roleList input[data-f], #roleList textarea[data-f]").forEach((el) => {
    el.onchange = () => updateRole(el.closest("[data-role]").dataset.role, el.dataset.f, el.value);
  });
  $$("#roleList input[data-v]").forEach((el) => {
    el.onchange = () => updateRoleVoice(el.closest("[data-role]").dataset.role, el.dataset.v, el.value);
  });
}
function resumen(r, present, cur) {
  const n = cur.dialogues.filter((d) => d.speaker_role_id === r.id && (d.zh_text || "").trim()).length;
  return `<span style="color:var(--ink-3);font-size:11.5px">
    ｜容貌参考 ${r.face_ref ? "已填" : "—"}｜音色 ${r.default_voice && Object.values(r.default_voice).some(Boolean) ? "已填" : "—"}
    ｜本段台词 ${n} 条</span>`;
}
async function updateRole(id, field, value) {
  const st = await api("/api/role/update", { id, [field]: field === "aliases"
    ? value.split(/[，,、\s]+/).filter(Boolean) : value });
  ST.project = st.project; renderRoles(); renderSegment();
}
async function updateRoleVoice(id, field, value) {
  const role = ST.project.roles.find((r) => r.id === id);
  const voice = Object.assign({}, role.default_voice || {}, { [field]: value });
  const st = await api("/api/role/update", { id, default_voice: voice });
  ST.project = st.project; renderSegment();
}

/* ------------------------------------------------------------------ C 本段 */
function renderSegment() {
  const s = seg();
  $("#seg-mode").innerHTML = ST.spec.modes.map((m) =>
    `<option value="${esc(m)}"${m === s.mode ? " selected" : ""}>${esc(ST.spec.mode_labels[m] || m)}</option>`).join("");
  $("#seg-duration").value = s.duration;
  $("#seg-title").value = s.title || "";
  $("#seg-action").value = s.action_zh || "";
  $("#seg-camera").value = s.camera_zh || "";
  $("#seg-soundscape").value = s.soundscape_zh || "";
  $("#seg-music").value = s.music_zh || "";
  $("#seg-extra").value = s.extra_zh || "";
  $("#seg-inherit").value = s.inherit_prev_end_state || "";
  renderDialogues();
  renderAssets();
  renderShots();
  renderRetention();
  renderTaskTypes();
  renderRelations();
}

async function patchSegment(patch, rerender) {
  const st = await api("/api/segment/update", Object.assign({ id: seg().id }, patch));
  ST.project = st.project;
  if (rerender) renderSegment();
}

/* ---- 台词 ---- */
async function addDialogue() {
  const s = seg();
  const ids = s.dialogues.map((d) => d.id);
  let n = 1; ids.forEach((i) => { const m = /^D(\d+)$/.exec(i); if (m) n = Math.max(n, +m[1] + 1); });
  const rows = s.dialogues.concat([{
    id: "D" + String(n).padStart(2, "0"),
    speaker_role_id: s.role_ids[0] || "", zh_text: "",
    emotion: "平静", tone: "", rate: "", volume: "", pause: "", breath: "",
    delivery: "onscreen", language: "Chinese", group: "", shot_index: 1,
  }]);
  await patchSegment({ dialogues: rows }, true);
}
function renderDialogues() {
  const s = seg(), box = $("#dialogueList");
  if (!s.dialogues.length) { box.innerHTML = `<div class="empty">还没有台词。点「+ 新增一条台词」。</div>`; return; }
  const opts = (sel) => s.role_ids.map((rid) => {
    const r = ST.project.roles.find((x) => x.id === rid);
    return r ? `<option value="${esc(rid)}"${rid === sel ? " selected" : ""}>${esc(r.id)} ${esc(r.name || "（未命名）")}</option>` : "";
  }).join("");
  const emo = ["平静", "温柔", "疲惫", "愤怒", "悲伤", "开心", "兴奋", "冷淡", "惊讶", "紧张", "戏谑"];
  const opt = (list, cur) => [`<option value="">—</option>`].concat(
    list.map((x) => `<option value="${esc(x)}"${x === cur ? " selected" : ""}>${esc(x)}</option>`)).join("");
  box.innerHTML = s.dialogues.map((d, i) => `
    <div class="dlg" data-dlg="${esc(d.id)}">
      <div class="dlghead">
        <b style="font-size:12.5px;color:var(--accent)">${esc(d.id)}</b>
        <label class="check">说话人
          <select data-d="speaker_role_id">${opts(d.speaker_role_id)}</select></label>
        <label class="check">画内/画外
          <select data-d="delivery">
            <option value="onscreen"${d.delivery === "onscreen" ? " selected" : ""}>画内说话</option>
            <option value="offscreen"${d.delivery === "offscreen" ? " selected" : ""}>画外音（旁白）</option>
          </select></label>
        <span style="flex:1"></span>
        <button class="mini danger" data-deldlg="${esc(d.id)}">删除</button>
      </div>
      <label>中文台词（逐字保留，不翻译）<textarea data-d="zh_text" rows="2">${esc(d.zh_text)}</textarea></label>
      <div class="grid5">
        <label>情绪<select data-d="emotion">${opt(emo, d.emotion)}</select></label>
        <label>语气<input data-d="tone" value="${esc(d.tone)}" placeholder="如 轻声"></label>
        <label>语速<select data-d="rate">${opt(["很慢", "慢", "中等", "快", "很快"], d.rate)}</select></label>
        <label>音量<select data-d="volume">${opt(["很轻", "轻", "中", "响", "很响"], d.volume)}</select></label>
        <label>呼吸<select data-d="breath">${opt(["平稳呼吸", "屏住呼吸", "深吸一口气", "叹息"], d.breath)}</select></label>
      </div>
      <div class="row2">
        <label>停顿<input data-d="pause" value="${esc(d.pause)}" placeholder="可留空"></label>
        <label>同时发声分组<input data-d="group" value="${esc(d.group)}" placeholder="同组填同样的字，会输出 (S1,S2)"></label>
      </div>
    </div>`).join("");
  $$("#dialogueList [data-d]").forEach((el) => {
    el.onchange = async () => {
      const id = el.closest("[data-dlg]").dataset.dlg;
      const rows = seg().dialogues.map((d) => d.id === id ? Object.assign({}, d, { [el.dataset.d]: el.value }) : d);
      await patchSegment({ dialogues: rows }, false);
    };
  });
  $$("[data-deldlg]").forEach((b) => b.onclick = async () => {
    const rows = seg().dialogues.filter((d) => d.id !== b.dataset.deldlg);
    await patchSegment({ dialogues: rows }, true);
  });
}

/* ---- 素材 ---- */
const PURPOSES = [
  ["face", "角色容貌（仅作来源，不单独占编号）"],
  ["body", "角色服装/体型（仅作来源）"],
  ["scene", "场景/环境（仅作来源）"],
  ["keyframe_first", "首帧（占 <Picture N>）"],
  ["keyframe_last", "尾帧（占 <Picture N>）"],
  ["storyboard", "分镜参考（占 <Picture N>）"],
  ["voice_timbre", "音色参考（占 <Audio N>）"],
  ["voice_copy", "音频完整复制（占 <Audio N>）"],
  ["ambience", "环境音参考（占 <Audio N>）"],
];
function renderAssets() {
  const s = seg(), box = $("#assetList");
  if (!s.assets.length) { box.innerHTML = `<div class="empty">还没有素材。未勾选"已真实连接"的素材不会生成任何引用标签。</div>`; return; }
  box.innerHTML = s.assets.map((a) => `
    <div class="asset" data-asset="${esc(a.id)}">
      <div class="assethead">
        <b style="font-size:12.5px;color:var(--accent)">${esc(a.id)}</b>
        <label class="check"><input type="checkbox" data-a="connected" ${a.connected ? "checked" : ""}>已真实连接</label>
        <span style="flex:1"></span>
        <button class="mini danger" data-delasset="${esc(a.id)}">删除</button>
      </div>
      <div class="grid4">
        <label>类型<select data-a="kind">${["Picture", "Video", "Audio"].map((k) =>
          `<option value="${k}"${k === a.kind ? " selected" : ""}>${k === "Picture" ? "图片" : k === "Video" ? "视频" : "音频"}</option>`).join("")}</select></label>
        <label>归属角色<select data-a="role_id"><option value="">—（场景/道具）</option>${
          ST.project.roles.map((r) => `<option value="${esc(r.id)}"${r.id === a.role_id ? " selected" : ""}>${esc(r.id)} ${esc(r.name)}</option>`).join("")}</select></label>
        <label>用途<select data-a="purpose">${PURPOSES.map(([v, t]) =>
          `<option value="${v}"${v === a.purpose ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
        <label>来源说明<input data-a="label" value="${esc(a.label)}"></label>
      </div>
    </div>`).join("");
  $$("#assetList [data-a]").forEach((el) => {
    el.onchange = async () => {
      const id = el.closest("[data-asset]").dataset.asset;
      const val = el.type === "checkbox" ? el.checked : el.value;
      const rows = seg().assets.map((a) => a.id === id ? Object.assign({}, a, { [el.dataset.a]: val }) : a);
      await patchSegment({ assets: rows }, true);
    };
  });
  $$("[data-delasset]").forEach((b) => b.onclick = async () => {
    await patchSegment({ assets: seg().assets.filter((a) => a.id !== b.dataset.delasset) }, true);
  });
}

/* ---- 镜头 ---- */
function renderShots() {
  const s = seg(), box = $("#shotList");
  if (!s.shots.length) { box.innerHTML = `<div class="empty">未设置镜头 → 自动按单镜头编译。多镜头时第 2 个起必须填切点时间。</div>`; return; }
  box.innerHTML = s.shots.map((sh, i) => `
    <div class="shot" data-shot="${i}">
      <div class="grid5">
        <label>序号<input data-s="index" type="number" value="${sh.index}"></label>
        <label>切点秒（第1个留空）<input data-s="at_seconds" type="number" step="0.001" value="${sh.at_seconds ?? ""}"></label>
        <label>镜头运动<select data-s="camera_motion"><option value="">—</option>${
          ST.spec.camera_motions.map((m) => `<option value="${esc(m)}"${m === sh.camera_motion ? " selected" : ""}>${esc(ST.spec.camera_labels[m] || m)}（${esc(m)}）</option>`).join("")}</select></label>
        <label>幅度<select data-s="camera_amplitude"><option value="">—</option>
          <option value="with small amplitude"${sh.camera_amplitude === "with small amplitude" ? " selected" : ""}>小幅度</option>
          <option value="with large amplitude"${sh.camera_amplitude === "with large amplitude" ? " selected" : ""}>大幅度</option></select></label>
        <label>速度<select data-s="camera_speed"><option value="">—</option>
          <option value="at slow speed"${sh.camera_speed === "at slow speed" ? " selected" : ""}>慢速</option>
          <option value="at fast speed"${sh.camera_speed === "at fast speed" ? " selected" : ""}>快速</option></select></label>
      </div>
      <label>镜头内容（中文）<textarea data-s="zh_content" rows="2">${esc(sh.zh_content)}</textarea></label>
      <button class="mini danger" data-delshot="${i}">删除该镜头</button>
    </div>`).join("");
  $$("#shotList [data-s]").forEach((el) => {
    el.onchange = async () => {
      const i = +el.closest("[data-shot]").dataset.shot;
      const rows = seg().shots.map((sh, j) => j === i
        ? Object.assign({}, sh, { [el.dataset.s]: el.value === "" ? (el.dataset.s === "at_seconds" ? null : "") : el.value }) : sh);
      await patchSegment({ shots: rows }, false);
    };
  });
  $$("[data-delshot]").forEach((b) => b.onclick = async () => {
    await patchSegment({ shots: seg().shots.filter((_, j) => j !== +b.dataset.delshot) }, true);
  });
}

/* ---- 保留关系 ---- */
function renderRetention() {
  const s = seg(), box = $("#retentionList");
  const labels = [];
  s.assets.filter((a) => a.connected).forEach((a) => {
    const standalone = ["keyframe_first", "keyframe_last", "storyboard", "composition"].includes(a.purpose);
    const kind = a.kind === "Audio" ? "Audio" : a.kind === "Video" ? "Video" : (standalone ? "Picture" : null);
    if (kind && !labels.includes(kind)) labels.push(kind);
  });
  if (s.mode !== "Ref2VA") { box.innerHTML = `<div class="empty">仅 Ref2VA 使用 retention_analysis。</div>`; return; }
  box.innerHTML = labels.map((k) => {
    const markers = k === "Audio" ? ST.spec.audio_markers : ST.spec.visual_markers;
    const labelsZh = k === "Audio" ? ST.spec.audio_marker_labels : ST.spec.visual_marker_labels;
    const cur = (s.retention || {})[k] || "";
    return `<div class="ret"><label>${esc(k)} 类参考标记
      <select data-ret="${esc(k)}"><option value="">—（使用默认）</option>${
        markers.map((m) => `<option value="${esc(m)}"${m === cur ? " selected" : ""}>${esc(labelsZh[m] || m)}（${esc(m)}）</option>`).join("")}</select></label></div>`;
  }).join("") || `<div class="empty">还没有已连接的参考素材。</div>`;
  $$("#retentionList [data-ret]").forEach((el) => {
    el.onchange = async () => {
      const ret = Object.assign({}, seg().retention || {});
      el.value ? ret[el.dataset.ret] = el.value : delete ret[el.dataset.ret];
      await patchSegment({ retention: ret }, false);
    };
  });
}

/* ---- 任务类型 ---- */
function renderTaskTypes() {
  const s = seg(), box = $("#taskTypeList");
  box.innerHTML = ST.spec.task_types.map((t) => {
    const on = (s.task_types || []).includes(t);
    return `<span class="chip${on ? " on" : ""}" data-tt="${esc(t)}">${esc(ST.spec.task_type_labels[t] || t)}</span>`;
  }).join("");
  $$("[data-tt]").forEach((c) => c.onclick = async () => {
    const cur = new Set(seg().task_types || []);
    cur.has(c.dataset.tt) ? cur.delete(c.dataset.tt) : cur.add(c.dataset.tt);
    await patchSegment({ task_types: Array.from(cur) }, true);
  });
}

/* ---- 角色关系（复杂时才用） ---- */
function renderRelations() {
  const s = seg(), box = $("#relationList");
  const rows = (s.relations || []);
  box.innerHTML = rows.length ? rows.map((r, i) => `
    <div class="shot" data-rel="${i}">
      <div class="grid4">
        <label>执行角色<select data-r="actor">${roleOpts(r.actor)}</select></label>
        <label>目标角色<select data-r="target">${roleOpts(r.target)}</select></label>
        <label>相对位置<input data-r="position" value="${esc(r.position || "")}"></label>
        <label>动作<input data-r="action" value="${esc(r.action || "")}"></label>
      </div>
      <button class="mini danger" data-delrel="${i}">删除</button>
    </div>`).join("") : `<div class="empty">用户已经把动作写清楚时，这里不用填。</div>`;
  function roleOpts(sel) {
    return `<option value="">—</option>` + s.role_ids.map((rid) => {
      const r = ST.project.roles.find((x) => x.id === rid);
      return r ? `<option value="${esc(rid)}"${rid === sel ? " selected" : ""}>${esc(r.id)} ${esc(r.name)}</option>` : "";
    }).join("");
  }
  $$("#relationList [data-r]").forEach((el) => {
    el.onchange = async () => {
      const i = +el.closest("[data-rel]").dataset.rel;
      const rows2 = (seg().relations || []).map((r, j) =>
        j === i ? Object.assign({}, r, { [el.dataset.r]: el.value }) : r);
      await patchSegment({ relations: rows2 }, false);
    };
  });
  $$("[data-delrel]").forEach((b) => b.onclick = async () => {
    await patchSegment({ relations: (seg().relations || []).filter((_, j) => j !== +b.dataset.delrel) }, true);
  });
}

/* ------------------------------------------------------------------ D 输出 */
async function compile() {
  const btn = $("#btn-compile");
  btn.disabled = true; btn.textContent = "正在编译…";
  try {
    const s = seg();
    const r = await api("/api/compile", {
      id: s.id, title: $("#seg-title").value, mode: $("#seg-mode").value,
      duration: +$("#seg-duration").value, action_zh: $("#seg-action").value,
      camera_zh: $("#seg-camera").value, soundscape_zh: $("#seg-soundscape").value,
      music_zh: $("#seg-music").value, extra_zh: $("#seg-extra").value,
      inherit_prev_end_state: $("#seg-inherit").value,
    });
    LAST = { prompt: r.prompt, report: r.report, ambiguous: r.ambiguous || [] };
    renderOutput(r);
    if (!r.ok) toast("编译未通过，请查看下方错误。", true);
    else toast(`编译完成（${r.elapsed_sec}s）`);
  } catch (e) { toast("编译失败：" + e.message, true); }
  finally { btn.disabled = false; btn.textContent = "编译完整提示词"; }
}

function renderOutput(r) {
  const s = seg();
  $("#out-zh").value = [
    `【模式】${ST.spec.mode_labels[s.mode] || s.mode}　【时长】${s.duration} 秒`,
    `【场景】${s.scene_zh || ST.project.preset.scene || "（未填）"}`,
    `【动作】${s.action_zh || "（未填）"}`,
    `【摄影机】${s.camera_zh || "（未填）"}`,
    `【环境音】${s.soundscape_zh || "（未填）"}`,
    `【配乐】${s.music_zh || "（未填）"}`,
    `【台词】${s.dialogues.filter((d) => (d.zh_text || "").trim()).map((d) => `${d.speaker_role_id}：${d.zh_text}`).join(" ｜ ") || "（无）"}`,
  ].join("\n");

  if (!r) { $("#out-final").value = s.final_edited_prompt || s.compiled_prompt || ""; return; }

  $("#out-en").value = extractBody(r.prompt);
  $("#out-final").value = r.final_prompt || r.prompt;
  $("#out-raw").value = r.prompt || "";

  const boxes = [];
  if (r.errors && r.errors.length) boxes.push(box("err", "编译错误", r.errors));
  if (r.ambiguous && r.ambiguous.length) boxes.push(box("warn", "需要你确认的指代", r.ambiguous));
  if (r.warnings && r.warnings.length) boxes.push(box("warn", "编译警告", r.warnings));
  if (r.report) {
    const errs = r.report.checks.filter((c) => c.severity === "error").map((c) => c.message);
    const warns = r.report.checks.filter((c) => c.severity === "warning").map((c) => c.message);
    if (errs.length) boxes.push(box("err", "确定性校验错误", errs));
    if (warns.length) boxes.push(box("warn", "确定性校验警告", warns));
    if (!errs.length && !warns.length) boxes.push(box("ok", "确定性校验", ["全部检查通过。"]));
  }
  $("#statusBox").innerHTML = boxes.join("") || box("ok", "状态", ["编译通过。"]);
  const m = r.meta || {};
  $("#compileInfo").textContent =
    `字符数 ${m.char_count || 0} / ${ST.spec.max_chars}\n`
    + `镜头数 ${m.final_shot || 1}　台词事件 ${m.dialogue_events || 0}\n`
    + `Subject 映射 ${JSON.stringify(m.subjects || {})}\n`
    + `说话人编号 ${JSON.stringify(m.role_speaker || {})}\n`
    + `参考编号 ${JSON.stringify(m.references || {})}\n`
    + `耗时 ${r.elapsed_sec}s\n`
    + `性能统计 ${JSON.stringify(r.perf || {})}`;
}
function box(kind, title, lines) {
  return `<div class="statusbox ${kind}"><b>${esc(title)}</b><ul>${
    lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>`;
}
function extractBody(prompt) {
  if (!prompt) return "";
  const m = prompt.match(/(integrated_multimodal_description:|detailed_description:)\s*([\s\S]*?)(\n\n[a-z_]+:|$)/);
  return m ? m[2].trim() : "";
}

/* ------------------------------------------------------------------ 库 */
async function refreshPrompts(q) {
  const r = await api("/api/prompts" + (q ? "?q=" + encodeURIComponent(q) : ""));
  $("#promptList").innerHTML = r.items.length ? r.items.map((it) => `
    <div class="item"><div class="meta">
      <b>${esc(it.title)}</b><br>${esc(it.mode)} · ${it.duration}s · ${it.chars} 字符 · ${esc(it.saved_at.slice(0, 19))}<br>
      ${esc(it.zh_summary || "").slice(0, 60)}</div>
      <button class="mini" data-pl="${esc(it.id)}">载入</button></div>`).join("")
    : `<div class="empty">提示词库为空。</div>`;
  $$("[data-pl]").forEach((b) => b.onclick = async () => {
    const r2 = await api("/api/prompt/load", { prompt_id: b.dataset.pl });
    $("#out-final").value = r2.item.prompt;
    toast("已载入提示词（未自动保存到工程，请自行决定是否覆盖）");
  });
}
async function refreshVersions() {
  const r = await api("/api/versions");
  $("#versionList").innerHTML = r.items.length ? r.items.map((v) => `
    <div class="item"><div class="meta"><b>${esc(v.label || "（无标签）")}</b><br>
      ${esc(v.saved_at.slice(0, 19))} · schema v${v.schema_version}</div>
      <button class="mini" data-vl="${esc(v.file)}">恢复</button></div>`).join("")
    : `<div class="empty">还没有历史版本。</div>`;
  $$("[data-vl]").forEach((b) => b.onclick = async () => {
    if (!confirm("恢复该版本会覆盖当前工程（之前的状态仍保留在历史里）。继续？")) return;
    const r2 = await api("/api/version/load", { file: b.dataset.vl });
    ST.project = r2.project;
    renderTabs(); renderPreset(); renderRoles(); renderSegment(); renderOutput(null);
    toast("已恢复到所选版本");
  });
}

/* ------------------------------------------------------------------ 绑定 */
function bind() {
  $$("[data-toggle]").forEach((b) => b.onclick = () => {
    const body = document.querySelector(`[data-body="${b.dataset.toggle}"]`);
    if (body) body.classList.toggle("hidden");
  });
  $("#btn-add-role").onclick = async () => {
    const st = await api("/api/role/add", { name: "新角色" });
    ST.project = st.project;
    const ids = ST.project.roles.map((r) => r.id);
    const sid = seg().id;
    await patchSegment({ role_ids: ST.project.roles
      .filter((r) => seg().role_ids.includes(r.id) || r.id === ids[ids.length - 1]).map((r) => r.id) }, false);
    const st2 = await api("/api/segment/select", { id: sid });
    ST.project = st2.project;
    renderRoles(); renderSegment();
    toast("已添加角色 " + ids[ids.length - 1]);
  };
  $("#btn-preset-save").onclick = () => savePreset(false);
  $("#btn-preset-apply").onclick = async () => {
    const name = $("#preset-list").value;
    if (!name) return toast("请先选择一个预设", true);
    const st = await api("/api/preset/apply", { name });
    ST.project = st.project; renderPreset(); renderSegment(); toast("已读取预设：" + name);
  };
  $("#btn-preset-del").onclick = async () => {
    const name = $("#preset-list").value;
    if (!name) return toast("请先选择一个预设", true);
    if (!confirm("删除预设「" + name + "」？会移入回收目录，不物理删除。")) return;
    const st = await api("/api/preset/delete", { name });
    ST.presets = st.presets; renderPreset(); toast("预设已移入回收目录");
  };
  $("#btn-preset-default").onclick = () => {
    ["#preset-scene", "#preset-people", "#preset-body", "#preset-voice",
     "#preset-camera", "#preset-sound", "#preset-style"]
      .forEach((s) => $(s).value = "");
    toast("已清空表单（点「保存预设」后才会生效）");
  };

  $("#seg-mode").onchange = () => patchSegment({ mode: $("#seg-mode").value }, true).then(renderTabs);
  $("#seg-duration").onchange = () => patchSegment({ duration: +$("#seg-duration").value }, false);
  $("#seg-title").onchange = () => patchSegment({ title: $("#seg-title").value }, false).then(renderTabs);
  $("#seg-action").onchange = () => patchSegment({ action_zh: $("#seg-action").value }, false);
  $("#seg-camera").onchange = () => patchSegment({ camera_zh: $("#seg-camera").value }, false);
  $("#seg-soundscape").onchange = () => patchSegment({ soundscape_zh: $("#seg-soundscape").value }, false);
  $("#seg-music").onchange = () => patchSegment({ music_zh: $("#seg-music").value }, false);
  $("#seg-extra").onchange = () => patchSegment({ extra_zh: $("#seg-extra").value }, false);
  $("#seg-inherit").onchange = () => patchSegment({ inherit_prev_end_state: $("#seg-inherit").value }, false);

  $("#btn-add-dialogue").onclick = addDialogue;
  $("#btn-add-asset").onclick = async () => {
    const ids = seg().assets.map((a) => a.id);
    let n = 1; ids.forEach((i) => { const m = /^M(\d+)$/.exec(i); if (m) n = Math.max(n, +m[1] + 1); });
    await patchSegment({ assets: seg().assets.concat([{
      id: "M" + String(n).padStart(2, "0"), kind: "Picture", label: "新素材",
      connected: false, role_id: "", purpose: "face", note: "" }]) }, true);
  };
  $("#btn-add-shot").onclick = async () => {
    const shots = seg().shots.concat([{ index: seg().shots.length + 1, at_seconds: 1, zh_content: "", camera_zh: "" }]);
    await patchSegment({ shots }, true);
  };
  $("#btn-add-relation").onclick = async () => {
    await patchSegment({ relations: (seg().relations || []).concat([{ actor: "", target: "", position: "", action: "" }]) }, true);
  };

  $("#btn-compile").onclick = compile;
  $("#btn-validate").onclick = async () => {
    try {
      const r = await api("/api/validate", { id: seg().id, prompt: $("#out-final").value });
      const errs = r.report.checks.filter((c) => c.severity === "error").map((c) => c.message);
      const warns = r.report.checks.filter((c) => c.severity === "warning").map((c) => c.message);
      $("#statusBox").innerHTML =
        (errs.length ? box("err", "确定性校验错误", errs) : "") +
        (warns.length ? box("warn", "确定性校验警告", warns) : "") +
        (!errs.length && !warns.length ? box("ok", "确定性校验", ["全部检查通过。"]) : "");
      toast(r.report.valid ? "校验通过" : "校验未通过", !r.report.valid);
    } catch (e) { toast("校验失败：" + e.message, true); }
  };
  $("#btn-copy").onclick = async () => {
    try { await navigator.clipboard.writeText($("#out-final").value); toast("已复制最终提示词"); }
    catch { $("#out-final").select(); document.execCommand("copy"); toast("已复制（兼容模式）"); }
  };
  $("#btn-save-prompt").onclick = async () => {
    try {
      const r = await api("/api/prompt/save", { id: seg().id, prompt: $("#out-final").value });
      toast("已保存到提示词库：" + r.id); await refreshPrompts();
    } catch (e) { toast("保存失败：" + e.message, true); }
  };
  $("#btn-export").onclick = async () => {
    try {
      const r = await api("/api/export", { id: seg().id, prompt: $("#out-final").value });
      toast("已导出：" + r.path);
    } catch (e) { toast("导出失败：" + e.message, true); }
  };
  $("#btn-version").onclick = async () => {
    const label = prompt("给这个版本起个名字：", seg().title || "版本");
    if (label === null) return;
    const r = await api("/api/version/save", { label });
    toast("已保存版本：" + r.file); await refreshVersions();
  };
  $("#btn-version-refresh").onclick = () => refreshVersions();
  $("#btn-prompt-search").onclick = () => refreshPrompts($("#prompt-search").value);
  $("#prompt-search").onkeydown = (e) => { if (e.key === "Enter") refreshPrompts($("#prompt-search").value); };

  $("#out-final").onchange = async () => {
    await patchSegment({ final_edited_prompt: $("#out-final").value }, false);
    toast("已记录人工编辑；旧校验状态已失效，请重新校验。");
  };
}

bind();
init();
