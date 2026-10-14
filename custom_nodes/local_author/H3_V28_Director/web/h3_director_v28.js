/**
 * H3 全中文导演台 V28 —— 【剧情自动导演】面板（任务书 §13 / §25）
 *
 * 一句话：用户给「总剧情构想 + 中性参考槽映射 + 用途说明」。Gemma4 文本导演一次性规划整部片子、
 * 拆成 SEG1..N 并编好每段的 H3 提示词，然后自己下线；之后用户只做三件事
 * ——【生成当前段】、【重新生成】、【接受并下一步】。
 *
 * ============================ 架构约束（不得改） ============================
 * 1) UI_REFACTOR_01（H3_DIRECTOR_V28_IN_WORKFLOW_UI_REFACTOR_01）起，导演台
 *    从「document.body 上的 fixed 浮动面板」迁移为「工作流内节点」：
 *    后端注册 H3V28DirectorConsole（纯 UI，RETURN_TYPES=()，见 v28_ui_node.py），
 *    前端在本文件里对该类型 addDOMWidget 挂载本面板（官方 extension 机制）。
 *    floating 面板已退役：FLOATING_DIRECTOR_PANEL = DISABLED，只保留右下角
 *    一个【定位剧情导演节点】小按钮。
 *    提交期安全：h3_workflow_ux.js 的 UI_ONLY_SELECTOR_TYPES 白名单会在
 *    /prompt 序列化时摘掉零连线的本类型节点（与 H3ContinuationSelector 同一
 *    机制）。导演台仍绝不自动排队、绝不自动接受（§21/§24）。
 * 2) 不接管 V27 傻瓜控制台（N159）里那块面板，避免两套 UI 互相覆盖。
 *    这里只借用 V27 已经验证过的三个原语：按 id 找节点、按名字找 widget、
 *    写 widget.value 之后调用 widget.callback 再 app.graph.change()。
 * 3) 本文件不 import V27 helper 的任何模块：V27 文件改名或缺失时，
 *    V28 面板必须还能加载。需要的常量都在下面自带一份并注明来源。
 * 4) 滚轮硬规则（P7/P8）：普通区域 wheel → 画布 zoom（局部桥接回 canvas）；
 *    只有 textarea 与「真正可滚动」的容器拦截 wheel；禁止任何全局 wheel hack。
 */
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const V28 = "0.28.2-gate6b";
const PANEL_ID = "h3v28-director-panel";
const LAUNCHER_ID = "h3v28-director-launcher";
const STORE_PROJECT = "h3v28.projectId";
const STORE_OPEN = "h3v28.panelOpen";
const draftKey = () => `h3v28.gate6c.${state.projectId || "new"}`;
function saveGate6cDraft() {
  if (!dom.dialogue) return;
  localStorage.setItem(draftKey(), JSON.stringify({
    dialogue: dom.dialogue.value || "", dialogueMode: dom.dialogueMode.value || "无台词",
    dialogueDensity: dom.dialogueDensity.value || "正常", allowPolish: dom.allowPolish.value || "关闭",
    userConstraints: dom.userConstraints?.value || "",
    promptSource: dom.promptSource?.value || "MANUAL",
    manualPrompts: dom.manualInputs?.map(x => x.value) || [],
  }));
}
function loadGate6cDraft() {
  if (!dom.dialogue) return;
  try {
    const x = JSON.parse(localStorage.getItem(draftKey()) || "{}");
    dom.dialogue.value = x.dialogue || ""; dom.dialogueMode.value = x.dialogueMode || "无台词";
    dom.dialogueDensity.value = x.dialogueDensity || "正常"; dom.allowPolish.value = x.allowPolish || "关闭";
    if (dom.userConstraints) dom.userConstraints.value = x.userConstraints || "";
    if (dom.promptSource) dom.promptSource.value = x.promptSource || "MANUAL";
    if (dom.manualInputs && Array.isArray(x.manualPrompts)) {
      dom.manualInputs.forEach((input, i) => { input.value = x.manualPrompts[i] || ""; });
    }
  } catch (_) { /* browser-only draft; ignore corrupt legacy value */ }
}
const NOT_RELEASED = "导演模型尚未释放显存，请稍候";   // 任务书 §31 原文

/** V27 图里被 V28 驱动的节点（来源：v28_paths.NODE，8197 实测副本）。 */
const NODE = {
  console: 159,          // H3OperationSelector：默认「只跑一采」
  prompt: 138,           // PrimitiveStringMultiline（N915/N136 的真正提示词源）
  duration: 132,         // PrimitiveFloat 秒数，帧数由 N131 公式派生
  seed: 142,             // SeedNode
  continuation: 992,     // H3ContinuationSelector（写它必须触发 callback）
  mcSave: 995,           // clip_index == 本段
  mcLoad: 996,           // clip_index == 上一已接受段（0 = 没有）
  mcChain: 997,          // segments == 连拍预算
  refImages: [687, 688, 689, 690, 1001, 1002, 1003, 1004, 1005],
};
const OPERATION_DEFAULT = "只跑一采";              // 与 V27 每次提交前一致
const FIXED_SEED_LABELS = ["fixed", "固定不变", "固定"];   // 中英两套选项都认
/** SeedNode「生成后」控件的全部合法取值（V27 同源常量，用于按语义认出这个控件）。 */
const SEED_CONTROL_VALUES = new Set([
  "fixed", "increment", "decrement", "randomize",
  "固定不变", "固定", "递增", "递减", "随机", "随机化",
]);

// ---------------------------------------------------------------------------
// 小工具：与 V27 h3_foolproof_v3_dashboard.js 同语义（自己一份，不 import）
// ---------------------------------------------------------------------------
function nodes() { return app?.graph?._nodes || []; }
function byId(id) {
  // 运行态 node.id 可能是字符串（本项目踩过），一律 Number() 归一。
  return nodes().find((n) => Number(n.id) === Number(id));
}
function widget(node, name) {
  if (!node || !node.widgets) return null;
  return node.widgets.find((w) => w.name === name) || null;
}
function isNumeric(w) {
  const t = String(w?.type || "");
  return t === "number" || t === "slider" || t === "knob";
}
/** 写一个 widget：数值控件拒绝非有限数字（V27 的 NaN 闸门），然后触发 callback。 */
function setWidget(target, value) {
  if (!target) return false;
  if (isNumeric(target) && (typeof value !== "number" || !Number.isFinite(value))) {
    console.error("[H3 V28] 已拒绝把非有限数字写入数值控件", { name: target.name, value });
    return false;
  }
  // P11 TEST6 / BUG-8：下拉控件写入空值同样是「静默写坏」。combo 的合法取值永远非空，
  // 拿到 undefined 只可能是上游取错了字段——宁可报「写入失败」让按钮停下，
  // 也不能把控件刷成空值还回 true（旧代码正是这样把种子控制写没的）。
  if (String(target.type) === "combo" && (value == null || value === "")) {
    console.error("[H3 V28] 已拒绝把空值写入下拉控件", { name: target.name, value });
    return false;
  }
  target.value = value;
  try { target.callback?.(value); } catch (e) { console.warn("[H3 V28] 控件同步失败", e); }
  app.graph?.change?.();
  return true;
}
function widgetValue(node, name) { return widget(node, name)?.value; }

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = String(text);
  return e;
}
function button(label, onClick, kind = "secondary") {
  const b = el("button", `h3v28-btn h3v28-${kind}`, label);
  b.type = "button";
  b.addEventListener("click", async (ev) => {
    ev.preventDefault(); ev.stopPropagation();
    if (state.busy && kind !== "danger") { flash(`导演台正在忙：${state.busy}`); return; }
    try { await onClick(ev); } catch (err) {
      console.error("[H3 V28] 操作失败", err);
      banner(`操作失败：${err?.message || err}`, "bad");
    }
  });
  b.addEventListener("pointerdown", (ev) => ev.stopPropagation());
  return b;
}
/** 让面板内的交互不被 LiteGraph 当成画布事件吃掉。
 *  UI_REFACTOR_01：wheel 从这份黑名单里摘掉了——wheel 由 installWheelPolicy
 *  按 P7 硬规则分流（普通区域回画布 zoom；textarea / 真正可滚容器才拦截）。 */
function stopCanvasEvents(root) {
  for (const name of ["pointerdown", "pointerup", "mousedown", "mouseup",
                      "click", "keydown", "contextmenu"]) {
    root.addEventListener(name, (ev) => ev.stopPropagation());
  }
}

// ---------------------------------------------------------------------------
// 滚轮硬规则（P7/P8）。禁止任何全局 wheel hack：事件只绑在本面板 root 上。
// ---------------------------------------------------------------------------
function isScrollableY(elm) {
  if (!elm || elm.nodeType !== 1) return false;
  const s = getComputedStyle(elm);
  if (!/(auto|scroll|overlay)/.test(String(s.overflowY))) return false;
  return elm.scrollHeight > elm.clientHeight + 1;
}
/** 最小局部桥接：把 wheel 原样转发到 LiteGraph 画布元素 → 官方 wheel 逻辑
 *  （指针处 zoom）自然接管。不改 ComfyUI Core、不改 LiteGraph、无全局监听。 */
