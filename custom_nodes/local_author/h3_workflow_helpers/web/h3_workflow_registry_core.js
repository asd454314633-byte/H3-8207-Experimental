/**
 * H3 P1 注册表核心（无 DOM / 无浏览器依赖）。
 *
 * 以原生 ES module 供 ComfyUI 浏览器控制器 h3_workflow_registry_v1.js 直接导入。
 * 生产运行路径不依赖 CommonJS、module.exports 或 Node.js require。
 *
 * 功能行为单一事实源：FUNCTION_REGISTRY（由图中 h3_operation 标签驱动）。
 * 功能轴只管理 h3_operation；647/886/645/884/885、h3_generation_branch 不由其管理。
 */

const SELECTOR_TYPE = "H3OperationSelector";
const REGISTRY_FLAG = "h3_registry_v1";

const EXCLUSIVE_COLOR = "#277a52";
const EXCLUSIVE_BG = "#123b2a";
const BYPASSED_COLOR = "#62408a";
const BYPASSED_BG = "#281a38";

/**
 * 单一 FUNCTION_REGISTRY —— 功能行为唯一事实源。
 * exclusiveTags 命中 h3_operation 标签；数组标签（如 expand+resample 共享链）
 * 表示两者任一命中即点亮。required_inputs 统一检查；allow_queue=false 表示不提交。
 */
const FUNCTION_REGISTRY = [
  {
    function_id: "primary_generate",
    name_zh: "一采生成",
    order: 1,
    h3_operation: "pass1",
    exclusiveTags: ["pass1"],
    required_inputs: [],
    allow_queue: true,
    action: "执行一采生成",
  },
  {
    function_id: "detect_only",
    name_zh: "只检测坏段",
    order: 2,
    h3_operation: "detect",
    exclusiveTags: ["detect"],
    required_inputs: ["参考视频"],
    allow_queue: true,
    action: "执行坏段检测",
  },
  {
    function_id: "expand_only",
    name_zh: "只放大扩时",
    order: 3,
    h3_operation: "expand",
    exclusiveTags: ["expand"],
    required_inputs: ["参考视频"],
    allow_queue: true,
    action: "执行放大扩时",
  },
  {
    function_id: "resample_only",
    name_zh: "只执行二采",
    order: 4,
    h3_operation: "resample",
    exclusiveTags: ["resample"],
    required_inputs: ["二采潜空间"],
    allow_queue: true,
    action: "执行二采修复",
  },
  {
    function_id: "auto_repair",
    name_zh: "自动检测修复",
    order: 5,
    h3_operation: "auto",
    exclusiveTags: ["auto"],
    required_inputs: ["参考视频"],
    allow_queue: true,
    action: "执行自动修复",
  },
  {
    function_id: "all_bypass",
    name_zh: "全部旁路",
    order: 6,
    h3_operation: "none",
    exclusiveTags: [],
    required_inputs: [],
    allow_queue: false,
    action: "切换为全部旁路",
  },
];

function registrySnapshot() {
  return FUNCTION_REGISTRY.slice();
}

function functionById(id) {
  return registrySnapshot().find((fn) => fn.function_id === id);
}

function normalizeOperationValue(value) {
  const text = String(value ?? "");
  const allowed = new Set([
    "只跑一采",
    "检测坏段",
    "放大/扩时",
    "执行二采",
    "自动检测+扩时+二采（实验）",
    "无任何选项状态",
  ]);
  return allowed.has(text) ? text : null;
}

function selectorNode(graph) {
  return (graph?._nodes || []).find((candidate) => candidate?.type === SELECTOR_TYPE);
}

function registryWidget(node) {
  return node?.widgets?.find((candidate) => candidate.name === "当前操作");
}

function currentFunctionId(node) {
  const widget = registryWidget(node);
  const value = normalizeOperationValue(widget?.value);
  switch (value) {
    case "只跑一采": return "primary_generate";
    case "检测坏段": return "detect_only";
    case "放大/扩时": return "expand_only";
    case "执行二采": return "resample_only";
    case "自动检测+扩时+二采（实验）": return "auto_repair";
    case "无任何选项状态": return "all_bypass";
    default: return null;
  }
}

