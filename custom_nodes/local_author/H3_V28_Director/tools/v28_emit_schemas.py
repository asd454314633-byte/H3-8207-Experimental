"""V28 - machine-generates the three schema documents §45 asks for.

WHY THIS FILE EXISTS
--------------------
§45 lists V28_REFERENCE_ANALYSIS_SCHEMA.json / V28_STORY_PLAN_SCHEMA.json /
V28_SESSION_STATE_SCHEMA.json as deliverables, while `v28_schemas.py` is the one
runtime authority. A hand-typed copy of a schema is a second source of truth that
drifts the first time someone edits the validator - and a drifting schema document
is worse than none, because people trust documents.

So nothing here is typed from memory. Every key list, enum and default is read out
of the module at run time:

  * allowed keys        <- S.PROFILE_KEYS / S.PLAN_KEYS / S.SEGMENT_KEYS
  * required keys       <- parsed out of the validators' own source with `ast`
  * enums               <- S.DIRECTIVE_AXES / S.STATUS_VALUES / S.CONTINUATION_MODES
  * defaults            <- S.TAIL_DEFAULT / S.SCHEMA_VERSION, and normalize_*()
  * the shape of REFERENCE_PROFILE is converted from S.REFERENCE_PROFILE_SCHEMA
    (python types -> JSON Schema types)

and every rule the document states is then *executed against the real validator*
as a probe: we feed the mutation, and we record the error string the validator
actually produced. A rule that the validator does not enforce is written down as
`NOT_REJECTED` - the document reports the gap instead of pretending it away.

Run it:  python tools/v28_emit_schemas.py            (writes the three files)
It exits non-zero if a probe fails to reject what the document claims is rejected,
so regeneration is itself a gate, not a favour.

test_v28_schemas.py re-runs build_all() and compares against the shipped files, so
the documents cannot silently fall behind the code.
"""
from __future__ import annotations

import ast
import copy
import datetime as _dt
import hashlib
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parent.parent
OUT_NAMES = {
    "reference_profile": "V28_REFERENCE_ANALYSIS_SCHEMA.json",
    "story_plan": "V28_STORY_PLAN_SCHEMA.json",
    "session_state": "V28_SESSION_STATE_SCHEMA.json",
}
TITLES = {
    "reference_profile": "V28 参考图分析结果（代码内名 reference_profile）",
    "story_plan": "V28 剧情计划（代码内名 story_plan，唯一事实源）",
    "session_state": "V28 会话/项目状态（代码内名 session_state）",
}


def load_pkg(name: str = "_h3v28_docgen") -> types.ModuleType:
    """Import the package without running ComfyUI-facing __init__.

    The modules use `from . import ...`, so they need a parent with __path__;
    importing H3_V28_Director directly would pull in PromptServer routing.
    """
    if name in sys.modules:
        return sys.modules[name]
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(PKG)]
    sys.modules[name] = pkg
    importlib.import_module(f"{name}.v28_paths")
    return pkg


PY2JSON = {int: "integer", float: "number", str: "string", bool: "boolean",
           list: "array", dict: "object", type(None): "null"}


def _js(t: Any) -> Any:
    """Convert a node of S.REFERENCE_PROFILE_SCHEMA into JSON Schema."""
    if isinstance(t, type):
        return {"type": PY2JSON.get(t, "object")}
    if isinstance(t, dict):
        return {"type": "object",
                "properties": {k: _js(v) for k, v in t.items()},
                "additionalProperties": False}
    if isinstance(t, list):                      # [example_element] == typed array
        if not t:
            return {"type": "array"}
        return {"type": "array", "items": _js(t[0])}
    return {"type": "object"}


