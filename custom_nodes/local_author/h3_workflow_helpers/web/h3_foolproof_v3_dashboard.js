import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import {
  H3_GEN_REF, H3_GEN_FL,
  H3_BACKEND_ORIGINAL, H3_BACKEND_VSA, H3_BACKEND_OFFICIAL,
  H3_BACKEND_STABLE8, H3_BACKEND_PDD8, H3_BACKEND_NATIVE20,
  H3_ATTENTION_INT8,
  H3_PREVIEW_ON, H3_PREVIEW_OFF, H3_PREVIEW_WIDGET,
  H3_IMAGE_T2V, H3_IMAGE_I2V, H3_IMAGE_FLF,
  H3_BACKEND_LABEL, H3_IMAGE_LABEL,
  H3_RECOMMENDED_STEPS, H3_STEP_TARGETS,
  H3_RATIO_ZH, H3_SEED_CONTROL_ZH,
  consoleModeKey, readFrameCount,
} from "./h3_console_state.js";

/* __H3_DIRECTOR_RULES_PURE_START__
 * V25_DETERMINISTIC_DIRECTOR_RULE_LAYER (Phase 1)
 * 来源：h3-director-simple V1.1.1 精确源（ZIP SHA256 62655c31…，Gate PASS）。
 * 范围：仅确定性规则（格式编译 + 校验 + 缺项提示）。语义导演层未实现（Phase 2 待授权）。
 * 边界：纯函数，无 DOM / 无 app / 无 import；不改模式、参数、素材；不调用 Queue。
 * 权威顺序：当前已验证本地工作流行为 > 官方 H3 prompt 格式 > 本规则 > 第三方惯例。
 */
const H3_DR_EMOTION_LEXICON = [
  "开心", "高兴", "快乐", "失落", "伤心", "难过", "悲伤", "沮丧", "失望", "生气",
  "愤怒", "害怕", "恐惧", "紧张", "焦虑", "兴奋", "激动", "放松", "平静", "惊讶",
  "吃惊", "羞愧", "尴尬", "骄傲", "嫉妒", "委屈", "满足", "幸福", "痛苦", "绝望",
  "怀念", "感动", "欣慰", "心酸", "彷徨", "无助", "释然",
];

function h3DrDetectAbstractEmotion(text) {
  const source = String(text || "");
  const hits = H3_DR_EMOTION_LEXICON.filter((word) => source.includes(word));
  return { hit: hits.length > 0, words: hits };
}

function h3DrRound2(v) {
  return (Math.round(Number(v) * 100) / 100).toFixed(2);
}

// 官方 alignment line 构造（h3-official-format.md A2/A3）。仅按已验证事实构造，不改用户文字。
function h3DrBuildAlignmentLine(subMode, durationSeconds, lastShotIndex) {
  const n = Number(lastShotIndex) || 1;
  if (subMode === "I2VA") {
    return "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.";
  }
  if (subMode === "FLF") {
    return "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot "
      + n + ") aligns with the " + h3DrRound2(durationSeconds) + "-second mark of the target video.";
  }
  return null; // T2VA：无 alignment 行（官方 A1）
}

function h3DrAlignmentFirstLine(text) {
  return String(text || "").trimStart().split(/\r?\n/, 1)[0].trim();
}

function h3DrParseShotTimes(text) {
  const out = [];
  const re = /\[Shot\s+(\d+)\]\s*(?:At\s+(\d{1,2}):(\d{2})\.(\d{3}))?/gi;
  let m;
  while ((m = re.exec(String(text || "")))) {
    out.push({
      index: Number(m[1]),
      seconds: m[2] != null ? Number(m[2]) * 60 + Number(m[3]) + Number(m[4]) / 1000 : null,
    });
  }
  return out;
}

const H3_DR_REF2VA_SECTIONS = [
  "subject_definitions", "summary", "retention_analysis",
  "detailed_description", "overall_soundscape", "non_diegetic_music",
];

function h3DrExtractSection(text, sectionName) {
  const re = new RegExp("(?:^|\\n)\\s*" + sectionName + "\\s*:\\s*\\n?([\\s\\S]*?)(?=\\n\\s*[A-Za-z_][A-Za-z_0-9]*\\s*:|$)");
  const m = String(text || "").match(re);
  return m ? m[1] : null;
}

function h3DrRef2vaSectionState(text) {
  const source = String(text || "");
  const found = H3_DR_REF2VA_SECTIONS
    .map((name, order) => ({ name, order, at: source.search(new RegExp("(?:^|\\n)\\s*" + name + "\\s*:")) }))
    .filter((s) => s.at >= 0);
  const ordered = found.every((s, i) => i === 0 || found[i - 1].at < s.at);
  return { count: found.length, ordered, found };
}

const H3_DR_RETENTION_VISUAL = ["fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"];
const H3_DR_RETENTION_AUDIO = ["fully_copy", "partially_copy", "reference", "weak_reference"];
const H3_DR_SUMMARY_PREFIXES = [
  "keyframe completion", "reference generation", "video editing",
  "video continuation", "audio reuse", "audio reference",
];

function h3DrSentenceCount(s) {
  const m = String(s || "").match(/[^.!?。！？]+[.!?。！？]*/g);
  return (m || []).map((x) => x.trim()).filter(Boolean).length;
}

function h3DrHasCJK(s) {
  return /[\u4e00-\u9fff\u3400-\u4dbf]/.test(String(s || ""));
}

// 通用确定性校验（两家族共用）：Shot 时间 / Speaker / 对白 / 标签 / 占位符 / 字段句数
function h3DrRunCommonChecks(input, warnings) {
  const text = String(input.text || "");
  const dur = Number(input.durationSeconds);

  // Shot 时间格式（官方 A5）
  const shots = h3DrParseShotTimes(text);
  if (shots.length) {
    if (shots[0].index !== 1) warnings.push("Shot 编号应从 [Shot 1] 开始且连续。");
    let prev = null;
    for (const s of shots) {
      if (s.index > 1 && s.seconds == null) {
        warnings.push("[Shot " + s.index + "] 是后续切镜，必须使用官方时间戳格式 [Shot N] At MM:SS.mmm。");
      }
      if (s.index === 1 && s.seconds != null) {
        warnings.push("[Shot 1] 不应带时间戳（官方规则 A5）。");
      }
      if (s.seconds != null) {
        if (prev != null && s.seconds <= prev) {
          warnings.push("后续切镜时间必须严格递增（[Shot " + s.index + "] 违反）。");
        }
        if (dur > 0 && s.seconds > dur) {
          warnings.push("[Shot " + s.index + "] 时间戳超出视频时长（" + h3DrRound2(dur) + "s）。");
        }
        prev = s.seconds;
      }
    }
    const indexes = shots.map((s) => s.index);
    for (let i = 0; i < indexes.length; i++) {
      if (indexes[i] !== i + 1) { warnings.push("Shot 编号必须连续（检测到缺口）。"); break; }
    }
  }

  // Speaker ID / 对白（官方 A7）
  const dialogueTags = [...text.matchAll(/<d\s*>([\s\S]*?)<\/d\s*>/g)];
  for (const tag of dialogueTags) {
    const body = tag[1];
    const lang = body.match(/^\s*\[([^\]]*)\]/);
    if (!lang) {
      warnings.push("对白标签缺少 [Language] 标记：官方格式为 <d>[Language] 原文</d>。");
      continue;
    }
    const token = lang[1].toLowerCase();
    const content = body.slice(lang[0].length);
    const hasCJK = h3DrHasCJK(content);
    if ((token.includes("chinese") || token.includes("中文") || token === "zh" || token === "cn") && !hasCJK) {
      warnings.push("对白标记为中文但内容不含中文字符，请核对是否被翻译。");
    }
    if ((token.includes("english") || token === "en") && hasCJK) {
      warnings.push("对白标记为英文但内容含中文，请核对。");
    }
  }
  const speakers = [...text.matchAll(/\(S(\d+)\)/g)].map((m) => Number(m[1]));
  if (speakers.length && dialogueTags.length === 0) {
    warnings.push("检测到 Speaker ID (Sx)，但未发现任何 <d>…</d> 对白标签。");
  }

  // 标签 vs 已提供素材（官方 B1：不得引用未提供的资产）
  const refLabels = (tag) => [...text.matchAll(new RegExp("<" + tag + "\\s*(\\d+)\\s*>", "g"))].map((m) => Number(m[1]));
  const refs = input.refs || {};
  const pics = refLabels("Picture");
  const maxPic = pics.length ? Math.max(...pics) : 0;
  if (maxPic > 0 && (refs.pictures || 0) < maxPic) {
    warnings.push("提示词引用 <Picture " + maxPic + ">，但当前仅提供 " + (refs.pictures || 0) + " 张图片素材。");
  }
  const maxVid = Math.max(0, ...refLabels("Video"));
  if (maxVid > 0 && (refs.videos || 0) < maxVid) {
    warnings.push("提示词引用 <Video " + maxVid + ">，但当前未提供对应的参考视频素材。");
  }
  const auds = refLabels("Audio");
  const maxAud = auds.length ? Math.max(...auds) : 0;
  if (maxAud > 0 && (refs.audios || 0) < maxAud) {
    warnings.push("检测到 <Audio " + maxAud + "> 引用，但当前未启用任何音频素材：普通参考视频的音轨不得自动虚构成 <Audio N>（官方 B1）。");
  }

  // 占位符残留
  if (/\{\{|\}\}|\bTODO\b|FIXME|待填|XXX|<Subject\s*\?>/i.test(text)) {
    warnings.push("提示词存在未解决的占位符，官方要求提交前不得残留。");
  }

  // 声音字段句数（官方 A9/A10）
  const soundFields = [["overall_soundscape", 1, 4, "仅在用户明确要求全片静音时才可使用 N/A"], ["non_diegetic_music", 1, 3, "无背景配乐时使用 N/A"]];
  for (const [name, min, max, naRule] of soundFields) {
    const value = h3DrExtractSection(text, name) ?? (text.match(new RegExp("(?:^|\\n)\\s*" + name + "\\s*:\\s*([^\\n]*)")) || [])[1];
    if (value == null) continue;
    const v = value.trim();
    if (!v) continue;
    if (v === "N/A") {
      warnings.push(name + " 当前为 N/A：" + naRule + "，请确认。");
    } else {
      const sc = h3DrSentenceCount(v);
      if (sc < min || sc > max) {
        warnings.push(name + " 官方建议 " + min + "–" + max + " 个英文句子，当前约 " + sc + " 句。");
      }
    }
  }
}