function forwardWheelToCanvas(ev) {
  const canvasEl = app?.canvas?.canvas;
  if (!canvasEl) return;
  canvasEl.dispatchEvent(new WheelEvent("wheel", {
    bubbles: true, cancelable: true,
    deltaX: ev.deltaX, deltaY: ev.deltaY, deltaZ: ev.deltaZ, deltaMode: ev.deltaMode,
    clientX: ev.clientX, clientY: ev.clientY, screenX: ev.screenX, screenY: ev.screenY,
  }));
}
function installWheelPolicy(root) {
  root.addEventListener("wheel", (ev) => {
    // ① 文本输入区（剧情构想 / 当前剧情 / 提示词等 textarea）：
    //    focus/hover 一律拦截——内容可滚走默认滚，到顶/底也保持焦点，
    //    绝不突然缩放画布（P7 明确要求）。
    if (ev.target instanceof HTMLTextAreaElement) { ev.stopPropagation(); return; }
    // ② 其它可滚容器（面板体 / 计划列表 / 日志）：真正能滚才拦截；
    //    已经顶到边缘 → 交还画布 zoom（保证普通区域始终可达缩放）。
    for (let e = ev.target; e && e !== root; e = e.parentElement) {
      if (isScrollableY(e)) {
        const goingUp = ev.deltaY < 0;
        const atTop = e.scrollTop <= 0;
        const atBottom = e.scrollTop + e.clientHeight >= e.scrollHeight - 1;
        if ((goingUp && atTop) || (!goingUp && atBottom)) break;  // 边缘 → 画布
        ev.stopPropagation();
        return;                                                    // 内部滚动
      }
    }
    // ③ 普通节点区域（标题/按钮/标签/空白/折叠区…）：交给画布 zoom。
    ev.preventDefault();
    forwardWheelToCanvas(ev);
  }, { passive: false });
}

// ---------------------------------------------------------------------------
// HTTP：/h3_director/* 既可能挂在根，也可能挂在 /api 前缀下（取决于挂载时机），
// 所以启动时探一次、把可用前缀记下来，而不是赌一个。
// ---------------------------------------------------------------------------
let BASE = null;
function rootBase() {
  return typeof api?.api_base === "string" ? api.api_base : "";
}
async function probeBase() {
  for (const cand of [`${rootBase()}/h3_director`, `${rootBase()}/api/h3_director`]) {
    try {
      const r = await fetch(`${cand}/ping`, { method: "GET", cache: "no-cache" });
      if (!r.ok) continue;
      const j = await r.json();
      if (j && j.package === "H3_V28_Director") return cand;
    } catch (e) { /* 换下一个候选 */ }
  }
  return null;
}
async function call(path, { method = "GET", body = null, query = null } = {}) {
  if (!BASE) BASE = await probeBase();
  if (!BASE) throw new Error("导演接口未挂载：请重启 8197 的 ComfyUI（H3_V28_Director 未加载）");
  let url = BASE + path;
  if (query) url += "?" + new URLSearchParams(query).toString();
  const opt = { method, headers: {}, cache: "no-cache" };
  if (body != null) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const resp = await fetch(url, opt);
  let data = null;
  try { data = await resp.json(); } catch (e) { data = { error: `响应不是 JSON（HTTP ${resp.status}）` }; }
  if (!resp.ok) {
    const msg = data?.error || data?.detail || `HTTP ${resp.status}`;
    const err = new Error(msg);
    err.status = resp.status;
    err.payload = data;
    throw err;
  }
  return data || {};
}

// ---------------------------------------------------------------------------
// 面板状态
// ---------------------------------------------------------------------------
const state = {
  projectId: localStorage.getItem(STORE_PROJECT) || "",
  card: null,           // /state 的返回
  task: null,           // 正在轮询的 PHASE A 任务
  busy: "",
  flight: null,         // {segment_id, seed, prompt_id}
  editing: false,       // 用户正在文本框里打字 -> 暂停刷新该字段
  refs: [],             // /pick_images 解析结果
};

let panel = null, launcher = null, dom = {};

// ---------------------------------------------------------------------------
// UI_REFACTOR_01：工作流内承载（H3V28DirectorConsole 节点）
// ---------------------------------------------------------------------------
const DIRECTOR_WIDGET = "h3v28_director";
const DIRECTOR_WIDGET_H = 780;          // 仅作为 widget 最小高度（节点收缩下限）；上限放开，跟随节点（FOLLOW_NODE_RESIZE_01）
const FLOATING_DIRECTOR_PANEL = false;  // P5：floating 面板 = DISABLED
let hostNode = null;                    // 当前承载面板的导演节点（仅一个生效）

function placeholderPanel() {
  const p = el("div", "h3v28-panel open");
  p.style.height = "120px";
  const h = el("div", "h3v28-head");
  h.append(el("b", "", "【V28 剧情自动导演】"));
  p.append(h);
  const b = el("div", "h3v28-body");
  b.append(el("div", "h3v28-hint",
    "本图已存在另一个导演节点，面板挂在那里（一张图只生效一个导演节点）。"));
  p.append(b);
  return p;
}

/** 把面板挂进 H3V28DirectorConsole 节点（官方 addDOMWidget 机制）。 */
function mountIntoNode(node) {
  buildPanel();
  if (hostNode && hostNode !== node && hostNode.graph === node.graph) {
    // 保守：一张图只挂一份面板；第二个导演节点只得到占位说明。
    node.addDOMWidget(DIRECTOR_WIDGET, "V28_DIRECTOR", placeholderPanel(), {
      serialize: false, hideOnZoom: false,
      getMinHeight: () => 120, getMaxHeight: () => 120,
    });
    return false;
  }
  hostNode = node;
  node.addDOMWidget(DIRECTOR_WIDGET, "V28_DIRECTOR", panel, {
    serialize: false, hideOnZoom: false,
    // FOLLOW_NODE_RESIZE_01：官方 _arrangeWidgets/distributeSpace 会把节点剩余
    // 高度分给 DOM widget（min→max 区间内）。min = 最小可用高度，max 放开 →
    // 节点拉高面板同步拉高，缩小则退回 min。高度分配来自 computedHeight，
    // wrapper 为 position:fixed 出流定位，面板内容不回灌 node.size（无反馈环）。
    getMinHeight: () => DIRECTOR_WIDGET_H, getMaxHeight: () => Infinity,
  });
  if (BASE) refresh().catch(() => {});
  return true;
}

/** P5 兼容入口：右下角小按钮，把画布居中到导演节点。不弹任何浮动面板。 */
function locateDirectorNode() {
  const n = nodes().find((x) => x.type === "H3V28DirectorConsole") || hostNode;
  if (!n || !n.graph) {
    const prev = launcher?.textContent;
    if (launcher) {
      launcher.textContent = "画布上没有导演节点";
      setTimeout(() => { if (launcher) launcher.textContent = prev; }, 1600);
    }
    return;
  }
  try { app.canvas?.centerOnNode?.(n); } catch (e) { /* 老版本无此 API 则忽略 */ }
  n.graph?.setDirtyCanvas?.(true, true);
}

