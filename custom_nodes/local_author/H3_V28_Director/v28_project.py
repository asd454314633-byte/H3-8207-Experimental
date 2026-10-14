"""V28 Director - project store on disk (task section 28).

Project state deliberately lives OUTSIDE the workflow JSON: a workflow edit must
never be able to destroy a half-finished story. Every write goes through
`v28_paths.atomic_write_json` (unique temp name -> fsync -> rename), which is
what makes section 29's crash recovery claim true.
"""
from __future__ import annotations

import json
import re
import time
import threading
import contextlib
from pathlib import Path
from typing import Any

from . import v28_paths as P

PROJECT_FILES = ("PROJECT.json", "REFERENCE_PROFILE.json", "STORY_PLAN.json",
                 "SESSION_STATE.json")
SUBDIRS = ("prompts", "candidates", "accepted", "logs")
_SAFE = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff.\-]+")
STATE_LOCK = threading.RLock()


def core_snapshot(project_id: str) -> dict[str, bytes]:
    d = project_dir(project_id)
    names = ["REFERENCE_PROFILE.json", "STORY_PLAN.json", "SESSION_STATE.json",
             "RESOLVED_SEGMENTS.json", "MANUAL_PROMPTS.json", "PROMPT_SOURCE.json",
             "PENDING_INSTRUCTION.json"]
    paths = [d / n for n in names] + list((d / "prompts").glob("*.txt"))
    with STATE_LOCK:
        return {str(p.relative_to(d)): p.read_bytes() for p in paths if p.is_file()}


@contextlib.contextmanager
def commit_transaction(project_id: str, expected: dict[str, bytes]):
    """Reject concurrent edits; roll back any failed multi-artifact commit."""
    d = project_dir(project_id)
    with STATE_LOCK:
        if core_snapshot(project_id) != expected:
            raise RuntimeError("规划期间项目输入已修改，请重试导演；本次结果未提交")
        try:
            yield
        except BaseException:
            current = core_snapshot(project_id)
            for name in current.keys() - expected.keys():
                (d / name).unlink()
            for name, data in expected.items():
                (d / name).write_bytes(data)
            raise


def _slug(text: str, limit: int = 24) -> str:
    s = _SAFE.sub("", str(text or ""))[:limit]
    return s or "story"


def project_dir(project_id: str) -> Path:
    pid = _SAFE.sub("", str(project_id or ""))[:64]
    if not pid:
        raise ValueError("非法项目 id")
    return P.PROJECTS_ROOT / pid


def create(title: str = "", project_id: str = "") -> dict:
    P.ensure_dirs()
    pid = project_id or f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(title)}"
    d = project_dir(pid)
    if not project_id and (d / "PROJECT.json").is_file():
        # The auto id is second-resolution plus a slugified title, so two 【新建项目】
        # clicks on the same title inside one second used to land on the SAME
        # directory - and because everything here is mkdir(exist_ok=True) plus an
        # overwrite of PROJECT.json, the second project silently inherited the
        # first one's STORY_PLAN / SESSION_STATE / REFERENCE_PROFILE: a fresh card
        # showing someone else's segments, and accepting on it would rewrite them.
        # Only the generated id gets de-duplicated; an explicit project_id is a
        # resume (routes /state, the tests, plan/analyze of an existing card) and
        # must keep being idempotent.
        for n in range(2, 1000):
            cand = project_dir(f"{pid}_{n}")
            if not (cand / "PROJECT.json").is_file():
                pid, d = f"{pid}_{n}", cand
                break
        else:                                     # pragma: no cover - absurd path
            raise ValueError(f"项目号 {pid} 连续 999 个都已被占用，请先清理 V28_PROJECTS")
    d.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    meta = {"version": 1, "project_id": pid, "title": title or _slug(title),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "workflow_v28": P.V28_DEV_NAME, "v27_sha256": P.V27_SHA256,
            "motion_context_version": P.V27_MOTION_CONTEXT_VERSION,
            "comfy_root": str(P.COMFY_ROOT), "port": 8197}
    P.atomic_write_json(d / "PROJECT.json", meta)
    return meta


def exists(project_id: str) -> bool:
    try:
        return (project_dir(project_id) / "PROJECT.json").is_file()
    except ValueError:
        return False


def read(project_id: str, name: str, default=None) -> Any:
    with STATE_LOCK:
        return P.read_json(project_dir(project_id) / name, default=default)


def write(project_id: str, name: str, payload: Any) -> Path:
    path = project_dir(project_id) / name
    with STATE_LOCK:
        P.atomic_write_json(path, payload)
    return path


def log_line(project_id: str, text: str) -> None:
    try:
        d = project_dir(project_id) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "director.log", "a", encoding="utf-8", newline="\n") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except OSError:
        pass


def save_prompt_text(project_id: str, segment_id: int, text: str,
                     *, kind: str = "compiled") -> Path:
    d = project_dir(project_id) / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    name = f"seg_{int(segment_id):03d}_{kind}.txt"
    with STATE_LOCK:
        P.atomic_write_text(d / name, text)
    return d / name


def record_clip(project_id: str, *, kind: str, segment_id: int, payload: dict) -> Path:
    """kind in {candidates, accepted}. One file per attempt, never overwritten."""
    d = project_dir(project_id) / kind
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H%M%S")
    name = f"seg_{int(segment_id):03d}_{stamp}_{payload.get('generation_id', 'x')}.json"
    P.atomic_write_json(d / name, payload)
    return d / name


def list_projects(limit: int = 40) -> list[dict]:
    out = []
    root = P.PROJECTS_ROOT
    if not root.exists():
        return out
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir() or not (d / "PROJECT.json").is_file():
            continue
        try:
            meta = json.loads((d / "PROJECT.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {"project_id": d.name, "title": d.name, "unreadable": True}
        state = None
        try:
            state = json.loads((d / "SESSION_STATE.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        meta["status"] = (state or {}).get("status", "NO_SESSION")
        meta["current_segment"] = (state or {}).get("current_segment")
        meta["segment_count"] = (state or {}).get("segment_count")
        meta["last_accepted_segment"] = (state or {}).get("last_accepted_segment")
        meta["_dir"] = str(d)
        out.append(meta)
        if len(out) >= limit:
            break
    return out


def resumable_projects() -> list[dict]:
    """【继续上次项目】candidates: planned or mid-flight, but not COMPLETE."""
    return [m for m in list_projects()
            if m.get("status") not in (None, "NO_SESSION", "COMPLETE")]


def has_plan(project_id: str) -> bool:
    return (project_dir(project_id) / "STORY_PLAN.json").is_file()


def mc_slot_path(segment_id: int) -> Path:
    """The pack's own slot naming, resolved against the 8197 output dir."""
    return (P.COMFY_OUTPUT / P.MC_SLOT_DIRNAME /
            (P.MC_CLIP_TEMPLATE % int(segment_id)))


def mc_slot_exists(segment_id: int) -> bool:
    return bool(segment_id) and mc_slot_path(segment_id).is_file()


def describe_output(project_id: str) -> dict:
    d = project_dir(project_id)
    out = {}
    for sub in SUBDIRS:
        p = d / sub
        out[sub] = len(list(p.glob("*"))) if p.is_dir() else 0
    return out
