"""角色与参考数据：永久编号、别名匹配、指代歧义检测。

对应任务书 §6：
  * 角色永久编号 C01…（本地 ID，非 H3 官方标签），一经建立不随出场顺序改变。
  * 按名称与别名做**确定性**匹配；明确对应一个角色时才自动绑定。
  * 出现「她 / 他 / 另一个人」等歧义表达时**必须提示用户选择，不能擅自猜测**。
  * 绝不让第三人的动作误绑定到第一人。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .h3model import Project, Role

# 需要人工消解的指代词
AMBIGUOUS_PRONOUNS = (
    "另一个人", "另一个人物", "其他人", "另外的人",
    "第三人", "第四人", "第五人",
    "那个人", "这个人", "对方", "双方",
    "她们", "他们", "他俩", "她俩",
    "她", "他", "它",
)

# 明确的角色指代（可作为"某个角色"的锚点，但本身不指定是谁）
NUMERIC_ORDINALS = {
    "第一人": 1, "第一个": 1, "第二人": 2, "第二个": 2,
    "第三人": 3, "第三个": 3, "第四人": 4, "第四个": 4,
    "第五人": 5, "第五个": 5,
}


@dataclass
class MatchResult:
    role: Role
    matched_names: list[str]


def match_roles(text: str, project: Project) -> list[MatchResult]:
    """按姓名与别名做确定性匹配，返回命中的角色（按首次出现位置排序）。"""
    text = text or ""
    hits: list[tuple[int, Role, list[str]]] = []
    for role in project.roles:
        names = role.all_names()
        found: list[str] = []
        pos = len(text) + 1
        for name in names:
            idx = text.find(name)
            if idx >= 0:
                found.append(name)
                pos = min(pos, idx)
        if found:
            hits.append((pos, role, found))
    hits.sort(key=lambda x: x[0])
    return [MatchResult(role=r, matched_names=n) for _, r, n in hits]


def detect_ambiguity(text: str, project: Project, segment_role_ids: list[str]) -> list[str]:
    """检测无法确定性归属的指代表达。

    规则（保守，不猜测）：
      * 出现歧义代词，且**本段出场角色数 >= 2** → 列入待确认。
      * 出现"第三人/第四人"等序数词，但本段出场角色数 < 该序号 → 列入待确认。
    """
    text = text or ""
    issues: list[str] = []
    present = len([rid for rid in segment_role_ids if project.role(rid) is not None])

    used: set[str] = set()
    for pronoun in AMBIGUOUS_PRONOUNS:
        if pronoun in text:
            used.add(pronoun)

    if used and present >= 2:
        hit = "、".join(sorted(used, key=len, reverse=True)[:4])
        issues.append(
            f"出现指代词「{hit}」，但本段有 {present} 位出场角色，无法确定指向谁。"
            "请在动作中以角色姓名（或角色编号）明确写明，或使用「动作关系」逐项指定执行者/目标。"
        )

    for word, ordinal in NUMERIC_ORDINALS.items():
        if word in text and present < ordinal:
            issues.append(
                f"动作里写到「{word}」，但本段只有 {present} 位出场角色。"
                "请先添加对应角色，或改用已出场角色的姓名。"
            )
    return issues


def resolve_ordinals(text: str, segment_role_ids: list[str]) -> str:
    """把「第一人/第二人…」按本段出场顺序替换为角色姓名（确定性）。

    仅替换**能确定对应**的序数词；超出出场人数的一律保留原文，交由歧义检测提示。
    """
    if not text:
        return ""
    out = text
    for word, ordinal in sorted(NUMERIC_ORDINALS.items(), key=lambda kv: -len(kv[0])):
        if word in out and len(segment_role_ids) >= ordinal:
            out = out.replace(word, f"「角色{segment_role_ids[ordinal - 1]}」")
    return out


def new_media_id(existing: list[str]) -> str:
    """素材稳定 ID：M01、M02…（不以界面排序为关联依据）。"""
    top = 0
    for mid in existing:
        m = re.match(r"M(\d+)$", mid or "")
        if m:
            top = max(top, int(m.group(1)))
    return f"M{top + 1:02d}"


def new_dialogue_id(existing: list[str]) -> str:
    top = 0
    for did in existing:
        m = re.match(r"D(\d+)$", did or "")
        if m:
            top = max(top, int(m.group(1)))
    return f"D{top + 1:02d}"
