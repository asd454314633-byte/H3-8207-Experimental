"""Permanent regression gates; no real model, queue or GPU is used."""
import copy
import asyncio
import json
from unittest.mock import patch

import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from _v28_bootstrap import load, fresh_env

P = load("v28_paths")
PJ = load("v28_project")
SM = load("v28_state_machine")
V = load("v28_provider")
C = load("v28_director_core")
S = load("v28_schemas")
G = load("v28_gemma_provider")
GS = load("v28_gemma_schema")
OR = load("v28_orchestrator")
PR = load("v28_prompt_resolution")
RC = load("v28_runtime_contract")


class TestFinalManualRoutes(unittest.TestCase):
    def test_switch_restores_manual_without_provider(self):
        routes = load("v28_routes")
        with fresh_env():
            PJ.create(project_id="route", title="route")
            manual("route")
            plan = PJ.read("route", "STORY_PLAN.json")
            plan["global_state"]["prompt_source"] = PR.DIRECTOR
            PJ.write("route", "STORY_PLAN.json", plan)
            PR.set_source("route", PR.DIRECTOR)
            async def body(_):
                return {"project_id": "route", "prompt_source": "MANUAL"}
            with patch.object(routes, "_body", body), patch.object(V, "get_provider", side_effect=AssertionError("Director touched")):
                response = asyncio.run(routes._prompt_source(None))
            self.assertEqual(response.status, 200)
            self.assertEqual(PR.final_prompt("route", 1), "manual action 1")

    def test_prepare_uses_current_unsaved_manual_draft(self):
        with fresh_env():
            PJ.create(project_id="draft", title="draft")
            manual("draft")
            prompts = [f"updated exact draft {i}" for i in range(6)]
            with patch.object(V, "get_provider", side_effect=AssertionError("Director touched")):
                instruction = OR.prepare_segment("draft", manual_prompts=prompts)
            self.assertEqual(instruction["resolved_segment"]["final_prompt"], prompts[0])


def semantic(i):
    body = {k: "UNKNOWN" for k in C.BODY_STATE_FIELDS}
    return {"segment_index": i, **{k: f"action {i}" for k in GS.TEXT_FIELDS},
            "beats": [f"action {i}"], "body_state_start": body, "body_state_end": copy.deepcopy(body),
            "micro_timeline": [{"phase": "EXECUTE", "action": f"action {i}", "state_change": ""}],
            "render_risk": {"body_geometry": "LOW", "occlusion": "LOW", "fast_full_body_motion": False},
            "user_display_zh": {k: f"中文第{i}段" for k in GS.ZH_FIELDS}}


class Replies(G.Gemma4TextDirectorProvider):
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.starts = 0
        self.stops = 0

    def start(self): self.starts += 1
    def stop(self): self.stops += 1
    def health(self): return V.Health(ok=True, provider="gemma4", running=True)
    def _complete(self, messages, **kwargs):
        self.calls.append(copy.deepcopy(messages))
        reply = next(self.replies)
        if isinstance(reply, Exception): raise reply
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)


def env():
    with fresh_env():
        PJ.create(project_id="regression", title="regression")
        yield "regression"


def args(n=6):
    return {"story_goal": "A person walks across a quiet room", "images": [
        {"index": 1, "slot_index": 1, "filename": "fixture.png"}],
        "total_seconds": n * 10, "segment_seconds": 10}


def manual(pid, n=6):
    return OR.plan_now(project_id=pid, prompt_source="MANUAL",
        manual_prompts=[f"manual action {i}" for i in range(1, n + 1)],
        generation_settings={"seed": 123, "steps": 8, "extra_limit": "keep costume"}, **args(n))


def director(pid, replies, n=6):
    prov = Replies(replies)
    with patch.object(V, "get_provider", return_value=prov), patch.object(
            OR, "_stop_and_confirm", side_effect=lambda p, name: (p.stop() or {"verdict": "RELEASED"})), patch.object(
            SM, "_gate", return_value=(True, "", {})):
        result = OR.plan_now(project_id=pid, **args(n))
    return result, prov


def test_T01_MANUAL_WITHOUT_DIRECTOR(env):
    with patch.object(V, "get_provider", side_effect=AssertionError("provider instantiated")), patch.object(
            G.R, "start", side_effect=AssertionError("8092 process started")), patch.object(
            G.R, "api", side_effect=AssertionError("8092 requested")), patch.object(
            RC, "get_active_director_runtime", side_effect=AssertionError("8092 probed")), patch.object(
            SM, "_gate", side_effect=AssertionError("Director gate entered")):
        result = manual(env)
        assert result["segment_count"] == 6
        instruction = OR.prepare_segment(env, seed=123)
        assert instruction["prompt"] == "manual action 1"
        assert instruction["motion_context"]["chain_segments"] == 6
        assert OR.card_state(env)["prompt_source"] == "MANUAL"
        assert instruction["PREVIEW_EQUALS_SUBMISSION"]


