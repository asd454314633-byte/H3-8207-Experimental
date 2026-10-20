# H3 六段独立编译器桥（8207侧最小适配，2026-10-19）
# 只代理到冻结的8210编译器；缺少身份确认时 fail closed，不会另起重复实例。
import asyncio
import os
import socket
import subprocess
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web
from server import PromptServer

UPSTREAM = "http://127.0.0.1:8210"
TASK_NAME = "H3-8210-Managed"
_PID_FILE_DEFAULT = Path(__file__).resolve().parents[4] / "H3_中文提示词编译器" / "data" / "server.pid"
PID_FILE = Path(os.environ.get("H3_8210_PID_FILE", str(_PID_FILE_DEFAULT)))
_session = None
_start_lock = None


def _decode_windows_output(raw):
    # schtasks uses the Windows console codepage on Chinese installations.
    # JSON/HTTP remains UTF-8; preserve raw command errors without replacement.
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='backslashreplace')


async def _http_health():
    global _session
    if _session is None:
        # Keep the shared proxy session long-lived; only the health probe is short.
        _session = ClientSession(timeout=ClientTimeout(total=300))
    try:
        async with _session.get(
            f"{UPSTREAM}/api/health", timeout=ClientTimeout(total=4)
        ) as response:
            if response.status != 200:
                return False
            data = await response.json()
            return data.get("ok") is True
    except Exception:
        return False


async def _listener_pid():
    """Read the actual local listener owner without changing network settings."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        proc = await asyncio.create_subprocess_exec(
            "netstat.exe", "-ano", "-p", "tcp",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=flags,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
        if proc.returncode != 0:
            return None
        for line in out.decode("utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[1].endswith(":8210") and parts[3].upper() == "LISTENING":
                return int(parts[-1])
    except Exception:
        return None
    return None


def _recorded_pid():
    try:
        return int(open(PID_FILE, "r", encoding="ascii").read().splitlines()[0].strip())
    except Exception:
        return None


async def _ready():
    if not await _http_health():
        return False
    recorded = _recorded_pid()
    owner = await _listener_pid()
    return bool(recorded and owner and recorded == owner)


async def _port_open():
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 8210), timeout=0.4)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _ensure_compiler():
    global _start_lock
    if await _ready():
        return True, ""
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    async with _start_lock:
        if await _ready():
            return True, ""
        # A listening but unhealthy or identity-mismatched process is not ours to replace.
        if await _port_open():
            return False, "8210端口已有监听，但健康状态或PID身份不一致；为避免覆盖未知实例，未启动新服务。"
        try:
            proc = await asyncio.create_subprocess_exec(
                "schtasks.exe", "/Run", "/TN", TASK_NAME,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode != 0:
                detail = _decode_windows_output(stderr or stdout).strip()
                return False, f"无法启动受管任务 {TASK_NAME}：{detail or proc.returncode}"
        except Exception as exc:
            return False, f"启动受管任务失败：{exc}"
        for _ in range(50):
            if await _ready():
                return True, ""
            if await _port_open():
                return False, "8210已出现监听，但健康或PID核验未通过；未重复启动。"
            await asyncio.sleep(0.2)
        return False, "8210受管启动超时；未提交请求。"


async def _proxy(request):
    global _session
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.host}":
        return web.json_response({"error": "Origin rejected"}, status=403)
    ready, reason = await _ensure_compiler()
    if not ready:
        return web.json_response({"error": reason}, status=502)
    tail = request.match_info["tail"]
    body = await request.read()
    if _session is None:
        _session = ClientSession(timeout=ClientTimeout(total=300))
    try:
        async with _session.request(
            request.method,
            f"{UPSTREAM}/{tail}",
            data=body,
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
        ) as upstream:
            payload = await upstream.read()
            return web.Response(
                status=upstream.status,
                body=payload,
                content_type=upstream.headers.get("Content-Type", "application/json").split(";")[0],
            )
    except Exception as ex:
        return web.json_response({"error": f"8210 unreachable: {ex}"}, status=502)


def register():
    server = PromptServer.instance
    if getattr(server, "h3_compiler_bridge_installed", False):
        return
    server.h3_compiler_bridge_installed = True
    server.routes.route("*", "/h3/compiler/{tail:.*}")(_proxy)


register()
