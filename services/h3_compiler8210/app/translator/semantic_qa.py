"""翻译语义 QA：对已知高风险类别做确定性复检。

任务书 §9.3 明确禁止"将语义明显错误的翻译标记为 PASS"。
本模块不猜测、不润色，只做**可判定的**一致性断言，把问题暴露出来交给用户确认。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import glossary


@dataclass
class QaIssue:
    code: str
    severity: str      # "error" | "warning"
    detail: str


_LEFT_RIGHT = [
    (re.compile(r"左"), re.compile(r"\bleft\b", re.I), "左 → left"),
    (re.compile(r"右"), re.compile(r"\bright\b", re.I), "右 → right"),
]
_FORWARD_BACK = [
    (re.compile(r"向前|前方|前移"), re.compile(r"\b(ahead|forward|front)\b", re.I), "前 → ahead/forward"),
    (re.compile(r"向后|后方|后退"), re.compile(r"\b(behind|backward|back)\b", re.I), "后 → behind/backward"),
]
_NEGATION = re.compile(r"不|没|别|禁止|勿")
_NEGATION_EN = re.compile(r"\b(not|no|never|without|doesn't|don't|didn't|cannot|can't|must not)\b", re.I)
_UP_DOWN = [
    (re.compile(r"站起|起身|站起来"), re.compile(r"\b(stand|stands|standing|stood up|rises|gets up)\b", re.I),
     "站起 → stand up"),
    (re.compile(r"坐下|坐回|坐下来"), re.compile(r"\b(sit|sits|sitting|sat)\b", re.I), "坐下 → sit down"),
]
_TURN = [
    (re.compile(r"转身"), re.compile(r"\bturns?\b", re.I), "转身 → turn"),
    (re.compile(r"回头"), re.compile(r"\b(looks? back|glances back|over (his|her|their) shoulder)\b", re.I),
     "回头 → look back"),
]


def qa_pair(zh: str, en: str) -> list[QaIssue]:
    """对一条中文原文与其英文译文做确定性一致性检查。"""
    issues: list[QaIssue] = []
    zh = zh or ""
    en = en or ""

    for pat_zh, pat_en, label in _LEFT_RIGHT + _FORWARD_BACK:
        if pat_zh.search(zh) and not pat_en.search(en):
            issues.append(QaIssue("direction_missing", "error",
                                  f"方向语义未在译文中体现：{label}｜中文：{zh}｜译文：{en}"))

    if _NEGATION.search(zh) and not _NEGATION_EN.search(en):
        issues.append(QaIssue("negation_missing", "error",
                              f"否定语义未在译文中体现｜中文：{zh}｜译文：{en}"))

    for pat_zh, pat_en, label in _UP_DOWN + _TURN:
        if pat_zh.search(zh) and not pat_en.search(en):
            issues.append(QaIssue("action_missing", "error",
                                  f"动作语义未在译文中体现：{label}｜中文：{zh}｜译文：{en}"))

    # 官方镜头词汇：用户写了镜头运动时，译文应使用官方英文术语
    zh_cam = [z for z in glossary.CAMERA_TERMS if z in zh]
    if zh_cam:
        if not any(w.lower() in en.lower() for w in glossary.OFFICIAL_CAMERA_WORDS):
            issues.append(QaIssue("camera_vocabulary", "warning",
                                  f"镜头运动建议使用官方词汇（当前译文未命中任何官方术语）"
                                  f"｜中文：{zh}｜译文：{en}"))
    return issues


# ---------------------------------------------------------------------------
# 提示词级检查
# ---------------------------------------------------------------------------
def qa_prompt_dialogue_integrity(zh_dialogues: list[str], prompt: str,
                                 soundscape: str = "", music: str = "") -> list[QaIssue]:
    """台词完整性：中文原文必须 100% 逐字出现在详细描述里，且不得出现在音频段。"""
    issues: list[QaIssue] = []
    for zh in zh_dialogues:
        text = (zh or "").strip()
        if not text:
            continue
        if text not in prompt:
            issues.append(QaIssue("dialogue_verbatim", "error",
                                  f"中文台词未逐字出现在最终提示词中：{text}"))
        if text in soundscape:
            issues.append(QaIssue("dialogue_in_soundscape", "error",
                                  f"台词出现在 overall_soundscape，违反官方对白合同：{text}"))
        if text in music:
            issues.append(QaIssue("dialogue_in_music", "error",
                                  f"台词出现在 non_diegetic_music，违反官方对白合同：{text}"))
    # <d> 事件数必须等于台词条数
    d_blocks = re.findall(r"<d>.*?</d>", prompt, re.DOTALL)
    expected = len([z for z in zh_dialogues if (z or "").strip()])
    if len(d_blocks) != expected:
        issues.append(QaIssue("dialogue_event_count", "error",
                              f"<d> 台词块数 {len(d_blocks)} 与台词条数 {expected} 不一致。"))
    return issues
