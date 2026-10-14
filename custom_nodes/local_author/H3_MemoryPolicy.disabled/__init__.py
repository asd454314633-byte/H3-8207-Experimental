"""8197 H3 startup policy: lower only the pinned-memory registration cap."""
import logging
from pathlib import Path
from comfy.cli_args import args
import comfy.model_management as mm

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

_expected = Path(r'<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\comfy\model_management.py')
if args.port == 8197 and Path(mm.__file__).resolve() == _expected.resolve():
    if args.disable_pinned_memory or mm.MAX_PINNED_MEMORY <= 0:
        logging.warning('[H3 MemoryPolicy] NOT_APPLIED: pinned memory is disabled')
    elif mm.TOTAL_PINNED_MEMORY != 0:
        logging.error('[H3 MemoryPolicy] NOT_APPLIED: pin initialization already started')
    else:
        _old = mm.MAX_PINNED_MEMORY
        _new = min(_old, 16 * 1024**3)
        mm.MAX_PINNED_MEMORY = _new
        logging.info('[H3 MemoryPolicy] Pinned memory cap: %.6f GiB -> %.6f GiB; MAX_PINNED_MEMORY=%d; TOTAL_PINNED_MEMORY=%d; TOTAL_RAM=%d',
                     _old / 1024**3, _new / 1024**3, mm.MAX_PINNED_MEMORY,
                     mm.TOTAL_PINNED_MEMORY, mm.ram)
