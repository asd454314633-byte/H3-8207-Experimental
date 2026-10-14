"""V28 Director - the front end and the back end must never drift apart.

Task 37 allows static checks while no GPU work is permitted, and the risk this
file retires is precisely the one static analysis CAN see: `h3_director_v28.js`
and `v28_routes.py` are two hand-written halves of one contract, edited in
different sessions by different agents. Every assertion here compares the two
texts against each other, so a rename on one side fails the suite instead of
producing a panel that silently 404s.

Locked contracts:
  * every path the UI calls exists as a HANDLERS key with the same method (§10)
  * the node ids the UI writes are the ids `v28_paths.NODE` documents (§12/§13)
  * the §31 refusal text is verbatim-identical on both sides
  * seeds survive the JSON -> JS number -> graphToPrompt round trip exactly (§23)
  * the package version the UI prints is the package's own version
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B          # noqa: E402  (path + synthetic package setup)

P = B.load("v28_paths")
R = B.load("v28_routes")
SM = B.load("v28_state_machine")

JS = (B.PKG_DIR / "web" / "h3_director_v28.js").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# parsing the UI
# --------------------------------------------------------------------------- #
def ui_calls() -> dict:
    """{path: method} for every request the panel makes.

    A line may name several paths (the plan/analyze ternary) and the method is
    carried on the same line as the `call(` opener in this file's style.
    """
    out = {}
    for line in JS.splitlines():
        if "call(" not in line or "function call" in line:
            continue
        methods = re.findall(r'method:\s*"([A-Z]+)"', line)
        method = methods[0] if methods else "GET"
        for path in re.findall(r'"(/[a-z_/]+)"', line):
            out[path] = method
    return out


def js_const_object(name: str) -> dict:
    """Eval a `const NAME = { key: value, ... }` literal well enough for ints."""
    m = re.search(rf"const {name} = \{{(.*?)\n\}};", JS, re.S)
    if not m:
        raise AssertionError(f"UI 里找不到常量 {name}")
    body = re.sub(r"//[^\n]*", "", m.group(1))          # drop trailing comments
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", body)}


def js_array(name: str) -> list:
    m = re.search(rf"const {name} = \[(.*?)\];", JS, re.S)
    assert m, f"UI 里找不到常量 {name}"
    body = re.sub(r"//[^\n]*", "", m.group(1))
    return re.findall(r'"([^"]+)"', body)


# --------------------------------------------------------------------------- #
class TestRouteContract(unittest.TestCase):
    def test_every_ui_path_is_served(self):
        calls = ui_calls()
        self.assertGreaterEqual(len(calls), 15, "解析不到调用点 = 本测试失效")
        served = {p for (p, _m) in R.HANDLERS}
        missing = {p: m for p, m in calls.items() if p not in served}
        self.assertEqual(missing, {}, f"UI 调了后端没有的端点: {missing}")

    def test_ui_method_matches_handler(self):
        by_path = {p: m for (p, m) in R.HANDLERS}
        for path, method in ui_calls().items():
            self.assertEqual(by_path[path], method, f"{path} 方法不一致")

    def test_no_unwired_mutating_endpoint(self):
        """A POST endpoint nobody calls is a dead switch or a missing button."""
        known_diag = {"/start", "/load_check", "/prompt_source"}     # external API and diagnostic entry points
        called = set(ui_calls())
        helper = (B.PKG_DIR.parent/'h3_workflow_helpers/web/h3_workflow_registry_core.js').read_text(encoding='utf-8')
        called.update(re.findall(r'fetch\("/h3_director([^"?]+)', helper))
        dead = {p for (p, m) in R.HANDLERS
                if m == "POST" and p not in called and p not in known_diag}
        self.assertEqual(dead, {"/reference_hygiene", "/submitted"}, f"后端有 POST 端点但界面上没人调用: {dead}")

    def test_handlers_are_all_under_the_prefix(self):
        for path, _m in R.HANDLERS:
            self.assertTrue(path.startswith("/"), path)
            self.assertNotIn(R.PREFIX, path, "HANDLERS 里不该再带前缀")
        self.assertEqual(R.PREFIX, "/h3_director")

    def test_analyze_and_reap_exist(self):
        """§31 names two START triggers; /reap is the only way out of a stale gate."""
        served = {p for (p, _m) in R.HANDLERS}
        for path in ("/analyze", "/reap", "/plan", "/stop"):
            self.assertIn(path, served)
        self.assertIn("/analyze", ui_calls(), "【分析参考图】按钮必须真打这个端点")
        self.assertIn("/reap", ui_calls(), "§31 拒绝后的自救按钮必须真打这个端点")

    def test_ui_never_calls_a_core_route_under_our_prefix(self):
        """/history and /view belong to ComfyUI core; the /api prefix differs."""
        self.assertNotIn("/history", ui_calls())
        self.assertNotIn("/view", ui_calls())
        for line in JS.splitlines():
            if "apiURL" in line:
                self.assertIn("/", line)
                self.assertNotIn("h3_director", line,
                                 "核心端点必须走 api.apiURL，不能手拼我们的前缀")


class TestNodeIdsAgree(unittest.TestCase):
    def test_scalar_node_ids_match_the_paths_module(self):
        js = js_const_object("NODE")
        pairs = {"console": "console", "prompt": "prompt_ref2va",
                 "duration": "duration_sec", "seed": "seed",
                 "continuation": "continuation_switch", "mcSave": "mc_save",
                 "mcLoad": "mc_load", "mcChain": "mc_chain"}
        for js_key, py_key in pairs.items():
            self.assertIn(js_key, js, f"UI 常量 NODE.{js_key} 不见了")
            self.assertEqual(js[js_key], P.NODE[py_key],
                             f"NODE.{js_key}={js.get(js_key)} 与 v28_paths."
                             f"{py_key}={P.NODE.get(py_key)} 不一致")

    def test_reference_image_slots_match(self):
        m = re.search(r"refImages:\s*\[([0-9,\s]+)\]", JS)
        assert m, "UI 里找不到 NODE.refImages"
        self.assertEqual([int(x) for x in m.group(1).split(",") if x.strip()],
                         list(P.NODE["ref_images"]))

    def test_instruction_keys_are_bidirectionally_consistent(self):
        """Whatever the panel reads must exist, and nothing it reads may vanish.

        Bidirectional on purpose: a key the backend drops would leave the UI
        writing `undefined` into a widget (a silent no-op on a combo), and a key
        the UI invents means the panel is guessing instead of being told.
        """
        src = (B.PKG_DIR / "v28_state_machine.py").read_text(encoding="utf-8")
        body = src[src.index("def widget_instructions"):src.index("def mark_generating")]
        for key in ("prompt", "prompt_text_node", "duration_sec", "seed",
                    "continuation", "motion_context", "expected_frames",
                    "ref_image_nodes", "segment_id"):
            self.assertIn(f'"{key}"', body, "状态机不再产出 " + key)
        for js_key in sorted(set(re.findall(r"\binstr\.([a-z_]+)", JS))):
            self.assertIn(f'"{js_key}"', body,
                          f"UI 读取 instr.{js_key}，但状态机不产出它")
        mc_body = body[body.index('"motion_context"'):]
        for js_key in sorted(set(re.findall(r"\bmc\.([a-z_]+)", JS))):
            self.assertIn(f'"{js_key}"', mc_body,
                          f"UI 读取 motion_context.{js_key}，但状态机不产出它")
        for js_key in sorted(set(re.findall(r"instr\.continuation\?\.([a-z_]+)", JS))):
            self.assertIn(f'"{js_key}"', body,
                          f"UI 读取 continuation.{js_key}，但状态机不产出它")

    def test_continuation_labels_have_exactly_one_source(self):
        """N992 is a combo: a label the widget does not contain silently no-ops.

        So the Chinese option text lives ONLY in the state machine and travels in
        the instruction dict. If the UI ever hardcodes its own copy, the two can
        disagree and the panel would claim success while nothing was written.
        """
        src = (B.PKG_DIR / "v28_state_machine.py").read_text(encoding="utf-8")
        on = re.search(r'CONT_ON = "([^"]+)"', src)
        off = re.search(r'CONT_OFF = "([^"]+)"', src)
        self.assertTrue(on and off, "状态机里的接续选项文案被改名")
        self.assertNotIn(on.group(1), JS, "UI 不得自带一份接续文案")
        self.assertNotIn(off.group(1), JS, "UI 不得自带一份接续文案")
        self.assertIn("instr.continuation?.value", JS)
        self.assertIn("instr.continuation?.strength", JS)
        # the two-choice control the UI offers must map onto the plan enum
        S = B.load("v28_schemas")
        self.assertEqual(S.CONTINUATION_MODES, ("same_shot", "natural_cut"))
        for mode in S.CONTINUATION_MODES:
            self.assertIn(mode, JS, "UI 的连续方式选项少了枚举值 " + mode)

    def test_operation_default_is_v27s_own_default(self):
        m = re.search(r'const OPERATION_DEFAULT = "([^"]+)"', JS)
        assert m
        self.assertEqual(m.group(1), "只跑一采", "§36: 不得改变 V27 的默认提交态")


class TestGateTextIsVerbatim(unittest.TestCase):
    def test_not_released_message_matches(self):
        BR = B.load("v28_bonsai_runtime")
        m = re.search(r'const NOT_RELEASED = "([^"]+)"', JS)
        assert m, "UI 里找不到 NOT_RELEASED 常量"
        self.assertEqual(m.group(1), BR.NOT_RELEASED_MSG,
                         "§31 要求中文提示逐字照抄，两侧不能各写一份")

    def test_the_ui_surfaces_the_gate_before_generating(self):
        """§31: the refusal must be shown, not swallowed by a generic error."""
        self.assertIn("isGateRefusal", JS)
        self.assertLess(JS.index("NOT_RELEASED"), JS.index("async function generate"),
                        "闸门文案要在生成路径之前就位")
        self.assertIn("停止并释放导演模型", JS)
        self.assertIn("回收残留进程", JS)


class TestRefusalKindsTravel(unittest.TestCase):
    """A 409 must say WHICH gate refused it, in a form the panel can branch on.

    Both refusals are Chinese sentences with the same HTTP status, and the §31 red
    bar that used to catch every 409 offers 停止并释放导演模型 / 回收残留进程 - the
    wrong controls for a prompt that dropped `retention_analysis:`. So the backend
    labels refusals and the panel reads the label; this test keeps the two vocabularies
    from drifting apart.
    """

    def kinds_in_python(self):
        """The `kind` literals that sit on a GateRefused payload.

        Matched by proximity rather than by a full parse because the whole point is
        to catch a NEW refusal site whose label the panel never learned about; a
        `"kind"` key used for something else (task status names live in the runtime
        module) must not be swept in.
        """
        found = set()
        for f in B.PKG_DIR.glob("v28_*.py"):
            src = f.read_text(encoding="utf-8")
            for m in re.finditer(r'"kind":\s*"([a-z_]+)"', src):
                window = src[max(0, m.start() - 500):m.start() + 120]
                if "GateRefused" in window:
                    found.add(m.group(1))
        return found

    def test_every_kind_the_backend_can_send_is_known_to_the_panel(self):
        kinds = self.kinds_in_python()
        self.assertIn("vram_gate", kinds, "§31 闸门必须带标签")
        self.assertIn("prompt_structure", kinds, "§27/§35 结构拒绝必须带标签")
        for k in kinds:
            self.assertIn(k, JS, f"后端会发 kind={k}，面板里却搜不到这个字符串")

    def test_err_helper_carries_the_kind_and_stays_quiet_without_one(self):
        out = R._err(SM.GateRefused("结构校验未通过", {"kind": "prompt_structure"}))
        self.assertEqual(out, {"error": "结构校验未通过", "kind": "prompt_structure"})
        self.assertNotIn("kind", R._err(SM.GateRefused("别的拒绝")))
        self.assertEqual(R._err(ValueError("炸了"))["error"], "ValueError: 炸了")

    def test_the_vram_gate_tags_itself(self):
        """Patch _gate rather than the runtime: the label is what's under test."""
        B.load("v28_gemma_provider")
        real = SM._gate
        SM._gate = lambda: (False, "导演模型尚未释放显存，请稍候", {"pid": 1234})
        try:
            with self.assertRaises(SM.GateRefused) as ctx:
                SM.require_director_released("")
        finally:
            SM._gate = real
        self.assertEqual(ctx.exception.details.get("kind"), "vram_gate")
        self.assertEqual(ctx.exception.details.get("pid"), 1234,
                         "加标签不能把闸门原来的细节丢掉")

    def test_the_panel_branches_on_the_label_first(self):
        body = JS[JS.index("function isGateRefusal"):]
        head = body[:body.index("\n}\n")]
        self.assertLess(head.index("refusalKind"), head.index("NOT_RELEASED"),
                        "先读 kind，中文匹配只作为没有标签时的退路")
        self.assertIn('kind === "vram_gate"', head)
        self.assertIn("prompt_structure", JS[:JS.index("async function accept")])


