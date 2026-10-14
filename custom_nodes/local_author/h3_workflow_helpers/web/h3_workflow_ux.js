import { app } from "../../../scripts/app.js";
// v014：由主 UX 显式导入 Dashboard，避免仅靠 /extensions 枚举或旧缓存时
// 出现“旧六卡已关闭但新面板未注册”的空壳状态。ESM 会自动去重重复导入。
import { applyDashboard } from "./h3_foolproof_v3_dashboard.js";
import {
  applyFunction,
  currentFunctionId,
  repairPrimaryOutput,
  validatePrimaryOutput,
  compactRefImageSlots,
} from "./h3_workflow_registry_core.js";

const ZH = {
  images: "图像帧",
  image: "图像",
  audio: "音频",
  audio_latent: "音频潜空间",
  av_latent: "音视频潜空间",
  samples: "视频潜空间",
  latent_image: "潜空间图像",
  model: "模型",
  clip: "文本编码器",
  conditioning: "生成条件",
  positive: "正向条件",
  negative: "负向条件",
  vae: "视频 VAE",
  audio_vae: "音频 VAE",
  sampler: "采样器",
  sigmas: "采样步进",
  noise: "随机噪声",
  noise_seed: "随机种子",
  guider: "引导器",
  hold_map: "扩时映射",
  oracle_hold_map: "检测器扩时映射",
  baseline_audio: "原始音频",
  length: "总帧数",
  fps: "帧率",
  frame_rate: "输出帧率",
  ranges: "坏段范围",
  hold: "放大倍数",
  ramp: "平滑过渡",
  bridge: "相邻坏段合并帧数",
  budget_dilated: "单窗口最大扩时帧数",
  handle_frames: "窗口上下文帧数",
  pin_frames: "窗口固定帧数",
  feather_frames: "窗口渐变帧数",
  seed_stride: "窗口种子偏移",
  draft_width: "二采草稿宽度",
  draft_height: "二采草稿高度",
  upscale_method: "缩放方法",
  on_interrupt: "中断处理",
  plan_only: "仅计算方案",
  audio_rms_search_ms: "音频切点搜索毫秒",
  s_per_step: "每步耗时（秒）",
  est_steps: "预计采样步数",
  overhead_s: "固定额外耗时（秒）",
  q: "检测灵敏分位数",
  d_max: "最大动作扩时倍数",
  preset: "检测预设",
  profile_mode: "动作分析方式",
  abstain_below: "无异常阈值",
  model_profile: "模型配置",
  mode: "处理方式",
  max_frames: "最大帧数",
  video: "上传视频",
  force_rate: "读取帧率",
  custom_width: "目标宽度",
  custom_height: "目标高度",
  frame_load_cap: "最多读取帧数",
  skip_first_frames: "跳过开头帧数",
  select_every_nth: "每隔几帧读取",
  meta_batch: "批处理信息",
  duration: "视频时长（秒）",
  width: "宽度",
  height: "高度",
  largest_size: "最大边尺寸",
  frame_count: "帧数",
  frames: "视频帧",
  first_frame: "首帧",
  last_frame: "尾帧",
  preview_frames: "预览帧",
  pixels: "像素图像",
  mask: "遮罩",
  prompt: "提示词",
  "启用四张参考图": "启用图片参考（各图可单独关闭）",
  text: "文本",
  seed: "随机种子",
  steps: "采样步数",
  total_steps: "总采样步数",
  source: "来源",
  output: "输出",
  filename: "文件名",
  Filenames: "文件名列表",
  video_info: "视频信息",
  video_latent: "视频潜空间",
  denoised_output: "去噪结果",
  plan: "修复方案",
  hold_map_used: "实际扩时映射",
  oracle_samples: "检测用潜空间",
  optional_interpolation_states: "可选插帧状态",
  tau_profile: "时间曲线",
  filename_prefix: "文件名前缀",
  format: "视频格式",
  pix_fmt: "像素格式",
  crf: "画质值（越低越清晰）",
  save_metadata: "保存工作流信息",
  trim_to_audio: "按音频长度裁切",
  pingpong: "正放后倒放",
  save_output: "保存到输出目录",
  loop_count: "循环次数",
  boolean: "选择开关",
  on_false: "关闭时使用",
  on_true: "开启时使用",
  on_false_value_1: "关闭时画面",
  on_false_value_2: "关闭时音频/潜空间",
  on_false_value_3: "关闭时帧数",
  on_true_value_1: "开启时画面",
  on_true_value_2: "开启时音频/潜空间",
  on_true_value_3: "开启时帧数",
  value: "选定结果",
  value_1: "选定画面",
  value_2: "选定音频/潜空间",
  value_3: "选定帧数",
  segments: "坏段时间与帧区间",
  profile: "动作强度曲线",
  report: "检测/修复报告",
  window_start: "窗口起始帧",
  window_len: "窗口帧数",
  string_a: "检测结果",
  string_b: "空结果基准",
  case_sensitive: "区分大小写",
  anything: "任意数据",
  OPT_CONNECTION: "可选连接",
  BOOL: "开关",
  BOOLEAN: "开关",
  FLOAT: "小数",
  int: "整数",
  STRING: "文本",
  LATENT: "潜空间",
  GUIDER: "引导器",
  // ---- V26 STEP 8：补全 8196 实测中仍显示英文的参数名（仅 label 显示） ----
  upload: "上传文件",
  file: "文件",
  sampler_name: "采样器名称",
  scheduler: "调度器",
  denoise: "去噪强度",
  crop: "裁剪模式",
  crop_position: "裁剪位置",
  crop_editor: "裁剪编辑面板",
  max_megapixels: "最大百万像素",
  megapixels: "百万像素",
  aspect_ratio: "画面比例",
  multiple: "对齐倍数",
  preview: "预览",
  codec: "编码器",
  bit_depth: "位深",
  color_space: "色彩空间",
  vae_name: "VAE 文件名",
  unet_name: "主模型文件名",
  clip_name: "文本编码器文件名",
  image_name: "关键帧图片",
  lora_name: "LoRA 文件名",
  strength_model: "LoRA 强度",
  weight_dtype: "权重精度",
  device: "运行设备",
  type: "模型类型",
  expression: "计算公式",
  keep_proportion: "保持比例",
  pad_color: "填充颜色",
  divisible_by: "整除对齐",
  max_resolution: "最大分辨率",
  jpeg_quality: "JPEG 质量",
  suppress_default_preview: "屏蔽默认预览",
  preview_fps: "预览帧率",
  preview_text: "预览文字",
  preview_mode: "预览模式",
  tiny_vae: "轻量 VAE",
  shift_video: "视频时间步偏移",
  shift_audio: "音频时间步偏移",
  ref_image_size: "参考图尺寸",
  audioUI: "音频控件",
  audio_mode: "音频模式",
  audio_strength: "音频强度",
  video_usage: "视频用途",
  picture_refs_enabled: "启用参考图",
  video_refs_enabled: "启用参考视频",
  audio1_enabled: "启用参考音频1",
  audio2_enabled: "启用参考音频2",
  gate_file: "门控权重文件",
  sparsity: "稀疏度",
  attention: "注意力方案",
  keep_percent: "保留比例",
  frame_idx: "关键帧序号",
  selection: "方案选择",
  start_percent: "起始比例",
  end_percent: "结束比例",
  dense_blocks: "稠密块数",
  min_tokens: "最小词元数",
  extra_tokens: "额外词元数",
  sink_conditioning: "锚定条件",
  verbose: "详细日志",
  dilation: "膨胀帧数",
  expand_to_end: "扩展到片尾",
  freeze_threshold: "冻结阈值",
  freeze_grow: "冻结扩展帧数",
  mask_feather: "遮罩羽化",
  invert_mask: "反相遮罩",
  time_varying: "随时间变化",
  inject: "注入计划",
  base_prompt: "基础提示词",
  latent: "潜空间数据",
  INT: "整数",
  VIDEO: "视频数据",
  MODEL: "模型数据",
  AUDIO: "音频数据",
  CONDITIONING: "生成条件数据",
  SAMPLER: "采样器对象",
  VAE: "VAE 对象",
  SIGMAS: "采样步进数据",
  h3_dashboard_v3: "控制台面板",
};

const PLAYER_TITLES = ["【模式 1 输出】", "【模式 3 输出】", "【模式 4 输出】"];
const OPERATION_KEYS = {
  "只跑一采": "pass1",
  "检测坏段": "detect",
  "放大/扩时": "expand",
  "执行二采": "resample",
  "自动检测+扩时+二采（实验）": "auto",
  "无任何选项状态": "none",
};

const OPERATION_CARDS = [
  {
    value: "只跑一采",
    key: "pass1",
    number: "1",
    title: "一采生成",
    description: "生成主视频并保存；检测、放大、二采和自动修复全部紫色旁路。",
    action: "执行一采生成",
  },
  {
    value: "检测坏段",
    key: "detect",
    number: "2",
    title: "只检测坏段",
    description: "只输出检测区间、曲线和结论，不放大、不二采。",
    action: "执行坏段检测",
  },
  {
    value: "放大/扩时",
    key: "expand",
    number: "3",
    title: "只放大扩时",
    description: "生成扩时预览和方案报告，到此停止，绝不启动二采。",
    action: "执行放大扩时",
  },
  {
    value: "执行二采",
    key: "resample",
    number: "4",
    title: "只执行二采",
    description: "读取放大扩时链并执行二采修复；与功能 3 独立。",
    action: "执行二采修复",
  },
  {
    value: "自动检测+扩时+二采（实验）",
    key: "auto",
    number: "5",
    title: "自动检测修复",
    description: "自动检测；无坏段直接输出，有坏段才点亮窗口二采。",
    action: "执行自动修复",
  },
  {
    value: "无任何选项状态",
    key: "none",
    number: "6",
    title: "全部旁路",
    description: "所有功能区变紫，仅查看参数，不提交任何任务。",
    action: "切换为全部旁路",
    queue: false,
  },
];

const ACTIVE_NODE_COLOR = "#277a52";
const ACTIVE_NODE_BACKGROUND = "#123b2a";
const BYPASSED_NODE_COLOR = "#62408a";
const BYPASSED_NODE_BACKGROUND = "#281a38";
const ACTIVE_GROUP_COLOR = "#2d9b68";
const BYPASSED_GROUP_COLOR = "#68478d";

// R-2（N159 尺寸竞态收口）：傻瓜控制台(≈500) 与只读时间轴(≈700) 同时挂 N159。
// 两者统一采用「只扩大不缩小」的确定性尺寸，最终 N159 size ≥ [880, 1360]，
// 不再由 install* 互相 setSize 覆盖产生竞态。
const FOOLPROOF_PANEL_HEIGHT = 500;
const COEXIST_WIDTH = 880;
const COEXIST_HEIGHT = 1360;

function setNodeSizeMin(node, w, h) {
  const cw = node.size?.[0] || 0;
  const ch = node.size?.[1] || 0;
  node.setSize([Math.max(cw, w), Math.max(ch, h)]);
}

function cardForValue(value) {
  const normalized = normalizeOperationValue(value);
  return OPERATION_CARDS.find((card) => card.value === normalized) || OPERATION_CARDS[0];
}

function normalizeOperationValue(value) {
  const text = String(value ?? "");
  if (OPERATION_KEYS[text]) return text;
  if (text.startsWith("检")) return "检测坏段";
  if (text.startsWith("放")) return "放大/扩时";
  if (text.startsWith("执")) return "执行二采";
  if (text.startsWith("自")) return "自动检测+扩时+二采（实验）";
  if (text.startsWith("无")) return "无任何选项状态";
  return "只跑一采";
}

function normalizeSizeValue(value) {
  return String(value ?? "").startsWith("自") ? "自定义尺寸" : "预设尺寸";
}

function normalizeGenerationValue(value) {
  const text = String(value ?? "");
  if (text.startsWith("多") || text.toUpperCase().startsWith("REF")) return "多参考图（REF2VA）";
  return "文生/单图/首尾帧（FL2VA）";
}

