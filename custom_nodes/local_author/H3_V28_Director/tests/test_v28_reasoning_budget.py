"""The reasoning-budget wiring and the arithmetic behind §33's ceilings.

Why this file exists (P11 TEST3, the first real vision call on the real card):
`BUDGET[kind]["thinking"]` was pure decoration. Its own comment called it
"advisory", and nothing carried it to llama.cpp - where the reasoning tier is the
command-line flag `--reasoning-budget` and, as measured against a live server,
NOT a request field (`reasoning_budget`, `chat_template_kwargs.reasoning` and
`thinking` in the POST body each produced a byte-identical reply). So
analyze_references declared 512 thinking tokens while the resident server ran
2048, spent its entire 2048-token max_tokens on `reasoning_content`, returned
`content: ""` with `finish_reason: "length"`, and hit its 240 s ceiling 2,015
tokens into generation. It could not have succeeded at any timeout.

These tests lock the three things that made that possible, each in the shape the
bug actually took:
  1. an answer must FIT next to its own thinking, and the clock must cover the
     model's MEASURED speed - not a hoped-for one;
  2. the tier a kind declares must be the tier the provider asks the runtime for;
  3. a resident server on a different tier must be restarted, not "reused".
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402

# ---- measured on this machine, 2026-09-27, P11 receipts -------------------
# decode:  tg = 10.14-11.11 tok/s across the 2,015-token TEST3 run (the server's
#          own print_timing lines); 13.02 tok/s only on a 66-token TEST1 reply.
# prefill: 61.18 tok/s over 2,355 prompt tokens for ONE reference image.
#          The product allows four.
MEASURED_TPS = 10.0                 # pessimistic decode rate
MEASURED_PREFILL_TPS = 61.18
IMAGE_TOKENS = 2000                 # ~2,000 of the 2,355 were the single image
MAX_IMAGES = 4
PREFILL_ALL_IMAGES_S = IMAGE_TOKENS * MAX_IMAGES / MEASURED_PREFILL_TPS


class TestBudgetArithmetic(unittest.TestCase):
    """The ceilings have to be reachable by the model that is actually installed."""

    def setUp(self):
        self.V = B.load("v28_provider")
        self.R = B.load("v28_bonsai_runtime")

    def test_answer_fits_beside_its_own_thinking(self):
        for kind, b in self.V.BUDGET.items():
            tier = self.R.THINKING_BUDGET.get(b["thinking"])
            self.assertIsNotNone(tier, f"{kind}: thinking tier {b['thinking']!r} is not a tier")
            self.assertGreaterEqual(
                b["max_tokens"] - tier, self.V.MIN_ANSWER_TOKENS,
                f"{kind}: max_tokens {b['max_tokens']} minus a {tier}-token thinking "
                f"budget leaves {b['max_tokens'] - tier} tokens for the answer - the "
                f"server will spend everything on reasoning_content and return an "
                f"empty content, which is exactly P11 TEST3")

    def test_clock_covers_measured_speed_not_a_hoped_for_one(self):
        for kind, b in self.V.BUDGET.items():
            needed = PREFILL_ALL_IMAGES_S + b["max_tokens"] / MEASURED_TPS
            self.assertGreaterEqual(
                b["timeout_s"], needed,
                f"{kind}: timeout_s {b['timeout_s']} cannot cover {b['max_tokens']} "
                f"tokens at the measured {MEASURED_TPS} tok/s plus "
                f"{round(PREFILL_ALL_IMAGES_S)}s of four-image prefill "
                f"(needs {round(needed)}s)")

    def test_the_rule_rejects_the_shape_test3_shipped_with(self):
        """Positive control: the arithmetic above must be strong enough to have
        failed the OLD analyze row (2048 max_tokens, 240 s, medium=2048 resident).
        A rule that only passes today's table proves nothing."""
        old_max, old_timeout, old_tier = 2048, 240, 2048
        self.assertLess(old_max - old_tier, self.V.MIN_ANSWER_TOKENS,
                        "headroom rule too weak: it would have passed 2048/2048")
        self.assertLess(old_timeout, PREFILL_ALL_IMAGES_S + old_max / MEASURED_TPS,
                        "clock rule too weak: it would have passed a 240s ceiling")




class TestNeedsTierRestart(unittest.TestCase):
    """The reuse decision, isolated: it is the only place a wrong answer costs a
    silent tier mismatch instead of an error."""

    def setUp(self):
        self.R = B.load("v28_bonsai_runtime")

    def test_matrix(self):
        n = self.R.needs_tier_restart
        self.assertTrue(n("low", "medium"), "the TEST3 case: asked low, resident medium")
        self.assertTrue(n("high", "off"))
        self.assertFalse(n("low", "low"), "same tier must reuse, never reload a 27B")
        self.assertFalse(n("low", None), "unknown live tier: a guess would throw away "
                                         "a working model, so leave it alone")
        self.assertFalse(n("low", "started-by-an-older-build"))
        self.assertFalse(n(None, "medium"))
        self.assertFalse(n("", "medium"))




if __name__ == "__main__":
    unittest.main()
