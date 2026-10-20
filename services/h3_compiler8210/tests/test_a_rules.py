"""A 层：纯规则单元验收（不依赖机器翻译、不依赖网络、不使用 GPU）。

设计纪律：
  * 使用**桩翻译函数**，把"格式规则正确性"与"MT 质量"彻底分离；
    这样 A 层失败必定是规则缺陷，而不是模型波动。
  * 每条用例只断言一个明确的官方契约，失败信息里给出实际值。

运行：
    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_a_rules.py" -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import official_spec as spec            # noqa: E402
from app.compiler import compile_segment, fmt_timestamp  # noqa: E402
from app.h3model import (Dialogue, MediaAsset, Project, ReferencePreset,  # noqa: E402
                         Segment)
from app.translator import glossary as gl         # noqa: E402
from app.validator import validate_compiled       # noqa: E402


# ---------------------------------------------------------------------------
# 桩翻译：确定性术语替换 + 其余原样返回（绝不调用 MT）
# ---------------------------------------------------------------------------
_SORTED = sorted(gl.TERMS.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def stub_zh(text: str, protect_terms: dict[str, str] | None = None) -> str:
    src = (text or "").strip()
    if not src:
        return ""
    extra = sorted((protect_terms or {}).items(), key=lambda kv: (-len(kv[0]), kv[0]))
    out, i = [], 0
    while i < len(src):
        for table in (extra, _SORTED):
            hit = next(((zh, en) for zh, en in table if src.startswith(zh, i)), None)
            if hit:
                out.append(hit[1])
                i += len(hit[0])
                break
        else:
            out.append(src[i])
            i += 1
    return " ".join(x for x in "".join(out).split() if x)


def project_two() -> tuple[Project, Segment]:
    p = Project(name="A层")
    p.preset = ReferencePreset(scene="便利店")
    a = p.add_role("林薇", name_en="Lin Wei", appearance="年轻女性")
    b = p.add_role("陈默", name_en="Chen Mo", appearance="男性")
    seg = p.add_segment(title="第一段", mode="Ref2VA", duration=8)
    seg.scene_zh = "便利店"
    seg.role_ids = [a.id, b.id]
    seg.action_zh = "两人对话。"
    seg.assets = [
        MediaAsset(id="M01", kind="Picture", label="林薇脸", connected=True,
                   role_id=a.id, purpose="face"),
        MediaAsset(id="M02", kind="Picture", label="陈默脸", connected=True,
                   role_id=b.id, purpose="face"),
    ]
    return p, seg


def compile_with_stub(seg: Segment, p: Project):
    return compile_segment(seg, p, translate=stub_zh)


# ---------------------------------------------------------------------------
class A01Duration(unittest.TestCase):  # 1–2
    def test_01_duration_lower_bound(self):
        p, seg = project_two()
        for ok_val, bad_val in ((4, 3),):
            seg.duration = ok_val
            self.assertTrue(compile_with_stub(seg, p).ok, "4 秒必须被接受")
            seg.duration = bad_val
            self.assertFalse(compile_with_stub(seg, p).ok, "3 秒必须被拒绝")

    def test_02_duration_upper_bound(self):
        p, seg = project_two()
        seg.duration = 15
        self.assertTrue(compile_with_stub(seg, p).ok, "15 秒必须被接受")
        seg.duration = 16
        self.assertFalse(compile_with_stub(seg, p).ok, "16 秒必须被拒绝")


class A03Mode(unittest.TestCase):
    def test_03_unknown_mode_rejected(self):
        p, seg = project_two()
        seg.mode = "Ref3VA"
        res = compile_with_stub(seg, p)
        self.assertFalse(res.ok)
        self.assertTrue(any("模式" in e for e in res.errors))


class A04BaseFields(unittest.TestCase):
    def test_04_t2va_emits_exactly_base_fields(self):
        p, seg = project_two()
        seg.mode = "T2VA"
        seg.role_ids = []
        seg.assets = []
        seg.action_zh = "空旷的海边。"
        res = compile_with_stub(seg, p)
        self.assertTrue(res.ok, res.errors)
        for f in spec.BASE_FIELDS:
            self.assertIn(f"{f}:", res.prompt)
        self.assertNotIn("subject_definitions:", res.prompt)
        self.assertNotIn("retention_analysis:", res.prompt)

    def test_05_ref2va_emits_exactly_ref_fields(self):
        p, seg = project_two()
        res = compile_with_stub(seg, p)
        self.assertTrue(res.ok, res.errors)
        for f in spec.REF_FIELDS:
            self.assertIn(f"{f}:", res.prompt)
        self.assertNotIn("integrated_multimodal_description:", res.prompt)

    def test_06_field_order_matches_official(self):
        p, seg = project_two()
        res = compile_with_stub(seg, p)
        pos = [res.prompt.find(f"{f}:") for f in spec.REF_FIELDS]
        self.assertNotIn(-1, pos)
        self.assertEqual(pos, sorted(pos), f"字段顺序必须为官方顺序，实际位置 {pos}")


class A07Shots(unittest.TestCase):
    def test_07_first_shot_has_no_timestamp(self):
        p, seg = project_two()
        seg.shots = []
        res = compile_with_stub(seg, p)
        head = res.prompt.split("[Shot 1]", 1)[1][:40]
        self.assertFalse(head.strip().startswith("At "), f"Shot 1 不得带时间戳：{head!r}")

    def test_08_later_shot_requires_timestamp(self):
        from app.h3model import Shot
        p, seg = project_two()
        seg.shots = [Shot(index=1, at_seconds=None, zh_content="第一镜"),
                     Shot(index=2, at_seconds=None, zh_content="第二镜")]
        res = compile_with_stub(seg, p)
        self.assertTrue(any("时间戳" in w for w in res.warnings),
                        f"缺少切点时间必须警告，实际 {res.warnings}")

    def test_09_timestamp_format_is_official(self):
        self.assertEqual(fmt_timestamp(0), "00:00.000")
        self.assertEqual(fmt_timestamp(1.5), "00:01.500")
        self.assertEqual(fmt_timestamp(65.25), "01:05.250")
        from app.h3model import Shot
        p, seg = project_two()
        seg.shots = [Shot(index=1, at_seconds=None, zh_content="A"),
                     Shot(index=2, at_seconds=3.25, zh_content="B")]
        res = compile_with_stub(seg, p)
        self.assertIn("At 00:03.250", res.prompt)


class A10SubjectMapping(unittest.TestCase):
    def test_10_subject_numbers_follow_permanent_role_ids(self):
        p, seg = project_two()
        # 出场顺序反着写，Subject 仍按 role_ids 给定顺序（永久编号顺序）分配
        seg.role_ids = ["C02", "C01"]
        res = compile_with_stub(seg, p)
        self.assertEqual(res.meta["subjects"]["role:C02"], 1)
        self.assertEqual(res.meta["subjects"]["role:C01"], 2)

    def test_11_silent_roles_get_no_speaker_number(self):
        p, seg = project_two()
        seg.dialogues = [Dialogue(id="D01", speaker_role_id="C01", zh_text="你好。")]
        res = compile_with_stub(seg, p)
        self.assertEqual(res.meta["role_speaker"], {"C01": 1})
        self.assertNotIn("C02", res.meta["role_speaker"])


class A12SpeakerGroups(unittest.TestCase):
    def test_12_simultaneous_speech_uses_composite_speaker(self):
        p, seg = project_two()
        seg.dialogues = [
            Dialogue(id="D01", speaker_role_id="C01", zh_text="一。", group="g1"),
            Dialogue(id="D02", speaker_role_id="C02", zh_text="二。", group="g1"),
        ]
        res = compile_with_stub(seg, p)
        self.assertIn("(S1,S2)", res.prompt)


class A13DialogueIntegrity(unittest.TestCase):
    def test_13_chinese_dialogue_is_verbatim(self):
        p, seg = project_two()
        seg.dialogues = [Dialogue(id="D01", speaker_role_id="C01",
                                  zh_text="路上小心，别回头。")]
        res = compile_with_stub(seg, p)
        self.assertIn("<d>[Chinese] 路上小心，别回头。</d>", res.prompt)

    def test_14_dialogue_block_count_matches_events(self):
        p, seg = project_two()
        seg.dialogues = [Dialogue(id="D01", speaker_role_id="C01", zh_text="一。"),
                         Dialogue(id="D02", speaker_role_id="C02", zh_text="二。")]
        res = compile_with_stub(seg, p)
        self.assertEqual(res.prompt.count("<d>"), 2)
        self.assertEqual(res.prompt.count("</d>"), 2)

    def test_15_dialogue_never_in_audio_sections(self):
        p, seg = project_two()
        seg.dialogues = [Dialogue(id="D01", speaker_role_id="C01", zh_text="台词内容。")]
        seg.soundscape_zh = "雨声"
        seg.music_zh = "钢琴"
        res = compile_with_stub(seg, p)
        rep = validate_compiled(res.prompt, seg, p)
        codes = [c.code for c in rep.errors]
        self.assertNotIn("local.dialogue_in_soundscape", codes)
        self.assertNotIn("local.dialogue_in_music", codes)
        sound = res.prompt.split("overall_soundscape:", 1)[1].split("non_diegetic_music:")[0]
        self.assertNotIn("台词内容。", sound)


class A16Assets(unittest.TestCase):
    def test_16_unconnected_asset_produces_no_label(self):
        p, seg = project_two()
        seg.assets.append(MediaAsset(id="M03", kind="Picture", label="未连接",
                                     connected=False, role_id="", purpose="scene"))
        res = compile_with_stub(seg, p)
        self.assertNotIn("<Picture 3>", res.prompt)

    def test_17_standalone_picture_gets_own_label_and_retention(self):
        p, seg = project_two()
        seg.assets.append(MediaAsset(id="M03", kind="Picture", label="首帧",
                                     connected=True, role_id="", purpose="keyframe_first"))
        res = compile_with_stub(seg, p)
        self.assertIn("<Picture 3>", res.prompt)
        retention = res.prompt.split("retention_analysis:", 1)[1].split("detailed_description:")[0]
        self.assertIn("<Picture 3>", retention)

    def test_18_scene_subject_is_covered_by_retention(self):
        p, seg = project_two()
        res = compile_with_stub(seg, p)
        scene_n = res.meta["subjects"]["scene"]
        retention = res.prompt.split("retention_analysis:", 1)[1].split("detailed_description:")[0]
        self.assertIn(f"<Subject {scene_n}>", retention,
                      "场景主体必须出现在 retention_analysis（上游 retention_coverage 规则）")


class A19RetentionMarkers(unittest.TestCase):
    def test_19_audio_marker_must_not_be_visual(self):
        p, seg = project_two()
        seg.assets.append(MediaAsset(id="M03", kind="Audio", label="环境音",
                                     connected=True, role_id="", purpose="ambience"))
        seg.retention = {"<Audio 1>": "fully_copy"}
        res = compile_with_stub(seg, p)
        rep = validate_compiled(res.prompt, seg, p)
        self.assertFalse(any(c.code == "upstream.retention_marker_family" for c in rep.errors),
                         "Audio 使用 fully_copy 属于合法音频标记，不应报错")
        seg.retention = {"<Audio 1>": "fully_preserved"}   # 视觉标记用在音频上
        res2 = compile_with_stub(seg, p)
        rep2 = validate_compiled(res2.prompt, seg, p)
        self.assertTrue(any(c.code == "upstream.retention_marker_family" for c in rep2.errors),
                        "视觉标记用在 Audio 上必须报错")


class A20Length(unittest.TestCase):
    def test_20_prompt_char_limit_enforced(self):
        p, seg = project_two()
        seg.action_zh = "测试。" * 4000
        res = compile_with_stub(seg, p)
        if len(res.prompt) > spec.MAX_PROMPT_CHARS:
            self.assertTrue(any("上限" in e for e in res.errors))
            rep = validate_compiled(res.prompt, seg, p)
            self.assertTrue(any(c.code == "local.too_long" for c in rep.errors))


class A21Alignment(unittest.TestCase):
    def test_21_i2va_alignment_is_verbatim(self):
        p, seg = project_two()
        seg.mode = "I2VA"
        seg.role_ids = []
        seg.assets = [MediaAsset(id="M01", kind="Picture", label="首帧",
                                 connected=True, role_id="", purpose="keyframe_first")]
        res = compile_with_stub(seg, p)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.prompt.startswith(spec.I2VA_ALIGNMENT),
                        f"必须以官方逐字对齐指令开头：{res.prompt[:80]!r}")

    def test_22_ref2va_has_no_alignment_instruction(self):
        p, seg = project_two()
        res = compile_with_stub(seg, p)
        self.assertFalse(res.prompt.startswith("For the target video"))
        self.assertNotIn("aligns with the", res.prompt)


class A23Misc(unittest.TestCase):
    def test_23_unknown_role_reference_rejected(self):
        p, seg = project_two()
        seg.role_ids = ["C99"]
        res = compile_with_stub(seg, p)
        self.assertFalse(res.ok)
        self.assertTrue(any("不存在" in e for e in res.errors))

    def test_24_ambiguity_is_reported_not_guessed(self):
        p, seg = project_two()
        seg.action_zh = "他转身离开。"
        res = compile_with_stub(seg, p)
        self.assertTrue(any("他" in w for w in res.warnings),
                        "指代不明必须提示用户，而不是擅自猜测")

    def test_25_relations_render_deterministically(self):
        p, seg = project_two()
        seg.relations = [{"actor": "C02", "target": "C01",
                          "position": "站在左侧", "action": "接过东西"}]
        res = compile_with_stub(seg, p)
        self.assertIn("to the left of", res.prompt)
        self.assertIn("Chen Mo", res.prompt)

    def test_26_roundtrip_preserves_new_fields(self):
        p, seg = project_two()
        seg.relations = [{"actor": "C01", "target": "C02",
                          "position": "前方", "action": ""}]
        seg.task_types = ["reference generation"]
        back = Project.from_dict(p.to_dict())
        s2 = back.segment(seg.id)
        self.assertEqual(s2.relations, seg.relations)
        self.assertEqual(s2.task_types, ["reference generation"])


class A27SixSegments(unittest.TestCase):
    """§12：六段剧情——逐段独立编译，共用同一参考预设。"""

    def test_27_six_segments_compile_independently(self):
        p = Project(name="六段")
        p.preset = ReferencePreset(scene="便利店", style_terms="电影感")
        a = p.add_role("林薇", name_en="Lin Wei", appearance="年轻女性")
        for i in range(1, 7):
            s = p.add_segment(title=f"第{i}段", mode="T2VA", duration=8)
            s.scene_zh = "便利店"
            s.role_ids = [a.id]
            s.action_zh = f"她第{i}次环顾四周。"
        self.assertEqual(len(p.segments), 6)
        prompts = []
        for s in p.segments:
            res = compile_with_stub(s, p)
            self.assertTrue(res.ok, f"「{s.title}」编译失败：{res.errors}")
            prompts.append(res.prompt)
        self.assertEqual(len(set(prompts)), 6, "六段必须各自独立成篇，不能雷同或拼接")
        self.assertEqual(p.preset.scene, "便利店")


class A28StorageMigration(unittest.TestCase):
    """§10：保存系统——版本迁移可回滚，损坏文件不静默删除。"""

    @staticmethod
    def _store(tmp: str):
        from pathlib import Path

        from app.storage import Store
        return Store(Path(tmp))

    def test_28_old_schema_is_migrated_on_load(self):
        import json
        import tempfile

        from app.h3model import SCHEMA_VERSION
        with tempfile.TemporaryDirectory() as tmp:
            st = self._store(tmp)
            p, _ = project_two()
            raw = p.to_dict()
            raw["schema_version"] = 0          # 模拟旧版本数据
            (st.data / "project.json").write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            back = st.load_project()
            self.assertEqual(back.schema_version, SCHEMA_VERSION)
            self.assertEqual(len(back.segments), len(p.segments), "迁移不得丢段")

    def test_29_missing_schema_defaults_to_current(self):
        import json
        import tempfile

        from app.h3model import SCHEMA_VERSION
        with tempfile.TemporaryDirectory() as tmp:
            st = self._store(tmp)
            p, _ = project_two()
            raw = p.to_dict()
            raw.pop("schema_version", None)
            (st.data / "project.json").write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(st.load_project().schema_version, SCHEMA_VERSION)

    def test_30_corrupt_project_is_backed_up_not_deleted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            st = self._store(tmp)
            (st.data / "project.json").write_text("{ 这不是合法 JSON", encoding="utf-8")
            st.load_project()
            backups = list(st.data.glob("project.corrupt-*.json"))
            self.assertTrue(backups, "损坏的工程文件必须被备份保留，不能静默删除")


def load_tests(loader, tests, pattern):  # noqa: ARG001
    """把上面的若干规则类合并成一个 30 条用例的套件。"""
    suite = unittest.TestSuite()
    cases = [A01Duration, A03Mode, A04BaseFields, A07Shots, A10SubjectMapping,
             A12SpeakerGroups, A13DialogueIntegrity, A16Assets, A19RetentionMarkers,
             A20Length, A21Alignment, A23Misc, A27SixSegments, A28StorageMigration]
    for cls in cases:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
