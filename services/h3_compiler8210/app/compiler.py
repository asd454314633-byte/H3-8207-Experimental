"""官方格式编译器（确定性，零 GPU，零生成式导演模型）。

职责边界（任务书 §15）：
  * 只做"官方模板编译 + 人物与参考映射 + 台词与声音格式 + 时间线格式"。
  * 不创造剧情、不擅自改写动作、不虚构人体空间关系（§8.2）。
  * 只组织用户已经写明的信息。

对外只暴露一个函数：`compile_segment(segment, project, translate)`。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import official_spec as spec
from . import roles as roles_mod
from .h3model import MediaAsset, Project, Role, Segment

TranslateFn = Callable[[str], str]


# ---------------------------------------------------------------------------
# 结果
# ---------------------------------------------------------------------------
@dataclass
class CompileResult:
    prompt: str = ""
    mode: str = ""
    duration: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest().upper()


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def fmt_timestamp(seconds: float) -> str:
    """秒 → MM:SS.mmm（官方镜头时间格式）。"""
    total_ms = int(round(seconds * 1000))
    minutes, rem = divmod(total_ms, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{minutes:02d}:{secs:02d}.{ms:03d}"


def _tidy(text: str) -> str:
    """压空白、去句末悬挂标点；不改动中文台词。"""
    return re.sub(r"\s+", " ", (text or "").strip()).rstrip(". ")


def _sentence(text: str) -> str:
    """补句号，使其可安全拼接（仅用于英文/已翻译文本）。"""
    t = _tidy(text)
    if not t:
        return ""
    return t if t.endswith((".", "!", "?", ":", ";", ">")) else t + "."


def _join_natural(items: list[str]) -> str:
    """自然连接：a / a and b / a, b and c。"""
    vals = [_tidy(x) for x in items if _tidy(x)]
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    return ", ".join(vals[:-1]) + " and " + vals[-1]


def _role_display(role: Role) -> str:
    """提示词中用到的角色名：优先英文名，否则中文名逐字保留。"""
    return (role.name_en or role.name or "").strip()


def _embed(text: str, keep: tuple[str, ...] = ()) -> str:
    """把一个**英文短语**嵌入句中时，把首字母改为小写。

    MT 会把每个独立片段当成新句子，因此译出来都是大写开头；
    直接拼进句子里会出现 "with Young women in their 20s" 这类不自然的写法。
    为避免误伤专有名词，`keep` 里给出的前缀（角色英文名等）一律不动。
    """
    t = _tidy(text)
    if not t or not t[:1].isupper():
        return t
    if t.startswith("<") or t.startswith("("):
        return t
    for name in keep:
        if name and t.startswith(name):
            return t
    head = t.split(" ", 1)[0]
    if head.isupper() and len(head) > 1:      # 缩写（如 POV、N/A）保持大写
        return t
    if len(head) > 1 and head[1:].isupper():  # 首词内部含大写（如 N/A、AC/DC）
        return t
    return t[0].lower() + t[1:]


def _make_translator(base: TranslateFn, protect_terms: dict[str, str]) -> TranslateFn:
    """包一层：把角色名等词条作为受保护项传给翻译引擎（避免被 MT 西化/改写）。"""
    if not protect_terms:
        return base

    def _tr(text: str) -> str:
        try:
            return base(text, protect_terms=protect_terms)  # type: ignore[call-arg]
        except TypeError:
            return base(text)

    return _tr


# ---------------------------------------------------------------------------
# 编号分配
# ---------------------------------------------------------------------------
def assign_subjects(seg: Segment, project: Project) -> dict[str, int]:
    """`<Subject N>` 分配：永久角色 ID 不受生成顺序影响（任务书 §6.4）。

    顺序（确定性）：本段出场角色（按本段 role_ids 顺序）→ 本段场景。
    只有"本段真实使用"的内容才分配 Subject。
    """
    mapping: dict[str, int] = {}
    n = 1
    for rid in seg.role_ids:
        if project.role(rid) is None:
            continue
        key = f"role:{rid}"
        if key not in mapping:
            mapping[key] = n
            n += 1
    if (seg.scene_zh or project.preset.scene).strip():
        mapping["scene"] = n
        n += 1
    return mapping


def assign_speakers(seg: Segment, project: Project) -> tuple[dict[str, int], dict[str, list[str]]]:
    """说话人编号：**按本段实际发声事件顺序**分配（任务书 §6.5）。

    返回 (role_id -> 首个 S 编号, group_id -> 该组说话人显示串)。
    从不发声的角色不分配编号；同一发声者在段内持续复用同一编号。
    """
    role_speaker: dict[str, int] = {}
    group_speakers: dict[str, list[str]] = {}
    next_id = 1
    for d in seg.dialogues:
        rid = d.speaker_role_id
        if not rid or project.role(rid) is None:
            continue
        if not (d.zh_text or "").strip():
            continue                      # 没有实际台词的条目不占用编号
        group = (d.group or "").strip()
        if group:
            bucket = group_speakers.setdefault(group, [])
            if rid not in role_speaker:
                role_speaker[rid] = next_id
                next_id += 1
            token = f"S{role_speaker[rid]}"
            if token not in bucket:
                bucket.append(token)
        elif rid not in role_speaker:
            role_speaker[rid] = next_id
            next_id += 1
    return role_speaker, group_speakers


def assign_references(seg: Segment) -> dict[str, Any]:
    """参考标签分配（任务书 §6.4 / §8.1）。

    两类严格区分：
      * 独立标签：图片作为具体帧锚 / 分镜参考 → 拥有自己的 `<Picture N>` 与 retention 行。
      * 仅来源图片：只用来定义角色容貌/服装/场景 → 写在该 <Subject N> 定义**内部**，
        不单独占编号、不需要 retention 行（官方 ref-en.txt §2.2）。
    `connected=False` 的素材一律不生成任何标签（§7.3 不宣称未连接素材生效）。
    """
    standalone_pictures: dict[str, int] = {}
    source_pictures: dict[str, int] = {}
    videos: dict[str, int] = {}
    audios: dict[str, int] = {}

    p_n = v_n = a_n = 0
    standalone_purposes = {"keyframe_first", "keyframe_last", "storyboard", "composition"}

    # 关键：所有 `<Picture N>` 共用**同一个编号序列**。
    # 否则"独立参考图"与"仅来源图片"会各自从 1 开始，产生重复标签
    # （例如 `<Picture 1>` 同时指首帧和某人的容貌图），官方格式不允许。
    for asset in seg.assets:
        if not asset.connected:
            continue
        if asset.kind == "Picture":
            p_n += 1
            if asset.purpose in standalone_purposes:
                standalone_pictures[asset.id] = p_n
            else:
                source_pictures[asset.id] = p_n
        elif asset.kind == "Video":
            v_n += 1
            videos[asset.id] = v_n
        elif asset.kind == "Audio":
            a_n += 1
            audios[asset.id] = a_n

    return {
        "standalone_pictures": standalone_pictures,
        "source_pictures": source_pictures,
        "videos": videos,
        "audios": audios,
        "unconnected": [a.id for a in seg.assets if not a.connected],
    }


def _asset_token(asset_id: str, refs: dict[str, Any]) -> str:
    for key, kind in (("standalone_pictures", "Picture"),
                      ("source_pictures", "Picture"),
                      ("videos", "Video"),
                      ("audios", "Audio")):
        n = refs[key].get(asset_id)
        if n:
            return f"<{kind} {n}>"
    return ""


# ---------------------------------------------------------------------------
# 主体定义
# ---------------------------------------------------------------------------
def _keep_names(project: Project) -> tuple[str, ...]:
    """需要保持原样（不被小写化）的前缀：所有角色的英文显示名。"""
    return tuple(n for n in (_role_display(r) for r in project.roles) if n)


def _subject_definitions(seg: Segment, project: Project, subjects: dict[str, int],
                         refs: dict[str, Any], translate: TranslateFn,
                         errors: list[str], warnings: list[str]) -> list[str]:
    lines: list[str] = []
    keep = _keep_names(project)

    for rid in seg.role_ids:
        role = project.role(rid)
        key = f"role:{rid}"
        if role is None or key not in subjects:
            continue
        n = subjects[key]

        face = [_asset_token(a.id, refs) for a in seg.assets
                if a.connected and a.role_id == role.id and a.purpose == "face"]
        body = [_asset_token(a.id, refs) for a in seg.assets
                if a.connected and a.role_id == role.id and a.purpose == "body"]
        face = [x for x in face if x]
        body = [x for x in body if x]

        head = f"<Subject {n}> is"
        name = _role_display(role)
        head += f" {name}" if name else " the referenced person"
        if face:
            head += f", whose appearance comes from {' and '.join(face)}"

        clauses: list[str] = []
        if role.appearance:
            a = _translate_safe(translate, role.appearance, errors, warnings,
                                f"{rid} 外观描述")
            if a:
                # 直接作同位语（"…, in their twenties a young woman."），
                # 加 "with" 会变成 "with in their twenties …" 这种非英文写法。
                clauses.append(_embed(a, keep))
        if body:
            clauses.append(f"wearing the outfit shown in {' and '.join(body)}")
        if not clauses:
            clauses.append("whose referenced appearance is preserved")

        lines.append(f"{head}, {', '.join(clauses)}.")

    if "scene" in subjects:
        n = subjects["scene"]
        scene_zh = (seg.scene_zh or project.preset.scene).strip()
        scene_en = _translate_safe(translate, scene_zh, errors, warnings, "场景")
        scene_assets = [a for a in seg.assets if a.connected and a.purpose == "scene"]
        toks = [t for t in (_asset_token(a.id, refs) for a in scene_assets) if t]
        src = f" defined by {' and '.join(toks)}" if toks else ""
        body = _embed(scene_en, keep) or "the referenced environment"
        lines.append(f"<Subject {n}> is the environment{src}, featuring {body}.")
    return lines


# ---------------------------------------------------------------------------
# 台词
# ---------------------------------------------------------------------------
def _speaker_token(role_speaker: dict[str, int], group_speakers: dict[str, list[str]], d) -> str:
    group = (d.group or "").strip()
    if group and group in group_speakers:
        return "(" + ",".join(group_speakers[group]) + ")"
    n = role_speaker.get(d.speaker_role_id)
    return f"(S{n})" if n else ""


def _voice_en(value: str, translate: TranslateFn, errors: list[str],
              warnings: list[str], what: str) -> str:
    """声音/情绪字段：先在确定性术语表里查，未命中才走 MT。"""
    v = (value or "").strip()
    if not v:
        return ""
    try:
        from .translator import glossary as gl
        if v in gl.VOICE_QUALIFIERS:
            return gl.VOICE_QUALIFIERS[v]
    except Exception:  # noqa: BLE001
        pass
    return _translate_safe(translate, v, errors, warnings, what)


def _delivery_clause(d, translate: TranslateFn, errors: list[str], warnings: list[str]) -> str:
    """台词标签**之外**的发声方式说明（任务书 §7.4：情绪写在对白标签外）。"""
    quals: list[str] = []
    for value, what in ((d.emotion, "情绪"), (d.tone, "语气"), (d.rate, "语速"),
                        (d.volume, "音量"), (d.breath, "呼吸")):
        en = _voice_en(value, translate, errors, warnings, what)
        if en:
            quals.append(en)
    return _join_natural(quals)


def _dialogue_sentence(d, role: Role | None, role_speaker: dict[str, int],
                       group_speakers: dict[str, list[str]], translate: TranslateFn,
                       errors: list[str], warnings: list[str],
                       keep: tuple[str, ...] = ()) -> str:
    token = _speaker_token(role_speaker, group_speakers, d)
    if not token:
        return ""

    # 说话人身份短语（角色类型/年龄/性别/音色）写在 <d> 之外
    ident: list[str] = []
    if role is not None:
        if role.appearance:
            a = _translate_safe(translate, role.appearance, errors, warnings,
                                f"{role.id} 说话人身份")
            if a:
                ident.append(_embed(a, keep))
        name = _role_display(role)
        if name:
            ident.append(name)
    who = ", ".join([x for x in ident if x]) or "the speaker"

    if role is not None and not role.default_voice.is_empty():
        voice_bits = []
        for value in (role.default_voice.timbre, role.default_voice.texture,
                      role.default_voice.rate):
            en = _voice_en(value, translate, errors, warnings, f"{role.id} 说话音色")
            if en:
                voice_bits.append(en)
        joined = _join_natural(voice_bits)
        # 术语表里的音色/质感/语速已经是完整短语（"in a raspy voice"、"at a slow pace"），
        # 再套一层 "with a … voice" 会拼出 "with a Low, in a raspy voice … voice"。
        # 因此这里只做自然并列，并显式标明这是该角色固定的声音特征。
        if joined:
            who += f", {joined}"

    verb = spec.OFFSCREEN_VOICEOVER_PHRASE if d.delivery == "offscreen" else "says"
    delivery = _delivery_clause(d, translate, errors, warnings)
    if delivery:
        verb = f"{verb} {delivery}"

    # 中文台词逐字保留（不翻译、不润色、不删减、不改顺序、不擅自添加）
    zh = d.zh_text or ""
    lang = d.language or spec.DEFAULT_LANGUAGE
    clause = f"{who} {token} {verb}: <d>[{lang}] {zh}</d>"
    if d.delivery == "offscreen":
        clause += f" {spec.LIPS_CLOSED_CLAUSE}"
    return clause


# ---------------------------------------------------------------------------
# 时间线
# ---------------------------------------------------------------------------
def _camera_clause(shot, translate: TranslateFn, errors: list[str],
                   warnings: list[str]) -> str:
    if shot.camera_motion:
        natural = None
        try:
            from .translator import glossary as gl
            natural = gl.CAMERA_LABEL_TO_NATURAL.get(shot.camera_motion)
        except Exception:  # noqa: BLE001
            natural = None
        body = natural or f"performs a {shot.camera_motion} movement"
        parts = [body]
        if shot.camera_amplitude:
            parts.append(shot.camera_amplitude)
        if shot.camera_speed:
            parts.append(shot.camera_speed)
        return "the camera " + " ".join(parts)
    if (shot.camera_zh or "").strip():
        return _translate_safe(translate, shot.camera_zh, errors, warnings, "摄影机")
    return ""


def _timeline(seg: Segment, project: Project, refs: dict[str, Any],
              role_speaker: dict[str, int], group_speakers: dict[str, list[str]],
              translate: TranslateFn, errors: list[str], warnings: list[str],
              first_shot_prefix: str = "", relations_clause: str = "") -> tuple[str, int]:
    """构造镜头时间线。返回 (文本, 最终镜头序号)。"""
    from .h3model import Shot
    shots = seg.shots or [Shot(index=1, at_seconds=None, zh_content=seg.action_zh,
                               camera_zh=seg.camera_zh)]
    by_shot: dict[int, list[Any]] = {}
    for d in seg.dialogues:
        idx = getattr(d, "shot_index", 1) or 1
        by_shot.setdefault(idx, []).append(d)

    chunks: list[str] = []
    last_index = 1
    for pos, shot in enumerate(shots, start=1):
        last_index = shot.index or pos
        head = f"[Shot {last_index}]"
        if pos > 1 and shot.at_seconds is not None:
            head += f" At {fmt_timestamp(shot.at_seconds)},"
        elif pos > 1:
            warnings.append(f"第 {last_index} 个镜头缺少时间戳，官方要求后续镜头必须写明切点时间。")

        pieces: list[str] = []
        if pos == 1 and first_shot_prefix:
            pieces.append(_sentence(first_shot_prefix))
        content_en = _translate_safe(translate, shot.zh_content, errors, warnings,
                                     f"[Shot {last_index}] 内容")
        if content_en:
            pieces.append(_sentence(content_en))
        if pos == 1 and relations_clause:
            pieces.append(_sentence(relations_clause))
        cam = _camera_clause(shot, translate, errors, warnings)
        if cam:
            pieces.append(_sentence(cam))
        for d in by_shot.get(last_index, []):
            role = project.role(d.speaker_role_id)
            sent = _dialogue_sentence(d, role, role_speaker, group_speakers,
                                      translate, errors, warnings,
                                      keep=_keep_names(project))
            if sent:
                pieces.append(_sentence(sent))
        chunks.append(f"{head} {' '.join(p for p in pieces if p)}".strip())
    return " ".join(chunks), last_index


def _style_text(seg: Segment, project: Project, translate: TranslateFn,
                errors: list[str], warnings: list[str]) -> str:
    style_zh = (seg.style or project.preset.style_terms).strip()
    if not style_zh:
        return ""
    return _translate_safe(translate, style_zh, errors, warnings, "视觉风格")


def _relations_clause(seg: Segment, project: Project, translate: TranslateFn,
                      errors: list[str], warnings: list[str]) -> str:
    """把**结构化**的角色关系渲染为自然英文（任务书 §6.2 方案 C）。

    只在用户显式填写关系时才生成；只组织用户已写明的信息，
    不虚构任何未被用户写出的空间关系（§8.2）。
    """
    from .translator import glossary as gl

    keep = _keep_names(project)
    out: list[str] = []
    for raw in (seg.relations or []):
        rel = dict(raw or {})
        actor = project.role(str(rel.get("actor") or ""))
        target = project.role(str(rel.get("target") or ""))
        an = _role_display(actor) if actor else ""
        tn = _role_display(target) if target else ""

        pos_zh = _tidy(str(rel.get("position") or ""))
        for pre in gl.RELATION_PREFIXES:
            if pos_zh.startswith(pre) and len(pos_zh) > len(pre):
                pos_zh = pos_zh[len(pre):].strip()
                break
        rel_pos = gl.RELATION_POSITIONS.get(pos_zh)
        if rel_pos:
            pos = rel_pos
        else:
            pos = _tidy(_translate_safe(translate, pos_zh, errors, warnings,
                                       "角色相对位置")) if pos_zh else ""
        act = _embed(_translate_safe(translate, str(rel.get("action") or ""),
                                     errors, warnings, "角色关系动作"), keep)

        if not (an or tn or pos or act):
            continue
        subject = an or "one of the people"
        if pos and tn:
            head = f"{subject} is {pos} {tn}"
        elif pos:
            head = f"{subject} is {pos}"
        elif tn:
            head = f"{subject} faces and interacts with {tn}"
        else:
            head = subject
        body = f"{head} and {act}" if act else head
        out.append(_sentence(body))
    return " ".join(p for p in out if p)


# ---------------------------------------------------------------------------
# 音频两段（严禁包含台词；任务书 §7.4 / 官方 ref-en §6）
# ---------------------------------------------------------------------------
def _soundscape(seg: Segment, project: Project, refs: dict[str, Any],
                translate: TranslateFn, errors: list[str], warnings: list[str]) -> str:
    parts: list[str] = []
    if seg.soundscape_zh.strip():
        parts.append(_sentence(_translate_safe(translate, seg.soundscape_zh, errors,
                                               warnings, "环境音")))
    elif project.preset.sound_style.strip():
        parts.append(_sentence(_translate_safe(translate, project.preset.sound_style,
                                               errors, warnings, "预设声音风格")))
    for asset in seg.assets:
        if asset.connected and asset.kind == "Audio" and asset.purpose in ("ambience", "sfx"):
            n = refs["audios"].get(asset.id)
            if n:
                parts.append(f"The copied ambience layer from <Audio {n}> continues "
                             "throughout the target video.")
    return " ".join(p for p in parts if p) or "N/A"


def _music(seg: Segment, translate: TranslateFn, errors: list[str], warnings: list[str]) -> str:
    if seg.music_zh.strip():
        return _sentence(_translate_safe(translate, seg.music_zh, errors, warnings, "配乐"))
    return "N/A"


# ---------------------------------------------------------------------------
# retention_analysis
# ---------------------------------------------------------------------------
_DEFAULT_RETENTION = {
    "role": "fully_preserved",
    "standalone_picture": "fully_preserved",
    "video": "fully_preserved",
    "audio_copy": "fully_copy",
    "audio_ref": "reference",
}


def _retention_lines(seg: Segment, project: Project, subjects: dict[str, int],
                     refs: dict[str, Any], final_shot: int, translate: TranslateFn,
                     errors: list[str], warnings: list[str]) -> list[str]:
    lines: list[str] = []

    def marker_for(label: str, default: str) -> str:
        chosen = (seg.retention or {}).get(label, default)
        allowed = spec.VISUAL_RETENTION_MARKERS + spec.AUDIO_RETENTION_MARKERS
        return chosen if chosen in allowed else default

    keep = _keep_names(project)
    span = f"[Shot 1]" if final_shot <= 1 else f"[Shot 1] through [Shot {final_shot}]"

    for rid in seg.role_ids:
        role = project.role(rid)
        key = f"role:{rid}"
        if role is None or key not in subjects:
            continue
        n = subjects[key]
        label = f"<Subject {n}>"
        desc = _translate_safe(translate, role.appearance, errors, warnings,
                               f"{rid} 保留说明") if role.appearance else ""
        note = _embed(desc, keep) or "the referenced appearance and identity are retained"
        lines.append(f"{label} (appears in {span}): "
                     f"{marker_for(label, _DEFAULT_RETENTION['role'])} - {note}.")

    for aid, n in refs["standalone_pictures"].items():
        label = f"<Picture {n}>"
        asset = next((a for a in seg.assets if a.id == aid), None)
        note = _translate_safe(translate, asset.note, errors, warnings,
                               "参考图说明") if (asset and asset.note) else ""
        note = _tidy(note) or "the referenced frame composition and content are retained"
        lines.append(f"{label} ([Shot 1] keyframe): "
                     f"{marker_for(label, _DEFAULT_RETENTION['standalone_picture'])} - {note}.")

    for _aid, n in refs["videos"].items():
        label = f"<Video {n}>"
        lines.append(f"{label} (temporal structure): "
                     f"{marker_for(label, _DEFAULT_RETENTION['video'])} - "
                     "the referenced temporal structure guides the target video.")

    for aid, n in refs["audios"].items():
        label = f"<Audio {n}>"
        asset = next((a for a in seg.assets if a.id == aid), None)
        default = (_DEFAULT_RETENTION["audio_copy"]
                   if asset and asset.purpose in ("voice_copy", "full_copy")
                   else _DEFAULT_RETENTION["audio_ref"])
        if asset and asset.purpose == "voice_timbre":
            note = ("the target speaker follows its voice timbre and measured delivery "
                    "without copying the original signal")
        else:
            note = "its audible characteristics guide the target video"
        lines.append(f"{label}: {marker_for(label, default)} - {note}.")

    # 场景主体同样是被跟踪的参考标签，官方要求 retention 覆盖**每一个**被跟踪标签
    # （上游校验规则 retention_coverage）。漏掉它会导致校验直接判 error。
    if "scene" in subjects:
        label = f"<Subject {subjects['scene']}>"
        scene_zh = (seg.scene_zh or project.preset.scene).strip()
        desc = _translate_safe(translate, scene_zh, errors, warnings,
                               "场景保留说明") if scene_zh else ""
        note = _embed(desc, keep) or "the referenced environment is retained"
        lines.append(f"{label} (appears in {span}): "
                     f"{marker_for(label, _DEFAULT_RETENTION['role'])} - {note}.")
    return lines


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def compile_segment(seg: Segment, project: Project,
                    translate: TranslateFn | None = None) -> CompileResult:
    """把一个段编译为符合 MiniMax H3 官方格式的完整提示词。"""
    if translate is None:
        from .translator import translate_zh_to_en as translate  # 延迟导入，便于测试注入

    res = CompileResult(mode=seg.mode, duration=int(seg.duration or 0))
    err, warn = res.errors, res.warnings

    # ---- 前置校验 --------------------------------------------------------
    if seg.mode not in spec.ALL_MODES:
        err.append(f"未知生成模式：{seg.mode}")
        return res
    if not isinstance(seg.duration, int) or not (spec.MIN_DURATION <= seg.duration <= spec.MAX_DURATION):
        err.append(f"时长必须是 {spec.MIN_DURATION}–{spec.MAX_DURATION} 之间的整数秒。")
        return res
    for rid in seg.role_ids:
        if project.role(rid) is None:
            err.append(f"本段引用了不存在的角色：{rid}")
    if err:
        return res

    # ---- 指代歧义（不猜测，直接提示用户） -------------------------------
    for issue in roles_mod.detect_ambiguity(seg.action_zh, project, seg.role_ids):
        warn.append(issue)

    refs = assign_references(seg)
    for aid in refs["unconnected"]:
        asset = next((a for a in seg.assets if a.id == aid), None)
        if asset:
            warn.append(f"素材「{asset.label or asset.id}」未真实连接，"
                        "本段不会为它生成任何引用标签。")

    is_ref = seg.mode == spec.REF_MODE
    n_pic = len(refs["standalone_pictures"]) + len(refs["source_pictures"])
    if is_ref:
        usable = n_pic + len(refs["videos"])
        if usable == 0:
            err.append("Ref2VA 至少需要一张已连接的参考图或参考视频。")
        elif refs["audios"] and n_pic == 0 and not refs["videos"]:
            err.append("仅音频参考无效：参考音频必须与图片或视频一起使用。")
    else:
        cap = spec.MODE_CAPACITY_HINT[seg.mode]["Picture"]
        if n_pic > cap:
            err.append(f"{spec.MODE_LABELS_ZH[seg.mode]} 只支持 {cap} 张关键帧图片，"
                       f"当前有 {n_pic} 张已连接素材（首尾帧不能伪装成多张 Ref2VA 参考图）。")
        if refs["videos"] or refs["audios"]:
            err.append(f"{spec.MODE_LABELS_ZH[seg.mode]} 不支持视频/音频参考素材。")
    if err:
        return res

    # ---- 受保护词条：角色名不参与机器翻译 --------------------------------
    protect: dict[str, str] = {}
    for role in project.roles:
        disp = _role_display(role)
        for alias in role.all_names():
            if disp:
                protect[alias] = disp
    tr = _make_translator(translate, protect)

    subjects = assign_subjects(seg, project)
    role_speaker, group_speakers = assign_speakers(seg, project)

    for d in seg.dialogues:
        if (d.zh_text or "").strip() and not d.speaker_role_id:
            warn.append("有一条台词未选择说话人，已跳过。")

    style_open = _style_text(seg, project, tr, err, warn)
    # 基础模式：官方要求风格写在 [Shot 1] 之内；Ref2VA：风格是 [Shot 1] 之前的一两句话
    prefix = "" if is_ref else style_open
    relations_clause = _relations_clause(seg, project, tr, err, warn)
    timeline, final_shot = _timeline(seg, project, refs, role_speaker, group_speakers,
                                     tr, err, warn, first_shot_prefix=prefix,
                                     relations_clause=relations_clause)
    if err:
        return res

    soundscape = _soundscape(seg, project, refs, tr, err, warn)
    music = _music(seg, tr, err, warn)

    blocks: list[str] = []
    if is_ref:
        defs = _subject_definitions(seg, project, subjects, refs, tr, err, warn)
        types = [t for t in seg.task_types if t in spec.TASK_TYPES] or ["reference generation"]
        summary_src = seg.extra_zh if seg.extra_zh.strip() else seg.action_zh
        summary_en = _translate_safe(tr, summary_src, err, warn, "summary")
        summary = f"[{' + '.join(dict.fromkeys(types))}] {_tidy(summary_en)}"
        retention = _retention_lines(seg, project, subjects, refs, final_shot, tr, err, warn)
        detail = " ".join(x for x in (style_open, timeline) if x)
        blocks.append("subject_definitions:\n" + "\n".join(defs))
        blocks.append("summary:\n" + summary)
        blocks.append("retention_analysis:\n" + "\n".join(retention))
        blocks.append("detailed_description:\n" + detail)
        blocks.append("overall_soundscape:\n" + soundscape)
        blocks.append("non_diegetic_music:\n" + music)
        body = "\n\n".join(blocks)
    else:
        blocks.append("integrated_multimodal_description: " + timeline)
        blocks.append("overall_soundscape: " + soundscape)
        blocks.append("non_diegetic_music: " + music)
        body = "\n\n".join(blocks)

    align = spec.alignment_instruction(seg.mode, seg.duration, final_shot)
    prompt = f"{align}\n\n{body}" if align else body

    if len(prompt) > spec.MAX_PROMPT_CHARS:
        err.append(f"编译结果 {len(prompt)} 字符，超过官方上限 {spec.MAX_PROMPT_CHARS}。")

    res.prompt = prompt
    res.meta = {
        "subjects": subjects,
        "role_speaker": role_speaker,
        "group_speakers": group_speakers,
        "references": refs,
        "final_shot": final_shot,
        "char_count": len(prompt),
        "dialogue_events": len([d for d in seg.dialogues if (d.zh_text or "").strip()]),
    }
    return res


# ---------------------------------------------------------------------------
# 翻译辅助（供 compiler 内部使用，保持签名独立便于测试）
# ---------------------------------------------------------------------------
def _translate_safe(translate: TranslateFn, text: str, errors: list[str],
                    warnings: list[str], what: str) -> str:
    """翻译单个字段。失败时保留中文并记录，绝不伪造成功（任务书 §9.3）。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        out = translate(raw)
    except Exception as exc:  # noqa: BLE001 - 需要对任意 Provider 失败保持鲁棒
        warnings.append(f"翻译失败（{what}）：{exc}；该字段保留中文原文。")
        return raw
    out = (out or "").strip()
    if not out:
        warnings.append(f"翻译返回空（{what}）：该字段保留中文原文。")
        return raw
    return out
