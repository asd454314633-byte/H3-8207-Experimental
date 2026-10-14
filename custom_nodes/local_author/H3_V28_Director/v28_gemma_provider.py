"""Gemma4 text-only DirectorPlan provider. It never receives image pixels."""
from __future__ import annotations
from typing import Any
import copy
import json
import re
import uuid
from . import v28_director_core as C
from . import v28_gemma_runtime as R
from . import v28_provider as V
from . import v28_schemas as S
from . import v28_gemma_schema as GS
from . import v28_paths as P


@V.register
class Gemma4TextDirectorProvider(V.DirectorProvider):
    name = "gemma4"
    SUPPORTS_VISION = False
    model = "Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"

    def start(self):
        R.start()
        # Startup acceptance is an actual inference-path gate, not an -ngl
        # configuration check. A failure stops the server inside R.api().
        self.load_check()
    def stop(self): R.stop()
    def health(self):
        s = R.status()
        return V.Health(ok=s["running"], provider=self.name, running=s["running"],
                        detail="就绪（文本导演，Vision OFF）" if s["running"] else "未运行",
                        model=self.model, vision=False,
                        endpoint=f"http://127.0.0.1:{s['port']}", extra=s)
    def load_check(self) -> dict:
        self._request_schema = GS.object_schema({"ok": {"type": "boolean"},
                                                "segments": {"type": "array", "maxItems": 0}})
        text = self._complete(
            [{"role": "system", "content": "You are a JSON planner. Output JSON only."},
             {"role": "user", "content": "Return exactly {\"ok\":true,\"segments\":[]}"}],
            max_tokens=256, timeout_s=120.0, temperature=0.0)
        obj = S.extract_complete_object(text)
        if GS.errors(obj, self._request_schema) or obj.get("ok") is not True:
            raise V.DirectorUnavailable("Gemma4 JSON 解码自检失败")
        return {"ok": True, "text": text[:300]}
    def analyze_references(self, images: list[dict], *, brief: str = "") -> dict:
        raise V.DirectorError("Gemma4 Text Director 禁止读取图片像素；请填写参考图用途说明。")
    def plan_story(self, *, story_goal: str, profile: dict, total_seconds: float,
                   segment_seconds: float, style: str = "auto",
                   continuation_mode: str = "same_shot", expect_segments: int | None = None) -> dict:
        planner = profile.get("director_input") or {}
        messages = C.gemma_messages(planner)
        budget = self.budget_for("plan_story")
        self.ensure_tier(budget.get("thinking"))
        self._request_schema = GS.plan_schema(int(planner["required_segment_count"]))
        self._diagnostic_records = []
        self._repair_count = 0
        raw = self._complete(messages, max_tokens=budget["max_tokens"],
                             timeout_s=budget["timeout_s"], temperature=0.6)
        initial_error = ""
        try:
            initial = S.extract_complete_object(raw)
        except ValueError as exc:
            initial_error = f"reply was not JSON ({exc})"
            initial = {"segments": []}
            self._record_failure(0, 0, raw, parse_error=initial_error)

        carrier = C._carrier_segments(initial)
        ids = [x.get("segment_index", x.get("segment", x.get("id")))
               for x in carrier if isinstance(x, dict)]
        if (len(ids) != len(carrier) or any(type(i) is not int or not 1 <= i <=
                planner["required_segment_count"] for i in ids) or len(set(ids)) != len(ids)):
            self._record_failure(0, 0, raw, validation_error="invalid or duplicate segment identity")
            raise V.SchemaRepairFailed("plan_story", ["invalid or duplicate segment identity"], [raw], repair_count=0)
        plan, alignment = C.align_plan_to_skeleton(initial, planner)
        repair_calls = 0
        repaired_segments: list[int] = []
        repair_texts: list[str] = []
        for seg in plan["segments"]:
            if repair_calls >= V.MAX_TARGETED_REPAIR_CALLS:
                break
            # One segment may need a second pass when its own fill came back
            # incomplete, but the plan is never regenerated as a whole.
            for _attempt in range(V.TARGETED_REPAIR_ATTEMPTS_PER_SEGMENT):
                gaps = GS.invalid_fields(seg)
                idx = int(seg["segment_index"])
                expected_start = plan["segments"][idx - 2].get("body_state_end") if idx > 1 else None
                if expected_start and seg.get("body_state_start") != expected_start:
                    gaps = list(dict.fromkeys(gaps + ["body_state_start"]))
                if C.detect_physical_conflicts(seg) and not seg.get("conflict_resolution"):
                    gaps = list(dict.fromkeys(gaps + ["conflict_resolution"]))
                if not gaps or repair_calls >= V.MAX_TARGETED_REPAIR_CALLS:
                    break
                # Count the request before parsing: a malformed repair is still a repair.
                repair_calls += 1
                self._repair_count = repair_calls
                self._repair_error = initial_error or "; ".join(
                    GS.errors(seg, GS.segment_schema()))
                if expected_start and "body_state_start" in gaps:
                    self._repair_error += " body_state_start must match preceding end: " + json.dumps(expected_start)
                if "conflict_resolution" in gaps:
                    self._repair_error += " resolve physical conflicts: " + json.dumps(C.detect_physical_conflicts(seg))
                self._repair_raw = repair_texts[-1] if repair_texts else raw
                try:
                    patch, text = self._repair_segment_fields(planner=planner, plan=plan,
                                                              segment_id=idx, fields=gaps)
                    problems = GS.errors(patch, GS.patch_schema(gaps))
                    if problems:
                        self._record_failure(idx, repair_calls, text, validation_error=problems)
                        repair_texts.append(text)
                        continue
                except V.SchemaRepairFailed as exc:
                    repair_texts.extend(exc.raws)
                    continue
                repair_texts.append(text)
                # Only the requested semantic fields may cross the repair boundary.
                for key in gaps:
                    if key in patch:
                        seg[key] = patch[key]
                if idx not in repaired_segments:
                    repaired_segments.append(idx)
            gaps = GS.invalid_fields(seg)
            if gaps:
                raise V.SchemaRepairFailed(
                    f"segment_{seg['segment_index']}_targeted_repair",
                    [f"invalid semantic fields: {gaps}"], [raw] + repair_texts,
                    repair_count=repair_calls)

        try:
            problems = [f"segment_{i}: {p}" for i, seg in enumerate(plan["segments"], 1)
                        for p in GS.errors(seg, GS.segment_schema())]
            if problems:
                raise ValueError("; ".join(problems))
            plan = C.validate_director_plan(plan, planner)
        except Exception as exc:
            self._record_failure(0, repair_calls, raw, validation_error=str(exc))
            raise V.SchemaRepairFailed(
                "plan_story_targeted",
                [f"定向补齐 {repair_calls} 段次后仍失败（未重写整计划）：{exc}"],
                [raw] + repair_texts, repair_count=repair_calls)
        generated = plan.get("generated_from") if isinstance(plan.get("generated_from"), dict) else {}
        generated.update({
            "plan_structure_owner": "deterministic_code",
            "plan_content_owner": "gemma4",
            "full_plan_llm_calls": 1,
            "full_plan_repair_calls": 0,
            "segment_count_llm_repair_calls": 0,
            "targeted_repair_calls": repair_calls,
            "targeted_repaired_segments": repaired_segments,
            "ignored_extra_segments": alignment["ignored_extra_segments"],
        })
        plan["generated_from"] = generated
        return plan

    def _repair_segment_fields(self, *, planner: dict, plan: dict,
                               segment_id: int, fields: list[str]) -> tuple[dict, str]:
        """One bounded, segment-local fill. It can never rewrite the plan."""
        clock = planner["segment_skeleton"][segment_id - 1]
        context = {
            "story_goal": planner.get("story_goal"),
            "reference_relationships": planner.get("reference_relationships"),
            "immutable_segment_skeleton": clock,
            "current_segment": plan["segments"][segment_id - 1],
            "fields_to_fill": fields,
            "validation_error": getattr(self, "_repair_error", ""),
            "raw_reply": getattr(self, "_repair_raw", "")[:16384],
            "target_schema": GS.patch_schema(fields),
        }
        messages = [{"role": "system", "content":
            "You repair only the listed director-semantic fields for one existing segment. "
            "Output ONE flat JSON object whose keys are exactly fields_to_fill - no wrapper "
            "object, no segments array. Use exactly the shapes in output_shape. Do not change "
            "clocks, renumber, add, remove, sanitize, weaken, or omit the user's intent."},
            {"role": "user", "content": __import__("json").dumps(
                {"context": context, "output_shape": C.segment_field_shapes(fields)},
                ensure_ascii=False)}]
        budget = self.budget_for("segment_repair")
        self._request_schema = GS.patch_schema(fields)
        text = self._complete(messages, max_tokens=budget["max_tokens"],
                              timeout_s=budget["timeout_s"], temperature=0.3)
        try:
            obj = S.extract_complete_object(text)
        except ValueError as exc:
            self._record_failure(segment_id, self._repair_count, text, parse_error=str(exc))
            raise V.SchemaRepairFailed(f"segment_{segment_id}_targeted_repair",
                                       [f"reply was not JSON ({exc})"], [text],
                                       repair_count=self._repair_count)
        if not isinstance(obj, dict):
            raise V.SchemaRepairFailed(f"segment_{segment_id}_targeted_repair",
                                       ["targeted repair must return an object"], [text])
        return obj, text
    def compile_segment(self, *, plan: dict, segment_id: int, profile: dict,
                        override_beat: str = "") -> str:
        planner = profile.get("director_input") or {}
        return C.compile_h3_prompt(planner=planner, plan=plan, segment_id=segment_id)["CANONICAL_H3_PROMPT"]
    def _complete(self, messages: list[dict], *, max_tokens: int, timeout_s: float,
                  temperature: float) -> str:
        schema = self._request_schema
        payload = {"model": "gemma4-director", "messages": messages,
                          "max_tokens": int(max_tokens), "temperature": float(temperature),
                          "top_p": 0.95, "stream": False,
                          "response_format": {"type": "json_schema", "json_schema": {
                              "name": "h3_director", "strict": True, "schema": schema}}}
        self._request_metadata = {k: copy.deepcopy(payload[k]) for k in (
            "max_tokens", "temperature", "top_p", "response_format")}
        self._response_metadata = {"finish_reason": None, "HTTP_status": None}
        try:
            envelope = R.api(payload, timeout_s)
        except Exception as exc:
            self._response_metadata["HTTP_status"] = getattr(exc, "code", None)
            self._record_failure(0, getattr(self, "_repair_count", 0), "", validation_error=str(exc))
            raise
        choices = envelope.get("choices") or []
        if not choices: raise V.DirectorUnavailable("Gemma4 返回空结果")
        msg = choices[0].get("message") or {}
        self._response_metadata = {"finish_reason": choices[0].get("finish_reason"),
                                   **envelope.get("_http_metadata", {})}
        return str(msg.get("content") or "")

    def _record_failure(self, segment_id, repair_count, raw, *, parse_error="", validation_error=""):
        """Bounded local evidence, without request messages, credentials or headers."""
        record = {"timestamp": V.utc_stamp(), "segment_id": segment_id,
                  "director_model": self.model, "endpoint": f"http://127.0.0.1:{R.PORT}/v1/chat/completions",
                  "request_mode": "chat/completions", "schema_grammar_mode": "response_format.json_schema",
                  "server_build": R.server_build(), "repair_count": repair_count,
                  "parse_error": parse_error, "validation_error": validation_error,
                  "raw_reply": re.sub(r"(?i)(bearer\s+\S+|sk-[\w-]+)", "[REDACTED]", raw[:16384]),
                  **getattr(self, "_request_metadata", {}), **getattr(self, "_response_metadata", {})}
        record.setdefault("HTTP_status", None)
        record.setdefault("finish_reason", None)
        for key in ("temperature", "top_p", "max_tokens", "response_format"):
            record.setdefault(key, None)
        self._diagnostic_records = getattr(self, "_diagnostic_records", []) + [record]
        try:
            P.atomic_write_json(P.DIRECTOR_LOGS_DIR / "director_failures" / f"{uuid.uuid4().hex}.json", record)
        except OSError:
            pass
