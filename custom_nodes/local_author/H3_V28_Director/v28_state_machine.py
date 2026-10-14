"""V28 Director - LAYER 2: the deterministic state machine (task sections 20-24, 27, 29, 30).

Two rules dominate this file:

  * Task 4: 禁止 LLM 控制状态机. Nothing here calls a provider. The model plans;
    this module owns segment numbers, candidates, acceptance and Motion Context
    indices, and it refuses transitions that are not legal.
  * Task 21/24: generating successfully is NOT acceptance. Every generation ends
    in CANDIDATE_READY and only a human click moves it to ACCEPTED, and accepting
    never queues the next clip. The watch-the-clip node is permanent.

Motion Context integration (P7) reuses V27's own invariant instead of inventing a
second chaining system - see V28_V27_FREEZE_RECORD.txt:
    Load node 996 clip_index == the last ACCEPTED segment (0 = none yet)
    Save node 995 clip_index == the segment about to be generated
The official pack's "Approve" advances *and queues*; task 24 forbids the queue,
so V28 writes those two widgets itself. That is the one new primitive:
ADVANCE-WITHOUT-QUEUE.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from typing import Any

from . import v28_paths as P
from . import v28_project as PJ
from . import v28_prompt_compiler as PC
from . import v28_schemas as S
from . import v28_prompt_resolution as PR

# Seeds travel through the front end as JSON numbers (N142's widget is a JS
# `number`), so anything above 2**53-1 is silently re-rounded on the way into the
# graph - the clip would then be generated with a seed that is not the seed the
# state machine recorded, which breaks task 23's traceability. Stay exact.
SEED_MAX = (1 << 53) - 1
STATE_NAME = "SESSION_STATE.json"

CONT_ON = "开启（接上一段继续演）"
# V27's own default, and the string the panel shows when a human set it by hand.
# Since P11 BUG-7 no V28 instruction emits this any more: 关闭 bypasses the SAVE node
# too, and every accepted segment needs its slot on disk.
CONT_OFF = "关闭（本段独立起步）"
CONT_STRENGTH = "自动"


class IllegalTransition(Exception):
    """Raised when a requested move contradicts the explicit state machine."""


class GateRefused(Exception):
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


def new_seed() -> int:
    return random.SystemRandom().randrange(1, SEED_MAX)


# --------------------------------------------------------------------------
def blank_state(project_id: str, *, segment_count: int = 0) -> dict:
    """Every field section 20 names, always explicit - no implicit state."""
    return {
        "version": S.SCHEMA_VERSION,
        "project_id": project_id,
        "status": "PLANNED" if not segment_count else "READY",
        "segment_count": int(segment_count),
        "current_segment": 1 if segment_count else 0,
        "last_accepted_segment": 0,
        "next_segment": (2 if segment_count > 1 else None),
        "current_candidate": None,
        "accepted": [],
        "errors": [],
        "attempt": 0,
        "plan_version": 0,
        "updated_at": _now(),
        "history": [],
    }


def load_state(project_id: str) -> dict:
    st = PJ.read(project_id, STATE_NAME, default=None)
    if not isinstance(st, dict):
        if st is not None:
            # A file that parsed but is not an object (a JSON list, a bare string)
            # is NOT the same event as "no state yet": the project had a story, and
            # dropping it here resets the cursor and the accepted list. The corrupt
            # path above keeps a corpse under a .corrupt name; this one leaves the
            # file exactly as it is, so say so in the project log where a human
            # looking at a suddenly-empty card will find it.
            PJ.log_line(project_id, f"SESSION_STATE unusable ({type(st).__name__}), "
                                    f"loaded blank state instead; file left on disk")
        return blank_state(project_id)
    st.setdefault("accepted", [])
    st.setdefault("errors", [])
    st.setdefault("history", [])
    st.setdefault("attempt", 0)
    st.setdefault("next_segment", None)
    if st.get("segment_count") and not st.get("current_segment"):
        st["current_segment"] = 1
    return st


def save_state(project_id: str, st: dict) -> dict:
    st["updated_at"] = _now()
    try:
        S.check("session_state", st)
    except S.SchemaError as e:
        # A bad state must never reach disk: it would come back on the next load
        # and corrupt the project (task 34's "不要破坏项目状态").
        st["errors"] = list(st.get("errors") or []) + [
            {"at": _now(), "kind": "STATE_SCHEMA", "detail": e.errors[:6]}][-24:]
        PJ.log_line(project_id, f"state rejected: {e.errors[:3]}")
        raise
    st["history"] = (list(st.get("history") or []) + [
        {"at": st["updated_at"], "status": st["status"],
         "current_segment": st["current_segment"],
         "last_accepted_segment": st["last_accepted_segment"]}])[-60:]
    PJ.write(project_id, STATE_NAME, st)
    return st


# --------------------------------------------------------------------------
# transitions
# --------------------------------------------------------------------------
def set_plan(project_id: str, plan: dict) -> dict:
    """Planning finished -> segment 1 is ready. Does not start generation."""
    S.check("story_plan", plan)
    PJ.write(project_id, "STORY_PLAN.json", plan)
    n = len(plan.get("segments") or [])
    old = load_state(project_id)
    st = blank_state(project_id, segment_count=n)
    # accepted work is never discarded by re-planning (task 27)
    st["last_accepted_segment"] = int(old.get("last_accepted_segment") or 0)
    st["accepted"] = list(old.get("accepted") or [])
    st["current_segment"] = min(max(1, st["last_accepted_segment"] + 1), n)
    st["plan_version"] = int(old.get("plan_version") or 0) + 1
    st["status"] = "READY"
    st["next_segment"] = st["current_segment"] + 1 if st["current_segment"] < n else None
    PJ.log_line(project_id, f"plan set: {n} segments (plan_version={st['plan_version']})")
    return save_state(project_id, st)


def current_segment(project_id: str) -> tuple[dict, dict, dict]:
    st = load_state(project_id)
    plan = PJ.read(project_id, "STORY_PLAN.json", default=None) or {}
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default=None) or {}
    if not (plan.get("segments") or []):
        raise GateRefused("还没有剧情计划，请先点击【生成剧情计划】")
    return st, plan, profile


def widget_instructions(project_id: str, *, seed: int | None = None,
                        prompt_override: str = "", reroll: bool = False,
                        same_seed: bool = False) -> dict:
    """Everything the front end must write onto the graph for this submission.

    This is the ONLY place that decides Motion Context indices, so the graph and
    SESSION_STATE can never disagree about which clip is being made.
    """
    st, plan, profile = current_segment(project_id)
    segs = plan.get("segments") or []
    cur = int(st.get("current_segment") or 1)
    if st.get("status") == "CANDIDATE_READY" and not reroll:
        raise GateRefused("当前段已有候选片段，请先【接受并下一步】或【重新生成】")
    if cur > len(segs):
        raise GateRefused("所有段落已完成")
    seg = segs[cur - 1]
    if int(st.get("last_accepted_segment") or 0) >= cur:
        raise IllegalTransition("last_accepted 不能不小于 current_segment")

    # Gate-6C: the canonical prompt compiled and audited during planning is the
    # one submitted. Recompiling here with the legacy compiler previously erased
    # explicit reference roles and rich directing just before queue submission.
    from . import v28_orchestrator as OR  # runtime import avoids the state/orchestration cycle
    resolved = PR.execution_segments(project_id)[cur - 1]
    prompt = resolved["final_prompt"]
    if prompt_override and prompt_override.strip() != prompt.strip():
        raise GateRefused("请先保存动作编辑再提交，不能绕过统一编译器。",
                          {"kind": "prompt_structure"})

    use_seed = seed if seed is not None else (
        int(seg.get("seed") or 0) if same_seed and seg.get("seed") else new_seed())
    load_idx = int(st.get("last_accepted_segment") or 0)
    if load_idx and not PJ.mc_slot_exists(load_idx):
        raise GateRefused(
            f"上一段（第 {load_idx} 段）的接续存档在磁盘上找不到，"
            f"无法继续接续生成。请检查输出目录或回到该段重跑。")
    dur = float(resolved["end_time"] - resolved["start_time"])
    frames = P.seconds_to_frames(dur)
    remaining = max(0, len(segs) - cur + 1)
    return {
        "project_id": project_id,
        "segment_id": cur,
        "prompt": prompt,
        "resolved_segment": resolved,
        "prompt_target_node": P.NODE["console"],
        # ...and which node actually carries the text. `prompt_target_node` names
        # the console the human interacts with; the front end must never confuse
        # the two, so the destination is stated explicitly instead of being
        # hardcoded in JS (a renumbering here would otherwise drive a wrong widget
        # while the panel still reported success).
        "prompt_text_node": P.NODE["prompt_ref2va"],
        "prompt_writer": "N159 -> N138 -> N915 -> N136",
        "duration_sec": dur,
        "expected_frames": frames,
        "seed": int(use_seed),
        "continuation": {"selector_node": P.NODE["continuation_switch"],
                         # P11 BUG-7 (found statically, before any GPU time was
                         # spent on it): this used to read
                         # `CONT_ON if load_idx > 0 else CONT_OFF`, i.e. 关闭 for the
                         # first segment. But all five official motion-context nodes
                         # 993-997 carry properties.h3_continuation_branch=True, and
                         # h3_workflow_ux.js:1040-1043 puts EVERY one of them into
                         # mode=4(BYPASS) while 接续生产=关闭 - including 995, the SAVE
                         # node. So SEG1 could never write clip_00001, while accept()
                         # (this file, line ~298) refuses any segment whose slot is
                         # missing: the very first 【接受并下一步】 would have
                         # dead-locked the whole story, and SEG2's own load gate
                         # ("上一段的接续存档在磁盘上找不到") would then refuse too.
                         # The pack's own contract is the opposite of what we had:
                         # nodes.py:1014-1016 "First clip: 1 here and 0 on the Load
                         # node", with 996 Load(clip_index<=0) -> (None,)
                         # (nodes.py:1123-1125), which makes 993 apply() a documented
                         # no-op returning the conditioning untouched
                         # (nodes.py:390-391) and 994 trim(0) leave the picture alone
                         # (nodes.py:755 `images[n:] if n else images`). So the branch
                         # stays active for every segment and `load_clip_index` below
                         # carries the only first-segment difference - exactly what
                         # V27's own 连拍 does for clip 1.
                         "value": CONT_ON,
                         "strength": CONT_STRENGTH,
                         "must_fire_callback": True},
        "motion_context": {
            "load_node": P.NODE["mc_load"], "load_clip_index": load_idx,
            "save_node": P.NODE["mc_save"], "save_clip_index": cur,
            "chain_node": P.NODE["mc_chain"], "chain_segments": remaining,
            "slot_dir": str(P.COMFY_OUTPUT / P.MC_SLOT_DIRNAME),
            "expected_slot": str(PJ.mc_slot_path(cur)),
        },
        "ref_image_nodes": list(P.NODE["ref_images"]),
        "reference_pictures": plan.get("references") or {},
        "advance_without_queue": True,
        "beat": seg.get("beat"),
        "same_seed": bool(same_seed),
    }


def mark_generating(project_id: str, *, instruction: dict) -> dict:
    st, _, _ = current_segment(project_id)
    st["attempt"] = int(st.get("attempt") or 0) + 1
    gid = f"g{int(st['attempt'])}"
    st["current_candidate"] = {
        "generation_id": gid, "segment_id": int(instruction["segment_id"]),
        "seed": int(instruction["seed"]), "expected_frames": instruction["expected_frames"],
        "motion_context_load_index": int(instruction["motion_context"]["load_clip_index"]),
        "prompt_sha": _sha(instruction["prompt"]), "started_at": _now(),
        "video": None, "audio_present": None, "state": "GENERATING"}
    st["status"] = "GENERATING"
    st["errors"] = []
    PJ.save_prompt_text(project_id, int(instruction["segment_id"]),
                        instruction["prompt"], kind=f"submit_{gid}")
    PJ.log_line(project_id, f"submit seg{instruction['segment_id']} seed={instruction['seed']} "
                            f"load={instruction['motion_context']['load_clip_index']} "
                            f"save={instruction['motion_context']['save_clip_index']}")
    return save_state(project_id, st)


def mark_error(project_id: str, message: str) -> dict:
    """Task 30: a failure is confined to the current segment. No advance, no delete."""
    st, _, _ = current_segment(project_id)
    cand = st.get("current_candidate") or {}
    if cand:
        cand["state"] = "FAILED"
        st["current_candidate"] = cand
    st["status"] = "ERROR"
    st["errors"] = (list(st.get("errors") or []) +
                    [{"at": _now(), "segment_id": st.get("current_segment"),
                      "detail": str(message)[:400]}])[-24:]
    PJ.log_line(project_id, f"ERROR seg{st.get('current_segment')}: {str(message)[:200]}")
    return save_state(project_id, st)


def mark_candidate(project_id: str, *, video: str, seed: int | None = None,
                   extra: dict | None = None) -> dict:
    """Task 21: generation finished -> CANDIDATE_READY. Never auto-accepts."""
    st, plan, _ = current_segment(project_id)
    cand = st.get("current_candidate") or {}
    cur = int(st.get("current_segment") or 1)
    segs = plan.get("segments") or []
    used_seed = int(seed if seed is not None else cand.get("seed") or 0)
    # BUG-9 additive: record the ACTUALLY delivered frame count so the card can
    # show planned (expected_frames) vs delivered. expected_frames is untouched.
    actual = probe_video_frame_count(video)
    planned = cand.get("expected_frames")
    load_index = int(cand.get("motion_context_load_index") or 0)
    trim = None
    context_note = None
    if load_index > 0 and isinstance(planned, int) and isinstance(actual, int):
        trim = max(0, planned - actual)
        if trim:
            context_note = f"Motion Context 接续实际交付比计划少 {trim} 帧"
    cand.update({"segment_id": cur, "state": "CANDIDATE", "video": str(video),
                 "finished_at": _now(), "seed": used_seed,
                 "actual_delivered_frames": actual,
                 "context_trim": trim,
                 "context_note": context_note})
    cand.update(extra or {})
    st["current_candidate"] = cand
    st["status"] = "CANDIDATE_READY"
    rec = dict(cand)
    rec["accepted"] = False
    # The slot facts have to be computed BEFORE record_clip(): they used to be
    # written into `rec` two lines after the file was already serialised, so
    # `motion_context_slot` / `motion_context_slot_exists` never reached disk and
    # never appeared in the /candidate reply - the candidate receipt silently
    # lacked the one field that says whether this clip can be accepted at all.
    slot = PJ.mc_slot_path(cur)
    rec["motion_context_slot"] = str(slot)
    rec["motion_context_slot_exists"] = slot.is_file()
    PJ.record_clip(project_id, kind="candidates", segment_id=cur, payload=rec)
    if segs and 1 <= cur <= len(segs):
        segs[cur - 1]["seed"] = used_seed
        PJ.write(project_id, "STORY_PLAN.json", plan)
    PJ.log_line(project_id, f"CANDIDATE seg{cur} -> {video}")
    return save_state(project_id, st)


def accept(project_id: str) -> dict:
    """Task 24's five atomic steps, in order, then STOP. Nothing is queued."""
    st, plan, _ = current_segment(project_id)
    if st.get("status") != "CANDIDATE_READY":
        raise GateRefused("只有已生成并等待确认的候选片段才能被接受"
                          f"（当前状态：{st.get('status')}）")
    cand = st.get("current_candidate") or {}
    cur = int(cand.get("segment_id") or st.get("current_segment") or 1)
    segs = plan.get("segments") or []
    slot = PJ.mc_slot_path(cur)
    if not slot.is_file():
        raise GateRefused(
            f"第 {cur} 段的接续存档还没有写入磁盘，暂时不能接受并进入下一段。"
            f"请确认本段已完整生成。")

    # 1. candidate -> ACCEPTED
    rec = dict(cand)
    rec.update({"accepted": True, "accepted_at": _now(),
                "motion_context_slot": str(slot),
                "motion_context_version": P.V27_MOTION_CONTEXT_VERSION})
    PJ.record_clip(project_id, kind="accepted", segment_id=cur, payload=rec)

    # 2. its final Motion Context latent becomes LAST_ACCEPTED_CONTEXT
    st["last_accepted_segment"] = cur
    st["last_accepted_context"] = {"segment_id": cur, "slot": str(slot),
                                   "seed": rec.get("seed"), "at": _now()}

    # 3. advance the cursor
    if 1 <= cur <= len(segs):
        segs[cur - 1]["seed"] = rec.get("seed") if rec.get("seed") is not None else \
            segs[cur - 1].get("seed")
        segs[cur - 1]["locked"] = True          # accepted segments are frozen
    accepted = [a for a in (st.get("accepted") or []) if a.get("segment_id") != cur]
    accepted.append({"segment_id": cur, "video": rec.get("video"),
                     "seed": rec.get("seed"), "accepted_at": rec["accepted_at"]})
    accepted.sort(key=lambda a: int(a.get("segment_id") or 0))
    st["accepted"] = accepted
    nxt = cur + 1
    st["current_segment"] = min(nxt, len(segs) or 1)

    # 4. load the next segment's prompt (compiled, not merely stored)
    st["current_candidate"] = None
    # Step 3 mutated the plan - `locked = True` and the seed that really produced
    # the accepted clip - so the plan must be written on the LAST accept too. It
    # used to be written only in the else-branch below, which meant a finished
    # story left STORY_PLAN.json with locked=False and seed=None: reopening it (or
    # 【从当前段重新规划后续】, §27) would treat every accepted segment as free to
    # rewrite, and §23's "which seed made this clip" stopped being answerable from
    # the plan alone. Same order as before: plan first, then the state file.
    PJ.write(project_id, "STORY_PLAN.json", plan)
    if nxt > len(segs):
        st["status"] = "COMPLETE"
        st["next_segment"] = None
        PJ.log_line(project_id, f"story complete after seg{cur}")
    else:
        st["status"] = "READY"
        st["next_segment"] = nxt + 1 if nxt < len(segs) else None

    # 5. STOP - task 24: 禁止自动开始生成下一段
    PJ.log_line(project_id, f"ACCEPTED seg{cur}; cursor -> {st['current_segment']} "
                            f"(no queue performed)")
    return save_state(project_id, st)


