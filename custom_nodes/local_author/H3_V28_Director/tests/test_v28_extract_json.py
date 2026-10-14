"""extract_json / salvage_truncated tests: the four reply shapes an LLM gives,
plus the truncation positions a real max_tokens cut lands on."""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402

S = B.load("v28_schemas")

PLAN = {"version": 1, "story_goal": "清晨", "global_state": {}, "segments": [
    {"id": 1, "beat": "坐起身", "duration": 10},
    {"id": 2, "beat": "走到窗边", "duration": 10},
    {"id": 3, "beat": "推开窗", "duration": 10}]}
BARE = json.dumps(PLAN, ensure_ascii=False, indent=None)


def cut_before(marker: str, text: str = BARE) -> str:
    """Deterministic truncation: keep the buffer up to (not incl.) `marker`."""
    return text[:text.index(marker)]


class TestExtractJsonHappyPaths(unittest.TestCase):

    def test_bare_json_object(self):
        self.assertEqual(S.extract_json(BARE), PLAN)

    def test_json_code_fence(self):
        self.assertEqual(S.extract_json("```json\n" + BARE + "\n```"), PLAN)

    def test_fence_without_language_tag(self):
        self.assertEqual(S.extract_json("```\n" + BARE + "\n```"), PLAN)

    def test_leading_reasoning_prose(self):
        reply = ("我先梳理参考图。\nFirst I considered a cut at the window, then kept "
                 "same_shot continuity.\n" + BARE)
        self.assertEqual(S.extract_json(reply), PLAN)

    def test_prose_before_and_after(self):
        self.assertEqual(S.extract_json("好的，计划如下：\n" + BARE + "\n以上。"), PLAN)

    def test_top_level_array_reply(self):
        arr = [{"id": 1}, {"id": 2}]
        self.assertEqual(S.extract_json("答案：\n```json\n" + json.dumps(arr) + "\n```"), arr)

    def test_pure_prose_raises_value_error(self):
        with self.assertRaises(ValueError):
            S.extract_json("很抱歉，我无法完成这个任务。")

    def test_empty_reply_raises(self):
        for bad in (None, ""):
            with self.assertRaises(ValueError):
                S.extract_json(bad)


class TestSalvageTruncated(unittest.TestCase):

    def test_salvage_unit_close_bracket(self):
        self.assertEqual(S.salvage_truncated('{"a": 1, "b": [1, 2, '), {"a": 1, "b": [1, 2]})

    def test_salvage_unit_array(self):
        self.assertEqual(S.salvage_truncated('[{"a": 1}, {"a": 2}, {"a"'), [{"a": 1}, {"a": 2}])

    def test_salvage_returns_none_when_nothing_is_truncated(self):
        self.assertIsNone(S.salvage_truncated('{"a": 1}'))

    def test_cut_inside_a_string_value_keeps_the_envelope(self):
        text = cut_before('"推开窗"')            # ... {"id": 3, "beat": <EOT>
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)
        out = S.extract_json(text)
        self.assertIsInstance(out, dict)
        self.assertEqual(out["version"], 1)
        self.assertEqual(out["story_goal"], "清晨")

    def test_cut_right_after_an_element_opening_brace_is_salvaged(self):
        """max_tokens very often stops just after `{`; the complete elements
        before it must still come back."""
        text = cut_before('"id": 2')            # ... {"id": 1, ...}, {<EOT>
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)
        out = S.extract_json(text)
        self.assertIsInstance(out, dict)
        self.assertEqual(out["segments"], [PLAN["segments"][0]], out)

    def test_salvaged_elements_are_complete_not_half_written(self):
        """The docstring promises "cut at the last complete element, drop the
        dangling fragment", so a surviving segment must still validate."""
        text = ('{"version": 1, "story_goal": "g", "global_state": {}, "segments": ['
                '{"id": 1, "beat": "x", "duration": 10}, {"id": 2, "beat": "y", "dur')
        out = S.extract_json(text)
        self.assertIsInstance(out, dict)
        for s in out["segments"]:
            self.assertIn("duration", s, f"salvaged a half-written element: {out}")
            self.assertIn("beat", s, f"salvaged a half-written element: {out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
