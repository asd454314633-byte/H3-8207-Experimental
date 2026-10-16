"""H3 Native Continuation Adapter - core logic.

Provider: CORE_NATIVE_MASKED_AV (Native Masked AV Exact Continuation).

This module is deliberately free of any ComfyUI import so it can be unit
tested offline. Everything here is data plumbing on top of contracts that
already exist in ComfyUI Core:

  * comfy_extras/nodes_custom_sampler.py:1047  SamplerCustomAdvanced reads
    latent["noise_mask"] and hands it to the guider as denoise_mask.
  * comfy/samplers.py:1297                     KSampler.sample accepts a
    NestedTensor denoise_mask, unpacks it per modality, fills missing
    modalities with ones, then packs it for the model.
  * comfy/model_base.py:1196-1240              the MiniMax H3 AV model
    unpacks that mask back into video_denoise_mask / audio_denoise_mask and
    patches the per-token timestep of both streams.

Nothing in ComfyUI is patched, wrapped or monkey-patched. If Core ever
removes one of those contracts, feature_detect() says exactly what is
missing instead of silently running the wrong path.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from typing import Any


def adapt_video_prefix(previous, target_shape, prefix_tokens, target_dtype):
    """Map only a real temporal tail to the requested spatial grid on CPU.

    This follows Core's bilinear latent upscale convention. Time, batch and
    channels are never interpolated. Equal grids retain the exact old path.
    """
    import torch
    if previous.ndim != 5 or len(target_shape) != 5:
        raise ValueError('Native continuation requires B,C,T,H,W video latents')
    if tuple(previous.shape[:2]) != tuple(target_shape[:2]):
        raise ValueError('Native predecessor batch/channel identity differs')
    if prefix_tokens <= 0 or previous.shape[2] < prefix_tokens or target_shape[2] <= prefix_tokens:
        raise ValueError('Native continuation temporal prefix is incomplete')
    if min(*previous.shape[-2:], *target_shape[-2:]) <= 0:
        raise ValueError('Native continuation spatial grid is empty')
    tail = previous[:, :, -prefix_tokens:].detach().to('cpu')
    if tuple(previous.shape[-2:]) == tuple(target_shape[-2:]):
        return tail.to(dtype=target_dtype), None
    batch, channels, tokens, height, width = tail.shape
    frames = tail.movedim(2, 1).reshape(batch * tokens, channels, height, width).float()
    frames = torch.nn.functional.interpolate(frames, size=tuple(target_shape[-2:]),
                                             mode='bilinear', align_corners=False)
    mapped = frames.reshape(batch, tokens, channels, *target_shape[-2:]).movedim(1, 2)
    transform = {'schema': 'H3_NATIVE_SPATIAL_PREFIX_V1', 'method': 'bilinear',
                 'align_corners': False, 'crop': 'disabled', 'compute_device': 'cpu',
                 'compute_dtype': 'float32', 'source_grid': list(previous.shape[-2:]),
                 'target_grid': list(target_shape[-2:]), 'video_prefix_tokens': prefix_tokens,
                 'raw_previous_video_tail_equal': False}
    return mapped.to(dtype=target_dtype), transform

# --------------------------------------------------------------------------
# frozen contract constants
# --------------------------------------------------------------------------

PROVIDER_ID = "CORE_NATIVE_MASKED_AV"
PROVIDER_NEXTGEN_RESERVED = "CONTINUOUS_LATENT_TIMELINE"  # reserved, NOT implemented

FPS = 24
AUDIO_LATENT_FPS = 40
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
FRAME_RESCALE = 5.0 / 3.0  # audio latent steps per pixel frame (40 / 24)

VIDEO_PREFIX_FRAMES = 39     # 17k+5 grid: 39 % 17 == 5
AUDIO_PREFIX_STEPS = 65      # round(39 / 24 * 40) == 65

BRANCH_GENERATED_AUDIO = "GENERATED_AUDIO_CONTINUITY"
BRANCH_DRIVING_AUDIO = "DRIVING_AUDIO"

# assembly tolerances
AV_DRIFT_TOLERANCE_SEC = 1.0 / FPS + 1e-6   # one pixel frame
DURATION_TOLERANCE_SEC = 2.0 / FPS


def resolve_continuation_policy(*, enabled: bool, segment_index: int,
                                reuse_previous_latent: bool,
                                save_current_latent: bool,
                                trim_reused_prefix: bool,
                                clean_rebase_enabled: bool = False,
                                clean_rebase_segment: int = 3) -> dict:
    """Resolve one segment's latent reuse/save/trim policy.

    The feature is inert unless both the continuation and explicit Clean Rebase
    switches are on. Segment indices are zero-based.
    """
    if isinstance(segment_index, bool) or not isinstance(segment_index, int) or segment_index < 0:
        raise ValueError("segment_index must be a non-negative integer")
    if isinstance(clean_rebase_segment, bool) or not isinstance(clean_rebase_segment, int) or clean_rebase_segment < 0:
        raise ValueError("clean_rebase_segment must be a non-negative integer")

    active = bool(enabled) and bool(clean_rebase_enabled) and segment_index == clean_rebase_segment
    return {
        "enabled": bool(enabled),
        "segment_index": segment_index,
        "clean_rebase_enabled": bool(clean_rebase_enabled),
        "clean_rebase_segment": clean_rebase_segment,
        "clean_rebase_active": active,
        "reuse_previous_latent": False if active else bool(reuse_previous_latent),
        "save_current_latent": bool(save_current_latent),
        "trim_reused_prefix": False if active else bool(trim_reused_prefix),
        "reason": "clean_rebase" if active else "compatibility_passthrough",
    }


# --------------------------------------------------------------------------
# timeline arithmetic (mirrors comfy_extras/nodes_minimax_h3.py exactly)
# --------------------------------------------------------------------------

def align_frame_count(n: int) -> int:
    n = max(5, int(n))
    while n % 17 != 5:
        n += 1
    return n


def video_latent_t(frame_count: int) -> int:
    return 2 if frame_count <= 5 else ((frame_count - 5) // 17) * 5 + 2


def frames_from_video_tokens(tokens: int) -> int:
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(int(tokens)))


def video_tokens_for_prefix(prefix_frames: int) -> int:
    """Latent tokens that cover exactly `prefix_frames` pixel frames.

    Raises when the requested prefix is not on a latent token boundary:
    a prefix that lands mid-token cannot be protected by a per-token mask.
    """
    acc = 0
    k = 0
    while acc < prefix_frames:
        acc += FRAME_PER_TOKEN[k % 5]
        k += 1
    if acc != prefix_frames:
        raise ValueError(
            "prefix {} frames is not a latent token boundary "
            "(nearest boundaries: {} / {})".format(
                prefix_frames, frames_from_video_tokens(k - 1), acc))
    return k


def audio_steps_for_frames(frame_count: int) -> int:
    """Core rounds this value (round(duration * 40)); mirrors temporal_shape()."""
    return int(round(frame_count / FPS * AUDIO_LATENT_FPS))


def audio_prefix_steps(prefix_frames: int = VIDEO_PREFIX_FRAMES) -> int:
    """Audio latent steps covered by a prefix, requiring an EXACT joint boundary.

    A prefix may sit on a video token boundary and still be unusable: a
    per-token mask can only protect a prefix whose audio side lands on a whole
    latent step. 39 frames -> 65 steps exactly; 22 frames -> 36.67 steps, which
    Core would silently round, so 22 is rejected here instead.
    """
    exact = prefix_frames / FPS * AUDIO_LATENT_FPS
    if abs(exact - round(exact)) > 1e-9:
        raise ValueError(
            "prefix %d frames is not an exact joint A/V boundary: it maps to "
            "%.4f audio latent steps, which Core would round to %d"
            % (prefix_frames, exact, int(round(exact))))
    return int(round(exact))


def is_exact_av_boundary(frames: int) -> bool:
    """True only for prefixes that are exact on BOTH streams.

    On the 17k+5 pixel grid this yields 39 / 90 / 141 - the same series the
    Continuum native-masked documentation lists as the shared A/V boundaries.
    """
    try:
        if align_frame_count(frames) != frames:
            return False
        video_tokens_for_prefix(frames)
        audio_prefix_steps(frames)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# feature detection - never trust a version string
# --------------------------------------------------------------------------

def feature_detect() -> dict:
    """Verify the Core AV mask contract really exists in this runtime.

    Returns a dict of {check_name: {"ok": bool, "detail": str}}.
    Raises RuntimeError listing every missing piece when the contract is
    broken, so the failure names the cause instead of degrading silently.
    """
    import inspect

    checks: dict[str, dict] = {}

    def rec(name, ok, detail):
        checks[name] = {"ok": bool(ok), "detail": str(detail)}

    try:
        import comfy.utils as cu
        rec("comfy.utils.pack_latents", hasattr(cu, "pack_latents"), "pack_latents present")
        rec("comfy.utils.unpack_latents", hasattr(cu, "unpack_latents"), "unpack_latents present")
    except Exception as exc:  # pragma: no cover - import failure is the finding
        rec("comfy.utils.pack_latents", False, "import comfy.utils failed: %s" % exc)
        rec("comfy.utils.unpack_latents", False, "import comfy.utils failed: %s" % exc)

    try:
        import comfy.nested_tensor as cnt
        rec("comfy.nested_tensor.NestedTensor", hasattr(cnt, "NestedTensor"),
            "NestedTensor present")
    except Exception as exc:
        rec("comfy.nested_tensor.NestedTensor", False,
            "import comfy.nested_tensor failed: %s" % exc)

    # A guider must unpack a NestedTensor denoise_mask per modality.
    # Discovered by capability, not by class name: in 0.36 this lives in
    # CFGGuider.sample (BasicGuider's base), not in KSampler.sample.
    try:
        import comfy.samplers as csamplers
        holders = []
        for obj in vars(csamplers).values():
            if not isinstance(obj, type):
                continue
            for meth in ("sample", "outer_sample"):
                fn = getattr(obj, meth, None)
                if fn is None:
                    continue
                try:
                    src = inspect.getsource(fn)
                except (TypeError, OSError):
                    continue
                if "denoise_mask.is_nested" in src and "latent_shapes" in src:
                    holders.append("%s.%s" % (obj.__name__, meth))
        rec("guider accepts nested AV denoise_mask", bool(holders),
            "found in %s" % (", ".join(holders) or "NONE"))
    except Exception as exc:
        rec("guider accepts nested AV denoise_mask", False, "inspect failed: %s" % exc)

    # Some model in model_base must consume audio_denoise_mask separately.
    try:
        import comfy.model_base as cmodel_base
        holders = []
        for obj in vars(cmodel_base).values():
            if not isinstance(obj, type):
                continue
            fn = getattr(obj, "process_timestep", None)
            if fn is None:
                continue
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):
                continue
            if "audio_denoise_mask" in params and "denoise_mask" in params:
                holders.append(obj.__name__)
        rec("model_base exposes audio_denoise_mask per-token path",
            bool(holders), "classes: %s" % (", ".join(holders) or "NONE"))
        checks["model_base.extra_conds_packs_AV_mask"] = {
            "ok": bool(holders),
            "detail": "video+audio timestep patching available on %s" % (holders[0] if holders else "NONE"),
        }
    except Exception as exc:
        rec("model_base exposes audio_denoise_mask per-token path", False,
            "inspect failed: %s" % exc)

    missing = [k for k, v in checks.items() if not v["ok"]]
    if missing:
        raise RuntimeError(
            "H3 Native Continuation: Core AV mask contract is incomplete. "
            "Missing: " + "; ".join("%s (%s)" % (k, checks[k]["detail"]) for k in missing))
    return checks


# --------------------------------------------------------------------------
# continuation store
# --------------------------------------------------------------------------

class ContinuationStore:
    """Per-project store of accepted segment latents + assembly bookkeeping.

    Layout:
        <root>/h3_continuation/<project_id>/seg_<05d>.safetensors
        <root>/h3_continuation/<project_id>/index.json
    """

    def __init__(self, root: str, project_id: str):
        self.root = root
        self.project_id = (project_id or "default").strip() or "default"
        self.dir = os.path.join(root, "h3_continuation", self._safe(self.project_id))

    @staticmethod
    def _safe(name: str) -> str:
        keep = [c for c in name if c.isalnum() or c in ("-", "_")]
        return "".join(keep)[:64] or "default"

    @property
    def index_path(self) -> str:
        return os.path.join(self.dir, "index.json")

    def _ensure(self):
        os.makedirs(self.dir, exist_ok=True)

    def load_index(self) -> dict:
        p = self.index_path
        if not os.path.isfile(p):
            return {"provider": PROVIDER_ID, "project_id": self.project_id,
                    "segments": [], "trim_events": []}
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def save_index(self, index: dict):
        self._ensure()
        tmp = self.index_path + ".tmp-" + uuid.uuid4().hex
        try:
            with open(tmp, "wb") as fh:
                fh.write(json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.index_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def seg_path(self, index: int) -> str:
        return os.path.join(self.dir, "seg_%05d.safetensors" % int(index))

    def save_segment(self, index: int, video, audio, meta: dict) -> str:
        """Persist the accepted AV latent of one segment (safetensors, no pickle)."""
        from safetensors.torch import save_file

        self._ensure()
        path = self.seg_path(index)
        md = {k: str(v) for k, v in meta.items()}
        md["provider"] = PROVIDER_ID
        md["segment_index"] = str(int(index))
        temporary = path + ".tmp-" + uuid.uuid4().hex
        try:
            save_file({"video": video.contiguous(), "audio": audio.contiguous()},
                      temporary, metadata=md)
            with open(temporary, "r+b") as fh:
                os.fsync(fh.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

        idx = self.load_index()
        idx["provider"] = PROVIDER_ID
        idx.setdefault("segments", [])
        entry = dict(meta)
        entry["segment_index"] = int(index)
        entry["file"] = os.path.basename(path)
        idx["segments"] = [s for s in idx["segments"]
                           if int(s.get("segment_index", -1)) != int(index)]
        idx["segments"].append(entry)
        idx["segments"].sort(key=lambda s: int(s["segment_index"]))
        self.save_index(idx)
        return path

    def load_segment(self, index: int):
        """Return (video, audio, meta) of a stored segment, or None."""
        from safetensors.torch import load_file

        path = self.seg_path(index)
        if not os.path.isfile(path):
            return None
        tensors = load_file(path)
        idx = self.load_index()
        meta = next((s for s in idx.get("segments", [])
                     if int(s.get("segment_index", -1)) == int(index)), {})
        return tensors["video"], tensors["audio"], meta

    def latest_segment(self):
        idx = self.load_index()
        segs = idx.get("segments", [])
        if not segs:
            return None
        return max(int(s["segment_index"]) for s in segs)

    def record_trim(self, segment_index: int, frames: int, audio_steps: int) -> list:
        idx = self.load_index()
        idx.setdefault("trim_events", [])
        idx["trim_events"].append({
            "segment_index": int(segment_index),
            "frames": int(frames),
            "audio_steps": int(audio_steps),
        })
        self.save_index(idx)
        return idx["trim_events"]


# --------------------------------------------------------------------------
# preparation: write the protected prefix, build the AV mask
# --------------------------------------------------------------------------

def plan_continuation(prev_meta: dict | None,
                      target_frames: int,
                      branch: str = BRANCH_GENERATED_AUDIO,
                      prefix_frames: int = VIDEO_PREFIX_FRAMES) -> dict:
    """Decide what this segment must do. Pure, no tensors."""
    vt = video_tokens_for_prefix(prefix_frames)
    at = audio_prefix_steps(prefix_frames)
    if branch not in (BRANCH_GENERATED_AUDIO, BRANCH_DRIVING_AUDIO):
        raise ValueError("unknown audio branch: %r" % branch)
    active = prev_meta is not None
    return {
        "active": active,
        "provider": PROVIDER_ID,
        "branch": branch,
        "video_prefix_frames": prefix_frames,
        "video_prefix_tokens": vt,
        "audio_prefix_steps": 0 if branch == BRANCH_DRIVING_AUDIO else at,
        "target_frames": int(target_frames),
        "new_frames": int(target_frames) - (prefix_frames if active else 0),
    }


def build_av_mask(video_shape, audio_shape, prefix_tokens: int,
                  prefix_steps: int, device=None):
    """Build the Core-native NestedTensor AV denoise mask.

    0 = keep (protected, copied from the previous accepted segment)
    1 = regenerate
    """
    import torch

    vt = video_shape[2]
    at = audio_shape[-1]
    if prefix_tokens > vt:
        raise ValueError("prefix %d tokens exceeds target %d" % (prefix_tokens, vt))
    if prefix_steps > at:
        raise ValueError("prefix %d audio steps exceeds target %d" % (prefix_steps, at))

    vmask = torch.ones((video_shape[0], 1, vt, 1, 1), device=device)
    if prefix_tokens:
        vmask[:, :, :prefix_tokens] = 0.0

    amask = torch.ones((audio_shape[0], 1, audio_shape[-2], at), device=device)
    if prefix_steps:
        amask[:, :, :, :prefix_steps] = 0.0
    return vmask, amask


# --------------------------------------------------------------------------
# guide resolution inside the protected window (DELETE / TRANSLATE / KEEP)
# --------------------------------------------------------------------------

def resolve_guides(keyframes: list, protected_frames: int, frame_count: int):
    """Apply the three-branch rule. Never silently shifts a user's timing."""
    kept, actions = [], []
    for kf in keyframes or []:
        idx = int(kf.get("resolved_frame_index", 0))
        entry = dict(kf)
        if idx >= protected_frames:
            actions.append({"frame": idx, "action": "KEEP", "reason": "beyond protected window"})
            kept.append(entry)
            continue
        if "h3_translate" in kf:
            target = int(kf["h3_translate"])
            if target < protected_frames:
                raise ValueError(
                    "timeline compiler asked to translate frame %d to %d, "
                    "which is still inside the protected %d frame window"
                    % (idx, target, protected_frames))
            if target >= frame_count:
                raise ValueError(
                    "timeline compiler asked to translate frame %d to %d, "
                    "past the segment's %d frames" % (idx, target, frame_count))
            entry["resolved_frame_index"] = target
            entry.pop("h3_translate", None)
            actions.append({"frame": idx, "action": "TRANSLATE",
                            "to": target, "reason": "timeline compiler supplied target"})
            kept.append(entry)
            continue
        role = kf.get("h3_guide_role") or ("anchor" if idx == 0 else "protected_region")
        actions.append({"frame": idx, "action": "DELETE",
                        "reason": "%s inside protected window" % role})
    return kept, actions