def prepare_reroll(project_id: str, *, same_seed: bool = False) -> dict:
    """Task 22/23: drop the candidate, keep last accepted + its latent, stay put."""
    st, plan, _ = current_segment(project_id)
    cur = int(st.get("current_segment") or 1)
    if cur <= int(st.get("last_accepted_segment") or 0):
        raise IllegalTransition("current_segment 不可能小于等于已接受段")
    st["current_candidate"] = None
    st["status"] = "RETRY_PENDING"
    segs = plan.get("segments") or []
    if same_seed:
        seed = int((segs[cur - 1] if 1 <= cur <= len(segs) else {}).get("seed") or 0) or new_seed()
    else:
        seed = new_seed()
    st["reroll"] = {"segment_id": cur, "same_seed": bool(same_seed), "seed": seed,
                    "at": _now(),
                    "kept": {"last_accepted_segment": st.get("last_accepted_segment"),
                             "story_plan_unchanged": True}}
    PJ.log_line(project_id, f"REROLL seg{cur} same_seed={same_seed} new_seed={seed}")
    out = save_state(project_id, st)
    out["_next_seed"] = seed
    return out


def edit_segment(project_id: str, *, segment_id: int, beat: str = "",
                 prompt: str = "", duration: float | None = None,
                 directives: dict | None = None, persist: bool = True) -> dict:
    """Task 27: an edit reaches the current segment and later, never accepted ones."""
    st, plan, _ = current_segment(project_id)
    segs = plan.get("segments") or []
    if not (1 <= int(segment_id) <= len(segs)):
        raise GateRefused(f"段号 {segment_id} 不在 1..{len(segs)}")
    seg = segs[int(segment_id) - 1]
    if seg.get("locked") or int(segment_id) <= int(st.get("last_accepted_segment") or 0):
        raise GateRefused(f"第 {segment_id} 段已被接受锁定，不能改写已有成果")
    if beat:
        seg["beat"] = str(beat)[:400]
    if prompt:
        seg["prompt"] = str(prompt)[:3000]
    if duration is not None:
        d = float(duration)
        if not (1.0 <= d <= 60.0):
            raise GateRefused("每段时长必须在 1..60 秒之间")
        seg["duration"] = d
    if directives:
        merged = dict(seg.get("directives") or {})
        merged.update({k: v for k, v in directives.items() if v})
        seg["directives"] = merged
    plan["segments"] = segs
    try:
        S.check("story_plan", plan)
    except S.SchemaError as e:
        raise GateRefused("修改后的计划不符合 STORY_PLAN 结构：" + "; ".join(e.errors[:4]))
    if not persist:
        return plan
    PJ.write(project_id, "STORY_PLAN.json", plan)
    PJ.log_line(project_id, f"edited seg{segment_id} (accepted segments untouched)")
    if prompt and PC.looks_compiled(seg.get("prompt") or ""):
        # P11 TEST5-UI / BUG-6. `first_action_sentence` only trusts a *non*-structured
        # seg.prompt and otherwise falls back to the beat, so storing the card's own
        # compiled envelope here costs the segment its English action sentence on the
        # next compile (measured 1748 -> 1613 chars: the whole action line replaced by
        # the Chinese beat). The panel no longer sends an unchanged envelope
        # (h3_director_v28.js saveEdit), but a scripted client can still arrive here,
        # and a rewrite of what will be submitted must never be silent. Recorded, not
        # refused: a human who really did edit the text still gets their way.
        PJ.log_line(project_id, f"edited seg{segment_id}: 送来的文本已是编译稿，"
                                f"编译器将把「本段动作句」退回梗概（beat），"
                                f"原动作句不再参与编译（P11 BUG-6）")
    return plan