function normalizeImageValue(value) {
  const text = String(value ?? "");
  if (text.startsWith("首")) return "首尾帧生视频";
  if (text.startsWith("单")) return "单图生视频";
  return "文生视频（不用图）";
}

const SPEED_MODES = ["默认（原样）", "画质优先", "高速平衡"];
const SPEED_BRANCH_OF = { "默认（原样）": "default", "画质优先": "quality", "高速平衡": "fast" };
function normalizeSpeedValue(value) {
  const text = String(value ?? "");
  if (text.startsWith("画")) return "画质优先";
  if (text.startsWith("高")) return "高速平衡";
  return "默认（原样）";
}

function operationForGroup(group) {
  const match = /【功能\s*([1-5])/.exec(group?.title || "");
  if (!match) return null;
  return OPERATION_CARDS[Number(match[1]) - 1]?.key || null;
}

function paintOperationNode(candidate, enabled) {
  if (!candidate.__h3OperationOriginalColors) {
    candidate.__h3OperationOriginalColors = {
      color: candidate.color,
      bgcolor: candidate.bgcolor,
    };
  }
  candidate.color = enabled ? ACTIVE_NODE_COLOR : BYPASSED_NODE_COLOR;
  candidate.bgcolor = enabled ? ACTIVE_NODE_BACKGROUND : BYPASSED_NODE_BACKGROUND;
}

function refreshOperationPanel(node, selected) {
  const controls = node.__h3OperationControls;
  if (!controls) return;
  for (const [value, control] of controls.cards) {
    const active = value === selected.value;
    control.card.style.background = active ? "#123b2a" : "#241833";
    control.card.style.borderColor = active ? "#62dfa0" : "#76549a";
    control.card.style.boxShadow = active ? "0 0 0 2px rgba(98,223,160,.18)" : "none";
    control.radio.checked = active;
    control.button.style.background = active ? "#2f9e68" : "#593d78";
    control.button.textContent = active ? `▶ ${control.definition.action}` : control.definition.action;
  }
  controls.state.textContent = selected.key === "none"
    ? "当前状态：全部功能已紫色旁路，不会提交任务。"
    : `当前已点亮：功能 ${selected.number}｜${selected.title}。点击本卡片执行按钮即可，无需点击顶部“运行”。`;
}

function syncOperation(node) {
  if (node?.type !== "H3OperationSelector") return;
  const widget = node.widgets?.find((candidate) => candidate.name === "当前操作");
  const normalizedValue = normalizeOperationValue(widget?.value);
  if (widget && widget.value !== normalizedValue) widget.value = normalizedValue;
  let selected = OPERATION_KEYS[normalizedValue] || "pass1";
  // "无任何选项状态" = base generation only: normal generation (or direct
  // upload output) stays active, while ALL repair chains (detect / expand /
  // resample / auto) are bypassed. Reuse the pass1 routing set so the
  // workflow always keeps its output player active.
  if (selected === "none" && !node.properties?.h3_foolproof_v2) selected = "pass1";
  for (const candidate of node.graph?._nodes || app.graph?._nodes || []) {
    const operation = candidate.properties?.h3_operation;
    if (!operation) continue;
    if (candidate.properties?.h3_force_bypass === true) {
      candidate.mode = 4;
      if (node.properties?.h3_foolproof_v2) paintOperationNode(candidate, false);
      continue;
    }
    const enabled = Array.isArray(operation)
      ? operation.includes(selected)
      : operation === selected;
    candidate.mode = enabled ? 0 : 4;
    if (node.properties?.h3_foolproof_v2) paintOperationNode(candidate, enabled);
  }
  if (node.properties?.h3_foolproof_v2) {
    for (const group of node.graph?._groups || app.graph?._groups || []) {
      const operation = operationForGroup(group);
      if (!operation) continue;
      group.color = operation === selected ? ACTIVE_GROUP_COLOR : BYPASSED_GROUP_COLOR;
    }
  }
  const selectedCard = cardForValue(normalizedValue);
  node.title = node.properties?.h3_dashboard_v3 === true
    ? "【H3 全中文傻瓜导演台】只需要操作这里"
    : node.properties?.h3_foolproof_v2
      ? `【傻瓜控制台】当前：${selectedCard.number}｜${selectedCard.title}`
      : `【当前操作】${widget?.value || "只跑一采"}`;
  refreshOperationPanel(node, selectedCard);
  node.graph?.setDirtyCanvas(true, true);
  app.graph?.change?.();
}

function operationStateProblems(node, selected) {
  const problems = [];
  let activeOutputCount = 0;
  for (const candidate of node.graph?._nodes || app.graph?._nodes || []) {
    const operation = candidate.properties?.h3_operation;
    if (!operation) continue;
    const matches = Array.isArray(operation)
      ? operation.includes(selected)
      : operation === selected;
    const shouldEnable = matches && candidate.properties?.h3_force_bypass !== true;
    const expectedMode = shouldEnable ? 0 : 4;
    if (candidate.mode !== expectedMode) {
      problems.push(`节点 ${candidate.id} 的执行状态应为 ${expectedMode}，实际为 ${candidate.mode}`);
    }
    if (shouldEnable && (
      candidate.type === "SaveVideo" ||
      candidate.type === "ShowText|pysssss" ||
      candidate.type === "PreviewAny"
    )) {
      activeOutputCount += 1;
    }
  }
  if (selected !== "none" && activeOutputCount === 0) {
    problems.push("所选功能没有任何真实输出节点被点亮");
  }
  return problems;
}

function selectOperation(node, widget, value) {
  widget.value = value;
  widget.callback?.(value);
  syncOperation(node);
}

async function queueSelectedOperation(node, widget, definition) {
  const controls = node.__h3OperationControls;
  if (controls?.busy) return;
  selectOperation(node, widget, definition.value);

  if (definition.queue === false) {
    if (controls) controls.state.textContent = "当前状态：全部功能已紫色旁路，不会提交任务。";
    return;
  }

  if (controls) {
    controls.busy = true;
    controls.state.textContent = `正在提交：功能 ${definition.number}｜${definition.title}……`;
    for (const control of controls.cards.values()) control.button.disabled = true;
  }
  try {
    syncAllBranchSelectors(node);
    const videoSourceNode = (node.graph?._nodes || app.graph?._nodes || [])
      .find((candidate) => candidate.properties?.h3_video_source_switch === true);
    if (videoSourceNode) syncVideoSource(videoSourceNode);
    const routeProblems = [
      ...operationStateProblems(node, definition.key),
      ...branchStateProblems(node),
    ];
    if (routeProblems.length) {
      throw new Error(`执行路由自检失败：${routeProblems.join("；")}`);
    }
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await app.queuePrompt(0, 1);
    if (controls) controls.state.textContent = `路由自检通过并已提交：功能 ${definition.number}｜${definition.title}。可在任务历史查看进度。`;
  } catch (error) {
    console.error("[H3] 独立执行失败", error);
    if (controls) controls.state.textContent = `提交失败：${error?.message || error}`;
  } finally {
    if (controls) {
      controls.busy = false;
      for (const control of controls.cards.values()) control.button.disabled = false;
    }
  }
}

function installFoolproofOperationPanel(node, widget) {
  const panel = document.createElement("div");
  panel.style.cssText = "box-sizing:border-box;width:100%;padding:12px;background:#100d18;border:1px solid #76549a;border-radius:9px;color:#fff;font:600 14px sans-serif";

  const heading = document.createElement("div");
  heading.textContent = "六选一傻瓜控制台｜每项独立执行";
  heading.style.cssText = "font-size:18px;color:#e6d8ff;margin-bottom:6px";
  const hint = document.createElement("div");
  hint.textContent = "先点卡片查看对应节点点亮状态；再点卡片内执行按钮。未选功能自动变紫并绕过。";
  hint.style.cssText = "font-size:12px;font-weight:500;color:#c7b4df;margin-bottom:10px;line-height:1.45";

  const grid = document.createElement("div");
  grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:8px";
  const cards = new Map();

  for (const definition of OPERATION_CARDS) {
    const card = document.createElement("div");
    card.style.cssText = "box-sizing:border-box;min-height:132px;padding:10px;border:2px solid #76549a;border-radius:8px;background:#241833;cursor:pointer;transition:.12s ease";
    card.dataset.operation = definition.key;

    const top = document.createElement("label");
    top.style.cssText = "display:flex;gap:8px;align-items:center;cursor:pointer;color:#fff;font-size:15px";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = `h3-operation-${node.id}`;
    radio.value = definition.value;
    radio.style.cssText = "width:18px;height:18px;accent-color:#52d692";
    const title = document.createElement("span");
    title.textContent = `${definition.number}｜${definition.title}`;
    top.append(radio, title);

    const description = document.createElement("div");
    description.textContent = definition.description;
    description.style.cssText = "min-height:36px;margin:8px 0;color:#d4c8e4;font-size:12px;font-weight:500;line-height:1.45";

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = definition.action;
    button.style.cssText = "width:100%;height:34px;border:0;border-radius:6px;background:#593d78;color:#fff;font:700 13px sans-serif;cursor:pointer";

    radio.addEventListener("change", () => selectOperation(node, widget, definition.value));
    card.addEventListener("click", (event) => {
      if (event.target === button || event.target === radio) return;
      selectOperation(node, widget, definition.value);
    });
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      queueSelectedOperation(node, widget, definition);
    });

    card.append(top, description, button);
    grid.appendChild(card);
    cards.set(definition.value, { card, radio, button, definition });
  }

  const state = document.createElement("div");
  state.style.cssText = "margin-top:10px;padding:9px 10px;border-radius:6px;background:#0c241a;color:#aaf1ca;font-size:12px;line-height:1.4";
  panel.append(heading, hint, grid, state);
  for (const eventName of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "wheel", "keydown"]) {
    panel.addEventListener(eventName, (event) => event.stopPropagation());
  }

  node.__h3OperationControls = { panel, cards, state, busy: false };
  const domWidget = node.addDOMWidget("h3_operation_foolproof", "H3_OPERATION_FOOLPROOF", panel, {
    serialize: false,
    hideOnZoom: false,
    getHeight: () => FOOLPROOF_PANEL_HEIGHT,
  });
  domWidget.computeSize = (width) => [width, FOOLPROOF_PANEL_HEIGHT];
  // R-2：与只读时间轴共存时采用确定性宽高（只扩大不缩小，避免互踩 setSize）。
  if (node.properties?.h3_timeline_v1 === true) {
    setNodeSizeMin(node, COEXIST_WIDTH, COEXIST_HEIGHT);
  } else {
    setNodeSizeMin(node, 740, FOOLPROOF_PANEL_HEIGHT + 70);
  }
}