// Ref2VA 六段结构校验（官方 B 节，全部为格式级确定性检查）
function h3DrRunRef2vaChecks(input, warnings, notes) {
  const text = String(input.text || "");
  const retention = h3DrExtractSection(text, "retention_analysis");
  if (retention != null) {
    const lines = [...retention.matchAll(/<([^>\d]+)\s*(\d+)>\s*:\s*([A-Za-z_]+)/g)];
    for (const line of lines) {
      const tag = line[1].trim();
      const marker = line[3].trim();
      const allowed = tag === "Audio" ? H3_DR_RETENTION_AUDIO : H3_DR_RETENTION_VISUAL;
      if (!allowed.includes(marker)) {
        warnings.push("retention_analysis 中 <" + tag + " " + line[2] + "> 使用了非法关系标记「" + marker + "」。合法集合：视觉 " + H3_DR_RETENTION_VISUAL.join("/") + "；音频 " + H3_DR_RETENTION_AUDIO.join("/") + "。");
      }
    }
    if (/\(S\d+\)/.test(retention)) {
      warnings.push("retention_analysis 中出现了 Speaker ID (Sx)：官方规定 Speaker ID 不得进入 retention_analysis。");
    }
  }
  const summary = h3DrExtractSection(text, "summary");
  if (summary != null && summary.trim()) {
    const hasPrefix = H3_DR_SUMMARY_PREFIXES.some((p) => summary.toLowerCase().includes(p));
    if (!hasPrefix) {
      warnings.push("summary 未包含官方任务类型前缀（" + H3_DR_SUMMARY_PREFIXES.join(" / ") + " 之一）。前缀选择属语义判断，本地层仅提示。");
    } else if (/video editing/i.test(summary) && !/The target video is an edited version of\s*<Video\s*\d+>\./i.test(summary)) {
      warnings.push("summary 前缀含 video editing 时，必须紧跟「The target video is an edited version of <Video N>.」开场句（仅限 video editing）。");
    }
  }
  const detailed = h3DrExtractSection(text, "detailed_description");
  if (detailed != null && detailed.trim() && summary != null && !/video editing/i.test(summary || "")) {
    const words = detailed.trim().split(/\s+/).length;
    if (words > 0 && (words < 350 || words > 500)) {
      notes.push("detailed_description 约 " + words + " 词（官方普通生成任务建议 350–500 词，仅供参考，不强制）。");
    }
  }
}

// 主编译入口：模式 → 目标格式；绝不改写用户原意，只补官方骨架 + 校验 + 提示
function h3DrCompile(input) {
  const warnings = [];
  const notes = [];
  const text = String(input.text || "");
  let draft = text;
  let changed = false;
  const isRef2vaFamily = input.modeKey === "original" || input.modeKey === "vsa" || input.modeKey === "official";

  // CASE A 语义红线：检测到抽象情绪 → 明确提示，绝不发明表演细节
  const emo = h3DrDetectAbstractEmotion(text);
  if (emo.hit) {
    warnings.push("检测到抽象情绪变化（关键词：" + emo.words.join("、") + "）。当前本地规则层不会擅自添加具体表演动作。可保留原描述，或由用户补充具体动作；完整语义整理将在后续可选语义层处理。");
  }

  if (isRef2vaFamily) {
    // Ref2VA：六段结构改写属语义任务 → 只校验，不重组（保留用户原文）
    const sec = h3DrRef2vaSectionState(text);
    if (sec.count === 0) {
      notes.push("当前为 Ref2VA 系（" + input.modeKey + "）。六段结构补全需要语义理解，本地确定性层不代写；已保留原文，仅做格式校验。");
    } else if (sec.count < 6 || !sec.ordered) {
      warnings.push("Ref2VA 六段结构不完整或顺序错误。官方顺序：" + H3_DR_REF2VA_SECTIONS.join(" → ") + "。");
    }
    h3DrRunRef2vaChecks(input, warnings, notes);
  } else {
    const sub = input.imageMode || "T2VA";
    const FIELD_RE = /^[A-Za-z_][A-Za-z_0-9]*\s*:/;
    const firstContent = String(text).split(/\r?\n/).map((l) => l.trim()).find((l) => l && !FIELD_RE.test(l)) || "";
    const hasFields = /integrated_multimodal_description\s*:/.test(text);
    const shots = h3DrParseShotTimes(text);
    const lastShot = shots.length ? Math.max(...shots.map((s) => s.index)) : 1;
    const expected = h3DrBuildAlignmentLine(sub, input.durationSeconds, lastShot);
    if (sub === "T2VA") {
      if (/For the target video, at 0\.00 seconds|How the reference pictures align/i.test(text)) {
        warnings.push("T2VA 不应包含图像 alignment 行（官方 A1）。");
      }
    } else {
      const alignOk = sub === "I2VA"
        ? /^For the target video, at 0\.00 seconds into the target video, <Picture 1>/i.test(firstContent)
        : /^How the reference pictures align with the target video/i.test(firstContent);
      let head = "";
      let body = text;
      if (!alignOk) {
        head = expected;
        changed = true;
        notes.push("已按官方格式补上 " + sub + " alignment 行（其后保留原文）。");
      } else {
        head = firstContent;
        if (sub === "FLF" && head !== expected) {
          warnings.push("检测到已有 FL2VA alignment 行，但与官方模式（Picture 2 对齐 " + h3DrRound2(input.durationSeconds) + "-second，两位小数）不完全一致；本地层不覆盖用户文字，请人工核对。");
        }
        const idx = text.indexOf(firstContent);
        body = text.slice(idx + firstContent.length).replace(/^[ \t]*(\r?\n)+/, "");
      }
      if (!hasFields) {
        // 官方顺序：alignment 行 → 空行 → 三字段（用户文字逐字保留在 integrated 字段内）
        const wrapped = "integrated_multimodal_description:\n" + body + "\n\noverall_soundscape: N/A\n\nnon_diegetic_music: N/A";
        draft = head ? head + "\n\n" + wrapped : wrapped;
        changed = true;
        warnings.push("已按官方三字段结构补齐骨架；overall_soundscape / non_diegetic_music 默认草稿为 N/A——官方仅允许在明确全片静音/无配乐时使用 N/A，请在应用前确认或自行改写这两字段（本地层不代写环境声/配乐描述）。");
      } else if (head && head !== firstContent) {
        // 仅缺 alignment：补在最前，其余原样保留
        draft = head + "\n\n" + text;
      }
      if (sub === "FLF") {
        const bodyText = alignOk ? body : text; // 终点检查只看用户内容，不含本地补的 alignment 行
        if (!/(Picture 2|尾帧|最后|最终|last frame|ends on|ending in|landing|下场|finally|eventually|settles|comes to rest|stops and holds|holds the final|remains in the|at the end)/i.test(bodyText)) {
          warnings.push("FL2VA 需要明确终点结构（最终落在 Picture 2 / 尾帧状态）。本地层只提示，不代写终点内容。");
        }
        if ((input.refs?.pictures || 0) < 2) {
          warnings.push("FL2VA 需要首帧与尾帧两张图片素材，当前仅检测到 " + (input.refs?.pictures || 0) + " 张。");
        }
      }
    }
    // T2VA 缺三字段骨架时同样补齐（无 alignment 行）
    if (sub === "T2VA" && !hasFields) {
      draft = "integrated_multimodal_description:\n" + text + "\n\noverall_soundscape: N/A\n\nnon_diegetic_music: N/A";
      changed = true;
      warnings.push("已按官方三字段结构补齐骨架；overall_soundscape / non_diegetic_music 默认草稿为 N/A——官方仅允许在明确全片静音/无配乐时使用 N/A，请在应用前确认或自行改写这两字段（本地层不代写环境声/配乐描述）。");
    }
  }

  h3DrRunCommonChecks(input, warnings);
  return { changed, draft, notes, warnings };
}
/* __H3_DIRECTOR_RULES_PURE_END__ */

/**
 * H3 v024 单控制台 Dashboard。
 *
 * 隔离门：仅当 H3OperationSelector.properties.h3_dashboard_v3 === true 时生效。
 * 所有 DOM 控件均为现有节点 widget 的即时投影；不保存第二套业务状态。
 * v024：①生成方式分块 ②素材 ③视频参考 ④提示词 ⑤生成设置 ⑥一采/二采 ⑦随机种子 ▶开始生成。
 */

const GATE = "h3_dashboard_v3";
const NODE_IDS = {
  dashboard: 159,
  references: 150,
  generation: 647,
  imageMode: 761,
  video: 638,
  promptRef: 138,
  promptFl: 914,
  quality: 873,
  resolution: 115,
  duration: 132,
  frameExpr: 131,
  seed: 142,
  pass2: 867,
  route: 886,
  ref2vaBackend: 931,
  ref2vaAttention: 952,
  videoRole: 915,
  uploadSource: 766,
};
const REF_IMAGES_V281 = [687, 688, 689, 690];
const REF_IMAGES_V282 = [687, 688, 689, 690, 1001, 1002, 1003, 1004, 1005];
const FL_IMAGES = [874, 875];
const AUDIOS = [143, 685];
// STEP 34：时间轴关键帧轴（与生成方式正交；默认「不使用」＝整链紫色旁路＝直通）。
// 刻意不并入 NODE_IDS：旧工作流缺这些节点时，控制台仍必须完整安装。
const GUIDE_MODES = ["不使用关键帧", "1 个关键帧画面", "2 个关键帧画面", "3 个关键帧画面"];
const GUIDE_SELECTOR = 991;
const GUIDE_SLOTS = [
  { crop: 983, guard: 984, addGuide: 965 },
  { crop: 985, guard: 986, addGuide: 987 },
  { crop: 988, guard: 989, addGuide: 990 },
];
const INTERNAL_IDS = new Set([
  115, 132, 138, 143, 150, 638, 647, 685,
  ...REF_IMAGES_V282, ...FL_IMAGES, 761, 766, 873, 886, 900, 901, 902, 903, 914, 915, 931,
]);

function nodes(node) {
  return node?.graph?._nodes || app.graph?._nodes || [];
}

function byId(node, id) {
  return nodes(node).find((candidate) => Number(candidate.id) === id);
}

function widget(node, name, fallbackIndex = 0) {
  return node?.widgets?.find((candidate) => candidate.name === name) || node?.widgets?.[fallbackIndex];
}

