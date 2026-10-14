import copy

from custom_nodes.H3_V28_Director import v28_director_core as C
from custom_nodes.H3_V28_Director import v28_gemma_provider as G
from custom_nodes.H3_V28_Director import v28_provider as V


def planner(total=60, segment=10):
    return C.planner_input(active_slots=[1, 2, 3, 4], reference_usage="图1到图4为用户说明的参考",
                           story_goal="保持原剧情强度并连续推进", total_seconds=total,
                           segment_seconds=segment)


def semantic_segment(i, state="S"):
    body = {k: state for k in C.BODY_STATE_FIELDS}
    return {
        "segment": i, "segment_objective": f"目标{i}", "start_state": f"开始{i}",
        "beats": [f"动作{i}"], "new_action": f"推进{i}", "performance": "自然表演",
        "blocking": "位置明确", "interaction": "关系连续", "camera": "镜头服务动作",
        "reference_usage": [], "dialogue": "", "dialogue_timing": "无台词",
        "ambience": "环境声", "physical_sounds": "动作声", "non_verbal_vocals": "呼吸",
        "music": "", "end_state": f"结束{i}", "continuity_out": "可连续",
        "body_state_start": copy.deepcopy(body), "body_state_end": copy.deepcopy(body),
        "micro_timeline": [{"phase": "EXECUTE", "action": f"动作{i}", "state_change": "推进"}],
        "physical_conflicts": [], "conflict_resolution": "",
        "physical_continuity_notes": [], "anatomy_camera_notes": "",
        "render_risk": {"body_geometry": "LOW", "occlusion": "LOW",
                        "fast_full_body_motion": False},
        "user_display_zh": {"objective": f"目标{i}", "start_state": f"开始{i}",
            "action_progression": f"动作{i}", "blocking": "位置明确", "camera": "跟随动作",
            "dialogue": "无台词", "sound": "环境声", "reference_usage": "按用户说明",
            "end_state": f"结束{i}"},
    }


# --- dialogue contract (official Ref2VA section semantics) ----------------
# An utterance lives in detailed_description and nowhere else. overall_soundscape
# is ambience + non-verbal sound; non_diegetic_music is score. The counted
# quantity is EVENTS, so "the story says it twice" is two renders and passes.

def _dialogue_planner(source, total=30, segment=10):
    return C.planner_input(active_slots=[1], reference_usage="", story_goal="story",
                           total_seconds=total, segment_seconds=segment,
                           dialogue_mode="原文拆分", source_dialogue=source)


def test_dialogue_renders_once_in_detailed_description_only():
    p = _dialogue_planner("钱我明天转过去。别担心！这是第二段；仍然保留。")
    plan = C.validate_director_plan(_plan3(), p)
    for sid in (1, 2, 3):
        prompt = C.compile_h3_prompt(planner=p, plan=plan, segment_id=sid)["CANONICAL_H3_PROMPT"]
        body = C._section_body(prompt, "detailed_description")
        sound = C._section_body(prompt, "overall_soundscape")
        music = C._section_body(prompt, "non_diegetic_music")
        line = plan["segments"][sid - 1]["dialogue"]
        assert prompt.count("<d>") == (1 if line.strip() else 0)
        assert "<d>" not in sound and "<d>" not in music
        assert line in body
        assert not C._dialogue_echo(sound, line) and not C._dialogue_echo(music, line)


def test_two_real_events_render_twice_and_pass_the_count_gate():
    """The gate counts EVENTS, not unique strings: a genuine repeat is legal.

    The track decides the count, so two entries for one segment (the story really
    says it twice) render twice and pass, while one entry rendered twice fails.
    """
    p = _dialogue_planner("走开。走开。", total=10, segment=10)
    p["dialogue_track"]["segments"] = [{"id": 1, "duration_s": 10, "dialogue": "走开。"},
                                       {"id": 1, "duration_s": 10, "dialogue": "走开。"}]
    plan = C.validate_director_plan(_plan3(1), p)
    assert plan["segments"][0]["dialogue"] == "走开。走开。"
    prompt = C.compile_h3_prompt(planner=p, plan=plan, segment_id=1)["CANONICAL_H3_PROMPT"]
    assert prompt.count("<d>") == 2
    assert not C.audit_dialogue_contract(prompt, expected_events=2,
                                         sources=["走开。", "走开。"])
    # ...but the same two blocks against a one-event declaration is a violation.
    assert C.audit_dialogue_contract(prompt, expected_events=1, sources=["走开。走开。"])


