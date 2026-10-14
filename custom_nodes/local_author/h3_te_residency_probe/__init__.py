"""Read-only, content-independent post-conditioning TE residency snapshot.

No model loading, unloading, pin registration, cache cleanup, or tensor copies.
Pin views and their HostBuffer are overlapping measurements, never additive.
"""
import ctypes
from ctypes import wintypes
import datetime
import json
import logging
import os
from pathlib import Path
import time

import torch
import comfy.model_management as mm

TARGET_MODULE = "comfy.text_encoders.minimax"
TARGET_QUALNAME = "te.<locals>.MiniMaxH3TEModel_"
GIB = 1024 ** 3
NA = "NOT_AVAILABLE"


def _read(call, errors, label):
    try:
        return call()
    except Exception as exc:
        errors.append(f"{label}: {type(exc).__name__}: {exc}")
        return NA


def _union_bytes(ranges):
    end = 0
    total = 0
    for start, stop in sorted(ranges):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


def _host_and_pins(model, errors):
    hostbufs = {}
    pins = set()
    allocated = []
    registered = []
    host_backed = []
    subsets = {}
    states = {}
    for state in getattr(model, "dynamic_pins", {}).values():
        if isinstance(state, dict):
            states[id(state)] = state
    for module in model.modules():
        state = module.__dict__.get("_pin_state")
        if isinstance(state, dict):
            states[id(state)] = state
        for subset, entry in module.__dict__.get("_pins", {}).items():
            if not isinstance(entry, dict):
                continue
            pin = entry.get("pin")
            if pin is None or id(pin) in pins:
                continue
            pins.add(id(pin))
            try:
                size = int(pin.numel()) * int(pin.element_size())
                start = int(pin.data_ptr())
                span = (start, start + size)
                allocated.append(span)
                if entry.get("registered", False):
                    registered.append(span)
                hostbuf = getattr(pin.untyped_storage(), "_comfy_hostbuf", None)
                if hostbuf is not None:
                    hostbufs[id(hostbuf)] = hostbuf
                    host_backed.append(span)
                subsets[subset] = subsets.get(subset, 0) + size
            except Exception as exc:
                errors.append(f"pin {subset}: {type(exc).__name__}: {exc}")
    for state in states.values():
        for subset in ("weights", "patches", "weights-loaded", "patches-loaded"):
            value = state.get(subset)
            if isinstance(value, (tuple, list)) and value:
                hostbufs[id(value[0])] = value[0]
    sizes = []
    for hostbuf in hostbufs.values():
        value = _read(lambda: int(hostbuf.size), errors, "HostBuffer.size")
        if value != NA:
            sizes.append(value)
    return {
        "TE_PIN_OBJECT_COUNT": len(pins),
        "TE_PIN_ALLOCATED_BYTES": _union_bytes(allocated),
        "TE_PIN_REGISTERED_BYTES": _union_bytes(registered),
        "TE_HOSTBUFFER_BACKED_PIN_BYTES": _union_bytes(host_backed),
        "TE_PIN_SUBSETS_LOGICAL_BYTES": subsets,
        "TE_HOSTBUFFER_COUNT": len(hostbufs),
        "TE_HOSTBUFFER_BYTES": sum(sizes) if len(sizes) == len(hostbufs) else "UNPROVEN",
        "TE_HOSTBUFFER_SIZE_MEANING": "HostBuffer.size logical grown extent; excludes unreported native prewarm/capacity",
        "TE_PIN_HOSTBUFFER_OVERLAP": "pin views overlap HostBuffer; do not add them",
    }


def _windows_memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
            (name, ctypes.c_ulonglong) for name in (
                "total_phys", "avail_phys", "total_pagefile", "avail_pagefile",
                "total_virtual", "avail_virtual", "avail_extended_virtual")]

    class PerformanceInfo(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "commit_total", "commit_limit", "commit_peak", "physical_total",
                "physical_available", "system_cache", "kernel_total", "kernel_paged",
                "kernel_nonpaged", "page_size")] + [
            (name, wintypes.DWORD) for name in ("handle_count", "process_count", "thread_count")]

    class ProcessMemory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("page_fault_count", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak_working_set", "working_set", "quota_peak_paged", "quota_paged",
                "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile", "private_usage")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
    psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(PerformanceInfo), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    mem, perf, proc = MemoryStatus(), PerformanceInfo(), ProcessMemory()
    mem.length, perf.cb, proc.cb = ctypes.sizeof(mem), ctypes.sizeof(perf), ctypes.sizeof(proc)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(mem)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(proc), proc.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    commit = perf.commit_total * perf.page_size
    limit = perf.commit_limit * perf.page_size
    return {
        "PROCESS_RSS_BYTES": proc.working_set,
        "PROCESS_VMS_BYTES": proc.pagefile,
        "PROCESS_VMS_MEANING": "Windows PROCESS_MEMORY_COUNTERS_EX.PagefileUsage (process commit charge); not reserved address space",
        "PROCESS_PRIVATE_BYTES": proc.private_usage,
        "SYSTEM_RAM_USED_BYTES": mem.total_phys - mem.avail_phys,
        "SYSTEM_RAM_AVAILABLE_BYTES": mem.avail_phys,
        "SYSTEM_COMMIT_USED_BYTES": commit,
        "SYSTEM_COMMIT_LIMIT_BYTES": limit,
        "SYSTEM_COMMIT_PERCENT": 100 * commit / limit if limit else NA,
    }


