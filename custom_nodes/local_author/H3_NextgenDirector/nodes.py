import json
import math

from comfy_api.latest import ComfyExtension, io
from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide
from comfy.ldm.minimax.model import FRAME_PER_TOKEN

FPS = 24
MAX_GUIDES = 4
GUIDE_TYPES = {"image", "clip", "audio", "clip+audio"}


def _visible_frame(seconds):
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Guide time must be a finite non-negative number")
    return math.floor(seconds * FPS + 0.5)


def _effective_clip_frames(count):
    if count < 5:
        return 1
    return count - ((count - 5) % 17)


class H3GuideTimeline(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        default = json.dumps({"schema_version": 1, "fps": 24, "guides": [
            {"id": "g1", "enabled": True, "type": "image", "time_seconds": 0.0},
            {"id": "g2", "enabled": True, "type": "image", "time_seconds": 2.5},
            {"id": "g3", "enabled": True, "type": "image", "time_seconds": 4.0}
        ]}, ensure_ascii=False)
        return io.Schema(
            node_id="H3GuideTimeline",
            display_name="H3 Guide Timeline",
            category="H3 Director/Timeline",
            description="Place image, clip, audio, or clip+audio guides at arbitrary 24 fps frames. Uses the native MiniMaxH3AddGuide implementation.",
            search_aliases=["MiniMax H3 timeline", "director keyframes", "guide timeline"],
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae", optional=True, advanced=True),
                io.Int.Input("protected_frames", default=0, min=0, max=9999, advanced=True,
                             tooltip="Connect the active Prepare output for continuation segments. Keep 0 for a standalone segment."),
                io.Image.Input("guide_1_image", optional=True), io.Audio.Input("guide_1_audio", optional=True, advanced=True),
                io.Image.Input("guide_2_image", optional=True), io.Audio.Input("guide_2_audio", optional=True, advanced=True),
                io.Image.Input("guide_3_image", optional=True), io.Audio.Input("guide_3_audio", optional=True, advanced=True),
                io.Image.Input("guide_4_image", optional=True), io.Audio.Input("guide_4_audio", optional=True, advanced=True),
                io.String.Input("guides_json", default=default, multiline=True, advanced=True),
            ],
            outputs=[io.Conditioning.Output("positive"), io.String.Output("compile_report")],
        )

    @classmethod
    def execute(cls, positive, latent, vae, protected_frames, guides_json,
                audio_vae=None, guide_1_image=None, guide_1_audio=None,
                guide_2_image=None, guide_2_audio=None, guide_3_image=None,
                guide_3_audio=None, guide_4_image=None, guide_4_audio=None):
        timeline = json.loads(guides_json)
        if timeline.get("schema_version") != 1 or timeline.get("fps") != FPS:
            raise ValueError("Unsupported H3 Guide Timeline schema or frame rate")
        guides = timeline.get("guides", [])
        if len(guides) > MAX_GUIDES:
            raise ValueError(f"At most {MAX_GUIDES} guide entries are supported in this candidate")
        image_inputs = [guide_1_image, guide_2_image, guide_3_image, guide_4_image]
        audio_inputs = [guide_1_audio, guide_2_audio, guide_3_audio, guide_4_audio]
        samples = latent["samples"]
        if not samples.is_nested or len(samples.tensors) != 2 or samples.tensors[0].ndim != 5:
            raise ValueError("Expected the native MiniMax H3 AV latent")
        video = samples.tensors[0]
        target_frames = sum(FRAME_PER_TOKEN[k % 5] for k in range(video.shape[2]))
        used_ids = set()
        report = []
        for index, guide in enumerate(guides):
            if not guide.get("enabled", True):
                continue
            guide_id = str(guide.get("id", ""))
            if not guide_id or guide_id in used_ids:
                raise ValueError("Every enabled guide needs a unique non-empty id")
            used_ids.add(guide_id)
            kind = guide.get("type")
            if kind not in GUIDE_TYPES:
                raise ValueError(f"Unsupported guide type: {kind}")
            image, audio = image_inputs[index], audio_inputs[index]
            if kind in ("image", "clip") and image is None:
                raise ValueError(f"Guide {guide_id} needs an image/video input")
            if kind == "audio" and audio is None:
                raise ValueError(f"Guide {guide_id} needs an audio input")
            if kind == "clip+audio" and (image is None or audio is None):
                raise ValueError(f"Guide {guide_id} needs both video and audio inputs")
            visible = _visible_frame(float(guide["time_seconds"]))
            internal = visible + int(protected_frames)
            output = MiniMaxH3AddGuide.execute(
                positive, latent, internal, vae=vae, audio_vae=audio_vae,
                image=image if kind in ("image", "clip", "clip+audio") else None,
                audio=audio if kind in ("audio", "clip+audio") else None)
            positive = output.result[0]
            source_count = int(image.shape[0]) if image is not None else None
            effective = _effective_clip_frames(source_count) if source_count is not None else None
            if internal >= target_frames:
                raise ValueError(f"Guide {guide_id} maps to internal frame {internal}, outside {target_frames} frames")
            report.append({"id": guide_id, "type": kind, "time_seconds": float(guide["time_seconds"]),
                           "visible_frame_idx": visible, "protected_frames": int(protected_frames),
                           "internal_frame_idx": internal, "target_frame_count": target_frames,
                           "source_frame_count": source_count, "effective_guide_frames": effective})
        return io.NodeOutput(positive, json.dumps({"fps": FPS, "guides": report}, ensure_ascii=False))

