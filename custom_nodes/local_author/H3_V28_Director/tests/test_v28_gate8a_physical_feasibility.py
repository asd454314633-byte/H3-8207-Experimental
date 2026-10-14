import copy

import pytest

import _v28_bootstrap as B

C = B.load("v28_director_core")


def planner(count=1, reference_usage="图1参考人物容貌"):
    return C.planner_input(active_slots=[1], reference_usage=reference_usage,
                           story_goal="保持原始高强度动作并形成可接续段尾",
                           total_seconds=10 * count, segment_seconds=10)


def body(**changes):
    value = {k: "NOT_RELEVANT" for k in C.BODY_STATE_FIELDS}
    value.update({"body_orientation": "reclined front three-quarter",
                  "torso_orientation": "front three-quarter",
                  "pelvis_orientation": "supported on sofa",
                  "weight_distribution": "supported on sofa",
                  "contact_state": "body supported by sofa; prop held in right hand",
                  "prop_owner": "right hand", "camera_side": "front three-quarter"})
    value.update(changes)
    return value


def segment(index=1, *, risk="HIGH"):
    return {
        "segment": index, "duration": 10,
        "segment_objective": "保留高强度核心动作并给出完整因果路径",
        "start_state": "人物斜靠沙发，右手持道具。",
        "beats": ["重心先由靠背承托", "右臂逐步执行核心动作", "躯干响应后稳定"],
        "new_action": "执行原始高强度核心动作",
        "performance": "强烈且持续", "blocking": "身体由沙发承托",
        "interaction": "右手持道具并保持接触连续", "camera": "前侧中景缓慢靠近",
        "reference_usage": [], "dialogue": "", "dialogue_timing": "",
        "ambience": "室内", "physical_sounds": "接触声", "non_verbal_vocals": "呼吸声",
        "music": "", "end_state": "人物仍斜靠沙发，右手持道具，可继续动作。",
        "continuity_out": "保持承托、接触和镜头侧。",
        "body_state_start": body(), "body_state_end": body(),
        "micro_timeline": [
            {"phase": "ESTABLISH", "action": "确认承重点", "state_change": "无"},
            {"phase": "PREPARE", "action": "右臂建立动作路径", "state_change": "接触保持"},
            {"phase": "EXECUTE", "action": "执行原始高强度核心动作", "state_change": "躯干逐步响应"},
            {"phase": "SETTLE", "action": "回到稳定承托", "state_change": "段尾可接续"},
        ],
        "physical_conflicts": [], "conflict_resolution": "",
        "physical_continuity_notes": ["seated weight remains supported on the sofa",
                                      "the right hand keeps ownership of the prop"],
        "anatomy_camera_notes": "keep the weight-bearing contact visible while moving closer",
        "render_risk": {"body_geometry": risk, "occlusion": "MEDIUM",
                        "fast_full_body_motion": True},
        "user_display_zh": {"objective": "保留原动作", "start_state": "斜靠沙发",
            "action_progression": "承重准备后执行并稳定", "blocking": "沙发承托",
            "camera": "前侧中景靠近", "dialogue": "无台词", "sound": "动作与呼吸声",
            "reference_usage": "图1仅按用户说明使用", "end_state": "稳定且可接续"},
    }


def test_gate7_core_action_is_preserved_and_physical_path_is_compiled():
    p = planner()
    plan = {"segments": [segment()]}
    out = C.validate_director_plan(copy.deepcopy(plan), p)
    prompt = C.compile_h3_prompt(planner=p, plan=out, segment_id=1)["CANONICAL_H3_PROMPT"]
    assert "执行原始高强度核心动作" in prompt
    assert "PREPARE:" in prompt and "SETTLE:" in prompt
    assert "seated weight remains supported" in prompt
    assert not any(x in prompt.lower() for x in C._ANATOMY_SPAM)
    assert len(out["segments"][0]["planning_advisories"]) == 2


def test_explicit_body_reference_suppresses_only_body_reference_suggestion():
    p = planner(reference_usage="图1是完整身体和目标姿态参考")
    out = C.validate_director_plan({"segments": [segment()]}, p)
    notes = out["segments"][0]["planning_advisories"]
    assert len(notes) == 1 and "分辨率" in notes[0]


def test_counterexample_is_rejected_until_camera_or_body_path_is_resolved():
    s = segment()
    s["blocking"] = "身体完全不转"
    s["camera"] = "镜头绕到人物正后方，人物始终正脸直视镜头"
    with pytest.raises(C.DirectorCompileError, match="未解决物理矛盾"):
        C.validate_director_plan({"segments": [copy.deepcopy(s)]}, planner())
    s["conflict_resolution"] = "允许肩部和躯干适度跟随，镜头停止在三分之四后侧"
    out = C.validate_director_plan({"segments": [s]}, planner())
    assert "FIXED_BODY_REAR_CAMERA_FRONT_FACE_CONFLICT" in out["segments"][0]["physical_conflicts"]


def test_cross_segment_body_ledger_must_join_exactly():
    a, b = segment(1), segment(2)
    b["body_state_start"]["prop_owner"] = "left hand"
    with pytest.raises(C.DirectorCompileError, match="END_STATE.*START_STATE"):
        C.validate_director_plan({"segments": [a, b]}, planner(2))


def test_low_risk_does_not_bloat_compiled_prompt():
    s = segment(risk="LOW")
    s["render_risk"]["occlusion"] = "LOW"
    s["render_risk"]["fast_full_body_motion"] = False
    p = planner(reference_usage="图1是完整身体参考")
    prompt = C.compile_h3_prompt(planner=p, plan={"segments": [s]}, segment_id=1)["CANONICAL_H3_PROMPT"]
    assert "Physical execution:" not in prompt
    assert "PREPARE:" not in prompt


def test_anatomy_negative_spam_is_refused():
    s = segment()
    s["physical_continuity_notes"] = ["perfect anatomy, no extra limbs"]
    with pytest.raises(C.DirectorCompileError, match="防畸形词库"):
        C.validate_director_plan({"segments": [s]}, planner())


def test_planner_echo_keys_are_not_story_plan_authority():
    p = planner()
    model_reply = {"segments": [segment()], **p}
    out = C.validate_director_plan(model_reply, p)
    echoes = set(p) - set(B.load("v28_schemas").PLAN_KEYS)
    for key in echoes:
        out.pop(key, None)
    assert not (set(out) & echoes)