def reset_to(project_id: str, segment_id: int) -> dict:
    """Resume from a given segment: cursor moves back, accepted list stays."""
    st, plan, _ = current_segment(project_id)
    segs = plan.get("segments") or []
    n = int(segment_id)
    if not (1 <= n <= len(segs)):
        raise GateRefused(f"段号 {n} 不在 1..{len(segs)}")
    la = int(st.get("last_accepted_segment") or 0)
    if n > la + 1:
        raise GateRefused(f"只能回到第 {la + 1} 段或其之前；第 {n} 段还没有被接续上下文支撑")
    if n <= la:
        # Rewinding below LAST_ACCEPTED. The motion context that segment n
        # continues from is segment n-1's, so the continuity pointer has to move
        # back with the cursor - leaving it at `la` would make the next
        # submission load a latent recorded *after* the segment being remade, and
        # the schema now refuses that shape.
        # Task 30: this never deletes an accepted clip. The later clips stay on
        # disk and stay in `accepted`, tagged superseded_at so the UI can still
        # list and play them; re-accepting one is the user's call, not ours.
        for a in (st.get("accepted") or []):
            if int(a.get("segment_id") or 0) >= n and not a.get("superseded_at"):
                a["superseded_at"] = _now()
        st["last_accepted_segment"] = n - 1
        st["last_accepted_context"] = None
        PJ.log_line(project_id,
                    f"cursor reset to seg{n}: continuity pointer -> seg{n - 1}, "
                    f"segments {n}..{la} tagged superseded (no clip deleted)")
    st["current_segment"] = n
    st["current_candidate"] = None
    st["status"] = "READY"
    st["next_segment"] = n + 1 if n < len(segs) else None
    for i, s in enumerate(segs, start=1):
        if i >= n:
            s["locked"] = False
    PJ.write(project_id, "STORY_PLAN.json", plan)
    PJ.log_line(project_id, f"cursor reset to seg{n}")
    return save_state(project_id, st)


