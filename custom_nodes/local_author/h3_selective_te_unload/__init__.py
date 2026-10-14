"""Narrow post-conditioning H3 TE lifecycle canary; fail closed."""
import importlib.util
import gc
import json
import logging
import math
import os
from pathlib import Path
import time

import comfy.model_management as mm
import torch

_spec = importlib.util.spec_from_file_location("h3_te_snapshot_shared", Path(__file__).parent.parent / "h3_te_residency_probe" / "__init__.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def target_entries():
    found = []
    for entry in tuple(mm.current_loaded_models):
        patcher = entry.model
        if patcher is None:
            continue
        model = patcher.model
        if type(model).__module__ == probe.TARGET_MODULE and type(model).__qualname__ == probe.TARGET_QUALNAME:
            found.append((entry, patcher, model))
    return found


def validate_residency(stats, model):
    """Residency is an observation, not a fixed minimum benefit gate."""
    if stats["MEASUREMENT_ERRORS"]:
        raise RuntimeError("Invalid TE residency measurement")
    for key in ("TE_PIN_ALLOCATED_BYTES", "TE_PIN_REGISTERED_BYTES", "TE_HOSTBUFFER_BYTES", "TE_LOADED_SIZE_BYTES"):
        value = stats.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise RuntimeError(f"Invalid TE residency statistic: {key}")
    if stats["TE_PIN_REGISTERED_BYTES"] > stats["TE_PIN_ALLOCATED_BYTES"]:
        raise RuntimeError("Registered TE pins exceed allocated pins")
    states = getattr(model, "dynamic_pins", {})
    if not isinstance(states, dict) or any(not isinstance(state, dict) for state in states.values()):
        raise RuntimeError("Malformed TE dynamic pin state")
    for module in model.modules():
        pins = module.__dict__.get("_pins", {})
        if not isinstance(pins, dict) or any(not isinstance(pin, dict) for pin in pins.values()):
            raise RuntimeError("Malformed TE module pins")


def validate_conditioning_and_position(conditioning, prompt, ancestors):
    if not isinstance(conditioning, (list, tuple)) or not conditioning:
        raise RuntimeError("Missing materialized conditioning")
    for item in conditioning:
        if not isinstance(item, (list, tuple)) or len(item) != 2 or not isinstance(item[0], torch.Tensor) or item[0].numel() == 0 or item[0].ndim < 2 or not isinstance(item[1], dict):
            raise RuntimeError("Invalid materialized conditioning")
    consumers = [nid for nid in ancestors if prompt[nid]['class_type'] == 'MiniMaxH3ReferenceToVideo']
    if len(consumers) != 1:
        raise RuntimeError("Unique final H3 conditioning consumer not proven")


def zero_target_census():
    """Read-only heap census includes cached/orphaned TE models, not just loaded entries.

    get_objects does not run a collection. No tensor copies or lifecycle mutations.
    """
    models = {}
    loaded = []
    for entry in tuple(mm.current_loaded_models):
        patcher = entry.model
        model = None if patcher is None else patcher.model
        if model is not None:
            loaded.append({'class': f'{type(model).__module__}.{type(model).__qualname__}', 'model_id': id(model), 'patcher_id': id(patcher)})
    objects = gc.get_objects()
    try:
        for obj in objects:
            cls = type(obj)
            related = any(base.__module__ == probe.TARGET_MODULE and base.__name__.startswith('MiniMaxH3TEModel') for base in cls.__mro__)
            related = related or cls.__qualname__.endswith('MiniMaxH3TEModel_')
            if not related:
                continue
            if cls.__module__ != probe.TARGET_MODULE or cls.__qualname__ != probe.TARGET_QUALNAME:
                raise RuntimeError('Equivalent or conflicting H3 TE class detected')
            models[id(obj)] = obj
    finally:
        del objects
    # Re-read the list after the census; any exact target makes zero-state inconsistent.
    if target_entries():
        raise RuntimeError('TE target appeared during zero-state census')
    observations = []
    for model in models.values():
        errors = []
        stats = probe._host_and_pins(model, errors)
        residency = getattr(model, 'model_loaded_weight_memory', 0)
        vbars = getattr(model, 'dynamic_vbars', {})
        if not isinstance(vbars, dict):
            raise RuntimeError('Malformed orphan TE vbar state')
        for vbar in vbars.values():
            value = vbar.loaded_size()
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise RuntimeError('Invalid orphan TE GPU residency')
            residency += value
        stats.update(MEASUREMENT_ERRORS=errors, TE_LOADED_SIZE_BYTES=residency)
        validate_residency(stats, model)
        if any(stats[key] != 0 for key in ('TE_PIN_ALLOCATED_BYTES', 'TE_PIN_REGISTERED_BYTES', 'TE_HOSTBUFFER_BYTES', 'TE_LOADED_SIZE_BYTES')):
            raise RuntimeError('Residual TE residency without LoadedModel entry')
        observations.append({'model_id':id(model), 'stats':stats})
    return {'current_loaded_models':loaded, 'TE_OBJECTS':observations, 'TE_MATCH_COUNT':0, 'RESIDENCY_CHECK':'PASS'}


class H3SelectiveTEUnload:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",)}, "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    FUNCTION = "unload"
    CATEGORY = "H3/diagnostics"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def unload(self, conditioning, prompt, unique_id):
        record = {"schema": "H3_SELECTIVE_TE_UNLOAD_RUNTIME_CANARY_V1", "pid": os.getpid(), "utc_epoch": time.time(), "status": "FAIL_CLOSED"}
        folder = Path(__file__).resolve().parents[2] / "user" / "h3_selective_te_unload"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"unload_{os.getpid()}_{time.time_ns()}.json"
        try:
            # Only the TE loader reachable from this final conditioning matters.
            ancestors = set()
            def visit(node_id):
                node_id = str(node_id)
                if node_id in ancestors:
                    return
                ancestors.add(node_id)
                for value in prompt[node_id]["inputs"].values():
                    if isinstance(value, list) and len(value) == 2 and str(value[0]) in prompt:
                        visit(value[0])
            visit(unique_id)
            clips = [n for nid, n in prompt.items() if str(nid) in ancestors and n["class_type"] == "CLIPLoader"]
            if len(clips) != 1 or clips[0]["inputs"].get("clip_name") != "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" or clips[0]["inputs"].get("type") != "minimax":
                raise RuntimeError("Unique graph H3 NVFP4 AWQ TE identity not proven")
            validate_conditioning_and_position(conditioning, prompt, ancestors)
            targets = target_entries()
            record["TE_MATCH_COUNT"] = len(targets)
            if len(targets) == 0:
                record['zero_target_census'] = zero_target_census()
                record['TE_UNLOAD_ACTION'] = 'SAFE_NOOP'
                record['MODEL_UNLOAD_CALLED'] = False
                record['status'] = 'PASS'
                return {'ui': {'text':[json.dumps(record)]}, 'result':(conditioning,)}
            if len(targets) != 1:
                raise RuntimeError("Expected exactly one MiniMaxH3TEModel_ LoadedModel")
            entry, patcher, model = targets[0]
            if entry.real_model is None or entry.real_model() is not model or entry.model is not patcher or patcher.model is not model:
                raise RuntimeError("LoadedModel/patcher/model identity mismatch")
            before = probe.snapshot()
            record["before"] = before
            validate_residency(before, model)
            if not any(existing is entry for existing in mm.current_loaded_models) or before.get("TE_MATCH_COUNT") != 1 or before.get("TE_MODEL_ID") != id(model) or before.get("TE_PATCHER_ID") != id(patcher):
                raise RuntimeError("Target entry/snapshot identity mismatch")
            record["identities"] = {"loaded": id(entry), "patcher": id(patcher), "model": id(model)}
            peers = tuple(x for x in mm.current_loaded_models if x is not entry)
            # Current 0.36.0: None bypasses partial unload; True releases Dynamic pins and vbar.
            result = entry.model_unload(memory_to_free=None, unpatch_weights=True)
            record["MODEL_UNLOAD_CALLED"] = True
            if result is not True:
                raise RuntimeError("Lifecycle did not report full unload")
            if entry.model is not patcher or patcher.model is not model:
                raise RuntimeError("Identity changed during unload")
            for index, existing in enumerate(mm.current_loaded_models):
                if existing is entry:
                    del mm.current_loaded_models[index]
                    break
            if tuple(id(x) for x in mm.current_loaded_models if x is not entry) != tuple(id(x) for x in peers):
                raise RuntimeError("Unexpected peer entry mutation")
            errors = []
            after = probe.snapshot()
            # The entry is absent: measure retained target model directly, never infer zero from absence.
            after.update(probe._host_and_pins(model, errors))
            after["TE_LOADED_SIZE_BYTES"] = patcher.loaded_size()
            after["TE_ENTRY_PRESENT_AFTER"] = any(x is entry for x in mm.current_loaded_models)
            for key, value in list(after.items()):
                if key.endswith("_BYTES") and isinstance(value, (int, float)):
                    after[key[:-6] + "_GIB"] = value / probe.GIB
            after["MEASUREMENT_ERRORS"].extend(errors)
            record["after"] = after
            record["TE_UNLOAD_FREED_GIB"] = (before["TE_PIN_REGISTERED_BYTES"] - after["TE_PIN_REGISTERED_BYTES"]) / probe.GIB
            validate_residency(after, model)
            if after["TE_ENTRY_PRESENT_AFTER"] or after["TE_PIN_REGISTERED_BYTES"] > 0.05 * probe.GIB or after["TE_HOSTBUFFER_BYTES"] > 0.05 * probe.GIB or after["TE_LOADED_SIZE_BYTES"] > 0.05 * probe.GIB:
                raise RuntimeError("Insufficient target residency release; sampler blocked")
            record["status"] = "PASS"
            record['TE_UNLOAD_ACTION'] = 'UNLOAD'
            return {"ui": {"text": [json.dumps(record)]}, "result": (conditioning,)}
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            logging.info("H3SelectiveTEUnload %s", json.dumps(record))


NODE_CLASS_MAPPINGS = {"H3SelectiveTEUnload": H3SelectiveTEUnload}
NODE_DISPLAY_NAME_MAPPINGS = {"H3SelectiveTEUnload": "H3 Selective TE Unload (fail closed)"}
