"""H3 Native Continuation Adapter - ComfyUI nodes.

Seven thin nodes. None of them patches, wraps or subclasses anything in
ComfyUI; they only move data around and then hand a plain LATENT (with a
NestedTensor "noise_mask") to the stock SamplerCustomAdvanced. The
per-token video/audio masking is done by ComfyUI Core itself.
"""

from __future__ import annotations

import json
import os
from comfy_execution.utils import get_executing_context

from . import core
from .core import (PROVIDER_ID, BRANCH_GENERATED_AUDIO, BRANCH_DRIVING_AUDIO,
                   VIDEO_PREFIX_FRAMES, AUDIO_PREFIX_STEPS)

CATEGORY = "H3/continuation"

try:  # ComfyUI is present when the nodes actually run
    import comfy.model_management as mm
    import comfy.utils
    from comfy.nested_tensor import NestedTensor
except Exception:  # pragma: no cover - offline unit tests import core only
    mm = None
    NestedTensor = None


def _output_root() -> str:
    try:
        import folder_paths
        return folder_paths.get_output_directory()
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "output")


def _unpack_av(latent, where: str):
    samples = latent["samples"]
    if not getattr(samples, "is_nested", False):
        raise ValueError("%s expects a MiniMax H3 AV latent (NestedTensor), got %s"
                         % (where, type(samples).__name__))
    tensors = list(samples.unbind())
    if len(tensors) != 2:
        raise ValueError("%s expects exactly 2 modalities, got %d" % (where, len(tensors)))
    return tensors[0], tensors[1]


def _pack_av(video, audio):
    return {"samples": NestedTensor((video, audio))}


# ---------------------------------------------------------------------------
# 1. provider + feature detect
# ---------------------------------------------------------------------------

class H3ContinuationProvider:
    DESCRIPTION = ("Declares the continuation provider and verifies at run time that "
                   "ComfyUI Core still exposes the native AV denoise mask contract.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {},
                "optional": {"verify": ("BOOLEAN", {"default": True})}}

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("provider_id", "capabilities_json", "video_prefix_frames", "audio_prefix_steps")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, verify=True):
        if verify:
            checks = core.feature_detect()
        else:
            checks = {"skipped": {"ok": True, "detail": "verify disabled"}}
        caps = {
            "provider": PROVIDER_ID,
            "av_joint_prefix": True,
            "per_token_mask": True,
            "audio_continuity": True,
            "driving_audio_branch": True,
            "prefix_user_selectable": False,
            "feature_detect": checks,
        }
        return (PROVIDER_ID, json.dumps(caps, ensure_ascii=False),
                VIDEO_PREFIX_FRAMES, AUDIO_PREFIX_STEPS)


# ---------------------------------------------------------------------------
# 2. audio branch - two explicit, mutually exclusive semantics
# ---------------------------------------------------------------------------

class H3ContinuationAudioBranch:
    DESCRIPTION = ("GENERATED_AUDIO_CONTINUITY: reuse the previous generated audio tail. "
                   "DRIVING_AUDIO: an authoritative soundtrack is supplied, so the audio "
                   "mask stays fully open and no previous audio is reused.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {},
                "optional": {"driving_audio": ("AUDIO",)}}

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("audio_branch", "audio_prefix_steps")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, driving_audio=None):
        if driving_audio is None:
            return (BRANCH_GENERATED_AUDIO, AUDIO_PREFIX_STEPS)
        return (BRANCH_DRIVING_AUDIO, 0)


# ---------------------------------------------------------------------------
# 3. prepare - write the protected prefix, build the AV mask
# ---------------------------------------------------------------------------