function setWidget(target, value) {
  if (!target) return;
  // V26_SEEDNODE_NAN_REPAIR_01：数值控件只接受有限数字。
  // 任何"按名字找不到控件 → 回落到 widgets[0]"的路径一旦把字符串写进数值控件，
  // 前端就会显示 NaN、graphToPrompt 序列化成 null、服务端报 INT 校验失败。
  // 这里是全局兜底闸门：宁可拒绝写入并报错，也不允许 NaN 落盘/入队。
  if (isNumericWidget(target) && (typeof value !== "number" || !Number.isFinite(value))) {
    console.error("[H3 V26] 已拒绝把非有限数字写入数值控件", { name: target?.name, value });
    return;
  }
  target.value = value;
  try { target.callback?.(value); } catch (error) { console.warn("[H3 v024] 控件同步失败", error); }
  app.graph?.change?.();
}

function isNumericWidget(target) {
  const type = String(target?.type || "");
  return type === "number" || type === "slider" || type === "knob";
}

function valueOf(node, name, fallbackIndex = 0) {
  return widget(node, name, fallbackIndex)?.value;
}

// ---- V26_SEEDNODE_NAN_REPAIR_01：种子随机化控件的定位器 ----
// V25 easy seed：控件名 = control_after_generate（widget() 按名字能命中）。
// V26 Core SeedNode：io schema 下 control_after_generate 取值为 "fixed"，
//   前端把该控件命名为 "fixed"（实测 widgets = [seed(number), fixed(combo)]）。
//   ⇒ widget(node,"control_after_generate") 必然 miss，旧代码回落到 widgets[0] = seed，
//     于是把 "randomize" 写进 seed → NaN。
// 修复：先按名字（兼容旧版），再按语义定位（数值 seed 之外的 combo 且取值属于随机化枚举），
//   且**绝不回落到 index 0**。找不到就返回 null（写入侧直接放弃，不改 seed）。
const H3_SEED_CONTROL_SET = new Set(H3_SEED_CONTROL_ZH.map(([, value]) => value));
const H3_SEED_CONTROL_FALLBACK = "randomize";

function seedControlWidget(node) {
  const list = node?.widgets || [];
  const seedWidget = list.find((candidate) => candidate.name === "seed");
  const byName = list.find((candidate) => candidate.name === "control_after_generate");
  if (byName) return byName;
  const bySemantics = list.find(
    (candidate) => candidate !== seedWidget && candidate.type === "combo" && H3_SEED_CONTROL_SET.has(String(candidate.value))
  );
  if (bySemantics) return bySemantics;
  // 最后一位手段：seed 之后紧邻的那个 combo 控件（V26 实测为 widgets[1]）
  const seedIndex = seedWidget ? list.indexOf(seedWidget) : -1;
  const neighbour = seedIndex >= 0 ? list[seedIndex + 1] : null;
  return neighbour && neighbour.type === "combo" ? neighbour : null;
}

function seedControlValue(node) {
  const value = seedControlWidget(node)?.value;
  return H3_SEED_CONTROL_SET.has(String(value)) ? String(value) : "";
}

function hasFile(node, name, fallbackIndex = 0) {
  const value = valueOf(node, name, fallbackIndex);
  if (value == null) return false;
  if (typeof value === "string") return value.trim() !== "";
  return Boolean(value);
}

/* UI_REFACTOR_01：wheel 从整块面板的黑名单里摘除——面板主区域的滚轮交给
 * installPanelWheelPolicy() 按 P7/P8 硬规则分流；keydown/pointer 照旧拦截。
 * 本函数仍用于临时弹层（导演规则预览框），那里保留旧的整块吞掉行为。 */
function stopPanelEvents(panel) {
  for (const eventName of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "keydown"]) {
    panel.addEventListener(eventName, (event) => event.stopPropagation());
  }
}

/* 临时弹层专用：整个弹层吞掉 wheel（维持 UI_REFACTOR_01 之前的旧行为）。 */
function swallowWheel(elm) {
  elm.addEventListener("wheel", (event) => event.stopPropagation());
}

/* ---- P7/P8 滚轮硬规则（与 V28 导演面板同语义，自带一份不跨包 import）----
 * ① textarea：hover/focus 一律拦截（能滚走默认滚，顶/底保持焦点，不缩放画布）
 * ② 其它「真正可滚」容器：能滚才拦截，顶到边缘交还画布
 * ③ 普通区域：wheel 局部桥接回画布 → 官方指针处 zoom（无任何全局 hack） */
function panelScrollableY(elm) {
  if (!elm || elm.nodeType !== 1) return false;
  const s = getComputedStyle(elm);
  if (!/(auto|scroll|overlay)/.test(String(s.overflowY))) return false;
  return elm.scrollHeight > elm.clientHeight + 1;
}
function panelForwardWheelToCanvas(event) {
  const canvasEl = app?.canvas?.canvas;
  if (!canvasEl) return;
  canvasEl.dispatchEvent(new WheelEvent("wheel", {
    bubbles: true, cancelable: true,
    deltaX: event.deltaX, deltaY: event.deltaY, deltaZ: event.deltaZ, deltaMode: event.deltaMode,
    clientX: event.clientX, clientY: event.clientY, screenX: event.screenX, screenY: event.screenY,
  }));
}
function installPanelWheelPolicy(root) {
  root.addEventListener("wheel", (event) => {
    if (event.target instanceof HTMLTextAreaElement) { event.stopPropagation(); return; }
    for (let e = event.target; e && e !== root; e = e.parentElement) {
      if (panelScrollableY(e)) {
        const goingUp = event.deltaY < 0;
        const atTop = e.scrollTop <= 0;
        const atBottom = e.scrollTop + e.clientHeight >= e.scrollHeight - 1;
        if ((goingUp && atTop) || (!goingUp && atBottom)) break;
        event.stopPropagation();
        return;
      }
    }
    event.preventDefault();
    panelForwardWheelToCanvas(event);
  }, { passive: false });
}

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function button(text, onClick, kind = "secondary") {
  const control = el("button", `h3v14-button h3v14-${kind}`, text);
  control.type = "button";
  control.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    onClick?.();
  });
  return control;
}

function invokeUpload(sourceNode) {
  if (!sourceNode) return;
  const candidates = sourceNode.widgets || [];
  const upload = candidates.find((candidate) => candidate.name === "upload")
    || candidates.find((candidate) => /^choose .* to upload$/i.test(candidate.name || ""))
    || candidates.find((candidate) => candidate.type === "button" && /上传|upload|choose/i.test(`${candidate.name || ""} ${candidate.label || ""}`));
  if (typeof upload?.callback === "function") {
    upload.callback();
    return;
  }
  const primary = sourceNode.type === "LoadVideo" ? widget(sourceNode, "file") : widget(sourceNode, "image") || widget(sourceNode, "audio");
  const input = primary?.inputEl || primary?.element;
  if (typeof input?.click === "function") input.click();
  else console.warn("[H3 v024] 未找到原上传控件", sourceNode.id, sourceNode.type);
}

function clearFileWidget(sourceNode, name) {
  const file = widget(sourceNode, name);
  if (!file) return;
  file.value = "";
  try { file.callback?.(""); } catch (error) { console.warn("[H3 v024] 清除素材同步失败", error); }
}

function invokeClear(sourceNode) {
  if (!sourceNode) return;
  const referenceNode = byId(sourceNode, NODE_IDS.references);
  if (sourceNode.type === "LoadImageCrop") {
    clearFileWidget(sourceNode, "image");
    const crop = widget(sourceNode, "crop", 1);
    if (crop) crop.value = "";
    sourceNode.properties ||= {};
    sourceNode.properties.h3_reference_slot_enabled = false;
    sourceNode.imgs = null;
  } else if (sourceNode.type === "LoadVideo") {
    clearFileWidget(sourceNode, "file");
    setWidget(widget(referenceNode, "启用参考视频"), false);
    const nativePreview = widget(sourceNode, "videopreview");
    if (nativePreview?.value) nativePreview.value.hidden = true;
    if (nativePreview?.parentEl) nativePreview.parentEl.hidden = true;
  } else if (sourceNode.type === "LoadAudio") {
    clearFileWidget(sourceNode, "audio");
    if (Number(sourceNode.id) === 143) setWidget(widget(referenceNode, "启用参考音频1"), false);
    if (Number(sourceNode.id) === 685) setWidget(widget(referenceNode, "启用参考音频2"), false);
  }
  sourceNode.graph?.setDirtyCanvas?.(true, true);
  app.graph?.change?.();
}

function materialUrl(value) {
  if (value == null || value === "") return "";
  const raw = typeof value === "object" ? value : { filename: String(value) };
  let filename = String(raw.filename || raw.name || "").replace(/\s+\[(input|output|temp)\]$/i, "").replaceAll("\\", "/");
  let subfolder = String(raw.subfolder || "").replaceAll("\\", "/");
  if (!subfolder && filename.includes("/")) {
    const parts = filename.split("/");
    filename = parts.pop();
    subfolder = parts.join("/");
  }
  if (!filename) return "";
  const params = new URLSearchParams({ filename, type: String(raw.type || "input"), subfolder });
  return api.apiURL(`/view?${params.toString()}`);
}

function bindMaterialFacts(dashboard, referenceNode, referenceImageIds) {
  const syncPictureMaster = () => {
    let active = false;
    for (const id of referenceImageIds) {
      const source = byId(dashboard, id);
      if (!source) continue;
      const loaded = hasFile(source, "image");
      source.properties ||= {};
      source.properties.h3_reference_slot_enabled = loaded;
      const toggle = source.widgets?.find((candidate) => candidate.name === "参与图片参考");
      if (toggle) toggle.value = loaded;
      active ||= loaded;
    }
    dashboard.properties ||= {};
    dashboard.properties.HAS_ANY_REFERENCE_IMAGE = active;
    // 旧 selector 字段只作为 V28.1 序列化兼容层，不再暴露为用户开关。
    const master = widget(referenceNode, "HAS_ANY_REFERENCE_IMAGE") || widget(referenceNode, "启用四张参考图");
    if (master && Boolean(master.value) !== active) setWidget(master, active);
  };
  for (const id of referenceImageIds) {
    const source = byId(dashboard, id);
    const file = widget(source, "image");
    if (!file || file.__h3V14FactBound) continue;
    file.__h3V14FactBound = true;
    const original = file.callback;
    file.callback = function(value) {
      const result = original?.apply(this, arguments);
      const loaded = String(value ?? "").trim() !== "";
      source.properties ||= {};
      source.properties.h3_reference_slot_enabled = loaded;
      const toggle = source.widgets?.find((candidate) => candidate.name === "参与图片参考");
      if (toggle) toggle.value = loaded;
      setTimeout(syncPictureMaster, 0);
      return result;
    };
  }
  for (const [id, switchName] of [[143, "启用参考音频1"], [685, "启用参考音频2"]]) {
    const source = byId(dashboard, id);
    const file = widget(source, "audio");
    if (!file || file.__h3V14FactBound) continue;
    file.__h3V14FactBound = true;
    const original = file.callback;
    file.callback = function(value) {
      const result = original?.apply(this, arguments);
      setWidget(widget(referenceNode, switchName), String(value ?? "").trim() !== "");
      return result;
    };
  }
  const syncAudioMasters = () => {
    for (const [id, switchName] of [[143, "启用参考音频1"], [685, "启用参考音频2"]]) {
      const loaded = hasFile(byId(dashboard, id), "audio");
      const master = widget(referenceNode, switchName);
      if (master && Boolean(master.value) !== loaded) setWidget(master, loaded);
    }
  };
  return () => {
    syncPictureMaster();
    syncAudioMasters();
  };
}

