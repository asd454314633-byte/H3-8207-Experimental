"""V28 Director - the instruction text the director model is given.

Kept apart from the transport code so a supervisor can read, in one place,
exactly what we ask the model to do. Everything here is our own wording; the
H3 output-format requirements it references live in v28_prompt_compiler.py and
are derived in V28_PROMPT_COMPILER_RULES.md (task section 18: rules reused,
third-party source code not copied).

Language policy (task section 35): user-facing content is Chinese - `beat`,
`story_goal`, `start_state`/`end_state` values. Only the fields that H3 itself
consumes (`prompt`, and the six compiled sections) are English. The user never
has to read English to run V28.
"""
from __future__ import annotations

import json
from typing import Any

from . import v28_prompt_compiler as C
from . import v28_schemas as S

JSON_ONLY_TAIL = (
    "\n\n输出要求（硬性）：\n"
    "1. 只输出一个 JSON 值。不要解释、不要前后缀、不要 Markdown 代码块。\n"
    "2. 不要输出思考过程文字；思考只在内部进行。\n"
    "3. 字段名必须与示例逐字一致，不得增删顶层键。\n"
    "4. 字符串内不要使用换行；需要分隔时用中文分号。\n"
)


# ==========================================================================
# 1. reference analysis (task sections 11 / 12 / 32)
# ==========================================================================
ANALYZE_SYSTEM = """\
你是影视选角与美术部门的「参考图记录员」。你的唯一职责是把参考图里**看得见的东西**
逐项记录下来，供后续剧情规划使用。你不是编剧，也不是动作指导。

必须遵守：
1. 只写你在图中实际看到的内容。看不到、被裁掉、被遮挡的一律不写。
2. 严禁推测：人物接下来会往哪走、身体不可见部分的结构、图中不存在的信息、任何剧情意图。
   这些是"不可回答"，要放进 do_not_infer / not_answerable，而不是编造。
3. 事实与推断必须分开：确定的外观写进 seen；确实需要但图中不完整的判断写进 inferred，
   并且必须写明依据是哪张图。
4. 人物编号按出场显著度；picture_refs 用 <Picture N> 的序号（从 1 开始，按给定顺序）。
5. 每人给出可用于跨段保持的"稳定标识"：发型、眼镜、显著外观特征、服装各部位。
   这些标签会被逐段复用，所以要用最不会随动作改变的方式描述（颜色+款式，不要写情绪）。
6. 场景与环境同样只写可见元素：空间类型、主要家具/结构、光线方向、色调。
7. 道具只列图中可见的，不要预置剧情道具。
""" + JSON_ONLY_TAIL + """
JSON 结构（严格按此形状，键名逐字一致）：
{
  "version": 1,
  "source_pictures": [{"index": 1, "filename": "a.png", "width": 1024, "height": 1024}],
  "subjects": [
    {"id": "subject_1", "picture_refs": [1, 2], "role": "女主角（标签，非剧情）",
     "seen": {"hair": "", "glasses": "", "wardrobe": {"上装": "", "下装": "", "鞋": ""},
              "distinctive_appearance": [],
              "visible_pose": {"body": "", "facing": "", "hands": ""}},
     "inferred": {"wardrobe_complete": "", "依据": ""},
     "do_not_infer": ["未来运动方向", "不可见身体结构"]}
  ],
  "scene": {"seen": {"space": "", "light": "", "palette": "", "key_objects": []},
            "inferred": {}},
  "props": [{"name": "", "picture_ref": 1, "state": ""}],
  "composition": {"seen": {"shot_size": "", "camera_height": "", "subject_position": ""},
                  "inferred": {}},
  "uncertain": [],
  "not_answerable": []
}"""


def analyze_user(images: list[dict], brief: str = "") -> str:
    n = len(images)
    lines = [f"本次共提供 {n} 张参考图，顺序即 <Picture 1> .. <Picture {n}>："]
    for i, im in enumerate(images, start=1):
        lines.append(f"  <Picture {i}> 文件：{im.get('name') or im.get('filename') or '(unnamed)'}")
    if brief:
        lines.append(f"\n作者补充说明（只作参考，不得据此编造画面内容）：{brief}")
    lines.append("\n请只输出 REFERENCE_PROFILE JSON。")
    return "\n".join(lines)