def derive_required(S, fn_name: str) -> tuple[list[str], int]:
    """Read the required-key tuple out of the validator's own body.

    `validate_*` states its requirements as `for k in ("a", "b"): _req(k in obj,
    ...)`, so the list is recoverable from the AST without re-typing it. If the
    shape ever changes, this raises and generation fails loudly - which is the
    correct outcome: the document would otherwise start lying.
    """
    src = (PKG / "v28_schemas.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    for node in ast.walk(fn):
        if not (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == "k" and isinstance(node.iter, ast.Tuple)
                and node.iter.elts):
            continue
        try:
            keys = [ast.literal_eval(e) for e in node.iter.elts]
        except (ValueError, TypeError, SyntaxError):
            continue
        if not keys or not all(isinstance(x, str) for x in keys):
            continue
        if "k in obj" in ast.unparse(node):
            return keys, node.lineno
    raise AssertionError(f"{fn_name}: required-key tuple not found - update derive_required()")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(validate, mut, expects_path: str, expect: str = "REJECTED",
 why: str = "") -> dict:
    """Run one mutation against the REAL validator and check it behaves as documented.

    `expect` makes the GAPS auditable too. A rule the validator provably does not
    enforce is still worth writing down - but then the document must say so, and the
    probe that says so has to pass as well: we assert NOT_REJECTED. If someone later
    closes the hole, this probe starts failing and the document has to be regenerated
    - which is exactly when the text should change. A gap that quietly becomes a
    rule is the same bug as a rule that quietly becomes a gap.
    """
    try:
        errs = validate(mut)
    except Exception as exc:                      # a raising validator is a finding too
        return {"rule": expects_path, "expect": expect, "why": why,
                "probe_status": "VALIDATOR_RAISED",
                "observed_error": f"{type(exc).__name__}: {exc}"}
    hit = [e for e in errs if e.startswith(expects_path)]
    got = "REJECTED" if hit else ("REJECTED_ELSEWHERE" if errs else "NOT_REJECTED")
    return {"rule": expects_path, "expect": expect, "why": why, "probe_status": got,
            "observed_error": (hit[0][:220] if hit else ("; ".join(errs)[:220] if errs else None))}


def control(validate, obj, label: str) -> dict:
    """The shipped example must produce ZERO errors.

    Without this, a probe could look "REJECTED" simply because the example itself
    is invalid, and the document would be describing its own bug.
    """
    try:
        errs = validate(obj)
    except Exception as exc:
        return {"rule": label, "expect": "CONTROL_PASSES", "why": "example 本身必须合法",
                "probe_status": "VALIDATOR_RAISED",
                "observed_error": f"{type(exc).__name__}: {exc}"}
    return {"rule": label, "expect": "CONTROL_PASSES", "why": "example 本身必须合法",
            "probe_status": "CONTROL_PASSES" if not errs else "CONTROL_FAILS",
            "observed_error": ("; ".join(errs)[:220]) or None}


# ---------------------------------------------------------------------------
# examples. Each is built from what the code actually writes, then REQUIRED to
# pass the real validator before it can be emitted.
# ---------------------------------------------------------------------------
def example_profile(S) -> dict:
    return {
        "version": S.SCHEMA_VERSION,
        "source_pictures": [{"index": 1, "filename": "ref_01.png",
                             "width": 1024, "height": 1024}],
        "subjects": [{
            "id": "person_a",
            "picture_refs": [1],
            "role": "主角",
            "seen": {"hair": "黑色短发", "glasses": "无",
                     "wardrobe": {"outerwear": "深色长外套"},
                     "distinctive_appearance": ["左手戴金属腕表"],
                     "visible_pose": {"body": "站立", "facing": "四分之三侧向镜头"}},
            "inferred": {"age_range": "青年（推断，非画面事实）"},
            "do_not_infer": ["future_motion", "hidden_anatomy"],
        }],
        "scene": {"seen": {"location_type": "城市巷道", "lighting": "夜间人工光",
                           "weather": "地面湿", "time_of_day": "夜"},
                  "inferred": {"season": "冬（由湿面与衣着推断）"}},
        "props": [{"name": "长柄伞", "picture_refs": [1], "state_seen": "收拢、右手持有"}],
        "composition": {"seen": {"shot_size": "中景", "camera_height": "齐眼",
                                 "subject_position": "画面中央偏左"},
                        "inferred": {"lens_feel": "标准"}},
        "uncertain": ["腕表是否同一只手上存在遮挡"],
        "not_answerable": ["转身后的表情", "画框外的空间关系"],
    }


def example_plan(S) -> dict:
    def seg(i, beat, **kw):
        s = {"id": i, "beat": beat, "start_state": {}, "end_state": {},
             "directives": {"join": "continuous" if i == 1 else "match_cut",
                            "camera": "hold", "framing": "keep", "pace": "steady",
                            "tail": S.TAIL_DEFAULT},
             "prompt": "", "duration": 10, "seed": None, "locked": False,
             "soundscape": "", "music": ""}
        s.update(kw)
        return s
    return {
        "version": S.SCHEMA_VERSION,
        "story_goal": "主角在雨夜巷道里收伞、推门进屋",
        "global_state": {"location": "巷道到门口", "time_of_day": "夜",
                         "held_object": "长柄伞"},
        "references": {"picture_1": "ref_01.png"},
        "segments": [seg(1, "站在巷口收伞"), seg(2, "收好伞后走向门"),
                     seg(3, "推门进入，回身带上门")],
        "style": {"color": "冷调高对比", "motion_blur": "低"},
        "continuation_mode": list(S.CONTINUATION_MODES)[0],
        "director": {"provider": "bonsai_2", "model": "PQ2_0"},
        "generated_from": "reference_profile@1",
        "warnings": [],
    }


def example_state(S, SM) -> dict:
    """Mid-story state: seg1 accepted, seg2 generating -> the exact field set the
    state machine writes (blank_state + accept()'s last_accepted_context +
    mark_generating()'s current_candidate)."""
    st = SM.blank_state("20260927_101500_story", segment_count=3)
    st.update({
        "status": "GENERATING",
        "current_segment": 2,
        "last_accepted_segment": 1,
        "next_segment": 3,
        "attempt": 2,
        "plan_version": 1,
        "last_accepted_context": {"segment_id": 1,
                                  "slot": r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\output\h3_context\clip_00001.safetensors",
                                  "seed": 1234567, "at": st["updated_at"]},
        "accepted": [{"segment_id": 1,
                      "video": r"H3_V28\seg001_20260927_101500.mp4",
                      "seed": 1234567, "accepted_at": st["updated_at"]}],
        "current_candidate": {"generation_id": "g2", "segment_id": 2, "seed": 7654321,
                              "expected_frames": 239, "prompt_sha": "0" * 40,
                              "started_at": st["updated_at"], "video": None,
                              "audio_present": None, "state": "GENERATING"},
        "errors": [],
        "history": [{"at": st["updated_at"], "status": "READY",
                     "current_segment": 1, "last_accepted_segment": 0}],
    })
    return st


# ---------------------------------------------------------------------------
def _plan_probes(S) -> list[dict]:
    V, P = S.validate_story_plan, example_plan(S)
    return [
        probe(V, _drop(copy.deepcopy(P), "segments"), "$.segments", why="必填键缺失"),
        probe(V, _drop(copy.deepcopy(P), "story_goal"), "$.story_goal", why="必填键缺失"),
        probe(V, _drop(copy.deepcopy(P), "global_state"), "$.global_state", why="必填键缺失"),
        probe(V, _drop(copy.deepcopy(P), "version"), "$.version", why="必填键缺失"),
        probe(V, _add(copy.deepcopy(P), "shot_count", 3), "$.shot_count",
              why="§14 计数唯一：计划里不允许出现第二个段数计数器"),
        probe(V, _add(copy.deepcopy(P), "segment_count", 3), "$.segment_count",
              why="同上，且这个键名最容易顺手写出来"),
        probe(V, _set(copy.deepcopy(P), "segments", []), "$.segments", why="空计划不是计划"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 1, "id", 7), "$.segments[1].id",
              why="编号是位置的，不是模型自由发挥的"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 1, "beat", "站在巷口收伞"), "$.segments",
              why="重复 beat = 计划失败（两段其实是同一段）"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "beat", "  "), "$.segments[0].beat",
              why="beat 是唯一必填字段，空白视为缺失"),
        probe(V, _add_seg_key(copy.deepcopy(P), "compiled_warnings", []), "$.segments[0].compiled_warnings",
              why="派生数据禁止入计划（§14 单一事实源）"),
        probe(V, _set_directive(copy.deepcopy(P), "camera", "zoomies"),
              "$.segments[0].directives.camera", why="轴值必须是枚举"),
        probe(V, _set_directive(copy.deepcopy(P), "lens", "hold"),
              "$.segments[0].directives.lens", why="轴名也必须是枚举：自创轴会一路活着直到编译器"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "duration", 900),
              "$.segments[0].duration", why="时长上限挡住失控计划（§33 的图侧对应物）"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "duration", "10"),
              "$.segments[0].duration", why="字符串时长会在 V27 的 N132/N131 链上变成垃圾帧数"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "seed", True),
              "$.segments[0].seed", why="bool 不是种子"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "prompt", {"en": "x"}),
              "$.segments[0].prompt", why="编译器把 prompt 当字符串读，字典会静默变成空提示词"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "soundscape", {}),
              "$.segments[0].soundscape", why="同上"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "start_state", "门口"),
              "$.segments[0].start_state", why="状态袋必须是对象"),
        probe(V, _set_idx(copy.deepcopy(P), "segments", 0, "locked", "yes"),
              "$.segments[0].locked",
              why="§27 靠 locked 冻结已接受段；Python 里非空字符串恒真，字符串 false 会误锁"),
        probe(V, _set(copy.deepcopy(P), "style", 5), "$.style", expect="NOT_REJECTED",
              why="已知的宽松处：style/references/director/warnings 只查键名白名单，不查值类型。"
                  "它们是给下游看的元数据，写坏了不会让生成变错。"),
        probe(V, _set(copy.deepcopy(P), "continuation_mode", "cross_dissolve"),
              "$.continuation_mode", expect="NOT_REJECTED",
              why="已知的宽松处：CONTINUATION_MODES 由编译器/状态机解释，校验器不查值。"
                  "真正的守卫在 v28_h3_format 里，因此本文档不把枚举写成机器保证。"),
        control(V, copy.deepcopy(P), "CONTROL: 本文档的 example 必须零错误通过"),
        control(V, S.normalize_story_plan({"version": 1, "story_goal": "g", "global_state": {},
                                           "segments": [{"beat": "a"}, {"beat": "b"}]}),
                "CONTROL: 最小懒惰回复经 normalizer 后必须可通过校验"),
    ]


