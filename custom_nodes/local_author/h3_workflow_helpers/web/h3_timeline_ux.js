import { app } from "../../../scripts/app.js";
import {
  TLD_ROUTE_REGISTRY,
  TLD_TIMELINE_FIXTURE,
  TLD_ROUTE_REGISTRY_SHA,
  H3_ROUTE_STATUS_ZH,
} from "./h3_timeline_registry_data.js";

/**
 * TLD Timeline Director Phase-1（只读化收口 · Q5）。
 *
 * 隔离门（与 h3_workflow_registry_v1.js 同一惯例）：
 *   仅当图中存在 properties.h3_timeline_v1 === true 的 H3OperationSelector 时启动；
 *   无标记 → 本文件完全 no-op，不接管任何 UI / mode / Queue。
 *
 * Q5 只读化（2026-09-06 作者裁决）：
 *   - 删除全部素材填写框与素材开关（textInput / checkbox / usage 下拉 全部移除）。
 *   - 素材状态改为只读行：读画布 N150(H3ReferenceSourceSelector) 实际开关 + 各素材节点
 *     当前文件，显示「已启用… / 未启用…」，绝不写回画布。
 *   - 段落字段全中文：段落编号（审计键）/ 段落名称 / 开始（结束）（秒）/ 段落启用开关 /
 *     段落提示词（只读）/ 关键帧锚点（本路线支持）/ 关键帧位置（帧号≥0）/ 重拍目标段落。
 *   - 路线生命周期状态英文枚举（status）保留为后端白名单，显示层用 H3_ROUTE_STATUS_ZH 映射：
 *     RESERVED_NOT_PHASE1→暂未开放，PHASE1_ACTIVE_*→实验可用。
 *   - 编译预览按钮保留（仅预览，不写画布、不产生素材 runtime_writes、不 queuePrompt）。
 *   - DOM widget 内部名 H3_TIMELINE_V1 属白名单保留。
 */

const TLD_UI_STATE = {
  zones: [],
  currentZoneIndex: 0,
  retakeTarget: "",
  expanded: true,
};

// 只读面板与傻瓜控制台共存时的确定性尺寸（R-2）：
// 宽 880 / 高 1360，足以容纳 foolproof(≈500) + timeline(≈720) 两 DOM 面板。
const READONLY_PANEL_HEIGHT = 720;
const COEXIST_WIDTH = 880;
const COEXIST_HEIGHT = 1360;

function registryRoutes() {
  return TLD_ROUTE_REGISTRY.routes;
}

function routeByZoneMode(mode) {
  const key = TLD_ROUTE_REGISTRY.zone_mode_to_route[mode];
  return key ? registryRoutes()[key] : null;
}

function deriveLengthFrames(durationSeconds) {
  // N131 唯一公式（禁止第二套帧数算法）
  const base = Math.max(5, Math.round(durationSeconds * 24));
  return base + (((5 - (base % 17)) % 17) + 17) % 17;
}

function zoneDefaults(index) {
  return {
    zone_id: "Z" + String(index).padStart(2, "0"),
    chinese_name: "段落 " + index, // G31：Zone N → 段落 N
    start: 0,
    end: 3,
    route: "REF2VA",
    prompt: "",
    assets: { pic1: "", pic2: "", pic3: "", pic4: "", video: "", audio1: "", audio2: "", first: "", last: "" },
    refImages: false, refVideo: false, refAudio1: false, refAudio2: false, videoUsage: "动作/镜头参考",
    anchor: { enabled: false, frame_idx: 0, image: "" },
    enabled: true,
  };
}

function fromFixture() {
  TLD_UI_STATE.zones = (TLD_TIMELINE_FIXTURE.zones || []).map((z, i) => {
    const ui = zoneDefaults(i + 1);
    ui.zone_id = z.zone_id;
    ui.route = z.mode;
    ui.start = i * (z.duration_seconds || 3);
    ui.end = ui.start + (z.duration_seconds || 3);
    ui.prompt = z.prompt_zone?.text || "";
    ui.enabled = true;
    if (z.mode === "REF2VA") {
      ui.refImages = !!z.binding?.ref_images?.enabled;
      if (ui.refImages) ["pic1", "pic2", "pic3", "pic4"].forEach((k) => { ui.assets[k] = z.binding.ref_images[k] || ""; });
      ui.refVideo = !!z.binding?.ref_video?.enabled;
      if (ui.refVideo) ui.assets.video = z.binding.ref_video.file || "";
      ui.refAudio1 = !!z.binding?.ref_audio1?.enabled;
      if (ui.refAudio1) ui.assets.audio1 = z.binding.ref_audio1.file || "";
      ui.refAudio2 = !!z.binding?.ref_audio2?.enabled;
      if (ui.refAudio2) ui.assets.audio2 = z.binding.ref_audio2.file || "";
      ui.videoUsage = z.video_usage || "动作/镜头参考";
    } else {
      ui.assets.first = z.binding?.fl2v_frames?.first_file || "";
      ui.assets.last = z.binding?.fl2v_frames?.last_file || "";
    }
    ui.anchor.enabled = !!z.anchor?.enabled;
    ui.anchor.frame_idx = z.anchor?.frame_idx ?? 0;
    ui.anchor.image = z.anchor?.image || "";
    return ui;
  });
  TLD_UI_STATE.currentZoneIndex = 0;
  TLD_UI_STATE.retakeTarget = "";
}