function installOperationSelector(node) {
  if (node?.type !== "H3OperationSelector" || node.__h3OperationReady) return;
  // P1 隔离：候选工作流由独立注册表控制器（h3_workflow_registry_v1.js）
  // 接管操作轴。此选择器带 h3_registry_v1=true 时旧控制器不再接管，
  // 避免双重接管；正式版无此标记，行为完全不变。
  if (node.properties?.h3_registry_v1) return;
  node.__h3OperationReady = true;
  const widget = node.widgets?.find((candidate) => candidate.name === "当前操作");
  if (!widget) return;

  // Keep the backend combo as the serialized source of truth, but replace its
  // tiny canvas presentation with an unmistakable Chinese control surface.
  widget.draw = () => {};
  widget.computeSize = () => [0, -4];

  if (node.properties?.h3_dashboard_v3 === true) {
    const originalCallback = widget.callback;
    widget.callback = function(value) {
      const result = originalCallback?.apply(this, arguments);
      setTimeout(() => syncOperation(node), 0);
      return result;
    };
    setTimeout(() => syncOperation(node), 0);
    return;
  }

  if (node.properties?.h3_foolproof_v2) {
    installFoolproofOperationPanel(node, widget);
    const originalCallback = widget.callback;
    widget.callback = function(value) {
      const result = originalCallback?.apply(this, arguments);
      setTimeout(() => syncOperation(node), 0);
      return result;
    };
    setTimeout(() => syncOperation(node), 0);
    return;
  }

  const panel = document.createElement("div");
  panel.style.cssText = "box-sizing:border-box;width:100%;padding:12px 14px;background:#10261e;border:1px solid #4ba878;border-radius:7px;color:#f3fff8;font:600 15px sans-serif";
  const label = document.createElement("label");
  label.textContent = "当前操作：";
  label.style.cssText = "display:block;margin-bottom:8px;color:#d9ffea";
  const select = document.createElement("select");
  select.style.cssText = "box-sizing:border-box;width:100%;height:40px;padding:6px 10px;border:1px solid #79d8a6;border-radius:5px;background:#091a14;color:#fff;font:600 15px sans-serif;cursor:pointer";
  for (const optionText of Object.keys(OPERATION_KEYS)) {
    const option = document.createElement("option");
    option.value = optionText;
    option.textContent = optionText;
    select.appendChild(option);
  }
  select.value = normalizeOperationValue(widget.value);
  widget.value = select.value;
  select.addEventListener("change", () => {
    widget.value = select.value;
    widget.callback?.(select.value);
    syncOperation(node);
  });
  for (const eventName of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "wheel", "keydown"]) {
    panel.addEventListener(eventName, (event) => event.stopPropagation());
  }
  label.appendChild(select);
  panel.appendChild(label);
  const domWidget = node.addDOMWidget("h3_operation_single_select", "H3_OPERATION_SELECT", panel, {
    serialize: false,
    hideOnZoom: false,
    getHeight: () => 92,
  });
  domWidget.computeSize = (width) => [width, 92];
  node.setSize([740, 155]);

  const originalCallback = widget.callback;
  widget.callback = function(value) {
    const result = originalCallback?.apply(this, arguments);
    if (select.value !== value && OPERATION_KEYS[value]) select.value = value;
    setTimeout(() => syncOperation(node), 0);
    return result;
  };
  setTimeout(() => syncOperation(node), 0);
}

function isH3WorkflowNode(node) {
  return typeof node?.title === "string" && node.title.includes("【");
}

function translatedName(name) {
  if (ZH[name]) return ZH[name];
  let match = /^any_0?(\d+)$/.exec(name);
  if (match) return `候选输入 ${match[1]}`;
  match = /^ref_images\.ref_image_(\d+)$/.exec(name);
  if (match) return `参考图 ${Number(match[1]) + 1}`;
  match = /^ref_videos\.ref_video_(\d+)$/.exec(name);
  if (match) return `参考视频 ${Number(match[1]) + 1}`;
  match = /^ref_audios\.ref_audio_(\d+)$/.exec(name);
  if (match) return `参考音频 ${Number(match[1]) + 1}`;
  match = /^ref_video_audios\.ref_video_audio_(\d+)$/.exec(name);
  if (match) return `参考视频音频 ${Number(match[1]) + 1}`;
  if (name === "*") return "任意数据";
  const dot = name.lastIndexOf(".");
  if (dot > 0 && ZH[name.slice(dot + 1)]) return ZH[name.slice(dot + 1)];
  const grp = /^values\.([a-z])$/.exec(name);
  if (grp) return `计算输入 ${grp[1].toUpperCase()}`;
  return null;
}

function translateNode(node) {
  if (!isH3WorkflowNode(node)) return;
  for (const input of node.inputs || []) {
    input.label = translatedName(input.name) || input.label || input.name;
  }
  for (const output of node.outputs || []) {
    output.label = translatedName(output.name) || output.label || output.name;
  }
  for (const widget of node.widgets || []) {
    if (/^choose .* to upload$/i.test(widget.name)) {
      widget.label = "选择文件上传";
    } else {
      widget.label = translatedName(widget.name) || widget.label || widget.name;
    }
  }
  if (node.title?.startsWith("【视频来源】")) {
    const widget = node.widgets?.find((candidate) => candidate.name === "value");
    if (widget) widget.label = "关＝当前一采｜开＝上传已有视频";
  }
}

function booleanWidgetValue(widget) {
  return widget?.value === true || widget?.value === 1 || widget?.value === "true";
}

function graphNodes(node) {
  return node?.graph?._nodes || app.graph?._nodes || [];
}

function widgetByName(node, name) {
  return node?.widgets?.find((candidate) => candidate.name === name);
}

// v024：永久关闭判定（历史废件 / 强制旁路）。只用于 mode 裁决，绝不用于视觉隐藏。
function isPermanentlyOff(candidate) {
  return candidate?.properties?.h3_force_bypass === true || candidate?.properties?.h3_legacy_disabled === true;
}

function setControlledMode(candidate, enabled, offMode = 4) {
  if (currentOperationKey() === "none" || isPermanentlyOff(candidate)) enabled = false;
  // REF_VIDEO_HARD_OFF_20260906：offMode 允许指定"关"的形态——
  //   4 = BYPASS（直通，适合无同型输入的节点，如 LoadImageCrop / 915）
  //   2 = MUTE（彻底断链，用于有同型输入可直通的节点：669 / 767 / 768 等，
  //        防止 638→136 之类经 bypass 直通的参考泄漏）
  candidate.mode = enabled ? 0 : offMode;
  paintOperationNode(candidate, enabled);
}

function selectedValue(node, widgetName, fallback) {
  return widgetByName(node, widgetName)?.value ?? node?.widgets?.[0]?.value ?? fallback;
}

function fl2vActive(graph) {
  // FL2VA 是否真正激活：生成模式选择器选中 FL2VA 且模型可用
  const nodes = graph?._nodes || app.graph?._nodes || [];
  const generationNode = nodes.find((candidate) => candidate.type === "H3GenerationModeSelector");
  return !normalizeGenerationValue(selectedValue(generationNode, "生成模式", "多参考图（REF2VA）")).startsWith("多参考图")
    && generationNode?.properties?.h3_fl2va_available !== false;
}

const FL2V_ROUTE_MODES = ["主用 F4（FastH3 VSA 4步）", "快速平衡（FastH3 V2 8步）"];

function normalizeFl2vRoute(value) {
  const text = String(value ?? "");
  // 逐项精确匹配（不能用 startsWith：两档都以不同前缀开头，且历史值可能已不在枚举内）；
  // 未识别值一律回落第 1 档＝默认档位不变（主用 F4）。
  const hit = FL2V_ROUTE_MODES.find((mode) => mode === text);
  return hit || FL2V_ROUTE_MODES[0];
}

// 路线显示值 → 节点属性 h3_fl2v_route_branch 的内部分支标识（三处引用必须同源，避免再次分叉）
function fl2vBranchOf(value) {
  return normalizeFl2vRoute(value) === FL2V_ROUTE_MODES[1] ? "v2" : "f4";
}

// 两档生产收口（2026-09-29 BACKEND_SELECTOR_FINAL_CONVERGENCE_01）：
// 稳定8步 = turbo_8step 链（stable8 分支）；PDD8步 = MiniMaxH3PDDAccApply 链（pdd8 分支）。
// original/vsa 为旧值兼容（枚举已移除，选项不再提供；分支节点保留 rollback）。
const REF2VA_BACKEND_MODES = ["稳定多参考8步", "PDD多参考8步", "Native Ref2VA 20步诊断"];
const REF2VA_ATTENTION_MODES = ["标准", "内置 INT8"];

function normalizeRef2vaBackend(value) {
  const text = String(value ?? "");
  if (text === REF2VA_BACKEND_MODES[2]) return "native20";
  if (text.startsWith("PDD")) return "pdd8";
  if (text.startsWith("稳定")) return "stable8";
  if (text.startsWith("官方")) return "official8";
  return text.startsWith("VSA") ? "vsa" : "original";
}

function normalizeRef2vaAttention(value) {
  return String(value ?? "").includes("INT8") ? "int8" : "standard";
}

function syncSpeedMode(node) {
  if (node?.type !== "H3SpeedModeSelector") return;
  const widget = widgetByName(node, "一采模式") || node.widgets?.[0];
  const value = normalizeSpeedValue(widget?.value);
  if (widget && widget.value !== value) widget.value = value;
  const branch = SPEED_BRANCH_OF[value] || "default";
  const fl2v = fl2vActive(node?.graph || app.graph);
  for (const candidate of graphNodes(node)) {
    const tag = candidate.properties?.h3_speed_branch;
    if (!tag) continue;
    const tags = Array.isArray(tag) ? tag : [tag];
    if (fl2v) {
      // FL2V 激活：一采档位链整轴熄灭（透明直通），仅 FL2V 共享件
      // （如 INT8 视频 VAE h3_fl2v_shared=true）保持点亮。
      setControlledMode(candidate, candidate.properties?.h3_fl2v_shared === true);
    } else {
      setControlledMode(candidate, tags.includes(branch));
    }
  }
  node.title = fl2v
    ? `【一采模式·FL2V】当前＝${value}（步数请在 FL2VA 采样设置修改）`
    : `【一采模式·真切换】当前＝${value}（仅作用于功能 1｜一采生成）`;
}

// C2（2026-09-09 作者裁决）：输出文件名前缀按引擎区分 —— FastH3_VSA4 / Ref2VA_Official8。
// 仅当功能1输出节点（VHS_VideoCombine）的 filename_prefix 属于受管集合时才改写；
// 用户自定义的其它前缀一律不碰。纯命名同步，不触碰任何模型链/采样链/连线。
const H3_MANAGED_OUTPUT_PREFIXES = ["H3_v017_FastH3_", "H3_FastH3_VSA4_", "H3_Ref2VA_Official8_", "H3_FastH3_V2_8S_"];
const H3_DEFAULT_OUTPUT_PREFIX = "H3_v017_FastH3_";
function syncOutputFilenamePrefix(graph, engine) {
  for (const candidate of (graph ? graph._nodes : [])) {
    if (candidate.type !== "SaveVideo") continue;
    const prefixWidget = widgetByName(candidate, "filename_prefix");
    if (!prefixWidget || !H3_MANAGED_OUTPUT_PREFIXES.includes(prefixWidget.value)) continue;
    const target = engine || H3_DEFAULT_OUTPUT_PREFIX;
    if (prefixWidget.value !== target) prefixWidget.value = target;
  }
}

function syncFl2vRoute(node) {
  if (node?.type !== "H3Fl2vRouteSelector") return;
  const widget = widgetByName(node, "FL2V 路线") || node.widgets?.[0];
  const value = normalizeFl2vRoute(widget?.value);
  if (widget && widget.value !== value) widget.value = value;
  const route = fl2vBranchOf(value);
  const fl2v = fl2vActive(node?.graph || app.graph);
  for (const candidate of graphNodes(node)) {
    const branch = candidate.properties?.h3_fl2v_route_branch;
    if (branch) setControlledMode(candidate, fl2v && branch === route);
  }
  // C2：FL2VA 模式下按路线命名输出（F4=社区 V1 4-step / V2=官方 FastH3 V2 8-Step）；
  // 非 FL2VA 不触碰（由后端轴管理）。未识别路线回落默认前缀。
  if (fl2v) syncOutputFilenamePrefix(node?.graph || app.graph,
    route === "f4" ? "H3_FastH3_VSA4_" : route === "v2" ? "H3_FastH3_V2_8S_" : null);
  node.title = fl2v
    ? `【单图生视频·路线切换】当前＝${value}`
    : `【单图生视频·路线待机】${value}（当前为多参考生成 Ref2VA）`;
}

