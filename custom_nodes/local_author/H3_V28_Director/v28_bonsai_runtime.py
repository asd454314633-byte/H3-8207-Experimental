"""V28 Director - PrismML llama.cpp (Bonsai 2) local runtime controller.

Task section 6: this is a *tool directory of the 8197 project*, not a second
environment. Task section 7 + 31: the model may only be resident during PHASE A
(director planning); H3 generation must refuse to start while it is still up.

Measured facts about this machine that shaped the release gate:
  * `nvidia-smi --query-compute-apps` reports `[N/A]` for per-process memory
    here, and the card idles at ~23.3/24.4 GB with 0% util (DynamicVRAM pinned
    allocation + WSL tenants). So "GPU memory is free" is NOT a usable signal.
  * Therefore release is proven by three positive facts instead:
        (a) the llama-server process is gone (exit code observed),
        (b) its 127.0.0.1 port stops answering,
        (c) system commit charge falls back to the pre-start baseline.
    All three are sampled before/after and written to the runtime receipt log.
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import v28_paths as P
from . import v28_runtime_contract as RC

try:
    import psutil
except Exception:                                    # pragma: no cover
    psutil = None                                    # ComfyUI ships psutil; degrade hard

CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008

NOT_RELEASED_MSG = "导演模型尚未释放显存，请稍候"   # task 31, verbatim
CUDA_DISABLED_MSG = "Bonsai CUDA 未启用"

# --- server config knobs, all overridable by runtime.json -----------------
DEFAULT_SERVER = {
    "ctx_size": 32768,
    "n_parallel": 1,
    "gpu_layers": 99,
    "reasoning_budget": 2048,      # section 33: never leave -1 (unlimited)
    "reasoning_format": "deepseek",
    "no_mmap": True,
    "flash_attn": "on",
    "health_timeout_s": 600.0,     # 27B ternary load is not instant
    "stop_timeout_s": 45.0,
    "api_prefix": "/v1",
}

# thinking level -> --reasoning-budget tokens (section 33's three tiers)
THINKING_BUDGET = {"off": 0, "low": 512, "medium": 2048, "high": 4096}

_LOCK = threading.RLock()
_STATE: dict[str, Any] = {"proc": None, "pid": None, "port": None,
                          "started_at": None, "purpose": "", "log_path": "",
                          # `thinking` is a command-line tier, not a request field: it
                          # has to be knowable after the fact or the reuse path silently
                          # serves whatever the previous caller asked for (P11 TEST3).
                          "thinking": None}


class RuntimeError_(Exception):
    """Any failure that should surface as a Chinese message rather than a crash."""


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------
def find_server_exe() -> Path | None:
    cands = [P.BONSAI_RUNTIME_DIR / "llama-server.exe"]
    cands += [Path(x) for x in glob.glob(str(P.BONSAI_RUNTIME_DIR / "**" / "llama-server.exe"),
                                        recursive=True)]
    cands += [Path(x) for x in glob.glob(str(P.BONSAI_ROOT / "**" / "llama-server.exe"),
                                        recursive=True)]
    for c in cands:
        if c.is_file():
            return c
    return None


def find_model(kind: str = "main") -> Path | None:
    """kind: main | mmproj | fallback_main. Never guess a name - glob the official ones."""
    pats = {
        "main": ["Ternary-Bonsai-2-27B-PQ2_0.gguf", "Ternary-Bonsai-2-27B-PTQ1_0.gguf",
                 "*Bonsai-2-27B-PQ2_0*.gguf", "*Bonsai-2*.gguf"],
        "fallback_main": ["Ternary-Bonsai-2-27B-PTQ1_0.gguf", "*Bonsai-2-27B*.gguf"],
        "mmproj": ["Ternary-Bonsai-2-27B-mmproj-Q8_0.gguf", "*mmproj*.gguf"],
    }[kind]
    d = P.BONSAI_MODELS_DIR
    for pat in pats:
        hits = sorted(glob.glob(str(d / pat)))
        if hits:
            return Path(hits[0])
    return None


def cuda_dll_dirs() -> list[str]:
    """The llama.cpp CUDA releases keep cudart/cublas next to the exes or in cudart/."""
    out = []
    for sub in ("", "cudart"):
        d = P.BONSAI_RUNTIME_DIR / sub if sub else P.BONSAI_RUNTIME_DIR
        if any(d.glob("cudart64_*.dll")) or any(d.glob("ggml-cuda.dll")):
            out.append(str(d.resolve()))
    return out


def cuda_start_gate(pid: int, log_path: str | Path) -> dict:
    """Fail-closed proof that the resident Bonsai server is a CUDA process."""
    names: set[str] = set()
    if psutil is not None:
        try:
            names = {Path(m.path).name.lower() for m in psutil.Process(int(pid)).memory_maps()
                     if getattr(m, "path", "")}
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            names = set()
    try:
        log = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        log = ""
    try:
        pmon = subprocess.run(["nvidia-smi", "pmon", "-s", "um", "-c", "1"],
                              capture_output=True, text=True, timeout=15)
        compute_visible = pmon.returncode == 0 and any(
            len(line.split()) > 3 and line.split()[1] == str(int(pid))
            and line.split()[2] == "C" for line in pmon.stdout.splitlines()
            if line.strip() and not line.lstrip().startswith("#"))
    except (OSError, subprocess.SubprocessError):
        compute_visible = False
    cuda_buffers = all(token in log for token in
                       ("CUDA0 model buffer", "CUDA0 KV buffer", "CUDA0 compute buffer"))
    verdict = {
        "CUDA_BACKEND_REGISTERED": "CUDA0" in log and cuda_buffers,
        "GGML_CUDA_LOADED": "ggml-cuda.dll" in names,
        "CUBLAS_LOADED": any(n.startswith("cublas64_") for n in names),
        "CUDART_LOADED": any(n.startswith("cudart64_") for n in names),
        "NVCUDA_LOADED": "nvcuda.dll" in names,
        "GPU_COMPUTE_VISIBLE": compute_visible,
        "CPU_DOMINANT": not cuda_buffers,
    }
    verdict["passed"] = (verdict["CUDA_BACKEND_REGISTERED"]
                         and verdict["GGML_CUDA_LOADED"]
                         and verdict["GPU_COMPUTE_VISIBLE"]
                         and not verdict["CPU_DOMINANT"])
    return verdict


# --------------------------------------------------------------------------
# runtime.json - the single place the port/pid are recorded (task section 6)
# --------------------------------------------------------------------------
def load_runtime_config() -> dict:
    cfg = dict(DEFAULT_SERVER)
    stored = P.read_json(P.RUNTIME_JSON, default=None)
    if isinstance(stored, dict):
        cfg.update(stored.get("server", {}))
        cfg["_record"] = stored
    cfg["model_main"] = str(find_model("main") or "")
    cfg["mmproj"] = str(find_model("mmproj") or "")
    cfg["server_exe"] = str(find_server_exe() or "")
    return cfg


def save_runtime_config(patch: dict) -> dict:
    with _LOCK:
        stored = P.read_json(P.RUNTIME_JSON, default=None) or {}
        stored = stored if isinstance(stored, dict) else {}
        srv = dict(stored.get("server") or {})
        srv.update(patch)
        stored["server"] = srv
        stored.setdefault("host", P.DIRECTOR_HOST)
        stored["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        P.atomic_write_json(P.RUNTIME_JSON, stored)
        return stored


def record_runtime(fields: dict) -> dict:
    """Append a lifecycle record (port/pid/state timestamps) to runtime.json."""
    with _LOCK:
        stored = P.read_json(P.RUNTIME_JSON, default=None) or {}
        stored = stored if isinstance(stored, dict) else {}
        hist = list(stored.get("history") or [])
        hist = (hist + [fields])[-40:]
        stored["history"] = hist
        stored.update({k: v for k, v in fields.items() if k != "kind"})
        P.atomic_write_json(P.RUNTIME_JSON, stored)
        return stored


# --------------------------------------------------------------------------
# port + socket helpers (task section 6's forbidden list)
# --------------------------------------------------------------------------
def port_is_free(port: int) -> bool:
    if port in P.FORBIDDEN_PORTS:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((P.DIRECTOR_HOST, port))
            return True
        except OSError:
            return False


def probe_free_port(preferred: int | None = None) -> int:
    if preferred and preferred not in P.FORBIDDEN_PORTS and port_is_free(preferred):
        return int(preferred)
    for port in range(P.DIRECTOR_PORT_MIN, P.DIRECTOR_PORT_MAX + 1):
        if port in P.FORBIDDEN_PORTS:
            continue
        if port_is_free(port):
            return port
    raise RuntimeError_(f"端口区间 {P.DIRECTOR_PORT_MIN}-{P.DIRECTOR_PORT_MAX} 无空闲端口")


def port_listening(port: int, host: str = P.DIRECTOR_HOST, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# resource sampling - the numbers behind the release verdict
# --------------------------------------------------------------------------
# --- commit measurement ----------------------------------------------------
# Measured on this box (2026-09-27): ctypes.windll.kernel32 has NO
# "GetProcessMemoryInfo" (only K32GetProcessMemoryInfo), and psapi has no
# K32* alias; and the GetCurrentProcess() pseudo handle must be passed as a
# pointer, because a plain Python int -1 is marshalled as a 32-bit int and the
# callee then sees an invalid handle. Getting this wrong made the whole commit
# leg of the release verdict silently return None - which reads as "no memory
# was freed", not as "the ruler is broken". Both are fixed below and the probe
# test keeps a positive control (a child that commits 2 GB) so the ruler is
# re-verified, not assumed.
_PMC_FIELDS = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
               ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
               ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
               ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
               ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
               ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = _PMC_FIELDS


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


def _pmi_fn():
    """Return (callable, owner_dll) for GetProcessMemoryInfo on this Windows build."""
    for dll_name, fn_name in (("psapi", "GetProcessMemoryInfo"),
                              ("kernel32", "K32GetProcessMemoryInfo")):
        try:
            fn = getattr(getattr(ctypes.windll, dll_name), fn_name)
        except (AttributeError, OSError):
            continue
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        return fn
    return None


def commit_kb() -> int | None:
    """System commit charge in KB. None means UNMEASURED and must never be read as 0."""
    try:
        ms = _MemoryStatusEx()
        ms.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            return None
        return int((ms.ullTotalPageFile - ms.ullAvailPageFile) // 1024)
    except Exception:
        return None


def proc_commit_kb(pid: int | None) -> int | None:
    """Per-process private commit (pagefile-backed) in KB for one pid.

    This is the targeted measurement: the 27B is loaded by ONE process, and on this
    card per-process VRAM is not observable, so its commit is the honest proxy for
    "the allocation came back".
    """
    if not pid:
        return None
    if psutil is not None:
        try:
            mi = psutil.Process(int(pid)).memory_info()
            pf = int(getattr(mi, "pagefile", 0) or 0)
            if pf:
                return pf // 1024
        except Exception:
            pass
    fn = _pmi_fn()
    if fn is None:
        return None
    try:
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
        h = k32.OpenProcess(0x1000 | 0x0010, 0, int(pid))
        if not h:
            return None
        try:
            pmc = _ProcessMemoryCountersEx()
            pmc.cb = ctypes.sizeof(_ProcessMemoryCountersEx)
            if not fn(h, ctypes.byref(pmc), pmc.cb):
                return None
            return int(pmc.PagefileUsage // 1024)
        finally:
            k32.CloseHandle(ctypes.c_void_p(h))
    except Exception:
        return None


def vram_used_mib() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=8.0)
        if out.returncode != 0:
            return None
        first = (out.stdout or "").strip().splitlines()[0].strip()
        return int(float(first))
    except Exception:
        return None


def sample_resources(pid: int | None = None) -> dict:
    d: dict[str, Any] = {"t": time.time(), "commit_kb": commit_kb(),
                         "vram_used_mib": vram_used_mib(),
                         "director_commit_kb": proc_commit_kb(pid or _STATE.get("pid"))}
    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            d.update(ram_total=vm.total, ram_available=vm.available, ram_percent=vm.percent)
            pm = psutil.swap_memory()
            d.update(swap_percent=pm.percent)
        except Exception:
            pass
    return d


def _proc_rss(pid: int | None) -> int:
    if psutil is None or not pid:
        return 0
    try:
        return int(psutil.Process(pid).memory_info().rss)
    except Exception:
        return 0


# --------------------------------------------------------------------------
# HTTP against the local server
# --------------------------------------------------------------------------
class NoProxyOpener:
    """127.0.0.1 must never go through the machine's proxy (7897)."""
    _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def open(cls, req, timeout: float):
        return cls._opener.open(req, timeout=timeout)