/**
 * Queue 前编译预览（只读版）。
 * 时间轴已只读：素材以画布为准，这里只做路线/时长/帧数预览；
 * 不再产生 node_id 687..690/638/143/685/874/875/902 的素材 runtime_writes；
 * 不写入画布、不提交任务。
 */
function compileZonePreview(zone) {
  const errors = [];
  const plan = { zone_id: zone.zone_id, fail_closed: true, fallback_present: false };
  const route = routeByZoneMode(zone.route);
  if (!route) {
    errors.push("未知路线：" + zone.route + "（注册表中无此映射）");
    return { ok: false, errors, plan };
  }
  if (route.phase1_selectable !== true) {
    errors.push("路线 " + route.route_id + " 不可选择（phase1_selectable!==true），Phase-1 编译拒绝（fail-closed）");
    return { ok: false, errors, plan };
  }
  plan.route_id = route.route_id;
  plan.route_chinese_name = route.chinese_name;

  const duration = Number(zone.end) - Number(zone.start);
  if (!(duration > 0)) errors.push("段落时长（结束 - 开始）必须大于 0 秒");
  plan.duration_seconds = duration;
  const length = deriveLengthFrames(duration);
  plan.derived = { length_frames: length, frame_load_cap: "LINKED_N131_DO_NOT_WRITE" };

  if (zone.anchor.enabled) {
    plan.anchor = {
      supported: route.anchor_supported,
      enabled: zone.anchor.enabled,
      frame_idx: zone.anchor.frame_idx,
      image: zone.anchor.image,
    };
  } else {
    plan.anchor = { supported: route.anchor_supported, enabled: false, frame_idx: null, image: "" };
  }
  plan.prompt = {
    target_node: route.prompt_role?.text_node,
    schema: route.prompt_role?.schema,
    effective: zone.prompt,
    note: "段落提示词仅只读展示；素材以画布「素材区」为准",
  };
  plan.output_node = route.output_node;
  plan.note = "只读预览：不写入画布参数、不提交任务；实际生成读取画布节点参数（素材区 + 总控）。";
  return { ok: errors.length === 0, errors, plan };
}

// ---------------- 只读素材状态读取（画布实际为准） ----------------
function graphNodeList(node) {
  return node?.graph?._nodes || app.graph?._nodes || [];
}

function widgetOf(n, name) {
  return n?.widgets?.find((w) => w.name === name);
}

function canvasMaterialState(node) {
  const graph = graphNodeList(node);
  const refs = graph.find((n) => n.type === "H3ReferenceSourceSelector");
  const getBool = (n, name) => n && widgetOf(n, name)?.value === true;
  const getFile = (id, wname) => {
    const n = graph.find((m) => m.id === id);
    const w = widgetOf(n, wname);
    if (!n || !w) return "";
    const v = w.value;
    if (v && typeof v === "object") return JSON.stringify(v);
    return String(v ?? "");
  };
  const enabledSlots = [];
  for (const id of [687, 688, 689, 690]) {
    if (getFile(id, "image")) enabledSlots.push(id - 686);
  }
  return {
    imagesSwitch: refs ? getBool(refs, "启用四张参考图") : null,
    enabledSlots,
    firstFile: getFile(874, "image"),
    lastFile: getFile(875, "image"),
    videoSwitch: refs ? getBool(refs, "启用参考视频") : null,
    videoFile: getFile(638, "video"),
    uploadSwitch: refs ? getBool(refs, "后处理使用上传视频") : null,
    audio1Switch: refs ? getBool(refs, "启用参考音频1") : null,
    audio1File: getFile(143, "audio"),
    audio2Switch: refs ? getBool(refs, "启用参考音频2") : null,
    audio2File: getFile(685, "audio"),
  };
}

