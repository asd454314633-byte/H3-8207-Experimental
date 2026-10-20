"""H3 官方格式规范常量（唯一真源）。

来源（A 级证据，逐字取自官方 Skill，不得凭记忆改动）：
  MiniMax-AI/MiniMax-H3  @ d21241f0a4b3acbb34c97dae47fa417b7065e438
    skills/h3-prompt-writing/SKILL.md          95D74FEE00E78641FB9E774AB17488516CEECE441231519287F0D3128EAA8C54
    skills/h3-prompt-writing/references/base-en.txt  088FB632FA3CBB18C9821024FB689E6F0F356F824C8F2E6B8E43A33239B137C7
    skills/h3-prompt-writing/references/ref-en.txt   B621067B41988C4D92BE715B7A98BA48338F4076AB6041D95FCF463EA7C8CCDD

本模块只存放"不可变事实"。任何改动都必须重新取证并更新 _evidence/g0_upstream/。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 上游版本锁
# --------------------------------------------------------------------------
OFFICIAL_SKILL_REPO = "https://github.com/MiniMax-AI/MiniMax-H3"
OFFICIAL_SKILL_COMMIT = "d21241f0a4b3acbb34c97dae47fa417b7065e438"
OFFICIAL_SKILL_SHA256 = {
    "SKILL.md": "95D74FEE00E78641FB9E774AB17488516CEECE441231519287F0D3128EAA8C54",
    "references/base-en.txt": "088FB632FA3CBB18C9821024FB689E6F0F356F824C8F2E6B8E43A33239B137C7",
    "references/ref-en.txt": "B621067B41988C4D92BE715B7A98BA48338F4076AB6041D95FCF463EA7C8CCDD",
}

VALIDATOR_REPO = "https://github.com/babicat4242-svg/minimax-h3-prompting"
VALIDATOR_COMMIT = "20256a88875164008eb71b1741a99e65996196ad"
VALIDATOR_LICENSE = "MIT"

# --------------------------------------------------------------------------
# 模式
# --------------------------------------------------------------------------
BASE_MODES = ("T2VA", "I2VA", "FL2VA", "L2VA")
REF_MODE = "Ref2VA"
ALL_MODES = BASE_MODES + (REF_MODE,)

MODE_LABELS_ZH = {
    "T2VA": "纯文本生成（T2VA）",
    "I2VA": "首帧图生视频（I2VA）",
    "FL2VA": "首尾帧生视频（FL2VA）",
    "L2VA": "尾帧生视频（L2VA）",
    "Ref2VA": "全参考生成（Ref2VA）",
}

# --------------------------------------------------------------------------
# 字段（顺序即官方顺序，不得重排）
# --------------------------------------------------------------------------
BASE_FIELDS = (
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
)

REF_FIELDS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

BASE_TIMELINE_FIELD = "integrated_multimodal_description"
REF_TIMELINE_FIELD = "detailed_description"

# --------------------------------------------------------------------------
# 对齐指令（必须逐字；base-en.txt §2.1）
# --------------------------------------------------------------------------
I2VA_ALIGNMENT = (
    "For the target video, at 0.00 seconds into the target video, <Picture 1> "
    "(from [Shot 1]) is fully referenced."
)

FL2VA_ALIGNMENT_TEMPLATE = (
    "How the reference pictures align with the target video — Picture 1 (from Shot 1) "
    "aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {final_shot}) "
    "aligns with the {duration:.2f}-second mark of the target video."
)

L2VA_ALIGNMENT_TEMPLATE = (
    "How the reference pictures align with the target video — <Picture 1> (from [Shot {final_shot}]) "
    "aligns with the {duration:.2f}-second mark of the target video."
)


def alignment_instruction(mode: str, duration: int, final_shot: int) -> str | None:
    """返回该模式要求的逐字对齐指令；T2VA / Ref2VA 返回 None。"""
    if mode == "I2VA":
        return I2VA_ALIGNMENT
    if mode == "FL2VA":
        return FL2VA_ALIGNMENT_TEMPLATE.format(final_shot=final_shot, duration=float(duration))
    if mode == "L2VA":
        return L2VA_ALIGNMENT_TEMPLATE.format(final_shot=final_shot, duration=float(duration))
    return None


# --------------------------------------------------------------------------
# 保留关系标记（ref-en.txt §4.1 / §4.2）—— 两类严禁混用
# --------------------------------------------------------------------------
VISUAL_RETENTION_MARKERS = (
    "fully_preserved",
    "partially_preserved",
    "attribute_transfer",
    "weak_reference",
)

AUDIO_RETENTION_MARKERS = (
    "fully_copy",
    "partially_copy",
    "reference",
    "weak_reference",
)

VISUAL_MARKER_LABELS_ZH = {
    "fully_preserved": "完整保留",
    "partially_preserved": "部分保留",
    "attribute_transfer": "属性迁移",
    "weak_reference": "弱参考",
}

AUDIO_MARKER_LABELS_ZH = {
    "fully_copy": "完整复制",
    "partially_copy": "部分复制",
    "reference": "音色/节奏参考",
    "weak_reference": "弱参考",
}

# --------------------------------------------------------------------------
# summary 任务类型前缀（ref-en.txt §3）
# --------------------------------------------------------------------------
TASK_TYPES = (
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
)

TASK_TYPE_LABELS_ZH = {
    "keyframe completion": "关键帧补全",
    "reference generation": "参考生成",
    "video editing": "视频编辑",
    "video continuation": "视频续写",
    "audio reuse": "音频复用",
    "audio reference": "音频参考",
}

# --------------------------------------------------------------------------
# 镜头运动词汇（base-en.txt §4.3）—— 官方英文术语
# --------------------------------------------------------------------------
CAMERA_MOTION_TYPES = (
    "Zoom In", "Zoom Out",
    "Push In", "Pull Out",
    "Pan Left", "Pan Right",
    "Truck Left", "Truck Right",
    "Tilt Up", "Tilt Down",
    "Pedestal Up", "Pedestal Down",
    "Arc Shot", "Tracking Shot", "Static Shot",
    "Shake Slightly", "Shake Strongly",
    "POV",
    "Roll Clockwise", "Roll Counterclockwise",
)

CAMERA_AMPLITUDES = ("with small amplitude", "with large amplitude")
CAMERA_SPEEDS = ("at slow speed", "at fast speed")

CAMERA_MOTION_LABELS_ZH = {
    "Zoom In": "变焦推近",
    "Zoom Out": "变焦拉远",
    "Push In": "机位推近",
    "Pull Out": "机位拉远",
    "Pan Left": "向左摇摄",
    "Pan Right": "向右摇摄",
    "Truck Left": "向左平移",
    "Truck Right": "向右平移",
    "Tilt Up": "向上仰摄",
    "Tilt Down": "向下俯摄",
    "Pedestal Up": "机位上升",
    "Pedestal Down": "机位下降",
    "Arc Shot": "环绕拍摄",
    "Tracking Shot": "跟拍",
    "Static Shot": "固定镜头",
    "Shake Slightly": "轻微晃动",
    "Shake Strongly": "剧烈晃动",
    "POV": "主观视角",
    "Roll Clockwise": "顺时针滚转",
    "Roll Counterclockwise": "逆时针滚转",
}

# 普通剪切连接词（base-en.txt §4.2）
CUT_PHRASES = (
    "the camera cuts to",
    "the shot cuts to",
    "the shot transitions to",
    "the shot changes to",
    "the shot switches to",
)

# --------------------------------------------------------------------------
# 参考标签类型
# --------------------------------------------------------------------------
LABEL_KINDS = ("Subject", "Picture", "Video", "Audio")

LABEL_LABELS_ZH = {
    "Subject": "主体",
    "Picture": "参考图",
    "Video": "参考视频",
    "Audio": "参考音频",
}

# --------------------------------------------------------------------------
# 硬契约数值
# --------------------------------------------------------------------------
MIN_DURATION = 4
MAX_DURATION = 15
MAX_PROMPT_CHARS = 7000

# 第三方交叉印证（B 级，Fantastic 1.8.2 MODE_CAPACITY）：仅作提示，非硬拒
MODE_CAPACITY_HINT = {
    "T2VA": {"Picture": 0, "Video": 0, "Audio": 0},
    "I2VA": {"Picture": 1, "Video": 0, "Audio": 0},
    "FL2VA": {"Picture": 2, "Video": 0, "Audio": 0},
    "L2VA": {"Picture": 1, "Video": 0, "Audio": 0},
    "Ref2VA": {"Picture": 9, "Video": 3, "Audio": 3},
}

# 画外音固定短语（base-en.txt §4.4）
OFFSCREEN_VOICEOVER_PHRASE = "says in an off-screen voiceover"
LIPS_CLOSED_CLAUSE = "while their lips remain completely closed"

# 台词语言标签
DEFAULT_LANGUAGE = "Chinese"
