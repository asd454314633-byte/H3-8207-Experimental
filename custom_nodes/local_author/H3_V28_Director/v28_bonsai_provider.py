"""V28 Director - the first DirectorProvider implementation: PrismML Bonsai 2.

This is the ONLY module (besides the runtime controller) allowed to know that
Bonsai speaks llama.cpp's OpenAI-compatible dialect. Nothing above it may import
it directly - the orchestrator resolves a provider by name (task section 10).

Model/runtime provenance (task section 5):
  weights  : prism-ml/Ternary-Bonsai-2-27B-gguf, PQ2_0 + mmproj Q8_0
  runtime  : PrismML-Eng/llama.cpp release prism-b10743-adfffbe, win-cuda-13.3
  Stock llama.cpp is refused on purpose: the weights live in a rotated (Hadamard)
  basis, so a runtime without the activation transform loads them and produces
  garbage instead of erroring. `load_check()` below is what proves we are not in
  that failure mode.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import v28_bonsai_runtime as R
from . import v28_director_prompts as DP
from . import v28_paths as P
from . import v28_prompt_compiler as PC
from . import v28_provider as V
from . import v28_schemas as S

MAX_IMAGE_BYTES = 12 * 1024 * 1024
RAW_DIR_NAME = "raw_replies"
# A ternary model on a runtime without the Hadamard activation transform still
# answers - it just answers with noise. This probe is what catches that.
LOAD_PROBE = "Reply with exactly this word and nothing else: BONSAI_OK"
LOAD_PROBE_EXPECT = "BONSAI_OK"


@V.register
class Bonsai2DirectorProvider(V.DirectorProvider):
    name = "bonsai2"
    SUPPORTS_VISION = True

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or R.load_runtime_config()
        self.model = os.path.basename(str(self.cfg.get("model_main") or "")) or "bonsai2"

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        purpose = self.cfg.get("purpose") or "plan"
        R.start_server(purpose=purpose, thinking=self.cfg.get("thinking", "medium"))

    def stop(self) -> None:
        R.stop_server()

    def ensure_tier(self, thinking: str | None) -> None:
        """Put the resident server at the tier this operation declared.

        P11 TEST3: `BUDGET[kind]["thinking"]` used to be a comment. llama.cpp only
        takes the reasoning budget on the command line, and start_server() used to
        answer "reused: True" for any already-running server - so an analyze that
        asked for `low` (512) ran against a `medium` (2048) resident, spent every
        one of its 2048 max_tokens on thinking, and returned an empty `content`.
        An unknown tier falls back to whatever runtime.json declares, then medium.
        """
        tier = (thinking if thinking in R.THINKING_BUDGET
                else self.cfg.get("thinking") or "medium")
        try:
            R.start_server(purpose=self.cfg.get("purpose") or "plan", thinking=tier)
        except R.RuntimeError_ as e:
            # A start failure is "director unavailable" in the caller's vocabulary -
            # DirectorError, so the task layer shows it in Chinese, keeps the input
            # for retry (§33) and still runs its finally-block release.
            raise V.DirectorUnavailable(str(e)[:400])

    def health(self) -> V.Health:
        h = R.health()
        running = bool(h.get("running"))
        ok = running and not h.get("api_error")
        return V.Health(ok=ok, provider=self.name, running=running,
                        detail=(h.get("api_error") or ("就绪" if ok else "导演模型未运行")),
                        model=h.get("model_main") or "", vision=True,
                        endpoint=(f"http://{P.DIRECTOR_HOST}:{h.get('port')}" if h.get("port") else ""),
                        extra={k: v for k, v in h.items() if k not in ("models", "resources")})

    def load_check(self) -> dict:
        """Non-destructive sanity: does the runtime reproduce a literal string?

        Garbage output from a rotated-basis model looks fluent-ish but never
        matches a two-token echo, so this separates "loaded" from "usable".
        """
        try:
            out = self._complete([{"role": "user", "content": LOAD_PROBE}],
                                 max_tokens=16, timeout_s=120.0, temperature=0.0)
        except V.DirectorError as e:
            return {"ok": False, "detail": str(e)[:200]}
        got = out.strip()
        return {"ok": LOAD_PROBE_EXPECT in got, "expected": LOAD_PROBE_EXPECT,
                "got": got[:120], "model": self.model}

    # -- transport ---------------------------------------------------------
    def _complete(self, messages: list[dict], *, max_tokens: int, timeout_s: float,
                  temperature: float) -> str:
        if not R.server_running():
            raise V.DirectorUnavailable("导演模型未运行，请先执行分析或规划（会自动启动）。")
        payload = {"model": self.cfg.get("alias") or "bonsai2",
                   "messages": messages,
                   "max_tokens": int(max_tokens),
                   "temperature": float(temperature),
                   "stream": False}
        t0 = time.time()
        try:
            j = R.api_json("/v1/chat/completions", payload, timeout=timeout_s)
        except urllib.error.HTTPError as e:
            raise V.DirectorUnavailable(f"导演服务 HTTP {e.code}")
        except R.RuntimeError_ as e:
            msg = str(e)
            if "无响应" in msg or "timed out" in msg.lower() or "timeout" in msg.lower():
                raise V.BudgetExceeded("director_call", timeout_s)
            raise V.DirectorUnavailable(msg)
        choices = j.get("choices") or []
        if not choices:
            raise V.DirectorUnavailable(f"导演服务返回空结果: {json.dumps(j)[:200]}")
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") or {}
        content = msg.get("content") or first.get("text") or ""
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        finish = first.get("finish_reason") or ""
        if not str(content).strip() and str(reasoning).strip():
            # some builds put everything in the reasoning field when the answer is cut
            content = reasoning
        self.last_meta = {"finish_reason": finish, "elapsed_s": round(time.time() - t0, 2),
                          "usage": j.get("usage") if isinstance(j, dict) else None,
                          "truncated": finish == "length"}
        # `truncated` lives in last_meta only: the config dict is a shared object
        # handed back by load_runtime_config(), so a reply must never write into it.
        return str(content)

    # -- director operations ----------------------------------------------
    def analyze_references(self, images: list[dict], *, brief: str = "") -> dict:
        if not images:
            raise V.DirectorUnavailable("没有可用的参考图槽位")
        if len(images) > 4:
            images = images[:4]
        content: list[dict] = [{"type": "text", "text": DP.analyze_user(images, brief)}]
        for im in images:
            url = self._image_data_url(im)
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [{"role": "system", "content": DP.ANALYZE_SYSTEM},
                    {"role": "user", "content": content}]
        idx = [int(im.get("index", i + 1)) for i, im in enumerate(images)]

        def _norm(obj: Any) -> Any:
            if not isinstance(obj, dict):
                raise ValueError("profile must be an object")
            obj.setdefault("version", S.SCHEMA_VERSION)
            sp = obj.get("source_pictures")
            if not isinstance(sp, list) or not sp:
                obj["source_pictures"] = [{"index": i, "filename": str(
                    (images[k].get("name") or images[k].get("filename") or "")),
                    "width": int(images[k].get("width") or 0),
                    "height": int(images[k].get("height") or 0)}
                    for k, i in enumerate(idx)]
            for s in obj.get("subjects") or []:
                if isinstance(s, dict):
                    refs = [int(r) for r in (s.get("picture_refs") or []) if str(r).isdigit()]
                    s["picture_refs"] = [r if 1 <= r <= len(idx) else 1 for r in refs] or [1]
                    s.setdefault("inferred", {})
                    s.setdefault("do_not_infer", ["未来运动方向", "不可见身体结构", "剧情意图"])
            obj.setdefault("uncertain", [])
            obj.setdefault("not_answerable", [])
            for banned in S.PROFILE_FORBIDDEN_TOPICS:
                obj["not_answerable"] = list(dict.fromkeys(
                    list(obj["not_answerable"]) + [banned]))
            return obj

        profile = self._json_only(messages, kind="analyze_references",
                                  validate=S.validate_reference_profile, normalize=_norm,
                                  temperature=0.3, raw_log=self._save_raw)
        # P11 TEST3 deleted the `profile["director"] = {...}` stamp that used to sit
        # here. Nothing is lost by that: PROFILE_KEYS (v28_schemas.py:88) is closed
        # and does NOT contain `director` - unlike PLAN_KEYS, which was widened on
        # purpose to carry `director` / `generated_from` / `warnings`. So the stamp
        # made the object the provider returns fail the very contract the provider
        # had just validated it against: `_json_only` checks the reply BEFORE
        # stamping, and v28_orchestrator.analyze_now re-checks with
        # `S.check("reference_profile", profile)` AFTER - three minutes of real
        # vision work discarded as SchemaError: $.director: unknown key.
        # No consumer ever read profile["director"] (grep: only the plan stamp and
        # this one mention it), and the provenance now lives where it cannot break
        # a validated artifact - the project log line analyze_now writes.
        return profile

    def plan_story(self, *, story_goal: str, profile: dict, total_seconds: float,
                   segment_seconds: float, style: str = "auto",
                   continuation_mode: str = "same_shot",
                   expect_segments: int | None = None) -> dict:
        n = int(expect_segments or max(1, round(float(total_seconds) / max(1.0, float(segment_seconds)))))
        if not (1 <= n <= 24):
            raise V.DirectorError(f"段数 {n} 超出可用范围 1..24")
        mode = continuation_mode if continuation_mode in S.CONTINUATION_MODES else "same_shot"
        system, user = DP.plan_user(story_goal=story_goal, profile=profile,
                                   total_seconds=total_seconds, segment_seconds=segment_seconds,
                                   style=style, continuation_mode=mode, n=n,
                                   provider=self.name, model=self.model)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        want_pics = [int(p.get("index", i + 1))
                     for i, p in enumerate(profile.get("source_pictures") or [])]

        def _validate(obj: Any) -> list[str]:
            errs = S.validate_story_plan(obj)
            if not errs:
                segs = obj.get("segments") or []
                if len(segs) != n:
                    errs.append(f"$.segments: must contain exactly {n} segments "
                                f"(total {total_seconds}s / {segment_seconds}s per segment), "
                                f"got {len(segs)}")
                if mode == "same_shot":
                    for s in segs[1:]:
                        j = (s.get("directives") or {}).get("join")
                        if j in ("hard_cut", "match_cut"):
                            errs.append(f"$.segments[{s.get('id')}].directives.join: "
                                        f"{j!r} not allowed while continuation_mode=same_shot")
                for s in segs:
                    p = str(s.get("prompt") or "")
                    if p and PC._INSTANT_RE.search(p):
                        errs.append(f"$.segments[{s.get('id')}].prompt: instant-change wording "
                                    f"is forbidden (task section 17)")
            return errs

        plan = self._json_only(messages, kind="plan_story", validate=_validate,
                               normalize=S.normalize_story_plan, temperature=0.6,
                               raw_log=self._save_raw)
        plan["continuation_mode"] = mode
        plan["style"] = style or "auto"
        plan["references"] = dict(plan.get("references") or {})
        plan["references"].setdefault("picture_count", len(want_pics))
        plan["references"].setdefault("picture_indices", want_pics)
        plan["generated_from"] = dict(plan.get("generated_from") or {})
        plan["generated_from"].update({
            "total_seconds": total_seconds, "segment_seconds": segment_seconds,
            "segment_count": len(plan.get("segments") or []),
            "story_goal": story_goal[:400], "provider": self.name, "model": self.model,
            "at": V.utc_stamp(), "call_meta": getattr(self, "last_meta", {})})
        # Record what the server ACTUALLY ran with, not what this object was
        # constructed with: start_server() re-reads runtime.json, and a config
        # edited in between would otherwise be logged wrong.
        live = dict(R.load_runtime_config())
        live.update({k: v for k, v in (R.health() or {}).items()
                     if k in ("port", "ctx_size", "thinking", "model_main", "alias") and v})
        self.cfg = live
        plan["director"] = {"provider": self.name, "model": self.model,
                            "ctx_size": int(live.get("ctx_size")
                                            or R.DEFAULT_SERVER.get("ctx_size")),
                            "reasoning_budget": THINKING(live)}
        load_warns = PC.audit_plan_load(plan)
        plan["warnings"] = list(dict.fromkeys(list(plan.get("warnings") or []) + load_warns))
        return plan

    def compile_segment(self, *, plan: dict, segment_id: int, profile: dict,
                        override_beat: str = "") -> str:
        segs = plan.get("segments") or []
        idx = int(segment_id) - 1
        if not (0 <= idx < len(segs)):
            raise V.DirectorError(f"段号 {segment_id} 不在 1..{len(segs)}")
        seg = segs[idx]
        prev = segs[idx - 1] if idx > 0 else None
        warns: list[str] = []

        if override_beat:
            seg["beat"] = str(override_beat).strip()[:400]
        # Ask the model only when the segment has no usable action text of its own
        # (or the human just rewrote the beat). Structure is always compiler-made.
        if override_beat or not str(seg.get("prompt") or "").strip():
            try:
                self._llm_action(plan=plan, seg=seg, profile=profile, prev=prev,
                                 segment_id=segment_id, override_beat=override_beat)
            except V.DirectorError as e:
                warns.append(f"导演编译回退为确定性拼装：{e}")

        prompt, cw = PC.compile_segment_prompt(plan, segment_id, profile, prev)
        warns += cw
        meta = PC.audit_prompt(prompt, shots_expected=_expected_shots(seg, plan))
        if meta:
            raise V.DirectorError("H3 prompt 结构校验失败: " + "; ".join(meta[:4]))
        # Advisories go where the plan already keeps them (PLAN_KEYS.warnings, the
        # same field plan_story fills in v28_orchestrator), never onto a segment:
        # SEGMENT_KEYS is closed precisely so that a segment carries story facts
        # only, and an extra derived key written there would make the very next
        # S.check("story_plan") reject a plan we just produced.
        if warns:
            plan["warnings"] = list(dict.fromkeys(
                list(plan.get("warnings") or []) + [f"seg{segment_id}: {w}" for w in warns]))[:40]
        return prompt

    def _llm_action(self, *, plan: dict, seg: dict, profile: dict, prev: dict | None,
                    segment_id: int, override_beat: str) -> str:
        user = DP.compile_user(plan=plan, seg=seg, profile=profile, prev_seg=prev,
                               segment_id=segment_id, override_beat=override_beat)
        messages = [{"role": "system", "content": DP.COMPILE_SYSTEM},
                    {"role": "user", "content": user}]

        def _v(obj: Any) -> list[str]:
            if not isinstance(obj, dict):
                return ["root must be an object"]
            if not str(obj.get("prompt") or "").strip():
                return ["prompt must be a non-empty English action text"]
            return []

        out = self._json_only(messages, kind="compile_segment", validate=_v,
                              temperature=0.5, raw_log=self._save_raw)
        text = str(out.get("prompt") or "").strip()
        if text:
            seg["prompt"] = text
        if out.get("soundscape") and str(out["soundscape"]).strip().upper() != "N/A":
            seg["soundscape"] = str(out["soundscape"]).strip()[:400]
        if out.get("music") and str(out["music"]).strip().upper() != "N/A":
            seg["music"] = str(out["music"]).strip()[:300]
        return text

    # -- helpers -----------------------------------------------------------
    def _image_data_url(self, im: dict) -> str:
        if im.get("b64"):
            mime = im.get("mime") or "image/png"
            return f"data:{mime};base64,{im['b64']}"
        path = Path(im.get("path") or "")
        if not path.is_file():
            raise V.DirectorUnavailable(f"参考图文件不存在: {path}")
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise V.DirectorError(f"参考图过大（{size // 1048576} MB），请压缩后重试")
        mime = im.get("mime") or mimetypes.guess_type(path.name)[0] or "image/png"
        with open(path, "rb") as f:
            blob = f.read()
        return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"

    def _save_raw(self, text: str) -> None:
        try:
            d = P.BONSAI_CACHE_DIR / RAW_DIR_NAME
            d.mkdir(parents=True, exist_ok=True)
            name = d / f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{int(time.time()*1000)%1000}.txt"
            with open(name, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError:
            pass


def THINKING(cfg: dict) -> int:
    return int(R.THINKING_BUDGET.get(cfg.get("thinking", "medium"),
                                     cfg.get("reasoning_budget") or 2048))


def _expected_shots(seg: dict, plan: dict) -> int:
    d = seg.get("directives") or {}
    if (plan.get("continuation_mode") == "natural_cut"
            and d.get("join") in ("hard_cut", "match_cut")
            and float(seg.get("duration") or 10) >= 2 * PC.SECONDS_PER_SHOT):
        return 2
    return 1
