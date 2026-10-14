"""P10 recovery-path fixes: nothing may silently inherit or quietly discard state.

Four behaviours that the read-only audits could only guess at, each turned into a
test after being reproduced against the CURRENT code:

  1. Two 【新建项目】 clicks in the same second used to land in the SAME directory
     (id = second-resolution + title slug, mkdir(exist_ok=True)), so the second
     project came up showing the first one's plan, state and reference profile.
  2. A torn state file is renamed to a `.corrupt.*` corpse - but the name had only
     second resolution, so a second torn read in the same second os.replace'd OVER
     the first corpse and destroyed the only copy of a lost session.
  3. A state file that parses but is not an object was replaced by a blank state
     with no trace; the card just looks empty.
  4. `mark_candidate` recorded the Motion-Context slot facts into a dict it had
     already serialised, so the on-disk candidate receipt never said whether the
     clip it describes can be accepted at all.

Runs in the temp library from _v28_bootstrap; never touches <H3_PROJECT_DIR>\\V28_PROJECTS.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import unittest

sys.path.insert(0, pathlib.Path(__file__).resolve().parent.as_posix())
import _v28_bootstrap as B                                                 # noqa: E402


def segment(i):
    return {"id": i, "beat": f"节拍{i}",
            "start_state": {"pose": f"pose {i} start"},
            "end_state": {"pose": f"pose {i} end", "motion": f"trend {i}"},
            "directives": {"join": "continuous", "camera": "hold", "framing": "keep",
                           "pace": "steady", "tail": "ongoing"},
            "prompt": __import__("test_v28_optional_director").manual_text(f"She performs action {i} slowly and continuously."),
            "duration": 10.0, "seed": None, "locked": False}


PLAN = {"version": 1, "story_goal": "一个清晨长镜头",
        "global_state": {"visual_style": "Cinematic live-action"},
        "references": {"picture_count": 1, "picture_indices": [1],
                       "scene_phrase": "a quiet bedroom"},
        "style": "auto", "continuation_mode": "same_shot", "warnings": [],
        "segments": [segment(1), segment(2)]}


PROFILE = {"version": 1,
           "source_pictures": [{"index": 1, "filename": "a.png", "width": 1024,
                                "height": 1024}],
           "subjects": [{"id": "subject_1", "picture_refs": [1], "role": "女主角",
                         "seen": {"hair": "black hair", "glasses": "", "wardrobe": {},
                                  "distinctive_appearance": [], "visible_pose": {}},
                         "inferred": {}, "do_not_infer": ["未来运动"]}],
           "scene": {"seen": {"space": "bedroom"}, "inferred": {}},
           "props": [], "composition": {"seen": {}, "inferred": {}},
           "uncertain": [], "not_answerable": []}


class HygieneCase(unittest.TestCase):

    def setUp(self):
        self._ctx = B.fresh_env()
        self.M, self.root = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)
        self.P = self.M["v28_paths"]
        self.PJ = self.M["v28_project"]
        self.SM = self.M["v28_state_machine"]


class TestProjectIdCollisions(HygieneCase):

    def test_two_creates_in_one_second_do_not_share_a_project(self):
        first = self.PJ.create("同一个标题")
        second = self.PJ.create("同一个标题")
        self.assertNotEqual(first["project_id"], second["project_id"],
                            "同秒同标题必须落在两个目录，否则新项目直接继承旧项目的剧情")
        self.PJ.write(first["project_id"], "STORY_PLAN.json", PLAN)
        self.assertIsNone(self.PJ.read(second["project_id"], "STORY_PLAN.json", default=None),
                          "第二个项目里不得看得见第一个项目的计划")

    def test_the_suffix_only_applies_to_generated_ids(self):
        """An explicit project_id is a RESUME (/state, /plan on an existing card,
        and every test fixture). It must stay idempotent, not fork a new folder."""
        a = self.PJ.create(title="甲", project_id="resume_me")
        b = self.PJ.create(title="甲", project_id="resume_me")
        self.assertEqual(a["project_id"], b["project_id"])
        self.assertEqual(sorted(d.name for d in self.P.PROJECTS_ROOT.iterdir()
                                if d.is_dir()), ["resume_me"],
                         "同一显式 id 重复 create 只能有一个目录")

    def test_an_empty_directory_does_not_count_as_taken(self):
        pid = self.PJ.create("占位")["project_id"]
        again = self.PJ.create("占位")
        self.assertTrue(again["project_id"].startswith(pid))
        self.assertEqual(again["project_id"], pid + "_2",
                         "第一个目录有 PROJECT.json，第二个才该加后缀")


class TestQuarantineKeepsEveryCorpse(HygieneCase):

    def torn_read_twice(self):
        pid = self.PJ.create("撕裂状态")["project_id"]
        state = self.PJ.project_dir(pid) / "SESSION_STATE.json"
        bodies = []
        for n in (1, 2):
            state.write_text('{"status": "GENERATING", ', encoding="utf-8")   # torn
            with self.assertRaises(json.JSONDecodeError):
                self.P.read_json(state)
            bodies.append(state)
        corpses = sorted(p.name for p in self.PJ.project_dir(pid).glob("*.corrupt.*"))
        self.assertEqual(len(corpses), 2, f"两次撕裂必须留下两具尸体：{corpses}")
        note = self.P.PROJECTS_ROOT / self.P.CORRUPT_NOTE_NAME
        self.assertTrue(note.is_file(), "隔离事件要在 V28_PROJECTS 里看得见，否则空卡片无从解释")
        lines = note.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(all("QUARANTINED" in ln for ln in lines), lines)
        return corpses

    def test_same_second_quarantine_does_not_eat_the_first_evidence(self):
        before = time.time()
        self.torn_read_twice()
        self.assertLess(time.time() - before, 5.0, "本用例就是要在同一秒内触发两次")

    def test_the_corpse_still_holds_the_original_bytes(self):
        corpses = self.torn_read_twice()
        pid = self.PJ.list_projects()[0]["project_id"]
        d = self.PJ.project_dir(pid)
        texts = [(d / n).read_text(encoding="utf-8") for n in corpses]
        self.assertEqual(texts[0], texts[1], "两具尸体都该是同一份撕裂内容，谁也不该被覆盖成空")
        self.assertTrue((d / corpses[0]).is_file())


class TestUnusableStateIsNotSilent(HygieneCase):

    def test_a_valid_json_non_object_is_logged_before_being_dropped(self):
        pid = self.PJ.create("列表状态")["project_id"]
        self.PJ.write(pid, "SESSION_STATE.json", [1, 2, 3])
        st = self.SM.load_state(pid)
        self.assertEqual(st["status"], "PLANNED", "仍然要落到空白态，卡片不能白屏")
        self.assertEqual(st["accepted"], [])
        logs = "\n".join(p.read_text(encoding="utf-8")
                         for p in (self.PJ.project_dir(pid) / "logs").glob("*.log"))
        self.assertIn("unusable", logs, f"丢弃一份能解析的状态文件必须留话：{logs[:200]}")
        self.assertTrue((self.PJ.project_dir(pid) / "SESSION_STATE.json").is_file(),
                        "日志不能替用户删文件：原件要留在原地，人才有可能把它救回来")


class TestCandidateReceiptFacts(HygieneCase):

    def drive_to_candidate(self, make_slot: bool):
        pid = self.PJ.create("候选回执")["project_id"]
        self.PJ.write(pid, "REFERENCE_PROFILE.json", PROFILE)
        self.PJ.write(pid, "STORY_PLAN.json", PLAN)
        # The real instruction, not a hand-made dict: mark_generating indexes the
        # frame-count and seed fields straight out of it, and a stub would only
        # prove that mark_candidate copies whatever was already copied.
        wi = self.SM.widget_instructions(pid, seed=77)
        self.SM.mark_generating(pid, instruction=wi)
        slot = self.PJ.mc_slot_path(wi["segment_id"])
        if make_slot:
            slot.parent.mkdir(parents=True, exist_ok=True)
            slot.write_bytes(b"FAKE-LATENT")
        else:
            slot.unlink(missing_ok=True)
        self.SM.mark_candidate(pid, video="H3_seg1.mp4", seed=wi["seed"])
        d = self.PJ.project_dir(pid) / "candidates"
        files = sorted(d.glob("*.json"))
        self.assertEqual(len(files), 1, files)
        return pid, json.loads(files[0].read_text(encoding="utf-8"))

    def test_the_slot_facts_reach_the_disk(self):
        _, rec = self.drive_to_candidate(make_slot=True)
        self.assertIn("motion_context_slot", rec,
                      "键曾在 record_clip 之后才写进字典，因此从未落盘")
        self.assertTrue(rec["motion_context_slot_exists"], rec)
        self.assertEqual(str(rec["motion_context_slot"]),
                         str(self.PJ.mc_slot_path(1)),
                         "回执里的路径必须是接受时真正检查的那一个")

    def test_a_missing_slot_is_recorded_as_missing(self):
        _, rec = self.drive_to_candidate(make_slot=False)
        self.assertIn("motion_context_slot", rec)
        self.assertFalse(rec["motion_context_slot_exists"],
                         "接受时会被拒的那一段事实，回执上就该先看得见")


if __name__ == "__main__":
    unittest.main(verbosity=2)
