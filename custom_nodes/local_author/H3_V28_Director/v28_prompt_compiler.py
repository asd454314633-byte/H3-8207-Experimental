"""V28 Director - deterministic H3 Ref2VA prompt compiler (task sections 15/17/18/35).

WHY THIS FILE EXISTS AT ALL
---------------------------
The story planner (an LLM) writes *content*. This module writes *structure*.
Task section 34 forbids feeding a natural-language reply straight to the
executor, and sections 15/17 require two properties that an LLM drifts on once
the clip count grows:

  15  GLOBAL_STATE holds the persistent facts; a segment carries only the new
      action of that segment - never a re-narrated copy of the whole story.
  17  SEG2+ opens with a "continuation airlock": ~1.5-2 s that continues the
      previous segment's pose / motion trend / rhythm / camera before the new
      action starts, and the first sentence must never demand an instant
      turn / stop / direction change / pose swap.

Both are enforced by construction here, not requested politely in a prompt.

PROMPT_RULE_SOURCE (task section 18)
------------------------------------
Structure, exact field names and the fixed marker vocabulary follow the MiniMax
H3 prompt-writing rules as collected in `lololerigolo60/Minimax-H3-prompt-studio`
(system_prompts.py / sequence_pipeline.py, fetched 2026-09-27, tarball SHA in
V28_BONSAI_RUNTIME_RECEIPT.txt). That repo ships NO LICENSE FILE, so
COPIED_CODE = NO: nothing from it is reproduced as source. What is reused is the
interoperability contract - the six literal section names and the label/marker
vocabulary that the model itself was trained on, restated here in independent
implementation, plus the "story is background context only" isolation idea.
See V28_PROMPT_COMPILER_RULES.md for the rule-by-rule derivation.
"""
from __future__ import annotations

import re
from typing import Any

from . import v28_schemas as S

# --- the literal, model-trained structure. Renaming these breaks H3. ------
SECTIONS = ("subject_definitions", "summary", "retention_analysis",
            "detailed_description", "overall_soundscape", "non_diegetic_music")

# summary: task-type vocabulary (fixed; combine with " + ", never repeat)
TASK_TYPES = ("keyframe completion", "reference generation", "video editing",
              "video continuation", "audio reuse", "audio reference")

# retention_analysis: markers (visible / audio are different sets)
VISIBLE_MARKERS = ("fully_preserved", "partially_preserved",
                   "attribute_transfer", "weak_reference")
AUDIO_MARKERS = ("fully_copy", "partially_copy", "reference", "weak_reference")

STYLE_WORDS = ("Cinematic", "live-action", "2D-animated", "3D CG",
               "claymation", "watercolor", "vintage film")

# Section 17's prohibition, as a machine check rather than a please.
INSTANT_CHANGE_TERMS = (
    # NOTE the \b before "abruptly": `\ab` is the BEL control character, so an
    # unescaped pattern here silently never matched and section 17's ban on
    # "abruptly" was inert (found by the 2026-09-27 static audit, case re-run
    # against the compiled SEG1 text).
    r"\bsuddenly\b", r"\binstantly\b", r"\babruptly\b", r"\bsnap(s|ping)?\b",
    r"\bspins?\b", r"\bwhips?\b", r"\bjerks?\b", r"\bstops?\s+dead\b",
    r"\bfreezes?\b", r"\bimmediately\s+(turn|stop|change|switch|leaps?)\b",
    r"\bwithout\s+(any\s+)?warning\b", r"\bmuscle\s*snap\b",
)
# Chinese equivalents, so a segment authored in Chinese is also caught.
INSTANT_CHANGE_CJK = ("突然", "瞬间", "猛然", "立刻转身", "立即转身", "急停", "硬切姿势", "一下子")

# Section 17's airlock window, in seconds, expressed as a ratio of the segment.
AIRLOCK_SECONDS = 1.75
AIRLOCK_MIN_SECONDS = 1.2
MAX_AIRLOCK_RATIO = 0.30