# ==========================================================================
# 2. story planning (task sections 13 / 14 / 15 / 16 / 19)
# ==========================================================================
PLAN_SYSTEM_TEMPLATE = """\
你是本地导演规划模型，负责把一个中文剧情构想拆成**连续生成的分段计划**。
你只规划，不生成视频；判断好坏和是否接受片段永远由人来做。

硬规则：
1. 段数必须正好是 {n} 段，id 从 1 连续到 {n}，每段时长 {seg_seconds} 秒。
   一段就是一个镜头（shot），只有一个计数器，不存在第二个"镜头数"。
2. 每段的动作负荷上限 = 1 个主要动作 + 1 个自然过渡动作 + 必要的镜头行为。
   禁止把"起床/走路/换衣/打电话/开车/离开"塞进同一段——那种计划无法执行。
3. 全局事实只写一次，放在 global_state：人物身份与服装、场景、整体视觉风格、
   摄影规则、身份保持要求、参考图映射。
   每段的 prompt 只写**这一段新发生的动作**，禁止重复转述整个故事或复述上一段。
4. 状态必须连续：segment k 的 start_state 必须能由 segment k-1 的 end_state 自然到达。
   不许出现瞬移、换装、突然换地点，除非剧情构想明确要求切镜并且 continuation_mode 允许。
5. continuation_mode = {continuation_mode}。
   {continuation_rule}
6. 段与段之间不得重复相同的 beat 描述；剧情按时间顺序推进，首段必须从参考图所示状态起步。
7. 字段语言：beat / story_goal / start_state / end_state 的值用中文；
   prompt 的值用英文（这是唯一给 H3 视频模型读的文本），只写一句到两句新动作，
   不要写镜头标签列表、不要写 "push in, small amplitude" 这类尾随标签。
8. prompt 里禁止"瞬间/suddenly/instantly/ abruptly"一类让画面硬跳的词，动作必须有过程。
9. directives 每轴只能取给定枚举值：
   join ∈ {join}；camera ∈ {camera}；framing ∈ {framing}；pace ∈ {pace}；tail ∈ {tail}。
   第 1 段 join 用 continuous；最后一段 tail 用 settle 或 hold。
10. seed 一律填 null（种子由本地状态机分配）；locked 一律填 false。
11. 不要写音频台词，除非剧情构想明确要求对白；需要时把台词原文放进 beat，
    并在 prompt 里用 <d>[Chinese 原话]</d> 逐字保留。
""" + JSON_ONLY_TAIL + """
JSON 结构（严格按此形状，顶层键不得增删）：
{{
  "version": 1,
  "story_goal": "一句话中文剧情目标",
  "global_state": {{"identities": [], "wardrobe": "", "scene": "", "visual_style": "",
                    "camera_rules": "", "identity_lock": "", "reference_map": ""}},
  "references": {{"picture_count": {n_pics}, "scene": "", "subject_labels": [],
                 "scene_phrase": ""}},
  "style": "auto",
  "continuation_mode": "{continuation_mode}",
  "director": {{"provider": "{provider}", "model": "{model}"}},
  "generated_from": {{"story_goal_sha": "", "total_seconds": {total}, "segment_seconds": {seg_seconds},
                      "segment_count": {n}}},
  "warnings": [],
  "segments": [
    {{"id": 1, "beat": "中文节拍描述", "start_state": {{"pose": "", "position": "", "facing": ""}},
      "end_state": {{"pose": "", "position": "", "facing": "", "completed": ""}},
      "directives": {{"join": "continuous", "camera": "hold", "framing": "keep",
                      "pace": "steady", "tail": "ongoing"}},
      "prompt": "English sentence describing only this segment's new action.",
      "duration": {seg_seconds}, "seed": null, "locked": false}}
  ]
}}"""


CONT_RULE_SAME = ("整片按同一镜头连续演进：每段开头必须自然延续上一段结尾的姿态、"
                  "动作趋势、运动节奏与镜头状态，约 1.5–2 秒之后才展开本段新动作。")
CONT_RULE_CUT = ("允许自然切镜：可以在必要处用 match_cut/hard_cut 换视点，"
                 "但切镜前的一段结尾必须收住（tail 用 settle 或 hold），"
                 "并且除切镜段之外同样遵守先延续再展开的规则。")


def plan_user(*, story_goal: str, profile: dict, total_seconds: float,
              segment_seconds: float, style: str, continuation_mode: str,
              n: int, provider: str = "", model: str = "") -> tuple[str, str]:
    system = PLAN_SYSTEM_TEMPLATE.format(
        n=n, seg_seconds=int(round(segment_seconds)), total=int(round(total_seconds)),
        continuation_mode=continuation_mode,
        continuation_rule=(CONT_RULE_SAME if continuation_mode == "same_shot" else CONT_RULE_CUT),
        join=" | ".join(S.DIRECTIVE_AXES["join"]), camera=" | ".join(S.DIRECTIVE_AXES["camera"]),
        framing=" | ".join(S.DIRECTIVE_AXES["framing"]), pace=" | ".join(S.DIRECTIVE_AXES["pace"]),
        tail=" | ".join(S.DIRECTIVE_AXES["tail"]), n_pics=len(profile.get("source_pictures") or []) or 0,
        provider=provider or "unknown", model=model or "unknown")
    u = ["【剧情构想】", story_goal.strip() or "(空)", "",
         f"【目标总时长】{int(round(total_seconds))} 秒",
         f"【每段时长】{int(round(segment_seconds))} 秒  →  必须正好 {n} 段",
         f"【剧情风格】{style or 'auto'}",
         f"【镜头连续方式】{'同镜头连续' if continuation_mode == 'same_shot' else '允许自然切镜'}",
         "", "【参考图记录 REFERENCE_PROFILE（已由视觉模型确认，只可引用，不可改写）】",
         json.dumps(profile, ensure_ascii=False)[:7000],
         "", "请输出 STORY_PLAN JSON。"]
    return system, "\n".join(u)