function invalidFunctionResult(functionId) {
  const shown = functionId === null || functionId === undefined || functionId === ""
    ? "（空）"
    : String(functionId);
  return {
    ok: false,
    blocked: true,
    invalid_function_id: true,
    functionId,
    message: `注册表错误：未知或非法 FUNCTION_ID ${shown}，已阻止状态切换与任务提交。`,
  };
}

function nodeTagValue(node) {
  return node?.properties?.h3_operation;
}

function setMode(node, enabled) {
  node.mode = enabled ? 0 : 4;
  node.color = enabled ? EXCLUSIVE_COLOR : BYPASSED_COLOR;
  node.bgcolor = enabled ? EXCLUSIVE_BG : BYPASSED_BG;
}

// The primary output must never select the uploaded repair source. Migrate only
// the known LazySwitch wiring; unknown custom wiring is rejected at serialization.
function repairPrimaryOutput(graph) {
  const nodes = graph?._nodes || [];
  const sourceOf = (node, name) => {
    const input = node.inputs?.find((i) => i.name === name);
    const link = graph.links?.[input?.link];
    return link ? { node: graph.getNodeById(link.origin_id), slot: link.origin_slot } : null;
  };
  for (const output of nodes) {
    if (output.type !== "CreateVideo" || output.properties?.h3_operation !== "pass1") continue;
    for (const [name, switchType, falseInput, decoderType] of [
      ["images", "LazySwitch3", "on_false_value_1", "VAEDecode"],
      ["audio", "LazySwitch", "on_false", "VAEDecodeAudio"],
    ]) {
      const current = sourceOf(output, name);
      if (current?.node?.type !== switchType) continue;
      const decoded = sourceOf(current.node, falseInput);
      if (decoded?.node?.type !== decoderType) throw new Error("一采输出迁移失败：生成解码来源不明确。");
      const sampled = sourceOf(decoded.node, "samples");
      if (sampled?.node?.type !== "SamplerCustomAdvanced") throw new Error("一采输出迁移失败：缺少真实采样来源。");
      decoded.node.connect(decoded.slot, output, output.inputs.findIndex((i) => i.name === name));
    }
  }
}

function instantiatedGraphNodes(graph) {
  const nodes=[],seen=new Set();
  function visit(current){
    if(!current||seen.has(current))return;seen.add(current);
    for(const node of current._nodes||[]){nodes.push(node);if(node.subgraph)visit(node.subgraph)}
  }
  visit(graph);return nodes;
}

