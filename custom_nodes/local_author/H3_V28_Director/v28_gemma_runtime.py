"""Fail-closed text-only Gemma4 llama.cpp runtime for V28.2 Director."""
from __future__ import annotations
import json, os, subprocess, threading, time, urllib.request
import hashlib
from pathlib import Path

from . import v28_runtime_contract as RC

ROOT = Path(r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\director_runtime\gemma4_vision_lab")
RUNTIME = ROOT / "runtime"
EXE = RUNTIME / "llama-server.exe"
MODEL = Path(r"<DIRECTOR_RUNTIME>\incoming\llm_candidates\Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf")
PORT = 8092
LOG = ROOT / "gemma4_text_director.log"
_PROC: subprocess.Popen | None = None
_LOG_HANDLE = None
_CUDA_BACKEND_LOADED = False
_OFFLOAD_CONFIRMED = False
_GPU_COMPUTE_CONFIRMED = False
_CPU_DOMINANT = False
_LAST_PROBE: dict = {}
_LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def server_build() -> str:
    if not EXE.is_file():
        return "unavailable"
    # Identifies the exact installed binary without starting another server.
    return "sha256:" + hashlib.sha256(EXE.read_bytes()).hexdigest()


class RuntimeError_(RuntimeError): pass


def _health() -> bool:
    try:
        with _LOCAL_HTTP.open(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _cuda_context_visible(pid: int) -> bool:
    try:
        cp = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return cp.returncode == 0 and str(int(pid)) in {
            line.strip().split(",", 1)[0] for line in cp.stdout.splitlines()}
    except Exception:
        return False


def start() -> None:
    global _PROC, _LOG_HANDLE, _CUDA_BACKEND_LOADED, _OFFLOAD_CONFIRMED
    global _GPU_COMPUTE_CONFIRMED, _CPU_DOMINANT, _LAST_PROBE
    if _health():
        return
    for p in (EXE, MODEL, RUNTIME / "ggml-cuda.dll", RUNTIME / "cudart64_13.dll",
              RUNTIME / "cublas64_13.dll", RUNTIME / "cublasLt64_13.dll"):
        if not p.is_file():
            raise RuntimeError_(f"Gemma4 CUDA runtime 缺少文件：{p}")
    env = os.environ.copy()
    env["PATH"] = str(RUNTIME) + os.pathsep + env.get("PATH", "")
    _LOG_HANDLE = open(LOG, "w", encoding="utf-8", buffering=1)
    cmd = [str(EXE), "--model", str(MODEL), "--alias", "gemma4-director",
           "--host", "127.0.0.1", "--port", str(PORT), "-ngl", "99",
           "-c", "20480", "-np", "1", "-fa", "on", "-lv", "2"]
    _PROC = subprocess.Popen(cmd, cwd=RUNTIME, env=env, stdout=_LOG_HANDLE,
                             stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    end = time.time() + 300
    while time.time() < end and _PROC.poll() is None:
        if _health():
            cuda_modules = {"ggml-cuda.dll", "cudart64_13.dll", "nvcuda.dll"}
            # /health can turn green just before redirected startup logs flush.
            # Give both independent witnesses (loaded modules and CUDA context)
            # a bounded settling window; never infer readiness from -ngl alone.
            settle = time.time() + 12
            modules: set[str] = set()
            text = ""
            context_visible = False
            while time.time() < settle and _PROC.poll() is None:
                text = LOG.read_text(encoding="utf-8", errors="replace")
                try:
                    import psutil
                    modules = {Path(x.path).name.lower()
                               for x in psutil.Process(_PROC.pid).memory_maps()
                               if getattr(x, "path", "")}
                except Exception:
                    modules = set()
                context_visible = _cuda_context_visible(_PROC.pid)
                if cuda_modules.issubset(modules) and (
                        ("CUDA0" in text and "offloaded" in text) or context_visible):
                    break
                time.sleep(0.5)
            _CUDA_BACKEND_LOADED = cuda_modules.issubset(modules)
            _OFFLOAD_CONFIRMED = bool(("CUDA0" in text and "offloaded" in text)
                                      or (_CUDA_BACKEND_LOADED and context_visible))
            _GPU_COMPUTE_CONFIRMED = False
            _CPU_DOMINANT = False
            _LAST_PROBE = {}
            # Startup alone cannot prove compute: some builds load the CUDA
            # driver lazily on their first request and flush no INFO lines at
            # -lv 2. The provider therefore runs one bounded inference probe
            # immediately after this returns; api() accepts its result only
            # after PID-level pmon + CPU-time evidence passes the common gate.
            return
        time.sleep(1)
    stop()
    raise RuntimeError_("Gemma4 Director 启动超时。")


def stop() -> None:
    global _PROC, _LOG_HANDLE
    if _PROC and _PROC.poll() is None:
        _PROC.terminate()
        try: _PROC.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _PROC.kill(); _PROC.wait(timeout=5)
    _PROC = None
    if _LOG_HANDLE:
        try: _LOG_HANDLE.close()
        except OSError: pass
    _LOG_HANDLE = None


def _cpu_seconds(pid: int) -> float:
    try:
        import psutil
        t = psutil.Process(pid).cpu_times()
        return float(t.user + t.system)
    except Exception:
        return 0.0


def _pmon_sample(pid: int) -> dict:
    try:
        cp = subprocess.run(["nvidia-smi", "pmon", "-s", "um", "-c", "1"],
                            capture_output=True, text=True, timeout=4,
                            creationflags=subprocess.CREATE_NO_WINDOW)
        rows = []
        for line in cp.stdout.splitlines():
            cols = line.split()
            if len(cols) >= 4 and cols[1].isdigit() and int(cols[1]) == pid:
                sm = int(cols[3]) if cols[3].lstrip("-").isdigit() else 0
                mem = int(cols[4]) if len(cols) > 4 and cols[4].lstrip("-").isdigit() else 0
                rows.append({"line": line.strip(), "sm": sm, "mem": mem})
        return {"visible": bool(rows), "compute": any(x["sm"] > 0 for x in rows), "rows": rows}
    except Exception as exc:
        return {"visible": False, "compute": False, "error": f"{type(exc).__name__}: {exc}"}


def _sample_request(call):
    global _GPU_COMPUTE_CONFIRMED, _CPU_DOMINANT, _LAST_PROBE
    global _CUDA_BACKEND_LOADED, _OFFLOAD_CONFIRMED
    if not _PROC or _PROC.poll() is not None:
        raise RuntimeError_("Gemma4 Director 未运行。")
    pid = _PROC.pid
    before = _cpu_seconds(pid)
    samples: list[dict] = []
    done = threading.Event()
    def sampler():
        while not done.is_set():
            samples.append(_pmon_sample(pid))
            if done.wait(0.1): break
    thread = threading.Thread(target=sampler, daemon=True)
    started = time.monotonic()
    thread.start()
    try:
        return call()
    finally:
        done.set(); thread.join(timeout=5)
        wall = max(0.001, time.monotonic() - started)
        cores = max(0.0, _cpu_seconds(pid) - before) / wall
        visible = any(x.get("visible") for x in samples)
        compute = any(x.get("compute") for x in samples)
        try:
            import psutil
            modules = {Path(x.path).name.lower() for x in psutil.Process(pid).memory_maps()
                       if getattr(x, "path", "")}
        except Exception:
            modules = set()
        _CUDA_BACKEND_LOADED = "ggml-cuda.dll" in modules and (
            "cudart64_13.dll" in modules or "nvcuda.dll" in modules)
        _GPU_COMPUTE_CONFIRMED = bool(visible and compute)
        _CPU_DOMINANT = bool(cores >= 4.0 or not _GPU_COMPUTE_CONFIRMED)
        _OFFLOAD_CONFIRMED = bool(_CUDA_BACKEND_LOADED and _GPU_COMPUTE_CONFIRMED)
        _LAST_PROBE = {"pid": pid, "wall_s": round(wall, 3),
                       "cpu_cores_equivalent": round(cores, 3),
                       "pmon_pid_visible": visible, "gpu_compute_visible": compute,
                       "cuda_modules": sorted(n for n in modules
                                              if "cuda" in n or "cublas" in n or "ggml" in n),
                       "samples": samples[-4:]}


def api(payload: dict, timeout: float) -> dict:
    def request():
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with _LOCAL_HTTP.open(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            result["_http_metadata"] = {"HTTP_status": response.status,
                                        "server_header": response.headers.get("Server", "")}
            return result
    result = _sample_request(request)
    try:
        RC.verify_director_gpu_ready("gemma4")
    except RuntimeError as exc:
        stop()
        raise RuntimeError_(f"{exc}（禁止 CPU fallback）") from exc
    return result


def status() -> dict:
    return {"running": _health(), "port": PORT, "model": str(MODEL),
            "vision": False, "cuda_fail_closed": True,
            "cuda_backend_loaded": _CUDA_BACKEND_LOADED,
            "offload_confirmed": _OFFLOAD_CONFIRMED,
            "gpu_compute_confirmed": _GPU_COMPUTE_CONFIRMED,
            "cpu_dominant": _CPU_DOMINANT, "last_probe": _LAST_PROBE}


def runtime_contract() -> RC.DirectorProviderRuntimeContract:
    running = _health()
    pid = _PROC.pid if _PROC and _PROC.poll() is None else None
    return RC.DirectorProviderRuntimeContract(
        provider_name="gemma4", process_identity={"pid": pid, "exe": str(EXE)},
        server_endpoint=f"http://127.0.0.1:{PORT}", model_alias="gemma4-director",
        cuda_backend_loaded=bool(_CUDA_BACKEND_LOADED), gpu_layers_requested=True,
        gpu_compute_confirmed=bool(_GPU_COMPUTE_CONFIRMED), cpu_dominant=bool(_CPU_DOMINANT),
        offload_confirmed=bool(_OFFLOAD_CONFIRMED), resident=running, released=not running)


RC.register_runtime("gemma4", runtime_contract, stop)
