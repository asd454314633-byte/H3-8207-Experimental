"""BUG-9 additive display: planned (expected_frames) vs actually-delivered frames.

The fix is strictly ADDITIVE:

  * ``mark_candidate`` now also records ``actual_delivered_frames`` (the real
    frame count of the generated video, probed via ffprobe) alongside the
    pre-existing ``expected_frames``. It never alters ``expected_frames``.
  * The Chinese card (h3_director_v28.js) shows both numbers during review, so a
    human watching the clip can see the planned-vs-delivered gap.

These tests pin the contract: the new field exists and is additive, the old
``expected_frames`` semantics are unchanged (still V27's N131 frame law), and
the probe is graceful (returns None, never raises) when the file or binary is
absent.
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                     # noqa: E402
from test_v28_state_machine import StateMachineCase, make_plan                  # noqa: E402


class TestBug9FrameDisplay(StateMachineCase):

    def test_continuation_192_plan_22_trim_displays_170(self):
        facts = self.SM.frame_delivery_facts({
            "expected_frames": 192, "actual_delivered_frames": None,
            "context_trim": 22, "context_note": None})
        self.assertEqual(facts["expected_frames"], 192)
        self.assertEqual(facts["actual_delivered_frames"], 170)
        self.assertIn("22", facts["context_note"])

    def test_real_delivered_count_wins_and_trim_is_not_applied_twice(self):
        facts = self.SM.frame_delivery_facts({
            "expected_frames": 192, "actual_delivered_frames": 170,
            "context_trim": 22})
        self.assertEqual(facts["actual_delivered_frames"], 170)
        self.assertNotEqual(facts["actual_delivered_frames"], 148)

    def test_first_segment_without_trim_stays_correct(self):
        facts = self.SM.frame_delivery_facts({
            "expected_frames": 192, "actual_delivered_frames": 192,
            "context_trim": None, "context_note": None})
        self.assertEqual(facts["expected_frames"], 192)
        self.assertEqual(facts["actual_delivered_frames"], 192)
        self.assertIsNone(facts["context_note"])

    def test_non_continuation_missing_actual_is_not_invented(self):
        facts = self.SM.frame_delivery_facts({"expected_frames": 192})
        self.assertEqual(facts["expected_frames"], 192)
        self.assertIsNone(facts.get("actual_delivered_frames"))

    def test_mark_candidate_records_actual_delivered_frames_additively(self):
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid)
        self.SM.mark_generating(self.pid, instruction=wi)
        self.slot(wi["segment_id"])
        out = self.SM.mark_candidate(self.pid, video=f"clip_{wi['segment_id']}.mp4",
                                     seed=wi["seed"])
        cand = out["current_candidate"]
        # 1. the new additive field is present (None here: no real video on disk)
        self.assertIn("actual_delivered_frames", cand,
                      "BUG-9: mark_candidate 必须加性写入 actual_delivered_frames")
        # 2. expected_frames is present and UNCHANGED by the fix
        self.assertIn("expected_frames", cand)
        self.assertEqual(cand["expected_frames"],
                         self.P.seconds_to_frames(wi["duration_sec"]))
        # 3. the two are independent: planned is the formula value, delivered is
        #    None here (no real video on disk) - the fix must not conflate them.
        self.assertIsNone(cand["actual_delivered_frames"])
        self.assertNotEqual(cand["actual_delivered_frames"], cand["expected_frames"])

    def test_expected_frames_semantics_are_untouched(self):
        """BUG-9 must NOT change how expected_frames is derived (V27 N131 law)."""
        self.set_plan(3)
        wi = self.SM.widget_instructions(self.pid)
        dur = wi["duration_sec"]
        self.assertEqual(wi["expected_frames"], self.P.seconds_to_frames(dur))
        # recompute the V27 law independently and compare
        a = max(5, round(dur * self.P.H3_FPS))
        expected = int(a + (5 - (a % 17)) % 17)
        self.assertEqual(wi["expected_frames"], expected)

    def test_probe_returns_none_when_video_file_missing(self):
        """Graceful: missing file -> None, never raises."""
        self.assertIsNone(self.SM.probe_video_frame_count("does_not_exist.mp4"))
        self.assertIsNone(self.SM.probe_video_frame_count(""))

    def test_probe_captures_real_frame_count_via_stub(self):
        """End-to-end of the probe path with a stub ffprobe binary."""
        # write a fake video under COMFY_OUTPUT so the file-locate step succeeds
        fake = self.P.COMFY_OUTPUT / "stub_movie.mp4"
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_bytes(b"FAKE-MP4")
        # stub ffprobe that emits a fixed nb_frames (Windows .bat echoes JSON)
        stub = self.root / "stub_ffprobe.bat"
        stub.write_text('@echo {"streams":[{"nb_frames":"170"}]}', encoding="ascii")
        old = os.environ.get("H3V28_FFPROBE_BIN")
        os.environ["H3V28_FFPROBE_BIN"] = str(stub)
        try:
            self.assertEqual(self.SM.probe_video_frame_count("stub_movie.mp4"), 170)
        finally:
            if old is None:
                os.environ.pop("H3V28_FFPROBE_BIN", None)
            else:
                os.environ["H3V28_FFPROBE_BIN"] = old

    def test_full_chain_keeps_both_frame_fields(self):
        """After accept, the accepted record keeps expected_frames and the new field."""
        self.set_plan(3)
        self.generate(expect_seg=1)
        self.SM.accept(self.pid)
        st = self.state()
        acc = st["accepted"][0]
        self.assertIn("video", acc)
        # expected_frames lives on the candidate/segment, not the accepted row;
        # the fix guarantees the candidate carried both frame fields through accept.
        cand_file = sorted((self.P.PROJECTS_ROOT / self.pid / "accepted").glob("seg_001_*.json"))[0]
        cand = self.PJ.read(self.pid, f"accepted/{cand_file.name}")
        self.assertIn("expected_frames", cand)
        self.assertIn("actual_delivered_frames", cand)


if __name__ == "__main__":
    unittest.main(verbosity=2)
