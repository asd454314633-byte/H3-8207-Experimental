/**
 * H3 v024 控制台状态机（纯数据 + 纯函数，不碰 DOM、不碰 node.mode）。
 *
 * 职责边界：
 * - 所有中文映射表、推荐值、步数路由表、种子映射表只放这里，其它文件 import，禁止在
 *   dashboard.js 里再写一份字面量（共享约定 2）。
 * - 红线 7：统一的是「用户入口」，不是「执行数据源」；四模式步数分别落在
 *   N750 / N920 / N942 / N880，物理隔离。
 * - 红线 9：种子不重写随机算法，只写回 N142 原生值。
 */

// ---- 底层 selector 的真实 enum 值（nodes.py 已同步两档收口，2026-09-29）----
export const H3_GEN_REF = "多参考图（REF2VA）";
export const H3_GEN_FL = "文生/单图/首尾帧（FL2VA）";

// 生产两档（BACKEND_SELECTOR_FINAL_CONVERGENCE_01）
export const H3_BACKEND_STABLE8 = "稳定多参考8步";   // turbo_8step（00029 健康路线，208 patches）
export const H3_BACKEND_PDD8 = "PDD多参考8步";       // MiniMaxH3PDDAccApply（308 patches）
export const H3_BACKEND_NATIVE20 = "Native Ref2VA 20步诊断";
// 旧值仅作旧图兼容（枚举已移除=生产 UI 隐藏；分支节点保留 rollback）
export const H3_BACKEND_ORIGINAL = "原版 Ref2VA（默认 / 画质优先 / 高速平衡）";
export const H3_BACKEND_VSA = "VSA Ref2VA（4步）";
export const H3_BACKEND_OFFICIAL = "PDD Ref2VA 8步（V28.1 主力候选）";

export const H3_ATTENTION_STANDARD = "标准";
export const H3_ATTENTION_INT8 = "内置 INT8";

export const H3_IMAGE_T2V = "文生视频（不用图）";
export const H3_IMAGE_I2V = "单图生视频";
export const H3_IMAGE_FLF = "首尾帧生视频";

// ---- 用户可见中文标签（映射，不改变底层值）----
export const H3_BACKEND_LABEL = {
  [H3_BACKEND_NATIVE20]: "Native Ref2VA 20步诊断",
  [H3_BACKEND_STABLE8]: "稳定多参考8步",
  [H3_BACKEND_PDD8]: "PDD多参考8步",
  [H3_BACKEND_OFFICIAL]: "PDD多参考8步",   // 旧图兼容：同指 PDD 链
  [H3_BACKEND_ORIGINAL]: "原版多参考8步（已收敛，请选稳定8步）",
  [H3_BACKEND_VSA]: "稀疏高速多参考4步（已退役）",
};

export const H3_IMAGE_LABEL = {
  [H3_IMAGE_T2V]: "文生视频",
  [H3_IMAGE_I2V]: "单图视频",
  [H3_IMAGE_FLF]: "首尾帧视频",
};

// ---- 一采步数：一个入口，四个真实源（红线 7/8）----
export const H3_RECOMMENDED_STEPS = { original: 8, vsa: 4, official: 8, fl2va: 4, native20: 20 };

export const H3_STEP_TARGETS = {
  native20: { nodeId: 1011, widget: "steps" },
  original: { nodeId: 750, widget: "value" },   // INTConstant → N871 → N124.steps
  vsa: { nodeId: 920, widget: "steps" },        // BasicScheduler
  official: { nodeId: 942, widget: "steps" },   // BasicScheduler
  fl2va: { nodeId: 880, widget: "steps" },      // BasicScheduler（FastH3）
};

// ---- 比例：用户可见中文 → N115 英文原值 ----
export const H3_RATIO_ZH = [
  ["16:9 横屏", "16:9 (Widescreen)"],
  ["9:16 竖屏", "9:16 (Portrait Widescreen)"],
  ["1:1 方形", "1:1 (Square)"],
  ["4:3 标准", "4:3 (Standard)"],
  ["3:4 竖版标准", "3:4 (Portrait Standard)"],
  ["3:2 横版照片", "3:2 (Photo)"],
  ["2:3 竖版照片", "2:3 (Portrait Photo)"],
  ["21:9 超宽屏", "21:9 (Ultrawide)"],
];

