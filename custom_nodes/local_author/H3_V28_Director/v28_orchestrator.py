"""V28 Director - LAYER 3 orchestration: the two phases the task defines.

PHASE A (one call, run once per project) - task sections 19/31/33/34:
    start text director -> record user-defined references -> plan the WHOLE film -> compile every
    segment deterministically -> stop the director and confirm release.
    The LLM is never consulted again afterwards: sections 24-27's per-segment
    operations are pure state-machine work.

PHASE B (once per segment, no LLM):
    gate -> widget instructions -> GENERATING -> CANDIDATE_READY
         -> user ACCEPT (advances, never queues) or RE-ROLL (stays put).

Everything that can block (the HTTP call into llama-server, the 27B load) runs
in a worker thread, because these functions are reached from the aiohttp event
loop and a 600-second planning run must not freeze ComfyUI's own websocket.

Failure policy (section 34): a repair-exhausted reply is written out raw and the
project's existing plan/state are left exactly as they were. Nothing here ever
rewrites STORY_PLAN.json or SESSION_STATE.json on the error path.
"""
from __future__ import annotations

import json
import copy
import re
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from . import v28_paths as P
from . import v28_project as PJ
from . import v28_prompt_compiler as PC
from . import v28_director_core as CORE
from . import v28_provider as V
from . import v28_schemas as S
from . import v28_state_machine as SM
from . import v28_runtime_contract as RC
from . import v28_prompt_resolution as PR

PENDING_NAME = "PENDING_INSTRUCTION.json"
TASKS: dict[str, dict] = {}
_TASKS_ORDER: list[str] = []
_MAX_TASKS = 24
_LOCK = threading.RLock()
_PLAN_RUNNING = threading.Lock()      # section 19: exactly one planning run


