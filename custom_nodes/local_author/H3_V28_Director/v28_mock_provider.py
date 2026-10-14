"""V28 Director - an offline stand-in provider (task section 37).

Why this exists: sections 20-31 (status machine, accept / re-roll / edit, the
Motion Context indices, the Chinese UI) are pure logic and must be testable
without ever loading a 27B model onto the GPU. The mock returns deterministic,
schema-valid objects so the whole chain - including the task-31 gate and the
task-34 repair loop - can be exercised with zero generation quota spent.

Guarantees this module makes:
  * no network, no subprocess, no GPU, no model load;
  * same object shapes and the same validation path as the real provider, so a
    test that passes here is meaningful for Bonsai;
  * `name = "mock"` keeps it out of the way: the default provider stays bonsai2.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import v28_paths as P
from . import v28_prompt_compiler as PC
from . import v28_provider as V
from . import v28_schemas as S
from . import v28_runtime_contract as RC

_MOCK_PROFILE_TOPICS = ["未来运动方向", "不可见身体结构", "剧情意图", "画外空间几何"]


def _runtime_contract() -> RC.DirectorProviderRuntimeContract:
    return RC.DirectorProviderRuntimeContract(
        provider_name="mock", process_identity={"pid": None, "in_process": True},
        server_endpoint="(in-process)", model_alias="mock-director",
        cuda_backend_loaded=False, gpu_layers_requested=False,
        gpu_compute_confirmed=False, cpu_dominant=False, offload_confirmed=False,
        resident=False, released=True)


RC.register_runtime("mock", _runtime_contract, lambda: None)


def _h(text: str, n: int = 6) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:n]


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[。！!?\n]+", str(text or "")) if p.strip()]
    return parts


@V.register
class MockDirectorProvider(V.DirectorProvider):
    name = "mock"
    SUPPORTS_VISION = True
    LABEL = "离线模拟导演（不占显存、不消耗生成额度）"

    def __init__(self) -> None:
        self._running = False
        self.calls: list[str] = []

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def health(self) -> V.Health:
        return V.Health(ok=self._running, provider=self.name, running=self._running,
                        detail=("模拟导演在线" if self._running
                                else "模拟导演未启动（先调用 start）"),
                        model="mock-director", vision=True, endpoint="(in-process)",
                        extra={"note": "no GPU, no network"})

    # -- never used: the mock builds objects directly ----------------------
    def _complete(self, messages: list[dict], *, max_tokens: int,
                  timeout_s: float, temperature: float) -> str:
        raise V.DirectorUnavailable("mock provider 不做文本补全")

    # -- the three director operations -------------------------------------
    def analyze_references(self, images: list[dict], *, brief: str = "") -> dict:
        if not self._running:
            raise V.DirectorUnavailable("模拟导演未启动")
        self.calls.append("analyze_references")
        pics: list[dict] = []
        subjects: list[dict] = []
        for i, im in enumerate(images[:4], start=1):
            name = str(im.get("name") or im.get("filename") or f"ref_{i}.png")
            pics.append({"index": i, "filename": name,
                         "width": int(im.get("width") or 0),
                         "height": int(im.get("height") or 0)})
            stem = re.sub(r"\.[A-Za-z0-9]+$", "", name)
            subjects.append({
                "id": f"sub_{i}_{_h(name)}",
                "picture_refs": [i],
                "role": "参考素材主体",
                "seen": {
                    "hair": "",
                    "glasses": "",
                    "wardrobe": {},
                    "distinctive_appearance": [f"文件 {name} 中可见的主体轮廓与配色"],
                    "visible_pose": {"shot": "整张画面", "facing": "未判定"},
                },
                "inferred": {"possible_subject": stem[:60]},
                "do_not_infer": list(_MOCK_PROFILE_TOPICS),
            })
        return {
            "version": S.SCHEMA_VERSION,
            "source_pictures": pics,
            "subjects": subjects,
            "scene": {"seen": {"summary": "（模拟）未在离线模式下读取像素内容"},
                      "inferred": {}},
            "props": [],
            "composition": {"seen": {"framing": "（模拟）按原图构图"}, "inferred": {}},
            "uncertain": ["离线模拟模式不分析图像内容，所有外观字段均为占位"],
            "not_answerable": list(_MOCK_PROFILE_TOPICS),
        }

    def plan_story(self, *, story_goal: str, profile: dict, total_seconds: float,
                   segment_seconds: float, style: str = "auto",
                   continuation_mode: str = "same_shot",
                   expect_segments: int | None = None) -> dict:
        if not self._running:
            raise V.DirectorUnavailable("模拟导演未启动")
        self.calls.append("plan_story")
        seg = max(1.0, float(segment_seconds or 8))
        total = max(seg, float(total_seconds or seg))
        n = int(expect_segments or len(C.build_segment_skeleton(total, seg)))
        n = max(1, min(n, 12))
        beats = _sentences(story_goal)
        pics = PC.picture_labels(profile)
        # picture_labels() yields {"index", "filename"} - the H3 label is derived
        # from the index, never stored, so it can never drift from the profile.
        labels = [f"<Picture {p.get('index')}>" for p in pics] or ["<Picture 1>"]
        segs: list[dict] = []
        for i in range(1, n + 1):
            zh = beats[(i - 1) % len(beats)] if beats else f"第 {i} 段推进一个动作"
            subject = labels[(i - 1) % len(labels)]
            segs.append({
                "id": i,
                "beat": f"{zh}（模拟第 {i} 段）"[:400],
                "start_state": {"position": f"承接第 {i - 1} 段结尾" if i > 1 else "画面起始位置",
                                "camera": "中景", "action": "静止站立"},
                "end_state": {"position": "原地略移动", "camera": "中景",
                              "action": "完成本段主动作并保持住"},
                "directives": ({"tail": "ongoing"} if i == 1 else
                               {"join": "continuous", "camera": "hold",
                                "framing": "keep", "pace": "steady", "tail": "ongoing"}),
                "prompt": (f"{subject} stays exactly as referenced while one clear action "
                           f"unfolds in front of it, and the frame settles on the result "
                           f"of that action before the clip ends." if continuation_mode == "same_shot"
                           else f"The shot cuts to a wider view of {subject}, one clear "
                                f"action unfolds, and the frame settles before the clip ends."),
                "duration": seg,
                "seed": None,
                "locked": False,
                "segment_objective": f"推进第 {i} 段的可见动作",
                "beats": [f"动作开始：{zh}", "动作发展并到达明确的新状态"],
                "new_action": f"{zh}，动作有开始、发展和结果",
                "performance": "自然且可观察的身体反应",
                "blocking": "主体位置和朝向连续",
                "interaction": "按用户剧情维持互动关系",
                "camera": "镜头按动作意图重新构图",
                "reference_usage": [], "dialogue": "", "dialogue_timing": "无台词",
                "ambience": "环境底噪", "physical_sounds": "动作对应的物理声",
                "non_verbal_vocals": "自然呼吸", "music": "",
                "continuity_out": "记录本段结束位置、姿态、动作和镜头状态",
                "user_display_zh": {"objective": f"推进第 {i} 段剧情",
                    "start_state": "承接上一段状态" if i > 1 else "建立初始状态",
                    "action_progression": f"第 {i} 段：{zh}，动作从发起推进到结果",
                    "blocking": "主体位置、朝向与互动关系保持清楚",
                    "camera": "镜头服务动作推进", "dialogue": "无台词",
                    "sound": "保留环境声、动作声与呼吸声",
                    "reference_usage": "仅使用用户指定的参考职责",
                    "end_state": "形成可供下一段承接的新状态"},
            })
        plan = {
            "version": S.SCHEMA_VERSION,
            "story_goal": str(story_goal or "")[:800],
            "global_state": {
                "visual_style": (style if style and style.lower() != "auto"
                                 else "Cinematic live-action, natural lighting, 24 fps"),
                "scene": {"location": "（模拟）由参考图定义的环境"},
                "soundscape": "Room tone and the physical sounds of the on-screen action.",
                "non_diegetic_music": "N/A",
            },
            "references": {"pictures": labels,
                           "scene_phrase": "the environment defined by the supplied references"},
            "segments": segs,
            "style": style or "auto",
            "continuation_mode": continuation_mode,
            "director": {"name": self.name, "model": "mock-director",
                         "reasoning_budget": "off"},
            "generated_from": {"provider": self.name, "model": "mock-director",
                               "story_goal": str(story_goal or "")[:200],
                               "total_seconds": float(total_seconds or seg),
                               "segment_seconds": seg,
                               "segment_count": n,
                               "offline_mock": True},
            "warnings": ["OFFLINE MOCK 计划：内容为占位，仅用于状态机与 UI 验证"],
        }
        plan = S.normalize_story_plan(plan)
        errs = S.validate_story_plan(plan)
        if errs:
            raise V.SchemaRepairFailed("plan_story", errs, ["<mock>"])
        return plan

    def compile_segment(self, *, plan: dict, segment_id: int, profile: dict,
                        override_beat: str = "") -> str:
        self.calls.append(f"compile_segment:{segment_id}")
        segs = plan.get("segments") or []
        prev = segs[int(segment_id) - 2] if int(segment_id) > 1 else None
        text, warns = PC.compile_segment_prompt(plan, int(segment_id), profile, prev)
        problems = PC.audit_prompt(text)
        if problems:
            raise V.SchemaRepairFailed("compile_segment", problems, [text])
        if warns:   # same advisory channel as the bonsai provider, so offline and
            plan["warnings"] = list(dict.fromkeys(   # live runs report identically
                list(plan.get("warnings") or [])
                + [f"seg{segment_id}: {w}" for w in warns]))[:40]
        return text


def make(project_id: str = "mock") -> MockDirectorProvider:
    """Convenience for tests and for the UI's OFFLINE mode."""
    return MockDirectorProvider()
