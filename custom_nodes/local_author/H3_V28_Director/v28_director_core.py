"""V28.2 deterministic Director core.

Reference slots are neutral UI indices.  This module is the sole owner of the
UI-slot -> H3 Picture ordinal map, reference-text validation, official six-
section assembly, audio routing and preview/submission identity receipt.
No function in this module accepts image pixels.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from typing import Any

from .v28_dialogue_track import split_dialogue, validate_dialogue_track

SECTIONS = ("subject_definitions", "summary", "retention_analysis",
            "detailed_description", "overall_soundscape", "non_diegetic_music")
LEGACY_TAGS = ("join-continuous", "camera-hold", "framing-keep",
               "pace-steady", "tail-ongoing")
_UI_REF = re.compile(r"图\s*([1-9])(?!\d)")
_TEMPORAL = re.compile(r"首帧|开始(?:状态|画面)?|第\s*\d+(?:\.\d+)?\s*秒|中间状态|最后一帧|最后画面|结束状态|最终画面|最终构图")
_NEGATED_FIRST = re.compile(r"(?:不作为|不用作|不是|不做|不作|不要|不得|禁止|不能|不应)[^，,；;。\n]{0,24}首帧")
_FIRST = re.compile(r"首帧")
_CONTROL_KEYS = re.compile(
    r"(?<![\w])(?:backend|steps|seed|resolution|cache(?:_id)?|slot_id|slot_index|"
    r"first_frame_enabled|ui_state|routing|DIALOGUE_DENSITY|ALLOW_POLISH)\s*[=:]", re.I)
COMPILER_VERSION = "v28.2-prompt-control-fix-1"
BODY_STATE_FIELDS = ("body_orientation", "torso_orientation", "pelvis_orientation",
                     "left_leg_state", "right_leg_state", "left_arm_state",
                     "right_arm_state", "weight_distribution", "contact_state",
                     "prop_owner", "camera_side")
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
MICRO_PHASES = {"ESTABLISH", "PREPARE", "EXECUTE", "SETTLE", "FINAL_HOLD"}
_ANATOMY_SPAM = ("no extra limbs", "no deformation", "perfect anatomy",
                 "perfect hands", "perfect legs", "no malformed body")


class DirectorCompileError(ValueError):
    pass


def _body_state(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    return {key: str(source.get(key) or "UNKNOWN").strip() for key in BODY_STATE_FIELDS}


def detect_physical_conflicts(seg: dict) -> list[str]:
    """Detect explicit planning contradictions, never content or intensity."""
    text = " ".join(str(seg.get(k) or "") for k in
                    ("start_state", "new_action", "blocking", "interaction", "camera"))
    low = text.lower()
    body_fixed = any(x in low for x in ("body does not turn", "body remains fixed",
                                        "torso does not turn", "身体完全不转", "躯干完全不转"))
    camera_rear = any(x in low for x in ("camera circles to directly behind", "camera moves behind",
                                         "正后方", "绕到人物背后", "绕到人物正后方"))
    face_camera = any(x in low for x in ("always faces the camera", "continues facing camera",
                                         "始终正脸直视镜头", "持续正脸直视镜头"))
    conflicts = []
    if body_fixed and camera_rear and face_camera:
        conflicts.append("FIXED_BODY_REAR_CAMERA_FRONT_FACE_CONFLICT")
    return conflicts


def _explicit_body_reference(planner: dict) -> bool:
    return any(re.search(r"身体|全身|髋|双腿|姿态|body|full.?body|pelvis|legs?|pose",
                         str(x.get("user_text") or ""), re.I)
               for x in (planner.get("reference_relationships") or []))


def active_reference_map(active_slots: list[int]) -> list[dict[str, int]]:
    slots = sorted({int(x) for x in active_slots})
    if any(x < 1 or x > 9 for x in slots):
        raise DirectorCompileError("参考图槽位只能是 1～9。")
    return [{"ui_slot": slot, "h3_picture": rank}
            for rank, slot in enumerate(slots, 1)]


def _map_dict(mapping: list[dict]) -> dict[int, int]:
    expected = active_reference_map([x.get("ui_slot") for x in mapping])
    normalized = [{"ui_slot": int(x.get("ui_slot")),
                   "h3_picture": int(x.get("h3_picture"))} for x in mapping]
    if normalized != expected:
        raise DirectorCompileError("ACTIVE_REFERENCE_MAP 不是 canonical mapping，已拒绝编译。")
    return {x["ui_slot"]: x["h3_picture"] for x in normalized}


def compile_reference_text(text: str, mapping: list[dict]) -> dict:
    """Validate UI references and deterministically replace 图N by <Picture M>."""
    text = str(text or "").strip()
    mp = _map_dict(mapping)
    mentioned = [int(m.group(1)) for m in _UI_REF.finditer(text)]
    missing = sorted({slot for slot in mentioned if slot not in mp})
    if missing:
        n = missing[0]
        raise DirectorCompileError(
            f"参考图说明引用了“图{n}”，但图{n}未上传。\n请上传图{n}或删除该引用。")

    compiled = _UI_REF.sub(lambda m: f"<Picture {mp[int(m.group(1))]}>", text)
    relationships = []
    for sentence in re.split(r"[；;。\n]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        slots = [int(x) for x in _UI_REF.findall(sentence)]
        if not slots:
            continue
        relationships.append({
            "ui_slots": slots,
            "h3_pictures": [mp[x] for x in slots],
            "user_text": sentence,
            "compiled_text": _UI_REF.sub(lambda m: f"<Picture {mp[int(m.group(1))]}>", sentence),
            "reference_attribute": True,
            "keyframe_anchor": bool(_TEMPORAL.search(_NEGATED_FIRST.sub("", sentence))),
            "first_frame": bool(_FIRST.search(sentence)) and not bool(_NEGATED_FIRST.search(sentence)),
        })
    return {
        "ACTIVE_REFERENCE_MAP": mapping,
        "reference_relationships": relationships,
        "compiled_reference_text": compiled,
        "REFERENCE_TIMELINE": "EXPLICIT_ONLY" if any(x["keyframe_anchor"] for x in relationships) else "NONE",
        "unassigned_role": "GENERAL_REFERENCE",
    }


def planner_input(*, active_slots: list[int], reference_usage: str,
                  story_goal: str, total_seconds: float, segment_seconds: float,
                  dialogue_mode: str = "无台词", source_dialogue: str = "",
                  previous_end_state: str = "", constraints: str = "",
                  planner_controls: dict | None = None) -> dict:
    mapping = active_reference_map(active_slots)
    refs = compile_reference_text(reference_usage, mapping)
    denied_first = {int(slot) for clause in re.split(r"[；;。\n]+", constraints or "")
                    if _NEGATED_FIRST.search(clause) for slot in _UI_REF.findall(clause)}
    for rel in refs["reference_relationships"]:
        if denied_first.intersection(rel["ui_slots"]):
            rel["first_frame"] = False
            rel["keyframe_anchor"] = bool(_TEMPORAL.search(_FIRST.sub("", rel["user_text"])))
    refs["REFERENCE_TIMELINE"] = "EXPLICIT_ONLY" if any(x["keyframe_anchor"] for x in refs["reference_relationships"]) else "NONE"
    skeleton = build_segment_skeleton(total_seconds, segment_seconds)
    count = len(skeleton)
    durations = [x["duration_sec"] for x in skeleton]
    dialogue = {"mode": dialogue_mode, "segments": [{"id": i + 1, "dialogue": ""}
                                                       for i in range(count)]}
    if dialogue_mode == "原文拆分":
        dialogue = {"mode": dialogue_mode, **split_dialogue(source_dialogue, durations)}
    elif dialogue_mode == "参考创作":
        dialogue["source_reference"] = str(source_dialogue or "")
    return {
        "GEMMA_VISION": "OFF",
        "ACTIVE_REFERENCE_MAP": mapping,
        "reference_relationships": refs["reference_relationships"],
        "compiled_reference_text": refs["compiled_reference_text"],
        "REFERENCE_TIMELINE": refs["REFERENCE_TIMELINE"],
        "story_goal": str(story_goal),
        "total_seconds": float(total_seconds),
        "segment_count": count,
        "segment_seconds": float(segment_seconds),
        "required_segment_count": count,
        "segment_skeleton": skeleton,
        "dialogue_track": dialogue,
        "previous_end_state": str(previous_end_state or ""),
        "user_constraints": str(constraints or ""),
        "planner_controls": dict(planner_controls or {}),
    }


def build_segment_skeleton(total_seconds: float, segment_seconds: float) -> list[dict]:
    """Own segment count and clock boundaries in deterministic code.

    The model may fill director semantics, but it never chooses, inserts, removes,
    renumbers or resizes segments.  A non-integral tail is deliberately shorter.
    """
    total = float(total_seconds)
    size = float(segment_seconds)
    if total <= 0 or size <= 0:
        raise DirectorCompileError("总时长和分段时长必须大于 0。")
    count = max(1, int(math.ceil(total / size)))
    out = []
    for i in range(count):
        start = min(total, i * size)
        end = min(total, (i + 1) * size)
        out.append({"segment_index": i + 1, "start_time": start,
                    "end_time": end, "duration_sec": end - start})
    return out


_SEMANTIC_KEYS = ("segment_objective", "start_state", "new_action", "beats",
                  "performance", "blocking", "interaction", "camera", "end_state",
                  "continuity_out", "user_display_zh", "micro_timeline",
                  "body_state_start", "body_state_end", "render_risk",
                  "physical_conflicts", "physical_continuity_notes")


def _carrier_segments(source: dict) -> list:
    """Find the array the model actually filled.

    Gate-8B R3: the reply filled the `segment_skeleton` copy it had been handed
    in `input` and never emitted a top-level `segments` array. That reply was
    complete - six fully typed segments - yet reading only `segments` turned it
    into six empty ones and burned the whole repair budget on no-ops. Both
    carriers are the same content and the clock is ours either way, so accept
    whichever one carries director semantics.
    """
    for key in ("segments", "segment_skeleton", "segment_timeline", "storyboard"):
        value = source.get(key)
        if not isinstance(value, list):
            continue
        items = [x for x in value if isinstance(x, dict)]
        if any(any(k in x for k in _SEMANTIC_KEYS) for x in items):
            return items
    return []


def align_plan_to_skeleton(plan: dict, planner: dict) -> tuple[dict, dict]:
    """Fit model content onto the program-owned skeleton without LLM count repair."""
    source = plan if isinstance(plan, dict) else {}
    raw = _carrier_segments(source)
    skeleton = planner.get("segment_skeleton") or build_segment_skeleton(
        planner["total_seconds"], planner["segment_seconds"])
    by_id: dict[int, dict] = {}
    extras: list[int | str] = []
    for pos, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            extras.append(pos)
            continue
        candidate = item.get("segment_index", item.get("segment", item.get("id", pos)))
        try:
            idx = int(candidate)
        except (TypeError, ValueError):
            extras.append(str(candidate))
            continue
        if idx < 1 or idx > len(skeleton) or idx in by_id:
            extras.append(idx)
            continue
        by_id[idx] = dict(item)
    aligned = []
    missing = []
    for clock in skeleton:
        idx = int(clock["segment_index"])
        seg = by_id.get(idx, {})
        if not seg:
            missing.append(idx)
        seg.update({"id": idx, "segment": idx, "segment_index": idx,
                    "start_time": float(clock["start_time"]),
                    "end_time": float(clock["end_time"]),
                    "duration_sec": float(clock["duration_sec"]),
                    "duration": float(clock["duration_sec"])})
        aligned.append(seg)
    result = dict(source)
    result["segments"] = aligned
    return result, {"missing_segment_ids": missing, "ignored_extra_segments": extras,
                    "required_segment_count": len(skeleton)}


def segment_content_gaps(seg: dict) -> list[str]:
    """Return semantic fields eligible for a targeted segment-only repair."""
    gaps = []
    for key in ("segment_objective", "start_state", "new_action", "performance",
                "blocking", "camera", "end_state", "continuity_out"):
        if not str(seg.get(key) or "").strip():
            gaps.append(key)
    if not [x for x in (seg.get("beats") or []) if str(x).strip()]:
        gaps.append("beats")
    if not isinstance(seg.get("body_state_start"), dict):
        gaps.append("body_state_start")
    if not isinstance(seg.get("body_state_end"), dict):
        gaps.append("body_state_end")
    timeline = seg.get("micro_timeline")
    if (not isinstance(timeline, list) or not timeline or
            any(not isinstance(x, dict) or str(x.get("phase") or "").upper() not in MICRO_PHASES
                for x in timeline)):
        gaps.append("micro_timeline")
    risk = seg.get("render_risk")
    if (not isinstance(risk, dict) or
            str(risk.get("body_geometry") or "").upper() not in RISK_LEVELS or
            str(risk.get("occlusion") or "").upper() not in RISK_LEVELS):
        gaps.append("render_risk")
    zh = seg.get("user_display_zh")
    if not isinstance(zh, dict) or any(not str(zh.get(k) or "").strip() for k in
            ("objective", "start_state", "action_progression", "blocking", "camera",
             "dialogue", "sound", "reference_usage", "end_state")):
        gaps.append("user_display_zh")
    return gaps


def _normalize_phase(value: Any) -> str:
    """Longest-substring match, so a bare `HOLD` resolves to FINAL_HOLD.

    The enum is structure and therefore code-owned; guessing a level from prose
    is not allowed, but discarding the model's actual intent is worse. Anything
    unmatched falls back to EXECUTE, which is the neutral default.
    """
    text = str(value or "").upper().strip()
    if text in MICRO_PHASES:
        return text
    hits = [p for p in MICRO_PHASES if text and text in p]
    return max(hits, key=len) if hits else "EXECUTE"


def _normalize_micro_timeline(value: Any) -> list[dict]:
    if isinstance(value, str):
        value = [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict):
            out.append({"phase": _normalize_phase(item.get("phase")),
                        "action": str(item.get("action") or "").strip(),
                        "state_change": str(item.get("state_change") or "").strip()})
        elif str(item).strip():
            out.append({"phase": _normalize_phase(item), "action": str(item).strip(),
                        "state_change": ""})
    return out


def _normalize_render_risk(value: Any) -> dict:
    risk = value if isinstance(value, dict) else {}
    body = str(risk.get("body_geometry") or "").upper()
    occ = str(risk.get("occlusion") or "").upper()
    return {"body_geometry": body if body in RISK_LEVELS else "LOW",
            "occlusion": occ if occ in RISK_LEVELS else "LOW",
            "fast_full_body_motion": bool(risk.get("fast_full_body_motion"))}


def _unwrap_fill_envelope(patch: Any, fields: list[str]) -> dict:
    """Strip an echo envelope such as {"fields_to_fill": {...}}.

    The repair request lists the wanted keys, so the model often answers wrapped
    in that same key. Reading it literally made every fill a silent no-op.
    """
    if not isinstance(patch, dict):
        return {}
    if any(f in patch for f in fields):
        return patch
    for value in patch.values():
        if isinstance(value, dict) and any(f in value for f in fields):
            return value
    return patch


def normalize_segment_patch(patch: Any, fields: list[str]) -> dict:
    """Coerce one targeted fill into the shapes the validator requires.

    Content is the model's; these shapes are structure and belong to code. A
    prose timeline becomes one EXECUTE step, a prose risk note stays LOW, and a
    non-dict body state stays UNKNOWN - none of which is a new invention.
    """
    out = dict(_unwrap_fill_envelope(patch, fields))
    if "beats" in out:
        beats = out["beats"]
        beats = [beats] if isinstance(beats, str) else beats
        out["beats"] = [str(x).strip() for x in beats
                        if str(x).strip()] if isinstance(beats, list) else []
    if "micro_timeline" in out:
        out["micro_timeline"] = _normalize_micro_timeline(out["micro_timeline"])
    for key in ("body_state_start", "body_state_end"):
        if key in out:
            out[key] = _body_state(out[key] if isinstance(out[key], dict) else None)
    if "render_risk" in out:
        out["render_risk"] = _normalize_render_risk(out["render_risk"])
    return out


EMPTY_SEGMENT_FIELD_SHAPES: dict[str, Any] = {
    "beats": [""],
    "micro_timeline": [{"phase": "EXECUTE", "action": "", "state_change": ""}],
    "body_state_start": {k: "UNKNOWN" for k in BODY_STATE_FIELDS},
    "body_state_end": {k: "UNKNOWN" for k in BODY_STATE_FIELDS},
    "render_risk": {"body_geometry": "LOW", "occlusion": "LOW",
                    "fast_full_body_motion": False},
    "user_display_zh": {"objective": "", "start_state": "", "action_progression": "",
                        "blocking": "", "camera": "", "dialogue": "", "sound": "",
                        "reference_usage": "", "end_state": ""},
}


def segment_field_shapes(fields: list[str]) -> dict:
    """The exact JSON shape a targeted fill must answer with."""
    out = {}
    for key in fields:
        out[key] = (copy.deepcopy(EMPTY_SEGMENT_FIELD_SHAPES[key])
                    if key in EMPTY_SEGMENT_FIELD_SHAPES else "")
    return out


def validate_director_plan(plan: dict, planner: dict) -> dict:
    plan, _alignment = align_plan_to_skeleton(plan, planner)
    segments = plan.get("segments") if isinstance(plan, dict) else None
    expected = int(planner["segment_count"])
    if not isinstance(segments, list) or len(segments) != expected:
        raise DirectorCompileError(f"Director Plan 必须包含 {expected} 段。")
    track = planner.get("dialogue_track") or {}
    track_segments = track.get("segments") or []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise DirectorCompileError(f"第 {i + 1} 段不是对象。")
        clock = planner["segment_skeleton"][i]
        seg.update({"id": i + 1, "segment": i + 1, "segment_index": i + 1,
                    "start_time": float(clock["start_time"]),
                    "end_time": float(clock["end_time"]),
                    "duration_sec": float(clock["duration_sec"]),
                    "duration": float(clock["duration_sec"])})
        for key in ("segment_objective", "start_state", "new_action", "performance",
                    "blocking", "interaction", "camera", "dialogue", "dialogue_timing",
                    "ambience", "physical_sounds", "non_verbal_vocals", "music",
                    "end_state", "continuity_out"):
            value = seg.get(key)
            # Persisted V28 plans wrap these states; unwrap rather than stringify
            # the dict so first compile and cache recovery remain identical.
            if key in ("start_state", "end_state") and isinstance(value, dict) and "text" in value:
                value = value["text"]
            seg[key] = str(value or "")
        seg["beats"] = [str(x).strip() for x in (seg.get("beats") or []) if str(x).strip()]
        if not seg["beats"]:
            seg["beats"] = [seg["new_action"]]
        seg["body_state_start"] = _body_state(seg.get("body_state_start"))
        seg["body_state_end"] = _body_state(seg.get("body_state_end"))
        timeline = seg.get("micro_timeline") or []
        if not isinstance(timeline, list):
            raise DirectorCompileError(f"第 {i + 1} 段 micro_timeline 必须是数组。")
        normalized_timeline = []
        for item in timeline:
            if not isinstance(item, dict):
                raise DirectorCompileError(f"第 {i + 1} 段 micro_timeline 项必须是对象。")
            phase = str(item.get("phase") or "").upper()
            if phase not in MICRO_PHASES:
                raise DirectorCompileError(f"第 {i + 1} 段 micro_timeline phase 无效：{phase}")
            normalized_timeline.append({"phase": phase,
                                        "action": str(item.get("action") or "").strip(),
                                        "state_change": str(item.get("state_change") or "").strip()})
        seg["micro_timeline"] = normalized_timeline
        risk = seg.get("render_risk") if isinstance(seg.get("render_risk"), dict) else {}
        body_risk = str(risk.get("body_geometry") or "LOW").upper()
        occlusion = str(risk.get("occlusion") or "LOW").upper()
        if body_risk not in RISK_LEVELS or occlusion not in RISK_LEVELS:
            raise DirectorCompileError(f"第 {i + 1} 段 render_risk 只能是 LOW/MEDIUM/HIGH。")
        seg["render_risk"] = {"body_geometry": body_risk, "occlusion": occlusion,
                              "fast_full_body_motion": bool(risk.get("fast_full_body_motion"))}
        detected = detect_physical_conflicts(seg)
        declared = [str(x) for x in (seg.get("physical_conflicts") or [])]
        seg["physical_conflicts"] = list(dict.fromkeys(declared + detected))
        seg["conflict_resolution"] = str(seg.get("conflict_resolution") or "").strip()
        seg["physical_continuity_notes"] = [str(x).strip() for x in
                                             (seg.get("physical_continuity_notes") or [])
                                             if str(x).strip()]
        combined_notes = " ".join(seg["physical_continuity_notes"] + [seg["conflict_resolution"]]).lower()
        if any(x in combined_notes for x in _ANATOMY_SPAM):
            raise DirectorCompileError("物理规划误用了全局防畸形词库；必须改写为可执行的正向状态。")
        if detected and not seg["conflict_resolution"]:
            raise DirectorCompileError(f"第 {i + 1} 段存在未解决物理矛盾：{detected}")
        seg["anatomy_camera_notes"] = str(seg.get("anatomy_camera_notes") or "").strip()
        advisories = []
        if body_risk == "HIGH" and not _explicit_body_reference(planner):
            advisories.append("本段包含大幅全身动作或复杂遮挡；增加一张清晰完整身体/目标姿态参考可能提高结构稳定性（非阻断）。")
        if seg["render_risk"]["fast_full_body_motion"]:
            advisories.append("本段属于快速全身动作；较高有效分辨率可能提高肢体稳定性（不会自动修改分辨率）。")
        seg["planning_advisories"] = advisories
        zh = seg.get("user_display_zh")
        if not isinstance(zh, dict):
            raise DirectorCompileError(f"第 {i + 1} 段缺少 user_display_zh 中文导演计划。")
        required_zh = ("objective", "start_state", "action_progression", "blocking",
                       "camera", "dialogue", "sound", "reference_usage", "end_state")
        if any(not str(zh.get(k) or "").strip() for k in required_zh):
            raise DirectorCompileError(f"第 {i + 1} 段中文导演计划字段不完整。")
        if track.get("mode") == "原文拆分":
            # Lossless join of every event the track declares for this segment:
            # one event is normal, two is "the story really says it twice".
            seg["dialogue"] = "".join(dialogue_events(planner, i + 1))
    for i in range(len(segments) - 1):
        left, right = segments[i]["body_state_end"], segments[i + 1]["body_state_start"]
        mismatched = [k for k in BODY_STATE_FIELDS if left[k] != right[k]]
        if mismatched:
            raise DirectorCompileError(
                f"第 {i + 1} 段 END_STATE 与第 {i + 2} 段 START_STATE 不一致：{mismatched}")
    if track.get("mode") == "原文拆分":
        receipt = validate_dialogue_track(track.get("SOURCE_DIALOGUE") or "",
                                          [x["dialogue"] for x in segments])
        if not receipt["passed"]:
            raise DirectorCompileError(f"原文台词完整性失败：{receipt}")
    plan["reference_relationships"] = planner["reference_relationships"]
    plan["ACTIVE_REFERENCE_MAP"] = planner["ACTIVE_REFERENCE_MAP"]
    return plan


_CJK = re.compile(r"[\u4e00-\u9fff]")


# --- dialogue contract (official Ref2VA section semantics) ----------------
# An utterance is ONE event and is rendered EXACTLY ONCE, inside
# `detailed_description`. `overall_soundscape` is ambience and non-verbal sound
# only; `non_diegetic_music` is score only. Repeating the line in either section
# double-weights the same language content, which is what makes H3 say it twice.
# The counted quantity is EVENTS, not unique strings: if the story genuinely asks
# for the same sentence twice, the dialogue track carries two entries and two
# renders are correct.
DIALOGUE_SOURCE_OF_TRUTH = "DIALOGUE_TRACK"
DIALOGUE_RENDER_TARGET = "DETAILED_DESCRIPTION_ONLY"
OVERALL_SOUNDSCAPE_CONTAINS_DIALOGUE = "NO"
NON_DIEGETIC_MUSIC_CONTAINS_DIALOGUE = "NO"
_D_BLOCK = re.compile(r"<d>.*?</d>", re.S)
_ECHO_WINDOW = 6          # chars of verbatim overlap that count as an echo


def dialogue_events(planner: dict, segment_id: int) -> list[str]:
    """The authoritative dialogue events for one segment, from the track only.

    The deterministic dialogue track is the sole owner of the author's source
    text, so it - not whatever the model wrote into the plan - decides how many
    spoken events this segment really has.
    """
    track = (planner or {}).get("dialogue_track") or {}
    out: list[str] = []
    for row in (track.get("segments") or []):
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("id") or 0) != int(segment_id):
                continue
        except (TypeError, ValueError):
            continue
        text = str(row.get("dialogue") or "").strip()
        if text:
            out.append(text)
    return out


def dialogue_block(text: str) -> str:
    """H3 reads the voice tag from inside every `<d>` block.

    `v28_prompt_compiler.audit_prompt` rejects an untagged block, so the marker
    is part of the compiled contract rather than decoration. The line itself is
    carried byte-for-byte; only the language marker is added. Gate-8B R4 reached
    this path for the first time because planning had always failed before it.
    """
    body = str(text or "").strip()
    if not body:
        return ""
    return f"<d>[{'Chinese' if _CJK.search(body) else 'English'}] {body}</d>"


def _section_body(text: str, name: str) -> str:
    """The text of one `name:` section, up to the next official section heading."""
    i = (text or "").find(f"{name}:")
    if i == -1:
        return ""
    body = text[i + len(name) + 1:]
    ends = [body.find(f"\n{s}:") for s in SECTIONS if s != name]
    ends = [x for x in ends if x != -1]
    return body[:min(ends)] if ends else body


def _dialogue_echo(body: str, source: str) -> bool:
    """True when `body` carries the spoken line verbatim, even as a fragment.

    Catches verbatim and fragment leakage in any shape (with or without a `<d>`
    wrapper). A *translated* paraphrase is not textually detectable - the
    guarantee against that one is structural: the compiler no longer carries the
    line into the audio sections at all. Rewriting the line as an English summary
    there would still double-weight the same language content, and is a contract
    violation even though this probe cannot see it.
    """
    probe = re.sub(r"\s+", "", unicodedata.normalize("NFC", str(source or "")))
    if len(probe) < 3:
        return False
    hay = re.sub(r"\s+", "", unicodedata.normalize("NFC", str(body or "")))
    if len(probe) < _ECHO_WINDOW:
        return probe in hay
    return any(probe[i:i + _ECHO_WINDOW] in hay
               for i in range(0, len(probe) - _ECHO_WINDOW + 1))


def audit_dialogue_contract(text: str, *, expected_events: int,
                            sources: list[str] | None = None) -> list[str]:
    """Deterministic dialogue gate. Empty list == the prompt may be submitted."""
    e: list[str] = []
    rendered = len(_D_BLOCK.findall(text or ""))
    if rendered != int(expected_events):
        e.append(f"对白事件数不匹配：台词轨声明 {int(expected_events)} 个事件，"
                 f"最终 Prompt 渲染了 {rendered} 个 <d> 块")
    for section in ("overall_soundscape", "non_diegetic_music"):
        body = _section_body(text or "", section)
        if "<d>" in body:
            e.append(f"{section} 出现对白块；对白只属于 detailed_description")
        for src in (sources or []):
            if _dialogue_echo(body, src):
                e.append(f"{section} 重复了对白内容（含改写/摘要）；"
                         f"禁止给同一语言内容二次加权")
    return e


def _audio(seg: dict) -> tuple[str, str]:
    """Ambience and non-verbal sound only - never the spoken line.

    The dialogue used to be emitted here as well as in detailed_description, so
    every spoken line reached H3 twice. The official section contract keeps this
    section to room tone, breath, fabric, footsteps, contact/friction and
    scene-continuous sound; the utterance lives only in detailed_description.
    """
    physical = "; ".join(x for x in (seg.get("ambience"), seg.get("physical_sounds"),
                                      seg.get("non_verbal_vocals")) if x)
    return physical or "Natural ambience only.", seg.get("music") or "N/A"


def compile_h3_prompt(*, planner: dict, plan: dict, segment_id: int,
                      raw_native_prompt: str = "", director_enabled: bool = True) -> dict:
    """Build one canonical prompt, or preserve the raw native prompt byte-for-byte."""
    if not director_enabled or not any((planner.get("compiled_reference_text"),
                                        planner.get("story_goal"), planner.get("user_constraints"))):
        prompt = str(raw_native_prompt)
        return canonical_prompt_bundle(prompt, path="RAW_NATIVE_H3_PATH")
    plan = validate_director_plan(plan, planner)
    seg = plan["segments"][int(segment_id) - 1]
    ref_text = planner.get("compiled_reference_text") or ""
    # User prohibitions are authoritative even when the planner omits them.
    # Chinese UI slot references are translated once to canonical H3 ordinals.
    constraints = compile_reference_text(
        planner.get("user_constraints") or "", planner["ACTIVE_REFERENCE_MAP"]
    )["compiled_reference_text"]
    if not ref_text:
        ref_text = "\n".join(f"<Picture {x['h3_picture']}> is a GENERAL_REFERENCE with no inferred fixed role."
                             for x in planner["ACTIVE_REFERENCE_MAP"])
    sound, music = _audio(seg)
    beat_text = " ".join(f"Beat {i + 1}: {b}" for i, b in enumerate(seg.get("beats") or []))
    action = beat_text or seg.get("new_action") or planner.get("story_goal") or "Continue the requested scene."
    risk = seg.get("render_risk") or {}
    physical_detail = ""
    if risk.get("body_geometry") in ("MEDIUM", "HIGH") or risk.get("occlusion") in ("MEDIUM", "HIGH"):
        micro = " ".join(f"{x['phase']}: {x['action']} {x['state_change']}".strip()
                         for x in (seg.get("micro_timeline") or []))
        positive = " ".join(seg.get("physical_continuity_notes") or [])
        physical_detail = " ".join(x for x in (micro, positive, seg.get("anatomy_camera_notes")) if x)
    directing = " ".join(x for x in (
        f"Objective: {seg.get('segment_objective')}." if seg.get("segment_objective") else "",
        f"Performance: {seg.get('performance')}." if seg.get("performance") else "",
        f"Blocking and interaction: {seg.get('blocking')} {seg.get('interaction')}." if seg.get("blocking") or seg.get("interaction") else "",
        f"Camera: {seg.get('camera')}." if seg.get("camera") else "",
        f"Dialogue timing: {seg.get('dialogue_timing')}." if seg.get("dialogue_timing") else "",
        f"Continuity out: {seg.get('continuity_out')}." if seg.get("continuity_out") else "",
        f"Physical execution: {physical_detail}." if physical_detail else "",
    ) if x)
    # One render per declared event, in detailed_description only. The track is
    # the source of truth; the plan's own `dialogue` is the fallback when no
    # track exists (no-dialogue and free-authored modes).
    events = dialogue_events(planner, int(segment_id))
    if not events:
        own = str(seg.get("dialogue") or "").strip()
        events = [own] if own else []
    if events:
        timing = str(seg.get("dialogue_timing") or "").strip()
        action += " Dialogue: " + " ".join(dialogue_block(x) for x in events) \
                  + (f" ({timing})" if timing else "")
    description = (f"[Shot 1] {seg.get('start_state')} {action} {directing} {seg.get('end_state')}").strip()
    if seg.get("detailed_description_edit"):
        description = compile_reference_text(seg["detailed_description_edit"], planner["ACTIVE_REFERENCE_MAP"])["compiled_reference_text"]
    if constraints and constraints not in description:
        description += "\n" + constraints
    prompt = "\n\n".join((
        f"subject_definitions:\n{ref_text}",
        f"summary:\n[reference generation] {planner.get('story_goal') or action}",
        "retention_analysis:\n" + "\n".join(
            f"<Picture {x['h3_picture']}>: attribute_transfer - preserve and apply exactly the user-defined role in subject_definitions; do not invent any unprovided visual fact or timeline."
            for x in planner["ACTIVE_REFERENCE_MAP"]),
        f"detailed_description:\n{description}",
        f"overall_soundscape:\n{sound}",
        f"non_diegetic_music:\n{music}",
    ))
    if any(x in prompt for x in LEGACY_TAGS):
        raise DirectorCompileError("检测到旧 Director 保守标签，已拒绝编译。")
    control_errors = audit_control_fields(prompt)
    if control_errors:
        raise DirectorCompileError("控制字段不能进入 H3 Prompt：" + "; ".join(control_errors))
    dialogue_errors = audit_dialogue_contract(prompt, expected_events=len(events),
                                              sources=events)
    if dialogue_errors:
        raise DirectorCompileError("对白合同校验失败：" + "；".join(dialogue_errors))
    if any(f"{s}:" not in prompt for s in SECTIONS):
        raise DirectorCompileError("官方 Ref2VA 六段结构不完整。")
    return canonical_prompt_bundle(prompt, path="DIRECTOR_COMPILED")


def audit_control_fields(prompt: str) -> list[str]:
    return [m.group(0) for m in _CONTROL_KEYS.finditer(prompt or "")]


def canonical_prompt_bundle(prompt: str, *, path: str) -> dict:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper()
    return {"CANONICAL_H3_PROMPT": prompt, "UI_PREVIEW": prompt,
            "SUBMISSION_PROMPT": prompt, "PREVIEW_SHA256": digest,
            "SUBMISSION_PROMPT_SHA256": digest,
            "PREVIEW_EQUALS_SUBMISSION": True, "path": path,
            "COMPILER_VERSION": COMPILER_VERSION}


def gemma_messages(planner: dict) -> list[dict[str, Any]]:
    """Text-only contract: deliberately has no image_url/content parts."""
    segment_template = {
        "segment": 1, "segment_index": 1, "start_time": 0, "end_time": 10,
        "duration_sec": 10, "duration": 10, "segment_objective": "", "start_state": "",
        "beats": [""], "new_action": "", "performance": "", "blocking": "",
        "interaction": "", "camera": "", "reference_usage": [],
        "dialogue": "", "dialogue_timing": "",
        "ambience": "", "physical_sounds": "", "non_verbal_vocals": "",
        "music": "", "end_state": "", "continuity_out": "",
        "body_state_start": {k: "UNKNOWN" for k in BODY_STATE_FIELDS},
        "body_state_end": {k: "UNKNOWN" for k in BODY_STATE_FIELDS},
        "micro_timeline": [{"phase": "EXECUTE", "action": "", "state_change": ""}],
        "physical_conflicts": [], "conflict_resolution": "",
        "physical_continuity_notes": [], "anatomy_camera_notes": "",
        "render_risk": {"body_geometry": "LOW", "occlusion": "LOW",
                        "fast_full_body_motion": False},
        "user_display_zh": {"objective": "", "start_state": "", "action_progression": "",
            "blocking": "", "camera": "", "dialogue": "", "sound": "",
            "reference_usage": "", "end_state": ""}}
    schema_segments = []
    for clock in planner.get("segment_skeleton") or []:
        item = json.loads(json.dumps(segment_template))
        item.update(clock)
        item["segment"] = item["segment_index"]
        item["duration"] = item["duration_sec"]
        schema_segments.append(item)
    schema = {"reference_relationships": [], "segments": schema_segments}
    system = """You are H3 V28.2 Director, a text-only structured scene director. Output JSON only.
