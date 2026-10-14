"""V28 Director - HTTP surface (aiohttp routes on the existing 8197 server).

Architecture decision, recorded here because it is load-bearing:
the V28 director registers **zero graph nodes**. V27 removes UI-only selector
nodes at submit time through a hardcoded type whitelist inside
`h3_workflow_helpers/web/h3_workflow_ux.js`; adding a V28 node type would mean
editing that shared V27 helper, which task sections 2 and 36 forbid. So the
director lives beside the graph (sidebar panel + these routes) and drives the
existing V27 nodes by writing their widgets through the front end.

Security: every mutating route requires a same-origin, loopback request. Reads
are harmless project metadata. This mirrors ComfyUI's own policy of not letting
a foreign page POST into a node server, and is stricter: a non-127.0.0.1
peer is refused even with a matching Origin.

Blocking work never happens on the event loop: PHASE A runs in a worker thread
owned by `v28_orchestrator`, and the handler only ever polls a task record.
"""
from __future__ import annotations

import asyncio
import json
from functools import wraps
from urllib.parse import urlparse, urlsplit

from aiohttp import web

from . import v28_orchestrator as OR
from . import v28_paths as P
from . import v28_provider as V
from . import v28_schemas as S
from . import v28_state_machine as SM
from . import v28_director_core as CORE
from . import v28_runtime_contract as RC
from . import v28_prompt_resolution as PR
from . import v28_project as PJ

PREFIX = "/h3_director"
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_registered = False


# --------------------------------------------------------------------------- #
# request guard
# --------------------------------------------------------------------------- #
def _host_parts(host_header: str):
    u = urlsplit("//" + (host_header or "").strip().lower())
    return (u.hostname or "").lower(), (u.port or 80)


def _origin_parts(value: str):
    raw = (value or "").strip()
    if not raw or raw.lower() == "null":
        return "", None
    u = urlparse(raw)
    host = (u.hostname or "").lower()
    if not host:
        return "", None
    return host, (u.port or (443 if u.scheme == "https" else 80))


def _peer_host(request) -> str:
    """Normalise aiohttp's peer address into a lowercase host string.

    P11 TEST1 found the real defect behind this helper: `request.remote` is
    declared `str | None` in aiohttp (3.14.3 `web_request.py`: the peer IP of the
    socket that accepted us), but the guard below read it as
    `request.remote.hostname or request.remote.host`. On a str that is an
    AttributeError, and because `guarded()` wraps every mutating handler the
    result was a bare `500 Internal Server Error` from aiohttp - no JSON body, no
    Chinese message, nothing the card could show - for EVERY POST, from the real
    browser included. None of the 208 static tests caught it because no test
    imported this module at all: an object-shaped mock could never have
    reproduced a shape that only the real transport produces.

    Tolerate both worlds without ever trusting one of them: str (real aiohttp),
    an object carrying `.hostname`/`.host` (transport-info style), or None.
    """
    rem = getattr(request, "remote", None)
    if rem is None:
        return ""
    if isinstance(rem, str):
        return rem.strip().strip("[]").lower()
    host = getattr(rem, "hostname", None) or getattr(rem, "host", None) or ""
    return str(host).strip().strip("[]").lower()


def reject_request(request):
    """403 unless this is a local, same-origin call."""
    peer = _peer_host(request)
    if peer not in _LOOPBACK:
        return web.json_response({"error": "只接受本机回环地址访问导演接口"}, status=403)
    if request.method not in _MUTATING:
        return None
    site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site == "cross-site":
        return web.json_response({"error": "跨站请求已被拒绝"}, status=403)
    hh, hp = _host_parts(request.headers.get("Host") or "")
    if not hh:
        return web.json_response({"error": "缺少 Host 头"}, status=403)
    oh, op = _origin_parts(request.headers.get("Origin") or "")
    if not oh:
        oh, op = _origin_parts(request.headers.get("Referer") or "")
    if not oh or oh != hh or op != hp:
        return web.json_response({"error": "来源与本机服务不一致"}, status=403)
    return None


def guarded(handler):
    @wraps(handler)
    async def wrapped(request):
        blocked = reject_request(request)
        if blocked is not None:
            return blocked
        return await handler(request)
    return wrapped


