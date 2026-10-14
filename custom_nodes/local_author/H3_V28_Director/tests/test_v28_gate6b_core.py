import pytest
from _v28_bootstrap import load

C = load("v28_director_core")
PC = load("v28_h3_format")


def _plan(n=1, dialogue=""):
    return {"segments": [{"segment": i + 1, "duration": 10, "start_state": "start",
             "segment_objective": "推进动作", "beats": ["walks forward"],
             "new_action": "walks forward", "performance": "natural", "blocking": "clear",
             "interaction": "consistent", "camera": "tracks the action",
             "reference_usage": [], "dialogue": dialogue,
             "dialogue_timing": "00:02", "ambience": "room tone",
             "physical_sounds": "footsteps", "non_verbal_vocals": "breathing",
             "music": "soft score", "end_state": "standing", "continuity_out": "standing",
             "user_display_zh": {"objective":"推进动作","start_state":"站立",
                "action_progression":"向前走","blocking":"位置清楚","camera":"跟随",
                "dialogue": dialogue or "无台词", "sound":"脚步与呼吸",
                "reference_usage":"按用户指定", "end_state":"站定"}} for i in range(n)]}


@pytest.mark.parametrize("slots", [[1], [1,2,3,4], [1,5,9], list(range(1,10))])
def test_canonical_mapping(slots):
    assert C.active_reference_map(slots) == [
        {"ui_slot": x, "h3_picture": i + 1} for i, x in enumerate(slots)]


def test_sparse_translation_and_missing_fail_closed():
    m = C.active_reference_map([1,5,9])
    out = C.compile_reference_text("图5只参考身体；图9作为最终构图", m)
    assert "<Picture 5>" in out["compiled_reference_text"]
    assert "<Picture 9>" in out["compiled_reference_text"]
    assert out["REFERENCE_TIMELINE"] == "EXPLICIT_ONLY"
    with pytest.raises(C.DirectorCompileError, match="REFERENCE_SLOT_MISSING"):
        C.compile_reference_text("图4参考服装", m)


def test_attribute_and_anchor_can_coexist_and_default_none():
    m = C.active_reference_map([4])
    both = C.compile_reference_text("图4参考表情，同时作为最后画面", m)
    assert both["reference_relationships"][0]["reference_attribute"]
    assert both["reference_relationships"][0]["keyframe_anchor"]
    assert C.compile_reference_text("图4参考表情", m)["REFERENCE_TIMELINE"] == "NONE"


def test_general_reference_no_vision_and_text_only_gemma():
    p = C.planner_input(active_slots=[1], reference_usage="", story_goal="story",
                        total_seconds=10, segment_seconds=10)
    assert p["GEMMA_VISION"] == "OFF"
    assert C.compile_h3_prompt(planner=p, plan=_plan(), segment_id=1)["CANONICAL_H3_PROMPT"].startswith("subject_definitions:")
    assert "GENERAL_REFERENCE" not in C.compile_h3_prompt(planner=p, plan=_plan(), segment_id=1)["CANONICAL_H3_PROMPT"]
    assert "image_url" not in str(C.gemma_messages(p))


def test_six_sections_audio_and_same_canonical_object():
    p = C.planner_input(active_slots=[1,3,7,9], reference_usage="图1和图3参考身份；图7参考服装；图9最终构图",
                        story_goal="A scene", total_seconds=10, segment_seconds=10)
    b = C.compile_h3_prompt(planner=p, plan=_plan(dialogue="(S1) <d>[Chinese] 你好</d>"), segment_id=1)
    assert all(f"{x}:" in b["CANONICAL_H3_PROMPT"] for x in C.SECTIONS)
    # H3 reads the voice tag from inside the block, and audit_prompt rejects an
    # untagged one - so the tag is part of the compiled contract.
    assert "<d>[Chinese] 你好</d>" in b["CANONICAL_H3_PROMPT"]
    assert not PC.audit_prompt(b["CANONICAL_H3_PROMPT"]), PC.audit_prompt(b["CANONICAL_H3_PROMPT"])
    assert "room tone" in b["CANONICAL_H3_PROMPT"] and "soft score" in b["CANONICAL_H3_PROMPT"]
    assert b["UI_PREVIEW"] == b["SUBMISSION_PROMPT"]
    assert b["PREVIEW_SHA256"] == b["SUBMISSION_PROMPT_SHA256"]
    assert not any(x in b["CANONICAL_H3_PROMPT"] for x in C.LEGACY_TAGS)


def test_lossless_dialogue_and_no_dialogue():
    source = "钱我明天转过去。别担心！这是第二段；仍然保留。"
    p = C.planner_input(active_slots=[1], reference_usage="", story_goal="story",
                        total_seconds=30, segment_seconds=10, dialogue_mode="原文拆分",
                        source_dialogue=source)
    plan = C.validate_director_plan(_plan(3), p)
    r = C.validate_dialogue_track(source, [x["dialogue"] for x in plan["segments"]])
    assert r["passed"] and r["MISSING_CHAR"] == r["DUPLICATED_CHAR"] == r["REORDERED_TEXT"] == 0
    p2 = C.planner_input(active_slots=[1], reference_usage="", story_goal="story",
                         total_seconds=10, segment_seconds=10, dialogue_mode="无台词")
    assert not C.validate_director_plan(_plan(), p2)["segments"][0]["dialogue"]


def test_native_bypass_byte_identity():
    p = C.planner_input(active_slots=[], reference_usage="", story_goal="",
                        total_seconds=10, segment_seconds=10)
    raw = "native prompt\nkept byte-for-byte"
    b = C.compile_h3_prompt(planner=p, plan=_plan(), segment_id=1,
                            raw_native_prompt=raw, director_enabled=False)
    assert b["path"] == "RAW_NATIVE_H3_PATH" and b["CANONICAL_H3_PROMPT"] == raw


@pytest.mark.parametrize("slots,text,timeline", [
    ([1], "", "NONE"),
    ([1,2,3,4], "图1和图2参考容貌；图3参考身体；图4参考表情", "NONE"),
    ([1,5,9], "图1参考服装；图5参考动作；图9最终画面", "EXPLICIT_ONLY"),
    (list(range(1,10)), "图1和图3共同定义人物A；图7参考服装；图9最终构图", "EXPLICIT_ONLY"),
    ([1], "图1同时参考人物容貌和服装", "NONE"),
    ([1,3], "图1和图3共同定义同一人物", "NONE"),
    ([4], "图4参考表情，同时作为最后一帧", "EXPLICIT_ONLY"),
])
def test_frozen_matrix_reference_cases(slots, text, timeline):
    out = C.compile_reference_text(text, C.active_reference_map(slots))
    assert out["REFERENCE_TIMELINE"] == timeline
    assert not any(tag in out["compiled_reference_text"] for tag in C.LEGACY_TAGS)


def test_gemma_runtime_is_cuda_fail_closed_and_text_only():
    runtime = (C.__file__.replace("v28_director_core.py", "v28_gemma_runtime.py"))
    text = open(runtime, encoding="utf-8").read()
    assert '"ggml-cuda.dll"' in text and '"cudart64_13.dll"' in text
    assert '"nvcuda.dll"' in text and '"CUDA0"' in text and '"offloaded"' in text
    assert "禁止 CPU fallback" in text