function renderMaterialStateRow(node, editor, field) {
  const state = canvasMaterialState(node);
  const none = state.imagesSwitch === null ? "（画布未检测到总控 N150）" : "";
  const imageText = state.imagesSwitch
    ? "已启用四张参考图（实际已上传：" + (state.enabledSlots.length ? state.enabledSlots.map((i) => "图" + i).join("、") : "无") + "）"
    : "未启用参考图";
  field("画布素材状态", textSpan(imageText + (none || "")));
  field("参考视频", textSpan(
    state.videoSwitch === true
      ? "已启用" + (state.videoFile ? "（文件：" + state.videoFile + "）" : "（尚未上传文件）")
      : "未启用"
  ));
  field("后处理使用上传视频", textSpan(state.uploadSwitch === true ? "已启用（后处理链读取上传视频）" : "未启用"));
  field("参考音频 1/2", textSpan(
    (state.audio1Switch === true ? "音频1 已启用" + (state.audio1File ? "" : "（未上传）") : "音频1 未启用") +
    "｜" +
    (state.audio2Switch === true ? "音频2 已启用" + (state.audio2File ? "" : "（未上传）") : "音频2 未启用")
  ));
  field("首帧/尾帧图片", textSpan(
    (state.firstFile ? "首帧：" + state.firstFile : "首帧：未上传") +
    "｜" +
    (state.lastFile ? "尾帧：" + state.lastFile : "尾帧：未上传")
  ));
}

function statusChinese(route) {
  if (!route) return "";
  const zh = H3_ROUTE_STATUS_ZH[route.status];
  return zh ? zh : String(route.status ?? "");
}

// ---------------- 只读 UI ----------------
function textSpan(text) {
  const el = document.createElement("span");
  el.textContent = text || "—";
  el.style.cssText = "flex:1;box-sizing:border-box;padding:4px 8px;border-radius:4px;border:1px solid #2a2440;background:#0d0a14;color:#e6d8ff;font-size:12px;word-break:break-all";
  return el;
}

function refreshPanel(node, controls) {
  const list = controls.zoneList;
  list.textContent = "";
  TLD_UI_STATE.zones.forEach((zone, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = zone.chinese_name + (zone.enabled ? "" : "（停用）");
    btn.style.cssText = "padding:6px 10px;border-radius:6px;border:1px solid #76549a;background:" +
      (i === TLD_UI_STATE.currentZoneIndex ? "#123b2a" : "#241833") + ";color:#fff;cursor:pointer";
    btn.addEventListener("click", () => { TLD_UI_STATE.currentZoneIndex = i; refreshPanel(node, controls); });
    list.appendChild(btn);
  });

  const zone = TLD_UI_STATE.zones[TLD_UI_STATE.currentZoneIndex];
  const editor = controls.editor;
  editor.textContent = "";
  if (!zone) return;
  const route = routeByZoneMode(zone.route);

  const field = (labelText, valueEl) => {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;align-items:center;margin:4px 0";
    const label = document.createElement("label");
    label.textContent = labelText;
    label.style.cssText = "min-width:150px;color:#d4c8e4;font-size:12px";
    row.append(label, valueEl);
    editor.appendChild(row);
    return row;
  };

  field("段落编号（审计键）", textSpan(zone.zone_id));
  field("段落名称", textSpan(zone.chinese_name));
  field("生产路线", textSpan(route
    ? route.chinese_name + "（" + statusChinese(route) + "）"
    : String(zone.route)));
  field("开始（秒）", textSpan(String(zone.start)));
  field("结束（秒）", textSpan(String(zone.end)));
  field("段落启用开关", textSpan(zone.enabled ? "启用" : "停用"));

  const promptArea = document.createElement("textarea");
  promptArea.value = zone.prompt || "";
  promptArea.rows = 5;
  promptArea.readOnly = true;
  promptArea.style.cssText = "flex:1;box-sizing:border-box;padding:6px 8px;border-radius:5px;border:1px solid #2a2440;background:#0d0a14;color:#e6d8ff;font-size:12px;font-family:monospace;resize:vertical";
  field("段落提示词（只读）", promptArea);

  if (route?.anchor_supported) {
    field("关键帧锚点（本路线支持）", textSpan(zone.anchor.enabled ? "已启用" : "未启用"));
    if (zone.anchor.enabled) {
      field("关键帧位置（帧号≥0）", textSpan(String(zone.anchor.frame_idx)));
      field("关键帧锚点图片", textSpan(zone.anchor.image || "（未设置）"));
    }
  } else {
    field("关键帧锚点（本路线支持）", textSpan("不支持（本路线 anchor_supported=false）"));
  }

  field("重拍目标段落", textSpan(
    TLD_UI_STATE.retakeTarget
      ? "下一次执行只针对 " + TLD_UI_STATE.retakeTarget
      : "（无：按段落顺序执行全部启用段落）"
  ));

  // 画布素材真实状态（只读）——时间轴不再提供任何素材入口（AC-03/AC-09）
  renderMaterialStateRow(node, editor, field);

  const hint = document.createElement("div");
  hint.textContent = "素材请在画布「01｜素材区」上传；本面板为只读展示，不写画布、不提交任务。";
  hint.style.cssText = "color:#8f80a8;font-size:11px;margin-top:6px";
  editor.appendChild(hint);

  const btnRow = document.createElement("div");
  btnRow.style.cssText = "display:flex;gap:8px;margin-top:8px";
  const compileBtn = document.createElement("button");
  compileBtn.type = "button";
  compileBtn.textContent = "查看此段只读预览（不应用到生成）";
  compileBtn.style.cssText = "flex:1;height:34px;border:0;border-radius:6px;background:#593d78;color:#fff;font:700 13px sans-serif;cursor:pointer";
  compileBtn.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const result = compileZonePreview(zone);
    const out = controls.planOut;
    if (!result.ok) {
      out.textContent = "只读预览 STOP（fail-closed，不做任何自动修正）：\n- " + result.errors.join("\n- ");
      out.style.color = "#ff9c9c";
    } else {
      out.textContent = "只读预览有效；实际生成读取画布节点参数（素材区 + 总控）。\n" +
        JSON.stringify(result.plan, null, 2);
      out.style.color = "#aaf1ca";
    }
  });
  btnRow.appendChild(compileBtn);
  editor.appendChild(btnRow);
}

