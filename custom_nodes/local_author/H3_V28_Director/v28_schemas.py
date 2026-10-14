"""V28 Director - the three authoritative JSON schemas and their validator.

Schema policy borrowed from a mature shot-plan implementation (MIT, github.com/
dntpi/ComfyUI-Hand-Tie-Clips): a strict key whitelist where an unknown key is a
hard error, only `beat` is required inside a segment, and the segment count is
DERIVED from the array length so a second counter can never drift.

Task section 14: SHOT COUNT must equal SEGMENT COUNT. There is exactly one
number here (`segments` length) and everything else reads it.
"""
from __future__ import annotations

import copy
import json
from typing import Any

SCHEMA_VERSION = 1

# --- LAYER 1a: what the vision model saw -------------------------------
# Task section 11/12: seen facts and inferences must live in separate places,
# and the vision model must not invent motion, hidden anatomy or plot intent.
REFERENCE_PROFILE_SCHEMA: dict[str, Any] = {
    "version": int,
    "source_pictures": list,          # [{index, filename, width, height}]
    "subjects": [
        {
            "id": str,
            "picture_refs": list,     # 1-based <Picture N> indices
            "role": str,              # label only; NOT a claim about plot
            "seen": {                 # visible facts only
                "hair": str, "glasses": str, "wardrobe": dict,
                "distinctive_appearance": list, "visible_pose": dict,
            },
            "inferred": dict,         # explicitly quarantined
            "do_not_infer": list,
        }
    ],
    "scene": {"seen": dict, "inferred": dict},
    "props": list,
    "composition": {"seen": dict, "inferred": dict},
    "uncertain": list,
    "not_answerable": list,           # things we deliberately refused to guess
}

PROFILE_FORBIDDEN_TOPICS = (
    "future_motion", "hidden_anatomy", "plot_intent", "off_frame_geometry",
)

# Top-level value types, READ OFF the schema above instead of restated, so the
# validator and the documented schema cannot drift apart.
#
# Why this is enforced here rather than tolerated downstream: the reference profile
# is a vision model's reply, and its consumers index into it -
# v28_prompt_compiler.py does `(profile.get("scene") or {}).get("seen")` and
# retired_prompt_layer.py does the same when it builds the repair feedback. A
# `"scene": "夜晚的街道"` (a string, which a lazy model absolutely writes) therefore
# passed validation at the boundary and blew up with a bare AttributeError inside
# the compiler several steps later, where §34's repair loop can no longer quote a
# path. Checking the shape where the JSON arrives is what turns that crash into a
# repairable `$.scene: must be object` and keeps the project state intact.
PROFILE_TYPES: dict[str, type] = {
    k: (t if isinstance(t, type) else (dict if isinstance(t, dict) else list))
    for k, t in REFERENCE_PROFILE_SCHEMA.items()
}

# --- LAYER 1b: the director's plan (single source of truth) ------------
DIRECTIVE_AXES: dict[str, tuple[str, ...]] = {
    # join = how this segment attaches to the previous one
    "join": ("continuous", "match_cut", "hard_cut"),
    "camera": ("hold", "pan_follow", "push_in", "pull_back", "orbit", "handheld"),
    "framing": ("keep", "wide", "medium", "close"),
    "pace": ("slow", "steady", "brisk"),
    # tail is the only axis with a default: it stops the last seconds from
    # drifting toward the reference image.
    "tail": ("ongoing", "settle", "hold"),
}
TAIL_DEFAULT = "ongoing"
SEGMENT_KEYS = frozenset({
    "id", "segment", "segment_index", "start_time", "end_time", "duration_sec",
    "beat", "start_state", "end_state", "directives", "prompt",
    "duration", "seed", "locked",
    # The per-segment prompt lane (retired_prompt_layer.compile_user) is asked to
    # return these two alongside `prompt`, and the compiler reads them from the
    # segment. They are plan-time story content (a persistent fact, task 15), so
    # they belong in the plan. Derived data - e.g. compile warnings - must NOT be
    # added here: it is recomputed, and §14 forbids a second source of truth.
    "soundscape", "music", "reference_usage", "dialogue", "dialogue_timing",
    "ambience", "physical_sounds", "non_verbal_vocals", "new_action",
    "segment_objective", "beats", "performance", "blocking", "interaction",
    "camera", "continuity_out", "user_display_zh",
    "body_state_start", "body_state_end", "micro_timeline",
    "physical_conflicts", "conflict_resolution", "physical_continuity_notes",
    "anatomy_camera_notes", "render_risk", "planning_advisories",
    "detailed_description_edit",
})
PROFILE_KEYS = frozenset({"version", "source_pictures", "subjects", "scene",
                          "props", "composition", "uncertain", "not_answerable",
                          "director_input"})