# ---------------------------------------------------------------------------
def _state_probes(S, SM, st_ex: dict) -> list[dict]:
    V = S.validate_session_state
    clone = lambda: copy.deepcopy(st_ex)          # noqa: E731 - probes must not share
    return [
        probe(V, _drop(clone(), "status"), "$.status", why="§20 禁止隐式状态：状态必须显式存在"),
        probe(V, _drop(clone(), "project_id"), "$.project_id", why="必填键缺失"),
        probe(V, _drop(clone(), "current_candidate"), "$.current_candidate", why="必填键缺失"),
        probe(V, _drop(clone(), "last_accepted_segment"), "$.last_accepted_segment",
              why="必填键缺失"),
        probe(V, _set(clone(), "status", "RUNNING"), "$.status",
              why="状态词表封闭：自创状态等于没有状态"),
        probe(V, _set(clone(), "current_segment", 9), "$.current_segment",
              why="游标不能越过计划长度"),
        probe(V, _set(clone(), "last_accepted_segment", 3), "$.last_accepted_segment",
              why="接续指针不能跑到游标前面——那会让下一段拿错 Motion Context"),
        probe(V, _set(clone(), "last_accepted_segment", "1"), "$.last_accepted_segment",
              why="字符串 1 在算术比较里会静默变脏"),
        probe(V, _multi(clone(), {"status": "COMPLETE", "current_segment": 3,
                                 "last_accepted_segment": 2}), "$.last_accepted_segment",
              why="COMPLETE 的定义是 n 段全部被接受"),
        probe(V, _multi(clone(), {"status": "COMPLETE", "current_segment": 3,
                                 "last_accepted_segment": 3}), "$.last_accepted_segment",
              expect="NOT_REJECTED",
              why="这条必须放行：最后一次接受把游标钳到 n 且 la==n，若按 la<cs 一刀切，"
                  "任何故事都永远到不了 COMPLETE（这是本校验器真正修过的错）"),
        probe(V, _multi(clone(), {"segment_count": 0, "current_segment": 1}), "$.current_segment",
              why="没有计划就没有游标"),
        probe(V, _set(clone(), "current_candidate", "g2"), "$.current_candidate",
              why="候选必须是对象或 null"),
        probe(V, _add(clone(), "curant_segment", 2), "$.curant_segment", expect="NOT_REJECTED",
              why="已知的宽松处：会话状态不查未知键。理由是状态字段会随版本增加、旧文件必须"
                  "能被新代码读；代价是拼错的键会静默存活，所以新增字段必须同时改 blank_state()。"
                  "这条取舍要人工知道，所以写进文档而不是偷偷收紧。"),
        probe(V, _multi(clone(), {"attempt": -5}), "$.attempt", expect="NOT_REJECTED",
              why="已知的宽松处：attempt/plan_version 未做下限检查（只影响显示，不影响转移）"),
        control(V, clone(), "CONTROL: 本文档的 example 必须零错误通过"),
        control(V, SM.blank_state("p", segment_count=0), "CONTROL: blank_state(0 段) 必须合法"),
        control(V, SM.blank_state("p", segment_count=4), "CONTROL: blank_state(4 段) 必须合法"),
    ]