function validatePrimaryOutput(graph, prompt) {
  // V27【接续生产】：官方 MiniMaxH3MotionContextTrim 允许插在解码器与 CreateVideo
  // 之间。它只把片头保护区裁掉，不引入任何外部视频源，所以"禁止上传视频直出"
  // 这条闸门必须继续成立：遇到官方 Trim 就顺着它的同名输入再走一跳，仍然要求
  // 最终来源是 VAEDecode / VAEDecodeAudio ← SamplerCustomAdvanced。检查强度不降。
  const CONTINUATION_TRIM = "MiniMaxH3MotionContextTrim";
  let primaryActive = false;
  for (const output of graph?._nodes || []) {
    if (output.type !== "CreateVideo" || output.properties?.h3_operation !== "pass1" || output.mode !== 0) continue;
    const saved = prompt[String(output.id)];
    primaryActive = true;
    const decodeRoutes = [];
    for (const [name, type] of [["images", "VAEDecode"], ["audio", "VAEDecodeAudio"]]) {
      const ref = saved?.inputs?.[name];
      let decoded = Array.isArray(ref) && prompt[String(ref[0])];
      const nativeProvider = instantiatedGraphNodes(graph).find(n => n.type === 'H3ContinuationProvider');
      const nativeTrim = decoded?.class_type === 'H3ContinuationTrimOnce' && nativeProvider?.properties?.h3_continuation_provider === 'CORE_NATIVE_MASKED_AV';
      if (decoded?.class_type === CONTINUATION_TRIM || nativeTrim) {
        // 顺着官方 Trim 的同名输入再走一跳（images←VAEDecode / audio←VAEDecodeAudio）
        const through = decoded?.inputs?.[name];
        decoded = Array.isArray(through) ? prompt[String(through[0])] : null;
      }
      // AUDIO_UPGRADE_OUTPUT_CONTRACT_V1: candidate-gated provenance traversal.
      const audioUpgrade = graph.getNodeById?.(159)?.properties?.h3_audio_upgrade === true;
      let audioRoute = null;
      if (audioUpgrade && name === "audio" && decoded?.class_type === "H3AudioOutput") {
        audioRoute = decoded;
        const generated = decoded.inputs.generated_audio;
        decoded = Array.isArray(generated) ? prompt[String(generated[0])] : null;
      }
      let sampled = decoded?.inputs?.samples;
      let sampleNode = Array.isArray(sampled) ? prompt[String(sampled[0])] : null;
      // STAGED_RELEASE_OUTPUT_CONTRACT_V1: one explicit LATENT hop only.
      // Resolve provenance for validation; never rewrite the executable prompt.
      let unloadId = null;
      if (["H3SelectiveDiffusionUnloadBeforeVAE", "H3PartialDiffusionEvictBeforeVAE"].includes(sampleNode?.class_type)) {
        const upstream = sampleNode.inputs?.latent;
        const sampler = Array.isArray(upstream) ? prompt[String(upstream[0])] : null;
        if (sampled.length !== 2 || sampled[1] !== 0 || !Array.isArray(upstream) || upstream.length !== 2 || upstream[1] !== 0 || sampler?.class_type !== "SamplerCustomAdvanced") {
          throw new Error("一采输出检查失败：DiffusionUnload 必须且只能透传 Sampler 的最终 LATENT 输出。");
        }
        unloadId = String(sampled[0]);
        sampleNode = sampler;
      }
      decodeRoutes.push({ name, unloadId });
      let audioContract = false;
      if (audioUpgrade && sampleNode?.class_type === "H3AudioRefineGate") {
        const gate = sampleNode;
        const sameGate = !audioRoute || (Array.isArray(audioRoute.inputs.latent) && String(audioRoute.inputs.latent[0]) === String(sampled[0]));
        const cached = gate.inputs.mode === "仅精修已缓存一采（不重跑画面）";
        const storeRef = gate.inputs.latent;
        const store = Array.isArray(storeRef) ? prompt[String(storeRef[0])] : null;
        const sourceRef = store?.inputs?.latent;
        const source = Array.isArray(sourceRef) ? prompt[String(sourceRef[0])] : null;
        const validStore = store?.class_type === "H3AudioSampleStore" && source?.class_type === "SamplerCustomAdvanced";
        audioContract = sameGate && (validStore || (cached && typeof gate.inputs.cache_name === "string" && gate.inputs.cache_name.endsWith(".pt")));
      }
      if (decoded?.class_type !== type || !Array.isArray(sampled) || (sampleNode?.class_type !== "SamplerCustomAdvanced" && !audioContract)) {
        throw new Error(`一采输出检查失败：${name} 必须来自真实采样解码，禁止上传视频直出。请重新加载修正版工作流。`);
      }
    }
    if (decodeRoutes.some(route => route.unloadId !== null) && (decodeRoutes.some(route => route.unloadId === null) || new Set(decodeRoutes.map(route => route.unloadId)).size !== 1)) {
      throw new Error("一采输出检查失败：Video / Audio 解码必须共同依赖同一个 DiffusionUnload，禁止旁路。");
    }
  }
  if (!primaryActive) return;
  for (const [conditionId, condition] of Object.entries(prompt)) {
    if (condition.class_type !== "MiniMaxH3ReferenceToVideo") continue;
    const inputs = condition.inputs;
    const graphCondition = graph.getNodeById?.(Number(conditionId));
    const hiddenPrompt = graphCondition?.widgets?.find(w => w.name === "prompt")?.value;
    if (typeof hiddenPrompt === "string" && hiddenPrompt !== "") throw new Error("参考编码节点内部旧 Prompt 必须为空，提交已停止。请清空内部文本后重试。");
    if (!Array.isArray(inputs.prompt)) throw new Error("参考编码节点必须连接外部最终 Prompt，提交已停止。");
    const pictureSlots = Object.keys(inputs).filter((k) => k.startsWith("ref_images.ref_image_")).map((k) => Number(k.split("_").pop())).sort((a,b) => a-b);
    // 稀疏 UI 槽位在 validate 前已由 compactRefImageSlots 压缩为连续 H3 Picture 序号。
    if (pictureSlots.some((slot,index) => slot !== index)) throw new Error("参考图槽位压缩失败：提交已停止，禁止静默错配 Picture 序号。");
    if(graph?.extra?.h3_six_segment_director?.enabled===true && graph?._nodes?.some(n=>n.properties?.h3_six_director===true))continue;
    let role = Array.isArray(inputs.prompt) ? prompt[String(inputs.prompt[0])] : null;
    // Unwrap audio numbering so the existing Picture-label gate remains active.
    if (graph.getNodeById?.(159)?.properties?.h3_audio_upgrade === true && role?.class_type === "H3AudioReferencePack") {
      const through = role.inputs.prompt;
      role = Array.isArray(through) ? prompt[String(through[0])] : null;
    }
    const source = role?.class_type === "H3VideoPromptRole" ? role.inputs.base_prompt : inputs.prompt;
    const text = typeof source === "string" ? source : prompt[String(source?.[0])]?.inputs?.value;
    if (typeof text !== "string") continue;
    if (role?.class_type !== "H3VideoPromptRole" || role.inputs.picture_refs_enabled !== false) {
      for (const match of text.matchAll(/<\s*Picture\s*(\d+)\s*>/gi)) {
        if (Number(match[1]) < 1 || Number(match[1]) > pictureSlots.length) throw new Error(`提示词引用 ${match[0]}，但实际只连接了 ${pictureSlots.length} 张图片。请修正素材与标签。`);
      }
    }
  }
}

