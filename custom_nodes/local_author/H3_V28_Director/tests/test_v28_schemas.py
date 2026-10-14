"""STORY_PLAN / REFERENCE_PROFILE schema tests (stdlib unittest only)."""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402

S = B.load("v28_schemas")


def segment(i, beat, duration=10.0, **directives):
    d = {"join": "continuous", "camera": "hold", "framing": "keep",
         "pace": "steady", "tail": "ongoing"}
    d.update(directives)
    return {
        "id": i, "beat": beat,
        "start_state": {"pose": "seated on the bed edge", "facing": "left"},
        "end_state": {"pose": "standing by the window", "facing": "window"},
        "directives": d,
        "prompt": f"She carries out beat {i} slowly and continuously.",
        "duration": duration, "seed": None, "locked": False,
    }


def plan(n=3):
    beats = ["清晨她坐起身", "她走向窗边", "她推开窗"][:n]
    return {
        "version": 1,
        "story_goal": "一个清晨醒来的连续长镜头",
        "global_state": {"identities": ["女主角"], "visual_style": "Cinematic live-action",
                         "scene": "卧室"},
        "references": {"picture_count": 1, "picture_indices": [1]},
        "style": "auto",
        "continuation_mode": "same_shot",
        "warnings": [],
        "segments": [segment(i + 1, b) for i, b in enumerate(beats)],
    }


class TestStoryPlanValidation(unittest.TestCase):

    def test_valid_plan_passes(self):
        self.assertEqual(S.validate_story_plan(plan()), [])

    def test_unknown_top_level_key_is_an_error(self):
        p = plan()
        p["shots"] = copy.deepcopy(p["segments"])
        errs = S.validate_story_plan(p)
        self.assertTrue(any("shots" in e and "unknown key" in e for e in errs), errs)

    def test_unknown_segment_key_is_an_error(self):
        p = plan()
        p["segments"][0]["motion_note"] = "x"
        errs = S.validate_story_plan(p)
        self.assertTrue(any("motion_note" in e for e in errs), errs)

    def test_non_contiguous_segment_ids_are_an_error(self):
        p = plan(2)
        p["segments"][1]["id"] = 7
        errs = S.validate_story_plan(p)
        self.assertTrue(any("must equal index+1" in e for e in errs), errs)
        self.assertTrue(any("no gaps" in e for e in errs), errs)

    def test_duplicate_beat_is_an_error(self):
        p = plan(3)
        p["segments"][2]["beat"] = p["segments"][0]["beat"]
        errs = S.validate_story_plan(p)
        self.assertTrue(any("identical beats" in e for e in errs), errs)

    def test_illegal_directive_value_is_an_error(self):
        p = plan()
        p["segments"][0]["directives"]["camera"] = "zoom_boost"
        errs = S.validate_story_plan(p)
        self.assertTrue(any("camera" in e for e in errs), errs)

    def test_empty_segments_is_an_error(self):
        p = plan()
        p["segments"] = []
        self.assertTrue(any("$.segments" in e for e in S.validate_story_plan(p)))

    def test_check_raises_schema_error_with_paths(self):
        p = plan()
        p["segments"][0]["beat"] = "   "
        with self.assertRaises(S.SchemaError) as ctx:
            S.check("story_plan", p)
        self.assertTrue(any(".beat" in e for e in ctx.exception.errors), ctx.exception.errors)


