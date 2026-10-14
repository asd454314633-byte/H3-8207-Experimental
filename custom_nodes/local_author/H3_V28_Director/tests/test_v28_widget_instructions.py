"""widget_instructions(): the one place that decides Motion Context indices.

Invariant under test (V27 freeze record):
    motion_context.load_clip_index == last_accepted_segment   (0 == none yet)
    motion_context.save_clip_index == current_segment         (the clip about to
                                                               be generated)
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402
from test_v28_state_machine import StateMachineCase, make_plan             # noqa: E402


class TestWidgetInstructions(StateMachineCase):

    def test_seg1_load_index_is_zero(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid)
        mc = wi["motion_context"]
        self.assertEqual(mc["load_clip_index"], 0)
        self.assertEqual(mc["save_clip_index"], 1)
        # P11 BUG-7：第一段也必须「开启」——关闭会把 993-997 整组（含存档节点 995）
        # 一起 BYPASS，第一段就永远写不出 clip_00001，accept() 随即死锁。
        self.assertEqual(wi["continuation"]["value"], self.SM.CONT_ON)
        self.assertEqual(mc["chain_segments"], 3)

    def test_load_equals_last_accepted_and_save_equals_current(self):
        self.set_plan(3)
        for expected in (1, 2, 3):
            wi = self.SM.widget_instructions(self.pid)
            st = self.state()
            self.assertEqual(wi["segment_id"], st["current_segment"])
            self.assertEqual(wi["motion_context"]["load_clip_index"],
                             st["last_accepted_segment"], wi["motion_context"])
            self.assertEqual(wi["motion_context"]["save_clip_index"],
                             st["current_segment"], wi["motion_context"])
            self.assertEqual(wi["motion_context"]["expected_slot"],
                             str(self.PJ.mc_slot_path(st["current_segment"])))
            self.assertEqual(wi["advance_without_queue"], True)
            if expected == 3:
                break
            self.slot(wi["segment_id"])
            self.SM.mark_generating(self.pid, instruction=wi)
            self.SM.mark_candidate(self.pid, video=f"clip{wi['segment_id']}.mp4",
                                   seed=wi["seed"])
            self.SM.accept(self.pid)
        self.assertEqual(self.state()["last_accepted_segment"], 2)
        self.assertEqual(self.state()["current_segment"], 3)

    def test_continuation_branch_stays_on_from_the_first_segment(self):
        """P11 BUG-7：曾经的名字是 “…is_on_only_after_the_first_accept”，那条契约是错的。

        接续开关一关，h3_workflow_ux.js 会把带 h3_continuation_branch 的 993-997
        全置 mode=4，其中 995 就是本段存档节点——第一段于是永远产不出
        output/h3_context/clip_00001.safetensors，而 accept() 恰恰要求该段存档存在，
        于是第一次【接受并下一步】就死锁。官方 v0.6.2 自己的连拍契约是
        “First clip: 1 here and 0 on the Load node”（Motion-Context nodes.py:1014-1016），
        即分支保持激活、由 clip_index 区分首段。本例把这条不变量钉住。
        """
        self.set_plan(3)
        first = self.SM.widget_instructions(self.pid)
        self.assertEqual(first["continuation"]["value"], self.SM.CONT_ON,
                         "第一段的接续开关必须是「开启」，否则本段存档节点一起被 BYPASS")
        self.assertEqual(first["motion_context"]["load_clip_index"], 0,
                         "首尾差别只允许体现在 load 序号上，不是开关上")
        self.assertEqual(first["motion_context"]["save_clip_index"], 1)
        self.generate()
        self.SM.accept(self.pid)
        wi = self.SM.widget_instructions(self.pid)
        self.assertEqual(wi["continuation"]["value"], self.SM.CONT_ON)
        self.assertEqual(wi["motion_context"]["load_clip_index"], 1)
        self.assertEqual(wi["continuation"]["selector_node"], self.P.NODE["continuation_switch"])
        self.assertTrue(wi["continuation"]["must_fire_callback"])

    def test_prompt_and_frames_targets_come_from_v27_node_map(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid)
        self.assertEqual(wi["prompt_target_node"], self.P.NODE["console"])
        self.assertEqual(wi["motion_context"]["load_node"], self.P.NODE["mc_load"])
        self.assertEqual(wi["motion_context"]["save_node"], self.P.NODE["mc_save"])
        self.assertEqual(wi["ref_image_nodes"], list(self.P.NODE["ref_images"]))
        self.assertEqual(wi["expected_frames"], self.P.seconds_to_frames(wi["duration_sec"]))
        self.assertEqual(wi["prompt"], self.PJ.read(self.pid, "STORY_PLAN.json")["segments"][0]["prompt"])
        self.assertEqual(self.P.frames_to_seconds(wi["expected_frames"]),
                         round(wi["expected_frames"] / self.P.H3_FPS, 3))

    def test_load_index_zero_must_not_require_a_slot_on_disk(self):
        self.set_plan(2)
        wi = self.SM.widget_instructions(self.pid)
        self.assertEqual(wi["motion_context"]["load_clip_index"], 0)
        self.assertFalse(self.PJ.mc_slot_exists(0))

    def test_missing_previous_slot_is_refused_instead_of_silently_restarting(self):
        self.set_plan(3)
        self.generate()
        self.SM.accept(self.pid)
        self.PJ.mc_slot_path(1).unlink(missing_ok=True)
        with self.assertRaises(self.SM.GateRefused):
            self.SM.widget_instructions(self.pid)

    def test_explicit_seed_is_honoured(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid, seed=777)
        self.assertEqual(wi["seed"], 777)
        wi2 = self.SM.widget_instructions(self.pid)
        self.assertNotEqual(wi2["seed"], 777)
        self.assertTrue(0 < wi2["seed"] < self.SM.SEED_MAX)


if __name__ == "__main__":
    unittest.main(verbosity=2)