def test_a_verbatim_echo_in_the_soundscape_is_rejected():
    """Verbatim or fragment leakage of the line into the audio sections fails.

    A *translated* paraphrase is not textually detectable; the guarantee against
    it is structural - the compiler never carries the line into those sections.
    """
    src = "妈妈好爽，想操你妈吗？"
    prompt = ("subject_definitions:\nx\n\nsummary:\ny\n\nretention_analysis:\nz\n\n"
              "detailed_description:\n[Shot 1] she says <d>[Chinese] " + src + "</d>\n\n"
              "overall_soundscape:\n" + src + " under room tone\n\n"
              "non_diegetic_music:\nN/A")
    assert C._dialogue_echo(C._section_body(prompt, "overall_soundscape"), src)
    errs = C.audit_dialogue_contract(prompt, expected_events=1, sources=[src])
    assert any("重复" in e for e in errs)
    # A wrapped echo is caught twice over: as a block and as verbatim content.
    wrapped = prompt.replace("overall_soundscape:\n" + src,
                             "overall_soundscape:\n<d>[Chinese] " + src + "</d>")
    errs_w = C.audit_dialogue_contract(wrapped, expected_events=1, sources=[src])
    assert any("出现对白块" in e for e in errs_w) and any("重复" in e for e in errs_w)
    clean = prompt.replace("overall_soundscape:\n" + src + " under room tone",
                           "overall_soundscape:\nRoom tone with breathing.")
    assert not C.audit_dialogue_contract(clean, expected_events=1, sources=[src])


def _plan3(n=3):
    from custom_nodes.H3_V28_Director.tests.test_v28_gate6b_core import _plan
    return _plan(n)


def test_segment_skeleton_boundaries_are_program_owned():
    assert [x["duration_sec"] for x in C.build_segment_skeleton(60, 10)] == [10] * 6
    assert [x["duration_sec"] for x in C.build_segment_skeleton(35, 10)] == [10, 10, 10, 5]
    assert [x["duration_sec"] for x in C.build_segment_skeleton(10, 10)] == [10]
    assert C.build_segment_skeleton(35, 10)[-1] == {
        "segment_index": 4, "start_time": 30.0, "end_time": 35.0, "duration_sec": 5.0}


def test_missing_and_extra_model_segments_align_without_count_repair():
    p = planner()
    raw = {"segments": [semantic_segment(i) for i in range(1, 6)] + [semantic_segment(7)]}
    aligned, report = C.align_plan_to_skeleton(raw, p)
    assert [x["segment_index"] for x in aligned["segments"]] == [1, 2, 3, 4, 5, 6]
    assert report["missing_segment_ids"] == [6]
    assert report["ignored_extra_segments"] == [7]
    assert aligned["segments"][-1]["duration_sec"] == 10


def test_a_reply_that_filled_the_skeleton_copy_is_still_a_complete_plan():
    """Gate-8B R3: the real reply put its content in `segment_skeleton`, not `segments`.

    It was complete and correctly typed. Reading only `segments` turned it into
    six empty segments and spent the whole repair budget on no-ops.
    """
    p = planner()
    filled = []
    for clock in p["segment_skeleton"]:
        item = dict(clock)
        item.update(semantic_segment(int(clock["segment_index"])))
        filled.append(item)
    aligned, report = C.align_plan_to_skeleton({"segment_skeleton": filled}, p)
    assert [x["segment_index"] for x in aligned["segments"]] == [1, 2, 3, 4, 5, 6]
    assert report["missing_segment_ids"] == []
    assert report["ignored_extra_segments"] == []


def test_a_pure_clock_skeleton_is_not_mistaken_for_content():
    p = planner()
    aligned, report = C.align_plan_to_skeleton({"segment_skeleton": p["segment_skeleton"]}, p)
    assert report["missing_segment_ids"] == [1, 2, 3, 4, 5, 6]


