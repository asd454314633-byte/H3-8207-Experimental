"""State-machine tests: the full PLANNED -> ... -> ACCEPTED chain, the cursor
invariants, the reroll/edit gates, and "an illegal state must never reach disk".

Everything runs against a temp project root (v28_paths constants are patched in
process), so <H3_PROJECT_DIR>\\V28_PROJECTS is never touched.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402


def segment(i, beat, prompt, join="continuous", duration=10.0):
    return {"id": i, "beat": beat,
            "start_state": {"pose": f"pose {i} start"},
            "end_state": {"pose": f"pose {i} end", "motion": f"trend {i}"},
            "directives": {"join": join, "camera": "hold", "framing": "keep",
                           "pace": "steady", "tail": "ongoing"},
            "prompt": "subject_definitions:\nN/A\n\nsummary:\n[reference generation] " + prompt + "\n\nretention_analysis:\nN/A\n\ndetailed_description:\n[Shot 1] " + prompt + "\n\noverall_soundscape:\nRoom tone.\n\nnon_diegetic_music:\nN/A", "duration": duration, "seed": None, "locked": False}


def make_plan(n=3):
    beats = ["清晨她坐直身体", "她走向窗边", "她推开窗", "她望向远处", "她回身拉上窗帘"]
    beats = (beats[:n] if n <= len(beats) else beats + [f"节拍{i}" for i in range(len(beats) + 1, n + 1)])[:n]
    prompts = [f"She performs action {i} slowly and continuously." for i in range(1, n + 1)]
    return {"version": 1, "story_goal": "一个清晨长镜头",
            "global_state": {"visual_style": "Cinematic live-action, natural window light"},
            "references": {"picture_count": 1, "picture_indices": [1],
                           "scene_phrase": "a quiet bedroom"},
            "style": "auto", "continuation_mode": "same_shot", "warnings": [],
            "segments": [segment(i + 1, beats[i], prompts[i]) for i in range(n)]}


PROFILE = {"version": 1,
           "source_pictures": [{"index": 1, "filename": "a.png", "width": 1024, "height": 1024}],
           "subjects": [{"id": "subject_1", "picture_refs": [1], "role": "女主角",
                         "seen": {"hair": "black hair", "glasses": "", "wardrobe": {},
                                  "distinctive_appearance": [], "visible_pose": {}},
                         "inferred": {}, "do_not_infer": ["未来运动"]}],
           "scene": {"seen": {"space": "bedroom"}, "inferred": {}},
           "props": [], "composition": {"seen": {}, "inferred": {}},
           "uncertain": [], "not_answerable": []}


class StateMachineCase(unittest.TestCase):

    def setUp(self):
        self._ctx = B.fresh_env()
        self.M, self.root = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)
        self.P, self.PJ, self.SM, self.S = (self.M["v28_paths"], self.M["v28_project"],
                                            self.M["v28_state_machine"], self.M["v28_schemas"])
        self.pid = "audit_case_1"
        self.PJ.create("审计用例", project_id=self.pid)
        self.PJ.write(self.pid, "REFERENCE_PROFILE.json", PROFILE)

    # -- helpers ----------------------------------------------------------
    def set_plan(self, n=3):
        plan = make_plan(n)
        self.SM.set_plan(self.pid, plan)
        return plan

    def slot(self, seg_id: int) -> pathlib.Path:
        p = self.PJ.mc_slot_path(seg_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"FAKE-LATENT")
        return p

    def state(self):
        return self.PJ.read(self.pid, "SESSION_STATE.json")

    def generate(self, expect_seg=None):
        """READY -> GENERATING -> CANDIDATE_READY for the current segment."""
        wi = self.SM.widget_instructions(self.pid)
        if expect_seg is not None:
            self.assertEqual(wi["segment_id"], expect_seg)
        self.SM.mark_generating(self.pid, instruction=wi)
        self.slot(wi["segment_id"])
        return self.SM.mark_candidate(self.pid, video=f"clip_{wi['segment_id']}.mp4",
                                      seed=wi["seed"])

    def state_file(self) -> pathlib.Path:
        return self.P.PROJECTS_ROOT / self.pid / "SESSION_STATE.json"


class TestTransitions(StateMachineCase):

    def test_blank_state_is_planned(self):
        st = self.SM.blank_state("x")
        self.assertEqual(st["status"], "PLANNED")
        self.assertEqual(st["current_segment"], 0)
        self.assertEqual(self.SM.load_state("never_created")["status"], "PLANNED")

    def test_full_chain_to_accepted(self):
        self.set_plan(3)
        st = self.state()
        self.assertEqual(st["status"], "READY")
        self.assertEqual((st["current_segment"], st["last_accepted_segment"]), (1, 0))
        self.generate(expect_seg=1)
        self.assertEqual(self.state()["status"], "CANDIDATE_READY")
        self.SM.accept(self.pid)
        st = self.state()
        self.assertEqual(st["status"], "READY")
        self.assertEqual((st["current_segment"], st["last_accepted_segment"]), (2, 1))
        self.assertEqual(st["accepted"], [
            {"segment_id": 1, "video": "clip_1.mp4", "seed": st["accepted"][0]["seed"],
             "accepted_at": st["accepted"][0]["accepted_at"]}])
        # task 24: accepting must not queue anything - no second GENERATING
        self.assertIsNone(st["current_candidate"])

    def test_after_accept_cursor_locked_relations(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        st, plan, _prof = self.SM.current_segment(self.pid)
        segs = plan["segments"]
        self.assertEqual(st["last_accepted_segment"], 1)
        self.assertEqual(st["current_segment"], 2)
        self.assertEqual(st["current_segment"], st["last_accepted_segment"] + 1)
        self.assertTrue(segs[0]["locked"], "accepted segment must be frozen")
        self.assertFalse(segs[1]["locked"])
        self.assertFalse(segs[2]["locked"])
        self.assertEqual(st["last_accepted_context"]["segment_id"], 1)

    def test_accept_refused_before_candidate_ready(self):
        self.set_plan(3)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.accept(self.pid)

    def test_accept_refused_when_slot_missing(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid)
        self.SM.mark_generating(self.pid, instruction=wi)
        self.SM.mark_candidate(self.pid, video="clip_1.mp4", seed=wi["seed"])
        (self.PJ.mc_slot_path(1)).unlink(missing_ok=True)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.accept(self.pid)
        self.assertEqual(self.state()["status"], "CANDIDATE_READY")

    def test_accept_final_segment_reaches_complete(self):
        """A 2-segment story must be able to finish."""
        self.set_plan(2)
        self.generate(expect_seg=1)
        self.SM.accept(self.pid)
        self.assertEqual(self.state()["status"], "READY")
        self.generate(expect_seg=2)
        out = self.SM.accept(self.pid)                # <- must not raise
        self.assertEqual(out["status"], "COMPLETE")
        self.assertEqual((out["current_segment"], out["last_accepted_segment"]), (2, 2))
        self.assertEqual(self.state()["status"], "COMPLETE")

    def test_single_segment_story_can_complete(self):
        self.set_plan(1)
        self.generate(expect_seg=1)
        out = self.SM.accept(self.pid)
        self.assertEqual(out["status"], "COMPLETE")

    def test_error_is_confined_to_the_current_segment(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        self.generate(expect_seg=2)
        st = self.SM.mark_error(self.pid, "生成失败：显存不足")
        self.assertEqual(st["status"], "ERROR")
        self.assertEqual(st["current_segment"], 2)
        self.assertEqual(st["last_accepted_segment"], 1)
        self.assertTrue(st["errors"])

    def test_reroll_does_not_advance(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        before = self.state()
        st = self.SM.prepare_reroll(self.pid)
        self.assertEqual(st["status"], "RETRY_PENDING")
        self.assertEqual(st["current_segment"], before["current_segment"])
        self.assertEqual(st["last_accepted_segment"], before["last_accepted_segment"])
        self.assertEqual(st["segment_count"], before["segment_count"])
        self.assertIsNone(st["current_candidate"])
        self.assertEqual(st["reroll"]["kept"]["last_accepted_segment"], 1)
        self.assertEqual(st["reroll"]["segment_id"], before["current_segment"])
        self.assertTrue(st["_next_seed"] > 0)

    def test_reroll_same_seed_reuses_segment_seed(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid, seed=12345)
        self.SM.mark_generating(self.pid, instruction=wi)
        self.SM.mark_candidate(self.pid, video="c.mp4", seed=12345)
        st = self.SM.prepare_reroll(self.pid, same_seed=True)
        self.assertEqual(st["reroll"]["seed"], 12345)

    def test_widget_instructions_refused_while_candidate_pending(self):
        self.set_plan(3)
        self.generate()
        with self.assertRaises(self.SM.GateRefused):
            self.SM.widget_instructions(self.pid)
        wi = self.SM.widget_instructions(self.pid, reroll=True)   # explicit reroll ok
        self.assertEqual(wi["segment_id"], 1)

    def test_edit_accepted_segment_is_refused(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.edit_segment(self.pid, segment_id=1, beat="改写已接受段")
        plan = self.PJ.read(self.pid, "STORY_PLAN.json")
        self.assertEqual(plan["segments"][0]["beat"], "清晨她坐直身体")
        self.assertTrue(plan["segments"][0]["locked"])

    def test_edit_current_and_later_segments_is_allowed(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        plan = self.SM.edit_segment(self.pid, segment_id=2, beat="她走到门前",
                                    duration=12.0)
        self.assertEqual(plan["segments"][1]["beat"], "她走到门前")
        self.assertEqual(plan["segments"][1]["duration"], 12.0)

    def test_edit_rejects_illegal_duration(self):
        self.set_plan(3)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.edit_segment(self.pid, segment_id=2, duration=90.0)

    def test_edit_rejects_a_plan_that_no_longer_validates(self):
        self.set_plan(3)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.edit_segment(self.pid, segment_id=2,
                                 directives={"camera": "helicopter_dive"})

    def test_reset_to_below_last_accepted_leaves_a_usable_state(self):
        """reset_to() advertises "回到第 la+1 段或其之前"; the cursor must then
        still be able to produce a submission instruction."""
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)              # la = 1, cur = 2
        self.generate(expect_seg=2)
        self.SM.accept(self.pid)              # la = 2, cur = 3
        self.SM.reset_to(self.pid, 2)         # rewind to the segment after the
        st = self.state()                     # last accepted one
        self.assertEqual(st["current_segment"], 2)
        wi = self.SM.widget_instructions(self.pid)      # <- must work
        self.assertEqual(wi["segment_id"], 2)


class TestPersistenceRules(StateMachineCase):

    def test_illegal_state_is_not_persisted(self):
        self.set_plan(3)
        path = self.state_file()
        good = path.read_bytes()
        st = self.SM.load_state(self.pid)
        st["status"] = "GENERATED_BUT_NOT_A_STATE"
        with self.assertRaises(self.S.SchemaError):
            self.SM.save_state(self.pid, st)
        self.assertEqual(path.read_bytes(), good, "rejected state reached the disk")

    def test_illegal_cursor_combination_is_not_persisted(self):
        self.set_plan(3)
        good = self.state_file().read_bytes()
        st = self.SM.load_state(self.pid)
        st["current_segment"] = 99          # > segment_count
        with self.assertRaises(self.S.SchemaError):
            self.SM.save_state(self.pid, st)
        self.assertEqual(self.state_file().read_bytes(), good)

    def test_accepted_cursor_not_behind_current_is_not_persisted(self):
        self.set_plan(3)
        good = self.state_file().read_bytes()
        st = self.SM.load_state(self.pid)
        st["last_accepted_segment"] = 3       # >= current_segment (1)
        with self.assertRaises(self.S.SchemaError):
            self.SM.save_state(self.pid, st)
        self.assertEqual(self.state_file().read_bytes(), good)

    def test_set_plan_keeps_accepted_work(self):
        """task 27: re-planning must not discard accepted segments."""
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        self.SM.set_plan(self.pid, make_plan(4))
        st = self.state()
        self.assertEqual(st["last_accepted_segment"], 1)
        self.assertEqual(st["current_segment"], 2)
        self.assertEqual(len(st["accepted"]), 1)
        self.assertEqual(st["plan_version"], 2)
        self.assertEqual(st["segment_count"], 4)

    def test_set_plan_rejects_an_invalid_plan(self):
        bad = make_plan(2)
        bad["segments"][0]["beat"] = ""
        with self.assertRaises(self.S.SchemaError):
            self.SM.set_plan(self.pid, bad)
        self.assertFalse((self.P.PROJECTS_ROOT / self.pid / "STORY_PLAN.json").exists())

    def test_history_is_appended_on_every_saved_transition(self):
        self.set_plan(3)
        self.generate()
        st = self.state()
        self.assertEqual([h["status"] for h in st["history"]],
                         ["READY", "GENERATING", "CANDIDATE_READY"])

    def test_atomic_write_uses_a_unique_temp_name(self):
        """A fixed temp name is the known Windows PermissionError failure mode."""
        import inspect
        src = inspect.getsource(self.P.atomic_write_json)
        self.assertIn("mkstemp", src)
        self.assertNotIn('".v28_state.tmp"', src)
        self.assertNotIn("TMP_NAME", src)
        target = self.P.PROJECTS_ROOT / self.pid / "ATOMIC_PROBE.json"
        for i in range(12):
            self.P.atomic_write_json(target, {"i": i})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"i": 11})
        leftovers = [p.name for p in target.parent.glob(".ATOMIC_PROBE.json.*")]
        self.assertEqual(leftovers, [], f"temp files leaked: {leftovers}")

    def test_nothing_is_written_outside_the_temp_root(self):
        """The audit must not pollute the real project library."""
        before = B.fingerprint_all()
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        self.SM.mark_error(self.pid, "boom")
        self.SM.prepare_reroll(self.pid)
        self.assertEqual(B.fingerprint_all(), before)
