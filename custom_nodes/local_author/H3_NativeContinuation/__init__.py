"""H3 Native Continuation Adapter.

Provider: CORE_NATIVE_MASKED_AV - Native Masked AV Exact Continuation.

This pack adds seven nodes and modifies nothing. It does not patch, wrap or
subclass any ComfyUI function; the per-token video/audio denoise masking is
performed by ComfyUI Core itself (comfy/model_base.py MiniMax H3 extra_conds
-> video_denoise_mask / audio_denoise_mask -> process_timestep).

Frozen contract:
    video prefix = 39 frames (12 latent tokens)
    audio prefix = 65 latent steps (40 Hz, 1.625 s)
    prefix is an engineering constant and is not user selectable

The adapter is one Provider behind the H3 Continuation Provider layer. A
future provider (CONTINUOUS_LATENT_TIMELINE) can replace it without touching
the director's six-segment prompts, references, task advance, logging, UI,
acceptance or state machine.
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from . import core

__version__ = "0.1.0"
PROVIDER_ID = core.PROVIDER_ID

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "core", "__version__"]
