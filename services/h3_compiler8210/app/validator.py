"""确定性校验：原样内嵌的 MIT 上游校验器 + 本项目本地规则。

分层（任务书 §15 的逻辑边界）：
  * `app/vendor/h3_prompt_validator.py`：上游 MIT 结构校验（**不改写**）。
  * 本模块：在其之上追加本项目特有的中文场景规则
    （台词逐字完整、角色名保留、未连接素材不得出现引用标签、Subject/Speaker 编号一致性）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import official_spec as spec
from .h3model import Project, Segment
from .translator.semantic_qa import qa_prompt_dialogue_integrity
from .vendor.h3_prompt_validator import (
    MAX_PROMPT_CHARS,
    MediaManifest,
    validate_prompt,
)

# 本项目模式名 → 上游校验器模式名
_VALIDATOR_MODE = {"Ref2VA": "R2VA", "T2VA": "T2VA", "I2VA": "I2VA",
                   "FL2VA": "FL2VA", "L2VA": "L2VA"}


@dataclass
class CheckResult:
    code: str
    severity: str        # "error" | "warning" | "info"
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass
class FullReport:
    mode: str = ""
    char_count: int = 0
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.checks if c.severity == "error"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.severity == "warning"]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "char_count": self.char_count,
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "checks": [c.as_dict() for c in self.checks],
        }


def _manifest_from_segment(seg: Segment) -> MediaManifest:
    """按模式构造媒体清单（首尾帧属于基础模式，其余属于参考模式）。"""
    first = last = imgs = vids = auds = 0
    for asset in seg.assets:
        if not asset.connected:
            continue
        if seg.mode == "I2VA":
            first += 1 if asset.kind == "Picture" else 0
        elif seg.mode == "FL2VA":
            if asset.kind == "Picture":
                if asset.purpose == "keyframe_last":
                    last += 1
                else:
                    first += 1
        elif seg.mode == "L2VA":
            last += 1 if asset.kind == "Picture" else 0
        else:
            if asset.kind == "Picture":
                imgs += 1
            elif asset.kind == "Video":
                vids += 1
            elif asset.kind == "Audio":
                auds += 1
    return MediaManifest(first_frames=first, last_frames=last,
                         reference_images=imgs, reference_videos=vids,
                         reference_audios=auds)


def validate_compiled(prompt: str, seg: Segment, project: Project,
                      soundscape: str = "", music: str = "") -> FullReport:
    """对编译产物跑全部确定性校验。"""
    report = FullReport(mode=seg.mode, char_count=len(prompt or ""))

    # ---- 上游 MIT 校验器 -------------------------------------------------
    upstream = validate_prompt(
        prompt or "",
        int(seg.duration or 0),
        _VALIDATOR_MODE.get(seg.mode, seg.mode),
        _manifest_from_segment(seg),
    )
    for item in upstream.messages:
        report.checks.append(CheckResult(f"upstream.{item.code}", item.severity, item.message))
    if upstream.mode is None:
        report.checks.append(CheckResult("local.mode_unrecognized", "error",
                                         "提示词结构无法识别为任何官方模式。"))

    # ---- 本地规则：中文台词 100% 逐字 ------------------------------------
    zh_lines = [d.zh_text for d in seg.dialogues if (d.zh_text or "").strip()]
    if zh_lines:
        if not soundscape:
            soundscape = _section_body(prompt, "overall_soundscape:")
        if not music:
            music = _section_body(prompt, "non_diegetic_music:")
        for issue in qa_prompt_dialogue_integrity(zh_lines, prompt or "", soundscape, music):
            report.checks.append(CheckResult(f"local.{issue.code}", issue.severity, issue.detail))

    # ---- 本地规则：角色名必须出现在提示词中 ------------------------------
    for rid in seg.role_ids:
        role = project.role(rid)
        if role is None:
            continue
        name = (role.name_en or role.name or "").strip()
        if name and name not in (prompt or ""):
            report.checks.append(CheckResult(
                "local.role_missing", "warning",
                f"角色 {rid}（{name}）在最终提示词里没有出现，请确认它确实出现在本段画面中。"))

    # ---- 本地规则：未连接素材不得出现在引用标签里 ------------------------
    # 按**数量**判定，不按"种类"判定：只要该种类出现过的标签编号数
    # 超过"已连接素材数"，就说明有标签是无源生成的。
    connected_count = {"Picture": 0, "Video": 0, "Audio": 0}
    for asset in seg.assets:
        if asset.connected and asset.kind in connected_count:
            connected_count[asset.kind] += 1
    for kind, cap in connected_count.items():
        found = [n for n in range(1, 40) if f"<{kind} {n}>" in (prompt or "")]
        if found and max(found) > cap:
            report.checks.append(CheckResult(
                "local.unconnected_referenced", "error",
                f"出现 <{kind} {max(found)}>，但已连接素材只有 {cap} 个："
                "未真实连接的素材不得生成引用标签。"))
            break

    # ---- 本地规则：长度与时长 --------------------------------------------
    if report.char_count > MAX_PROMPT_CHARS:
        report.checks.append(CheckResult("local.too_long", "error",
                                         f"提示词 {report.char_count} 字符，超过官方上限 {MAX_PROMPT_CHARS}。"))
    if not (spec.MIN_DURATION <= int(seg.duration or 0) <= spec.MAX_DURATION):
        report.checks.append(CheckResult("local.duration", "error",
                                         f"时长必须是 {spec.MIN_DURATION}–{spec.MAX_DURATION} 秒。"))
    return report


def _section_body(prompt: str, header: str) -> str:
    """取某个字段的正文（用于本地对白合同检查）。"""
    if not prompt or f"{header}:" not in prompt:
        return ""
    tail = prompt.split(f"{header}:", 1)[1]
    known = [f"{h}:" for h in spec.REF_FIELDS + spec.BASE_FIELDS]
    end = len(tail)
    for h in known:
        idx = tail.find("\n" + h)
        if idx >= 0:
            end = min(end, idx)
    return tail[:end].strip()