// ---------------------------------------------------------------------------
// 构建
// ---------------------------------------------------------------------------
const CSS = `
/* UI_REFACTOR_01：面板不再 fixed 浮动，改为工作流内 DOM Widget 承载。
   FOLLOW_NODE_RESIZE_01：宽高均 100% 跟随官方分配的 widget 区域（节点拉大→
   面板同步变大；缩回 min 以下由 widget minHeight 兜底），内部由 .h3v28-body
   纵向滚动。wrapper 高度由 computedHeight 显式设定，内容不回灌 node.size。 */
.h3v28-panel{box-sizing:border-box;position:relative;top:auto;right:auto;bottom:auto;width:100%;height:100%;
 display:flex;flex-direction:column;gap:0;padding:0;background:#100d18;border:1px solid #76549a;
 border-radius:10px;color:#fff;font:600 13px/1.45 system-ui,"Microsoft YaHei",sans-serif;
 box-shadow:none;overflow:hidden}
.h3v28-panel.open{display:flex}
.h3v28-head{display:flex;align-items:center;gap:8px;padding:9px 13px;background:#1b1428;border-bottom:1px solid #3e3151;cursor:move;user-select:none;-webkit-user-select:none;touch-action:none}
.h3v28-head b{font-size:15px;color:#f0e7ff}
.h3v28-head .h3v28-ver{margin-left:auto;color:#9b86b5;font-size:11px;font-weight:600}
.h3v28-body{flex:1;overflow:auto;overscroll-behavior:contain;padding:12px}
.h3v28-sec{margin:0 0 11px;padding:11px;border:1px solid #3e3151;border-radius:9px;background:#171120}
.h3v28-sec>h4{margin:0 0 8px;font-size:14px;color:#e6d8ff;font-weight:700}
.h3v28-row{display:grid;grid-template-columns:76px 1fr;align-items:center;gap:8px;margin:6px 0}
.h3v28-row.top{align-items:start}
.h3v28-lab{color:#baa9ce;font-size:12px;font-weight:600}
.h3v28-ta{box-sizing:border-box;width:100%;min-height:96px;resize:vertical;padding:8px;border:1px solid #76549a;
 border-radius:7px;background:#0d0a12;color:#fff;font:500 13px/1.5 ui-monospace,Consolas,"Microsoft YaHei",monospace;
 overscroll-behavior:contain}
.h3v28-ta.sm{min-height:64px}
.h3v28-in,.h3v28-sel{box-sizing:border-box;width:100%;height:32px;padding:4px 8px;border:1px solid #76549a;
 border-radius:7px;background:#0d0a12;color:#fff;font-weight:600;font-size:13px}
.h3v28-nums{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.h3v28-btn{min-height:32px;padding:6px 9px;border:1px solid #76549a;border-radius:7px;background:#322342;
 color:#fff;font-weight:700;font-size:13px;cursor:pointer;font-family:inherit}
.h3v28-btn:hover{filter:brightness(1.15)}
.h3v28-btn:disabled{opacity:.45;cursor:not-allowed}
.h3v28-primary{background:#2f9e68;border-color:#2f9e68;color:#04150d}
.h3v28-warn{background:#8a6a2f;border-color:#c79b45;color:#1d1405}
.h3v28-danger{background:#3b2029;border-color:#754052;color:#ffd5df}
.h3v28-acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.h3v28-choice{display:flex;gap:6px}
.h3v28-choice .h3v28-btn.on{background:#123b2a;border-color:#62dfa0;box-shadow:0 0 0 2px rgba(98,223,160,.16)}
.h3v28-check{display:flex;align-items:center;gap:6px;color:#baa9ce;font-size:12px;font-weight:600}
.h3v28-status{margin-top:9px;padding:9px;border-radius:7px;background:#0c241a;color:#aaf1ca;font-size:12px;
 white-space:pre-wrap;word-break:break-word}
.h3v28-status.bad{background:#3b2029;color:#ffd5df}
.h3v28-status.warn{background:#2b2410;color:#f3c979}
.h3v28-gate{margin:0 0 11px;padding:10px;border-radius:9px;border:1px solid #754052;background:#3b2029;
 color:#ffd5df;font-size:13px;display:none}
.h3v28-gate.on{display:block}
.h3v28-list{margin:0;padding:0;list-style:none}
.h3v28-seg{display:grid;grid-template-columns:22px 1fr auto;gap:7px;align-items:center;padding:5px 6px;
 border-radius:6px;font-size:12.5px;color:#cbbce4;font-weight:600}
.h3v28-seg.cur{background:#123b2a;color:#e9fff3;border:1px solid #2f9e68}
.h3v28-seg.acc{color:#7ee5ad}
.h3v28-seg i{font-style:normal;color:#8d7ba1;font-size:11px}
.h3v28-chip{padding:2px 7px;border-radius:20px;background:#241833;color:#cdb9e7;font-size:11px;font-weight:700;
 border:1px solid #3e3151}
.h3v28-chip.ok{background:#10241a;color:#7ee5ad;border-color:#2f9e68}
.h3v28-chip.run{background:#10243a;color:#8fd0ff;border-color:#2f6da3}
.h3v28-chip.err{background:#3b2029;color:#ffd5df;border-color:#754052}
.h3v28-kv{display:flex;justify-content:space-between;gap:8px;padding:3px 0;color:#baa9ce;font-size:12px}
.h3v28-kv b{color:#fff;font-weight:700;text-align:right;word-break:break-all}
.h3v28-ref{display:flex;justify-content:space-between;gap:8px;padding:3px 0;font-size:12px;color:#baa9ce}
.h3v28-ref b{color:#7ee5ad;font-weight:700;word-break:break-all;text-align:right}
.h3v28-ref.miss b{color:#ffd5df}
.h3v28-lines{max-height:132px;overflow:auto;overscroll-behavior:contain;margin-top:8px;padding:8px;border-radius:7px;background:#0d0a12;
 font:500 11.5px/1.5 ui-monospace,Consolas,"Microsoft YaHei",monospace;color:#9fd8c0;white-space:pre-wrap}
.h3v28-lines:empty{display:none}
.h3v28-vid{display:block;width:100%;max-height:230px;margin-top:8px;border-radius:7px;background:#000}
.h3v28-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;font-size:11.5px}
.h3v28-links a{color:#8fd0ff}
.h3v28-fold{margin-top:8px;border-top:1px dashed #3e3151;padding-top:6px}
.h3v28-fold>summary{cursor:pointer;color:#cdb9e7;font-size:12px;font-weight:700}
.h3v28-hint{margin-top:6px;color:#8d7ba1;font-size:11px;font-weight:600;line-height:1.5}
/* UI_REFACTOR_01：launcher 退役为【定位剧情导演节点】小按钮（P5 兼容入口）。 */
.h3v28-launch{position:fixed;right:14px;bottom:14px;z-index:9997;min-height:30px;padding:6px 12px;
 border:1px solid #76549a;border-radius:16px;background:#241833;color:#cdb9e7;font:700 12px/1 system-ui,
 "Microsoft YaHei",sans-serif;cursor:pointer;box-shadow:0 6px 16px rgba(0,0,0,.4)}
.h3v28-launch:hover{filter:brightness(1.15)}
.h3v28-launch.hide{display:none}
.h3v28-segno{font-size:17px;font-weight:800;color:#7ee5ad}
`;