def test_T02_DIRECTOR_SUCCESS(env):
    manual(env)
    prompts_before = PJ.read(env, PR.MANUAL_FILE)
    result, prov = director(env, [{"segments": [semantic(i) for i in range(1, 7)]}])
    assert result["director_status"] == "COMMITTED"
    assert len(PR.execution_segments(env)) == 6
    assert prov.starts == prov.stops == 1
    assert PJ.read(env, PR.MANUAL_FILE) == prompts_before


def test_T03_malformed_initial_actually_repairs(env):
    result, prov = director(env, ["not JSON", semantic(1)], n=1)
    assert result["director_status"] == "COMMITTED"
    assert len(prov.calls) == 2
    assert PJ.read(env, "STORY_PLAN.json")["generated_from"]["targeted_repair_calls"] == 1
    assert "not JSON" in prov.calls[1][1]["content"]


def test_T04_DIRECTOR_MALFORMED_RECOVERABLE_preserves_core(env):
    manual(env)
    before = PJ.core_snapshot(env)
    result, prov = director(env, [{"segments": [{"segment_index": 1}]}, "broken", "still broken"])
    # Prompt source is an explicit mode selection; all other core bytes are unchanged.
    after = PJ.core_snapshot(env)
    before.pop(PR.SOURCE_FILE); after.pop(PR.SOURCE_FILE)
    assert after == before
    assert result["director_status"] == "FAILED_RECOVERABLE"
    assert len(prov.calls) == 3 and "after 2 repairs" in result["error"]
    assert prov.stops == 1
    with unittest.TestCase().assertRaises(SM.GateRefused): OR.prepare_segment(env)


def test_T05_DIRECTOR_UNAVAILABLE_RECOVERABLE(env):
    manual(env)
    prov = Replies([])
    with patch.object(V, "get_provider", return_value=prov), patch.object(
            prov, "start", side_effect=V.DirectorUnavailable("8092 unavailable")), patch.object(
            OR, "_stop_and_confirm", return_value={"verdict": "RELEASED"}):
        out = OR.plan_now(project_id=env, **args())
    assert out["director_status"] == "FAILED_RECOVERABLE"
    PR.set_source(env, "MANUAL")
    assert OR.prepare_segment(env, seed=123)["prompt"] == "manual action 1"


def test_T06_markdown_and_surrounding_prose():
    obj = {"a": {"text": "brace } in string"}}
    assert S.extract_complete_object("Answer\n```json\n" + json.dumps(obj) + "\n```\nDone") == obj


def test_T07_truncation_is_repaired_without_guessing(env):
    truncated = '{"segments": [{"segment_index":1,"segment_objective":"unfinished'
    with unittest.TestCase().assertRaises(ValueError): S.extract_complete_object(truncated)
    result, prov = director(env, [truncated, semantic(1)], n=1)
    assert result["director_status"] == "COMMITTED" and len(prov.calls) == 2


def test_T08_missing_segment_repairs_only_failed_segment(env):
    initial = {"segments": [semantic(i) for i in range(1, 6)]}
    result, prov = director(env, [initial, semantic(6)])
    assert result["director_status"] == "COMMITTED"
    assert len(prov.calls) == 2
    context = json.loads(prov.calls[1][1]["content"])["context"]
    assert context["immutable_segment_skeleton"]["segment_index"] == 6
    assert "previous_segment" not in context and "next_segment" not in context


def test_T09_failed_director_switch_manual_without_rebuilding_map(env):
    manual(env)
    profile = PJ.read(env, "REFERENCE_PROFILE.json")
    director(env, ["bad", "bad", "bad"])
    PR.set_source(env, "MANUAL")
    with patch.object(C, "active_reference_map", side_effect=AssertionError("map rebuilt")):
        assert OR.prepare_segment(env, seed=123)["prompt"] == "manual action 1"
    assert PJ.read(env, "REFERENCE_PROFILE.json") == profile


def test_T10_repeated_manual_has_no_director_or_staging(env):
    with patch.object(G.R, "api", side_effect=AssertionError("8092 touched")):
        for _ in range(3):
            manual(env)
            instr = OR.prepare_segment(env, seed=123)
            assert instr["prompt"] == "manual action 1"
            assert not (PJ.project_dir(env) / "director_staging").exists()


