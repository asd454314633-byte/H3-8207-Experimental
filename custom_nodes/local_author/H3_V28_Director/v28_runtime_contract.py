"""Provider-agnostic Director runtime lifecycle and fail-closed GPU gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class DirectorProviderRuntimeContract:
    provider_name: str
    process_identity: dict
    server_endpoint: str
    model_alias: str
    cuda_backend_loaded: bool
    gpu_layers_requested: bool
    gpu_compute_confirmed: bool
    cpu_dominant: bool
    offload_confirmed: bool
    resident: bool
    released: bool

    @property
    def gpu_ready(self) -> bool:
        return bool(self.resident and self.cuda_backend_loaded
                    and self.gpu_layers_requested and self.gpu_compute_confirmed
                    and not self.cpu_dominant and self.offload_confirmed)

    def as_dict(self) -> dict:
        return {**asdict(self), "director_gpu_ready": self.gpu_ready,
                "director_cpu_fallback": bool(self.resident and not self.gpu_ready)}


@dataclass
class _Adapter:
    snapshot: Callable[[], DirectorProviderRuntimeContract]
    stop: Callable[[], object]
    reap: Callable[[], object]


_ADAPTERS: dict[str, _Adapter] = {}


def register_runtime(provider_name: str, snapshot: Callable[[], DirectorProviderRuntimeContract],
                     stop: Callable[[], object], reap: Callable[[], object] | None = None) -> None:
    _ADAPTERS[provider_name] = _Adapter(snapshot, stop, reap or stop)


def runtime_snapshot(provider_name: str) -> DirectorProviderRuntimeContract:
    try:
        return _ADAPTERS[provider_name].snapshot()
    except KeyError as exc:
        raise RuntimeError(f"Director provider 未注册 runtime contract：{provider_name}") from exc


def get_active_director_runtime(preferred: str = "") -> DirectorProviderRuntimeContract:
    if preferred:
        return runtime_snapshot(preferred)
    states = [adapter.snapshot() for adapter in _ADAPTERS.values()]
    for state in states:
        if state.resident:
            return state
    for state in states:
        if state.provider_name == "gemma4":
            return state
    if states:
        return states[0]
    raise RuntimeError("没有已注册的 Director runtime contract")


def verify_director_gpu_ready(provider_name: str) -> DirectorProviderRuntimeContract:
    state = runtime_snapshot(provider_name)
    if not state.gpu_ready:
        missing = []
        if not state.resident: missing.append("resident")
        if not state.cuda_backend_loaded: missing.append("CUDA backend")
        if not state.gpu_layers_requested: missing.append("GPU layers requested")
        if not state.gpu_compute_confirmed: missing.append("GPU compute")
        if state.cpu_dominant: missing.append("CPU dominant")
        if not state.offload_confirmed: missing.append("offload")
        raise RuntimeError(
            f"{provider_name} CUDA 未启用：{', '.join(missing)} 未确认，禁止 CPU fallback。")
    return state


def generation_gate(refresh: bool = False) -> tuple[bool, str, dict]:
    del refresh
    states = [adapter.snapshot() for adapter in _ADAPTERS.values()]
    resident = [state for state in states if state.resident or not state.released]
    details = {"active_directors": [state.as_dict() for state in resident],
               "registered_providers": sorted(_ADAPTERS)}
    if resident:
        names = ", ".join(state.provider_name for state in resident)
        return False, f"Director 仍驻留（{names}），禁止与 H3 GPU 共存；请先停止并确认释放。", details
    return True, "", details


def require_director_released() -> None:
    allowed, message, details = generation_gate()
    if not allowed:
        error = RuntimeError(message)
        error.details = details
        raise error


def stop_active_director(provider_name: str = "") -> dict:
    state = get_active_director_runtime(provider_name)
    result = _ADAPTERS[state.provider_name].stop()
    after = runtime_snapshot(state.provider_name)
    return {"provider": state.provider_name, "result": result,
            "released": after.released, "runtime": after.as_dict()}


def reap_active_director(provider_name: str = "") -> dict:
    state = get_active_director_runtime(provider_name)
    result = _ADAPTERS[state.provider_name].reap()
    after = runtime_snapshot(state.provider_name)
    return {"provider": state.provider_name, "result": result,
            "released": after.released, "runtime": after.as_dict()}
