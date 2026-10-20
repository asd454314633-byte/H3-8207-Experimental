"""数据持久化：原子写入、预设、六段工程、历史版本、提示词库、导出。

纪律（任务书 §10）：
  * 稳定 ID 关联，绝不使用"界面排序"作为数据关联依据。
  * 原子写入（临时文件 + os.replace），避免进程异常导致文件损坏。
  * 默认不自动删除历史记录；版本迁移可回滚（schema_version）。
  * 所有产出落在本项目目录内。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import official_spec as spec
from .h3model import Project, ReferencePreset, SCHEMA_VERSION, Segment

try:  # 编译版本号随代码走，写进每个保存产物，便于日后溯源与回滚
    from . import __version__ as COMPILER_VERSION
except ImportError:  # pragma: no cover
    COMPILER_VERSION = "unknown"


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """原子写文本：同目录临时文件 → fsync → os.replace。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def safe_name(text: str, fallback: str = "unnamed") -> str:
    """把用户输入变成安全的文件名（保留中文，剔除路径分隔符与控制字符）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", (text or "").strip())
    cleaned = cleaned.strip(". ")
    return cleaned[:60] or fallback


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
@dataclass
class SavedPrompt:
    id: str
    title: str
    mode: str
    duration: int
    zh_summary: str
    prompt: str
    prompt_sha256: str
    saved_at: str
    source: str          # "compiled" | "manual"
    skill_commit: str
    compiler_version: str


class Store:
    """本地数据仓库。所有路径都在项目根目录之下。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.data = self.root / "data"
        self.history = self.data / "history"
        self.presets = self.data / "presets"
        self.library = self.data / "prompt_library"
        self.exports = self.data / "exports"
        for d in (self.data, self.history, self.presets, self.library, self.exports):
            d.mkdir(parents=True, exist_ok=True)

    # -- 工程 -------------------------------------------------------------
    @property
    def project_file(self) -> Path:
        return self.data / "project.json"

    def load_project(self) -> Project:
        if not self.project_file.exists():
            return self.default_project()
        try:
            raw = json.loads(self.project_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏时保留现场，回退到默认工程（不静默删除用户数据）
            self.backup_corrupt(self.project_file)
            proj = self.default_project()
            proj.name = f"（工程文件损坏，已备份并新建）{exc}"
            return proj
        return self.migrate(Project.from_dict(raw))

    def save_project(self, project: Project) -> None:
        project.schema_version = SCHEMA_VERSION
        project.compiler_version = COMPILER_VERSION
        project.official_skill_commit = spec.OFFICIAL_SKILL_COMMIT
        atomic_write_json(self.project_file, project.to_dict())

    def default_project(self) -> Project:
        proj = Project(name="未命名工程")
        proj.official_skill_commit = spec.OFFICIAL_SKILL_COMMIT
        proj.preset = ReferencePreset()
        proj.add_segment(title="第一段", order=1, mode="Ref2VA", duration=6)
        proj.active_segment_id = proj.segments[0].id
        return proj

    def migrate(self, project: Project) -> Project:
        """版本迁移：低版本补齐字段，永不删除数据。"""
        if project.schema_version < SCHEMA_VERSION:
            project.schema_version = SCHEMA_VERSION
        if not project.segments:
            project.add_segment(title="第一段", order=1, mode="Ref2VA", duration=6)
        if not project.active_segment_id or project.segment(project.active_segment_id) is None:
            project.active_segment_id = project.segments[0].id
        project.official_skill_commit = spec.OFFICIAL_SKILL_COMMIT
        return project

    def backup_corrupt(self, path: Path) -> Path:
        target = path.with_name(f"{path.stem}.corrupt-{timestamp()}{path.suffix}")
        try:
            os.replace(path, target)
        except OSError:
            pass
        return target

    # -- 历史版本 ---------------------------------------------------------
    def save_version(self, project: Project, label: str = "") -> str:
        name = f"{timestamp()}-{safe_name(label, '版本')}.json"
        atomic_write_json(self.history / name, {
            "saved_at": datetime.now().astimezone().isoformat(),
            "label": label,
            "schema_version": SCHEMA_VERSION,
            "official_skill_commit": spec.OFFICIAL_SKILL_COMMIT,
            "project": project.to_dict(),
        })
        return name

    def list_versions(self) -> list[dict[str, Any]]:
        out = []
        for f in sorted(self.history.glob("*.json"), reverse=True):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            out.append({
                "file": f.name,
                "saved_at": raw.get("saved_at", ""),
                "label": raw.get("label", ""),
                "schema_version": raw.get("schema_version", 0),
                "skill_commit": raw.get("official_skill_commit", ""),
                "size": f.stat().st_size,
            })
        return out

    def load_version(self, filename: str) -> Project:
        path = self.history / safe_name(filename, "")
        if not path.exists() or path.suffix != ".json":
            raise FileNotFoundError(f"找不到历史版本：{filename}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return self.migrate(Project.from_dict(raw.get("project", {})))

    # -- 参考预设 ---------------------------------------------------------
    def save_preset(self, preset: ReferencePreset) -> str:
        name = safe_name(preset.name, "默认参考预设")
        atomic_write_json(self.presets / f"{name}.json", asdict(preset))
        return name

    def list_presets(self) -> list[str]:
        return sorted(p.stem for p in self.presets.glob("*.json"))

    def load_preset(self, name: str) -> ReferencePreset:
        path = self.presets / f"{safe_name(name)}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ReferencePreset(**{k: v for k, v in raw.items()
                                  if k in ReferencePreset.__dataclass_fields__})

    def delete_preset(self, name: str) -> bool:
        path = self.presets / f"{safe_name(name)}.json"
        if path.exists():
            # 只移入回收目录，不物理删除（默认不自动删除用户数据）
            trash = self.data / "presets_deleted"
            trash.mkdir(exist_ok=True)
            os.replace(path, trash / f"{path.stem}-{timestamp()}.json")
            return True
        return False

    # -- 提示词库 ---------------------------------------------------------
    def save_prompt(self, item: SavedPrompt) -> str:
        atomic_write_json(self.library / f"{safe_name(item.id, 'P')}.json", asdict(item))
        return item.id

    def list_prompts(self, query: str = "") -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        out: list[dict[str, Any]] = []
        for f in sorted(self.library.glob("*.json"), reverse=True):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if q and q not in json.dumps(raw, ensure_ascii=False).lower():
                continue
            out.append({
                "id": raw.get("id", f.stem),
                "title": raw.get("title", ""),
                "mode": raw.get("mode", ""),
                "duration": raw.get("duration", 0),
                "zh_summary": raw.get("zh_summary", ""),
                "saved_at": raw.get("saved_at", ""),
                "source": raw.get("source", ""),
                "prompt_sha256": raw.get("prompt_sha256", ""),
                "chars": len(raw.get("prompt", "")),
            })
        return out

    def load_prompt(self, prompt_id: str) -> dict[str, Any]:
        path = self.library / f"{safe_name(prompt_id, '')}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # -- 导出 -------------------------------------------------------------
    def export(self, project: Project, segment: Segment, prompt: str,
               suffix: str = "") -> Path:
        tag = f"{safe_name(project.name, '工程')}_{safe_name(segment.title or segment.id, '段')}"
        tag += f"_{timestamp()}{suffix}"
        json_path = self.exports / f"{tag}.json"
        txt_path = self.exports / f"{tag}.txt"
        atomic_write_json(json_path, {
            "exported_at": datetime.now().astimezone().isoformat(),
            "official_skill_commit": spec.OFFICIAL_SKILL_COMMIT,
            "compiler_version": project.compiler_version,
            "project_name": project.name,
            # 用 asdict 深转换：Segment 里含 Dialogue/Shot/MediaAsset，
            # Role 里含 VoiceProfile，直接 __dict__ 无法 JSON 序列化。
            "segment": asdict(segment),
            "preset": asdict(project.preset),
            "roles": [asdict(r) for r in project.roles],
            "final_prompt": prompt,
        })
        atomic_write_text(txt_path, prompt)
        return txt_path