# ---------------------------------------------------------------------------
def build(S, SM, stamp: str) -> dict[str, dict]:
    src_lines = (PKG / "v28_schemas.py").read_text(encoding="utf-8").splitlines()
    meta = {
        "generated_by": "custom_nodes/H3_V28_Director/tools/v28_emit_schemas.py",
        "generated_at_utc": stamp,
        "source_of_truth": "custom_nodes/H3_V28_Director/v28_schemas.py",
        "source_sha256": sha256(PKG / "v28_schemas.py"),
        "source_lines": len(src_lines),
        "authority": ("运行时判据以 v28_schemas.py 的 validate_*() 为准。本文档由该文件机械生成，"
                      "不是第二套规范：键名白名单、枚举、默认值全部从代码常量读出，"
                      "每条规则都通过对真实校验器做一次 mutation 探针来核实，"
                      "探针未被拒绝的规则会如实标成 NOT_REJECTED 而不是删掉不说。"),
    }

    # ---------- 1) reference analysis ----------
    req_p, req_p_line = derive_required(S, "validate_reference_profile")
    props_p = _js(S.REFERENCE_PROFILE_SCHEMA)
    V = S.validate_reference_profile
    probes = [
        probe(V, _drop(example_profile(S), "subjects"), "$.subjects",
              why="必填键缺失必须被拒"),
        probe(V, _drop(example_profile(S), "scene"), "$.scene", why="必填键缺失"),
        probe(V, _drop(example_profile(S), "props"), "$.props", why="必填键缺失"),
        probe(V, _drop(example_profile(S), "composition"), "$.composition", why="必填键缺失"),
        probe(V, _drop(example_profile(S), "uncertain"), "$.uncertain", why="必填键缺失"),
        probe(V, _set(example_profile(S), "version", True), "$.version",
              why="bool 不是版本号（bool 是 int 的子类，必须显式排除）"),
        probe(V, _set(example_profile(S), "composition", 5), "$.composition",
              why="顶层值类型受 S.PROFILE_TYPES 约束"),
        probe(V, _set(example_profile(S), "uncertain", "x"), "$.uncertain",
              why="字符串冒充数组必须在边界拦住，而不是让编译器炸 AttributeError"),
        probe(V, _set(example_profile(S), "props", 5), "$.props", why="同上"),
        probe(V, _set(example_profile(S), "scene", "夜晚的街道"), "$.scene",
              why="这是本 schema 最容易被偷懒写出的一种形状"),
        probe(V, _add(example_profile(S), "mood", "忧郁"), "$.mood",
              why="未知键是硬错误：否则模型自创字段会一路活着"),
        probe(V, _multi(example_profile(S), {"subjects": [], "scene": {}}), "$",
              why="subjects 与 scene 同时为空 = 什么都没描述"),
        probe(V, _set_in_seg(example_profile(S), ("subjects", 0), "seen", None),
              "$.subjects[0].seen", why="看到的事实必须放在 .seen 下（§11/§12）"),
        probe(V, _set_in_seg(example_profile(S), ("subjects", 0), "picture_refs", "1"),
              "$.subjects[0].picture_refs", why="<Picture N> 索引必须是数组"),
        probe(V, _set_in_seg(example_profile(S), ("subjects", 0), "id", ""),
              "$.subjects[0].id", why="主体 id 必须非空，否则无法跨段引用"),
        probe(V, _add_in_seg(example_profile(S), ("subjects", 0), "stable_identity", {}),
              "$.subjects[0].stable_identity", expect="NOT_REJECTED",
              why="已知的宽松处：主体级不查未知键。理由：这是视觉模型的回复，"
                  "逐键收紧会把可用产出变成修复循环空转；真正致命的 .seen 分离已经查了。"),
        probe(V, _set_in_seg(example_profile(S), ("subjects", 0), "inferred",
                             {"future_motion": "她接下来会奔跑"}),
              "$.subjects[0].inferred.future_motion", expect="NOT_REJECTED",
              why="已知的宽松处：forbidden_topics 是提示词层与人工复核约束，"
                  "校验器无法识别主题。不要把它当成机器保证。"),
        control(V, example_profile(S), "CONTROL: 本文档的 example 必须零错误通过"),
    ]
    out_ref = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": TITLES["reference_profile"],
        "x_v28": {**meta, "kind": "reference_profile",
                  "validator": "v28_schemas.validate_reference_profile",
                  "validator_def_line": _def_line(src_lines, "validate_reference_profile"),
                  "required_derived_from": f"v28_schemas.py:{req_p_line}",
                  "normalizer": None,
                  "example_passed_validation": not S.validate_reference_profile(example_profile(S))},
        "type": "object",
        "required": req_p,
        "properties": props_p["properties"],
        "additionalProperties": False,
        "x_v28_closed_world": {
            "allowed_keys": sorted(S.PROFILE_KEYS),
            "properties_match_allowed_keys": sorted(props_p["properties"]) == sorted(S.PROFILE_KEYS),
            "note": "未知键是硬错误：白名单直接读自 S.PROFILE_KEYS，不做人工转录。"},
        "x_v28_type_enforcement": {
            "table": {k: v.__name__ for k, v in sorted(S.PROFILE_TYPES.items())},
            "derived_from": "S.PROFILE_TYPES —— 由 REFERENCE_PROFILE_SCHEMA 推导，不是手抄",
            "bool_is_not_int": "version 显式排除 bool（isinstance(True, int) 为真）",
            "why_here": ("profile 的下游用 .get(...).get(...) 索引 scene/composition；"
                         "类型不在边界拦住就会在编译器里抛 AttributeError，"
                         "那时 §34 的修复回路已经无法给出 JSON 路径。")},
        "x_v28_seen_vs_inferred": {
            "rule": "看到的与推断的必须分开存放；裸的事实袋非法（§11/§12）。",
            "quarantined_keys": ["subjects[].inferred", "scene.inferred", "composition.inferred"],
            "forbidden_topics": list(S.PROFILE_FORBIDDEN_TOPICS),
            "enforced_by": "validate_reference_profile 的 $.subjects[i].seen 存在性检查 + "
                           "facts-must-live-under-.seen 检查。",
            "not_enforced": "forbidden_topics 属提示词层与人工复核约束：校验器只查形状，"
                            "不识别语义主题。见 probes 中标 NOT_REJECTED 的那条。"},
        "x_v28_probes": probes,
        "example": example_profile(S),
    }

    # ---------- 2) story plan ----------
    req_l, req_l_line = derive_required(S, "validate_story_plan")
    seg_props = {
        "id": {"type": "integer", "x_v28_rule": "必须等于数组下标+1（位置即编号，§14 不允许第二套计数）"},
        "beat": {"type": "string", "x_v28_rule": "唯一必填字段；全计划内不得重复"},
        "start_state": {"type": "object"}, "end_state": {"type": "object"},
        "directives": {"type": "object", "additionalProperties": False,
                       "properties": {a: {"type": "string", "enum": list(v)}
                                      for a, v in S.DIRECTIVE_AXES.items()},
                       "x_v28_defaults": {"tail": S.TAIL_DEFAULT,
                                          "note": "只有 tail 有默认值；其余轴缺失即缺失，不猜。"}},
        "prompt": {"type": "string",
                   "x_v28_rule": "英文 H3 提示词（§35 中英分层）；计划里的 prompt 只是占位，"
                                 "真正交付文本由 v28_h3_format 现算，绝不缓存进计划（§14）"},
        "duration": {"type": "number", "minimum": 1, "maximum": 60,
                     "x_v28_rule": "秒；帧数不由计划决定，走 V27 的 N131 表达式"},
        "seed": {"type": ["integer", "null"], "x_v28_rule": "整数或 null（null 表示未定，生成时才分配）"},
        "locked": {"type": "boolean",
                   "x_v28_rule": "已接受段被冻结，重规划不得覆盖（§27）；校验器强制 bool/null，"
                                 "因为 Python 里字符串 \"false\" 恒真，松散值会误锁用户没接受过的段"},
        "soundscape": {"type": "string"}, "music": {"type": "string"},
    }
    NC = "只查键名白名单，值类型不检查（见 documented_looseness）"
    plan_props = {
        "version": {"type": "integer", "x_v28_validator": "只查存在性"},
        "story_goal": {"type": "string", "x_v28_validator": "只查存在性"},
        "global_state": {"type": "object", "x_v28_validator": "只查存在性",
                         "x_v28_rule": "只放贯穿全片的事实（§15）；段内变化进 start_state/end_state"},
        "references": {"type": "object", "x_v28_validator": NC},
        "segments": {"type": "array", "minItems": 1,
                     "items": {"type": "object", "required": ["beat"],
                               "properties": seg_props,
                               "additionalProperties": False}},
        "style": {"type": ["string", "object"], "x_v28_validator": NC +
                  "；两种写法都出现在真实产出里（测试夹具给 \"auto\"，模型常给对象），"
                  "所以这里不假装它一定是 object"},
        "continuation_mode": {"type": "string", "enum": list(S.CONTINUATION_MODES),
                              "x_v28_validator": "枚举值由 v28_h3_format 与状态机解释，"
                                                 "校验器不查值（有探针为证）"},
        "director": {"type": "object", "x_v28_validator": NC},
        "generated_from": {"type": "string", "x_v28_validator": NC},
        "warnings": {"type": "array", "x_v28_validator": NC},
    }
    out_plan = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": TITLES["story_plan"],
        "x_v28": {**meta, "kind": "story_plan",
                  "validator": "v28_schemas.validate_story_plan",
                  "validator_def_line": _def_line(src_lines, "validate_story_plan"),
                  "required_derived_from": f"v28_schemas.py:{req_l_line}",
                  "normalizer": "v28_schemas.normalize_story_plan（幂等、无损；修复回路只允许这一组自动补全）",
                  "example_passed_validation": not S.validate_story_plan(example_plan(S))},
        "type": "object",
        "required": req_l,
        "properties": plan_props,
        "additionalProperties": False,
        "x_v28_closed_world": {
            "top_level_allowed": sorted(S.PLAN_KEYS),
            "segment_allowed": sorted(S.SEGMENT_KEYS),
            "properties_match_top_level": sorted(plan_props) == sorted(S.PLAN_KEYS),
            "properties_match_segment": sorted(seg_props) == sorted(S.SEGMENT_KEYS),
            "note": "两个白名单都读自代码 frozenset。派生数据（如编译告警）禁止入计划。"},
        "x_v28_shot_count_equals_segment_count": {
            "law": "§14：镜头数 == 段数。这里只有一个数字，就是 segments 的长度。",
            "consequences": [
                "normalize_story_plan 不得往计划里加 segment_count（会同时违反 PLAN_KEYS 白名单）",
                "模型写成 shots 时，normalizer 把它改名成 segments，绝不同时保留两者",
                "会话状态里的 segment_count 是派生值，由 len(plan['segments']) 计算"],
            "derivation_site": "v28_state_machine.apply_plan -> n = len(plan.get('segments') or [])"},
        "x_v28_normalization": _normalization_facts(S),
        "x_v28_probes": _plan_probes(S),
        "example": example_plan(S),
    }

    # ---------- 3) session state ----------
    req_s, req_s_line = derive_required(S, "validate_session_state")
    st_ex = example_state(S, SM)
    cand_props = {k: {"type": "string"} for k in
                  ("generation_id", "video", "prompt_sha", "started_at", "state")}
    out_state = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": TITLES["session_state"],
        "x_v28": {**meta, "kind": "session_state",
                  "validator": "v28_schemas.validate_session_state",
                  "validator_def_line": _def_line(src_lines, "validate_session_state"),
                  "required_derived_from": f"v28_schemas.py:{req_s_line}",
                  "normalizer": None,
                  "written_by": "v28_state_machine.save_state -> v28_project.write（原子写）",
                  "file_name": "SESSION_STATE.json",
                  "lives_outside_workflow_json": "§28：项目状态绝不进工作流 JSON",
                  "example_passed_validation": not S.validate_session_state(st_ex),
                  "example_builder": "v28_state_machine.blank_state() + 状态机各转移函数实际写入的字段"},
        "type": "object",
        "required": req_s,
        "properties": {
            "version": {"type": "integer", "const": S.SCHEMA_VERSION},
            "project_id": {"type": "string"},
            "status": {"type": "string", "enum": list(S.STATUS_VALUES)},
            "segment_count": {"type": "integer", "minimum": 0,
                              "x_v28_rule": "派生自 len(plan['segments'])；0 = 已建项目、还没有计划"},
            "current_segment": {"type": "integer", "minimum": 0,
                                "x_v28_rule": "游标；0 只在无计划时合法（§20 禁止隐式状态）"},
            "last_accepted_segment": {"type": "integer", "minimum": 0,
                                      "x_v28_rule": "接续指针：0 = 一段都没接受；必须 <= 游标"},
            "next_segment": {"type": ["integer", "null"]},
            "current_candidate": {"type": ["object", "null"],
                                  "properties": {**cand_props,
                                                 "segment_id": {"type": "integer"},
                                                 "seed": {"type": "integer"},
                                                 "expected_frames": {"type": "integer"},
                                                 "actual_delivered_frames": {"type": ["integer", "null"]},
                                                 "motion_context_load_index": {"type": "integer"},
                                                 "context_trim": {"type": ["integer", "null"]},
                                                 "context_note": {"type": ["string", "null"]},
                                                 "audio_present": {"type": ["boolean", "null"]},
                                                 "finished_at": {"type": "string"}}},
            "accepted": {"type": "array", "items": {"type": "object",
                                                    "properties": {"segment_id": {"type": "integer"},
                                                                   "video": {"type": "string"},
                                                                   "seed": {"type": "integer"},
                                                                   "accepted_at": {"type": "string"}}},
                         "x_v28_rule": "只增不删：§30 任何失败路径都不得删除已接受段"},
            "last_accepted_context": {"type": "object",
                                      "x_v28_rule": "accept() 第 2 步写入：Motion Context 存档路径"},
            "errors": {"type": "array", "x_v28_rule": "尾部截断保留最近 24 条"},
            "attempt": {"type": "integer", "minimum": 0},
            "plan_version": {"type": "integer", "minimum": 0},
            "updated_at": {"type": "string"},
            "history": {"type": "array", "x_v28_rule": "尾部截断保留最近 60 条状态轨迹"},
        },
        "additionalProperties": True,
        "x_v28_closed_world": {
            "allowed_keys": None,
            "note": ("会话状态没有键名白名单——校验器不拒绝未知键（与 plan/profile 不同，"
                     "见 probes：加未知键的结果是 NOT_REJECTED）。"
                     "理由：状态字段会随版本增加，旧文件必须能被新代码读；"
                     "代价是拼错的键会静默存活，因此新增字段必须同时改 blank_state()。"),
            "fields_written_by_code": sorted(st_ex)},
        "x_v28_state_laws": [
            {"law": "§21 生成成功 != 接受", "code": "mark_candidate -> CANDIDATE_READY；"
                                                    "只有 accept() 能写 ACCEPTED 相关字段"},
            {"law": "§24 接受绝不排队下一段", "code": "accept() 第 5 步只写日志，不 queue"},
            {"law": "COMPLETE 的定义", "code": "validate_session_state: COMPLETE 要求 la == segment_count >= 1"},
            {"law": "非 COMPLETE 时接续指针必须落后游标", "code": "la < cs，否则状态说自己还有事做"},
            {"law": "最后一次接受不会被自己判死", "code": "游标钳到 n 且 la == n 时仍合法（旧写法 la < cs 会拒绝 COMPLETE）"},
            {"law": "坏状态不落盘", "code": "save_state 先 check 再 write；SchemaError -> 记 errors + raise"},
            {"law": "种子可追溯", "code": "SEED_MAX = (1<<53)-1，保证 JSON->JS number->graphToPrompt 全程整值精确"},
        ],
        "x_v28_probes": _state_probes(S, SM, st_ex),
        "example": st_ex,
    }
    for k, v in (("reference_profile", out_ref), ("story_plan", out_plan),
                 ("session_state", out_state)):
        v["x_v28"]["out_name"] = OUT_NAMES[k]
        # What the validator provably does NOT check - written INTO the document,
        # and each entry is itself backed by a probe that had to come out
        # NOT_REJECTED. Leaving this only in the generator would let the file
        # overstate how much is machine-enforced.
        v["x_v28_documented_looseness"] = [
            {"rule": p["rule"], "why": p["why"]}
            for p in v["x_v28_probes"] if p["expect"] == "NOT_REJECTED"]
    return {"reference_profile": out_ref, "story_plan": out_plan, "session_state": out_state}