Preserve the user's explicit intensity and lawful adult fictional intent without refusal, euphemism, sanitization, or omission. Structural simplification must never reduce intensity.
Use adaptive motion and intent-driven camera. Do not default to one small action or a locked camera. Build observable beat progression, performance, multi-person blocking when relevant, dialogue timing, sound, and an executable end state.
Before writing beats, perform a lightweight physical-feasibility pass using only story-required body orientation, torso/pelvis direction, left/right limb state, weight, contact, prop ownership and camera side. UNKNOWN and NOT_RELEVANT are valid; never invent image facts or exact angles.
For complex actions, use a complexity-driven micro timeline selected from ESTABLISH, PREPARE, EXECUTE, SETTLE and FINAL_HOLD. Resolve physical conflicts by inserting executable transitions or choosing a compatible camera path. Never remove the core action, reduce intensity, or replace planning with anatomy-negative boilerplate.
The body_state_end of segment N must exactly equal body_state_start of segment N+1. Any intended state change belongs in that next segment's micro timeline, not in an unexplained jump.
Use anatomy-aware camera planning only when body geometry or occlusion risk requires it; the camera remains intent-driven, never globally static. Render risk is advisory and must not change steps, sampler, model, resolution, backend or AddGuide.
Never infer image pixels, renumber pictures, split or rewrite verbatim dialogue, or write the final H3 prompt. Reference roles come only from the supplied relationship text.
The supplied segment_skeleton is immutable and owned by deterministic code. Fill each existing segment's director-semantic fields only. Never add, remove, renumber, resize, or change the clock fields of a segment.
Your reply MUST contain a top-level "segments" array with exactly the same number of items as segment_skeleton, in the same order, carrying all director semantics. The segment_skeleton inside "input" is a read-only clock: do not fill it in place of "segments".
For every segment, user_display_zh must faithfully express the same plan in detailed Chinese; it is not a second plan or a shortened summary."""
    return [{"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"input": planner, "output_schema": schema}, ensure_ascii=False)}]