# ==========================================================================
# 3. per-segment prompt compilation (task sections 17 / 18)
# ==========================================================================
COMPILE_SYSTEM = """\
你把一段中文节拍翻译成 H3 视频模型用的**英文动作句**。你不是编剧，不得改动剧情。

硬规则：
1. 只写这一段新发生的动作与必要的镜头行为；不得复述全局设定，不得转述其他段。
2. 输出 1–3 句英文，全部是可被看见/听见的客观描述（不写情绪词、不写"氛围"、不写心理）。
3. 摄影运动写成自然句子里的一部分，带幅度与速度（例：
   "The camera pushes in with small amplitude at slow speed toward ..."），
   禁止句尾堆标签。
4. 严禁瞬间变化：不出现 suddenly / instantly / abruptly / snaps / spins / freezes / stops dead。
5. 若这是接续段（非第 1 段），第一句必须承接上一段的姿态与运动趋势，再展开新动作。
6. 如剧情明确需要对白：说话人第一次出现时给外貌/声音描述，台词放进 <d>[Chinese 原文]</d>，
   逐字保留，不翻译。
7. 环境音与配乐各一句以内；没有就写 N/A。
""" + JSON_ONLY_TAIL + """
JSON 结构：
{"prompt": "English action sentences for this segment only.",
 "soundscape": "1-2 English sentences or N/A", "music": "1 English sentence or N/A",
 "notes": ""}"""


def compile_user(*, plan: dict, seg: dict, profile: dict, prev_seg: dict | None,
                 segment_id: int, override_beat: str = "") -> str:
    g = plan.get("global_state") or {}
    lines = [f"【当前段号】{segment_id} / {len(plan.get('segments') or [])}",
             f"【本段节拍】{override_beat or seg.get('beat')}",
             f"【本段起始状态】{json.dumps(seg.get('start_state') or {}, ensure_ascii=False)}",
             f"【本段结束状态】{json.dumps(seg.get('end_state') or {}, ensure_ascii=False)}",
             f"【镜头指令】{json.dumps(seg.get('directives') or {}, ensure_ascii=False)}",
             f"【本段时长】{seg.get('duration')} 秒",
             "", "【全局设定（仅作一致性约束，禁止写进 prompt）】",
             json.dumps({k: v for k, v in g.items()}, ensure_ascii=False)[:2500]]
    if prev_seg:
        lines += ["", "【上一段结束状态（本段第一句必须承接它）】",
                  json.dumps(prev_seg.get("end_state") or {}, ensure_ascii=False),
                  f"上一段节拍：{prev_seg.get('beat')}"]
    else:
        lines += ["", "【这是第 1 段：必须从参考图所示状态自然起步】",
                  json.dumps({"subjects": [s.get("seen") for s in (profile.get("subjects") or [])][:2],
                              "scene": (profile.get("scene") or {}).get("seen")},
                             ensure_ascii=False)[:1500]]
    lines += ["", "请只输出编译 JSON。"]
    return "\n".join(lines)


# ==========================================================================
# 4. tail replan (task section 27) - same planner, restricted range
# ==========================================================================
def replan_user(*, plan: dict, from_segment: int, story_goal: str, profile: dict,
                segment_seconds: float, continuation_mode: str) -> tuple[str, str]:
    segs = plan.get("segments") or []
    keep = segs[:max(0, from_segment - 1)]
    n_left = len(segs) - len(keep)
    system, base = plan_user(
        story_goal=story_goal, profile=profile, total_seconds=n_left * segment_seconds,
        segment_seconds=segment_seconds, style=plan.get("style") or "auto",
        continuation_mode=continuation_mode, n=n_left,
        provider="bonsai2", model="tail-replan")
    lock_note = [
        "", "【重新规划范围】",
        f"已接受并锁定的段：{len(keep)} 段（id 1..{len(keep)}），一个字节都不许改。",
        f"只需规划 id {from_segment}..{len(segs)}，共 {n_left} 段。",
        "输出的 segments 数组长度必须正好是 "
        f"{n_left}，且必须能被上一段（id {len(keep)}）的状态自然接续。",
    ]
    if keep:
        lock_note += ["上一段（已锁定）的结束状态：",
                      json.dumps((keep[-1] or {}).get("end_state") or {}, ensure_ascii=False)]
    return system + "\n".join(lock_note), base