# --------------------------------------------------------------------------
# the task-31 gate, expressed in state-machine language
# --------------------------------------------------------------------------
def _gate():
    from . import v28_runtime_contract as RC
    return RC.generation_gate()


def require_director_released(project_id: str = "") -> None:
    if project_id and PR.source(project_id) == PR.MANUAL:
        return
    allowed, msg, details = _gate()
    if not allowed:
        if project_id:
            PJ.log_line(project_id, f"generation refused: {msg}")
        # "kind" is read by v28_routes._err() and put on the wire, so the card can
        # show this in the §31 red bar (whose buttons are 停止并释放导演模型 /
        # 回收残留进程) and show a structure refusal somewhere else.
        raise GateRefused(msg, {**(details or {}), "kind": "vram_gate"})


def view(project_id: str) -> dict:
    """Everything the Chinese card needs, in one read."""
    st, plan, profile = current_segment(project_id)
    segs = plan.get("segments") or []
    cur = int(st.get("current_segment") or 1)
    seg = segs[cur - 1] if 1 <= cur <= len(segs) else {}
    allowed, gate_msg, gate = ((True, "导演关闭，手工连续生成可用", {})
                               if PR.source(project_id) == PR.MANUAL else _gate())
    return {
        "project_id": project_id,
        "status": st.get("status"),
        "segment_count": len(segs),
        "current_segment": cur,
        "last_accepted_segment": int(st.get("last_accepted_segment") or 0),
        "next_segment": st.get("next_segment"),
        "story_goal": plan.get("story_goal"),
        "continuation_mode": plan.get("continuation_mode"),
        "segments": [{"id": s.get("id"), "beat": s.get("beat"),
                      "dialogue_summary": (s.get("user_display_zh") or {}).get("dialogue") or "无台词",
                      "duration": s.get("duration"), "locked": bool(s.get("locked")),
                      "seed": s.get("seed"),
                      "start_state": s.get("start_state"), "end_state": s.get("end_state"),
                      "directives": s.get("directives")} for s in segs],
        "current": {"beat": seg.get("beat"), "prompt": seg.get("prompt"),
                    "user_display_zh": seg.get("user_display_zh") or {},
                    "render_risk": seg.get("render_risk") or {},
                    "planning_advisories": seg.get("planning_advisories") or [],
                    "body_state_start": seg.get("body_state_start") or {},
                    "body_state_end": seg.get("body_state_end") or {},
                    "micro_timeline": seg.get("micro_timeline") or [],
                    "duration": seg.get("duration"), "directives": seg.get("directives"),
                    "start_state": seg.get("start_state"), "end_state": seg.get("end_state"),
                    "locked": bool(seg.get("locked"))},
        "candidate": frame_delivery_facts(st.get("current_candidate")),
        "accepted": st.get("accepted") or [],
        "errors": (st.get("errors") or [])[-6:],
        "attempt": st.get("attempt"),
        "plan_version": st.get("plan_version"),
        "gate": {"generation_allowed": allowed, "message": gate_msg, **gate},
        "has_profile": bool(profile),
        "updated_at": st.get("updated_at"),
    }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def frame_delivery_facts(candidate: dict | None) -> dict | None:
    """Return additive planned/delivered display facts without mutating state.

    ``expected_frames`` always remains the plan.  A probed delivered count wins;
    ``context_trim`` is only a fallback when a legacy/external candidate did not
    carry the real count.  This precedence is the no-double-subtraction gate.
    """
    if not isinstance(candidate, dict):
        return None
    out = dict(candidate)
    planned = out.get("expected_frames")
    actual = out.get("actual_delivered_frames")
    trim = out.get("context_trim")
    if not isinstance(actual, int) and isinstance(planned, int) and isinstance(trim, int):
        actual = max(0, planned - max(0, trim))
        out["actual_delivered_frames"] = actual
    if out.get("context_note") is None and isinstance(trim, int) and trim > 0:
        out["context_note"] = f"Motion Context 接续实际交付比计划少 {trim} 帧"
    return out