function buildPanel() {
  if (panel) return;
  panel = el("div", "h3v28-panel");
  panel.id = PANEL_ID;
  panel.innerHTML = `<style>${CSS}</style>`;

  const head = el("div", "h3v28-head");
  head.append(el("b", "", "【V28 剧情自动导演】"));
  const ver = el("span", "h3v28-ver", "8197 · Gemma4 Text Director · Vision OFF");
  head.append(ver);

  // UI_REFACTOR_01：ComfyUI 1.48 把首个 DOM widget 摆在节点顶(+2px)，LiteGraph
  // 标题栏被面板盖住 → 节点无法按标题拖动。这里把面板头部自身做成拖拽手柄：
  // 纯局部 pointer 监听（不碰 canvas、不碰 ComfyUI 核心），拖动 = 更新 node.pos。
  head.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || !hostNode || !hostNode.graph) return;
    if (ev.target.closest("button,select,input,textarea")) return;
    ev.preventDefault();
    ev.stopPropagation();
    const n = hostNode;
    const startX = ev.clientX, startY = ev.clientY;
    const startPos = [n.pos[0], n.pos[1]];
    try { head.setPointerCapture(ev.pointerId); } catch (e) { /* 老版本无此 API 则忽略 */ }
    const onMove = (e) => {
      const s = app.canvas?.ds?.scale || 1;
      n.pos[0] = startPos[0] + (e.clientX - startX) / s;
      n.pos[1] = startPos[1] + (e.clientY - startY) / s;
      n.graph.setDirtyCanvas(true, true);
    };
    const onUp = () => {
      head.removeEventListener("pointermove", onMove);
      head.removeEventListener("pointerup", onUp);
      head.removeEventListener("pointercancel", onUp);
    };
    head.addEventListener("pointermove", onMove);
    head.addEventListener("pointerup", onUp);
    head.addEventListener("pointercancel", onUp);
  });

  const body = el("div", "h3v28-body");

  // ---- §31 拒绝横幅 -------------------------------------------------------
  dom.gate = el("div", "h3v28-gate");
  const gateActs = el("div", "h3v28-acts");
  gateActs.append(button("停止并释放导演模型", () => stopDirector(true), "danger"));
  gateActs.append(button("回收残留进程", () => stopDirector(false), "danger"));
  dom.gateText = el("div", "", NOT_RELEASED);
  dom.gate.append(dom.gateText, gateActs);

  // ---- ① 剧情自动导演（§13）---------------------------------------------
  const s1 = el("div", "h3v28-sec");
  s1.append(el("h4", "", "① 剧情自动导演"));

  const projRow = el("div", "h3v28-row");
  projRow.append(el("span", "h3v28-lab", "项目"));
  dom.projects = el("select", "h3v28-sel");
  dom.projects.addEventListener("change", async () => {
    state.projectId = dom.projects.value || "";
    localStorage.setItem(STORE_PROJECT, state.projectId);
    loadGate6cDraft();
    await refresh();
  });
  const newBtn = button("＋ 新项目", async () => {
    const title = (dom.goal.value || "").trim().slice(0, 24) || "新故事";
    const out = await call("/project/create", { method: "POST", body: { title } });
    state.projectId = out.project_id || "";
    localStorage.setItem(STORE_PROJECT, state.projectId);
    loadGate6cDraft();
    await refresh();
    flash(`已创建项目 ${state.projectId}`);
  });
  projRow.append(dom.projects);
  s1.append(projRow);
  const projActs = el("div", "h3v28-acts");
  projActs.append(newBtn);
  s1.append(projActs);

  s1.append(el("div", "h3v28-hint", "参考图：沿用当前 9 个中性槽位。编号只表示槽位，不预设人物、服装、动作或时间顺序。"));
  dom.refs = el("div", "");
  s1.append(dom.refs);

  const refUseRow = el("div", "h3v28-row top");
  refUseRow.append(el("span", "h3v28-lab", "参考图用途说明（可选）"));
  dom.referenceUsage = el("textarea", "h3v28-ta sm");
  dom.referenceUsage.placeholder = "按槽位图号说明用途，例如：图1参考人物身份；图3参考姿态。空槽会自动压缩，图号只映射一次。";
  dom.referenceUsage.addEventListener("input", () => { state.editing = true; });
  dom.referenceUsage.addEventListener("blur", () => { state.editing = false; });
  refUseRow.append(dom.referenceUsage);
  s1.append(refUseRow);
  const constraintsRow = el("div", "h3v28-row top");
  constraintsRow.append(el("span", "h3v28-lab", "额外语义约束（可选）"));
  dom.userConstraints = el("textarea", "h3v28-ta sm");
  dom.userConstraints.placeholder = "例如：保持服装和背景；图3不作为首帧。";
  dom.userConstraints.addEventListener("input", saveGate6cDraft);
  constraintsRow.append(dom.userConstraints); s1.append(constraintsRow);

  const goalRow = el("div", "h3v28-row top");
  goalRow.append(el("span", "h3v28-lab", "剧情构想"));
  dom.goal = el("textarea", "h3v28-ta");
  dom.goal.placeholder = "用一段中文说清整部片子要发生什么。例：末班车上的女孩发现车票不见了，"
    + "在空荡的车厢里一路找下去，最后发现被自己夹在了笔记本里。";
  dom.goal.addEventListener("input", () => { state.editing = true; });
  dom.goal.addEventListener("blur", () => { state.editing = false; });
  goalRow.append(dom.goal);
  s1.append(goalRow);

  const dialogueRow = el("div", "h3v28-row top");
  dialogueRow.append(el("span", "h3v28-lab", "台词"));
  dom.dialogue = el("textarea", "h3v28-ta");
  dom.dialogue.placeholder = "原文拆分：粘贴必须逐字保留的台词；参考创作：填写语气、人设、关键词或示例；无台词可留空。";
  dom.dialogue.addEventListener("input", saveGate6cDraft);
  dialogueRow.append(dom.dialogue); s1.append(dialogueRow);
  const dialogueControls = el("div", "h3v28-nums");
  const choice = (label, values) => {
    const row = el("div", "h3v28-row"); row.append(el("span", "h3v28-lab", label));
    const select = el("select", "h3v28-sel");
    values.forEach(v => { const o=el("option", "", v); o.value=v; select.append(o); });
    select.addEventListener("change", saveGate6cDraft); row.append(select); dialogueControls.append(row);
    return select;
  };
  dom.dialogueMode = choice("台词模式", ["原文拆分", "参考创作", "无台词"]);
  dom.dialogueDensity = choice("台词密度", ["少", "正常", "多"]);
  dom.allowPolish = choice("允许模型润色", ["关闭", "开启"]);
  s1.append(dialogueControls);
  loadGate6cDraft();

  const nums = el("div", "h3v28-nums");
  const totalRow = el("div", "h3v28-row");
  totalRow.append(el("span", "h3v28-lab", "目标总时长"));
  dom.total = el("input", "h3v28-in"); dom.total.type = "number"; dom.total.min = "5"; dom.total.step = "1";
  dom.total.value = "60";
  totalRow.append(dom.total);
  const segRow = el("div", "h3v28-row");
  segRow.append(el("span", "h3v28-lab", "每段"));
  dom.seg = el("input", "h3v28-in"); dom.seg.type = "number"; dom.seg.min = "1"; dom.seg.max = "60";
  dom.seg.step = "1"; dom.seg.value = "10";
  segRow.append(dom.seg);
  nums.append(totalRow, segRow);
  s1.append(nums);
  dom.segCount = el("div", "h3v28-hint", "将拆成 6 段。");
  const recalc = () => {
    const n = Math.max(1, Math.ceil((Number(dom.total.value) || 0) / (Number(dom.seg.value) || 1)));
    dom.segCount.textContent = `将拆成 ${n} 段 × ${Number(dom.seg.value) || 0} 秒`
      + `（段数 == 镜头数，系统只维护这一个计数器）。`;
  };
  dom.total.addEventListener("input", recalc); dom.seg.addEventListener("input", recalc);
  s1.append(dom.segCount);

  const styleRow = el("div", "h3v28-row");
  styleRow.append(el("span", "h3v28-lab", "剧情风格"));
  dom.style = el("input", "h3v28-in");
  dom.style.placeholder = "自动（可填：治愈 / 悬疑 / 纪录片感 …）";
  dom.style.value = "";
  styleRow.append(dom.style);
  s1.append(styleRow);

  const contRow = el("div", "h3v28-row top");
  contRow.append(el("span", "h3v28-lab", "镜头连续"));
  const cont = el("div", "h3v28-choice");
  dom.contSame = button("同镜头连续", () => setCont("same_shot"), "secondary");
  dom.contCut = button("允许自然切镜", () => setCont("natural_cut"), "secondary");
  cont.append(dom.contSame, dom.contCut);
  contRow.append(cont);
  s1.append(contRow);
  s1.append(el("div", "h3v28-hint", "同镜头连续：每段开头 1.5–2 秒接住上一段的姿势、速度与镜头，再展开新动作。"
    + "允许自然切镜：只在切镜段做一次衔接，其余同样先延续再展开。"));

  const acts1 = el("div", "h3v28-acts");
  const sourceRow = el("div", "h3v28-row");
  sourceRow.append(el("span", "h3v28-lab", "提示词来源"));
  dom.promptSource = el("select", "h3v28-sel");
  for (const [value, label] of [["MANUAL", "手工（导演关闭）"], ["DIRECTOR", "导演（Gemma4）"]]) {
    const opt = el("option", "", label); opt.value = value; dom.promptSource.append(opt);
  }
  dom.promptSource.addEventListener("change", async () => {
    saveGate6cDraft();
    if (state.projectId) await call("/prompt_source", {method: "POST", body: {
      project_id: state.projectId, prompt_source: dom.promptSource.value}});
    await refresh();
  });
  sourceRow.append(dom.promptSource); s1.append(sourceRow);
  dom.manualBox = el("div", "");
  dom.manualInputs = [];
  function manualFields() {
    const old = dom.manualInputs.map(x => x.value);
    const n = Math.max(1, Math.ceil((Number(dom.total.value) || 60) / (Number(dom.seg.value) || 10)));
    dom.manualBox.replaceChildren(); dom.manualInputs = [];
    for (let i = 0; i < n; i++) {
      dom.manualBox.append(el("div", "h3v28-lab", `第 ${i + 1} 段手工提示词`));
      const input = el("textarea", "h3v28-ta sm"); input.value = old[i] || "";
      input.placeholder = "填写本段最终 H3 提示词";
      input.addEventListener("input", saveGate6cDraft);
      dom.manualInputs.push(input); dom.manualBox.append(input);
    }
  }
  manualFields();
  dom.total.addEventListener("change", manualFields); dom.seg.addEventListener("change", manualFields);
  s1.append(dom.manualBox);
  loadGate6cDraft();
  dom.btnAnalyze = button("校验参考关系", () => validateReferenceUsage(), "warn");
  dom.btnPlan = button("保存手工段落", () => startPhase("plan"), "primary");
  acts1.append(dom.btnAnalyze, dom.btnPlan);
  s1.append(acts1);
  s1.append(el("div", "h3v28-hint", "Gemma4 只读取槽位映射、用途说明和剧情文本，不读取图片像素，也不猜测图片内容。"));
  dom.phaseLines = el("div", "h3v28-lines");
  s1.append(dom.phaseLines);

  // ---- ② 剧情计划（§25）--------------------------------------------------
  const s2 = el("div", "h3v28-sec");
  s2.append(el("h4", "", "② 剧情计划"));
  dom.planMeta = el("div", "");
  dom.segList = el("ul", "h3v28-list");
  s2.append(dom.planMeta, dom.segList);

  // ---- ③ 当前段（§25）----------------------------------------------------
  const s3 = el("div", "h3v28-sec");
  s3.append(el("h4", "", "③ 当前段"));
  dom.curNo = el("div", "h3v28-segno", "—");
  const curHead = el("div", "h3v28-kv");
  dom.curStatus = el("span", "");
  curHead.append(el("span", "h3v28-lab", "状态"), dom.curStatus);
  s3.append(curHead);

  const beatRow = el("div", "h3v28-row top");
  beatRow.append(el("span", "h3v28-lab", "剧情"));
  dom.beat = el("textarea", "h3v28-ta sm");
  dom.beat.addEventListener("input", () => { state.editing = true; });
  dom.beat.addEventListener("blur", () => { state.editing = false; });
  beatRow.append(dom.beat);
  s3.append(beatRow);
  dom.curKv = el("div", "");
  s3.append(dom.curKv);

  const fold = el("details", "h3v28-fold");        // §25：当前提示词默认折叠
  fold.append(el("summary", "", "最终 H3 提示词（高级）"));
  dom.prompt = el("textarea", "h3v28-ta");
  dom.prompt.spellcheck = false;
  dom.prompt.addEventListener("input", () => { state.editing = true; });
  dom.prompt.addEventListener("blur", () => { state.editing = false; });
  const editActs = el("div", "h3v28-acts");
  editActs.append(button("保存并重新编译本段及其后", () => saveEdit(), "warn"));
  fold.append(dom.prompt, editActs);
  fold.append(el("div", "h3v28-hint", "手工编辑只影响当前段及其之后的段落；已被接受的段不会被改写（§27/§30）。"));
  s3.append(fold);

  const acts3 = el("div", "h3v28-acts");
  dom.btnGen = button("生成当前段", () => generate(false), "primary");
  dom.btnRe = button("重新生成", () => generate(true), "warn");
  dom.btnAcc = button("接受并下一步", () => accept(), "primary");
  acts3.append(dom.btnGen, dom.btnRe, dom.btnAcc);
  s3.append(acts3);
  const sameSeed = el("label", "h3v28-check");
  dom.sameSeed = el("input", ""); dom.sameSeed.type = "checkbox";
  sameSeed.append(dom.sameSeed, el("span", "", "重生成时保持种子不变（默认换一个）"));
  s3.append(sameSeed);
  s3.append(el("div", "h3v28-hint", "看完片子再决定：接受并下一步只推进游标，绝不会自动开始生成下一段。"));
  dom.candBox = el("div", "");
  s3.append(dom.candBox);
  dom.genStatus = el("div", "h3v28-status", "等待计划。");
  s3.append(dom.genStatus);

  // ---- 尾部：诊断 ---------------------------------------------------------
  const s4 = el("div", "h3v28-sec");
  s4.append(el("h4", "", "运行状态"));
  dom.diag = el("div", "");
  const fold2 = el("details", "h3v28-fold");
  fold2.append(el("summary", "", "导演台日志（最近 24 行）"));
  dom.logs = el("div", "h3v28-lines");
  fold2.append(dom.logs);
  s4.append(dom.diag, fold2);

  body.append(dom.gate, s1, s2, s3, s4);
  panel.append(head, body);
  stopCanvasEvents(panel);
  installWheelPolicy(panel);
  panel.classList.add("open");   // 节点内常显（floating 时代的开合已退役）

  // UI_REFACTOR_01：floating 面板退役（FLOATING_DIRECTOR_PANEL = DISABLED）。
  // 只保留一个 P5 允许的兼容入口：右下角【定位剧情导演节点】小按钮。
  launcher = el("button", "h3v28-launch", "定位剧情导演节点");
  launcher.type = "button";
  launcher.id = LAUNCHER_ID;
  launcher.addEventListener("click", (ev) => {
    ev.preventDefault(); ev.stopPropagation();
    locateDirectorNode();
  });
  document.body.append(launcher);
  recalc();
}

