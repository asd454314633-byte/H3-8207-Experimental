"""B 层：中文语义验收（真实离线 CPU 翻译引擎 + 真实编译器）。

纪律（任务书 §9.3 / §13-B）：
  * 每条用例给出「必须出现」与「必须不出现」两个方向的断言，
    避免"看起来像英文就算通过"的宽松判定。
  * 额外加两条**全局幻觉红线**：任何输出都不得包含
    "I don't know." / "Yeah." / "Shall I" / "I'm sorry." / "I'm not sure."
    这些是 Argos 对孤立标点或单字输入的幻觉产物，出现即判 FAIL。
  * 语义明显错误**不允许**被标记为 PASS：断言失败就是失败。

运行：
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_b_semantics.py" -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.translator import TranslationUnavailable, provider_status, translate_zh_to_en  # noqa: E402
from app.translator import semantic_qa                                                     # noqa: E402

HALLUCINATIONS = ("i don't know", "i'm sorry", "i'm not sure", "yeah.", "shall i")

# (分类, 中文, 必含(小写), 禁止(小写))
CASES: list[tuple[str, str, list[str], list[str]]] = [
    # ---- 方向：左右 -------------------------------------------------------
    ("方向-左手", "女孩用左手拿起杯子。", ["left hand"], ["right hand"]),
    ("方向-右手", "男孩举起右手。", ["right hand"], ["left hand"]),
    ("方向-画面左侧", "她从画面左侧走入。", ["left"], ["right"]),
    ("方向-画面右侧", "他从画面右侧靠近。", ["right"], ["left"]),
    ("方向-左右手不混淆", "他右手拿着伞，左手插在口袋里。", ["right hand", "left hand"], []),
    # ---- 方向：前后 -------------------------------------------------------
    ("方向-向前", "她向前走了一步。", ["forward"], ["backward"]),
    ("方向-向后", "他后退了两步。", ["backward"], ["forward"]),
    ("方向-前方", "前方出现一辆车。", ["ahead"], []),
    # ---- 距离：靠近 / 远离 ------------------------------------------------
    ("距离-靠近", "她慢慢靠近他。", ["closer"], ["away"]),
    ("距离-远离", "他转身远离人群。", ["away"], ["closer"]),
    # ---- 姿态：站起 / 坐下 ------------------------------------------------
    ("姿态-站起", "她从沙发上站起来。", ["stands up"], ["sits down"]),
    ("姿态-坐下", "他慢慢坐下。", ["sits down"], ["stands up"]),
    # ---- 朝向：面对 / 背对 ------------------------------------------------
    ("朝向-面对", "她面对着他。", ["faces"], ["back to"]),
    ("朝向-背对", "他背对着窗户。", ["back"], []),
    # ---- 接触 / 分离 ------------------------------------------------------
    ("接触-触碰", "她伸手接触到他的肩膀。", ["contact"], []),
    ("分离-分开", "两人随后分开。", ["separates"], []),
    # ---- 动作先后 ---------------------------------------------------------
    ("时序-然后", "她先开门，然后走进去。", ["then"], []),
    ("时序-同时", "他一边说话，一边挥手。", ["at the same time"], []),
    ("时序-同时动作", "两人同时转身。", ["at the same time"], []),
    # ---- 否定 -------------------------------------------------------------
    ("否定-不动", "他不动。", ["not move"], []),
    ("否定-不说话", "她没有说话。", ["not speak"], []),
    ("否定-不回头", "他继续走，没有回头。", ["not look back"], []),
    ("否定-禁止", "不要移动镜头。", ["must not"], []),
    # ---- 转身 / 回头 ------------------------------------------------------
    ("转头-转身", "她转身走向门口。", ["turns around"], []),
    ("转头-回头", "他回头看了一眼。", ["looks back"], []),
    # ---- 镜头移动方向（官方词汇） ----------------------------------------
    ("镜头-左移", "镜头向左平移。", ["trucks left"], ["trucks right"]),
    ("镜头-右摇", "镜头向右摇摄。", ["pans right"], ["pans left"]),
    ("镜头-变焦推近", "镜头变焦推近。", ["zooms in"], ["zooms out"]),
    ("镜头-固定", "镜头固定不动。", ["static"], []),
    ("镜头-跟拍", "镜头跟拍他的背影。", ["tracks"], []),
    # ---- 实体保全（实测 Argos 会丢实体，必须由术语表兜住） ---------------
    ("实体-场景", "深夜的便利店。", ["convenience store"], []),
    ("实体-门口", "她走向门口。", ["door"], []),
    ("实体-沙发", "他坐在沙发上。", ["couch"], []),
    ("实体-桌子", "杯子放在桌上。", ["table"], []),
    ("实体-街道", "雨夜的城市街道空无一人。", ["street"], []),
    ("实体-伞", "她手里拿着一把伞。", ["umbrella"], []),
    # ---- 外观 / 年龄 ------------------------------------------------------
    ("外观-年轻女性", "二十多岁的年轻女性。", ["young woman"], []),
    ("外观-中年男性", "三十岁左右的男性。", ["man"], []),
    ("外观-西装", "他穿着西装。", ["suit"], []),
    ("外观-长发", "她有一头长发。", ["long hair"], []),
    # ---- 风格 / 景别 ------------------------------------------------------
    ("风格-电影感", "电影感的画面。", ["cinematic"], []),
    ("景别-中景", "中景镜头。", ["medium shot"], []),
    # ---- 指代 -------------------------------------------------------------
    ("指代-多人", "两人并肩站着。", ["two of them"], []),
    ("指代-第三人", "画面里有第三人。", ["third person"], []),
    # ---- 复合句（考查长句下不崩坏） --------------------------------------
    ("复合-方向+动作", "她从右侧靠近他，然后停下脚步。", ["right", "closer"], []),
    ("复合-否定+回头", "他不动，也不回头。", ["not move", "not look back"], []),
]


class SemanticsB(unittest.TestCase):
    """B 层语义用例：每个分类一条 test，内部逐条断言并汇总。"""

    @classmethod
    def setUpClass(cls) -> None:
        st = provider_status()
        if not st.get("available"):
            raise unittest.SkipTest(f"离线翻译引擎不可用：{st.get('error')}")

    def _run_case(self, cat: str, zh: str, must: list[str], forbid: list[str]) -> None:
        try:
            en = translate_zh_to_en(zh)
        except TranslationUnavailable as exc:  # pragma: no cover
            self.fail(f"[{cat}] 翻译引擎不可用：{exc}")
        low = (en or "").lower()
        self.assertTrue(en and en.strip(), f"[{cat}] 译文为空：{zh!r}")
        for token in must:
            self.assertIn(token, low, f"[{cat}] 缺少必需语义 {token!r}\n  中文：{zh}\n  译文：{en}")
        for token in forbid:
            self.assertNotIn(token, low, f"[{cat}] 出现不应有的语义 {token!r}\n  中文：{zh}\n  译文：{en}")
        for bad in HALLUCINATIONS:
            self.assertNotIn(bad, low, f"[{cat}] 译文含 MT 幻觉 {bad!r}\n  中文：{zh}\n  译文：{en}")


def _make(cat: str, zh: str, must: list[str], forbid: list[str]):
    def _test(self: SemanticsB) -> None:
        self._run_case(cat, zh, must, forbid)
    _test.__name__ = "test_" + str(abs(hash(cat)) % 10**8).zfill(8) + "_" + cat.replace("-", "_")
    _test.__doc__ = f"{cat}：{zh}"
    return _test


for _i, (_cat, _zh, _must, _forbid) in enumerate(CASES, start=1):
    _t = _make(_cat, _zh, _must, _forbid)
    _t.__name__ = f"test_{_i:02d}_{_cat.replace('-', '_')}"
    setattr(SemanticsB, _t.__name__, _t)


class SemanticsBExtra(unittest.TestCase):
    """B 层附加：整句编译链路上的语义与合同检查（不只看单字段翻译）。"""

    @classmethod
    def setUpClass(cls) -> None:
        if not provider_status().get("available"):
            raise unittest.SkipTest("离线翻译引擎不可用")

    def test_90_dialogue_never_translated(self):
        from app.h3model import Dialogue, Project, ReferencePreset
        from app.compiler import compile_segment
        p = Project(name="B")
        p.preset = ReferencePreset(scene="房间")
        a = p.add_role("林薇", name_en="Lin Wei")
        seg = p.add_segment(title="段", mode="T2VA", duration=6)
        seg.action_zh = "她坐在窗边。"
        seg.dialogues = [Dialogue(id="D01", speaker_role_id=a.id,
                                 zh_text="我等你很久了，别走。")]
        res = compile_segment(seg, p)
        self.assertTrue(res.ok, res.errors)
        self.assertIn("我等你很久了，别走。", res.prompt)
        self.assertIn("<d>[Chinese] 我等你很久了，别走。</d>", res.prompt)

    def test_91_qa_pair_flags_missing_direction(self):
        issues = semantic_qa.qa_pair("她从左侧走近。", "she approaches")
        self.assertTrue(any(i.code == "direction_missing" for i in issues),
                        "左 未译出 left 时必须报 direction_missing")

    def test_92_qa_pair_passes_correct_translation(self):
        issues = semantic_qa.qa_pair("她从左侧走近。", "she approaches from the left side")
        self.assertFalse(any(i.code == "direction_missing" for i in issues))

    def test_93_official_camera_vocabulary_used(self):
        en = translate_zh_to_en("镜头向左平移")
        self.assertTrue(any(w.lower() in en.lower()
                            for w in ("Truck Left", "pans left", "trucks left")),
                        f"镜头方向必须命中官方词汇，实际：{en!r}")

    def test_94_role_name_protected_from_mt(self):
        en = translate_zh_to_en("林薇走向门口。", protect_terms={"林薇": "Lin Wei"})
        self.assertIn("Lin Wei", en)
        self.assertNotIn("Lindsey", en)

    # ---- 幻觉守卫（回归用例） -------------------------------------------
    def test_95_hallucination_guard_detects_known_patterns(self):
        from app.translator.engine import looks_hallucinated
        self.assertTrue(looks_hallucinated("I'm not sure what I'm talking about."))
        self.assertTrue(looks_hallucinated("I don't know."))
        self.assertTrue(looks_hallucinated("I'm sorry."))
        self.assertTrue(looks_hallucinated(""))
        # 必须**不**误伤合法短译
        for good in ("Here.", "Call me.", "he does not move.",
                     "the camera holds a static shot."):
            self.assertFalse(looks_hallucinated(good), f"误判为幻觉：{good!r}")

    def test_96_field_keeps_chinese_when_mt_hallucinates(self):
        """MT 幻觉时，编译器必须保留中文原文并记录警告，而不是写入错误英文。"""
        from app.h3model import Project, ReferencePreset
        from app.compiler import compile_segment

        def bad_translate(text: str, protect_terms=None) -> str:  # noqa: ARG001
            raise TranslationUnavailable("模拟翻译引擎给出幻觉输出")

        p = Project(name="守卫")
        p.preset = ReferencePreset(scene="房间")
        seg = p.add_segment(title="段", mode="T2VA", duration=6)
        seg.action_zh = "她坐在窗边。"
        res = compile_segment(seg, p, translate=bad_translate)
        self.assertTrue(res.ok, "翻译失败不应导致编译整体失败")
        self.assertIn("她坐在窗边。", res.prompt, "翻译失败时必须保留中文原文")
        self.assertTrue(any("翻译失败" in w for w in res.warnings),
                        f"必须记录翻译失败警告，实际 {res.warnings}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