/**
 * 参考图槽位 → 新序号的 1 基映射（Q1/§7，幂等纯函数）。
 *
 * @param {number[]} slots 启用槽位（0 基、升序，如 [0,2,3]）
 * @returns {Object} old1based -> new1based（单调且 new≤old）
 */
function pictureOrdinalMap(slots) {
  const sorted = (slots || [])
    .map(Number)
    .filter((n) => Number.isInteger(n) && n >= 0)
    .sort((a, b) => a - b);
  const map = {};
  sorted.forEach((slotIndex, pos) => {
    map[slotIndex + 1] = pos + 1;
  });
  return map;
}

// §11.5 唯一权威正则：`/<(\s*)(Picture|Video|Audio)(\s+)(\d+)(\s*)>/gi`
// 只动 Picture 的编号；Video/Audio 引用不动（本轮不压缩视频/音频槽）。
const H3_MEDIA_REF_RE = /<(\s*)(Picture|Video|Audio)(\s+)(\d+)(\s*)>/gi;

/**
 * 定位提示词文本（graphToPrompt 输出结构）并返回读写句柄。
 * 支持：136.inputs.prompt 为裸字符串 / H3VideoPromptRole.base_prompt 链接到
 * PrimitiveString 源节点（inputs.value）。picture_refs_enabled=false 时跳过。
 */
function locatePromptText(prompt, cond) {
  const promptRef = cond?.inputs?.prompt;
  if (typeof promptRef === "string") {
    return { read: () => promptRef, write: (v) => { cond.inputs.prompt = v; } };
  }
  if (!Array.isArray(promptRef) || promptRef.length < 2) return null;
  const role = prompt[String(promptRef[0])];
  if (!role) return null;
  if (role.class_type !== "H3VideoPromptRole") {
    if (["PrimitiveString", "PrimitiveStringMultiline"].includes(role.class_type)
        && typeof role.inputs?.value === "string") {
      return { read: () => role.inputs.value, write: (v) => { role.inputs.value = v; } };
    }
    return null;
  }
  // 对齐 registry_core validatePrimaryOutput:204：picture_refs_enabled=false 表示后端已删图片行 → 跳过
  if (role.inputs?.picture_refs_enabled === false) return null;
  const bp = role.inputs?.base_prompt;
  if (typeof bp === "string") {
    return { read: () => bp, write: (v) => { role.inputs.base_prompt = v; } };
  }
  if (Array.isArray(bp) && bp.length >= 2) {
    const src = prompt[String(bp[0])];
    if (src?.inputs && typeof src.inputs.value === "string") {
      return { read: () => src.inputs.value, write: (v) => { src.inputs.value = v; } };
    }
    if (src?.inputs) {
      return {
        read: () => (typeof src.inputs.value === "string" ? src.inputs.value : ""),
        write: (v) => { src.inputs.value = v; },
      };
    }
  }
  return null;
}

