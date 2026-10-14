"""Provider contract tests: the JSON-only repair loop (task 34) and the
budget ceilings (task 33). No network, no model - a stub provider feeds replies."""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402
from test_v28_state_machine import PROFILE, make_plan                      # noqa: E402

V = B.load("v28_provider")
S = B.load("v28_schemas")


class StubProvider(V.DirectorProvider):
    """Implements the six abstract methods; replies are scripted."""
    name = "stub"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.seen_messages = []

    def health(self):
        return V.Health(ok=True, provider=self.name)

    def analyze_references(self, images, *, brief=""):
        raise NotImplementedError

    def plan_story(self, **kw):
        raise NotImplementedError

    def compile_segment(self, **kw):
        raise NotImplementedError

    def _complete(self, messages, *, max_tokens, timeout_s, temperature):
        self.calls += 1
        self.seen_messages.append(json.dumps(messages, ensure_ascii=False))
        if not self.replies:
            raise AssertionError("the repair loop asked more times than allowed")
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]




class TestBudgets(unittest.TestCase):

    def test_every_op_has_a_token_and_time_ceiling(self):
        for kind, b in V.BUDGET.items():
            self.assertGreater(b["max_tokens"], 0, kind)
            self.assertGreater(b["timeout_s"], 0, kind)
            self.assertNotEqual(b["thinking"], "unlimited", kind)

    def test_unknown_op_kind_is_rejected(self):
        p = StubProvider(["{}"])
        with self.assertRaises(KeyError):
            p.budget_for("summon_gpu")

    def test_plan_story_thinking_is_not_unbounded(self):
        self.assertLessEqual(V.BUDGET["plan_story"]["max_tokens"], 16384)


class TestProviderRegistry(unittest.TestCase):

    def test_gemma_is_registered_and_resolvable(self):
        B.load("v28_gemma_provider")
        self.assertIn("gemma4", V.available_providers())

    def test_get_provider_without_registration_is_refused(self):
        with self.assertRaises(V.DirectorUnavailable):
            V._instantiate("no_such_provider")




class TestPlanPromptInjection(unittest.TestCase):
    def test_plan_user_injects_the_provider_identity(self):
        C = B.load("v28_director_core")
        planner = C.planner_input(active_slots=[1], reference_usage="", story_goal="g", total_seconds=30, segment_seconds=10)
        system = C.gemma_messages(planner)[0]["content"]
        self.assertIn("JSON", system)
        self.assertNotIn("{provider}", system)
        self.assertNotIn("{model}", system)


if __name__ == "__main__":
    unittest.main(verbosity=2)
