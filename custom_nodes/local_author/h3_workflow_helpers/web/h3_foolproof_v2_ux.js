import { app } from "../../../scripts/app.js";

/**
 * H3 傻瓜控制台 v2 补充 UX（隔离门：图内存在 properties.h3_foolproof_v2 === true 才生效）。
 *
 * 与 h3_workflow_registry_v1.js / h3_timeline_ux.js 同一隔离惯例：
 *   无 h3_foolproof_v2 标记 → 本文件 no-op，不接管任何 UI / mode / Queue。
 *
 * 本轮功能：
 *   1. 素材「清除」按钮（R11 / AC-11）：LoadImageCrop / VHS_LoadVideo / LoadAudioUI
 *      素材节点上各加一个「清除素材」按钮：置空文件 + 重置 crop + 关闭对应槽位/总控开关
 *      + 触发同步（对应链熄灭）+ 中文提示（文件仍在 input 目录，未删除）。
 *   2. 英文枚举 combo 的显示层中文映射（R19，P2 最小集）：不改 widget 值 / 不改 options，
 *      仅把当前选中值的 widget.label 显示为中文语义（底层序列化值保留英文）。
 *   3. N159 / N150 面板状态行：「参考图自动重排：开」（H3_PICTURE_AUTO_REINDEX 默认 true）。
 *   4. 只读锁定兜底（AC-04）：对【暂未开放】【内部】等显式节点集合隐藏可编辑 widget。
 */

const GATE_FLAG = "h3_foolproof_v2";
const H3_PICTURE_AUTO_REINDEX = true; // §7.1：默认开启；前端 settings 关闭留作后续

function graphNodeList(node) {
  return node?.graph?._nodes || app.graph?._nodes || [];
}

function foolproofActive(node) {
  if (node && node.properties?.[GATE_FLAG] === true) return true;
  return (app.graph?._nodes || []).some((n) => n.properties?.[GATE_FLAG] === true);
}

function widgetOf(n, name) {
  return n?.widgets?.find((w) => w.name === name);
}

function hideWidgetReadonly(w) {
  if (!w || w.type === "hidden") return;
  w.type = "hidden";
  if (w.options && typeof w.options === "object") w.options.serialize = true;
}

// =====================================================================
// 1. 素材「清除」按钮（R11 / AC-11）
// =====================================================================
const IMAGE_SLOT_IDS = [687, 688, 689, 690];   // 参考图 1-4（每槽独立关闭）
const FIRST_LAST_IDS = [874, 875];             // FL2V 首/尾帧（可选，R05）
const VIDEO_IDS = [638];                       // VHS_LoadVideo
const AUDIO_IDS = [143, 685];                  // LoadAudioUI