def _err(exc: Exception) -> dict:
    """The body of every refusal this module returns.

    `kind` is there so the card can tell the §31 VRAM gate apart from §35's
    structure refusal without pattern-matching a Chinese sentence: the two need
    different actions (wait / stop the director vs. edit the prompt), and the red
    gate bar offers only the first one's buttons.
    """
    out = {"error": _zh(exc)}
    kind = (getattr(exc, "details", None) or {}).get("kind")
    if kind:
        out["kind"] = str(kind)
    return out


def _zh(exc: Exception) -> str:
    """Every failure leaves as one Chinese sentence the card can show verbatim."""
    if isinstance(exc, SM.GateRefused):
        return str(exc)
    if isinstance(exc, V.DirectorError):
        return str(exc)
    if isinstance(exc, S.SchemaError):
        return "结构校验未通过：" + "; ".join(exc.errors[:4])
    return f"{type(exc).__name__}: {exc}"


async def _body(request) -> dict:
    raw = await request.read()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"请求体不是合法 JSON（{exc}）") from exc
    if not isinstance(data, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return data


def _ok(payload: dict) -> web.Response:
    return web.json_response(payload, dumps=lambda o: json.dumps(o, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# handlers
# --------------------------------------------------------------------------- #
async def _ping(request):
    return _ok({"ok": True, "package": "H3_V28_Director", "port_hint": 8197,
                "comfy_root": str(P.COMFY_ROOT)})


async def _health(request):
    pid = request.query.get("project_id") or ""
    if request.query.get("prompt_source") == PR.MANUAL or (pid and PR.source(pid) == PR.MANUAL):
        return _ok({"prompt_source": PR.MANUAL, "director_enabled": False,
                    "generation_gate": {"allowed": True}, "provider_health": None})
    name = request.query.get("provider") or ""
    out: dict = {"runtime": RC.get_active_director_runtime(name).as_dict(),
                 "providers": V.available_providers(),
                 "generation_gate": None, "provider_health": None}
    allowed, msg, details = RC.generation_gate()
    out["generation_gate"] = {"allowed": allowed, "message": msg, "details": details}
    try:
        out["provider_health"] = V.get_provider(name or None).health().as_dict()
    except Exception as exc:                                # noqa: BLE001
        out["provider_health"] = {"ok": False, "detail": _zh(exc), "provider": name}
    return _ok(out)


async def _start(request):
    body = await _body(request)
    if body.get("project_id") and PR.source(str(body["project_id"])) == PR.MANUAL:
        return web.json_response({"error": "导演关闭：请先选择导演模式"}, status=409)
    # P11 TEST1 (second half): a director that refuses to come up - no model
    # file, port taken, VRAM gate, health timeout - raised straight out of this
    # handler, so aiohttp answered with a bare 500 and the card had nothing to
    # show. `/start` is the ONE route whose failure is a normal, expected event,
    # so it owes the same Chinese 409 body every other refusal uses.
    try:
        prov = V.get_provider(body.get("provider") or None)
        await asyncio.get_running_loop().run_in_executor(None, prov.start)
        return _ok({"started": True, "provider": getattr(prov, "name", "?"),
                    "health": prov.health().as_dict(),
                    "runtime": RC.runtime_snapshot(prov.name).as_dict()})
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)


async def _stop(request):
    body = await _body(request)
    try:
        verdict = await asyncio.get_running_loop().run_in_executor(
            None, lambda: RC.stop_active_director(str(body.get("provider") or "")))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"stopped": True, "release": verdict})


async def _load_check(request):
    """Provider-owned short inference plus the common fail-closed GPU gate."""
    try:
        prov = V.get_provider(request.query.get("provider") or None)
        fn = getattr(prov, "load_check", None)
        if fn is None:
            return web.json_response(
                {"error": f"{getattr(prov, 'name', '?')} 未实现 GPU inference 自检"}, status=409)
        out = await asyncio.get_running_loop().run_in_executor(None, fn)
        runtime = RC.verify_director_gpu_ready(prov.name).as_dict()
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"probe": out, "runtime": runtime})


async def _projects(request):
    return _ok({"projects": OR.list_projects(),
                "resumable": [m for m in OR.list_projects()
                              if m.get("status") not in (None, "NO_SESSION", "COMPLETE")]})


async def _create(request):
    body = await _body(request)
    return _ok(OR.create_project(str(body.get("title") or "")))


async def _state(request):
    pid = request.query.get("project_id") or ""
    if not pid:
        return _ok({"projects": OR.list_projects()})
    from . import v28_project as PJ
    if not PJ.exists(pid):
        return web.json_response({"error": f"项目 {pid} 不存在"}, status=404)
    return _ok(await asyncio.to_thread(OR.card_state, pid))