/**
 * Compact image sockets in source-slot order. Picture tags are canonical H3
 * ordinals and are validated but never rewritten. UI slot references belong
 * to the Director's single mapping stage. Idempotent, no semantic mutation.
 */
function compactRefImageSlots(prompt, allowLiteralReferences=false) {
  if (!prompt || typeof prompt !== "object") return prompt;
  for (const nodeId of Object.keys(prompt)) {
    const cond = prompt[nodeId];
    if (!cond || cond.class_type !== "MiniMaxH3ReferenceToVideo" || !cond.inputs) continue;
    const inputs = cond.inputs;
    // 对齐 registry_core validatePrimaryOutput:204：H3VideoPromptRole 且 picture_refs_enabled=false
    // 表示后端已删图片行 → 整节点跳过（不压缩槽位、不改写文本）。
    const roleRef = inputs.prompt;
    if (Array.isArray(roleRef) && roleRef.length >= 2) {
      const roleNode = prompt[String(roleRef[0])];
      if (roleNode && roleNode.class_type === "H3VideoPromptRole" && roleNode.inputs?.picture_refs_enabled === false) continue;
    }
    const slotKeys = Object.keys(inputs)
      .filter((k) => /^ref_images\.ref_image_\d+$/.test(k));
    if (slotKeys.length === 0) continue; // 无启用参考图 → 交 validate 处理（picture_refs_enabled=false 时跳过）
    const slots = slotKeys
      .map((k) => Number(k.split("_").pop()))
      .sort((a, b) => a - b);
    // <Picture N> is already the H3 ordinal, never a UI-slot number.
    // The Director maps Chinese 图N once. Do not remap canonical tags here.
    const loc = locatePromptText(prompt, cond);
    const text = loc?.read();
    if (!allowLiteralReferences && typeof text === "string") {
      for (const match of text.matchAll(H3_MEDIA_REF_RE)) {
        if (match[2].toLowerCase() !== "picture") continue;
        const num = Number(match[4]);
        if (num < 1 || num > slots.length) {
          throw new Error(`提示词引用 <Picture ${num}>，但实际只有 ${slots.length} 张有效参考图。Picture 编号按有效图片顺序从 1 连续排列；UI 的“图N”请先交由导演映射。`);
        }
      }
    }
    if (slots.every((slot, index) => slot === index)) continue;
    const values = slots.map((slot) => inputs["ref_images.ref_image_" + slot]);
    for (const key of slotKeys) delete inputs[key];
    values.forEach((value, index) => { inputs["ref_images.ref_image_" + index] = value; });
  }
  return prompt;
}

/**
 * 统一 applyFunction。
 * 职责：读注册表 → 当前功能独占节点 mode=0 → 其他独占 mode=4 → Shared 不误伤。
 */
function applyFunction(node, functionId) {
  const definition = functionById(functionId);
  if (!definition) return invalidFunctionResult(functionId);
  const exclusiveTags = definition.exclusiveTags;
  const nodes = node.graph?._nodes || [];
  for (const candidate of nodes) {
    const tagged = nodeTagValue(candidate);
    if (functionId === "all_bypass" && Object.keys(candidate.properties || {}).some((k) => k.startsWith("h3_") && (k.endsWith("_branch") || k === "h3_shared_video_loader"))) {
      setMode(candidate, false);
    }
    if (!tagged) continue;
    if (candidate.properties?.h3_force_bypass === true) {
      setMode(candidate, false);
      continue;
    }
    const enabled = exclusiveTags.length === 0
      ? false
      : Array.isArray(tagged)
        ? tagged.some((t) => exclusiveTags.includes(t))
        : exclusiveTags.includes(tagged);
    setMode(candidate, enabled);
  }
  return { ok: true, functionId, definition };
}

function selectFunction(node, functionId) {
  const definition = functionById(functionId);
  if (!definition) return invalidFunctionResult(functionId);
  const mapping = {
    primary_generate: "只跑一采",
    detect_only: "检测坏段",
    expand_only: "放大/扩时",
    resample_only: "执行二采",
    auto_repair: "自动检测+扩时+二采（实验）",
    all_bypass: "无任何选项状态",
  };
  const widget = registryWidget(node);
  const value = mapping[functionId];
  if (widget && value) {
    widget.value = value;
    if (typeof widget.callback === "function") widget.callback(value);
  }
  return applyFunction(node, functionId);
}