# --------------------------------------------------------------------------
# deterministic assembly assertions
# --------------------------------------------------------------------------

def expected_total_frames(segments: list, prefix_frames: int = VIDEO_PREFIX_FRAMES, external_first_prefix=False) -> int:
    """Segment 1 contributes fully; every later segment loses its prefix once."""
    if not segments:
        return 0
    ordered = sorted(segments, key=lambda s: int(s["segment_index"]))
    total = int(ordered[0]["frames"]) - (int(prefix_frames) if external_first_prefix else 0)
    for s in ordered[1:]:
        total += int(s["frames"]) - int(prefix_frames)
    return total


def assert_assembly(index: dict,
                    final_frames: int | None = None,
                    final_duration: float | None = None,
                    audio_duration: float | None = None,
                    fps: float = float(FPS),
                    prefix_frames: int = VIDEO_PREFIX_FRAMES) -> dict:
    """Deterministic, scriptable assertions. Nothing here is a judgement call."""
    segments = sorted(index.get("segments", []), key=lambda s: int(s["segment_index"]))
    trims = index.get("trim_events", [])
    report: dict[str, Any] = {"checks": [], "provider": index.get("provider", PROVIDER_ID)}
    ok = True

    def add(name, passed, detail):
        nonlocal ok
        report["checks"].append({"check": name, "pass": bool(passed), "detail": detail})
        if not passed:
            ok = False

    # 1. the 39 frame prefix of every continuation segment is trimmed exactly once
    continuation_indices = {int(s["segment_index"]) for s in segments[1:]}
    if index.get('_external_first_prefix') and segments:
        continuation_indices.add(int(segments[0]['segment_index']))
    counts: dict[int, int] = {}
    for ev in trims:
        counts[int(ev["segment_index"])] = counts.get(int(ev["segment_index"]), 0) + 1
    frames_by_index = {int(s["segment_index"]): int(s["frames"]) for s in segments}
    # Stale/foreign trim records must produce a failed check, not StopIteration.
    bad_once = {i: c for i, c in counts.items()
                if c != 1 or frames_by_index.get(i, 0) == 0}
    stray = sorted(set(counts) - continuation_indices)
    add("trim_once_per_continuation_prefix",
        not bad_once and not stray,
        "counts=%s stray=%s" % (counts, stray))
    for ev in trims:
        si = int(ev["segment_index"])
        if si in continuation_indices and int(ev["frames"]) != int(prefix_frames):
            add("trim_width_is_prefix", False,
                "segment %d trimmed %s frames, expected %d"
                % (si, ev["frames"], prefix_frames))
            break
    else:
        add("trim_width_is_prefix", True, "every trim removed exactly %d frames" % prefix_frames)

    # 2. frame bookkeeping
    if final_frames is not None:
        exp = expected_total_frames(segments, prefix_frames, index.get('_external_first_prefix',False))
        add("final_frame_count", int(final_frames) == exp,
            "expected=%d actual=%s" % (exp, final_frames))
        if final_duration is not None:
            exp_dur = exp / fps
            add("final_duration", abs(float(final_duration) - exp_dur) <= DURATION_TOLERANCE_SEC,
                "expected=%.4fs actual=%.4fs tol=%.4fs" % (exp_dur, float(final_duration), DURATION_TOLERANCE_SEC))

    # 3. A/V drift
    if final_duration is not None and audio_duration is not None:
        drift = abs(float(final_duration) - float(audio_duration))
        add("av_drift", drift <= AV_DRIFT_TOLERANCE_SEC,
            "video=%.4fs audio=%.4fs drift=%.4fs tol=%.4fs"
            % (float(final_duration), float(audio_duration), drift, AV_DRIFT_TOLERANCE_SEC))

    # 4. every stored segment declares the same provider
    provs = sorted({str(s.get("provider", PROVIDER_ID)) for s in segments})
    add("single_provider", provs in ([], [PROVIDER_ID]),
        "providers=%s" % provs)

    report["pass"] = ok
    return report
