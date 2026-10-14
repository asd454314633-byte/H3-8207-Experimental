"""Shared loader + disk-isolation helper for the V28 audit tests.

This is *test-only* code (stdlib only). It does two things the audit needs:

  1. Import the audited modules without running the package's real ``__init__.py``
     (which attaches HTTP routes and calls ``ensure_dirs()`` on the production
     tree). We register a synthetic parent module whose ``__path__`` points at
     the package directory, so the modules' own ``from . import ...`` statements
     resolve. If the package is ever made bare-name importable again, this loader
     uses the bare names instead.
  2. Redirect every on-disk path constant in ``v28_paths`` into a per-test temp
     directory, so nothing can be written into
     ``<H3_PROJECT_DIR>\\V28_PROJECTS`` or the real ComfyUI tree. That only
     works while each module exists ONCE - see ``load()`` / ``identity_check()``,
     because a second unpatched copy keeps the production constants.
"""
from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import sys
import tempfile
import types
import contextlib

HERE = pathlib.Path(__file__).resolve().parent
PKG_DIR = HERE.parent                      # ...\custom_nodes\H3_V28_Director
PKG_NAME = "_h3v28_under_test"             # synthetic parent, NOT the real package
MODULES = ("v28_paths", "v28_schemas", "v28_prompt_compiler", "v28_project",
           "v28_state_machine", "v28_provider", "v28_director_prompts",
           "v28_runtime_contract", "v28_bonsai_runtime", "v28_bonsai_provider")

sys.dont_write_bytecode = True            # do not litter the package __pycache__
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                      # pragma: no cover
        pass

if str(PKG_DIR) not in sys.path:
    sys.path.insert(0, str(PKG_DIR))


def _synthetic_package() -> types.ModuleType:
    pkg = sys.modules.get(PKG_NAME)
    if pkg is None:
        pkg = types.ModuleType(PKG_NAME)
        pkg.__path__ = [str(PKG_DIR)]
        pkg.__package__ = PKG_NAME
        sys.modules[PKG_NAME] = pkg
    return pkg


_synthetic_package()


def load(name: str):
    """Import one audited module under EXACTLY ONE module identity.

    Getting this wrong is not theoretical. Every audited module resolves its
    siblings with `from . import v28_paths as P`, which means the object it uses
    is `<synthetic>.v28_paths`. Importing the bare name first - which the previous
    version of this function did, "preferring a bare-name import" - created a
    SECOND copy of `v28_paths` (and of every other module) with its own, unpatched
    path constants. `isolate()` could only patch one of the two copies, so the
    tests read and asserted against the temp copy while the code under test wrote
    through the other copy straight into the production
    `<H3_PROJECT_DIR>\\V28_PROJECTS` and the real
    `output\\h3_context\\clip_NNNNN.safetensors` Motion Context slot directory -
    and still reported a clean run. The synthetic-package import is therefore the
    ONLY one performed here; the bare name is registered as an alias to that same
    object, never as a second module.
    """
    key = f"{PKG_NAME}.{name}"
    mod = sys.modules.get(key)
    if mod is None:
        mod = importlib.import_module(key)
        sys.modules[key] = mod
    other = sys.modules.get(name)
    if other is not None and other is not mod:
        # A bare copy exists => isolation is a lie again. Fail loudly, do not
        # silently paper over it: this is the exact condition that let test writes
        # reach the production tree once already.
        raise RuntimeError(
            f"double module identity for {name}: "
            f"id(bare)={id(other)} id({key})={id(mod)}. "
            f"Something imported {name} bypassing _v28_bootstrap.load().")
    sys.modules[name] = mod                          # alias == the same object
    return mod


def load_all() -> dict:
    return {m: load(m) for m in MODULES}


def identity_check(names=MODULES) -> list:
    """Return a list of human-readable isolation breaches (empty == isolated).

    Two things have to hold for the temp isolation to be real rather than
    nominal: one module must exist under one object only, and every module that
    consumed `v28_paths` at import time must hold the SAME object the tests patch.
    """
    bad = []
    paths = sys.modules.get(f"{PKG_NAME}.v28_paths")
    for n in names:
        syn = sys.modules.get(f"{PKG_NAME}.{n}")
        if syn is None:
            continue
        if sys.modules.get(n) is not syn:
            bad.append(f"{n}: bare alias is a different object "
                       f"({id(sys.modules.get(n))} vs {id(syn)})")
        for attr in ("P", "PJ", "PC", "S", "V"):
            held = getattr(syn, attr, None)
            if held is None or not hasattr(held, "__file__"):
                continue
            base = os.path.basename(held.__file__).rsplit(".", 1)[0]
            expected = sys.modules.get(f"{PKG_NAME}.{base}")
            if expected is not None and held is not expected:
                bad.append(f"{n}.{attr} -> {base}: two copies in sys.modules")
    if paths is not None:
        for n in names:
            mod = sys.modules.get(f"{PKG_NAME}.{n}")
            if getattr(mod, "P", None) is not None and mod.P is not paths:
                bad.append(f"{n}.P is not the patched v28_paths object")
    return bad