# --- tiny mutation helpers (each returns a NEW object) ---------------------
def _drop(o, k):
    c = copy.deepcopy(o); c.pop(k, None); return c


def _set(o, k, v):
    c = copy.deepcopy(o); c[k] = v; return c


def _add(o, k, v):
    c = copy.deepcopy(o); c[k] = v; return c


def _multi(o, kv):
    c = copy.deepcopy(o); c.update(kv); return c


def _set_idx(o, arr, i, k, v):
    c = copy.deepcopy(o); c[arr][i][k] = v; return c


def _set_in_seg(o, path, k, v):
    c = copy.deepcopy(o)
    cur = c
    for p in path:
        cur = cur[p]
    cur[k] = v
    return c


def _add_in_seg(o, path, k, v):
    c = copy.deepcopy(o)
    cur = c
    for p in path:
        cur = cur[p]
    cur[k] = v
    return c


def _add_seg_key(o, k, v):
    c = copy.deepcopy(o); c["segments"][0][k] = v; return c


def _set_directive(o, axis, val):
    c = copy.deepcopy(o)
    c["segments"][0]["directives"][axis] = val
    return c


def _def_line(lines, name) -> int:
    for i, ln in enumerate(lines, 1):
        if ln.startswith(f"def {name}("):
            return i
    return 0