function syncRef2vaBackend(node) {
  if (node?.type !== "H3Ref2vaBackendSelector") return;
  const widget = widgetByName(node, "Ref2VA 后端") || node.widgets?.[0];
  // 修复（2026-09-08 第二轮 bug）：line 711 原写 "widget.value = value" 会把 widget
  // 设成内部标识 "vsa"/"original"（非 options 值），下一次 sync 时
  // normalizeRef2vaBackend 因 "vsa" 不 startsWith "VSA" 反而判为 "original"，
  // 造成 g2p 提交时 VSA 链被错误熄灭、原版链被错误点亮。必须写回完整 options 值。
  const normalized = normalizeRef2vaBackend(widget?.value);
  const displayValue = normalized === "pdd8" || normalized === "official8" ? REF2VA_BACKEND_MODES[1]
    : normalized === "stable8" ? REF2VA_BACKEND_MODES[0]
    : normalized === "native20" ? REF2VA_BACKEND_MODES[2]
    : null; // original/vsa 旧值：选项已移除，不强写，保留旧文本提示用户重选
  if (displayValue && widget && widget.value !== displayValue) widget.value = displayValue;
  const ref2va = !fl2vActive(node?.graph || app.graph);
  const backend = normalized;
  for (const candidate of graphNodes(node)) {
    const tag = candidate.properties?.h3_ref2va_backend_branch;
    if (tag) {
      const isTail = candidate.properties?.h3_ref2va_backend_tail === true;
      if (tag === "native20") {
        setControlledMode(candidate, ref2va && backend === "native20", 2);
      } else if (tag === "stable8") {
        // 稳定8步分支（两档收口）：turbo_8step 健康路线（00029 形态），与 PDD 链物理隔离
        const on = ref2va && backend === "stable8";
        setControlledMode(candidate, on, isTail ? 2 : 4);
      } else if (tag === "pdd8" || tag === "official8") {
        // PDD 分支：MiniMaxH3PDDAccApply 新链；official8 为旧图标签兼容（同指 PDD 链）
        const on = ref2va && (backend === "pdd8" || backend === "official8");
        setControlledMode(candidate, on, isTail ? 2 : 4);
      } else if (tag === "vsa") {
        // VSA 分支：仅 ref2va+vsa 点亮；否则整链旁路，尾部 MUTE(2) 真断
        const on = ref2va && backend === "vsa";
        setControlledMode(candidate, on, isTail ? 2 : 4);
      } else if (tag === "official8") {
        // 官方8步分支（v020，2026-09-09）：仅 ref2va+official8 点亮；
        // 否则整链旁路，尾部 MUTE(2) 真断（与 VSA 分支同规则，互斥）。
        const on = ref2va && backend === "official8";
        setControlledMode(candidate, on, isTail ? 2 : 4);
      } else {
        // 原版分支：仅在 REF2VA 模式下由本轴裁决；FL2VA 模式下不触碰（交给 speed 轴 BYPASS 直通）
        if (ref2va) {
          if (backend === "original") {
            // M8-FIX（2026-09-08 作者裁决）：backend 轴只决定 original/VSA，
            // speed 轴才决定 original 内部 default/quality/fast。若节点带
            // h3_speed_branch，说明它属于原版 speed 三档，本轴不得修改其 mode
            // （保留 syncSpeedMode 已做出的三档裁决）；否则（original 专属、不
            // 属 speed 三档）才允许 backend 轴保持其正常 active。
            if (candidate.properties?.h3_speed_branch) {
              // 不做任何 mode 写入，保留 syncSpeedMode 的裁决
            } else {
              setControlledMode(candidate, true, isTail ? 2 : 4);
            }
          } else {
            setControlledMode(candidate, false, isTail ? 2 : 4);
          }
        }
      }
    }
    const vaeTag = candidate.properties?.h3_vsa_vae;
    if (vaeTag) {
      if (ref2va && backend === "vsa") {
        // VSA 档：解码 VAE 钉 FP16（REAL_v2 一致）；INT8 熄灭(MUTE)
        setControlledMode(candidate, vaeTag === "fp16", 2);
      }
    }
    // C1（2026-09-08 作者裁决）：ref_image_size 按后端切换 —— 原版 max / VSA match / 官方8步 match。
    // 绑定 N931 后端状态，切回 original 自动恢复 max；不写死、不新增控制项、不新建 conditioning。
    if (ref2va && candidate.type === "MiniMaxH3ReferenceToVideo") {
      const sizeWidget = widgetByName(candidate, "ref_image_size");
      if (sizeWidget) {
        const targetSize = backend === "original" ? "max" : "match";
        if (sizeWidget.value !== targetSize) sizeWidget.value = targetSize;
      }
    }
  }
  const backendLabel = normalized === "native20" ? "Native Ref2VA 20步诊断"
    : normalized === "stable8" ? "稳定多参考8步"
    : normalized === "pdd8" || normalized === "official8" ? "PDD多参考8步"
    : normalized === "vsa" ? "VSA Ref2VA" : "原版 Ref2VA";
  // C2：REF2VA 模式下按后端命名输出（官方8步专用前缀，其余恢复默认）；非 REF2VA 不触碰（由 FL2V 路线轴管理）
  if (ref2va) syncOutputFilenamePrefix(node?.graph || app.graph, backend === "official8" ? "H3_Ref2VA_Official8_" : null);
  node.title = ref2va
    ? `【多参考生成·后端切换】当前＝${backendLabel}`
    : `【多参考生成·后端待机】${backendLabel}（当前为单图生视频 FL2VA）`;
}

function syncRef2vaAttention(node) {
  if (node?.type !== "H3Ref2vaAttentionSelector") return;
  const widget = widgetByName(node, "注意力方案") || node.widgets?.[0];
  const attention = normalizeRef2vaAttention(widget?.value);
  const displayValue = attention === "int8" ? REF2VA_ATTENTION_MODES[1] : REF2VA_ATTENTION_MODES[0];
  if (widget && widget.value !== displayValue) widget.value = displayValue;
  const nodes = graphNodes(node);
  const backendNode = nodes.find((candidate) => candidate.type === "H3Ref2vaBackendSelector");
  const backend = normalizeRef2vaBackend(selectedValue(backendNode, "Ref2VA 后端", REF2VA_BACKEND_MODES[0]));
  // N950_PDD8_FIX（2026-09-29）：两档收口后 PDD 档 normalize 为 "pdd8"（startsWith("PDD")），
  // 本轴点亮条件若只认 "official8"，新图 PDD 档下 N950(ModelAttentionBackend INT8) 永远 mode=4
  // → INT8 attention 不进执行图 → 10.8 s/it 结构性劣化为 17-18 s/it。
  // official8 与 pdd8 在两档收口后同指 PDD 链（见 syncRef2vaBackend L856 注释），一并点亮。
  const enabled = !fl2vActive(node?.graph || app.graph) && (backend === "official8" || backend === "pdd8") && attention === "int8";
  for (const candidate of nodes) {
    if (candidate.properties?.h3_ref2va_attention_branch === "int8") {
      setControlledMode(candidate, enabled, 4);
    }
  }
  node.title = (backend === "official8" || backend === "pdd8")
    ? `【注意力方案·真切换】当前＝${displayValue}`
    : `【注意力方案·待机】${displayValue}（仅PDD 8步）`;
}

function syncMemoryOptimization(node) {
  if (node?.type !== "H3MemoryOptimizationSelector") return;
  const widget = widgetByName(node, "H3内存优化") || node.widgets?.[0];
  const value = String(widget?.value ?? "关闭") === "开启" ? "开启" : "关闭";
  if (widget && widget.value !== value) widget.value = value;
  const nodes = graphNodes(node);
  const backendNode = nodes.find((candidate) => candidate.type === "H3Ref2vaBackendSelector");
  const backend = normalizeRef2vaBackend(selectedValue(backendNode, "Ref2VA 后端", REF2VA_BACKEND_MODES[0]));
  // N998_PDD8_FIX（2026-09-29）：与 N950_PDD8_FIX 同类。两档收口后 PDD 档 normalize 为
  // "pdd8"（startsWith("PDD")），而本轴点亮条件只认 "official8"（旧图兼容值，选项枚举已无），
  // 导致新图 PDD 档下 N998(H3MemoryOptimization) 永远无法点亮，与设计意图
  // "开启时仅作用于 PDD 8步"（N998/N999 title 自证）相悖。pdd8 与 official8 一并点亮。
  const enabled = !fl2vActive(node?.graph || app.graph) && (backend === "pdd8" || backend === "official8") && value === "开启";
  for (const candidate of nodes) {
    if (candidate.properties?.h3_memory_opt_branch === true) setControlledMode(candidate, enabled, 4);
  }
  node.title = (backend === "pdd8" || backend === "official8")
    ? `【H3内存优化·高级开关】当前＝${value}`
    : `【H3内存优化·待机】${value}（仅PDD 8步）`;
}

// ===== 时间轴关键帧轴（V26 STEP 34，2026-09-20）=====
// 概念边界（作者方案 §8）：Reference＝语义参考（不规定第几帧出现）；
// Guide＝时间轴锚点（规定第 frame_idx 帧必须是这张画面）。本轴只接管
// properties.h3_guide_branch = 1/2/3 的关键帧链，与生成模式（REF2VA/FL2VA）正交：
// 三条链都挂在共享的 N648（正向条件）→ N126（引导器）之间，旁路即直通＝零影响。
const GUIDE_MODES = ["不使用关键帧", "1 个关键帧画面", "2 个关键帧画面", "3 个关键帧画面"];
// 与 nodes.py 的 SENTINEL_GUIDE_NAME 同值：关键帧图片未选择时钉在这个占位上，
// 由 H3GuideImageGuard 在执行期抛中文错误（fail-closed，不自动回退）。
const SENTINEL_GUIDE_IMAGE = "__H3_GUIDE_NOT_SET__.png";

function guideCountOf(value) {
  const hit = GUIDE_MODES.findIndex((mode) => mode === String(value ?? ""));
  return hit > 0 ? hit : 0; // 未识别值一律回落「不使用」＝默认路线不变
}

function guideModeValue(graph) {
  const nodes = graph?._nodes || app.graph?._nodes || [];
  const selector = nodes.find((candidate) => candidate.type === "H3GuideModeSelector");
  return guideCountOf(selectedValue(selector, "关键帧控制", GUIDE_MODES[0]));
}

function syncGuideMode(node) {
  if (node?.type !== "H3GuideModeSelector") return;
  const widget = widgetByName(node, "关键帧控制") || node.widgets?.[0];
  const value = GUIDE_MODES[guideCountOf(widget?.value)];
  if (widget && widget.value !== value) widget.value = value;
  const count = guideCountOf(value);
  for (const candidate of graphNodes(node)) {
    const slot = Number(candidate.properties?.h3_guide_branch);
    if (slot) setControlledMode(candidate, count >= slot);
  }
  node.title = count
    ? `【时间轴关键帧·真切换】当前＝${count} 个（每张图规定第几帧出现）`
    : "【时间轴关键帧·关闭】默认不用关键帧";
}

// ============================================================================
// STEP 7（V27 唯一新增能力）：【接续生产】轴
// 官方 ComfyUI-H3-Motion-Context v0.6.2 的中文薄壳：本段只负责"点亮/旁路官方链 +
// 写官方自带的档位下拉"，不含任何接续算法（P3 REUSE FIRST / thin adapter）。
//   关闭（默认）＝ 整条官方链 m4 直通 ⇒ conditioning / 画面 / 音频原样透传，
//                官方节点不进 /prompt ⇒ 执行输入与 V26 冻结基线逐项一致（STEP 8）。
//   开启        ＝ 官方五节点 m0：读取上一段 → 接续 → 去掉片头保护区 → 存档 → 分段推进。
// 用户可见文案里禁止出现 Motion Context / latent / context_latent / match_tail /
// head anchor / timeline audio —— 这些技术名只登记在 nodes.py 的 TECHNICAL_ALIAS。
// ============================================================================
const CONTINUATION_MODES = ["关闭（本段独立起步）", "开启（接上一段继续演）"];
const CONTINUATION_STRENGTHS = ["自动", "更强连续"];
// 档位 → 官方 context_length（官方只接受 "5"/"22"/"39"/"56" 这几个整潜空间步）
const CONTINUATION_CONTEXT_LENGTH = { "自动": "22", "更强连续": "39" };
// STEP 10：官方 MiniMaxH3MotionContext 会丢弃落在保护区内的关键帧锚点（源码
// nodes.py:626-656 "Anchors inside the pinned head are dropped"）。这里不做任何
// 拦截或改写，只把这条官方既有行为用中文提前告诉用户，杜绝"静默失效"。
const CONTINUATION_GUIDE_NOTICE = "【该关键帧位于接续保护区，已自动忽略】";

