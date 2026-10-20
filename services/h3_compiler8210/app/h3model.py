"""数据模型：角色库 / 默认参考预设 / 段 / 工程。

设计纪律（对应任务书 §6、§7、§10）：
  * 角色编号是本项目**本地永久 ID**（C01、C02…），不是 H3 官方标签，
    一经建立不随出场顺序改变，删除本段出场不删除角色档案。
  * 所有关联一律用稳定 ID，绝不使用"界面排序"做数据关联依据。
  * 全部结构可 JSON 往返，字段带 schema 版本以便迁移与回滚。
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = 1

ROLE_ID_RE = re.compile(r"^C(\d{2,})$")


def next_role_id(existing: list[str]) -> str:
    """返回下一个永久角色编号（C01、C02…），编号只增不复用。"""
    top = 0
    for rid in existing:
        m = ROLE_ID_RE.match(rid)
        if m:
            top = max(top, int(m.group(1)))
    return f"C{top + 1:02d}"


# ---------------------------------------------------------------------------
# 声音
# ---------------------------------------------------------------------------
@dataclass
class VoiceProfile:
    """角色**固定音色**（永久声音身份）。任务书 §7.1。"""

    pitch: str = ""          # 音高
    timbre: str = ""         # 音色
    texture: str = ""        # 声音质感
    accent: str = ""         # 口音
    rate: str = ""           # 默认语速
    volume: str = ""         # 默认音量
    audio_file: str = ""     # 可选声音参考文件（真实素材路径/名称）

    def is_empty(self) -> bool:
        return not any([self.pitch, self.timbre, self.texture, self.accent,
                        self.rate, self.volume])

    def english_descriptors(self) -> list[str]:
        """返回用于写入提示词的英文音色描述片段（由术语层翻译后填入）。"""
        out = []
        for label, value in (("pitch", self.pitch), ("timbre", self.timbre),
                             ("texture", self.texture), ("accent", self.accent),
                             ("speaking rate", self.rate), ("volume", self.volume)):
            if value.strip():
                out.append(f"{label}: {value.strip()}")
        return out


@dataclass
class Role:
    """角色档案。永久编号 + 别名 + 参考素材。任务书 §6.1。"""

    id: str
    name: str = ""
    name_en: str = ""           # 英文名（可选）。留空则中文名逐字保留、不参与翻译
    aliases: list[str] = field(default_factory=list)
    appearance: str = ""        # 中文外观描述
    face_ref: str = ""          # 容貌参考（图片素材标识）
    body_ref: str = ""          # 身体及服装参考
    default_voice: VoiceProfile = field(default_factory=VoiceProfile)
    audio_ref: str = ""         # 可选音频素材（真实连接才生效）
    states: list[str] = field(default_factory=list)   # 状态预设

    def display(self) -> str:
        return f"{self.id}（{self.name}）" if self.name else self.id

    def all_names(self) -> list[str]:
        """用于确定性指代匹配的全部名称（姓名 + 别名），已去空与去重。"""
        seen, out = set(), []
        for raw in [self.name, *self.aliases]:
            n = (raw or "").strip()
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out


# ---------------------------------------------------------------------------
# 参考预设（任务书 §5-A）
# ---------------------------------------------------------------------------
@dataclass
class ReferencePreset:
    """当前参考预设。默认加载用户最近一次保存的预设，可被本段临时覆盖。"""

    name: str = "默认参考预设"
    scene: str = ""                       # 当前场景（中文）
    people_ref: str = ""                  # 人物容貌参考（整体）
    body_costume_ref: str = ""            # 体型与服装参考
    voice_ref: str = ""                   # 声音参考
    camera_style: str = ""                # 摄影风格（中文）
    sound_style: str = ""                 # 声音风格（中文）
    style_terms: str = ""                 # 视觉风格（如 Cinematic、live-action）

    def clone(self) -> "ReferencePreset":
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# 素材（真实连接判定，任务书 §7.3 / §8.1）
# ---------------------------------------------------------------------------
@dataclass
class MediaAsset:
    """一个参考素材。

    关键纪律：`connected=True` 表示它**确实被目标工作流读取**；
    仅"编辑器里存了文件"不等于生效，未连接的素材不得生成引用标签。
    """

    id: str
    kind: str                 # "Picture" | "Video" | "Audio"
    label: str = ""           # 素材来源说明（中文）
    connected: bool = False   # 是否真实连接
    role_id: str = ""         # 归属角色（可空：场景/道具）
    purpose: str = ""         # 用途：face/body/voice/scene/keyframe_first/keyframe_last/storyboard
    note: str = ""            # 中文补充说明


# ---------------------------------------------------------------------------
# 台词（任务书 §5-C、§7.2、§7.4）
# ---------------------------------------------------------------------------
@dataclass
class Dialogue:
    id: str
    speaker_role_id: str = ""
    zh_text: str = ""         # 中文原文：逐字保留，不翻译不润色
    emotion: str = ""         # 情绪
    tone: str = ""            # 语气
    rate: str = ""            # 语速
    volume: str = ""          # 音量
    pause: str = ""           # 停顿
    breath: str = ""          # 呼吸方式
    delivery: str = "onscreen"   # onscreen | offscreen
    language: str = "Chinese"
    group: str = ""              # 同时发声分组：同组的多条台词合并为复合说话人 ID (S1,S2)
    shot_index: int = 1          # 归属镜头序号（缺省并入 [Shot 1]）


# ---------------------------------------------------------------------------
# 镜头
# ---------------------------------------------------------------------------
@dataclass
class Shot:
    index: int = 1
    at_seconds: float | None = None   # 首个镜头必须为 None
    zh_content: str = ""              # 中文镜头内容
    camera_zh: str = ""               # 中文镜头说明
    camera_motion: str = ""           # 官方英文运动类型（可选，确定性）
    camera_amplitude: str = ""
    camera_speed: str = ""


# ---------------------------------------------------------------------------
# 段（六段剧情，任务书 §12）
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    id: str
    title: str = ""
    order: int = 1
    mode: str = "Ref2VA"
    duration: int = 6
    style: str = ""                    # 视觉风格（中文，可空则用预设）
    scene_zh: str = ""                 # 本段场景
    action_zh: str = ""                # 动作与行为（主输入）
    camera_zh: str = ""                # 摄影机（可留空）
    soundscape_zh: str = ""            # 环境音
    music_zh: str = ""                 # 配乐
    extra_zh: str = ""                 # 其他要求
    role_ids: list[str] = field(default_factory=list)     # 本段出场角色（永久 ID）
    dialogues: list[Dialogue] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    assets: list[MediaAsset] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)   # summary 前缀（Ref2VA）
    retention: dict[str, str] = field(default_factory=dict)  # 标签 -> 标记
    # 角色关系（多人复杂场景展开；任务书 §6.2 方案 C）
    # 每项：{"actor": 角色ID, "target": 角色ID, "position": 位置关系, "action": 动作关系}
    relations: list[dict] = field(default_factory=list)
    inherit_prev_end_state: str = ""   # 继承上一段明确记录的结束状态（可为空）
    final_edited_prompt: str = ""      # 人工编辑后的最终文本（最高优先级）
    final_edited_sha256: str = ""      # 人工编辑文本的哈希（用于旧校验状态失效）
    compiled_prompt: str = ""          # 上一次编译结果
    compiled_sha256: str = ""
    compiled_valid: bool = False
    compile_warnings: list[str] = field(default_factory=list)
    compile_errors: list[str] = field(default_factory=list)

    def end_state_zh(self) -> str:
        """本段明确记录的结束状态（供下一段选择性继承）。"""
        return self.inherit_prev_end_state.strip()


# ---------------------------------------------------------------------------
# 工程
# ---------------------------------------------------------------------------
@dataclass
class Project:
    name: str = "未命名工程"
    schema_version: int = SCHEMA_VERSION
    roles: list[Role] = field(default_factory=list)
    preset: ReferencePreset = field(default_factory=ReferencePreset)
    segments: list[Segment] = field(default_factory=list)
    active_segment_id: str = ""
    compiler_version: str = ""
    official_skill_commit: str = ""

    # -- 角色库操作 -------------------------------------------------------
    def role(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)

    def add_role(self, name: str = "", **kw: Any) -> Role:
        kw.setdefault("id", next_role_id([r.id for r in self.roles]))
        role = Role(name=name, **kw)
        self.roles.append(role)
        return role

    def remove_role(self, role_id: str) -> bool:
        """从角色库彻底删除（会同时从各段出场名单移除）。"""
        before = len(self.roles)
        self.roles = [r for r in self.roles if r.id != role_id]
        if len(self.roles) == before:
            return False
        for seg in self.segments:
            seg.role_ids = [x for x in seg.role_ids if x != role_id]
            seg.dialogues = [d for d in seg.dialogues if d.speaker_role_id != role_id]
        return True

    # -- 段操作 -----------------------------------------------------------
    def segment(self, seg_id: str) -> Segment | None:
        return next((s for s in self.segments if s.id == seg_id), None)

    def next_segment_id(self) -> str:
        top = 0
        for s in self.segments:
            m = re.match(r"SEG(\d+)", s.id or "")
            if m:
                top = max(top, int(m.group(1)))
        return f"SEG{top + 1:02d}"

    def add_segment(self, **kw: Any) -> Segment:
        """新建段。`id`/`order` 未显式给出时自动分配（显式值优先，不覆盖调用方）。"""
        kw.setdefault("id", self.next_segment_id())
        kw.setdefault("order", len(self.segments) + 1)
        seg = Segment(**kw)
        self.segments.append(seg)
        return seg

    # -- 序列化 -----------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Project":
        data = dict(data or {})
        roles = []
        for r in data.get("roles", []):
            r = dict(r)
            r["default_voice"] = VoiceProfile(**(r.get("default_voice") or {}))
            roles.append(Role(**{k: v for k, v in r.items() if k in Role.__dataclass_fields__}))
        preset = ReferencePreset(**(data.get("preset") or {}))
        segs = []
        for s in data.get("segments", []):
            s = dict(s)
            s["dialogues"] = [Dialogue(**{k: v for k, v in d.items()
                                         if k in Dialogue.__dataclass_fields__})
                              for d in s.get("dialogues", [])]
            s["shots"] = [Shot(**{k: v for k, v in sh.items() if k in Shot.__dataclass_fields__})
                          for sh in s.get("shots", [])]
            s["assets"] = [MediaAsset(**{k: v for k, v in a.items()
                                         if k in MediaAsset.__dataclass_fields__})
                           for a in s.get("assets", [])]
            segs.append(Segment(**{k: v for k, v in s.items()
                                   if k in Segment.__dataclass_fields__}))
        return Project(
            name=data.get("name", "未命名工程"),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            roles=roles,
            preset=preset,
            segments=segs,
            active_segment_id=data.get("active_segment_id", ""),
            compiler_version=data.get("compiler_version", ""),
            official_skill_commit=data.get("official_skill_commit", ""),
        )