def api_json(path: str, payload: dict | None = None, timeout: float = 60.0,
             method: str = "POST", *, port: int | None = None) -> dict:
    port = port or _STATE.get("port") or (P.read_json(P.RUNTIME_JSON, default={}) or {}).get("port")
    if not port:
        raise RuntimeError_("导演服务尚未启动，没有可用端口")
    url = f"http://{P.DIRECTOR_HOST}:{int(port)}{path}"
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with NoProxyOpener.open(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError_(f"导演服务返回 {e.code}: {e.read().decode('utf-8','replace')[:300]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError_(f"导演服务无响应: {type(e).__name__} {e}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError_(f"导演服务返回非 JSON: {body[:200]}")


# --------------------------------------------------------------------------
# "is the 27B resident right now?" - memory state with a disk fallback
# --------------------------------------------------------------------------
# _STATE is process-local. llama-server is spawned DETACHED_PROCESS, so when ComfyUI
# restarts (or this module is reloaded) the director keeps serving and keeps the model
# resident while _STATE goes empty. If every read path only consulted _STATE, a restart
# would turn "still loaded" into a false "released" - which is exactly what task 31 and
# task 7 forbid (Bonsai 2 and H3 generation must never sit on the GPU together). So the
# single resolver below also reads runtime.json, and identifies the thing it finds
# instead of trusting a pid that may have been recycled after a reboot.

DIRECTOR_IDENTITY_HINTS = ("llama-server", "bonsai", "ternary")


def stored_target() -> dict:
    """The pid/port recorded on disk by the last start, if any."""
    stored = P.read_json(P.RUNTIME_JSON, default={}) or {}
    if not isinstance(stored, dict):
        return {}
    return {"pid": stored.get("pid"), "port": stored.get("port"),
            "kind": stored.get("kind"), "last_start": stored.get("last_start"),
            "history_len": len(stored.get("history") or [])}


def _identity_is_director(pid: int, port) -> bool | None:
    """Reject a recycled pid. None == cannot be confirmed either way (no psutil)."""
    if psutil is None:
        return None
    try:
        p = psutil.Process(int(pid))
        if "llama-server" in (p.name() or "").lower():
            return True
        cmd = " ".join(p.cmdline() or []).lower()
        if "llama-server" in cmd:
            return True
        # our own command-line fingerprint from build_command(), for a renamed binary
        if "--reasoning-budget" in cmd and "--alias" in cmd:
            return True
        return False
    except Exception:
        return False


def _director_answers(port: int) -> bool | None:
    """Does this port talk like our server? True/False, None when inconclusive."""
    try:
        j = api_json("/v1/models", None, timeout=4.0, method="GET", port=int(port))
    except RuntimeError_ as e:
        t = str(e).lower()
        if " refused" in t or "10061" in t or "connectionerror" in t:
            return False                 # nothing of ours behind that port
        return None                      # timeout / reset: inconclusive, do not clear
    except Exception:
        return None
    blob = json.dumps(j, ensure_ascii=False).lower()
    if any(h in blob for h in DIRECTOR_IDENTITY_HINTS):
        return True
    return False if isinstance(j, dict) and "data" in j else None


def live_thinking() -> str | None:
    """Which reasoning tier the director that exists right now was started with.

    In-process memory first, then the `start` record on disk - the same two-source
    rule live_target() uses, because an orphan from a previous ComfyUI session is
    still holding a real --reasoning-budget.
    """
    tier = _STATE.get("thinking")
    if tier:
        return str(tier)
    for rec in reversed((P.read_json(P.RUNTIME_JSON, default={}) or {}).get("history") or []):
        if not isinstance(rec, dict):
            continue
        if rec.get("kind") == "start":
            return str(rec.get("thinking") or "") or None
        if rec.get("kind") == "stop":
            return None          # the resident server died after this record
    return None


def live_target() -> dict:
    """Resolve the director server that exists *right now*, from memory and from disk.

    {"running","pid","port","owned","source","evidence","confirmable"} - `owned` means
    this ComfyUI process still holds the Popen handle, i.e. it can terminate directly.
    """
    with _LOCK:
        proc = _STATE.get("proc")
        pid = _STATE.get("pid")
        port = _STATE.get("port")
        owned = bool(pid or proc)
        source = "memory"
        if not owned:
            st = stored_target()
            pid, port = st.get("pid"), st.get("port")
            source = "disk" if (pid or port) else "none"
        evidence: list[str] = []
        if source == "none":
            return {"running": False, "pid": None, "port": None, "owned": False,
                    "source": "none", "confirmable": True,
                    "evidence": ["runtime.json 没有启动记录"]}

        alive: bool | None = None
        if proc is not None:
            try:
                alive = proc.poll() is None
                evidence.append(f"popen.poll()->{alive}")
            except Exception:
                alive = None
        if alive is None and pid:
            alive = _pid_alive(int(pid))
            if alive and source == "disk":
                ident = _identity_is_director(int(pid), port)
                evidence.append(f"pid identity->{ident}")
                if ident is False:
                    alive = False         # recycled pid, not our model process
                elif ident is None:
                    evidence.append("identity unconfirmed: fail closed")

        listening = bool(port and port_listening(int(port), timeout=0.5))
        evidence.append(f"port {port} listening->{listening}")
        http: bool | None = _director_answers(int(port)) if listening else None
        if listening:
            evidence.append(f"http identity->{http}")

        # Decision table. Positive facts only:
        #   pid provably alive AND identified as ours            -> resident
        #   the port answers /v1/models as our bonsai alias      -> resident
        #   pid liveness unknown (no psutil, identity undecided) -> resident (fail closed)
        #   pid provably gone AND the port is not our director   -> released
        if alive is True or http is True:
            running, basis = True, "positive identity"
        elif alive is None:
            running, basis = True, "pid liveness unverifiable: fail closed"
        elif listening:
            # our detached server cannot answer with a dead pid, so a port that does
            # not speak like the director is somebody else's listener on a re-issued port
            running = http is True
            basis = "http said it is ours" if running else "pid gone + port not ours"
        else:
            running, basis = False, "pid gone and port closed"
        evidence.append(basis)
        confirmable = not (alive is None and http is not True)
        return {"running": running, "pid": pid, "port": port, "owned": owned,
                "source": source, "confirmable": confirmable,
                "evidence": evidence[-6:]}


def server_running() -> bool:
    return bool(live_target()["running"])


# --------------------------------------------------------------------------
# start / stop
# --------------------------------------------------------------------------
def build_command(cfg: dict, purpose: str) -> tuple[list[str], dict]:
    exe = cfg.get("server_exe") or str(find_server_exe() or "")
    model = cfg.get("model_main") or str(find_model("main") or "")
    mmproj = cfg.get("mmproj") or str(find_model("mmproj") or "")
    if not exe:
        raise RuntimeError_("找不到 PrismML llama.cpp 的 llama-server.exe（runtime 目录为空）")
    if not model:
        raise RuntimeError_("找不到 Bonsai 2 模型文件（models 目录为空）")
    if not cfg.get("port"):
        cfg["port"] = probe_free_port(cfg.get("port"))
    budget = THINKING_BUDGET.get(cfg.get("thinking", "medium"),
                                 int(cfg.get("reasoning_budget") or 2048))
    cmd = [exe,
           "--model", model,
           "--alias", "bonsai2",
           "--gpu-layers", str(int(cfg.get("gpu_layers", 99))),
           "--ctx-size", str(int(cfg.get("ctx_size", 32768))),
           # P11 TEST1: the shipped build (PrismML llama.cpp b10743 / adfffbe41)
           # rejects `--n-parallel` outright - `error: invalid argument:
           # --n-parallel` - and exits 1 five seconds in, so the director never
           # came up at all. That spelling is upstream's retired one; this build
           # calls the same thing `--parallel` / `-np` ("number of server slots").
           # The CONFIG key stays `n_parallel` (it is V28 vocabulary, quoted in
           # the docs and in runtime.json); only the CLI token changed.
           # `--no-display-prompt` was dropped in the same pass: it is a
           # llama-cli-only flag and does not appear in llama-server's help in
           # this build either - it would have been the next rejection.
           "--parallel", str(int(cfg.get("n_parallel", 1))),
           "--host", P.DIRECTOR_HOST,
           "--port", str(int(cfg["port"])),
           "--reasoning-budget", str(int(budget)),
           "--reasoning-format", str(cfg.get("reasoning_format", "deepseek")),
           "--flash-attn", str(cfg.get("flash_attn", "on")),
           "-lv", "4",
           # P11 TEST1, third finding: `--log-disable` made a SUCCESSFUL start
           # write a 0-byte log, so the per-start receipt (how many layers really
           # reached VRAM, the ctx that was allocated, load seconds) simply did
           # not exist - only the pre-logging argument errors ever got out. The
           # default log level is what the card's "log" field and P11 point at,
           # so it stays on; `--verbose` remains opt-in through verbose_log.
           *(["--verbose"] if cfg.get("verbose_log") else [])]
    if mmproj and os.path.isfile(mmproj):
        cmd += ["--mmproj", mmproj]
    else:
        cmd += ["--no-mmproj"]
    if cfg.get("no_mmap"):
        cmd += ["--no-mmap"]
    if cfg.get("temp") is not None:
        cmd += ["--temp", str(float(cfg["temp"]))]
    env = dict(os.environ)
    dirs = cuda_dll_dirs()
    if dirs:
        env["PATH"] = os.pathsep.join(dirs) + os.pathsep + env.get("PATH", "")
    env.setdefault("CUDA_VISIBLE_DEVICES", env.get("CUDA_VISIBLE_DEVICES", "0"))
    env["PYTHONUNBUFFERED"] = "1"
    return cmd, env


def needs_tier_restart(requested: str | None, live: str | None) -> bool:
    """Must the resident server be re-launched to honour `requested`?

    Only two *known* tiers can disagree. A None / unrecognised live tier means the
    record is missing (an orphan started by a build that did not log it), and
    restarting on a guess would throw away a working 27B model for nothing.
    """
    return (requested in THINKING_BUDGET and live in THINKING_BUDGET
            and requested != live)


def start_server(purpose: str = "plan", thinking: str = "medium") -> dict:
    """PHASE A entry. Idempotent; blocks until /health says ready or budget runs out."""
    with _LOCK:
        tgt = live_target()
        if tgt["running"] and not tgt["owned"]:
            # A director recorded on disk that this ComfyUI process does not own can
            # only mean a previous session left it resident. Spawning now would put
            # two 27B models on one card (task 5/6), so it is reaped first and the
            # release receipt is carried out for the UI to show.
            reaped = stop_server()
            out = {"ok": True, "reused": False, "reaped_orphan": reaped}
        else:
            out = {}
        if tgt["running"] and tgt["owned"]:
            live = live_thinking()
            if needs_tier_restart(thinking, live):
                # P11 TEST3: the reasoning tier is a --reasoning-budget COMMAND-LINE
                # flag, and the running server ignores every per-request equivalent -
                # measured, not assumed: reasoning_budget / chat_template_kwargs.reasoning
                # / thinking in the POST body each returned a byte-identical reply
                # (reasoning_content 116 chars, completion_tokens 38) against a server
                # started at low. So "reused: True, tier silently different" is the only
                # way to get the asked-for budget: stop, then start at the right tier.
                # Cost is one release (measured 1.1s) + one load (measured 3.8s), against
                # the 200+ second generation it replaces.
                record_runtime({"kind": "tier_restart", "from": live, "to": thinking,
                                "pid": tgt.get("pid"), "port": tgt.get("port")})
                verdict = stop_server()
                if not verdict.get("released"):
                    # Never stack a second 27B on top of one that did not let go.
                    raise RuntimeError_(
                        f"切换推理档位失败：旧导演进程尚未释放（{verdict.get('not_released_message')}），"
                        f"已停止切换，不会叠第二个模型")
                out = {"ok": True, "reused": False, "tier_restarted": f"{live}->{thinking}"}
                tgt = {"running": False, "owned": False}
            else:
                gate = cuda_start_gate(int(tgt["pid"]), _STATE.get("log_path") or
                                       (P.read_json(P.RUNTIME_JSON, default={}) or {}).get("log", ""))
                if not gate["passed"]:
                    record_runtime({"kind": "cuda_gate_fail", "pid": tgt.get("pid"),
                                    "port": tgt.get("port"), "DIRECTOR_START": "FAIL", **gate})
                    stop_server(force=True)
                    raise RuntimeError_(f"{CUDA_DISABLED_MSG}：已停止导演服务，禁止 CPU fallback")
                return {"ok": True, "reused": True, "thinking": live,
                        "cuda_gate": gate, **_public_state(tgt)}
        cfg = load_runtime_config()
        cfg["thinking"] = thinking
        cfg["purpose"] = purpose
        base = sample_resources()
        log_path = P.BONSAI_LOGS_DIR / f"bonsai_server_{time.strftime('%Y%m%d_%H%M%S')}.log"
        cmd, env = build_command(cfg, purpose)
        P.ensure_dirs()
        # last line of defence before a port is handed to a detached process
        port = int(cfg["port"])
        if port in P.FORBIDDEN_PORTS or not port_is_free(port):
            raise RuntimeError_(f"端口 {port} 属于禁用清单或已被占用，不能启动导演服务")
        t0 = time.time()
        try:
            logf = open(log_path, "ab", buffering=0)
            proc = subprocess.Popen(cmd, cwd=str(P.BONSAI_RUNTIME_DIR), env=env,
                                    stdout=logf, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL,
                                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
        except OSError as e:
            raise RuntimeError_(f"无法启动导演服务: {type(e).__name__} {e}")
        _STATE.update(proc=proc, pid=proc.pid, port=int(cfg["port"]),
                      started_at=t0, purpose=purpose, log_path=str(log_path),
                      thinking=thinking, baseline=base)
        record_runtime({"kind": "start", "pid": proc.pid, "port": int(cfg["port"]),
                        "cmd": cmd, "model": cfg.get("model_main"),
                        "mmproj": cfg.get("mmproj"), "thinking": thinking,
                        "baseline": base, "log": str(log_path)})
        deadline = t0 + float(cfg.get("health_timeout_s", 600.0))
        last_err = ""
        while time.time() < deadline:
            rc = proc.poll()
            if rc is not None:
                tail = _tail(log_path, 1200)
                _STATE.update(proc=None, pid=None, port=None, thinking=None)
                raise RuntimeError_(
                    f"导演服务启动失败（进程已退出 code={rc}）。日志摘要：{tail}")
            try:
                j = api_json("/health", None, timeout=4.0, method="GET")
                ok = isinstance(j, dict) and j.get("status") in (None, "ok")
            except Exception as e:
                ok, last_err = False, str(e)[:200]
            if ok or _health_tcp_open(int(cfg["port"])):
                break
            time.sleep(1.5)
        else:
            stop_server()
            raise RuntimeError_(f"导演服务在 "
                                f"{cfg.get('health_timeout_s')} 秒内没有就绪。{last_err}")
        ready = time.time() - t0
        # a real chat round-trip proves the binary actually loaded the ternary weights
        try:
            api_json("/v1/models", None, timeout=30.0, method="GET")
        except RuntimeError_ as e:
            stop_server()
            raise RuntimeError_(f"导演服务不可用: {e}")
        gate = cuda_start_gate(proc.pid, log_path)
        if not gate["passed"]:
            record_runtime({"kind": "cuda_gate_fail", "pid": proc.pid,
                            "port": int(cfg["port"]), "DIRECTOR_START": "FAIL", **gate})
            stop_server(force=True)
            raise RuntimeError_(f"{CUDA_DISABLED_MSG}：已停止导演服务，禁止 CPU fallback")
        _STATE["ready_in_s"] = round(ready, 1)
        record_runtime({"kind": "ready", "pid": proc.pid, "port": int(cfg["port"]),
                        "ready_in_s": round(ready, 1), "DIRECTOR_START": "PASS",
                        **gate})
        return {"ok": True, "reused": False, "ready_in_s": round(ready, 1),
                "cuda_gate": gate, **out, **_public_state()}


def _health_tcp_open(port: int) -> bool:
    """Some builds answer /health with a bare 200 and no JSON body."""
    try:
        req = urllib.request.Request(f"http://{P.DIRECTOR_HOST}:{port}/health",
                                     headers={"Accept": "*/*"})
        with NoProxyOpener.open(req, timeout=3.0) as r:
            return 200 <= int(getattr(r, "status", 200)) < 300
    except Exception:
        return False


def stop_server(timeout: float | None = None, *, force: bool = False) -> dict:
    """PHASE A exit. Returns the release verdict; the H3 gate reads it (task 31).

    Driven by live_target(), never by _STATE alone: after a ComfyUI restart the orphan
    still holds the model, and a verdict computed from empty memory state would read
    "process gone, port free, released" - a false green light for H3 generation.
    """
    with _LOCK:
        tgt = live_target()
        proc = _STATE.get("proc") if tgt["owned"] else None
        pid, port = tgt.get("pid"), tgt.get("port")
        base = dict(_STATE.get("baseline") or {})
        stored = P.read_json(P.RUNTIME_JSON, default={}) or {}
        base = base or (stored.get("baseline") or {})
        cfg = load_runtime_config()
        to = float(timeout if timeout is not None else cfg.get("stop_timeout_s", 45.0))
        before = sample_resources(int(pid) if pid else None)
        if pid and (tgt["running"] or _pid_alive(int(pid))):
            _terminate(int(pid), proc, to, force)
        # wait for the kernel to give the GPU allocations back
        exit_code = None
        if proc is not None:
            try:
                exit_code = proc.wait(timeout=to)
            except Exception:
                exit_code = None
        elif pid:
            exit_code = _wait_pid_exit(int(pid), to)
        deadline = time.time() + max(3.0, to / 3.0)
        port_down = not port_listening(int(port), timeout=0.5) if port else True
        while not port_down and time.time() < deadline:
            time.sleep(0.4)
            port_down = not port_listening(int(port), timeout=0.5)
        gone = not pid or not _pid_alive(int(pid))
        after = _wait_commit_release(before, base, deadline=time.time() + to,
                                     pid=int(pid) if pid else None)
        _STATE.update(proc=None, pid=None, port=None, purpose="", thinking=None)
        verdict = release_verdict(before, after, base, gone, port_down, exit_code)
        verdict.update(target_found=tgt["source"] != "none", source=tgt["source"],
                       confirmable=tgt["confirmable"], identity_evidence=tgt["evidence"])
        if tgt["source"] == "none":
            verdict["note"] = "本机没有导演服务记录，无需释放"
        # once released, the disk record must stop pointing at a dead pid: a later
        # live_target() would otherwise probe a port that may have been re-issued.
        clear = {"pid": None, "port": None} if verdict["released"] else {"pid": pid, "port": port}
        record_runtime({"kind": "stop", **clear, "finalized_pid": pid,
                        "finalized_port": port, **verdict})
        _append_receipt(verdict, pid=pid, port=port, exit_code=exit_code)
        return verdict


def _wait_pid_exit(pid: int, to: float):
    """No Popen handle (restart / orphan case): poll until the pid disappears.

    Returns an int exit code when psutil can supply one, None when the process was
    already gone, or the string 'still_running' when it survived the whole budget.
    """
    if psutil is not None:
        try:
            return psutil.Process(int(pid)).wait(timeout=max(2.0, to))
        except psutil.NoSuchProcess:
            return None
        except Exception:
            pass
    deadline = time.time() + max(2.0, to)
    while time.time() < deadline:
        if not _pid_alive(int(pid)):
            return None
        time.sleep(0.5)
    return "still_running"


def _terminate(pid: int, proc, to: float, force: bool) -> None:
    if proc is not None and proc.poll() is None:
        if force:
            proc.kill()
        else:
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=max(2.0, to * 0.6))
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
    elif psutil is not None:
        try:
            p = psutil.Process(int(pid))
            p.terminate()
            p.wait(timeout=max(2.0, to * 0.4))
        except Exception:
            try:
                psutil.Process(int(pid)).kill()
            except Exception:
                pass
    else:
        # no Popen handle and no psutil (restart with a bare interpreter): the only
        # way to honour "release before generating" is a direct, pid-targeted kill.
        # There is no graceful channel to a DETACHED_PROCESS without a handle, and
        # live_target() already proved this pid is (or was) our llama-server.
        _win_terminate(int(pid))


def _win_terminate(pid: int) -> bool:
    """PROCESS_TERMINATE on a pid we already identified as our llama-server.

    Deliberately separate from probing - _win_pid_alive only ever asks for
    QUERY_LIMITED_INFORMATION, and os.kill(pid, 0) is never called anywhere in this
    module: on Windows, across consoles, it can TerminateProcess(h, 0).
    """
    try:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x0001 | 0x1000, False, pid)   # TERMINATE | QUERY_LIMITED
        if not h:
            return False
        try:
            return bool(k32.TerminateProcess(h, 0))
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    """Never os.kill(pid, 0) here: on Windows that can TERMINATE a process in another
    console. Both paths below are read-only handle queries."""
    if psutil is not None:
        try:
            p = psutil.Process(int(pid))
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except Exception:
            return _win_pid_alive(int(pid))
    return _win_pid_alive(int(pid))


def _win_pid_alive(pid: int) -> bool:
    """Read-only liveness. Only PROCESS_QUERY_LIMITED_INFORMATION is requested, and
    the handle is always closed - this runs on every gate probe."""
    try:
        STILL_ACTIVE = 259
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)      # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_uint32()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def _wait_commit_release(before: dict, base: dict, deadline: float, pid=None) -> dict:
    """Poll until system commit settles, then return the final sample."""
    after = before
    floor = (base.get("commit_kb") or before.get("commit_kb") or 0)
    while time.time() < deadline:
        after = sample_resources(pid)
        c = after.get("commit_kb") or 0
        if not floor or c <= floor * 1.02:
            return after
        time.sleep(0.6)
    return after


