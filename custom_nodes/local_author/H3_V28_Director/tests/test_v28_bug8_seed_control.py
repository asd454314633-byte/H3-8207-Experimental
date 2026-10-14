# -*- coding: utf-8 -*-
"""P11 BUG-8 —— 种子控制（“生成后”下拉）被静默写空缺陷锁定测试。

被锁定的产品缺陷（BUG-8 / P11 TEST6-UI）：
  h3_director_v28.js 面板在【生成当前段】/【重新生成】提交前，必须先把 SeedNode
  的“生成后控制”widget 钉成固定值，否则 ComfyUI 会在提交时刻重新随机种子，
  “同种子 / 同种子 reroll”的整套状态机契约随之塌掉。旧代码从 `control.values`
  读下拉候选清单——

8197 实机前端测得的事实（本测试要编码的就是它）：
  ComfyUI 1.52.7 真实前端里 SeedNode 只有两个 widget：
      {name:"seed",  type:"number"}
      {name:"fixed", type:"combo", value:"randomize"}
  且 `widget.values` 是 **undefined**，选项清单住在 `widget.options.values`
  = ["fixed","increment","decrement","randomize"]。后果链：旧 fixedSeedOption()
  里 `(undefined || [])` → [].find() → undefined → setWidget() 当时对 combo 没有
  任何防护，把 undefined 赋给 widget、触发回调并**返回 true**——面板报“写入
  成功”，实际把种子控制刷成了空值。旧台架给 stub widget 配的是 `values` 数组，
  所以 TEST5-UI 72/72 全绿也抓不到这一条。

修复面（已进面板源码，本文件只读、不改）：
  * h3_director_v28.js:48-51   SEED_CONTROL_VALUES（种子控件全部合法取值集合）；
  * h3_director_v28.js:617-632 seedControlWidget() 先按“当前取值本身属于随机化
    枚举”定位控件——当前值永远可读，与 V27
    h3_workflow_helpers/web/h3_foolproof_v3_dashboard.js:419-432 同一手法；
  * h3_director_v28.js:641-644 seedControlOptions() 统一读
    options?.values ?? values ?? []；
  * h3_director_v28.js:645-651 fixedSeedOption() 清单确实为空时回落到字面量
    "fixed"，而不是 undefined；
  * h3_director_v28.js:70-87   setWidget() 拒绝把 null/"" 写进 combo 并返回 false。

测试方式：绝不在测试里重新实现面板函数。取面板**真实源码文本**——从两条
import 之后切到 fixedSeedOption 收尾大括号（按字面量锚点 + 花括号计数器定位，
不硬编码行号），拼上 stub 前导写成临时 .mjs，交给 node 执行、打印 JSON 判决，
Python 侧逐条断言。node 不可得时才降级为对 JS 文本的静态不变量断言（弱但真）；
判决 JSON 带 mode 字段，测试会断言实际走的是哪条路，杜绝“因没走到而空过”。
全程离线、无 HTTP、无浏览器、无 GPU，落盘只进 tempfile.TemporaryDirectory()，
对 <COMFYUI_DIR>\\... 严格只读。

运行方式与邻居测试完全一致（在包的 tests/ 目录里）：
     cd <COMFYUI_DIR>\\ComfyUI_H3_V27_Lab\\custom_nodes\\H3_V28_Director\\tests
     <COMFYUI_DIR>\\ComfyUI_H3_V26_Lab\\venv\\Scripts\\python.exe -m unittest -v \\
         test_v28_bug8_seed_control.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402

# 与 test_v28_bug6_compiled_roundtrip.py 完全一致的路径解析：定位面板 JS 走 B.PKG_DIR。
JS = (B.PKG_DIR / "web" / "h3_director_v28.js").read_text(encoding="utf-8")

# 切片起点锚：第二条（最后一条）import 行的字面量。终点锚：fixedSeedOption( 的
# 收尾大括号——用花括号计数器找，绝不写死行号（面板在 BUG-1..8 之间已被改过多次，
# 任何行号锚点都是过期信息）。
LAST_IMPORT_ANCHOR = 'import { compileReferenceGraph, initializeReferenceWorkflow, referenceState } from "/extensions/h3_workflow_helpers/h3_workflow_registry_core.js";'


def _func_src(js: str, header: str) -> str:
    """返回 `header`（形如 "function name("）所在函数从声明到收尾大括号的源码。

    朴素花括号计数对本文件已足够：被切的这批小工具函数体内没有任何含花括号的
    字符串字面量（逐函数肉眼核对过），fixedSeedOption/seedControlWidget 等全是
    纯逻辑代码。
    """
    start = js.index(header)
    i = js.index("{", start)
    depth = 0
    for j in range(i, len(js)):
        ch = js[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
    raise AssertionError(f"花括号未闭合，定位函数失败: {header}")


def _slice_helpers_region(js: str) -> str:
    """import 之后 → fixedSeedOption 收尾。常量+图/widget 小工具+种子三函数。"""
    imp = js.index(LAST_IMPORT_ANCHOR)
    start = imp + len(LAST_IMPORT_ANCHOR)
    end_body = _func_src(js[start - 200:], "function fixedSeedOption(")
    return js[start:start + js[start:].index(end_body) + len(end_body)]


SLICE = _slice_helpers_region(JS)
SET_WIDGET_SRC = _func_src(SLICE, "function setWidget(")
SEED_CONTROL_WIDGET_SRC = _func_src(SLICE, "function seedControlWidget(")
SEED_CONTROL_OPTIONS_SRC = _func_src(SLICE, "function seedControlOptions(")
FIXED_SEED_OPTION_SRC = _func_src(SLICE, "function fixedSeedOption(")

# 临时 .mjs 的前导：被剥掉的两条 import 用 stub 顶上。localStorage 也是必需的：
# 切片里 `const state = { projectId: localStorage.getItem(...) }`（面板 :163-171）
# 在模块顶层求值，node 下没有浏览器全局，必须给最小 stub——这正是"切片无顶层
# DOM 交互"的边界所在：除它之外 document./window./fetch 只出现在函数体里。
PRELUDE = '''export const app = { graph: { _nodes: [], change() {} } };
export const api = {};
const localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
'''
EXPORTS = ("\nexport { NODE, OPERATION_DEFAULT, FIXED_SEED_LABELS, SEED_CONTROL_VALUES,\n"
           "  nodes, byId, widget, isNumeric, setWidget, widgetValue,\n"
           "  seedControlWidget, seedControlOptions, fixedSeedOption };\n")

# node 驱动：构造四种 widget 形态（1.52.7 实测形态 / 空清单 / 旧 values 数组形态 /
# setWidget 闸门），全部调用**切片里的真函数**，把结果打成 JSON。
DRIVER = r"""
import { app, setWidget, widget, seedControlWidget, seedControlOptions, fixedSeedOption }
  from "./mod.mjs";