def test_failure_mid_commit_rolls_back_all_artifacts(env):
    manual(env)
    before = PJ.core_snapshot(env)
    original = PJ.save_prompt_text
    def broken(pid, sid, text, **kwargs):
        if sid == 2: raise OSError("disk failure during commit")
        return original(pid, sid, text, **kwargs)
    with patch.object(PJ, "save_prompt_text", side_effect=broken):
        result, _ = director(env, [{"segments": [semantic(i) for i in range(1, 7)]}])
    after = PJ.core_snapshot(env)
    before.pop(PR.SOURCE_FILE); after.pop(PR.SOURCE_FILE)
    assert result["director_status"] == "FAILED_RECOVERABLE" and after == before


def test_actual_payload_carries_decoder_schema(env):
    provider = G.Gemma4TextDirectorProvider()
    provider._request_schema = GS.plan_schema(6)
    captured = []
    def api(payload, timeout):
        captured.append(payload)
        return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "_http_metadata": {"HTTP_status": 200}}
    with patch.object(G.R, "api", side_effect=api):
        provider._complete([], max_tokens=256, timeout_s=2, temperature=0)
    assert captured[0]["response_format"]["json_schema"]["schema"]["properties"]["segments"]["minItems"] == 6
    assert captured[0]["stream"] is False


def test_wrong_field_type_rejected_and_targeted(env):
    initial = semantic(1); initial["camera"] = {"wrong": "object"}
    result, prov = director(env, [{"segments": [initial]}, {"camera": "tracking camera"}], n=1)
    assert result["director_status"] == "COMMITTED"
    assert json.loads(prov.calls[1][1]["content"])["context"]["fields_to_fill"] == ["camera"]


def test_failure_evidence_has_actual_count_and_bounded_raw(env):
    director(env, ["bad", "bad", "bad"], n=1)
    evidence = [json.loads(p.read_text(encoding="utf-8"))
                for p in (P.DIRECTOR_LOGS_DIR / "director_failures").glob("*.json")]
    assert sorted(x["repair_count"] for x in evidence) == [0, 1, 2]
    required = {"timestamp", "segment_id", "director_model", "server_build", "endpoint",
                "request_mode", "schema_grammar_mode", "finish_reason", "HTTP_status",
                "repair_count", "parse_error", "validation_error", "raw_reply"}
    assert all(required <= set(x) for x in evidence)


def test_mock_server_observes_actual_HTTP_payload(env):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"choices": [{"message": {"content": json.dumps(semantic(1))},
                                            "finish_reason": "stop"}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    provider = G.Gemma4TextDirectorProvider()
    provider._request_schema = GS.segment_schema()
    try:
        with patch.object(G.R, "PORT", server.server_port), patch.object(
                G.R, "_sample_request", side_effect=lambda fn: fn()), patch.object(
                RC, "verify_director_gpu_ready", return_value=None):
            raw = provider._complete([], max_tokens=2048, timeout_s=2, temperature=0)
        assert S.extract_complete_object(raw)["segment_index"] == 1
        assert received[0]["response_format"]["type"] == "json_schema"
        assert received[0]["response_format"]["json_schema"]["schema"] == GS.segment_schema()
        assert provider._response_metadata["HTTP_status"] == 200
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


def test_timeout_never_mutates_manual_state(env):
    manual(env)
    before = PJ.core_snapshot(env)
    result, prov = director(env, [TimeoutError("8092 timed out")])
    after = PJ.core_snapshot(env)
    before.pop(PR.SOURCE_FILE); after.pop(PR.SOURCE_FILE)
    assert before == after and result["director_status"] == "FAILED_RECOVERABLE"
    assert prov.stops == 1


def test_manual_chain_advances_without_Director(env):
    manual(env)
    with patch.object(SM, "_gate", side_effect=AssertionError("Director gate touched")):
        for i in (1, 2, 3):
            instruction = OR.prepare_segment(env, seed=123)
            assert instruction["prompt"] == f"manual action {i}"
            OR.confirm_submitted(env, seed=123)
            slot = PJ.mc_slot_path(i); slot.parent.mkdir(parents=True, exist_ok=True)
            slot.write_bytes(b"mock latent")
            SM.mark_candidate(env, video=f"mock_{i}.mp4", seed=123)
            SM.accept(env)
        assert SM.load_state(env)["current_segment"] == 4


class OptionalDirectorRegression(unittest.TestCase):
    """Stdlib runner so the frozen ComfyUI environment needs no pytest install."""


def _case(fn):
    def run(self):
        with fresh_env():
            PJ.create(project_id="regression", title="regression")
            if fn.__code__.co_argcount:
                fn("regression")
            else:
                fn()
    return run


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        setattr(OptionalDirectorRegression, _name, _case(_fn))

if __name__ == "__main__":
    unittest.main(verbosity=2)