# --------------------------------------------------------------------------- #
# progress tasks (the UI polls these; nothing here blocks an HTTP handler)
# --------------------------------------------------------------------------- #
def _new_task(kind: str, project_id: str = "") -> dict:
    task = {"task_id": uuid.uuid4().hex[:12], "kind": kind, "project_id": project_id,
            "status": "RUNNING", "lines": [], "result": None, "error": None,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_at": None}
    with _LOCK:
        TASKS[task["task_id"]] = task
        _TASKS_ORDER.append(task["task_id"])
        while len(_TASKS_ORDER) > _MAX_TASKS:
            TASKS.pop(_TASKS_ORDER.pop(0), None)
    return task


def _say(task: dict, text: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {text}"
    with _LOCK:
        task["lines"] = (task["lines"] + [line])[-120:]
    if task.get("project_id"):
        PJ.log_line(task["project_id"], text)


def task_state(task_id: str) -> dict | None:
    with _LOCK:
        task = TASKS.get(task_id)
        return json.loads(json.dumps(task, ensure_ascii=False)) if task else None


def recent_tasks(project_id: str = "") -> list[dict]:
    with _LOCK:
        out = [dict(TASKS[t]) for t in reversed(_TASKS_ORDER) if t in TASKS]
    if project_id:
        out = [t for t in out if t.get("project_id") == project_id]
    return out[:10]


def _finish(task: dict, *, ok: bool, result: Any = None, error: str = "") -> None:
    with _LOCK:
        recoverable = isinstance(result, dict) and result.get("director_status") == "FAILED_RECOVERABLE"
        task["status"] = "FAILED_RECOVERABLE" if recoverable else ("DONE" if ok else "ERROR")
        task["result"] = result
        task["error"] = None if ok else str(error)[:800]
        task["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _spawn(task: dict, fn: Callable[[], Any]) -> threading.Thread:
    def runner():
        try:
            result = fn()
            _finish(task, ok=True, result=result)
            _say(task, "完成")
        except Exception as exc:                       # noqa: BLE001 - reported to UI
            _say(task, f"失败：{type(exc).__name__}: {exc}")
            _finish(task, ok=False, error=f"{type(exc).__name__}: {exc}")
    t = threading.Thread(target=runner, daemon=True, name=f"h3v28-{task['kind']}")
    t.start()
    return t


# --------------------------------------------------------------------------- #
# reference images: the UI sends what is on the graph, we resolve on disk
# --------------------------------------------------------------------------- #
def _input_dirs() -> list[Path]:
    """Prefer ComfyUI's own folder map; fall back to the 8197 input dir."""
    dirs: list[Path] = []
    try:
        import folder_paths                                   # inside the ComfyUI proc
        base = folder_paths.get_input_directory()
        dirs.append(Path(base))
    except Exception:                                         # noqa: BLE001
        pass
    dirs.append(P.COMFY_ROOT / "input")
    return [d for d in dirs if d.is_dir()]


def resolve_input_image(name: str) -> Path | None:
    """Map an uploaded filename (possibly `subdir/file.png`) to a real path,
    refusing anything that escapes the input directory."""
    raw = str(name or "").strip().replace("\\", "/").strip("/")
    if not raw or ".." in Path(raw).parts:
        return None
    for base in _input_dirs():
        cand = (base / raw).resolve()
        try:
            cand.relative_to(base.resolve())
        except ValueError:
            continue
        if cand.is_file():
            return cand
    return None


def reference_images(names: list[str], *, node_ids: list[int] | None = None) -> list[dict]:
    """Resolve up to nine neutral slots and attach the one canonical mapping.

    Empty slots are skipped, so a 2-image project really sends 2 images and
    <Picture 1>/<Picture 2> keep the meaning the graph gave them.
    """
    out: list[dict] = []
    for i, nm in enumerate(names or [], start=1):
        path = resolve_input_image(nm)
        if path is None:
            continue
        out.append({"index": len(out) + 1,
                    "picture": f"<Picture {len(out) + 1}>",
                    "slot_index": i,
                    "node": (node_ids[i - 1] if node_ids and i <= len(node_ids) else None),
                    "name": path.name, "filename": path.name, "path": str(path),
                    "size": path.stat().st_size})
    mapping = CORE.active_reference_map([x["slot_index"] for x in out])
    for image, item in zip(out, mapping):
        image["index"] = item["h3_picture"]
        image["picture"] = f"<Picture {item['h3_picture']}>"
    return out


# --------------------------------------------------------------------------- #
# PHASE A - plan the whole film, then unload
# --------------------------------------------------------------------------- #
def _director_plan_now(*, project_id: str, story_goal: str, images: list[dict],
             total_seconds: float, segment_seconds: float,
             style: str = "auto", continuation_mode: str = "same_shot",
             reference_usage: str = "",
             user_constraints: str = "",
             dialogue_mode: str = "无台词", source_dialogue: str = "",
             dialogue_density: str = "正常", allow_polish: bool = False,
             provider: str = "", task: dict | None = None,
             keep_director_up: bool = False, generation_settings: dict | None = None) -> dict:
    """Synchronous PHASE A. Returns {"project_id", "segment_count", "release", "view"}.

    `keep_director_up` exists only for the provider self-test; the production
    path never sets it, because section 31 forbids the director staying resident
    while H3 generates.
    """
    say: Callable[[str], None] = (lambda t: _say(task, t)) if task else (lambda t: None)
    if not story_goal or not str(story_goal).strip():
        raise V.DirectorError("必须先填写总剧情构想")
    if not images:
        raise V.DirectorError("参考图为空：请先在 9 个中性参考图槽里上传素材")
    if continuation_mode not in ("same_shot", "natural_cut"):
        raise V.DirectorError(f"未知的接续模式 {continuation_mode!r}")

    prov = V.get_provider(provider or None)
    name = getattr(prov, "name", "?")
    # Bound before the try: the finally branch that keeps the model up (provider
    # self-test) never assigns it, and line 263 reads it unconditionally.
    release: dict = {"verdict": "NOT_RUN", "detail": "未走释放流程"}
    if not PJ.exists(project_id):
        PJ.create(project_id=project_id, title=str(story_goal)[:24])
    if task:
        task["project_id"] = project_id

    busy = _PLAN_RUNNING.acquire(blocking=False)
    if not busy:
        raise V.DirectorError("已有一次剧情规划正在运行，请等待它结束")
    try:
        active_slots = [int(x.get("slot_index") or i) for i, x in enumerate(images, 1)]
        planner = CORE.planner_input(
            active_slots=active_slots,
            reference_usage=str(reference_usage or ""),
            story_goal=str(story_goal), total_seconds=total_seconds,
            segment_seconds=segment_seconds, dialogue_mode=dialogue_mode,
            source_dialogue=source_dialogue,
            constraints=str(user_constraints or ""),
            planner_controls={"dialogue_density": dialogue_density,
                              "allow_polish": bool(allow_polish)})
        profile = {"version": S.SCHEMA_VERSION,
                   "source_pictures": [{"index": x["index"], "filename": x["filename"],
                                        "width": 0, "height": 0} for x in images],
                   "subjects": [], "scene": {"user_text_only": True}, "props": [],
                   "composition": {}, "uncertain": [],
                   "not_answerable": ["image pixels are not supplied to Gemma4"],
                   "director_input": planner}
        snapshot = PJ.core_snapshot(project_id)
        director_staging = {"profile": profile, "plan": None, "compiled": []}
        say(f"启动导演模型（{name}）…")
        prov.start()
        h = prov.health()
        if not h.ok:
            raise V.DirectorUnavailable(f"导演模型未就绪：{h.detail}")
        say(f"导演模型在线：{h.model} @ {h.endpoint}")
        # Provenance goes to the project log, NOT into the artifact: PROFILE_KEYS is
        # closed and does not carry `director` (P11 TEST3 - the provider used to
        # stamp it after its own validation, so the S.check above threw away a
        # completed three-minute vision run).
        PJ.log_line(project_id, f"PROFILE_FROM provider={name} "
                                f"model={getattr(prov, 'model', '')} at={V.utc_stamp()}")
        say(f"已建立 canonical reference map：{len(images)} 张；Gemma Vision=OFF")

        n = int(planner["required_segment_count"])
        say(f"确定性时间轴已建立：{n} 段；Gemma 只填写导演语义…")
        try:
            plan = prov.plan_story(story_goal=str(story_goal).strip(), profile=profile,
                                   total_seconds=float(total_seconds),
                                   segment_seconds=float(segment_seconds),
                                   style=style, continuation_mode=continuation_mode,
                                   expect_segments=n)
            plan = CORE.validate_director_plan(plan, planner)
        except V.SchemaRepairFailed as exc:
            _stash_raw(project_id, "plan_story", exc)
            raise
        if len(plan.get("segments") or []) != n:
            raise V.DirectorError("程序时间轴内部错误：segment skeleton 未保持精确段数")

        # deterministic compile of EVERY segment, right here, once (section 19).
        segs = plan["segments"]
        all_warnings: list[str] = []
        try:
            compiled = [_compile_segment(plan, i, profile)
                        for i in range(1, len(segs) + 1)]
            for i, (seg, bundle) in enumerate(zip(segs, compiled), start=1):
                text, warns = bundle["CANONICAL_H3_PROMPT"], []
                problems = PC.audit_prompt(text)
                if problems:
                    raise V.SchemaRepairFailed(
                        "compile_segment",
                        [f"seg{i}: {p}" for p in problems], [text])
                director_staging["compiled"].append(text)
                seg["id"] = i
                seg["beat"] = ((seg.get("user_display_zh") or {}).get("action_progression")
                               or seg.get("new_action") or f"第 {i} 段")
                seg["prompt"] = text; seg["soundscape"] = seg.get("ambience") or ""
                seg["directives"] = {}
                seg["start_state"] = {"text": seg.get("start_state") or ""}
                seg["end_state"] = {"text": seg.get("end_state") or ""}
                seg["seed"] = None; seg["locked"] = False
                seg.pop("segment", None)
                all_warnings += [f"seg{i}: {w}" for w in warns]
        except V.SchemaRepairFailed as exc:
            # §34 says the rejected text must be kept. Until now only the
            # provider's own schema failures were stashed, so a compile-time
            # rejection - which IS a defect in the model's reply, since the
            # compiler is deterministic - left no artifact at all: nothing on
            # disk, nothing in cache/raw_replies, and the log line did not quote
            # the text. Reproducing it then means asking the model for luck again.
            _stash_raw(project_id, "compile_segment", exc)
            raise
        say(f"{n} 段 H3 提示词编译并结构校验通过")
        if all_warnings:
            plan.setdefault("warnings", [])
            plan["warnings"] = list(dict.fromkeys(list(plan.get("warnings") or [])
                                                  + all_warnings))[:20]
        plan["generated_from"] = dict(plan.get("generated_from") or {})
        plan["generated_from"]["compiled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                              time.gmtime())
        plan["generated_from"]["provider"] = name

        plan.pop("reference_relationships", None)
        plan.pop("ACTIVE_REFERENCE_MAP", None)
        plan["version"] = S.SCHEMA_VERSION
        plan["story_goal"] = str(story_goal)
        plan["global_state"] = {"reference_role_source": "USER_TEXT_ONLY",
                                "reference_timeline_default": "NONE",
                                "director_contract": "GATE6C_STRUCTURED",
                                "prompt_source": "CANONICAL_PLAN_TIME_ONLY"}
        plan["references"] = {"picture_count": len(images),
                              "active_reference_map": planner["ACTIVE_REFERENCE_MAP"]}
        plan["style"] = style or "auto"
        plan["continuation_mode"] = continuation_mode
        # A long structured reply may harmlessly echo planner-input fields at
        # top level (compiled_reference_text, duration counters, dialogue_track,
        # etc.). They are already preserved in REFERENCE_PROFILE.director_input
        # and are not STORY_PLAN fields. Drop only those known echoes before the
        # closed artifact schema runs; unknown model inventions still fail.
        planner_echoes = set(planner) - set(S.PLAN_KEYS)
        echoed = sorted(k for k in planner_echoes if k in plan)
        for key in echoed:
            plan.pop(key, None)
        if echoed:
            PJ.log_line(project_id, f"ignored planner-input echoes in plan: {echoed}")
        S.check("story_plan", plan)
        director_staging["plan"] = plan
        previous_resolved = PJ.read(project_id, PR.RESOLVED_FILE, default=[]) or []
        settings = (generation_settings if generation_settings is not None else
                    previous_resolved[0]["generation_parameters"] if previous_resolved else {})
        resolved = PR.resolve(plan, planner, generation_parameters=settings)
        with PJ.commit_transaction(project_id, snapshot):
            PJ.write(project_id, "REFERENCE_PROFILE.json", profile)
            SM.set_plan(project_id, plan)
            PJ.write(project_id, PR.RESOLVED_FILE, resolved)
            for i, text in enumerate(director_staging["compiled"], 1):
                PJ.save_prompt_text(project_id, i, text, kind="compiled")
            PJ.project_dir(project_id).joinpath(PENDING_NAME).unlink(missing_ok=True)
        director_staging.clear()
        say("计划已落盘，状态 READY（不会自动开始生成）")
    finally:
        try:
            if keep_director_up:
                say("（自检模式）导演模型保持在线")
            else:
                say("停止导演模型并确认资源释放…")
                release = _stop_and_confirm(prov, name)
                _last_release(project_id, release)
                say(f"释放结论 {release.get('verdict')}：{release.get('detail')}")
        finally:
            _PLAN_RUNNING.release()

    if not keep_director_up and release.get("verdict") not in ("RELEASED", "NOT_RUNNING"):
        _say_release_warning(project_id, release)

    return {"project_id": project_id, "segment_count": n,
            "release": release if not keep_director_up else {"verdict": "KEPT_UP"},
            "view": SM.view(project_id)}


def plan_now(*, project_id: str, prompt_source: str = PR.DIRECTOR,
             manual_prompts: list[str] | None = None,
             generation_settings: dict | None = None, **kwargs) -> dict:
    if prompt_source == PR.MANUAL:
        return manual_now(project_id=project_id, manual_prompts=manual_prompts,
                          generation_settings=generation_settings, **kwargs)
    if prompt_source != PR.DIRECTOR:
        raise ValueError("未知提示词来源")
    if _PLAN_RUNNING.locked():
        raise V.DirectorError("已有一次导演规划正在运行")
    if not PJ.exists(project_id):
        PJ.create(project_id=project_id, title=str(kwargs.get("story_goal") or "新故事")[:24])
    PR.set_source(project_id, PR.DIRECTOR)
    PJ.write(project_id, PR.STATUS_FILE, {"director_status": "RUNNING"})
    try:
        if SM.load_state(project_id).get("status") in ("GENERATING", "CANDIDATE_READY"):
            raise V.DirectorError("当前段正在生成或等待确认，请先完成该段")
        result = _director_plan_now(project_id=project_id, generation_settings=generation_settings, **kwargs)
    except Exception as exc:
        failure = {"director_status": "FAILED_RECOVERABLE",
                   "message": "导演生成失败，手工提示词和连续生成功能未受影响。请重试导演，或关闭导演使用手工提示词。",
                   "error": f"{type(exc).__name__}: {exc}"[:800], "at": V.utc_stamp()}
        PJ.write(project_id, PR.STATUS_FILE, failure)
        return {"project_id": project_id, **failure}
    PJ.write(project_id, PR.STATUS_FILE, {"director_status": "COMMITTED", "at": V.utc_stamp()})
    return {**result, "director_status": "COMMITTED"}


def manual_now(*, project_id: str, manual_prompts: list[str] | None = None,
               generation_settings: dict | None = None, **kwargs) -> dict:
    if _PLAN_RUNNING.locked():
        raise V.DirectorError("导演仍在运行，请等待本轮结束后切换手工模式")
    if not PJ.exists(project_id):
        PJ.create(project_id=project_id, title=str(kwargs.get("story_goal") or "手工连续生成")[:24])
    st = SM.load_state(project_id)
    if st.get("status") in ("GENERATING", "CANDIDATE_READY"):
        raise SM.GateRefused("当前段正在生成或等待确认，请先完成该段")
    snapshot = PJ.core_snapshot(project_id)
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default={}) or {}
    old_planner = profile.get("director_input") or {}
    images = kwargs.get("images") or []
    slots = ([int(x.get("slot_index") or i) for i, x in enumerate(images, 1)]
             if "images" in kwargs else [x["ui_slot"] for x in old_planner.get("ACTIVE_REFERENCE_MAP", [])])
    total = float(kwargs.get("total_seconds") or old_planner.get("total_seconds") or 60)
    duration = float(kwargs.get("segment_seconds") or old_planner.get("segment_seconds") or 10)
    if (old_planner.get("total_seconds") == total and old_planner.get("segment_seconds") == duration
            and [x["ui_slot"] for x in old_planner.get("ACTIVE_REFERENCE_MAP", [])] == slots):
        planner = copy.deepcopy(old_planner)
    else:
        planner = CORE.planner_input(active_slots=slots, reference_usage=kwargs.get("reference_usage") or "",
                                     story_goal=kwargs.get("story_goal") or "手工连续生成",
                                     total_seconds=total, segment_seconds=duration,
                                     constraints=kwargs.get("user_constraints") or "")
        profile = {"director_input": planner}
    saved = PJ.read(project_id, PR.MANUAL_FILE, default={}) or {}
    old_plan = PJ.read(project_id, "STORY_PLAN.json", default={}) or {}
    prompts = manual_prompts if manual_prompts is not None else saved.get(
        "prompts", [x.get("prompt", "") for x in old_plan.get("segments", [])])
    settings = generation_settings if generation_settings is not None else saved.get("generation_settings", {})
    plan, resolved = PR.manual_plan(planner, prompts,
        continuation_mode=kwargs.get("continuation_mode") or old_plan.get("continuation_mode") or "same_shot", generation_parameters=settings)
    accepted = int(st.get("last_accepted_segment") or 0)
    for i in range(accepted):
        if (i >= len(plan["segments"]) or i >= len(old_plan.get("segments", [])) or
                plan["segments"][i]["prompt"] != old_plan["segments"][i]["prompt"]):
            raise SM.GateRefused("已接受段落不可被手工草稿覆盖，请从未接受的段落编辑")
        plan["segments"][i] = copy.deepcopy(old_plan["segments"][i])
    with PJ.commit_transaction(project_id, snapshot):
        if not old_planner or old_planner != planner:
            PJ.write(project_id, "REFERENCE_PROFILE.json", profile)
        PJ.write(project_id, PR.MANUAL_FILE, {"prompts": prompts, "generation_settings": settings})
        SM.set_plan(project_id, plan)
        PJ.write(project_id, PR.RESOLVED_FILE, resolved)
        PR.set_source(project_id, PR.MANUAL)
        PJ.project_dir(project_id).joinpath(PENDING_NAME).unlink(missing_ok=True)
    return {"project_id": project_id, "prompt_source": PR.MANUAL,
            "segment_count": len(resolved), "view": SM.view(project_id)}


def start_planning_async(payload: dict) -> dict:
    """Entry point for the HTTP route: returns immediately with a task handle."""
    task = _new_task("plan", payload.get("project_id", ""))
    _spawn(task, lambda: plan_now(
        project_id=payload.get("project_id") or "",
        story_goal=payload.get("story_goal", ""),
        images=payload.get("_images") or [],
        total_seconds=float(payload.get("total_seconds") or 40),
        segment_seconds=float(payload.get("segment_seconds") or 10),
        style=payload.get("style") or "auto",
        continuation_mode=payload.get("continuation_mode") or "same_shot",
        reference_usage=payload.get("reference_usage") or "",
        user_constraints=payload.get("user_constraints") or "",
        dialogue_mode=payload.get("dialogue_mode") or "无台词",
        source_dialogue=payload.get("source_dialogue") or "",
        dialogue_density=payload.get("dialogue_density") or "正常",
        allow_polish=bool(payload.get("allow_polish")),
        provider=payload.get("provider") or "",
        prompt_source=payload.get("prompt_source") or PR.DIRECTOR,
        manual_prompts=payload.get("manual_prompts"),
        generation_settings=payload.get("generation_settings"),
        task=task))
    return {"task_id": task["task_id"]}


def analyze_now(*, project_id: str, story_goal: str = "", images: list[dict],
                provider: str = "", task: dict | None = None) -> dict:
    raise V.DirectorError("导演视觉识别已取消，请用文字定义参考图用途。")


def start_analyze_async(payload: dict) -> dict:
    raise V.DirectorError("导演视觉识别已取消，请用文字定义参考图用途。")


def _stop_and_confirm(prov: V.DirectorProvider, name: str) -> dict:
    try:
        prov.stop()
        state = RC.runtime_snapshot(name)
    except Exception as exc:                            # noqa: BLE001
        return {"verdict": "STOP_FAILED", "detail": f"{type(exc).__name__}: {exc}"}
    return {"verdict": "RELEASED" if state.released else "STILL_RUNNING",
            "detail": "Director 进程已释放" if state.released else "Director 端口或进程仍驻留",
            "runtime": state.as_dict()}


def _last_release(project_id: str, release: dict) -> None:
    try:
        PJ.write(project_id, "RELEASE_RECEIPT.json",
                 {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **release})
    except Exception:                                   # noqa: BLE001
        pass


def _say_release_warning(project_id: str, release: dict) -> None:
    PJ.log_line(project_id, f"RELEASE NOT CONFIRMED: {release}")


def _stash_raw(project_id: str, kind: str, exc: V.SchemaRepairFailed) -> Path | None:
    """Section 34: keep the offending replies for inspection, change nothing else."""
    try:
        d = P.DIRECTOR_CACHE_DIR / "raw_replies"
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = d / f"{stamp}_{os.getpid()}_{kind}.json"
        P.atomic_write_json(path, {"project_id": project_id, "kind": kind,
                                   "errors": exc.errors, "repair_count": exc.repair_count,
                                   "raws": [re.sub(r"(?i)(bearer\s+\S+|sk-[\w-]+)",
                                                   "[REDACTED]", raw[:16384]) for raw in exc.raws]})
        try:
            PJ.project_dir(project_id).joinpath("logs").mkdir(parents=True, exist_ok=True)
            PJ.log_line(project_id, f"schema repair exhausted ({kind}) -> {path.name}")
        except Exception:                               # noqa: BLE001
            pass
        return path
    except Exception:                                   # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# PHASE B - one segment at a time, deterministic
# --------------------------------------------------------------------------- #
def prepare_segment(project_id: str, *, seed: int | None = None,
                    same_seed: bool = False, reroll: bool = False,
                    prompt_override: str = "", manual_prompts: list[str] | None = None) -> dict:
    """The task-31 gate plus the graph write plan. Raises GateRefused in Chinese."""
    src = PR.source(project_id)
    if src == PR.MANUAL and manual_prompts is not None:
        saved = PJ.read(project_id, PR.MANUAL_FILE, default={}) or {}
        if manual_prompts != saved.get("prompts"):
            manual_now(project_id=project_id, manual_prompts=manual_prompts)
    if src == PR.DIRECTOR:
        director_status = PJ.read(project_id, PR.STATUS_FILE, default={}) or {}
        if director_status.get("director_status") in ("RUNNING", "FAILED_RECOVERABLE"):
            raise SM.GateRefused("导演本轮未提交，请重试导演或关闭导演使用手工提示词。")
        SM.require_director_released(project_id)
    plan = PJ.read(project_id, "STORY_PLAN.json", default={}) or {}
    plan_source = plan.get("global_state", {}).get("prompt_source")
    if src == PR.MANUAL and plan_source != PR.MANUAL:
        raise SM.GateRefused("请先保存手工段落提示词，再开始连续生成。")
    if prompt_override:
        st, _, _ = SM.current_segment(project_id)
        edit_and_recompile(project_id, segment_id=int(st["current_segment"]), prompt=prompt_override)
        prompt_override = ""
    instr = SM.widget_instructions(project_id, seed=seed, reroll=reroll,
                                   prompt_override=prompt_override,
                                   same_seed=same_seed)
    # The structural audit has to run on the text that is ABOUT TO BE SUBMITTED,
    # not only on what plan_now compiled. Two paths reached this line unaudited:
    # a manual edit (section 27 arrives here as prompt_override, and
    # widget_instructions takes it verbatim), and a segment whose plan text was
    # empty and got compiled fresh here. Before, a hand-deleted `retention_analysis:`,
    # a dropped `detailed_description:` heading or a second `[Shot 1]` went straight
    # into N138 and the "generation failure" showed up minutes later as a bad clip -
    # the most expensive place to discover a structural problem. This is the cheap place.
    #
    # What this gate checks is STRUCTURE (§35's six sections, the retention markers,
    # one shot marker per clip, section 17's instant-change wording). It deliberately
    # does not check the language of the action prose: §35 leaves "does this need the
    # English template" to V27's production rules, and the compiler's `language:`
    # notice is a warning on the plan, not a refusal - the author may write the action
    # in Chinese on purpose, and H3's encoder reads it.
    #
    # Refusing is the right shape for structure: the UI keeps the offending text on
    # screen so the user can fix it or clear the box to fall back to the compiled
    # version (an unedited box sends "" - no override at all).
    problems = ([] if src == PR.MANUAL else PC.audit_prompt(instr.get("prompt") or "")
                + CORE.audit_control_fields(instr.get("prompt") or ""))
    if problems:
        PJ.log_line(project_id, f"prompt audit refused submit seg{instr.get('segment_id')}: "
                                f"{problems[:4]}")
        raise SM.GateRefused(
            f"第 {instr.get('segment_id')} 段的提示词没有通过 H3 结构校验，已拒绝提交：\n"
            + "\n".join(f"· {p}" for p in problems[:6])
            + "\n请照上面缺项补齐；清空编辑框可回到本段编译出来的版本。",
            {"kind": "prompt_structure", "problems": problems[:6]})
    canonical = CORE.canonical_prompt_bundle(instr.get("prompt") or "", path=src)
    instr.update({k: canonical[k] for k in (
        "CANONICAL_H3_PROMPT", "UI_PREVIEW", "SUBMISSION_PROMPT",
        "PREVIEW_SHA256", "SUBMISSION_PROMPT_SHA256", "PREVIEW_EQUALS_SUBMISSION")})
    P.atomic_write_json(PJ.project_dir(project_id) / PENDING_NAME,
                        {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         **instr})
    return instr


def confirm_submitted(project_id: str, *, seed: int | None = None) -> dict:
    """Called by the UI right after app.queuePrompt() succeeds -> GENERATING."""
    instr = PJ.read(project_id, PENDING_NAME, default=None)
    if not instr:
        raise SM.GateRefused("没有待提交的段落指令，请先点击【生成本段】")
    if instr.get("prompt") != PR.final_prompt(project_id, int(instr["segment_id"])):
        raise SM.GateRefused("段落提示词已修改，请重新准备本段，旧指令未提交")
    if PR.source(project_id) == PR.DIRECTOR:
        status = PJ.read(project_id, PR.STATUS_FILE, default={}) or {}
        if status.get("director_status") in ("RUNNING", "FAILED_RECOVERABLE"):
            raise SM.GateRefused("导演本轮未提交，不能使用旧段落指令")
    if seed is not None:
        instr = dict(instr)
        instr["seed"] = int(seed)
    return SM.mark_generating(project_id, instruction=instr)


def record_candidate(project_id: str, *, video: str = "", seed: int | None = None,
                     extra: dict | None = None) -> dict:
    out = SM.mark_candidate(project_id, video=video, seed=seed, extra=extra)
    try:
        PJ.project_dir(project_id).joinpath(PENDING_NAME).unlink(missing_ok=True)
    except OSError:
        pass
    return out


def accepted_next(project_id: str) -> dict:
    """Section 24's five atomic steps, and explicitly no queue."""
    out = SM.accept(project_id)
    try:
        PJ.project_dir(project_id).joinpath(PENDING_NAME).unlink(missing_ok=True)
    except OSError:
        pass
    return out


def reroll_segment(project_id: str, *, same_seed: bool = False) -> dict:
    st = SM.prepare_reroll(project_id, same_seed=same_seed)
    return prepare_segment(project_id, seed=st.get("_next_seed"),
                           reroll=True, same_seed=same_seed)


def _compile_segment(plan: dict, segment_id: int, profile: dict) -> dict:
    planner = copy.deepcopy(profile.get("director_input"))
    if not isinstance(planner, dict) or "ACTIVE_REFERENCE_MAP" not in planner:
        raise V.DirectorError("项目缺少确定性导演输入，不能恢复职责。请重新建立导演计划；不会回退旧编译器。")
    # Previously persisted planner inputs mixed these two controls into constraints.
    # Migrate only the exact known control assignments; leave semantic prose intact.
    controls = dict(planner.get("planner_controls") or {})
    semantic = []
    for part in re.split(r"[;；]", planner.get("user_constraints") or ""):
        item = part.strip()
        match = re.fullmatch(r"(DIALOGUE_DENSITY|ALLOW_POLISH)\s*=\s*([^;；]+)", item)
        if match:
            controls[match[1].lower()] = match[2]
        elif item:
            semantic.append(part)
    if controls != (planner.get("planner_controls") or {}):
        planner["user_constraints"] = ";".join(semantic).strip()
    planner["planner_controls"] = controls
    bundle = CORE.compile_h3_prompt(planner=planner, plan=plan, segment_id=int(segment_id))
    problems = PC.audit_prompt(bundle["CANONICAL_H3_PROMPT"])
    if problems:
        raise V.SchemaRepairFailed("compile_segment", problems[:4], [bundle["CANONICAL_H3_PROMPT"]])
    return bundle


def segment_prompt(project_id: str, segment_id: int) -> str:
    """Compile from saved semantic inputs; the cache never selects a compiler."""
    plan = PJ.read(project_id, "STORY_PLAN.json", default=None) or {}
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default=None) or {}
    segs = plan.get("segments") or []
    if not (1 <= int(segment_id) <= len(segs)):
        raise V.DirectorError(f"段号 {segment_id} 不在 1..{len(segs)}")
    if plan.get("global_state", {}).get("prompt_source") == PR.MANUAL:
        return PR.final_prompt(project_id, int(segment_id))
    text = _compile_segment(plan, int(segment_id), profile)["CANONICAL_H3_PROMPT"]
    p = PJ.project_dir(project_id) / "prompts" / f"seg_{int(segment_id):03d}_compiled.txt"
    if not p.is_file() or p.read_text(encoding="utf-8") != text:
        PJ.save_prompt_text(project_id, int(segment_id), text, kind="compiled")
    return text


def edit_and_recompile(project_id: str, *, segment_id: int, beat: str = "",
                       prompt: str = "", duration: float | None = None,
                       directives: dict | None = None) -> dict:
    """Section 27: edit from here forward; accepted segments are refused."""
    if PR.source(project_id) == PR.MANUAL:
        st, plan, _ = SM.current_segment(project_id)
        if st.get("status") in ("GENERATING", "CANDIDATE_READY"):
            raise SM.GateRefused("当前段正在生成或等待确认，不能修改提交提示词")
        if int(segment_id) <= int(st.get("last_accepted_segment") or 0):
            raise SM.GateRefused("已接受段落不可覆盖")
        if prompt:
            resolved = PR.execution_segments(project_id)
            resolved[int(segment_id) - 1]["final_prompt"] = prompt
            plan["segments"][int(segment_id) - 1]["prompt"] = prompt
            manual = PJ.read(project_id, PR.MANUAL_FILE, default={}) or {}
            manual["prompts"] = [r["final_prompt"] for r in resolved]
            snapshot = PJ.core_snapshot(project_id)
            with PJ.commit_transaction(project_id, snapshot):
                PJ.write(project_id, PR.MANUAL_FILE, manual)
                PJ.write(project_id, "STORY_PLAN.json", plan)
                PJ.write(project_id, PR.RESOLVED_FILE, resolved)
        return {"plan": plan, "recompiled": []}
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default=None) or {}
    current = segment_prompt(project_id, segment_id)
    old_plan = PJ.read(project_id, "STORY_PLAN.json", default=None) or {}
    if prompt and prompt.strip() == current.strip():
        prompt = ""
    description_edit = ""
    if prompt and PC.looks_compiled(prompt):
        problems = PC.audit_prompt(prompt) + CORE.audit_control_fields(prompt)
        if problems:
            raise V.DirectorError("编辑稿校验未通过：" + "; ".join(problems[:4]))
        changed = [key for key in CORE.SECTIONS if PC._block(prompt, key).strip() != PC._block(current, key).strip()]
        if any(key != "detailed_description" for key in changed):
            raise V.DirectorError("高级动作编辑只修改 detailed_description；参考职责和额外约束请在导演输入中修改后重新规划。")
        description_edit = PC._block(prompt, "detailed_description").strip()
        prompt = ""
    if duration is not None:
        existing = PJ.read(project_id, "STORY_PLAN.json", default=None) or {}
        if float(duration) != float(existing["segments"][int(segment_id) - 1]["duration"]):
            raise V.DirectorError("本轮不改变确定性时间轴；请重新规划时长。")
    plan = SM.edit_segment(project_id, segment_id=segment_id, beat=beat,
                           prompt=prompt, duration=duration, directives=directives,
                           persist=False)
    edited = plan["segments"][int(segment_id) - 1]
    if description_edit:
        edited["detailed_description_edit"] = description_edit
    action = prompt or (beat if beat != old_plan["segments"][int(segment_id) - 1].get("beat") else "")
    if action and not description_edit:
        edited.pop("detailed_description_edit", None)
        action = CORE.compile_reference_text(action, profile["director_input"]["ACTIVE_REFERENCE_MAP"])["compiled_reference_text"]
        edited["new_action"] = action
        edited["beats"] = [action]
    segs = plan.get("segments") or []
    compiled = {}
    for i in range(int(segment_id), len(segs) + 1):
        text = _compile_segment(plan, i, profile)["CANONICAL_H3_PROMPT"]
        compiled[i] = text
    # Admit the entire edit before writing either the plan or its caches.
    S.check("story_plan", plan)
    PJ.write(project_id, "STORY_PLAN.json", plan)
    PJ.write(project_id, PR.RESOLVED_FILE, PR.resolve(plan, profile["director_input"],
        prompts=[compiled.get(i, s["prompt"]) for i, s in enumerate(segs, 1)]))
    recompiled = []
    for i, text in compiled.items():
        PJ.save_prompt_text(project_id, i, text, kind="compiled")
        recompiled.append(i)
    PJ.log_line(project_id, f"edited seg{segment_id}; recompiled {recompiled}")
    return {"plan": plan, "recompiled": recompiled}


# --------------------------------------------------------------------------- #
# one read-only blob for the whole card
# --------------------------------------------------------------------------- #
def card_state(project_id: str) -> dict:
    out: dict[str, Any] = {"project_id": project_id, "providers": V.available_providers()}
    src = PR.source(project_id)
    out["prompt_source"] = src
    out["director"] = PJ.read(project_id, PR.STATUS_FILE, default={}) or {}
    out["manual"] = PJ.read(project_id, PR.MANUAL_FILE, default={}) or {}
    if not out["manual"]:
        plan = PJ.read(project_id, "STORY_PLAN.json", default={}) or {}
        out["manual"] = {"prompts": [s.get("prompt", "") for s in plan.get("segments", [])]}
    out["runtime"] = (RC.get_active_director_runtime().as_dict() if src == PR.DIRECTOR
                      else {"provider_name": "OFF", "resident": False, "released": True})
    try:
        out["view"] = SM.view(project_id)
    except SM.GateRefused as exc:
        out["view"] = None
        out["no_plan"] = str(exc)
    d = PJ.project_dir(project_id) if PJ.exists(project_id) else None
    out["pending"] = bool(d and (d / PENDING_NAME).is_file())
    if d and (d / "RELEASE_RECEIPT.json").is_file():
        out["release"] = PJ.read(project_id, "RELEASE_RECEIPT.json", default={})
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default=None) if d else None
    if isinstance(profile, dict):
        # The card shows what the director saw, not the whole fact bag.
        out["profile"] = {
            "pictures": [
                {"index": p.get("index"), "filename": p.get("filename"),
                 "width": p.get("width"), "height": p.get("height")}
                for p in (profile.get("source_pictures") or []) if isinstance(p, dict)],
            "subjects": [{"id": s.get("id"), "role": s.get("role"),
                          "picture_refs": s.get("picture_refs") or []}
                         for s in (profile.get("subjects") or []) if isinstance(s, dict)],
            "uncertain": [str(u)[:160] for u in (profile.get("uncertain") or [])[:8]],
        }
    out["logs"] = _tail_lines(d / "logs" / "director.log") if d else []
    out["tasks"] = recent_tasks(project_id)
    return out


def _tail_lines(path: Path, n: int = 24) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f.readlines()[-n:]]
    except OSError:
        return []


def list_projects() -> list[dict]:
    return PJ.list_projects()


def create_project(title: str) -> dict:
    return PJ.create(title=title or "")