function continuationModeValue(value) {
  return CONTINUATION_MODES.indexOf(String(value ?? "")) > 0
    ? CONTINUATION_MODES[1] : CONTINUATION_MODES[0]; // 未识别值回落「关闭」＝默认路线不变
}

function continuationStrengthValue(value) {
  const hit = CONTINUATION_STRENGTHS.indexOf(String(value ?? ""));
  return hit > 0 ? CONTINUATION_STRENGTHS[hit] : CONTINUATION_STRENGTHS[0];
}

function continuationState(graph) {
  // 唯一事实源 = H3ContinuationSelector。它自身不进 /prompt 不是靠 RETURN_TYPES=()
  // 实现的（实测：已注册的后端类即使没有输出也会被写进 /prompt，MarkdownNote 之
  // 所以干净是因为它压根不是后端类），而是靠下面 stripUiOnlyNodes() 在提交前摘掉。
  const nodes = graph?._nodes || app.graph?._nodes || [];
  const selector = nodes.find((candidate) => candidate.type === "H3ContinuationSelector");
  const mode = continuationModeValue(selectedValue(selector, "接续生产", CONTINUATION_MODES[0]));
  const strength = continuationStrengthValue(selectedValue(selector, "接续强度", CONTINUATION_STRENGTHS[0]));
  // 接续链只挂在功能 1（一采）的条件链与输出链上：检测/扩时/二采/自动修复时
  // 必须整体保持直通，否则会污染那些功能的帧对齐与时间轴。操作轴唯一事实源
  // 复用 currentOperationKey()，不另立第二套判定。
  const pass1Active = currentOperationKey() === "pass1";
  return {
    present: Boolean(selector),
    enabled: mode === CONTINUATION_MODES[1] && pass1Active,
    requested: mode === CONTINUATION_MODES[1],
    strength,
    contextLength: CONTINUATION_CONTEXT_LENGTH[strength],
  };
}

function stripContinuationNotice(title) {
  const text = String(title ?? "");
  return text.endsWith(CONTINUATION_GUIDE_NOTICE)
    ? text.slice(0, text.length - CONTINUATION_GUIDE_NOTICE.length) : text;
}

function annotateProtectedGuides(node, enabled, headFrames) {
  // 只改标题（UI 层），不改 mode、不改 frame_idx、不碰连线。
  for (const candidate of graphNodes(node)) {
    if (candidate.type !== "MiniMaxH3AddGuide") continue;
    const base = stripContinuationNotice(candidate.title);
    if (!enabled || candidate.mode !== 0) {
      if (candidate.title !== base) candidate.title = base;
      continue;
    }
    const widget = widgetByName(candidate, "frame_idx");
    const index = Number(widget?.value ?? candidate.widgets_values?.[0] ?? 0);
    const next = Number.isFinite(index) && index < headFrames ? base + CONTINUATION_GUIDE_NOTICE : base;
    if (candidate.title !== next) candidate.title = next;
  }
}

function syncContinuation(node) {
  if (node?.type !== "H3ContinuationSelector") return;
  const modeWidget = widgetByName(node, "接续生产") || node.widgets?.[0];
  const strengthWidget = widgetByName(node, "接续强度") || node.widgets?.[1];
  const mode = continuationModeValue(modeWidget?.value);
  const strength = continuationStrengthValue(strengthWidget?.value);
  if (modeWidget && modeWidget.value !== mode) modeWidget.value = mode;
  if (strengthWidget && strengthWidget.value !== strength) strengthWidget.value = strength;
  // 归一化写完再取状态，保证 mode / context_length / 标题三者同源
  const state = continuationState(node?.graph || app.graph);
  for (const candidate of graphNodes(node)) {
    if (candidate.properties?.h3_continuation_branch !== true) continue;
    setControlledMode(candidate, state.enabled); // 关闭＝m4 直通（官方链整体退出执行图）
  }
  for (const candidate of graphNodes(node)) {
    if (candidate.type !== "MiniMaxH3MotionContext") continue;
    const widget = widgetByName(candidate, "context_length");
    if (widget && String(widget.value) !== state.contextLength) widget.value = state.contextLength;
  }
  annotateProtectedGuides(node, state.enabled, Number(state.contextLength));
  node.title = state.enabled
    ? `【接续生产·开启】接上一段继续演（强度＝${strength}）`
    : state.requested
      ? "【接续生产·暂不生效】接续只用于功能 1（一采生成），请切回功能 1"
      : "【接续生产·关闭】本段独立起步（默认，与本功能加入前完全一致）";
  node.graph?.setDirtyCanvas?.(true, true);
}

// 纯 UI 事实源开关：图上确实一根线都没连时，不进提交级 /prompt。
// UI_REFACTOR_01：H3V28DirectorConsole（【V28 剧情自动导演】）是同一待遇的
// 纯 UI 节点——零连线时提交前摘除；一旦有人接线绝不静默删除（保守边界不变）。
const UI_ONLY_SELECTOR_TYPES = new Set(["H3ContinuationSelector", "H3MemoryOptimizationSelector", "H3V28DirectorConsole"]);

function hasAnyConnection(node) {
  for (const slot of node?.inputs || []) {
    if (slot?.link != null && slot.link !== -1) return true;
  }
  for (const slot of node?.outputs || []) {
    if (Array.isArray(slot?.links) && slot.links.length) return true;
  }
  return false;
}

function stripUiOnlyNodes(graph, output) {
  // 为什么要摘：前端会把任何「已注册后端类」写进 /prompt，哪怕它没有输出、
  // 不喂任何执行输入。STEP 8 要求「接续生产＝关闭」时提交级 prompt 与 V26
  // canonical 逐项相等，所以按 V26 对纯 UI 节点（MarkdownNote）的既有待遇，
  // 把这个开关从执行图里摘掉——它的全部作用已经由 syncContinuation() 落进
  // 官方节点的 mode / context_length 里了。
  // 保守边界：只摘「类型在白名单 且 零连线」的节点。一旦有人真的接了线，
  // 宁可多留一个空操作节点，也绝不静默删掉可能承载语义的东西。
  if (!output) return output;
  const nodes = graph?._nodes || app.graph?._nodes || [];
  for (const candidate of nodes) {
    if (!UI_ONLY_SELECTOR_TYPES.has(candidate.type)) continue;
    if (hasAnyConnection(candidate)) continue;
    delete output[String(candidate.id)];
  }
  return output;
}

function syncSizeMode(node) {
  if (node?.type !== "H3SizeModeSelector") return;
  const widget = widgetByName(node, "尺寸模式") || node.widgets?.[0];
  const value = normalizeSizeValue(widget?.value);
  if (widget && widget.value !== value) widget.value = value;
  const selectedBranch = value === "自定义尺寸" ? "custom" : "preset";
  for (const candidate of graphNodes(node)) {
    const branch = candidate.properties?.h3_size_branch;
    if (branch) setControlledMode(candidate, branch === selectedBranch);
  }
  node.title = `【尺寸模式·真切换】当前＝${value}`;
}

function syncGenerationMode(node) {
  if (node?.type !== "H3GenerationModeSelector") return;
  const widget = widgetByName(node, "生成模式") || node.widgets?.[0];
  let value = normalizeGenerationValue(widget?.value);
  const fl2vaAvailable = node.properties?.h3_fl2va_available !== false;
  if (!fl2vaAvailable && value.includes("FL2VA")) value = "多参考图（REF2VA）";
  if (widget && widget.value !== value) widget.value = value;
  const selectedBranch = value.startsWith("多参考图") ? "ref2va" : "fl2va";
  for (const candidate of graphNodes(node)) {
    const branch = candidate.properties?.h3_generation_branch;
    if (branch) setControlledMode(candidate, branch === selectedBranch);
  }
  node.title = fl2vaAvailable
    ? `【生成模式·真切换】当前＝${value}`
    : `【生成模式·安全锁】REF2VA（FL2VA 专用模型未安装）`;
}

function syncImageMode(node) {
  if (node?.type !== "H3ImageModeSelector") return;
  const widget = widgetByName(node, "图片模式") || node.widgets?.[0];
  const value = normalizeImageValue(widget?.value);
  if (widget && widget.value !== value) widget.value = value;
  const generationNode = graphNodes(node).find((candidate) => candidate.type === "H3GenerationModeSelector");
  const fl2vaActive = !normalizeGenerationValue(selectedValue(generationNode, "生成模式", "多参考图（REF2VA）")).startsWith("多参考图") && generationNode?.properties?.h3_fl2va_available !== false;
  const enabledBranches = new Set();
  if (value === "单图生视频") enabledBranches.add("first");
  if (value === "首尾帧生视频") {
    enabledBranches.add("first");
    enabledBranches.add("last");
  }
  for (const candidate of graphNodes(node)) {
    const branch = candidate.properties?.h3_image_mode_branch;
    if (branch) setControlledMode(candidate, fl2vaActive && enabledBranches.has(branch));
  }
  node.title = fl2vaActive
    ? `【图片模式·真切换】当前＝${value}`
    : `【图片模式·待机】${value}（当前为 REF2VA）`;
}

function referenceSelections(node) {
  return {
    images: booleanWidgetValue(widgetByName(node, "启用四张参考图")),
    video: booleanWidgetValue(widgetByName(node, "启用参考视频")),
    audio1: booleanWidgetValue(widgetByName(node, "启用参考音频1")),
    audio2: booleanWidgetValue(widgetByName(node, "启用参考音频2")),
    // REF_MASTER_CONTROL_20260906：第 5 项总控开关——后处理上传视频链
    // （766/767/768/769/770）的唯一控制源，与四个 REF2VA 参考开关独立。
    upload: booleanWidgetValue(widgetByName(node, "后处理使用上传视频")),
  };
}

function sharedVideoLoaderEnabled(graph) {
  // SHARED_LOADER_ARBITRATION_20260906：638 的出栈仲裁改为只看总控两个开关：
  //   后处理上传视频 = 开  → 638 工作（供 769 后处理链）
  //   参考视频 = 开 且 REF2VA 激活 → 638 工作（供 669→136 参考链）
  // 两者都关 → 638 出栈（不再进入执行队列）。
  // 不再读取 766 的布尔值（766 已降级为内部选择器，随总控自动同步）。
  const nodes = graph?._nodes || app.graph?._nodes || [];
  const references = nodes.find((candidate) => candidate.type === "H3ReferenceSourceSelector");
  if (!references) return false;
  const selections = referenceSelections(references);
  const generationNode = nodes.find((candidate) => candidate.type === "H3GenerationModeSelector");
  const ref2vaActive = normalizeGenerationValue(selectedValue(generationNode, "生成模式", "多参考图（REF2VA）")).startsWith("多参考图") || generationNode?.properties?.h3_fl2va_available === false;
  const referenceVideoEnabled = selections.video && ref2vaActive;
  const uploadEnabled = Boolean(selections.upload);
  return uploadEnabled || referenceVideoEnabled;
}

function syncSharedVideoLoader(node) {
  for (const candidate of graphNodes(node)) {
    if (candidate.properties?.h3_shared_video_loader === true) {
      // SHARED_LOADER_ARBITRATION_20260906：638 关闭时用 MUTE(2) 彻底出栈，
      // 不留 BYPASS 直通通道（与"关就是彻底关"总控原则一致）。
      setControlledMode(candidate, sharedVideoLoaderEnabled(node?.graph || app.graph), 2);
    }
  }
}