# --------------------------------------------------------------------------- #
# BUG-9 additive display: planned vs actually-delivered frame count.
#
# The planned count is `expected_frames` (= V27's N131 frame law, see
# seconds_to_frames). The *delivered* count comes from the real generated video
# and is NEVER the same number the plan predicted (VAE alignment, last-frame
# rounding, model behaviour). Task 24's watch-the-clip node is permanent, so the
# human reviewer must be able to SEE the gap. This helper is the data source for
# that display. It is strictly additive: it never touches expected_frames, never
# raises, and returns None (card shows "—") when the probe cannot run.
# --------------------------------------------------------------------------- #
def _ffprobe_bin() -> str | None:
    env = os.environ.get("H3V28_FFPROBE_BIN")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("ffprobe")
    if found:
        return found
    # Common WinGet install location on this machine; harmless if absent.
    win = (r"<USER_HOME>/AppData/Local/Microsoft/WinGet/Packages/"
           r"Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/"
           r"ffmpeg-8.1.1-full_build/bin/ffprobe.exe")
    if os.path.isfile(win):
        return win
    return None


def probe_video_frame_count(video: str) -> int | None:
    """Return the real frame count of a candidate video, or None.

    Additive only: never raises, never alters expected_frames or any plan value.
    `video` may be a bare filename or a /view?... / http://... URL; only the
    basename is used to locate the file under COMFY_OUTPUT.
    """
    if not video:
        return None
    name = str(video).split("?")[0].split("/")[-1]
    if not name:
        return None
    base = str(P.COMFY_OUTPUT)
    targets = [os.path.join(base, name)]
    if os.path.isdir(base):
        for d in os.listdir(base):
            targets.append(os.path.join(base, d, name))
    target = next((t for t in targets if os.path.isfile(t)), None)
    if target is None:
        return None
    exe = _ffprobe_bin()
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "-v", "error",
                              "-show_entries", "stream=nb_frames,duration",
                              "-of", "json", target],
                             capture_output=True, text=True, timeout=30)
        data = json.loads(out.stdout or "{}")
        for s in data.get("streams", []):
            nb = s.get("nb_frames")
            if nb and str(nb).strip().isdigit():
                return int(nb)
        return None
    except Exception:
        return None