function makeChoice(label, value, onPick) {
  const control = button(label, () => onPick(value), "choice");
  control.dataset.value = value;
  return control;
}

function makeMaterialRow(label, sourceNode, fileWidgetName, mediaKind = "image") {
  const row = el("div", "h3v14-material");
  const name = el("div", "h3v14-material-name", label);
  const state = el("div", "h3v14-material-state", "未上传");
  const previewHost = el("div", "h3v14-material-preview");
  const preview = el(mediaKind === "image" ? "img" : mediaKind, "h3v14-media");
  if (mediaKind !== "image") {
    preview.controls = true;
    preview.preload = "metadata";
  } else {
    preview.alt = `${label}预览`;
    preview.title = "点击查看大图";
    preview.addEventListener("click", () => preview.src && window.open(preview.src, "_blank", "noopener"));
  }
  previewHost.append(preview);
  const refreshRow = () => {
    const loaded = hasFile(sourceNode, fileWidgetName);
    state.textContent = loaded ? "已上传" : "未上传";
    state.classList.toggle("h3v14-ok", loaded);
    const url = loaded ? materialUrl(valueOf(sourceNode, fileWidgetName)) : "";
    previewHost.classList.toggle("h3v14-hidden", !url);
    if (url && preview.dataset.url !== url) {
      preview.dataset.url = url;
      preview.src = url;
    } else if (!url && preview.dataset.url) {
      preview.dataset.url = "";
      preview.removeAttribute("src");
      preview.load?.();
    }
  };
  const actions = el("div", "h3v14-material-actions");
  actions.append(
    button("上传/更换", () => invokeUpload(sourceNode)),
    button("清除", () => { invokeClear(sourceNode); refreshRow(); }, "danger"),
  );
  row.append(name, state, previewHost, actions);
  return { row, refresh: refreshRow };
}

function internalizeSources(dashboard, ready) {
  // Canvas visibility is not graph state. Native collapse/expand belongs to the user.
}