/** floating 时代的开合函数；节点内常显后仅保留兼容语义（不隐藏面板）。 */
function setOpen(open) {
  buildPanel();
  panel.classList.add("open");
  if (open) refresh();
}

function flash(msg) {
  dom.genStatus.className = "h3v28-status";
  dom.genStatus.textContent = msg;
}
function banner(msg, kind) {
  dom.genStatus.className = `h3v28-status ${kind === "bad" ? "bad" : "warn"}`;
  dom.genStatus.textContent = msg;
}

function setCont(mode) {
  state.cont = mode;
  dom.contSame.classList.toggle("on", mode === "same_shot");
  dom.contCut.classList.toggle("on", mode === "natural_cut");
}

// ---------------------------------------------------------------------------
// 画布 <-> 后端
// ---------------------------------------------------------------------------
function referenceNames() {
  return NODE.refImages.map((id) => {
    const n = byId(id);
    const v = widgetValue(n, "image");
    return typeof v === "string" ? v.trim() : "";
  });
}
function renderRefs(list, missing) {
  dom.refs.innerHTML = "";
  const names = referenceNames();
  const resolved = new Map((list || []).map((im) => [im.slot_index, im]));
  names.forEach((nm, i) => {
    const row = el("div", "h3v28-ref");
    const ok = Boolean(list) && resolved.has(i + 1);
    row.className = `h3v28-ref ${ok || !nm ? "" : "miss"}`;
    row.append(el("span", "", `参考图 ${i + 1}`));
    let label;
    if (list == null) label = nm ? `画布上：${nm}` : "空";
    else label = ok ? (resolved.get(i + 1).filename || nm)
                    : (nm ? `后端找不到：${nm}` : "空");
    row.append(el("b", "", label));
    dom.refs.append(row);
  });
  if (missing && missing.length) {
    dom.refs.append(el("div", "h3v28-hint", "后端读不到这些素材文件：" + missing.join("、")));
  }
}

// ---------------------------------------------------------------------------
// PHASE A：分析 / 规划
// ---------------------------------------------------------------------------
async function startPhase(kind) {
  if (!state.projectId) {
    banner("请先点【＋ 新项目】创建一个项目。", "warn");
    return;
  }
  const names = referenceNames();
  if (!names.filter(Boolean).length) {
    banner("参考图还是空的：请先在 9 个中性参考图槽里上传素材。", "bad");
    return;
  }
  const goal = (dom.goal.value || "").trim();
  if (kind === "plan" && dom.promptSource.value === "DIRECTOR" && !goal) {
    banner("请先写下总剧情构想。", "bad");
    return;
  }
  state.busy = kind === "plan" ? "规划剧情中" : "分析参考图中";
  dom.btnPlan.disabled = true; dom.btnAnalyze.disabled = true;
  dom.phaseLines.textContent = "";
  try {
    const picked = await call("/pick_images", { method: "POST", body: { image_names: names } });
    renderRefs(picked.images, picked.missing);
    if (!(picked.images || []).length) {
      banner("画布上填的素材在后端找不到实际文件，无法建立参考映射。请重新上传一次参考图。", "bad");
      return;
    }
    const body = {
      project_id: state.projectId,
      prompt_source: dom.promptSource.value,
      manual_prompts: dom.manualInputs.map(x => x.value),
      generation_settings: {seed: Number(widgetValue(byId(NODE.seed), "seed")) || null},
      story_goal: goal,
      image_names: names,
      active_slots: names.map((name, index) => name ? index + 1 : null).filter(Boolean),
      reference_usage: (dom.referenceUsage.value || "").trim(),
      user_constraints: (dom.userConstraints.value || "").trim(),
      total_seconds: Number(dom.total.value) || 60,
      segment_seconds: Number(dom.seg.value) || 10,
      style: (dom.style.value || "").trim() || "auto",
      continuation_mode: state.cont || "same_shot",
      dialogue_mode: dom.dialogueMode.value || "无台词",
      source_dialogue: dom.dialogue.value || "",
      dialogue_density: dom.dialogueDensity.value || "正常",
      allow_polish: dom.allowPolish.value === "开启",
    };
    const out = await call(kind === "plan" ? "/plan" : "/analyze", { method: "POST", body });
    await pollTask(out.task_id, kind);
  } catch (err) {
    banner(`${kind === "plan" ? "规划" : "分析"}失败：${err.message}`, "bad");
  } finally {
    state.busy = "";
    dom.btnPlan.disabled = false; dom.btnAnalyze.disabled = false;
    await refresh();
  }
}

async function validateReferenceUsage() {
  const names = referenceNames();
  try {
    const out = await call("/core/dry_run", { method: "POST", body: {
      active_slots: names.map((name, index) => name ? index + 1 : null).filter(Boolean),
      reference_usage: (dom.referenceUsage.value || "").trim(),
      story_goal: (dom.goal.value || "").trim(),
      total_seconds: Number(dom.total.value) || 60,
      segment_seconds: Number(dom.seg.value) || 10,
    }});
    dom.phaseLines.textContent = JSON.stringify(out.ACTIVE_REFERENCE_MAP || [], null, 2);
    flash(`参考关系通过：${(out.ACTIVE_REFERENCE_MAP || []).length} 张有效参考图；时间轴=${out.REFERENCE_TIMELINE || "NONE"}`);
  } catch (err) {
    banner(`参考关系失败：${err.message}`, "bad");
  }
}

async function pollTask(taskId, kind) {
  const deadline = Date.now() + 25 * 60 * 1000;      // 27B 加载 + 全片规划
  while (Date.now() < deadline) {
    const t = await call("/task", { query: { task_id: taskId } });
    dom.phaseLines.textContent = (t.lines || []).join("\n");
    dom.phaseLines.scrollTop = dom.phaseLines.scrollHeight;
    if (t.status === "DONE") {
      flash(kind === "plan" ? (dom.promptSource.value === "MANUAL" ? "手工段落已保存，可以连续生成。" : "全片计划已生成，导演模型已卸载。可以开始逐段生成了。")
                            : "参考关系已校验。Gemma4 不读取图片像素。");
      return t;
    }
    if (t.status === "FAILED_RECOVERABLE") throw new Error(t.result?.message || "导演生成失败，手工提示词和连续生成功能未受影响。");
    if (t.status === "ERROR") throw new Error(t.error || "导演任务失败");
    await new Promise((r) => setTimeout(r, 1200));
  }
  throw new Error("导演任务超过 25 分钟仍未结束，请在日志里检查");
}

// ---------------------------------------------------------------------------
// PHASE B：生成 / 重生成 / 接受
// ---------------------------------------------------------------------------
function applyInstruction(instr) {
  const problems = [];
  const console159 = byId(NODE.console);
  // Which node to write is decided by the BACK END, not by these constants: the
  // instruction carries prompt_text_node / selector_node / load_node / save_node
  // / chain_node, and NODE.* is only the fallback for an older instruction that
  // omits them. Without this, a renumbering on one side would silently drive the
  // wrong widget while the panel still reported success.
  const mc = instr.motion_context || {};
  const pick = (id, fallback) => (Number.isFinite(Number(id)) && Number(id) > 0
    ? byId(Number(id)) : byId(fallback));
  const promptNode = pick(instr.prompt_text_node, NODE.prompt);
  const durNode = byId(NODE.duration);
  const seedNode = byId(NODE.seed);
  const contNode = pick(instr.continuation?.selector_node, NODE.continuation);
  const saveNode = pick(mc.save_node, NODE.mcSave);
  const loadNode = pick(mc.load_node, NODE.mcLoad);
  const chainNode = pick(mc.chain_node, NODE.mcChain);
  if (!promptNode || !seedNode || !contNode || !saveNode || !loadNode) {
    problems.push("当前画布不是 V27 导演台（缺 138/142/992/995/996 之一），无法驱动。");
    return problems;
  }
  // 提示词：走 V27 自己的同步链 N138 -> N915 -> N136
  const canonicalPrompt = instr.CANONICAL_H3_PROMPT ?? instr.SUBMISSION_PROMPT ?? instr.prompt;
  if (!setWidget(widget(promptNode, "value"), canonicalPrompt)) problems.push("提示词写入失败。");
  // 时长（秒）：帧数仍由 V27 的 N131 公式派生，V28 绝不自己算帧
  if (durNode) setWidget(widget(durNode, "value"), Number(instr.duration_sec));
  // 种子：先把「生成后」控制设成固定，再写种子，否则提交时会被重新随机化
  const seedW = widget(seedNode, "seed");
  const control = seedControlWidget(seedNode);
  if (control) {
    if (!setWidget(control, fixedSeedOption(control))) {
      problems.push("种子控制控件写入失败。");
    }
  } else {
    problems.push("找不到种子控制控件：提交时种子可能被重新随机，请手动设为固定。");
  }
  if (seedW) setWidget(seedW, Number(instr.seed));
  // 接续选择器（必须触发 callback，V27 靠它改写旁路）
  if (!setWidget(widget(contNode, "接续生产"), instr.continuation?.value)) {
    problems.push("接续选择器 992 上没有「接续生产」控件，无法写入。");
  }
  if (instr.continuation?.strength) {
    setWidget(widget(contNode, "接续强度"), instr.continuation.strength);
  }
  // Motion Context：存档序号 == 本段，读取序号 == 上一已接受段，两者由状态机独占
  if (!setWidget(widget(saveNode, "clip_index"), Number(mc.save_clip_index))) problems.push("995 clip_index 写入失败。");
  if (!setWidget(widget(loadNode, "clip_index"), Number(mc.load_clip_index))) problems.push("996 clip_index 写入失败。");
  if (chainNode) setWidget(widget(chainNode, "segments"), Number(mc.chain_segments));
  // 与 V27 每次提交前完全一致的一步：把傻瓜控制台拨回「只跑一采」
  if (console159) setWidget(widget(console159, "当前操作"), OPERATION_DEFAULT);
  return problems;
}