PLAN_KEYS = frozenset({"version", "story_goal", "global_state", "references",
                       "segments", "style", "continuation_mode", "director",
                       "generated_from", "warnings"})
STATUS_VALUES = ("PLANNED", "READY", "GENERATING", "CANDIDATE_READY",
                 "ACCEPTED", "RETRY_PENDING", "COMPLETE", "ERROR")

CONTINUATION_MODES = ("same_shot", "natural_cut")


class SchemaError(Exception):
    """Raised with a machine-readable path list so the repair loop can quote it."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors[:12]))


def _req(cond: bool, where: str, msg: str, sink: list[str]) -> None:
    if not cond:
        sink.append(f"{where}: {msg}")


def validate_reference_profile(obj: Any) -> list[str]:
    e: list[str] = []
    if not isinstance(obj, dict):
        return ["root must be an object"]
    for k in ("subjects", "scene", "props", "composition", "uncertain"):
        _req(k in obj, f"$.{k}", "required key missing", e)
    for k in obj:
        _req(k in PROFILE_KEYS, f"$.{k}", f"unknown key (allowed: {sorted(PROFILE_KEYS)})", e)
    for k, want in PROFILE_TYPES.items():
        if k not in obj:
            continue                     # presence is the loop above
        v = obj[k]
        # bool is a subclass of int, and `version: true` is not a version number.
        ok = isinstance(v, want) and not (want is int and isinstance(v, bool))
        _req(ok, f"$.{k}",
             f"must be {want.__name__} (got {type(v).__name__}: {str(v)[:60]!r})", e)
    for i, s in enumerate(obj.get("subjects") or []):
        w = f"$.subjects[{i}]"
        if not isinstance(s, dict):
            _req(False, w, "must be an object", e)
            continue
        _req(isinstance(s.get("id"), str) and s["id"], f"{w}.id", "non-empty string required", e)
        _req(isinstance(s.get("picture_refs"), list), f"{w}.picture_refs", "array required", e)
        # Task 12: seen vs inferred must be separable, so a bare fact bag is invalid.
        _req(isinstance(s.get("seen"), dict), f"{w}.seen", "object of visible facts required", e)
        if "stable_identity" in s and "seen" not in s:
            _req(False, w, "facts must live under .seen, not at top level", e)
        _req(isinstance(s.get("do_not_infer"), list), f"{w}.do_not_infer",
             "array required (state what the picture cannot tell you)", e)
    if not (obj.get("subjects") or obj.get("scene")):
        _req(False, "$", "profile describes nothing", e)
    return e


def validate_story_plan(obj: Any) -> list[str]:
    e: list[str] = []
    if not isinstance(obj, dict):
        return ["root must be an object"]
    for k in ("version", "story_goal", "global_state", "segments"):
        _req(k in obj, f"$.{k}", "required key missing", e)
    for k in obj:
        _req(k in PLAN_KEYS, f"$.{k}", f"unknown key (allowed: {sorted(PLAN_KEYS)})", e)
    segs = obj.get("segments")
    if not isinstance(segs, list) or not segs:
        _req(False, "$.segments", "non-empty array required", e)
        return e
    for i, s in enumerate(segs):
        w = f"$.segments[{i}]"
        if not isinstance(s, dict):
            _req(False, w, "must be an object", e)
            continue
        _req(isinstance(s.get("beat"), str) and s["beat"].strip(),
             f"{w}.beat", "required (only `beat` is mandatory)", e)
        for k in s:
            _req(k in SEGMENT_KEYS, f"{w}.{k}",
                 f"unknown key (allowed: {sorted(SEGMENT_KEYS)})", e)
        _req(s.get("id") == i + 1, f"{w}.id",
             f"must equal index+1 (got {s.get('id')!r}); ids are positional", e)
        d = s.get("directives") or {}
        if not isinstance(d, dict):
            _req(False, f"{w}.directives", "object required", e)
        else:
            for axis, val in d.items():
                if axis not in DIRECTIVE_AXES:
                    _req(False, f"{w}.directives.{axis}",
                         f"unknown axis (allowed: {sorted(DIRECTIVE_AXES)})", e)
                elif val not in DIRECTIVE_AXES[axis]:
                    _req(False, f"{w}.directives.{axis}",
                         f"{val!r} not in {DIRECTIVE_AXES[axis]}", e)
        _req(isinstance(s.get("duration"), (int, float)) and 1 <= s["duration"] <= 60,
             f"{w}.duration", "seconds as a number 1..60", e)
        if s.get("seed") is not None:
            _req(isinstance(s["seed"], int) and not isinstance(s["seed"], bool),
                 f"{w}.seed", "int or null", e)
        if s.get("locked") is not None:
            # `locked` is the freeze flag §27 relies on: replanning and
            # 【从当前段重新规划后续】 both refuse to touch a segment whose locked is
            # truthy. A string "false" is truthy in Python, so a loose value here
            # would silently lock a segment the user never accepted - the exact
            # opposite of the rule, and invisible in the UI.
            _req(isinstance(s["locked"], bool), f"{w}.locked",
                 "boolean or null (it gates replanning; a string would be truthy)", e)
        for txt in ("prompt", "soundscape", "music"):
            v = s.get(txt)
            if v is not None:
                _req(isinstance(v, str), f"{w}.{txt}",
                     "English string (or omit it); the compiler never reads a dict here", e)
        for st in ("start_state", "end_state"):
            _req(isinstance(s.get(st, {}), dict), f"{w}.{st}", "object required", e)
    ids = [s.get("id") for s in segs if isinstance(s, dict)]
    _req(ids == list(range(1, len(segs) + 1)), "$.segments",
         f"ids must be 1..N with no gaps (got {ids})", e)
    beats = [str(s.get("beat", "")).strip() for s in segs]
    dupe = {b for b in beats if b and beats.count(b) > 1}
    if dupe:
        _req(False, "$.segments", f"identical beats are a plan failure: {sorted(dupe)[:3]}", e)
    return e


def validate_session_state(obj: Any) -> list[str]:
    e: list[str] = []
    if not isinstance(obj, dict):
        return ["root must be an object"]
    for k in ("project_id", "status", "current_segment",
              "last_accepted_segment", "current_candidate"):
        _req(k in obj, f"$.{k}", "required key missing", e)
    st = obj.get("status")
    _req(st in STATUS_VALUES, "$.status",
         f"{st!r} not an explicit state (allowed: {STATUS_VALUES})", e)
    for k in ("current_segment", "last_accepted_segment"):
        v = obj.get(k)
        _req(isinstance(v, int) and not isinstance(v, bool) and v >= 0,
             f"$.{k}", "int >= 0 required (0 means none)", e)
    n = obj.get("segment_count")
    if n is not None:
        _req(isinstance(n, int) and not isinstance(n, bool) and n >= 0,
             "$.segment_count", "int >= 0 required (0 = created, no plan yet)", e)
    cs = obj.get("current_segment")
    la = obj.get("last_accepted_segment")
    if isinstance(n, int) and isinstance(cs, int):
        if n == 0:
            _req(cs == 0, "$.current_segment",
                 f"{cs} with no plan: the cursor only exists once segments do", e)
        else:
            _req(cs <= n, "$.current_segment", f"{cs} exceeds segment_count {n}", e)
    if isinstance(cs, int) and isinstance(la, int):
        # The real law is "the continuity pointer never sits ahead of the cursor".
        # `la < cs` was wrong in both directions it mattered: it rejected a fresh
        # project (0 < 0 false) and - far worse - the FINAL accept, whose cursor
        # clamps to n while la becomes n, so a story could never reach COMPLETE.
        _req(la <= cs, "$.last_accepted_segment",
             f"accepted {la} cannot be ahead of the cursor {cs}", e)
        if st == "COMPLETE":
            _req(isinstance(n, int) and n >= 1 and la == n, "$.last_accepted_segment",
                 f"COMPLETE means every one of {n} segments was accepted (la={la})", e)
        elif isinstance(n, int) and n >= 1:
            _req(la < cs, "$.last_accepted_segment",
                 f"{st} still has work to do, so accepted {la} must sit behind the "
                 f"cursor {cs}", e)
    cand = obj.get("current_candidate")
    if cand is not None and not isinstance(cand, dict):
        _req(False, "$.current_candidate", "object or null", e)
    return e


VALIDATORS = {
    "reference_profile": validate_reference_profile,
    "story_plan": validate_story_plan,
    "session_state": validate_session_state,
}


def check(kind: str, obj: Any) -> None:
    errs = VALIDATORS[kind](obj)
    if errs:
        raise SchemaError(errs)


# --- normalisation the repair loop is allowed to apply automatically ----
def normalize_story_plan(obj: dict) -> dict:
    """Idempotent, lossless fixes only. Never invents story content."""
    out = copy.deepcopy(obj)
    if isinstance(out.get("shots"), list) and "segments" not in out:
        out["segments"] = out.pop("shots")   # single counter: shots == segments
    out.setdefault("version", SCHEMA_VERSION)
    out.setdefault("global_state", {})
    out.setdefault("references", {})
    segs = out.get("segments")
    if isinstance(segs, list):
        fixed = []
        for i, s in enumerate(segs):
            if isinstance(s, str):
                s = {"beat": s}                      # bare string == beat shorthand
            s = dict(s)
            s["id"] = i + 1                          # ids are positional, always
            d = dict(s.get("directives") or {})
            d.setdefault("tail", TAIL_DEFAULT)
            for axis in ("join", "camera", "framing", "pace"):
                d.pop(axis, None) if d.get(axis) in (None, "") else None
            s["directives"] = d
            s.setdefault("start_state", {})
            s.setdefault("end_state", {})
            s.setdefault("prompt", "")
            s.setdefault("duration", 10)
            s.setdefault("seed", None)
            s.setdefault("locked", False)
            fixed.append(s)
        out["segments"] = fixed
        # Task 14: the array length IS the count. Storing a second `segment_count`
        # here would both duplicate it and violate the top-level key whitelist
        # (PLAN_KEYS), so normalisation must not add it.
    return out


def extract_complete_object(text: str) -> dict:
    """Extract one complete object; never close brackets or salvage fragments."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response")
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in reply")
    obj, end = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    if "{" in text[start + end:]:
        raise ValueError("ambiguous multiple JSON objects")
    return obj