function toast(message) {
  const host = document.body;
  if (!host) return;
  const el = document.createElement("div");
  el.textContent = message;
  el.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:99999;background:#123b2a;border:1px solid #52d692;color:#eafff3;padding:10px 14px;border-radius:8px;font:600 13px sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.4)";
  host.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

function setToggleAndSync(toggleWidget, value) {
  if (!toggleWidget) return;
  toggleWidget.value = value;
  const cb = toggleWidget.callback;
  if (typeof cb === "function") {
    try { cb(value); } catch (error) { console.warn("[H3] 清除同步回调失败", error); }
  }
}

function turnOffN150Switch(n150, switchName) {
  const w = widgetOf(n150, switchName);
  if (w && (w.value === true || w.value === 1)) {
    setToggleAndSync(w, false);
    return true;
  }
  return false;
}

function findRefsNode(node) {
  return graphNodeList(node).find((n) => n.type === "H3ReferenceSourceSelector");
}

function findImageModeNode(node) {
  return graphNodeList(node).find((n) => n.type === "H3ImageModeSelector");
}

function resetCropWidget(cropWidget) {
  if (!cropWidget) return;
  if (cropWidget.value && typeof cropWidget.value === "object") {
    cropWidget.value = {};
  } else {
    cropWidget.value = "";
  }
}

function hideVideoPreview(node) {
  const preview = widgetOf(node, "videopreview");
  if (preview?.value && typeof preview.value === "object") {
    preview.value.hidden = true;
  }
  if (preview?.parentEl) preview.parentEl.hidden = true;
}

function clearMaterialNode(node, triggerNode) {
  const nid = node.id;
  const type = node.type;
  if (type === "LoadImageCrop") {
    const imageW = widgetOf(node, "image") || node.widgets?.[0];
    const cropW = widgetOf(node, "crop") || node.widgets?.[1];
    if (imageW) imageW.value = "";
    resetCropWidget(cropW);
    if (IMAGE_SLOT_IDS.includes(nid)) {
      // 参考图：关闭该槽位的「参与图片参考」（事实源 h3_reference_slot_enabled=false）
      node.properties.h3_reference_slot_enabled = false;
      const toggle = (node.widgets || []).find((w) => w.type === "toggle" || String(w.name || "").includes("参与图片参考"));
      if (toggle) setToggleAndSync(toggle, false);
    } else if (FIRST_LAST_IDS.includes(nid)) {
      // 首/尾帧：若正在被 FL2V 图片模式点亮，把图片模式切回文生视频，避免空素材激活
      const imageModeNode = findImageModeNode(triggerNode || node);
      const w = imageModeNode ? (widgetOf(imageModeNode, "图片模式") || imageModeNode.widgets?.[0]) : null;
      if (w && node.mode === 0 && String(w.value || "").startsWith("首")) {
        setToggleAndSync(w, "文生视频（不用图）");
      } else if (w && node.mode === 0 && String(w.value || "").startsWith("单")) {
        setToggleAndSync(w, "文生视频（不用图）");
      }
    }
    return true;
  }
  if (type === "LoadVideo") {
    const videoW = widgetOf(node, "video") || node.widgets?.[0];
    if (videoW) videoW.value = "";
    hideVideoPreview(node);
    const n150 = findRefsNode(triggerNode || node);
    if (n150) {
      turnOffN150Switch(n150, "启用参考视频");
      turnOffN150Switch(n150, "后处理使用上传视频");
    }
    return true;
  }
  if (type === "LoadAudio") {
    const audioW = widgetOf(node, "audio") || node.widgets?.[0];
    if (audioW) audioW.value = "";
    const n150 = findRefsNode(triggerNode || node);
    if (n150) {
      if (nid === 143) turnOffN150Switch(n150, "启用参考音频1");
      if (nid === 685) turnOffN150Switch(n150, "启用参考音频2");
    }
    return true;
  }
  return false;
}

function isClearableMaterialNode(node) {
  if (!foolproofActive(node)) return false;
  if (node.type === "LoadImageCrop") {
    return IMAGE_SLOT_IDS.includes(node.id) || FIRST_LAST_IDS.includes(node.id);
  }
  if (node.type === "LoadVideo" && VIDEO_IDS.includes(node.id)) return true;
  if (node.type === "LoadAudio" && AUDIO_IDS.includes(node.id)) return true;
  return false;
}

function installClearButton(node) {
  if (!isClearableMaterialNode(node) || node.__h3ClearInstalled) return;
  node.__h3ClearInstalled = true;
  node.addWidget("button", "清除素材", null, () => {
    const ok = clearMaterialNode(node, node);
    if (ok) {
      toast("已清除「" + (node.title || node.type) + "」；文件仍在 input 目录，未删除。");
      node.graph?.setDirtyCanvas?.(true, true);
      app.graph?.change?.();
    } else {
      toast("该节点暂不支持一键清除，请在控件内手动清空。");
    }
  }, { serialize: false });
}

// =====================================================================
// 2. 英文枚举显示层中文映射（R19，P2 最小集；不改值 / 不改 options）
// =====================================================================
const ENUM_NODE_IDS = new Set([115, 725, 769, 728, 765, 781, 655, 636]);

const ENUM_ZH = {
  "9:16 (Portrait Widescreen)": "竖屏 9:16",
  "economy (tight spans)": "经济档（紧跨度）",
  "value |d3| (default)": "数值 |d3|（默认）",
  "trim tail (default)": "默认（裁剪尾部）",
  "custom (use audio_strength)": "自定义（用音频强度）",
  "raise (stock behaviour)": "抬升（默认行为）",
  "system_ram": "系统内存",
  "hard_clip": "硬裁剪",
  "no_attenuation": "不衰减",
  "coordinate_rls": "坐标 RL 修正",
  "exact_kv": "精确 KV",
  "2d_frame": "二维画面",
  "minimax-h3": "MiniMax-H3 模型",
};

function enumChineseForValue(value) {
  if (value == null) return "";
  return ENUM_ZH[String(value)] || "";
}

function applyEnumDisplay(node) {
  if (!ENUM_NODE_IDS.has(node.id) || !foolproofActive(node)) return;
  for (const w of node.widgets || []) {
    const zh = enumChineseForValue(w.value);
    if (zh && w.label !== zh) w.label = zh;
  }
  if (node.__h3EnumBound) return;
  node.__h3EnumBound = true;
  for (const w of node.widgets || []) {
    const originalCallback = w.callback;
    if (typeof originalCallback !== "function") continue;
    w.callback = function (value, ...rest) {
      const result = originalCallback.apply(this, [value, ...rest]);
      const zh = enumChineseForValue(value);
      if (zh && this.label !== zh) this.label = zh;
      return result;
    };
  }
}

// =====================================================================
// 3. 参考图自动重排提示行（H3_PICTURE_AUTO_REINDEX = 开）
// =====================================================================
function installAutoReindexStatus(node) {
  if (!foolproofActive(node)) return;
  const selector = (graphNodeList(node).find((n) => n.properties?.[GATE_FLAG] === true)) || node;
  const tryAppend = () => {
    const controls = selector.__h3OperationControls;
    if (!controls?.panel) return false;
    if (controls.panel.querySelector(".h3AutoReindexLine")) return true;
    const line = document.createElement("div");
    line.className = "h3AutoReindexLine";
    line.textContent = H3_PICTURE_AUTO_REINDEX
      ? "参考图自动重排：开（删除中间参考图后，提交时自动压缩并同步改写提示词编号）"
      : "参考图自动重排：关";
    line.style.cssText = "margin-top:6px;padding:6px 8px;border-radius:6px;background:#172233;color:#bcd8ff;font-size:12px;line-height:1.4";
    controls.panel.appendChild(line);
    return true;
  };
  if (tryAppend()) return;
  let tries = 0;
  const timer = setInterval(() => {
    tries += 1;
    if (tryAppend() || tries > 30) clearInterval(timer);
  }, 60);
}

// =====================================================================
// 4. 只读锁定兜底（AC-04，显式节点集合，避免 title 启发式误伤 Note/输出件）
// =====================================================================
const LOCKED_NODE_IDS = new Set([
  766,           // 【内部】后处理视频源选择（只随总控）
  900, 901, 902, 903, // AddGuide 实验链（暂未开放；901/902/903 另有属性锁，双保险）
  146, 746, 676, 692, 765, // 插帧链 + 孤儿/备用（暂未开放）
  800, 801, 803, 804, 805, 808, 809, 810, 811, 813, // 废版保留
]);

function lockUnavailableWidgets(node) {
  if (!foolproofActive(node)) return;
  if (!LOCKED_NODE_IDS.has(node.id)) return;
  for (const w of node.widgets || []) hideWidgetReadonly(w);
}

// =====================================================================
// 统一 apply（在 onCreated / onConfigure 后补挂）
// =====================================================================
function applyFoolproofV2(node) {
  if (!foolproofActive(node)) return;
  installClearButton(node);
  applyEnumDisplay(node);
  lockUnavailableWidgets(node);
  if (node.properties?.[GATE_FLAG] === true) {
    installAutoReindexStatus(node);
  }
}

app.registerExtension({
  name: "H3.Workflow.FoolproofV2Ux",
  beforeRegisterNodeDef(nodeType, nodeData) {
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onCreated?.apply(this, arguments);
      setTimeout(() => applyFoolproofV2(this), 0);
      setTimeout(() => applyFoolproofV2(this), 120);
      return result;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => applyFoolproofV2(this), 0);
      setTimeout(() => applyFoolproofV2(this), 120);
      return result;
    };
  },
  afterConfigureGraph() {
    // 图加载完成后兜底补挂（素材节点可能晚于 selector 出现）
    const nodes = app.graph?._nodes || [];
    if (!nodes.some((n) => n.properties?.[GATE_FLAG] === true)) return;
    for (const n of nodes) applyFoolproofV2(n);
  },
});