function widgetBool(widget) {
  return widget?.value === true || widget?.value === 1 || widget?.value === "true";
}

/**
 * required_inputs 统一检查（真实工作流状态）。
 * - 修复素材：检查实际选中的来源，节点存在不等于已有素材。
 * - 二采潜空间：放大扩时链已点亮（expand 标签节点 mode=0）→ 就绪。
 */
function requiredInputsSatisfied(node, definition) {
  if (!definition) return invalidFunctionResult(null);
  if (!definition.required_inputs.length) return { ok: true, missing: [] };
  const nodes = node.graph?._nodes || [];
  const missing = [];
  for (const input of definition.required_inputs) {
    let satisfied = false;
    if (input.includes("参考视频")) {
      // UPLOAD_CHAIN_MASTER_20260906：上传开关唯一事实源 = N150 第 5 项
      // 「后处理使用上传视频」（766 已降级为内部选择器，不再承载用户开关）。
      const refsNode = nodes.find((n) => n.type === "H3ReferenceSourceSelector");
      const uploaded = widgetBool(refsNode?.widgets?.find((w) => w.name === "后处理使用上传视频"));
      if (uploaded) {
        satisfied = nodes.some((n) => n.properties?.h3_shared_video_loader === true &&
          Boolean(String(n.widgets?.find((w) => w.name === "video")?.value || "").trim()));
      } else {
        satisfied = nodes.some((n) => n.type === "VAEDecode" && n.inputs?.some((i) => i.name === "samples" && i.link != null));
      }
    } else if (input.includes("二采潜空间")) {
      satisfied = nodes.some((candidate) => {
        const tagged = candidate.properties?.h3_operation;
        if (!tagged) return false;
        const tags = Array.isArray(tagged) ? tagged : [tagged];
        return tags.includes("expand") && candidate.mode === 0;
      });
    } else {
      satisfied = false;
    }
    if (!satisfied) missing.push(input);
  }
  return { ok: missing.length === 0, missing };
}

/**
 * 统一 queueSelectedFunction。
 * SELECT 与 QUEUE 分离：只在此处提交任务。
 * 缺素材 → 中文报错并阻止 Queue（不调用 queueCallback）。
 * 正常 → 只 Queue 当前已选择功能。
 *
 * @param {{queueCallback:Function}} rt 运行时注入，测试时可替换以捕获/阻止 Queue。
 */
async function queueSelectedFunction(node, functionId, rt) {
  const definition = functionById(functionId);
  if (!definition) return invalidFunctionResult(functionId);

  if (definition.allow_queue === false) {
    return { ok: true, skipped: true, message: "当前状态：全部功能已紫色旁路，不会提交任务。" };
  }

  if (!rt || typeof rt.queueCallback !== "function") {
    return {
      ok: false,
      blocked: true,
      invalid_queue_runtime: true,
      message: "提交失败：Queue 运行时不可用，已阻止任务提交。",
    };
  }

  const check = requiredInputsSatisfied(node, definition);
  if (!check.ok) {
    const message = `提交失败：缺少必需素材 ${check.missing.join("、")}。请先补充后再执行 ${definition.name_zh}。`;
    return { ok: false, blocked: true, message };
  }

  if (currentFunctionId(node) !== functionId) {
    return { ok: false, blocked: true, message: "提交失败：当前功能已改变，请重新选择要执行的功能。" };
  }
  try {
    await rt.queueCallback(node, functionId, definition);
  } catch (error) {
    return { ok: false, blocked: true, message: `提交失败：${error?.message || error}` };
  }
  return { ok: true, message: `已提交：${definition.name_zh}` };
}

export {
  SELECTOR_TYPE,
  REGISTRY_FLAG,
  FUNCTION_REGISTRY,
  registrySnapshot,
  functionById,
  normalizeOperationValue,
  selectorNode,
  registryWidget,
  currentFunctionId,
  applyFunction,
  selectFunction,
  requiredInputsSatisfied,
  queueSelectedFunction,
  setMode,
  repairPrimaryOutput,
  validatePrimaryOutput,
  pictureOrdinalMap,
  compactRefImageSlots,
};