const out = { mode: "node" };
const LEGAL = ["fixed", "increment", "decrement", "randomize"];

// A. 前端 1.52.7 实测形态：无 values 字段，选项在 options.values，当前值 randomize。
function realFrontendSeedNode() {
  return { id: 142, widgets: [
    { name: "seed", type: "number", value: 12345 },
    { name: "fixed", type: "combo", value: "randomize",
      options: { values: LEGAL.slice() } },
  ] };
}
{
  const n = realFrontendSeedNode();
  app.graph._nodes = [n];
  const c = seedControlWidget(n);
  out.A = {
    notNull: !!c,
    controlName: c ? c.name : null,
    isSeedWidget: c === n.widgets[0],
    valuesFieldUndefined: !!c && c.values === undefined,
    option: c ? fixedSeedOption(c) : null,
    optionType: c ? typeof fixedSeedOption(c) : null,
  };
}

// B. 清单彻底拿不到：既无 values 也无 options.values。
{
  const bare = { name: "fixed", type: "combo", value: "randomize" };
  out.B = { option: fixedSeedOption(bare),
            optionType: typeof fixedSeedOption(bare),
            optionsLen: seedControlOptions(bare).length };
}

// C. 旧前端/旧台架形态：候选清单就在 values 数组里，含中文标签「固定不变」。
{
  const legacy = { name: "生成后", type: "combo", value: "随机",
                   values: ["固定不变", "递增", "递减", "随机"] };
  const n = { id: 142, widgets: [{ name: "seed", type: "number", value: 1 }, legacy] };
  app.graph._nodes = [n];
  const c = seedControlWidget(n);
  out.C = { controlIsLegacyWidget: c === legacy,
            optionsFromValuesArray: seedControlOptions(legacy),
            option: fixedSeedOption(legacy) };
}