async def _plan(request):
    body = await _body(request)
    names = [str(x) for x in (body.get("image_names") or [])][:9]
    pid = str(body.get("project_id") or "")
    images = OR.reference_images(names, node_ids=list(P.NODE["ref_images"]))
    if not images:
        return web.json_response({"error": "参考图为空或文件不存在，请先在参考图槽上传"},
                                 status=400)
    body = dict(body)
    body["_images"] = images
    try:
        return _ok(OR.start_planning_async(body))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)


async def _prompt_source(request):
    body = await _body(request)
    pid = str(body.get("project_id") or "")
    try:
        if OR._PLAN_RUNNING.locked():
            raise V.DirectorError("导演仍在运行，请等待本轮结束")
        selected = str(body.get("prompt_source") or "")
        plan = PJ.read(pid, "STORY_PLAN.json", default={}) or {}
        if selected == PR.MANUAL and plan.get("segments") and plan.get("global_state", {}).get("prompt_source") != PR.MANUAL:
            OR.manual_now(project_id=pid)
        else:
            PR.set_source(pid, selected)
        return _ok({"prompt_source": PR.source(pid)})
    except Exception as exc:
        return web.json_response(_err(exc), status=409)


async def _analyze(request):
    return web.json_response(
        {"error": "导演视觉识别已取消。请在参考图用途说明中填写文字，再生成剧情计划。"},
        status=410)


async def _core_dry_run(request):
    """Pure compile admission check. Never starts a model and never queues H3."""
    body = await _body(request)
    try:
        p = CORE.planner_input(
            active_slots=[int(x) for x in (body.get("active_slots") or [])],
            reference_usage=str(body.get("reference_usage") or ""),
            story_goal=str(body.get("story_goal") or ""),
            total_seconds=float(body.get("total_seconds") or 10),
            segment_seconds=float(body.get("segment_seconds") or 10),
            dialogue_mode=str(body.get("dialogue_mode") or "无台词"),
            source_dialogue=str(body.get("source_dialogue") or ""),
            previous_end_state=str(body.get("previous_end_state") or ""),
            constraints=str(body.get("user_constraints") or body.get("constraints") or ""),
            planner_controls=(body.get("planner_controls") if isinstance(body.get("planner_controls"), dict) else {}))
        return _ok(p)
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)


async def _reap(request):
    """Release a registered Director runtime left behind by an earlier session."""
    body = await _body(request)
    try:
        out = await asyncio.get_running_loop().run_in_executor(
            None, lambda: RC.reap_active_director(str(body.get("provider") or "")))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok(out)


async def _task(request):
    tid = request.query.get("task_id") or ""
    st = OR.task_state(tid)
    if st is None:
        return web.json_response({"error": f"没有任务 {tid}"}, status=404)
    return _ok(st)


async def _prepare(request):
    body = await _body(request)
    try:
        instr = OR.prepare_segment(
            str(body.get("project_id") or ""),
            seed=(int(body["seed"]) if body.get("seed") not in (None, "") else None),
            same_seed=bool(body.get("same_seed")),
            reroll=bool(body.get("reroll")),
            prompt_override=str(body.get("prompt_override") or ""),
            manual_prompts=body.get("manual_prompts"))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"instruction": instr})


async def _submitted(request):
    body = await _body(request)
    try:
        st = OR.confirm_submitted(str(body.get("project_id") or ""),
                                  seed=(int(body["seed"])
                                        if body.get("seed") not in (None, "") else None))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"status": st.get("status"), "attempt": st.get("attempt")})


async def _candidate(request):
    body = await _body(request)
    try:
        out = OR.record_candidate(
            str(body.get("project_id") or ""),
            video=str(body.get("video") or ""),
            seed=(int(body["seed"]) if body.get("seed") not in (None, "") else None),
            extra={"reported_by": "front_end", "prompt_id": str(body.get("prompt_id") or "")})
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"status": out.get("status"), "candidate": out.get("current_candidate")})


async def _generation_error(request):
    body = await _body(request)
    try:
        out = SM.mark_error(str(body.get("project_id") or ""),
                            str(body.get("message") or "生成失败"))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"status": out.get("status")})


async def _accept(request):
    body = await _body(request)
    try:
        out = OR.accepted_next(str(body.get("project_id") or ""))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"status": out.get("status"),
                "current_segment": out.get("current_segment"),
                "last_accepted_segment": out.get("last_accepted_segment"),
                "queued": False})