def _normalization_facts(S) -> dict:
    """What normalize_story_plan is allowed to auto-fix - read from its OUTPUT, not
    from a description of it, so the document cannot overstate the repair budget."""
    raw = {"version": 1, "shots": ["站在巷口收伞", {"beat": "走向门"}],
           "story_goal": "g", "global_state": {}}
    out = S.normalize_story_plan(raw)
    fixed = {}
    for s in out["segments"]:
        for k, v in s.items():
            fixed.setdefault(k, v)
    return {"applied": {"shots -> segments 改名（计数唯一化）": "shots" not in out,
                        "裸字符串段 -> {beat: ...}": all(isinstance(s, dict) for s in out["segments"]),
                        "id 按下标重编": [s["id"] for s in out["segments"]],
                        "directives.tail 默认值": out["segments"][0]["directives"].get("tail"),
                        "补齐的可选键": sorted(k for k in S.SEGMENT_KEYS if k in fixed)},
            "validated_after_normalize": not S.validate_story_plan(out),
            "lossless": "只补默认值与改名；不生成任何剧情内容（§34 的修复预算之外，正常化不占次数）"}


def build_all(stamp: str | None = None) -> dict[str, dict]:
    pkg = load_pkg()
    S = importlib.import_module(f"{pkg.__name__}.v28_schemas")
    SM = importlib.import_module(f"{pkg.__name__}.v28_state_machine")
    if stamp is None:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build(S, SM, stamp)


