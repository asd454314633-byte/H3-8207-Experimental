"""Prompt sources and the provider-independent segment execution contract."""
from __future__ import annotations

import copy
from . import v28_director_core as C
from . import v28_project as PJ
from . import v28_schemas as S

MANUAL = "MANUAL"
DIRECTOR = "DIRECTOR"
SOURCE_FILE = "PROMPT_SOURCE.json"
MANUAL_FILE = "MANUAL_PROMPTS.json"
RESOLVED_FILE = "RESOLVED_SEGMENTS.json"
STATUS_FILE = "DIRECTOR_STATUS.json"


def source(project_id: str) -> str:
    saved = PJ.read(project_id, SOURCE_FILE, default={}) or {}
    value = saved.get("prompt_source")
    if value in (MANUAL, DIRECTOR):
        return value
    # Existing projects retain their plan; new projects start with Director OFF.
    return DIRECTOR if PJ.has_plan(project_id) else MANUAL


def set_source(project_id: str, value: str) -> None:
    if value not in (MANUAL, DIRECTOR):
        raise ValueError("PROMPT_SOURCE 必须是 MANUAL 或 DIRECTOR")
    PJ.write(project_id, SOURCE_FILE, {"prompt_source": value})


def resolve(plan: dict, planner: dict, *, prompts: list[str] | None = None,
            generation_parameters: dict | None = None) -> list[dict]:
    clocks = planner["segment_skeleton"]
    texts = prompts if prompts is not None else [x["prompt"] for x in plan["segments"]]
    if len(texts) != len(clocks) or any(not isinstance(x, str) or not x.strip() for x in texts):
        raise ValueError(f"必须填写全部 {len(clocks)} 段的提示词")
    return [{"segment_id": clock["segment_index"], "start_time": clock["start_time"],
             "end_time": clock["end_time"], "final_prompt": text,
             "reference_mapping": copy.deepcopy(planner["ACTIVE_REFERENCE_MAP"]),
             "generation_parameters": copy.deepcopy(generation_parameters or {})}
            for clock, text in zip(clocks, texts)]


def manual_plan(planner: dict, prompts: list[str], *, continuation_mode: str,
                generation_parameters: dict | None = None) -> tuple[dict, list[dict]]:
    resolved = resolve({}, planner, prompts=prompts, generation_parameters=generation_parameters)
    plan = {"version": S.SCHEMA_VERSION, "story_goal": planner.get("story_goal") or "手工连续生成",
            "global_state": {"prompt_source": MANUAL}, "continuation_mode": continuation_mode,
            "references": {"active_reference_map": copy.deepcopy(planner["ACTIVE_REFERENCE_MAP"])},
            "segments": [{"id": r["segment_id"], "beat": f"手工第 {r['segment_id']} 段",
                          "duration": r["end_time"] - r["start_time"], "prompt": r["final_prompt"],
                          "start_state": {}, "end_state": {}, "directives": {},
                          "seed": (r["generation_parameters"].get("seed")), "locked": False}
                         for r in resolved]}
    S.check("story_plan", plan)
    return plan, resolved


def execution_segments(project_id: str) -> list[dict]:
    saved = PJ.read(project_id, RESOLVED_FILE, default=None)
    if isinstance(saved, list) and saved:
        return saved
    # Internal migration of existing projects needs no model or user re-entry.
    plan = PJ.read(project_id, "STORY_PLAN.json", default={}) or {}
    profile = PJ.read(project_id, "REFERENCE_PROFILE.json", default={}) or {}
    planner = profile.get("director_input")
    if not isinstance(planner, dict):
        clocks = []
        start = 0.0
        for i, seg in enumerate(plan.get("segments", []), 1):
            end = start + seg["duration"]
            clocks.append({"segment_index": i, "start_time": start, "end_time": end})
            start = end
        planner = {"segment_skeleton": clocks,
                   "ACTIVE_REFERENCE_MAP": plan.get("references", {}).get("active_reference_map", [])}
    return resolve(plan, planner)


def final_prompt(project_id: str, segment_id: int) -> str:
    segments = execution_segments(project_id)
    if not 1 <= segment_id <= len(segments):
        raise ValueError("段号不在时间轴范围内")
    return segments[segment_id - 1]["final_prompt"]