// D. setWidget 闸门：combo 拒写 undefined 且不动值不触发回调；写 "fixed" 正常放行；
//    数值控件的 NaN 闸门（既有契约，不得被 combo 闸门挤掉）。
{
  let fired = 0, lastCb = "not-called";
  const combo = { name: "fixed", type: "combo", value: "randomize",
                  options: { values: LEGAL.slice() },
                  callback: (v) => { fired += 1; lastCb = v; } };
  const r1 = setWidget(combo, undefined);
  out.D = {
    rejectUndefined: r1,
    valueAfterReject: combo.value,
    firedAfterReject: fired,
    acceptFixed: setWidget(combo, "fixed"),
    valueAfterAccept: combo.value,
    firedAfterAccept: fired,
    callbackSawFixed: lastCb === "fixed",
    rejectNull: setWidget(combo, null),
    valueAfterNull: combo.value,
  };
  let numFired = 0;
  const num = { name: "seed", type: "number", value: 42, callback: () => { numFired += 1; } };
  out.Dnumeric = { rejectNaN: setWidget(num, NaN), valueAfterNaN: num.value, fired: numFired };
}

// E. applyInstruction 的种子段原样重放（面板 :590-600 的同一序列）：先钉控制再写种子。
{
  const n = realFrontendSeedNode();
  app.graph._nodes = [n];
  const seedW = widget(n, "seed");
  const control = seedControlWidget(n);
  let firedWith = null;
  control.callback = (v) => { firedWith = v; };
  const wrote = control ? setWidget(control, fixedSeedOption(control)) : false;
  if (seedW) setWidget(seedW, Number("777"));
  out.E = {
    controlFound: !!control,
    writeOk: wrote,
    value: control ? control.value : null,
    inLegalOptions: LEGAL.includes(control ? control.value : null),
    blanked: !control || control.value == null || control.value === "",
    callbackFired: firedWith !== null,
    callbackValue: firedWith,
    seedValue: seedW.value,
  };
}