function installDashboard(node) {
  if (Number(node?.id) !== NODE_IDS.dashboard || node.properties?.[GATE] !== true || node.__h3DashboardV3) return;
  const referenceImageIds = node.properties?.h3_v282_reference_9slot === true ? REF_IMAGES_V282 : REF_IMAGES_V281;
  const requiredIds = [...Object.values(NODE_IDS), ...referenceImageIds, ...FL_IMAGES, ...AUDIOS];
  if (requiredIds.some((id) => !byId(node, id)?.widgets?.length)) return;

  const generationNode = byId(node, NODE_IDS.generation);
  const imageModeNode = byId(node, NODE_IDS.imageMode);
  const referenceNode = byId(node, NODE_IDS.references);
  const refPromptNode = byId(node, NODE_IDS.promptRef);
  const flPromptNode = byId(node, NODE_IDS.promptFl);
  const qualityNode = byId(node, NODE_IDS.quality);
  const resolutionNode = byId(node, NODE_IDS.resolution);
  const durationNode = byId(node, NODE_IDS.duration);
  const frameExprNode = byId(node, NODE_IDS.frameExpr);
  const seedNode = byId(node, NODE_IDS.seed);
  const pass2Node = byId(node, NODE_IDS.pass2);
  const routeNode = byId(node, NODE_IDS.route);
  const ref2vaBackendNode = byId(node, NODE_IDS.ref2vaBackend);
  const ref2vaAttentionNode = byId(node, NODE_IDS.ref2vaAttention);
  const memoryOptNode = nodes(node).find((candidate) => candidate.type === "H3MemoryOptimizationSelector");
  const productionUi = node.properties?.h3_v281_production_ui === true;
  // STEP 34：关键帧轴节点（缺任一即整轴不安装，绝不因此让控制台消失）
  const guideSlots = GUIDE_SLOTS.map((slot) => ({
    cropNode: byId(node, slot.crop),
    guardNode: byId(node, slot.guard),
    addGuideNode: byId(node, slot.addGuide),
  }));
  const guideSelectorNode = byId(node, GUIDE_SELECTOR);
  const guideReady = Boolean(guideSelectorNode?.widgets?.length)
    && guideSlots.every((slot) => slot.cropNode?.widgets?.length && slot.guardNode?.widgets?.length && slot.addGuideNode?.widgets?.length);
  const operationWidget = widget(node, "当前操作");

  const syncMaterialFacts = bindMaterialFacts(node, referenceNode, referenceImageIds);
  setWidget(operationWidget, "只跑一采");

  const modeKey = () => consoleModeKey(app.graph, (id) => byId(node, id));
  const isRef = () => modeKey() !== "fl2va";

  const panel = el("div", "h3v14-dashboard");
  panel.innerHTML = `<style>
    .h3v14-dashboard{box-sizing:border-box;width:100%;height:100%;min-width:0;min-height:0;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;container-type:inline-size;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-content:start;padding:12px;background:var(--comfy-menu-bg,#171717);border:1px solid var(--border-color,#555);border-radius:8px;color:var(--input-text,#eee);font:500 14px/1.4 system-ui,"Microsoft YaHei",sans-serif}
    .h3v14-dashboard>*{min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere}.h3v14-dashboard>.h3v14-title,.h3v14-dashboard>.h3v14-subtitle,.h3v14-dashboard>.h3v14-material-section,.h3v14-dashboard>.h3v14-status,.h3v14-dashboard>.h3v14-run{grid-column:1/-1}
    .h3v14-dashboard>.h3v14-section{margin-top:0;padding:10px;background:var(--comfy-input-bg,#222);border-color:var(--border-color,#555)}
    .h3v14-reference-grid{grid-template-columns:repeat(auto-fit,minmax(min(160px,100%),1fr))!important}.h3v14-material-actions{flex-wrap:wrap}.h3v14-button{white-space:normal;overflow-wrap:normal}.h3v14-dashboard select,.h3v14-dashboard input{min-width:0}.h3v14-dashboard .h3v14-material-preview{min-height:64px}.h3v14-dashboard .h3v14-media{max-height:80px}
    @container (max-width:620px){.h3v14-dashboard>.h3v14-section,.h3v14-dashboard>.h3v14-advanced{grid-column:1/-1}.h3v14-material{grid-template-columns:minmax(0,1fr) auto}.h3v14-material-preview,.h3v14-material-actions{grid-column:1/-1}.h3v14-setting{grid-template-columns:90px minmax(0,1fr)}}
    .h3v14-title{font-size:24px;color:#f0e7ff}.h3v14-subtitle{margin:2px 0 14px;color:#baa9ce;font-size:13px;font-weight:500}
    .h3v14-section{margin-top:12px;padding:12px;border:1px solid #3e3151;border-radius:9px;background:#171120}
    .h3v14-section-title{margin-bottom:9px;color:#e6d8ff;font-size:16px}.h3v14-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.h3v14-grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}.h3v14-grid-2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
    .h3v14-button{min-height:35px;padding:7px 10px;border:1px solid #76549a;border-radius:7px;background:#322342;color:#fff;font-weight:700;cursor:pointer}.h3v14-button:hover{filter:brightness(1.15)}
    .h3v14-choice{min-height:48px;background:#241833}.h3v14-choice.h3v14-active{background:#123b2a;border-color:#62dfa0;box-shadow:0 0 0 2px rgba(98,223,160,.16)}.h3v14-danger{border-color:#754052;background:#3b2029}
    .h3v14-material{display:grid;grid-template-columns:110px 70px minmax(120px,1fr) auto;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #2e243b}.h3v14-material:last-child{border-bottom:0}.h3v14-reference-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.h3v14-reference-grid .h3v14-material{display:flex;flex-wrap:wrap;align-content:flex-start;padding:9px;border:1px solid #3e3151;border-radius:8px;background:#120d19}.h3v14-reference-grid .h3v14-material-name{flex:1}.h3v14-reference-grid .h3v14-material-preview{order:3;width:100%}.h3v14-reference-grid .h3v14-material-actions{order:4;width:100%;justify-content:flex-start}.h3v14-material-state{color:#b9a8ca}.h3v14-material-state.h3v14-ok{color:#7ee5ad}.h3v14-material-actions{display:flex;gap:6px;justify-content:flex-end}.h3v14-material-preview{min-height:54px}.h3v14-media{display:block;width:100%;max-width:220px;max-height:120px;object-fit:contain;border-radius:6px;background:#08060c}.h3v14-material-preview audio{height:36px}
    .h3v14-textarea{box-sizing:border-box;width:100%;min-height:120px;resize:vertical;padding:10px;border:1px solid #76549a;border-radius:7px;background:#0d0a12;color:#fff;font:500 13px/1.5 ui-monospace,Consolas,monospace;overscroll-behavior:contain}
    .h3v14-setting{display:grid;grid-template-columns:100px 1fr;align-items:center;gap:8px;margin:7px 0}.h3v14-select,.h3v14-input{box-sizing:border-box;width:100%;height:38px;padding:6px 9px;border:1px solid #76549a;border-radius:7px;background:#0d0a12;color:#fff;font-weight:600}
    .h3v14-inline{display:grid;grid-template-columns:1fr auto;gap:7px}.h3v14-advanced{margin-top:12px;padding:12px;border:1px solid #3e3151;border-radius:9px;background:#14101b}.h3v14-advanced>summary{cursor:pointer;color:#e6d8ff;font-size:16px;font-weight:800}.h3v14-advanced-note{margin:7px 0 3px;color:#a995bd;font-size:12px;font-weight:500}.h3v14-status{margin-top:12px;padding:10px;border-radius:7px;background:#0c241a;color:#aaf1ca;font-size:12px;white-space:pre-wrap}.h3v14-run{width:100%;min-height:50px;margin-top:11px;border:0;border-radius:9px;background:#2f9e68;color:#fff;font-size:17px;font-weight:800;cursor:pointer}.h3v14-run:disabled{opacity:.55;cursor:wait}.h3v14-hidden{display:none!important}.h3v14-warning{color:#f3c979;font-size:12px;font-weight:500;margin-top:7px}
    .h3v14-refmode{margin:4px 0 8px;padding:6px 10px;border-radius:7px;font-size:14px;font-weight:800}
    .h3v14-refmode.single{background:#10243a;color:#8fd0ff;border:1px solid #2f6da3}
    .h3v14-refmode.multi{background:#10241a;color:#7ee5ad;border:1px solid #2f9e68}
    .h3v14-refmode.none{background:#3b2029;color:#ffd5df;border:1px solid #754052}
    .h3v14-tabbar{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
    .h3v14-kv{display:flex;justify-content:space-between;align-items:center;padding:6px 0;color:#cbbce4;font-size:13px}.h3v14-kv b{color:#fff;font-weight:700}
    .h3v14-stepper{display:grid;grid-template-columns:44px 1fr 44px auto;gap:8px;align-items:center;margin:9px 0}
    .h3v14-stepval{text-align:center;font-size:21px;font-weight:800;color:#7ee5ad}
    .h3v14-seed-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}
    .h3v14-readonly{color:#8fb8a2;font-size:13px;font-weight:600}
    .h3v14-guide-slot{margin-top:8px;padding-top:6px;border-top:1px dashed #3e3151}
    .h3v14-dashboard .h3v14-button,.h3v14-dashboard .h3v14-select,.h3v14-dashboard .h3v14-input{font:inherit;color:var(--input-text,#eee);background:var(--comfy-input-bg,#282828);border-color:var(--border-color,#555)}
    .h3v14-dashboard .h3v14-choice.h3v14-active{background:#123b2a;border-color:#62dfa0}.h3v14-dashboard .h3v14-danger{background:#3b2029;border-color:#754052}
    .h3v14-dashboard .h3v14-title{font-size:clamp(20px,3cqw,28px);color:var(--input-text,#eee)}.h3v14-dashboard .h3v14-section-title{color:var(--input-text,#eee)}
    .h3v14-dashboard .h3v14-reference-grid .h3v14-material,.h3v14-dashboard .h3v14-advanced{background:var(--comfy-menu-bg,#171717);border-color:var(--border-color,#555)}
  </style>`;

  const heading = el("div", "h3v14-title", node.properties?.h3_v283_text_only
    ? "H3 V28.3 长视频生产导演台" : productionUi ? "H3 V28.2 长视频生产导演台" : "H3 全中文傻瓜导演台");
  const subtitle = el("div", "h3v14-subtitle", productionUi
    ? "选生成方式 → 传素材 → 导演整理 → 设时长 → 开始生成。描述使用原生提示词节点。"
    : "选方式、传素材、导演整理、调步数与种子；描述使用原生提示词节点。");
  panel.append(heading, subtitle);

  // ===== ① 选择生成方式 =====
  const modeSection = el("section", "h3v14-section");
  modeSection.append(el("div", "h3v14-section-title", "① 选择生成方式"));
  const topGrid = el("div", "h3v14-grid");
  const refButton = makeChoice("多参考生成", H3_GEN_REF, () => {
    setWidget(widget(generationNode, "生成模式"), H3_GEN_REF);
    refresh();
  });
  const flButton = makeChoice("常规视频生成", H3_GEN_FL, () => {
    setWidget(widget(generationNode, "生成模式"), H3_GEN_FL);
    refresh();
  });
  topGrid.append(refButton, flButton);
  // 多参考子块：V28.2 收口为两档（稳定8步 turbo_8step / PDD8步 MiniMaxH3PDDAccApply）。
  // 稀疏高速4步已退役：后端节点保留在图内作 rollback，但不再提供 UI 入口。
  const refBackendGrid = el("div", "h3v14-grid-2");
  const backendChoices = [
    [H3_BACKEND_LABEL[H3_BACKEND_STABLE8], H3_BACKEND_STABLE8],
    [H3_BACKEND_LABEL[H3_BACKEND_PDD8], H3_BACKEND_PDD8],
  ].map(([label, value]) => makeChoice(label, value, () => {
    setWidget(widget(ref2vaBackendNode, "Ref2VA 后端"), value);
    if (value === H3_BACKEND_PDD8) setWidget(widget(ref2vaAttentionNode, "注意力方案"), H3_ATTENTION_INT8);
    refresh();
  }));
  refBackendGrid.append(...backendChoices);
  // 常规子块：三种图片模式
  const flImageGrid = el("div", "h3v14-grid-3");
  const flImageChoices = [
    [H3_IMAGE_LABEL[H3_IMAGE_T2V], H3_IMAGE_T2V],
    [H3_IMAGE_LABEL[H3_IMAGE_I2V], H3_IMAGE_I2V],
    [H3_IMAGE_LABEL[H3_IMAGE_FLF], H3_IMAGE_FLF],
  ].map(([label, value]) => makeChoice(label, value, () => {
    setWidget(widget(imageModeNode, "图片模式"), value);
    refresh();
  }));
  flImageGrid.append(...flImageChoices);
  // FL2VA 路线改为只读中文状态（§12：不再显示下拉）
  const flEngineNote = el("div", "h3v14-warning", "当前常规视频引擎：高速4步");
  modeSection.append(topGrid, refBackendGrid, flImageGrid, flEngineNote);
  panel.append(modeSection);

  // ===== ② 参考素材 =====
  const materialSection = el("section", "h3v14-section h3v14-material-section");
  materialSection.append(el("div", "h3v14-section-title", "② 参考素材"));
  // 参考模式真实徽标（不再仅凭 selector 声明）：single=单首帧 / multi=多参考图 / none=声称但未接
  const refModeLabel = el("div", "h3v14-refmode single", "参考模式：—");
  materialSection.append(refModeLabel);
  materialSection.append(el("div", "h3v14-readonly", "参考图请从图1开始连续上传，不要中间留空。每张图的用途由你用文字定义。"));
  const materialHost = el("div", "h3v14-material-host");
  const materialRows = {
    refs: referenceImageIds.map((id, index) => makeMaterialRow(`参考图 ${index + 1}`, byId(node, id), "image", "image")),
    first: makeMaterialRow("主图 / 首帧", byId(node, 874), "image"),
    last: makeMaterialRow("尾帧（可选）", byId(node, 875), "image"),
    video: makeMaterialRow("参考视频", byId(node, NODE_IDS.video), "video", "video"),
    audios: AUDIOS.map((id, index) => makeMaterialRow(`参考音频 ${index + 1}`, byId(node, id), "audio", "audio")),
  };
  const referenceGrid = el("div", "h3v14-reference-grid");
  for (const item of materialRows.refs) referenceGrid.append(item.row);
  materialHost.append(referenceGrid);
  for (const item of [materialRows.first, materialRows.last, materialRows.video, ...materialRows.audios]) materialHost.append(item.row);
  materialSection.append(materialHost);
  panel.append(materialSection);

  // ===== ③ 视频参考 =====
  const videoSection = el("section", "h3v14-section");
  videoSection.append(el("div", "h3v14-section-title", "③ 视频参考"));
  const videoToggleGrid = el("div", "h3v14-grid");
  const videoOn = makeChoice("开", "true", () => { setWidget(widget(referenceNode, "启用参考视频"), true); refresh(); });
  const videoOff = makeChoice("关", "false", () => { setWidget(widget(referenceNode, "启用参考视频"), false); refresh(); });
  videoToggleGrid.append(videoOn, videoOff);
  videoSection.append(videoToggleGrid);
  if (productionUi) {
    videoSection.querySelector(".h3v14-section-title").textContent = "参考视频开关（可选）";
    materialSection.append(videoSection);
  } else {
    panel.append(videoSection);
  }

  // ===== ④ 提示词 =====
  const promptSection = el("section", "h3v14-section");
  promptSection.append(el("div", "h3v14-section-title", "④ 导演整理"));
  promptSection.append(el("div", "h3v14-readonly", "读取当前生成方式的原生提示词；预览后应用。"));
  // ===== ④ 导演规则自动整理（V25_DETERMINISTIC_DIRECTOR_RULE_LAYER；语义层未实现）=====
  const organizeBtn = button("导演规则自动整理", () => openDirectorOrganize(), "choice");
  organizeBtn.title = "确定性规则层：格式编译与校验；不改语义内容、不改模式/参数/素材、不提交 Queue";
  promptSection.append(organizeBtn);
  panel.append(promptSection);

  // ===== ⑤ 生成设置 =====
  const settings = el("section", "h3v14-section");
  settings.append(el("div", "h3v14-section-title", "⑤ 生成设置"));
  const ratio = el("select", "h3v14-select");
  H3_RATIO_ZH.forEach(([label, value]) => ratio.add(new Option(label, value)));
  ratio.addEventListener("change", () => setWidget(widget(resolutionNode, "aspect_ratio"), ratio.value));
  const mp = el("input", "h3v14-input"); mp.type = "number"; mp.min = "0.1"; mp.max = "16"; mp.step = "0.1";
  mp.addEventListener("change", () => setWidget(widget(resolutionNode, "megapixels", 1), Number(mp.value)));
  const duration = el("input", "h3v14-input"); duration.type = "number"; duration.min = "1"; duration.step = "0.1";
  duration.addEventListener("change", () => setWidget(widget(durationNode, "value"), Number(duration.value)));
  const frameCountText = el("span", "h3v14-readonly", "—");
  const frameCountRow = el("label", "h3v14-setting"); frameCountRow.append(el("span", "", "实际帧数"), frameCountText);
  const settingRow = (label, control) => { const row = el("label", "h3v14-setting"); row.append(el("span", "", label), control); settings.append(row); };
  settingRow("比例", ratio); settingRow("目标百万像素", mp); settingRow("时长（秒）", duration);
  settings.append(frameCountRow);
  panel.append(settings);

  // V28.1 Production：MemoryOpt 是可选生产能力，不是锁死开关。
  // 控件直接投影 H3MemoryOptimizationSelector 的真实 widget，不保存第二套状态。
  let memoryOptOff = null;
  let memoryOptOn = null;
  let memoryOptNote = null;
  const memoryOptSection = el("section", "h3v14-section");
  memoryOptSection.append(el("div", "h3v14-section-title", "H3 内存优化（仅 PDD 8步）"));
  const memoryOptGrid = el("div", "h3v14-grid");
  if (memoryOptNode?.widgets?.length) {
    memoryOptOff = makeChoice("关闭（生产默认）", "关闭", () => {
      setWidget(widget(memoryOptNode, "H3内存优化"), "关闭");
      refresh();
    });
    memoryOptOn = makeChoice("开启（高级可选）", "开启", () => {
      setWidget(widget(memoryOptNode, "H3内存优化"), "开启");
      refresh();
    });
    memoryOptGrid.append(memoryOptOff, memoryOptOn);
    memoryOptNote = el("div", "h3v14-warning",
      "当前生产证据未观察到稳定收益，默认关闭。需要时可手动开启；只对 PDD Ref2VA 8步生效。");
    memoryOptSection.append(memoryOptGrid, memoryOptNote);
  } else {
    memoryOptSection.append(el("div", "h3v14-warning", "当前工作流未检测到 H3 内存优化节点。"));
  }

  // ===== ⑥ 采样调节 =====
  const samplingSection = el("section", "h3v14-section");
  samplingSection.append(el("div", "h3v14-section-title", "⑥ 采样调节"));
  const tabBar = el("div", "h3v14-tabbar");
  const tabOne = button("一采调节", () => { showTab(true); }, "choice");
  const tabTwo = button("二采调节", () => { showTab(false); }, "choice");
  tabBar.append(tabOne, tabTwo);
  samplingSection.append(tabBar);
  // 一采面板
  const onePanel = el("div", "");
  const engineKV = el("div", "h3v14-kv"); engineKV.append(el("span", "", "当前引擎"), el("b", "", "—"));
  const recommendKV = el("div", "h3v14-kv"); recommendKV.append(el("span", "", "推荐步数"), el("b", "", "—"));
  const stepInput = el("input", "h3v14-input"); stepInput.type = "number"; stepInput.min = "1"; stepInput.max = "100"; stepInput.step = "1";
  stepInput.addEventListener("change", () => {
    const target = H3_STEP_TARGETS[modeKey()];
    setWidget(widget(byId(node, target.nodeId), target.widget), Math.max(1, Math.min(100, Number(stepInput.value) || 1)));
    refresh();
  });
  const stepper = el("div", "h3v14-stepper");
  const minusBtn = button("−", () => adjustStep(-1), "secondary");
  const plusBtn = button("+", () => adjustStep(1), "secondary");
  const restoreBtn = button("恢复推荐值", () => {
    const target = H3_STEP_TARGETS[modeKey()];
    setWidget(widget(byId(node, target.nodeId), target.widget), H3_RECOMMENDED_STEPS[modeKey()]);
    refresh();
  }, "secondary");
  stepper.append(minusBtn, stepInput, plusBtn, restoreBtn);
  const devNote = el("div", "h3v14-warning", "");
  onePanel.append(engineKV, recommendKV, stepper, devNote);
  // 二采面板（只读，§18）
  const twoPanel = el("div", "");
  const pass2KV = el("div", "h3v14-kv"); pass2KV.append(el("span", "", "当前步数"), el("b", "", "—"));
  const pass2State = el("div", "h3v14-readonly", "状态：暂未开放");
  twoPanel.append(pass2KV, pass2State);
  samplingSection.append(onePanel, twoPanel);
  panel.append(samplingSection);

  // ===== ⑦生成过程预览（Phase D2：仅代理 N691 原生 mode，关闭=真正绕过）=====
  const previewSection = el("section", "h3v14-section");
  previewSection.append(el("div", "h3v14-section-title", "⑦ 生成过程预览"));
  const previewToggleGrid = el("div", "h3v14-grid");
  const previewOn = makeChoice("开启", H3_PREVIEW_ON, () => { setWidget(widget(node, H3_PREVIEW_WIDGET), H3_PREVIEW_ON); refresh(); });
  const previewOff = makeChoice("关闭", H3_PREVIEW_OFF, () => { setWidget(widget(node, H3_PREVIEW_WIDGET), H3_PREVIEW_OFF); refresh(); });
  previewToggleGrid.append(previewOff, previewOn);
  const previewNote = el("div", "h3v14-warning", "默认关闭（速度优先）。开启后采样时显示实时画面，会略微增加耗时。");
  previewSection.append(previewToggleGrid, previewNote);
  panel.append(previewSection);
  function showTab(isOne) {
    tabOne.classList.toggle("h3v14-active", isOne);
    tabTwo.classList.toggle("h3v14-active", !isOne);
    onePanel.classList.toggle("h3v14-hidden", !isOne);
    twoPanel.classList.toggle("h3v14-hidden", isOne);
  }
  function adjustStep(delta) {
    const target = H3_STEP_TARGETS[modeKey()];
    const w = widget(byId(node, target.nodeId), target.widget);
    const next = Math.max(1, Math.min(100, (Number(w?.value) || 0) + delta));
    setWidget(w, next);
    refresh();
  }

  // ===== ⑧ 时间轴关键帧（STEP 34：可选轴，默认「不使用」＝整链旁路＝直通）=====
  // 概念边界（作者 2026-09-19 方案 §8，禁止再混淆）：
  //   参考素材＝语义参考，只告诉模型"长什么样"，不规定出现在第几帧；
  //   关键帧＝时间轴锚点，规定"第 frame_idx 帧必须到达这张画面"。两者互不替代。
  const guideValueNow = () => String(valueOf(guideSelectorNode, "关键帧控制") || GUIDE_MODES[0]);
  const guideCountNow = () => Math.max(0, GUIDE_MODES.indexOf(guideValueNow()));
  let guideRows = null;
  const guideChoices = [];
  let guideSection = null;
  if (guideReady) {
    guideSection = el("section", "h3v14-section");
    guideSection.append(el("div", "h3v14-section-title", "⑧ 时间轴关键帧（可选）"));
    guideSection.append(el("div", "h3v14-warning",
      "关键帧＝规定「第几帧必须出现这张画面」；参考图只告诉模型长什么样、不规定时刻。默认不使用；开启后每张关键帧都必须上传图片。"));
    const guideChoiceGrid = el("div", "h3v14-grid");
    GUIDE_MODES.forEach((mode) => guideChoices.push(makeChoice(
      mode === GUIDE_MODES[0] ? "不使用关键帧" : `使用 ${mode.slice(0, 1)} 张`,
      mode,
      () => { setWidget(widget(guideSelectorNode, "关键帧控制"), mode); refresh(); },
    )));
    guideChoiceGrid.append(...guideChoices);
    const guideHost = el("div", "");
    guideRows = guideSlots.map((slot, index) => {
      const wrap = el("div", "h3v14-guide-slot");
      const material = makeMaterialRow(`关键帧 ${index + 1} 画面`, slot.cropNode, "image", "image");
      const frameInput = el("input", "h3v14-input");
      frameInput.type = "number"; frameInput.min = "-9999"; frameInput.max = "9999"; frameInput.step = "1";
      frameInput.title = "从 0 开始计帧；负数＝从片尾倒数（-1＝最后一帧）";
      frameInput.addEventListener("change", () => {
        const parsed = Math.round(Number(frameInput.value));
        setWidget(widget(slot.addGuideNode, "frame_idx"), Number.isFinite(parsed) ? parsed : 0);
        refresh();
      });
      const frameRow = el("label", "h3v14-setting");
      frameRow.append(el("span", "", "出现在第几帧"), frameInput);
      wrap.append(material.row, frameRow);
      guideHost.append(wrap);
      return { wrap, material, frameInput, slot };
    });
    guideSection.append(guideChoiceGrid, guideHost);
    if (!node.properties?.h3_v283_text_only) panel.append(guideSection);
  }

  // ===== ⑨ 随机种子（紧贴开始生成上方）=====
  const seedSection = el("section", "h3v14-section");
  seedSection.append(el("div", "h3v14-section-title", "⑨ 随机种子"));
  const seedStepper = el("div", "h3v14-stepper");
  const seedMinus = button("−", () => adjustSeed(-1));
  const seedInput = el("input", "h3v14-input"); seedInput.type = "text"; seedInput.inputMode = "numeric";
  seedInput.addEventListener("change", () => {
    const v = Number(seedInput.value);
    if (Number.isFinite(v)) setWidget(widget(seedNode, "seed"), Math.round(v));
    refresh();
  });
  const seedPlus = button("+", () => adjustSeed(1));
  seedStepper.append(seedMinus, seedInput, seedPlus);
  const seedControlGrid = el("div", "h3v14-seed-grid");
  const seedControls = H3_SEED_CONTROL_ZH.map(([label, value]) => makeChoice(label, value, () => {
    setWidget(seedControlWidget(seedNode), value);
    refresh();
  }));
  seedControlGrid.append(...seedControls);
  seedSection.append(seedStepper, seedControlGrid);
  panel.append(seedSection);
  function adjustSeed(delta) {
    const w = widget(seedNode, "seed");
    setWidget(w, (Number(w?.value) || 0) + delta);
    refresh();
  }

  // V28.1 Production：一级界面只保留长视频制作的必经步骤。
  const diagnosticSection = el("section", "h3v14-section");
  diagnosticSection.append(el("div", "h3v14-section-title", "失败诊断（手动使用）"));
  const nativeAvailable = byId(node, 1011)?.properties?.h3_ref2va_backend_branch === "native20";
  const nativeButton = makeChoice(H3_BACKEND_LABEL[H3_BACKEND_NATIVE20], H3_BACKEND_NATIVE20, () => {
    if (!isRef() || !nativeAvailable) return;
    setWidget(widget(ref2vaBackendNode, "Ref2VA 后端"), H3_BACKEND_NATIVE20);
    refresh();
  });
  nativeButton.disabled = !nativeAvailable;
  diagnosticSection.append(nativeButton, el("div", "h3v14-readonly",
    "对照前将种子设为固定不变，保留同一提示词和参考图，手动生成一次；完成后点 PDD多参考8步返回主线。"));
  // 采样、预览、关键帧、种子、MemoryOpt 统一收进一个可展开高级区，
  // 避免重复一级标题；所有控件仍是可见、可读回的真实前端状态。
  if (productionUi) {
    const advanced = el("details", "h3v14-advanced");
    advanced.append(el("summary", "", "高级选项（通常不用改）"));
    advanced.append(el("div", "h3v14-advanced-note",
      "包含采样步数、过程预览、时间轴关键帧、随机种子和 H3 内存优化。"));
    advanced.append(diagnosticSection, memoryOptSection, samplingSection, previewSection);
    if (guideSection && !node.properties?.h3_v283_text_only) advanced.append(guideSection);
    advanced.append(seedSection);
    panel.append(advanced);
  }

  if (!productionUi && nativeAvailable) panel.append(diagnosticSection);

  // ===== 状态 + 开始生成 =====
  const status = el("div", "h3v14-status", "正在读取底层状态……");
  const run = el("button", "h3v14-run", "▶ 开始生成"); run.type = "button";
  let busy = false;
  function prequeueProblems() {
    syncMaterialFacts();
    const problems = [];
    const refMode = isRef();
    const imageMode = String(valueOf(imageModeNode, "图片模式") || H3_IMAGE_T2V);
    const activePrompt = String(valueOf(refMode ? refPromptNode : flPromptNode, "value") || "").trim();
    if (!activePrompt) problems.push("请先填写提示词。");
    if (refMode) {
      const imageCount = referenceImageIds.filter((id) => hasFile(byId(node, id), "image")).length;
      const imageReady = imageCount > 0;
      const videoReady = Boolean(valueOf(referenceNode, "启用参考视频")) && hasFile(byId(node, NODE_IDS.video), "video");
      const audioCount = AUDIOS.filter((id, index) => Boolean(valueOf(referenceNode, `启用参考音频${index + 1}`)) && hasFile(byId(node, id), "audio")).length;
      const audioReady = audioCount > 0;
      if (!imageReady && !videoReady && !audioReady) problems.push("多参考图生成至少需要一项有效的图片、视频或音频参考素材。");
      if (Boolean(valueOf(referenceNode, "启用参考视频")) && !hasFile(byId(node, NODE_IDS.video), "video")) problems.push("视频参考已开启，但尚未上传参考视频。");
      if (imageCount + (videoReady ? 1 : 0) + audioCount > 12) problems.push("参考文件总数超过 12（图片 + 视频 + 音频），请清除多余素材后再提交。");
    } else if (imageMode === H3_IMAGE_I2V && !hasFile(byId(node, 874), "image")) {
      problems.push("单图视频尚未上传主图，请先上传主图。");
    } else if (imageMode === H3_IMAGE_FLF && !hasFile(byId(node, 874), "image")) {
      problems.push("首尾帧视频尚未上传首帧。尾帧可以为空。");
    }
    const durationValue = Number(valueOf(durationNode, "value"));
    if (!Number.isFinite(durationValue) || durationValue <= 0) problems.push("视频时长必须大于 0 秒。");
    // STEP 34：关键帧轴 —— 开启几张就必须真的传了几张图（后端 guard 也会报中文错，这里提前拦）。
    const guideCount = guideCountNow();
    for (let index = 0; index < guideCount; index += 1) {
      if (!hasFile(guideSlots[index].cropNode, "image")) problems.push(`已开启 ${guideCount} 个时间轴关键帧，但关键帧 ${index + 1} 尚未上传图片。`);
    }
    return problems;
  }
  run.addEventListener("click", async (event) => {
    event.preventDefault(); event.stopPropagation();
    if (busy) return;
    const problems = prequeueProblems();
    if (problems.length) {
      status.textContent = `无法开始生成：\n${problems.map((item) => `• ${item}`).join("\n")}`;
      status.style.background = "#3b2029";
      status.style.color = "#ffd5df";
      return;
    }
    busy = true; run.disabled = true; status.style.background = "#0c241a"; status.style.color = "#aaf1ca"; status.textContent = "正在同步执行路由并提交……";
    try {
      setWidget(operationWidget, "只跑一采");
      for (const [source, name] of [[generationNode, "生成模式"], [imageModeNode, "图片模式"], [referenceNode, "启用参考视频"], [ref2vaBackendNode, "Ref2VA 后端"], [ref2vaAttentionNode, "注意力方案"], [guideSelectorNode, "关键帧控制"]]) {
        const target = widget(source, name); if (target) setWidget(target, target.value);
      }
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      await app.queuePrompt(0, 1);
      status.textContent = "已提交 1 个任务，可在任务历史查看进度。";
    } catch (error) {
      console.error("[H3 v024] 提交失败", error);
      status.textContent = `提交失败：${error?.message || error}`;
    } finally {
      busy = false; run.disabled = false;
    }
  });
  panel.append(status, run);
  stopPanelEvents(panel);
  installPanelWheelPolicy(panel);   // UI_REFACTOR_01：主面板滚轮分流（P7/P8）

  // ===== 导演规则自动整理：预览 → 用户应用/取消（绝不直接覆盖、绝不 Queue）=====
  let directorOverlay = null;

  function directorContext() {
    const key = modeKey();
    const refMode = key !== "fl2va";
    const targetNode = refMode ? refPromptNode : flPromptNode;
    const imageModeRaw = String(valueOf(imageModeNode, "图片模式") || "");
    const imageMode = imageModeRaw === H3_IMAGE_I2V ? "I2VA" : imageModeRaw === H3_IMAGE_FLF ? "FLF" : "T2VA";
    let pictures;
    if (refMode) {
      pictures = referenceImageIds.filter((id) => hasFile(byId(node, id), "image")).length;
    } else if (imageMode === "FLF") {
      pictures = (hasFile(byId(node, 874), "image") ? 1 : 0) + (hasFile(byId(node, 875), "image") ? 1 : 0);
    } else if (imageMode === "I2VA") {
      pictures = hasFile(byId(node, 874), "image") ? 1 : 0;
    } else {
      pictures = 0;
    }
    const videos = Boolean(valueOf(referenceNode, "启用参考视频")) && hasFile(byId(node, NODE_IDS.video), "video") ? 1 : 0;
    const audios = AUDIOS.filter((id, index) => Boolean(valueOf(referenceNode, `启用参考音频${index + 1}`)) && hasFile(byId(node, id), "audio")).length;
    return {
      modeKey: key,
      imageMode: refMode ? "" : imageMode,
      text: String(valueOf(targetNode, "value") || ""),
      durationSeconds: Number(valueOf(durationNode, "value")) || 0,
      refs: { pictures, videos, audios },
    };
  }

  function openDirectorOrganize() {
    const ctx = directorContext();
    if (!ctx.text.trim()) {
      status.textContent = "导演规则自动整理：当前提示词为空，无需整理。";
      return;
    }
    const result = h3DrCompile(ctx);
    showDirectorPreview(result);
  }

  function showDirectorPreview(result) {
    if (!directorOverlay) {
      directorOverlay = el("div", "");
      directorOverlay.style.cssText = "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center";
      const box = el("div", "");
      box.style.cssText = "box-sizing:border-box;width:min(780px,92vw);max-height:88vh;overflow:auto;padding:16px;background:#171120;border:1px solid #76549a;border-radius:12px;color:#fff;font:600 14px/1.5 system-ui,'Microsoft YaHei',sans-serif";
      const title = el("div", "h3v14-section-title", "导演规则自动整理 · 预览（V1.1.1 确定性层）");
      const warnBox = el("div", "");
      warnBox.style.cssText = "margin:8px 0";
      const noteBox = el("div", "h3v14-readonly");
      const draftArea = el("textarea", "h3v14-textarea");
      draftArea.style.cssText = "min-height:230px";
      const row = el("div", "h3v14-grid");
      const applyBtn = button("应用", applyDirectorDraft, "choice");
      const cancelBtn = button("取消", hideDirectorPreview, "secondary");
      row.append(cancelBtn, applyBtn);
      const hint = el("div", "h3v14-warning", "草稿可先手动修改再应用。应用仅写回提示词文本；不改动模式/模型/参数/素材，不提交 Queue。");
      box.append(title, warnBox, noteBox, draftArea, row, hint);
      directorOverlay.append(box);
      stopPanelEvents(box);
      document.body.append(directorOverlay);
      directorOverlay.__h3 = { draftArea, warnBox, noteBox };
    }
    const ref = directorOverlay.__h3;
    ref.warnBox.innerHTML = "";
    if (result.warnings.length) {
      for (const w of result.warnings) {
        const line = el("div", "h3v14-warning", "⚠ " + w);
        line.style.cssText = "margin:4px 0";
        ref.warnBox.append(line);
      }
    } else {
      ref.warnBox.append(el("div", "h3v14-readonly", "未发现格式问题。"));
    }
    ref.noteBox.innerHTML = "";
    for (const n of result.notes) ref.noteBox.append(el("div", "", "· " + n));
    ref.draftArea.value = result.draft;
    directorOverlay.style.display = "flex";
  }

  function hideDirectorPreview() {
    if (directorOverlay) directorOverlay.style.display = "none";
  }

  function applyDirectorDraft() {
    const draft = directorOverlay?.__h3?.draftArea?.value;
    if (typeof draft !== "string") { hideDirectorPreview(); return; }
    const targetNode = isRef() ? refPromptNode : flPromptNode;
    setWidget(widget(targetNode, "value"), draft); // 走既有同步逻辑 → N138 / N914
    hideDirectorPreview();
    refresh();
  }

  function refresh() {
    const key = modeKey();
    const refMode = key !== "fl2va";
    // v024：控制台模式的唯一权威来源是 N647「生成模式」。执行节点 mode 的同步存在
    // 时序差，绝不能反向用 N136/N687 等执行态来锁定用户素材入口。
    // 「当前是否参与生成」与「用户是否允许上传素材」必须完全分离。
    const truth = refMode ? "multi" : "single";
    const imageMode = String(valueOf(imageModeNode, "图片模式") || H3_IMAGE_T2V);
    // ① 生成方式
    refButton.classList.toggle("h3v14-active", refMode);
    flButton.classList.toggle("h3v14-active", !refMode);
    refBackendGrid.classList.toggle("h3v14-hidden", !refMode);
    flImageGrid.classList.toggle("h3v14-hidden", refMode);
    flEngineNote.classList.toggle("h3v14-hidden", refMode);
    const backendValue = String(valueOf(ref2vaBackendNode, "Ref2VA 后端") || H3_BACKEND_STABLE8);
    backendChoices.forEach((control) => control.classList.toggle("h3v14-active", refMode && control.dataset.value === backendValue));
    nativeButton.classList.toggle("h3v14-active", refMode && backendValue === H3_BACKEND_NATIVE20);
    nativeButton.disabled = !nativeAvailable || !refMode;
    flImageChoices.forEach((control) => control.classList.toggle("h3v14-active", !refMode && control.dataset.value === imageMode));
    // H3 MemoryOpt：只在 PDD 8步时允许切换；其他后端明确显示待机并保持关闭。
    if (memoryOptNode?.widgets?.length) {
      // V28.2：PDD 档枚举为「PDD多参考8步」；旧图遗留「官方PDD多参考8步」等 official 值按同档兼容。
      const pddActive = refMode && (backendValue === H3_BACKEND_PDD8 || backendValue === H3_BACKEND_OFFICIAL);
      const memoryValue = String(valueOf(memoryOptNode, "H3内存优化") || "关闭");
      memoryOptOff?.classList.toggle("h3v14-active", memoryValue !== "开启");
      memoryOptOn?.classList.toggle("h3v14-active", pddActive && memoryValue === "开启");
      if (memoryOptOff) memoryOptOff.disabled = false;
      if (memoryOptOn) memoryOptOn.disabled = !pddActive;
      if (memoryOptNote) memoryOptNote.textContent = pddActive
        ? `当前：${memoryValue}。生产默认关闭；需要时可手动开启，状态会直接写入工作流。`
        : "当前后端不是 PDD 8步；H3 内存优化不参与执行。";
    }
    // ② 素材 / ③ 视频参考 条件显隐
    // 参考模式真实徽标（single=单首帧 / multi=多参考图 / none=声称未接）
    refModeLabel.textContent = truth === "multi"
      ? "参考模式：多参考图"
      : "参考模式：单首帧";
    refModeLabel.classList.remove("single", "multi", "none");
    refModeLabel.classList.add(truth === "multi" ? "multi" : "single");
    // v024：参考图 1-4 仅在多参考模式显隐；单首帧模式隐藏，绝不加 pointer-events 锁。
    // 素材入口始终可写，上传/清除永远可用。
    materialRows.refs.forEach((item) => item.row.classList.toggle("h3v14-hidden", !refMode));
    materialRows.audios.forEach((item) => item.row.classList.toggle("h3v14-hidden", !refMode));
    materialRows.video.row.classList.toggle("h3v14-hidden", !refMode);
    const firstFrameUsed = !refMode && imageMode !== H3_IMAGE_T2V;
    const lastFrameUsed = !refMode && imageMode === H3_IMAGE_FLF;
    materialRows.first.row.classList.toggle("h3v14-hidden", !firstFrameUsed);
    materialRows.last.row.classList.toggle("h3v14-hidden", !lastFrameUsed);
    videoSection.classList.toggle("h3v14-hidden", !refMode);
    const videoEnabled = Boolean(valueOf(referenceNode, "启用参考视频"));
    videoOn.classList.toggle("h3v14-active", videoEnabled);
    videoOff.classList.toggle("h3v14-active", !videoEnabled);
    // ④ 提示词
    const activePrompt = String(valueOf(refMode ? refPromptNode : flPromptNode, "value") || "");
    // ⑤ 生成设置
    if (document.activeElement !== ratio) ratio.value = String(valueOf(resolutionNode, "aspect_ratio") || "9:16 (Portrait Widescreen)");
    if (document.activeElement !== mp) mp.value = String(valueOf(resolutionNode, "megapixels", 1) ?? 0.6);
    if (document.activeElement !== duration) duration.value = String(valueOf(durationNode, "value") ?? 8);
    const seconds = Number(valueOf(durationNode, "value")) || 0;
    const frameCount = readFrameCount(String(valueOf(frameExprNode, "expression") || ""), seconds);
    frameCountText.textContent = frameCount == null ? "—" : String(frameCount);
    // ⑥ 采样调节
    const target = H3_STEP_TARGETS[key];
    const currentSteps = Number(widget(byId(node, target.nodeId), target.widget)?.value) || 0;
    const recommended = H3_RECOMMENDED_STEPS[key];
    const engineName = key === "fl2va"
      ? "常规高速视频"
      : (H3_BACKEND_LABEL[backendValue] || "稳定多参考8步");
    engineKV.querySelector("b").textContent = engineName;
    recommendKV.querySelector("b").textContent = String(recommended);
    if (document.activeElement !== stepInput && String(stepInput.value) !== String(currentSteps)) stepInput.value = String(currentSteps);
    devNote.textContent = currentSteps !== recommended
      ? `当前 ${currentSteps} 步，已偏离该引擎推荐值 ${recommended}，可能影响效果。`
      : "";
    devNote.classList.toggle("h3v14-hidden", currentSteps === recommended);
    const pass2Value = Number(widget(pass2Node, "value")?.value) || 0;
    pass2KV.querySelector("b").textContent = String(pass2Value);
    // ⑦ 随机种子
    const seedValue = Number(widget(seedNode, "seed")?.value) || 0;
    if (document.activeElement !== seedInput && seedInput.value !== String(seedValue)) seedInput.value = String(seedValue);
    const seedControl = seedControlValue(seedNode) || H3_SEED_CONTROL_FALLBACK;
    seedControls.forEach((control) => control.classList.toggle("h3v14-active", control.dataset.value === seedControl));
    // ⑦生成过程预览（只读高亮，绝不在此写 N691 mode —— 手动 BYPASS 必须被尊重）
    const previewEnabledNow = widget(node, H3_PREVIEW_WIDGET)?.value === H3_PREVIEW_ON;
    previewOn.classList.toggle("h3v14-active", previewEnabledNow);
    previewOff.classList.toggle("h3v14-active", !previewEnabledNow);
    // 素材事实回写
    for (const item of [...materialRows.refs, materialRows.first, materialRows.last, materialRows.video, ...materialRows.audios]) item.refresh();
    syncMaterialFacts();
    // ⑧ 时间轴关键帧（隐藏＝该槽位未启用；绝不一键清空用户已选图片）
    const guideCount = guideCountNow();
    guideChoices.forEach((control) => control.classList.toggle("h3v14-active", control.dataset.value === guideValueNow()));
    if (guideRows) guideRows.forEach((row, index) => {
      row.wrap.classList.toggle("h3v14-hidden", guideCount < index + 1);
      const idx = Number(widget(row.slot.addGuideNode, "frame_idx")?.value) || 0;
      if (document.activeElement !== row.frameInput && String(row.frameInput.value) !== String(idx)) row.frameInput.value = String(idx);
      row.material.refresh();
    });
    // 状态区（以真实参考模式为准，不谎称多参考）
    const isMulti = truth === "multi";
    const modeText = isMulti ? (H3_BACKEND_LABEL[backendValue] || "多参考") : (H3_IMAGE_LABEL[imageMode] || imageMode);
    const materialText = isMulti
      ? materialRows.refs.map((item, index) => `图${index + 1}：${item.row.querySelector(".h3v14-material-state")?.textContent}`).join("｜")
      : imageMode === H3_IMAGE_T2V ? "无需图片" : `首帧：${materialRows.first.row.querySelector(".h3v14-material-state")?.textContent}` + (imageMode === H3_IMAGE_FLF ? `｜尾帧：${materialRows.last.row.querySelector(".h3v14-material-state")?.textContent}` : "");
    const guideText = guideCount ? `\n时间轴关键帧：${guideCount} 张（${guideRows ? guideRows.slice(0, guideCount).map((row) => row.material.row.querySelector(".h3v14-material-state")?.textContent).join("｜") : ""}）` : "\n时间轴关键帧：不使用（直通）";
    const memoryStatus = memoryOptNode?.widgets?.length
      ? `｜内存优化：${String(valueOf(memoryOptNode, "H3内存优化") || "关闭")}`
      : "";
    if (!busy) status.textContent = `当前：${modeText}｜视频参考：${videoEnabled ? "开" : "关"}${memoryStatus}\n${materialText}\n${duration.value} 秒｜${ratio.options[ratio.selectedIndex]?.text || ratio.value}｜一采 ${currentSteps} 步${guideRows ? guideText : ""}`;
  }

  // Refresh before registering the widget so a failed build can be retried cleanly.
  refresh();
  showTab(true);
  // Native DOM widget owns height and canvas zoom. Discard stale widget widths
  // on draw as well as resize (configure/undo can restore geometry without a drag).
  const syncPanelWidth = (widget) => { widget.width = node.size[0]; };
  const domWidget = node.addDOMWidget("h3_dashboard_v3", "H3_DASHBOARD_V3", panel, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 240,
    getMaxHeight: () => Infinity,
    onDraw: syncPanelWidth,
    afterResize() { syncPanelWidth(this); },
  });
  syncPanelWidth(domWidget);
  // Preserve saved/user dimensions; installing a widget must not reset node geometry.
  node.__h3DashboardV3 = true;
  node.__h3DashboardV3Panel = panel;
  node.__h3DashboardV3Refresh = refresh;
  if (node.__h3DashboardV3Timer) clearInterval(node.__h3DashboardV3Timer);
  node.__h3DashboardV3Timer = setInterval(() => {
    if (node.graph && panel.isConnected) {
      refresh();
    }
  }, 500);
  const originalOnRemoved = node.onRemoved;
  node.onRemoved = function() {
    if (this.__h3DashboardV3Timer) {
      clearInterval(this.__h3DashboardV3Timer);
      this.__h3DashboardV3Timer = null;
    }
    const index = this.widgets?.indexOf(domWidget) ?? -1;
    if (index >= 0) this.widgets.splice(index, 1);
    domWidget.onRemove?.();
    panel.remove();
    this.__h3DashboardV3 = false;
    this.__h3DashboardV3Panel = null;
    this.__h3DashboardV3Refresh = null;
    return originalOnRemoved?.apply(this, arguments);
  };
}