async def _reroll(request):
    body = await _body(request)
    try:
        instr = OR.reroll_segment(str(body.get("project_id") or ""),
                                  same_seed=bool(body.get("same_seed")))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"instruction": instr})


async def _edit(request):
    body = await _body(request)
    try:
        out = OR.edit_and_recompile(
            str(body.get("project_id") or ""),
            segment_id=int(body.get("segment_id") or 0),
            beat=str(body.get("beat") or ""),
            prompt=str(body.get("prompt") or ""),
            duration=(float(body["duration"]) if body.get("duration") not in (None, "") else None),
            directives=(body.get("directives") if isinstance(body.get("directives"), dict) else None))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"recompiled": out["recompiled"]})


async def _reset(request):
    body = await _body(request)
    try:
        out = SM.reset_to(str(body.get("project_id") or ""),
                          int(body.get("segment_id") or 1))
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"status": out.get("status"), "current_segment": out.get("current_segment")})


async def _prompt_text(request):
    pid = request.query.get("project_id") or ""
    sid = int(request.query.get("segment_id") or 1)
    try:
        text = OR.segment_prompt(pid, sid)
    except Exception as exc:                                # noqa: BLE001
        return web.json_response(_err(exc), status=409)
    return _ok({"segment_id": sid, "prompt": text})


async def _pick_images(request):
    """Resolve the four V27 reference slots the UI read off the graph into real
    files, so the card can show what the director will actually see."""
    try:
        body = await _body(request)
        names = [str(x) for x in (body.get("image_names") or [])][:9]
        found = OR.reference_images(names, node_ids=list(P.NODE["ref_images"]))
        resolved = {im["slot_index"] for im in found}
        missing = [nm for i, nm in enumerate(names, start=1) if nm and i not in resolved]
        return _ok({"images": [{k: v for k, v in im.items() if k != "path"} for im in found],
                    "missing": missing})
    except Exception as exc:                                # noqa: BLE001
        # P11: this one scans the input directory and indexes into whatever came
        # back, so it is exactly as capable of raising as /start was. Every other
        # POST on this card answers a refusal with a Chinese `error` body; a bare
        # 500 here would be the only case the UI has to special-case.
        return web.json_response(_err(exc), status=409,
                                 dumps=lambda o: json.dumps(o, ensure_ascii=False))


HANDLERS = {
    ("/ping", "GET"): _ping,
    ("/health", "GET"): _health,
    ("/projects", "GET"): _projects,
    ("/state", "GET"): _state,
    ("/task", "GET"): _task,
    ("/prompt", "GET"): _prompt_text,
    ("/load_check", "POST"): _load_check,
    ("/start", "POST"): _start,
    ("/stop", "POST"): _stop,
    ("/project/create", "POST"): _create,
    ("/plan", "POST"): _plan,
    ("/prompt_source", "POST"): _prompt_source,
    ("/core/dry_run", "POST"): _core_dry_run,
    ("/analyze", "POST"): _analyze,
    ("/reap", "POST"): _reap,
    ("/prepare", "POST"): _prepare,
    ("/submitted", "POST"): _submitted,
    ("/candidate", "POST"): _candidate,
    ("/generation_error", "POST"): _generation_error,
    ("/accept", "POST"): _accept,
    ("/reroll", "POST"): _reroll,
    ("/edit", "POST"): _edit,
    ("/reset", "POST"): _reset,
    ("/pick_images", "POST"): _pick_images,
}


def register_director_routes() -> None:
    """Attach to the running PromptServer. Safe to call twice."""
    global _registered
    if _registered:
        return
    try:
        from server import PromptServer
    except ImportError:
        return
    server = getattr(PromptServer, "instance", None)
    if server is None:
        return
    for (path, method), handler in HANDLERS.items():
        full = PREFIX + path
        route = getattr(server.routes, method.lower(), None)
        if route is None:
            continue
        # GET handlers are read-only metadata; POST handlers mutate project state
        # or start/stop a model process, so only those carry the CSRF guard.
        decorated = guarded(handler) if method in _MUTATING else handler
        decorated.__name__ = f"h3v28_{path.strip('/').replace('/', '_')}"
        route(full)(decorated)
    _registered = True
    print(f"[H3_V28_Director] 导演接口已挂载 {PREFIX}/*（{len(HANDLERS)} 个端点，仅本机回环）")