console.log(JSON.stringify(out));
"""


def _run_node_driver():
    """写 mod.mjs + driver.mjs 到临时目录，node 执行，返回 (mode, verdict|None, err)。

    node 不可得 -> ("static", None, "")；node 在但驱动失败 -> 抛异常（大声失败，
    绝不静默降级成 static 让门冒充通过）。
    """
    node = shutil.which("node")
    if node is None:
        return "static", None, ""
    with tempfile.TemporaryDirectory(prefix="h3v28_bug8_") as td:
        mod = os.path.join(td, "mod.mjs")
        drv = os.path.join(td, "driver.mjs")
        with open(mod, "w", encoding="utf-8") as f:
            f.write(PRELUDE + SLICE + EXPORTS)
        with open(drv, "w", encoding="utf-8") as f:
            f.write(DRIVER)
        cp = subprocess.run([node, drv], capture_output=True, timeout=120, cwd=td)
        if cp.returncode != 0:
            raise RuntimeError(
                "node 驱动失败（node 在场时本测试绝不允许降级为 static）：\n"
                + cp.stderr.decode("utf-8", errors="replace")[-4000:])
        verdict = json.loads(cp.stdout.decode("utf-8"))
        return "node", verdict, ""


MODE, VERDICT, DRIVER_ERROR = _run_node_driver()
NODE_AVAILABLE = shutil.which("node") is not None

# 各行为用例在 node 缺席时的静态等价物：断言修复面的字面文本确实在真源码里。
# 这组检查本身就是"降级仍是真门"的兑现，node 在场时也会跑（见静态类）。
STATIC_EQUIVALENTS = {
    "A": ('SEED_CONTROL_VALUES.has(String(w.value))', SEED_CONTROL_WIDGET_SRC,
          "1.52.7 形态：seedControlWidget 必须有按当前值语义定位的分支"),
    "B": ('return opts.length ? opts[0] : "fixed";', FIXED_SEED_OPTION_SRC,
          "空清单必须回落字面量 fixed，而不是 undefined"),
    "C": ('control?.options?.values ?? control?.values ?? []', SEED_CONTROL_OPTIONS_SRC,
          "旧 values 数组形态必须仍是 seedControlOptions 的回落读取源"),
    "D": ('String(target.type) === "combo"', SET_WIDGET_SRC,
          "setWidget 必须有 combo 空值拒绝闸门"),
    "E": ('return opts.length ? opts[0] : "fixed";', FIXED_SEED_OPTION_SRC,
          "E 的落点=控制值恒为合法选项；静态面即 B+D 两条字面量"),
}


class Bug8Case(unittest.TestCase):
    """共享：node 判决 + 静态回落的通用断言入口。"""

    def branch(self, key: str):
        """返回判决 JSON 里的第 key 段；node 缺席时先核对静态等价物再返回 None。"""
        text, haystack, why = STATIC_EQUIVALENTS[key][0], STATIC_EQUIVALENTS[key][1], STATIC_EQUIVALENTS[key][2]
        if MODE == "node":
            self.assertIsNotNone(VERDICT.get(key), f"判决 JSON 缺少 {key} 段——驱动没走到该分支")
            return VERDICT[key]
        # 降级模式：弱化但真实的静态面断言，且必须在输出里点名。
        self.assertIn(text, haystack, f"[static 降级] {why}\n缺失文本: {text}")
        print(f"\n[BUG-8] 分支 {key}: mode=static（node 不可得，降级为文本断言: {why}）")
        return None


# --------------------------------------------------------------------------- #
class TestSliceRegionAndMode(Bug8Case):
    """0. 切片本身的不变量：切对了地方、无顶层 DOM 交互、mode 与 node 在场性一致。"""

    def test_slice_covers_constants_and_helpers_only(self):
        for anchor in ("const NODE = {", "const FIXED_SEED_LABELS", "const SEED_CONTROL_VALUES",
                       "function nodes()", "function widget(", "function setWidget(",
                       "function seedControlWidget(", "function fixedSeedOption("):
            self.assertIn(anchor, SLICE, f"切片缺少必须成员 {anchor}——锚点定位已失效")
        self.assertNotIn("import {", SLICE, "切片应已剥掉 import 行")
        # 上界：fixedSeedOption 是切片里最后一个函数，其后的 promptOverride 不得进来。
        self.assertNotIn("promptOverride", SLICE,
                         "切片终点必须是 fixedSeedOption 的收尾大括号，多吃进了后续函数")
        self.assertTrue(SLICE.rstrip().endswith("}"), "切片必须以 } 收尾")

    def test_slice_has_no_top_level_dom_surface(self):
        """顶层不得碰 DOM/提交：document./window. 只允许出现在缩进的函数体里；
        提交/注册入口（queuePrompt、registerExtension）整体不在切片内。

        注意（与任务书的偏差，已在报告注明）：buildPanel 定义在 :251、落在切片
        范围内且只被函数体调用，故不能用"不含 buildPanel 字样"做判据，改用
        registerExtension/queuePrompt 缺席 + 缩进核验 + node 顶层求值成功。
        """
        for line in SLICE.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "*", "/*")):
                continue
            if "document." in line or "window." in line:
                self.assertTrue(line.startswith((" ", "\t")),
                                f"疑似顶层 DOM 访问（未缩进行）: {line!r}")
        self.assertNotIn("registerExtension", SLICE, "注册入口不应进入可执行切片")
        self.assertNotIn("queuePrompt", SLICE, "提交入口不应进入可执行切片")

    def test_mode_matches_node_availability(self):
        """mode 必须如实记录实际执行的路径：有 node 却走了 static == 门禁撒谎。"""
        if NODE_AVAILABLE:
            self.assertEqual(MODE, "node", "shutil.which 找得到 node，判决就必须来自 node 执行")
            self.assertEqual(VERDICT["mode"], "node", "驱动 JSON 自报的 mode 必须与外层一致")
        else:
            self.assertEqual(MODE, "static")
            self.assertIsNone(VERDICT)
        print(f"\n[BUG-8] 本次执行模式: mode={MODE}（node 可得的静态真源断言始终会跑）")


# --------------------------------------------------------------------------- #
class TestFixSurfaceStaticInvariants(Bug8Case):
    """0b. 修复面的文本级不变量——两种模式下都跑，node 缺席时这就是唯一防线。"""

    def test_seed_control_values_set_declared_after_fixed_labels(self):
        self.assertIn("const SEED_CONTROL_VALUES = new Set(", SLICE)
        self.assertLess(SLICE.index("const FIXED_SEED_LABELS"),
                        SLICE.index("const SEED_CONTROL_VALUES"),
                        "SEED_CONTROL_VALUES 按任务书应声明在 FIXED_SEED_LABELS 之后")
        for v in ("fixed", "increment", "decrement", "randomize"):
            self.assertIn(f'"{v}"', SLICE[SLICE.index("const SEED_CONTROL_VALUES"):
                                           SLICE.index("function nodes()")],
                          f"合法取值集合缺少 {v}")

    def test_combo_guard_is_before_assignment_and_returns_false(self):
        guard = SET_WIDGET_SRC.index('String(target.type) === "combo"')
        assign = SET_WIDGET_SRC.index("target.value = value")
        self.assertLess(guard, assign, "combo 空值闸门必须先于赋值，否则值已被刷空")
        seg = SET_WIDGET_SRC[guard:guard + 220]
        self.assertIn("value == null || value === \"\"", seg)
        self.assertIn("return false", seg, "闸门必须 return false，让按钮报写入失败而不是假成功")

    def test_numeric_nan_gate_survives(self):
        self.assertIn("Number.isFinite(value)", SET_WIDGET_SRC,
                      "数值控件 NaN 闸门是既有契约，修 combo 时不得挤掉")


# --------------------------------------------------------------------------- #
class TestARealFrontendShape(Bug8Case):
    """A. 1.52.7 实测形态（无 values、有 options.values）下定位与取值都必须对。"""

    def test_seed_control_widget_returns_combo_not_seed_not_null(self):
        a = self.branch("A")
        if a is None:
            return
        self.assertTrue(a["notNull"], "真实前端形态下 seedControlWidget() 不得返回 null")
        self.assertEqual(a["controlName"], "fixed",
                         "必须定位到 fixed 下拉控件本体（1.52.7 里它就叫 name:'fixed'）")
        self.assertFalse(a["isSeedWidget"], "绝不能把 seed 数值控件误当成生成后控制")
        self.assertTrue(a["valuesFieldUndefined"],
                        "前置事实核对：该形态里 widget.values 必须是 undefined，否则用例 A 退化成 C")

    def test_fixed_seed_option_returns_fixed_string(self):
        a = self.branch("A")
        if a is None:
            return
        self.assertEqual(a["option"], "fixed")
        self.assertEqual(a["optionType"], "string", "绝不能再返回 undefined（BUG-8 之因）")


class TestBEmptyOptionList(Bug8Case):
    """B. 清单彻底为空：fixedSeedOption 仍必须给出 "fixed"。"""

    def test_empty_list_falls_back_to_literal_fixed(self):
        b = self.branch("B")
        if b is None:
            return
        self.assertEqual(b["optionsLen"], 0, "fixture 必须确实造出双缺（values/options.values 皆无）形态")
        self.assertEqual(b["option"], "fixed")
        self.assertNotIn(b["option"], (None, "", "undefined"))
        self.assertEqual(b["optionType"], "string")


class TestCLegacyValuesShape(Bug8Case):
    """C. 旧形态（values 数组含「固定不变」）行为不得回退。"""

    def test_legacy_values_array_still_honoured(self):
        c = self.branch("C")
        if c is None:
            return
        self.assertTrue(c["controlIsLegacyWidget"], "旧形态下也必须定位到那个 combo 而非 seed")
        self.assertEqual(c["optionsFromValuesArray"], ["固定不变", "递增", "递减", "随机"],
                         "options.values 缺失时 seedControlOptions 必须回落到 values 数组")
        self.assertEqual(c["option"], "固定不变",
                         "旧标签「固定不变」必须原样返回（含中文标签的中英双认）")


class TestDSetWidgetGuards(Bug8Case):
    """D. setWidget：combo 拒写空值（不动值、不触发回调）；合法值放行；NaN 闸门保留。"""

    def test_combo_rejects_undefined_without_side_effects(self):
        d = self.branch("D")
        if d is None:
            return
        self.assertIs(d["rejectUndefined"], False,
                      "BUG-8 核心：往 combo 写 undefined 必须判 false，而不是刷空后回 true")
        self.assertEqual(d["valueAfterReject"], "randomize", "拒绝路径不得改动原值")
        self.assertEqual(d["firedAfterReject"], 0, "拒绝路径不得触发 callback（避免图被标脏）")
        self.assertIs(d["rejectNull"], False, "null 与 undefined 同罪")
        self.assertEqual(d["valueAfterNull"], "fixed" if d["acceptFixed"] else d["valueAfterReject"])

    def test_combo_accepts_legal_fixed(self):
        d = self.branch("D")
        if d is None:
            return
        self.assertIs(d["acceptFixed"], True)
        self.assertEqual(d["valueAfterAccept"], "fixed")
        self.assertEqual(d["firedAfterAccept"], 1, "成功路径必须且只触发一次 callback")
        self.assertTrue(d["callbackSawFixed"], "回调收到的值应为 fixed")

    def test_numeric_widget_still_rejects_nan(self):
        if MODE == "node":
            dn = VERDICT["Dnumeric"]
            self.assertIs(dn["rejectNaN"], False)
            self.assertEqual(dn["valueAfterNaN"], 42, "NaN 写入不得改动数值控件原值")
            self.assertEqual(dn["fired"], 0, "NaN 被拒不触发回调")
        else:
            self.assertIn("Number.isFinite(value)", SET_WIDGET_SRC)
            print("\n[BUG-8] 分支 Dnumeric: mode=static，仅断言 NaN 闸门文本")


class TestECommitContract(Bug8Case):
    """E. 全链意义务：applyInstruction 种子段重放后，控制值必落在合法选项清单里。"""

    def test_after_apply_style_write_seed_control_is_never_blank(self):
        e = self.branch("E")
        if e is None:
            return
        self.assertTrue(e["controlFound"], "种子段第一步就是定位控制控件，找不到则全案无意义")
        self.assertTrue(e["writeOk"], "setWidget(control, fixedSeedOption(control)) 必须回 true")
        self.assertEqual(e["value"], "fixed")
        self.assertTrue(e["inLegalOptions"],
                        "面板可提交的前提：控制值必须是 options 清单成员（旧代码在此处会留下 undefined）")
        self.assertFalse(e["blanked"], "BUG-8 终态判据：提交前种子控制绝不允许为空值")
        self.assertTrue(e["callbackFired"])
        self.assertEqual(e["callbackValue"], "fixed", "回调收到的必须是最终值 fixed")
        self.assertEqual(e["seedValue"], 777, "顺带核对：种子本体照常写入")


if __name__ == "__main__":
    unittest.main(verbosity=2)