export function applyDashboard(node) {
  const dashboard = Number(node?.id) === NODE_IDS.dashboard ? node : byId(node, NODE_IDS.dashboard);
  if (!dashboard || dashboard.properties?.[GATE] !== true) return;
  try {
    if (!dashboard.__h3DashboardV3) internalizeSources(dashboard, false);
    installDashboard(dashboard);
  } catch (error) {
    console.error("[H3 v024] Dashboard 安装失败", error);
    dashboard.title = `【H3 控制台加载失败】${error?.message || error}`;
    internalizeSources(dashboard, false);
    dashboard.graph?.setDirtyCanvas?.(true, true);
  }
}

app.registerExtension({
  name: "H3.Workflow.FoolproofV3Dashboard",
  beforeRegisterNodeDef(nodeType) {
    const onAdded = nodeType.prototype.onAdded;
    nodeType.prototype.onAdded = function () {
      const result = onAdded?.apply(this, arguments);
      setTimeout(() => applyDashboard(this), 0);
      return result;
    };
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      setTimeout(() => applyDashboard(this), 0);
      return result;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => applyDashboard(this), 0);
      setTimeout(() => applyDashboard(this), 150);
      return result;
    };
  },
  afterConfigureGraph() {
    const dashboard = (app.graph?._nodes || []).find((node) => Number(node.id) === NODE_IDS.dashboard && node.properties?.[GATE] === true);
    if (dashboard) {
      applyDashboard(dashboard);
      setTimeout(() => applyDashboard(dashboard), 250);
      setTimeout(() => applyDashboard(dashboard), 1000);
    }
  },
});