def extract_json(text: str) -> Any:
    """Pull one JSON value out of a model reply. Task 34: never feed prose to the
    executor. Tolerates ``` fences and a leading reasoning block, nothing else."""
    if text is None:
        raise ValueError("empty response")
    t = _strip_fences(text)
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object or array found in reply")
    i = min(starts)
    try:
        return json.loads(t[i:])
    except json.JSONDecodeError:
        pass
    # balance-scan the first complete value, bounded by the buffer length
    open_c, close_c = ("[", "]") if t[i] == "[" else ("{", "}")
    depth = in_str = esc = 0
    for j in range(i, len(t)):
        c = t[j]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == open_c:
                depth += 1
            elif c == close_c:
                depth -= 1
                if depth == 0:
                    return json.loads(t[i:j + 1])
    # local models routinely get cut off by max_tokens: salvage the complete part
    # instead of pretending the reply was unreadable (same failure mode the mature
    # H3 prompt tools work around; reimplemented here, not copied).
    salvaged = salvage_truncated(t[i:])
    if salvaged is not None:
        return salvaged
    raise ValueError("unterminated JSON in reply")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
    return t


def salvage_truncated(text: str) -> Any | None:
    """Close a reply that ran out of tokens: cut at the last complete element,
    drop the dangling fragment, re-balance the open brackets. Returns None when
    nothing can be salvaged, so the caller still gets an honest error."""
    stack: list[str] = []
    in_str = esc = False
    last_comma = 0            # last top-level-ish separator, the fallback cut
    last_close = 0            # position just after the last completed container
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            if stack:                     # a container that is NOT the root ended
                last_close = i + 1        # -> everything before it is complete
            last_comma = i + 1
        elif ch == "," and stack:
            last_comma = i
    if not stack and not in_str:
        return None
    # Cut after the last COMPLETE element whenever there is one. The old code cut
    # at the last comma, which kept a half-written `{"id": 2, "beat": "y"` and
    # then closed it - producing an element that passes json.loads but fails
    # validate_story_plan (`duration` is required), i.e. a salvage that invents a
    # malformed segment. Falling back to the comma is still right when the reply
    # died inside a scalar (`"style": "ci`).
    cut_at = last_close or last_comma
    head = text[:cut_at].rstrip().rstrip(",")
    # Closers must match the stack AT THE CUT, not at the end of the text: after
    # `{"segments":[{...}],` the text is deeper than the prefix, and appending the
    # end-of-text closers produced `{"segments":[{...]}]}` - unparsable.
    open_at_cut: list[str] = []
    s2 = e2 = False
    for ch in head:
        if s2:
            if e2:
                e2 = False
            elif ch == "\\":
                e2 = True
            elif ch == '"':
                s2 = False
            continue
        if ch == '"':
            s2 = True
        elif ch in "{[":
            open_at_cut.append(ch)
        elif ch in "}]":
            if open_at_cut:
                open_at_cut.pop()
    closers = {"{": "}", "[": "]"}
    head += "".join(closers[o] for o in reversed(open_at_cut))
    if not head.strip():
        return None
    try:
        return json.loads(head)
    except json.JSONDecodeError:
        return None