def main() -> int:
    docs = build_all()
    pkg = load_pkg()
    P = importlib.import_module(f"{pkg.__name__}.v28_paths")
    target_dir = Path(P.PROJECT_DIR)
    failures = []
    for kind, doc in docs.items():
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        out = target_dir / doc["x_v28"]["out_name"]
        P.atomic_write_json_raw(out, text)
        gaps = [p for p in doc["x_v28_probes"] if p["expect"] == "NOT_REJECTED"]
        for pr in doc["x_v28_probes"]:
            if pr["probe_status"] != pr["expect"]:
                failures.append(f"{kind}: {pr['rule']} 期望 {pr['expect']}，实测 "
                                f"{pr['probe_status']} | {pr['observed_error']}")
        print(f"[ok] {out}  {len(text):7d} B  probes={len(doc['x_v28_probes']):2d} "
              f"文档承认的宽松处={len(gaps)}")
    if failures:
        print("\nPROBE GATE FAILED —— 校验器行为与文档不一致，必须二选一："
              "\n  收紧 v28_schemas.py，或改正本生成器里的说法。不许只改文档措辞蒙过去。")
        for f in failures:
            print("  - " + f)
        return 1
    print("\nPROBE_GATE=PASS  "
          f"source_sha={docs['story_plan']['x_v28']['source_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