class H3ContinuationPrepare:
    DESCRIPTION = ("Native Masked AV Exact Continuation: copy the tail of the previous "
                   "accepted segment into this segment's head, then hand Core a "
                   "video+audio denoise mask that freezes it (0 = keep, 1 = regenerate).")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT",),
                "project_id": ("STRING", {"default": ""}),
                "segment_index": ("INT", {"default": 0, "min": 0, "max": 99999}),
            },
            "optional": {
                "enabled": ("BOOLEAN", {"forceInput": True}),
                "provider_id": ("STRING", {"forceInput": True}),
                "audio_branch": ("STRING", {"forceInput": True}),
                "prev_latent": ("LATENT",),
                "clean_rebase_enabled": ("BOOLEAN", {"default": False}),
                "clean_rebase_segment": ("INT", {"default": 3, "min": 0, "max": 99999}),
            },
        }

    RETURN_TYPES = ("LATENT", "STRING", "INT", "INT", "INT")
    RETURN_NAMES = ("latent", "plan_json", "video_prefix_frames", "video_prefix_tokens",
                    "audio_prefix_steps")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, latent, enabled=False, project_id="", segment_index=0,
            provider_id=None, audio_branch=None, prev_latent=None,
            clean_rebase_enabled=False, clean_rebase_segment=3):
        import torch

        video, audio = _unpack_av(latent, "H3ContinuationPrepare")
        frame_count = core.frames_from_video_tokens(video.shape[2])

        if provider_id is not None and provider_id != PROVIDER_ID:
            raise ValueError("unsupported continuation provider %r; this adapter "
                             "implements %s only" % (provider_id, PROVIDER_ID))

        if not enabled:
            plan = {"active": False, "provider": PROVIDER_ID,
                    "branch": audio_branch or BRANCH_GENERATED_AUDIO,
                    "video_prefix_frames": 0, "video_prefix_tokens": 0,
                    "audio_prefix_steps": 0, "target_frames": frame_count,
                    "new_frames": frame_count}
            return (latent, json.dumps(plan, ensure_ascii=False), 0, 0, 0)

        policy = core.resolve_continuation_policy(
            enabled=enabled, segment_index=int(segment_index),
            reuse_previous_latent=True, save_current_latent=True,
            trim_reused_prefix=True,
            clean_rebase_enabled=clean_rebase_enabled,
            clean_rebase_segment=clean_rebase_segment)
        if policy["clean_rebase_active"]:
            plan = {"active": True, "provider": PROVIDER_ID,
                    "branch": audio_branch or BRANCH_GENERATED_AUDIO,
                    "clean_rebase": True, "segment_index": int(segment_index),
                    "prev_source": None, "video_prefix_frames": 0,
                    "video_prefix_tokens": 0, "audio_prefix_steps": 0,
                    "target_frames": frame_count, "new_frames": frame_count,
                    "reuse_previous_latent": False,
                    "save_current_latent": True,
                    "trim_reused_prefix": False}
            return (latent, json.dumps(plan, ensure_ascii=False), 0, 0, 0)

        core.feature_detect()

        branch = audio_branch or BRANCH_GENERATED_AUDIO
        if prev_latent is not None:
            prev_video, prev_audio = _unpack_av(prev_latent, "H3ContinuationPrepare.prev")
            prev_source = "input"
        else:
            store = core.ContinuationStore(_output_root(), project_id)
            prev_index = int(segment_index) - 1
            if prev_index < 0:
                raise ValueError(
                    "continuation is ON but segment_index=%d has no predecessor; "
                    "segment 1 must run with continuation OFF" % int(segment_index))
            loaded = store.load_segment(prev_index)
            if loaded is None:
                latest = store.latest_segment()
                raise ValueError(
                    "continuation is ON but no accepted latent is stored for segment %d "
                    "(project %r, latest stored = %s)"
                    % (prev_index, project_id or "default", latest))
            prev_video, prev_audio, _meta = loaded
            prev_source = "store:seg_%05d" % prev_index

        plan = core.plan_continuation({"segment_index": segment_index}, frame_count, branch)
        vt, at = plan["video_prefix_tokens"], plan["audio_prefix_steps"]

        if prev_video.shape[2] < vt:
            raise ValueError("previous segment has %d video tokens, need %d for a %d frame prefix"
                             % (prev_video.shape[2], vt, VIDEO_PREFIX_FRAMES))
        if prev_audio.shape[-1] < (at or 0):
            raise ValueError("previous segment has %d audio steps, need %d"
                             % (prev_audio.shape[-1], at))
        if video.shape[2] <= vt:
            raise ValueError("target segment has %d video tokens; a %d frame prefix needs "
                             "at least %d + 1" % (video.shape[2], VIDEO_PREFIX_FRAMES, vt))

        device = video.device
        video = video.clone()
        audio = audio.clone()
        prefix, spatial_transform = core.adapt_video_prefix(prev_video, tuple(video.shape), vt, video.dtype)
        if spatial_transform is not None:
            import logging
            logging.info('H3 Native spatial prefix resample: %s', json.dumps(spatial_transform))
        video[:, :, :vt] = prefix.to(device=device)
        if at:
            audio[..., :at] = prev_audio[..., -at:].to(device=device, dtype=audio.dtype)

        vmask, amask = core.build_av_mask(video.shape, audio.shape, vt, at, device=device)
        out = _pack_av(video, audio)
        out["noise_mask"] = NestedTensor((vmask, amask))

        plan.update({"prev_source": prev_source,
                     "video_prefix_transform": spatial_transform,
                     "protected_frames": VIDEO_PREFIX_FRAMES,
                     "mask_video_zero_tokens": int(vt),
                     "mask_audio_zero_steps": int(at)})
        return (out, json.dumps(plan, ensure_ascii=False),
                VIDEO_PREFIX_FRAMES, vt, at)


# ---------------------------------------------------------------------------
# 4. guides - DELETE / TRANSLATE / KEEP inside the protected window
# ---------------------------------------------------------------------------

