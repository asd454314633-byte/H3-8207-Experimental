"""本地 HTTP 服务（stdlib，仅监听 127.0.0.1，不向局域网/公网开放）。

纪律：
  * 不占用 8096 / 8193 / 8197 / 8207 等既有端口（默认 8210，可配置）。
  * 不加载任何 GPU 模型；提示词编译与翻译全部在 CPU 完成。
  * 只读写本项目目录内的文件。
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import official_spec as spec
from . import storage as store_mod
from . import translator
from .compiler import compile_segment
from .h3model import Dialogue, MediaAsset, Project, ReferencePreset, Role, Segment, VoiceProfile
from .roles import detect_ambiguity, new_dialogue_id, new_media_id
from .storage import SavedPrompt, Store
from .validator import validate_compiled

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
STORE = Store(ROOT)
# 用 RLock：所有**写路径**（load → 改字段 → save）必须串行，
# 否则两个并发请求会各自基于旧快照保存，后写者把先写者的修改覆盖掉
# （本机实测到：先改 action_zh 再立刻改 mode，action 会被回滚）。
_LOCK = threading.RLock()
PERF: list[float] = []          # 编译+翻译耗时记录（秒）


# ---------------------------------------------------------------------------
def _project() -> Project:
    return STORE.load_project()


def _save(project: Project) -> None:
    STORE.save_project(project)


def _locked(fn: Any) -> Any:
    """把「读工程 → 改 → 写回」整段放进同一把锁，消除丢更新竞态。"""
    def wrapper(data: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            return fn(data)
    wrapper.__name__ = getattr(fn, "__name__", "handler")
    return wrapper


def _segment_or_404(project: Project, seg_id: str) -> Segment:
    seg = project.segment(seg_id)
    if seg is None:
        raise KeyError(f"找不到段：{seg_id}")
    return seg


def _apply_segment(seg: Segment, data: dict[str, Any]) -> None:
    """把前端提交的字段写回段对象（只接受已知字段）。"""
    simple = ("title", "mode", "style", "scene_zh", "action_zh", "camera_zh",
              "soundscape_zh", "music_zh", "extra_zh", "inherit_prev_end_state",
              "final_edited_prompt")
    for key in simple:
        if key in data:
            setattr(seg, key, data[key])
    if "duration" in data:
        try:
            seg.duration = int(data["duration"])
        except (TypeError, ValueError):
            pass
    if "role_ids" in data:
        seg.role_ids = [str(x) for x in data["role_ids"]]
    if "task_types" in data:
        seg.task_types = [str(x) for x in data["task_types"]]
    if "retention" in data and isinstance(data["retention"], dict):
        seg.retention = {str(k): str(v) for k, v in data["retention"].items()}
    if "relations" in data and isinstance(data["relations"], list):
        rows = []
        for raw in data["relations"]:
            raw = dict(raw or {})
            rows.append({
                "actor": str(raw.get("actor", "")),
                "target": str(raw.get("target", "")),
                "position": str(raw.get("position", "")),
                "action": str(raw.get("action", "")),
            })
        seg.relations = rows

    if "dialogues" in data:
        rows = []
        for raw in data["dialogues"]:
            raw = dict(raw)
            rows.append(Dialogue(**{k: raw.get(k, "")
                                    for k in Dialogue.__dataclass_fields__
                                    if k not in ("shot_index", "group")}
                                 | {"shot_index": int(raw.get("shot_index", 1) or 1),
                                    "group": str(raw.get("group", ""))}))
        seg.dialogues = rows

    if "assets" in data:
        rows = []
        for raw in data["assets"]:
            raw = dict(raw)
            rows.append(MediaAsset(
                id=str(raw.get("id") or new_media_id([a.id for a in rows])),
                kind=str(raw.get("kind", "Picture")),
                label=str(raw.get("label", "")),
                connected=bool(raw.get("connected", False)),
                role_id=str(raw.get("role_id", "")),
                purpose=str(raw.get("purpose", "")),
                note=str(raw.get("note", "")),
            ))
        seg.assets = rows

    if "shots" in data:
        from .h3model import Shot
        rows = []
        for i, raw in enumerate(data["shots"], start=1):
            raw = dict(raw)
            at = raw.get("at_seconds")
            rows.append(Shot(
                index=int(raw.get("index", i) or i),
                at_seconds=(None if at in ("", None) else float(at)),
                zh_content=str(raw.get("zh_content", "")),
                camera_zh=str(raw.get("camera_zh", "")),
                camera_motion=str(raw.get("camera_motion", "")),
                camera_amplitude=str(raw.get("camera_amplitude", "")),
                camera_speed=str(raw.get("camera_speed", "")),
            ))
        seg.shots = rows


# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "H3CNPromptCompiler/1.0"

    # -- 基础设施 ---------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        if os.environ.get("H3CN_VERBOSE"):
            print(f"[{datetime.now():%H:%M:%S}] {fmt % args}")

    def _same_authority(self) -> bool:
        """只接受来自本机回环地址的请求（不向局域网/公网开放）。"""
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"ok": False, "error": "文件不存在"}, 404)
            return
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"请求体不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    # -- 路由 -------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if not self._same_authority():
            self._send_json({"ok": False, "error": "仅允许本机访问"}, 403)
            return
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if route in ("/", "/index.html"):
                self._send_file(WEB_DIR / "index.html")
            elif route.startswith("/static/"):
                rel = route[len("/static/"):]
                target = (WEB_DIR / rel).resolve()
                if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
                    self._send_json({"ok": False, "error": "非法路径"}, 403)
                    return
                self._send_file(target)
            elif route == "/api/state":
                self._send_json(self._state())
            elif route == "/api/prompts":
                q = (query.get("q") or [""])[0]
                self._send_json({"ok": True, "items": STORE.list_prompts(q)})
            elif route == "/api/versions":
                self._send_json({"ok": True, "items": STORE.list_versions()})
            elif route == "/api/health":
                self._send_json({"ok": True, "time": datetime.now().isoformat()})
            elif route == "/favicon.ico":
                # 明确返回 204，避免浏览器在控制台刷 404 噪音
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self._send_json({"ok": False, "error": f"未知路径 {route}"}, 404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        if not self._same_authority():
            self._send_json({"ok": False, "error": "仅允许本机访问"}, 403)
            return
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/")
        try:
            data = self._read_json()
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)
            return
        try:
            handler = _ROUTES.get(route)
            if handler is None:
                self._send_json({"ok": False, "error": f"未知接口 {route}"}, 404)
                return
            self._send_json(handler(data))
        except KeyError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    # -- 状态 -------------------------------------------------------------
    def _state(self) -> dict[str, Any]:
        project = _project()
        return {
            "ok": True,
            "project": project.to_dict(),
            "translation": translator.provider_status(),
            "spec": {
                "official_skill_commit": spec.OFFICIAL_SKILL_COMMIT,
                "official_skill_repo": spec.OFFICIAL_SKILL_REPO,
                "modes": list(spec.ALL_MODES),
                "mode_labels": spec.MODE_LABELS_ZH,
                "base_fields": list(spec.BASE_FIELDS),
                "ref_fields": list(spec.REF_FIELDS),
                "camera_motions": list(spec.CAMERA_MOTION_TYPES),
                "camera_labels": spec.CAMERA_MOTION_LABELS_ZH,
                "task_types": list(spec.TASK_TYPES),
                "task_type_labels": spec.TASK_TYPE_LABELS_ZH,
                "visual_markers": list(spec.VISUAL_RETENTION_MARKERS),
                "visual_marker_labels": spec.VISUAL_MARKER_LABELS_ZH,
                "audio_markers": list(spec.AUDIO_RETENTION_MARKERS),
                "audio_marker_labels": spec.AUDIO_MARKER_LABELS_ZH,
                "min_duration": spec.MIN_DURATION,
                "max_duration": spec.MAX_DURATION,
                "max_chars": spec.MAX_PROMPT_CHARS,
            },
            "presets": STORE.list_presets(),
            "perf": _perf_summary(),
        }


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------
def api_project_save(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    if "name" in data:
        project.name = str(data["name"])
    _save(project)
    return {"ok": True, "project": project.to_dict()}


def api_role_add(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    role = project.add_role(str(data.get("name", "")))
    if data.get("name_en"):
        role.name_en = str(data["name_en"])
    _save(project)
    return {"ok": True, "role": asdict(role), "project": project.to_dict()}


def api_role_update(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    role = project.role(str(data.get("id", "")))
    if role is None:
        raise KeyError(f"找不到角色：{data.get('id')}")
    for key in ("name", "name_en", "appearance", "face_ref", "body_ref", "audio_ref"):
        if key in data:
            setattr(role, key, str(data[key]))
    if "aliases" in data:
        role.aliases = [str(x) for x in data["aliases"]]
    if "states" in data:
        role.states = [str(x) for x in data["states"]]
    if "default_voice" in data and isinstance(data["default_voice"], dict):
        role.default_voice = VoiceProfile(**{
            k: str(v) for k, v in data["default_voice"].items()
            if k in VoiceProfile.__dataclass_fields__})
    _save(project)
    return {"ok": True, "role": asdict(role), "project": project.to_dict()}


def api_role_delete(data: dict[str, Any]) -> dict[str, Any]:
    """从角色库彻底删除（会同时从各段出场名单移除）。"""
    project = _project()
    ok = project.remove_role(str(data.get("id", "")))
    _save(project)
    return {"ok": ok, "project": project.to_dict()}


def api_segment_add(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    seg = project.add_segment(title=str(data.get("title") or f"第{len(project.segments) + 1}段"),
                              order=len(project.segments) + 1,
                              mode=str(data.get("mode", "Ref2VA")),
                              duration=int(data.get("duration", 6) or 6))
    if project.segments:
        prev = project.segments[-2]
        seg.role_ids = list(prev.role_ids)
    project.active_segment_id = seg.id
    _save(project)
    return {"ok": True, "segment": asdict(seg), "project": project.to_dict()}


def api_segment_update(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    seg = _segment_or_404(project, str(data.get("id", "")))
    _apply_segment(seg, data)
    # 人工编辑后，旧校验状态立即失效（任务书 §5-D）
    if "final_edited_prompt" in data:
        import hashlib
        seg.final_edited_sha256 = hashlib.sha256(
            (seg.final_edited_prompt or "").encode("utf-8")).hexdigest().upper()
        seg.compiled_valid = False
        seg.compile_warnings = []
        seg.compile_errors = []
    _save(project)
    return {"ok": True, "segment": asdict(seg), "project": project.to_dict()}


def api_segment_delete(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    sid = str(data.get("id", ""))
    if len(project.segments) <= 1:
        return {"ok": False, "error": "至少要保留一段。"}
    project.segments = [s for s in project.segments if s.id != sid]
    for i, s in enumerate(project.segments, start=1):
        s.order = i
    if project.active_segment_id == sid:
        project.active_segment_id = project.segments[0].id
    _save(project)
    return {"ok": True, "project": project.to_dict()}


def api_segment_select(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    _segment_or_404(project, str(data.get("id", "")))
    project.active_segment_id = str(data["id"])
    _save(project)
    return {"ok": True, "project": project.to_dict()}


def api_preset_save(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    payload = data.get("preset") or {}
    project.preset = ReferencePreset(**{
        k: str(v) for k, v in payload.items()
        if k in ReferencePreset.__dataclass_fields__})
    name = STORE.save_preset(project.preset)
    _save(project)
    return {"ok": True, "name": name, "presets": STORE.list_presets()}


def api_preset_apply(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    preset = STORE.load_preset(str(data.get("name", "")))
    project.preset = preset
    _save(project)
    return {"ok": True, "preset": asdict(preset), "project": project.to_dict()}


def api_preset_delete(data: dict[str, Any]) -> dict[str, Any]:
    ok = STORE.delete_preset(str(data.get("name", "")))
    return {"ok": ok, "presets": STORE.list_presets()}


def api_compile(data: dict[str, Any]) -> dict[str, Any]:
    """编译一段。返回完整提示词 + 确定性校验 + 性能数据。"""
    project = _project()
    seg_id = str(data.get("id") or project.active_segment_id)
    seg = _segment_or_404(project, seg_id)
    if data:
        _apply_segment(seg, {k: v for k, v in data.items() if k != "id"})

    t0 = time.perf_counter()
    with _LOCK:
        result = compile_segment(seg, project)
    elapsed = time.perf_counter() - t0
    PERF.append(elapsed)

    report = validate_compiled(result.prompt, seg, project) if result.ok else None

    # 人工编辑优先：最终文本以下面这个字段为准（任务书 §5-D）
    final_text = (seg.final_edited_prompt or "").strip() or result.prompt
    # 编译失败时**不要清空上一次成功的提示词**（否则用户改错一个字段就丢掉已有成果）；
    # 只在成功时覆盖，失败时保留旧值并在错误区提示。
    if result.ok:
        seg.compiled_prompt = result.prompt
        import hashlib
        seg.compiled_sha256 = hashlib.sha256(result.prompt.encode("utf-8")).hexdigest().upper()
    seg.compile_errors = list(result.errors)
    seg.compile_warnings = list(result.warnings) + (
        [c.message for c in report.warnings] if report else [])
    seg.compiled_valid = bool(report and report.valid) and result.ok
    _save(project)

    return {
        "ok": result.ok,
        "segment_id": seg.id,
        "prompt": result.prompt,
        "final_prompt": final_text,
        "edited": bool((seg.final_edited_prompt or "").strip()),
        "errors": result.errors,
        "warnings": result.warnings,
        "ambiguous": detect_ambiguity(seg.action_zh, project, seg.role_ids),
        "meta": {k: v for k, v in result.meta.items() if k != "references"}
        | {"references": {k: v for k, v in (result.meta.get("references") or {}).items()}},
        "report": report.as_dict() if report else None,
        "elapsed_sec": round(elapsed, 3),
        "perf": _perf_summary(),
    }


def api_validate(data: dict[str, Any]) -> dict[str, Any]:
    """对任意文本（含人工编辑后的文本）跑确定性校验。"""
    project = _project()
    seg = _segment_or_404(project, str(data.get("id") or project.active_segment_id))
    prompt = str(data.get("prompt", "")) or seg.compiled_prompt
    report = validate_compiled(prompt, seg, project)
    return {"ok": True, "report": report.as_dict()}


def api_translate(data: dict[str, Any]) -> dict[str, Any]:
    """单字段翻译预览（供界面即时查看英文）。"""
    text = str(data.get("text", ""))
    try:
        out = translator.translate_zh_to_en(text)
        issues = [i.__dict__ for i in translator.qa_pair(text, out)]
        return {"ok": True, "en": out, "issues": issues}
    except translator.TranslationUnavailable as exc:
        return {"ok": False, "error": f"翻译引擎不可用：{exc}", "en": ""}


def api_prompt_save(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    seg = _segment_or_404(project, str(data.get("id") or project.active_segment_id))
    prompt = str(data.get("prompt", "")).strip() or seg.compiled_prompt
    if not prompt:
        return {"ok": False, "error": "没有可保存的提示词。"}
    import hashlib
    pid = str(data.get("prompt_id") or f"P-{store_mod.timestamp()}")
    item = SavedPrompt(
        id=pid,
        title=str(data.get("title") or f"{project.name}·{seg.title or seg.id}"),
        mode=seg.mode,
        duration=int(seg.duration),
        zh_summary=seg.action_zh,
        prompt=prompt,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper(),
        saved_at=datetime.now().astimezone().isoformat(),
        source="manual" if (seg.final_edited_prompt or "").strip() else "compiled",
        skill_commit=spec.OFFICIAL_SKILL_COMMIT,
        compiler_version=project.compiler_version,
    )
    STORE.save_prompt(item)
    return {"ok": True, "id": pid, "items": STORE.list_prompts()}


def api_prompt_load(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "item": STORE.load_prompt(str(data.get("prompt_id", "")))}


def api_version_save(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    name = STORE.save_version(project, str(data.get("label", "")))
    return {"ok": True, "file": name, "items": STORE.list_versions()}


def api_version_load(data: dict[str, Any]) -> dict[str, Any]:
    project = STORE.load_version(str(data.get("file", "")))
    STORE.save_project(project)
    return {"ok": True, "project": project.to_dict()}


def api_export(data: dict[str, Any]) -> dict[str, Any]:
    project = _project()
    seg = _segment_or_404(project, str(data.get("id") or project.active_segment_id))
    prompt = str(data.get("prompt", "")).strip() or seg.compiled_prompt
    path = STORE.export(project, seg, prompt, str(data.get("suffix", "")))
    return {"ok": True, "path": str(path)}


def api_translation_reset(data: dict[str, Any]) -> dict[str, Any]:
    translator.clear_cache()
    PERF.clear()
    return {"ok": True, "translation": translator.provider_status(), "perf": _perf_summary()}


def _perf_summary() -> dict[str, Any]:
    if not PERF:
        return {"samples": 0}
    vals = sorted(PERF)
    n = len(vals)

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return round(vals[idx], 3)

    return {
        "samples": n,
        "avg_sec": round(sum(vals) / n, 3),
        "p50_sec": pct(0.50),
        "p95_sec": pct(0.95),
        "max_sec": round(vals[-1], 3),
        "min_sec": round(vals[0], 3),
    }


_MUTATING = {
    "/api/project", "/api/project/save",
    "/api/role/add", "/api/role/update", "/api/role/delete",
    "/api/segment/add", "/api/segment/update", "/api/segment/delete",
    "/api/segment/select", "/api/preset/save", "/api/preset/apply",
    "/api/preset/delete", "/api/compile", "/api/prompt/save",
    "/api/version/save", "/api/version/load", "/api/export",
    "/api/translation/reset",
}

_ROUTES: dict[str, Any] = {
    "/api/project": api_project_save,
    "/api/project/save": api_project_save,
    "/api/role/add": api_role_add,
    "/api/role/update": api_role_update,
    "/api/role/delete": api_role_delete,
    "/api/segment/add": api_segment_add,
    "/api/segment/update": api_segment_update,
    "/api/segment/delete": api_segment_delete,
    "/api/segment/select": api_segment_select,
    "/api/preset/save": api_preset_save,
    "/api/preset/apply": api_preset_apply,
    "/api/preset/delete": api_preset_delete,
    "/api/compile": api_compile,
    "/api/validate": api_validate,
    "/api/translate": api_translate,
    "/api/prompt/save": api_prompt_save,
    "/api/prompt/load": api_prompt_load,
    "/api/version/save": api_version_save,
    "/api/version/load": api_version_load,
    "/api/export": api_export,
    "/api/translation/reset": api_translation_reset,
}
# 所有会改数据的接口统一加锁（/api/validate、/api/translate、/api/prompt/load 是只读，无需加锁）
_ROUTES = {path: (_locked(fn) if path in _MUTATING else fn)
           for path, fn in _ROUTES.items()}


class Server(ThreadingHTTPServer):
    """本地服务。

    **关闭地址复用**：Windows 的 SO_REUSEADDR 语义允许两个进程同时监听同一端口，
    会出现"第二次启动看似成功、请求却被旧进程接走"的隐蔽故障（本机实测到过）——
    表现为改了代码却仍然跑旧逻辑。这里改为 fail-closed：端口被占用就直接报错退出。
    """

    allow_reuse_address = False
    daemon_threads = True


def _pid_file() -> Path:
    return ROOT / "data" / "server.pid"


def _write_pid(port: int) -> None:
    try:
        _pid_file().parent.mkdir(parents=True, exist_ok=True)
        _pid_file().write_text(f"{os.getpid()}\n{port}\n", encoding="utf-8")
    except OSError:
        pass


def _clear_pid() -> None:
    try:
        _pid_file().unlink()
    except OSError:
        pass


def run(host: str = "127.0.0.1", port: int = 8210) -> None:
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("安全限制：只能监听本机回环地址 127.0.0.1")
    try:
        httpd = Server((host, port), Handler)
    except OSError as exc:
        raise SystemExit(
            f"启动失败：端口 {port} 已被占用（{exc}）。\n"
            f"请先运行 stop.ps1 停止本项目的服务，或改用其它端口： start.ps1 -Port 8211"
        ) from exc
    _write_pid(port)
    print("=" * 68)
    print("  H3 官方中文提示词编译器 V1")
    print(f"  已在运行： http://{host}:{port}/")
    print(f"  项目目录： {ROOT}")
    print(f"  官方规范： {spec.OFFICIAL_SKILL_REPO} @ {spec.OFFICIAL_SKILL_COMMIT[:12]}")
    status = translator.provider_status()
    print(f"  翻译引擎： {status['provider']}  可用={status['available']}")
    print("  按 Ctrl+C 停止")
    print("=" * 68)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止……")
    finally:
        httpd.server_close()
        _clear_pid()


if __name__ == "__main__":
    import sys
    run(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8210)