function setNodeSizeMin(node, w, h) {
  const cw = node.size?.[0] || 0;
  const ch = node.size?.[1] || 0;
  node.setSize([Math.max(cw, w), Math.max(ch, h)]);
}

function installTimelinePanel(node) {
  const panel = document.createElement("div");
  panel.style.cssText = "box-sizing:border-box;width:100%;padding:12px;background:#100d18;border:1px solid #76549a;border-radius:9px;color:#fff;font:600 14px sans-serif;overflow-y:auto";

  const heading = document.createElement("div");
  heading.textContent = "【时间轴预览（只读）】";
  heading.style.cssText = "font-size:18px;color:#e6d8ff;margin-bottom:4px";
  const hint = document.createElement("div");
  hint.textContent = "时间轴已只读化：素材一律在画布「01｜素材区」上传，本面板仅展示段落状态，不写入画布参数、不随工作流保存、不提交任务。";
  hint.style.cssText = "font-size:12px;font-weight:500;color:#c7b4df;margin-bottom:10px;line-height:1.45";

  const zoneList = document.createElement("div");
  zoneList.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px";
  const editor = document.createElement("div");
  editor.style.cssText = "border:1px solid #76549a;border-radius:8px;padding:10px;background:#171223";
  const planOut = document.createElement("pre");
  planOut.style.cssText = "margin-top:10px;padding:9px 10px;border-radius:6px;background:#0c0a12;border:1px solid #333;color:#aaf1ca;font-size:11px;line-height:1.45;white-space:pre-wrap;max-height:220px;overflow:auto";

  panel.append(heading, hint, zoneList, editor, planOut);
  for (const eventName of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "wheel", "keydown"]) {
    panel.addEventListener(eventName, (event) => event.stopPropagation());
  }

  const controls = { panel, zoneList, editor, planOut };
  node.__h3TimelineControls = controls;
  const domWidget = node.addDOMWidget("h3_timeline_v1", "H3_TIMELINE_V1", panel, {
    serialize: false, // UI 元数据不序列化进 workflow（序列化分层）
    hideOnZoom: false,
    getHeight: () => READONLY_PANEL_HEIGHT,
  });
  domWidget.computeSize = (width) => [width, READONLY_PANEL_HEIGHT];
  // R-2：与傻瓜控制台共存时采用确定性宽高（不互踩 setSize，只扩大不缩小）
  if (node.properties?.h3_foolproof_v2 === true) {
    setNodeSizeMin(node, COEXIST_WIDTH, COEXIST_HEIGHT);
  } else {
    node.setSize([860, 800]);
  }
  fromFixture();
  refreshPanel(node, controls);
}

function installTimeline(node) {
  if (node?.type !== "H3OperationSelector" || node.__h3TimelineReady) return;
  if (node.properties?.h3_timeline_v1 !== true) return; // 隔离门：无标记 no-op
  node.__h3TimelineReady = true;
  installTimelinePanel(node);
}

app.registerExtension({
  name: "H3.Workflow.TimelinePhase1",
  beforeRegisterNodeDef(nodeType, nodeData) {
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onCreated?.apply(this, arguments);
      setTimeout(() => installTimeline(this), 0);
      return result;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => installTimeline(this), 0);
      return result;
    };
  },
});