class H3ContinuationGuides:
    DESCRIPTION = ("Guides resolving inside the protected 39 frame prefix are removed "
                   "(the copied latent is already authoritative there). A guide carrying "
                   "h3_translate is moved by the timeline compiler; guides after the "
                   "prefix are kept untouched.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "latent": ("LATENT",),
            },
            "optional": {"enabled": ("BOOLEAN", {"forceInput": True}),
                         "protected_frames": ("INT", {"default": VIDEO_PREFIX_FRAMES,
                                                      "min": 0, "max": 4096})},
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("positive", "guide_report")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, positive, latent, enabled=False, protected_frames=VIDEO_PREFIX_FRAMES):
        video, _audio = _unpack_av(latent, "H3ContinuationGuides")
        frame_count = core.frames_from_video_tokens(video.shape[2])

        if not enabled:
            return (positive, json.dumps(
                {"active": False, "frame_count": frame_count, "actions": []},
                ensure_ascii=False))

        keyframes = list(positive[0][1].get("minimax_keyframes", []))
        kept, actions = core.resolve_guides(keyframes, int(protected_frames), frame_count)

        out = [list(x) for x in positive]
        for i in range(len(out)):
            d = dict(out[i][1])
            d["minimax_keyframes"] = kept
            out[i] = (out[i][0], d)

        competing = [a for a in actions if a["action"] in ("KEEP",)]
        report = {"active": True, "frame_count": frame_count,
                  "protected_frames": int(protected_frames),
                  "input_guides": len(keyframes), "kept_guides": len(kept),
                  "actions": actions,
                  "guides_inside_protected_window": len(competing) == 0}
        return (out, json.dumps(report, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 5. save the accepted latent of this segment
# ---------------------------------------------------------------------------

class H3ContinuationSave:
    DESCRIPTION = "Persist the accepted AV latent so the next segment can continue from it."
    # Side-effect sink: ComfyUI only executes nodes reachable from OUTPUT_NODEs,
    # so a latent store whose outputs nobody consumes would silently never run
    # (found by Gate 1 on 2026-10-03: segment 0 video rendered, latent never saved).
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT",),
                "project_id": ("STRING", {"default": ""}),
                "segment_index": ("INT", {"default": 0, "min": 0, "max": 99999}),
            },
            "optional": {"enabled": ("BOOLEAN", {"forceInput": True})}
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("store_path", "meta_json")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, latent, enabled=False, project_id="", segment_index=0):
        video, audio = _unpack_av(latent, "H3ContinuationSave")
        if not enabled:
            return ("", json.dumps({"active": False}, ensure_ascii=False))

        context = get_executing_context()
        if not context or not context.prompt_id:
            raise RuntimeError("H3 Native Continuation: cannot persist a latent without its executing prompt_id")

        frames = core.frames_from_video_tokens(video.shape[2])
        meta = {"frames": frames, "video_tokens": int(video.shape[2]),
                "audio_steps": int(audio.shape[-1]), "provider": PROVIDER_ID,
                "prompt_id": context.prompt_id}
        store = core.ContinuationStore(_output_root(), project_id)
        path = store.save_segment(int(segment_index),
                                  video.to("cpu").contiguous(),
                                  audio.to("cpu").contiguous(),
                                  meta)
        meta.update({"path": path, "segment_index": int(segment_index), "active": True})
        return (path, json.dumps(meta, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 6. trim the duplicated prefix - exactly once
# ---------------------------------------------------------------------------

class H3ContinuationTrimOnce:
    DESCRIPTION = ("Drop the duplicated 39 frame prefix and 1.625 s of audio, and record "
                   "the trim so the assembly assertion can prove it happened once.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "project_id": ("STRING", {"default": ""}),
                "segment_index": ("INT", {"default": 0, "min": 0, "max": 99999}),
            },
            "optional": {
                "enabled": ("BOOLEAN", {"forceInput": True}),
                "audio": ("AUDIO",),
                "fps": ("FLOAT", {"default": float(core.FPS), "min": 1.0, "max": 120.0}),
                "trim_frames": ("INT", {"default": VIDEO_PREFIX_FRAMES, "min": 0, "max": 4096}),
                "clean_rebase_enabled": ("BOOLEAN", {"default": False}),
                "clean_rebase_segment": ("INT", {"default": 3, "min": 0, "max": 99999}),
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING")
    RETURN_NAMES = ("images", "audio", "trim_log_json")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, images, enabled=False, project_id="", segment_index=0,
            audio=None, fps=float(core.FPS), trim_frames=VIDEO_PREFIX_FRAMES,
            clean_rebase_enabled=False, clean_rebase_segment=3):
        import torch

        if not enabled:
            return (images, audio, json.dumps({"active": False}, ensure_ascii=False))

        policy = core.resolve_continuation_policy(
            enabled=enabled, segment_index=int(segment_index),
            reuse_previous_latent=True, save_current_latent=True,
            trim_reused_prefix=True,
            clean_rebase_enabled=clean_rebase_enabled,
            clean_rebase_segment=clean_rebase_segment)
        if policy["clean_rebase_active"]:
            return (images, audio, json.dumps(
                {"active": True, "segment_index": int(segment_index),
                 "clean_rebase": True, "trimmed_frames": 0,
                 "audio_steps": 0, "reason": "fresh_epoch_has_no_prefix"},
                ensure_ascii=False))

        if images.shape[0] <= trim_frames:
            raise ValueError("cannot trim %d frames from a %d frame clip"
                             % (trim_frames, images.shape[0]))
        out_images = images[trim_frames:].contiguous()

        out_audio = audio
        audio_steps = 0
        if audio is not None:
            sr = int(audio["sample_rate"])
            cut = int(round(trim_frames / float(fps) * sr))
            w = audio["waveform"]
            if w.shape[-1] <= cut:
                raise ValueError("cannot trim %d audio samples from %d"
                                 % (cut, w.shape[-1]))
            out_audio = {"waveform": w[..., cut:].contiguous(), "sample_rate": sr}
            audio_steps = core.audio_steps_for_frames(int(trim_frames))

        store = core.ContinuationStore(_output_root(), project_id)
        events = store.record_trim(int(segment_index), int(trim_frames), audio_steps)
        return (out_images, out_audio,
                json.dumps({"active": True, "trimmed_frames": int(trim_frames),
                            "audio_steps": audio_steps,
                            "events_for_this_segment":
                                [e for e in events if int(e["segment_index"]) == int(segment_index)]},
                           ensure_ascii=False))


# ---------------------------------------------------------------------------
# 7. deterministic assembly assertions
# ---------------------------------------------------------------------------

class H3ContinuationAssemble:
    DESCRIPTION = ("Deterministic post-assembly assertions: final frame count, final "
                   "duration, every 39 frame prefix trimmed exactly once, A/V drift.")
    # Assertion terminal: must always run when present, otherwise the
    # deterministic assembly assertions are silently skipped.
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"project_id": ("STRING", {"default": ""})},
            "optional": {
                "images": ("IMAGE",),
                "audio": ("AUDIO",),
                "fps": ("FLOAT", {"default": float(core.FPS), "min": 1.0, "max": 120.0}),
                "cross_group_json": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "BOOLEAN")
    RETURN_NAMES = ("assert_report", "all_pass")
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, project_id="", images=None, audio=None, fps=float(core.FPS),cross_group_json=''):
        store = core.ContinuationStore(_output_root(), project_id)
        index = store.load_index()
        if cross_group_json:
            import copy,nodes
            proof=nodes.NODE_CLASS_MAPPINGS['H3CrossGroupPrevious'].verify(cross_group_json)
            if proof['source_project']==project_id:raise ValueError('跨组组装目标与前驱相同')
            index=copy.deepcopy(index);index['_external_first_prefix']=True

        final_frames = int(images.shape[0]) if images is not None else None
        final_duration = (final_frames / float(fps)) if final_frames is not None else None
        audio_duration = None
        if audio is not None:
            w = audio["waveform"]
            audio_duration = float(w.shape[-1]) / float(audio["sample_rate"])

        report = core.assert_assembly(index, final_frames, final_duration,
                                      audio_duration, fps=fps)
        report["segments"] = index.get("segments", [])
        report["observed"] = {"final_frames": final_frames,
                              "final_duration": final_duration,
                              "audio_duration": audio_duration}
        return (json.dumps(report, ensure_ascii=False, indent=2), bool(report["pass"]))


NODE_CLASS_MAPPINGS = {
    "H3ContinuationProvider": H3ContinuationProvider,
    "H3ContinuationAudioBranch": H3ContinuationAudioBranch,
    "H3ContinuationPrepare": H3ContinuationPrepare,
    "H3ContinuationGuides": H3ContinuationGuides,
    "H3ContinuationSave": H3ContinuationSave,
    "H3ContinuationTrimOnce": H3ContinuationTrimOnce,
    "H3ContinuationAssemble": H3ContinuationAssemble,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ContinuationProvider": "H3 连续 Provider（特性探测）",
    "H3ContinuationAudioBranch": "H3 连续 音频分支",
    "H3ContinuationPrepare": "H3 连续 前缀与 AV 掩码",
    "H3ContinuationGuides": "H3 连续 Guide 保护区裁决",
    "H3ContinuationSave": "H3 连续 保存已接受潜空间",
    "H3ContinuationTrimOnce": "H3 连续 裁剪重复前缀（一次）",
    "H3ContinuationAssemble": "H3 连续 组装确定性断言",
}