// ---- 种子：中文按钮 → N142 control_after_generate 原生英文值 ----
export const H3_SEED_CONTROL_ZH = [
  ["固定不变", "fixed"],
  ["自动递增", "increment"],
  ["自动递减", "decrement"],
  ["每次随机", "randomize"],
];

// ---- Phase D2【生成过程预览】开关（N691 原生 mode 代理，非第二套 Preview 算法）----
// 关闭 = N691.mode=BYPASS(4)：wrapper 不执行、tiny-VAE 不解码、不发送 kj_preview_override；
// 开启 = N691.mode=ACTIVE(0)。唯一持久化事实源 = N159.properties.h3_preview_enabled。
export const H3_PREVIEW_ON = "开启";
export const H3_PREVIEW_OFF = "关闭";
export const H3_PREVIEW_VALUES = [H3_PREVIEW_OFF, H3_PREVIEW_ON];
export const H3_PREVIEW_WIDGET = "生成过程预览";
export const H3_PREVIEW_NODE_ID = 691;

// ---- 模式判定：从底层 selector 读出当前叶子模式 key ----
// 返回 'original' | 'vsa' | 'official' | 'fl2va'
// 两档收口（2026-09-29）：稳定8步与 PDD8步都走 official 键（步数目标 N942 / 推荐 8 步）
export function consoleModeKey(graph, byId) {
  const gen = String(byId(647)?.widgets?.find((w) => w.name === "生成模式")?.value ?? "");
  if (gen === H3_GEN_FL) return "fl2va";
  const backend = String(byId(931)?.widgets?.find((w) => w.name === "Ref2VA 后端")?.value ?? "");
  if (backend === H3_BACKEND_NATIVE20) return "native20";
  if (backend.startsWith("稳定") || backend.startsWith("官方") || backend.startsWith("PDD")) return "official";
  if (backend.startsWith("VSA")) return "vsa";
  return "original";
}

// ---- 帧数只读：唯一事实源 = N131 表达式 ----
// 后端用 Python simple_eval + MATH_FUNCTIONS 求值，这里用受控 new Function 复刻同一函数集，
// 白名单校验通过后才求值；失败返回 null（显示「—」），绝不手写第二套公式。
const MATH_FUNCS = {
  // Python round 为银行家舍入（恰为 .5 时向偶数取整），与后端 simple_eval 一致
  round: (v) => {
    const f = Math.floor(v);
    const d = v - f;
    if (d < 0.5) return f;
    if (d > 0.5) return f + 1;
    return f % 2 === 0 ? f : f + 1;
  },
  max: (...a) => Math.max(...a),
  min: (...a) => Math.min(...a),
  abs: (v) => Math.abs(v),
  floor: (v) => Math.floor(v),
  ceil: (v) => Math.ceil(v),
  sqrt: (v) => Math.sqrt(v),
  pow: (a, b) => Math.pow(a, b),
  log: (v) => Math.log(v),
  log2: (v) => Math.log2(v),
  log10: (v) => Math.log10(v),
  sin: (v) => Math.sin(v),
  cos: (v) => Math.cos(v),
  tan: (v) => Math.tan(v),
};
const MATH_FUNC_NAMES = Object.keys(MATH_FUNCS).join("|");

export function readFrameCount(expr, seconds) {
  try {
    if (typeof expr !== "string" || expr.length > 160) return null;
    // 白名单：把已知函数名与单字母变量（a~z，即后端 autogrow 输入名）替换后，
    // 剩余字符只允许 数字 / 运算符 / 逗号 / 点 / 空格 / %。
    const sanitized = expr
      .replace(new RegExp(`\\b(${MATH_FUNC_NAMES})\\b`, "g"), "F")
      .replace(/\b[a-z]\b/g, "1");
    if (!/^[0-9+\-*/().,%\sF]+$/.test(sanitized)) return null;
    const fn = new Function("a", "b", ...Object.keys(MATH_FUNCS), `return (${expr});`);
    const value = fn(seconds, 0, ...Object.values(MATH_FUNCS));
    return Number.isFinite(value) ? Math.round(value) : null;
  } catch {
    return null;
  }
}