function syncReferenceSources(node) {
  if (node?.type !== "H3ReferenceSourceSelector") return;
  const selections = referenceSelections(node);
  const generationNode = graphNodes(node).find((candidate) => candidate.type === "H3GenerationModeSelector");
  const ref2vaActive = normalizeGenerationValue(selectedValue(generationNode, "生成模式", "多参考图（REF2VA）")).startsWith("多参考图") || generationNode?.properties?.h3_fl2va_available === false;
  for (const candidate of graphNodes(node)) {
    const branch = candidate.properties?.h3_reference_branch;
    if (branch) {
      const on = ref2vaActive && Boolean(selections[branch]) && candidate.properties?.h3_reference_slot_enabled !== false;
      // REF_VIDEO_HARD_OFF_20260906：参考视频链的"关"必须彻底断链。
      // 669 一旦 BYPASS，前端直通语义（_getBypassSlotIndex）会把 638 的
      // 原始视频继续送进 136.ref_videos（638→136 泄漏）。凡带
      // h3_video_hard_link 标记的节点，关闭时用 MUTE(mode 2)：节点不序列化、
      // 连接死链删除，136 真正收不到任何参考视频。
      const offMode = branch === "video" && candidate.properties?.h3_video_hard_link === true ? 2 : 4;
      setControlledMode(candidate, on, offMode);
    }
    // UPLOAD_CHAIN_MASTER_20260906：后处理上传视频链（766/767/768/769/770）
    // 整体由总控第 5 项「后处理使用上传视频」控制：
    //   关 = 整链 MUTE(mode 2)（LazySwitch3/767 有多个 * 型输入，若用 BYPASS
    //        会把一采结果直通漏进检测链，故必须 MUTE）
    //   开 = 整链恢复；766 内部选择值固定为"上传视频"（用户不可见、不可操作）
    if (candidate.properties?.h3_upload_chain === true) {
      setControlledMode(candidate, Boolean(selections.upload), 2);
      if (selections.upload && candidate.properties?.h3_upload_chain_source === true) {
        const sourceWidget = widgetByName(candidate, "value") || candidate.widgets?.[0];
        if (sourceWidget) sourceWidget.value = true;
      }
    }
  }
  syncSharedVideoLoader(node);
  mirrorReferenceState(node);
  // 【参考素材总控】傻瓜化状态标题：一眼看清当前开了哪些参考。
  const labels = { images: "图片", video: "视频", audio1: "音频1", audio2: "音频2" };
  const active = Object.keys(labels).filter((key) => selections[key]).map((key) => labels[key]);
  // §7.1：foolproof v2 下在标题追加「参考图自动重排：开」状态行（运行期只读提示）。
  const foolproofActive = graphNodes(node).some((candidate) => candidate.properties?.h3_foolproof_v2 === true);
  node.title = `【参考素材总控】当前参考素材：${active.length ? active.join("＋") : "无"}｜后处理上传视频：${selections.upload ? "开" : "关"}` +
    (foolproofActive ? "｜参考图自动重排：开" : "");
}

function mirrorReferenceState(node) {
  // P3F1: 把 N150(H3ReferenceSourceSelector) 的真实开关状态镜像到全图
  // H3VideoPromptRole 的内部镜像 widget（picture_refs_enabled / audio1_enabled /
  // audio2_enabled）。用户仍只操作 N150；N915 内部状态自动同步、不显示为
  // 第二套开关（widget 以 type=hidden 隐藏，值仍随 graphToPrompt 序列化）。
  const graph = node?.graph || window.app?.graph;
  if (!graph) return;
  const refNode = (graph._nodes || []).find((candidate) => candidate.type === "H3ReferenceSourceSelector");
  if (!refNode) return;
  const sels = referenceSelections(refNode);
  for (const candidate of graph._nodes || []) {
    if (candidate.type !== "H3VideoPromptRole") continue;
    const mirror = (name, value) => {
      const w = candidate.widgets?.find((x) => x.name === name);
      if (!w) return;
      w.value = value;
      if (w.type !== "hidden") {
        w.type = "hidden"; // 只读镜像：不绘制、不可点击；值仍被 graphToPrompt 序列化
        if (w.options && typeof w.options === "object") w.options.serialize = true;
      }
    };
    mirror("picture_refs_enabled", sels.images);
    mirror("audio1_enabled", sels.audio1);
    mirror("audio2_enabled", sels.audio2);
    // VIDEO_SWITCH_INDEPENDENT_MINIMAL_FIX_20260905：补上视频参考镜像。
    // 唯一事实源 = N150「启用参考视频」；video_refs_enabled 只是内部镜像值，
    // 随开关同步（与模式选择无关）。此前缺这条镜像，导致 N915 的
    // video_refs_enabled 保持独立默认 True —— 表现为"选 REF2VA 即视频参考
    // 自动推导为 True"。mirror() 同时把 widget 置为 hidden，消除第二可见开关。
    mirror("video_refs_enabled", sels.video);
    candidate.graph?.setDirtyCanvas?.(true, true);
  }
}

function currentOperationKey() {
  const opNode = (app.graph?._nodes || []).find((candidate) => candidate.type === "H3OperationSelector");
  const widget = opNode?.widgets?.find((candidate) => candidate.name === "当前操作");
  return OPERATION_KEYS[normalizeOperationValue(widget?.value)] || "pass1";
}

function syncAllBranchSelectors(node) {
  // 【none 门控】"无任何选项状态"= 真正全关：syncOperation 已把所有带
  // h3_operation 标签节点设为 BYPASS；分支同步无条件执行会把分支标签
  // 节点（如 h3_generation_branch / h3_reference_branch）强制回 ALWAYS，
  // 造成 none 模式下仍有节点运行。none 模式下跳过所有分支同步。
  if (currentOperationKey() === "none") {
    for (const candidate of graphNodes(node)) {
      if (Object.keys(candidate.properties || {}).some((k) => k.startsWith("h3_") && (k.endsWith("_branch") || k === "h3_shared_video_loader" || k === "h3_upload_chain"))) setControlledMode(candidate, false);
    }
    return;
  }
  const nodes = graphNodes(node);
  // v024：先强制拉回锁定值（N873 一采模式等），再同步分支
  for (const candidate of nodes) enforceLockedValues(candidate);
  for (const candidate of nodes) syncSizeMode(candidate);
  for (const candidate of nodes) syncGenerationMode(candidate);
  for (const candidate of nodes) syncImageMode(candidate);
  for (const candidate of nodes) syncReferenceSources(candidate);
  for (const candidate of nodes) syncSpeedMode(candidate);
  for (const candidate of nodes) syncFl2vRoute(candidate); // OI-1 补丁(2026-09-04 作者裁决A)：接线 FL2V 路线真切换
  for (const candidate of nodes) syncRef2vaBackend(candidate); // 双 Ref2VA 后端轴（覆盖 speed 轴的旁路状态）
  for (const candidate of nodes) syncRef2vaAttention(candidate); // 官方8步内部注意力二级轴
  for (const candidate of nodes) syncMemoryOptimization(candidate); // V28.1：PDD MemoryOpt 高级开关（默认关闭）
  for (const candidate of nodes) syncGuideMode(candidate); // STEP 34：时间轴关键帧轴（默认关闭＝直通）
  for (const candidate of nodes) syncContinuation(candidate); // STEP 7（V27）：接续生产轴（默认关闭＝直通）
  const videoSource = nodes.find((candidate) => candidate.properties?.h3_video_source_switch === true);
  if (videoSource) syncVideoSource(videoSource);
}

function branchStateProblems(node) {
  // 【none 门控】none 模式下分支节点应全为 BYPASS，不做分支期望校验
  if (currentOperationKey() === "none") return [];
  const problems = [];
  const nodes = graphNodes(node);
  const sizeNode = nodes.find((candidate) => candidate.type === "H3SizeModeSelector");
  const sizeBranch = normalizeSizeValue(selectedValue(sizeNode, "尺寸模式", "预设尺寸")) === "自定义尺寸" ? "custom" : "preset";
  const generationNode = nodes.find((candidate) => candidate.type === "H3GenerationModeSelector");
  const generationBranch = normalizeGenerationValue(selectedValue(generationNode, "生成模式", "多参考图（REF2VA）")).startsWith("多参考图") || generationNode?.properties?.h3_fl2va_available === false ? "ref2va" : "fl2va";
  const imageNode = nodes.find((candidate) => candidate.type === "H3ImageModeSelector");
  const imageValue = normalizeImageValue(selectedValue(imageNode, "图片模式", "文生视频（不用图）"));
  const imageBranches = new Set(imageValue === "单图生视频" ? ["first"] : imageValue === "首尾帧生视频" ? ["first", "last"] : []);
  const referenceNode = nodes.find((candidate) => candidate.type === "H3ReferenceSourceSelector");
  const references = referenceNode ? referenceSelections(referenceNode) : {};
  const speedNode = nodes.find((candidate) => candidate.type === "H3SpeedModeSelector");
  const speedBranch = SPEED_BRANCH_OF[normalizeSpeedValue(selectedValue(speedNode, "一采模式", "默认（原样）"))] || "default";
  const ref2vaActive = generationBranch === "ref2va";
  const fl2vaActive = generationBranch === "fl2va";
  // UPLOAD_CHAIN_MASTER_20260906：上传开关唯一事实源 = 总控第 5 项
  const uploadEnabled = Boolean(references.upload);
  const routeSelector = nodes.find((candidate) => candidate.type === "H3Fl2vRouteSelector");
  const fl2vRoute = fl2vBranchOf(selectedValue(routeSelector, "FL2V 路线", FL2V_ROUTE_MODES[0])); // 与 syncFl2vRoute 同源映射（f4 / v2）
  const ref2vaBackendNode = nodes.find((candidate) => candidate.type === "H3Ref2vaBackendSelector");
  const ref2vaBackend = normalizeRef2vaBackend(selectedValue(ref2vaBackendNode, "Ref2VA 后端", REF2VA_BACKEND_MODES[0]));
  const ref2vaAttentionNode = nodes.find((candidate) => candidate.type === "H3Ref2vaAttentionSelector");
  const ref2vaAttention = normalizeRef2vaAttention(selectedValue(ref2vaAttentionNode, "注意力方案", REF2VA_ATTENTION_MODES[0]));
  const memoryOptNode = nodes.find((candidate) => candidate.type === "H3MemoryOptimizationSelector");
  const memoryOptEnabled = selectedValue(memoryOptNode, "H3内存优化", "关闭") === "开启";
  const guideCount = guideModeValue(node?.graph || app.graph); // STEP 34：时间轴关键帧轴
  const continuation = continuationState(node?.graph || app.graph); // STEP 7（V27）：接续生产轴
  for (const candidate of nodes) {
    // v024：永久关闭节点不参与一致性审计（N674 等历史废件，mode 恒为 4）
    if (isPermanentlyOff(candidate)) continue;
    let expected = null;
    if (candidate.properties?.h3_size_branch) expected = candidate.properties.h3_size_branch === sizeBranch;
    if (candidate.properties?.h3_generation_branch) expected = candidate.properties.h3_generation_branch === generationBranch;
    if (candidate.properties?.h3_image_mode_branch) expected = fl2vaActive && imageBranches.has(candidate.properties.h3_image_mode_branch);
    if (candidate.properties?.h3_reference_branch) expected = ref2vaActive && Boolean(references[candidate.properties.h3_reference_branch]) && candidate.properties?.h3_reference_slot_enabled !== false;
    if (candidate.properties?.h3_speed_branch) {
      if (fl2vaActive) {
        // FL2V 激活：一采档位链整轴熄灭，仅 FL2V 共享件（h3_fl2v_shared）保持点亮
        expected = candidate.properties?.h3_fl2v_shared === true;
      } else {
        const speedTags = Array.isArray(candidate.properties.h3_speed_branch) ? candidate.properties.h3_speed_branch : [candidate.properties.h3_speed_branch];
        expected = speedTags.includes(speedBranch);
      }
    }
    if (candidate.properties?.h3_fl2v_route_branch) expected = fl2vaActive && candidate.properties.h3_fl2v_route_branch === fl2vRoute;
    if (candidate.properties?.h3_guide_branch) expected = guideCount >= Number(candidate.properties.h3_guide_branch);
    if (candidate.properties?.h3_continuation_branch === true) expected = continuation.enabled;
    if (candidate.properties?.h3_ref2va_attention_branch === "int8") expected = ref2vaActive && ref2vaBackend === "official8" && ref2vaAttention === "int8";
    if (candidate.properties?.h3_memory_opt_branch === true) expected = ref2vaActive && (ref2vaBackend === "pdd8" || ref2vaBackend === "official8") && memoryOptEnabled;
    if (candidate.properties?.h3_upload_chain === true) expected = uploadEnabled;
    if (candidate.properties?.h3_shared_video_loader === true) expected = uploadEnabled || (ref2vaActive && Boolean(references.video));
    // REF_VIDEO_HARD_OFF_20260906：期望校验感知"关"的形态（MUTE=2 / BYPASS=4）
    const offMode = candidate.properties?.h3_upload_chain === true || candidate.properties?.h3_shared_video_loader === true || (candidate.properties?.h3_reference_branch === "video" && candidate.properties?.h3_video_hard_link === true) ? 2 : 4;
    if (expected !== null && candidate.mode !== (expected ? 0 : offMode)) {
      problems.push(`节点 ${candidate.id} 的控制台状态与真实执行状态不一致`);
    }
  }
  return problems;
}