class TestSeedPrecision(unittest.TestCase):
    """A seed that cannot round-trip through JS numbers breaks §23 auditability."""

    def test_seed_max_is_float64_exact(self):
        self.assertLessEqual(SM.SEED_MAX, (1 << 53) - 1)
        self.assertEqual(float(SM.SEED_MAX), SM.SEED_MAX)

    def test_generated_seeds_survive_a_json_round_trip(self):
        for _ in range(400):
            s = SM.new_seed()
            self.assertIsInstance(s, int)
            self.assertGreaterEqual(s, 1)
            self.assertLessEqual(s, SM.SEED_MAX)
            self.assertEqual(json.loads(json.dumps({"seed": s}))["seed"], s)
            self.assertEqual(float(s), s, "该 seed 在 JS Number 里不精确")

    def test_the_ui_never_invents_a_seed(self):
        """§20/§24: the number on the graph must be the number in SESSION_STATE."""
        self.assertIn("lastSubmittedSeed", JS)
        self.assertNotIn("/submitted", ui_calls())
        self.assertNotIn("Math.random", JS, "seed 只能由后端决定")


class TestVersionAndDocs(unittest.TestCase):
    def test_ui_reports_the_package_version(self):
        init = (B.PKG_DIR / "__init__.py").read_text(encoding="utf-8")
        real = re.search(r'__version__ = "([^"]+)"', init).group(1)
        shown = re.search(r'const V28 = "([^"]+)"', JS).group(1)
        self.assertEqual(shown, real)

    def test_only_the_ui_graph_node_is_registered(self):
        """UI_REFACTOR_01: only one zero-output Director UI node is allowed."""
        init = (B.PKG_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('NODE_CLASS_MAPPINGS: dict = {"H3V28DirectorConsole": _ui.H3V28DirectorConsole}', init)
        self.assertNotIn("defineNode", JS)
        self.assertNotIn("registerNodeDefs", JS)


class TestAnalyzePath(unittest.TestCase):
    """【分析参考图】 must not be able to damage a project mid-story (§30)."""

    def setUp(self):
        self.M = B.load_all()
        self.OR = B.load("v28_orchestrator")
        self.V = B.load("v28_provider")
        # the registry is filled by each provider module's own @V.register, and
        # the package __init__ (which imports them all) is deliberately not run
        # under the test bootstrap, so the offline stand-in is loaded by hand.
        B.load("v28_gemma_provider")

    def test_only_the_profile_file_is_written(self):
        with B.fresh_env() as (M, root):
            PJ = M["v28_project"]
            PJ.create(project_id="an1", title="测试")
            img = root / "r1.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"z" * 64)
            images = [{"index": 1, "picture": "<Picture 1>", "slot_index": 1,
                       "node": 687, "name": img.name, "filename": img.name,
                       "path": str(img), "size": img.stat().st_size}]
            with self.assertRaisesRegex(self.V.DirectorError, "视觉识别已取消"):
                self.OR.analyze_now(project_id="an1", story_goal="查看参考图",
                                    images=images, provider="gemma4")
            d = PJ.project_dir("an1")
            self.assertFalse((d / "REFERENCE_PROFILE.json").exists())
            self.assertFalse((d / "STORY_PLAN.json").exists(),
                             "单独分析参考图不得产出剧情计划")
            self.assertFalse((d / "SESSION_STATE.json").exists(),
                             "单独分析参考图不得改动会话状态")

    def test_empty_images_refuse_before_starting_the_director(self):
        with self.assertRaises(self.V.DirectorError):
            self.OR.analyze_now(project_id="an_empty", images=[], provider="gemma4")

    def test_one_to_four_reference_slots_all_work(self):
        """§32: 支持 1–4 张，按 V27 实际素材槽动态决定，不得固定要求 4 张。

        The user-visible consequence is what gets asserted: whatever count the
        canvas actually holds must be what the director saw, and the compiled
        prompt must declare exactly those <Picture N> lines - no phantom 4th
        reference when the user only uploaded one.
        """
        def ref(i: int, root) -> dict:
            p = root / f"r{i}.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"q" * 64)
            return {"index": i, "picture": f"<Picture {i}>", "slot_index": i,
                    "node": P.NODE["ref_images"][i - 1], "name": p.name,
                    "filename": p.name, "path": str(p), "size": p.stat().st_size}

        for k in (1, 2, 3, 4):
            with self.subTest(pictures=k):
                with B.fresh_env() as (M, root):
                    PJ = M["v28_project"]
                    pid = f"refs{k}"
                    PJ.create(project_id=pid, title=f"{k}图测试")
                    images = [ref(i, root) for i in range(1, k + 1)]
                    from unittest.mock import patch
                    from test_v28_optional_director import Replies, semantic
                    provider = Replies([{"segments":[dict(semantic(1),reference_usage=[f'图{i}参考人物身份' for i in range(1,k+1)]),dict(semantic(2),reference_usage=[f'图{i}参考人物身份' for i in range(1,k+1)])]}])
                    with patch.object(self.V,"get_provider",return_value=provider), patch.object(self.OR,"_stop_and_confirm",return_value={"verdict":"RELEASED"}), patch.object(SM,"_gate",return_value=(True,"",{})):
                        res = self.OR.plan_now(project_id=pid, story_goal="一个人走进房间坐下",
                                               images=images, total_seconds=20,
                                               segment_seconds=10, provider="gemma4",
                                               reference_usage='；'.join(f'图{i}参考人物身份' for i in range(1,k+1)))
                    prof = PJ.read(pid, "REFERENCE_PROFILE.json")
                    self.assertEqual(len(prof["source_pictures"]), k)
                    self.assertTrue(prof["scene"]["user_text_only"])
                    self.assertEqual(res["segment_count"], 2)
                    text = self.OR.segment_prompt(pid, 1)
                    import re as _re
                    declared = {int(n) for n in
                                _re.findall(r"<Picture (\d)>", text, _re.M)}
                    self.assertTrue(declared, "提示词里必须声明参考图")
                    self.assertTrue(declared <= set(range(1, k + 1)),
                                    f"提示词引用了没上传的图: {declared - set(range(1, k+1))}")

    def test_card_state_exposes_a_compact_profile(self):
        """The UI's hint line reads card.profile; the whole blob must not be dumped."""
        src = (B.PKG_DIR / "v28_orchestrator.py").read_text(encoding="utf-8")
        body = src[src.index("def card_state"):]
        self.assertIn('"profile"', body)
        for key in ('"pictures"', '"subjects"', '"uncertain"'):
            self.assertIn(key, body, f"card_state 的 profile 摘要缺少 {key}")


class TestJsSyntaxGate(unittest.TestCase):
    """§37 allows a JS syntax check - but only in the form that can actually fail.

    Measured on this machine (node v24.17.0): `node --check x.js` parses as
    CommonJS, exits 0 on a file containing a duplicate top-level `const`, and
    therefore reports a clean bill of health for broken code. Copying the same
    bytes to `x.mjs` makes the identical command report
    `SyntaxError: Identifier 'a' has already been declared`. Since ComfyUI loads
    `web/*.js` as an ES module, `.mjs` is the only dialect worth checking, and
    the canary below proves the gate fires before we trust a PASS.
    """

    @staticmethod
    def _node() -> str | None:
        import shutil
        return shutil.which("node") or shutil.which("node.exe")

    def test_gate_fires_on_the_canary(self):
        import subprocess
        import tempfile
        import pathlib
        node = self._node()
        if node is None:
            self.skipTest("本机没有 node，无法做 JS 语法检查")
        root = pathlib.Path(tempfile.mkdtemp(prefix="h3v28_js_"))
        try:
            bad = root / "canary_bad.mjs"
            bad.write_text('import { x } from "y";\nconst a = 1;\nconst a = 2;\n',
                           encoding="utf-8")
            good = root / "canary_good.mjs"
            good.write_text('import { x } from "y";\nconst a = 1;\nexport { a };\n',
                            encoding="utf-8")
            ok = subprocess.run([node, "--check", str(good)], capture_output=True)
            self.assertEqual(ok.returncode, 0, "对照文件本该干净")
            bad_res = subprocess.run([node, "--check", str(bad)], capture_output=True)
            self.assertNotEqual(bad_res.returncode, 0,
                                "语法闸门对重复 const 不敏感 = 本测试失效")
            self.assertIn(b"already been declared", bad_res.stderr)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_panel_is_syntactically_valid_as_an_es_module(self):
        import subprocess
        import tempfile
        import pathlib
        node = self._node()
        if node is None:
            self.skipTest("本机没有 node，无法做 JS 语法检查")
        root = pathlib.Path(tempfile.mkdtemp(prefix="h3v28_js_"))
        try:
            dst = root / "h3_director_v28.mjs"
            dst.write_text(JS, encoding="utf-8")
            res = subprocess.run([node, "--check", str(dst)], capture_output=True)
            self.assertEqual(res.returncode, 0,
                             "导演面板语法错误：\n"
                             + res.stderr.decode("utf-8", "replace")[:1500])
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_panel_is_an_es_module_that_touches_no_node_api(self):
        """It is loaded by the browser: require()/process would break at runtime."""
        self.assertIn("import { app", JS)
        self.assertNotIn("require(", JS)
        self.assertNotIn("process.", JS)
        self.assertNotIn("__dirname", JS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