def release_verdict(before: dict, after: dict, base: dict,
                    process_gone: bool, port_down: bool, exit_code) -> dict:
    c_before = before.get("commit_kb") or 0
    c_after = after.get("commit_kb") or 0
    c_base = base.get("commit_kb") or c_before
    freed = c_before - c_after
    floor_ok = (not c_base) or (c_after <= c_base * 1.03)
    v_before = before.get("vram_used_mib")
    v_after = after.get("vram_used_mib")
    vram_delta = None if (v_before is None or v_after is None) else v_before - v_after
    d_before = before.get("director_commit_kb")
    d_after = after.get("director_commit_kb")
    commit_measured = bool(before.get("commit_kb") and after.get("commit_kb"))
    return {
        "process_exited": bool(process_gone),
        "exit_code": exit_code,
        "port_closed": bool(port_down),
        "commit_measured": commit_measured,
        "commit_before_kb": c_before,
        "commit_after_kb": c_after,
        "commit_freed_mb": round(freed / 1024.0, 1),
        "director_commit_before_kb": d_before,
        "director_commit_after_kb": d_after,
        # the director process's own private commit: 0/None after exit is the direct
        # evidence its allocation came back, independent of what the rest of the box does
        "director_commit_freed_mb": round(((d_before or 0) - (d_after or 0)) / 1024.0, 1),
        "commit_back_to_baseline": bool(floor_ok),
        # which floor we compared against is part of the evidence: an orphan release
        # has no pre-start sample of its own, so its baseline is the stop-time sample
        "baseline_source": "pre_start_record" if base.get("commit_kb") else "stop_time_sample",
        "vram_before_mib": v_before,
        "vram_after_mib": v_after,
        "vram_freed_mib": vram_delta,
        # per-process VRAM is not observable on this box, so vram is advisory only;
        # commit must actually have been MEASURED - an unmeasured leg may never read
        # as "released" (that is how the old ctypes bug hid a dead ruler).
        "released": bool(process_gone and port_down and floor_ok and commit_measured),
        "not_released_message": NOT_RELEASED_MSG,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# --------------------------------------------------------------------------
# the gate the H3 submit path must consult (task 7 + 31)
# --------------------------------------------------------------------------
def generation_gate(refresh: bool = False) -> tuple[bool, str, dict]:
    """(allowed, chinese_message, details). Blocking while Bonsai is resident.

    `live_target()` is disk-aware, so a ComfyUI restart that leaves the 27B loaded
    still reports bonsai_running=True here: the refusal (task 31) survives the restart.
    """
    with _LOCK:
        tgt = live_target()
        info = _public_state(tgt)
        if not tgt["running"]:
            return True, "", {"bonsai_running": False, **info}
        return False, NOT_RELEASED_MSG, {"bonsai_running": True, **info}


def _live_view(tgt: dict) -> dict:
    return {"target_source": tgt["source"], "owned_by_this_session": tgt["owned"],
            "orphan": bool(tgt["running"] and not tgt["owned"]),
            "confirmable": tgt["confirmable"], "identity_evidence": list(tgt["evidence"])}


def reap_orphan(*, timeout: float | None = None) -> dict:
    """PHASE A cleanup for the case ComfyUI restarted and no longer owns the process.

    Goes through stop_server(), so an orphan release produces the same measured
    receipt (process gone + port closed + commit back to baseline) as an owned one.
    """
    tgt = live_target()
    out = {"reaped": False, "pid": tgt["pid"], "port": tgt["port"],
           "source": tgt["source"], "was_running": tgt["running"],
           "identity_evidence": list(tgt["evidence"])}
    if not tgt["running"] and not tgt["pid"]:
        out["skipped"] = "runtime.json 没有在册的导演服务"
        return out
    if not tgt["running"]:
        out["skipped"] = "进程已不在，仅清理登记"
        record_runtime({"kind": "reap_noop", "pid": tgt["pid"], "port": tgt["port"]})
        return out
    verdict = stop_server(timeout)
    out.update(reaped=bool(verdict.get("released")), release=verdict)
    return out


def _public_state(tgt: dict | None = None) -> dict:
    tgt = tgt or live_target()
    tier = live_thinking() if tgt.get("running") else None
    cfg = load_runtime_config()
    return {"pid": tgt.get("pid"), "port": tgt.get("port"),
            "purpose": _STATE.get("purpose"), "started_at": _STATE.get("started_at"),
            # The tier and the token budget it maps to have to be readable together:
            # P11 TEST3 could only diagnose "why did the answer never arrive" by
            # reading two server logs, because nothing on the card said which
            # --reasoning-budget was actually serving the request.
            "thinking": tier,
            "reasoning_budget": (THINKING_BUDGET.get(tier) if tier in THINKING_BUDGET
                                 else None) if tier else None,
            "log": _STATE.get("log_path", ""), **_live_view(tgt)}


def _append_receipt(verdict: dict, *, pid, port, exit_code) -> None:
    line = (f"[{verdict['measured_at']}] stop pid={pid} port={port} exit={exit_code} "
            f"process_exited={verdict['process_exited']} port_closed={verdict['port_closed']} "
            f"commit_measured={verdict.get('commit_measured')} "
            f"commit={verdict['commit_before_kb']}->{verdict['commit_after_kb']}KB "
            f"(freed {verdict['commit_freed_mb']}MB) "
            f"director_commit={verdict.get('director_commit_before_kb')}->"
            f"{verdict.get('director_commit_after_kb')}KB "
            f"baseline_ok={verdict['commit_back_to_baseline']}[{verdict.get('baseline_source')}] "
            f"vram={verdict['vram_before_mib']}->{verdict['vram_after_mib']}MiB "
            f"released={verdict['released']}\n")
    try:
        P.ensure_dirs()
        with open(P.BONSAI_LOGS_DIR / "lifecycle.log", "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _tail(path: Path, n: int) -> str:
    try:
        with open(path, "rb") as f:
            sz = os.fstat(f.fileno()).st_size
            f.seek(max(0, sz - n * 4))
            data = f.read().decode("utf-8", "replace")
        return " / ".join(x.strip() for x in data.strip().splitlines()[-6:])[:n]
    except OSError:
        return "(no log)"


def health() -> dict:
    cfg = load_runtime_config()
    free_d = shutil.disk_usage(str(P.BONSAI_ROOT)).free / 2**30
    tgt = live_target()
    out = {"running": tgt["running"], **_public_state(tgt),
           "server_exe": cfg.get("server_exe"), "model_main": cfg.get("model_main"),
           "mmproj": cfg.get("mmproj"), "disk_free_gib": round(free_d, 1),
           "psutil": psutil is not None, "resources": sample_resources()}
    stored = P.read_json(P.RUNTIME_JSON, default={}) or {}
    if isinstance(stored, dict) and stored.get("kind") == "stop":
        out["release_verdict"] = "RELEASED" if stored.get("released") else "NOT_RELEASED"
        out["release_detail"] = (f"pid 退出={stored.get('process_exited')} "
                                 f"端口关闭={stored.get('port_closed')} "
                                 f"commit 回落={stored.get('commit_back_to_baseline')} "
                                 f"释放 {stored.get('commit_freed_mb')}MB")
    out["runtime_history_len"] = stored.get("history") and len(stored["history"]) or 0
    if out["running"]:
        try:
            out["models"] = api_json("/v1/models", None, timeout=10.0, method="GET",
                                     port=tgt.get("port"))
        except RuntimeError_ as e:
            out["api_error"] = str(e)
    return out


def runtime_contract() -> RC.DirectorProviderRuntimeContract:
    tgt = live_target()
    running = bool(tgt.get("running"))
    gate = {}
    if running and tgt.get("pid"):
        gate = cuda_start_gate(int(tgt["pid"]), _STATE.get("log_path") or "")
    cfg = load_runtime_config()
    return RC.DirectorProviderRuntimeContract(
        provider_name="bonsai2",
        process_identity={"pid": tgt.get("pid"), "exe": cfg.get("server_exe")},
        server_endpoint=(f"http://{P.DIRECTOR_HOST}:{tgt.get('port')}" if tgt.get("port") else ""),
        model_alias="bonsai2", cuda_backend_loaded=bool(gate.get("GGML_CUDA_LOADED")),
        gpu_layers_requested=True, gpu_compute_confirmed=bool(gate.get("GPU_COMPUTE_VISIBLE")),
        cpu_dominant=bool(gate.get("CPU_DOMINANT", running)),
        offload_confirmed=bool(gate.get("CUDA_BACKEND_REGISTERED")),
        resident=running, released=not running)


RC.register_runtime("bonsai2", runtime_contract, stop_server, reap_orphan)