def test_a_wrapped_fill_patch_is_unwrapped_and_normalized():
    patch = {"fields_to_fill": {"micro_timeline": "0-3s: slow thrust",
                                "beats": "one beat", "render_risk": "keep it clean",
                                "user_display_zh": {"objective": "目标"}}}
    out = C.normalize_segment_patch(patch, ["micro_timeline", "beats", "render_risk",
                                            "user_display_zh"])
    assert out["micro_timeline"] == [{"phase": "EXECUTE", "action": "0-3s: slow thrust",
                                      "state_change": ""}]
    assert out["beats"] == ["one beat"]
    assert out["render_risk"] == {"body_geometry": "LOW", "occlusion": "LOW",
                                  "fast_full_body_motion": False}
    assert out["user_display_zh"]["objective"] == "目标"


def test_a_bare_hold_phase_normalizes_to_final_hold_not_a_failure():
    out = C.normalize_segment_patch(
        {"micro_timeline": [{"phase": "HOLD", "action": "x", "state_change": ""}]},
        ["micro_timeline"])
    assert out["micro_timeline"][0]["phase"] == "FINAL_HOLD"


def test_invalid_local_enum_is_a_targeted_field_gap():
    seg = semantic_segment(1)
    seg["micro_timeline"][0]["phase"] = "HOLD"
    assert C.segment_content_gaps(seg) == ["micro_timeline"]


class StubGemma(G.Gemma4TextDirectorProvider):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def ensure_tier(self, thinking):
        return None

    def _complete(self, messages, *, max_tokens, timeout_s, temperature):
        import json
        self.calls.append(messages)
        reply = self.replies.pop(0)
        return json.dumps(reply, ensure_ascii=False)


def test_normal_plan_is_one_full_call_and_zero_repairs():
    p = planner()
    reply = {"segments": [semantic_segment(i) for i in range(1, 7)]}
    provider = StubGemma([reply])
    out = provider.plan_story(story_goal=p["story_goal"],
                              profile={"director_input": p}, total_seconds=60,
                              segment_seconds=10, expect_segments=6)
    metrics = out["generated_from"]
    assert len(provider.calls) == 1
    assert metrics["full_plan_llm_calls"] == 1
    assert metrics["full_plan_repair_calls"] == 0
    assert metrics["segment_count_llm_repair_calls"] == 0
    assert metrics["targeted_repair_calls"] == 0


def test_a_fully_degraded_reply_fails_bounded_never_as_a_six_way_rewrite():
    """Worst case: a bounded failure with a ceiling, not a plan-wide loop."""
    p = planner()
    empty = {"segments": [{"segment_index": i} for i in range(1, 7)]}
    provider = StubGemma([empty] + [{}] * 12)
    try:
        provider.plan_story(story_goal=p["story_goal"],
                            profile={"director_input": p}, total_seconds=60,
                            segment_seconds=10, expect_segments=6)
    except V.SchemaRepairFailed:
        pass
    # 1 full plan call + at most MAX_TARGETED_REPAIR_CALLS segment-local fills.
    assert len(provider.calls) <= 1 + V.MAX_TARGETED_REPAIR_CALLS


def test_targeted_repair_has_its_own_budget_not_the_whole_plan_one():
    """A fill must not inherit plan_story's 9000-token / 1500 s ceiling."""
    b = V.BUDGET["segment_repair"]
    assert b["max_tokens"] < V.BUDGET["plan_story"]["max_tokens"]
    assert b["timeout_s"] < V.BUDGET["plan_story"]["timeout_s"]


def test_missing_sixth_segment_gets_one_targeted_fill_not_full_rewrite():
    p = planner()
    initial = {"segments": [semantic_segment(i) for i in range(1, 6)]}
    sixth = semantic_segment(6)
    provider = StubGemma([initial, sixth])
    out = provider.plan_story(story_goal=p["story_goal"],
                              profile={"director_input": p}, total_seconds=60,
                              segment_seconds=10, expect_segments=6)
    metrics = out["generated_from"]
    assert len(provider.calls) == 2
    assert metrics["full_plan_llm_calls"] == 1
    assert metrics["full_plan_repair_calls"] == 0
    assert metrics["segment_count_llm_repair_calls"] == 0
    assert metrics["targeted_repair_calls"] == 1
    assert metrics["targeted_repaired_segments"] == [6]
    assert [x["segment_index"] for x in out["segments"]] == [1, 2, 3, 4, 5, 6]