class TestNormalizeStoryPlan(unittest.TestCase):

    def minimal(self):
        """What a lax model reply plausibly looks like: bare string beats."""
        return {"story_goal": "g", "global_state": {},
                "segments": [{"beat": "起床"}, {"beat": "走到窗边"}, {"beat": "开窗"}]}

    def test_normalize_idempotent_byte_identical(self):
        once = S.normalize_story_plan(self.minimal())
        twice = S.normalize_story_plan(once)
        a = json.dumps(once, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        b = json.dumps(twice, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self.assertEqual(a, b)
        c = json.dumps(once, ensure_ascii=False, indent=2)
        d = json.dumps(twice, ensure_ascii=False, indent=2)
        self.assertEqual(c, d, "key order differs -> not idempotent byte-for-byte")

    def test_normalize_fills_ids_defaults_and_tail(self):
        out = S.normalize_story_plan(self.minimal())
        self.assertEqual([s["id"] for s in out["segments"]], [1, 2, 3])
        for s in out["segments"]:
            self.assertEqual(s["directives"]["tail"], S.TAIL_DEFAULT)
            self.assertEqual(s["duration"], 10)
            self.assertIsNone(s["seed"])
            self.assertFalse(s["locked"])
            self.assertIsInstance(s["start_state"], dict)

    def test_normalize_never_invents_beats(self):
        out = S.normalize_story_plan(self.minimal())
        self.assertEqual([s["beat"] for s in out["segments"]], ["起床", "走到窗边", "开窗"])

    def test_normalized_plan_still_validates_against_story_plan(self):
        """The repair loop normalises then validates, so these two must agree."""
        out = S.normalize_story_plan(self.minimal())
        errs = S.validate_story_plan(out)
        self.assertEqual(errs, [], f"normalize output rejected by validator: {errs}")

    def test_normalize_is_pure_does_not_mutate_input(self):
        src = self.minimal()
        before = json.dumps(src, ensure_ascii=False, sort_keys=True)
        S.normalize_story_plan(src)
        self.assertEqual(json.dumps(src, ensure_ascii=False, sort_keys=True), before)


class TestValueTypesAreChecked(unittest.TestCase):
    """Keys being present is half the contract; their TYPE is the other half.

    The reference profile is a vision model's reply and its consumers index into it
    (`(profile.get("scene") or {}).get("seen")` in the compiler and in the repair
    feedback). Before PROFILE_TYPES existed, `{"scene": "夜晚的街道"}` passed the
    boundary and died as a bare AttributeError several steps later - where §34's
    repair loop can no longer quote a JSON path back to the model. These tests are
    the reason the two rules were added, so they belong to the validator, not to a
    document.
    """

    def profile(self):
        return {
            "version": 1,
            "source_pictures": [{"index": 1, "filename": "a.png",
                                 "width": 1024, "height": 1024}],
            "subjects": [{"id": "subject_1", "picture_refs": [1], "role": "女主角",
                          "seen": {"hair": "black hair", "glasses": "", "wardrobe": {},
                                   "distinctive_appearance": [], "visible_pose": {}},
                          "inferred": {}, "do_not_infer": ["未来运动"]}],
            "scene": {"seen": {"space": "bedroom"}, "inferred": {}},
            "props": [],
            "composition": {"seen": {}, "inferred": {}},
            "uncertain": [], "not_answerable": [],
        }

    def test_honest_profile_passes(self):
        self.assertEqual(S.validate_reference_profile(self.profile()), [])

    def test_a_string_scene_is_refused_at_the_boundary(self):
        p = self.profile()
        p["scene"] = "夜晚的街道"
        errs = S.validate_reference_profile(p)
        self.assertTrue(any("$.scene" in e and "must be dict" in e for e in errs), errs)

    def test_a_list_where_a_dict_is_required_is_refused(self):
        p = self.profile()
        p["composition"] = [{"shot_size": "medium"}]
        self.assertTrue(any("$.composition" in e for e in
                            S.validate_reference_profile(p)), S.validate_reference_profile(p))

    def test_a_dict_where_a_list_is_required_is_refused(self):
        p = self.profile()
        p["source_pictures"] = {"index": 1}
        self.assertTrue(any("$.source_pictures" in e for e in
                            S.validate_reference_profile(p)))

    def test_a_version_written_as_a_string_or_bool_is_refused(self):
        for bad in ("1", True):
            p = self.profile()
            p["version"] = bad
            errs = S.validate_reference_profile(p)
            self.assertTrue(any("$.version" in e for e in errs), f"{bad!r}: {errs}")

    def test_a_missing_key_is_still_a_presence_error_not_a_type_error(self):
        p = self.profile()
        del p["props"]
        errs = S.validate_reference_profile(p)
        self.assertTrue(any("props" in e for e in errs), errs)
        self.assertFalse(any("$.props must be" in e for e in errs),
                         f"absence must not be reported as a wrong type: {errs}")

    def test_locked_must_be_a_real_boolean(self):
        """`locked` gates §27's accept protection, and any non-empty string is
        truthy in Python - "false" would silently lock a segment nobody accepted."""
        for bad in ("true", 1, "False"):
            p = plan()
            p["segments"][0]["locked"] = bad
            errs = S.validate_story_plan(p)
            self.assertTrue(any("locked" in e for e in errs), f"{bad!r}: {errs}")
        good = plan()
        good["segments"][0]["locked"] = True
        self.assertEqual(S.validate_story_plan(good), [])
        null = plan()
        null["segments"][0]["locked"] = None
        self.assertEqual(S.validate_story_plan(null), [], "null means 'not decided yet'")




if __name__ == "__main__":
    unittest.main(verbosity=2)
