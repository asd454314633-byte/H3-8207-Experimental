"""V28 Director - shared paths, config and crash-safe state writing.

Design rules baked into this module (all from verified project history):
  * No dependency is *added* to the 8197 interpreter. It is the shared
    <COMFYUI_DIR>/ComfyUI_H3_V26_Lab/venv (uv cpython 3.13); installing anything there
    could break the frozen V27 baseline, so this package is stdlib-only with ONE
    exception: `psutil`, which ComfyUI itself already requires and which is already
    present (7.2.2). Every psutil call site has a ctypes/win32 fallback, and
    v28_bonsai_runtime degrades if the import ever fails.
  * No new ComfyUI environment: everything lives under the 8197 root.
  * Atomic writes use a UNIQUE temp name per call. A fixed temp name is a known
    Windows failure mode (PermissionError [Errno 13] that never recovers).
"""
from __future__ import annotations

import itertools
import json
import os
import tempfile
import time
from pathlib import Path

# --- the one and only ComfyUI root (8197) --------------------------------
COMFY_ROOT = Path(os.environ.get("H3_COMFY_ROOT", r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab"))
DIRECTOR_RUNTIME_ROOT = COMFY_ROOT / "director_runtime"
DIRECTOR_STATE_ROOT = DIRECTOR_RUNTIME_ROOT / "director_common"
DIRECTOR_LOGS_DIR = DIRECTOR_STATE_ROOT / "logs"
DIRECTOR_CACHE_DIR = DIRECTOR_STATE_ROOT / "cache"
BONSAI_ROOT = DIRECTOR_RUNTIME_ROOT / "bonsai2"
BONSAI_RUNTIME_DIR = DIRECTOR_RUNTIME_ROOT / "bonsai2_cuda_lab" / "runtime"
BONSAI_MODELS_DIR = BONSAI_ROOT / "models"
BONSAI_SCRIPTS_DIR = BONSAI_ROOT / "scripts"
BONSAI_LOGS_DIR = BONSAI_ROOT / "logs"
BONSAI_CACHE_DIR = BONSAI_ROOT / "cache"
RUNTIME_JSON = BONSAI_ROOT / "runtime.json"

COMFY_OUTPUT = COMFY_ROOT / "output"
MC_SLOT_DIRNAME = "h3_context"          # pack default, see nodes.py:_resolve_latent_path
MC_CLIP_TEMPLATE = "clip_%05d.safetensors"

V28_PKG_DIR = COMFY_ROOT / "custom_nodes" / "H3_V28_Director"

# Project state deliberately lives OUTSIDE the workflow JSON (task section 28)
PROJECTS_ROOT = Path(os.environ.get(
    "H3_V28_PROJECTS", r"<H3_PROJECT_DIR>\V28_PROJECTS"))

# Frozen V27 identity, recomputed at P0 (see V28_V27_FREEZE_RECORD.txt)
V27_CANONICAL_NAME = "MiniMax_H3_全中文导演台_v027_CONTINUATION_DEV.json"
V27_SHA256 = "bbc6a26d7b6cebcf4863f94dfc011b58e037aecc6917c10de1cf4b311f7aa88c"
V27_NODE_COUNT = 172
V27_LINK_COUNT = 216
V28_DEV_NAME = "MiniMax_H3_全中文导演台_v028_DIRECTOR_DEV.json"
PROJECT_DIR = Path(r"<H3_PROJECT_DIR>")

MOTION_CONTEXT_PACK_VERSION = "0.6.2"
# V27 has no such field; V28 defines it as pack version + slot naming contract.
V27_MOTION_CONTEXT_VERSION = f"motion-context-pack {MOTION_CONTEXT_PACK_VERSION} " \
                             f"+ {MC_SLOT_DIRNAME}/{MC_CLIP_TEMPLATE}"

# Ports the director server must never take (task section 6)
FORBIDDEN_PORTS = frozenset({8188, 8193, 8196, 8197, 8199})
DIRECTOR_PORT_MIN, DIRECTOR_PORT_MAX = 18197, 18999
DIRECTOR_HOST = "127.0.0.1"

# Verified V27 graph wiring (8197 live copy; do not re-derive at runtime)
NODE = {
    "console": 159,            # H3OperationSelector - the single user console
    "prompt_ref2va": 138,      # PrimitiveStringMultiline, branch=ref2va
    "prompt_fl2va": 914,       # PrimitiveStringMultiline, branch=fl2va
    "prompt_role": 915,        # H3VideoPromptRole.base_prompt <- 138
    "ref2va": 136,             # MiniMaxH3ReferenceToVideo
    "ref_images": [687, 688, 689, 690, 1001, 1002, 1003, 1004, 1005],  # neutral x9
    "duration_sec": 132,       # PrimitiveFloat (seconds)
    "frames_expr": 131,        # ComfyMathExpression - derives legal frame count
    "seed": 142,               # SeedNode -> N129 RandomNoise.noise_seed (linked)
    "noise": 129,
    "continuation_switch": 992,  # H3ContinuationSelector (UI-only, stripped at submit)
    "mc_apply": 993,
    "mc_trim": 994,
    "mc_save": 995,            # clip_index == the segment about to be generated
    "mc_load": 996,            # clip_index == last ACCEPTED segment (0 = none)
    "mc_chain": 997,           # segments == how many clips before auto-stop
}

# The frame law is V27's own expression, copied verbatim so V28 can never
# disagree with the graph about what a legal clip length is.
_H3_FRAME_LAW = "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17"
H3_FPS = 24


def seconds_to_frames(seconds: float) -> int:
    """Evaluate V27's N131 expression. Keeps 17g+5 VAE alignment."""
    a = max(5.0, round(float(seconds) * H3_FPS))
    return int(a + (5 - (a % 17)) % 17)


def frames_to_seconds(frames: int) -> float:
    return round(frames / H3_FPS, 3)


def ensure_dirs() -> None:
    for p in (DIRECTOR_LOGS_DIR, DIRECTOR_CACHE_DIR, BONSAI_RUNTIME_DIR,
              BONSAI_MODELS_DIR, BONSAI_SCRIPTS_DIR, BONSAI_LOGS_DIR,
              BONSAI_CACHE_DIR, PROJECTS_ROOT):
        p.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    """tmp -> flush -> fsync -> close -> rename. Never overwrite the only copy."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    # durability of the rename itself on the containing directory is not
    # available on Windows; best effort fsync of the file we just moved.
    with path.open("rb") as f:
        try:
            os.fsync(f.fileno())
        except OSError:
            pass


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_json_raw(Path(path), text)


def atomic_write_json_raw(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


CORRUPT_NOTE_NAME = "_corrupt_quarantine.log"
_corrupt_seq = itertools.count(1)


def _note_corrupt(src: Path, corpse: Path, exc: Exception, moved: bool) -> None:
    """The quarantine is invisible by design (it renames, it does not log), so a
    card that suddenly looks empty has no trace of WHY. One append-only line per
    event, under a name a maintainer is told about in V28_RECOVERY_RULES. Best
    effort: never let the bookkeeping replace the exception the caller handles."""
    try:
        note = PROJECTS_ROOT / CORRUPT_NOTE_NAME
        note.parent.mkdir(parents=True, exist_ok=True)
        with note.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                     f"{'QUARANTINED' if moved else 'QUARANTINE_FAILED'} "
                     f"pid={os.getpid()} file={src} -> {corpse.name} "
                     f"err={str(exc)[:160]}\n")
    except Exception:                                    # noqa: BLE001
        pass


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        # A torn file must never be silently treated as absent; keep the corpse.
        # The name carries pid + a counter because second resolution alone is not
        # enough: two readers of the same still-torn file inside one second used to
        # os.replace onto the SAME corpse name, so the second quarantine destroyed
        # the first one's evidence - which is the only copy of a lost session.
        stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{next(_corrupt_seq)}"
        bad = Path(f"{path}.corrupt.{stamp}")
        try:
            os.replace(path, bad)
            moved = True
        except OSError:
            moved = False
        _note_corrupt(Path(path), bad, exc, moved)
        raise


def new_project_id(title: str = "") -> str:
    slug = "".join(c for c in title.strip() if c.isalnum())[:16] or "story"
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{slug}"