def isolate(P, root) -> None:
    """Point every path constant of v28_paths at `root` (a temp dir)."""
    root = pathlib.Path(root)
    comfy = root / "comfy_root"
    P.COMFY_ROOT = comfy
    P.DIRECTOR_RUNTIME_ROOT = comfy / "director_runtime"
    P.DIRECTOR_STATE_ROOT = P.DIRECTOR_RUNTIME_ROOT / "director_common"
    P.DIRECTOR_LOGS_DIR = P.DIRECTOR_STATE_ROOT / "logs"
    P.DIRECTOR_CACHE_DIR = P.DIRECTOR_STATE_ROOT / "cache"
    P.BONSAI_ROOT = P.DIRECTOR_RUNTIME_ROOT / "bonsai2"
    P.BONSAI_RUNTIME_DIR = P.BONSAI_ROOT / "runtime"
    P.BONSAI_MODELS_DIR = P.BONSAI_ROOT / "models"
    P.BONSAI_SCRIPTS_DIR = P.BONSAI_ROOT / "scripts"
    P.BONSAI_LOGS_DIR = P.BONSAI_ROOT / "logs"
    P.BONSAI_CACHE_DIR = P.BONSAI_ROOT / "cache"
    P.RUNTIME_JSON = P.BONSAI_ROOT / "runtime.json"
    P.COMFY_OUTPUT = comfy / "output"
    P.V28_PKG_DIR = comfy / "custom_nodes" / "H3_V28_Director"
    P.PROJECT_DIR = root / "director_projects"
    P.PROJECTS_ROOT = P.PROJECT_DIR / "V28_PROJECTS"
    # sweep: any other Path constant (present or added later) must also be inside
    for k, v in list(vars(P).items()):
        if isinstance(v, pathlib.Path) and not str(v).startswith(str(root)):
            setattr(P, k, root / v.name)


@contextlib.contextmanager
def fresh_env():
    """Temp-isolated environment with v28_paths patched; yields the module map.

    The identity check runs BEFORE anything can write: patching one of two module
    copies is what let a previous revision of this harness call itself isolated
    while it was creating real projects under <H3_PROJECT_DIR>\\V28_PROJECTS.
    A breach raises here rather than polluting the production tree quietly.

    The patch is UNDONE on exit, and that matters more than it looks: `isolate()`
    rewrites the constants on the ONE shared module object (single identity is
    enforced above, on purpose), so without the restore every later test in the
    same process inherits a temp root that has already been deleted.
    `test_v28_bonsai_cli_flags.test_cuda_dll_dirs_are_on_path_and_gpu_layers_reach
    _the_server` was the first casualty of that - it asserts the CUDA directories
    made it onto PATH, and with `P.BONSAI_RUNTIME_DIR` pointing at a removed temp
    dir `cuda_dll_dirs()` returns [] and PATH is the shell's. It passed alone and
    failed in a full run, i.e. it depended on alphabetical position, which is not
    a property of the code under test. A new test file sorting before it exposed
    that (2026-09-27, P11 BUG-5 regression).
    """
    root = tempfile.mkdtemp(prefix="h3v28_audit_")
    M = load_all()
    P = M["v28_paths"]
    before = {k: v for k, v in vars(P).items() if isinstance(v, pathlib.Path)}
    isolate(P, root)
    breach = identity_check()
    if breach:
        for k, v in before.items():
            setattr(P, k, v)
        shutil.rmtree(root, ignore_errors=True)
        raise RuntimeError("isolation breach, refusing to run the test: "
                           + "; ".join(breach))
    try:
        yield M, pathlib.Path(root)
    finally:
        for k, v in before.items():
            setattr(P, k, v)
        shutil.rmtree(root, ignore_errors=True)


# --- real-disk fingerprints (used by the no-pollution test) --------------
REAL_WATCHED = (r"<H3_PROJECT_DIR>\V28_PROJECTS",
                r"<H3_PROJECT_DIR>\MiniMax_H3_全中文导演台_v027_CONTINUATION_DEV.json",
                r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\custom_nodes\h3_workflow_helpers",
                r"<COMFYUI_DIR>\ComfyUI_H3_V27_Lab\director_runtime")


def fingerprint(path) -> tuple:
    p = pathlib.Path(path)
    if not p.exists():
        return (str(path), "MISSING", 0, 0, ())
    st = p.stat()
    if p.is_file():
        return (str(path), "FILE", st.st_mtime_ns, st.st_size, ())
    kids = tuple(sorted((x.name, x.stat().st_mtime_ns) for x in p.iterdir()))
    return (str(path), "DIR", st.st_mtime_ns, len(kids), kids)


def fingerprint_all() -> tuple:
    return tuple(fingerprint(p) for p in REAL_WATCHED)