function syncVideoSource(node) {
  if (node?.properties?.h3_video_source_switch !== true) return;
  // 【none 门控】none 模式下视频源选择器不强制任何分支
  if (currentOperationKey() === "none") return;
  const widget = node.widgets?.find((candidate) => candidate.name === "value") || node.widgets?.[0];
  const uploadEnabled = booleanWidgetValue(widget);
  for (const candidate of node.graph?._nodes || app.graph?._nodes || []) {
    if (candidate.properties?.h3_video_source_branch !== "upload") continue;
    candidate.mode = uploadEnabled ? 0 : 4;
    paintOperationNode(candidate, uploadEnabled);
  }
  syncSharedVideoLoader(node);
  node.title = uploadEnabled
    ? "【修复视频来源】上传视频（仅检测/扩时/二采，不替代一采输出）"
    : "【修复视频来源】本次一采（仅检测/扩时/二采）";
  node.graph?.setDirtyCanvas(true, true);
  app.graph?.change?.();
}

function installBranchSelector(node) {
  if (!["H3SizeModeSelector", "H3GenerationModeSelector", "H3ImageModeSelector", "H3ReferenceSourceSelector", "H3SpeedModeSelector", "H3Fl2vRouteSelector", "H3Ref2vaBackendSelector", "H3Ref2vaAttentionSelector", "H3MemoryOptimizationSelector", "H3GuideModeSelector", "H3ContinuationSelector"].includes(node?.type) || node.__h3BranchSelectorReady) return;
  node.__h3BranchSelectorReady = true;
  for (const widget of node.widgets || []) {
    const originalCallback = widget.callback;
    widget.callback = function(value) {
      const result = originalCallback?.apply(this, arguments);
      setTimeout(() => syncAllBranchSelectors(node), 0);
      return result;
    };
  }
  setTimeout(() => syncAllBranchSelectors(node), 0);
}

function installVideoSourceSelector(node) {
  if (node?.properties?.h3_video_source_switch !== true || node.__h3VideoSourceReady) return;
  const widget = node.widgets?.find((candidate) => candidate.name === "value") || node.widgets?.[0];
  if (!widget) return;
  node.__h3VideoSourceReady = true;
  const originalCallback = widget.callback;
  widget.callback = function(value) {
    const result = originalCallback?.apply(this, arguments);
    setTimeout(() => syncVideoSource(node), 0);
    return result;
  };
  setTimeout(() => syncVideoSource(node), 0);
}

function hideUnusedOptionalInputs(node, optionalNames) {
  if (!isH3WorkflowNode(node) || !optionalNames?.size) return;
  for (const input of node.inputs || []) {
    if (optionalNames.has(input.name)) {
      input.hidden = input.link == null;
    }
  }
  node.graph?.setDirtyCanvas(true, true);
}

function isOutputPlayer(node) {
  return node?.type === "SaveVideo" && (
    PLAYER_TITLES.some((prefix) => node.title?.startsWith(prefix)) ||
    Boolean(node.properties?.h3_operation)
  );
}

function isUploadPlayer(node) {
  return node?.type === "LoadVideo" && node.title?.startsWith("【上传已有视频】");
}

function videoParams(filename) {
  const extension = String(filename).split(".").pop()?.toLowerCase() || "mp4";
  const mediaType = ["gif", "webp", "avif"].includes(extension) ? "image" : "video";
  return { filename, type: "input", format: `${mediaType}/${extension}` };
}

function refreshUploadPreview(node) {
  if (!isUploadPlayer(node)) return;
  const filename = node.widgets?.find((widget) => widget.name === "video")?.value;
  const preview = node.widgets?.find((widget) => widget.name === "videopreview");
  if (!filename || !preview) return;

  preview.value ||= { hidden: false, paused: true, params: {} };
  preview.value.hidden = false;
  preview.value.params ||= {};
  // Sanitize: VHS URLSearchParams serializes null as the literal "null", which
  // makes the backend /vhs/viewvideo crash with "could not convert string to
  // float: 'null'" (HTTP 500), leaving the <video> preview permanently empty.
  for (const key of Object.keys(preview.value.params)) {
    if (preview.value.params[key] == null) delete preview.value.params[key];
  }
  Object.assign(preview.value.params, videoParams(filename));
  if (preview.parentEl) preview.parentEl.hidden = false;
  preview.updateSource?.();
  node.graph?.setDirtyCanvas(true, true);
}

function installUploadPreview(node) {
  if (!isUploadPlayer(node)) return;
  const upload = node.widgets?.find((widget) => widget.name === "video");
  if (upload && !upload.__h3PreviewRefreshInstalled) {
    upload.__h3PreviewRefreshInstalled = true;
    const originalCallback = upload.callback;
    upload.callback = function(value) {
      const result = originalCallback?.apply(this, arguments);
      setTimeout(() => refreshUploadPreview(node), 0);
      return result;
    };
  }
  setTimeout(() => refreshUploadPreview(node), 0);
}

function enableNativeVideoPlayer(node) {
  if (!isOutputPlayer(node) && !isUploadPlayer(node)) return;
  node.flags ||= {};
  node.flags.pinned = false;
  const widget = node.widgets?.find((w) => w.name === "videopreview");
  const video = widget?.videoEl;
  if (!widget || !video || widget.__h3PlayerReady) return;
  widget.__h3PlayerReady = true;

  video.controls = true;
  video.loop = false;
  video.preload = "metadata";
  video.playsInline = true;
  video.disablePictureInPicture = false;
}

function mirrorGuideSource(node) {
  // H3GuideImageGuard: image_name 自动镜像上游图片源(如 LoadImageCrop)的真实已选文件，
  // 并把自身 combo 锁成单选项 —— 关键帧图片只有源节点一个选择位置。
  if (!node || node.type !== "H3GuideImageGuard") return;
  const imgWidget = node.widgets?.[0];
  if (!imgWidget) return;
  const graph = node.graph || window.app?.graph;
  const linkId = node.inputs?.[0]?.link;
  if (!graph || linkId == null) return;
  const link = graph.links?.[linkId];
  const src = link && graph.getNodeById ? graph.getNodeById(link.origin_id) : null;
  const srcWidget = src?.widgets?.[0];
  if (!src || !srcWidget || typeof srcWidget.value !== "string") return;

  const mirror = (guardNode, value) => {
    const w = guardNode.widgets?.[0];
    if (!w) return;
    // 空选择回落专用哨兵，而不是把 "" 写进 combo："" 不在服务端文件列表里，
    // 提交时会得到英文的 value_not_in_list 校验错；哨兵能让后端抛出中文提示。
    const v = typeof value === "string" && value.trim() ? value : SENTINEL_GUIDE_IMAGE;
    w.value = v;
    if (w.options) w.options.values = [v]; // 单选项锁定：只读镜像，非第二个选择器
    if (w.hidden === undefined) w.hidden = false;
  };
  mirror(node, srcWidget.value);

  if (!src.__h3GuideMirrorBound) {
    src.__h3GuideMirrorBound = true;
    const baseCallback = typeof srcWidget.callback === "function" ? srcWidget.callback : null;
    srcWidget.callback = function (value, canvas, srcNode) {
      if (baseCallback) { try { baseCallback(value, canvas, srcNode); } catch (e) { /* keep mirror alive */ } }
      const g = srcNode?.graph || window.app?.graph;
      if (g) for (const n of g.nodes || []) {
        if (n?.type === "H3GuideImageGuard" && n.inputs?.[0]?.link != null) {
          const l = g.links?.[n.inputs[0].link];
          if (l && l.origin_id === srcNode.id) mirror(n, value);
        }
      }
      return value;
    };
  }
}

function hideWidgetReadonly(w) {
  // mirrorReferenceState() 既有手法复用：type=hidden 不绘制、不可点击，
  // 值仍被 graphToPrompt 序列化（R03 / Q3 只读化）。
  if (!w || w.type === "hidden") return;
  w.type = "hidden";
  if (w.options && typeof w.options === "object") w.options.serialize = true;
}

// v024：h3_locked_value = { widget名: 锁定值 }，把对应 widget 钉死（只回写值，不做视觉隐藏）。
// 在每次 syncAllBranchSelectors 里强制执行，保证任何运行时篡改都会被拉回锁定值。
function enforceLockedValues(node) {
  const lockedValue = node?.properties?.h3_locked_value;
  if (!lockedValue || typeof lockedValue !== "object") return;
  for (const [name, value] of Object.entries(lockedValue)) {
    const w = widgetByName(node, name);
    if (!w) continue;
    if (w.value !== value) {
      w.value = value;
      try { w.callback?.(value); } catch (error) { console.error("[H3 v024] 锁定值回写失败", error); }
    }
  }
}

function lockControlledWidgets(node) {
  // R03：N766（h3_upload_chain_source）的 value widget 彻底内部化——只随 N150 第 5 项。
  if (node.properties?.h3_upload_chain_source === true) {
    const w = widgetByName(node, "value") || node.widgets?.[0];
    if (w) hideWidgetReadonly(w);
  }
  // Q3：带 h3_locked_widgets=true 的节点（N901/902/903）隐藏全部可编辑 widget。
  if (node.properties?.h3_locked_widgets === true) {
    for (const w of node.widgets || []) hideWidgetReadonly(w);
  }
  // v024：h3_locked_value = { widget名: 锁定值 }，把对应 widget 钉死 + 隐藏。
  // 例如 N873 一采模式钉死「默认（原样）」，防止滑到画质/高速档破坏 N861 直通尾。
  const lockedValue = node.properties?.h3_locked_value;
  if (lockedValue && typeof lockedValue === "object") {
    enforceLockedValues(node);
    for (const name of Object.keys(lockedValue)) {
      const w = widgetByName(node, name);
      if (w) hideWidgetReadonly(w);
    }
  }
}

// ===== v024 Phase D2：【生成过程预览】开关（N691 原生 mode 代理）=====
// 设计红线（作者 2026-09-10 Phase D2 任务书）：
// - 只代理 N691 原生 mode：开启=ACTIVE(0)，关闭=BYPASS(4)。不加新 Switch、不实现第二套 Preview 算法。
// - 真关闭定义：wrapper 不执行 / tiny-VAE 不解码 / 不发送 kj_preview_override / 无 Preview 采样开销。
// - 唯一持久化事实源 = N159.properties.h3_preview_enabled（properties 随工作流保存/加载）。
//   运行时新增 widget 不会被 configure 按索引回填，故 widget 值不参与序列化（serializeValue=undefined）。
// - 模式只在两处写 N691：①widget 回调（控制台按钮/下拉）②加载恢复（applyUx）。
//   500ms 轮询与 graphToPrompt 包装器一律不碰 N691 —— 手动 BYPASS 必须被尊重（MANUAL_BYPASS_RESPECTED）。
function applyPreviewState(node, enabled, fromLoad = false) {
  node.properties ||= {};
  node.properties.h3_preview_enabled = Boolean(enabled);
  // 用户/控制台显式操作（fromLoad=false）作废尚在途的加载恢复，杜绝"挂载后恢复覆盖用户开关"竞态。
  if (!fromLoad) node.__h3PreviewTouched = true;
  const previewNode = (node.graph?._nodes || app.graph?._nodes || []).find((n) => Number(n.id) === 691);
  if (previewNode) previewNode.mode = enabled ? 0 : 4;
  app.graph?.change?.();
}