def snapshot():
    errors = []
    result = {
        "SCHEMA": "H3_TE_RESIDENCY_RUNTIME_OBSERVATION_V1",
        "UTC_TIME": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "8197_PID": os.getpid(),
        "TE_LAST_USE_BEFORE_SAMPLER": "YES_BY_CANDIDATE_DEPENDENCY",
        "INFERENCE_MODE_ENABLED": torch.is_inference_mode_enabled(),
        "MODEL_UNLOAD_CALLED": "NO", "FREE_MEMORY_CALLED": "NO", "GC_CALLED": "NO",
        "GLOBAL_TOTAL_PINNED_MEMORY_BYTES": getattr(mm, "TOTAL_PINNED_MEMORY", NA),
    }
    targets = []
    for loaded in tuple(mm.current_loaded_models):
        patcher = loaded.model
        if patcher is None:
            continue
        model = patcher.model
        cls = type(model)
        if cls.__module__ == TARGET_MODULE and cls.__qualname__ == TARGET_QUALNAME:
            targets.append((loaded, patcher, model))
    result["TE_MATCH_COUNT"] = len(targets)
    result["TE_STATUS"] = "UNIQUE_TARGET" if len(targets) == 1 else "NO_TARGET" if not targets else "AMBIGUOUS_TARGET"
    if len(targets) == 1:
        loaded, patcher, model = targets[0]
        result.update({
            "TE_CLASS": f"{type(model).__module__}.{type(model).__qualname__}",
            "TE_PATCHER_CLASS": f"{type(patcher).__module__}.{type(patcher).__qualname__}",
            "TE_MODEL_ID": id(model), "TE_PATCHER_ID": id(patcher),
            "TE_CURRENTLY_USED": getattr(loaded, "currently_used", NA),
            "TE_WEIGHTS_LOADED": getattr(loaded, "weights_loaded", NA),
            "TE_LOWVRAM_MODEL_MEMORY": getattr(loaded, "lowvram_model_memory", NA),
            "TE_LOAD_DEVICE": str(patcher.load_device),
            "TE_OFFLOAD_DEVICE": str(patcher.offload_device),
            "TE_CURRENT_DEVICE": str(_read(patcher.current_loaded_device, errors, "current_loaded_device")),
            "TE_MODEL_MEMORY_BYTES": _read(loaded.model_memory, errors, "model_memory"),
            "TE_LOADED_SIZE_BYTES": _read(patcher.loaded_size, errors, "loaded_size"),
            "TE_MODEL_MEMORY_MEANING": "model size estimate; not proof of CPU residency",
            "TE_CPU_RAM_ATTRIBUTION": "registered host pin bytes are a lower bound; no per-model OS working-set measurement",
        })
        result.update(_host_and_pins(model, errors))
        vbar = _read(lambda: getattr(model, "dynamic_vbars", {}).get(patcher.load_device), errors, "dynamic_vbar lookup")
        result["TE_DYNAMIC_VRAM_BYTES"] = _read(vbar.loaded_size, errors, "vbar.loaded_size") if vbar not in (None, NA) else 0 if vbar is None else NA
    memory = _read(_windows_memory, errors, "Windows memory snapshot")
    if isinstance(memory, dict):
        result.update(memory)
    # Do not initialize CUDA just to measure it. During normal H3 encode it is initialized.
    if torch.cuda.is_initialized():
        cuda_memory = _read(torch.cuda.mem_get_info, errors, "CUDA global memory snapshot")
        if isinstance(cuda_memory, tuple):
            free, total = cuda_memory
            result["GPU_VRAM_USED_BYTES"] = total - free
            result["GPU_VRAM_USED_SCOPE"] = "device total minus free, including other processes"
    else:
        result["GPU_VRAM_USED_BYTES"] = NA
    for name, value in list(result.items()):
        if name.endswith("_BYTES") and isinstance(value, (int, float)):
            result[name[:-6] + "_GIB"] = value / GIB
    result["MEASUREMENT_ERRORS"] = errors
    return result


class H3TEResidencyProbe:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",)}}

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    FUNCTION = "observe"
    CATEGORY = "H3/diagnostics"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def observe(self, conditioning):
        # Errors in observation must not mutate or block the production conditioning.
        try:
            result = snapshot()
            folder = Path(__file__).resolve().parents[2] / "user" / "h3_te_residency_probe"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / f"snapshot_{os.getpid()}_{time.time_ns()}.json"
            result["SNAPSHOT_PATH"] = str(output)
            message = json.dumps(result, ensure_ascii=False, indent=2)
            output.write_text(message, encoding="utf-8")
            logging.info("H3TEResidencyProbe %s", json.dumps(result, ensure_ascii=False))
            return {"ui": {"text": [message]}, "result": (conditioning,)}
        except Exception as exc:
            logging.error("H3TEResidencyProbe observation failed: %s: %s", type(exc).__name__, exc)
            return (conditioning,)


NODE_CLASS_MAPPINGS = {"H3TEResidencyProbe": H3TEResidencyProbe}
NODE_DISPLAY_NAME_MAPPINGS = {"H3TEResidencyProbe": "H3 TE Residency Probe (read only)"}