async function sha256Text(text) {
  const bytes = new TextEncoder().encode(String(text ?? ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
}

function seedControlWidget(seedNode) {
  const list = seedNode?.widgets || [];
  const seedW = list.find((w) => w.name === "seed");
  const byName = list.find((w) => w.name === "control_after_generate");
  if (byName) return byName;
  // P11 TEST6 / BUG-8：候选值清单在这个前端里读不到（见 seedControlOptions 的注释），
  // 所以先按「当前取值本身属于随机化枚举」定位——与 V27 h3_foolproof_v3_dashboard.js
  // 的 seedControlWidget() 同一手法（那边实测 widgets = [seed(number), fixed(combo)]，
  // 按名字 control_after_generate 必然 miss）。
  const bySemantics = list.find((w) => w !== seedW && w.type === "combo"
    && SEED_CONTROL_VALUES.has(String(w.value)));
  if (bySemantics) return bySemantics;
  const combos = list.filter((w) => w !== seedW && w.type === "combo");
  return combos.find((w) => seedControlOptions(w).some((v) => FIXED_SEED_LABELS.includes(String(v))))
    || combos[0] || null;
}
/** combo 的候选值清单。
 *  P11 TEST6 / BUG-8：前端 1.52.7 把候选值放在 `widget.options.values`，
 *  `widget.values` 是 **undefined**（8197 实测：SeedNode 的 fixed 控件
 *  options.values = ["fixed","increment","decrement","randomize"]，而 w.values 为空）。
 *  旧代码只读 `control.values`，于是 fixedSeedOption() 返回 undefined，
 *  setWidget() 又因为 combo 不是数值控件而照单全收并回 true ——
 *  面板报告「写入成功」，实际把种子控制控件刷成了空值，提交时是否重新随机全凭运气。
 *  台架里 stub 的 widget 带 values 数组，所以 TEST5-UI(A) 72/72 抓不到这一条。 */
function seedControlOptions(control) {
  const list = control?.options?.values ?? control?.values ?? [];
  return Array.isArray(list) ? list : [];
}
function fixedSeedOption(control) {
  const opts = seedControlOptions(control);
  const hit = opts.find((v) => FIXED_SEED_LABELS.includes(String(v)));
  if (hit != null) return hit;
  // 清单确实拿不到时按 SeedNode io schema 的字面量写，而不是写 undefined。
  return opts.length ? opts[0] : "fixed";
}

/** 折叠区里的文本是否真的和后端编译出来不一样（避免把等价的空白改动当编辑）。
 *  比对基准在点击这一刻重新取一次，不依赖上一次刷新留下的缓存。 */
async function promptOverride(text, segmentId) {
  const edited = String(text || "").trim();
  if (!edited || !segmentId) return "";
  try {
    const pt = await call("/prompt", { query: { project_id: state.projectId, segment_id: segmentId } });
    if (edited === String(pt.prompt || "").trim()) return "";
  } catch (err) {
    console.warn("[H3 V28] 无法比对当前提示词，按手工编辑处理", err);
  }
  return edited;
}

async function generate(isReroll) {
  if (!state.projectId) { banner("请先创建项目。", "bad"); return; }
  const segId = state.card?.view?.current_segment || 0;
  const override = isReroll ? "" : await promptOverride(dom.prompt.value, segId);
  const rerollUsesSameSeed = isReroll && dom.sameSeed.checked;
  state.busy = isReroll ? "准备重生成" : "准备生成";
  dom.btnGen.disabled = true; dom.btnRe.disabled = true; dom.btnAcc.disabled = true;
  try {
    let instr;
    if (isReroll) {
      const out = await call("/reroll", { method: "POST",
        body: { project_id: state.projectId, same_seed: rerollUsesSameSeed } });
      instr = out.instruction;
    } else {
      const out = await call("/prepare", { method: "POST",
        body: { project_id: state.projectId,
                same_seed: dom.sameSeed.checked,
                prompt_override: override,
                manual_prompts: dom.promptSource.value === "MANUAL" ? dom.manualInputs.map(x => x.value) : undefined } });
      instr = out.instruction;
    }
    if (!instr) throw new Error("后端没有返回段落指令");
    const problems = applyInstruction(instr);
    if (problems.length) { banner("写入画布失败：\n• " + problems.join("\n• "), "bad"); return; }
    await settleWidgets();
    const promptReadBack = String(widgetValue(byId(NODE.prompt), "value") ?? "");
    const submissionHash = await sha256Text(promptReadBack);
    if (!instr.PREVIEW_EQUALS_SUBMISSION
        || submissionHash !== String(instr.SUBMISSION_PROMPT_SHA256 || "")) {
      throw new Error("最终 Prompt 预览与画布提交内容哈希不一致，已禁止排队。");
    }
    const readBack = Number(widgetValue(byId(NODE.seed), "seed"));
    const submittedSeed = Number.isFinite(readBack) ? readBack : Number(instr.seed);
    state.lastSubmittedSeed = submittedSeed;
    await call("/submitted", { method: "POST",
      body: { project_id: state.projectId, seed: submittedSeed } });
    if (submittedSeed !== Number(instr.seed)) {
      banner(`注意：画布上的种子回读为 ${submittedSeed}，与状态机记录的 ${instr.seed} 不一致，`
        + `已按画布实际值登记。请确认 N142 的「生成后」控制是固定。`, "warn");
    }
    state.flight = { segment_id: instr.segment_id, seed: instr.seed, prompt_id: null };
    await app.queuePrompt(0, 1);          // 唯一的排队点：用户按下的这一颗按钮
    flash(`已提交第 ${instr.segment_id} 段（种子 ${instr.seed}，接续自 `
      + `${instr.motion_context?.load_clip_index ? "第" + instr.motion_context.load_clip_index + "段" : "无"}）。`
      + `生成完再由您决定接受还是重生成。`);
  } catch (err) {
    if (refusalKind(err) === "prompt_structure") showStructureRefusal(err.message);
    else if (isGateRefusal(err)) showGate(err.message);
    else banner(`生成失败：${err.message}`, "bad");
  } finally {
    state.busy = "";
    await refresh();
  }
}

// The backend labels every 409 with `kind` (v28_routes._err). Labelling beats
// reading the Chinese sentence: the §31 red bar underneath offers
// 【停止并释放导演模型】/【回收残留进程】, and those are the wrong two buttons to
// put next to a prompt that is missing `retention_analysis:`.
function refusalKind(err) {
  return (err?.status === 409 && err?.payload?.kind) || "";
}
function showStructureRefusal(msg) {
  banner(`已拒绝提交（未排队，未消耗额度）：\n${msg || "提示词未通过 H3 结构校验"}`, "bad");
  flash("请在「编辑本段提示词」里补齐上面点名的段落；清空编辑框可回到编译器生成的版本。");
}

function isGateRefusal(err) {
  const kind = refusalKind(err);
  if (kind) return kind === "vram_gate";
  const msg = String(err?.message || "");
  return msg.includes(NOT_RELEASED) || err?.status === 409 && /尚未释放|未释放/.test(msg);
}
function showGate(msg) {
  dom.gate.classList.add("on");
  dom.gateText.textContent = msg || NOT_RELEASED;
  banner(msg || NOT_RELEASED, "bad");
}

async function accept() {
  try {
    const out = await call("/accept", { method: "POST", body: { project_id: state.projectId } });
    flash(`第 ${out.last_accepted_segment} 段已接受，游标到第 ${out.current_segment} 段。`
      + `未排队（要看片确认后再点【生成当前段】）。`);
  } catch (err) {
    banner(`接受失败：${err.message}`, "bad");
  }
  await refresh();
}

async function saveEdit() {
  const seg = state.card?.view?.current_segment;
  if (!seg) { banner("还没有当前段。", "bad"); return; }
  // P11 TEST5-UI / BUG-6：折叠区里放的是**编译稿**（六段骨架，由 refresh() 调 /prompt
  // 读回后填进 textarea），而编译器只把「非结构化的 seg.prompt」当本段动作句，
  // 结构化就退回中文 beat（v28_prompt_compiler.first_action_sentence）。所以过去只要
  // 按一下【保存编辑】——哪怕什么都没改——编译稿就会被写回 seg["prompt"]，下一版编译
  // 里那句英文动作句会被中文 beat 顶掉（实测 1748 -> 1613 字符，动作句整段消失）。
  // 这里复用提交路径已经在用的「等价即未编辑」判据（promptOverride）：
  // 只有真的改过文本才把 prompt 发出去，只改梗概的保存不再动动作句。
  const promptToSend = await promptOverride(dom.prompt.value, seg);
  try {
    const out = await call("/edit", { method: "POST",
      body: { project_id: state.projectId, segment_id: seg,
              beat: dom.beat.value || "", prompt: promptToSend } });
    flash(`第 ${seg} 段已保存${promptToSend ? "（含提示词改写）" : "（提示词未改，动作句保持原样）"}，`
      + `重新编译了 ${out.recompiled.join("、")} 段。`);
  } catch (err) {
    banner(`保存失败：${err.message}`, "bad");
  }
  await refresh();
}

async function stopDirector(ownedOnly) {
  try {
    const out = ownedOnly ? await call("/stop", { method: "POST", body: {} })
                          : await call("/reap", { method: "POST", body: {} });
    const rel = out.release || out;
    const verdict = rel.verdict || (out.reaped ? "RELEASED" : "UNKNOWN");
    const detail = rel.detail || out.skipped || "";
    flash(`释放结论：${verdict}${detail ? "（" + detail + "）" : ""}`);
    if (!ownedOnly) dom.gate.classList.remove("on");
  } catch (err) {
    banner(`释放失败：${err.message}`, "bad");
  }
  await refresh();
}

// ---------------------------------------------------------------------------
// 生成结果：WS 事件 -> /history -> /candidate
// ---------------------------------------------------------------------------
let bound = false;
function bindExecutionEvents() {
  if (bound) return;
  bound = true;
  api.addEventListener("execution_start", (ev) => {
    const pid = ev?.detail?.prompt_id;
    if (state.flight && pid && !state.flight.prompt_id) state.flight.prompt_id = pid;
  });
  api.addEventListener("execution_success", async (ev) => {
    const pid = ev?.detail?.prompt_id;
    const flight = state.flight;
    if (!flight) return;
    if (flight.prompt_id && pid && flight.prompt_id !== pid) return;
    state.flight = null;
    await onGenerated(pid || flight.prompt_id, flight.segment_id);
  });
  api.addEventListener("execution_error", async (ev) => {
    const detail = ev?.detail || {};
    if (!state.flight) return;
    if (detail.prompt_id && state.flight.prompt_id && detail.prompt_id !== state.flight.prompt_id) return;
    state.flight = null;
    const msg = detail.exception_message || detail.node_type || "生成失败";
    try {
      await call("/generation_error", { method: "POST",
        body: { project_id: state.projectId, message: `${msg}（节点 ${detail.node_id || "?"}）` } });
    } catch (e) { /* 状态机会在下次刷新时显示真实状态 */ }
    banner(`第 ${flight.segment_id} 段生成失败：${msg}`, "bad");
    await refresh();
  });
  api.addEventListener("execution_interrupted", async (ev) => {
    if (!state.flight) return;
    state.flight = null;
    try {
      await call("/generation_error", { method: "POST",
        body: { project_id: state.projectId, message: "用户中断了本次生成" } });
    } catch (e) { /* 同上 */ }
    banner("本次生成已被中断；已接受的段没有变化。", "warn");
    await refresh();
  });
}

function videoExt(name) {
  return /\.(mp4|webm|mkv|mov|m4v)$/i.test(String(name || ""));
}
async function onGenerated(promptId, segmentId) {
  if (!promptId) {
    banner("执行结束但没有拿到 prompt_id，请到任务历史里确认后再决定。", "warn");
    await refresh();
    return;
  }
  let media = [];
  try {
    const r = await fetch(api.apiURL(`/history/${encodeURIComponent(promptId)}`),
                          { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    const outs = (j?.[promptId] || {}).outputs || {};
    for (const nid of Object.keys(outs)) {
      const o = outs[nid] || {};
      for (const key of ["videos", "images", "gifs", "animated"]) {
        for (const item of (o[key] || [])) {
          if (item && videoExt(item.filename)) media.push(item);
        }
      }
    }
  } catch (err) {
    console.warn("[H3 V28] 读取 history 失败", err);
    banner(`执行成功，但读取输出清单失败：${err.message}`, "warn");
  }
  if (!media.length) {
    banner("执行成功，但没有在输出里找到视频文件；请到任务历史里确认后再决定。", "warn");
    await refresh();
    return;
  }
  const first = media[0];
  const qs = new URLSearchParams({ filename: first.filename,
                                   subfolder: first.subfolder || "",
                                   type: first.type || "output" });
  const viewUrl = api.apiURL(`/view?${qs.toString()}`);
  try {
    await call("/candidate", { method: "POST",
      body: { project_id: state.projectId, video: viewUrl,
              seed: state.lastSubmittedSeed ?? undefined,
              prompt_id: promptId } });
    flash(`第 ${segmentId ?? "?"} 段已生成（${first.filename}），正在等您看片确认。`);
  } catch (err) {
    banner(`候选登记失败：${err.message}`, "bad");
  }
  await refresh();
}

function nextFrame(times = 1) {
  let p = Promise.resolve();
  for (let i = 0; i < times; i += 1) {
    p = p.then(() => new Promise((r) => requestAnimationFrame(() => r())));
  }
  return p;
}
/** 给运行时的 widget callback 一拍生效时间。
 *  页面被遮挡时 requestAnimationFrame 可能永远不触发（本项目实测过），
 *  所以用 race 兜底，绝不让【生成当前段】卡死在这里。 */
function settleWidgets() {
  return Promise.race([nextFrame(2), new Promise((r) => setTimeout(r, 400))]);
}

// ---------------------------------------------------------------------------
// 刷新：一次 /state 拿到整张卡片
// ---------------------------------------------------------------------------
const STATUS_ZH = {
  PLANNED: "等待规划", READY: "等待生成", GENERATING: "正在生成",
  CANDIDATE_READY: "已生成，待确认", ACCEPTED: "已接受", RETRY_PENDING: "准备重生成",
  COMPLETE: "全部完成", ERROR: "本段失败", NO_SESSION: "还没有项目",
};
function statusChip(status) {
  const cls = status === "GENERATING" ? "run"
    : status === "ERROR" ? "err"
    : status === "CANDIDATE_READY" || status === "COMPLETE" ? "ok" : "";
  return el("span", `h3v28-chip ${cls}`, STATUS_ZH[status] || status || "—");
}

async function refresh() {
  buildPanel();
  if (!BASE) BASE = await probeBase();
  // 项目下拉
  try {
    const ps = await call("/projects");
    const list = ps.projects || [];
    dom.projects.innerHTML = "";
    if (!list.length) dom.projects.append(el("option", "", "（还没有项目，点右边新建）"));
    for (const p of list) {
      const o = el("option", "", `${p.title || p.project_id} · ${STATUS_ZH[p.status] || p.status}`);
      o.value = p.project_id;
      dom.projects.append(o);
    }
    if (state.projectId) dom.projects.value = state.projectId;
    if (dom.projects.value !== state.projectId && list.length) {
      state.projectId = "";
      localStorage.removeItem(STORE_PROJECT);
    }
  } catch (err) {
    dom.diag.textContent = `接口状态：${err.message}`;
    return;
  }
  if (!state.projectId) {
    dom.diag.textContent = "还没有选择项目。";
    dom.curStatus.replaceChildren(statusChip("NO_SESSION"));
    dom.segList.innerHTML = "";
    dom.planMeta.innerHTML = "";
    return;
  }
  let card;
  try { card = await call("/state", { query: { project_id: state.projectId } }); }
  catch (err) { dom.diag.textContent = `读取项目状态失败：${err.message}`; return; }
  state.card = card;
  dom.promptSource.value = card.prompt_source || "MANUAL";
  const manual = dom.promptSource.value === "MANUAL";
  dom.manualBox.hidden = !manual;
  dom.btnPlan.textContent = manual ? "保存手工段落" : "生成／重试导演计划";
  // Only hydrate an empty draft. Director results never replace manual inputs.
  if (dom.manualInputs.every(x => !x.value) && card.manual?.prompts?.length) {
    dom.manualInputs.forEach((input, i) => { input.value = card.manual.prompts[i] || ""; });
  }
  if (card.director?.director_status === "FAILED_RECOVERABLE" && !manual) {
    banner(card.director.message, "bad");
  }
  const view = card.view || null;

  // §31 闸门：以状态机给的结论为准
  if (view && view.gate && view.gate.generation_allowed === false) showGate(view.gate.message);
  else dom.gate.classList.remove("on");

  // ② 计划
  dom.planMeta.innerHTML = "";
  dom.segList.innerHTML = "";
  if (view) {
    const meta = el("div", "h3v28-kv");
    meta.append(el("span", "h3v28-lab", "当前"), el("b", "", `第 ${view.current_segment} / ${view.segment_count} 段`));
    dom.planMeta.append(meta);
    const meta2 = el("div", "h3v28-kv");
    meta2.append(el("span", "h3v28-lab", "已接受到"),
                 el("b", "", view.last_accepted_segment ? `第 ${view.last_accepted_segment} 段` : "还没有"));
    dom.planMeta.append(meta2);
    const meta3 = el("div", "h3v28-kv");
    meta3.append(el("span", "h3v28-lab", "连续方式"),
                 el("b", "", view.continuation_mode === "natural_cut" ? "允许自然切镜" : "同镜头连续"));
    dom.planMeta.append(meta3);
    if (!state.editing && !dom.goal.value.trim()) {
      // 只在框里空的时侯回填计划里存的构想，绝不覆盖用户正在起草的新构想。
      dom.goal.value = view.story_goal || "";
    }
    for (const s of (view.segments || [])) {
      const li = el("li", "h3v28-seg");
      const isCur = s.id === view.current_segment;
      const isAcc = s.locked || (s.id || 0) <= (view.last_accepted_segment || 0);
      if (isCur) li.classList.add("cur"); else if (isAcc) li.classList.add("acc");
      li.append(el("i", "", String(s.id)));
      li.append(el("span", "", `${s.beat || "（无剧情）"}｜${s.dialogue_summary || "无台词"}`));
      const tail = el("i", "", `${s.duration ?? "?"}s${isAcc ? " · 已接受" : ""}`);
      li.append(tail);
      if (!isCur && isAcc) {
        const back = button("回到此段", () => resetTo(s.id), "danger");
        back.style.minHeight = "22px"; back.style.padding = "2px 6px"; back.style.fontSize = "11px";
        li.append(back);
      }
      dom.segList.append(li);
    }
    // 参考画像
    if (card.profile) {
      const line = el("div", "h3v28-hint", `导演看到的：${(card.profile.pictures || []).length} 张图、`
        + `${(card.profile.subjects || []).length} 个主体、${(card.profile.uncertain || []).length} 条不确定项。`);
      dom.planMeta.append(line);
    }
  } else {
    const p = el("div", "h3v28-hint", card.no_plan || "还没有剧情计划。");
    dom.planMeta.append(p);
  }

  // ③ 当前段
  dom.curNo.textContent = view ? `第 ${view.current_segment} 段 / 共 ${view.segment_count} 段` : "—";
  dom.curStatus.replaceChildren(statusChip(view?.status));
  const cur = view?.current || {};
  if (!state.editing) {
    dom.beat.value = cur.beat || "";
  }
  dom.curKv.innerHTML = "";
  const kv = (lab, val) => {
    const r = el("div", "h3v28-kv");
    r.append(el("span", "h3v28-lab", lab), el("b", "", val == null || val === "" ? "—" : String(val)));
    return r;
  };
  dom.curKv.append(kv("本段时长", cur.duration != null ? `${cur.duration} 秒` : null));
  const zh = cur.user_display_zh || {};
  dom.curKv.append(kv("本段目标", zh.objective));
  dom.curKv.append(kv("起始状态", zh.start_state));
  dom.curKv.append(kv("动作推进", zh.action_progression));
  dom.curKv.append(kv("人物调度", zh.blocking));
  dom.curKv.append(kv("镜头", zh.camera));
  dom.curKv.append(kv("台词", zh.dialogue));
  dom.curKv.append(kv("声音", zh.sound));
  dom.curKv.append(kv("参考图用途", zh.reference_usage));
  dom.curKv.append(kv("段尾状态", zh.end_state));
  const risk = cur.render_risk || {};
  dom.curKv.append(kv("渲染风险", `身体=${risk.body_geometry || "LOW"} 遮挡=${risk.occlusion || "LOW"} 快速全身=${risk.fast_full_body_motion ? "是" : "否"}`));
  for (const note of (cur.planning_advisories || [])) {
    dom.curKv.append(kv("非阻断建议", note));
  }
  const dirs = cur.directives || {};
  if (Object.keys(dirs).length) {
    dom.curKv.append(kv("镜头指令", Object.entries(dirs).map(([k, v]) => `${k}=${v}`).join(" ")));
  }
  if (view?.attempt) dom.curKv.append(kv("本段第几次尝试", view.attempt));
  for (const e of (view?.errors || []).slice(-2)) {
    dom.curKv.append(kv("最近错误", `${e.segment_id ? "第" + e.segment_id + "段 " : ""}${e.detail}`));
  }
  if (view?.candidate) {
    dom.curKv.append(kv("候选种子", view.candidate.seed));
    // BUG-9 加性显示：计划帧数（= expected_frames，由 V27 N131 公式派生）与实际交付帧数对照，
    // 让人工看片时能看到「计划 vs 实交」的缺口。expected_frames 语义不被改动。
    dom.curKv.append(kv("计划帧数", view.candidate.expected_frames));
    dom.curKv.append(kv("实际交付帧数", view.candidate.actual_delivered_frames));
    if (view.candidate.context_note) {
      dom.curKv.append(kv("接续说明", view.candidate.context_note));
    }
  }

  if (view) {
    try {
      const pt = await call("/prompt", { query: { project_id: state.projectId, segment_id: view.current_segment } });
      if (!state.editing) dom.prompt.value = pt.prompt || "";
    } catch (err) {
      dom.prompt.value = `（读取提示词失败：${err.message}）`;
    }
  }

  // 按钮可用性完全由状态机决定，不由前端猜
  const st = view?.status;
  const planned = Boolean(view);
  const generating = st === "GENERATING";
  dom.btnGen.disabled = !planned || generating || st === "COMPLETE" || st === "CANDIDATE_READY";
  if (!manual && ["RUNNING", "FAILED_RECOVERABLE"].includes(card.director?.director_status)) dom.btnGen.disabled = true;
  dom.btnRe.disabled = !(st === "CANDIDATE_READY" || st === "ERROR") || generating;
  dom.btnAcc.disabled = st !== "CANDIDATE_READY";
  if (st === "COMPLETE") flash("全部段落都已接受，这部片子做完了。");
  else if (generating) flash(`第 ${view?.current_segment} 段正在生成中……`);
  else if (st === "CANDIDATE_READY") flash(`第 ${view?.current_segment} 段已生成，请看片后选择接受或重生成。`);

  // 候选播放
  dom.candBox.innerHTML = "";
  const cand = view?.candidate;
  if (cand && cand.video && typeof cand.video === "string" && cand.video.startsWith("/")) {
    const v = el("video", "h3v28-vid");
    v.src = cand.video; v.controls = true; v.loop = true; v.playsInline = true;
    dom.candBox.append(v);
    const links = el("div", "h3v28-links");
    links.append(el("a", "", cand.video.split("?")[0].split("/").pop() || "视频文件"));
    dom.candBox.append(links);
  } else if (cand?.video) {
    dom.candBox.append(el("div", "h3v28-hint", "候选：" + cand.video));
  }

  // 运行状态
  const rel = card.release || {};
  dom.diag.innerHTML = "";
  const r1 = el("div", "h3v28-kv");
  r1.append(el("span", "h3v28-lab", "导演模型"),
            el("b", "", (card.runtime?.running ? "在线（未释放）" : "已停止")));
  dom.diag.append(r1);
  const r2 = el("div", "h3v28-kv");
  r2.append(el("span", "h3v28-lab", "上次释放结论"),
            el("b", "", rel.verdict ? `${rel.verdict}${rel.detail ? " · " + rel.detail : ""}` : "—"));
  dom.diag.append(r2);
  const r3 = el("div", "h3v28-kv");
  r3.append(el("span", "h3v28-lab", "H3 是否可生成"),
            el("b", "", (view?.gate?.generation_allowed === false) ? "否：见上方红条" : "是"));
  dom.diag.append(r3);
  const r4 = el("div", "h3v28-kv");
  r4.append(el("span", "h3v28-lab", "提供方"),
            el("b", "", (card.providers || []).join(" / ") || "—"));
  dom.diag.append(r4);
  dom.logs.textContent = (card.logs || []).join("\n");
  // 素材行只报画布上看到什么；后端核实发生在按【分析参考图】/【生成剧情计划】那一刻。
  renderRefs(null, null);
}

async function resetTo(segmentId) {
  try {
    const out = await call("/reset", { method: "POST",
      body: { project_id: state.projectId, segment_id: segmentId } });
    flash(`游标回到第 ${out.current_segment} 段。之前的成果都还在磁盘上，没有被删除。`);
  } catch (err) {
    banner(`回到该段失败：${err.message}`, "bad");
  }
  await refresh();
}

// ---------------------------------------------------------------------------
// 挂载
// ---------------------------------------------------------------------------
let poller = null;
function startPoller() {
  if (poller) return;
  poller = setInterval(() => {
    if (!panel?.classList.contains("open")) return;
    if (state.busy || state.editing || state.flight) return;   // 别打断输入/生成
    refresh().catch(() => {});
  }, 4000);
}

app.registerExtension({
  name: "H3.V28DirectorPanel",
  // UI_REFACTOR_01：导演台挂进 H3V28DirectorConsole 节点（官方 DOM Widget 机制）。
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (String(nodeData?.name) !== "H3V28DirectorConsole") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      try {
        // 默认尺寸（P6：宽 ~500 / 高 ~840）；工作流里保存过的尺寸会在
        // onConfigure 时覆盖它，不会丢用户拖出来的位置/大小。
        if (!this.size || Number(this.size[0]) < 400) this.size = [500, 840];
        mountIntoNode(this);
      } catch (error) {
        console.error("[H3 V28] Director 节点挂载失败", error);
      }
      return result;
    };
    const onRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      if (hostNode === this) hostNode = null;   // 面板回到游离态，等下一个宿主
      return onRemoved?.apply(this, arguments);
    };
  },
  async setup() {
    buildPanel();
    bindExecutionEvents();
    startPoller();
    setCont("same_shot");
    renderRefs(null, null);
    const saved = localStorage.getItem(STORE_PROJECT);
    if (saved && !state.projectId) state.projectId = saved;
    BASE = await probeBase();
    if (!BASE) {
      if (launcher) launcher.textContent = "导演节点（接口未挂载）";
      dom.diag.textContent = "没找到 /h3_director/ping。H3_V28_Director 未加载或路由未挂载，"
        + "请重启 8197 的 ComfyUI；V27 本身不受影响。";
      return;
    }
    await refresh();
  },
  async afterConfigureGraph() {
    // 换工作流 / 重新加载画布之后，素材行和当前段都要按新图重算
    renderRefs(null, null);
    if (BASE) refresh().catch(() => {});
  },
});