function installPreviewSwitch(node) {
  if (node.__h3PreviewReady) return;
  if (node.type !== "H3OperationSelector" || Number(node.id) !== 159) return;
  // N691 尚未就绪时不落锁，等下一次 applyUx 重试（onConfigure/onConnectionsChange 都会再进）。
  const previewNode = (node.graph?._nodes || app.graph?._nodes || []).find((n) => Number(n.id) === 691);
  if (!previewNode || previewNode.type !== "ModelPreviewOverrideKJ") return;
  node.__h3PreviewReady = true;
  node.properties ||= {};
  // REGRESSION_RECOVERY_01（2026-09-29）：默认值语义反转 —— 只有显式 false 才关。
  // 旧逻辑 `=== true` 使字段缺失（从未保存过/外部 JSON 载入）时默认 bypass，
  // 用户每次打开图都必须手动重开预览（PREVIEW_DEFAULT_STATE_BUG，取证实证
  // FastH3_00008 嵌入图 N691 mode=4 + preview_prop=False）。
  // 现在：缺失/undefined → ON；显式 false → OFF。不碰预览质量/帧数/VAE/性能参数。
  const saved = node.properties.h3_preview_enabled !== false;
  const previewWidget = node.addWidget("combo", "生成过程预览", saved ? "开启" : "关闭", (value) => {
    applyPreviewState(node, value === "开启");
  }, { values: ["关闭", "开启"] });
  previewWidget.serializeValue = () => undefined;
  // 画布上隐藏（与「当前操作」同款处理）：控制台唯一 UI 是 dashboard 面板，避免撑高节点。
  previewWidget.draw = () => {};
  previewWidget.computeSize = () => [0, -4];
  // 加载恢复：默认开启（REGRESSION_RECOVERY_01 起；显式关闭才保持关闭）。
  // 仅在加载时写一次 mode，之后不再强制；若恢复落地前用户已显式切换
  // （__h3PreviewTouched），不得覆盖用户意图。
  setTimeout(() => { if (!node.__h3PreviewTouched) applyPreviewState(node, saved, true); }, 0);
}

// ===== STEP 7：官方【连拍推进】节点的 DOM 按钮中文化（纯显示层） =====
// 官方包用 addDOMWidget 注入英文按钮（Approve / Run-Re-roll / Chain / Reset /
// Clear latents）和一行英文状态。STEP 7 规定用户可见文案不得是英文主标题，
// 也规定 V27 的粘合层只能是 thin adapter —— 所以这里只改 textContent / title，
// 不 fork 官方包、不替换官方回调、不碰 clip_index 的任何推进逻辑。
// 幂等：映射表只认英文键，中文结果永远不再命中，MutationObserver 不会自激。
const CHAIN_NODE_TYPE = "MiniMaxH3MotionContextChain";
const CHAIN_ZH_BUTTONS = {
  "Approve": "采纳并接下一段",
  "Run/Re-roll": "重跑本段",
  "Chain": "自动连拍",
  "Stop": "停止连拍",
  "Reset": "回到第一段",
  "Clear latents": "清空段存档",
};
const CHAIN_ZH_TIPS = {
  "采纳并接下一段": "认可这一段，序号推进到下一段并开始生成。",
  "重跑本段": "按当前序号重新生成这一段（请用它代替 ComfyUI 的 Run 按钮）。",
  "自动连拍": "连续自动往下生成多段；【连拍段数】填 0 表示一直连拍直到点停止。",
  "停止连拍": "停止自动连拍，停在当前这一段。",
  "回到第一段": "序号复位为「读上一段＝无、本段＝第 1 段」；不提交生成、不删文件。",
  "清空段存档": "删除编号的段存档（clip_00001.safetensors 这类）；自定义命名的文件不动。",
};

function chainMetaZh(text) {
  let out = String(text ?? "");
  if (!out) return out;
  out = out.replace(/^Chaining\b/, "连拍中");
  out = out.replace(/Load\s*(\d+)\s*\/\s*Save\s*(\d+)/,
    "读取第$1段存档 ｜ 本段存为第$2段");
  out = out.replace(/·\s*(\d+)\s+left/, "｜ 还剩 $1 段");
  out = out.replace(/Load, Save, and Chain must share one canvas group\./,
    "请把「读上一段」「存档本段」「连拍推进」放进同一个画布分组。");
  out = out.replace(/Removed\s+(\d+)\s+numbered slots?\.\s*Custom names kept\./,
    "已清空 $1 个编号段存档（自定义命名的文件保留）。");
  out = out.replace(/No numbered chain slots to remove\./,
    "没有可清空的编号段存档。");
  return out;
}

function localizeChainRoot(root) {
  let touched = 0;
  for (const btn of root.querySelectorAll("button")) {
    const raw = (btn.textContent || "").trim();
    const zh = CHAIN_ZH_BUTTONS[raw];
    if (zh && raw !== zh) {
      btn.textContent = zh;
      touched += 1;
    }
    const tip = CHAIN_ZH_TIPS[(btn.textContent || "").trim()];
    if (tip && btn.title !== tip) {
      btn.title = tip;
      touched += 1;
    }
  }
  const meta = root.querySelector(".h3mc-chain-meta");
  if (meta) {
    const raw = meta.textContent || "";
    const zh = chainMetaZh(raw);
    if (zh !== raw) {
      meta.textContent = zh;
      touched += 1;
    }
  }
  return touched;
}

function localizeChainControls(node) {
  if (node?.type !== CHAIN_NODE_TYPE) return;
  const host = (node.widgets || []).find((w) => w.name === "h3mc_chain" || w.type === "CHAIN");
  const root = host?.element;
  if (!(root instanceof HTMLElement)) return;
  localizeChainRoot(root);
  if (node.__h3ChainZhInstalled) return;
  node.__h3ChainZhInstalled = true;
  // 官方 paint() 会在连拍状态切换时把 Chain 按钮改回 "Chain"/"Stop"，序号变化时
  // 重写状态行，所以必须观察而不是只在创建时翻译一次。
  new MutationObserver(() => localizeChainRoot(root)).observe(root, {
    childList: true, subtree: true, characterData: true,
  });
}

function applyUx(node, optionalNames) {
  translateNode(node);
  hideUnusedOptionalInputs(node, optionalNames);
  lockControlledWidgets(node);
  localizeChainControls(node);
  installUploadPreview(node);
  enableNativeVideoPlayer(node);
  installOperationSelector(node);
  installPreviewSwitch(node);
  installBranchSelector(node);
  installVideoSourceSelector(node);
  mirrorGuideSource(node);
  mirrorReferenceState(node);
  if (node.properties?.h3_dashboard_v3 === true) applyDashboard(node);
  if (node.properties?.h3_reference_branch === "images" && node.type === "LoadImageCrop" && !node.__h3ReferenceSlot) {
    node.__h3ReferenceSlot = true;
    const toggle = node.addWidget("toggle", "参与图片参考", node.properties.h3_reference_slot_enabled !== false, (value) => {
      node.properties.h3_reference_slot_enabled = Boolean(value);
      syncAllBranchSelectors(node);
    }, { serialize: false });
    toggle.serializeValue = () => undefined;
  }
}

// ===== v024 内部节点视觉隐藏（DEFERRED，作者 2026-09-10 紧急纠正）=====
// 【已废弃】曾用「Y+40000 relocation」方案被作者现场否决：即使幂等化，也会把工作流
// 坐标边界拉长数千像素，导致适应全图缩成极小、minimap 纵向空白严重异常。
// 作者红线：内部节点隐藏必须「节点坐标完全不改变」——不得改 pos / size / mode / group。
// 本轮退化方案：保持全部原始坐标，只把视口聚焦到 N159 主控制台（focusConsoleView，
// 纯视图操作，不触碰任何节点数据）。宁可暂时还能手动找到技术节点，绝不污染工作流坐标。
// h3_visual_hide 标记保留为惰性元数据，供未来无坐标突变的纯视觉方案使用。
function applyVisualHide() {
  // DEFERRED：不再对节点做任何坐标/尺寸/mode/group 变更。
}

// 把默认视口钉到 N159 主控制台，让内部区不进入用户默认视野。
function focusConsoleView(graph) {
  try {
    const nodes = graph?._nodes || app.graph?._nodes || [];
    const consoleNode = nodes.find((n) => n.properties?.h3_keep_visible === true || n.type === "H3OperationSelector");
    if (consoleNode && app.canvas?.centerOnNode) {
      setTimeout(() => app.canvas.centerOnNode(consoleNode), 30);
    }
  } catch (error) {
    console.error("[H3 v024] 视图定位失败", error);
  }
}

app.registerExtension({
  name: "H3.Workflow.ChinesePlayerUX",
  setup() {
    const original = app.graphToPrompt;
    app.graphToPrompt = async function (...args) {
      const graph = this.graph;
      const selector = graph?._nodes?.find((n) => n.type === "H3OperationSelector");
      if (selector) {
        if (selector.properties?.h3_registry_v1) {
          const result = applyFunction(selector, currentFunctionId(selector));
          if (!result.ok) throw new Error(result.message);
        } else {
          syncOperation(selector);
        }
        syncAllBranchSelectors(selector);
        repairPrimaryOutput(graph);
      }
      // 提交前再算一次接续开关：mode / context_length 必须在真正发出去的
      // prompt 里就是权威状态，不能依赖用户点击时事件回调是否恰好触发过
      // （loadGraphData、脚本改值都不会触发 onWidgetChange）。
      const continuation = graph?._nodes?.find((n) => n.type === "H3ContinuationSelector");
      if (continuation) syncContinuation(continuation);
      const result = await original.apply(this, args);
      // STEP 8：纯 UI 开关（零连线）不进执行图。放在最前面，让后续的
      // 参考图重排与主输出校验都基于同一份「真正会被提交」的 prompt。
      if (result?.output) result.output = stripUiOnlyNodes(graph, result.output);
      if (result?.output) {
        // 所有 H3 图（包括旧 workflow）提交前使用同一 Python 引用策略。
        // 编译后的 provenance 保持 Picture 对应的原素材槽；未赋职责的图排除。
        // 失败 → fail-closed：转中文错误并阻止提交，绝不带病生成。
        try {
          result.output = compactRefImageSlots(result.output, graph?.extra?.h3_six_segment_director?.enabled===true && graph?._nodes?.some(n=>n.properties?.h3_six_director===true));
        } catch (error) {
          console.error("[H3] 参考图自动重排失败", error);
          throw new Error(`参考图自动重排失败：${error?.message || error}。已阻止提交，请整理素材后再运行。`);
        }
      }
      if (selector) validatePrimaryOutput(graph, result.output);
      return result;
    };
  },
  afterConfigureGraph() {
    repairPrimaryOutput(app.graph);
    applyVisualHide(app.graph);
    focusConsoleView(app.graph);
  },
  beforeRegisterNodeDef(nodeType, nodeData) {
    const optionalNames = new Set(Object.keys(nodeData?.input?.optional || {}));
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = onCreated?.apply(this, arguments);
      setTimeout(() => applyUx(this, optionalNames), 0);
      return result;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function() {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => applyUx(this, optionalNames), 0);
      return result;
    };

    const onConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function() {
      const result = onConnectionsChange?.apply(this, arguments);
      setTimeout(() => applyUx(this, optionalNames), 0);
      return result;
    };
  },
});