# Word budgets, taken from the H3 length rule (simple single-shot clip).
WORDS_SINGLE_SHOT = (150, 260)
WORDS_MULTI_SHOT = (300, 500)

# One cut needs ~3 s of room to establish anything; H3 does not do 4 cuts in 10 s.
SECONDS_PER_SHOT = 3.0
# comfy_extras/nodes_minimax_h3.py: `length` accepts up to 3600 frames, but the
# model card's trained range is ~124-362 frames, i.e. up to ~15 seconds.
H3_MAX_TRAINED_SECONDS = 15.0


class PromptRuleError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors[:8]))


# --------------------------------------------------------------------------
# small text helpers
# --------------------------------------------------------------------------
def _clean(s: Any, limit: int = 400) -> str:
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    return t[:limit].strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", _clean(text, 4000))
    return [p.strip() for p in parts if p.strip()]


def _join_bits(items, sep: str = ", ") -> str:
    out, seen = [], set()
    for it in items or []:
        v = _clean(it, 160)
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return sep.join(out)


def mmss(frames: int, fps: int = 24) -> str:
    """H3 timestamp format MM:SS.mmm from a frame index."""
    total_ms = int(round(frames * 1000.0 / fps))
    m, rem = divmod(total_ms, 60000)
    s, ms = divmod(rem, 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"


# --------------------------------------------------------------------------
# labels: <Picture N> / <Subject N>, numbered independently from 1 (section 18)
# --------------------------------------------------------------------------
def picture_labels(profile: dict) -> list[dict]:
    """Every picture the profile knows about, in <Picture N> order.

    `source_pictures` is the authoritative list; picture_refs are only used to
    attribute subjects. A picture nobody references still gets a definition
    line, because H3 must be told what an unconsumed reference means.
    """
    src = profile.get("source_pictures") or []
    out = []
    for i, p in enumerate(src, start=1):
        if not isinstance(p, dict):
            continue
        out.append({
            "index": int(p.get("index", i)),
            "filename": _clean(p.get("filename"), 120),
            "used_by": [],
        })
    # fall back to the union of referenced indices if source_pictures is thin
    if not out:
        idxs = set()
        for s in profile.get("subjects") or []:
            for r in (s.get("picture_refs") or []):
                try:
                    idxs.add(int(r))
                except (TypeError, ValueError):
                    pass
        out = [{"index": i, "filename": "", "used_by": []} for i in sorted(idxs)]
    return out


def _subject_phrase(s: dict) -> str:
    """What one picture is *for*, as seen-facts only (section 12)."""
    seen = s.get("seen") or {}
    ward = seen.get("wardrobe") or {}
    who = _clean(s.get("role"), 60) or "a subject of the video"
    look = _join_bits([
        _clean(seen.get("hair"), 90),
        _clean(seen.get("glasses")) and f"wearing {seen['glasses']}",
        _join_bits(seen.get("distinctive_appearance") or [], ", "),
    ], ", ")
    txt = f"the identity and wardrobe of {who}"
    if look:
        txt += f" ({look})"
    wp = _dict_phrase(ward)
    if wp:
        txt += f", wardrobe: {wp}"
    return txt


def _subject_definitions(plan: dict, profile: dict, pics: list[dict]) -> list[str]:
    """subject_definitions: - one anchored line per reference picture.

    DIALECT (fixed 2026-09-27): the reference label is <Picture N>, the family
    MiniMax H3 was trained on and the only family V27's H3VideoPromptRole
    understands (its Reference-Label machinery deletes or fail-closes on
    <Picture N>/<Audio N>/<Video N> lines; a tag it does not know passes
    through unvalidated). The earlier draft invented <Subject N> as a second,
    parallel label set and put <Picture N> *inside* those lines, which (a) asked
    H3 to bind an undefined label and (b) made every line mixed-enable, i.e. a
    fail-closed waiting to happen whenever N150 turned picture refs off.
    Content that has no picture anchor (scene, props, style) is written as a
    tagless continuity sentence, which V27 keeps verbatim.
    """
    subjects = profile.get("subjects") or []
    for s in subjects:
        for r in (s.get("picture_refs") or []):
            try:
                pi = int(r)
            except (TypeError, ValueError):
                continue
            for p in pics:
                if p["index"] == pi:
                    phrase = _subject_phrase(s)
                    if phrase not in p["used_by"]:
                        p["used_by"].append(phrase)
    lines: list[str] = []
    for p in pics:
        if p["used_by"]:
            lines.append(f"<Picture {p['index']}> defines {'; '.join(p['used_by'])}. "
                         f"Everything this picture defines stays unchanged for the whole "
                         f"video; it is a source of appearance, not a frame to copy.")
        else:
            lines.append(f"<Picture {p['index']}> is a visual reference only; it is not a "
                         f"frame anchor and no single frame must copy it exactly.")
    scene = _dict_phrase((profile.get("scene") or {}).get("seen") or {})
    props = _join_bits((profile.get("props") or []), ", ") \
        if isinstance(profile.get("props"), list) else _dict_phrase(profile.get("props") or {})
    bits = [x for x in (("environment: " + scene) if scene else "",
                        ("props: " + props) if props else "") if x]
    if bits:
        lines.append("The environment, layout, materials and lighting come from the "
                     "supplied references and stay continuous across every clip "
                     f"({'; '.join(bits)}).")
    return lines


def _dict_phrase(d: dict) -> str:
    bits = []
    for k, v in (d or {}).items():
        if isinstance(v, (list, tuple)):
            v = _join_bits(v, " / ")
        v = _clean(v, 90)
        if v:
            bits.append(f"{k} = {v}")
    return "; ".join(bits[:10])


# --------------------------------------------------------------------------
# the continuation airlock (section 17)
# --------------------------------------------------------------------------
def airlock_seconds(duration: float) -> float:
    return max(AIRLOCK_MIN_SECONDS,
               min(AIRLOCK_SECONDS, float(duration) * MAX_AIRLOCK_RATIO))


def build_airlock(prev_seg: dict, continuation_mode: str) -> str:
    """The opening sentence of every SEG2+. Built from the previous segment's
    end_state, which is *recorded fact*, not invention."""
    es = (prev_seg or {}).get("end_state") or {}
    body = _dict_phrase({k: es[k] for k in ("pose", "position", "facing", "hands",
                                             "motion", "speed") if es.get(k)})
    if not body:
        body = _dict_phrase(es)
    cam = _clean(((prev_seg or {}).get("directives") or {}).get("camera"), 40)
    tail = _clean((prev_seg or {}).get("end_state") or {}).replace("\n", " ")
    lead = ("The clip begins exactly where the previous one ends: the same framing, "
            "the same subjects in the same positions, holding "
            f"{body or 'the final pose of the previous clip'} and the same movement "
            f"trend{', ' + cam if cam else ''}. ")
    if continuation_mode == "natural_cut":
        lead += ("For the first moments the camera keeps that motion and rhythm, "
                 "then settles into this clip's new framing with a soft match cut. ")
    else:
        # Wording note: this sentence used to read "nothing changes abruptly",
        # i.e. the boilerplate itself contained a word section 17 bans - so the
        # instant-change scrubber, once its regex is fixed, would have rewritten
        # our own airlock into "nothing changes gradually" and inverted its
        # meaning. The continuation is therefore asserted positively.
        lead += ("For the first seconds the pose, the pace and the camera all keep "
                 "running on exactly as they were, before anything new begins. ")
    if tail:
        lead += ("The audio continues from the same room tone with no gap. ")
    return lead


def first_action_sentence(seg: dict) -> str:
    """The segment's own new action, as one observable English sentence."""
    beat = _clean(seg.get("beat"), 300)
    prompt = _clean(seg.get("prompt"), 3000)
    if prompt and not _looks_like_structured_prompt(prompt):
        return prompt if prompt.endswith((".", "!", "?")) else prompt + "."
    return beat if beat.endswith((".", "!", "?")) else (beat + ".") if beat else ""


_INSTANT_RE = re.compile("|".join(INSTANT_CHANGE_TERMS), re.I)


def strip_instant_change(text: str) -> tuple[str, list[str]]:
    """Neutralise an illegal instant-change opening. Returns (text, warnings)."""
    warns: list[str] = []
    out = text
    hits = [m.group(0) for m in _INSTANT_RE.finditer(text)]
    cjk = [w for w in INSTANT_CHANGE_CJK if w in text]
    if hits or cjk:
        warns.append(f"section 17: instant-change wording {hits + cjk} "
                     f"kept inside the airlock window")
        for bad in hits + cjk:
            out = out.replace(bad, "gradually")
    return out, warns


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------
def _looks_like_structured_prompt(text: str) -> bool:
    """Does this text already carry the six-section skeleton?

    Case-insensitive on purpose: a local model that echoes the headings as
    `Subject Definitions:` would otherwise slip through and get nested inside
    the compiler's own `detailed_description:` block, which H3 cannot parse.
    """
    low = (text or "").lower()
    return sum(1 for s in SECTIONS if f"{s.lower()}:" in low) >= 3


def looks_compiled(text: str) -> bool:
    """Public spelling of the same test, for callers outside this module.

    P11 TEST5-UI (BUG-6): the state machine needs to know whether an incoming
    【保存编辑】 payload is the card's own compiled envelope, because
    `first_action_sentence` will then fall back to the Chinese beat and the
    segment's English action line disappears. That must never be silent, so the
    check has to be reachable without reaching into a private name.
    """
    return _looks_like_structured_prompt(text)


def _destructure(text: str) -> tuple[str, bool]:
    """Recover from a model that wrote a whole prompt where only this segment's
    own action sentence belongs: keep its `detailed_description` body and let the
    compiler rebuild the rest. Returns (text, was_destructured)."""
    if not _looks_like_structured_prompt(text):
        return text, False
    body = (_block(text, "detailed_description") or "").strip()
    body = re.sub(r"^\[Shot\s*1\]\s*", "", body, flags=re.I)
    return (body or text), bool(body)


def compile_segment_prompt(plan: dict, segment_id: int, profile: dict,
                           prev_segment: dict | None = None) -> tuple[str, list[str]]:
    """Deterministically build the final H3 Ref2VA prompt for one segment.

    Returns (prompt, warnings). Never raises for a legal plan; raises
    PromptRuleError only if the inputs make an H3-legal prompt impossible.
    """
    segs = plan.get("segments") or []
    if not (1 <= int(segment_id) <= len(segs)):
        raise PromptRuleError([f"segment_id {segment_id} out of range 1..{len(segs)}"])
    seg = segs[int(segment_id) - 1]
    cont_mode = plan.get("continuation_mode") or "same_shot"
    g = plan.get("global_state") or {}
    warns: list[str] = []

    pics = picture_labels(profile)
    if not pics:
        raise PromptRuleError(
            ["the reference profile carries no <Picture N> anchor, so an H3 Ref2VA prompt "
             "cannot say what each supplied reference defines; refusing to compile a "
             "prompt that silently drops every reference"])
    subj_lines = _subject_definitions(plan, profile, pics)

    # ---- detailed_description -------------------------------------------
    style = _clean(g.get("visual_style") or plan.get("style") or "", 200)
    if not style or style.lower() in ("auto", "自动"):
        style = "Cinematic live-action, natural lighting, 24 fps, shallow depth of field"
    body: list[str] = [f"{style}. The scene keeps the exact identity, wardrobe and layout "
                       f"defined by the supplied references throughout."]

    is_first = int(segment_id) <= 1
    dur = float(seg.get("duration") or 10)
    if not (1.0 <= dur <= 60.0):
        raise PromptRuleError(
            [f"segment {segment_id} duration {dur}s is outside the 1..60s the schema allows; "
             f"compiling it would put cut timestamps beyond the real clip length"])
    if dur > H3_MAX_TRAINED_SECONDS:
        # comfy_extras/nodes_minimax_h3.py lets `length` run to 3600 frames, but the
        # card's trained range stops here; past it H3 is extrapolating, so say so.
        warns.append(f"section 16: {dur}s exceeds H3's ~{H3_MAX_TRAINED_SECONDS}s trained "
                     f"range; expect drift late in the clip")
    total_frames = _frames(dur)
    airlock = ""
    if not is_first and prev_segment:
        al = build_airlock(prev_segment, cont_mode)
        al, w = strip_instant_change(al)
        warns += w
        airlock = al
    action = _clean(first_action_sentence(seg), 2200)
    action, broke = _destructure(action)
    if broke:
        warns.append("structure: this segment's own text already contained the six H3 "
                     "sections; only its detailed_description was kept and the rest was "
                     "rebuilt here, so nothing is nested twice")
    action, w = strip_instant_change(action)
    if w and not is_first:
        # the action sentence is not the opener any more, so the airlock already
        # absorbs it - keep the notice but do not double-report.
        warns.append("section 17: soft-worded " + w[0])
    elif w:
        warns.extend(w)
    # ONE [Shot 1] per clip: the airlock is the opening of the first shot, not a
    # second shot. Emitting two `[Shot 1]` lines (airlock, then action) made every
    # SEG2+ prompt carry a duplicated shot marker, which H3 reads as two shots with
    # the same number and which the structural audit cannot count correctly.
    shot1 = (airlock + action).strip()
    if shot1:
        body.append(f"[Shot 1] {shot1}")
    else:
        warns.append("structure: this segment produced no action sentence; [Shot 1] is "
                     "empty, so the prompt will be refused by the structural audit")

    d = seg.get("directives") or {}
    body.append(_camera_sentence(d, plan, is_first, dur))
    body.append(_state_sentence(seg))
    shots = _extra_shots(seg, plan, cont_mode, dur, warns)
    body.extend(shots)
    body_text = "\n".join(x for x in body if x)

    # ---- summary ---------------------------------------------------------
    # Interaction limit (documented, not silently ignored): when N150's 参考视频
    # switch is ON, V27's H3VideoPromptRole rewrites the summary tag and only
    # accepts a bare `[reference generation]` / `[video editing]` there. A
    # multi-tag summary therefore fail-closes in Chinese inside V27. V28's story
    # director is reference-IMAGE driven (task 3), so video refs stay OFF; if a
    # future lane turns them on, this is the line to revisit.
    kinds = ["reference generation"]
    if not is_first:
        kinds.append("video continuation")
    used_pics = [p["index"] for p in pics if p["used_by"]]
    summ = (f"[{' + '.join(kinds)}] This clip continues the same {len(used_pics) or 'several'} "
            f"reference-defined subject(s) in the reference-defined environment and performs "
            f"only this clip's own new action; no event from any other clip is shown.")

    # ---- retention_analysis ---------------------------------------------
    # One line per reference picture, in the exact shape V27's own Ref2VA template
    # uses (`<Picture 1>: fully_preserved - preserve the target identity.`) - the
    # marker is what the structural audit reads, the reason is what H3 was trained
    # to expect after it.
    ret: list[str] = []
    for p in pics:
        if p["used_by"]:
            ret.append(f"<Picture {p['index']}>: fully_preserved - "
                       f"preserve the identity and wardrobe it defines")
        else:
            ret.append(f"<Picture {p['index']}>: weak_reference - "
                       f"guides appearance only, never copied as a whole frame")

    # ---- audio fields ----------------------------------------------------
    sound = _sound_sentence(plan, seg, g)
    music = _music_sentence(plan, seg, g)

    parts = [
        "subject_definitions:\n" + "\n".join(subj_lines),
        f"summary:\n{summ}",
        "retention_analysis:\n" + "\n".join(ret),
        "detailed_description:\n" + body_text,
        f"overall_soundscape:\n{sound}",
        f"non_diegetic_music:\n{music}",
    ]
    text = "\n\n".join(parts)

    # Language policy (task 35): beat / story_goal / start_state / end_state are
    # deliberately Chinese so the user can read and edit them, and they are
    # quoted verbatim into the state sentence and the airlock - that is the
    # author's contract, not a defect, and it is NOT reported. What IS reported is
    # Chinese inside the ACTION SENTENCE, the one line that must be English:
    # it means this segment had no `prompt` and the compiler fell back to the
    # Chinese `beat`. Dialogue in <d>[Chinese ...]</d> is verbatim by design, so
    # it is excluded before scanning.
    #
    # The window used to be `shot1`, i.e. airlock + action. That was wrong: the
    # airlock quotes the previous segment's end_state, and in the real chain
    # end_state is Chinese (§35 makes the plan display Chinese). So from SEG2 on
    # every legal plan reported "this segment had no English action sentence"
    # while its `prompt` was present and English - a false positive that also
    # said something factually untrue, on the most visible warning slot.
    # Scanning `action` alone is what the message actually describes.
    outside_dialogue = re.sub(r"<d>.*?</d>", " ", action, flags=re.S)
    cjk = sorted({c for c in outside_dialogue if "\u4e00" <= c <= "\u9fff"})
    if cjk:
        warns.append("language: this segment's action sentence carries Chinese, so it had "
                     "no English action (`prompt`) and the Chinese beat was used "
                     "instead - H3 reads it, but the action was never "
                     "written for the model")

    wc = len(re.findall(r"[A-Za-z0-9'\-]+", text))
    lo, hi = (WORDS_MULTI_SHOT if shots else WORDS_SINGLE_SHOT)
    if wc < lo:
        warns.append(f"length: {wc} words is under the {lo}-{hi} band for a "
                     f"{'multi' if shots else 'single'}-shot clip; H3 under-directs here")
    elif wc > hi + 220:
        warns.append(f"length: {wc} words far over the {lo}-{hi} band")
    return text, warns


def _frames(seconds: float) -> int:
    from . import v28_paths as P
    return P.seconds_to_frames(seconds)


def _camera_sentence(d: dict, plan: dict, is_first: bool, dur: float) -> str:
    """Camera motion written as natural prose with amplitude and speed (rule 18)."""
    cam = d.get("camera") or "hold"
    fram = d.get("framing") or "keep"
    pace = d.get("pace") or "steady"
    AMP = {"slow": "with small amplitude at slow speed",
           "steady": "with small amplitude",
           "brisk": "with large amplitude at fast speed"}
    MOVE = {"hold": "stays in a Static Shot", "pan_follow": "pans to follow the subject",
            "push_in": "pushes in toward the subject", "pull_back": "pulls out to widen the frame",
            "orbit": "arcs slowly around the subject", "handheld": "drifts with slight handheld shake"}
    phrase = AMP.get(pace, AMP["steady"])
    move = MOVE.get(cam, MOVE["hold"])
    fr = {"keep": "keeping the same framing as before", "wide": "in a wide frame",
          "medium": "in a medium frame", "close": "in a close frame"}.get(fram, "")
    lead = "The camera " if is_first else "The camera then "
    return f"{lead}{move} {phrase}, {fr}."


def _state_sentence(seg: dict) -> str:
    st = seg.get("start_state") or {}
    en = seg.get("end_state") or {}
    a = _dict_phrase({k: v for k, v in st.items() if k in
                      ("pose", "position", "facing", "hands", "carrying")})
    b = _dict_phrase({k: v for k, v in en.items() if k in
                      ("pose", "position", "facing", "hands", "carrying", "completed")})
    out = []
    if a:
        out.append(f"At the start the subject state is: {a}.")
    if b:
        out.append(f"By the end it must have reached: {b}.")
    return " ".join(out)


def _extra_shots(seg: dict, plan: dict, cont_mode: str, dur: float,
                 warns: list[str]) -> list[str]:
    """A second [Shot 2] only when the plan explicitly cuts and there is room."""
    join = (seg.get("directives") or {}).get("join") or "continuous"
    if cont_mode != "natural_cut" or join not in ("hard_cut", "match_cut"):
        return []
    if dur < 2 * SECONDS_PER_SHOT:
        warns.append(f"section 16: {dur}s cannot hold a cut (~{SECONDS_PER_SHOT}s per shot); "
                     f"kept it single-shot")
        return []
    cut_at = max(SECONDS_PER_SHOT, round(dur * 0.55, 2))
    cut_frames = _frames(cut_at)
    tail = _clean(seg.get("beat"), 300)
    return [f"[Shot 2] At {mmss(cut_frames)}, the camera cuts to a new viewpoint of the "
            f"same subject and continues {tail}"]


def _sound_sentence(plan: dict, seg: dict, g: dict) -> str:
    s = seg.get("soundscape") if isinstance(seg.get("soundscape"), str) else None
    if not s:
        s = (g.get("soundscape") or "")
    if not s:
        # This used to read
        #     refs.scene_phrase or g.scene.location if isinstance(g.scene, dict) else ""
        # which Python parses as `(a or b) if cond else ""`: the isinstance guard on
        # the SECOND candidate decided whether the FIRST one was used at all. Since
        # the plan shape the director prompts ask for carries `global_state.scene` as
        # a plain string, the condition was False and the tier collapsed to "" even
        # when references.scene_phrase was present - so the documented
        # "derived from scene_phrase" soundscape never appeared, and every clip got
        # the generic fallback line instead. Parenthesised per candidate now.
        refs = plan.get("references") or {}
        scene = g.get("scene")
        env = (refs.get("scene_phrase")
               or (scene.get("location") if isinstance(scene, dict) else ""))
        s = _clean(env, 120) and f"Continuous room tone of {_clean(env, 120).lower()}, " \
                                 f"with the physical sounds of the described actions."
    if not s:
        s = "Room tone matching the reference environment, plus the physical sounds of " \
            "the described actions and the subject's breathing."
    return _clean(s, 600)


def _music_sentence(plan: dict, seg: dict, g: dict) -> str:
    m = seg.get("music") if isinstance(seg.get("music"), str) else None
    m = m or (g.get("non_diegetic_music") or "")
    if not m:
        return "N/A"
    return _clean(m, 500)


# --------------------------------------------------------------------------
# structural gate - used on anything an LLM produced, and on our own output
# --------------------------------------------------------------------------
def audit_prompt(text: str, *, shots_expected: int = 1) -> list[str]:
    """Return a list of structural violations (empty == this may be submitted)."""
    e: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["prompt is empty"]
    low = text.lower()
    order = [s for s in SECTIONS if f"{s.lower()}:" in low]
    missing = [s for s in SECTIONS if f"{s.lower()}:" not in low]
    if missing:
        e.append(f"missing H3 sections: {missing}")
    # case-insensitive on purpose: H3 was trained on the literal lowercase names,
    # and a model that echoes "Subject Definitions:" must be caught, not passed.
    idx = [low.find(f"{s.lower()}:") for s in order]
    if idx != sorted(idx):
        e.append("sections out of the required order")
    if not re.search(r"^\s*\[?(?:keyframe completion|reference generation|video editing|"
                     r"video continuation|audio reuse|audio reference)\b",
                     _after(text, "summary:"), re.I | re.M):
        e.append("summary: must open with a task-type bracket from the fixed vocabulary")
    for ln in _block(text, "retention_analysis").splitlines():
        if not ln.strip():
            continue
        m = re.search(r":\s*(\w+)\b", ln)
        if not m or m.group(1) not in VISIBLE_MARKERS + AUDIO_MARKERS:
            e.append(f"retention_analysis line has no legal marker: {ln[:70]!r}")
    dd = _block(text, "detailed_description")
    if "[Shot 1]" not in dd:
        e.append("detailed_description must contain [Shot 1]")
    # One clip, one opening shot. A hand-edited or LLM-written body that repeats
    # `[Shot 1]` reads to H3 as two shots carrying the same number - the failure
    # the airlock fold (§14/§17) exists to prevent, so the gate has to keep
    # enforcing it after the compiler stopped producing it.
    dup = len(re.findall(r"\[Shot 1\]", dd))
    if dup > 1:
        e.append(f"[Shot 1] appears {dup} times; one clip opens with exactly one "
                 f"untimestamped [Shot 1], later shots are [Shot 2] and up")
    if re.search(r"\[Shot 1\][^\n]*At \d\d:", dd):
        e.append("[Shot 1] must never carry a timestamp")
    stamps = re.findall(r"\[Shot (\d+)\] At (\d\d:\d\d\.\d\d\d)", dd)
    if len(stamps) + 1 < int(shots_expected or 1):
        e.append(f"expected {shots_expected} shot(s), found {len(stamps) + 1}")
    prev = None
    for _, ts in stamps:
        secs = _ts_seconds(ts)
        if prev is not None and secs <= prev:
            e.append(f"shot timestamps must strictly increase ({ts})")
        prev = secs
    if re.search(r"push in, small amplitude|pan left, slow", text, re.I):
        e.append("camera motion written as trailing tags instead of prose")
    for bad in _INSTANT_RE.finditer(_block(text, "detailed_description")):
        e.append(f"section 17 violation: {bad.group(0)!r} inside the clip body")
    opened = len(re.findall(r"<d>", text))
    closed = len(re.findall(r"</d>", text))
    if opened != closed:
        # A mid-text `</d>` that never arrived used to slip through: the old
        # check only looked at the very end of the prompt.
        e.append(f"unbalanced <d> dialogue blocks: {opened} opened, {closed} closed")
    else:
        # `not re.search(r"<d>\s*\[", text)` would pass a two-line dialogue as long
        # as ONE of them carried a tag, which is not what the marker means: the
        # language tag tells H3 which voice to use for THAT line, so an untagged
        # block in a valid-looking prompt still gets sung in the wrong language.
        for n, blk in enumerate(re.findall(r"<d>(.*?)</d>", text, re.S), start=1):
            if not re.match(r"\s*\[[^\]]+\]", blk):
                e.append(f"every <d> block needs a [Language] tag right after it "
                         f"(block {n} of {opened}: {blk.strip()[:40]!r})")
    return e


def _after(text: str, key: str) -> str:
    i = text.find(key)
    return text[i + len(key):] if i != -1 else ""


def _block(text: str, key: str) -> str:
    body = _after(text, key)
    # The heading is `name:` on its own line, and callers pass the bare name
    # ("retention_analysis"). Without dropping that colon the first "line" of
    # every block was ":" - which made audit_report flag every legal prompt, and
    # made _destructure keep a stray ":" at the head of the recovered body.
    if body.startswith(":"):
        body = body[1:]
    ends = [body.find(f"\n{s}:") for s in SECTIONS if s != key.split(":")[0]]
    ends = [x for x in ends if x != -1]
    return body[:min(ends)] if ends else body


def _ts_seconds(ts: str) -> float:
    m = re.match(r"(\d+):(\d+)\.(\d+)", ts)
    if not m:
        return -1.0
    mm, ss, ms = m.groups()
    return int(mm) * 60 + int(ss) + int(ms) / 1000.0


# --------------------------------------------------------------------------
# plan-level advisories (section 16: per-segment action load must be executable)
# --------------------------------------------------------------------------
def audit_plan_load(plan: dict) -> list[str]:
    out: list[str] = []
    for s in plan.get("segments") or []:
        beat = _clean(s.get("beat"), 400)
        dur = float(s.get("duration") or 10)
        verbs = len(re.findall(r"[\u4e00-\u9fff](?:起|走|拿|坐|站|开|关|穿|脱|打|跑|跳|转身|"
                               r"上车|下车|进门|出门)|\b(?:walks?|opens?|closes?|sits?|stands?|"
                               r"picks? up|puts? on|takes? off|drives?|enters?|exits?)\b",
                               beat, re.I))
        if verbs >= 4:
            out.append(f"segment {s.get('id')}: {verbs} distinct actions in {dur}s - "
                       f"section 16 allows ~1 main + 1 transition")
        if dur < 5:
            out.append(f"segment {s.get('id')}: {dur}s is below the 5s useful minimum")
    return out
